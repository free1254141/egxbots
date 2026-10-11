"""Bounded continuation of reports/cache only; never replay trading stages."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from api.daily_job_outcome import effective_daily_steps, social_reports_outcome
from api.daily_recovery_state import read_checkpoint, replace_checkpoint
from api.daily_stage_recovery import append_step
from api.price_sync_policy import price_sync_usable


def resume_daily_social_reports(client, job_id):
    result = (client.table('daily_job_runs').select('id,status,job_type,started_at,steps')
              .eq('id', job_id).limit(1).execute())
    job = (result.data or [None])[0]
    today = datetime.now(ZoneInfo('Africa/Cairo')).date()
    if (not job or job['status'] != 'completed' or job['job_type'] != 'daily_bot'
            or datetime.fromisoformat(job['started_at'].replace('Z', '+00:00')).astimezone(ZoneInfo('Africa/Cairo')).date() != today):
        raise ValueError('Only the completed current-session closing job may resume reports')
    raw = json.loads(job['steps']) if isinstance(job['steps'], str) else job['steps']
    steps = effective_daily_steps(raw)
    latest = {s['step']: s for s in steps}
    if not price_sync_usable(latest.get('sync_prices')) or latest.get('calculate_indicators', {}).get('status') != 'success':
        raise ValueError('Report inputs are not ready')
    key = 'daily_social_resume_' + job_id
    existing = read_checkpoint(client, key)
    attempts = 1
    if existing:
        payload = existing.get('payload') or {}
        reports_started = any(s.get('step') == 'daily_social_reports' and s.get('status') == 'started'
                              for s in raw if isinstance(s, dict))
        # A failed cache refresh is safe to retry once because report generation
        # has not started and the report table is still empty. Never replay an
        # LLM/report attempt whose outcome could be ambiguous.
        if (payload.get('status') != 'failed' or payload.get('stage') != 'cache_revalidation'
                or payload.get('attempts') != 1 or reports_started):
            return {'status': 'already_claimed', 'checkpoint': payload.get('status')}
        reports = (client.table('daily_social_reports').select('id').eq('job_run_id', job_id)
                   .limit(1).execute())
        if reports.data:
            return {'status': 'already_claimed', 'checkpoint': payload.get('status')}
        attempts = 2
    claim = replace_checkpoint(client, key, {'status': 'running', 'stage': 'cache_revalidation',
                                             'job_run_id': job_id, 'attempts': attempts}, existing)
    if not claim:
        return {'status': 'already_claimed'}
    try:
        from api.cache_invalidation import invalidate_daily_cache
        # Report symbol selection reads the cached technical scanner. Refresh
        # the validated datasets before requesting any LLM report.
        append_step(client, job, {'step': 'cache_revalidation', 'status': 'started',
                                  'details': 'Refresh successful current-session datasets before report continuation'})
        cache = invalidate_daily_cache(steps)
        if cache.get('error') or cache.get('skipped'):
            append_step(client, job, {'step': 'cache_revalidation', 'status': 'failed',
                                      'details': cache.get('error') or 'Cache refresh skipped'})
            raise RuntimeError('Current-session cache refresh did not complete')
        append_step(client, job, {'step': 'cache_revalidation', 'status': 'success',
                                  'details': 'Refreshed tags: ' + ', '.join(cache.get('invalidated', []))})
        claim = replace_checkpoint(client, key, {'status': 'running', 'stage': 'daily_social_reports',
                                                  'job_run_id': job_id, 'attempts': attempts}, claim)
        if not claim:
            raise RuntimeError('Could not reserve the report-generation stage')
        append_step(client, job, {'step': 'daily_social_reports', 'status': 'started',
                                  'details': 'Resume missing reports only; original trading results retained'})
        from api.daily_social_reports import generate_daily_social_reports
        reports = generate_daily_social_reports(job_id, steps, trigger='scheduled', client=client)
        ok, message, count = social_reports_outcome(reports)
        append_step(client, job, {'step': 'daily_social_reports', 'status': 'success' if ok else 'failed',
                                  'details': message, 'count': count})
        status = 'completed' if ok and not cache.get('error') else 'partial'
        saved = {'status': status, 'stage': 'complete', 'job_run_id': job_id,
                 'reports': reports, 'cache': cache, 'attempts': attempts}
        replace_checkpoint(client, key, saved, claim)
        return saved
    except Exception as error:
        stage = (claim.get('payload') or {}).get('stage', 'cache_revalidation')
        replace_checkpoint(client, key, {'status': 'failed', 'stage': stage, 'job_run_id': job_id,
                                        'error': type(error).__name__, 'attempts': attempts}, claim)
        raise
