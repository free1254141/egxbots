"""
Scanner Alerts Scheduler — background thread in FastAPI.
Monitors EGX market hours (Sun-Thu 10:00 - 14:35 Cairo time)
and triggers the scanner alerts pipeline at the configured interval (e.g. every 15 minutes).
Features thread-level concurrency locks and cooldown guards to prevent duplicate execution.
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
_scan_lock = threading.Lock()
_saudi_last_run_timestamp: float = 0.0
_saudi_scan_lock = threading.Lock()

def _get_cairo_time() -> dt.datetime:
    try:
        return dt.datetime.now(ZoneInfo("Africa/Cairo"))
    except Exception:
        # Fallback to UTC+2
        return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)

def _get_riyadh_time() -> dt.datetime:
    try:
        return dt.datetime.now(ZoneInfo("Asia/Riyadh"))
    except Exception:
        return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)

def _is_market_session(cairo_dt: dt.datetime) -> bool:
    # Python weekday: Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    # EGX trading days: Sunday (6), Monday (0), Tuesday (1), Wednesday (2), Thursday (3)
    if cairo_dt.weekday() not in {6, 0, 1, 2, 3}:
        return False
    
    total_minutes = cairo_dt.hour * 60 + cairo_dt.minute
    # EGX Market hours: 10:00 AM (600m) to 02:35 PM (875m)
    return 600 <= total_minutes <= 875

def _is_saudi_market_session(riyadh_dt: dt.datetime) -> bool:
    try:
        from api.saudi_trading_calendar import is_saudi_session
        if not is_saudi_session(riyadh_dt):
            return False
    except Exception:
        if riyadh_dt.weekday() not in {6, 0, 1, 2, 3}:
            return False
    total_minutes = riyadh_dt.hour * 60 + riyadh_dt.minute
    # Tadawul regular hours: 10:00 AM (600m) to 03:00 PM (900m) Riyadh
    return 600 <= total_minutes <= 900

def _trigger_scanner_job(force: bool = False, force_dispatch: bool = False) -> Dict[str, Any]:
    global _last_run_timestamp
    if not _scan_lock.acquire(blocking=False):
        print("[SCANNER_SCHEDULER] Concurrency lock active: another scan is currently executing. Skipping.")
        return {"ok": False, "skipped": True, "reason": "concurrency_lock_active"}

    try:
        now = time.time()
        # Cooldown: Minimum 10 minutes (600s) between successive scans unless force_dispatch is explicitly requested
        if not force_dispatch and (now - _last_run_timestamp < 600):
            print(f"[SCANNER_SCHEDULER] Cooldown active (elapsed: {int(now - _last_run_timestamp)}s < 600s). Skipping.")
            return {"ok": True, "skipped": True, "reason": "cooldown_active"}

        _last_run_timestamp = now

        # Execute scanner natively inside Python on Hugging Face Spaces to avoid
        # waking Vercel Serverless Functions or consuming Vercel CPU quotas.
        try:
            from api.scanner_alerts_engine import execute_scanner_alerts_native
            res = execute_scanner_alerts_native(force=force, force_dispatch=force_dispatch)
            if res.get("ok"):
                dispatched = res.get("alerts_dispatched", 0)
                matches = res.get("matches", {})
                print(f"[SCANNER_SCHEDULER] Native Python scan executed! Dispatched: {dispatched} alerts to Telegram. Matches: {matches}")
                return {"ok": True, "data": res}
            elif res.get("skipped"):
                return res
        except Exception as e:
            print(f"[SCANNER_SCHEDULER] Native Python scanner error: {e}")

        # Fallback to local dev endpoint only if running in local development
        admin_key = os.getenv("ADMIN_SECRET_KEY", "").strip()
        for url in ["http://localhost:3000/api/cron/scanner-alerts", "http://127.0.0.1:3000/api/cron/scanner-alerts"]:
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
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if resp.status == 200:
                        _last_run_timestamp = time.time()
                        return {"ok": True, "data": data}
            except Exception:
                continue

        return {"ok": False, "error": "Native scan skipped or inactive"}
    finally:
        _scan_lock.release()

def trigger_scanner_job_now(force: bool = True, force_dispatch: bool = True) -> Dict[str, Any]:
    return _trigger_scanner_job(force=force, force_dispatch=force_dispatch)

def _trigger_saudi_scanner_job(force: bool = False, force_dispatch: bool = False) -> Dict[str, Any]:
    global _saudi_last_run_timestamp
    if not _saudi_scan_lock.acquire(blocking=False):
        return {"ok": False, "skipped": True, "reason": "saudi_concurrency_lock_active"}
    try:
        now = time.time()
        if not force_dispatch and (now - _saudi_last_run_timestamp < 600):
            return {"ok": True, "skipped": True, "reason": "saudi_cooldown_active"}
        _saudi_last_run_timestamp = now
        from api.saudi_scanner_alerts_engine import execute_saudi_scanner_alerts_native
        res = execute_saudi_scanner_alerts_native(force=force, force_dispatch=force_dispatch)
        print(f"[SCANNER_SCHEDULER] Saudi native scan result: {res}")
        return res
    except Exception as e:
        print(f"[SCANNER_SCHEDULER] Saudi native scanner error: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        _saudi_scan_lock.release()

def _worker_loop():
    print("[SCANNER_SCHEDULER] Worker thread started. Monitoring EGX & Saudi session hours...")
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

            riyadh_now = _get_riyadh_time()
            if (
                os.getenv("SAUDI_SUPABASE_URL")
                and os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY")
                and _is_saudi_market_session(riyadh_now)
            ):
                saudi_elapsed = time.time() - _saudi_last_run_timestamp
                if saudi_elapsed >= 15 * 60:
                    print(f"[SCANNER_SCHEDULER] Tadawul session active ({riyadh_now.strftime('%H:%M:%S')} Riyadh). Triggering Saudi scanner...")
                    threading.Thread(
                        target=_trigger_saudi_scanner_job,
                        daemon=True,
                        name="SaudiScannerAlert",
                    ).start()
            
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
