"""Unit tests for analysis cache key fixes, Arabic normalization, multi-tool resolution, and single-stock 1-round fast-track."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from api.agentic_chat.analysis_cache import (
    build_analysis_cache_key,
    clear_analysis_cache,
    get_vip_analysis_cache,
    resolve_tool_calls_to_cache_key,
    set_vip_analysis_cache,
)
import importlib
from api.agentic_chat import pipeline
chat_router = importlib.import_module("api.agentic_chat.router")
from api.agentic_chat import tools_execution
from api import native_telegram_vip_chat


def test_arabic_normalization_and_canonical_keys():
    assert build_analysis_cache_key("اقوى الاسهم النهارده") == "vip_top_stocks"
    assert build_analysis_cache_key("أقوى الأسهم النهارده") == "vip_top_stocks"
    assert (
        build_analysis_cache_key(
            "رشّح لي 3 أسهم عليها فرصة شراء النهارده، مع سعر الدخول ووقف الخسارة والهدف"
        )
        == "vip_open_recommendations"
    )
    assert build_analysis_cache_key("هل في فرصة شراء في سهم COMI") == "vip_stock_COMI"


def test_single_stock_levels_unified_with_stock_key():
    k1 = build_analysis_cache_key("حلّل لي سهم PHDC فنياً وقولّي مناطق الدخول والخروج المناسبة")
    k2 = build_analysis_cache_key("ما هي مستويات الدعم والمقاومة وأهداف سهم PHDC")
    assert k1 == "vip_stock_PHDC"
    assert k2 == "vip_stock_PHDC"


def test_resolve_tool_calls_to_cache_key_multi_tool():
    pair = [
        {"function": {"name": "get_stock", "arguments": '{"symbol":"PHDC"}'}},
        {"function": {"name": "get_stock_levels", "arguments": '{"symbol":"PHDC"}'}},
    ]
    assert resolve_tool_calls_to_cache_key(pair) == "vip_stock_PHDC"

    recs_pair = [
        {"function": {"name": "get_recommendations", "arguments": "{}"}},
        {"function": {"name": "get_technical_scan", "arguments": "{}"}},
    ]
    assert resolve_tool_calls_to_cache_key(recs_pair) == "vip_open_recommendations"


@pytest.mark.anyio
async def test_single_stock_fast_track_single_llm_call_and_cache_hit(monkeypatch):
    clear_analysis_cache()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test_key")

    post_calls = []

    async def fake_post(self, url, *args, **kwargs):
        payload = kwargs.get("json", {})
        post_calls.append(payload)
        # Fast-track sends grounded context without tools schema
        assert "tools" not in payload
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                "### 📊 تحليل سهم بالم هيلز (PHDC) — EGX\n\n"
                                "**السعر الأخير:** `12.39` ج.م (-0.08%)\n"
                                "📌 **حالة السهم في محفظتك:** السهم غير مسجل ضمن مراكز محفظتك الاستثمارية المحفوظة.\n"
                                "الدعم الأول 10.33 ج.م والمقاومة الأولى 13.30 ج.م مع متابعة حجم التداول والاتجاه الفني العام."
                            )
                        }
                    }
                ]
            },
        )

    async def fake_dispatch(tool_name, arguments, **_kwargs):
        dispatched_calls.append((tool_name, arguments))
        assert arguments == {"symbols": ["PHDC"]}
        if tool_name == "get_stock":
            return {"status": "success", "stocks": [{"symbol": "PHDC", "name_ar": "بالم هيلز", "close": 12.39, "change_pct": -0.08}]}
        if tool_name == "get_stock_levels":
            return {"status": "success", "symbol": "PHDC", "support_1": 10.33, "resistance_1": 13.30}
        if tool_name == "get_news":
            return {"status": "success", "symbol": "PHDC", "news": []}
        return {"status": "success"}

    dispatched_calls = []

    with patch.object(httpx.AsyncClient, "post", new=fake_post), patch.object(
        pipeline, "dispatch_tool", side_effect=fake_dispatch
    ), patch("api.agentic_chat.pipeline._init_supabase"), patch.object(
        pipeline, "supabase", SimpleNamespace()
    ):
        # 1) Cold call: Fast-track runs 3 tools concurrently + ONLY 1 DeepSeek LLM call
        done_cold = None
        async for chunk in pipeline.run_agentic_chat_stream(
            message="حلل سهم PHDC",
            history=[],
            images=[],
            session_id="test_fast_1",
            user_id="11111111-1111-1111-1111-111111111111",
            is_pro=True,
            remaining_quota=350,
            quota_limit=350,
        ):
            line = chunk.strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                ev = json.loads(line[5:].strip())
                if ev.get("type") == "done":
                    done_cold = ev

        assert len(post_calls) == 1
        assert [c[0] for c in dispatched_calls] == ["get_stock", "get_stock_levels", "get_news"]
        assert all(c[1] == {"symbols": ["PHDC"]} for c in dispatched_calls)
        assert done_cold is not None
        assert done_cold["cached"] is False
        assert done_cold["cache_key"] == "vip_stock_PHDC"
        assert len(done_cold["tables"]) == 1

        # 2) Second call with different wording: hits RAM cache with 0 LLM calls
        post_calls.clear()
        done_hit = None
        async for chunk in pipeline.run_agentic_chat_stream(
            message="ما هي مستويات الدعم والمقاومة وأهداف سهم PHDC",
            history=[],
            images=[],
            session_id="test_fast_2",
            user_id="11111111-1111-1111-1111-111111111111",
            is_pro=True,
            remaining_quota=350,
            quota_limit=350,
        ):
            line = chunk.strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                ev = json.loads(line[5:].strip())
                if ev.get("type") == "done":
                    done_hit = ev

        assert len(post_calls) == 0
        assert done_hit is not None
        assert done_hit["cached"] is True
        assert done_hit["cache_key"] == "vip_stock_PHDC"


def test_build_analysis_cache_key_regressions():
    assert build_analysis_cache_key("analyze COMI") == "vip_stock_COMI"
    assert build_analysis_cache_key("price of FWRY") == "vip_stock_FWRY"
    assert build_analysis_cache_key("what is the best stock today") is None
    swing_key = build_analysis_cache_key("رشح لي أسهم swing اليوم")
    assert swing_key != "vip_stock_SWING"
    assert swing_key == "vip_open_recommendations"
    assert build_analysis_cache_key("حلل سهم COMI و PHDC") is None
    assert build_analysis_cache_key("حساب زكاة 500 سهم COMI") is None
    assert build_analysis_cache_key("تحليل مالي لسهم COMI") == "vip_stock_COMI_financials"
    assert build_analysis_cache_key("ما هي أخبار سهم COMI اليوم؟") == "vip_stock_COMI_news"


def test_resolve_tool_calls_to_cache_key_strict_rejections():
    assert resolve_tool_calls_to_cache_key(
        [{"function": {"name": "get_recommendations", "arguments": '{"sharia_only": true}'}}]
    ) is None
    assert resolve_tool_calls_to_cache_key(
        [{"function": {"name": "get_recommendations", "arguments": '{"symbols": ["COMI"]}'}}]
    ) is None
    assert resolve_tool_calls_to_cache_key(
        [{"function": {"name": "get_recommendations", "arguments": '{"status": "closed"}'}}]
    ) is None
    assert resolve_tool_calls_to_cache_key(
        [
            {"function": {"name": "get_recommendations", "arguments": '{"timeframe": "last_week"}'}},
            {"function": {"name": "get_technical_scan", "arguments": "{}"}},
        ]
    ) is None
    assert resolve_tool_calls_to_cache_key(
        [{"function": {"name": "get_accumulation_stocks", "arguments": '{"sharia_only": true}'}}]
    ) is None
    assert resolve_tool_calls_to_cache_key(
        [{"function": {"name": "get_technical_scan", "arguments": '{"sector": "عقارات"}'}}]
    ) is None
    assert resolve_tool_calls_to_cache_key(
        [{"function": {"name": "get_fair_value", "arguments": '{"symbol": "COMI", "sharia_only": true}'}}]
    ) is None
    assert resolve_tool_calls_to_cache_key(
        [
            {"function": {"name": "get_stock", "arguments": '{"symbol": "COMI"}'}},
            {"function": {"name": "manage_portfolio", "arguments": '{"action": "get"}'}},
        ]
    ) is None
    assert resolve_tool_calls_to_cache_key(
        [
            {"function": {"name": "get_stock", "arguments": '{"symbol": "COMI"}'}},
            {"function": {"name": "get_fair_value", "arguments": '{"symbol": "COMI"}'}},
        ]
    ) is None
    assert resolve_tool_calls_to_cache_key(
        [{"function": {"name": "get_stock", "arguments": '{"symbols": ["COMI", "PHDC"]}'}}]
    ) is None
    assert (
        resolve_tool_calls_to_cache_key(
            [
                {"function": {"name": "get_stock", "arguments": '{"symbols": ["COMI"]}'}},
                {"function": {"name": "get_stock_levels", "arguments": '{"symbols": ["COMI"]}'}},
                {"function": {"name": "get_news", "arguments": '{"symbols": ["COMI"]}'}},
            ]
        )
        == "vip_stock_COMI"
    )
    assert (
        resolve_tool_calls_to_cache_key(
            [{"function": {"name": "get_news", "arguments": '{"symbols": ["PHDC"]}'}}]
        )
        == "vip_news_PHDC"
    )


@pytest.mark.anyio
async def test_dispatch_tool_get_news_singular_symbol_fallback():
    captured = {}

    async def fake_exec_news(symbols=None, market=None):
        captured["symbols"] = symbols
        captured["market"] = market
        return {"status": "success", "news": []}

    with patch.object(tools_execution, "execute_get_news", side_effect=fake_exec_news):
        await tools_execution.dispatch_tool("get_news", {"symbol": "phdc"}, default_market="EGX")
    assert captured["symbols"] == ["PHDC"]


@pytest.mark.anyio
async def test_pipeline_history_bypasses_fast_track_and_cache(monkeypatch):
    clear_analysis_cache()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test_key")

    set_vip_analysis_cache(
        cache_key="vip_stock_PHDC",
        reply="تحليل مخزن سابقا " + ("تفاصيل " * 20),
        tables=[],
    )

    seen_tools_flag = []

    async def fake_post(self, url, *args, **kwargs):
        payload = kwargs.get("json", {})
        seen_tools_flag.append("tools" in payload)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "رد متابعة مرتبط بسياق المحادثة السابقة لسهم PHDC."}}
                ]
            },
        )

    with patch.object(httpx.AsyncClient, "post", new=fake_post), patch(
        "api.agentic_chat.pipeline._init_supabase"
    ), patch.object(pipeline, "supabase", SimpleNamespace()):
        done_ev = None
        async for chunk in pipeline.run_agentic_chat_stream(
            message="حلل سهم PHDC",
            history=[{"role": "user", "content": "قارن مع مقترحي السابق"}],
            images=[],
            session_id="test_hist_1",
            user_id="11111111-1111-1111-1111-111111111111",
        ):
            line = chunk.strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                ev = json.loads(line[5:].strip())
                if ev.get("type") == "done":
                    done_ev = ev

        assert seen_tools_flag == [True]
        assert done_ev is not None
        assert done_ev["cached"] is False
        assert done_ev["cache_key"] is None


@pytest.mark.anyio
async def test_pipeline_round1_clears_stale_candidate_on_non_cacheable_batch(monkeypatch):
    clear_analysis_cache()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test_key")

    call_idx = 0

    async def fake_post(self, url, *args, **kwargs):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "tc1",
                                        "type": "function",
                                        "function": {"name": "get_stock", "arguments": '{"symbols":["COMI"]}'},
                                    },
                                    {
                                        "id": "tc2",
                                        "type": "function",
                                        "function": {"name": "manage_portfolio", "arguments": '{"action":"get"}'},
                                    },
                                ],
                            }
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "📌 **حالة السهم في محفظتك:** لديك 100 سهم COMI " + ("تفاصيل " * 20),
                        }
                    }
                ]
            },
        )

    async def fake_dispatch(tool_name, arguments, **_kwargs):
        if tool_name == "get_stock":
            return {"status": "success", "stocks": [{"symbol": "COMI", "close": 100.0}]}
        return {"status": "success", "positions": [{"symbol": "COMI", "quantity": 100}]}

    with patch.object(httpx.AsyncClient, "post", new=fake_post), patch.object(
        pipeline, "dispatch_tool", side_effect=fake_dispatch
    ), patch("api.agentic_chat.pipeline._init_supabase"), patch.object(
        pipeline, "supabase", SimpleNamespace()
    ):
        done_ev = None
        async for chunk in pipeline.run_agentic_chat_stream(
            message="ما هي أخبار سهم COMI اليوم؟",
            history=[],
            images=[],
            session_id="test_stale_clear",
            user_id="11111111-1111-1111-1111-111111111111",
        ):
            line = chunk.strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                ev = json.loads(line[5:].strip())
                if ev.get("type") == "done":
                    done_ev = ev

        assert done_ev is not None
        assert done_ev["cached"] is False
        assert done_ev["cache_key"] is None
        assert get_vip_analysis_cache("vip_stock_COMI_news") is None


@pytest.mark.anyio
async def test_pipeline_round1_model_driven_cache_hit(monkeypatch):
    clear_analysis_cache()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test_key")

    set_vip_analysis_cache(
        cache_key="vip_accumulation",
        reply="### أسهم التجميع المؤسسي اليوم\n" + ("تجميع قوي " * 15),
        tables=[{"title": "التجميع", "headers": ["السهم"], "rows": [["PHDC"]]}],
    )

    post_calls = []

    async def fake_post(self, url, *args, **kwargs):
        post_calls.append(kwargs.get("json", {}))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "tc1",
                                    "type": "function",
                                    "function": {"name": "get_accumulation_stocks", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ]
            },
        )

    with patch.object(httpx.AsyncClient, "post", new=fake_post), patch(
        "api.agentic_chat.pipeline._init_supabase"
    ), patch.object(pipeline, "supabase", SimpleNamespace()):
        done_ev = None
        async for chunk in pipeline.run_agentic_chat_stream(
            message="هل في تجميع مؤسسي وشراء قوي؟",
            history=[],
            images=[],
            session_id="test_r1_hit",
            user_id="11111111-1111-1111-1111-111111111111",
        ):
            line = chunk.strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                ev = json.loads(line[5:].strip())
                if ev.get("type") == "done":
                    done_ev = ev

        assert len(post_calls) == 1
        assert done_ev is not None
        assert done_ev["cached"] is True
        assert done_ev["cache_key"] == "vip_accumulation"


@pytest.mark.anyio
async def test_pipeline_synthesis_retry_and_error_handling(monkeypatch):
    clear_analysis_cache()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test_key")

    # 1) Retry succeeds after transient 503
    attempts = []

    async def retry_success_post(self, url, *args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(503, text="upstream busy")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "تقرير COMI بعد إعادة المحاولة " + ("بيانات فنية " * 12),
                        }
                    }
                ]
            },
        )

    async def fake_dispatch(tool_name, arguments, **_kwargs):
        return {"status": "success"}

    with patch.object(httpx.AsyncClient, "post", new=retry_success_post), patch.object(
        pipeline, "dispatch_tool", side_effect=fake_dispatch
    ), patch("api.agentic_chat.pipeline._init_supabase"), patch.object(
        pipeline, "supabase", SimpleNamespace()
    ):
        done_ev = None
        async for chunk in pipeline.run_agentic_chat_stream(
            message="حلل سهم COMI",
            history=[],
            images=[],
            session_id="test_retry_ok",
            user_id="11111111-1111-1111-1111-111111111111",
        ):
            line = chunk.strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                ev = json.loads(line[5:].strip())
                if ev.get("type") == "done":
                    done_ev = ev
        assert len(attempts) == 2
        assert done_ev is not None
        assert "تقرير COMI بعد إعادة المحاولة" in done_ev["reply"]

    # 2) Permanent 503 emits error event and never emits done or writes cache
    clear_analysis_cache()

    async def always_503_post(self, url, *args, **kwargs):
        return httpx.Response(503, text="down")

    with patch.object(httpx.AsyncClient, "post", new=always_503_post), patch.object(
        pipeline, "dispatch_tool", side_effect=fake_dispatch
    ), patch("api.agentic_chat.pipeline._init_supabase"), patch.object(
        pipeline, "supabase", SimpleNamespace()
    ):
        events = []
        async for chunk in pipeline.run_agentic_chat_stream(
            message="حلل سهم COMI",
            history=[],
            images=[],
            session_id="test_retry_fail",
            user_id="11111111-1111-1111-1111-111111111111",
        ):
            line = chunk.strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                events.append(json.loads(line[5:].strip()))
        assert any(e.get("type") == "error" for e in events)
        assert not any(e.get("type") == "done" for e in events)
        assert get_vip_analysis_cache("vip_stock_COMI") is None


@pytest.mark.anyio
async def test_pipeline_synthesis_dsml_safety_fallback(monkeypatch):
    clear_analysis_cache()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test_key")

    synth_calls = []

    async def dsml_then_clean_post(self, url, *args, **kwargs):
        synth_calls.append(kwargs.get("json", {}))
        if len(synth_calls) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "<｜DSML｜function_calls>"
                                    "<｜DSML｜invoke name=\"get_fair_value\">"
                                    "<｜DSML｜parameter name=\"symbol\" string=\"true\">PHDC</｜DSML｜parameter>"
                                    "</｜DSML｜invoke>"
                                    "</｜DSML｜function_calls>"
                                ),
                            }
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "التحليل النظيف لسهم PHDC بعد تنفيذ الأداة " + ("مقاومة ودعم " * 12),
                        }
                    }
                ]
            },
        )

    async def fake_dispatch(tool_name, arguments, **_kwargs):
        return {"status": "success", "symbol": "PHDC"}

    with patch.object(httpx.AsyncClient, "post", new=dsml_then_clean_post), patch.object(
        pipeline, "dispatch_tool", side_effect=fake_dispatch
    ), patch("api.agentic_chat.pipeline._init_supabase"), patch.object(
        pipeline, "supabase", SimpleNamespace()
    ):
        done_ev = None
        async for chunk in pipeline.run_agentic_chat_stream(
            message="حلل سهم PHDC",
            history=[],
            images=[],
            session_id="test_dsml_fb",
            user_id="11111111-1111-1111-1111-111111111111",
        ):
            line = chunk.strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                ev = json.loads(line[5:].strip())
                if ev.get("type") == "done":
                    done_ev = ev
        assert len(synth_calls) == 2
        assert done_ev is not None
        assert "DSML" not in done_ev["reply"]
        assert "التحليل النظيف لسهم PHDC" in done_ev["reply"]


def test_router_and_telegram_persist_cache_telemetry():
    # 1) router._persist_message_background records cached, cache_key, and latency_ms
    inserted_batches = []

    class FakeTable:
        def __init__(self, name):
            self.name = name

        def upsert(self, payload, **_kwargs):
            return self

        def insert(self, rows):
            inserted_batches.append((self.name, rows))
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    fake_sb = SimpleNamespace(from_=lambda name: FakeTable(name))
    with patch.object(chat_router, "_init_supabase"), patch.object(chat_router, "supabase", fake_sb):
        chat_router._persist_message_background(
            session_id="sess_web_1",
            user_id="11111111-1111-1111-1111-111111111111",
            user_msg="حلل سهم PHDC",
            reply="تقرير PHDC",
            latency_ms=420,
            market="EGX",
            cached=True,
            cache_key="vip_stock_PHDC",
        )

    assert len(inserted_batches) == 1
    assert inserted_batches[0][0] == "ai_chat_messages"
    assistant_row = inserted_batches[0][1][1]
    assert assistant_row["metadata"]["cached"] is True
    assert assistant_row["metadata"]["cache_key"] == "vip_stock_PHDC"
    assert assistant_row["metadata"]["latency_ms"] == 420

    # 2) Telegram fast-path cache hit + fallback telemetry reset
    clear_analysis_cache()
    set_vip_analysis_cache(
        cache_key="vip_stock_PHDC",
        reply="تقرير تليجرام المخزن لسهم PHDC " + ("مستويات " * 12),
        tables=[],
    )

    tg_batches = []

    class FakeTgTable:
        def __init__(self, name):
            self.name = name

        def upsert(self, *_args, **_kwargs):
            return self

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def insert(self, rows):
            tg_batches.append((self.name, rows))
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    fake_tg_sb = SimpleNamespace(from_=lambda name: FakeTgTable(name))
    fake_user = {
        "linked": True,
        "linked_user_id": "11111111-1111-1111-1111-111111111111",
        "display_name": "Tester",
        "is_pro": True,
        "is_admin": False,
        "limit": 350,
        "used": 0,
        "remaining": 350,
        "period": "monthly",
        "chat_source": "telegram_private",
        "state_row": {"chat_history": [], "daily_count": 0},
    }
    payload = {
        "action": "chat",
        "message": "حلل سهم PHDC",
        "telegram_user_id": 999,
        "telegram_username": "tester",
        "chat_source": "telegram_private",
    }

    with patch.object(native_telegram_vip_chat, "_resolve_telegram_user", return_value=fake_user), patch(
        "api.agentic_chat.auth_guard.check_and_consume_quota", return_value=(True, 349, 350, None)
    ), patch.object(native_telegram_vip_chat, "_supabase_request", return_value=[]), patch(
        "api.stock_ai._init_supabase"
    ), patch("api.stock_ai.supabase", fake_tg_sb):
        res_hit = native_telegram_vip_chat.handle_native_vip_chat(payload)
    assert res_hit["ok"] is True
    assert len(tg_batches) == 1
    tg_meta = tg_batches[0][1][1]["metadata"]
    assert tg_meta["cached"] is True
    assert tg_meta["cache_key"] == "vip_stock_PHDC"
    assert isinstance(tg_meta["latency_ms"], int)

    # Fallback path: clear cache and force empty agentic stream -> cached=False and no cache_key leaked
    clear_analysis_cache()
    tg_batches.clear()

    async def empty_stream(**_kwargs):
        if False:
            yield ""

    with patch.object(native_telegram_vip_chat, "_resolve_telegram_user", return_value=fake_user), patch(
        "api.agentic_chat.auth_guard.check_and_consume_quota", return_value=(True, 348, 350, None)
    ), patch(
        "api.agentic_chat.pipeline.run_agentic_chat_stream", side_effect=empty_stream
    ), patch.object(native_telegram_vip_chat, "_supabase_request", return_value=[]), patch(
        "api.stock_ai._init_supabase"
    ), patch("api.stock_ai.supabase", fake_tg_sb):
        res_fb = native_telegram_vip_chat.handle_native_vip_chat(payload)
    assert res_fb["ok"] is True
    assert len(tg_batches) == 1
    fb_meta = tg_batches[0][1][1]["metadata"]
    assert fb_meta["cached"] is False
    assert "cache_key" not in fb_meta


def test_scheduled_worker_ai_score_rvol_limit_and_live_screen_prompt():
    from api.agentic_chat import prompts
    from api import scheduled_automations_worker as saw

    assert "/stocks" in prompts.ARTORO_PLATFORM_CONTEXT
    assert "شاشة أسعار الأسهم المباشرة" in prompts.ARTORO_PLATFORM_CONTEXT

    seen_urls = []

    def fake_supa(path, **_kwargs):
        seen_urls.append(path)
        if "select=date" in path:
            return [{"date": "2026-11-15"}]
        if "stock_technical_indicators" in path:
            return [
                {
                    "symbol": "AIH",
                    "date": "2026-11-15",
                    "close": 0.879,
                    "change_pct": 1.2,
                    "volume": 500000,
                    "r_vol": 0.0303,
                    "rsi_14": 58.2,
                    "ema_20": 0.85,
                    "ema_50": 0.81,
                    "bb_lower": 0.79,
                    "bb_upper": 0.92,
                    "egx_ai_score": 0.594,
                }
            ]
        return []

    with patch.object(saw, "_supabase_request", side_effect=fake_supa):
        brief = saw._fetch_market_indicators_brief(
            symbols=[],
            prompt="عاوزك تبعتلى أعلى عشرة اسهم حاصلين على أعلى سكور شامل",
        )

    assert "تقييم AI: 59/100" in brief
    assert "تقييم AI: 1/100" not in brief
    assert "السيولة النسبية: 0.03x" in brief
    assert any("limit=10" in u for u in seen_urls)


def test_model_driven_followup_flag_and_preset_cache_isolation():
    from api.agentic_chat.analysis_cache import inspect_tool_calls_followup_flags

    # Contextual follow-up flagged by model must NEVER hit or pollute shared cache
    assert resolve_tool_calls_to_cache_key(
        [{"function": {"name": "get_stock", "arguments": '{"symbols": ["AMES"], "is_contextual_followup": true}'}}]
    ) is None
    assert resolve_tool_calls_to_cache_key(
        [
            {"function": {"name": "get_stock", "arguments": '{"symbols": ["AMES"], "is_contextual_followup": false}'}},
            {"function": {"name": "get_stock_levels", "arguments": '{"symbols": ["AMES"], "is_contextual_followup": true}'}},
        ]
    ) is None

    # Arabic symbol alias inside tool call normalizes to canonical ASCII ticker key
    assert (
        resolve_tool_calls_to_cache_key(
            [{"function": {"name": "get_stock", "arguments": '{"symbols": ["فوري"], "is_contextual_followup": false}'}}]
        )
        == "vip_stock_FWRY"
    )

    # Technical scan presets isolate cache keys cleanly (top_losers != rsi_oversold)
    assert (
        resolve_tool_calls_to_cache_key(
            [{"function": {"name": "get_technical_scan", "arguments": '{"preset": "top_losers", "is_contextual_followup": false}'}}]
        )
        == "vip_tech_screener_top_losers"
    )
    assert (
        resolve_tool_calls_to_cache_key(
            [{"function": {"name": "get_technical_scan", "arguments": '{"preset": "rsi_oversold", "is_contextual_followup": false}'}}]
        )
        == "vip_tech_screener_rsi_oversold"
    )

    assert inspect_tool_calls_followup_flags(
        [{"function": {"name": "get_stock", "arguments": '{"symbols": ["AMES"], "is_contextual_followup": false}'}}]
    ) == (False, True)
    assert inspect_tool_calls_followup_flags(
        [{"function": {"name": "get_stock", "arguments": '{"symbols": ["AMES"], "is_contextual_followup": true}'}}]
    ) == (True, False)
    assert inspect_tool_calls_followup_flags(
        [{"function": {"name": "get_stock", "arguments": '{"symbols": ["AMES"]}'}}]
    ) == (False, False)


@pytest.mark.anyio
async def test_multi_turn_standalone_caches_and_prunes_and_followup_bypasses(monkeypatch):
    clear_analysis_cache()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test_key")

    dispatched_args = []

    async def fake_dispatch(tool_name, args, **_kwargs):
        dispatched_args.append((tool_name, dict(args)))
        return {"status": "success", "symbol": "AMES", "close": 54.97, "change_pct": 5.92, "rsi_14": 91.82}

    seen_synth_messages = []
    llm_call_idx = 0

    async def fake_post_standalone(self, url, *args, **kwargs):
        nonlocal llm_call_idx
        llm_call_idx += 1
        payload = kwargs.get("json", {})
        if llm_call_idx == 1:
            # Round 1: Model reads history and explicitly signals is_contextual_followup=False
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "tc_ames_1",
                                        "type": "function",
                                        "function": {
                                            "name": "get_stock",
                                            "arguments": '{"symbols": ["AMES"], "is_contextual_followup": false}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        seen_synth_messages.append(payload.get("messages", []))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "### 📊 تحليل سهم اميس (AMES) — EGX\n**السعر الأخير:** 54.97 ج.م " + ("تفاصيل فنية موثقة " * 10),
                        }
                    }
                ]
            },
        )

    fake_history = [{"role": "user", "content": "سؤال قديم عن COMI"}, {"role": "assistant", "content": "تحليل COMI السابق"}]

    # 1. First call with history (MISS -> populates cache cleanly and prunes prior history from synthesis)
    with patch.object(httpx.AsyncClient, "post", new=fake_post_standalone), patch(
        "api.agentic_chat.pipeline.dispatch_tool", side_effect=fake_dispatch
    ), patch("api.agentic_chat.pipeline._init_supabase"), patch.object(
        pipeline, "supabase", SimpleNamespace()
    ), patch("api.agentic_chat.analysis_cache.set_vip_analysis_cache") as mock_set_cache, patch(
        "api.agentic_chat.pipeline.set_vip_analysis_cache"
    ) as mock_pipe_set:
        done1 = None
        async for chunk in pipeline.run_agentic_chat_stream(
            message="حلل سهم AMES",
            history=fake_history,
            images=[],
            session_id="mt_1",
            user_id="11111111-1111-1111-1111-111111111111",
        ):
            line = chunk.strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                ev = json.loads(line[5:].strip())
                if ev.get("type") == "done":
                    done1 = ev

    assert done1 is not None
    assert done1["cached"] is False
    assert done1["cache_key"] == "vip_stock_AMES"
    # is_contextual_followup must be stripped before dispatching tool
    assert dispatched_args == [("get_stock", {"symbols": ["AMES"]})]
    # Prior history turns must be pruned from Round 2 synthesis to prevent cross-stock bleed
    assert seen_synth_messages and not any("سؤال قديم عن COMI" in str(m.get("content", "")) for m in seen_synth_messages[0])
    assert mock_pipe_set.called or mock_set_cache.called

    # 2. Seed cache and verify Round-1 HIT even with history present (0 Round-2 calls!)
    set_vip_analysis_cache(
        cache_key="vip_stock_AMES",
        reply="### 📊 تحليل سهم اميس (AMES) مخزن بالكاش " + ("بيانات " * 15),
        tables=[],
    )
    hit_calls = 0

    async def fake_post_hit(self, url, *args, **kwargs):
        nonlocal hit_calls
        hit_calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "tc_ames_2",
                                    "type": "function",
                                    "function": {
                                        "name": "get_stock",
                                        "arguments": '{"symbols": ["AMES"], "is_contextual_followup": false}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    with patch.object(httpx.AsyncClient, "post", new=fake_post_hit), patch(
        "api.agentic_chat.pipeline._init_supabase"
    ), patch.object(pipeline, "supabase", SimpleNamespace()):
        done2 = None
        async for chunk in pipeline.run_agentic_chat_stream(
            message="حلل سهم AMES",
            history=fake_history,
            images=[],
            session_id="mt_2",
            user_id="11111111-1111-1111-1111-111111111111",
        ):
            line = chunk.strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                ev = json.loads(line[5:].strip())
                if ev.get("type") == "done":
                    done2 = ev

    assert hit_calls == 1  # Only Round 1 LLM call, ZERO Round 2 synthesis!
    assert done2 is not None
    assert done2["cached"] is True
    assert done2["cache_key"] == "vip_stock_AMES"

    # 3. Contextual follow-up flagged is_contextual_followup=True MUST bypass cache AND keep full history
    followup_synth_msgs = []
    f_call = 0

    async def fake_post_followup(self, url, *args, **kwargs):
        nonlocal f_call
        f_call += 1
        payload = kwargs.get("json", {})
        if f_call == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "tc_ames_3",
                                        "type": "function",
                                        "function": {
                                            "name": "get_stock",
                                            "arguments": '{"symbols": ["AMES"], "is_contextual_followup": true}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        followup_synth_msgs.append(payload.get("messages", []))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "سبب ارتفاع RSI إلى 91 هو الزخم المتسارع مقارنة بجلسة COMI."}}]},
        )

    with patch.object(httpx.AsyncClient, "post", new=fake_post_followup), patch(
        "api.agentic_chat.pipeline.dispatch_tool", side_effect=fake_dispatch
    ), patch("api.agentic_chat.pipeline._init_supabase"), patch.object(
        pipeline, "supabase", SimpleNamespace()
    ), patch("api.agentic_chat.pipeline.set_vip_analysis_cache") as mock_skip_set:
        done3 = None
        async for chunk in pipeline.run_agentic_chat_stream(
            message="ليه RSI بتاعه عالي أوي كده مقارنة باللي قبله؟",
            history=fake_history,
            images=[],
            session_id="mt_3",
            user_id="11111111-1111-1111-1111-111111111111",
        ):
            line = chunk.strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                ev = json.loads(line[5:].strip())
                if ev.get("type") == "done":
                    done3 = ev

    assert f_call == 2
    assert done3 is not None
    assert done3["cached"] is False
    assert done3["cache_key"] is None
    assert not mock_skip_set.called
    # Full history must remain intact in synthesis for contextual follow-up
    assert any("سؤال قديم عن COMI" in str(m.get("content", "")) for m in followup_synth_msgs[0])
