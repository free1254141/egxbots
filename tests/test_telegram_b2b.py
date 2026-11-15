"""
Unit tests for B2B Telegram Group Bot Licensing and Explicit Triggers.
"""

import asyncio
from unittest.mock import MagicMock, patch

from api.easykash_payments import _PLANS
from api.payment_common import activate_subscription, plan_amount_egp, subscription_days
from api.telegram_b2b import (
    _is_group_admin,
    _process_and_send_b2b_reply,
    handle_b2b_chat_migration,
    handle_b2b_group_message,
    handle_b2b_my_chat_member,
    is_explicit_group_trigger,
)
from api.telegram_bot import TelegramBot
from api.telegram_vip_chat import is_vip_chat_update


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


def test_activate_command_links_group():
    fake_msg = {
        "message_id": 9991,
        "from": {"id": 8888, "is_bot": False, "first_name": "VIP Owner"},
        "chat": {"id": -100998877, "type": "supergroup", "title": "قناة توصيات الذهب والأسهم"},
        "text": "/activate b2b_test_code",
    }

    with patch("api.telegram_b2b._call_telegram_api") as mock_api:
        with patch("api.telegram_b2b.supabase") as mock_sb:
            mock_select = MagicMock()
            mock_select.execute.return_value.data = [
                {
                    "id": "b2b_test_code_uuid_1234",
                    "order_id": "ORDER_B2B_100",
                    "tier": "b2b_pro",
                    "daily_limit": 120,
                    "custom_signature": "تحليلات قناة توصيات الذهب",
                }
            ]
            mock_sb.table.return_value.select.return_value.in_.return_value = mock_select
            mock_update = MagicMock()
            mock_sb.table.return_value.update.return_value.eq.return_value = mock_update

            handled = handle_b2b_group_message(
                bot_token="fake_token",
                chat_id=-100998877,
                text="/activate b2b_test_code",
                msg=fake_msg,
            )

            assert handled is True
            mock_api.assert_called_once()
            payload = mock_api.call_args[0][2]
            assert "تم تفعيل وربط رخصة البوت بنجاح" in payload["text"]
            assert payload["chat_id"] == -100998877


def test_start_deep_link_activates_group_automatically():
    fake_msg = {
        "message_id": 9992,
        "from": {"id": 8888, "is_bot": False, "first_name": "VIP Owner"},
        "chat": {"id": -100998877, "type": "supergroup", "title": "قناة النخبة للبورصة المصرية"},
        "text": "/start activate_trial1234",
    }

    with patch("api.telegram_b2b._call_telegram_api") as mock_api:
        with patch("api.telegram_b2b.supabase") as mock_sb:
            mock_select = MagicMock()
            mock_select.execute.return_value.data = [
                {
                    "id": "trial1234_uuid_abc",
                    "order_id": "B2B-TRIAL-89X",
                    "tier": "b2b_pro",
                    "daily_limit": 120,
                    "custom_signature": "تحليلات قناة النخبة",
                }
            ]
            mock_sb.table.return_value.select.return_value.in_.return_value = mock_select
            mock_update = MagicMock()
            mock_sb.table.return_value.update.return_value.eq.return_value = mock_update

            handled = handle_b2b_group_message(
                bot_token="fake_token",
                chat_id=-100998877,
                text="/start activate_trial1234",
                msg=fake_msg,
            )

            assert handled is True
            mock_api.assert_called_once()
            payload = mock_api.call_args[0][2]
            assert "تم تفعيل وربط رخصة البوت بنجاح" in payload["text"]
            assert "فترة تجريبية 3 أيام" in payload["text"]
            assert payload["chat_id"] == -100998877


def test_reply_to_other_bot_does_not_trigger():
    other_bot_reply = {"reply_to_message": {"from": {"is_bot": True, "id": 1111, "username": "MissRose_bot"}}}
    triggered, _ = is_explicit_group_trigger("شكرا", other_bot_reply)
    assert not triggered

    our_bot_reply = {"reply_to_message": {"from": {"is_bot": True, "id": 2222, "username": "egxbots_bot"}}}
    triggered, clean = is_explicit_group_trigger("طب والهدف كام؟", our_bot_reply)
    assert triggered
    assert clean == "طب والهدف كام؟"


