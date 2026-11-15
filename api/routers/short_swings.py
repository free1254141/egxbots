import os
import hmac
import datetime as dt
from fastapi import APIRouter, Query, Request, HTTPException, Header, Response
from typing import Optional
from api.perf_utils import (
    BoundedTTLCache,
    SingleFlight,
    get_market_supabase,
    resolve_request_market,
    resolve_verified_viewer,
)
from api.short_swings_engine import get_cached_short_swings, compute_short_swings

router = APIRouter(prefix="/api/short-swings", tags=["Short Swings"])

_SAUDI_SWINGS_CACHE = BoundedTTLCache(max_entries=4, default_ttl=86400.0)
_SAUDI_SWINGS_SF = SingleFlight()


def clear_saudi_swings_cache() -> None:
    """Clear Saudi short-swings in-memory cache when daily runner refreshes data."""
    _SAUDI_SWINGS_CACHE.clear()


def _is_internal_authorized(x_admin_key: Optional[str]) -> bool:
    secret = (os.getenv("ADMIN_SECRET_KEY") or "").strip()
    # Missing configuration must fail closed.  This endpoint is also directly
    # reachable on the Python service, so a missing secret must never turn
    # ?is_pro=true into an entitlement bypass.
    return bool(secret and x_admin_key and hmac.compare_digest(x_admin_key.strip(), secret))


def _get_saudi_short_swings(refresh: bool = False) -> dict:
    """Read or recompute Saudi short swings payload using bounded TTL + SingleFlight cache."""
    if refresh:
        _SAUDI_SWINGS_CACHE.clear()
        return compute_short_swings(exchange="TADAWUL")

    found, cached = _SAUDI_SWINGS_CACHE.get("saudi_short_swings_v1")
    if found:
        return cached

    def _fetch() -> dict:
        sb = get_market_supabase("tasi")
        if sb is not None:
            try:
                res = (
                    sb.table("market_cache")
                    .select("payload")
                    .eq("cache_key", "saudi_short_swings_v1")
                    .eq("country", "Saudi Arabia")
                    .limit(1)
                    .execute()
                )
                rows = res.data or []
                if rows and isinstance(rows[0].get("payload"), dict):
                    return rows[0]["payload"]
            except Exception as exc:
                print(f"[SHORT_SWINGS] Saudi market_cache read error: {exc}")

        local_cached = get_cached_short_swings(exchange="TADAWUL")
        if isinstance(local_cached, dict) and local_cached.get("status") != "unavailable":
            return local_cached
        return {"status": "unavailable", "kpis": {}, "active_trades": [], "closed_trades": [], "market": "TASI", "currency": "SAR"}

    payload = _SAUDI_SWINGS_SF.do("saudi_short_swings_v1", _fetch)
    if isinstance(payload, dict) and payload.get("status") != "unavailable":
        _SAUDI_SWINGS_CACHE.set("saudi_short_swings_v1", payload)
    return payload


