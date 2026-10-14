"""Resume failed daily stages once, without replaying successful stages/reports."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from api.daily_recovery_state import read_checkpoint, replace_checkpoint, utc_now, parse_timestamp
from api.daily_job_outcome import summarise_daily_steps, effective_daily_steps, executed_recovery_stages, is_withheld_recovery

_FINISHED = set()
ORDER = ('sync_prices', 'calculate_indicators', 'ml_scores_update', 'precompute_heatmap',
         'refresh_market_status_for_gate', 'update_positions', 'evaluate_recommendations',
         'generate_recommendations', 'short_swings_daily')
MIDDAY = set(ORDER) - {'update_positions', 'evaluate_recommendations', 'generate_recommendations'}

# Short-swings can safely operate on the usable subset when a provider leaves
# a few symbols without prices. It still requires a successful indicator pass;
# gating it on an all-symbol price sync made valid intraday recommendations
# disappear whenever a small provider subset failed.
REQUIRES_PRICES = {'calculate_indicators', 'ml_scores_update', 'precompute_heatmap',
                   'refresh_market_status_for_gate', 'update_positions',
                   'evaluate_recommendations', 'generate_recommendations'}
REQUIRES_INDICATORS = {'ml_scores_update', 'precompute_heatmap', 'short_swings_daily',
                       'evaluate_recommendations', 'generate_recommendations'}


def clear_egx_candle_cache():
    import sys
    router = sys.modules.get('api.routers.bot')
    cache = getattr(router, 'candle_cache', {})
    for key in list(cache):
        if len(key) >= 4 and str(key[3]).upper() == 'EGX':
            cache.pop(key, None)


def plan_recovery(steps, phase):
    latest = {s['step']: s for s in effective_daily_steps(steps)}
    allowed = MIDDAY if phase == 'midday' else set(ORDER)
    failed = {name for name, s in latest.items()
              if s.get('status') in {'failed', 'started'} and name in allowed}
    price_failures = latest.get('sync_prices', {}).get('failure_details')
    if isinstance(price_failures, dict) and price_failures and not any(
            failure.get('retryable', True) for failure in price_failures.values()):
        failed.discard('sync_prices')  # Both sources exhausted for this phase.
    # Refresh derived data after repairing incomplete prices; otherwise old
    # indicators can be tagged as fresh alongside the repaired price snapshot.
    from api.price_sync_policy import price_sync_usable
    # A small provider gap leaves dependents valid; only cascade when prices
    # were unusable, otherwise successful stages would be falsely re-failed.
    if 'sync_prices' in failed and not price_sync_usable(latest.get('sync_prices')):
        failed.update({'calculate_indicators', 'ml_scores_update', 'precompute_heatmap',
                       'refresh_market_status_for_gate', 'short_swings_daily'} & allowed)
        if phase == 'close':
            failed.add('evaluate_recommendations')
    if 'calculate_indicators' in failed:
        failed.update({'ml_scores_update', 'precompute_heatmap', 'short_swings_daily'} & allowed)
        if phase == 'close':
            failed.update({'evaluate_recommendations', 'generate_recommendations'} & allowed)
    return [name for name in ORDER if name in failed]


def execute_stage(name, phase, job_id, previous):
    """Reuse production operations; each runner is an offline-mockable boundary."""
    from api import daily_bot_run as bot
    if name == 'sync_prices':
        symbols = bot._filter_active_symbols(bot._fetch_egx_symbols())
        selected = previous.get('failed_symbols') or [f'{s}.EGX' for s in symbols]
        failures = previous.get('failure_details')
        if isinstance(failures, dict):
            selected = [symbol for symbol in selected if failures.get(symbol, {}).get('retryable', True)]
        if not selected:
            return {'success': False, 'count': 0,
                    'details': 'Recovery withheld: alternate source confirmed no current bar; revisit next phase',
                    'execution_started': False, 'withheld': True,
                    'failed_symbols': previous.get('failed_symbols', [])}
        verification_start = datetime.now(timezone.utc)
        result = bot.get_smart_sync().sync_exchange_prices('EGX', selected, max_days=365, refresh_latest=True)
        from api.daily_price_verification import verify_daily_prices
        from api.recommendation_freshness import expected_session
        # The original stage already tried EODHD; don't repeat alternate calls.
        result = verify_daily_prices(bot.supabase, result, expected_session(), verification_start, fallback=False)
        bot.stock_ai.clear_exchange_bulk_cache('EGX')
        clear_egx_candle_cache()
        failed = [sym for sym, res in result.get('results', {}).items() if not res.get('success')]
        return {'success': bool(selected) and result.get('success') == len(selected),
                'count': result.get('success', 0), 'details': f"Recovered {result.get('success',0)}/{len(selected)} prices",
                'failed_symbols': failed, 'failure_details': result.get('failure_details', {})}
    if name == 'calculate_indicators':
        from concurrent.futures import ThreadPoolExecutor
        symbols = bot._filter_active_symbols(bot._fetch_egx_symbols())
        bulk = bot.stock_ai._get_exchange_bulk_data('EGX', bypass_min_limit=True, cache_ttl_seconds=7200)
        failures, rows = [], []
        def calculate(symbol):
            try:
                return bot.calculate_indicators_for_symbol(symbol, 'EGX', bulk.get(symbol.upper())), None
            except Exception as error:
                return [], str(error)
        with ThreadPoolExecutor(max_workers=15) as pool:
            for symbol, (records, error) in zip(symbols, pool.map(calculate, symbols)):
                if error: failures.append(symbol)
                rows.extend(records)
        if rows: bot._batch_upsert_indicators(rows, batch_size=200)
        return {'success': bool(symbols) and not failures, 'count': len(symbols)-len(failures),
                'details': f'{len(rows)} indicator records; {len(failures)} failures'}
    if name == 'ml_scores_update':
        from api.update_ml_scores import update_all_scores
        update_all_scores(bulk_cache_ttl_seconds=7200)
        return {'success': True, 'details': 'Updated ML scores', 'count': 0}
    elif name == 'precompute_heatmap':
        ok, message = bot.update_market_heatmap()
        return {'success': ok, 'details': message, 'count': 0}
    elif name == 'refresh_market_status_for_gate':
        ok, message = bot._refresh_market_status_cache()
        return {'success': ok, 'details': message, 'count': 0}
    elif name == 'update_positions':
        bot.update_open_portfolio_positions()
        return {'success': True, 'details': 'Updated portfolio positions', 'count': 0}
    elif name == 'evaluate_recommendations':
        result = bot.evaluate_old_recommendations(return_report=True)
        return {'success': not (result['blocked'] or result['errors']),
                'details': json.dumps(result, ensure_ascii=False), 'count': result['evaluated']}
    elif name == 'generate_recommendations':
        from api.daily_job_scheduler import get_scheduler_state
        gate = bot.should_reject_new_buys()
        if gate.get('blocked'):
            return {'success': True, 'details': 'Skipped - '+str(gate.get('reason')), 'count': 0}
        count = asyncio.run(bot.generate_daily_recommendations(model_name=get_scheduler_state().get('model_filter', 'adaptive'),
                           bulk_cache_ttl_seconds=7200, run_context=gate))
        return {'success': True, 'details': f'Recovered generation: {count} recommendations', 'count': count or 0}
    elif name == 'short_swings_daily':
        from api.short_swings_daily import run_daily_short_swings
        result = run_daily_short_swings(trigger='retry', phase=phase, job_run_id=job_id)
        return {'success': result.get('success', False), 'details': result.get('message',''), 'count': result.get('count',0)}
    else:
        raise ValueError('Unsupported recovery stage')


def append_step(client, job, step):
    # Keep the completion time intact; JSONB equality creates a huge PostgREST
    # URL. Durable stage checkpoints prevent duplicate workers, and read-back
    # detects the rare concurrent audit append before one bounded retry.
    for _ in range(2):
        current = (client.table('daily_job_runs').select('steps')
                   .eq('id', job['id']).limit(1).execute())
        row = (current.data or [None])[0]
        if not row:
            raise RuntimeError('Daily recovery job disappeared')
        raw = row.get('steps')
        if raw is None:
            raw = '[]'
        steps = json.loads(raw) if isinstance(raw, str) else list(raw)
        marker = {**step, 'sequence': len(steps)+1, 'timestamp': utc_now().isoformat(), 'recovery_attempt': 1}
        steps.append(marker)
        encoded = json.dumps(steps)
        health = summarise_daily_steps(steps)
        client.table('daily_job_runs').update({'steps': encoded, 'error': health['error']}).eq('id', job['id']).execute()
        verified = (client.table('daily_job_runs').select('steps')
                    .eq('id', job['id']).limit(1).execute())
        saved = (verified.data or [None])[0]
        saved_raw = saved.get('steps') if saved else None
        saved_steps = json.loads(saved_raw) if isinstance(saved_raw, str) else saved_raw or []
        if any(isinstance(item, dict) and item.get('timestamp') == marker['timestamp'] for item in saved_steps):
            job['steps'] = json.dumps(saved_steps)
            job['error'] = health['error']
            return saved_steps
    raise RuntimeError('Daily recovery audit write lost to a concurrent update')


def retry_failed_daily_stages(now):
    """One durable attempt per failed stage/job; only the currently due phase."""
    from api.daily_job_scheduler import _due_phase
    from api import stock_ai
    phase = _due_phase(now)
    if not phase:
        return None
    stock_ai._init_supabase()
    client = stock_ai.supabase
    if not client:
        return None
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    query = (client.table('daily_job_runs').select('id,status,steps,started_at')
             .eq('job_type', 'daily_midday' if phase == 'midday' else 'daily_bot')
             .gte('started_at', start.isoformat()).lt('started_at', (start+timedelta(days=1)).isoformat())
             .order('started_at', desc=True).limit(1).execute())
    job = (query.data or [None])[0]
    if not job or job.get('status') == 'running':
        return None
    identity = f"{job['id']}:{phase}"
    if identity in _FINISHED:
        return None

    steps = json.loads(job['steps']) if isinstance(job.get('steps'), str) else job.get('steps') or []
    from api.daily_continuation import interrupted_job
    if interrupted_job(job, steps, phase):
        key = 'daily_continuation_' + job['id']
        existing = read_checkpoint(client, key)
        if existing:
            return {'phase': phase, 'continuation': 'already_claimed'}
        claim = replace_checkpoint(client, key, {'status': 'running', 'phase': phase, 'attempts': 1}, None)
        if not claim:
            return None
        from api.daily_bot_run import run_daily_job
        from api.daily_job_scheduler import get_scheduler_state
        try:
            result = asyncio.run(run_daily_job(trigger='scheduled', phase=phase,
                model_filter=get_scheduler_state().get('model_filter', 'adaptive'), resume_job_id=job['id']))
            replace_checkpoint(client, key, {'status': result.get('status', 'failed'), 'phase': phase, 'attempts': 1}, claim)
            _FINISHED.add(identity)
            return {'phase': phase, 'continuation': result}
        except Exception as error:
            replace_checkpoint(client, key, {'status': 'failed', 'phase': phase, 'attempts': 1,
                                           'error': type(error).__name__}, claim)
            raise
    planned = plan_recovery(steps, phase)
    if not planned:
        _FINISHED.add(identity)
        return None

    latest = {s.get('step'): s for s in effective_daily_steps(steps)}
    attempted_stages = executed_recovery_stages(steps)
    changed = []
    for name in planned:
        # Also survives restarts through both the job audit and durable CAS.
        if name in attempted_stages:
            continue
        key = f"daily_stage_retry_{job['id']}_{name}"
        existing = read_checkpoint(client, key)
        if existing:
            existing_payload = existing.get('payload') or {}
            # Older workers claimed a lease then failed before recording the
            # started step (JSONB/string CAS bug). No operation was executed:
            # repair that lease without spending the user's one actual retry.
            repair_audit = is_withheld_recovery(latest.get(name)) or existing_payload.get('status') == 'blocked' or existing_payload.get('status') == 'audit_failed' or (
                existing_payload.get('status') == 'failed'
                and existing_payload.get('error') == 'Stale recovery checkpoint')
            if repair_audit and name not in attempted_stages:
                claim = replace_checkpoint(client, key,
                    {'status':'running','stage':name,'phase':phase,'attempts':1,'audit_repaired':True}, existing)
                if not claim:
                    continue
            else:
                if existing_payload.get('status') == 'running':
                    comp = parse_timestamp(existing.get('computed_at'))
                    if comp and (utc_now() - comp) > timedelta(minutes=15):
                        replace_checkpoint(client, key, {**existing_payload, 'status': 'failed', 'error': 'Stale recovery checkpoint'}, existing)
                continue
        else:
            claim = replace_checkpoint(client, key, {'status': 'running', 'stage': name, 'phase': phase, 'attempts': 1}, None)
        if not claim:
            continue
        try:
            append_step(client, job, {'step': name, 'status': 'started', 'details': 'Independent one-time stage recovery'})
        except Exception:
            replace_checkpoint(client, key, {'status':'audit_failed','stage':name,'phase':phase,
                                           'attempts':0,'execution_started':False}, claim)
            raise
        # Market-data consumers must not run over a still-incomplete price sync or indicator calculation.
        from api.price_sync_policy import price_sync_usable
        if name in REQUIRES_PRICES and not price_sync_usable(latest.get('sync_prices')):
            result = {'success': False, 'details': 'Price sync incomplete; dependent recovery withheld', 'count': 0}
        elif name in REQUIRES_INDICATORS and latest.get('calculate_indicators', {}).get('status') != 'success':
            result = {'success': False, 'details': 'Indicators incomplete; dependent recovery withheld', 'count': 0}
        else:
            try:
                result = execute_stage(name, phase, job['id'], latest.get(name, {}))
            except Exception as error:
                result = {'success': False, 'details': str(error)[:400], 'count': 0}
        status = 'success' if result.get('success') else 'failed'
        append_step(client, job, {'step': name, 'status': status, **{k: v for k, v in result.items() if k != 'success'}})
        if not (name == 'sync_prices' and status != 'success') or price_sync_usable({'status': status, **result}):
            # A failed one-symbol-subset recovery must not erase the original
            # coverage figure that dependents are gated on.
            latest[name] = {'status': status, 'details': result.get('details'), 'count': result.get('count')}
        if status == 'success':
            changed.append(name)
        replace_checkpoint(client, key, {'status': status, 'attempts': 1, 'stage': name, 'phase': phase}, claim)
    if changed:
        from api.cache_invalidation import select_cache_tags, invalidate_cache_tags
        all_steps = json.loads(job['steps']) if isinstance(job['steps'], str) else job['steps']
        tags = select_cache_tags(all_steps, changed_steps=changed)
        inv_result = invalidate_cache_tags(tags)
        if inv_result.get('error'):
            print(f"[DAILY-RECOVERY] Cache invalidation failed: {inv_result['error']}")
    _FINISHED.add(identity)
    return {'phase': phase, 'recovered': changed, 'planned': planned}
