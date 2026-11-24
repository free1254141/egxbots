"""
Offline deterministic unit tests for:
- Market-calibrated Fat-Tail Monte Carlo barrier simulator (`quant_engine.py`)
- Bull vs. Bear conflict resolution & FRA-compliant setup regimes
- Rolling empirical barrier backtesting, Bayesian shrinkage & self-learning ledger grading
- Operations Research Smart DCA & Break-Even Optimizer (`portfolio_or_optimizer.py`)
- Pipeline structured visual extraction (`quant_analysis`, `dca_plan`)
"""

import time


def _make_synthetic_bars(n: int = 60, start_price: float = 36.0, drift: float = 0.001, vol: float = 0.02):
    import math
    bars = []
    px = float(start_price)
    for i in range(n):
        # Deterministic smooth oscillation around drift so rolling barrier hit-rate is non-trivial
        step = drift + vol * math.sin(i * 0.7) * 0.8
        op = px
        cl = round(op * math.exp(step), 3)
        hi = round(max(op, cl) * (1.0 + vol * 0.6), 3)
        lo = round(min(op, cl) * (1.0 - vol * 0.6), 3)
        bars.append({
            "date": f"2026-10-{(i % 28) + 1:02d}" if i < 28 else f"2026-11-{(i - 27):02d}",
            "open": op,
            "high": hi,
            "low": lo,
            "close": cl,
        })
        px = cl
    return bars


