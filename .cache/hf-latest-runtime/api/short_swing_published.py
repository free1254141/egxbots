"""Immutable published entry intent, separate from recalculated signal eligibility."""
from api.daily_recovery_state import read_checkpoint, replace_checkpoint
import math

LEDGER_KEY = 'short_swings_published_signals'


def load_published_signals(client):
    row = read_checkpoint(client, LEDGER_KEY)
    return list(((row or {}).get('payload') or {}).get('signals', {}).values())


def record_published_signal(client, trade, evidence):
    """First publication fixes the signal date/reference; retries cannot rewrite it."""
    date = trade.get('signal_date')
    symbol = trade.get('symbol')
    reference = trade.get('reference_close') or trade.get('entry_price')
    if not date or not symbol or not reference or not math.isfinite(float(reference)) or float(reference) <= 0:
        raise ValueError('Published entry needs symbol, signal date and reference close')
    identity = f'{symbol}_{date}'
    signal = {'signal_id': identity, 'symbol': symbol, 'signal_date': date,
              'reference_close': float(reference), 'trigger_type': trade.get('trigger_type'),
              'publication_evidence': evidence}
    if trade.get('entry_kind') == 'intraday_observed' or trade.get('entry_mode') == 'intraday':
        from datetime import datetime
        observed = datetime.fromisoformat(str(trade.get('observed_at') or '').replace('Z', '+00:00'))
        if observed.tzinfo is None or not trade.get('entry_date') or not math.isfinite(float(trade.get('entry_price') or 0)) or float(trade.get('entry_price') or 0) <= 0:
            raise ValueError('Observed publication requires dated price and timezone-aware observation')
        from zoneinfo import ZoneInfo
        if observed.astimezone(ZoneInfo('Africa/Cairo')).date().isoformat() != trade['entry_date']:
            raise ValueError('Observed publication must match its Cairo entry session')
        signal.update(entry_kind='intraday_observed', entry_mode='intraday', entry_date=trade['entry_date'],
                      entry_price=float(trade['entry_price']), reference_close=float(trade['entry_price']), observed_at=observed.isoformat())
    for _ in range(2):
        old = read_checkpoint(client, LEDGER_KEY)
        signals = dict(((old or {}).get('payload') or {}).get('signals', {}))
        if identity in signals:
            return signals[identity]
        signals[identity] = signal
        if replace_checkpoint(client, LEDGER_KEY, {'signals': signals}, old):
            return signal
    raise RuntimeError('Cannot persist published entry intent')
