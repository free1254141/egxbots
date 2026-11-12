"""
tests/test_agentic_chat_optimization_and_cache.py
Verification suite for:
1. In-Memory Response Caching (analysis_cache.py).
2. Elimination of AGENTIC_TOOLS_SCHEMA in Round 2 synthesis.
3. Distributed atomic claim in scheduled_automations_worker.py.
"""

import json
import time
from unittest.mock import MagicMock, patch
import pytest

from api.agentic_chat.analysis_cache import (
    extract_canonical_cache_key,
    get_cached_analysis,
    set_cached_analysis,
    clear_analysis_cache,
    is_egx_live_session,
    get_cairo_now,
)
from api.scheduled_automations_worker import execute_single_automation


def test_analysis_cache_canonical_keys():
    clear_analysis_cache()
    # Canonical stock keys
    assert extract_canonical_cache_key("سعر فوري كام دلوقتي") == "vip_stock_FWRY"
    assert extract_canonical_cache_key("حلل سهم البنك التجاري الدولي COMI") == "vip_stock_COMI"
    assert extract_canonical_cache_key("عتاقة نظامه ايه") == "vip_stock_ATQA"
    assert extract_canonical_cache_key("طلعت مصطفى TMGH") == "vip_stock_TMGH"

    # Canonical market keys
    assert extract_canonical_cache_key("حالة السوق المصري النهاردة") == "vip_market_summary"
    assert extract_canonical_cache_key("وضع السوق") == "vip_market_summary"

    # Canonical Wyckoff & Recommendations
    assert extract_canonical_cache_key("ايه هي اقوى اسهم التجميع") == "vip_accumulation"
    assert extract_canonical_cache_key("التوصيات المفتوحة النهاردة") == "vip_open_recommendations"
    assert extract_canonical_cache_key("صفقات السوينغ") == "vip_open_recommendations"

    # Personal queries MUST return None (no cache)
    assert extract_canonical_cache_key("حلل اسهم محفظتي") is None
    assert extract_canonical_cache_key("انا اشتريت فوري على 8.20 ابيع ولا اعمل ايه") is None
    assert extract_canonical_cache_key("عدل الكمية في محفظتي") is None

    # Multimodal image queries MUST return None (no cache)
    assert extract_canonical_cache_key("حلل الصورة دي", images=["data:image/png;base64,..."]) is None


def test_model_driven_tool_call_to_cache_key():
    """Verify zero-regex model-driven tool call resolver matches canonical keys."""
    from api.agentic_chat.analysis_cache import resolve_tool_call_to_cache_key

    # 1. Single stock & levels
    assert resolve_tool_call_to_cache_key("get_stock", {"symbol": "FWRY"}) == "vip_stock_FWRY"
    assert resolve_tool_call_to_cache_key("get_stock_levels", {"symbols": ["COMI"]}) == "vip_stock_COMI"

    # 2. Recommendations
    assert resolve_tool_call_to_cache_key("get_recommendations", {}) == "vip_open_recommendations"
    assert resolve_tool_call_to_cache_key("get_recommendations", {"timeframe": "this_week"}) == "vip_recs_this_week"
    assert resolve_tool_call_to_cache_key("get_recommendations", {"timeframe": "last_week"}) == "vip_recs_last_week"

    # 3. Market overview & accumulation
    assert resolve_tool_call_to_cache_key("get_accumulation_stocks", {}) == "vip_accumulation"
    assert resolve_tool_call_to_cache_key("get_market", {"metric": "top_gainers"}) == "vip_top_stocks"
    assert resolve_tool_call_to_cache_key("get_market", {}) == "vip_market_summary"

    # 4. Comparison
    assert resolve_tool_call_to_cache_key("get_comparison", {"symbols": ["FWRY", "COMI"]}) == "vip_compare_COMI_FWRY"

    # 5. Non-cacheable tool calls
    assert resolve_tool_call_to_cache_key("manage_portfolio", {}) is None
    assert resolve_tool_call_to_cache_key("analyze_portfolio_risk", {}) is None


