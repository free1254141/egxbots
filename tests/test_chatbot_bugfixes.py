"""
Regression tests covering the 2026-11-14 chatbot audit fixes.
"""

import datetime as dt
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from api.agentic_chat.analysis_cache import resolve_cache_validity
from api.agentic_chat.tools_execution import (
    _TOOL_CACHE,
    _safe_price,
    _sync_get_stock,
    _sync_get_stock_levels,
    _sync_manage_portfolio,
)
from api.stock_aliases import extract_all_stock_symbols, resolve_stock_symbol
from api.telegram_vip_chat import detect_topic_query_intent, handle_vip_chat_update


CAIRO = ZoneInfo("Africa/Cairo")


def test_weekend_cache_validity_blocks_monday_stale_entries():
    # Saturday 2026-11-14 08:00 Cairo -> last completed EGX session was Thursday 2026-11-12 17:15
    sat_morning = dt.datetime(2026, 11, 14, 8, 0, tzinfo=CAIRO).timestamp()

    # Monday 2026-11-09 21:06 Cairo (HDBK stale cache bug) must be rejected
    mon_evening = dt.datetime(2026, 11, 9, 21, 6, tzinfo=CAIRO).timestamp()
    assert resolve_cache_validity(mon_evening, sat_morning) is False

    # Thursday 2026-11-12 14:00 Cairo (before close ready 17:15) must be rejected on weekend
    thu_intraday = dt.datetime(2026, 11, 12, 14, 0, tzinfo=CAIRO).timestamp()
    assert resolve_cache_validity(thu_intraday, sat_morning) is False

    # Thursday 2026-11-12 17:30 Cairo (after close ready 17:15) is valid all weekend
    thu_evening = dt.datetime(2026, 11, 12, 17, 30, tzinfo=CAIRO).timestamp()
    assert resolve_cache_validity(thu_evening, sat_morning) is True


def test_arabic_aliases_normalization_and_scanner_exclusion():
    assert resolve_stock_symbol("تحليل بنك فيصل الإسلامي") == "FAIT"
    assert resolve_stock_symbol("بنك فيصل الاسلامى") == "FAIT"
    assert resolve_stock_symbol("العربية للتنمية والاستثمار العقاري") == "ADRI"
    assert resolve_stock_symbol("بريميم هيلث كير") == "PHGC"
    assert resolve_stock_symbol("/scanner@egxbots_bot") is None
    assert extract_all_stock_symbols("/scanner@egxbots_bot") == []
    assert extract_all_stock_symbols("قارن بين بنك فيصل الاسلامي وبريميم هيلث كير") == ["FAIT", "PHGC"]


def test_sub_2_egp_decimal_precision():
    assert _safe_price(0.082) == 0.082
    assert _safe_price(0.074165) == 0.0742
    assert _safe_price(0.085735) == 0.0857
    assert _safe_price(2.1489) == 2.149
    assert _safe_price(88.456) == 88.46


def test_batch_symbol_limit_exceeds_10_for_large_portfolios():
    _TOOL_CACHE.clear()
    symbols = [
        "ABUK", "ADRI", "AMOC", "ATQA", "BTFH",
        "COMI", "EFID", "EGAL", "EGCH", "EKHO",
        "ETRS", "FAIT", "FWRY", "HRHO", "TMGH",
    ]
    mock_sb = MagicMock()
    mock_sb.from_().select().eq().in_().order().limit().execute.return_value.data = []
    mock_sb.from_().select().eq().limit().execute.return_value.data = []
    mock_sb.from_().select().eq().eq().order().limit().execute.return_value.data = []
    mock_sb.from_().select().eq().order().limit().execute.return_value.data = []
    mock_sb.from_().select().eq().eq().limit().execute.return_value.data = []

    with patch("api.agentic_chat.tools_execution._get_sb", return_value=mock_sb):
        res_stock = _sync_get_stock(symbols)
        res_levels = _sync_get_stock_levels(symbols)

    assert len(res_stock["stocks"]) == 15
    assert len(res_levels["levels"]) == 15


def test_manage_portfolio_intent_and_required_qty_price():
    mock_sb = MagicMock()
    mock_sb.from_().select().eq().eq().eq().limit().execute.return_value.data = []

    with patch("api.agentic_chat.tools_execution._get_sb", return_value=mock_sb):
        # Casual question blocked
        res_blocked = _sync_manage_portfolio(
            operation="add",
            symbol="COMI",
            quantity=100,
            price=88.0,
            user_id="u1",
            user_prompt="سعر فوري كام النهاردة",
        )
        assert res_blocked["status"] == "blocked"

        # Egyptian dialect "ضيف" allowed through write guard, but missing price/qty rejected (no qty=100 fabrication!)
        res_clarify = _sync_manage_portfolio(
            operation="add",
            symbol="COMI",
            quantity=None,
            price=88.0,
            user_id="u1",
            user_prompt="ضيف السهم للمحفظة",
        )
        assert res_clarify["status"] == "needs_clarification"

        # Explicit qty + 4-decimal price inserts cleanly with 4 decimals preserved
        res_ok = _sync_manage_portfolio(
            operation="add",
            symbol="ELEC",
            quantity=500,
            price=1.62282,
            user_id="u1",
            user_prompt="ضيفهم للمحفظة يا بطل",
        )
        assert res_ok["status"] == "success"
        inserted_payload = mock_sb.from_().insert.call_args[0][0]
        assert inserted_payload["quantity"] == 500.0
        assert inserted_payload["entry_price"] == 1.6228