def test_activate_rejects_short_code():
    fake_msg = {
        "message_id": 9993,
        "from": {"id": 8888, "is_bot": False, "first_name": "Admin"},
        "chat": {"id": -100998877, "type": "supergroup", "title": "Test Group"},
        "text": "/activate a",
    }

    with patch("api.telegram_b2b._call_telegram_api") as mock_api:
        with patch("api.telegram_b2b.supabase") as mock_sb:
            handled = handle_b2b_group_message(
                bot_token="fake_token",
                chat_id=-100998877,
                text="/activate a",
                msg=fake_msg,
            )

            assert handled is True
            mock_sb.table.assert_not_called()
            payload = mock_api.call_args[0][2]
            assert "كود التفعيل غير صالح أو قصير جداً" in payload["text"]


def test_activate_rejects_license_already_bound_to_other_group():
    fake_msg = {
        "message_id": 9994,
        "from": {"id": 8888, "is_bot": False, "first_name": "Other Admin"},
        "chat": {"id": -100998877, "type": "supergroup", "title": "Hijacker Group"},
        "text": "/activate bounduuid1234",
    }

    with patch("api.telegram_b2b._call_telegram_api") as mock_api:
        with patch("api.telegram_b2b.supabase") as mock_sb:
            mock_select = MagicMock()
            mock_select.execute.return_value.data = [
                {
                    "id": "bounduuid1234_full",
                    "order_id": "ORD-991",
                    "tier": "b2b_pro",
                    "daily_limit": 120,
                    "telegram_chat_id": -100555666,
                }
            ]
            mock_sb.table.return_value.select.return_value.in_.return_value = mock_select

            handled = handle_b2b_group_message(
                bot_token="fake_token",
                chat_id=-100998877,
                text="/activate bounduuid1234",
                msg=fake_msg,
            )

            assert handled is True
            mock_sb.table.return_value.update.assert_not_called()
            payload = mock_api.call_args[0][2]
            assert "مربوطة بالفعل بمجموعة تليجرام أخرى" in payload["text"]


def test_activate_blocks_repeat_free_trial_for_same_group():
    fake_msg = {
        "message_id": 9995,
        "from": {"id": 8888, "is_bot": False, "first_name": "Trial Farmer"},
        "chat": {"id": -100998877, "type": "supergroup", "title": "VIP Group"},
        "text": "/activate newtrial8888",
    }

    with patch("api.telegram_b2b._call_telegram_api") as mock_api:
        with patch("api.telegram_b2b.supabase") as mock_sb:
            lic_table = MagicMock()
            lic_table.select.return_value.in_.return_value.execute.return_value.data = [
                {
                    "id": "newtrial8888_uuid",
                    "order_id": "B2B-TRIAL-NEW2",
                    "owner_user_id": "user-2",
                    "tier": "b2b_pro",
                    "daily_limit": 30,
                }
            ]
            hist_table = MagicMock()
            hist_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
                {"telegram_chat_id": -100998877, "first_license_id": "old-trial-1111"}
            ]
            mock_sb.table.side_effect = lambda name: hist_table if name == "b2b_trial_chat_history" else lic_table

            handled = handle_b2b_group_message(
                bot_token="fake_token",
                chat_id=-100998877,
                text="/activate newtrial8888",
                msg=fake_msg,
            )

            assert handled is True
            lic_table.update.assert_not_called()
            payload = mock_api.call_args[0][2]
            assert "استهلكت التجربة المجانية مسبقاً" in payload["text"]


