import datetime as dt
import os
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import api.scanner_alerts_engine as sa_engine
import api.short_swings_engine as ss_engine
import scripts.saudi_backtest_and_systems as saudi_sys


def _make_ohlcv_bars(
    start: str = "2024-01-01",
    periods: int = 80,
    base_price: float = 20.0,
    drift: float = 0.002,
    volume: float = 2_000_000.0,
) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=periods)
    closes = [base_price * ((1.0 + drift) ** i) for i in range(periods)]
    opens = [c * 0.995 for c in closes]
    highs = [c * 1.015 for c in closes]
    lows = [c * 0.985 for c in closes]
    return pd.DataFrame(
        {
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": [volume] * periods,
        },
        index=dates,
    )


def test_saudi_parse_args_and_zero_arg_main_ignores_pytest_argv():
    ns_default = saudi_sys.parse_args([])
    assert ns_default.only_systems is False
    assert ns_default.only_models is False

    ns_sys = saudi_sys.parse_args(["--only-systems"])
    assert ns_sys.only_systems is True
    assert ns_sys.only_models is False

    ns_mod = saudi_sys.parse_args(["--only-models"])
    assert ns_mod.only_models is True
    assert ns_mod.only_systems is False

    fake_bars = {"1120": _make_ohlcv_bars(periods=90, base_price=80.0)}
    fake_idx = _make_ohlcv_bars(periods=90, base_price=11000.0).rename(
        columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    )
    fake_sb = MagicMock()
    with (
        patch.object(saudi_sys, "_init_saudi_client", return_value=fake_sb),
        patch.object(saudi_sys, "_load_saudi_stocks_meta", return_value=(["1120"], {"1120": {"name_ar": "الراجحي"}}, {"1120": {"symbol": "1120"}})),
        patch.object(saudi_sys, "_load_saudi_history_for_systems", return_value=(fake_idx, fake_bars, {})),
        patch.object(saudi_sys, "_build_saudi_backtests_dataset", return_value={"backtests": [], "models": [], "as_of": "2024-05-01"}) as m_bt,
        patch.object(saudi_sys, "_build_saudi_short_swings_dataset", return_value={"total_active": 0, "total_closed": 0, "kpis": {}}) as m_ss,
        patch.object(saudi_sys, "_build_saudi_scanner_alerts_dataset", return_value={"active_signals": [], "closed_signals": [], "signals_kpis": {}}) as m_sc,
        patch.object(saudi_sys, "_upsert_market_cache") as m_up,
    ):
        # Simulate scheduler invoking main() with zero args even while pytest cli has extra args
        out = saudi_sys.main()
        assert "backtests" in out and "short_swings" in out and "scanner_alerts" in out
        assert m_bt.call_count == 1
        assert m_ss.call_count == 1
        assert m_sc.call_count == 1
        assert m_up.call_count == 3


def test_short_swings_saudi_cache_isolation_and_snapshot_schema(tmp_path):
    egx_path = tmp_path / "egx_cache.json"
    sa_path = tmp_path / "saudi_cache.json"
    egx_path.write_text('{"status":"ok","market":"EGX","kpis":{},"closed_trades":[]}', encoding="utf-8")
    sa_path.write_text('{"status":"ok","market":"TASI","kpis":{},"closed_trades":[]}', encoding="utf-8")

    with (
        patch.object(ss_engine, "CACHE_PATHS", [egx_path]),
        patch.object(ss_engine, "SAUDI_CACHE_PATHS", [sa_path]),
        patch.object(ss_engine, "_restore_saudi_snapshot", return_value=None),
        patch.object(ss_engine, "_restore_saved_snapshot", return_value=None),
    ):
        assert ss_engine.get_cached_short_swings()["market"] == "EGX"
        assert ss_engine.get_cached_short_swings(exchange="TADAWUL")["market"] == "TASI"

    fake_table = MagicMock()
    fake_sb = MagicMock()
    fake_sb.table.return_value = fake_table
    fake_table.upsert.return_value = fake_table
    with patch.object(ss_engine, "_get_saudi_supabase_client", return_value=fake_sb):
        ss_engine._persist_saudi_snapshot({"status": "ok"})
    upsert_args, upsert_kwargs = fake_table.upsert.call_args
    assert upsert_args[0]["country"] == "Saudi Arabia"
    assert upsert_args[0]["cache_key"] == ss_engine.SAUDI_SHORT_SWINGS_CACHE_KEY
    assert "computed_at" in upsert_args[0]
    assert upsert_kwargs["on_conflict"] == "cache_key,country"


