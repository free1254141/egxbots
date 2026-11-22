from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import cache_invalidation as ci
from api import daily_bot_run
from api.routers import offload_public


class _FakeQuery:
    def __init__(self, table_name: str, rows_by_table: dict, recorded_selects: list):
        self._table = table_name
        self._rows_by_table = rows_by_table
        self._recorded_selects = recorded_selects
        self._limit = None
        self._want_count = False

    def select(self, cols: str, count: str | None = None):
        self._recorded_selects.append((self._table, cols))
        self._want_count = count == "exact"
        return self

    def order(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def execute(self):
        rows = list(self._rows_by_table.get(self._table, []))
        total = len(rows)
        if self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=rows, count=total if self._want_count else None)


class _FakeSupabase:
    def __init__(self, rows_by_table: dict):
        self.rows_by_table = rows_by_table
        self.recorded_selects = []

    def table(self, name: str):
        return _FakeQuery(name, self.rows_by_table, self.recorded_selects)


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(offload_public.router)
    return TestClient(app)


def test_disclosures_page_data_excludes_raw_content_and_caches():
    offload_public._DISCLOSURES_PAGE_CACHE.clear()
    fake_sb = _FakeSupabase(
        {
            "egx_disclosures": [
                {
                    "id": "d1",
                    "symbol": "COMI",
                    "company_name": "CIB",
                    "disclosure_type": "insiders",
                    "disclosure_date": "2026-11-22",
                    "title": "Insider buy",
                    "ai_summary": "Bought shares",
                    "sentiment": "bullish",
                    "action_type": "buy",
                    "shares_count": 1000,
                    "stake_before": None,
                    "stake_after": 5.2,
                    "party_name": "Board",
                    "party_role": "Director",
                    "source_url": "https://example.com/d1.pdf",
                    "metadata": {},
                }
            ],
            "stock_technical_indicators": [{"symbol": "comi", "close": 100.0, "change_pct": 1.5}],
            "stock_fundamentals": [{"symbol": "COMI", "data": {"marketCap": 1000000}}],
        }
    )
    client = _make_client()

    with mock.patch("api.routers.offload_public.get_primary_supabase", return_value=fake_sb):
        r1 = client.get("/api/public/disclosures-page-data")
        r2 = client.get("/api/public/disclosures-page-data")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.headers.get("vercel-cache-tag") == "daily-disclosures"
    body = r1.json()
    assert body["stats"] == {"total": 1, "buys": 1, "sells": 0, "shareholding": 1}
    assert body["priceMap"]["COMI"] == {
        "close": 100.0,
        "change_pct": 1.5,
        "market_cap": 1000000,
        "total_shares": 10000,
    }
    # Verify raw_content is never selected and cache served second call
    for table, cols in fake_sb.recorded_selects:
        if table == "egx_disclosures":
            assert "raw_content" not in cols
    assert len(fake_sb.recorded_selects) == 4

    cleared = ci.invalidate_local_hf_caches(["daily-disclosures"])
    assert "disclosures_page" in cleared


def test_gcc_metals_directory_merges_indicators_and_caches():
    offload_public._GCC_METALS_DIR_CACHE.clear()
    fake_sb = _FakeSupabase(
        {
            "stocks": [
                {
                    "symbol": "EMAAR",
                    "exchange": "DFM",
                    "name": "Emaar Properties",
                    "name_ar": "إعمار العقارية",
                    "sector": "Real Estate",
                    "currency": "AED",
                    "updated_at": "2026-11-22T00:00:00Z",
                }
            ],
            "stock_technical_indicators": [
                {
                    "symbol": "EMAAR",
                    "exchange": "DFM",
                    "close": 9.5,
                    "change_pct": 2.1,
                    "rsi_14": 58.4,
                    "date": "2026-11-22T00:00:00Z",
                }
            ],
        }
    )
    client = _make_client()

    with mock.patch("api.routers.offload_public.get_market_supabase", return_value=fake_sb):
        r1 = client.get("/api/public/gcc-metals-directory")
        r2 = client.get("/api/public/gcc-metals-directory")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.headers.get("vercel-cache-tag") == "daily-symbols"
    stocks = r1.json()["stocks"]
    assert len(stocks) == 1
    assert stocks[0]["symbol"] == "EMAAR"
    assert stocks[0]["close"] == 9.5
    assert stocks[0]["rsi14"] == 58.4
    assert stocks[0]["priceDate"] == "2026-11-22"
    assert len(fake_sb.recorded_selects) == 2

    cleared = ci.invalidate_local_hf_caches(["daily-symbols"])
    assert "gcc_metals_dir" in cleared


def test_default_cooldown_is_900_and_recommendation_reval_uses_cache_invalidation():
    ci.reset_revalidation_cooldown()
    with mock.patch.dict(os.environ, {"REVALIDATE_COOLDOWN_SECONDS": ""}, clear=False):
        assert ci._cooldown_seconds() == 900.0

    with mock.patch("api.cache_invalidation.invalidate_cache_tags", return_value={"invalidated": ["daily-recommendations"], "status": 200}) as inv:
        ok = daily_bot_run._revalidate_recommendation_cache()
    assert ok is True
    inv.assert_called_once_with([ci.TAG_RECOMMENDATIONS], timeout=45.0)