def test_bare_mention_help_does_not_consume_quota():
    fake_msg = {
        "message_id": 9996,
        "from": {"id": 5555, "is_bot": False, "first_name": "Ahmed"},
        "chat": {"id": -1001234567, "type": "supergroup"},
        "text": "@egxbots_bot",
    }

    with patch("api.telegram_b2b._call_telegram_api") as mock_api:
        with patch("api.telegram_b2b.supabase") as mock_sb:
            lic_q = MagicMock()
            lic_q.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
                {
                    "id": "lic-1",
                    "daily_used": 5,
                    "daily_limit": 50,
                    "custom_signature": "توقيع تجريبي",
                    "status": "active",
                }
            ]
            mock_sb.table.return_value = lic_q

            handled = handle_b2b_group_message(
                bot_token="fake_token",
                chat_id=-1001234567,
                text="@egxbots_bot",
                msg=fake_msg,
            )

            assert handled is True
            mock_sb.rpc.assert_not_called()
            payload = mock_api.call_args[0][2]
            assert "رسالة المساعدة لا تستهلك الرصيد" in payload["text"]


def test_activate_subscription_routes_b2b_to_rpc():
    with patch("api.payment_common._init_supabase"), patch("api.payment_common.supabase") as mock_sb:
        activate_subscription(
            user_id="00000000-0000-0000-0000-000000000001",
            plan_id="b2b_enterprise",
            provider="direct_wallet",
            payment_order_id="00000000-0000-0000-0000-000000000099",
        )
        mock_sb.rpc.assert_called_once_with(
            "activate_b2b_group_license",
            {
                "p_user_id": "00000000-0000-0000-0000-000000000001",
                "p_tier": "b2b_enterprise",
                "p_duration_days": 30,
                "p_payment_order_id": "00000000-0000-0000-0000-000000000099",
            },
        )


def test_semaphore_timeout_skips_llm():
    with patch("api.telegram_b2b._B2B_SEMAPHORE") as mock_sem, patch("api.telegram_b2b._call_telegram_api") as mock_api:
        mock_sem.acquire.return_value = False
        with patch("api.telegram_vip_chat.call_web_vip_chat_api") as mock_ai:
            _process_and_send_b2b_reply(
                bot_token="fake_token",
                chat_id=-1001234567,
                thread_id=None,
                reply_to_msg_id=10,
                user_id=5555,
                user_name="Ahmed",
                query_text="حلل فوري",
                custom_signature="توقيع",
                daily_used=1,
                daily_limit=50,
            )
            mock_ai.assert_not_called()
            mock_sem.release.assert_not_called()
            payload = mock_api.call_args[0][2]
            assert "مزدحم حالياً" in payload["text"]


def test_vip_chat_does_not_hijack_external_group_ask():
    external_update = {
        "update_id": 5001,
        "message": {
            "message_id": 77,
            "from": {"id": 5555, "is_bot": False, "first_name": "Member"},
            "chat": {"id": -100888999, "type": "supergroup", "title": "External Group"},
            "text": "/ask حلل سهم فوري",
        },
    }
    assert is_vip_chat_update(external_update) is False

    bridge = TelegramBot("fake_token")
    with patch("api.telegram_vip_chat.handle_vip_chat_update") as mock_vip, patch(
        "api.telegram_b2b.handle_b2b_group_message", return_value=True
    ) as mock_b2b:
        asyncio.run(bridge.handle_webhook_update(external_update))
        mock_vip.assert_not_called()
        mock_b2b.assert_called_once()


def test_command_addressed_to_other_bot_is_ignored():
    triggered, _ = is_explicit_group_trigger("/help@MissRose_bot", {})
    assert triggered is False
    triggered, _ = is_explicit_group_trigger("/start@GroupHelpBot activate_12345678", {})
    assert triggered is False
    triggered, clean = is_explicit_group_trigger("/start@egxbots_bot activate_12345678", {})
    assert triggered is True
    assert clean == "activate_12345678"


