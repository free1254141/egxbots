from datetime import datetime, timezone

from api.fundamentals_refresh import (
    is_fundamentals_refresh_due,
    quarterly_fundamentals_due,
    should_run_quarterly_fundamentals,
)


def test_fundamentals_refresh_due_uses_ninety_day_age():
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    assert is_fundamentals_refresh_due("2026-07-05T15:10:00+00:00", now=now)
    assert not is_fundamentals_refresh_due("2026-09-06T15:10:00+00:00", now=now)
    assert is_fundamentals_refresh_due(None, now=now)


def test_quarterly_refresh_only_runs_scheduled_sunday_close():
    sunday = datetime(2026, 10, 11, 17, 0, tzinfo=timezone.utc)
    monday = datetime(2026, 10, 12, 17, 0, tzinfo=timezone.utc)
    assert should_run_quarterly_fundamentals("scheduled", "close", sunday)
    assert not should_run_quarterly_fundamentals("scheduled", "midday", sunday)
    assert not should_run_quarterly_fundamentals("scheduled", "close", monday)
    assert not should_run_quarterly_fundamentals("manual", "close", sunday)


def test_freshness_check_uses_one_narrow_oldest_snapshot_query():
    calls = []

    class Query:
        def select(self, value):
            calls.append(("select", value))
            return self

        def eq(self, *args):
            calls.append(("eq", args))
            return self

        def order(self, *args, **kwargs):
            calls.append(("order", args, kwargs))
            return self

        def limit(self, value):
            calls.append(("limit", value))
            return self

        def execute(self):
            return type("Result", (), {"data": [{"updated_at": "2026-07-05T15:10:00+00:00"}]})()

    class Client:
        def table(self, name):
            calls.append(("table", name))
            return Query()

    due, reason = quarterly_fundamentals_due(Client())
    assert due is True
    assert "older than 90" in reason
    assert ("limit", 1) in calls
