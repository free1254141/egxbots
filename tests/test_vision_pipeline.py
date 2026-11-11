"""
tests/test_vision_pipeline.py
Unit tests for the complete Vision Analysis system ported from Vercel legacy vision.ts.
Tests extraction, Egyptian broker column mapping, OCR repair, market reconciliation,
and end-to-end streaming integration.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.agentic_chat.vision import (
    coerce_number_or_null,
    normalize_visible_price,
    extract_json_from_response,
    validate_vision_output,
    reconcile_vision_with_market,
    safe_portfolio_image_reply,
    safe_image_evidence_reply,
    format_vision_context_for_prompt,
    analyze_image,
)
from api.agentic_chat.pipeline import run_agentic_chat_stream


def test_coerce_number_or_null():
    assert coerce_number_or_null(123) == 123.0
    assert coerce_number_or_null("50,000") == 50000.0
    assert coerce_number_or_null("18.50 ج.م") == 18.5
    assert coerce_number_or_null("+5.25%") == 5.25
    assert coerce_number_or_null("-3.10%") == -3.1
    assert coerce_number_or_null("null") is None
    assert coerce_number_or_null("-") is None
    assert coerce_number_or_null(None) is None


def test_normalize_visible_price_ocr_correction():
    # Egyptian quote tables sometimes drop the decimal point (18150 -> 181.50)
    assert normalize_visible_price(18150, "portfolio") == 181.50
    assert normalize_visible_price(2550, "table") == 25.50
    # Values with thousands separator should NOT be divided (it's a share quantity)
    assert normalize_visible_price("22,700", "portfolio") == 22700.0
    # Values under 1000 stay intact
    assert normalize_visible_price(85.5, "portfolio") == 85.5


def test_extract_json_from_response_repairs():
    # 1. Plain clean JSON
    clean = '{"image_type": "portfolio", "symbols": [{"symbol": "COMI"}]}'
    assert extract_json_from_response(clean)["image_type"] == "portfolio"

    # 2. Markdown fenced with prose before/after
    fenced = 'Here is the JSON:\n```json\n{"image_type": "chart", "symbols": [{"symbol": "EAST"}]}\n```\nHope that helps!'
    parsed = extract_json_from_response(fenced)
    assert parsed is not None
    assert parsed["image_type"] == "chart"

    # 3. Comma-thousands in numbers
    comma_num = '{"image_type": "portfolio", "symbols": [{"symbol": "FWRY", "visible_values": {"quantity": 50,000}}]}'
    parsed = extract_json_from_response(comma_num)
    assert parsed is not None
    assert parsed["symbols"][0]["visible_values"]["quantity"] == 50000

    # 4. Trailing commas and single quotes
    smart_quotes = "{'image_type': 'table', 'symbols': [{'symbol': 'ORAS',},],}"
    parsed = extract_json_from_response(smart_quotes)
    assert parsed is not None
    assert parsed["image_type"] == "table"

    # 5. Salvage uppercase tickers when JSON is completely invalid
    garbage_with_tickers = "The screenshot shows COMI trading at higher levels, along with AMOC and FWRY."
    salvaged = extract_json_from_response(garbage_with_tickers)
    assert salvaged is not None
    syms = [s["symbol"] for s in salvaged["symbols"]]
    assert "COMI" in syms and "AMOC" in syms and "FWRY" in syms


def test_validate_vision_output_arabic_mapping():
    raw_data = {
        "image_type": "portfolio",
        "symbols": [
            {
                "symbol": "comi",
                "name": "البنك التجاري الدولي",
                "asset_type": "stock",
                "visible_values": {
                    "price": "88.50",
                    "average_price": "82.00",
                    "quantity": "1,500",
                    "market_value": "132750",
                    "profit_loss": "+9750",
                    "return_pct": "+7.93%",
                },
            },
            {
                "symbol": "CI30",
                "name": "صندوق مؤشر سي آي",
                "asset_type": "fund",
                "visible_values": {
                    "price": "22.50",
                    "quantity": "500",
                    "change_pct": "150.0%",  # Implausible daily change (OCR mix-up)
                },
            },
        ],
        "technical_observations": [
            {"symbol": "COMI", "indicator": "RSI", "value": 62.5, "meaning": "منطقة قوة شرائية"}
        ],
        "confidence": 0.95,
    }

    validated = validate_vision_output(raw_data)
    assert validated is not None
    assert validated["image_type"] == "portfolio"
    assert len(validated["symbols"]) == 2

    comi = next(s for s in validated["symbols"] if s["symbol"] == "COMI")
    assert comi["visible_values"]["price"] == 88.5
    assert comi["visible_values"]["average_price"] == 82.0
    assert comi["visible_values"]["quantity"] == 1500.0
    assert comi["visible_values"]["return_pct"] == 7.93
    assert comi["visible_values"]["profit_loss"] == 9750.0

    ci30 = next(s for s in validated["symbols"] if s["symbol"] == "CI30")
    # Implausible change_pct > 100% should be clamped to None and flagged in uncertainties
    assert ci30["visible_values"]["change_pct"] is None
    assert any("ترتيب الأعمدة غير منطقي" in u for u in validated["uncertainties"])


def test_reconcile_vision_with_market():
    vision = {
        "image_type": "portfolio",
        "symbols": [
            {
                "symbol": "COMI",
                "visible_values": {"price": 400.0},  # Implausible price vs close 88.5
            }
        ],
        "uncertainties": [],
    }

    mock_sb = MagicMock()
    mock_query = MagicMock()
    mock_sb.from_.return_value = mock_query
    mock_query.select.return_value = mock_query
    mock_query.in_.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.execute.return_value = MagicMock(data=[{"symbol": "COMI", "close": 88.5, "date": "2026-11-10"}])

    reconciled = reconcile_vision_with_market(vision, mock_sb)
    assert any("يختلف كثيراً عن آخر إغلاق مسجل" in u for u in reconciled["uncertainties"])


def test_safe_replies_formatting():
    vision = {
        "image_type": "portfolio",
        "symbols": [
            {
                "symbol": "COMI",
                "asset_type": "stock",
                "visible_values": {
                    "quantity": 1000,
                    "average_price": 80.0,
                    "price": 88.5,
                    "market_value": 88500,
                    "cost_basis": 80000,
                    "profit_loss": 8500,
                    "return_pct": 10.62,
                },
            }
        ],
        "uncertainties": [],
    }

    reply = safe_portfolio_image_reply(vision)
    assert "COMI" in reply
    assert "80.00 ج.م" in reply
    assert "88.50 ج.م" in reply
    assert "+10.62%" in reply

    chart_vision = {
        "image_type": "chart",
        "symbols": [{"symbol": "AMOC", "visible_values": {"price": 10.5, "change_pct": 2.1}}],
        "technical_observations": [{"symbol": "AMOC", "indicator": "RSI", "value": 55.0, "meaning": "حيادي"}],
        "market_depth": {},
        "user_relevant_summary": "شارت يومي يوضح اتجاه صاعد.",
        "uncertainties": [],
    }
    chart_reply = safe_image_evidence_reply(chart_vision)
    assert "AMOC" in chart_reply
    assert "10.50 ج.م" in chart_reply
    assert "RSI = 55.00" in chart_reply


@pytest.mark.anyio
async def test_end_to_end_vision_pipeline_streaming():
    """Verify that run_agentic_chat_stream runs vision analysis first and yields vision_result."""
    mock_vision_data = {
        "image_type": "portfolio",
        "symbols": [
            {
                "symbol": "COMI",
                "name": "البنك التجاري الدولي",
                "asset_type": "stock",
                "visible_values": {
                    "price": 88.5,
                    "average_price": 82.0,
                    "quantity": 1000,
                    "market_value": 88500,
                    "profit_loss": 6500,
                    "return_pct": 7.93,
                },
            }
        ],
        "technical_observations": [],
        "market_depth": {},
        "user_relevant_summary": "محفظة تحتوي على سهم COMI بربح 7.93%.",
        "uncertainties": [],
        "confidence": 0.95,
    }

    mock_llm_reply = MagicMock()
    mock_llm_reply.status_code = 200
    mock_llm_reply.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "قرأت محفظتك بنجاح، وسهم COMI حقق ربح ممتاز بنسبة 7.93%.",
                    "tool_calls": None,
                }
            }
        ]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.return_value = mock_llm_reply

    with patch("api.agentic_chat.pipeline.analyze_image", return_value=(mock_vision_data, None)), \
         patch("httpx.AsyncClient", return_value=mock_client), \
         patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test_key"}):

        chunks = []
        async for chunk in run_agentic_chat_stream(
            message="حلل محفظتي",
            images=["data:image/jpeg;base64,dummy_data"],
        ):
            chunks.append(chunk)

        full_output = "".join(chunks)

        # 1. Status event with 'vision' was yielded
        assert '"status": "vision"' in full_output

        # 2. Vision result event was yielded with extracted data
        assert '"type": "vision_result"' in full_output or '"type": "vision"' in full_output
        assert "COMI" in full_output

        # 3. LLM reply streamed successfully
        assert "قرأت محفظتك بنجاح" in full_output
