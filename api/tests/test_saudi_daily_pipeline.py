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


def test_saudi_telegram_dispatch_retries_on_timeout(monkeypatch):
    import requests as req_mod

    monkeypatch.setenv("SAUDI_TELEGRAM_PRO_CHAT_ID", "-1004397045436")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.setattr(saudi_telegram_dispatch.time, "sleep", lambda *_a: None)

    calls = {"n": 0}

    class _OkResp:
        status_code = 200
        content = b'{"ok":true}'

        def json(self):
            return {"ok": True, "result": {"message_id": 888}}

    def flaky_post(_url, json=None, timeout=25):
        calls["n"] += 1
        if calls["n"] < 3:
            raise req_mod.exceptions.ReadTimeout("timed out")
        return _OkResp()

    monkeypatch.setattr(saudi_telegram_dispatch.requests, "post", flaky_post)
    res = saudi_telegram_dispatch._send_telegram_message("hello", chat_id="-1004397045436")
    assert res["ok"] is True
    assert res["message_id"] == 888
    assert calls["n"] == 3


def test_saudi_runner_cache_revalidation_success_with_status_200(monkeypatch):
    from api import saudi_daily_runner

    fake_sb = _FakeSaudiSupabase()
    monkeypatch.setattr("api.saudi_price_sync.sync_saudi_daily_prices", lambda **_kw: {"success": True, "synced": 264, "total": 264, "latest_date": "2026-11-16"})
    monkeypatch.setattr(saudi_daily_runner, "_run_intraday_snapshot_and_short_swings", lambda *_a, **_kw: {"indicators_count": 264, "latest_date": "2026-11-16", "market_status": {}, "swings_payload": {}})
    monkeypatch.setattr("api.saudi_news_sync.run_saudi_news_sync", lambda **_kw: {"ok": True, "rows_saved": 10, "total_headlines": 20})
    monkeypatch.setattr("api.saudi_disclosures_sync.run_saudi_disclosures_sync", lambda **_kw: {"ok": True, "saved": 2, "fetched": 5})
    monkeypatch.setattr("api.gcc_metals_sync.run_gcc_metals_sync", lambda **_kw: {"ok": True, "summary": {"DFM": {"symbols_synced": 33}}})
    monkeypatch.setattr("api.gcc_news_sync.sync_gcc_market_news", lambda **_kw: {"ok": True, "synced_rows": 5, "matched_symbols": 3})
    monkeypatch.setattr("api.gcc_disclosures_sync.run_gcc_disclosures_sync", lambda **_kw: {"ok": True, "results": {"uae": {"inserted": 1}}})
    monkeypatch.setattr("api.cache_invalidation.invalidate_cache_tags", lambda tags: {"invalidated": list(tags), "skipped": False, "status": 200})

    out = saudi_daily_runner.run_saudi_daily_job(phase="midday", trigger="manual", dry_run=True, main_sb=fake_sb, saudi_sb=fake_sb)
    step_by_name = {s["step"]: s for s in out["steps"]}
    assert step_by_name["cache_revalidation"]["status"] == "success"
    assert out["error"] is None


def test_saudi_short_swings_vip_sends_active_updates_with_pnl_pct(monkeypatch):
    monkeypatch.setenv("SAUDI_TELEGRAM_PRO_CHAT_ID", "-1004397045436")
    monkeypatch.setenv("TELEGRAM_FREE_CHAT_ID", "-1009999999999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")

    sent_calls = []

    class _MockResp:
        status_code = 200
        content = b'{"ok":true}'

        def json(self):
            return {"ok": True, "result": {"message_id": 901}}

    monkeypatch.setattr(
        saudi_telegram_dispatch.requests,
        "post",
        lambda _u, json=None, timeout=25: (sent_calls.append(json) or _MockResp()),
    )

    fake_sb = _FakeSaudiSupabase()
    payload = {
        "as_of": "2026-11-17",
        "active_trades": [
            {
                "symbol": "2222",
                "name_ar": "أرامكو السعودية",
                "entry_date": "2026-11-15",
                "entry_price": 27.0,
                "current_price": 28.08,
                "trailing_stop": 27.10,
                "return_pct": 4.0,
                "status": "مؤمنة بربح",
            }
        ],
    }
    res = saudi_telegram_dispatch.dispatch_saudi_short_swings_vip(payload, phase="midday", sb=fake_sb)
    assert res["updates_sent"] == 1
    assert len(sent_calls) == 1
    assert sent_calls[0]["chat_id"] == "-1004397045436"
    assert "🟢 `+4.00%`" in sent_calls[0]["text"]
    assert "ر.س" in sent_calls[0]["text"]


