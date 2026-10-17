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
    # 1. Message inside Topic 1680 (ARTORO topic in -1002083067817) -> True
    update_in_artoro_topic = {
        "message": {
            "message_id": 101,
            "chat": {"id": -1002083067817, "type": "supergroup"},
            "message_thread_id": 1680,
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
                "message_thread_id": 1680,
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
                    "message_thread_id": 1680,
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

        # Step 2: User types just "فوري" in Topic 1680
        calls.clear()
        msg_data = {
            "message": {
                "message_id": 11,
                "chat": {"id": -1002083067817, "type": "supergroup"},
                "message_thread_id": 1680,
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
                    "message_thread_id": 1680,
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
                    "message_thread_id": 1680,
                },
            }
        }
        handle_vip_chat_update(cb_data, "TEST_TOKEN")

        alert_calls = [p for m, p in calls if m == "answerCallbackQuery"]
        assert len(alert_calls) == 1
        assert alert_calls[0]["show_alert"] is True
        assert "PRO" in alert_calls[0]["text"]


def test_unprompted_group_chat_is_ignored_without_button_press():
    """
    Members chatting with each other in Topic 1680 without clicking an ARTORO menu button
    must NOT trigger ARTORO replies or deduct from their quota.
    """
    tg_calls = []
    web_calls = []

    def fake_tg_api(bot_token, method, payload, timeout=15):
        tg_calls.append((method, payload))
        return {"ok": True, "result": {"message_id": 999}}

    def fake_web_api(payload, timeout=75):
        web_calls.append(payload)
        return {"ok": True}

    with patch("api.telegram_vip_chat._call_telegram_api", side_effect=fake_tg_api), patch(
        "api.telegram_vip_chat.call_web_vip_chat_api", side_effect=fake_web_api
    ):
        # Ensure user has no pending prompt
        set_local_pending_prompt(-1002083067817, 556677, None)

        msg_data = {
            "message": {
                "message_id": 205,
                "chat": {"id": -1002083067817, "type": "supergroup"},
                "message_thread_id": 1680,
                "from": {"id": 556677, "first_name": "Omar"},
                "text": "يا جماعة حد اشترى في فوري النهارده؟ إيه رأيكم في السوق؟",
            }
        }
        handled = handle_vip_chat_update(msg_data, "TEST_TOKEN")
        assert handled is True
        # Zero web API calls (no quota deducted) and zero Telegram messages sent by ARTORO
        assert len(web_calls) == 0
        assert len(tg_calls) == 0


def test_private_bot_button_in_topic_and_direct_private_chat():
    """
    1. Public topic keyboard has '🔒 تحدث مع أرتورو في شات خاص (@egxbots_bot)' button.
    2. In private chat with @egxbots_bot (chat.type == 'private'), users can type directly
       or send /start artoro_chat to get the private panel.
    """
    topic_kb = build_vip_chat_keyboard(is_private=False)
    last_row = topic_kb["inline_keyboard"][-1]
    assert len(last_row) == 1
    assert "@egxbots_bot" in last_row[0]["text"]
    assert "https://t.me/egxbots_bot?start=artoro_chat" in last_row[0]["url"]

    tg_calls = []
    web_calls = []

    def fake_tg_api(bot_token, method, payload, timeout=15):
        tg_calls.append((method, payload))
        return {"ok": True, "result": {"message_id": 888}}

    def fake_web_api(payload, timeout=75):
        web_calls.append(payload)
        return {
            "ok": True,
            "reply": "تحليل خاص لسهم فوري",
            "tables": [],
            "display_name": "Sara",
            "is_pro": True,
            "used": 1,
            "limit": 350,
            "remaining": 349,
            "period": "monthly",
        }

    with patch("api.telegram_vip_chat._call_telegram_api", side_effect=fake_tg_api), patch(
        "api.telegram_vip_chat.call_web_vip_chat_api", side_effect=fake_web_api
    ):
        # 1. /start artoro_chat in private chat
        start_msg = {
            "message": {
                "message_id": 301,
                "chat": {"id": 990011, "type": "private"},
                "from": {"id": 990011, "first_name": "Sara"},
                "text": "/start artoro_chat",
            }
        }
        assert handle_vip_chat_update(start_msg, "TEST_TOKEN") is True
        assert len(tg_calls) == 1
        assert "الشات الخاص مع أرتورو" in tg_calls[0][1]["text"]

        # 2. Direct text in private chat without pressing a button first
        tg_calls.clear()
        direct_msg = {
            "message": {
                "message_id": 302,
                "chat": {"id": 990011, "type": "private"},
                "from": {"id": 990011, "first_name": "Sara"},
                "text": "حلل سهم فوري",
            }
        }
        assert handle_vip_chat_update(direct_msg, "TEST_TOKEN") is True
        time.sleep(0.25)
        assert len(web_calls) == 1
        assert web_calls[0]["message"] == "حلل سهم فوري"




def test_telegram_reply_has_site_and_pricing_links_without_telegram_promo():
    from api.telegram_vip_chat import format_pipeline_reply_for_telegram

    reply = (
        "### تحليل سهم\n\nتم التحليل\n\n"
        "📢 [قناة EGX Bots المجانية على تليجرام للتنبيهات والفرص](https://t.me/egxbots)\n"
    )
    out = format_pipeline_reply_for_telegram(reply, [], "Ahmed", 1, False, 1, 5, 4, "daily")
    assert "t.me/egxbots" not in out
    assert "قناة EGX Bots المجانية" not in out
    assert "/pricing" in out
    assert "موقع EGX Bots" in out
    assert "صفحة التسعير" in out


def test_telegram_api_retries_on_flood_control(monkeypatch):
    import api.telegram_vip_chat as vip

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("TELEGRAM_TEST_MODE", "false")
    monkeypatch.setattr(vip.time, "sleep", lambda *_: None)
    calls = []

    class Resp:
        def __init__(self, data):
            self._d = data

        def json(self):
            return self._d

    def fake_post(url, json=None, timeout=None):
        calls.append(url)
        if len(calls) == 1:
            return Resp({"ok": False, "error_code": 429, "parameters": {"retry_after": 1}})
        return Resp({"ok": True, "result": {"message_id": 5}})

    monkeypatch.setattr(vip.requests, "post", fake_post)
    res = vip._call_telegram_api("tok", "sendMessage", {"chat_id": 1, "text": "x"})
    assert res.get("ok") is True
    assert len(calls) == 2


def test_direct_stock_ticker_in_topic_without_button_press():
    """
    When a user types an EGX stock ticker (like ASCM or PHDC) directly in Topic 1680
    without pressing a menu button first, ARTORO must recognize it and analyze the stock!
    """
    from api.telegram_vip_chat import handle_vip_chat_update, set_local_pending_prompt
    import time

    tg_calls = []
    web_calls = []

    def fake_tg_api(bot_token, method, payload, timeout=15):
        tg_calls.append((method, payload))
        return {"ok": True, "result": {"message_id": 111}}

    def fake_web_api(payload, timeout=75):
        web_calls.append(payload)
        return {
            "ok": True,
            "reply": f"تحليل سهم أسيك للتعدين (ASCM): السعر 42.80 ج.م",
            "tables": [],
            "display_name": "Taher A",
            "is_pro": False,
            "used": 1,
            "limit": 5,
            "remaining": 4,
            "period": "daily",
        }

    with patch("api.telegram_vip_chat._call_telegram_api", side_effect=fake_tg_api), patch(
        "api.telegram_vip_chat.call_web_vip_chat_api", side_effect=fake_web_api
    ):
        set_local_pending_prompt(-1002083067817, 778899, None)

        msg_update = {
            "message": {
                "message_id": 801,
                "chat": {"id": -1002083067817, "type": "supergroup"},
                "message_thread_id": 1680,
                "from": {"id": 778899, "first_name": "Taher", "last_name": "A"},
                "text": "ASCM",
            }
        }
        assert handle_vip_chat_update(msg_update, "TEST_TOKEN") is True

        # Wait briefly for worker thread to execute
        time.sleep(0.1)

        assert len(web_calls) == 1
        assert web_calls[0]["telegram_user_id"] == 778899
        assert "ASCM" in web_calls[0]["message"]
        assert "حلل سهم ASCM" == web_calls[0]["message"]


def test_concurrent_users_in_same_minute_both_get_replies():
    """
    When two users ask in the same minute (e.g. Sameh asks Phdc and Taher asks ASCM),
    both queries must be processed concurrently and both users must receive their replies!
    """
    from api.telegram_vip_chat import handle_vip_chat_update, set_local_pending_prompt
    import time

    tg_calls = []
    web_calls = []

    def fake_tg_api(bot_token, method, payload, timeout=15):
        tg_calls.append((method, payload))
        return {"ok": True, "result": {"message_id": 999}}

    def fake_web_api(payload, timeout=75):
        web_calls.append(payload)
        uid = payload["telegram_user_id"]
        sym = "PHDC" if uid == 1150269195 else "ASCM"
        return {
            "ok": True,
            "reply": f"تحليل سهم {sym}: مؤشرات إيجابية وتداول مستقر",
            "tables": [],
            "display_name": payload.get("telegram_username", ""),
            "is_pro": False,
            "used": 1,
            "limit": 5,
            "remaining": 4,
            "period": "daily",
        }

    with patch("api.telegram_vip_chat._call_telegram_api", side_effect=fake_tg_api), patch(
        "api.telegram_vip_chat.call_web_vip_chat_api", side_effect=fake_web_api
    ):
        # User 1: Sameh Avram has a stock pending prompt and sends "Phdc"
        set_local_pending_prompt(-1002083067817, 1150269195, "stock")
        msg_sameh = {
            "message": {
                "message_id": 901,
                "chat": {"id": -1002083067817, "type": "supergroup"},
                "message_thread_id": 1680,
                "from": {"id": 1150269195, "first_name": "Sameh", "last_name": "Avram"},
                "text": "Phdc",
            }
        }

        # User 2: Taher A sends "ASCM" directly without button prompt
        set_local_pending_prompt(-1002083067817, 223344, None)
        msg_taher = {
            "message": {
                "message_id": 902,
                "chat": {"id": -1002083067817, "type": "supergroup"},
                "message_thread_id": 1680,
                "from": {"id": 223344, "first_name": "Taher", "last_name": "A"},
                "text": "ASCM",
            }
        }

        # Dispatch both within the same minute!
        assert handle_vip_chat_update(msg_sameh, "TEST_TOKEN") is True
        assert handle_vip_chat_update(msg_taher, "TEST_TOKEN") is True

        # Wait briefly for both concurrent worker threads
        time.sleep(0.15)

        # Both web calls must have fired!
        assert len(web_calls) == 2
        user_ids = {c["telegram_user_id"] for c in web_calls}
        assert user_ids == {1150269195, 223344}

        queries = {c["message"] for c in web_calls}
        assert "حلل سهم Phdc" in queries
        assert "حلل سهم ASCM" in queries

