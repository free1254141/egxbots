"""
api/scheduled_automations_worker.py — Background Scheduler for User-Defined AI Chat Automations.

Executes on Hugging Face Spaces / Python Backend natively.
Monitors user-scheduled times (Cairo Time), verifies Pro subscription,
consumes quota atomically via consume_ai_chat_quota, generates DeepSeek analysis
backed by live EGX indicators, Wyckoff scans, open recommendations, and user portfolio,
and delivers responses directly to user Telegram channels/chats.

Key architectural rules:
- Zero load on Vercel: Runs natively in Python background thread.
- Zero Supabase log query waste: Targeted lookups with explicit column projections and strict limits.
- HF sleep resilience: In-memory cache + 90-minute catch-up window for cold boots.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    requests = None

try:
    from dotenv import load_dotenv
    _base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_base_dir, ".env"))
    load_dotenv(os.path.join(_base_dir, "web", ".env.local"), override=True)
except Exception:
    pass

logger = logging.getLogger("scheduled_automations_worker")
logger.setLevel(logging.INFO)

CAIRO_TZ = ZoneInfo("Africa/Cairo")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
TELEGRAM_RELAY_BASE = (os.getenv("TELEGRAM_RELAY_URL") or "https://api.telegram.org").rstrip("/")

_worker_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_cached_automations: List[Dict[str, Any]] = []
_cache_lock = threading.Lock()
_last_cache_refresh: float = 0.0
_CACHE_TTL_SECONDS = 300.0  # 5 minutes background refresh, or immediate via sync_automations_cache()

_cached_egx_stocks: List[Dict[str, Any]] = []
_last_stocks_refresh: float = 0.0
_cached_market_stocks: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}
_STOCKS_TTL_SECONDS = 3600.0  # 1 hour cache for symbol/Arabic name lookup
_AUTO_METRICS_TLS = threading.local()

try:
    from api.perf_utils import BoundedTTLCache as _BoundedTTLCache
except Exception:
    _BoundedTTLCache = None

_AUTOMATION_SNAP_CACHE = (
    _BoundedTTLCache(max_entries=256, default_ttl=6 * 3600.0)
    if _BoundedTTLCache is not None
    else None
)
_FALLBACK_SNAP_LOCK = threading.Lock()
_FALLBACK_SNAP_STORE: Dict[str, tuple[float, str]] = {}

AUTOMATION_STATIC_SYSTEM_PROMPT = (
    "أنت أرتورو (ARTORO AI)، المساعد المالي والتقني الخبير في البورصة المصرية (EGX) والأسواق الخليجية "
    "(السعودي تاسي TASI، قطر QSE، دبي DFM، أبوظبي ADX، الكويت KSE) والذهب والفضة.\n"
    "تقدم استشارة مجدولة مخصصة وموجزة للمشترك Pro بناءً على طلبه المحدد وسوقه المستهدف، وتعمل في أي وقت يختاره المستخدم طوال اليوم وعلى مدار الأسبوع.\n"
    "قواعد الإجابة الثابتة:\n"
    "1. اعتمد حصرياً على الأرقام، الأسعار، العملة المعتمدة للسوق في البيانات (ج.م / ر.س / ر.ق / د.إ / د.ك / دولار)، التوصيات المفتوحة، ونتائج مسح وايكوف والمؤشرات الفنية المرفقة في رسالة المستخدم، واذكر كود السهم واسمه العربي المعتمد.\n"
    "2. قدّم تحليلاً فنياً واقعياً ومحترفاً ومباشراً مقسماً بوضوح حسب نقاط سؤال المشترك بدون حشو، مع مراعاة تنبيهات القيم العادلة والتحذيرات المالية إن وُجدت.\n"
    "3. ركز على مستويات الدعم، المقاومة، اتجاه السيولة، وحجم التداول؛ وإذا ورد في البيانات أن السيولة اللحظية لا تزال قيد التحديث أو أن الرقم يمثل آخر إغلاق مكتمل أو مُعايرة زمنية، فانقل هذا التوصيف بأمانة ولا تصف السهم خطأً بانعدام السيولة.\n"
    "4. التزم بحالة الجلسة المذكورة في مقدمة رسالة المستخدم فقط: إذا كانت الجلسة مفتوحة لا تكتب أن الوقت خارج ساعات التداول، وإذا كانت مغلقة أو عطلة فقدّم رؤية استباقية واستعداداً للجلسة القادمة.\n"
    "5. اختم دائماً بنصيحة إدارة مخاطر ذكية مبنية على مستوى الدعم ووقف الخسارة الحقيقي المرفق في البيانات (لا تثبّت نسبة عشوائية 2.5%-3.5% بل انقل `وقف محسوب` أو مستوى الدعم الفعلي)، والتزم تماماً بعلامات `فوق EMA ✅` أو `تحت EMA 🔴` المحسوبة حتمياً في البيانات ولا تكتب أبداً أي مسمى تقني إنجليزي.\n"
    "6. التزم باللغة العربية الواضحة وتنسيق تليجرام أنيق ومرتب مع الإيموجي المناسب للقراءة السريعة، واستخدم مصطلحات البحث الكمي والتعليمي دون وعود عوائد.\n"
    "7. احرص على إكمال كل فكرة وجملة بدقة، ولا تترك أي فقرة أو نقطة مقطوعة أو غير مكتملة أبداً."
)


def _clear_automation_snapshot_cache() -> None:
    """Reset the in-memory automation snapshot cache (used by tests & maintenance)."""
    if _AUTOMATION_SNAP_CACHE is not None:
        _AUTOMATION_SNAP_CACHE.clear()
    with _FALLBACK_SNAP_LOCK:
        _FALLBACK_SNAP_STORE.clear()


def _snap_cache_get(key: str) -> Optional[str]:
    if _AUTOMATION_SNAP_CACHE is not None:
        hit, val = _AUTOMATION_SNAP_CACHE.get(key)
        return str(val) if hit and val else None
    now_m = time.monotonic()
    with _FALLBACK_SNAP_LOCK:
        entry = _FALLBACK_SNAP_STORE.get(key)
        if not entry:
            return None
        exp, val = entry
        if now_m >= exp:
            _FALLBACK_SNAP_STORE.pop(key, None)
            return None
        return val


def _snap_cache_set(key: str, val: str, ttl_seconds: float) -> None:
    if not key or not val:
        return
    if _AUTOMATION_SNAP_CACHE is not None:
        _AUTOMATION_SNAP_CACHE.set(key, val, ttl=ttl_seconds)
        return
    with _FALLBACK_SNAP_LOCK:
        if len(_FALLBACK_SNAP_STORE) > 256:
            _FALLBACK_SNAP_STORE.clear()
        _FALLBACK_SNAP_STORE[key] = (time.monotonic() + max(1.0, float(ttl_seconds)), val)


def _is_test_runtime() -> bool:
    return bool("pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"))


def _record_automation_deepseek_usage(raw_usage: Optional[Dict[str, Any]]) -> None:
    """Compute exact DeepSeek token/cost metrics into thread-local storage for chat history logging."""
    if not isinstance(raw_usage, dict):
        return
    try:
        from api.agentic_chat.pipeline import (
            _accumulate_deepseek_usage,
            _finalize_usage_cost,
            _new_usage_accumulator,
        )
        acc = _new_usage_accumulator()
        _accumulate_deepseek_usage(acc, raw_usage)
        _AUTO_METRICS_TLS.last_usage = _finalize_usage_cost(acc, cached=False)
    except Exception:
        pass


def _get_supabase_config() -> tuple[str, str]:
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or ""
    )
    return url, key


def _execute_supabase_rest_request(
    url: str,
    key: str,
    endpoint: str,
    *,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 15,
    extra_headers: Optional[Dict[str, str]] = None,
    tag: str = "",
) -> Optional[Any]:
    """Execute a low-level PostgREST HTTP request against `(url, key)`."""
    if not url or not key:
        return None
    full_url = f"{url}/rest/v1/{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if method in ("POST", "PATCH"):
        headers["Prefer"] = "return=representation"
    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(full_url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except Exception as e:
        prefix = f"[{tag}] " if tag else ""
        logger.warning(f"[AUTOMATIONS_WORKER] {prefix}{method} {endpoint} failed: {e}")
        return None


def _supabase_request(
    endpoint: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 15,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Optional[Any]:
    url, key = _get_supabase_config()
    return _execute_supabase_rest_request(
        url,
        key,
        endpoint,
        method=method,
        payload=payload,
        timeout=timeout,
        extra_headers=extra_headers,
    )


def _get_market_supabase_config(exchange: str = "EGX") -> tuple[str, str]:
    """Resolve REST (url, key) for a market exchange, routing GCC/Metals to SAUDI_SUPABASE when configured."""
    try:
        from api.agentic_chat.market_registry import get_market_config
        cfg = get_market_config(exchange)
    except Exception:
        return _get_supabase_config()

    if cfg.exchange == "EGX" or not cfg.supabase_env_prefix:
        return _get_supabase_config()

    prefixes: List[str] = []
    if cfg.exchange != cfg.supabase_env_prefix:
        prefixes.append(cfg.exchange)
    prefixes.append(cfg.supabase_env_prefix)

    for pref in prefixes:
        u = (
            os.getenv(f"{pref}_SUPABASE_URL")
            or os.getenv(f"NEXT_PUBLIC_{pref}_SUPABASE_URL")
            or ""
        ).strip().rstrip("/")
        k = (
            os.getenv(f"{pref}_SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv(f"{pref}_SUPABASE_ANON_KEY")
            or os.getenv(f"NEXT_PUBLIC_{pref}_SUPABASE_ANON_KEY")
            or ""
        ).strip()
        if u and k:
            return u, k

    if cfg.exchange == "TADAWUL":
        return "", ""
    return _get_supabase_config()


def _market_supabase_request(
    endpoint: str,
    exchange: str = "EGX",
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 15,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Optional[Any]:
    """Execute REST query on the appropriate Supabase project for `exchange` (EGX -> `_supabase_request`)."""
    try:
        from api.agentic_chat.market_registry import normalize_exchange_code
        exch = normalize_exchange_code(exchange)
    except Exception:
        exch = str(exchange or "EGX").strip().upper() or "EGX"

    def _delegate_primary() -> Optional[Any]:
        sb_kw: Dict[str, Any] = {}
        if method != "GET":
            sb_kw["method"] = method
        if payload is not None:
            sb_kw["payload"] = payload
        if timeout != 15:
            sb_kw["timeout"] = timeout
        if extra_headers is not None:
            sb_kw["extra_headers"] = extra_headers
        return _supabase_request(endpoint, **sb_kw)

    if exch == "EGX":
        return _delegate_primary()

    url, key = _get_market_supabase_config(exch)
    if not url or not key:
        return None
    if (url, key) == _get_supabase_config():
        return _delegate_primary()

    return _execute_supabase_rest_request(
        url,
        key,
        endpoint,
        method=method,
        payload=payload,
        timeout=timeout,
        extra_headers=extra_headers,
        tag=exch,
    )


_AUTO_NON_TICKER_NUM_NEIGHBOR_RE = re.compile(
    r"^\s*(?:جنيه|ج\.م|ريال|ر\.س|درهم|دينار|دولار|سهم|أسهم|اسهم|نقطة|نقطه|ألف|الف|مليون|مليار|EGP|SAR|USD|AED|QAR|KWD|%)",
    re.IGNORECASE,
)
_AUTO_STOCK_PREFIX_RE = re.compile(r"(?:سهم|كود|رمز|شركة|تداول)\s*$", re.IGNORECASE)


def _detect_automation_market(prompt: str, task_name: str = "") -> str:
    """Detect canonical target exchange (EGX, TADAWUL, QSE, DFM, ADX, KSE, COMMODITIES) for an automation."""
    combined = f"{task_name or ''} {prompt or ''}".strip()
    if not combined:
        return "EGX"
    try:
        from api.agentic_chat.market_registry import detect_market_from_text
        explicit = detect_market_from_text(combined)
        if explicit:
            return explicit
    except Exception:
        pass

    up = combined.upper()
    has_egx_kw = any(kw in up for kw in ("EGX", ".CA", "البورصة المصرية", "السوق المصري", "مصر"))

    if not has_egx_kw:
        # Detect bare 4-digit Tadawul tickers with guards against years, currency amounts, and round lot quantities
        for m_num in re.finditer(r"(?<!\d)([1-9]\d{3})(?!\d)", combined):
            num_val = int(m_num.group(1))
            if 1990 <= num_val <= 2035:
                continue
            after_ctx = combined[m_num.end() : m_num.end() + 20]
            before_ctx = combined[max(0, m_num.start() - 16) : m_num.start()]
            if _AUTO_NON_TICKER_NUM_NEIGHBOR_RE.match(after_ctx):
                continue
            if num_val % 500 == 0 and not _AUTO_STOCK_PREFIX_RE.search(before_ctx):
                continue
            return "TADAWUL"

        # Detect well-known Saudi Arabic stock names when no explicit EGX keyword is present
        try:
            from api.saudi_stock_aliases import extract_all_saudi_symbols
            if extract_all_saudi_symbols(combined):
                return "TADAWUL"
        except Exception:
            pass

    return "EGX"


def get_cairo_time() -> dt.datetime:
    try:
        return dt.datetime.now(CAIRO_TZ)
    except Exception:
        return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)


def sync_automations_cache() -> int:
    """Refreshes the in-memory cache of active scheduled automations from Supabase."""
    global _cached_automations, _last_cache_refresh
    rows = _supabase_request(
        "scheduled_chat_automations?is_active=eq.true&select=id,user_id,name,prompt,scheduled_time,days_of_week,telegram_chat_id,is_active,last_run_at,last_run_date,last_status,created_at,updated_at&limit=500"
    )
    if rows is not None and isinstance(rows, list):
        with _cache_lock:
            _cached_automations = rows
            _last_cache_refresh = time.time()
        logger.info(f"[AUTOMATIONS_WORKER] Cached {len(_cached_automations)} active automations.")
        return len(_cached_automations)
    return len(_cached_automations)


def get_telegram_bot_token() -> str:
    return (
        os.getenv("ARTORO_AI_BOT")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or os.getenv("SUPPORT_BOT_TOKEN")
        or ""
    ).strip()


def _strip_markdown_formatting(text: str) -> str:
    """Removes Markdown markers when retrying plain-text delivery after Telegram parse errors."""
    return text.replace("**", "").replace("__", "").replace("`", "")


def _split_telegram_message(text: str, max_length: int = 3900) -> List[str]:
    """Splits a long message into natural chunks on paragraph or line boundaries without truncation."""
    if len(text) <= max_length:
        return [text]
    chunks: List[str] = []
    remaining = text
    while len(remaining) > max_length:
        # Prefer splitting at a blank line / section break
        cut = remaining.rfind("\n\n", 0, max_length)
        if cut < 1000:
            # Fallback to single newline
            cut = remaining.rfind("\n", 0, max_length)
        if cut < 1000:
            # Fallback to whitespace
            cut = remaining.rfind(" ", 0, max_length)
        if cut < 1000:
            cut = max_length
        chunk = remaining[:cut].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def send_telegram_direct(chat_id: str | int, text: str) -> bool:
    """Delivers message directly to user's Telegram chat or channel with auto-chunking & plain-text fallback."""
    token = get_telegram_bot_token()
    if not token or not chat_id:
        logger.warning("[AUTOMATIONS_WORKER] Missing Telegram Bot Token or chat_id")
        return False

    target_chat_id: str | int = str(chat_id).strip()
    thread_id: Optional[int] = None
    if isinstance(target_chat_id, str) and "_" in target_chat_id and not target_chat_id.startswith("@"):
        parts = target_chat_id.split("_", 1)
        target_chat_id = parts[0]
        try:
            thread_id = int(parts[1])
        except ValueError:
            pass

    if isinstance(target_chat_id, str) and target_chat_id.lstrip("-").isdigit():
        target_chat_id = int(target_chat_id)

    # Deliver all chunks completely without cutting off content
    chunks = _split_telegram_message(text)

    bases = [TELEGRAM_RELAY_BASE]
    if "https://api.telegram.org" not in bases:
        bases.append("https://api.telegram.org")

    all_delivered = True
    for chunk in chunks:
        chunk_delivered = False
        for base in bases:
            if chunk_delivered:
                break
            url = f"{base}/bot{token}/sendMessage"
            # Attempt 1: Markdown parse_mode, Attempt 2: Plain text fallback if Markdown entities fail
            for mode in ("Markdown", None):
                payload: Dict[str, Any] = {
                    "chat_id": target_chat_id,
                    "text": chunk if mode else _strip_markdown_formatting(chunk),
                    "disable_web_page_preview": True,
                }
                if mode:
                    payload["parse_mode"] = mode
                if thread_id is not None:
                    payload["message_thread_id"] = thread_id

                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        res_json = json.loads(resp.read().decode("utf-8"))
                        if res_json.get("ok"):
                            chunk_delivered = True
                            break
                except urllib.error.HTTPError as he:
                    err_body = ""
                    try:
                        err_body = he.read().decode("utf-8", errors="ignore")
                    except Exception:
                        pass
                    if he.code == 400 and mode == "Markdown":
                        logger.info(f"[AUTOMATIONS_WORKER] Markdown parse error for {chat_id}, retrying plain text...")
                        continue
                    logger.warning(f"[AUTOMATIONS_WORKER] Telegram HTTP {he.code} to {chat_id} via {base}: {err_body[:200]}")
                    break
                except Exception as e:
                    logger.warning(f"[AUTOMATIONS_WORKER] Telegram send to {chat_id} via {base} failed: {e}")
                    break

        if not chunk_delivered:
            all_delivered = False

    return all_delivered