def test_saudi_scanner_alerts_engine_vip_only_and_scheduler_hours(monkeypatch):
    from api import saudi_scanner_alerts_engine, scanner_alerts_scheduler

    monkeypatch.setenv("SAUDI_TELEGRAM_PRO_CHAT_ID", "-1004397045436")
    monkeypatch.setenv("TELEGRAM_FREE_CHAT_ID", "-1009999999999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")

    # Verify Tadawul hours helper (10:00..15:00 Riyadh Sun..Thu)
    assert scanner_alerts_scheduler._is_saudi_market_session(dt.datetime(2026, 11, 17, 10, 15, tzinfo=SAUDI_TZ)) is True
    assert scanner_alerts_scheduler._is_saudi_market_session(dt.datetime(2026, 11, 17, 14, 55, tzinfo=SAUDI_TZ)) is True
    assert scanner_alerts_scheduler._is_saudi_market_session(dt.datetime(2026, 11, 17, 15, 5, tzinfo=SAUDI_TZ)) is False
    assert scanner_alerts_scheduler._is_saudi_market_session(dt.datetime(2026, 11, 20, 12, 0, tzinfo=SAUDI_TZ)) is False

    sent_calls = []

    class _MockResp:
        status_code = 200
        content = b'{"ok":true}'

        def json(self):
            return {"ok": True, "result": {"message_id": 902}}

    monkeypatch.setattr(
        saudi_telegram_dispatch.requests,
        "post",
        lambda _u, json=None, timeout=25: (sent_calls.append(json) or _MockResp()),
    )

    fake_sb = _FakeSaudiSupabase(
        {
            "stock_technical_indicators": [
                {"symbol": "1120", "exchange": "TADAWUL", "date": "2026-11-17", "close": 95.0, "change_pct": 3.2, "volume": 2_000_000, "vol_sma20": 500_000, "r_vol": 4.0, "rsi_14": 62.0, "ema_20": 90.0, "bb_upper": 94.0},
                {"symbol": "2222", "exchange": "TADAWUL", "date": "2026-11-17", "close": 28.0, "change_pct": 1.1, "volume": 5_000_000, "vol_sma20": 4_000_000, "r_vol": 1.25, "rsi_14": 54.0, "ema_20": 27.2, "bb_upper": 28.5},
            ],
            "stock_prices": [
                {"symbol": "1120", "exchange": "TADAWUL", "date": "2026-11-17", "open": 92.0, "high": 95.5, "low": 91.8, "close": 95.0, "volume": 2_000_000},
                {"symbol": "2222", "exchange": "TADAWUL", "date": "2026-11-17", "open": 27.7, "high": 28.1, "low": 27.6, "close": 28.0, "volume": 5_000_000},
            ],
        }
    )

    out = saudi_scanner_alerts_engine.execute_saudi_scanner_alerts_native(
        force=True,
        refresh_prices=False,
        sb=fake_sb,
    )
    assert out["ok"] is True
    assert out["vip_only"] is True
    assert all(c["chat_id"] == "-1004397045436" for c in sent_calls)
    assert all(c["chat_id"] != "-1009999999999" for c in sent_calls)


def test_saudi_scanner_blocks_new_entries_in_panic_regime(monkeypatch):
    from api import saudi_scanner_alerts_engine

    monkeypatch.setenv("SAUDI_TELEGRAM_PRO_CHAT_ID", "-1004397045436")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.setattr(
        saudi_scanner_alerts_engine,
        "get_riyadh_now",
        lambda: {"date_str": "2026-11-17", "time_str": "12:00", "is_trading_day": True, "is_trading_hours": True},
    )

    fake_sb = _FakeSaudiSupabase(
        {
            "market_cache": [
                {
                    "cache_key": "market_status_Saudi Arabia",
                    "country": "Saudi Arabia",
                    "payload": {"regime": "panic", "reject_buys": True},
                }
            ],
            "stock_technical_indicators": [
                {"symbol": "1120", "exchange": "TADAWUL", "date": "2026-11-17", "close": 95.0, "change_pct": 4.5, "volume": 2_000_000, "vol_sma20": 500_000, "r_vol": 4.0, "rsi_14": 62.0, "ema_20": 90.0, "ema_50": 88.0, "bb_upper": 94.0},
            ],
            "stock_prices": [
                {"symbol": "1120", "exchange": "TADAWUL", "date": "2026-11-17", "open": 91.0, "high": 95.2, "low": 90.9, "close": 95.0, "volume": 2_000_000},
            ],
        }
    )

    out = saudi_scanner_alerts_engine.execute_saudi_scanner_alerts_native(
        force=False,
        refresh_prices=False,
        dry_run=True,
        sb=fake_sb,
    )
    assert out["ok"] is True
    assert out["new_signals"] == 0


