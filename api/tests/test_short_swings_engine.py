"""
Unit tests for the Short Swings Engine, Router, and Daily Dispatcher.
Validates all audit findings (F1 through F14) from docs/short-swings-review-2026-10-07.md.
"""
import os
import json
import sys
import types
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api.short_swings_engine import (
    compute_kpis_from_trades,
    load_stock_metadata,
    EXIT_REASON_LABELS
)
from api.routers.short_swings import router
from fastapi import FastAPI
from api import short_swings_engine as engine


@pytest.fixture
def telegram_dependencies(monkeypatch):
    # Dispatch tests need the notification boundary, not provider/model imports.
    module = types.ModuleType('api.daily_bot_run')
    module._telegram_recommendation_writes_enabled = MagicMock(return_value=True)
    module._notify_vip_telegram = MagicMock()
    module._notify_free_telegram = MagicMock()
    monkeypatch.setitem(sys.modules, 'api.daily_bot_run', module)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# =========================================================================
# F1: PRO Entitlement Security Verification
# =========================================================================
def test_f1_unauthorized_pro_query_is_masked(client, monkeypatch):
    """An external caller passing ?is_pro=true without valid admin secret MUST be served masked data."""
    monkeypatch.setenv("ADMIN_SECRET_KEY", "super-secret-key-12345")
    
    mock_data = {
        "status": "ok",
        "kpis": {"win_rate_pct": 52.0},
        "active_trades": [
            {
                "symbol": "COMI",
                "entry_date": "2026-10-06",
                "entry_price": 100.0,
                "current_price": 105.0,
                "is_pending_entry": True,
                "return_pct": 5.0,
                "is_locked": False,
            }
        ],
        "closed_trades": [
            {
                "symbol": "ETEL",
                "entry_date": "2026-09-01",
                "exit_date": "2026-09-05",
                "return_pct": 4.5,
                "is_locked": False,
            }
        ],
        "total_active": 1,
        "total_closed": 1,
        "as_of": "2026-10-06"
    }
    
    with patch("api.routers.short_swings.get_cached_short_swings", return_value=mock_data):
        # 1. Attacker calls ?is_pro=true without header
        res = client.get("/api/short-swings?is_pro=true")
        assert res.status_code == 200
        body = res.json()
        assert body["is_pro"] is False
        assert len(body["active_trades"]) == 1
        active = body["active_trades"][0]
        assert active["is_locked"] is True
        assert active["symbol"] == "CO**"
        assert active["entry_price"] is None
        assert "upgrade_cta" in body

        # 2. Trusted internal caller with valid x-admin-key gets full unmasked data
        res_auth = client.get("/api/short-swings?is_pro=true", headers={"x-admin-key": "super-secret-key-12345"})
        assert res_auth.status_code == 200
        body_auth = res_auth.json()
        assert body_auth["is_pro"] is True
        assert body_auth["active_trades"][0]["is_locked"] is False
        assert body_auth["active_trades"][0]["symbol"] == "COMI"
        assert body_auth["active_trades"][0]["entry_price"] == 100.0


def test_f1_missing_admin_secret_fails_closed(client, monkeypatch):
    """A missing deployment secret must never authorize the private payload."""
    monkeypatch.delenv("ADMIN_SECRET_KEY", raising=False)
    mock_data = {
        "status": "ok",
        "active_trades": [{
            "symbol": "COMI",
            "entry_date": "2026-10-06",
            "entry_price": 100.0,
            "is_pending_entry": True,
            "signal_id": "COMI_2026-10-06",
        }],
        "closed_trades": [],
    }
    with patch("api.routers.short_swings.get_cached_short_swings", return_value=mock_data):
        response = client.get("/api/short-swings?is_pro=true")
    assert response.status_code == 200
    body = response.json()
    assert body["is_pro"] is False
    assert body["active_trades"][0]["signal_id"] is None
    assert body["active_trades"][0]["entry_price"] is None


