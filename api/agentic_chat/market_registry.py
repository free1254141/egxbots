"""
api/agentic_chat/market_registry.py
Unified, data-driven Multi-Market Registry for ARTORO Agentic Chat.

Allows EGX, Saudi TASI (TADAWUL), Qatar (QSE), Dubai (DFM), Abu Dhabi (ADX),
Kuwait (KSE), and any future exchange added to Supabase to share the exact same
pipeline, tools, VIP cache, Fast-Track, and portfolio pricing code paths.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MarketConfig:
    exchange: str                  # DB `exchange` column value (e.g. "EGX", "TADAWUL", "QSE", "DFM", "ADX")
    ui_code: str                   # Short UI/cache label (e.g. "EGX", "TASI", "QSE", "DFM", "ADX")
    name_ar: str                   # Arabic market display name
    name_en: str                   # English market display name
    index_name: str                # Primary benchmark index (e.g. "EGX30", "TASI", "QSI", "DFMGI", "FADGI")
    currency_ar: str               # Arabic currency symbol ("ج.م", "ر.س", "ر.ق", "د.إ", "د.ك")
    currency_code: str             # ISO currency code ("EGP", "SAR", "QAR", "AED", "KWD")
    timezone_name: str             # IANA timezone ("Africa/Cairo", "Asia/Riyadh", "Asia/Qatar", "Asia/Dubai")
    utc_offset_hours: int          # Fallback UTC offset if ZoneInfo fails
    trading_weekdays: Tuple[int, ...] = (6, 0, 1, 2, 3)  # Sun-Thu by default (GCC & EGX)
    session_open_min: int = 10 * 60
    session_close_min: int = 14 * 60 + 30
    data_ready_min: int = 17 * 60 + 15
    sharia_index: str = "Sharia"
    market_cache_key: str = ""
    official_site: str = ""
    supabase_env_prefix: Optional[str] = None  # e.g. "SAUDI" -> SAUDI_SUPABASE_URL; None -> Primary Supabase
    ticker_suffixes: Tuple[str, ...] = ()
    aliases: Tuple[str, ...] = ()


BUILTIN_MARKETS: Dict[str, MarketConfig] = {
    "EGX": MarketConfig(
        exchange="EGX",
        ui_code="EGX",
        name_ar="البورصة المصرية",
        name_en="Egyptian Exchange",
        index_name="EGX30",
        currency_ar="ج.م",
        currency_code="EGP",
        timezone_name="Africa/Cairo",
        utc_offset_hours=2,
        trading_weekdays=(6, 0, 1, 2, 3),
        session_open_min=10 * 60,
        session_close_min=14 * 60 + 30,
        data_ready_min=17 * 60 + 15,
        sharia_index="EGX33",
        market_cache_key="market_status_Egypt",
        official_site="egx.com.eg",
        supabase_env_prefix=None,
        ticker_suffixes=(".CA", ".EGX"),
        aliases=("EGX", "EGYPT", "EGY", "CAIRO", "EGP", "مصر", "المصرية", "المصري", "القاهرة"),
    ),
    "TADAWUL": MarketConfig(
        exchange="TADAWUL",
        ui_code="TASI",
        name_ar="السوق السعودي (تداول)",
        name_en="Saudi Exchange (Tadawul)",
        index_name="TASI",
        currency_ar="ر.س",
        currency_code="SAR",
        timezone_name="Asia/Riyadh",
        utc_offset_hours=3,
        trading_weekdays=(6, 0, 1, 2, 3),
        session_open_min=10 * 60,
        session_close_min=15 * 60,
        data_ready_min=17 * 60,
        sharia_index="TASI Sharia",
        market_cache_key="market_status_Saudi Arabia",
        official_site="saudiexchange.sa",
        supabase_env_prefix="SAUDI",
        ticker_suffixes=(".SR", ".SA", ".TADAWUL"),
        aliases=("TADAWUL", "TASI", "SAUDI", "KSA", "SA", "SR", "SAR", "السعودي", "السعودية", "تاسي", "تداول", "الرياض"),
    ),
    "QSE": MarketConfig(
        exchange="QSE",
        ui_code="QSE",
        name_ar="بورصة قطر",
        name_en="Qatar Stock Exchange",
        index_name="QSI",
        currency_ar="ر.ق",
        currency_code="QAR",
        timezone_name="Asia/Qatar",
        utc_offset_hours=3,
        trading_weekdays=(6, 0, 1, 2, 3),
        session_open_min=9 * 60 + 30,
        session_close_min=13 * 60 + 15,
        data_ready_min=15 * 60 + 30,
        sharia_index="Al Rayan Islamic",
        market_cache_key="market_status_Qatar",
        official_site="qe.com.qa",
        supabase_env_prefix="SAUDI",
        ticker_suffixes=(".QA", ".QE", ".QSE"),
        aliases=("QSE", "QE", "QSI", "QATAR", "QAR", "قطر", "القطرية", "القطري", "الدوحة"),
    ),
    "DFM": MarketConfig(
        exchange="DFM",
        ui_code="DFM",
        name_ar="سوق دبي المالي",
        name_en="Dubai Financial Market",
        index_name="DFMGI",
        currency_ar="د.إ",
        currency_code="AED",
        timezone_name="Asia/Dubai",
        utc_offset_hours=4,
        trading_weekdays=(0, 1, 2, 3, 4),  # Mon-Fri in UAE
        session_open_min=10 * 60,
        session_close_min=15 * 60,
        data_ready_min=17 * 60,
        sharia_index="DFM Sharia",
        market_cache_key="market_status_DFM",
        official_site="dfm.ae",
        supabase_env_prefix="SAUDI",
        ticker_suffixes=(".DU", ".DFM", ".AE"),
        aliases=("DFM", "DFMGI", "DUBAI", "دبي", "سوق دبي", "الامارات", "الإمارات", "الاماراتية", "الإماراتية"),
    ),
    "ADX": MarketConfig(
        exchange="ADX",
        ui_code="ADX",
        name_ar="سوق أبوظبي للأوراق المالية",
        name_en="Abu Dhabi Securities Exchange",
        index_name="FADGI",
        currency_ar="د.إ",
        currency_code="AED",
        timezone_name="Asia/Dubai",
        utc_offset_hours=4,
        trading_weekdays=(0, 1, 2, 3, 4),  # Mon-Fri in UAE
        session_open_min=10 * 60,
        session_close_min=15 * 60,
        data_ready_min=17 * 60,
        sharia_index="ADX Sharia",
        market_cache_key="market_status_ADX",
        official_site="adx.ae",
        supabase_env_prefix="SAUDI",
        ticker_suffixes=(".AD", ".ADX"),
        aliases=("ADX", "FADGI", "ABU DHABI", "ABUDHABI", "أبوظبي", "ابوظبي", "أبو ظبي", "ابو ظبي"),
    ),
    "COMMODITIES": MarketConfig(
        exchange="COMMODITIES",
        ui_code="METALS",
        name_ar="الذهب والفضة",
        name_en="Gold & Silver",
        index_name="METALS_IDX",
        currency_ar="دولار",
        currency_code="USD",
        timezone_name="UTC",
        utc_offset_hours=0,
        trading_weekdays=(0, 1, 2, 3, 4),  # Mon-Fri global markets
        session_open_min=0,
        session_close_min=23 * 60 + 59,
        data_ready_min=23 * 60,
        sharia_index="Metals",
        market_cache_key="market_status_METALS",
        official_site="",
        supabase_env_prefix="SAUDI",
        ticker_suffixes=("=F", "=X"),
        aliases=("COMMODITIES", "METALS", "GOLD", "SILVER", "XAU", "XAG", "XAUUSD", "XAGUSD", "الذهب", "الدهب", "الفضة", "الفضه", "المعادن", "السلع"),
    ),
    "KSE": MarketConfig(
        exchange="KSE",
        ui_code="KSE",
        name_ar="بورصة الكويت",
        name_en="Boursa Kuwait",
        index_name="BKP",
        currency_ar="د.ك",
        currency_code="KWD",
        timezone_name="Asia/Kuwait",
        utc_offset_hours=3,
        trading_weekdays=(6, 0, 1, 2, 3),
        session_open_min=9 * 60,
        session_close_min=12 * 60 + 40,
        data_ready_min=15 * 60,
        sharia_index="Kuwait Sharia",
        market_cache_key="market_status_Kuwait",
        official_site="boursakuwait.com.kw",
        supabase_env_prefix="KUWAIT",
        ticker_suffixes=(".KW", ".KSE"),
        aliases=("KSE", "BKP", "KUWAIT", "KWD", "الكويت", "الكويتية", "الكويتي"),
    ),
}

# Precomputed lookup table: uppercase alias -> canonical exchange code
_ALIAS_TO_EXCHANGE: Dict[str, str] = {}
for _exch_code, _cfg in BUILTIN_MARKETS.items():
    _ALIAS_TO_EXCHANGE[_exch_code.upper()] = _exch_code
    _ALIAS_TO_EXCHANGE[_cfg.ui_code.upper()] = _exch_code
    for _al in _cfg.aliases:
        _ALIAS_TO_EXCHANGE[_al.strip().upper()] = _exch_code

_DYNAMIC_MARKETS: Dict[str, MarketConfig] = {}
_SB_CLIENTS: Dict[str, Any] = {}
_SB_LOCK = threading.Lock()
_CLEAN_EXCH_RE = re.compile(r"^[A-Z0-9_]{2,16}$")


def normalize_exchange_code(market: Optional[str]) -> str:
    """Normalize any market/exchange alias to its canonical DB exchange code (default 'EGX')."""
    if not market:
        return "EGX"
    raw = str(market).strip()
    if not raw:
        return "EGX"
    up = raw.upper()
    if up in _ALIAS_TO_EXCHANGE:
        return _ALIAS_TO_EXCHANGE[up]
    for alias_key, exch in _ALIAS_TO_EXCHANGE.items():
        if len(alias_key) >= 3 and alias_key in up:
            return exch
    # Support arbitrary future exchange codes directly (e.g. "MSX", "BHB", "OMAN")
    clean = re.sub(r"[^A-Z0-9_]", "", up)
    if _CLEAN_EXCH_RE.fullmatch(clean):
        return clean
    return "EGX"


def get_market_config(market: Optional[str]) -> MarketConfig:
    """Return MarketConfig for a known exchange or auto-synthesize one for any future exchange."""
    exch = normalize_exchange_code(market)
    if exch in BUILTIN_MARKETS:
        return BUILTIN_MARKETS[exch]
    if exch in _DYNAMIC_MARKETS:
        return _DYNAMIC_MARKETS[exch]

    cfg = MarketConfig(
        exchange=exch,
        ui_code=exch,
        name_ar=f"سوق {exch}",
        name_en=f"{exch} Exchange",
        index_name=exch,
        currency_ar="",
        currency_code="",
        timezone_name="Asia/Riyadh",
        utc_offset_hours=3,
        market_cache_key=f"market_status_{exch}",
        supabase_env_prefix=exch,
    )
    _DYNAMIC_MARKETS[exch] = cfg
    return cfg


def ui_market_label(market: Optional[str]) -> str:
    return get_market_config(market).ui_code


EGX_USD_SYMBOLS = frozenset({
    "FAITA", "EGBE", "EKHO", "MOIL", "NAHO", "NDRL", "SAIB", "GPPL", "TRTO",
})


def currency_for_market(market: Optional[str]) -> str:
    cfg = get_market_config(market)
    return cfg.currency_ar or cfg.currency_code or ""


def currency_for_symbol(symbol: Optional[str], market: Optional[str] = "EGX") -> str:
    """Return exact display currency for a ticker (handling USD-denominated EGX stocks like FAITA, EGBE, MOIL)."""
    clean = str(symbol or "").strip().upper().split(".")[0]
    if clean and normalize_exchange_code(market) == "EGX" and clean in EGX_USD_SYMBOLS:
        return "$"
    return currency_for_market(market)


def get_market_now(market: Optional[str] = "EGX", now_ts: Optional[float] = None) -> dt.datetime:
    cfg = get_market_config(market)
    try:
        tz = ZoneInfo(cfg.timezone_name)
    except Exception:
        tz = dt.timezone(dt.timedelta(hours=cfg.utc_offset_hours))
    if now_ts is not None:
        return dt.datetime.fromtimestamp(now_ts, tz=tz)
    return dt.datetime.now(tz)


def is_market_live_session(market: Optional[str] = "EGX", now_dt: Optional[dt.datetime] = None) -> bool:
    """Return True if the given exchange is currently inside live trading hours."""
    cfg = get_market_config(market)
    local_dt = now_dt or get_market_now(cfg.exchange)
    if local_dt.weekday() not in cfg.trading_weekdays:
        return False
    if cfg.exchange == "EGX":
        try:
            from api.egx_trading_calendar import is_egx_session
            if not is_egx_session(local_dt):
                return False
        except Exception:
            pass
    cur_min = local_dt.hour * 60 + local_dt.minute
    return cfg.session_open_min <= cur_min < cfg.session_close_min


def get_last_completed_session_ready_ts_for_market(
    market: Optional[str] = "EGX",
    now_dt: Optional[dt.datetime] = None,
) -> Optional[float]:
    """Return local ready timestamp (post-close) of the latest completed session for any market."""
    cfg = get_market_config(market)
    local_dt = now_dt or get_market_now(cfg.exchange)
    cur_min = local_dt.hour * 60 + local_dt.minute
    today = local_dt.date()
    tz = local_dt.tzinfo

    egx_cal = None
    if cfg.exchange == "EGX":
        try:
            from api.egx_trading_calendar import is_egx_session
            egx_cal = is_egx_session
        except Exception:
            egx_cal = None

    for back in range(0, 14):
        cand_day = today - dt.timedelta(days=back)
        if egx_cal is not None:
            if not egx_cal(cand_day):
                continue
        elif cand_day.weekday() not in cfg.trading_weekdays:
            continue
        if back == 0 and cur_min < cfg.session_close_min:
            continue
        r_hr, r_min = divmod(cfg.data_ready_min, 60)
        ready_dt = dt.datetime(cand_day.year, cand_day.month, cand_day.day, r_hr, r_min, 0, tzinfo=tz)
        return ready_dt.timestamp()
    return None


def detect_exchange_from_suffix(raw_symbol: str) -> Optional[Tuple[str, str]]:
    """If raw_symbol carries a known exchange suffix (e.g. .SR, .QA, .DU, .AD, .CA), return (core, exchange)."""
    s = str(raw_symbol or "").strip().upper()
    if not s:
        return None
    for exch, cfg in BUILTIN_MARKETS.items():
        for suf in cfg.ticker_suffixes:
            if s.endswith(suf):
                core = s[: -len(suf)].strip()
                if core:
                    return (core, exch)
    return None


_TEXT_MARKET_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    (
        "TADAWUL",
        re.compile(
            r"(?:\b(?:TADAWUL|TASI|SAUDI|KSA|SAR)\b"
            r"|السعودي|السعودية|تاسي|سوق\s+تداول|تداول\s+السعودي|تداول\s+السعودية|الريال\s+السعودي|ريال\s+سعودي)",
            re.IGNORECASE,
        ),
    ),
    (
        "QSE",
        re.compile(
            r"(?:\b(?:QSE|QSI|QATAR|QAR)\b"
            r"|بورصة\s+قطر|سوق\s+قطر|الأسهم\s+القطرية|الاسهم\s+القطرية|سوق\s+الدوحة|بورصة\s+الدوحة|ريال\s+قطري"
            r"|(?:^|[\s،,؟?])(?:قطر|القطرية|القطري)(?:$|[\s،,؟?]))",
            re.IGNORECASE,
        ),
    ),
    (
        "DFM",
        re.compile(
            r"(?:\b(?:DFM|DFMGI|DUBAI)\b"
            r"|سوق\s+دبي|بورصة\s+دبي|دبي\s+المالي|الأسهم\s+الإماراتية|الاسهم\s+الاماراتية|درهم\s+إماراتي|درهم\s+اماراتي"
            r"|(?:^|[\s،,؟?])(?:دبي|الإمارات|الامارات|الإماراتية|الاماراتية)(?:$|[\s،,؟?]))",
            re.IGNORECASE,
        ),
    ),
    (
        "ADX",
        re.compile(
            r"(?:\b(?:ADX|FADGI|ABU\s+DHABI|ABUDHABI)\b"
            r"|سوق\s+أبوظبي|سوق\s+ابوظبي|بورصة\s+أبوظبي|بورصة\s+ابوظبي|أبوظبي\s+للأوراق|ابوظبي\s+للأوراق"
            r"|(?:^|[\s،,؟?])(?:أبوظبي|ابوظبي|أبو\s+ظبي|ابو\s+ظبي)(?:$|[\s،,؟?]))",
            re.IGNORECASE,
        ),
    ),
    (
        "KSE",
        re.compile(
            r"(?:\b(?:KSE|KUWAIT|KWD)\b"
            r"|بورصة\s+الكويت|سوق\s+الكويت|الأسهم\s+الكويتية|الاسهم\s+الكويتية|دينار\s+كويتي"
            r"|(?:^|[\s،,؟?])(?:الكويت|الكويتية|الكويتي)(?:$|[\s،,؟?]))",
            re.IGNORECASE,
        ),
    ),
    (
        "COMMODITIES",
        re.compile(
            r"(?:\b(?:XAUUSD|XAGUSD|XAU|XAG|COMMODITIES|METALS)\b"
            r"|سعر\s+الذهب|أونصة\s+الذهب|اونصة\s+الذهب|سعر\s+الفضة|أونصة\s+الفضة|اونصة\s+الفضة|الذهب\s+والفضة|المعادن\s+النفيسة"
            r"|(?:^|[\s،,؟?])(?:الذهب|الدهب|الفضة|الفضه)(?:$|[\s،,؟?]))",
            re.IGNORECASE,
        ),
    ),
)

_ENV_LOADED = False


def _ensure_registry_env_loaded() -> None:
    """Lazily load repo `.env` and `web/.env.local` once so dedicated DB URLs are visible in local dev."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    with _SB_LOCK:
        if _ENV_LOADED:
            return
        try:
            from dotenv import load_dotenv
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            for cand in (
                os.path.join(repo_root, ".env"),
                os.path.join(repo_root, "web", ".env.local"),
            ):
                if os.path.isfile(cand):
                    load_dotenv(cand, override=False)
        except Exception:
            pass
        _ENV_LOADED = True