def test_saudi_short_swings_ignores_egx_published_signals(monkeypatch):
    import pandas as pd
    from api import short_swings_engine as sse

    dates = pd.bdate_range(end="2026-10-16", periods=70)
    rows = []
    for i, d in enumerate(dates):
        base = 50.0 + i * 0.25
        close = base + (2.5 if i == 68 else 0.1)
        vol = 1_200_000.0 if i == 68 else 500_000.0
        rows.append({
            "symbol": "1120",
            "exchange": "TADAWUL",
            "date": d.strftime("%Y-%m-%d"),
            "open": base,
            "high": close + 0.1,
            "low": base - 0.1,
            "close": close,
            "volume": vol,
        })
    preloaded = pd.DataFrame(rows)
    monkeypatch.setattr(sse, "_load_published_signals", lambda _sb: [{"symbol": "COMI", "signal_date": "2026-10-01", "reference_close": 80.0}])
    monkeypatch.setattr(sse, "_persist_saudi_snapshot", lambda _r: True)
    monkeypatch.setattr(sse, "SAUDI_CACHE_PATHS", [])
    res = sse.compute_short_swings(phase="close", exchange="TADAWUL", preloaded_df=preloaded, preloaded_meta={"1120": {"name_ar": "الراجحي", "sector": "المصارف"}})
    assert res["status"] == "ok"
    assert len(res["active_trades"]) + len(res["closed_trades"]) >= 1


def test_saudi_tv_fallback_does_not_hang_on_stalled_symbol(monkeypatch):
    import sys
    import threading
    import time
    import types
    import pandas as pd
    from api import saudi_price_sync

    release = threading.Event()

    class _Interval:
        in_daily = "1d"

    class _FakeTv:
        def get_hist(self, symbol, exchange=None, interval=None, n_bars=5):
            if symbol == "STALL":
                release.wait(timeout=5.0)
                return None
            return pd.DataFrame(
                {"open": [30.0], "high": [31.0], "low": [29.5], "close": [30.5], "volume": [1_000_000.0]},
                index=pd.to_datetime(["2026-11-16"]),
            )

    fake_mod = types.SimpleNamespace(TvDatafeed=_FakeTv, Interval=_Interval)
    monkeypatch.setitem(sys.modules, "tvDatafeed", fake_mod)

    t0 = time.monotonic()
    try:
        out = saudi_price_sync._default_tv_fetcher(
            ["2222", "STALL"],
            lookback_days=7,
            max_date_str="2026-11-16",
            symbol_timeout_s=0.15,
            batch_timeout_s=0.5,
        )
    finally:
        release.set()

    elapsed = time.monotonic() - t0
    assert "2222" in out
    assert out["2222"][0]["close"] == 30.5
    assert "STALL" not in out
    assert elapsed < 1.5


