import pytest
from unittest.mock import MagicMock, patch
from api.telegram_bot import TelegramBot
from api.telegram_vip_chat import handle_vip_chat_update


def test_setup_bot_menu_isolates_commands_to_private_only():
    bot = TelegramBot("fake_token_123", None)
    calls = []

    def mock_call_api(method, payload=None, timeout=30):
        calls.append((method, payload))
        return {"ok": True}

    bot._call_api = mock_call_api
    bot._setup_bot_menu()

    methods = [c[0] for c in calls]
    assert "deleteMyCommands" in methods
    assert "setMyCommands" in methods

    # Verify group chats had their commands deleted
    deleted_scopes = [c[1].get("scope", {}).get("type") for c in calls if c[0] == "deleteMyCommands"]
    assert "all_group_chats" in deleted_scopes
    assert "all_chat_administrators" in deleted_scopes

    # Verify setMyCommands only registers start and help for all_private_chats
    set_my_commands_calls = [c for c in calls if c[0] == "setMyCommands"]
    assert len(set_my_commands_calls) == 1
    reg = set_my_commands_calls[0][1]
    assert reg["scope"]["type"] == "all_private_chats"
    commands_registered = [cmd["command"] for cmd in reg["commands"]]
    assert "start" in commands_registered
    assert "help" in commands_registered
    assert "daily" not in commands_registered
    assert "weekly" not in commands_registered


def test_dispatch_command_silently_ignores_group_messages_outside_topic_1680():
    bot = TelegramBot("fake_token_123", None)
    bot._reply = MagicMock()
    bot._handle_daily = MagicMock()
    bot._handle_weekly = MagicMock()
    bot._handle_help = MagicMock()

    # Message from supergroup topic 1 (الدردشة العامة)
    group_msg = {
        "message_id": 999,
        "chat": {"id": -1002083067817, "type": "supergroup"},
        "message_thread_id": 1,
        "text": "/daily@egxbots_bot",
    }

    bot._dispatch_command(-1002083067817, "/daily@egxbots_bot", group_msg, raw_update={"message": group_msg})

    # Must NOT reply and must NOT call daily handler
    bot._reply.assert_not_called()
    bot._handle_daily.assert_not_called()
    bot._handle_weekly.assert_not_called()
    bot._handle_help.assert_not_called()


def test_dispatch_command_routes_private_daily_to_artoro():
    bot = TelegramBot("fake_token_123", None)
    bot._reply = MagicMock()

    private_msg = {
        "message_id": 1001,
        "from": {"id": 12345678, "first_name": "Karim"},
        "chat": {"id": 12345678, "type": "private"},
        "text": "/daily",
    }
    raw_update = {"update_id": 555, "message": private_msg}

    with patch("api.telegram_vip_chat.handle_vip_chat_update") as mock_vip_handler:
        mock_vip_handler.return_value = True
        bot._dispatch_command(12345678, "/daily", private_msg, raw_update=raw_update)
        mock_vip_handler.assert_called_once_with(raw_update, bot.token)
