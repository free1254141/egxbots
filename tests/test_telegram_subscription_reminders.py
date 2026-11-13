import os
from unittest.mock import MagicMock, patch
import pytest

from jobs.telegram_subscription_reminders import (
    determine_reminder_stage,
    is_lifetime_plan,
    message_for,
    parse_chat_id,
    send_private_telegram,
    run_subscription_reminders,
    get_telegram_token,
)
from api.jobs.telegram_subscription_reminders import (
    run_subscription_reminders as api_run_subscription_reminders,
)


def test_is_lifetime_plan():
    assert is_lifetime_plan("lifetime") is True
    assert is_lifetime_plan("pro_lifetime") is True
    assert is_lifetime_plan("lifetime_vip") is True
    assert is_lifetime_plan("lifetime-vip") is True
    assert is_lifetime_plan("LIFETIME") is True
    assert is_lifetime_plan("pro") is False
    assert is_lifetime_plan("free") is False
    assert is_lifetime_plan("pro_6m") is False
    assert is_lifetime_plan("pro_1y") is False
    assert is_lifetime_plan("") is False
    assert is_lifetime_plan(None) is False


def test_determine_reminder_stage():
    # Stage 7 window: 4 to 7 days
    assert determine_reminder_stage(7) == 7
    assert determine_reminder_stage(6) == 7
    assert determine_reminder_stage(5) == 7
    assert determine_reminder_stage(4) == 7

    # Stage 3 window: 1 to 3 days
    assert determine_reminder_stage(3) == 3
    assert determine_reminder_stage(2) == 3
    assert determine_reminder_stage(1) == 3

    # Stage 0 window: -1 to 0 days
    assert determine_reminder_stage(0) == 0
    assert determine_reminder_stage(-1) == 0

    # Outside windows: None
    assert determine_reminder_stage(8) is None
    assert determine_reminder_stage(30) is None
    assert determine_reminder_stage(-2) is None
    assert determine_reminder_stage(-10) is None


def test_get_telegram_token_never_uses_support_bot():
    with patch.dict(os.environ, {
        "SUBSCRIPTION_REMINDER_BOT_TOKEN": "",
        "SUPPORT_BOT_TOKEN": "support-token",
        "ARTORO_AI_BOT": "",
        "TELEGRAM_BOT_TOKEN": "subscription-token",
    }, clear=False):
        assert get_telegram_token() == "subscription-token"


def test_get_telegram_token_uses_artoro_ai_bot():
    with patch.dict(os.environ, {
        "SUBSCRIPTION_REMINDER_BOT_TOKEN": "",
        "SUPPORT_BOT_TOKEN": "support-token",
        "ARTORO_AI_BOT": "artoro-main-bot-token",
        "TELEGRAM_BOT_TOKEN": "fallback-token",
    }, clear=False):
        assert get_telegram_token() == "artoro-main-bot-token"


def test_get_telegram_token_allows_dedicated_override():
    with patch.dict(os.environ, {
        "SUBSCRIPTION_REMINDER_BOT_TOKEN": "reminder-token",
        "SUPPORT_BOT_TOKEN": "support-token",
        "TELEGRAM_BOT_TOKEN": "other-token",
    }, clear=False):
        assert get_telegram_token() == "reminder-token"


def test_parse_chat_id():
    assert parse_chat_id(12345678) == 12345678
    assert parse_chat_id("12345678") == 12345678
    assert parse_chat_id("12345678_invite_code") == 12345678
    assert parse_chat_id("  987654321  ") == 987654321
    # Groups / Channels (negative IDs) must be rejected for privacy
    assert parse_chat_id(-1002083067817) is None
    assert parse_chat_id("-1002083067817") is None
    # Invalid strings
    assert parse_chat_id("invalid_chat") is None
    assert parse_chat_id("") is None
    assert parse_chat_id(None) is None


def test_message_for():
    msg7 = message_for(stage=7, days_left=7, end_date="2026-10-28")
    assert "7 أيام" in msg7
    assert "2026-10-28" in msg7
    assert "https://egxbots.com" in msg7

    msg3 = message_for(stage=3, days_left=2, end_date="2026-10-23")
    assert "يومين" in msg3
    assert "2026-10-23" in msg3

    msg1 = message_for(stage=3, days_left=1, end_date="2026-10-22")
    assert "يوم واحد" in msg1

    msg0 = message_for(stage=0, days_left=0, end_date="2026-10-21")
    assert "النهارده" in msg0


