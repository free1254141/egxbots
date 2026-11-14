"""
Test photo and screenshot handling for Telegram VIP / Artoro bot.
Verifies that photos are detected, downloaded, routed to Vision AI and stored.
"""
from unittest.mock import MagicMock, patch
import pytest

from api.telegram_vip_chat import handle_vip_chat_update, is_vip_chat_update


def test_is_vip_chat_update_allows_photo_message():
    """Verify that is_vip_chat_update accepts photo messages in private chat."""
    update = {
        "update_id": 12345,
        "message": {
            "message_id": 1,
            "chat": {"id": 8914747813, "type": "private"},
            "from": {"id": 8914747813, "is_bot": False, "first_name": "Hazem"},
            "photo": [
                {"file_id": "thumb_123", "width": 100, "height": 100},
                {"file_id": "highres_456", "width": 800, "height": 800},
            ],
            "caption": "حلل محفظتي",
        }
    }
    assert is_vip_chat_update(update) is True


def test_is_vip_chat_update_allows_photo_without_caption():
    """Verify that photo without caption in private chat is also accepted."""
    update = {
        "update_id": 12346,
        "message": {
            "message_id": 2,
            "chat": {"id": 8914747813, "type": "private"},
            "from": {"id": 8914747813, "is_bot": False, "first_name": "Hazem"},
            "photo": [
                {"file_id": "highres_456", "width": 800, "height": 800},
            ],
        }
    }
    assert is_vip_chat_update(update) is True


@patch("api.telegram_vip_chat._execute_and_reply_vip_chat")
def test_handle_vip_chat_update_routes_photo_to_worker(mock_worker):
    """Verify handle_vip_chat_update extracts the highest resolution photo and passes file_id."""
    update = {
        "update_id": 12347,
        "message": {
            "message_id": 3,
            "chat": {"id": 8914747813, "type": "private"},
            "from": {"id": 8914747813, "is_bot": False, "first_name": "Hazem"},
            "photo": [
                {"file_id": "low_123", "width": 100, "height": 100},
                {"file_id": "high_999", "width": 1080, "height": 1920},
            ],
        }
    }

    handled = handle_vip_chat_update(update, "fake_token")
    assert handled is True
    assert mock_worker.called
    call_kwargs = mock_worker.call_args[1]
    assert call_kwargs["file_id"] == "high_999"
    assert call_kwargs["query_text"] == ""
