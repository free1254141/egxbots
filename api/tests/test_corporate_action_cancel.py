from types import SimpleNamespace
import pandas as pd
import pytest

from api import daily_bot_run


def test_send_telegram_exit_corporate_action_message(monkeypatch):
    captured = []
    monkeypatch.setattr(daily_bot_run, "_telegram_recommendation_writes_enabled", lambda: True)
    monkeypatch.setattr(daily_bot_run, "_has_valid_telegram_event_claim", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(daily_bot_run, "_notify_central_telegram", lambda msg, stype="central": captured.append((msg, stype)) or True)

    delivered = daily_bot_run._send_telegram_exit(
        "INEG",
        "EGX",
        0.608,
        0.608,
        0.0,
        "cancelled",
        exit_reason="corporate_action_adjustment",
        closed_on="2026-11-19",
        corporate_action={
            "day": "2026-11-19",
            "prior_close": 0.608,
            "open": 0.389,
            "close": 0.401,
            "change_pct": -34.05,
            "confirmed": False,
        },
        event_id="e",
        claim_token="t",
        event_client=object(),
    )

    assert delivered is True
    assert len(captured) == 1
    msg, service_type = captured[0]
    assert service_type == "recommendation_exit"
    assert "إلغاء تقني" in msg
    assert "0.00%" in msg
    assert "تنفيذ الوقف" not in msg
    assert "0.608" in msg
    assert "0.401" in msg


def test_evaluate_old_recommendations_verifies_live_and_rebases_on_corporate_action(monkeypatch):
    import api.corporate_actions_engine as ca_engine
    import api.hf_history_cache as history
    import api.recommendation_data as data
    import api.recommendation_events as events

    monkeypatch.setattr(data, "repair_history", lambda client, rec, current, today: (current, {"status": "failed"}))
    # Simulate initial cache empty, triggering verify_symbol_corporate_action_live on-demand
    monkeypatch.setattr(ca_engine, "load_price_adjusting_action_dates", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        ca_engine,
        "verify_symbol_corporate_action_live",
        lambda *_args, **_kwargs: {
            "confirmed": True,
            "action_type": "rights_issue",
            "action_type_ar": "حقوق اكتتاب",
            "title": "اليوم.. نهاية حق اكتتاب زيادة رأسمال المجموعة المتكاملة - جريدة البورصة",
            "date": "2026-11-19",
            "source": "google_news_rss",
        },
    )

    rec = dict(
        id="rec-ineg",
        symbol="INEG",
        exchange="EGX",
        status="open",
        entry_price=0.608,
        target_price=0.790,
        stop_loss=0.517,
        last_close=0.608,
        created_at="2026-11-18T14:00:00+00:00",
        updated_at="2026-11-18T14:00:00+00:00",
        adjustments=[],
        rich_details={"evaluation": {"last_evaluated_date": "2026-11-18"}, "recommendation_policy": {"max_sessions": 20}},
    )
    archive = pd.DataFrame([
        dict(symbol="INEG", exchange="EGX", date=pd.Timestamp("2026-11-18"), open=0.553, high=0.608, low=0.553, close=0.608, volume=87617719),
        dict(symbol="INEG", exchange="EGX", date=pd.Timestamp("2026-11-19"), open=0.382596, high=0.392035, low=0.361201, close=0.388889, volume=208352862),
        dict(symbol="INEG", exchange="EGX", date=pd.Timestamp("2026-11-22"), open=0.389, high=0.426, low=0.365, close=0.401, volume=133705269),
    ])

    recorded_events = []
    sent_vip = []
    sent_free = []

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

        def lt(self, *_args):
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
                rec.update(self.patch)
                return SimpleNamespace(data=[rec.copy()])
            if self.fields == "id":
                return SimpleNamespace(data=[{"id": rec["id"]}])
            return SimpleNamespace(data=[rec.copy()])

    class Client:
        def table(self, table):
            return Query(table)

    monkeypatch.setattr(daily_bot_run, "supabase", Client())
    monkeypatch.setattr(history, "load_history_snapshot", lambda _ex: archive)
    monkeypatch.setattr(
        events,
        "record_event",
        lambda _sb, rec_id, etype, **kwargs: recorded_events.append((rec_id, etype, kwargs)) or {"id": "ev-ineg"},
    )
    monkeypatch.setattr(events, "claim_event_delivery", lambda *_args, **_kwargs: "claim-1")
    monkeypatch.setattr(events, "update_telegram_delivery", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(daily_bot_run, "_telegram_recommendation_writes_enabled", lambda: True)
    monkeypatch.setattr(daily_bot_run, "_has_valid_telegram_event_claim", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        daily_bot_run,
        "_notify_free_telegram",
        lambda msg, stype="central": sent_free.append((msg, stype)) or daily_bot_run.TelegramNotificationOutcome(True, receipts=[{"chat_id": -1, "message_id": 1}]),
    )
    monkeypatch.setattr(
        daily_bot_run,
        "_notify_central_telegram",
        lambda msg, stype="central": sent_vip.append((msg, stype)) or daily_bot_run.TelegramNotificationOutcome(True, receipts=[{"chat_id": -2, "message_id": 2}]),
    )

    report = daily_bot_run.evaluate_old_recommendations(return_report=True)
    assert report["updated"] == 1
    assert rec["status"] == "open"
    assert rec["entry_price"] == pytest.approx(0.389, abs=0.002)
    assert rec["target_price"] == pytest.approx(0.505, abs=0.002)
    assert rec["stop_loss"] == pytest.approx(0.331, abs=0.002)
    assert rec["last_close"] == 0.401
    assert rec["profit_loss_pct"] == pytest.approx(3.08, abs=0.2)
    assert rec["rich_details"]["evaluation"]["rebased"] is True
    assert recorded_events[0][1] == "target_or_stop_adjusted"
    assert len(sent_vip) == 1 and len(sent_free) == 1
    assert "تحديث تلقائي لمستويات التوصية" in sent_vip[0][0]
    assert "0.389" in sent_vip[0][0]


def test_evaluate_old_recommendations_blocks_when_discontinuity_unconfirmed(monkeypatch):
    import api.corporate_actions_engine as ca_engine
    import api.hf_history_cache as history
    import api.recommendation_data as data

    monkeypatch.setattr(data, "repair_history", lambda client, rec, current, today: (current, {"status": "failed"}))
    monkeypatch.setattr(ca_engine, "load_price_adjusting_action_dates", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(ca_engine, "verify_symbol_corporate_action_live", lambda *_args, **_kwargs: None)

    rec = dict(
        id="rec-unconf",
        symbol="UNCF",
        exchange="EGX",
        status="open",
        entry_price=100.0,
        target_price=120.0,
        stop_loss=90.0,
        last_close=100.0,
        created_at="2026-11-18T14:00:00+00:00",
        updated_at="2026-11-18T14:00:00+00:00",
        adjustments=[],
        rich_details={"evaluation": {"last_evaluated_date": "2026-11-18"}, "recommendation_policy": {"max_sessions": 20}},
    )
    archive = pd.DataFrame([
        dict(symbol="UNCF", exchange="EGX", date=pd.Timestamp("2026-11-18"), open=98.0, high=101.0, low=97.0, close=100.0, volume=100000),
        dict(symbol="UNCF", exchange="EGX", date=pd.Timestamp("2026-11-19"), open=70.0, high=72.0, low=69.0, close=71.0, volume=200000),
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

        def lt(self, *_args):
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
                rec.update(self.patch)
                return SimpleNamespace(data=[rec.copy()])
            return SimpleNamespace(data=[rec.copy()])

    class Client:
        def table(self, table):
            return Query(table)

    monkeypatch.setattr(daily_bot_run, "supabase", Client())
    monkeypatch.setattr(history, "load_history_snapshot", lambda _ex: archive)

    report = daily_bot_run.evaluate_old_recommendations(return_report=True)
    assert report["blocked"] == 1
    assert report["blocked_symbols"][0]["reason"] == "unconfirmed_corporate_action_discontinuity"
    assert rec["status"] == "open"
    assert rec["entry_price"] == 100.0
    assert rec["target_price"] == 120.0
    assert rec["stop_loss"] == 90.0


def test_send_telegram_exit_corporate_action_currency_matches_exchange(monkeypatch):
    captured = []
    monkeypatch.setattr(daily_bot_run, "_telegram_recommendation_writes_enabled", lambda: True)
    monkeypatch.setattr(daily_bot_run, "_has_valid_telegram_event_claim", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(daily_bot_run, "_notify_central_telegram", lambda msg, stype="central": captured.append(msg) or True)

    daily_bot_run._send_telegram_exit(
        "1120",
        "TADAWUL",
        85.0,
        85.0,
        0.0,
        "cancelled",
        exit_reason="corporate_action_adjustment",
        closed_on="2026-11-19",
        corporate_action={"day": "2026-11-19", "prior_close": 85.0, "close": 58.0, "change_pct": -31.76},
        event_id="e-sa",
        claim_token="t-sa",
        event_client=object(),
    )
    assert "SAR" in captured[0]
    assert "EGP" not in captured[0]


def test_offload_recommendations_and_chart_markers_exclude_cancelled_and_preserve_limit(monkeypatch):
    from api.routers import offload

    class Query:
        def __init__(self, table, data):
            self.table = table
            self.data = list(data)
            self._limit = None

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, col, val):
            if self.table == "scan_results":
                self.data = [r for r in self.data if r.get(col) == val]
            return self

        def in_(self, col, vals):
            vals_set = set(vals)
            self.data = [r for r in self.data if r.get(col) in vals_set]
            return self

        def gte(self, *_args):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, n):
            self._limit = n
            return self

        def execute(self):
            out = self.data[: self._limit] if self._limit is not None else self.data
            return SimpleNamespace(data=out)

    sample_rows = [
        {"id": "c-1", "symbol": "INEG", "exchange": "EGX", "is_public": True, "status": "cancelled", "created_at": "2026-11-19T12:00:00Z"},
        {"id": "o-1", "symbol": "COMI", "exchange": "EGX", "is_public": True, "status": "open", "created_at": "2026-11-18T12:00:00Z"},
        {"id": "w-1", "symbol": "HRHO", "exchange": "EGX", "is_public": True, "status": "win", "created_at": "2026-11-17T12:00:00Z"},
    ]

    class Client:
        def table(self, name):
            return Query(name, sample_rows if name == "scan_results" else [])

    offload._RECS_CACHE.clear()
    offload._MARKERS_CACHE.clear()
    monkeypatch.setattr(offload, "get_market_supabase", lambda _m: Client())

    bundle = offload._load_recommendations_bundle("egx", "EGX", 2)
    assert [r["id"] for r in bundle["rows"]] == ["o-1", "w-1"]

    marker_rows, _ = offload._load_chart_markers_raw("egx", "EGX", "INEG")
    assert marker_rows == []

