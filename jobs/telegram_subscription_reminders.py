# /// script
# dependencies = ["requests"]
# ///
"""
EGX BOTS private Telegram subscription reminders.
Required environment:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  TELEGRAM_BOT_TOKEN or SUPPORT_BOT_TOKEN

Runs daily. Sends only to the user's private Telegram chat_id saved in
public.profiles.telegram_chat_id. It never sends to groups or channels.
Uses durable idempotency logging in public.telegram_subscription_reminder_log.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

CAIRO = ZoneInfo("Africa/Cairo")
SITE_URL = os.getenv("EGXBOTS_BILLING_URL", "https://egxbots.com/profile#subscription")
API_TIMEOUT = 20
LIFETIME_KEYWORDS = {"lifetime", "pro_lifetime", "lifetime_vip", "lifetime-vip", "lifetime-vip-pro"}


def get_supabase_config() -> Tuple[str, str, Dict[str, str]]:
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        raise RuntimeError("Missing required SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    return url, key, headers


def get_telegram_token() -> str:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("SUPPORT_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("Missing required secret: TELEGRAM_BOT_TOKEN (or SUPPORT_BOT_TOKEN)")
    return token


def parse_chat_id(raw_chat_id: Any) -> Optional[int]:
    """Safely parse Telegram private chat ID (rejects non-positive / channels)."""
    if not raw_chat_id:
        return None
    s = str(raw_chat_id).strip()
    if "_" in s:
        s = s.split("_", 1)[0]
    try:
        cid = int(float(s))
        return cid if cid > 0 else None
    except (ValueError, TypeError):
        return None


def send_private_telegram(chat_id: int, text: str, token: str) -> dict:
    """Send private Telegram message with relay fallback for regional network reliability."""
    if chat_id <= 0:
        raise ValueError(f"Invalid private Telegram chat_id: {chat_id}")

    relay = (os.getenv("TELEGRAM_RELAY_URL") or "https://api.telegram.org").strip().rstrip("/")
    bases = [relay] if relay != "https://api.telegram.org" else []
    bases.append("https://api.telegram.org")

    last_exc = None
    for base in bases:
        try:
            response = requests.post(
                f"{base}/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
                timeout=API_TIMEOUT,
            )
            if response.status_code == 200:
                body = response.json()
                if body.get("ok"):
                    return body.get("result", {})
                last_exc = RuntimeError(f"Telegram API rejected message: {body}")
            else:
                last_exc = RuntimeError(f"Telegram API HTTP {response.status_code}: {response.text[:250]}")
        except Exception as exc:
            last_exc = exc
            continue

    raise last_exc or RuntimeError("Failed to send Telegram message to all endpoints")


def message_for(stage: int, days_left: int, end_date: str) -> str:
    """Compose clear, actionable Arabic renewal reminder."""
    if stage == 7:
        lead = f"🔔 تذكير من EGX BOTS PRO\n\nفاضل {days_left} أيام على انتهاء اشتراكك."
    elif stage == 3:
        if days_left == 1:
            lead = "⏳ تذكير من EGX BOTS PRO\n\nفاضل يوم واحد على انتهاء اشتراكك."
        elif days_left == 2:
            lead = "⏳ تذكير من EGX BOTS PRO\n\nفاضل يومين على انتهاء اشتراكك."
        else:
            lead = f"⏳ تذكير من EGX BOTS PRO\n\nفاضل {days_left} أيام على انتهاء اشتراكك."
    else:
        if days_left < 0:
            lead = "⚠️ تنبيه من EGX BOTS PRO\n\nاشتراكك انتهى مؤخراً."
        else:
            lead = "⚠️ تذكير من EGX BOTS PRO\n\nاشتراكك بينتهي النهارده."

    return (
        f"{lead}\n"
        f"تاريخ الانتهاء: {end_date}\n\n"
        "للاستمرار في الاستفادة من الإشارات الفورية وروبوتات التداول وأدوات Pro، "
        "تقدر تجدّد اشتراكك من هنا:\n"
        f"{SITE_URL}\n\n"
        "لو كنت جدّدت بالفعل، تجاهل الرسالة دي."
    )


def determine_reminder_stage(days_left: int) -> Optional[int]:
    """
    Map remaining days to target reminder stage with catch-up windows
    so skipped days (e.g. weekend/holidays) do not miss alerts:
      - Stage 7: 4 to 7 days remaining
      - Stage 3: 1 to 3 days remaining
      - Stage 0: -1 to 0 days remaining (expired today or yesterday)
    """
    if 4 <= days_left <= 7:
        return 7
    if 1 <= days_left <= 3:
        return 3
    if -1 <= days_left <= 0:
        return 0
    return None


def is_lifetime_plan(plan_id: str) -> bool:
    """Check if a plan should never receive expiration reminders."""
    p = str(plan_id or "").lower().strip()
    return "lifetime" in p or p in LIFETIME_KEYWORDS


def run_subscription_reminders(
    now: Optional[datetime] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Core executor for private Telegram renewal reminders.
    Can be invoked programmatically (from daily job scheduler or API)
    or as a standalone script.
    """
    now = now or datetime.now(timezone.utc)
    cairo_today = now.astimezone(CAIRO).date()
    print(f"[SUBSCRIPTION_REMINDERS] Starting run Cairo date={cairo_today.isoformat()} UTC={now.isoformat()}")

    supabase_url, _, headers = get_supabase_config()
    telegram_token = get_telegram_token()
    rest = f"{supabase_url}/rest/v1"

    # 1. Fetch active subscriptions with a set period end
    resp = requests.get(
        f"{rest}/subscriptions",
        headers=headers,
        params={
            "select": "id,user_id,plan_id,status,current_period_end",
            "status": "eq.active",
            "current_period_end": "not.is.null",
            "limit": "1000",
        },
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    subscriptions = resp.json()

    eligible = []
    user_ids = set()
    for sub in subscriptions:
        if is_lifetime_plan(sub.get("plan_id")):
            continue
        try:
            raw_end = str(sub.get("current_period_end") or "")
            end_dt = datetime.fromisoformat(raw_end.replace("Z", "+00:00"))
        except Exception:
            print(f"[SUBSCRIPTION_REMINDERS] [skip] invalid end date for subscription={sub.get('id')}")
            continue

        days_left = (end_dt.astimezone(CAIRO).date() - cairo_today).days
        stage = determine_reminder_stage(days_left)
        if stage is not None:
            eligible.append((sub, end_dt, days_left, stage))
            user_ids.add(sub["user_id"])

    if not eligible:
        print("[SUBSCRIPTION_REMINDERS] [done] No reminders due today")
        return {"status": "completed", "sent": 0, "failed": 0, "skipped": 0, "eligible": 0}

    # 2. Fetch profiles for eligible users
    prof_resp = requests.get(
        f"{rest}/profiles",
        headers=headers,
        params={
            "select": "id,telegram_chat_id,display_name,username",
            "id": "in.(" + ",".join(sorted(user_ids)) + ")",
            "limit": "1000",
        },
        timeout=API_TIMEOUT,
    )
    prof_resp.raise_for_status()
    profiles = prof_resp.json()
    profile_by_id = {p["id"]: p for p in profiles}

    sent = 0
    failed = 0
    skipped = 0

    for sub, end_dt, days_left, stage in eligible:
        profile = profile_by_id.get(sub["user_id"], {})
        raw_chat_id = profile.get("telegram_chat_id")
        chat_id = parse_chat_id(raw_chat_id)
        if not chat_id:
            skipped += 1
            print(f"[SUBSCRIPTION_REMINDERS] [skip] no linked private Telegram chat for user={sub['user_id']}")
            continue

        period_end = end_dt.astimezone(timezone.utc).isoformat()
        log_payload = {
            "subscription_id": sub["id"],
            "user_id": sub["user_id"],
            "period_end": period_end,
            "reminder_days": stage,
            "status": "pending",
        }

        # Idempotency check via durable log
        insert_res = requests.post(
            f"{rest}/telegram_subscription_reminder_log",
            headers={**headers, "Prefer": "return=representation"},
            json=log_payload,
            timeout=API_TIMEOUT,
        )

        log_id = None
        if insert_res.status_code == 409:
            # Row already exists; inspect state
            existing_res = requests.get(
                f"{rest}/telegram_subscription_reminder_log",
                headers=headers,
                params={
                    "select": "id,status,created_at",
                    "subscription_id": f"eq.{sub['id']}",
                    "period_end": f"eq.{period_end}",
                    "reminder_days": f"eq.{stage}",
                    "limit": "1",
                },
                timeout=API_TIMEOUT,
            )
            existing = existing_res.json() if existing_res.ok else []
            if not existing:
                failed += 1
                print(f"[SUBSCRIPTION_REMINDERS] [error] conflict but log row not found subscription={sub['id']}")
                continue
            row = existing[0]
            if row.get("status") == "sent":
                print(f"[SUBSCRIPTION_REMINDERS] [skip] already sent subscription={sub['id']} stage={stage}")
                continue

            # Retry only if previous pending/failed attempt is at least 20 minutes old
            try:
                created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                if (now - created_at).total_seconds() < 1200:
                    print(f"[SUBSCRIPTION_REMINDERS] [skip] recent attempt pending subscription={sub['id']}")
                    continue
            except Exception:
                pass

            requests.patch(
                f"{rest}/telegram_subscription_reminder_log",
                headers=headers,
                params={"id": f"eq.{row['id']}"},
                json={"status": "pending", "error": None},
                timeout=API_TIMEOUT,
            )
            log_id = row["id"]
        elif insert_res.ok:
            returned = insert_res.json()
            if not returned:
                failed += 1
                print(f"[SUBSCRIPTION_REMINDERS] [error] log insert returned empty row subscription={sub['id']}")
                continue
            log_id = returned[0]["id"]
        else:
            failed += 1
            print(f"[SUBSCRIPTION_REMINDERS] [error] log insert failed status={insert_res.status_code} body={insert_res.text[:200]}")
            continue

        if dry_run:
            print(f"[SUBSCRIPTION_REMINDERS] [dry-run] would send stage={stage} to chat_id={chat_id}")
            continue

        # Send Telegram notification
        msg_text = message_for(stage, days_left, end_dt.astimezone(CAIRO).date().isoformat())
        try:
            tg_result = send_private_telegram(chat_id, msg_text, telegram_token)
            requests.patch(
                f"{rest}/telegram_subscription_reminder_log",
                headers=headers,
                params={"id": f"eq.{log_id}"},
                json={
                    "status": "sent",
                    "telegram_message_id": tg_result.get("message_id"),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                },
                timeout=API_TIMEOUT,
            )
            sent += 1
            print(f"[SUBSCRIPTION_REMINDERS] [sent] user={sub['user_id']} stage={stage} days_left={days_left}")
        except Exception as send_err:
            failed += 1
            try:
                requests.patch(
                    f"{rest}/telegram_subscription_reminder_log",
                    headers=headers,
                    params={"id": f"eq.{log_id}"},
                    json={"status": "failed", "error": str(send_err)[:1000]},
                    timeout=API_TIMEOUT,
                )
            except Exception as patch_err:
                print(f"[SUBSCRIPTION_REMINDERS] [error] unable to update failure log: {patch_err}")
            print(f"[SUBSCRIPTION_REMINDERS] [error] send failed user={sub['user_id']}: {send_err}")

        time.sleep(0.15)

    summary = {
        "status": "completed" if failed == 0 else "partial_success",
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "eligible": len(eligible),
    }
    print(f"[SUBSCRIPTION_REMINDERS] Summary: {summary}")
    return summary


def main() -> int:
    try:
        res = run_subscription_reminders()
        return 0 if res.get("failed", 0) == 0 else 1
    except Exception as exc:
        print(f"[SUBSCRIPTION_REMINDERS] [fatal] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
