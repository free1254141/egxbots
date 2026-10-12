from types import SimpleNamespace
from unittest.mock import Mock
import threading
from api import recommendation_freshness as freshness


def bar(symbol='A', day='2026-10-12', volume=10):
    return dict(symbol=symbol,date=day,open=10,high=12,low=9,close=11,volume=volume)


def test_current_valid_bar_and_no_trade_are_distinguished():
    assert freshness.quote_health(bar(), '2026-10-12') == 'verified'
    assert freshness.quote_health(bar(day='2026-10-11'), '2026-10-12') == 'missing_current_session'
    assert freshness.quote_health(bar(volume=0), '2026-10-12', require_trading=True) == 'no_trading_volume'
    assert freshness.quote_health(bar(volume=0), '2026-10-12') == 'verified'
    bad = bar(); bad['close'] = 100
    assert freshness.quote_health(bad, '2026-10-12') == 'invalid_current_ohlc'


def test_new_candidates_without_current_prices_are_rejected(monkeypatch,tmp_path):
    import json
    path=tmp_path/'inventory.json'
    path.write_text(json.dumps([{'Symbol':s,'InventorySource':'EODHD'} for s in ('A','B','MISSING')]),encoding='utf-8')
    monkeypatch.setattr('api.symbols_local._find_latest_file',lambda _:str(path))
    monkeypatch.setattr(freshness, '_current_quotes', lambda *args: {'A': bar(), 'B': bar('B', volume=0)})
    q=Mock(); q.select.return_value=q; q.eq.return_value=q; q.in_.return_value=q; q.limit.return_value=q
    q.execute.return_value=SimpleNamespace(data=[])
    rows=[{'symbol':x,'date':'2026-10-12'} for x in ('A','B','MISSING')]
    accepted,rejected=freshness.eligible_candidates(SimpleNamespace(table=lambda _:q), rows,'2026-10-12')
    assert [r['symbol'] for r in accepted] == ['A']
    assert {r['reason'] for r in rejected} == {'no_trading_volume','missing_current_session'}


def test_critical_lane_runs_in_parallel_and_never_retries_provider(monkeypatch):
    q=Mock(); q.select.return_value=q; q.eq.return_value=q; q.limit.return_value=q
    q.execute.return_value=SimpleNamespace(data=[{'symbol':'A'},{'symbol':'B'}])
    client=SimpleNamespace(table=lambda _:q)
    repaired=set(); release=threading.Event(); started=threading.Event(); calls=[]
    monkeypatch.setattr(freshness,'_current_quotes',lambda _,syms,session:{s:bar(s) for s in syms if s in repaired})
    monkeypatch.setattr(freshness,'read_checkpoint',lambda *args:None)
    monkeypatch.setattr(freshness,'replace_checkpoint',lambda *args:{'payload':{}})
    def fetch(symbol,**kwargs):
        calls.append(symbol); started.set()
        assert release.wait(2)
        repaired.add(symbol.split('.')[0])
        return True,'saved'
    monkeypatch.setattr('api.tradingview_integration.fetch_tradingview_prices',fetch)
    lane=freshness.CriticalPriceLane(client,'job','2026-10-12')
    assert started.wait(1)  # Main pipeline can continue before quotes finish.
    assert len(repaired)==0
    release.set(); result=lane.finish()
    assert len(calls)==2 and all(r['verified'] for r in result.values())


def test_provider_success_with_old_bar_never_confirms_freshness(monkeypatch):
    monkeypatch.setattr(freshness,'_eodhd_session_quote',lambda *args:'EODHD_missing_current_session')
    q=Mock(); q.select.return_value=q; q.eq.return_value=q; q.limit.return_value=q
    q.execute.return_value=SimpleNamespace(data=[{'symbol':'A'}])
    monkeypatch.setattr(freshness,'_current_quotes',lambda *args:{})
    monkeypatch.setattr(freshness,'read_checkpoint',lambda *args:None)
    monkeypatch.setattr(freshness,'replace_checkpoint',lambda *args:{'payload':{}})
    calls=[]
    monkeypatch.setattr('api.tradingview_integration.fetch_tradingview_prices',lambda *args,**kwargs:calls.append(1) or (True,'saved old bars'))
    result=freshness.CriticalPriceLane(SimpleNamespace(table=lambda _:q),'job','2026-10-12').finish()
    assert len(calls)==1 and not result['A']['verified']


def test_eodhd_fallback_only_writes_a_valid_actual_current_session(monkeypatch):
    monkeypatch.setenv('EODHD_API_KEY','test-secret')
    q=Mock(); q.upsert.return_value=q
    client=SimpleNamespace(table=lambda _:q)
    response=SimpleNamespace(status_code=200,json=lambda:[bar(day='2026-10-11')])
    monkeypatch.setattr('requests.get',lambda *args,**kwargs:response)
    assert freshness._eodhd_session_quote(client,'A','2026-10-12')=='EODHD_missing_current_session'
    q.upsert.assert_not_called()
    response.json=lambda:[bar()]
    assert freshness._eodhd_session_quote(client,'A','2026-10-12')=='EODHD_current_session_saved'
    written=q.upsert.call_args[0][0]
    assert written['date']=='2026-10-12' and written['volume']==10 and written['symbol']=='A'


def test_failed_close_refresh_cannot_reuse_cached_midday_quote(monkeypatch):
    q=Mock(); q.select.return_value=q; q.eq.return_value=q; q.limit.return_value=q
    q.execute.return_value=SimpleNamespace(data=[{'symbol':'A'}])
    monkeypatch.setattr(freshness,'_current_quotes',lambda *args:{'A':bar()})
    monkeypatch.setattr(freshness,'read_checkpoint',lambda *args:None)
    monkeypatch.setattr(freshness,'replace_checkpoint',lambda *args:{'payload':{}})
    monkeypatch.setattr(freshness,'_eodhd_session_quote',lambda *args:'EODHD_missing_current_session')
    calls=[]
    monkeypatch.setattr('api.tradingview_integration.fetch_tradingview_prices',lambda *args,**kwargs:calls.append(1) or (False,'No current session bar'))
    lane=freshness.CriticalPriceLane(SimpleNamespace(table=lambda _:q),'job','2026-10-12',['A.EGX'])
    result=lane.finish()
    assert len(calls)==1 and not result['A']['verified']
    assert result['A']['reason']=='current_session_source_unconfirmed'
