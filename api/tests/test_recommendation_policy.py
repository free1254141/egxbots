import pytest
import pandas as pd
from types import SimpleNamespace
from api.recommendation_policy import evaluate_bars, valid_candidate


def bar(day, opening=100, high=104, low=96, close=101):
    return dict(date=f"2026-09-{day:02}", open=opening, high=high, low=low, close=close)


def evaluate(bars, **kwargs):
    return evaluate_bars(entry=100, target=120, stop=90, bars=bars,
                         entry_date="2026-09-01", cursor="2026-09-01", **kwargs)


def test_exit_before_time_limit_and_gap_fill():
    result = evaluate([bar(2, 85, 89, 80, 86)], max_sessions=1)
    assert result["exit_price"] == 85
    assert result["profit_loss_pct"] == pytest.approx(-15)
    assert result["exit_reason"] == "stop_hit"


def test_first_timeout_bar_wins_even_when_job_missed_later_sessions():
    result = evaluate([bar(2), bar(5), bar(6, 110, 115, 108, 112)], max_sessions=2)
    assert result["closed_on"] == "2026-09-05"
    assert result["exit_price"] == 101
    assert result["exit_reason"] == "time_exit"


def test_entry_bar_excluded_and_both_barriers_conservative():
    result = evaluate([bar(1, 100, 130, 80, 100), bar(2, 100, 130, 80, 100)])
    assert result["closed_on"] == "2026-09-02"
    assert result["exit_price"] == 90


def test_trailing_applies_next_bar_and_never_decreases():
    result = evaluate([bar(2, 100, 112, 98, 110), bar(3, 110, 112, 108, 109),
                       bar(4, 107, 109, 105, 106)], trail_pct=.03)
    assert result["closed_on"] == "2026-09-04"
    assert result["exit_price"] == pytest.approx(106.7)
    assert len(result["adjustments"]) == 1


def test_repeated_run_does_not_process_same_bar_again():
    result = evaluate_bars(entry=100, target=120, stop=102, bars=[bar(2)],
                           entry_date="2026-09-01", cursor="2026-09-02")
    assert result["last_close"] is None


@pytest.mark.parametrize("value", [None, 0, -1, float("nan"), float("inf")])
def test_bad_entry_is_rejected(value):
    assert not valid_candidate(dict(last_close=value, target_price=120, stop_loss=90))


def test_new_candidate_geometry_does_not_restrict_legacy_profit_stop():
    assert not valid_candidate(dict(last_close=100, target_price=120, stop_loss=105))
    result = evaluate_bars(entry=100, target=120, stop=105, bars=[bar(2, 104, 106, 103, 104)],
                           entry_date="2026-09-01", cursor="2026-09-01")
    assert result["status"] == "win"


def test_invalid_data_is_not_silently_marked_reviewed():
    with pytest.raises(ValueError):
        evaluate([bar(2, high=90, low=110)])


def test_sector_distribution_exit_records_outcome_for_a_winning_or_losing_trade():
    risk = {"2026-09-02": {"Real Estate": {"sector_change_pct": -1.4}}}
    result = evaluate([bar(2, opening=100, high=106, low=96, close=105)],
        sector_risk_by_date=risk, recommendation_sector="Real Estate",
        recommendation_symbol="TEST", weak_symbols_by_date={"2026-09-02": {"TEST"}})
    assert result["exit_reason"] == "sector_distribution_exit"
    assert result["exit_price"] == 105
    assert result["status"] == "win"
    assert result["sector_risk"]["sector_change_pct"] == -1.4


def test_intraday_stop_keeps_precedence_over_sector_distribution_exit():
    risk = {"2026-09-02": {"Real Estate": {"sector_change_pct": -1.4}}}
    result = evaluate([bar(2, opening=89, high=95, low=88, close=90)],
        sector_risk_by_date=risk, recommendation_sector="Real Estate",
        recommendation_symbol="TEST", weak_symbols_by_date={"2026-09-02": {"TEST"}})
    assert result["exit_reason"] == "stop_hit"


def test_strong_stock_is_not_closed_only_because_its_sector_is_weak():
    risk = {"2026-09-02": {"Real Estate": {"sector_change_pct": -1.4}}}
    result = evaluate([bar(2, opening=100, high=106, low=96, close=105)],
        sector_risk_by_date=risk, recommendation_sector="Real Estate",
        recommendation_symbol="STRONG", weak_symbols_by_date={"2026-09-02": {"WEAK"}})
    assert result["status"] == "open"


