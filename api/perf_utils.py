"""Shared performance, caching, single-flight coalescing, and auth helpers for HF offload routes.

Provides O(1) bounded LRU+TTL caching, concurrent thundering-herd coalescing,
unified EGX/Saudi market Supabase resolution, and SHA-256 cached JWT verification.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import os
import re
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import Request

from api.agentic_chat.auth_guard import extract_jwt_token
from api.payment_common import is_payments_enabled
import api.stock_ai as stock_ai

CAIRO_TZ = ZoneInfo("Africa/Cairo")
PRO_PLAN_IDS = frozenset({"pro", "pro_6m", "pro_1y", "lifetime", "pro_lifetime"})
SAUDI_SYMBOL_QUERY_RE = re.compile(r"^\d{4}(\.(sr|sa|tadawul))?$", re.IGNORECASE)
_DEFAULT_UNLIMITED_CHAT_EMAILS = frozenset({
    "user@gmail.com",
    "abdallahsaied912@gmail.com",
    "session.flow.test@example.com",
})
_SAUDI_CLIENT_LOCK = threading.Lock()
_SAUDI_CLIENT = None


class BoundedTTLCache:
    """Thread-safe O(1) bounded LRU + monotonic TTL cache."""

    def __init__(self, max_entries: int = 512, default_ttl: float = 300.0) -> None:
        self._max_entries = max(1, int(max_entries))
        self._default_ttl = max(0.0, float(default_ttl))
        self._lock = threading.Lock()
        self._store: OrderedDict[str, Tuple[float, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Tuple[bool, Any]:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return False, None
            expires_at, value = entry
            if now >= expires_at:
                del self._store[key]
                self._misses += 1
                return False, None
            self._store.move_to_end(key)
            self._hits += 1
            return True, value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        ttl_s = self._default_ttl if ttl is None else max(0.0, float(ttl))
        if ttl_s <= 0:
            return
        expires_at = time.monotonic() + ttl_s
        with self._lock:
            self._store[key] = (expires_at, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
            }


class _Flight:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.value: Any = None
        self.error: Optional[BaseException] = None


class SingleFlight:
    """Coalesce concurrent calls sharing the same key into a single execution."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight: Dict[str, _Flight] = {}

    def do(self, key: str, fn: Callable[[], Any]) -> Any:
        with self._lock:
            existing = self._inflight.get(key)
            if existing is None:
                flight = _Flight()
                self._inflight[key] = flight
                is_leader = True
            else:
                flight = existing
                is_leader = False

        if not is_leader:
            flight.event.wait()
            if flight.error is not None:
                raise flight.error
            return flight.value

        try:
            flight.value = fn()
            return flight.value
        except BaseException as exc:
            flight.error = exc
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)
            flight.event.set()


_AUTH_USER_CACHE = BoundedTTLCache(max_entries=1024, default_ttl=60.0)
_AUTH_USER_SF = SingleFlight()
_VIEWER_PLAN_CACHE = BoundedTTLCache(max_entries=1024, default_ttl=45.0)
_VIEWER_PLAN_SF = SingleFlight()


def clear_perf_caches() -> None:
    """Reset auth & plan caches (primarily for deterministic unit tests)."""
    _AUTH_USER_CACHE.clear()
    _VIEWER_PLAN_CACHE.clear()


def normalize_market_hint(raw: Optional[str]) -> Optional[str]:
    """Normalize explicit market/country/exchange string to 'tasi' or 'egx'."""
    val = (raw or "").strip().lower()
    if not val:
        return None
    if val in ("tasi", "tadawul", "sa", "sar", "saudi", "saudi arabia", "sr", "ksa"):
        return "tasi"
    if val in ("egx", "eg", "egp", "egypt", "ca", "cairo"):
        return "egx"
    return None