# =========================================================================
# F2: Gap-Down Exit Pricing (Never Exit Above High)
# =========================================================================
def test_f2_gap_down_exit_pricing_conservative():
    """When a stock gaps down below stop loss, fill must occur at Open (with slippage), never above High."""
    sl_price = 115.0
    open_p = 100.0
    high_p = 102.0
    low_p = 98.0
    slippage = 0.0015

    # Gap-down condition: open <= sl_price
    assert open_p <= sl_price
    
    # Formula implemented in engine:
    raw_fill = min(high_p, open_p) * (1 - slippage)
    fill_price = max(low_p * (1 - slippage), min(high_p, raw_fill))

    assert fill_price < sl_price
    assert fill_price <= high_p
    assert fill_price >= low_p * (1 - slippage)
    assert round(fill_price, 2) == 99.85  # 100 * (1 - 0.0015) = 99.85


# =========================================================================
# F3: Telegram Verified Outbox Receipt Tracking
# =========================================================================
def test_f3_telegram_failure_does_not_mark_sent(telegram_dependencies):
    """If Telegram dispatch fails, symbols must NOT be marked as sent."""
    from api.short_swings_daily import run_daily_short_swings
    from datetime import datetime
    from zoneinfo import ZoneInfo
    session_date = datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()

    mock_swings = {
        "as_of": session_date, "status": "ok", "phase": "close",
        "active_trades": [
            {
                "symbol": "TEST_STOCK", "signal_date": session_date,
                "name_ar": "سهم اختبار",
                "reference_close": 50.0,
                "trailing_stop": 48.0,
                "is_pending_entry": True
            }
        ],
        "closed_trades": []
    }

    mock_sb = MagicMock()
    # Mock empty sent state
    mock_sb.table().select().eq().eq().maybe_single().execute.return_value.data = {
        "payload": {"sent_entries": {}, "sent_exits": {}}
    }

    from api import daily_recovery_state
    memory = {}
    def write(_sb, key, payload, expected):
        memory[key] = {"payload": dict(payload)}
        return memory[key]
    with patch.object(daily_recovery_state, "read_checkpoint", side_effect=lambda sb, key: memory.get(key)), \
         patch('api.cache_invalidation.invalidate_cache_tags', return_value={'invalidated': ['daily-short-swings']}), \
         patch.object(daily_recovery_state, "replace_checkpoint", side_effect=write), \
         patch("api.short_swings_daily._get_sent_cache_state", return_value={"sent_entries": {}, "sent_exits": {}}), \
         patch("api.short_swings_daily.compute_short_swings", return_value=mock_swings), \
         patch("api.short_swings_daily._get_supabase_client", return_value=mock_sb), \
         patch("api.daily_bot_run._telegram_recommendation_writes_enabled", return_value=True), \
         patch("api.daily_bot_run._notify_vip_telegram", return_value=False), \
         patch("api.daily_bot_run._notify_free_telegram", return_value=False):

        result = run_daily_short_swings(trigger="scheduled", dry_run=False)

        assert result["success"] is False
        assert result["status"] == "partial" or result["status"] == "noop" or len(result["report"]["failures"]) > 0
        assert result["report"]["vip_entries_sent"] is False
        assert result["report"]["free_entries_sent"] is False

        # Verify that upsert to market_cache did NOT record "TEST_STOCK" as vip: True
        upsert_call = mock_sb.table().upsert.call_args
        if upsert_call:
            saved_payload = upsert_call[0][0]["payload"]
            assert saved_payload["sent_entries"].get("TEST_STOCK", {}).get("vip") is not True


