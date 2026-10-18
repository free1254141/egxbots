"""
Scanner Alerts Scheduler — background thread in FastAPI.
Monitors EGX market hours (Sun-Thu 10:00 - 14:35 Cairo time)
and triggers the scanner alerts pipeline at the configured interval (e.g. every 15 minutes).
"""
import os
import time
import threading
import datetime as dt
import urllib.request
import json
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any

_scheduler_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_last_run_timestamp: float = 0.0

def _get_cairo_time() -> dt.datetime:
    try:
        return dt.datetime.now(ZoneInfo("Africa/Cairo"))
    except Exception:
        # Fallback to UTC+2
        return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)

def _is_market_session(cairo_dt: dt.datetime) -> bool:
    # Python weekday: Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    # EGX trading days: Sunday (6), Monday (0), Tuesday (1), Wednesday (2), Thursday (3)
    if cairo_dt.weekday() not in {6, 0, 1, 2, 3}:
        return False
    
    total_minutes = cairo_dt.hour * 60 + cairo_dt.minute
    # EGX Market hours: 10:00 AM (600m) to 02:35 PM (875m)
    return 600 <= total_minutes <= 875

def _trigger_scanner_job(force: bool = False, force_dispatch: bool = False) -> Dict[str, Any]:
    global _last_run_timestamp
    admin_key = os.getenv("ADMIN_SECRET_KEY", "").strip()
    web_origin = os.getenv("WEB_ORIGIN", "https://egxbots.com").rstrip("/")
    target_urls = [
        f"{web_origin}/api/cron/scanner-alerts",
        "http://localhost:3000/api/cron/scanner-alerts",
        "http://127.0.0.1:3000/api/cron/scanner-alerts"
    ]

    last_error = None
    result_data = None
    for url in target_urls:
        try:
            req = urllib.request.Request(
                url,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "x-admin-key": admin_key,
                },
                data=json.dumps({
                    "trigger": "Python Manual Trigger" if force else "Python Background Scheduler",
                    "force": force,
                    "force_dispatch": force_dispatch,
                }).encode("utf-8")
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if resp.status == 200:
                    dispatched = data.get("alerts_dispatched", 0)
                    matches = data.get("matches", {})
                    fresh = data.get("fresh_matches", {})
                    print(f"[SCANNER_SCHEDULER] Scan executed! Dispatched: {dispatched} alerts to Telegram. Matches: {matches}, Fresh: {fresh}")
                    _last_run_timestamp = time.time()
                    return {"ok": True, "data": data}
        except Exception as e:
            last_error = str(e)
            continue

    print(f"[SCANNER_SCHEDULER] Scanner trigger skipped or failed to reach frontend cron endpoint. Error: {last_error}")
    return {"ok": False, "error": last_error}

def trigger_scanner_job_now(force: bool = True, force_dispatch: bool = True) -> Dict[str, Any]:
    return _trigger_scanner_job(force=force, force_dispatch=force_dispatch)

def _worker_loop():
    print("[SCANNER_SCHEDULER] Worker thread started. Monitoring EGX session hours...")
    while not _stop_event.is_set():
        try:
            cairo_now = _get_cairo_time()
            if _is_market_session(cairo_now):
                # Default interval: 15 minutes (900 seconds)
                interval_seconds = 15 * 60
                
                # Check how much time passed since last run
                elapsed = time.time() - _last_run_timestamp
                if elapsed >= interval_seconds:
                    print(f"[SCANNER_SCHEDULER] EGX session active ({cairo_now.strftime('%H:%M:%S')} Cairo). Triggering scanner...")
                    _trigger_scanner_job()
            
        except Exception as e:
            print(f"[SCANNER_SCHEDULER] Worker error: {e}")

        # Sleep in small slices to allow clean shutdown
        for _ in range(30):
            if _stop_event.is_set():
                break
            time.sleep(1)

def start_scanner_alerts_scheduler():
    global _scheduler_thread, _stop_event
    if _scheduler_thread and _scheduler_thread.is_alive():
        print("[SCANNER_SCHEDULER] Scheduler is already running.")
        return

    _stop_event.clear()
    _scheduler_thread = threading.Thread(target=_worker_loop, name="ScannerAlertsScheduler", daemon=True)
    _scheduler_thread.start()
    print("[SCANNER_SCHEDULER] Background scheduler started successfully.")

def stop_scanner_alerts_scheduler():
    global _stop_event
    _stop_event.set()
    print("[SCANNER_SCHEDULER] Background scheduler stopped.")
