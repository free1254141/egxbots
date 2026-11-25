"""Deterministic regression tests for the 2026-11-24 bcd522ec forensic chat audit fixes."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from api.agentic_chat.analysis_cache import (
    build_analysis_cache_key,
    resolve_tool_calls_to_cache_key,
)
from api.agentic_chat.output_guard import verify_and_guard_reply
from api.agentic_chat.tools_execution import (
    _compute_fundamental_fair_value,
    _dividend_entitlement_rule_ar,
    _sync_get_fair_value,
    dispatch_tool,
)
from api.daily_bot_run import _adjust_df_for_unadjusted_splits
from api.portfolio_or_optimizer import AssetInput, optimize_portfolio_or
from api.routers.offload_public import _compute_single_fair_value
from api.scheduled_automations_worker import (
    _guard_automation_reply,
    _log_automation_to_chat_history,
)


def test_optimizer_excludes_zero_volume_or_loss_asset_and_forces_sell_when_held() -> None:
    """Excluded asset (`max_weight_override=0.0`) must receive 0% weight and SELL when currently held."""
    rng = np.random.default_rng(42)
    dates = [f"2026-10-{d:02d}" for d in range(1, 21)]

    def _mk_ret(mu: float, sig: float) -> dict[str, float]:
        vals = rng.normal(mu, sig, size=len(dates))
        return {dt: float(v) for dt, v in zip(dates, vals)}

    assets = [
        AssetInput(
            symbol="EPPK",
            price=9.78,
            name_ar="الورق للشرق الأوسط",
            sector="صناعة ومواد",
            current_shares=1000.0,
            expected_score=-0.85,
            fallback_daily_vol=0.032,
            returns_by_date=_mk_ret(-0.002, 0.025),
            max_weight_override=0.0,
            exclusion_reason="سيولة شبه منعدمة وخسائر صافية — مستبعد من الشراء",
        ),
        AssetInput(
            symbol="COMI",
            price=100.0,
            name_ar="التجاري الدولي",
            sector="بنوك",
            current_shares=0.0,
            expected_score=0.55,
            fallback_daily_vol=0.018,
            returns_by_date=_mk_ret(0.002, 0.015),
        ),
        AssetInput(
            symbol="TMGH",
            price=60.0,
            name_ar="طلعت مصطفى",
            sector="عقارات",
            current_shares=0.0,
            expected_score=0.50,
            fallback_daily_vol=0.020,
            returns_by_date=_mk_ret(0.002, 0.017),
        ),
        AssetInput(
            symbol="ETEL",
            price=40.0,
            name_ar="المصرية للاتصالات",
            sector="اتصالات",
            current_shares=0.0,
            expected_score=0.45,
            fallback_daily_vol=0.019,
            returns_by_date=_mk_ret(0.0015, 0.016),
        ),
    ]

    result = optimize_portfolio_or(
        assets,
        total_capital=100000.0,
        objective="balanced",
        max_weight_pct=35.0,
        max_sector_pct=45.0,
        min_cash_pct=10.0,
    )
    by_sym = {row["symbol"]: row for row in result["allocations"]}
    eppk = by_sym["EPPK"]
    assert eppk["targetWeightPct"] == 0.0
    assert eppk["actualWeightPct"] == 0.0
    assert eppk["targetShares"] == 0
    assert eppk["action"] == "SELL"
    assert "سيولة" in eppk["exclusionReason"]

    total_actual_weight = sum(row["actualWeightPct"] for row in result["allocations"])
    assert total_actual_weight <= 90.5
    assert result["leftoverCashPct"] >= 9.5


def test_optimizer_marks_unheld_excluded_asset_as_skip() -> None:
    """Unheld excluded asset must receive targetWeightPct == 0.0 and action == SKIP."""
    assets = [
        AssetInput(
            symbol="EPPK",
            price=9.78,
            sector="صناعة",
            current_shares=0.0,
            expected_score=-0.85,
            max_weight_override=0.0,
            exclusion_reason="مستبعد لضعف السيولة",
        ),
        AssetInput(symbol="COMI", price=80.0, sector="بنوك", expected_score=0.5),
        AssetInput(symbol="TMGH", price=55.0, sector="عقارات", expected_score=0.4),
        AssetInput(symbol="ETEL", price=35.0, sector="اتصالات", expected_score=0.35),
    ]
    result = optimize_portfolio_or(assets, total_capital=100000.0, max_weight_pct=35.0, min_cash_pct=10.0)
    by_sym = {row["symbol"]: row for row in result["allocations"]}
    assert by_sym["EPPK"]["action"] == "SKIP"
    assert by_sym["EPPK"]["targetWeightPct"] == 0.0


def test_distressed_loss_making_fair_value_parity_website_and_chat() -> None:
    """Loss-making stocks with high BVPS must receive discounted pb_distressed fair value <= 0.98 * close."""
    close = 9.78
    fund_data = {
        "eps": -0.69,
        "netIncome": -45_000_000,
        "roe": -8.2,
        "bookValuePerShare": 15.0,
        "sector": "Materials",
        "industry": "Paper & Forest Products",
    }

    web_row = _compute_single_fair_value(
        symbol="EPPK",
        close=close,
        fund_row={"symbol": "EPPK", "data": fund_data},
        ind={"ema_200": 10.2, "vwap_20": 9.8},
        sector_median_pe=10.0,
        sector_median_pb=1.5,
        market="egx",
    )
    assert web_row["modelType"] == "pb_distressed"
    assert web_row["fairValue"] <= round(close * 0.98, 2)
    assert web_row["fairValue"] >= round(close * 0.45, 2)
    assert web_row["upsidePct"] < 0

    chat_fv, chat_model, chat_extra = _compute_fundamental_fair_value(
        close=close,
        vwap=9.8,
        ema=10.0,
        fd=fund_data,
        market="EGX",
    )
    assert chat_model == "قيمة دفترية مخفضة (شركة خاسرة)"
    assert chat_extra.get("loss_making_discount_applied") is True
    assert chat_fv <= round(close * 0.98, 2)
    assert chat_fv >= round(close * 0.45, 2)


def test_dispatch_fair_value_accepts_singular_symbol() -> None:
    """dispatch_tool('get_fair_value', {'symbol': 'COSG'}) should forward symbols=['COSG']."""
    import asyncio

    captured: dict[str, object] = {}

    async def _fake_exec_fv(**kwargs):
        captured.update(kwargs)
        return {"status": "success", "fair_value_stocks": []}

    with patch("api.agentic_chat.tools_execution.execute_get_fair_value", side_effect=_fake_exec_fv):
        res = asyncio.run(dispatch_tool("get_fair_value", {"symbol": "COSG"}, default_market="EGX"))

    assert res["status"] == "success"
    assert captured["symbols"] == ["COSG"]


def test_sync_get_fair_value_filters_symbol_before_order_limit() -> None:
    """EGX fair value query must call .in_('symbol', ...) before .order().limit()."""
    call_log: list[tuple[str, object]] = []

    class _MockQuery:
        def __init__(self, table_name: str) -> None:
            self.table_name = table_name

        def select(self, cols: str):
            call_log.append((f"{self.table_name}.select", cols))
            return self

        def eq(self, col: str, val: object):
            call_log.append((f"{self.table_name}.eq", (col, val)))
            return self

        def in_(self, col: str, vals: list[str]):
            call_log.append((f"{self.table_name}.in_", (col, list(vals))))
            return self

        def order(self, col: str, desc: bool = False):
            call_log.append((f"{self.table_name}.order", (col, desc)))
            return self

        def limit(self, n: int):
            call_log.append((f"{self.table_name}.limit", n))
            return self

        def execute(self):
            if self.table_name == "stock_technical_indicators":
                return SimpleNamespace(
                    data=[{"symbol": "COSG", "close": 1.28, "vwap_20": 1.27, "ema_50": 1.26, "ema_200": 1.30, "date": "2026-11-23"}]
                )
            if self.table_name == "stock_fundamentals":
                return SimpleNamespace(data=[{"symbol": "COSG", "data": {"eps": -0.15, "bookValuePerShare": 2.4}}])
            return SimpleNamespace(data=[])

    class _MockSB:
        def from_(self, name: str):
            return _MockQuery(name)

    with patch("api.agentic_chat.tools_execution._get_sb", return_value=_MockSB()):
        res = _sync_get_fair_value(symbols=["COSG"], market="EGX")

    assert res["status"] == "success"
    assert len(res["fair_value_stocks"]) == 1
    assert res["fair_value_stocks"][0]["fair_value"] <= round(1.28 * 0.98, 2)

    names = [c[0] for c in call_log]
    assert "stock_technical_indicators.in_" in names
    in_idx = names.index("stock_technical_indicators.in_")
    order_idx = names.index("stock_technical_indicators.order")
    limit_idx = names.index("stock_technical_indicators.limit")
    assert in_idx < order_idx < limit_idx


def test_ex_date_entitlement_rule_and_output_guard_sanitizer() -> None:
    """Verify deterministic Ex-Date explanation and output_guard catching inversions, typos, and leaks."""
    rule_txt = _dividend_entitlement_rule_ar("2026-11-26", "2026-11-25")
    assert "2026-11-26" in rule_txt
    assert "2026-11-25" in rule_txt
    assert "يستحق الكوبون كاملاً حتى لو باع أسهمه في يوم الـ Ex-Date نفسه" in rule_txt
    assert "تاريخ التسجيل" in rule_txt and "وليس آخر يوم للشراء أو البيع" in rule_txt

    bad_reply = (
        "يوم Ex-Date (2026-11-26): ← البيع هنا = بدون كوبون. "
        "السيولة السيولة النسبية مرتفعة عند `السيولة النسبية` 2.1x مع distribution_score = 45 "
        "وتطبيق الضريبة الشرعية باستخدام risk_parity و max_diversification و dist_score."
    )
    guarded = verify_and_guard_reply(bad_reply, [], market="EGX")
    out = guarded["reply"]
    assert "ex_date_rule_inverted_corrected" in guarded["warnings"]
    assert "sharia_typo_fixed" in guarded["warnings"]
    assert guarded["block_cache"] is True
    assert "البيع هنا = بدون كوبون" not in out
    assert "السيولة السيولة النسبية" not in out
    assert "`السيولة النسبية`" not in out
    assert "الضريبة الشرعية" not in out
    assert "الضوابط الشرعية" in out
    for leaked in ("distribution_score", "risk_parity", "max_diversification", "dist_score"):
        assert leaked not in out


def test_vip_cache_keys_and_tool_batch_resolution() -> None:
    """Verify CRST/COSG/EPPK, market phrases, and parallel sharia/dividends batch cache key normalization."""
    assert build_analysis_cache_key("حلل سهم CRST", market="EGX") == "vip_stock_CRST"
    assert build_analysis_cache_key("تقييم سهم COSG", market="EGX") == "vip_stock_COSG"
    assert build_analysis_cache_key("سعر سهم EPPK", market="EGX") == "vip_stock_EPPK"
    assert build_analysis_cache_key("تحليل السوق الان", market="EGX") == "vip_market_summary"
    assert build_analysis_cache_key("التوصيات المفتوحة حالياً", market="EGX") == "vip_open_recommendations"

    default_batch = [
        {"function": {"name": "get_stock", "arguments": '{"symbols": ["CRST"]}'}},
        {"function": {"name": "get_sharia_cleanser", "arguments": '{"symbol": "CRST"}'}},
        {"function": {"name": "get_dividends", "arguments": '{"symbol": "CRST"}'}},
    ]
    assert resolve_tool_calls_to_cache_key(default_batch) == "vip_stock_CRST"

    custom_shares_batch = [
        {"function": {"name": "get_stock", "arguments": '{"symbols": ["CRST"]}'}},
        {"function": {"name": "get_sharia_cleanser", "arguments": '{"symbol": "CRST", "shares_count": 500}'}},
    ]
    assert resolve_tool_calls_to_cache_key(custom_shares_batch) is None


def test_daily_bot_run_adjusts_4_to_1_corporate_split() -> None:
    """Synthetic 4:1 unadjusted split (40 -> 10) must rebase prior prices by 0.25 and volume by 4x."""
    n_pre = 220
    n_post = 30
    dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(n_pre + n_post)]
    closes = [40.0] * n_pre + [10.0] * n_post
    vols = [100_000.0] * n_pre + [400_000.0] * n_post
    df = pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.02 for c in closes],
            "low": [c * 0.98 for c in closes],
            "close": closes,
            "volume": vols,
        },
        index=pd.DatetimeIndex(dates, name="date"),
    )
    adj = _adjust_df_for_unadjusted_splits(df)
    assert float(adj["close"].iloc[0]) == pytest.approx(10.0, rel=1e-4)
    assert float(adj["volume"].iloc[0]) == pytest.approx(400_000.0, rel=1e-4)
    ema50 = float(adj["close"].ewm(span=50, adjust=False).mean().iloc[-1])
    ema200 = float(adj["close"].ewm(span=200, adjust=False).mean().iloc[-1])
    assert 9.5 <= ema50 <= 10.5
    assert 9.5 <= ema200 <= 10.5


def test_scheduled_automation_guard_and_timestamp_offset() -> None:
    """_guard_automation_reply must sanitize leaks/Ex-Date and assistant log timestamp must be strictly +1s."""
    raw = "السهم لديه `r_vol` = 1.4x و dist_score = 30. البيع هنا = بدون كوبون في Ex-Date الكوبون."
    cleaned = _guard_automation_reply(raw)
    assert "r_vol" not in cleaned
    assert "dist_score" not in cleaned
    assert "البيع هنا = بدون كوبون" not in cleaned

    posted: list[tuple[str, dict]] = []

    def _fake_req(path: str, method: str = "GET", payload=None, extra_headers=None):
        posted.append((path, dict(payload or {})))
        return []

    user_iso = "2026-11-24T08:30:00+00:00"
    with patch("api.scheduled_automations_worker._supabase_request", side_effect=_fake_req):
        _log_automation_to_chat_history(
            auto_id="11111111-1111-1111-1111-111111111111",
            user_id="22222222-2222-2222-2222-222222222222",
            name="صباح الخير",
            prompt="حلل محفظتي",
            reply_text="تحليل منضبط",
            now_iso=user_iso,
            latency_ms=420,
        )

    msgs = [p for path, p in posted if path == "ai_chat_messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user" and msgs[0]["created_at"] == user_iso
    assert msgs[1]["role"] == "assistant"
    t_u = datetime.fromisoformat(msgs[0]["created_at"])
    t_a = datetime.fromisoformat(msgs[1]["created_at"])
    assert (t_a - t_u).total_seconds() == pytest.approx(1.0, abs=1e-6)


def test_market_news_batch_and_canonical_standalone_cache() -> None:
    """Parallel get_market + market-wide get_news resolves to vip_market_summary without breaking PHDC guard."""
    from api.agentic_chat.pipeline import _is_unambiguous_standalone_input

    market_news_batch = [
        {"function": {"name": "get_market", "arguments": '{"market": "EGX"}'}},
        {"function": {"name": "get_news", "arguments": '{"market": "EGX"}'}},
    ]
    assert resolve_tool_calls_to_cache_key(market_news_batch) == "vip_market_summary"

    single_stock_news_batch = [
        {"function": {"name": "get_market", "arguments": '{"market": "EGX"}'}},
        {"function": {"name": "get_news", "arguments": '{"symbol": "COMI"}'}},
    ]
    assert resolve_tool_calls_to_cache_key(single_stock_news_batch) is None

    assert _is_unambiguous_standalone_input("تحليل السوق الان", market="EGX") is True
    assert _is_unambiguous_standalone_input("CRST", market="EGX") is True
    assert _is_unambiguous_standalone_input("حلل سهم PHDC", market="EGX") is False

    market_pulse_traps_batch = [
        {"function": {"name": "get_market", "arguments": '{"market": "EGX"}'}},
        {"function": {"name": "get_recommendations", "arguments": '{"market": "EGX", "status": "open", "timeframe": "this_week", "limit": 10}'}},
        {"function": {"name": "get_accumulation_stocks", "arguments": '{"market": "EGX"}'}},
        {"function": {"name": "get_price_traps", "arguments": '{"market": "EGX", "trap_type": "all"}'}},
    ]
    assert resolve_tool_calls_to_cache_key(market_pulse_traps_batch) == "vip_market_pulse_and_recs"

    last_week_rejected = [
        {"function": {"name": "get_recommendations", "arguments": '{"timeframe": "last_week"}'}},
        {"function": {"name": "get_technical_scan", "arguments": "{}"}},
    ]
    assert resolve_tool_calls_to_cache_key(last_week_rejected) is None


def test_fetch_market_indicators_brief_uses_valid_columns_and_deterministic_tags() -> None:
    """_fetch_market_indicators_brief must never request nonexistent TI columns and emits deterministic tags."""
    from api.scheduled_automations_worker import _fetch_market_indicators_brief

    seen_paths: list[str] = []

    def _fake_req(path: str, method: str = "GET", payload=None, extra_headers=None):
        seen_paths.append(path)
        if path.startswith("stocks?"):
            return [
                {"symbol": "INEG", "name_ar": "المتكاملة للهندسة"},
                {"symbol": "AIDC", "name_ar": "العربية للتنمية"},
            ]
        if path.startswith("stock_technical_indicators?"):
            assert "support_1" not in path
            assert "resistance_1" not in path
            assert "stop_loss" not in path
            return [
                {
                    "symbol": "INEG",
                    "date": "2026-11-23",
                    "close": 0.397,
                    "change_pct": -1.0,
                    "volume": 5000000,
                    "r_vol": 0.83,
                    "rsi_14": 57.5,
                    "ema_20": 0.382,
                    "ema_50": 0.376,
                    "ema_200": 0.462,
                    "bb_upper": 0.425,
                    "bb_lower": 0.365,
                    "atr_14": 0.015,
                    "egx_ai_score": 0.65,
                }
            ]
        if path.startswith("stock_fundamentals?"):
            return [{"symbol": "INEG", "fund_score": 35, "data": {"eps": -0.04}}]
        if path.startswith("scan_results?"):
            return [{"symbol": "INEG", "stop_loss": 0.331}]
        return []

    with patch("api.scheduled_automations_worker._supabase_request", side_effect=_fake_req):
        brief = _fetch_market_indicators_brief(["INEG"], prompt="تابع سهم INEG", in_trading_hours=False)

    assert any(p.startswith("stock_technical_indicators?") for p in seen_paths)
    assert "فوق EMA20 ✅" in brief
    assert "فوق EMA50 ✅" in brief
    assert "تحت EMA200 🔴" in brief
    assert "دعم 0.365" in brief
    assert "مقاومة 0.425" in brief
    assert "وقف محسوب 0.331" in brief
    assert "تحذير مالي" in brief
    assert "r_vol" not in brief


def test_primary_deepseek_requests_path_applies_output_guard() -> None:
    """Primary requests.post path in _generate_ai_consultation must sanitize leaked fields & inverted Ex-Date."""
    from api import scheduled_automations_worker as worker

    fake_resp = SimpleNamespace(
        status_code=200,
        json=lambda: {
            "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140},
            "choices": [
                {
                    "message": {
                        "content": (
                            "تقرير السهم: `r_vol` = 1.8x مع dist_score = 40. "
                            "يوم Ex-Date الكوبون: البيع هنا = بدون كوبون."
                        )
                    }
                }
            ],
        },
        text="",
    )

    with (
        patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=False),
        patch.object(worker, "_fetch_market_indicators_brief", return_value="• #COMI: 100"),
        patch.object(worker.requests, "post", return_value=fake_resp),
    ):
        out = worker._generate_ai_consultation("حلل COMI", "أحمد")

    assert "r_vol" not in out
    assert "dist_score" not in out
    assert "البيع هنا = بدون كوبون" not in out


def test_single_sharia_or_dividends_tool_calls_do_not_collide_with_vip_stock() -> None:
    """Single-tool get_sharia_cleanser / get_dividends must resolve to isolated sub-keys, never vip_stock_{sym}."""
    assert resolve_tool_calls_to_cache_key(
        [{"function": {"name": "get_dividends", "arguments": '{"symbol": "BIOC"}'}}]
    ) == "vip_stock_BIOC_divs"
    assert resolve_tool_calls_to_cache_key(
        [{"function": {"name": "get_sharia_cleanser", "arguments": '{"symbol": "COMI"}'}}]
    ) == "vip_stock_COMI_sharia"


def test_optimizer_compute_returns_rebases_split_jump() -> None:
    """4:1 unadjusted split in stock_prices must produce 0% split-day return instead of -25% outlier spike."""
    from api.portfolio_or_optimizer import compute_returns_by_date

    rows = [
        {"symbol": "ORHD", "date": "2026-09-18", "close": 40.0},
        {"symbol": "ORHD", "date": "2026-09-20", "close": 40.0},
        {"symbol": "ORHD", "date": "2026-09-21", "close": 10.0},
        {"symbol": "ORHD", "date": "2026-09-22", "close": 10.2},
    ]
    rets = compute_returns_by_date(rows)["ORHD"]
    assert rets["2026-09-21"] == pytest.approx(0.0, abs=1e-6)
    assert rets["2026-09-22"] == pytest.approx(0.02, abs=1e-6)


def test_split_adjusted_fundamentals_and_offload_parity() -> None:
    """POUL pre-split EPS/BVPS must scale down realistically while already-adjusted ORHD remains untouched."""
    from api.agentic_chat.tools_execution import _normalize_split_adjusted_fundamentals

    poul_raw = {"eps": 4.58, "bookValuePerShare": 16.86, "pbRatio": 1.71, "peRatio": 6.29}
    poul_adj, did_poul = _normalize_split_adjusted_fundamentals(poul_raw, close_price=7.10)
    assert did_poul is True
    assert 6.0 <= poul_adj["peRatio"] <= 6.6
    assert poul_adj["bookValuePerShare"] == pytest.approx(7.10 / 1.71, rel=0.02)

    orhd_raw = {"eps": 1.4677, "bookValuePerShare": 5.2062, "pbRatio": 1.98, "peRatio": 7.04}
    orhd_adj, did_orhd = _normalize_split_adjusted_fundamentals(orhd_raw, close_price=9.98)
    assert did_orhd is False
    assert orhd_adj["peRatio"] == pytest.approx(7.04)

    web_poul = _compute_single_fair_value(
        symbol="POUL",
        close=7.10,
        fund_row={"symbol": "POUL", "data": poul_raw},
        ind={"ema_200": 8.0, "vwap_20": 7.3},
        sector_median_pe=10.0,
        sector_median_pb=1.5,
        market="egx",
    )
    assert 6.0 <= web_poul["peRatio"] <= 6.6
    assert web_poul["grahamValue"] < 12.0


def test_detect_and_adjust_price_split_and_ema_position_labels() -> None:
    """ORHD split jump (42.5 -> 12.96) must rebase stale EMAs and emit exact Arabic position tags."""
    from api.agentic_chat.tools_execution import (
        _compute_stock_context_metrics,
        _detect_and_adjust_price_split,
    )

    desc_rows = [{"date": f"2026-10-{d:02d}", "close": 10.0} for d in range(25, 0, -1)]
    desc_rows += [{"date": "2026-09-21", "close": 12.96}]
    desc_rows += [{"date": f"2026-09-{d:02d}", "close": 42.5} for d in range(20, 10, -1)]

    adj50, adj200, sp_factor, did_adj = _detect_and_adjust_price_split(desc_rows, 15.51, 25.46, 9.98)
    assert did_adj is True
    assert sp_factor is not None and sp_factor < 0.45
    assert adj50 is not None and adj50 < 12.0
    assert adj200 is not None and adj200 < 13.0

    ctx = _compute_stock_context_metrics(
        close=74.41,
        ema_50=74.0,
        ema_200=77.28,
        vwap_20=74.1,
        support_1=73.5,
        resistance_1=78.0,
        stop_loss=71.0,
    )
    assert ctx["above_ema200"] is False
    assert "تحت EMA200 (77.28) 🔴" == ctx["ema200_position_ar"]


def test_build_portfolio_view_payload_deterministic_rotation_matrix() -> None:
    """_build_portfolio_view_payload must classify EXIT_PRIORITY, TRIM_EXCESS, HOLD_CORE and do_not_buy."""
    from api.agentic_chat.tools_execution import _build_portfolio_view_payload

    holdings = [
        {"id": "1", "symbol": "PRCL", "quantity": 150, "entry_price": 22.5},
        {"id": "2", "symbol": "OIH", "quantity": 2000, "entry_price": 1.8},
        {"id": "3", "symbol": "EPPK", "quantity": 1000, "entry_price": 10.3},
        {"id": "4", "symbol": "EFIC", "quantity": 300, "entry_price": 170.0},
        {"id": "5", "symbol": "HDBK", "quantity": 100, "entry_price": 95.0},
        {"id": "6", "symbol": "AMOC", "quantity": 1000, "entry_price": 12.5},
    ]

    class _MockQ:
        def __init__(self, tbl: str):
            self.tbl = tbl
            self._eq: dict[str, object] = {}

        def select(self, *_a): return self
        def eq(self, c, v):
            self._eq[c] = v
            return self
        def in_(self, *_a): return self
        def order(self, *_a, **_kw): return self
        def limit(self, *_a): return self

        def execute(self):
            if self.tbl == "stock_technical_indicators":
                return SimpleNamespace(data=[
                    {"symbol": "PRCL", "exchange": "EGX", "close": 18.0, "ema_50": 23.0, "ema_200": 24.0, "r_vol": 0.45},
                    {"symbol": "OIH", "exchange": "EGX", "close": 1.64, "ema_50": 1.75, "ema_200": 1.60, "r_vol": 1.0},
                    {"symbol": "EPPK", "exchange": "EGX", "close": 9.78, "ema_50": 10.6, "ema_200": 11.5, "r_vol": 1.0},
                    {"symbol": "EFIC", "exchange": "EGX", "close": 155.0, "ema_50": 164.0, "ema_200": 187.0, "r_vol": 0.8},
                    {"symbol": "HDBK", "exchange": "EGX", "close": 105.5, "ema_50": 102.0, "ema_200": 84.0, "r_vol": 1.1},
                    {"symbol": "AMOC", "exchange": "EGX", "close": 12.5, "ema_50": 12.6, "ema_200": 10.6, "r_vol": 1.2},
                ])
            if self.tbl == "stock_fundamentals":
                return SimpleNamespace(data=[
                    {"symbol": "PRCL", "fund_score": 32.0, "data": {"eps": -2.0, "bookValuePerShare": -5.3}},
                    {"symbol": "OIH", "fund_score": 14.0, "data": {"eps": -0.09, "roe": -21.0}},
                    {"symbol": "EPPK", "fund_score": 42.0, "data": {"eps": -0.69, "bookValuePerShare": 10.0}},
                    {"symbol": "EFIC", "fund_score": 52.0, "data": {"eps": 2.8, "peRatio": 54.0, "freeCashFlow": -50000000}},
                    {"symbol": "HDBK", "fund_score": 87.0, "data": {"eps": 18.2, "peRatio": 5.79}},
                    {"symbol": "AMOC", "fund_score": 77.0, "data": {"eps": 1.08, "peRatio": 11.59}},
                ])
            if self.tbl == "stock_prices":
                return SimpleNamespace(data=[
                    {"symbol": "EPPK", "date": f"2026-11-{d:02d}", "close": 9.78, "volume": 0}
                    for d in range(23, 13, -1)
                ])
            return SimpleNamespace(data=[])

    class _MockSB:
        def from_(self, tbl: str):
            return _MockQ(tbl)

    with (
        patch("api.agentic_chat.tools_execution._lookup_upcoming_dividend", return_value=None),
        patch("api.agentic_chat.tools_execution.is_sharia_compliant", side_effect=lambda s, market="EGX": s == "AMOC"),
    ):
        payload = _build_portfolio_view_payload(_MockSB(), holdings, [], cash=4000.0)

    rot = payload["portfolio_rotation_matrix"]
    assert set(["PRCL", "OIH", "EPPK"]).issubset(set(rot["exit_priority_symbols"]))
    assert "EFIC" in rot["trim_excess_symbols"]
    assert set(["HDBK", "AMOC"]).issubset(set(rot["hold_core_symbols"]))
    assert set(["PRCL", "OIH", "EPPK", "EFIC"]).issubset(set(rot["do_not_buy_symbols"]))


def test_output_guard_blocks_buy_recommendation_on_excluded_portfolio_stock() -> None:
    """Check E must flag lines recommending buying/increasing excluded stocks without false positives on exits."""
    tool_payloads = [
        {
            "excludedFromBuying": [{"symbol": "PRCL", "reason": "شركة خاسرة"}],
            "portfolio_rotation_matrix": {"exit_priority_symbols": ["PRCL", "OIH", "EPPK"]},
        }
    ]
    bad_reply = (
        "| **PRCL** زيادة | 18.19 | ~8,000 ج.م عند 16.78 |\n"
        "- بيع OIH وشراء AMOC\n"
        "- لا أنصح بزيادة EPPK حالياً\n"
    )
    res = verify_and_guard_reply(bad_reply, tool_payloads, market="EGX")
    assert "excluded_stock_buy_conflict:PRCL" in res["warnings"]
    assert "excluded_stock_buy_conflict:OIH" not in res["warnings"]
    assert "excluded_stock_buy_conflict:EPPK" not in res["warnings"]
    assert res["block_cache"] is True
    assert "تنبيه اتساق المحفظة التلقائي" in res["reply"]


def test_optimizer_relaxation_preserves_excluded_zero_caps_and_prompt_param() -> None:
    """Relaxing thin-liquidity caps must not grant positive weights to excluded assets, and prompt uses use_my_portfolio."""
    import asyncio
    from api.agentic_chat.prompts import AGENTIC_SYSTEM_PROMPT
    from api.portfolio_or_optimizer import estimate_covariance_matrix, solve_optimal_weights

    assert "optimize_portfolio(use_my_portfolio=True)" in AGENTIC_SYSTEM_PROMPT
    assert "use_user_portfolio" not in AGENTIC_SYSTEM_PROMPT

    assets = [
        AssetInput(symbol="EX1", price=10.0, sector="A", max_weight_override=0.0, expected_score=-0.8),
        AssetInput(symbol="TH1", price=10.0, sector="B", max_weight_override=0.15, expected_score=0.5),
        AssetInput(symbol="TH2", price=10.0, sector="C", max_weight_override=0.15, expected_score=0.5),
        AssetInput(symbol="TH3", price=10.0, sector="D", max_weight_override=0.15, expected_score=0.5),
    ]
    cov, _, _ = estimate_covariance_matrix(assets)
    w, _, _, notes = solve_optimal_weights(assets, cov, max_weight=0.45, max_sector_weight=0.60, min_cash_weight=0.0)
    assert w[0] == pytest.approx(0.0, abs=1e-6)
    # Explicit max_weight_override caps (0.15 each) are preserved; remaining 55% absorbed into Cash Reserve
    assert sum(w[1:]) == pytest.approx(0.45, abs=1e-4)
    assert any("كاش احتياطي" in n for n in notes)

    captured: dict[str, object] = {}

    async def _fake_opt(**kwargs):
        captured.update(kwargs)
        return {"status": "success"}

    with patch("api.agentic_chat.tools_execution.execute_optimize_portfolio", side_effect=_fake_opt):
        asyncio.run(dispatch_tool("optimize_portfolio", {"use_user_portfolio": True}))
    assert captured["use_my_portfolio"] is True


def test_optimize_portfolio_excludes_loss_making_acamd_and_caps_hold_watch_actf() -> None:
    """Loss-making stocks (even with high fund_score like ACAMD) must be excluded, and HOLD_WATCH (ACTF) capped at current weight."""
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch
    from api.agentic_chat.tools_execution import _sync_optimize_portfolio

    pos_rows = [
        {"symbol": "ABUK", "quantity": 100, "entry_price": 75.0},
        {"symbol": "ETRS", "quantity": 1000, "entry_price": 10.5},
        {"symbol": "ALCN", "quantity": 800, "entry_price": 21.0},
        {"symbol": "ACAP", "quantity": 2000, "entry_price": 3.0},
        {"symbol": "ACAMD", "quantity": 5000, "entry_price": 1.0},
        {"symbol": "ACTF", "quantity": 2000, "entry_price": 2.1},
    ]
    ind_rows = [
        {"symbol": "ABUK", "date": "2026-11-23", "close": 74.41, "rsi_14": 42.3, "ema_50": 82.07, "ema_200": 77.28, "r_vol": 0.9, "atr_14": 2.0, "change_pct": 0.5, "exchange": "EGX"},
        {"symbol": "ETRS", "date": "2026-11-23", "close": 11.10, "rsi_14": 60.0, "ema_50": 10.7, "ema_200": 9.6, "r_vol": 1.1, "atr_14": 0.3, "change_pct": 1.0, "exchange": "EGX"},
        {"symbol": "ALCN", "date": "2026-11-23", "close": 22.0, "rsi_14": 55.0, "ema_50": 21.0, "ema_200": 19.5, "r_vol": 1.2, "atr_14": 0.5, "change_pct": 0.8, "exchange": "EGX"},
        {"symbol": "ACAP", "date": "2026-11-23", "close": 3.20, "rsi_14": 58.0, "ema_50": 3.0, "ema_200": 2.7, "r_vol": 1.3, "atr_14": 0.1, "change_pct": 1.5, "exchange": "EGX"},
        {"symbol": "ACAMD", "date": "2026-11-23", "close": 0.95, "rsi_14": 45.0, "ema_50": 1.10, "ema_200": 1.20, "r_vol": 0.9, "atr_14": 0.04, "change_pct": -1.0, "exchange": "EGX"},
        {"symbol": "ACTF", "date": "2026-11-23", "close": 2.05, "rsi_14": 44.0, "ema_50": 2.25, "ema_200": 2.40, "r_vol": 0.9, "atr_14": 0.08, "change_pct": -0.5, "exchange": "EGX"},
    ]
    st_rows = [
        {"symbol": "ABUK", "name": "Abou Kir", "name_ar": "أبو قير للأسمدة", "exchange": "EGX"},
        {"symbol": "ETRS", "name": "Egytrans", "name_ar": "إيجيترانس", "exchange": "EGX"},
        {"symbol": "ALCN", "name": "Alex Containers", "name_ar": "الإسكندرية للحاويات", "exchange": "EGX"},
        {"symbol": "ACAP", "name": "A Capital", "name_ar": "أيه كابيتال", "exchange": "EGX"},
        {"symbol": "ACAMD", "name": "Arab Co Asset", "name_ar": "أكامد", "exchange": "EGX"},
        {"symbol": "ACTF", "name": "Act Financial", "name_ar": "أكت فاينانشال", "exchange": "EGX"},
    ]
    sf_rows = [
        {"symbol": "ABUK", "fund_score": 73.0, "data": {"eps": 3.69, "netIncome": 4.66e9, "peRatio": 20.69, "bookValuePerShare": 18.4, "roe": 16.5, "sector": "Basic Materials"}},
        {"symbol": "ETRS", "fund_score": 84.0, "data": {"eps": 1.0, "netIncome": 1.2e8, "peRatio": 11.4, "bookValuePerShare": 4.5, "roe": 22.5, "sector": "Industrials"}},
        {"symbol": "ALCN", "fund_score": 82.0, "data": {"eps": 2.5, "netIncome": 3.0e8, "peRatio": 10.5, "bookValuePerShare": 6.0, "roe": 81.7, "sector": "Logistics"}},
        {"symbol": "ACAP", "fund_score": 76.0, "data": {"eps": 0.4, "netIncome": 5.0e7, "peRatio": 9.3, "bookValuePerShare": 1.5, "roe": 20.0, "sector": "Financials"}},
        {"symbol": "ACAMD", "fund_score": 82.0, "data": {"eps": 0.146, "netIncome": -1453247.0, "peRatio": 13.22, "bookValuePerShare": 0.0335, "roe": 227.4, "sector": "Real Estate"}},
    ]
    base_dt = datetime(2026, 11, 23, tzinfo=timezone.utc)
    price_rows = []
    for s_row in ind_rows:
        base_c = s_row["close"]
        for d in range(25):
            dt_str = (base_dt - timedelta(days=d)).strftime("%Y-%m-%d")
            drift = 1.0 + ((d % 5) - 2) * 0.008
            price_rows.append({"symbol": s_row["symbol"], "date": dt_str, "close": round(base_c * drift, 4), "volume": 500000})

    class _MockRes:
        def __init__(self, data):
            self.data = data

    class _MockQuery:
        def __init__(self, tbl):
            self._tbl = tbl
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def in_(self, *_a): return self
        def gte(self, *_a): return self
        def order(self, *_a, **_kw): return self
        def limit(self, *_a): return self
        def execute(self):
            return {
                "positions": _MockRes(pos_rows),
                "profiles": _MockRes([{"cash_balance": 20000.0}]),
                "stock_technical_indicators": _MockRes(ind_rows),
                "stocks": _MockRes(st_rows),
                "stock_fundamentals": _MockRes(sf_rows),
                "stock_prices": _MockRes(price_rows),
            }.get(self._tbl, _MockRes([]))

    class _MockSB:
        def from_(self, tbl): return _MockQuery(tbl)

    mock_sb = _MockSB()
    with (
        patch("api.agentic_chat.tools_execution._get_sb", return_value=mock_sb),
        patch("api.agentic_chat.tools_execution._get_sb_for_market", return_value=mock_sb),
        patch("api.routers.offload_public._get_fair_value", return_value={"stocks": []}),
        patch("api.agentic_chat.tools_execution._resolve_symbol_and_market", side_effect=lambda s, explicit_market=None: (str(s).upper(), "EGX")),
    ):
        res = _sync_optimize_portfolio(user_id="u-acamd-test", use_my_portfolio=True, objective="balanced")

    assert res["status"] == "success"
    opt = res["optimization"]
    excl_syms = {row["symbol"] for row in (opt.get("excludedFromBuying") or [])}
    assert "ACAMD" in excl_syms
    alloc_map = {row["symbol"]: row for row in opt["allocations"]}
    assert alloc_map["ACAMD"]["targetWeightPct"] == 0.0
    assert alloc_map["ACAMD"]["action"] != "BUY"
    assert alloc_map["ACTF"]["targetWeightPct"] <= alloc_map["ACTF"]["currentWeightPct"] + 1e-6
    assert alloc_map["ACTF"]["action"] != "BUY"


def test_quant_engine_overvalued_text_contradiction_guard() -> None:
    """Strong financials above fair value in a downtrend must NOT say 'تقييمه رخيص'."""
    from datetime import datetime, timedelta, timezone
    from api.agentic_chat.quant_engine import build_quant_intelligence_for_stock

    base_dt = datetime(2026, 11, 23, tzinfo=timezone.utc)
    bars = [
        {
            "date": (base_dt - timedelta(days=i)).strftime("%Y-%m-%d"),
            "close": round(74.41 + i * 0.15, 2),
            "high": round(75.2 + i * 0.15, 2),
            "low": round(73.5 + i * 0.15, 2),
        }
        for i in range(45)
    ]
    res = build_quant_intelligence_for_stock(
        symbol="ABUK",
        exchange="EGX",
        currency="ج.م",
        close=74.41,
        ema_50=82.07,
        ema_200=77.28,
        rsi_14=42.28,
        r_vol=0.19,
        fund_score=73.0,
        fair_value=68.26,
        valuation_upside_pct=-8.3,
        resistance_1=92.33,
        stop_loss=72.13,
        ohlcv_rows=bars,
        record_ledger=False,
    )
    assert res["setup_regime"] == "value_in_downtrend"
    assert "تقييمه رخيص" not in res["conflict_resolution_ar"]
    assert "أعلى من القيمة العادلة" in res["conflict_resolution_ar"]
    assert "أعلى من القيمة العادلة" in res["setup_regime_label_ar"]


def test_smart_dca_abuk_fair_breakeven_reference() -> None:
    """DCA breakeven rally & 10d probability must measure from post-tranche fill price, not pre-dip price."""
    from datetime import datetime, timedelta, timezone
    from api.portfolio_or_optimizer import build_smart_dca_plan

    base_dt = datetime(2026, 11, 23, tzinfo=timezone.utc)
    bars = [
        {
            "date": (base_dt - timedelta(days=i)).strftime("%Y-%m-%d"),
            "close": round(74.41 + (i % 7 - 3) * 0.7, 2),
            "high": round(75.5 + (i % 7 - 3) * 0.7, 2),
            "low": round(73.1 + (i % 7 - 3) * 0.7, 2),
        }
        for i in range(60)
    ]
    res = build_smart_dca_plan(
        symbol="ABUK",
        exchange="EGX",
        currency="ج.م",
        current_price=74.41,
        old_shares=100,
        old_avg_price=85.0,
        dca_budget=20000.0,
        support_1=73.60,
        support_2=66.66,
        stop_loss=63.99,
        setup_regime="value_in_downtrend",
        fund_score=73.0,
        is_loss_making=False,
        ohlcv_rows=bars,
    )
    assert res["dca_allowed"] is True
    assert res["breakeven_reference_price"] == 66.66
    assert res["rally_needed_after_pct"] > 5.0
    assert res["rally_needed_after_pct"] < res["rally_needed_before_pct"]
    assert res["prob_breakeven_10d_after_pct"] < 100.0
    assert res["prob_breakeven_10d_after_pct"] >= res["prob_breakeven_10d_before_pct"]


def test_calculate_position_auto_loads_user_portfolio_shares() -> None:
    """When user omits quantity, _sync_calculate_position reads real held shares from positions."""
    from unittest.mock import patch
    from api.agentic_chat.tools_execution import _sync_calculate_position

    class _MockRes:
        def __init__(self, data):
            self.data = data

    class _MockQuery:
        def __init__(self, tbl):
            self._tbl = tbl
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def order(self, *_a, **_kw): return self
        def limit(self, *_a): return self
        def execute(self):
            return {
                "positions": _MockRes([{"quantity": 1888, "entry_price": 85.0}]),
                "stock_technical_indicators": _MockRes([{"close": 74.41, "date": "2026-11-23"}]),
                "stock_prices": _MockRes([{"high": 75.0, "low": 73.5, "close": 74.41, "date": "2026-11-23"}] * 15),
            }.get(self._tbl, _MockRes([]))

    class _MockSB:
        def from_(self, tbl): return _MockQuery(tbl)

    mock_stock = {
        "status": "success",
        "stocks": [{
            "symbol": "ABUK",
            "close": 74.41,
            "support_1": 73.60,
            "support_2": 66.66,
            "stop_loss": 63.99,
            "fund_score": 73.0,
            "quant_intelligence": {"setup_regime": "value_in_downtrend"},
        }],
    }
    with (
        patch("api.agentic_chat.tools_execution._get_sb", return_value=_MockSB()),
        patch("api.agentic_chat.tools_execution._sync_get_stock", return_value=mock_stock),
        patch("api.agentic_chat.tools_execution._resolve_symbol_and_market", return_value=("ABUK", "EGX")),
    ):
        res = _sync_calculate_position(
            symbol="ABUK",
            quantity=None,
            entry_price=85.0,
            dca_budget=20000.0,
            user_id="user-abuk-123",
        )

    assert res["quantity"] == 1888.0
    assert res.get("quantity_source") == "user_portfolio"
    assert res["smart_dca_plan"]["old_shares"] == 1888.0
    assert res["smart_dca_plan"]["reference_100_shares"] is False


def test_optimize_portfolio_overweight_watch_and_thin_liquidity_never_wipes_caps() -> None:
    """Overweight HOLD_WATCH (GBCO=34%) + thin-liquidity HOLD_CORE (ABUK=14.9%) must NOT trigger solver relaxation."""
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch
    from api.agentic_chat.tools_execution import _sync_optimize_portfolio

    # Core: ABUK (thin r_vol=0.19 -> 15% cap, cur~15%), ETRS (25%), ALCN (25%) -> core_cap_sum = 0.65
    # Watch: GBCO (34% uncapped, capped to 0.25), ACTF (2.1%) -> watch_cap_sum = 0.271 -> total=0.921 < 1.0
    pos_rows = [
        {"symbol": "ABUK", "quantity": 200, "entry_price": 75.0},   # 14,882
        {"symbol": "ETRS", "quantity": 2000, "entry_price": 10.5},  # 22,200
        {"symbol": "ALCN", "quantity": 1200, "entry_price": 21.0},  # 26,400
        {"symbol": "GBCO", "quantity": 1600, "entry_price": 22.0},  # 34,400 (~34%)
        {"symbol": "ACTF", "quantity": 1000, "entry_price": 2.1},   # 2,050 (~2.1%)
    ]
    ind_rows = [
        {"symbol": "ABUK", "date": "2026-11-23", "close": 74.41, "rsi_14": 42.3, "ema_50": 82.07, "ema_200": 77.28, "r_vol": 0.19, "atr_14": 2.0, "change_pct": 0.5, "exchange": "EGX"},
        {"symbol": "ETRS", "date": "2026-11-23", "close": 11.10, "rsi_14": 60.0, "ema_50": 10.7, "ema_200": 9.6, "r_vol": 1.1, "atr_14": 0.3, "change_pct": 1.0, "exchange": "EGX"},
        {"symbol": "ALCN", "date": "2026-11-23", "close": 22.0, "rsi_14": 55.0, "ema_50": 21.0, "ema_200": 19.5, "r_vol": 1.2, "atr_14": 0.5, "change_pct": 0.8, "exchange": "EGX"},
        {"symbol": "GBCO", "date": "2026-11-23", "close": 21.50, "rsi_14": 48.0, "ema_50": 23.0, "ema_200": 24.0, "r_vol": 1.1, "atr_14": 0.5, "change_pct": -0.2, "exchange": "EGX"},
        {"symbol": "ACTF", "date": "2026-11-23", "close": 2.05, "rsi_14": 44.0, "ema_50": 2.25, "ema_200": 2.40, "r_vol": 0.9, "atr_14": 0.08, "change_pct": -0.5, "exchange": "EGX"},
    ]
    sf_rows = [
        {"symbol": "ABUK", "fund_score": 73.0, "data": {"eps": 3.69, "netIncome": 4.66e9, "peRatio": 20.69, "bookValuePerShare": 18.4, "roe": 16.5, "sector": "Materials"}},
        {"symbol": "ETRS", "fund_score": 84.0, "data": {"eps": 1.0, "netIncome": 1.2e8, "peRatio": 11.4, "bookValuePerShare": 4.5, "roe": 22.5, "sector": "Logistics"}},
        {"symbol": "ALCN", "fund_score": 82.0, "data": {"eps": 2.5, "netIncome": 3.0e8, "peRatio": 10.5, "bookValuePerShare": 6.0, "roe": 81.7, "sector": "Shipping"}},
        {"symbol": "GBCO", "fund_score": 60.0, "data": {"eps": 1.2, "netIncome": 2.0e8, "peRatio": 18.0, "bookValuePerShare": 9.0, "roe": 14.0, "sector": "Autos"}},
    ]
    base_dt = datetime(2026, 11, 23, tzinfo=timezone.utc)
    price_rows = [
        {"symbol": s_row["symbol"], "date": (base_dt - timedelta(days=d)).strftime("%Y-%m-%d"), "close": round(s_row["close"] * (1 + ((d % 5) - 2) * 0.008), 4), "volume": 500000}
        for s_row in ind_rows
        for d in range(25)
    ]

    class _MockRes:
        def __init__(self, data):
            self.data = data

    class _MockQuery:
        def __init__(self, tbl):
            self._tbl = tbl
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def in_(self, *_a): return self
        def gte(self, *_a): return self
        def order(self, *_a, **_kw): return self
        def limit(self, *_a): return self
        def execute(self):
            return {
                "positions": _MockRes(pos_rows),
                "profiles": _MockRes([{"cash_balance": 100.0}]),
                "stock_technical_indicators": _MockRes(ind_rows),
                "stocks": _MockRes([{"symbol": r["symbol"], "name": r["symbol"], "name_ar": r["symbol"], "exchange": "EGX"} for r in ind_rows]),
                "stock_fundamentals": _MockRes(sf_rows),
                "stock_prices": _MockRes(price_rows),
            }.get(self._tbl, _MockRes([]))

    class _MockSB:
        def from_(self, tbl): return _MockQuery(tbl)

    mock_sb = _MockSB()
    with (
        patch("api.agentic_chat.tools_execution._get_sb", return_value=mock_sb),
        patch("api.agentic_chat.tools_execution._get_sb_for_market", return_value=mock_sb),
        patch("api.routers.offload_public._get_fair_value", return_value={"stocks": []}),
        patch("api.agentic_chat.tools_execution._resolve_symbol_and_market", side_effect=lambda s, explicit_market=None: (str(s).upper(), "EGX")),
    ):
        res = _sync_optimize_portfolio(user_id="u-thin-watch", use_my_portfolio=True, objective="balanced")

    alloc_map = {row["symbol"]: row for row in res["optimization"]["allocations"]}
    # Thin-liquidity ABUK must keep its 15% cap intact, and full-downtrend ACTF must NEVER be auto-bought
    assert alloc_map["ABUK"]["targetWeightPct"] <= 15.1
    assert alloc_map["ACTF"]["action"] != "BUY"
    assert any("كاش احتياطي" in n for n in res["optimization"]["constraints"]["relaxationNotes"])
