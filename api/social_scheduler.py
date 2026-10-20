"""Autonomous Facebook Social Media Scheduler for Hugging Face Spaces / Python Backend.

Schedules 3 daily post-market and pre-market image publications at peak viewing hours:
1. Slot 1 (18:45 Cairo): Market Overview (وضع السوق المصري — market)
2. Slot 2 (21:30 Cairo): Top Stock Analysis (تحليل سهم الجلسة الأبرز — stock)
3. Slot 3 (08:45 Cairo next morning): Accumulation & Smart Money (أسهم التجميع المالي — accumulation)

Runs as a lightweight daemon background thread in FastAPI (api/main.py).
Zero remote log polling. Idempotent deduplication via daily_social_publications.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from api.social_facebook_publisher import (
    get_facebook_credentials,
    publish_photo_to_facebook_page,
)

logger = logging.getLogger("social_scheduler")
logger.setLevel(logging.INFO)

CAIRO_TZ = ZoneInfo("Africa/Cairo")

SCHEDULED_SLOTS = [
    {
        "slot_id": "market_evening",
        "time": "18:45",
        "preferred_kind": "market",
        "fallback_kinds": ["stock", "accumulation", "follow_up"],
        "description": "وضع السوق المصري — ذروة المساء الأولى (18:45)",
        "target": "current_session",
    },
    {
        "slot_id": "stock_night",
        "time": "21:30",
        "preferred_kind": "stock",
        "fallback_kinds": ["market", "accumulation", "follow_up"],
        "description": "تحليل سهم الجلسة الأبرز — ذروة السهرة وأعلى تفاعل (21:30)",
        "target": "current_session",
    },
    {
        "slot_id": "accumulation_morning",
        "time": "08:45",
        "preferred_kind": "accumulation",
        "fallback_kinds": ["follow_up", "stock", "market"],
        "description": "أسهم التجميع المالي والسيولة — ذروة الصباح قبل الجلسة (08:45)",
        "target": "latest_closed_session",
    },
]

_scheduler_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_completed_slots_lock = threading.Lock()
_completed_slots_today: set = set()
_last_cleanup_day: Optional[str] = None


def now_cairo() -> datetime:
    """Return current timestamp in Africa/Cairo timezone."""
    try:
        return datetime.now(CAIRO_TZ)
    except Exception:
        return datetime.now(timezone.utc) + timedelta(hours=3)


def is_egx_trading_day(dt: datetime) -> bool:
    """Sunday (6) through Thursday (3) are Egyptian trading days."""
    return dt.weekday() in (6, 0, 1, 2, 3)


def resolve_session_date_for_slot(slot: Dict[str, Any], now_dt: datetime) -> Optional[str]:
    """Resolve the session date that should be published for a given slot."""
    target_mode = slot.get("target", "current_session")

    if target_mode == "current_session":
        if is_egx_trading_day(now_dt):
            return now_dt.date().isoformat()
        return None

    if target_mode == "latest_closed_session":
        weekday = now_dt.weekday()
        if weekday == 6:  # Sunday morning: target Thursday's session (3 days prior)
            return (now_dt - timedelta(days=3)).date().isoformat()
        if weekday in (0, 1, 2, 3):  # Mon-Thu morning: target yesterday's session
            return (now_dt - timedelta(days=1)).date().isoformat()
        return None

    return None


def is_slot_due(slot: Dict[str, Any], now_dt: datetime, window_minutes: int = 15) -> bool:
    """Return true for a due slot, including a bounded same-day catch-up window.

    A sleeping/restarting Space can miss the exact publication minute. The
    caller may widen window_minutes to catch up, but never across midnight.
    """
    slot_hour, slot_minute = map(int, slot["time"].split(":"))
    slot_time_today = now_dt.replace(
        hour=slot_hour, minute=slot_minute, second=0, microsecond=0
    )
    diff_minutes = (now_dt - slot_time_today).total_seconds() / 60.0
    minutes_until_midnight = (23 * 60 + 59) - (slot_hour * 60 + slot_minute)
    allowed_window = min(window_minutes, minutes_until_midnight)
    return 0 <= diff_minutes <= allowed_window


def execute_publication_slot(
    client: Any,
    slot: Dict[str, Any],
    now_dt: datetime,
    force: bool = False,
    opener: Any = None,
) -> Dict[str, Any]:
    """Execute publication for a specific slot with idempotency guard."""
    if not client:
        return {"status": "skipped", "reason": "No database client"}

    session_date = resolve_session_date_for_slot(slot, now_dt)
    if not session_date:
        return {"status": "skipped", "reason": f"Not a trading day window for {slot['slot_id']}"}

    slot_key = f"{session_date}:{slot['slot_id']}"
    with _completed_slots_lock:
        if not force and slot_key in _completed_slots_today:
            return {"status": "skipped", "reason": f"Slot {slot_key} already published in memory"}

    # 1. Check database idempotency
    try:
        existing = (
            client.table("daily_social_publications")
            .select("state, post_id, kind")
            .eq("session_date", session_date)
            .eq("platform", "facebook")
            .eq("kind", slot["preferred_kind"])
            .maybe_single()
            .execute()
        )
        if existing and existing.data and existing.data.get("state") == "published":
            with _completed_slots_lock:
                _completed_slots_today.add(slot_key)
            return {
                "status": "already_published",
                "post_id": existing.data.get("post_id"),
                "session_date": session_date,
                "kind": slot["preferred_kind"],
            }
    except Exception as e:
        logger.warning(f"[FB_SCHEDULER] Could not check existing publication: {e}")

    # 2. Check credentials from market_cache / env
    creds = get_facebook_credentials(client)
    if not creds or not creds.get("token"):
        logger.warning("[FB_SCHEDULER] Skipping slot: Facebook Page Access Token not configured")
        return {"status": "skipped", "reason": "Token not configured"}

    # 3. Find suitable report image from daily_social_reports
    candidate_kinds = [slot["preferred_kind"]] + slot.get("fallback_kinds", [])
    selected_report = None
    selected_kind = None

    for kind in candidate_kinds:
        try:
            res = (
                client.table("daily_social_reports")
                .select("kind, symbol, image_url, image_status, social_caption, social_title")
                .eq("session_date", session_date)
                .eq("kind", kind)
                .maybe_single()
                .execute()
            )
            r = res.data if res else None
            if r and r.get("image_url") and r.get("image_status") == "ready":
                selected_report = r
                selected_kind = kind
                break
        except Exception as e:
            logger.warning(f"[FB_SCHEDULER] Error fetching report {kind}: {e}")

    if not selected_report:
        logger.info(
            f"[FB_SCHEDULER] No ready report found for {candidate_kinds} on {session_date}"
        )
        return {
            "status": "no_report",
            "session_date": session_date,
            "kinds": candidate_kinds,
        }

    image_url = selected_report["image_url"]
    caption = selected_report.get("social_caption") or selected_report.get("social_title") or ""

    # 4. Publish via Graph API
    try:
        publish_res = publish_photo_to_facebook_page(
            image_url=image_url,
            caption=caption,
            page_id=creds["page_id"],
            token=creds["token"],
            opener=opener,
        )
        post_id = publish_res.get("post_id")
        logger.info(
            f"[FB_SCHEDULER] ✅ Published {selected_kind} for session {session_date} ({slot['description']}) — post_id: {post_id}"
        )

        # 5. Record state in daily_social_publications
        client.table("daily_social_publications").upsert({
            "session_date": session_date,
            "platform": "facebook",
            "kind": selected_kind,
            "state": "published",
            "post_id": post_id,
            "publication_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        with _completed_slots_lock:
            _completed_slots_today.add(slot_key)

        return {
            "status": "published",
            "session_date": session_date,
            "kind": selected_kind,
            "post_id": post_id,
            "slot_id": slot["slot_id"],
        }
    except Exception as exc:
        logger.error(f"[FB_SCHEDULER] Publication failed for {slot['slot_id']}: {exc}")
        return {"status": "failed", "error": str(exc), "slot_id": slot["slot_id"]}


def _cleanup_daily_tracking_if_new_day(now_dt: datetime) -> None:
    global _last_cleanup_day, _completed_slots_today
    day_str = now_dt.date().isoformat()
    if _last_cleanup_day != day_str:
        with _completed_slots_lock:
            _completed_slots_today.clear()
            _last_cleanup_day = day_str


def _scheduler_worker_loop():
    logger.info("[FB_SCHEDULER] Background scheduler worker loop started.")
    while not _stop_event.is_set():
        try:
            now_dt = now_cairo()
            _cleanup_daily_tracking_if_new_day(now_dt)

            from api.short_swings_daily import _get_supabase_client

            client = _get_supabase_client()

            for slot in SCHEDULED_SLOTS:
                if is_slot_due(slot, now_dt, window_minutes=900):
                    execute_publication_slot(client, slot, now_dt)

        except Exception as e:
            logger.warning(f"[FB_SCHEDULER] Worker loop tick error: {e}")

        # Tick every 30 seconds
        _stop_event.wait(30)

    logger.info("[FB_SCHEDULER] Worker loop terminated.")


def start_social_scheduler():
    """Start the background social scheduler thread if not already running."""
    global _scheduler_thread, _stop_event
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.info("[FB_SCHEDULER] Scheduler is already active.")
        return

    _stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_worker_loop,
        name="FacebookSocialScheduler",
        daemon=True,
    )
    _scheduler_thread.start()
    logger.info("[FB_SCHEDULER] Autonomous 3-slot Facebook Social Scheduler started successfully.")


def stop_social_scheduler():
    """Stop the background social scheduler thread."""
    global _stop_event
    _stop_event.set()
    logger.info("[FB_SCHEDULER] Stopping Facebook Social Scheduler...")