def test_analysis_cache_hit_and_miss_lifecycle():
    clear_analysis_cache()
    # Miss
    assert get_cached_analysis("سعر فوري كام دلوقتي") is None

    # Store (must be >= 600 chars for stock report)
    sample_reply = (
        "📊 **تحليل سهم فوري لتكنولوجيا البنوك والمدفوعات الإلكترونية (FWRY):**\n"
        "• السعر الحالي: 8.50 ج.م (+1.50%)\n"
        "• الدعم الفني الأول: 8.30 ج.م والمقاومة الأولى: 8.90 ج.م.\n"
        "• مؤشر RSI يستقر عند 54.2 في منطقة زخم إيجابي متوازن يدعم استمرار المسار الصاعد.\n"
        "• متوسط متحرك 50 يوم: 8.15 ج.م ومتوسط متحرك 200 يوم: 7.80 ج.م.\n"
        "• نموذج وايكوف يشير إلى مرحلة تجميع مؤسسي مدعومة بارتفاع أحجام التداول النسبي بمعدل 1.8x.\n"
        "• إدارة المخاطر: ينصح بوضع حد وقف خسارة أسفل مستوى 8.10 ج.م لحماية رأس المال.\n"
        "📌 **حالة السهم في محفظتك:** السهم غير مسجل ضمن مراكز محفظتك الاستثمارية المحفوظة.\n"
        "• تقييم السهم الفني: فرصة شراء مقترحة بناءً على المؤشرات الفنية والسيولة اللحظية."
    )
    sample_tables = [{"symbol": "FWRY", "close": 8.50, "rsi": 54.2}]
    set_cached_analysis("سعر فوري كام دلوقتي", sample_reply, sample_tables, [])

    # Hit
    hit = get_cached_analysis("سعر فوري كام دلوقتي")
    assert hit is not None
    assert hit["key"] == "vip_stock_FWRY"
    assert "FWRY" in hit["reply"]
    assert len(hit["tables"]) == 1
    assert hit["tables"][0]["close"] == 8.50


def test_portfolio_sanitization_and_personalization():
    """Verify that personal portfolio line is sanitized before cache and personalized on read."""
    from api.agentic_chat.analysis_cache import (
        sanitize_analysis_for_cache,
        personalize_cached_analysis,
        NEUTRAL_PORTFOLIO_LINE,
    )

    personal_reply = (
        "تقرير سهم COMI:\n"
        "السعر الأخير: 88.50 ج.م.\n"
        "📌 **حالة السهم في محفظتك:** مسجل لديك 1000 سهم بمتوسط شراء 85.00 ج.م.\n"
        "مركزك الحالي عند 85.00 يحقق أرباح ممتازة.\n"
        "المقاومة القادمة 92.00 ج.م."
    )

    # 1. Sanitize for shared cache
    sanitized = sanitize_analysis_for_cache(personal_reply)
    assert "1000 سهم" not in sanitized
    assert "مركزك الحالي" not in sanitized
    assert NEUTRAL_PORTFOLIO_LINE in sanitized

    # 2. Personalize without user position returns neutral line
    with patch("api.stock_ai.supabase.table") as mock_table:
        mock_table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        personalized = personalize_cached_analysis(sanitized, "user-123", "COMI")
        assert NEUTRAL_PORTFOLIO_LINE in personalized


def test_scheduled_automations_atomic_claim_prevents_duplicate():
    """Verify that execute_single_automation skips execution if claimed by another instance today."""
    automation_mock = {
        "id": "mock-auto-uuid-1234",
        "user_id": "mock-user-uuid-5678",
        "name": "متابعة أقوى الأسهم",
        "prompt": "أقوى الأسهم اليوم",
        "scheduled_time": "10:30",
    }

    # Simulate Supabase PATCH returning [] (indicating last_run_date was already today)
    with patch("api.scheduled_automations_worker._supabase_request") as mock_sb:
        mock_sb.return_value = []  # No rows updated because last_run_date is already today!

        res = execute_single_automation(automation_mock, is_test=False)
        assert res["ok"] is True
        assert res["reason"] == "already_claimed_today"

        # Verify that patch was called with idempotency filter
        mock_sb.assert_called_once()
        call_url = mock_sb.call_args[0][0]
        assert "scheduled_chat_automations?id=eq.mock-auto-uuid-1234" in call_url
        assert "last_run_date" in call_url


