# /// script
# dependencies = ["requests"]
# ///
"""
EGX BOTS private Telegram subscription reminders.
Required environment:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  TELEGRAM_BOT_TOKEN

Runs once daily. Sends only to the user's private Telegram chat_id saved in
public.profiles.telegram_chat_id. It never sends to a group/channel.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

CAIRO = ZoneInfo("Africa/Cairo")
SITE_URL = os.getenv("EGXBOTS_BILLING_URL", "https://egxbots.com/profile")
API_TIMEOUT = 20
DAYS_TO_REMIND = {7, 3, 0}
LIFETIME_PLAN_IDS = {"lifetime", "lifetime_vip", "lifetime-vip", "lifetime-vip-pro"}


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required secret: {name}")
    return value


SUPABASE_URL = required_env("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = required_env("SUPABASE_SERVICE_ROLE_KEY")
TELEGRAM_TOKEN = required_env("TELEGRAM_BOT_TOKEN")
REST = f"{SUPABASE_URL}/rest/v1"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def supabase_get(table: str, params: dict) -> list[dict]:
    response = requests.get(
        f"{REST}/{table}", headers=HEADERS, params=params, timeout=API_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response from {table}")
    return data


def supabase_post(table: str, payload: dict, *, prefer: str = "return=representation"):
    headers = {**HEADERS, "Prefer": prefer}
    response = requests.post(
        f"{REST}/{table}", headers=headers, json=payload, timeout=API_TIMEOUT
    )
    return response


def supabase_patch(table: str, params: dict, payload: dict):
    response = requests.patch(
        f"{REST}/{table}", headers=HEADERS, params=params,
        json=payload, timeout=API_TIMEOUT
    )
    response.raise_for_status()


def send_private_telegram(chat_id: str, text: str) -> dict:
    # Only direct private chat IDs are accepted; groups/supergroups/channels are rejected.
    cid = int(str(chat_id).strip())
    if cid <= 0:
        raise ValueError("Not a positive Telegram private chat_id")
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": cid, "text": text, "disable_web_page_preview": True},
        timeout=API_TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram API rejected message: {body}")
    return body["result"]


def message_for(days_left: int, end_date: str) -> str:
    if days_left == 7:
        lead = "🔔 تذكير من EGX BOTS PRO\n\nفاضل 7 أيام على انتهاء اشتراكك."
    elif days_left == 3:
        lead = "⏳ تذكير من EGX BOTS PRO\n\nفاضل 3 أيام على انتهاء اشتراكك."
    else:
        lead = "⚠️ تذكير من EGX BOTS PRO\n\nاشتراكك بينتهي النهارده."
    return (
        f"{lead}\n"
        f"تاريخ الانتهاء: {end_date}\n\n"
        "للاستمرار في الاستفادة من الإشارات الفورية وأدوات Pro، "
        "تقدر تجدّد اشتراكك من هنا:\n"
        f"{SITE_URL}\n\n"
        "لو كنت جدّدت بالفعل، تجاهل الرسالة دي."
    )


def main() -> int:
    now = datetime.now(timezone.utc)
    cairo_today = now.astimezone(CAIRO).date()
    print(f"[start] Cairo date={cairo_today.isoformat()} UTC={now.isoformat()}")

    subscriptions = supabase_get(
        "subscriptions",
        {
            "select": "id,user_id,plan_id,status,current_period_end",
            "status": "eq.active",
            "current_period_end": "not.is.null",
            "limit": "1000",
        },
    )
    eligible = []
    user_ids = set()
    for sub in subscriptions:
        plan = str(sub.get("plan_id") or "").lower().strip()
        if plan in LIFETIME_PLAN_IDS:
            continue
        try:
            end_dt = datetime.fromisoformat(sub["current_period_end"].replace("Z", "+00:00"))
        except Exception:
            print(f"[skip] invalid end date for subscription={sub.get('id')}")
            continue
        days_left = (end_dt.astimezone(CAIRO).date() - cairo_today).days
        if days_left in DAYS_TO_REMIND:
            eligible.append((sub, end_dt, days_left))
            user_ids.add(sub["user_id"])

    if not eligible:
        print("[done] no reminders due today")
        return 0

    profiles = supabase_get(
        "profiles",
        {
            "select": "id,telegram_chat_id,display_name,username",
            "id": "in.(" + ",".join(sorted(user_ids)) + ")",
            "limit": "1000",
        },
    )
    profile_by_id = {p["id"]: p for p in profiles}
    sent = failed = skipped = 0

    for sub, end_dt, days_left in eligible:
        profile = profile_by_id.get(sub["user_id"], {})
        chat_id = str(profile.get("telegram_chat_id") or "").strip()
        if not chat_id:
            skipped += 1
            print(f"[skip] no linked private Telegram chat for user={sub['user_id']}")
            continue

        period_end = end_dt.astimezone(timezone.utc).isoformat()
        log_payload = {
            "subscription_id": sub["id"],
            "user_id": sub["user_id"],
            "period_end": period_end,
            "reminder_days": days_left,
            "status": "pending",
        }
        # Idempotency key: subscription + exact period end + reminder stage.
        insert = supabase_post(
            "telegram_subscription_reminder_log",
            log_payload,
            prefer="return=representation",
        )
        if insert.status_code == 409:
            existing = supabase_get(
                "telegram_subscription_reminder_log",
                {
                    "select": "id,status,created_at",
                    "subscription_id": f"eq.{sub['id']}",
                    "period_end": f"eq.{period_end}",
                    "reminder_days": f"eq.{days_left}",
                    "limit": "1",
                },
            )
            if not existing:
                failed += 1
                print(f"[error] conflict but log row not found subscription={sub['id']}")
                continue
            row = existing[0]
            if row.get("status") == "sent":
                print(f"[skip] already sent subscription={sub['id']} days={days_left}")
                continue
            # Retry only a failed/pending row that is at least 20 minutes old,
            # avoiding immediate duplicate sends after a transient request timeout.
            created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            if (now - created_at).total_seconds() < 1200:
                print(f"[skip] recent pending attempt subscription={sub['id']}")
                continue
            supabase_patch(
                "telegram_subscription_reminder_log",
                {"id": f"eq.{row['id']}"},
                {"status": "pending", "error": None},
            )
            log_id = row["id"]
        elif insert.ok:
            returned = insert.json()
            if not returned:
                failed += 1
                print(f"[error] log insert returned no row subscription={sub['id']}")
                continue
            log_id = returned[0]["id"]
        else:
            failed += 1
            print(f"[error] log insert failed status={insert.status_code} body={insert.text[:300]}")
            continue

        try:
            result = send_private_telegram(chat_id, message_for(days_left, end_dt.astimezone(CAIRO).date().isoformat()))
            supabase_patch(
                "telegram_subscription_reminder_log",
                {"id": f"eq.{log_id}"},
                {
                    "status": "sent",
                    "telegram_message_id": result.get("message_id"),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                },
            )
            sent += 1
            print(f"[sent] user={sub['user_id']} days_left={days_left}")
        except Exception as exc:
            failed += 1
            try:
                supabase_patch(
                    "telegram_subscription_reminder_log",
                    {"id": f"eq.{log_id}"},
                    {"status": "failed", "error": str(exc)[:1000]},
                )
            except Exception as log_exc:
                print(f"[error] unable to update failure log: {log_exc}")
            print(f"[error] send failed user={sub['user_id']}: {exc}")
        time.sleep(0.15)

    print(f"[summary] sent={sent} failed={failed} skipped_no_private_chat={skipped}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[fatal] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
