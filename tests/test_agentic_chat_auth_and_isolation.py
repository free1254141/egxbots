import base64
import json
import os
import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request

from api.agentic_chat.auth_guard import extract_jwt_token, get_authenticated_user
from api.agentic_chat.router import get_chat_root, delete_session, update_session


def build_mock_request(
    headers: dict = None,
    cookies: dict = None,
    query_params: dict = None,
    method: str = "GET",
    body: dict = None,
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()],
        "query_string": "&".join(f"{k}={v}" for k, v in (query_params or {}).items()).encode("latin-1") if query_params else b"",
    }
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        scope["headers"].append((b"cookie", cookie_header.encode("latin-1")))

    req = Request(scope)
    if body is not None:
        async def mock_json():
            return body
        req.json = mock_json
    return req


# ==========================================
# 1. Tests for extract_jwt_token
# ==========================================

def test_extract_jwt_token_from_bearer_header():
    req = build_mock_request(headers={"authorization": "Bearer my_super_jwt_token"})
    assert extract_jwt_token(req) == "my_super_jwt_token"


def test_extract_jwt_token_from_simple_cookie():
    req = build_mock_request(cookies={"sb-access-token": "cookie_access_jwt"})
    assert extract_jwt_token(req) == "cookie_access_jwt"


def test_extract_jwt_token_base64url_with_missing_padding():
    sample_payload = {"access_token": "token_inside_supabase_ssr_cookie", "refresh_token": "ref_123"}
    json_bytes = json.dumps(sample_payload).encode("utf-8")
    # Base64url encode without padding (like @supabase/ssr does)
    b64_unpadded = base64.urlsafe_b64encode(json_bytes).decode("ascii").rstrip("=")
    cookie_val = f"base64-{b64_unpadded}"

    req = build_mock_request(cookies={"sb-proj-auth-token": cookie_val})
    token = extract_jwt_token(req)
    assert token == "token_inside_supabase_ssr_cookie"


def test_extract_jwt_token_chunked_cookies():
    sample_payload = {"access_token": "chunked_token_xyz"}
    b64 = base64.urlsafe_b64encode(json.dumps(sample_payload).encode("utf-8")).decode("ascii").rstrip("=")
    cookie_val = f"base64-{b64}"
    mid = len(cookie_val) // 2

    req = build_mock_request(cookies={
        "sb-proj-auth-token.0": cookie_val[:mid],
        "sb-proj-auth-token.1": cookie_val[mid:],
    })
    token = extract_jwt_token(req)
    assert token == "chunked_token_xyz"


# ==========================================
# 2. Tests for Benchmark Guard & get_authenticated_user
# ==========================================

def test_benchmark_guard_disabled_by_default():
    # Benchmark disabled by default: headers MUST NOT bypass auth
    with patch.dict(os.environ, {}, clear=True):
        req = build_mock_request(headers={"x-benchmark-test": "true", "x-benchmark-key": "any_secret"})
        assert get_authenticated_user(req) is None


def test_benchmark_guard_enabled_with_secret():
    env = {
        "ALLOW_LOADTEST_BENCHMARK": "true",
        "BENCHMARK_SECRET_KEY": "super_secret_bench_key",
    }
    with patch.dict(os.environ, env, clear=True):
        # 1. Matching x-benchmark-key
        req1 = build_mock_request(headers={"x-benchmark-key": "super_secret_bench_key"})
        u1 = get_authenticated_user(req1)
        assert u1 is not None
        assert u1["is_benchmark"] is True
        assert u1["id"] == "00000000-0000-0000-0000-000000000000"

        # 2. Matching Bearer token
        req2 = build_mock_request(headers={"authorization": "Bearer super_secret_bench_key"})
        u2 = get_authenticated_user(req2)
        assert u2 is not None
        assert u2["is_benchmark"] is True

        # 3. Wrong key
        req3 = build_mock_request(headers={"x-benchmark-key": "wrong_key"})
        assert get_authenticated_user(req3) is None


