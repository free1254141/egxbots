"""
api/agentic_chat/auth_guard.py
Authentication, Quota enforcement, and Security Sanitization for EGX Bots Agentic Chatbot.
"""

import base64
import json
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple

from fastapi import Request
import pytz

from api.stock_ai import _init_supabase, supabase
from api.plan_limits import is_pro_user, effective_limits
from api.payment_common import is_payments_enabled, plan_amount_egp, founders_offer_is_open

CAIRO_TZ = pytz.timezone("Africa/Cairo")

BLOCKED_INPUT_PATTERNS = [
    "system prompt", "ignore previous instructions", "ignore all previous",
    "developer mode", "jailbreak", "admin_secret_key", "service_role_key",
    "بيانات سرية للمستخدمين", "كلمة سر السيرفر", "اختراق الموقع", "اختراق السيرفر", "اختراق النظام"
]

BLOCKED_OUTPUT_REGEX = re.compile(
    r"(اشتري الآن|شراء فوراً|شراء الان|أرباح مؤكدة|guaranteed profits|buy now)",
    re.IGNORECASE
)


def _get_sb():
    """Return active Supabase client while preserving monkeypatched `auth_guard.supabase` in tests."""
    global supabase
    if supabase is not None:
        return supabase
    _init_supabase()
    try:
        import api.stock_ai as _stock_ai
        if getattr(_stock_ai, "supabase", None) is not None:
            supabase = _stock_ai.supabase
    except Exception:
        pass
    return supabase


def get_cairo_date_string() -> str:
    """Return current date in Cairo timezone as YYYY-MM-DD."""
    return datetime.now(CAIRO_TZ).strftime("%Y-%m-%d")


def extract_jwt_token(request: Request) -> Optional[str]:
    """
    Extract Supabase JWT token from:
    1. Authorization: Bearer <token>
    2. Cookies (sb-access-token, sb-<project_ref>-auth-token, or chunked cookies)
    """
    # 1. Check Authorization header
    auth_header = request.headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    # 2. Check cookies
    cookies = request.cookies
    if "sb-access-token" in cookies:
        token = cookies["sb-access-token"].strip()
        if token:
            return token

    # 3. Check for sb-*-auth-token or chunked variants (Supabase SSR format)
    auth_cookie_keys = [k for k in cookies.keys() if "auth-token" in k]
    if auth_cookie_keys:
        base_names = set(k.split(".")[0] for k in auth_cookie_keys)
        for base in base_names:
            chunks = []
            idx = 0
            while f"{base}.{idx}" in cookies:
                chunks.append(cookies[f"{base}.{idx}"])
                idx += 1
            raw_val = "".join(chunks) if chunks else cookies.get(base, "")
            if not raw_val:
                continue

            # Handle base64- prefix used by @supabase/ssr (URL-safe base64 with missing padding)
            if raw_val.startswith("base64-"):
                try:
                    b64_str = raw_val[7:]
                    b64_str += "=" * (-len(b64_str) % 4)
                    raw_val = base64.urlsafe_b64decode(b64_str.encode("ascii")).decode("utf-8")
                except Exception:
                    try:
                        raw_val = base64.b64decode(raw_val[7:]).decode("utf-8")
                    except Exception:
                        pass

            # Parse JSON token bundle
            try:
                parsed = json.loads(raw_val)
                if isinstance(parsed, dict) and "access_token" in parsed:
                    return str(parsed["access_token"])
                if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], str):
                    return str(parsed[0])
            except Exception:
                pass

            # Raw JWT token
            if raw_val.count(".") == 2:
                return raw_val

    return None


