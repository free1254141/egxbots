"""
api/agentic_chat/analysis_cache.py
High-performance In-Memory Response Cache for the Python Agentic Chatbot.

Caches canonical, non-personalized Egyptian Stock Exchange analyses:
- Single stock analyses (e.g. "حلل فوري", "سعر التجاري الدولي COMI").
- Market status & index overview (e.g. "حالة السوق", "وضع البورصة اليوم").
- Wyckoff institutional accumulation scans (e.g. "أسهم التجميع", "تجميع وايكوف").
- Open algorithm recommendations (e.g. "التوصيات المفتوحة", "ترشيحات الشراء").

Rules:
1. Strict privacy: Personal/portfolio questions ("محفظتي", "أسهمي", "اشتريت", "بعت") NEVER touch the cache.
2. Multimodal exclusion: Messages with attached images NEVER touch the cache.
3. Session-aware TTL:
   - During live EGX trading session (Sun-Thu 10:00 - 14:30 Cairo): 15 minutes TTL.
   - Outside trading session (post-close after 17:15 Cairo): valid until next trading session opens (10:00 AM).
   - Maximum retention: 36 hours.
4. Zero-token, 0ms CPU delivery on cache hit.
"""

from __future__ import annotations

import datetime as dt
import re
import threading
import time
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from api.stock_aliases import resolve_stock_symbol, ARABIC_STOCK_MAPPINGS

CAIRO_TZ = ZoneInfo("Africa/Cairo")
LIVE_SESSION_TTL_SECONDS = 15 * 60  # 15 minutes during live trading
OFF_HOURS_TTL_SECONDS = 36 * 3600  # Up to 36 hours during weekends / off-hours
MAX_CACHE_ENTRIES = 500

_cache_store: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()

# Personal & state-mutating keywords that strictly bypass the cache
PERSONAL_KEYWORDS = (
    "محفظت", "محفظة", "اسهمي", "أسهمي", "مراكز", "اشتريت", "بعت",
    "متوسط شراء", "رصيدي", "شراء سهم", "بيع سهم", "اضف", "أضف",
    "احذف", "حذف", "عدل", "تعديل", "تصفية"
)


def get_cairo_now() -> dt.datetime:
    try:
        return dt.datetime.now(CAIRO_TZ)
    except Exception:
        return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)


def is_egx_live_session(now_cairo: dt.datetime) -> bool:
    """Returns True if currently inside EGX live trading session (Sun-Thu 10:00 - 14:30 Cairo)."""
    # Python weekday: Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    # EGX trading days: Sun(6), Mon(0), Tue(1), Wed(2), Thu(3)
    if now_cairo.weekday() not in {6, 0, 1, 2, 3}:
        return False
    current_minutes = now_cairo.hour * 60 + now_cairo.minute
    return (10 * 60) <= current_minutes < (14 * 60 + 30)


def is_cache_entry_valid(entry: Dict[str, Any], now_cairo: dt.datetime) -> bool:
    """Determines whether a cached response is still fresh enough to be served."""
    computed_at = entry.get("computed_at", 0.0)
    age_seconds = time.time() - computed_at

    if age_seconds < 0:
        return False  # Clock skew guard
    if age_seconds < LIVE_SESSION_TTL_SECONDS:
        return True
    if age_seconds > OFF_HOURS_TTL_SECONDS:
        return False

    # If currently in live trading, never serve anything older than 15 minutes
    if is_egx_live_session(now_cairo):
        return False

    # Outside live trading: check if computed after today's (or last session's) 17:15 close job
    try:
        computed_dt = dt.datetime.fromtimestamp(computed_at, tz=CAIRO_TZ)
        is_after_close = (computed_dt.hour * 60 + computed_dt.minute) >= (17 * 60 + 15)

        if is_after_close:
            # 1. On the same evening: valid all night
            if computed_dt.date() == now_cairo.date():
                return True
            # 2. On the next calendar day: valid in the morning before market opens at 10:00 AM
            if now_cairo.date() == computed_dt.date() + dt.timedelta(days=1):
                return (now_cairo.hour * 60 + now_cairo.minute) < (10 * 60)
            # 3. Weekend (Fri=4, Sat=5): valid all weekend until next trading session
            if now_cairo.weekday() in {4, 5}:
                return True
            # 4. Sunday morning before 10:00 AM: valid if computed Thursday post-close
            if now_cairo.weekday() == 6 and (now_cairo.hour * 60 + now_cairo.minute) < (10 * 60):
                return True
    except Exception:
        pass

    return age_seconds < (60 * 60)  # Default 1 hour fallback outside session


