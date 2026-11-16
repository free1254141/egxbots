import importlib
import types
import pytest
from fastapi.testclient import TestClient

from api.agentic_chat import auth_guard
chat_router_mod = importlib.import_module("api.agentic_chat.router")


class _FakeQuery:
    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self._filters = []
        self._mode = "select"

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, val):
        self._filters.append(lambda r: str(r.get(col)) == str(val))
        return self

    def neq(self, col, val):
        self._filters.append(lambda r: str(r.get(col)) != str(val))
        return self

    def in_(self, col, vals):
        allowed = {str(v) for v in vals}
        self._filters.append(lambda r: str(r.get(col)) in allowed)
        return self

    def gte(self, col, val):
        self._filters.append(lambda r: str(r.get(col) or "") >= str(val))
        return self

    def lt(self, col, val):
        self._filters.append(lambda r: str(r.get(col) or "") < str(val))
        return self

    def contains(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def maybe_single(self):
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def execute(self):
        matched = [r for r in self._rows if all(fn(r) for fn in self._filters)]
        if self._mode == "delete":
            return types.SimpleNamespace(data=matched)
        return types.SimpleNamespace(data=matched)


class _FakeSupabase:
    def __init__(self, tables=None, bonus_credits=10):
        self.tables = tables or {}
        self.bonus_credits = bonus_credits
        self.rpc_calls = []

    def table(self, name):
        return _FakeQuery(self.tables.get(name, []))

    def from_(self, name):
        return self.table(name)

    def rpc(self, fn_name, params=None):
        self.rpc_calls.append((fn_name, params or {}))
        if fn_name == "consume_ai_chat_quota":
            p_limit = int((params or {}).get("p_limit", 0))
            if p_limit <= 0:
                return _FakeRpcResult([{"allowed": False, "chat_count": 0}])
            return _FakeRpcResult([{"allowed": True, "chat_count": 1}])
        if fn_name == "consume_chat_bonus":
            if self.bonus_credits > 0:
                self.bonus_credits -= 1
                return _FakeRpcResult({"allowed": True, "source": "telegram_link", "remaining_in_bucket": self.bonus_credits})
            return _FakeRpcResult({"allowed": False})
        if fn_name == "get_chat_bonus_balance":
            return _FakeRpcResult(self.bonus_credits)
        return _FakeRpcResult(None)


class _FakeRpcResult:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return types.SimpleNamespace(data=self._data)


def test_monthly_quota_exhausted_on_prior_days_consumes_bonus_and_skips_insert(monkeypatch):
    fake_sb = _FakeSupabase(
        tables={
            "ai_chatbot_limits": [
                {"user_id": "u-free", "date": "2026-11-10", "chat_count": 6},
                {"user_id": "u-free", "date": "2026-11-13", "chat_count": 4},
            ]
        },
        bonus_credits=10,
    )
    monkeypatch.setattr(auth_guard, "supabase", fake_sb)
    monkeypatch.setattr(auth_guard, "_init_supabase", lambda: None)
    monkeypatch.setattr(auth_guard, "is_payments_enabled", lambda: True)
    monkeypatch.setattr(auth_guard, "get_cairo_date_string", lambda: "2026-11-16")

    allowed, remaining, limit, err = auth_guard.check_and_consume_quota("u-free", is_pro=False)

    assert allowed is True
    assert remaining == 9
    assert limit == 10
    assert err == ""
    called_rpcs = [name for name, _ in fake_sb.rpc_calls]
    assert "consume_ai_chat_quota" not in called_rpcs
    assert "consume_chat_bonus" in called_rpcs
    assert fake_sb.bonus_credits == 9


def test_quota_exhausted_without_bonus_shows_200_egp_when_founders_closed(monkeypatch):
    fake_sb = _FakeSupabase(
        tables={
            "ai_chatbot_limits": [
                {"user_id": "u-free", "date": "2026-11-05", "chat_count": 10},
            ]
        },
        bonus_credits=0,
    )
    monkeypatch.setattr(auth_guard, "supabase", fake_sb)
    monkeypatch.setattr(auth_guard, "_init_supabase", lambda: None)
    monkeypatch.setattr(auth_guard, "is_payments_enabled", lambda: True)
    monkeypatch.setattr(auth_guard, "get_cairo_date_string", lambda: "2026-11-16")
    monkeypatch.setattr(auth_guard, "founders_offer_is_open", lambda: False)
    monkeypatch.setattr(auth_guard, "plan_amount_egp", lambda _pid: 200)

    allowed, remaining, limit, err = auth_guard.check_and_consume_quota("u-free", is_pro=False)

    assert allowed is False
    assert remaining == 0
    assert limit == 10
    assert "200 ج.م" in err
    assert "100 ج.م" not in err


def test_get_user_chat_quota_counts_full_month_and_bonus_for_free(monkeypatch):
    fake_sb = _FakeSupabase(
        tables={
            "ai_chatbot_limits": [
                {"user_id": "u-free", "date": "2026-11-02", "chat_count": 7},
                {"user_id": "u-free", "date": "2026-11-16", "chat_count": 1},
            ]
        },
        bonus_credits=6,
    )
    monkeypatch.setattr(auth_guard, "supabase", fake_sb)
    monkeypatch.setattr(auth_guard, "_init_supabase", lambda: None)
    monkeypatch.setattr(auth_guard, "get_cairo_date_string", lambda: "2026-11-16")

    used, remaining, limit = auth_guard.get_user_chat_quota("u-free", is_pro=False)

    assert used == 8
    assert remaining == 8  # 2 base + 6 bonus
    assert limit == 10


def test_router_rejects_unauthenticated_user_id_override_by_default(monkeypatch):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(chat_router_mod.router, prefix="/api/ai-chat")
    client = TestClient(app)

    monkeypatch.delenv("ALLOW_DEV_USER_ID_OVERRIDE", raising=False)
    monkeypatch.setattr(chat_router_mod, "get_authenticated_user", lambda _req: None)

    resp = client.post(
        "/api/ai-chat",
        json={"message": "حلل سهم COMI", "user_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 401


def test_mid_month_quota_passes_single_subtracted_today_cap(monkeypatch):
    fake_sb = _FakeSupabase(
        tables={
            "ai_chatbot_limits": [
                {"user_id": "u-free", "date": "2026-11-08", "chat_count": 5},
            ]
        },
        bonus_credits=10,
    )
    monkeypatch.setattr(auth_guard, "supabase", fake_sb)
    monkeypatch.setattr(auth_guard, "_init_supabase", lambda: None)
    monkeypatch.setattr(auth_guard, "is_payments_enabled", lambda: True)
    monkeypatch.setattr(auth_guard, "get_cairo_date_string", lambda: "2026-11-16")

    allowed, remaining, limit, err = auth_guard.check_and_consume_quota("u-free", is_pro=False)

    assert allowed is True
    assert err == ""
    consume_calls = [p for name, p in fake_sb.rpc_calls if name == "consume_ai_chat_quota"]
    assert len(consume_calls) == 1
    assert consume_calls[0]["p_limit"] == 5


def test_founders_offer_defaults_closed_when_settings_empty(monkeypatch):
    from api import payment_common

    monkeypatch.setattr(payment_common, "billing_settings", lambda: {})
    monkeypatch.delenv("FOUNDERS_OFFER_ENDS_AT", raising=False)
    assert payment_common.founders_offer_is_open() is False


def test_free_quota_never_resets_next_month(monkeypatch):
    fake_sb = _FakeSupabase(
        tables={
            "ai_chatbot_limits": [
                {"user_id": "u-free", "date": "2026-09-20", "chat_count": 6},
                {"user_id": "u-free", "date": "2026-10-05", "chat_count": 4},
            ]
        },
        bonus_credits=2,
    )
    monkeypatch.setattr(auth_guard, "supabase", fake_sb)
    monkeypatch.setattr(auth_guard, "_init_supabase", lambda: None)
    monkeypatch.setattr(auth_guard, "is_payments_enabled", lambda: True)
    monkeypatch.setattr(auth_guard, "get_cairo_date_string", lambda: "2026-11-16")

    used, remaining, limit = auth_guard.get_user_chat_quota("u-free", is_pro=False)
    assert used == 10
    assert limit == 10
    assert remaining == 2  # only the 2 bonus credits remain; base 10 did NOT renew in Nov

    allowed, rem_after, _lim, err = auth_guard.check_and_consume_quota("u-free", is_pro=False)
    assert allowed is True
    assert err == ""
    assert rem_after == 1
    assert [n for n, _ in fake_sb.rpc_calls if n == "consume_ai_chat_quota"] == []
    assert [n for n, _ in fake_sb.rpc_calls if n == "consume_chat_bonus"] == ["consume_chat_bonus"]


def test_offload_user_quota_free_reports_lifetime_across_months():
    from unittest import mock
    from api.tests import test_offload_router as tor

    tor._reset_all_caches()
    sb_free = tor._FakeSupabase(
        tables={
            "subscriptions": [],
            "ai_chatbot_limits": [
                {"user_id": "u-free", "date": "2026-09-20", "chat_count": 6},
                {"user_id": "u-free", "date": "2026-10-05", "chat_count": 4},
            ],
            "positions": [],
            "subscription_trials": [],
            "profiles": [],
            "local_payment_orders": [],
            "founders_offer_members": [],
        },
        bonus_balance=4,
    )
    client = tor._make_client()
    with mock.patch(
        "api.routers.offload.resolve_verified_viewer",
        return_value={"authenticated": True, "pro": False, "user_id": "u-free", "email": "f@x.y", "email_confirmed": True},
    ), mock.patch("api.routers.offload.get_primary_supabase", return_value=sb_free), mock.patch(
        "api.routers.offload.is_payments_enabled", return_value=True
    ), mock.patch("api.plan_limits.is_payments_enabled", return_value=True):
        resp = client.get("/api/user/quota")
    assert resp.status_code == 200
    chat = resp.json()["quota"]["chat_messages"]
    assert chat["used"] == 10
    assert chat["limit"] == 10
    assert chat["bonus_credits"] == 4
    assert chat["remaining"] == 4
    assert chat["period"] == "lifetime"


def test_telegram_vip_chat_renders_lifetime_period_and_200_egp_when_founders_closed(monkeypatch):
    from api import payment_common as pc
    from api import telegram_vip_chat as tvc

    monkeypatch.setattr(pc, "founders_offer_is_open", lambda: False)
    monkeypatch.setattr(pc, "plan_amount_egp", lambda plan_id, user_id=None: 200.0)

    reply_html = tvc.format_pipeline_reply_for_telegram(
        "تحليل ممتاز", [], "Ahmed", 12345, False, 3, 10, 7, "lifetime"
    )
    assert "إجمالي — مرة واحدة" in reply_html
    assert "اليوم):" not in reply_html

    dialog_html = tvc.build_pricing_dialog_html("Ahmed", 12345, reason="limit_reached", used=10, limit=10)
    assert "200 ج.م شهرياً" in dialog_html
    assert "عرض المؤسسين" not in dialog_html
    assert "10 رسائل مجانية لمرة واحدة لكل إيميل" in dialog_html

    cta_line = pc.format_pro_cta_sentence(is_html=True)
    assert "200 ج.م شهرياً" in cta_line
    assert "عرض المؤسسين" not in cta_line

    calls = []
    monkeypatch.setattr(tvc, "_call_telegram_api", lambda *a, **k: calls.append(a) or {"ok": True})
    monkeypatch.setattr(
        tvc,
        "call_web_vip_chat_api",
        lambda *a, **k: {"ok": True, "linked": True, "is_pro": False, "used": 3, "limit": 10, "remaining": 7, "period": "lifetime"},
    )
    handled = tvc.handle_vip_chat_update(
        {
            "callback_query": {
                "id": "cb_q",
                "data": "vip_my_quota",
                "from": {"id": 12345, "first_name": "Ahmed"},
                "message": {"message_id": 9, "chat": {"id": -1002083067817, "type": "supergroup"}, "message_thread_id": 1680},
            }
        },
        "TEST_TOKEN",
    )
    assert handled is True
    assert len(calls) == 1
    alert_txt = calls[0][2]["text"]
    assert "إجمالي — مرة واحدة" in alert_txt
    assert "3 من 10" in alert_txt
    assert "(اليوم)" not in alert_txt

    for price, is_open in [(200.0, False), (100.0, True)]:
        monkeypatch.setattr(pc, "founders_offer_is_open", lambda open_flag=is_open: open_flag)
        monkeypatch.setattr(pc, "plan_amount_egp", lambda plan_id, user_id=None, p=price: p)
        assert len(tvc._limit_reached_alert_text()) <= 199
        assert len(tvc._pro_only_tool_alert_text()) <= 199
        assert len(tvc._pricing_features_alert_text()) <= 199




