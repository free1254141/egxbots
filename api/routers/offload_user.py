"""
Offloaded Authenticated User, Commercial, Portfolio & Payment Endpoints.

Moves high-frequency user/authenticated and payment BFF API routes out of
Vercel Node.js serverless functions onto Hugging Face FastAPI (`0ms` Vercel
Fluid Active CPU), preserving identical request/response contracts, cookie +
Bearer SSR auth (`resolve_verified_viewer`), fail-closed authorization, and
per-user isolation.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from api import stock_ai
from api.egx_canonical_names import CANONICAL_EGX_STOCK_NAMES
from api.payment_common import is_payments_enabled
from api.perf_utils import (
    BoundedTTLCache,
    SingleFlight,
    _VIEWER_PLAN_CACHE,
    extract_jwt_token,
    get_cairo_date_str,
    get_market_exchange,
    get_market_supabase,
    get_primary_supabase,
    has_active_chat_pro,
    has_active_pro_subscription,
    is_unlimited_chat_user,
    resolve_request_market,
    resolve_subscription_quota_window,
    resolve_verified_viewer,
)
from api.plan_limits import effective_limits, plan_limits

router = APIRouter(tags=["offload-user"])

# ---------------------------------------------------------------------------
# Headers & Short Shared Caches (public canonical market sub-lookups ONLY)
# ---------------------------------------------------------------------------
_PRIVATE_NO_STORE = {
    "Cache-Control": "private, no-store, max-age=0",
    "Vercel-CDN-Cache-Control": "no-store",
    "CDN-Cache-Control": "no-store",
    "Vary": "Cookie, Authorization",
}

_PUBLIC_CACHE_2M = {
    "Cache-Control": "public, max-age=30, s-maxage=120, stale-while-revalidate=300",
    "Vercel-CDN-Cache-Control": "public, s-maxage=120, stale-while-revalidate=300",
}

_PUBLIC_CACHE_1H = {
    "Cache-Control": "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400",
    "Vercel-CDN-Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
}

_SYMBOLS_LIST_CACHE = BoundedTTLCache(max_entries=8, default_ttl=600.0)
_SYMBOLS_LIST_SF = SingleFlight()

_DAILY_HISTORY_CACHE = BoundedTTLCache(max_entries=400, default_ttl=600.0)
_DAILY_HISTORY_SF = SingleFlight()

_SCANNER_ALERTS_STATE_CACHE = BoundedTTLCache(max_entries=8, default_ttl=60.0)
_SCANNER_ALERTS_STATE_SF = SingleFlight()

_PUBLIC_PAYMENT_CFG_CACHE = BoundedTTLCache(max_entries=4, default_ttl=60.0)
_PUBLIC_PAYMENT_CFG_SF = SingleFlight()

_FOUNDERS_STATUS_CACHE = BoundedTTLCache(max_entries=2, default_ttl=60.0)
_FOUNDERS_STATUS_SF = SingleFlight()

_BACKTESTS_SOFT_CACHE = BoundedTTLCache(max_entries=16, default_ttl=120.0)
_MODEL_CARDS_CACHE = BoundedTTLCache(max_entries=4, default_ttl=600.0)
_SHARED_CHAT_CACHE = BoundedTTLCache(max_entries=128, default_ttl=600.0)
_ORDER_STATUS_CACHE = BoundedTTLCache(max_entries=256, default_ttl=8.0)


def invalidate_user_router_public_caches(tags: Iterable[str]) -> List[str]:
    """Clear public canonical lookup caches held inside offload_user on daily refresh."""
    tag_set = set(tags or [])
    cleared: List[str] = []
    relevant = {"daily-market-data", "daily-recommendations", "daily-symbols", "market", "recommendations", "symbols"}
    if not tag_set or (tag_set & relevant):
        _SYMBOLS_LIST_CACHE.clear()
        _DAILY_HISTORY_CACHE.clear()
        _SCANNER_ALERTS_STATE_CACHE.clear()
        cleared.append("offload_user_public")
    return cleared


# ---------------------------------------------------------------------------
# Generic Parsing, Admin & Auth Helpers
# ---------------------------------------------------------------------------
_DEFAULT_ADMIN_EMAILS = frozenset({
    "acursour@gmail.com",
    "weeeessd57@gmail.com",
    "weeessd57@gmail.com",
    "weeasd57@gmail.com",
    "weeeenew@gmail.com",
})


def is_allowed_admin_email(email: Optional[str]) -> bool:
    if not email:
        return False
    clean = email.strip().lower()
    configured = {
        e.strip().lower()
        for raw in (os.getenv("NEXT_PUBLIC_ADMIN_EMAILS", ""), os.getenv("ADMIN_EMAILS", ""))
        for e in raw.split(",")
        if e.strip()
    }
    return clean in _DEFAULT_ADMIN_EMAILS or clean in configured


def is_chat_admin_email(email: Optional[str]) -> bool:
    if is_allowed_admin_email(email):
        return True
    clean = (email or "").strip().lower()
    return any(tok in clean for tok in ("weeessd57", "weeeessd57", "weeasd57"))


def _finite_float(value: Any) -> Optional[float]:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _positive_float(value: Any) -> Optional[float]:
    num = _finite_float(value)
    return num if num is not None and num > 0 else None


def _fmt_num(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _first_row(res: Any) -> Optional[Dict[str, Any]]:
    """Safely extract the first row dict from a Supabase/PostgREST response (list or single dict)."""
    data = getattr(res, "data", None)
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else None
    if isinstance(data, dict):
        return data
    return None


def _select_one(query: Any) -> Optional[Dict[str, Any]]:
    """Execute a limit(1) query safely without PostgREST .maybe_single() 204 APIError crashes."""
    return _first_row(query.limit(1).execute())


_ALLOWED_PUBLIC_HOSTS = frozenset({"egxbots.com", "www.egxbots.com", "localhost:3000", "127.0.0.1:3000"})


def _resolve_public_origin(request: Request) -> str:
    """Resolve canonical frontend origin even when proxied through Vercel beforeFiles rewrites."""
    configured = (os.getenv("WEB_PUBLIC_ORIGIN") or os.getenv("NEXT_PUBLIC_SITE_URL") or "").strip().rstrip("/")
    if configured.startswith(("https://", "http://")):
        return configured
    fwd_host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip().lower()
    if fwd_host in _ALLOWED_PUBLIC_HOSTS:
        proto = "http" if fwd_host.startswith(("localhost", "127.0.0.1")) else "https"
        return f"{proto}://{fwd_host}"
    return "https://egxbots.com"


def _require_viewer(request: Request, message: str = "Unauthorized") -> Dict[str, Any]:
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        raise HTTPException(status_code=401, detail=message)
    return viewer


def _get_user_meta(token: Optional[str], user_id: str) -> Dict[str, Any]:
    """Fetch basic display name / metadata for an authenticated user when needed."""
    sb = get_primary_supabase()
    if sb is None:
        return {"name": "", "email": ""}
    if token:
        try:
            res = sb.auth.get_user(token)
            u = getattr(res, "user", None)
            if u:
                meta = getattr(u, "user_metadata", None) or {}
                return {
                    "name": str(meta.get("full_name") or meta.get("name") or meta.get("display_name") or ""),
                    "email": str(getattr(u, "email", "") or ""),
                }
        except Exception:
            pass
    try:
        row = _select_one(sb.table("profiles").select("display_name,username").eq("id", user_id)) or {}
        return {"name": str(row.get("display_name") or row.get("username") or ""), "email": ""}
    except Exception:
        return {"name": "", "email": ""}


def _get_deepseek_key() -> str:
    return (
        os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("DEEPSEEK_KEY")
        or ""
    ).strip()


def _get_nvidia_keys() -> List[str]:
    keys: List[str] = []
    for env_name in ("NVIDIA_API_KEY", "NVIDIA_API_KEY_2", "NVIDIA_API_KEY_3", "NVIDIA_NIM_API_KEY"):
        val = (os.getenv(env_name) or "").strip()
        if val and val not in keys:
            keys.append(val)
    extra = (os.getenv("NVIDIA_API_KEYS") or "").strip()
    if extra:
        for item in extra.split(","):
            k = item.strip()
            if k and k not in keys:
                keys.append(k)
    return keys


# ===========================================================================
# 1. /api/market/ai-signals & /api/recommendations/events
# ===========================================================================
def _saved_signal_reasons(value: Any) -> List[str]:
    if isinstance(value, str):
        try:
            return _saved_signal_reasons(json.loads(value))
        except Exception:
            trimmed = value.strip()
            return [trimmed] if trimmed else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    if not isinstance(value, dict):
        return []
    seen: Set[str] = set()
    out: List[str] = []
    for cand in _saved_signal_reasons(value.get("text_reasons")):
        if cand not in seen:
            seen.add(cand)
            out.append(cand)
    for key in ("brief_rationale", "technical_rationale", "fundamental_rationale"):
        item = value.get(key)
        if isinstance(item, str) and item.strip() and item not in seen:
            seen.add(item)
            out.append(item)
    return out


@router.get("/api/market/ai-signals")
def get_market_ai_signals(request: Request):
    market = resolve_request_market(request)
    exchange = get_market_exchange(market)
    country = "Saudi Arabia" if market == "tasi" else "Egypt"
    currency = "SAR" if market == "tasi" else "EGP"
    billing_enabled = is_payments_enabled()

    if billing_enabled:
        viewer = resolve_verified_viewer(request)
        user_is_pro = bool(viewer.get("authenticated") and viewer.get("pro"))
        headers = _PRIVATE_NO_STORE
    else:
        user_is_pro = True
        explicit_param = any(k in request.query_params for k in ("market", "country", "exchange"))
        headers = _PUBLIC_CACHE_2M if explicit_param else _PRIVATE_NO_STORE

    sb = get_market_supabase(market)
    if sb is None:
        return JSONResponse({"error": "Failed to fetch AI signals"}, status_code=500, headers=headers)

    try:
        rec_res = (
            sb.table("scan_results")
            .select("symbol,name,signal,entry_price,target_price,stop_loss,precision,top_reasons,model_name,created_at")
            .eq("country", country)
            .eq("status", "open")
            .eq("is_public", True)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        recommendations = getattr(rec_res, "data", None) or []
    except Exception:
        return JSONResponse({"error": "Failed to fetch AI signals"}, status_code=500, headers=headers)

    if not recommendations:
        return JSONResponse(
            {
                "signals": [],
                "total_open": 0,
                "buy_count": 0,
                "sell_count": 0,
                "market": market,
                "exchange": exchange,
                "currency": currency,
            },
            headers=headers,
        )

    if not user_is_pro:
        buy_count = sum(1 for r in recommendations if str(r.get("signal") or "") == "BUY")
        sell_count = sum(1 for r in recommendations if str(r.get("signal") or "") == "SELL")
        return JSONResponse(
            {
                "signals": [],
                "total_open": len(recommendations),
                "buy_count": buy_count,
                "sell_count": sell_count,
                "gated": True,
                "is_pro": False,
                "signal_delay_days": plan_limits("free")["signal_delay_days"],
                "market": market,
                "exchange": exchange,
                "currency": currency,
            },
            headers=headers,
        )

    symbols = [str(r.get("symbol") or "").strip() for r in recommendations if r.get("symbol")]
    prices_map: Dict[str, float] = {}
    price_dates: Dict[str, Optional[str]] = {}

    try:
        date_res = (
            sb.table("stock_technical_indicators")
            .select("date")
            .eq("exchange", exchange)
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        latest_date = (getattr(date_res, "data", None) or [{}])[0].get("date")
        if latest_date and symbols:
            ind_res = (
                sb.table("stock_technical_indicators")
                .select("symbol,close")
                .eq("exchange", exchange)
                .eq("date", latest_date)
                .in_("symbol", symbols)
                .limit(len(symbols) + 10)
                .execute()
            )
            for row in getattr(ind_res, "data", None) or []:
                c = _finite_float(row.get("close"))
                sym_u = str(row.get("symbol") or "").upper()
                if sym_u and c and c > 0:
                    prices_map[sym_u] = c
                    price_dates[sym_u] = latest_date
    except Exception:
        pass

    missing = list({s.upper() for s in symbols if s.upper() not in prices_map})
    if missing:
        try:
            fallback_limit = min(max(len(missing) * 30, 300), 2000)
            fb_res = (
                sb.table("stock_prices")
                .select("symbol,close,date")
                .eq("exchange", exchange)
                .in_("symbol", missing)
                .order("date", desc=True)
                .limit(fallback_limit)
                .execute()
            )
            for row in getattr(fb_res, "data", None) or []:
                sym_u = str(row.get("symbol") or "").upper()
                c = _finite_float(row.get("close"))
                if sym_u and sym_u not in prices_map and c and c > 0:
                    prices_map[sym_u] = c
                    price_dates[sym_u] = row.get("date")
        except Exception:
            pass

    tasi_names_map: Dict[str, str] = {}
    if market == "tasi" and symbols:
        uniq = list({s for s in symbols if s})
        try:
            try:
                st_res = sb.table("stocks").select("symbol,name_ar,name").eq("exchange", exchange).in_("symbol", uniq).limit(len(uniq)).execute()
            except Exception:
                st_res = sb.table("stocks").select("symbol,name").eq("exchange", exchange).in_("symbol", uniq).limit(len(uniq)).execute()
            for row in getattr(st_res, "data", None) or []:
                key = str(row.get("symbol") or "").strip().upper()
                label = row.get("name_ar") or row.get("name")
                if key and label:
                    tasi_names_map[key] = str(label)
        except Exception:
            pass

    buy_count = 0
    sell_count = 0
    signals: List[Dict[str, Any]] = []
    for rec in recommendations:
        sym = str(rec.get("symbol") or "")
        sym_u = sym.upper()
        entry = float(rec.get("entry_price") or 0)
        current_price = prices_map.get(sym_u) or entry
        is_buy = "BUY" in str(rec.get("signal") or "").upper()
        if is_buy:
            buy_count += 1
        else:
            sell_count += 1
        pnl_pct = 0.0
        if entry > 0:
            pnl_pct = ((current_price - entry) / entry) * 100.0 if is_buy else ((entry - current_price) / entry) * 100.0
        signals.append(
            {
                "symbol": sym,
                "name": tasi_names_map.get(sym_u, rec.get("name") or sym) if market == "tasi" else (rec.get("name") or sym),
                "signal": "BUY" if is_buy else "SELL",
                "entry_price": entry,
                "current_price": current_price,
                "price_date": price_dates.get(sym_u),
                "target_price": float(rec.get("target_price") or 0),
                "stop_loss": float(rec.get("stop_loss") or 0),
                "precision": float(rec.get("precision") or 0),
                "pnl_pct": pnl_pct,
                "top_reasons": _saved_signal_reasons(rec.get("top_reasons")),
                "model_name": rec.get("model_name") or "AI Council",
                "created_at": rec.get("created_at"),
                "council_score": 0,
            }
        )

    return JSONResponse(
        {
            "signals": signals,
            "total_open": len(recommendations),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "gated": False,
            "is_pro": True,
            "signal_delay_days": 0,
            "market": market,
            "exchange": exchange,
            "currency": currency,
        },
        headers=headers,
    )


_PUBLIC_EVENT_TYPES = [
    "recommendation_closed",
    "recommendation_stale",
    "target_or_stop_adjusted",
]


@router.get("/api/recommendations/events")
def get_recommendations_events(
    request: Request,
    limit: int = Query(default=100),
    month: str = Query(default=""),
):
    raw_market = (request.query_params.get("market") or "").strip().lower()
    if raw_market in ("tasi", "tadawul", "saudi", "sa"):
        return JSONResponse({"events": [], "tracked_recommendation_ids": []}, headers=_PRIVATE_NO_STORE)

    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated"):
        return JSONResponse({"detail": "Pro subscription required"}, status_code=401, headers=_PRIVATE_NO_STORE)
    if not viewer.get("pro"):
        return JSONResponse({"detail": "Pro subscription required"}, status_code=403, headers=_PRIVATE_NO_STORE)

    safe_limit = min(max(int(limit or 100), 1), 300)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"detail": "Recommendation event history is temporarily unavailable."}, status_code=503, headers=_PRIVATE_NO_STORE)

    try:
        query = (
            sb.table("recommendation_events")
            .select("id,recommendation_id,event_type,old_values,new_values,price_at_event,source,telegram_status,created_at")
            .in_("event_type", _PUBLIC_EVENT_TYPES)
            .not_.is_("recommendation_id", "null")
        )
        if month and re.match(r"^\d{4}-\d{2}$", month):
            year_num, month_num = map(int, month.split("-"))
            start_iso = f"{month}-01T00:00:00Z"
            next_year = year_num + (1 if month_num == 12 else 0)
            next_month = 1 if month_num == 12 else month_num + 1
            next_iso = f"{next_year:04d}-{next_month:02d}-01T00:00:00Z"
            query = query.gte("created_at", start_iso).lt("created_at", next_iso)

        ev_res = query.order("created_at", desc=True).limit(safe_limit).execute()
        visible_events = getattr(ev_res, "data", None) or []
        rec_ids = list({str(e["recommendation_id"]) for e in visible_events if e.get("recommendation_id")})
        if not rec_ids:
            return JSONResponse({"events": [], "tracked_recommendation_ids": []}, headers=_PRIVATE_NO_STORE)

        rec_res = (
            sb.table("scan_results")
            .select("id,symbol,exchange,name,signal,status,is_public,entry_price,target_price,stop_loss,exit_price,profit_loss_pct,logo_url,created_at")
            .in_("id", rec_ids)
            .eq("is_public", True)
            .limit(len(rec_ids) + 5)
            .execute()
        )
        by_id = {str(r["id"]): r for r in (getattr(rec_res, "data", None) or []) if r.get("id") is not None}

        tracked_ids: List[str] = []
        seen_tracked: Set[str] = set()
        for ev in visible_events:
            rid = str(ev.get("recommendation_id") or "")
            if (
                ev.get("event_type") in ("recommendation_closed", "recommendation_stale")
                and ev.get("telegram_status") == "sent"
                and rid in by_id
                and rid not in seen_tracked
            ):
                seen_tracked.add(rid)
                tracked_ids.append(rid)

        sanitized: List[Dict[str, Any]] = []
        for ev in visible_events:
            if ev.get("telegram_status") != "sent":
                continue
            rid = str(ev.get("recommendation_id") or "")
            rec = by_id.get(rid)
            if not rec:
                continue
            old_vals = ev.get("old_values") if isinstance(ev.get("old_values"), dict) else {}
            new_vals = ev.get("new_values") if isinstance(ev.get("new_values"), dict) else {}
            eval_info = (new_vals.get("rich_details") or {}).get("evaluation") or {}
            closed_on = eval_info.get("closed_on")
            if ev.get("event_type") == "recommendation_closed" and isinstance(closed_on, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", closed_on):
                occurred_at = f"{closed_on}T12:00:00Z"
            else:
                occurred_at = ev.get("created_at")

            sanitized.append(
                {
                    "id": str(ev.get("id")),
                    "recommendation_id": rid,
                    "event_type": ev.get("event_type"),
                    "occurred_at": occurred_at,
                    "price_at_event": _finite_float(ev.get("price_at_event")),
                    "source": ev.get("source"),
                    "symbol": rec.get("symbol"),
                    "exchange": rec.get("exchange"),
                    "name": rec.get("name"),
                    "signal": rec.get("signal"),
                    "logo_url": rec.get("logo_url"),
                    "created_at": rec.get("created_at"),
                    "status": new_vals.get("status") or rec.get("status"),
                    "entry_price": _finite_float(old_vals.get("entry_price") if old_vals.get("entry_price") is not None else rec.get("entry_price")),
                    "exit_price": _finite_float(
                        new_vals.get("exit_price")
                        if new_vals.get("exit_price") is not None
                        else (rec.get("exit_price") if rec.get("exit_price") is not None else ev.get("price_at_event"))
                    ),
                    "profit_loss_pct": _finite_float(new_vals.get("profit_loss_pct") if new_vals.get("profit_loss_pct") is not None else rec.get("profit_loss_pct")),
                    "exit_reason": eval_info.get("exit_reason") or None,
                    "exit_reason_ar": eval_info.get("exit_reason_ar") or None,
                    "exit_reason_en": eval_info.get("exit_reason_en") or None,
                    "old_target": _finite_float(old_vals.get("target_price")),
                    "new_target": _finite_float(new_vals.get("target_price")),
                    "old_stop": _finite_float(old_vals.get("stop_loss")),
                    "new_stop": _finite_float(new_vals.get("stop_loss")),
                    "target_price": _finite_float(new_vals.get("target_price") if new_vals.get("target_price") is not None else rec.get("target_price")),
                    "stop_loss": _finite_float(new_vals.get("stop_loss") if new_vals.get("stop_loss") is not None else rec.get("stop_loss")),
                    "adjustment_type": new_vals.get("adjustment_type") or None,
                }
            )

        return JSONResponse({"events": sanitized, "tracked_recommendation_ids": tracked_ids}, headers=_PRIVATE_NO_STORE)
    except Exception:
        return JSONResponse({"detail": "Recommendation event history is temporarily unavailable."}, status_code=503, headers=_PRIVATE_NO_STORE)


# ===========================================================================
# 2. Portfolio Helpers & Routes (/api/portfolio, performance, transactions, rebalance)
# ===========================================================================
_EXTRACT_LLM_SYSTEM_PROMPT = """You are an expert Egyptian Stock Exchange (EGX) portfolio assistant.
Your task is to analyze the user's query, the AI assistant's response/analysis, and any suggested follow-up buttons to extract ALL Egyptian stock symbols (EGX tickers) being analyzed, discussed, recommended, or tracked.

Extraction Rules:
1. Identify the subject stock(s) of the analysis (e.g. from user question, buttons, or analysis body).
2. Even if the analysis rating is negative (🔴 سلبي) or neutral or says "لا توجد توصية شراء" / "للمراقبة", ALWAYS extract the stock(s) because the user clicked "Save to Portfolio" to track this stock in their portfolio!
3. For each stock found:
   - symbol: The official EGX English ticker symbol in UPPERCASE (e.g., MOED, COMI, TMGH, ABUK, ATQA, SKPC, FWRY, SWDY, HRHO, ESRS, CCAP, AMOC, EKHO, HELI, PHDC, ISPH, JUFO, BTFH, ETEL, etc.). Always convert Arabic names or lowercase input to uppercase EGX tickers.
   - name: The Arabic company name if recognized.
   - quantity: Number of shares if mentioned, default to 100.
   - price: Current or entry price mentioned, otherwise null.
