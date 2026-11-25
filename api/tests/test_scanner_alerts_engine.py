import pytest

from api.scanner_alerts_engine import (
    compute_scanner_signals_kpis,
    evaluate_scanner_candidates,
    step_scanner_lifecycle,
)


def _sample_cand(sym="COMI", close=100.0):
    return {"symbol": sym, "close": close, "change_pct": 3.5, "r_vol": 2.4, "rsi_14": 58.0}


def test_intraday_live_ignores_pre_signal_morning_ohlc_on_entry_day():
    """Morning low/high from daily stock_prices must never stop-out or arm BE on an intraday entry on entry_date."""
    active, closed, hits, stops = step_scanner_lifecycle(
        [],
        [],
        {},
        final_vol=[_sample_cand("DSCW", 1.64)],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-15",
        action_date="2026-11-15",
        action_time="14:18",
        now_iso="2026-11-15T12:18:00Z",
        causal_be_prev_only=False,
        intraday_live=True,
    )
    assert len(active) == 1
    assert active[0]["entry_price"] == 1.64

    # Next 15m tick on the same day: quote is still 1.64, even though full-day low was 1.55 (from 10:15 AM)
    # and full-day high was 1.75 (from 10:30 AM). Signal must remain active with unchanged highest/lowest!
    latest = {"DSCW": {"close": 1.64, "high": 1.75, "low": 1.55}}
    active, closed, hits, stops = step_scanner_lifecycle(
        active,
        closed,
        latest,
        final_vol=[],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-15",
        action_date="2026-11-15",
        action_time="14:20",
        now_iso="2026-11-15T12:20:00Z",
        causal_be_prev_only=False,
        intraday_live=True,
    )
    assert len(active) == 1
    assert len(closed) == 0
    assert not hits and not stops
    assert active[0]["highest_price"] == 1.64
    assert active[0]["lowest_price"] == 1.64

    # Later tick observes actual price rally >= +2.5% -> arms BE for NEXT tick, not retroactively on same tick
    latest_up = {"DSCW": {"close": 1.69, "high": 1.75, "low": 1.55}}
    active, closed, hits, stops = step_scanner_lifecycle(
        active,
        closed,
        latest_up,
        final_vol=[],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-15",
        action_date="2026-11-15",
        action_time="14:22",
        now_iso="2026-11-15T12:22:00Z",
        causal_be_prev_only=False,
        intraday_live=True,
    )
    assert len(active) == 1
    assert active[0]["stop_loss"] == pytest.approx(1.648, abs=0.002)

    # Subsequent tick reverses to locked BE stop (+0.5% on EGX -> 1.648) -> closes at +0.49% protection
    latest_be = {"DSCW": {"close": 1.648, "high": 1.75, "low": 1.55}}
    active, closed, hits, stops = step_scanner_lifecycle(
        active,
        closed,
        latest_be,
        final_vol=[],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-15",
        action_date="2026-11-15",
        action_time="14:24",
        now_iso="2026-11-15T12:24:00Z",
        causal_be_prev_only=False,
        intraday_live=True,
    )
    assert len(active) == 0
    assert len(closed) == 1
    assert closed[0]["return_pct"] == pytest.approx(0.49, abs=0.05)
    assert closed[0].get("is_breakeven") is True
    assert "التعادل" in closed[0]["exit_reason"]


def test_intraday_live_day2_multi_tick_keeps_sessions_count_at_two():
    """Calling step_scanner_lifecycle multiple times on Day 2 must keep sessions_count == 2 (Sun -> Mon)."""
    active, closed, _, _ = step_scanner_lifecycle(
        [],
        [],
        {},
        final_vol=[_sample_cand("COMI", 100.0)],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-15",
        action_date="2026-11-15",
        action_time="11:00",
        now_iso="2026-11-15T09:00:00Z",
        intraday_live=True,
    )
    latest = {"COMI": {"close": 101.0, "high": 102.0, "low": 99.5}}
    for hhmm in ("10:15", "10:30", "10:45", "11:00", "11:15"):
        active, closed, _, _ = step_scanner_lifecycle(
            active,
            closed,
            latest,
            final_vol=[],
            final_bo=[],
            final_os=[],
            as_of_date="2026-11-16",
            action_date="2026-11-16",
            action_time=hhmm,
            now_iso=f"2026-11-16T{hhmm}:00Z",
            intraday_live=True,
        )
    assert len(active) == 1
    assert active[0]["sessions_count"] == 2


