"""Unit tests for the independent Saudi (Tadawul / TASI) daily pipeline & VIP dispatch."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from api import daily_job_scheduler
from api import saudi_price_sync
from api import saudi_telegram_dispatch
from api.saudi_trading_calendar import SAUDI_TZ, is_saudi_session


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table_name: str, tables: dict):
        self.table_name = table_name
        self.tables = tables
        self._filters = []
        self._gte_filters = []
        self._range = None
        self._limit = None
        self._order_desc = False
        self._order_col = None
        self._op = "select"
        self._payload = None

    def select(self, *_args):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def gte(self, col, val):
        self._gte_filters.append((col, val))
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def maybe_single(self):
        self._limit = 1
        self._single = True
        return self

    def upsert(self, payload, **_kwargs):
        self._op = "upsert"
        self._payload = payload
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def execute(self):
        rows = self.tables.setdefault(self.table_name, [])
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            next_id = max([int(r.get("id") or 0) for r in rows] + [0]) + 1
            for item in items:
                copy_item = dict(item)
                if "id" not in copy_item:
                    copy_item["id"] = next_id
                    next_id += 1
                rows.append(copy_item)
            return _FakeResponse(items)
        if self._op == "upsert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            if self.table_name == "market_cache":
                for item in items:
                    rows[:] = [
                        r for r in rows
                        if not (r.get("cache_key") == item.get("cache_key") and r.get("country") == item.get("country"))
                    ]
                    rows.append(dict(item))
            elif self.table_name == "market_index":
                for item in items:
                    rows[:] = [
                        r for r in rows
                        if not (r.get("exchange") == item.get("exchange") and r.get("date") == item.get("date"))
                    ]
                    rows.append(dict(item))
            elif self.table_name == "stock_prices":
                for item in items:
                    rows[:] = [r for r in rows if r.get("id") != item.get("id")]
                    rows.append(dict(item))
            else:
                rows.extend([dict(i) for i in items])
            return _FakeResponse(items)

        matched = [
            r for r in rows
            if all(r.get(c) == v for c, v in self._filters)
            and all(str(r.get(c) or "") >= str(v) for c, v in self._gte_filters)
        ]
        if self._order_col:
            matched.sort(key=lambda r: r.get(self._order_col) or "", reverse=self._order_desc)
        if getattr(self, "_single", False):
            return _FakeResponse(matched[0] if matched else None)
        if self._range is not None:
            matched = matched[self._range[0] : self._range[1] + 1]
        if self._limit is not None:
            matched = matched[: self._limit]
        return _FakeResponse(matched)


class _FakeSaudiSupabase:
    def __init__(self, initial=None):
        self.tables = initial or {}

    def table(self, name: str):
        return _FakeQuery(name, self.tables)


def test_saudi_calendar_weekends_and_holidays(monkeypatch):
    # Sunday 2026-11-15 -> open
    assert is_saudi_session(dt.date(2026, 11, 15)) is True
    # Thursday 2026-11-19 -> open
    assert is_saudi_session(dt.date(2026, 11, 19)) is True
    # Friday 2026-11-20 & Saturday 2026-11-21 -> closed
    assert is_saudi_session(dt.date(2026, 11, 20)) is False
    assert is_saudi_session(dt.date(2026, 11, 21)) is False
    # Saudi National Day
    assert is_saudi_session(dt.date(2026, 9, 23)) is False

    monkeypatch.setenv("SAUDI_HOLIDAY_DATES", "2026-11-16")
    assert is_saudi_session(dt.date(2026, 11, 16)) is False


def test_saudi_price_sync_updates_prices_and_equal_weight_index():
    fake_sb = _FakeSaudiSupabase(
        {
            "market_index": [
                {"exchange": "TADAWUL", "date": "2026-11-12", "close": 3965.776321, "ret": -0.003, "source": "equal_weight"}
            ]
        }
    )
    stocks = [{"id": i, "symbol": str(1010 + i)} for i in range(12)]

    def fake_yf(symbols, _lookback, _max_date):
        # 11 symbols gain +2% from 10.0 to 10.20 between 2026-11-12 and 2026-11-15
        out = {}
        for sym in symbols[:11]:
            out[sym] = [
                {"date": "2026-11-12", "open": 10.0, "high": 10.1, "low": 9.9, "close": 10.0, "adjusted_close": 10.0, "volume": 1000, "source": "yahoo"},
                {"date": "2026-11-15", "open": 10.0, "high": 10.3, "low": 10.0, "close": 10.2, "adjusted_close": 10.2, "volume": 1500, "source": "yahoo"},
            ]
        return out

    def fake_tv(missing_syms, _lookback, _max_date):
        return {
            sym: [
                {"date": "2026-11-12", "open": 20.0, "high": 20.1, "low": 19.9, "close": 20.0, "adjusted_close": 20.0, "volume": 500, "source": "tvdatafeed"},
                {"date": "2026-11-15", "open": 20.0, "high": 20.5, "low": 20.0, "close": 20.4, "adjusted_close": 20.4, "volume": 700, "source": "tvdatafeed"},
            ]
            for sym in missing_syms
        }

    res = saudi_price_sync.sync_saudi_daily_prices(
        phase="close",
        lookback_days=7,
        sb=fake_sb,
        stock_rows=stocks,
        yf_fetcher=fake_yf,
        tv_fetcher=fake_tv,
    )

    assert res["success"] is True
    assert res["synced"] == 12
    assert res["failed_symbols"] == []
    assert res["latest_date"] == "2026-11-15"
    assert "2026-11-15" in res["index_dates_updated"]

    idx_2026_11_15 = [r for r in fake_sb.tables["market_index"] if r["date"] == "2026-11-15"]
    assert len(idx_2026_11_15) == 1
    assert idx_2026_11_15[0]["ret"] == pytest.approx(0.02, abs=1e-5)
    assert idx_2026_11_15[0]["close"] == pytest.approx(3965.776321 * 1.02, abs=1e-2)


def test_saudi_telegram_dispatch_is_vip_only_and_deduped(monkeypatch):
    monkeypatch.setenv("SAUDI_TELEGRAM_PRO_CHAT_ID", "-1004397045436")
    monkeypatch.setenv("TELEGRAM_FREE_CHAT_ID", "-1009999999999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")

    sent_calls = []

    class _MockResp:
        def json(self):
            return {"ok": True, "result": {"message_id": 777}}

    def fake_post(url, json=None, timeout=15):
        sent_calls.append({"url": url, "chat_id": json["chat_id"], "text": json["text"]})
        return _MockResp()

    monkeypatch.setattr(saudi_telegram_dispatch.requests, "post", fake_post)

    fake_sb = _FakeSaudiSupabase(
        {
            "scan_results": [
                {
                    "symbol": "2222",
                    "name": "أرامكو السعودية",
                    "status": "open",
                    "is_public": True,
                    "entry_price": 27.5,
                    "last_close": 28.0,
                    "target_price": 30.0,
                    "stop_loss": 26.2,
                    "precision": 0.78,
                }
            ]
        }
    )

    swings_payload = {
        "as_of_date": "2026-11-15",
        "new_entries": [
            {
                "symbol": "1120",
                "name_ar": "مصرف الراجحي",
                "reference_close": 92.5,
                "stop_loss": 88.8,
                "sector": "المصارف",
            }
        ],
        "new_exits": [
            {
                "symbol": "2010",
                "name_ar": "سابك",
                "entry_date": "2026-11-10",
                "exit_date": "2026-11-15",
                "entry_price": 70.0,
                "exit_price": 74.2,
                "return_pct": 6.0,
                "sessions": 4,
                "exit_reason": "هدف / تتبع EMA10",
            }
        ],
    }

    r1 = saudi_telegram_dispatch.dispatch_saudi_short_swings_vip(swings_payload, phase="close", sb=fake_sb)
    r2 = saudi_telegram_dispatch.dispatch_saudi_short_swings_vip(swings_payload, phase="close", sb=fake_sb)
    rec1 = saudi_telegram_dispatch.dispatch_saudi_open_recommendations(dedup_date="2026-11-15", sb=fake_sb)
    rec2 = saudi_telegram_dispatch.dispatch_saudi_open_recommendations(dedup_date="2026-11-15", sb=fake_sb)

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_OFFICIAL_API_KEY", raising=False)
    out1 = saudi_telegram_dispatch.dispatch_saudi_market_outlook_vip(
        market_status={"latest_date": "2026-11-15", "regime": "bull", "breadth": {"advancers": 150, "decliners": 90, "unchanged": 24}, "tasi_metrics": {"return_1d_pct": 1.1}},
        ind_rows=[{"symbol": "1120", "close": 92.5, "change_pct": 3.4}],
        recommendations_count=1,
        sb=fake_sb,
    )
    out2 = saudi_telegram_dispatch.dispatch_saudi_market_outlook_vip(
        market_status={"latest_date": "2026-11-15", "regime": "bull"},
        ind_rows=[],
        recommendations_count=1,
        sb=fake_sb,
    )

    assert r1["entries_sent"] == 1 and r1["exits_sent"] == 1
    assert r2["entries_sent"] == 0 and r2["exits_sent"] == 0
    assert rec1["ok"] is True and not rec1.get("skipped")
    assert rec2.get("skipped") is True
    assert out1["ok"] is True and not out1.get("skipped")
    assert out2.get("skipped") is True

    # Strictly VIP only — zero calls to free chat ID
    assert all(c["chat_id"] == "-1004397045436" for c in sent_calls)
    assert all(c["chat_id"] != "-1009999999999" for c in sent_calls)
    assert any("ر.س" in c["text"] for c in sent_calls)


def test_saudi_scheduler_phases_independent_of_egx(monkeypatch):
    monkeypatch.setenv("SAUDI_SUPABASE_URL", "https://saudi.supabase.co")
    monkeypatch.setenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setitem(daily_job_scheduler._scheduler_state, "saudi_enabled", True)
    monkeypatch.setitem(daily_job_scheduler._scheduler_state, "saudi_morning_run_time", "10:20")
    monkeypatch.setitem(daily_job_scheduler._scheduler_state, "saudi_midday_run_time", "12:45")
    monkeypatch.setitem(daily_job_scheduler._scheduler_state, "saudi_close_run_time", "15:25")
    monkeypatch.setitem(daily_job_scheduler._scheduler_state, "saudi_active_days", [0, 1, 2, 3, 6])

    tz = SAUDI_TZ
    # Sunday Nov 15, 2026
    assert daily_job_scheduler._due_saudi_phase(dt.datetime(2026, 11, 15, 9, 50, tzinfo=tz)) is None
    assert daily_job_scheduler._due_saudi_phase(dt.datetime(2026, 11, 15, 10, 20, tzinfo=tz)) == "morning"
    assert daily_job_scheduler._due_saudi_phase(dt.datetime(2026, 11, 15, 12, 45, tzinfo=tz)) == "midday"
    assert daily_job_scheduler._due_saudi_phase(dt.datetime(2026, 11, 15, 15, 10, tzinfo=tz)) is None
    assert daily_job_scheduler._due_saudi_phase(dt.datetime(2026, 11, 15, 15, 25, tzinfo=tz)) == "close"
    # Friday closed
    assert daily_job_scheduler._due_saudi_phase(dt.datetime(2026, 11, 20, 15, 30, tzinfo=tz)) is None

    # Verify EGX _execute_phase does NOT call _run_saudi_daily_refresh
    saudi_called = []
    monkeypatch.setattr(daily_job_scheduler, "_run_saudi_daily_refresh", lambda *a, **kw: saudi_called.append(True))

    async def fake_run_daily_job(**_kwargs):
        return {"job_run_id": "egx-job-1", "status": "completed", "steps": []}

    import api.daily_bot_run as daily_bot_run
    monkeypatch.setattr(daily_bot_run, "run_daily_job", fake_run_daily_job)
    monkeypatch.setattr(daily_job_scheduler, "_record_run", lambda *a, **kw: None)

    daily_job_scheduler._execute_phase("close", "test")
    assert saudi_called == []
