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


def test_structured_data_providers():
    from api.support_analytics import (
        get_registrations_data,
        get_activity_data,
        get_chat_history_data,
        get_platform_kpis_data,
        _get_cairo_bounds_for_date
    )
    s_iso, e_iso, d_str = _get_cairo_bounds_for_date("2026-10-15")
    assert d_str == "2026-10-15"
    assert s_iso is not None and "T" in s_iso
    assert e_iso is not None and "T" in e_iso

    reg_data = get_registrations_data("today")
    assert "date" in reg_data
    assert "new_registrations_count" in reg_data

    act_data = get_activity_data("today")
    assert "dau" in act_data
    assert "top_visited_pages" in act_data

    chat_data = get_chat_history_data("today", "all")
    assert "support_tickets" in chat_data
    assert "ai_chat" in chat_data

    kpi_data = get_platform_kpis_data()
    assert "total_registered_users" in kpi_data
    assert "pro_vip_subscribers" in kpi_data


def test_admin_ai_tool_dispatch():
    from api.admin_ai_assistant import execute_admin_tool
    import json

    res1 = execute_admin_tool("get_registrations_report", {"date": "today"})
    parsed1 = json.loads(res1)
    assert "date" in parsed1

    res2 = execute_admin_tool("get_platform_kpis", {})
    parsed2 = json.loads(res2)
    assert "total_registered_users" in parsed2

    res3 = execute_admin_tool("get_open_recommendations", {})
    parsed3 = json.loads(res3)
    assert "has_open_recommendations" in parsed3


@patch("api.admin_ai_assistant.ask_admin_ai")
@patch("api.support_chat.send_telegram_message")
def test_admin_ai_natural_language_routing(mock_send, mock_ask):
    mock_ask.return_value = "<b>تحليل ديب سيك:</b> تم تسجيل مستخدمين جدد اليوم."
    mock_send.return_value = True

    # When admin sends arbitrary question, routes to ask_admin_ai
    handle_telegram_update({"message": {"chat": {"id": 99999}, "text": "مين اللي سجل النهاردة وفتح صفحة الأسعار؟"}})
    assert mock_ask.call_count == 1
    assert mock_send.call_count == 1
    args, kwargs = mock_send.call_args
    assert "تحليل ديب سيك" in args[1]


@patch("requests.post")
def test_send_telegram_message_chunking(mock_post):
    from api.support_chat import send_telegram_message
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True}
    mock_post.return_value = mock_resp

    long_text = "A" * 8500
    res = send_telegram_message(99999, long_text)
    assert res is True
    # Should chunk into at least 3 parts (4000 + 4000 + 500)
    assert mock_post.call_count >= 3