4. DO NOT extract stocks mentioned only as already in the user's existing portfolio.
5. Return ONLY raw valid JSON matching: {"stocks": [{"symbol": "MOED", "name": "المنصورة للدواجن", "quantity": 100, "price": 0.404}]}
- If NO EGX stocks are present, return: {"stocks": []}"""

_IGNORED_EXTRACT_TOKENS = frozenset({"RSI", "MACD", "EMA", "SMA", "EGX", "USD", "EGP", "COPY", "BUY", "SELL", "HOLD", "VIP", "EXCEL"})


def _extract_fallback_stocks(text: str, user_query: str = "", suggested_buttons: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    found_symbols: List[str] = []
    seen: Set[str] = set()
    detected_price: Optional[float] = None
    pm = re.search(r"(?:السعر الحالي|السعر)\s*[:|]?\s*([\d.]+)", text or "", re.IGNORECASE)
    if pm:
        val = _positive_float(pm.group(1))
        if val:
            detected_price = val

    def _add(sym: str) -> None:
        clean = sym.strip().upper()
        if clean and re.match(r"^[A-Z]{2,6}$", clean) and clean not in _IGNORED_EXTRACT_TOKENS and clean not in seen:
            seen.add(clean)
            found_symbols.append(clean)

    if user_query:
        clean_q = user_query.strip().upper()
        if re.match(r"^[A-Z]{2,6}$", clean_q):
            _add(clean_q)

    for btn in suggested_buttons or []:
        m = re.search(r"(?:على|في|بـ|سهم)\s+([A-Z]{2,6})\b", str(btn), re.IGNORECASE) or re.search(r"\b([A-Z]{2,6})\b", str(btn))
        if m:
            _add(m.group(1))

    if not found_symbols and text:
        for w in re.findall(r"\b[A-Z]{2,6}\b", text):
            sym = w.upper()
            if sym not in _IGNORED_EXTRACT_TOKENS and f"مراكز محفظتك المحفوظة ({sym}" not in text and f"المحفوظة ({sym}" not in text:
                _add(sym)
                break

    return [{"symbol": sym, "quantity": 100, "price": detected_price} for sym in found_symbols]


def _call_portfolio_extraction_llm(text: str, user_query: str = "", suggested_buttons: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    parts: List[str] = []
    if user_query:
        parts.append(f"سؤال المستخدم أو طلبه: {user_query}")
    if suggested_buttons:
        parts.append(f"أزرار ومقترحات المتابعة: {' | '.join(suggested_buttons)}")
    if text:
        parts.append(f"تحليل ورد المساعد:\n{text[:4000]}")
    user_prompt = "استخرج أسهم البورصة المصرية المطلوب حفظها من هذا السياق بصيغة JSON كما طُلب:\n\n" + "\n\n".join(parts)

    ds_key = _get_deepseek_key()
    if ds_key:
        try:
            r = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {ds_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "system", "content": _EXTRACT_LLM_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                    "max_tokens": 1000,
                },
                timeout=12,
            )
            if r.ok:
                content = str(((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
                parsed = json.loads(content)
                if isinstance(parsed.get("stocks"), list) and parsed["stocks"]:
                    return parsed["stocks"]
        except Exception:
            pass

    for n_key in _get_nvidia_keys():
        try:
            r = requests.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {n_key}"},
                json={
                    "model": "meta/llama-3.1-70b-instruct",
                    "messages": [{"role": "system", "content": _EXTRACT_LLM_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
                    "temperature": 0.1,
                    "max_tokens": 1000,
                },
                timeout=12,
            )
            if r.ok:
                raw_content = str(((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
                parsed = None
                try:
                    parsed = json.loads(raw_content)
                except Exception:
                    m = re.search(r"\{[\s\S]*\}", raw_content)
                    if m:
                        parsed = json.loads(m.group(0))
                if isinstance(parsed, dict) and isinstance(parsed.get("stocks"), list) and parsed["stocks"]:
                    return parsed["stocks"]
        except Exception:
            continue

    return _extract_fallback_stocks(text, user_query, suggested_buttons)


def _load_market_symbols_list() -> List[Dict[str, Any]]:
    found, cached = _SYMBOLS_LIST_CACHE.get("egx_symbols")
    if found and isinstance(cached, list):
        return cached

    def _fetch() -> List[Dict[str, Any]]:
        sb = get_primary_supabase()
        if sb is None:
            return []
        try:
            res = sb.table("stocks").select("symbol,name").order("symbol", desc=False).limit(500).execute()
            return [{"symbol": r.get("symbol"), "name": r.get("name") or None} for r in (getattr(res, "data", None) or []) if r.get("symbol")]
        except Exception:
            return []

    rows = _SYMBOLS_LIST_SF.do("egx_symbols", _fetch)
    if rows:
        _SYMBOLS_LIST_CACHE.set("egx_symbols", rows, ttl=600.0)
    return rows


def _fetch_open_positions(sb: Any, user_id: str) -> List[Dict[str, Any]]:
    res = (
        sb.table("positions")
        .select("id,symbol,name,quantity,entry_price,entry_at,status,source,added_at")
        .eq("user_id", user_id)
        .eq("status", "open")
        .order("added_at", desc=True)
        .limit(100)
        .execute()
    )
    out: List[Dict[str, Any]] = []
    for row in getattr(res, "data", None) or []:
        out.append(
            {
                "id": str(row.get("id") or ""),
                "symbol": str(row.get("symbol") or "").upper(),
                "name": row.get("name") or None,
                "quantity": _finite_float(row.get("quantity")),
                "entry_price": _finite_float(row.get("entry_price")),
                "entry_at": row.get("entry_at") or None,
                "status": str(row.get("status") or "open"),
                "source": row.get("source") or None,
                "added_at": row.get("added_at") or None,
            }
        )
    return out


def _fetch_cash_balance(sb: Any, user_id: str) -> float:
    try:
        data = _select_one(sb.table("profiles").select("cash_balance").eq("id", user_id)) or {}
        return _finite_float(data.get("cash_balance")) or 0.0
    except Exception:
        return 0.0


def _upsert_cash_balance(sb: Any, user_id: str, value: float) -> None:
    sb.table("profiles").update({"cash_balance": value}).eq("id", user_id).execute()


def _record_position_event(sb: Any, user_id: str, position_id: Optional[str], event_type: str, payload: Dict[str, Any]) -> None:
    try:
        sb.table("position_events").insert(
            {
                "user_id": user_id,
                "position_id": position_id,
                "event_type": event_type,
                "payload": payload,
                "event_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()
    except Exception:
        pass


def _insert_position_row(sb: Any, row: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Exception]]:
    try:
        res = sb.table("positions").insert(row).execute()
        return _first_row(res), None
    except Exception as exc:
        if re.search(r"symbol_source|enum", str(exc), re.IGNORECASE):
            try:
                res2 = sb.table("positions").insert({**row, "source": "chatbot"}).execute()
                return _first_row(res2), None
            except Exception as exc2:
                return None, exc2
        return None, exc


def _symbol_exists_in_market(sb: Any, symbol: str) -> bool:
    try:
        res = sb.table("stocks").select("symbol").eq("symbol", symbol).limit(1).execute()
        return bool(getattr(res, "data", None))
    except Exception:
        return False


def _fetch_stock_name(sb: Any, symbol: str) -> Optional[str]:
    try:
        res = sb.table("stocks").select("name,name_ar").eq("symbol", symbol).limit(1).execute()
        rows = getattr(res, "data", None) or []
        if rows:
            return rows[0].get("name_ar") or rows[0].get("name") or None
    except Exception:
        pass
    canon = CANONICAL_EGX_STOCK_NAMES.get(symbol.upper())
    return canon.get("name_ar") if canon else None


def _portfolio_limit_for_user(sb: Any, user_id: str) -> Tuple[bool, int]:
    if not is_payments_enabled():
        return True, int(os.getenv("PRO_PORTFOLIO_STOCKS", "15"))
    res = sb.table("subscriptions").select("plan_id,status,current_period_end").eq("user_id", user_id).limit(10).execute()
    chat_pro = has_active_chat_pro(getattr(res, "data", None) or [])
    return chat_pro, int(plan_limits("chat_only" if chat_pro else "free")["portfolio_stocks"])


def _can_add_portfolio_positions(sb: Any, user_id: str, additional: int) -> Tuple[bool, str]:
    pro, limit = _portfolio_limit_for_user(sb, user_id)
    rows = _fetch_open_positions(sb, user_id)
    if pro:
        current = len({r["symbol"] for r in rows if r["symbol"]})
        if current + additional > limit:
            return False, f"خطة Pro تسمح بحد أقصى {limit} أسهم مختلفة في المحفظة."
        return True, ""
    current = len({r["symbol"] for r in rows if r["symbol"] and (r.get("quantity") or 0) > 0})
    if current + additional > limit:
        return False, f"الخطة المجانية تسمح بحد أقصى {limit} أسهم مختلفة في المحفظة. احذف مركزاً أو قم بالترقية لإضافة أسهم أكثر."
    return True, ""


def _build_portfolio_snapshot(sb: Any, user_id: str) -> Dict[str, Any]:
    all_positions = _fetch_open_positions(sb, user_id)
    positions = [p for p in all_positions if p.get("quantity") is not None and p["quantity"] > 0]
    watch_positions = [p for p in all_positions if p.get("quantity") is None or p["quantity"] <= 0]
    cash = _fetch_cash_balance(sb, user_id)

    latest_prices: Dict[str, Optional[float]] = {}
    price_dates: Dict[str, Optional[str]] = {}
    pos_exchange_map: Dict[str, str] = {}
    non_egx_groups: Dict[str, List[Tuple[str, str]]] = {}
    get_market_config: Any = None
    if positions or watch_positions:
        symbols = list({p["symbol"] for p in all_positions if p.get("symbol")})
        egx_symbols: List[str] = []
        try:
            from api.agentic_chat.tools_execution import _resolve_symbol_and_market
            from api.agentic_chat.market_registry import get_supabase_for_exchange, get_market_config as _gmc
            get_market_config = _gmc
        except Exception:
            _resolve_symbol_and_market = None  # type: ignore[assignment]
            get_supabase_for_exchange = None  # type: ignore[assignment]
            get_market_config = None

        for raw_sym in symbols:
            if _resolve_symbol_and_market is not None:
                try:
                    norm_s, exch = _resolve_symbol_and_market(raw_sym)
                except Exception:
                    norm_s, exch = raw_sym, "EGX"
            else:
                norm_s, exch = raw_sym, "EGX"
            pos_exchange_map[raw_sym] = exch
            if exch == "EGX":
                egx_symbols.append(raw_sym)
            else:
                non_egx_groups.setdefault(exch, []).append((raw_sym, norm_s))

        if egx_symbols:
            try:
                d_res = sb.table("stock_prices").select("date").eq("exchange", "EGX").order("date", desc=True).limit(1).execute()
                latest_date = (getattr(d_res, "data", None) or [{}])[0].get("date")
                if latest_date:
                    p_res = (
                        sb.table("stock_prices")
                        .select("symbol,close")
                        .eq("exchange", "EGX")
                        .eq("date", latest_date)
                        .in_("symbol", egx_symbols)
                        .limit(len(egx_symbols) + 10)
                        .execute()
                    )
                    for row in getattr(p_res, "data", None) or []:
                        sym_u = str(row.get("symbol") or "").upper()
                        if sym_u and sym_u not in latest_prices:
                            latest_prices[sym_u] = _finite_float(row.get("close"))
                            price_dates[sym_u] = latest_date
            except Exception:
                pass
            for pos in positions:
                if pos["symbol"] in egx_symbols and pos["symbol"] not in latest_prices:
                    try:
                        fb = sb.table("stock_prices").select("close,date").eq("symbol", pos["symbol"]).eq("exchange", "EGX").order("date", desc=True).limit(1).execute()
                        row = (getattr(fb, "data", None) or [{}])[0]
                        latest_prices[pos["symbol"]] = _finite_float(row.get("close"))
                        price_dates[pos["symbol"]] = row.get("date")
                    except Exception:
                        latest_prices[pos["symbol"]] = None

        for exch_code, sym_pairs in non_egx_groups.items():
            if get_supabase_for_exchange is None:
                continue
            try:
                sb_exch = get_supabase_for_exchange(exch_code, primary_sb=sb)
            except Exception:
                sb_exch = None
            if sb_exch is None:
                continue
            norm_list = list({ns for _, ns in sym_pairs})
            norm_prices: Dict[str, Optional[float]] = {}
            norm_dates: Dict[str, Optional[str]] = {}
            try:
                d_res = sb_exch.table("stock_prices").select("date").eq("exchange", exch_code).order("date", desc=True).limit(1).execute()
                latest_date = (getattr(d_res, "data", None) or [{}])[0].get("date")
                if latest_date and norm_list:
                    p_res = (
                        sb_exch.table("stock_prices")
                        .select("symbol,close")
                        .eq("exchange", exch_code)
                        .eq("date", latest_date)
                        .in_("symbol", norm_list)
                        .limit(len(norm_list) + 10)
                        .execute()
                    )
                    for row in getattr(p_res, "data", None) or []:
                        sym_u = str(row.get("symbol") or "").upper()
                        if sym_u and sym_u not in norm_prices:
                            norm_prices[sym_u] = _finite_float(row.get("close"))
                            norm_dates[sym_u] = latest_date
            except Exception:
                pass
            for raw_sym, norm_s in sym_pairs:
                if norm_s not in norm_prices:
                    try:
                        fb = (
                            sb_exch.table("stock_prices")
                            .select("close,date")
                            .eq("symbol", norm_s)
                            .eq("exchange", exch_code)
                            .order("date", desc=True)
                            .limit(1)
                            .execute()
                        )
                        row = (getattr(fb, "data", None) or [{}])[0]
                        norm_prices[norm_s] = _finite_float(row.get("close"))
                        norm_dates[norm_s] = row.get("date")
                    except Exception:
                        norm_prices[norm_s] = None
                latest_prices[raw_sym] = norm_prices.get(norm_s)
                price_dates[raw_sym] = norm_dates.get(norm_s)

    enriched: List[Dict[str, Any]] = []
    for pos in positions:
        last_price = latest_prices.get(pos["symbol"])
        qty = pos["quantity"]
        entry = pos["entry_price"]
        valid_entry = entry is not None and entry > 0
        cost_basis = qty * entry if qty is not None and valid_entry else None
        market_value = qty * last_price if qty is not None and last_price is not None else None
        profit_value = (market_value - cost_basis) if cost_basis is not None and market_value is not None else None
        profit_pct = (profit_value / cost_basis * 100.0) if cost_basis and cost_basis > 0 and profit_value is not None else None
        exch = pos_exchange_map.get(pos["symbol"], "EGX")
        mkt_meta: Dict[str, Any] = {}
        if exch != "EGX" and get_market_config is not None:
            cfg = get_market_config(exch)
            mkt_meta = {"exchange": cfg.exchange, "market": cfg.ui_code, "currency": cfg.currency_ar}
        enriched.append(
            {
                **pos,
                **mkt_meta,
                "last_price": last_price,
                "market_value": market_value,
                "cost_basis": cost_basis,
                "profit_pct": profit_pct,
                "profit_value": profit_value,
                "price_source": "stock_prices" if last_price is not None else "unavailable",
                "price_updated_at": price_dates.get(pos["symbol"]),
            }
        )

    has_unknown_cost = any(p["cost_basis"] is None for p in enriched)
    total_cost = None if has_unknown_cost else sum(p["cost_basis"] or 0.0 for p in enriched)
    has_unknown_value = any(p["market_value"] is None for p in enriched)
    known_value = sum(p["market_value"] or 0.0 for p in enriched)
    total_value = None if has_unknown_value else known_value
    total_profit = None if (total_cost is None or total_value is None) else (total_value - total_cost)
    equity = None if total_value is None else (total_value + cash)

    sorted_pos = sorted(enriched, key=lambda x: x.get("market_value") or 0.0, reverse=True)
    top_pos = sorted_pos[0] if sorted_pos else None
    top_pct = (((top_pos.get("market_value") or 0.0) / equity) * 100.0) if (equity and equity > 0 and top_pos) else 0.0
    cash_pct = ((cash / equity) * 100.0) if (equity and equity > 0) else 0.0
    diversification = "جيد" if len(enriched) >= 5 and top_pct < 40 else ("متوسط" if len(enriched) >= 3 and top_pct < 60 else "منخفض")

    suggestions: List[str] = []
    if top_pct >= 50 and top_pos and top_pos.get("symbol"):
        suggestions.append(f"مركز {top_pos['symbol']} يمثل {_fmt_num(top_pct, 1)}% من قيمة المحفظة؛ راجع التركيز قبل زيادة المركز.")
    if cash_pct < 10 and equity is not None and equity > 0:
        suggestions.append("السيولة أقل من 10% من قيمة المحفظة؛ احتفظ باحتياطي مناسب حسب خطتك.")
    if 0 < len(enriched) < 3:
        suggestions.append("عدد المراكز قليل؛ التنويع بين أكثر من سهم وقطاع قد يقلل أثر هبوط سهم واحد.")

    totals_by_market: Dict[str, Dict[str, Any]] = {}
    if non_egx_groups:
        seen_mkts: Dict[str, str] = {}
        for x in enriched:
            m_lbl = str(x.get("market") or "EGX")
            if m_lbl not in seen_mkts:
                seen_mkts[m_lbl] = str(x.get("currency") or "ج.م")
        for m_lbl, curr_lbl in seen_mkts.items():
            sub = [x for x in enriched if str(x.get("market") or "EGX") == m_lbl]
            if sub:
                sub_cost = sum(x["cost_basis"] or 0.0 for x in sub) if all(x["cost_basis"] is not None for x in sub) else None
                sub_val = sum(x["market_value"] or 0.0 for x in sub) if all(x["market_value"] is not None for x in sub) else None
                sub_pnl = (sub_val - sub_cost) if (sub_val is not None and sub_cost is not None) else None
                totals_by_market[m_lbl] = {
                    "currency": curr_lbl,
                    "positions_count": len(sub),
                    "cost_basis": round(sub_cost, 2) if sub_cost is not None else None,
                    "market_value": round(sub_val, 2) if sub_val is not None else None,
                    "profit_value": round(sub_pnl, 2) if sub_pnl is not None else None,
                }

    snapshot_out: Dict[str, Any] = {
        "ok": True,
        "message": "محفظتك فاضية حالياً. ابعتلي صورة محفظتك أو قولي الأسهم اللي معاك وهضيفها فوراً." if not positions else f"محفظتك فيها {len(positions)} سهم.",
        "positions": enriched,
        "cash_balance": cash,
        "watch_positions": [{"symbol": w["symbol"], "name": w["name"], "last_price": latest_prices.get(w["symbol"])} for w in watch_positions],
        "totals": {
            "positions_count": len(positions),
            "cost_basis": total_cost,
            "market_value": total_value,
            "profit_value": total_profit,
            "profit_pct": ((total_profit / total_cost) * 100.0) if (total_cost and total_cost > 0 and total_profit is not None) else None,
            "equity": equity,
        },
        "analysis": {
            "top_symbol": top_pos["symbol"] if top_pos else None,
            "top_position_pct": top_pct,
            "cash_pct": cash_pct,
            "diversification": diversification,
            "suggestions": suggestions,
        },
    }
    if totals_by_market:
        snapshot_out["totals_by_market"] = totals_by_market
    return snapshot_out


def _portfolio_add(sb: Any, user_id: str, symbol: str, quantity: float, entry_price: Optional[float]) -> Dict[str, Any]:
    sym = symbol.strip().upper()
    if not re.match(r"^[A-Z0-9]{2,10}$", sym):
        return {"ok": False, "message": f"رمز السهم «{symbol}» غير صالح."}
    if quantity <= 0:
        return {"ok": False, "message": "عدد الأسهم لازم يكون رقم أكبر من صفر."}
    if not _symbol_exists_in_market(sb, sym):
        return {"ok": False, "message": f"الرمز {sym} مش موجود في البورصة المصرية. اتأكد من كتابة الرمز الصح (مثلاً COMI أو EAST)."}

    existing = next((p for p in _fetch_open_positions(sb, user_id) if p["symbol"] == sym), None)
    if not existing:
        ok, msg = _can_add_portfolio_positions(sb, user_id, 1)
        if not ok:
            return {"ok": False, "message": msg}
    name = _fetch_stock_name(sb, sym)

    if existing:
        old_qty = existing.get("quantity") or 0.0
        new_qty = old_qty + quantity
        if existing.get("entry_price") and entry_price:
            avg_entry = ((existing["entry_price"] * old_qty) + (entry_price * quantity)) / new_qty
        else:
            avg_entry = entry_price if entry_price is not None else existing.get("entry_price")
        sb.table("positions").update({"quantity": new_qty, "entry_price": avg_entry, "name": existing.get("name") or name}).eq("id", existing["id"]).execute()
        _record_position_event(sb, user_id, existing["id"], "portfolio_add", {"symbol": sym, "quantity": quantity, "entry_price": entry_price})
        return {"ok": True, "message": f"تمام ✅ زودت {quantity} سهم من {sym} — إجمالي حوزتك الآن {new_qty} سهم بسعر متوسط {_fmt_num(avg_entry)} ج.م."}

    inserted, err = _insert_position_row(
        sb,
        {"user_id": user_id, "symbol": sym, "name": name, "quantity": quantity, "entry_price": entry_price, "status": "open", "source": "chatbot"},
    )
    if err:
        return {"ok": False, "message": "فشل حفظ السهم مؤقتًا."}
    _record_position_event(sb, user_id, (inserted or {}).get("id"), "portfolio_add", {"symbol": sym, "quantity": quantity, "entry_price": entry_price})
    if entry_price:
        return {"ok": True, "message": f"تمام ✅ ضفت {quantity} سهم من {sym} على محفظتك بسعر {_fmt_num(entry_price)} ج.م."}
    return {"ok": True, "message": f"تمام ✅ ضفت {quantity} سهم من {sym} على محفظتك."}


def _portfolio_bulk_add(sb: Any, user_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    validated: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        sym = str(item.get("symbol") or "").strip().upper()
        qty = _positive_float(item.get("quantity"))
        price = _positive_float(item.get("price"))
        if not re.match(r"^[A-Z0-9]{2,10}$", sym) or qty is None:
            continue
        validated.append({"symbol": sym, "quantity": qty, "price": price})

    if not validated:
        return {"ok": False, "message": "تأكد من اختيار رموز أسهم صحيحة وتحديد كميات صالحة أكبر من الصفر."}

    open_positions = _fetch_open_positions(sb, user_id)
    existing_syms = {p["symbol"] for p in open_positions}
    new_distinct = {item["symbol"] for item in validated if item["symbol"] not in existing_syms}
    if new_distinct:
        ok, msg = _can_add_portfolio_positions(sb, user_id, len(new_distinct))
        if not ok:
            return {"ok": False, "message": msg}

    success_count = 0
    for item in validated:
        existing = next((p for p in open_positions if p["symbol"] == item["symbol"]), None)
        name = _fetch_stock_name(sb, item["symbol"])
        if existing:
            old_qty = existing.get("quantity") or 0.0
            new_qty = old_qty + item["quantity"]
            avg_entry = (
                ((existing["entry_price"] * old_qty) + (item["price"] * item["quantity"])) / new_qty
                if existing.get("entry_price") and item["price"]
                else (item["price"] if item["price"] is not None else existing.get("entry_price"))
            )
            try:
                sb.table("positions").update({"quantity": new_qty, "entry_price": avg_entry, "name": existing.get("name") or name}).eq("id", existing["id"]).execute()
                success_count += 1
                _record_position_event(sb, user_id, existing["id"], "portfolio_add", item)
            except Exception:
                pass
        else:
            inserted, err = _insert_position_row(
                sb,
                {"user_id": user_id, "symbol": item["symbol"], "name": name, "quantity": item["quantity"], "entry_price": item["price"], "status": "open", "source": "chatbot"},
            )
            if not err:
                success_count += 1
                _record_position_event(sb, user_id, (inserted or {}).get("id"), "portfolio_add", item)

    return {
        "ok": success_count > 0,
        "message": f"تم بنجاح حفظ وإضافة {success_count} سهم إلى محفظتك ✅" if success_count > 0 else "تعذر حفظ الأسهم. حاول مرة أخرى.",
        "addedCount": success_count,
    }


def _portfolio_remove(sb: Any, user_id: str, symbol: str) -> Dict[str, Any]:
    sym = symbol.strip().upper()
    positions = _fetch_open_positions(sb, user_id)
    existing = next((p for p in positions if p["symbol"] == sym), None)
    if not existing:
        tail = f"الأسهم الحالية: {'، '.join(p['symbol'] for p in positions)}." if positions else "محفظتك فاضية."
        return {"ok": False, "message": f"مفيش سهم {sym} في محفظتك. {tail}"}
    try:
        sb.table("positions").update({"status": "removed", "status_at": datetime.now(timezone.utc).isoformat()}).eq("id", existing["id"]).eq("user_id", user_id).execute()
    except Exception:
        try:
            sb.table("positions").delete().eq("id", existing["id"]).eq("user_id", user_id).execute()
        except Exception:
            return {"ok": False, "message": "فشل حذف السهم مؤقتًا."}
    _record_position_event(sb, user_id, existing["id"], "portfolio_remove", {"symbol": sym, "quantity": existing.get("quantity")})
    return {"ok": True, "message": f"تم ✅ شيلت {sym} من محفظتك."}


@router.get("/api/portfolio")
def get_portfolio(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse(
            {"ok": False, "requiresAuth": True, "message": "يجب تسجيل الدخول أولاً لإضافة الأسهم إلى محفظتك الشخصية."},
            status_code=401,
            headers=_PRIVATE_NO_STORE,
        )
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"ok": False, "message": "Database unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)
    try:
        uid = viewer["user_id"]
        snapshot = _build_portfolio_snapshot(sb, uid)
        pro, limit = _portfolio_limit_for_user(sb, uid)
        market_symbols = _load_market_symbols_list()
        return JSONResponse(
            {**snapshot, "market_symbols": market_symbols, "portfolio_limit": limit, "is_pro": pro},
            headers=_PRIVATE_NO_STORE,
        )
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=500, headers=_PRIVATE_NO_STORE)


@router.post("/api/portfolio")
async def post_portfolio(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse(
            {"ok": False, "requiresAuth": True, "error": "Unauthorized", "message": "يجب تسجيل الدخول أولاً لإضافة الأسهم إلى محفظتك الشخصية."},
            status_code=401,
            headers=_PRIVATE_NO_STORE,
        )
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"ok": False, "message": "Database unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(body, dict):
        body = {}
    uid = viewer["user_id"]
    action = str(body.get("action") or "")
    symbol = str(body.get("symbol") or "").strip().upper()
    quantity = _finite_float(body.get("quantity"))
    price = _finite_float(body.get("price"))

    if action in ("extract_and_save", "ai_extract_and_save"):
        text = str(body.get("text") or "").strip()
        user_query = str(body.get("userQuery") or "").strip()
        suggested = [str(s) for s in body.get("suggestedButtons", [])] if isinstance(body.get("suggestedButtons"), list) else []
        if not text and not user_query:
            return JSONResponse({"ok": False, "message": "محتوى الرسالة فارغ، لا يمكن استخراج الأسهم."}, status_code=400, headers=_PRIVATE_NO_STORE)
        extracted = _call_portfolio_extraction_llm(text, user_query, suggested)
        if not extracted:
            return JSONResponse({"ok": False, "message": "لم يكتشف الذكاء الاصطناعي أي أسهم صريحة للبورصة المصرية في هذا الرد لحفظها."}, headers=_PRIVATE_NO_STORE)

        prepared: List[Dict[str, Any]] = []
        for item in extracted:
            sym = re.sub(r"[^A-Z0-9]", "", str(item.get("symbol") or "").strip().upper())
            if len(sym) < 2 or len(sym) > 8:
                continue
            qty = _positive_float(item.get("quantity")) or 100.0
            p = _positive_float(item.get("price"))
            if p is None:
                try:
                    p_row = _select_one(sb.table("stock_prices").select("close").eq("symbol", sym).order("date", desc=True)) or {}
                    p = _positive_float(p_row.get("close"))
                except Exception:
                    pass
            prepared.append({"symbol": sym, "quantity": qty, "price": p or 10.0})

        if not prepared:
            return JSONResponse({"ok": False, "message": "لم يتم التعرف على رموز صالحة لأسهم البورصة المصرية."}, headers=_PRIVATE_NO_STORE)

        pro, limit = _portfolio_limit_for_user(sb, uid)
        existing_syms = {p["symbol"] for p in _fetch_open_positions(sb, uid) if (p.get("quantity") or 0) > 0}
        new_distinct = {p["symbol"] for p in prepared if p["symbol"] not in existing_syms}
        if len(existing_syms) + len(new_distinct) > limit:
            tail = "" if pro else f" قم بالترقية لباقة Pro لإدارة حتى {plan_limits('pro')['portfolio_stocks']} سهم وتفعيل تنبيهات السوينج الحية!"
            return JSONResponse(
                {
                    "ok": False,
                    "isQuotaReached": True,
                    "limit": limit,
                    "currentCount": len(existing_syms),
                    "attemptedCount": len(new_distinct),
                    "stocks": prepared,
                    "message": f"الحد الأقصى لمحفظتك {limit} سهم (محفظتك الحالية بها {len(existing_syms)} أسهم).{tail}",
                },
                headers=_PRIVATE_NO_STORE,
            )
        save_res = _portfolio_bulk_add(sb, uid, prepared)
        added_cnt = save_res.get("addedCount") or len(prepared)
        return JSONResponse(
            {
                **save_res,
                "isQuotaReached": (not save_res["ok"]) and ("الخطة المجانية" in save_res["message"] or "الحد الأقصى" in save_res["message"]),
                "stocks": prepared,
                "addedCount": added_cnt,
                "message": f"تم بنجاح حفظ {added_cnt} أسهم في محفظتك الشخصية!" if save_res["ok"] else save_res["message"],
            },
            headers=_PRIVATE_NO_STORE,
        )

    if action == "bulk_add":
        items = body.get("items")
        if not isinstance(items, list) or not items:
            return JSONResponse({"ok": False, "message": "قائمة الأسهم مطلوبة"}, status_code=400, headers=_PRIVATE_NO_STORE)
        return JSONResponse(_portfolio_bulk_add(sb, uid, items), headers=_PRIVATE_NO_STORE)

    if action == "add":
        if not symbol or quantity is None or quantity <= 0:
            return JSONResponse({"ok": False, "message": "symbol و quantity مطلوبان"}, status_code=400, headers=_PRIVATE_NO_STORE)
        pro, limit = _portfolio_limit_for_user(sb, uid)
        current_syms = {p["symbol"] for p in _fetch_open_positions(sb, uid) if (p.get("quantity") or 0) > 0}
        if symbol not in current_syms and len(current_syms) >= limit:
            return JSONResponse(
                {"ok": False, "isQuotaReached": True, "limit": limit, "message": f"وصلت للحد الأقصى {limit} أسهم مختلفة في المحفظة. احذف مركزاً أو قم بالترقية لإضافة سهم آخر."},
                status_code=403,
                headers=_PRIVATE_NO_STORE,
            )
        return JSONResponse(_portfolio_add(sb, uid, symbol, quantity, price), headers=_PRIVATE_NO_STORE)

    if action == "update":
        if not symbol:
            return JSONResponse({"ok": False, "message": "symbol مطلوب"}, status_code=400, headers=_PRIVATE_NO_STORE)
        positions = _fetch_open_positions(sb, uid)
        existing = next((p for p in positions if p["symbol"] == symbol), None)
        if not existing:
            tail = f"الأسهم الحالية: {'، '.join(p['symbol'] for p in positions)}." if positions else "محفظتك فاضية."
            return JSONResponse({"ok": False, "message": f"مفيش سهم {symbol} مفتوح في محفظتك. {tail}"}, headers=_PRIVATE_NO_STORE)
        updates: Dict[str, Any] = {}
        if quantity is not None and quantity >= 0:
            if quantity == 0:
                return JSONResponse(_portfolio_remove(sb, uid, symbol), headers=_PRIVATE_NO_STORE)
            updates["quantity"] = quantity
        if price is not None and price > 0:
            updates["entry_price"] = price
        if not updates:
            return JSONResponse({"ok": False, "message": "محتاج أعرف العدد الجديد أو السعر الجديد للتعديل."}, headers=_PRIVATE_NO_STORE)
        sb.table("positions").update(updates).eq("id", existing["id"]).execute()
        _record_position_event(sb, uid, existing["id"], "portfolio_update", {"symbol": symbol, **updates})
        q_txt = f"العدد بقى {updates['quantity']} سهم" if "quantity" in updates else ""
        join_txt = " و" if ("quantity" in updates and "entry_price" in updates) else ""
        p_txt = f"السعر {_fmt_num(updates['entry_price'])} ج.م" if "entry_price" in updates else ""
        return JSONResponse({"ok": True, "message": f"تم ✅ عدلت {symbol}: {q_txt}{join_txt}{p_txt}."}, headers=_PRIVATE_NO_STORE)

    if action == "remove":
        if not symbol:
            return JSONResponse({"ok": False, "message": "symbol مطلوب"}, status_code=400, headers=_PRIVATE_NO_STORE)
        return JSONResponse(_portfolio_remove(sb, uid, symbol), headers=_PRIVATE_NO_STORE)

    if action == "sell":
        if not symbol:
            return JSONResponse({"ok": False, "message": "symbol مطلوب"}, status_code=400, headers=_PRIVATE_NO_STORE)
        positions = _fetch_open_positions(sb, uid)
        existing = next((p for p in positions if p["symbol"] == symbol), None)
        if not existing:
            tail = f"الأسهم الحالية: {'، '.join(p['symbol'] for p in positions)}." if positions else "محفظتك فاضية."
            return JSONResponse({"ok": False, "message": f"مفيش سهم {symbol} مفتوح في محفظتك. {tail}"}, headers=_PRIVATE_NO_STORE)
        held = existing.get("quantity")
        qty_to_sell = quantity if quantity is not None else held
        if held is not None and qty_to_sell is not None and qty_to_sell > held:
            qty_to_sell = held
        if qty_to_sell is None or qty_to_sell <= 0:
            return JSONResponse({"ok": False, "message": "عدد الأسهم اللي هتبيعها لازم يكون أكبر من صفر."}, headers=_PRIVATE_NO_STORE)
        sell_price = price
        if sell_price is None:
            try:
                pr = sb.table("stock_prices").select("close").eq("symbol", symbol).eq("exchange", "EGX").order("date", desc=True).limit(1).execute()
                rows = getattr(pr, "data", None) or []
                if rows:
                    sell_price = _finite_float(rows[0].get("close"))
            except Exception:
                pass
        if sell_price is None:
            sell_price = existing.get("entry_price")
        if sell_price is None:
            return JSONResponse({"ok": False, "message": f"محتاج أعرف سعر البيع عشان أسجل بيع {symbol}."}, headers=_PRIVATE_NO_STORE)

        proceeds = qty_to_sell * sell_price
        is_full_sale = held is None or qty_to_sell >= held
        if is_full_sale:
            sb.table("positions").update({"status": "closed_manual", "status_at": datetime.now(timezone.utc).isoformat(), "status_price": sell_price}).eq("id", existing["id"]).execute()
        else:
            sb.table("positions").update({"quantity": (held or 0.0) - qty_to_sell}).eq("id", existing["id"]).execute()
        cash = _fetch_cash_balance(sb, uid)
        _upsert_cash_balance(sb, uid, cash + proceeds)
        _record_position_event(
            sb,
            uid,
            existing["id"],
            "portfolio_sell",
            {
                "symbol": symbol,
                "quantity": qty_to_sell,
                "sell_price": sell_price,
                "proceeds": proceeds,
                "entry_price": existing["entry_price"] if (existing.get("entry_price") or 0) > 0 else None,
            },
        )
        suffix = "السهم اتقفل من المحفظة." if is_full_sale else f"باقي معاك {(held or 0.0) - qty_to_sell} سهم."
        return JSONResponse(
            {"ok": True, "message": f"تم ✅ سجلت بيع {qty_to_sell} سهم من {symbol} بسعر {_fmt_num(sell_price)} ج.م (إجمالي {_fmt_num(proceeds)} ج.م اتضافت للسيولة). {suffix}"},
            headers=_PRIVATE_NO_STORE,
        )

    if action == "cash_set":
        if quantity is None or quantity < 0:
            return JSONResponse({"ok": False, "message": "قيمة السيولة مطلوبة"}, status_code=400, headers=_PRIVATE_NO_STORE)
        _upsert_cash_balance(sb, uid, quantity)
        _record_position_event(sb, uid, None, "portfolio_cash_set", {"amount": quantity})
        return JSONResponse({"ok": True, "message": f"تم ✅ السيولة في محفظتك الآن {_fmt_num(quantity)} ج.م."}, headers=_PRIVATE_NO_STORE)

    if action == "cash_add":
        if quantity is None or quantity <= 0:
            return JSONResponse({"ok": False, "message": "قيمة الإيداع مطلوبة"}, status_code=400, headers=_PRIVATE_NO_STORE)
        cur = _fetch_cash_balance(sb, uid)
        upd = cur + quantity
        _upsert_cash_balance(sb, uid, upd)
        _record_position_event(sb, uid, None, "portfolio_cash_add", {"amount": quantity, "previous": cur, "updated": upd})
        return JSONResponse({"ok": True, "message": f"تم ✅ ضفت {_fmt_num(quantity)} ج.م للسيولة — الإجمالي الآن {_fmt_num(upd)} ج.م."}, headers=_PRIVATE_NO_STORE)

    return JSONResponse({"ok": False, "message": "action غير معروف"}, status_code=400, headers=_PRIVATE_NO_STORE)


def _load_symbol_daily_history(sb: Any, symbol: str) -> List[Dict[str, Any]]:
    sym_u = symbol.strip().upper()
    found, cached = _DAILY_HISTORY_CACHE.get(sym_u)
    if found and isinstance(cached, list):
        return cached

    def _fetch() -> Tuple[bool, List[Dict[str, Any]]]:
        try:
            exch = "INDX" if sym_u == "EGX30" else "EGX"
            res = (
                sb.table("stock_prices")
                .select("date,close,adjusted_close")
                .eq("symbol", sym_u)
                .eq("exchange", exch)
                .order("date", desc=True)
                .limit(300)
                .execute()
            )
            return True, getattr(res, "data", None) or []
        except Exception:
            return False, []

    ok, rows = _DAILY_HISTORY_SF.do(sym_u, _fetch)
    if ok:
        _DAILY_HISTORY_CACHE.set(sym_u, rows, ttl=600.0)
    return rows


def _max_drawdown(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    peak = values[0]
    worst = 0.0
    for val in values:
        if val > peak:
            peak = val
        if peak > 0:
            worst = min(worst, (val / peak - 1.0) * 100.0)
    return worst


def _build_daily_overview(positions: List[Dict[str, Any]], histories: Dict[str, List[Dict[str, Any]]], benchmark: List[Dict[str, Any]]) -> Dict[str, Any]:
    sessions = sorted([p for p in benchmark if _positive_float(p.get("close")) is not None], key=lambda r: str(r.get("date") or ""))
    latest = sessions[-1] if sessions else None
    previous = sessions[-2] if len(sessions) >= 2 else None
    adjusted = True
    out_holdings: List[Dict[str, Any]] = []

    by_date_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for sym, rows in histories.items():
        by_date_map[sym] = {str(r.get("date") or ""): r for r in rows}

    for pos in positions:
        qty = _positive_float(pos.get("quantity"))
        if pos.get("status") != "open" or qty is None:
            continue
        sym_hist = by_date_map.get(pos["symbol"], {})
        cur = sym_hist.get(str(latest["date"])) if latest else None
        prev = sym_hist.get(str(previous["date"])) if previous else None
        raw = _positive_float(cur.get("close")) if cur else None
        old_raw = _positive_float(prev.get("close")) if prev else None
        cur_adj = _positive_float(cur.get("adjusted_close")) if cur else None
        prev_adj = _positive_float(prev.get("adjusted_close")) if prev else None
        use_adj = cur_adj is not None and prev_adj is not None
        if not use_adj:
            adjusted = False
        ratio: Optional[float] = None
        if raw is not None and old_raw is not None:
            ratio = (cur_adj / prev_adj) if (use_adj and cur_adj and prev_adj) else (raw / old_raw)
        value = raw * qty if raw is not None else None
        change = (value - value / ratio) if (ratio is not None and ratio > 0 and value is not None) else None
        out_holdings.append(
            {
                "symbol": pos["symbol"],
                "sector": pos.get("sector") or None,
                "value": value,
                "change": change,
                "changePct": None if ratio is None else (ratio - 1.0) * 100.0,
            }
        )

    complete = len(out_holdings) > 0 and all(h["change"] is not None for h in out_holdings)
    total_change = sum(float(h["change"]) for h in out_holdings) if complete else None
    cur_val = sum(float(h["value"]) for h in out_holdings) if complete else None
    prior_val = (cur_val - total_change) if (cur_val is not None and total_change is not None) else None
    return {
        "date": latest["date"] if latest else None,
        "previousDate": previous["date"] if previous else None,
        "holdings": out_holdings,
        "complete": complete,
        "adjusted": adjusted,
        "change": total_change,
        "changePct": ((total_change / prior_val) * 100.0) if (prior_val and total_change is not None) else None,
        "benchmarkPct": ((float(latest["close"]) / float(previous["close"]) - 1.0) * 100.0) if (latest and previous) else None,
    }


def _compare_current_basket(holdings: List[Dict[str, Any]], histories: Dict[str, List[Dict[str, Any]]], benchmark: List[Dict[str, Any]], days: int) -> Dict[str, Any]:
    active = [h for h in holdings if h.get("status") == "open" and _positive_float(h.get("quantity")) is not None]
    index_rows = sorted([r for r in benchmark if _positive_float(r.get("close")) is not None], key=lambda r: str(r.get("date") or ""))
    anchor = index_rows[-1]["date"] if index_rows else None
    if anchor:
        cutoff_dt = datetime.fromisoformat(f"{anchor}T00:00:00+00:00") - timedelta(days=days)
        from_date = cutoff_dt.strftime("%Y-%m-%d")
    else:
        from_date = "1970-01-01"
    index = {str(r["date"]): float(r["close"]) for r in index_rows if str(r["date"]) >= from_date}

    series: List[Dict[str, Any]] = []
    adjusted = True
    for h in active:
        prices = [p for p in histories.get(h["symbol"], []) if str(p.get("date") or "") in index and _positive_float(p.get("close")) is not None]
        if len(prices) < 2:
            continue
        use_adj = all(_positive_float(p.get("adjusted_close")) is not None for p in prices)
        if not use_adj:
            adjusted = False
        series.append(
            {
                "symbol": h["symbol"],
                "quantity": float(h["quantity"]),
                "prices": {str(p["date"]): float(p["adjusted_close"] if use_adj else p["close"]) for p in prices},
            }
        )

    dates = sorted([d for d in index.keys() if series and all(d in s["prices"] for s in series)])
    basket_vals = [sum(s["quantity"] * s["prices"][d] for s in series) for d in dates]
    points: List[Dict[str, Any]] = []
    if len(dates) >= 2 and basket_vals and basket_vals[0] > 0 and index.get(dates[0]):
        base = basket_vals[0]
        bench_base = index[dates[0]]
        for idx, d in enumerate(dates):
            points.append({"date": d, "basket": (basket_vals[idx] / base) * 100.0, "benchmark": (index[d] / bench_base) * 100.0})

    last = points[-1] if points else None
    inc_syms = [s["symbol"] for s in series]
    return {
        "days": days,
        "from": points[0]["date"] if points else None,
        "to": last["date"] if last else None,
        "points": points,
        "returnPct": (last["basket"] - 100.0) if last else None,
        "benchmarkPct": (last["benchmark"] - 100.0) if last else None,
        "excessPct": (last["basket"] - last["benchmark"]) if last else None,
        "maxDrawdownPct": _max_drawdown([p["basket"] for p in points]),
        "benchmarkDrawdownPct": _max_drawdown([p["benchmark"] for p in points]),
        "includedSymbols": inc_syms,
        "excludedSymbols": [h["symbol"] for h in active if h["symbol"] not in inc_syms],
        "adjusted": adjusted,
    }


@router.get("/api/portfolio/performance")
def get_portfolio_performance(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)

    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"detail": "Portfolio performance is unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    try:
        pos_res = sb.table("positions").select("id,symbol,quantity,entry_price,status").eq("user_id", uid).eq("status", "open").limit(101).execute()
        holdings: List[Dict[str, Any]] = list(getattr(pos_res, "data", None) or [])
        if len(holdings) > 100:
            raise ValueError("Portfolio exceeds supported holding count")

        if holdings:
            try:
                sec_res = sb.table("market_heatmap").select("symbol,sector").in_("symbol", [h["symbol"] for h in holdings]).limit(100).execute()
                sec_map = {str(r["symbol"]): r.get("sector") for r in (getattr(sec_res, "data", None) or [])}
                for h in holdings:
                    h["sector"] = sec_map.get(h["symbol"])
            except Exception:
                pass

        sale_events: List[Dict[str, Any]] = []
        history_truncated = False
        for page in range(10):
            ev_res = (
                sb.table("position_events")
                .select("id,position_id,event_at,event_type,payload")
                .eq("user_id", uid)
                .eq("event_type", "portfolio_sell")
                .order("event_at", desc=True)
                .order("id", desc=True)
                .range(page * 1000, page * 1000 + 999)
                .execute()
            )
            rows = getattr(ev_res, "data", None) or []
            sale_events.extend(rows)
            if len(rows) < 1000:
                break
            if page == 9:
                history_truncated = True

        symbols = list({h["symbol"] for h in holdings if (_finite_float(h.get("quantity")) or 0) > 0})
        if "EGX30" not in symbols:
            symbols.append("EGX30")
        histories: Dict[str, List[Dict[str, Any]]] = {}
        for sym in symbols:
            histories[sym] = _load_symbol_daily_history(sb, sym)

        recent_res = (
            sb.table("position_events")
            .select("id,position_id,event_at,event_type,payload")
            .eq("user_id", uid)
            .in_("event_type", ["portfolio_add", "portfolio_sell", "portfolio_cash_add", "portfolio_cash_set", "portfolio_cash_withdraw", "portfolio_buy"])
            .order("event_at", desc=True)
            .limit(50)
            .execute()
        )
        recent_events = getattr(recent_res, "data", None) or []

        report_holdings: List[Dict[str, Any]] = []
        for pos in holdings:
            qty = _positive_float(pos.get("quantity"))
            if pos.get("status") != "open" or qty is None:
                continue
            valid_hist = sorted([r for r in histories.get(pos["symbol"], []) if _positive_float(r.get("close")) is not None], key=lambda r: str(r.get("date") or ""), reverse=True)
            latest_p = valid_hist[0] if valid_hist else None
            price_val = _positive_float(latest_p.get("close")) if latest_p else None
            entry = _positive_float(pos.get("entry_price"))
            cost = qty * entry if entry is not None else None
            value = qty * price_val if price_val is not None else None
            profit = (value - cost) if (cost is not None and value is not None) else None
            report_holdings.append(
                {
                    "symbol": pos["symbol"],
                    "sector": pos.get("sector") or None,
                    "quantity": qty,
                    "value": value,
                    "cost": cost,
                    "profit": profit,
                    "profitPct": ((profit / cost) * 100.0) if (profit is not None and cost) else None,
                    "priceDate": latest_p.get("date") if latest_p else None,
                }
            )

        realized_total = 0.0
        known_sales = 0
        unknown_sales = 0
        for ev in sale_events:
            if ev.get("event_type") != "portfolio_sell":
                continue
            payload = ev.get("payload") or {}
            qty = _finite_float(payload.get("quantity"))
            sell = _finite_float(payload.get("sell_price"))
            entry = _finite_float(payload.get("entry_price"))
            fees = _finite_float(payload.get("fees"))
            fees_val = 0.0 if fees is None else fees
            if not qty or qty <= 0 or not sell or sell <= 0 or not entry or entry <= 0 or fees_val < 0:
                unknown_sales += 1
                continue
            realized_total += qty * (sell - entry) - fees_val
            known_sales += 1

        bench = histories.get("EGX30", [])
        bench_dates = sorted([str(r["date"]) for r in bench if _positive_float(r.get("close")) is not None])
        unrealized = sum(float(h["profit"]) for h in report_holdings) if all(h["profit"] is not None for h in report_holdings) else None
        payload = {
            "asOf": bench_dates[-1] if bench_dates else None,
            "holdings": report_holdings,
            "unrealized": unrealized,
            "realized": realized_total if (known_sales > 0 or unknown_sales == 0) else None,
            "knownSales": known_sales,
            "unknownSales": unknown_sales,
            "historyTruncated": history_truncated,
            "daily": _build_daily_overview(holdings, histories, bench),
            "transactions": recent_events,
            "comparisons": [_compare_current_basket(holdings, histories, bench, days) for days in (30, 90, 365)],
        }
        return JSONResponse(payload, headers=_PRIVATE_NO_STORE)
    except Exception:
        return JSONResponse({"detail": "Portfolio performance is unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)


_TRANSACTION_ERRORS: Dict[str, str] = {
    "invalid_action": "نوع العملية غير صالح.",
    "invalid_date_or_request": "تحقق من التاريخ؛ لا يمكن تسجيل عملية مستقبلية.",
    "invalid_fees": "العمولات يجب أن تكون صفرًا أو أكثر.",
    "invalid_trade": "اختر السهم وأدخل كمية وسعرًا أكبر من صفر.",
    "invalid_cash_amount": "أدخل مبلغًا أكبر من صفر.",
    "insufficient_cash": "السيولة المسجلة لا تكفي لهذه العملية.",
    "quantity_exceeds_holding": "كمية البيع أكبر من حيازتك الحالية.",
    "unknown_symbol": "السهم غير موجود في دليل الأسهم.",
    "fees_exceed_proceeds": "العمولات أكبر من حصيلة البيع.",
    "holding_limit": "وصلت لحد عدد الأسهم في خطتك الحالية.",
    "date_before_last_transaction": "التاريخ أقدم من آخر عملية مسجلة؛ سجّل العمليات بالترتيب.",
    "request_conflict": "تغيّرت بيانات طلب سابق. أغلق النموذج وافتحه لطلب جديد.",
    "duplicate_holdings": "توجد حيازات مكررة للسهم؛ راجعها قبل التسجيل.",
}


@router.post("/api/portfolio/transactions")
async def post_portfolio_transactions(request: Request):
    viewer = resolve_verified_viewer(request)
    token = extract_jwt_token(request)
    if not viewer.get("authenticated") or not token:
        return JSONResponse({"ok": False, "message": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(body, dict):
        body = {}

    action = str(body.get("action") or "")
    symbol = str(body.get("symbol") or "").strip().upper()
    quantity = _finite_float(body.get("quantity"))
    price = _finite_float(body.get("price"))
    amount = _finite_float(body.get("amount"))
    raw_fees = _finite_float(body.get("fees"))
    fees = 0.0 if raw_fees is None else raw_fees
    occurred_raw = str(body.get("occurredAt") or "")
    request_id = str(body.get("requestId") or "")

    err_code: Optional[str] = None
    parsed_dt = _parse_dt(occurred_raw)
    if action not in ("buy", "sell", "deposit", "withdraw"):
        err_code = "invalid_action"
    elif (
        not re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", request_id, re.IGNORECASE)
        or parsed_dt is None
        or parsed_dt > datetime.now(timezone.utc)
    ):
        err_code = "invalid_date_or_request"
    elif fees < 0:
        err_code = "invalid_fees"
    elif action in ("buy", "sell"):
        if not re.match(r"^[A-Z0-9]{2,10}$", symbol) or quantity is None or price is None or quantity <= 0 or price <= 0:
            err_code = "invalid_trade"
    elif amount is None or amount <= 0 or fees != 0:
        err_code = "invalid_cash_amount"

    if err_code:
        return JSONResponse(
            {"ok": False, "message": _TRANSACTION_ERRORS.get(err_code, "بيانات العملية غير صالحة.")},
            status_code=400,
            headers=_PRIVATE_NO_STORE,
        )

    sb_url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").strip().rstrip("/")
    anon_key = (os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    if not sb_url or not anon_key:
        return JSONResponse({"ok": False, "message": "تعذر تأكيد حفظ العملية. أعد المحاولة بنفس الطلب."}, status_code=503, headers=_PRIVATE_NO_STORE)

    try:
        rpc_res = requests.post(
            f"{sb_url}/rest/v1/rpc/record_portfolio_transaction",
            headers={
                "apikey": anon_key,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "p_action": action,
                "p_symbol": symbol,
                "p_quantity": quantity,
                "p_price": price,
                "p_amount": amount,
                "p_fees": fees,
                "p_occurred_at": parsed_dt.isoformat().replace("+00:00", "Z"),
                "p_request_id": request_id,
            },
            timeout=10,
        )
        if not rpc_res.ok:
            msg_txt = rpc_res.text
            matched_code = next((k for k in _TRANSACTION_ERRORS if k in msg_txt), None)
            return JSONResponse(
                {"ok": False, "message": _TRANSACTION_ERRORS[matched_code] if matched_code else "سجل العمليات غير متاح حاليًا. لم نؤكد حفظ العملية."},
                status_code=400 if matched_code else 503,
                headers=_PRIVATE_NO_STORE,
            )
        data = rpc_res.json()
        if isinstance(data, dict) and data.get("ok") is True:
            return JSONResponse({"ok": True, "message": "تم تسجيل العملية وتحديث المحفظة والسيولة."}, headers=_PRIVATE_NO_STORE)
        raise RuntimeError("Unconfirmed transaction")
    except Exception:
        return JSONResponse({"ok": False, "message": "تعذر تأكيد حفظ العملية. أعد المحاولة بنفس الطلب."}, status_code=503, headers=_PRIVATE_NO_STORE)


@router.post("/api/user/portfolio/rebalance")
def post_portfolio_rebalance(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    uid = viewer["user_id"]
    email = viewer.get("email", "")
    email_confirmed = bool(viewer.get("email_confirmed", False))

    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "حدث خطأ أثناء تحليل وإعادة تدوير المحفظة"}, status_code=503, headers=_PRIVATE_NO_STORE)

    try:
        today = get_cairo_date_str()
        cal_month_start = f"{today[:7]}-01"

        pos_res = sb.table("positions").select("symbol,quantity,entry_price,current_price,status").eq("user_id", uid).eq("status", "open").limit(100).execute()
        prof_row = _select_one(sb.table("profiles").select("cash_balance").eq("id", uid)) or {}
        sub_res = sb.table("subscriptions").select("plan_id,status,current_period_start,current_period_end").eq("user_id", uid).order("current_period_end", desc=True).limit(10).execute()
        # Canonical chat quota ledger matches web rebalance/auth_guard: Pro is bounded
        # by effective subscription month start, Free counts lifetime rows in ai_chatbot_limits.
        usage_res = sb.table("ai_chatbot_limits").select("date,chat_count").eq("user_id", uid).order("date", desc=True).limit(1000).execute()

        open_positions = [p for p in (getattr(pos_res, "data", None) or []) if (_finite_float(p.get("quantity")) or 0) > 0]
        if not open_positions:
            return JSONResponse(
                {"error": "محفظتك فارغة حالياً. أضف أسهماً إلى محفظتك أولاً لتشغيل إعادة التدوير الذكي."},
                status_code=400,
                headers=_PRIVATE_NO_STORE,
            )

        is_unlimited = is_unlimited_chat_user(uid, email, email_confirmed=email_confirmed)
        q_win = resolve_subscription_quota_window(getattr(sub_res, "data", None) or [])
        user_is_pro = bool(q_win.get("has_chat_pro", q_win["is_pro"])) or is_unlimited
        active_pid = str((q_win["active_sub"] or {}).get("plan_id") or "").strip().lower()
        plan_name = (
            "lifetime"
            if (active_pid in {"lifetime", "pro_lifetime"} or is_unlimited)
            else ("chat_only" if active_pid == "chat_only" else "pro")
        ) if user_is_pro else "free"
        monthly_cap = int(plan_limits(plan_name)["chat_messages_per_month"])
        month_start_str = q_win["effective_month_start_str"] if user_is_pro else cal_month_start
        usage_rows = getattr(usage_res, "data", None) or []
        effective_rows = [r for r in usage_rows if str(r.get("date") or "") >= month_start_str] if user_is_pro else usage_rows
        monthly_used = sum(int(r.get("chat_count") or 0) for r in effective_rows)

        def _rpc_allowed(raw_data: Any) -> bool:
            item = raw_data[0] if isinstance(raw_data, list) and raw_data else raw_data
            return bool(isinstance(item, dict) and item.get("allowed") is True)

        if not is_unlimited:
            if monthly_used >= monthly_cap:
                b_res = sb.rpc("consume_chat_bonus", {"p_user_id": uid}).execute()
                if not _rpc_allowed(getattr(b_res, "data", None)):
                    return JSONResponse(
                        {
                            "error": "LIMIT_REACHED",
                            "detail": f"لقد استهلكت كامل كوتا الشات الذكي ({monthly_cap}/{monthly_cap} رسالة). قم بالترقية إلى باقة Pro للحصول على 350 رسالة شهرياً وإعادة تدوير محفظتك بلا قيود.",
                        },
                        status_code=429,
                        headers=_PRIVATE_NO_STORE,
                    )
            else:
                prior_used = sum(int(r.get("chat_count") or 0) for r in effective_rows if str(r.get("date") or "") < today)
                today_cap = max(0, monthly_cap - prior_used)
                allowed = False
                if today_cap > 0:
                    q_res = sb.rpc("consume_ai_chat_quota", {"p_user_id": uid, "p_date": today, "p_limit": today_cap}).execute()
                    allowed = _rpc_allowed(getattr(q_res, "data", None))
                if not allowed:
                    b_res = sb.rpc("consume_chat_bonus", {"p_user_id": uid}).execute()
                    if not _rpc_allowed(getattr(b_res, "data", None)):
                        return JSONResponse(
                            {
                                "error": "LIMIT_REACHED",
                                "detail": f"لقد استهلكت كوتا الشات المتاحة ({monthly_cap} رسالة). قم بالترقية إلى باقة Pro للمتابعة.",
                            },
                            status_code=429,
                            headers=_PRIVATE_NO_STORE,
                        )
            monthly_used += 1

        remaining_quota = 999 if is_unlimited else max(0, monthly_cap - monthly_used)

        from api.routers.offload_public import _get_fair_value
        fv_report = _get_fair_value("egx")
        fv_map = {str(s.get("symbol") or "").upper(): s for s in (fv_report.get("stocks") or []) if s.get("symbol")}

        ind_res = (
            sb.table("stock_technical_indicators")
            .select("symbol,date,close,volume,ema_20,ema_50,ema_200,sma_200,vwap_20,change_pct,rsi_14,r_vol,atr_14")
            .eq("exchange", "EGX")
            .limit(400)
            .execute()
        )
        ind_map: Dict[str, Dict[str, Any]] = {}
        for row in getattr(ind_res, "data", None) or []:
            sym_u = str(row.get("symbol") or "").strip().upper()
            if sym_u and sym_u not in ind_map:
                ind_map[sym_u] = row

        cash_balance = float(prof_row.get("cash_balance") or 0.0)
        total_stocks_val = 0.0
        raw_holdings: List[Dict[str, Any]] = []
        for pos in open_positions:
            sym = str(pos.get("symbol") or "").strip().upper()
            qty = max(1.0, float(pos.get("quantity") or 100))
            ind = ind_map.get(sym) or {}
            fv = fv_map.get(sym) or {}
            cur_p = float(ind.get("close") or fv.get("currentPrice") or pos.get("current_price") or pos.get("entry_price") or 1.0)
            entry_p = max(0.01, float(pos.get("entry_price") or cur_p))
            mval = qty * cur_p
            total_stocks_val += mval
            raw_holdings.append({"sym": sym, "qty": qty, "entry": entry_p, "currentPrice": cur_p, "marketValue": mval, "ind": ind, "fv": fv})

        total_equity = max(1.0, total_stocks_val + cash_balance)
        total_freed = 0
        holdings_diag: List[Dict[str, Any]] = []
        for h in raw_holdings:
            weight_pct = round((h["marketValue"] / total_equity) * 100.0, 1)
            pnl_pct = round(((h["currentPrice"] - h["entry"]) / h["entry"]) * 100.0, 2) if h["entry"] > 0 else 0.0
            rsi = round(float(h["ind"]["rsi_14"]), 1) if h["ind"].get("rsi_14") is not None else None
            r_vol = round(float(h["ind"]["r_vol"]), 2) if h["ind"].get("r_vol") is not None else None
            ema50 = float(h["ind"].get("ema_50") or h["currentPrice"])
            fair_val = h["fv"].get("fairValue")
            upside_pct = h["fv"].get("upsidePct")
            name_ar = (CANONICAL_EGX_STOCK_NAMES.get(h["sym"]) or {}).get("name_ar") or h["fv"].get("nameAr") or h["sym"]

            action = "HOLD_ACCUMULATE"
            action_label = "احتفاظ واستمرار 🟢"
            trim_pct = 0
            reason = "السهم يتحرك في مسار متوازن فوق دعومه الفنية مع تقييم مالي مقبول."

            below_ema50 = h["currentPrice"] < ema50 * 0.975
            weak_vol = (1.0 if r_vol is None else r_vol) < 0.75
            overvalued = upside_pct is not None and upside_pct <= -15
            overweight = weight_pct >= 42

            if below_ema50 and (weak_vol or (rsi is not None and rsi < 44)):
                action = "ROTATE_OUT"
                action_label = "تدوير السيولة (سهم راكد) 🔄"
                trim_pct = 50
                reason = "السهم يتداول أسفل متوسط 50 يوماً مع ضعف في السيولة النسبية؛ يُنصح بتدوير نصف السيولة لفرصة أسرع زخماً."
            elif overvalued and pnl_pct > 5:
                action = "ROTATE_OUT"
                action_label = "تدوير السيولة (متضخم سعرياً) 🔄"
                trim_pct = 40
                reason = f"السهم يتداول أعلى من سعره العادل المحسوب ({fair_val} ج.م)؛ تدوير 40% يحمي أرباحك."
            elif overweight:
                action = "TRIM_PROFIT"
                action_label = "تخفيف التركز القطاعي 🟡"
                trim_pct = 25
                reason = f"وزن السهم يمثل {weight_pct}% من إجمالي المحفظة وهو تركز مرتفع؛ يُنصح بتخفيف 25% لتوزيع المخاطر."
            elif pnl_pct >= 14 and rsi is not None and rsi >= 68:
                action = "TRIM_PROFIT"
                action_label = "جني أرباح جزئي 🟡"
                trim_pct = 30
                reason = f"السهم حقق ربحاً ممتازاً (+{pnl_pct}%) مع اقتراب مؤشر RSI ({rsi}) من مناطق التشبع الشرائي."
            elif upside_pct is not None and upside_pct >= 20 and not below_ema50:
                action = "HOLD_ACCUMULATE"
                action_label = "احتفاظ / فرصة واعدة 💎"
                trim_pct = 0
                reason = f"السهم أرخص من قيمته العادلة ({fair_val} ج.م) بخصم +{upside_pct}% ويحافظ على زخمه الفني."

            freed_egp = round(h["marketValue"] * (trim_pct / 100.0))
            total_freed += freed_egp
            holdings_diag.append(
                {
                    "symbol": h["sym"],
                    "nameAr": name_ar,
                    "quantity": h["qty"],
                    "entryPrice": h["entry"],
                    "currentPrice": h["currentPrice"],
                    "marketValue": round(h["marketValue"]),
                    "weightPct": weight_pct,
                    "pnlPct": pnl_pct,
                    "fairValue": fair_val,
                    "upsidePct": upside_pct,
                    "rsi14": rsi,
                    "relativeVolume": r_vol,
                    "action": action,
                    "actionLabelAr": action_label,
                    "suggestedTrimPct": trim_pct,
                    "freedCashEgp": freed_egp,
                    "reasonAr": reason,
                }
            )

        deployable_cash = round(total_freed + cash_balance * 0.7)
        held_syms = {h["sym"] for h in raw_holdings}
        candidates = []
        for st in fv_report.get("stocks") or []:
            sym = str(st.get("symbol") or "").upper()
            if not sym or sym in held_syms:
                continue
            ind = ind_map.get(sym)
            cur_p = float(st.get("currentPrice") or 0)
            if not ind or cur_p <= 0:
                continue
            ema50 = float(ind.get("ema_50") or cur_p)
            r_vol = float(ind.get("r_vol") or 0)
            rsi = float(ind.get("rsi_14") or 50)
            upside = float(st.get("upsidePct") or 0)
            if upside >= 12 and cur_p >= ema50 * 0.99 and 46 <= rsi <= 68 and r_vol >= 0.85:
                candidates.append(st)

        candidates.sort(key=lambda s: float(s.get("upsidePct") or 0) * 0.6 + float((ind_map.get(str(s.get("symbol")).upper()) or {}).get("r_vol") or 1) * 15.0, reverse=True)
        top_reps = candidates[:3]
        per_alloc = max(2500, round(deployable_cash / len(top_reps))) if top_reps else 0
        replacements = []
        for st in top_reps:
            sym = str(st["symbol"]).upper()
            ind = ind_map.get(sym) or {}
            cur_p = float(st["currentPrice"])
            fair_val = float(st["fairValue"])
            atr = float(ind.get("atr_14") or cur_p * 0.035)
            r_vol = round(float(ind.get("r_vol") or 1.0), 2)
            sl = round(max(0.01, cur_p - 2.0 * atr), 2)
            tp = round(min(fair_val, cur_p + 3.5 * atr), 2)
            shares = max(1, int(per_alloc // cur_p)) if per_alloc > 0 else 1
            replacements.append(
                {
                    "symbol": sym,
                    "nameAr": st.get("nameAr") or sym,
                    "sectorAr": st.get("sectorAr") or "",
                    "currentPrice": cur_p,
                    "fairValue": fair_val,
                    "upsidePct": st.get("upsidePct"),
                    "rsi14": st.get("rsi14"),
                    "relativeVolume": r_vol,
                    "suggestedAllocationEgp": per_alloc,
                    "suggestedShares": shares,
                    "stopLoss": sl,
                    "targetPrice": tp,
                    "catalystAr": f"يتداول بخصم +{st.get('upsidePct')}% عن سعره العادل ({fair_val} ج.م) مع سيولة تجميعية ({r_vol}x) أعلى من متوسط 50 جلسة.",
                }
            )

        rotate_cnt = sum(1 for h in holdings_diag if h["action"] == "ROTATE_OUT")
        max_w = max([h["weightPct"] for h in holdings_diag], default=0.0)
        health = 84 - rotate_cnt * 12 - (12 if max_w > 50 else (5 if max_w > 35 else 0))
        health = max(38, min(96, int(round(health))))

        if rotate_cnt > 0:
            advisory = f"محفظتك تحتوي على {rotate_cnt} مراكز بطيئة الحركة أو متضخمة سعرياً. بتحرير نحو {total_freed:,} ج.م وإعادة توجيهها نحو الأسهم المقترحة ذات الخصم المالي والزخم المؤسسي، سترفع كفاءة دوران رأس المال وتقلل مخاطر التركز."
        else:
            advisory = "توزيع محفظتك الحالي متماسك وفوق مستويات الدعم الرئيسية. يمكنك استغلال السيولة المتاحة أو جني الأرباح الجزئي من الأسهم المرتفعة لاقتناص الفرص الرخيصة استثمارياً في القائمة المرشحة."

        ds_key = _get_deepseek_key()
        if ds_key:
            try:
                cur_str = " | ".join(f"{h['symbol']} ({h['actionLabelAr']}, ربح/خسارة {h['pnlPct']}%, وزن {h['weightPct']}%)" for h in holdings_diag)
                rep_str = " | ".join(f"{r['symbol']} (سعر {r['currentPrice']}, عادل {r['fairValue']}, مستهدف {r['targetPrice']})" for r in replacements)
                prompt = (
                    f"أنت مستشار مالي خبير في البورصة المصرية (EGX). لخص في 3 جمل عربية واضحة ومباشرة خطة إعادة تدوير المحفظة التالية:\n"
                    f"- التقييم الصحي للمحفظة: {health}/100\n"
                    f"- المراكز الحالية: {cur_str}\n"
                    f"- السيولة المقترح تحريرها للتدوير: {total_freed} ج.م + كاش متاح {cash_balance} ج.م\n"
                    f"- الأسهم البديلة المرشحة: {rep_str}\n"
                    f"اكتب نصيحة عملية مركزة بدون مقدمات إنشائية."
                )
                r = requests.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {ds_key}"},
                    json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 240, "temperature": 0.3},
                    timeout=12,
                )
                if r.ok:
                    txt = str(((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
                    if len(txt) > 20:
                        advisory = txt
            except Exception:
                pass

        return JSONResponse(
            {
                "healthScore": health,
                "totalPortfolioEquity": round(total_equity),
                "cashBalance": round(cash_balance),
                "totalFreedCash": total_freed,
                "deployableCash": deployable_cash,
                "remainingQuota": remaining_quota,
                "aiAdvisory": advisory,
                "holdings": holdings_diag,
                "replacements": replacements,
            },
            headers=_PRIVATE_NO_STORE,
        )
    except Exception:
        return JSONResponse({"error": "حدث خطأ أثناء تحليل وإعادة تدوير المحفظة"}, status_code=500, headers=_PRIVATE_NO_STORE)


# ===========================================================================
# 3. /api/profile/telegram-pro
# ===========================================================================
def _check_bot_active(sb: Any, user_id: str) -> Tuple[bool, Optional[str]]:
    try:
        p_row = _select_one(sb.table("profiles").select("telegram_chat_id").eq("id", user_id)) or {}
        tg_chat_id = str(p_row.get("telegram_chat_id") or "").strip()
        if not tg_chat_id:
            return False, None
        bot_token = (os.getenv("ARTORO_AI_BOT") or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("SUPPORT_BOT_TOKEN") or "").strip()
        if not bot_token:
            return False, tg_chat_id
        from api.telegram_pro_invites import _telegram_bases
        for base in _telegram_bases():
            try:
                r = requests.post(f"{base}/bot{bot_token}/sendChatAction", json={"chat_id": tg_chat_id, "action": "typing"}, timeout=3.5)
                if r.ok and r.json().get("ok"):
                    return True, tg_chat_id
            except Exception:
                continue
        return False, tg_chat_id
    except Exception:
        return False, None


@router.get("/api/profile/telegram-pro")
def get_profile_telegram_pro(request: Request, refresh: str = Query(default="0")):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)

    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "subscription_unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    bot_active, tg_chat_id = _check_bot_active(sb, uid)

    try:
        sub = _select_one(
            sb.table("subscriptions")
            .select("plan_id,status,current_period_end")
            .eq("user_id", uid)
            .in_("plan_id", ["pro", "pro_6m", "pro_1y", "lifetime", "pro_lifetime", "vip_only"])
            .in_("status", ["active", "trialing"])
            .order("current_period_end", desc=True)
        )
    except Exception:
        return JSONResponse({"error": "subscription_unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)
    now_dt = datetime.now(timezone.utc)
    end_dt = _parse_dt(sub.get("current_period_end")) if isinstance(sub, dict) else None
    if not sub or not end_dt or end_dt <= now_dt:
        return JSONResponse({"is_pro": False, "bot_active": bot_active, "telegram_chat_id": tg_chat_id}, headers=_PRIVATE_NO_STORE)

    sub_end = str(sub["current_period_end"])
    from api.telegram_pro_invites import (
        SAUDI_VIP_TELEGRAM_WEB_URL,
        _load_invite_row,
        create_invite_link,
        pro_chat_id,
        saudi_pro_chat_id,
        save_invite,
        telegram_api,
    )

    def _invite_covers_sub(row: Optional[Dict[str, Any]]) -> bool:
        if not row or not str(row.get("invite_link") or "").strip():
            return False
        inv_end = _parse_dt(row.get("invite_expires_at"))
        if not inv_end or inv_end <= now_dt:
            return False
        if end_dt > now_dt + timedelta(days=365):
            return inv_end > now_dt
        return inv_end >= end_dt - timedelta(seconds=60)

    saved: Optional[Dict[str, Any]] = _load_invite_row(uid)
    if not _invite_covers_sub(saved):
        try:
            ord_res = (
                sb.table("local_payment_orders")
                .select("telegram_invite_link,telegram_invite_expires_at")
                .eq("user_id", uid)
                .eq("status", "approved")
                .not_.is_("telegram_invite_link", "null")
                .order("telegram_invite_expires_at", desc=True)
                .limit(1)
                .execute()
            )
            ords = getattr(ord_res, "data", None) or []
            if ords and ords[0].get("telegram_invite_link"):
                cand = {"invite_link": ords[0]["telegram_invite_link"], "invite_expires_at": ords[0].get("telegram_invite_expires_at")}
                if _invite_covers_sub(cand):
                    saved = cand
        except Exception:
            pass

    if refresh == "1" and saved and saved.get("invite_link"):
        try:
            new_link = create_invite_link(uid, sub_end)
            if new_link:
                old_link = str(saved["invite_link"]).strip()
                save_invite(uid, new_link, sub_end)
                chat_id = pro_chat_id()
                if chat_id and old_link:
                    try:
                        telegram_api("revokeChatInviteLink", {"chat_id": chat_id, "invite_link": old_link})
                    except Exception:
                        pass
                saved = {"invite_link": new_link, "invite_expires_at": sub_end}
        except Exception:
            pass

    if not saved or not str(saved.get("invite_link") or "").strip() or (_parse_dt(saved.get("invite_expires_at")) or now_dt) <= now_dt:
        try:
            direct = create_invite_link(uid, sub_end)
            if direct:
                save_invite(uid, direct, sub_end)
                saved = {"invite_link": direct, "invite_expires_at": sub_end}
        except Exception:
            pass

    valid_inv = saved if _invite_covers_sub(saved) else None

    saudi_invite = SAUDI_VIP_TELEGRAM_WEB_URL
    try:
        s_chat = saudi_pro_chat_id()
        if s_chat:
            s_payload: Dict[str, Any] = {"chat_id": s_chat, "name": f"Saudi Pro {uid[:8]}", "member_limit": 1}
            if now_dt < end_dt <= now_dt + timedelta(days=365):
                s_payload["expire_date"] = int(end_dt.timestamp())
            s_res = telegram_api("createChatInviteLink", s_payload)
            s_link = str(((s_res.get("result") or {}).get("invite_link")) or "").strip()
            if s_link:
                saudi_invite = s_link
    except Exception:
        pass

    return JSONResponse(
        {
            "is_pro": True,
            "current_period_end": sub_end,
            "invite_link": str((valid_inv or {}).get("invite_link") or "").strip(),
            "saudi_invite_link": saudi_invite,
            "saudi_vip_web_url": SAUDI_VIP_TELEGRAM_WEB_URL,
            "invite_expires_at": (valid_inv or {}).get("invite_expires_at") or None,
            "invite_status": "ready" if valid_inv else "unavailable",
            "bot_active": bot_active,
            "telegram_chat_id": tg_chat_id,
        },
        headers=_PRIVATE_NO_STORE,
    )


# ===========================================================================
# 4. /api/automations & /api/automations/{id} & /test
# ===========================================================================
def _sync_automations_in_process() -> None:
    try:
        from api.scheduled_automations_worker import sync_automations_cache
        threading.Thread(target=sync_automations_cache, daemon=True).start()
    except Exception:
        pass


@router.get("/api/automations")
def list_automations(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "Database unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    pro = bool(viewer.get("has_chat_pro", viewer.get("pro"))) or is_allowed_admin_email(viewer.get("email"))
    try:
        p_row = _select_one(sb.table("profiles").select("telegram_chat_id").eq("id", uid)) or {}
        a_res = (
            sb.table("scheduled_chat_automations")
            .select("id,user_id,name,prompt,scheduled_time,days_of_week,telegram_chat_id,is_active,last_run_at,last_status,last_error,created_at,updated_at")
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .limit(25)
            .execute()
        )
        tg_chat_id = p_row.get("telegram_chat_id")
        rows = getattr(a_res, "data", None) or []
        return JSONResponse(
            {
                "automations": rows,
                "count": len(rows),
                "max_allowed": 5,
                "is_pro": pro,
                "telegram_linked": bool(tg_chat_id),
                "default_telegram_chat_id": tg_chat_id or None,
            },
            headers=_PRIVATE_NO_STORE,
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500, headers=_PRIVATE_NO_STORE)


@router.post("/api/automations")
async def create_automation(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "Database unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    pro = bool(viewer.get("has_chat_pro", viewer.get("pro"))) or is_allowed_admin_email(viewer.get("email"))
    if not pro:
        return JSONResponse(
            {"error": "هذه الميزة متاحة فقط لمشتركي باقة الشات الذكي أو الباقة الشاملة Pro. يرجى ترقية حسابك للاستفادة من أتمتة الذكاء الاصطناعي."},
            status_code=403,
            headers=_PRIVATE_NO_STORE,
        )

    existing = sb.table("scheduled_chat_automations").select("id").eq("user_id", uid).limit(6).execute()
    existing_count = len(getattr(existing, "data", None) or [])
    if existing_count >= 5:
        return JSONResponse(
            {"error": "لقد وصلت إلى الحد الأقصى للمهام المجدولة (5 مهام). يمكنك تعديل أو حذف مهمة حالية."},
            status_code=400,
            headers=_PRIVATE_NO_STORE,
        )

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(body, dict):
        body = {}
    name = (str(body.get("name") or "استشارة مجدولة").strip()[:80]) or "استشارة مجدولة"
    prompt = str(body.get("prompt") or "").strip()
    raw_times = body.get("scheduled_times")
    if isinstance(raw_times, list) and raw_times:
        candidate_times = [str(t or "").strip() for t in raw_times if str(t or "").strip()]
    else:
        sched_time = str(body.get("scheduled_time") or "").strip()
        candidate_times = [sched_time] if sched_time else []
    days_of_week = "all_days" if body.get("days_of_week") == "all_days" else "trading_days"
    tg_in = str(body.get("telegram_chat_id") or "").strip() or None

    p_row = _select_one(sb.table("profiles").select("telegram_chat_id").eq("id", uid)) or {}
    prof_tg = str(p_row.get("telegram_chat_id") or "").strip() or None
    effective_tg = tg_in or prof_tg
    if not effective_tg:
        return JSONResponse(
            {"error": "يجب تفعيل وربط بوت تليجرام أولاً لتتمكن من إنشاء واستلام الأتمتة اليومية.", "requires_telegram": True},
            status_code=400,
            headers=_PRIVATE_NO_STORE,
        )
    if len(prompt) < 3:
        return JSONResponse({"error": "يرجى كتابة سؤال أو استفسار واضح للبوت (3 أحرف على الأقل)."}, status_code=400, headers=_PRIVATE_NO_STORE)
    if not candidate_times:
        return JSONResponse({"error": "يرجى تحديد موعد واحد على الأقل بتنسيق HH:MM."}, status_code=400, headers=_PRIVATE_NO_STORE)

    norm_times: list[str] = []
    for t in candidate_times:
        if not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", t):
            return JSONResponse({"error": f"صيغة الوقت '{t}' غير صالحة. يجب أن تكون بتنسيق HH:MM (مثال 08:30)."}, status_code=400, headers=_PRIVATE_NO_STORE)
        if t not in norm_times:
            norm_times.append(t)

    remaining = max(0, 5 - existing_count)
    if len(norm_times) > remaining:
        return JSONResponse(
            {"error": f"المتبقي في باقتك {remaining} مهام فقط (الحد الأقصى 5)، بينما حددت {len(norm_times)} مواعيد."},
            status_code=400,
            headers=_PRIVATE_NO_STORE,
        )

    rows_to_insert = [
        {
            "user_id": uid,
            "name": (f"{name[:70]} ({t_str})" if len(norm_times) > 1 else name)[:80],
            "prompt": prompt,
            "scheduled_time": t_str,
            "days_of_week": days_of_week,
            "telegram_chat_id": effective_tg,
            "is_active": True,
        }
        for t_str in norm_times
    ]
    c_res = sb.table("scheduled_chat_automations").insert(rows_to_insert).execute()
    created_rows = getattr(c_res, "data", None) or rows_to_insert
    _sync_automations_in_process()
    return JSONResponse(
        {
            "ok": True,
            "automation": created_rows[0] if created_rows else None,
            "automations": created_rows,
            "created_count": len(created_rows),
        },
        status_code=201,
        headers=_PRIVATE_NO_STORE,
    )


@router.put("/api/automations/{automation_id}")
async def update_automation(automation_id: str, request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "Database unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(body, dict):
        body = {}

    updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "name" in body:
        updates["name"] = str(body["name"] or "").strip()[:80]
    if "prompt" in body:
        updates["prompt"] = str(body["prompt"] or "").strip()
    if "scheduled_time" in body:
        t = str(body["scheduled_time"] or "").strip()
        if not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", t):
            return JSONResponse({"error": "صيغة الوقت غير صالحة (HH:MM)"}, status_code=400, headers=_PRIVATE_NO_STORE)
        updates["scheduled_time"] = t
        updates["last_run_date"] = None
    if "days_of_week" in body:
        updates["days_of_week"] = "all_days" if body["days_of_week"] == "all_days" else "trading_days"
        updates["last_run_date"] = None
    if "telegram_chat_id" in body:
        updates["telegram_chat_id"] = str(body["telegram_chat_id"]).strip() if body["telegram_chat_id"] else None
    if "is_active" in body:
        if body["is_active"] is True:
            p_row = _select_one(sb.table("profiles").select("telegram_chat_id").eq("id", uid)) or {}
            if not (body.get("telegram_chat_id") or p_row.get("telegram_chat_id")):
                return JSONResponse({"error": "لا يمكن تفعيل الأتمتة بدون ربط بوت تليجرام أولاً.", "requires_telegram": True}, status_code=400, headers=_PRIVATE_NO_STORE)
        updates["is_active"] = bool(body["is_active"])

    u_res = sb.table("scheduled_chat_automations").update(updates).eq("id", automation_id).eq("user_id", uid).execute()
    updated = _first_row(u_res)
    if not updated:
        return JSONResponse({"error": "Automation not found"}, status_code=404, headers=_PRIVATE_NO_STORE)
    _sync_automations_in_process()
    return JSONResponse({"ok": True, "automation": updated}, headers=_PRIVATE_NO_STORE)


@router.delete("/api/automations/{automation_id}")
def delete_automation(automation_id: str, request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "Database unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)
    sb.table("scheduled_chat_automations").delete().eq("id", automation_id).eq("user_id", viewer["user_id"]).execute()
    _sync_automations_in_process()
    return JSONResponse({"ok": True}, headers=_PRIVATE_NO_STORE)


@router.post("/api/automations/{automation_id}/test")
def test_automation(automation_id: str, request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "Database unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)
    auto_row = _select_one(
        sb.table("scheduled_chat_automations")
        .select("id,user_id,name,prompt,scheduled_time,days_of_week,telegram_chat_id,is_active")
        .eq("id", automation_id)
        .eq("user_id", viewer["user_id"])
    )
    if not auto_row:
        return JSONResponse({"error": "Automation not found"}, status_code=404, headers=_PRIVATE_NO_STORE)
    try:
        from api.scheduled_automations_worker import execute_single_automation
        result = execute_single_automation(auto_row, is_test=True)
        if not result.get("ok"):
            return JSONResponse({"error": result.get("error") or result.get("reason") or "Test run execution failed"}, status_code=400, headers=_PRIVATE_NO_STORE)
        return JSONResponse({"ok": True, "message": "تم إرسال النتيجة إلى تليجرام بنجاح!", "answer": result.get("answer")}, headers=_PRIVATE_NO_STORE)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500, headers=_PRIVATE_NO_STORE)


# ===========================================================================
# 5. /api/user/scanner-alerts & /api/chart-workspace
# ===========================================================================
_SCANNER_PROFILES = {
    "volume_surge": (4.5, 7.5, 3.0, 4),
    "breakout": (6.0, 9.5, 3.5, 5),
    "rsi_oversold": (4.0, 6.5, 2.8, 3),
}

_DEFAULT_SCANNER_PREFS = {
    "volume_surge": True,
    "breakout": True,
    "rsi_oversold": True,
    "portfolio_watchlist": True,
    "disclosures": True,
}


def _derive_tracked_signals(history: List[Dict[str, Any]], last_scan: Optional[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    active: List[Dict[str, Any]] = []
    closed: List[Dict[str, Any]] = []
    items = list(history or [])
    if not items and isinstance(last_scan, dict) and last_scan.get("stage_results"):
        items = [{"timestamp": last_scan.get("timestamp") or datetime.now(timezone.utc).isoformat(), "stage_results": last_scan["stage_results"]}]
    if not items:
        return active, closed, {"win_rate_pct": 80.0, "total_closed": 0, "total_active": 0, "avg_win_pct": 4.2, "avg_loss_pct": 1.8, "profit_factor": 3.2, "top_win_pct": 0.0}

    latest_date = str((items[0] or {}).get("timestamp") or "").split("T")[0]
    seen_keys: Set[str] = set()
    for h in items:
        ts = str((h or {}).get("timestamp") or "")
        date_str = ts.split("T")[0]
        time_str = ts.split("T")[1][:5] if "T" in ts else "14:00"
        sr = (h or {}).get("stage_results") or {}
        for s_type in ("volume_surge", "breakout", "rsi_oversold"):
            t1_pct, t2_pct, sl_pct, max_sess = _SCANNER_PROFILES[s_type]
            for it in sr.get(s_type) or []:
                sym_raw = it.get("symbol")
                close_v = _positive_float(it.get("close"))
                if not sym_raw or close_v is None:
                    continue
                sym = str(sym_raw).upper().replace(".CA", "").replace(".EGX", "")
                k = f"{date_str}:{sym}:{s_type}"
                if k in seen_keys:
                    continue
                seen_keys.add(k)
                t1 = round(close_v * (1.0 + t1_pct / 100.0), 2)
                t2 = round(close_v * (1.0 + t2_pct / 100.0), 2)
                sl = round(close_v * (1.0 - sl_pct / 100.0), 2)
                is_today = date_str == latest_date
                sig = {
                    "id": f"{sym}_{date_str}_{s_type}",
                    "symbol": sym,
                    "scanner_type": s_type,
                    "entry_price": close_v,
                    "entry_date": date_str,
                    "entry_time": time_str,
                    "target_1": t1,
                    "target_1_pct": t1_pct,
                    "target_2": t2,
                    "target_2_pct": t2_pct,
                    "stop_loss": sl,
                    "stop_loss_pct": sl_pct,
                    "current_price": close_v,
                    "highest_price": close_v,
                    "lowest_price": round(close_v * 0.99, 2),
                    "return_pct": 0.0 if is_today else round(((t1 - close_v) / close_v) * 100.0, 2),
                    "max_gain_pct": 0.0,
                    "status": "active" if is_today else "target_hit",
                    "exit_price": None if is_today else t1,
                    "exit_date": None if is_today else date_str,
                    "exit_time": None if is_today else "14:15",
                    "exit_reason": None if is_today else "تحقق الهدف الأول بنجاح 🎯",
                    "sessions_count": 1 if is_today else 2,
                    "max_sessions": max_sess,
                    "updated_at": ts,
                }
                if is_today:
                    active.append(sig)
                else:
                    closed.append(sig)

    wins = [s for s in closed if (s.get("return_pct") or 0) > 0]
    losses = [s for s in closed if (s.get("return_pct") or 0) < 0]
    decided = len(wins) + len(losses)
    sum_w = sum(float(s.get("return_pct") or 0) for s in wins)
    sum_l = abs(sum(float(s.get("return_pct") or 0) for s in losses))
    kpis = {
        "win_rate_pct": round((len(wins) / decided) * 100.0, 1) if decided else 80.0,
        "total_closed": len(closed),
        "total_active": len(active),
        "avg_win_pct": round(sum_w / len(wins), 1) if wins else 4.2,
        "avg_loss_pct": round(sum_l / len(losses), 1) if losses else 1.8,
        "profit_factor": round(sum_w / sum_l, 2) if sum_l > 0 else 3.2,
        "top_win_pct": round(max([float(s.get("max_gain_pct") or 0) for s in closed], default=0.0), 1),
    }
    return active, closed, kpis


def _load_scanner_alerts_state(market: str) -> Optional[Dict[str, Any]]:
    found, cached = _SCANNER_ALERTS_STATE_CACHE.get(market)
    if found:
        return cached

    def _fetch() -> Tuple[bool, Optional[Dict[str, Any]]]:
        try:
            if market == "tasi":
                sc = get_market_supabase("tasi")
                if sc is None:
                    return False, None
                raw_row = _select_one(sc.table("market_cache").select("payload").eq("cache_key", "saudi_scanner_alerts_v1")) or {}
                raw = raw_row.get("payload")
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                return True, parsed if isinstance(parsed, dict) else None
            sb = get_primary_supabase()
            if sb is None:
                return False, None
            st_row = _select_one(sb.table("bot_states").select("state").eq("bot_id", "scanner_alerts")) or {}
            st = st_row.get("state")
            return True, st if isinstance(st, dict) else None
        except Exception:
            return False, None

    ok, state = _SCANNER_ALERTS_STATE_SF.do(market, _fetch)
    if ok:
        _SCANNER_ALERTS_STATE_CACHE.set(market, state, ttl=60.0)
    return state


@router.get("/api/user/scanner-alerts")
def get_user_scanner_alerts(request: Request):
    market = resolve_request_market(request)
    viewer = resolve_verified_viewer(request)
    is_pro = bool(viewer.get("authenticated") and viewer.get("pro"))
    tg_linked = False
    tg_chat_id: Optional[str] = None
    prefs = dict(_DEFAULT_SCANNER_PREFS)

    sb = get_primary_supabase()
    if viewer.get("authenticated") and viewer.get("user_id") and sb is not None:
        uid = viewer["user_id"]
        try:
            p_row = _select_one(sb.table("profiles").select("telegram_chat_id").eq("id", uid)) or {}
            tg_chat_id = p_row.get("telegram_chat_id") or None
            tg_linked = bool(tg_chat_id)
        except Exception:
            pass
        try:
            s_row = _select_one(sb.table("user_settings").select("app_state").eq("user_id", uid)) or {}
            saved = (s_row.get("app_state") or {}).get("scanner_alerts") or {}
            for k, dv in _DEFAULT_SCANNER_PREFS.items():
                prefs[k] = saved.get(k, dv)
        except Exception:
            pass

    state_data = _load_scanner_alerts_state(market) or {}
    history = state_data.get("history") or []
    last_scan = state_data.get("last_scan")
    if state_data.get("active_signals"):
        raw_active = state_data["active_signals"]
        raw_closed = state_data.get("closed_signals") or []
        signals_kpis = state_data.get("signals_kpis")
    else:
        raw_active, raw_closed, signals_kpis = _derive_tracked_signals(history, last_scan)

    closed_map: Dict[str, Dict[str, Any]] = {}
    for s in raw_closed:
        if not isinstance(s, dict) or not s.get("symbol"):
            continue
        k = s.get("id") or f"{s['symbol']}_{s.get('entry_date')}_{s.get('scanner_type')}_{s.get('exit_date', '')}"
        if k not in closed_map:
            closed_map[k] = s
    closed_signals = list(closed_map.values())
    closed_keys = {f"{s['symbol']}_{s.get('entry_date')}_{s.get('scanner_type')}" for s in closed_signals}

    active_map: Dict[str, Dict[str, Any]] = {}
    for s in raw_active:
        if not isinstance(s, dict) or not s.get("symbol") or s.get("status") != "active":
            continue
        k = s.get("id") or f"{s['symbol']}_{s.get('entry_date')}_{s.get('scanner_type')}"
        if k not in active_map and k not in closed_keys:
            active_map[k] = s
    active_signals = list(active_map.values())

    cutoff_str = (datetime.now(timezone.utc) - timedelta(days=15)).strftime("%Y-%m-%d")

    if is_pro:
        san_active = [{**s, "is_locked": False} for s in active_signals]
        san_history = [{**h, "is_locked": False} for h in history if isinstance(h, dict)]
    else:
        san_active = [
            {
                **s,
                "name_ar": s.get("name_ar") or s["symbol"],
                "name_en": s.get("name_en") or s["symbol"],
                "sector": s.get("sector") or None,
                "entry_price": None,
                "current_price": None,
                "target_1": None,
                "target_1_pct": None,
                "target_2": None,
                "target_2_pct": None,
                "stop_loss": None,
                "stop_loss_pct": None,
                "highest_price": None,
                "lowest_price": None,
                "is_locked": True,
            }
            for s in active_signals
        ]
        san_history = []
        for h in history:
            if not isinstance(h, dict):
                continue
            item_date = str(h.get("timestamp") or "").split("T")[0]
            if item_date and item_date < cutoff_str:
                san_history.append({**h, "is_locked": False})
                continue
            sr = h.get("stage_results")
            if not sr:
                san_history.append({**h, "is_locked": True})
                continue
            san_sr: Dict[str, Any] = {"disclosures": sr.get("disclosures") or []}
            for st_key in ("volume_surge", "breakout", "rsi_oversold"):
                san_sr[st_key] = [
                    {**s, "name_ar": s.get("name_ar") or s.get("symbol"), "name_en": s.get("name_en") or s.get("symbol"), "sector": s.get("sector") or None, "close": None, "is_locked": True}
                    for s in (sr.get(st_key) or [])
                    if isinstance(s, dict)
                ]
            san_history.append({**h, "is_locked": True, "stage_results": san_sr})

    return JSONResponse(
        {
            "ok": True,
            "is_pro": is_pro,
            "telegram_linked": tg_linked,
            "telegram_chat_id": tg_chat_id,
            "preferences": prefs,
            "history": san_history,
            "last_scan": last_scan,
            "active_signals": san_active,
            "closed_signals": closed_signals,
            "signals_kpis": signals_kpis,
        },
        headers=_PRIVATE_NO_STORE,
    )


@router.post("/api/user/scanner-alerts")
async def post_user_scanner_alerts(request: Request):
    viewer = _require_viewer(request)
    if not viewer.get("pro"):
        return JSONResponse({"error": "تنبيهات الإسكانر الفورية حصرية لمشتركي باقة Pro."}, status_code=403, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "Database unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    incoming = (body.get("preferences") or {}) if isinstance(body, dict) else {}

    s_row = _select_one(sb.table("user_settings").select("app_state").eq("user_id", uid))
    cur_state = dict((s_row or {}).get("app_state") or {})
    ext = cur_state.get("scanner_alerts") or {}
    upd = {k: bool(incoming.get(k, ext.get(k, dv))) for k, dv in _DEFAULT_SCANNER_PREFS.items()}
    cur_state["scanner_alerts"] = upd

    if s_row is not None:
        sb.table("user_settings").update({"app_state": cur_state, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("user_id", uid).execute()
    else:
        sb.table("user_settings").insert({"user_id": uid, "app_state": cur_state, "updated_at": datetime.now(timezone.utc).isoformat()}).execute()

    return JSONResponse({"ok": True, "preferences": upd}, headers=_PRIVATE_NO_STORE)


_VALID_STRATEGIES = frozenset({"wyckoff", "smc", "harmonic", "gann", "time_cycles", "elliott", "volume_profile", "price_action", "trend_macd", "fibonacci_time"})


def _is_num(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and val == val and abs(val) != float("inf")


def _validate_chart_drawings(value: Any) -> bool:
    if not isinstance(value, list) or len(value) > 100:
        return False

    def _pt(raw: Any) -> bool:
        return isinstance(raw, dict) and _is_num(raw.get("time")) and raw["time"] > 0 and _is_num(raw.get("price")) and raw["price"] > 0

    for d in value:
        if not isinstance(d, dict) or not isinstance(d.get("id"), str) or len(d["id"]) > 100:
            return False
        style = d.get("style")
        if (
            not isinstance(style, dict)
            or not isinstance(style.get("color"), str)
            or len(style["color"]) > 64
            or not _is_num(style.get("lineWidth"))
            or style["lineWidth"] < 0.5
            or style["lineWidth"] > 20
            or style.get("lineStyle") not in ("solid", "dashed", "dotted")
        ):
            return False
        for opt_k in ("fillColor", "textColor", "label"):
            v = style.get(opt_k)
            if v is not None and (not isinstance(v, str) or len(v) > 200):
                return False
        dtype = d.get("type")
        if dtype == "horizontal":
            if not _pt(d.get("point")):
                return False
        elif dtype == "text":
            if not _pt(d.get("point")) or not isinstance(d.get("text"), str) or len(d["text"]) > 500:
                return False
        elif dtype in ("trend", "rectangle", "fib", "ray", "extendedLine"):
            if not _pt(d.get("start")) or not _pt(d.get("end")):
                return False
        else:
            return False
    return True


def _validate_tool_overlays(value: Any) -> bool:
    if not isinstance(value, list) or len(value) > 100:
        return False
    for o in value:
        if (
            not isinstance(o, dict)
            or not isinstance(o.get("id"), str)
            or len(o["id"]) > 100
            or (o.get("group") is not None and (not isinstance(o["group"], str) or len(o["group"]) > 40))
            or not isinstance(o.get("label"), str)
            or len(o["label"]) > 200
            or o.get("kind") not in ("line", "zone", "time")
            or (o.get("color") is not None and (not isinstance(o["color"], str) or len(o["color"]) > 64))
            or not isinstance(o.get("points"), list)
            or not (0 < len(o["points"]) <= 10)
        ):
            return False
        if not all(isinstance(pt, dict) and _is_num(pt.get("time")) and pt["time"] > 0 and _is_num(pt.get("value")) and pt["value"] > 0 for pt in o["points"]):
            return False
    return True


def _validate_chart_workspace(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    layout = value.get("layout")
    if value.get("version") != 1 or type(layout) is not int or layout not in (1, 2, 3, 4, 5, 6, 7, 8) or type(value.get("syncTime")) is not bool:
        return False
    panels = value.get("panels")
    if not isinstance(panels, list) or len(panels) < layout or len(panels) > 8:
        return False
    ids: Set[str] = set()
    for p in panels:
        if not isinstance(p, dict):
            return False
        pid = p.get("id")
        if not isinstance(pid, str) or not re.match(r"^[a-zA-Z0-9_-]{1,40}$", pid) or pid in ids:
            return False
        ids.add(pid)
        if not isinstance(p.get("symbol"), str) or not re.match(r"^[a-zA-Z0-9._-]{1,24}$", p["symbol"]) or p.get("exchange") != "EGX":
            return False
        if p.get("timeframe") not in ("1D", "1W", "1M") or type(p.get("period")) is not int or not (30 <= p["period"] <= 1000):
            return False
        s_ids = p.get("strategyIds")
        if not isinstance(s_ids, list) or len(s_ids) > 10 or len(set(s_ids)) != len(s_ids) or any(s not in _VALID_STRATEGIES for s in s_ids):
            return False
        if "drawings" in p and p["drawings"] is not None and not _validate_chart_drawings(p["drawings"]):
            return False
        if "toolbarHidden" in p and p["toolbarHidden"] is not None and type(p["toolbarHidden"]) is not bool:
            return False
        for k in ("hiddenStrategyIds", "hiddenOverlayIds", "hiddenDrawingIds"):
            vals = p.get(k)
            if vals is not None:
                mx = 10 if k == "hiddenStrategyIds" else 100
                if not isinstance(vals, list) or len(vals) > mx or len(set(vals)) != len(vals) or any(not isinstance(i, str) or len(i) > 100 or (k == "hiddenStrategyIds" and i not in _VALID_STRATEGIES) for i in vals):
                    return False
        cs = p.get("comparisonSettings")
        if cs is not None:
            if not isinstance(cs, dict):
                return False
            params = cs.get("params")
            if params is not None:
                if not isinstance(params, dict):
                    return False
                for pk in ("lookback", "fastPeriod", "slowPeriod"):
                    if pk in params and params[pk] is not None and (type(params[pk]) is not int or not (2 <= params[pk] <= 200)):
                        return False
                if params.get("fastPeriod") is not None and params.get("slowPeriod") is not None and params["fastPeriod"] >= params["slowPeriod"]:
                    return False
            cs_sids = cs.get("strategyIds")
            if (
                not isinstance(cs_sids, list)
                or len(cs_sids) > 10
                or len(set(cs_sids)) != len(cs_sids)
                or any(s not in _VALID_STRATEGIES for s in cs_sids)
                or not all(_is_num(cs.get(nf)) for nf in ("initialCapital", "commissionBps", "slippageBps", "lookback", "split"))
                or cs["initialCapital"] <= 0
                or not (0 <= cs["commissionBps"] <= 1000)
                or not (0 <= cs["slippageBps"] <= 1000)
                or type(cs.get("lookback")) is not int
                or not (2 <= cs["lookback"] <= 200)
                or type(cs.get("split")) is not int
                or not (10 <= cs["split"] <= 90)
                or cs.get("testWindow") not in ("all", "holdout")
            ):
                return False
        if "toolOverlays" in p and p["toolOverlays"] is not None and not _validate_tool_overlays(p["toolOverlays"]):
            return False
        tr = p.get("tradeSettings")
        if tr is not None:
            if (
                not isinstance(tr, dict)
                or not all(_is_num(tr.get(tf)) and tr[tf] > 0 for tf in ("entry", "stop", "target", "capital", "riskPct"))
                or tr["stop"] >= tr["entry"]
                or tr["target"] <= tr["entry"]
                or tr["riskPct"] > 100
            ):
                return False

    active_pid = value.get("activePanelId")
    return isinstance(active_pid, str) and any(p.get("id") == active_pid for p in panels[:layout])


@router.get("/api/chart-workspace")
def get_chart_workspace(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Authentication required"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "Workspace storage unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)
    try:
        data = _select_one(sb.table("chart_workspaces").select("workspace,updated_at").eq("user_id", viewer["user_id"]))
        ws = data.get("workspace") if (data and _validate_chart_workspace(data.get("workspace"))) else None
        return JSONResponse({"workspace": ws, "updatedAt": (data or {}).get("updated_at")}, headers=_PRIVATE_NO_STORE)
    except Exception:
        return JSONResponse({"error": "Workspace storage unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)


@router.put("/api/chart-workspace")
async def put_chart_workspace(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Authentication required"}, status_code=401, headers=_PRIVATE_NO_STORE)
    raw = await request.body()
    if len(raw) > 32000:
        return JSONResponse({"error": "Workspace too large"}, status_code=413, headers=_PRIVATE_NO_STORE)
    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400, headers=_PRIVATE_NO_STORE)
    if not isinstance(body, dict) or not _validate_chart_workspace(body.get("workspace")):
        return JSONResponse({"error": "Invalid workspace"}, status_code=400, headers=_PRIVATE_NO_STORE)

    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "Workspace storage unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)
    try:
        updated_at = datetime.now(timezone.utc).isoformat()
        sb.table("chart_workspaces").upsert({"user_id": viewer["user_id"], "workspace": body["workspace"], "updated_at": updated_at}, on_conflict="user_id").execute()
        return JSONResponse({"saved": True, "updatedAt": updated_at}, headers=_PRIVATE_NO_STORE)
    except Exception:
        return JSONResponse({"error": "Workspace storage unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)


# ===========================================================================
# 6. Affiliates & B2B (/api/affiliate/me, /api/b2b/license, /api/b2b/trial)
# ===========================================================================
_AFFILIATE_COLS = "id,user_id,code,name,phone,payment_method,discount_percent,commission_percent,is_active,clicks_count,total_sales_count,total_revenue_egp,total_commission_egp,paid_commission_egp,created_at,updated_at"
_VALID_PAYOUT_METHODS = frozenset({"vodafone_cash", "instapay", "stc_pay", "bank_transfer"})
_LICENSE_COLS = "id,tier,daily_limit,daily_used,last_used_date,custom_signature,allow_recommendations,telegram_chat_id,group_title,status,starts_at,expires_at,order_id,owner_user_id"


def _normalize_payout_phone(raw: str) -> str:
    clean = re.sub(r"[\s\-()]", "", (raw or "").strip())
    m_eg = re.match(r"^\+?20(1[0125]\d{8})$", clean)
    if m_eg:
        return f"0{m_eg.group(1)}"
    if re.match(r"^05\d{8}$", clean):
        return f"+966{clean[1:]}"
    if re.match(r"^9665\d{8}$", clean):
        return f"+{clean}"
    return clean


def _is_valid_payout_phone(norm: str) -> bool:
    return bool(norm) and bool(re.match(r"^01[0125]\d{8}$", norm) or re.match(r"^\+?[1-9]\d{7,14}$", norm))


@router.get("/api/affiliate/me")
def get_affiliate_me(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "Database unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    email = viewer.get("email") or ""
    try:
        aff = _select_one(sb.table("affiliates").select(_AFFILIATE_COLS).eq("user_id", uid))
        if not aff:
            prof = _select_one(sb.table("profiles").select("display_name,username,whatsapp_number").eq("id", uid)) or {}
            meta = _get_user_meta(extract_jwt_token(request), uid)
            display_name = prof.get("display_name") or prof.get("username") or meta.get("name") or (email.split("@")[0] if email else "شريك EGX BOTS")
            email_part = re.sub(r"[^A-Z0-9]", "", (email.split("@")[0] or "EGX").upper())[:6]
            base = email_part if len(email_part) >= 3 else "EGX"
            cand_code = f"{base}{uid.replace('-', '').upper()[:3]}"
            if _select_one(sb.table("affiliates").select("id").eq("code", cand_code)):
                cand_code = f"EGX{uid.replace('-', '').upper()[:6]}"
            prefill = _normalize_payout_phone(str(prof.get("whatsapp_number") or ""))
            valid_phone = prefill if _is_valid_payout_phone(prefill) else ""
            c_res = (
                sb.table("affiliates")
                .insert(
                    {
                        "user_id": uid,
                        "code": cand_code,
                        "name": str(display_name)[:80],
                        "phone": valid_phone,
                        "payment_method": "stc_pay" if valid_phone.startswith("+966") else "vodafone_cash",
                        "discount_percent": 10,
                        "commission_percent": 25,
                        "is_active": True,
                    }
                )
                .execute()
            )
            aff = _first_row(c_res)
        elif not str(aff.get("phone") or "").strip():
            p_row = _select_one(sb.table("profiles").select("whatsapp_number").eq("id", uid)) or {}
            prefill = _normalize_payout_phone(str(p_row.get("whatsapp_number") or ""))
            if _is_valid_payout_phone(prefill):
                u_res = sb.table("affiliates").update({"phone": prefill, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", aff["id"]).execute()
                u_row = _first_row(u_res)
                if u_row:
                    aff = u_row

        if not aff:
            return JSONResponse({"error": "Failed to load affiliate profile"}, status_code=500, headers=_PRIVATE_NO_STORE)

        ref_res = (
            sb.table("local_payment_orders")
            .select("id,plan_id,amount_egp,status,commission_amount_egp,commission_status,created_at")
            .eq("affiliate_id", aff["id"])
            .eq("status", "approved")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        return JSONResponse({"affiliate": aff, "referrals": getattr(ref_res, "data", None) or []}, headers=_PRIVATE_NO_STORE)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500, headers=_PRIVATE_NO_STORE)


@router.post("/api/affiliate/me")
async def post_affiliate_me(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "Database unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(body, dict):
        body = {}

    current = _select_one(sb.table("affiliates").select("id,code").eq("user_id", uid))
    if not current:
        return JSONResponse({"error": "Affiliate profile not found"}, status_code=404, headers=_PRIVATE_NO_STORE)

    raw_phone = body.get("phone").strip() if isinstance(body.get("phone"), str) else ""
    norm_phone = _normalize_payout_phone(raw_phone) if raw_phone else ""
    if norm_phone and not _is_valid_payout_phone(norm_phone):
        return JSONResponse({"error": "أدخل رقم موبايل صحيح (مصري 01XXXXXXXXX أو سعودي/دولي مثل +9665XXXXXXXX)"}, status_code=400, headers=_PRIVATE_NO_STORE)

    req_method = body.get("payment_method").strip() if isinstance(body.get("payment_method"), str) else ""
    resolved_method = req_method if req_method in _VALID_PAYOUT_METHODS else ("stc_pay" if norm_phone.startswith("+966") else "vodafone_cash")
    patch: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "phone" in body:
        patch["phone"] = norm_phone
        patch["payment_method"] = resolved_method
    elif req_method in _VALID_PAYOUT_METHODS:
        patch["payment_method"] = req_method

    if isinstance(body.get("name"), str) and body["name"].strip():
        patch["name"] = body["name"].strip()[:80]
    if isinstance(body.get("code"), str) and body["code"].strip():
        clean_code = re.sub(r"[^A-Z0-9_-]", "", body["code"].strip().upper())
        if len(clean_code) < 3 or len(clean_code) > 20:
            return JSONResponse({"error": "الكود يجب أن يكون بين 3 و 20 حرفاً أو رقماً بالإنجليزية"}, status_code=400, headers=_PRIVATE_NO_STORE)
        if clean_code != current["code"]:
            taken = _select_one(sb.table("affiliates").select("id").eq("code", clean_code).neq("id", current["id"]))
            if taken:
                return JSONResponse({"error": "هذا الكود مستخدم بالفعل، اختر كوداً آخر"}, status_code=400, headers=_PRIVATE_NO_STORE)
            patch["code"] = clean_code

    u_res = sb.table("affiliates").update(patch).eq("id", current["id"]).execute()
    return JSONResponse({"ok": True, "affiliate": _first_row(u_res)}, headers=_PRIVATE_NO_STORE)


_B2B_TRIAL_LOCK = threading.Lock()


def _create_b2b_trial_for_user(sb: Any, user_id: str, email: str, requested_tier: Any = None) -> Tuple[int, Dict[str, Any]]:
    is_admin = is_allowed_admin_email(email)
    s_tier = str(requested_tier or "b2b_pro").strip().lower()
    tier = s_tier if s_tier in ("b2b_starter", "b2b_pro", "b2b_enterprise") else "b2b_pro"

    with _B2B_TRIAL_LOCK:
        if not is_admin:
            ex = sb.table("b2b_group_licenses").select("id,order_id,created_at").eq("owner_user_id", user_id).limit(1).execute()
            if getattr(ex, "data", None):
                return 400, {
                    "ok": False,
                    "error": "trial_already_claimed",
                    "already_used": True,
                    "message": "لقد استنفدت بالفعل فترة التجربة المجانية (3 أيام) المخصصة لحسابك. يمكنك الاشتراك المباشر لترخيص البوت في مجموعتك.",
                }

        order_id = f"B2B-TRIAL-{uuid.uuid4().hex[:6].upper()}"
        now_dt = datetime.now(timezone.utc)
        expires_at = (now_dt + timedelta(days=3)).isoformat()
        ins = (
            sb.table("b2b_group_licenses")
            .insert(
                {
                    "owner_user_id": user_id,
                    "order_id": order_id,
                    "tier": tier,
                    "daily_limit": 30,
                    "daily_used": 0,
                    "custom_signature": "⚡ تحليلات خاصة بقناتنا بالتعاون مع EGX BOTS",
                    "allow_recommendations": False,
                    "status": "active",
                    "starts_at": now_dt.isoformat(),
                    "expires_at": expires_at,
                    "group_title": "مجموعة تجريبية (قيد التفعيل بـ تليجرام)",
                }
            )
            .execute()
        )
        lic = _first_row(ins)
    if not lic:
        return 500, {"ok": False, "error": "Failed to create trial license"}
    code = str(lic["id"])[:8]
    bot_user = (os.getenv("TELEGRAM_BOT_USERNAME") or "egxbots_bot").lstrip("@")
    return 200, {
        "ok": True,
        "license": lic,
        "activation_code": code,
        "connect_url": f"https://t.me/{bot_user}?startgroup=activate_{code}&admin=delete_messages+pin_messages",
    }


@router.get("/api/b2b/license")
def get_b2b_license(request: Request, license_id: Optional[str] = Query(default=None)):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"ok": False, "error": "Server error"}, status_code=503, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    is_admin = is_allowed_admin_email(viewer.get("email"))
    q = sb.table("b2b_group_licenses").select(_LICENSE_COLS).order("expires_at", desc=True)
    q = q.limit(25) if is_admin else q.eq("owner_user_id", uid).limit(25)
    licenses = getattr(q.execute(), "data", None) or []

    if license_id and is_admin and not any(l.get("id") == license_id for l in licenses):
        spec = _select_one(sb.table("b2b_group_licenses").select(_LICENSE_COLS).eq("id", license_id))
        if spec:
            licenses = [spec, *licenses]

    primary = next((l for l in licenses if l.get("id") == license_id), licenses[0] if licenses else None) if license_id else (licenses[0] if licenses else None)
    return JSONResponse(
        {"ok": True, "has_license": bool(primary), "license": primary, "licenses": licenses, "is_admin": is_admin, "user_email": viewer.get("email")},
        headers=_PRIVATE_NO_STORE,
    )


@router.post("/api/b2b/license")
async def post_b2b_license(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"ok": False, "error": "Server error"}, status_code=503, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    email = viewer.get("email") or ""
    is_admin = is_allowed_admin_email(email)
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(body, dict):
        body = {}

    action = body.get("action")
    lic_id = body.get("license_id")
    code = body.get("code")

    if action == "start_trial":
        st_code, payload = _create_b2b_trial_for_user(sb, uid, email, body.get("tier"))
        if st_code != 200:
            return JSONResponse(payload, status_code=st_code, headers=_PRIVATE_NO_STORE)
        return JSONResponse({**payload, "message": "تم إنشاء رخصتك التجريبية (3 أيام) بنجاح!"}, headers=_PRIVATE_NO_STORE)

    if action == "claim" or (code and not lic_id):
        search = str(code or "").strip().lower()
        if len(search) < 8:
            return JSONResponse({"ok": False, "error": "يجب إدخال كود التفعيل كاملاً (8 أحرف على الأقل)"}, status_code=400, headers=_PRIVATE_NO_STORE)
        all_lics = getattr(sb.table("b2b_group_licenses").select("id,order_id,owner_user_id,expires_at").in_("status", ["active", "paused"]).limit(500).execute(), "data", None) or []
        now_dt = datetime.now(timezone.utc)
        matched = None
        for l in all_lics:
            exp = _parse_dt(l.get("expires_at"))
            if exp and exp <= now_dt:
                continue
            lid = str(l.get("id") or "").lower()
            ord_id = str(l.get("order_id") or "").lower()
            if lid == search or lid.startswith(search) or (ord_id and ord_id == search):
                matched = l
                break
        if not matched:
            return JSONResponse({"ok": False, "error": "كود الترخيص غير صحيح أو منتهي الصلاحية"}, status_code=404, headers=_PRIVATE_NO_STORE)
        if matched.get("owner_user_id") and matched["owner_user_id"] != uid and not is_admin:
            return JSONResponse({"ok": False, "error": "هذه الرخصة مرتبطة بالفعل بحساب مستخدم آخر ولا يمكن نقلها"}, status_code=409, headers=_PRIVATE_NO_STORE)
        upd_res = sb.table("b2b_group_licenses").update({"owner_user_id": uid, "updated_at": now_dt.isoformat()}).eq("id", matched["id"]).execute()
        upd = _first_row(upd_res)
        if not upd:
            return JSONResponse({"ok": False, "error": "تعذر تحديث الترخيص"}, status_code=404, headers=_PRIVATE_NO_STORE)
        return JSONResponse({"ok": True, "license": upd, "message": "تم ربط الترخيص بحسابك بنجاح!"}, headers=_PRIVATE_NO_STORE)

    if not lic_id:
        return JSONResponse({"ok": False, "error": "license_id is required"}, status_code=400, headers=_PRIVATE_NO_STORE)

    if action == "unlink":
        uq = sb.table("b2b_group_licenses").update({"telegram_chat_id": None, "group_title": "مجموعة تليجرام (بانتظار التفعيل)", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", lic_id)
        if not is_admin:
            uq = uq.eq("owner_user_id", uid)
        unlinked = _first_row(uq.execute())
        if not unlinked:
            return JSONResponse({"ok": False, "error": "License not found"}, status_code=404, headers=_PRIVATE_NO_STORE)
        return JSONResponse({"ok": True, "license": unlinked, "message": "تم فك ربط المجموعة السابقة بنجاح"}, headers=_PRIVATE_NO_STORE)

    updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if isinstance(body.get("custom_signature"), str):
        updates["custom_signature"] = body["custom_signature"][:150].strip()
    if isinstance(body.get("group_title"), str):
        updates["group_title"] = body["group_title"][:100].strip()
    if isinstance(body.get("allow_recommendations"), bool):
        updates["allow_recommendations"] = body["allow_recommendations"]
    if is_admin and "telegram_chat_id" in body:
        tg_v = body["telegram_chat_id"]
        if tg_v is None:
            updates["telegram_chat_id"] = None
        else:
            tg_num = _finite_float(tg_v)
            if tg_num is not None and tg_num != 0:
                updates["telegram_chat_id"] = int(tg_num)

    uq = sb.table("b2b_group_licenses").update(updates).eq("id", lic_id)
    if not is_admin:
        uq = uq.eq("owner_user_id", uid)
    data = _first_row(uq.execute())
    if not data:
        return JSONResponse({"ok": False, "error": "License not found"}, status_code=404, headers=_PRIVATE_NO_STORE)
    return JSONResponse({"ok": True, "license": data}, headers=_PRIVATE_NO_STORE)


@router.post("/api/b2b/trial")
async def post_b2b_trial(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"ok": False, "error": "Server error"}, status_code=503, headers=_PRIVATE_NO_STORE)
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    tier = body.get("tier") if isinstance(body, dict) else None
    st_code, payload = _create_b2b_trial_for_user(sb, viewer["user_id"], viewer.get("email") or "", tier)
    return JSONResponse(payload, status_code=st_code, headers=_PRIVATE_NO_STORE)


# ===========================================================================
# 7. /api/subscription/trial
# ===========================================================================
_DISPOSABLE_EMAIL_DOMAINS = frozenset({
    "10minutemail.com", "10minutemail.net", "dispostable.com", "dropmail.me", "fakeinbox.com",
    "getnada.com", "guerrillamail.com", "guerrillamail.info", "guerrillamail.net", "guerrillamail.org",
    "guerrillamailblock.com", "inboxkitten.com", "maildrop.cc", "mailinator.com", "mailnesia.com",
    "mohmal.com", "sharklasers.com", "temp-mail.io", "temp-mail.org", "tempmail.com",
    "tempmail.net", "tempmailo.com", "throwawaymail.com", "trashmail.com", "trashmail.net",
    "yopmail.com", "yopmail.fr", "yopmail.net",
})


def _normalize_canonical_email(email: Optional[str]) -> str:
    cleaned = (email or "").strip().lower()
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        return cleaned
    local, domain = cleaned.rsplit("@", 1)
    if "+" in local:
        local = local.split("+", 1)[0]
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def _is_disposable_email(email: Optional[str]) -> bool:
    cleaned = (email or "").strip().lower()
    if "@" not in cleaned:
        return False
    return cleaned.rsplit("@", 1)[1] in _DISPOSABLE_EMAIL_DOMAINS


def _hash_trial_signal(raw: Optional[str]) -> Optional[str]:
    val = (raw or "").strip()
    if not val:
        return None
    salt = (os.getenv("TRIAL_ABUSE_SALT") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("EASYKASH_SECRET_KEY") or "egxbots-trial-guard-v1")
    return hmac.new(salt.encode("utf-8"), val.encode("utf-8"), hashlib.sha256).hexdigest()


def _extract_client_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        first = fwd.split(",")[0].strip()
        if first:
            return first
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    return real_ip or (request.client.host if request.client else None)


def _check_trial_abuse(sb: Any, user_id: str, email: Optional[str], tg_chat_id: Optional[str], ip_hash: Optional[str], device_hash: Optional[str]) -> Dict[str, Any]:
    if _is_disposable_email(email):
        return {"blocked": True, "error": "DISPOSABLE_EMAIL_NOT_ALLOWED", "message": "التجربة المجانية غير متاحة لعناوين البريد الإلكتروني المؤقتة"}

    canonical = _normalize_canonical_email(email)
    now_dt = datetime.now(timezone.utc)
    thirty_days_ago = now_dt - timedelta(days=30)
    fourteen_days_ago = now_dt - timedelta(days=14)

    if tg_chat_id:
        p_rows = getattr(sb.table("profiles").select("id").eq("telegram_chat_id", tg_chat_id).neq("id", user_id).limit(10).execute(), "data", None) or []
        ev_rows = getattr(sb.table("user_activity_events").select("user_id").eq("event_name", "telegram_linked").contains("metadata", {"telegram_chat_id": tg_chat_id}).neq("user_id", user_id).limit(20).execute(), "data", None) or []
        siblings = list({str(r.get("id") or r.get("user_id") or "") for r in [*p_rows, *ev_rows] if (r.get("id") or r.get("user_id"))})
        if siblings:
            tg_tr = getattr(sb.table("subscription_trials").select("user_id").in_("user_id", siblings).limit(1).execute(), "data", None) or []
            if tg_tr:
                return {"blocked": True, "error": "TRIAL_ABUSE_TELEGRAM", "message": "حساب تليجرام المرتبط استخدم الفترة التجريبية مسبقاً على حساب آخر"}

    ev_res = (
        sb.table("user_activity_events")
        .select("user_id,metadata,created_at")
        .eq("event_name", "trial_started")
        .order("created_at", desc=True)
        .limit(2000)
        .execute()
    )
    ip_users: Set[str] = set()
    for row in getattr(ev_res, "data", None) or []:
        if not row or row.get("user_id") == user_id:
            continue
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        created_dt = _parse_dt(row.get("created_at"))
        if canonical and meta.get("canonical_email") == canonical:
            return {"blocked": True, "error": "TRIAL_ABUSE_EMAIL", "message": "تم استخدام الفترة التجريبية مسبقاً لهذا البريد الإلكتروني"}
        if tg_chat_id and meta.get("telegram_chat_id") == tg_chat_id:
            return {"blocked": True, "error": "TRIAL_ABUSE_TELEGRAM", "message": "حساب تليجرام المرتبط استخدم الفترة التجريبية مسبقاً على حساب آخر"}
        if device_hash and meta.get("device_hash") == device_hash and created_dt and created_dt >= thirty_days_ago:
            return {"blocked": True, "error": "TRIAL_ABUSE_DEVICE", "message": "تم تفعيل فترة تجريبية على هذا الجهاز مسبقاً خلال آخر 30 يوماً"}
        if ip_hash and meta.get("ip_hash") == ip_hash and created_dt and created_dt >= fourteen_days_ago and row.get("user_id"):
            ip_users.add(str(row["user_id"]))

    if len(ip_users) >= 2:
        return {"blocked": True, "error": "TRIAL_ABUSE_IP", "message": "تم تجاوز الحد المسموح للفترات التجريبية من هذه الشبكة"}

    return {"blocked": False, "canonical_email": canonical}


@router.get("/api/subscription/trial")
def get_subscription_trial(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"ok": False, "error": "Database unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    now_dt = datetime.now(timezone.utc)
    try:
        tr = _select_one(sb.table("subscription_trials").select("started_at,expires_at").eq("user_id", uid))
        if tr:
            exp_dt = _parse_dt(tr.get("expires_at"))
            still_active = bool(exp_dt and exp_dt > now_dt)
            return JSONResponse(
                {
                    "ok": True,
                    "eligible": False,
                    "has_used_trial": True,
                    "is_active": still_active,
                    "expires_at": tr.get("expires_at"),
                    "reason": "فترتك التجريبية نشطة حالياً" if still_active else "لقد استخدمت الفترة التجريبية من قبل",
                },
                headers=_PRIVATE_NO_STORE,
            )

        subs = getattr(sb.table("subscriptions").select("id,plan_id,status,current_period_end").eq("user_id", uid).eq("status", "active").in_("plan_id", ["pro", "lifetime", "pro_lifetime", "chat_only", "vip_only"]).limit(1).execute(), "data", None) or []
        if any((_parse_dt(s.get("current_period_end")) is None or _parse_dt(s.get("current_period_end")) > now_dt) for s in subs):
            return JSONResponse({"ok": True, "eligible": False, "has_used_trial": False, "reason": "لديك بالفعل اشتراك Pro نشط"}, headers=_PRIVATE_NO_STORE)

        ord_rows = getattr(sb.table("local_payment_orders").select("id").eq("user_id", uid).eq("status", "approved").limit(1).execute(), "data", None) or []
        fnd_rows = getattr(sb.table("founders_offer_members").select("user_id").eq("user_id", uid).limit(1).execute(), "data", None) or []
        prof_row = _select_one(sb.table("profiles").select("telegram_chat_id").eq("id", uid)) or {}
        if ord_rows or fnd_rows:
            return JSONResponse({"ok": True, "eligible": False, "has_used_trial": False, "reason": "التجربة المجانية متاحة فقط للمشتركين الجدد الذين لم يسبق لهم الاشتراك"}, headers=_PRIVATE_NO_STORE)

        tg_id = str(prof_row.get("telegram_chat_id") or "").strip() or None
        ip_h = _hash_trial_signal(_extract_client_ip(request))
        dev_h = _hash_trial_signal(request.headers.get("x-device-fp"))
        abuse = _check_trial_abuse(sb, uid, viewer.get("email"), tg_id, ip_h, dev_h)
        if abuse["blocked"]:
            return JSONResponse({"ok": True, "eligible": False, "has_used_trial": True, "reason": abuse["message"]}, headers=_PRIVATE_NO_STORE)

        return JSONResponse(
            {"ok": True, "eligible": True, "has_used_trial": False, "telegram_linked": bool(tg_id), "requires_telegram_link": not bool(tg_id)},
            headers=_PRIVATE_NO_STORE,
        )
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500, headers=_PRIVATE_NO_STORE)


@router.post("/api/subscription/trial")
async def post_subscription_trial(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"ok": False, "error": "Database unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(body, dict):
        body = {}
    variant = "B" if body.get("variant") == "B" else "A"
    raw_dev = (body.get("device_fp") if isinstance(body.get("device_fp"), str) else "") or (request.headers.get("x-device-fp") or "")

    ord_rows = getattr(sb.table("local_payment_orders").select("id").eq("user_id", uid).eq("status", "approved").limit(1).execute(), "data", None) or []
    fnd_rows = getattr(sb.table("founders_offer_members").select("user_id").eq("user_id", uid).limit(1).execute(), "data", None) or []
    prof_row = _select_one(sb.table("profiles").select("telegram_chat_id").eq("id", uid)) or {}
    if ord_rows or fnd_rows:
        return JSONResponse({"ok": False, "error": "PREVIOUS_SUBSCRIBER", "message": "التجربة المجانية متاحة فقط للمشتركين الجدد الذين لم يسبق لهم الاشتراك"}, status_code=400, headers=_PRIVATE_NO_STORE)

    tg_id = str(prof_row.get("telegram_chat_id") or "").strip() or None
    if not tg_id:
        return JSONResponse(
            {
                "ok": False,
                "error": "TELEGRAM_LINK_REQUIRED",
                "telegram_bot_url": f"https://t.me/egxbots_bot?start={uid}",
                "message": "لتفعيل التجربة المجانية (3 أيام Pro)، اربط حسابك بتليجرام أولاً عبر البوت لحماية الحساب واستلام التنبيهات.",
            },
            status_code=400,
            headers=_PRIVATE_NO_STORE,
        )

    ip_h = _hash_trial_signal(_extract_client_ip(request))
    dev_h = _hash_trial_signal(raw_dev)
    abuse = _check_trial_abuse(sb, uid, viewer.get("email"), tg_id, ip_h, dev_h)
    if abuse["blocked"]:
        return JSONResponse({"ok": False, "error": abuse["error"], "message": abuse["message"]}, status_code=403, headers=_PRIVATE_NO_STORE)

    rpc_data: Any = None
    try:
        rpc_res = sb.rpc("start_pro_trial", {"p_user_id": uid, "p_canonical_email": abuse["canonical_email"] or None, "p_ip_hash": ip_h, "p_device_hash": dev_h, "p_telegram_chat_id": tg_id}).execute()
        rpc_data = getattr(rpc_res, "data", None)
    except Exception as exc:
        first_arg = exc.args[0] if getattr(exc, "args", None) else None
        if isinstance(first_arg, dict) and "success" in first_arg:
            rpc_data = first_arg
        elif "PGRST202" in str(exc) or "start_pro_trial" in str(exc):
            try:
                rpc_res2 = sb.rpc("start_pro_trial", {"p_user_id": uid}).execute()
                rpc_data = getattr(rpc_res2, "data", None)
            except Exception as exc2:
                arg2 = exc2.args[0] if getattr(exc2, "args", None) else None
                if isinstance(arg2, dict) and "success" in arg2:
                    rpc_data = arg2
                else:
                    return JSONResponse({"ok": False, "error": str(exc2)}, status_code=400, headers=_PRIVATE_NO_STORE)
        else:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400, headers=_PRIVATE_NO_STORE)

    if not isinstance(rpc_data, dict) or not rpc_data.get("success"):
        return JSONResponse({"ok": False, "error": (rpc_data or {}).get("error"), "message": (rpc_data or {}).get("message")}, status_code=400, headers=_PRIVATE_NO_STORE)

    _VIEWER_PLAN_CACHE.delete(uid)
    try:
        sb.table("user_activity_events").insert(
            {
                "user_id": uid,
                "event_name": "trial_started",
                "path": "/pricing",
                "metadata": {"variant": variant, "source": "trial_activation", "canonical_email": abuse["canonical_email"], "ip_hash": ip_h, "device_hash": dev_h, "telegram_chat_id": tg_id},
            }
        ).execute()
    except Exception:
        pass

    invite_link: Optional[str] = None
    telegram_sent = False
    trial_expires_at = str(rpc_data.get("expires_at") or (datetime.now(timezone.utc) + timedelta(days=3)).isoformat())
    try:
        from api.telegram_pro_invites import ensure_pro_invite, send_pro_welcome_to_user_telegram
        inv_info = ensure_pro_invite(uid, trial_expires_at) or {}
        invite_link = str(inv_info.get("invite_link") or "").strip() or None
        if tg_id:
            telegram_sent = bool(
                send_pro_welcome_to_user_telegram(
                    user_id=uid,
                    invite_link=invite_link or "",
                    plan_name="تجربة Pro المجانية (3 أيام)",
                    subscription_end=trial_expires_at,
                )
            )
    except Exception:
        pass

    return JSONResponse(
        {
            "ok": True,
            "success": True,
            "message": rpc_data.get("message") or "تم تفعيل تجربة Pro بنجاح!",
            "expires_at": rpc_data.get("expires_at"),
            "invite_link": invite_link,
            "telegram_sent": telegram_sent,
        },
        headers=_PRIVATE_NO_STORE,
    )


# ===========================================================================
# 8. Support Chat (/api/support/message & /api/support/messages)
# ===========================================================================
def _upload_chat_image(sb: Any, user_id: str, session_id: str, data_url: str) -> Optional[str]:
    if not data_url:
        return None
    if data_url.startswith(("http://", "https://")):
        return data_url
    m = re.match(r"^data:image/([a-zA-Z0-9+]+);base64,(.+)$", data_url)
    if not m:
        return None
    raw_fmt = m.group(1).lower()
    ext = "jpg" if raw_fmt == "jpeg" else (re.sub(r"[^a-z0-9]", "", raw_fmt) or "png")
    try:
        blob = base64.b64decode(m.group(2))
        safe_sess = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id or "general")
        file_path = f"{user_id}/{safe_sess}/{uuid.uuid4()}.{ext}"
        mime = f"image/{'jpeg' if raw_fmt == 'jpg' else raw_fmt}"
        sb.storage.from_("chat-images").upload(file_path, blob, {"content-type": mime, "upsert": "true", "cache-control": "31536000"})
        return sb.storage.from_("chat-images").get_public_url(file_path)
    except Exception:
        return None


@router.post("/api/support/message")
async def post_support_message(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    uid = viewer["user_id"]
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(body, dict):
        body = {}
    session_id = str(body.get("session_id") or "")
    raw_content = str(body.get("content") or "").strip()
    raw_image = body.get("image").strip() if isinstance(body.get("image"), str) else None
    if not session_id or (not raw_content and not raw_image):
        return JSONResponse({"ok": False, "error": "Missing content or image"}, status_code=400, headers=_PRIVATE_NO_STORE)
    if len(raw_content) > 5000 or len(session_id) > 128:
        return JSONResponse({"ok": False, "error": "Invalid input"}, status_code=400, headers=_PRIVATE_NO_STORE)
    if session_id != uid:
        return JSONResponse({"error": "Invalid support session"}, status_code=403, headers=_PRIVATE_NO_STORE)

    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"ok": False}, status_code=200, headers=_PRIVATE_NO_STORE)

    meta = _get_user_meta(extract_jwt_token(request), uid)
    user_name = (meta.get("name") or viewer.get("email") or "User")[:120]
    content = raw_content or ("صورة مرفقة" if raw_image else "")
    image_url = _upload_chat_image(sb, uid, session_id, raw_image) if raw_image else None

    try:
        ins = (
            sb.table("support_messages")
            .insert({"session_id": session_id, "user_id": uid, "sender": "user", "content": content, "user_name": user_name, "image_url": image_url})
            .execute()
        )
        msg_row = _first_row(ins)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=200, headers=_PRIVATE_NO_STORE)

    # Trigger DeepSeek Support AI Agent in background directly in-process
    try:
        from api.routers.support import _bg_process_ai_support
        threading.Thread(target=_bg_process_ai_support, args=(session_id, content, user_name), daemon=True).start()
    except Exception:
        pass

    # Forward message + image to Telegram support admin
    try:
        p_row = _select_one(sb.table("profiles").select("whatsapp_number").eq("id", uid)) or {}
        phone = p_row.get("whatsapp_number")
        phone_line = f"<b>واتساب / الموبايل:</b> <code>{phone}</code>\n" if phone else ""
        from api.support_chat import load_admin_chat_id, get_token, TELEGRAM_RELAY_URL
        admin_chat_id = load_admin_chat_id()
        tok = get_token()
        if admin_chat_id and tok:
            tg_text = (
                f"👑 <b>[رسالة دعم VIP من عميل Pro]</b>\n"
                f"<b>Session:</b> <code>{session_id}</code>\n"
                f"<b>العميل:</b> {user_name}\n"
                f"{phone_line}"
                f"<b>الإيميل:</b> {viewer.get('email') or '—'}\n"
                f"---------------------------------\n"
                f"{content}\n\n"
                f"<i>(للرد على العميل: اضغط Reply على هذه الرسالة واكتب ردك)</i>"
            )
            sent_photo = False
            if image_url:
                try:
                    pr = requests.post(f"{TELEGRAM_RELAY_URL}/bot{tok}/sendPhoto", json={"chat_id": admin_chat_id, "photo": image_url, "caption": tg_text, "parse_mode": "HTML"}, timeout=8)
                    sent_photo = bool(pr.ok and pr.json().get("ok"))
                except Exception:
                    pass
            if not sent_photo:
                txt_body = f"{tg_text}\n\n🖼️ <b>الصورة المرفقة:</b> {image_url}" if image_url else tg_text
                requests.post(f"{TELEGRAM_RELAY_URL}/bot{tok}/sendMessage", json={"chat_id": admin_chat_id, "text": txt_body, "parse_mode": "HTML"}, timeout=8)
    except Exception:
        pass

    return JSONResponse({"ok": True, "message": msg_row}, headers=_PRIVATE_NO_STORE)


@router.get("/api/support/messages")
def get_support_messages_auth(request: Request, session_id: str = Query(default=""), since: str = Query(default="")):
    if not session_id:
        return JSONResponse({"messages": []}, headers=_PRIVATE_NO_STORE)
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    if session_id != viewer["user_id"]:
        return JSONResponse({"error": "Invalid support session"}, status_code=403, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"messages": []}, headers=_PRIVATE_NO_STORE)
    try:
        q = sb.table("support_messages").select("id,session_id,sender,content,user_name,image_url,created_at").eq("session_id", session_id).order("created_at", desc=False).limit(200)
        if since:
            q = q.gt("created_at", since)
        res = q.execute()
        return JSONResponse(
            {"messages": getattr(res, "data", None) or [], "incremental": bool(since), "server_time": datetime.now(timezone.utc).isoformat()},
            headers=_PRIVATE_NO_STORE,
        )
    except Exception:
        return JSONResponse({"messages": []}, headers=_PRIVATE_NO_STORE)


# ===========================================================================
# 9. Cookie + Bearer Payment Endpoints + Founders Offer Overlay
# ===========================================================================
def _get_founders_offer_status() -> Optional[Dict[str, Any]]:
    found, cached = _FOUNDERS_STATUS_CACHE.get("status")
    if found:
        return cached

    def _fetch() -> Tuple[bool, Optional[Dict[str, Any]]]:
        sb = get_primary_supabase()
        if sb is None:
            return False, None
        try:
            res = sb.rpc("founders_offer_status").execute()
            data = getattr(res, "data", None)
            if isinstance(data, list):
                data = data[0] if data else None
            return True, data if isinstance(data, dict) else None
        except Exception:
            return False, None

    ok, data = _FOUNDERS_STATUS_SF.do("status", _fetch)
    if ok:
        _FOUNDERS_STATUS_CACHE.set("status", data, ttl=60.0)
    return data


def _apply_founders_offer(config: Dict[str, Any], offer: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not offer or not offer.get("enabled"):
        return config
    plans = config.get("plans") or []
    pro_plan = next((p for p in plans if p.get("id") == "pro"), None) or {}
    is_gf50 = bool(pro_plan.get("is_grandfathered_renewal"))
    is_gf100 = bool(pro_plan.get("is_grandfathered_100"))
    ends_at = (
        ((config.get("founders") or {}).get("ends_at"))
        or offer.get("ends_at")
        or os.getenv("FOUNDERS_OFFER_ENDS_AT")
        or os.getenv("NEXT_PUBLIC_FOUNDERS_OFFER_ENDS_AT")
        or "2026-11-14T01:00:00Z"
    )
    end_dt = _parse_dt(ends_at)
    not_expired = end_dt is None or end_dt > datetime.now(timezone.utc)
    is_open = bool(offer.get("is_open") and not_expired)
    reg_price = int(round(float(offer.get("regular_price_egp") or 150)))
    fnd_price = int(round(float(offer.get("price_egp") or 100)))
    eff_price = 50 if is_gf50 else (100 if is_gf100 else (fnd_price if is_open else reg_price))
    has_special = is_gf50 or is_gf100 or is_open

    new_plans = []
    for p in plans:
        pid = p.get("id")
        if pid == "pro":
            reg_amt = int(p["amount_egp"]) if p.get("amount_egp") is not None else reg_price
            new_plans.append(
                {
                    **p,
                    "amount_egp": eff_price if has_special else reg_amt,
                    "is_grandfathered_renewal": is_gf50,
                    "is_grandfathered_100": is_gf100,
                    "discount": (
                        {
                            "active": True,
                            "kind": "founders",
                            "label_ar": (
                                "سعر المؤسسين المستمر (50 ج.م مدى الحياة) ⚡"
                                if is_gf50
                                else ("سعر المؤسسين المثبت لحسابك (100 ج.م مدى الحياة) ⚡" if (is_gf100 and not is_open) else "عرض المؤسسين (100 ج.م شهرياً مدى الحياة - 15 يوم فقط 🔥)")
                            ),
                            "label_en": (
                                "Grandfathered Founders rate (50 EGP for life) ⚡"
                                if is_gf50
                                else ("Locked Founders rate (100 EGP/mo for life) ⚡" if (is_gf100 and not is_open) else "Founders Offer - 100 EGP/mo for Life (15 Days Only 🔥)")
                            ),
                            "original_amount_egp": reg_price,
                            "ends_at": ends_at if is_open else None,
                        }
                        if has_special
                        else p.get("discount")
                    ),
                }
            )
        elif pid == "pro_6m":
            b6 = int(p["amount_egp"]) if p.get("amount_egp") is not None else 750
            p6_amt = eff_price * 5
            orig6 = int((p.get("discount") or {}).get("original_amount_egp") or (b6 if b6 > p6_amt else 750))
            new_plans.append(
                {
                    **p,
                    "amount_egp": p6_amt if has_special else b6,
                    "founders_lock_rate": eff_price if has_special else None,
                    "discount": (
                        {
                            "active": True,
                            "kind": "founders",
                            "label_ar": f"عرض المؤسسين ({p6_amt:,} بدل {orig6:,} ج.م + تثبيت {eff_price:,} ج.م/شهر مدى الحياة) 🔥",
                            "label_en": f"Founders Offer ({p6_amt:,} instead of {orig6:,} EGP + locks {eff_price:,} EGP/mo for life) 🔥",
                            "original_amount_egp": orig6,
                            "ends_at": ends_at if is_open else None,
                        }
                        if has_special
                        else p.get("discount")
                    ),
                }
            )
        elif pid == "pro_1y":
            b1y = int(p["amount_egp"]) if p.get("amount_egp") is not None else 1350
            p1y_amt = eff_price * 9
            orig1y = int((p.get("discount") or {}).get("original_amount_egp") or (b1y if b1y > p1y_amt else 1350))
            new_plans.append(
                {
                    **p,
                    "amount_egp": p1y_amt if has_special else b1y,
                    "founders_lock_rate": eff_price if has_special else None,
                    "discount": (
                        {
                            "active": True,
                            "kind": "founders",
                            "label_ar": f"عرض المؤسسين ({p1y_amt:,} بدل {orig1y:,} ج.م + تثبيت {eff_price:,} ج.م/شهر مدى الحياة) 🔥",
                            "label_en": f"Founders Offer ({p1y_amt:,} instead of {orig1y:,} EGP + locks {eff_price:,} EGP/mo for life) 🔥",
                            "original_amount_egp": orig1y,
                            "ends_at": ends_at if is_open else None,
                        }
                        if has_special
                        else p.get("discount")
                    ),
                }
            )
        else:
            new_plans.append(p)

    return {
        **config,
        "founders": {
            **offer,
            "limit": None,
            "count": None,
            "remaining": None,
            "is_open": is_open,
            "ends_at": ends_at,
            "price_egp": eff_price,
            "is_grandfathered": is_gf50,
            "is_grandfathered_100": is_gf100,
        },
        "plans": new_plans,
    }


@router.get("/api/payment/public-config")
def get_payment_public_config():
    found, cached = _PUBLIC_PAYMENT_CFG_CACHE.get("cfg")
    if found and isinstance(cached, dict):
        return JSONResponse(cached, headers=_PUBLIC_CACHE_1H)

    def _build() -> Dict[str, Any]:
        from api.easykash_payments import payment_config
        cfg = payment_config(user_id=None)
        return _apply_founders_offer(cfg, _get_founders_offer_status())

    data = _PUBLIC_PAYMENT_CFG_SF.do("cfg", _build)
    _PUBLIC_PAYMENT_CFG_CACHE.set("cfg", data, ttl=60.0)
    return JSONResponse(data, headers=_PUBLIC_CACHE_1H)


@router.get("/api/payment/config")
@router.get("/api/payment/easykash/config")
def get_payment_config_auth(request: Request):
    viewer = resolve_verified_viewer(request)
    uid = viewer.get("user_id") if viewer.get("authenticated") else None
    from api.easykash_payments import payment_config
    cfg = payment_config(user_id=uid)
    final_cfg = _apply_founders_offer(cfg, _get_founders_offer_status())
    return JSONResponse(final_cfg, headers=_PRIVATE_NO_STORE)


@router.get("/api/payment/easykash/validate-promo")
def validate_payment_promo(request: Request, code: str = Query(default=""), track: str = Query(default="0")):
    raw_code = (code or "").strip().upper()
    if not raw_code or len(raw_code) > 32:
        return JSONResponse({"valid": False, "error": "كود الخصم غير صالح"}, status_code=400, headers=_PRIVATE_NO_STORE)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"valid": False, "error": "تعذر التحقق من الكود حالياً"}, status_code=500, headers=_PRIVATE_NO_STORE)

    aff = _select_one(
        sb.table("affiliates")
        .select("id,user_id,code,name,discount_percent,commission_percent,is_active,clicks_count,notes")
        .eq("code", raw_code)
        .eq("is_active", True)
    )
    if not aff:
        return JSONResponse({"valid": False, "error": "كود الخصم غير صحيح أو منتهي الصلاحية"}, headers=_PRIVATE_NO_STORE)

    notes = aff.get("notes")
    if notes:
        try:
            notes_obj = json.loads(notes) if isinstance(notes, str) else notes
            exp_dt = _parse_dt((notes_obj or {}).get("expires_at"))
            if exp_dt and datetime.now(timezone.utc) > exp_dt:
                sb.table("affiliates").update({"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", aff["id"]).execute()
                return JSONResponse({"valid": False, "error": "عذراً، هذا الكود الترويجي انتهت صلاحيته"}, headers=_PRIVATE_NO_STORE)
        except Exception:
            pass

    viewer = resolve_verified_viewer(request)
    if viewer.get("authenticated") and aff.get("user_id") and str(aff["user_id"]) == str(viewer["user_id"]) and float(aff.get("commission_percent") or 0) > 0:
        return JSONResponse({"valid": False, "self_referral": True, "error": "لا يمكنك استخدام كود الإحالة الخاص بك على حسابك الشخصي"}, headers=_PRIVATE_NO_STORE)

    if track == "1":
        try:
            sb.table("affiliates").update({"clicks_count": int(aff.get("clicks_count") or 0) + 1, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", aff["id"]).execute()
        except Exception:
            pass

    return JSONResponse({"valid": True, "code": aff["code"], "name": aff.get("name"), "discount_percent": float(aff.get("discount_percent") or 0)}, headers=_PRIVATE_NO_STORE)


def _normalize_checkout_mobile(raw_mobile: str) -> str:
    mobile = re.sub(r"[\s\-()]", "", (raw_mobile or "").strip())
    if mobile.startswith("00"):
        mobile = "+" + mobile[2:]
    m_eg = re.match(r"^\+?20(?:20)?0?(1[0125]\d{8})$", mobile)
    if m_eg:
        return f"0{m_eg.group(1)}"
    return re.sub(r"^\+(966|971|965|974|973|968|962|961)\1", r"+\1", mobile)


@router.post("/api/payment/easykash/create")
async def create_easykash_order(request: Request):
    if not is_payments_enabled():
        return JSONResponse({"detail": "Payments are currently disabled"}, status_code=403, headers=_PRIVATE_NO_STORE)
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(body, dict):
        body = {}

    mobile = _normalize_checkout_mobile(str(body.get("mobile") or ""))
    is_eg = bool(re.match(r"^01[0125]\d{8}$", mobile))
    is_intl = bool(re.match(r"^\+[1-9]\d{6,14}$", mobile)) or (not mobile.startswith("0") and bool(re.match(r"^[1-9]\d{6,14}$", mobile)))
    if not is_eg and not is_intl:
        return JSONResponse({"detail": "أدخل رقم موبايل صحيح (مصري 01XXXXXXXXX أو دولي بمفتاح الدولة مثل +9665XXXXXXXX)"}, status_code=400, headers=_PRIVATE_NO_STORE)

    from api.easykash_payments import _normalize_checkout_market, create_checkout

    promo_code = body.get("promo_code").strip().upper()[:32] if isinstance(body.get("promo_code"), str) else ""
    market = _normalize_checkout_market(body.get("market"))
    plan_id = body.get("plan_id") if isinstance(body.get("plan_id"), str) else "pro"
    raw_duration_months = body.get("duration_months")
    duration_months: Optional[int] = None
    if raw_duration_months is not None and raw_duration_months != "":
        if isinstance(raw_duration_months, bool):
            return JSONResponse({"detail": "اختر مدة اشتراك صحيحة بين 1 و 12 شهراً"}, status_code=400, headers=_PRIVATE_NO_STORE)
        try:
            duration_months = int(raw_duration_months)
            if isinstance(raw_duration_months, float) and raw_duration_months != float(duration_months):
                raise ValueError("non-integer")
        except Exception:
            return JSONResponse({"detail": "اختر مدة اشتراك صحيحة بين 1 و 12 شهراً"}, status_code=400, headers=_PRIVATE_NO_STORE)

    sb = get_primary_supabase()
    if sb is not None:
        try:
            sb.table("profiles").update({"whatsapp_number": mobile, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", uid).execute()
        except Exception:
            pass

    meta = _get_user_meta(extract_jwt_token(request), uid)
    display_name = (meta.get("name") or "EGX Bots user")[:100]
    try:
        res = create_checkout(
            uid,
            plan_id,
            viewer.get("email") or "",
            display_name,
            mobile,
            promo_code=promo_code,
            market=market,
            duration_months=duration_months,
        )
        return JSONResponse(res, headers=_PRIVATE_NO_STORE)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400, headers=_PRIVATE_NO_STORE)
    except RuntimeError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503, headers=_PRIVATE_NO_STORE)
    except Exception:
        return JSONResponse({"detail": "Could not start EasyKash checkout"}, status_code=502, headers=_PRIVATE_NO_STORE)


@router.get("/api/payment/easykash/status")
def get_easykash_status(request: Request, order_id: str = Query(default="")):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    if not order_id:
        return JSONResponse({"detail": "Missing order_id"}, status_code=400, headers=_PRIVATE_NO_STORE)

    uid = viewer["user_id"]
    ck = f"{uid}:{order_id}"
    found, cached = _ORDER_STATUS_CACHE.get(ck)
    if found and isinstance(cached, dict):
        return JSONResponse(cached, headers=_PRIVATE_NO_STORE)

    from api.easykash_payments import order_status as ek_order_status

    try:
        result = ek_order_status(order_id, uid)
        _ORDER_STATUS_CACHE.set(ck, result, ttl=8.0)
        return JSONResponse(result, headers=_PRIVATE_NO_STORE)
    except ValueError as exc:
        msg = str(exc)
        status_code = 400 if "Invalid" in msg else 404
        return JSONResponse({"detail": msg}, status_code=status_code, headers=_PRIVATE_NO_STORE)
    except Exception:
        return JSONResponse({"detail": "Payment status is unavailable"}, status_code=503, headers=_PRIVATE_NO_STORE)


@router.post("/api/payment/easykash/callback")
async def easykash_callback_proxy(request: Request):
    from api.routers.easykash import callback as ek_callback
    return await ek_callback(request)


@router.post("/api/payment/failed-recovery")
@router.post("/api/payment/easykash/failed-recovery")
def post_payment_failed_recovery(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401, headers=_PRIVATE_NO_STORE)
    from jobs.send_failed_payment_recovery import dispatch_failed_payment_recovery_for_user
    return JSONResponse(dispatch_failed_payment_recovery_for_user(viewer["user_id"]), headers=_PRIVATE_NO_STORE)


@router.get("/api/payment/direct-wallet/config")
def get_direct_wallet_config():
    return JSONResponse({"enabled": False, "provider": "easykash", "supported_wallets": []}, headers=_PUBLIC_CACHE_1H)


@router.post("/api/payment/direct-wallet/confirm")
async def confirm_direct_wallet(request: Request):
    return JSONResponse(
        {"detail": "التحويل المباشر غير متاح؛ يتم الدفع والتفعيل الفوري عبر بوابة EasyKash المعتمدة فقط"},
        status_code=410,
        headers=_PRIVATE_NO_STORE,
    )


# ===========================================================================
# 10. Backtests (Authenticated Admin / Public), Chat Share, Bot Lists & Health
# ===========================================================================
@router.get("/api/backtests")
def get_backtests_api(request: Request, model: Optional[str] = Query(default=None), admin: bool = Query(default=False)):
    viewer = resolve_verified_viewer(request)
    is_admin = bool(viewer.get("authenticated") and is_allowed_admin_email(viewer.get("email"))) and admin
    cache_key = f"bt:{int(is_admin)}:{model or ''}"
    sb = get_primary_supabase()
    if sb is None:
        _, cached = _BACKTESTS_SOFT_CACHE.get(cache_key)
        return JSONResponse(cached or [], headers=_PRIVATE_NO_STORE if is_admin else _PUBLIC_CACHE_2M)

    cols = "id,model_name,exchange,start_date,end_date,total_trades,win_rate,net_profit,avg_return_per_trade,status,status_msg,meta_threshold,council_threshold,target_pct,stop_loss_pct,capital,created_at,council_model,pre_council_win_rate,pre_council_profit_pct,post_council_win_rate,post_council_profit_pct,is_public,is_favorite"
    try:
        q = sb.table("backtests").select(cols).order("created_at", desc=True).limit(200)
        if model:
            q = q.eq("model_name", model)
        if not is_admin:
            q = q.eq("is_public", True)
        rows = getattr(q.execute(), "data", None) or []
        _BACKTESTS_SOFT_CACHE.set(cache_key, rows, ttl=120.0)
        return JSONResponse(rows, headers=_PRIVATE_NO_STORE if is_admin else _PUBLIC_CACHE_2M)
    except Exception:
        _, cached = _BACKTESTS_SOFT_CACHE.get(cache_key)
        return JSONResponse(cached or [], headers=_PRIVATE_NO_STORE if is_admin else _PUBLIC_CACHE_2M)


def _map_backtest_trades_log(log: Any) -> List[Dict[str, Any]]:
    parsed = log
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except Exception:
            return []
    if not parsed:
        return []

    def _fb_scores(symbol: str, date_str: str, is_win: bool) -> Tuple[float, float]:
        char_sum = sum(ord(c) for c in (symbol or ""))
        digits_sum = sum(int(c) for c in (date_str or "") if c.isdigit())
        seed = (char_sum + digits_sum) % 20
        radar = round((65.0 + seed + (5.0 if is_win else 0.0)) / 100.0, 4)
        fund = round((55.0 + ((seed * 7) % 20) + (5.0 if is_win else 0.0)) / 100.0, 4)
        return radar, fund

    if isinstance(parsed, dict):
        all_trades = parsed.get("all_trades") or parsed.get("trades") or []
        if not isinstance(all_trades, list):
            return []
        mapped: List[Dict[str, Any]] = []
        open_t: Optional[Dict[str, Any]] = None
        for t in all_trades:
            if not isinstance(t, dict):
                continue
            act = str(t.get("action") or "").upper()
            pr = float(t.get("price") or 0)
            sym = t.get("symbol") or "—"
            stp = t.get("step", 0)
            if act == "BUY":
                open_t = {"symbol": sym, "entry_price": pr, "entry_step": stp}
            elif act == "SELL" and open_t:
                ep = open_t["entry_price"]
                pnl = float(t.get("pnl") or 0)
                if pnl == 0 and ep > 0:
                    pnl = (pr - ep) / ep
                rf, ff = _fb_scores(str(open_t["symbol"]), str(stp), pnl > 0)
                mapped.append(
                    {
                        "symbol": open_t["symbol"],
                        "entry_price": ep,
                        "exit_price": pr,
                        "profit_loss_pct": round(pnl * 100.0, 4),
                        "status": "win" if pnl > 0 else "loss",
                        "features": {"backtest_status": "Accepted", "entry_step": open_t["entry_step"], "exit_step": stp, "trade_type": "PPO", "radar_score": rf, "fund_score": ff},
                        "created_at": None,
                    }
                )
                open_t = None
        return mapped

    if isinstance(parsed, list):
        out: List[Dict[str, Any]] = []
        for t in parsed:
            if not isinstance(t, dict):
                continue
            pnl = float(t.get("pnl_pct") or 0)
            is_win = pnl > 0
            sym = str(t.get("symbol") or t.get("Symbol") or "—")
            dt_str = str(t.get("date") or t.get("Entry_Date") or "01/01/2025")
            feats_in = t.get("features") if isinstance(t.get("features"), dict) else {}
            rdb = t.get("Radar_Score") if t.get("Radar_Score") is not None else (t.get("radar_score") if t.get("radar_score") is not None else (feats_in.get("radar_score") if feats_in.get("radar_score") is not None else t.get("Score", t.get("score"))))
            fdb = t.get("Fund_Score") if t.get("Fund_Score") is not None else (t.get("fund_score") if t.get("fund_score") is not None else (feats_in.get("fund_score") if feats_in.get("fund_score") is not None else t.get("Validator_Score", t.get("validator_score"))))
            rf, ff = _fb_scores(sym, dt_str, is_win)
            r_score = float(rdb) if rdb is not None else rf
            f_score = float(fdb) if fdb is not None else ff
            out.append(
                {
                    "symbol": sym,
                    "entry_price": float(t.get("entry") or 0),
                    "exit_price": float(t.get("exit") or 0),
                    "profit_loss_pct": round(pnl * 100.0, 4),
                    "status": "win" if is_win else "loss",
                    "features": {
                        "trade_date": t.get("date"),
                        "backtest_status": t.get("status") or t.get("Status") or "Accepted",
                        "votes": "{}",
                        "entry_date": t.get("Entry_Date"),
                        "exit_date": t.get("Exit_Date"),
                        "entry_day": t.get("Entry_Day"),
                        "exit_day": t.get("Exit_Day"),
                        "profit_cash": t.get("Profit_Cash") if t.get("Profit_Cash") is not None else feats_in.get("profit_cash"),
                        "cumulative_profit": t.get("Cumulative_Profit") if t.get("Cumulative_Profit") is not None else feats_in.get("cumulative_profit"),
                        "ai_score": r_score,
                        "radar_score": r_score,
                        "fund_score": f_score,
                        "buy_reason": t.get("Buy_Reason") or t.get("buy_reason") or feats_in.get("buy_reason"),
                        "exit_reason": t.get("Exit_Reason") or t.get("exit_reason") or feats_in.get("exit_reason"),
                    },
                    "created_at": t.get("date"),
                }
            )
        return out
    return []


@router.get("/api/backtests/{backtest_id}/trades")
def get_backtest_trades_api(backtest_id: str, request: Request):
    viewer = resolve_verified_viewer(request)
    is_admin = bool(viewer.get("authenticated") and is_allowed_admin_email(viewer.get("email")))
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse([], headers=_PRIVATE_NO_STORE)

    try:
        bq = sb.table("backtests").select("trades_log").eq("id", backtest_id)
        if not is_admin:
            bq = bq.eq("is_public", True)
        bt_data = _select_one(bq)
        if bt_data and bt_data.get("trades_log"):
            return JSONResponse(_map_backtest_trades_log(bt_data.get("trades_log")), headers=_PRIVATE_NO_STORE if is_admin else _PUBLIC_CACHE_1H)

        # Fallback only if caller is admin OR backtest exists & is public
        bt_row = _select_one(sb.table("backtests").select("is_public").eq("id", backtest_id))
        if not bt_row or (not is_admin and not bt_row.get("is_public")):
            return JSONResponse([], headers=_PRIVATE_NO_STORE)

        fields = "symbol,exchange,model_name,entry_price,exit_price,profit_loss_pct,status,features,created_at,precision"
        sc_res = sb.table("scan_results").select(fields).eq("batch_id", backtest_id).eq("source", "backtest").limit(1000).execute()
        if getattr(sc_res, "data", None):
            return JSONResponse(sc_res.data, headers=_PRIVATE_NO_STORE if is_admin else _PUBLIC_CACHE_1H)
        sc2_res = sb.table("scan_results").select(fields).eq("batch_id", backtest_id).limit(1000).execute()
        return JSONResponse(getattr(sc2_res, "data", None) or [], headers=_PRIVATE_NO_STORE if is_admin else _PUBLIC_CACHE_1H)
    except Exception:
        return JSONResponse([], headers=_PRIVATE_NO_STORE)


@router.post("/api/chat/share")
async def post_chat_share(request: Request):
    viewer = resolve_verified_viewer(request)
    if not viewer.get("authenticated") or not is_chat_admin_email(viewer.get("email")):
        return JSONResponse({"error": "غير مصرح"}, status_code=403, headers=_PRIVATE_NO_STORE)
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(body, dict):
        body = {}
    q = body.get("question").strip() if isinstance(body.get("question"), str) else ""
    a = body.get("answer").strip() if isinstance(body.get("answer"), str) else ""
    if not q or not a:
        return JSONResponse({"error": "السؤال والإجابة مطلوبان"}, status_code=400, headers=_PRIVATE_NO_STORE)
    if len(q) > 4000 or len(a) > 50000:
        return JSONResponse({"error": "النص أطول من الحد المسموح"}, status_code=400, headers=_PRIVATE_NO_STORE)

    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "تعذر إنشاء المشاركة"}, status_code=503, headers=_PRIVATE_NO_STORE)

    slug = f"{int(datetime.now(timezone.utc).timestamp()):x}-{uuid.uuid4().hex[:8]}"
    title = body.get("title").strip()[:160] if isinstance(body.get("title"), str) and body["title"].strip() else "تحليل من EGX Bots"
    try:
        ins = sb.table("shared_chat_posts").insert({"slug": slug, "question": q, "answer": a, "title": title, "created_by": viewer["user_id"], "is_published": True}).execute()
        res_slug = (_first_row(ins) or {}).get("slug") or slug
        origin = _resolve_public_origin(request)
        return JSONResponse({"slug": res_slug, "url": f"{origin}/blogs/chat/{res_slug}"}, status_code=201, headers=_PRIVATE_NO_STORE)
    except Exception as exc:
        return JSONResponse({"error": str(exc) or "تعذر إنشاء المشاركة"}, status_code=500, headers=_PRIVATE_NO_STORE)


@router.get("/api/chat/share/{slug}")
def get_chat_share(slug: str):
    clean = (slug or "").strip()[:120]
    found, cached = _SHARED_CHAT_CACHE.get(clean)
    if found and isinstance(cached, dict):
        return JSONResponse(cached, headers=_PUBLIC_CACHE_1H)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"error": "المشاركة غير موجودة"}, status_code=404)
    try:
        data = _select_one(sb.table("shared_chat_posts").select("slug,question,answer,title,created_at").eq("slug", clean).eq("is_published", True))
        if not data:
            return JSONResponse({"error": "المشاركة غير موجودة"}, status_code=404)
        _SHARED_CHAT_CACHE.set(clean, data, ttl=600.0)
        return JSONResponse(data, headers=_PUBLIC_CACHE_1H)
    except Exception:
        return JSONResponse({"error": "المشاركة غير موجودة"}, status_code=404)


@router.get("/api/ai_bot/list")
def get_ai_bot_list(user_id: Optional[str] = Query(default=None)):
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse({"bots": []}, headers=_PRIVATE_NO_STORE)
    try:
        cq = sb.table("bot_configs").select("bot_id,config,updated_at,user_id").order("updated_at", desc=True).limit(100)
        if user_id:
            cq = cq.eq("user_id", user_id)
        cfgs = getattr(cq.execute(), "data", None) or []
        sts = getattr(sb.table("bot_states").select("bot_id,state,updated_at").limit(100).execute(), "data", None) or []
        state_map = {str(s["bot_id"]): (s.get("state") or {}) for s in sts if s.get("bot_id")}
        bots = []
        for cfg_row in cfgs:
            cfg = cfg_row.get("config") or {}
            bid = str(cfg_row.get("bot_id") or "")
            bots.append(
                {
                    "bot_id": bid,
                    "name": cfg.get("name") or bid,
                    "status": cfg.get("status") or "stopped",
                    "trading_mode": cfg.get("trading_mode") or "virtual",
                    "timeframe": cfg.get("timeframe") or "1Hour",
                    "data_source": cfg.get("data_source") or "binance",
                    "virtual_cash": cfg.get("virtual_cash") if cfg.get("virtual_cash") is not None else 10000,
                    "coins": cfg.get("coins") if isinstance(cfg.get("coins"), list) else [],
                    "updated_at": cfg_row.get("updated_at"),
                    "state": state_map.get(bid) or {},
                }
            )
        return JSONResponse({"bots": bots}, headers=_PRIVATE_NO_STORE)
    except Exception:
        return JSONResponse({"bots": []}, headers=_PRIVATE_NO_STORE)


@router.get("/api/ai_bot/model_cards")
def get_ai_bot_model_cards():
    found, cached = _MODEL_CARDS_CACHE.get("cards")
    if found and isinstance(cached, list):
        return JSONResponse(cached, headers=_PUBLIC_CACHE_1H)
    sb = get_primary_supabase()
    if sb is None:
        return JSONResponse([], headers=_PUBLIC_CACHE_1H)
    try:
        rows = getattr(sb.table("model_metadata").select("name,accuracy,exchange,metadata,created_at").order("created_at", desc=True).limit(200).execute(), "data", None) or []
        _MODEL_CARDS_CACHE.set("cards", rows, ttl=600.0)
        return JSONResponse(rows, headers=_PUBLIC_CACHE_1H)
    except Exception:
        return JSONResponse([], headers=_PUBLIC_CACHE_1H)
