"""send_failed_payment_recovery.py — Empathetic Outreach for Failed/Abandoned Checkouts.

Reaches out to users who experienced failed or incomplete checkout attempts on EasyKash:
1. Via Telegram (if telegram_chat_id is available).
2. Via Resend Email.

Listens to their problems (bank decline, OTP issues, card errors) and provides the direct
e-wallet / InstaPay alternative (01024359100) with instant support.
"""
from __future__ import annotations

import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
import html
import requests
from datetime import datetime, timezone, timedelta
import time
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.getcwd())

from api.stock_ai import _init_supabase, supabase
from api.marketing_lifecycle import (
    send_resend_email,
    _build_email_html,
    record_marketing_message,
    is_user_unsubscribed,
    has_recent_message,
    APP_URL,
)

DIRECT_WALLET_NUMBER = "01024359100"
WHATSAPP_SUPPORT_URL = f"https://wa.me/20{DIRECT_WALLET_NUMBER[1:]}?text=" + requests.utils.quote(
    "مرحبا، واجهت مشكلة في الدفع بالفيزا على EGX BOTS وأريد المساعدة / الدفع بالمحفظة الإلكترونية"
)
TELEGRAM_SUPPORT_URL = "https://t.me/SharksZone_support_bot"


def send_failed_payment_telegram(chat_id: str | int, display_name: str) -> bool:
    """Sends a friendly support message to the user's Telegram."""
    token = os.getenv("ARTORO_AI_BOT") or os.getenv("SUPPORT_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return False

    relay_url = (os.getenv("TELEGRAM_RELAY_URL", "https://api.telegram.org")).rstrip("/")
    clean_name = html.escape(display_name or "المستثمر")

    text = (
        f"أهلاً بك يا <b>{clean_name}</b> 👋\n\n"
        "لاحظنا تعثر عملية الدفع الأخيرة لاشتراك <b>EGX BOTS PRO</b> على الموقع 💳\n\n"
        "حابين نطمئن عليك ونعرف هل واجهتك أي مشكلة تقنية، أو رفض من البنك أو تأخر كود التأكيد؟ <b>احكيلنا ونساعدك فوراً!</b> 💬\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <b>حابين نوضحلك إنك تقدر تشترك بدون فيزا خالص:</b>\n"
        "متاح الدفع والتحويل المباشر عبر <b>أي محفظة إلكترونية أو إنستاباي</b> (InstaPay / فودافون كاش / اتصالات / أورنج / وي) على رقمنا:\n"
        f"📱 <code>{DIRECT_WALLET_NUMBER}</code>\n\n"
        "بمجرد التحويل، راسلنا هنا أو على واتساب برقم العملية وهنفعل لك باقة PRO ونضيفك لقناة التوصيات VIP فوراً! 🚀\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "نسعد دائماً بخدمتك ونتمنى لك تداولات موفقة ومربحة! 📈"
    )

    buttons = [
        [{"text": "💬 تواصل معنا على واتساب", "url": WHATSAPP_SUPPORT_URL}],
        [{"text": "🌐 العودة لصفحة الباقات", "url": f"{APP_URL}/pricing"}],
    ]

    try:
        url = f"{relay_url}/bot{token}/sendMessage"
        resp = requests.post(
            url,
            json={
                "chat_id": str(chat_id),
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": buttons},
            },
            timeout=10,
        )
        return bool(resp.status_code == 200 and resp.json().get("ok"))
    except Exception as exc:
        print(f"[RECOVERY] Telegram dispatch error to {chat_id}: {exc}")
        return False


def send_failed_payment_email(user_id: str, email: str, display_name: str) -> bool:
    """Sends an empathetic outreach email via Resend."""
    if is_user_unsubscribed(user_id, email):
        return False

    clean_name = display_name or "المستثمر"
    subject = f"واجهت مشكلة في الدفع يا {clean_name}؟ احكيلنا ونساعدك فوراً 💬"
    greeting = f"أهلاً {clean_name} 👋"

    paragraphs = [
        "لاحظنا أن محاولتك الأخيرة لتفعيل اشتراك <strong>EGX BOTS PRO</strong> لم تكتمل بنجاح.",
        "نود الاطمئنان عليك.. <strong>هل واجهتك مشكلة أثناء الدفع؟</strong> مثل رفض المعاملة من البنك، أو عدم وصول كود التأكيد، أو عدم توفر بطاقة بنكية مناسبة؟ يهمنا جداً سماع تجربتك لنساعدك في حلها فوراً.",
        f"💡 <strong>حابين نوضحلك إنه متاح الدفع بدون فيزا نهائياً:</strong><br/>"
        f"يمكنك التحويل المباشر من <strong>أي محفظة إلكترونية أو إنستاباي</strong> (InstaPay / فودافون كاش / أورنج / اتصالات / وي / المحافظ البنكية) مباشرة إلى رقمنا:<br/>"
        f"<div style='background:#f4f4f5;padding:12px;border-left:4px solid #10b981;font-size:18px;font-family:monospace;font-weight:bold;margin:10px 0;'>"
        f"📱 {DIRECT_WALLET_NUMBER}</div>"
        f"بمجرد التحويل، فقط أرسل لنا رسالة برقم العملية وسنقوم <strong>بتفعيل حسابك فوراً وإضافتك لقناة التوصيات VIP</strong> بدون أي انتظار!",
        "فريق الدعم متاح معك خطوة بخطوة للرد على أي استفسار أو تفعيل حسابك مباشرة.",
    ]

    cta_text = "💬 تواصل معنا عبر واتساب للمساعدة الفورية"
    cta_url = WHATSAPP_SUPPORT_URL

    html_content = _build_email_html(
        headline=subject,
        greeting=greeting,
        content_paragraphs=paragraphs,
        cta_text=cta_text,
        cta_url=cta_url,
        user_id=user_id,
        email=email,
        campaign="failed_payment_recovery",
    )

    send_meta: Dict[str, Any] = {}
    if send_resend_email(email, subject, html_content, out=send_meta):
        record_marketing_message(
            user_id=user_id,
            email=email,
            message_type="failed_payment_recovery",
            metadata={"channel": "email", "campaign": "failed_payment_support_direct_wallet"},
            provider_message_id=send_meta.get("provider_message_id"),
        )
        return True
    return False


def get_failed_checkout_targets() -> List[Dict[str, Any]]:
    """Returns unique users with failed/pending checkout orders who are not currently Pro."""
    _init_supabase()
    orders = (
        supabase.table("local_payment_orders")
        .select("id, user_id, amount_egp, status, created_at, provider")
        .neq("status", "approved")
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )

    user_ids = list(dict.fromkeys([o["user_id"] for o in orders.data if o.get("user_id")]))
    targets = []

    for uid in user_ids:
        # Check if already Pro
        sub_res = (
            supabase.table("subscriptions")
            .select("status")
            .eq("user_id", uid)
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        if sub_res.data:
            continue

        email = ""
        name = "المستثمر"
        try:
            u = supabase.auth.admin.get_user_by_id(uid)
            if u and getattr(u, "user", None):
                email = u.user.email or ""
                name = (
                    (u.user.user_metadata or {}).get("full_name")
                    or (u.user.user_metadata or {}).get("name")
                    or name
                )
        except Exception:
            pass

        prof_res = (
            supabase.table("profiles")
            .select("id, display_name, username, telegram_chat_id, whatsapp_number")
            .eq("id", uid)
            .limit(1)
            .execute()
        )
        p = prof_res.data[0] if prof_res.data else {}
        if p.get("display_name") or p.get("username"):
            name = p.get("display_name") or p.get("username") or name

        if email and "test" not in email.lower() and email != "egxbots@gmail.com":
            targets.append({
                "user_id": uid,
                "email": email,
                "name": name,
                "telegram_chat_id": p.get("telegram_chat_id"),
                "whatsapp_number": p.get("whatsapp_number"),
            })

    return targets


def dispatch_failed_payment_recovery_for_user(user_id: str) -> Dict[str, Any]:
    """Triggers empathetic outreach for a specific user whose payment failed or was incomplete."""
    _init_supabase()
    # Check cooldown (avoid sending more than once every 24 hours to the same user)
    if has_recent_message(user_id, "failed_payment_recovery", cooldown_days=1):
        return {"ok": True, "skipped": "cooldown"}

    # Check if user has already become active Pro
    sub_res = (
        supabase.table("subscriptions")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if sub_res.data and len(sub_res.data) > 0:
        return {"ok": True, "skipped": "already_pro"}

    email = ""
    name = "المستثمر"
    try:
        u = supabase.auth.admin.get_user_by_id(user_id)
        if u and getattr(u, "user", None):
            email = u.user.email or ""
            name = (
                (u.user.user_metadata or {}).get("full_name")
                or (u.user.user_metadata or {}).get("name")
                or name
            )
    except Exception:
        pass

    prof_res = (
        supabase.table("profiles")
        .select("id, display_name, username, telegram_chat_id, whatsapp_number")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    p = prof_res.data[0] if prof_res.data else {}
    if p.get("display_name") or p.get("username"):
        name = p.get("display_name") or p.get("username") or name

    tg_sent = False
    if p.get("telegram_chat_id"):
        tg_sent = send_failed_payment_telegram(p["telegram_chat_id"], name)

    email_sent = False
    if email and "@" in email and "test" not in email.lower() and email != "egxbots@gmail.com":
        email_sent = send_failed_payment_email(user_id, email, name)

    return {
        "ok": True,
        "telegram_sent": tg_sent,
        "email_sent": email_sent,
        "email": email,
        "name": name,
    }


def dispatch_to_all_failed_targets() -> Dict[str, Any]:
    """Dispatches the empathetic recovery outreach to all eligible failed-checkout targets."""
    targets = get_failed_checkout_targets()
    print(f"Starting failed-checkout empathetic outreach to {len(targets)} users...")
    stats = {"total": len(targets), "emails_sent": 0, "telegrams_sent": 0, "skipped": 0, "failed": 0}

    for t in targets:
        uid = t["user_id"]
        res = dispatch_failed_payment_recovery_for_user(uid)
        if res.get("skipped"):
            stats["skipped"] += 1
            print(f"⏩ {t['email']}: Skipped ({res['skipped']})")
        else:
            e_ok = res.get("email_sent", False)
            tg_ok = res.get("telegram_sent", False)
            if e_ok:
                stats["emails_sent"] += 1
            if tg_ok:
                stats["telegrams_sent"] += 1
            print(f"✅ {t['email']}: Email={'SENT' if e_ok else 'NO'} | TG={'SENT' if tg_ok else 'NO'}")
            time.sleep(0.5)

    print(f"\nCompleted! Stats: {stats}")
    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Failed Checkout Outreach Dispatcher")
    parser.add_argument("--send", action="store_true", help="Send outreach to all failed checkout targets")
    args = parser.parse_args()

    targets = get_failed_checkout_targets()
    print(f"Found {len(targets)} eligible failed-checkout targets:")
    for t in targets:
        print(f"- {t['email']} | Name: {t['name']} | TG: {t['telegram_chat_id']} | WA: {t['whatsapp_number']}")

    if args.send:
        print("\n🚀 Executing outreach dispatch...")
        dispatch_to_all_failed_targets()
    else:
        print("\nℹ️ Dry-run preview only. Pass --send to execute dispatch.")