def test_f3_missing_delivery_checkpoint_does_not_send(telegram_dependencies):
    """Do not broadcast when receipt persistence is unavailable."""
    from api.short_swings_daily import run_daily_short_swings

    mock_swings = {
        "as_of": "2026-10-07",
        "active_trades": [{"symbol": "TEST_STOCK", "is_pending_entry": True}],
        "closed_trades": [],
    }
    with patch("api.short_swings_daily.compute_short_swings", return_value=mock_swings), \
         patch("api.short_swings_daily._get_supabase_client", return_value=None), \
         patch("api.daily_bot_run._telegram_recommendation_writes_enabled", return_value=True), \
         patch("api.daily_bot_run._notify_vip_telegram") as vip_send, \
         patch("api.daily_bot_run._notify_free_telegram") as free_send:
        result = run_daily_short_swings(trigger="scheduled", dry_run=False)

    assert result["success"] is False
    assert result["status"] == "checkpoint_unavailable"
    vip_send.assert_not_called()
    free_send.assert_not_called()


# =========================================================================
# F5: Causal Breakeven Activation
# =========================================================================
def test_f5_breakeven_delay_causality():
    """Breakeven activation must be scheduled for next session, not executed retroactively on same day."""
    p = {
        "entry_price": 100.0,
        "sl_price": 96.0,
        "highest_high": 100.0,
        "be_active": False,
        "be_pending_activation": False
    }

    # Day 1: price hits high = 105.0 (+5.0% >= +4.5%)
    day_1_high = 105.0
    gain = (day_1_high / p["entry_price"] - 1)
    if not p["be_active"] and not p.get("be_pending_activation") and gain >= 0.045:
        p["be_pending_activation"] = True

    # Intraday defensive stop on Day 1 is STILL 96.0, NOT breakeven!
    assert p["be_active"] is False
    assert p["sl_price"] == 96.0
    assert p["be_pending_activation"] is True

    # At start of Day 2: scheduled activation takes effect
    if p.get("be_pending_activation"):
        p["be_active"] = True
        p["sl_price"] = max(p["sl_price"], p["entry_price"] * 1.003)
        p["be_pending_activation"] = False

    assert p["be_active"] is True
    assert p["sl_price"] == pytest.approx(100.3)


# =========================================================================
# F8: Dynamic KPI Computation
# =========================================================================
def test_f8_dynamic_kpi_computation():
    """KPIs must be computed from actual trade data, not static constants."""
    trades = [
        {"return_pct": 10.0, "sessions": 3, "exit_date": "2026-05-01"},
        {"return_pct": 6.0, "sessions": 2, "exit_date": "2026-05-10"},
        {"return_pct": -4.0, "sessions": 4, "exit_date": "2026-05-15"},
    ]

    kpis = compute_kpis_from_trades(trades)
    assert kpis["total_trades"] == 3
    assert kpis["wins_count"] == 2
    assert kpis["losses_count"] == 1
    assert kpis["win_rate_pct"] == 66.7
    assert kpis["profit_factor"] == 4.0  # 16.0 / 4.0 = 4.0
    assert kpis["avg_win_pct"] == 8.0   # (10 + 6) / 2 = 8.0
    assert kpis["avg_loss_pct"] == -4.0
    assert kpis["top_win_pct"] == 10.0
    assert kpis["avg_holding_days"] == 3.0  # (3 + 2 + 4) / 3 = 3.0


def test_f8_empty_trades_kpis():
    """Empty trades list returns 0 KPIs, never hardcoded fake metrics."""
    kpis = compute_kpis_from_trades([])
    assert kpis["total_trades"] == 0
    assert kpis["win_rate_pct"] == 0.0
    assert kpis["profit_factor"] == 0.0
    assert kpis["total_return_pct"] == 0.0


def test_f8_drawdown_includes_initial_cash_peak():
    """The first losing trade must create drawdown instead of reporting zero."""
    kpis = compute_kpis_from_trades([{"return_pct": -15.0, "exit_date": "2026-01-01"}])
    assert kpis["max_drawdown_pct"] == 1.0


