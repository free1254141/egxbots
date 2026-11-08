"""
Unit tests for B2B Telegram Group Bot Licensing and Explicit Triggers.
"""

from unittest.mock import MagicMock, patch

from api.easykash_payments import _PLANS
from api.payment_common import plan_amount_egp, subscription_days
from api.telegram_b2b import (
    handle_b2b_group_message,
    is_explicit_group_trigger,
)


def test_b2b_plans_in_easykash_and_common():
    assert "b2b_starter" in _PLANS
    assert "b2b_pro" in _PLANS
    assert "b2b_enterprise" in _PLANS

    assert plan_amount_egp("b2b_starter") == 1000.0
    assert plan_amount_egp("b2b_pro") == 1500.0
    assert plan_amount_egp("b2b_enterprise") == 2500.0

    assert subscription_days("b2b_starter") == 30
    assert subscription_days("b2b_pro") == 30
    assert subscription_days("b2b_enterprise") == 30


def test_is_explicit_group_trigger_filters_general_chatter():
    # Ordinary chatter must NOT trigger the bot
    triggered, _ = is_explicit_group_trigger("صباح الخير يا رجالة", {})
    assert not triggered

    triggered, _ = is_explicit_group_trigger("السوق نازل النهاردة والسيولة ضعيفة", {})
    assert not triggered

    triggered, _ = is_explicit_group_trigger("حد يعرف طلعت مصطفى كسر دعم؟", {})
    assert not triggered


def test_is_explicit_group_trigger_detects_mentions_and_commands():
    # Mention trigger
    triggered, clean = is_explicit_group_trigger("@egxbots_bot حلل سهم فوري", {})
    assert triggered
    assert "حلل سهم فوري" in clean

    # Command trigger
    triggered, clean = is_explicit_group_trigger("/ask رأيك في طلعت مصطفى", {})
    assert triggered
    assert "رأيك في طلعت مصطفى" in clean

    # Custom Arabic command trigger
    triggered, clean = is_explicit_group_trigger("!سهم COMI", {})
    assert triggered
    assert "COMI" in clean

    # Reply to bot trigger
    reply_msg = {"reply_to_message": {"from": {"is_bot": True, "id": 9999}}}
    triggered, clean = is_explicit_group_trigger("طب والهدف القادم كام؟", reply_msg)
    assert triggered
    assert clean == "طب والهدف القادم كام؟"


def test_unlicensed_group_sends_upgrade_prompt():
    fake_msg = {
        "message_id": 1234,
        "from": {"id": 5555, "is_bot": False, "first_name": "Ahmed"},
        "chat": {"id": -1001234567, "type": "supergroup"},
        "text": "@egxbots_bot حلل سهم فوري",
    }

    with patch("api.telegram_b2b._call_telegram_api") as mock_api:
        with patch("api.telegram_b2b.supabase") as mock_sb:
            mock_rpc = MagicMock()
            mock_rpc.execute.return_value.data = {"allowed": False, "reason": "not_licensed"}
            mock_sb.rpc.return_value = mock_rpc

            handled = handle_b2b_group_message(
                bot_token="fake_token",
                chat_id=-1001234567,
                text="@egxbots_bot حلل سهم فوري",
                msg=fake_msg,
            )

            assert handled is True
            mock_api.assert_called_once()
            args = mock_api.call_args[0]
            payload = args[2]
            assert "مرحباً بكم في منصة EGX BOTS" in payload["text"]
            assert "pricing?mode=b2b" in payload["text"]
            assert payload["chat_id"] == -1001234567


def test_daily_limit_reached_informs_group():
    fake_msg = {
        "message_id": 1235,
        "from": {"id": 5555, "is_bot": False, "first_name": "Ahmed"},
        "chat": {"id": -1001234567, "type": "supergroup"},
        "text": "/ask حلل سهم السويدي",
    }

    with patch("api.telegram_b2b._call_telegram_api") as mock_api:
        with patch("api.telegram_b2b.supabase") as mock_sb:
            mock_rpc = MagicMock()
            mock_rpc.execute.return_value.data = {
                "allowed": False,
                "reason": "group_daily_limit_reached",
                "daily_limit": 50,
                "daily_used": 50,
            }
            mock_sb.rpc.return_value = mock_rpc

            handled = handle_b2b_group_message(
                bot_token="fake_token",
                chat_id=-1001234567,
                text="/ask حلل سهم السويدي",
                msg=fake_msg,
            )

            assert handled is True
            mock_api.assert_called_once()
            payload = mock_api.call_args[0][2]
            assert "وصلت المجموعة للحد اليومي المخصص (50/50 استفسار)" in payload["text"]
