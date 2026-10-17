import os
import time
from unittest.mock import patch, MagicMock
import pytest

from api.telegram_vip_chat import (
    is_vip_chat_update,
    handle_vip_chat_update,
    format_pipeline_reply_for_telegram,
    build_vip_chat_keyboard,
    build_pricing_dialog_html,
    get_local_pending_prompt,
    set_local_pending_prompt,
    _PROCESSED_EVENTS,
)


@pytest.fixture(autouse=True)
def clear_dedup_state():
    _PROCESSED_EVENTS.clear()
    yield
    _PROCESSED_EVENTS.clear()


def test_is_vip_chat_update_topic_isolation():
    # 1. Message inside Topic 1652 (ARTORO topic in -1002083067817) -> True
    update_in_artoro_topic = {
        "message": {
            "message_id": 101,
            "chat": {"id": -1002083067817, "type": "supergroup"},
            "message_thread_id": 1652,
            "from": {"id": 998877, "first_name": "Ahmed"},
            "text": "حلل فوري",
        }
    }
    assert is_vip_chat_update(update_in_artoro_topic) is True

    # 2. Message inside Topic 153 (Recommendations topic) -> False
    update_in_recs_topic = {
        "message": {
            "message_id": 102,
            "chat": {"id": -1002083067817, "type": "supergroup"},
            "message_thread_id": 153,
            "from": {"id": 998877, "first_name": "Ahmed"},
            "text": "مبروك",
        }
    }
    assert is_vip_chat_update(update_in_recs_topic) is False

    # 3. Message in general topic (thread_id=None) -> False
    update_in_general = {
        "message": {
            "message_id": 103,
            "chat": {"id": -1002083067817, "type": "supergroup"},
            "from": {"id": 998877, "first_name": "Ahmed"},
            "text": "صباح الخير",
        }
    }
    assert is_vip_chat_update(update_in_general) is False

    # 4. Callback query with vip_ prefix -> True
    cb_update = {
        "callback_query": {
            "id": "cb_1",
            "data": "vip_ask_stock",
            "from": {"id": 998877, "first_name": "Ahmed"},
            "message": {
                "message_id": 50,
                "chat": {"id": -1002083067817, "type": "supergroup"},
                "message_thread_id": 1652,
            },
        }
    }
    assert is_vip_chat_update(cb_update) is True


def test_stock_button_sets_pending_prompt_and_processes_stock_name():
    calls = []

    def fake_tg_api(bot_token, method, payload, timeout=15):
        calls.append((method, payload))
        return {"ok": True, "result": {"message_id": 555}}

    def fake_web_api(payload, timeout=75):
        if payload.get("action") == "set_pending_prompt":
            return {
                "ok": True,
                "linked": True,
                "is_pro": False,
                "used": 1,
                "limit": 5,
                "remaining": 4,
                "period": "daily",
            }
        if payload.get("action") == "chat":
            return {
                "ok": True,
                "reply": f"تحليل شامل لسهم ({payload['message']}): السعر 10.50 ج.م",
                "tables": [
                    {
                        "title": "المستويات الفنية",
                        "headers": ["المستوى", "السعر"],
                        "rows": [["الدعم الأول", "10.00"], ["المقاومة الأولى", "11.20"]],
                    }
                ],
                "display_name": "Ahmed",
                "is_pro": False,
                "used": 2,
                "limit": 5,
                "remaining": 3,
                "period": "daily",
            }
        return {"ok": True}

    with patch("api.telegram_vip_chat._call_telegram_api", side_effect=fake_tg_api), patch(
        "api.telegram_vip_chat.call_web_vip_chat_api", side_effect=fake_web_api
    ):
        # Step 1: User clicks "🔍 حلل سهم"
        cb_data = {
            "callback_query": {
                "id": "cb_stock_1",
                "data": "vip_ask_stock",
                "from": {"id": 112233, "first_name": "Ahmed"},
                "message": {
                    "message_id": 10,
                    "chat": {"id": -1002083067817, "type": "supergroup"},
                    "message_thread_id": 1652,
                },
            }
        }
        handled = handle_vip_chat_update(cb_data, "TEST_TOKEN")
        assert handled is True
        assert get_local_pending_prompt(-1002083067817, 112233) == "stock"

        # Verify ForceReply was sent
        send_calls = [p for m, p in calls if m == "sendMessage"]
        assert len(send_calls) == 1
        assert send_calls[0]["reply_markup"]["force_reply"] is True

        # Step 2: User types just "فوري" in Topic 1652
        calls.clear()
        msg_data = {
            "message": {
                "message_id": 11,
                "chat": {"id": -1002083067817, "type": "supergroup"},
                "message_thread_id": 1652,
                "from": {"id": 112233, "first_name": "Ahmed"},
                "text": "فوري",
            }
        }
        handled2 = handle_vip_chat_update(msg_data, "TEST_TOKEN")
        assert handled2 is True
        time.sleep(0.25)

        final_sends = [p for m, p in calls if m == "sendMessage" and "رد أرتورو الذكي" in p.get("text", "")]
        assert len(final_sends) == 1
        assert "حلل سهم فوري" in final_sends[0]["text"]
        assert "المتبقي (اليوم): <code>3</code> من <code>5</code>" in final_sends[0]["text"]