def test_allow_new_entries_false_blocks_closing_bell_entries_but_manages_exits():
    """After 14:25, allow_new_entries=False stops opening late entries while allowing target exits."""
    existing = [{
        "id": "COMI_2026-11-12_volume_surge",
        "symbol": "COMI",
        "scanner_type": "volume_surge",
        "entry_price": 100.0,
        "entry_date": "2026-11-12",
        "target_1": 104.5,
        "stop_loss": 97.0,
        "current_price": 101.0,
        "highest_price": 101.0,
        "lowest_price": 99.0,
        "sessions_count": 2,
        "max_sessions": 4,
    }]
    latest = {"COMI": {"close": 105.0, "high": 105.0, "low": 100.0}}
    active, closed, hits, _ = step_scanner_lifecycle(
        existing,
        [],
        latest,
        final_vol=[_sample_cand("MICH", 50.0)],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-15",
        action_date="2026-11-15",
        action_time="14:34",
        now_iso="2026-11-15T12:34:00Z",
        intraday_live=True,
        allow_new_entries=False,
    )
    assert len(hits) == 1
    assert len(closed) == 1
    assert active == []


def test_evaluate_scanner_candidates_quality_filters_and_sniper_regime():
    """Penny stocks, red candles, overheated tops, and low turnover must be rejected; weak breadth cuts limit to 1."""
    rows = {
        "PENNY": {"open": 0.08, "close": 0.09, "change_pct": 5.0, "volume": 5000000, "r_vol": 3.0, "rsi_14": 60, "ema_20": 0.08, "bb_upper": 0.085},
        "REDCND": {"open": 50.0, "close": 49.0, "change_pct": 3.0, "volume": 100000, "r_vol": 3.0, "rsi_14": 60, "ema_20": 48.0, "bb_upper": 49.5},
        "HOTTOP": {"open": 48.0, "close": 50.0, "change_pct": 4.0, "volume": 100000, "r_vol": 3.0, "rsi_14": 86.0, "ema_20": 44.0, "bb_upper": 49.0},
        "PARABOL": {"open": 45.0, "close": 50.0, "change_pct": 9.8, "volume": 100000, "r_vol": 3.5, "rsi_14": 68.0, "ema_20": 43.0, "bb_upper": 49.0},
        "THIN": {"open": 2.0, "close": 2.10, "change_pct": 3.5, "volume": 60000, "r_vol": 3.0, "rsi_14": 58.0, "ema_20": 2.0, "bb_upper": 2.2},
        "GOOD1": {"open": 48.5, "close": 50.0, "change_pct": 3.1, "volume": 100000, "r_vol": 2.8, "rsi_14": 60.0, "ema_20": 47.0, "bb_upper": 51.0},
        "GOOD2": {"open": 29.0, "close": 30.0, "change_pct": 3.2, "volume": 100000, "r_vol": 2.5, "rsi_14": 61.0, "ema_20": 28.0, "bb_upper": 31.0},
        # Weak-breadth drag stocks so breadth < 30% triggers Sniper Mode (max 1 per category)
        "DRAG1": {"open": 10.0, "close": 9.8, "change_pct": -2.0, "volume": 100000, "r_vol": 1.0, "rsi_14": 40.0, "ema_20": 11.0, "bb_upper": 12.0},
        "DRAG2": {"open": 10.0, "close": 9.7, "change_pct": -3.0, "volume": 100000, "r_vol": 1.0, "rsi_14": 40.0, "ema_20": 11.0, "bb_upper": 12.0},
        "DRAG3": {"open": 10.0, "close": 9.6, "change_pct": -4.0, "volume": 100000, "r_vol": 1.0, "rsi_14": 40.0, "ema_20": 11.0, "bb_upper": 12.0},
        "DRAG4": {"open": 10.0, "close": 9.5, "change_pct": -5.0, "volume": 100000, "r_vol": 1.0, "rsi_14": 40.0, "ema_20": 11.0, "bb_upper": 12.0},
        "DRAG5": {"open": 10.0, "close": 9.4, "change_pct": -6.0, "volume": 100000, "r_vol": 1.0, "rsi_14": 40.0, "ema_20": 11.0, "bb_upper": 12.0},
        "DRAG6": {"open": 10.0, "close": 9.3, "change_pct": -7.0, "volume": 100000, "r_vol": 1.0, "rsi_14": 40.0, "ema_20": 11.0, "bb_upper": 12.0},
        "DRAG7": {"open": 10.0, "close": 9.2, "change_pct": -8.0, "volume": 100000, "r_vol": 1.0, "rsi_14": 40.0, "ema_20": 11.0, "bb_upper": 12.0},
        "DRAG8": {"open": 10.0, "close": 9.1, "change_pct": -9.0, "volume": 100000, "r_vol": 1.0, "rsi_14": 40.0, "ema_20": 11.0, "bb_upper": 12.0},
        "DRAG9": {"open": 10.0, "close": 9.0, "change_pct": -10.0, "volume": 100000, "r_vol": 1.0, "rsi_14": 40.0, "ema_20": 11.0, "bb_upper": 12.0},
        "DRAG10": {"open": 10.0, "close": 9.0, "change_pct": -10.0, "volume": 100000, "r_vol": 1.0, "rsi_14": 40.0, "ema_20": 11.0, "bb_upper": 12.0},
    }
    res = evaluate_scanner_candidates(rows, force=True, limit_per_category=2)
    assert res["is_market_healthy"] is False
    # Sniper mode caps at 1 per category and picks highest r_vol valid candidate GOOD1
    assert [s["symbol"] for s in res["final_vol"]] == ["GOOD1"]
    assert res["final_bo"] == []


