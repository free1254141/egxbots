"""Resume the canonical daily runner without repeating confirmed operations."""
from api.daily_job_outcome import effective_daily_steps, executed_recovery_stages, is_withheld_recovery
from api.price_sync_policy import price_sync_usable

PRICE_DEPENDENTS = {'calculate_indicators', 'ml_scores_update', 'precompute_heatmap',
                    'update_positions', 'evaluate_recommendations', 'generate_recommendations',
                    'short_swings_daily', 'historical_similarity', 'accumulation_scan',
                    'cache_revalidation', 'daily_market_outlook', 'daily_social_reports'}
INDICATOR_DEPENDENTS = PRICE_DEPENDENTS - {'calculate_indicators', 'update_positions'}


def stage_decision(steps, name):
    latest = {s['step']: s for s in effective_daily_steps(steps)}
    previous = latest.get(name, {})
    if previous.get('status') in {'success', 'skipped'}:
        return 'done', 'Confirmed operation retained'
    if name == 'sync_prices' and price_sync_usable(previous):
        return 'done', 'Usable full-universe price coverage retained'
    if name in executed_recovery_stages(steps):
        return 'exhausted', 'An actual or ambiguous recovery attempt is already recorded'
    if previous.get('continuation_attempt') and not is_withheld_recovery(previous):
        return 'exhausted', 'An actual or ambiguous continuation attempt is already recorded'
    if name in PRICE_DEPENDENTS and not price_sync_usable(latest.get('sync_prices')):
        return 'blocked', 'Price sync incomplete; dependent recovery withheld'
    if name in INDICATOR_DEPENDENTS and latest.get('calculate_indicators', {}).get('status') != 'success':
        return 'blocked', 'Indicators incomplete; dependent recovery withheld'
    return 'execute', 'Operation was never executed'


def interrupted_job(job, steps, phase):
    # Ordinary completed jobs retain the existing bounded stage-repair path.
    terminal = 'short_swings_daily' if phase == 'midday' else 'daily_social_reports'
    ordinary = [s for s in steps if not s.get('recovery_attempt') and not s.get('continuation_attempt')]
    return job.get('status') == 'failed' and not any(
        s.get('step') == terminal and s.get('status') in {'success', 'failed', 'skipped'} for s in ordinary)