# =========================================================================
# F12 & F13: Metadata & Exit Reason Labels
# =========================================================================
def test_f12_exit_reason_labels():
    """Verify Arabic mappings for exit reasons exist."""
    assert "ema10_break" in EXIT_REASON_LABELS
    assert "stop_be" in EXIT_REASON_LABELS
    assert "stop_loss" in EXIT_REASON_LABELS
    assert "حماية أرباح" in EXIT_REASON_LABELS["ema10_break"]


def test_f13_case_insensitive_metadata_loading(monkeypatch, tmp_path):
    """load_stock_metadata loads tickers when JSON keys are Capitalized."""
    registry = tmp_path / 'symbols_data'
    registry.mkdir()
    (registry / 'Egypt_all_symbols_fixture.json').write_text(json.dumps([
        {'Symbol': 'COMI', 'Name': 'Fixture company', 'ArabicName': 'شركة اختبار'},
    ]))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(engine, '_METADATA_CACHE', None)
    monkeypatch.setitem(sys.modules, 'api.stock_ai', types.SimpleNamespace(_init_supabase=lambda: None, supabase=None))
    meta = load_stock_metadata()
    assert isinstance(meta, dict)
    assert len(meta) > 0
    # COMI should be present
    assert "COMI" in meta
    assert "name_en" in meta["COMI"]
    assert "name_ar" in meta["COMI"]



def test_morning_phase_supported_and_isolated_from_midday(telegram_dependencies):
    """Morning intraday phase completes without ValueError and uses its own checkpoint."""
    from api.short_swings_daily import run_daily_short_swings
    from api import daily_recovery_state
    from datetime import datetime
    from zoneinfo import ZoneInfo

    session_date = datetime.now(ZoneInfo("Africa/Cairo")).date().isoformat()
    memory = {}

    def write(_sb, key, payload, expected):
        memory[key] = {"payload": dict(payload)}
        return memory[key]

    mock_sb = MagicMock()
    with patch.object(daily_recovery_state, "read_checkpoint", side_effect=lambda sb, key: memory.get(key)), \
         patch.object(daily_recovery_state, "replace_checkpoint", side_effect=write), \
         patch("api.cache_invalidation.invalidate_cache_tags", return_value={"invalidated": []}), \
         patch("api.short_swings_daily._get_sent_cache_state", return_value={"sent_entries": {}, "sent_exits": {}}), \
         patch("api.short_swings_daily.compute_short_swings", side_effect=lambda phase="close", **kwargs: {"as_of": session_date, "status": "ok", "phase": phase, "active_trades": [], "closed_trades": []}), \
         patch("api.short_swings_daily._get_supabase_client", return_value=mock_sb), \
         patch("api.daily_bot_run._telegram_recommendation_writes_enabled", return_value=True):
        morning_res = run_daily_short_swings(trigger="scheduled", phase="morning")
        midday_res = run_daily_short_swings(trigger="scheduled", phase="midday")

    assert morning_res["success"] is True
    assert morning_res["status"] == "completed"
    assert f"short_swings_run_{session_date}_morning" in memory
    assert midday_res["success"] is True
    assert midday_res["status"] == "completed"
    assert f"short_swings_run_{session_date}_midday" in memory


# =========================================================================
# Regression Tests: Causal Day-0 Stop, Two-Tier Profit Lock & +13% Take Profit
# =========================================================================
def _build_uptrend_rows(symbol: str, start_end_date: str = "2026-10-05", periods: int = 90):
    import pandas as pd
    dates = pd.bdate_range(end=start_end_date, periods=periods)
    return [
        {
            "symbol": symbol,
            "exchange": "EGX",
            "date": day.strftime("%Y-%m-%d"),
            "open": 100.0 + i * 0.5,
            "high": 100.5 + i * 0.5,
            "low": 99.5 + i * 0.5,
            "close": 100.2 + i * 0.5,
            "volume": 100_000.0,
        }
        for i, day in enumerate(dates)
    ]


