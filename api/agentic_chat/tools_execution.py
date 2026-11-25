"""
api/agentic_chat/tools_execution.py
Asynchronous, non-blocking execution of agentic financial tools against Supabase.
All I/O calls are offloaded via asyncio.to_thread to ensure the FastAPI event loop
never blocks.
"""

import asyncio
import contextvars
import json
import math
import os
import re
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import pytz

from api.stock_ai import _init_supabase, supabase
from api.stock_aliases import (
    ARABIC_STOCK_MAPPINGS,
    _normalize_arabic_text,
    resolve_stock_symbol,
)
from api.sharia_stocks import is_sharia_compliant
from api.egx_canonical_names import CANONICAL_EGX_STOCK_NAMES
from api.agentic_chat.intraday_volume import get_exchange_session_state, resolve_intraday_r_vol

try:
    import api.saudi_stock_aliases as _saudi_aliases_mod

    _ext_resolve_saudi_symbol = getattr(_saudi_aliases_mod, "resolve_saudi_symbol", None)
    _EXT_SAUDI_MAPPINGS: Dict[str, str] = (
        getattr(_saudi_aliases_mod, "SAUDI_STOCK_MAPPINGS", None)
        or getattr(_saudi_aliases_mod, "SAUDI_STOCK_ALIASES", None)
        or getattr(_saudi_aliases_mod, "ARABIC_SAUDI_MAPPINGS", None)
        or {}
    )
except ImportError:
    _ext_resolve_saudi_symbol = None
    _EXT_SAUDI_MAPPINGS = {}

CAIRO_TZ = pytz.timezone("Africa/Cairo")
RIYADH_TZ = pytz.timezone("Asia/Riyadh")

_TOOL_CACHE: Dict[str, Dict[str, Any]] = {}
_TOOL_CACHE_LOCK = threading.Lock()
TOOL_CACHE_TTL_SECONDS = 300  # 5 minutes in-memory cache for public market data

_ENV_LOADED = False
_ENV_LOCK = threading.Lock()
_SAUDI_SB_CLIENT = None
_SAUDI_SB_LOCK = threading.Lock()

# Thread/async-safe default UI market tie-breaker for market-agnostic questions
_ACTIVE_MARKET_CTX: contextvars.ContextVar[str] = contextvars.ContextVar(
    "artoro_active_market", default="EGX"
)

# Thread/async-safe Telegram user ID for unlinked private-bot portfolio isolation
_TG_PORTFOLIO_CTX: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "artoro_tg_portfolio_user_id", default=None
)
_TG_PORTFOLIO_LOCKS: Dict[int, threading.Lock] = {}
_TG_PORTFOLIO_META_LOCK = threading.Lock()


def set_telegram_portfolio_context(telegram_user_id: Optional[int]) -> contextvars.Token:
    """Bind the unlinked Telegram user ID so portfolio tools persist to telegram_vip_chat_state.portfolio_state."""
    val = int(telegram_user_id) if telegram_user_id is not None else None
    return _TG_PORTFOLIO_CTX.set(val)


def reset_telegram_portfolio_context(token: contextvars.Token) -> None:
    """Restore previous Telegram portfolio context."""
    _TG_PORTFOLIO_CTX.reset(token)


_ALLOW_RECOMMENDATIONS_CTX: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "artoro_allow_recommendations", default=True
)
_GROUP_PORTFOLIO_BLOCKED_CTX: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "artoro_group_portfolio_blocked", default=False
)


def set_allow_recommendations_context(allow: bool) -> contextvars.Token:
    """Bind whether active recommendation exposure is allowed in the current request."""
    return _ALLOW_RECOMMENDATIONS_CTX.set(bool(allow))


def reset_allow_recommendations_context(token: contextvars.Token) -> None:
    """Restore previous allow_recommendations context."""
    _ALLOW_RECOMMENDATIONS_CTX.reset(token)


def set_group_portfolio_blocked_context(blocked: bool) -> contextvars.Token:
    """Bind whether personal portfolio mutations/reads are blocked because the query came from a group."""
    return _GROUP_PORTFOLIO_BLOCKED_CTX.set(bool(blocked))


def reset_group_portfolio_blocked_context(token: contextvars.Token) -> None:
    """Restore previous group portfolio blocking context."""
    _GROUP_PORTFOLIO_BLOCKED_CTX.reset(token)


def _get_tg_portfolio_lock(telegram_user_id: int) -> threading.Lock:
    with _TG_PORTFOLIO_META_LOCK:
        if len(_TG_PORTFOLIO_LOCKS) > 2000:
            unlocked = [k for k, lk in list(_TG_PORTFOLIO_LOCKS.items()) if not lk.locked()]
            for k in unlocked[:1000]:
                _TG_PORTFOLIO_LOCKS.pop(k, None)
        lk = _TG_PORTFOLIO_LOCKS.get(telegram_user_id)
        if lk is None:
            lk = threading.Lock()
            _TG_PORTFOLIO_LOCKS[telegram_user_id] = lk
        return lk

_TASI_MARKET_TOKENS = {
    "TASI",
    "TADAWUL",
    "SAUDI",
    "SAUDI ARABIA",
    "SAUDI EXCHANGE",
    "KSA",
    "SA",
    "SAR",
    "SR",
    "تاسي",
    "السعوديه",
    "السعودية",
    "تداول",
    "تداول السعوديه",
    "تداول السعودية",
    "السوق السعودي",
}

_SAUDI_TICKER_RE = re.compile(r"^\d{4}$")

_BUILTIN_SAUDI_ALIASES: Dict[str, str] = {
    "أرامكو": "2222",
    "ارامكو": "2222",
    "أرامكوا": "2222",
    "ارامكوا": "2222",
    "أرامكو السعودية": "2222",
    "ارامكو السعودية": "2222",
    "ARAMCO": "2222",
    "SAUDI ARAMCO": "2222",
    "الراجحي": "1120",
    "الراجحى": "1120",
    "الرجحي": "1120",
    "الرجحى": "1120",
    "رجحي": "1120",
    "رجحى": "1120",
    "مصرف الراجحي": "1120",
    "مصرف الرجحي": "1120",
    "ALRAJHI": "1120",
    "RAJHI": "1120",
    "سابك": "2010",
    "سابيك": "2010",
    "SABIC": "2010",
    "الاتصالات السعودية": "7010",
    "اتصالات السعودية": "7010",
    "اس تي سي": "7010",
    "إس تي سي": "7010",
    "STC": "7010",
    "الاهلي السعودي": "1180",
    "الأهلي السعودي": "1180",
    "البنك الاهلي السعودي": "1180",
    "البنك الأهلي السعودي": "1180",
    "SNB": "1180",
    "NCB": "1180",
    "معادن": "1211",
    "معادين": "1211",
    "MAADEN": "1211",
    "اكوا باور": "2082",
    "أكوا باور": "2082",
    "اكواباور": "2082",
    "أكواباور": "2082",
    "ACWA POWER": "2082",
    "ACWA": "2082",
    "سليمان الحبيب": "4013",
    "الحبيب": "4013",
    "دكتور سليمان الحبيب": "4013",
    "SULAIMAN ALHABIB": "4013",
    "ALHABIB": "4013",
    "المراعي": "2280",
    "ALMARAI": "2280",
    "الإنماء": "1150",
    "الانماء": "1150",
    "مصرف الإنماء": "1150",
    "مصرف الانماء": "1150",
    "ALINMA": "1150",
    "بنك الرياض": "1010",
    "الرياض": "1010",
    "بنك الجزيرة": "1020",
    "الجزيرة": "1020",
    "البنك السعودي للاستثمار": "1030",
    "السعودي الفرنسي": "1050",
    "بنك الأول": "1060",
    "الاول": "1060",
    "الأول": "1060",
    "العربي الوطني": "1080",
    "مجموعة تداول": "1111",
    "تداول السعودية": "1111",
    "بنك البلاد": "1140",
    "البلاد": "1140",
    "سابك للمغذيات": "2020",
    "سافكو": "2020",
    "مجموعة صافولا": "2050",
    "صافولا": "2050",
    "التصنيع": "2060",
    "ينساب": "2290",
    "سبكيم": "2310",
    "المتقدمة": "2330",
    "كيان السعودية": "2350",
    "كيان": "2350",
    "بترورابغ": "2380",
    "الحفر العربية": "2381",
    "أديس": "2382",
    "اديس": "2382",
    "اسواق العثيم": "4001",
    "العثيم": "4001",
    "المواساة": "4002",
    "دله الصحية": "4004",
    "البحري": "4030",
    "جرير": "4190",
    "مكتبة جرير": "4190",
    "الدريس": "4200",
    "إعمار": "4220",
    "اعمار المدينة الاقتصادية": "4220",
    "بدجت السعودية": "4260",
    "ذيب": "4261",
    "دار الاركان": "4300",
    "دار الأركان": "4300",
    "سينومي سنترز": "4321",
    "كهرباء السعودية": "5110",
    "الكهرباء السعودية": "5110",
    "موبايلي": "7020",
    "اتحاد اتصالات": "7020",
    "زين السعودية": "7030",
    "سلوشنز": "7202",
    "علم": "7203",
    "شركة علم": "7203",
    "التعاونية": "8010",
    "بوبا العربية": "8210",
    "بوبا": "8210",
    "الخدمات الأرضية": "4031",
    "أمريكانا": "6015",
    "لوسيد": "2083",
}

_BUILTIN_SAUDI_NORM_INDEX: Dict[str, str] = {}
for _k_alias, _v_sym in _BUILTIN_SAUDI_ALIASES.items():
    _BUILTIN_SAUDI_NORM_INDEX[_k_alias.strip().upper()] = _v_sym
    _BUILTIN_SAUDI_NORM_INDEX[_normalize_arabic_text(_k_alias).strip().upper()] = _v_sym

_BUILTIN_SAUDI_COMMON_TICKER_SET = set(_BUILTIN_SAUDI_ALIASES.values())


def set_active_market_context(market: Optional[str]) -> contextvars.Token:
    """Bind the current request's default UI market into contextvars."""
    return _ACTIVE_MARKET_CTX.set(_normalize_market_code(market))


def reset_active_market_context(token: contextvars.Token) -> None:
    """Restore previous active market contextvars token."""
    try:
        _ACTIVE_MARKET_CTX.reset(token)
    except Exception:
        pass


def get_active_market_context() -> str:
    """Return normalized active market code ('EGX' or 'TADAWUL') for current context."""
    return _ACTIVE_MARKET_CTX.get()


from api.agentic_chat.market_registry import (
    currency_for_market as _reg_currency_for_market,
    currency_for_symbol as _reg_currency_for_symbol,
    detect_exchange_from_suffix as _reg_detect_exchange_from_suffix,
    get_market_config as _reg_get_market_config,
    get_supabase_for_exchange as _reg_get_supabase_for_exchange,
    normalize_exchange_code as _reg_normalize_exchange_code,
    ui_market_label as _reg_ui_market_label,
)


def _normalize_market_code(market: Optional[str]) -> str:
    """Normalize arbitrary market/country label to its canonical DB exchange code (EGX, TADAWUL, QSE, DFM, ADX, ...)."""
    if not market:
        return "EGX"
    raw = str(market).strip()
    if not raw:
        return "EGX"
    upper_clean = re.sub(r"[()\[\]{}._/-]+", " ", raw).strip().upper()
    ar_clean = re.sub(r"[()\[\]{}._/-]+", " ", _normalize_arabic_text(raw)).strip().upper()
    if upper_clean in _TASI_MARKET_TOKENS or ar_clean in _TASI_MARKET_TOKENS:
        return "TADAWUL"
    return _reg_normalize_exchange_code(ar_clean or upper_clean)


def _ui_market_label(market_code: Optional[str]) -> str:
    return _reg_ui_market_label(_normalize_market_code(market_code))


def _currency_for_market(market_code: Optional[str]) -> str:
    return _reg_currency_for_market(_normalize_market_code(market_code))


def _ensure_env_loaded() -> None:
    """Load local .env files once when running outside pytest test isolation."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
        return
    with _ENV_LOCK:
        if _ENV_LOADED:
            return
        try:
            from dotenv import load_dotenv

            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            for candidate in (
                os.path.join(repo_root, ".env"),
                os.path.join(repo_root, "web", ".env.local"),
            ):
                if os.path.isfile(candidate):
                    load_dotenv(candidate, override=False)
        except Exception:
            pass
        _ENV_LOADED = True


def _get_tool_cached(cache_key: str) -> Optional[Any]:
    with _TOOL_CACHE_LOCK:
        entry = _TOOL_CACHE.get(cache_key)
        if entry and (time.time() - entry["ts"]) < TOOL_CACHE_TTL_SECONDS:
            return entry["val"]
        _TOOL_CACHE.pop(cache_key, None)
        return None


def _set_tool_cached(cache_key: str, val: Any) -> None:
    with _TOOL_CACHE_LOCK:
        if len(_TOOL_CACHE) > 500:
            oldest = min(_TOOL_CACHE.keys(), key=lambda k: _TOOL_CACHE[k]["ts"])
            _TOOL_CACHE.pop(oldest, None)
        _TOOL_CACHE[cache_key] = {"val": val, "ts": time.time()}


def _get_sb():
    """Ensure Primary (EGX + Auth/Portfolio) Supabase client is initialized and return it."""
    _init_supabase()
    return supabase


def _get_saudi_sb():
    """Return thread-safe singleton Supabase client for Saudi Exchange (Tadawul / TASI)."""
    global _SAUDI_SB_CLIENT
    if _SAUDI_SB_CLIENT is not None:
        return _SAUDI_SB_CLIENT
    _ensure_env_loaded()
    with _SAUDI_SB_LOCK:
        if _SAUDI_SB_CLIENT is not None:
            return _SAUDI_SB_CLIENT
        url = (
            os.getenv("SAUDI_SUPABASE_URL")
            or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_URL")
            or ""
        ).strip()
        key = (
            os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SAUDI_SUPABASE_ANON_KEY")
            or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_ANON_KEY")
            or ""
        ).strip()
        if not url or not key:
            return None
        try:
            from supabase import ClientOptions, create_client

            options = ClientOptions(
                postgrest_client_timeout=15,
                storage_client_timeout=15,
            )
            _SAUDI_SB_CLIENT = create_client(url, key, options=options)
        except TypeError:
            try:
                from supabase import create_client

                _SAUDI_SB_CLIENT = create_client(url, key)
            except Exception:
                return None
        except Exception:
            return None
        return _SAUDI_SB_CLIENT


def _get_sb_for_market(market: Optional[str] = "EGX"):
    """Route any exchange to its dedicated Supabase (if configured), shared SAUDI_SUPABASE (GCC/Metals), or Primary Supabase."""
    exch = _normalize_market_code(market)
    if exch == "TADAWUL":
        return _get_saudi_sb()
    cfg = _reg_get_market_config(exch)
    if exch != "EGX" and cfg.supabase_env_prefix == "SAUDI":
        # Check optional exchange-specific DB override (e.g. QSE_SUPABASE_URL) first, then reuse singleton _get_saudi_sb()
        from api.agentic_chat.market_registry import get_dedicated_supabase_client
        exch_override = get_dedicated_supabase_client(exch)
        if exch_override is not None:
            return exch_override
        sa_sb = _get_saudi_sb()
        if sa_sb is not None:
            return sa_sb
        return _get_sb()
    return _reg_get_supabase_for_exchange(exch, _get_sb)


def _market_unconfigured_error(market: Optional[str] = "TADAWUL", extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = _reg_get_market_config(market)
    payload: Dict[str, Any] = {
        "status": "error",
        "market": cfg.ui_code,
        "exchange": cfg.exchange,
        "currency": cfg.currency_ar or cfg.currency_code,
        "message": f"قاعدة بيانات {cfg.name_ar} ({cfg.ui_code}) غير مهيأة أو غير متاحة حالياً.",
    }
    if extra:
        payload.update(extra)
    return payload


def _saudi_unconfigured_error(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _market_unconfigured_error("TADAWUL", extra=extra)


_DATE_STR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_DB_SYMBOL_CACHE: Dict[str, Optional[str]] = {}


def _resolve_saudi_alias_local(raw: str) -> Optional[str]:
    """Resolve Saudi ticker or Arabic/English company name using track-1 module or built-in map."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    upper_s = s.upper()
    for suffix in (".TADAWUL", ".SR", ".SA"):
        if upper_s.endswith(suffix):
            s = s[: -len(suffix)].strip()
            upper_s = s.upper()
            break
    if _ext_resolve_saudi_symbol is not None:
        try:
            ext_res = _ext_resolve_saudi_symbol(s)
            if ext_res:
                return str(ext_res).strip().upper()
        except Exception:
            pass
    if upper_s in {"TASI", "^TASI", "تاسي"}:
        return "TASI"
    if _SAUDI_TICKER_RE.fullmatch(upper_s):
        return upper_s
    norm_upper = _normalize_arabic_text(s).strip().upper()
    if upper_s in _BUILTIN_SAUDI_NORM_INDEX:
        return _BUILTIN_SAUDI_NORM_INDEX[upper_s]
    if norm_upper in _BUILTIN_SAUDI_NORM_INDEX:
        return _BUILTIN_SAUDI_NORM_INDEX[norm_upper]
    for k_map, v_map in _EXT_SAUDI_MAPPINGS.items():
        if _normalize_arabic_text(str(k_map)).strip().upper() == norm_upper:
            return str(v_map).strip().upper()
    return None


def _lookup_symbol_in_db(raw_text: str, market: str = "EGX") -> Optional[str]:
    """Lookup exact ticker (non-EGX) or company name against Supabase `stocks` for a given exchange."""
    clean_q = " ".join(str(raw_text or "").strip().split())
    if len(clean_q) < 2:
        return None
    norm_mkt = _normalize_market_code(market)
    cache_k = f"{norm_mkt}:{clean_q.lower()}"
    if cache_k in _DB_SYMBOL_CACHE:
        return _DB_SYMBOL_CACHE[cache_k]
    is_ascii_ticker = bool(re.fullmatch(r"[A-Za-z0-9]{2,12}", clean_q))
    # For EGX, skip obvious single-token tickers (already handled as clean symbols)
    if norm_mkt == "EGX" and (re.fullmatch(r"[A-Za-z]{2,8}", clean_q) or _SAUDI_TICKER_RE.fullmatch(clean_q)):
        return None
    found: Optional[str] = None
    try:
        sb = _get_sb_for_market(norm_mkt)
        if sb is None:
            return None
        if norm_mkt != "EGX" and is_ascii_ticker:
            res_exact = (
                sb.from_("stocks")
                .select("symbol")
                .eq("exchange", norm_mkt)
                .eq("symbol", clean_q.upper())
                .limit(1)
                .execute()
            )
            exact_rows = [r for r in (res_exact.data or []) if isinstance(r, dict) and r.get("symbol")]
            if exact_rows:
                found = str(exact_rows[0]["symbol"]).upper().strip()
        if found is None and len(clean_q) >= 3:
            safe_q = clean_q.replace("%", "").replace(",", " ").strip()
            res = (
                sb.from_("stocks")
                .select("symbol,name,name_ar")
                .eq("exchange", norm_mkt)
                .or_(f"name_ar.ilike.%{safe_q}%,name.ilike.%{safe_q}%")
                .limit(3)
                .execute()
            )
            rows = [r for r in (res.data or []) if isinstance(r, dict) and r.get("symbol")]
            if rows:
                found = str(rows[0]["symbol"]).upper().strip()
            elif " " in safe_q:
                # Try matching longest meaningful word when full Arabic phrase differs slightly
                words = sorted([w for w in safe_q.split() if len(w) >= 4], key=len, reverse=True)
                for word in words[:2]:
                    res_w = (
                        sb.from_("stocks")
                        .select("symbol")
                        .eq("exchange", norm_mkt)
                        .or_(f"name_ar.ilike.%{word}%,name.ilike.%{word}%")
                        .limit(3)
                        .execute()
                    )
                    w_rows = [r for r in (res_w.data or []) if isinstance(r, dict) and r.get("symbol")]
                    if len(w_rows) == 1:
                        found = str(w_rows[0]["symbol"]).upper().strip()
                        break
        if found is None and norm_mkt != "EGX" and any(ord(ch) > 127 for ch in clean_q):
            cands = _search_catalog_candidates(clean_q, exchange=norm_mkt, limit=1, min_score=3.5)
            if cands:
                found = str(cands[0]["symbol"]).upper().strip()
    except Exception:
        pass
    if len(_DB_SYMBOL_CACHE) < 300:
        _DB_SYMBOL_CACHE[cache_k] = found
    return found


_METALS_ALIAS_MAP: Dict[str, Tuple[str, str]] = {
    "XAUUSD": ("XAUUSD", "COMMODITIES"),
    "XAU": ("XAUUSD", "COMMODITIES"),
    "GC=F": ("XAUUSD", "COMMODITIES"),
    "GOLD": ("XAUUSD", "COMMODITIES"),
    "الذهب": ("XAUUSD", "COMMODITIES"),
    "الدهب": ("XAUUSD", "COMMODITIES"),
    "اونصة الذهب": ("XAUUSD", "COMMODITIES"),
    "أونصة الذهب": ("XAUUSD", "COMMODITIES"),
    "سعر الذهب": ("XAUUSD", "COMMODITIES"),
    "XAGUSD": ("XAGUSD", "COMMODITIES"),
    "XAG": ("XAGUSD", "COMMODITIES"),
    "SI=F": ("XAGUSD", "COMMODITIES"),
    "SILVER": ("XAGUSD", "COMMODITIES"),
    "الفضة": ("XAGUSD", "COMMODITIES"),
    "الفضه": ("XAGUSD", "COMMODITIES"),
    "اونصة الفضة": ("XAGUSD", "COMMODITIES"),
    "أونصة الفضة": ("XAGUSD", "COMMODITIES"),
    "سعر الفضة": ("XAGUSD", "COMMODITIES"),
}
_GCC_EXCHANGES_IN_SAUDI_DB = ("DFM", "ADX", "QSE", "COMMODITIES")
_GCC_SYMBOL_CACHE: Dict[str, Optional[Tuple[str, str]]] = {}


def _lookup_symbol_in_gcc_and_metals(raw_text: str) -> Optional[Tuple[str, str]]:
    """Lookup ticker or Arabic/English company name across DFM, ADX, QSE, COMMODITIES in SAUDI_SUPABASE."""
    clean_q = " ".join(str(raw_text or "").strip().split())
    if len(clean_q) < 2:
        return None
    cache_k = clean_q.lower()
    if cache_k in _GCC_SYMBOL_CACHE:
        return _GCC_SYMBOL_CACHE[cache_k]
    found: Optional[Tuple[str, str]] = None
    try:
        sb_sa = _get_saudi_sb()
        if sb_sa is not None:
            up = clean_q.upper()
            if re.fullmatch(r"[A-Z0-9]{2,12}", up):
                res = (
                    sb_sa.from_("stocks")
                    .select("symbol,exchange")
                    .in_("exchange", list(_GCC_EXCHANGES_IN_SAUDI_DB))
                    .eq("symbol", up)
                    .limit(1)
                    .execute()
                )
                rows = [r for r in (res.data or []) if isinstance(r, dict) and r.get("symbol")]
                if rows:
                    found = (str(rows[0]["symbol"]).upper().strip(), str(rows[0]["exchange"]).upper().strip())
            if found is None and len(clean_q) >= 3:
                safe_q = clean_q.replace("%", "").replace(",", " ").strip()
                res = (
                    sb_sa.from_("stocks")
                    .select("symbol,exchange")
                    .in_("exchange", list(_GCC_EXCHANGES_IN_SAUDI_DB))
                    .or_(f"name_ar.ilike.%{safe_q}%,name.ilike.%{safe_q}%")
                    .limit(2)
                    .execute()
                )
                rows = [r for r in (res.data or []) if isinstance(r, dict) and r.get("symbol")]
                if rows:
                    found = (str(rows[0]["symbol"]).upper().strip(), str(rows[0]["exchange"]).upper().strip())
    except Exception:
        pass
    if len(_GCC_SYMBOL_CACHE) < 300:
        _GCC_SYMBOL_CACHE[cache_k] = found
    return found


def _resolve_symbol_and_market(sym: Any, explicit_market: Optional[str] = None) -> Tuple[str, str]:
    """Resolve raw ticker or Arabic/English name to (normalized_symbol, exchange_code)."""
    if not sym:
        return ("", "EGX")
    raw = str(sym).strip()
    if not raw:
        return ("", "EGX")
    clean = raw.upper()

    # 0. Gold & Silver / Commodities aliases
    if clean in _METALS_ALIAS_MAP:
        return _METALS_ALIAS_MAP[clean]
    if raw in _METALS_ALIAS_MAP:
        return _METALS_ALIAS_MAP[raw]

    # 1. Explicit exchange suffixes take top priority (.CA, .SR, .SA, .TADAWUL, .QA, .QE, .DU, .AD, .AE, ...)
    suf_match = _reg_detect_exchange_from_suffix(raw)
    if suf_match:
        core_sym, exch = suf_match
        if exch == "EGX":
            resolved = resolve_stock_symbol(core_sym) or _lookup_symbol_in_db(core_sym, market="EGX")
            return (resolved or core_sym, "EGX")
        if exch == "TADAWUL":
            saudi_hit = _resolve_saudi_alias_local(core_sym) or _lookup_symbol_in_db(core_sym, market="TADAWUL")
            return (saudi_hit or core_sym, "TADAWUL")
        db_hit = _lookup_symbol_in_db(core_sym, market=exch)
        return (db_hit or core_sym, exch)

    # 1b. When caller explicitly specifies a non-EGX market parameter (e.g. get_stock(symbols=["ADIB"], market="ADX")),
    # resolve within that exchange first and do NOT fall back to EGX aliases/tickers for clean ticker symbols.
    if explicit_market:
        exp_mkt = _normalize_market_code(explicit_market)
        if exp_mkt != "EGX":
            if exp_mkt == "TADAWUL":
                saudi_hit = _resolve_saudi_alias_local(raw) or _lookup_symbol_in_db(raw, market="TADAWUL")
                if saudi_hit:
                    return (saudi_hit, "TADAWUL")
            exp_db = _lookup_symbol_in_db(raw, market=exp_mkt)
            if exp_db:
                return (exp_db, exp_mkt)
            if re.fullmatch(r"[A-Za-z0-9]{2,12}", clean):
                return (clean, exp_mkt)

    # 2. Active non-EGX market DB lookup takes priority before EGX static aliases
    active_mkt = get_active_market_context()
    if active_mkt != "EGX":
        active_db = _lookup_symbol_in_db(raw, market=active_mkt)
        if active_db:
            return (active_db, active_mkt)
        if active_mkt in _GCC_EXCHANGES_IN_SAUDI_DB:
            gcc_act = _lookup_symbol_in_gcc_and_metals(raw)
            if gcc_act:
                return gcc_act

    # 3. Direct Saudi static alias or 4-digit Tadawul numeric ticker, and GCC/Metals exact DB lookup
    _egx_known_tickers = set(ARABIC_STOCK_MAPPINGS.values())
    gcc_exact = _lookup_symbol_in_gcc_and_metals(raw)
    if gcc_exact and (len(raw) >= 5 or clean == gcc_exact[0]):
        if clean not in _egx_known_tickers or active_mkt in _GCC_EXCHANGES_IN_SAUDI_DB:
            return gcc_exact

    saudi_hit = _resolve_saudi_alias_local(raw)
    if saudi_hit:
        return (saudi_hit, "TADAWUL")

    # 4. Exact EGX ticker in ARABIC_STOCK_MAPPINGS before fuzzy EGX resolution
    if clean in _egx_known_tickers:
        return (clean, "EGX")

    if gcc_exact:
        return gcc_exact

    # 5. EGX alias resolution ONLY for non-ASCII (Arabic) names or exact keys in ARABIC_STOCK_MAPPINGS
    # (NEVER let resolve_stock_symbol's blind len>=3 ASCII fallback or substring match mangle GCC/future tickers like QNBK/AIRARABIA/EMAAR!)
    has_non_ascii = any(ord(ch) > 127 for ch in raw)
    if has_non_ascii or clean in ARABIC_STOCK_MAPPINGS or raw in ARABIC_STOCK_MAPPINGS:
        resolved_egx = resolve_stock_symbol(raw) if has_non_ascii else (ARABIC_STOCK_MAPPINGS.get(clean) or ARABIC_STOCK_MAPPINGS.get(raw))
        if resolved_egx:
            return (resolved_egx, "EGX")

    # 6. DB company-name / ticker fallback (prioritize active market context when un-suffixed)
    if active_mkt != "EGX":
        egx_db = _lookup_symbol_in_db(raw, market="EGX")
        if egx_db:
            return (egx_db, "EGX")
        return (clean, active_mkt)
    else:
        egx_db = _lookup_symbol_in_db(raw, market="EGX")
        if egx_db:
            return (egx_db, "EGX")
        saudi_db = _lookup_symbol_in_db(raw, market="TADAWUL")
        if saudi_db:
            return (saudi_db, "TADAWUL")

    return (clean, "EGX")


def _normalize_symbol(sym: Any) -> str:
    """Normalize stock symbol across EGX & Tadawul, preserving backward-compatible return value."""
    resolved, _ = _resolve_symbol_and_market(sym)
    return resolved


def _safe_float(val: Any, decimals: int = 2) -> Optional[float]:
    """Safely cast value to float with bounded precision."""
    try:
        if val is None or val == "":
            return None
        f = float(val)
        if f != f:  # NaN check
            return None
        return round(f, decimals)
    except Exception:
        return None


def _price_decimals(val: float) -> int:
    """Use 4 decimals under 2 EGP (penny stocks like PHGC), 3 under 10 EGP, 2 otherwise."""
    mag = abs(val)
    if mag < 2.0:
        return 4
    if mag < 10.0:
        return 3
    return 2


def _safe_price(val: Any) -> Optional[float]:
    """Cast a price/level value preserving dynamic EGX tick precision."""
    try:
        if val is None or val == "":
            return None
        f = float(val)
        if f != f:
            return None
        return round(f, _price_decimals(f))
    except Exception:
        return None


def _get_latest_table_date(
    sb: Any,
    table: str,
    date_col: str = "date",
    exchange: Optional[str] = "EGX",
) -> Optional[str]:
    """Fetch the latest YYYY-MM-DD trading date present in a Supabase market table."""
    cache_key = f"latest_date:{table}:{date_col}:{exchange}"
    cached = _get_tool_cached(cache_key)
    if cached is not None:
        return cached
    try:
        q = sb.from_(table).select(date_col)
        if exchange:
            q = q.eq("exchange", exchange)
        res = q.order(date_col, desc=True).limit(1).execute()
        rows = res.data or []
        if rows and isinstance(rows[0], dict):
            d = rows[0].get(date_col)
            if isinstance(d, str) and _DATE_STR_RE.match(d):
                _set_tool_cached(cache_key, d)
                return d
    except Exception:
        pass
    return None


def _alias_name_for_symbol(sym: str, market: Optional[str] = None) -> Optional[str]:
    eff_mkt = _normalize_market_code(market) if market else (
        "TADAWUL" if _SAUDI_TICKER_RE.fullmatch(str(sym or "").strip()) else "EGX"
    )
    if eff_mkt == "TADAWUL":
        # Prefer Arabic names first
        for src in (_BUILTIN_SAUDI_ALIASES, _EXT_SAUDI_MAPPINGS):
            for name_k, mapped_sym in src.items():
                if str(mapped_sym).upper() == str(sym).upper() and re.search(r"[\u0600-\u06FF]", str(name_k)):
                    return str(name_k)
        for src in (_BUILTIN_SAUDI_ALIASES, _EXT_SAUDI_MAPPINGS):
            for name_k, mapped_sym in src.items():
                if str(mapped_sym).upper() == str(sym).upper():
                    return str(name_k)
        return None
    for ar_name, mapped_sym in ARABIC_STOCK_MAPPINGS.items():
        if mapped_sym == sym:
            return ar_name
    return None


def _resolve_effective_market(
    market: Optional[str] = None,
    symbols: Optional[List[str]] = None,
) -> str:
    """Resolve tool execution market: explicit param > symbol exchange > active UI ContextVar."""
    if market and str(market).strip():
        return _normalize_market_code(market)
    if symbols:
        resolved_mkts = []
        for s in symbols:
            if s and str(s).strip():
                _, m = _resolve_symbol_and_market(s)
                resolved_mkts.append(m)
        non_egx = [m for m in resolved_mkts if m != "EGX"]
        if non_egx:
            return non_egx[0]
        if resolved_mkts:
            return "EGX"
    return get_active_market_context()


def _group_symbols_by_exchange(
    symbols: Optional[List[str]],
    market: Optional[str] = None,
) -> Dict[str, List[str]]:
    """Resolve and group symbols by canonical exchange code (EGX, TADAWUL, QSE, DFM, ADX, ...)."""
    grouped: Dict[str, List[str]] = {}
    seen_per_exch: Dict[str, set] = {}
    tok = set_active_market_context(market) if market else None
    try:
        for raw in symbols or []:
            if not raw:
                continue
            sym, mkt = _resolve_symbol_and_market(raw, explicit_market=market)
            if not sym:
                continue
            exch = _normalize_market_code(mkt)
            seen = seen_per_exch.setdefault(exch, set())
            if sym not in seen and len(seen) < 25:
                seen.add(sym)
                grouped.setdefault(exch, []).append(sym)
    finally:
        if tok is not None:
            reset_active_market_context(tok)
    return grouped


def _split_symbols_by_market(symbols: Optional[List[str]]) -> Tuple[List[str], List[str]]:
    """Backward-compatible wrapper returning (egx_symbols, tasi_symbols)."""
    grouped = _group_symbols_by_exchange(symbols)
    return (grouped.get("EGX", []), grouped.get("TADAWUL", []))


def _is_real_saudi_sb(sb: Any) -> bool:
    """True only when operating on a live (non-mock) Supabase client instance."""
    if sb is None:
        return False
    if _SAUDI_SB_CLIENT is not None and sb is _SAUDI_SB_CLIENT:
        return True
    if supabase is not None and sb is supabase:
        return True
    url = getattr(sb, "supabase_url", None)
    key = getattr(sb, "supabase_key", None)
    return isinstance(url, str) and url.startswith(("http://", "https://")) and isinstance(key, str) and bool(key)


def _extract_sb_url_and_key(sb: Any) -> Tuple[str, str]:
    """Extract (url, key) from any live Supabase client (Primary, Saudi, or future dedicated DB)."""
    url = getattr(sb, "supabase_url", None)
    key = getattr(sb, "supabase_key", None)
    if isinstance(url, str) and url.startswith(("http://", "https://")) and isinstance(key, str) and key:
        return (url.strip().rstrip("/"), key.strip())
    _ensure_env_loaded()
    if _SAUDI_SB_CLIENT is not None and sb is _SAUDI_SB_CLIENT:
        sa_url = (os.getenv("SAUDI_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_URL") or "").strip().rstrip("/")
        sa_key = (
            os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SAUDI_SUPABASE_ANON_KEY")
            or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_ANON_KEY")
            or ""
        ).strip()
        return (sa_url, sa_key)
    if supabase is not None and sb is supabase:
        p_url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").strip().rstrip("/")
        p_key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_KEY")
            or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
            or ""
        ).strip()
        return (p_url, p_key)
    return ("", "")


def _get_saudi_openapi_schema(sb: Any) -> Dict[str, set]:
    """Fetch and cache PostgREST OpenAPI table->columns map for any live Supabase client."""
    if not _is_real_saudi_sb(sb):
        return {}
    url, key = _extract_sb_url_and_key(sb)
    if not url or not key:
        return {}
    cache_key = f"openapi_cols:{url}"
    cached = _get_tool_cached(cache_key)
    if isinstance(cached, dict):
        return cached
    try:
        req = urllib.request.Request(
            f"{url}/rest/v1/",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Accept": "application/openapi+json",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            spec = json.loads(resp.read().decode("utf-8"))
        defs = spec.get("definitions") or {}
        table_cols: Dict[str, set] = {}
        for tbl_name, tbl_def in defs.items():
            props = tbl_def.get("properties") if isinstance(tbl_def, dict) else None
            if isinstance(props, dict):
                table_cols[tbl_name] = set(props.keys())
        if table_cols:
            _set_tool_cached(cache_key, table_cols)
        return table_cols
    except Exception:
        return {}


def _get_saudi_table_columns(table_name: str, sb: Any) -> Optional[set]:
    """Return actual column set for a table on any live Supabase client if inspectable, else None."""
    schema = _get_saudi_openapi_schema(sb)
    if table_name in schema:
        return schema[table_name]
    return None


_SAUDI_TI_DESIRED_COLS = [
    "symbol",
    "date",
    "updated_at",
    "close",
    "change_pct",
    "volume",
    "vol_sma20",
    "volume_sma_20",
    "r_vol",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bb_upper",
    "bb_lower",
    "ema_20",
    "ema_50",
    "ema_200",
    "vwap_20",
    "momentum_10",
    "cmf_20",
    "atr_14",
    "adx_14",
    "king_ai_score",
]

_SAUDI_TI_BASE_SAFE_COLS = {
    "symbol",
    "updated_at",
    "close",
    "change_pct",
    "volume",
    "volume_sma_20",
    "rsi_14",
    "ema_50",
    "ema_200",
    "vwap_20",
    "momentum_10",
    "atr_14",
    "adx_14",
    "cmf_20",
}

_PRIMARY_TI_BASE_SAFE_COLS = {
    "symbol",
    "date",
    "close",
    "change_pct",
    "volume",
    "vol_sma20",
    "r_vol",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bb_upper",
    "bb_lower",
    "ema_20",
    "ema_50",
    "ema_200",
    "vwap_20",
    "cmf_20",
    "king_ai_score",
}


def _saudi_ti_select_and_order(sb: Any) -> Tuple[str, str]:
    """Build schema-safe SELECT projection and order column for stock_technical_indicators."""
    cols = _get_saudi_table_columns("stock_technical_indicators", sb)
    if cols:
        chosen = [c for c in _SAUDI_TI_DESIRED_COLS if c in cols]
        order_col = "date" if "date" in cols else ("updated_at" if "updated_at" in cols else "symbol")
        if chosen:
            return (",".join(chosen), order_col)
    if supabase is not None and sb is supabase:
        chosen = [c for c in _SAUDI_TI_DESIRED_COLS if c in _PRIMARY_TI_BASE_SAFE_COLS]
        return (",".join(chosen), "date")
    chosen = [c for c in _SAUDI_TI_DESIRED_COLS if c in _SAUDI_TI_BASE_SAFE_COLS]
    return (",".join(chosen), "updated_at")


def _ema_series(values: List[float], period: int) -> Optional[float]:
    if not values or len(values) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1.0 - k)
    return ema


def _ema_full_series(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    k = 2.0 / (period + 1)
    ema = values[0]
    out = [ema]
    for v in values[1:]:
        ema = v * k + ema * (1.0 - k)
        out.append(ema)
    return out


def _rsi_wilder(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_indicators_from_price_rows(rows_desc: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute technical indicators & S/R levels from OHLCV bars (ordered newest first)."""
    valid = [
        r for r in (rows_desc or [])
        if isinstance(r, dict) and r.get("close") is not None and float(r.get("close") or 0) > 0
    ]
    if not valid:
        return {}
    asc = sorted(valid, key=lambda r: str(r.get("date") or ""))
    closes = [float(r["close"]) for r in asc]
    highs = [float(r.get("high") or r["close"]) for r in asc]
    lows = [float(r.get("low") or r["close"]) for r in asc]
    vols = [float(r.get("volume") or 0.0) for r in asc]

    latest = asc[-1]
    close_val = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else None
    change_pct = ((close_val - prev_close) / prev_close * 100.0) if prev_close else None

    vol_latest = vols[-1]
    vol_window = vols[-20:] if len(vols) >= 5 else vols
    nonzero_vols = [v for v in vol_window if v > 0]
    vol_sma20 = (sum(nonzero_vols) / len(nonzero_vols)) if nonzero_vols else None
    r_vol = (vol_latest / vol_sma20) if (vol_sma20 and vol_sma20 > 0) else None

    rsi_14 = _rsi_wilder(closes, 14)
    ema_20 = _ema_series(closes, 20)
    ema_50 = _ema_series(closes, 50)
    ema_200 = _ema_series(closes, 200)

    macd_val = macd_sig = macd_hist = None
    if len(closes) >= 26:
        e12 = _ema_full_series(closes, 12)
        e26 = _ema_full_series(closes, 26)
        macd_line = [a - b for a, b in zip(e12, e26)]
        sig_line = _ema_full_series(macd_line, 9)
        macd_val = macd_line[-1]
        macd_sig = sig_line[-1]
        macd_hist = macd_val - macd_sig

    bb_up = bb_low = None
    if len(closes) >= 20:
        w20 = closes[-20:]
        sma20 = sum(w20) / 20.0
        var20 = sum((x - sma20) ** 2 for x in w20) / 20.0
        std20 = math.sqrt(var20)
        bb_up = sma20 + 2.0 * std20
        bb_low = sma20 - 2.0 * std20

    vwap_20 = None
    recent_20_bars = asc[-20:]
    tv_sum = 0.0
    v_sum = 0.0
    for b in recent_20_bars:
        v = float(b.get("volume") or 0.0)
        if v > 0:
            tp = (float(b.get("high") or b["close"]) + float(b.get("low") or b["close"]) + float(b["close"])) / 3.0
            tv_sum += tp * v
            v_sum += v
    if v_sum > 0:
        vwap_20 = tv_sum / v_sum

    cmf_20 = None
    mf_vol_sum = 0.0
    cmf_v_sum = 0.0
    for b in recent_20_bars:
        v = float(b.get("volume") or 0.0)
        hi = float(b.get("high") or b["close"])
        lo = float(b.get("low") or b["close"])
        cl = float(b["close"])
        if v > 0 and hi > lo:
            mfm = ((cl - lo) - (hi - cl)) / (hi - lo)
            mf_vol_sum += mfm * v
            cmf_v_sum += v
    if cmf_v_sum > 0:
        cmf_20 = mf_vol_sum / cmf_v_sum

    mom_10 = ((close_val / closes[-11] - 1.0) * 100.0) if len(closes) >= 11 and closes[-11] > 0 else None

    recent_20_lows = [lo for lo in lows[-20:] if lo > 0]
    recent_20_highs = [hi for hi in highs[-20:] if hi > 0]
    all_60_lows = [lo for lo in lows[-60:] if lo > 0]
    all_60_highs = [hi for hi in highs[-60:] if hi > 0]

    s1 = _safe_price(min(recent_20_lows)) if recent_20_lows else _safe_price(close_val * 0.96)
    r1 = _safe_price(max(recent_20_highs)) if recent_20_highs else _safe_price(close_val * 1.05)
    s2 = _safe_price(min(all_60_lows)) if all_60_lows else (_safe_price(s1 * 0.96) if s1 else None)
    r2 = _safe_price(max(all_60_highs)) if all_60_highs else (_safe_price(r1 * 1.05) if r1 else None)

    # Heuristic technical score (0-100) from verified price/indicator series
    score = 50.0
    if ema_50 and close_val > ema_50:
        score += 12.0
    elif ema_50 and close_val < ema_50:
        score -= 10.0
    if ema_200 and close_val > ema_200:
        score += 10.0
    if rsi_14 is not None:
        if 45.0 <= rsi_14 <= 66.0:
            score += 12.0
        elif rsi_14 < 35.0:
            score += 6.0
        elif rsi_14 > 75.0:
            score -= 12.0
    if cmf_20 is not None:
        score += 10.0 if cmf_20 > 0.05 else (-8.0 if cmf_20 < -0.05 else 0.0)
    if r_vol is not None and r_vol >= 1.2 and (change_pct or 0) > 0:
        score += 6.0
    king_score = round(max(5.0, min(95.0, score)), 1)

    return {
        "date": latest.get("date"),
        "close": _safe_price(close_val),
        "change_pct": _safe_float(change_pct, 2),
        "volume": int(round(vol_latest)) if vol_latest else 0,
        "vol_sma20": round(vol_sma20, 0) if vol_sma20 else None,
        "r_vol": _safe_float(r_vol, 2),
        "rsi_14": _safe_float(rsi_14, 2),
        "ema_20": _safe_price(ema_20),
        "ema_50": _safe_price(ema_50),
        "ema_200": _safe_price(ema_200),
        "macd": _safe_float(macd_val, 4),
        "macd_signal": _safe_float(macd_sig, 4),
        "macd_histogram": _safe_float(macd_hist, 4),
        "bb_upper": _safe_price(bb_up),
        "bb_lower": _safe_price(bb_low),
        "vwap_20": _safe_price(vwap_20),
        "momentum_10": _safe_float(mom_10, 2),
        "cmf_20": _safe_float(cmf_20, 3),
        "support_1": s1,
        "resistance_1": r1,
        "support_2": s2,
        "resistance_2": r2,
        "stop_loss": _safe_price(s1 * 0.98) if s1 else None,
        "entry_zone": f"{s1} – {_safe_price(s1 * 1.02)}" if s1 else "غير محدد",
        "king_ai_score": king_score,
        "source": "computed_from_ohlcv",
    }


_SAUDI_STORAGE_EXCHANGES = frozenset({"TADAWUL", "DFM", "ADX", "QSE", "COMMODITIES"})


def _backfill_saudi_ohlcv_from_storage(
    sb: Any,
    exchange: str,
    by_sym: Dict[str, List[Dict[str, Any]]],
    syms: List[str],
    limit_per_sym: int,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Hybrid Storage + Postgres merge for Saudi/GCC/Commodities chatbot reads.
    Only fetches from SAUDI_SUPABASE Storage (`market-history`) when:
      - caller requests >220 bars (multi-year history beyond rolling Postgres tail), OR
      - a symbol returned fewer than `min(limit_per_sym, 60)` rows in Postgres
        (e.g. suspended, thinly traded, or newly archived stock).
    Returns newest-first descending rows per symbol (matching `stock_prices` order).
    """
    ex = str(exchange or "").strip().upper()
    if ex == "TASI":
        ex = "TADAWUL"
    if sb is None or ex not in _SAUDI_STORAGE_EXCHANGES or not syms:
        return by_sym

    need_storage_syms: List[str] = []
    min_ok = min(max(int(limit_per_sym or 60), 1), 60)
    force_storage = int(limit_per_sym or 0) > 220
    for s in syms:
        s_u = str(s or "").strip().upper()
        if not s_u:
            continue
        existing = by_sym.get(s_u) or by_sym.get(s) or []
        if force_storage or len(existing) < min_ok:
            need_storage_syms.append(s_u)

    if not need_storage_syms:
        return by_sym

    try:
        from api.saudi_storage_history import (
            load_storage_symbol_bars,
            merge_bars_storage_with_live,
        )
    except Exception:
        return by_sym

    cap = max(1, min(int(limit_per_sym or 120), 5000))
    for s_u in need_storage_syms[:6]:
        try:
            st_bars = load_storage_symbol_bars(sb, ex, s_u)
            if not st_bars:
                continue
            live_rows = list(reversed(by_sym.get(s_u) or []))
            merged_asc = merge_bars_storage_with_live(st_bars, live_rows)
            if merged_asc:
                # Attach symbol and return newest-first descending
                desc_rows = [
                    {**bar, "symbol": s_u}
                    for bar in reversed(merged_asc[-cap:])
                ]
                by_sym[s_u] = desc_rows
        except Exception:
            continue
    return by_sym


def _fetch_saudi_ohlcv_for_symbols(
    sb: Any, syms: List[str], limit_per_sym: int = 120, exchange: str = "TADAWUL"
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch bounded OHLCV bars from `stock_prices` (+ Storage backfill when needed) grouped newest-first by symbol."""
    if not syms or sb is None:
        return {}
    if len(syms) == 1 and limit_per_sym > 220:
        per_sym = min(int(limit_per_sym), 5000)
        db_per_sym = 400
    else:
        per_sym = min(220, max(45, 950 // max(len(syms), 1))) if len(syms) > 3 else min(limit_per_sym, 220)
        db_per_sym = per_sym
    total_limit = min(len(syms) * db_per_sym, 1000)
    by_sym: Dict[str, List[Dict[str, Any]]] = {}
    try:
        res = (
            sb.from_("stock_prices")
            .select("symbol,date,open,high,low,close,volume")
            .eq("exchange", exchange)
            .in_("symbol", syms)
            .order("date", desc=True)
            .limit(total_limit)
            .execute()
        )
        for r in (res.data or []):
            s = str(r.get("symbol") or "").strip().upper()
            if s:
                by_sym.setdefault(s, []).append(r)
    except Exception:
        by_sym = {}

    return _backfill_saudi_ohlcv_from_storage(sb, exchange, by_sym, syms, per_sym)


def _fetch_saudi_recent_dates(sb: Any, count: int = 25, exchange: str = "TADAWUL") -> List[str]:
    """Return latest trading dates from `market_index` (fallback `stock_prices`) for any exchange."""
    cache_key = f"recent_dates:{exchange}:{count}"
    cached = _get_tool_cached(cache_key)
    if cached is not None:
        return cached
    try:
        res = (
            sb.from_("market_index")
            .select("date")
            .eq("exchange", exchange)
            .order("date", desc=True)
            .limit(min(count * 2, 60))
            .execute()
        )
        dates: List[str] = []
        seen = set()
        for r in (res.data or []):
            d = r.get("date")
            if isinstance(d, str) and d not in seen:
                seen.add(d)
                dates.append(d)
                if len(dates) >= count:
                    break
        if dates:
            _set_tool_cached(cache_key, dates)
        return dates
    except Exception:
        return []


def _get_saudi_computed_market_indicators(
    sb: Any, lookback_days: int = 22, exchange: str = "TADAWUL"
) -> List[Dict[str, Any]]:
    """
    Compute per-stock indicators from recent OHLCV bars for any exchange when
    `stock_technical_indicators` has not been populated yet.
    Cached 5 minutes in-memory to keep DB reads minimal.
    """
    cache_key = f"computed_mkt_ti:{exchange}:{lookback_days}"
    cached = _get_tool_cached(cache_key)
    if cached is not None:
        return cached

    dates = _fetch_saudi_recent_dates(sb, count=lookback_days, exchange=exchange)
    if not dates:
        return []
    start_date = dates[-1]
    all_rows: List[Dict[str, Any]] = []
    try:
        if len(dates) <= 2:
            res = (
                sb.from_("stock_prices")
                .select("symbol,date,open,high,low,close,volume")
                .eq("exchange", exchange)
                .in_("date", dates)
                .limit(700)
                .execute()
            )
            all_rows = res.data or []
        else:
            # Bounded pagination up to 6 pages (<= 6000 rows covering ~264 stocks * 22 days)
            page_size = 1000
            for page in range(7):
                start_idx = page * page_size
                end_idx = start_idx + page_size - 1
                res = (
                    sb.from_("stock_prices")
                    .select("symbol,date,open,high,low,close,volume")
                    .eq("exchange", exchange)
                    .gte("date", start_date)
                    .order("date", desc=True)
                    .range(start_idx, end_idx)
                    .execute()
                )
                batch = res.data or []
                all_rows.extend(batch)
                if len(batch) < page_size:
                    break
    except Exception:
        return []

    by_sym: Dict[str, List[Dict[str, Any]]] = {}
    for r in all_rows:
        s = r.get("symbol")
        if s:
            by_sym.setdefault(s, []).append(r)

    computed: List[Dict[str, Any]] = []
    for s_sym, sym_rows in by_sym.items():
        ind = _compute_indicators_from_price_rows(sym_rows)
        if ind:
            ind["symbol"] = s_sym
            computed.append(ind)

    if computed:
        _set_tool_cached(cache_key, computed)
    return computed


def _fetch_saudi_names_map(sb: Any, syms: List[str], exchange: str = "TADAWUL") -> Dict[str, Dict[str, str]]:
    """Fetch name / name_ar / sector for symbols on any exchange cleanly."""
    if not syms or sb is None:
        return {}
    out: Dict[str, Dict[str, str]] = {}
    try:
        res = (
            sb.from_("stocks")
            .select("symbol,name,name_ar,sector")
            .eq("exchange", exchange)
            .in_("symbol", syms[:50])
            .limit(50)
            .execute()
        )
        for r in (res.data or []):
            s = r.get("symbol")
            if s:
                out[s] = {
                    "name": r.get("name") or s,
                    "name_ar": r.get("name_ar") or "",
                    "sector": r.get("sector") or "",
                }
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Tool: get_stock
# ---------------------------------------------------------------------------
def _build_ui_chart_payload(
    rows_desc: List[Dict[str, Any]],
    ema_50: Optional[float] = None,
    support_1: Optional[float] = None,
    resistance_1: Optional[float] = None,
    currency: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Build compact 30-session price/volume series for client-side SVG rendering (stripped before LLM prompt)."""
    if not rows_desc:
        return None
    pts: List[Dict[str, Any]] = []
    for r in reversed(rows_desc[:30]):
        if not isinstance(r, dict):
            continue
        c_val = _safe_price(r.get("close"))
        if c_val is None or c_val <= 0:
            continue
        v_raw = _safe_float(r.get("volume"), 0)
        v_val = int(v_raw) if (v_raw is not None and v_raw >= 0) else None
        pts.append({
            "d": str(r.get("date") or "")[:10],
            "c": c_val,
            "v": v_val,
        })
    if len(pts) < 3:
        return None
    payload: Dict[str, Any] = {
        "series": pts,
        "ema50": ema_50,
        "support1": support_1,
        "resistance1": resistance_1,
    }
    if currency:
        payload["currency"] = currency
    return payload


def _distinct_secondary_levels(
    support_1: Optional[float],
    support_2: Optional[float],
    resistance_1: Optional[float],
    resistance_2: Optional[float],
    bb_low: Optional[float] = None,
    bb_up: Optional[float] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """Ensure S2 < S1 and R2 > R1 when the 20-day and 60-day extremes coincide."""
    s2 = support_2
    if support_1 and (s2 is None or s2 >= support_1 * 0.995):
        if bb_low and bb_low < support_1 * 0.99:
            s2 = _safe_price(bb_low)
        else:
            s2 = _safe_price(support_1 * 0.96)

    r2 = resistance_2
    if resistance_1 and (r2 is None or r2 <= resistance_1 * 1.005):
        if bb_up and bb_up > resistance_1 * 1.01:
            r2 = _safe_price(bb_up)
        else:
            r2 = _safe_price(resistance_1 * 1.05)

    return s2, r2


def _compute_stock_verdict(
    close: Optional[float],
    change_pct: Optional[float],
    rsi: Optional[float],
    macd_hist: Optional[float] = None,
    ema_50: Optional[float] = None,
    ema_200: Optional[float] = None,
    acc_score: Optional[float] = None,
    dist_score: Optional[float] = None,
) -> str:
    """Compute a trend-, momentum-, and flow-aware technical verdict."""
    if close and (ema_50 or ema_200):
        score = 0.0
        if ema_50:
            score += 1.0 if close > ema_50 else -1.0
        if ema_200:
            score += 1.0 if close > ema_200 else -1.0
        if macd_hist is not None:
            score += 0.5 if macd_hist > 0 else (-0.5 if macd_hist < 0 else 0.0)
        if rsi is not None:
            if 50 <= rsi <= 68:
                score += 0.5
            elif rsi > 75:
                score -= 1.0
            elif rsi < 35:
                score -= 0.5
        if acc_score is not None and acc_score >= 50:
            score += 1.0
        if dist_score is not None and dist_score >= 50:
            score -= 1.0

        if score >= 1.5 and (rsi is None or rsi <= 72):
            return "🟢 إيجابي / اتجاه صاعد"
        if score <= -1.0 or (rsi is not None and rsi > 78):
            return "🔴 سلبي / مخاطرة مرتفعة"
        return "🟡 حيادي للمراقبة"

    if change_pct is not None and change_pct > 0 and rsi is not None and 45 <= rsi <= 68:
        return "🟢 إيجابي / فرصة جيدة"
    if (change_pct is not None and change_pct < -2) or (rsi is not None and rsi > 75):
        return "🔴 سلبي / مخاطرة مرتفعة"
    return "🟡 حيادي للمراقبة"


def _normalize_king_ai_score(val: Any) -> Optional[float]:
    """Normalize King AI score onto a unified 0–100 percentage scale (converting 0–1 decimals like 0.71 -> 71.0)."""
    num = _safe_float(val, 4)
    if num is None:
        return None
    if 0.0 < num <= 1.0:
        return round(num * 100.0, 1)
    return round(num, 1)


def _build_fair_value_gap(
    close: float,
    fair_value: float,
    *,
    is_loss_making: bool = False,
) -> Dict[str, Any]:
    """Return exact, unambiguous valuation gap metrics so the LLM never confuses upside_pct with premium_pct."""
    upside = round(((fair_value - close) / close) * 100.0, 2) if close > 0 else 0.0
    price_vs_fv = round(((close - fair_value) / fair_value) * 100.0, 2) if fair_value > 0 else 0.0
    if is_loss_making:
        gap_ar = (
            f"تقييم دفتري مخفّض لشركة خاسرة ({fair_value:g} — السعر الحالي أعلى من التقييم التحفظي بنحو "
            f"+{abs(price_vs_fv):.1f}% ولا يُعد رخيصاً مع استمرار صافي الخسائر)"
        )
    elif upside >= 12.0:
        gap_ar = f"السهم أقل من قيمته العادلة بفرصة صعود +{upside:.1f}%"
    elif upside <= -10.0:
        gap_ar = (
            f"السعر الحالي أعلى من القيمة العادلة بنسبة +{abs(price_vs_fv):.1f}% "
            f"(أي القيمة العادلة أقل من السعر الحالي بنحو {abs(upside):.1f}%)"
        )
    else:
        gap_ar = f"يتداول قريباً من قيمته العادلة (فارق {upside:+.1f}%)"
    return {
        "upside_pct": upside,
        "valuation_upside_pct": upside,
        "price_vs_fv_pct": price_vs_fv,
        "valuation_gap_ar": gap_ar,
    }


def _build_graham_gap_ar(close: Optional[float], graham: Optional[float]) -> Optional[str]:
    """Return exact, unambiguous Graham defensive-floor comparison text without LLM mental math."""
    if not close or not graham or close <= 0 or graham <= 0:
        return None
    up = (graham - close) / close * 100.0
    disc = (graham - close) / graham * 100.0
    if up >= 0:
        return f"أرضية جراهام {graham:g} أعلى من السعر الحالي بنسبة +{up:.1f}% (أي السعر أقل منها بخصم {disc:.1f}%)"
    return f"السعر الحالي أعلى من أرضية جراهام {graham:g} بنسبة +{(close - graham) / graham * 100.0:.1f}% (أي جراهام أقل من السعر بنحو {abs(up):.1f}%)"


def _detect_and_adjust_price_split(
    desc_rows: List[Dict[str, Any]],
    ema_50: Optional[float],
    ema_200: Optional[float],
    close: Optional[float],
) -> Tuple[Optional[float], Optional[float], Optional[float], bool]:
    """Detect unadjusted overnight corporate splits (<0.45x) and recompute split-adjusted EMAs."""
    if not close or close <= 0 or not desc_rows:
        return ema_50, ema_200, None, False
    asc_closes = [
        float(r["close"])
        for r in reversed(list(desc_rows))
        if isinstance(r, dict) and r.get("close") and float(r["close"]) > 0
    ]
    if len(asc_closes) < 5:
        return ema_50, ema_200, None, False

    split_factor = 1.0
    had_split_jump = False
    for idx_c in range(1, len(asc_closes)):
        prev_v = asc_closes[idx_c - 1]
        cur_v = asc_closes[idx_c]
        if prev_v > 0 and cur_v / prev_v < 0.45:
            sp_ratio = cur_v / prev_v
            asc_closes[:idx_c] = [c * sp_ratio for c in asc_closes[:idx_c]]
            split_factor *= sp_ratio
            had_split_jump = True

    out_split_factor: Optional[float] = round(split_factor, 4) if (had_split_jump and split_factor < 0.45) else None
    recent_25 = asc_closes[-25:]
    max_25 = max(recent_25) if recent_25 else close
    stale_ema = bool(
        (ema_50 and max_25 > 0 and ema_50 > max_25 * 1.25)
        or (ema_200 and max_25 > 0 and ema_200 > max_25 * 1.25)
    )
    if (had_split_jump or stale_ema) and len(asc_closes) >= 20:
        def _ewm_span(vals: List[float], span: int) -> float:
            alpha = 2.0 / (span + 1.0)
            cur = vals[0]
            for v_c in vals[1:]:
                cur = alpha * v_c + (1.0 - alpha) * cur
            return round(cur, 4)

        return _ewm_span(asc_closes, 50), _ewm_span(asc_closes, 200), out_split_factor, True
    return ema_50, ema_200, out_split_factor, False


def _normalize_split_adjusted_fundamentals(
    fd: Any,
    close_price: Optional[float],
    split_factor: Optional[float] = None,
    *,
    symbol: str = "",
    market: str = "EGX",
) -> Tuple[Dict[str, Any], bool]:
    """Normalize EGP->USD currency on USD-traded EGX symbols and scale pre-split EPS/BVPS cleanly."""
    from api.fair_value_engine import normalize_fundamentals_for_valuation
    return normalize_fundamentals_for_valuation(
        fd,
        close_price,
        symbol=symbol,
        market=market,
        split_factor=split_factor,
    )


def _compute_stock_context_metrics(
    close: Optional[float],
    ema_50: Optional[float],
    ema_200: Optional[float],
    vwap_20: Optional[float],
    support_1: Optional[float],
    resistance_1: Optional[float],
    stop_loss: Optional[float],
) -> Dict[str, Any]:
    """Pre-compute exact percentage distances, EMA position tags, tactical near-term support/stop, and risk/reward."""
    if not close or close <= 0:
        return {}
    metrics: Dict[str, Any] = {}
    if ema_50:
        metrics["above_ema50"] = close >= ema_50
        metrics["ema50_position_ar"] = f"فوق EMA50 ({ema_50}) ✅" if close >= ema_50 else f"تحت EMA50 ({ema_50}) 🔴"
    if ema_200:
        metrics["above_ema200"] = close >= ema_200
        metrics["ema200_position_ar"] = f"فوق EMA200 ({ema_200}) ✅" if close >= ema_200 else f"تحت EMA200 ({ema_200}) 🔴"
    if vwap_20:
        metrics["above_vwap"] = close >= vwap_20
    dist_s1_pct: Optional[float] = None
    if support_1:
        dist_s1_pct = round(((support_1 - close) / close) * 100.0, 2)
        metrics["dist_to_support_pct"] = dist_s1_pct
    dist_sl_pct: Optional[float] = None
    if stop_loss and stop_loss > 0:
        dist_sl_pct = round(((stop_loss - close) / close) * 100.0, 2)
        metrics["dist_to_stop_loss_pct"] = dist_sl_pct
    dist_r1_pct: Optional[float] = None
    if resistance_1:
        dist_r1_pct = round(((resistance_1 - close) / close) * 100.0, 2)
        metrics["dist_to_resistance_pct"] = dist_r1_pct
    if resistance_1 and stop_loss and resistance_1 > close > stop_loss:
        risk = close - stop_loss
        reward = resistance_1 - close
        if risk > 0:
            metrics["risk_reward_from_close"] = round(reward / risk, 2)
    if support_1 and resistance_1 and stop_loss and stop_loss < support_1 < close < resistance_1:
        s_risk = support_1 - stop_loss
        s_reward = resistance_1 - support_1
        if s_risk > 0:
            metrics["risk_reward_from_support"] = round(s_reward / s_risk, 2)

    # When structural support_1 is far below close (> 12%), compute practical near-term tactical support & stop
    if dist_s1_pct is not None and dist_s1_pct < -12.0:
        metrics["support_1_is_distant"] = True
        near_floors = [
            lvl
            for lvl in (vwap_20, ema_50, ema_200)
            if lvl and (close * 0.88) <= lvl <= (close * 0.985)
        ]
        tac_sup = _safe_price(max(near_floors)) if near_floors else _safe_price(close * 0.94)
        tac_stop = _safe_price(tac_sup * 0.975) if tac_sup else _safe_price(close * 0.92)
        if tac_sup and tac_stop:
            metrics["tactical_support"] = tac_sup
            metrics["tactical_stop_loss"] = tac_stop
            metrics["dist_to_tactical_support_pct"] = round(((tac_sup - close) / close) * 100.0, 2)
            metrics["dist_to_tactical_stop_pct"] = round(((tac_stop - close) / close) * 100.0, 2)
            if resistance_1 and resistance_1 > close > tac_stop:
                t_risk = close - tac_stop
                t_reward = resistance_1 - close
                if t_risk > 0:
                    metrics["tactical_risk_reward"] = round(t_reward / t_risk, 2)
            if resistance_1 and resistance_1 > tac_sup > tac_stop:
                ts_risk = tac_sup - tac_stop
                ts_reward = resistance_1 - tac_sup
                if ts_risk > 0:
                    metrics["tactical_risk_reward_from_support"] = round(ts_reward / ts_risk, 2)

    dist_parts: List[str] = []
    if support_1 and dist_s1_pct is not None:
        dist_parts.append(f"الدعم الأول ({support_1}): {dist_s1_pct:+.2f}%")
    if stop_loss and dist_sl_pct is not None:
        dist_parts.append(f"وقف الخسارة ({stop_loss}): {dist_sl_pct:+.2f}%")
    if metrics.get("tactical_support") and metrics.get("dist_to_tactical_support_pct") is not None:
        dist_parts.append(f"الدعم العملي القريب ({metrics['tactical_support']}): {metrics['dist_to_tactical_support_pct']:+.2f}%")
    if metrics.get("tactical_stop_loss") and metrics.get("dist_to_tactical_stop_pct") is not None:
        dist_parts.append(f"وقف الخسارة العملي ({metrics['tactical_stop_loss']}): {metrics['dist_to_tactical_stop_pct']:+.2f}%")
    if resistance_1 and dist_r1_pct is not None:
        dist_parts.append(f"المقاومة الأولى ({resistance_1}): {dist_r1_pct:+.2f}%")
    if dist_parts:
        metrics["levels_distance_ar"] = " | ".join(dist_parts)

    return metrics


def _summarize_breadth(breadth: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Compute advance/decline ratio and a concise market breadth verdict."""
    if not isinstance(breadth, dict):
        return None
    adv = next((breadth[k] for k in ("advancing", "up", "gainers") if breadth.get(k) is not None), None)
    dec = next((breadth[k] for k in ("declining", "down", "losers") if breadth.get(k) is not None), None)
    try:
        adv_n = int(adv) if adv is not None else None
        dec_n = int(dec) if dec is not None else None
    except Exception:
        return None
    if adv_n is None or dec_n is None:
        return None
    ratio = round(adv_n / max(dec_n, 1), 2)
    if ratio >= 1.5:
        verdict = "🟢 اتساع إيجابي (سيولة شرائية غالبة)"
    elif ratio <= 0.65:
        verdict = "🔴 ضغط بيعي واسع (تفضيل الحذر)"
    else:
        verdict = "🟡 سوق متوازن / انتقائي"
    return {"advance_decline_ratio": ratio, "breadth_verdict": verdict}


def _enrich_rec_distances(rec_item: Dict[str, Any]) -> None:
    """Attach unrealized PnL %, remaining upside %, and stop distance % when last_close is known."""
    lc = _safe_price(rec_item.get("last_close"))
    ep = _safe_price(rec_item.get("entry_price"))
    tp = _safe_price(rec_item.get("target_price"))
    sl = _safe_price(rec_item.get("stop_loss"))
    if not lc or lc <= 0:
        return
    if ep and ep > 0:
        rec_item["pnl_since_entry_pct"] = round(((lc - ep) / ep) * 100.0, 2)
    if tp and tp > 0:
        rec_item["remaining_upside_pct"] = round(((tp - lc) / lc) * 100.0, 2)
    if sl and sl > 0:
        rec_item["dist_to_stop_pct"] = round(((sl - lc) / lc) * 100.0, 2)


_BANK_INDUSTRY_KEYWORDS = (
    "bank", "banks", "insurance", "credit", "savings", "lending", "broker", "leasing",
    "بنك", "بنوك", "مصرف", "مصارف", "تأمين", "تامين",
)
_NON_BANK_EXCLUSIONS = (
    "real estate", "reit", "homebuilding", "property", "construction",
    "technology", "software", "payment", "fintech", "electronic", "telecom",
    "عقار", "تطوير عقاري", "تكنولوجيا", "مدفوعات", "برمجيات",
)


def _is_financial_sector(sector: Any, industry: Any, name: Any = None) -> bool:
    sec_ind = f"{sector or ''} {industry or ''}".lower()
    full_blob = f"{sec_ind} {name or ''}".lower()
    if any(ex in full_blob for ex in _NON_BANK_EXCLUSIONS):
        return False
    if any(kw in sec_ind for kw in _BANK_INDUSTRY_KEYWORDS):
        return True
    # Name-based fallback only if industry is absent (e.g. 'Commercial International Bank', 'Al Rajhi Bank')
    if not industry and any(kw in full_blob for kw in ("bank", "مصرف", "بنك", "تأمين", "insurance")):
        return True
    return False


def _is_tech_growth_sector(sector: Any, industry: Any) -> bool:
    """Detect technology / fintech / telecom / digital-payment companies where asset-light growth multiples apply."""
    blob = f"{sector or ''} {industry or ''}".lower()
    return any(
        kw in blob
        for kw in (
            "technology",
            "software",
            "fintech",
            "payment",
            "telecom",
            "electronic",
            "digital",
            "تكنولوجيا",
            "مدفوعات",
            "اتصالات",
        )
    )


def _build_fundamental_diagnosis(
    metrics: Dict[str, Any],
    *,
    close_price: Optional[float] = None,
    name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Build a deterministic, sector-aware institutional fundamental diagnosis in plain Arabic
    so ARTORO gives users a crystal-clear bottom-line answer: is this stock financially good or bad, and WHY?
    """
    pe = metrics.get("pe_ratio")
    forward_pe = metrics.get("forward_pe")
    pb = metrics.get("pb_ratio")
    ev_ebitda = metrics.get("ev_ebitda")
    eps = metrics.get("eps")
    bvps = metrics.get("book_value_per_share")
    roe = metrics.get("roe_pct")
    roa = metrics.get("roa_pct")
    roic = metrics.get("roic_pct")
    nm = metrics.get("net_margin_pct")
    om = metrics.get("operating_margin_pct")
    rev = metrics.get("revenue")
    ni = metrics.get("net_income")
    fcf = metrics.get("free_cash_flow")
    cash = metrics.get("total_cash")
    debt = metrics.get("total_debt")
    de = metrics.get("debt_to_equity")
    cr = metrics.get("current_ratio")
    dy = metrics.get("dividend_yield_pct")
    payout = metrics.get("payout_ratio_pct")
    f_score = metrics.get("piotroski_score")
    z_score = metrics.get("altman_z_score")
    score = metrics.get("fund_score")

    core_present = sum(
        1 for v in (pe, pb, eps, bvps, roe, roa, nm, ni, de, cr, fcf, dy) if v is not None
    )
    if core_present < 2:
        return None

    is_bank = _is_financial_sector(metrics.get("sector"), metrics.get("industry"), name)
    is_tech = _is_tech_growth_sector(metrics.get("sector"), metrics.get("industry"))
    loss_making = (eps is not None and eps < 0) or (ni is not None and ni < 0)

    strengths: List[str] = []
    weaknesses: List[str] = []

    # 1. Valuation Pillar
    graham_upside: Optional[float] = None
    if close_price and close_price > 0 and eps and eps > 0 and bvps and bvps > 0:
        graham_v = (22.5 * eps * bvps) ** 0.5
        if graham_v > 0:
            graham_upside = round(((graham_v - close_price) / close_price) * 100.0, 1)

    if loss_making:
        valuation_label = "شركة خاسرة حالياً (بدون مكرر ربحية موجب)"
        weaknesses.append("الشركة تحقق خسائر صافية حالياً (ربحية السهم سالبة)")
    elif pe is not None and pe > 0:
        if pe <= 9.5:
            valuation_label = "رخيص وجذاب سعرياً"
            strengths.append(f"مكرر ربحية منخفض وجذاب (P/E = {pe:.2f}x)")
        elif pe <= 15.5:
            valuation_label = "تسعير عادل ومنطقي"
            strengths.append(f"مكرر ربحية متوازن ومنطقي (P/E = {pe:.2f}x)")
        elif pe <= 24.0:
            valuation_label = "مرتفع نسبياً (يسعّر توقعات نمو)"
            weaknesses.append(f"مكرر الربحية مرتفع نسبياً (P/E = {pe:.2f}x) — يحتاج نمو أرباح لتبريره")
        else:
            valuation_label = "غالي / متضخم سعرياً"
            weaknesses.append(f"السهم مسعّر بمكرر ربحية مرتفع جداً (P/E = {pe:.2f}x)")
    elif pb is not None and pb > 0:
        if pb <= 1.1:
            valuation_label = "يتداول قرب أو أقل من القيمة الدفترية"
            strengths.append(f"مضاعف قيمة دفترية منخفض (P/B = {pb:.2f}x)")
        elif pb <= 2.5:
            valuation_label = "تسعير دفتري متوازن"
        else:
            valuation_label = "مرتفع مقارنة بالقيمة الدفترية"
            weaknesses.append(f"مضاعف القيمة الدفترية مرتفع (P/B = {pb:.2f}x)")
    else:
        valuation_label = "بيانات التقييم محدودة"

    if pb is not None and pb > 0 and not loss_making:
        if pb <= 1.25 and (roe is None or roe >= 12):
            if not any("P/B" in s for s in strengths):
                strengths.append(f"سعر قريب من القيمة الدفترية (P/B = {pb:.2f}x)")
        elif pb >= 4.0 and (roe is None or roe < 25):
            if not any("P/B" in w for w in weaknesses):
                weaknesses.append(f"مضاعف القيمة الدفترية مرتفع ({pb:.2f}x)")

    has_attractive_forward_pe = (
        forward_pe is not None
        and 0 < forward_pe <= 12.0
        and pe is not None
        and pe > 15.5
    )
    if has_attractive_forward_pe and not loss_making:
        strengths.append(
            f"المكرر المستقبلي جذاب (Forward P/E = {forward_pe:.2f}x) — السوق يسعّر تحسناً قوياً في الأرباح القادمة"
        )

    if graham_upside is not None and graham_upside >= 15 and not loss_making:
        strengths.append(f"يتداول بخصم عن قيمة جراهام الدفاعية (فجوة صعود نظرية +{graham_upside:.0f}%)")
    elif (
        graham_upside is not None
        and graham_upside <= -30
        and not loss_making
        and not is_bank
        and not is_tech
        and not has_attractive_forward_pe
    ):
        weaknesses.append(f"السعر السوقي أعلى من قيمة جراهام الدفاعية بنحو {abs(graham_upside):.0f}%")

    # 2. Profitability Pillar
    if loss_making:
        profitability_label = "خسائر صافية (ربحية سلبية)"
    elif roe is not None:
        if roe >= 20.0:
            profitability_label = "ربحية ممتازة جداً"
            strengths.append(f"عائد قوي جداً على حقوق المساهمين (ROE = {roe:.1f}%)")
        elif roe >= 12.0:
            profitability_label = "ربحية جيدة وصحية"
            strengths.append(f"عائد جيد على حقوق المساهمين (ROE = {roe:.1f}%)")
        elif roe >= 5.0:
            profitability_label = "ربحية متواضعة"
            weaknesses.append(f"العائد على حقوق المساهمين متواضع (ROE = {roe:.1f}%)")
        else:
            profitability_label = "ربحية ضعيفة جداً"
            weaknesses.append(f"العائد على حقوق المساهمين ضعيف جداً (ROE = {roe:.1f}%)")
    elif nm is not None:
        profitability_label = "ربحية جيدة" if nm >= 10 else ("ربحية ضيقة" if nm > 0 else "خسائر صافية")
    else:
        profitability_label = "غير مكتملة"

    if is_bank and roa is not None:
        if roa >= 1.5:
            strengths.append(f"كفاءة أصول ممتازة للقطاع المصرفي (ROA = {roa:.2f}%)")
        elif roa < 0.7:
            weaknesses.append(f"عائد على الأصول منخفض نسبياً للبنوك (ROA = {roa:.2f}%)")
    elif not is_bank and nm is not None and not loss_making:
        if nm >= 18.0:
            strengths.append(f"هامش ربح صافي قوي ({nm:.1f}%)")
        elif 0 < nm < 4.0:
            weaknesses.append(f"هامش ربح صافي ضيق جداً ({nm:.1f}%) — حساس لأي ارتفاع في التكاليف")

    # 3. Financial Health & Balance Sheet Safety Pillar (Bank-Aware!)
    high_solvency_risk = False
    if is_bank:
        health_label = "مؤسسة مالية/بنك (ودائع العملاء التزامات طبيعية — يُقيّم بـ ROE وROA وP/B وليس D/E أو السيولة الصناعية)"
    else:
        if de is not None and de <= 0.45 and (cr is None or cr >= 1.2):
            health_label = "ميزانية صلبة وآمنة (ديون منخفضة)"
            strengths.append(f"مديونية منخفضة وآمنة (الديون/حقوق الملكية = {de:.2f}x)")
        elif de is not None and de > 1.8:
            health_label = "مديونية مرتفعة (مخاطرة تمويل وفوائد)"
            high_solvency_risk = True
            weaknesses.append(f"مديونية عالية مقارنة بحقوق الملكية (D/E = {de:.2f}x)")
        elif cr is not None and cr < 1.0:
            health_label = "ضغط سيولة قصيرة الأجل"
            high_solvency_risk = True
            weaknesses.append(f"نسبة التداول أقل من 1 ({cr:.2f}x) — الالتزامات القصيرة تفوق الأصول المتداولة")
        elif de is not None or cr is not None:
            health_label = "ملاءة مالية متوازنة"
        else:
            health_label = "بيانات المديونية محدودة"

        if cash is not None and debt is not None and cash > debt and cash > 0:
            strengths.append("مركز نقدي صافي إيجابي (الكاش يغطي إجمالي الديون بالكامل)")
        if z_score is not None and z_score < 1.8:
            high_solvency_risk = True
            weaknesses.append(f"مؤشر ألتمان للأمان المالي منخفض (Altman Z = {z_score:.2f} — منطقة حذر)")
        if f_score is not None:
            if f_score >= 7:
                strengths.append(f"جودة مالية ومحاسبية قوية (Piotroski F-Score = {int(f_score)}/9)")
            elif f_score <= 3:
                weaknesses.append(f"ضعف في مؤشر الجودة المالية (Piotroski F-Score = {int(f_score)}/9)")

    # 4. Cash Flow Quality & Dividends Pillar
    cash_quality_label = "غير متاح"
    neg_fcf_vs_profit = False
    if not is_bank and fcf is not None:
        if ni is not None and ni > 0:
            if fcf >= 0.7 * ni:
                cash_quality_label = "أرباح نقدية حقيقية (التدفق النقدي الحر يغطي صافي الربح)"
                strengths.append("أرباح عالية الجودة مدعومة بتدفق نقدي حر موجب وقوي (كاش فعلي)")
            elif fcf > 0:
                cash_quality_label = "تدفق نقدي حر موجب لكنه أقل من الربح المحاسبي"
            else:
                cash_quality_label = "تحذير جودة أرباح: الربح المحاسبي موجب لكن التدفق النقدي الحر سالب"
                neg_fcf_vs_profit = True
                weaknesses.append("التدفق النقدي الحر سالب رغم تسجيل أرباح محاسبية (يستحق الانتباه لتحصيل الكاش أو النفقات الرأسمالية)")
        elif fcf > 0:
            cash_quality_label = "تدفق نقدي حر موجب"
        else:
            cash_quality_label = "تدفق نقدي حر سالب"

    if dy is not None and dy >= 4.0:
        strengths.append(f"توزيعات نقدية مجزية (عائد توزيع {dy:.1f}%)")
    if payout is not None and payout > 100.0 and dy is not None and dy > 0:
        weaknesses.append(f"نسبة توزيع الأرباح تتجاوز 100% ({payout:.0f}%) — استدامة الكوبون تحتاج متابعة")

    # 5. Value Trap Detection
    value_trap_warning: Optional[str] = None
    if (
        not is_bank
        and pe is not None
        and 0 < pe <= 10.5
        and (
            (neg_fcf_vs_profit and (de is not None and de > 1.2))
            or high_solvency_risk
            or (f_score is not None and f_score <= 3)
        )
    ):
        value_trap_warning = (
            "تنبيه فخ قيمة محتمل (Value Trap): السهم يبدو رخيصاً بمكرر الربحية، لكن هناك ضغط في الديون/السيولة أو جودة التدفق النقدي."
        )

    # 6. Bottom-Line Verdict & Investor Fit
    eff_score = float(score) if score is not None else None
    is_expensive = pe is not None and pe > 22.0
    is_growth_priced = pe is not None and 16.0 < pe <= 22.0
    is_cheap_or_fair = pe is not None and 0 < pe <= 16.0

    if loss_making:
        verdict_ar = "🔴 سلبي مالياً — الشركة تحقق خسائر حالياً (مخاطرة أساسية مرتفعة)"
        suitable_for = "غير مناسب للاستثمار الأساسي المحافظ حالياً (يصلح للمراقبة حتى التحول للربحية أو للمضاربة بوقف صارم فقط)"
    elif high_solvency_risk and (eff_score is None or eff_score < 55):
        verdict_ar = "🔴 ضعيف مالياً — ضغط ديون/سيولة مرتفع يرفع المخاطرة"
        suitable_for = "مخاطرة مالية مرتفعة — يحتاج حذراً شديداً ولا يناسب المستثمر المحافظ"
    elif value_trap_warning:
        verdict_ar = "🟠 حذر (فخ قيمة محتمل) — السعر يبدو رخيصاً لكن الأساسيات فيها مخاطر"
        suitable_for = "للمراقبة فقط حتى يتحسن التدفق النقدي أو تنخفض المديونية"
    elif (eff_score is not None and eff_score >= 75) and not is_expensive and not is_growth_priced:
        verdict_ar = "🟢 ممتاز مالياً — شركة قوية وسعرها جذاب/عادل"
        suitable_for = (
            "مناسب للاستثمار المتوسط والطويل (قيمة + توزيعات نقدية)"
            if (dy is not None and dy >= 3.5)
            else "مناسب للاستثمار المتوسط والطويل (جودة مالية عالية وتقييم منطقي)"
        )
    elif (eff_score is not None and eff_score >= 65) or (roe is not None and roe >= 15 and not high_solvency_risk):
        if is_expensive:
            verdict_ar = "🟡 شركة قوية مالياً — لكن سعر السهم الحالي مرتفع جداً"
            suitable_for = "شركة عالية الجودة؛ الأفضل انتظار تصحيح سعري أو دخول تدريجي بدل المطاردة"
        elif is_growth_priced:
            verdict_ar = "🟢 شركة قوية مالياً — مسعّرة كسهم نمو (تقييم متوسط إلى مرتفع نسبياً)"
            suitable_for = "مناسب لمستثمر النمو على المدى المتوسط مع مراقبة استمرار نمو الأرباح"
        else:
            verdict_ar = "🟢 جيد إلى قوي مالياً — أساسيات صحية ومتوازنة"
            suitable_for = (
                "مناسب للاستثمار المتوازن وتوزيعات الدخل"
                if (dy is not None and dy >= 3.0)
                else "مناسب للاستثمار المتوسط مع متابعة نتائج الأعمال الدورية"
            )
    elif (eff_score is not None and eff_score >= 45) or is_cheap_or_fair:
        verdict_ar = "🟡 متوسط مالياً — يجمع بين نقاط إيجابية وملاحظات تحتاج متابعة"
        suitable_for = "يحتاج انتقائية ومراقبة للنتائج القادمة (لا تضع فيه وزناً كبيراً من المحفظة)"
    else:
        verdict_ar = "🟠 ضعيف مالياً — ربحية متواضعة أو تقييم غير جذاب"
        suitable_for = "أقل جاذبية استثمارياً مقارنة ببدائل أقوى في نفس السوق"

    diag: Dict[str, Any] = {
        "verdict_ar": verdict_ar,
        "is_financial_institution": is_bank,
        "valuation": valuation_label,
        "profitability": profitability_label,
        "financial_health": health_label,
        "cash_quality": cash_quality_label,
        "strengths": strengths[:7],
        "weaknesses": weaknesses[:5],
        "suitable_for": suitable_for,
    }
    if value_trap_warning:
        diag["value_trap_warning"] = value_trap_warning
    if graham_upside is not None:
        diag["graham_upside_pct"] = graham_upside
    return diag


def _extract_rich_fundamentals(
    fd: Any,
    fund_score: Any = None,
    *,
    close_price: Optional[float] = None,
    name: Optional[str] = None,
    trade_currency: Optional[str] = None,
    split_factor: Optional[float] = None,
    symbol: str = "",
    market: str = "EGX",
) -> Dict[str, Any]:
    """Extract normalized financial & fundamental ratios (camelCase + snake_case) plus deterministic diagnosis."""
    if not isinstance(fd, dict):
        fd = {}
    eff_sym = str(symbol or fd.get("symbol") or "").strip().upper()
    raw_fin_curr = str(fd.get("financialCurrency") or fd.get("currency") or "").strip().upper()
    fd, fund_split_adjusted = _normalize_split_adjusted_fundamentals(
        fd,
        close_price,
        split_factor=split_factor,
        symbol=eff_sym,
        market=market,
    )
    pick = lambda *ks: next((fd.get(k) for k in ks if fd.get(k) is not None and fd.get(k) != ""), None)
    raw = {
        "pe_ratio": _safe_float(pick("peRatio", "pe_ratio", "trailing_pe")),
        "forward_pe": _safe_float(pick("forwardPe", "forward_pe")),
        "pb_ratio": _safe_float(pick("pbRatio", "pb_ratio")),
        "ps_ratio": _safe_float(pick("priceToSales", "ps_ratio")),
        "ev_ebitda": _safe_float(pick("evToEbitda", "ev_ebitda")),
        "eps": _safe_float(pick("eps", "trailing_eps"), 4),
        "book_value_per_share": _safe_float(pick("bookValuePerShare", "book_value_per_share", "bvps")),
        "roe_pct": _safe_float(pick("roe", "return_on_equity")),
        "roa_pct": _safe_float(pick("roa", "return_on_assets")),
        "roic_pct": _safe_float(pick("roic")),
        "dividend_yield_pct": _safe_float(pick("dividendYield", "dividend_yield")),
        "dividend_per_share": _safe_float(pick("dividendPerShare", "dividend_per_share"), 4),
        "payout_ratio_pct": _safe_float(pick("payoutRatio", "payout_ratio")),
        "market_cap": _safe_float(pick("marketCap", "market_cap"), 2),
        "revenue": _safe_float(pick("revenue", "total_revenue"), 2),
        "net_income": _safe_float(pick("netIncome", "net_income"), 2),
        "ebitda": _safe_float(pick("ebitda"), 2),
        "free_cash_flow": _safe_float(pick("freeCashFlow", "free_cash_flow"), 2),
        "gross_margin_pct": _safe_float(pick("grossMargin", "gross_margin")),
        "operating_margin_pct": _safe_float(pick("operatingMargin", "operating_margin")),
        "net_margin_pct": _safe_float(pick("netMargin", "net_margin", "profit_margin")),
        "total_cash": _safe_float(pick("totalCash", "total_cash"), 2),
        "total_debt": _safe_float(pick("totalDebt", "total_debt"), 2),
        "debt_to_equity": _safe_float(pick("debtToEquity", "debt_to_equity")),
        "current_ratio": _safe_float(pick("currentRatio", "current_ratio")),
        "piotroski_score": _safe_float(pick("piotroskiFScore"), 0),
        "altman_z_score": _safe_float(pick("altmanZScore")),
        "ex_dividend_date": pick("exDividendDate", "ex_dividend_date"),
        "earnings_date": pick("earningsDate", "earnings_date"),
        "sector": pick("sector"),
        "industry": pick("industry"),
        "fund_score": _safe_float(fund_score),
    }
    clean = {k: v for k, v in raw.items() if v is not None}
    roe_v = clean.get("roe_pct")
    pe_v = clean.get("pe_ratio")
    pb_v = clean.get("pb_ratio")
    if (
        isinstance(roe_v, (int, float))
        and isinstance(pe_v, (int, float))
        and isinstance(pb_v, (int, float))
        and roe_v > 0
        and pe_v > 0
        and pb_v > 0
    ):
        implied_roe_end = round((float(pb_v) / float(pe_v)) * 100.0, 1)
        if abs(float(roe_v) - implied_roe_end) >= 4.0:
            clean["roe_basis_note_ar"] = (
                f"ملاحظة محاسبية: ROE المعلن ({float(roe_v):.1f}%) محسوب على متوسط حقوق الملكية للفترة، "
                f"بينما قسمة P/B على P/E تعطي ~{implied_roe_end:.1f}% على حقوق الملكية الختامية."
            )
    if trade_currency == "$" and raw_fin_curr == "EGP":
        clean["financials_currency"] = "ج.م"
        if fd.get("fx_adjusted_from_egp"):
            clean["financials_currency_note_ar"] = (
                "تنبيه عملة القوائم: سعر السهم وربحية السهم (EPS) والقيمة الدفترية للسهم محوّلة بالدولار ($)، "
                "بينما إجماليات القوائم المالية (الإيرادات وصافي الربح والتدفق النقدي والديون) مسجلة بالجنيه المصري (ج.م) — اكتب الإجماليات بـ ج.م."
            )
        else:
            clean["financials_currency_note_ar"] = (
                "تنبيه عملة القوائم: سعر تداول السهم بالدولار ($) لكن أرقام القوائم المالية والتدفق النقدي "
                "والكوبون المسجل بالجنيه المصري (ج.م) — اكتبها بـ ج.م ولا تضع علامة $ بجانبها."
            )
    if fund_split_adjusted:
        clean["fundamentals_split_adjusted"] = True
    diag = _build_fundamental_diagnosis(clean, close_price=close_price, name=name or pick("name", "name_ar"))
    if diag:
        clean["fundamental_diagnosis"] = diag
    return clean


def _resolve_cached_sector_multiples(symbol: str, market: str = "EGX") -> Tuple[Optional[float], Optional[float]]:
    """Lookup live sector median (P/E, P/B) from shared `/fair-value` RAM cache so Chat & Page match 100%."""
    sym_u = str(symbol or "").strip().upper()
    if not sym_u:
        return None, None
    mkt_u = str(market or "EGX").strip().upper()
    norm_mkt = (
        "tasi" if mkt_u in ("TADAWUL", "TASI", "SA", "SAUDI")
        else ("qatar" if mkt_u in ("QSE", "QATAR", "QE")
        else ("uae" if mkt_u in ("DFM", "ADX", "UAE") else "egx"))
    )
    try:
        from api.routers.offload_public import _FAIR_VALUE_CACHE, _get_fair_value
        found, cached_rep = _FAIR_VALUE_CACHE.get(norm_mkt)
        if not found:
            sb_chk = _get_sb() if norm_mkt == "egx" else _get_sb_for_market(mkt_u)
            sb_url = getattr(sb_chk, "supabase_url", None)
            if sb_chk is None or not isinstance(sb_url, str) or not sb_url.startswith("http"):
                return None, None
            cached_rep = _get_fair_value(norm_mkt)
        for st_row in ((cached_rep or {}).get("stocks") or []):
            if str(st_row.get("symbol") or "").upper() == sym_u:
                return _safe_float(st_row.get("sectorMedianPe")), _safe_float(st_row.get("sectorMedianPb"))
    except Exception:
        pass
    return None, None


def _compute_fundamental_fair_value(
    close: float,
    vwap: float,
    ema: float,
    fd: Optional[Dict[str, Any]],
    market: str = "EGX",
    split_factor: Optional[float] = None,
    *,
    symbol: str = "",
    ema_200: Optional[float] = None,
    sector_median_pe: Optional[float] = None,
    sector_median_pb: Optional[float] = None,
) -> Tuple[float, str, Dict[str, Any]]:
    """
    Single-source Fair Value delegating directly to `api.fair_value_engine.compute_unified_fair_value`
    so AI Chat (`get_fair_value` & `get_stock`) matches `/fair-value` to the exact penny.
    """
    from api.fair_value_engine import compute_unified_fair_value

    eff_sym = str(symbol or (fd.get("symbol") if isinstance(fd, dict) else "") or "").strip().upper()
    if (sector_median_pe is None or sector_median_pb is None) and eff_sym:
        c_pe, c_pb = _resolve_cached_sector_multiples(eff_sym, market)
        if sector_median_pe is None and c_pe is not None:
            sector_median_pe = c_pe
        if sector_median_pb is None and c_pb is not None:
            sector_median_pb = c_pb

    res = compute_unified_fair_value(
        symbol=eff_sym,
        close=close,
        fund_data=fd if isinstance(fd, dict) else None,
        ind={
            "ema_200": ema_200 if ema_200 is not None else ema,
            "ema_50": ema,
            "vwap_20": vwap,
        },
        sector_median_pe=sector_median_pe,
        sector_median_pb=sector_median_pb,
        market=market,
        split_factor=split_factor,
    )

    extra: Dict[str, Any] = {}
    if res.get("isLossMaking"):
        extra["is_loss_making"] = True
    if res.get("lossMakingDiscountApplied"):
        extra["loss_making_discount_applied"] = True
    if res.get("peRatio") is not None:
        extra["pe_ratio"] = res["peRatio"]
    if res.get("forwardPe") is not None:
        extra["forward_pe"] = res["forwardPe"]
    if res.get("pbRatio") is not None:
        extra["pb_ratio"] = res["pbRatio"]
    if res.get("eps") is not None:
        extra["eps"] = res["eps"]
    if res.get("bvps") is not None:
        extra["book_value_per_share"] = res["bvps"]
    if res.get("roe") is not None:
        extra["roe_pct"] = res["roe"]
    if res.get("dividendYield") is not None:
        extra["dividend_yield_pct"] = res["dividendYield"]
    if res.get("sectorAr"):
        extra["sector"] = res["sectorAr"]
    if res.get("peFairValue") is not None:
        extra["pe_fair_value"] = res["peFairValue"]
    if res.get("pbFairValue") is not None:
        extra["pb_fair_value"] = res["pbFairValue"]
    if res.get("grahamValue") is not None:
        extra["graham_value"] = res["grahamValue"]
    elif res.get("classicGrahamValue") is not None:
        extra["graham_value"] = res["classicGrahamValue"]
    if res.get("formulaSubstitutionAr"):
        extra["formula_substitution_ar"] = res["formulaSubstitutionAr"]
    return float(res["fairValue"]), str(res["modelLabelAr"]), extra


_CATALOG_CACHE: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}
_CATALOG_CACHE_LOCK = threading.Lock()
_CATALOG_TTL_SECONDS = 3600.0


def _get_market_stocks_catalog(exchange: str = "EGX") -> List[Dict[str, str]]:
    """Hourly RAM-cached catalog of active stocks (symbol, name, name_ar) from Supabase."""
    raw_exch = str(exchange or "EGX").strip().upper()
    exch = "UAE" if raw_exch == "UAE" else _normalize_market_code(raw_exch)
    now = time.time()
    with _CATALOG_CACHE_LOCK:
        hit = _CATALOG_CACHE.get(exch)
        if hit and (now - hit[0]) < _CATALOG_TTL_SECONDS:
            return hit[1]
    sb = _get_sb() if exch == "EGX" else _get_sb_for_market("DFM" if exch == "UAE" else exch)
    if sb is None:
        return []
    try:
        if exch in ("TADAWUL", "TASI"):
            exchs = ["TADAWUL", "TASI"]
        elif exch == "UAE":
            exchs = ["DFM", "ADX"]
        else:
            exchs = [exch]
        rows = (
            sb.table("stocks")
            .select("symbol,name,name_ar")
            .in_("exchange", exchs)
            .eq("is_active", True)
            .limit(450)
            .execute()
            .data
            or []
        )
        cleaned = [
            {
                "symbol": str(r.get("symbol") or "").strip().upper(),
                "name": str(r.get("name") or "").strip(),
                "name_ar": str(r.get("name_ar") or "").strip(),
            }
            for r in rows
            if r.get("symbol")
        ]
        with _CATALOG_CACHE_LOCK:
            _CATALOG_CACHE[exch] = (now, cleaned)
        return cleaned
    except Exception:
        return []


def _search_catalog_candidates(
    query_text: str,
    exchange: str = "EGX",
    limit: int = 4,
    min_score: float = 2.0,
) -> List[Dict[str, str]]:
    """Zero-regex token-overlap + SequenceMatcher lookup against the real DB stocks catalog."""
    from difflib import SequenceMatcher

    raw = str(query_text or "").strip()
    if len(raw) < 2:
        return []
    q_norm = _normalize_arabic_text(raw).lower()
    q_tokens = {t for t in q_norm.split() if len(t) >= 2 and t not in ("سهم", "شركه", "شركة", "شركات", "في", "من", "على")}
    catalog = _get_market_stocks_catalog(exchange)
    if not catalog:
        return []

    scored: List[Tuple[float, Dict[str, str]]] = []
    for item in catalog:
        sym = item["symbol"]
        sym_low = sym.lower()
        name_en = item["name"].lower()
        name_ar = _normalize_arabic_text(item["name_ar"]).lower()
        alias_ar = _normalize_arabic_text(_alias_name_for_symbol(sym, market=exchange) or "").lower()
        haystack = f"{sym_low} {name_en} {name_ar} {alias_ar}".strip()
        if not haystack:
            continue

        score = 0.0
        if q_norm == sym_low:
            score = 10.0
        elif sym_low.startswith(q_norm) or (len(q_norm) >= 3 and q_norm in sym_low):
            score = 4.0
        else:
            # Pure token overlap (Arabic + English)
            if q_tokens:
                h_tokens = set(haystack.split())
                exact_hits = len(q_tokens & h_tokens)
                sub_hits = sum(1 for qt in q_tokens if qt in haystack)
                score += exact_hits * 2.5 + sub_hits * 1.2
            # SequenceMatcher similarity for minor typos (e.g. IENG -> INEG, PREMIUM -> Premium HealthCare)
            sim_sym = SequenceMatcher(None, q_norm, sym_low).ratio()
            sim_name = max(
                SequenceMatcher(None, q_norm, name_en[: len(q_norm) + 8]).ratio() if name_en else 0.0,
                SequenceMatcher(None, q_norm, name_ar[: len(q_norm) + 8]).ratio() if name_ar else 0.0,
                SequenceMatcher(None, q_norm, alias_ar[: len(q_norm) + 8]).ratio() if alias_ar else 0.0,
            )
            if sim_sym >= 0.72:
                score += sim_sym * 3.0
            if sim_name >= 0.65:
                score += sim_name * 2.5

        if score >= min_score:
            scored.append((score, {
                "symbol": sym,
                "name_ar": item["name_ar"] or _alias_name_for_symbol(sym, market=exchange) or item["name"] or sym,
                "name": item["name"],
                "exchange": exchange,
            }))

    scored.sort(key=lambda x: (x[0], -len(x[1]["symbol"])), reverse=True)
    return [c for _, c in scored[:limit]]


_CATALOG_INDEX_BY_ID: Dict[str, Tuple[int, Dict[str, Dict[str, str]]]] = {}
_NON_TICKER_LABELS = frozenset({
    "EGX", "TASI", "TADAWUL", "QSE", "DFM", "ADX", "UAE", "KSE", "COMMODITIES",
    "ALL", "MARKET", "USD", "EGP", "SAR", "QAR", "AED", "KWD", "NONE", "NULL",
})


def _resolve_symbol_display_names(symbol: str, exchange: str = "EGX") -> Tuple[str, str]:
    """O(1) cached lookup returning (name_ar, name_en) from DB catalog, canonical EGX map, and aliases."""
    sym = str(symbol or "").strip().upper()
    if not sym or sym in _NON_TICKER_LABELS:
        return ("", "")
    exch = _normalize_market_code(exchange)
    catalog = _get_market_stocks_catalog(exch)
    item: Optional[Dict[str, str]] = None
    if catalog:
        hit = _CATALOG_INDEX_BY_ID.get(exch)
        cat_id = id(catalog)
        if hit and hit[0] == cat_id:
            idx_map = hit[1]
        else:
            idx_map = {str(it.get("symbol") or "").upper(): it for it in catalog if it.get("symbol")}
            _CATALOG_INDEX_BY_ID[exch] = (cat_id, idx_map)
        item = idx_map.get(sym)

    canon = CANONICAL_EGX_STOCK_NAMES.get(sym) or {} if exch == "EGX" else {}
    db_ar = str(item.get("name_ar") or "").strip() if item else ""
    db_en = str(item.get("name") or "").strip() if item else ""
    if db_ar.upper() == sym:
        db_ar = ""
    if db_en.upper() == sym:
        db_en = ""

    canon_ar = str(canon.get("name_ar") or "").strip()
    canon_en = str(canon.get("name_en") or "").strip()
    alias_ar = str(_alias_name_for_symbol(sym, market=exch) or "").strip()
    if alias_ar.upper() == sym:
        alias_ar = ""

    name_ar = db_ar or canon_ar or alias_ar
    name_en = db_en or canon_en
    return (name_ar, name_en)


def _enrich_tool_result_identities(res: Any, default_market: Optional[str] = None) -> Any:
    """Universal identity & currency enricher ensuring zero bare tickers or wrong currencies across all tools."""
    if not isinstance(res, (dict, list)):
        return res
    base_mkt = _normalize_market_code(default_market or get_active_market_context() or "EGX")

    def _visit(node: Any, depth: int) -> None:
        if depth > 4:
            return
        if isinstance(node, list):
            for el in node:
                _visit(el, depth + 1)
            return
        if not isinstance(node, dict):
            return

        sym_raw = node.get("symbol")
        if isinstance(sym_raw, str):
            sym = sym_raw.strip().upper()
            if sym and sym not in _NON_TICKER_LABELS and re.fullmatch(r"[A-Z0-9.=-]{2,14}", sym):
                row_exch = _normalize_market_code(node.get("exchange") or node.get("market") or base_mkt)
                if "." in sym:
                    suf = _reg_detect_exchange_from_suffix(sym)
                    if suf:
                        sym = suf[0]
                        row_exch = suf[1]
                cur_ar = str(node.get("name_ar") or "").strip()
                cur_en = str(node.get("name") or "").strip()
                need_ar = not cur_ar or cur_ar.upper() == sym
                need_en = not cur_en or cur_en.upper() == sym
                if need_ar or need_en:
                    res_ar, res_en = _resolve_symbol_display_names(sym, row_exch)
                    if need_ar and res_ar:
                        node["name_ar"] = res_ar
                    if need_en and res_en:
                        node["name"] = res_en
                    elif need_en and res_ar and "name" in node and not cur_en:
                        node["name"] = res_ar
                if "currency" in node or any(
                    k in node for k in ("close", "current_price", "fair_value", "support_1", "market_value", "entry_price")
                ):
                    canon_curr = _reg_currency_for_symbol(sym, row_exch)
                    if not str(node.get("currency") or "").strip() or (row_exch == "EGX" and canon_curr == "$"):
                        node["currency"] = canon_curr

        for v in node.values():
            if isinstance(v, (dict, list)):
                _visit(v, depth + 1)

    _visit(res, 0)
    return res


def _sync_search_stocks(queries: List[str], market: Optional[str] = None) -> Dict[str, Any]:
    """Fast RAM-cached stock lookup resolving Arabic names, nicknames, and tickers in <1ms."""
    eff_mkt = _normalize_market_code(market or get_active_market_context() or "EGX")
    clean_qs = [str(q).strip() for q in (queries or []) if str(q or "").strip()][:20]
    if not clean_qs:
        return {"status": "error", "message": "لم يتم تحديد كلمات بحث صالحة", "results": []}

    norm_egx_map: Dict[str, str] = {}
    if eff_mkt == "EGX":
        for k_ar, v_sym in ARABIC_STOCK_MAPPINGS.items():
            nk = _normalize_arabic_text(k_ar).lower()
            if nk and nk not in norm_egx_map:
                norm_egx_map[nk] = v_sym.upper()

    results: List[Dict[str, Any]] = []
    for q in clean_qs:
        seen_syms = set()
        matches: List[Dict[str, str]] = []

        def _add_match(sym_code: str, exch_code: str) -> None:
            su = str(sym_code or "").strip().upper()
            if not su or su in seen_syms or len(matches) >= 3:
                return
            seen_syms.add(su)
            ar_nm, en_nm = _resolve_symbol_display_names(su, exch_code)
            matches.append({
                "symbol": su,
                "name_ar": ar_nm or en_nm or su,
                "name": en_nm or ar_nm or su,
                "exchange": exch_code,
                "currency": _reg_currency_for_symbol(su, exch_code),
            })

        q_norm = _normalize_arabic_text(q).lower()
        if eff_mkt == "EGX":
            direct = norm_egx_map.get(q_norm)
            if not direct:
                padded_q = f" {q_norm} "
                for nk, v_sym in sorted(norm_egx_map.items(), key=lambda kv: len(kv[0]), reverse=True):
                    if len(nk) >= 3 and f" {nk} " in padded_q:
                        direct = v_sym
                        break
            if direct:
                _add_match(direct, "EGX")
        elif eff_mkt == "TADAWUL":
            sa_hit = _resolve_saudi_alias_local(q)
            if sa_hit and sa_hit != "TASI":
                _add_match(sa_hit, "TADAWUL")

        for cand in _search_catalog_candidates(q, exchange=eff_mkt, limit=3, min_score=2.0):
            _add_match(cand["symbol"], cand.get("exchange") or eff_mkt)

        results.append({"query": q, "matches": matches})

    return {
        "status": "success",
        "market": _ui_market_label(eff_mkt),
        "exchange": eff_mkt,
        "results": results,
    }


async def execute_search_stocks(queries: List[str], market: Optional[str] = None) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_search_stocks, queries, market)


def _sync_get_stock(symbols: List[str], market: Optional[str] = None) -> Dict[str, Any]:
    grouped_syms = _group_symbols_by_exchange(symbols, market=market)
    if not grouped_syms:
        return {"status": "error", "message": "لم يتم تحديد رموز أسهم صالحة"}

    egx_syms = grouped_syms.get("EGX", [])
    non_egx_groups = {exch: syms for exch, syms in grouped_syms.items() if exch != "EGX" and syms}

    allow_recs = _ALLOW_RECOMMENDATIONS_CTX.get()
    cache_parts = []
    for exch_k in sorted(grouped_syms.keys()):
        cache_parts.extend(f"{exch_k}:{s}" for s in sorted(grouped_syms[exch_k]))
    cache_key = f"get_stock:{','.join(cache_parts)}:rec={1 if allow_recs else 0}"
    cached = _get_tool_cached(cache_key)
    if cached is not None:
        return cached

    stocks_data: List[Dict[str, Any]] = []
    errors: List[str] = []
    total_requested_syms = len(egx_syms) + sum(len(v) for v in non_egx_groups.values())

    # ── 1. EGX symbols (Primary Supabase) ────────────────────────────────────
    if egx_syms:
        sb = _get_sb()

        levels_map: Dict[str, Dict[str, Any]] = {}
        by_sym: Dict[str, List[Dict[str, Any]]] = {}
        try:
            price_limit = min(max(len(egx_syms) * 120, 120), 2200)
            res_prices = (
                sb.from_("stock_prices")
                .select("symbol,high,low,close,volume,date")
                .eq("exchange", "EGX")
                .in_("symbol", egx_syms)
                .order("date", desc=True)
                .limit(price_limit)
                .execute()
            )
            for r in (res_prices.data or []):
                s_sym = r.get("symbol")
                by_sym.setdefault(s_sym, []).append(r)
            for s_sym, sym_rows in by_sym.items():
                recent_20 = sym_rows[:20]
                recent_lows = [float(r["low"]) for r in recent_20 if r.get("low")]
                recent_highs = [float(r["high"]) for r in recent_20 if r.get("high")]
                all_lows = [float(r["low"]) for r in sym_rows if r.get("low")]
                all_highs = [float(r["high"]) for r in sym_rows if r.get("high")]
                s1 = _safe_price(min(recent_lows)) if recent_lows else None
                r1 = _safe_price(max(recent_highs)) if recent_highs else None
                s2 = _safe_price(min(all_lows)) if all_lows else (_safe_price(s1 * 0.96) if s1 else None)
                r2 = _safe_price(max(all_highs)) if all_highs else (_safe_price(r1 * 1.05) if r1 else None)
                levels_map[s_sym] = {
                    "support_1": s1,
                    "resistance_1": r1,
                    "support_2": s2,
                    "resistance_2": r2,
                    "stop_loss": _safe_price(s1 * 0.98) if s1 else None,
                    "entry_zone": f"{s1} – {_safe_price(s1 * 1.02)}" if s1 else "غير محدد",
                }
        except Exception:
            pass

        # Batch-fetch stocks, latest technical indicators, wyckoff scans, and fundamentals in 4 queries (vs 4*N sequential)
        stocks_meta_map: Dict[str, Dict[str, Any]] = {}
        try:
            res_stocks_batch = (
                sb.from_("stocks")
                .select("symbol,name,name_ar")
                .in_("symbol", egx_syms)
                .limit(len(egx_syms) + 5)
                .execute()
            )
            for row in (res_stocks_batch.data or []):
                if isinstance(row, dict) and row.get("symbol"):
                    stocks_meta_map[str(row["symbol"]).upper()] = row
        except Exception:
            pass

        tech_map: Dict[str, Dict[str, Any]] = {}
        try:
            res_tech_batch = (
                sb.from_("stock_technical_indicators")
                .select(
                    "symbol,date,close,change_pct,volume,r_vol,rsi_14,macd,macd_signal,macd_histogram,"
                    "bb_upper,bb_lower,ema_50,ema_200,vwap_20,king_ai_score,egx_ai_score"
                )
                .eq("exchange", "EGX")
                .in_("symbol", egx_syms)
                .order("date", desc=True)
                .limit(max(len(egx_syms) * 3, 30))
                .execute()
            )
            for row in (res_tech_batch.data or []):
                if isinstance(row, dict) and row.get("symbol"):
                    s_k = str(row["symbol"]).upper()
                    if s_k not in tech_map:
                        tech_map[s_k] = row
        except Exception:
            pass

        wyckoff_map: Dict[str, Dict[str, Any]] = {}
        try:
            res_wyck_batch = (
                sb.from_("stock_scans_summary")
                .select("symbol,scan_date,acc_score,dist_score,wyckoff_phase,vol_ratio,signal,consecutive_acc_days,consecutive_dist_days")
                .in_("symbol", egx_syms)
                .order("scan_date", desc=True)
                .limit(max(len(egx_syms) * 3, 30))
                .execute()
            )
            for row in (res_wyck_batch.data or []):
                if isinstance(row, dict) and row.get("symbol"):
                    s_k = str(row["symbol"]).upper()
                    if s_k not in wyckoff_map:
                        wyckoff_map[s_k] = row
        except Exception:
            pass

        fund_map: Dict[str, Dict[str, Any]] = {}
        fund_score_map: Dict[str, Any] = {}
        try:
            res_fund_batch = (
                sb.from_("stock_fundamentals")
                .select("symbol,data,fund_score")
                .eq("exchange", "EGX")
                .in_("symbol", egx_syms)
                .limit(len(egx_syms) + 5)
                .execute()
            )
            for row in (res_fund_batch.data or []):
                if isinstance(row, dict) and row.get("symbol"):
                    s_k = str(row["symbol"]).upper()
                    if isinstance(row.get("data"), dict):
                        fund_map[s_k] = row["data"]
                    if row.get("fund_score") is not None:
                        fund_score_map[s_k] = row.get("fund_score")
        except Exception:
            pass

        rec_by_sym: Dict[str, Dict[str, Any]] = {}
        if egx_syms and _ALLOW_RECOMMENDATIONS_CTX.get():
            try:
                res_rec_batch = (
                    sb.from_("scan_results")
                    .select("symbol,signal,entry_price,target_price,stop_loss,status,created_at")
                    .eq("exchange", "EGX")
                    .in_("symbol", egx_syms)
                    .in_("status", ["open", "active"])
                    .order("created_at", desc=True)
                    .limit(max(len(egx_syms) * 2, 10))
                    .execute()
                )
                for row in (res_rec_batch.data or []):
                    if isinstance(row, dict) and row.get("symbol"):
                        s_k = str(row["symbol"]).upper()
                        if s_k not in rec_by_sym:
                            rec_by_sym[s_k] = row
            except Exception:
                pass

        for sym in egx_syms:
            meta_row = stocks_meta_map.get(sym, {})
            stock_name_ar = meta_row.get("name_ar") or _alias_name_for_symbol(sym, market="EGX")
            stock_name_en = meta_row.get("name") or sym

            if stock_name_ar:
                stock_name_ar = stock_name_ar.split(",")[0].strip()

            latest_tech = tech_map.get(sym, {})
            wyckoff_info = wyckoff_map.get(sym, {})

            close_price = _safe_price(latest_tech.get("close"))
            bb_low = _safe_price(latest_tech.get("bb_lower"))
            bb_up = _safe_price(latest_tech.get("bb_upper"))
            ema_50, ema_200, split_factor, split_adjusted_ema = _detect_and_adjust_price_split(
                by_sym.get(sym) or [],
                _safe_price(latest_tech.get("ema_50")),
                _safe_price(latest_tech.get("ema_200")),
                close_price,
            )

            fundamentals: Dict[str, Any] = {}
            fd = fund_map.get(sym)
            if isinstance(fd, dict):
                if stock_name_en == sym and fd.get("name"):
                    stock_name_en = str(fd["name"]).split(",")[0].strip()
                fundamentals = _extract_rich_fundamentals(
                    fd,
                    fund_score=fund_score_map.get(sym),
                    close_price=close_price,
                    name=stock_name_en,
                    trade_currency=_reg_currency_for_symbol(sym, "EGX"),
                    split_factor=split_factor,
                )

            change_pct = _safe_float(latest_tech.get("change_pct"))
            sharia = is_sharia_compliant(sym)

            king_score = _normalize_king_ai_score(latest_tech.get("king_ai_score"))
            acc_score = _safe_float(wyckoff_info.get("acc_score"))
            rsi = _safe_float(latest_tech.get("rsi_14"))

            vwap_20 = _safe_price(latest_tech.get("vwap_20"))
            macd_hist = _safe_float(latest_tech.get("macd_histogram"), 4)
            dist_score = _safe_float(wyckoff_info.get("dist_score"))

            lvl = levels_map.get(sym, {})
            support_1 = lvl.get("support_1") or (bb_low if bb_low else (_safe_price(close_price * 0.96) if close_price else None))
            resistance_1 = lvl.get("resistance_1") or (bb_up if bb_up else (_safe_price(close_price * 1.05) if close_price else None))
            support_2, resistance_2 = _distinct_secondary_levels(
                support_1,
                lvl.get("support_2"),
                resistance_1,
                lvl.get("resistance_2"),
                bb_low=bb_low,
                bb_up=bb_up,
            )
            stop_loss = lvl.get("stop_loss") or (_safe_price(support_1 * 0.98) if support_1 else None)
            entry_zone = lvl.get("entry_zone") or (f"{support_1} – {_safe_price(support_1 * 1.02)}" if support_1 else "غير محدد")

            verdict = _compute_stock_verdict(
                close=close_price,
                change_pct=change_pct,
                rsi=rsi,
                macd_hist=macd_hist,
                ema_50=ema_50,
                ema_200=ema_200,
                acc_score=acc_score,
                dist_score=dist_score,
            )
            ctx_metrics = _compute_stock_context_metrics(
                close=close_price,
                ema_50=ema_50,
                ema_200=ema_200,
                vwap_20=vwap_20,
                support_1=support_1,
                resistance_1=resistance_1,
                stop_loss=stop_loss,
            )

            sym_prices_egx = by_sym.get(sym, []) if "by_sym" in locals() else []
            rv_info = resolve_intraday_r_vol(
                _safe_float(latest_tech.get("r_vol")),
                latest_tech.get("date"),
                exchange="EGX",
                ohlcv_rows=sym_prices_egx,
            )

            sym_currency = _reg_currency_for_symbol(sym, "EGX")
            egx_item: Dict[str, Any] = {
                "symbol": sym,
                "market": "EGX",
                "exchange": "EGX",
                "currency": sym_currency,
                "name_ar": stock_name_ar or sym,
                "name": stock_name_en,
                "is_sharia_compliant": sharia,
                "sharia_index": "EGX33" if sharia else None,
                "date": latest_tech.get("date"),
                "close": close_price,
                "change_pct": change_pct,
                "rsi_14": rsi,
                "macd": _safe_float(latest_tech.get("macd"), 4),
                "macd_signal": _safe_float(latest_tech.get("macd_signal"), 4),
                "macd_histogram": macd_hist,
                "ema_50": ema_50,
                "ema_200": ema_200,
                "vwap_20": vwap_20,
                "bb_upper": bb_up,
                "bb_lower": bb_low,
                "r_vol": rv_info["effective_r_vol"],
                **(
                    {
                        "r_vol_raw": rv_info["raw_r_vol"],
                        "r_vol_mode": rv_info["r_vol_mode"],
                        "r_vol_note_ar": rv_info["r_vol_note_ar"],
                    }
                    if rv_info["is_intraday_adjusted"]
                    else {}
                ),
                "volume": latest_tech.get("volume"),
                "support_1": support_1,
                "resistance_1": resistance_1,
                "support_2": support_2,
                "resistance_2": resistance_2,
                "stop_loss": stop_loss,
                "entry_zone": entry_zone,
                "king_ai_score": king_score,
                "egx_ai_score": _safe_float(latest_tech.get("egx_ai_score")),
                "wyckoff_phase": wyckoff_info.get("wyckoff_phase"),
                "scan_signal": wyckoff_info.get("signal"),
                "accumulation_score": acc_score,
                "distribution_score": dist_score,
                "consecutive_acc_days": wyckoff_info.get("consecutive_acc_days"),
                "verdict": verdict,
                "has_active_recommendation": sym in rec_by_sym,
                **(
                    {
                        "active_recommendation": {
                            "signal": rec_by_sym[sym].get("signal"),
                            "entry_price": _safe_price(rec_by_sym[sym].get("entry_price")),
                            "target_price": _safe_price(rec_by_sym[sym].get("target_price")),
                            "stop_loss": _safe_price(rec_by_sym[sym].get("stop_loss")),
                            "signal_date": str(rec_by_sym[sym].get("created_at") or "")[:10],
                        }
                    }
                    if sym in rec_by_sym
                    else {}
                ),
                **ctx_metrics,
                **fundamentals,
            }
            if split_adjusted_ema:
                egx_item["split_adjusted_ema"] = True
            up_div = _lookup_upcoming_dividend(sym, "EGX")
            if up_div:
                egx_item["upcoming_dividend"] = up_div
            # Flag stale / suspended stock quotes (> 10 days old) so ARTORO warns transparently
            _raw_dt = str(latest_tech.get("date") or "")[:10]
            if len(_raw_dt) == 10:
                try:
                    _age_days = (datetime.now(CAIRO_TZ).date() - datetime.strptime(_raw_dt, "%Y-%m-%d").date()).days
                    if _age_days > 10:
                        egx_item["data_is_stale"] = True
                        egx_item["data_age_days"] = _age_days
                        egx_item["stale_data_warning"] = (
                            f"⚠️ تنبيه شفافية مهم: آخر جلسة مسجلة لسهم {sym} في قاعدة البيانات بتاريخ {_raw_dt} "
                            f"(منذ {_age_days} يوماً) — قد يكون السهم موقوفاً عن التداول أو غير محدث من مزود البيانات، "
                            "فلا تعتمد هذا السعر كإغلاق حالي."
                        )
                except Exception:
                    pass
            ui_chart = _build_ui_chart_payload(
                by_sym.get(sym, []) if "by_sym" in locals() else [],
                ema_50,
                support_1,
                resistance_1,
                currency=sym_currency,
            )
            if ui_chart:
                egx_item["_ui_chart"] = ui_chart
            if total_requested_syms <= 4 and close_price and close_price > 0:
                try:
                    from api.agentic_chat.quant_engine import build_quant_intelligence_for_stock
                    fv_est, fv_model_est, fv_extra_est = _compute_fundamental_fair_value(
                        close_price,
                        vwap_20 or close_price,
                        ema_50 or close_price,
                        fd if isinstance(fd, dict) else None,
                        market="EGX",
                        split_factor=split_factor,
                        symbol=sym,
                        ema_200=ema_200,
                    )
                    eps_val = _safe_float(fundamentals.get("eps"), 4)
                    ni_val = _safe_float(fundamentals.get("net_income"), 2)
                    roe_val = _safe_float(fundamentals.get("roe_pct"))
                    loss_flag = bool(
                        (eps_val is not None and eps_val < 0)
                        or (ni_val is not None and ni_val < 0)
                        or (roe_val is not None and roe_val < 0)
                        or fv_extra_est.get("is_loss_making")
                    )
                    fv_gap_egx = _build_fair_value_gap(close_price, fv_est, is_loss_making=loss_flag)
                    egx_item["fair_value"] = fv_est
                    egx_item["fair_value_model"] = fv_model_est
                    egx_item["valuation_upside_pct"] = fv_gap_egx["upside_pct"]
                    egx_item["valuation_gap_ar"] = fv_gap_egx["valuation_gap_ar"]
                    if fv_extra_est.get("graham_value"):
                        egx_item["graham_value"] = fv_extra_est["graham_value"]
                        egx_item["graham_gap_ar"] = _build_graham_gap_ar(close_price, fv_extra_est.get("graham_value"))
                    qi = build_quant_intelligence_for_stock(
                        symbol=sym,
                        exchange="EGX",
                        currency=sym_currency,
                        close=close_price,
                        rsi_14=rsi,
                        macd_histogram=macd_hist,
                        ema_50=ema_50,
                        ema_200=ema_200,
                        vwap_20=vwap_20,
                        r_vol=rv_info["effective_r_vol"],
                        r_vol_mode=rv_info["r_vol_mode"],
                        support_1=support_1,
                        resistance_1=resistance_1,
                        stop_loss=stop_loss,
                        tactical_stop_loss=ctx_metrics.get("tactical_stop_loss"),
                        support_1_is_distant=bool(ctx_metrics.get("support_1_is_distant")),
                        acc_score=acc_score,
                        dist_score=dist_score,
                        king_ai_score=king_score,
                        fair_value=fv_est,
                        valuation_upside_pct=fv_gap_egx["upside_pct"],
                        fund_score=fundamentals.get("fund_score"),
                        roe=fundamentals.get("roe_pct"),
                        pe_ratio=fundamentals.get("pe_ratio"),
                        debt_to_equity=fundamentals.get("debt_to_equity"),
                        is_loss_making=loss_flag,
                        is_sharia_compliant=sharia,
                        ohlcv_rows=by_sym.get(sym, []) if "by_sym" in locals() else [],
                        last_date=_raw_dt,
                    )
                    if qi:
                        egx_item["quant_intelligence"] = qi
                except Exception as qi_err:
                    logger.debug(f"[get_stock] quant_engine skipped for {sym}: {qi_err}")
            stocks_data.append(egx_item)

    # ── 2. Unified Non-EGX Exchanges (TADAWUL/TASI, QSE, DFM, ADX, KSE, and any future exchange) ─
    for exch_code, exch_syms in non_egx_groups.items():
        cfg = _reg_get_market_config(exch_code)
        sb_sa = _get_sb_for_market(exch_code)
        if sb_sa is None:
            if not egx_syms and len(non_egx_groups) == 1:
                return _market_unconfigured_error(exch_code)
            errors.append(f"بيانات {cfg.name_ar} ({cfg.ui_code}) غير مهيأة حالياً.")
        else:
            sa_meta_map: Dict[str, Dict[str, Any]] = {}
            idx_code = cfg.index_name.upper()
            equity_syms = [s for s in exch_syms if s.upper() != idx_code]

            # Handle benchmark index if explicitly asked via get_stock (e.g. TASI, QSI, DFMGI)
            if any(s.upper() == idx_code for s in exch_syms):
                try:
                    c0 = chg_idx = m_idx_date = idx_source = None
                    res_idx = (
                        sb_sa.from_("market_index")
                        .select("date,close,ret,source")
                        .eq("exchange", exch_code)
                        .order("date", desc=True)
                        .limit(2)
                        .execute()
                    )
                    idx_rows = res_idx.data or []
                    if idx_rows:
                        c0 = _safe_float(idx_rows[0].get("close"))
                        m_idx_date = idx_rows[0].get("date")
                        idx_source = idx_rows[0].get("source")
                        ret0 = _safe_float(idx_rows[0].get("ret"), 4)
                        chg_idx = round(ret0 * 100, 2) if ret0 is not None else None
                        if chg_idx is None and len(idx_rows) >= 2:
                            c1 = _safe_float(idx_rows[1].get("close"))
                            if c1 and c0:
                                chg_idx = round((c0 - c1) / c1 * 100, 2)

                    if c0 is None and cfg.market_cache_key and (_get_saudi_table_columns("market_cache", sb_sa) is not None or not _is_real_saudi_sb(sb_sa)):
                        try:
                            res_mc = (
                                sb_sa.from_("market_cache")
                                .select("payload")
                                .eq("cache_key", cfg.market_cache_key)
                                .limit(1)
                                .execute()
                            )
                            if res_mc.data and isinstance(res_mc.data[0].get("payload"), dict):
                                pl = res_mc.data[0]["payload"]
                                c0 = _safe_float(pl.get("tasi_close") or pl.get("index_close") or pl.get("close"))
                                chg_idx = _safe_float(pl.get("tasi_change_pct") or pl.get("index_change_pct") or pl.get("change_pct"))
                                m_idx_date = pl.get("date") or m_idx_date
                                idx_source = pl.get("source") or "market_cache"
                        except Exception:
                            pass

                    if c0 is not None:
                        tasi_entry: Dict[str, Any] = {
                            "symbol": cfg.index_name,
                            "market": cfg.ui_code,
                            "exchange": exch_code,
                            "currency": "نقطة",
                            "name_ar": f"مؤشر {cfg.name_ar} ({cfg.index_name})",
                            "name": f"{cfg.name_en} Index ({cfg.index_name})",
                            "is_sharia_compliant": None,
                            "sharia_index": None,
                            "date": m_idx_date,
                            "close": c0,
                            "change_pct": chg_idx,
                            "index_source": idx_source,
                            "verdict": f"🟡 مؤشر السوق العام — استخدم get_market('{cfg.ui_code}') لمزيد من التفاصيل",
                        }
                        if idx_source == "equal_weight":
                            tasi_entry["index_type"] = "equal_weight_composite"
                            tasi_entry["index_note"] = f"مؤشر {cfg.name_ar} المركب متساوي الأوزان (سنة الأساس = 1000)"
                        stocks_data.append(tasi_entry)
                except Exception:
                    pass

            if equity_syms:
                sa_fund_map: Dict[str, Dict[str, Any]] = {}
                sa_ti_map: Dict[str, Dict[str, Any]] = {}
                mkt_rec_by_sym: Dict[str, Dict[str, Any]] = {}
                sa_ohlcv_map: Dict[str, List[Dict[str, Any]]] = {}

                def _q_st() -> Dict[str, Dict[str, Any]]:
                    out_m: Dict[str, Dict[str, Any]] = {}
                    try:
                        res_st = (
                            sb_sa.from_("stocks")
                            .select("symbol,name,name_ar,sector,industry,currency")
                            .eq("exchange", exch_code)
                            .in_("symbol", equity_syms)
                            .limit(len(equity_syms))
                            .execute()
                        )
                        for r in (res_st.data or []):
                            if r.get("symbol"):
                                out_m[r["symbol"]] = r
                    except Exception:
                        pass
                    return out_m

                def _q_sf() -> Dict[str, Dict[str, Any]]:
                    out_m: Dict[str, Dict[str, Any]] = {}
                    try:
                        res_sf = (
                            sb_sa.from_("stock_fundamentals")
                            .select("symbol,data,fund_score")
                            .eq("exchange", exch_code)
                            .in_("symbol", equity_syms)
                            .limit(len(equity_syms))
                            .execute()
                        )
                        for r in (res_sf.data or []):
                            if r.get("symbol"):
                                out_m[r["symbol"]] = r
                    except Exception:
                        pass
                    return out_m

                def _q_ti() -> Dict[str, Dict[str, Any]]:
                    out_m: Dict[str, Dict[str, Any]] = {}
                    try:
                        ti_cols, order_col = _saudi_ti_select_and_order(sb_sa)
                        res_sti = (
                            sb_sa.from_("stock_technical_indicators")
                            .select(ti_cols)
                            .eq("exchange", exch_code)
                            .in_("symbol", equity_syms)
                            .order(order_col, desc=True)
                            .limit(len(equity_syms) * 2)
                            .execute()
                        )
                        for r in (res_sti.data or []):
                            s_sym = r.get("symbol")
                            if s_sym and s_sym not in out_m:
                                out_m[s_sym] = r
                    except Exception:
                        pass
                    return out_m

                def _q_rec() -> Dict[str, Dict[str, Any]]:
                    out_m: Dict[str, Dict[str, Any]] = {}
                    if not allow_recs:
                        return out_m
                    try:
                        res_mrec = (
                            sb_sa.from_("scan_results")
                            .select("symbol,signal,entry_price,target_price,stop_loss,status,created_at")
                            .eq("exchange", exch_code)
                            .in_("symbol", equity_syms)
                            .in_("status", ["open", "active"])
                            .order("created_at", desc=True)
                            .limit(max(len(equity_syms) * 2, 10))
                            .execute()
                        )
                        for row in (res_mrec.data or []):
                            if isinstance(row, dict) and row.get("symbol"):
                                s_k = str(row["symbol"]).upper()
                                if s_k not in out_m:
                                    out_m[s_k] = row
                    except Exception:
                        pass
                    return out_m

                def _q_ohlcv() -> Dict[str, List[Dict[str, Any]]]:
                    try:
                        return _fetch_saudi_ohlcv_for_symbols(sb_sa, equity_syms, exchange=exch_code)
                    except Exception:
                        return {}

                from concurrent.futures import ThreadPoolExecutor as _TPE
                with _TPE(max_workers=5) as _pool:
                    f_st = _pool.submit(_q_st)
                    f_sf = _pool.submit(_q_sf)
                    f_ti = _pool.submit(_q_ti)
                    f_rec = _pool.submit(_q_rec)
                    f_oh = _pool.submit(_q_ohlcv)
                    sa_meta_map = f_st.result()
                    sa_fund_map = f_sf.result()
                    sa_ti_map = f_ti.result()
                    mkt_rec_by_sym = f_rec.result()
                    sa_ohlcv_map = f_oh.result()

                for sym in equity_syms:
                    meta = sa_meta_map.get(sym, {})
                    raw_fund = sa_fund_map.get(sym, {})
                    fd = raw_fund.get("data") if isinstance(raw_fund.get("data"), dict) else {}

                    stock_name_ar = meta.get("name_ar") or _alias_name_for_symbol(sym, market=exch_code)
                    if stock_name_ar:
                        stock_name_ar = str(stock_name_ar).split(",")[0].strip()
                    stock_name_en = meta.get("name") or (str(fd.get("name")).split(",")[0].strip() if fd.get("name") else sym)

                    db_ti = sa_ti_map.get(sym, {})
                    calc_ti = _compute_indicators_from_price_rows(sa_ohlcv_map.get(sym, []))

                    # Prefer DB indicator value if present, seamlessly backfill from computed OHLCV
                    close_price = _safe_price(db_ti.get("close")) or calc_ti.get("close")
                    change_pct = _safe_float(db_ti.get("change_pct"))
                    if change_pct is None:
                        change_pct = calc_ti.get("change_pct")

                    vol_val = db_ti.get("volume") if db_ti.get("volume") is not None else calc_ti.get("volume")
                    vol_sma = db_ti.get("vol_sma20") or db_ti.get("volume_sma_20") or calc_ti.get("vol_sma20")
                    r_vol = _safe_float(db_ti.get("r_vol"))
                    if r_vol is None and vol_val and vol_sma and float(vol_sma) > 0:
                        r_vol = _safe_float(float(vol_val) / float(vol_sma))
                    if r_vol is None:
                        r_vol = calc_ti.get("r_vol")

                    rsi = _safe_float(db_ti.get("rsi_14"))
                    if rsi is None:
                        rsi = calc_ti.get("rsi_14")

                    macd_v = _safe_float(db_ti.get("macd"), 4)
                    if macd_v is None:
                        macd_v = calc_ti.get("macd")
                    macd_s = _safe_float(db_ti.get("macd_signal"), 4)
                    if macd_s is None:
                        macd_s = calc_ti.get("macd_signal")
                    macd_h = _safe_float(db_ti.get("macd_histogram"), 4)
                    if macd_h is None:
                        macd_h = calc_ti.get("macd_histogram")

                    ema_20 = _safe_price(db_ti.get("ema_20")) or calc_ti.get("ema_20")
                    ema_50 = _safe_price(db_ti.get("ema_50")) or calc_ti.get("ema_50")
                    ema_200 = _safe_price(db_ti.get("ema_200")) or calc_ti.get("ema_200")
                    vwap_20 = _safe_price(db_ti.get("vwap_20")) or calc_ti.get("vwap_20")
                    bb_low = _safe_price(db_ti.get("bb_lower")) or calc_ti.get("bb_lower")
                    bb_up = _safe_price(db_ti.get("bb_upper")) or calc_ti.get("bb_upper")

                    support_1 = calc_ti.get("support_1") or (bb_low if bb_low else (_safe_price(close_price * 0.96) if close_price else None))
                    resistance_1 = calc_ti.get("resistance_1") or (bb_up if bb_up else (_safe_price(close_price * 1.05) if close_price else None))
                    support_2, resistance_2 = _distinct_secondary_levels(
                        support_1,
                        calc_ti.get("support_2"),
                        resistance_1,
                        calc_ti.get("resistance_2"),
                        bb_low=bb_low,
                        bb_up=bb_up,
                    )
                    stop_loss = calc_ti.get("stop_loss") or (_safe_price(support_1 * 0.98) if support_1 else None)
                    entry_zone = calc_ti.get("entry_zone") or (f"{support_1} – {_safe_price(support_1 * 1.02)}" if support_1 else "غير محدد")

                    king_score = _normalize_king_ai_score(db_ti.get("king_ai_score"))
                    if king_score is None:
                        king_score = _normalize_king_ai_score(calc_ti.get("king_ai_score"))

                    ti_date = db_ti.get("date") or calc_ti.get("date") or (
                        str(db_ti.get("updated_at"))[:10] if db_ti.get("updated_at") else None
                    )
                    rv_info_sa = resolve_intraday_r_vol(
                        r_vol,
                        ti_date,
                        exchange=exch_code,
                        ohlcv_rows=sa_ohlcv_map.get(sym, []),
                    )

                    verdict = _compute_stock_verdict(
                        close=close_price,
                        change_pct=change_pct,
                        rsi=rsi,
                        macd_hist=macd_h,
                        ema_50=ema_50,
                        ema_200=ema_200,
                    )
                    ctx_metrics_sa = _compute_stock_context_metrics(
                        close=close_price,
                        ema_50=ema_50,
                        ema_200=ema_200,
                        vwap_20=vwap_20,
                        support_1=support_1,
                        resistance_1=resistance_1,
                        stop_loss=stop_loss,
                    )

                    sharia_sa = fd.get("is_sharia_compliant")
                    if sharia_sa is not None:
                        sharia_sa = bool(sharia_sa)

                    sym_u = str(sym).upper()
                    item_currency = cfg.currency_ar or meta.get("currency") or cfg.currency_code
                    sa_item: Dict[str, Any] = {
                        "symbol": sym,
                        "market": cfg.ui_code,
                        "exchange": exch_code,
                        "currency": item_currency,
                        "name_ar": stock_name_ar or stock_name_en or sym,
                        "name": stock_name_en,
                        "sector": meta.get("sector") or fd.get("sector"),
                        "is_sharia_compliant": sharia_sa,
                        "sharia_index": cfg.sharia_index if sharia_sa else None,
                        "date": ti_date,
                        "close": close_price,
                        "change_pct": change_pct,
                        "rsi_14": rsi,
                        "macd": macd_v,
                        "macd_signal": macd_s,
                        "macd_histogram": macd_h,
                        "ema_20": ema_20,
                        "ema_50": ema_50,
                        "ema_200": ema_200,
                        "vwap_20": vwap_20,
                        "bb_upper": bb_up,
                        "bb_lower": bb_low,
                        "r_vol": rv_info_sa["effective_r_vol"],
                        **(
                            {
                                "r_vol_raw": rv_info_sa["raw_r_vol"],
                                "r_vol_mode": rv_info_sa["r_vol_mode"],
                                "r_vol_note_ar": rv_info_sa["r_vol_note_ar"],
                            }
                            if rv_info_sa["is_intraday_adjusted"]
                            else {}
                        ),
                        "volume": vol_val,
                        "cmf_20": _safe_float(db_ti.get("cmf_20"), 3) or calc_ti.get("cmf_20"),
                        "support_1": support_1,
                        "resistance_1": resistance_1,
                        "support_2": support_2,
                        "resistance_2": resistance_2,
                        "stop_loss": stop_loss,
                        "entry_zone": entry_zone,
                        "king_ai_score": king_score,
                        **_extract_rich_fundamentals(
                            fd,
                            fund_score=raw_fund.get("fund_score"),
                            close_price=close_price,
                            name=stock_name_en,
                        ),
                        "verdict": verdict,
                        "has_active_recommendation": sym_u in mkt_rec_by_sym,
                        **(
                            {
                                "active_recommendation": {
                                    "signal": mkt_rec_by_sym[sym_u].get("signal"),
                                    "entry_price": _safe_price(mkt_rec_by_sym[sym_u].get("entry_price")),
                                    "target_price": _safe_price(mkt_rec_by_sym[sym_u].get("target_price")),
                                    "stop_loss": _safe_price(mkt_rec_by_sym[sym_u].get("stop_loss")),
                                    "signal_date": str(mkt_rec_by_sym[sym_u].get("created_at") or "")[:10],
                                }
                            }
                            if sym_u in mkt_rec_by_sym
                            else {}
                        ),
                        **ctx_metrics_sa,
                    }
                    up_div_sa = _lookup_upcoming_dividend(sym, exch_code)
                    if up_div_sa:
                        sa_item["upcoming_dividend"] = up_div_sa
                    # Flag stale / suspended quotes (> 10 days old) across GCC markets as well
                    _raw_sa_dt = str(ti_date or "")[:10]
                    if len(_raw_sa_dt) == 10:
                        try:
                            _sa_age_days = (datetime.now(CAIRO_TZ).date() - datetime.strptime(_raw_sa_dt, "%Y-%m-%d").date()).days
                            if _sa_age_days > 10:
                                sa_item["data_is_stale"] = True
                                sa_item["data_age_days"] = _sa_age_days
                                sa_item["stale_data_warning"] = (
                                    f"⚠️ تنبيه شفافية مهم: آخر جلسة مسجلة لسهم {sym} في قاعدة البيانات بتاريخ {_raw_sa_dt} "
                                    f"(منذ {_sa_age_days} يوماً) — قد يكون السهم موقوفاً عن التداول أو غير محدث من مزود البيانات، "
                                    "فلا تعتمد هذا السعر كإغلاق حالي."
                                )
                        except Exception:
                            pass
                    ui_chart_sa = _build_ui_chart_payload(
                        sa_ohlcv_map.get(sym, []),
                        ema_50,
                        support_1,
                        resistance_1,
                        currency=cfg.currency_ar,
                    )
                    if ui_chart_sa:
                        sa_item["_ui_chart"] = ui_chart_sa
                    if total_requested_syms <= 4 and close_price and close_price > 0:
                        try:
                            from api.agentic_chat.quant_engine import build_quant_intelligence_for_stock
                            fv_sa, fv_model_sa, fv_extra_sa = _compute_fundamental_fair_value(
                                close_price,
                                vwap_20 or close_price,
                                ema_50 or close_price,
                                fd if isinstance(fd, dict) else None,
                                market=exch_code,
                                symbol=sym,
                                ema_200=ema_200,
                            )
                            eps_sa = _safe_float(sa_item.get("eps"), 4)
                            ni_sa = _safe_float(sa_item.get("net_income"), 2)
                            roe_sa = _safe_float(sa_item.get("roe_pct"))
                            loss_sa = bool(
                                (eps_sa is not None and eps_sa < 0)
                                or (ni_sa is not None and ni_sa < 0)
                                or (roe_sa is not None and roe_sa < 0)
                                or fv_extra_sa.get("is_loss_making")
                            )
                            fv_gap_sa = _build_fair_value_gap(close_price, fv_sa, is_loss_making=loss_sa)
                            sa_item["fair_value"] = fv_sa
                            sa_item["fair_value_model"] = fv_model_sa
                            sa_item["valuation_upside_pct"] = fv_gap_sa["upside_pct"]
                            sa_item["valuation_gap_ar"] = fv_gap_sa["valuation_gap_ar"]
                            if fv_extra_sa.get("graham_value"):
                                sa_item["graham_value"] = fv_extra_sa["graham_value"]
                                sa_item["graham_gap_ar"] = _build_graham_gap_ar(close_price, fv_extra_sa.get("graham_value"))
                            qi_sa = build_quant_intelligence_for_stock(
                                symbol=sym,
                                exchange=exch_code,
                                currency=item_currency,
                                close=close_price,
                                rsi_14=rsi,
                                macd_histogram=macd_h,
                                ema_50=ema_50,
                                ema_200=ema_200,
                                vwap_20=vwap_20,
                                r_vol=rv_info_sa["effective_r_vol"],
                                r_vol_mode=rv_info_sa["r_vol_mode"],
                                support_1=support_1,
                                resistance_1=resistance_1,
                                stop_loss=stop_loss,
                                tactical_stop_loss=ctx_metrics_sa.get("tactical_stop_loss"),
                                support_1_is_distant=bool(ctx_metrics_sa.get("support_1_is_distant")),
                                king_ai_score=king_score,
                                fair_value=fv_sa,
                                valuation_upside_pct=fv_gap_sa["upside_pct"],
                                fund_score=sa_item.get("fund_score"),
                                roe=sa_item.get("roe_pct"),
                                pe_ratio=sa_item.get("pe_ratio"),
                                debt_to_equity=sa_item.get("debt_to_equity"),
                                is_loss_making=loss_sa,
                                is_sharia_compliant=sharia_sa,
                                ohlcv_rows=sa_ohlcv_map.get(sym, []),
                                last_date=_raw_sa_dt,
                            )
                            if qi_sa:
                                sa_item["quant_intelligence"] = qi_sa
                        except Exception as qi_sa_err:
                            logger.debug(f"[get_stock] quant_engine skipped for {sym} ({exch_code}): {qi_sa_err}")
                    stocks_data.append(sa_item)

    # If any requested symbol had no price/indicator data, suggest closest real DB matches in the user's market
    eff_mkt_for_lookup = _normalize_market_code(market or _ACTIVE_MARKET_CTX.get() or "EGX")
    suggested_map: Dict[str, List[Dict[str, str]]] = {}
    for row in stocks_data:
        if row.get("close") is None:
            q_sym = str(row.get("symbol") or "").strip()
            if q_sym:
                row_mkt = _normalize_market_code(row.get("exchange") or eff_mkt_for_lookup)
                cands = _search_catalog_candidates(q_sym, exchange=row_mkt, limit=4)
                if cands:
                    row["suggested_matches"] = cands
                    suggested_map[q_sym] = cands

    res: Dict[str, Any] = {"status": "success", "stocks": stocks_data}
    if errors:
        res["warnings"] = errors
    if suggested_map:
        res["suggested_matches"] = suggested_map
    _set_tool_cached(cache_key, res)
    return res


async def execute_get_stock(symbols: List[str], market: Optional[str] = None) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_stock, symbols, market)


# ---------------------------------------------------------------------------
# Tool: get_stock_levels
# ---------------------------------------------------------------------------
def _sync_get_stock_levels_for_market(
    sb: Any,
    syms: List[str],
    exchange_code: str,
    allow_recommendations: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    eff_allow_recs = _ALLOW_RECOMMENDATIONS_CTX.get() if allow_recommendations is None else bool(allow_recommendations)
    ui_mkt = _ui_market_label(exchange_code)
    currency = _currency_for_market(exchange_code)
    levels: List[Dict[str, Any]] = []

    # Batch-fetch price history, indicators, fundamentals & open recs for all symbols
    rows_by_sym: Dict[str, List[Dict[str, Any]]] = {}
    if syms:
        try:
            res_p = (
                sb.from_("stock_prices")
                .select("symbol,high,low,close,volume,date")
                .eq("exchange", exchange_code)
                .in_("symbol", syms)
                .order("date", desc=True)
                .limit(min(max(len(syms) * 120, 120), 2400))
                .execute()
            )
            for r in (res_p.data or []):
                s_k = str(r.get("symbol") or "").upper()
                if s_k:
                    lst = rows_by_sym.setdefault(s_k, [])
                    if len(lst) < 120:
                        lst.append(r)
        except Exception:
            pass
        if exchange_code != "EGX":
            _backfill_saudi_ohlcv_from_storage(sb, exchange_code, rows_by_sym, syms, 120)

    ti_by_sym: Dict[str, Dict[str, Any]] = {}
    if syms:
        try:
            ti_cols = (
                "symbol,ema_50,ema_200,vwap_20,rsi_14,r_vol,king_ai_score"
                if exchange_code == "EGX"
                else "symbol,ema_50,ema_200,vwap_20,rsi_14,r_vol"
            )
            res_ti = (
                sb.from_("stock_technical_indicators")
                .select(ti_cols)
                .eq("exchange", exchange_code)
                .in_("symbol", syms)
                .order("date", desc=True)
                .limit(max(len(syms) * 3, 20))
                .execute()
            )
            for r in (res_ti.data or []):
                s_k = str(r.get("symbol") or "").upper()
                if s_k and s_k not in ti_by_sym:
                    ti_by_sym[s_k] = r
        except Exception:
            pass

    fund_lv_by_sym: Dict[str, Dict[str, Any]] = {}
    if syms:
        try:
            res_fl = (
                sb.from_("stock_fundamentals")
                .select("symbol,fund_score,data")
                .eq("exchange", exchange_code)
                .in_("symbol", syms)
                .limit(len(syms) + 5)
                .execute()
            )
            for r in (res_fl.data or []):
                s_k = str(r.get("symbol") or "").upper()
                if s_k and s_k not in fund_lv_by_sym:
                    fund_lv_by_sym[s_k] = r
        except Exception:
            pass

    rec_by_sym: Dict[str, Dict[str, Any]] = {}
    if syms and eff_allow_recs:
        try:
            res_rec = (
                sb.from_("scan_results")
                .select("symbol,signal,entry_price,target_price,stop_loss,status,created_at")
                .eq("exchange", exchange_code)
                .in_("symbol", syms)
                .in_("status", ["open", "active"])
                .order("created_at", desc=True)
                .limit(max(len(syms) * 2, 20))
                .execute()
            )
            for r in (res_rec.data or []):
                s_k = str(r.get("symbol") or "").upper()
                if s_k and s_k not in rec_by_sym:
                    rec_by_sym[s_k] = r
        except Exception:
            pass

    for sym in syms:
        rows = rows_by_sym.get(sym, [])

        if not rows:
            levels.append({
                "symbol": sym,
                "market": ui_mkt,
                "exchange": exchange_code,
                "currency": currency,
                "status": "missing",
                "message": f"لا توجد بيانات أسعار تاريخية كافية لسهم {sym}",
            })
            continue

        close = _safe_price(rows[0].get("close"))
        date = rows[0].get("date")
        ti_row = ti_by_sym.get(sym) or {}
        vwap_20 = _safe_price(ti_row.get("vwap_20"))
        ema_50, ema_200, split_factor, split_adjusted_ema = _detect_and_adjust_price_split(
            rows,
            _safe_price(ti_row.get("ema_50")),
            _safe_price(ti_row.get("ema_200")),
            close,
        )

        f_row = fund_lv_by_sym.get(sym) or {}
        f_score = _safe_float(f_row.get("fund_score"))
        norm_fd, _ = _normalize_split_adjusted_fundamentals(f_row.get("data"), close, split_factor=split_factor)
        f_eps = _safe_float(norm_fd.get("eps") if norm_fd.get("eps") is not None else norm_fd.get("trailing_eps"), 4)
        f_ni = _safe_float(norm_fd.get("netIncome") if norm_fd.get("netIncome") is not None else norm_fd.get("net_income"), 2)
        f_bvps = _safe_float(norm_fd.get("bookValuePerShare") if norm_fd.get("bookValuePerShare") is not None else norm_fd.get("bvps"), 4)
        f_pe = _safe_float(norm_fd.get("peRatio") if norm_fd.get("peRatio") is not None else norm_fd.get("pe_ratio"))
        is_loss_making = bool((f_eps is not None and f_eps < 0) or (f_ni is not None and f_ni < 0))
        is_neg_eq = bool(f_bvps is not None and f_bvps <= 0)

        recent_20 = rows[:20]
        recent_lows = [float(r["low"]) for r in recent_20 if r.get("low")]
        recent_highs = [float(r["high"]) for r in recent_20 if r.get("high")]
        all_lows = [float(r["low"]) for r in rows if r.get("low")]
        all_highs = [float(r["high"]) for r in rows if r.get("high")]

        support_1 = _safe_price(min(recent_lows)) if recent_lows else None
        resistance_1 = _safe_price(max(recent_highs)) if recent_highs else None
        raw_s2 = _safe_price(min(all_lows)) if all_lows else None
        raw_r2 = _safe_price(max(all_highs)) if all_highs else None
        support_2, resistance_2 = _distinct_secondary_levels(support_1, raw_s2, resistance_1, raw_r2)

        stop_loss = _safe_price(support_1 * 0.98) if support_1 else None
        entry_zone = f"{support_1} – {_safe_price(support_1 * 1.02)}" if support_1 else "غير محدد"

        has_rec = False
        rec_data = None
        if eff_allow_recs and sym in rec_by_sym:
            has_rec = True
            r = rec_by_sym[sym]
            rec_data = {
                "signal": r.get("signal"),
                "entry_price": _safe_price(r.get("entry_price")),
                "target_price": _safe_price(r.get("target_price")),
                "stop_loss": _safe_price(r.get("stop_loss")),
                "status": r.get("status"),
                "signal_date": str(r.get("created_at") or "")[:10],
            }

        lvl_ctx = _compute_stock_context_metrics(
            close=close,
            ema_50=ema_50,
            ema_200=ema_200,
            vwap_20=vwap_20,
            support_1=support_1,
            resistance_1=resistance_1,
            stop_loss=stop_loss,
        )
        rv_info_lv = resolve_intraday_r_vol(
            _safe_float(ti_row.get("r_vol")),
            date,
            exchange=exchange_code,
            ohlcv_rows=rows,
        )
        lvl_item: Dict[str, Any] = {
            "symbol": sym,
            "market": ui_mkt,
            "exchange": exchange_code,
            "currency": currency,
            "close": close,
            "date": date,
            "ema_50": ema_50,
            "ema_200": ema_200,
            "vwap_20": vwap_20,
            "rsi_14": _safe_float(ti_row.get("rsi_14")),
            "r_vol": rv_info_lv["effective_r_vol"],
            **(
                {
                    "r_vol_raw": rv_info_lv["raw_r_vol"],
                    "r_vol_mode": rv_info_lv["r_vol_mode"],
                    "r_vol_note_ar": rv_info_lv["r_vol_note_ar"],
                }
                if rv_info_lv["is_intraday_adjusted"]
                else {}
            ),
            "king_ai_score": _normalize_king_ai_score(ti_row.get("king_ai_score")),
            "fund_score": f_score,
            "pe_ratio": f_pe,
            "is_loss_making": is_loss_making,
            "is_negative_equity": is_neg_eq,
            "is_sharia_compliant": is_sharia_compliant(sym, market=exchange_code) if exchange_code in ("EGX", "TADAWUL") else None,
            "support_1": support_1,
            "support_2": support_2,
            "resistance_1": resistance_1,
            "resistance_2": resistance_2,
            "stop_loss": stop_loss,
            "target_1": resistance_1,
            "target_2": resistance_2,
            "entry_zone": entry_zone,
            "has_active_recommendation": has_rec,
            "active_recommendation": rec_data,
            **lvl_ctx,
        }
        if split_adjusted_ema:
            lvl_item["split_adjusted_ema"] = True
        levels.append(lvl_item)
    return levels


def _sync_get_stock_levels(
    symbols: List[str],
    allow_recommendations: Optional[bool] = None,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    grouped_syms = _group_symbols_by_exchange(symbols, market=market)
    if not grouped_syms:
        return {"status": "error", "message": "لم يتم تحديد رموز أسهم صالحة"}

    eff_allow_recs = _ALLOW_RECOMMENDATIONS_CTX.get() if allow_recommendations is None else bool(allow_recommendations)
    cache_parts = []
    for exch_k in sorted(grouped_syms.keys()):
        cache_parts.extend(f"{exch_k}:{s}" for s in sorted(grouped_syms[exch_k]))
    cache_key = f"get_stock_levels:{','.join(cache_parts)}:rec={1 if eff_allow_recs else 0}"
    cached = _get_tool_cached(cache_key)
    if cached is not None:
        return cached

    levels: List[Dict[str, Any]] = []
    for exch_code, exch_syms in grouped_syms.items():
        if not exch_syms:
            continue
        sb_exch = _get_sb() if exch_code == "EGX" else _get_sb_for_market(exch_code)
        if sb_exch is None:
            if len(grouped_syms) == 1:
                return _market_unconfigured_error(exch_code)
            cfg = _reg_get_market_config(exch_code)
            for s in exch_syms:
                levels.append({
                    "symbol": s,
                    "market": cfg.ui_code,
                    "exchange": exch_code,
                    "currency": cfg.currency_ar or cfg.currency_code,
                    "status": "missing",
                    "message": f"قاعدة بيانات {cfg.name_ar} غير متاحة حالياً.",
                })
        else:
            levels.extend(
                _sync_get_stock_levels_for_market(
                    sb_exch, exch_syms, exch_code, allow_recommendations=eff_allow_recs
                )
            )

    res = {"status": "success", "levels": levels}
    _set_tool_cached(cache_key, res)
    return res


async def execute_get_stock_levels(
    symbols: List[str],
    allow_recommendations: Optional[bool] = None,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_stock_levels, symbols, allow_recommendations, market)


# ---------------------------------------------------------------------------
# Tool: get_market
# ---------------------------------------------------------------------------
def _sync_get_market(market: Optional[str] = None) -> Dict[str, Any]:
    eff_mkt = _resolve_effective_market(market=market)
    cache_key = f"get_market:{eff_mkt}"
    cached = _get_tool_cached(cache_key)
    if cached is not None:
        return cached

    if eff_mkt != "EGX":
        cfg = _reg_get_market_config(eff_mkt)
        sb_sa = _get_sb_for_market(eff_mkt)
        if sb_sa is None:
            return _market_unconfigured_error(eff_mkt)

        sa_payload: Dict[str, Any] = {}
        if cfg.market_cache_key and (_get_saudi_table_columns("market_cache", sb_sa) is not None or not _is_real_saudi_sb(sb_sa)):
            try:
                res_mc = (
                    sb_sa.from_("market_cache")
                    .select("payload")
                    .eq("cache_key", cfg.market_cache_key)
                    .limit(1)
                    .execute()
                )
                if res_mc.data and isinstance(res_mc.data[0].get("payload"), dict):
                    sa_payload = res_mc.data[0]["payload"]
            except Exception:
                pass

        tasi_close = _safe_float(sa_payload.get("tasi_close") or sa_payload.get("index_close") or sa_payload.get("close"))
        tasi_change_pct = _safe_float(sa_payload.get("tasi_change_pct") or sa_payload.get("index_change_pct") or sa_payload.get("change_pct"))
        m_date = sa_payload.get("date")
        idx_source = sa_payload.get("source")
        try:
            res_idx = (
                sb_sa.from_("market_index")
                .select("date,close,ret,source")
                .eq("exchange", eff_mkt)
                .order("date", desc=True)
                .limit(2)
                .execute()
            )
            idx_rows = res_idx.data or []
            if idx_rows:
                tasi_close = _safe_float(idx_rows[0].get("close")) or tasi_close
                m_date = idx_rows[0].get("date") or m_date
                idx_source = idx_rows[0].get("source") or idx_source
                ret0 = _safe_float(idx_rows[0].get("ret"), 6)
                if ret0 is not None:
                    tasi_change_pct = round(ret0 * 100.0, 2)
                elif len(idx_rows) >= 2:
                    prev_c = _safe_float(idx_rows[1].get("close"))
                    if prev_c and tasi_close:
                        tasi_change_pct = round(((tasi_close - prev_c) / prev_c) * 100.0, 2)
        except Exception:
            pass

        top_gainers: List[Dict[str, Any]] = list(sa_payload.get("top_gainers") or [])
        top_losers: List[Dict[str, Any]] = list(sa_payload.get("top_losers") or [])
        breadth: Dict[str, Any] = dict(sa_payload.get("breadth") or {}) if isinstance(sa_payload.get("breadth"), dict) else {}

        def _format_sa_movers(items: List[Dict[str, Any]], names_lookup: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
            formatted = []
            for r in items:
                sym = r.get("symbol")
                if not sym:
                    continue
                nm = names_lookup.get(sym, {})
                clean_nm = (
                    nm.get("name_ar")
                    or _alias_name_for_symbol(sym, eff_mkt)
                    or nm.get("name")
                    or r.get("name")
                    or sym
                ).split(",")[0].strip()
                formatted.append({
                    "symbol": sym,
                    "name": clean_nm,
                    "close": _safe_price(r.get("close")),
                    "change_pct": _safe_float(r.get("change_pct")),
                    "currency": cfg.currency_ar or cfg.currency_code,
                })
            return formatted

        # Prefer stock_technical_indicators when populated (filtered to latest date & non-null change_pct)
        if not top_gainers and not top_losers:
            try:
                ti_cols_str, _ = _saudi_ti_select_and_order(sb_sa)
                ti_cols = set(ti_cols_str.split(","))
                latest_ti_date = (
                    _get_latest_table_date(sb_sa, "stock_technical_indicators", "date", eff_mkt)
                    if "date" in ti_cols
                    else None
                )
                if latest_ti_date:
                    res_ti_all = (
                        sb_sa.from_("stock_technical_indicators")
                        .select("symbol,close,change_pct")
                        .eq("exchange", eff_mkt)
                        .eq("date", latest_ti_date)
                        .not_.is_("change_pct", "null")
                        .order("change_pct", desc=True)
                        .limit(350)
                        .execute()
                    )
                    valid_ti = [
                        r for r in (res_ti_all.data or [])
                        if isinstance(r, dict) and r.get("change_pct") is not None
                    ]
                    if valid_ti:
                        valid_ti.sort(key=lambda r: float(r["change_pct"]), reverse=True)
                        adv = sum(1 for r in valid_ti if float(r["change_pct"]) > 0)
                        dec = sum(1 for r in valid_ti if float(r["change_pct"]) < 0)
                        unch = sum(1 for r in valid_ti if float(r["change_pct"]) == 0)
                        breadth = {
                            "advancing": adv,
                            "declining": dec,
                            "unchanged": unch,
                            "total_stocks": len(valid_ti),
                        }
                        g_raw = valid_ti[:5]
                        l_raw = sorted(valid_ti[-5:], key=lambda x: float(x["change_pct"]))
                        movers_syms = [r["symbol"] for r in (g_raw + l_raw) if r.get("symbol")]
                        names_map = _fetch_saudi_names_map(sb_sa, movers_syms, exchange=eff_mkt)
                        top_gainers = _format_sa_movers(g_raw, names_map)
                        top_losers = _format_sa_movers(l_raw, names_map)
                else:
                    res_g = (
                        sb_sa.from_("stock_technical_indicators")
                        .select("symbol,close,change_pct")
                        .eq("exchange", eff_mkt)
                        .not_.is_("change_pct", "null")
                        .order("change_pct", desc=True)
                        .limit(5)
                        .execute()
                    )
                    res_l = (
                        sb_sa.from_("stock_technical_indicators")
                        .select("symbol,close,change_pct")
                        .eq("exchange", eff_mkt)
                        .not_.is_("change_pct", "null")
                        .order("change_pct", desc=False)
                        .limit(5)
                        .execute()
                    )
                    g_raw = [r for r in (res_g.data or []) if isinstance(r, dict) and r.get("change_pct") is not None]
                    l_raw = [r for r in (res_l.data or []) if isinstance(r, dict) and r.get("change_pct") is not None]
                    if g_raw or l_raw:
                        movers_syms = [r["symbol"] for r in (g_raw + l_raw) if r.get("symbol")]
                        names_map = _fetch_saudi_names_map(sb_sa, movers_syms, exchange=eff_mkt)
                        top_gainers = _format_sa_movers(g_raw, names_map)
                        top_losers = _format_sa_movers(l_raw, names_map)
            except Exception:
                pass

        # Fallback cleanly to 2-day OHLCV snapshot when stock_technical_indicators is empty
        if not top_gainers and not top_losers:
            snap_rows = _get_saudi_computed_market_indicators(sb_sa, lookback_days=2, exchange=eff_mkt)
            valid_snap = [r for r in snap_rows if r.get("change_pct") is not None]
            valid_snap.sort(key=lambda r: float(r["change_pct"]), reverse=True)
            adv = sum(1 for r in valid_snap if float(r["change_pct"]) > 0)
            dec = sum(1 for r in valid_snap if float(r["change_pct"]) < 0)
            unch = sum(1 for r in valid_snap if float(r["change_pct"]) == 0)
            breadth = {
                "advancing": adv,
                "declining": dec,
                "unchanged": unch,
                "total_stocks": len(valid_snap),
            }
            g_raw = valid_snap[:5]
            l_raw = sorted(valid_snap[-5:], key=lambda x: float(x["change_pct"]))
            movers_syms = [r["symbol"] for r in (g_raw + l_raw) if r.get("symbol")]
            names_map = _fetch_saudi_names_map(sb_sa, movers_syms, exchange=eff_mkt)
            top_gainers = _format_sa_movers(g_raw, names_map)
            top_losers = _format_sa_movers(l_raw, names_map)

        res: Dict[str, Any] = {
            "status": "success",
            "market": cfg.ui_code,
            "market_display": f"{cfg.ui_code} ({cfg.name_ar})",
            "market_code": eff_mkt,
            "exchange": eff_mkt,
            "index_name": cfg.index_name,
            "currency": cfg.currency_ar or cfg.currency_code,
            "index_close": tasi_close,
            "index_change_pct": tasi_change_pct,
            **({"tasi_close": tasi_close, "tasi_change_pct": tasi_change_pct} if eff_mkt == "TADAWUL" else {}),
            "index_source": idx_source,
            "date": m_date,
            "breadth": breadth or None,
            "breadth_summary": _summarize_breadth(breadth),
            "top_gainers": top_gainers,
            "top_losers": top_losers,
        }
        if idx_source == "equal_weight":
            res["index_type"] = "equal_weight_composite"
            res["index_note"] = f"مؤشر {cfg.name_ar} المركب متساوي الأوزان (سنة الأساس = 1000)"
        _set_tool_cached(cache_key, res)
        return res

    # ── EGX (preserved existing logic) ───────────────────────────────────────
    sb = _get_sb()
    payload: Dict[str, Any] = {}
    try:
        res_mc = sb.from_("market_cache").select("payload").eq("cache_key", "market_status_Egypt").limit(1).execute()
        if res_mc.data and isinstance(res_mc.data[0].get("payload"), dict):
            payload = res_mc.data[0]["payload"]
    except Exception:
        pass

    egx30_close = None
    egx30_change_pct = None
    m_date = None
    try:
        res_egx30 = sb.from_("stock_prices").select("close,date").eq("symbol", "EGX30").order("date", desc=True).limit(2).execute()
        if res_egx30.data and len(res_egx30.data) >= 1:
            egx30_close = _safe_float(res_egx30.data[0].get("close"))
            m_date = res_egx30.data[0].get("date")
            if len(res_egx30.data) >= 2:
                prev = _safe_float(res_egx30.data[1].get("close"))
                if prev and egx30_close:
                    egx30_change_pct = round(((egx30_close - prev) / prev) * 100, 2)
    except Exception:
        pass

    top_gainers = payload.get("top_gainers") or []
    top_losers = payload.get("top_losers") or []
    if not top_gainers:
        try:
            res_g = sb.from_("stock_technical_indicators").select("symbol,close,change_pct").eq("exchange", "EGX").order("change_pct", desc=True).limit(5).execute()
            top_gainers = res_g.data or []
        except Exception:
            pass
    if not top_losers:
        try:
            res_l = sb.from_("stock_technical_indicators").select("symbol,close,change_pct").eq("exchange", "EGX").order("change_pct", desc=False).limit(5).execute()
            top_losers = res_l.data or []
        except Exception:
            pass

    breadth = payload.get("breadth")
    if not breadth:
        try:
            b_date = m_date or payload.get("date") or _get_latest_table_date(sb, "stock_technical_indicators", "date", "EGX")
            if b_date:
                res_b = (
                    sb.from_("stock_technical_indicators")
                    .select("change_pct")
                    .eq("exchange", "EGX")
                    .eq("date", b_date)
                    .not_.is_("change_pct", "null")
                    .limit(350)
                    .execute()
                )
                vals = [float(r["change_pct"]) for r in (res_b.data or []) if isinstance(r, dict) and r.get("change_pct") is not None]
                if vals:
                    breadth = {
                        "advancing": sum(1 for v in vals if v > 0),
                        "declining": sum(1 for v in vals if v < 0),
                        "unchanged": sum(1 for v in vals if v == 0),
                        "total_stocks": len(vals),
                    }
        except Exception:
            breadth = None

    res = {
        "status": "success",
        "market": "EGX (البورصة المصرية)",
        "market_code": "EGX",
        "index_name": "EGX30",
        "currency": "ج.م",
        "egx30_close": egx30_close or payload.get("egx30_close"),
        "egx30_change_pct": egx30_change_pct or payload.get("egx30_change_pct"),
        "date": m_date or payload.get("date"),
        "breadth": breadth,
        "breadth_summary": _summarize_breadth(breadth),
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "liquidity_summary": payload.get("liquidity", "سيولة متوازنة في جلسة اليوم"),
    }
    _set_tool_cached(cache_key, res)
    return res


async def execute_get_market(market: Optional[str] = None) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_market, market)


# ---------------------------------------------------------------------------
# Tool: get_recommendations
# ---------------------------------------------------------------------------
def _sync_get_recommendations(
    status: str = "open",
    timeframe: str = "all",
    symbols: Optional[List[str]] = None,
    sharia_only: bool = False,
    limit: int = 20,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    eff_mkt = _resolve_effective_market(market=market, symbols=symbols)
    currency = _currency_for_market(eff_mkt)
    ui_mkt = _ui_market_label(eff_mkt)

    if eff_mkt != "EGX":
        cfg = _reg_get_market_config(eff_mkt)
        sb_sa = _get_sb_for_market(eff_mkt)
        if sb_sa is None:
            return _market_unconfigured_error(eff_mkt)

        desired_rec_cols = [
            "id", "symbol", "name", "signal", "entry_price", "target_price",
            "stop_loss", "last_close", "precision", "top_reasons",
            "status", "created_at", "model_name", "exchange",
        ]
        safe_rec_fallback = (
            "id,symbol,name,signal,entry_price,target_price,stop_loss,"
            "last_close,precision,status,created_at,model_name"
        )
        rows: List[Dict[str, Any]] = []
        mkt_syms = _group_symbols_by_exchange(symbols).get(eff_mkt, []) if symbols else []

        for tbl_name in ("scan_results", "current_public_recommendations"):
            tbl_cols = _get_saudi_table_columns(tbl_name, sb_sa)
            if tbl_cols is not None:
                sel_cols = ",".join([c for c in desired_rec_cols if c in tbl_cols]) or safe_rec_fallback
                has_exchange_col = "exchange" in tbl_cols
            else:
                sel_cols = safe_rec_fallback
                has_exchange_col = True

            # NEVER drop exchange filter or query exchange-less tables for GCC/Metals/future exchanges
            # sharing SAUDI_SUPABASE or Primary Supabase!
            allow_unfiltered = eff_mkt == "TADAWUL" and sb_sa is not _get_sb()
            if not has_exchange_col and not allow_unfiltered:
                continue
            filter_modes = (True, False) if (has_exchange_col and allow_unfiltered) else ((True,) if has_exchange_col else (False,))
            for use_exchange_filter in filter_modes:
                try:
                    q = sb_sa.from_(tbl_name).select(sel_cols)
                    if use_exchange_filter:
                        q = q.eq("exchange", eff_mkt)
                    if status == "open":
                        q = q.in_("status", ["open", "active"])
                    elif status == "closed":
                        q = q.in_("status", ["closed", "win", "loss"])
                    if mkt_syms:
                        q = q.in_("symbol", mkt_syms)
                    res = q.order("created_at", desc=True).limit(min(limit or 20, 30)).execute()
                    rows = [
                        r for r in (res.data or [])
                        if str(r.get("status") or "").lower() != "cancelled"
                    ]
                    if rows:
                        break
                except Exception:
                    continue
            if rows:
                break

        rec_syms = [r.get("symbol") for r in rows if r.get("symbol")]
        names_map = _fetch_saudi_names_map(sb_sa, rec_syms, exchange=eff_mkt)

        recs = []
        for r in rows:
            sym = r.get("symbol")
            nm = names_map.get(sym, {})
            stock_name_ar = nm.get("name_ar") or _alias_name_for_symbol(sym, market=eff_mkt)
            clean_name = (stock_name_ar or nm.get("name") or r.get("name") or sym).split(",")[0].strip()
            rec_item: Dict[str, Any] = {
                "symbol": sym,
                "market": ui_mkt,
                "exchange": eff_mkt,
                "currency": currency,
                "name": clean_name,
                "name_ar": clean_name,
                "signal": r.get("signal", "BUY"),
                "entry_price": _safe_price(r.get("entry_price")),
                "target_price": _safe_price(r.get("target_price")),
                "stop_loss": _safe_price(r.get("stop_loss")),
                "status": "نشطة (مفتوحة)" if r.get("status") in ["open", "active"] else r.get("status"),
                "timeframe": "سوينغ يومي 🎯",
                "strategy": r.get("model_name") or "خوارزمية الذكاء الاصطناعي",
                "date": str(r.get("created_at") or "")[:10],
                "is_sharia_compliant": None,
            }
            if r.get("last_close") is not None:
                rec_item["last_close"] = _safe_price(r.get("last_close"))
            if r.get("precision") is not None:
                rec_item["precision"] = _safe_float(r.get("precision"))
            if r.get("top_reasons") is not None:
                rec_item["top_reasons"] = r.get("top_reasons")
            _enrich_rec_distances(rec_item)
            recs.append(rec_item)

        out: Dict[str, Any] = {
            "status": "success",
            "market": ui_mkt,
            "exchange": eff_mkt,
            "currency": currency,
            "count": len(recs),
            "filter_status": status,
            "sharia_only": sharia_only,
            "recommendations": recs,
        }
        if not recs:
            out["note"] = (
                f"لا توجد توصيات منشورة حالياً في جدول توصيات {cfg.name_ar} ({ui_mkt}). "
                f"يمكنك طلب فحص فني فوري عبر get_technical_scan(market='{ui_mkt}') أو تحليل سهم محدد برمزه."
            )
        return out

    # ── EGX (preserve exact mock chain for tests!) ───────────────────────────
    sb = _get_sb()
    try:
        query = sb.from_("scan_results").select(
            "id,symbol,name,signal,entry_price,target_price,stop_loss,status,created_at,model_name"
        )
        if status == "open":
            query = query.in_("status", ["open", "active"])
        elif status == "closed":
            query = query.in_("status", ["closed", "win", "loss"])

        if symbols:
            clean_syms = [_normalize_symbol(s) for s in symbols if s]
            query = query.in_("symbol", clean_syms)

        query = query.order("created_at", desc=True).limit(min(limit or 20, 30))
        res = query.execute()
        rows = [
            r for r in (res.data or [])
            if str(r.get("status") or "").lower() != "cancelled"
        ]
    except Exception as e:
        return {"status": "error", "message": f"تعذر استرجاع التوصيات: {str(e)}"}

    recs = []
    for r in rows:
        sym = r.get("symbol")
        if sharia_only and not is_sharia_compliant(sym):
            continue

        stock_name_ar = _alias_name_for_symbol(sym, market="EGX")
        clean_name = (stock_name_ar or r.get("name") or sym).split(",")[0].strip()

        recs.append({
            "symbol": sym,
            "market": "EGX",
            "exchange": "EGX",
            "currency": _reg_currency_for_symbol(sym, "EGX"),
            "name": clean_name,
            "name_ar": clean_name,
            "signal": r.get("signal", "BUY"),
            "entry_price": _safe_price(r.get("entry_price")),
            "target_price": _safe_price(r.get("target_price")),
            "stop_loss": _safe_price(r.get("stop_loss")),
            "status": "نشطة (مفتوحة)" if r.get("status") in ["open", "active"] else r.get("status"),
            "timeframe": "سوينغ يومي 🎯",
            "strategy": r.get("model_name") or "خوارزمية الذكاء الاصطناعي",
            "date": str(r.get("created_at") or "")[:10],
            "is_sharia_compliant": is_sharia_compliant(sym),
        })

    if recs:
        try:
            rec_syms = list({r["symbol"] for r in recs if r.get("symbol")})[:30]
            if rec_syms:
                res_lc = (
                    sb.from_("stock_technical_indicators")
                    .select("symbol,close,date")
                    .eq("exchange", "EGX")
                    .in_("symbol", rec_syms)
                    .order("date", desc=True)
                    .limit(len(rec_syms) * 2)
                    .execute()
                )
                lc_map: Dict[str, float] = {}
                for row in (res_lc.data or []):
                    if isinstance(row, dict) and row.get("symbol") and row["symbol"] not in lc_map:
                        cv = _safe_price(row.get("close"))
                        if cv is not None:
                            lc_map[row["symbol"]] = cv
                for rec_item in recs:
                    if rec_item.get("last_close") is None and rec_item.get("symbol") in lc_map:
                        rec_item["last_close"] = lc_map[rec_item["symbol"]]
        except Exception:
            pass
        for rec_item in recs:
            _enrich_rec_distances(rec_item)

    return {
        "status": "success",
        "market": ui_mkt,
        "exchange": "EGX",
        "currency": currency,
        "count": len(recs),
        "filter_status": status,
        "sharia_only": sharia_only,
        "recommendations": recs,
    }


async def execute_get_recommendations(
    status: str = "open",
    timeframe: str = "all",
    symbols: Optional[List[str]] = None,
    sharia_only: bool = False,
    limit: int = 20,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_recommendations, status, timeframe, symbols, sharia_only, limit, market)


# ---------------------------------------------------------------------------
# Tool: get_technical_scan
# ---------------------------------------------------------------------------
def _momentum_scan_intraday_fallback(
    sb_client: Any,
    *,
    exchange: str,
    select_cols: str,
    latest_date: Optional[str],
    primary_rows: List[Dict[str, Any]],
    min_primary: int = 5,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Time-paced intraday fallback for `momentum_and_volume` when raw `r_vol >= 1.2` returns too few rows
    because session volume is still accumulating. Falls back to prior completed session if intraday feed is empty.
    """
    if len(primary_rows) >= min_primary or not latest_date:
        return primary_rows, None

    sess = get_exchange_session_state(exchange=exchange)
    fallback_note: Optional[str] = None
    existing_syms = {str(r.get("symbol") or "").upper() for r in primary_rows if r.get("symbol")}
    merged: List[Dict[str, Any]] = [dict(r) for r in primary_rows]

    # Step 1: Fetch active intraday gainers on latest_date and pace their partial r_vol
    try:
        q_gain = (
            sb_client.from_("stock_technical_indicators")
            .select(select_cols)
            .eq("exchange", exchange)
            .eq("date", latest_date)
            .gte("change_pct", 0)
            .order("r_vol", desc=True)
            .limit(40)
        )
        gainers = q_gain.execute().data or []
    except Exception:
        gainers = []

    paced_candidates: List[Tuple[Tuple[float, float], Dict[str, Any]]] = []
    for row in gainers:
        sym_u = str(row.get("symbol") or "").upper()
        if not sym_u or sym_u in existing_syms:
            continue
        raw_rv = _safe_float(row.get("r_vol"))
        chg = _safe_float(row.get("change_pct")) or 0.0
        rv_info = resolve_intraday_r_vol(raw_rv, row.get("date") or latest_date, exchange=exchange)
        eff_rv = rv_info.get("effective_r_vol")
        if (eff_rv is not None and eff_rv >= 1.15) or (chg >= 1.5 and (raw_rv or 0.0) >= 0.05):
            r_copy = dict(row)
            r_copy["_paced_r_vol"] = eff_rv if eff_rv is not None else raw_rv
            r_copy["_r_vol_mode"] = rv_info.get("r_vol_mode")
            r_copy["_r_vol_note_ar"] = rv_info.get("r_vol_note_ar")
            paced_candidates.append(((float(eff_rv or 0.0), float(chg)), r_copy))

    paced_candidates.sort(key=lambda item: item[0], reverse=True)
    for _, cand in paced_candidates:
        sym_u = str(cand.get("symbol") or "").upper()
        if sym_u not in existing_syms:
            existing_syms.add(sym_u)
            merged.append(cand)
        if len(merged) >= 15:
            break

    if len(merged) >= 3:
        if sess.get("is_live_session") and not primary_rows:
            fallback_note = (
                f"تمت معايرة السيولة النسبية زمنياً وفق التقدم اللحظي للجلسة ({latest_date}) لعرض أقوى أسهم الزخم النشطة."
            )
        return merged, fallback_note

    # Step 2: If intraday volume feed is still near-zero across the board, fall back to previous completed session
    try:
        q_prev_dt = (
            sb_client.from_("stock_technical_indicators")
            .select("date")
            .eq("exchange", exchange)
            .lt("date", latest_date)
            .order("date", desc=True)
            .limit(1)
        )
        prev_dt_rows = q_prev_dt.execute().data or []
        prev_date = str(prev_dt_rows[0].get("date") or "")[:10] if prev_dt_rows else None
        if prev_date:
            q_prev = (
                sb_client.from_("stock_technical_indicators")
                .select(select_cols)
                .eq("exchange", exchange)
                .eq("date", prev_date)
                .gte("r_vol", 1.2)
                .gte("change_pct", 0)
                .order("r_vol", desc=True)
                .limit(30)
            )
            prev_rows = q_prev.execute().data or []
            if prev_rows:
                note = (
                    f"بيانات السيولة اللحظية لجلسة اليوم ({latest_date}) لا تزال في بدايتها؛ "
                    f"النتائج التالية مستخرجة من أقوى أسهم الزخم والسيولة في آخر جلسة مكتملة ({prev_date})."
                )
                return prev_rows, note
    except Exception:
        pass

    return merged, fallback_note


def _sync_get_technical_scan(
    preset: str,
    sharia_only: bool = False,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    eff_mkt = _resolve_effective_market(market=market)
    ui_mkt = _ui_market_label(eff_mkt)
    currency = _currency_for_market(eff_mkt)

    if eff_mkt != "EGX":
        cfg = _reg_get_market_config(eff_mkt)
        sb_sa = _get_sb_for_market(eff_mkt)
        if sb_sa is None:
            return _market_unconfigured_error(eff_mkt)

        rows: List[Dict[str, Any]] = []
        used_computed = False
        scan_fallback_note: Optional[str] = None
        ti_cols_str = ""
        latest_sa_date: Optional[str] = None
        try:
            ti_cols_str, order_col = _saudi_ti_select_and_order(sb_sa)
            ti_cols = set(ti_cols_str.split(","))
            q = (
                sb_sa.from_("stock_technical_indicators")
                .select(ti_cols_str)
                .eq("exchange", eff_mkt)
            )
            if "date" in ti_cols:
                latest_sa_date = _get_latest_table_date(sb_sa, "stock_technical_indicators", "date", eff_mkt)
                if latest_sa_date:
                    q = q.eq("date", latest_sa_date)
            if preset == "rsi_oversold" and "rsi_14" in ti_cols:
                q = q.not_.is_("rsi_14", "null").lte("rsi_14", 35).order("rsi_14", desc=False).limit(30)
            elif preset == "top_gainers" and "change_pct" in ti_cols:
                q = q.not_.is_("change_pct", "null").order("change_pct", desc=True).limit(30)
            elif preset == "top_losers" and "change_pct" in ti_cols:
                q = q.not_.is_("change_pct", "null").order("change_pct", desc=False).limit(30)
            elif preset == "momentum_and_volume":
                if "r_vol" in ti_cols:
                    q = (
                        q.not_.is_("r_vol", "null")
                        .not_.is_("change_pct", "null")
                        .gte("r_vol", 1.2)
                        .gte("change_pct", 0)
                        .order("r_vol", desc=True)
                        .limit(30)
                    )
                else:
                    q = (
                        q.not_.is_("change_pct", "null")
                        .not_.is_("volume", "null")
                        .gte("change_pct", 0)
                        .order("volume", desc=True)
                        .limit(30)
                    )
            elif preset == "macd_cross" and "macd_histogram" in ti_cols:
                q = q.not_.is_("macd_histogram", "null").gte("macd_histogram", 0).order("macd_histogram", desc=True).limit(30)
            else:
                q = q.not_.is_("volume", "null").order("volume", desc=True).limit(30)

            res = q.execute()
            rows = res.data or []
            if preset == "momentum_and_volume" and "r_vol" in ti_cols and len(rows) < 3:
                rows, scan_fallback_note = _momentum_scan_intraday_fallback(
                    sb_sa,
                    exchange=eff_mkt,
                    select_cols=ti_cols_str,
                    latest_date=latest_sa_date,
                    primary_rows=rows,
                    min_primary=3,
                )
        except Exception:
            rows = []

        if not rows:
            used_computed = True
            snap = _get_saudi_computed_market_indicators(
                sb_sa,
                lookback_days=2 if preset in ("top_gainers", "top_losers", "high_volume") else 22,
                exchange=eff_mkt,
            )
            if preset == "rsi_oversold":
                rows = sorted(
                    [r for r in snap if r.get("rsi_14") is not None and float(r["rsi_14"]) <= 40],
                    key=lambda r: float(r["rsi_14"]),
                )[:20]
            elif preset == "top_gainers":
                rows = sorted(
                    [r for r in snap if r.get("change_pct") is not None],
                    key=lambda r: float(r["change_pct"]),
                    reverse=True,
                )[:20]
            elif preset == "top_losers":
                rows = sorted(
                    [r for r in snap if r.get("change_pct") is not None],
                    key=lambda r: float(r["change_pct"]),
                )[:20]
            elif preset == "momentum_and_volume":
                rows = sorted(
                    [r for r in snap if (r.get("change_pct") or 0) >= 0 and (r.get("r_vol") or 0) >= 1.1],
                    key=lambda r: float(r.get("r_vol") or 0),
                    reverse=True,
                )[:20]
            elif preset == "macd_cross":
                rows = sorted(
                    [r for r in snap if r.get("macd_histogram") is not None and float(r["macd_histogram"]) > 0],
                    key=lambda r: float(r["macd_histogram"]),
                    reverse=True,
                )[:20]
            else:
                rows = sorted(snap, key=lambda r: float(r.get("volume") or 0), reverse=True)[:20]

        syms_for_names = [r.get("symbol") for r in rows[:15] if r.get("symbol")]
        names_map = _fetch_saudi_names_map(sb_sa, syms_for_names, exchange=eff_mkt)

        results = []
        seen = set()
        for r in rows:
            sym = r.get("symbol")
            if not sym or sym in seen:
                continue
            seen.add(sym)

            close = _safe_price(r.get("close"))
            change_pct = _safe_float(r.get("change_pct"))
            rsi = _safe_float(r.get("rsi_14"))
            bb_low = _safe_price(r.get("bb_lower"))
            bb_up = _safe_price(r.get("bb_upper"))
            s1 = r.get("support_1") or (bb_low if bb_low else (_safe_price(close * 0.96) if close else None))
            r1 = r.get("resistance_1") or (bb_up if bb_up else (_safe_price(close * 1.05) if close else None))
            vol_val = r.get("volume")
            vol_sma = r.get("vol_sma20") or r.get("volume_sma_20")
            r_vol = _safe_float(r.get("_paced_r_vol"))
            if r_vol is None:
                r_vol = _safe_float(r.get("r_vol"))
            if r_vol is None and vol_val and vol_sma and float(vol_sma) > 0:
                r_vol = _safe_float(float(vol_val) / float(vol_sma))

            if change_pct is not None and change_pct > 0 and rsi is not None and 45 <= rsi <= 68:
                verdict = "🟢 إيجابي / فرصة جيدة"
            elif (change_pct is not None and change_pct < -2) or (rsi is not None and rsi > 75):
                verdict = "🔴 سلبي / مخاطرة مرتفعة"
            else:
                verdict = "🟡 حيادي للمراقبة"

            nm_meta = names_map.get(sym, {})
            stock_name_ar = nm_meta.get("name_ar") or _alias_name_for_symbol(sym, market=eff_mkt)
            clean_name = (stock_name_ar or nm_meta.get("name") or sym).split(",")[0].strip()

            results.append({
                "symbol": sym,
                "market": ui_mkt,
                "exchange": eff_mkt,
                "currency": currency,
                "name": clean_name,
                "name_ar": clean_name,
                "close": close,
                "change_pct": change_pct,
                "rsi_14": rsi,
                "r_vol": r_vol,
                **(
                    {
                        "r_vol_raw": _safe_float(r.get("r_vol")),
                        "r_vol_mode": r.get("_r_vol_mode"),
                        "r_vol_note_ar": r.get("_r_vol_note_ar"),
                    }
                    if r.get("_paced_r_vol") is not None and r.get("_r_vol_note_ar")
                    else {}
                ),
                "volume": vol_val,
                "macd": _safe_float(r.get("macd"), 4),
                "king_ai_score": _safe_float(r.get("king_ai_score")),
                "support_1": s1,
                "resistance_1": r1,
                "support_2": r.get("support_2") or (_safe_price(s1 * 0.96) if s1 else None),
                "resistance_2": r.get("resistance_2") or (_safe_price(r1 * 1.05) if r1 else None),
                "stop_loss": r.get("stop_loss") or (_safe_price(s1 * 0.98) if s1 else None),
                "verdict": verdict,
                "date": r.get("date") or (str(r.get("updated_at"))[:10] if r.get("updated_at") else None),
                "is_sharia_compliant": None,
            })
            if len(results) >= 10:
                break

        out: Dict[str, Any] = {
            "status": "success",
            "market": ui_mkt,
            "exchange": eff_mkt,
            "currency": currency,
            "preset": preset,
            "stocks": results,
        }
        if used_computed:
            out["data_source"] = "computed_from_ohlcv"
        if scan_fallback_note:
            out["scan_fallback_note_ar"] = scan_fallback_note
        if sharia_only:
            out["sharia_note"] = f"تصنيف الشريعة لأسهم {cfg.name_ar} قيد الإضافة، وتُعرض نتائج المسح الفني العامة حالياً."
        return out

    # ── EGX (with intraday time-paced & prev-session momentum fallback) ────────
    sb = _get_sb()
    egx_scan_select = (
        "symbol,date,close,change_pct,volume,r_vol,rsi_14,macd,macd_signal,macd_histogram,"
        "bb_upper,bb_lower,ema_50,ema_200,king_ai_score,egx_ai_score"
    )
    egx_scan_fallback_note: Optional[str] = None
    try:
        latest_date = _get_latest_table_date(sb, "stock_technical_indicators", "date", "EGX")
        query = sb.from_("stock_technical_indicators").select(egx_scan_select).eq("exchange", "EGX")
        if latest_date:
            query = query.eq("date", latest_date)

        if preset == "rsi_oversold":
            query = query.lte("rsi_14", 35).order("rsi_14", desc=False).limit(30)
        elif preset == "top_gainers":
            query = query.order("change_pct", desc=True).limit(30)
        elif preset == "top_losers":
            query = query.order("change_pct", desc=False).limit(30)
        elif preset == "momentum_and_volume":
            query = query.gte("r_vol", 1.2).gte("change_pct", 0).order("r_vol", desc=True).limit(30)
        elif preset == "macd_cross":
            query = query.gte("macd_histogram", 0).order("macd_histogram", desc=True).limit(30)
        else:
            query = query.order("volume", desc=True).limit(30)

        res = query.execute()
        rows = res.data or []
        if preset == "momentum_and_volume" and len(rows) < 5:
            rows, egx_scan_fallback_note = _momentum_scan_intraday_fallback(
                sb,
                exchange="EGX",
                select_cols=egx_scan_select,
                latest_date=latest_date,
                primary_rows=rows,
                min_primary=5,
            )
    except Exception as e:
        return {"status": "error", "message": f"تعذر تنفيذ المسح الفني: {str(e)}"}

    results = []
    seen = set()
    for r in rows:
        sym = r.get("symbol")
        if not sym or sym in seen:
            continue
        seen.add(sym)

        if sharia_only and not is_sharia_compliant(sym):
            continue

        close = _safe_price(r.get("close"))
        change_pct = _safe_float(r.get("change_pct"))
        rsi = _safe_float(r.get("rsi_14"))
        bb_low = _safe_price(r.get("bb_lower"))
        bb_up = _safe_price(r.get("bb_upper"))
        s1 = bb_low if bb_low else (_safe_price(close * 0.96) if close else None)
        r1 = bb_up if bb_up else (_safe_price(close * 1.05) if close else None)

        if change_pct is not None and change_pct > 0 and rsi is not None and 45 <= rsi <= 68:
            verdict = "🟢 إيجابي / فرصة جيدة"
        elif (change_pct is not None and change_pct < -2) or (rsi is not None and rsi > 75):
            verdict = "🔴 سلبي / مخاطرة مرتفعة"
        else:
            verdict = "🟡 حيادي للمراقبة"

        stock_name_ar = _alias_name_for_symbol(sym, market="EGX")
        clean_name = (stock_name_ar or sym).split(",")[0].strip()

        scan_rv_info = (
            {"effective_r_vol": _safe_float(r.get("_paced_r_vol")), "raw_r_vol": _safe_float(r.get("r_vol")), "r_vol_mode": r.get("_r_vol_mode"), "r_vol_note_ar": r.get("_r_vol_note_ar"), "is_intraday_adjusted": True}
            if r.get("_paced_r_vol") is not None
            else resolve_intraday_r_vol(_safe_float(r.get("r_vol")), r.get("date"), exchange="EGX")
        )
        results.append({
            "symbol": sym,
            "market": "EGX",
            "exchange": "EGX",
            "currency": _reg_currency_for_symbol(sym, "EGX"),
            "name": clean_name,
            "name_ar": clean_name,
            "close": close,
            "change_pct": change_pct,
            "rsi_14": rsi,
            "r_vol": scan_rv_info["effective_r_vol"],
            **(
                {
                    "r_vol_raw": scan_rv_info["raw_r_vol"],
                    "r_vol_mode": scan_rv_info["r_vol_mode"],
                    "r_vol_note_ar": scan_rv_info["r_vol_note_ar"],
                }
                if scan_rv_info.get("is_intraday_adjusted")
                else {}
            ),
            "macd": _safe_float(r.get("macd"), 4),
            "king_ai_score": _normalize_king_ai_score(r.get("king_ai_score")),
            "egx_ai_score": _safe_float(r.get("egx_ai_score")),
            "support_1": s1,
            "resistance_1": r1,
            "support_2": _safe_price(s1 * 0.96) if s1 else None,
            "resistance_2": _safe_price(r1 * 1.05) if r1 else None,
            "stop_loss": _safe_price(s1 * 0.98) if s1 else None,
            "verdict": verdict,
            "date": r.get("date"),
            "is_sharia_compliant": is_sharia_compliant(sym),
        })
        if len(results) >= 10:
            break

    egx_scan_out: Dict[str, Any] = {
        "status": "success",
        "market": ui_mkt,
        "exchange": "EGX",
        "currency": currency,
        "preset": preset,
        "stocks": results,
    }
    if egx_scan_fallback_note:
        egx_scan_out["scan_fallback_note_ar"] = egx_scan_fallback_note
    return egx_scan_out


async def execute_get_technical_scan(
    preset: str,
    sharia_only: bool = False,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_technical_scan, preset, sharia_only, market)


# ---------------------------------------------------------------------------
# Tool: get_accumulation_stocks
# ---------------------------------------------------------------------------
def _sync_get_accumulation_stocks(
    sharia_only: bool = False,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    eff_mkt = _resolve_effective_market(market=market)
    ui_mkt = _ui_market_label(eff_mkt)
    currency = _currency_for_market(eff_mkt)

    if eff_mkt != "EGX":
        cfg = _reg_get_market_config(eff_mkt)
        sb_sa = _get_sb_for_market(eff_mkt)
        if sb_sa is None:
            return _market_unconfigured_error(eff_mkt)

        # 1. Prefer stock_scans_summary ONLY when it has an `exchange` column (preventing TADAWUL/EGX bleed into GCC/Metals),
        #    for TADAWUL on dedicated SAUDI_SUPABASE, or in non-live mock unit tests.
        summary_cols = _get_saudi_table_columns("stock_scans_summary", sb_sa)
        has_summary_exchange = bool(summary_cols and "exchange" in summary_cols)
        can_query_summary = (
            has_summary_exchange
            or not _is_real_saudi_sb(sb_sa)
            or (eff_mkt == "TADAWUL" and summary_cols is not None and sb_sa is not _get_sb())
        )
        if can_query_summary:
            try:
                desired_sum = [
                    "symbol", "scan_date", "acc_score", "dist_score",
                    "wyckoff_phase", "vol_ratio", "signal", "consecutive_acc_days",
                ]
                sum_sel = (
                    ",".join([c for c in desired_sum if c in summary_cols])
                    if summary_cols is not None
                    else ",".join(desired_sum)
                )
                exch_filter = (
                    eff_mkt
                    if (eff_mkt != "TADAWUL" or has_summary_exchange or not _is_real_saudi_sb(sb_sa))
                    else None
                )
                latest_sa_scan = _get_latest_table_date(
                    sb_sa, "stock_scans_summary", "scan_date", exchange=exch_filter
                )
                q_sum = (
                    sb_sa.from_("stock_scans_summary")
                    .select(sum_sel)
                    .not_.is_("acc_score", "null")
                    .gte("acc_score", 50)
                    .neq("wyckoff_phase", "distribution")
                )
                if exch_filter:
                    q_sum = q_sum.eq("exchange", exch_filter)
                if latest_sa_scan:
                    q_sum = q_sum.eq("scan_date", latest_sa_scan)
                res_sum = q_sum.order("acc_score", desc=True).limit(30).execute()
                sum_rows = res_sum.data or []

                stocks_sum: List[Dict[str, Any]] = []
                seen_sum = set()
                for r in sum_rows:
                    sym = r.get("symbol")
                    if not sym or sym in seen_sum:
                        continue
                    acc_val = _safe_float(r.get("acc_score")) or 0.0
                    dist_val = _safe_float(r.get("dist_score")) or 0.0
                    phase = str(r.get("wyckoff_phase") or "").lower()
                    if phase == "distribution" or dist_val > acc_val:
                        continue
                    seen_sum.add(sym)
                    stocks_sum.append({
                        "symbol": sym,
                        "market": ui_mkt,
                        "exchange": eff_mkt,
                        "currency": currency,
                        "accumulation_score": acc_val,
                        "distribution_score": dist_val,
                        "wyckoff_phase": r.get("wyckoff_phase") or "تجميع مؤسسي (Accumulation)",
                        "consecutive_acc_days": r.get("consecutive_acc_days") or 1,
                        "date": r.get("scan_date"),
                        "is_sharia_compliant": None,
                    })
                    if len(stocks_sum) >= 10:
                        break

                if stocks_sum:
                    acc_syms = [s["symbol"] for s in stocks_sum]
                    names_map = _fetch_saudi_names_map(sb_sa, acc_syms, exchange=eff_mkt)
                    ti_map: Dict[str, Dict[str, Any]] = {}
                    try:
                        ti_cols_str, order_col = _saudi_ti_select_and_order(sb_sa)
                        res_ti = (
                            sb_sa.from_("stock_technical_indicators")
                            .select(ti_cols_str)
                            .eq("exchange", eff_mkt)
                            .in_("symbol", acc_syms)
                            .order(order_col, desc=True)
                            .limit(len(acc_syms) * 3)
                            .execute()
                        )
                        for row in (res_ti.data or []):
                            s_sym = row.get("symbol")
                            if s_sym and s_sym not in ti_map:
                                ti_map[s_sym] = row
                    except Exception:
                        pass

                    for s in stocks_sum:
                        s_sym = s["symbol"]
                        ti = ti_map.get(s_sym, {})
                        close = _safe_price(ti.get("close"))
                        change_pct = _safe_float(ti.get("change_pct"))
                        rsi = _safe_float(ti.get("rsi_14"))
                        bb_low = _safe_price(ti.get("bb_lower"))
                        bb_up = _safe_price(ti.get("bb_upper"))
                        s1 = bb_low if bb_low else (_safe_price(close * 0.96) if close else None)
                        r1 = bb_up if bb_up else (_safe_price(close * 1.05) if close else None)
                        if change_pct is not None and change_pct > 0 and rsi is not None and 45 <= rsi <= 68:
                            verdict = "🟢 إيجابي / فرصة جيدة"
                        elif (change_pct is not None and change_pct < -2) or (rsi is not None and rsi > 75):
                            verdict = "🔴 سلبي / مخاطرة مرتفعة"
                        else:
                            verdict = "🟡 حيادي للمراقبة"

                        nm = names_map.get(s_sym, {})
                        clean_name = (
                            nm.get("name_ar")
                            or _alias_name_for_symbol(s_sym, eff_mkt)
                            or nm.get("name")
                            or s_sym
                        ).split(",")[0].strip()

                        s["name"] = clean_name
                        s["name_ar"] = clean_name
                        s["close"] = close
                        s["change_pct"] = change_pct
                        s["rsi_14"] = rsi
                        s["support_1"] = s1
                        s["resistance_1"] = r1
                        s["support_2"] = _safe_price(s1 * 0.96) if s1 else None
                        s["resistance_2"] = _safe_price(r1 * 1.05) if r1 else None
                        s["stop_loss"] = _safe_price(s1 * 0.98) if s1 else None
                        s["king_ai_score"] = _normalize_king_ai_score(ti.get("king_ai_score"))
                        s["verdict"] = verdict

                    out_sum: Dict[str, Any] = {
                        "status": "success",
                        "market": ui_mkt,
                        "exchange": eff_mkt,
                        "currency": currency,
                        "accumulation_stocks": stocks_sum,
                        "stocks": stocks_sum,
                        "data_source": "stock_scans_summary",
                    }
                    if sharia_only:
                        out_sum["sharia_note"] = f"تصنيف الشريعة لأسهم {cfg.name_ar} قيد الإضافة؛ تم عرض أعلى أسهم التجميع المتاحة."
                    return out_sum
            except Exception:
                pass

        # 2. Fallback to computed CMF & relative volume accumulation from OHLCV bars
        snap = _get_saudi_computed_market_indicators(sb_sa, lookback_days=22, exchange=eff_mkt)
        acc_candidates = []
        for r in snap:
            cmf = float(r.get("cmf_20") or 0.0)
            r_vol = float(r.get("r_vol") or 1.0)
            chg = float(r.get("change_pct") or 0.0)
            rsi = float(r.get("rsi_14") or 50.0)
            # Institutional accumulation proxy: positive money flow + volume expansion without blowoff
            if cmf >= 0.04 and chg >= -2.5 and rsi <= 72.0:
                score = min(98.0, round(50.0 + cmf * 150.0 + max(r_vol - 1.0, 0.0) * 15.0, 1))
                acc_candidates.append((score, r))

        acc_candidates.sort(key=lambda item: item[0], reverse=True)
        top_items = acc_candidates[:10]
        names_map = _fetch_saudi_names_map(sb_sa, [r["symbol"] for _, r in top_items], exchange=eff_mkt)
        stocks = []
        for acc_score, r in top_items:
            sym = r["symbol"]
            nm = names_map.get(sym, {})
            clean_name = (nm.get("name_ar") or _alias_name_for_symbol(sym, eff_mkt) or nm.get("name") or sym).split(",")[0].strip()
            close = r.get("close")
            chg = r.get("change_pct")
            rsi = r.get("rsi_14")
            verdict = (
                "🟢 إيجابي / فرصة جيدة"
                if (chg is not None and chg > 0 and rsi is not None and 45 <= rsi <= 68)
                else "🟡 حيادي للمراقبة"
            )
            stocks.append({
                "symbol": sym,
                "market": ui_mkt,
                "exchange": eff_mkt,
                "currency": currency,
                "name": clean_name,
                "name_ar": clean_name,
                "accumulation_score": acc_score,
                "cmf_20": r.get("cmf_20"),
                "r_vol": r.get("r_vol"),
                "wyckoff_phase": "تجميع مؤسسي (CMF & Volume Accumulation)",
                "close": close,
                "change_pct": chg,
                "rsi_14": rsi,
                "support_1": r.get("support_1"),
                "resistance_1": r.get("resistance_1"),
                "support_2": r.get("support_2"),
                "resistance_2": r.get("resistance_2"),
                "stop_loss": r.get("stop_loss"),
                "king_ai_score": _normalize_king_ai_score(r.get("king_ai_score")),
                "verdict": verdict,
                "date": r.get("date"),
                "is_sharia_compliant": None,
            })

        return {
            "status": "success",
            "market": ui_mkt,
            "exchange": eff_mkt,
            "currency": currency,
            "accumulation_stocks": stocks,
            "stocks": stocks,
            "data_source": "computed_from_ohlcv_cmf",
        }

    # ── EGX (preserved existing logic) ───────────────────────────────────────
    sb = _get_sb()
    try:
        latest_scan_date = _get_latest_table_date(sb, "stock_scans_summary", "scan_date", exchange=None)
        query = (
            sb.from_("stock_scans_summary")
            .select("symbol,scan_date,acc_score,dist_score,wyckoff_phase,vol_ratio,signal,consecutive_acc_days")
            .gte("acc_score", 50)
            .neq("wyckoff_phase", "distribution")
        )
        if latest_scan_date:
            query = query.eq("scan_date", latest_scan_date)
        res = query.order("acc_score", desc=True).limit(30).execute()
        rows = res.data or []
    except Exception as e:
        return {"status": "error", "message": f"تعذر جلب أسهم التجميع: {str(e)}"}

    stocks = []
    seen = set()
    for r in rows:
        sym = r.get("symbol")
        if not sym or sym in seen:
            continue
        acc_val = _safe_float(r.get("acc_score")) or 0.0
        dist_val = _safe_float(r.get("dist_score")) or 0.0
        phase = str(r.get("wyckoff_phase") or "").lower()
        if phase == "distribution" or dist_val > acc_val:
            continue
        seen.add(sym)

        if sharia_only and not is_sharia_compliant(sym):
            continue

        stocks.append({
            "symbol": sym,
            "market": "EGX",
            "exchange": "EGX",
            "currency": _reg_currency_for_symbol(sym, "EGX"),
            "accumulation_score": _safe_float(r.get("acc_score")),
            "distribution_score": _safe_float(r.get("dist_score")),
            "wyckoff_phase": r.get("wyckoff_phase") or "تجميع مؤسسي (Accumulation)",
            "consecutive_acc_days": r.get("consecutive_acc_days") or 1,
            "date": r.get("scan_date"),
            "is_sharia_compliant": is_sharia_compliant(sym),
        })
        if len(stocks) >= 10:
            break

    acc_symbols = [s["symbol"] for s in stocks]
    if acc_symbols:
        try:
            res_ti = (
                sb.from_("stock_technical_indicators")
                .select("symbol,close,change_pct,rsi_14,bb_lower,bb_upper,king_ai_score,egx_ai_score,date")
                .eq("exchange", "EGX")
                .in_("symbol", acc_symbols)
                .order("date", desc=True)
                .limit(len(acc_symbols) * 3)
                .execute()
            )
            ti_map = {}
            for row in (res_ti.data or []):
                s_sym = row.get("symbol")
                if s_sym not in ti_map:
                    ti_map[s_sym] = row
            for s in stocks:
                s_sym = s["symbol"]
                ti = ti_map.get(s_sym, {})
                close = _safe_price(ti.get("close"))
                change_pct = _safe_float(ti.get("change_pct"))
                rsi = _safe_float(ti.get("rsi_14"))
                bb_low = _safe_price(ti.get("bb_lower"))
                bb_up = _safe_price(ti.get("bb_upper"))
                s1 = bb_low if bb_low else (_safe_price(close * 0.96) if close else None)
                r1 = bb_up if bb_up else (_safe_price(close * 1.05) if close else None)

                if change_pct is not None and change_pct > 0 and rsi is not None and 45 <= rsi <= 68:
                    verdict = "🟢 إيجابي / فرصة جيدة"
                elif (change_pct is not None and change_pct < -2) or (rsi is not None and rsi > 75):
                    verdict = "🔴 سلبي / مخاطرة مرتفعة"
                else:
                    verdict = "🟡 حيادي للمراقبة"

                stock_name_ar = _alias_name_for_symbol(s_sym, market="EGX")
                clean_name = (stock_name_ar or s_sym).split(",")[0].strip()

                s["name"] = clean_name
                s["name_ar"] = clean_name
                s["close"] = close
                s["change_pct"] = change_pct
                s["rsi_14"] = rsi
                s["support_1"] = s1
                s["resistance_1"] = r1
                s["support_2"] = _safe_price(s1 * 0.96) if s1 else None
                s["resistance_2"] = _safe_price(r1 * 1.05) if r1 else None
                s["stop_loss"] = _safe_price(s1 * 0.98) if s1 else None
                s["king_ai_score"] = _normalize_king_ai_score(ti.get("king_ai_score"))
                s["egx_ai_score"] = _normalize_king_ai_score(ti.get("egx_ai_score"))
                s["verdict"] = verdict
        except Exception:
            pass

    return {
        "status": "success",
        "market": ui_mkt,
        "exchange": "EGX",
        "currency": currency,
        "accumulation_stocks": stocks,
        "stocks": stocks,
    }


async def execute_get_accumulation_stocks(
    sharia_only: bool = False,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_accumulation_stocks, sharia_only, market)


# ---------------------------------------------------------------------------
# Tool: get_news
# ---------------------------------------------------------------------------
def _sync_get_news(
    symbols: Optional[List[str]] = None,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    eff_mkt = _resolve_effective_market(market=market, symbols=symbols)
    ui_mkt = _ui_market_label(eff_mkt)
    currency = _currency_for_market(eff_mkt)

    if eff_mkt != "EGX":
        cfg = _reg_get_market_config(eff_mkt)
        sb_sa = _get_sb_for_market(eff_mkt)
        if sb_sa is None:
            return _market_unconfigured_error(eff_mkt)
        # Check whether news/disclosures tables exist before querying (avoid SELECT *)
        desired_news_cols = [
            "symbol", "company_name", "title", "summary", "ai_summary",
            "sentiment", "sentiment_score", "news_count", "headlines", "sources",
            "date", "disclosure_date", "published_at", "source_url", "exchange",
        ]
        news_tbl = None
        news_tbl_cols = None
        for cand_tbl in ("market_news", "stock_news_sentiment"):
            cset = _get_saudi_table_columns(cand_tbl, sb_sa)
            if cset is not None:
                news_tbl = cand_tbl
                news_tbl_cols = cset
                break
        news_items: List[Dict[str, Any]] = []
        if news_tbl and news_tbl_cols:
            try:
                sel_cols = ",".join([c for c in desired_news_cols if c in news_tbl_cols]) or "symbol,date"
                q = sb_sa.from_(news_tbl).select(sel_cols)
                if "exchange" in news_tbl_cols:
                    q = q.eq("exchange", eff_mkt)
                if symbols:
                    mkt_syms = _group_symbols_by_exchange(symbols).get(eff_mkt, [])
                    if mkt_syms:
                        q = q.in_("symbol", mkt_syms[:10])
                order_field = (
                    "published_at" if "published_at" in news_tbl_cols
                    else ("disclosure_date" if "disclosure_date" in news_tbl_cols
                          else ("date" if "date" in news_tbl_cols else None))
                )
                if order_field:
                    q = q.order(order_field, desc=True)
                res = q.limit(10).execute()
                news_items = res.data or []
            except Exception:
                news_items = []
        out: Dict[str, Any] = {
            "status": "success",
            "market": ui_mkt,
            "exchange": eff_mkt,
            "currency": currency,
            "count": len(news_items),
            "news": news_items,
        }
        if not news_items:
            site_hint = f" عبر {cfg.official_site}" if cfg.official_site else ""
            out["note"] = (
                f"أخبار وإفصاحات {cfg.name_ar} ({ui_mkt}) غير مخزنة حالياً في قاعدة البيانات. "
                f"يمكن للمستخدم متابعة الإفصاحات الرسمية{site_hint} بينما نواصل تغطية التحليل الفني والأسعار لـ{cfg.name_ar}."
            )
        return out

    # ── EGX: query egx_disclosures + stock_news_sentiment cleanly ────────────
    sb = _get_sb()
    news_items = []
    egx_syms, _ = _split_symbols_by_market(symbols)
    try:
        q_disc = (
            sb.from_("egx_disclosures")
            .select("symbol,company_name,disclosure_type,disclosure_date,title,ai_summary,sentiment,source_url")
            .order("disclosure_date", desc=True)
            .limit(8)
        )
        if egx_syms:
            q_disc = q_disc.in_("symbol", egx_syms[:10])
        res = q_disc.execute()
        for r in (res.data or []):
            news_items.append({
                "symbol": r.get("symbol"),
                "company_name": r.get("company_name"),
                "title": r.get("title"),
                "summary": r.get("ai_summary"),
                "sentiment": r.get("sentiment"),
                "type": r.get("disclosure_type"),
                "date": r.get("disclosure_date"),
                "source_url": r.get("source_url"),
            })
    except Exception:
        pass

    if not news_items:
        try:
            q_sent = (
                sb.from_("stock_news_sentiment")
                .select("symbol,date,sentiment_score,news_count,headlines,sources")
                .eq("exchange", "EGX")
                .order("date", desc=True)
                .limit(6)
            )
            if egx_syms:
                q_sent = q_sent.in_("symbol", egx_syms[:10])
            res_s = q_sent.execute()
            for r in (res_s.data or []):
                headlines = r.get("headlines") or []
                first_hl = headlines[0] if isinstance(headlines, list) and headlines else None
                news_items.append({
                    "symbol": r.get("symbol"),
                    "title": first_hl or f"ملخص أخبار {r.get('symbol')}",
                    "headlines": headlines[:3] if isinstance(headlines, list) else [],
                    "sentiment_score": r.get("sentiment_score"),
                    "news_count": r.get("news_count"),
                    "date": r.get("date"),
                })
        except Exception:
            pass

    return {
        "status": "success",
        "market": ui_mkt,
        "exchange": "EGX",
        "currency": currency,
        "count": len(news_items),
        "news": news_items,
    }


async def execute_get_news(
    symbols: Optional[List[str]] = None,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_news, symbols, market)


# ---------------------------------------------------------------------------
# Tool: get_comparison
# ---------------------------------------------------------------------------
def _sync_get_comparison(symbols: List[str]) -> Dict[str, Any]:
    grouped = _group_symbols_by_exchange(symbols)
    if not grouped:
        return {"status": "error", "message": "لم يتم تحديد رموز أسهم صالحة للمقارنة"}

    stock_res = _sync_get_stock(symbols)
    stocks = stock_res.get("stocks", [])
    try:
        fv_map: Dict[Tuple[str, Any], Dict[str, Any]] = {}
        for exch_code, mkt_syms in grouped.items():
            if not mkt_syms:
                continue
            ui_code = _ui_market_label(exch_code)
            fv_res = _sync_get_fair_value(
                symbols=mkt_syms,
                mode="specific_stocks",
                limit=len(mkt_syms) + 2,
                market=ui_code,
            )
            for it in (fv_res.get("fair_value_stocks") or []):
                if isinstance(it, dict) and it.get("symbol"):
                    fv_map[(str(it["symbol"]).upper(), it.get("market") or ui_code)] = it

        for s in stocks:
            fv_it = fv_map.get((str(s.get("symbol") or "").upper(), s.get("market")))
            if fv_it:
                if fv_it.get("fair_value") is not None:
                    s["fair_value"] = fv_it.get("fair_value")
                if fv_it.get("upside_pct") is not None:
                    s["upside_pct"] = fv_it.get("upside_pct")
                val_status = fv_it.get("status_ar") or fv_it.get("status")
                if val_status:
                    s["valuation_status"] = val_status
    except Exception:
        pass

    mkts_present = sorted(list({s.get("market") for s in stocks if s.get("market")}))
    res: Dict[str, Any] = {
        "status": "success",
        "markets": mkts_present,
        "cross_market": len(mkts_present) > 1,
        "stocks": stocks,
    }
    if stock_res.get("warnings"):
        res["warnings"] = stock_res["warnings"]
    return res


async def execute_get_comparison(symbols: List[str]) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_comparison, symbols)


# ---------------------------------------------------------------------------
# Tool: get_fair_value
# ---------------------------------------------------------------------------
def _sync_get_fair_value(
    symbols: Optional[List[str]] = None,
    mode: str = "screen_undervalued",
    sharia_only: bool = False,
    limit: int = 10,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    eff_mkt = _resolve_effective_market(market=market, symbols=symbols)
    ui_mkt = _ui_market_label(eff_mkt)
    currency = _currency_for_market(eff_mkt)

    if eff_mkt != "EGX":
        cfg = _reg_get_market_config(eff_mkt)
        sb_sa = _get_sb_for_market(eff_mkt)
        if sb_sa is None:
            return _market_unconfigured_error(eff_mkt)

        rows: List[Dict[str, Any]] = []
        mkt_syms = _group_symbols_by_exchange(symbols).get(eff_mkt, []) if symbols else []
        try:
            ti_cols_str, order_col = _saudi_ti_select_and_order(sb_sa)
            ti_cols = set(ti_cols_str.split(","))
            q = (
                sb_sa.from_("stock_technical_indicators")
                .select(ti_cols_str)
                .eq("exchange", eff_mkt)
            )
            if mkt_syms:
                q = q.in_("symbol", mkt_syms)
            elif "date" in ti_cols:
                ld = _get_latest_table_date(sb_sa, "stock_technical_indicators", "date", eff_mkt)
                if ld:
                    q = q.eq("date", ld)
            scan_row_cap = max(50, len(mkt_syms) * 3) if mkt_syms else 320
            res = q.order(order_col, desc=True).limit(scan_row_cap).execute()
            rows = res.data or []
        except Exception:
            rows = []

        if not rows:
            if mkt_syms:
                ohlcv_map = _fetch_saudi_ohlcv_for_symbols(sb_sa, mkt_syms, limit_per_sym=60, exchange=eff_mkt)
                for s_sym in mkt_syms:
                    calc = _compute_indicators_from_price_rows(ohlcv_map.get(s_sym, []))
                    if calc:
                        calc["symbol"] = s_sym
                        rows.append(calc)
            else:
                rows = _get_saudi_computed_market_indicators(sb_sa, lookback_days=22, exchange=eff_mkt)

        fv_syms_sa = [r.get("symbol") for r in rows[:320] if r.get("symbol")]
        names_map = _fetch_saudi_names_map(sb_sa, fv_syms_sa, exchange=eff_mkt)
        fv_fund_sa: Dict[str, Dict[str, Any]] = {}
        if fv_syms_sa:
            try:
                f_res_sa = (
                    sb_sa.from_("stock_fundamentals")
                    .select("symbol,data")
                    .eq("exchange", eff_mkt)
                    .in_("symbol", fv_syms_sa)
                    .limit(len(fv_syms_sa) + 5)
                    .execute()
                )
                for fr in (f_res_sa.data or []):
                    if isinstance(fr, dict) and fr.get("symbol") and isinstance(fr.get("data"), dict):
                        fv_fund_sa[str(fr["symbol"]).upper()] = fr["data"]
            except Exception:
                pass
        items = []
        seen = set()
        for r in rows:
            sym = r.get("symbol")
            if not sym or sym in seen:
                continue
            seen.add(sym)

            close = _safe_price(r.get("close"))
            if not close or close <= 0:
                continue

            vwap = _safe_price(r.get("vwap_20")) or close
            ema = _safe_price(r.get("ema_50")) or close
            ema200_sa = _safe_price(r.get("ema_200"))
            fair_value, fv_model, fv_extra = _compute_fundamental_fair_value(
                close,
                vwap,
                ema,
                fv_fund_sa.get(str(sym).upper()),
                market=eff_mkt,
                symbol=str(sym),
                ema_200=ema200_sa,
            )
            loss_making_sa = bool(fv_extra.get("is_loss_making") or fv_extra.get("loss_making_discount_applied"))
            gap_info = _build_fair_value_gap(close, fair_value, is_loss_making=loss_making_sa)
            upside = gap_info["upside_pct"]
            nm = names_map.get(sym, {})
            clean_name = (nm.get("name_ar") or _alias_name_for_symbol(sym, eff_mkt) or nm.get("name") or sym).split(",")[0].strip()
            if loss_making_sa:
                st_code = "overvalued"
                st_ar = "شركة خاسرة — تقييم دفتري مخفّض ⚠️"
            else:
                st_code = "undervalued" if upside >= 15 else ("overvalued" if upside <= -12 else "fair")
                st_ar = "أقل من السعر العادل (رخيص) 🟢" if upside >= 15 else ("أعلى من السعر العادل (متضخم) 🔴" if upside <= -12 else "في النطاق العادل ⚖️")

            items.append({
                "symbol": sym,
                "name": clean_name,
                "market": ui_mkt,
                "exchange": eff_mkt,
                "currency": currency,
                "current_price": close,
                "fair_value": fair_value,
                **gap_info,
                "status": st_code,
                "status_ar": st_ar,
                "model": fv_model,
                "is_sharia_compliant": None,
                **fv_extra,
                "graham_gap_ar": _build_graham_gap_ar(close, fv_extra.get("graham_value")),
            })

        if mode == "screen_undervalued":
            items.sort(key=lambda x: x["upside_pct"], reverse=True)
        elif mode == "screen_overvalued":
            items.sort(key=lambda x: x["upside_pct"], reverse=False)

        out: Dict[str, Any] = {
            "status": "success",
            "market": ui_mkt,
            "exchange": eff_mkt,
            "currency": currency,
            "fair_value_stocks": items[:limit],
        }
        if sharia_only:
            out["sharia_note"] = f"تصنيف الشريعة لأسهم {cfg.name_ar} قيد الإضافة؛ تم حساب السعر العادل لجميع الأسهم المتاحة."
        return out

    # ── EGX (preserved existing logic) ───────────────────────────────────────
    sb = _get_sb()
    try:
        latest_date = None if symbols else _get_latest_table_date(sb, "stock_technical_indicators", "date", "EGX")
        query = (
            sb.from_("stock_technical_indicators")
            .select("symbol,close,change_pct,vwap_20,ema_50,ema_200,date")
            .eq("exchange", "EGX")
        )
        if latest_date:
            query = query.eq("date", latest_date)
        if symbols:
            clean_syms = [_normalize_symbol(s) for s in symbols if s][:25]
            query = query.in_("symbol", clean_syms).order("date", desc=True).limit(max(50, len(clean_syms) * 3))
        else:
            query = query.order("date", desc=True).limit(320)
        res = query.execute()
        rows = res.data or []
    except Exception as e:
        return {"status": "error", "message": f"تعذر حساب السعر العادل: {str(e)}"}

    fv_syms_egx = [str(r.get("symbol")).upper() for r in rows[:320] if r.get("symbol")]
    fv_fund_egx: Dict[str, Dict[str, Any]] = {}
    if fv_syms_egx:
        try:
            f_res_egx = (
                sb.from_("stock_fundamentals")
                .select("symbol,data")
                .eq("exchange", "EGX")
                .in_("symbol", fv_syms_egx)
                .limit(len(fv_syms_egx) + 5)
                .execute()
            )
            for fr in (f_res_egx.data or []):
                if isinstance(fr, dict) and fr.get("symbol") and isinstance(fr.get("data"), dict):
                    fv_fund_egx[str(fr["symbol"]).upper()] = fr["data"]
        except Exception:
            pass

    items = []
    seen = set()
    for r in rows:
        sym = r.get("symbol")
        if not sym or sym in seen:
            continue
        seen.add(sym)

        if sharia_only and not is_sharia_compliant(sym):
            continue

        close = _safe_price(r.get("close"))
        if not close or close <= 0:
            continue

        vwap = _safe_price(r.get("vwap_20")) or close
        ema = _safe_price(r.get("ema_50")) or close
        ema200_egx = _safe_price(r.get("ema_200"))
        fair_value, fv_model, fv_extra = _compute_fundamental_fair_value(
            close,
            vwap,
            ema,
            fv_fund_egx.get(str(sym).upper()),
            market="EGX",
            symbol=str(sym),
            ema_200=ema200_egx,
        )
        loss_making_egx = bool(fv_extra.get("is_loss_making") or fv_extra.get("loss_making_discount_applied"))
        gap_info = _build_fair_value_gap(close, fair_value, is_loss_making=loss_making_egx)
        upside = gap_info["upside_pct"]
        sym_ar, sym_en = _resolve_symbol_display_names(sym, "EGX")
        if loss_making_egx:
            st_code_egx = "overvalued"
            st_ar_egx = "شركة خاسرة — تقييم دفتري مخفّض ⚠️"
        else:
            st_code_egx = "undervalued" if upside >= 15 else ("overvalued" if upside <= -12 else "fair")
            st_ar_egx = "أقل من السعر العادل (رخيص) 🟢" if upside >= 15 else ("أعلى من السعر العادل (متضخم) 🔴" if upside <= -12 else "في النطاق العادل ⚖️")

        items.append({
            "symbol": sym,
            "name": sym_en or sym_ar or sym,
            "name_ar": sym_ar or sym_en or sym,
            "market": "EGX",
            "exchange": "EGX",
            "currency": _reg_currency_for_symbol(sym, "EGX"),
            "current_price": close,
            "fair_value": fair_value,
            **gap_info,
            "status": st_code_egx,
            "status_ar": st_ar_egx,
            "model": fv_model,
            "is_sharia_compliant": is_sharia_compliant(sym),
            **fv_extra,
            "graham_gap_ar": _build_graham_gap_ar(close, fv_extra.get("graham_value")),
        })

    if mode == "screen_undervalued":
        items.sort(key=lambda x: x["upside_pct"], reverse=True)
    elif mode == "screen_overvalued":
        items.sort(key=lambda x: x["upside_pct"], reverse=False)

    return {
        "status": "success",
        "market": ui_mkt,
        "exchange": "EGX",
        "currency": currency,
        "fair_value_stocks": items[:limit],
    }


async def execute_get_fair_value(
    symbols: Optional[List[str]] = None,
    mode: str = "screen_undervalued",
    sharia_only: bool = False,
    limit: int = 10,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_fair_value, symbols, mode, sharia_only, limit, market)


# ---------------------------------------------------------------------------
# Tool: get_dividends (4-Market Upcoming & Recent Cash Dividend Calendar)
# ---------------------------------------------------------------------------
def _div_market_key(market: Optional[str]) -> str:
    m = str(market or _ACTIVE_MARKET_CTX.get() or "EGX").strip().upper()
    if m in ("TADAWUL", "TASI", "SA", "SAUDI"):
        return "tasi"
    if m in ("QSE", "QE", "QATAR"):
        return "qatar"
    if m in ("DFM", "ADX", "UAE"):
        return "uae"
    return "egx"


def _load_dividends_calendar_cached(market_key: str) -> Dict[str, Any]:
    ck = f"div_cal:{market_key}"
    cached = _get_tool_cached(ck)
    if cached is not None:
        return cached
    try:
        from api.dividends_engine import get_cached_market_dividends
        data = get_cached_market_dividends(market_key)
        if isinstance(data, dict) and data.get("dividends"):
            _set_tool_cached(ck, data)
            return data
    except Exception:
        pass
    return {"market": market_key, "dividends": [], "summary": {}}


def _dividend_entitlement_rule_ar(ex_date: Any, record_date: Any = None) -> str:
    ex_s = str(ex_date or "غير محدد")[:10]
    rec_s = str(record_date or "غير محدد")[:10]
    return (
        f"قاعدة استحقاق الكوبون الحتمية: يوم التداول بدون كوبون (Ex-Date: {ex_s}) هو أول جلسة لا يستحق فيها المشتري الجديد الكوبون؛ "
        f"أما مالك السهم عند إغلاق آخر جلسة تسبق الـ Ex-Date فيستحق الكوبون كاملاً حتى لو باع أسهمه في يوم الـ Ex-Date نفسه ({ex_s}) أو بعده. "
        f"تاريخ التسجيل (Record Date: {rec_s}) تاريخ مقاصة إداري وليس آخر يوم للشراء أو البيع."
    )


def _lookup_upcoming_dividend(symbol: str, market: Optional[str] = "EGX") -> Optional[Dict[str, Any]]:
    """Fast O(1) cached lookup for a stock's upcoming or pending-pay cash dividend."""
    if not symbol:
        return None
    sym_u = str(symbol).strip().upper().split(".")[0]
    mkey = _div_market_key(market)
    cal = _load_dividends_calendar_cached(mkey)
    for item in cal.get("dividends") or []:
        if str(item.get("symbol") or "").upper() == sym_u:
            if item.get("status") in ("upcoming", "pending_pay"):
                return {
                    "symbol": sym_u,
                    "exchange": item.get("exchange"),
                    "amount": item.get("amount"),
                    "currency": item.get("currency"),
                    "currency_ar": item.get("currency_ar"),
                    "ex_date": item.get("ex_date"),
                    "record_date": item.get("record_date"),
                    "pay_date": item.get("pay_date"),
                    "yield_pct": item.get("yield_pct"),
                    "days_until_ex": item.get("days_until_ex"),
                    "status": item.get("status"),
                    "entitlement_rule_ar": _dividend_entitlement_rule_ar(item.get("ex_date"), item.get("record_date")),
                }
            break
    return None


def _sync_get_dividends(
    symbols: Optional[List[str]] = None,
    upcoming_only: bool = True,
    limit: int = 15,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    lim = max(1, min(30, int(limit or 15)))
    mkey = _div_market_key(market)
    cal = _load_dividends_calendar_cached(mkey)
    all_rows = cal.get("dividends") or []

    def _with_rule(rows_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out_rows = []
        for r in rows_list:
            if not isinstance(r, dict):
                continue
            item = dict(r)
            item["entitlement_rule_ar"] = _dividend_entitlement_rule_ar(r.get("ex_date"), r.get("record_date"))
            out_rows.append(item)
        return out_rows

    if symbols:
        want = {_normalize_symbol(s) for s in symbols if s}
        matched = [r for r in all_rows if str(r.get("symbol") or "").upper() in want]
        # Cross-market fallback if user asked about a GCC stock while active market is EGX
        if not matched:
            for alt_m in ("tasi", "qatar", "uae", "egx"):
                if alt_m == mkey:
                    continue
                alt_cal = _load_dividends_calendar_cached(alt_m)
                alt_hits = [r for r in (alt_cal.get("dividends") or []) if str(r.get("symbol") or "").upper() in want]
                if alt_hits:
                    matched = alt_hits
                    mkey = alt_m
                    cal = alt_cal
                    break
        return {
            "status": "success",
            "market": mkey.upper(),
            "updated_at": cal.get("updatedAt"),
            "entitlement_rule_general_ar": "مالك السهم عند إغلاق آخر جلسة قبل الـ Ex-Date يستحق الكوبون كاملاً حتى لو باع يوم الـ Ex-Date نفسه أو بعده؛ المشتري يوم Ex-Date لا يستحق.",
            "dividends": _with_rule(matched[:lim]),
            "calendar_url": "/dividends" if mkey == "egx" else f"/dividends/{mkey}",
        }

    filtered = (
        [r for r in all_rows if r.get("status") in ("upcoming", "pending_pay")]
        if upcoming_only
        else all_rows
    )
    if upcoming_only and not filtered:
        # Fallback to latest recent payouts so user always sees rich data
        filtered = all_rows[:lim]
    return {
        "status": "success",
        "market": mkey.upper(),
        "updated_at": cal.get("updatedAt"),
        "entitlement_rule_general_ar": "مالك السهم عند إغلاق آخر جلسة قبل الـ Ex-Date يستحق الكوبون كاملاً حتى لو باع يوم الـ Ex-Date نفسه أو بعده؛ المشتري يوم Ex-Date لا يستحق.",
        "summary": cal.get("summary") or {},
        "dividends": _with_rule(filtered[:lim]),
        "calendar_url": "/dividends" if mkey == "egx" else f"/dividends/{mkey}",
    }


async def execute_get_dividends(
    symbols: Optional[List[str]] = None,
    upcoming_only: bool = True,
    limit: int = 15,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_dividends, symbols, upcoming_only, limit, market)


# ---------------------------------------------------------------------------
# Tool: get_sharia_cleanser
# ---------------------------------------------------------------------------
def _sync_get_sharia_cleanser(
    symbol: str,
    shares_count: float = 1000.0,
    coupon_per_share: Optional[float] = None,
    purification_rate_pct: Optional[float] = None,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    clean_sym, sym_mkt = _resolve_symbol_and_market(symbol, explicit_market=market)
    eff_mkt = _normalize_market_code(market) if market else sym_mkt
    try:
        shares = float(shares_count) if shares_count is not None else 1000.0
    except Exception:
        shares = 1000.0
    if shares <= 0:
        shares = 1000.0

    close_px: Optional[float] = None
    try:
        stock_res = _sync_get_stock([clean_sym], market=eff_mkt)
        row = (stock_res.get("stocks") or [{}])[0]
        if isinstance(row, dict):
            close_px = _safe_price(row.get("close"))
    except Exception:
        close_px = None

    market_value = round(shares * close_px, 2) if (close_px and close_px > 0) else None
    zakat_amount = round(market_value * 0.025, 2) if market_value is not None else None

    coupon: Optional[float] = None
    coupon_source: Optional[str] = None
    if coupon_per_share is not None:
        try:
            c_val = float(coupon_per_share)
            if c_val > 0:
                coupon = c_val
                coupon_source = "user"
        except Exception:
            pass
    if coupon is None:
        try:
            up_div = _lookup_upcoming_dividend(clean_sym, eff_mkt)
            if isinstance(up_div, dict) and up_div.get("amount"):
                amt = _safe_float(up_div.get("amount"), 4)
                if amt and amt > 0:
                    coupon = amt
                    coupon_source = "upcoming_dividend"
        except Exception:
            pass
    total_coupon = round(shares * coupon, 2) if coupon is not None else None

    rate: Optional[float] = None
    if purification_rate_pct is not None:
        try:
            r_val = float(purification_rate_pct)
            if r_val >= 0:
                rate = r_val
        except Exception:
            pass
    purification_amount = (
        round(total_coupon * (rate / 100.0), 2)
        if (total_coupon is not None and rate is not None)
        else None
    )

    zakat_basis_ar = "الزكاة الاسترشادية = 2.5% من القيمة السوقية للأسهم (عدد الأسهم × سعر الإغلاق)"
    purif_note_ar = (
        "نسبة التطهير المعتمدة لهذا السهم غير متوفرة في قاعدة البيانات — لم نفترض أي نسبة؛ أدخل النسبة من القوائم المالية أو راجع [حاسبة التوافق الشرعي](/sharia)"
        if rate is None
        else None
    )

    if eff_mkt != "EGX":
        cfg = _reg_get_market_config(eff_mkt)
        sb_sa = _get_sb_for_market(eff_mkt)
        sharia_mkt: Optional[bool] = None
        if sb_sa is not None and clean_sym:
            try:
                res_sf = (
                    sb_sa.from_("stock_fundamentals")
                    .select("data")
                    .eq("exchange", eff_mkt)
                    .eq("symbol", clean_sym)
                    .limit(1)
                    .execute()
                )
                if res_sf.data and isinstance(res_sf.data[0].get("data"), dict):
                    val = res_sf.data[0]["data"].get("is_sharia_compliant")
                    if val is not None:
                        sharia_mkt = bool(val)
            except Exception:
                pass
        if sharia_mkt is True:
            verdict_ar = f"السهم مصنف كمتوافق مع الضوابط الشرعية في {cfg.name_ar}"
            idx_lbl = cfg.sharia_index
        elif sharia_mkt is False:
            verdict_ar = "السهم غير مصنف ضمن قائمة الأسهم الشرعية المعتمدة"
            idx_lbl = "غير متوافق"
        else:
            verdict_ar = (
                f"تصنيف الشريعة الرسمي للسهم في {cfg.name_ar} غير متوفر حالياً في القاعدة؛ "
                f"الزكاة الاسترشادية محسوبة بعملة السوق ({cfg.currency_ar}) على القيمة السوقية"
            )
            idx_lbl = f"قيد المراجعة الشرعية ({cfg.ui_code})"

        out_sharia: Dict[str, Any] = {
            "status": "success",
            "market": cfg.ui_code,
            "exchange": eff_mkt,
            "currency": cfg.currency_ar,
            "symbol": clean_sym,
            "is_sharia_compliant": sharia_mkt,
            "sharia_index": idx_lbl,
            "shares_count": shares,
            "close_price": close_px,
            "market_value": market_value,
            "coupon_per_share": coupon,
            "coupon_source": coupon_source,
            "total_dividends": total_coupon,
            "purification_rate_pct": rate,
            "purification_amount": purification_amount,
            "zakat_amount": zakat_amount,
            "zakat_basis_ar": zakat_basis_ar,
            "verdict_ar": verdict_ar,
        }
        if purif_note_ar:
            out_sharia["purification_note_ar"] = purif_note_ar
        if sharia_mkt is False:
            out_sharia["sharia_note_ar"] = "السهم غير متوافق شرعياً؛ التطهير لا يجعله متوافقاً"
        if eff_mkt == "TADAWUL":
            out_sharia["purification_amount_sar"] = purification_amount
            out_sharia["zakat_amount_sar"] = zakat_amount
        return out_sharia

    sharia = is_sharia_compliant(clean_sym)
    out_egx: Dict[str, Any] = {
        "status": "success",
        "market": "EGX",
        "exchange": "EGX",
        "currency": "ج.م",
        "symbol": clean_sym,
        "is_sharia_compliant": sharia,
        "sharia_index": "EGX33 Shariah" if sharia else "غير مدرج بمؤشر الشريعة",
        "shares_count": shares,
        "close_price": close_px,
        "market_value": market_value,
        "coupon_per_share": coupon,
        "coupon_source": coupon_source,
        "total_dividends": total_coupon,
        "purification_rate_pct": rate,
        "purification_amount": purification_amount,
        "purification_amount_egp": purification_amount,
        "zakat_amount": zakat_amount,
        "zakat_amount_egp": zakat_amount,
        "zakat_basis_ar": zakat_basis_ar,
        "verdict_ar": "السهم متوافق مع معايير الشريعة الإسلامية ومؤشر EGX33" if sharia else "السهم غير مصنف ضمن أسهم الشريعة المعتمدة EGX33",
    }
    if purif_note_ar:
        out_egx["purification_note_ar"] = purif_note_ar
    if sharia is False:
        out_egx["sharia_note_ar"] = "السهم غير متوافق شرعياً؛ التطهير لا يجعله متوافقاً"
    return out_egx


async def execute_get_sharia_cleanser(
    symbol: str,
    shares_count: float = 1000.0,
    coupon_per_share: Optional[float] = None,
    purification_rate_pct: Optional[float] = None,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        _sync_get_sharia_cleanser, symbol, shares_count, coupon_per_share, purification_rate_pct, market
    )


# ---------------------------------------------------------------------------
# Tool: calculate_position
# ---------------------------------------------------------------------------
def _sync_calculate_position(
    symbol: str,
    quantity: Optional[float] = None,
    entry_price: Optional[float] = None,
    total_cost: Optional[float] = None,
    dca_budget: Optional[float] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    clean_sym, sym_mkt = _resolve_symbol_and_market(symbol)
    ui_mkt = _ui_market_label(sym_mkt)
    currency = _currency_for_market(sym_mkt)

    quantity_source: Optional[str] = None
    if quantity is None and total_cost is None and not _GROUP_PORTFOLIO_BLOCKED_CTX.get():
        effective_tg_id = _TG_PORTFOLIO_CTX.get()
        sb_pf = _get_sb()
        if sb_pf is not None and (user_id or effective_tg_id is not None):
            try:
                found_qty = 0.0
                weighted_cost = 0.0
                weighted_qty = 0.0
                if effective_tg_id is not None:
                    tg_state = _load_tg_portfolio_state(sb_pf, int(effective_tg_id))
                    for row in (tg_state.get("positions") or []):
                        rsym = _resolve_symbol_and_market(str(row.get("symbol") or ""))[0]
                        if str(rsym or "").upper() == clean_sym:
                            rq = _safe_float(row.get("quantity")) or 0.0
                            re_p = _safe_float(row.get("entry_price")) or 0.0
                            if rq > 0:
                                found_qty += rq
                                if re_p > 0:
                                    weighted_cost += rq * re_p
                                    weighted_qty += rq
                elif user_id:
                    pos_res = (
                        sb_pf.from_("positions")
                        .select("quantity, entry_price")
                        .eq("user_id", user_id)
                        .eq("status", "open")
                        .eq("symbol", clean_sym)
                        .limit(5)
                        .execute()
                    )
                    for row in (pos_res.data or []):
                        rq = _safe_float(row.get("quantity")) or 0.0
                        re_p = _safe_float(row.get("entry_price")) or 0.0
                        if rq > 0:
                            found_qty += rq
                            if re_p > 0:
                                weighted_cost += rq * re_p
                                weighted_qty += rq
                if found_qty > 0:
                    quantity = found_qty
                    quantity_source = "user_portfolio"
                    if entry_price is None and weighted_qty > 0:
                        entry_price = round(weighted_cost / weighted_qty, 4)
            except Exception as pf_lookup_err:
                logger.debug(f"[calculate_position] Portfolio lookup skipped for {clean_sym}: {pf_lookup_err}")

    close = 1.0
    ohlcv_rows: List[Dict[str, Any]] = []
    if sym_mkt != "EGX":
        sb_sa = _get_sb_for_market(sym_mkt)
        if sb_sa is None:
            return _market_unconfigured_error(sym_mkt, {"symbol": clean_sym})
        try:
            _, order_col = _saudi_ti_select_and_order(sb_sa)
            res = (
                sb_sa.from_("stock_technical_indicators")
                .select(f"close,{order_col}")
                .eq("exchange", sym_mkt)
                .eq("symbol", clean_sym)
                .order(order_col, desc=True)
                .limit(1)
                .execute()
            )
            if res.data and res.data[0].get("close"):
                close = _safe_float(res.data[0].get("close")) or 1.0
            res_p = (
                sb_sa.from_("stock_prices")
                .select("high,low,close,date")
                .eq("exchange", sym_mkt)
                .eq("symbol", clean_sym)
                .order("date", desc=True)
                .limit(60)
                .execute()
            )
            ohlcv_rows = res_p.data or []
            if len(ohlcv_rows) < 20:
                merged_map = _backfill_saudi_ohlcv_from_storage(
                    sb_sa, sym_mkt, {clean_sym: ohlcv_rows}, [clean_sym], 60
                )
                ohlcv_rows = merged_map.get(clean_sym, ohlcv_rows)
            if close == 1.0 and ohlcv_rows and ohlcv_rows[0].get("close"):
                close = _safe_float(ohlcv_rows[0].get("close")) or 1.0
        except Exception:
            pass
    else:
        sb = _get_sb()
        try:
            res = (
                sb.from_("stock_technical_indicators")
                .select("close,date")
                .eq("exchange", "EGX")
                .eq("symbol", clean_sym)
                .order("date", desc=True)
                .limit(1)
                .execute()
            )
            if res.data and res.data[0].get("close"):
                close = _safe_float(res.data[0].get("close")) or 1.0
            res_p = (
                sb.from_("stock_prices")
                .select("high,low,close,date")
                .eq("exchange", "EGX")
                .eq("symbol", clean_sym)
                .order("date", desc=True)
                .limit(60)
                .execute()
            )
            ohlcv_rows = res_p.data or []
        except Exception:
            pass

    cost = total_cost or ((quantity or 0) * (entry_price or 0))
    qty = quantity or (cost / entry_price if entry_price else 0)
    current_val = qty * close
    profit_loss = round(current_val - cost, 2)
    profit_pct = round((profit_loss / cost * 100), 2) if cost > 0 else 0.0

    out: Dict[str, Any] = {
        "status": "success",
        "market": ui_mkt,
        "exchange": sym_mkt,
        "currency": currency,
        "symbol": clean_sym,
        "quantity": qty,
        "entry_price": entry_price,
        "close_price": close,
        "total_cost": round(cost, 2),
        "current_market_value": round(current_val, 2),
        "profit_loss": profit_loss,
        "profit_loss_pct": profit_pct,
    }
    if quantity_source:
        out["quantity_source"] = quantity_source
    if sym_mkt == "TADAWUL":
        out["profit_loss_sar"] = profit_loss
    elif sym_mkt == "EGX":
        out["profit_loss_egp"] = profit_loss

    eff_entry = float(entry_price or 0.0)
    if (eff_entry == 0.0 and qty > 0 and cost > 0):
        eff_entry = cost / qty
    wants_dca = bool((dca_budget and float(dca_budget) > 0) or (close > 0 and eff_entry > close * 1.015))
    if wants_dca and close > 0:
        try:
            from api.portfolio_or_optimizer import build_smart_dca_plan
            stock_info: Dict[str, Any] = {}
            stock_res = _sync_get_stock([clean_sym], market=sym_mkt)
            if isinstance(stock_res, dict) and isinstance(stock_res.get("stocks"), list) and stock_res["stocks"]:
                stock_info = stock_res["stocks"][0] or {}
            qi = stock_info.get("quant_intelligence") if isinstance(stock_info.get("quant_intelligence"), dict) else {}
            ref_used = qty <= 0
            eff_qty = float(qty) if qty > 0 else 100.0
            eff_stop = (
                stock_info.get("tactical_stop_loss")
                if stock_info.get("support_1_is_distant") and stock_info.get("tactical_stop_loss")
                else stock_info.get("stop_loss")
            )
            eps_chk = _safe_float(stock_info.get("eps"), 4)
            ni_chk = _safe_float(stock_info.get("net_income"), 2)
            loss_flag = bool(
                stock_info.get("is_loss_making")
                or (eps_chk is not None and eps_chk < 0)
                or (ni_chk is not None and ni_chk < 0)
            )
            out["smart_dca_plan"] = build_smart_dca_plan(
                symbol=clean_sym,
                exchange=sym_mkt,
                currency=currency,
                current_price=close,
                old_shares=eff_qty,
                old_avg_price=eff_entry if eff_entry > 0 else close,
                dca_budget=dca_budget,
                support_1=stock_info.get("support_1"),
                support_2=stock_info.get("support_2"),
                stop_loss=eff_stop,
                setup_regime=qi.get("setup_regime"),
                dist_score=stock_info.get("distribution_score"),
                fund_score=stock_info.get("fund_score"),
                is_loss_making=loss_flag,
                ohlcv_rows=ohlcv_rows,
                reference_shares_used=ref_used,
            )
        except Exception as dca_err:
            logger.debug(f"[calculate_position] Smart DCA skipped for {clean_sym}: {dca_err}")

    return out


async def execute_calculate_position(
    symbol: str,
    quantity: Optional[float] = None,
    entry_price: Optional[float] = None,
    total_cost: Optional[float] = None,
    dca_budget: Optional[float] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_calculate_position, symbol, quantity, entry_price, total_cost, dca_budget, user_id)


# ---------------------------------------------------------------------------
# Tool: get_price_traps
# ---------------------------------------------------------------------------
def _sync_get_price_traps(
    market: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 8,
) -> Dict[str, Any]:
    from api.trap_detector import detect_daily_traps

    eff_mkt = _resolve_effective_market(market=market, symbols=[symbol] if symbol else None)
    ui_mkt = _ui_market_label(eff_mkt)
    currency = _currency_for_market(eff_mkt)
    clean_sym = _resolve_symbol_and_market(symbol)[0] if symbol else None

    if eff_mkt != "EGX":
        sb_sa = _get_sb_for_market(eff_mkt)
        if sb_sa is None:
            return _market_unconfigured_error(eff_mkt)

        bars_by_sym: Dict[str, List[Dict[str, Any]]] = {}
        indicators: List[Dict[str, Any]] = []
        if clean_sym:
            ohlcv = _fetch_saudi_ohlcv_for_symbols(sb_sa, [clean_sym], limit_per_sym=60, exchange=eff_mkt)
            bars = ohlcv.get(clean_sym, [])
            bars_by_sym[clean_sym] = sorted(bars, key=lambda r: str(r.get("date") or ""))
            calc = _compute_indicators_from_price_rows(bars)
            if calc:
                calc["symbol"] = clean_sym
                indicators.append(calc)
        else:
            # Top active stocks in this exchange from 5-day OHLCV window for trap detection
            dates = _fetch_saudi_recent_dates(sb_sa, count=5, exchange=eff_mkt)
            if dates:
                try:
                    page_rows: List[Dict[str, Any]] = []
                    start_d = dates[-1]
                    for pg in range(2):
                        res_p = (
                            sb_sa.from_("stock_prices")
                            .select("symbol,date,open,high,low,close,volume")
                            .eq("exchange", eff_mkt)
                            .gte("date", start_d)
                            .order("date", desc=True)
                            .range(pg * 1000, pg * 1000 + 999)
                            .execute()
                        )
                        batch = res_p.data or []
                        page_rows.extend(batch)
                        if len(batch) < 1000:
                            break
                    for r in page_rows:
                        s = r.get("symbol")
                        if s:
                            bars_by_sym.setdefault(s, []).append(r)
                    for s, b_list in bars_by_sym.items():
                        b_list.sort(key=lambda r: str(r.get("date") or ""))
                        calc = _compute_indicators_from_price_rows(b_list)
                        if calc:
                            calc["symbol"] = s
                            indicators.append(calc)
                except Exception:
                    pass

        latest_bar_by_sym = {s: b_list[-1] for s, b_list in bars_by_sym.items() if b_list}
        detected = detect_daily_traps(indicators, latest_bar_by_sym, max_per_side=min(limit or 8, 15))
        return {
            "status": "success",
            "market": ui_mkt,
            "exchange": eff_mkt,
            "currency": currency,
            "symbol": clean_sym,
            **detected,
        }

    # ── EGX: read market_cache first, fallback to detect_daily_traps ─────────
    sb = _get_sb()
    payload: Optional[Dict[str, Any]] = None
    for ck in ("scanner_traps_EGX", "daily_traps_snapshot"):
        try:
            res_mc = sb.from_("market_cache").select("payload").eq("cache_key", ck).limit(1).execute()
            if res_mc.data and isinstance(res_mc.data[0].get("payload"), dict):
                payload = res_mc.data[0]["payload"]
                break
        except Exception:
            continue

    if payload is not None:
        bear_list = list(payload.get("bearTraps") or [])
        bull_list = list(payload.get("bullTraps") or [])
        if clean_sym:
            bear_list = [t for t in bear_list if str(t.get("symbol", "")).upper() == clean_sym]
            bull_list = [t for t in bull_list if str(t.get("symbol", "")).upper() == clean_sym]
        return {
            "status": "success",
            "market": ui_mkt,
            "exchange": "EGX",
            "currency": currency,
            "symbol": clean_sym,
            "asOf": payload.get("asOf"),
            "bearTraps": bear_list[:limit],
            "bullTraps": bull_list[:limit],
            "totalBearTraps": len(bear_list),
            "totalBullTraps": len(bull_list),
        }

    # Fallback: live bounded detection on EGX prices/indicators
    bars_by_sym = {}
    indicators = []
    try:
        q_ind = (
            sb.from_("stock_technical_indicators")
            .select("symbol,date,close,change_pct,volume,r_vol,rsi_14,cmf_20,vol_sma20")
            .eq("exchange", "EGX")
            .order("date", desc=True)
            .limit(30 if not clean_sym else 5)
        )
        if clean_sym:
            q_ind = q_ind.eq("symbol", clean_sym)
        ind_res = q_ind.execute()
        indicators = ind_res.data or []
        target_syms = [clean_sym] if clean_sym else list({r["symbol"] for r in indicators if r.get("symbol")})[:25]
        if target_syms:
            res_p = (
                sb.from_("stock_prices")
                .select("symbol,date,open,high,low,close,volume")
                .eq("exchange", "EGX")
                .in_("symbol", target_syms)
                .order("date", desc=True)
                .limit(min(len(target_syms) * 10, 500))
                .execute()
            )
            for r in (res_p.data or []):
                s = r.get("symbol")
                if s:
                    bars_by_sym.setdefault(s, []).append(r)
            for s in bars_by_sym:
                bars_by_sym[s].sort(key=lambda r: str(r.get("date") or ""))
    except Exception:
        pass

    latest_bar_by_sym = {s: b_list[-1] for s, b_list in bars_by_sym.items() if b_list}
    detected = detect_daily_traps(indicators, latest_bar_by_sym, max_per_side=min(limit or 8, 15))
    return {
        "status": "success",
        "market": ui_mkt,
        "exchange": "EGX",
        "currency": currency,
        "symbol": clean_sym,
        **detected,
    }


async def execute_get_price_traps(
    market: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 8,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_price_traps, market, symbol, limit)


# ---------------------------------------------------------------------------
# Tool: get_disclosures
# ---------------------------------------------------------------------------
def _sync_get_disclosures(
    symbol: Optional[str] = None,
    disclosure_type: Optional[str] = None,
    limit: int = 10,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    eff_mkt = _resolve_effective_market(market=market, symbols=[symbol] if symbol else None)
    ui_mkt = _ui_market_label(eff_mkt)
    currency = _currency_for_market(eff_mkt)
    clean_sym = _resolve_symbol_and_market(symbol)[0] if symbol else None

    if eff_mkt != "EGX":
        cfg = _reg_get_market_config(eff_mkt)
        sb_sa = _get_sb_for_market(eff_mkt)
        if sb_sa is None:
            return _market_unconfigured_error(eff_mkt)
        # Only query if disclosure table exists in schema
        disc_tbl = None
        disc_cols = None
        cand_tables = [
            "disclosures",
            f"{eff_mkt.lower()}_disclosures",
            f"{cfg.ui_code.lower()}_disclosures",
        ]
        # SAUDI_SUPABASE stores TADAWUL disclosures in `egx_disclosures`; NEVER let non-TADAWUL markets bleed from it!
        if eff_mkt == "TADAWUL" and sb_sa is not _get_sb():
            cand_tables.append("egx_disclosures")
        for cand in cand_tables:
            cset = _get_saudi_table_columns(cand, sb_sa)
            if cset is not None:
                # On shared DBs, non-TADAWUL generic `disclosures` table MUST have an `exchange` column
                if cand == "disclosures" and eff_mkt != "TADAWUL" and "exchange" not in cset:
                    continue
                disc_tbl = cand
                disc_cols = cset
                break
        items: List[Dict[str, Any]] = []
        if disc_tbl:
            try:
                desired_disc = [
                    "symbol", "title", "ai_summary", "sentiment",
                    "disclosure_type", "disclosure_date", "source_url",
                ]
                sel_disc = (
                    ",".join([c for c in desired_disc if c in disc_cols])
                    if disc_cols else ",".join(desired_disc)
                )
                q = sb_sa.from_(disc_tbl).select(sel_disc).limit(min(limit or 10, 20))
                if disc_cols and "exchange" in disc_cols:
                    q = q.eq("exchange", eff_mkt)
                if clean_sym:
                    q = q.eq("symbol", clean_sym)
                if disclosure_type:
                    q = q.eq("disclosure_type", disclosure_type)
                res = q.order("disclosure_date", desc=True).execute()
                items = res.data or []
            except Exception:
                items = []
        out: Dict[str, Any] = {
            "status": "success",
            "market": ui_mkt,
            "exchange": eff_mkt,
            "currency": currency,
            "count": len(items),
            "disclosures": items,
        }
        if not items:
            site_hint = f" عبر {cfg.official_site}" if cfg.official_site else ""
            out["note"] = (
                f"إفصاحات {cfg.name_ar} ({ui_mkt}) غير متوفرة حالياً في قاعدة البيانات؛ "
                f"يمكنك متابعة إعلانات الشركات مباشرة{site_hint}، وسأساعدك في التحليل الفني والأساسي لأي سهم فوراً."
            )
        return out

    sb = _get_sb()
    try:
        q = (
            sb.from_("egx_disclosures")
            .select(
                "symbol,company_name,disclosure_type,disclosure_date,title,ai_summary,"
                "sentiment,action_type,shares_count,stake_before,stake_after,party_name,source_url"
            )
            .order("disclosure_date", desc=True)
            .limit(min(limit or 10, 20))
        )
        if clean_sym:
            q = q.eq("symbol", clean_sym)
        if disclosure_type:
            q = q.eq("disclosure_type", disclosure_type)
        res = q.execute()
        rows = res.data or []
    except Exception as e:
        return {"status": "error", "message": f"تعذر جلب الإفصاحات: {str(e)}"}

    return {
        "status": "success",
        "market": ui_mkt,
        "exchange": "EGX",
        "currency": currency,
        "count": len(rows),
        "disclosures": rows,
    }


async def execute_get_disclosures(
    symbol: Optional[str] = None,
    disclosure_type: Optional[str] = None,
    limit: int = 10,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_disclosures, symbol, disclosure_type, limit, market)


def _resolve_stock_display_name(clean_sym: str, sym_mkt: str) -> str:
    """Resolve official Arabic/English company name for newly added portfolio symbols."""
    stock_name = clean_sym
    try:
        sb_lookup = _get_sb_for_market(sym_mkt)
        if sb_lookup is not None:
            s_res = (
                sb_lookup.from_("stocks")
                .select("name_ar, name")
                .eq("exchange", sym_mkt)
                .eq("symbol", clean_sym)
                .limit(1)
                .execute()
            )
            if s_res.data and isinstance(s_res.data[0], dict):
                stock_name = s_res.data[0].get("name_ar") or s_res.data[0].get("name") or clean_sym
    except Exception:
        pass
    if stock_name == clean_sym:
        stock_name = _alias_name_for_symbol(clean_sym, sym_mkt) or clean_sym
    return stock_name


_MARKET_TURNOVER_THRESHOLDS: Dict[str, Tuple[float, float, float]] = {
    "EGX": (50_000.0, 1_500_000.0, 5_000_000.0),      # EGP
    "TADAWUL": (5_000.0, 150_000.0, 500_000.0),       # SAR
    "QSE": (5_000.0, 150_000.0, 500_000.0),           # QAR
    "DFM": (5_000.0, 150_000.0, 500_000.0),           # AED
    "ADX": (5_000.0, 150_000.0, 500_000.0),           # AED
    "KSE": (400.0, 12_000.0, 40_000.0),               # KWD
}


def _assess_stock_liquidity(
    hist_rows: List[Dict[str, Any]],
    ind_row: Dict[str, Any],
    price: Optional[float],
    exchange: str,
) -> Dict[str, Any]:
    """Unified liquidity & intraday pacing classifier shared by manage_portfolio and optimize_portfolio."""
    exch_code = _normalize_market_code(exchange)
    vols = [float(r["volume"]) for r in (hist_rows or [])[:10] if r.get("volume") is not None]
    has_vol_hist = len(vols) >= 3
    avg_vol_5 = (sum(vols[:5]) / len(vols[:5])) if vols else None
    avg_vol_10 = (sum(vols) / len(vols)) if vols else None
    zero_vol_days_10 = sum(1 for v in vols if v <= 0)
    avg_turnover_10 = (avg_vol_10 * price) if (avg_vol_10 is not None and price is not None) else None

    rv_info = resolve_intraday_r_vol(
        _safe_float(ind_row.get("r_vol")),
        ind_row.get("date"),
        exchange=exch_code,
        ohlcv_rows=hist_rows,
    )
    eff_r_vol = rv_info["effective_r_vol"]
    thr = _MARKET_TURNOVER_THRESHOLDS.get(exch_code)
    illiquid_thr, thin_thr, bluechip_thr = thr if thr is not None else (None, None, None)

    is_illiquid = bool(
        has_vol_hist
        and (
            (avg_vol_5 is not None and avg_vol_5 <= 0)
            or zero_vol_days_10 >= 4
            or (illiquid_thr is not None and avg_turnover_10 is not None and avg_turnover_10 < illiquid_thr)
        )
    )
    high_turnover_bluechip_intraday = bool(
        rv_info["is_intraday_adjusted"]
        and bluechip_thr is not None
        and avg_turnover_10 is not None
        and avg_turnover_10 >= bluechip_thr
    )
    is_thin_liquidity = bool(
        is_illiquid
        or (
            eff_r_vol is not None
            and eff_r_vol < 0.45
            and rv_info["r_vol_mode"] not in ("prev_close_fallback", "intraday_unavailable")
            and not high_turnover_bluechip_intraday
        )
        or (thin_thr is not None and avg_turnover_10 is not None and avg_turnover_10 < thin_thr)
    )
    return {
        "r_vol": eff_r_vol,
        "rv_info": rv_info,
        "avg_vol_10": avg_vol_10,
        "zero_vol_days_10": zero_vol_days_10,
        "is_illiquid": is_illiquid,
        "is_thin_liquidity": is_thin_liquidity,
    }


def _build_portfolio_view_payload(
    sb: Any,
    holdings: List[Dict[str, Any]],
    watchlist_only: List[Dict[str, Any]],
    cash: float,
) -> Dict[str, Any]:
    """Shared live-quote enrichment & P&L calculator for both website and Telegram-only portfolios."""
    if not holdings:
        if watchlist_only:
            wl_syms = ", ".join(w["symbol"] for w in watchlist_only[:10])
            msg = (
                f"لديك {len(watchlist_only)} سهم مسجل في قائمة المتابعة بدون تحديد كمية ({wl_syms}). "
                "أرسل لي الكمية وسعر الشراء لأي سهم لتسجيله في حسابات المحفظة الفعلية."
            )
        else:
            msg = "محفظتك فاضية حالياً. تقدر تضيف أسهمك هنا بالكتابة أو برفع سكرين شوت لمحفظتك وهحللها فوراً."
        return {
            "status": "success",
            "operation": "view",
            "message": msg,
            "positions_count": 0,
            "positions": [],
            "watchlist_count": len(watchlist_only),
            "watchlist_positions": watchlist_only,
            "cash_balance": round(cash, 2),
            "totals": {
                "positions_count": 0,
                "cost_basis": 0.0,
                "market_value": 0.0,
                "profit_value": 0.0,
                "profit_pct": 0.0,
                "equity": round(cash, 2),
            },
        }

    symbols = list({str(p.get("symbol", "")).upper() for p in holdings if p.get("symbol")})
    egx_syms: List[str] = []
    non_egx_by_mkt: Dict[str, List[str]] = {}
    for s in symbols:
        norm_s, mkt = _resolve_symbol_and_market(s)
        if mkt == "EGX":
            egx_syms.append(s)
        else:
            non_egx_by_mkt.setdefault(mkt, []).append(norm_s)

    # Key quote maps by (exchange, symbol) so overlapping tickers (e.g. EGX ADIB vs ADX ADIB.AD) never collide!
    price_map: Dict[Tuple[str, str], Optional[float]] = {}
    change_map: Dict[Tuple[str, str], Optional[float]] = {}
    tech_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    wyckoff_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

    fund_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    price_hist_by_sym: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    if egx_syms:
        try:
            tech_res = (
                sb.from_("stock_technical_indicators")
                .select("symbol, exchange, close, change_pct, date, rsi_14, ema_50, ema_200, macd_histogram, bb_lower, bb_upper, r_vol, king_ai_score")
                .in_("symbol", egx_syms)
                .order("date", desc=True)
                .limit(max(len(egx_syms) * 5, 30))
                .execute()
            )
            for row in tech_res.data or []:
                row_exch = str(row.get("exchange") or "EGX").upper()
                if row_exch != "EGX":
                    continue
                s = str(row.get("symbol", "")).upper()
                k = ("EGX", s)
                if s and k not in price_map:
                    price_map[k] = _safe_price(row.get("close"))
                    change_map[k] = _safe_float(row.get("change_pct"))
                    tech_map[k] = row
        except Exception:
            pass

        try:
            wyck_res = (
                sb.from_("stock_scans_summary")
                .select("symbol, wyckoff_phase, acc_score, dist_score, signal")
                .in_("symbol", egx_syms)
                .order("scan_date", desc=True)
                .limit(max(len(egx_syms) * 3, 20))
                .execute()
            )
            for row in wyck_res.data or []:
                s = str(row.get("symbol", "")).upper()
                k = ("EGX", s)
                if s and k not in wyckoff_map:
                    wyckoff_map[k] = row
        except Exception:
            pass

        try:
            sf_res = (
                sb.from_("stock_fundamentals")
                .select("symbol, fund_score, data")
                .eq("exchange", "EGX")
                .in_("symbol", egx_syms)
                .limit(len(egx_syms) + 5)
                .execute()
            )
            for row in sf_res.data or []:
                s = str(row.get("symbol", "")).upper()
                if s and ("EGX", s) not in fund_map:
                    fund_map[("EGX", s)] = row
        except Exception:
            pass

        try:
            sp_hist_res = (
                sb.from_("stock_prices")
                .select("symbol, date, close, volume")
                .eq("exchange", "EGX")
                .in_("symbol", egx_syms)
                .order("date", desc=True)
                .limit(min(max(len(egx_syms) * 120, 120), 2400))
                .execute()
            )
            for row in sp_hist_res.data or []:
                s = str(row.get("symbol", "")).upper()
                if s:
                    lst = price_hist_by_sym.setdefault(("EGX", s), [])
                    if len(lst) < 120:
                        lst.append(row)
        except Exception:
            pass

        missing_egx = [s for s in egx_syms if ("EGX", s) not in price_map]
        if missing_egx:
            try:
                sp_res = (
                    sb.from_("stock_prices")
                    .select("symbol, close, change_pct, date")
                    .eq("exchange", "EGX")
                    .in_("symbol", missing_egx)
                    .order("date", desc=True)
                    .limit(max(len(missing_egx) * 5, 30))
                    .execute()
                )
                for row in sp_res.data or []:
                    s = str(row.get("symbol", "")).upper()
                    k = ("EGX", s)
                    if s and k not in price_map:
                        price_map[k] = _safe_price(row.get("close"))
                        change_map[k] = _safe_float(row.get("change_pct"))
            except Exception:
                pass

    for exch_code, exch_syms in non_egx_by_mkt.items():
        sb_exch = _get_sb_for_market(exch_code)
        if sb_exch is None:
            continue
        try:
            ti_cols_str, order_col = _saudi_ti_select_and_order(sb_exch)
            tech_res = (
                sb_exch.from_("stock_technical_indicators")
                .select(ti_cols_str)
                .eq("exchange", exch_code)
                .in_("symbol", exch_syms)
                .order(order_col, desc=True)
                .limit(max(len(exch_syms) * 5, 30))
                .execute()
            )
            for row in tech_res.data or []:
                s_norm = str(row.get("symbol", "")).upper()
                k = (exch_code, s_norm)
                if s_norm and k not in price_map:
                    price_map[k] = _safe_price(row.get("close"))
                    change_map[k] = _safe_float(row.get("change_pct"))
                    tech_map[k] = row
        except Exception:
            pass

        missing_exch = [s for s in exch_syms if (exch_code, s) not in price_map]
        if missing_exch:
            exch_ohlcv = _fetch_saudi_ohlcv_for_symbols(sb_exch, missing_exch, limit_per_sym=5, exchange=exch_code)
            for s_norm, bars in exch_ohlcv.items():
                if bars:
                    k = (exch_code, s_norm)
                    c0 = _safe_price(bars[0].get("close"))
                    price_map[k] = c0
                    if len(bars) >= 2:
                        c1 = _safe_price(bars[1].get("close"))
                        if c1 and c0:
                            change_map[k] = _safe_float(((c0 - c1) / c1) * 100.0)

    enriched = []
    fcf_by_pos_key: Dict[str, Optional[float]] = {}
    for p in holdings:
        s = str(p.get("symbol", "")).upper()
        norm_s, mkt = _resolve_symbol_and_market(s)
        curr = _currency_for_market(mkt)
        qty = _safe_float(p.get("quantity"), 4)
        entry = _safe_price(p.get("entry_price"))
        last_price = price_map.get((mkt, s)) if (mkt, s) in price_map else price_map.get((mkt, norm_s))
        change_pct = change_map.get((mkt, s)) if (mkt, s) in change_map else change_map.get((mkt, norm_s))

        valid_entry = entry is not None and entry > 0
        cost_basis = (qty * entry) if (qty is not None and valid_entry) else None
        market_value = (qty * last_price) if (qty is not None and last_price is not None) else None
        profit_value = (market_value - cost_basis) if (cost_basis is not None and market_value is not None) else None
        profit_pct = ((profit_value / cost_basis) * 100) if (cost_basis and cost_basis > 0 and profit_value is not None) else None

        t_row = tech_map.get((mkt, s)) or tech_map.get((mkt, norm_s)) or {}
        w_row = wyckoff_map.get((mkt, s)) or wyckoff_map.get((mkt, norm_s)) or {}
        hist_rows = price_hist_by_sym.get((mkt, s)) or price_hist_by_sym.get((mkt, norm_s)) or []
        adj_ema50, adj_ema200, sp_factor, sp_adj_flag = _detect_and_adjust_price_split(
            hist_rows,
            _safe_price(t_row.get("ema_50")),
            _safe_price(t_row.get("ema_200")),
            last_price,
        )
        f_row = fund_map.get((mkt, s)) or fund_map.get((mkt, norm_s)) or {}
        f_score = _safe_float(f_row.get("fund_score"))
        norm_fd, _ = _normalize_split_adjusted_fundamentals(f_row.get("data"), last_price, split_factor=sp_factor)
        f_eps = _safe_float(norm_fd.get("eps") if norm_fd.get("eps") is not None else norm_fd.get("trailing_eps"), 4)
        f_ni = _safe_float(norm_fd.get("netIncome") if norm_fd.get("netIncome") is not None else norm_fd.get("net_income"), 2)
        f_bvps = _safe_float(norm_fd.get("bookValuePerShare") if norm_fd.get("bookValuePerShare") is not None else norm_fd.get("bvps"), 4)
        f_pe = _safe_float(norm_fd.get("peRatio") if norm_fd.get("peRatio") is not None else norm_fd.get("pe_ratio"))
        f_roe = _safe_float(norm_fd.get("roe") if norm_fd.get("roe") is not None else norm_fd.get("return_on_equity"))
        f_fcf = _safe_float(norm_fd.get("freeCashFlow") if norm_fd.get("freeCashFlow") is not None else norm_fd.get("free_cash_flow"), 2)
        fcf_by_pos_key[s] = f_fcf

        liq_info = _assess_stock_liquidity(hist_rows, t_row, last_price, mkt)
        rv_info_pf = liq_info["rv_info"]
        r_vol = liq_info["r_vol"]
        is_illiquid = liq_info["is_illiquid"]
        is_thin_liquidity = liq_info["is_thin_liquidity"]
        is_loss_making = bool(
            (f_eps is not None and f_eps < 0)
            or (f_ni is not None and f_ni < 0)
            or (f_roe is not None and f_roe < 0)
        )
        is_negative_equity = bool(f_bvps is not None and f_bvps <= 0)
        is_sharia = is_sharia_compliant(s, market=mkt) if mkt in ("EGX", "TADAWUL") else None

        pos_entry: Dict[str, Any] = {
            "id": p.get("id"),
            "symbol": s,
            "market": _ui_market_label(mkt),
            "currency": curr,
            "name": p.get("name") or s,
            "quantity": qty,
            "entry_price": entry,
            "last_price": last_price,
            "change_pct": change_pct,
            "market_value": round(market_value, 2) if market_value is not None else None,
            "cost_basis": round(cost_basis, 2) if cost_basis is not None else None,
            "profit_value": round(profit_value, 2) if profit_value is not None else None,
            "profit_pct": round(profit_pct, 2) if profit_pct is not None else None,
            "rsi_14": _safe_float(t_row.get("rsi_14")),
            "ema_50": adj_ema50,
            "ema_200": adj_ema200,
            "macd_histogram": _safe_float(t_row.get("macd_histogram"), 4),
            "support_est": _safe_price(t_row.get("bb_lower")),
            "resistance_est": _safe_price(t_row.get("bb_upper")),
            "r_vol": r_vol,
            **(
                {
                    "r_vol_mode": rv_info_pf["r_vol_mode"],
                    "r_vol_note_ar": rv_info_pf["r_vol_note_ar"],
                }
                if rv_info_pf["is_intraday_adjusted"] and rv_info_pf.get("r_vol_note_ar")
                else {}
            ),
            "king_ai_score": _normalize_king_ai_score(t_row.get("king_ai_score")),
            "wyckoff_phase": w_row.get("wyckoff_phase"),
            "acc_score": _safe_float(w_row.get("acc_score")),
            "dist_score": _safe_float(w_row.get("dist_score")),
            "fund_score": f_score,
            "pe_ratio": f_pe,
            "eps": f_eps,
            "roe_pct": f_roe,
            "is_loss_making": is_loss_making,
            "is_negative_equity": is_negative_equity,
            "is_illiquid": is_illiquid,
            "is_thin_liquidity": is_thin_liquidity,
            "is_sharia_compliant": is_sharia,
            "added_at": p.get("added_at"),
        }
        if last_price and adj_ema50:
            pos_entry["ema50_position_ar"] = f"فوق EMA50 ({adj_ema50}) ✅" if last_price >= adj_ema50 else f"تحت EMA50 ({adj_ema50}) 🔴"
        if last_price and adj_ema200:
            pos_entry["ema200_position_ar"] = f"فوق EMA200 ({adj_ema200}) ✅" if last_price >= adj_ema200 else f"تحت EMA200 ({adj_ema200}) 🔴"
        if sp_adj_flag:
            pos_entry["split_adjusted_ema"] = True
        enriched.append(pos_entry)

    has_unknown_cost = any(p["cost_basis"] is None for p in enriched)
    total_cost = None if has_unknown_cost else sum(p["cost_basis"] or 0 for p in enriched)
    has_unknown_val = any(p["market_value"] is None for p in enriched)
    total_value = None if has_unknown_val else sum(p["market_value"] or 0 for p in enriched)
    total_profit = (total_value - total_cost) if (total_cost is not None and total_value is not None) else None
    total_profit_pct = ((total_profit / total_cost) * 100) if (total_cost and total_cost > 0 and total_profit is not None) else None
    equity = (total_value + cash) if total_value is not None else cash

    denom_w = equity if equity and equity > 0 else (total_cost if total_cost and total_cost > 0 else 0.0)
    exit_priority_syms: List[str] = []
    trim_excess_syms: List[str] = []
    hold_core_syms: List[str] = []
    hold_watch_syms: List[str] = []
    do_not_buy_syms: List[str] = []
    conc_warnings: List[str] = []
    est_cash_freed = 0.0

    for item in enriched:
        val_i = item.get("market_value") if item.get("market_value") is not None else (item.get("cost_basis") or 0.0)
        w_pct = round((float(val_i) / float(denom_w)) * 100.0, 1) if denom_w > 0 and val_i is not None else 0.0
        item["weight_pct"] = w_pct
        lp = _safe_float(item.get("last_price"))
        e50 = _safe_float(item.get("ema_50"))
        e200 = _safe_float(item.get("ema_200"))
        below_both = bool(lp and e50 and e200 and lp < e50 and lp < e200)
        pe_v = _safe_float(item.get("pe_ratio"))
        fs_v = _safe_float(item.get("fund_score"))
        chk_fcf = fcf_by_pos_key.get(str(item.get("symbol") or "").upper())
        sym_u = str(item.get("symbol") or "").upper()
        loss_mk = bool(item.get("is_loss_making"))
        neg_eq = bool(item.get("is_negative_equity"))
        illq = bool(item.get("is_illiquid"))
        thin = bool(item.get("is_thin_liquidity"))

        if w_pct >= 16.0:
            conc_warnings.append(f"{sym_u} يمثل {w_pct}% من المحفظة (تركّز مرتفع)")

        reasons: List[str] = []
        over_and_weak = bool(pe_v is not None and pe_v > 30.0 and ((chk_fcf is not None and chk_fcf < 0) or (lp and e50 and lp < e50)))
        heavy_trim = bool(w_pct >= 16.0 and ((pe_v is not None and pe_v > 30.0) or (fs_v is not None and fs_v < 55.0) or below_both))

        if illq or neg_eq or (loss_mk and (fs_v is None or fs_v < 50.0)):
            rot_act = "EXIT_PRIORITY"
            forbidden = True
            if illq:
                reasons.append("سيولة منعدمة / تداول صفري")
            if neg_eq:
                reasons.append("حقوق ملكية سالبة")
            if loss_mk:
                reasons.append("شركة خاسرة وتقييم مالي ضعيف")
            est_cash_freed += float(val_i or 0.0)
            exit_priority_syms.append(sym_u)
        elif heavy_trim or over_and_weak:
            rot_act = "TRIM_EXCESS"
            forbidden = bool((pe_v is not None and pe_v > 30.0) or loss_mk)
            if w_pct >= 16.0:
                reasons.append(f"تركّز وزن مرتفع ({w_pct}%)")
            if pe_v is not None and pe_v > 30.0:
                reasons.append(f"مكرر ربحية متضخم (P/E={pe_v:.1f}x)")
            if below_both:
                reasons.append("اتجاه هابط تحت EMA50 و EMA200")
            est_cash_freed += float(val_i or 0.0) * 0.33
            trim_excess_syms.append(sym_u)
        elif (not loss_mk) and (fs_v is not None and fs_v >= 65.0) and (pe_v is None or pe_v <= 22.0):
            rot_act = "HOLD_CORE"
            forbidden = False
            reasons.append(f"أساسيات قوية (تقييم مالي {fs_v:.0f}/100)" + (" + سيولة ضعيفة نسبياً (لا تتجاوز 15%)" if thin else ""))
            hold_core_syms.append(sym_u)
        else:
            rot_act = "HOLD_WATCH"
            forbidden = bool(loss_mk or (pe_v is not None and pe_v > 30.0))
            reasons.append("يُحتفظ به بمراقبة الوقف دون اندفاع للشراء")
            hold_watch_syms.append(sym_u)

        if forbidden and sym_u not in do_not_buy_syms:
            do_not_buy_syms.append(sym_u)
        item["rotation_action"] = rot_act
        item["rotation_reason_ar"] = " — ".join(reasons)
        item["forbidden_to_buy"] = forbidden

    totals_by_market: Dict[str, Dict[str, Any]] = {}
    if non_egx_by_mkt:
        seen_mkts: Dict[str, str] = {}
        for x in enriched:
            m_lbl = str(x.get("market") or "EGX")
            if m_lbl not in seen_mkts:
                seen_mkts[m_lbl] = str(x.get("currency") or "ج.م")
        for m_lbl, curr_lbl in seen_mkts.items():
            sub = [x for x in enriched if x.get("market") == m_lbl]
            if sub:
                sub_cost = sum(x["cost_basis"] or 0 for x in sub) if all(x["cost_basis"] is not None for x in sub) else None
                sub_val = sum(x["market_value"] or 0 for x in sub) if all(x["market_value"] is not None for x in sub) else None
                sub_pnl = (sub_val - sub_cost) if (sub_val is not None and sub_cost is not None) else None
                totals_by_market[m_lbl] = {
                    "currency": curr_lbl,
                    "positions_count": len(sub),
                    "cost_basis": round(sub_cost, 2) if sub_cost is not None else None,
                    "market_value": round(sub_val, 2) if sub_val is not None else None,
                    "profit_value": round(sub_pnl, 2) if sub_pnl is not None else None,
                }

    profitable_items = [p for p in enriched if p.get("profit_value") is not None and float(p["profit_value"]) > 0]
    losing_items = [p for p in enriched if p.get("profit_value") is not None and float(p["profit_value"]) < 0]
    breakeven_items = [p for p in enriched if p.get("profit_value") is not None and float(p["profit_value"]) == 0]
    profitable_items_sorted = sorted(profitable_items, key=lambda x: float(x.get("profit_pct") or 0.0), reverse=True)

    res_payload: Dict[str, Any] = {
        "status": "success",
        "operation": "view",
        "message": (
            f"محفظتك تحتوي على {len(enriched)} سهم."
            + (f" ويوجد {len(watchlist_only)} سهم آخر في قائمة المتابعة بدون كمية محددة." if watchlist_only else "")
        ),
        "positions_count": len(enriched),
        "positions": enriched,
        "watchlist_count": len(watchlist_only),
        "watchlist_positions": watchlist_only,
        "cash_balance": round(cash, 2),
        "totals": {
            "positions_count": len(enriched),
            "cost_basis": round(total_cost, 2) if total_cost is not None else None,
            "market_value": round(total_value, 2) if total_value is not None else None,
            "profit_value": round(total_profit, 2) if total_profit is not None else None,
            "profit_pct": round(total_profit_pct, 2) if total_profit_pct is not None else None,
            "equity": round(equity, 2),
            "profitable_positions_count": len(profitable_items),
            "profitable_symbols": [
                f"{p['symbol']} ({float(p.get('profit_pct') or 0):+.2f}%)"
                for p in profitable_items_sorted
            ],
            "losing_positions_count": len(losing_items),
            "breakeven_positions_count": len(breakeven_items),
        },
    }
    if totals_by_market:
        res_payload["totals_by_market"] = totals_by_market
    if enriched:
        res_payload["portfolio_rotation_matrix"] = {
            "exit_priority_symbols": exit_priority_syms,
            "trim_excess_symbols": trim_excess_syms,
            "hold_core_symbols": hold_core_syms,
            "hold_watch_symbols": hold_watch_syms,
            "do_not_buy_symbols": do_not_buy_syms,
            "estimated_cash_freed_from_exits": round(est_cash_freed, 2),
            "current_cash_pct": round((cash / equity) * 100.0, 1) if equity and equity > 0 else 0.0,
            "concentration_warnings": conc_warnings,
            "note_ar": (
                "مصفوفة القرار الحتمية: يُمنع منعاً باتاً اقتراح شراء أو تعزيز أي سهم في do_not_buy_symbols أو exit_priority_symbols "
                "(شركات خاسرة، حقوق ملكية سالبة، أو سيولة منعدمة). الأسهم في hold_core_symbols ذات أساسيات قوية."
            ),
        }

    # Enrich portfolio view with upcoming/pending cash dividends for user's held stocks
    port_divs: List[Dict[str, Any]] = []
    for p in enriched:
        psym = str(p.get("symbol") or "").upper()
        pqty = _safe_float(p.get("quantity"), 4) or 0.0
        pmkt = p.get("exchange") or p.get("market") or "EGX"
        if not psym or pqty <= 0:
            continue
        udiv = _lookup_upcoming_dividend(psym, pmkt)
        if udiv and udiv.get("amount"):
            gross = round(pqty * float(udiv["amount"]), 2)
            is_egx_div = str(udiv.get("exchange") or pmkt).upper() == "EGX"
            net = round(gross * 0.95, 2) if is_egx_div else gross
            port_divs.append({
                "symbol": psym,
                "exchange": udiv.get("exchange") or pmkt,
                "shares_held": pqty,
                "coupon_per_share": udiv["amount"],
                "gross_amount": gross,
                "net_amount_after_tax": net,
                "currency": udiv.get("currency_ar") or udiv.get("currency") or p.get("currency") or "ج.م",
                "ex_date": udiv.get("ex_date"),
                "record_date": udiv.get("record_date"),
                "pay_date": udiv.get("pay_date"),
                "days_until_ex": udiv.get("days_until_ex"),
                "status": udiv.get("status"),
                "entitlement_rule_ar": _dividend_entitlement_rule_ar(udiv.get("ex_date"), udiv.get("record_date")),
            })
    if port_divs:
        res_payload["upcoming_dividends"] = port_divs
    return res_payload


def _load_tg_portfolio_state(sb: Any, telegram_user_id: int) -> Dict[str, Any]:
    res = (
        sb.from_("telegram_vip_chat_state")
        .select("portfolio_state")
        .eq("telegram_user_id", int(telegram_user_id))
        .limit(1)
        .execute()
    )
    rows = res.data or []
    raw_state = (rows[0].get("portfolio_state") if rows and isinstance(rows[0], dict) else None) or {}
    if not isinstance(raw_state, dict):
        raw_state = {}
    positions = raw_state.get("positions")
    if not isinstance(positions, list):
        positions = []
    cash = _safe_float(raw_state.get("cash_balance"), 2) or 0.0
    return {
        "cash_balance": cash,
        "positions": [dict(p) for p in positions if isinstance(p, dict) and p.get("symbol")],
    }


def _save_tg_portfolio_state(sb: Any, telegram_user_id: int, state: Dict[str, Any]) -> None:
    sb.from_("telegram_vip_chat_state").upsert(
        {
            "telegram_user_id": int(telegram_user_id),
            "portfolio_state": state,
            "updated_at": datetime.now(CAIRO_TZ).isoformat(),
        },
        on_conflict="telegram_user_id",
    ).execute()


_PORTFOLIO_REFRESH_ONLY_RE = re.compile(
    r"^\s*(?:من\s*فضلك\s+|لو\s*سمحت\s+)?(?:حدث|حدثلي|تحديث|اعمل\s*تحديث(?:\s*ل)?|اعرض|اظهر|شوف|راجع|قيم|هات|وريني)\s*(?:لي\s*)?(?:ال)?محفظ(?:ه|تي|ه\s*بتاعتي)?(?:\s*(?:الان|دلوقتي|الحاليه|باسعار\s*اليوم|من\s*فضلك|لو\s*سمحت))?\s*[!.؟?]*\s*$"
)

_PORTFOLIO_WRITE_INTENT_RE = re.compile(
    r"(?:احفظ|سجل|اشتريت|شريت|ضف|اضف|اضيف|ضيف|ضيفه|ضيفهم|ضيفلي|"
    r"حط|حطه|دخل|شيل|بيع|بعت|احذف|امسح|الغي|نقص|زود|تزود|"
    r"عدل|عدلي|غير|حدث|موافق|تمام|اكد|تاكيد|نفذ|اضافه|تعديل|"
    r"(?:^|[^\w\u0621-\u064a])شراء(?:$|[^\w\u0621-\u064a]))"
)

_PORTFOLIO_CONFIRM_RE = re.compile(
    r"(?:^|[^\w\u0621-\u064a])(?:موافق|اكد|تاكيد|نفذ|تمام|ايوه|نعم)(?:$|[^\w\u0621-\u064a])"
)


def _validate_portfolio_write_intent(op: str, user_prompt: str) -> Optional[Dict[str, Any]]:
    """Reject accidental portfolio writes on pure refresh/view requests or unconfirmed replays."""
    norm_prompt = _normalize_arabic_text(user_prompt or "").lower().strip()
    if _PORTFOLIO_REFRESH_ONLY_RE.match(norm_prompt):
        return {
            "status": "blocked",
            "message": "الرسالة الحالية تطلب عرض أو تحديث أسعار المحفظة فقط، وليس إضافة أو تعديل كميات؛ استخدم operation='view'.",
        }
    if not _PORTFOLIO_WRITE_INTENT_RE.search(norm_prompt):
        return {
            "status": "blocked",
            "message": "لم يتم تأكيد طلب تعديل المحفظة من رسالة المستخدم صراحةً.",
        }
    if op in ("add", "buy"):
        has_digits = bool(re.search(r"[\d\u0660-\u0669]", norm_prompt))
        if not has_digits and not _PORTFOLIO_CONFIRM_RE.search(norm_prompt):
            return {
                "status": "blocked",
                "message": "لم تُذكر كمية أو سعر شراء جديد في رسالتك الحالية لإضافته للمحفظة؛ استخدم operation='view' لعرض المحفظة.",
            }
    return None


def _manage_tg_json_portfolio(
    sb: Any,
    telegram_user_id: int,
    op: str,
    symbol: Optional[str],
    quantity: Optional[float],
    price: Optional[float],
    user_prompt: str,
    cash_amount: Optional[float],
) -> Dict[str, Any]:
    """Isolated zero-login portfolio storage backed by telegram_vip_chat_state.portfolio_state."""
    if op in ("view", "get"):
        try:
            state = _load_tg_portfolio_state(sb, telegram_user_id)
            holdings = [
                p for p in state["positions"]
                if p.get("quantity") is not None and (_safe_float(p.get("quantity")) or 0) > 0
            ]
            res = _build_portfolio_view_payload(sb, holdings, [], float(state.get("cash_balance") or 0.0))
            res["storage_mode"] = "telegram_private_only"
            return res
        except Exception as e:
            return {"status": "error", "message": f"تعذر استرجاع محفظتك: {str(e)}"}

    # Anti-injection write check matches website portfolio behavior
    write_guard_err = _validate_portfolio_write_intent(op, user_prompt)
    if write_guard_err:
        return write_guard_err

    lock = _get_tg_portfolio_lock(int(telegram_user_id))
    with lock:
        if op in ("set_cash", "add_cash"):
            amount = _safe_float(cash_amount, 2)
            if amount is None:
                amount = _safe_float(price, 2)
            if amount is None:
                amount = _safe_float(quantity, 2)
            if amount is None or amount < 0 or (op == "add_cash" and amount == 0):
                return {
                    "status": "needs_clarification",
                    "operation": op,
                    "message": "يلزم تحديد مبلغ السيولة النقدية (الكاش) برقم واضح لتحديث رصيد المحفظة.",
                }
            state = _load_tg_portfolio_state(sb, telegram_user_id)
            current_cash = _safe_float(state.get("cash_balance"), 2) or 0.0
            new_cash = round(amount if op == "set_cash" else (current_cash + amount), 2)
            state["cash_balance"] = new_cash
            _save_tg_portfolio_state(sb, telegram_user_id, state)
            return {
                "status": "success",
                "operation": op,
                "cash_balance": new_cash,
                "storage_mode": "telegram_private_only",
                "message": f"تم بنجاح تحديث رصيد الكاش (السيولة المتاحة) في محفظتك الخاصة على تليجرام إلى {new_cash:,.2f} ج.م.",
            }

        clean_sym, sym_mkt = _resolve_symbol_and_market(symbol)
        curr_lbl = _currency_for_market(sym_mkt)
        if not clean_sym:
            return {"status": "error", "message": "رمز السهم مطلوب لإجراء تعديل المحفظة."}

        state = _load_tg_portfolio_state(sb, telegram_user_id)
        positions: List[Dict[str, Any]] = state["positions"]
        existing_idx = next(
            (i for i, p in enumerate(positions) if str(p.get("symbol", "")).upper() == clean_sym),
            None,
        )
        existing = positions[existing_idx] if existing_idx is not None else None

        if op in ("add", "buy"):
            add_qty = _safe_float(quantity, 4)
            new_entry = _safe_float(price, 4)
            if add_qty is None or add_qty <= 0 or new_entry is None or new_entry <= 0:
                return {
                    "status": "needs_clarification",
                    "operation": op,
                    "symbol": clean_sym,
                    "message": (
                        f"يلزم تحديد عدد الأسهم (> 0) وسعر الشراء الفعلي (> 0) بوضوح لإضافة أو شراء {clean_sym} في محفظتك — "
                        "لا يُسمح بافتراض كمية أو سعر تلقائياً."
                    ),
                }
            if existing is not None:
                old_qty = _safe_float(existing.get("quantity"), 4) or 0.0
                new_qty = round(old_qty + add_qty, 4)
                old_entry = _safe_float(existing.get("entry_price"), 4)
                avg_entry = ((old_entry * old_qty) + (new_entry * add_qty)) / new_qty if (old_entry and old_qty > 0 and new_qty > 0) else new_entry
                avg_entry_stored = round(avg_entry, 4)
                positions[existing_idx]["quantity"] = new_qty
                positions[existing_idx]["entry_price"] = avg_entry_stored
                msg = f"تم بنجاح تحديث سهم {clean_sym} في محفظتك الخاصة: الإجمالي الآن {new_qty} سهم بمتوسط سعر {_safe_price(avg_entry_stored)} {curr_lbl}."
            else:
                stock_name = _resolve_stock_display_name(clean_sym, sym_mkt)
                positions.append({
                    "id": f"tg-{telegram_user_id}-{clean_sym}",
                    "symbol": clean_sym,
                    "name": stock_name,
                    "quantity": add_qty,
                    "entry_price": new_entry,
                    "status": "open",
                    "source": "telegram_private",
                    "added_at": datetime.now(CAIRO_TZ).isoformat(),
                })
                msg = f"تم بنجاح حفظ {add_qty} سهم من {clean_sym} في محفظتك الخاصة على تليجرام بسعر {_safe_price(new_entry)} {curr_lbl} (بدون الحاجة لحساب على الموقع)."
            _save_tg_portfolio_state(sb, telegram_user_id, state)
            return {
                "status": "success",
                "operation": op,
                "symbol": clean_sym,
                "market": _ui_market_label(sym_mkt),
                "currency": curr_lbl,
                "storage_mode": "telegram_private_only",
                "message": msg,
            }

        if op in ("update",):
            if existing is None:
                return {"status": "error", "message": f"سهم {clean_sym} غير موجود في محفظتك الخاصة."}
            if quantity is None and price is None:
                return {"status": "error", "message": "يلزم تحديد الكمية أو السعر لتعديل المركز."}
            if quantity is not None:
                positions[existing_idx]["quantity"] = _safe_float(quantity, 4)
            if price is not None:
                positions[existing_idx]["entry_price"] = _safe_float(price, 4)
            _save_tg_portfolio_state(sb, telegram_user_id, state)
            return {
                "status": "success",
                "operation": op,
                "symbol": clean_sym,
                "storage_mode": "telegram_private_only",
                "message": f"تم تعديل مركز سهم {clean_sym} في محفظتك الخاصة بنجاح.",
            }

        if op in ("remove", "delete"):
            if existing is None:
                return {"status": "error", "message": f"سهم {clean_sym} غير موجود في محفظتك."}
            positions.pop(existing_idx)
            _save_tg_portfolio_state(sb, telegram_user_id, state)
            return {
                "status": "success",
                "operation": op,
                "symbol": clean_sym,
                "storage_mode": "telegram_private_only",
                "message": f"تم حذف سهم {clean_sym} من محفظتك الخاصة بنجاح.",
            }

        if op in ("sell",):
            if existing is None:
                return {"status": "error", "message": f"سهم {clean_sym} غير موجود في محفظتك المفتوحة."}
            held = _safe_float(existing.get("quantity")) or 0.0
            sell_qty = _safe_float(quantity) if quantity is not None else held
            if sell_qty <= 0:
                return {"status": "error", "message": "كمية البيع يجب أن تكون أكبر من الصفر."}
            if sell_qty >= held:
                positions.pop(existing_idx)
                msg = f"تم تسجيل بيع كامل رصيد سهم {clean_sym} ({held} سهم)."
            else:
                rem = round(held - sell_qty, 4)
                positions[existing_idx]["quantity"] = rem
                msg = f"تم تسجيل بيع {sell_qty} سهم من {clean_sym}، والمتبقي {rem} سهم."
            if price and price > 0:
                current_cash = _safe_float(state.get("cash_balance"), 2) or 0.0
                state["cash_balance"] = round(current_cash + (sell_qty * price), 2)
            _save_tg_portfolio_state(sb, telegram_user_id, state)
            return {
                "status": "success",
                "operation": op,
                "symbol": clean_sym,
                "storage_mode": "telegram_private_only",
                "message": msg,
            }

        return {"status": "error", "message": f"العملية {op} غير مدعومة."}


# ---------------------------------------------------------------------------
# Tool: manage_portfolio (with prompt-injection safeguard)
# ---------------------------------------------------------------------------
def _fetch_compact_portfolio_summary(sb: Any, user_id: str) -> Dict[str, Any]:
    """Read compact post-mutation cost basis & cash balance so replies never quote stale totals."""
    try:
        pos_res = (
            sb.from_("positions")
            .select("quantity,entry_price")
            .eq("user_id", user_id)
            .eq("status", "open")
            .limit(80)
            .execute()
        )
        open_rows = pos_res.data or []
        total_cost = 0.0
        open_cnt = 0
        for row in open_rows:
            q = _safe_float(row.get("quantity"), 4) or 0.0
            ep = _safe_float(row.get("entry_price"), 4) or 0.0
            if q > 0:
                open_cnt += 1
                total_cost += q * ep
        cash_bal = 0.0
        try:
            prof = sb.from_("profiles").select("cash_balance").eq("id", user_id).limit(1).execute()
            if prof.data:
                cash_bal = _safe_float(prof.data[0].get("cash_balance")) or 0.0
        except Exception:
            pass
        return {
            "open_positions_count": open_cnt,
            "total_cost_basis": round(total_cost, 2),
            "cash_balance": round(cash_bal, 2),
        }
    except Exception:
        return {}


def _sync_manage_portfolio(
    user_id: Optional[str],
    operation: str,
    symbol: Optional[str] = None,
    quantity: Optional[float] = None,
    price: Optional[float] = None,
    user_prompt: str = "",
    cash_amount: Optional[float] = None,
    telegram_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Secure portfolio management backed by Supabase `positions` + `profiles.cash_balance`
    for website-authenticated accounts, or `telegram_vip_chat_state.portfolio_state`
    for unlinked private Telegram users (zero website registration required).
    """
    effective_tg_id = telegram_user_id if telegram_user_id is not None else _TG_PORTFOLIO_CTX.get()
    if _GROUP_PORTFOLIO_BLOCKED_CTX.get():
        return {
            "status": "redirect_private",
            "requires_private_chat": True,
            "private_bot_url": "https://t.me/egxbots_bot?start=b2b_portfolio",
            "message": (
                "لحماية خصوصية محفظتك الاستثمارية، تم تعطيل تسجيل أو عرض المحافظ داخل الجروب العام أو جروبات الشركات. "
                "افتح الشات الخاص مع البوت مباشرةً عبر الرابط التالي لتسجيل وتحليل محفظتك بسرية وبدون تسجيل دخول على الموقع: "
                "https://t.me/egxbots_bot?start=b2b_portfolio"
            ),
        }

    sb = _get_sb()
    op = (operation or "view").lower().strip()

    if effective_tg_id is not None:
        return _manage_tg_json_portfolio(
            sb=sb,
            telegram_user_id=int(effective_tg_id),
            op=op,
            symbol=symbol,
            quantity=quantity,
            price=price,
            user_prompt=user_prompt,
            cash_amount=cash_amount,
        )

    if not user_id:
        return {
            "status": "error",
            "message": "يلزم تسجيل الدخول لعرض أو تعديل المحفظة الاستثمارية.",
            "requires_login": True,
        }

    if op in ("view", "get"):
        try:
            res = (
                sb.from_("positions")
                .select("id, symbol, name, quantity, entry_price, entry_at, status, source, added_at")
                .eq("user_id", user_id)
                .eq("status", "open")
                .order("added_at", desc=True)
                .limit(100)
                .execute()
            )
            raw_positions = res.data or []

            holdings = [
                p for p in raw_positions
                if p.get("quantity") is not None and _safe_float(p.get("quantity")) is not None and _safe_float(p.get("quantity")) > 0
            ]
            watchlist_only = [
                {
                    "symbol": str(p.get("symbol", "")).upper(),
                    "name": p.get("name") or str(p.get("symbol", "")).upper(),
                    "entry_price": _safe_float(p.get("entry_price")),
                    "source": p.get("source"),
                    "added_at": p.get("added_at"),
                }
                for p in raw_positions
                if p.get("quantity") is None or _safe_float(p.get("quantity")) is None or _safe_float(p.get("quantity")) <= 0
            ]

            cash = 0.0
            try:
                prof_res = sb.from_("profiles").select("cash_balance").eq("id", user_id).limit(1).execute()
                if prof_res.data:
                    cash = _safe_float(prof_res.data[0].get("cash_balance")) or 0.0
            except Exception:
                cash = 0.0

            return _build_portfolio_view_payload(sb, holdings, watchlist_only, cash)
        except Exception as e:
            return {"status": "error", "message": f"تعذر استرجاع المحفظة: {str(e)}"}

    # Write operations require explicit intent in user's prompt (anti-injection guard)
    write_guard_err = _validate_portfolio_write_intent(op, user_prompt)
    if write_guard_err:
        return write_guard_err

    if op in ("set_cash", "add_cash"):
        amount = _safe_float(cash_amount, 2)
        if amount is None:
            amount = _safe_float(price, 2)
        if amount is None:
            amount = _safe_float(quantity, 2)
        if amount is None or amount < 0 or (op == "add_cash" and amount == 0):
            return {
                "status": "needs_clarification",
                "operation": op,
                "message": "يلزم تحديد مبلغ السيولة النقدية (الكاش) برقم واضح لتحديث رصيد المحفظة.",
            }
        try:
            p_res = sb.from_("profiles").select("cash_balance").eq("id", user_id).limit(1).execute()
            current_cash = _safe_float(p_res.data[0].get("cash_balance")) or 0.0 if p_res.data else 0.0
            new_cash = round(amount if op == "set_cash" else (current_cash + amount), 2)
            sb.from_("profiles").update({"cash_balance": new_cash}).eq("id", user_id).execute()
            return {
                "status": "success",
                "operation": op,
                "cash_balance": new_cash,
                "message": f"تم بنجاح تحديث رصيد الكاش (السيولة المتاحة) في محفظتك إلى {new_cash:,.2f} ج.م.",
            }
        except Exception as e:
            return {"status": "error", "message": f"تعذر تحديث رصيد الكاش: {str(e)}"}

    clean_sym, sym_mkt = _resolve_symbol_and_market(symbol)
    curr_lbl = _currency_for_market(sym_mkt)
    if not clean_sym:
        return {"status": "error", "message": "رمز السهم مطلوب لإجراء تعديل المحفظة."}

    try:
        res = (
            sb.from_("positions")
            .select("id, symbol, name, quantity, entry_price, status")
            .eq("user_id", user_id)
            .eq("symbol", clean_sym)
            .eq("status", "open")
            .limit(1)
            .execute()
        )
        existing = res.data[0] if res.data else None

        if op in ("add", "buy"):
            add_qty = _safe_float(quantity, 4)
            new_entry = _safe_float(price, 4)
            if add_qty is None or add_qty <= 0 or new_entry is None or new_entry <= 0:
                return {
                    "status": "needs_clarification",
                    "operation": op,
                    "symbol": clean_sym,
                    "message": (
                        f"يلزم تحديد عدد الأسهم (> 0) وسعر الشراء الفعلي (> 0) بوضوح لإضافة أو شراء {clean_sym} في محفظتك — "
                        "لا يُسمح بافتراض كمية أو سعر تلقائياً."
                    ),
                }

            if existing:
                old_qty = _safe_float(existing.get("quantity"), 4) or 0.0
                new_qty = round(old_qty + add_qty, 4)
                old_entry = _safe_float(existing.get("entry_price"), 4)
                if old_entry and old_qty > 0 and new_qty > 0:
                    avg_entry = ((old_entry * old_qty) + (new_entry * add_qty)) / new_qty
                else:
                    avg_entry = new_entry
                avg_entry_stored = round(avg_entry, 4)
                sb.from_("positions").update({
                    "quantity": new_qty,
                    "entry_price": avg_entry_stored,
                }).eq("id", existing["id"]).execute()
                msg = f"تم بنجاح تحديث سهم {clean_sym}: إجمالي الرصيد الآن {new_qty} سهم بمتوسط سعر {_safe_price(avg_entry_stored)} {curr_lbl}."
            else:
                stock_name = _resolve_stock_display_name(clean_sym, sym_mkt)
                row = {
                    "user_id": user_id,
                    "symbol": clean_sym,
                    "name": stock_name,
                    "quantity": add_qty,
                    "entry_price": new_entry,
                    "status": "open",
                    "source": "chatbot",
                }
                try:
                    sb.from_("positions").insert(row).execute()
                except Exception as ins_err:
                    if "source" in str(ins_err).lower() or "enum" in str(ins_err).lower():
                        row.pop("source", None)
                        sb.from_("positions").insert(row).execute()
                    else:
                        raise
                msg = f"تم بنجاح إضافة {add_qty} سهم من {clean_sym} إلى محفظتك بسعر {_safe_price(new_entry)} {curr_lbl}."

            return {
                "status": "success",
                "operation": op,
                "symbol": clean_sym,
                "market": _ui_market_label(sym_mkt),
                "currency": curr_lbl,
                "message": msg,
                "updated_portfolio_totals": _fetch_compact_portfolio_summary(sb, user_id),
            }

        elif op in ("update",):
            if not existing:
                return {"status": "error", "message": f"سهم {clean_sym} غير موجود في محفظتك المفتوحة."}
            updates = {}
            if quantity is not None:
                updates["quantity"] = quantity
            if price is not None:
                updates["entry_price"] = price
            if not updates:
                return {"status": "error", "message": "يلزم تحديد الكمية أو السعر لتعديل المركز."}
            sb.from_("positions").update(updates).eq("id", existing["id"]).execute()
            return {
                "status": "success",
                "operation": op,
                "symbol": clean_sym,
                "message": f"تم تعديل مركز سهم {clean_sym} بنجاح.",
                "updated_portfolio_totals": _fetch_compact_portfolio_summary(sb, user_id),
            }

        elif op in ("remove", "delete"):
            if not existing:
                return {"status": "error", "message": f"سهم {clean_sym} غير موجود في محفظتك."}
            try:
                sb.from_("positions").update({"status": "removed"}).eq("id", existing["id"]).execute()
            except Exception:
                sb.from_("positions").delete().eq("id", existing["id"]).execute()
            return {
                "status": "success",
                "operation": op,
                "symbol": clean_sym,
                "message": f"تم حذف سهم {clean_sym} من محفظتك بنجاح.",
                "updated_portfolio_totals": _fetch_compact_portfolio_summary(sb, user_id),
            }

        elif op in ("sell",):
            if not existing:
                return {"status": "error", "message": f"سهم {clean_sym} غير موجود في محفظتك المفتوحة."}
            held = _safe_float(existing.get("quantity")) or 0.0
            sell_qty = _safe_float(quantity) if quantity is not None else held
            if sell_qty <= 0:
                return {"status": "error", "message": "كمية البيع يجب أن تكون أكبر من الصفر."}
            if sell_qty >= held:
                update_data: Dict[str, Any] = {
                    "status": "closed_manual",
                    "status_at": datetime.now(timezone.utc).isoformat(),
                }
                if price is not None:
                    update_data["status_price"] = price
                sb.from_("positions").update(update_data).eq("id", existing["id"]).execute()
                msg = f"تم تسجيل بيع كامل رصيد سهم {clean_sym} ({held} سهم)."
            else:
                rem = held - sell_qty
                sb.from_("positions").update({"quantity": rem}).eq("id", existing["id"]).execute()
                msg = f"تم تسجيل بيع {sell_qty} سهم من {clean_sym}، والمتبقي {rem} سهم."

            if price and price > 0:
                proceeds = sell_qty * price
                try:
                    p_res = sb.from_("profiles").select("cash_balance").eq("id", user_id).limit(1).execute()
                    current_cash = _safe_float(p_res.data[0].get("cash_balance")) or 0.0 if p_res.data else 0.0
                    sb.from_("profiles").update({"cash_balance": current_cash + proceeds}).eq("id", user_id).execute()
                except Exception:
                    pass

            return {
                "status": "success",
                "operation": op,
                "symbol": clean_sym,
                "message": msg,
                "updated_portfolio_totals": _fetch_compact_portfolio_summary(sb, user_id),
            }
        else:
            return {"status": "error", "message": f"العملية {op} غير مدعومة."}
    except Exception as e:
        return {"status": "error", "message": f"تعذر تحديث المحفظة: {str(e)}"}


async def execute_manage_portfolio(
    user_id: Optional[str],
    operation: str,
    symbol: Optional[str] = None,
    quantity: Optional[float] = None,
    price: Optional[float] = None,
    user_prompt: str = "",
    cash_amount: Optional[float] = None,
    telegram_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    effective_tg_id = telegram_user_id if telegram_user_id is not None else _TG_PORTFOLIO_CTX.get()
    return await asyncio.to_thread(
        _sync_manage_portfolio,
        user_id,
        operation,
        symbol,
        quantity,
        price,
        user_prompt,
        cash_amount,
        effective_tg_id,
    )


# ---------------------------------------------------------------------------
# Tool: optimize_portfolio (Operations Research Quantitative Allocator)
# ---------------------------------------------------------------------------
def _sync_optimize_portfolio(
    user_id: Optional[str],
    symbols: Optional[List[str]] = None,
    capital: Optional[float] = None,
    use_my_portfolio: bool = False,
    objective: str = "balanced",
    max_weight_pct: Optional[float] = None,
    max_sector_pct: Optional[float] = None,
    min_cash_pct: Optional[float] = None,
    sharia_only: bool = False,
    market: Optional[str] = None,
    telegram_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Run Operations Research portfolio optimization on user holdings and/or requested symbols."""
    import math as _math
    from datetime import datetime, timedelta, timezone
    from api.portfolio_or_optimizer import (
        AssetInput,
        compute_returns_by_date,
        normalize_objective,
        optimize_portfolio_or,
    )
    from api.sharia_stocks import is_sharia_compliant
    from api.agentic_chat.market_registry import currency_for_market, normalize_exchange_code

    # Validate explicit capital early (fail closed on <= 0 or NaN/Inf)
    parsed_capital: Optional[float] = None
    if capital is not None:
        try:
            cap_val = float(capital)
        except (TypeError, ValueError):
            return {"status": "error", "message": "قيمة رأس المال غير صالحة؛ أدخل رقماً موجباً مثل 50000 أو 100000."}
        if not _math.isfinite(cap_val) or cap_val <= 0:
            return {"status": "error", "message": "يجب إدخال رأس مال صحيح وموجب لتشغيل التحسين الرياضي."}
        parsed_capital = cap_val

    use_pf = bool(use_my_portfolio)
    req_syms_raw = [str(s).strip() for s in (symbols or []) if str(s or "").strip()]
    if not req_syms_raw and not use_pf:
        use_pf = True

    effective_tg_id = telegram_user_id if telegram_user_id is not None else _TG_PORTFOLIO_CTX.get()

    if use_pf and _GROUP_PORTFOLIO_BLOCKED_CTX.get():
        return {
            "status": "redirect_private",
            "requires_private_chat": True,
            "private_bot_url": "https://t.me/egxbots_bot?start=b2b_portfolio",
            "message": (
                "لحماية خصوصية محفظتك، تم تعطيل قراءة المحفظة الشخصية داخل الجروبات. "
                "يمكنك إرسال قائمة رموز الأسهم ورأس المال مباشرة للتوزيع الرياضي، أو استخدام البوت الخاص لتحسين محفظتك المسجلة."
            ),
        }

    sb = _get_sb()
    if sb is None:
        return {"status": "error", "message": "تعذر الاتصال بقاعدة البيانات لتشغيل محرك التحسين الرياضي."}

    # 1. Resolve symbols and existing holdings (supports website auth + unlinked private Telegram)
    existing_shares_map: Dict[str, float] = {}
    existing_cash = 0.0
    resolved_pairs: List[Tuple[str, str]] = []
    seen_syms: set[str] = set()

    def _add_resolved(raw_token: str, market_hint: Optional[str]) -> Optional[str]:
        sym_r, exch_r = _resolve_symbol_and_market(raw_token, explicit_market=market_hint)
        clean_s = str(sym_r or "").strip().upper()
        canon_e = normalize_exchange_code(exch_r)
        if not clean_s:
            return None
        if clean_s not in seen_syms:
            seen_syms.add(clean_s)
            resolved_pairs.append((clean_s, canon_e))
        return clean_s

    if use_pf:
        if effective_tg_id is not None:
            try:
                tg_state = _load_tg_portfolio_state(sb, int(effective_tg_id))
                existing_cash = max(0.0, _safe_float(tg_state.get("cash_balance")) or 0.0)
                for row in (tg_state.get("positions") or []):
                    qty = _safe_float(row.get("quantity")) or 0.0
                    raw_sym = str(row.get("symbol") or "").strip()
                    if raw_sym and qty > 0:
                        clean_u = _add_resolved(raw_sym, market)
                        if clean_u:
                            existing_shares_map[clean_u] = existing_shares_map.get(clean_u, 0.0) + qty
            except Exception as pf_err:
                return {"status": "error", "message": f"تعذر قراءة مراكز محفظة تليجرام: {pf_err}"}
        elif not user_id:
            if not req_syms_raw:
                return {
                    "status": "error",
                    "requires_login": True,
                    "message": "يلزم تسجيل الدخول لتحسين محفظتك المحفوظة، أو اذكر قائمة رموز الأسهم ورأس المال المطلوب توزيعه مباشرة.",
                }
        else:
            try:
                pos_res = (
                    sb.from_("positions")
                    .select("symbol, quantity, entry_price")
                    .eq("user_id", user_id)
                    .eq("status", "open")
                    .limit(25)
                    .execute()
                )
                for row in (pos_res.data or []):
                    qty = _safe_float(row.get("quantity")) or 0.0
                    raw_sym = str(row.get("symbol") or "").strip()
                    if raw_sym and qty > 0:
                        clean_u = _add_resolved(raw_sym, market)
                        if clean_u:
                            existing_shares_map[clean_u] = existing_shares_map.get(clean_u, 0.0) + qty
                prof_res = sb.from_("profiles").select("cash_balance").eq("id", user_id).limit(1).execute()
                if prof_res.data:
                    existing_cash = max(0.0, _safe_float(prof_res.data[0].get("cash_balance")) or 0.0)
            except Exception as pf_err:
                return {"status": "error", "message": f"تعذر قراءة مراكز المحفظة: {pf_err}"}

    for raw_s in req_syms_raw:
        _add_resolved(raw_s, market)

    resolved_pairs = resolved_pairs[:20]
    resolved_syms = [s for s, _ in resolved_pairs]
    if not resolved_syms:
        return {
            "status": "error",
            "message": "لم يتم العثور على أسهم للتحسين. اذكر رموز الأسهم المطلوب توزيع رأس المال عليها أو أضف مراكز إلى محفظتك أولاً.",
        }

    # Determine canonical exchange code (EGX, TADAWUL, DFM, ADX, QSE)
    if market:
        exch = normalize_exchange_code(market)
    else:
        pair_exches = [e for _, e in resolved_pairs if e]
        if pair_exches:
            exch = max(set(pair_exches), key=pair_exches.count)
        else:
            exch = normalize_exchange_code(_ACTIVE_MARKET_CTX.get() or "EGX")
    currency = currency_for_market(exch)
    sharia_mkt_arg = "tasi" if exch == "TADAWUL" else exch.lower()

    # Optional Sharia filter
    excluded_sharia: List[str] = []
    if sharia_only:
        filtered = []
        for s in resolved_syms:
            if is_sharia_compliant(s, market=sharia_mkt_arg):
                filtered.append(s)
            else:
                excluded_sharia.append(s)
        resolved_syms = filtered
        if not resolved_syms:
            return {
                "status": "error",
                "excluded_non_sharia": excluded_sharia,
                "message": "جميع الأسهم المطلوبة غير مدرجة في قائمة الأسهم المتوافقة مع الشريعة لهذا السوق.",
            }

    # 2. Route market tables to the proper market Supabase (EGX primary vs Saudi/GCC SAUDI_SUPABASE)
    mkt_sb = _get_sb_for_market(exch) or sb
    ind_map: Dict[str, Dict[str, Any]] = {}
    stock_meta: Dict[str, Dict[str, Any]] = {}
    price_rows: List[Dict[str, Any]] = []
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=145)).strftime("%Y-%m-%d")

    try:
        if exch == "EGX":
            ti_cols = "symbol, date, close, rsi_14, ema_50, ema_200, r_vol, atr_14, change_pct, exchange"
            ti_order = "date"
        else:
            ti_cols, ti_order = _saudi_ti_select_and_order(mkt_sb)
        ind_res = (
            mkt_sb.from_("stock_technical_indicators")
            .select(ti_cols)
            .eq("exchange", exch)
            .in_("symbol", resolved_syms)
            .order(ti_order, desc=True)
            .limit(len(resolved_syms) * 2)
            .execute()
        )
        for row in (ind_res.data or []):
            s_u = str(row.get("symbol") or "").strip().upper()
            if s_u and s_u not in ind_map:
                ind_map[s_u] = row
    except Exception:
        pass

    try:
        st_cols = "symbol, name, name_ar, exchange" if exch == "EGX" else "symbol, name, name_ar, sector, exchange"
        st_res = (
            mkt_sb.from_("stocks")
            .select(st_cols)
            .eq("exchange", exch)
            .in_("symbol", resolved_syms)
            .limit(len(resolved_syms) * 2)
            .execute()
        )
        for row in (st_res.data or []):
            s_u = str(row.get("symbol") or "").strip().upper()
            if s_u and s_u not in stock_meta:
                stock_meta[s_u] = row
    except Exception:
        pass

    # Fetch rich institutional fundamentals (sector, industry, fund_score, dividendYield, eps, pe, roe) for ALL markets
    fund_opt_map: Dict[str, Dict[str, Any]] = {}
    try:
        sf_res = (
            mkt_sb.from_("stock_fundamentals")
            .select("symbol, data, fund_score")
            .eq("exchange", exch)
            .in_("symbol", resolved_syms)
            .limit(len(resolved_syms) + 5)
            .execute()
        )
        for row in (sf_res.data or []):
            s_u = str(row.get("symbol") or "").strip().upper()
            if s_u and s_u not in fund_opt_map:
                fund_opt_map[s_u] = row
    except Exception:
        pass

    try:
        pr_res = (
            mkt_sb.from_("stock_prices")
            .select("symbol, date, close, volume")
            .eq("exchange", exch)
            .in_("symbol", resolved_syms)
            .gte("date", cutoff_date)
            .order("date", desc=True)
            .limit(min(2400, max(120, len(resolved_syms) * 120)))
            .execute()
        )
        price_rows = pr_res.data or []
    except Exception:
        price_rows = []

    returns_map = compute_returns_by_date(price_rows)
    latest_close_map: Dict[str, float] = {}
    price_rows_by_sym: Dict[str, List[Dict[str, Any]]] = {}
    for row in price_rows:
        s_u = str(row.get("symbol") or "").strip().upper()
        if s_u:
            lst = price_rows_by_sym.setdefault(s_u, [])
            if len(lst) < 120:
                lst.append(row)
        c_val = _safe_float(row.get("close"))
        if s_u and c_val and c_val > 0 and s_u not in latest_close_map:
            latest_close_map[s_u] = c_val

    # Optional Fair Value upside map for ALL 4 markets (cached, zero extra DB queries on warm cache)
    fv_upside_map: Dict[str, float] = {}
    _fv_mkt_map = {"EGX": "egx", "TADAWUL": "tasi", "QSE": "qatar", "DFM": "uae", "ADX": "uae"}
    try:
        fv_key = _fv_mkt_map.get(exch)
        if fv_key:
            from api.routers.offload_public import _get_fair_value
            fv_rep = _get_fair_value(fv_key)
            for st in (fv_rep.get("stocks") or []):
                s_u = str(st.get("symbol") or "").strip().upper()
                up = _safe_float(st.get("upsidePct"))
                if s_u and up is not None:
                    fv_upside_map[s_u] = up
    except Exception:
        pass

    try:
        from api.routers.offload_public import _resolve_sector_ar
    except Exception:
        _resolve_sector_ar = None

    # 3. Assemble AssetInput list (combining Fair Value + Fundamental Quality + Liquidity + Technical Health)
    candidate_items: List[Dict[str, Any]] = []
    missing_syms: List[str] = []
    fund_summary_by_sym: Dict[str, Dict[str, Any]] = {}
    for sym in resolved_syms:
        ind = ind_map.get(sym) or {}
        meta = stock_meta.get(sym) or {}
        sf_row = fund_opt_map.get(sym) or {}
        raw_sf_data = sf_row.get("data") if isinstance(sf_row.get("data"), dict) else {}
        price = _safe_float(ind.get("close")) or latest_close_map.get(sym)
        if not price or not _math.isfinite(price) or price <= 0:
            missing_syms.append(sym)
            continue
        atr = _safe_float(ind.get("atr_14"))
        fallback_vol = max(0.008, min(0.08, (atr / price) if (atr and price > 0) else 0.022))

        adj_ema50, adj_ema200, sp_factor, _ = _detect_and_adjust_price_split(
            price_rows_by_sym.get(sym) or [],
            _safe_float(ind.get("ema_50")),
            _safe_float(ind.get("ema_200")),
            price,
        )
        sf_data, _ = _normalize_split_adjusted_fundamentals(raw_sf_data, price, split_factor=sp_factor)

        f_score = _safe_float(sf_row.get("fund_score"))
        f_dy = _safe_float(sf_data.get("dividendYield") or sf_data.get("dividend_yield"))
        f_eps = _safe_float(sf_data.get("eps") or sf_data.get("trailing_eps"), 4)
        f_ni = _safe_float(sf_data.get("netIncome") or sf_data.get("net_income"), 2)
        f_bvps = _safe_float(
            sf_data.get("bookValuePerShare")
            if sf_data.get("bookValuePerShare") is not None
            else (sf_data.get("book_value_per_share") if sf_data.get("book_value_per_share") is not None else sf_data.get("bvps")),
            4,
        )
        f_pe = _safe_float(sf_data.get("peRatio") or sf_data.get("pe_ratio"))
        f_roe = _safe_float(sf_data.get("roe") or sf_data.get("return_on_equity"))
        f_fcf = _safe_float(
            sf_data.get("freeCashFlow")
            if sf_data.get("freeCashFlow") is not None
            else sf_data.get("free_cash_flow"),
            2,
        )
        is_loss_making = bool(
            (f_eps is not None and f_eps < 0)
            or (f_ni is not None and f_ni < 0)
            or (f_roe is not None and f_roe < 0)
        )
        is_negative_equity = bool(f_bvps is not None and f_bvps <= 0)

        liq_opt = _assess_stock_liquidity(price_rows_by_sym.get(sym) or [], ind, price, exch)
        zero_vol_days_10 = liq_opt["zero_vol_days_10"]
        is_illiquid = liq_opt["is_illiquid"]
        r_vol = liq_opt["r_vol"]
        is_thin_liquidity = bool((not is_illiquid) and liq_opt["is_thin_liquidity"])
        is_unhealthy_loss = bool(is_negative_equity or (is_loss_making and (f_score is None or f_score < 50.0)))
        over_and_weak = bool(
            f_pe is not None
            and f_pe > 30.0
            and ((f_fcf is not None and f_fcf < 0) or (adj_ema50 and price < adj_ema50))
        )
        is_hard_excluded = bool(is_illiquid or is_negative_equity or is_loss_making or over_and_weak)
        is_hold_core = bool((not is_hard_excluded) and (f_score is not None and f_score >= 65.0) and (f_pe is None or f_pe <= 22.0))

        fund_summary_by_sym[sym] = {
            k: v
            for k, v in {
                "fund_score": f_score,
                "dividend_yield_pct": f_dy,
                "pe_ratio": f_pe,
                "roe_pct": f_roe,
                "is_illiquid": True if is_illiquid else None,
                "is_thin_liquidity": True if is_thin_liquidity else None,
            }.items()
            if v is not None
        }

        # Bounded quantitative composite signal in [-1, 1] (Fundamental Quality + Fair Value + Trend + RSI + RVol)
        score = 0.0
        if f_score is not None:
            # Map fund_score (0..100, centered at 55) into [-0.30, +0.30]
            score += max(-0.30, min(0.30, (f_score - 55.0) / 130.0))
        if is_loss_making:
            score -= 0.35  # Penalize loss-making companies inside portfolio optimizer
        else:
            if f_fcf is not None and f_fcf < 0:
                score -= 0.18
            if f_pe is not None and f_pe > 30.0:
                score -= 0.25
            if f_dy is not None and f_dy >= 3.0:
                score += min(0.12, f_dy / 50.0)

        up_pct = fv_upside_map.get(sym)
        if up_pct is not None:
            # Never apply an upside valuation bonus to loss-making or illiquid stocks
            if not is_loss_making and not is_illiquid:
                score += max(-0.35, min(0.35, up_pct / 75.0))
            elif up_pct < 0:
                score += max(-0.35, up_pct / 75.0)
        if adj_ema50 and adj_ema50 > 0:
            score += 0.20 if price >= adj_ema50 else -0.15
        rsi = _safe_float(ind.get("rsi_14"))
        if rsi is not None:
            if 45.0 <= rsi <= 65.0:
                score += 0.12
            elif rsi > 74.0:
                score -= 0.18
            elif rsi < 35.0:
                score -= 0.08
        if r_vol is not None and r_vol >= 1.1 and not is_illiquid:
            score += 0.08
        score = max(-1.0, min(1.0, score))

        raw_sec = meta.get("sector") or sf_data.get("sector")
        raw_ind = sf_data.get("industry")
        if _resolve_sector_ar is not None:
            sector_label = str(_resolve_sector_ar(sym, raw_sec, raw_ind) or raw_sec or "أخرى").strip() or "أخرى"
        else:
            sector_label = str(raw_sec or "أخرى").strip() or "أخرى"
        name_ar = str(meta.get("name_ar") or sf_data.get("name_ar") or meta.get("name") or sf_data.get("name") or sym).strip()

        candidate_items.append({
            "sym": sym,
            "price": price,
            "name_ar": name_ar,
            "sector_label": sector_label,
            "existing_shares": existing_shares_map.get(sym, 0.0),
            "score": score,
            "fallback_vol": fallback_vol,
            "returns": returns_map.get(sym) or {},
            "is_illiquid": is_illiquid,
            "is_thin_liquidity": is_thin_liquidity,
            "is_unhealthy_loss": is_unhealthy_loss,
            "is_loss_making": is_loss_making,
            "is_negative_equity": is_negative_equity,
            "is_hard_excluded": is_hard_excluded,
            "is_hold_core": is_hold_core,
            "over_and_weak": over_and_weak,
            "f_pe": f_pe,
            "avg_vol_10": liq_opt.get("avg_vol_10"),
            "zero_vol_days_10": zero_vol_days_10,
        })

    holdings_eq_pre = sum(it["existing_shares"] * it["price"] for it in candidate_items)
    if parsed_capital is not None:
        if use_pf and holdings_eq_pre > 0 and parsed_capital < holdings_eq_pre:
            est_total_eq = holdings_eq_pre + existing_cash + parsed_capital
        else:
            est_total_eq = max(holdings_eq_pre, parsed_capital)
    else:
        est_total_eq = holdings_eq_pre + existing_cash

    healthy_count = sum(1 for item in candidate_items if not item["is_hard_excluded"])
    core_count = sum(1 for item in candidate_items if item["is_hold_core"])
    eff_default_max_w = 25.0 if healthy_count >= 5 else 35.0
    eff_cap_pct = float(max_weight_pct) if max_weight_pct is not None else eff_default_max_w
    eff_cap_frac = eff_cap_pct / 100.0
    eff_invested_frac = max(0.0, min(1.0, 1.0 - max(0.0, min(0.80, float(min_cash_pct or 0.0) / 100.0))))
    core_cap_sum = sum(
        min(eff_cap_frac, 0.15) if (healthy_count >= 3 and it["is_thin_liquidity"]) else eff_cap_frac
        for it in candidate_items
        if it["is_hold_core"]
    )
    watch_cap_sum = sum(
        min(
            min(eff_cap_frac, 0.15) if (healthy_count >= 3 and it["is_thin_liquidity"]) else eff_cap_frac,
            ((it["existing_shares"] * it["price"]) / est_total_eq) if est_total_eq > 0 else 0.0,
        )
        for it in candidate_items
        if (not it["is_hard_excluded"] and not it["is_hold_core"])
    )
    cap_hold_watch = bool(use_pf and core_count >= 3 and (core_cap_sum + watch_cap_sum) >= eff_invested_frac + 1e-6)

    assets: List[AssetInput] = []
    for item in candidate_items:
        max_w_ov = None
        excl_reason = None
        sc = item["score"]
        if healthy_count >= 2 and item["is_hard_excluded"]:
            max_w_ov = 0.0
            sc = -0.85
            if item["is_illiquid"] and item["is_loss_making"]:
                excl_reason = f"سيولة شبه منعدمة ({item['zero_vol_days_10']} جلسات تداول صفري) وخسائر صافية — مستبعد من الشراء"
            elif item["is_illiquid"]:
                excl_reason = f"سيولة منعدمة أو ضعيفة جداً ({item['zero_vol_days_10']} جلسات تداول صفري) — مستبعد من الشراء"
            elif item["is_negative_equity"]:
                excl_reason = "شركة خاسرة وحقوق ملكية سالبة — مستبعد من الشراء أو التعزيز"
            elif item["is_loss_making"]:
                excl_reason = "شركة تحقق صافي خسائر — مستبعد من الشراء أو التعزيز"
            elif item["over_and_weak"]:
                excl_reason = f"مكرر ربحية متضخم (P/E={float(item['f_pe']):.1f}x) مع اتجاه هابط أو تدفق نقدي سالب — مستبعد من الشراء"
            else:
                excl_reason = "شركة خاسرة وتقييم مالي ضعيف — مستبعد من زيادة الوزن"
        elif cap_hold_watch and (not item["is_hold_core"]):
            curr_w_frac = ((item["existing_shares"] * item["price"]) / est_total_eq) if est_total_eq > 0 else 0.0
            base_watch_cap = min(eff_cap_frac, 0.15) if (healthy_count >= 3 and item["is_thin_liquidity"]) else eff_cap_frac
            max_w_ov = min(base_watch_cap, curr_w_frac)
        elif healthy_count >= 3 and item["is_thin_liquidity"]:
            max_w_ov = min(eff_cap_frac, 0.15)
        assets.append(
            AssetInput(
                symbol=item["sym"],
                price=item["price"],
                name_ar=item["name_ar"],
                sector=item["sector_label"],
                current_shares=item["existing_shares"],
                expected_score=sc,
                fallback_daily_vol=item["fallback_vol"],
                returns_by_date=item["returns"],
                max_weight_override=max_w_ov,
                exclusion_reason=excl_reason,
                avg_daily_volume=item.get("avg_vol_10"),
            )
        )

    if not assets:
        return {
            "status": "error",
            "missing_symbols": missing_syms,
            "message": "لم يتم العثور على أسعار متاحة للرموز المطلوبة في قاعدة البيانات.",
        }

    holdings_equity = sum(a.current_shares * a.price for a in assets)
    if parsed_capital is not None:
        if use_pf and holdings_equity > 0:
            # If user supplies an amount smaller than current holdings, treat it as additional cash on top of holdings + existing cash;
            # otherwise treat it as the total target equity (always >= holdings_equity so current weights never exceed 100%).
            if parsed_capital < holdings_equity:
                total_capital = holdings_equity + existing_cash + parsed_capital
            else:
                total_capital = parsed_capital
        else:
            total_capital = parsed_capital
    elif holdings_equity + existing_cash > 0:
        total_capital = holdings_equity + existing_cash
    else:
        total_capital = 100000.0 if exch == "EGX" else 50000.0

    res = optimize_portfolio_or(
        assets,
        total_capital=total_capital,
        objective=normalize_objective(objective),
        max_weight_pct=eff_cap_pct,
        max_sector_pct=float(max_sector_pct) if max_sector_pct is not None else 45.0,
        min_cash_pct=float(min_cash_pct) if min_cash_pct is not None else 0.0,
        exchange=exch,
        turnover_penalty=0.015 if holdings_equity > 0 else 0.0,
    )

    # Enrich OR allocations with fundamental metrics & portfolio-level weighted fund_score / dividend yield
    allocs = res.get("allocations") if isinstance(res, dict) else None
    if isinstance(allocs, list):
        w_fs_num = w_fs_den = 0.0
        w_dy_num = 0.0
        for row in allocs:
            s_u = str(row.get("symbol") or "").upper()
            fs_info = fund_summary_by_sym.get(s_u) or {}
            if fs_info:
                row.update(fs_info)
            tw = float(row.get("targetWeightPct") or 0.0)
            if tw > 0:
                if fs_info.get("fund_score") is not None:
                    w_fs_num += tw * float(fs_info["fund_score"])
                    w_fs_den += tw
                if fs_info.get("dividend_yield_pct") is not None:
                    w_dy_num += (tw / 100.0) * float(fs_info["dividend_yield_pct"])
        if w_fs_den > 0:
            res["weightedFundScore"] = round(w_fs_num / w_fs_den, 1)
        if w_dy_num > 0:
            res["expectedDividendYieldPct"] = round(w_dy_num, 2)

    return {
        "status": "success",
        "currency": currency,
        "exchange": exch,
        "capitalAssumedDefault": bool(parsed_capital is None and (holdings_equity + existing_cash) <= 0),
        "excludedNonSharia": excluded_sharia,
        "missingSymbols": missing_syms,
        "optimization": res,
        "disclaimerAr": "نتائج المحاكاة الرياضية (بحوث العمليات) أداة تحليل كمي لإدارة المخاطر والتنويع لأغراض البحث والتعليم الشخصي فقط، وليست توصية استثمارية أو ضماناً للعائد.",
    }


async def execute_optimize_portfolio(
    user_id: Optional[str],
    symbols: Optional[List[str]] = None,
    capital: Optional[float] = None,
    use_my_portfolio: bool = False,
    objective: str = "balanced",
    max_weight_pct: Optional[float] = None,
    max_sector_pct: Optional[float] = None,
    min_cash_pct: Optional[float] = None,
    sharia_only: bool = False,
    market: Optional[str] = None,
    telegram_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    effective_tg_id = telegram_user_id if telegram_user_id is not None else _TG_PORTFOLIO_CTX.get()
    return await asyncio.to_thread(
        _sync_optimize_portfolio,
        user_id,
        symbols,
        capital,
        use_my_portfolio,
        objective,
        max_weight_pct,
        max_sector_pct,
        min_cash_pct,
        sharia_only,
        market,
        effective_tg_id,
    )


# ---------------------------------------------------------------------------
# Tool: manage_automations
# ---------------------------------------------------------------------------
_TIME_HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _normalize_hhmm(raw: str) -> Optional[str]:
    m = _TIME_HHMM_RE.match((raw or "").strip())
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"


def _sync_manage_automations(
    user_id: Optional[str],
    operation: str = "list",
    name: Optional[str] = None,
    prompt: Optional[str] = None,
    scheduled_times: Optional[List[str]] = None,
    scheduled_time: Optional[str] = None,
    days_of_week: str = "trading_days",
    automation_id: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Dict[str, Any]:
    """Create, list, toggle, or delete Scheduled AI Chat Automations directly from chat."""
    if not user_id:
        return {
            "status": "error",
            "requires_login": True,
            "message": "يلزم تسجيل الدخول لحسابك على الموقع لإدارة المهام المجدولة (الأتمتة).",
        }

    sb = _get_sb()
    op = (operation or "list").lower().strip()

    if op == "list":
        try:
            res = (
                sb.from_("scheduled_chat_automations")
                .select("id,name,prompt,scheduled_time,days_of_week,is_active,last_run_at,last_status,created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(10)
                .execute()
            )
            rows = res.data or []
            return {
                "status": "success",
                "operation": "list",
                "count": len(rows),
                "max_allowed": 5,
                "automations": rows,
                "message": f"لديك {len(rows)} مهمة مجدولة من أصل 5 مهام متاحة.",
            }
        except Exception as e:
            return {"status": "error", "message": f"تعذر جلب المهام المجدولة: {str(e)}"}

    # Verify Chat Pro subscription (Full Pro or AI Chat Only — excludes vip_only) & Telegram link
    is_pro = False
    try:
        from api.plan_limits import has_chat_pro_user

        is_pro = has_chat_pro_user(user_id, sb)
    except Exception:
        is_pro = False

    if not is_pro:
        return {
            "status": "pro_required",
            "message": "ميزة الأتمتة اليومية المجدولة متاحة لمشتركي باقة الشات الذكي (100 ج.م) أو الباقة الشاملة Pro (150 ج.م). يمكنك الترقية عبر https://egxbots.com/pricing",
        }

    tg_chat_id: Optional[str] = None
    try:
        p_res = sb.from_("profiles").select("telegram_chat_id").eq("id", user_id).limit(1).execute()
        if p_res.data:
            tg_chat_id = str(p_res.data[0].get("telegram_chat_id") or "").strip() or None
    except Exception:
        tg_chat_id = None

    if op == "create":
        if not tg_chat_id:
            return {
                "status": "no_telegram_linked",
                "connect_url": f"https://t.me/egxbots_bot?start={user_id}",
                "message": (
                    "حسابك غير مربوط ببوت تليجرام بعد. "
                    f"افتح الرابط التالي واضغط Start لربط حسابك واستلام التقارير المجدولة: https://t.me/egxbots_bot?start={user_id}"
                ),
            }

        clean_prompt = (prompt or "").strip()
        if len(clean_prompt) < 3:
            return {"status": "needs_clarification", "message": "يرجى تحديد نص السؤال المطلوب جدولته بوضوح (3 أحرف على الأقل)."}

        raw_times: List[str] = []
        if isinstance(scheduled_times, list) and scheduled_times:
            raw_times.extend(str(t) for t in scheduled_times if t)
        elif scheduled_time:
            raw_times.append(str(scheduled_time))
        else:
            raw_times.append("08:30")

        norm_times: List[str] = []
        for rt in raw_times:
            nt = _normalize_hhmm(rt)
            if not nt:
                return {"status": "error", "message": f"صيغة الوقت '{rt}' غير صالحة. استخدم صيغة HH:MM مثل 10:30 أو 14:00."}
            if nt not in norm_times:
                norm_times.append(nt)

        try:
            existing_res = sb.from_("scheduled_chat_automations").select("id,scheduled_time").eq("user_id", user_id).limit(6).execute()
            existing_rows = existing_res.data or []
        except Exception as e:
            return {"status": "error", "message": f"تعذر فحص المهام الحالية: {str(e)}"}

        remaining = max(0, 5 - len(existing_rows))
        if len(norm_times) > remaining:
            return {
                "status": "limit_exceeded",
                "existing_count": len(existing_rows),
                "remaining_slots": remaining,
                "message": (
                    f"لديك حالياً {len(existing_rows)} مهام مجدولة من الحد الأقصى (5 مهام)، المتبقي {remaining} خانات فقط "
                    f"بينما طلبت إضافة {len(norm_times)} مواعيد. احذف مهمة قديمة أو قلّل عدد المواعيد."
                ),
            }

        eff_days = "all_days" if days_of_week == "all_days" else "trading_days"
        base_name = (name or "").strip()[:70]
        if not base_name:
            snippet = clean_prompt.replace("\n", " ").strip()
            base_name = f"استشارة: {snippet[:35]}..." if len(snippet) > 35 else f"استشارة: {snippet}"

        rows_to_insert = []
        for idx, t_str in enumerate(norm_times):
            row_name = f"{base_name} ({t_str})" if len(norm_times) > 1 else base_name
            rows_to_insert.append({
                "user_id": user_id,
                "name": row_name[:80],
                "prompt": clean_prompt,
                "scheduled_time": t_str,
                "days_of_week": eff_days,
                "telegram_chat_id": tg_chat_id,
                "is_active": True,
            })

        try:
            ins_res = sb.from_("scheduled_chat_automations").insert(rows_to_insert).execute()
            created = ins_res.data or rows_to_insert
            try:
                from api.scheduled_automations_worker import sync_automations_cache
                threading.Thread(target=sync_automations_cache, daemon=True).start()
            except Exception:
                pass
            total_after = len(existing_rows) + len(created)
            remaining_after = max(0, 5 - total_after)
            return {
                "status": "success",
                "operation": "create",
                "created_count": len(created),
                "total_count": total_after,
                "max_allowed": 5,
                "remaining_slots": remaining_after,
                "scheduled_times": norm_times,
                "days_of_week": eff_days,
                "automations": created,
                "message": (
                    f"تمت جدولة {len(created)} مهمة أتمتة بنجاح بتوقيت القاهرة ({', '.join(norm_times)}) "
                    f"وسيتم إرسال التقارير تلقائياً إلى تليجرام. "
                    f"إجمالي المهام في حسابك الآن: {total_after} من 5 (المتبقي {remaining_after})."
                ),
            }
        except Exception as e:
            return {"status": "error", "message": f"تعذر حفظ الأتمتة في قاعدة البيانات: {str(e)}"}

    elif op == "toggle":
        if not automation_id:
            return {"status": "needs_clarification", "message": "يرجى تحديد معرف المهمة المطلوب تفعيلها أو إيقافها."}
        try:
            cur = sb.from_("scheduled_chat_automations").select("id,is_active,name").eq("id", automation_id).eq("user_id", user_id).limit(1).execute()
            if not cur.data:
                return {"status": "error", "message": "لم يتم العثور على المهمة المحددة."}
            new_state = (not bool(cur.data[0].get("is_active"))) if is_active is None else bool(is_active)
            sb.from_("scheduled_chat_automations").update({"is_active": new_state}).eq("id", automation_id).eq("user_id", user_id).execute()
            try:
                from api.scheduled_automations_worker import sync_automations_cache
                threading.Thread(target=sync_automations_cache, daemon=True).start()
            except Exception:
                pass
            return {
                "status": "success",
                "operation": "toggle",
                "automation_id": automation_id,
                "is_active": new_state,
                "message": f"تم {'تفعيل' if new_state else 'إيقاف'} المهمة بنجاح.",
            }
        except Exception as e:
            return {"status": "error", "message": f"تعذر تحديث حالة المهمة: {str(e)}"}

    elif op == "delete":
        if not automation_id:
            return {"status": "needs_clarification", "message": "يرجى تحديد معرف المهمة المطلوب حذفها."}
        try:
            sb.from_("scheduled_chat_automations").delete().eq("id", automation_id).eq("user_id", user_id).execute()
            try:
                from api.scheduled_automations_worker import sync_automations_cache
                threading.Thread(target=sync_automations_cache, daemon=True).start()
            except Exception:
                pass
            return {
                "status": "success",
                "operation": "delete",
                "automation_id": automation_id,
                "message": "تم حذف المهمة المجدولة بنجاح.",
            }
        except Exception as e:
            return {"status": "error", "message": f"تعذر حذف المهمة: {str(e)}"}

    return {"status": "error", "message": f"العملية {op} غير مدعومة في إدارة الأتمتة."}


async def execute_manage_automations(
    user_id: Optional[str],
    operation: str = "list",
    name: Optional[str] = None,
    prompt: Optional[str] = None,
    scheduled_times: Optional[List[str]] = None,
    scheduled_time: Optional[str] = None,
    days_of_week: str = "trading_days",
    automation_id: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        _sync_manage_automations,
        user_id,
        operation,
        name,
        prompt,
        scheduled_times,
        scheduled_time,
        days_of_week,
        automation_id,
        is_active,
    )


BENCHMARK_FIXTURES: Dict[str, Any] = {
    "get_stock": {
        "status": "success",
        "stocks": [
            {
                "symbol": "COMI",
                "name_ar": "البنك التجاري الدولي",
                "name_en": "Commercial International Bank",
                "close": 129.50,
                "change_pct": 1.25,
                "volume": 2450000,
                "rsi_14": 52.4,
                "macd": 0.85,
                "macd_signal": 0.60,
                "macd_histogram": 0.25,
                "bb_upper": 133.0,
                "bb_lower": 124.0,
                "ema_50": 125.2,
                "ema_200": 118.5,
                "sharia_compliant": True,
                "king_ai_score": 8.5,
                "egx_ai_score": 8.8,
            },
            {
                "symbol": "FWRY",
                "name_ar": "فوري لتكنولوجيا البنوك",
                "name_en": "Fawry",
                "close": 7.85,
                "change_pct": 2.10,
                "volume": 12400000,
                "rsi_14": 58.2,
                "macd": 0.12,
                "macd_signal": 0.08,
                "macd_histogram": 0.04,
                "bb_upper": 8.10,
                "bb_lower": 7.45,
                "ema_50": 7.55,
                "ema_200": 6.95,
                "sharia_compliant": True,
                "king_ai_score": 7.9,
                "egx_ai_score": 8.1,
            },
            {
                "symbol": "ETEL",
                "name_ar": "المصرية للاتصالات",
                "name_en": "Telecom Egypt",
                "close": 36.80,
                "change_pct": -0.54,
                "volume": 850000,
                "rsi_14": 46.8,
                "macd": -0.15,
                "macd_signal": -0.10,
                "macd_histogram": -0.05,
                "bb_upper": 38.5,
                "bb_lower": 35.2,
                "ema_50": 36.5,
                "ema_200": 34.8,
                "sharia_compliant": True,
                "king_ai_score": 7.2,
                "egx_ai_score": 7.5,
            }
        ]
    },
    "get_stock_levels": {
        "status": "success",
        "levels": [
            {
                "symbol": "COMI",
                "current_price": 129.50,
                "support_1": 126.00,
                "support_2": 122.50,
                "resistance_1": 132.50,
                "resistance_2": 136.00,
                "stop_loss": 123.50,
                "target_1": 132.50,
                "target_2": 136.00,
                "trend": "صاعد معتدل",
            },
            {
                "symbol": "FWRY",
                "current_price": 7.85,
                "support_1": 7.60,
                "support_2": 7.35,
                "resistance_1": 8.10,
                "resistance_2": 8.40,
                "stop_loss": 7.40,
                "target_1": 8.10,
                "target_2": 8.40,
                "trend": "صاعد قوي",
            }
        ]
    },
    "get_market": {
        "status": "success",
        "egx30": {"value": 30550.0, "change_pct": 0.65},
        "egx70": {"value": 7250.0, "change_pct": 1.15},
        "egx33_sharia": {"value": 3120.0, "change_pct": 0.80},
        "total_turnover_egp": "3.85 مليار جنيه",
        "advancers": 85,
        "decliners": 42,
        "market_sentiment": "إيجابي تجميعي",
        "top_gainers": [{"symbol": "FWRY", "change_pct": 2.10}, {"symbol": "COMI", "change_pct": 1.25}],
        "top_turnover": [{"symbol": "COMI", "turnover_egp": "450 مليون"}, {"symbol": "TMGH", "turnover_egp": "380 مليون"}],
    },
    "get_recommendations": {
        "status": "success",
        "total_open": 3,
        "recommendations": [
            {"symbol": "COMI", "timeframe": "سوينغ قصير 🎯", "entry": 128.0, "target": 135.0, "stop": 123.0, "gain_expected": "+5.5%"},
            {"symbol": "FWRY", "timeframe": "لحظية سريعة ⚡", "entry": 7.75, "target": 8.20, "stop": 7.45, "gain_expected": "+5.8%"},
            {"symbol": "SWDY", "timeframe": "سوينغ متوسط 📈", "entry": 44.5, "target": 49.0, "stop": 42.0, "gain_expected": "+10.1%"},
        ]
    },
    "get_comparison": {
        "status": "success",
        "comparison": [
            {"symbol": "COMI", "name": "البنك التجاري الدولي", "price": 129.5, "rsi": 52.4, "pe_ratio": 7.8, "trend": "صاعد"},
            {"symbol": "ETEL", "name": "المصرية للاتصالات", "price": 36.8, "rsi": 46.8, "pe_ratio": 6.2, "trend": "عرضي"},
        ]
    },
    "get_technical_scan": {
        "status": "success",
        "signals": [
            {"symbol": "FWRY", "type": "اختراق مقاومة", "strength": "قوي", "price": 7.85},
            {"symbol": "COMI", "type": "دايفرجنس إيجابي", "strength": "متوسط", "price": 129.50},
        ]
    },
    "get_accumulation_stocks": {
        "status": "success",
        "accumulation_stocks": [
            {"symbol": "COMI", "score": 92, "phase": "تجميع ذكي (Markup)"},
            {"symbol": "FWRY", "score": 88, "phase": "تجميع وايكوف"},
        ]
    },
    "get_news": {
        "status": "success",
        "news": [
            {"title": "نتائج أعمال قوية ونمو أرباح قياسي", "date": "اليوم", "impact": "إيجابي"}
        ]
    },
    "manage_portfolio": {
        "status": "success",
        "operation": "view",
        "message": "محفظتك تحتوي على 2 سهم.",
        "positions_count": 2,
        "positions": [
            {
                "id": "pos_1",
                "symbol": "COMI",
                "name": "البنك التجاري الدولي",
                "quantity": 500,
                "entry_price": 125.0,
                "last_price": 129.50,
                "change_pct": 1.25,
                "market_value": 64750.0,
                "cost_basis": 62500.0,
                "profit_value": 2250.0,
                "profit_pct": 3.6,
            },
            {
                "id": "pos_2",
                "symbol": "FWRY",
                "name": "فوري لتكنولوجيا البنوك",
                "quantity": 2000,
                "entry_price": 7.50,
                "last_price": 7.85,
                "change_pct": 2.10,
                "market_value": 15700.0,
                "cost_basis": 15000.0,
                "profit_value": 700.0,
                "profit_pct": 4.67,
            },
        ],
        "cash_balance": 25000.0,
        "totals": {
            "positions_count": 2,
            "cost_basis": 77500.0,
            "market_value": 80450.0,
            "profit_value": 2950.0,
            "profit_pct": 3.81,
            "equity": 105450.0,
        },
    },
    "calculate_position": {
        "status": "success",
        "symbol": "COMI",
        "quantity": 500,
        "entry_price": 125.0,
        "close_price": 129.50,
        "total_cost": 62500.0,
        "current_market_value": 64750.0,
        "profit_loss_egp": 2250.0,
        "profit_loss_pct": 3.6,
    },
    "optimize_portfolio": {
        "status": "success",
        "currency": "ج.م",
        "exchange": "EGX",
        "optimization": {
            "objective": "balanced",
            "totalCapital": 100000.0,
            "investedAmount": 99650.0,
            "leftoverCash": 350.0,
            "estimatedFees": 179.37,
            "metricsBefore": {"annualVolatilityPct": 28.4, "effectiveStocks": 2.0},
            "metricsAfter": {"annualVolatilityPct": 22.1, "effectiveStocks": 3.6},
            "allocations": [],
        },
    },
    "manage_user_preferences": {
        "status": "success",
        "operation": "get",
        "rules": "- التداول بالأسهم المتوافقة مع الشريعة الإسلامية فقط",
        "message": "تم استرجاع تفضيلات المستخدم بنجاح.",
    },
}


def _sync_manage_user_preferences(
    user_id: Optional[str],
    operation: str,
    rule: Optional[str] = None,
    rules: Optional[List[str]] = None,
) -> Dict[str, Any]:
    from api.agentic_chat.user_preferences import (
        merge_user_rule,
        remove_user_rule,
        replace_user_rules,
        user_rules_list,
    )
    if not user_id or user_id == "00000000-0000-0000-0000-000000000000":
        return {
            "status": "unauthenticated",
            "message": "يجب تسجيل الدخول لحفظ أو تعديل الذاكرة والقواعد الدائمة.",
            "rules": "",
        }

    op = str(operation or "").strip().lower()
    _init_supabase()
    sb = supabase
    if not sb:
        return {"status": "error", "message": "قاعدة البيانات غير متاحة حالياً."}

    try:
        res = sb.table("profiles").select("custom_ai_rules").eq("id", user_id).limit(1).execute()
        existing = res.data[0].get("custom_ai_rules") if (res and res.data) else None
        existing_str = str(existing or "").strip()
        next_rules = existing_str

        if op == "get":
            return {
                "status": "success",
                "operation": "get",
                "rules": existing_str,
                "rules_list": user_rules_list(existing_str),
                "message": "القواعد الدائمة المحفوظة بحسابك:" if existing_str else "لا توجد قواعد دائمة محفوظة بحسابك حالياً.",
            }

        elif op == "add":
            if not rule or not str(rule).strip():
                return {"status": "error", "message": "يرجى تحديد نص القاعدة المراد حفظها في جملة واضحة."}
            next_rules = merge_user_rule(existing_str, str(rule).strip())
            if next_rules == existing_str:
                return {
                    "status": "success",
                    "operation": "add",
                    "saved": False,
                    "rules": existing_str,
                    "message": "هذه القاعدة مسجلة ومحفوظة بالفعل في ذاكرتك الدائمة.",
                }

        elif op == "delete":
            if not rule or not str(rule).strip():
                return {"status": "error", "message": "يرجى تحديد القاعدة أو الكلمة المراد حذفها من الذاكرة."}
            next_rules, removed = remove_user_rule(existing_str, str(rule).strip())
            if not removed:
                return {
                    "status": "success",
                    "operation": "delete",
                    "saved": False,
                    "rules": existing_str,
                    "message": "لم أجد قاعدة محفوظة مطابقة للنص المطلوب حذفه.",
                }

        elif op == "replace":
            if not rules or not isinstance(rules, list):
                return {"status": "error", "message": "قائمة القواعد الجديدة فارغة. لحذف كل القواعد استخدم عملية delete."}
            next_rules = replace_user_rules(rules)

        else:
            return {"status": "error", "message": f"العملية {op} غير مدعومة. العمليات المدعومة: add, delete, replace, get."}

        # Save to profiles table
        sb.table("profiles").update({"custom_ai_rules": next_rules if next_rules else None}).eq("id", user_id).execute()

        msg = (
            "تم حذف القاعدة من ذاكرتك الدائمة بنجاح."
            if op == "delete"
            else "تم حفظ وتحديث ذاكرتك الدائمة بنجاح، وسألتزم بهذه القواعد في كل محادثاتنا القادمة."
        )
        return {
            "status": "success",
            "operation": op,
            "saved": True,
            "rules": next_rules,
            "rules_list": user_rules_list(next_rules),
            "message": msg,
        }

    except Exception as e:
        logger.error(f"[agentic_chat] Error in manage_user_preferences: {e}")
        return {"status": "error", "message": f"تعذر تحديث الذاكرة الدائمة: {str(e)}"}


async def execute_manage_user_preferences(
    user_id: Optional[str],
    operation: str,
    rule: Optional[str] = None,
    rules: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        _sync_manage_user_preferences,
        user_id,
        operation,
        rule,
        rules,
    )


# ---------------------------------------------------------------------------
# Master Tool Dispatcher
# ---------------------------------------------------------------------------
async def dispatch_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: Optional[str] = None,
    user_prompt: str = "",
    default_market: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main asynchronous dispatcher for all agentic tools.
    Supports EGX and Saudi TASI (Tadawul) routing, with optional UI context market tie-breaker.
    """
    # Safe benchmark guard: Return in-memory fixtures to protect Supabase DB and quotas
    if user_id == "00000000-0000-0000-0000-000000000000":
        if tool_name in BENCHMARK_FIXTURES:
            return BENCHMARK_FIXTURES[tool_name]
        return {"status": "success", "data": "Benchmark mode active."}

    eff_default_mkt = arguments.get("market") or default_market
    ctx_token = set_active_market_context(eff_default_mkt) if eff_default_mkt else None
    try:
        result: Dict[str, Any]
        if tool_name == "search_stocks":
            raw_qs = arguments.get("queries")
            if not raw_qs and arguments.get("query"):
                raw_qs = [arguments["query"]]
            result = await execute_search_stocks(
                queries=raw_qs if isinstance(raw_qs, list) else ([str(raw_qs)] if raw_qs else []),
                market=arguments.get("market"),
            )

        elif tool_name == "get_stock":
            symbols = arguments.get("symbols") or ([arguments["symbol"]] if "symbol" in arguments else [])
            result = await execute_get_stock(symbols, market=arguments.get("market"))

        elif tool_name == "get_stock_levels":
            symbols = arguments.get("symbols") or ([arguments["symbol"]] if "symbol" in arguments else [])
            result = await execute_get_stock_levels(symbols, market=arguments.get("market"))

        elif tool_name == "get_market":
            result = await execute_get_market(market=arguments.get("market"))

        elif tool_name == "get_recommendations":
            if not _ALLOW_RECOMMENDATIONS_CTX.get():
                result = {
                    "status": "disabled",
                    "message": "تم تعطيل توصيات الشراء والبيع المفتوحة لهذه المجموعة بناءً على إعدادات الإدارة.",
                    "recommendations": [],
                }
            else:
                result = await execute_get_recommendations(
                    status=arguments.get("status", "open"),
                    timeframe=arguments.get("timeframe", "all"),
                    symbols=arguments.get("symbols"),
                    sharia_only=arguments.get("sharia_only", False),
                    limit=arguments.get("limit", 20),
                    market=arguments.get("market"),
                )

        elif tool_name == "get_technical_scan":
            result = await execute_get_technical_scan(
                preset=arguments.get("preset", "top_gainers"),
                sharia_only=arguments.get("sharia_only", False),
                market=arguments.get("market"),
            )

        elif tool_name == "get_accumulation_stocks":
            result = await execute_get_accumulation_stocks(
                sharia_only=arguments.get("sharia_only", False),
                market=arguments.get("market"),
            )

        elif tool_name == "get_news":
            news_syms = arguments.get("symbols")
            if not news_syms and arguments.get("symbol"):
                sym_val = str(arguments.get("symbol") or "").strip().upper()
                if sym_val and sym_val not in ("EGX", "MARKET", "ALL", "TASI", "SAUDI"):
                    news_syms = [sym_val]
            result = await execute_get_news(
                symbols=news_syms,
                market=arguments.get("market"),
            )

        elif tool_name == "get_comparison":
            result = await execute_get_comparison(symbols=arguments.get("symbols", []))

        elif tool_name == "get_fair_value":
            fv_syms = arguments.get("symbols")
            if not fv_syms and arguments.get("symbol"):
                fv_syms = [arguments.get("symbol")]
            result = await execute_get_fair_value(
                symbols=fv_syms,
                mode=arguments.get("mode", "screen_undervalued"),
                sharia_only=arguments.get("sharia_only", False),
                limit=arguments.get("limit", 10),
                market=arguments.get("market"),
            )

        elif tool_name == "get_dividends":
            result = await execute_get_dividends(
                symbols=arguments.get("symbols"),
                upcoming_only=arguments.get("upcoming_only", True),
                limit=arguments.get("limit", 15),
                market=arguments.get("market"),
            )

        elif tool_name == "get_sharia_cleanser":
            result = await execute_get_sharia_cleanser(
                symbol=arguments.get("symbol", ""),
                shares_count=arguments.get("shares_count", 1000.0),
                coupon_per_share=arguments.get("coupon_per_share"),
                purification_rate_pct=arguments.get("purification_rate_pct"),
                market=arguments.get("market"),
            )

        elif tool_name == "get_price_traps":
            result = await execute_get_price_traps(
                market=arguments.get("market"),
                symbol=arguments.get("symbol"),
                limit=arguments.get("limit", 8),
            )

        elif tool_name == "get_disclosures":
            result = await execute_get_disclosures(
                symbol=arguments.get("symbol"),
                disclosure_type=arguments.get("disclosure_type"),
                limit=arguments.get("limit", 10),
                market=arguments.get("market"),
            )

        elif tool_name == "manage_portfolio":
            result = await execute_manage_portfolio(
                user_id=user_id,
                operation=arguments.get("operation", "view"),
                symbol=arguments.get("symbol"),
                quantity=arguments.get("quantity"),
                price=arguments.get("price"),
                user_prompt=user_prompt,
                cash_amount=arguments.get("cash_amount"),
            )

        elif tool_name == "calculate_position":
            result = await execute_calculate_position(
                symbol=arguments.get("symbol", ""),
                quantity=arguments.get("quantity"),
                entry_price=arguments.get("entry_price"),
                total_cost=arguments.get("total_cost"),
                dca_budget=arguments.get("dca_budget"),
                user_id=user_id,
            )

        elif tool_name == "optimize_portfolio":
            result = await execute_optimize_portfolio(
                user_id=user_id,
                symbols=arguments.get("symbols"),
                capital=arguments.get("capital"),
                use_my_portfolio=bool(arguments.get("use_my_portfolio") or arguments.get("use_user_portfolio")),
                objective=str(arguments.get("objective") or "balanced"),
                max_weight_pct=arguments.get("max_weight_pct"),
                max_sector_pct=arguments.get("max_sector_pct"),
                min_cash_pct=arguments.get("min_cash_pct"),
                sharia_only=bool(arguments.get("sharia_only", False)),
                market=arguments.get("market"),
            )

        elif tool_name == "enable_autonomous_recommendations":
            result = {
                "status": "success",
                "autonomous_recommendations_enabled": True,
                "message": "تم تفعيل وضع التوصيات الحرة المستقلة للذكاء الاصطناعي بنجاح في الواجهة.",
            }

        elif tool_name == "disable_autonomous_recommendations":
            result = {
                "status": "success",
                "autonomous_recommendations_enabled": False,
                "message": "تم إيقاف وضع التوصيات الحرة المستقلة والعودة للوضع القياسي.",
            }

        elif tool_name == "manage_user_preferences":
            result = await execute_manage_user_preferences(
                user_id=user_id,
                operation=arguments.get("operation", "get"),
                rule=arguments.get("rule"),
                rules=arguments.get("rules"),
            )

        elif tool_name == "manage_automations":
            result = await execute_manage_automations(
                user_id=user_id,
                operation=arguments.get("operation", "list"),
                name=arguments.get("name"),
                prompt=arguments.get("prompt"),
                scheduled_times=arguments.get("scheduled_times"),
                scheduled_time=arguments.get("scheduled_time"),
                days_of_week=arguments.get("days_of_week", "trading_days"),
                automation_id=arguments.get("automation_id"),
                is_active=arguments.get("is_active"),
            )

        else:
            result = {"status": "error", "message": f"الأداة {tool_name} غير معروفة"}

        return _enrich_tool_result_identities(result, default_market=eff_default_mkt)

    except Exception as e:
        return {"status": "error", "message": f"خطأ أثناء تنفيذ الأداة {tool_name}: {str(e)}"}
    finally:
        if ctx_token is not None:
            reset_active_market_context(ctx_token)
