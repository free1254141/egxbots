import pytest
from unittest.mock import MagicMock, patch

from jobs.founders_campaign import (
    build_founders_announcement_text,
    get_founders_inline_keyboard,
    send_telegram_campaign_message,
    get_active_target_users,
    run_campaign,
)


def test_build_founders_announcement_text():
    text_named = build_founders_announcement_text("أحمد")
    assert "أحمد" in text_named
    assert "50 ج.م" in text_named
    assert "عرض الـ 100 مؤسس الأوائل" in text_named
    assert "توصيات صفقات السوينج السريع" in text_named

    text_default = build_founders_announcement_text(None)
    assert "صديقنا المستثمر" in text_default
    assert "50 ج.م" in text_default


def test_get_founders_inline_keyboard():
    markup = get_founders_inline_keyboard()
    assert "inline_keyboard" in markup
    buttons = markup["inline_keyboard"]
    assert len(buttons) == 2
    assert "plan=pro" in buttons[0][0]["url"]
    assert "50 ج.م" in buttons[0][0]["text"]
    assert "التجربة المجانية" in buttons[1][0]["text"]


@patch("requests.post")
def test_send_telegram_campaign_message(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True}
    mock_post.return_value = mock_resp

    success = send_telegram_campaign_message(
        chat_id=123456,
        text="Hello world",
        reply_markup=get_founders_inline_keyboard(),
        token="test_token",
    )
    assert success is True
    assert mock_post.called
    payload = mock_post.call_args[1]["json"]
    assert payload["chat_id"] == 123456
    assert payload["text"] == "Hello world"
    assert "inline_keyboard" in payload["reply_markup"]


@patch("jobs.founders_campaign.supabase")
def test_get_active_target_users_filters_active_and_cooldown(mock_supabase):
    # Mock active subscriptions: user1 is active Pro
    mock_subs = MagicMock()
    mock_subs.execute.return_value.data = [{"user_id": "u1"}]

    # Mock profiles: u1 (active Pro), u2 (free eligible), u3 (recent cooldown)
    mock_profiles = MagicMock()
    mock_profiles.execute.return_value.data = [
        {"id": "u1", "display_name": "User 1", "telegram_chat_id": 111, "updated_at": "2026-10-25T10:00:00Z"},
        {"id": "u2", "display_name": "User 2", "telegram_chat_id": 222, "updated_at": "2026-10-25T11:00:00Z"},
        {"id": "u3", "display_name": "User 3", "telegram_chat_id": 333, "updated_at": "2026-10-25T12:00:00Z"},
    ]

    # Mock marketing_message_log: u3 received it recently
    mock_log = MagicMock()
    def mock_table(table_name):
        mock_builder = MagicMock()
        if table_name == "subscriptions":
            mock_builder.select.return_value.eq.return_value = mock_subs
        elif table_name == "profiles":
            mock_builder.select.return_value.not_.is_.return_value.order.return_value.limit.return_value = mock_profiles
        elif table_name == "marketing_message_log":
            # Return log for u3 only
            def select_handler(*args, **kwargs):
                sub_b = MagicMock()
                def eq_handler(field, val):
                    eq_b = MagicMock()
                    if field == "user_id" and val == "u3":
                        eq_b.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = [{"id": 1}]
                    else:
                        eq_b.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []
                    return eq_b
                sub_b.eq = eq_handler
                return sub_b
            mock_builder.select = select_handler
        return mock_builder

    mock_supabase.table.side_effect = mock_table

    targets = get_active_target_users(cooldown_days=7)
    # Only u2 should be eligible (u1 is active Pro, u3 is in cooldown)
    assert len(targets) == 1
    assert targets[0]["user_id"] == "u2"
    assert targets[0]["telegram_chat_id"] == 222