ADMIN_USER_IDS = {"ba9c27e8-f62d-452f-8a29-dc77fd092207", "c4b3a6d0-61c5-4f75-97bc-24f486666da0"}
ADMIN_TG_IDS = {"5149631436"}


def _is_user_pro(user_id: str) -> bool:
    """Verifies that the user currently holds an active Pro/Lifetime/Trial subscription or is admin."""
    # 1. Check known admin user IDs
    if user_id in ADMIN_USER_IDS:
        return True

    # 2. Check profile admin Telegram chat IDs
    prof = _supabase_request(f"profiles?id=eq.{user_id}&select=telegram_chat_id&limit=1") or []
    if prof and isinstance(prof, list) and len(prof) > 0:
        if str(prof[0].get("telegram_chat_id") or "") in ADMIN_TG_IDS:
            return True

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    # 3. Check active or trialing subscriptions (AI Chat Pro or Full Pro — excludes vip_only)
    subs = _supabase_request(
        f"subscriptions?user_id=eq.{user_id}&status=in.(active,trialing)&select=plan_id,current_period_end&order=current_period_end.desc&limit=5"
    ) or []
    chat_pro_plans = {"pro", "pro_6m", "pro_1y", "lifetime", "pro_lifetime", "chat_only"}
    for sub_row in (subs if isinstance(subs, list) else []):
        end_str = str(sub_row.get("current_period_end") or "")
        plan_id = str(sub_row.get("plan_id") or "").strip().lower()
        if plan_id not in chat_pro_plans:
            continue
        if not end_str or "lifetime" in plan_id or "2126" in end_str or end_str > now_iso:
            return True

    # 4. Check 3-day Pro trial table if applicable
    trials = _supabase_request(
        f"subscription_trials?user_id=eq.{user_id}&select=expires_at&order=expires_at.desc&limit=1"
    ) or []
    if trials and isinstance(trials, list) and len(trials) > 0:
        exp_str = str(trials[0].get("expires_at") or "")
        if exp_str and exp_str > now_iso:
            return True

    return False


def _resolve_user_telegram(user_id: str, custom_chat_id: Optional[str]) -> Optional[str]:
    """Finds the best Telegram chat or channel ID for delivering the automation."""
    if custom_chat_id and str(custom_chat_id).strip():
        return str(custom_chat_id).strip()

    prof = _supabase_request(f"profiles?id=eq.{user_id}&select=telegram_chat_id&limit=1") or []
    if prof and prof[0].get("telegram_chat_id"):
        return str(prof[0]["telegram_chat_id"])

    invites = _supabase_request(f"pro_telegram_invites?user_id=eq.{user_id}&select=vip_telegram_user_id&limit=1") or []
    if invites and invites[0].get("vip_telegram_user_id"):
        return str(invites[0]["vip_telegram_user_id"])

    state = _supabase_request(f"telegram_vip_chat_state?linked_user_id=eq.{user_id}&select=telegram_user_id&limit=1") or []
    if state and state[0].get("telegram_user_id"):
        return str(state[0]["telegram_user_id"])

    return None


