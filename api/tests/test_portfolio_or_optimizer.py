"""Deterministic unit & integration tests for Operations Research (OR) portfolio optimization."""

from __future__ import annotations

import asyncio
import math
from unittest import mock

import numpy as np
import pytest

from api.portfolio_or_optimizer import (
    AssetInput,
    allocate_integer_shares,
    compute_returns_by_date,
    estimate_covariance_matrix,
    optimize_portfolio_or,
    project_onto_portfolio_constraints,
    select_diversified_candidates,
    solve_optimal_weights,
)


def _synthetic_returns(n_days: int = 80) -> dict[str, dict[str, float]]:
    rng = np.random.default_rng(42)
    dates = [f"2026-08-{d:02d}" if d <= 31 else (f"2026-09-{d-31:02d}" if d <= 61 else f"2026-10-{d-61:02d}") for d in range(1, n_days + 1)]
    market = rng.normal(0.0005, 0.012, size=n_days)
    # LOW_VOL: defensive low volatility stock
    low_vol = 0.25 * market + rng.normal(0.0003, 0.005, size=n_days)
    # HIGH_VOL_A & HIGH_VOL_B: strongly correlated high-volatility pair (same sector)
    shared = rng.normal(0.0, 0.025, size=n_days)
    hv_a = 0.8 * market + 0.9 * shared + rng.normal(0.0, 0.006, size=n_days)
    hv_b = 0.8 * market + 0.9 * shared + rng.normal(0.0, 0.006, size=n_days)
    # UNCORR: uncorrelated stock in a third sector
    uncorr = rng.normal(0.0008, 0.014, size=n_days)
    return {
        "LOWV": {d: float(r) for d, r in zip(dates, low_vol)},
        "HVA": {d: float(r) for d, r in zip(dates, hv_a)},
        "HVB": {d: float(r) for d, r in zip(dates, hv_b)},
        "UNCR": {d: float(r) for d, r in zip(dates, uncorr)},
    }


def _sample_assets() -> list[AssetInput]:
    rets = _synthetic_returns()
    return [
        AssetInput(symbol="LOWV", price=50.0, name_ar="منخفض التذبذب", sector="اتصالات", expected_score=0.35, returns_by_date=rets["LOWV"]),
        AssetInput(symbol="HVA", price=120.0, name_ar="بنك أ", sector="بنوك", expected_score=0.40, returns_by_date=rets["HVA"]),
        AssetInput(symbol="HVB", price=80.0, name_ar="بنك ب", sector="بنوك", expected_score=0.38, returns_by_date=rets["HVB"]),
        AssetInput(symbol="UNCR", price=25.0, name_ar="أسمدة", sector="كيماويات", expected_score=0.50, returns_by_date=rets["UNCR"]),
    ]


def test_compute_returns_by_date_winsorizes_and_deduplicates():
    rows = [
        {"symbol": "COMI", "date": "2026-10-01", "close": 100.0},
        {"symbol": "COMI", "date": "2026-10-02", "close": 105.0},
        {"symbol": "COMI", "date": "2026-10-02", "close": 110.0},  # duplicate date keeps latest
        {"symbol": "COMI", "date": "2026-10-03", "close": 220.0},  # +100% spike -> capped at +25%
    ]
    out = compute_returns_by_date(rows)
    assert pytest.approx(out["COMI"]["2026-10-02"], abs=1e-6) == 0.10
    assert pytest.approx(out["COMI"]["2026-10-03"], abs=1e-6) == 0.25


def test_dykstra_projection_enforces_simplex_box_and_sector_caps():
    v = np.array([0.55, 0.30, 0.10, 0.05])
    sectors = ["بنوك", "بنوك", "كيماويات", "اتصالات"]
    w = project_onto_portfolio_constraints(v, sectors, invested_total=0.90, max_weight=0.35, max_sector_weight=0.40)
    assert pytest.approx(float(np.sum(w)), abs=1e-4) == 0.90
    assert np.all(w >= -1e-6)
    assert float(np.max(w)) <= 0.35 + 1e-4
    assert float(w[0] + w[1]) <= 0.40 + 1e-4