def test_anonymous_admin_and_topic_thread_activate_cleanly():
    anon_msg = {
        "message_id": 9997,
        "message_thread_id": 42,
        "from": {"id": 1087968824, "is_bot": True, "username": "GroupAnonymousBot"},
        "sender_chat": {"id": -100777888, "type": "supergroup", "title": "VIP Topic Group"},
        "chat": {"id": -100777888, "type": "supergroup", "title": "VIP Topic Group"},
        "text": "/start@egxbots_bot activate_anon12345",
    }
    with patch("api.telegram_b2b._is_pytest", return_value=False):
        assert _is_group_admin("fake_token", -100777888, 1087968824, msg=anon_msg) is True

    with patch("api.telegram_b2b._call_telegram_api") as mock_api, patch("api.telegram_b2b.supabase") as mock_sb:
        mock_select = MagicMock()
        mock_select.execute.return_value.data = [
            {
                "id": "anon12345_uuid",
                "order_id": "ORD-ANON-1",
                "tier": "b2b_enterprise",
                "daily_limit": 250,
                "custom_signature": "توقيع النخبة",
            }
        ]
        mock_sb.table.return_value.select.return_value.in_.return_value = mock_select
        handled = handle_b2b_group_message(
            bot_token="fake_token",
            chat_id=-100777888,
            text="/start@egxbots_bot activate_anon12345",
            msg=anon_msg,
        )
        assert handled is True
        payload = mock_api.call_args[0][2]
        assert payload["message_thread_id"] == 42
        assert "تم تفعيل وربط رخصة البوت بنجاح" in payload["text"]


def test_supergroup_migration_updates_b2b_chat_id():
    bridge = TelegramBot("fake_token")
    migration_update = {
        "update_id": 5002,
        "message": {
            "message_id": 88,
            "chat": {"id": -45123456, "type": "group", "title": "Old Group"},
            "migrate_to_chat_id": -100234567890,
        },
    }
    with patch("api.telegram_b2b.supabase") as mock_sb:
        asyncio.run(bridge.handle_webhook_update(migration_update))
        assert mock_sb.table.return_value.update.call_count >= 2


def test_private_dm_start_activate_shows_group_button():
    bridge = TelegramBot("fake_token")
    dm_msg = {
        "message_id": 100,
        "chat": {"id": 999111222, "type": "private"},
        "from": {"id": 999111222, "is_bot": False, "first_name": "Owner"},
        "text": "/start activate_abcd1234",
    }
    with patch("api.telegram_vip_chat.send_vip_message") as mock_send:
        bridge._dispatch_command(999111222, "/start activate_abcd1234", dm_msg)
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        assert "startgroup=activate_abcd1234" in str(kwargs["reply_markup"])


def test_photo_caption_trigger_in_group_routes_to_b2b():
    bridge = TelegramBot("fake_token")
    photo_update = {
        "update_id": 5003,
        "message": {
            "message_id": 99,
            "from": {"id": 5555, "is_bot": False, "first_name": "ChartUser"},
            "chat": {"id": -100888999, "type": "supergroup", "title": "Chart VIP"},
            "caption": "@egxbots_bot حلل الشارت ده",
        },
    }
    with patch("api.telegram_b2b.handle_b2b_group_message", return_value=True) as mock_b2b:
        asyncio.run(bridge.handle_webhook_update(photo_update))
        mock_b2b.assert_called_once()
        assert mock_b2b.call_args[0][2] == "@egxbots_bot حلل الشارت ده"


def test_my_chat_member_sends_onboarding_when_bot_added_manually():
    bridge = TelegramBot("fake_token")
    added_update = {
        "update_id": 5004,
        "my_chat_member": {
            "chat": {"id": -100333444, "type": "supergroup", "title": "New Company Group"},
            "old_chat_member": {"status": "left"},
            "new_chat_member": {"status": "administrator"},
        },
    }
    with patch("api.telegram_b2b._call_telegram_api") as mock_api, patch("api.telegram_b2b.supabase") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        asyncio.run(bridge.handle_webhook_update(added_update))
        mock_api.assert_called_once()
        payload = mock_api.call_args[0][2]
        assert "/activate" in payload["text"]
        assert payload["chat_id"] == -100333444