def test_compute_scanner_signals_kpis_excludes_flat_breakeven_from_losses():
    closed = [
        {"return_pct": 4.5, "max_gain_pct": 5.0},
        {"return_pct": 3.5, "max_gain_pct": 4.0},
        {"return_pct": -2.5, "max_gain_pct": 0.5},
        {"return_pct": 0.0, "max_gain_pct": 2.8},
        {"return_pct": 0.0, "max_gain_pct": 3.1},
        {"return_pct": 0.0, "max_gain_pct": 2.6},
    ]
    kpis = compute_scanner_signals_kpis(closed, [])
    assert kpis["total_closed"] == 6
    # 2 wins / (2 wins + 1 loss) = 66.7% (not 2/6 = 33.3%)
    assert kpis["win_rate_pct"] == pytest.approx(66.7, abs=0.1)


def test_saudi_evaluate_scanner_candidates_filters_and_caps():
    """TADAWUL scanner enforces >=10 SAR, breadth-adaptive >=3M/5M SAR, close_pos>=0.70, EMA50 trend, 2<=ch<=7.5%, RSI<=70/72, no RSI oversold, max 1/cat."""
    rows = {
        "SUB10": {"open": 9.1, "high": 9.6, "low": 9.0, "close": 9.5, "change_pct": 4.8, "volume": 3_000_000, "r_vol": 3.5, "rsi_14": 60.0, "ema_20": 9.0, "ema_50": 8.8, "bb_upper": 9.6},
        "LOWSAR": {"open": 19.0, "high": 20.0, "low": 18.9, "close": 20.0, "change_pct": 4.8, "volume": 100_000, "r_vol": 3.5, "rsi_14": 60.0, "ema_20": 19.0, "ema_50": 18.5, "bb_upper": 20.5},
        "WICKY": {"open": 48.0, "high": 52.0, "low": 48.0, "close": 50.0, "change_pct": 4.8, "volume": 600_000, "r_vol": 3.5, "rsi_14": 60.0, "ema_20": 47.0, "ema_50": 45.0, "bb_upper": 51.0},
        "DOWN50": {"open": 48.0, "high": 50.0, "low": 47.9, "close": 50.0, "change_pct": 4.8, "volume": 600_000, "r_vol": 3.5, "rsi_14": 60.0, "ema_20": 48.0, "ema_50": 52.0, "bb_upper": 51.0},
        "CHASE": {"open": 46.5, "high": 50.0, "low": 46.5, "close": 50.0, "change_pct": 7.8, "volume": 600_000, "r_vol": 3.5, "rsi_14": 60.0, "ema_20": 46.0, "ema_50": 44.0, "bb_upper": 49.0},
        "HOTRSI": {"open": 47.8, "high": 50.0, "low": 47.7, "close": 50.0, "change_pct": 4.5, "volume": 600_000, "r_vol": 3.5, "rsi_14": 73.0, "ema_20": 47.0, "ema_50": 45.0, "bb_upper": 51.0},
        "OVERSOLD": {"open": 31.0, "high": 31.5, "low": 30.0, "close": 30.5, "change_pct": -1.5, "volume": 800_000, "r_vol": 2.5, "rsi_14": 25.0, "ema_20": 33.0, "ema_50": 35.0, "bb_upper": 34.0},
        "VALID1": {"open": 47.8, "high": 50.0, "low": 47.7, "close": 50.0, "change_pct": 4.6, "volume": 600_000, "r_vol": 3.2, "rsi_14": 62.0, "ema_20": 47.5, "ema_50": 45.0, "bb_upper": 51.0},
        "VALID2": {"open": 28.7, "high": 30.0, "low": 28.6, "close": 30.0, "change_pct": 4.4, "volume": 800_000, "r_vol": 2.6, "rsi_14": 60.0, "ema_20": 28.5, "ema_50": 27.0, "bb_upper": 31.0},
        "VALIDBO": {"open": 38.8, "high": 40.0, "low": 38.7, "close": 40.0, "change_pct": 3.0, "volume": 600_000, "r_vol": 2.4, "rsi_14": 61.0, "ema_20": 38.0, "ema_50": 36.0, "bb_upper": 39.5},
    }
    res = evaluate_scanner_candidates(rows, force=True, limit_per_category=3, exchange="TADAWUL")
    assert [s["symbol"] for s in res["final_vol"]] == ["VALID1"]
    assert [s["symbol"] for s in res["final_bo"]] == ["VALIDBO"]
    assert res["final_os"] == []


