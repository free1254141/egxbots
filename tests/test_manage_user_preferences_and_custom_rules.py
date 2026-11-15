"""
tests/test_manage_user_preferences_and_custom_rules.py
Unit tests for per-user custom AI rules and manage_user_preferences standing preferences.
"""

import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
import pytest

from api.agentic_chat import user_preferences
from api.agentic_chat import tools_execution
from api.agentic_chat import tools_schema
from api.agentic_chat import pipeline
chat_router_module = importlib.import_module("api.agentic_chat.router")


# ---------------------------------------------------------------------------
# 1. user_preferences helper functions tests
# ---------------------------------------------------------------------------

def test_user_rules_list_and_merge():
    # Empty
    assert user_preferences.user_rules_list("") == []
    assert user_preferences.user_rules_list(None) == []

    # Merge new rule
    r1 = user_preferences.merge_user_rule("", "التعامل بالأسهم المتوافقة مع الشريعة فقط")
    assert r1 == "- التعامل بالأسهم المتوافقة مع الشريعة فقط"

    # Merge second rule
    r2 = user_preferences.merge_user_rule(r1, "أنا مضارب لحظي ركز على فريم 15 دقيقة")
    assert "- التعامل بالأسهم المتوافقة مع الشريعة فقط" in r2
    assert "- أنا مضارب لحظي ركز على فريم 15 دقيقة" in r2

    # Duplicate rule is ignored
    r3 = user_preferences.merge_user_rule(r2, "التعامل بالأسهم المتوافقة مع الشريعة فقط")
    assert r3 == r2


def test_remove_user_rule():
    existing = "- التعامل بالأسهم المتوافقة مع الشريعة فقط\n- أنا مضارب لحظي\n- لا ترشح أسهم قطاع العقارات"
    res, removed = user_preferences.remove_user_rule(existing, "عقارات")
    assert removed is True
    assert "عقارات" not in res
    assert "الشريعة" in res
    assert "مضارب" in res

    # Non-existent rule
    res2, removed2 = user_preferences.remove_user_rule(existing, "ذهب")
    assert removed2 is False
    assert res2 == existing


def test_replace_user_rules():
    new_rules = ["التداول في EGX فقط", "التركيز على وقف الخسارة"]
    replaced = user_preferences.replace_user_rules(new_rules)
    assert replaced == "- التداول في EGX فقط\n- التركيز على وقف الخسارة"


def test_is_sharia_preference_and_tool_args_enforcement():
    assert user_preferences.is_sharia_preference("- أسهم شرعية فقط") is True
    assert user_preferences.is_sharia_preference("- التعامل وفق أحكام الشريعة الإسلامية") is True
    assert user_preferences.is_sharia_preference("- أسهم حلال فقط") is True
    assert user_preferences.is_sharia_preference("- مؤشر EGX 33") is True
    assert user_preferences.is_sharia_preference("- مضاربة لحظية سريعة") is False
    assert user_preferences.is_sharia_preference(None) is False

    # Apply to recommendation tool
    recs_args = {"timeframe": "open"}
    enforced = user_preferences.apply_user_rules_to_tool_args(
        "get_recommendations", recs_args, "- أسهم شرعية فقط"
    )
    assert enforced["sharia_only"] is True

    # Do not affect non-filter tools
    stock_args = {"symbols": ["COMI"]}
    not_enforced = user_preferences.apply_user_rules_to_tool_args(
        "get_stock", stock_args, "- أسهم شرعية فقط"
    )
    assert "sharia_only" not in not_enforced


def test_build_user_rules_prompt():
    prompt = user_preferences.build_user_rules_prompt("- الالتزام بالشريعة")
    assert "ذاكرة المستخدم الدائمة" in prompt
    assert "- الالتزام بالشريعة" in prompt
    assert "sharia_only=true" in prompt

    assert user_preferences.build_user_rules_prompt("") == ""
    assert user_preferences.build_user_rules_prompt(None) == ""


# ---------------------------------------------------------------------------
# 2. Schema verification
# ---------------------------------------------------------------------------

def test_manage_user_preferences_schema_registered():
    tool_names = [t["function"]["name"] for t in tools_schema.AGENTIC_TOOLS_SCHEMA]
    assert "manage_user_preferences" in tool_names


# ---------------------------------------------------------------------------
# 3. Execution tests (add, get, delete, replace, unauthenticated)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_execute_manage_user_preferences_unauthenticated():
    res = await tools_execution.execute_manage_user_preferences(
        user_id="00000000-0000-0000-0000-000000000000",
        operation="add",
        rule="تداول شرعي فقط",
    )
    assert res["status"] == "unauthenticated"