def test_limit_reached_triggers_private_alert_dialog_and_pricing_card():
    calls = []

    def fake_tg_api(bot_token, method, payload, timeout=15):
        calls.append((method, payload))
        return {"ok": True, "result": {"message_id": 777}}

    def fake_web_api(payload, timeout=75):
        return {
            "ok": True,
            "linked": False,
            "is_pro": False,
            "used": 5,
            "limit": 5,
            "remaining": 0,
            "period": "daily",
        }

    with patch("api.telegram_vip_chat._call_telegram_api", side_effect=fake_tg_api), patch(
        "api.telegram_vip_chat.call_web_vip_chat_api", side_effect=fake_web_api
    ):
        cb_data = {
            "callback_query": {
                "id": "cb_limit_99",
                "data": "vip_tool_market",
                "from": {"id": 445566, "first_name": "Mahmoud"},
                "message": {
                    "message_id": 20,
                    "chat": {"id": -1002083067817, "type": "supergroup"},
                    "message_thread_id": 1652,
                },
            }
        }
        handled = handle_vip_chat_update(cb_data, "TEST_TOKEN")
        assert handled is True

        # 1. Verify native popup modal dialog (show_alert=True) was shown ONLY to this user
        alert_calls = [p for m, p in calls if m == "answerCallbackQuery"]
        assert len(alert_calls) == 1
        assert alert_calls[0]["show_alert"] is True
        assert "انتهى رصيدك المجاني" in alert_calls[0]["text"]
        assert "PRO" in alert_calls[0]["text"]

        # 2. Verify Pricing Upgrade Card was sent with /pricing button
        msg_calls = [p for m, p in calls if m == "sendMessage"]
        assert len(msg_calls) >= 1
        card = msg_calls[0]
        assert "مميزات الاشتراك في باقة PRO VIP" in card["text"]
        kb_rows = card["reply_markup"]["inline_keyboard"]
        pricing_btn = kb_rows[0][0]
        assert "/pricing" in pricing_btn["url"]


def test_pro_only_recommendations_gate_for_free_user():
    calls = []

    def fake_tg_api(bot_token, method, payload, timeout=15):
        calls.append((method, payload))
        return {"ok": True, "result": {"message_id": 888}}

    def fake_web_api(payload, timeout=75):
        return {
            "ok": True,
            "linked": True,
            "is_pro": False,
            "used": 1,
            "limit": 5,
            "remaining": 4,
            "period": "daily",
        }

    with patch("api.telegram_vip_chat._call_telegram_api", side_effect=fake_tg_api), patch(
        "api.telegram_vip_chat.call_web_vip_chat_api", side_effect=fake_web_api
    ):
        cb_data = {
            "callback_query": {
                "id": "cb_recs_1",
                "data": "vip_tool_recs",
                "from": {"id": 778899, "first_name": "Karim"},
                "message": {
                    "message_id": 30,
                    "chat": {"id": -1002083067817, "type": "supergroup"},
                    "message_thread_id": 1652,
                },
            }
        }
        handle_vip_chat_update(cb_data, "TEST_TOKEN")

        alert_calls = [p for m, p in calls if m == "answerCallbackQuery"]
        assert len(alert_calls) == 1
        assert alert_calls[0]["show_alert"] is True
        assert "PRO" in alert_calls[0]["text"]
