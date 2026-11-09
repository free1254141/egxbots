"""Direct E-Wallet Transfer & Instant Pro Auto-Activation.

Allows users to pay directly to the owner's mobile wallet (01024359100)
via Vodafone Cash, InstaPay, Orange Cash, Etisalat Cash, WE Pay, or Smart Bank Wallets.
Automatically verifies transaction reference uniqueness, activates Pro instantly,
generates VIP Telegram invite, and notifies the support bot on Telegram.
"""
from __future__ import annotations

import html
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from uuid import uuid4

import requests

from api.stock_ai import _init_supabase, supabase
from api.payment_common import (
    activate_subscription,
    is_payments_enabled,
    plan_amount_egp,
    pro_discount,
)
from api.easykash_payments import (
    validate_affiliate_code,
    _ACTIVE_PRO_PLAN_IDS,
)
from api.telegram_pro_invites import (
    ensure_pro_invite,
    send_pro_welcome_to_user_telegram,
)

# Owner destination wallet for direct transfers
DIRECT_WALLET_RECIPIENT_NUMBER = "01024359100"
SUPPORT_ADMIN_CHAT_ID = 5149631436  # Chat ID for owner chatting with SharksZone_support_bot (8328474058)


def is_direct_wallet_enabled() -> bool:
    """Direct wallet transfers are active whenever billing/payments is enabled."""
    return is_payments_enabled()


