"""Offline unit tests for process_signup_telegram_nudge in api.marketing_lifecycle."""

from types import SimpleNamespace
from unittest.mock import patch

import api.marketing_lifecycle as ml


class _FakeQuery:
    def __init__(self, table_name: str, db: dict):
        self._table = table_name
        self._db = db
        self._filters = []
        self._limit = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, col: str, val):
        self._filters.append(("eq", col, val))
        return self

    def is_(self, col: str, val):
        self._filters.append(("is", col, val))
        return self

    def gte(self, col: str, val):
        self._filters.append(("gte", col, val))
        return self

    def lte(self, col: str, val):
        self._filters.append(("lte", col, val))
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def execute(self):
        rows = list(self._db.get(self._table, []))
        for kind, col, val in self._filters:
            if kind == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif kind == "is" and val == "null":
                rows = [r for r in rows if r.get(col) is None]
            elif kind == "gte":
                rows = [r for r in rows if (r.get(col) or "") >= val]
            elif kind == "lte":
                rows = [r for r in rows if (r.get(col) or "") <= val]
        if self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=rows)


class _FakeSupabase:
    def __init__(self, db: dict):
        self._db = db

    def table(self, name: str):
        return _FakeQuery(name, self._db)


def _base_db():
    return {
        "profiles": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "display_name": "Ahmed",
                "username": "ahmed",
                "telegram_chat_id": None,
                "created_at": "2026-11-25T10:00:00+00:00",
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "display_name": "HasTrial",
                "username": "hastrial",
                "telegram_chat_id": None,
                "created_at": "2026-11-25T10:05:00+00:00",
            },
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "display_name": "HasSub",
                "username": "hassub",
                "telegram_chat_id": None,
                "created_at": "2026-11-25T10:10:00+00:00",
            },
            {
                "id": "44444444-4444-4444-4444-444444444444",
                "display_name": "HasOrder",
                "username": "hasorder",
                "telegram_chat_id": None,
                "created_at": "2026-11-25T10:15:00+00:00",
            },
            {
                "id": "55555555-5555-5555-5555-555555555555",
                "display_name": "Founder",
                "username": "founder",
                "telegram_chat_id": None,
                "created_at": "2026-11-25T10:20:00+00:00",
            },
        ],
        "subscription_trials": [{"user_id": "22222222-2222-2222-2222-222222222222"}],
        "subscriptions": [{"id": "s1", "user_id": "33333333-3333-3333-3333-333333333333"}],
        "local_payment_orders": [
            {"id": "o1", "user_id": "44444444-4444-4444-4444-444444444444", "status": "approved"},
        ],
        "founders_offer_members": [{"user_id": "55555555-5555-5555-5555-555555555555"}],
    }


