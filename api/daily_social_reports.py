"""Generate four verified reports through the website's canonical LLM responder.

Called only after the daily data job is completed. No Facebook publishing or
LLM keys are duplicated here; reports are persisted once per session/type.
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
from api.daily_job_outcome import effective_daily_steps

REPORT_KINDS = ('stock', 'accumulation', 'market', 'follow_up')


def generate_daily_social_reports(job_run_id, steps, trigger='scheduled', dry_run=False, opener=None, client=None):
    date = datetime.now(ZoneInfo('Africa/Cairo'))
    steps = effective_daily_steps(steps)
    from api.price_sync_policy import price_sync_usable
    latest = {s.get('step'): s.get('status') for s in steps}
    sync_step = [s for s in steps if s.get('step') == 'sync_prices' and s.get('status') != 'started']
    prices_usable = price_sync_usable(sync_step[-1]) if sync_step else False
    if dry_run or trigger != 'scheduled' or date.weekday() in (4, 5):
        return {'skipped': True, 'reason': 'Not a scheduled trading-day run'}
    if not prices_usable or latest.get('calculate_indicators') != 'success':
        return {'skipped': True, 'reason': 'Essential data steps failed'}
    origin = (os.getenv('WEB_ORIGIN') or 'https://egxbots.com').rstrip('/')
    secret = os.getenv('REVALIDATE_SECRET') or os.getenv('ADMIN_SECRET_KEY')
    if not secret:
        return {'skipped': True, 'reason': 'Shared web authentication not configured'}
    endpoint = origin + '/api/social/daily-reports'
    results = {}
    for kind in REPORT_KINDS:
        if kind == 'accumulation' and latest.get('accumulation_scan') != 'success':
            results[kind] = {'status': 'skipped', 'reason': 'Accumulation scan failed'}
            continue
        if kind == 'market' and latest.get('refresh_market_status') != 'success':
            results[kind] = {'status': 'skipped', 'reason': 'Market refresh failed'}
            continue
        # Execute natively inside Python on Hugging Face Spaces to eliminate 4x120s Vercel Lambdas
        try:
            from api.native_social_reports import generate_native_social_report
            results[kind] = generate_native_social_report(kind, date.date().isoformat(), job_run_id)
        except Exception as error:
            results[kind] = {'status': 'failed', 'error': str(error)}
    images = {}
    fb_publication = None
    if client is not None:
        from api.social_report_images import attach_report_images
        images = attach_report_images(client, date.date().isoformat(), job_run_id)
        try:
            from api.social_facebook_publisher import auto_publish_daily_report_to_facebook
            fb_publication = auto_publish_daily_report_to_facebook(client, date.date().isoformat(), job_run_id)
        except Exception as error:
            # Preserve a useful diagnostic without logging provider responses,
            # request URLs, access tokens, or other secrets.
            import logging
            logging.getLogger(__name__).error(
                "[FB_AUTO] Auto-publish call failed (%s)", type(error).__name__
            )
    # Reports are created after the general market invalidation. Refresh their
    # own cache only after all report writes finish; never invoke an LLM here.
    if any(r.get('status') == 'ready' for r in results.values()):
        from api.cache_invalidation import invalidate_cache_tags
        invalidate_cache_tags(['daily-public-reports'])
    return {'date': date.date().isoformat(), 'reports': results, 'images': images, 'facebook_publication': fb_publication}
