"""Unit & contract tests for HF offload routes, perf_utils algorithms, and zero-trust auth."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import sys
import threading
import time
from types import SimpleNamespace
from unittest import mock
import urllib.error
import urllib.request

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api import perf_utils
from api.routers import offload, short_swings


class _FakeQuery:
    def __init__(self, table_name: str, db: "_FakeSupabase"):
        self.table_name = table_name
        self.db = db
        self.filters = []
        self.limit_n = None
        self.range_bounds = None
        self.insert_payload = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def ilike(self, col, val):
        self.filters.append(("ilike", col, val))
        return self

    def in_(self, col, vals):
        self.filters.append(("in", col, set(vals)))
        return self

    def gte(self, col, val):
        self.filters.append(("gte", col, val))
        return self

    def or_(self, expr):
        self.filters.append(("or", expr))
        return self

    def range(self, start, end):
        self.range_bounds = (start, end)
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    @property
    def not_(self):
        return self

    def is_(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def execute(self):
        self.db.calls.append((self.table_name, list(self.filters), self.limit_n))
        if self.insert_payload is not None:
            self.db.inserts.append((self.table_name, self.insert_payload))
            return SimpleNamespace(data=[self.insert_payload], count=1)

        rows = list(self.db.tables.get(self.table_name, []))
        for filt in self.filters:
            kind = filt[0]
            if kind == "eq":
                _, col, val = filt
                rows = [r for r in rows if r.get(col) == val]
            elif kind == "ilike":
                _, col, val = filt
                rows = [r for r in rows if str(r.get(col) or "").lower() == str(val or "").lower()]
            elif kind == "in":
                _, col, val = filt
                rows = [r for r in rows if r.get(col) in val]
            elif kind == "gte":
                _, col, val = filt
                rows = [r for r in rows if str(r.get(col) or "") >= str(val)]
            elif kind == "or":
                expr = filt[1]
                terms = [t.strip() for t in expr.split(",") if "." in t]
                matched = []
                for r in rows:
                    ok = False
                    for t in terms:
                        parts = t.split(".", 2)
                        if len(parts) == 3:
                            col, op, raw_v = parts
                            cell = str(r.get(col) or "")
                            if op == "eq" and cell == raw_v:
                                ok = True
                            elif op == "ilike" and raw_v.strip("%").lower() in cell.lower():
                                ok = True
                    if ok:
                        matched.append(r)
                rows = matched
        total = len(rows)
        if self.range_bounds is not None:
            s, e = self.range_bounds
            rows = rows[s : e + 1]
        if self.limit_n is not None:
            rows = rows[: self.limit_n]
        return SimpleNamespace(data=rows, count=total)


class _FakeAuth:
    def __init__(self, tokens_to_users=None):
        self.tokens_to_users = tokens_to_users or {}
        self.calls = 0

    def get_user(self, token: str):
        self.calls += 1
        user = self.tokens_to_users.get(token)
        return SimpleNamespace(user=user)


class _FakeSupabase:
    def __init__(self, tables=None, tokens_to_users=None, bonus_balance=0):
        self.tables = tables or {}
        self.auth = _FakeAuth(tokens_to_users)
        self.bonus_balance = bonus_balance
        self.calls = []
        self.inserts = []

    def table(self, name: str):
        return _FakeQuery(name, self)

    def rpc(self, _name: str, _params: dict):
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.bonus_balance))


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(offload.router)
    app.include_router(short_swings.router)
    return TestClient(app)


def _reset_all_caches():
    perf_utils.clear_perf_caches()
    offload.clear_offload_caches()
    short_swings._SAUDI_SWINGS_CACHE.clear()


# ---------------------------------------------------------------------------
# Algorithmic Cache & SingleFlight Tests
# ---------------------------------------------------------------------------

def test_bounded_ttl_cache_lru_and_expiry():
    cache = perf_utils.BoundedTTLCache(max_entries=2, default_ttl=10.0)
    cache.set("a", 1)
    cache.set("b", 2)
    # Touch "a" so "b" becomes least recently used
    assert cache.get("a") == (True, 1)
    cache.set("c", 3)
    assert cache.get("b") == (False, None)
    assert cache.get("a") == (True, 1)
    assert cache.get("c") == (True, 3)

    # Short TTL expires cleanly
    cache.set("ephemeral", 99, ttl=0.02)
    time.sleep(0.05)
    assert cache.get("ephemeral") == (False, None)
    stats = cache.stats()
    assert stats["hits"] >= 3 and stats["misses"] >= 2


def test_singleflight_coalesces_concurrent_calls_and_recovers_after_error():
    sf = perf_utils.SingleFlight()
    counter = {"n": 0}
    lock = threading.Lock()
    barrier = threading.Barrier(6)

    def _work():
        time.sleep(0.03)
        with lock:
            counter["n"] += 1
        return "shared-value"

    def _caller():
        barrier.wait()
        return sf.do("hot-key", _work)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: _caller(), range(6)))

    assert results == ["shared-value"] * 6
    assert counter["n"] == 1

    # Errors do not leave stale inflight keys behind
    try:
        sf.do("err-key", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    except RuntimeError:
        pass
    assert sf.do("err-key", lambda: "recovered") == "recovered"


# ---------------------------------------------------------------------------
# Zero-Trust Auth & Entitlement Verification
# ---------------------------------------------------------------------------

def test_resolve_verified_viewer_caches_token_and_checks_active_subscription():
    _reset_all_caches()
    future = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    user = SimpleNamespace(
        id="user-pro-1",
        email="pro@example.com",
        email_confirmed_at="2026-01-01T00:00:00Z",
    )
    sb = _FakeSupabase(
        tables={
            "subscriptions": [
                {"user_id": "user-other", "plan_id": "pro", "status": "active", "current_period_end": past},
                {"user_id": "user-pro-1", "plan_id": "pro", "status": "active", "current_period_end": future},
            ]
        },
        tokens_to_users={"valid-tok": user},
    )

    class _FakeReq:
        def __init__(self, headers):
            self.headers = headers
            self.cookies = {}
            self.query_params = {}

    with mock.patch("api.perf_utils.get_primary_supabase", return_value=sb), mock.patch(
        "api.perf_utils.is_payments_enabled", return_value=True
    ):
        v1 = perf_utils.resolve_verified_viewer(_FakeReq({"authorization": "Bearer valid-tok"}))
        v2 = perf_utils.resolve_verified_viewer(_FakeReq({"authorization": "Bearer valid-tok"}))
        anon = perf_utils.resolve_verified_viewer(_FakeReq({}))

    assert v1 == {
        "authenticated": True,
        "pro": True,
        "user_id": "user-pro-1",
        "email": "pro@example.com",
        "email_confirmed": True,
    }
    assert v2 == v1
    assert sb.auth.calls == 1  # SHA-256 cached!
    assert anon["authenticated"] is False and anon["pro"] is False

    # Transient auth failure must NOT negative-cache
    _reset_all_caches()
    with mock.patch("api.perf_utils.get_primary_supabase", return_value=None):
        fail_v = perf_utils.resolve_verified_viewer(_FakeReq({"authorization": "Bearer valid-tok"}))
        assert fail_v["authenticated"] is False
    with mock.patch("api.perf_utils.get_primary_supabase", return_value=sb), mock.patch(
        "api.perf_utils.is_payments_enabled", return_value=True
    ):
        ok_after = perf_utils.resolve_verified_viewer(_FakeReq({"authorization": "Bearer valid-tok"}))
        assert ok_after["authenticated"] is True and ok_after["pro"] is True

    # Unconfirmed email in unlimited list must NOT bypass
    assert perf_utils.is_unlimited_chat_user("x", "user@gmail.com", email_confirmed=False) is False
    assert perf_utils.is_unlimited_chat_user("x", "user@gmail.com", email_confirmed=True) is True


# ---------------------------------------------------------------------------
# Offloaded Routes Tests
# ---------------------------------------------------------------------------

def test_symbols_search_and_countries_egx_and_tasi():
    _reset_all_caches()
    egx_sb = _FakeSupabase(
        tables={
            "market_cache": [
                {
                    "cache_key": "all_symbols_by_country",
                    "payload": [
                        {"Symbol": "COMI.CA", "Exchange": "EGX", "Name": "Commercial International Bank", "NameAr": "البنك التجاري الدولي", "Country": "Egypt", "Currency": "EGP"},
                        {"Symbol": "BTCUSD", "Exchange": "BINANCE", "Name": "Bitcoin", "Country": "Crypto", "Currency": "USD"},
                        {"Symbol": "TMGH.CA", "Exchange": "EGX", "Name": "Talaat Moustafa", "NameAr": "طلعت مصطفى", "Country": "Egypt", "Currency": "EGP"},
                    ],
                }
            ],
            "stocks": [{"country": "Egypt"}, {"country": "Saudi Arabia"}],
        }
    )
    tasi_sb = _FakeSupabase(
        tables={
            "market_cache": [
                {
                    "cache_key": "symbols_Saudi Arabia",
                    "payload": [
                        {"Symbol": "2222.SR", "Exchange": "TADAWUL", "Name": "Saudi Aramco", "NameAr": "أرامكو السعودية", "Country": "Saudi Arabia", "Currency": "SAR"}
                    ],
                }
            ]
        }
    )

    client = _make_client()
    with mock.patch("api.routers.offload.get_market_supabase", side_effect=lambda m: tasi_sb if m == "tasi" else egx_sb), mock.patch(
        "api.routers.offload.get_primary_supabase", return_value=egx_sb
    ):
        res_egx = client.get("/api/symbols/search?q=التجاري&market=egx")
        assert res_egx.status_code == 200
        items_egx = res_egx.json()["results"]
        assert len(items_egx) == 1
        assert items_egx[0]["symbol"] == "COMI.CA"
        assert "max-age=30" in res_egx.headers.get("cache-control", "")

        # Crypto removed exchange filtered out
        res_all = client.get("/api/symbols/search?q=&market=egx")
        assert all(i["symbol"] != "BTCUSD" for i in res_all.json()["results"])

        # Auto-routes 4-digit code to Saudi
        res_tasi = client.get("/api/symbols/search?q=2222")
        assert res_tasi.status_code == 200
        assert res_tasi.json()["results"][0]["symbol"] == "2222.SR"

        res_countries = client.get("/api/symbols/countries")
        assert res_countries.status_code == 200
        assert res_countries.json()["countries"] == ["Egypt", "Saudi Arabia"]
        assert res_countries.headers.get("vercel-cache-tag") == "daily-symbols"


def test_chart_markers_validation_and_visibility_gating():
    _reset_all_caches()
    now = datetime.now(timezone.utc)
    fresh_iso = (now - timedelta(days=2)).isoformat()
    old_iso = (now - timedelta(days=20)).isoformat()
    sb = _FakeSupabase(
        tables={
            "scan_results": [
                {
                    "id": "rec-fresh",
                    "symbol": "COMI",
                    "exchange": "EGX",
                    "is_public": True,
                    "created_at": fresh_iso,
                    "updated_at": fresh_iso,
                    "status": "open",
                    "signal": "BUY",
                    "entry_price": 80.0,
                    "last_close": 82.0,
                    "target_price": 95.0,
                    "stop_loss": 74.0,
                },
                {
                    "id": "rec-old-low",
                    "symbol": "COMI",
                    "exchange": "EGX",
                    "is_public": True,
                    "created_at": old_iso,
                    "updated_at": old_iso,
                    "status": "open",
                    "signal": "BUY",
                    "entry_price": 50.0,
                    "last_close": 55.0,
                    "target_price": 65.0,
                    "stop_loss": 46.0,
                },
                {
                    "id": "rec-old-high",
                    "symbol": "COMI",
                    "exchange": "EGX",
                    "is_public": True,
                    "created_at": old_iso,
                    "updated_at": old_iso,
                    "status": "open",
                    "signal": "BUY",
                    "entry_price": 20.0,
                    "last_close": 40.0,  # +100% > 50% threshold
                    "target_price": 45.0,
                    "stop_loss": 18.0,
                },
            ]
        }
    )
    client = _make_client()
    with mock.patch("api.routers.offload.get_market_supabase", return_value=sb):
        bad = client.get("/api/recommendations/chart-markers?symbol=BAD!!&exchange=EGX")
        assert bad.status_code == 400

        pub = client.get("/api/recommendations/chart-markers?symbol=COMI&exchange=EGX&scope=public")
        assert pub.status_code == 200
        pub_ids = [r["id"] for r in pub.json()["recommendations"]]
        assert pub_ids == ["rec-old-low"]
        assert "public" in pub.headers.get("cache-control", "")

        with mock.patch(
            "api.routers.offload.resolve_verified_viewer",
            return_value={"authenticated": True, "pro": True, "user_id": "u1", "email": "a@b.c"},
        ), mock.patch("api.routers.offload.is_payments_enabled", return_value=True):
            pro_resp = client.get("/api/recommendations/chart-markers?symbol=COMI&exchange=EGX")
        assert pro_resp.status_code == 200
        assert len(pro_resp.json()["recommendations"]) == 3
        assert "no-store" in pro_resp.headers.get("cache-control", "")


def test_ai_bot_recommendations_masking_and_pro_unmasking():
    _reset_all_caches()
    now = datetime.now(timezone.utc)
    fresh_iso = (now - timedelta(days=1)).isoformat()
    old_iso = (now - timedelta(days=25)).isoformat()
    sb = _FakeSupabase(
        tables={
            "scan_results": [
                {
                    "id": "r1",
                    "symbol": "COMI",
                    "exchange": "EGX",
                    "name": "CIB",
                    "last_close": 80.0,
                    "precision": 0.91,
                    "signal": "BUY",
                    "status": "open",
                    "entry_price": 80.0,
                    "target_price": 96.0,
                    "stop_loss": 75.0,
                    "is_public": True,
                    "created_at": fresh_iso,
                    "updated_at": fresh_iso,
                    "top_reasons": ["Strong momentum"],
                    "rich_details": {},
                },
                {
                    "id": "r2",
                    "symbol": "TMGH",
                    "exchange": "EGX",
                    "name": "Talaat",
                    "last_close": 50.0,
                    "precision": 0.88,
                    "signal": "BUY",
                    "status": "open",
                    "entry_price": 45.0,
                    "target_price": 60.0,
                    "stop_loss": 40.0,
                    "is_public": True,
                    "created_at": old_iso,
                    "updated_at": old_iso,
                    "top_reasons": ["Breakout"],
                    "rich_details": {},
                },
            ],
            "stock_prices": [
                {"symbol": "COMI", "exchange": "EGX", "date": now.strftime("%Y-%m-%d"), "close": 85.0, "volume": 1000},
                {"symbol": "TMGH", "exchange": "EGX", "date": now.strftime("%Y-%m-%d"), "close": 52.0, "volume": 500},
            ],
            "stock_fundamentals": [
                {"symbol": "COMI", "data": {"sector": "Financials"}},
            ],
        }
    )

    client = _make_client()
    with mock.patch("api.routers.offload.get_market_supabase", return_value=sb), mock.patch(
        "api.routers.offload.is_payments_enabled", return_value=True
    ):
        # 1. Anonymous visitor: all open trades locked (fresh & old)
        with mock.patch(
            "api.routers.offload.resolve_verified_viewer",
            return_value={"authenticated": False, "pro": False, "user_id": None, "email": ""},
        ):
            anon_resp = client.get("/api/ai_bot/recommendations?market=egx")
        assert anon_resp.status_code == 200
        anon_rows = anon_resp.json()
        assert anon_rows[0]["locked"] is True and "symbol" not in anon_rows[0]
        assert anon_rows[1]["locked"] is True and "symbol" not in anon_rows[1]

        # 2. Signed-in Free user: fresh open locked, old (>=15d) open unlocked with live close
        with mock.patch(
            "api.routers.offload.resolve_verified_viewer",
            return_value={"authenticated": True, "pro": False, "user_id": "free-1", "email": "f@x.y"},
        ):
            free_resp = client.get("/api/ai_bot/recommendations?market=egx")
        assert free_resp.status_code == 200
        free_rows = free_resp.json()
        assert free_rows[0]["locked"] is True and "symbol" not in free_rows[0]
        assert free_rows[1]["symbol"] == "TMGH"
        assert free_rows[1]["last_close"] == 52.0

        # 3. Signed-in Pro user: all unlocked including fresh COMI + sector
        with mock.patch(
            "api.routers.offload.resolve_verified_viewer",
            return_value={"authenticated": True, "pro": True, "user_id": "pro-1", "email": "p@x.y"},
        ):
            pro_resp = client.get("/api/ai_bot/recommendations?market=egx")
        assert pro_resp.status_code == 200
        pro_rows = pro_resp.json()
        assert "locked" not in pro_rows[0]
        assert pro_rows[0]["symbol"] == "COMI"
        assert pro_rows[0]["sector"] == "Financials"
        assert pro_rows[0]["last_close"] == 85.0
        assert "no-store" in pro_resp.headers.get("cache-control", "")


def test_ai_bot_candles_400_410_egx_and_tasi_all_limit():
    _reset_all_caches()
    tasi_sb = _FakeSupabase(
        tables={
            "stock_prices": [
                {"symbol": "2222", "exchange": "TADAWUL", "date": "2026-11-12", "open": 28.0, "high": 29.0, "low": 27.5, "close": 28.8, "volume": 10000}
            ],
            "bot_trades": [
                {"bot_id": "primary", "symbol": "2222", "timestamp": "2026-11-12T10:00:00Z", "action": "BUY", "price": 28.1, "pnl": None}
            ],
        }
    )
    client = _make_client()

    assert client.get("/api/ai_bot/candles?symbol=").status_code == 400
    assert client.get("/api/ai_bot/candles?symbol=BTCUSDT&exchange=BINANCE").status_code == 410

    captured = {}

    def _fake_bot_candles(symbol, bot_id="primary", limit=150, exchange=None):
        captured["limit"] = limit
        captured["symbol"] = symbol
        return {"candles": [{"time": 1700000000, "close": 80}], "markers": [{"time": 1700000000}]}

    fake_bot_mod = SimpleNamespace(get_candles=_fake_bot_candles)
    with mock.patch.dict(sys.modules, {"api.routers.bot": fake_bot_mod}):
        egx_all = client.get("/api/ai_bot/candles?symbol=COMI.CA&all=true&include_markers=false")
    assert egx_all.status_code == 200
    assert captured["limit"] == 5000
    assert egx_all.json()["markers"] == []

    with mock.patch("api.routers.offload.get_market_supabase", return_value=tasi_sb):
        tasi_res = client.get("/api/ai_bot/candles?symbol=2222.SR&limit=50")
    assert tasi_res.status_code == 200
    body = tasi_res.json()
    assert body["currency"] == "SAR"
    assert len(body["candles"]) == 1 and len(body["markers"]) == 1


def test_user_quota_401_parallel_pro_and_cache():
    _reset_all_caches()
    future = (datetime.now(timezone.utc) + timedelta(days=15)).isoformat()
    today_cairo = perf_utils.get_cairo_date_str()
    sb = _FakeSupabase(
        tables={
            "subscriptions": [
                {"id": "s1", "user_id": "u-123", "plan_id": "pro", "status": "active", "current_period_start": f"{today_cairo[:7]}-01", "current_period_end": future, "created_at": "2025-01-01T00:00:00Z"},
            ],
            "ai_chatbot_limits": [{"user_id": "u-123", "date": today_cairo, "chat_count": 7}],
            "positions": [{"user_id": "u-123", "status": "open", "symbol": "COMI"}, {"user_id": "u-123", "status": "open", "symbol": "TMGH"}],
            "subscription_trials": [],
            "profiles": [{"id": "u-123", "telegram_chat_id": "99999"}],
            "local_payment_orders": [],
            "founders_offer_members": [],
        },
        bonus_balance=4,
    )
    client = _make_client()

    with mock.patch("api.routers.offload.resolve_verified_viewer", return_value={"authenticated": False, "pro": False, "user_id": None, "email": ""}):
        assert client.get("/api/user/quota").status_code == 401

    with mock.patch("api.routers.offload.resolve_verified_viewer", return_value={"authenticated": True, "pro": True, "user_id": "u-123", "email": "u@x.y"}), mock.patch(
        "api.routers.offload.get_primary_supabase", return_value=sb
    ), mock.patch("api.routers.offload.is_payments_enabled", return_value=True):
        r1 = client.get("/api/user/quota")
        calls_after_first = len(sb.calls)
        r2 = client.get("/api/user/quota")

    assert r1.status_code == 200
    data = r1.json()
    assert data["ok"] is True
    assert data["plan"]["is_pro"] is True
    assert data["plan"]["is_founding_member"] is True
    assert data["plan"]["founding_member_number"] == 1
    assert data["plan"]["telegram_linked"] is True
    assert data["quota"]["chat_messages"]["used"] == 7
    assert data["quota"]["portfolio_stocks"]["used"] == 2
    assert r2.json() == data
    assert len(sb.calls) == calls_after_first  # Cached for 15s!


def test_analytics_events_validation_and_zero_trust_user_id():
    _reset_all_caches()
    sb = _FakeSupabase()
    client = _make_client()

    with mock.patch("api.routers.offload.resolve_verified_viewer", return_value={"authenticated": False, "pro": False, "user_id": None, "email": ""}):
        assert client.post("/api/analytics/events", json={"event_name": "page_view", "path": "/"}).status_code == 401

    with mock.patch("api.routers.offload.resolve_verified_viewer", return_value={"authenticated": True, "pro": False, "user_id": "real-user", "email": ""}), mock.patch(
        "api.routers.offload.get_primary_supabase", return_value=sb
    ):
        assert client.post("/api/analytics/events", json={"event_name": "evil_event", "path": "/"}).status_code == 400
        assert client.post("/api/analytics/events", json={"event_name": "page_view", "path": "no-slash"}).status_code == 400

        ok = client.post(
            "/api/analytics/events",
            json={
                "user_id": "spoofed-user",
                "event_name": "feature_use",
                "path": "/scanner/technical",
                "metadata": {"tab": "rsi", "bad key!": "drop", "nan_val": float("nan")},
            },
        )
    assert ok.status_code == 200 and ok.json() == {"ok": True}
    assert len(sb.inserts) == 1
    inserted = sb.inserts[0][1]
    assert inserted["user_id"] == "real-user"
    assert inserted["metadata"] == {"tab": "rsi"}


def test_scanner_intraday_session_batch_post():
    _reset_all_caches()
    client = _make_client()

    def _fake_intraday(symbol, date, to_date=None, signal_time=None, signal_price=None):
        if symbol == "BAD":
            raise RuntimeError("transient error")
        return {"signal": {"max_gain_pct": 4.25}, "session_high": 88.5, "peak_time": "12:15"}

    fake_main = SimpleNamespace(get_scanner_intraday_session=_fake_intraday)
    with mock.patch.dict(sys.modules, {"api.main": fake_main}):
        resp = client.post(
            "/api/scanner/intraday-session",
            json={
                "date": "2026-11-15",
                "items": [{"symbol": "COMI.CA", "signal_price": 85.0}, {"symbol": "BAD"}],
            },
        )
    assert resp.status_code == 200
    assert resp.json()["gains"] == {
        "COMI": {"max_gain_pct": 4.25, "peak_price": 88.5, "peak_time": "12:15", "session_high": 88.5}
    }


def test_short_swings_zero_trust_cookie_pro_unlock_and_saudi_cache():
    _reset_all_caches()
    fresh_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    saudi_payload = {
        "status": "ok",
        "kpis": {"win_rate": 72},
        "active_trades": [
            {"symbol": "2222", "entry_date": fresh_date, "entry_price": 28.0, "is_pending_entry": False}
        ],
        "closed_trades": [],
        "market": "TASI",
        "currency": "SAR",
    }
    tasi_sb = _FakeSupabase(
        tables={
            "market_cache": [
                {"cache_key": "saudi_short_swings_v1", "country": "Saudi Arabia", "payload": saudi_payload}
            ]
        }
    )
    client = _make_client()

    with mock.patch("api.routers.short_swings.get_market_supabase", return_value=tasi_sb):
        # Unauthenticated spoof attempt (?is_pro=true) must still be masked and never public-CDN cached!
        with mock.patch(
            "api.routers.short_swings.resolve_verified_viewer",
            return_value={"authenticated": False, "pro": False, "user_id": None, "email": ""},
        ):
            free_resp = client.get("/api/short-swings?is_pro=true", headers={"x-egxbots-market": "tasi"})
        assert free_resp.status_code == 200
        assert free_resp.json()["is_pro"] is False
        assert free_resp.json()["active_trades"][0]["symbol"] == "22**"
        assert free_resp.json()["active_trades"][0]["is_locked"] is True
        assert "no-store" in free_resp.headers.get("cache-control", "")
        assert free_resp.headers.get("vercel-cdn-cache-control") == "private, no-store"

        # Verified Pro session via cookie/JWT (with egxbots_market cookie) unlocks without hitting market_cache again!
        calls_before = len(tasi_sb.calls)
        with mock.patch(
            "api.routers.short_swings.resolve_verified_viewer",
            return_value={"authenticated": True, "pro": True, "user_id": "pro-u", "email": "p@x.y"},
        ):
            pro_resp = client.get("/api/short-swings", headers={"cookie": "egxbots_market=tasi"})
        assert pro_resp.status_code == 200
        assert pro_resp.json()["is_pro"] is True
        assert pro_resp.json()["active_trades"][0]["symbol"] == "2222"
        assert "no-store" in pro_resp.headers.get("cache-control", "")
        assert len(tasi_sb.calls) == calls_before


def test_quota_lifetime_and_payments_disabled_and_malformed_candle_pnl():
    _reset_all_caches()
    from api import plan_limits as pl

    assert pl.plan_limits("lifetime") == pl.pro_limits()
    assert pl.plan_limits("pro_6m") == pl.pro_limits()
    assert pl.plan_limits("lifetime")["chat_messages_per_month"] > pl.free_limits()["chat_messages_per_month"]

    today_cairo = perf_utils.get_cairo_date_str()
    sb_lifetime = _FakeSupabase(
        tables={
            "subscriptions": [
                {"id": "s-life", "user_id": "u-life", "plan_id": "lifetime", "status": "active", "current_period_end": None}
            ],
            "ai_chatbot_limits": [{"user_id": "u-life", "date": today_cairo, "chat_count": 3}],
            "positions": [],
            "subscription_trials": [],
            "profiles": [],
            "local_payment_orders": [],
            "founders_offer_members": [],
        }
    )
    client = _make_client()
    with mock.patch(
        "api.routers.offload.resolve_verified_viewer",
        return_value={"authenticated": True, "pro": True, "user_id": "u-life", "email": "l@x.y", "email_confirmed": True},
    ), mock.patch("api.routers.offload.get_primary_supabase", return_value=sb_lifetime), mock.patch(
        "api.routers.offload.is_payments_enabled", return_value=True
    ), mock.patch("api.plan_limits.is_payments_enabled", return_value=True):
        life_resp = client.get("/api/user/quota")
    assert life_resp.status_code == 200
    life_data = life_resp.json()
    assert life_data["plan"]["id"] == "lifetime"
    assert life_data["plan"]["is_lifetime"] is True
    assert life_data["quota"]["chat_messages"]["limit"] == pl.pro_limits()["chat_messages_per_month"]
    assert life_data["quota"]["portfolio_stocks"]["limit"] == pl.pro_limits()["portfolio_stocks"]
    assert life_data["quota"]["signals"]["delay_days"] == 0

    # When payments disabled, effective_limits yields unlimited and delay_days=0
    _reset_all_caches()
    with mock.patch(
        "api.routers.offload.resolve_verified_viewer",
        return_value={"authenticated": True, "pro": True, "user_id": "u-free", "email": "f@x.y", "email_confirmed": True},
    ), mock.patch("api.routers.offload.get_primary_supabase", return_value=_FakeSupabase()), mock.patch(
        "api.routers.offload.is_payments_enabled", return_value=False
    ), mock.patch("api.plan_limits.is_payments_enabled", return_value=False):
        disabled_resp = client.get("/api/user/quota")
    assert disabled_resp.status_code == 200
    d_data = disabled_resp.json()
    assert d_data["quota"]["chat_messages"]["limit"] >= 10**6
    assert d_data["quota"]["signals"]["delay_days"] == 0

    # Malformed pnl string on TASI candle marker never triggers HTTP 500
    tasi_bad_pnl = _FakeSupabase(
        tables={
            "stock_prices": [{"symbol": "2222", "exchange": "TADAWUL", "date": "2026-11-12", "open": 28, "high": 29, "low": 27, "close": 28.5, "volume": 10}],
            "bot_trades": [{"bot_id": "primary", "symbol": "2222", "timestamp": "2026-11-12T10:00:00Z", "action": "SELL", "price": 28.5, "pnl": ""}],
        }
    )
    with mock.patch("api.routers.offload.get_market_supabase", return_value=tasi_bad_pnl):
        bad_pnl_resp = client.get("/api/ai_bot/candles?symbol=2222.SR&limit=10")
    assert bad_pnl_resp.status_code == 200
    assert bad_pnl_resp.json()["markers"][0]["text"] == "SELL"
    assert "X-Egxbots-Market" in bad_pnl_resp.headers.get("vary", "")


def test_api_main_registers_offload_router():
    src = open("api/main.py", encoding="utf-8").read()
    assert "from api.routers import" in src and "offload" in src
    assert "app.include_router(offload.router)" in src


def test_market_status_proof_fundamentals_counts_and_scan_ai():
    _reset_all_caches()
    egx_sb = _FakeSupabase(
        tables={
            "market_cache": [
                {
                    "cache_key": "market_status_Egypt",
                    "payload": {"egx30": [{"date": "2026-11-12", "close": 31000}], "egx100": [], "usdegp": []},
                },
                {
                    "cache_key": "signal_performance_EGX",
                    "computed_at": "2026-11-12T15:00:00Z",
                    "payload": {"ok": True, "asOf": "2026-11-12", "unusual": {"events": 12}},
                },
            ],
            "stock_prices": [
                {"symbol": "USDEGP", "date": "2026-11-12", "open": 49.0, "high": 49.2, "low": 48.9, "close": 49.1, "volume": 0}
            ],
            "scan_results": [
                {"id": "1", "symbol": "COMI", "exchange": "EGX", "name": "CIB", "last_close": 80, "precision": 0.85, "signal": "BUY", "is_public": True, "status": "win", "created_at": "2026-11-10T10:00:00Z", "top_reasons": ["R1"], "rich_details": {"council_score": 8, "consensus_ratio": 0.9}},
                {"id": "2", "symbol": "TMGH", "exchange": "EGX", "name": "TMG", "last_close": 50, "precision": 0.65, "signal": "BUY", "is_public": True, "status": "loss", "created_at": "2026-11-10T11:00:00Z", "top_reasons": ["R2"], "rich_details": {}},
                {"id": "3", "symbol": "FWRY", "exchange": "EGX", "name": "Fawry", "last_close": 9, "precision": 0.9, "signal": "BUY", "is_public": True, "status": "open", "created_at": "2026-11-11T10:00:00Z", "top_reasons": ["R3"], "rich_details": {"council_score": 9, "consensus_ratio": 0.95}},
            ],
            "stock_fundamentals": [{"symbol": "COMI", "exchange": "EGX", "data": {"pe": 8.4}, "updated_at": "2026-11-12"}],
        }
    )
    tasi_sb = _FakeSupabase(
        tables={
            "market_cache": [],
            "market_index": [
                {"date": "2026-11-11", "exchange": "TADAWUL", "close": 11500, "ret": -0.041, "source": "TADAWUL"},
                {"date": "2026-11-10", "exchange": "TADAWUL", "close": 12000, "ret": 0.005, "source": "TADAWUL"},
            ],
            "scan_results": [
                {"id": "t1", "symbol": "1120", "exchange": "TADAWUL", "name": "Al Rajhi", "last_close": 88, "precision": 0.87, "signal": "BUY", "is_public": True, "status": "open", "top_reasons": ["R1"], "council_score": 8.5, "consensus_ratio": 0.88}
            ],
        }
    )
    client = _make_client()

    with mock.patch("api.routers.offload.get_market_supabase", side_effect=lambda m: tasi_sb if m == "tasi" else egx_sb), mock.patch(
        "api.routers.offload.get_primary_supabase", return_value=egx_sb
    ):
        st_egx = client.get("/api/market/status?market=egx")
        assert st_egx.status_code == 200
        assert st_egx.json()["egx30"][0]["close"] == 31000
        assert st_egx.json()["usdegp"][0]["close"] == 49.1
        assert "public" in st_egx.headers.get("cache-control", "")

        st_tasi = client.get("/api/market/status?market=tasi")
        assert st_tasi.status_code == 200
        assert st_tasi.json()["regime"] == "panic"
        assert st_tasi.json()["reject_buys"] is True

        proof = client.get("/api/market/proof?market=egx")
        assert proof.status_code == 200
        assert proof.json() == {"recommendations": 3, "closed": 2, "win_rate": 50}
        assert "X-Egxbots-Market" in proof.headers.get("vary", "")

        assert client.get("/api/market/fundamentals?ticker=BAD!!").status_code == 400
        fund = client.get("/api/market/fundamentals?ticker=COMI.EGX")
        assert fund.status_code == 200 and fund.json()["data"] == {"pe": 8.4}

        counts = client.get("/api/market/recommendation-counts?from=2026-11-01")
        assert counts.status_code == 200
        assert counts.json()["daily_counts"] == {"2026-11-10": 2, "2026-11-11": 1}

        perf = client.get("/api/scan/signal-performance")
        assert perf.status_code == 200 and perf.json()["ok"] is True

        scan = client.post("/api/scan/ai?limit=10&min_precision=0.8", json={"market": "egx"})
        assert scan.status_code == 200
        assert scan.json()["scanned_count"] == 2
        assert scan.json()["results"][0]["confidence"] == "High"
        assert scan.json()["results"][0]["council_score"] == 8.0

        scan_tasi = client.post("/api/scan/ai?limit=10&min_precision=0.8", json={"market": "tasi"})
        assert scan_tasi.status_code == 200
        assert scan_tasi.json()["scanned_count"] == 1
        assert scan_tasi.json()["results"][0]["council_score"] == 8.5


def test_disclosures_list_and_ssrf_safe_pdf_proxy():
    _reset_all_caches()
    sb = _FakeSupabase(
        tables={
            "egx_disclosures": [
                {
                    "id": "disc-1",
                    "symbol": "COMI",
                    "company_name": "CIB",
                    "disclosure_type": "insider_trading",
                    "disclosure_date": "2026-11-12",
                    "title": "Board buy",
                    "sentiment": "bullish",
                    "action_type": "buy",
                    "source_url": "http://169.254.169.254/secret.pdf",
                },
                {
                    "id": "disc-2",
                    "symbol": "TMGH",
                    "company_name": "TMG",
                    "disclosure_type": "earnings",
                    "disclosure_date": "2026-11-10",
                    "title": "Q3 results",
                    "sentiment": "neutral",
                    "action_type": None,
                    "source_url": "https://static.mubasher.info/File.Mix_Announcement_File/sample.pdf",
                },
            ]
        }
    )
    client = _make_client()

    with mock.patch("api.routers.offload.get_market_supabase", return_value=sb), mock.patch(
        "api.routers.offload.get_primary_supabase", return_value=sb
    ):
        lst = client.get("/api/disclosures?market=egx&sentiment=bullish&sector=banking_finance&search=CIB")
        assert lst.status_code == 200
        assert lst.json()["total"] == 1 and lst.json()["data"][0]["symbol"] == "COMI"
        assert "public" in lst.headers.get("cache-control", "")

        assert client.get("/api/disclosures/pdf/bad$id").status_code == 400

        seen_urls = []

        class _FakePdfResp:
            status = 200
            def read(self, _n=-1): return b"%PDF-1.4 fake"
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def _fake_open_safe_pdf(req, timeout=10.0):
            seen_urls.append(req.full_url)
            return _FakePdfResp()

        with mock.patch("api.routers.offload._open_safe_pdf", side_effect=_fake_open_safe_pdf):
            # Private IP source_url must be rejected by SSRF guard and fall back to safe default!
            pdf1 = client.get("/api/disclosures/pdf/disc-1")
            # Second call hits _PDF_CACHE without re-fetching!
            pdf2 = client.get("/api/disclosures/pdf/disc-1")

        assert pdf1.status_code == 200 and pdf1.content == b"%PDF-1.4 fake"
        assert pdf1.headers.get("content-type") == "application/pdf"
        assert pdf2.content == b"%PDF-1.4 fake"
        assert len(seen_urls) == 1
        assert seen_urls[0].startswith("https://static.mubasher.info/")


def test_qa_hardening_redirect_ssrf_cache_poison_and_or_sanitization():
    _reset_all_caches()
    handler = offload._SafePdfRedirectHandler()
    orig_req = urllib.request.Request("https://static.mubasher.info/File.Mix_Announcement_File/orig.pdf")

    with pytest.raises(urllib.error.URLError):
        handler.redirect_request(orig_req, None, 302, "Found", {}, "http://169.254.169.254/latest/meta-data/")

    with pytest.raises(urllib.error.URLError):
        handler.redirect_request(orig_req, None, 302, "Found", {}, "//evil.internal/secret.pdf")

    allowed_abs = handler.redirect_request(
        orig_req, None, 302, "Found", {}, "https://static.mubasher.info/File.Mix_Announcement_File/next.pdf"
    )
    assert allowed_abs.full_url == "https://static.mubasher.info/File.Mix_Announcement_File/next.pdf"

    allowed_rel = handler.redirect_request(orig_req, None, 302, "Found", {}, "/File.Mix_Announcement_File/rel.pdf")
    assert allowed_rel.full_url == "https://static.mubasher.info/File.Mix_Announcement_File/rel.pdf"

    sb = _FakeSupabase(
        tables={
            "market_index": [
                {"exchange": "TADAWUL", "date": "2026-11-14", "close": 11500.0, "ret": 0.0035, "source": "TADAWUL"}
            ],
            "egx_disclosures": [
                {
                    "id": "d-1",
                    "symbol": "1120",
                    "company_name": "Al Rajhi",
                    "disclosure_type": "earnings",
                    "disclosure_date": "2026-11-14",
                    "title": "Q3",
                    "sentiment": "bullish",
                    "action_type": None,
                    "source_url": "https://static.mubasher.info/sample.pdf",
                }
            ],
        }
    )
    client = _make_client()

    with mock.patch("api.routers.offload.get_market_supabase", return_value=sb), mock.patch(
        "api.routers.offload.get_primary_supabase", return_value=sb
    ):
        # Empty/unrecognized market param + Cookie: egxbots_market=tasi MUST stay private no-store (zero CDN cache poisoning!)
        client.cookies.set("egxbots_market", "tasi")
        for qs in ("market=", "market=unknown", "country=&exchange=invalid"):
            st = client.get(f"/api/market/status?{qs}")
            assert st.status_code == 200
            assert st.json()["market"] == "tasi"
            assert "private" in st.headers.get("cache-control", "")
            assert "no-store" in st.headers.get("vercel-cdn-cache-control", "")

            dl = client.get(f"/api/disclosures?{qs}")
            assert dl.status_code == 200
            assert "private" in dl.headers.get("cache-control", "")
            assert "no-store" in dl.headers.get("vercel-cdn-cache-control", "")
        client.cookies.clear()

        # PostgREST .or_() sanitization MUST strip quotes and backslashes!
        sb.calls.clear()
        inj = client.get('/api/disclosures?market=egx&search=CIB"%2Cinjected%3Dtrue\\')
        assert inj.status_code == 200
        or_clauses = [
            f[1]
            for tbl, filters, _ in sb.calls
            if tbl == "egx_disclosures"
            for f in filters
            if f[0] == "or"
        ]
        assert or_clauses
        assert '"' not in or_clauses[0] and "\\" not in or_clauses[0] and "," in or_clauses[0]
        assert "CIBinjected=true" in or_clauses[0]


