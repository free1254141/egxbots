"""Current-session eligibility and a bounded parallel lane for open recommendations."""
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from math import isfinite
import os
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from api.daily_recovery_state import read_checkpoint, replace_checkpoint


def expected_session():
    from api.egx_trading_calendar import is_egx_session
    day = datetime.now(ZoneInfo('Africa/Cairo')).date()
    while not is_egx_session(day):
        day -= timedelta(days=1)
    return day.isoformat()


def quote_health(row, session, *, require_trading=False):
    if not row or str(row.get('date') or '')[:10] != session:
        return 'missing_current_session'
    try:
        opening, high, low, close = [float(row[k]) for k in ('open', 'high', 'low', 'close')]
        volume = float(row.get('volume') or 0)
        if not all(isfinite(v) and v > 0 for v in (opening, high, low, close)) or not low <= min(opening, close) <= max(opening, close) <= high:
            return 'invalid_current_ohlc'
        if not isfinite(volume) or volume < 0:
            return 'invalid_volume'
        if require_trading and volume == 0:
            return 'no_trading_volume'
    except (TypeError, ValueError, KeyError):
        return 'invalid_current_ohlc'
    return 'verified'


def _current_quotes(client, symbols, session):
    if not symbols:
        return {}
    rows = (client.table('stock_prices').select('symbol,date,open,high,low,close,volume')
            .eq('exchange', 'EGX').eq('date', session).in_('symbol', list(symbols)).limit(500).execute()).data or []
    return {r['symbol']: r for r in rows}


def eligible_candidates(client, candidates, session):
    from api.symbols_local import _find_latest_file
    path=_find_latest_file('Egypt_all_symbols')
    inventory=json.loads(Path(path).read_text(encoding='utf-8')) if path else []
    listed={r['Symbol'] for r in inventory if r.get('InventorySource')=='EODHD'}
    if not listed:
        raise RuntimeError('Validated EODHD inventory unavailable')
    symbols = list(dict.fromkeys(str(r.get('symbol') or '').split('.')[0].upper() for r in candidates))
    quotes = _current_quotes(client, symbols, session)
    funds = (client.table('stock_fundamentals').select('symbol,data').eq('exchange', 'EGX')
             .in_('symbol', symbols).limit(500).execute()).data or [] if symbols else []
    funds = {r['symbol']: r.get('data') or {} for r in funds}
    accepted, rejected = [], []
    for row in candidates:
        symbol = str(row.get('symbol') or '').split('.')[0].upper()
        reason = quote_health(quotes.get(symbol), session, require_trading=True)
        if reason == 'verified' and str(row.get('date') or '')[:10] != session:
            reason = 'stale_indicator_snapshot'
        fund = funds.get(symbol, {})
        if fund.get('isListed') is False or str(fund.get('listingStatus', '')).lower() in {'delisted', 'suspended'}:
            reason = 'listing_not_eligible'
        if symbol not in listed:
            reason = 'not_in_current_eodhd_inventory'
        (accepted if reason == 'verified' else rejected).append(row if reason == 'verified' else {'symbol': symbol, 'reason': reason})
    return accepted, rejected


def _eodhd_session_quote(client, symbol, session):
    """One authenticated alternate-source request for an unresolved open trade."""
    token=os.getenv('EODHD_API_KEY') or os.getenv('EODHD_API_TOKEN')
    if not token:
        return 'EODHD_not_configured'
    try:
        import requests
        response=requests.get(f'https://eodhd.com/api/eod/{symbol}.EGX',
            params={'api_token':token,'fmt':'json','period':'d','from':session,'to':session},timeout=12)
        if response.status_code!=200:
            return f'EODHD_HTTP_{response.status_code}'
        rows=response.json()
        current=next((r for r in rows if quote_health(r,session)=='verified'),None) if isinstance(rows,list) else None
        if current is None:
            return 'EODHD_missing_current_session'
        row={k:current[k] for k in ('date','open','high','low','close')}
        row.update(symbol=symbol,exchange='EGX',volume=int(current.get('volume') or 0))
        client.table('stock_prices').upsert(row,on_conflict='symbol,exchange,date').execute()
        return 'EODHD_current_session_saved'
    except Exception as error:
        return 'EODHD_' + type(error).__name__  # Never log a token-bearing request URL.


class CriticalPriceLane:
    def __init__(self, client, job_id, session, failed_symbols=None):
        self.client, self.session = client, session
        rows = (client.table('scan_results').select('symbol,exchange').eq('status', 'open')
                .eq('is_public', True).eq('exchange', 'EGX').limit(100).execute()).data or []
        symbols = sorted({r['symbol'] for r in rows})
        quotes = _current_quotes(client, symbols, session)
        self.results, self.futures = {}, {}
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='critical-quotes')
        failed = {s.split('.')[0] for s in (failed_symbols or [])}
        for symbol in symbols:
            if quote_health(quotes.get(symbol), session) == 'verified' and symbol not in failed:
                self.results[symbol] = {'verified': True, 'fetched': False}
            else:
                self.futures[symbol] = self.pool.submit(self._repair, symbol, job_id)

    def _repair(self, symbol, job_id):
        key = f'daily_critical_quote_{job_id}_{symbol}'
        try:
            existing = read_checkpoint(self.client, key)
            if existing:
                return {'verified': False, 'fetched': False, 'reason': 'attempt_already_claimed'}
            claim = replace_checkpoint(self.client, key, {'status': 'running', 'attempts': 1}, None)
            if not claim:
                return {'verified': False, 'fetched': False, 'reason': 'claim_unavailable'}
            from api.tradingview_integration import fetch_tradingview_prices
            # Exactly one provider attempt, including its bounded Yahoo fallback.
            ok, message = fetch_tradingview_prices(f'{symbol}.EGX', max_days=150, refresh_latest=True)
            reason = quote_health(_current_quotes(self.client, [symbol], self.session).get(symbol), self.session)
            if reason!='verified' or not ok:
                alternate=_eodhd_session_quote(self.client,symbol,self.session)
                if alternate=='EODHD_current_session_saved':
                    reason=quote_health(_current_quotes(self.client,[symbol],self.session).get(symbol),self.session)
                elif reason=='verified':
                    reason='current_session_source_unconfirmed'
                ok=ok or alternate=='EODHD_current_session_saved'
                message=f'{message}; {alternate}'
            result = {'verified': reason == 'verified', 'fetched': bool(ok), 'reason': reason,
                      'provider_message': str(message)[:500]}
            replace_checkpoint(self.client, key, {'status': 'verified' if result['verified'] else 'unverified',
                                                  'attempts': 1, **result}, claim)
            print(f'[CRITICAL-QUOTES] {symbol}: {reason}; provider_success={ok}')
            return result
        except Exception as error:
            return {'verified': False, 'fetched': False, 'reason': type(error).__name__}

    def finish(self):
        # Runs in parallel with indicators/news/scans; it never blocks their start.
        wait(self.futures.values())
        for symbol, future in self.futures.items():
            self.results[symbol] = future.result()
        self.pool.shutdown(wait=False)
        return self.results

    @property
    def unverified_symbols(self):
        return [symbol for symbol,future in self.futures.items()
                if not future.done() or not future.result()['verified']]