def test_scanner_alerts_causal_be_and_simulation_contract():
    # Build symbol passing Saudi institutional quality & liquidity filters (>=10 SAR, >=15M SAR,
    # strong green close_pos >= 0.70, healthy pre-breakout RSI <= 68), then arming BE (+2.5%)
    # on day 41 and pulling back on day 42 to lock +0.5% profit.
    bars_a = _make_ohlcv_bars(start="2024-01-01", periods=60, base_price=10.0, drift=0.0, volume=500_000.0)
    # Mild pullback sequence on days 34..39 so Wilder RSI stays <= 68 on the breakout bar
    pre_closes = [10.30, 10.10, 9.90, 9.75, 9.90, 10.00]
    for offset, px in enumerate(pre_closes):
        idx = 34 + offset
        bars_a.iloc[idx, bars_a.columns.get_loc("Open")] = px
        bars_a.iloc[idx, bars_a.columns.get_loc("Close")] = px
        bars_a.iloc[idx, bars_a.columns.get_loc("High")] = px + 0.05
        bars_a.iloc[idx, bars_a.columns.get_loc("Low")] = px - 0.05

    # Trigger volume_surge on day 40 (+4.5% gain, ~4x vol, 20.9M SAR turnover, close_pos=1.0)
    i = 40
    bars_a.iloc[i, bars_a.columns.get_loc("Open")] = 10.00
    bars_a.iloc[i, bars_a.columns.get_loc("Close")] = 10.45
    bars_a.iloc[i, bars_a.columns.get_loc("High")] = 10.45
    bars_a.iloc[i, bars_a.columns.get_loc("Low")] = 9.98
    bars_a.iloc[i, bars_a.columns.get_loc("Volume")] = 2_000_000.0
    # Next day (+2.87% close, High < T1=10.85 -> arms BE strictly on previous close when causal)
    bars_a.iloc[i + 1, bars_a.columns.get_loc("Open")] = 10.50
    bars_a.iloc[i + 1, bars_a.columns.get_loc("Close")] = 10.75
    bars_a.iloc[i + 1, bars_a.columns.get_loc("High")] = 10.80
    bars_a.iloc[i + 1, bars_a.columns.get_loc("Low")] = 10.42
    # Day i+2 pulls back below +0.5% locked BE floor (10.502) -> closes as target_hit with +0.5% profit
    bars_a.iloc[i + 2, bars_a.columns.get_loc("Close")] = 10.35
    bars_a.iloc[i + 2, bars_a.columns.get_loc("Low")] = 10.30

    res = sa_engine.run_scanner_alerts_simulation(
        {"1120": bars_a},
        meta={"1120": {"name_ar": "الراجحي", "name_en": "Al Rajhi", "sector": "البنوك"}},
        exchange="TADAWUL",
        start_date="2024-02-01",
        causal_be_prev_only=True,
    )
    assert res["ok"] is True
    assert res["market"] == "TASI"
    assert res["currency"] == "SAR"
    assert isinstance(res["signals_kpis"], dict)
    assert res["signals_kpis"]["total_closed"] >= 1
    be_hits = [sig for sig in res["closed_signals"] if sig["symbol"] == "1120" and sig["status"] == "target_hit"]
    assert be_hits, f"Expected TADAWUL locked-BE target_hit signal, got: {res['closed_signals']}"
    assert all(sig["return_pct"] > 0 for sig in be_hits)


def test_short_swings_saudi_exit_labels_and_profile_separation():
    from api import short_swings_engine as ss_engine

    assert "ema20_break" in ss_engine.EXIT_REASON_LABELS
    assert "EMA20" in ss_engine.EXIT_REASON_LABELS["ema20_break"]
    assert sa_engine.SAUDI_SCANNER_PROFILES["volume_surge"]["be_lock_pct"] == 0.5
    assert sa_engine.SAUDI_SCANNER_PROFILES["breakout"]["max_sessions"] == 6


def test_simulate_radar_strategy_backtest_uses_strategy_engine_and_trailing_stops():
    # Use realistic oscillatory uptrend so RSI stays in 45..65 band (passes StrategyEngine RSI filter)
    dates = pd.bdate_range(start="2021-10-01", periods=180)
    closes = [20.0 * ((1.0018) ** i) * (1.0 + 0.015 * np.sin(i / 2.5)) for i in range(180)]
    bars = pd.DataFrame(
        {
            "Open": [c * 0.996 for c in closes],
            "High": [c * 1.022 for c in closes],
            "Low": [c * 0.985 for c in closes],
            "Close": closes,
            "Volume": [2_000_000.0 + (i % 5) * 400_000.0 for i in range(180)],
        },
        index=dates,
    )
    sub_bars = {"1120": bars}
    market_df = _make_ohlcv_bars(start="2021-10-01", periods=180, base_price=10000.0, drift=0.002, volume=100_000_000.0).rename(
        columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    )
    df_all = pd.DataFrame({
        "symbol": ["1120"] * len(bars),
        "date_str": [ts.strftime("%Y-%m-%d") for ts in bars.index],
        "prob": [0.80] * len(bars),
    })
    market_cache = saudi_sys._prepare_market_and_signal_cache(sub_bars, market_df, min_turnover=1_000_000.0)
    bt = saudi_sys.simulate_radar_strategy_backtest(
        model_name="KING_TASI",
        df_all=df_all,
        prob_col="prob",
        threshold=0.5,
        sub_bars=sub_bars,
        market_cache=market_cache,
        meta={"1120": {"name_ar": "الراجحي", "name_en": "Al Rajhi", "sector": "البنوك"}},
        start_date="2022-01-01",
        index_gate="above_ema50",
        use_trend_filter=True,
        adaptive_exits=True,
        min_turnover=1_000_000.0,
        now_iso="2026-11-14T00:00:00Z",
    )
    assert bt["model_name"] == "KING_TASI"
    assert bt["exchange"] == "TADAWUL"
    assert bt["total_trades"] >= 1
    assert "exit_reason_code" in bt["trades"][0]
