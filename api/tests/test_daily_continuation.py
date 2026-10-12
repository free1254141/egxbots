import json
from api.daily_continuation import stage_decision, interrupted_job
from api.daily_job_outcome import effective_daily_steps, executed_recovery_stages
from api.price_sync_policy import price_sync_usable


def incident():
    rows = [{'step': 'sync_prices', 'status': 'started'},
            {'step': 'sync_prices', 'status': 'started', 'recovery_attempt': 1},
            {'step': 'sync_prices', 'status': 'failed', 'details': 'Recovered 236/284 prices', 'recovery_attempt': 1}]
    for name in ('calculate_indicators', 'ml_scores_update', 'evaluate_recommendations', 'short_swings_daily'):
        rows += [{'step': name, 'status': 'started', 'recovery_attempt': 1},
                 {'step': name, 'status': 'failed', 'recovery_attempt': 1,
                  'details': 'Price sync incomplete; dependent recovery withheld'}]
    return rows


def test_actual_incident_retains_usable_prices_and_releases_only_blocked_stages():
    rows = incident()
    effective = {s['step']: s for s in effective_daily_steps(rows)}
    assert price_sync_usable(effective['sync_prices'])
    assert executed_recovery_stages(rows) == {'sync_prices'}
    assert stage_decision(rows, 'sync_prices')[0] == 'done'
    assert stage_decision(rows, 'calculate_indicators')[0] == 'execute'
    assert stage_decision(rows, 'evaluate_recommendations')[0] == 'blocked'
    rows.append({'step': 'calculate_indicators', 'status': 'success', 'continuation_attempt': 1})
    assert stage_decision(rows, 'evaluate_recommendations')[0] == 'execute'
    assert stage_decision(rows, 'update_positions')[0] == 'execute'
    assert stage_decision(rows, 'news_sentiment')[0] == 'execute'
    assert interrupted_job({'status': 'failed'}, rows, 'close')


def test_actual_failure_or_ambiguous_start_is_never_replayed():
    rows = incident() + [{'step': 'calculate_indicators', 'status': 'success'},
                        {'step': 'generate_recommendations', 'status': 'started', 'recovery_attempt': 1}]
    assert stage_decision(rows, 'generate_recommendations')[0] == 'exhausted'
    rows.append({'step': 'generate_recommendations', 'status': 'failed', 'recovery_attempt': 1,
                 'details': 'Provider response ambiguous'})
    assert stage_decision(rows, 'generate_recommendations')[0] == 'exhausted'


def test_missing_prices_remain_blocked_and_successful_reports_are_not_repeated():
    rows = [{'step': 'sync_prices', 'status': 'failed', 'details': 'Recovered 100/284 prices'}]
    assert stage_decision(rows, 'calculate_indicators')[0] == 'blocked'
    rows += [{'step': 'daily_social_reports', 'status': 'success'}]
    assert stage_decision(rows, 'daily_social_reports')[0] == 'done'
    assert not interrupted_job({'status': 'failed'}, rows, 'close')