@pytest.mark.parametrize("signal_close, expected_updates", [(100, 1), (50, 0)])
def test_daily_evaluator_closes_using_hf_archive_when_supabase_has_no_prices(
    monkeypatch, signal_close, expected_updates
):
    from api import daily_bot_run
    import api.hf_history_cache as history
    import api.recommendation_events as events
    import api.recommendation_data as data
    monkeypatch.setattr(data, "repair_history", lambda client, rec, current, today: (current, {"status": "failed"}))

    recommendation = dict(id="rec-1", symbol="TEST", exchange="EGX", status="open",
        entry_price=100, target_price=110, stop_loss=95, last_close=100,
        created_at="2026-09-01T14:00:00+00:00", updated_at="2026-09-01T14:00:00+00:00",
        adjustments=[], rich_details={"evaluation": {"last_evaluated_date": "2026-09-01"},
            "recommendation_policy": {"max_sessions": 20}})
    archive = pd.DataFrame([
        dict(symbol="TEST", exchange="EGX", date=pd.Timestamp("2026-09-01"),
             open=signal_close, high=signal_close + 1, low=signal_close - 1,
             close=signal_close, volume=1000),
        dict(symbol="TEST", exchange="EGX", date=pd.Timestamp("2026-09-02"),
             open=100, high=112, low=99, close=111, volume=1000),
    ])

    class Query:
        def __init__(self, table):
            self.table = table
            self.fields = ""
            self.patch = None

        def select(self, fields):
            self.fields = fields
            return self

        def update(self, patch):
            self.patch = patch
            return self

        def eq(self, *_args):
            return self

        def gte(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.table == "stock_prices":
                return SimpleNamespace(data=[])
            if self.patch is not None:
                recommendation.update(self.patch)
                return SimpleNamespace(data=[recommendation.copy()])
            if self.fields == "id":
                return SimpleNamespace(data=[{"id": recommendation["id"]}])
            return SimpleNamespace(data=[recommendation.copy()])

    class Client:
        def table(self, table):
            return Query(table)

    monkeypatch.setattr(daily_bot_run, "supabase", Client())
    monkeypatch.setattr(history, "load_history_snapshot", lambda _exchange: archive)
    monkeypatch.setattr(events, "record_event", lambda *_args, **_kwargs: {"id": "event-1"})
    monkeypatch.setattr(daily_bot_run, "_telegram_recommendation_writes_enabled", lambda: False)

    assert daily_bot_run.evaluate_old_recommendations() == expected_updates
    if expected_updates:
        assert recommendation["status"] == "win"
        assert recommendation["exit_price"] == 110
        assert recommendation["rich_details"]["evaluation"]["closed_on"] == "2026-09-02"
    else:
        assert recommendation["status"] == "open"
        assert "exit_price" not in recommendation


def test_unadjusted_corporate_action_drop_is_blocked_instead_of_false_stop_hit():
    from api.recommendation_policy import CorporateActionDiscontinuity

    bars = [
        dict(date="2026-11-18", open=0.553, high=0.608, low=0.553, close=0.608, volume=87617719),
        dict(date="2026-11-19", open=0.382596, high=0.392035, low=0.361201, close=0.388889, volume=208352862),
        dict(date="2026-11-22", open=0.389, high=0.426, low=0.365, close=0.401, volume=133705269),
    ]
    # Unconfirmed discontinuity never rebases blindly — raises CorporateActionDiscontinuity(confirmed=False)
    with pytest.raises(CorporateActionDiscontinuity) as exc_info:
        evaluate_bars(
            entry=0.608,
            target=0.790,
            stop=0.517,
            bars=bars,
            entry_date="2026-11-18",
            cursor="2026-11-18",
        )
    assert exc_info.value.confirmed is False

    # Verified corporate action triggers Auto-Rebase and keeps trade open (+3.08%)
    res = evaluate_bars(
        entry=0.608,
        target=0.790,
        stop=0.517,
        bars=bars,
        entry_date="2026-11-18",
        cursor="2026-11-18",
        corporate_action_dates=["2026-11-19"],
    )
    assert res["status"] == "open"
    assert res["rebased"] is True
    assert res["entry_price"] == pytest.approx(0.389, abs=0.002)
    assert res["target_price"] == pytest.approx(0.505, abs=0.002)
    assert res["stop_loss"] == pytest.approx(0.331, abs=0.002)
    assert res["last_close"] == 0.401
    assert res["profit_loss_pct"] == pytest.approx(3.08, abs=0.2)
    assert res["adjustments"][-1]["type"] == "corporate_action_rebase"


def test_wide_stop_loss_above_10_pct_is_rejected():
    from api.recommendation_policy import candidate_assessment

    wide = candidate_assessment(dict(symbol="INEG", last_close=100, target_price=135, stop_loss=85))
    assert not wide["accepted"]
    assert wide["reason"] == "stop_loss_too_wide"
    assert wide["stop_distance_pct"] == 15.0

    within_limit = candidate_assessment(dict(symbol="COMI", last_close=100, target_price=120, stop_loss=90))
    assert within_limit["accepted"]
    assert within_limit["reason"] == "accepted"


def test_corporate_action_discontinuity_ineg_like_drop_and_valueerror_subclass():
    from api.recommendation_policy import CorporateActionDiscontinuity

    bars = [
        dict(date="2026-11-18", open=0.553, high=0.608, low=0.553, close=0.608, volume=100000),
        dict(date="2026-11-19", open=0.389, high=0.410, low=0.385, close=0.401, volume=200000),
    ]
    # Unconfirmed raise is still a ValueError subclass
    with pytest.raises(CorporateActionDiscontinuity) as exc_info:
        evaluate_bars(
            entry=0.608,
            target=0.790,
            stop=0.517,
            bars=bars,
            entry_date="2026-11-18",
            cursor="2026-11-18",
        )
    err = exc_info.value
    assert isinstance(err, ValueError)
    assert err.confirmed is False
    assert err.change_pct == pytest.approx(-34.05, abs=0.2)

    # With rebase_corporate_actions=False, even confirmed actions raise
    with pytest.raises(CorporateActionDiscontinuity) as exc_conf:
        evaluate_bars(
            entry=0.608,
            target=0.790,
            stop=0.517,
            bars=bars,
            entry_date="2026-11-18",
            cursor="2026-11-18",
            corporate_action_dates=["2026-11-19"],
            rebase_corporate_actions=False,
        )
    assert exc_conf.value.confirmed is True

    # Next-run replay after DB was already rebased must NOT double-rebase
    replay = evaluate_bars(
        entry=0.389,
        target=0.505,
        stop=0.331,
        bars=bars + [dict(date="2026-11-22", open=0.401, high=0.415, low=0.395, close=0.410, volume=150000)],
        entry_date="2026-11-18",
        cursor="2026-11-19",
        corporate_action_dates=["2026-11-19"],
    )
    assert replay["rebased"] is False
    assert replay["entry_price"] == 0.389
    assert replay["target_price"] == 0.505
    assert replay["stop_loss"] == 0.331


def test_confirmed_12pct_gap_down_rebases_when_confirmed_and_stops_when_unconfirmed():
    # Entry at 100 on 2026-09-01, stop at 92; next bar opens at 88 (-12% gap)
    bars = [bar(2, opening=88, high=90, low=87, close=89)]

    rebased = evaluate(bars, corporate_action_dates=["2026-08-03"])
    assert rebased["rebased"] is True
    assert rebased["status"] == "open"
    assert rebased["entry_price"] == pytest.approx(89.0, abs=0.2)
    assert rebased["target_price"] == pytest.approx(106.8, abs=0.2)
    assert rebased["stop_loss"] == pytest.approx(80.1, abs=0.2)

    result = evaluate(bars)
    assert result["exit_reason"] == "stop_hit"
    assert result["exit_price"] == 88


def test_reverse_split_40pct_jump_raises_discontinuity():
    from api.recommendation_policy import CorporateActionDiscontinuity

    with pytest.raises(CorporateActionDiscontinuity):
        evaluate([bar(2, opening=140, high=145, low=138, close=142)])


def test_normal_minus_9pct_bar_without_action_is_still_stop_hit():
    result = evaluate([bar(2, opening=91, high=93, low=89, close=91)])
    assert result["exit_reason"] == "stop_hit"
    assert result["exit_price"] == 90


def test_corporate_action_confirmed_window_edges():
    from api.recommendation_policy import corporate_action_confirmed

    # 2026-09-01 minus 120 days is 2026-05-04; minus 121 days is 2026-05-03
    assert corporate_action_confirmed("2026-09-01", ["2026-05-03"]) is False
    assert corporate_action_confirmed("2026-09-01", ["2026-05-04"]) is True
    assert corporate_action_confirmed("2026-09-01", ["2026-09-02"]) is True
    assert corporate_action_confirmed("2026-09-01", ["2026-09-03"]) is False
    assert corporate_action_confirmed("2026-09-01", ["not-a-date", None]) is False


def test_multiday_drift_before_confirmed_minus_15pct_action_rebases_and_same_day_cursor():
    from api.recommendation_policy import evaluate_bars, resolve_signal_reference

    # Entry at 100 on 2026-09-01, drifts +15% to 115 on 2026-09-02, then confirmed -15% action on 2026-09-03
    bars = [
        dict(date="2026-09-01", open=99, high=101, low=98, close=100, volume=10000),
        dict(date="2026-09-02", open=101, high=116, low=100, close=115, volume=10000),
        dict(date="2026-09-03", open=97.75, high=99.0, low=96.5, close=97.75, volume=12000),
    ]
    res = evaluate_bars(
        entry=100,
        target=120,
        stop=92,
        bars=bars,
        entry_date="2026-09-01",
        cursor="2026-09-03",
        corporate_action_dates=["2026-09-03"],
    )
    assert res["rebased"] is True
    assert res["entry_price"] == pytest.approx(85.0, abs=0.05)
    assert res["target_price"] == pytest.approx(102.0, abs=0.05)
    assert res["stop_loss"] == pytest.approx(78.2, abs=0.05)
    assert res["last_close"] == pytest.approx(97.75, abs=0.01)
    assert res["sessions_held"] == 2
    assert len(res["adjustments"]) == 1
    assert res["adjustments"][0]["type"] == "corporate_action_rebase"

    ref = resolve_signal_reference(
        85.0,
        bars,
        "2026-09-01",
        "2026-09-01",
        rebased=True,
        corporate_action_dates=["2026-09-03"],
    )
    assert ref["ok"] is True
    assert ref["reason"] == "verified_rebased_signal_reference"