def _consume_user_quota(user_id: str, today_cairo: str) -> bool:
    """Atomically consumes 1 credit from the user's monthly chat quota (350/month)."""
    url, key = _get_supabase_config()
    if not url or not key:
        return False

    month_start = f"{today_cairo[:7]}-01"
    prior_rows = (
        _supabase_request(
            f"ai_chatbot_limits?user_id=eq.{user_id}&date=gte.{month_start}&date=lt.{today_cairo}&select=chat_count"
        )
        or []
    )
    prior_used = sum(int(r.get("chat_count") or 0) for r in prior_rows if isinstance(r, dict))
    today_cap = max(0, 350 - prior_used)
    if today_cap <= 0:
        return False

    rpc_url = f"{url}/rest/v1/rpc/consume_ai_chat_quota"
    payload = {
        "p_user_id": user_id,
        "p_date": today_cairo,
        "p_limit": today_cap,
    }
    req = urllib.request.Request(
        rpc_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 0:
                return bool(data[0].get("allowed"))
            return False
    except Exception as e:
        logger.warning(f"[AUTOMATIONS_WORKER] Quota RPC failed for {user_id}: {e}")
        # Fail safe: allow if transient database RPC error occurs
        return True


def _get_egx_stocks_catalog() -> List[Dict[str, Any]]:
    """Returns cached list of EGX stocks (symbol, name, name_ar) for fast Arabic/English matching."""
    global _cached_egx_stocks, _last_stocks_refresh
    if _cached_egx_stocks and (time.time() - _last_stocks_refresh < _STOCKS_TTL_SECONDS):
        return _cached_egx_stocks

    rows = _supabase_request("stocks?country=eq.Egypt&select=symbol,name,name_ar&limit=300")
    if rows and isinstance(rows, list):
        _cached_egx_stocks = rows
        _last_stocks_refresh = time.time()
    return _cached_egx_stocks


def _get_market_stocks_catalog(exchange: str = "EGX") -> List[Dict[str, Any]]:
    """Return cached stock catalog for any exchange (`EGX` delegates to `_get_egx_stocks_catalog`)."""
    try:
        from api.agentic_chat.market_registry import normalize_exchange_code
        exch = normalize_exchange_code(exchange)
    except Exception:
        exch = str(exchange or "EGX").strip().upper() or "EGX"
    if exch == "EGX":
        return _get_egx_stocks_catalog()

    now_ts = time.time()
    cached_entry = _cached_market_stocks.get(exch)
    if cached_entry and (now_ts - cached_entry[0] < _STOCKS_TTL_SECONDS):
        return cached_entry[1]

    rows = _market_supabase_request(
        f"stocks?exchange=eq.{exch}&select=symbol,name,name_ar&limit=400",
        exchange=exch,
    )
    if isinstance(rows, list) and rows:
        _cached_market_stocks[exch] = (now_ts, rows)
        return rows
    return cached_entry[1] if cached_entry else []


def _strip_market_symbol_suffix(raw_sym: str) -> str:
    s = str(raw_sym or "").strip().upper()
    for suf in (".CA", ".EGX", ".SR", ".SA", ".TADAWUL", ".QA", ".QE", ".QSE", ".DU", ".DFM", ".AE", ".AD", ".ADX", ".KW", ".KSE"):
        if s.endswith(suf):
            return s[: -len(suf)].strip()
    return s


def _resolve_pos_symbol_and_market(raw_sym: str) -> tuple[str, str]:
    """Infer `(clean_symbol, canonical_exchange)` from a portfolio position's symbol."""
    s = str(raw_sym or "").strip().upper()
    if not s:
        return "", "EGX"
    try:
        from api.agentic_chat.market_registry import detect_exchange_from_suffix
        hit = detect_exchange_from_suffix(s)
        if hit:
            return hit[0], hit[1]
    except Exception:
        pass
    core = _strip_market_symbol_suffix(s)
    if core.isdigit() and len(core) == 4:
        return core, "TADAWUL"
    return core, "EGX"


_GCC_ARABIC_ALIASES_BY_EXCHANGE: Dict[str, Dict[str, str]] = {
    "QSE": {
        "بنك قطر الوطني": "QNBK",
        "قطر الوطني": "QNBK",
        "صناعات قطر": "IQCD",
        "مصرف قطر الاسلامي": "QIBK",
        "اوريدو": "ORDS",
        "ناقله": "QGTS",
        "ناقلات": "QGTS",
    },
    "DFM": {
        "اعمار": "EMAAR",
        "اعمار العقاريه": "EMAAR",
        "اعمار للتطوير": "EMAARDEV",
        "بنك دبي الاسلامي": "DIB",
        "بنك الامارات دبي الوطني": "EMIRATESNBD",
        "سالك": "SALIK",
        "ديوا": "DEWA",
    },
    "ADX": {
        "الدار": "ALDAR",
        "الدار العقاريه": "ALDAR",
        "العالميه القابضه": "IHC",
        "ابوظبي الاول": "FAB",
        "اتصالات": "EAND",
        "اي اند": "EAND",
        "ادنوك للحفر": "ADNOCDRILL",
    },
    "COMMODITIES": {
        "الذهب": "XAUUSD",
        "الدهب": "XAUUSD",
        "الفضه": "XAGUSD",
    },
}


def _normalize_ar(text: str) -> str:
    """Normalizes Arabic text for fuzzy stock name matching."""
    s = re.sub(r"[أإآ]", "ا", text)
    s = s.replace("ة", "ه").replace("ى", "ي")
    return s


_NON_TICKER_STOP_WORDS = frozenset({
    "THE", "AND", "FOR", "BUY", "SELL", "HOLD", "TRIM", "EXIT", "VIP", "BOT", "EGX",
    "EGX30", "EGX70", "EGX33", "PRO", "RSI", "EMA", "SMA", "MACD", "ATR", "SMC",
    "VWAP", "CMF", "ADX", "OBV", "DCA", "HHI", "GMV", "ROE", "ROA", "ROIC", "EPS",
    "EBITDA", "EGP", "SAR", "USD", "AED", "QAR", "KWD", "TASI", "TADAWUL", "QSE",
    "DFM", "KSE", "AI", "OR", "SL", "TP", "BULL", "BEAR", "FVG", "BOS", "PDF", "UTC",
})


def _extract_symbols_from_text(text: str, exchange: str = "EGX") -> tuple[List[str], Dict[str, str]]:
    """Extracts both English/numeric tickers and Arabic stock names from user prompt for any supported exchange."""
    try:
        from api.agentic_chat.market_registry import normalize_exchange_code
        exch = normalize_exchange_code(exchange)
    except Exception:
        exch = str(exchange or "EGX").strip().upper() or "EGX"

    if exch == "EGX":
        catalog = _get_egx_stocks_catalog()
        name_map: Dict[str, str] = {}
        for row in catalog:
            sym = str(row.get("symbol") or "").upper().replace(".CA", "").replace(".EGX", "").strip()
            if sym:
                name_map[sym] = str(row.get("name_ar") or row.get("name") or sym)

        words = re.findall(r"[A-Za-z]{2,8}", text)
        found: List[str] = []
        for w in words:
            u = w.upper()
            if u not in _NON_TICKER_STOP_WORDS and (not name_map or u in name_map):
                if u not in found:
                    found.append(u)

        norm_text = _normalize_ar(text)
        arabic_aliases = {
            "فوري": "FWRY",
            "طلعت مصطفي": "TMGH",
            "التجاري الدولي": "COMI",
            "بلتون": "BTFH",
            "القلعه": "CCAP",
            "هيرميس": "HRHO",
            "السويدي": "SWDY",
            "مصر الجديده": "HELI",
            "مدينه مصر": "MASR",
            "بالم هيلز": "PHDC",
            "سوديك": "OCDI",
            "ابن سينا": "ISPH",
            "ابو قير": "ABUK",
            "موبكو": "MFPC",
            "سيدي كرير": "SKPC",
            "اموك": "AMOC",
            "المصريه للاتصالات": "ETEL",
            "وي للاتصالات": "ETEL",
            "الشرقيه للدخان": "EAST",
            "اي فاينانس": "EFIH",
            "حديد عز": "ESRS",
            "عتاقه": "ATQA",
            "كيما": "EGCH",
            "زهراء المعادي": "ZMID",
            "اعمار": "EMFD",
            "اوراسكوم": "ORAS",
            "جي بي": "GBCO",
            "ايبيكو": "PHAR",
            "ممفيس": "MPCI",
            "جنوب الوادي": "SVCE",
            "العبور للاستثمار": "OBRI",
        }
        for alias, sym in arabic_aliases.items():
            if alias in norm_text and sym not in found:
                found.append(sym)

        for row in catalog:
            sym = str(row.get("symbol") or "").upper().replace(".CA", "").replace(".EGX", "").strip()
            name_ar = str(row.get("name_ar") or "").strip()
            if sym and name_ar and len(name_ar) >= 4:
                norm_name = _normalize_ar(name_ar)
                if norm_name in norm_text and sym not in found:
                    found.append(sym)

        return found[:8], name_map

    # Non-EGX markets: build localized name_map and extract exchange-accurate tickers
    name_map = {}
    if exch == "TADAWUL":
        try:
            from api.saudi_stock_aliases import SAUDI_STOCK_NAMES_AR, extract_all_saudi_symbols
            name_map.update(SAUDI_STOCK_NAMES_AR)
        except Exception:
            extract_all_saudi_symbols = None  # type: ignore[assignment]
    else:
        extract_all_saudi_symbols = None  # type: ignore[assignment]

    catalog = _get_market_stocks_catalog(exch)
    for row in catalog:
        sym = _strip_market_symbol_suffix(str(row.get("symbol") or ""))
        if sym:
            name_map.setdefault(sym, str(row.get("name_ar") or row.get("name") or sym))
            if row.get("name_ar"):
                name_map[sym] = str(row["name_ar"])

    found = []
    if exch == "TADAWUL":
        if extract_all_saudi_symbols is not None:
            for s in extract_all_saudi_symbols(text):
                if s not in found:
                    found.append(s)
        for m_num in re.finditer(r"(?<!\d)([1-9]\d{3})(?:\.(?:SR|SA|TADAWUL))?(?!\d)", text, re.IGNORECASE):
            code = m_num.group(1)
            if code in name_map or re.search(r"\.(?:SR|SA|TADAWUL)\b", m_num.group(0), re.IGNORECASE):
                if code not in found:
                    found.append(code)
    else:
        for tok in re.findall(r"[A-Za-z0-9=]{2,14}(?:\.(?:QA|QE|QSE|DU|DFM|AE|AD|ADX|KW|KSE))?", text, re.IGNORECASE):
            core = _strip_market_symbol_suffix(tok)
            if "." in tok or "=" in tok:
                if core and core not in found:
                    found.append(core)
            elif core not in _NON_TICKER_STOP_WORDS and name_map and core in name_map:
                if core not in found:
                    found.append(core)

    norm_text = _normalize_ar(text)
    for alias, sym in _GCC_ARABIC_ALIASES_BY_EXCHANGE.get(exch, {}).items():
        if alias in norm_text and sym not in found:
            found.append(sym)

    for row in catalog:
        sym = _strip_market_symbol_suffix(str(row.get("symbol") or ""))
        name_ar = str(row.get("name_ar") or "").strip()
        if sym and name_ar and len(name_ar) >= 4:
            if _normalize_ar(name_ar) in norm_text and sym not in found:
                found.append(sym)

    return found[:8], name_map


def _fetch_market_indicators_brief(
    symbols: List[str],
    prompt: str = "",
    task_name: str = "",
    user_id: str = "",
    *,
    in_trading_hours: bool = False,
    market: str = "EGX",
) -> str:
    """Fetches rich precalculated technical indicators, open recommendations, Wyckoff scans, disclosures, and full 15-stock portfolio across EGX & GCC."""
    try:
        from api.agentic_chat.market_registry import (
            currency_for_market,
            currency_for_symbol,
            get_market_config,
            normalize_exchange_code,
        )
        eff_mkt = normalize_exchange_code(market)
        mkt_cfg = get_market_config(eff_mkt)
        mkt_curr = currency_for_market(eff_mkt) or "ج.م"
        mkt_label_ar = mkt_cfg.name_ar
    except Exception:
        eff_mkt = str(market or "EGX").strip().upper() or "EGX"
        mkt_curr = "ج.م"
        mkt_label_ar = "البورصة المصرية"
        currency_for_symbol = lambda _s, m="EGX": mkt_curr  # type: ignore[assignment]

    combined_text = f"{task_name} {prompt}"
    extracted_syms, name_map = _extract_symbols_from_text(combined_text, exchange=eff_mkt)
    all_symbols = list(dict.fromkeys([_strip_market_symbol_suffix(s) for s in (symbols or []) if s] + extracted_syms))[:15]

    sections: List[str] = []

    # 1. User Portfolio (Primary Supabase always; filter indicator lookups cleanly by target market)
    if user_id and _contains_personal_portfolio_intent(combined_text):
        pos_rows = _supabase_request(
            f"positions?user_id=eq.{user_id}&status=eq.open&select=symbol,quantity,entry_price&limit=15"
        ) or []
        if not pos_rows:
            pos_rows = _supabase_request(
                f"positions?user_id=eq.{user_id}&status=eq.OPEN&select=symbol,quantity,entry_price&limit=15"
            ) or []
        if isinstance(pos_rows, list) and pos_rows:
            port_lines = ["💼 محفظة المشترك المسجلة حالياً:"]
            for p in pos_rows:
                psym, pos_mkt = _resolve_pos_symbol_and_market(str(p.get("symbol") or ""))
                if not psym:
                    continue
                if pos_mkt == eff_mkt or (eff_mkt != "EGX" and psym in name_map):
                    if psym not in all_symbols and len(all_symbols) < 15:
                        all_symbols.append(psym)
                pname = name_map.get(psym, psym)
                pos_curr = currency_for_symbol(psym, pos_mkt) or mkt_curr
                port_lines.append(
                    f"• #{psym} ({pname}): الكمية {p.get('quantity') or 'غير محددة'} | متوسط الشراء {p.get('entry_price') or 0} {pos_curr}"
                )
            sections.append("\n".join(port_lines))

    # 2. Specific Symbols (all up to 15, deduplicated to latest row per symbol) or Top Bullish Market Indicators
    if eff_mkt == "EGX":
        if all_symbols:
            sym_filter = ",".join(all_symbols[:15])
            raw_rows = _supabase_request(
                f"stock_technical_indicators?symbol=in.({sym_filter})&select=symbol,date,close,change_pct,volume,r_vol,rsi_14,ema_20,ema_50,ema_200,macd,macd_signal,bb_upper,bb_lower,atr_14,vwap_20,cmf_20,egx_ai_score,divergence_summary&order=date.desc&limit=45"
            ) or []
            rows: List[Dict[str, Any]] = []
            seen_syms: set[str] = set()
            for r in (raw_rows if isinstance(raw_rows, list) else []):
                rsym = str(r.get("symbol") or "").upper()
                if rsym and rsym not in seen_syms:
                    seen_syms.add(rsym)
                    rows.append(r)
        else:
            latest_ti_rows = _supabase_request(
                "stock_technical_indicators?exchange=eq.EGX&select=date&order=date.desc&limit=1"
            ) or []
            latest_ti_date = (
                latest_ti_rows[0].get("date")
                if isinstance(latest_ti_rows, list) and latest_ti_rows and isinstance(latest_ti_rows[0], dict)
                else None
            )
            ti_date_filter = f"&date=eq.{latest_ti_date}" if latest_ti_date else ""
            ti_limit = 15 if any(k in combined_text for k in ("15", "١٥", "خمسه عشر", "خمسة عشر", "12", "١٢")) else 10
            rows = _supabase_request(
                f"stock_technical_indicators?exchange=eq.EGX{ti_date_filter}&change_pct=gt.0&rsi_14=gte.45&rsi_14=lte.75&select=symbol,date,close,change_pct,volume,r_vol,rsi_14,ema_20,ema_50,ema_200,macd,macd_signal,bb_upper,bb_lower,atr_14,vwap_20,cmf_20,egx_ai_score,divergence_summary&order=egx_ai_score.desc.nullslast,r_vol.desc.nullslast&limit={ti_limit}"
            ) or []
            if not rows:
                rows = _supabase_request(
                    f"stock_technical_indicators?exchange=eq.EGX{ti_date_filter}&select=symbol,date,close,change_pct,volume,r_vol,rsi_14,ema_20,ema_50,ema_200,bb_upper,bb_lower,atr_14,vwap_20,egx_ai_score&order=volume.desc&limit={ti_limit}"
                ) or []
    else:
        gcc_rich_cols = (
            "symbol,date,updated_at,close,change_pct,volume,r_vol,volume_sma_20,"
            "rsi_14,ema_20,ema_50,ema_200,macd,macd_signal,bb_upper,bb_lower,"
            "atr_14,vwap_20,cmf_20,king_ai_score"
        )
        gcc_safe_cols = (
            "symbol,updated_at,close,change_pct,volume,volume_sma_20,"
            "rsi_14,ema_50,ema_200,vwap_20,momentum_10,atr_14,adx_14,cmf_20"
        )
        if all_symbols:
            sym_filter = ",".join(all_symbols[:15])
            raw_rows = _market_supabase_request(
                f"stock_technical_indicators?exchange=eq.{eff_mkt}&symbol=in.({sym_filter})&select={gcc_rich_cols}&order=date.desc&limit=45",
                exchange=eff_mkt,
            )
            if raw_rows is None:
                raw_rows = _market_supabase_request(
                    f"stock_technical_indicators?exchange=eq.{eff_mkt}&symbol=in.({sym_filter})&select={gcc_safe_cols}&order=updated_at.desc&limit=45",
                    exchange=eff_mkt,
                ) or []
            rows = []
            seen_syms = set()
            for r in (raw_rows if isinstance(raw_rows, list) else []):
                rsym = _strip_market_symbol_suffix(str(r.get("symbol") or ""))
                if rsym and rsym not in seen_syms:
                    seen_syms.add(rsym)
                    rows.append(r)
        else:
            latest_ti_rows = _market_supabase_request(
                f"stock_technical_indicators?exchange=eq.{eff_mkt}&select=date&order=date.desc&limit=1",
                exchange=eff_mkt,
            )
            latest_ti_date = (
                latest_ti_rows[0].get("date")
                if isinstance(latest_ti_rows, list) and latest_ti_rows and isinstance(latest_ti_rows[0], dict)
                else None
            )
            ti_date_filter = f"&date=eq.{latest_ti_date}" if latest_ti_date else ""
            ti_limit = 15 if any(k in combined_text for k in ("15", "١٥", "خمسه عشر", "خمسة عشر", "12", "١٢")) else 10
            rows = _market_supabase_request(
                f"stock_technical_indicators?exchange=eq.{eff_mkt}{ti_date_filter}&change_pct=gt.0&rsi_14=gte.45&rsi_14=lte.75&select={gcc_rich_cols}&order=king_ai_score.desc.nullslast,r_vol.desc.nullslast&limit={ti_limit}",
                exchange=eff_mkt,
            )
            if rows is None or not rows:
                rows = _market_supabase_request(
                    f"stock_technical_indicators?exchange=eq.{eff_mkt}{ti_date_filter}&change_pct=gt.0&rsi_14=gte.45&rsi_14=lte.75&select={gcc_safe_cols}&order=change_pct.desc.nullslast,volume.desc.nullslast&limit={ti_limit}",
                    exchange=eff_mkt,
                ) or []
            if not rows:
                rows = _market_supabase_request(
                    f"stock_technical_indicators?exchange=eq.{eff_mkt}&select={gcc_safe_cols}&order=volume.desc.nullslast&limit={ti_limit}",
                    exchange=eff_mkt,
                ) or []

    fund_brief_map: Dict[str, Dict[str, Any]] = {}
    open_stop_map: Dict[str, float] = {}
    if isinstance(rows, list) and rows:
        row_syms = [_strip_market_symbol_suffix(str(r.get("symbol") or "")) for r in rows if r.get("symbol")][:20]
        if row_syms:
            sym_in = ",".join(row_syms)
            f_rows = _market_supabase_request(
                f"stock_fundamentals?exchange=eq.{eff_mkt}&symbol=in.({sym_in})&select=symbol,fund_score,data&limit={len(row_syms) + 2}",
                exchange=eff_mkt,
            ) or []
            for fr in (f_rows if isinstance(f_rows, list) else []):
                if isinstance(fr, dict) and fr.get("symbol"):
                    fund_brief_map[_strip_market_symbol_suffix(str(fr["symbol"]))] = fr
            if eff_mkt == "EGX":
                sr_rows = _supabase_request(
                    f"scan_results?symbol=in.({sym_in})&status=eq.open&select=symbol,stop_loss&limit=20"
                ) or []
            else:
                sr_rows = _market_supabase_request(
                    f"scan_results?exchange=eq.{eff_mkt}&symbol=in.({sym_in})&status=in.(open,active)&select=symbol,stop_loss&limit=20",
                    exchange=eff_mkt,
                ) or []
            for sr in (sr_rows if isinstance(sr_rows, list) else []):
                if isinstance(sr, dict) and sr.get("symbol") and sr.get("stop_loss") is not None:
                    try:
                        open_stop_map[_strip_market_symbol_suffix(str(sr["symbol"]))] = float(sr["stop_loss"])
                    except Exception:
                        pass

        lines = [f"📊 بيانات {mkt_label_ar} والمؤشرات الفنية المسجلة (مقارنات المتوسطات محسوبة بدقة في الخلفية):"]
        for r in rows:
            sym = _strip_market_symbol_suffix(str(r.get("symbol") or ""))
            ar_name = name_map.get(sym, "")
            label = f"#{sym} ({ar_name})" if ar_name and ar_name != sym else f"#{sym}"
            row_curr = currency_for_symbol(sym, eff_mkt) or mkt_curr
            close = r.get("close")
            close_f = float(close or 0.0)
            r_date = str(r.get("date") or r.get("updated_at") or "")[:10]
            chg = float(r.get("change_pct") or 0)
            rsi = float(r.get("rsi_14") or 50)
            ema20 = r.get("ema_20")
            ema50 = r.get("ema_50")
            ema200 = r.get("ema_200")
            rvol = r.get("r_vol")
            if rvol is None and r.get("volume") is not None and r.get("volume_sma_20"):
                try:
                    vsma = float(r["volume_sma_20"])
                    if vsma > 0:
                        rvol = float(r["volume"]) / vsma
                except Exception:
                    pass
            bb_u = r.get("bb_upper")
            bb_l = r.get("bb_lower")
            atr_raw = r.get("atr_14")
            atr_f = float(atr_raw) if atr_raw is not None else 0.0
            sup1 = float(bb_l) if (bb_l is not None and 0 < float(bb_l) < close_f) else (round(max(close_f * 0.85, close_f - 1.5 * atr_f), 3) if close_f > 0 and atr_f > 0 else None)
            res1 = float(bb_u) if (bb_u is not None and float(bb_u) > close_f) else (round(close_f + 2.0 * atr_f, 3) if close_f > 0 and atr_f > 0 else None)
            sr_stop = open_stop_map.get(sym)
            stp = sr_stop if (sr_stop is not None and 0 < sr_stop < close_f) else (round(sup1 * 0.98, 3) if sup1 and sup1 > 0 else (round(max(close_f * 0.82, close_f - 2.0 * atr_f), 3) if close_f > 0 and atr_f > 0 else None))
            ai_sc = r.get("egx_ai_score") if r.get("egx_ai_score") is not None else r.get("king_ai_score")
            extra = []
            if ema20:
                e20_f = float(ema20)
                pos20 = "فوق EMA20 ✅" if close_f >= e20_f else "تحت EMA20 🔴"
                ema20_str = f"{e20_f:.3f} ({pos20})"
            else:
                ema20_str = "غير متاح"
            if ema50:
                e50_f = float(ema50)
                pos50 = "فوق EMA50 ✅" if close_f >= e50_f else "تحت EMA50 🔴"
                extra.append(f"EMA50: {e50_f:.3f} ({pos50})")
            if ema200:
                e200_f = float(ema200)
                pos200 = "فوق EMA200 ✅" if close_f >= e200_f else "تحت EMA200 🔴"
                extra.append(f"EMA200: {e200_f:.3f} ({pos200})")
            if sup1 or res1 or stp:
                lvl_parts = []
                if sup1:
                    lvl_parts.append(f"دعم {float(sup1):.3f}")
                if res1:
                    lvl_parts.append(f"مقاومة {float(res1):.3f}")
                if stp:
                    lvl_parts.append(f"وقف محسوب {float(stp):.3f}")
                if lvl_parts:
                    extra.append(" | ".join(lvl_parts))
            elif bb_l and bb_u:
                extra.append(f"دعم/مقاومة بولينجر: {float(bb_l):.2f} - {float(bb_u):.2f}")
            if rvol is not None:
                rv_f = float(rvol)
                try:
                    from api.agentic_chat.intraday_volume import resolve_intraday_r_vol
                    rv_info = resolve_intraday_r_vol(rv_f, r_date, exchange=eff_mkt)
                    eff_rv = rv_info.get("effective_r_vol")
                    if rv_info.get("r_vol_note_ar"):
                        extra.append(f"السيولة النسبية: {rv_info['r_vol_note_ar']}")
                    elif eff_rv is not None:
                        extra.append(f"السيولة النسبية: {eff_rv:.2f}x")
                except Exception:
                    if in_trading_hours and rv_f < 0.15:
                        extra.append(f"السيولة النسبية: {rv_f:.2f}x (تراكمي لحظي أثناء الجلسة — غير مكتمل بعد)")
                    else:
                        extra.append(f"السيولة النسبية: {rv_f:.2f}x")
            if ai_sc is not None:
                ai_val = float(ai_sc)
                ai_pct = ai_val * 100.0 if ai_val <= 1.0 else (ai_val * 10.0 if ai_val <= 10.0 else ai_val)
                if ai_pct > 0:
                    extra.append(f"تقييم AI: {ai_pct:.0f}/100")
            fr = fund_brief_map.get(sym) or {}
            fs = fr.get("fund_score")
            fdata = fr.get("data") if isinstance(fr.get("data"), dict) else {}
            eps_f = fdata.get("eps")
            if (fs is not None and float(fs) < 40.0) or (eps_f is not None and float(eps_f) < 0):
                extra.append(f"⚠️ تحذير مالي: شركة خاسرة أو تقييم مالي ضعيف ({fs or 'ضعيف'})")
            extra_str = (" | " + " | ".join(extra)) if extra else ""
            date_tag = f" [{r_date}]" if r_date else ""
            lines.append(
                f"• {label}{date_tag}: آخر سعر مسجل {close} {row_curr} ({chg:+.2f}%) | RSI: {rsi:.1f} | EMA20: {ema20_str}{extra_str}"
            )
        sections.append("\n".join(lines))

    # 2b. Official Disclosures (SAUDI_SUPABASE also stores Tadawul disclosures in egx_disclosures; isolate non-EGX/non-TADAWUL markets)
    if all_symbols and eff_mkt in ("EGX", "TADAWUL") and any(k in combined_text for k in ("أخبار", "اخبار", "إفصاح", "افصاح", "توزيع", "مجاني", "مجانى", "رأس المال", "استحقاق")):
        disc_filter = ",".join(all_symbols[:15])
        disc_rows = _market_supabase_request(
            f"egx_disclosures?symbol=in.({disc_filter})&select=symbol,disclosure_date,title,sentiment&order=disclosure_date.desc&limit=6",
            exchange=eff_mkt,
        ) or []
        if isinstance(disc_rows, list) and disc_rows:
            disc_lines = ["📢 أحدث الإفصاحات الرسمية المسجلة للأسهم المطلوبة:"]
            for d in disc_rows:
                dsym = _strip_market_symbol_suffix(str(d.get("symbol") or ""))
                ddate = str(d.get("disclosure_date") or "")[:10]
                dtitle = str(d.get("title") or "").strip()[:160]
                if dtitle:
                    disc_lines.append(f"• #{dsym} [{ddate}]: {dtitle}")
            if len(disc_lines) > 1:
                sections.append("\n".join(disc_lines))

    # 3. Open Recommendations
    if any(k in combined_text for k in ("توصي", "صفق", "مفتوح", "إشارات", "اشارات", "مرشح", "ايجاب", "إيجاب", "شراء")):
        if eff_mkt == "EGX":
            rec_rows = _supabase_request(
                "scan_results?is_public=eq.true&status=eq.open&select=symbol,name,entry_price,target_price,stop_loss,last_close,profit_loss_pct&limit=10"
            ) or []
        else:
            rec_rows = _market_supabase_request(
                f"scan_results?exchange=eq.{eff_mkt}&status=in.(open,active)&select=symbol,signal,entry_price,target_price,stop_loss,created_at&order=created_at.desc&limit=10",
                exchange=eff_mkt,
            ) or []
        if isinstance(rec_rows, list) and rec_rows:
            rec_lines = [f"🎯 التوصيات والصفقات المفتوحة المعتمدة حالياً ({mkt_label_ar}):"]
            for rec in rec_rows:
                rsym = _strip_market_symbol_suffix(str(rec.get("symbol") or ""))
                rname = name_map.get(rsym) or rec.get("name") or rsym
                rec_curr = currency_for_symbol(rsym, eff_mkt) or mkt_curr
                parts_rec = [f"• #{rsym} ({rname}): سعر الدخول {rec.get('entry_price')} {rec_curr}"]
                if rec.get("last_close") is not None:
                    parts_rec.append(f"السعر الحالي {rec.get('last_close')} {rec_curr}")
                if rec.get("target_price") is not None:
                    parts_rec.append(f"المستهدف {rec.get('target_price')} {rec_curr}")
                if rec.get("stop_loss") is not None:
                    parts_rec.append(f"وقف الخسارة {rec.get('stop_loss')} {rec_curr}")
                if rec.get("profit_loss_pct") is not None:
                    parts_rec.append(f"العائد الحالي {float(rec.get('profit_loss_pct') or 0):+.2f}%")
                elif rec.get("signal"):
                    parts_rec.append(f"الإشارة {rec.get('signal')}")
                rec_lines.append(" | ".join(parts_rec))
            sections.append("\n".join(rec_lines))

    # 4. Wyckoff Accumulation & Breakout Scan Summary
    if any(k in combined_text for k in ("وايكوف", "تجميع", "سيول", "موج", "اخترق", "اختراق", "نموذج", "اليوت", "إليوت", "ارتداد", "ايجاب", "إيجاب")):
        if eff_mkt == "EGX":
            latest_scan_rows = _supabase_request(
                "stock_scans_summary?select=scan_date&order=scan_date.desc&limit=1"
            ) or []
            latest_scan_date = (
                latest_scan_rows[0].get("scan_date")
                if isinstance(latest_scan_rows, list) and latest_scan_rows and isinstance(latest_scan_rows[0], dict)
                else None
            )
            scan_date_filter = f"&scan_date=eq.{latest_scan_date}" if latest_scan_date else ""
            acc_rows = _supabase_request(
                f"stock_scans_summary?acc_score=gte.50{scan_date_filter}&wyckoff_phase=neq.distribution&select=symbol,scan_date,signal,wyckoff_phase,acc_score,vol_ratio,consecutive_acc_days,rsi_14,change_pct&order=acc_score.desc&limit=8"
            ) or []
        else:
            exch_q = f"exchange=eq.{eff_mkt}&"
            latest_scan_rows = _market_supabase_request(
                f"stock_scans_summary?{exch_q}select=scan_date&order=scan_date.desc&limit=1",
                exchange=eff_mkt,
            )
            if latest_scan_rows is None and eff_mkt == "TADAWUL":
                exch_q = ""
                latest_scan_rows = _market_supabase_request(
                    "stock_scans_summary?select=scan_date&order=scan_date.desc&limit=1",
                    exchange=eff_mkt,
                )
            latest_scan_date = (
                latest_scan_rows[0].get("scan_date")
                if isinstance(latest_scan_rows, list) and latest_scan_rows and isinstance(latest_scan_rows[0], dict)
                else None
            )
            scan_date_filter = f"&scan_date=eq.{latest_scan_date}" if latest_scan_date else ""
            acc_rows = _market_supabase_request(
                f"stock_scans_summary?{exch_q}acc_score=gte.50{scan_date_filter}&wyckoff_phase=neq.distribution&select=symbol,scan_date,signal,wyckoff_phase,acc_score,vol_ratio,consecutive_acc_days,rsi_14,change_pct&order=acc_score.desc&limit=8",
                exchange=eff_mkt,
            )
            if acc_rows is None:
                acc_rows = _market_supabase_request(
                    f"stock_scans_summary?{exch_q}acc_score=gte.50{scan_date_filter}&wyckoff_phase=neq.distribution&select=symbol,scan_date,signal,wyckoff_phase,acc_score,vol_ratio,consecutive_acc_days&order=acc_score.desc&limit=8",
                    exchange=eff_mkt,
                ) or []
        if isinstance(acc_rows, list) and acc_rows:
            acc_lines = [f"🔍 نتائج مسح التجميع المؤسسي (وايكوف) والسيولة الذكية — {mkt_label_ar}:"]
            for a in acc_rows:
                asym = _strip_market_symbol_suffix(str(a.get("symbol") or ""))
                aname = name_map.get(asym, asym)
                tail_parts = []
                if a.get("rsi_14") is not None:
                    tail_parts.append(f"RSI={float(a['rsi_14']):.1f}")
                if a.get("change_pct") is not None:
                    tail_parts.append(f"تغير={float(a['change_pct']):+.2f}%")
                tail_str = (" | " + " | ".join(tail_parts)) if tail_parts else ""
                acc_lines.append(
                    f"• #{asym} ({aname}): مرحلة وايكوف={a.get('wyckoff_phase')} | إشارة={a.get('signal')} | قوة التجميع={a.get('acc_score')}% | أيام تجميع متتالية={a.get('consecutive_acc_days')} | سيولة نسبية={float(a.get('vol_ratio') or 1.0):.2f}x{tail_str}"
                )
            sections.append("\n".join(acc_lines))

    return "\n\n".join(sections)


_CUSTOM_RANKING_RE = re.compile(
    r"(?:اعلى|أعلى|اقوى|أقوى|اكبر|أكبر|افضل|أفضل)\s+(?:\d+|عشر|عشرة|خمس|خمسة|ثلاث|ثلاثة|سبع|سبعة)",
    re.IGNORECASE,
)


_PERSONAL_AUTOMATION_KEYWORDS = (
    "محفظ", "اسهمي", "مركزي", "مراكزي", "شرائي", "كاش", "رصيدي",
    "الاسهم المراد بيعها", "اسهم البيع", "تدوير المحفظ", "اعاده تدوير", "اعاده التوازن",
    "portfolio", "holdings", "my stocks",
)


def _contains_personal_portfolio_intent(text: str) -> bool:
    """Detect portfolio/personal intent even with Arabic diacritics or trailing ى/ي dialect variations."""
    raw = str(text or "").strip()
    if not raw:
        return False
    norm = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", _normalize_ar(raw)).lower()
    return any(k in norm for k in _PERSONAL_AUTOMATION_KEYWORDS)


def _is_cacheable_automation_prompt(prompt: str) -> bool:
    """Return True only when an automated prompt is generic & free of portfolio/custom ranking constraints."""
    text = str(prompt or "").strip()
    if not text:
        return False
    if _contains_personal_portfolio_intent(text):
        return False
    if _CUSTOM_RANKING_RE.search(text):
        return False
    return True


def _record_cached_automation_usage() -> None:
    """Record zero-token/zero-cost cached hit usage into thread-local storage."""
    try:
        from api.agentic_chat.pipeline import _finalize_usage_cost, _new_usage_accumulator
        _AUTO_METRICS_TLS.last_usage = _finalize_usage_cost(_new_usage_accumulator(), cached=True)
    except Exception:
        pass


def _guard_automation_reply(text: str, market: str = "EGX") -> str:
    try:
        from api.agentic_chat.output_guard import verify_and_guard_reply
        return verify_and_guard_reply(text, [], market=market).get("reply") or text
    except Exception:
        return text


_TZ_AR_LABELS: Dict[str, str] = {
    "Africa/Cairo": "القاهرة",
    "Asia/Riyadh": "الرياض",
    "Asia/Qatar": "الدوحة",
    "Asia/Dubai": "دبي",
    "Asia/Kuwait": "الكويت",
    "UTC": "UTC",
}


def _format_hhmm_ar(minutes: int) -> str:
    hr, mn = divmod(max(0, int(minutes)), 60)
    suffix = "م" if hr >= 12 else "ص"
    disp_hr = hr if 1 <= hr <= 12 else (hr - 12 if hr > 12 else 12)
    return f"{disp_hr}:{mn:02d} {suffix}"


def _format_trading_days_ar(weekdays: tuple[int, ...]) -> str:
    if set(weekdays) == {6, 0, 1, 2, 3}:
        return "الأحد–الخميس"
    if set(weekdays) == {0, 1, 2, 3, 4}:
        return "الإثنين–الجمعة"
    return "أيام التداول الرسمية"


def _generate_ai_consultation(prompt: str, user_name: str, user_id: str = "") -> str:
    """Generates a professional multi-market stock consultation using DeepSeek with snapshot & prefix caching."""
    _AUTO_METRICS_TLS.last_usage = None
    _AUTO_METRICS_TLS.last_cached = False
    _AUTO_METRICS_TLS.last_cache_key = None

    target_exchange = _detect_automation_market(prompt, user_name)
    try:
        from api.agentic_chat.market_registry import get_market_config, get_market_now
        mkt_cfg = get_market_config(target_exchange)
        mkt_now_fn = get_market_now
    except Exception:
        mkt_cfg = None
        mkt_now_fn = None

    is_public_prompt = _is_cacheable_automation_prompt(prompt) and not _contains_personal_portfolio_intent(user_name)
    if is_public_prompt:
        try:
            from api.agentic_chat.analysis_cache import build_analysis_cache_key, get_vip_analysis_cache
            auto_cache_key = build_analysis_cache_key(prompt, market=target_exchange)
            if auto_cache_key:
                cached_hit = get_vip_analysis_cache(auto_cache_key, user_id=user_id, market=target_exchange)
                if cached_hit and cached_hit.get("reply"):
                    _AUTO_METRICS_TLS.last_cached = True
                    _AUTO_METRICS_TLS.last_cache_key = auto_cache_key
                    _record_cached_automation_usage()
                    return str(cached_hit["reply"])
        except Exception as cache_err:
            logger.debug(f"[AUTOMATIONS_WORKER] Cache lookup skipped: {cache_err}")

    deepseek_key = os.getenv("DEEPSEEK_OFFICIAL_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
    if not deepseek_key:
        return "أهلاً بك! تعذر الاتصال بمحرك الذكاء الاصطناعي حالياً لعدم توفر المفتاح. برجاء المراجعة مع الدعم الفني."

    arabic_days = ("الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
    if target_exchange == "EGX":
        now_cairo = dt.datetime.now(ZoneInfo("Africa/Cairo"))
        try:
            from api.egx_trading_calendar import is_egx_session
            egx_open = is_egx_session(now_cairo)
        except Exception:
            egx_open = False
        cairo_mins = now_cairo.hour * 60 + now_cairo.minute
        in_trading_hours = egx_open and (10 * 60 <= cairo_mins <= 14 * 60 + 30)
        words = re.findall(r"[A-Za-z]{2,8}", prompt)
        symbols = [w.upper() for w in words if w.upper() not in _NON_TICKER_STOP_WORDS]
        day_ar = arabic_days[now_cairo.weekday()]
        session_status_str = (
            f"جلسة البورصة المصرية مفتوحة حالياً للتداول (10:00 ص – 2:30 م بتوقيت القاهرة) — التوقيت الآن: {day_ar} {now_cairo.strftime('%Y-%m-%d %H:00')} القاهرة."
            if in_trading_hours
            else f"البورصة المصرية مغلقة حالياً (خارج ساعات التداول الرسمية 10:00 ص – 2:30 م الأحد–الخميس) — التوقيت الآن: {day_ar} {now_cairo.strftime('%Y-%m-%d %H:00')} القاهرة."
        )
        mkt_name_ar = "البورصة المصرية"
        cache_country = "Egypt"
    else:
        try:
            from api.agentic_chat.intraday_volume import get_exchange_session_state
            sess = get_exchange_session_state(target_exchange)
            in_trading_hours = bool(sess.get("is_live_session"))
            sess_len = int(sess.get("session_len_min") or 0)
        except Exception:
            in_trading_hours = False
            sess_len = 300
        mkt_now = mkt_now_fn(target_exchange) if mkt_now_fn is not None else dt.datetime.now(ZoneInfo("Asia/Riyadh"))
        symbols = []
        day_ar = arabic_days[mkt_now.weekday()]
        mkt_name_ar = mkt_cfg.name_ar if mkt_cfg else target_exchange
        cache_country = mkt_cfg.name_en if mkt_cfg else target_exchange
        tz_ar = _TZ_AR_LABELS.get(mkt_cfg.timezone_name if mkt_cfg else "", mkt_cfg.timezone_name if mkt_cfg else "UTC")
        if sess_len >= 1400 or target_exchange == "COMMODITIES":
            session_status_str = (
                f"أسواق {mkt_name_ar} العالمية مفتوحة حالياً للتداول على مدار الساعة (الإثنين–الجمعة UTC) — التوقيت الآن: {day_ar} {mkt_now.strftime('%Y-%m-%d %H:00')} UTC."
                if in_trading_hours
                else f"أسواق {mkt_name_ar} العالمية مغلقة حالياً (عطلة نهاية الأسبوع) — التوقيت الآن: {day_ar} {mkt_now.strftime('%Y-%m-%d %H:00')} UTC."
            )
        else:
            open_ar = _format_hhmm_ar(mkt_cfg.session_open_min if mkt_cfg else 600)
            close_ar = _format_hhmm_ar(mkt_cfg.session_close_min if mkt_cfg else 900)
            days_ar = _format_trading_days_ar(mkt_cfg.trading_weekdays if mkt_cfg else (6, 0, 1, 2, 3))
            session_status_str = (
                f"جلسة {mkt_name_ar} مفتوحة حالياً للتداول ({open_ar} – {close_ar} بتوقيت {tz_ar}) — التوقيت الآن: {day_ar} {mkt_now.strftime('%Y-%m-%d %H:00')} {tz_ar}."
                if in_trading_hours
                else f"{mkt_name_ar} مغلق حالياً (خارج ساعات التداول الرسمية {open_ar} – {close_ar} {days_ar}) — التوقيت الآن: {day_ar} {mkt_now.strftime('%Y-%m-%d %H:00')} {tz_ar}."
            )

    indicators_brief = _fetch_market_indicators_brief(
        symbols,
        prompt=prompt,
        task_name=user_name,
        user_id=user_id,
        in_trading_hours=in_trading_hours,
        market=target_exchange,
    )

    # Content-Addressed SHA-256 Snapshot Cache:
    # Strictly isolated per user_id (RAM-only) for portfolio/personal prompts or personal task names;
    # shareable (RAM + market_cache) ONLY when zero personal portfolio data is present.
    has_personal_data = "💼 محفظة المشترك" in str(indicators_brief or "")
    is_public_snapshot = bool(is_public_prompt and not has_personal_data)
    snap_key: Optional[str] = None
    snap_ttl = 3600.0 * 6 if in_trading_hours else 3600.0 * 16
    if indicators_brief and str(indicators_brief).strip():
        scope_tag: Optional[str] = (
            "pub"
            if is_public_snapshot
            else (f"u_{hashlib.sha256(str(user_id).encode('utf-8')).hexdigest()[:12]}" if user_id else None)
        )
        if scope_tag:
            norm_prompt = re.sub(r"\s+", " ", _normalize_ar(prompt)).strip()
            fp_raw = f"v1|{target_exchange}|{scope_tag}|{norm_prompt}|{int(in_trading_hours)}|{indicators_brief}"
            snap_key = f"auto_snap_{scope_tag}_{hashlib.sha256(fp_raw.encode('utf-8')).hexdigest()[:20]}"

            ram_hit = _snap_cache_get(snap_key)
            if ram_hit:
                _AUTO_METRICS_TLS.last_cached = True
                _AUTO_METRICS_TLS.last_cache_key = snap_key
                _record_cached_automation_usage()
                return ram_hit

            if is_public_snapshot and not _is_test_runtime():
                try:
                    mc_rows = _supabase_request(
                        f"market_cache?cache_key=eq.{snap_key}&select=payload,computed_at&limit=1"
                    ) or []
                    if isinstance(mc_rows, list) and mc_rows and isinstance(mc_rows[0], dict):
                        mc_payload = mc_rows[0].get("payload")
                        mc_ts = mc_rows[0].get("computed_at")
                        if isinstance(mc_payload, dict) and mc_payload.get("reply") and mc_ts:
                            ts_dt = dt.datetime.fromisoformat(str(mc_ts).replace("Z", "+00:00"))
                            age_sec = (dt.datetime.now(dt.timezone.utc) - ts_dt).total_seconds()
                            max_age = 15 * 60.0 if in_trading_hours else 18 * 3600.0
                            if 0 <= age_sec <= max_age:
                                cached_txt = str(mc_payload["reply"])
                                _snap_cache_set(snap_key, cached_txt, snap_ttl)
                                _AUTO_METRICS_TLS.last_cached = True
                                _AUTO_METRICS_TLS.last_cache_key = snap_key
                                _record_cached_automation_usage()
                                return cached_txt
                except Exception as mc_err:
                    logger.debug(f"[AUTOMATIONS_WORKER] Public snapshot lookup skipped: {mc_err}")

    # Static immutable system prompt unlocks 100% DeepSeek Prefix Cache continuity across all hours & days.
    system_prompt = AUTOMATION_STATIC_SYSTEM_PROMPT

    prompt_user_label = "مشترك Pro" if is_public_snapshot else user_name
    user_content = (
        f"السوق المستهدف: {mkt_name_ar} ({target_exchange})\n"
        f"حالة الجلسة الآن: {session_status_str}\n"
        f"طلب الاستشارة المجدولة من المشترك ({prompt_user_label}):\n{prompt}"
    )
    if indicators_brief:
        user_content += f"\n\n{indicators_brief}"

    def _finalize_and_cache_reply(raw_reply: str) -> str:
        guarded = _guard_automation_reply(raw_reply, market=target_exchange)
        if snap_key and indicators_brief and guarded and "تعذر" not in guarded[:120]:
            _snap_cache_set(snap_key, guarded, snap_ttl)
            _AUTO_METRICS_TLS.last_cache_key = snap_key
            if is_public_snapshot and not _is_test_runtime():
                try:
                    _supabase_request(
                        "market_cache?on_conflict=cache_key",
                        method="POST",
                        payload={
                            "cache_key": snap_key,
                            "country": cache_country,
                            "payload": {"reply": guarded, "prompt": prompt[:120], "market": target_exchange},
                            "computed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                        },
                        extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                    )
                except Exception:
                    pass
        return guarded

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": 2800,
    }

    # 1. Primary engine: DeepSeek Chat with browser-standard User-Agent
    deepseek_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {deepseek_key}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    if requests is not None:
        try:
            r = requests.post(DEEPSEEK_API_URL, headers=deepseek_headers, json=payload, timeout=35)
            if r.status_code == 200:
                res_data = r.json()
                content = res_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if content:
                    _record_automation_deepseek_usage(res_data.get("usage"))
                    return _finalize_and_cache_reply(content)
            logger.warning(f"[AUTOMATIONS_WORKER] DeepSeek returned HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.warning(f"[AUTOMATIONS_WORKER] DeepSeek requests error: {e}")
    else:
        req = urllib.request.Request(
            DEEPSEEK_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=deepseek_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if content:
                    _record_automation_deepseek_usage(data.get("usage"))
                    return _finalize_and_cache_reply(content)
        except Exception as e:
            logger.warning(f"[AUTOMATIONS_WORKER] DeepSeek urllib error: {e}")

    # 2. Secondary fallback engine: Nvidia Llama-3.3-70B
    nvidia_key = (os.getenv("NVIDIA_API_KEY") or os.getenv("NVIDIA_SECONDARY_API_KEY") or "").strip()
    if nvidia_key:
        try:
            nv_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {nvidia_key}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            nv_payload = {
                "model": "meta/llama-3.3-70b-instruct",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.3,
                "max_tokens": 3200,
            }
            if requests is not None:
                nv_resp = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=nv_headers, json=nv_payload, timeout=30)
                if nv_resp.status_code == 200:
                    nv_data = nv_resp.json()
                    content = nv_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if content:
                        logger.info("[AUTOMATIONS_WORKER] Generated consultation via Nvidia Llama-3.3-70B fallback.")
                        return _guard_automation_reply(content, market=target_exchange)
                logger.warning(f"[AUTOMATIONS_WORKER] Nvidia API returned HTTP {nv_resp.status_code}: {nv_resp.text[:200]}")
        except Exception as e:
            logger.warning(f"[AUTOMATIONS_WORKER] Nvidia fallback error: {e}")

    # 3. Tertiary fallback: Structured technical analysis directly from real market indicators
    fallback_lines = [
        "📊 **تقرير المتابعة الفنية المجدولة — EGX BOTS**",
        f"👤 المشترك: **{user_name}** | الطلب: *{prompt}*",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if indicators_brief:
        fallback_lines.append("📈 **أحدث مؤشرات وأسعار السوق:**")
        fallback_lines.append(indicators_brief)
        fallback_lines.append("")
    fallback_lines.extend([
        "⚖️ **إدارة المخاطر:**",
        "• يرجى الالتزام بمستوى وقف الخسارة المحسوب أو الدعم القريب الموضح في المؤشرات أعلاه وتجنب الدخول بكامل السيولة في سهم واحد.",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💡 *تحديث دوري مؤتمت صادر عن محرك ARTORO AI لـ {mkt_name_ar}.*"
    ])
    return "\n".join(fallback_lines)


def _log_automation_to_chat_history(
    auto_id: str,
    user_id: str,
    name: str,
    prompt: str,
    reply_text: str,
    now_iso: str,
    latency_ms: Optional[int] = None,
    usage: Optional[Dict[str, Any]] = None,
    cached: bool = False,
    cache_key: Optional[str] = None,
) -> None:
    """Persists the scheduled consultation into ai_chat_sessions and ai_chat_messages using valid UUID auto_id."""
    try:
        try:
            asst_iso = (dt.datetime.fromisoformat(str(now_iso).replace("Z", "+00:00")) + dt.timedelta(seconds=1)).isoformat()
        except Exception:
            asst_iso = now_iso
        # 1. Upsert session in ai_chat_sessions so foreign key on ai_chat_messages(session_id) is satisfied
        _supabase_request(
            "ai_chat_sessions?on_conflict=id",
            method="POST",
            payload={
                "id": auto_id,
                "user_id": user_id,
                "title": f"⏰ {name}"[:80],
                "updated_at": asst_iso,
            },
            extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        # 2. Insert user prompt and assistant response with scheduled_automation source & usage metadata
        _supabase_request(
            "ai_chat_messages",
            method="POST",
            payload={
                "session_id": auto_id,
                "user_id": user_id,
                "role": "user",
                "content": f"[استشارة مجدولة: {name}] {prompt}",
                "created_at": now_iso,
            },
            extra_headers={"Prefer": "return=minimal"},
        )
        asst_meta: Dict[str, Any] = {
            "chat_source": "scheduled_automation",
            "engine": "deepseek-v3",
            "cached": bool(cached),
        }
        if cache_key:
            asst_meta["cache_key"] = cache_key
        if latency_ms is not None:
            asst_meta["latency_ms"] = int(latency_ms)
        if isinstance(usage, dict) and usage:
            asst_meta["usage"] = usage
        asst_payload: Dict[str, Any] = {
            "session_id": auto_id,
            "user_id": user_id,
            "role": "assistant",
            "content": reply_text,
            "created_at": asst_iso,
            "metadata": asst_meta,
        }
        if latency_ms is not None:
            asst_payload["latency_ms"] = int(latency_ms)
        _supabase_request(
            "ai_chat_messages",
            method="POST",
            payload=asst_payload,
            extra_headers={"Prefer": "return=minimal"},
        )
    except Exception as e:
        logger.warning(f"[AUTOMATIONS_WORKER] Chat history log skipped for {auto_id}: {e}")


def execute_single_automation(automation: Dict[str, Any], is_test: bool = False) -> Dict[str, Any]:
    """
    Executes a single scheduled automation:
    Verifies Pro, checks quota, generates AI response, sends to Telegram, and logs to DB.
    Note: Manual test runs (is_test=True) do NOT set last_run_date, so they never block
    the user's daily scheduled slot on the same day.
    """
    auto_id = automation["id"]
    user_id = automation["user_id"]
    name = automation.get("name") or "استشارة مجدولة"
    prompt = automation.get("prompt") or ""
    scheduled_time = automation.get("scheduled_time") or "08:30"
    today_cairo = get_cairo_time().strftime("%Y-%m-%d")

    # 0. Distributed Atomic Claim: Ensure only ONE worker/instance executes this automation today
    # Prevents duplicate runs between HF Space and local dev servers running concurrently
    if not is_test:
        claim_patch = _supabase_request(
            f"scheduled_chat_automations?id=eq.{auto_id}&or=(last_run_date.is.null,last_run_date.neq.{today_cairo})&select=id",
            method="PATCH",
            payload={
                "last_run_date": today_cairo,
                "last_run_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "last_status": "running",
            },
        )
        if not claim_patch or not isinstance(claim_patch, list) or len(claim_patch) == 0:
            logger.info(f"[AUTOMATIONS_WORKER] Automation {auto_id} was already claimed/executed today ({today_cairo}). Skipping duplicate run.")
            return {"ok": True, "reason": "already_claimed_today"}

    # 1. Pro check
    if not _is_user_pro(user_id):
        logger.info(f"[AUTOMATIONS_WORKER] Skipped {auto_id}: user {user_id} is not Pro.")
        _supabase_request(
            f"scheduled_chat_automations?id=eq.{auto_id}",
            method="PATCH",
            payload={"last_status": "pro_required", "last_error": "User does not have an active Pro subscription"},
        )
        return {"ok": False, "reason": "pro_required"}

    # 2. Resolve Telegram Target
    chat_id = _resolve_user_telegram(user_id, automation.get("telegram_chat_id"))
    if not chat_id:
        logger.info(f"[AUTOMATIONS_WORKER] Skipped {auto_id}: user {user_id} has no Telegram connected.")
        _supabase_request(
            f"scheduled_chat_automations?id=eq.{auto_id}",
            method="PATCH",
            payload={"last_status": "no_telegram_linked", "last_error": "No Telegram chat or channel linked to profile"},
        )
        return {"ok": False, "reason": "no_telegram_linked"}

    # 3. Quota check & deduction
    quota_allowed = _consume_user_quota(user_id, today_cairo)
    if not quota_allowed:
        logger.info(f"[AUTOMATIONS_WORKER] Skipped {auto_id}: user {user_id} monthly quota exceeded.")
        msg = (
            f"⚠️ **تنبيه أرتورو AI للاستشارة المجدولة ({name}):**\n\n"
            f"حان موعد استشارتك المجدولة الساعة `{scheduled_time}` بتوقيت القاهرة، ولكن تم استهلاك باقتك الشهرية من الرسائل بالكامل (350 رسالة).\n\n"
            f"لتجديد الرصيد أو الترقية: [اضغط هنا](https://egxbots.com/pricing)\n"
            f"لإدارة مواعيد استشاراتك: [الملف الشخصي](https://egxbots.com/profile)"
        )
        send_telegram_direct(chat_id, msg)
        patch_payload: Dict[str, Any] = {
            "last_status": "quota_exceeded",
            "last_error": "Monthly quota exhausted",
        }
        if not is_test:
            patch_payload["last_run_date"] = today_cairo
        _supabase_request(
            f"scheduled_chat_automations?id=eq.{auto_id}",
            method="PATCH",
            payload=patch_payload,
        )
        return {"ok": False, "reason": "quota_exceeded"}

    # 4. Generate AI consultation (timed + track usage metrics)
    user_name = automation.get("name") or "المستثمر"
    _t_gen_start = time.time()
    reply_text = _generate_ai_consultation(prompt, user_name, user_id=user_id)
    auto_latency_ms = max(int((time.time() - _t_gen_start) * 1000), 1)
    auto_usage = getattr(_AUTO_METRICS_TLS, "last_usage", None)
    auto_cached = bool(getattr(_AUTO_METRICS_TLS, "last_cached", False))
    auto_cache_key = getattr(_AUTO_METRICS_TLS, "last_cache_key", None)

    # 5. Format Telegram Message
    telegram_message = (
        f"🤖 **استشارة أرتورو AI المجدولة: {name}**\n"
        f"⏰ **الموعد:** `{scheduled_time}` بتوقيت القاهرة {('(تجربة فورية)' if is_test else '')}\n"
        f"📌 **السؤال:** _{prompt}_\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"{reply_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 _تم خصم رسالة واحدة من كوتتك الشهرية | للتحكم وإدارة المواعيد: [egxbots.com/profile](https://egxbots.com/profile)_"
    )

    # 6. Deliver to Telegram
    sent = send_telegram_direct(chat_id, telegram_message)

    # 7. Record in DB (only set last_run_date on real scheduled runs that succeeded)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    status = "success" if sent else "telegram_delivery_failed"
    err = None if sent else "Failed to send message to Telegram"

    update_payload: Dict[str, Any] = {
        "last_run_at": now_iso,
        "last_status": status,
        "last_error": err,
    }
    if not is_test and sent:
        update_payload["last_run_date"] = today_cairo

    _supabase_request(
        f"scheduled_chat_automations?id=eq.{auto_id}",
        method="PATCH",
        payload=update_payload,
    )

    # 8. Log to chat history with valid UUID session
    _log_automation_to_chat_history(
        auto_id,
        user_id,
        name,
        prompt,
        reply_text,
        now_iso,
        latency_ms=auto_latency_ms,
        usage=auto_usage,
        cached=auto_cached,
        cache_key=auto_cache_key,
    )

    return {"ok": sent, "status": status, "chat_id": chat_id, "error": err}


def _was_modified_after_schedule_today(auto: Dict[str, Any], now_cairo: dt.datetime, sh: int, sm: int) -> bool:
    """
    Checks if the automation was newly created or edited TODAY after its scheduled_time.
    Prevents an automation created at 09:00 with default time 08:30 from firing immediately as a false catch-up.
    """
    raw_ts = auto.get("updated_at") or auto.get("created_at")
    if not raw_ts:
        return False
    try:
        mod_dt = dt.datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00")).astimezone(CAIRO_TZ)
        if mod_dt.date() != now_cairo.date():
            return False
        sched_minutes = sh * 60 + sm
        mod_minutes = mod_dt.hour * 60 + mod_dt.minute
        return mod_minutes > sched_minutes + 1
    except Exception:
        return False


def _worker_loop() -> None:
    """Continuous minute-level scheduler loop."""
    logger.info("[AUTOMATIONS_WORKER] Background Scheduler Thread started.")
    time.sleep(5)  # initial brief settle
    sync_automations_cache()

    while not _stop_event.is_set():
        try:
            now_cairo = get_cairo_time()
            current_time_str = now_cairo.strftime("%H:%M")
            today_date_str = now_cairo.strftime("%Y-%m-%d")
            cairo_weekday = now_cairo.weekday()  # Sun=6, Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5

            # Refresh cache periodically
            if time.time() - _last_cache_refresh > _CACHE_TTL_SECONDS:
                sync_automations_cache()

            # Find matching automations
            with _cache_lock:
                automations = list(_cached_automations)

            for auto in automations:
                if not auto.get("is_active"):
                    continue

                # Check if already ran today
                if auto.get("last_run_date") == today_date_str:
                    continue

                # Check days of week against the automation's target market calendar
                days_type = auto.get("days_of_week") or "trading_days"
                if days_type == "trading_days":
                    auto_mkt = _detect_automation_market(auto.get("prompt") or "", auto.get("name") or "")
                    if auto_mkt == "EGX":
                        if cairo_weekday not in {6, 0, 1, 2, 3}:
                            continue
                    else:
                        try:
                            from api.agentic_chat.market_registry import get_market_config, get_market_now
                            mkt_weekdays = set(get_market_config(auto_mkt).trading_weekdays)
                            if get_market_now(auto_mkt).weekday() not in mkt_weekdays:
                                continue
                        except Exception:
                            if cairo_weekday not in {6, 0, 1, 2, 3}:
                                continue

                sched_time = str(auto.get("scheduled_time") or "").strip()
                if sched_time != current_time_str:
                    # Catch-up window: up to 90 minutes if HF Space restarted or woke up after schedule
                    try:
                        sh, sm = map(int, sched_time.split(":"))
                        ch, cm = now_cairo.hour, now_cairo.minute
                        diff_minutes = (ch * 60 + cm) - (sh * 60 + sm)
                        if diff_minutes < 0:
                            diff_minutes += 1440
                        if not (0 <= diff_minutes <= 90):
                            continue
                        if diff_minutes > 1 and _was_modified_after_schedule_today(auto, now_cairo, sh, sm):
                            continue
                    except Exception:
                        continue

                # Run automation in dedicated background thread
                logger.info(f"[AUTOMATIONS_WORKER] Triggering scheduled automation: {auto.get('id')} - {auto.get('name')}")
                # Mark in memory to prevent re-triggering this minute
                auto["last_run_date"] = today_date_str
                threading.Thread(target=execute_single_automation, args=(auto, False), daemon=True).start()

        except Exception as e:
            logger.error(f"[AUTOMATIONS_WORKER] Worker loop error: {e}")

        # Sleep until the next 30-second boundary
        time.sleep(30)


def start_scheduled_automations_worker() -> None:
    """Starts the background worker thread if not already running."""
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="ScheduledAutomationsWorker")
    _worker_thread.start()
    logger.info("[AUTOMATIONS_WORKER] Worker thread spawned.")


def stop_scheduled_automations_worker() -> None:
    """Stops the background worker thread gracefully."""
    _stop_event.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=3)
    logger.info("[AUTOMATIONS_WORKER] Worker thread stopped.")
