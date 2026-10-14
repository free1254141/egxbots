"""Shared entry-only EGX liquidity policy; never invent fills or close holdings."""
from datetime import date, timedelta
from math import isfinite
from statistics import median
from api.egx_trading_calendar import is_egx_session

POLICY_VERSION = 'egx-entry-liquidity-v1'
EFFECTIVE_DATE = '2026-10-14'
LOOKBACK_SESSIONS = 20
MIN_ACTIVE_SESSIONS = 15
MIN_AVERAGE_TURNOVER = 1_000_000
MIN_MEDIAN_TURNOVER = 500_000
MIN_CURRENT_TURNOVER = 250_000


def recent_sessions(session):
    day = date.fromisoformat(str(session)[:10])
    sessions = []
    while len(sessions) < LOOKBACK_SESSIONS:
        if is_egx_session(day):
            sessions.append(day.isoformat())
        day -= timedelta(days=1)
    return sessions


def assess_entry_liquidity(rows, session):
    """Twenty exchange sessions, not twenty irregular bars or a volume spike."""
    sessions = recent_sessions(session)
    by_date = {}
    for row in rows:
        day = str(row.get('date') or '')[:10]
        if day not in sessions:
            continue
        try:
            close, volume = float(row['close']), float(row['volume'])
            if not isfinite(close) or not isfinite(volume) or close <= 0 or volume < 0:
                continue
            turnover = close * volume
            if not isfinite(turnover):
                continue
            by_date[day] = turnover
        except (KeyError, TypeError, ValueError):
            continue
    # Missing sessions have zero observed turnover and cannot inflate liquidity.
    values = [by_date.get(day, 0) for day in sessions]
    active = sum(value > 0 for value in values)
    average, typical, current = sum(values) / LOOKBACK_SESSIONS, median(values), values[0]
    reason = ('missing_current_session' if sessions[0] not in by_date else
              'low_current_turnover' if current < MIN_CURRENT_TURNOVER else
              'infrequent_trading' if active < MIN_ACTIVE_SESSIONS else
              'low_average_turnover' if average < MIN_AVERAGE_TURNOVER else
              'low_typical_turnover' if typical < MIN_MEDIAN_TURNOVER else 'eligible')
    return {'eligible': reason == 'eligible', 'reason': reason, 'version': POLICY_VERSION,
            'sessions': LOOKBACK_SESSIONS, 'active_sessions': active,
            'average_turnover': round(average, 2), 'median_turnover': round(typical, 2),
            'current_turnover': round(current, 2)}


def candidate_liquidity(client, symbols, session):
    """Bounded current-window reads, reused across the candidate batch."""
    symbols = list(dict.fromkeys(symbols))[:200]
    sessions = recent_sessions(session)
    history = {symbol: [] for symbol in symbols}
    for offset in range(0, len(symbols), 20):
        chunk = symbols[offset:offset + 20]
        rows = (client.table('stock_prices').select('symbol,date,close,volume')
                .eq('exchange', 'EGX').in_('symbol', chunk).in_('date', sessions)
                .limit(len(chunk) * LOOKBACK_SESSIONS).execute()).data or []
        for row in rows:
            if row.get('symbol') in history:
                history[row['symbol']].append(row)
    return {symbol: assess_entry_liquidity(rows, session) for symbol, rows in history.items()}