def test_b2b_recs_admin_toggle_command_updates_license():
    admin_msg = {
        "message_id": 6001,
        "from": {"id": 8888, "is_bot": False, "first_name": "GroupAdmin"},
        "chat": {"id": -100555666, "type": "supergroup", "title": "Company VIP"},
        "text": "/b2b_recs off",
    }
    with patch("api.telegram_b2b._call_telegram_api") as mock_api, patch(
        "api.telegram_b2b._is_group_admin", return_value=True
    ), patch("api.telegram_b2b.supabase") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = [
            {"id": "lic-123", "allow_recommendations": True, "status": "active", "expires_at": "2099-01-01T00:00:00+00:00"}
        ]
        handled = handle_b2b_group_message("fake_token", -100555666, "/b2b_recs off", admin_msg)
        assert handled is True
        mock_sb.table.return_value.update.assert_called_once_with({"allow_recommendations": False})
        sent = mock_api.call_args[0][2]["text"]
        assert "تم قفل توصيات" in sent

    # Non-admin must be rejected cleanly
    member_msg = {
        "message_id": 6002,
        "from": {"id": 7777, "is_bot": False, "first_name": "RegularMember"},
        "chat": {"id": -100555666, "type": "supergroup", "title": "Company VIP"},
        "text": "/recs_on",
    }
    with patch("api.telegram_b2b._call_telegram_api") as mock_api, patch(
        "api.telegram_b2b._is_group_admin", return_value=False
    ), patch("api.telegram_b2b.supabase"):
        handled = handle_b2b_group_message("fake_token", -100555666, "/recs_on", member_msg)
        assert handled is True
        assert "لمشرفي المجموعة" in mock_api.call_args[0][2]["text"]


def test_b2b_group_redirects_personal_portfolio_to_private_bot():
    msg = {
        "message_id": 6003,
        "from": {"id": 5555, "is_bot": False, "first_name": "Sara"},
        "chat": {"id": -100777888, "type": "supergroup", "title": "Broker VIP"},
        "text": "@egxbots_bot حلل محفظتي",
    }
    with patch("api.telegram_b2b._call_telegram_api") as mock_api, patch("api.telegram_b2b.supabase") as mock_sb, patch(
        "api.telegram_b2b._B2B_EXECUTOR"
    ) as mock_exec:
        mock_sb.rpc.return_value.execute.return_value.data = {
            "allowed": True,
            "tier": "b2b_pro",
            "daily_used": 2,
            "daily_limit": 120,
            "custom_signature": "شركة النخبة لتداول الأوراق المالية",
            "allow_recommendations": False,
        }
        handled = handle_b2b_group_message("fake_token", -100777888, "@egxbots_bot حلل محفظتي", msg)
        assert handled is True
        # Must NOT spin up AI executor — zero DeepSeek tokens used
        mock_exec.submit.assert_not_called()
        payload = mock_api.call_args[0][2]
        assert "بدون الحاجة لإنشاء حساب" in payload["text"]
        assert "start=b2b_portfolio" in str(payload["reply_markup"])
        assert "شركة النخبة" in payload["text"]


def test_b2b_process_reply_forwards_allow_recommendations_flag():
    with patch("api.telegram_vip_chat.call_web_vip_chat_api", return_value={"ok": True, "reply": "تحليل فوري"}) as mock_chat, patch(
        "api.telegram_b2b._call_telegram_api"
    ) as mock_tg:
        _process_and_send_b2b_reply(
            bot_token="fake_token",
            chat_id=-100111222,
            thread_id=None,
            reply_to_msg_id=10,
            user_id=5555,
            user_name="Ali",
            query_text="حلل فوري",
            custom_signature="Partner Sign",
            daily_used=1,
            daily_limit=120,
            allow_recommendations=False,
        )
        call_payload = mock_chat.call_args[0][0]
        assert call_payload["chat_source"] == "telegram_b2b"
        assert call_payload["allow_recommendations"] is False
        assert "Partner Sign" in mock_tg.call_args[0][2]["text"]


