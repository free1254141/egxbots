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
from api.payment_common import is_payments_enabled

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
        _init_supabase()
        res = supabase.auth.get_user(token)
        if res and hasattr(res, "user") and res.user:
            return {
                "id": str(res.user.id),
                "email": getattr(res.user, "email", "") or "",
                "is_authenticated": True,
            }
    except Exception:
        pass

    return None


def check_and_consume_quota(
    user_id: Optional[str],
    is_pro: bool,
) -> Tuple[bool, int, int, str]:
    """
    Check and deduct chat quota for the user.
    Returns:
      (allowed: bool, remaining_quota: int, quota_limit: int, error_message: str)
    """
    if user_id == "00000000-0000-0000-0000-000000000000":
        return True, 9999, 9999, ""

    # If billing is globally disabled, everything is free and unlimited
    if not is_payments_enabled():
        return True, 999, 999, ""

    # Billing is enabled:
    quota_limit = 350 if is_pro else 10

    if not user_id:
        return False, 0, quota_limit, "يلزم تسجيل الدخول لاستخدام المساعد الذكي."

    today = get_cairo_date_string()
    _init_supabase()

    try:
        res = supabase.rpc(
            "consume_ai_chat_quota",
            {
                "p_user_id": user_id,
                "p_date": today,
                "p_limit": quota_limit,
            }
        ).execute()

        quota_data = res.data
        if isinstance(quota_data, list) and quota_data:
            quota_data = quota_data[0]

        allowed = bool(quota_data.get("allowed", False)) if isinstance(quota_data, dict) else False
        chat_count = int(quota_data.get("chat_count", 0)) if isinstance(quota_data, dict) else quota_limit

        if not allowed:
            # Check bonus credits
            try:
                bonus_res = supabase.rpc("consume_chat_bonus", {"p_user_id": user_id}).execute()
                if bonus_res.data and bonus_res.data.get("allowed") is True:
                    allowed = True
            except Exception:
                pass

        if not allowed:
            msg = (
                f"لقد استهلكت باقتك ({quota_limit}/{quota_limit} رسائل). "
                "🔥 عرض المؤسسين: اشترك الآن بـ 100 ج.م فقط شهرياً (بدلاً من 200 ج.م) لفترة محدودة "
                "واحصل على 350 رسالة شهرياً، رفع صور المحفظة، التوصيات المفتوحة، وقناة توصيات VIP!"
            ) if not is_pro else (
                f"لقد استهلكت حد الرسائل الشهري لباقة Pro ({quota_limit} رسالة)."
            )
            return False, 0, quota_limit, msg

        remaining = max(0, quota_limit - chat_count)
        return True, remaining, quota_limit, ""

    except Exception as e:
        # If DB check fails, default to allowing with warning to avoid breaking active UX
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
    Calculate (used, remaining, limit) exactly matching web/src/app/api/user/quota/route.ts.
    """
    limit = 350 if is_pro else 10
    if not user_id or user_id == "00000000-0000-0000-0000-000000000000":
        return 0, limit, limit

    today = get_cairo_date_string()
    month_start = f"{today[:7]}-01"
    try:
        _init_supabase()
        res = (
            supabase.from_("ai_chatbot_limits")
            .select("date, chat_count")
            .eq("user_id", user_id)
            .gte("date", month_start if is_pro else today)
            .execute()
        )
        used = sum(int(r.get("chat_count") or 0) for r in (res.data or []))
        remaining = max(0, limit - used)
        return used, remaining, limit
    except Exception as e:
        return 0, limit, limit


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