def send_direct_wallet_support_alert(
    user_email: str,
    sender_mobile: str,
    transaction_id: str,
    amount_egp: float,
    plan_id: str,
    promo_code: str,
    order_id: str,
) -> bool:
    """Send an instant push alert to admin Telegram support bot chat."""
    token = os.getenv("SUPPORT_BOT_TOKEN", "").strip()
    if not token:
        print("[DIRECT_WALLET] SUPPORT_BOT_TOKEN is missing, skipping telegram alert")
        return False

    relay_url = (os.getenv("TELEGRAM_RELAY_URL", "https://api.telegram.org")).rstrip("/")
    cairo_now = datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d %I:%M %p")

    plan_label = "Pro VIP (شهري)" if plan_id in ("pro", "pro_renewal") else f"خطة {plan_id}"
    promo_text = f"<code>{promo_code}</code>" if promo_code else "بدون كود"

    text = (
        "⚡ <b>اشتراك فوري جديد عبر المحفظة الإلكترونية!</b>\n\n"
        f"👤 <b>المستخدم:</b> <code>{html.escape(user_email)}</code>\n"
        f"📱 <b>المحفظة المحول منها:</b> <code>{html.escape(sender_mobile)}</code>\n"
        f"💳 <b>المحفظة المستلمة:</b> <code>{DIRECT_WALLET_RECIPIENT_NUMBER}</code>\n"
        f"🔢 <b>رقم العملية / المرجع:</b> <code>{html.escape(transaction_id)}</code>\n"
        f"💰 <b>المبلغ:</b> <b>{amount_egp:,.0f} ج.م</b>\n"
        f"📦 <b>الخطة:</b> {plan_label}\n"
        f"🏷️ <b>كود الخصم:</b> {promo_text}\n"
        f"🆔 <b>Order ID:</b> <code>{order_id}</code>\n"
        f"⏰ <b>التوقيت:</b> {cairo_now} بتوقيت القاهرة\n\n"
        "✅ <b>تم تفعيل باقة PRO للمستخدم فوراً ولحظياً بدون أي انتظار!</b> 🚀\n"
        "<i>(يرجى مطابقة رسالة استلام الرصيد الواردة على هاتفك)</i>"
    )

    admin_chat_id = SUPPORT_ADMIN_CHAT_ID
    env_chat = os.getenv("SUPPORT_ADMIN_CHAT_ID")
    if env_chat and env_chat.strip().lstrip("-").isdigit():
        try:
            admin_chat_id = int(env_chat.strip())
        except ValueError:
            pass

    try:
        url = f"{relay_url}/bot{token}/sendMessage"
        resp = requests.post(
            url,
            json={
                "chat_id": admin_chat_id,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        data = resp.json() if resp.status_code == 200 else {}
        ok = bool(data.get("ok"))
        if not ok:
            print(f"[DIRECT_WALLET] Telegram send error: {resp.status_code} {resp.text}")
        return ok
    except Exception as exc:
        print(f"[DIRECT_WALLET] Telegram notification failed: {exc}")
        return False


def confirm_direct_wallet_payment(
    user_id: str,
    plan_id: str,
    sender_mobile: str,
    transaction_id: str,
    promo_code: str = "",
) -> Dict[str, Any]:
    """Verify and instantly auto-activate a direct wallet payment.
    
    Prevents duplicate transaction references, creates the approved order,
    activates subscription, grants VIP invite, and dispatches the support notification.
    """
    _init_supabase()
    if not supabase:
        raise RuntimeError("Supabase is not initialized")

    if not is_direct_wallet_enabled():
        raise ValueError("المدفوعات معطلة حالياً")

    # 1. Validate Mobile Number (Egyptian 11 digits)
    clean_mobile = re.sub(r"[\s-]", "", sender_mobile or "")
    if not re.match(r"^01[0125]\d{8}$", clean_mobile):
        raise ValueError("رقم الموبايل المحول منه يجب أن يكون رقماً مصرياً صحيحاً (11 رقم)")

    # 2. Validate Transaction ID
    clean_tx = re.sub(r"[\s\r\n\t]", "", transaction_id or "").strip()
    if len(clean_tx) < 6:
        raise ValueError("رقم العملية أو المرجع يجب أن يكون 6 أرقام أو حروف على الأقل")

    # 3. Fraud & Duplicate Replay Protection
    # Check if transaction ID has already been recorded in local_payment_orders
    existing = (
        supabase.table("local_payment_orders")
        .select("id, status, created_at")
        .or_(f"provider_order_id.eq.{clean_tx},customer_note.ilike.%Ref: {clean_tx}%")
        .limit(1)
        .execute()
    )
    if existing and existing.data:
        raise ValueError("رقم العملية أو المرجع هذا تم استخدامه مسبقاً للتفعيل")

    # Fetch user details from auth/profiles
    user_email = ""
    try:
        auth_user = supabase.auth.admin.get_user_by_id(user_id)
        if auth_user and getattr(auth_user, "user", None):
            user_email = auth_user.user.email or ""
    except Exception:
        pass

    if not user_email:
        # Fallback query to profiles
        prof = supabase.table("profiles").select("email, username").eq("id", user_id).maybe_single().execute()
        user_email = (prof.data or {}).get("email") or (prof.data or {}).get("username") or "مستخدم EGX Bots"

    # Save phone to user profile so they never have to re-enter it
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        supabase.table("profiles").update({
            "whatsapp_number": clean_mobile,
            "updated_at": now_iso,
        }).eq("id", user_id).execute()
    except Exception as e:
        print(f"[DIRECT_WALLET] Update whatsapp_number warning: {e}")

    # 4. Pricing & Promo Calculation
    requested_plan = (plan_id or "pro").strip().lower()
    base_price = float(plan_amount_egp(requested_plan, user_id=user_id))
    discount_amount = 0.0
    commission_amount = 0.0
    aff_id = None
    applied_promo = (promo_code or "").strip().upper()

    if applied_promo:
        aff_val = validate_affiliate_code(applied_promo, track_click=False)
        if aff_val.get("valid"):
            aff_id = aff_val.get("affiliate_id")
            disc_pct = float(aff_val.get("discount_percent") or 0)
            comm_pct = float(aff_val.get("commission_percent") or 0)
            if disc_pct > 0:
                discount_amount = round(base_price * (disc_pct / 100.0), 2)
            final_price = max(1.0, round(base_price - discount_amount, 2))
            if comm_pct > 0:
                commission_amount = round(final_price * (comm_pct / 100.0), 2)
        else:
            final_price = base_price
    else:
        final_price = base_price

    # 5. Create Approved Order in local_payment_orders
    order_id = str(uuid4())
    customer_note = (
        f"Direct Wallet: {clean_mobile} -> {DIRECT_WALLET_RECIPIENT_NUMBER} | "
        f"Ref: {clean_tx} | Plan: {requested_plan} | Promo: {applied_promo or 'none'}"
    )

    order_payload = {
        "id": order_id,
        "user_id": user_id,
        "plan_id": requested_plan,
        "amount_egp": final_price,
        "provider": "direct_wallet",
        "status": "approved",
        "payment_review_status": "reviewed",
        "payment_reviewed_by": "instant_auto_activation",
        "payment_reviewed_at": now_iso,
        "auto_activated_at": now_iso,
        "customer_note": customer_note,
        "affiliate_id": aff_id,
        "affiliate_code": applied_promo if aff_id else None,
        "discount_amount_egp": discount_amount,
        "commission_amount_egp": commission_amount,
        "commission_status": "earned" if aff_id else "none",
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    insert_res = supabase.table("local_payment_orders").insert(order_payload).execute()
    if not insert_res.data:
        raise RuntimeError("تعذر حفظ طلب الدفع في قاعدة البيانات")

    # 6. Instant Subscription Activation
    activate_subscription(
        user_id,
        requested_plan,
        provider="direct_wallet",
        payment_order_id=order_id,
    )

    # 7. Fetch Subscription End & Generate VIP Invite Link
    sub_res = (
        supabase.table("subscriptions")
        .select("current_period_end")
        .eq("user_id", user_id)
        .in_("plan_id", _ACTIVE_PRO_PLAN_IDS)
        .eq("status", "active")
        .order("current_period_end", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    sub_data = (sub_res.data if sub_res else None) or {}
    subscription_end = sub_data.get("current_period_end")

    invite_link = ""
    if subscription_end:
        try:
            invite = ensure_pro_invite(user_id, str(subscription_end))
            invite_link = str((invite or {}).get("invite_link") or "").strip()
            if invite_link:
                supabase.table("local_payment_orders").update({
                    "telegram_invite_link": invite_link,
                }).eq("id", order_id).execute()

                # Dispatch Telegram Pro welcome to user if linked
                try:
                    send_pro_welcome_to_user_telegram(
                        user_id,
                        invite_link=invite_link,
                        plan_name="Pro",
                        subscription_end=str(subscription_end),
                    )
                except Exception as tg_err:
                    print(f"[DIRECT_WALLET] User welcome dispatch error: {tg_err}")
        except Exception as inv_err:
            print(f"[DIRECT_WALLET] VIP invite generation error: {inv_err}")

    # 8. Update Affiliate Metrics if applicable
    if aff_id:
        try:
            aff_res = (
                supabase.table("affiliates")
                .select("total_sales_count,total_revenue_egp,total_commission_egp")
                .eq("id", aff_id)
                .maybe_single()
                .execute()
            )
            aff_row = (aff_res.data if aff_res else None) or {}
            supabase.table("affiliates").update({
                "total_sales_count": int(aff_row.get("total_sales_count") or 0) + 1,
                "total_revenue_egp": float(aff_row.get("total_revenue_egp") or 0) + float(final_price),
                "total_commission_egp": float(aff_row.get("total_commission_egp") or 0) + float(commission_amount),
                "updated_at": now_iso,
            }).eq("id", aff_id).execute()
        except Exception as aff_e:
            print(f"[DIRECT_WALLET] Affiliate update warning: {aff_e}")

    # 9. Send Instant Push Alert to Telegram Support Bot
    send_direct_wallet_support_alert(
        user_email=user_email,
        sender_mobile=clean_mobile,
        transaction_id=clean_tx,
        amount_egp=final_price,
        plan_id=requested_plan,
        promo_code=applied_promo,
        order_id=order_id,
    )

    return {
        "ok": True,
        "status": "approved",
        "order_id": order_id,
        "plan_id": requested_plan,
        "amount_egp": final_price,
        "telegram_pro_url": invite_link,
        "subscription_end": subscription_end,
    }