def test_monte_carlo_reproducibility_circuit_limits_and_speed():
    from api.agentic_chat.quant_engine import run_monte_carlo_barrier_sim, get_exchange_daily_limit

    assert get_exchange_daily_limit("EGX") == 0.20
    assert get_exchange_daily_limit("TADAWUL") == 0.10
    assert get_exchange_daily_limit("QSE") == 0.10

    bars = _make_synthetic_bars(60, start_price=36.0)
    last_close = bars[-1]["close"]

    t0 = time.perf_counter()
    sim1 = run_monte_carlo_barrier_sim(
        bars,
        close=last_close,
        target_price=round(last_close * 1.07, 2),
        stop_price=round(last_close * 0.94, 2),
        exchange="EGX",
        symbol="MFPC",
        last_date="2026-11-23",
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    sim2 = run_monte_carlo_barrier_sim(
        bars,
        close=last_close,
        target_price=round(last_close * 1.07, 2),
        stop_price=round(last_close * 0.94, 2),
        exchange="EGX",
        symbol="MFPC",
        last_date="2026-11-23",
    )
    assert sim1 == sim2  # 100% deterministic for identical state
    assert sim1["paths_count"] == 5000
    assert sim1["daily_limit_pct"] == 20.0
    total_prob = sim1["raw_target_prob_pct"] + sim1["prob_hit_stop_first_pct"] + sim1["prob_stay_in_range_pct"]
    assert abs(total_prob - 100.0) <= 0.2
    rng = sim1["expected_10d_range"]
    assert rng["p10"] <= rng["p50"] <= rng["p90"]
    assert elapsed_ms < 50.0  # Pure NumPy budget comfortably under 50ms even on cold test import

    # TASI tighter circuit limit (+/-10%)
    sim_tasi = run_monte_carlo_barrier_sim(
        bars,
        close=28.0,
        target_price=29.5,
        stop_price=26.8,
        exchange="TADAWUL",
        symbol="2222",
        last_date="2026-11-23",
    )
    assert sim_tasi["daily_limit_pct"] == 10.0


def test_bull_bear_conflict_resolution_and_self_learning_calibration():
    from api.agentic_chat.quant_engine import (
        build_quant_intelligence_for_stock,
        _grade_and_record_ledger,
        _mem_get,
        LEDGER_CACHE_KEY,
    )

    bars = _make_synthetic_bars(60, start_price=36.0)
    last_c = bars[-1]["close"]

    # Case 1: Financially strong/cheap but technically below EMA50 & EMA200 (classic MFPC/ADIB conflict)
    qi_conflict = build_quant_intelligence_for_stock(
        symbol="MFPC",
        exchange="EGX",
        close=last_c,
        rsi_14=33.0,
        macd_histogram=-0.4,
        ema_50=last_c * 1.12,
        ema_200=last_c * 1.08,
        vwap_20=last_c * 1.07,
        r_vol=0.85,
        support_1=round(last_c * 0.95, 2),
        resistance_1=round(last_c * 1.08, 2),
        stop_loss=round(last_c * 0.92, 2),
        fair_value=round(last_c * 1.48, 2),
        fund_score=82.0,
        roe=24.0,
        is_sharia_compliant=True,
        ohlcv_rows=bars,
        last_date="2026-11-23",
    )
    assert qi_conflict["setup_regime"] == "value_in_downtrend"
    assert qi_conflict["fundamental_score"] >= 80
    assert qi_conflict["technical_score"] < 46
    assert "تعارض واضح" in qi_conflict["conflict_resolution_ar"]
    mc = qi_conflict["monte_carlo"]
    assert abs(mc["prob_hit_target_first_pct"] + mc["prob_hit_stop_first_pct"] + mc["prob_stay_in_range_pct"] - 100.0) <= 0.2
    sl = qi_conflict["self_learning"]
    assert sl["empirical_sample_size"] >= 5
    assert sl["empirical_hit_rate_pct"] is not None

    # Case 2: Institutional distribution mistake penalty reduces target probability
    qi_dist = build_quant_intelligence_for_stock(
        symbol="CRST",
        exchange="EGX",
        close=last_c,
        rsi_14=76.0,
        r_vol=0.75,
        dist_score=80.0,
        ema_50=last_c * 1.15,
        ema_200=last_c * 1.10,
        support_1=round(last_c * 0.94, 2),
        resistance_1=round(last_c * 1.08, 2),
        stop_loss=round(last_c * 0.90, 2),
        fund_score=30.0,
        is_loss_making=True,
        ohlcv_rows=bars,
        last_date="2026-11-23",
    )
    assert qi_dist["setup_regime"] == "high_risk_avoid"
    assert qi_dist["conviction_score"] <= 35
    assert qi_dist["self_learning"]["calibrated_target_prob_pct"] <= qi_dist["self_learning"]["raw_target_prob_pct"]
    assert "تصريف مؤسسي" in qi_dist["self_learning"]["learned_lesson_ar"]

    # Case 3: Ledger outcome grading computes Brier score when >= 5 later bars exist
    early_date = bars[5]["date"]
    avg_brier = _grade_and_record_ledger(
        symbol="TESTG",
        exchange="EGX",
        eval_date=early_date,
        close=bars[5]["close"],
        target_price=bars[5]["close"] * 1.03,
        stop_price=bars[5]["close"] * 0.97,
        calibrated_prob_pct=60.0,
        setup_regime="aligned_bullish",
        bars=bars,
    )
    # Call a second time after subsequent bars exist -> grades prior ungraded entry
    avg_brier_2 = _grade_and_record_ledger(
        symbol="TESTG",
        exchange="EGX",
        eval_date=bars[-1]["date"],
        close=bars[-1]["close"],
        target_price=bars[-1]["close"] * 1.05,
        stop_price=bars[-1]["close"] * 0.95,
        calibrated_prob_pct=55.0,
        setup_regime="aligned_bullish",
        bars=bars,
    )
    hit, ledger = _mem_get(LEDGER_CACHE_KEY)
    assert hit is True
    assert ledger["graded_count"] >= 1
    assert avg_brier_2 is not None and 0.0 <= avg_brier_2 <= 1.0


def test_smart_dca_optimizer_blocks_traps_and_builds_ladder():
    from api.portfolio_or_optimizer import build_smart_dca_plan

    bars = _make_synthetic_bars(60, start_price=36.0)

    # 1. Blocking trap: CRST (distribution / loss-making) MUST reject averaging down
    blocked = build_smart_dca_plan(
        symbol="CRST",
        exchange="EGX",
        currency="ج.م",
        current_price=1.57,
        old_shares=5000,
        old_avg_price=2.40,
        dca_budget=5000.0,
        setup_regime="high_risk_avoid",
        dist_score=80.0,
        fund_score=25.0,
        is_loss_making=True,
        ohlcv_rows=bars,
    )
    assert blocked["dca_allowed"] is False
    assert "تصريف مؤسسي" in blocked["rejection_reason_ar"]
    assert blocked["capital_protection_stop"] < 1.57

    # 2. Eligible value stock (MFPC): lowers break-even & boosts 10d break-even probability
    allowed = build_smart_dca_plan(
        symbol="MFPC",
        exchange="EGX",
        currency="ج.م",
        current_price=36.56,
        old_shares=1000,
        old_avg_price=38.15,
        dca_budget=18000.0,
        support_1=35.20,
        support_2=33.80,
        stop_loss=32.90,
        setup_regime="value_in_downtrend",
        dist_score=10.0,
        fund_score=82.0,
        is_loss_making=False,
        ohlcv_rows=bars,
    )
    assert allowed["dca_allowed"] is True
    assert allowed["new_avg_price_t1"] < allowed["old_avg_price"]
    assert allowed["new_avg_price_full"] < allowed["new_avg_price_t1"]
    assert allowed["rally_needed_after_pct"] < allowed["rally_needed_before_pct"]
    assert allowed["prob_breakeven_10d_after_pct"] >= allowed["prob_breakeven_10d_before_pct"]
    assert len(allowed["tranches"]) == 2
    assert allowed["tranches"][0]["shares"] > 0 and allowed["tranches"][1]["shares"] > 0


def test_pipeline_collect_structured_outputs_extracts_quant_and_dca():
    from api.agentic_chat.pipeline import _collect_structured_outputs

    visuals = {}
    tables = []
    recs = []

    stock_tool_out = {
        "status": "success",
        "stocks": [
            {
                "symbol": "MFPC",
                "name_ar": "موبكو للأسمدة",
                "close": 36.56,
                "quant_intelligence": {
                    "symbol": "MFPC",
                    "setup_regime": "value_in_downtrend",
                    "monte_carlo": {"prob_hit_target_first_pct": 40.0, "prob_hit_stop_first_pct": 30.0},
                },
            }
        ],
    }
    pos_tool_out = {
        "status": "success",
        "symbol": "MFPC",
        "smart_dca_plan": {
            "symbol": "MFPC",
            "dca_allowed": True,
            "old_avg_price": 38.15,
            "new_avg_price_full": 37.10,
        },
    }

    _collect_structured_outputs(stock_tool_out, tables, recs, visuals)
    _collect_structured_outputs(pos_tool_out, tables, recs, visuals)

    assert len(visuals["quant_analysis"]) == 1
    assert visuals["quant_analysis"][0]["symbol"] == "MFPC"
    assert visuals["quant_analysis"][0]["name_ar"] == "موبكو للأسمدة"
    assert visuals["dca_plan"]["symbol"] == "MFPC"
    assert visuals["dca_plan"]["dca_allowed"] is True


def test_sideways_range_bound_empirical_rate_not_inflated():
    from api.agentic_chat.quant_engine import build_quant_intelligence_for_stock

    sideways_bars = []
    for i in range(60):
        c = 100.0 + ((i % 3) - 1) * 0.25
        sideways_bars.append({
            "date": f"2026-09-{(i % 28) + 1:02d}" if i < 28 else f"2026-10-{(i - 27):02d}",
            "open": c,
            "high": round(c + 0.3, 3),
            "low": round(c - 0.3, 3),
            "close": round(c, 3),
        })

    qi = build_quant_intelligence_for_stock(
        symbol="SIDEW",
        exchange="EGX",
        close=100.0,
        rsi_14=50.0,
        support_1=96.0,
        resistance_1=108.0,
        stop_loss=94.0,
        ohlcv_rows=sideways_bars,
        last_date="2026-10-31",
        record_ledger=False,
    )
    mc = qi["monte_carlo"]
    sl = qi["self_learning"]
    assert sl["empirical_hit_rate_pct"] == 0.0
    assert mc["raw_target_prob_pct"] == 0.0
    assert mc["prob_hit_target_first_pct"] == 0.0
    assert mc["prob_hit_stop_first_pct"] == 0.0
    assert mc["prob_stay_in_range_pct"] == 100.0


def test_ledger_thread_safety_under_concurrent_writes():
    from concurrent.futures import ThreadPoolExecutor
    from api.agentic_chat.quant_engine import _grade_and_record_ledger, _mem_get, LEDGER_CACHE_KEY

    bars = _make_synthetic_bars(40, start_price=20.0)

    def _worker(idx: int):
        return _grade_and_record_ledger(
            symbol=f"CONC{idx}",
            exchange="EGX",
            eval_date="2026-10-15",
            close=20.0,
            target_price=21.5,
            stop_price=18.8,
            calibrated_prob_pct=42.0,
            setup_regime="neutral_watch",
            bars=bars,
        )

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_worker, range(12)))

    assert len(results) == 12
    hit, ledger = _mem_get(LEDGER_CACHE_KEY)
    assert hit is True
    entries = ledger.get("entries") or {}
    for idx in range(12):
        assert f"EGX:CONC{idx}:2026-10-15" in entries


