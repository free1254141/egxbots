"""High-frequency public & authenticated API routes hosted on Hugging Face.

Replaces Vercel Serverless Function invocations for symbols search, countries,
candles, chart markers, recommendations, user quota, analytics events, and
batch intraday gain checks using bounded LRU+TTL caching and SingleFlight coalescing.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import math
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple
import urllib.error
from urllib.parse import urljoin, urlparse
import urllib.request

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from api.payment_common import is_payments_enabled
from api.perf_utils import (
    BoundedTTLCache,
    SingleFlight,
    get_cairo_date_str,
    get_market_exchange,
    get_market_exchanges,
    get_market_supabase,
    get_primary_supabase,
    is_unlimited_chat_user,
    normalize_market_hint,
    resolve_request_market,
    resolve_subscription_quota_window,
    resolve_verified_viewer,
)
from api.plan_limits import effective_limits
from api.saudi_stock_aliases import SAUDI_STOCK_NAMES_AR, is_saudi_symbol
from api.stock_aliases import ARABIC_STOCK_MAPPINGS
from api.symbols_local import list_countries, search_symbols

router = APIRouter()

_DAY_MS = 86400000
_FREE_ENCRYPTED_OPEN_RETURN_PCT = 50.0
_SAUDI_TICKER_RE = re.compile(r"^\d{4}(\.(sr|sa|tadawul))?$", re.IGNORECASE)
_EGX_SUFFIX_RE = re.compile(r"\.ca$", re.IGNORECASE)
_SYMBOL_PARAM_RE = re.compile(r"^[A-Z0-9._-]{1,20}$")
_EXCHANGE_PARAM_RE = re.compile(r"^[A-Z0-9._-]{1,12}$")
_META_KEY_RE = re.compile(r"^[a-zA-Z0-9_:-]{1,50}$")
_FUND_TICKER_RE = re.compile(r"^[A-Z0-9_-]{1,24}(?:\.[A-Z0-9_-]{1,12})?$")
_DISCLOSURE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REMOVED_EXCHANGES = frozenset({"binance", "crypto", "forex", "lse", "indx", "index", "indices"})
_INDEX_SYMBOLS = frozenset({
    "EGX30", "EGX70", "EGX100", "EGX30CAPPED", "EGX33", "TAMAYUZ",
    "TASI", "NOMU", "MT30", "DFMGI", "FADX15", "FADGI", "QSI", "GNRI",
})
_MARKET_ALLOWED_EXCHANGES = {
    "egx": frozenset({"egx"}),
    "tasi": frozenset({"tadawul"}),
    "uae": frozenset({"dfm", "adx"}),
    "qatar": frozenset({"qse"}),
}
_MARKET_CURRENCY_MAP = {"egx": "EGP", "tasi": "SAR", "uae": "AED", "qatar": "QAR"}
_ARABIC_LETTER_RE = re.compile(r"[\u0600-\u06FF]")
_ALLOWED_EVENTS = frozenset({"page_view", "feature_use"})

_RUN_TO_RUN_TTL = 86400.0

_SYMBOLS_CACHE = BoundedTTLCache(max_entries=64, default_ttl=_RUN_TO_RUN_TTL)
_SYMBOLS_SF = SingleFlight()
_COUNTRIES_CACHE = BoundedTTLCache(max_entries=8, default_ttl=_RUN_TO_RUN_TTL)
_COUNTRIES_SF = SingleFlight()
_MARKERS_CACHE = BoundedTTLCache(max_entries=256, default_ttl=_RUN_TO_RUN_TTL)
_MARKERS_SF = SingleFlight()
_RECS_CACHE = BoundedTTLCache(max_entries=16, default_ttl=_RUN_TO_RUN_TTL)
_RECS_SF = SingleFlight()
_CANDLES_CACHE = BoundedTTLCache(max_entries=256, default_ttl=_RUN_TO_RUN_TTL)
_CANDLES_SF = SingleFlight()
_FOUNDERS_CACHE = BoundedTTLCache(max_entries=2, default_ttl=900.0)
_FOUNDERS_SF = SingleFlight()
_QUOTA_CACHE = BoundedTTLCache(max_entries=512, default_ttl=15.0)
_QUOTA_SF = SingleFlight()
_MARKET_STATUS_CACHE = BoundedTTLCache(max_entries=8, default_ttl=_RUN_TO_RUN_TTL)
_MARKET_STATUS_SF = SingleFlight()
_PROOF_CACHE = BoundedTTLCache(max_entries=4, default_ttl=_RUN_TO_RUN_TTL)
_PROOF_SF = SingleFlight()
_FUNDAMENTALS_CACHE = BoundedTTLCache(max_entries=512, default_ttl=_RUN_TO_RUN_TTL)
_FUNDAMENTALS_SF = SingleFlight()
_REC_COUNTS_CACHE = BoundedTTLCache(max_entries=16, default_ttl=_RUN_TO_RUN_TTL)
_REC_COUNTS_SF = SingleFlight()
_SIG_PERF_CACHE = BoundedTTLCache(max_entries=4, default_ttl=_RUN_TO_RUN_TTL)
_SIG_PERF_SF = SingleFlight()
_SCAN_AI_CACHE = BoundedTTLCache(max_entries=16, default_ttl=_RUN_TO_RUN_TTL)
_SCAN_AI_SF = SingleFlight()
_DISCLOSURES_CACHE = BoundedTTLCache(max_entries=128, default_ttl=_RUN_TO_RUN_TTL)
_DISCLOSURES_SF = SingleFlight()
_PDF_CACHE = BoundedTTLCache(max_entries=12, default_ttl=3600.0)
_PDF_SF = SingleFlight()
_METALS_SERIES_CACHE = BoundedTTLCache(max_entries=4, default_ttl=_RUN_TO_RUN_TTL)
_METALS_SERIES_SF = SingleFlight()

_TAG_TO_CACHES: Dict[str, Tuple[Tuple[str, BoundedTTLCache], ...]] = {
    "daily-symbols": (
        ("symbols", _SYMBOLS_CACHE),
        ("countries", _COUNTRIES_CACHE),
        ("fundamentals", _FUNDAMENTALS_CACHE),
        ("metals_series", _METALS_SERIES_CACHE),
    ),
    "daily-market-data": (
        ("symbols", _SYMBOLS_CACHE),
        ("candles", _CANDLES_CACHE),
        ("market_status", _MARKET_STATUS_CACHE),
        ("metals_series", _METALS_SERIES_CACHE),
        ("fundamentals", _FUNDAMENTALS_CACHE),
        ("recommendations", _RECS_CACHE),
        ("signal_performance", _SIG_PERF_CACHE),
        ("scan_ai", _SCAN_AI_CACHE),
    ),
    "daily-recommendations": (
        ("markers", _MARKERS_CACHE),
        ("recommendations", _RECS_CACHE),
        ("candles", _CANDLES_CACHE),
        ("proof", _PROOF_CACHE),
        ("rec_counts", _REC_COUNTS_CACHE),
        ("signal_performance", _SIG_PERF_CACHE),
        ("scan_ai", _SCAN_AI_CACHE),
    ),
    "daily-disclosures": (
        ("disclosures", _DISCLOSURES_CACHE),
        ("disclosures_pdf", _PDF_CACHE),
    ),
}


def invalidate_offload_caches(tags: Optional[Iterable[str]] = None) -> List[str]:
    """Selectively clear in-memory HF caches for the refreshed daily tags."""
    if not tags:
        return []
    cleared: List[str] = []
    seen_ids = set()
    for tag in tags:
        for name, cache in _TAG_TO_CACHES.get(tag, ()):
            cid = id(cache)
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            cache.clear()
            cleared.append(name)
    return cleared


def clear_offload_caches() -> None:
    """Clear all module caches (for deterministic tests or forced refresh)."""
    for cache in (
        _SYMBOLS_CACHE,
        _COUNTRIES_CACHE,
        _MARKERS_CACHE,
        _RECS_CACHE,
        _CANDLES_CACHE,
        _FOUNDERS_CACHE,
        _QUOTA_CACHE,
        _MARKET_STATUS_CACHE,
        _PROOF_CACHE,
        _FUNDAMENTALS_CACHE,
        _REC_COUNTS_CACHE,
        _SIG_PERF_CACHE,
        _SCAN_AI_CACHE,
        _DISCLOSURES_CACHE,
        _PDF_CACHE,
        _METALS_SERIES_CACHE,
    ):
        cache.clear()


def _has_explicit_market_param(request: Request) -> bool:
    """True only when URL query explicitly supplies a recognized market/country/exchange hint."""
    return any(normalize_market_hint(request.query_params.get(k)) is not None for k in ("market", "country", "exchange"))


def _to_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == "":
        return default
    try:
        num = float(val)
        return num if math.isfinite(num) else default
    except (TypeError, ValueError):
        return default


def _parse_iso_ms(ts: Any) -> Optional[float]:
    if not ts:
        return None
    raw = str(ts).strip()
    if not raw:
        return None
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        raw = f"{raw}T00:00:00+00:00"
    elif raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt_val = datetime.fromisoformat(raw)
        if dt_val.tzinfo is None:
            dt_val = dt_val.replace(tzinfo=timezone.utc)
        return dt_val.timestamp() * 1000.0
    except Exception:
        return None


def _normalize_arabic(text: str) -> str:
    cleaned = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", text.lower())
    return (
        cleaned.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
        .strip()
    )


def _normalize_exchange(raw: Optional[str]) -> Optional[str]:
    val = (raw or "").strip().lower()
    if not val:
        return None
    if val in ("tasi", "sr", "tadawul"):
        return "tadawul"
    return val


def _build_egx_arabic_lookups() -> Tuple[Dict[str, str], Dict[str, Tuple[str, ...]]]:
    primary: Dict[str, str] = {}
    aliases_by_sym: Dict[str, List[str]] = {}
    for phrase, sym in ARABIC_STOCK_MAPPINGS.items():
        if not sym or not _ARABIC_LETTER_RE.search(phrase):
            continue
        sym_up = sym.strip().upper()
        norm_p = _normalize_arabic(phrase)
        if norm_p:
            bucket = aliases_by_sym.setdefault(sym_up, [])
            if norm_p not in bucket:
                bucket.append(norm_p)
        clean_disp = phrase.strip()
        if clean_disp.startswith("سهم ") or clean_disp.startswith("شركة "):
            continue
        prev = primary.get(sym_up, "")
        if len(clean_disp) > len(prev):
            primary[sym_up] = clean_disp
    return primary, {sym: tuple(vals) for sym, vals in aliases_by_sym.items()}


_EGX_PRIMARY_NAME_AR, _EGX_ARABIC_ALIASES = _build_egx_arabic_lookups()


def _daily_cdn_headers(tag: str) -> Dict[str, str]:
    return {
        "Cache-Control": "public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800",
        "Vercel-CDN-Cache-Control": "public, s-maxage=604800, stale-while-revalidate=2592000",
        "Vercel-Cache-Tag": tag,
    }


def _private_no_store_headers(tag: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "Cache-Control": "private, no-store, max-age=0",
        "Vercel-CDN-Cache-Control": "private, no-store",
    }
    if tag:
        headers["Vercel-Cache-Tag"] = tag
    return headers


def _safe_exec(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


# ---------------------------------------------------------------------------
# 1. Symbols Search & Countries
# ---------------------------------------------------------------------------

_UAE_SEARCH_HINTS = {"uae", "dfm", "adx", "united arab emirates", "ae", "dubai", "abudhabi", "abu dhabi", "emirates"}
_QATAR_SEARCH_HINTS = {"qatar", "qse", "qe", "qa", "doha", "qsi"}


def _resolve_gcc_search_market(request: Request, country: Optional[str], exchange: Optional[str]) -> Optional[str]:
    """Detect UAE (DFM/ADX) or Qatar (QSE) search scope. Explicit query params win over headers/cookies."""
    explicit = (request.query_params.get("market"), country, exchange)
    for raw in explicit:
        val = (raw or "").strip().lower()
        if not val:
            continue
        if val in _UAE_SEARCH_HINTS:
            return "uae"
        if val in _QATAR_SEARCH_HINTS:
            return "qatar"
        if normalize_market_hint(val) is not None or val == "tadawul":
            return None
    for raw in (
        request.headers.get("x-egxbots-market"),
        request.headers.get("x-market"),
        request.cookies.get("egxbots_market"),
        request.cookies.get("egx_market"),
    ):
        val = (raw or "").strip().lower()
        if not val:
            continue
        if val in _UAE_SEARCH_HINTS:
            return "uae"
        if val in _QATAR_SEARCH_HINTS:
            return "qatar"
    return None


def _load_market_symbols_dataset(market: str, country: Optional[str], exchange: Optional[str]) -> List[Dict[str, Any]]:
    cache_key = f"{market}:{country or ''}:{exchange or ''}"
    found, cached = _SYMBOLS_CACHE.get(cache_key)
    if found:
        return cached

    def _fetch() -> List[Dict[str, Any]]:
        if market in ("uae", "qatar"):
            sb = get_market_supabase("tasi")
            if sb is None:
                return []
            if market == "uae":
                exchanges_filter = [exchange.upper()] if exchange in ("dfm", "adx") else ["DFM", "ADX"]
                default_country = "UAE"
                default_currency = "AED"
            else:
                exchanges_filter = ["QSE"]
                default_country = "Qatar"
                default_currency = "QAR"
            target_exchange = exchanges_filter[0]
            for cols in (
                "symbol, exchange, name, name_ar, country, currency",
                "symbol, exchange, name, name_ar, country",
                "symbol, exchange, name, country",
            ):
                try:
                    res = (
                        sb.table("stocks")
                        .select(cols)
                        .eq("is_active", True)
                        .in_("exchange", exchanges_filter)
                        .limit(5000)
                        .execute()
                    )
                    rows = getattr(res, "data", None) or []
                    return [
                        {
                            "Symbol": r.get("symbol"),
                            "Exchange": r.get("exchange") or target_exchange,
                            "Name": r.get("name"),
                            "NameAr": r.get("name_ar") or "",
                            "Country": r.get("country") or default_country,
                            "Type": "Common Stock",
                            "Currency": r.get("currency") or default_currency,
                        }
                        for r in rows
                    ]
                except Exception:
                    continue
            return []

        sb = get_market_supabase(market)
        if sb is None:
            return []
        target_exchange = get_market_exchange(market)
        default_country = "Saudi Arabia" if market == "tasi" else "Egypt"
        default_currency = "SAR" if market == "tasi" else "EGP"

        if market == "tasi":
            candidates = list(dict.fromkeys([
                *(
                    [f"symbols_{country}", f"symbols_{country[:1].upper()}{country[1:]}", f"symbols_{country.upper()}"]
                    if country else []
                ),
                "symbols_Saudi Arabia",
                "symbols_Saudi",
                "symbols_TADAWUL",
                "symbols_TASI",
                "all_symbols_by_country",
            ]))
        elif country:
            candidates = list(dict.fromkeys([
                f"symbols_{country}",
                f"symbols_{country[:1].upper()}{country[1:]}",
                f"symbols_{country.upper()}",
            ]))
        else:
            candidates = ["all_symbols_by_country"]

        for ck in candidates:
            res = _safe_exec(
                lambda ck=ck: sb.table("market_cache").select("payload").eq("cache_key", ck).limit(1).execute()
            )
            rows = getattr(res, "data", None) or []
            if rows and isinstance(rows[0].get("payload"), list):
                return _enrich_and_filter_symbol_items(rows[0]["payload"], market)

        for cols in (
            "symbol, exchange, name, name_ar, country, currency",
            "symbol, exchange, name, name_ar, country",
            "symbol, exchange, name, country",
        ):
            try:
                q_builder = sb.table("stocks").select(cols).eq("is_active", True).limit(5000)
                if market == "tasi":
                    q_builder = q_builder.eq("exchange", target_exchange)
                else:
                    if country:
                        q_builder = q_builder.ilike("country", country)
                    if exchange:
                        q_builder = q_builder.ilike("exchange", exchange)
                res = q_builder.execute()
                rows = getattr(res, "data", None) or []
                mapped = [
                    {
                        "Symbol": r.get("symbol"),
                        "Exchange": r.get("exchange") or target_exchange,
                        "Name": r.get("name"),
                        "NameAr": r.get("name_ar") or "",
                        "Country": r.get("country") or default_country,
                        "Type": "Common Stock",
                        "Currency": r.get("currency") or default_currency,
                    }
                    for r in rows
                ]
                return _enrich_and_filter_symbol_items(mapped, market)
            except Exception:
                continue
        return []

    items = _SYMBOLS_SF.do(cache_key, _fetch)
    if items:
        _SYMBOLS_CACHE.set(cache_key, items)
    return items


def _enrich_and_filter_symbol_items(raw_items: List[Dict[str, Any]], market: str) -> List[Dict[str, Any]]:
    allowed_exs = _MARKET_ALLOWED_EXCHANGES.get(market)
    clean_items: List[Dict[str, Any]] = []
    for raw_item in raw_items:
        item = dict(raw_item)
        raw_sym = str(item.get("Symbol") or item.get("symbol") or item.get("Code") or "").strip()
        if not raw_sym:
            continue
        sym_base = re.sub(r"\.(sr|sa|tadawul|ca)$", "", raw_sym.lower()).upper()
        raw_name = str(item.get("Name") or item.get("name") or "")
        if sym_base in _INDEX_SYMBOLS or raw_name.startswith("Unknown ("):
            continue
        raw_ex = str(item.get("Exchange") or item.get("exchange") or "")
        ex = _normalize_exchange(raw_ex) or ""
        if ex in _REMOVED_EXCHANGES:
            continue
        if allowed_exs and ex and ex not in allowed_exs:
            continue
        raw_name_ar = str(item.get("NameAr") or item.get("name_ar") or item.get("arabic_name") or "").strip()
        if not raw_name_ar:
            if market == "egx":
                raw_name_ar = _EGX_PRIMARY_NAME_AR.get(sym_base, "")
            elif market == "tasi":
                raw_name_ar = SAUDI_STOCK_NAMES_AR.get(sym_base, "")
            if raw_name_ar:
                item["NameAr"] = raw_name_ar
        clean_items.append(item)
    return clean_items


@router.get("/api/symbols/search")
async def api_symbols_search(
    request: Request,
    q: str = Query(default="", max_length=64),
    country: Optional[str] = Query(default=None, max_length=64),
    exchange: Optional[str] = Query(default=None, max_length=24),
    limit: int = Query(default=25, ge=1, le=100000),
    source: str = Query(default="supabase"),
):
    """Unified EGX + TASI + UAE + Qatar symbols search backed by bounded LRU cache."""
    q_raw = q.strip()
    q_low = q_raw.lower()
    q_norm = _normalize_arabic(q_raw)
    norm_ex = _normalize_exchange(exchange)

    gcc_market = _resolve_gcc_search_market(request, country, norm_ex)
    looks_saudi = bool(_SAUDI_TICKER_RE.match(q_raw)) and not gcc_market
    explicit_egypt = bool(country and "egypt" in country.lower())
    hint = request.query_params.get("market") or country or exchange
    if gcc_market:
        market = gcc_market
    elif looks_saudi and not explicit_egypt and norm_ex != "egx":
        market = "tasi"
    else:
        market = resolve_request_market(request, hint)
    explicit_gcc_in_url = bool(
        gcc_market and any(request.query_params.get(k) for k in ("market", "country", "exchange"))
    )
    explicit_in_url = _has_explicit_market_param(request) or looks_saudi or explicit_gcc_in_url
    resp_headers = (
        {
            "Cache-Control": "public, max-age=30",
            "Vercel-CDN-Cache-Control": (
                "public, s-maxage=60, stale-while-revalidate=120"
                if limit > 1000
                else "public, s-maxage=600, stale-while-revalidate=1800"
            ),
            "Vary": "X-Egxbots-Market",
        }
        if explicit_in_url
        else {**_private_no_store_headers(), "Vary": "Cookie, X-Egxbots-Market"}
    )

    if market == "egx" and source == "local":
        results = search_symbols(q=q_raw, country=country, exchange=exchange, limit=limit)
        return JSONResponse({"results": results}, headers=resp_headers)

    all_items = _load_market_symbols_dataset(market, country, norm_ex)
    if not all_items and market == "egx":
        results = search_symbols(q=q_raw, country=country, exchange=exchange, limit=limit)
        return JSONResponse({"results": results}, headers=resp_headers)

    target_exchange = (
        "DFM" if market == "uae" else "QSE" if market == "qatar" else get_market_exchange(market)
    )
    default_country = (
        "UAE"
        if market == "uae"
        else "Qatar"
        if market == "qatar"
        else "Saudi Arabia"
        if market == "tasi"
        else "Egypt"
    )
    default_currency = (
        "AED"
        if market == "uae"
        else "QAR"
        if market == "qatar"
        else "SAR"
        if market == "tasi"
        else "EGP"
    )
    q_clean = re.sub(r"\.(sr|sa|tadawul|ca)$", "", q_low)
    allowed_exs = _MARKET_ALLOWED_EXCHANGES.get(market)

    ranked: List[Tuple[int, str, Dict[str, Any]]] = []
    for item in all_items:
        raw_sym = str(item.get("Symbol") or item.get("symbol") or item.get("Code") or "")
        if not raw_sym:
            continue
        sym = raw_sym.lower()
        sym_clean = re.sub(r"\.(sr|sa|tadawul|ca)$", "", sym)
        sym_base_up = sym_clean.upper()
        raw_name = str(item.get("Name") or item.get("name") or "")
        if sym_base_up in _INDEX_SYMBOLS or raw_name.startswith("Unknown ("):
            continue
        name = raw_name.lower()
        raw_name_ar = str(item.get("NameAr") or item.get("name_ar") or item.get("arabic_name") or "")
        if not raw_name_ar and market == "egx":
            raw_name_ar = _EGX_PRIMARY_NAME_AR.get(sym_base_up, "")
        elif not raw_name_ar and market == "tasi":
            raw_name_ar = SAUDI_STOCK_NAMES_AR.get(sym_base_up, "")
        name_ar_norm = _normalize_arabic(raw_name_ar)
        name_norm = _normalize_arabic(raw_name)
        aliases_ar = _EGX_ARABIC_ALIASES.get(sym_base_up, ()) if market == "egx" else ()
        raw_ex = str(item.get("Exchange") or item.get("exchange") or target_exchange)
        ex = _normalize_exchange(raw_ex) or ""
        if ex in _REMOVED_EXCHANGES:
            continue
        if allowed_exs and ex not in allowed_exs:
            continue
        if norm_ex and norm_ex not in ("uae", "qatar") and ex != norm_ex:
            continue

        matches = (
            not q_low
            or q_low in sym
            or (q_clean and q_clean in sym_clean)
            or q_low in name
            or (q_norm and (q_norm in name_norm or q_norm in name_ar_norm or any(q_norm in alias for alias in aliases_ar)))
        )
        if not matches:
            continue

        if not q_low or sym == q_low or (q_clean and sym_clean == q_clean):
            rank = 0
        elif sym.startswith(q_low) or (q_clean and sym_clean.startswith(q_clean)):
            rank = 1
        elif name.startswith(q_low) or (q_norm and (name_norm.startswith(q_norm) or name_ar_norm.startswith(q_norm))):
            rank = 2
        elif q_low in sym or (q_clean and q_clean in sym_clean):
            rank = 3
        else:
            rank = 4

        out_item: Dict[str, Any] = {
            "symbol": raw_sym,
            "exchange": raw_ex,
            "name": raw_name or raw_name_ar or raw_sym,
            "country": str(item.get("Country") or item.get("country") or country or default_country),
            "currency": str(item.get("Currency") or item.get("currency") or default_currency),
            "hasLocal": True,
        }
        if raw_name_ar:
            out_item["name_ar"] = raw_name_ar
        ranked.append((rank, raw_sym, out_item))

    if q_low:
        ranked.sort(key=lambda row: (row[0], row[1]))

    return JSONResponse({"results": [row[2] for row in ranked[:limit]]}, headers=resp_headers)


@router.get("/api/symbols/countries")
async def api_symbols_countries(source: str = Query(default="supabase")):
    """Cached canonical countries directory."""
    headers = _daily_cdn_headers("daily-symbols")
    if source == "local":
        return JSONResponse({"countries": list_countries()}, headers=headers)

    found, cached = _COUNTRIES_CACHE.get("countries")
    if found:
        return JSONResponse({"countries": cached}, headers=headers)

    def _load() -> List[str]:
        sb = get_primary_supabase()
        if sb is not None:
            res = _safe_exec(
                lambda: sb.table("stocks").select("country").not_.is_("country", "null").limit(5000).execute()
            )
            rows = getattr(res, "data", None) or []
            countries = sorted({str(r.get("country") or "").strip() for r in rows if r.get("country")})
            if countries:
                return countries
        return list_countries()

    countries = _COUNTRIES_SF.do("countries", _load)
    if countries:
        _COUNTRIES_CACHE.set("countries", countries)
    return JSONResponse({"countries": countries}, headers=headers)


# ---------------------------------------------------------------------------
# 2. Recommendations Chart Markers
# ---------------------------------------------------------------------------

def _load_chart_markers_raw(market: str, effective_exchange: str, symbol: str) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    cache_key = f"{effective_exchange}:{symbol}"
    found, cached = _MARKERS_CACHE.get(cache_key)
    if found:
        return cached

    def _fetch() -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        sb = get_market_supabase(market)
        if sb is None:
            raise RuntimeError("market supabase unavailable")
        scan_res = (
            sb.table("scan_results")
            .select("id,created_at,updated_at,status,signal,entry_price,exit_price,profit_loss_pct,last_close,target_price,stop_loss")
            .eq("symbol", symbol)
            .eq("exchange", effective_exchange)
            .eq("is_public", True)
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
        rows = [
            r for r in (getattr(scan_res, "data", None) or [])
            if str(r.get("status") or "").lower() != "cancelled"
        ]
        closed_ids = [str(r["id"]) for r in rows if str(r.get("status") or "").lower() in ("win", "loss")]
        exit_dates: Dict[str, str] = {}
        if closed_ids:
            ev_res = (
                sb.table("recommendation_events")
                .select("recommendation_id,created_at,new_values,telegram_status")
                .in_("recommendation_id", closed_ids)
                .eq("event_type", "recommendation_closed")
                .order("created_at", desc=True)
                .limit(500)
                .execute()
            )
            for ev in getattr(ev_res, "data", None) or []:
                rec_id = str(ev.get("recommendation_id") or "")
                if ev.get("telegram_status") != "sent" or not rec_id or rec_id in exit_dates:
                    continue
                new_vals = ev.get("new_values") if isinstance(ev.get("new_values"), dict) else {}
                rich = new_vals.get("rich_details") if isinstance(new_vals.get("rich_details"), dict) else {}
                ev_meta = rich.get("evaluation") if isinstance(rich.get("evaluation"), dict) else {}
                closed_on = ev_meta.get("closed_on")
                if isinstance(closed_on, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", closed_on):
                    exit_dates[rec_id] = closed_on
                elif ev.get("created_at"):
                    exit_dates[rec_id] = str(ev["created_at"])
        return rows, exit_dates

    result = _MARKERS_SF.do(cache_key, _fetch)
    _MARKERS_CACHE.set(cache_key, result)
    return result


@router.get("/api/recommendations/chart-markers")
async def api_recommendations_chart_markers(
    request: Request,
    symbol: str = Query(default=""),
    exchange: str = Query(default="EGX"),
    scope: Optional[str] = Query(default=None),
):
    """Per-symbol entry/exit chart markers with LRU caching and plan visibility gating."""
    sym = symbol.strip().upper()
    exch = exchange.strip().upper()
    if not _SYMBOL_PARAM_RE.match(sym) or not _EXCHANGE_PARAM_RE.match(exch):
        return JSONResponse({"markers": []}, status_code=400)

    is_authenticated = False
    unrestricted = False
    if scope != "public":
        viewer = resolve_verified_viewer(request)
        is_authenticated = viewer["authenticated"]
        unrestricted = is_authenticated and (not is_payments_enabled() or viewer["pro"])

    is_saudi_req = (
        exch in ("TADAWUL", "TASI", "SA")
        or is_saudi_symbol(sym)
        or resolve_request_market(request) == "tasi"
    )
    market = "tasi" if is_saudi_req else "egx"
    effective_exchange = "TADAWUL" if is_saudi_req else exch

    try:
        rows, exit_dates = _load_chart_markers_raw(market, effective_exchange, sym)
    except Exception as exc:
        print(f"[CHART_MARKERS] {exc}")
        return JSONResponse({"markers": []}, status_code=503)

    delay_days = int(os.getenv("FREE_SIGNAL_DELAY_DAYS", "15") or "15")
    cutoff_ms = datetime.now(timezone.utc).timestamp() * 1000.0 - delay_days * _DAY_MS

    visible: List[Dict[str, Any]] = []
    for row in rows:
        closed = str(row.get("status") or "").lower() in ("win", "loss")
        created_ms = _parse_iso_ms(row.get("created_at"))
        if created_ms is None:
            continue
        entry = _to_float(row.get("entry_price"), 0.0)
        last = _to_float(row.get("last_close"), 0.0)
        ret_pct = ((last - entry) / entry) * 100.0 if (entry > 0 and last > 0) else _to_float(row.get("profit_loss_pct"), 0.0)
        if unrestricted or (created_ms <= cutoff_ms and not closed and not (ret_pct > _FREE_ENCRYPTED_OPEN_RETURN_PCT)):
            visible.append(row)

    markers: List[Dict[str, Any]] = []
    recommendations: List[Dict[str, Any]] = []
    for row in visible:
        rec_id = str(row.get("id") or "")
        created_ms = _parse_iso_ms(row.get("created_at")) or 0.0
        entry = _to_float(row.get("entry_price"), 0.0)
        if entry > 0:
            markers.append({"id": rec_id, "kind": "entry", "time": int(created_ms // 1000), "price": entry})

        status_low = str(row.get("status") or "").lower()
        exit_date = exit_dates.get(rec_id) or row.get("updated_at")
        exit_ms = _parse_iso_ms(exit_date)
        exit_price = _to_float(row.get("exit_price"), 0.0)
        if status_low in ("win", "loss") and exit_ms is not None and exit_price > 0:
            markers.append({
                "id": rec_id,
                "kind": "exit",
                "time": int(exit_ms // 1000),
                "price": exit_price,
                "outcome": str(row.get("status") or ""),
            })

        recommendations.append({
            "id": rec_id,
            "created_at": row.get("created_at"),
            "status": row.get("status"),
            "signal": row.get("signal"),
            "entry_price": row.get("entry_price"),
            "exit_price": row.get("exit_price"),
            "exit_at": exit_dates.get(rec_id) or (row.get("updated_at") if status_low in ("win", "loss") else None),
            "profit_loss_pct": row.get("profit_loss_pct"),
            "target_price": row.get("target_price"),
            "stop_loss": row.get("stop_loss"),
        })

    explicit_market_in_url = (
        _has_explicit_market_param(request)
        or exch in ("TADAWUL", "TASI", "SA")
        or is_saudi_symbol(sym)
        or bool(_EGX_SUFFIX_RE.match(sym))
    )
    can_cdn_cache = (scope == "public") and explicit_market_in_url
    headers = (
        {**_daily_cdn_headers("daily-recommendations"), "Vary": "X-Egxbots-Market, Cookie, Authorization"}
        if can_cdn_cache
        else {**_private_no_store_headers("daily-recommendations"), "Vary": "X-Egxbots-Market, Cookie, Authorization"}
    )
    return JSONResponse({"markers": markers, "recommendations": recommendations}, headers=headers)


# ---------------------------------------------------------------------------
# 3. AI Bot Recommendations
# ---------------------------------------------------------------------------

def _apply_quotes(rows: List[Dict[str, Any]], quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest_by_sym: Dict[str, Dict[str, Any]] = {}
    for q in quotes:
        sym = str(q.get("symbol") or "").upper()
        if not sym or sym in latest_by_sym:
            continue
        latest_by_sym[sym] = q

    out = []
    for row in rows:
        item = dict(row)
        if str(item.get("status") or "").lower() == "open":
            q = latest_by_sym.get(str(item.get("symbol") or "").upper())
            if q and _to_float(q.get("close"), 0.0) > 0:
                item["last_close"] = _to_float(q["close"])
        out.append(item)
    return out


def _load_recommendations_bundle(market: str, exchange: str, limit: int) -> Dict[str, Any]:
    cache_key = f"{market}:{exchange}:{limit}"
    found, cached = _RECS_CACHE.get(cache_key)
    if found:
        return cached

    def _fetch() -> Dict[str, Any]:
        sb = get_market_supabase(market)
        if sb is None:
            raise RuntimeError("market supabase unavailable")
        rec_fields = (
            "id,batch_id,symbol,exchange,name,last_close,precision,signal,status,"
            "entry_price,target_price,stop_loss,is_public,created_at,updated_at,"
            "exit_price,profit_loss_pct,top_reasons,rich_details,adjustments"
        )
        qb = sb.table("scan_results").select(rec_fields).eq("is_public", True).eq("exchange", exchange)
        qb = qb.order("created_at", desc=True)
        if market == "tasi":
            qb = qb.order("precision", desc=True)
        rows = getattr(qb.limit(min(limit + 10, 250)).execute(), "data", None) or []
        rows = [r for r in rows if str(r.get("status") or "").lower() != "cancelled"][:limit]

        open_syms = sorted({str(r.get("symbol") or "") for r in rows if r.get("status") == "open" and r.get("symbol")})
        all_syms = sorted({str(r.get("symbol") or "") for r in rows if r.get("symbol")})

        def _fetch_quotes():
            if not open_syms:
                return []
            since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
            try:
                return (
                    getattr(
                        sb.table("stock_prices")
                        .select("symbol,exchange,date,close,volume,updated_at")
                        .eq("exchange", exchange)
                        .in_("symbol", open_syms)
                        .gte("date", since)
                        .order("date", desc=True)
                        .limit(6000)
                        .execute(),
                        "data",
                        None,
                    )
                    or []
                )
            except Exception:
                return (
                    getattr(
                        sb.table("stock_prices")
                        .select("symbol,exchange,date,close,volume")
                        .eq("exchange", exchange)
                        .in_("symbol", open_syms)
                        .gte("date", since)
                        .order("date", desc=True)
                        .limit(6000)
                        .execute(),
                        "data",
                        None,
                    )
                    or []
                )

        def _fetch_fundamentals():
            if not all_syms:
                return []
            return _safe_exec(
                lambda: getattr(
                    sb.table("stock_fundamentals").select("symbol,data").in_("symbol", all_syms).limit(max(len(all_syms), 1)).execute(),
                    "data",
                    None,
                )
                or [],
                [],
            )

        def _fetch_stock_meta():
            if market != "tasi" or not all_syms:
                return []
            for cols in ("symbol,name,name_ar,sector", "symbol,name,sector"):
                try:
                    return (
                        getattr(
                            sb.table("stocks")
                            .select(cols)
                            .eq("exchange", exchange)
                            .in_("symbol", all_syms)
                            .limit(len(all_syms))
                            .execute(),
                            "data",
                            None,
                        )
                        or []
                    )
                except Exception:
                    continue
            return []

        with ThreadPoolExecutor(max_workers=3) as pool:
            f_quotes = pool.submit(_fetch_quotes)
            f_fund = pool.submit(_fetch_fundamentals)
            f_meta = pool.submit(_fetch_stock_meta)
            quotes = f_quotes.result()
            fundamentals = f_fund.result()
            stock_meta = f_meta.result()

        rows_with_quotes = _apply_quotes(rows, quotes) if quotes else rows
        sector_map: Dict[str, Any] = {}
        for f in fundamentals:
            data_obj = f.get("data") if isinstance(f.get("data"), dict) else {}
            sec = data_obj.get("sector") or data_obj.get("Sector") or data_obj.get("industry")
            if f.get("symbol"):
                sector_map[str(f["symbol"])] = sec

        meta_map = {str(m["symbol"]): m for m in stock_meta if m.get("symbol")}
        return {"rows": rows_with_quotes, "sector_map": sector_map, "meta_map": meta_map}

    bundle = _RECS_SF.do(cache_key, _fetch)
    _RECS_CACHE.set(cache_key, bundle)
    return bundle


@router.get("/api/ai_bot/recommendations")
async def api_ai_bot_recommendations(
    request: Request,
    limit: int = Query(default=50),
    scope: Optional[str] = Query(default=None),
):
    """Serve public/Pro recommendations using 10m shared cache + per-user masking."""
    eff_limit = min(max(int(limit), 1), 200) if limit > 0 else 50
    market = resolve_request_market(request)
    exchange = get_market_exchange(market)
    currency = "SAR" if market == "tasi" else "EGP"

    is_public_scope = scope == "public"
    explicit_market_param = _has_explicit_market_param(request)
    if is_public_scope:
        authenticated, pro = False, False
    else:
        viewer = resolve_verified_viewer(request)
        authenticated, pro = viewer["authenticated"], viewer["pro"]

    can_cdn_cache = is_public_scope and explicit_market_param
    delayed_visibility = (not authenticated) or (is_payments_enabled() and not pro)
    delay_days = int(os.getenv("FREE_SIGNAL_DELAY_DAYS", "15") or "15")
    now_ms = datetime.now(timezone.utc).timestamp() * 1000.0
    cutoff_ms = now_ms - delay_days * _DAY_MS
    cutoff_iso = datetime.fromtimestamp(int(cutoff_ms // _DAY_MS) * 86400, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    try:
        bundle = _load_recommendations_bundle(market, exchange, eff_limit)
    except Exception as exc:
        print(f"ai_bot recommendations error: {exc}")
        return JSONResponse({"error": "Recommendations temporarily unavailable"}, status_code=503)

    rows = bundle["rows"]
    sector_map = bundle["sector_map"]
    meta_map = bundle["meta_map"]
    results: List[Dict[str, Any]] = []

    for row in rows:
        is_closed = str(row.get("status") or "").lower() in ("win", "loss")
        created_ms = _parse_iso_ms(row.get("created_at"))
        closed_at_ms = _parse_iso_ms(row.get("updated_at")) or created_ms
        fresh = created_ms is None or created_ms > cutoff_ms
        is_fresh_closed = closed_at_ms is None or closed_at_ms > cutoff_ms

        entry_p = _to_float(row.get("entry_price"), 0.0)
        last_c = _to_float(row.get("last_close"), 0.0)
        if is_closed:
            ret_pct = None if row.get("profit_loss_pct") is None else _to_float(row.get("profit_loss_pct"), 0.0)
        elif entry_p > 0 and last_c > 0:
            ret_pct = ((last_c - entry_p) / entry_p) * 100.0
        else:
            ret_pct = None if row.get("profit_loss_pct") is None else _to_float(row.get("profit_loss_pct"), 0.0)

        high_return_pro = (not is_closed) and (ret_pct is not None and ret_pct > _FREE_ENCRYPTED_OPEN_RETURN_PCT)
        locked = delayed_visibility and (not is_closed) and ((not authenticated or fresh) or high_return_pro)

        if locked:
            precision = _to_float(row.get("precision"), 0.0)
            score = lambda v: max(1, min(10, round(v)))
            stop_loss = _to_float(row.get("stop_loss"), 0.0)
            safety_rate = score(10 - abs((last_c - stop_loss) / last_c) * 20) if (last_c > 0 and stop_loss > 0) else 5
            end_at = closed_at_ms if (is_closed and closed_at_ms is not None) else now_ms
            age_days = int(max(0.0, end_at - created_ms) // _DAY_MS) if created_ms is not None else None
            results.append({
                "id": row.get("id"),
                "locked": True,
                "exchange": row.get("exchange") or exchange,
                "currency": currency,
                "signal": row.get("signal") or "BUY",
                "status": row.get("status") or "open",
                "precision": precision,
                "technical_score": score(precision * 10 - 0.5),
                "fundamental_score": score(precision * 10 - 0.8),
                "sentiment_score": score(precision * 10 - 1.2),
                "safety_rate": safety_rate,
                "profit_loss_pct": ret_pct,
                "high_return_pro": high_return_pro,
                "recommendation_age_days": age_days if high_return_pro else None,
                "created_at": row.get("created_at"),
                "delayed": True,
                "snapshot_cutoff": cutoff_iso,
            })
            continue

        closed_locked = delayed_visibility and is_closed and (fresh or is_fresh_closed)
        if closed_locked:
            results.append({
                "id": row.get("id"),
                "identity_locked": True,
                "exchange": row.get("exchange") or exchange,
                "currency": currency,
                "status": row.get("status"),
                "precision": _to_float(row.get("precision"), 0.0),
                "profit_loss_pct": _to_float(row.get("profit_loss_pct"), 0.0),
                "high_return_pro": False,
                "recommendation_age_days": None,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at") or row.get("created_at"),
                "delayed": False,
            })
            continue

        rich = row.get("rich_details") if isinstance(row.get("rich_details"), dict) else {}
        evaluation = rich.get("evaluation") if isinstance(rich.get("evaluation"), dict) else {}
        exit_reason = (
            {
                "exit_reason": evaluation.get("exit_reason"),
                "exit_reason_ar": evaluation.get("exit_reason_ar"),
                "exit_reason_en": evaluation.get("exit_reason_en"),
            }
            if is_closed
            else {}
        )
        sym = str(row.get("symbol") or "")
        meta = meta_map.get(sym, {})
        resolved_name = (
            str(meta.get("name_ar") or row.get("name") or meta.get("name") or sym)
            if market == "tasi"
            else row.get("name")
        )
        tasi_fields = {"name_ar": meta.get("name_ar") or resolved_name or None} if market == "tasi" else {}
        year_val = int(str(row.get("created_at"))[:4]) if row.get("created_at") and str(row.get("created_at"))[:4].isdigit() else None

        if authenticated:
            base = {**row, "exchange": row.get("exchange") or exchange, "name": resolved_name, **tasi_fields}
        else:
            base = {
                "id": row.get("id"),
                "symbol": row.get("symbol"),
                "exchange": row.get("exchange") or exchange,
                "name": resolved_name,
                **tasi_fields,
                "is_public": row.get("is_public"),
                "created_at": row.get("created_at"),
                **(
                    {
                        "status": row.get("status"),
                        "updated_at": row.get("updated_at"),
                        "entry_price": row.get("entry_price"),
                        "exit_price": row.get("exit_price"),
                        "profit_loss_pct": row.get("profit_loss_pct"),
                    }
                    if is_closed
                    else {}
                ),
                "anonymous": True,
            }

        results.append({
            **base,
            "currency": currency,
            "sector": sector_map.get(sym) or meta.get("sector") or "General",
            "year": year_val,
            "delayed": False,
            "snapshot_cutoff": None,
            "precision": _to_float(row.get("precision"), 0.0) if authenticated else None,
            "last_close": last_c if last_c > 0 else None,
            "top_reasons": row.get("top_reasons"),
            "adjustments": row.get("adjustments") if isinstance(row.get("adjustments"), list) else [],
            **exit_reason,
        })

    headers = {
        **(_daily_cdn_headers("daily-recommendations") if can_cdn_cache else _private_no_store_headers("daily-recommendations")),
        "Vary": "X-Egxbots-Market, Cookie, Authorization",
    }
    return JSONResponse(results, headers=headers)


# ---------------------------------------------------------------------------
# 4. AI Bot Candles (EGX + TASI)
# ---------------------------------------------------------------------------

def _load_tasi_candles_payload(
    symbol: str, exchange: str, bot_id: str, limit: int, market: str = "tasi"
) -> Dict[str, Any]:
    cache_key = f"{market}:{exchange}:{symbol}:{bot_id}:{limit}"
    found, cached = _CANDLES_CACHE.get(cache_key)
    if found:
        return cached

    exchanges = get_market_exchanges(market)
    currency = _MARKET_CURRENCY_MAP.get(market, "SAR")
    use_storage = limit > 220
    known_storage_ex = (
        exchange.upper()
        if (market == "uae" and exchange.upper() in ("DFM", "ADX"))
        else (None if market == "uae" else get_market_exchange(market))
    )

    def _fetch() -> Dict[str, Any]:
        sb = get_market_supabase(market)
        if sb is None:
            raise RuntimeError(f"{market.upper()} Supabase unavailable")
        db_limit = min(limit, 400) if use_storage else limit
        with ThreadPoolExecutor(max_workers=3) as pool:
            def _fetch_prices():
                price_q = (
                    sb.table("stock_prices")
                    .select("exchange,date,open,high,low,close,volume")
                    .eq("symbol", symbol)
                )
                price_q = (
                    price_q.in_("exchange", exchanges)
                    if market == "uae"
                    else price_q.eq("exchange", get_market_exchange(market))
                )
                return (
                    getattr(
                        price_q.order("date", desc=True).limit(db_limit).execute(),
                        "data",
                        None,
                    )
                    or []
                )

            def _fetch_storage():
                if not use_storage or not known_storage_ex:
                    return []
                from api.saudi_storage_history import load_storage_symbol_bars
                return load_storage_symbol_bars(sb, known_storage_ex, symbol)

            f_prices = pool.submit(_fetch_prices)
            f_storage = pool.submit(_fetch_storage)
            f_markers = pool.submit(
                lambda: _safe_exec(
                    lambda: getattr(
                        sb.table("bot_trades")
                        .select("timestamp,action,price,entry_price,pnl")
                        .eq("bot_id", bot_id)
                        .eq("symbol", symbol)
                        .order("timestamp", desc=False)
                        .limit(200)
                        .execute(),
                        "data",
                        None,
                    )
                    or [],
                    [],
                )
            )
            raw_prices = list(reversed(f_prices.result()))
            storage_bars = f_storage.result()
            raw_markers = f_markers.result()

        if use_storage and not known_storage_ex and market == "uae":
            from api.saudi_storage_history import load_storage_symbol_bars

            hint_ex = str((raw_prices[-1] if raw_prices else {}).get("exchange") or "").upper()
            candidates = [hint_ex] if hint_ex in ("DFM", "ADX") else ["DFM", "ADX"]
            for cand_ex in candidates:
                storage_bars = load_storage_symbol_bars(sb, cand_ex, symbol)
                if storage_bars:
                    break

        if storage_bars:
            from api.saudi_storage_history import merge_bars_storage_with_live
            raw_prices = merge_bars_storage_with_live(storage_bars, raw_prices)[-limit:]

        candles = []
        for c in raw_prices:
            ms = _parse_iso_ms(c.get("date"))
            if ms is None or ms <= 0:
                continue
            candles.append({
                "time": int(ms // 1000),
                "open": _to_float(c.get("open")),
                "high": _to_float(c.get("high")),
                "low": _to_float(c.get("low")),
                "close": _to_float(c.get("close")),
                "volume": _to_float(c.get("volume")),
            })

        markers = []
        for m in raw_markers:
            ms = _parse_iso_ms(m.get("timestamp"))
            if ms is None:
                continue
            action = str(m.get("action") or "").upper()
            pnl = m.get("pnl")
            pnl_suffix = ""
            if pnl not in (None, ""):
                try:
                    pnl_val = float(pnl)
                    if math.isfinite(pnl_val):
                        pnl_suffix = f" ({'+' if pnl_val > 0 else ''}{pnl_val:.1f}%)"
                except (TypeError, ValueError):
                    pnl_suffix = ""
            markers.append({
                "time": int(ms // 1000),
                "position": "belowBar" if action == "BUY" else "aboveBar",
                "color": "#10B981" if action == "BUY" else "#EF4444",
                "shape": "arrowUp" if action == "BUY" else "arrowDown",
                "text": f"{action}{pnl_suffix}",
                "action": m.get("action"),
                "price": m.get("price"),
            })
        return {"candles": candles, "markers": markers, "timeframe": "1d", "exchange": exchange, "currency": currency}

    payload = _CANDLES_SF.do(cache_key, _fetch)
    _CANDLES_CACHE.set(cache_key, payload)
    return payload


@router.get("/api/ai_bot/candles")
async def api_ai_bot_candles(
    request: Request,
    symbol: str = Query(default=""),
    exchange: str = Query(default=""),
    limit: Optional[int] = Query(default=None),
    all: Optional[str] = Query(default=None),
    bot_id: str = Query(default="primary"),
    include_markers: str = Query(default="true"),
):
    """Unified EGX + TASI candles endpoint eliminating Vercel cold-start functions."""
    raw_symbol = symbol.strip()
    if not raw_symbol:
        return JSONResponse({"candles": [], "markers": []}, status_code=400)

    raw_exch_upper = exchange.strip().upper()
    saudi_sym = bool(_SAUDI_TICKER_RE.match(raw_symbol) or re.match(r"^(\^)?TASI(\.SR)?$", raw_symbol, re.IGNORECASE))
    egx_suffix = bool(_EGX_SUFFIX_RE.match(raw_symbol))
    saudi_exch = raw_exch_upper in ("TADAWUL", "TASI", "SR")
    uae_exch = raw_exch_upper in ("DFM", "ADX", "UAE")
    qatar_exch = raw_exch_upper in ("QSE", "QATAR")
    if not saudi_sym and not egx_suffix and raw_exch_upper not in ("", "EGX", "TADAWUL", "TASI", "SR", "DFM", "ADX", "UAE", "QSE", "QATAR"):
        return JSONResponse(
            {"candles": [], "markers": [], "error": "Only EGX and GCC (TASI, DFM, ADX, QSE) market data is available."},
            status_code=410,
        )

    hint = request.query_params.get("market") or request.query_params.get("country") or (
        "TADAWUL" if saudi_exch else ("DFM" if uae_exch else ("QSE" if qatar_exch else ("EGX" if raw_exch_upper == "EGX" else None)))
    )
    market = (
        "tasi"
        if (saudi_sym or saudi_exch)
        else (
            "uae"
            if uae_exch
            else (
                "qatar"
                if qatar_exch
                else ("egx" if (egx_suffix or raw_exch_upper == "EGX") else resolve_request_market(request, hint))
            )
        )
    )
    if all == "true":
        eff_limit = min(max(int(limit or 5000), 1), 5000)
    else:
        raw_lim = 150 if limit is None else int(limit)
        eff_limit = min(max(raw_lim, 1), 5000 if raw_lim > 1000 else 1000)
    clean_symbol = re.sub(r"\.(SR|SA|TADAWUL|AE|DU|AD|QA)$", "", raw_symbol, flags=re.IGNORECASE).upper() if market != "egx" else raw_symbol
    explicit_in_url = (
        _has_explicit_market_param(request)
        or saudi_sym
        or saudi_exch
        or uae_exch
        or qatar_exch
        or egx_suffix
        or raw_exch_upper == "EGX"
    )
    headers = (
        {**_daily_cdn_headers("daily-market-data"), "Vary": "X-Egxbots-Market"}
        if explicit_in_url
        else {**_private_no_store_headers("daily-market-data"), "Vary": "Cookie, X-Egxbots-Market"}
    )
    with_markers = include_markers != "false"

    try:
        if market == "egx":
            from api.routers.bot import get_candles as bot_get_candles

            egx_key = f"egx:{clean_symbol}:{bot_id}:{eff_limit}"
            found, cached = _CANDLES_CACHE.get(egx_key)
            if not found:
                def _load_egx():
                    data = bot_get_candles(symbol=clean_symbol, bot_id=bot_id, limit=eff_limit, exchange="EGX")
                    if isinstance(data, dict):
                        _CANDLES_CACHE.set(egx_key, data)
                    return data

                payload = _CANDLES_SF.do(egx_key, _load_egx)
            else:
                payload = cached
            if isinstance(payload, dict) and not with_markers:
                payload = {**payload, "markers": []}
            return JSONResponse(payload, headers=headers)

        payload = _load_tasi_candles_payload(
            clean_symbol, raw_exch_upper or get_market_exchange(market), bot_id, eff_limit, market=market
        )
        if not with_markers:
            payload = {**payload, "markers": []}
        return JSONResponse(payload, headers=headers)
    except HTTPException as http_exc:
        return JSONResponse({"candles": [], "markers": [], "error": str(http_exc.detail)}, status_code=http_exc.status_code)
    except Exception as exc:
        print(f"Candles endpoint error: {exc}")
        return JSONResponse({"candles": [], "markers": []}, status_code=500)


# ---------------------------------------------------------------------------
# 5. User Quota & Founding Member Status
# ---------------------------------------------------------------------------

def _get_founder_uids(sb) -> List[str]:
    found, cached = _FOUNDERS_CACHE.get("top100")
    if found:
        return cached

    def _fetch() -> List[str]:
        res = _safe_exec(
            lambda: sb.table("subscriptions")
            .select("user_id, created_at")
            .eq("status", "active")
            .in_("plan_id", ["pro", "lifetime", "pro_lifetime"])
            .order("created_at", desc=False)
            .limit(200)
            .execute()
        )
        seen = set()
        ordered: List[str] = []
        for row in getattr(res, "data", None) or []:
            uid = str(row.get("user_id") or "")
            if uid and uid not in seen:
                seen.add(uid)
                ordered.append(uid)
                if len(ordered) >= 100:
                    break
        return ordered

    uids = _FOUNDERS_SF.do("top100", _fetch)
    _FOUNDERS_CACHE.set("top100", uids)
    return uids


@router.get("/api/user/quota")
async def api_user_quota(request: Request):
    """Compute authenticated user's plan, trial eligibility, and monthly quota in one parallel round-trip."""
    viewer = resolve_verified_viewer(request)
    if not viewer["authenticated"] or not viewer["user_id"]:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    uid = viewer["user_id"]
    email = viewer.get("email", "")
    found, cached = _QUOTA_CACHE.get(uid)
    if found:
        return JSONResponse(cached, headers=_private_no_store_headers())

    def _compute() -> Dict[str, Any]:
        sb = get_primary_supabase()
        if sb is None:
            raise RuntimeError("Supabase unavailable")

        cal_month_start = f"{get_cairo_date_str()[:7]}-01"
        with ThreadPoolExecutor(max_workers=8) as pool:
            f_subs = pool.submit(
                lambda: _safe_exec(
                    lambda: getattr(
                        sb.table("subscriptions")
                        .select("id, plan_id, status, current_period_start, current_period_end, created_at")
                        .eq("user_id", uid)
                        .in_("status", ["active", "trialing"])
                        .order("current_period_end", desc=True)
                        .limit(5)
                        .execute(),
                        "data",
                        None,
                    )
                    or [],
                    [],
                )
            )
            f_limits = pool.submit(
                lambda: _safe_exec(
                    lambda: getattr(
                        sb.table("ai_chatbot_limits")
                        .select("date, chat_count")
                        .eq("user_id", uid)
                        .order("date", desc=True)
                        .limit(1000)
                        .execute(),
                        "data",
                        None,
                    )
                    or [],
                    [],
                )
            )
            f_pos = pool.submit(
                lambda: _safe_exec(
                    lambda: getattr(
                        sb.table("positions")
                        .select("symbol")
                        .eq("user_id", uid)
                        .eq("status", "open")
                        .limit(500)
                        .execute(),
                        "data",
                        None,
                    )
                    or [],
                    [],
                )
            )
            f_trial = pool.submit(
                lambda: _safe_exec(
                    lambda: getattr(
                        sb.table("subscription_trials")
                        .select("started_at, expires_at")
                        .eq("user_id", uid)
                        .limit(1)
                        .execute(),
                        "data",
                        None,
                    )
                    or [],
                    [],
                )
            )
            f_bonus = pool.submit(
                lambda: _safe_exec(
                    lambda: getattr(sb.rpc("get_chat_bonus_balance", {"p_user_id": uid}).execute(), "data", 0) or 0,
                    0,
                )
            )
            f_profile = pool.submit(
                lambda: _safe_exec(
                    lambda: getattr(
                        sb.table("profiles").select("telegram_chat_id").eq("id", uid).limit(1).execute(),
                        "data",
                        None,
                    )
                    or [],
                    [],
                )
            )
            f_orders = pool.submit(
                lambda: _safe_exec(
                    lambda: getattr(
                        sb.table("local_payment_orders")
                        .select("id")
                        .eq("user_id", uid)
                        .eq("status", "approved")
                        .limit(1)
                        .execute(),
                        "data",
                        None,
                    )
                    or [],
                    [],
                )
            )
            f_founders = pool.submit(
                lambda: _safe_exec(
                    lambda: getattr(
                        sb.table("founders_offer_members").select("user_id").eq("user_id", uid).limit(1).execute(),
                        "data",
                        None,
                    )
                    or [],
                    [],
                )
            )

            sub_rows = f_subs.result()
            limit_rows = f_limits.result()
            pos_rows = f_pos.result()
            trial_rows = f_trial.result()
            bonus_balance = int(f_bonus.result() or 0)
            profile_rows = f_profile.result()
            orders_rows = f_orders.result()
            founder_rows = f_founders.result()

        is_unlimited = is_unlimited_chat_user(
            uid,
            email,
            email_confirmed=bool(viewer.get("email_confirmed", False)),
        )
        quota_win = resolve_subscription_quota_window(sub_rows)
        pro = quota_win["is_pro"] or is_unlimited
        has_chat_pro = quota_win.get("has_chat_pro", pro) or is_unlimited
        has_vip_access = quota_win.get("has_vip_access", pro) or is_unlimited
        if not is_payments_enabled():
            pro = True
            has_chat_pro = True
            has_vip_access = True
        active_sub = quota_win["active_sub"]
        month_start = quota_win["effective_month_start_str"]

        plan_id = str(active_sub.get("plan_id") or "").lower() if active_sub else ""
        if not pro:
            plan_name = "free"
        elif is_unlimited or plan_id in ("lifetime", "pro_lifetime"):
            plan_name = "lifetime"
        elif plan_id == "chat_only":
            plan_name = "chat_only"
        elif plan_id == "vip_only":
            plan_name = "vip_only"
        else:
            plan_name = "pro"
        limits = effective_limits(plan_name)

        chat_used = (
            sum(
                int(r.get("chat_count") or 0)
                for r in limit_rows
                if str(r.get("date") or "") >= month_start
            )
            if has_chat_pro
            else sum(int(r.get("chat_count") or 0) for r in limit_rows)
        )
        quota_period = "monthly" if has_chat_pro else "lifetime"
        chat_limit = int(limits["chat_messages_per_month"])
        unique_syms = {str(p.get("symbol") or "").strip().upper() for p in pos_rows if p.get("symbol")}
        portfolio_count = len(unique_syms)
        portfolio_limit = int(limits["portfolio_stocks"])

        is_founding = False
        founding_num = None
        if pro:
            founder_uids = _get_founder_uids(sb)
            if uid in founder_uids:
                is_founding = True
                founding_num = founder_uids.index(uid) + 1

        is_lifetime = plan_id in ("lifetime", "pro_lifetime")
        trial_row = trial_rows[0] if trial_rows else None
        trial_exp_ms = _parse_iso_ms(trial_row.get("expires_at")) if trial_row else None
        is_trial_active = bool(trial_exp_ms and trial_exp_ms > datetime.now(timezone.utc).timestamp() * 1000.0)
        is_trial = bool(
            (active_sub and (active_sub.get("status") == "trialing" or active_sub.get("provider") == "trial"))
            or is_trial_active
        )
        telegram_linked = bool(profile_rows and profile_rows[0].get("telegram_chat_id"))
        has_paid_before = bool(orders_rows or founder_rows)
        trial_eligible = (trial_row is None) and (not pro) and (not has_paid_before)

        plan_label = (
            "مدى الحياة VIP"
            if is_lifetime
            else (
                "تجربة Pro مجانية"
                if is_trial
                else (
                    "الشات الذكي (AI Chat)"
                    if plan_name == "chat_only"
                    else (
                        "رادار تليجرام VIP"
                        if plan_name == "vip_only"
                        else ("الباقة الشاملة Pro" if pro else "مجاني")
                    )
                )
            )
        )

        return {
            "ok": True,
            "plan": {
                "id": plan_name,
                "label": plan_label,
                "is_trial": is_trial,
                "trial_eligible": trial_eligible,
                "trial_expires_at": trial_row.get("expires_at") if trial_row else None,
                "is_pro": pro,
                "has_chat_pro": has_chat_pro,
                "has_vip_access": has_vip_access,
                "is_lifetime": is_lifetime,
                "status": (active_sub.get("status") or "active") if (pro and active_sub) else ("active" if pro else ("canceled" if active_sub else "none")),
                "current_period_end": active_sub.get("current_period_end") if active_sub else None,
                "created_at": active_sub.get("created_at") if active_sub else None,
                "is_founding_member": is_founding,
                "founding_member_number": founding_num,
                "bonus_credits": bonus_balance,
                "telegram_linked": telegram_linked,
            },
            "quota": {
                "chat_messages": {
                    "used": chat_used,
                    "limit": chat_limit,
                    "bonus_credits": bonus_balance,
                    "remaining": max(0, chat_limit - chat_used) + (0 if has_chat_pro else bonus_balance),
                    "percent": min(100, round((chat_used / max(1, chat_limit)) * 100)),
                    "period": quota_period,
                },
                "portfolio_stocks": {
                    "used": portfolio_count,
                    "limit": portfolio_limit,
                    "remaining": max(0, portfolio_limit - portfolio_count),
                    "percent": min(100, round((portfolio_count / max(1, portfolio_limit)) * 100)),
                },
                "signals": {
                    "delay_days": int(limits["signal_delay_days"]),
                    "is_instant": int(limits["signal_delay_days"]) == 0,
                },
            },
        }

    try:
        payload = _QUOTA_SF.do(uid, _compute)
        _QUOTA_CACHE.set(uid, payload)
        return JSONResponse(payload, headers=_private_no_store_headers())
    except Exception as exc:
        print(f"[api/user/quota] error: {exc}")
        return JSONResponse({"ok": False, "error": "Quota temporarily unavailable"}, status_code=500)


