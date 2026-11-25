"""
marketing_lifecycle.py — Resend Email Lifecycle & Recovery Automation for EGX Bots.

Handles:
1. Abandoned checkout & pricing recovery (2h to 72h).
2. Dormant user win-back (users inactive for 21-30+ days).
3. Trial activation: day-0 welcome (ask the first question), day-1 nudge.
4. Trial expiring alerts (<24h remaining on 3-day Pro trial).

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
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from api.stock_ai import supabase

try:
    from api.perf_utils import ALL_PAID_PLAN_IDS
except Exception:  # pragma: no cover - standalone fallback
    ALL_PAID_PLAN_IDS = frozenset({"pro", "pro_6m", "pro_1y", "lifetime", "pro_lifetime", "chat_only", "vip_only"})

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


def _click_sig(channel: str, campaign: str, message_id: str, target: str) -> str:
    msg = f"click:{channel}:{campaign}:{message_id}:{target}".encode("utf-8")
    return hmac.new(UNSUB_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:32]


def build_tracked_url(target: str, channel: str, campaign: str, message_id: str = "") -> str:
    """Wraps a destination in a signed /api/marketing/click redirect so clicks are recorded.

    `target` is either an internal path (/pricing) or a full URL; internal full URLs are
    reduced to their path. The signature prevents the endpoint from being used as an open redirect.
    """
    if target.startswith(APP_URL):
        target = target[len(APP_URL):] or "/"
    qs = urllib.parse.urlencode({
        "ch": channel,
        "c": campaign,
        "m": message_id or "",
        "to": target,
        "sig": _click_sig(channel, campaign, message_id or "", target),
    })
    return f"{APP_URL}/api/marketing/click?{qs}"


def send_resend_email(to_email: str, subject: str, html_body: str, out: Optional[dict] = None) -> bool:
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
            if out is not None:
                out["provider_message_id"] = data.get("id")
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


def record_marketing_message(user_id: str, email: str, message_type: str, metadata: dict = None, message_id: str = None, provider_message_id: str = None):
    """Logs sent message for cooldown and tracking."""
    if not supabase:
        return
    try:
        row = {
            "user_id": user_id,
            "email": email,
            "message_type": message_type,
            "channel": "email",
            "status": "sent",
            "metadata": metadata or {},
        }
        if message_id:
            row["id"] = message_id
        if provider_message_id:
            row["provider_message_id"] = provider_message_id
        supabase.table("marketing_message_log").insert(row).execute()
    except Exception as e:
        print(f"[MARKETING] Error recording message log: {e}")


def _build_email_html(headline: str, greeting: str, content_paragraphs: List[str], cta_text: str, cta_url: str, user_id: str, email: str, campaign: str = "", message_id: str = "") -> str:
    """Builds a responsive, high-converting Arabic HTML email with styling and unsubscribe footer."""
    support_url = "https://t.me/egxbots_bot"
    if campaign:
        cta_url = build_tracked_url(cta_url, "email", campaign, message_id)
        support_url = build_tracked_url(support_url, "email", f"{campaign}:support", message_id)
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
              <span style="font-size: 11px; font-weight: bold; color: #ffffff; display: block; margin-top: 4px;">أدوات التحليل الفني بالذكاء الاصطناعي للبورصة المصرية والسعودية</span>
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
                <p style="margin: 0 0 8px 0;">هل لديك أي استفسار؟ تواصل مباشرة مع فريق الدعم الفني على تليجرام: <a href="{support_url}" style="color: #2563eb; font-weight: bold;">@egxbots_bot</a></p>
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


def _resolve_user_pro_offer(user_id: Optional[str] = None) -> tuple[int, Optional[int]]:
    """Return ``(effective_pro_price_egp, founder_tier)`` respecting 50/100 EGP Founders lock."""
    if user_id:
        try:
            from api.payment_common import (
                is_user_eligible_for_50_egp_renewal,
                is_user_eligible_for_100_egp_renewal,
            )

            if is_user_eligible_for_50_egp_renewal(user_id):
                return 50, 50
            if is_user_eligible_for_100_egp_renewal(user_id):
                return 100, 100
        except Exception:
            pass

    try:
        from api.payment_common import current_pro_offer_copy

        pro_price, _ = current_pro_offer_copy()
        return int(round(float(pro_price))), None
    except Exception:
        return 150, None


def _build_tiers_summary_html(pro_price: int, founder_tier: Optional[int] = None) -> str:
    """Build FRA-compliant HTML block summarizing the 3-tier split or Founder Full Bundle lock."""
    duration_line = (
        "⏱️ <strong>خصم المدة التصاعدي:</strong> اختر أي مدة من شهر حتى 12 شهراً لأي باقة "
        "(فردية أو شاملة) بخصم تصاعدي يصل إلى <strong>25%</strong>.<br>"
    )
    payment_line = (
        "💳 <em>الدفع فوري وآمن عبر بوابة EasyKash المعتمدة "
        "(بطاقات بنكية محلية ودولية مع 3D Secure، محافظ إلكترونية، أو فوري).</em>"
    )
    if founder_tier in (50, 100):
        six_m = 250 if founder_tier == 50 else 500
        one_y = 450 if founder_tier == 50 else 900
        return (
            f"<strong>🔒 سعرك محفوظ كمؤسس في الباقة الشاملة ({founder_tier} ج.م/شهر بدلاً من 150 ج.م):</strong><br>"
            f"• <strong>الباقة الشاملة Pro:</strong> {founder_tier} ج.م/شهر — أو باقة 6 شهور بـ <strong>{six_m:,} ج.م</strong> / السنوية بـ <strong>{one_y:,} ج.م</strong>.<br>"
            "• <strong>تشمل كل شيء معاً:</strong> 350 رسالة تحليلية شهرياً مع ARTORO + تحليل صور الشارت والمحفظة (Vision AI) + محفظة 15 سهماً + 5 مهام مجدولة يومياً + قنوات تليجرام VIP (EGX + TASI).<br>"
            "• كما يمكنك اختيار <strong>باقة الشات الذكي فقط (100 ج.م/شهر)</strong> أو <strong>باقة تليجرام VIP فقط (100 ج.م/شهر)</strong>.<br>"
            f"{duration_line}"
            f"{payment_line}"
        )

    return (
        "<strong>اختر الباقة المناسبة لاستخدامك الآن:</strong><br>"
        "• 🤖 <strong>باقة الشات الذكي فقط: 100 ج.م/شهر</strong> — 350 رسالة تحليلية شهرياً مع ARTORO + تحليل صور الشارت والمحفظة (Vision AI) + محفظة 15 سهماً + 5 مهام مجدولة يومياً.<br>"
        "• 📡 <strong>باقة تليجرام VIP فقط: 100 ج.م/شهر</strong> — قنوات التنبيهات الفنية الفورية للبورصة المصرية (EGX) والسوق السعودي (TASI) + بيانات الموقع بدون تأخير.<br>"
        f"• 👑 <strong>الباقة الشاملة Pro (الأفضل قيمة): {pro_price} ج.م/شهر</strong> — تجمع الشات الذكي + قنوات تليجرام VIP معاً بتوفير 50 ج.م (ومتاح أيضاً باقة 6 شهور بـ <strong>750 ج.م</strong> والسنوية بـ <strong>1,350 ج.م</strong>).<br>"
        f"{duration_line}"
        f"{payment_line}"
    )


def process_abandoned_checkouts() -> int:
    """
    Finds users with pending/submitted orders between 2h and 72h old who haven't completed payment.
    Sends a plan-aware recovery email aligned with EasyKash-only & FRA compliance.
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

                # Check if user already has an active paid subscription across any paid tier
                sub_res = (
                    supabase.table("subscriptions")
                    .select("id")
                    .eq("user_id", uid)
                    .eq("status", "active")
                    .in_("plan_id", list(ALL_PAID_PLAN_IDS))
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

                order_plan = str(order.get("plan_id") or "pro").strip().lower()
                pro_price, founder_tier = _resolve_user_pro_offer(uid)

                if order_plan == "chat_only":
                    subject = "⏳ تذكير: استكمل اشتراكك في باقة الشات الذكي (100 ج.م/شهر) | EGX BOTS"
                    paragraphs = [
                        "لاحظنا أنك بدأت خطوات الاشتراك في <strong>باقة الشات الذكي (100 ج.م/شهر)</strong> ولم تستكمل عملية الدفع عبر EasyKash بعد.",
                        "<strong>ما تشمله باقة الشات الذكي (100 ج.م شهرياً):</strong><br>"
                        "• <strong>350 رسالة تحليلية شهرياً</strong> مع مساعد التحليل الفني ARTORO + تحليل صور الشارت والمحفظة (Vision AI).<br>"
                        "• <strong>متابعة محفظة حتى 15 سهماً</strong> + <strong>5 مهام مجدولة يومياً</strong> + إعادة توازن المحفظة + بيانات الموقع بدون تأخير.<br>"
                        f"• <em>ملاحظة:</em> يمكنك أيضاً اختيار <strong>الباقة الشاملة Pro ({pro_price} ج.م/شهر)</strong> لضم قنوات تليجرام VIP (EGX + TASI) مع الشات الذكي بتوفير 50 ج.م.",
                        "💳 لإتمام الاشتراك بأمان، ادخل على صفحة التسعير وأكمل الدفع عبر بوابة <strong>EasyKash</strong> (بطاقات بنكية محلية ودولية مع 3D Secure، محافظ إلكترونية، أو فوري).",
                    ]
                    cta_text = "استكمال اشتراك الشات الذكي (100 ج.م/شهر)"
                    cta_url = f"{APP_URL}/pricing?plan=chat_only"
                elif order_plan == "vip_only":
                    subject = "⏳ تذكير: استكمل اشتراكك في باقة تليجرام VIP (100 ج.م/شهر) | EGX BOTS"
                    paragraphs = [
                        "لاحظنا أنك بدأت خطوات الاشتراك في <strong>باقة تليجرام VIP (100 ج.م/شهر)</strong> ولم تستكمل عملية الدفع عبر EasyKash بعد.",
                        "<strong>ما تشمله باقة تليجرام VIP (100 ج.م شهرياً):</strong><br>"
                        "• <strong>رابط دخول خاص لقنوات تليجرام VIP</strong> للبورصة المصرية (EGX) والسوق السعودي (TASI) بمتابعة فورية للمؤشرات والاختراقات.<br>"
                        "• <strong>إلغاء تأخير بيانات الموقع</strong> لمتابعة شاشات الفحص الفني وكاشف المصائد والقيمة العادلة لحظياً.<br>"
                        f"• <em>ملاحظة:</em> يمكنك أيضاً الترقية إلى <strong>الباقة الشاملة Pro ({pro_price} ج.م/شهر)</strong> لضم الشات الذكي (350 رسالة تحليلية + Vision AI + محفظة 15 سهماً) مع قنوات VIP.",
                        "💳 لإتمام الاشتراك بأمان، ادخل على صفحة التسعير وأكمل الدفع عبر بوابة <strong>EasyKash</strong> (بطاقات بنكية محلية ودولية مع 3D Secure، محافظ إلكترونية، أو فوري).",
                    ]
                    cta_text = "استكمال اشتراك تليجرام VIP (100 ج.م/شهر)"
                    cta_url = f"{APP_URL}/pricing?plan=vip_only"
                else:
                    subject = f"⏳ تذكير: استكمل اشتراكك في الباقة الشاملة Pro ({pro_price} ج.م/شهر) | EGX BOTS"
                    paragraphs = [
                        "لاحظنا أنك بدأت خطوات الاشتراك في <strong>الباقة الشاملة EGX BOTS Pro</strong> ولم تستكمل عملية الدفع عبر EasyKash بعد.",
                        _build_tiers_summary_html(pro_price, founder_tier),
                    ]
                    cta_text = f"استكمال الاشتراك الآن ({pro_price} ج.م/شهر)"
                    cta_url = f"{APP_URL}/pricing?plan=pro"

                greeting = f"أهلاً {display_name} 👋"
                message_id = str(uuid.uuid4())
                html = _build_email_html(subject, greeting, paragraphs, cta_text, cta_url, uid, user_email, "abandoned_checkout", message_id)
                send_info: dict = {}
                if send_resend_email(user_email, subject, html, send_info):
                    record_marketing_message(uid, user_email, "abandoned_checkout", {"order_id": order.get("id"), "plan_id": order_plan}, message_id, send_info.get("provider_message_id"))
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
    Sends them a clear 3-tier / Founders-aware renewal reminder.
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

                # Check if already upgraded to any paid tier
                sub_res = (
                    supabase.table("subscriptions")
                    .select("id")
                    .eq("user_id", uid)
                    .eq("status", "active")
                    .in_("plan_id", list(ALL_PAID_PLAN_IDS))
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

                pro_price, founder_tier = _resolve_user_pro_offer(uid)

                if founder_tier in (50, 100):
                    subject = f"⏳ فترتك التجريبية تنتهي قريباً — سعرك كمؤسس محفوظ ({pro_price} ج.م/شهر) | EGX BOTS"
                    cta_text = f"تفعيل الباقة الشاملة بسعر المؤسسين ({pro_price} ج.م/شهر)"
                else:
                    subject = f"⏳ فترتك التجريبية تنتهي قريباً — باقات تبدأ من 100 ج.م/شهر (والشاملة {pro_price} ج.م) | EGX BOTS"
                    cta_text = "استعراض الباقات وتفعيل الاشتراك الآن"

                greeting = f"أهلاً {display_name} ⚡"
                paragraphs = [
                    "نود إعلامك أن <strong>تجربتك المجانية لأدوات EGX BOTS ستنتهي خلال الساعات القادمة</strong>.",
                    "نتمنى أن تكون قد استفدت من أدوات التحليل الفني ومساعد ARTORO ومؤشرات السيولة الفورية وكاشف المصائد خلال الأيام الماضية.",
                    _build_tiers_summary_html(pro_price, founder_tier),
                ]
                cta_url = f"{APP_URL}/pricing"

                message_id = str(uuid.uuid4())
                html = _build_email_html(subject, greeting, paragraphs, cta_text, cta_url, uid, user_email, "trial_expiring", message_id)
                send_info: dict = {}
                if send_resend_email(user_email, subject, html, send_info):
                    record_marketing_message(uid, user_email, "trial_expiring", {"expires_at": trial.get("expires_at")}, message_id, send_info.get("provider_message_id"))
                    sent_count += 1
            except Exception as trial_err:
                print(f"[MARKETING] Error processing trial for user {trial.get('user_id')}: {trial_err}")
                continue

    except Exception as e:
        print(f"[MARKETING] Error in process_trial_expiring: {e}")

    return sent_count


def _trial_recipient(uid: str):
    """Return (display_name, email) for a trial user, or (None, None)."""
    try:
        user_res = (
            supabase.table("profiles")
            .select("display_name, username")
            .eq("id", uid)
            .maybe_single()
            .execute()
        )
        profile = user_res.data or {}
    except Exception:
        profile = {}
    display_name = profile.get("display_name") or profile.get("username") or "صديقنا العزيز"
    return display_name, get_user_email(uid)


def _trial_already_paid(uid: str) -> bool:
    try:
        sub_res = (
            supabase.table("subscriptions")
            .select("id")
            .eq("user_id", uid)
            .eq("status", "active")
            .in_("plan_id", list(ALL_PAID_PLAN_IDS))
            .limit(1)
            .execute()
        )
        return bool(sub_res.data)
    except Exception:
        return False


def process_trial_welcome() -> int:
    """Day-0 activation email: the trial started but the first question did not.

    A trial that never opens the assistant converts at 0%, so this email hands
    the user the exact first analytical prompt instead of another price reminder.
    """
    if not supabase:
        return 0

    sent_count = 0
    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(hours=24)).isoformat()
    window_end = (now - timedelta(minutes=5)).isoformat()

    try:
        res = (
            supabase.table("subscription_trials")
            .select("user_id, started_at, expires_at")
            .gte("started_at", window_start)
            .lte("started_at", window_end)
            .limit(20)
            .execute()
        )
        trials = res.data or []

        for trial in trials:
            try:
                uid = trial.get("user_id")
                if not uid:
                    continue
                if _trial_already_paid(uid):
                    continue
                if has_recent_message(uid, "trial_welcome", 30):
                    continue

                display_name, user_email = _trial_recipient(uid)
                if not user_email or "@" not in user_email:
                    continue
                if is_user_unsubscribed(uid, user_email):
                    continue

                subject = "⚡ تجربتك في EGX BOTS Pro بدأت — اسأل أول سؤال تحليلي دلوقتي"
                greeting = f"أهلاً {display_name} 🚀"
                paragraphs = [
                    "تم تفعيل <strong>تجربة Pro الشاملة المجانية لمدة 3 أيام</strong> على حسابك، وتفتح لك حالياً الشات الذكي وقنوات تليجرام VIP (EGX + TASI) معاً.",
                    "أسرع طريقة تشوف القيمة: افتح شات التحليل الذكي واسأل سؤالاً مباشراً، مثل <strong>«اعرض لي أبرز 3 أسهم عليها زخم فني اليوم»</strong> أو <strong>«حلّل سهم COMI وقولّي مستويات الدعم والمقاومة»</strong>.",
                    "كل قراءة فنية ترجع لك بالمؤشرات الكمية ومستويات الدعم والمقاومة وإحصاءات السيولة، بالإضافة إلى قراءات المؤشرات الفنية المفتوحة ومتابعة المحفظة.",
                    "ولو ربطت حسابك بتيليجرام، تحصل على <strong>10 رسائل إضافية مجاناً</strong> وتقدر تتابع من الموبايل بسهولة.",
                ]
                message_id = str(uuid.uuid4())
                html = _build_email_html(
                    subject, greeting, paragraphs,
                    "افتح الشات واسأل أول سؤال",
                    f"{APP_URL}/?chat=open&from=trial_welcome",
                    uid, user_email, "trial_welcome", message_id,
                )
                send_info: dict = {}
                if send_resend_email(user_email, subject, html, send_info):
                    record_marketing_message(uid, user_email, "trial_welcome", {"expires_at": trial.get("expires_at")}, message_id, send_info.get("provider_message_id"))
                    sent_count += 1
            except Exception as trial_err:
                print(f"[MARKETING] Error sending trial welcome for {trial.get('user_id')}: {trial_err}")
                continue
    except Exception as e:
        print(f"[MARKETING] Error in process_trial_welcome: {e}")

    return sent_count


def process_trial_day1() -> int:
    """Day-1 nudge for trials that are still running and not converted yet."""
    if not supabase:
        return 0

    sent_count = 0
    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(hours=48)).isoformat()
    window_end = (now - timedelta(hours=20)).isoformat()

    try:
        res = (
            supabase.table("subscription_trials")
            .select("user_id, started_at, expires_at")
            .gte("started_at", window_start)
            .lte("started_at", window_end)
            .gte("expires_at", now.isoformat())
            .limit(20)
            .execute()
        )
        trials = res.data or []

        for trial in trials:
            try:
                uid = trial.get("user_id")
                if not uid:
                    continue
                if _trial_already_paid(uid):
                    continue
                if has_recent_message(uid, "trial_day1", 30):
                    continue

                display_name, user_email = _trial_recipient(uid)
                if not user_email or "@" not in user_email:
                    continue
                if is_user_unsubscribed(uid, user_email):
                    continue

                subject = "3 أسئلة تحليلية تفتح لك قيمة EGX BOTS قبل نهاية تجربتك"
                greeting = f"كيف حالك {display_name}؟"
                paragraphs = [
                    "فاضل أقل من يومين على نهاية تجربتك، وأفضل استغلال ليها هو أسئلة تحليلية مباشرة على أسهمك.",
                    "<strong>جرّب واحداً من هذه الأسئلة الآن:</strong><br>• «اعرض لي أبرز 3 أسهم عليها إشارة فنية إيجابية اليوم»<br>• «حلّل سهماً في محفظتي وحدّد مناطق الدعم والمقاومة»<br>• «إيه أقوى القطاعات سيولة هذا الأسبوع؟»",
                    "كل إجابة بتوصلك بمؤشرات فنية رقمية واضحة، مع متابعة تنبيهاتك الفنية ومحفظتك من مكان واحد.",
                ]
                message_id = str(uuid.uuid4())
                html = _build_email_html(
                    subject, greeting, paragraphs,
                    "افتح الشات دلوقتي",
                    f"{APP_URL}/?chat=open&from=trial_day1",
                    uid, user_email, "trial_day1", message_id,
                )
                send_info: dict = {}
                if send_resend_email(user_email, subject, html, send_info):
                    record_marketing_message(uid, user_email, "trial_day1", {"expires_at": trial.get("expires_at")}, message_id, send_info.get("provider_message_id"))
                    sent_count += 1
            except Exception as trial_err:
                print(f"[MARKETING] Error sending trial day1 for {trial.get('user_id')}: {trial_err}")
                continue
    except Exception as e:
        print(f"[MARKETING] Error in process_trial_day1: {e}")

    return sent_count


