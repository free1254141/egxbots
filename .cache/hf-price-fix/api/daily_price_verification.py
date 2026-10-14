"""Verify stored session bars; bounded EODHD recovery, never ticker guessing."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from api.recommendation_freshness import quote_health, _eodhd_session_quote


def _read(client, symbols, session):
    rows = []
    # Every request is bounded below PostgREST's row cap.
    for offset in range(0, len(symbols), 100):
        batch = symbols[offset:offset + 100]
        response = (client.table('stock_prices')
                    .select('symbol,date,open,high,low,close,volume,updated_at')
                    .eq('exchange', 'EGX').eq('date', session)
                    .in_('symbol', batch).limit(len(batch)).execute())
        rows.extend(response.data or [])
    return {row['symbol']: row for row in rows}


def _health(row, session, since):
    health = quote_health(row, session)
    if health != 'verified':
        return health
    # A cached midday bar cannot certify a failed close refresh.
    try:
        stamp = datetime.fromisoformat(str(row.get('updated_at') or '').replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp < since:
            return 'session_not_refreshed'
    except (KeyError, TypeError, ValueError):
        return 'refresh_timestamp_missing'
    return 'verified'


def verify_daily_prices(client, result, session, since, *, fallback=True):
    outcomes = result['results']
    symbols = list(dict.fromkeys(key.rsplit('.', 1)[0] for key in outcomes))
    rows = _read(client, symbols, session)
    unresolved = [symbol for symbol in symbols if _health(rows.get(symbol), session, since) != 'verified']
    alternate = {}
    # One alternate provider request per unresolved symbol. At most 80 requests,
    # two concurrent workers, each transport bounded to 12s; no nested retries.
    if fallback and unresolved:
        selected = unresolved[:80]
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix='session-repair') as pool:
            alternate = dict(zip(selected, pool.map(
                lambda symbol: _eodhd_session_quote(client, symbol, session), selected)))
        rows = _read(client, symbols, session)
    verified = 0
    for ticker, original in outcomes.items():
        symbol = ticker.rsplit('.', 1)[0]
        reason = _health(rows.get(symbol), session, since)
        ok = reason == 'verified'
        verified += int(ok)
        source_message = alternate.get(symbol)
        # A genuine no-bar answer is terminal for this phase, not a claim of
        # delisting. Revisit next scheduled phase; don't replay 0/N immediately.
        retryable = not ok and source_message not in {
            'EODHD_missing_current_session', 'EODHD_HTTP_404', 'EODHD_not_configured'}
        outcomes[ticker] = {**original, 'success': ok,
                            'provider_success': original['success'],
                            'reason': reason, 'retryable': retryable,
                            'alternate': source_message,
                            'price_date': (rows.get(symbol) or {}).get('date'),
                            'refreshed_at': (rows.get(symbol) or {}).get('updated_at')}
    result['provider_success'] = result['success']
    result['success'] = verified
    result['coverage'] = {'scope': 'exchange', 'success': verified, 'total': len(outcomes),
                          'session': session, 'verified_after': since.isoformat(),
                          'alternate_attempted': len(alternate),
                          'alternate_recovered': [symbol for symbol, status in alternate.items()
                              if status == 'EODHD_current_session_saved'
                              and _health(rows.get(symbol), session, since) == 'verified']}
    result['failure_details'] = {ticker: outcome for ticker, outcome in outcomes.items()
                                 if not outcome['success']}
    # Failed verification must not leave a quote eligible for an intraday entry.
    result['observed_quotes'] = {symbol: quote for symbol, quote in result.get('observed_quotes', {}).items()
                                 if any(key.rsplit('.', 1)[0] == symbol and value['success']
                                        for key, value in outcomes.items())}
    return result
