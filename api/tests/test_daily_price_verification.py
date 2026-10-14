from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from api import daily_price_verification as verification
from api.daily_stage_recovery import plan_recovery

SESSION = '2026-10-14'
START = datetime(2026, 10, 14, 14, tzinfo=timezone.utc)


def bar(symbol='A', **changes):
    return dict(symbol=symbol, date=SESSION, open=10, high=12, low=9,
                close=11, volume=10, updated_at='2026-10-14T14:01:00+00:00', **changes)


def result(*symbols):
    return {'success': len(symbols), 'results': {f'{s}.EGX': {'success': True, 'message': 'saved history'}
                                               for s in symbols}, 'observed_quotes': {}}


@pytest.mark.parametrize('row,reason', [
    (None, 'missing_current_session'),
    ({**bar(), 'date': '2026-10-13'}, 'missing_current_session'),
    ({**bar(), 'close': 100}, 'invalid_current_ohlc'),
    ({**bar(), 'updated_at': '2026-10-14T09:00:00+00:00'}, 'session_not_refreshed'),
    ({**bar(), 'updated_at': None}, 'refresh_timestamp_missing'),
])
def test_history_or_midday_does_not_count_as_close_success(monkeypatch, row, reason):
    monkeypatch.setattr(verification, '_read', lambda *args: {'A': row} if row else {})
    actual = verification.verify_daily_prices(None, result('A'), SESSION, START, fallback=False)
    assert actual['success'] == 0 and actual['provider_success'] == 1
    assert actual['failure_details']['A.EGX']['reason'] == reason


def test_current_readback_repairs_with_one_alternate_and_no_symbol_swap(monkeypatch):
    saved = {}
    calls = []
    monkeypatch.setattr(verification, '_read', lambda *args: dict(saved))
    def alternate(client, symbol, session):
        calls.append(symbol)
        saved[symbol] = bar(symbol)
        return 'EODHD_current_session_saved'
    monkeypatch.setattr(verification, '_eodhd_session_quote', alternate)
    actual = verification.verify_daily_prices(None, result('AUTO', 'GBCO'), SESSION, START)
    assert sorted(calls) == ['AUTO', 'GBCO']
    assert actual['success'] == 2 and actual['failure_details'] == {}
    assert actual['coverage']['session'] == SESSION


def test_no_bar_is_visible_and_not_retried_again_in_same_phase(monkeypatch):
    monkeypatch.setattr(verification, '_read', lambda *args: {})
    monkeypatch.setattr(verification, '_eodhd_session_quote', lambda *args: 'EODHD_missing_current_session')
    actual = verification.verify_daily_prices(None, result('EPPK'), SESSION, START)
    assert actual['success'] == 0
    assert not actual['failure_details']['EPPK.EGX']['retryable']
    assert 'sync_prices' not in plan_recovery([{'step': 'sync_prices', 'status': 'failed',
                                              'details': 'Synced 0/1 symbols',
                                              'failure_details': actual['failure_details']}], 'close')


def test_transport_failure_can_use_existing_one_time_recovery(monkeypatch):
    monkeypatch.setattr(verification, '_read', lambda *args: {})
    monkeypatch.setattr(verification, '_eodhd_session_quote', lambda *args: 'EODHD_HTTP_503')
    actual = verification.verify_daily_prices(None, result('A'), SESSION, START)
    assert actual['failure_details']['A.EGX']['retryable']


def test_alternate_write_success_still_requires_valid_readback(monkeypatch):
    monkeypatch.setattr(verification, '_read', lambda *args: {})
    monkeypatch.setattr(verification, '_eodhd_session_quote', lambda *args: 'EODHD_current_session_saved')
    actual = verification.verify_daily_prices(None, result('A'), SESSION, START)
    assert actual['success'] == 0


def test_failure_removes_observed_entry_quote(monkeypatch):
    monkeypatch.setattr(verification, '_read', lambda *args: {})
    data = result('A'); data['observed_quotes'] = {'A': {'price': 11}}
    assert verification.verify_daily_prices(None, data, SESSION, START, fallback=False)['observed_quotes'] == {}


def test_flat_no_trade_quote_can_be_stored_but_not_fabricated(monkeypatch):
    row = {**bar(), 'open': 11, 'high': 11, 'low': 11, 'volume': 0}
    monkeypatch.setattr(verification, '_read', lambda *args: {'A': row})
    assert verification.verify_daily_prices(None, result('A'), SESSION, START)['success'] == 1


def test_read_is_projected_batched_and_bounded():
    requests = []
    class Query:
        def select(self, projection):
            assert projection == 'symbol,date,open,high,low,close,volume,updated_at'
            return self
        def eq(self, key, value): return self
        def in_(self, key, symbols): self.symbols = symbols; return self
        def limit(self, count): assert count <= 100; return self
        def execute(self): requests.append(self.symbols); return SimpleNamespace(data=[])
    verification._read(SimpleNamespace(table=lambda _: Query()), [str(i) for i in range(275)], SESSION)
    assert [len(batch) for batch in requests] == [100, 100, 75]


def test_fallback_cap_and_no_nested_recovery(monkeypatch):
    monkeypatch.setattr(verification, '_read', lambda *args: {})
    calls = []
    monkeypatch.setattr(verification, '_eodhd_session_quote',
                        lambda client, symbol, session: calls.append(symbol) or 'EODHD_missing_current_session')
    actual = verification.verify_daily_prices(None, result(*(str(i) for i in range(100))), SESSION, START)
    assert len(calls) == 80 and actual['success'] == 0
    verification.verify_daily_prices(None, result('A'), SESSION, START, fallback=False)
    assert len(calls) == 80


def test_actual_price_writer_advances_refresh_time_and_rejects_invalid_bars():
    # Execute the real writer with only its database dependency replaced.
    # Importing stock_ai would load trained models and network initializers.
    import ast
    import datetime as dt
    import math
    from pathlib import Path
    import pandas as pd
    tree = ast.parse(Path('api/stock_ai.py').read_text(encoding='utf-8'))
    writer = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'sync_df_to_supabase')
    written = []
    class Query:
        def upsert(self, rows, **kwargs): written.extend(rows); return self
        def execute(self): return SimpleNamespace(data=[])
    def finite(value):
        number = float(value)
        return number if math.isfinite(number) else None
    scope = {'pd': pd, 'dt': dt, '_finite_float': finite, '_init_supabase': lambda: None,
             'supabase': SimpleNamespace(table=lambda name: Query())}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[writer], type_ignores=[])), '<actual-price-writer>', 'exec'), scope)
    frame = pd.DataFrame([
        {'date': SESSION, 'open': 10, 'high': 12, 'low': 9, 'close': 11, 'volume': 10},
        {'date': '2026-10-13', 'open': 10, 'high': 12, 'low': 9, 'close': 100, 'volume': 10},
    ])
    assert scope['sync_df_to_supabase']('COMI.EGX', frame)[0]
    assert len(written) == 1
    first = written[0]['updated_at']
    assert datetime.fromisoformat(first).tzinfo is not None
    assert scope['sync_df_to_supabase']('COMI.EGX', frame)[0]
    assert datetime.fromisoformat(written[-1]['updated_at']) >= datetime.fromisoformat(first)