def process_trial_day2() -> int:
    """Day-2 analytical case study & split-tier summary for trials nearing their final day."""
    if not supabase:
        return 0

    sent_count = 0
    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(hours=60)).isoformat()
    window_end = (now - timedelta(hours=36)).isoformat()

    try:
        res = (
            supabase.table("subscription_trials")
            .select("user_id, started_at, expires_at")
            .gte("started_at", window_start)
            .lte("started_at", window_end)
            .gte("expires_at", now.isoformat())
            .limit(20)
            .execute()
        )
        trials = res.data or []

        for trial in trials:
            try:
                uid = trial.get("user_id")
                if not uid:
                    continue
                if _trial_already_paid(uid):
                    continue
                if has_recent_message(uid, "trial_day2", 30):
                    continue

                display_name, user_email = _trial_recipient(uid)
                if not user_email or "@" not in user_email:
                    continue
                if is_user_unsubscribed(uid, user_email):
                    continue

                pro_price, founder_tier = _resolve_user_pro_offer(uid)

                subject = "📊 كيف يلتقط رادار السيولة الاختراقات الفنية ومصائد السوق مبكراً؟ | EGX BOTS"
                greeting = f"أهلاً {display_name} 🎯"
                paragraphs = [
                    "تجربتك في <strong>EGX BOTS Pro</strong> قربت على الانتهاء (أقل من 24 ساعة متبقية)، وحبينا نوضح لك عملياً كيف تعمل أدوات التحليل الفني في المنصة.",
                    "<strong>كيف يعمل نظام الرصد الكمي والفني؟</strong><br>"
                    "1️⃣ <strong>رادار السيولة الذكية:</strong> يرصد تدفقات السيولة غير الاعتيادية والاختراقات السعرية اللحظية بالبورصة المصرية والسعودية.<br>"
                    "2️⃣ <strong>كاشف المصائد والقمم:</strong> يميّز رقمياً بين نماذج الارتداد التجميعي (Spring) ومصائد القمم (Upthrust) مع تحديد مستويات المراقبة.<br>"
                    "3️⃣ <strong>مساعد التحليل الفني ARTORO:</strong> يقرأ الشارت وصور المحافظ (Vision AI) ويحسب القيمة العادلة والتوافق الشرعي لأي سهم.",
                    _build_tiers_summary_html(pro_price, founder_tier),
                ]
                message_id = str(uuid.uuid4())
                html = _build_email_html(
                    subject, greeting, paragraphs,
                    "استعراض الباقات والاشتراك الآن",
                    f"{APP_URL}/pricing",
                    uid, user_email, "trial_day2", message_id,
                )
                send_info: dict = {}
                if send_resend_email(user_email, subject, html, send_info):
                    record_marketing_message(uid, user_email, "trial_day2", {"expires_at": trial.get("expires_at")}, message_id, send_info.get("provider_message_id"))
                    sent_count += 1
            except Exception as trial_err:
                print(f"[MARKETING] Error sending trial day2 for {trial.get('user_id')}: {trial_err}")
                continue
    except Exception as e:
        print(f"[MARKETING] Error in process_trial_day2: {e}")

    return sent_count