def test_saudi_runner_resumes_only_missing_stages(monkeypatch):
    import json
    from api import saudi_daily_runner

    now_riyadh = dt.datetime.now(SAUDI_TZ).isoformat()
    fake_sb = _FakeSaudiSupabase(
        {
            "daily_job_runs": [
                {
                    "id": "saudi-resume-1",
                    "job_type": "saudi_midday",
                    "status": "failed",
                    "started_at": now_riyadh,
                    "total_symbols": 264,
                    "steps": json.dumps([
                        {"step": "saudi_price_sync", "status": "success", "count": 263, "details": "synced=263/264"},
                    ]),
                }
            ]
        }
    )

    def fail_if_called(**_kw):
        raise AssertionError("saudi_price_sync must not re-run when already succeeded")

    monkeypatch.setattr("api.saudi_price_sync.sync_saudi_daily_prices", fail_if_called)
    monkeypatch.setattr(
        saudi_daily_runner,
        "_run_intraday_snapshot_and_short_swings",
        lambda *_a, **_kw: {"indicators_count": 264, "latest_date": "2026-11-17", "market_status": {}, "swings_payload": {}},
    )
    monkeypatch.setattr("api.saudi_news_sync.run_saudi_news_sync", lambda **_kw: {"ok": True, "rows_saved": 5, "total_headlines": 10})
    monkeypatch.setattr("api.saudi_disclosures_sync.run_saudi_disclosures_sync", lambda **_kw: {"ok": True, "saved": 1, "fetched": 2})
    monkeypatch.setattr("api.gcc_metals_sync.run_gcc_metals_sync", lambda **_kw: {"ok": True, "summary": {"DFM": {"symbols_synced": 33}}})
    monkeypatch.setattr("api.gcc_news_sync.sync_gcc_market_news", lambda **_kw: {"ok": True, "synced_rows": 5, "matched_symbols": 3})
    monkeypatch.setattr("api.gcc_disclosures_sync.run_gcc_disclosures_sync", lambda **_kw: {"ok": True, "results": {"uae": {"inserted": 1}}})
    monkeypatch.setattr("api.cache_invalidation.invalidate_cache_tags", lambda tags: {"invalidated": list(tags), "skipped": False, "status": 200})

    out = saudi_daily_runner.run_saudi_daily_job(
        phase="midday",
        trigger="scheduled",
        dry_run=True,
        main_sb=fake_sb,
        saudi_sb=fake_sb,
        resume_job_id="saudi-resume-1",
    )
    assert out["ok"] is True
    assert out["job_run_id"] == "saudi-resume-1"
    step_names = [s["step"] for s in out["steps"]]
    assert step_names.count("saudi_price_sync") == 1
    assert "saudi_intraday_refresh" in step_names
    assert "cache_revalidation" in step_names


def test_market_outlook_includes_index_levels_and_percentages(monkeypatch):
    from api import daily_market_outlook as egx_outlook
    from api import saudi_telegram_dispatch as sa_disp

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_OFFICIAL_API_KEY", raising=False)

    monkeypatch.setattr(egx_outlook, "_supabase_get", lambda _ep: [])
    egx_msg = egx_outlook.compose_daily_market_outlook_native(
        "2026-11-17",
        {
            "regime": "bear",
            "blocked": True,
            "reason": "test",
            "market_context": {
                "egx30": {"close": 51681.6, "return_1d_pct": -0.99, "return_5d_pct": -1.53, "sma50": 52434.1},
                "egx100": {"close": 23535.1, "return_1d_pct": -2.03, "return_5d_pct": -3.92},
            },
        },
        recommendations_created=0,
    )
    assert "51,681.60" in egx_msg and "-0.99%" in egx_msg
    assert "23,535.10" in egx_msg and "-2.03%" in egx_msg

    sa_msg = sa_disp.compose_saudi_market_outlook(
        "2026-11-17",
        {
            "regime": "bull",
            "reject_buys": False,
            "breadth": {"advancers": 150, "decliners": 90, "unchanged": 24, "above_sma50_pct": 62.5},
            "tasi_metrics": {"close": 11250.5, "return_1d_pct": 1.1, "return_5d_pct": 2.4},
        },
        ind_rows=[{"symbol": "1120", "close": 92.5, "change_pct": 3.4}],
        recommendations_count=1,
    )
    assert "11,250.50" in sa_msg and "+1.10%" in sa_msg and "+2.40%" in sa_msg

    # Synthetic equal-weight base-4000 index (< 8000) must NOT display fake TASI 'نقطة' points
    sa_synth = sa_disp.compose_saudi_market_outlook(
        "2026-11-18",
        {
            "regime": "bear",
            "reject_buys": True,
            "breadth": {"advancers": 47, "decliners": 209, "unchanged": 8, "above_sma50_pct": 23.9},
            "tasi_metrics": {"close": 3831.88, "return_1d_pct": -1.17, "return_5d_pct": -3.67},
        },
        ind_rows=[{"symbol": "2110", "close": 199.3, "change_pct": 4.9}],
        recommendations_count=1,
    )
    assert "3,831.88" not in sa_synth
    assert "نقطة" not in sa_synth
    assert "-1.17%" in sa_synth and "-3.67%" in sa_synth


