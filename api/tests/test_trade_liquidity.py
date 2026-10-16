from types import SimpleNamespace
from datetime import date, timedelta
import sys
import pandas as pd
import pytest
from api.trade_liquidity import assess_entry_liquidity, recent_sessions, candidate_liquidity

SESSION = '2026-10-14'


def history(turnover=2_000_000):
    return [{'symbol': 'TEST', 'date': day, 'close': 10, 'volume': turnover / 10}
            for day in recent_sessions(SESSION)]


def test_regular_liquid_stock_passes_with_dated_metrics():
    result = assess_entry_liquidity(history(), SESSION)
    assert result['eligible'] and result['active_sessions'] == 20
    assert result['average_turnover'] == result['median_turnover'] == 2_000_000


@pytest.mark.parametrize('change,reason', [
    ('low_current', 'low_current_turnover'), ('sparse', 'infrequent_trading'),
    ('low_average', 'low_average_turnover'), ('one_spike', 'low_typical_turnover'),
    ('missing_current', 'missing_current_session'), ('invalid_current', 'missing_current_session'),
])
def test_low_or_unverifiable_liquidity_never_grants_entry(change, reason):
    rows = history()
    if change == 'low_current': rows[0]['volume'] = 2554
    if change == 'sparse': rows = rows[:14]
    if change == 'low_average':
        for row in rows: row['volume'] = 60_000
    if change == 'one_spike':
        for row in rows: row['volume'] = 1
        rows[0]['volume'] = 20_000_000
    if change == 'missing_current': rows = rows[1:]
    if change == 'invalid_current': rows[0]['volume'] = float('inf')
    result = assess_entry_liquidity(rows, SESSION)
    assert not result['eligible'] and result['reason'] == reason


def test_old_bars_and_duplicate_rows_cannot_inflate_activity():
    rows = history()[:3] * 10 + [{'date': '2026-07-01', 'close': 10, 'volume': 1_000_000}]
    result = assess_entry_liquidity(rows, SESSION)
    assert not result['eligible'] and result['active_sessions'] == 3


def test_batch_read_has_explicit_columns_calendar_filter_and_limit():
    operations = []
    class Query:
        def __getattr__(self, name):
            if name == 'execute': return lambda: SimpleNamespace(data=history())
            return lambda *args: operations.append((name, args)) or self
    client = SimpleNamespace(table=lambda _: Query())
    assert candidate_liquidity(client, ['TEST'], SESSION)['TEST']['eligible']
    assert ('select', ('symbol,date,close,volume',)) in operations
    assert ('limit', (20,)) in operations
    assert any(name == 'in_' and args[0] == 'date' for name, args in operations)


@pytest.mark.parametrize('thin', [True, False])
def test_short_engine_blocks_thin_published_pending_entry_without_rewriting_history(monkeypatch, tmp_path, thin):
    from api import short_swings_engine as engine
    sessions = []
    day = date.fromisoformat(SESSION)
    from api.egx_trading_calendar import is_egx_session
    while len(sessions) < 90:
        if is_egx_session(day): sessions.append(day.isoformat())
        day -= timedelta(days=1)
    sessions.reverse()
    rows = []
    for i, day in enumerate(sessions):
        close = 100 + i * 0.3
        rows.append({'symbol': 'TEST', 'exchange': 'EGX', 'date': day, 'open': close,
                     'high': close + 0.2, 'low': close - 0.2, 'close': close, 'volume': 100000})
    if thin: rows[-1]['volume'] = 1
    class Query:
        def __getattr__(self, name):
            if name == 'execute': return lambda: SimpleNamespace(data=[])
            return lambda *args, **kwargs: self
    monkeypatch.setitem(sys.modules, 'api.stock_ai', SimpleNamespace(_init_supabase=lambda: None,
                        supabase=SimpleNamespace(table=lambda _: Query())))
    monkeypatch.setattr('api.hf_history_cache.load_history_snapshot', lambda _: pd.DataFrame(rows))
    from zoneinfo import ZoneInfo
    import datetime as dt_mod
    session_dt = dt_mod.datetime.fromisoformat(SESSION).replace(hour=17, tzinfo=ZoneInfo('Africa/Cairo'))
    class Clock(dt_mod.datetime):
        @classmethod
        def now(cls, tz=None): return session_dt.astimezone(tz or dt_mod.timezone.utc)
    monkeypatch.setattr(engine, 'dt', SimpleNamespace(datetime=Clock, date=dt_mod.date, timezone=dt_mod.timezone, timedelta=dt_mod.timedelta))
    monkeypatch.setattr(engine, 'load_stock_metadata', lambda: {})
    monkeypatch.setattr(engine, 'CACHE_PATHS', [tmp_path / 'cache.json'])
    monkeypatch.setattr(engine, '_load_published_signals', lambda _: [
        {'symbol': 'TEST', 'signal_date': SESSION, 'reference_close': rows[-1]['close']}])
    result = engine.compute_short_swings(phase='close')
    pending = [r for r in result['active_trades'] if r['is_pending_entry']]
    assert bool(pending) is not thin
