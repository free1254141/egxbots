"""
jobs/send_new_signups_welcome.py — one-off deep welcome email for recent signups.

Default is a dry run. Pass --send to dispatch through Resend.
Respects unsubscribe, daily cap, and never emails a user twice for this campaign.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding="utf-8")

from api.stock_ai import supabase
try:
    from api.perf_utils import ALL_PAID_PLAN_IDS
except Exception:  # pragma: no cover
    ALL_PAID_PLAN_IDS = frozenset({"pro", "pro_6m", "pro_1y", "lifetime", "pro_lifetime", "chat_only", "vip_only"})
from api.marketing_lifecycle import (
    APP_URL,
    MARKETING_DAILY_EMAIL_CAP,
    _build_email_html,
    _build_tiers_summary_html,
    _resolve_user_pro_offer,
    get_daily_sent_count,
    get_user_email,
    has_recent_message,
    is_user_unsubscribed,
    record_marketing_message,
    send_resend_email,
)

CAMPAIGN = "signup_welcome_deep"
ADMIN_EMAILS = {"acursour@gmail.com", "weeeessd57@gmail.com", "weeeenew@gmail.com"}
BAD_MARKERS = ("example.", "test", "fake", "bgugvbhchj")


def mask(email: str) -> str:
    if not email or "@" not in email:
        return "-"
    local, domain = email.split("@", 1)
    return f"{local[:2]}***@{domain}"


def target_users(since: str, limit: int):
    profiles = (
        supabase.table("profiles")
        .select("id,created_at,display_name,username")
        .gte("created_at", since)
        .order("created_at", desc=True)
        .limit(500)
        .execute()
        .data or []
    )
    trial_ids = {
        row["user_id"]
        for row in (supabase.table("subscription_trials").select("user_id").execute().data or [])
    }
    paid_ids = {
        row["user_id"]
        for row in (
            supabase.table("subscriptions").select("user_id,plan_id,status")
            .eq("status", "active").execute().data or []
        )
        if str(row.get("plan_id") or "").lower() in ALL_PAID_PLAN_IDS
    }

    targets = []
    for profile in profiles:
        uid = profile["id"]
        email = get_user_email(uid)
        if not email or "@" not in email or email.lower() in ADMIN_EMAILS:
            continue
        if any(marker in email.lower() for marker in BAD_MARKERS):
            continue
        if uid in trial_ids or uid in paid_ids:
            continue
        if is_user_unsubscribed(uid, email):
            continue
        if has_recent_message(uid, CAMPAIGN, cooldown_days=30):
            continue
        targets.append({
            "user_id": uid,
            "email": email,
            "name": profile.get("display_name") or profile.get("username") or "صديقنا العزيز",
            "created_at": profile.get("created_at"),
        })
        if len(targets) >= limit:
            break
    return targets


def build_email(user_id: str, email: str, name: str) -> tuple[str, str]:
    pro_price, founder_tier = _resolve_user_pro_offer(user_id)
    subject = "أهلاً بيك في EGX BOTS 👋 — خطوتك الأولى لتحليل أسهم EGX وتاسي بالذكاء الاصطناعي"
    greeting = f"أهلاً {name} 🚀"
    paragraphs = [
        "حسابك في <strong>EGX BOTS</strong> جاهز. المنصة تقدم أدوات برمجية للتحليل الفني والكمي للبورصة المصرية (EGX) والسوق السعودي (TASI): شات بوت ذكاء اصطناعي يفهم أسهمك، رادار نماذج فنية، ومتابعة لمحفظتك في مكان واحد.",
        "<strong>ابدأ في 3 خطوات بسيطة:</strong><br/>"
        "1️⃣ افتح شات التحليل الفني ARTORO واسأل سؤالاً مباشراً: «اعرض لي أبرز 3 أسهم عليها زخم فني اليوم» أو «حلّل سهم COMI وحدّد مستويات الدعم والمقاومة».<br/>"
        "2️⃣ اربط حسابك بتيليجرام وخذ <strong>10 رسائل إضافية مجاناً</strong> وتابع من الموبايل.<br/>"
        "3️⃣ تابع الماسح الفني ومحفظتك لمعرفة مستويات المراقبة وإشارات السيولة أولاً بأول.",
        "<strong>إيه اللي بيميز التحليل عندنا؟</strong> كل قراءة فنية بتوصلك بمؤشرات رقمية واضحة: مستويات الدعم والمقاومة، القيمة العادلة، والتوافق الشرعي — مع تحقق فوري من حداثة البيانات.",
        _build_tiers_summary_html(pro_price, founder_tier),
    ]
    html = _build_email_html(
        subject,
        greeting,
        paragraphs,
        "افتح الشات واسأل أول سؤال",
        f"{APP_URL}/?chat=open&from=signup_welcome",
        user_id,
        email,
        CAMPAIGN,
    )
    return subject, html


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Dispatch for real (default: dry run)")
    parser.add_argument("--since", default=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat())
    parser.add_argument("--max", type=int, default=30)
    args = parser.parse_args()

    sent_today = get_daily_sent_count()
    remaining = max(0, MARKETING_DAILY_EMAIL_CAP - sent_today)
    targets = target_users(args.since, args.max)
    print(f"Mode: {'SEND' if args.send else 'DRY RUN'} | since={args.since[:19]} | targets={len(targets)} | "
          f"sent_today={sent_today}/{MARKETING_DAILY_EMAIL_CAP}")
    if remaining <= 0:
        print("Daily cap reached; aborting.")
        return 0

    sent = failed = 0
    for index, target in enumerate(targets[:remaining], 1):
        subject, html = build_email(target["user_id"], target["email"], target["name"])
        print(f"{index:02d}. {mask(target['email'])} | {target['created_at'][:10]} | {target['name'][:24]}")
        if not args.send:
            continue
        info: dict = {}
        if send_resend_email(target["email"], subject, html, info):
            record_marketing_message(
                target["user_id"], target["email"], CAMPAIGN,
                {"source": "new_signups_welcome"}, provider_message_id=info.get("provider_message_id"),
            )
            sent += 1
        else:
            failed += 1

    if args.send:
        print(f"\nDISPATCHED: sent={sent} failed={failed} skipped_over_cap={max(0, len(targets) - remaining)}")
    else:
        print("\nDry run only. Re-run with --send to dispatch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