def test_saudi_scanner_allows_bear_sniper_entries(monkeypatch):
    from api import saudi_scanner_alerts_engine

    monkeypatch.setattr(
        saudi_scanner_alerts_engine,
        "get_riyadh_now",
        lambda: {"date_str": "2026-11-18", "time_str": "11:30", "is_trading_day": True, "is_trading_hours": True},
    )
    fake_sb = _FakeSaudiSupabase(
        {
            "market_cache": [
                {
                    "cache_key": "market_status_Saudi Arabia",
                    "country": "Saudi Arabia",
                    "payload": {"regime": "bear", "reject_buys": True},
                },
            ],
            "stock_technical_indicators": [
                {
                    "symbol": "1150",
                    "exchange": "TADAWUL",
                    "date": "2026-11-18",
                    "open": 19.2,
                    "high": 20.1,
                    "low": 19.1,
                    "close": 20.0,
                    "change_pct": 4.2,
                    "volume": 200_000,  # 4M SAR turnover (>= 3M healthy sniper gate)
                    "vol_sma20": 80_000,
                    "r_vol": 2.5,
                    "rsi_14": 60.0,
                    "ema_20": 18.8,
                    "ema_50": 18.0,
                    "bb_upper": 19.8,
                },
            ],
            "stock_prices": [
                {
                    "symbol": "1150",
                    "exchange": "TADAWUL",
                    "date": "2026-11-18",
                    "open": 19.2,
                    "high": 20.1,
                    "low": 19.1,
                    "close": 20.0,
                    "volume": 200_000,
                },
            ],
        }
    )

    out = saudi_scanner_alerts_engine.execute_saudi_scanner_alerts_native(
        force=False, refresh_prices=False, dry_run=True, sb=fake_sb
    )
    assert out["ok"] is True
    assert out["new_signals"] >= 1


def test_saudi_daily_vip_report_compose_and_dispatch(monkeypatch):
    sent_messages = []

    def _fake_send(text, chat_id=None, parse_mode="HTML", dry_run=False):
        sent_messages.append({"text": text, "chat_id": chat_id, "parse_mode": parse_mode, "dry_run": dry_run})
        return {"ok": True, "message_id": 9001}

    monkeypatch.setattr(saudi_telegram_dispatch, "_send_telegram_message", _fake_send)

    fake_sb = _FakeSaudiSupabase(
        {
            "market_cache": [
                {
                    "cache_key": "daily_traps_snapshot",
                    "country": "Saudi Arabia",
                    "payload": {
                        "asOf": "2026-11-18",
                        "totalBearTraps": 11,
                        "totalBullTraps": 14,
                        "bearTraps": [
                            {"symbol": "1120", "close": 92.5, "keyLevel": 90.0, "conviction": 82, "relativeVolume": 1.9}
                        ],
                        "bullTraps": [{"symbol": "2010", "close": 70.0, "keyLevel": 72.0}],
                    },
                }
            ],
            "stock_scans_summary": [
                {
                    "symbol": "2222",
                    "scan_date": "2026-11-18",
                    "signal": "strong_accumulation",
                    "acc_score": 88,
                    "dist_score": 10,
                    "vol_ratio": 2.1,
                    "consecutive_acc_days": 4,
                    "rsi_14": 54.0,
                    "change_pct": 1.8,
                }
            ],
            "egx_disclosures": [
                {
                    "symbol": "1211",
                    "company_name": "معادن",
                    "disclosure_type": "financial",
                    "disclosure_date": "2026-11-18",
                    "title": "نتائج الربع الثالث <نمو> & أرباح قوية",
                    "sentiment": "positive",
                }
            ],
            "stock_technical_indicators": [
                {"symbol": "1120", "exchange": "TADAWUL", "date": "2026-11-18", "close": 92.5, "change_pct": 3.4, "volume": 1_200_000, "r_vol": 2.1},
            ],
        }
    )

    first = saudi_telegram_dispatch.dispatch_saudi_daily_vip_report(market_date="2026-11-18", sb=fake_sb)
    assert first["ok"] is True
    assert first["message_id"] == 9001
    assert len(sent_messages) == 1
    body = sent_messages[0]["text"]
    assert "تقرير VIP الحصري" in body
    assert "1120" in body
    assert "2222" in body
    assert "1211" in body
    assert "11 نموذج ارتداد تجميعي" in body
    assert "14 مصيدة قمة" in body
    assert "تجميع مؤسسي قوي" in body
    assert "strong_accumulation" not in body
    assert "/scanner/backtests?market=sa" in body
    assert "/tasi\"" not in body
    assert "&lt;نمو&gt; &amp; أرباح قوية" in body

    second = saudi_telegram_dispatch.dispatch_saudi_daily_vip_report(market_date="2026-11-18", sb=fake_sb)
    assert second["ok"] is True
    assert second.get("skipped") is True
    assert len(sent_messages) == 1