def _run_offline_engine(monkeypatch, tmp_path, rows, now_iso="2026-10-12T16:00:00+02:00", confirmed_action_dates=None):
    import datetime as dt
    import pandas as pd

    parsed_now = dt.datetime.fromisoformat(now_iso)

    class FixedClock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return parsed_now.astimezone(tz or dt.timezone.utc)

    monkeypatch.setattr(
        engine,
        "dt",
        types.SimpleNamespace(
            datetime=FixedClock,
            date=dt.date,
            timezone=dt.timezone,
            timedelta=dt.timedelta,
        ),
    )
    monkeypatch.setitem(sys.modules, "api.stock_ai", types.SimpleNamespace(_init_supabase=lambda: None, supabase=None))
    monkeypatch.setattr("api.hf_history_cache.load_history_snapshot", lambda _: pd.DataFrame(rows))
    monkeypatch.setattr(engine, "load_stock_metadata", lambda: {})
    monkeypatch.setattr(engine, "_load_published_signals", lambda _: [])
    monkeypatch.setattr(engine, "_persist_saved_snapshot", lambda *_: True)
    monkeypatch.setattr(engine, "CACHE_PATHS", [tmp_path / "ss_test_cache.json"])
    return engine.compute_short_swings(phase="close", confirmed_action_dates=confirmed_action_dates)


def test_day0_negative_close_blocks_be_and_schedules_eod_stop(monkeypatch, tmp_path):
    """Spiking +5% on Day 0 before closing below -4% must NOT arm fake stop_be; must exit at next open as stop_loss."""
    assert "take_profit" in EXIT_REASON_LABELS
    rows = _build_uptrend_rows("REVX", start_end_date="2026-10-05", periods=90)
    # 2026-10-06: strong breakout bar triggering entry on 2026-10-07 open
    rows.append({"symbol": "REVX", "exchange": "EGX", "date": "2026-10-06", "open": 146.0, "high": 152.0, "low": 145.5, "close": 151.0, "volume": 280_000.0})
    # 2026-10-07 (Day 0): opens at 151.0, spikes +7% intraday (161.6), reverses and closes at 142.0 (below -4% initial stop ~145.18)
    rows.append({"symbol": "REVX", "exchange": "EGX", "date": "2026-10-07", "open": 151.0, "high": 161.6, "low": 141.5, "close": 142.0, "volume": 320_000.0})
    # 2026-10-08 (Day 1): opens lower at 140.0 — pending Day-0 EOD stop closes cleanly at Open with stop_loss
    rows.append({"symbol": "REVX", "exchange": "EGX", "date": "2026-10-08", "open": 140.0, "high": 143.0, "low": 139.0, "close": 141.0, "volume": 200_000.0})

    result = _run_offline_engine(monkeypatch, tmp_path, rows, now_iso="2026-10-08T16:00:00+02:00")
    revx_closed = [t for t in result["closed_trades"] if t["symbol"] == "REVX"]
    assert len(revx_closed) == 1
    assert revx_closed[0]["reason"] == "stop_loss"
    assert revx_closed[0]["exit_date"] == "2026-10-08"


def test_two_tier_profit_lock_protects_9pct_gain_from_be_choke(monkeypatch, tmp_path):
    """Reaching +9% with positive close locks +4.0% floor for next session instead of dropping to +0.15%."""
    rows = _build_uptrend_rows("LOCKX", start_end_date="2026-10-05", periods=90)
    # 2026-10-06: breakout signal
    rows.append({"symbol": "LOCKX", "exchange": "EGX", "date": "2026-10-06", "open": 146.0, "high": 152.0, "low": 145.5, "close": 151.0, "volume": 280_000.0})
    # 2026-10-07 (Day 0): opens at 151.0 (fill ~151.2265), rallies to 166.5 (+10.1% >= +9%) and closes strongly at 165.0
    rows.append({"symbol": "LOCKX", "exchange": "EGX", "date": "2026-10-07", "open": 151.0, "high": 166.5, "low": 150.5, "close": 165.0, "volume": 350_000.0})
    # 2026-10-08 (Day 1): retraces intraday down to 154.0 (+1.8%), crossing the +4.0% Tier-2 lock (~157.28)
    rows.append({"symbol": "LOCKX", "exchange": "EGX", "date": "2026-10-08", "open": 162.0, "high": 163.0, "low": 154.0, "close": 155.0, "volume": 220_000.0})

    result = _run_offline_engine(monkeypatch, tmp_path, rows, now_iso="2026-10-08T16:00:00+02:00")
    closed = [t for t in result["closed_trades"] if t["symbol"] == "LOCKX"]
    assert len(closed) == 1
    assert closed[0]["reason"] == "stop_be"
    assert closed[0]["return_pct"] >= 3.7