def resolve_request_market(request: Request, explicit_hint: Optional[str] = None) -> str:
    """Resolve target market ('egx' or 'tasi') matching Next.js resolveRequestMarket."""
    for candidate in (
        explicit_hint,
        request.query_params.get("market"),
        request.query_params.get("country"),
        request.query_params.get("exchange"),
    ):
        norm = normalize_market_hint(candidate)
        if norm:
            return norm

    sym_param = (request.query_params.get("symbol") or "").strip()
    if sym_param and SAUDI_SYMBOL_QUERY_RE.match(sym_param):
        return "tasi"

    for candidate in (
        request.headers.get("x-egxbots-market"),
        request.headers.get("x-market"),
        request.cookies.get("egxbots_market"),
        request.cookies.get("egx_market"),
    ):
        norm = normalize_market_hint(candidate)
        if norm:
            return norm
    return "egx"


def get_market_exchange(market: str) -> str:
    return "TADAWUL" if market == "tasi" else "EGX"


def get_primary_supabase():
    """Return initialized primary EGX Supabase client or None."""
    if not stock_ai.supabase:
        stock_ai._init_supabase()
    return stock_ai.supabase if stock_ai.supabase else None


def get_market_supabase(market: str):
    """Return primary (egx) or Saudi (tasi) Supabase client."""
    if market != "tasi":
        return get_primary_supabase()

    global _SAUDI_CLIENT
    if _SAUDI_CLIENT is not None:
        return _SAUDI_CLIENT

    url = (os.getenv("SAUDI_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_URL") or "").strip()
    key = (
        os.getenv("SAUDI_SUPABASE_SECRET_KEY")
        or os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SAUDI_SUPABASE_SERVICE_KEY")
        or os.getenv("SAUDI_SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_ANON_KEY")
        or ""
    ).strip()
    if not url or not key:
        return None

    with _SAUDI_CLIENT_LOCK:
        if _SAUDI_CLIENT is None:
            from supabase import create_client
            _SAUDI_CLIENT = create_client(url, key)
    return _SAUDI_CLIENT


def get_cairo_date_str(now: Optional[datetime] = None) -> str:
    dt_val = now or datetime.now(timezone.utc)
    if dt_val.tzinfo is None:
        dt_val = dt_val.replace(tzinfo=timezone.utc)
    return dt_val.astimezone(CAIRO_TZ).strftime("%Y-%m-%d")


