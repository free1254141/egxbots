"""
jobs/send_founders_final_48h_emails.py — Scheduled Final-48-Hours FOMO Campaign Dispatcher
for the 100 EGP Founders Offer (expiring 2026-11-14T01:00:00Z, after which Pro returns to 200 EGP).

Automatically activates only during the final 48 hours before `founders_offer_ends_at()`
(Nov 12 & Nov 13, 2026) unless `--force` is passed.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from api.stock_ai import _init_supabase, supabase
from api.payment_common import founders_offer_ends_at
from api.marketing_lifecycle import (
    APP_URL,
    MARKETING_DAILY_EMAIL_CAP,
    _build_email_html,
    get_daily_sent_count,
    get_user_email,
    has_recent_message,
    is_user_unsubscribed,
    record_marketing_message,
    send_resend_email,
)

MESSAGE_TYPE = "founders_final_48h"
DEFAULT_ENDS_AT = datetime(2026, 11, 14, 1, 0, 0, tzinfo=timezone.utc)


def get_offer_hours_remaining(now: datetime | None = None) -> float:
    """Return hours remaining until the 100 EGP Founders offer expires."""
    now_dt = now or datetime.now(timezone.utc)
    ends_dt = founders_offer_ends_at() or DEFAULT_ENDS_AT
    return (ends_dt - now_dt).total_seconds() / 3600.0


def is_within_final_48h_window(now: datetime | None = None, window_hours: float = 52.0) -> bool:
    """Return True if we are within the final 48h window (Nov 12-13, 2026) before expiry."""
    hours_left = get_offer_hours_remaining(now)
    return 0.0 < hours_left <= window_hours


def send_founders_final_48h_email(
    user_id: str,
    email: str,
    display_name: str,
    hours_left: int,
    is_trial_or_warm: bool = False,
) -> bool:
    """Sends the final 48-hour scarcity email before monthly Pro returns from 100 EGP to 200 EGP."""
    if is_user_unsubscribed(user_id, email) or has_recent_message(user_id, MESSAGE_TYPE, cooldown_days=14):
        return False

    hrs_display = max(1, min(48, int(round(hours_left))))
    time_badge = "أقل من 24 ساعة" if hrs_display <= 24 else f"{hrs_display} ساعة فقط"
    subject = f"⏳ باقي {time_badge}: آخر فرصة لتثبيت اشتراك EGX BOTS Pro بـ 100 ج.م قبل العودة لـ 200 ج.م"
    greeting = f"أهلاً {display_name} 👋"

    intro = (
        "نود تذكيرك بأنك قمت بتجربة منصة <strong>EGX BOTS</strong> مؤخراً، وأمامك الآن <strong>الفرصة الأخيرة</strong> لتثبيت سعر المؤسسين المخفض على حسابك قبل إغلاق العرض نهائياً."
        if is_trial_or_warm
        else "تنبيه هام قبل إغلاق باب عرض المؤسسين الأوائل على منصة <strong>EGX BOTS</strong> وعودة التسعير الرسمي."
    )

    paragraphs = [
        intro,
        f"⏰ <strong>يتبقى {time_badge} فقط (حتى يوم 14 نوفمبر):</strong><br/>"
        "ينتهي عرض الـ <strong>100 ج.م شهرياً</strong> ويعود سعر الاشتراك الشهري تلقائياً إلى السعر الرسمي <strong>(200 ج.م شهرياً)</strong> لأي مشترك جديد.",
        "🔒 <strong>ميزة تثبيت السعر مدى الحياة (Grandfather Lock):</strong><br/>"
        "كل من يفعّل اشتراكه قبل انتهاء العداد يحتفظ بسعر <strong>100 ج.م شهرياً مدى الحياة</strong> عند التجديد (بدلاً من 200 ج.م)، بالإضافة إلى فتح كافة المزايا فوراً:<br/>"
        "• <strong>إشارات المدى القصير والمتوسط واللحظي (Short & Medium Swings)</strong> بدون حجب أو تأخير.<br/>"
        "• <strong>قناة تليجرام VIP الفورية</strong> ورادار السيولة الذكية والاختراقات لحظة بلحظة.<br/>"
        "• <strong>350 رسالة ذكاء اصطناعي شهرياً</strong> لتحليل الأسهم، مستويات الدخول، ورفع لقطات المحفظة والشارت (Vision AI).",
        "💡 <em>تفعيل فوري بضغطة زر عبر فودافون كاش أو انستاباي أو البطاقات البنكية عبر بوابة EasyKash المعتمدة.</em>",
    ]

    cta_text = f"🔥 ثبّت اشتراكك بـ 100 ج.م الآن (قبل العودة لـ 200 ج.م)"
    cta_url = f"{APP_URL}/pricing?plan=pro&from=final_48h"
    message_id = str(uuid.uuid4())

    html = _build_email_html(
        subject,
        greeting,
        paragraphs,
        cta_text,
        cta_url,
        user_id,
        email,
        campaign=MESSAGE_TYPE,
        message_id=message_id,
    )
    send_meta: Dict[str, Any] = {}
    if send_resend_email(email, subject, html, out=send_meta):
        record_marketing_message(
            user_id,
            email,
            MESSAGE_TYPE,
            {"hours_left": hrs_display, "warm_lead": is_trial_or_warm},
            message_id=message_id,
            provider_message_id=send_meta.get("provider_message_id"),
        )
        return True
    return False


def dispatch_final_48h_campaign(
    max_emails: int = 45,
    dry_run: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Dispatches the Final-48-Hours FOMO email batch if within the scheduled window
    (Nov 12 & Nov 13, 2026) or when `force=True`.
    """
    _init_supabase()
    now = datetime.now(timezone.utc)
    hours_left = get_offer_hours_remaining(now)
    in_window = is_within_final_48h_window(now)

    results: Dict[str, Any] = {
        "dry_run": dry_run,
        "force": force,
        "in_scheduled_window": in_window,
        "hours_remaining": round(hours_left, 2),
        "warm_leads_sent": 0,
        "free_users_sent": 0,
        "total_sent": 0,
        "skipped": 0,
    }

    if not in_window and not force:
        print(
            f"[FINAL-48H] Outside scheduled 48h window (hours_remaining={hours_left:.1f}h). "
            "Standing by until Nov 12–13, 2026 (or pass --force to override)."
        )
        return results

    if hours_left <= 0 and not force:
        print("[FINAL-48H] Offer has already expired. Skipping dispatch.")
        return results

    daily_count = get_daily_sent_count()
    remaining_quota = max(0, MARKETING_DAILY_EMAIL_CAP - daily_count)
    limit_for_this_run = min(max_emails, remaining_quota)
    results["remaining_daily_cap"] = remaining_quota

    if limit_for_this_run <= 0:
        print(f"[FINAL-48H] Daily email cap reached ({daily_count}/{MARKETING_DAILY_EMAIL_CAP}).")
        return results

    # Pre-fetch emails from Auth admin API
    email_map: Dict[str, str] = {}
    try:
        page = 1
        while True:
            resp = supabase.auth.admin.list_users(page=page, per_page=100)
            users = resp.users if hasattr(resp, "users") else (resp if isinstance(resp, list) else [])
            if not users:
                break
            for u in users:
                uid = str(getattr(u, "id", None) or (u.get("id") if isinstance(u, dict) else None))
                em = str(getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else "") or "").strip().lower()
                if em and "@" in em:
                    email_map[uid] = em
            if len(users) < 100:
                break
            page += 1
    except Exception as exc:
        print(f"[FINAL-48H] Warning: bulk email prefetch fallback: {exc}")

    # Exclude active Pro/Lifetime subscribers
    paid_subs = (
        supabase.table("subscriptions")
        .select("user_id")
        .eq("status", "active")
        .in_("plan_id", ["pro", "lifetime", "pro_lifetime"])
        .execute()
        .data
        or []
    )
    paid_uids = {s["user_id"] for s in paid_subs if s.get("user_id")}

    # Exclude users who already received `founders_final_48h`
    already_sent_rows = (
        supabase.table("marketing_message_log")
        .select("user_id")
        .eq("message_type", MESSAGE_TYPE)
        .execute()
        .data
        or []
    )
    already_sent_uids = {r["user_id"] for r in already_sent_rows if r.get("user_id")}

    # Identify warm leads: trialing users, expired subscribers, and pending checkout users
    trial_rows = (
        supabase.table("subscriptions")
        .select("user_id")
        .in_("status", ["trialing", "canceled", "expired"])
        .limit(100)
        .execute()
        .data
        or []
    )
    pending_orders = (
        supabase.table("local_payment_orders")
        .select("user_id")
        .in_("status", ["pending", "expired"])
        .limit(100)
        .execute()
        .data
        or []
    )
    warm_uids: List[str] = []
    for r in trial_rows + pending_orders:
        uid = r.get("user_id")
        if uid and uid not in paid_uids and uid not in already_sent_uids and uid not in warm_uids:
            warm_uids.append(uid)

    # Fetch active free profiles ordered by recent activity
    recent_profiles = (
        supabase.table("profiles")
        .select("id, username, display_name, updated_at")
        .order("updated_at", desc=True)
        .limit(500)
        .execute()
        .data
        or []
    )
    profile_map = {p["id"]: p for p in recent_profiles if p.get("id")}

    fake_patterns = [
        "@example.", "@test.", "test@", "test1@", "test2@", "weeeenew",
        "fakeuse", "fakebot", "ghgfhgfh", "123456", "asdfgh", ".cim",
    ]
    excluded_emails = {"user@gmail.com", "weeessd57@gmail.com"}

    ordered_candidates: List[tuple[str, bool]] = [(uid, True) for uid in warm_uids]
    for p in recent_profiles:
        uid = p.get("id")
        if uid and uid not in paid_uids and uid not in already_sent_uids and uid not in warm_uids:
            ordered_candidates.append((uid, False))

    sent_this_run = 0
    hrs_int = max(1, int(round(hours_left if hours_left > 0 else 48)))

    for uid, is_warm in ordered_candidates:
        if sent_this_run >= limit_for_this_run:
            break
        email = email_map.get(uid) or get_user_email(uid)
        if not email or "@" not in email:
            continue
        if email.lower() in excluded_emails or any(pat in email.lower() for pat in fake_patterns):
            continue
        if is_user_unsubscribed(uid, email):
            results["skipped"] += 1
            continue

        p = profile_map.get(uid) or {}
        dname = p.get("display_name") or p.get("username") or "صديقنا العزيز"

        if dry_run:
            tag = "WARM-LEAD" if is_warm else "FREE-USER"
            print(f"[DRY-RUN][{tag}] Would send Final-48h email to: {email} ({dname})", flush=True)
            if is_warm:
                results["warm_leads_sent"] += 1
            else:
                results["free_users_sent"] += 1
            results["total_sent"] += 1
            sent_this_run += 1
        else:
            ok = send_founders_final_48h_email(uid, email, dname, hrs_int, is_trial_or_warm=is_warm)
            if ok:
                if is_warm:
                    results["warm_leads_sent"] += 1
                else:
                    results["free_users_sent"] += 1
                results["total_sent"] += 1
                sent_this_run += 1
                print(f"[SENT] Final-48h email sent to: {email} ({dname})", flush=True)
            time.sleep(0.5)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EGX BOTS Final-48h Founders Offer Email Dispatcher")
    parser.add_argument("--send", action="store_true", help="Execute live email sending")
    parser.add_argument("--force", action="store_true", help="Bypass the 48-hour date window guard")
    parser.add_argument("--max", type=int, default=45, help="Maximum emails to send in this run")
    args = parser.parse_args()

    res = dispatch_final_48h_campaign(
        max_emails=args.max,
        dry_run=not args.send,
        force=args.force,
    )
    print(f"\n[FINAL-48H] Summary: {res}")