def test_all_four_objectives_satisfy_hard_constraints_and_min_risk_beats_equal_weight():
    assets = _sample_assets()
    cov, corr, overlap = estimate_covariance_matrix(assets)
    assert overlap >= 70
    assert corr[1, 2] > 0.65  # HVA & HVB strongly correlated

    for obj in ("balanced", "min_risk", "risk_parity", "max_diversification"):
        res = optimize_portfolio_or(
            assets,
            total_capital=100000.0,
            objective=obj,
            max_weight_pct=35.0,
            max_sector_pct=40.0,
            min_cash_pct=5.0,
            exchange="EGX",
        )
        assert res["investedAmount"] <= 95000.0 + 1e-6
        assert res["leftoverCash"] >= 5000.0 - 1e-6
        assert res["estimatedFees"] > 0
        # Verify per-stock and per-sector constraints on target continuous weights
        for row in res["allocations"]:
            assert row["targetWeightPct"] <= 35.1
            assert row["targetShares"] >= 0
            assert isinstance(row["targetShares"], int)
        bank_sum = sum(r["targetWeightPct"] for r in res["allocations"] if r["sector"] == "بنوك")
        assert bank_sum <= 40.2

    res_min = optimize_portfolio_or(
        assets,
        total_capital=100000.0,
        objective="min_risk",
        max_weight_pct=50.0,
        max_sector_pct=60.0,
    )
    # Global Minimum Variance must achieve lower annual volatility than equal-weight baseline
    assert res_min["metricsAfter"]["annualVolatilityPct"] < res_min["metricsBefore"]["annualVolatilityPct"]
    # High-correlation pair HVA/HVB must be detected
    assert any("HVA / HVB" in p["pair"] for p in res_min["highCorrelationPairs"])


def test_graceful_constraint_relaxation_when_all_stocks_in_same_sector():
    rets = _synthetic_returns()
    same_sec_assets = [
        AssetInput(symbol="COMI", price=80.0, sector="بنوك", returns_by_date=rets["HVA"]),
        AssetInput(symbol="CIEB", price=20.0, sector="بنوك", returns_by_date=rets["HVB"]),
    ]
    res = optimize_portfolio_or(
        same_sec_assets,
        total_capital=50000.0,
        objective="balanced",
        max_weight_pct=30.0,
        max_sector_pct=40.0,
    )
    assert res["investedAmount"] > 49000.0
    assert len(res["constraints"]["relaxationNotes"]) >= 2
    assert res["constraints"]["maxStockWeightPct"] >= 50.0
    assert res["constraints"]["maxSectorWeightPct"] >= 99.9


def test_integer_knapsack_allocator_respects_budget_and_computes_rebalance_deltas():
    assets = _sample_assets()
    assets[0].current_shares = 200  # 10,000
    assets[1].current_shares = 600  # 72,000 (heavily overweight!)
    assets[2].current_shares = 100  # 8,000
    assets[3].current_shares = 400  # 10,000
    res = optimize_portfolio_or(
        assets,
        total_capital=100000.0,
        objective="balanced",
        max_weight_pct=35.0,
        max_sector_pct=45.0,
        exchange="TASI",
        turnover_penalty=0.015,
    )
    assert res["hasExistingHoldings"] is True
    assert res["feeRatePct"] == pytest.approx(0.155, abs=1e-4)
    hva_row = next(r for r in res["allocations"] if r["symbol"] == "HVA")
    assert hva_row["action"] == "SELL"
    assert hva_row["deltaShares"] < 0
    assert res["metricsAfter"]["annualVolatilityPct"] < res["metricsBefore"]["annualVolatilityPct"]


def test_select_diversified_candidates_enforces_sector_and_correlation_caps():
    rets = _synthetic_returns()
    scored = [
        {"symbol": "HVA", "score": 95.0, "sector": "بنوك"},
        {"symbol": "HVB", "score": 92.0, "sector": "بنوك"},       # same sector & correlated with HVA -> skipped!
        {"symbol": "UNCR", "score": 85.0, "sector": "كيماويات"},
        {"symbol": "LOWV", "score": 80.0, "sector": "اتصالات"},
    ]
    picked = select_diversified_candidates(scored, rets, k=3, max_per_sector=1, max_correlation=0.75)
    syms = [p["symbol"] for p in picked]
    assert syms == ["HVA", "UNCR", "LOWV"]


