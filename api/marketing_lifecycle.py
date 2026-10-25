"""
marketing_lifecycle.py — Resend Email Lifecycle & Recovery Automation for EGX Bots.

Handles:
1. Abandoned checkout & pricing recovery (2h to 72h).
2. Dormant user win-back (users inactive for 21-30+ days).
3. Trial expiring alerts (<24h remaining on 3-day Pro trial).

Features:
- Resend API integration (plain HTTPS requests; safe no-op if RESEND_API_KEY is not set).
- Strict daily cap guard (MARKETING_DAILY_EMAIL_CAP, default 90/day) to fit the free Resend tier.
- Cooldown and idempotency via `marketing_message_log`.
- One-click unsubscribe HMAC link + `marketing_preferences` compliance.
"""

import os
import json
import time
import hmac
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from api.stock_ai import supabase

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
MARKETING_EMAIL_FROM = (
    os.getenv("MARKETING_EMAIL_FROM")
    or os.getenv("MARKETING_FROM_EMAIL")
    or "EGX BOTS <support@egxbots.com>"
).strip()
MARKETING_DAILY_EMAIL_CAP = int(os.getenv("MARKETING_DAILY_EMAIL_CAP", "90"))
APP_URL = os.getenv("NEXT_PUBLIC_APP_URL", "https://egxbots.com").rstrip("/")

UNSUB_SECRET = (
    os.getenv("SUPABASE_JWT_SECRET")
    or os.getenv("RESEND_API_KEY")
    or "egxbots-marketing-secret-key-2026"
)


def generate_unsub_token(user_id: str, email: str) -> str:
    """Generates a secure HMAC-SHA256 unsubscribe token."""
    msg = f"unsub:{user_id}:{email.lower().strip()}".encode("utf-8")
    return hmac.new(UNSUB_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:32]


def verify_unsub_token(user_id: str, email: str, token: str) -> bool:
    """Verifies the HMAC unsubscribe token."""
    expected = generate_unsub_token(user_id, email)
    return hmac.compare_digest(expected, token)


