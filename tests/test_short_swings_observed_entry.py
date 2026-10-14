"""Offline observed-entry causality fixtures; isolate all snapshots/providers."""
import datetime as dt
import sys
import types
from zoneinfo import ZoneInfo
import pandas as pd
import pytest
from api import short_swings_engine as engine

NOW = dt.datetime(2026, 10, 13, 12, tzinfo=ZoneInfo('Africa/Cairo'))
QUOTE = {'verified': True, 'date': '2026-10-13', 'observed_at': NOW.isoformat(), 'price': 207, 'volume': 300000}

@pytest.mark.parametrize('patch', [{'verified':False}, {'volume':0}, {'date':'2026-10-12'}, {'observed_at':'2026-10-13T08:00:00+03:00'}, {'observed_at':'2026-10-13T12:00:00'}, {'price':float('nan')}])
def test_unverified_stale_or_nontrading_observations_are_rejected(patch):
    assert engine._verified_intraday_quote({**QUOTE, **patch}, NOW) is None

def test_closed_session_rejects_current_quote():
    assert engine._verified_intraday_quote(QUOTE, NOW.replace(hour=16)) is None

def setup_engine(monkeypatch, tmp_path, published=()):
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None): return NOW.astimezone(tz or dt.timezone.utc)
    monkeypatch.setattr(engine, 'dt', types.SimpleNamespace(datetime=Clock, date=dt.date, timezone=dt.timezone, timedelta=dt.timedelta))
    rows = [{'symbol':'TEST','exchange':'EGX','date':day,'open':100+i,'close':100+i,'high':100.5+i,'low':99.5+i,'volume':100000} for i,day in enumerate(pd.bdate_range(end='2026-10-12', periods=90))]
    rows.append({'symbol':'TEST','exchange':'EGX','date':'2026-10-13','open':190,'close':205,'high':209,'low':189,'volume':300000})
    monkeypatch.setattr('api.hf_history_cache.load_history_snapshot', lambda _: pd.DataFrame(rows))
    client = types.SimpleNamespace(table=lambda _: types.SimpleNamespace(select=lambda *_: None))
    monkeypatch.setitem(sys.modules, 'api.stock_ai', types.SimpleNamespace(_init_supabase=lambda:None, supabase=client))
    monkeypatch.setattr(engine,'_load_published_signals',lambda _:list(published))
    monkeypatch.setattr(engine,'_persist_saved_snapshot',lambda *_:True)
    monkeypatch.setattr(engine,'load_stock_metadata',lambda:{})
    monkeypatch.setattr(engine,'CACHE_PATHS',[tmp_path/'snapshot.json'])
    return rows

def test_midday_observed_entry_never_replays_prior_daily_open_or_peak(monkeypatch,tmp_path):
    setup_engine(monkeypatch,tmp_path)
    result = engine.compute_short_swings(phase='midday', observed_quotes={'TEST':QUOTE})
    trade = next(t for t in result['active_trades'] if t['symbol']=='TEST')
    assert trade['entry_price']==207 and trade['observed_at']==NOW.isoformat()
    assert trade['entry_mode']=='intraday'
    assert not trade['is_pending_entry'] and trade['max_gain_pct']==0
    assert not trade['is_breakeven_protected'] and trade['return_pct']==0 and trade['is_new_entry']

def test_midday_without_verified_observation_has_no_today_new_entry(monkeypatch,tmp_path):
    setup_engine(monkeypatch,tmp_path)
    result=engine.compute_short_swings(phase='midday')
    assert not any(t.get('entry_date')=='2026-10-13' or t.get('is_pending_entry') for t in result['active_trades'])

def test_close_preserves_published_observed_price_without_daily_high_low_replay(monkeypatch,tmp_path):
    setup_engine(monkeypatch,tmp_path,[{'symbol':'TEST','signal_date':'2026-10-13','entry_date':'2026-10-13','entry_kind':'intraday_observed','entry_price':207,'reference_close':207,'observed_at':NOW.isoformat()}])
    result=engine.compute_short_swings(phase='close')
    trade=next(t for t in result['active_trades'] if t['symbol']=='TEST')
    assert trade['entry_price']==207 and trade['observed_at']==NOW.isoformat()
    assert trade['published'] and not trade['is_new_entry'] and not trade['is_pending_entry'] and trade['max_gain_pct']==0

def test_published_observed_entry_is_immutable(monkeypatch):
    from api import short_swing_published as ledger
    state = {}
    monkeypatch.setattr(ledger, 'read_checkpoint', lambda *_: {'payload': state} if state else None)
    def save(_client, _key, payload, _old): state.update(payload); return True
    monkeypatch.setattr(ledger, 'replace_checkpoint', save)
    trade={'symbol':'TEST','signal_date':'2026-10-13','entry_date':'2026-10-13','entry_kind':'intraday_observed','entry_price':207,'reference_close':205,'observed_at':NOW.isoformat()}
    first=ledger.record_published_signal(None,trade,{'channel':'vip'})
    second=ledger.record_published_signal(None,{**trade,'entry_price':999}, {'channel':'free'})
    assert first==second and second['entry_price']==207 and second['reference_close']==207

def test_snapshot_reuse_requires_same_session_and_phase(monkeypatch):
    stub = types.ModuleType('api.daily_bot_run')
    stub._telegram_recommendation_writes_enabled=lambda:False
    monkeypatch.setitem(sys.modules,'api.daily_bot_run',stub)
    from api.short_swings_daily import _snapshot_matches
    assert _snapshot_matches({'status':'ok','as_of':'2026-10-13','phase':'midday'},'2026-10-13','midday')
    assert not _snapshot_matches({'status':'ok','as_of':'2026-10-12','phase':'midday'},'2026-10-13','midday')
    assert not _snapshot_matches({'status':'ok','as_of':'2026-10-13','phase':'close'},'2026-10-13','midday')

def test_verified_quote_alone_cannot_bypass_strategy_gate(monkeypatch,tmp_path):
    rows=setup_engine(monkeypatch,tmp_path)
    rows[-1].update(close=185,high=200,low=180)
    result=engine.compute_short_swings(phase='midday',observed_quotes={'TEST':QUOTE})
    assert not any(t.get('entry_mode')=='intraday' for t in result['active_trades'])

def test_close_retains_published_entry_when_corrected_candle_is_missing(monkeypatch,tmp_path):
    published={'symbol':'TEST','signal_date':'2026-10-13','entry_date':'2026-10-13','entry_mode':'intraday','entry_price':207,'reference_close':207,'observed_at':NOW.isoformat()}
    rows=setup_engine(monkeypatch,tmp_path,[published]); rows.pop()
    result=engine.compute_short_swings(phase='close')
    trade=next(t for t in result['active_trades'] if t['symbol']=='TEST')
    assert trade['entry_price']==207 and trade['entry_mode']=='intraday' and trade['current_price'] is None