def test_native_vip_chat_blocks_b2b_recommendations_when_disabled():
    from api.native_telegram_vip_chat import handle_native_vip_chat

    with patch("api.agentic_chat.analysis_cache.get_vip_analysis_cache") as mock_cache, patch(
        "api.agentic_chat.pipeline.run_agentic_chat_stream"
    ) as mock_stream, patch("api.stock_ai._init_supabase"), patch("api.stock_ai.supabase"):
        res = handle_native_vip_chat(
            {
                "action": "chat",
                "telegram_user_id": 5555,
                "telegram_username": "Member",
                "telegram_chat_id": -100999111,
                "chat_source": "telegram_b2b",
                "bypass_quota": True,
                "allow_recommendations": False,
                "message": "هات كل التوصيات المفتوحة اليوم",
            }
        )
        assert res["ok"] is True
        assert "تم إيقاف عرض توصيات الشراء والبيع" in res["reply"]
        mock_cache.assert_not_called()
        mock_stream.assert_not_called()


def test_private_start_b2b_portfolio_and_unlinked_button():
    from api.telegram_vip_chat import handle_vip_chat_update

    start_update = {
        "update_id": 7001,
        "message": {
            "message_id": 201,
            "chat": {"id": 999888777, "type": "private"},
            "from": {"id": 999888777, "is_bot": False, "first_name": "Guest"},
            "text": "/start b2b_portfolio",
        },
    }
    with patch("api.telegram_vip_chat.send_vip_message") as mock_send:
        assert handle_vip_chat_update(start_update, "fake_token") is True
        sent_txt = mock_send.call_args.kwargs["text"]
        assert "بدون تسجيل دخول للموقع" in sent_txt
        assert "احفظ في محفظتي" in sent_txt

    # Unlinked user clicking vip_tool_portfolio in private chat must NOT be blocked by account_link
    cb_update = {
        "update_id": 7002,
        "callback_query": {
            "id": "cb_pf_private",
            "from": {"id": 999888777, "is_bot": False, "first_name": "Guest"},
            "data": "vip_tool_portfolio",
            "message": {
                "message_id": 202,
                "chat": {"id": 999888777, "type": "private"},
            },
        },
    }
    with patch("api.telegram_vip_chat._get_cached_user_quota", return_value=None), patch(
        "api.telegram_vip_chat.call_web_vip_chat_api",
        return_value={"ok": True, "is_pro": False, "linked": False, "remaining": 9, "used": 1, "limit": 10},
    ), patch("api.telegram_vip_chat._show_limit_or_upgrade_dialog") as mock_dialog, patch(
        "api.telegram_vip_chat.threading.Thread"
    ) as mock_thread:
        assert handle_vip_chat_update(cb_update, "fake_token") is True
        mock_dialog.assert_not_called()
        mock_thread.return_value.start.assert_called_once()


