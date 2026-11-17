"""Unit tests for manage_portfolio cash operations and watchlist-only positions."""
from types import SimpleNamespace
from unittest.mock import patch

from api.agentic_chat.tools_execution import _sync_manage_portfolio


class _FakeQuery:
    def __init__(self, table_name, store):
        self.table_name = table_name
        self.store = store
        self._filters = {}
        self._update_payload = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def execute(self):
        rows = self.store.get(self.table_name, [])
        matched = [
            r for r in rows
            if all(r.get(k) == v for k, v in self._filters.items())
        ]
        if self._update_payload is not None:
            for r in matched:
                r.update(self._update_payload)
            return SimpleNamespace(data=matched)
        return SimpleNamespace(data=matched)


class _FakeSB:
    def __init__(self, store):
        self.store = store

    def from_(self, table_name):
        return _FakeQuery(table_name, self.store)


def test_manage_portfolio_set_and_add_cash():
    store = {
        "profiles": [{"id": "u1", "cash_balance": 0.0}],
        "positions": [],
    }
    fake_sb = _FakeSB(store)
    with patch("api.agentic_chat.tools_execution._get_sb", return_value=fake_sb):
        res = _sync_manage_portfolio(
            user_id="u1",
            operation="set_cash",
            cash_amount=150000,
            user_prompt="عايز اضيف اني معايا سيوله ١٥٠ الف",
        )
        assert res["status"] == "success"
        assert res["cash_balance"] == 150000.0
        assert store["profiles"][0]["cash_balance"] == 150000.0

        res2 = _sync_manage_portfolio(
            user_id="u1",
            operation="add_cash",
            cash_amount=50000,
            user_prompt="زود السيولة 50 الف",
        )
        assert res2["status"] == "success"
        assert res2["cash_balance"] == 200000.0
        assert store["profiles"][0]["cash_balance"] == 200000.0


def test_manage_portfolio_cash_blocks_unconfirmed_prompt():
    store = {"profiles": [{"id": "u1", "cash_balance": 0.0}], "positions": []}
    fake_sb = _FakeSB(store)
    with patch("api.agentic_chat.tools_execution._get_sb", return_value=fake_sb):
        res = _sync_manage_portfolio(
            user_id="u1",
            operation="set_cash",
            cash_amount=150000,
            user_prompt="حلل محفظتي",
        )
        assert res["status"] == "blocked"
        assert store["profiles"][0]["cash_balance"] == 0.0


def test_manage_portfolio_view_returns_watchlist_without_quantity():
    store = {
        "profiles": [{"id": "u1", "cash_balance": 10000.0}],
        "positions": [
            {
                "id": "p1",
                "user_id": "u1",
                "symbol": "COMI",
                "name": "CIB",
                "quantity": None,
                "entry_price": 80.0,
                "status": "open",
                "source": "watchlist",
                "added_at": "2026-11-14T20:00:00Z",
            }
        ],
    }
    fake_sb = _FakeSB(store)
    with patch("api.agentic_chat.tools_execution._get_sb", return_value=fake_sb):
        res = _sync_manage_portfolio(user_id="u1", operation="view")
        assert res["status"] == "success"
        assert res["positions_count"] == 0
        assert res["watchlist_count"] == 1
        assert res["watchlist_positions"][0]["symbol"] == "COMI"
        assert "COMI" in res["message"]
        assert res["cash_balance"] == 10000.0


def test_manage_portfolio_full_sell_uses_closed_manual_status_and_records_status_at():
    store = {
        "profiles": [{"id": "u1", "cash_balance": 1000.0}],
        "positions": [
            {
                "id": "p_elec",
                "user_id": "u1",
                "symbol": "ELEC",
                "name": "Electro Cable",
                "quantity": 89.0,
                "entry_price": 1.62,
                "status": "open",
                "source": "chatbot",
                "added_at": "2026-11-16T10:00:00Z",
            }
        ],
    }
    fake_sb = _FakeSB(store)
    with patch("api.agentic_chat.tools_execution._get_sb", return_value=fake_sb):
        res = _sync_manage_portfolio(
            user_id="u1",
            operation="sell",
            symbol="ELEC",
            quantity=89,
            price=1.77,
            user_prompt="بيع كامل كمية ELEC 89 سهم بسعر 1.77",
        )
        assert res["status"] == "success"
        pos = store["positions"][0]
        assert pos["status"] == "closed_manual"
        assert pos["status_price"] == 1.77
        assert pos.get("status_at")
        assert store["profiles"][0]["cash_balance"] == 1000.0 + (89.0 * 1.77)


def test_manage_portfolio_blocks_refresh_only_prompt_from_readding_positions():
    store = {
        "profiles": [{"id": "u1", "cash_balance": 0.0}],
        "positions": [
            {
                "id": "p_valu",
                "user_id": "u1",
                "symbol": "VALU",
                "name": "ValU",
                "quantity": 500.0,
                "entry_price": 9.8151,
                "status": "open",
                "source": "chatbot",
                "added_at": "2026-11-16T22:25:00Z",
            }
        ],
    }
    fake_sb = _FakeSB(store)
    with patch("api.agentic_chat.tools_execution._get_sb", return_value=fake_sb):
        res = _sync_manage_portfolio(
            user_id="u1",
            operation="add",
            symbol="VALU",
            quantity=500,
            price=9.8151,
            user_prompt="حدث المحفظه",
        )
        assert res["status"] == "blocked"
        assert store["positions"][0]["quantity"] == 500.0

        res2 = _sync_manage_portfolio(
            user_id="u1",
            operation="add",
            symbol="VALU",
            quantity=500,
            price=9.8151,
            user_prompt="تحديث المحفظة بأسعار اليوم",
        )
        assert res2["status"] == "blocked"
        assert store["positions"][0]["quantity"] == 500.0

        res3 = _sync_manage_portfolio(
            user_id="u1",
            operation="update",
            symbol="VALU",
            price=9.5,
            user_prompt="حدث سعر دخول VALU إلى 9.5",
        )
        assert res3["status"] == "success"
        assert store["positions"][0]["entry_price"] == 9.5

