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
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import pytz

from api.stock_ai import _init_supabase, supabase
from api.stock_aliases import (
    ARABIC_STOCK_MAPPINGS,
    _normalize_arabic_text,
    resolve_stock_symbol,
)
from api.sharia_stocks import is_sharia_compliant

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
    "أرامكو السعودية": "2222",
    "ارامكو السعودية": "2222",
    "ARAMCO": "2222",
    "SAUDI ARAMCO": "2222",
    "الراجحي": "1120",
    "مصرف الراجحي": "1120",
    "ALRAJHI": "1120",
    "RAJHI": "1120",
    "سابك": "2010",
    "SABIC": "2010",
    "الاتصالات السعودية": "7010",
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
    "MAADEN": "1211",
    "اكوا باور": "2082",
    "أكوا باور": "2082",
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


def _normalize_market_code(market: Optional[str]) -> str:
    """Normalize arbitrary market/country label to 'TADAWUL' or 'EGX'."""
    if not market:
        return "EGX"
    raw = str(market).strip()
    if not raw:
        return "EGX"
    upper_clean = re.sub(r"[()\[\]{}._/-]+", " ", raw).strip().upper()
    ar_clean = re.sub(r"[()\[\]{}._/-]+", " ", _normalize_arabic_text(raw)).strip().upper()
    if upper_clean in _TASI_MARKET_TOKENS or ar_clean in _TASI_MARKET_TOKENS:
        return "TADAWUL"
    if any(
        tok in upper_clean
        for tok in ("TADAWUL", "TASI", "SAUDI", "KSA")
    ) or any(tok in ar_clean for tok in ("تاسي", "تداول", "السعود")):
        return "TADAWUL"
    return "EGX"


def _ui_market_label(market_code: Optional[str]) -> str:
    return "TASI" if _normalize_market_code(market_code) == "TADAWUL" else "EGX"


def _currency_for_market(market_code: Optional[str]) -> str:
    return "ر.س" if _normalize_market_code(market_code) == "TADAWUL" else "ج.م"


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
    """Route to Saudi Supabase when market is TADAWUL, else Primary EGX Supabase."""
    if _normalize_market_code(market) == "TADAWUL":
        return _get_saudi_sb()
    return _get_sb()


def _saudi_unconfigured_error(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": "error",
        "market": "TASI",
        "exchange": "TADAWUL",
        "currency": "ر.س",
        "message": "قاعدة بيانات السوق السعودي (تداول TASI) غير مهيأة أو غير متاحة حالياً.",
    }
    if extra:
        payload.update(extra)
    return payload


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
    """Fallback company-name lookup against Supabase `stocks` when static aliases miss."""
    clean_q = " ".join(str(raw_text or "").strip().split())
    if len(clean_q) < 3:
        return None
    norm_mkt = _normalize_market_code(market)
    cache_k = f"{norm_mkt}:{clean_q.lower()}"
    if cache_k in _DB_SYMBOL_CACHE:
        return _DB_SYMBOL_CACHE[cache_k]
    # Skip obvious single-token tickers (already handled as clean symbols)
    if re.fullmatch(r"[A-Za-z]{2,8}", clean_q) or _SAUDI_TICKER_RE.fullmatch(clean_q):
        return None
    found: Optional[str] = None
    try:
        sb = _get_sb_for_market(norm_mkt)
        if sb is None:
            return None
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
    except Exception:
        pass
    if len(_DB_SYMBOL_CACHE) < 300:
        _DB_SYMBOL_CACHE[cache_k] = found
    return found


def _resolve_symbol_and_market(sym: Any) -> Tuple[str, str]:
    """Resolve raw ticker or Arabic/English name to (normalized_symbol, 'EGX'|'TADAWUL')."""
    if not sym:
        return ("", "EGX")
    raw = str(sym).strip()
    if not raw:
        return ("", "EGX")
    clean = raw.upper()

    # 1. Explicit exchange suffixes take top priority
    if clean.endswith(".CA"):
        core = clean[:-3].strip()
        resolved = resolve_stock_symbol(core) or resolve_stock_symbol(raw[:-3].strip())
        if resolved:
            return (resolved, "EGX")
        resolved_db = _lookup_symbol_in_db(raw[:-3].strip(), market="EGX")
        return (resolved_db or core, "EGX")

    for s_suf in (".TADAWUL", ".SR", ".SA"):
        if clean.endswith(s_suf):
            core_raw = raw[: -len(s_suf)].strip()
            core_up = core_raw.upper()
            saudi_hit = _resolve_saudi_alias_local(core_raw) or _lookup_symbol_in_db(
                core_raw, market="TADAWUL"
            )
            return (saudi_hit or core_up, "TADAWUL")

    # 2. Direct Saudi static alias or 4-digit Tadawul numeric ticker
    saudi_hit = _resolve_saudi_alias_local(raw)
    if saudi_hit:
        return (saudi_hit, "TADAWUL")

    # 3. Direct EGX static alias
    resolved_egx = resolve_stock_symbol(clean) or resolve_stock_symbol(raw)
    if resolved_egx:
        return (resolved_egx, "EGX")

    # 4. DB company-name lookup (prioritize active market context when un-suffixed)
    active_mkt = get_active_market_context()
    if active_mkt == "TADAWUL":
        saudi_db = _lookup_symbol_in_db(raw, market="TADAWUL")
        if saudi_db:
            return (saudi_db, "TADAWUL")
        egx_db = _lookup_symbol_in_db(raw, market="EGX")
        if egx_db:
            return (egx_db, "EGX")
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
        if any(m == "TADAWUL" for m in resolved_mkts):
            return "TADAWUL"
        if resolved_mkts:
            return "EGX"
    return get_active_market_context()


def _split_symbols_by_market(symbols: Optional[List[str]]) -> Tuple[List[str], List[str]]:
    """Resolve and group symbols into (egx_symbols, tasi_symbols) preserving uniqueness."""
    egx_syms: List[str] = []
    tasi_syms: List[str] = []
    seen_egx = set()
    seen_tasi = set()
    for raw in symbols or []:
        if not raw:
            continue
        sym, mkt = _resolve_symbol_and_market(raw)
        if not sym:
            continue
        if mkt == "TADAWUL":
            if sym not in seen_tasi:
                seen_tasi.add(sym)
                tasi_syms.append(sym)
        else:
            if sym not in seen_egx:
                seen_egx.add(sym)
                egx_syms.append(sym)
    return (egx_syms[:25], tasi_syms[:25])


def _is_real_saudi_sb(sb: Any) -> bool:
    """True only when operating on the live singleton Saudi Supabase client (not a mock)."""
    return sb is not None and _SAUDI_SB_CLIENT is not None and sb is _SAUDI_SB_CLIENT


def _get_saudi_openapi_schema(sb: Any) -> Dict[str, set]:
    """Fetch and cache PostgREST OpenAPI table->columns map for live SAUDI_SUPABASE."""
    if not _is_real_saudi_sb(sb):
        return {}
    cached = _get_tool_cached("saudi_openapi_cols")
    if isinstance(cached, dict):
        return cached
    _ensure_env_loaded()
    url = (
        os.getenv("SAUDI_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_URL") or ""
    ).strip().rstrip("/")
    key = (
        os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SAUDI_SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_ANON_KEY")
        or ""
    ).strip()
    if not url or not key:
        return {}
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
            _set_tool_cached("saudi_openapi_cols", table_cols)
        return table_cols
    except Exception:
        return {}


def _get_saudi_table_columns(table_name: str, sb: Any) -> Optional[set]:
    """Return actual column set for a Saudi table if inspectable, else None."""
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


def _saudi_ti_select_and_order(sb: Any) -> Tuple[str, str]:
    """Build schema-safe SELECT projection and order column for Saudi stock_technical_indicators."""
    cols = _get_saudi_table_columns("stock_technical_indicators", sb)
    if cols:
        chosen = [c for c in _SAUDI_TI_DESIRED_COLS if c in cols]
        order_col = "date" if "date" in cols else ("updated_at" if "updated_at" in cols else "symbol")
        if chosen:
            return (",".join(chosen), order_col)
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