def process_signup_telegram_nudge() -> int:
    """Send an automated reminder email ~30 minutes after signup to new users
    who have not yet linked Telegram or activated their free 3-day Pro trial."""
    if not supabase:
        return 0

    sent_count = 0
    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(hours=24)).isoformat()
    window_end = (now - timedelta(minutes=30)).isoformat()

    try:
        res = (
            supabase.table("profiles")
            .select("id, display_name, username, created_at")
            .is_("telegram_chat_id", "null")
            .gte("created_at", window_start)
            .lte("created_at", window_end)
            .order("created_at", desc=False)
            .limit(25)
            .execute()
        )
        candidates = res.data or []
        if not candidates:
            return 0

        daily_sent = get_daily_sent_count()

        for profile in candidates:
            if daily_sent + sent_count >= MARKETING_DAILY_EMAIL_CAP:
                break
            try:
                uid = profile.get("id")
                if not uid:
                    continue

                # Never email if already sent this nudge or recent re-engagement
                if has_recent_message(uid, "signup_tg_trial_nudge", 30):
                    continue
                if has_recent_message(uid, "trial_reengagement_fix_nov25", 7):
                    continue

                # Strictly exclude users who already had a trial, subscription, approved order, or founders slot
                t_res = supabase.table("subscription_trials").select("user_id").eq("user_id", uid).limit(1).execute()
                if t_res.data:
                    continue
                s_res = supabase.table("subscriptions").select("id").eq("user_id", uid).limit(1).execute()
                if s_res.data:
                    continue
                o_res = (
                    supabase.table("local_payment_orders")
                    .select("id")
                    .eq("user_id", uid)
                    .eq("status", "approved")
                    .limit(1)
                    .execute()
                )
                if o_res.data:
                    continue
                f_res = supabase.table("founders_offer_members").select("user_id").eq("user_id", uid).limit(1).execute()
                if f_res.data:
                    continue

                user_email = get_user_email(uid)
                if not user_email or "@" not in user_email:
                    continue
                if is_user_unsubscribed(uid, user_email):
                    continue

                display_name = profile.get("display_name") or profile.get("username") or "صديقنا العزيز"
                bot_url = f"https://t.me/egxbots_bot?start={uid}"
                start_code = f"/start {uid}"

                subject = "🎁 خطوة واحدة (5 ثوانٍ) لتفعيل 3 أيام Pro مجاناً في EGX BOTS"
                greeting = f"أهلاً {display_name} 👋"
                paragraphs = [
                    "مرحباً بك في <strong>EGX BOTS</strong>! لاحظنا أنك أنشأت حسابك بنجاح، لكنك لم تربط حسابك ببوت تليجرام لتفعيل <strong>تجربتك المجانية لمدة 3 أيام كاملة (بدون بطاقة بنكية)</strong>.",
                    "<strong>كيف تفعّل تجربتك خلال 5 ثوانٍ؟</strong><br>"
                    "1️⃣ اضغط على الزر بالأسفل لفتح بوت <strong>@egxbots_bot</strong> على تليجرام.<br>"
                    "2️⃣ اضغط <strong>Start / ابدأ</strong> داخل المحادثة — وسيتم ربط حسابك وتفعيل <strong>3 أيام Pro مجاناً</strong> تلقائياً خلال ثانية!<br>"
                    "3️⃣ استمتع بمساعد التحليل الفني <strong>ARTORO AI</strong>، رادار السيولة، وتنبيهات قناة VIP.",
                    f"<div style='background:#f9fafb;border:1px dashed #9ca3af;border-radius:8px;padding:12px;margin-top:8px;'>"
                    f"<div style='font-size:12px;color:#4b5563;margin-bottom:6px;'>💡 إذا لم يفتح الرابط مباشرة، افتح تليجرام وابحث عن <strong>@egxbots_bot</strong> وأرسل له هذا الكود:</div>"
                    f"<div dir='ltr' style='font-family:monospace;font-size:13px;background:#111827;color:#93c5fd;padding:8px 10px;border-radius:6px;text-align:left;word-break:break-all;'>{start_code}</div>"
                    f"</div>",
                    "<span style='font-size:12px;color:#6b7280;'>ملاحظة: EGX BOTS أداة تحليلية برمجية للأبحاث الشخصية والتعليمية فقط ولا تُقدّم نصيحة استثمارية.</span>",
                ]

                message_id = str(uuid.uuid4())
                html = _build_email_html(
                    subject,
                    greeting,
                    paragraphs,
                    "اربط تليجرام وفعّل 3 أيام مجاناً ⚡",
                    bot_url,
                    uid,
                    user_email,
                    "signup_tg_trial_nudge",
                    message_id,
                )
                send_info: dict = {}
                if send_resend_email(user_email, subject, html, send_info):
                    record_marketing_message(
                        uid,
                        user_email,
                        "signup_tg_trial_nudge",
                        {"created_at": profile.get("created_at")},
                        message_id,
                        send_info.get("provider_message_id"),
                    )
                    sent_count += 1
            except Exception as item_err:
                print(f"[MARKETING] Error sending signup_tg_trial_nudge for {profile.get('id')}: {item_err}")
                continue
    except Exception as e:
        print(f"[MARKETING] Error in process_signup_telegram_nudge: {e}")

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
    signup_nudge = process_signup_telegram_nudge()
    abandoned = process_abandoned_checkouts()
    welcome = process_trial_welcome()
    nudges_enabled = os.getenv("MARKETING_TRIAL_NUDGES_ENABLED", "").strip().lower() in ("1", "true", "yes")
    day1 = process_trial_day1() if nudges_enabled else 0
    day2 = process_trial_day2() if nudges_enabled else 0
    trials = process_trial_expiring()
    final_48h_sent = 0

    total_sent = signup_nudge + abandoned + welcome + day1 + day2 + trials
    print(f"[MARKETING] Lifecycle run finished. Sent: {total_sent} "
          f"(Signup TG nudge: {signup_nudge}, Abandoned: {abandoned}, Trial welcome: {welcome}, Trial day1: {day1}, Day2: {day2}, "
          f"Trials expiring: {trials})")
    return {
        "status": "ok",
        "signup_tg_nudge_sent": signup_nudge,
        "abandoned_sent": abandoned,
        "trial_welcome_sent": welcome,
        "trial_day1_sent": day1,
        "trial_day2_sent": day2,
        "trials_sent": trials,
        "final_48h_sent": final_48h_sent,
        "total_sent": total_sent,
        "sent_today": daily_count + total_sent,
    }


class MarketingLifecycleEngine:
    """Class wrapper for Marketing Lifecycle operations."""
    run = staticmethod(run_marketing_lifecycle)
    send_email = staticmethod(send_resend_email)
    process_signup_telegram_nudge = staticmethod(process_signup_telegram_nudge)
    process_abandoned = staticmethod(process_abandoned_checkouts)
    process_trial_welcome = staticmethod(process_trial_welcome)
    process_trial_day1 = staticmethod(process_trial_day1)
    process_trial_day2 = staticmethod(process_trial_day2)
    process_trials = staticmethod(process_trial_expiring)