# ---------------------------------------------------------------------------
# 6. Analytics Events Telemetry Ingestion
# ---------------------------------------------------------------------------

def _clean_metadata(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    cleaned: Dict[str, Any] = {}
    for key, item in list(value.items())[:12]:
        k_str = str(key)
        if not _META_KEY_RE.match(k_str):
            continue
        if isinstance(item, bool):
            cleaned[k_str] = item
        elif isinstance(item, (int, float)) and math.isfinite(float(item)):
            cleaned[k_str] = item
        elif isinstance(item, str):
            cleaned[k_str] = item[:240]
    return cleaned


@router.post("/api/analytics/events")
async def api_analytics_events(request: Request):
    """Ingest authenticated user activity events on HF instead of Vercel Functions."""
    viewer = resolve_verified_viewer(request)
    if not viewer["authenticated"] or not viewer["user_id"]:
        return JSONResponse({"ok": False}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    event_name = str(body.get("event_name") or "")
    if event_name not in _ALLOWED_EVENTS:
        return JSONResponse({"ok": False}, status_code=400)

    path = str(body.get("path") or "")[:180]
    if not path.startswith("/"):
        return JSONResponse({"ok": False}, status_code=400)

    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"ok": False, "unavailable": True}, status_code=202)

    try:
        sb.table("user_activity_events").insert({
            "user_id": viewer["user_id"],
            "session_id": (str(body.get("session_id") or "")[:100]) or None,
            "event_name": event_name,
            "path": path,
            "metadata": _clean_metadata(body.get("metadata")),
        }).execute()
        return {"ok": True}
    except Exception as exc:
        print(f"[activity] event insert skipped: {exc}")
        return JSONResponse({"ok": False, "unavailable": True}, status_code=202)