def test_saudi_evaluate_scanner_candidates_weak_breadth_raises_gates():
    """Weak breadth (is_market_healthy=False) raises TADAWUL turnover to >=5M SAR and vol r_vol to >=2.0."""
    rows = {
        f"WEAK{i}": {"open": 20.5, "high": 20.6, "low": 19.5, "close": 19.8, "change_pct": -2.5, "volume": 300_000, "r_vol": 1.1, "rsi_14": 38.0, "ema_20": 21.0, "ema_50": 22.0}
        for i in range(1, 10)
    }
    rows.update({
        "SUB5M": {"open": 19.2, "high": 20.1, "low": 19.1, "close": 20.0, "change_pct": 4.2, "volume": 200_000, "r_vol": 2.8, "rsi_14": 60.0, "ema_20": 19.0, "ema_50": 18.0, "bb_upper": 20.5},
        "LOWRVOL": {"open": 28.8, "high": 30.0, "low": 28.7, "close": 30.0, "change_pct": 4.2, "volume": 200_000, "r_vol": 1.9, "rsi_14": 60.0, "ema_20": 28.5, "ema_50": 27.0, "bb_upper": 31.0},
        "GOOD6M": {"open": 28.8, "high": 30.0, "low": 28.7, "close": 30.0, "change_pct": 4.2, "volume": 220_000, "r_vol": 2.1, "rsi_14": 60.0, "ema_20": 28.5, "ema_50": 27.0, "bb_upper": 31.0},
    })
    res = evaluate_scanner_candidates(rows, force=True, limit_per_category=3, exchange="TADAWUL")
    assert res["is_market_healthy"] is False
    assert [s["symbol"] for s in res["final_vol"]] == ["GOOD6M"]


