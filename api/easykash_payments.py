"""EasyKash hosted-checkout integration for Pro subscriptions."""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import requests

from api.stock_ai import _init_supabase, supabase
from api.payment_common import (
    activate_subscription,
    billing_settings,
    is_payments_enabled,
    plan_amount_egp,
    pro_discount,
    pro_regular_amount_egp,
    is_user_eligible_for_50_egp_renewal,
    is_user_eligible_for_100_egp_renewal,
    founders_offer_is_open,
)
from api.telegram_pro_invites import ensure_pro_invite


_EASYKASH_PAY_URL = "https://back.easykash.net/api/directpayv1/pay"
# EasyKash Hosted Checkout payment-option IDs for installments and BNPL.
# Keep method selection on EasyKash while preventing credit/installment offers.
_EASYKASH_INSTALLMENT_OPTIONS = [
    3,  # Qassatly
    8, 9, 10,  # NBE installments
    17,  # ValU
    18, 19, 20,  # Banque Misr installments
    21,  # Aman installments
    22,  # Souhoula
    23,  # Contact
    24,  # Mogo / MidTakseet
    25,  # Blnk
    26, 27, 28,  # Multiple-bank installments
    29,  # Halan
    32,  # TRU
    33,  # Klivvr (shown under EasyKash Installments)
    34,  # Forsa
]
_PLANS = {"pro": 30, "pro_renewal": 30, "pro_6m": 180, "pro_1y": 365, "lifetime": 36500}
_ACTIVE_PRO_PLAN_IDS = list(_PLANS)


def _hosted_checkout_url(value: Any) -> str:
    """Accept only EasyKash hosted payment links and avoid its www redirect hop."""
    if not isinstance(value, str):
        raise RuntimeError("EasyKash returned an invalid checkout URL")
    parsed = urlsplit(value)
    path_parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"easykash.net", "www.easykash.net"}
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or len(path_parts) != 2
        or path_parts[0] != "DirectPayV1"
        or not path_parts[1].isalnum()
    ):
        raise RuntimeError("EasyKash returned an invalid checkout URL")
    return urlunsplit(("https", "www.easykash.net", f"/DirectPayV1/{path_parts[1]}", "", ""))


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def is_easykash_ready() -> bool:
    return bool(os.getenv("EASYKASH_API_KEY", "").strip() and os.getenv("EASYKASH_CALLBACK_SECRET", "").strip())


def payment_config(user_id: str | None = None) -> Dict[str, Any]:
    from api.plan_limits import free_limits, pro_limits

    enabled = is_payments_enabled() and is_easykash_ready()
    discount = pro_discount()
    settings = billing_settings()

    from api.payment_common import is_user_eligible_for_50_egp_renewal, is_user_eligible_for_100_egp_renewal, founders_offer_is_open
    is_eligible_50 = is_user_eligible_for_50_egp_renewal(user_id) if user_id else False
    is_eligible_100 = is_user_eligible_for_100_egp_renewal(user_id) if user_id else False
    monthly_amount = float(plan_amount_egp("pro", user_id=user_id))
    
    monthly = {
        "id": "pro",
        "name_ar": "شهري",
        "name_en": "Monthly",
        "amount_egp": int(monthly_amount),
        "days": 30,
        "is_grandfathered_renewal": is_eligible_50,
        "is_grandfathered_100": is_eligible_100,
        "founders_lock_rate": 50 if is_eligible_50 else (100 if (is_eligible_100 or founders_offer_is_open()) else None),
    }
    if discount["active"]:
        monthly["discount"] = {
            "active": True,
            "label_ar": str(settings.get("discount_label_ar") or "عرض محدود"),
            "label_en": str(settings.get("discount_label_en") or "Limited offer"),
            "original_amount_egp": int(pro_regular_amount_egp()),
            "ends_at": discount["ends_at"],
        }
    plans = [
        monthly,
        {"id": "pro_6m", "name_ar": "6 شهور", "name_en": "6 Months", "amount_egp": int(plan_amount_egp("pro_6m")), "days": 180},
        {"id": "pro_1y", "name_ar": "سنة", "name_en": "1 Year", "amount_egp": int(plan_amount_egp("pro_1y")), "days": 365},
        {
            "id": "lifetime",
            "name_ar": "مدى الحياة (Lifetime)",
            "name_en": "Lifetime Deal",
            "amount_egp": int(plan_amount_egp("lifetime")),
            "days": 36500,
            "badge": "حصري لـ 20 مقعداً 🔥",
        },
    ]
    # Founders offer - time-limited (15 days): strictly time-limited
    from api.payment_common import founders_offer_ends_at, founders_offer_is_open
    _founders_ends_at = founders_offer_ends_at()
    _founders_is_open = founders_offer_is_open()
    _founders_ends_at_str = _founders_ends_at.isoformat().replace("+00:00", "Z") if _founders_ends_at else "2026-11-14T01:00:00Z"

    # Lifetime spots counter: strictly limited to 20 users only
    lifetime_limit = int(settings.get("lifetime_limit") or os.getenv("LIFETIME_LIMIT", "20"))
    lifetime_count = 0
    try:
        if supabase:
            res_life = supabase.table("subscriptions").select("user_id", count="exact").eq("status", "active").eq("plan_id", "lifetime").execute()
            if res_life and res_life.data:
                lifetime_count = len(set(r.get("user_id") for r in res_life.data if r.get("user_id")))
            else:
                lifetime_count = res_life.count or 0
    except Exception:
        lifetime_count = 0
    lifetime_remaining = max(0, lifetime_limit - lifetime_count)

    return {
        "enabled": enabled,
        "mode": "easykash" if enabled else "disabled",
        "provider": "easykash",
        "currency": "EGP",
        "plans": plans,
        "limits": {"free": free_limits(), "pro": pro_limits()},
        "founders": {
            "limit": None,
            "count": None,
            "remaining": None,
            "is_open": _founders_is_open,
            "price_egp": 50 if is_eligible_50 else 100,
            "regular_price_egp": int(pro_regular_amount_egp()),
            "ends_at": _founders_ends_at_str,
            "is_grandfathered": is_eligible_50,
        },
        "lifetime": {
            "limit": lifetime_limit,
            "count": lifetime_count,
            "remaining": lifetime_remaining,
            "is_open": lifetime_remaining > 0,
            "price_egp": int(plan_amount_egp("lifetime")),
        },
    }