def _parse_iso(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    raw = str(ts).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def has_active_pro_subscription(rows: Iterable[Dict[str, Any]], now: Optional[datetime] = None) -> bool:
    """Strict paid Pro subscription check matching frontend hasActiveProSubscription."""
    now_dt = now or datetime.now(timezone.utc)
    for row in rows or ():
        plan = str(row.get("plan_id") or "").lower()
        status = str(row.get("status") or "").lower()
        if plan not in PRO_PLAN_IDS or status not in ("active", "trialing"):
            continue
        end_dt = _parse_iso(row.get("current_period_end"))
        if end_dt is not None and end_dt <= now_dt:
            continue
        return True
    return False


def is_unlimited_chat_user(
    user_id: Optional[str],
    email: Optional[str],
    email_confirmed: bool = False,
) -> bool:
    env_emails = {
        e.strip().lower()
        for e in (os.getenv("UNLIMITED_CHAT_EMAILS") or "").split(",")
        if e.strip()
    }
    emails = _DEFAULT_UNLIMITED_CHAT_EMAILS | env_emails
    uids = {
        u.strip()
        for u in (os.getenv("UNLIMITED_CHAT_USER_IDS") or "").split(",")
        if u.strip()
    }
    if user_id and user_id in uids:
        return True
    if email and email_confirmed and email.strip().lower() in emails:
        return True
    return False


def resolve_subscription_quota_window(
    rows: Optional[List[Dict[str, Any]]],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Single source of truth for subscription Pro state and monthly quota boundary."""
    now_dt = now or datetime.now(timezone.utc)
    items = rows if isinstance(rows, list) else []
    pro = has_active_pro_subscription(items, now_dt)

    active_sub = None
    for row in items:
        plan = str(row.get("plan_id") or "").lower()
        status = str(row.get("status") or "").lower()
        if plan not in PRO_PLAN_IDS or status not in ("active", "trialing"):
            continue
        end_dt = _parse_iso(row.get("current_period_end"))
        if end_dt is not None and end_dt <= now_dt:
            continue
        active_sub = row
        break
    if active_sub is None and items:
        active_sub = items[0]

    today_str = get_cairo_date_str(now_dt)
    cal_month_start_str = f"{today_str[:7]}-01"
    effective_month_start_str = cal_month_start_str

    if pro and active_sub and active_sub.get("current_period_start"):
        parsed = _parse_iso(active_sub.get("current_period_start"))
        if parsed is not None:
            sub_start_str = parsed.astimezone(timezone.utc).strftime("%Y-%m-%d")
            if cal_month_start_str < sub_start_str <= today_str:
                effective_month_start_str = sub_start_str

    return {
        "is_pro": pro,
        "active_sub": active_sub,
        "today_str": today_str,
        "cal_month_start_str": cal_month_start_str,
        "effective_month_start_str": effective_month_start_str,
    }


def _verify_token_cached(token: str) -> Optional[Dict[str, Any]]:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    found, cached = _AUTH_USER_CACHE.get(token_hash)
    if found:
        return cached

    def _load() -> Tuple[bool, Optional[Dict[str, Any]]]:
        sb = get_primary_supabase()
        if sb is None:
            return False, None
        try:
            res = sb.auth.get_user(token)
            user_obj = getattr(res, "user", None)
            if not user_obj:
                return True, None
            email_confirmed = bool(
                getattr(user_obj, "email_confirmed_at", None)
                or getattr(user_obj, "confirmed_at", None)
            )
            return True, {
                "id": str(user_obj.id),
                "email": str(getattr(user_obj, "email", "") or ""),
                "email_confirmed": email_confirmed,
            }
        except Exception:
            return False, None

    cacheable, user_info = _AUTH_USER_SF.do(token_hash, _load)
    if cacheable:
        _AUTH_USER_CACHE.set(token_hash, user_info, ttl=60.0 if user_info else 10.0)
    return user_info


def _get_user_pro_flag(user_id: str, email: str, email_confirmed: bool = False) -> bool:
    if is_unlimited_chat_user(user_id, email, email_confirmed=email_confirmed):
        return True
    if not is_payments_enabled():
        return True

    found, cached = _VIEWER_PLAN_CACHE.get(user_id)
    if found:
        return bool(cached)

    def _load() -> Tuple[bool, bool]:
        sb = get_primary_supabase()
        if sb is None:
            return False, False
        try:
            res = (
                sb.table("subscriptions")
                .select("plan_id,status,current_period_end")
                .eq("user_id", user_id)
                .in_("status", ["active", "trialing"])
                .order("current_period_end", desc=True)
                .limit(5)
                .execute()
            )
            return True, has_active_pro_subscription(getattr(res, "data", None) or [])
        except Exception:
            return False, False

    cacheable, pro = _VIEWER_PLAN_SF.do(user_id, _load)
    if cacheable:
        _VIEWER_PLAN_CACHE.set(user_id, pro, ttl=45.0)
    return pro


def resolve_verified_viewer(request: Request) -> Dict[str, Any]:
    """Authenticate caller from Bearer JWT or @supabase/ssr cookies and resolve Pro status."""
    token = extract_jwt_token(request)
    if not token:
        return {"authenticated": False, "pro": False, "user_id": None, "email": "", "email_confirmed": False}

    user_info = _verify_token_cached(token)
    if not user_info or not user_info.get("id"):
        return {"authenticated": False, "pro": False, "user_id": None, "email": "", "email_confirmed": False}

    uid = user_info["id"]
    email = user_info.get("email", "")
    email_confirmed = bool(user_info.get("email_confirmed", False))
    pro = _get_user_pro_flag(uid, email, email_confirmed=email_confirmed)
    return {"authenticated": True, "pro": pro, "user_id": uid, "email": email, "email_confirmed": email_confirmed}