def test_agentic_chat_optimize_portfolio_tool_and_sharia_filter():
    from api.agentic_chat.tools_execution import dispatch_tool

    rets = _synthetic_returns(40)
    price_rows = []
    for sym, rmap in [("ABUK", rets["UNCR"]), ("COMI", rets["HVA"]), ("TMGH", rets["LOWV"])]:
        px = 50.0 if sym == "ABUK" else (80.0 if sym == "COMI" else 60.0)
        for dt_s, r in sorted(rmap.items()):
            px = round(px * (1.0 + r), 2)
            price_rows.append({"symbol": sym, "date": dt_s, "close": px})

    class _FakeSb:
        def from_(self, name):
            class _Q:
                def select(self, *_a, **_kw): return self
                def eq(self, *_a, **_kw): return self
                def in_(self, *_a, **_kw): return self
                def gte(self, *_a, **_kw): return self
                def order(self, *_a, **_kw): return self
                def limit(self, *_a, **_kw): return self
                def execute(self):
                    if name == "stock_technical_indicators":
                        return type("R", (), {"data": [
                            {"symbol": "ABUK", "close": 55.0, "rsi_14": 54.0, "ema_50": 51.0, "r_vol": 1.3, "atr_14": 1.8, "exchange": "EGX"},
                            {"symbol": "COMI", "close": 82.0, "rsi_14": 58.0, "ema_50": 79.0, "r_vol": 1.1, "atr_14": 2.4, "exchange": "EGX"},
                            {"symbol": "TMGH", "close": 62.0, "rsi_14": 52.0, "ema_50": 60.0, "r_vol": 1.2, "atr_14": 1.5, "exchange": "EGX"},
                        ]})()
                    if name == "stocks":
                        return type("R", (), {"data": [
                            {"symbol": "ABUK", "name_ar": "أبوقير للأسمدة", "sector": "Basic Resources", "exchange": "EGX"},
                            {"symbol": "COMI", "name_ar": "البنك التجاري الدولي", "sector": "Banks", "exchange": "EGX"},
                            {"symbol": "TMGH", "name_ar": "طلعت مصطفى", "sector": "Real Estate", "exchange": "EGX"},
                        ]})()
                    if name == "stock_prices":
                        return type("R", (), {"data": price_rows})()
                    if name == "positions":
                        return type("R", (), {"data": [
                            {"symbol": "COMI", "quantity": 600, "entry_price": 78.0},
                            {"symbol": "ABUK", "quantity": 200, "entry_price": 50.0},
                        ]})()
                    if name == "profiles":
                        return type("R", (), {"data": [{"cash_balance": 10000.0}]})()
                    return type("R", (), {"data": []})()
            return _Q()

    with mock.patch("api.agentic_chat.tools_execution._get_sb", return_value=_FakeSb()), mock.patch(
        "api.routers.offload_public._get_fair_value", return_value={"stocks": []}
    ):
        res = asyncio.run(
            dispatch_tool(
                "optimize_portfolio",
                {
                    "symbols": ["ABUK", "COMI", "TMGH"],
                    "capital": 100000,
                    "objective": "min_risk",
                    "max_weight_pct": 55,
                    "sharia_only": True,
                    "market": "EGX",
                },
                user_id="u-test",
            )
        )
        res_pf = asyncio.run(
            dispatch_tool(
                "optimize_portfolio",
                {"use_my_portfolio": True, "objective": "balanced", "max_weight_pct": 55},
                user_id="u-test",
            )
        )

    assert res["status"] == "success"
    assert res["currency"] == "ج.م"
    assert "COMI" in res["excludedNonSharia"]  # COMI excluded under EGX33 Sharia filter
    alloc_syms = {a["symbol"] for a in res["optimization"]["allocations"]}
    assert alloc_syms == {"ABUK", "TMGH"}
    assert res["optimization"]["investedAmount"] <= 100000.0
    assert "disclaimerAr" in res

    assert res_pf["status"] == "success"
    assert res_pf["optimization"]["hasExistingHoldings"] is True


