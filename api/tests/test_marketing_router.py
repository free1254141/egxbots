import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.marketing_lifecycle as ml
import api.routers.marketing as marketing_router


def _build_client(monkeypatch, fake_supabase=None):
    app = FastAPI()
    app.include_router(marketing_router.router)
    monkeypatch.setattr(marketing_router, "_get_supabase", lambda: fake_supabase)
    return TestClient(app)


def _sign_svix(body: str, svix_id: str, ts: str, secret: str) -> str:
    raw = base64.b64decode(secret[6:] if secret.startswith("whsec_") else secret)
    digest = hmac.new(raw, f"{svix_id}.{ts}.{body}".encode("utf-8"), hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode("ascii")


class _FakeQuery:
    def __init__(self, table_name, state):
        self.table_name = table_name
        self.state = state

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        self.state["inserted"].append((self.table_name, payload))
        return self

    def upsert(self, payload, on_conflict=None):
        self.state["upserted"].append((self.table_name, payload, on_conflict))
        return self

    def execute(self):
        if self.table_name == "marketing_message_log":
            return SimpleNamespace(data=self.state.get("log_rows", []))
        return SimpleNamespace(data=[])


class _FakeSupabase:
    def __init__(self, log_rows=None):
        self.state = {
            "log_rows": log_rows or [],
            "inserted": [],
            "upserted": [],
        }

    def table(self, name):
        return _FakeQuery(name, self.state)


def test_resend_webhook_status_reports_configuration(monkeypatch):
    secret = "whsec_dGVzdHNlY3JldDEyMzQ1Njc4OTA="
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", secret)
    client = _build_client(monkeypatch)

    res = client.get("/marketing/resend-webhook")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["configured"] is True
    assert body["backend"] == "huggingface"


def test_resend_webhook_rejects_missing_signature(monkeypatch):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", "whsec_dGVzdHNlY3JldDEyMzQ1Njc4OTA=")
    client = _build_client(monkeypatch, _FakeSupabase())

    res = client.post("/marketing/resend-webhook", content=json.dumps({"type": "email.opened"}))
    assert res.status_code == 401


def test_resend_webhook_tracks_signed_opened_event(monkeypatch):
    secret = "whsec_dGVzdHNlY3JldDEyMzQ1Njc4OTA="
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", secret)
    fake_db = _FakeSupabase(
        log_rows=[{"id": "log-uuid-1", "user_id": "user-uuid-1", "message_type": "founders_offer"}]
    )
    client = _build_client(monkeypatch, fake_db)

    payload = json.dumps({"type": "email.opened", "data": {"email_id": "resend-msg-123", "to": ["trader@example.com"]}})
    svix_id = "msg_test_123"
    svix_ts = str(int(time.time()))
    svix_sig = _sign_svix(payload, svix_id, svix_ts, secret)

    res = client.post(
        "/marketing/resend-webhook",
        content=payload,
        headers={"svix-id": svix_id, "svix-timestamp": svix_ts, "svix-signature": svix_sig},
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True, "tracked": "opened"}
    assert len(fake_db.state["inserted"]) == 1
    table, row = fake_db.state["inserted"][0]
    assert table == "marketing_events"
    assert row["event_type"] == "opened"
    assert row["campaign"] == "founders_offer"
    assert row["provider_message_id"] == "resend-msg-123"
    assert row["user_id"] == "user-uuid-1"
    assert row["svix_id"] == svix_id


def test_marketing_click_signed_redirect_records_event(monkeypatch):
    fake_db = _FakeSupabase(log_rows=[{"user_id": "user-uuid-2"}])
    client = _build_client(monkeypatch, fake_db)

    msg_uuid = "11111111-1111-1111-1111-111111111111"
    sig = ml._click_sig("email", "trial_expiring", msg_uuid, "/pricing")
    res = client.get(
        "/marketing/click",
        params={"ch": "email", "c": "trial_expiring", "m": msg_uuid, "to": "/pricing", "sig": sig},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert res.headers["location"].endswith("/pricing")
    assert len(fake_db.state["inserted"]) == 1
    assert fake_db.state["inserted"][0][1]["event_type"] == "clicked"
    assert fake_db.state["inserted"][0][1]["user_id"] == "user-uuid-2"


def test_marketing_click_rejects_bad_signature(monkeypatch):
    fake_db = _FakeSupabase()
    client = _build_client(monkeypatch, fake_db)

    res = client.get(
        "/marketing/click",
        params={"ch": "email", "c": "promo", "to": "https://evil.example", "sig": "bad"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert res.headers["location"] == "https://egxbots.com/"
    assert fake_db.state["inserted"] == []


def test_marketing_unsubscribe_upserts_and_renders_html(monkeypatch):
    fake_db = _FakeSupabase()
    client = _build_client(monkeypatch, fake_db)

    token = ml.generate_unsub_token("user-uuid-3", "user@example.com")
    res = client.get(
        "/marketing/unsubscribe",
        params={"uid": "user-uuid-3", "email": "user@example.com", "token": token},
    )
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "user@example.com" in res.text
    assert len(fake_db.state["upserted"]) == 1
    table, row, on_conflict = fake_db.state["upserted"][0]
    assert table == "marketing_preferences"
    assert row["user_id"] == "user-uuid-3"
    assert row["unsubscribed_all"] is True
    assert on_conflict == "user_id"


def test_resend_webhook_rejects_nan_timestamp(monkeypatch):
    secret = "whsec_dGVzdHNlY3JldDEyMzQ1Njc4OTA="
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", secret)
    client = _build_client(monkeypatch, _FakeSupabase())

    payload = json.dumps({"type": "email.opened", "data": {"email_id": "id-1"}})
    svix_id = "msg_nan"
    svix_sig = _sign_svix(payload, svix_id, "nan", secret)

    res = client.post(
        "/marketing/resend-webhook",
        content=payload,
        headers={"svix-id": svix_id, "svix-timestamp": "nan", "svix-signature": svix_sig},
    )
    assert res.status_code == 401


def test_get_supabase_returns_none_when_proxy_uninitialized(monkeypatch):
    app = FastAPI()
    app.include_router(marketing_router.router)

    class _EmptyProxy:
        def __bool__(self):
            return False

    monkeypatch.setattr(marketing_router.stock_ai, "supabase", _EmptyProxy())
    monkeypatch.setattr(marketing_router.stock_ai, "_init_supabase", lambda: None)

    assert marketing_router._get_supabase() is None

    secret = "whsec_dGVzdHNlY3JldDEyMzQ1Njc4OTA="
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", secret)
    payload = json.dumps({"type": "email.opened", "data": {"email_id": "id-1"}})
    svix_id = "msg_503"
    svix_ts = str(int(time.time()))
    svix_sig = _sign_svix(payload, svix_id, svix_ts, secret)

    client = TestClient(app)
    res = client.post(
        "/marketing/resend-webhook",
        content=payload,
        headers={"svix-id": svix_id, "svix-timestamp": svix_ts, "svix-signature": svix_sig},
    )
    assert res.status_code == 503