# ---------------------------------------------------------------------------
# 7. Batch Intraday Session Gains (POST parity)
# ---------------------------------------------------------------------------

@router.post("/api/scanner/intraday-session")
async def api_scanner_intraday_session_batch(request: Request):
    """Batch compute intraday post-signal peak gains directly on HF."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    date_str = str(body.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10]
    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        return {"ok": True, "gains": {}}

    from api.main import get_scanner_intraday_session
    import json as _json

    gains: Dict[str, Dict[str, Any]] = {}
    limited_items = items[:40]

    def _resolve_one(item: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
        if not isinstance(item, dict):
            return None
        clean_sym = str(item.get("symbol") or "").strip().upper().replace(".CA", "").replace(".EGX", "")
        if not clean_sym:
            return None
        try:
            sig_time = item.get("signal_time")
            sig_price = _to_float(item.get("signal_price"), 0.0) or None
            resp = get_scanner_intraday_session(
                symbol=clean_sym,
                date=date_str,
                to_date=None,
                signal_time=str(sig_time) if sig_time else None,
                signal_price=sig_price,
            )
            payload = _json.loads(resp.body.decode("utf-8")) if hasattr(resp, "body") else (resp if isinstance(resp, dict) else None)
            sig = payload.get("signal") if isinstance(payload, dict) else None
            if isinstance(sig, dict):
                return clean_sym, {
                    "max_gain_pct": sig.get("max_gain_pct"),
                    "peak_price": payload.get("session_high"),
                    "peak_time": payload.get("peak_time"),
                    "session_high": payload.get("session_high"),
                }
        except Exception:
            return None
        return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        for res in pool.map(_resolve_one, limited_items):
            if res:
                gains[res[0]] = res[1]

    return {"ok": True, "gains": gains}


# ---------------------------------------------------------------------------
# 8. Market Status, Proof, Fundamentals, Recommendation Counts & Signal Stats
# ---------------------------------------------------------------------------

def _compute_tasi_trend_regime(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not points:
        return {"regime": "sideways", "tasiReturn": 0.0, "rejectBuys": False}
    latest = points[-1]
    prev = points[-2] if len(points) >= 2 else None
    latest_close = _to_float(latest.get("close"), 0.0)
    prev_close = _to_float(prev.get("close"), 0.0) if prev else 0.0
    ret_raw = latest.get("ret")
    if prev and prev_close > 0:
        tasi_ret = (latest_close - prev_close) / prev_close
    elif ret_raw is not None:
        r_num = _to_float(ret_raw, 0.0)
        tasi_ret = (r_num / 100.0) if abs(r_num) > 1.0 else r_num
    else:
        tasi_ret = 0.0

    def _avg_close(chunk: List[Dict[str, Any]]) -> float:
        return (sum(_to_float(p.get("close"), 0.0) for p in chunk) / len(chunk)) if chunk else latest_close

    sma20 = _avg_close(points[-20:])
    sma50 = _avg_close(points[-50:])
    regime = "sideways"
    if tasi_ret <= -0.025:
        regime = "panic"
    elif latest_close > sma20 * 1.005 and sma20 >= sma50 * 0.995:
        regime = "trending_up"
    elif latest_close < sma20 * 0.995 and sma20 <= sma50 * 1.005:
        regime = "trending_down"
    return {
        "regime": regime,
        "tasiReturn": tasi_ret,
        "rejectBuys": regime in ("panic", "trending_down"),
    }


def _load_metals_series() -> Dict[str, List[Dict[str, Any]]]:
    """Load recent XAUUSD (Gold) and XAGUSD (Silver) daily bars once and cache across all 4 markets."""
    found, cached = _METALS_SERIES_CACHE.get("global_metals")
    if found:
        return cached

    def _fetch_metals() -> Dict[str, List[Dict[str, Any]]]:
        sb = get_market_supabase("tasi")
        if sb is None:
            return {"gold": [], "silver": []}
        rows = _safe_exec(
            lambda: getattr(
                sb.table("stock_prices")
                .select("symbol,date,open,high,low,close,volume")
                .eq("exchange", "COMMODITIES")
                .in_("symbol", ["XAUUSD", "XAGUSD"])
                .order("date", desc=True)
                .limit(520)
                .execute(),
                "data",
                None,
            )
            or [],
            [],
        )
        by_sym: Dict[str, Dict[str, Dict[str, Any]]] = {"XAUUSD": {}, "XAGUSD": {}}
        for r in rows:
            sym = str(r.get("symbol") or "").strip().upper()
            if sym not in by_sym:
                continue
            d = str(r.get("date") or "")[:10]
            close = _to_float(r.get("close"), 0.0)
            if not d or close <= 0:
                continue
            by_sym[sym][d] = {
                "date": d,
                "open": _to_float(r.get("open"), close),
                "high": _to_float(r.get("high"), close),
                "low": _to_float(r.get("low"), close),
                "close": close,
                "volume": _to_float(r.get("volume"), 0.0),
            }
        gold = [by_sym["XAUUSD"][d] for d in sorted(by_sym["XAUUSD"].keys())]
        silver = [by_sym["XAGUSD"][d] for d in sorted(by_sym["XAGUSD"].keys())]
        return {"gold": gold, "silver": silver}

    payload = _METALS_SERIES_SF.do("global_metals", _fetch_metals)
    if payload.get("gold") or payload.get("silver"):
        _METALS_SERIES_CACHE.set("global_metals", payload)
    return payload


def _build_index_series(rows: List[Dict[str, Any]], default_source: str) -> List[Dict[str, Any]]:
    ordered = []
    for r in reversed(rows or []):
        close = _to_float(r.get("close"), 0.0)
        if close <= 0:
            continue
        ordered.append({
            "date": r.get("date"),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 0,
            "ret": None if r.get("ret") is None else _to_float(r.get("ret"), 0.0),
            "source": r.get("source") or default_source,
        })
    return ordered


def _load_market_status_payload(market: str) -> Dict[str, Any]:
    found, cached = _MARKET_STATUS_CACHE.get(market)
    if found:
        return cached

    def _fetch() -> Dict[str, Any]:
        sb = get_market_supabase(market)
        if sb is None:
            raise RuntimeError("Market Supabase unavailable")
        exchange = get_market_exchange(market)
        metals = _load_metals_series()

        if market == "uae":
            idx_res = (
                sb.table("market_index")
                .select("exchange,date,close,ret,source")
                .in_("exchange", ["DFM", "ADX"])
                .order("date", desc=True)
                .limit(730)
                .execute()
            )
            raw_rows = getattr(idx_res, "data", None) or []
            dfm_rows = [r for r in raw_rows if str(r.get("exchange") or "").upper() == "DFM"]
            adx_rows = [r for r in raw_rows if str(r.get("exchange") or "").upper() == "ADX"]
            dfm_series = _build_index_series(dfm_rows, "DFM")
            adx_series = _build_index_series(adx_rows, "ADX")
            primary_series = dfm_series or adx_series
            if not primary_series:
                raise RuntimeError("UAE market status snapshot is missing")
            trend = _compute_tasi_trend_regime(primary_series)
            return {
                "dfm": dfm_series,
                "adx": adx_series,
                "tasi": [],
                "egx30": [],
                "egx100": [],
                "usdegp": [],
                "gold": metals["gold"],
                "silver": metals["silver"],
                "regime": trend["regime"],
                "tasi_return": trend["tasiReturn"],
                "reject_buys": trend["rejectBuys"],
                "updated_at": primary_series[-1].get("date") or datetime.now(timezone.utc).isoformat(),
                "market": "uae",
                "exchange": "DFM",
                "currency": "AED",
            }

        if market == "qatar":
            idx_res = (
                sb.table("market_index")
                .select("date,close,ret,source")
                .eq("exchange", "QSE")
                .order("date", desc=True)
                .limit(365)
                .execute()
            )
            qse_series = _build_index_series(getattr(idx_res, "data", None) or [], "QSE")
            if not qse_series:
                raise RuntimeError("Qatar market status snapshot is missing")
            trend = _compute_tasi_trend_regime(qse_series)
            return {
                "qse": qse_series,
                "tasi": [],
                "egx30": [],
                "egx100": [],
                "usdegp": [],
                "gold": metals["gold"],
                "silver": metals["silver"],
                "regime": trend["regime"],
                "tasi_return": trend["tasiReturn"],
                "reject_buys": trend["rejectBuys"],
                "updated_at": qse_series[-1].get("date") or datetime.now(timezone.utc).isoformat(),
                "market": "qatar",
                "exchange": "QSE",
                "currency": "QAR",
            }

        cache_key = "market_status_Saudi Arabia" if market == "tasi" else "market_status_Egypt"
        res = sb.table("market_cache").select("payload").eq("cache_key", cache_key).limit(1).execute()
        rows = getattr(res, "data", None) or []
        raw_payload = rows[0].get("payload") if rows else None

        if market == "egx":
            if not raw_payload:
                raise RuntimeError("Market status snapshot is missing")
            payload = json.loads(raw_payload) if isinstance(raw_payload, str) else dict(raw_payload)
            safe_payload = {
                **payload,
                "egx30": payload.get("egx30") if isinstance(payload.get("egx30"), list) else [],
                "egx100": payload.get("egx100") if isinstance(payload.get("egx100"), list) else [],
                "usdegp": payload.get("usdegp") if isinstance(payload.get("usdegp"), list) else [],
                "gold": metals["gold"],
                "silver": metals["silver"],
            }
            if not safe_payload["usdegp"]:
                usd_res = _safe_exec(
                    lambda: getattr(
                        sb.table("stock_prices")
                        .select("date,open,high,low,close,volume")
                        .eq("symbol", "USDEGP")
                        .order("date", desc=True)
                        .limit(365)
                        .execute(),
                        "data",
                        None,
                    )
                    or [],
                    [],
                )
                if usd_res:
                    safe_payload["usdegp"] = [
                        {
                            "date": r.get("date"),
                            "open": _to_float(r.get("open")),
                            "high": _to_float(r.get("high")),
                            "low": _to_float(r.get("low")),
                            "close": _to_float(r.get("close")),
                            "volume": _to_float(r.get("volume")),
                        }
                        for r in reversed(usd_res)
                    ]
            return safe_payload

        cached_payload: Optional[Dict[str, Any]] = None
        if raw_payload:
            try:
                parsed = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
                if isinstance(parsed, dict):
                    cached_payload = parsed
            except Exception:
                cached_payload = None

        if cached_payload and isinstance(cached_payload.get("tasi"), list) and cached_payload["tasi"]:
            return {
                **cached_payload,
                "tasi": cached_payload["tasi"],
                "egx30": cached_payload.get("egx30") if isinstance(cached_payload.get("egx30"), list) else [],
                "egx100": cached_payload.get("egx100") if isinstance(cached_payload.get("egx100"), list) else [],
                "usdegp": cached_payload.get("usdegp") if isinstance(cached_payload.get("usdegp"), list) else [],
                "gold": metals["gold"],
                "silver": metals["silver"],
                "market": "tasi",
                "exchange": exchange,
                "currency": "SAR",
            }

        idx_res = (
            sb.table("market_index")
            .select("date,close,ret,source")
            .eq("exchange", "TADAWUL")
            .order("date", desc=True)
            .limit(365)
            .execute()
        )
        ordered = _build_index_series(getattr(idx_res, "data", None) or [], "TADAWUL")
        if not ordered:
            raise RuntimeError("TASI market status snapshot is missing")
        trend = _compute_tasi_trend_regime(ordered)
        base = cached_payload or {}
        return {
            **base,
            "tasi": ordered,
            "egx30": [],
            "egx100": [],
            "usdegp": [],
            "gold": metals["gold"],
            "silver": metals["silver"],
            "regime": base.get("regime") or trend["regime"],
            "tasi_return": base["tasi_return"] if "tasi_return" in base else trend["tasiReturn"],
            "reject_buys": base["reject_buys"] if "reject_buys" in base else trend["rejectBuys"],
            "updated_at": base.get("updated_at") or ordered[-1].get("date") or datetime.now(timezone.utc).isoformat(),
            "market": "tasi",
            "exchange": exchange,
            "currency": "SAR",
        }

    payload = _MARKET_STATUS_SF.do(market, _fetch)
    _MARKET_STATUS_CACHE.set(market, payload)
    return payload


@router.get("/api/market/status")
async def api_market_status(request: Request):
    """Market index/FX status snapshot offloaded from Vercel."""
    market = resolve_request_market(request)
    explicit_market = _has_explicit_market_param(request)
    headers = (
        {**_daily_cdn_headers("daily-market-data"), "Vary": "X-Egxbots-Market"}
        if explicit_market
        else {**_private_no_store_headers("daily-market-data"), "Vary": "Cookie, X-Egxbots-Market"}
    )
    try:
        return JSONResponse(_load_market_status_payload(market), headers=headers)
    except Exception as exc:
        print(f"[api/market/status] error: {exc}")
        return JSONResponse({"error": "Market status temporarily unavailable"}, status_code=503, headers=_private_no_store_headers())


@router.get("/api/market/proof")
async def api_market_proof(request: Request):
    """Aggregate public recommendation track-record counts offloaded from Vercel."""
    market = resolve_request_market(request)
    explicit_market = _has_explicit_market_param(request)
    headers = (
        {
            "Cache-Control": "public, max-age=3600",
            "Vercel-CDN-Cache-Control": "public, s-maxage=86400, stale-while-revalidate=86400",
            "Vercel-Cache-Tag": "daily-recommendations",
            "Vary": "X-Egxbots-Market",
        }
        if explicit_market
        else {**_private_no_store_headers("daily-recommendations"), "Vary": "Cookie, X-Egxbots-Market"}
    )

    found, cached = _PROOF_CACHE.get(market)
    if found:
        return JSONResponse(cached, headers=headers)

    def _fetch() -> Dict[str, Any]:
        sb = get_market_supabase(market)
        if sb is None:
            raise RuntimeError("Supabase unavailable")
        exchange = get_market_exchange(market)

        def _count(status_filter: Optional[str] = None) -> int:
            qb = sb.table("scan_results").select("id", count="exact").eq("is_public", True).eq("exchange", exchange)
            if status_filter:
                qb = qb.eq("status", status_filter)
            res = qb.limit(1).execute()
            c = getattr(res, "count", None)
            if c is None:
                c = len(getattr(res, "data", None) or [])
            return int(c or 0)

        with ThreadPoolExecutor(max_workers=4) as pool:
            f_all = pool.submit(_count, None)
            f_wins = pool.submit(_count, "win")
            f_losses = pool.submit(_count, "loss")
            f_cancelled = pool.submit(_count, "cancelled")
            total = max(0, f_all.result() - f_cancelled.result())
            wins = f_wins.result()
            losses = f_losses.result()

        closed = wins + losses
        return {
            "recommendations": total,
            "closed": closed,
            "win_rate": round((wins / closed) * 100) if closed > 0 else None,
        }

    try:
        stats = _PROOF_SF.do(market, _fetch)
        _PROOF_CACHE.set(market, stats)
        return JSONResponse(stats, headers=headers)
    except Exception:
        return JSONResponse({"recommendations": None, "closed": None, "win_rate": None}, headers=_private_no_store_headers())


@router.get("/api/market/fundamentals")
async def api_market_fundamentals(ticker: str = Query(default="")):
    """Per-symbol fundamentals lookup with 30m LRU + 24h CDN caching."""
    clean = ticker.strip().upper()
    if not _FUND_TICKER_RE.match(clean):
        return JSONResponse({"error": "Invalid ticker"}, status_code=400)

    parts = clean.split(".", 1)
    sym = parts[0]
    exch_part = parts[1] if len(parts) > 1 else ""
    market = "tasi" if (is_saudi_symbol(sym) or exch_part in ("SR", "SA", "TADAWUL", "TASI")) else "egx"
    db_exchange = "TADAWUL" if market == "tasi" and exch_part in ("SR", "SA", "TADAWUL", "TASI") else exch_part
    cache_key = f"{market}:{sym}:{db_exchange}"

    cdn_headers = {"Cache-Control": "public, max-age=3600, s-maxage=86400, stale-while-revalidate=86400"}
    found, cached = _FUNDAMENTALS_CACHE.get(cache_key)
    if found:
        return JSONResponse(cached, headers=cdn_headers)

    def _fetch() -> Dict[str, Any]:
        sb = get_market_supabase(market)
        if sb is None:
            raise RuntimeError("Supabase unavailable")
        qb = sb.table("stock_fundamentals").select("data,fund_score,updated_at").eq("symbol", sym).order("updated_at", desc=True).limit(1)
        if db_exchange:
            qb = qb.eq("exchange", db_exchange)
        res = qb.execute()
        rows = getattr(res, "data", None) or []
        return {"data": rows[0].get("data") if rows else None}

    try:
        payload = _FUNDAMENTALS_SF.do(cache_key, _fetch)
        _FUNDAMENTALS_CACHE.set(cache_key, payload)
        return JSONResponse(payload, headers=cdn_headers)
    except Exception:
        return JSONResponse({"error": "Fundamentals unavailable"}, status_code=503)


@router.get("/api/market/recommendation-counts")
async def api_market_recommendation_counts(from_param: Optional[str] = Query(default=None, alias="from")):
    """Daily public recommendation counts aggregated with bounded pagination + 30m LRU cache."""
    from_date = (
        from_param
        if (from_param and _ISO_DATE_RE.match(from_param))
        else (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
    )
    headers = _daily_cdn_headers("daily-recommendations")
    found, cached = _REC_COUNTS_CACHE.get(from_date)
    if found:
        return JSONResponse(cached, headers=headers)

    def _fetch() -> Dict[str, Any]:
        sb = get_primary_supabase()
        if sb is None:
            raise RuntimeError("Supabase unavailable")
        daily_counts: Dict[str, int] = {}
        page_size = 1000
        for page in range(25):
            offset = page * page_size
            res = (
                sb.table("scan_results")
                .select("created_at,status")
                .eq("is_public", True)
                .eq("exchange", "EGX")
                .gte("created_at", f"{from_date}T00:00:00")
                .order("created_at", desc=False)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            rows = getattr(res, "data", None) or []
            for row in rows:
                if str(row.get("status") or "").lower() == "cancelled":
                    continue
                d = str(row.get("created_at") or "")[:10]
                if _ISO_DATE_RE.match(d):
                    daily_counts[d] = daily_counts.get(d, 0) + 1
            if len(rows) < page_size:
                break
        return {"from": from_date, "daily_counts": daily_counts}

    try:
        payload = _REC_COUNTS_SF.do(from_date, _fetch)
        _REC_COUNTS_CACHE.set(from_date, payload)
        return JSONResponse(payload, headers=headers)
    except Exception as exc:
        print(f"[MARKET_RECOMMENDATION_COUNTS] {exc}")
        return JSONResponse({"error": "Recommendation counts are temporarily unavailable"}, status_code=503)


@router.get("/api/scan/signal-performance")
async def api_scan_signal_performance():
    """Cached EGX intraday signal performance stats."""
    headers = _daily_cdn_headers("daily-market-data")
    found, cached = _SIG_PERF_CACHE.get("signal_performance_EGX")
    if found:
        return JSONResponse(cached, headers=headers)

    def _fetch() -> Optional[Dict[str, Any]]:
        sb = get_primary_supabase()
        if sb is None:
            raise RuntimeError("Supabase unavailable")
        res = (
            sb.table("market_cache")
            .select("payload,computed_at")
            .eq("cache_key", "signal_performance_EGX")
            .order("computed_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        if rows and isinstance(rows[0].get("payload"), dict):
            return rows[0]["payload"]
        return None

    try:
        payload = _SIG_PERF_SF.do("signal_performance_EGX", _fetch)
        if not payload:
            return JSONResponse({"ok": False, "message": "Signal performance stats are not yet computed."}, status_code=404)
        _SIG_PERF_CACHE.set("signal_performance_EGX", payload)
        return JSONResponse(payload, headers=headers)
    except Exception as exc:
        print(f"[SIGNAL_PERFORMANCE] {exc}")
        return JSONResponse({"ok": False, "error": "Signal performance service temporarily unavailable."}, status_code=503)


@router.post("/api/scan/ai")
async def api_scan_ai(
    request: Request,
    limit: int = Query(default=50),
    min_precision: float = Query(default=0.6),
):
    """Market-scoped AI scanner snapshot offloaded from Vercel Functions."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    body_dict = body if isinstance(body, dict) else {}
    hint = str(body_dict.get("market") or body_dict.get("country") or body_dict.get("exchange") or "") or None
    market = resolve_request_market(request, hint)
    exchange = get_market_exchange(market)
    eff_limit = min(max(int(limit), 1), 100) if limit > 0 else 50
    eff_prec = max(0.0, min(1.0, float(min_precision)))
    cache_key = f"{market}:{exchange}:{eff_limit}:{eff_prec:.2f}"

    found, cached = _SCAN_AI_CACHE.get(cache_key)
    if found:
        return cached

    def _fetch() -> Dict[str, Any]:
        sb = get_market_supabase(market)
        if sb is None:
            raise RuntimeError("Supabase unavailable")
        cols = (
            "symbol,exchange,name,last_close,precision,signal,top_reasons,council_score,consensus_ratio"
            if market == "tasi"
            else "symbol,exchange,name,last_close,precision,signal,top_reasons,rich_details"
        )
        res = (
            sb.table("scan_results")
            .select(cols)
            .eq("exchange", exchange)
            .gte("precision", eff_prec)
            .order("precision", desc=True)
            .limit(eff_limit)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        results = []
        for s in rows:
            prec = _to_float(s.get("precision"), 0.0)
            rich = s.get("rich_details") if isinstance(s.get("rich_details"), dict) else {}
            council_raw = s.get("council_score") if s.get("council_score") is not None else rich.get("council_score")
            consensus_raw = s.get("consensus_ratio") if s.get("consensus_ratio") is not None else rich.get("consensus_ratio")
            results.append({
                "symbol": s.get("symbol"),
                "exchange": s.get("exchange"),
                "name": s.get("name") or s.get("symbol"),
                "last_close": _to_float(s.get("last_close")),
                "precision": prec,
                "signal": s.get("signal") or "HOLD",
                "confidence": "High" if prec >= 0.8 else ("Medium" if prec >= 0.6 else "Low"),
                "top_reasons": s.get("top_reasons") or [],
                "council_score": _to_float(council_raw),
                "consensus_ratio": consensus_raw,
            })
        return {"results": results, "scanned_count": len(results)}

    try:
        payload = _SCAN_AI_SF.do(cache_key, _fetch)
        _SCAN_AI_CACHE.set(cache_key, payload)
        return payload
    except Exception as exc:
        print(f"AI scan API error: {exc}")
        return JSONResponse({"error": "Failed to perform AI scan"}, status_code=500)


# ---------------------------------------------------------------------------
# 9. EGX/TASI Disclosures Listing & SSRF-Safe PDF Proxy
# ---------------------------------------------------------------------------

_EGX_DISCLOSURE_SECTORS: Dict[str, Tuple[str, ...]] = {
    "banking_finance": (
        "COMI", "HRHO", "PRMH", "NAHO", "CCAP", "CICH", "CIEB", "EGBE", "FAIT", "ADIB",
        "SAUD", "SAIB", "QNBE", "HDBK", "EXPA", "BTFH", "CNFN", "OFH", "EHDR", "GPIM",
        "ZMID", "AALR", "ICID", "DCRC", "SEIG", "PRDC", "TYCN", "VALU", "UNIT", "ADRI",
        "ACAP", "AIH", "AFDI", "ANFI", "ASPI", "ATLC", "BONY", "CANA", "COPR", "EALR",
        "EASB", "EMFD", "ELSH", "EIUD", "ELKA", "GPPL", "GRCA", "ICLE", "KRDI", "KWIN",
        "FIRE", "ARAB", "ODIN", "EBSC", "DEIN", "BINV", "AMIA", "AIDC", "FAITA", "VLMR",
        "SEIGA", "CPME", "TWSA", "DAPH",
    ),
    "real_estate": (
        "TMGH", "PHDC", "DSCW", "ACRO", "SMCR", "SCCD", "AGIG", "AIND", "PHTV", "MHOT",
        "HELI", "ORHD", "AMER", "ROTO", "SDTI", "TALM", "IDRE", "MASR", "MAAL", "RTVC",
        "RREI", "UTOP", "EITP", "CIRA", "MENA", "NARE", "NCCW", "OBRI", "RMTV", "SPHT",
        "SMPP", "UBEE", "WKOL", "CAED", "CCRS", "GOCO", "GGCC", "GIHD", "ELWA", "MPRC",
        "TOUR", "ORAS", "HBCO", "OCDI", "EGSA",
    ),
    "chemicals_fertilizers": (
        "MFPC", "ABUK", "FERC", "ICFC", "AMOC", "SKPC", "EFIC", "RKAZ", "EPPK", "BIDI",
        "MPCO", "AIVCB", "APSW", "EGCH", "NEDA", "PACH", "IFAP", "ISMA", "KZPC", "MOSC",
        "SCFM", "EPCO", "POUL", "ZEOT", "APPC", "MEPA", "WCDF", "UNIP", "MEGM", "SUGR",
        "MICH", "MILS", "NCGC", "RAKT", "SNFC", "SPIN", "UEFM", "WATP", "ACGC", "CEFM",
        "ELNA", "GTWL",
    ),
    "industrial_manufacturing": (
        "SWDY", "EEII", "MTIE", "ORWE", "ACAMD", "AMII", "IEEC", "EGAL", "IRON", "CERA",
        "FNAR", "TORA", "SUCE", "SVCE", "INEG", "ISMQ", "ALUM", "ENGC", "GDWA", "ALEX",
        "LCSW", "ARCC", "CRST", "ELEC", "RUBX", "ARVA", "ATQA", "AREH", "ASCM", "ECAP",
        "MCQE", "MBSC", "SMFR", "ESRS", "IRAX", "SCEM", "NDRL",
    ),
    "telecom_tech": ("ETEL", "FWRY", "RAYA", "EFIH", "FTNS", "AMPI", "VERT", "DGTZ", "GTHE", "OIH"),
    "healthcare_pharma": (
        "ISPH", "ADCI", "AMES", "RMDA", "CLHO", "UPMS", "MIPH", "CPCI", "MPCI", "PHAR",
        "OCPH", "MCRO", "NIPH", "SIPC", "SPMD", "AXPH", "PHGC",
    ),
    "consumer_food": (
        "UFMH", "GTEX", "DOMT", "JUFO", "EAST", "EDFM", "IBCT", "BIGP", "CFGH", "BIOC",
        "INFI", "EFID", "KABO", "GOUR", "GSSC", "PRCL", "ADPC", "AJWA", "OLFI", "AFMC",
        "COSG", "MBEG",
    ),
    "energy_utilities": ("TAQA", "EGAS", "EGTS", "CSAG", "ETRS", "ALCN", "KORA"),
}

_SESSION_PDF_MAP: Dict[str, str] = {
    "2026-11-05": "https://static.mubasher.info/File.Mix_Announcement_File/3F6C910C-B6A9-4704-9908-C22F20EAD533.pdf",
    "2026-11-04": "https://static.mubasher.info/File.Mix_Announcement_File/06152F35-6E05-4299-AD5C-C82D2A9F45D3.pdf",
    "default_insider": "https://static.mubasher.info/File.Mix_Announcement_File/3F6C910C-B6A9-4704-9908-C22F20EAD533.pdf",
}

_ALLOWED_PDF_HOSTS = ("static.mubasher.info", "www.egx.com.eg", "egx.com.eg")
_ALLOWED_PDF_SUFFIXES = (".mubasher.info", ".supabase.co")


def _is_allowed_pdf_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return host in _ALLOWED_PDF_HOSTS or any(host.endswith(sfx) for sfx in _ALLOWED_PDF_SUFFIXES)


class _SafePdfRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Enforce SSRF host/scheme allowlist across every HTTP redirect hop."""

    max_redirections = 3

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        resolved_url = urljoin(req.full_url, newurl)
        if not _is_allowed_pdf_url(resolved_url):
            raise urllib.error.URLError(f"Disallowed PDF redirect target: {resolved_url}")
        return super().redirect_request(req, fp, code, msg, headers, resolved_url)


_SAFE_PDF_OPENER = urllib.request.build_opener(_SafePdfRedirectHandler())


def _open_safe_pdf(req: urllib.request.Request, timeout: float = 12.0):
    """Open PDF URL with redirect-hop SSRF validation enabled."""
    return _SAFE_PDF_OPENER.open(req, timeout=timeout)


@router.get("/api/disclosures")
async def api_disclosures_list(
    request: Request,
    limit: int = Query(default=12),
    offset: int = Query(default=0),
    search: str = Query(default=""),
    type: str = Query(default="all"),
    sentiment: str = Query(default="all"),
    timeframe: str = Query(default="all"),
    sector: str = Query(default="all"),
):
    """Paginated EGX/TASI disclosures listing with bounded LRU + SingleFlight caching."""
    market = resolve_request_market(request)
    eff_limit = min(max(int(limit), 1), 50)
    eff_offset = max(int(offset), 0)
    clean_search = re.sub(r'[%_,()*\\"]', "", search.strip())[:80]
    type_clean = type.strip()[:40] or "all"
    sent_clean = sentiment.strip()[:30] or "all"
    tf_clean = timeframe.strip()[:20] or "all"
    sec_clean = sector.strip()[:40] or "all"

    explicit_market = _has_explicit_market_param(request)
    headers = (
        {**_daily_cdn_headers("daily-disclosures"), "Vary": "X-Egxbots-Market"}
        if explicit_market
        else {**_private_no_store_headers("daily-disclosures"), "Vary": "Cookie, X-Egxbots-Market"}
    )

    sb_check = get_market_supabase(market)
    if sb_check is None:
        return JSONResponse({"data": [], "total": 0, "stats": {"total": 0, "buys": 0, "sells": 0, "shareholding": 0}}, headers=_private_no_store_headers())

    cache_key = f"{market}:{eff_limit}:{eff_offset}:{clean_search}:{type_clean}:{sent_clean}:{tf_clean}:{sec_clean}"
    found, cached = _DISCLOSURES_CACHE.get(cache_key)
    if found:
        return JSONResponse(cached, headers=headers)

    def _fetch() -> Dict[str, Any]:
        sb = get_market_supabase(market)
        if sb is None:
            raise RuntimeError("Market Supabase unavailable")
        cols = (
            "id,symbol,company_name,disclosure_type,disclosure_date,title,raw_content,"
            "ai_summary,sentiment,action_type,shares_count,stake_before,stake_after,"
            "party_name,party_role,source_url,metadata"
        )
        def _apply_exchange_filter(q: Any) -> Any:
            if market == "uae":
                return q.in_("metadata->>exchange", ["DFM", "ADX"])
            if market == "qatar":
                return q.eq("metadata->>exchange", "QSE")
            if market == "tasi":
                return q.eq("metadata->>exchange", "TADAWUL")
            return q

        qb = _apply_exchange_filter(
            sb.table("egx_disclosures")
            .select(cols, count="exact")
            .order("disclosure_date", desc=True)
            .order("created_at", desc=True)
        )
        if type_clean != "all":
            qb = qb.eq("disclosure_type", type_clean)
        if sent_clean != "all":
            if sent_clean == "bullish":
                qb = qb.or_("sentiment.eq.bullish,action_type.eq.buy")
            elif sent_clean == "bearish":
                qb = qb.or_("sentiment.eq.bearish,action_type.eq.sell")
            else:
                qb = qb.eq("sentiment", sent_clean)
        if sec_clean != "all" and market == "egx":
            sec_syms = _EGX_DISCLOSURE_SECTORS.get(sec_clean)
            if sec_syms:
                qb = qb.in_("symbol", list(sec_syms))

        if tf_clean != "all":
            latest_res = (
                _apply_exchange_filter(
                    sb.table("egx_disclosures").select("disclosure_date")
                )
                .order("disclosure_date", desc=True)
                .limit(150)
                .execute()
            )
            seen_dates: List[str] = []
            for r in getattr(latest_res, "data", None) or []:
                d_val = r.get("disclosure_date")
                if d_val and d_val not in seen_dates:
                    seen_dates.append(str(d_val))
            ref_date = seen_dates[0] if seen_dates else datetime.now(timezone.utc).strftime("%Y-%m-%d")
            yest_date = seen_dates[1] if len(seen_dates) > 1 else None
            if tf_clean == "today":
                qb = qb.eq("disclosure_date", ref_date)
            elif tf_clean == "yesterday":
                qb = qb.eq("disclosure_date", yest_date or ref_date)
            else:
                days_map = {"3d": 3, "7d": 7, "14d": 14, "30d": 30, "90d": 90}
                days_back = days_map.get(tf_clean, 30)
                try:
                    ref_dt = datetime.fromisoformat(ref_date[:10]).replace(tzinfo=timezone.utc)
                except Exception:
                    ref_dt = datetime.now(timezone.utc)
                threshold = (ref_dt - timedelta(days=days_back)).strftime("%Y-%m-%d")
                qb = qb.gte("disclosure_date", threshold)

        if clean_search:
            qb = qb.or_(
                f"symbol.ilike.%{clean_search}%,company_name.ilike.%{clean_search}%,title.ilike.%{clean_search}%,party_name.ilike.%{clean_search}%"
            )

        res = qb.range(eff_offset, eff_offset + eff_limit - 1).execute()
        rows = getattr(res, "data", None) or []
        total_val = getattr(res, "count", None)
        total = int(total_val) if total_val is not None else len(rows)
        return {"data": rows, "total": total, "hasMore": (eff_offset + len(rows)) < total}

    try:
        payload = _DISCLOSURES_SF.do(cache_key, _fetch)
        _DISCLOSURES_CACHE.set(cache_key, payload)
        return JSONResponse(payload, headers=headers)
    except Exception as exc:
        print(f"[api/disclosures] error: {exc}")
        return JSONResponse({"data": [], "total": 0, "error": "Failed to fetch disclosures"}, status_code=500)


@router.get("/api/disclosures/pdf/{item_id}")
async def api_disclosure_pdf(item_id: str):
    """SSRF-guarded disclosure PDF proxy offloaded from Vercel Functions."""
    if not _DISCLOSURE_ID_RE.match(item_id):
        return JSONResponse({"error": "Invalid disclosure ID"}, status_code=400)

    pdf_headers_base = {
        "Cache-Control": "public, max-age=604800, s-maxage=2592000, stale-while-revalidate=2592000, immutable",
        "Vercel-CDN-Cache-Control": "public, s-maxage=2592000, stale-while-revalidate=2592000, immutable",
    }

    found, cached = _PDF_CACHE.get(item_id)
    if found:
        content, sym = cached
        return Response(
            content=content,
            media_type="application/pdf",
            headers={**pdf_headers_base, "Content-Disposition": f'inline; filename="egx_disclosure_{sym}.pdf"'},
        )

    def _load_pdf() -> Tuple[bytes, str]:
        sb = get_primary_supabase()
        item: Dict[str, Any] = {}
        if sb is not None:
            res = _safe_exec(
                lambda: sb.table("egx_disclosures")
                .select("id,symbol,disclosure_date,disclosure_type,source_url")
                .eq("id", item_id)
                .limit(1)
                .execute()
            )
            rows = getattr(res, "data", None) or []
            if rows:
                item = rows[0]

        sym = re.sub(r"[^A-Z0-9_-]", "", str(item.get("symbol") or "official").upper()) or "official"
        target_url = str(item.get("source_url") or "")
        if ".pdf" not in target_url.lower():
            d_str = str(item.get("disclosure_date") or "")
            target_url = _SESSION_PDF_MAP.get(d_str) or _SESSION_PDF_MAP["default_insider"]

        if not _is_allowed_pdf_url(target_url):
            target_url = _SESSION_PDF_MAP["default_insider"]

        req = urllib.request.Request(
            target_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/pdf,*/*",
            },
        )
        with _open_safe_pdf(req, timeout=12.0) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"PDF status {resp.status}")
            raw = resp.read(15 * 1024 * 1024 + 1)
        if len(raw) > 15 * 1024 * 1024:
            raise RuntimeError("PDF exceeds size cap")
        return raw, sym

    try:
        pdf_bytes, sym = _PDF_SF.do(item_id, _load_pdf)
        if len(pdf_bytes) <= 2_500_000:
            _PDF_CACHE.set(item_id, (pdf_bytes, sym))
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={**pdf_headers_base, "Content-Disposition": f'inline; filename="egx_disclosure_{sym}.pdf"'},
        )
    except Exception as exc:
        print(f"[api/disclosures/pdf] {exc}")
        return JSONResponse({"error": "PDF document unavailable"}, status_code=404)