def test_cash_reserve_absorption_and_no_buy_guards_on_real_portfolios():
    """
    Replay both real 2026-11-25 portfolios:
    1) OBRI (35% cap) + IDRE (excluded 0%) + MAAL (excluded 0%) -> must NEVER buy MAAL; 65% becomes Cash Reserve!
    2) ETEL (68.4% -> trimmed to 35%) + SWDY (19.9%) + MTIE (4.9% downtrend NO-BUY cap) -> must NEVER buy MTIE!
    """
    rets = _synthetic_returns(60)

    # Case 1: OBRI + IDRE (excluded) + MAAL (excluded)
    p1_assets = [
        AssetInput(
            symbol="OBRI", price=21.70, name_ar="العبور", sector="عقارات",
            current_shares=2585, expected_score=0.25, returns_by_date=rets["LOWV"],
            max_weight_override=0.35,
        ),
        AssetInput(
            symbol="IDRE", price=39.91, name_ar="رواد السياحة", sector="عقارات",
            current_shares=1426, expected_score=-0.85, returns_by_date=rets["HVA"],
            max_weight_override=0.0, exclusion_reason="مكرر ربحية متضخم مع اتجاه هابط — مستبعد من الشراء",
        ),
        AssetInput(
            symbol="MAAL", price=5.94, name_ar="مرسيليا", sector="عقارات",
            current_shares=1500, expected_score=-0.85, returns_by_date=rets["HVB"],
            max_weight_override=0.0, exclusion_reason="تقييم مالي ضعيف واتجاه هابط — مستبعد من الشراء",
        ),
    ]
    res1 = optimize_portfolio_or(
        p1_assets,
        total_capital=121916.16,
        objective="hrp",
        max_weight_pct=35.0,
        max_sector_pct=45.0,
        exchange="EGX",
    )
    by1 = {r["symbol"]: r for r in res1["allocations"]}
    assert by1["MAAL"]["action"] == "SELL"
    assert by1["MAAL"]["targetShares"] == 0
    assert by1["IDRE"]["action"] == "SELL"
    assert by1["IDRE"]["targetShares"] == 0
    assert by1["OBRI"]["actualWeightPct"] <= 35.5
    assert res1["leftoverCash"] >= 121916.16 * 0.64  # >= 64% Cash Reserve instead of buying MAAL!
    assert any("كاش احتياطي" in n for n in res1["constraints"]["relaxationNotes"])

    # Case 2: ETEL (68.4%) + SWDY (19.9%) + MTIE (4.9% capped at current weight due to full downtrend)
    p2_assets = [
        AssetInput(
            symbol="ETEL", price=140.84, name_ar="المصرية للاتصالات", sector="اتصالات",
            current_shares=1000, expected_score=0.45, returns_by_date=rets["LOWV"],
        ),
        AssetInput(
            symbol="SWDY", price=116.69, name_ar="السويدي", sector="صناعات هندسية",
            current_shares=352, expected_score=0.20, returns_by_date=rets["UNCR"],
        ),
        AssetInput(
            symbol="MTIE", price=6.60, name_ar="إم إم جروب", sector="توزيع",
            current_shares=1530, expected_score=0.10, returns_by_date=rets["HVA"],
            max_weight_override=0.049, exclusion_reason="مسار هابط تحت EMA50 وEMA200 — يُمنع التعزيز التلقائي",
        ),
    ]
    res2 = optimize_portfolio_or(
        p2_assets,
        total_capital=206012.88,
        objective="hrp",
        max_weight_pct=35.0,
        max_sector_pct=45.0,
        exchange="EGX",
    )
    by2 = {r["symbol"]: r for r in res2["allocations"]}
    assert by2["ETEL"]["action"] == "SELL"
    assert by2["ETEL"]["actualWeightPct"] <= 35.5
    assert by2["MTIE"]["action"] != "BUY"
    assert by2["MTIE"]["deltaShares"] <= 0
    assert res2["leftoverCash"] >= 206012.88 * 0.24  # Excess cash preserved instead of dumping into MTIE!

    assert res_pf["optimization"]["totalCapital"] == pytest.approx(600 * 82.0 + 200 * 55.0 + 10000.0, abs=1.0)


