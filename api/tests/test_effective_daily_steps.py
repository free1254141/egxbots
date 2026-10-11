from api.daily_job_outcome import effective_daily_steps, summarise_daily_steps
from api.daily_stage_recovery import plan_recovery
from api.cache_invalidation import select_cache_tags


def partial_job():
    return [
        {'step': 'sync_prices', 'status': 'failed', 'details': 'Synced 235/284 symbols'},
        {'step': 'calculate_indicators', 'status': 'success'},
        {'step': 'evaluate_recommendations', 'status': 'success'},
        {'step': 'generate_recommendations', 'status': 'skipped', 'details': 'Bear market'},
        {'step': 'short_swings_daily', 'status': 'success'},
        {'step': 'sync_prices', 'status': 'started', 'recovery_attempt': 1},
        {'step': 'sync_prices', 'status': 'failed', 'details': 'Recovered 1/49 prices', 'recovery_attempt': 1},
        {'step': 'calculate_indicators', 'status': 'started', 'recovery_attempt': 1},
        {'step': 'calculate_indicators', 'status': 'failed', 'details': 'Price sync incomplete; dependent recovery withheld', 'recovery_attempt': 1},
    ]


def test_withheld_recovery_retains_actual_success_and_original_coverage():
    rows = partial_job()
    effective = {s['step']: s for s in effective_daily_steps(rows)}
    assert effective['sync_prices']['details'] == 'Synced 235/284 symbols'
    assert effective['calculate_indicators']['status'] == 'success'
    assert summarise_daily_steps(rows)['failed_steps'] == ['sync_prices']
    assert plan_recovery(rows, 'close') == ['sync_prices']
    assert 'daily-market-data' in select_cache_tags(rows)
    assert 'daily-short-swings' in select_cache_tags(rows)
    assert len(rows) == 9  # Audit remains intact.


def test_real_executed_failure_is_not_hidden():
    rows = partial_job() + [{'step': 'calculate_indicators', 'status': 'failed',
                            'details': 'Database write failed', 'recovery_attempt': 1}]
    assert 'calculate_indicators' in summarise_daily_steps(rows)['failed_steps']
    assert 'daily-market-data' not in select_cache_tags(rows)


def test_low_coverage_remains_blocked():
    rows = partial_job()
    rows[0]['details'] = 'Synced 100/284 symbols'
    assert select_cache_tags(rows) == []