def test_saudi_scanner_lifecycle_be_lock_and_six_session_expiry():
    """TADAWUL arms locked BE at +0.5% (while keeping stop_loss_pct=0.0 for UI badge) and expires at 6 sessions."""
    active, closed, _, _ = step_scanner_lifecycle(
        [],
        [],
        {},
        final_vol=[_sample_cand("1120", 100.0)],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-10",
        action_date="2026-11-10",
        action_time="14:40",
        now_iso="2026-11-10T11:40:00Z",
        causal_be_prev_only=True,
        intraday_live=False,
        exchange="TADAWUL",
    )
    assert len(active) == 1
    assert active[0]["max_sessions"] == 6

    # Day 2 reaches +3.0% (below T1=3.8%) -> next session has BE armed at 100.5 (+0.5%)
    active, closed, _, _ = step_scanner_lifecycle(
        active,
        closed,
        {"1120": {"close": 103.0, "high": 103.2, "low": 100.1}},
        final_vol=[],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-11",
        action_date="2026-11-11",
        action_time="14:40",
        now_iso="2026-11-11T11:40:00Z",
        causal_be_prev_only=True,
        intraday_live=False,
        exchange="TADAWUL",
    )
    assert len(active) == 1
    assert active[0]["stop_loss"] == pytest.approx(100.5, abs=0.01)
    assert active[0]["stop_loss_pct"] == 0.0

    # Day 3 pulls back below 100.5 -> exits at 100.5 (+0.5%)
    active, closed, hits, _ = step_scanner_lifecycle(
        active,
        closed,
        {"1120": {"close": 100.1, "high": 101.0, "low": 99.8}},
        final_vol=[],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-12",
        action_date="2026-11-12",
        action_time="14:40",
        now_iso="2026-11-12T11:40:00Z",
        causal_be_prev_only=True,
        intraday_live=False,
        exchange="TADAWUL",
    )
    assert active == []
    assert len(hits) == 1
    assert closed[0]["return_pct"] == pytest.approx(0.5, abs=0.05)

    # Expiry label at session 6 must dynamically read "6 جلسات"
    exp_sig = [{
        "id": "2222_2026-11-01_breakout",
        "symbol": "2222",
        "scanner_type": "breakout",
        "entry_price": 30.0,
        "entry_date": "2026-11-01",
        "target_1": 31.35,
        "stop_loss": 28.95,
        "stop_loss_pct": 3.5,
        "current_price": 30.2,
        "highest_price": 30.5,
        "lowest_price": 29.8,
        "sessions_count": 5,
        "max_sessions": 6,
    }]
    active2, closed2, _, _ = step_scanner_lifecycle(
        exp_sig,
        [],
        {"2222": {"close": 29.8, "high": 30.1, "low": 29.7}},
        final_vol=[],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-12",
        action_date="2026-11-12",
        action_time="14:40",
        now_iso="2026-11-12T11:40:00Z",
        causal_be_prev_only=True,
        intraday_live=False,
        exchange="TADAWUL",
    )
    assert active2 == []
    assert len(closed2) == 1
    assert closed2[0]["status"] == "expired"
    assert "6 جلسات" in closed2[0]["exit_reason"]


def test_scanner_flat_breakeven_not_reported_as_target_hit_and_empty_kpis_zero():
    """A flat 0.0% BE exit gets status='breakeven' and stays out of hit_target_signals; empty KPIs return 0.0."""
    legacy_flat = [{
        "id": "COMI_2026-11-10_volume_surge",
        "symbol": "COMI",
        "scanner_type": "volume_surge",
        "entry_price": 100.0,
        "entry_date": "2026-11-10",
        "target_1": 104.5,
        "stop_loss": 100.0,
        "be_lock_pct": 0.0,
        "current_price": 102.6,
        "highest_price": 103.0,
        "lowest_price": 99.8,
        "sessions_count": 1,
        "max_sessions": 4,
    }]
    active, closed, hits, stops = step_scanner_lifecycle(
        legacy_flat,
        [],
        {"COMI": {"open": 101.0, "high": 101.5, "low": 99.5, "close": 100.0}},
        final_vol=[],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-11",
        action_date="2026-11-11",
        action_time="14:15",
        now_iso="2026-11-11T12:15:00Z",
        causal_be_prev_only=True,
        intraday_live=False,
    )
    assert active == [] and hits == [] and stops == []
    assert len(closed) == 1
    assert closed[0]["status"] == "breakeven"
    assert closed[0]["is_breakeven"] is True

    empty_kpis = compute_scanner_signals_kpis([], [])
    assert empty_kpis["win_rate_pct"] == 0.0
    assert empty_kpis["strict_win_rate_pct"] == 0.0
    assert empty_kpis["profit_factor"] == 0.0