def test_saudi_runner_close_dispatches_vip_report(monkeypatch):
    from api import saudi_daily_runner

    fake_sb = _FakeSaudiSupabase(
        {
            "market_cache": [
                {"cache_key": "market_status_Saudi Arabia", "country": "Saudi Arabia", "payload": {"regime": "bear", "reject_buys": True}},
            ],
            "stock_technical_indicators": [
                {"symbol": "1120", "exchange": "TADAWUL", "date": "2026-11-18", "close": 92.5, "change_pct": 3.4},
            ],
            "scan_results": [
                {"symbol": "8200", "status": "open"},
            ],
        }
    )
    monkeypatch.setattr("api.saudi_price_sync.sync_saudi_daily_prices", lambda **_kw: {"success": True, "synced": 264, "total": 264, "latest_date": "2026-11-18"})
    monkeypatch.setattr("scripts.saudi_pipeline_bootstrap.main", lambda **_kw: 0)
    monkeypatch.setattr(
        "scripts.saudi_backtest_and_systems.main",
        lambda *_a, **_kw: {"short_swings": {"as_of_date": "2026-11-18", "active_trades": [], "new_entries": [], "new_exits": []}},
    )
    monkeypatch.setattr("api.saudi_news_sync.run_saudi_news_sync", lambda **_kw: {"ok": True, "rows_saved": 5, "total_headlines": 10})
    monkeypatch.setattr("api.saudi_disclosures_sync.run_saudi_disclosures_sync", lambda **_kw: {"ok": True, "saved": 1, "fetched": 2})
    monkeypatch.setattr("api.gcc_metals_sync.run_gcc_metals_sync", lambda **_kw: {"ok": True, "summary": {"DFM": {"symbols_synced": 33}}})
    monkeypatch.setattr("api.gcc_news_sync.sync_gcc_market_news", lambda **_kw: {"ok": True, "synced_rows": 5, "matched_symbols": 3})
    monkeypatch.setattr("api.gcc_disclosures_sync.run_gcc_disclosures_sync", lambda **_kw: {"ok": True, "results": {"uae": {"inserted": 1}}})
    monkeypatch.setattr("api.cache_invalidation.invalidate_cache_tags", lambda tags: {"invalidated": list(tags), "skipped": False, "status": 200})

    called_report = []
    monkeypatch.setattr(saudi_telegram_dispatch, "dispatch_saudi_short_swings_vip", lambda *_a, **_kw: {"entries_sent": 0, "exits_sent": 0, "updates_sent": 0, "errors": []})
    monkeypatch.setattr(saudi_telegram_dispatch, "dispatch_saudi_open_recommendations", lambda **_kw: {"ok": True, "skipped": True})
    monkeypatch.setattr(saudi_telegram_dispatch, "dispatch_saudi_market_outlook_vip", lambda **_kw: {"ok": True, "message_id": 101})
    monkeypatch.setattr(
        saudi_telegram_dispatch,
        "dispatch_saudi_daily_vip_report",
        lambda **kw: (called_report.append(kw.get("market_date")) or {"ok": True, "message_id": 102}),
    )

    out = saudi_daily_runner.run_saudi_daily_job(phase="close", trigger="manual", dry_run=True, main_sb=fake_sb, saudi_sb=fake_sb)
    step_by_name = {s["step"]: s for s in out["steps"]}
    assert called_report == ["2026-11-18"]
    assert "report_vip(ok=True, skipped=False)" in step_by_name["saudi_telegram_vip"]["details"]


