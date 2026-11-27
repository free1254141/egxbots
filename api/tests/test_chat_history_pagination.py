"""Offline unit tests for GET /api/ai-chat session message cursor pagination."""

import importlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeMessagesQuery:
    def __init__(self, rows):
        self._rows = list(rows)
        self._session_id = None
        self._user_id = None
        self._before = None
        self._desc = False
        self._limit = None
        self.recorded_calls = []

    def select(self, cols):
        self.recorded_calls.append(("select", cols))
        return self

    def eq(self, col, val):
        self.recorded_calls.append(("eq", col, val))
        if col == "session_id":
            self._session_id = val
        elif col == "user_id":
            self._user_id = val
        return self

    def lt(self, col, val):
        self.recorded_calls.append(("lt", col, val))
        if col == "created_at":
            self._before = val
        return self

    def order(self, col, desc=False):
        self.recorded_calls.append(("order", col, desc))
        self._desc = bool(desc)
        return self

    def limit(self, n):
        self.recorded_calls.append(("limit", n))
        self._limit = int(n)
        return self

    def execute(self):
        filtered = [
            r for r in self._rows
            if r["session_id"] == self._session_id and r["user_id"] == self._user_id
        ]
        if self._before is not None:
            filtered = [r for r in filtered if r["created_at"] < self._before]
        filtered.sort(key=lambda r: r["created_at"], reverse=self._desc)
        if self._limit is not None:
            filtered = filtered[: self._limit]
        return SimpleNamespace(data=filtered)


@pytest.fixture
def paginated_chat_client(monkeypatch):
    chat_router = importlib.import_module("api.agentic_chat.router")

    rows = [
        {
            "id": f"m-{i}",
            "session_id": "sess-1",
            "user_id": "user-1",
            "role": "user" if i % 2 == 1 else "assistant",
            "content": f"Message {i}",
            "image_url": None,
            "created_at": f"2026-11-27T00:{i:02d}:00+00:00",
            "latency_ms": 100 + i if i % 2 == 0 else None,
            "metadata": {},
        }
        for i in range(1, 11)
    ]

    queries = []

    class _FakeSupabase:
        def from_(self, table_name):
            assert table_name == "ai_chat_messages"
            q = _FakeMessagesQuery(rows)
            queries.append(q)
            return q

    monkeypatch.setattr(chat_router, "_init_supabase", lambda: None)
    monkeypatch.setattr(chat_router, "supabase", _FakeSupabase())
    monkeypatch.setattr(chat_router, "get_authenticated_user", lambda _req: {"id": "user-1"})
    monkeypatch.setattr(chat_router, "has_chat_pro_user", lambda _uid, _sb: True)

    test_app = FastAPI()
    test_app.include_router(chat_router.router, prefix="/api/ai-chat")
    client = TestClient(test_app)
    return client, queries


def test_get_chat_history_returns_latest_four_ascending_with_cursor(paginated_chat_client):
    client, queries = paginated_chat_client

    resp = client.get("/api/ai-chat?session_id=sess-1&limit=4")
    assert resp.status_code == 200
    body = resp.json()

    assert [m["id"] for m in body["history"]] == ["m-7", "m-8", "m-9", "m-10"]
    assert [m["content"] for m in body["messages"]] == ["Message 7", "Message 8", "Message 9", "Message 10"]
    assert body["has_more"] is True
    assert body["next_before"] == "2026-11-27T00:07:00+00:00"
    assert body["history"][0]["createdAt"] == "2026-11-27T00:07:00+00:00"

    # postgrest filter-before-order-before-limit contract
    calls = queries[-1].recorded_calls
    order_idx = next(i for i, c in enumerate(calls) if c[0] == "order")
    limit_idx = next(i for i, c in enumerate(calls) if c[0] == "limit")
    assert calls[order_idx] == ("order", "created_at", True)
    assert calls[limit_idx] == ("limit", 5)


def test_get_chat_history_before_cursor_fetches_older_page(paginated_chat_client):
    client, queries = paginated_chat_client

    resp1 = client.get("/api/ai-chat?session_id=sess-1&limit=4")
    cursor = resp1.json()["next_before"]

    resp2 = client.get(f"/api/ai-chat?session_id=sess-1&limit=6&before={cursor}")
    assert resp2.status_code == 200
    body2 = resp2.json()

    assert [m["id"] for m in body2["history"]] == ["m-1", "m-2", "m-3", "m-4", "m-5", "m-6"]
    assert body2["has_more"] is False
    assert body2["next_before"] is None

    calls = queries[-1].recorded_calls
    lt_idx = next(i for i, c in enumerate(calls) if c[0] == "lt")
    order_idx = next(i for i, c in enumerate(calls) if c[0] == "order")
    limit_idx = next(i for i, c in enumerate(calls) if c[0] == "limit")
    assert lt_idx < order_idx < limit_idx
    assert calls[limit_idx] == ("limit", 7)


def test_get_chat_history_epoch_ms_before_and_limit_clamping(paginated_chat_client):
    client, queries = paginated_chat_client

    # Limit clamped to 1..50; numeric epoch ms converted to UTC ISO
    resp = client.get("/api/ai-chat?session_id=sess-1&limit=999&before=1795738020000")
    assert resp.status_code == 200
    assert queries[-1]._limit == 51
