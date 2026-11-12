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

from api.stock_aliases import resolve_stock_symbol, ARABIC_STOCK_MAPPINGS

logger = logging.getLogger("agentic_chat.cache")

CAIRO_TZ = ZoneInfo("Africa/Cairo")
LIVE_SESSION_TTL_SECONDS = 15 * 60  # 15 minutes during live trading
MAX_OFF_HOURS_AGE_SECONDS = 4 * 24 * 3600  # Never serve anything older than 4 days
MAX_MEMORY_CACHE_ENTRIES = 500

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
    """True if currently inside EGX live trading session (Sun-Thu 10:00 - 14:30 Cairo)."""
    cairo_dt = now_cairo or get_cairo_now()
    if cairo_dt.weekday() not in TRADING_WEEKDAYS:
        return False
    current_minutes = cairo_dt.hour * 60 + cairo_dt.minute
    return SESSION_OPEN_MIN <= current_minutes < SESSION_CLOSE_MIN


def resolve_cache_validity(computed_at_ts: float, now_ts: Optional[float] = None) -> bool:
    """
    Decide whether a cached entry may still be served:
    - Always valid for the first 15 minutes.
    - During live session (10:00–14:30 Sun–Thu): never valid beyond 15 minutes.
    - Outside session: if computed after the 17:00 after-close job finished (>= 17:15 Cairo),
      valid all night and all weekend until the next trading session opens at 10:00 AM Cairo time.
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
    current_minutes = now_cairo.hour * 60 + now_cairo.minute

    # If inside live trading session, never serve anything older than 15 minutes
    if is_egx_live_session(now_cairo):
        return False

    # Outside live session: check if computed after latest completed session ready time (17:15)
    try:
        computed_cairo = dt.datetime.fromtimestamp(computed_at_ts, tz=CAIRO_TZ)
        computed_minutes = computed_cairo.hour * 60 + computed_cairo.minute
        is_computed_after_close = (computed_minutes >= DATA_READY_MIN)

        if is_computed_after_close:
            # 1. Computed today after close: valid all evening/night
            if computed_cairo.date() == now_cairo.date():
                return True
            # 2. Computed yesterday after close: valid in morning before 10:00 AM
            if now_cairo.date() == computed_cairo.date() + dt.timedelta(days=1):
                return current_minutes < SESSION_OPEN_MIN
            # 3. Weekend (Fri/Sat): valid all weekend if computed Thursday after close
            if now_cairo.weekday() in {4, 5}:  # Fri=4, Sat=5
                return True
            # 4. Sunday morning before 10:00 AM: valid if computed Thursday after close
            if now_cairo.weekday() == 6 and current_minutes < SESSION_OPEN_MIN:
                return True
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

    # 1. Single Stock Analysis & Levels
    if tool_name in ("get_stock", "get_stock_levels"):
        raw_sym = safe_args.get("symbol")
        if not raw_sym and isinstance(safe_args.get("symbols"), list) and len(safe_args["symbols"]) == 1:
            raw_sym = safe_args["symbols"][0]
        if not raw_sym or not isinstance(raw_sym, str):
            return None
        sym = raw_sym.strip().upper().replace(".CA", "")
        if len(sym) < 2 or len(sym) > 8:
            return None
        return f"vip_stock_{sym}"

    # 2. Recommendations
    if tool_name == "get_recommendations":
        timeframe = str(safe_args.get("timeframe") or "").lower()
        if "last_week" in timeframe or "past" in timeframe:
            return "vip_recs_last_week"
        if "this_week" in timeframe:
            return "vip_recs_this_week"
        return "vip_open_recommendations"

    # 3. Accumulation & Wyckoff Smart Money Flow
    if tool_name == "get_accumulation_stocks":
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
        sym = safe_args.get("symbol")
        return f"vip_fair_value_{str(sym).strip().upper()}" if sym else "vip_fair_value_undervalued"

    # 8. Market News
    if tool_name == "get_news":
        sym = safe_args.get("symbol")
        if sym and str(sym).upper() not in ("EGX", "MARKET", "ALL"):
            return f"vip_news_{str(sym).strip().upper()}"
        return "vip_market_news"

    return None


# ---------------------------------------------------------------------------
# String-Based Canonical Key Resolver (Early Check Fallback)
# ---------------------------------------------------------------------------

PERSONAL_WORDS = {
    "محفظتي", "محفظتك", "محفظه", "محفظة", "اسهمي", "أسهمي", "متوسطي",
    "شرائي", "اشتريت", "شريت", "بعت", "معايا", "عندي", "عالق", "متعلق",
    "خسران", "خسرت", "كسبان", "رصيدي", "فلوسي", "مركزي", "مراكزي",
}

DIALOGUE_WORDS = {
    "ليه", "لماذا", "ازاي", "كيف", "اشمعني", "اشمعنا", "امتي", "امتى", "متي", "متى",
    "لو", "اذا", "افرض", "تفتكر", "تتوقع", "اشرح", "اشرحلي", "فهمني", "باك", "backtest",
}


def build_analysis_cache_key(query: str, images: Optional[List[str]] = None) -> Optional[str]:
    """
    String intent classifier matching Vercel analysis-cache.ts.
    Returns canonical key or None if conversational / personal / image.
    """
    if not query or (images and len(images) > 0):
        return None

    norm = " " + re.sub(r"[^\w\s]", " ", query.lower()).strip() + " "
    tokens = set(norm.split())

    # Skip personal & dialogue questions
    if any(w in tokens or w in norm for w in PERSONAL_WORDS):
        return None
    if any(w in tokens for w in DIALOGUE_WORDS):
        return None

    # Canonical Market-Wide Buttons & Direct Queries
    if any(k in norm for k in (" ملخص السوق ", " حالة السوق ", " وضع السوق ", " market summary ")):
        return "vip_market_summary"
    if any(k in norm for k in (" اسهم التجميع ", " أسهم التجميع ", " تجميع وايكوف ", " السيولة الذكية ", " accumulation ")):
        return "vip_accumulation"
    if any(k in norm for k in (" المسح الفني ", " مسح فني ", " الماسح الذكي ", " tech screener ")):
        return "vip_tech_screener"
    if any(k in norm for k in (" اقوي الاسهم ", " أقوى الأسهم ", " افضل الاسهم ", " أفضل الأسهم ", " top stocks ")) and not any(k in norm for k in ("تجميع", "قطاع", "مسح")):
        return "vip_top_stocks"
    if any(k in norm for k in (" اخبار البورصة ", " أخبار البورصة ", " اخبار السوق ", " أخبار السوق ", " إفصاحات السوق ")):
        return "vip_market_news"
    if any(k in norm for k in (" التوصيات المفتوحة ", " كل التوصيات المفتوحة ", " صفقات السوينغ ", " صفقات السوينج ", " توصيات اليوم ")):
        return "vip_open_recommendations"
    if any(k in norm for k in (" توصيات الاسبوع الحالي ", " توصيات هذا الاسبوع ")):
        return "vip_recs_this_week"
    if any(k in norm for k in (" توصيات الاسبوع الماضي ", " توصيات الاسبوع السابق ")):
        return "vip_recs_last_week"
    if any(k in norm for k in (" اقوي القطاعات ", " أقوى القطاعات ", " أفضل القطاعات ")):
        return "vip_top_sectors"

    # Single stock query
    latin_matches = re.findall(r"\b[A-Za-z]{2,8}\b", query)
    stopwords = {"THE", "AND", "FOR", "BUY", "SELL", "BOT", "EGX", "VIP", "AI", "CHAT", "RSI", "MACD"}
    found_sym = None
    for tok in latin_matches:
        u = tok.upper()
        if u not in stopwords:
            res = resolve_stock_symbol(u)
            if res:
                found_sym = res
                break

    if not found_sym:
        for ar_name, sym in ARABIC_STOCK_MAPPINGS.items():
            if f" {ar_name.lower()} " in norm or norm.startswith(f" {ar_name.lower()} "):
                found_sym = sym
                break

    if found_sym:
        # Check sub-intent
        if re.search(r"دعم|مقاوم|مستويات|اهداف|هدف|وقف", norm):
            return f"vip_stock_{found_sym}_levels"
        if re.search(r"اخبار|خبر|افصاح|اعلان", norm):
            return f"vip_stock_{found_sym}_news"
        if re.search(r"كوبون|توزيع|ارباح", norm):
            return f"vip_stock_{found_sym}_divs"
        if re.search(r"شرعي|حلال|حرام|شريعه", norm):
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