def extract_canonical_cache_key(query: str, images: Optional[List[str]] = None) -> Optional[str]:
    """
    Extracts a canonical cache key for repeatable public questions.
    Returns None if the query is conversational, personal, or multimodal.
    """
    if images and len(images) > 0:
        return None

    norm = " " + re.sub(r"[^\w\s]", " ", query.lower()).strip() + " "
    if any(k in norm for k in PERSONAL_KEYWORDS):
        return None

    # 1. Market Overview Intent
    if any(m in norm for m in (" حالة السوق ", " وضع السوق ", " المؤشر العام ", " اخبار البورصة ", " أخبار البورصة ", " egx30 ")):
        return "market:overview"

    # 2. Wyckoff Accumulation Intent
    if any(w in norm for w in (" اسهم التجميع ", " أسهم التجميع ", " تجميع وايكوف ", " السيولة الذكية ", " اقوى اسهم التجميع ", " أقوى أسهم التجميع ")):
        return "wyckoff:accumulation"

    # 3. Open Recommendations Intent
    if any(r in norm for r in (" التوصيات المفتوحة ", " ترشيحات الشراء ", " توصيات اليوم ", " الصفقات المفتوحة ", " صفقات اليوم ")):
        return "recommendations:open"

    # 4. Single Stock Analysis Intent
    # Search for English ticker symbol
    latin_words = re.findall(r"\b[A-Za-z]{2,8}\b", query)
    found_sym = None
    for w in latin_words:
        upper = w.upper()
        if upper not in {"THE", "AND", "FOR", "BUY", "SELL", "BOT", "EGX", "VIP", "AI", "CHAT"}:
            resolved = resolve_stock_symbol(upper)
            if resolved:
                found_sym = resolved
                break

    # Search for Arabic stock name
    if not found_sym:
        for ar_name, sym in ARABIC_STOCK_MAPPINGS.items():
            if f" {ar_name.lower()} " in norm or norm.startswith(f" {ar_name.lower()} "):
                found_sym = sym
                break

    if found_sym:
        # Check if the query is an analysis or price request
        # (Exclude complex questions with multi-condition filters or comparison)
        if any(c in norm for c in (" مقارنة ", " قارن ", " انهي احسن ", " انهي أفضل ")):
            return None
        return f"stock:{found_sym.upper()}"

    return None


def get_cached_analysis(query: str, images: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Retrieves a valid cached analysis if available."""
    cache_key = extract_canonical_cache_key(query, images)
    if not cache_key:
        return None

    now_cairo = get_cairo_now()
    with _cache_lock:
        entry = _cache_store.get(cache_key)
        if not entry:
            return None

        if is_cache_entry_valid(entry, now_cairo):
            return {
                "key": cache_key,
                "reply": entry["reply"],
                "tables": list(entry.get("tables") or []),
                "recommendations": list(entry.get("recommendations") or []),
                "computed_at": entry["computed_at"],
            }
        else:
            # Stale entry
            _cache_store.pop(cache_key, None)
            return None


def set_cached_analysis(
    query: str,
    reply: str,
    tables: Optional[List[Any]] = None,
    recommendations: Optional[List[Any]] = None,
    images: Optional[List[str]] = None,
) -> None:
    """Saves a generated analysis into the in-memory cache if eligible."""
    if not reply or len(reply) < 50:
        return
    # Guard against error messages being cached
    if any(err_word in reply for err_word in ("تعذر الاتصال", "حدث خطأ", "غير متاح حالياً")):
        return

    cache_key = extract_canonical_cache_key(query, images)
    if not cache_key:
        return

    with _cache_lock:
        # Prune oldest if store exceeds capacity
        if len(_cache_store) >= MAX_CACHE_ENTRIES:
            oldest_key = min(_cache_store.keys(), key=lambda k: _cache_store[k].get("computed_at", 0))
            _cache_store.pop(oldest_key, None)

        _cache_store[cache_key] = {
            "reply": reply,
            "tables": list(tables or []),
            "recommendations": list(recommendations or []),
            "computed_at": time.time(),
        }


def clear_analysis_cache() -> None:
    """Clears the in-memory analysis cache completely."""
    with _cache_lock:
        _cache_store.clear()