def test_unlinked_telegram_portfolio_json_roundtrip():
    from api.agentic_chat.tools_execution import _sync_manage_portfolio

    stored = {"cash_balance": 0.0, "positions": []}

    class _FakeTable:
        def __init__(self, tbl_name):
            self.tbl_name = tbl_name
            self._payload = None

        def select(self, *_):
            return self

        def eq(self, *_):
            return self

        def limit(self, *_):
            return self

        def in_(self, *_):
            return self

        def order(self, *_args, **_kw):
            return self

        def upsert(self, payload, **_):
            self._payload = payload
            if self.tbl_name == "telegram_vip_chat_state" and "portfolio_state" in payload:
                stored.clear()
                stored.update(payload["portfolio_state"])
            return self

        def execute(self):
            res = MagicMock()
            if self.tbl_name == "telegram_vip_chat_state":
                res.data = [{"portfolio_state": stored}]
            elif self.tbl_name == "stock_technical_indicators":
                res.data = [{"symbol": "FWRY", "close": 8.0, "change_pct": 2.5, "date": "2026-11-15"}]
            elif self.tbl_name == "stocks":
                res.data = [{"name_ar": "فوري لتكنولوجيا البنوك", "name": "Fawry"}]
            else:
                res.data = []
            return res

    fake_sb = MagicMock()
    fake_sb.from_.side_effect = lambda tbl: _FakeTable(tbl)

    with patch("api.agentic_chat.tools_execution._get_sb", return_value=fake_sb), patch(
        "api.agentic_chat.tools_execution._get_sb_for_market", return_value=fake_sb
    ):
        add_res = _sync_manage_portfolio(
            user_id="synthetic-uuid-not-in-auth",
            operation="add",
            symbol="FWRY",
            quantity=1000,
            price=7.5,
            user_prompt="احفظ في محفظتي 1000 سهم فوري بسعر 7.5",
            telegram_user_id=999888777,
        )
        assert add_res["status"] == "success"
        assert add_res["storage_mode"] == "telegram_private_only"

        cash_res = _sync_manage_portfolio(
            user_id="synthetic-uuid-not-in-auth",
            operation="set_cash",
            cash_amount=20000,
            user_prompt="حدث الكاش 20000",
            telegram_user_id=999888777,
        )
        assert cash_res["status"] == "success"
        assert cash_res["cash_balance"] == 20000.0

        view_res = _sync_manage_portfolio(
            user_id="synthetic-uuid-not-in-auth",
            operation="view",
            telegram_user_id=999888777,
        )
        assert view_res["status"] == "success"
        assert view_res["positions_count"] == 1
        assert view_res["positions"][0]["symbol"] == "FWRY"
        assert view_res["totals"]["market_value"] == 8000.0
        assert view_res["totals"]["profit_value"] == 500.0
        assert view_res["totals"]["equity"] == 28000.0

        sell_res = _sync_manage_portfolio(
            user_id="synthetic-uuid-not-in-auth",
            operation="sell",
            symbol="FWRY",
            quantity=400,
            price=8.0,
            user_prompt="بعت 400 سهم فوري بسعر 8",
            telegram_user_id=999888777,
        )
        assert sell_res["status"] == "success"
        assert stored["positions"][0]["quantity"] == 600.0
        assert stored["cash_balance"] == 23200.0


def test_private_b2b_portfolio_deeplink_routes_to_vip_onboarding(monkeypatch):
    from api.telegram_vip_chat import is_vip_chat_update, handle_vip_chat_update

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-token-test")
    upd = {
        "update_id": 1001,
        "message": {
            "message_id": 10,
            "chat": {"id": 445566, "type": "private"},
            "from": {"id": 445566, "first_name": "سارة"},
            "text": "/start b2b_portfolio",
        },
    }
    assert is_vip_chat_update(upd) is True
    assert is_vip_chat_update({
        "update_id": 1002,
        "message": {
            "message_id": 11,
            "chat": {"id": 445566, "type": "private"},
            "from": {"id": 445566, "first_name": "سارة"},
            "text": "/start 123e4567-e89b-12d3-a456-426614174000",
        },
    }) is False

    sent = []
    with patch("api.telegram_vip_chat.send_vip_message", side_effect=lambda **kw: sent.append(kw) or True):
        handled = handle_vip_chat_update(upd, bot_token="bot-token-test")
        assert handled is True
        assert sent and "مساعد المحفظة الذكي في الخاص" in sent[0]["text"]


def test_vip_tool_portfolio_callback_in_group_answers_without_name_error():
    from api.telegram_vip_chat import handle_vip_chat_update

    answers = []
    sent = []
    upd = {
        "update_id": 1003,
        "callback_query": {
            "id": "cb-group-pf",
            "from": {"id": 889900, "first_name": "عمر"},
            "message": {"message_id": 55, "chat": {"id": -1002083067817, "type": "supergroup"}, "message_thread_id": 1680},
            "data": "vip_tool_portfolio",
        },
    }
    with patch("api.telegram_vip_chat.get_vip_group_id", return_value="-1002083067817"), patch(
        "api.telegram_vip_chat.get_vip_topic_id", return_value=1680
    ), patch("api.telegram_vip_chat.answer_vip_callback", side_effect=lambda *a, **kw: answers.append((a, kw))), patch(
        "api.telegram_vip_chat.send_vip_message", side_effect=lambda **kw: sent.append(kw) or True
    ), patch("api.telegram_vip_chat._get_cached_user_quota", return_value=None), patch(
        "api.telegram_vip_chat.call_web_vip_chat_api",
        return_value={"ok": True, "linked": True, "is_pro": True, "used": 1, "limit": 999, "remaining": 998},
    ):
        handled = handle_vip_chat_update(upd, bot_token="bot-token-test")
        assert handled is True
        assert len(answers) == 1
        assert "b2b_portfolio" in sent[0]["reply_markup"]["inline_keyboard"][0][0]["url"]