def test_admin_secret_key_trusted_proxy():
    env = {"ADMIN_SECRET_KEY": "secret_admin_gateway"}
    with patch.dict(os.environ, env, clear=True):
        # Valid admin proxy
        req1 = build_mock_request(headers={
            "x-admin-key": "secret_admin_gateway",
            "x-user-id": "user_12345",
            "x-user-email": "user@example.com",
        })
        u1 = get_authenticated_user(req1)
        assert u1 is not None
        assert u1["id"] == "user_12345"
        assert u1["email"] == "user@example.com"

        # Invalid admin key
        req2 = build_mock_request(headers={
            "x-admin-key": "wrong_key",
            "x-user-id": "user_12345",
        })
        assert get_authenticated_user(req2) is None


# ==========================================
# 3. Tests for Router Session Isolation & Security
# ==========================================

@pytest.mark.anyio
async def test_get_sessions_unauthenticated_returns_empty():
    req = build_mock_request(query_params={"action": "sessions"})
    with patch("api.agentic_chat.router.get_authenticated_user", return_value=None):
        resp = await get_chat_root(req, action="sessions")
        body = json.loads(resp.body.decode())
        assert body["sessions"] == []
        assert body["remaining_quota"] == 10
        assert body["is_pro"] is False


@pytest.mark.anyio
async def test_get_sessions_authenticated_queries_by_user_id():
    req = build_mock_request(query_params={"action": "sessions"})
    mock_supabase = MagicMock()
    mock_supabase.from_.return_value.select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "sess_1", "title": "My Stock Query", "created_at": "2026-11-10T00:00:00Z", "updated_at": "2026-11-10T00:00:00Z"}
    ]

    with patch("api.agentic_chat.router.get_authenticated_user", return_value={"id": "user_abc", "is_authenticated": True}), \
         patch("api.agentic_chat.router.supabase", mock_supabase), \
         patch("api.agentic_chat.router.is_pro_user", return_value=True):
        resp = await get_chat_root(req, action="sessions")
        body = json.loads(resp.body.decode())
        assert len(body["sessions"]) == 1
        assert body["sessions"][0]["id"] == "sess_1"
        assert body["is_pro"] is True
        # Verify user_id filtering was strictly called
        mock_supabase.from_.return_value.select.return_value.eq.assert_called_with("user_id", "user_abc")


@pytest.mark.anyio
async def test_get_messages_unauthenticated_returns_empty():
    req = build_mock_request(query_params={"session_id": "sess_secret_123"})
    with patch("api.agentic_chat.router.get_authenticated_user", return_value=None):
        resp = await get_chat_root(req, session_id="sess_secret_123")
        body = json.loads(resp.body.decode())
        assert body["messages"] == []


@pytest.mark.anyio
async def test_delete_session_unauthenticated_returns_401():
    req = build_mock_request(method="DELETE", query_params={"session_id": "sess_123"})
    with patch("api.agentic_chat.router.get_authenticated_user", return_value=None):
        resp = await delete_session(req, session_id="sess_123")
        assert resp.status_code == 401
        body = json.loads(resp.body.decode())
        assert body["status"] == "error"
        assert body["message"] == "Unauthorized"


@pytest.mark.anyio
async def test_delete_session_authenticated_deletes_with_user_filter():
    req = build_mock_request(method="DELETE", query_params={"session_id": "sess_123"})
    mock_supabase = MagicMock()
    with patch("api.agentic_chat.router.get_authenticated_user", return_value={"id": "user_owner", "is_authenticated": True}), \
         patch("api.agentic_chat.router.supabase", mock_supabase):
        resp = await delete_session(req, session_id="sess_123")
        assert resp["status"] == "ok"
        assert resp["deleted"] == "sess_123"
        # Verify eq("user_id", "user_owner") was executed for soft-delete
        mock_supabase.from_.return_value.update.return_value.eq.return_value.eq.assert_called_with("user_id", "user_owner")


