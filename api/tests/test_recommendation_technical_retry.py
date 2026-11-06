from api.daily_bot_run import is_technical_no_buy, TECHNICAL_NO_BUY_CODES
from api.daily_stage_recovery import plan_recovery


def test_technical_zero_is_retryable_but_a_real_decision_is_not():
    for code in TECHNICAL_NO_BUY_CODES:
        assert is_technical_no_buy(code) is True
    for code in (
        None,
        "",
        "no_ml_signals",
        "council_rejection",
        "trade_structure",
        "sector_filter",
        "capacity",
    ):
        assert is_technical_no_buy(code) is False


def test_failed_generation_stage_is_planned_for_recovery():
    steps = [
        {"step": "sync_prices", "status": "success"},
        {"step": "calculate_indicators", "status": "success"},
        {"step": "generate_recommendations", "status": "failed", "details": "Retryable block"},
    ]
    assert plan_recovery(steps, "close") == ["generate_recommendations"]


def test_successful_zero_generation_is_not_retried():
    steps = [
        {"step": "sync_prices", "status": "success"},
        {"step": "calculate_indicators", "status": "success"},
        {"step": "generate_recommendations", "status": "success", "count": 0},
    ]
    assert plan_recovery(steps, "close") == []


def _stub_generation(monkeypatch, reason_code, reason="reason", count=0):
    from api import daily_bot_run as bot
    from api import daily_job_scheduler

    monkeypatch.setattr(bot, "should_reject_new_buys", lambda: {"blocked": False})

    async def fake_generate(**kwargs):
        kwargs["run_context"]["no_buy_reason_code"] = reason_code
        kwargs["run_context"]["no_buy_reason"] = reason
        return count

    monkeypatch.setattr(bot, "generate_daily_recommendations", fake_generate)
    monkeypatch.setattr(daily_job_scheduler, "get_scheduler_state", lambda: {"model_filter": "adaptive"})


def test_recovery_marks_a_technical_zero_as_failed(monkeypatch):
    from api.daily_stage_recovery import execute_stage

    _stub_generation(monkeypatch, "sector_data_not_aligned", "بيانات القطاعات غير متطابقة")
    result = execute_stage("generate_recommendations", "close", "job-1", {})
    assert result["success"] is False
    assert result["count"] == 0
    assert "بيانات القطاعات غير متطابقة" in result["details"]


def test_recovery_marks_a_real_no_opportunity_zero_as_success(monkeypatch):
    from api.daily_stage_recovery import execute_stage

    _stub_generation(monkeypatch, "council_rejection", "كل المرشحين دون الحد")
    result = execute_stage("generate_recommendations", "close", "job-1", {})
    assert result["success"] is True
    assert result["count"] == 0


def test_dormant_council_voter_does_not_halve_the_consensus():
    from api.daily_bot_run import ignore_dormant_council_voters

    results = [
        {"symbol": "COMI", "council_score": 30.0,
         "detailed_votes": {"model_EGX.pkl": 0.60, "KING.bin": 0.0}},
        {"symbol": "ETEL", "council_score": 37.0,
         "detailed_votes": {"model_EGX.pkl": 0.74, "KING.bin": 0.0}},
    ]
    adjusted, dormant, unavailable = ignore_dormant_council_voters(results)
    assert dormant == ["KING.bin"]
    assert unavailable is False
    assert [row["council_score"] for row in adjusted] == [60.0, 74.0]
    assert all(row["council_recomputed"] is True for row in adjusted)


def test_a_genuine_negative_vote_is_preserved():
    from api.daily_bot_run import ignore_dormant_council_voters

    results = [
        {"symbol": "COMI", "council_score": 30.0,
         "detailed_votes": {"model_EGX.pkl": 0.60, "KING.bin": 0.0}},
        {"symbol": "ETEL", "council_score": 37.0,
         "detailed_votes": {"model_EGX.pkl": 0.74, "KING.bin": 0.20}},
    ]
    adjusted, dormant, unavailable = ignore_dormant_council_voters(results)
    assert dormant == []
    assert unavailable is False
    assert adjusted[0]["council_score"] == 30.0


def test_all_dormant_voters_become_a_technical_block():
    from api.daily_bot_run import ignore_dormant_council_voters

    results = [
        {"symbol": "COMI", "council_score": 0.0,
         "detailed_votes": {"model_EGX.pkl": 0.0, "KING.bin": 0.0}},
        {"symbol": "ETEL", "council_score": 0.0,
         "detailed_votes": {"model_EGX.pkl": 0.0, "KING.bin": 0.0}},
    ]
    adjusted, dormant, unavailable = ignore_dormant_council_voters(results)
    assert dormant == ["KING.bin", "model_EGX.pkl"]
    assert unavailable is True


def test_a_single_candidate_never_proves_dormancy():
    from api.daily_bot_run import ignore_dormant_council_voters

    results = [
        {"symbol": "COMI", "council_score": 30.0,
         "detailed_votes": {"model_EGX.pkl": 0.60, "KING.bin": 0.0}},
    ]
    adjusted, dormant, unavailable = ignore_dormant_council_voters(results)
    assert dormant == []
    assert unavailable is False
    assert adjusted[0]["council_score"] == 30.0