def _fetch_saudi_ohlcv_for_symbols(
    sb: Any, syms: List[str], limit_per_sym: int = 120
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch bounded OHLCV bars from Saudi `stock_prices` grouped newest-first by symbol."""
    if not syms or sb is None:
        return {}
    per_sym = min(220, max(45, 950 // max(len(syms), 1))) if len(syms) > 3 else min(limit_per_sym, 220)
    total_limit = min(len(syms) * per_sym, 1000)
    try:
        res = (
            sb.from_("stock_prices")
            .select("symbol,date,open,high,low,close,volume")
            .eq("exchange", "TADAWUL")
            .in_("symbol", syms)
            .order("date", desc=True)
            .limit(total_limit)
            .execute()
        )
        by_sym: Dict[str, List[Dict[str, Any]]] = {}
        for r in (res.data or []):
            s = r.get("symbol")
            if s:
                by_sym.setdefault(s, []).append(r)
        return by_sym
    except Exception:
        return {}


def _fetch_saudi_recent_dates(sb: Any, count: int = 25) -> List[str]:
    """Return latest trading dates from Saudi `market_index` (tiny 25-row read)."""
    cache_key = f"saudi_recent_dates:{count}"
    cached = _get_tool_cached(cache_key)
    if cached is not None:
        return cached
    try:
        res = (
            sb.from_("market_index")
            .select("date")
            .eq("exchange", "TADAWUL")
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


def _get_saudi_computed_market_indicators(sb: Any, lookback_days: int = 22) -> List[Dict[str, Any]]:
    """
    Compute per-stock Saudi indicators from recent OHLCV bars when
    `SAUDI_SUPABASE.stock_technical_indicators` has not been populated yet.
    Cached 5 minutes in-memory to keep DB reads minimal.
    """
    cache_key = f"saudi_computed_mkt_ti:{lookback_days}"
    cached = _get_tool_cached(cache_key)
    if cached is not None:
        return cached

    dates = _fetch_saudi_recent_dates(sb, count=lookback_days)
    if not dates:
        return []
    start_date = dates[-1]
    all_rows: List[Dict[str, Any]] = []
    try:
        if len(dates) <= 2:
            res = (
                sb.from_("stock_prices")
                .select("symbol,date,open,high,low,close,volume")
                .eq("exchange", "TADAWUL")
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
                    .eq("exchange", "TADAWUL")
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


def _fetch_saudi_names_map(sb: Any, syms: List[str]) -> Dict[str, Dict[str, str]]:
    """Fetch name / name_ar / sector for Saudi symbols cleanly."""
    if not syms or sb is None:
        return {}
    out: Dict[str, Dict[str, str]] = {}
    try:
        res = (
            sb.from_("stocks")
            .select("symbol,name,name_ar,sector")
            .eq("exchange", "TADAWUL")
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
def _sync_get_stock(symbols: List[str]) -> Dict[str, Any]:
    egx_syms, tasi_syms = _split_symbols_by_market(symbols)
    if not egx_syms and not tasi_syms:
        return {"status": "error", "message": "لم يتم تحديد رموز أسهم صالحة"}

    cache_parts = [f"EGX:{s}" for s in sorted(egx_syms)] + [f"TADAWUL:{s}" for s in sorted(tasi_syms)]
    cache_key = f"get_stock:{','.join(cache_parts)}"
    cached = _get_tool_cached(cache_key)
    if cached is not None:
        return cached

    stocks_data: List[Dict[str, Any]] = []
    errors: List[str] = []

    # ── 1. EGX symbols (Primary Supabase) ────────────────────────────────────
    if egx_syms:
        sb = _get_sb()

        levels_map: Dict[str, Dict[str, Any]] = {}
        try:
            res_prices = (
                sb.from_("stock_prices")
                .select("symbol,high,low,close,date")
                .eq("exchange", "EGX")
                .in_("symbol", egx_syms)
                .order("date", desc=True)
                .limit(min(len(egx_syms) * 30, 1000))
                .execute()
            )
            by_sym: Dict[str, List[Dict[str, Any]]] = {}
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

        for sym in egx_syms:
            stock_name_ar = None
            stock_name_en = sym
            try:
                res_stock = sb.from_("stocks").select("symbol,name,name_ar").eq("symbol", sym).limit(1).execute()
                if res_stock.data and isinstance(res_stock.data[0], dict):
                    stock_name_ar = res_stock.data[0].get("name_ar")
                    stock_name_en = res_stock.data[0].get("name") or sym
            except Exception:
                pass

            if not stock_name_ar:
                stock_name_ar = _alias_name_for_symbol(sym, market="EGX")

            if stock_name_ar:
                stock_name_ar = stock_name_ar.split(",")[0].strip()

            latest_tech: Dict[str, Any] = {}
            try:
                res_tech = (
                    sb.from_("stock_technical_indicators")
                    .select(
                        "date,close,change_pct,volume,r_vol,rsi_14,macd,macd_signal,macd_histogram,"
                        "bb_upper,bb_lower,ema_50,ema_200,vwap_20,king_ai_score,egx_ai_score"
                    )
                    .eq("exchange", "EGX")
                    .eq("symbol", sym)
                    .order("date", desc=True)
                    .limit(1)
                    .execute()
                )
                if res_tech.data:
                    latest_tech = res_tech.data[0]
            except Exception:
                pass

            wyckoff_info: Dict[str, Any] = {}
            try:
                res_wyckoff = (
                    sb.from_("stock_scans_summary")
                    .select("scan_date,acc_score,dist_score,wyckoff_phase,vol_ratio,signal,consecutive_acc_days,consecutive_dist_days")
                    .eq("symbol", sym)
                    .order("scan_date", desc=True)
                    .limit(1)
                    .execute()
                )
                if res_wyckoff.data:
                    wyckoff_info = res_wyckoff.data[0]
            except Exception:
                pass

            fundamentals: Dict[str, Any] = {}
            try:
                res_fund = (
                    sb.from_("stock_fundamentals")
                    .select("data")
                    .eq("exchange", "EGX")
                    .eq("symbol", sym)
                    .limit(1)
                    .execute()
                )
                if res_fund.data and isinstance(res_fund.data[0].get("data"), dict):
                    fd = res_fund.data[0]["data"]
                    if stock_name_en == sym and fd.get("name"):
                        stock_name_en = str(fd["name"]).split(",")[0].strip()
                    fundamentals = {
                        "pe_ratio": _safe_float(fd.get("pe_ratio") or fd.get("trailing_pe")),
                        "eps": _safe_float(fd.get("eps") or fd.get("trailing_eps")),
                        "market_cap": fd.get("market_cap"),
                    }
            except Exception:
                pass

            close_price = _safe_price(latest_tech.get("close"))
            change_pct = _safe_float(latest_tech.get("change_pct"))
            sharia = is_sharia_compliant(sym)

            king_score = _safe_float(latest_tech.get("king_ai_score"))
            acc_score = _safe_float(wyckoff_info.get("acc_score"))
            rsi = _safe_float(latest_tech.get("rsi_14"))

            bb_low = _safe_price(latest_tech.get("bb_lower"))
            bb_up = _safe_price(latest_tech.get("bb_upper"))
            lvl = levels_map.get(sym, {})
            support_1 = lvl.get("support_1") or (bb_low if bb_low else (_safe_price(close_price * 0.96) if close_price else None))
            resistance_1 = lvl.get("resistance_1") or (bb_up if bb_up else (_safe_price(close_price * 1.05) if close_price else None))
            support_2 = lvl.get("support_2") or (_safe_price(support_1 * 0.96) if support_1 else None)
            resistance_2 = lvl.get("resistance_2") or (_safe_price(resistance_1 * 1.05) if resistance_1 else None)
            stop_loss = lvl.get("stop_loss") or (_safe_price(support_1 * 0.98) if support_1 else None)
            entry_zone = lvl.get("entry_zone") or (f"{support_1} – {_safe_price(support_1 * 1.02)}" if support_1 else "غير محدد")

            if change_pct is not None and change_pct > 0 and rsi is not None and 45 <= rsi <= 68:
                verdict = "🟢 إيجابي / فرصة جيدة"
            elif (change_pct is not None and change_pct < -2) or (rsi is not None and rsi > 75):
                verdict = "🔴 سلبي / مخاطرة مرتفعة"
            else:
                verdict = "🟡 حيادي للمراقبة"

            stocks_data.append({
                "symbol": sym,
                "market": "EGX",
                "exchange": "EGX",
                "currency": "ج.م",
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
                "macd_histogram": _safe_float(latest_tech.get("macd_histogram"), 4),
                "ema_50": _safe_price(latest_tech.get("ema_50")),
                "ema_200": _safe_price(latest_tech.get("ema_200")),
                "r_vol": _safe_float(latest_tech.get("r_vol")),
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
                "accumulation_score": acc_score,
                "distribution_score": _safe_float(wyckoff_info.get("dist_score")),
                "consecutive_acc_days": wyckoff_info.get("consecutive_acc_days"),
                "verdict": verdict,
                **fundamentals,
            })

    # ── 2. Saudi TASI symbols (SAUDI_SUPABASE) ───────────────────────────────
    if tasi_syms:
        sb_sa = _get_sb_for_market("TADAWUL")
        if sb_sa is None:
            if not egx_syms:
                return _saudi_unconfigured_error()
            errors.append("بيانات السوق السعودي (تداول TASI) غير مهيأة حالياً.")
        else:
            sa_meta_map: Dict[str, Dict[str, Any]] = {}
            equity_syms = [s for s in tasi_syms if s != "TASI"]

            # Handle TASI index if explicitly asked via get_stock
            if "TASI" in tasi_syms:
                try:
                    c0 = chg_idx = m_idx_date = idx_source = None
                    res_idx = (
                        sb_sa.from_("market_index")
                        .select("date,close,ret,source")
                        .eq("exchange", "TADAWUL")
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

                    # Optionally check market_cache ('market_status_Saudi Arabia') if present
                    if c0 is None and (_get_saudi_table_columns("market_cache", sb_sa) is not None or not _is_real_saudi_sb(sb_sa)):
                        try:
                            res_mc = (
                                sb_sa.from_("market_cache")
                                .select("payload")
                                .eq("cache_key", "market_status_Saudi Arabia")
                                .limit(1)
                                .execute()
                            )
                            if res_mc.data and isinstance(res_mc.data[0].get("payload"), dict):
                                pl = res_mc.data[0]["payload"]
                                c0 = _safe_float(pl.get("tasi_close") or pl.get("close"))
                                chg_idx = _safe_float(pl.get("tasi_change_pct") or pl.get("change_pct"))
                                m_idx_date = pl.get("date") or m_idx_date
                                idx_source = pl.get("source") or "market_cache"
                        except Exception:
                            pass

                    if c0 is not None:
                        tasi_entry: Dict[str, Any] = {
                            "symbol": "TASI",
                            "market": "TASI",
                            "exchange": "TADAWUL",
                            "currency": "نقطة",
                            "name_ar": "مؤشر السوق السعودي (تاسي)",
                            "name": "Tadawul All Share Index (TASI)",
                            "is_sharia_compliant": None,
                            "sharia_index": None,
                            "date": m_idx_date,
                            "close": c0,
                            "change_pct": chg_idx,
                            "index_source": idx_source,
                            "verdict": "🟡 مؤشر السوق العام — استخدم get_market('TASI') لمزيد من التفاصيل",
                        }
                        if idx_source == "equal_weight":
                            tasi_entry["index_type"] = "equal_weight_composite"
                            tasi_entry["index_note"] = "مؤشر السوق السعودي المركب متساوي الأوزان (سنة الأساس = 1000)"
                        stocks_data.append(tasi_entry)
                except Exception:
                    pass

            if equity_syms:
                try:
                    res_st = (
                        sb_sa.from_("stocks")
                        .select("symbol,name,name_ar,sector,industry,currency")
                        .eq("exchange", "TADAWUL")
                        .in_("symbol", equity_syms)
                        .limit(len(equity_syms))
                        .execute()
                    )
                    for r in (res_st.data or []):
                        if r.get("symbol"):
                            sa_meta_map[r["symbol"]] = r
                except Exception:
                    pass

                sa_fund_map: Dict[str, Dict[str, Any]] = {}
                try:
                    res_sf = (
                        sb_sa.from_("stock_fundamentals")
                        .select("symbol,data,fund_score")
                        .eq("exchange", "TADAWUL")
                        .in_("symbol", equity_syms)
                        .limit(len(equity_syms))
                        .execute()
                    )
                    for r in (res_sf.data or []):
                        if r.get("symbol"):
                            sa_fund_map[r["symbol"]] = r
                except Exception:
                    pass

                sa_ti_map: Dict[str, Dict[str, Any]] = {}
                try:
                    ti_cols, order_col = _saudi_ti_select_and_order(sb_sa)
                    res_sti = (
                        sb_sa.from_("stock_technical_indicators")
                        .select(ti_cols)
                        .eq("exchange", "TADAWUL")
                        .in_("symbol", equity_syms)
                        .order(order_col, desc=True)
                        .limit(len(equity_syms) * 2)
                        .execute()
                    )
                    for r in (res_sti.data or []):
                        s_sym = r.get("symbol")
                        if s_sym and s_sym not in sa_ti_map:
                            sa_ti_map[s_sym] = r
                except Exception:
                    pass

                sa_ohlcv_map = _fetch_saudi_ohlcv_for_symbols(sb_sa, equity_syms)

                for sym in equity_syms:
                    meta = sa_meta_map.get(sym, {})
                    raw_fund = sa_fund_map.get(sym, {})
                    fd = raw_fund.get("data") if isinstance(raw_fund.get("data"), dict) else {}

                    stock_name_ar = meta.get("name_ar") or _alias_name_for_symbol(sym, market="TADAWUL")
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
                    bb_low = _safe_price(db_ti.get("bb_lower")) or calc_ti.get("bb_lower")
                    bb_up = _safe_price(db_ti.get("bb_upper")) or calc_ti.get("bb_upper")

                    support_1 = calc_ti.get("support_1") or (bb_low if bb_low else (_safe_price(close_price * 0.96) if close_price else None))
                    resistance_1 = calc_ti.get("resistance_1") or (bb_up if bb_up else (_safe_price(close_price * 1.05) if close_price else None))
                    support_2 = calc_ti.get("support_2") or (_safe_price(support_1 * 0.96) if support_1 else None)
                    resistance_2 = calc_ti.get("resistance_2") or (_safe_price(resistance_1 * 1.05) if resistance_1 else None)
                    stop_loss = calc_ti.get("stop_loss") or (_safe_price(support_1 * 0.98) if support_1 else None)
                    entry_zone = calc_ti.get("entry_zone") or (f"{support_1} – {_safe_price(support_1 * 1.02)}" if support_1 else "غير محدد")

                    king_score = _safe_float(db_ti.get("king_ai_score"))
                    if king_score is None:
                        king_score = calc_ti.get("king_ai_score")

                    ti_date = db_ti.get("date") or calc_ti.get("date") or (
                        str(db_ti.get("updated_at"))[:10] if db_ti.get("updated_at") else None
                    )

                    if change_pct is not None and change_pct > 0 and rsi is not None and 45 <= rsi <= 68:
                        verdict = "🟢 إيجابي / فرصة جيدة"
                    elif (change_pct is not None and change_pct < -2) or (rsi is not None and rsi > 75):
                        verdict = "🔴 سلبي / مخاطرة مرتفعة"
                    else:
                        verdict = "🟡 حيادي للمراقبة"

                    sharia_sa = fd.get("is_sharia_compliant")
                    if sharia_sa is not None:
                        sharia_sa = bool(sharia_sa)

                    stocks_data.append({
                        "symbol": sym,
                        "market": "TASI",
                        "exchange": "TADAWUL",
                        "currency": "ر.س",
                        "name_ar": stock_name_ar or stock_name_en or sym,
                        "name": stock_name_en,
                        "sector": meta.get("sector") or fd.get("sector"),
                        "is_sharia_compliant": sharia_sa,
                        "sharia_index": "TASI Sharia" if sharia_sa else None,
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
                        "r_vol": r_vol,
                        "volume": vol_val,
                        "cmf_20": _safe_float(db_ti.get("cmf_20"), 3) or calc_ti.get("cmf_20"),
                        "support_1": support_1,
                        "resistance_1": resistance_1,
                        "support_2": support_2,
                        "resistance_2": resistance_2,
                        "stop_loss": stop_loss,
                        "entry_zone": entry_zone,
                        "king_ai_score": king_score,
                        "pe_ratio": _safe_float(fd.get("pe_ratio") or fd.get("trailing_pe")),
                        "eps": _safe_float(fd.get("eps") or fd.get("trailing_eps")),
                        "market_cap": fd.get("market_cap"),
                        "fund_score": _safe_float(raw_fund.get("fund_score")),
                        "verdict": verdict,
                    })

    res: Dict[str, Any] = {"status": "success", "stocks": stocks_data}
    if errors:
        res["warnings"] = errors
    _set_tool_cached(cache_key, res)
    return res


async def execute_get_stock(symbols: List[str]) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_stock, symbols)


# ---------------------------------------------------------------------------
# Tool: get_stock_levels
# ---------------------------------------------------------------------------
def _sync_get_stock_levels_for_market(
    sb: Any, syms: List[str], exchange_code: str
) -> List[Dict[str, Any]]:
    ui_mkt = _ui_market_label(exchange_code)
    currency = _currency_for_market(exchange_code)
    levels: List[Dict[str, Any]] = []

    for sym in syms:
        try:
            res_p = (
                sb.from_("stock_prices")
                .select("high,low,close,date")
                .eq("exchange", exchange_code)
                .eq("symbol", sym)
                .order("date", desc=True)
                .limit(60)
                .execute()
            )
            rows = res_p.data or []
        except Exception:
            rows = []

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

        recent_20 = rows[:20]
        recent_lows = [float(r["low"]) for r in recent_20 if r.get("low")]
        recent_highs = [float(r["high"]) for r in recent_20 if r.get("high")]
        all_lows = [float(r["low"]) for r in rows if r.get("low")]
        all_highs = [float(r["high"]) for r in rows if r.get("high")]

        support_1 = _safe_price(min(recent_lows)) if recent_lows else None
        resistance_1 = _safe_price(max(recent_highs)) if recent_highs else None
        support_2 = _safe_price(min(all_lows)) if all_lows else (_safe_price(support_1 * 0.96) if support_1 else None)
        resistance_2 = _safe_price(max(all_highs)) if all_highs else (_safe_price(resistance_1 * 1.05) if resistance_1 else None)

        stop_loss = _safe_price(support_1 * 0.98) if support_1 else None
        entry_zone = f"{support_1} – {_safe_price(support_1 * 1.02)}" if support_1 else "غير محدد"

        has_rec = False
        rec_data = None
        try:
            res_rec = (
                sb.from_("scan_results")
                .select("signal,entry_price,target_price,stop_loss,status,created_at")
                .eq("exchange", exchange_code)
                .eq("symbol", sym)
                .in_("status", ["open", "active"])
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if res_rec.data:
                has_rec = True
                r = res_rec.data[0]
                rec_data = {
                    "signal": r.get("signal"),
                    "entry_price": _safe_price(r.get("entry_price")),
                    "target_price": _safe_price(r.get("target_price")),
                    "stop_loss": _safe_price(r.get("stop_loss")),
                    "status": r.get("status"),
                    "signal_date": str(r.get("created_at") or "")[:10],
                }
        except Exception:
            pass

        levels.append({
            "symbol": sym,
            "market": ui_mkt,
            "exchange": exchange_code,
            "currency": currency,
            "close": close,
            "date": date,
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
        })
    return levels


def _sync_get_stock_levels(symbols: List[str]) -> Dict[str, Any]:
    egx_syms, tasi_syms = _split_symbols_by_market(symbols)
    if not egx_syms and not tasi_syms:
        return {"status": "error", "message": "لم يتم تحديد رموز أسهم صالحة"}

    cache_parts = [f"EGX:{s}" for s in sorted(egx_syms)] + [f"TADAWUL:{s}" for s in sorted(tasi_syms)]
    cache_key = f"get_stock_levels:{','.join(cache_parts)}"
    cached = _get_tool_cached(cache_key)
    if cached is not None:
        return cached

    levels: List[Dict[str, Any]] = []
    if egx_syms:
        levels.extend(_sync_get_stock_levels_for_market(_get_sb(), egx_syms, "EGX"))
    if tasi_syms:
        sb_sa = _get_sb_for_market("TADAWUL")
        if sb_sa is None:
            if not egx_syms:
                return _saudi_unconfigured_error()
            for s in tasi_syms:
                levels.append({
                    "symbol": s,
                    "market": "TASI",
                    "exchange": "TADAWUL",
                    "currency": "ر.س",
                    "status": "missing",
                    "message": "قاعدة بيانات السوق السعودي غير متاحة حالياً.",
                })
        else:
            levels.extend(_sync_get_stock_levels_for_market(sb_sa, tasi_syms, "TADAWUL"))

    res = {"status": "success", "levels": levels}
    _set_tool_cached(cache_key, res)
    return res


async def execute_get_stock_levels(symbols: List[str]) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_stock_levels, symbols)


# ---------------------------------------------------------------------------
# Tool: get_market
# ---------------------------------------------------------------------------
def _sync_get_market(market: Optional[str] = None) -> Dict[str, Any]:
    eff_mkt = _resolve_effective_market(market=market)
    cache_key = f"get_market:{eff_mkt}"
    cached = _get_tool_cached(cache_key)
    if cached is not None:
        return cached

    if eff_mkt == "TADAWUL":
        sb_sa = _get_sb_for_market("TADAWUL")
        if sb_sa is None:
            return _saudi_unconfigured_error()

        sa_payload: Dict[str, Any] = {}
        if _get_saudi_table_columns("market_cache", sb_sa) is not None or not _is_real_saudi_sb(sb_sa):
            try:
                res_mc = (
                    sb_sa.from_("market_cache")
                    .select("payload")
                    .eq("cache_key", "market_status_Saudi Arabia")
                    .limit(1)
                    .execute()
                )
                if res_mc.data and isinstance(res_mc.data[0].get("payload"), dict):
                    sa_payload = res_mc.data[0]["payload"]
            except Exception:
                pass

        tasi_close = _safe_float(sa_payload.get("tasi_close") or sa_payload.get("close"))
        tasi_change_pct = _safe_float(sa_payload.get("tasi_change_pct") or sa_payload.get("change_pct"))
        m_date = sa_payload.get("date")
        idx_source = sa_payload.get("source")
        try:
            res_idx = (
                sb_sa.from_("market_index")
                .select("date,close,ret,source")
                .eq("exchange", "TADAWUL")
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
                    or _alias_name_for_symbol(sym, "TADAWUL")
                    or nm.get("name")
                    or r.get("name")
                    or sym
                ).split(",")[0].strip()
                formatted.append({
                    "symbol": sym,
                    "name": clean_nm,
                    "close": _safe_price(r.get("close")),
                    "change_pct": _safe_float(r.get("change_pct")),
                    "currency": "ر.س",
                })
            return formatted

        # Prefer stock_technical_indicators when populated (filtered to latest date & non-null change_pct)
        if not top_gainers and not top_losers:
            try:
                ti_cols_str, _ = _saudi_ti_select_and_order(sb_sa)
                ti_cols = set(ti_cols_str.split(","))
                latest_ti_date = (
                    _get_latest_table_date(sb_sa, "stock_technical_indicators", "date", "TADAWUL")
                    if "date" in ti_cols
                    else None
                )
                if latest_ti_date:
                    res_ti_all = (
                        sb_sa.from_("stock_technical_indicators")
                        .select("symbol,close,change_pct")
                        .eq("exchange", "TADAWUL")
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
                        names_map = _fetch_saudi_names_map(sb_sa, movers_syms)
                        top_gainers = _format_sa_movers(g_raw, names_map)
                        top_losers = _format_sa_movers(l_raw, names_map)
                else:
                    res_g = (
                        sb_sa.from_("stock_technical_indicators")
                        .select("symbol,close,change_pct")
                        .eq("exchange", "TADAWUL")
                        .not_.is_("change_pct", "null")
                        .order("change_pct", desc=True)
                        .limit(5)
                        .execute()
                    )
                    res_l = (
                        sb_sa.from_("stock_technical_indicators")
                        .select("symbol,close,change_pct")
                        .eq("exchange", "TADAWUL")
                        .not_.is_("change_pct", "null")
                        .order("change_pct", desc=False)
                        .limit(5)
                        .execute()
                    )
                    g_raw = [r for r in (res_g.data or []) if isinstance(r, dict) and r.get("change_pct") is not None]
                    l_raw = [r for r in (res_l.data or []) if isinstance(r, dict) and r.get("change_pct") is not None]
                    if g_raw or l_raw:
                        movers_syms = [r["symbol"] for r in (g_raw + l_raw) if r.get("symbol")]
                        names_map = _fetch_saudi_names_map(sb_sa, movers_syms)
                        top_gainers = _format_sa_movers(g_raw, names_map)
                        top_losers = _format_sa_movers(l_raw, names_map)
            except Exception:
                pass

        # Fallback cleanly to 2-day OHLCV snapshot when stock_technical_indicators is empty
        if not top_gainers and not top_losers:
            snap_rows = _get_saudi_computed_market_indicators(sb_sa, lookback_days=2)
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
            names_map = _fetch_saudi_names_map(sb_sa, movers_syms)
            top_gainers = _format_sa_movers(g_raw, names_map)
            top_losers = _format_sa_movers(l_raw, names_map)

        res: Dict[str, Any] = {
            "status": "success",
            "market": "TASI",
            "market_display": "TASI (السوق السعودي - تداول)",
            "market_code": "TADAWUL",
            "index_name": "TASI",
            "currency": "ر.س",
            "tasi_close": tasi_close,
            "tasi_change_pct": tasi_change_pct,
            "index_source": idx_source,
            "date": m_date,
            "breadth": breadth or None,
            "top_gainers": top_gainers,
            "top_losers": top_losers,
        }
        if idx_source == "equal_weight":
            res["index_type"] = "equal_weight_composite"
            res["index_note"] = "مؤشر السوق السعودي المركب متساوي الأوزان (سنة الأساس = 1000)"
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

    res = {
        "status": "success",
        "market": "EGX (البورصة المصرية)",
        "market_code": "EGX",
        "index_name": "EGX30",
        "currency": "ج.م",
        "egx30_close": egx30_close or payload.get("egx30_close"),
        "egx30_change_pct": egx30_change_pct or payload.get("egx30_change_pct"),
        "date": m_date or payload.get("date"),
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

    if eff_mkt == "TADAWUL":
        sb_sa = _get_sb_for_market("TADAWUL")
        if sb_sa is None:
            return _saudi_unconfigured_error()

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
        _, sa_syms = _split_symbols_by_market(symbols) if symbols else ([], [])

        for tbl_name in ("scan_results", "current_public_recommendations"):
            tbl_cols = _get_saudi_table_columns(tbl_name, sb_sa)
            if tbl_cols is not None:
                sel_cols = ",".join([c for c in desired_rec_cols if c in tbl_cols]) or safe_rec_fallback
                has_exchange_col = "exchange" in tbl_cols
            else:
                sel_cols = safe_rec_fallback
                has_exchange_col = True

            filter_modes = (True, False) if has_exchange_col else (False,)
            for use_exchange_filter in filter_modes:
                try:
                    q = sb_sa.from_(tbl_name).select(sel_cols)
                    if use_exchange_filter:
                        q = q.eq("exchange", "TADAWUL")
                    if status == "open":
                        q = q.in_("status", ["open", "active"])
                    elif status == "closed":
                        q = q.in_("status", ["closed", "win", "loss"])
                    if sa_syms:
                        q = q.in_("symbol", sa_syms)
                    res = q.order("created_at", desc=True).limit(min(limit or 20, 30)).execute()
                    rows = res.data or []
                    if rows:
                        break
                except Exception:
                    continue
            if rows:
                break

        rec_syms = [r.get("symbol") for r in rows if r.get("symbol")]
        names_map = _fetch_saudi_names_map(sb_sa, rec_syms)

        recs = []
        for r in rows:
            sym = r.get("symbol")
            nm = names_map.get(sym, {})
            stock_name_ar = nm.get("name_ar") or _alias_name_for_symbol(sym, market="TADAWUL")
            clean_name = (stock_name_ar or nm.get("name") or r.get("name") or sym).split(",")[0].strip()
            rec_item: Dict[str, Any] = {
                "symbol": sym,
                "market": "TASI",
                "exchange": "TADAWUL",
                "currency": "ر.س",
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
            recs.append(rec_item)

        out: Dict[str, Any] = {
            "status": "success",
            "market": ui_mkt,
            "exchange": "TADAWUL",
            "currency": currency,
            "count": len(recs),
            "filter_status": status,
            "sharia_only": sharia_only,
            "recommendations": recs,
        }
        if not recs:
            out["note"] = (
                "لا توجد توصيات منشورة حالياً في جدول توصيات السوق السعودي (TASI). "
                "يمكنك طلب فحص فني فوري عبر get_technical_scan(market='TASI') أو تحليل سهم سعودي بالرقم (مثل 2222 أو 1120)."
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
        rows = res.data or []
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
            "currency": "ج.م",
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
def _sync_get_technical_scan(
    preset: str,
    sharia_only: bool = False,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    eff_mkt = _resolve_effective_market(market=market)
    ui_mkt = _ui_market_label(eff_mkt)
    currency = _currency_for_market(eff_mkt)

    if eff_mkt == "TADAWUL":
        sb_sa = _get_sb_for_market("TADAWUL")
        if sb_sa is None:
            return _saudi_unconfigured_error()

        rows: List[Dict[str, Any]] = []
        used_computed = False
        try:
            ti_cols_str, order_col = _saudi_ti_select_and_order(sb_sa)
            ti_cols = set(ti_cols_str.split(","))
            q = (
                sb_sa.from_("stock_technical_indicators")
                .select(ti_cols_str)
                .eq("exchange", "TADAWUL")
            )
            if "date" in ti_cols:
                latest_sa_date = _get_latest_table_date(sb_sa, "stock_technical_indicators", "date", "TADAWUL")
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
        except Exception:
            rows = []

        if not rows:
            used_computed = True
            snap = _get_saudi_computed_market_indicators(
                sb_sa, lookback_days=2 if preset in ("top_gainers", "top_losers", "high_volume") else 22
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
        names_map = _fetch_saudi_names_map(sb_sa, syms_for_names)

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
            stock_name_ar = nm_meta.get("name_ar") or _alias_name_for_symbol(sym, market="TADAWUL")
            clean_name = (stock_name_ar or nm_meta.get("name") or sym).split(",")[0].strip()

            results.append({
                "symbol": sym,
                "market": "TASI",
                "exchange": "TADAWUL",
                "currency": "ر.س",
                "name": clean_name,
                "name_ar": clean_name,
                "close": close,
                "change_pct": change_pct,
                "rsi_14": rsi,
                "r_vol": r_vol,
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
            "exchange": "TADAWUL",
            "currency": currency,
            "preset": preset,
            "stocks": results,
        }
        if used_computed:
            out["data_source"] = "computed_from_ohlcv"
        if sharia_only:
            out["sharia_note"] = "تصنيف الشريعة لأسهم السوق السعودي قيد الإضافة، وتُعرض نتائج المسح الفني العامة حالياً."
        return out

    # ── EGX (preserved existing query) ───────────────────────────────────────
    sb = _get_sb()
    try:
        latest_date = _get_latest_table_date(sb, "stock_technical_indicators", "date", "EGX")
        query = sb.from_("stock_technical_indicators").select(
            "symbol,date,close,change_pct,volume,r_vol,rsi_14,macd,macd_signal,macd_histogram,"
            "bb_upper,bb_lower,ema_50,ema_200,king_ai_score,egx_ai_score"
        ).eq("exchange", "EGX")
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

        results.append({
            "symbol": sym,
            "market": "EGX",
            "exchange": "EGX",
            "currency": "ج.م",
            "name": clean_name,
            "name_ar": clean_name,
            "close": close,
            "change_pct": change_pct,
            "rsi_14": rsi,
            "r_vol": _safe_float(r.get("r_vol")),
            "macd": _safe_float(r.get("macd"), 4),
            "king_ai_score": _safe_float(r.get("king_ai_score")),
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

    return {
        "status": "success",
        "market": ui_mkt,
        "exchange": "EGX",
        "currency": currency,
        "preset": preset,
        "stocks": results,
    }


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

    if eff_mkt == "TADAWUL":
        sb_sa = _get_sb_for_market("TADAWUL")
        if sb_sa is None:
            return _saudi_unconfigured_error()

        # 1. Prefer SAUDI_SUPABASE.stock_scans_summary when available and populated
        summary_cols = _get_saudi_table_columns("stock_scans_summary", sb_sa)
        if summary_cols is not None or not _is_real_saudi_sb(sb_sa):
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
                exch_filter = "TADAWUL" if (summary_cols is None or "exchange" in summary_cols) else None
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
                        "market": "TASI",
                        "exchange": "TADAWUL",
                        "currency": "ر.س",
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
                    names_map = _fetch_saudi_names_map(sb_sa, acc_syms)
                    ti_map: Dict[str, Dict[str, Any]] = {}
                    try:
                        ti_cols_str, order_col = _saudi_ti_select_and_order(sb_sa)
                        res_ti = (
                            sb_sa.from_("stock_technical_indicators")
                            .select(ti_cols_str)
                            .eq("exchange", "TADAWUL")
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
                            or _alias_name_for_symbol(s_sym, "TADAWUL")
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
                        s["king_ai_score"] = _safe_float(ti.get("king_ai_score"))
                        s["verdict"] = verdict

                    out_sum: Dict[str, Any] = {
                        "status": "success",
                        "market": ui_mkt,
                        "exchange": "TADAWUL",
                        "currency": currency,
                        "accumulation_stocks": stocks_sum,
                        "stocks": stocks_sum,
                        "data_source": "stock_scans_summary",
                    }
                    if sharia_only:
                        out_sum["sharia_note"] = "تصنيف الشريعة لأسهم تداول قيد الإضافة؛ تم عرض أعلى أسهم التجميع المتاحة."
                    return out_sum
            except Exception:
                pass

        # 2. Fallback to computed CMF & relative volume accumulation from OHLCV bars
        snap = _get_saudi_computed_market_indicators(sb_sa, lookback_days=22)
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
        names_map = _fetch_saudi_names_map(sb_sa, [r["symbol"] for _, r in top_items])
        stocks = []
        for acc_score, r in top_items:
            sym = r["symbol"]
            nm = names_map.get(sym, {})
            clean_name = (nm.get("name_ar") or _alias_name_for_symbol(sym, "TADAWUL") or nm.get("name") or sym).split(",")[0].strip()
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
                "market": "TASI",
                "exchange": "TADAWUL",
                "currency": "ر.س",
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
                "king_ai_score": r.get("king_ai_score"),
                "verdict": verdict,
                "date": r.get("date"),
                "is_sharia_compliant": None,
            })

        return {
            "status": "success",
            "market": ui_mkt,
            "exchange": "TADAWUL",
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
            "currency": "ج.م",
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
                s["king_ai_score"] = _safe_float(ti.get("king_ai_score"))
                s["egx_ai_score"] = _safe_float(ti.get("egx_ai_score"))
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

    if eff_mkt == "TADAWUL":
        sb_sa = _get_sb_for_market("TADAWUL")
        if sb_sa is None:
            return _saudi_unconfigured_error()
        # Check whether news/disclosures tables exist on SAUDI_SUPABASE before querying
        cols_news = _get_saudi_table_columns("market_news", sb_sa) or _get_saudi_table_columns("stock_news_sentiment", sb_sa)
        news_items: List[Dict[str, Any]] = []
        if cols_news is not None:
            try:
                tbl = "market_news" if _get_saudi_table_columns("market_news", sb_sa) else "stock_news_sentiment"
                q = sb_sa.from_(tbl).select("*").limit(10)
                if symbols:
                    _, sa_syms = _split_symbols_by_market(symbols)
                    if sa_syms:
                        q = q.in_("symbol", sa_syms)
                res = q.execute()
                news_items = res.data or []
            except Exception:
                news_items = []
        out: Dict[str, Any] = {
            "status": "success",
            "market": ui_mkt,
            "exchange": "TADAWUL",
            "currency": currency,
            "count": len(news_items),
            "news": news_items,
        }
        if not news_items:
            out["note"] = (
                "أخبار وإفصاحات السوق السعودي (تداول TASI) غير مخزنة حالياً في قاعدة البيانات. "
                "يمكن للمستخدم متابعة الإفصاحات الرسمية على saudiexchange.sa بينما نواصل تغطية التحليل الفني والأسعار للسوق السعودي."
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
    egx_syms, tasi_syms = _split_symbols_by_market(symbols)
    clean_syms = egx_syms + tasi_syms
    if not clean_syms:
        return {"status": "error", "message": "لم يتم تحديد رموز أسهم صالحة للمقارنة"}

    stock_res = _sync_get_stock(symbols)
    levels_res = _sync_get_stock_levels(symbols)
    levels_map = {}
    for item in levels_res.get("levels", []):
        if isinstance(item, dict) and item.get("symbol"):
            levels_map[(item["symbol"], item.get("market"))] = item

    stocks = stock_res.get("stocks", [])
    for s in stocks:
        key = (s.get("symbol"), s.get("market"))
        lvl = levels_map.get(key) or {}
        if not lvl:
            # fallback lookup by symbol alone
            for k, v in levels_map.items():
                if k[0] == s.get("symbol"):
                    lvl = v
                    break
        if lvl.get("support_1") is not None:
            s["support_1"] = lvl.get("support_1")
        if lvl.get("resistance_1") is not None:
            s["resistance_1"] = lvl.get("resistance_1")
        if lvl.get("support_2") is not None:
            s["support_2"] = lvl.get("support_2")
        if lvl.get("resistance_2") is not None:
            s["resistance_2"] = lvl.get("resistance_2")

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

    if eff_mkt == "TADAWUL":
        sb_sa = _get_sb_for_market("TADAWUL")
        if sb_sa is None:
            return _saudi_unconfigured_error()

        rows: List[Dict[str, Any]] = []
        _, sa_syms = _split_symbols_by_market(symbols)
        try:
            ti_cols_str, order_col = _saudi_ti_select_and_order(sb_sa)
            ti_cols = set(ti_cols_str.split(","))
            q = (
                sb_sa.from_("stock_technical_indicators")
                .select(ti_cols_str)
                .eq("exchange", "TADAWUL")
            )
            if sa_syms:
                q = q.in_("symbol", sa_syms)
            elif "date" in ti_cols:
                ld = _get_latest_table_date(sb_sa, "stock_technical_indicators", "date", "TADAWUL")
                if ld:
                    q = q.eq("date", ld)
            res = q.order(order_col, desc=True).limit(50).execute()
            rows = res.data or []
        except Exception:
            rows = []

        if not rows:
            if sa_syms:
                ohlcv_map = _fetch_saudi_ohlcv_for_symbols(sb_sa, sa_syms, limit_per_sym=60)
                for s_sym in sa_syms:
                    calc = _compute_indicators_from_price_rows(ohlcv_map.get(s_sym, []))
                    if calc:
                        calc["symbol"] = s_sym
                        rows.append(calc)
            else:
                rows = _get_saudi_computed_market_indicators(sb_sa, lookback_days=22)

        names_map = _fetch_saudi_names_map(sb_sa, [r.get("symbol") for r in rows[:40] if r.get("symbol")])
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
            fair_value = _safe_price((vwap * 0.6) + (ema * 0.4))
            upside = round(((fair_value - close) / close) * 100, 2)
            nm = names_map.get(sym, {})
            clean_name = (nm.get("name_ar") or _alias_name_for_symbol(sym, "TADAWUL") or nm.get("name") or sym).split(",")[0].strip()

            items.append({
                "symbol": sym,
                "name": clean_name,
                "market": "TASI",
                "exchange": "TADAWUL",
                "currency": "ر.س",
                "current_price": close,
                "fair_value": fair_value,
                "upside_pct": upside,
                "status": "undervalued" if upside > 5 else ("overvalued" if upside < -5 else "fair"),
                "status_ar": "أقل من السعر العادل (رخيص) 🟢" if upside > 5 else ("أعلى من السعر العادل (متضخم) 🔴" if upside < -5 else "في النطاق العادل ⚖️"),
                "model": "التوازن الكمي (VWAP & EMA)",
                "is_sharia_compliant": None,
            })

        if mode == "screen_undervalued":
            items.sort(key=lambda x: x["upside_pct"], reverse=True)
        elif mode == "screen_overvalued":
            items.sort(key=lambda x: x["upside_pct"], reverse=False)

        out: Dict[str, Any] = {
            "status": "success",
            "market": ui_mkt,
            "exchange": "TADAWUL",
            "currency": currency,
            "fair_value_stocks": items[:limit],
        }
        if sharia_only:
            out["sharia_note"] = "تصنيف الشريعة لأسهم تداول قيد الإضافة؛ تم حساب السعر العادل لجميع الأسهم المتاحة."
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
        query = query.order("date", desc=True).limit(50)
        if symbols:
            clean_syms = [_normalize_symbol(s) for s in symbols if s][:25]
            query = query.in_("symbol", clean_syms)
        res = query.execute()
        rows = res.data or []
    except Exception as e:
        return {"status": "error", "message": f"تعذر حساب السعر العادل: {str(e)}"}

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
        fair_value = _safe_price((vwap * 0.6) + (ema * 0.4))
        upside = round(((fair_value - close) / close) * 100, 2)

        items.append({
            "symbol": sym,
            "market": "EGX",
            "exchange": "EGX",
            "currency": "ج.م",
            "current_price": close,
            "fair_value": fair_value,
            "upside_pct": upside,
            "status": "undervalued" if upside > 5 else ("overvalued" if upside < -5 else "fair"),
            "status_ar": "أقل من السعر العادل (رخيص) 🟢" if upside > 5 else ("أعلى من السعر العادل (متضخم) 🔴" if upside < -5 else "في النطاق العادل ⚖️"),
            "model": "التوازن الكمي (VWAP & EMA)",
            "is_sharia_compliant": is_sharia_compliant(sym),
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
# Tool: get_sharia_cleanser
# ---------------------------------------------------------------------------
def _sync_get_sharia_cleanser(
    symbol: str,
    shares_count: float = 1000.0,
    coupon_per_share: Optional[float] = None,
    purification_rate_pct: Optional[float] = None,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    clean_sym, sym_mkt = _resolve_symbol_and_market(symbol)
    eff_mkt = _normalize_market_code(market) if market else sym_mkt
    rate = purification_rate_pct or 1.5
    coupon = coupon_per_share or 1.0
    total_coupon = shares_count * coupon
    purification_amount = round(total_coupon * (rate / 100.0), 2)
    zakat_amount = round(total_coupon * 0.025, 2)

    if eff_mkt == "TADAWUL":
        sb_sa = _get_sb_for_market("TADAWUL")
        sharia_sa: Optional[bool] = None
        if sb_sa is not None and clean_sym:
            try:
                res_sf = (
                    sb_sa.from_("stock_fundamentals")
                    .select("data")
                    .eq("exchange", "TADAWUL")
                    .eq("symbol", clean_sym)
                    .limit(1)
                    .execute()
                )
                if res_sf.data and isinstance(res_sf.data[0].get("data"), dict):
                    val = res_sf.data[0]["data"].get("is_sharia_compliant")
                    if val is not None:
                        sharia_sa = bool(val)
            except Exception:
                pass
        if sharia_sa is True:
            verdict_ar = "السهم مصنف كمتوافق مع الضوابط الشرعية في السوق السعودي"
            idx_lbl = "TASI Shariah"
        elif sharia_sa is False:
            verdict_ar = "السهم غير مصنف ضمن قائمة الأسهم الشرعية المعتمدة"
            idx_lbl = "غير متوافق"
        else:
            verdict_ar = "تصنيف الشريعة الرسمي للسهم في تداول غير متوفر حالياً في القاعدة؛ تم حساب التطهير والزكاة الاسترشادية بالريال السعودي"
            idx_lbl = "قيد المراجعة الشرعية (TASI)"

        return {
            "status": "success",
            "market": "TASI",
            "exchange": "TADAWUL",
            "currency": "ر.س",
            "symbol": clean_sym,
            "is_sharia_compliant": sharia_sa,
            "sharia_index": idx_lbl,
            "shares_count": shares_count,
            "coupon_per_share": coupon,
            "total_dividends": total_coupon,
            "purification_rate_pct": rate,
            "purification_amount": purification_amount,
            "purification_amount_sar": purification_amount,
            "zakat_amount": zakat_amount,
            "zakat_amount_sar": zakat_amount,
            "verdict_ar": verdict_ar,
        }

    sharia = is_sharia_compliant(clean_sym)
    return {
        "status": "success",
        "market": "EGX",
        "exchange": "EGX",
        "currency": "ج.م",
        "symbol": clean_sym,
        "is_sharia_compliant": sharia,
        "sharia_index": "EGX33 Shariah" if sharia else "غير مدرج بمؤشر الشريعة",
        "shares_count": shares_count,
        "coupon_per_share": coupon,
        "total_dividends": total_coupon,
        "purification_rate_pct": rate,
        "purification_amount": purification_amount,
        "purification_amount_egp": purification_amount,
        "zakat_amount": zakat_amount,
        "zakat_amount_egp": zakat_amount,
        "verdict_ar": "السهم متوافق مع معايير الشريعة الإسلامية ومؤشر EGX33" if sharia else "السهم غير مصنف ضمن أسهم الشريعة المعتمدة EGX33",
    }


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
) -> Dict[str, Any]:
    clean_sym, sym_mkt = _resolve_symbol_and_market(symbol)
    ui_mkt = _ui_market_label(sym_mkt)
    currency = _currency_for_market(sym_mkt)

    close = 1.0
    if sym_mkt == "TADAWUL":
        sb_sa = _get_sb_for_market("TADAWUL")
        if sb_sa is None:
            return _saudi_unconfigured_error({"symbol": clean_sym})
        try:
            _, order_col = _saudi_ti_select_and_order(sb_sa)
            res = (
                sb_sa.from_("stock_technical_indicators")
                .select(f"close,{order_col}")
                .eq("exchange", "TADAWUL")
                .eq("symbol", clean_sym)
                .order(order_col, desc=True)
                .limit(1)
                .execute()
            )
            if res.data and res.data[0].get("close"):
                close = _safe_float(res.data[0].get("close")) or 1.0
            else:
                res_p = (
                    sb_sa.from_("stock_prices")
                    .select("close,date")
                    .eq("exchange", "TADAWUL")
                    .eq("symbol", clean_sym)
                    .order("date", desc=True)
                    .limit(1)
                    .execute()
                )
                if res_p.data and res_p.data[0].get("close"):
                    close = _safe_float(res_p.data[0].get("close")) or 1.0
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
            if res.data:
                close = _safe_float(res.data[0].get("close")) or 1.0
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
    if sym_mkt == "TADAWUL":
        out["profit_loss_sar"] = profit_loss
    else:
        out["profit_loss_egp"] = profit_loss
    return out


async def execute_calculate_position(
    symbol: str,
    quantity: Optional[float] = None,
    entry_price: Optional[float] = None,
    total_cost: Optional[float] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_calculate_position, symbol, quantity, entry_price, total_cost)


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

    if eff_mkt == "TADAWUL":
        sb_sa = _get_sb_for_market("TADAWUL")
        if sb_sa is None:
            return _saudi_unconfigured_error()

        bars_by_sym: Dict[str, List[Dict[str, Any]]] = {}
        indicators: List[Dict[str, Any]] = []
        if clean_sym:
            ohlcv = _fetch_saudi_ohlcv_for_symbols(sb_sa, [clean_sym], limit_per_sym=60)
            bars = ohlcv.get(clean_sym, [])
            bars_by_sym[clean_sym] = sorted(bars, key=lambda r: str(r.get("date") or ""))
            calc = _compute_indicators_from_price_rows(bars)
            if calc:
                calc["symbol"] = clean_sym
                indicators.append(calc)
        else:
            # Top active Saudi stocks from 5-day OHLCV window for trap detection
            dates = _fetch_saudi_recent_dates(sb_sa, count=5)
            if dates:
                try:
                    page_rows: List[Dict[str, Any]] = []
                    start_d = dates[-1]
                    for pg in range(2):
                        res_p = (
                            sb_sa.from_("stock_prices")
                            .select("symbol,date,open,high,low,close,volume")
                            .eq("exchange", "TADAWUL")
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

        detected = detect_daily_traps(indicators, bars_by_sym, max_per_side=min(limit or 8, 15))
        return {
            "status": "success",
            "market": ui_mkt,
            "exchange": "TADAWUL",
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
        if not clean_sym or bear_list or bull_list:
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

    detected = detect_daily_traps(indicators, bars_by_sym, max_per_side=min(limit or 8, 15))
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

    if eff_mkt == "TADAWUL":
        sb_sa = _get_sb_for_market("TADAWUL")
        if sb_sa is None:
            return _saudi_unconfigured_error()
        # Only query if disclosure table exists in SAUDI_SUPABASE OpenAPI schema
        disc_tbl = None
        for cand in ("disclosures", "tasi_disclosures", "egx_disclosures"):
            if _get_saudi_table_columns(cand, sb_sa) is not None:
                disc_tbl = cand
                break
        items: List[Dict[str, Any]] = []
        if disc_tbl:
            try:
                q = sb_sa.from_(disc_tbl).select("symbol,title,ai_summary,sentiment,disclosure_type,disclosure_date,source_url").limit(min(limit or 10, 20))
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
            "exchange": "TADAWUL",
            "currency": currency,
            "count": len(items),
            "disclosures": items,
        }
        if not items:
            out["note"] = (
                "إفصاحات السوق السعودي (تداول) غير متوفرة حالياً في قاعدة البيانات؛ "
                "يمكنك متابعة إعلانات الشركات مباشرة عبر saudiexchange.sa، وسأساعدك في التحليل الفني والأساسي لأي سهم سعودي فوراً."
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


# ---------------------------------------------------------------------------
# Tool: manage_portfolio (with prompt-injection safeguard)
# ---------------------------------------------------------------------------
def _sync_manage_portfolio(
    user_id: Optional[str],
    operation: str,
    symbol: Optional[str] = None,
    quantity: Optional[float] = None,
    price: Optional[float] = None,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """
    Secure portfolio management backed by Supabase `positions` table and `profiles.cash_balance`.
    Requires verified user_id.
    Enforces anti-injection: write operations (add/update/remove/sell) require explicit
    confirmation words in user_prompt to prevent autonomous hallucinated mutations.
    Supports both EGX and Saudi TADAWUL holdings in unified user portfolio.
    """
    if not user_id:
        return {
            "status": "error",
            "message": "يلزم تسجيل الدخول لعرض أو تعديل المحفظة الاستثمارية.",
            "requires_login": True,
        }

    sb = _get_sb()
    op = (operation or "view").lower().strip()

    if op in ("view", "get"):
        try:
            # 1. Fetch open positions from `positions` table
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

            # Filter real holdings (quantity > 0)
            holdings = [
                p for p in raw_positions
                if p.get("quantity") is not None and _safe_float(p.get("quantity")) is not None and _safe_float(p.get("quantity")) > 0
            ]

            # 2. Fetch cash balance from `profiles`
            cash = 0.0
            try:
                prof_res = sb.from_("profiles").select("cash_balance").eq("id", user_id).limit(1).execute()
                if prof_res.data:
                    cash = _safe_float(prof_res.data[0].get("cash_balance")) or 0.0
            except Exception:
                cash = 0.0

            if not holdings:
                return {
                    "status": "success",
                    "operation": "view",
                    "message": "محفظتك فاضية حالياً. تقدر تضيف أسهمك هنا بالكتابة أو برفع سكرين شوت لمحفظتك وهحللها فوراً.",
                    "positions_count": 0,
                    "positions": [],
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

            # 3. Group holdings by market and enrich with latest quotes from the right DB
            symbols = list({str(p.get("symbol", "")).upper() for p in holdings if p.get("symbol")})
            sym_market_map: Dict[str, str] = {}
            egx_syms: List[str] = []
            sa_syms: List[str] = []
            for s in symbols:
                norm_s, mkt = _resolve_symbol_and_market(s)
                sym_market_map[s] = mkt
                if mkt == "TADAWUL":
                    sa_syms.append(norm_s)
                else:
                    egx_syms.append(s)

            price_map: Dict[str, Optional[float]] = {}
            change_map: Dict[str, Optional[float]] = {}

            if egx_syms:
                try:
                    tech_res = (
                        sb.from_("stock_technical_indicators")
                        .select("symbol, close, change_pct, date")
                        .in_("symbol", egx_syms)
                        .order("date", desc=True)
                        .limit(max(len(egx_syms) * 5, 30))
                        .execute()
                    )
                    for row in tech_res.data or []:
                        s = str(row.get("symbol", "")).upper()
                        if s and s not in price_map:
                            price_map[s] = _safe_price(row.get("close"))
                            change_map[s] = _safe_float(row.get("change_pct"))
                except Exception:
                    pass

                missing_egx = [s for s in egx_syms if s not in price_map]
                if missing_egx:
                    try:
                        sp_res = (
                            sb.from_("stock_prices")
                            .select("symbol, close, change_pct, date")
                            .in_("symbol", missing_egx)
                            .order("date", desc=True)
                            .limit(max(len(missing_egx) * 5, 30))
                            .execute()
                        )
                        for row in sp_res.data or []:
                            s = str(row.get("symbol", "")).upper()
                            if s and s not in price_map:
                                price_map[s] = _safe_price(row.get("close"))
                                change_map[s] = _safe_float(row.get("change_pct"))
                    except Exception:
                        pass

            if sa_syms:
                sb_sa = _get_sb_for_market("TADAWUL")
                if sb_sa is not None:
                    sa_ohlcv = _fetch_saudi_ohlcv_for_symbols(sb_sa, sa_syms, limit_per_sym=5)
                    for s_norm, bars in sa_ohlcv.items():
                        if bars:
                            c0 = _safe_price(bars[0].get("close"))
                            price_map[s_norm] = c0
                            if len(bars) >= 2:
                                c1 = _safe_price(bars[1].get("close"))
                                if c1 and c0:
                                    change_map[s_norm] = _safe_float(((c0 - c1) / c1) * 100.0)

            enriched = []
            for p in holdings:
                s = str(p.get("symbol", "")).upper()
                norm_s, mkt = _resolve_symbol_and_market(s)
                curr = _currency_for_market(mkt)
                qty = _safe_float(p.get("quantity"), 4)
                entry = _safe_price(p.get("entry_price"))
                last_price = price_map.get(s) if s in price_map else price_map.get(norm_s)
                change_pct = change_map.get(s) if s in change_map else change_map.get(norm_s)

                valid_entry = entry is not None and entry > 0
                cost_basis = (qty * entry) if (qty is not None and valid_entry) else None
                market_value = (qty * last_price) if (qty is not None and last_price is not None) else None
                profit_value = (market_value - cost_basis) if (cost_basis is not None and market_value is not None) else None
                profit_pct = ((profit_value / cost_basis) * 100) if (cost_basis and cost_basis > 0 and profit_value is not None) else None

                enriched.append({
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
                    "added_at": p.get("added_at"),
                })

            has_unknown_cost = any(p["cost_basis"] is None for p in enriched)
            total_cost = None if has_unknown_cost else sum(p["cost_basis"] or 0 for p in enriched)
            has_unknown_val = any(p["market_value"] is None for p in enriched)
            total_value = None if has_unknown_val else sum(p["market_value"] or 0 for p in enriched)
            total_profit = (total_value - total_cost) if (total_cost is not None and total_value is not None) else None
            total_profit_pct = ((total_profit / total_cost) * 100) if (total_cost and total_cost > 0 and total_profit is not None) else None
            equity = (total_value + cash) if total_value is not None else cash

            # Per-market sub-totals when Saudi positions are present
            totals_by_market: Dict[str, Dict[str, Any]] = {}
            if sa_syms:
                for m_lbl, curr_lbl in (("EGX", "ج.م"), ("TASI", "ر.س")):
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

            res_payload: Dict[str, Any] = {
                "status": "success",
                "operation": "view",
                "message": f"محفظتك تحتوي على {len(enriched)} سهم.",
                "positions_count": len(enriched),
                "positions": enriched,
                "cash_balance": round(cash, 2),
                "totals": {
                    "positions_count": len(enriched),
                    "cost_basis": round(total_cost, 2) if total_cost is not None else None,
                    "market_value": round(total_value, 2) if total_value is not None else None,
                    "profit_value": round(total_profit, 2) if total_profit is not None else None,
                    "profit_pct": round(total_profit_pct, 2) if total_profit_pct is not None else None,
                    "equity": round(equity, 2),
                },
            }
            if totals_by_market:
                res_payload["totals_by_market"] = totals_by_market
            return res_payload
        except Exception as e:
            return {"status": "error", "message": f"تعذر استرجاع المحفظة: {str(e)}"}

    # Write operations require explicit intent in user's prompt (anti-injection guard)
    norm_prompt = _normalize_arabic_text(user_prompt).lower()
    write_intent_patterns = (
        r"(?:احفظ|سجل|اشتريت|شريت|ضف|اضف|اضيف|ضيف|ضيفه|ضيفهم|ضيفلي|"
        r"حط|حطه|دخل|شيل|بيع|بعت|احذف|امسح|الغي|نقص|زود|تزود|"
        r"عدل|عدلي|غير|حدث|موافق|تمام|اكد|تاكيد|نفذ|اضافه|تعديل|"
        r"(?:^|[^\w\u0621-\u064a])شراء(?:$|[^\w\u0621-\u064a]))"
    )
    if not re.search(write_intent_patterns, norm_prompt):
        return {
            "status": "blocked",
            "message": "لم يتم تأكيد طلب تعديل المحفظة من رسالة المستخدم صراحةً.",
        }

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
                stock_name = clean_sym
                try:
                    sb_lookup = _get_sb_for_market(sym_mkt)
                    if sb_lookup is not None:
                        s_res = sb_lookup.from_("stocks").select("name_ar, name").eq("symbol", clean_sym).limit(1).execute()
                        if s_res.data and isinstance(s_res.data[0], dict):
                            stock_name = s_res.data[0].get("name_ar") or s_res.data[0].get("name") or clean_sym
                except Exception:
                    pass
                if stock_name == clean_sym:
                    stock_name = _alias_name_for_symbol(clean_sym, sym_mkt) or clean_sym
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
            }

        elif op in ("sell",):
            if not existing:
                return {"status": "error", "message": f"سهم {clean_sym} غير موجود في محفظتك المفتوحة."}
            held = _safe_float(existing.get("quantity")) or 0.0
            sell_qty = _safe_float(quantity) if quantity is not None else held
            if sell_qty <= 0:
                return {"status": "error", "message": "كمية البيع يجب أن تكون أكبر من الصفر."}
            if sell_qty >= held:
                update_data: Dict[str, Any] = {"status": "closed"}
                if price is not None:
                    update_data["status_price"] = price
                sb.from_("positions").update(update_data).eq("id", existing["id"]).execute()
                msg = f"تم تسجيل بيع كامل رصيد سهم {clean_sym} ({held} سهم)."
            else:
                rem = held - sell_qty
                sb.from_("positions").update({"quantity": rem}).eq("id", existing["id"]).execute()
                msg = f"تم تسجيل بيع {sell_qty} سهم من {clean_sym}، والمتبقي {rem} سهم."

            # Update cash if price provided
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
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_manage_portfolio, user_id, operation, symbol, quantity, price, user_prompt)


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
    }
}


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

    ctx_token = set_active_market_context(default_market) if default_market else None
    try:
        if tool_name == "get_stock":
            symbols = arguments.get("symbols") or ([arguments["symbol"]] if "symbol" in arguments else [])
            return await execute_get_stock(symbols)

        elif tool_name == "get_stock_levels":
            symbols = arguments.get("symbols") or ([arguments["symbol"]] if "symbol" in arguments else [])
            return await execute_get_stock_levels(symbols)

        elif tool_name == "get_market":
            return await execute_get_market(market=arguments.get("market"))

        elif tool_name == "get_recommendations":
            return await execute_get_recommendations(
                status=arguments.get("status", "open"),
                timeframe=arguments.get("timeframe", "all"),
                symbols=arguments.get("symbols"),
                sharia_only=arguments.get("sharia_only", False),
                limit=arguments.get("limit", 20),
                market=arguments.get("market"),
            )

        elif tool_name == "get_technical_scan":
            return await execute_get_technical_scan(
                preset=arguments.get("preset", "top_gainers"),
                sharia_only=arguments.get("sharia_only", False),
                market=arguments.get("market"),
            )

        elif tool_name == "get_accumulation_stocks":
            return await execute_get_accumulation_stocks(
                sharia_only=arguments.get("sharia_only", False),
                market=arguments.get("market"),
            )

        elif tool_name == "get_news":
            return await execute_get_news(
                symbols=arguments.get("symbols"),
                market=arguments.get("market"),
            )

        elif tool_name == "get_comparison":
            return await execute_get_comparison(symbols=arguments.get("symbols", []))

        elif tool_name == "get_fair_value":
            return await execute_get_fair_value(
                symbols=arguments.get("symbols"),
                mode=arguments.get("mode", "screen_undervalued"),
                sharia_only=arguments.get("sharia_only", False),
                limit=arguments.get("limit", 10),
                market=arguments.get("market"),
            )

        elif tool_name == "get_sharia_cleanser":
            return await execute_get_sharia_cleanser(
                symbol=arguments.get("symbol", ""),
                shares_count=arguments.get("shares_count", 1000.0),
                coupon_per_share=arguments.get("coupon_per_share"),
                purification_rate_pct=arguments.get("purification_rate_pct"),
                market=arguments.get("market"),
            )

        elif tool_name == "get_price_traps":
            return await execute_get_price_traps(
                market=arguments.get("market"),
                symbol=arguments.get("symbol"),
                limit=arguments.get("limit", 8),
            )

        elif tool_name == "get_disclosures":
            return await execute_get_disclosures(
                symbol=arguments.get("symbol"),
                disclosure_type=arguments.get("disclosure_type"),
                limit=arguments.get("limit", 10),
                market=arguments.get("market"),
            )

        elif tool_name == "manage_portfolio":
            return await execute_manage_portfolio(
                user_id=user_id,
                operation=arguments.get("operation", "view"),
                symbol=arguments.get("symbol"),
                quantity=arguments.get("quantity"),
                price=arguments.get("price"),
                user_prompt=user_prompt,
            )

        elif tool_name == "calculate_position":
            return await execute_calculate_position(
                symbol=arguments.get("symbol", ""),
                quantity=arguments.get("quantity"),
                entry_price=arguments.get("entry_price"),
                total_cost=arguments.get("total_cost"),
            )

        elif tool_name == "enable_autonomous_recommendations":
            return {
                "status": "success",
                "autonomous_recommendations_enabled": True,
                "message": "تم تفعيل وضع التوصيات الحرة المستقلة للذكاء الاصطناعي بنجاح في الواجهة.",
            }

        elif tool_name == "disable_autonomous_recommendations":
            return {
                "status": "success",
                "autonomous_recommendations_enabled": False,
                "message": "تم إيقاف وضع التوصيات الحرة المستقلة والعودة للوضع القياسي.",
            }

        else:
            return {"status": "error", "message": f"الأداة {tool_name} غير معروفة"}

    except Exception as e:
        return {"status": "error", "message": f"خطأ أثناء تنفيذ الأداة {tool_name}: {str(e)}"}
    finally:
        if ctx_token is not None:
            reset_active_market_context(ctx_token)