def test_saudi_short_swings_rs_leader_fires_between_022_and_045_breadth(monkeypatch, tmp_path):
    import pandas as pd
    from api import short_swings_engine as ss_engine

    dates = pd.bdate_range(end="2026-11-18", periods=90)
    rows = []
    for sym in ["1120", "2010", "4001"]:
        for i, d in enumerate(dates):
            if sym == "1120":
                c = 80.0 + i * 0.6
                rows.append({
                    "symbol": sym, "exchange": "TADAWUL", "date": d,
                    "open": c - 0.5, "high": c + 0.1, "low": c - 0.7, "close": c,
                    "volume": 900_000 if i == len(dates) - 2 else 400_000,
                })
            else:
                c = 150.0 - i * 0.5
                rows.append({
                    "symbol": sym, "exchange": "TADAWUL", "date": d,
                    "open": c + 0.2, "high": c + 0.5, "low": c - 0.5, "close": c,
                    "volume": 100_000,
                })

    monkeypatch.setattr(ss_engine, "SAUDI_CACHE_PATHS", [tmp_path / "saudi_swings.json"])
    monkeypatch.setattr(ss_engine, "_persist_saudi_snapshot", lambda *_: True)
    monkeypatch.setattr(ss_engine, "_restore_saudi_snapshot", lambda *_: None)
    monkeypatch.setattr(ss_engine, "_get_saudi_supabase_client", lambda: None)

    res = ss_engine.compute_short_swings(
        phase="close",
        exchange="TADAWUL",
        preloaded_df=pd.DataFrame(rows),
        preloaded_meta={"1120": {"name_ar": "الراجحي", "name_en": "Al Rajhi", "sector": "البنوك"}},
    )
    active = next((t for t in res["active_trades"] if t["symbol"] == "1120"), None)
    assert active is not None
    assert "RS Leader" in str(active.get("trigger_type") or "")
    audit_sig = next((a for a in res["signal_audit"] if a["symbol"] == "1120" and a["date"] == dates[-2].date().isoformat()), None)
    assert audit_sig is not None
    assert 0.22 <= audit_sig["breadth"] < 0.45


def test_egx_daily_disclosures_sync_imports_exclude_keywords():
    from jobs import daily_disclosures_sync
    from scripts.disclosures import sync_egx_disclosures

    assert sync_egx_disclosures.EXCLUDE_KEYWORDS is sync_egx_disclosures.GULF_EXCLUDE_KEYWORDS
    assert daily_disclosures_sync.EXCLUDE_KEYWORDS is sync_egx_disclosures.GULF_EXCLUDE_KEYWORDS
    assert len(daily_disclosures_sync.EXCLUDE_KEYWORDS) > 0


def test_gcc_and_metals_scheduler_friday_uae_and_weekday_metals(monkeypatch):
    monkeypatch.setenv("SAUDI_SUPABASE_URL", "https://saudi.supabase.co")
    monkeypatch.setenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setitem(daily_job_scheduler._scheduler_state, "gcc_enabled", True)
    monkeypatch.setitem(daily_job_scheduler._scheduler_state, "uae_friday_close_time", "15:30")
    monkeypatch.setitem(daily_job_scheduler._scheduler_state, "metals_close_time_utc", "22:15")

    dubai_tz = ZoneInfo("Asia/Dubai")
    utc_tz = dt.timezone.utc

    # Thursday 16:00 Dubai / 12:00 UTC -> covered by saudi_close, nothing extra due yet
    assert daily_job_scheduler._due_gcc_modes(
        dt.datetime(2026, 11, 19, 16, 0, tzinfo=dubai_tz),
        dt.datetime(2026, 11, 19, 12, 0, tzinfo=utc_tz),
    ) == []

    # Thursday 22:20 UTC -> global metals close due
    assert daily_job_scheduler._due_gcc_modes(
        dt.datetime(2026, 11, 20, 2, 20, tzinfo=dubai_tz),
        dt.datetime(2026, 11, 19, 22, 20, tzinfo=utc_tz),
    ) == ["metals_close"]

    # Friday 15:30 Dubai / 11:30 UTC -> UAE Friday close due
    assert daily_job_scheduler._due_gcc_modes(
        dt.datetime(2026, 11, 20, 15, 30, tzinfo=dubai_tz),
        dt.datetime(2026, 11, 20, 11, 30, tzinfo=utc_tz),
    ) == ["uae_close"]

    # Friday 22:30 UTC (still Friday in Dubai? No, 02:30 Sat in Dubai) -> metals_close due
    assert daily_job_scheduler._due_gcc_modes(
        dt.datetime(2026, 11, 21, 2, 30, tzinfo=dubai_tz),
        dt.datetime(2026, 11, 20, 22, 30, tzinfo=utc_tz),
    ) == ["metals_close"]

    # Friday 19:50 Dubai / 15:50 UTC -> only uae_close
    assert daily_job_scheduler._due_gcc_modes(
        dt.datetime(2026, 11, 20, 19, 50, tzinfo=dubai_tz),
        dt.datetime(2026, 11, 20, 15, 50, tzinfo=utc_tz),
    ) == ["uae_close"]

    # Saturday / Sunday -> nothing due
    assert daily_job_scheduler._due_gcc_modes(
        dt.datetime(2026, 11, 21, 16, 0, tzinfo=dubai_tz),
        dt.datetime(2026, 11, 21, 22, 30, tzinfo=utc_tz),
    ) == []
    assert daily_job_scheduler._due_gcc_modes(
        dt.datetime(2026, 11, 22, 16, 0, tzinfo=dubai_tz),
        dt.datetime(2026, 11, 22, 22, 30, tzinfo=utc_tz),
    ) == []