def test_scheduled_automations_queries_filter_latest_dates():
    from api.scheduled_automations_worker import _fetch_market_indicators_brief

    seen_endpoints = []

    def fake_sb(endpoint, method="GET", payload=None, timeout=10):
        seen_endpoints.append(endpoint)
        if "select=date" in endpoint:
            return [{"date": "2026-11-12"}]
        if "select=scan_date" in endpoint:
            return [{"scan_date": "2026-11-12"}]
        return []

    with patch("api.scheduled_automations_worker._supabase_request", side_effect=fake_sb), \
         patch("api.scheduled_automations_worker._extract_symbols_from_text", return_value=([], {})):
        _fetch_market_indicators_brief("اقوى اسهم التجميع وايكوف اليوم", "اقوى اسهم التجميع")

    assert any("date=eq.2026-11-12" in ep for ep in seen_endpoints)
    assert any("scan_date=eq.2026-11-12" in ep and "wyckoff_phase=neq.distribution" in ep for ep in seen_endpoints)


def test_telegram_scanner_command_cleanly_handled():
    # With extra query, strips /scanner@egxbots_bot prefix cleanly
    mode, text = detect_topic_query_intent("/scanner@egxbots_bot اقوى اسهم السوق")
    assert mode == "free"
    assert "/scanner" not in text

    # Bare /scanner@egxbots_bot shows panel immediately instead of calling AI as ticker
    update = {
        "message": {
            "message_id": 9001,
            "chat": {"id": -1002083067817, "type": "supergroup"},
            "message_thread_id": 1680,
            "from": {"id": 998877, "first_name": "Test"},
            "text": "/scanner@egxbots_bot",
        }
    }
    with patch("api.telegram_vip_chat.send_vip_message", return_value=123) as mock_send, \
         patch("api.telegram_vip_chat.call_web_vip_chat_api") as mock_ai:
        handled = handle_vip_chat_update(update, "dummy-token")
    assert handled is True
    mock_send.assert_called_once()
    mock_ai.assert_not_called()


def test_accumulation_and_technical_scan_filter_latest_dates():
    from api.agentic_chat.tools_execution import (
        _sync_get_accumulation_stocks,
        _sync_get_technical_scan,
    )

    _TOOL_CACHE.clear()
    mock_sb = MagicMock()

    # Latest scan_date probe returns 2026-11-12; distribution rows skipped even if acc_score >= 50
    mock_sb.from_().select().order().limit().execute.return_value.data = [{"scan_date": "2026-11-12"}]
    scan_rows = [
        {"symbol": "PRCL", "scan_date": "2026-11-12", "acc_score": 55, "dist_score": 60, "wyckoff_phase": "distribution"},
        {"symbol": "SUGR", "scan_date": "2026-11-12", "acc_score": 90, "dist_score": 10, "wyckoff_phase": "accumulation"},
    ]
    mock_sb.from_().select().gte().neq().eq().order().limit().execute.return_value.data = scan_rows
    mock_sb.from_().select().eq().in_().order().limit().execute.return_value.data = [
        {"symbol": "SUGR", "close": 52.0, "change_pct": 1.2, "rsi_14": 54.0, "bb_lower": 50.0, "bb_upper": 56.0, "date": "2026-11-12"}
    ]

    with patch("api.agentic_chat.tools_execution._get_sb", return_value=mock_sb):
        acc_res = _sync_get_accumulation_stocks()

    returned_syms = [s["symbol"] for s in acc_res["accumulation_stocks"]]
    assert returned_syms == ["SUGR"]

    # Also verify _sync_get_technical_scan filters by latest_date when present
    _TOOL_CACHE.clear()
    mock_sb2 = MagicMock()
    mock_sb2.from_().select().eq().order().limit().execute.return_value.data = [{"date": "2026-11-12"}]
    mock_sb2.from_().select().eq().eq().order().limit().execute.return_value.data = [
        {"symbol": "PHGC", "date": "2026-11-12", "close": 0.082, "change_pct": 2.5, "rsi_14": 51.0, "bb_lower": 0.074165, "bb_upper": 0.085735}
    ]
    with patch("api.agentic_chat.tools_execution._get_sb", return_value=mock_sb2):
        tech_res = _sync_get_technical_scan("top_gainers")
    assert tech_res["stocks"][0]["symbol"] == "PHGC"
    assert tech_res["stocks"][0]["support_1"] == 0.0742
    assert tech_res["stocks"][0]["resistance_1"] == 0.0857