def test_b2b_analysis_cache_isolation_and_weekly_recs_blocking():
    from api.agentic_chat.analysis_cache import (
        _memory_cache,
        _memory_lock,
        get_vip_analysis_cache,
        set_vip_analysis_cache,
    )

    with _memory_lock:
        _memory_cache.clear()

    set_vip_analysis_cache("vip_stock_COMI", "تحليل عام يشمل t.me/egxbots وتوصية شراء مفتوحة على COMI بسعر مستهدف 100")
    set_vip_analysis_cache("vip_recs_this_week", "توصيات هذا الأسبوع على السوق المصري وتشمل سهم COMI وسهم FWRY وETEL")

    # Locked B2B must not read Web/VIP vip_stock_COMI or any vip_recs_* keys
    assert get_vip_analysis_cache("vip_stock_COMI", is_b2b=True, allow_recommendations=False) is None
    assert get_vip_analysis_cache("vip_recs_this_week", is_b2b=True, allow_recommendations=False) is None
    assert get_vip_analysis_cache("vip_recs_last_week", is_b2b=True, allow_recommendations=False) is None

    # B2B write goes only to its scoped key and never overwrites public vip_stock_COMI
    set_vip_analysis_cache(
        "vip_stock_COMI",
        "تحليل فني صرف لسهم COMI داخل جروب الشركة بدون روابط أو توصيات مفتوحة",
        is_b2b=True,
        allow_recommendations=False,
    )
    b2b_hit = get_vip_analysis_cache("vip_stock_COMI", is_b2b=True, allow_recommendations=False)
    vip_hit = get_vip_analysis_cache("vip_stock_COMI", is_b2b=False, allow_recommendations=True)
    assert b2b_hit is not None and "t.me/egxbots" not in b2b_hit["reply"]
    assert vip_hit is not None and "t.me/egxbots" in vip_hit["reply"]


def test_stock_levels_omits_active_recs_and_group_blocks_portfolio():
    from api.agentic_chat.tools_execution import (
        _sync_get_stock_levels_for_market,
        _sync_manage_portfolio,
        reset_allow_recommendations_context,
        reset_group_portfolio_blocked_context,
        set_allow_recommendations_context,
        set_group_portfolio_blocked_context,
    )

    class _FakeExec:
        def __init__(self, data):
            self.data = data

    class _FakeTable:
        def __init__(self, name):
            self.name = name

        def select(self, *args, **kwargs):
            return self

        def eq(self, *args, **kwargs):
            return self

        def in_(self, *args, **kwargs):
            return self

        def order(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def execute(self):
            if self.name == "stock_prices":
                return _FakeExec([{"high": 10.5, "low": 9.8, "close": 10.2, "date": "2026-11-15"}])
            if self.name == "scan_results":
                raise AssertionError("scan_results must NOT be queried when allow_recommendations=False")
            return _FakeExec([])

    class _FakeSB:
        def from_(self, name):
            return _FakeTable(name)

    tok_rec = set_allow_recommendations_context(False)
    tok_grp = set_group_portfolio_blocked_context(True)
    try:
        lvls = _sync_get_stock_levels_for_market(_FakeSB(), ["FWRY"], "EGX")
        assert lvls[0]["has_active_recommendation"] is False
        assert lvls[0]["active_recommendation"] is None

        pf = _sync_manage_portfolio(
            user_id=None,
            operation="add",
            symbol="FWRY",
            quantity=500,
            user_prompt="اشتريت 500 سهم فوري",
        )
        assert pf["status"] == "redirect_private"
        assert "b2b_portfolio" in pf["private_bot_url"]
    finally:
        reset_group_portfolio_blocked_context(tok_grp)
        reset_allow_recommendations_context(tok_rec)