def test_signup_nudge_sends_only_to_eligible_unlinked_user():
    db = _base_db()
    sent_calls = []
    logged_calls = []

    def fake_send(to_email, subject, html_body, out=None):
        if out is not None:
            out["provider_message_id"] = "prov-1"
        sent_calls.append((to_email, subject, html_body))
        return True

    def fake_record(uid, email, msg_type, metadata=None, message_id=None, provider_message_id=None):
        logged_calls.append((uid, email, msg_type, provider_message_id))

    with (
        patch.object(ml, "supabase", _FakeSupabase(db)),
        patch.object(ml, "MARKETING_DAILY_EMAIL_CAP", 90),
        patch.object(ml, "get_daily_sent_count", return_value=0),
        patch.object(ml, "has_recent_message", return_value=False),
        patch.object(ml, "get_user_email", side_effect=lambda uid: f"{uid[:8]}@example.com"),
        patch.object(ml, "is_user_unsubscribed", return_value=False),
        patch.object(ml, "send_resend_email", side_effect=fake_send),
        patch.object(ml, "record_marketing_message", side_effect=fake_record),
    ):
        # Pin window to include the 2026-11-25T10:* profiles
        from datetime import datetime, timezone

        fixed_now = datetime(2026, 11, 25, 11, 30, tzinfo=timezone.utc)
        with patch.object(ml, "datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            count = ml.process_signup_telegram_nudge()

    assert count == 1
    assert len(sent_calls) == 1
    to_email, _subj, html = sent_calls[0]
    assert to_email == "11111111@example.com"
    assert "/start 11111111-1111-1111-1111-111111111111" in html
    assert "t.me%2Fegxbots_bot%3Fstart%3D11111111-1111-1111-1111-111111111111" in html
    assert "/api/marketing/click?" in html
    assert logged_calls == [
        ("11111111-1111-1111-1111-111111111111", "11111111@example.com", "signup_tg_trial_nudge", "prov-1")
    ]


def test_signup_nudge_excludes_recent_nudge_reengagement_and_unsubscribed():
    db = {
        "profiles": [
            {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "display_name": "SentNudge", "telegram_chat_id": None, "created_at": "2026-11-25T10:00:00+00:00"},
            {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "display_name": "Reengaged", "telegram_chat_id": None, "created_at": "2026-11-25T10:01:00+00:00"},
            {"id": "cccccccc-cccc-cccc-cccc-cccccccccccc", "display_name": "Unsubbed", "telegram_chat_id": None, "created_at": "2026-11-25T10:02:00+00:00"},
        ],
        "subscription_trials": [],
        "subscriptions": [],
        "local_payment_orders": [],
        "founders_offer_members": [],
    }
    sent_calls = []

    def fake_recent(uid, msg_type, _days):
        if uid == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" and msg_type == "signup_tg_trial_nudge":
            return True
        if uid == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" and msg_type == "trial_reengagement_fix_nov25":
            return True
        return False

    def fake_unsub(uid, _email):
        return uid == "cccccccc-cccc-cccc-cccc-cccccccccccc"

    with (
        patch.object(ml, "supabase", _FakeSupabase(db)),
        patch.object(ml, "MARKETING_DAILY_EMAIL_CAP", 90),
        patch.object(ml, "get_daily_sent_count", return_value=0),
        patch.object(ml, "has_recent_message", side_effect=fake_recent),
        patch.object(ml, "get_user_email", side_effect=lambda uid: f"{uid[:8]}@example.com"),
        patch.object(ml, "is_user_unsubscribed", side_effect=fake_unsub),
        patch.object(ml, "send_resend_email", side_effect=lambda *a, **kw: sent_calls.append(a) or True),
        patch.object(ml, "record_marketing_message"),
    ):
        from datetime import datetime, timezone

        fixed_now = datetime(2026, 11, 25, 11, 30, tzinfo=timezone.utc)
        with patch.object(ml, "datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            count = ml.process_signup_telegram_nudge()

    assert count == 0
    assert sent_calls == []


def test_signup_nudge_respects_daily_cap():
    db = {
        "profiles": [
            {"id": "11111111-1111-1111-1111-111111111111", "display_name": "U1", "telegram_chat_id": None, "created_at": "2026-11-25T10:00:00+00:00"},
            {"id": "22222222-2222-2222-2222-222222222222", "display_name": "U2", "telegram_chat_id": None, "created_at": "2026-11-25T10:01:00+00:00"},
        ],
        "subscription_trials": [],
        "subscriptions": [],
        "local_payment_orders": [],
        "founders_offer_members": [],
    }
    sent_calls = []

    with (
        patch.object(ml, "supabase", _FakeSupabase(db)),
        patch.object(ml, "MARKETING_DAILY_EMAIL_CAP", 10),
        patch.object(ml, "get_daily_sent_count", return_value=9),
        patch.object(ml, "has_recent_message", return_value=False),
        patch.object(ml, "get_user_email", side_effect=lambda uid: f"{uid[:8]}@example.com"),
        patch.object(ml, "is_user_unsubscribed", return_value=False),
        patch.object(ml, "send_resend_email", side_effect=lambda *a, **kw: sent_calls.append(a[0]) or True),
        patch.object(ml, "record_marketing_message"),
    ):
        from datetime import datetime, timezone

        fixed_now = datetime(2026, 11, 25, 11, 30, tzinfo=timezone.utc)
        with patch.object(ml, "datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            count = ml.process_signup_telegram_nudge()

    assert count == 1
    assert sent_calls == ["11111111@example.com"]
