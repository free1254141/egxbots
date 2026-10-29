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
    send_meta: Dict[str, Any] = {}
    if send_resend_email(email, subject, html, out=send_meta):
        record_marketing_message(
            user_id,
            email,
            "renewal_reminder",
            {"days_left": days_left, "end_date": end_date},
            provider_message_id=send_meta.get("provider_message_id")
        )
        return True
    return False


def send_expired_reactivation_email(user_id: str, email: str, display_name: str, end_date: str) -> bool:
    """Sends an urgent expired reactivation email to users whose subscription recently ended."""
    if is_user_unsubscribed(user_id, email) or has_recent_message(user_id, "expired_reactivation", cooldown_days=3):
        return False

    subject = "⚠️ تنبيه: انتهت صلاحية اشتراكك في EGX BOTS Pro - يمكنك إعادة التفعيل وتثبيت السعر (50 ج.م)"
    greeting = f"أهلاً {display_name} 👋"
    paragraphs = [
        f"نحيطك علماً بأن اشتراكك في <strong>باقة EGX BOTS PRO</strong> قد انتهى مؤخراً <strong>(بتاريخ {end_date[:10]})</strong>.",
        "لقد توقفت صلاحيات الوصول إلى <strong>مساعد الشات بوت الذكي (AI Chatbot)، إشارات ونماذج السوينج الفنية اللحظية، مستويات المراقبة، وقناة التنبيهات الفنية VIP على تليجرام</strong>.",
        "💡 <strong>فرصة لتثبيت السعر:</strong> يمكنك إعادة تفعيل اشتراكك الآن والاحتفاظ بنفس سعر باقة المؤسسين المخفض <strong>(50 ج.م شهرياً مدى الحياة بدلاً من 200 ج.م)</strong> قبل اكتمال مقاعد الـ 100 مؤسس.",
    ]
    cta_text = "إعادة تفعيل الاشتراك وتثبيت السعر (50 ج.م)"
    cta_url = f"{APP_URL}/pricing?plan=pro"

    html = _build_email_html(subject, greeting, paragraphs, cta_text, cta_url, user_id, email)
    send_meta: Dict[str, Any] = {}
    if send_resend_email(email, subject, html, out=send_meta):
        record_marketing_message(
            user_id,
            email,
            "expired_reactivation",
            {"end_date": end_date},
            provider_message_id=send_meta.get("provider_message_id")
        )
        return True
    return False


def send_trial_onboarding_email(user_id: str, email: str, display_name: str, invite_link: str, end_date: str) -> bool:
    """Sends a targeted onboarding and activation email to a trialing user."""
    if is_user_unsubscribed(user_id, email) or has_recent_message(user_id, "trial_onboarding", cooldown_days=2):
        return False

    subject = "🚀 تفعيل باقتك: رابط قناة VIP الخاصة بك وجرب الشات بوت الذكي الآن | EGX BOTS"
    greeting = f"أهلاً {display_name} 👋"
    paragraphs = [
        f"لاحظنا أنك قمت بتفعيل <strong>تجربة باقة Pro المجانية</strong> لمدة 3 أيام، ونود التأكد من حصولك على أقصى استفادة قبل انتهاء فترة التجربة <strong>(بتاريخ {end_date[:10]})</strong>.",
        f"1️⃣ <strong>رابط قناة التنبيهات الفنية VIP على تليجرام:</strong><br/>"
        f"انضم الآن لقناة التنبيهات اللحظية عبر الرابط المخصص لحسابك:<br/>"
        f"<a href='{invite_link}' style='color:#10b981;font-weight:bold;'>{invite_link}</a>",
        "2️⃣ <strong>جرب الشات بوت الذكي الآن:</strong><br/>"
        "اسأل الشات بوت عن أي سهم في محفظتك بالبورصة المصرية ليحلل لك مستويات السيولة، نقاط الدعم والمقاومة، والاتجاه الفني لحظياً.",
        "💡 <strong>تثبيت السعر:</strong> يمكنك الاستمرار بنفس سعر باقة المؤسسين المخفض <strong>(50 ج.م شهرياً مدى الحياة بدلاً من 200 ج.م)</strong> قبل انتهاء الفترة التجريبية.",
    ]
    cta_text = "بدء استخدام الشات بوت وفحص الأسهم"
    cta_url = f"{APP_URL}/ai-chat"

    html = _build_email_html(subject, greeting, paragraphs, cta_text, cta_url, user_id, email)
    send_meta: Dict[str, Any] = {}
    if send_resend_email(email, subject, html, out=send_meta):
        record_marketing_message(
            user_id,
            email,
            "trial_onboarding",
            {"invite_link": invite_link, "end_date": end_date},
            provider_message_id=send_meta.get("provider_message_id")
        )
        return True
    return False