def test_send_private_telegram_relay_fallback():
    with patch.dict(os.environ, {"TELEGRAM_RELAY_URL": "https://relay.test.org"}):
        with patch("requests.post") as mock_post:
            # First attempt (relay) fails, second attempt (api.telegram.org) succeeds
            mock_res_fail = MagicMock()
            mock_res_fail.status_code = 502
            mock_res_fail.text = "Bad Gateway"

            mock_res_ok = MagicMock()
            mock_res_ok.status_code = 200
            mock_res_ok.json.return_value = {"ok": True, "result": {"message_id": 9999}}

            mock_post.side_effect = [mock_res_fail, mock_res_ok]

            res = send_private_telegram(123456, "Hello", "test_token")
            assert res == {"message_id": 9999}
            assert mock_post.call_count == 2
            assert "https://relay.test.org" in mock_post.call_args_list[0][0][0]
            assert "https://api.telegram.org" in mock_post.call_args_list[1][0][0]


def test_send_private_telegram_rejects_negative_id():
    with pytest.raises(ValueError):
        send_private_telegram(-100, "Hello", "test_token")


def test_run_subscription_reminders_filters_lifetime():
    mock_subs = [
        {"id": "sub-1", "user_id": "u-1", "plan_id": "lifetime", "status": "active", "current_period_end": "2026-10-28T00:00:00Z"},
        {"id": "sub-2", "user_id": "u-2", "plan_id": "pro_lifetime", "status": "active", "current_period_end": "2026-10-28T00:00:00Z"},
    ]

    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "fake_key",
        "TELEGRAM_BOT_TOKEN": "fake_token",
    }):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_subs
            mock_get.return_value = mock_resp

            result = run_subscription_reminders(dry_run=True)
            assert result["status"] == "completed"
            assert result["eligible"] == 0
            assert result["sent"] == 0


def test_api_jobs_package_import_equivalence():
    """Verify that both api.jobs and root jobs import the exact same runner."""
    assert callable(api_run_subscription_reminders)
    assert callable(run_subscription_reminders)
    assert api_run_subscription_reminders.__name__ == run_subscription_reminders.__name__


def test_permanent_telegram_errors_are_detected():
    from api.jobs.telegram_subscription_reminders import _is_permanent_telegram_error

    assert _is_permanent_telegram_error(
        'Telegram API HTTP 403: {"ok":false,"error_code":403,"description":"Forbidden: bot can\'t initiate conversation with a user"}'
    )
    assert _is_permanent_telegram_error("Bad Request: chat not found")
    assert _is_permanent_telegram_error("Forbidden: bot was blocked by the user")
    # Transient failures stay retryable inside the same run.
    assert not _is_permanent_telegram_error("HTTPSConnectionPool: Read timed out. (read timeout=20)")
    assert not _is_permanent_telegram_error("Telegram API HTTP 502: Bad Gateway")


def test_support_copy_dedupe_detects_existing_message():
    from api.jobs.telegram_subscription_reminders import _support_copy_already_delivered

    with patch("requests.get") as mock_get:
        mock_res = MagicMock()
        mock_res.ok = True
        mock_res.json.return_value = [{"id": "m1", "content": "نفس نص التذكير"}]
        mock_get.return_value = mock_res

        assert _support_copy_already_delivered("https://x.supabase.co/rest/v1", {}, "u-1", "نفس نص التذكير") is True
        assert _support_copy_already_delivered("https://x.supabase.co/rest/v1", {}, "u-1", "نص مختلف") is False


def test_failed_reminder_is_not_resent_and_does_not_touch_support_chat():
    """A previously failed delivery must not produce a second web support message."""
    from datetime import datetime, timedelta, timezone
    from api.jobs.telegram_subscription_reminders import run_subscription_reminders

    now = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)
    period_end = (now + timedelta(days=1)).isoformat()

    def fake_get(url, *args, **kwargs):
        res = MagicMock()
        res.ok = True
        res.status_code = 200
        if url.endswith("/subscriptions"):
            res.json.return_value = [
                {"id": "sub-1", "user_id": "u-1", "plan_id": "pro", "status": "active",
                 "current_period_end": period_end},
            ]
        elif url.endswith("/profiles"):
            res.json.return_value = [{"id": "u-1", "telegram_chat_id": "123456"}]
        elif "telegram_subscription_reminder_log" in url:
            res.json.return_value = [{"id": "log-1", "status": "failed",
                                      "created_at": "2026-11-12T08:00:00+00:00"}]
        else:
            res.json.return_value = []
        return res

    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "fake_key",
        "TELEGRAM_BOT_TOKEN": "fake_token",
    }):
        with patch("requests.get", side_effect=fake_get), patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(ok=True, status_code=201, text="[]", json=lambda: [])

            result = run_subscription_reminders(now=now)

    assert result["sent"] == 0
    assert result["failed"] == 0
    # Only the idempotency insert is attempted; no Telegram send, no support copy.
    assert mock_post.call_count == 1
    posted_urls = [call.args[0] for call in mock_post.call_args_list]
    assert all("support_messages" not in url for url in posted_urls)
    assert all("sendMessage" not in url for url in posted_urls)