@pytest.mark.anyio
async def test_update_session_unauthenticated_returns_401():
    req = build_mock_request(method="PUT", body={"session_id": "sess_123", "title": "New Title"})
    with patch("api.agentic_chat.router.get_authenticated_user", return_value=None):
        resp = await update_session(req)
        assert resp.status_code == 401


@pytest.mark.anyio
async def test_update_session_authenticated_updates_with_user_filter():
    req = build_mock_request(method="PUT", body={"session_id": "sess_123", "title": "Renamed Title"})
    mock_supabase = MagicMock()
    with patch("api.agentic_chat.router.get_authenticated_user", return_value={"id": "user_owner", "is_authenticated": True}), \
         patch("api.agentic_chat.router.supabase", mock_supabase):
        resp = await update_session(req)
        assert resp["status"] == "ok"
        assert resp["updated"] == "sess_123"
        assert resp["title"] == "Renamed Title"
        mock_supabase.from_.return_value.update.return_value.eq.return_value.eq.assert_called_with("user_id", "user_owner")


# ==========================================
# 4. Tests for Egyptian Stock Hints & Resolution
# ==========================================

def test_known_symbol_hints_egyptian_stocks():
    from api.agentic_chat.pipeline import known_symbol_hints

    # 1. Test "عتاقه" / "عتاقة" resolves to ATQA
    hints_1 = known_symbol_hints("عتاقه")
    assert any("ATQA" in h["symbols"] for h in hints_1), f"Expected ATQA in hints: {hints_1}"

    hints_2 = known_symbol_hints("حلل سهم عتاقة")
    assert any("ATQA" in h["symbols"] for h in hints_2), f"Expected ATQA in hints: {hints_2}"

    # 2. Test multi-stock comparison
    hints_3 = known_symbol_hints("قارن بين التجاري الدولي وطلعت مصطفى")
    syms_3 = [s for h in hints_3 for s in h["symbols"]]
    assert "COMI" in syms_3
    assert "TMGH" in syms_3


def test_normalize_symbol_resolves_arabic_and_aliases():
    from api.agentic_chat.tools_execution import _normalize_symbol

    assert _normalize_symbol("عتاقه") == "ATQA"
    assert _normalize_symbol("عتاقة") == "ATQA"
    assert _normalize_symbol("ATQA.CA") == "ATQA"
    assert _normalize_symbol("فوري") == "FWRY"
    assert _normalize_symbol("comi") == "COMI"


@pytest.mark.anyio
async def test_get_session_history_camel_case_sessionId():
    req = build_mock_request(query_params={"sessionId": "sess_camel_123"})
    mock_supabase = MagicMock()
    mock_supabase.from_.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "msg_1",
                "role": "user",
                "content": "سهم عتاقه كام",
                "created_at": "2026-11-10T12:00:00Z",
                "image_url": None,
                "latency_ms": 120,
            }
        ]
    )

    with patch("api.agentic_chat.router.get_authenticated_user", return_value={"id": "user_owner", "is_authenticated": True}), \
         patch("api.agentic_chat.router.supabase", mock_supabase):
        resp = await get_chat_root(req)
        assert resp.status_code == 200
        body = json.loads(resp.body.decode())
        # Must return BOTH "history" and "messages" for frontend compatibility
        assert "history" in body
        assert "messages" in body
        assert len(body["history"]) == 1
        assert body["history"][0]["content"] == "سهم عتاقه كام"
        assert isinstance(body["history"][0]["timestamp"], int)


# ==========================================
# 6. Tests for Portfolio Management Fixes
# ==========================================

def test_manage_portfolio_requires_login():
    from api.agentic_chat.tools_execution import _sync_manage_portfolio
    res = _sync_manage_portfolio(user_id=None, operation="view")
    assert res.get("status") == "error"
    assert res.get("requires_login") is True


