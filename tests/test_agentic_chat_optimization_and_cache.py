"""
tests/test_agentic_chat_optimization_and_cache.py
Verification suite for:
1. In-Memory Response Caching (analysis_cache.py).
2. Elimination of AGENTIC_TOOLS_SCHEMA in Round 2 synthesis.
3. Distributed atomic claim in scheduled_automations_worker.py.
"""

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
    assert extract_canonical_cache_key("سعر فوري كام دلوقتي") == "stock:FWRY"
    assert extract_canonical_cache_key("حلل سهم البنك التجاري الدولي COMI") == "stock:COMI"
    assert extract_canonical_cache_key("عتاقة نظامه ايه") == "stock:ATQA"
    assert extract_canonical_cache_key("طلعت مصطفى TMGH") == "stock:TMGH"

    # Canonical market keys
    assert extract_canonical_cache_key("حالة السوق المصري النهاردة") == "market:overview"
    assert extract_canonical_cache_key("المؤشر العام EGX30") == "market:overview"

    # Canonical Wyckoff & Recommendations
    assert extract_canonical_cache_key("ايه هي اقوى اسهم التجميع") == "wyckoff:accumulation"
    assert extract_canonical_cache_key("التوصيات المفتوحة النهاردة") == "recommendations:open"

    # Personal queries MUST return None (no cache)
    assert extract_canonical_cache_key("حلل اسهم محفظتي") is None
    assert extract_canonical_cache_key("انا اشتريت فوري على 8.20 ابيع ولا اعمل ايه") is None
    assert extract_canonical_cache_key("عدل الكمية في محفظتي") is None

    # Multimodal image queries MUST return None (no cache)
    assert extract_canonical_cache_key("حلل الصورة دي", images=["data:image/png;base64,..."]) is None


def test_analysis_cache_hit_and_miss_lifecycle():
    clear_analysis_cache()
    # Miss
    assert get_cached_analysis("سعر فوري كام دلوقتي") is None

    # Store
    sample_reply = (
        "📊 **تحليل سهم فوري (FWRY):**\n"
        "• السعر الحالي: 8.50 ج.م (+1.50%)\n"
        "• الدعم الفني الأول: 8.30 ج.م والمقاومة الأولى: 8.90 ج.م.\n"
        "• مؤشر RSI يستقر عند 54.2 في منطقة زخم إيجابي متوازن."
    )
    sample_tables = [{"symbol": "FWRY", "close": 8.50, "rsi": 54.2}]
    set_cached_analysis("سعر فوري كام دلوقتي", sample_reply, sample_tables, [])

    # Hit
    hit = get_cached_analysis("سعر فوري كام دلوقتي")
    assert hit is not None
    assert hit["key"] == "stock:FWRY"
    assert "FWRY" in hit["reply"]
    assert len(hit["tables"]) == 1
    assert hit["tables"][0]["close"] == 8.50

    # Synonymous query maps to the same stock key and hits the cache!
    synonym_hit = get_cached_analysis("تحليل فني لسهم شركة فوري للمدفوعات")
    assert synonym_hit is not None
    assert synonym_hit["key"] == "stock:FWRY"


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
async def test_round2_tools_schema_elimination():
    """Verify that after tools execute in round 1, round 2 streaming payload has NO 'tools' schema."""
    from api.agentic_chat.pipeline import run_agentic_chat_stream

    captured_post_payloads = []
    captured_stream_payloads = []

    mock_client = MagicMock()

    # Round 1: mock post returns tool call for get_stock
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {
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
                                "arguments": '{"symbols": ["COMI"]}'
                            }
                        }
                    ]
                }
            }
        ]
    }

    async def fake_post(url, headers=None, json=None, timeout=None):
        captured_post_payloads.append(json)
        return mock_post_resp

    mock_client.post = fake_post

    # Round 2: mock stream response
    class FakeStreamResp:
        status_code = 200
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def aiter_lines(self):
            yield 'data: {"choices": [{"delta": {"content": "تقرير سهم COMI"}}]}'
            yield 'data: [DONE]'

    def fake_stream(method, url, headers=None, json=None):
        captured_stream_payloads.append(json)
        return FakeStreamResp()

    mock_client.stream = fake_stream

    with patch("httpx.AsyncClient") as mock_http_cls, \
         patch("api.agentic_chat.pipeline.dispatch_tool") as mock_dispatch:
        mock_http_cls.return_value.__aenter__.return_value = mock_client
        mock_http_cls.return_value.__aexit__.return_value = None
        mock_dispatch.return_value = {"status": "success", "stocks": [{"symbol": "COMI", "close": 88.5}]}

        # Call with unique message to bypass cache
        unique_msg = f"سؤال تجريبي مخصص لاختبار الراوند {int(time.time()*1000)}"
        events = []
        async for chunk in run_agentic_chat_stream(
            message=unique_msg,
            user_id="test-uid",
            session_id="test-sid",
        ):
            events.append(chunk)

        # 1. Round 1 POST had tools schema
        assert len(captured_post_payloads) == 1
        assert "tools" in captured_post_payloads[0]

        # 2. Round 2 STREAM synthesis had NO tools schema (saving ~2,000 tokens)
        assert len(captured_stream_payloads) == 1
        assert "tools" not in captured_stream_payloads[0]
        assert "tool_choice" not in captured_stream_payloads[0]
        assert captured_stream_payloads[0]["stream"] is True


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

