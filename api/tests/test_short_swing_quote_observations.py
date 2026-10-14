from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from api.tradingview_integration import _emit_observed_quote
from api.smart_sync import SmartSync


def test_quote_observation_requires_actual_current_positive_bar():
    today = datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    collected = []
    frame = pd.DataFrame([{'ts': today, 'close': 12.5, 'volume': 400}])
    _emit_observed_quote(frame, today, collected.append, 'fixture')
    assert len(collected) == 1
    assert collected[0]['price'] == 12.5
    assert collected[0]['verified'] is True
    assert datetime.fromisoformat(collected[0]['observed_at']).tzinfo is not None
    for value in (0, -10, float('nan')):
        _emit_observed_quote(frame.assign(volume=value), today, collected.append, 'fixture')
    yesterday = (datetime.now(ZoneInfo('Africa/Cairo')).date() - timedelta(days=1)).isoformat()
    _emit_observed_quote(frame, yesterday, collected.append, 'fixture')
    _emit_observed_quote(frame.assign(ts=yesterday), today, collected.append, 'fixture')
    _emit_observed_quote(frame.assign(close=float('inf')), today, collected.append, 'fixture')
    assert len(collected) == 1


def test_failed_sync_cannot_publish_collected_quote(monkeypatch):
    syncer = SmartSync(throttle_delay=0)
    def sync(symbol, **kwargs):
        kwargs['on_observed_quote']({'price': 15, 'verified': True})
        return symbol != 'BAD.EGX', 'fixture'
    monkeypatch.setattr(syncer, 'sync_symbol_prices', sync)
    result = syncer.sync_exchange_prices('EGX', ['GOOD.EGX', 'BAD.EGX'], refresh_latest=True)
    assert result['observed_quotes'] == {'GOOD': {'price': 15, 'verified': True}}


def test_retained_history_does_not_become_new_observation(monkeypatch):
    syncer = SmartSync(throttle_delay=0)
    def sync(symbol, **kwargs):
        assert 'on_observed_quote' not in kwargs
        return True, 'history already present'
    monkeypatch.setattr(syncer, 'sync_symbol_prices', sync)
    assert syncer.sync_exchange_prices('EGX', ['A.EGX'])['observed_quotes'] == {}
