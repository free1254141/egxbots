import datetime
import sys
import types
from functools import partial

import pandas as pd
import pytest
import requests

from api import tradingview_integration as provider
from api import price_sync_policy as policy
from api.tests.test_price_sync_deadline import Clock, Socket


@pytest.fixture
def isolated_provider(monkeypatch):
    writes = []
    class Query:
        def __getattr__(self, _):
            return lambda *args, **kwargs: self
        def execute(self):
            return types.SimpleNamespace(data=[{'date': datetime.date.today().isoformat()}], count=500)
    monkeypatch.setitem(sys.modules, 'api.stock_ai', types.SimpleNamespace(
        _init_supabase=lambda: None, _get_thread_local_supabase=lambda: Query(),
        _last_trading_day=lambda day: day,
        sync_df_to_supabase=lambda *args, **kwargs: writes.append((args, kwargs)) or (True, 'saved'),
    ))
    monkeypatch.setattr(provider, '_yahoo_missing_until', {})
    monkeypatch.setattr(provider, '_yahoo_proxy_fail_count', 0)
    monkeypatch.setattr(provider, '_yahoo_proxy_tripped', False)
    monkeypatch.setattr(provider, '_yahoo_proxy_retry_after', 0)
    monkeypatch.setenv('TRADINGVIEW_REQUEST_DELAY', '0')
    return writes


def test_real_fetch_path_discards_deadline_partial_bars_and_uses_fallback(monkeypatch, isolated_provider):
    clock = Clock()
    socket = Socket(clock)
    clients = []
    class TvDatafeed:
        __ws_timeout = 15
        def __init__(self):
            clients.append(self)
        def __create_connection(self):
            self.ws = socket
        def get_hist(self, **kwargs):
            self.__create_connection()
            try:
                while True:
                    self.ws.recv()
            except TimeoutError:
                return pd.DataFrame({'close': [9999]})  # Swallowed error must not allow a write.
    names = ['in_1_minute', 'in_5_minute', 'in_15_minute', 'in_30_minute', 'in_1_hour', 'in_4_hour', 'in_daily']
    monkeypatch.setitem(sys.modules, 'tvDatafeed', types.SimpleNamespace(
        TvDatafeed=TvDatafeed, Interval=types.SimpleNamespace(**{name: name for name in names})))
    real_fetch = policy.fetch_tradingview_history
    monkeypatch.setattr(policy, 'fetch_tradingview_history', partial(real_fetch, clock=clock))
    fallback_calls = []
    monkeypatch.setattr(provider, '_try_yahoo_direct_fallback',
                        lambda *args: fallback_calls.append(args) or (True, 'saved dated Yahoo bars'))
    assert provider.fetch_tradingview_prices('COMI.EGX', refresh_latest=True) == (True, 'saved dated Yahoo bars')
    assert len(clients) == 1 and len(fallback_calls) == 1
    assert socket.closed and isolated_provider == []


def test_yahoo_404_is_cached_only_for_that_symbol_and_expires(monkeypatch, isolated_provider):
    now = [1000]
    monkeypatch.setattr(provider.time, 'monotonic', lambda: now[0])
    monkeypatch.delenv('CF_PROXY_URL', raising=False)
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return types.SimpleNamespace(status_code=404, text='No data found')
    monkeypatch.setattr(provider, '_get_yahoo_session', lambda: types.SimpleNamespace(get=get))
    args = ('1d', 365, None, None)
    assert not provider._try_yahoo_direct_fallback('X.EGX', 'X', *args)[0]
    assert 'cached' in provider._try_yahoo_direct_fallback('X.EGX', 'X', *args)[1]
    assert len(calls) == 1
    provider._try_yahoo_direct_fallback('Y.EGX', 'Y', *args)
    assert len(calls) == 2
    now[0] += 901
    provider._try_yahoo_direct_fallback('X.EGX', 'X', *args)
    assert len(calls) == 3 and isolated_provider == []


def test_proxy_cooldown_survives_direct_success(monkeypatch, isolated_provider):
    monkeypatch.setenv('CF_PROXY_URL', 'https://proxy.example')
    calls = []
    chart = {'chart': {'result': [{
        'timestamp': [1791806400],
        'indicators': {'quote': [{'open': [1], 'high': [2], 'low': [1], 'close': [2], 'volume': [10]}]},
    }]}}
    def get(url, **kwargs):
        calls.append(url)
        if url.startswith('https://proxy.example'):
            raise requests.exceptions.Timeout('read timed out')
        return types.SimpleNamespace(status_code=200, json=lambda: chart, raise_for_status=lambda: None)
    monkeypatch.setattr(provider, '_get_yahoo_session', lambda: types.SimpleNamespace(get=get))
    for symbol in ('A', 'B', 'C', 'D'):
        assert provider._try_yahoo_direct_fallback(f'{symbol}.EGX', symbol, '1d', 365, None, None)[0]
    assert sum(url.startswith('https://proxy.example') for url in calls) == 3
    assert provider._yahoo_proxy_tripped and len(isolated_provider) == 4


def test_daily_refresh_rejects_old_provider_bars_even_if_cloud_has_today(monkeypatch, isolated_provider):
    class TvDatafeed:
        _TvDatafeed__ws_timeout=15
    names=['in_1_minute','in_5_minute','in_15_minute','in_30_minute','in_1_hour','in_4_hour','in_daily']
    monkeypatch.setitem(sys.modules,'tvDatafeed',types.SimpleNamespace(
        TvDatafeed=TvDatafeed,Interval=types.SimpleNamespace(**{n:n for n in names})))
    previous=datetime.date.today()-datetime.timedelta(days=10)
    frame=pd.DataFrame({'open':[10],'high':[12],'low':[9],'close':[11],'volume':[10]},
                       index=pd.DatetimeIndex([str(previous)],name='datetime'))
    monkeypatch.setattr(policy,'fetch_tradingview_history',lambda *args,**kwargs:frame)
    calls=[]
    monkeypatch.setattr(provider,'_try_yahoo_direct_fallback',lambda *args:calls.append(args) or (False,'Yahoo returned no current session'))
    result=provider.fetch_tradingview_prices('COMI.EGX',refresh_latest=True)
    assert not result[0] and len(calls)==1 and isolated_provider==[]