def detect_market_from_text(text: Optional[str]) -> Optional[str]:
    """
    Detect an explicit non-EGX exchange mention in user query text (returns canonical exchange or None).
    Uses strict word/ticker boundaries so ordinary EGX prose (e.g. 'أحجام التداول', 'التقاطع الذهبي', 'necessary')
    NEVER triggers false-positive routing to Saudi/GCC/Commodities.
    """
    if not text:
        return None
    raw = str(text)
    up = raw.upper()
    # 1. Explicit ticker suffixes anchored to a real ticker token (e.g. 2222.SR, QNBK.QA, EMAAR.DU, GC=F)
    for exch, cfg in BUILTIN_MARKETS.items():
        if exch == "EGX":
            continue
        for suf in cfg.ticker_suffixes:
            if re.search(rf"(?<![A-Za-z0-9/])[A-Za-z0-9]{{2,12}}{re.escape(suf)}(?![A-Za-z0-9])", up):
                return exch
    # 2. Word-bounded Arabic/English market patterns
    for exch, pat in _TEXT_MARKET_PATTERNS:
        if pat.search(raw):
            return exch
    return None


def get_dedicated_supabase_client(env_prefix: str) -> Optional[Any]:
    """Return cached Supabase client for `<PREFIX>_SUPABASE_URL` if configured in env, else None."""
    pref = str(env_prefix or "").strip().upper()
    if not pref:
        return None
    if pref in _SB_CLIENTS:
        return _SB_CLIENTS[pref]
    _ensure_registry_env_loaded()
    with _SB_LOCK:
        if pref in _SB_CLIENTS:
            return _SB_CLIENTS[pref]
        url = (
            os.getenv(f"{pref}_SUPABASE_URL")
            or os.getenv(f"NEXT_PUBLIC_{pref}_SUPABASE_URL")
            or ""
        ).strip()
        key = (
            os.getenv(f"{pref}_SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv(f"{pref}_SUPABASE_ANON_KEY")
            or os.getenv(f"NEXT_PUBLIC_{pref}_SUPABASE_ANON_KEY")
            or ""
        ).strip()
        if not url or not key:
            return None
        try:
            from supabase import ClientOptions, create_client
            client = create_client(
                url,
                key,
                options=ClientOptions(postgrest_client_timeout=15, storage_client_timeout=15),
            )
        except TypeError:
            try:
                from supabase import create_client
                client = create_client(url, key)
            except Exception:
                return None
        except Exception:
            return None
        _SB_CLIENTS[pref] = client
        return client


def get_supabase_for_exchange(
    market: Optional[str],
    primary_sb_getter: Any = None,
    *,
    primary_sb: Any = None,
) -> Optional[Any]:
    """
    Resolve the Supabase client for any exchange:
    - EGX -> Primary Supabase.
    - TADAWUL -> dedicated SAUDI_SUPABASE (returns None if unconfigured, preserving explicit error handling).
    - Any other exchange (QSE, DFM, ADX, KSE, future) -> dedicated `<PREFIX>_SUPABASE_URL` if set,
      otherwise automatically falls back to Primary Supabase (shared multi-exchange tables filtered by `exchange`).
    """
    def _resolve_primary() -> Optional[Any]:
        if primary_sb is not None:
            return primary_sb
        if callable(primary_sb_getter):
            return primary_sb_getter()
        return primary_sb_getter

    cfg = get_market_config(market)
    if cfg.exchange == "EGX":
        return _resolve_primary()
    # 1. Check exchange-specific dedicated DB first (e.g., QSE_SUPABASE_URL, DFM_SUPABASE_URL)
    if cfg.exchange != cfg.supabase_env_prefix:
        exch_dedicated = get_dedicated_supabase_client(cfg.exchange)
        if exch_dedicated is not None:
            return exch_dedicated
    # 2. Check configured shared/regional DB prefix (e.g., SAUDI_SUPABASE_URL for TADAWUL + GCC/METALS)
    if cfg.supabase_env_prefix:
        dedicated = get_dedicated_supabase_client(cfg.supabase_env_prefix)
        if dedicated is not None:
            return dedicated
    # TADAWUL lives on dedicated SAUDI_SUPABASE; new exchanges (QSE/DFM/ADX/OMAN/...) fall back to Primary Supabase!
    if cfg.exchange == "TADAWUL":
        return None
    return _resolve_primary()
