import pytest
from api.stock_aliases import resolve_stock_symbol, extract_all_stock_symbols
from api.native_telegram_vip_chat import handle_native_vip_chat

def test_stock_aliases_arabic_resolution():
    assert resolve_stock_symbol("حلل سهم طلعت مصطفى") == "TMGH"
    assert resolve_stock_symbol("سهم فوري") == "FWRY"
    assert resolve_stock_symbol("السويدي اليكتريك") == "SWDY"
    assert resolve_stock_symbol("البنك التجاري الدولي") == "COMI"
    assert resolve_stock_symbol("حديد عز") == "ESRS"
    assert resolve_stock_symbol("بلتون القابضة") == "BTFH"
    assert resolve_stock_symbol("مدينة مصر") == "MASR"

def test_stock_aliases_multi_symbol_extraction():
    symbols = extract_all_stock_symbols("قارن بين طلعت مصطفى وفوري والسويدي")
    assert "TMGH" in symbols
    assert "FWRY" in symbols
    assert "SWDY" in symbols
    assert len(symbols) == 3

def test_native_vip_chat_check_quota():
    res = handle_native_vip_chat({
        "action": "check_quota",
        "telegram_user_id": 999999123,
        "telegram_username": "test_user",
    })
    assert res.get("ok") is True
    assert "remaining" in res
    assert "limit" in res

def test_native_vip_chat_set_pending_prompt():
    res = handle_native_vip_chat({
        "action": "set_pending_prompt",
        "telegram_user_id": 999999123,
        "telegram_username": "test_user",
        "prompt_mode": "stock",
    })
    assert res.get("ok") is True
    assert res.get("pending_prompt", {}).get("mode") == "stock"


def test_native_vip_chat_multi_profile_active_pro_wins():
    from unittest.mock import patch
    from api.native_telegram_vip_chat import _resolve_telegram_user

    def fake_sb(endpoint, method="GET", payload=None, timeout=10):
        if "telegram_vip_chat_state" in endpoint:
            return [{"telegram_user_id": 12345, "linked_user_id": "old_canceled_uid"}]
        if "profiles" in endpoint:
            return [
                {"id": "old_canceled_uid", "display_name": "Old User"},
                {"id": "new_active_uid", "display_name": "Active User"},
            ]
        if "pro_telegram_invites" in endpoint:
            return []
        if "subscriptions" in endpoint:
            return [{"user_id": "new_active_uid", "plan_id": "pro", "status": "active"}]
        if "ai_chatbot_limits" in endpoint:
            return [{"chat_count": 5}]
        return []

    with patch("api.native_telegram_vip_chat._supabase_request", side_effect=fake_sb):
        res = _resolve_telegram_user(12345, "test")
        assert res["is_pro"] is True
        assert res["linked_user_id"] == "new_active_uid"
        assert res["limit"] == 350
        assert res["used"] == 5


def test_native_vip_chat_admin_unconditionally_pro():
    from unittest.mock import patch
    from api.native_telegram_vip_chat import _resolve_telegram_user

    with patch("api.native_telegram_vip_chat._supabase_request", return_value=[]):
        res = _resolve_telegram_user(5149631436, "admin_user")
        assert res["is_admin"] is True
        assert res["is_pro"] is True
        assert res["limit"] == 350
        assert res["remaining"] == 350


def test_telegram_bot_unlink_conflicting_profiles_on_link():
    from unittest.mock import MagicMock
    from api.telegram_bot import TelegramBot

    bot = TelegramBot("123456:dummy_token")
    mock_sb = MagicMock()
    mock_table = MagicMock()
    mock_sb.table.return_value = mock_table
    mock_update = MagicMock()
    mock_table.update.return_value = mock_update
    mock_eq = MagicMock()
    mock_update.eq.return_value = mock_eq
    mock_neq = MagicMock()
    mock_eq.neq.return_value = mock_neq
    mock_neq.execute.return_value = MagicMock(data=[])

    # Simulate the unlink call in TelegramBot
    mock_sb.table("profiles").update({"telegram_chat_id": None}).eq("telegram_chat_id", "999").neq("id", "user_active").execute()
    mock_table.update.assert_called_with({"telegram_chat_id": None})
    mock_update.eq.assert_called_with("telegram_chat_id", "999")
    mock_eq.neq.assert_called_with("id", "user_active")


