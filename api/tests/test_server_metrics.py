from __future__ import annotations

import os
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.perf_utils import BoundedTTLCache, ServerMetrics, get_all_cache_stats
from api.routers import admin as admin_router
import api.stock_ai as stock_ai


def test_server_metrics_tracks_requests_and_latencies():
    m = ServerMetrics(latency_window=10)
    m.enter_request()
    m.enter_request()
    snap = m.snapshot()
    assert snap["requests"]["in_flight"] == 2

    m.record_request(200, 0.010)
    m.record_request(404, 0.020)
    m.enter_request()
    m.record_request(500, 0.100)

    snap = m.snapshot()
    req = snap["requests"]
    assert req["in_flight"] == 0
    assert req["total"] == 3
    assert req["status_2xx"] == 1
    assert req["status_4xx"] == 1
    assert req["status_5xx"] == 1
    assert req["max_latency_ms"] == 100.0
    assert req["p95_latency_ms"] == 100.0
    assert snap["system"]["cpu_count"] >= 1
    assert snap["system"]["threads"] >= 1


def test_cache_registry_aggregates_stats():
    c = BoundedTTLCache(max_entries=10, default_ttl=60.0)
    c.set("k1", "v1")
    hit, val = c.get("k1")
    assert hit is True and val == "v1"
    miss, _ = c.get("missing")
    assert miss is False

    stats = get_all_cache_stats()
    assert stats["total_caches"] >= 1
    assert stats["total_hits"] >= 1
    assert stats["total_misses"] >= 1


def test_admin_server_metrics_requires_admin_key():
    app = FastAPI()
    app.include_router(admin_router.router)
    client = TestClient(app)

    with mock.patch.dict(os.environ, {"ADMIN_SECRET_KEY": "test-secret-key"}, clear=False):
        denied = client.get("/admin/server-metrics")
        assert denied.status_code == 403

        wrong = client.get("/admin/server-metrics", headers={"x-admin-key": "wrong"})
        assert wrong.status_code == 403

        ok = client.get("/admin/server-metrics", headers={"x-admin-key": "test-secret-key"})
        assert ok.status_code == 200
        assert ok.headers.get("cache-control") == "private, no-store, max-age=0"
        body = ok.json()
        assert "uptime_seconds" in body
        assert "requests" in body
        assert "system" in body
        assert "caches" in body


def test_init_supabase_logs_once_per_process(capsys):
    stock_ai._supabase_init_logged = False
    fake_client = object()

    with mock.patch.dict(
        os.environ,
        {"NEXT_PUBLIC_SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "key"},
        clear=False,
    ), mock.patch.object(stock_ai, "create_client", return_value=fake_client):
        stock_ai._set_thread_local_supabase(None)
        stock_ai._init_supabase(force=True)
        stock_ai._set_thread_local_supabase(None)
        stock_ai._init_supabase(force=True)

    captured = capsys.readouterr().out
    assert captured.count("DEBUG: Init Supabase.") == 1
    assert captured.count("DEBUG: Supabase client initialized successfully") == 1
