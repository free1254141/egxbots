"""
Offline deterministic unit tests for 2026-11-24 post-29a43112 production audit hardening:
1. Time-of-day intraday U-shaped volume pacing & missing-feed prior-close fallback
2. Quant engine intraday-unavailable guard (no false low-liquidity bear case)
3. Tactical support risk/reward + EGX momentum_and_volume intraday scan fallback
4. Portfolio profitable position counts & intraday high-turnover blue-chip guard
5. Deterministic OR tradeSummary totals
6. Scheduled automations static system prompt + strictly user-isolated SHA-256 snapshot cache
7. Telegram relative markdown link rewriting (Web <-> Telegram shared VIP cache parity)
8. Pipeline degraded/empty scan cache guard + standalone multi-turn & preset Fast-Track
9. HF sync manifest registration check
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest


# ---------------------------------------------------------------------------
# 1. Intraday Volume Pacing Engine
# ---------------------------------------------------------------------------

def test_intraday_volume_curve_and_live_pacing() -> None:
    from api.agentic_chat.intraday_volume import (
        expected_cumulative_volume_fraction,
        get_exchange_session_state,
        resolve_intraday_r_vol,
    )

    # Monotonic U-shaped cumulative volume curve
    samples = [expected_cumulative_volume_fraction(u) for u in (0.0, 0.11, 0.35, 0.75, 1.0)]
    assert samples[0] == 0.0
    assert samples[-1] == 1.0
    assert all(samples[i] < samples[i + 1] for i in range(len(samples) - 1))

    cairo_tz = ZoneInfo("Africa/Cairo")
    t_1041 = dt.datetime(2026, 11, 24, 10, 41, tzinfo=cairo_tz)  # Tuesday live morning
    sess_am = get_exchange_session_state("EGX", now_dt=t_1041)
    assert sess_am["is_live_session"] is True
    assert sess_am["elapsed_min"] == 41

    # Liquid stock COMI with unpopulated intraday volume (raw 0.00x) -> previous completed session fallback (1.25x)
    hist_liquid = [{"date": "2026-11-24", "volume": 0}, {"date": "2026-11-23", "volume": 2_500_000}] + [
        {"date": f"2026-11-{d:02d}", "volume": 2_000_000} for d in range(22, 10, -1)
    ]
    res_missing = resolve_intraday_r_vol(
        0.0,
        "2026-11-24",
        exchange="EGX",
        ohlcv_rows=hist_liquid,
        now_dt=t_1041,
    )
    assert res_missing["r_vol_mode"] == "prev_close_fallback"
    assert res_missing["effective_r_vol"] == 1.25
    assert res_missing["is_intraday_adjusted"] is True
    assert res_missing["r_vol_note_ar"] and "آخر إغلاق" in res_missing["r_vol_note_ar"]

    # Genuinely dead/illiquid stock (zero volume for past 10 sessions) MUST keep 0.00x
    hist_dead = [{"date": f"2026-11-{d:02d}", "volume": 0} for d in range(24, 10, -1)]
    res_dead = resolve_intraday_r_vol(
        0.0,
        "2026-11-24",
        exchange="EGX",
        ohlcv_rows=hist_dead,
        now_dt=t_1041,
    )
    assert res_dead["r_vol_mode"] == "eod"
    assert res_dead["effective_r_vol"] == 0.0
    assert res_dead["is_intraday_adjusted"] is False

    # Measurable partial live volume (0.45x at 12:15 Cairo) -> Bayesian time-paced projection > 0.45x
    t_1215 = dt.datetime(2026, 11, 24, 12, 15, tzinfo=cairo_tz)
    res_paced = resolve_intraday_r_vol(
        0.45,
        "2026-11-24",
        exchange="EGX",
        ohlcv_rows=hist_liquid,
        now_dt=t_1215,
    )
    assert res_paced["r_vol_mode"] == "intraday_paced"
    assert 0.80 <= res_paced["effective_r_vol"] <= 1.20
    assert res_paced["is_intraday_adjusted"] is True

    # Outside live session -> EOD untouched
    t_1600 = dt.datetime(2026, 11, 24, 16, 0, tzinfo=cairo_tz)
    res_eod = resolve_intraday_r_vol(1.42, "2026-11-24", exchange="EGX", ohlcv_rows=hist_liquid, now_dt=t_1600)
    assert res_eod["r_vol_mode"] == "eod"
    assert res_eod["effective_r_vol"] == 1.42
    assert res_eod["is_intraday_adjusted"] is False


# ---------------------------------------------------------------------------
# 2. Quant Engine Intraday Guard
# ---------------------------------------------------------------------------

def test_quant_engine_intraday_unavailable_suppresses_low_liquidity_bear() -> None:
    from api.agentic_chat.quant_engine import build_quant_intelligence_for_stock

    bars = [
        {"date": f"2026-11-{d:02d}", "close": 100.0 + d * 0.2, "high": 102.0, "low": 99.0}
        for d in range(1, 24)
    ]
    res_unavail = build_quant_intelligence_for_stock(
        symbol="COMI",
        exchange="EGX",
        close=104.5,
        rsi_14=54.0,
        ema_50=102.0,
        ema_200=95.0,
        r_vol=0.0,
        r_vol_mode="intraday_unavailable",
        fund_score=85.0,
        ohlcv_rows=bars,
        record_ledger=False,
    )
    assert not any("سيولة منخفضة" in item for item in res_unavail["bear_case"])

    # In true EOD mode, genuine 0.25x still emits the bear-case liquidity caution
    res_eod_low = build_quant_intelligence_for_stock(
        symbol="COMI",
        exchange="EGX",
        close=104.5,
        rsi_14=54.0,
        ema_50=102.0,
        ema_200=95.0,
        r_vol=0.25,
        r_vol_mode="eod",
        fund_score=85.0,
        ohlcv_rows=bars,
        record_ledger=False,
    )
    assert any("سيولة منخفضة" in item for item in res_eod_low["bear_case"])


# ---------------------------------------------------------------------------
# 3. Context Metrics Tactical Support R:R & EGX Momentum Scan Intraday Fallback
# ---------------------------------------------------------------------------

def test_tactical_support_rr_and_technical_scan_intraday_fallback() -> None:
    from api.agentic_chat.tools_execution import _compute_stock_context_metrics, _sync_get_technical_scan

    ctx = _compute_stock_context_metrics(
        close=0.500,
        ema_50=0.490,
        ema_200=0.480,
        vwap_20=0.492,
        support_1=0.400,  # distant (-20%)
        resistance_1=0.588,
        stop_loss=0.392,
    )
    assert ctx["support_1_is_distant"] is True
    assert ctx["tactical_support"] == 0.492
    assert ctx["tactical_stop_loss"] == 0.4797
    assert ctx["tactical_risk_reward_from_support"] == round((0.588 - 0.492) / (0.492 - 0.4797), 2)

    class _MockRes:
        def __init__(self, data):
            self.data = data

    class _MockScanQuery:
        def __init__(self, scenario: str):
            self._scenario = scenario
            self._filters = []
            self._select = ""
            self._gte_rvol = None

        def select(self, cols: str):
            self._select = cols
            return self

        def eq(self, col: str, val):
            self._filters.append(("eq", col, val))
            return self

        def gte(self, col: str, val):
            self._filters.append(("gte", col, val))
            if col == "r_vol":
                self._gte_rvol = val
            return self

        def lt(self, col: str, val):
            self._filters.append(("lt", col, val))
            return self

        def order(self, col: str, desc: bool = False):
            return self

        def limit(self, n: int):
            return self

        def execute(self):
            eq_map = {col: val for op, col, val in self._filters if op == "eq"}
            has_lt_date = any(op == "lt" and col == "date" for op, col, _ in self._filters)
            if self._select == "date" and not eq_map.get("date") and not has_lt_date:
                return _MockRes([{"date": "2026-11-24"}])
            if self._select == "date" and has_lt_date:
                return _MockRes([{"date": "2026-11-23"}])
            if self._scenario == "empty_raw_then_paced":
                if self._gte_rvol is not None and eq_map.get("date") == "2026-11-24":
                    return _MockRes([])
                return _MockRes([
                    {"symbol": "MTIE", "date": "2026-11-24", "close": 7.5, "change_pct": 5.1, "volume": 500000, "r_vol": 0.75, "rsi_14": 61.0},
                    {"symbol": "CRST", "date": "2026-11-24", "close": 2.4, "change_pct": 4.2, "volume": 400000, "r_vol": 0.68, "rsi_14": 58.0},
                    {"symbol": "KORA", "date": "2026-11-24", "close": 1.1, "change_pct": 3.0, "volume": 300000, "r_vol": 0.62, "rsi_14": 55.0},
                ])
            # Scenario B: zero intraday r_vol today -> falls back to prev_date (2026-11-23)
            if eq_map.get("date") == "2026-11-24":
                return _MockRes([])
            return _MockRes([
                {"symbol": "FWRY", "date": "2026-11-23", "close": 14.5, "change_pct": 3.4, "volume": 9000000, "r_vol": 1.85, "rsi_14": 59.0},
            ])

    class _MockScanSB:
        def __init__(self, scenario: str):
            self._scenario = scenario

        def from_(self, _tbl: str):
            return _MockScanQuery(self._scenario)

    live_noon = dt.datetime(2026, 11, 24, 12, 15, tzinfo=ZoneInfo("Africa/Cairo"))
    with patch("api.agentic_chat.tools_execution._get_sb", return_value=_MockScanSB("empty_raw_then_paced")), \
         patch("api.agentic_chat.intraday_volume.get_exchange_session_state", return_value={
             "exchange": "EGX", "today_str": "2026-11-24", "is_trading_day": True,
             "is_live_session": True, "elapsed_min": 135, "session_len_min": 270,
             "progress_u": 0.5, "expected_cum_vol_frac": 0.50,
         }):
        res_paced = _sync_get_technical_scan("momentum_and_volume", market="EGX")
        assert res_paced["status"] == "success"
        assert len(res_paced["stocks"]) == 3
        assert res_paced["stocks"][0]["r_vol"] > 1.15
        assert "معايرة السيولة" in (res_paced.get("scan_fallback_note_ar") or "")

    with patch("api.agentic_chat.tools_execution._get_sb", return_value=_MockScanSB("zero_today_prev_session")), \
         patch("api.agentic_chat.intraday_volume.get_exchange_session_state", return_value={
             "exchange": "EGX", "today_str": "2026-11-24", "is_trading_day": True,
             "is_live_session": True, "elapsed_min": 30, "session_len_min": 270,
             "progress_u": 0.11, "expected_cum_vol_frac": 0.16,
         }):
        res_prev = _sync_get_technical_scan("momentum_and_volume", market="EGX")
        assert res_prev["status"] == "success"
        assert len(res_prev["stocks"]) == 1
        assert res_prev["stocks"][0]["symbol"] == "FWRY"
        assert "2026-11-23" in (res_prev.get("scan_fallback_note_ar") or "")


# ---------------------------------------------------------------------------
# 4. Portfolio Profitable Counts & Intraday Bluechip Guard
# ---------------------------------------------------------------------------

def test_portfolio_view_profitable_counts_and_intraday_bluechip_guard() -> None:
    from api.agentic_chat.tools_execution import _build_portfolio_view_payload

    holdings = [
        {"symbol": "EFID", "quantity": 100, "entry_price": 18.0},
        {"symbol": "ETRS", "quantity": 100, "entry_price": 10.0},
        {"symbol": "SUGR", "quantity": 100, "entry_price": 50.0},
        {"symbol": "GBCO", "quantity": 100, "entry_price": 25.0},
    ]
    ind_rows = [
        {"symbol": "EFID", "date": "2026-11-24", "close": 19.01, "change_pct": 1.0, "r_vol": 0.01},
        {"symbol": "ETRS", "date": "2026-11-24", "close": 10.164, "change_pct": 0.5, "r_vol": 0.01},
        {"symbol": "SUGR", "date": "2026-11-24", "close": 50.24, "change_pct": 0.2, "r_vol": 0.01},
        {"symbol": "GBCO", "date": "2026-11-24", "close": 23.00, "change_pct": -1.0, "r_vol": 0.01},
    ]
    hist_rows = []
    for r in ind_rows:
        hist_rows.append({"symbol": r["symbol"], "date": "2026-11-24", "close": r["close"], "volume": 0})
        for d in range(23, 12, -1):
            hist_rows.append({"symbol": r["symbol"], "date": f"2026-11-{d:02d}", "close": r["close"], "volume": 600_000})

    class _MR:
        def __init__(self, data): self.data = data

    class _MQ:
        def __init__(self, tbl): self._tbl = tbl
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def in_(self, *_a): return self
        def order(self, *_a, **_kw): return self
        def limit(self, *_a): return self
        def execute(self):
            return {
                "stock_technical_indicators": _MR(ind_rows),
                "stock_scans_summary": _MR([]),
                "stock_fundamentals": _MR([{"symbol": r["symbol"], "fund_score": 72.0, "data": {"eps": 2.0}} for r in ind_rows]),
                "stock_prices": _MR(hist_rows),
            }.get(self._tbl, _MR([]))

    class _MSB:
        def from_(self, tbl): return _MQ(tbl)

    with patch("api.agentic_chat.tools_execution._resolve_symbol_and_market", side_effect=lambda s: (str(s).upper(), "EGX")), \
         patch("api.agentic_chat.tools_execution._lookup_upcoming_dividend", return_value=None), \
         patch("api.agentic_chat.intraday_volume.get_exchange_session_state", return_value={
             "exchange": "EGX", "today_str": "2026-11-24", "is_trading_day": True,
             "is_live_session": True, "elapsed_min": 41, "session_len_min": 270,
             "progress_u": 0.15, "expected_cum_vol_frac": 0.19,
         }):
        payload = _build_portfolio_view_payload(_MSB(), holdings, [], 1000.0)

    totals = payload["totals"]
    assert totals["profitable_positions_count"] == 3
    assert totals["losing_positions_count"] == 1
    assert totals["breakeven_positions_count"] == 0
    joined_winners = " ".join(totals["profitable_symbols"])
    assert "EFID" in joined_winners and "ETRS" in joined_winners and "SUGR" in joined_winners
    assert all(not pos["is_thin_liquidity"] for pos in payload["positions"])


# ---------------------------------------------------------------------------
# 5. Deterministic OR tradeSummary
# ---------------------------------------------------------------------------

def test_optimizer_trade_summary_matches_allocations_exactly() -> None:
    from api.portfolio_or_optimizer import AssetInput, optimize_portfolio_or

    assets = [
        AssetInput(symbol="EPPK", price=9.78, sector="صناعة", current_shares=1000.0, expected_score=-0.9, max_weight_override=0.0, exclusion_reason="مستبعد"),
        AssetInput(symbol="COMI", price=100.0, sector="بنوك", current_shares=0.0, expected_score=0.6),
        AssetInput(symbol="TMGH", price=60.0, sector="عقارات", current_shares=50.0, expected_score=0.5),
        AssetInput(symbol="ETRS", price=11.0, sector="نقل", current_shares=100.0, expected_score=0.55),
    ]
    res = optimize_portfolio_or(assets, total_capital=100000.0, max_weight_pct=35.0, min_cash_pct=10.0)
    ts = res["tradeSummary"]
    allocs = res["allocations"]
    exp_sell = round(sum(a["tradeValue"] for a in allocs if a["action"] == "SELL"), 2)
    exp_buy = round(sum(a["tradeValue"] for a in allocs if a["action"] == "BUY"), 2)
    assert ts["totalSellValue"] == exp_sell
    assert ts["totalBuyValue"] == exp_buy
    assert ts["sellCount"] == sum(1 for a in allocs if a["action"] == "SELL")
    assert ts["buyCount"] == sum(1 for a in allocs if a["action"] == "BUY")
    assert ts["holdCount"] == sum(1 for a in allocs if a["action"] == "HOLD")
    assert ts["netCashDelta"] == round(exp_sell - exp_buy, 2)


# ---------------------------------------------------------------------------
# 6. Scheduled Automations Snapshot Cache & Privacy Isolation
# ---------------------------------------------------------------------------

def test_automation_snapshot_cache_and_strict_per_user_isolation() -> None:
    from api import scheduled_automations_worker as worker

    worker._clear_automation_snapshot_cache()
    try:
        # Static system prompt must never embed mutable hour/day strings
        assert ":00" not in worker.AUTOMATION_STATIC_SYSTEM_PROMPT
        assert "2026-" not in worker.AUTOMATION_STATIC_SYSTEM_PROMPT

        calls = []

        def _fake_post(url, headers=None, json=None, timeout=None):
            calls.append(json)
            user_text = json["messages"][1]["content"]
            reply = "تقرير خاص للمستخدم A" if "محفظة A" in user_text else (
                "تقرير خاص للمستخدم B" if "محفظة B" in user_text else "تقرير محدث"
            )
            return SimpleNamespace(
                status_code=200,
                text="",
                json=lambda: {
                    "choices": [{"message": {"content": reply}}],
                    "usage": {"prompt_tokens": 500, "completion_tokens": 200, "prompt_cache_hit_tokens": 384},
                },
            )

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}), \
             patch.object(worker.requests, "post", side_effect=_fake_post):

            # User A identical portfolio snapshot x2 -> 1st live, 2nd RAM cache hit ($0.000)
            with patch.object(worker, "_fetch_market_indicators_brief", return_value="محفظة A | COMI=100.0"):
                out_a1 = worker._generate_ai_consultation("حلل محفظتي", "UserA", user_id="user-aaa-111")
                assert out_a1 == "تقرير خاص للمستخدم A"
                assert len(calls) == 1
                assert worker._AUTO_METRICS_TLS.last_cached is False

                out_a2 = worker._generate_ai_consultation("حلل محفظتي", "UserA", user_id="user-aaa-111")
                assert out_a2 == "تقرير خاص للمستخدم A"
                assert len(calls) == 1  # ZERO extra LLM calls!
                assert worker._AUTO_METRICS_TLS.last_cached is True
                assert worker._AUTO_METRICS_TLS.last_usage["cost_usd"] == 0.0
                assert "auto_snap_u_" in (worker._AUTO_METRICS_TLS.last_cache_key or "")

            # User B with DIFFERENT user_id MUST NEVER receive User A's cached portfolio reply
            with patch.object(worker, "_fetch_market_indicators_brief", return_value="محفظة B | COMI=100.0"):
                out_b = worker._generate_ai_consultation("حلل محفظتي", "UserB", user_id="user-bbb-222")
                assert out_b == "تقرير خاص للمستخدم B"
                assert len(calls) == 2

            # Even if User C had identical indicator brief text, separate user_id hash prevents cross-user hit
            with patch.object(worker, "_fetch_market_indicators_brief", return_value="محفظة A | COMI=100.0"):
                worker._generate_ai_consultation("حلل محفظتي", "UserC", user_id="user-ccc-333")
                assert len(calls) == 3

            # Price change for User A invalidates snapshot hash immediately
            with patch.object(worker, "_fetch_market_indicators_brief", return_value="محفظة A | COMI=102.5"):
                worker._generate_ai_consultation("حلل محفظتي", "UserA", user_id="user-aaa-111")
                assert len(calls) == 4
    finally:
        worker._clear_automation_snapshot_cache()


# ---------------------------------------------------------------------------
# 7. Telegram Relative Link Parity
# ---------------------------------------------------------------------------

def test_telegram_relative_markdown_links_rewritten_to_absolute() -> None:
    from api.telegram_vip_chat import format_pipeline_reply_for_telegram

    body = (
        "راجع [حاسبة التوافق الشرعي](/sharia) و [شاشة أسعار الأسهم المباشرة](/stocks)\n"
        "> يمكنك متابعة [شارت الأسهم اللحظي](/chart) وكذلك [تقويم التوزيعات](/dividends)"
    )
    html_out = format_pipeline_reply_for_telegram(
        reply_text=body,
        tables=[],
        user_name="أحمد",
        tg_user_id=123456,
        is_pro=True,
        used=5,
        limit=350,
        remaining=345,
        period="monthly",
    )
    assert '<a href="https://egxbots.com/sharia">حاسبة التوافق الشرعي</a>' in html_out
    assert '<a href="https://egxbots.com/stocks">شاشة أسعار الأسهم المباشرة</a>' in html_out
    assert '<a href="https://egxbots.com/chart">شارت الأسهم اللحظي</a>' in html_out
    assert '<a href="https://egxbots.com/dividends">تقويم التوزيعات</a>' in html_out
    assert "](/sharia)" not in html_out
    assert "](/chart)" not in html_out


# ---------------------------------------------------------------------------
# 8. Pipeline Degraded Scan Cache Guard & Standalone Multi-Turn / Preset Fast-Track
# ---------------------------------------------------------------------------

def test_pipeline_degraded_scan_blocks_cache_and_fast_track_skips_tools() -> None:
    from api.agentic_chat.pipeline import _tool_result_is_degraded_scan, run_agentic_chat_stream

    assert _tool_result_is_degraded_scan("get_technical_scan", {"status": "success", "stocks": []}) is True
    assert _tool_result_is_degraded_scan("get_accumulation_stocks", {"status": "success", "stocks": [], "accumulation_stocks": []}) is True
    assert _tool_result_is_degraded_scan("get_technical_scan", {"status": "error", "message": "err"}) is True
    assert _tool_result_is_degraded_scan("get_technical_scan", {"status": "success", "stocks": [{"symbol": "MTIE"}]}) is False

    captured_requests = []
    cache_writes = []

    class _FakeHttpResp:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [{"message": {"content": "تحليل فني من مسار Fast-Track بسعر 104.5 ج.م."}}],
                "usage": {"prompt_tokens": 1200, "completion_tokens": 80, "prompt_cache_hit_tokens": 1000},
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            captured_requests.append(json)
            return _FakeHttpResp()

    async def _fake_dispatch(tool_name, tool_args, user_id=None, user_prompt="", default_market="EGX"):
        if tool_name == "get_stock":
            return {"status": "success", "stocks": [{"symbol": "COMI", "close": 104.5, "currency": "ج.م"}]}
        if tool_name == "get_accumulation_stocks":
            return {"status": "success", "stocks": [{"symbol": "CRST"}], "accumulation_stocks": [{"symbol": "CRST"}]}
        if tool_name == "get_technical_scan":
            return {"status": "success", "stocks": []}  # Degraded empty scan
        return {"status": "success"}

    async def _run_case(msg: str, history):
        events = []
        async for chunk in run_agentic_chat_stream(
            message=msg,
            history=history,
            market="EGX",
            user_id="00000000-0000-0000-0000-000000000000",
        ):
            if chunk.startswith("data:") and "[DONE]" not in chunk:
                events.append(json.loads(chunk[5:].strip()))
        return events

    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}), \
         patch("api.agentic_chat.pipeline.get_vip_analysis_cache", return_value=None), \
         patch("api.agentic_chat.pipeline.set_vip_analysis_cache", side_effect=lambda **kw: cache_writes.append(kw)), \
         patch("api.agentic_chat.pipeline.dispatch_tool", side_effect=_fake_dispatch), \
         patch("api.agentic_chat.pipeline.httpx.AsyncClient", _FakeAsyncClient):

        # Case A: Canonical preset `vip_accumulation` with empty `get_technical_scan` -> Fast-Track (no tools schema) & NO cache write
        ev_a = asyncio.run(_run_case(
            "أقوى أسهم التجميع والسيولة الذكية اليوم",
            [{"role": "user", "content": "مرحبا"}, {"role": "assistant", "content": "أهلاً بك"}],
        ))
        assert len(captured_requests) == 1
        assert "tools" not in captured_requests[0]
        assert len(cache_writes) == 0
        assert any(e.get("type") == "done" and e.get("cache_key") is None for e in ev_a)

        # Case B: Bare stock ticker inside an ongoing conversation -> Single-Stock Fast-Track (1 LLM call, no tools, caches cleanly)
        captured_requests.clear()
        cache_writes.clear()
        ev_b = asyncio.run(_run_case(
            "COMI",
            [{"role": "user", "content": "حلل فوري"}, {"role": "assistant", "content": "إليك تحليل فوري السابق"}],
        ))
        assert len(captured_requests) == 1
        assert "tools" not in captured_requests[0]
        assert len(cache_writes) == 1
        assert cache_writes[0]["cache_key"] == "vip_stock_COMI"
        assert any(e.get("type") == "done" and e.get("cache_key") == "vip_stock_COMI" for e in ev_b)


# ---------------------------------------------------------------------------
# 9. HF Sync Manifest Registration
# ---------------------------------------------------------------------------

def test_hf_sync_manifest_includes_intraday_volume() -> None:
    from scripts.sync_to_hf_space import FILES_TO_SYNC

    assert "api/agentic_chat/intraday_volume.py" in FILES_TO_SYNC


def test_qa_regressions_dialect_privacy_zero_prev_vol_and_optimizer_parity() -> None:
    """Verify QA edge cases: Arabic ى/ي privacy detection, prev_vol=0 no contradiction, & optimizer parity."""
    from api import scheduled_automations_worker as worker
    from api.agentic_chat.intraday_volume import resolve_intraday_r_vol
    from api.agentic_chat.tools_execution import _assess_stock_liquidity

    # 1. Alef maqsura & English portfolio keywords must NEVER be classified as public cacheable
    for priv in ("حلل محفظتى", "مراجعة اسهمى اليوم", "وضع مركزى الحالى", "portfolio review"):
        assert worker._is_cacheable_automation_prompt(priv) is False

    # Even with a generic prompt, if indicators_brief contains personal portfolio block OR personal task_name,
    # snapshot MUST stay strictly private (`auto_snap_u_...`) and public prompts anonymize `user_name`.
    worker._clear_automation_snapshot_cache()
    try:
        captured = []

        def _fake_post(url, headers=None, json=None, timeout=None):
            captured.append(json)
            return SimpleNamespace(
                status_code=200,
                text="",
                json=lambda: {
                    "choices": [{"message": {"content": "رد تحليلي"}}],
                    "usage": {"prompt_tokens": 400, "completion_tokens": 100, "prompt_cache_hit_tokens": 300},
                },
            )

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}), \
             patch.object(worker.requests, "post", side_effect=_fake_post):

            with patch.object(
                worker,
                "_fetch_market_indicators_brief",
                return_value="💼 محفظة المشترك المسجلة حالياً:\n• #COMI: 100 سهم",
            ):
                worker._generate_ai_consultation("تابع السوق", "تقرير المحفظة", user_id="u-priv-1")
                assert "auto_snap_u_" in (worker._AUTO_METRICS_TLS.last_cache_key or "")

            # Generic public prompt must NOT embed User A's display name in user_content
            worker._clear_automation_snapshot_cache()
            with patch.object(worker, "_fetch_market_indicators_brief", return_value="• #COMI: 100"):
                worker._generate_ai_consultation("وضع سهم COMI", "SecretRealName", user_id="u-pub-1")
                assert "SecretRealName" not in captured[-1]["messages"][1]["content"]
                assert "مشترك Pro" in captured[-1]["messages"][1]["content"]
    finally:
        worker._clear_automation_snapshot_cache()

    # 2. High 20d avg volume + zero yesterday volume + live unpopulated volume -> intraday_unavailable (no 0.00x contradiction)
    cairo_tz = ZoneInfo("Africa/Cairo")
    t_1041 = dt.datetime(2026, 11, 24, 10, 41, tzinfo=cairo_tz)
    hist_zero_yday = (
        [{"date": "2026-11-24", "volume": 0}, {"date": "2026-11-23", "volume": 0}]
        + [{"date": f"2026-11-{d:02d}", "volume": 500_000} for d in range(22, 12, -1)]
    )
    res_z = resolve_intraday_r_vol(0.0, "2026-11-24", exchange="EGX", ohlcv_rows=hist_zero_yday, now_dt=t_1041)
    assert res_z["r_vol_mode"] == "intraday_unavailable"
    assert res_z["effective_r_vol"] is None
    assert "0.00x يمثل" not in (res_z.get("r_vol_note_ar") or "")

    # 3. Shared _assess_stock_liquidity keeps blue-chip intraday COMI liquid (not capped at 15% in optimizer)
    hist_comi = [{"date": "2026-11-24", "volume": 0}] + [
        {"date": f"2026-11-{d:02d}", "volume": 1_500_000} for d in range(23, 12, -1)
    ]
    with patch("api.agentic_chat.intraday_volume.get_exchange_session_state", return_value={
        "exchange": "EGX", "today_str": "2026-11-24", "is_trading_day": True,
        "is_live_session": True, "elapsed_min": 41, "session_len_min": 270,
        "progress_u": 0.15, "expected_cum_vol_frac": 0.19,
    }):
        liq = _assess_stock_liquidity(hist_comi, {"r_vol": 0.01, "date": "2026-11-24"}, 100.0, "EGX")
        assert liq["is_illiquid"] is False
        assert liq["is_thin_liquidity"] is False


# ---------------------------------------------------------------------------
# 10. Multi-Market Registry Schedule, Liquidity Thresholds & Automations
# ---------------------------------------------------------------------------

def test_intraday_volume_uses_market_registry_schedules_and_skips_commodities() -> None:
    from api.agentic_chat.intraday_volume import get_exchange_session_state, resolve_intraday_r_vol

    dubai_tz = ZoneInfo("Asia/Dubai")
    t_1450_dxb = dt.datetime(2026, 11, 24, 14, 50, tzinfo=dubai_tz)  # Tuesday 14:50 Dubai (< 15:00 close)
    t_1505_dxb = dt.datetime(2026, 11, 24, 15, 5, tzinfo=dubai_tz)
    for exch in ("DFM", "ADX"):
        s_live = get_exchange_session_state(exch, now_dt=t_1450_dxb)
        assert s_live["is_live_session"] is True
        assert s_live["close_min"] == 15 * 60
        s_closed = get_exchange_session_state(exch, now_dt=t_1505_dxb)
        assert s_closed["is_live_session"] is False

    kuwait_tz = ZoneInfo("Asia/Kuwait")
    t_1200_kw = dt.datetime(2026, 11, 24, 12, 0, tzinfo=kuwait_tz)
    s_kw = get_exchange_session_state("KSE", now_dt=t_1200_kw)
    assert s_kw["is_live_session"] is True
    assert s_kw["close_min"] == 12 * 60 + 40

    utc_now = dt.datetime(2026, 11, 24, 14, 0, tzinfo=dt.timezone.utc)
    hist_gold = [{"date": f"2026-11-{d:02d}", "volume": 120_000} for d in range(24, 10, -1)]
    res_gold = resolve_intraday_r_vol(
        0.52,
        "2026-11-24",
        exchange="COMMODITIES",
        ohlcv_rows=hist_gold,
        now_dt=utc_now,
    )
    assert res_gold["r_vol_mode"] == "eod"
    assert res_gold["effective_r_vol"] == 0.52
    assert res_gold["is_intraday_adjusted"] is False


def test_assess_stock_liquidity_currency_appropriate_gcc_vs_egx() -> None:
    from api.agentic_chat.tools_execution import _assess_stock_liquidity

    live_hist = [{"date": "2026-11-24", "volume": 0}]

    # Saudi/QSE/DFM/ADX blue-chip: avg_turnover_10 = 600,000 SAR/QAR/AED (>= 500k bluechip protection)
    hist_600k = live_hist + [{"date": f"2026-11-{d:02d}", "volume": 20_000} for d in range(23, 12, -1)]
    # Saudi/GCC illiquid stock: avg_turnover_10 = 3,000 SAR/QAR/AED (< 5k floor)
    hist_3k = live_hist + [{"date": f"2026-11-{d:02d}", "volume": 300} for d in range(23, 12, -1)]

    with patch("api.agentic_chat.intraday_volume.get_exchange_session_state", return_value={
        "exchange": "TADAWUL", "today_str": "2026-11-24", "is_trading_day": True,
        "is_live_session": True, "elapsed_min": 120, "session_len_min": 300,
        "progress_u": 0.4, "expected_cum_vol_frac": 0.42,
    }):
        for exch in ("TADAWUL", "QSE", "DFM", "ADX"):
            liq_ok = _assess_stock_liquidity(hist_600k, {"r_vol": 0.15, "date": "2026-11-24"}, 30.0, exch)
            assert liq_ok["is_illiquid"] is False
            assert liq_ok["is_thin_liquidity"] is False

            liq_bad = _assess_stock_liquidity(hist_3k, {"r_vol": 0.15, "date": "2026-11-24"}, 10.0, exch)
            assert liq_bad["is_illiquid"] is True
            assert liq_bad["is_thin_liquidity"] is True

    # EGX preserves exact 50k / 1.5M / 5M EGP thresholds
    with patch("api.agentic_chat.intraday_volume.get_exchange_session_state", return_value={
        "exchange": "EGX", "today_str": "2026-11-24", "is_trading_day": True,
        "is_live_session": True, "elapsed_min": 120, "session_len_min": 270,
        "progress_u": 0.44, "expected_cum_vol_frac": 0.46,
    }):
        hist_egx_40k = live_hist + [{"date": f"2026-11-{d:02d}", "volume": 4_000} for d in range(23, 12, -1)]
        hist_egx_600k = live_hist + [{"date": f"2026-11-{d:02d}", "volume": 60_000} for d in range(23, 12, -1)]
        # With today's 0-vol bar included in [:10], 60,000 * 9 / 10 * 100 = 5,400,000 EGP (>= 5M bluechip floor)
        hist_egx_5_4m = live_hist + [{"date": f"2026-11-{d:02d}", "volume": 60_000} for d in range(23, 12, -1)]

        assert _assess_stock_liquidity(hist_egx_40k, {"r_vol": 0.60, "date": "2026-11-24"}, 10.0, "EGX")["is_illiquid"] is True
        assert _assess_stock_liquidity(hist_egx_600k, {"r_vol": 0.60, "date": "2026-11-24"}, 10.0, "EGX")["is_thin_liquidity"] is True
        liq_egx_big = _assess_stock_liquidity(hist_egx_5_4m, {"r_vol": 0.15, "date": "2026-11-24"}, 100.0, "EGX")
        assert liq_egx_big["is_illiquid"] is False
        assert liq_egx_big["is_thin_liquidity"] is False


def test_scheduled_automations_multi_market_detection_routing_and_fallback() -> None:
    from api import scheduled_automations_worker as worker

    # 1. Market auto-detection
    assert worker._detect_automation_market("حلل لي سهم 2222") == "TADAWUL"
    assert worker._detect_automation_market("تقرير السوق السعودي") == "TADAWUL"
    assert worker._detect_automation_market("تابع أرامكو والراجحي") == "TADAWUL"
    assert worker._detect_automation_market("تحليل QNBK.QA") == "QSE"
    assert worker._detect_automation_market("أفضل أسهم قطر") == "QSE"
    assert worker._detect_automation_market("متابعة إعمار في دبي") == "DFM"
    assert worker._detect_automation_market("سوق أبوظبي") == "ADX"
    assert worker._detect_automation_market("تحديث سعر الذهب اليوم") == "COMMODITIES"
    assert worker._detect_automation_market("حلل لي COMI بمبلغ 2000 جنيه") == "EGX"
    assert worker._detect_automation_market("تقرير 2026 للبورصة المصرية") == "EGX"
    assert worker._detect_automation_market("مؤشر EGX70 عند 8550") == "EGX"

    # 2. End-to-end Saudi consultation routes via _market_supabase_request(exchange="TADAWUL") with base-safe GCC fallback
    seen_market_calls = []
    seen_guard_markets = []
    captured_llm_payloads = []

    def _fake_market_req(endpoint: str, exchange: str = "EGX", **_kw):
        seen_market_calls.append((exchange, endpoint))
        if endpoint.startswith("stocks?"):
            return [{"symbol": "2222", "name": "Saudi Aramco", "name_ar": "أرامكو السعودية"}]
        if endpoint.startswith("stock_technical_indicators?") and "king_ai_score" in endpoint:
            # Simulate dedicated Saudi DB missing optional rich columns (returns None -> must fall back to base-safe cols)
            return None
        if endpoint.startswith("stock_technical_indicators?"):
            return [
                {
                    "symbol": "2222",
                    "updated_at": "2026-11-24T12:00:00Z",
                    "close": 28.45,
                    "change_pct": 1.25,
                    "volume": 12_000_000,
                    "volume_sma_20": 10_000_000,
                    "rsi_14": 57.5,
                    "ema_50": 27.90,
                    "ema_200": 27.10,
                    "atr_14": 0.45,
                }
            ]
        if endpoint.startswith("stock_fundamentals?"):
            return [{"symbol": "2222", "fund_score": 82, "data": {"eps": 1.65}}]
        return []

    def _fake_guard(text: str, *, market: str = "EGX") -> str:
        seen_guard_markets.append(market)
        return text

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured_llm_payloads.append(json)
        return SimpleNamespace(
            status_code=200,
            text="",
            json=lambda: {
                "choices": [{"message": {"content": "تقرير أرامكو السعودية (#2222) عند 28.45 ر.س."}}],
                "usage": {"prompt_tokens": 500, "completion_tokens": 120, "prompt_cache_hit_tokens": 384},
            },
        )

    worker._clear_automation_snapshot_cache()
    worker._cached_market_stocks.clear()
    try:
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}), \
             patch.object(worker, "_market_supabase_request", side_effect=_fake_market_req), \
             patch.object(worker, "_supabase_request", side_effect=AssertionError("Must NOT hit primary EGX DB for Saudi market reads")), \
             patch.object(worker, "_guard_automation_reply", side_effect=_fake_guard), \
             patch.object(worker.requests, "post", side_effect=_fake_post):

            out_sa = worker._generate_ai_consultation("حلل لي سهم 2222", "تقرير تاسي", user_id="u-sa-1")
            assert "28.45 ر.س" in out_sa
            assert any(ex == "TADAWUL" and "stock_technical_indicators" in ep for ex, ep in seen_market_calls)
            assert any(ex == "TADAWUL" and "momentum_10" in ep for ex, ep in seen_market_calls)
            assert seen_guard_markets == ["TADAWUL"]

            user_prompt_sent = captured_llm_payloads[0]["messages"][1]["content"]
            sys_prompt_sent = captured_llm_payloads[0]["messages"][0]["content"]
            assert sys_prompt_sent == worker.AUTOMATION_STATIC_SYSTEM_PROMPT
            assert "السعودي" in user_prompt_sent
            assert "28.45 ر.س" in user_prompt_sent
            assert "ج.م" not in user_prompt_sent.split("طلب الاستشارة")[1]

            sa_snap_key = worker._AUTO_METRICS_TLS.last_cache_key
            assert sa_snap_key is not None

            # Calling again hits RAM snapshot cache with zero extra LLM calls
            out_sa_cached = worker._generate_ai_consultation("حلل لي سهم 2222", "تقرير تاسي", user_id="u-sa-1")
            assert out_sa_cached == out_sa
            assert len(captured_llm_payloads) == 1
            assert worker._AUTO_METRICS_TLS.last_cached is True
    finally:
        worker._clear_automation_snapshot_cache()
        worker._cached_market_stocks.clear()