def test_numerical_safety_inf_nan_and_risk_parity_optimality():
    # 1. Inf price is skipped; NaN expected_score safely sanitized; Inf/negative capital rejected
    assets = _sample_assets()
    assets[0].expected_score = float("nan")
    bad_asset = AssetInput(symbol="INF1", price=float("inf"), sector="بنوك")
    # Unconstrained risk parity equalizes all 4 risk contributions tightly around ~25% each
    res_unc = optimize_portfolio_or(assets + [bad_asset], total_capital=100000.0, objective="risk_parity", max_weight_pct=95.0, max_sector_pct=100.0)
    assert all(a["symbol"] != "INF1" for a in res_unc["allocations"])
    assert math.isfinite(res_unc["investedAmount"])
    assert math.isfinite(res_unc["metricsAfter"]["annualVolatilityPct"])
    rc_vals = [a["riskContributionPct"] for a in res_unc["allocations"]]
    assert max(rc_vals) - min(rc_vals) < 1.5

    # Constrained risk parity (max_weight=50%) respects the cap while equalizing the unconstrained assets
    res_con = optimize_portfolio_or(assets, total_capital=100000.0, objective="risk_parity", max_weight_pct=50.0, max_sector_pct=70.0)
    assert max(a["targetWeightPct"] for a in res_con["allocations"]) <= 50.1
    non_capped_rc = [a["riskContributionPct"] for a in res_con["allocations"] if a["symbol"] != "LOWV"]
    assert max(non_capped_rc) - min(non_capped_rc) < 2.5

    with pytest.raises(ValueError):
        optimize_portfolio_or(assets, total_capital=float("inf"))
    with pytest.raises(ValueError):
        optimize_portfolio_or(assets, total_capital=-5000.0)


