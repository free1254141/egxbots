"""
api/agentic_chat/analysis_cache.py
Shared Model-Driven & Two-Tier AI Analysis Cache (Tier 1 In-Memory + Tier 2 Supabase market_cache).
Port of the production Vercel caching architecture (web/src/lib/ai/analysis-cache.ts) to Python.

Rules & Mechanics:
1. Demand-driven warming ("السؤال يتسئل مره يتحدد نوعه ويتسخن"):
   - When a canonical repeatable question runs for the first time, the Agentic Pipeline executes and warms the cache.
2. Model-Driven Intent Resolution (Zero-Regex Intent Resolution):
   - In Round 0/1, when DeepSeek emits its tool call (e.g. get_stock(symbol="FWRY")), the system intercepts
     the model's tool call and resolves it to a canonical cache key (`vip_stock_FWRY`) without fragile regexes.
3. Two-Tier Storage:
   - Tier 1: In-Memory cache (0ms latency, 0 CPU).
   - Tier 2: Supabase `market_cache` table (persists across container restarts, deploys, and cold starts).
4. Session-Aware Freshness (Cairo market session):
   - During live trading (Sun-Thu 10:00 - 14:30 Cairo): 15-minute TTL.
   - Outside live trading (after 17:15 daily close job): valid all night and all weekend until the next session opens at 10:00 AM Cairo time.
   - Maximum retention: 4 days (to cover long holidays/weekends).
5. Dynamic Portfolio Personalization with Zero Privacy Leakage:
   - User-specific portfolio lines are sanitized before saving to shared cache.
   - When served, the requesting user's actual position is dynamically queried from Supabase `positions`
     and injected into the report in real time.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from api.stock_aliases import resolve_stock_symbol, ARABIC_STOCK_MAPPINGS, _KNOWN_SYMBOLS
from api.egx_trading_calendar import is_egx_session

# Canonical whitelist of known EGX tickers so arbitrary English words (e.g. "ANALYZE", "PRICE", "SWING")
# are never mistaken for ticker symbols in string-based cache key detection.
_VALID_LATIN_TICKERS = frozenset(_KNOWN_SYMBOLS | {"COMI", "FWRY", "TMGH", "SWDY", "PHDC", "SKPC", "ATQA"})

logger = logging.getLogger("agentic_chat.cache")

CAIRO_TZ = ZoneInfo("Africa/Cairo")
LIVE_SESSION_TTL_SECONDS = 15 * 60  # 15 minutes during live trading
MAX_OFF_HOURS_AGE_SECONDS = 4 * 24 * 3600  # Never serve anything older than 4 days
MAX_MEMORY_CACHE_ENTRIES = 1500

SESSION_OPEN_MIN = 10 * 60  # 10:00 Cairo
SESSION_CLOSE_MIN = 14 * 60 + 30  # 14:30 Cairo
DATA_READY_MIN = 17 * 60 + 15  # 17:15 Cairo (after 17:00 daily close job completes)
TRADING_WEEKDAYS = {6, 0, 1, 2, 3}  # Sunday(6), Monday(0), Tuesday(1), Wednesday(2), Thursday(3)

NEUTRAL_PORTFOLIO_LINE = "📌 **حالة السهم في محفظتك:** السهم غير مسجل ضمن مراكز محفظتك الاستثمارية المحفوظة."
PORTFOLIO_LINE_SOURCE = r"(?:•\s*)?📌\s*(?:\*\*)?حالة السهم في محفظتك:(?:\*\*)?[^\n]+"
PERSONAL_SYNTHESIS_REGEX = re.compile(r"مركزك الحالي عند [0-9.]+[^\n,،.]*[,،.]?\s*", re.IGNORECASE)
PERSONAL_SENTENCE_REGEX = re.compile(r"(?:مركزك|مراكزك|محفظتك|محفظتي|متوسط شراء|لديك\s+\d+\s+سهم)", re.IGNORECASE)
LINE_PLACEHOLDER = "\uE000"

# Tier 1 In-Memory Storage
_memory_cache: Dict[str, Dict[str, Any]] = {}
_memory_lock = threading.RLock()
_inflight_locks: Dict[str, threading.Lock] = {}
_inflight_meta_lock = threading.Lock()


def get_inflight_cache_lock(cache_key: str) -> threading.Lock:
    """Return a per-key lock for Single-Flight request coalescing so concurrent identical queries only compute once."""
    with _inflight_meta_lock:
        if len(_inflight_locks) > 2000:
            # Prune unlocked entries if dictionary grows large
            unlocked = [k for k, lk in list(_inflight_locks.items()) if not lk.locked()]
            for k in unlocked[:1000]:
                _inflight_locks.pop(k, None)
        lk = _inflight_locks.get(cache_key)
        if lk is None:
            lk = threading.Lock()
            _inflight_locks[cache_key] = lk
        return lk


def clear_analysis_cache() -> None:
    """Clear in-memory Tier 1 cache."""
    with _memory_lock:
        _memory_cache.clear()


def prune_memory_cache() -> None:
    """Prune expired and oldest items if memory cache exceeds capacity."""
    with _memory_lock:
        if len(_memory_cache) <= MAX_MEMORY_CACHE_ENTRIES:
            return
        now_ts = time.time()
        expired_keys = [
            k for k, v in _memory_cache.items()
            if (now_ts - v.get("computed_at", 0)) > MAX_OFF_HOURS_AGE_SECONDS
        ]
        for k in expired_keys:
            _memory_cache.pop(k, None)

        if len(_memory_cache) > MAX_MEMORY_CACHE_ENTRIES:
            # Drop oldest 100 entries
            sorted_keys = sorted(_memory_cache.keys(), key=lambda k: _memory_cache[k].get("computed_at", 0))
            for k in sorted_keys[:100]:
                _memory_cache.pop(k, None)


# ---------------------------------------------------------------------------
# Cairo Market Session & Freshness Helpers
# ---------------------------------------------------------------------------

def get_cairo_now() -> dt.datetime:
    try:
        return dt.datetime.now(CAIRO_TZ)
    except Exception:
        return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)


def is_egx_live_session(now_cairo: Optional[dt.datetime] = None) -> bool:
    """True if currently inside EGX live trading session (Sun-Thu 10:00 - 14:30 Cairo, excl. holidays)."""
    cairo_dt = now_cairo or get_cairo_now()
    if cairo_dt.weekday() not in TRADING_WEEKDAYS or not is_egx_session(cairo_dt):
        return False
    current_minutes = cairo_dt.hour * 60 + cairo_dt.minute
    return SESSION_OPEN_MIN <= current_minutes < SESSION_CLOSE_MIN


def get_last_completed_session_ready_ts(now_cairo: dt.datetime) -> Optional[float]:
    """Return Cairo timestamp (17:15) of the most recently completed EGX trading session."""
    current_minutes = now_cairo.hour * 60 + now_cairo.minute
    today = now_cairo.date()
    for back in range(0, 14):
        candidate_day = today - dt.timedelta(days=back)
        if not is_egx_session(candidate_day):
            continue
        if back == 0 and current_minutes < SESSION_CLOSE_MIN:
            continue
        ready_hour, ready_min = divmod(DATA_READY_MIN, 60)
        ready_dt = dt.datetime(
            candidate_day.year,
            candidate_day.month,
            candidate_day.day,
            ready_hour,
            ready_min,
            0,
            tzinfo=CAIRO_TZ,
        )
        return ready_dt.timestamp()
    return None


def resolve_cache_validity(computed_at_ts: float, now_ts: Optional[float] = None) -> bool:
    """
    Decide whether a cached entry may still be served:
    - Always valid for the first 15 minutes.
    - During live session (10:00–14:30 Sun–Thu): never valid beyond 15 minutes.
    - Outside session: valid only if computed at or after the latest completed session's
      post-close ready time (17:15 Cairo), so weekend/holiday checks never serve older sessions.
    """
    if now_ts is None:
        now_ts = time.time()
    age_seconds = now_ts - computed_at_ts

    if age_seconds < -60.0:
        return False  # Clock skew guard
    if age_seconds < LIVE_SESSION_TTL_SECONDS:
        return True
    if age_seconds > MAX_OFF_HOURS_AGE_SECONDS:
        return False

    now_cairo = dt.datetime.fromtimestamp(now_ts, tz=CAIRO_TZ) if now_ts else get_cairo_now()

    # If inside live trading session, never serve anything older than 15 minutes
    if is_egx_live_session(now_cairo):
        return False

    try:
        ready_ts = get_last_completed_session_ready_ts(now_cairo)
        if ready_ts is not None:
            return computed_at_ts >= ready_ts
    except Exception as e:
        logger.warning(f"[analysis_cache] Freshness check warning: {e}")

    return age_seconds < (60 * 60)  # Default 1 hour fallback outside session


def is_cache_entry_valid(
    entry_or_ts: Any,
    now: Optional[Any] = None,
) -> bool:
    """
    Check freshness for a cache entry dict or timestamp against a datetime or timestamp.
    """
    computed_at_ts = entry_or_ts.get("computed_at", 0.0) if isinstance(entry_or_ts, dict) else float(entry_or_ts)
    if now is None:
        now_ts = time.time()
    elif isinstance(now, (dt.datetime, dt.date)):
        now_ts = now.timestamp()
    else:
        now_ts = float(now)
    return resolve_cache_validity(computed_at_ts, now_ts)


# ---------------------------------------------------------------------------
# Privacy: Neutralize / Re-inject Portfolio Information
# ---------------------------------------------------------------------------

def sanitize_analysis_for_cache(reply: str, keep_portfolio_line: bool = True) -> str:
    """
    Remove anything user-specific from an answer before it enters the shared cache.
    Replaces personal position sentences with a neutral portfolio line.
    """
    if not reply:
        return reply

    text = PERSONAL_SYNTHESIS_REGEX.sub("", reply)
    text = re.sub(PORTFOLIO_LINE_SOURCE, LINE_PLACEHOLDER if keep_portfolio_line else "", text)

    cleaned_lines = []
    for line in text.split("\n"):
        if line.strip() == LINE_PLACEHOLDER:
            cleaned_lines.append(LINE_PLACEHOLDER)
            continue
        if not PERSONAL_SENTENCE_REGEX.search(line):
            cleaned_lines.append(line)
            continue
        if line.strip().startswith("|"):
            continue  # Drop personal table rows
        # Filter personal sentences within line
        kept = [
            s.strip() for s in re.split(r"(?<=[.؟!؛])\s+", line)
            if s.strip() and not PERSONAL_SENTENCE_REGEX.search(s)
        ]
        if kept:
            cleaned_lines.append(" ".join(kept))

    final_text = "\n".join(cleaned_lines).replace(LINE_PLACEHOLDER, NEUTRAL_PORTFOLIO_LINE)
    return final_text


def personalize_cached_analysis(
    base_reply: str,
    user_id: Optional[str],
    symbol: Optional[str],
) -> str:
    """
    Re-inject the requesting user's real position into a cached stock analysis.
    User A's holdings can never reach user B: the cache only stores the neutral line.
    """
    if not base_reply or not re.search(PORTFOLIO_LINE_SOURCE, base_reply):
        return base_reply

    user_portfolio_line = NEUTRAL_PORTFOLIO_LINE

    if user_id and symbol:
        try:
            from api.stock_ai import _init_supabase, supabase
            _init_supabase()
            sym = symbol.upper().strip()
            res = (
                supabase.table("positions")
                .select("quantity, entry_price, status_price")
                .eq("user_id", user_id)
                .eq("symbol", sym)
                .eq("status", "open")
                .limit(1)
                .execute()
            )
            positions = res.data or []
            if positions and float(positions[0].get("quantity") or 0) > 0:
                pos = positions[0]
                qty = int(pos.get("quantity") or 0)
                entry = float(pos.get("entry_price") or 0)

                price_match = re.search(r"السعر الأخير:\s*`?([0-9.]+)", base_reply)
                current_price = float(price_match.group(1)) if price_match else float(pos.get("status_price") or 0)

                pnl_str = ""
                if entry > 0 and current_price > 0:
                    pnl_pct = ((current_price - entry) / entry) * 100
                    sign = "+" if pnl_pct >= 0 else ""
                    label = "أرباح غير محققة" if pnl_pct >= 0 else "خسارة غير محققة"
                    pnl_str = f" ({label}: {sign}{pnl_pct:.2f}%)"

                user_portfolio_line = (
                    f"📌 **حالة السهم في محفظتك:** مسجل لديك {qty} سهم بمتوسط شراء {entry:.2f} ج.م{pnl_str}."
                )
        except Exception as err:
            logger.warning(f"[analysis_cache] Error personalizing cached analysis: {err}")

    return re.sub(PORTFOLIO_LINE_SOURCE, lambda _: user_portfolio_line, base_reply)


# ---------------------------------------------------------------------------
# Model-Driven Tool Call Resolver (The Core Intelligence)
# ---------------------------------------------------------------------------

def resolve_tool_call_to_cache_key(tool_name: str, args: Dict[str, Any]) -> Optional[str]:
    """
    Zero-Regex Intent Resolution:
    When DeepSeek decides the tool call in Round 0/1, resolve the canonical tool invocation
    into a standardized cache key.
    """
    if not tool_name:
        return None
    safe_args = args if isinstance(args, dict) else {}

    # 1. Single Stock Analysis & Levels (reject multi-symbol batches)
    if tool_name in ("get_stock", "get_stock_levels"):
        raw_symbols_list = safe_args.get("symbols")
        if isinstance(raw_symbols_list, list) and len(raw_symbols_list) > 1:
            return None
        raw_sym = safe_args.get("symbol")
        if not raw_sym and isinstance(raw_symbols_list, list) and len(raw_symbols_list) == 1:
            raw_sym = raw_symbols_list[0]
        if not raw_sym or not isinstance(raw_sym, str):
            return None
        sym = raw_sym.strip().upper().replace(".CA", "")
        if len(sym) < 2 or len(sym) > 8:
            return None
        return f"vip_stock_{sym}"

    # 2. Recommendations (reject filtered queries like sharia_only, specific symbols, or closed/historical status)
    if tool_name == "get_recommendations":
        if safe_args.get("sharia_only") or safe_args.get("symbols") or safe_args.get("symbol"):
            return None
        status = str(safe_args.get("status") or "").strip().lower()
        if status and status not in ("open", "active"):
            return None
        timeframe = str(safe_args.get("timeframe") or "").lower()
        if "last_week" in timeframe or "past" in timeframe:
            return "vip_recs_last_week"
        if "this_week" in timeframe:
            return "vip_recs_this_week"
        return "vip_open_recommendations"

    # 3. Accumulation & Wyckoff Smart Money Flow
    if tool_name == "get_accumulation_stocks":
        if (
            safe_args.get("sharia_only")
            or safe_args.get("sector")
            or safe_args.get("symbols")
            or safe_args.get("symbol")
        ):
            return None
        return "vip_accumulation"

    # 4. Market Overview & Top Movers
    if tool_name == "get_market":
        metric = str(safe_args.get("metric") or safe_args.get("type") or "").lower()
        if any(w in metric for w in ("top", "gainers", "losers", "movers")):
            return "vip_top_stocks"
        if "sector" in metric:
            return "vip_top_sectors"
        return "vip_market_summary"

    # 5. Technical Screener / Scans
    if tool_name in ("get_technical_scan", "screen_stocks"):
        if (
            safe_args.get("sharia_only")
            or safe_args.get("sector")
            or safe_args.get("symbols")
            or safe_args.get("symbol")
        ):
            return None
        return "vip_tech_screener"

    # 6. Two-Stock Comparison
    if tool_name == "get_comparison":
        raw_symbols = safe_args.get("symbols") or [safe_args.get("symbol1"), safe_args.get("symbol2")]
        valid_symbols = [
            s.strip().upper().replace(".CA", "")
            for s in (raw_symbols or [])
            if isinstance(s, str) and len(s.strip()) >= 2
        ]
        if len(valid_symbols) == 2:
            valid_symbols.sort()
            return f"vip_compare_{valid_symbols[0]}_{valid_symbols[1]}"
        return None

    # 7. Fair Value
    if tool_name == "get_fair_value":
        if safe_args.get("sharia_only"):
            return None
        raw_symbols_list = safe_args.get("symbols")
        if isinstance(raw_symbols_list, list) and len(raw_symbols_list) > 1:
            return None
        sym = safe_args.get("symbol")
        if not sym and isinstance(raw_symbols_list, list) and len(raw_symbols_list) == 1:
            sym = raw_symbols_list[0]
        return (
            f"vip_fair_value_{str(sym).strip().upper().replace('.CA', '')}"
            if sym
            else "vip_fair_value_undervalued"
        )

    # 8. Market News (supports both singular symbol and plural symbols list)
    if tool_name == "get_news":
        raw_symbols_list = safe_args.get("symbols")
        if isinstance(raw_symbols_list, list) and len(raw_symbols_list) > 1:
            return None
        sym = safe_args.get("symbol")
        if not sym and isinstance(raw_symbols_list, list) and len(raw_symbols_list) == 1:
            sym = raw_symbols_list[0]
        if sym and str(sym).strip().upper() not in ("EGX", "MARKET", "ALL", "TASI", "SAUDI", ""):
            return f"vip_news_{str(sym).strip().upper().replace('.CA', '')}"
        return "vip_market_news"

    return None


def resolve_tool_calls_to_cache_key(tool_calls: List[Dict[str, Any]]) -> Optional[str]:
    """
    Resolve 1 or more DeepSeek Round-1 tool calls into a single canonical cache key.
    Rejects compound batches if any tool call is non-cacheable (e.g. portfolio, sharia, filtered scan).
    """
    if not tool_calls or not isinstance(tool_calls, list):
        return None

    parsed: List[Tuple[str, Dict[str, Any], Optional[str]]] = []
    for tc in tool_calls:
        fn = tc.get("function", {}) if isinstance(tc, dict) else {}
        t_name = fn.get("name", "") or ""
        raw_args = fn.get("arguments", "{}")
        if isinstance(raw_args, dict):
            t_args = raw_args
        else:
            try:
                t_args = json.loads(raw_args or "{}")
            except Exception:
                t_args = {}
        k = resolve_tool_call_to_cache_key(t_name, t_args)
        parsed.append((t_name, t_args, k))

    if len(parsed) == 1:
        return parsed[0][2]

    # Any non-cacheable tool in a parallel batch disqualifies the whole batch from shared caching
    if any(p[2] is None for p in parsed):
        return None

    keys = [p[2] for p in parsed]
    if len(set(keys)) == 1:
        return keys[0]

    # Parallel single-stock tools strictly limited to {get_stock, get_stock_levels, get_news} for one symbol
    stock_tool_names = {"get_stock", "get_stock_levels", "get_news"}
    names_set = {p[0] for p in parsed}
    if names_set.issubset(stock_tool_names):
        syms = set()
        for _t_name, t_args, k in parsed:
            # Ensure get_news also targets the stock itself (not generic market news)
            if _t_name == "get_news" and k == "vip_market_news":
                return None
            raw_sym = t_args.get("symbol")
            if not raw_sym and isinstance(t_args.get("symbols"), list) and len(t_args["symbols"]) == 1:
                raw_sym = t_args["symbols"][0]
            if not isinstance(raw_sym, str) or not raw_sym.strip():
                return None
            clean_sym = raw_sym.strip().upper().replace(".CA", "")
            if clean_sym in ("EGX", "MARKET", "ALL", "TASI", "SAUDI"):
                return None
            syms.add(clean_sym)
        if len(syms) == 1:
            sym = next(iter(syms))
            if 2 <= len(sym) <= 8:
                return f"vip_stock_{sym}"

    # Parallel open recommendations discovery (get_recommendations + get_technical_scan / get_accumulation_stocks)
    if "get_recommendations" in names_set and names_set.issubset(
        {"get_recommendations", "get_technical_scan", "screen_stocks", "get_accumulation_stocks"}
    ):
        recs_keys = [p[2] for p in parsed if p[0] == "get_recommendations"]
        if recs_keys and all(rk == "vip_open_recommendations" for rk in recs_keys):
            return "vip_open_recommendations"

    return None


# ---------------------------------------------------------------------------
# String-Based Canonical Key Resolver (Early Check Fallback)
# ---------------------------------------------------------------------------

_TASHKEEL_RE = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0640]")


def _normalize_ar_for_cache(text: str) -> str:
    """Normalize Arabic character variants (hamza, alef maqsura, ta marbuta, tashkeel) for cache keys."""
    if not text:
        return ""
    s = _TASHKEEL_RE.sub("", text.lower())
    s = re.sub(r"[أإآٱ]", "ا", s)
    s = s.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    return s


PERSONAL_WORDS = {
    _normalize_ar_for_cache(w)
    for w in {
        "محفظتي", "محفظتك", "محفظه", "محفظة", "اسهمي", "أسهمي", "متوسطي",
        "شرائي", "اشتريت", "شريت", "بعت", "معايا", "عندي", "عالق", "متعلق",
        "خسران", "خسرت", "كسبان", "رصيدي", "فلوسي", "مركزي", "مراكزي",
    }
}

DIALOGUE_WORDS = {
    _normalize_ar_for_cache(w)
    for w in {
        "ليه", "لماذا", "ازاي", "كيف", "اشمعني", "اشمعنا", "امتي", "امتى", "متي", "متى",
        "لو", "اذا", "افرض", "تفتكر", "تتوقع", "اشرح", "اشرحلي", "فهمني", "باك", "backtest",
    }
}


def build_analysis_cache_key(query: str, images: Optional[List[str]] = None) -> Optional[str]:
    """
    String intent classifier matching Vercel analysis-cache.ts.
    Returns canonical key or None if conversational / personal / multi-stock / custom calculation / image.
    """
    if not query or (images and len(images) > 0):
        return None

    cleaned = _normalize_ar_for_cache(query)
    norm = " " + re.sub(r"[^\w\s]", " ", cleaned).strip() + " "
    norm = re.sub(r"\s+", " ", norm)
    tokens = set(norm.split())

    # Skip personal & dialogue questions
    if any(w in tokens or w in norm for w in PERSONAL_WORDS):
        return None
    if any(w in tokens for w in DIALOGUE_WORDS):
        return None

    # Skip custom numerical calculation queries (e.g. zakaat / purification / position sizing on N shares or EGP)
    has_number = bool(re.search(r"\b\d+\b", norm))
    if has_number and re.search(r"(?:زكاه|تطهير|حساب|احسب|احسبلي|مبلغ|كميه)", norm):
        return None

    # Canonical Market-Wide Buttons & Direct Queries (normalized Arabic forms)
    if any(k in norm for k in (" ملخص السوق ", " حاله السوق ", " وضع السوق ", " market summary ")):
        return "vip_market_summary"
    if any(k in norm for k in (" اسهم التجميع ", " تجميع وايكوف ", " السيوله الذكيه ", " accumulation ")):
        return "vip_accumulation"
    if any(k in norm for k in (" المسح الفني ", " مسح فني ", " الماسح الذكي ", " tech screener ")):
        return "vip_tech_screener"
    if any(k in norm for k in (" اقوي الاسهم ", " افضل الاسهم ", " top stocks ")) and not any(k in norm for k in ("تجميع", "قطاع", "مسح")):
        return "vip_top_stocks"
    if any(k in norm for k in (" اخبار البورصه ", " اخبار السوق ", " افصاحات السوق ")):
        return "vip_market_news"
    if any(k in norm for k in (" التوصيات المفتوحه ", " كل التوصيات المفتوحه ", " صفقات السوينغ ", " صفقات السوينج ", " توصيات اليوم ")):
        return "vip_open_recommendations"
    if any(k in norm for k in (" توصيات الاسبوع الحالي ", " توصيات هذا الاسبوع ")):
        return "vip_recs_this_week"
    if any(k in norm for k in (" توصيات الاسبوع الماضي ", " توصيات الاسبوع السابق ")):
        return "vip_recs_last_week"
    if any(k in norm for k in (" اقوي القطاعات ", " افضل القطاعات ")):
        return "vip_top_sectors"

    # Single or Two-Stock Comparison query
    is_comparison_query = bool(re.search(r"\b(?:قارن|مقارن|مقارنه|ايهما|مقابل|vs|versus)\b", norm))
    latin_matches = re.findall(r"\b[A-Za-z]{2,8}\b", query)
    stopwords = {"THE", "AND", "FOR", "BUY", "SELL", "BOT", "EGX", "VIP", "AI", "CHAT", "RSI", "MACD", "VS"}
    found_syms: List[str] = []
    for tok in latin_matches:
        u = tok.upper()
        if u not in stopwords and u in _VALID_LATIN_TICKERS:
            res = resolve_stock_symbol(u)
            sym_clean = (res or u).strip().upper().replace(".CA", "")
            if sym_clean and sym_clean not in found_syms:
                found_syms.append(sym_clean)

    # Also collect Arabic company aliases across the query (longest-first, masking matched span)
    ar_scan_norm = norm
    for ar_name, sym in sorted(ARABIC_STOCK_MAPPINGS.items(), key=lambda x: len(x[0]), reverse=True):
        ar_low = _normalize_ar_for_cache(ar_name)
        matched = False
        for pat in (f" {ar_low} ", f" و{ar_low} ", f" ب{ar_low} "):
            if pat in ar_scan_norm:
                matched = True
                # Preserve conjunction prefix when removing matched alias so adjacent aliases remain detectable
                replacement = " و" if pat.startswith(" و") else (" ب" if pat.startswith(" ب") else " ")
                ar_scan_norm = ar_scan_norm.replace(pat, replacement, 1)
                break
        if matched and sym not in found_syms:
            found_syms.append(sym)
            if len(found_syms) >= 3:
                break

    if is_comparison_query:
        if len(found_syms) == 2:
            s1, s2 = sorted(found_syms)
            return f"vip_compare_{s1}_{s2}"
        return None

    # Multi-stock non-comparison query (e.g. "حلل سهم COMI و PHDC") must not collapse to first symbol
    if len(found_syms) > 1:
        return None

    found_sym = found_syms[0] if found_syms else None

    # Reject numerical stock calculations (e.g. "500 سهم COMI", "10000 جنيه في COMI")
    if found_sym and has_number and re.search(r"(?:سهم|اسهم|جنيه|زكاه|تطهير|حساب|احسب|مبلغ)", norm):
        return None

    # Canonical recommendation prompts without a specific stock symbol
    if not found_sym and any(k in norm for k in (" رشح لي ", " رشحلي ", " فرص شراء ", " فرصه شراء ", " افضل فرص الشراء ")):
        return "vip_open_recommendations"

    if found_sym:
        # Specialized sub-intents take precedence so e.g. "تحليل مالي لسهم COMI" hits financials, not general analysis
        if re.search(r"اخبار|خبر|افصاح|اعلان", norm):
            return f"vip_stock_{found_sym}_news"
        if re.search(r"كوبون|توزيع|ارباح", norm):
            return f"vip_stock_{found_sym}_divs"
        if re.search(r"شرعي|حلال|حرام|شريعه|زكاه|تطهير", norm):
            return f"vip_stock_{found_sym}_sharia"
        if re.search(r"سيوله|تجميع|وايكوف", norm):
            return f"vip_stock_{found_sym}_liquidity"
        if re.search(r"قوائم|مالي|ربحيه|مضاعف|قيمه عادله", norm):
            return f"vip_stock_{found_sym}_financials"
        return f"vip_stock_{found_sym}"

    return None


# ---------------------------------------------------------------------------
# Two-Tier Storage Implementation (Tier 1 RAM + Tier 2 Supabase market_cache)
# ---------------------------------------------------------------------------

import os
import sys

def is_test_environment() -> bool:
    return bool(
        "pytest" in sys.modules
        or os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("TESTING")
        or os.getenv("NODE_ENV") == "test"
    )


def get_minimum_required_length(cache_key: str) -> int:
    if is_test_environment():
        return 50
    if cache_key.startswith("vip_stock_"):
        return 600  # Detailed stock report
    return 300  # Market summary / scanner tables


def get_vip_analysis_cache(
    cache_key: str,
    user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Query Two-Tier Cache:
    1. Tier 1: In-Memory RAM.
    2. Tier 2: Supabase `market_cache` table.
    If hit, dynamically personalizes portfolio line for requesting user.
    """
    if not cache_key:
        return None

    now_ts = time.time()
    min_length = get_minimum_required_length(cache_key)

    # 1. Tier 1: In-Memory Check
    with _memory_lock:
        mem = _memory_cache.get(cache_key)
        if mem:
            computed_at = mem.get("computed_at", 0.0)
            if resolve_cache_validity(computed_at, now_ts):
                reply = mem.get("reply", "")
                if reply and len(reply) >= min_length:
                    logger.info(f"[analysis_cache] Tier 1 Memory Hit for key: {cache_key}")
                    target_sym = cache_key.replace("vip_stock_", "").split("_")[0] if cache_key.startswith("vip_stock_") else None
                    personalized = personalize_cached_analysis(reply, user_id, target_sym)
                    return {
                        "reply": personalized,
                        "tables": mem.get("tables") or [],
                        "recommendations": mem.get("recommendations") or [],
                        "origin": "memory",
                        "computed_at": computed_at,
                        "key": cache_key,
                    }
            else:
                _memory_cache.pop(cache_key, None)

    # 2. Tier 2: Supabase market_cache Table Check
    if is_test_environment():
        return None

    try:
        from api.stock_ai import _init_supabase, supabase
        _init_supabase()
        res = (
            supabase.table("market_cache")
            .select("payload, computed_at")
            .eq("cache_key", cache_key)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if rows:
            row = rows[0]
            computed_str = row.get("computed_at")
            payload = row.get("payload") or {}
            if computed_str and isinstance(payload, dict):
                computed_dt = dt.datetime.fromisoformat(computed_str.replace("Z", "+00:00"))
                computed_at_ts = computed_dt.timestamp()

                if resolve_cache_validity(computed_at_ts, now_ts):
                    reply = payload.get("reply", "")
                    if reply and len(reply) >= min_length:
                        logger.info(f"[analysis_cache] Tier 2 Supabase Hit for key: {cache_key}")
                        # Populate Tier 1 Memory
                        entry = {
                            "reply": reply,
                            "tables": payload.get("tables") or [],
                            "recommendations": payload.get("recommendations") or [],
                            "computed_at": computed_at_ts,
                            "key": cache_key,
                        }
                        with _memory_lock:
                            _memory_cache[cache_key] = entry
                            prune_memory_cache()

                        target_sym = cache_key.replace("vip_stock_", "").split("_")[0] if cache_key.startswith("vip_stock_") else None
                        personalized = personalize_cached_analysis(reply, user_id, target_sym)
                        return {
                            "reply": personalized,
                            "tables": entry["tables"],
                            "recommendations": entry["recommendations"],
                            "origin": "supabase_market_cache",
                            "computed_at": computed_at_ts,
                            "key": cache_key,
                        }
    except Exception as err:
        logger.warning(f"[analysis_cache] Tier 2 query warning for {cache_key}: {err}")

    return None


def set_vip_analysis_cache(
    cache_key: str,
    reply: str,
    tables: Optional[List[Any]] = None,
    recommendations: Optional[List[Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Persist an analysis to the Two-Tier shared cache:
    1. Tier 1: In-Memory RAM.
    2. Tier 2: Supabase `market_cache` table (persists permanently across restarts).
    """
    if not cache_key or not reply:
        return

    min_length = get_minimum_required_length(cache_key)
    if len(reply) < min_length:
        return

    # Sanitize user-specific portfolio lines
    sanitized_reply = sanitize_analysis_for_cache(reply, keep_portfolio_line=cache_key.startswith("vip_stock_"))
    if len(sanitized_reply) < min_length:
        return

    now_ts = time.time()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    entry = {
        "reply": sanitized_reply,
        "tables": tables or [],
        "recommendations": recommendations or [],
        "extra": extra or {},
        "computed_at": now_ts,
        "key": cache_key,
    }

    # 1. Store in Tier 1 RAM
    with _memory_lock:
        _memory_cache[cache_key] = entry
        prune_memory_cache()

    # 2. Store in Tier 2 Supabase market_cache Table (cross-instance, survives restarts)
    def _bg_upsert():
        if is_test_environment():
            return
        try:
            from api.stock_ai import _init_supabase, supabase
            _init_supabase()
            supabase.table("market_cache").upsert({
                "cache_key": cache_key,
                "country": "Egypt",
                "payload": {
                    "reply": sanitized_reply,
                    "tables": tables or [],
                    "recommendations": recommendations or [],
                    "extra": extra or {},
                },
                "computed_at": now_iso,
            }).execute()
            logger.info(f"[analysis_cache] Saved to Tier 2 market_cache: {cache_key}")
        except Exception as e:
            logger.warning(f"[analysis_cache] Tier 2 upsert error for {cache_key}: {e}")

    threading.Thread(target=_bg_upsert, daemon=True).start()


# Backward compatibility aliases
extract_canonical_cache_key = build_analysis_cache_key
get_cached_analysis = lambda query, user_id=None, images=None: (
    get_vip_analysis_cache(build_analysis_cache_key(query, images), user_id)
)
set_cached_analysis = lambda query, reply, tables=None, recommendations=None, images=None: (
    set_vip_analysis_cache(build_analysis_cache_key(query, images), reply, tables, recommendations)
    if build_analysis_cache_key(query, images) else None
)