def get_authenticated_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Verify JWT against Supabase Auth API and return authenticated user dict:
    {"id": user_id, "email": user_email, "is_authenticated": True}
    Returns None if token is invalid or absent.
    """
    # 1. Benchmark Guard (Strictly gated behind ALLOW_LOADTEST_BENCHMARK environment variable)
    allow_benchmark = os.getenv("ALLOW_LOADTEST_BENCHMARK", "").strip().lower() in ("true", "1")
    benchmark_secret = os.getenv("BENCHMARK_SECRET_KEY", "").strip()
    if allow_benchmark and benchmark_secret:
        header_bench = request.headers.get("x-benchmark-key", "").strip()
        auth_header = request.headers.get("authorization", "").strip()
        if header_bench == benchmark_secret or auth_header == f"Bearer {benchmark_secret}":
            return {
                "id": "00000000-0000-0000-0000-000000000000",
                "email": "benchmark@egxbots.com",
                "is_authenticated": True,
                "is_pro": True,
                "is_benchmark": True,
            }

    # 2. Trusted internal proxy check (e.g. from Vercel proxy with ADMIN_SECRET_KEY)
    admin_key = os.getenv("ADMIN_SECRET_KEY", "").strip()
    incoming_admin_key = (request.headers.get("x-admin-key") or "").strip()
    incoming_user_id = (request.headers.get("x-user-id") or "").strip()
    if admin_key and incoming_admin_key == admin_key and incoming_user_id:
        incoming_email = (request.headers.get("x-user-email") or "").strip()
        return {
            "id": incoming_user_id,
            "email": incoming_email,
            "is_authenticated": True,
        }

    # 3. Standard Supabase JWT token verification
    token = extract_jwt_token(request)
    if not token:
        return None

    try:
        sb = _get_sb()
        if not sb:
            return None
        res = sb.auth.get_user(token)
        if res and hasattr(res, "user") and res.user:
            return {
                "id": str(res.user.id),
                "email": getattr(res.user, "email", "") or "",
                "is_authenticated": True,
            }
    except Exception:
        pass

    return None


def _monthly_quota_start(user_id: Optional[str], is_pro: bool, today: str) -> str:
    """Return effective YYYY-MM-DD quota start date.

    Free users receive 10 messages ONCE per account lifetime (no monthly reset),
    whereas Pro subscribers reset per subscription/calendar month (350/month).
    """
    if not is_pro:
        return "1970-01-01"
    cal_month_start = f"{today[:7]}-01"
    sb = _get_sb()
    if not user_id or not sb:
        return cal_month_start
    try:
        from api.perf_utils import resolve_subscription_quota_window

        sub_res = (
            sb.table("subscriptions")
            .select("plan_id, status, current_period_start, current_period_end")
            .eq("user_id", user_id)
            .in_("status", ["active", "trialing"])
            .order("current_period_end", desc=True)
            .limit(5)
            .execute()
        )
        win = resolve_subscription_quota_window(sub_res.data or [])
        return str(win.get("effective_month_start_str") or cal_month_start)
    except Exception:
        return cal_month_start


def _fetch_bonus_balance(user_id: Optional[str]) -> int:
    """Return remaining admin/referral bonus chat credits for the user."""
    sb = _get_sb()
    if not user_id or not sb:
        return 0
    try:
        res = sb.rpc("get_chat_bonus_balance", {"p_user_id": user_id}).execute()
        return max(0, int(getattr(res, "data", 0) or 0))
    except Exception:
        return 0


def _invalidate_quota_cache(user_id: str) -> None:
    try:
        from api.routers.offload import _QUOTA_CACHE
        _QUOTA_CACHE.delete(user_id)
    except Exception:
        pass


def check_and_consume_quota(
    user_id: Optional[str],
    is_pro: bool,
) -> Tuple[bool, int, int, str]:
    """
    Check and deduct monthly chat quota (with bonus-credit fallback for Free users).
    Returns:
      (allowed: bool, remaining_quota: int, quota_limit: int, error_message: str)
    """
    if user_id == "00000000-0000-0000-0000-000000000000":
        return True, 9999, 9999, ""

    # If billing is globally disabled, everything is free and unlimited
    if not is_payments_enabled():
        return True, 999, 999, ""

    quota_limit = 350 if is_pro else 10

    if not user_id:
        return False, 0, quota_limit, "يلزم تسجيل الدخول لاستخدام المساعد الذكي."

    today = get_cairo_date_string()
    sb = _get_sb()
    if sb is None:
        if not is_pro:
            return False, 0, quota_limit, "تعذر التحقق من رصيد الرسائل حالياً، يرجى المحاولة مرة أخرى بعد لحظات."
        return True, quota_limit, quota_limit, ""

    month_start = _monthly_quota_start(user_id, is_pro, today)

    try:
        prior_res = (
            sb.from_("ai_chatbot_limits")
            .select("date, chat_count")
            .eq("user_id", user_id)
            .gte("date", month_start)
            .lt("date", today)
            .execute()
        )
        prior_used = sum(int(r.get("chat_count") or 0) for r in (prior_res.data or []))
        today_cap = max(0, quota_limit - prior_used)

        allowed = False
        total_used = prior_used

        if today_cap > 0:
            res = sb.rpc(
                "consume_ai_chat_quota",
                {
                    "p_user_id": user_id,
                    "p_date": today,
                    "p_limit": today_cap,
                }
            ).execute()
            quota_data = res.data
            if isinstance(quota_data, list) and quota_data:
                quota_data = quota_data[0]
            allowed = bool(quota_data.get("allowed", False)) if isinstance(quota_data, dict) else False
            today_count = int(quota_data.get("chat_count", 0)) if isinstance(quota_data, dict) else today_cap
            total_used = prior_used + today_count

        if not allowed and not is_pro:
            try:
                bonus_res = sb.rpc("consume_chat_bonus", {"p_user_id": user_id}).execute()
                bonus_data = getattr(bonus_res, "data", None)
                if isinstance(bonus_data, list) and bonus_data:
                    bonus_data = bonus_data[0]
                if isinstance(bonus_data, dict) and bonus_data.get("allowed") is True:
                    _invalidate_quota_cache(user_id)
                    bonus_left = _fetch_bonus_balance(user_id)
                    return True, bonus_left, quota_limit, ""
            except Exception:
                pass

        if not allowed:
            if not is_pro:
                if founders_offer_is_open():
                    offer_line = "🔥 عرض المؤسسين: اشترك الآن بـ 100 ج.م فقط شهرياً "
                else:
                    chat_egp = int(plan_amount_egp("chat_only"))
                    pro_egp = int(plan_amount_egp("pro"))
                    offer_line = f"اشترك الآن في باقة الشات الذكي بـ {chat_egp} ج.م أو الباقة الشاملة بـ {pro_egp} ج.م شهرياً "
                msg = (
                    f"لقد استهلكت باقتك المجانية ({quota_limit}/{quota_limit} رسائل — الرصيد المجاني لمرة واحدة لكل حساب). "
                    + offer_line
                    + "واحصل على 350 رسالة تحليلية شهرياً، رفع صور المحفظة، والمؤشرات الفنية اللحظية!"
                )
            else:
                msg = f"لقد استهلكت حد الرسائل الشهري لباقة الشات ({quota_limit} رسالة)."
            return False, 0, quota_limit, msg

        base_remaining = max(0, quota_limit - total_used)
        bonus_left = 0 if is_pro else _fetch_bonus_balance(user_id)
        _invalidate_quota_cache(user_id)
        return True, base_remaining + bonus_left, quota_limit, ""

    except Exception:
        # Fail-closed for Free accounts so DB hiccups can NEVER leak extra unpaid LLM turns
        if not is_pro:
            return False, 0, quota_limit, "تعذر التحقق من رصيد الرسائل حالياً، يرجى المحاولة مرة أخرى بعد لحظات."
        return True, quota_limit, quota_limit, ""


def sanitize_user_input(text: str) -> Tuple[bool, str]:
    """
    Validate and sanitize user input:
    - Length bounds (max 4000 characters).
    - Block prompt injection patterns.
    Returns (is_valid, sanitized_text_or_error)
    """
    clean = (text or "").strip()
    if not clean:
        return False, "الرسالة فارغة، يرجى كتابة استفسارك."

    if len(clean) > 4000:
        return False, "الرسالة طويلة جداً (الحد الأقصى 4000 حرف)."

    lowered = clean.lower()
    for pattern in BLOCKED_INPUT_PATTERNS:
        if pattern in lowered:
            return False, "معذرة، لا يمكن الاستجابة لهذه الرسالة بناءً على إرشادات الأمان والحماية الخاصة بالمنصة."

    return True, clean


def get_user_chat_quota(user_id: Optional[str], is_pro: bool) -> Tuple[int, int, int]:
    """
    Calculate (used, remaining, limit) on a monthly window matching /api/user/quota.
    """
    limit = 350 if is_pro else 10
    if not user_id or user_id == "00000000-0000-0000-0000-000000000000":
        return 0, limit, limit

    today = get_cairo_date_string()
    try:
        sb = _get_sb()
        if sb is None:
            return (limit, 0, limit) if not is_pro else (0, limit, limit)
        month_start = _monthly_quota_start(user_id, is_pro, today)
        res = (
            sb.from_("ai_chatbot_limits")
            .select("date, chat_count")
            .eq("user_id", user_id)
            .gte("date", month_start)
            .execute()
        )
        used = sum(int(r.get("chat_count") or 0) for r in (res.data or []))
        base_remaining = max(0, limit - used)
        bonus_left = 0 if is_pro else _fetch_bonus_balance(user_id)
        return used, base_remaining + bonus_left, limit
    except Exception:
        return (limit, 0, limit) if not is_pro else (0, limit, limit)


def strip_dsml(text: str) -> str:
    """
    Remove all DeepSeek internal DSML tool tags and invocations:
    - Entire <'DSML | | calls | | > ... <DSML | | calls | | > blocks
    - Entire <｜DSML｜tool_calls> ... </｜DSML｜tool_calls> blocks
    - Individual <DSML | | invoke ... > ... <DSML | | invoke | | > blocks
    - Any stray DSML tokens
    """
    if not text or ("DSML" not in text and "dsml" not in text):
        return text
    clean = text
    # 1. Strip entire calls / tool_calls block (with any quotes, spaces, or pipes)
    call_prefix = r"<['\"]?\s*[|｜\s]*\s*(?:DSML)?\s*[|｜\s]*\s*"
    close_prefix = r"<\/?\s*[|｜\s]*\s*(?:DSML)?\s*[|｜\s]*\s*"
    clean = re.sub(
        rf"{call_prefix}(?:calls|tool_calls)[^>]*>[\s\S]*?{close_prefix}(?:calls|tool_calls)[^>]*>",
        "",
        clean,
        flags=re.IGNORECASE,
    )
    # 2. Strip invoke blocks
    clean = re.sub(
        rf"{call_prefix}invoke[^>]*>[\s\S]*?{close_prefix}invoke[^>]*>",
        "",
        clean,
        flags=re.IGNORECASE,
    )
    # 3. Strip any stray tags containing DSML
    clean = re.sub(r"<['\"]?[^>]*DSML[^>]*>", "", clean, flags=re.IGNORECASE)
    return clean.strip()


def filter_output(response_text: str) -> str:
    """
    Clean output matching legacy Vercel pipeline:
    - Replace forced buy directives with compliant advisory language (never wipe out whole reply).
    - Remove leaked environment details.
    - Remove raw DSML markup tags.
    """
    clean = response_text
    clean = strip_dsml(clean)
    clean = re.sub(r"<environment_details>[\s\S]*?<\/environment_details>", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\[?\s*environment_details\s*\]?[\s\S]*$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"Current time:\s*[^\n]+", "", clean, flags=re.IGNORECASE)
    clean = clean.strip()

    # Preserves full text while sanitizing forced-action words
    clean = BLOCKED_OUTPUT_REGEX.sub("فرصة شراء مقترحة بناءً على المؤشرات", clean)
    return clean