def test_tadawul_multimarket_routing_telegram_portfolio_capital_and_guards():
    from api.agentic_chat.tools_execution import _TG_PORTFOLIO_CTX, dispatch_tool
    from api.agentic_chat.user_preferences import SHARIA_FILTER_TOOLS
    from api.agentic_chat.analysis_cache import build_analysis_cache_key

    assert "optimize_portfolio" in SHARIA_FILTER_TOOLS
    assert build_analysis_cache_key("وزع 100000 على COMI") is None
    assert build_analysis_cache_key("توزيع رأس المال على COMI") is None
    assert build_analysis_cache_key("إعادة توازن COMI") is None
    assert build_analysis_cache_key("توزيعات أرباح COMI") == "vip_stock_COMI_divs"
    assert build_analysis_cache_key("توزيع كوبون ABUK") == "vip_stock_ABUK_divs"

    rets = _synthetic_returns(40)
    saudi_prices = []
    for sym, rmap in [("2222", rets["LOWV"]), ("1120", rets["UNCR"])]:
        px = 28.0 if sym == "2222" else 90.0
        for dt_s, r in sorted(rmap.items()):
            px = round(px * (1.0 + r), 2)
            saudi_prices.append({"symbol": sym, "date": dt_s, "close": px})

    selected_cols_seen = []

    class _StrictSchemaSb:
        def __init__(self, market_name: str):
            self.market_name = market_name

        def from_(self, name):
            outer = self

            class _Q:
                def select(self, cols, *_a, **_kw):
                    selected_cols_seen.append((outer.market_name, name, cols))
                    assert "sector_ar" not in cols, "stocks.sector_ar does not exist in DB!"
                    if name == "positions":
                        assert "current_price" not in cols, "positions.current_price does not exist in DB!"
                    return self

                def eq(self, *_a, **_kw): return self
                def in_(self, *_a, **_kw): return self
                def gte(self, *_a, **_kw): return self
                def order(self, *_a, **_kw): return self
                def limit(self, *_a, **_kw): return self

                def execute(self):
                    if name == "telegram_vip_chat_state":
                        return type("R", (), {"data": [{
                            "portfolio_state": {
                                "cash_balance": 5000.0,
                                "positions": [
                                    {"symbol": "2222", "quantity": 1000, "entry_price": 27.0},
                                    {"symbol": "1120", "quantity": 200, "entry_price": 85.0},
                                ],
                            }
                        }]})()
                    if name == "stock_technical_indicators" and outer.market_name == "TADAWUL":
                        return type("R", (), {"data": [
                            {"symbol": "2222", "close": 28.0, "rsi_14": 52.0, "ema_50": 27.5, "atr_14": 0.4, "exchange": "TADAWUL"},
                            {"symbol": "1120", "close": 90.0, "rsi_14": 57.0, "ema_50": 86.0, "atr_14": 1.6, "exchange": "TADAWUL"},
                        ]})()
                    if name == "stocks" and outer.market_name == "TADAWUL":
                        return type("R", (), {"data": [
                            {"symbol": "2222", "name_ar": "أرامكو السعودية", "sector": "Energy", "exchange": "TADAWUL"},
                            {"symbol": "1120", "name_ar": "مصرف الراجحي", "sector": "Banks", "exchange": "TADAWUL"},
                        ]})()
                    if name == "stock_prices" and outer.market_name == "TADAWUL":
                        return type("R", (), {"data": saudi_prices})()
                    return type("R", (), {"data": []})()

            return _Q()

    primary_sb = _StrictSchemaSb("PRIMARY")
    saudi_sb = _StrictSchemaSb("TADAWUL")

    with (
        mock.patch("api.agentic_chat.tools_execution._get_sb", return_value=primary_sb),
        mock.patch("api.agentic_chat.tools_execution._get_sb_for_market", side_effect=lambda m: saudi_sb if str(m).upper() in ("TADAWUL", "TASI") else primary_sb),
        mock.patch("api.agentic_chat.tools_execution._saudi_ti_select_and_order", return_value=("symbol,date,close,rsi_14,ema_50,atr_14,exchange", "date")),
        mock.patch("api.routers.offload_public._get_fair_value", return_value={"stocks": []}),
    ):
        # 1. Explicit capital <= 0 fails closed
        err_res = asyncio.run(dispatch_tool("optimize_portfolio", {"symbols": ["أرامكو", "الراجحي"], "capital": -100}, user_id=None))
        assert err_res["status"] == "error"

        # 2. Arabic Saudi names resolve cleanly to TADAWUL via _get_sb_for_market & 0.155% fee
        res_sa = asyncio.run(
            dispatch_tool("optimize_portfolio", {"symbols": ["أرامكو", "الراجحي"], "capital": 50000, "objective": "balanced", "max_weight_pct": 60}, user_id=None)
        )
        assert res_sa["status"] == "success"
        assert res_sa["exchange"] == "TADAWUL"
        assert res_sa["currency"] == "ر.س"
        assert res_sa["optimization"]["feeRatePct"] == pytest.approx(0.155, abs=1e-4)
        assert {a["symbol"] for a in res_sa["optimization"]["allocations"]} == {"2222", "1120"}

        # 3. Unlinked Telegram private user + partial top-up capital (20k < 46k holdings) preserves existing cash (5k)
        tok = _TG_PORTFOLIO_CTX.set(999111222)
        try:
            res_tg = asyncio.run(
                dispatch_tool("optimize_portfolio", {"use_my_portfolio": True, "capital": 20000, "max_weight_pct": 60}, user_id=None)
            )
        finally:
            _TG_PORTFOLIO_CTX.reset(tok)
        assert res_tg["status"] == "success"
        assert res_tg["optimization"]["hasExistingHoldings"] is True
        # holdings = 1000*28 + 200*90 = 46,000 + existing_cash 5,000 + top-up 20,000 = 71,000
        assert res_tg["optimization"]["totalCapital"] == pytest.approx(71000.0, abs=1.0)
        assert sum(a["currentWeightPct"] for a in res_tg["optimization"]["allocations"]) <= 100.0


