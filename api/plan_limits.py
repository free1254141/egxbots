"""
Centralized plan / feature limits for EGX Bots.

Single source of truth for the two tiers:
  FREE  - (when PAYMENTS_ENABLED=true) signals delayed 15 days, 10 chat msgs once per email lifetime (no monthly reset), 5 portfolio stocks.
  PRO   - 200 EGP: daily signals, 350 chat msgs/month, 15 portfolio stocks.

When PAYMENTS_ENABLED is false (default) the platform is FREE-UNLIMITED:
no delays, no message cap, and no portfolio stock cap. This keeps the site
completely free until the operator flips the flag.
"""
import os
from typing import Any, Dict

from api.payment_common import is_payments_enabled, plan_amount_egp, plan_amount_egp


# ---------------------------------------------------------------------------
# Tiers
# ---------------------------------------------------------------------------

def free_limits() -> Dict[str, Any]:
    return {
        "name": "free",
        "signal_delay_days": int(os.getenv("FREE_SIGNAL_DELAY_DAYS", "15")),
        "chat_messages_daily": 10,
        "chat_messages_per_month": 10,
        "portfolio_stocks": int(os.getenv("FREE_PORTFOLIO_STOCKS", "5")),
        "price_egp": 0,
    }


def chat_only_limits() -> Dict[str, Any]:
    return {
        "name": "chat_only",
        "signal_delay_days": 0,
        "chat_messages_daily": int(os.getenv("PRO_CHAT_DAILY_MESSAGES", "350")),
        "chat_messages_per_month": int(os.getenv("PRO_CHAT_MESSAGES", "350")),
        "portfolio_stocks": int(os.getenv("PRO_PORTFOLIO_STOCKS", "15")),
        "price_egp": int(plan_amount_egp("chat_only")),
    }


def vip_only_limits() -> Dict[str, Any]:
    return {
        "name": "vip_only",
        "signal_delay_days": 0,
        "chat_messages_daily": 10,
        "chat_messages_per_month": 10,
        "portfolio_stocks": int(os.getenv("FREE_PORTFOLIO_STOCKS", "5")),
        "price_egp": int(plan_amount_egp("vip_only")),
    }


def pro_limits() -> Dict[str, Any]:
    return {
        "name": "pro",
        "signal_delay_days": 0,
        "chat_messages_daily": int(os.getenv("PRO_CHAT_DAILY_MESSAGES", "350")),
        "chat_messages_per_month": int(os.getenv("PRO_CHAT_MESSAGES", "350")),
        "portfolio_stocks": int(os.getenv("PRO_PORTFOLIO_STOCKS", "15")),
        "price_egp": int(plan_amount_egp("pro")),
    }


FULL_PRO_PLAN_IDS = frozenset({"pro", "pro_6m", "pro_1y", "lifetime", "pro_lifetime"})
CHAT_PRO_PLAN_IDS = FULL_PRO_PLAN_IDS | frozenset({"chat_only"})
VIP_TELEGRAM_PLAN_IDS = FULL_PRO_PLAN_IDS | frozenset({"vip_only"})
ALL_PAID_PLAN_IDS = FULL_PRO_PLAN_IDS | frozenset({"chat_only", "vip_only"})
PRO_PLAN_IDS = ALL_PAID_PLAN_IDS


def plan_limits(plan_id: str) -> Dict[str, Any]:
    clean = (plan_id or "").strip().lower()
    if clean == "chat_only":
        return chat_only_limits()
    if clean == "vip_only":
        return vip_only_limits()
    if clean in FULL_PRO_PLAN_IDS:
        return pro_limits()
    return free_limits()


def effective_limits(plan_id: str) -> Dict[str, Any]:
    """Return limits actually in force for a plan.

    When payments are disabled the platform is FREE-UNLIMITED regardless of
    plan_id so the site stays free.
    """
    if not is_payments_enabled():
        return {
            "name": "free",
            "signal_delay_days": 0,
            "chat_messages_daily": 10 ** 9,
            "chat_messages_per_month": 10 ** 9,  # effectively unlimited
            "portfolio_stocks": 10 ** 9,
            "price_egp": 0,
            "billing": "disabled",
        }
    limits = plan_limits(plan_id)
    limits["billing"] = "enabled"
    return limits