@pytest.mark.anyio
async def test_execute_manage_user_preferences_crud():
    fake_db = {"rules": None}

    class FakeTable:
        def __init__(self, name):
            self.name = name

        def select(self, cols):
            return self

        def eq(self, col, val):
            return self

        def limit(self, n):
            return self

        def update(self, data):
            fake_db["rules"] = data.get("custom_ai_rules")
            return self

        def execute(self):
            return SimpleNamespace(data=[{"custom_ai_rules": fake_db["rules"]}])

    fake_supabase = SimpleNamespace(table=lambda name: FakeTable(name))

    with patch.object(tools_execution, "_init_supabase"), patch.object(
        tools_execution, "supabase", fake_supabase
    ):
        # 1. Add rule
        res_add = await tools_execution.execute_manage_user_preferences(
            user_id="user_123",
            operation="add",
            rule="التعامل بالأسهم الشرعية فقط",
        )
        assert res_add["status"] == "success"
        assert res_add["saved"] is True
        assert "- التعامل بالأسهم الشرعية فقط" in res_add["rules"]
        assert fake_db["rules"] == "- التعامل بالأسهم الشرعية فقط"

        # 2. Get rules
        res_get = await tools_execution.execute_manage_user_preferences(
            user_id="user_123",
            operation="get",
        )
        assert res_get["status"] == "success"
        assert "- التعامل بالأسهم الشرعية فقط" in res_get["rules"]

        # 3. Add second rule
        res_add2 = await tools_execution.execute_manage_user_preferences(
            user_id="user_123",
            operation="add",
            rule="أنا مستثمر متوسط الأجل",
        )
        assert res_add2["saved"] is True
        assert "- أنا مستثمر متوسط الأجل" in res_add2["rules"]

        # 4. Delete first rule
        res_del = await tools_execution.execute_manage_user_preferences(
            user_id="user_123",
            operation="delete",
            rule="الشرعية",
        )
        assert res_del["status"] == "success"
        assert res_del["saved"] is True
        assert "الشرعية" not in res_del["rules"]
        assert "متوسط الأجل" in res_del["rules"]

        # 5. Replace rules
        res_rep = await tools_execution.execute_manage_user_preferences(
            user_id="user_123",
            operation="replace",
            rules=["قاعدة جديدة وحيدة"],
        )
        assert res_rep["status"] == "success"
        assert res_rep["rules"] == "- قاعدة جديدة وحيدة"

        # 6. Dispatcher executes cleanly
        res_disp = await tools_execution.dispatch_tool(
            "manage_user_preferences",
            {"operation": "get"},
            user_id="user_123",
        )
        assert res_disp["status"] == "success"


# ---------------------------------------------------------------------------
# 4. Pipeline integration: prompt injection, sharia tool enforcement & cache bypass
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_pipeline_injects_user_rules_and_enforces_sharia(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test_key")

    captured_payloads = []

    async def fake_post(self, url, *args, **kwargs):
        payload = kwargs.get("json", {})
        captured_payloads.append(payload)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "تقرير التوصيات الشرعية المعتمدة للمستخدم.",
                        }
                    }
                ]
            },
        )

    dispatched_args = {}

    async def fake_dispatch(tool_name, arguments, **kwargs):
        dispatched_args[tool_name] = arguments
        return {"status": "success"}

    class FakeProfileTable:
        def select(self, cols):
            return self

        def eq(self, col, val):
            return self

        def limit(self, n):
            return self

        def execute(self):
            return SimpleNamespace(data=[{"custom_ai_rules": "- أسهم شرعية متوافقة مع الشريعة فقط"}])

    fake_sb = SimpleNamespace(table=lambda name: FakeProfileTable())

    with patch.object(httpx.AsyncClient, "post", new=fake_post), patch.object(
        pipeline, "dispatch_tool", side_effect=fake_dispatch
    ), patch.object(pipeline, "_init_supabase"), patch.object(
        pipeline, "supabase", fake_sb
    ):
        events = []
        async for chunk in pipeline.run_agentic_chat_stream(
            message="رشح لي أفضل فرص السوق اليوم",
            history=[],
            images=[],
            session_id="test_user_rules_sess",
            user_id="user_sharia_123",
        ):
            s = chunk.strip()
            if s.startswith("data:") and s[5:].strip() != "[DONE]":
                events.append(json.loads(s[5:].strip()))

        # Verify prompt injection
        assert len(captured_payloads) >= 1
        system_msgs = [
            m["content"]
            for m in captured_payloads[0].get("messages", [])
            if m.get("role") == "system" and isinstance(m.get("content"), str)
        ]
        assert any("ذاكرة المستخدم الدائمة" in sm for sm in system_msgs)
        assert any("أسهم شرعية" in sm for sm in system_msgs)

        # Done event must not be served from public cache
        done_ev = next((e for e in events if e.get("type") == "done"), None)
        assert done_ev is not None
        assert done_ev["cached"] is False


# ---------------------------------------------------------------------------
# 5. Router action=settings and PUT update tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_router_settings_and_put_custom_rules():
    fake_profile = {"custom_ai_rules": "- قاعدة مسجلة"}

    class FakeTable:
        def select(self, cols):
            return self

        def eq(self, col, val):
            return self

        def limit(self, n):
            return self

        def update(self, data):
            fake_profile["custom_ai_rules"] = data.get("custom_ai_rules")
            return self

        def execute(self):
            return SimpleNamespace(data=[fake_profile])

    fake_sb = SimpleNamespace(
        from_=lambda name: FakeTable(),
        table=lambda name: FakeTable(),
    )

    fake_request = SimpleNamespace(
        query_params={"action": "settings"},
        headers={},
        cookies={},
    )

    with patch.object(chat_router_module, "_init_supabase"), patch.object(
        chat_router_module, "supabase", fake_sb
    ), patch.object(
        chat_router_module, "get_authenticated_user", return_value={"id": "user_456"}
    ), patch.object(
        chat_router_module, "get_user_chat_quota", return_value=(0, 350, 350)
    ):
        # 1. GET settings returns custom_ai_rules
        resp = await chat_router_module.get_chat_root(request=fake_request, action="settings")
        data = json.loads(resp.body.decode("utf-8"))
        assert data["status"] == "ok"
        assert data["custom_ai_rules"] == "- قاعدة مسجلة"

        # 2. PUT updates custom_ai_rules
        async def fake_json():
            return {"custom_ai_rules": "- قاعدة جديدة محدثة"}

        put_request = SimpleNamespace(json=fake_json)
        resp_put = await chat_router_module.update_session(request=put_request)
        assert resp_put["status"] == "ok"
        assert resp_put["custom_ai_rules"] == "- قاعدة جديدة محدثة"
        assert fake_profile["custom_ai_rules"] == "- قاعدة جديدة محدثة"
