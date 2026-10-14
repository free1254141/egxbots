import asyncio
import json
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from api.tests.test_daily_continuation import incident


def test_real_runner_completes_missing_close_stages_without_replaying_prices(monkeypatch):
    from api import daily_bot_run as bot
    import api.stock_ai as stock
    job={'id':'interrupted-test','job_type':'daily_bot','status':'failed',
         'started_at':datetime.now(timezone.utc).isoformat(),'total_symbols':0,
         'steps':json.dumps(incident()+[{'step':'sync_inventory','status':'skipped'},
                                      {'step':'quarterly_fundamentals','status':'skipped'}])}
    class Query:
        def __init__(self): self.payload=None
        def select(self,*args,**kwargs): return self
        def eq(self,*args): return self
        def limit(self,*args): return self
        def upsert(self,row): self.payload=row; return self
        def execute(self):
            if self.payload: job.update(self.payload)
            return SimpleNamespace(data=[dict(job)])
    client=SimpleNamespace(table=lambda _:Query())
    monkeypatch.setattr(stock,'_init_supabase',lambda:None)
    monkeypatch.setattr(bot,'_init_supabase',lambda:None)
    monkeypatch.setattr(stock,'supabase',client)
    monkeypatch.setattr(bot,'supabase',client)
    monkeypatch.setattr(bot,'_fetch_egx_symbols',lambda:['COMI'])
    monkeypatch.setattr(bot,'_filter_active_symbols',lambda rows:rows)
    monkeypatch.setattr(bot,'_should_run_weekly_inventory',lambda _:False)
    monkeypatch.setattr(bot,'_should_send_weekly_report',lambda _:False)
    monkeypatch.setattr(stock,'_get_exchange_bulk_data',lambda *args,**kwargs:{'COMI':None})
    monkeypatch.setattr(bot,'calculate_indicators_for_symbol',lambda *args:[])
    monkeypatch.setattr(bot,'_batch_upsert_indicators',lambda *args,**kwargs:None)
    for name in ('update_market_heatmap','_refresh_market_status_cache'):
        monkeypatch.setattr(bot,name,lambda:(True,'updated'))
    monkeypatch.setattr(bot,'update_open_portfolio_positions',lambda:None)
    evaluator=Mock(return_value=dict(total=1,evaluated=1,updated=0,closed=0,adjusted=0,unchanged=1,blocked=0,errors=0,blocked_symbols=[]))
    monkeypatch.setattr(bot,'evaluate_old_recommendations',evaluator)
    monkeypatch.setattr(bot,'retry_pending_recommendation_telegram_events',lambda **kwargs:0)
    monkeypatch.setattr(bot,'should_reject_new_buys',lambda:{'blocked':True,'reason':'Test market gate'})
    monkeypatch.setattr(bot,'_mark_daily_cache_payload',lambda *args:None)
    monkeypatch.setattr(bot,'_send_daily_market_outlook',lambda *args:True)
    prices=Mock(side_effect=AssertionError('Usable exchange prices must not be replayed'))
    monkeypatch.setattr(bot,'get_smart_sync',prices)
    monkeypatch.setattr('api.update_ml_scores.update_all_scores',lambda **kwargs:None)
    monkeypatch.setattr('api.news_sentiment_engine.process_exchange_news',lambda *args,**kwargs:(True,1))
    monkeypatch.setattr('api.corporate_actions_engine.process_exchange_corporate_actions',lambda *args,**kwargs:(True,1))
    monkeypatch.setattr('api.short_swings_daily.run_daily_short_swings',lambda **kwargs:{'success':True,'message':'done','count':1})
    monkeypatch.setattr('api.historical_similarity.run_market_wide_similarity_scan',lambda **kwargs:[])
    monkeypatch.setattr('api.hf_history_cache.should_rebase_snapshot',lambda *args,**kwargs:False)
    monkeypatch.setitem(sys.modules,'accumulation_scanner',SimpleNamespace(
        get_supabase=lambda:client, fetch_all_symbols=lambda _:[],fetch_recent_technicals=lambda *args:{},
        analyze_symbol=lambda _:None,upsert_results=lambda *args:0))
    monkeypatch.setattr('api.cache_invalidation.invalidate_daily_cache',lambda *args:{'invalidated':['daily-market-data']})
    reports=Mock(return_value={'reports':{name:{'status':'ready'} for name in ('stock','accumulation','market','follow_up')}})
    monkeypatch.setattr('api.daily_social_reports.generate_daily_social_reports',reports)
    lane=SimpleNamespace(finish=lambda:{'COMI':{'verified':True,'fetched':True}},unverified_symbols=[])
    monkeypatch.setattr('api.recommendation_freshness.CriticalPriceLane',lambda *args:lane)
    result=asyncio.run(bot.run_daily_job(trigger='scheduled',phase='close',resume_job_id=job['id']))
    assert result['status']=='completed' and job['status']=='completed'
    assert result['job_run_id']=='interrupted-test' and job['total_symbols']==284
    rows=json.loads(job['steps']); latest={s['step']:s for s in rows}
    for name in ('calculate_indicators','ml_scores_update','news_sentiment','corporate_actions',
                 'precompute_heatmap','update_positions','evaluate_recommendations',
                 'recommendation_telegram_retries','refresh_market_status_for_gate','short_swings_daily',
                 'historical_similarity','refresh_market_status','accumulation_scan',
                 'cache_revalidation','daily_market_outlook','daily_social_reports'):
        assert latest[name]['status']=='success', (name,latest[name])
    assert latest['generate_recommendations']['status']=='skipped'
    reports.assert_called_once(); prices.assert_not_called()
    # A parallel repair that finished before evaluation must not evaluate the
    # same unchanged recommendation again and inflate the aggregate count.
    evaluator.assert_called_once()
    assert 'evaluate_recommendations_late' not in latest