def _user_has_plan_in_set(user_id: str, supabase, allowed_plans: frozenset[str]) -> bool:
    if not is_payments_enabled():
        return True
    from dateutil import parser as date_parser
    from datetime import datetime, timezone

    try:
        res = (
            supabase.table("subscriptions")
            .select("plan_id,status,current_period_end")
            .eq("user_id", user_id)
            .in_("status", ["active", "trialing"])
            .order("updated_at", desc=True)
            .limit(5)
            .execute()
        )
        now = datetime.now(timezone.utc)
        for row in res.data or []:
            plan = str(row.get("plan_id", "")).lower()
            if plan not in allowed_plans:
                continue
            end = row.get("current_period_end")
            if end:
                try:
                    if date_parser.isoparse(end) < now:
                        continue  # expired
                except Exception:
                    pass
            return True
        return False
    except Exception:
        return False


def is_pro_user(user_id: str, supabase) -> bool:
    """True when the user holds any active paid/trial subscription (Pro, Chat Only, or VIP Only)."""
    return _user_has_plan_in_set(user_id, supabase, ALL_PAID_PLAN_IDS)


def has_chat_pro_user(user_id: str, supabase) -> bool:
    """True when the user holds an active Full Pro or AI Chat Only subscription."""
    return _user_has_plan_in_set(user_id, supabase, CHAT_PRO_PLAN_IDS)


def has_vip_telegram_user(user_id: str, supabase) -> bool:
    """True when the user holds an active Full Pro or VIP Telegram Only subscription."""
    return _user_has_plan_in_set(user_id, supabase, VIP_TELEGRAM_PLAN_IDS)


def user_is_pro(user_id: str, supabase) -> bool:
    return is_pro_user(user_id, supabase)


# ---------------------------------------------------------------------------
# Telegram destination
# ---------------------------------------------------------------------------

def telegram_recommendations_target() -> str:
    """Chat target that daily recommendations are published to.

    Until the global pricing flag (PAYMENTS_ENABLED) is activated, signals stay
    on the OLD public channel/topic so nothing changes for current members.
    Only after billing is enabled does it switch to the new group
    (TELEGRAM_RECOMMENDATIONS_CHAT_ID), then TELEGRAM_CHAT_ID, then the legacy
    public channel.
    """
    if not is_payments_enabled():
        return "-1002083067817_153"  # legacy public channel while free

    target = os.getenv("TELEGRAM_RECOMMENDATIONS_CHAT_ID", "").strip()
    if target:
        return target
    target = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if target:
        return target
    return "-1002083067817_153"


def telegram_free_channel_target() -> str:
    """Legacy public channel/topic used for delayed content and upgrade notices."""
    return os.getenv("TELEGRAM_FREE_CHAT_ID", "-1002083067817_153").strip()


def telegram_pro_channel_target() -> str:
    """Private Pro channel/group used for live recommendations and updates."""
    return os.getenv("TELEGRAM_PRO_CHAT_ID", os.getenv("TELEGRAM_RECOMMENDATIONS_CHAT_ID", "")).strip()


def telegram_public_link() -> str:
    """Invite/link for the channel shown in chatbot footers."""
    # While free, point users at the old channel; switch to the new group only
    # once billing is enabled.
    if not is_payments_enabled():
        return os.getenv("TELEGRAM_PUBLIC_LINK_FREE", "https://t.me/egxbots/153").strip()
    return os.getenv("TELEGRAM_PUBLIC_LINK", "https://t.me/egxbots").strip()


def free_channel_notice() -> str:
    return f"i️ القناة المجانية تعرض التوصيات والتعديلات بتأخير {free_limits()['signal_delay_days']} يوماً. التحديث اللحظي متاح لمشتركي Pro فقط."