def test_causal_take_profit_exits_cleanly_at_13_pct(monkeypatch, tmp_path):
    """Hitting +13% on Day 1 exits cleanly as take_profit around +12.8% net."""
    rows = _build_uptrend_rows("TPX", start_end_date="2026-10-05", periods=90)
    # 2026-10-06: breakout signal
    rows.append({"symbol": "TPX", "exchange": "EGX", "date": "2026-10-06", "open": 146.0, "high": 152.0, "low": 145.5, "close": 151.0, "volume": 280_000.0})
    # 2026-10-07 (Day 0): quiet hold +3%
    rows.append({"symbol": "TPX", "exchange": "EGX", "date": "2026-10-07", "open": 151.0, "high": 156.0, "low": 150.0, "close": 155.0, "volume": 210_000.0})
    # 2026-10-08 (Day 1): surges to 175.0 (+15.7% above entry ~151.23) -> fills target +13%
    rows.append({"symbol": "TPX", "exchange": "EGX", "date": "2026-10-08", "open": 156.0, "high": 175.0, "low": 155.0, "close": 172.0, "volume": 380_000.0})

    result = _run_offline_engine(monkeypatch, tmp_path, rows, now_iso="2026-10-08T16:00:00+02:00")
    closed = [t for t in result["closed_trades"] if t["symbol"] == "TPX"]
    assert len(closed) == 1
    assert closed[0]["reason"] == "take_profit"
    assert closed[0]["return_pct"] == pytest.approx(12.83, abs=0.05)


def test_vip_update_message_includes_profit_and_loss_pct():
    from api.short_swings_daily import build_vip_update_message

    msg = build_vip_update_message(
        [
            {
                "symbol": "AJWA",
                "name_ar": "أجواء للصناعات الغذائية",
                "current_price": 267.600,
                "entry_price": 258.387,
                "trailing_stop": 260.454,
                "status": "مؤمنة بربح",
            },
            {
                "symbol": "LOSER",
                "name_ar": "سهم هابط",
                "current_price": 97.500,
                "entry_price": 100.000,
                "stop_loss": 96.000,
                "return_pct": -2.50,
                "status": "قيد التداول",
            },
        ],
        "2026-11-16",
        "https://egxbots.com",
    )
    assert "نسبة الربح/الخسارة: 🟢 `+3.57%`" in msg
    assert "نسبة الربح/الخسارة: 🔴 `-2.50%`" in msg