def test_run_gcc_metals_daily_job_modes(monkeypatch):
    from api import saudi_daily_runner

    fake_sb = _FakeSaudiSupabase()
    sync_calls = []
    news_calls = []
    disc_calls = []
    cache_calls = []

    monkeypatch.setattr(
        "api.gcc_metals_sync.run_gcc_metals_sync",
        lambda **kw: (sync_calls.append(kw) or {"ok": True, "summary": {e: {"symbols_synced": 2} for e in kw.get("exchanges", [])}}),
    )
    monkeypatch.setattr(
        "api.gcc_news_sync.sync_gcc_market_news",
        lambda **kw: (news_calls.append(kw) or {"ok": True, "synced_rows": 12, "matched_symbols": 6}),
    )
    monkeypatch.setattr(
        "api.gcc_disclosures_sync.run_gcc_disclosures_sync",
        lambda **kw: (disc_calls.append(kw) or {"ok": True, "results": {"uae": {"inserted": 4}}}),
    )
    monkeypatch.setattr(
        "api.cache_invalidation.invalidate_cache_tags",
        lambda tags: (cache_calls.append(list(tags)) or {"invalidated": list(tags), "skipped": False, "status": 200}),
    )

    uae_out = saudi_daily_runner.run_gcc_metals_daily_job(mode="uae_close", trigger="scheduled", main_sb=fake_sb)
    assert uae_out["ok"] is True
    assert uae_out["job_type"] == "uae_close"
    assert sync_calls[-1] == {"exchanges": ["DFM", "ADX", "COMMODITIES"], "daily_only": True}
    assert news_calls[-1]["market"] == "uae"
    assert disc_calls[-1]["market"] == "uae"
    assert cache_calls[-1] == ["daily-market-data", "daily-symbols", "daily-news-data", "daily-disclosures"]

    metals_out = saudi_daily_runner.run_gcc_metals_daily_job(mode="metals_close", trigger="scheduled", main_sb=fake_sb)
    assert metals_out["ok"] is True
    assert metals_out["job_type"] == "metals_close"
    assert sync_calls[-1] == {"exchanges": ["COMMODITIES"], "daily_only": True}
    assert len(news_calls) == 1
    assert len(disc_calls) == 1
    assert cache_calls[-1] == ["daily-market-data", "daily-symbols"]

    # Failure path: when all data steps fail, status must be failed and cache invalidation must NOT run
    cache_calls.clear()
    monkeypatch.setattr("api.gcc_metals_sync.run_gcc_metals_sync", lambda **_kw: {"ok": False, "error": "provider_down"})
    monkeypatch.setattr("api.gcc_news_sync.sync_gcc_market_news", lambda **_kw: {"ok": False, "error": "rss_down"})
    monkeypatch.setattr("api.gcc_disclosures_sync.run_gcc_disclosures_sync", lambda **_kw: {"ok": False, "error": "disc_down"})
    fail_out = saudi_daily_runner.run_gcc_metals_daily_job(mode="uae_close", trigger="scheduled", main_sb=fake_sb)
    assert fail_out["ok"] is False
    assert fail_out["status"] == "failed"
    assert cache_calls == []