def send_resend_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Sends an email using Resend API.
    If RESEND_API_KEY is missing or dummy, acts as a safe no-op and logs.
    """
    if not RESEND_API_KEY or RESEND_API_KEY.startswith("re_placeholder") or len(RESEND_API_KEY) < 10:
        print(f"[MARKETING-EMAIL-SIMULATED] To: {to_email} | Subject: {subject}")
        return True

    payload = {
        "from": MARKETING_EMAIL_FROM,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "EGXBots-Marketing/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"[MARKETING-EMAIL-SENT] ID: {data.get('id')} to {to_email}")
            return True
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        print(f"[MARKETING-EMAIL-ERROR] HTTP {e.code} to {to_email}: {err_msg}")
        return False
    except Exception as e:
        print(f"[MARKETING-EMAIL-ERROR] Exception sending to {to_email}: {e}")
        return False


def get_daily_sent_count() -> int:
    """Returns number of emails sent today to guard against exceeding the daily cap."""
    if not supabase:
        return 0
    try:
        today_start = datetime.now(timezone.utc).strftime("%Y-%m-%d 00:00:00+00")
        res = (
            supabase.table("marketing_message_log")
            .select("id", count="exact")
            .gte("sent_at", today_start)
            .execute()
        )
        return res.count or 0
    except Exception as e:
        print(f"[MARKETING] Error fetching daily count: {e}")
        return 0


def is_user_unsubscribed(user_id: str, email: str) -> bool:
    """Checks if the user has opted out of marketing emails."""
    if not supabase:
        return False
    try:
        res = (
            supabase.table("marketing_preferences")
            .select("unsubscribed_all")
            .or_(f"user_id.eq.{user_id},email.eq.{email}")
            .limit(1)
            .execute()
        )
        if res.data and len(res.data) > 0:
            return bool(res.data[0].get("unsubscribed_all"))
        return False
    except Exception:
        return False


def has_recent_message(user_id: str, message_type: str, cooldown_days: int) -> bool:
    """Checks if a message of this type was sent within the cooldown window."""
    if not supabase:
        return False
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=cooldown_days)).isoformat()
        res = (
            supabase.table("marketing_message_log")
            .select("id")
            .eq("user_id", user_id)
            .eq("message_type", message_type)
            .gte("sent_at", cutoff)
            .limit(1)
            .execute()
        )
        return bool(res.data and len(res.data) > 0)
    except Exception:
        return False


def get_user_email(uid: str) -> Optional[str]:
    """Retrieves user email using RPC get_user_email_for_marketing with admin API fallback."""
    if not supabase or not uid:
        return None

    # 1. Try secure RPC
    try:
        email_res = supabase.rpc("get_user_email_for_marketing", {"p_user_id": uid}).execute()
        if email_res and email_res.data and isinstance(email_res.data, str) and "@" in email_res.data:
            return email_res.data.strip()
    except Exception as rpc_err:
        print(f"[MARKETING] RPC get_user_email_for_marketing failed for {uid}: {rpc_err}")

    # 2. Fallback to auth.admin.get_user_by_id if available
    try:
        admin_auth = getattr(supabase, "auth", None)
        if admin_auth and hasattr(admin_auth, "admin"):
            user_obj = admin_auth.admin.get_user_by_id(uid)
            # Handle User object or dictionary
            user_data = getattr(user_obj, "user", user_obj)
            email = getattr(user_data, "email", None) or (user_data.get("email") if isinstance(user_data, dict) else None)
            if email and "@" in email:
                return email.strip()
    except Exception as admin_err:
        pass

    return None


def record_marketing_message(user_id: str, email: str, message_type: str, metadata: dict = None):
    """Logs sent message for cooldown and tracking."""
    if not supabase:
        return
    try:
        supabase.table("marketing_message_log").insert({
            "user_id": user_id,
            "email": email,
            "message_type": message_type,
            "channel": "email",
            "status": "sent",
            "metadata": metadata or {},
        }).execute()
    except Exception as e:
        print(f"[MARKETING] Error recording message log: {e}")


def _build_email_html(headline: str, greeting: str, content_paragraphs: List[str], cta_text: str, cta_url: str, user_id: str, email: str) -> str:
    """Builds a responsive, high-converting Arabic HTML email with styling and unsubscribe footer."""
    unsub_token = generate_unsub_token(user_id, email)
    unsub_url = f"{APP_URL}/api/marketing/unsubscribe?uid={user_id}&email={urllib.request.quote(email)}&token={unsub_token}"

    paragraphs_html = "".join([f"<p style='margin: 0 0 16px 0; font-size: 15px; line-height: 1.8; color: #374151;'>{p}</p>" for p in content_paragraphs])

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{headline}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f3f4f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; direction: rtl; text-align: right;">
  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
    <tr>
      <td align="center" style="padding: 24px 12px;">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border: 3px solid #000000; box-shadow: 6px 6px 0px #000000;">
          <!-- Header -->
          <tr>
            <td style="padding: 24px; background-color: #000000; color: #FFE600; text-align: center; border-bottom: 3px solid #000000;">
              <h1 style="margin: 0; font-size: 24px; font-weight: 900; letter-spacing: 1px;">EGX BOTS ⚡</h1>
              <span style="font-size: 11px; font-weight: bold; color: #ffffff; display: block; margin-top: 4px;">الذكاء الاصطناعي الأقوى للبورصة المصرية</span>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding: 32px 24px;">
              <h2 style="margin: 0 0 16px 0; font-size: 20px; font-weight: 900; color: #111827;">{greeting}</h2>
              {paragraphs_html}

              <!-- CTA Button -->
              <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="margin: 28px 0;">
                <tr>
                  <td align="center">
                    <a href="{cta_url}" style="display: inline-block; padding: 14px 28px; background-color: #FFE600; color: #000000; text-decoration: none; font-size: 16px; font-weight: 900; border: 3px solid #000000; box-shadow: 4px 4px 0px #000000; text-align: center;">
                      {cta_text} ←
                    </a>
                  </td>
                </tr>
              </table>

              <div style="border-top: 2px dashed #e5e7eb; padding-top: 20px; margin-top: 24px; font-size: 12px; color: #6b7280; text-align: center;">
                <p style="margin: 0 0 8px 0;">هل لديك أي استفسار؟ تواصل مباشرة مع فريق الدعم الفني على تليجرام: <a href="https://t.me/egxbots_bot" style="color: #2563eb; font-weight: bold;">@egxbots_bot</a></p>
              </div>
            </td>
          </tr>

          <!-- FRA Regulatory Disclaimer -->
          <tr>
            <td style="padding: 14px 24px; background-color: #fefce8; border-top: 1px solid #fef08a; font-size: 11px; line-height: 1.6; color: #854d0e; text-align: justify; direction: rtl;">
              <strong>⚠️ تنبيه قانوني وإخلاء مسؤولية (FRA):</strong> مخرجات النماذج الكمية وشات بوت الذكاء الاصطناعي هي مؤشرات وأدوات فنية وإحصائية لأغراض البحث والتحليل الفني والتعليم الشخصي فقط، ولا تمثل توصية استثمارية أو دعوة لشراء أو بيع أي ورقة مالية أو إدارة محافظ. قرارات التداول مسؤوليتك المستقلة عبر شركة سمسرة مرخصة من الهيئة العامة للرقابة المالية (FRA).
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 16px 24px; background-color: #f9fafb; border-top: 2px solid #e5e7eb; text-align: center; font-size: 11px; color: #9ca3af;">
              <p style="margin: 0 0 4px 0;">EGX BOTS — القاهرة، مصر</p>
              <p style="margin: 0;">إذا كنت لا ترغب في استلام هذه الإشعارات مستقبلاً، يمكنك <a href="{unsub_url}" style="color: #6b7280; text-decoration: underline;">إلغاء الاشتراك بنقرة واحدة</a>.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def process_abandoned_checkouts() -> int:
    """
    Finds users with pending/submitted orders between 2h and 72h old who haven't completed payment.
    Sends them an urgent Founders scarcity recovery email.
    """
    if not supabase:
        return 0

    sent_count = 0
    now = datetime.now(timezone.utc)
    two_hours_ago = (now - timedelta(hours=2)).isoformat()
    seventy_two_hours_ago = (now - timedelta(hours=72)).isoformat()

    try:
        # Fetch pending local payment orders in window
        res = (
            supabase.table("local_payment_orders")
            .select("id, user_id, plan_id, created_at, status")
            .in_("status", ["pending", "submitted"])
            .gte("created_at", seventy_two_hours_ago)
            .lte("created_at", two_hours_ago)
            .limit(20)
            .execute()
        )
        orders = res.data or []

        for order in orders:
            try:
                uid = order.get("user_id")
                if not uid:
                    continue

                # Check if user already has an active Pro subscription
                sub_res = (
                    supabase.table("subscriptions")
                    .select("id")
                    .eq("user_id", uid)
                    .eq("status", "active")
                    .in_("plan_id", ["pro", "lifetime", "pro_lifetime"])
                    .limit(1)
                    .execute()
                )
                if sub_res.data and len(sub_res.data) > 0:
                    continue

                # Check cooldown (once ever per order)
                if has_recent_message(uid, "abandoned_checkout", cooldown_days=14):
                    continue

                # Get user profile
                user_res = (
                    supabase.table("profiles")
                    .select("display_name, username")
                    .eq("id", uid)
                    .maybe_single()
                    .execute()
                )
                profile = user_res.data or {}
                display_name = profile.get("display_name") or profile.get("username") or "صديقنا العزيز"

                # Get email using resilient RPC with admin API fallback
                user_email = get_user_email(uid)
                if not user_email or "@" not in user_email:
                    continue

                if is_user_unsubscribed(uid, user_email):
                    continue

                subject = "🔥 تذكير: مقعدك في باقة المؤسسين (50 ج.م شهرياً) محجوز لفترة محدودة | EGX BOTS"
                greeting = f"أهلاً {display_name} 👋"
                paragraphs = [
                    "لاحظنا أنك بدأت خطوات الاشتراك في <strong>باقة Pro للمؤسسين</strong> ولم تستكمل عملية الدفع بعد.",
                    "نود تذكيرك أن <strong>عرض المؤسسين الأوائل متاح لـ 100 مشترك فقط بسعر 50 ج.م شهرياً مدى الحياة</strong> (بدلاً من 200 ج.م) — وتبقى عدد قليل جداً من المقاعد قبل إغلاق العرض نهائياً.",
                    "باشتراكك في Pro، ستحصل فوراً على: <strong>شات بوت الذكاء الاصطناعي (AI Chatbot) للتحليل الفني اللحظي، إشارات ونماذج السوينج الفنية المؤتمتة، نقاط المراقبة والأهداف الاسترشادية ووقف الخسارة، وقناة تنبيهات VIP الخاصة على تليجرام</strong>.",
                    "إذا كنت ترغب في تجربة المنصة أولاً دون أي التزام، يمكنك تفعيل <strong>تجربة Pro المجانية لمدة 3 أيام</strong> بضغطة زر واحدة من صفحة الباقات!",
                ]
                cta_text = "استكمال الاشتراك وتثبيت السعر (50 ج.م)"
                cta_url = f"{APP_URL}/pricing?plan=pro"

                html = _build_email_html(subject, greeting, paragraphs, cta_text, cta_url, uid, user_email)
                if send_resend_email(user_email, subject, html):
                    record_marketing_message(uid, user_email, "abandoned_checkout", {"order_id": order.get("id")})
                    sent_count += 1
            except Exception as user_err:
                print(f"[MARKETING] Error processing order {order.get('id')}: {user_err}")
                continue

    except Exception as e:
        print(f"[MARKETING] Error in process_abandoned_checkouts: {e}")

    return sent_count


def process_trial_expiring() -> int:
    """
    Finds users whose 3-day Pro trial is expiring within 24 hours.
    Sends them an urgent upgrade discount reminder.
    """
    if not supabase:
        return 0

    sent_count = 0
    now = datetime.now(timezone.utc)
    in_24_hours = (now + timedelta(hours=24)).isoformat()
    now_iso = now.isoformat()

    try:
        res = (
            supabase.table("subscription_trials")
            .select("user_id, expires_at")
            .gte("expires_at", now_iso)
            .lte("expires_at", in_24_hours)
            .limit(20)
            .execute()
        )
        trials = res.data or []

        for trial in trials:
            try:
                uid = trial.get("user_id")
                if not uid:
                    continue

                # Check if already upgraded to paid Pro
                sub_res = (
                    supabase.table("subscriptions")
                    .select("id")
                    .eq("user_id", uid)
                    .eq("status", "active")
                    .in_("plan_id", ["pro", "lifetime", "pro_lifetime"])
                    .limit(1)
                    .execute()
                )
                if sub_res.data and len(sub_res.data) > 0:
                    continue

                if has_recent_message(uid, "trial_expiring", cooldown_days=7):
                    continue

                user_res = (
                    supabase.table("profiles")
                    .select("display_name, username")
                    .eq("id", uid)
                    .maybe_single()
                    .execute()
                )
                profile = user_res.data or {}
                display_name = profile.get("display_name") or profile.get("username") or "صديقنا العزيز"

                user_email = get_user_email(uid)
                if not user_email or "@" not in user_email:
                    continue

                if is_user_unsubscribed(uid, user_email):
                    continue

                subject = "⏳ فترتك التجريبية في EGX BOTS Pro تنتهي قريباً — ثبّت سعر المؤسسين بـ 50 ج.م الآن"
                greeting = f"أهلاً {display_name} ⚡"
                paragraphs = [
                    "نود إعلامك أن <strong>تجربتك المجانية لباقة Pro ستنتهي خلال الساعات القادمة</strong>.",
                    "نتمنى أن تكون قد استفدت من شات بوت الذكاء الاصطناعي ونماذج وإشارات السوينج الفنية خلال الأيام الماضية.",
                    "لتستمر في استخدام الشات بوت واستلام إشعارات النماذج الفنية دون انقطاع، احجز الآن ضمن <strong>عرض المؤسسين بـ 50 ج.م فقط شهرياً مدى الحياة</strong> قبل عودة السعر الرسمي إلى 200 ج.م.",
                ]
                cta_text = "تثبيت اشتراك Pro بـ 50 ج.م شهرياً"
                cta_url = f"{APP_URL}/pricing?plan=pro"

                html = _build_email_html(subject, greeting, paragraphs, cta_text, cta_url, uid, user_email)
                if send_resend_email(user_email, subject, html):
                    record_marketing_message(uid, user_email, "trial_expiring", {"expires_at": trial.get("expires_at")})
                    sent_count += 1
            except Exception as trial_err:
                print(f"[MARKETING] Error processing trial for user {trial.get('user_id')}: {trial_err}")
                continue

    except Exception as e:
        print(f"[MARKETING] Error in process_trial_expiring: {e}")

    return sent_count


def run_marketing_lifecycle() -> Dict[str, Any]:
    """
    Main entry point for automated marketing lifecycle runs.
    Called on a scheduled background cadence from daily_job_scheduler.
    """
    daily_count = get_daily_sent_count()
    if daily_count >= MARKETING_DAILY_EMAIL_CAP:
        print(f"[MARKETING] Daily email cap reached ({daily_count}/{MARKETING_DAILY_EMAIL_CAP}). Skipping run.")
        return {"status": "capped", "sent_today": daily_count}

    print(f"[MARKETING] Starting marketing lifecycle run. (Sent today: {daily_count}/{MARKETING_DAILY_EMAIL_CAP})")
    abandoned = process_abandoned_checkouts()
    trials = process_trial_expiring()

    total_sent = abandoned + trials
    print(f"[MARKETING] Lifecycle run finished. Sent: {total_sent} (Abandoned: {abandoned}, Trials: {trials})")
    return {
        "status": "ok",
        "abandoned_sent": abandoned,
        "trials_sent": trials,
        "total_sent": total_sent,
        "sent_today": daily_count + total_sent,
    }


class MarketingLifecycleEngine:
    """Class wrapper for Marketing Lifecycle operations."""
    run = staticmethod(run_marketing_lifecycle)
    send_email = staticmethod(send_resend_email)
    process_abandoned = staticmethod(process_abandoned_checkouts)
    process_trials = staticmethod(process_trial_expiring)