def test_falling_knife_with_missing_fundamentals_escalates_high_risk():
    from api.agentic_chat.quant_engine import build_quant_intelligence_for_stock
    from api.portfolio_or_optimizer import build_smart_dca_plan

    bars = _make_synthetic_bars(40, start_price=120.0, drift=-0.005, vol=0.025)
    last_c = bars[-1]["close"]

    qi = build_quant_intelligence_for_stock(
        symbol="KNIFE",
        exchange="EGX",
        close=last_c,
        rsi_14=28.0,
        macd_histogram=-1.2,
        ema_50=last_c * 1.15,
        ema_200=last_c * 1.25,
        vwap_20=last_c * 1.10,
        r_vol=0.8,
        support_1=round(last_c * 0.94, 2),
        resistance_1=round(last_c * 1.10, 2),
        stop_loss=round(last_c * 0.90, 2),
        fund_score=None,
        fair_value=None,
        is_loss_making=False,
        ohlcv_rows=bars,
        last_date="2026-11-23",
        record_ledger=False,
    )
    assert qi["technical_score"] < 26
    assert qi["setup_regime"] == "high_risk_avoid"

    blocked = build_smart_dca_plan(
        symbol="KNIFE",
        exchange="EGX",
        currency="ج.م",
        current_price=last_c,
        old_shares=500,
        old_avg_price=last_c * 1.30,
        dca_budget=5000.0,
        setup_regime=qi["setup_regime"],
        dist_score=30.0,
        fund_score=None,
        is_loss_making=False,
        ohlcv_rows=bars,
    )
    assert blocked["dca_allowed"] is False


def test_pipeline_stage_label_helpers():
    from api.agentic_chat.pipeline import _build_tools_stage_label, _build_quant_stage_label

    lbl_many = _build_tools_stage_label([
        "get_stock",
        "get_market",
        "screen_stocks",
        "get_fair_value",
        "get_news",
        "get_disclosures",
        "get_price_traps",
    ])
    assert "الأسعار والمؤشرات" in lbl_many
    assert "مسح السوق والسيولة" in lbl_many
    assert lbl_many.endswith(" • ...)")

    assert "مونت كارلو (5,000 مسار)" in _build_quant_stage_label(["get_stock"], {"quant_analysis": [{"symbol": "MFPC"}]})
    assert "التوزيع الرياضي الأمثل" in _build_quant_stage_label(["optimize_portfolio"], {})
    assert "تدقيق ومطابقة البيانات" in _build_quant_stage_label(["get_dividends"], {})