@pytest.mark.anyio
async def test_multi_round_tool_chaining_and_synthesis():
    """Verify that multi-round tool chaining works and final synthesis completes cleanly without DSML."""
    from api.agentic_chat.pipeline import run_agentic_chat_stream

    captured_post_payloads = []
    mock_client = MagicMock()

    # Turn 1: DeepSeek calls get_stock
    resp_turn1 = MagicMock()
    resp_turn1.status_code = 200
    resp_turn1.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "get_stock",
                                "arguments": '{"symbols": ["COMI"]}',
                            },
                        }
                    ],
                }
            }
        ]
    }

    # Turn 2: DeepSeek sees tool results and returns final technical analysis
    resp_turn2 = MagicMock()
    resp_turn2.status_code = 200
    resp_turn2.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "سهم التجاري الدولي COMI يتداول بإيجابية عند مستوى 88.5 ج.م مع دعم عند 86.0 ج.م.",
                    "tool_calls": None,
                }
            }
        ]
    }

    turn_counter = 0

    async def fake_post(url, headers=None, json=None, timeout=None):
        nonlocal turn_counter
        captured_post_payloads.append(json)
        turn_counter += 1
        if turn_counter == 1:
            return resp_turn1
        return resp_turn2

    mock_client.post = fake_post

    with patch("httpx.AsyncClient") as mock_http_cls, \
         patch("api.agentic_chat.pipeline.dispatch_tool") as mock_dispatch:
        mock_http_cls.return_value.__aenter__.return_value = mock_client
        mock_http_cls.return_value.__aexit__.return_value = None
        mock_dispatch.return_value = {"status": "success", "stocks": [{"symbol": "COMI", "close": 88.5}]}

        unique_msg = f"سؤال تجريبي مخصص لاختبار التشاينينج {int(time.time()*1000)}"
        events = []
        async for chunk in run_agentic_chat_stream(
            message=unique_msg,
            user_id="test-uid",
            session_id="test-sid",
        ):
            events.append(chunk)

        # 1. Two turns executed: Turn 1 (tool call) and Turn 2 (synthesis)
        assert len(captured_post_payloads) == 2
        assert "tools" in captured_post_payloads[0]
        assert "tools" in captured_post_payloads[1]

        # 2. Verify events streamed final text
        tokens = [json.loads(c[5:].strip()) for c in events if c.startswith("data:") and not c.startswith("data: [DONE]")]
        token_texts = "".join(t.get("token", "") for t in tokens if t.get("type") == "token")
        assert "التجاري الدولي" in token_texts
        assert "DSML" not in token_texts