@router.get("")
@router.get("/")
def get_short_swings(
    request: Request,
    response: Response = None,
    is_pro: bool = Query(False, description="Whether the requesting user has an active PRO subscription"),
    refresh: bool = Query(False, description="Force recompute signals"),
    market: Optional[str] = Query(None, description="Target market: egx or tasi/tadawul"),
    x_admin_key: Optional[str] = Header(None, alias="x-admin-key"),
):
    """
    Fetch active and historical short swing trades.

    Security & Entitlement:
      - Closed trades: NEVER encrypted for any user. Historical record is always fully visible for auditing.
      - Active (open) trades: locked (is_locked=True) for free users ONLY IF entry_date is
        within the last 15 days (the signal is still fresh & actionable) or pending for tomorrow.
        Active trades older than 15 days are shown freely.
      - PRO unmasking requires either an authenticated internal secret (x-admin-key) OR a
        cryptographically verified Supabase session belonging to an active PRO subscriber.
        refresh=True is restricted strictly to internal x-admin-key requests.
    """
    is_internal = _is_internal_authorized(x_admin_key)
    if not is_internal:
        refresh = False
        viewer = resolve_verified_viewer(request)
        is_pro = bool(viewer.get("authenticated") and viewer.get("pro"))

    if response is not None:
        response.headers["Cache-Control"] = "private, no-cache, no-store, max-age=0"
        response.headers["Vercel-CDN-Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie, Authorization, X-Admin-Key, X-Egxbots-Market"

    mkt_norm = resolve_request_market(request, market)
    if mkt_norm == "tasi":
        data = _get_saudi_short_swings(refresh=refresh)
    else:
        data = compute_short_swings() if refresh else get_cached_short_swings()
    cutoff_date = (dt.date.today() - dt.timedelta(days=15)).strftime("%Y-%m-%d")

    if not is_pro:
        # Active trades: lock only the ones whose entry_date is within the last 15 days or is_pending_entry for tomorrow
        masked_active = []
        for t in data.get("active_trades", []):
            entry_date = t.get("entry_date", "")
            is_pending = bool(t.get("is_pending_entry"))
            is_recent = is_pending or bool(entry_date and entry_date >= cutoff_date)
            if is_recent:
                sym = t.get("symbol", "")
                masked_active.append({
                    # signal_id is derived from the real ticker/date and is
                    # therefore sensitive just like the ticker itself.
                    "signal_id": None,
                    "symbol": (sym[:2] + "**") if len(sym) > 2 else "**",
                    "name_ar": "سهم قيادي مشفر (متاح لـ PRO)",
                    "name_en": "PRO Signal",
                    "sector": t.get("sector", "عام"),
                    "entry_date": t.get("entry_date"),
                    "signal_date": t.get("signal_date"),
                    "entry_price": None,
                    "current_price": None,
                    "reference_close": None,
                    "trailing_stop": None,
                    "stop_loss": None,
                    "ema10_trend": None,
                    "return_pct": t.get("return_pct", 0.0),
                    "is_breakeven_protected": t.get("is_breakeven_protected", False),
                    "max_gain_pct": t.get("max_gain_pct", 0.0),
                    "trigger_type": "صفقة زخم وليدة مشفرة",
                    "status": t.get("status"),
                    "is_pending_entry": is_pending,
                    "is_locked": True
                })
            else:
                masked_active.append({**t, "is_locked": False})

        unmasked_closed = [{**t, "is_locked": False} for t in data.get("closed_trades", [])]

        return {
            "status": data.get("status", "ok"),
            "is_pro": False,
            "kpis": data.get("kpis", {}),
            "active_trades": masked_active,
            "closed_trades": unmasked_closed,
            "total_active": data.get("total_active", len(masked_active)),
            "total_closed": data.get("total_closed", len(unmasked_closed)),
            "as_of": data.get("as_of"),
            "phase": data.get("phase"),
            "computed_at": data.get("computed_at"),
            "session_complete": data.get("session_complete"),
            "cutoff_date_15d": cutoff_date,
            "upgrade_cta": "اشترك في باقة PRO للوصول اللحظي لإشارات الصفقات القصيرة فور ظهورها ومستويات الوقف المتحرك اليومية."
        }

    # PRO users: all trades unmasked
    unmasked_closed = [{**t, "is_locked": False} for t in data.get("closed_trades", [])]
    unmasked_active = [{**t, "is_locked": False} for t in data.get("active_trades", [])]

    return {
        "status": data.get("status", "ok"),
        "is_pro": True,
        "kpis": data.get("kpis", {}),
        "active_trades": unmasked_active,
        "closed_trades": unmasked_closed,
        "total_active": data.get("total_active", len(unmasked_active)),
        "total_closed": data.get("total_closed", len(unmasked_closed)),
        "as_of": data.get("as_of"),
        "phase": data.get("phase"),
        "computed_at": data.get("computed_at"),
        "session_complete": data.get("session_complete"),
        "cutoff_date_15d": cutoff_date
    }