def test_cash_reserve_absorption_and_no_buy_guards_on_real_portfolios():
    """Replay both real 2026-11-25 user portfolios to guarantee zero destructive BUY orders."""
    from api.portfolio_or_optimizer import AssetInput, build_smart_dca_plan, optimize_portfolio_or

    # Case 1: OBRI (healthy 46%) + IDRE (hard-excluded P/E 1606x) + MAAL (hard-excluded weak fund 37 + downtrend)
    assets_1 = [
        AssetInput(
            symbol="OBRI",
            price=18.29,
            sector="عقارات",
            current_shares=2400,
            expected_score=0.25,
            fallback_daily_vol=0.022,
        ),
        AssetInput(
            symbol="IDRE",
            price=44.50,
            sector="عقارات",
            current_shares=1000,
            expected_score=-0.85,
            fallback_daily_vol=0.028,
            max_weight_override=0.0,
            exclusion_reason="مكرر ربحية متضخم",
        ),
        AssetInput(
            symbol="MAAL",
            price=1.02,
            sector="عقارات",
            current_shares=6800,
            expected_score=-0.85,
            fallback_daily_vol=0.030,
            max_weight_override=0.0,
            exclusion_reason="تقييم مالي ضعيف (37/100) ومسار هابط",
        ),
    ]
    res_1 = optimize_portfolio_or(
        assets_1,
        total_capital=95332.0,
        objective="hrp",
        max_weight_pct=35.0,
        max_sector_pct=45.0,
        exchange="EGX",
    )
    by_sym_1 = {r["symbol"]: r for r in res_1["allocations"]}
    assert by_sym_1["IDRE"]["targetWeightPct"] == 0.0
    assert by_sym_1["IDRE"]["action"] == "SELL"
    assert by_sym_1["MAAL"]["targetWeightPct"] == 0.0
    assert by_sym_1["MAAL"]["action"] == "SELL"
    assert by_sym_1["OBRI"]["targetWeightPct"] <= 35.5
    assert res_1["leftoverCashPct"] >= 64.0
    assert any("كاش احتياطي" in n for n in res_1["constraints"]["relaxationNotes"])

    # Case 2: ETEL (68.4%) + SWDY (19.9%) + MTIE (4.9%, full downtrend capped at current weight) + 14,000 cash
    assets_2 = [
        AssetInput(
            symbol="ETEL",
            price=78.40,
            sector="اتصالات",
            current_shares=1800,
            expected_score=0.55,
            fallback_daily_vol=0.019,
        ),
        AssetInput(
            symbol="SWDY",
            price=82.00,
            sector="صناعة",
            current_shares=500,
            expected_score=0.40,
            fallback_daily_vol=0.021,
        ),
        AssetInput(
            symbol="MTIE",
            price=6.60,
            sector="اتصالات",
            current_shares=1545,
            expected_score=-0.10,
            fallback_daily_vol=0.026,
            max_weight_override=0.049,
            exclusion_reason="مسار هابط تحت EMA50 وEMA200 — يُمنع التعزيز التلقائي",
        ),
    ]
    res_2 = optimize_portfolio_or(
        assets_2,
        total_capital=206317.0,
        objective="hrp",
        max_weight_pct=35.0,
        max_sector_pct=45.0,
        exchange="EGX",
    )
    by_sym_2 = {r["symbol"]: r for r in res_2["allocations"]}
    assert by_sym_2["ETEL"]["targetWeightPct"] <= 35.5
    assert by_sym_2["MTIE"]["action"] != "BUY"
    assert by_sym_2["MTIE"]["deltaShares"] <= 0
    assert by_sym_2["MTIE"]["targetWeightPct"] <= 5.2
    assert res_2["leftoverCashPct"] >= 24.0

    # Case 3: Smart DCA blocks weak fundamentals (< 42/100, e.g. MAAL = 37)
    dca_maal = build_smart_dca_plan(
        symbol="MAAL",
        current_price=1.02,
        old_avg_price=1.35,
        old_shares=6800,
        dca_budget=10000.0,
        fund_score=37.0,
        setup_regime="watch_wait",
        exchange="EGX",
    )
    assert dca_maal["dca_allowed"] is False
    assert "37/100" in dca_maal["rejection_reason_ar"]


