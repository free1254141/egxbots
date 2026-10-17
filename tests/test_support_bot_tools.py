import pytest
from unittest.mock import patch, MagicMock
from api.support_analytics import (
    get_registrations_summary,
    get_activity_summary,
    get_chat_summary,
    get_comprehensive_report,
    _get_cairo_day_bounds
)
from api.support_chat import handle_telegram_update

def test_cairo_day_bounds():
    today_iso, yesterday_iso, now_str, today_start, now_cairo = _get_cairo_day_bounds()
    assert today_iso is not None
    assert yesterday_iso is not None
    assert "T" in today_iso
    assert "T" in yesterday_iso
    assert now_str is not None

def test_analytics_reports_format():
    # Reports should return valid formatted HTML strings without exceptions
    reg_report = get_registrations_summary()
    assert isinstance(reg_report, str)
    assert "المسجلين اليوم" in reg_report
    assert "المسجلين أمس" in reg_report
    assert "إجمالي مستخدمي المنصة" in reg_report

    act_report = get_activity_summary()
    assert isinstance(act_report, str)
    assert "المستخدمين النشطين" in act_report
    assert "التفاعلات" in act_report

    chat_report = get_chat_summary()
    assert isinstance(chat_report, str)
    assert "دعم العملاء المباشر" in chat_report
    assert "شات الذكاء الاصطناعي" in chat_report

    comp_report = get_comprehensive_report()
    assert isinstance(comp_report, str)
    assert "التقرير التنفيذي الشامل" in comp_report
    assert "المسجلين الجدد" in comp_report

@patch("api.support_chat.send_telegram_message")
def test_handle_telegram_commands(mock_send):
    mock_send.return_value = True

    # 1. Test /start command
    handle_telegram_update({"message": {"chat": {"id": 99999}, "text": "/start"}})
    assert mock_send.call_count >= 2
    mock_send.reset_mock()

    # 2. Test /users command
    handle_telegram_update({"message": {"chat": {"id": 99999}, "text": "المسجلين"}})
    assert mock_send.call_count == 1
    args, kwargs = mock_send.call_args
    assert "المسجلين" in args[1]
    mock_send.reset_mock()

    # 3. Test /activity command
    handle_telegram_update({"message": {"chat": {"id": 99999}, "text": "النشاط"}})
    assert mock_send.call_count == 1
    args, kwargs = mock_send.call_args
    assert "النشاط" in args[1]
    mock_send.reset_mock()

    # 4. Test /chat command
    handle_telegram_update({"message": {"chat": {"id": 99999}, "text": "الشات"}})
    assert mock_send.call_count == 1
    args, kwargs = mock_send.call_args
    assert "الشات" in args[1]
    mock_send.reset_mock()

    # 5. Test /stats command
    handle_telegram_update({"message": {"chat": {"id": 99999}, "text": "/stats"}})
    assert mock_send.call_count == 1
    args, kwargs = mock_send.call_args
    assert "التقرير التنفيذي الشامل" in args[1]
    mock_send.reset_mock()

@patch("api.support_chat.answer_callback_query")
@patch("api.support_chat.edit_telegram_message")
def test_handle_callback_queries(mock_edit, mock_answer):
    mock_edit.return_value = True

    # Test callback for cmd_users
    data = {
        "callback_query": {
            "id": "cb_test_1",
            "data": "cmd_users",
            "message": {"chat": {"id": 99999}, "message_id": 123}
        }
    }
    handle_telegram_update(data)
    assert mock_answer.call_count == 1
    assert mock_edit.call_count == 1
    args, kwargs = mock_edit.call_args
    assert "المسجلين" in args[2]