def test_scanner_egx_breakout_hardening_regime_gate_and_cross_system_dedup():
    """EGX breakout rejects below-EMA50 / upper-wick / extended chasing; downtrend allows RSI oversold only; Saudi blocks all; blocked_symbols suppresses duplicates."""
    rows = {
        "BELOW50": {"open": 48.0, "high": 50.1, "low": 47.9, "close": 50.0, "change_pct": 3.5, "volume": 120_000, "r_vol": 2.5, "rsi_14": 60.0, "ema_20": 48.0, "ema_50": 52.0, "bb_upper": 49.5},
        "WICKBO": {"open": 48.0, "high": 53.0, "low": 47.5, "close": 50.0, "change_pct": 3.5, "volume": 120_000, "r_vol": 2.5, "rsi_14": 60.0, "ema_20": 48.0, "ema_50": 46.0, "bb_upper": 49.5},
        "EXTBO": {"open": 55.0, "high": 57.5, "low": 54.8, "close": 57.0, "change_pct": 4.0, "volume": 120_000, "r_vol": 2.5, "rsi_14": 68.0, "ema_20": 49.0, "ema_50": 45.0, "bb_upper": 56.0},
        "DUPVOL": {"open": 48.5, "high": 50.2, "low": 48.4, "close": 50.0, "change_pct": 3.1, "volume": 150_000, "r_vol": 3.8, "rsi_14": 60.0, "ema_20": 48.0, "ema_50": 46.0, "bb_upper": 51.0},
        "GOODVOL1": {"open": 48.5, "high": 50.2, "low": 48.4, "close": 50.0, "change_pct": 3.1, "volume": 150_000, "r_vol": 3.4, "rsi_14": 60.0, "ema_20": 48.0, "ema_50": 46.0, "bb_upper": 55.0},
        "GOODVOL2": {"open": 29.0, "high": 30.1, "low": 28.9, "close": 30.0, "change_pct": 3.0, "volume": 150_000, "r_vol": 3.0, "rsi_14": 58.0, "ema_20": 28.5, "ema_50": 27.0, "bb_upper": 33.0},
        "VALIDBO": {"open": 39.0, "high": 40.2, "low": 38.8, "close": 40.0, "change_pct": 3.2, "volume": 120_000, "r_vol": 2.3, "rsi_14": 61.0, "ema_20": 38.5, "ema_50": 36.0, "bb_upper": 39.5},
        "DEEPOS": {"open": 19.6, "high": 20.1, "low": 19.5, "close": 20.0, "change_pct": 2.0, "volume": 100_000, "r_vol": 1.6, "rsi_14": 23.0, "ema_20": 21.5, "ema_50": 23.0, "bb_upper": 23.0},
    }
    res_healthy = evaluate_scanner_candidates(rows, force=True, limit_per_category=2, exchange="EGX", blocked_symbols={"DUPVOL.CA"})
    assert [s["symbol"] for s in res_healthy["final_vol"]] == ["GOODVOL1", "GOODVOL2"]
    assert [s["symbol"] for s in res_healthy["final_bo"]] == ["VALIDBO"]
    assert all(s["symbol"] != "DUPVOL" for s in res_healthy["final_vol"])

    # In confirmed EGX downtrend: momentum breakout/volume_surge are stopped; strong oversold rebound still allowed (capped at 1)
    res_down = evaluate_scanner_candidates(rows, force=True, limit_per_category=2, exchange="EGX", market_downtrend=True)
    assert res_down["final_vol"] == []
    assert res_down["final_bo"] == []
    assert [s["symbol"] for s in res_down["final_os"]] == ["DEEPOS"]

    # In confirmed TADAWUL bear/panic downtrend: ALL entries are blocked
    saudi_rows = {
        "1120": {"open": 48.0, "high": 50.0, "low": 47.9, "close": 50.0, "change_pct": 4.2, "volume": 500_000, "r_vol": 3.0, "rsi_14": 60.0, "ema_20": 47.0, "ema_50": 45.0, "bb_upper": 49.0},
    }
    res_sa_down = evaluate_scanner_candidates(saudi_rows, force=True, limit_per_category=2, exchange="TADAWUL", market_downtrend=True)
    assert res_sa_down["final_vol"] == []
    assert res_sa_down["final_bo"] == []
    assert res_sa_down["final_os"] == []

    # step_scanner_lifecycle also respects blocked_symbols
    active_b, _, _, _ = step_scanner_lifecycle(
        [],
        [],
        {},
        final_vol=[_sample_cand("COMI", 100.0), _sample_cand("ETEL", 40.0)],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-25",
        action_date="2026-11-25",
        action_time="11:00",
        now_iso="2026-11-25T09:00:00Z",
        blocked_symbols={"COMI"},
    )
    assert [s["symbol"] for s in active_b] == ["ETEL"]


