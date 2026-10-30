"""Shared billing flags, prices and Pro entitlement activation."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta

from api.stock_ai import _init_supabase, supabase

_SETTINGS_CACHE_SECONDS = 15
_settings_cache: dict = {"fetched_at": 0.0, "row": None}


def founders_offer_ends_at() -> datetime | None:
    """Return the founders offer expiry datetime (UTC), or None if unlimited.

    Priority:
    1. local_billing_settings.founders_offer_ends_at (if configured in DB).
    2. FOUNDERS_OFFER_ENDS_AT env var (ISO 8601 string).
    3. If neither is set, returns None (no time limit).
    """
    settings = billing_settings()
    raw = (settings.get("founders_offer_ends_at") or os.getenv("FOUNDERS_OFFER_ENDS_AT", "") or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def founders_offer_is_open() -> bool:
    """Return True if the founders offer is still within its active time window."""
    ends = founders_offer_ends_at()
    if ends is None:
        return True  # No expiry set = always open
    return datetime.now(timezone.utc) < ends


def is_payments_enabled() -> bool:
    return os.getenv("PAYMENTS_ENABLED", "false").strip().lower() not in {"", "0", "false", "no", "off"}


def billing_settings() -> dict:
    """Admin-managed billing row from local_billing_settings, cached briefly.

    Returns an empty dict when the table is missing or unreachable, so prices
    fall back to env defaults and checkout never breaks on a settings outage.
    """
    now = time.monotonic()
    if now - _settings_cache["fetched_at"] < _SETTINGS_CACHE_SECONDS:
        return _settings_cache["row"] or {}
    row: dict = {}
    try:
        _init_supabase()
        if supabase:
            result = supabase.table("local_billing_settings").select("*").eq("id", 1).maybe_single().execute()
            row = (result.data if result else None) or {}
    except Exception:
        row = {}
    _settings_cache["fetched_at"] = now
    _settings_cache["row"] = row or None
    return row


def _env_price(name: str, fallback: float) -> float:
    try:
        return float(os.getenv(name, str(fallback)))
    except ValueError:
        return fallback


def pro_discount() -> dict:
    """Return the currently-active limited-time Pro discount window, if any.

    Admin settings (local_billing_settings) take precedence; env variables
    PRO_DISCOUNT_PRICE_EGP + PRO_DISCOUNT_ENDS_AT are the fallback. Missing,
    invalid, or past end means no discount.
    """
    inactive = {"active": False, "price_egp": None, "ends_at": None}
    settings = billing_settings()
    if "discount_enabled" in settings:
        if not settings.get("discount_enabled"):
            return inactive
        price = settings.get("discount_price_egp")
        end_raw = settings.get("discount_ends_at")
    else:
        price = str(os.getenv("PRO_DISCOUNT_PRICE_EGP", "")).strip()
        end_raw = str(os.getenv("PRO_DISCOUNT_ENDS_AT", "")).strip()
    if price in (None, "") or not end_raw:
        return inactive
    try:
        price_value = float(price)
        ends_at = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return inactive
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)
    if price_value <= 0 or datetime.now(timezone.utc) >= ends_at:
        return inactive
    return {"active": True, "price_egp": price_value, "ends_at": ends_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}


def pro_discount_active() -> bool:
    return pro_discount()["active"]


def is_user_eligible_for_50_egp_renewal(user_id: str | None) -> bool:
    """Determine if a user qualifies for grandfathered 50 EGP monthly renewal.

    Rules:
    1. User must have previously joined under the 50 EGP founders era (tracked in founders_offer_members or 50 EGP orders).
    2. User is currently active, OR expired within the 3-day grace period (72 hours).
    3. If expired > 3 days ago without renewing, or new user, eligibility is forfeited (price becomes 100 EGP).
    """
    if not user_id:
        return False
    try:
        _init_supabase()
        if not supabase:
            return False

        # 1. Did the user join under founders offer or pay 50 EGP previously?
        in_members = supabase.table("founders_offer_members").select("user_id").eq("user_id", user_id).limit(1).execute().data
        had_50_order = supabase.table("local_payment_orders").select("id").eq("user_id", user_id).eq("amount_egp", 50.0).limit(1).execute().data
        if not in_members and not had_50_order:
            return False

        # 2. Check current subscription status & grace period (use order/limit to avoid PGRST116)
        sub_res = supabase.table("subscriptions").select("status, current_period_end").eq("user_id", user_id).order("current_period_end", desc=True).limit(1).execute()
        sub = (sub_res.data or [None])[0]
        if not sub:
            return False

        end_str = sub.get("current_period_end")
        status = sub.get("status")
        now = datetime.now(timezone.utc)
        if end_str:
            try:
                end_dt = datetime.fromisoformat(str(end_str).replace("Z", "+00:00"))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                if now < end_dt:
                    return True
                if now <= end_dt + timedelta(days=3):
                    return True
                return False
            except Exception:
                pass

        return status in ("active", "trialing")
    except Exception as exc:
        print(f"[BILLING] Error checking 50 EGP eligibility for {user_id}: {exc}")
        return False


def is_user_eligible_for_100_egp_renewal(user_id: str | None) -> bool:
    """Determine if a user qualifies for grandfathered 100 EGP monthly renewal for life.

    Rules:
    1. User joined under founders offer (tracked in founders_offer_members or approved 100 EGP orders).
    2. User is currently active, OR expired within the 3-day grace period (72 hours).
    3. If expired > 3 days ago without renewing, eligibility is forfeited (reverts to regular 200 EGP once offer ends).
    """
    if not user_id:
        return False
    try:
        _init_supabase()
        if not supabase:
            return False

        # If they qualify for 50 EGP grandfathering, that takes precedence
        if is_user_eligible_for_50_egp_renewal(user_id):
            return False

        # Did the user join under founders offer or pay 100 EGP previously?
        in_members = supabase.table("founders_offer_members").select("user_id").eq("user_id", user_id).limit(1).execute().data
        had_100_order = supabase.table("local_payment_orders").select("id").eq("user_id", user_id).in_("plan_id", ["pro", "pro_renewal"]).eq("status", "approved").limit(1).execute().data
        if not in_members and not had_100_order:
            return False

        # Check current subscription status & grace period (use order/limit to avoid PGRST116)
        sub_res = supabase.table("subscriptions").select("status, current_period_end").eq("user_id", user_id).order("current_period_end", desc=True).limit(1).execute()
        sub = (sub_res.data or [None])[0]
        if not sub:
            return False

        end_str = sub.get("current_period_end")
        status = sub.get("status")
        now = datetime.now(timezone.utc)
        if end_str:
            try:
                end_dt = datetime.fromisoformat(str(end_str).replace("Z", "+00:00"))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                if now < end_dt:
                    return True
                if now <= end_dt + timedelta(days=3):
                    return True
                return False
            except Exception:
                pass

        return status in ("active", "trialing")
    except Exception as exc:
        print(f"[BILLING] Error checking 100 EGP eligibility for {user_id}: {exc}")
        return False


def plan_amount_egp(plan_id: str, user_id: str | None = None) -> float:
    plan = (plan_id or "").strip().lower()
    if plan == "pro_renewal":
        return 50.0
    if plan == "pro":
        if user_id:
            if is_user_eligible_for_50_egp_renewal(user_id):
                return 50.0
            if is_user_eligible_for_100_egp_renewal(user_id):
                return 100.0
        discount = pro_discount()
        if discount["active"]:
            return float(discount["price_egp"])
        settings = billing_settings()
        if settings.get("pro_price_egp") is not None:
            return float(settings["pro_price_egp"])
        return _env_price("PRO_PRICE_EGP", 200.0)
    if plan == "pro_6m":
        settings = billing_settings()
        if settings.get("pro_6m_price_egp") is not None:
            return float(settings["pro_6m_price_egp"])
        return _env_price("PRO_6M_PRICE_EGP", 1000)
    if plan == "pro_1y":
        settings = billing_settings()
        if settings.get("pro_1y_price_egp") is not None:
            return float(settings["pro_1y_price_egp"])
        return _env_price("PRO_1Y_PRICE_EGP", 1800)
    if plan in ("lifetime", "pro_lifetime"):
        settings = billing_settings()
        if settings.get("lifetime_price_egp") is not None:
            return float(settings["lifetime_price_egp"])
        return _env_price("LIFETIME_PRICE_EGP", 2250)
    return _env_price("PRO_PRICE_EGP", 100.0)


def pro_regular_amount_egp() -> float:
    """Base (undiscounted) monthly Pro price, for discount strike-through."""
    settings = billing_settings()
    if settings.get("founders_regular_price_egp") is not None:
        return float(settings["founders_regular_price_egp"])
    if settings.get("pro_price_egp") is not None:
        return float(settings["pro_price_egp"])
    return _env_price("PRO_REGULAR_PRICE_EGP", _env_price("PRO_PRICE_EGP", 200.0))


def subscription_days(plan_id: str) -> int:
    plan = (plan_id or "").strip().lower()
    return {"pro": 30, "pro_renewal": 30, "pro_6m": 180, "pro_1y": 365, "lifetime": 36500, "pro_lifetime": 36500}.get(plan, 30)


def activate_subscription(user_id: str, plan_id: str, provider: str = "easykash", payment_order_id: str | None = None) -> None:
    """Activate the subscription only after a verified gateway callback."""
    _init_supabase()
    if not supabase:
        raise RuntimeError("Supabase is not initialized")
    requested_plan = (plan_id or "pro").strip().lower()
    stored_plan = "pro" if requested_plan in {"pro", "pro_renewal", "pro_6m", "pro_1y"} else ("lifetime" if requested_plan in {"lifetime", "pro_lifetime"} else requested_plan)
    if not payment_order_id:
        raise ValueError("Payment order id is required for idempotent activation")
    supabase.rpc("activate_easykash_subscription", {
        "p_user_id": user_id,
        "p_plan_id": stored_plan,
        "p_duration_days": subscription_days(requested_plan),
        "p_provider": provider,
        "p_payment_order_id": payment_order_id,
        "p_price_monthly_cents": int(round(plan_amount_egp(requested_plan, user_id=user_id) * 100)),
    }).execute()
    # Enroll user in founders_offer_members so they lock in founders rates for life
    if requested_plan in {"pro", "pro_renewal"} and founders_offer_is_open():
        try:
            supabase.table("founders_offer_members").upsert({"user_id": user_id}).execute()
        except Exception as _fe:
            pass