def send_founders_offer_email(user_id: str, email: str, display_name: str) -> bool:
    """Sends the high-converting 3-Day Pro Trial & Founders scarcity email to active free users."""
    if is_user_unsubscribed(user_id, email) or has_recent_message(user_id, "founders_offer", cooldown_days=7):
        return False

    subject = "🎁 هديتك من EGX BOTS: تفعيل باقة Pro مجاناً لمدة 3 أيام (بدون دفع وبدون بطاقة)"
    greeting = f"أهلاً {display_name} 👋"
    paragraphs = [
        "يسعدنا تواجدك معنا في منصة <strong>EGX BOTS</strong>. ولأننا نؤمن أن التجربة العملية هي أفضل برهان للمتداول، يسعدنا أن نهديك <strong>تفعيل باقة Pro مجاناً بالكامل لمدة 3 أيام</strong> بضغطة زر واحدة — بدون أي دفع مسبق وبدون طلب بطاقة بنكية.",
        "🚀 <strong>ما الذي يمكنك تجربته واستكشافه فوراً خلال الـ 3 أيام؟</strong><br/>"
        "• <strong>فحص أي سهم مصري عبر الشات بوت الذكي:</strong> اسأل الشات بوت عن أي سهم بالبورصة المصرية ليحلل لك مستويات السيولة، نقاط الدعم والمقاومة، والاتجاه الفني لحظياً.<br/>"
        "• <strong>ماسح السيولة الذكية والنماذج الفنية:</strong> رصد رقمي ومؤتمت لمستويات المراقبة الفنية والأهداف السعرية الاسترشادية وحركة التجميع بالبورصة المصرية.<br/>"
        "• <strong>قناة التنبيهات الفنية VIP على تليجرام:</strong> إشعارات رقمية مباشرة لاكتمال النماذج الفنية لحظياً عبر تليجرام.",
        "💡 <strong>عرض تثبيت السعر (50 ج.م):</strong> إذا نالت أدوات ومزايا Pro إعجابك خلال فترة التجربة، يمكنك تثبيت اشتراكك بسعر باقة المؤسسين المخفض <strong>(50 ج.م فقط شهرياً مدى الحياة بدلاً من 200 ج.م)</strong> قبل اكتمال مقاعد الـ 100 مؤسس الأولى.",
    ]
    cta_text = "⚡ تفعيل باقة Pro المجانية الآن (0 ج.م)"
    cta_url = f"{APP_URL}/pricing?plan=pro&trial=true"

    html = _build_email_html(subject, greeting, paragraphs, cta_text, cta_url, user_id, email)
    send_meta: Dict[str, Any] = {}
    if send_resend_email(email, subject, html, out=send_meta):
        record_marketing_message(
            user_id,
            email,
            "founders_offer",
            {"channel": "email", "version": "free_trial_v2"},
            provider_message_id=send_meta.get("provider_message_id")
        )
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
        "expired_sent": 0,
        "onboarding_sent": 0,
        "founders_sent": 0,
        "skipped": 0,
        "remaining_daily_cap": remaining_quota,
    }

    if limit_for_this_run <= 0:
        print(f"[CAMPAIGN-EMAIL] Daily cap reached ({daily_count}/{MARKETING_DAILY_EMAIL_CAP}).")
        return results

    now = datetime.now(timezone.utc)

    # Pre-fetch email map to eliminate hundreds of individual RPC network calls
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
    except Exception as e:
        print(f"[CAMPAIGN-EMAIL] Warning: bulk email prefetch fallback: {e}")

    # 1. Active Pro subscriptions to exclude from Founders offer and identify renewals
    paid_subs = supabase.table("subscriptions").select("id, user_id, plan_id, status, current_period_end").eq("status", "active").execute().data or []
    paid_uids = {s["user_id"] for s in paid_subs}

    # Pre-fetch recent marketing logs to avoid hundreds of individual RPC/table calls
    cutoff_7d = (now - timedelta(days=7)).isoformat()
    recent_logs = supabase.table("marketing_message_log").select("user_id").gte("sent_at", cutoff_7d).execute().data or []
    recently_contacted_uids = {r["user_id"] for r in recent_logs}

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
            email = email_map.get(uid) or get_user_email(uid)
            if not email or "@" not in email:
                continue
            if email.lower() in ["user@gmail.com", "weeessd57@gmail.com"]:
                continue
            if is_user_unsubscribed(uid, email) or uid in recently_contacted_uids:
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

    # 3. Priority A2: Active Trialing Users needing onboarding & VIP invite
    trialing_subs = (
        supabase.table("subscriptions")
        .select("id, user_id, plan_id, status, current_period_end")
        .eq("status", "trialing")
        .execute()
        .data or []
    )
    for tsub in trialing_subs:
        if sent_this_run >= limit_for_this_run:
            break
        t_uid = tsub["user_id"]
        t_end = tsub.get("current_period_end") or ""
        if not t_end:
            continue
        try:
            t_end_dt = datetime.fromisoformat(t_end.replace("Z", "+00:00"))
            if t_end_dt < now:
                continue
        except Exception:
            continue
        t_email = email_map.get(t_uid) or get_user_email(t_uid)
        if not t_email or "@" not in t_email or is_user_unsubscribed(t_uid, t_email):
            continue
        if has_recent_message(t_uid, "trial_onboarding", cooldown_days=2):
            continue
        # get VIP invite link
        inv_row = supabase.table("pro_telegram_invites").select("invite_link").eq("user_id", t_uid).maybe_single().execute().data or {}
        inv_link = inv_row.get("invite_link") or "https://t.me/egxbots"
        t_prof = supabase.table("profiles").select("display_name, username").eq("id", t_uid).maybe_single().execute().data or {}
        t_name = t_prof.get("display_name") or t_prof.get("username") or "صديقنا العزيز"

        if dry_run:
            print(f"[DRY-RUN] Would send Trial Onboarding email to: {t_email} ({t_name})", flush=True)
            results["onboarding_sent"] += 1
            sent_this_run += 1
        else:
            ok = send_trial_onboarding_email(t_uid, t_email, t_name, inv_link, t_end)
            if ok:
                results["onboarding_sent"] += 1
                sent_this_run += 1
                print(f"[SENT] Trial Onboarding email sent to: {t_email} ({t_name})", flush=True)
            time.sleep(0.5)

    # 4. Priority B: Recently Expired Subscriptions (ended in last 4 days, not renewed)
    expired_subs = (
        supabase.table("subscriptions")
        .select("id, user_id, plan_id, status, current_period_end")
        .in_("status", ["canceled", "expired"])
        .order("current_period_end", desc=True)
        .limit(20)
        .execute()
        .data or []
    )
    for sub in expired_subs:
        if sent_this_run >= limit_for_this_run:
            break
        uid = sub["user_id"]
        if uid in paid_uids:
            continue
        end_str = sub.get("current_period_end")
        if not end_str:
            continue
        try:
            end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        except Exception:
            continue
        days_ago = (now.date() - end_dt.date()).days
        if 0 <= days_ago <= 4:
            email = email_map.get(uid) or get_user_email(uid)
            if not email or "@" not in email:
                continue
            if is_user_unsubscribed(uid, email) or has_recent_message(uid, "expired_reactivation", cooldown_days=3):
                continue
            prof = supabase.table("profiles").select("display_name, username").eq("id", uid).maybe_single().execute().data or {}
            dname = prof.get("display_name") or prof.get("username") or "صديقنا العزيز"

            if dry_run:
                print(f"[DRY-RUN] Would send Expired Reactivation email to: {email} ({dname}) - Expired {days_ago} days ago", flush=True)
                results["expired_sent"] += 1
                sent_this_run += 1
            else:
                ok = send_expired_reactivation_email(uid, email, dname, end_str)
                if ok:
                    results["expired_sent"] += 1
                    sent_this_run += 1
                    print(f"[SENT] Expired Reactivation email sent to: {email} ({dname})", flush=True)
                time.sleep(0.5)

    # 4. Priority C: Active Non-Pro Users (Targeted for Founders Offer)
    recent_profiles = (
        supabase.table("profiles")
        .select("id, username, display_name, updated_at")
        .order("updated_at", desc=True)
        .limit(500)
        .execute()
        .data or []
    )

    for p in recent_profiles:
        if sent_this_run >= limit_for_this_run:
            break
        uid = p["id"]
        if uid in paid_uids or uid in recently_contacted_uids:
            continue

        email = email_map.get(uid) or get_user_email(uid)
        if not email or "@" not in email:
            continue

        # Filter out test domains, known bad addresses, and admin accounts
        fake_patterns = ["@example.", "@test.", "test@", "test1@", "test2@", "weeeenew", "fakeuse", "fakebot", "ghgfhgfh", "123456", "asdfgh", ".cim"]
        if any(pat in email.lower() for pat in fake_patterns):
            continue
        if email.lower() in ["user@gmail.com", "weeessd57@gmail.com"]:
            continue

        if is_user_unsubscribed(uid, email):
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
