"""Comprehensive offline unit & contract tests for offload_public, offload_user, sharia_stocks, and cache invalidation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api import cache_invalidation, perf_utils, sharia_stocks
from api.routers import offload_public, offload_user


class _FakeQuery:
    def __init__(self, table_name: str, db: "_FakeSupabase"):
        self.table_name = table_name
        self.db = db
        self.filters = []
        self.orders = []
        self.limit_n = None
        self.range_bounds = None
        self.op = "select"
        self.payload = None
        self.is_single = False

    def select(self, cols="*", *_args, **_kwargs):
        if self.op != "select":
            raise AttributeError(f"PostgREST builder does not support .select() after .{self.op}()")
        self.cols = cols
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self.filters.append(("neq", col, val))
        return self

    def ilike(self, col, val):
        self.filters.append(("ilike", col, val))
        return self

    def in_(self, col, vals):
        self.filters.append(("in", col, set(vals)))
        return self

    def contains(self, col, val):
        self.filters.append(("contains", col, val))
        return self

    def gte(self, col, val):
        self.filters.append(("gte", col, val))
        return self

    def lte(self, col, val):
        self.filters.append(("lte", col, val))
        return self

    def lt(self, col, val):
        self.filters.append(("lt", col, val))
        return self

    def gt(self, col, val):
        self.filters.append(("gt", col, val))
        return self

    def or_(self, expr):
        self.filters.append(("or", expr))
        return self

    @property
    def not_(self):
        return self

    def is_(self, col, val):
        self.filters.append(("not_is", col, val))
        return self

    def order(self, col, desc=False, **_kwargs):
        self.orders.append((col, desc))
        return self

    def range(self, start, end):
        self.range_bounds = (start, end)
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def single(self):
        if self.op != "select":
            raise AttributeError(f"PostgREST builder does not support .single() after .{self.op}()")
        self.is_single = True
        return self

    def maybe_single(self):
        if self.op != "select":
            raise AttributeError(f"PostgREST builder does not support .maybe_single() after .{self.op}()")
        self.is_single = "maybe"
        return self

    def insert(self, payload):
        self.op = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = payload
        return self

    def upsert(self, payload, **_kwargs):
        self.op = "upsert"
        self.payload = payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def _matches(self, row: dict) -> bool:
        for f in self.filters:
            kind = f[0]
            if kind == "eq":
                _, col, val = f
                if "->>" in col:
                    parent, key = col.split("->>", 1)
                    actual = (row.get(parent) or {}).get(key)
                    actual_str = str(actual).lower() if isinstance(actual, bool) else str(actual)
                    if actual_str != str(val):
                        return False
                elif row.get(col) != val:
                    return False
            elif kind == "neq":
                if row.get(f[1]) == f[2]:
                    return False
            elif kind == "in":
                if row.get(f[1]) not in f[2]:
                    return False
            elif kind == "gte":
                if row.get(f[1]) is None or str(row.get(f[1])) < str(f[2]):
                    return False
            elif kind == "lte":
                if row.get(f[1]) is None or str(row.get(f[1])) > str(f[2]):
                    return False
            elif kind == "lt":
                if row.get(f[1]) is None or str(row.get(f[1])) >= str(f[2]):
                    return False
            elif kind == "gt":
                if row.get(f[1]) is None or str(row.get(f[1])) <= str(f[2]):
                    return False
            elif kind == "ilike":
                pat = str(f[2]).replace("%", "").lower()
                if pat not in str(row.get(f[1]) or "").lower():
                    return False
            elif kind == "not_is":
                if f[2] == "null" and row.get(f[1]) is None:
                    return False
        return True

    def execute(self):
        self.db.calls.append((self.op, self.table_name, list(self.filters), self.limit_n))
        rows = self.db.tables.setdefault(self.table_name, [])

        if self.op == "insert":
            if isinstance(self.payload, list):
                items = [{"id": f"new-{len(rows) + idx + 1}", **dict(r)} for idx, r in enumerate(self.payload)]
                rows.extend(items)
                return SimpleNamespace(data=items)
            item = {"id": f"new-{len(rows) + 1}", **dict(self.payload)}
            rows.append(item)
            return SimpleNamespace(data=[item])

        if self.op == "update":
            updated = []
            for row in rows:
                if self._matches(row):
                    row.update(self.payload)
                    updated.append(dict(row))
            return SimpleNamespace(data=updated)

        if self.op == "upsert":
            item = dict(self.payload)
            rows.append(item)
            return SimpleNamespace(data=[item])

        if self.op == "delete":
            kept = [r for r in rows if not self._matches(r)]
            self.db.tables[self.table_name] = kept
            return SimpleNamespace(data=[])

        matched = [dict(r) for r in rows if self._matches(r)]
        for col, desc in reversed(self.orders):
            matched.sort(key=lambda r: str(r.get(col) or ""), reverse=bool(desc))
        if self.range_bounds is not None:
            s, e = self.range_bounds
            matched = matched[s : e + 1]
        elif self.limit_n is not None:
            matched = matched[: self.limit_n]
        if self.is_single == "maybe":
            if not matched:
                raise RuntimeError("Missing response 204")
            return SimpleNamespace(data=matched[0])
        if self.is_single:
            if not matched:
                raise RuntimeError("JSON object requested, multiple (or no) rows returned")
            return SimpleNamespace(data=matched[0])
        return SimpleNamespace(data=matched)


class _FakeStorageBucket:
    def upload(self, *_args, **_kwargs):
        return {"ok": True}

    def get_public_url(self, file_path: str):
        return f"https://cdn.example.com/chat-images/{file_path}"


class _FakeStorage:
    def from_(self, _bucket: str):
        return _FakeStorageBucket()


class _FakeSupabase:
    def __init__(self, tables=None, rpc_handlers=None):
        self.tables = {k: list(v) for k, v in (tables or {}).items()}
        self.rpc_handlers = rpc_handlers or {}
        self.calls = []
        self.storage = _FakeStorage()

    def table(self, name: str):
        return _FakeQuery(name, self)

    def rpc(self, fn_name: str, params=None):
        handler = self.rpc_handlers.get(fn_name)
        res = handler(params or {}) if callable(handler) else None
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=res))


@pytest.fixture(autouse=True)
def _reset_caches():
    offload_public.invalidate_public_offload_caches(["market", "recommendations", "symbols", "news"])
    offload_user.invalidate_user_router_public_caches(["market", "recommendations", "symbols"])
    offload_user._PUBLIC_PAYMENT_CFG_CACHE.clear()
    offload_user._FOUNDERS_STATUS_CACHE.clear()
    offload_user._BACKTESTS_SOFT_CACHE.clear()
    offload_user._MODEL_CARDS_CACHE.clear()
    offload_user._SHARED_CHAT_CACHE.clear()
    offload_user._ORDER_STATUS_CACHE.clear()
    yield


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(offload_public.router)
    app.include_router(offload_user.router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Sharia Stocks Tests
# ---------------------------------------------------------------------------
def test_sharia_compliance_egx_and_tasi():
    assert sharia_stocks.is_sharia_compliant("ABUK") is True
    assert sharia_stocks.is_sharia_compliant("COMI") is False
    assert sharia_stocks.is_sharia_compliant("1120") is True
    assert sharia_stocks.is_sharia_compliant("2222.SR") is True
    assert sharia_stocks.is_sharia_compliant("9999", market="tasi") is False
    assert sharia_stocks.get_sharia_compliant_count("egx") == len(sharia_stocks.SHARIA_COMPLIANT_EGX_SYMBOLS)
    assert sharia_stocks.get_sharia_compliant_count("tasi") == len(sharia_stocks.SHARIA_COMPLIANT_TASI_SYMBOLS)


# ---------------------------------------------------------------------------
# Public Offload Router Tests
# ---------------------------------------------------------------------------
def test_public_stock_directory_and_page_data():
    db = _FakeSupabase(
        tables={
            "stock_fundamentals": [
                {
                    "symbol": "ABUK",
                    "exchange": "EGX",
                    "updated_at": "2026-11-15T12:00:00Z",
                    "data": {"name": "Abu Qir", "sector": "Chemicals", "peRatio": 6.5, "pbRatio": 1.8, "eps": 8.2, "marketCap": 75000000000},
                },
                {
                    "symbol": "SKPC",
                    "exchange": "EGX",
                    "updated_at": "2026-11-15T12:00:00Z",
                    "data": {"name": "Sidi Kerir", "sector": "Chemicals", "peRatio": 7.1, "pbRatio": 2.0, "eps": 3.2},
                },
            ],
            "stock_prices": [
                {"symbol": "ABUK", "exchange": "EGX", "date": "2026-11-15", "open": 52, "high": 55, "low": 51.5, "close": 54.0, "volume": 1200000, "updated_at": "2026-11-15T14:30:00Z"},
                {"symbol": "ABUK", "exchange": "EGX", "date": "2026-11-14", "open": 51, "high": 53, "low": 50.5, "close": 52.0, "volume": 900000, "updated_at": "2026-11-14T14:30:00Z"},
            ],
            "stock_technical_indicators": [
                {"symbol": "ABUK", "exchange": "EGX", "date": "2026-11-15", "close": 54.0, "change_pct": 3.85, "adx_14": 28, "rsi_14": 58, "macd": 1.2, "macd_signal": 0.9, "ema_50": 50, "ema_200": 46, "sma_50": 49, "sma_200": 45, "calculated_at": "2026-11-15T15:00:00Z"},
                {"symbol": "SKPC", "exchange": "EGX", "date": "2026-11-15", "close": 24.0, "change_pct": 1.2, "rsi_14": 52, "ema_50": 22, "ema_200": 21, "sma_200": 20, "vwap_20": 23.5, "volume": 500000},
            ],
            "scan_results": [
                {"symbol": "ABUK", "exchange": "EGX", "created_at": "2026-11-15T15:10:00Z", "precision": 0.84, "signal": "BUY", "top_reasons": ["Strong volume"]},
            ],
            "stocks": [{"symbol": "ABUK", "name": "Abu Qir", "name_ar": "أبو قير للأسمدة", "exchange": "EGX"}],
        }
    )
    client = _build_client()
    with mock.patch("api.routers.offload_public.get_market_supabase", return_value=db), mock.patch(
        "api.routers.offload_public.get_primary_supabase", return_value=db
    ):
        dir_res = client.get("/api/public/stock-directory?market=egx")
        assert dir_res.status_code == 200
        dir_body = dir_res.json()
        assert len(dir_body["stocks"]) == 2
        assert dir_body["stocks"][0]["symbol"] == "ABUK"

        page_res = client.get("/api/public/stock-page-data?symbol=ABUK&market=egx")
        assert page_res.status_code == 200
        page_body = page_res.json()
        assert page_body["snapshot"]["latestPrice"]["close"] == 54.0
        assert [p["date"] for p in page_body["snapshot"]["historicalPrices"]] == ["2026-11-14", "2026-11-15"]
        assert page_body["related"]["stocks"][0]["symbol"] == "SKPC"

        bad_res = client.get("/api/public/stock-page-data?symbol=BAD$$$")
        assert bad_res.status_code == 400

        fv_res = client.get("/api/public/fair-value-report?market=egx")
        assert fv_res.status_code == 200
        fv_body = fv_res.json()
        assert fv_body["summary"]["totalEvaluated"] >= 1
        assert any(s["symbol"] == "ABUK" and s["fairValue"] > 0 for s in fv_body["stocks"])

        tech_res = client.post("/api/scan/technical", json={"limit": 10})
        assert tech_res.status_code == 200
        assert tech_res.json()["scanned_count"] >= 1
        assert len(tech_res.json()["results"]) >= 1

        breadth_res = client.get("/api/market/breadth")
        assert breadth_res.status_code == 200
        assert breadth_res.json()["advancing"] == 2
        assert "avg_rsi" in breadth_res.json()

        from api import main as api_main
        routes = {r.path for r in api_main.app.routes}
        assert "/api/public/stock-page-data" in routes
        assert "/api/portfolio" in routes
        assert "/api/payment/public-config" in routes


def test_public_reports_archive_sitemap_and_invalidation():
    job = {
        "id": "job-1",
        "job_type": "daily_bot",
        "status": "completed",
        "started_at": "2026-11-15T14:00:00Z",
        "steps": [
            {"step": "sync_prices", "status": "success"},
            {"step": "calculate_indicators", "status": "success"},
            {"step": "refresh_market_status", "status": "success"},
        ],
    }
    db = _FakeSupabase(
        tables={
            "daily_social_reports": [
                {
                    "session_date": "2026-11-15",
                    "kind": "market",
                    "status": "ready",
                    "validation": {"ok": True},
                    "content": "تقرير السوق اليومي",
                    "evidence": [{"tool": "get_market", "data": {"egx30": 31000}}],
                    "job_run_id": "job-1",
                    "created_at": "2026-11-15T16:00:00Z",
                    "updated_at": "2026-11-15T16:00:00Z",
                }
            ],
            "daily_job_runs": [job],
            "shared_chat_posts": [{"slug": "comi-analysis", "is_published": True, "updated_at": "2026-11-15T10:00:00Z", "created_at": "2026-11-15T10:00:00Z"}],
            "egx_disclosures": [{"id": "11111111-1111-1111-1111-111111111111", "symbol": "COMI", "company_name": "CIB", "disclosure_type": "board_resolution", "disclosure_date": "2026-11-15", "title": "Board Meeting", "raw_content": "Approved budget", "ai_summary": "Neutral disclosure", "sentiment": "neutral"}],
        }
    )
    client = _build_client()
    with mock.patch("api.routers.offload_public.get_primary_supabase", return_value=db):
        rep = client.get("/api/public/reports-archive")
        assert rep.status_code == 200
        assert len(rep.json()["reports"]) == 1

        smp = client.get("/api/public/sitemap-posts")
        assert smp.status_code == 200
        assert smp.json()["posts"][0]["slug"] == "comi-analysis"

        svg_ok = client.get("/api/disclosures/image/11111111-1111-1111-1111-111111111111")
        assert svg_ok.status_code == 200
        assert svg_ok.headers["content-type"].startswith("image/svg+xml")
        assert b"<svg" in svg_ok.content

        svg_bad = client.get("/api/disclosures/image/../../secret")
        assert svg_bad.status_code in (400, 404)

    cleared = cache_invalidation.invalidate_local_hf_caches(
        ["daily-market-data", "daily-recommendations", "daily-news-data", "daily-public-reports"]
    )
    assert "fair_value" in cleared
    assert "public_stock_page" in cleared
    assert "reports_archive" in cleared
    assert "offload_user_public" in cleared


# ---------------------------------------------------------------------------
# Authenticated User Offload Tests (Zero-Trust & Fail-Closed)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/portfolio", None),
        ("POST", "/api/portfolio", {"action": "add", "symbol": "COMI", "quantity": 100}),
        ("GET", "/api/portfolio/performance", None),
        ("POST", "/api/portfolio/transactions", {"action": "deposit", "amount": 1000, "occurredAt": "2026-11-15T10:00:00Z", "requestId": "11111111-1111-1111-1111-111111111111"}),
        ("POST", "/api/user/portfolio/rebalance", None),
        ("GET", "/api/profile/telegram-pro", None),
        ("GET", "/api/automations", None),
        ("POST", "/api/user/scanner-alerts", {"preferences": {"breakout": False}}),
        ("GET", "/api/chart-workspace", None),
        ("PUT", "/api/chart-workspace", {"workspace": {}}),
        ("GET", "/api/affiliate/me", None),
        ("GET", "/api/b2b/license", None),
        ("POST", "/api/b2b/trial", {}),
        ("GET", "/api/subscription/trial", None),
        ("POST", "/api/support/message", {"session_id": "u1", "content": "hi"}),
        ("GET", "/api/support/messages?session_id=u1", None),
        ("POST", "/api/payment/easykash/create", {"mobile": "01012345678"}),
        ("GET", "/api/payment/easykash/status?order_id=1", None),
        ("POST", "/api/payment/direct-wallet/confirm", {"sender_mobile": "01012345678", "transaction_id": "TX123456"}),
        ("POST", "/api/payment/failed-recovery", None),
    ],
)
def test_authenticated_endpoints_fail_closed_401(method, path, body):
    client = _build_client()
    with mock.patch("api.routers.offload_user.resolve_verified_viewer", return_value={"authenticated": False, "pro": False, "user_id": None, "email": ""}), mock.patch(
        "api.routers.offload_user.extract_jwt_token", return_value=None
    ), mock.patch("api.routers.offload_user.is_payments_enabled", return_value=True):
        if method == "GET":
            res = client.get(path)
        elif method == "POST":
            res = client.post(path, json=body)
        else:
            res = client.put(path, json=body)
        assert res.status_code == 401


def test_ai_signals_and_events_pro_gate():
    db = _FakeSupabase(
        tables={
            "scan_results": [
                {"id": "rec-1", "symbol": "COMI", "name": "CIB", "exchange": "EGX", "country": "Egypt", "status": "open", "is_public": True, "signal": "BUY", "entry_price": 80.0, "target_price": 92.0, "stop_loss": 75.0, "precision": 0.85, "top_reasons": ["Breakout"], "created_at": "2026-11-15T12:00:00Z"},
            ],
            "stock_technical_indicators": [{"symbol": "COMI", "exchange": "EGX", "date": "2026-11-15", "close": 84.0}],
            "recommendation_events": [{"id": 10, "recommendation_id": "rec-1", "event_type": "recommendation_closed", "old_values": {"entry_price": 80}, "new_values": {"exit_price": 92, "profit_loss_pct": 15.0}, "price_at_event": 92.0, "source": "bot", "telegram_status": "sent", "created_at": "2026-11-15T15:00:00Z"}],
        }
    )
    client = _build_client()
    free_viewer = {"authenticated": True, "pro": False, "user_id": "user-free", "email": "free@example.com"}
    pro_viewer = {"authenticated": True, "pro": True, "user_id": "user-pro", "email": "pro@example.com"}

    with mock.patch("api.routers.offload_user.get_market_supabase", return_value=db), mock.patch(
        "api.routers.offload_user.get_primary_supabase", return_value=db
    ), mock.patch("api.routers.offload_user.is_payments_enabled", return_value=True):
        with mock.patch("api.routers.offload_user.resolve_verified_viewer", return_value=free_viewer):
            sig_free = client.get("/api/market/ai-signals?market=egx")
            assert sig_free.status_code == 200
            assert sig_free.json()["gated"] is True
            assert sig_free.json()["signals"] == []
            assert sig_free.json()["total_open"] == 1

            ev_free = client.get("/api/recommendations/events")
            assert ev_free.status_code == 403

        with mock.patch("api.routers.offload_user.resolve_verified_viewer", return_value=pro_viewer):
            sig_pro = client.get("/api/market/ai-signals?market=egx")
            assert sig_pro.status_code == 200
            assert sig_pro.json()["gated"] is False
            assert sig_pro.json()["signals"][0]["pnl_pct"] == pytest.approx(5.0)

            ev_pro = client.get("/api/recommendations/events")
            assert ev_pro.status_code == 200
            assert ev_pro.json()["events"][0]["recommendation_id"] == "rec-1"


def test_portfolio_crud_and_performance():
    db = _FakeSupabase(
        tables={
            "positions": [
                {"id": "pos-1", "user_id": "u1", "symbol": "COMI", "name": "CIB", "quantity": 100, "entry_price": 80.0, "status": "open", "source": "chatbot", "added_at": "2026-11-10T10:00:00Z"},
                {"id": "watch-1", "user_id": "u1", "symbol": "FWRY", "name": "Fawry", "quantity": None, "entry_price": None, "status": "open", "source": "tech_scanner", "added_at": "2026-11-11T10:00:00Z"},
            ],
            "profiles": [{"id": "u1", "cash_balance": 5000.0}],
            "subscriptions": [],
            "stocks": [{"symbol": "COMI", "name": "CIB", "name_ar": "التجاري الدولي"}, {"symbol": "ABUK", "name": "Abu Qir", "name_ar": "أبو قير"}],
            "stock_prices": [
                {"symbol": "COMI", "exchange": "EGX", "date": "2026-11-15", "close": 90.0, "adjusted_close": 90.0},
                {"symbol": "COMI", "exchange": "EGX", "date": "2026-11-14", "close": 85.0, "adjusted_close": 85.0},
                {"symbol": "EGX30", "exchange": "INDX", "date": "2026-11-15", "close": 31000.0, "adjusted_close": None},
                {"symbol": "EGX30", "exchange": "INDX", "date": "2026-11-14", "close": 30000.0, "adjusted_close": None},
            ],
            "market_heatmap": [{"symbol": "COMI", "sector": "Banks"}],
            "position_events": [
                {"id": "ev-1", "user_id": "u1", "position_id": None, "event_at": "2026-11-12T10:00:00Z", "event_type": "portfolio_sell", "payload": {"quantity": 10, "sell_price": 100, "entry_price": 80, "fees": 5}},
            ],
        }
    )
    viewer = {"authenticated": True, "pro": False, "user_id": "u1", "email": "u1@example.com"}
    client = _build_client()
    with mock.patch("api.routers.offload_user.resolve_verified_viewer", return_value=viewer), mock.patch(
        "api.routers.offload_user.get_primary_supabase", return_value=db
    ), mock.patch("api.routers.offload_user.is_payments_enabled", return_value=True):
        res_get = client.get("/api/portfolio")
        assert res_get.status_code == 200
        snap = res_get.json()
        assert snap["totals"]["positions_count"] == 1  # watch_positions excluded!
        assert snap["totals"]["market_value"] == 9000.0
        assert snap["totals"]["profit_value"] == 1000.0
        assert len(snap["watch_positions"]) == 1

        res_add = client.post("/api/portfolio", json={"action": "add", "symbol": "ABUK", "quantity": 50, "price": 60})
        assert res_add.status_code == 200
        assert res_add.json()["ok"] is True

        res_perf = client.get("/api/portfolio/performance")
        assert res_perf.status_code == 200
        perf = res_perf.json()
        assert perf["realized"] == pytest.approx(195.0)
        assert perf["knownSales"] == 1
        assert perf["daily"]["date"] == "2026-11-15"


def test_portfolio_transaction_jwt_forwarding_and_validation():
    viewer = {"authenticated": True, "pro": False, "user_id": "u1", "email": "u1@example.com"}
    client = _build_client()
    with mock.patch("api.routers.offload_user.resolve_verified_viewer", return_value=viewer), mock.patch(
        "api.routers.offload_user.extract_jwt_token", return_value="user-jwt-token"
    ), mock.patch.dict("os.environ", {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": "anon-key"}):
        bad = client.post("/api/portfolio/transactions", json={"action": "buy", "symbol": "ABUK", "quantity": -1, "price": 50, "occurredAt": "2026-11-15T10:00:00Z", "requestId": "11111111-1111-1111-1111-111111111111"})
        assert bad.status_code == 400

        with mock.patch("api.routers.offload_user.requests.post") as m_post:
            m_post.return_value = SimpleNamespace(ok=True, json=lambda: {"ok": True})
            ok = client.post(
                "/api/portfolio/transactions",
                json={"action": "buy", "symbol": "ABUK", "quantity": 10, "price": 50, "occurredAt": "2026-11-15T10:00:00Z", "requestId": "11111111-1111-1111-1111-111111111111"},
            )
            assert ok.status_code == 200
            assert m_post.call_args.kwargs["headers"]["Authorization"] == "Bearer user-jwt-token"


def test_scanner_alerts_15day_lock_and_workspace_validation():
    now_iso = datetime.now(timezone.utc).isoformat()
    today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db = _FakeSupabase(
        tables={
            "profiles": [{"id": "u1", "telegram_chat_id": "12345"}],
            "user_settings": [],
            "bot_states": [
                {
                    "bot_id": "scanner_alerts",
                    "state": {
                        "history": [{"timestamp": now_iso, "stage_results": {"volume_surge": [{"symbol": "COMI", "close": 85.0}], "breakout": [], "rsi_oversold": [], "disclosures": []}}],
                        "active_signals": [{"id": f"COMI_{today_date}_volume_surge", "symbol": "COMI", "scanner_type": "volume_surge", "entry_date": today_date, "entry_price": 85.0, "target_1": 88.8, "status": "active"}],
                        "closed_signals": [],
                    },
                }
            ],
            "chart_workspaces": [],
        }
    )
    free_v = {"authenticated": True, "pro": False, "user_id": "u1", "email": "u1@example.com"}
    pro_v = {"authenticated": True, "pro": True, "user_id": "u1", "email": "u1@example.com"}
    client = _build_client()

    with mock.patch("api.routers.offload_user.get_primary_supabase", return_value=db):
        with mock.patch("api.routers.offload_user.resolve_verified_viewer", return_value=free_v):
            r_free = client.get("/api/user/scanner-alerts")
            assert r_free.status_code == 200
            assert r_free.json()["active_signals"][0]["entry_price"] is None
            assert r_free.json()["active_signals"][0]["is_locked"] is True

            # Chart workspace size + validation
            too_big = client.put("/api/chart-workspace", data=b"x" * 33000)
            assert too_big.status_code == 413
            bad_ws = client.put("/api/chart-workspace", json={"workspace": {"version": 2}})
            assert bad_ws.status_code == 400
            valid_ws = {
                "version": 1,
                "layout": 1,
                "syncTime": True,
                "activePanelId": "p1",
                "panels": [
                    {"id": "p1", "symbol": "COMI", "exchange": "EGX", "timeframe": "1D", "period": 180, "strategyIds": ["smc"]}
                ],
            }
            ok_ws = client.put("/api/chart-workspace", json={"workspace": valid_ws})
            assert ok_ws.status_code == 200

        with mock.patch("api.routers.offload_user.resolve_verified_viewer", return_value=pro_v):
            r_pro = client.get("/api/user/scanner-alerts")
            assert r_pro.status_code == 200
            assert r_pro.json()["active_signals"][0]["entry_price"] == 85.0


def test_backtests_rejects_admin_spoof_and_payments_founders():
    db = _FakeSupabase(
        tables={
            "backtests": [
                {"id": "pub-1", "model_name": "king", "is_public": True, "trades_log": []},
                {"id": "priv-1", "model_name": "king", "is_public": False, "trades_log": []},
            ],
            "subscription_trials": [],
            "local_payment_orders": [],
            "founders_offer_members": [],
            "profiles": [{"id": "u1", "telegram_chat_id": None}],
            "user_activity_events": [],
        },
        rpc_handlers={
            "founders_offer_status": lambda _: {"enabled": True, "is_open": True, "price_egp": 100, "regular_price_egp": 200, "ends_at": "2027-01-01T00:00:00Z"},
        },
    )
    client = _build_client()
    non_admin = {"authenticated": True, "pro": True, "user_id": "u1", "email": "notadmin@example.com"}

    with mock.patch("api.routers.offload_user.get_primary_supabase", return_value=db), mock.patch(
        "api.routers.offload_user.resolve_verified_viewer", return_value=non_admin
    ):
        bt = client.get("/api/backtests?admin=true")
        assert bt.status_code == 200
        assert [row["id"] for row in bt.json()] == ["pub-1"]

        # Disposable email trial rejected & missing telegram rejected
        tr_missing_tg = client.post("/api/subscription/trial", json={})
        assert tr_missing_tg.status_code == 400
        assert tr_missing_tg.json()["error"] == "TELEGRAM_LINK_REQUIRED"

        with mock.patch(
            "api.easykash_payments.payment_config",
            return_value={"enabled": True, "plans": [{"id": "pro", "amount_egp": 200}, {"id": "pro_6m", "amount_egp": 1000}, {"id": "pro_1y", "amount_egp": 1800}]},
        ):
            cfg = client.get("/api/payment/public-config")
            assert cfg.status_code == 200
            plans = {p["id"]: p for p in cfg.json()["plans"]}
            assert plans["pro"]["amount_egp"] == 100
            assert plans["pro_6m"]["amount_egp"] == 500
            assert plans["pro_1y"]["amount_egp"] == 1000

        # Non-admin chat share forbidden
        sh = client.post("/api/chat/share", json={"question": "q", "answer": "a"})
        assert sh.status_code == 403


def test_portfolio_rebalance_quota_and_fair_value():
    db = _FakeSupabase(
        tables={
            "positions": [{"id": "pos-1", "user_id": "u-free", "symbol": "COMI", "quantity": 100, "entry_price": 75.0, "current_price": 80.0, "status": "open"}],
            "profiles": [{"id": "u-free", "cash_balance": 5000.0}],
            "subscriptions": [],
            "ai_chatbot_limits": [{"user_id": "u-free", "date": "2025-01-15", "chat_count": 9}],
            "stock_technical_indicators": [
                {"symbol": "COMI", "exchange": "EGX", "date": "2026-11-16", "close": 80.0, "volume": 100000, "ema_20": 78.0, "ema_50": 76.0, "ema_200": 70.0, "sma_200": 69.0, "vwap_20": 79.0, "change_pct": 1.2, "rsi_14": 55.0, "r_vol": 1.1, "atr_14": 2.0},
                {"symbol": "ABUK", "exchange": "EGX", "date": "2026-11-16", "close": 52.0, "volume": 200000, "ema_20": 50.0, "ema_50": 49.0, "ema_200": 45.0, "sma_200": 44.0, "vwap_20": 51.0, "change_pct": 2.1, "rsi_14": 56.0, "r_vol": 1.2, "atr_14": 1.8},
            ],
            "stock_fundamentals": [
                {"symbol": "ABUK", "exchange": "EGX", "updated_at": "2026-11-16T10:00:00Z", "data": {"name": "Abu Qir", "sector": "Chemicals", "peRatio": 6.0, "pbRatio": 1.5, "eps": 12.0}},
            ],
            "stock_prices": [
                {"symbol": "COMI", "exchange": "EGX", "date": "2026-11-16", "close": 80.0},
                {"symbol": "ABUK", "exchange": "EGX", "date": "2026-11-16", "close": 52.0},
            ],
            "recommendations": [],
        },
        rpc_handlers={
            "consume_ai_chat_quota": lambda p: [{"allowed": True, "remaining": p.get("p_limit", 1)}],
            "consume_chat_bonus": lambda _p: [{"allowed": False}],
        },
    )
    client = _build_client()
    free_v = {"authenticated": True, "pro": False, "user_id": "u-free", "email": "free@example.com", "email_confirmed": True}

    with mock.patch("api.routers.offload_user.get_primary_supabase", return_value=db), mock.patch(
        "api.routers.offload_public.get_market_supabase", return_value=db
    ), mock.patch("api.routers.offload_user.resolve_verified_viewer", return_value=free_v), mock.patch(
        "api.routers.offload_user._get_deepseek_key", return_value=""
    ):
        res_ok = client.post("/api/user/portfolio/rebalance")
        assert res_ok.status_code == 200
        body = res_ok.json()
        assert body["remainingQuota"] == 0
        assert body["holdings"][0]["symbol"] == "COMI"
        assert "healthScore" in body and "aiAdvisory" in body

        # Now lifetime row = 10 -> Free cap hit -> consume_chat_bonus denies -> 429
        db.tables["ai_chatbot_limits"][0]["chat_count"] = 10
        res_cap = client.post("/api/user/portfolio/rebalance")
        assert res_cap.status_code == 429
        assert res_cap.json()["error"] == "LIMIT_REACHED"


def test_automations_crud_and_test_run():
    db = _FakeSupabase(
        tables={
            "profiles": [{"id": "u-pro", "telegram_chat_id": "998877"}],
            "scheduled_chat_automations": [],
        }
    )
    client = _build_client()
    pro_v = {"authenticated": True, "pro": True, "user_id": "u-pro", "email": "pro@example.com"}

    with mock.patch("api.routers.offload_user.get_primary_supabase", return_value=db), mock.patch(
        "api.routers.offload_user.resolve_verified_viewer", return_value=pro_v
    ), mock.patch("api.scheduled_automations_worker.execute_single_automation", return_value={"ok": True, "status": "sent", "chat_id": "998877"}) as m_exec:
        cr = client.post(
            "/api/automations",
            json={"name": "ملخص السوق", "prompt": "اعطني ملخص EGX30", "scheduled_time": "09:30", "days_of_week": "trading_days"},
        )
        assert cr.status_code == 201
        auto_id = cr.json()["automation"]["id"]

        ls = client.get("/api/automations")
        assert ls.status_code == 200
        assert ls.json()["count"] == 1

        up = client.put(f"/api/automations/{auto_id}", json={"name": "ملخص محدث", "is_active": True})
        assert up.status_code == 200
        assert up.json()["automation"]["name"] == "ملخص محدث"

        tr = client.post(f"/api/automations/{auto_id}/test")
        assert tr.status_code == 200
        assert tr.json()["ok"] is True
        m_exec.assert_called_once()
        assert m_exec.call_args.kwargs["is_test"] is True


def test_support_message_affiliate_b2b_and_chat_share_origin():
    db = _FakeSupabase(
        tables={
            "profiles": [{"id": "u1", "whatsapp_number": "01012345678", "telegram_chat_id": "555"}],
            "support_messages": [],
            "affiliates": [],
            "local_payment_orders": [],
            "b2b_group_licenses": [],
            "shared_chat_posts": [],
        }
    )
    client = _build_client()
    user_v = {"authenticated": True, "pro": True, "user_id": "u1", "email": "partner@example.com"}

    with mock.patch("api.routers.offload_user.get_primary_supabase", return_value=db), mock.patch(
        "api.routers.offload_user.resolve_verified_viewer", return_value=user_v
    ), mock.patch("api.routers.offload_user._get_user_meta", return_value={"name": "Partner One"}), mock.patch(
        "api.support_chat.load_admin_chat_id", return_value=123456
    ), mock.patch("api.support_chat.get_token", return_value="bot-tok"), mock.patch(
        "api.routers.offload_user.requests.post", return_value=SimpleNamespace(ok=True, json=lambda: {"ok": True})
    ) as m_tg:
        sup = client.post("/api/support/message", json={"session_id": "u1", "content": "محتاج مساعدة"})
        assert sup.status_code == 200
        assert sup.json()["ok"] is True
        assert sup.json()["message"]["content"] == "محتاج مساعدة"
        assert m_tg.called

        # Affiliate auto-create on empty affiliates table (no 204 crash, no .select after .insert)
        aff_get = client.get("/api/affiliate/me")
        assert aff_get.status_code == 200
        assert aff_get.json()["affiliate"]["user_id"] == "u1"

        aff_post = client.post("/api/affiliate/me", json={"phone": "01099998888", "code": "PARTNER1"})
        assert aff_post.status_code == 200
        assert aff_post.json()["affiliate"]["code"] == "PARTNER1"

        # B2B trial + unlink + update without .select().single()
        b2b_tr = client.post("/api/b2b/trial", json={"tier": "b2b_pro"})
        assert b2b_tr.status_code == 200
        lic_id = b2b_tr.json()["license"]["id"]
        b2b_un = client.post("/api/b2b/license", json={"action": "unlink", "license_id": lic_id})
        assert b2b_un.status_code == 200
        assert b2b_un.json()["license"]["telegram_chat_id"] is None

    # Admin chat share resolves public host behind reverse proxy
    admin_v = {"authenticated": True, "pro": True, "user_id": "admin-1", "email": "admin@egxbots.com"}
    with mock.patch("api.routers.offload_user.get_primary_supabase", return_value=db), mock.patch(
        "api.routers.offload_user.resolve_verified_viewer", return_value=admin_v
    ), mock.patch("api.routers.offload_user.is_chat_admin_email", return_value=True):
        sh_res = client.post(
            "/api/chat/share",
            headers={"x-forwarded-host": "egxbots.com", "x-forwarded-proto": "https"},
            json={"question": "ما هو تحليل COMI؟", "answer": "السهم في اتجاه صاعد.", "title": "تحليل التجاري"},
        )
        assert sh_res.status_code == 201
        assert sh_res.json()["url"].startswith("https://egxbots.com/blogs/chat/")
        slug = sh_res.json()["slug"]
        sh_get = client.get(f"/api/chat/share/{slug}")
        assert sh_get.status_code == 200
        assert sh_get.json()["slug"] == slug


def test_public_market_cookie_vs_param_cache_headers():
    db = _FakeSupabase(
        tables={
            "stock_fundamentals": [{"symbol": "ABUK", "exchange": "EGX", "updated_at": "2026-11-16T10:00:00Z", "data": {"name": "Abu Qir", "peRatio": 6.0, "pbRatio": 1.6, "eps": 10.0}}],
            "stock_prices": [{"symbol": "ABUK", "exchange": "EGX", "date": "2026-11-16", "close": 50.0, "volume": 100000}],
            "stock_technical_indicators": [{"symbol": "ABUK", "exchange": "EGX", "date": "2026-11-16", "close": 50.0, "rsi_14": 55.0, "ema_50": 48.0, "sma_200": 45.0, "volume": 100000, "r_vol": 1.1, "change_pct": 1.5}],
            "recommendations": [],
            "scan_results": [],
            "daily_news_sentiment": [{"id": 1, "symbol": "ABUK", "exchange": "EGX", "date": "2026-11-16", "sentiment_score": 0.4, "news_count": 2, "headlines": [{"title": "Positive results"}], "sources": ["Mubasher"]}],
            "stocks": [{"symbol": "ABUK", "exchange": "EGX", "sector": "Chemicals", "sector_ar": "كيماويات"}],
        }
    )
    client = _build_client()
    with mock.patch("api.routers.offload_public.get_market_supabase", return_value=db), mock.patch(
        "api.routers.offload_public.get_primary_supabase", return_value=db
    ):
        fv_cookie = client.get("/api/public/fair-value-report", headers={"cookie": "egxbots_market=tasi"})
        assert fv_cookie.status_code == 200
        assert "private" in (fv_cookie.headers.get("cache-control") or "").lower()

        fv_param = client.get("/api/public/fair-value-report?market=egx")
        assert fv_param.status_code == 200
        assert "public" in (fv_param.headers.get("cache-control") or "").lower()

        news_cookie = client.get("/api/scan/news", headers={"cookie": "egxbots_market=egx"})
        assert news_cookie.status_code == 200
        assert "private" in (news_cookie.headers.get("cache-control") or "").lower()

        news_param = client.get("/api/scan/news?market=egx")
        assert news_param.status_code == 200
        assert "public" in (news_param.headers.get("cache-control") or "").lower()

        stats_cookie = client.get("/api/scan/news/stats", headers={"cookie": "egxbots_market=egx"})
        assert stats_cookie.status_code == 200
        assert "private" in (stats_cookie.headers.get("cache-control") or "").lower()

        tech_post = client.post("/api/scan/technical?market=egx", json={"limit": 10})
        assert tech_post.status_code == 200
        assert "private" in (tech_post.headers.get("cache-control") or "").lower()