def test_dsml_interception_and_sanitization():
    """Verify that raw DSML markup is properly parsed into tool calls and sanitized from output."""
    from api.agentic_chat.pipeline import parse_dsml_tool_calls
    from api.agentic_chat.auth_guard import filter_output, strip_dsml

    raw_dsml = """<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="get_stock_levels">
<｜｜DSML｜｜ parameter name="symbol" string="true">MPCI</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
<｜｜DSML｜｜ invoke name="get_news">
<｜｜DSML｜｜ parameter name="symbol" string="true">EGX</｜｜DSML｜｜ parameter>
<｜｜DSML｜｜ parameter name="limit" string="false">15</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
</｜｜DSML｜｜ calls>"""

    # 1. Test parser
    calls = parse_dsml_tool_calls(raw_dsml)
    assert len(calls) == 2
    assert calls[0]["function"]["name"] == "get_stock_levels"
    assert json.loads(calls[0]["function"]["arguments"]) == {"symbol": "MPCI"}
    assert calls[1]["function"]["name"] == "get_news"
    assert json.loads(calls[1]["function"]["arguments"]) == {"symbol": "EGX", "limit": 15}

    # 2. Test stripper
    mixed_text = f"أهلاً بك، إليك التحليل:\n{raw_dsml}\nبالتوفيق دائماً."
    cleaned = strip_dsml(mixed_text)
    assert "DSML" not in cleaned
    assert "أهلاً بك" in cleaned
    assert "بالتوفيق دائماً" in cleaned

    # 3. Test filter_output
    filtered = filter_output(mixed_text)
    assert "DSML" not in filtered

    # 4. Test exact real-world DSML formats from user issues (Image 3 and Image 4)
    real_dsml_image_3 = """<'DSML | | calls | | >
<DSML | | invoke name="get_news" | | >
<DSML | | parameter name="symbol" string="true">EGX</ | | DSML | | parameter | | >
<DSML | | parameter name="limit" string="false">15</ | | DSML | | parameter | | >
<DSML | | invoke | | >
<DSML | | calls | | >"""

    calls_3 = parse_dsml_tool_calls(real_dsml_image_3)
    assert len(calls_3) == 1
    assert calls_3[0]["function"]["name"] == "get_news"
    assert json.loads(calls_3[0]["function"]["arguments"]) == {"symbol": "EGX", "limit": 15}
    assert strip_dsml(real_dsml_image_3) == ""

    real_dsml_image_4 = """<'DSML | | calls | | >
<DSML | | invoke name="get_stock" | | >
<DSML | | parameter name="symbol" string="true">AMFS</ | | DSML | | parameter | | >
<DSML | | invoke | | >
<DSML | | invoke name="get_stock" | | >
<DSML | | parameter name="symbol" string="true">ADIB</ | | DSML | | parameter | | >
<DSML | | invoke | | >
<DSML | | invoke name="get_stock" | | >
<DSML | | parameter name="symbol" string="true">UNIT</ | | DSML | | parameter | | >
<DSML | | invoke | | >
<DSML | | invoke name="get_stock" | | >
<DSML | | parameter name="symbol" string="true">LCSW</ | | DSML | | parameter | | >
<DSML | | invoke | | >
<DSML | | invoke name="get_stock" | | >
<DSML | | parameter name="symbol" string="true">AMIA</ | | DSML | | parameter | | >
<DSML | | invoke | | >
<DSML | | invoke name="get_stock" | | >
<DSML | | parameter name="symbol" string="true">CPOT</ | | DSML | | parameter | | >
<DSML | | invoke | | >
<DSML | | calls | | >"""

    calls_4 = parse_dsml_tool_calls(real_dsml_image_4)
    assert len(calls_4) == 6
    assert [c["function"]["name"] for c in calls_4] == ["get_stock"] * 6
    assert [json.loads(c["function"]["arguments"])["symbol"] for c in calls_4] == [
        "AMFS", "ADIB", "UNIT", "LCSW", "AMIA", "CPOT"
    ]
    assert strip_dsml(real_dsml_image_4) == ""


def test_multi_stock_get_stock_returns_all_symbols():
    """Verify that _sync_get_stock returns all requested symbols and does not break after first item."""
    from api.agentic_chat.tools_execution import _sync_get_stock, _TOOL_CACHE

    # Clear tool cache to test fresh execution
    _TOOL_CACHE.clear()

    res = _sync_get_stock(["COMI", "FWRY"])
    assert res.get("status") == "success"
    stocks = res.get("stocks") or []
    assert len(stocks) >= 2, f"Expected at least 2 stocks, got {len(stocks)}"
    symbols_returned = {s.get("symbol") for s in stocks}
    assert "COMI" in symbols_returned
    assert "FWRY" in symbols_returned


def test_analysis_cache_off_hours_evening_validity():
    """Verify that cache entry computed after 17:15 Cairo remains valid on the same evening at 20:00."""
    from zoneinfo import ZoneInfo
    import datetime as dt
    from api.agentic_chat.analysis_cache import is_cache_entry_valid

    cairo_tz = ZoneInfo("Africa/Cairo")
    # Computed Wednesday at 17:30
    computed_time = dt.datetime(2026, 11, 11, 17, 30, tzinfo=cairo_tz).timestamp()
    entry = {"computed_at": computed_time, "reply": "test"}

    # Probe on same Wednesday at 20:00
    probe_same_evening = dt.datetime(2026, 11, 11, 20, 0, tzinfo=cairo_tz)
    assert is_cache_entry_valid(entry, probe_same_evening) is True

    # Probe on Thursday morning at 08:30 (before market open at 10:00)
    probe_next_morning = dt.datetime(2026, 11, 12, 8, 30, tzinfo=cairo_tz)
    assert is_cache_entry_valid(entry, probe_next_morning) is True

    # Probe on Thursday at 10:30 (market open -> must be invalid)
    probe_during_market = dt.datetime(2026, 11, 12, 10, 30, tzinfo=cairo_tz)
    assert is_cache_entry_valid(entry, probe_during_market) is False