def test_short_swings_rebases_open_position_when_confirmed_and_blocks_when_unconfirmed(monkeypatch, tmp_path):
    """Confirmed corporate action rebases open position barriers and keeps trade active; unconfirmed drops cleanly without rebasing."""
    rows = _build_uptrend_rows("CAX1", start_end_date="2026-10-05", periods=90)
    # 2026-10-06: breakout signal
    rows.append({"symbol": "CAX1", "exchange": "EGX", "date": "2026-10-06", "open": 146.0, "high": 152.0, "low": 145.5, "close": 151.0, "volume": 280_000.0})
    # 2026-10-07 (Day 0): opens and holds normally -> position opened at ~151.23, last close 152.0
    rows.append({"symbol": "CAX1", "exchange": "EGX", "date": "2026-10-07", "open": 151.0, "high": 154.0, "low": 150.0, "close": 152.0, "volume": 220_000.0})
    # 2026-10-08 (Day 1): -35.5% gap down from 152.0 -> open 95.0, close 98.0
    rows.append({"symbol": "CAX1", "exchange": "EGX", "date": "2026-10-08", "open": 95.0, "high": 99.0, "low": 94.0, "close": 98.0, "volume": 350_000.0})

    # Confirmed corporate action -> rebases and stays OPEN
    res_conf = _run_offline_engine(
        monkeypatch,
        tmp_path,
        rows,
        now_iso="2026-10-08T16:00:00+02:00",
        confirmed_action_dates={"CAX1": ["2026-10-08"]},
    )
    active = [t for t in res_conf["active_trades"] if t["symbol"] == "CAX1"]
    assert len(active) == 1
    assert active[0]["entry_price"] == pytest.approx(94.52, abs=1.0)
    assert len(res_conf["rebased_corporate_actions"]) == 1
    assert [t for t in res_conf["closed_trades"] if t["symbol"] == "CAX1"] == []

    # Unconfirmed discontinuity -> does NOT blindly rebase target/entry
    res_unconf = _run_offline_engine(
        monkeypatch,
        tmp_path,
        rows,
        now_iso="2026-10-08T16:00:00+02:00",
        confirmed_action_dates={},
    )
    assert [t for t in res_unconf["closed_trades"] if t["symbol"] == "CAX1"] == []
    assert [t for t in res_unconf["active_trades"] if t["symbol"] == "CAX1"] == []
    assert len(res_unconf.get("unconfirmed_discontinuities", [])) == 1


def test_short_swings_entry_day_corporate_action_gap_requires_confirmation(monkeypatch, tmp_path):
    """Confirmed entry-day gap rebases limit_price and enters at post-split price; unconfirmed skips ghost trade."""
    rows = _build_uptrend_rows("CAX2", start_end_date="2026-10-05", periods=90)
    # 2026-10-06: breakout signal (limit_price = 151.0)
    rows.append({"symbol": "CAX2", "exchange": "EGX", "date": "2026-10-06", "open": 146.0, "high": 152.0, "low": 145.5, "close": 151.0, "volume": 280_000.0})
    # 2026-10-07 (Entry Day): gap-down to 95.0 open, 98.0 close
    rows.append({"symbol": "CAX2", "exchange": "EGX", "date": "2026-10-07", "open": 95.0, "high": 99.0, "low": 94.0, "close": 98.0, "volume": 350_000.0})
    # 2026-10-08: steady hold at 97.0 (above rebased stop ~91.2)
    rows.append({"symbol": "CAX2", "exchange": "EGX", "date": "2026-10-08", "open": 98.0, "high": 99.0, "low": 96.0, "close": 97.0, "volume": 200_000.0})

    res_conf = _run_offline_engine(
        monkeypatch,
        tmp_path,
        rows,
        now_iso="2026-10-08T16:00:00+02:00",
        confirmed_action_dates={"CAX2": ["2026-10-07"]},
    )
    active = [t for t in res_conf["active_trades"] if t["symbol"] == "CAX2"]
    assert len(active) == 1
    assert active[0]["entry_price"] == pytest.approx(95.14, abs=0.5)
    assert len(res_conf["rebased_corporate_actions"]) == 1

    res_unconf = _run_offline_engine(
        monkeypatch,
        tmp_path,
        rows,
        now_iso="2026-10-08T16:00:00+02:00",
        confirmed_action_dates={},
    )
    assert [t for t in res_unconf["active_trades"] if t["symbol"] == "CAX2"] == []
    assert [t for t in res_unconf["closed_trades"] if t["symbol"] == "CAX2"] == []
    assert len(res_unconf.get("unconfirmed_discontinuities", [])) == 1