def _customer_reference(value: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Invalid payment order reference") from exc


def _direct_pay_payload(
    amount: Decimal,
    name: str,
    email: str,
    mobile: str,
    redirect_url: str,
    customer_reference: str,
) -> Dict[str, Any]:
    """Let EasyKash present enabled methods, excluding installments and BNPL."""
    return {
        "amount": float(amount),
        "currency": "EGP",
        "paymentOptionsExcluded": list(_EASYKASH_INSTALLMENT_OPTIONS),
        "cashExpiry": int(os.getenv("EASYKASH_CASH_EXPIRY_HOURS", os.getenv("EASYKASH_CASH_EXPIRY_DAYS", "3"))),
        "name": (name or "EGX Bots user")[:100],
        "email": (email or "")[:254],
        "mobile": mobile,
        "redirectUrl": redirect_url,
        "customerReference": customer_reference,
    }


def create_checkout(user_id: str, plan_id: str, email: str, name: str, mobile: str) -> Dict[str, Any]:
    if not is_payments_enabled():
        raise RuntimeError("Payments are currently disabled")
    if not is_easykash_ready():
        raise RuntimeError("EasyKash credentials are not fully configured")
    plan_id = (plan_id or "").strip().lower()
    if plan_id not in _PLANS:
        raise ValueError("Unsupported Pro plan")
    mobile = "".join(ch for ch in str(mobile or "") if ch.isdigit() or ch == "+")
    if not (mobile.startswith("01") and len(mobile) == 11 and mobile.isdigit()):
        raise ValueError("Enter a valid Egyptian mobile number (010/011/012/015)")
    _init_supabase()
    if not supabase:
        raise RuntimeError("Supabase is not initialized")

    if plan_id == "lifetime":
        life_limit = int(billing_settings().get("lifetime_limit") or os.getenv("LIFETIME_LIMIT", "20"))
        try:
            res_check = supabase.table("subscriptions").select("user_id", count="exact").eq("status", "active").eq("plan_id", "lifetime").execute()
            current_life = len(set(r.get("user_id") for r in res_check.data if r.get("user_id"))) if (res_check and res_check.data) else (res_check.count or 0)
            if current_life >= life_limit:
                raise ValueError("عذراً، اكتملت جميع مقاعد باقة مدى الحياة (20/20)")
        except ValueError:
            raise
        except Exception:
            pass

    order_id = str(uuid4())
    actual_plan_id = plan_id
    if plan_id in ("pro", "pro_renewal"):
        if is_user_eligible_for_50_egp_renewal(user_id):
            actual_plan_id = "pro_renewal"
            amount = Decimal("50.00")
        elif is_user_eligible_for_100_egp_renewal(user_id) or founders_offer_is_open():
            actual_plan_id = "pro"
            amount = Decimal("100.00")
        else:
            actual_plan_id = "pro"
            amount = Decimal(str(plan_amount_egp("pro", user_id=user_id))).quantize(Decimal("0.01"))
    else:
        amount = Decimal(str(plan_amount_egp(plan_id, user_id=user_id))).quantize(Decimal("0.01"))

    row = {
        "id": order_id,
        "user_id": user_id,
        "plan_id": actual_plan_id,
        "amount_egp": float(amount),
        "provider": "easykash",
        "status": "pending",
        "payment_review_status": "pending_review",
    }
    inserted = supabase.table("local_payment_orders").insert(row).execute()
    if not inserted.data:
        raise RuntimeError("Could not create payment order")
    try:
        supabase.table("profiles").update({"whatsapp_number": mobile, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", user_id).execute()
    except Exception as exc:
        print(f"[EASYKASH] Warning: could not update profile whatsapp_number: {exc}")

    origin = os.getenv("WEB_ORIGIN", "https://egxbots.com").strip().rstrip("/")
    return_url = f"{origin}/profile?payment=easykash&customerReference={order_id}"
    try:
        payload = _direct_pay_payload(amount, name, email, mobile, return_url, order_id)
        response = requests.post(
            os.getenv("EASYKASH_PAY_API_URL", _EASYKASH_PAY_URL),
            json=payload,
            headers={"authorization": _required_env("EASYKASH_API_KEY"), "Content-Type": "application/json"},
            timeout=(5, 25),
        )
        if response.status_code >= 300:
            raise RuntimeError(f"EasyKash checkout failed ({response.status_code})")
        data = response.json()
        redirect_url = _hosted_checkout_url(data.get("redirectUrl"))
        if os.getenv("NOTIFY_TELEGRAM_ON_PAYMENT", "false").lower() in ("true", "1"):
            try:
                from api.support_chat import send_telegram_message, load_admin_chat_id
                admin_chat = load_admin_chat_id()
                if admin_chat:
                    plan_days = _PLANS.get(plan_id, 30)
                    msg = (
                        f"🛒 <b>طلب اشتراك جديد (قيد الدفع)</b>\n\n"
                        f"<b>الخطة:</b> Pro ({plan_days} يوم)\n"
                        f"<b>المبلغ:</b> {float(amount):,.0f} ج.م\n"
                        "<b>وسيلة الدفع:</b> يحددها العميل داخل بوابة EasyKash\n"
                        f"<b>الموبايل:</b> <code>{mobile}</code>\n"
                        f"<b>البريد:</b> <code>{email or '—'}</code>\n"
                        f"<b>الاسم:</b> {name or 'عميل'}\n"
                        f"<b>Order ID:</b> <code>{order_id}</code>\n\n"
                        f"⏳ العميل انتقل لصفحة EasyKash لإتمام العملية."
                    )
                    send_telegram_message(admin_chat, msg)
            except Exception as notify_err:
                print(f"[EASYKASH] Telegram admin checkout notification error: {notify_err}")
        return {"order_id": order_id, "plan_id": plan_id, "amount_egp": float(amount), "url": redirect_url, "status": "pending"}
    except Exception:
        supabase.table("local_payment_orders").update({"status": "expired", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", order_id).eq("status", "pending").execute()
        raise


def _verify_callback(payload: Dict[str, Any]) -> bool:
    signature = str(payload.get("signatureHash") or "").strip().lower()
    if len(signature) != 128:
        return False
    # EasyKash callback docs define the signature input in this exact field order.
    signed_fields = ("ProductCode", "Amount", "ProductType", "PaymentMethod", "status", "easykashRef", "customerReference")
    if any(payload.get(key) is None for key in signed_fields):
        return False
    message = "".join(str(payload[key]) for key in signed_fields).encode("utf-8")
    expected = hmac.new(_required_env("EASYKASH_CALLBACK_SECRET").encode("utf-8"), message, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False
    expected_product = os.getenv("EASYKASH_PRODUCT_CODE", "").strip()
    return not expected_product or str(payload.get("ProductCode") or "") == expected_product


def process_callback(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not _verify_callback(payload):
        return {"ok": False, "status_code": 401, "code": "invalid_signature"}
    try:
        order_id = _customer_reference(str(payload.get("customerReference") or ""))
    except ValueError:
        return {"ok": False, "status_code": 400, "code": "invalid_reference"}

    _init_supabase()
    if not supabase:
        return {"ok": False, "status_code": 503, "code": "database_unavailable"}
    result = supabase.table("local_payment_orders").select("id,user_id,plan_id,amount_egp,status,provider,updated_at").eq("id", order_id).maybe_single().execute()
    order = result.data if result else None
    if not order or order.get("provider") != "easykash":
        return {"ok": False, "status_code": 404, "code": "order_not_found"}
    try:
        received = Decimal(str(payload.get("Amount"))).quantize(Decimal("0.01"))
        expected_amount = Decimal(str(order.get("amount_egp"))).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        return {"ok": False, "status_code": 400, "code": "invalid_amount"}
    if received != expected_amount or str(payload.get("status", "")).upper() != "PAID":
        if os.getenv("NOTIFY_TELEGRAM_ON_PAYMENT", "false").lower() in ("true", "1"):
            try:
                from api.support_chat import send_telegram_message, load_admin_chat_id
                admin_chat = load_admin_chat_id()
                if admin_chat:
                    easykash_ref = str(payload.get("easykashRef") or "—")
                    failed_status = str(payload.get("status", "FAILED"))
                    msg = (
                        f"⚠️ <b>إشعار عدم اكتمال الدفع من EasyKash</b>\n\n"
                        f"<b>Order ID:</b> <code>{order_id}</code>\n"
                        f"<b>حالة الدفع:</b> {failed_status}\n"
                        f"<b>المبلغ المستلم:</b> {float(received):,.0f} ج.م (المتوقع: {float(expected_amount):,.0f} ج.م)\n"
                        f"<b>رقم المرجع:</b> <code>{easykash_ref}</code>"
                    )
                    send_telegram_message(admin_chat, msg)
            except Exception:
                pass
        return {"ok": True, "code": "payment_not_paid_or_amount_mismatch"}

    now = datetime.now(timezone.utc).isoformat()
    if order.get("status") == "approved":
        return {"ok": True, "code": "already_processed"}
    if order.get("status") not in {"pending", "submitted"}:
        return {"ok": True, "code": "order_not_pending"}

    # Reuse the table's established `submitted` state as a short processing
    # lease, so we do not introduce an unsupported status value into old schemas.
    if order.get("status") == "submitted":
        updated_at = order.get("updated_at")
        try:
            lease_expired = updated_at and (datetime.now(timezone.utc) - datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))).total_seconds() > 300
        except ValueError:
            lease_expired = True
        if not lease_expired:
            return {"ok": False, "status_code": 503, "code": "callback_processing"}
        claim_query = supabase.table("local_payment_orders").update({"updated_at": now}).eq("id", order_id).eq("status", "submitted").eq("updated_at", updated_at)
    else:
        claim_query = supabase.table("local_payment_orders").update({"status": "submitted", "updated_at": now}).eq("id", order_id).eq("status", "pending")
    claimed = claim_query.execute()
    if not claimed.data:
        latest = supabase.table("local_payment_orders").select("status").eq("id", order_id).maybe_single().execute()
        if (latest.data or {}).get("status") == "approved":
            return {"ok": True, "code": "already_processed"}
        return {"ok": False, "status_code": 503, "code": "callback_processing"}
    try:
        activate_subscription(order["user_id"], order.get("plan_id") or "pro", provider="easykash", payment_order_id=order_id)
        supabase.table("local_payment_orders").update({
            "status": "approved",
            "payment_review_status": "reviewed",
            "payment_reviewed_at": now,
            "customer_note": f"EasyKash reference: {str(payload.get('easykashRef') or '')[:100]}",
            "updated_at": now,
        }).eq("id", order_id).eq("status", "submitted").execute()
    except Exception as exc:
        supabase.table("local_payment_orders").update({"status": "pending", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", order_id).eq("status", "submitted").execute()
        print(f"[EASYKASH] callback processing failed for order {order_id}: {type(exc).__name__}")
        return {"ok": False, "status_code": 503, "code": "processing_failed"}
    # Telegram is downstream of payment approval. Invite failures must not
    # roll the paid order back to pending or re-activate the same payment.
    try:
        sub = supabase.table("subscriptions").select("current_period_end").eq("user_id", order["user_id"]).in_("plan_id", _ACTIVE_PRO_PLAN_IDS).eq("status", "active").order("current_period_end", desc=True).limit(1).maybe_single().execute()
        subscription_end = (sub.data or {}).get("current_period_end") if sub and sub.data else None
        if subscription_end:
            invite = ensure_pro_invite(order["user_id"], str(subscription_end))
            invite_link = str((invite or {}).get("invite_link") or "").strip()
            try:
                from api.telegram_pro_invites import send_pro_welcome_to_user_telegram
                sent = send_pro_welcome_to_user_telegram(
                    order["user_id"],
                    invite_link=invite_link,
                    plan_name="Pro",
                    subscription_end=str(subscription_end),
                )
                if sent:
                    note = str(order.get("customer_note") or "")
                    supabase.table("local_payment_orders").update({
                        "customer_note": f"{note} | tg_welcomed".strip(" |")
                    }).eq("id", order_id).execute()
            except Exception as tg_err:
                print(f"[EASYKASH] Welcome telegram dispatch warning: {tg_err}")
    except Exception as exc:
        print(f"[EASYKASH] VIP invite deferred for order {order_id}: {type(exc).__name__}")

    # Notify admin on Telegram about confirmed payment and Pro activation (silenced by default)
    if os.getenv("NOTIFY_TELEGRAM_ON_PAYMENT", "false").lower() in ("true", "1"):
        try:
            from api.support_chat import send_telegram_message, load_admin_chat_id
            admin_chat = load_admin_chat_id()
            if admin_chat:
                plan_id = order.get("plan_id", "pro")
                plan_days = _PLANS.get(plan_id, 30)
                easykash_ref = str(payload.get("easykashRef") or "—")
                msg = (
                    f"🎉 <b>تم تأكيد الدفع وتفعيل Pro بنجاح!</b>\n\n"
                    f"<b>الخطة:</b> Pro ({plan_days} يوم)\n"
                    f"<b>المبلغ المدفوع:</b> {float(expected_amount):,.0f} ج.م\n"
                    f"<b>رقم المرجع (EasyKash):</b> <code>{easykash_ref}</code>\n"
                    f"<b>Order ID:</b> <code>{order_id}</code>\n"
                    f"<b>User ID:</b> <code>{order['user_id']}</code>\n"
                    f"<b>نهاية الاشتراك:</b> {subscription_end or 'مفعل'}\n\n"
                    f"✅ تم تفعيل الاشتراك تلقائياً ورابط VIP متاح للمشترك."
                )
                send_telegram_message(admin_chat, msg)
        except Exception as notify_err:
            print(f"[EASYKASH] Telegram admin activation notification error: {notify_err}")

    return {"ok": True, "code": "payment_activated"}


def order_status(order_id: str, user_id: str) -> Dict[str, Any]:
    order_id = _customer_reference(order_id)
    _init_supabase()
    result = supabase.table("local_payment_orders").select("id,plan_id,amount_egp,status,provider,telegram_invite_link,telegram_invite_expires_at,customer_note").eq("id", order_id).eq("user_id", user_id).eq("provider", "easykash").maybe_single().execute()
    order = result.data if result else None
    if not order:
        raise ValueError("Payment order not found")
    end = None
    invite_link = ""
    if order.get("status") == "approved":
        sub = supabase.table("subscriptions").select("current_period_end").eq("user_id", user_id).in_("plan_id", _ACTIVE_PRO_PLAN_IDS).eq("status", "active").order("current_period_end", desc=True).limit(1).maybe_single().execute()
        end = (sub.data or {}).get("current_period_end") if sub and sub.data else None
        if end:
            invite = ensure_pro_invite(user_id, str(end))
            invite_link = str(invite.get("invite_link") or "")
            note = str(order.get("customer_note") or "")
            if "tg_welcomed" not in note:
                try:
                    from api.telegram_pro_invites import send_pro_welcome_to_user_telegram
                    sent = send_pro_welcome_to_user_telegram(user_id, invite_link=invite_link, subscription_end=str(end))
                    if sent:
                        supabase.table("local_payment_orders").update({
                            "customer_note": f"{note} | tg_welcomed".strip(" |")
                        }).eq("id", order_id).execute()
                except Exception as tg_status_err:
                    print(f"[EASYKASH] Status welcome telegram dispatch warning: {tg_status_err}")
    return {**order, "subscription": {"current_period_end": end} if end else None, "telegram_pro_url": invite_link}
