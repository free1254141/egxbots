"""
jobs/send_founders_emails.py — Email Campaign Dispatcher for 100 Founders Offer & Renewals.
Sends verified emails via Resend from: EGX BOTS <support@egxbots.com>
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

from api.stock_ai import supabase
from api.marketing_lifecycle import (
    send_resend_email,
    record_marketing_message,
    has_recent_message,
    is_user_unsubscribed,
    get_user_email,
    get_daily_sent_count,
    _build_email_html,
    APP_URL,
    MARKETING_DAILY_EMAIL_CAP,
)


def send_renewal_reminder_email(user_id: str, email: str, display_name: str, days_left: int, end_date: str) -> bool:
    """Sends a clear, urgent Pro renewal reminder email."""
    if is_user_unsubscribed(user_id, email) or has_recent_message(user_id, "renewal_reminder", cooldown_days=3):
        return False

    time_str = "غداً" if days_left <= 1 else f"خلال {days_left} أيام"
    subject = f"⏳ تذكير: ينتهي اشتراكك في EGX BOTS Pro {time_str} ({end_date[:10]})"
    greeting = f"أهلاً {display_name} 👋"
    paragraphs = [
        f"نود تذكيرك بأن اشتراكك الحالي في <strong>باقة EGX BOTS PRO</strong> سينتهي <strong>{time_str} (بتاريخ {end_date[:10]})</strong>.",
        "لضمان استمرار وصولك دون انقطاع إلى <strong>مساعد الشات بوت الذكي (AI Chatbot)، إشارات ونماذج السوينج الفنية اللحظية، مستويات المراقبة والأهداف السعرية الاسترشادية، وقناة التنبيهات الفنية على تليجرام</strong>، يمكنك تجديد اشتراكك الآن.",
        "💡 <strong>عرض خاص للمجددين:</strong> يمكنك الاستمرار بنفس سعر باقة المؤسسين المخفض <strong>(50 ج.م شهرياً مدى الحياة)</strong> بتجديد اشتراكك قبل انتهاء الفترة.",
    ]
    cta_text = "تجديد الاشتراك وتثبيت السعر (50 ج.م)"
    cta_url = f"{APP_URL}/pricing?plan=pro"

    html = _build_email_html(subject, greeting, paragraphs, cta_text, cta_url, user_id, email)
    if send_resend_email(email, subject, html):
        record_marketing_message(user_id, email, "renewal_reminder", {"days_left": days_left, "end_date": end_date})
        return True
    return False


def send_founders_offer_email(user_id: str, email: str, display_name: str) -> bool:
    """Sends the 100 Founders scarcity email to active free users."""
    if is_user_unsubscribed(user_id, email) or has_recent_message(user_id, "founders_offer", cooldown_days=7):
        return False

    subject = "⚡ عرض الـ 100 مؤسس الأوائل: باقة Pro بـ 50 ج.م شهرياً مدى الحياة | EGX BOTS"
    greeting = f"أهلاً {display_name} ⚡"
    paragraphs = [
        "يسعدنا تواجدك وتفاعلك معنا في منصة <strong>EGX BOTS</strong>.",
        "نود إعلامك أننا أطلقنا رسمياً <strong>عرض الـ 100 مؤسس الأوائل</strong>، والذي يمنحك اشتراك كامل في باقة Pro بسعر <strong>50 ج.م فقط شهرياً مدى الحياة</strong> (بدلاً من 200 ج.م).",
        "🎯 <strong>أدوات ومزايا باقة Pro الرقمية:</strong><br/>"
        "• <strong>مساعد الشات بوت الذكي (AI Chatbot):</strong> شات بوت متطور لتحليل أي سهم، فحص مستويات الدعم والمقاومة، ومقارنة الشركات لحظياً عبر الموقع وتليجرام (350 استفساراً شهرياً).<br/>"
        "• <strong>إشارات ونماذج السوينج الفنية:</strong> رصد رقمي ومؤتمت لمستويات المراقبة الفنية والأهداف السعرية الاسترشادية وإدارة المخاطر.<br/>"
        "• <strong>ماسح التجميع والسيولة الذكية:</strong> فحص كمي وإحصائي لحظي لحركة التداول بالبورصة المصرية.<br/>"
        "• <strong>قناة التنبيهات الفنية VIP:</strong> إشعارات رقمية مباشرة لاكتمال النماذج الفنية على تليجرام.<br/>"
        "• <strong>تثبيت السعر:</strong> مهما ارتفع سعر الاشتراك مستقبلاً، اشتراكك البرمجي ثابت بـ 50 ج.م شهرياً للأبد.",
        "🎁 <strong>تريد التجربة أولاً؟</strong> يمكنك تفعيل <strong>تجربة Pro المجانية لمدة 3 أيام</strong> بضغطة زر واحدة من صفحة الأسعار ودون أي التزام!",
    ]
    cta_text = "حجز مقعد المؤسسين بـ 50 ج.م شهرياً"
    cta_url = f"{APP_URL}/pricing?plan=pro"

    html = _build_email_html(subject, greeting, paragraphs, cta_text, cta_url, user_id, email)
    if send_resend_email(email, subject, html):
        record_marketing_message(user_id, email, "founders_offer", {"channel": "email"})
        return True
    return False


def dispatch_campaign_emails(max_emails: int = 40, dry_run: bool = True) -> Dict[str, Any]:
    """
    Main dispatcher for marketing & renewal emails.
    Respects daily caps, idempotency, and unsubscribes.
    """
    daily_count = get_daily_sent_count()
    remaining_quota = max(0, MARKETING_DAILY_EMAIL_CAP - daily_count)
    limit_for_this_run = min(max_emails, remaining_quota)

    results = {
        "dry_run": dry_run,
        "renewals_sent": 0,
        "founders_sent": 0,
        "skipped": 0,
        "remaining_daily_cap": remaining_quota,
    }

    if limit_for_this_run <= 0:
        print(f"[CAMPAIGN-EMAIL] Daily cap reached ({daily_count}/{MARKETING_DAILY_EMAIL_CAP}).")
        return results

    now = datetime.now(timezone.utc)

    # 1. Active Pro subscriptions to exclude from Founders offer and identify renewals
    paid_subs = supabase.table("subscriptions").select("id, user_id, plan_id, status, current_period_end").eq("status", "active").execute().data or []
    paid_uids = {s["user_id"] for s in paid_subs}

    sent_this_run = 0

    # 2. Priority A: Subscription Renewals (Ending in <= 7 days)
    for sub in paid_subs:
        if sent_this_run >= limit_for_this_run:
            break
        if sub.get("plan_id") in ["lifetime", "pro_lifetime"]:
            continue
        end_str = sub.get("current_period_end")
        if not end_str:
            continue
        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        days_left = (end_dt.date() - now.date()).days
        if days_left <= 7:
            uid = sub["user_id"]
            email = get_user_email(uid)
            if not email or "@" not in email:
                continue
            prof = supabase.table("profiles").select("display_name, username").eq("id", uid).maybe_single().execute().data or {}
            dname = prof.get("display_name") or prof.get("username") or "صديقنا العزيز"

            if dry_run:
                print(f"[DRY-RUN] Would send Renewal email to: {email} ({dname}) - Days left: {days_left}", flush=True)
                results["renewals_sent"] += 1
                sent_this_run += 1
            else:
                ok = send_renewal_reminder_email(uid, email, dname, days_left, end_str)
                if ok:
                    results["renewals_sent"] += 1
                    sent_this_run += 1
                    print(f"[SENT] Renewal email sent to: {email} ({dname})", flush=True)
                time.sleep(0.5)

    # 3. Priority B: Active Non-Pro Users (Targeted for Founders Offer)
    recent_profiles = (
        supabase.table("profiles")
        .select("id, username, display_name, updated_at")
        .order("updated_at", desc=True)
        .limit(100)
        .execute()
        .data or []
    )

    for p in recent_profiles:
        if sent_this_run >= limit_for_this_run:
            break
        uid = p["id"]
        if uid in paid_uids:
            continue

        email = get_user_email(uid)
        if not email or "@" not in email:
            continue

        dname = p.get("display_name") or p.get("username") or "صديقنا العزيز"

        if dry_run:
            print(f"[DRY-RUN] Would send Founders email to: {email} ({dname})", flush=True)
            results["founders_sent"] += 1
            sent_this_run += 1
        else:
            ok = send_founders_offer_email(uid, email, dname)
            if ok:
                results["founders_sent"] += 1
                sent_this_run += 1
                print(f"[SENT] Founders email sent to: {email} ({dname})", flush=True)
            time.sleep(0.5)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EGX BOTS Founders & Renewals Email Dispatcher")
    parser.add_argument("--send", action="store_true", help="Execute live email sending")
    parser.add_argument("--max", type=int, default=30, help="Maximum emails to send in this batch")
    args = parser.parse_args()

    res = dispatch_campaign_emails(max_emails=args.max, dry_run=not args.send)
    print(f"\n[CAMPAIGN-EMAIL] Results: {res}")
