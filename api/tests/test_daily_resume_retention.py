import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_continuation_withheld_audit_preserves_success_when_prices_missing():
    from api.daily_job_outcome import effective_daily_steps, summarise_daily_steps
    from api.daily_continuation import stage_decision
    rows = [
        {'step': 'sync_prices', 'status': 'failed', 'details': 'No prices'},
        {'step': 'calculate_indicators', 'status': 'success', 'count': 284},
        {'step': 'calculate_indicators', 'status': 'blocked', 'continuation_attempt': 1,
         'execution_started': False, 'details': 'Price sync incomplete; dependent recovery withheld'},
    ]
    latest = {row['step']: row for row in effective_daily_steps(rows)}
    assert latest['calculate_indicators']['status'] == 'success'
    assert stage_decision(rows, 'calculate_indicators')[0] == 'done'
    assert summarise_daily_steps(rows)['failed_steps'] == ['sync_prices']


def test_resume_does_not_replace_successful_stages_with_calendar_skips(monkeypatch):
    from api import daily_bot_run as bot
    import api.stock_ai as stock
    stages = ('sync_inventory', 'quarterly_fundamentals', 'critical_recommendation_prices',
              'calculate_indicators', 'ml_scores_update', 'news_sentiment', 'corporate_actions',
              'precompute_heatmap', 'update_positions', 'evaluate_recommendations',
              'recommendation_telegram_retries', 'refresh_market_status_for_gate',
              'generate_recommendations', 'short_swings_daily', 'historical_similarity',
              'weekly_performance_report', 'refresh_market_status', 'accumulation_scan',
              'cache_revalidation', 'daily_market_outlook', 'daily_social_reports')
    original = [{'step': name, 'status': 'success', 'count': 1} for name in stages]
    original.append({'step': 'sync_prices', 'status': 'failed', 'continuation_attempt': 1,
                     'details': 'No current prices'})
    job = {'id': 'retention', 'job_type': 'daily_bot', 'status': 'failed',
           'started_at': datetime.now(timezone.utc).isoformat(), 'total_symbols': 1,
           'steps': json.dumps(original)}

    class Query:
        def __init__(self): self.payload = None
        def select(self, *args): return self
        def eq(self, *args): return self
        def limit(self, *args): return self
        def upsert(self, payload): self.payload = payload; return self
        def execute(self):
            if self.payload: job.update(self.payload)
            return SimpleNamespace(data=[dict(job)])

    client = SimpleNamespace(table=lambda _: Query())
    monkeypatch.setattr(bot, '_init_supabase', lambda: None)
    monkeypatch.setattr(bot, 'supabase', client)
    monkeypatch.setattr(stock, 'supabase', client)
    monkeypatch.setattr(bot, '_should_run_weekly_inventory', lambda _: False)
    monkeypatch.setattr(bot, '_should_send_weekly_report', lambda _: False)
    sync = Mock(side_effect=AssertionError('Must not sync during exhausted resume'))
    monkeypatch.setattr(bot, 'get_smart_sync', sync)
    short = Mock(side_effect=AssertionError('Confirmed short lifecycle must not repeat'))
    monkeypatch.setattr('api.short_swings_daily.run_daily_short_swings', short)
    asyncio.run(bot.run_daily_job(skip_sync=True, trigger='manual', resume_job_id=job['id']))
    assert json.loads(job['steps']) == original
    sync.assert_not_called()
    short.assert_not_called()


@pytest.mark.parametrize('response', [None, SimpleNamespace(data=None), SimpleNamespace(data=[]), SimpleNamespace(data={'payload': []})])
def test_country_summary_empty_response_falls_back_without_none_data_warning(monkeypatch, capsys, response):
    import api.symbols_local as symbols
    import api.stock_ai as stock
    query = Mock()
    query.table.return_value = query
    query.select.return_value = query
    query.eq.return_value = query
    query.maybe_single.return_value = query
    query.execute.return_value = response
    monkeypatch.setattr(stock, '_init_supabase', lambda: None)
    monkeypatch.setattr(stock, 'supabase', query)
    monkeypatch.setattr(symbols, '_find_latest_file', lambda _: 'fixture.json')
    monkeypatch.setattr(symbols, '_safe_read_json', lambda _: {'Egypt': {'TotalSymbols': 284}})
    symbols.load_country_summary.cache_clear()
    try:
        assert symbols.load_country_summary() == {'Egypt': {'TotalSymbols': 284}}
        assert 'Failed to load country_summary' not in capsys.readouterr().out
    finally:
        symbols.load_country_summary.cache_clear()