def test_scanner_lifecycle_stop_checked_conservatively_before_target_and_gap_down():
    """When a daily bar hits both SL and T1 without gapping above T1, stop-loss wins; gap-down fills at open."""
    existing = [{
        "id": "COMI_2026-11-10_volume_surge",
        "symbol": "COMI",
        "scanner_type": "volume_surge",
        "entry_price": 100.0,
        "entry_date": "2026-11-10",
        "target_1": 104.5,
        "stop_loss": 97.0,
        "stop_loss_pct": 3.0,
        "current_price": 100.5,
        "highest_price": 101.0,
        "lowest_price": 99.0,
        "sessions_count": 1,
        "max_sessions": 4,
    }]
    # Ambiguous wide candle opens below SL (gap-down 95.0) even though intraday high reaches 105.0
    active, closed, hits, stops = step_scanner_lifecycle(
        existing,
        [],
        {"COMI": {"open": 95.0, "high": 105.0, "low": 94.0, "close": 104.8}},
        final_vol=[],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-11",
        action_date="2026-11-11",
        action_time="14:30",
        now_iso="2026-11-11T12:30:00Z",
        causal_be_prev_only=True,
        intraday_live=False,
    )
    assert active == []
    assert hits == []
    assert len(stops) == 1
    assert closed[0]["status"] == "stopped_out"
    assert closed[0]["exit_price"] == pytest.approx(95.0, abs=0.01)
    assert closed[0]["return_pct"] == pytest.approx(-5.0, abs=0.05)


def test_scanner_lifecycle_rebases_when_confirmed_and_freezes_when_unconfirmed():
    """Confirmed corporate action rebases scanner levels & stays active; unconfirmed extreme gap freezes without fake stop or target drop."""
    existing = [{
        "id": "INEG_2026-11-18_volume_surge",
        "symbol": "INEG",
        "scanner_type": "volume_surge",
        "entry_price": 20.0,
        "entry_date": "2026-11-18",
        "target_1": 20.9,
        "stop_loss": 19.4,
        "stop_loss_pct": 3.0,
        "current_price": 20.0,
        "highest_price": 20.2,
        "lowest_price": 19.8,
        "sessions_count": 1,
        "max_sessions": 4,
    }]
    # Confirmed corporate action -> rebases entry/target/stop (factor=12.6/20=0.63) and stays active
    active_c, closed_c, hits_c, stops_c = step_scanner_lifecycle(
        existing,
        [],
        {"INEG": {"open": 12.5, "high": 12.7, "low": 12.45, "close": 12.6}},
        final_vol=[],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-19",
        action_date="2026-11-19",
        action_time="14:30",
        now_iso="2026-11-19T12:30:00Z",
        causal_be_prev_only=True,
        intraday_live=False,
        confirmed_action_dates={"INEG": ["2026-11-19"]},
    )
    assert len(active_c) == 1
    assert active_c[0]["entry_price"] == pytest.approx(12.6, abs=0.05)
    assert active_c[0]["target_1"] == pytest.approx(13.17, abs=0.05)
    assert active_c[0]["stop_loss"] == pytest.approx(12.22, abs=0.05)
    assert active_c[0]["rebased_factor"] == pytest.approx(0.63, abs=0.01)
    assert closed_c == [] and hits_c == [] and stops_c == []

    # Unconfirmed discontinuity -> freezes with original barriers, no stop-out, no blind target reduction
    active_u, closed_u, hits_u, stops_u = step_scanner_lifecycle(
        existing,
        [],
        {"INEG": {"open": 12.5, "high": 12.7, "low": 12.45, "close": 12.6}},
        final_vol=[],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-19",
        action_date="2026-11-19",
        action_time="14:30",
        now_iso="2026-11-19T12:30:00Z",
        causal_be_prev_only=True,
        intraday_live=False,
        confirmed_action_dates=None,
    )
    assert len(active_u) == 1
    assert active_u[0]["entry_price"] == 20.0
    assert active_u[0]["target_1"] == 20.9
    assert active_u[0]["stop_loss"] == 19.4
    assert active_u[0]["sessions_count"] == 2
    assert closed_u == [] and hits_u == [] and stops_u == []

    # Frozen signal still expires cleanly once max_sessions is reached
    active_exp, closed_exp, hits_exp, stops_exp = step_scanner_lifecycle(
        [{**active_u[0], "sessions_count": 3}],
        [],
        {"INEG": {"open": 12.5, "high": 12.7, "low": 12.45, "close": 12.6}},
        final_vol=[],
        final_bo=[],
        final_os=[],
        as_of_date="2026-11-23",
        action_date="2026-11-23",
        action_time="14:30",
        now_iso="2026-11-23T12:30:00Z",
        causal_be_prev_only=True,
        intraday_live=False,
        confirmed_action_dates=None,
    )
    assert active_exp == [] and hits_exp == [] and stops_exp == []
    assert len(closed_exp) == 1
    assert closed_exp[0]["status"] == "expired"