def test_manage_portfolio_anti_injection_blocks_unauthorized_mutation():
    from api.agentic_chat.tools_execution import _sync_manage_portfolio
    # Prompt without explicit write keywords
    res = _sync_manage_portfolio(
        user_id="user_123",
        operation="add",
        symbol="COMI",
        quantity=100,
        price=120.0,
        user_prompt="ما هو أفضل سهم للشراء اليوم؟",
    )
    assert res.get("status") == "blocked"


def test_manage_portfolio_view_from_positions_table():
    from api.agentic_chat.tools_execution import _sync_manage_portfolio

    mock_sb = MagicMock()

    # Mock positions table query
    positions_mock_query = MagicMock()
    positions_mock_query.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "p_1",
                "symbol": "COMI",
                "name": "البنك التجاري الدولي",
                "quantity": 100,
                "entry_price": 120.0,
                "status": "open",
                "added_at": "2026-11-10T10:00:00Z",
            }
        ]
    )

    # Mock profiles table for cash balance
    profiles_mock_query = MagicMock()
    profiles_mock_query.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"cash_balance": 5000.0}]
    )

    # Mock technical indicators for current price
    tech_mock_query = MagicMock()
    tech_mock_query.select.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"symbol": "COMI", "close": 125.0, "change_pct": 1.5, "date": "2026-11-10"}]
    )

    def from_side_effect(table_name):
        if table_name == "positions":
            return positions_mock_query
        elif table_name == "profiles":
            return profiles_mock_query
        elif table_name == "stock_technical_indicators":
            return tech_mock_query
        return MagicMock()

    mock_sb.from_.side_effect = from_side_effect

    with patch("api.agentic_chat.tools_execution._get_sb", return_value=mock_sb):
        res = _sync_manage_portfolio(user_id="user_123", operation="view")
        assert res.get("status") == "success"
        assert res.get("positions_count") == 1
        pos = res.get("positions")[0]
        assert pos["symbol"] == "COMI"
        assert pos["cost_basis"] == 12000.0
        assert pos["market_value"] == 12500.0
        assert pos["profit_value"] == 500.0
        assert round(pos["profit_pct"], 2) == 4.17
        assert res.get("cash_balance") == 5000.0
        assert res.get("totals")["equity"] == 17500.0


@pytest.mark.anyio
async def test_dispatch_tool_manage_portfolio_benchmark():
    from api.agentic_chat.tools_execution import dispatch_tool

    res = await dispatch_tool(
        tool_name="manage_portfolio",
        arguments={"operation": "view"},
        user_id="00000000-0000-0000-0000-000000000000",
    )
    assert res.get("status") == "success"
    assert res.get("positions_count") == 2
    assert res.get("totals")["equity"] == 105450.0


def test_persist_message_background_stores_latency_ms():
    from api.agentic_chat.router import _persist_message_background

    mock_supabase = MagicMock()
    inserted_rows = []

    def mock_insert(rows):
        inserted_rows.extend(rows)
        return MagicMock(execute=lambda: None)

    mock_supabase.from_.return_value.upsert.return_value.execute = MagicMock()
    mock_supabase.from_.return_value.insert = mock_insert

    with patch("api.agentic_chat.router.supabase", mock_supabase), \
         patch("api.agentic_chat.router._init_supabase", lambda: None):
        _persist_message_background(
            session_id="sess_test_latency",
            user_id="user_test_123",
            user_msg="سعر فوري كام",
            reply="سعر فوري 7.85 ج.م",
            latency_ms=5430,
        )

        assert len(inserted_rows) == 2
        user_row = [r for r in inserted_rows if r["role"] == "user"][0]
        asst_row = [r for r in inserted_rows if r["role"] == "assistant"][0]

        assert asst_row["latency_ms"] == 5430
        assert asst_row["metadata"]["latency_ms"] == 5430
        assert user_row["created_at"] < asst_row["created_at"]



