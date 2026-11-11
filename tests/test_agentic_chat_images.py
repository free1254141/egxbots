import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from api.agentic_chat.pipeline import run_agentic_chat_stream
from api.agentic_chat.router import _persist_message_background, ChatRequest, chat_stream_endpoint


@pytest.mark.anyio
async def test_run_agentic_chat_stream_multimodal_formatting():
    """Verify that run_agentic_chat_stream performs vision analysis and injects verified facts."""
    dummy_image = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD..."
    captured_payloads = []

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

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "تم تحليل الصورة بنجاح وتحديد سهم COMI.",
                    "tool_calls": None
                }
            }
        ]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    async def fake_post(url, headers=None, json=None, timeout=None):
        captured_payloads.append(json)
        return mock_response

    mock_client.post = fake_post

    with patch("api.agentic_chat.pipeline.analyze_image", return_value=(mock_vision_data, None)), \
         patch("httpx.AsyncClient", return_value=mock_client), \
         patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test_key"}):
        chunks = []
        async for chunk in run_agentic_chat_stream(
            message="ما رأيك في هذه المحفظة؟",
            images=[dummy_image],
            history=[
                {"role": "user", "content": "مرحبا", "image_url": "data:image/png;base64,xyz123"},
                {"role": "assistant", "content": "أهلاً بك!"}
            ],
        ):
            chunks.append(chunk)

    assert len(captured_payloads) > 0, "No request was made to LLM client"
    payload = captured_payloads[0]
    messages = payload["messages"]

    # 1. Verify history with image_url is formatted multimodally
    history_user_msg = [m for m in messages if m.get("role") == "user" and isinstance(m.get("content"), list)][0]
    assert any(part.get("type") == "image_url" and part["image_url"]["url"] == "data:image/png;base64,xyz123" for part in history_user_msg["content"])

    # 2. Verify Vision Ground Truth system context is injected
    vision_sys_msgs = [m for m in messages if m.get("role") == "system" and "محرك Vision" in m.get("content", "")]
    assert len(vision_sys_msgs) == 1
    assert "COMI" in vision_sys_msgs[0]["content"]

    # 3. Verify SSE stream returned content
    full_text = "".join(chunks)
    assert "تم تحليل الصورة بنجاح" in full_text
    assert '"type": "vision_result"' in full_text or '"type": "vision"' in full_text


def test_persist_message_background_stores_image_url():
    """Verify that _persist_message_background includes image_url in user row."""
    mock_supabase = MagicMock()
    mock_sessions = MagicMock()
    mock_messages = MagicMock()

    mock_supabase.from_.side_effect = lambda table: mock_sessions if table == "ai_chat_sessions" else mock_messages

    with patch("api.agentic_chat.router.supabase", mock_supabase):
        _persist_message_background(
            session_id="test-session-123",
            user_id="user-456",
            user_msg="تحليل هذه الصورة",
            reply="تم التحليل",
            latency_ms=450,
            image_url="data:image/png;base64,sample_image_data",
        )

        assert mock_messages.insert.called
        inserted_rows = mock_messages.insert.call_args[0][0]
        user_row = next(r for r in inserted_rows if r["role"] == "user")
        assert user_row["image_url"] == "data:image/png;base64,sample_image_data"
        assert user_row["content"] == "تحليل هذه الصورة"


@pytest.mark.anyio
async def test_chat_stream_endpoint_passes_images_to_pipeline_and_persistence():
    """Verify that chat_stream_endpoint correctly extracts images and delegates to pipeline and persistence."""
    from tests.test_agentic_chat_auth_and_isolation import build_mock_request

    req = build_mock_request(
        headers={"authorization": "Bearer valid_token"},
        body={"message": "حلل محفظتي", "images": ["data:image/png;base64,image123"]}
    )

    body = ChatRequest(
        message="حلل محفظتي",
        images=["data:image/png;base64,image123"],
        sessionId="session-789",
        stream=False,
    )

    fake_stream_chunks = [
        "data: " + json.dumps({"type": "content", "content": "تحليل المحفظة"}) + "\n\n",
        "data: " + json.dumps({"type": "done", "reply": "تحليل المحفظة كامل", "latency_ms": 250}) + "\n\n",
        "data: [DONE]\n\n"
    ]

    async def mock_generator(*args, **kwargs):
        assert kwargs.get("images") == ["data:image/png;base64,image123"]
        assert kwargs.get("message") == "حلل محفظتي"
        for c in fake_stream_chunks:
            yield c

    with patch("api.agentic_chat.router.get_authenticated_user", return_value={"id": "usr-123", "is_pro": True, "remaining_quota": 99}), \
         patch("api.agentic_chat.router.run_agentic_chat_stream", side_effect=mock_generator), \
         patch("api.agentic_chat.router._persist_message_background") as mock_persist:

        resp = await chat_stream_endpoint(
            request=req,
            body=body,
        )

        data = json.loads(resp.body)
        assert data["reply"] == "تحليل المحفظة كامل"
        assert data["session_id"] == "session-789"


@pytest.mark.anyio
async def test_chat_stream_endpoint_streaming_mode_with_images():
    """Verify that chat_stream_endpoint in streaming mode yields SSE chunks and handles image inputs."""
    from tests.test_agentic_chat_auth_and_isolation import build_mock_request

    req = build_mock_request(
        headers={"authorization": "Bearer valid_token", "accept": "text/event-stream"},
        body={"message": "حلل صورتي", "images": ["data:image/png;base64,image999"]}
    )

    body = ChatRequest(
        message="حلل صورتي",
        images=["data:image/png;base64,image999"],
        sessionId="session-streaming-1",
        stream=True,
    )

    fake_stream_chunks = [
        "data: " + json.dumps({"type": "content", "content": "تم تحليل"}, ensure_ascii=False) + "\n\n",
        "data: " + json.dumps({"type": "done", "reply": "تم تحليل محفظتك بنجاح", "latency_ms": 300}, ensure_ascii=False) + "\n\n",
        "data: [DONE]\n\n"
    ]

    async def mock_generator(*args, **kwargs):
        assert kwargs.get("images") == ["data:image/png;base64,image999"]
        assert kwargs.get("message") == "حلل صورتي"
        for c in fake_stream_chunks:
            yield c

    with patch("api.agentic_chat.router.get_authenticated_user", return_value={"id": "usr-123", "is_pro": True, "remaining_quota": 99}), \
         patch("api.agentic_chat.router.run_agentic_chat_stream", side_effect=mock_generator), \
         patch("api.agentic_chat.router.asyncio.create_task") as mock_task:

        resp = await chat_stream_endpoint(
            request=req,
            body=body,
            accept="text/event-stream"
        )

        assert resp.status_code == 200
        # Iterate streaming response
        collected = []
        async for chunk in resp.body_iterator:
            collected.append(chunk)

        full_stream_text = "".join(collected)
        assert "تم تحليل محفظتك بنجاح" in full_stream_text
        assert mock_task.called
