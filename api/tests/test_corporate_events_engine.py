"""Offline unit tests for Event Reality-Check (#4) and Corporate Actions Ex-Date Calculator (#5)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from api.corporate_events_engine import (
    calculate_corporate_action,
    classify_event_reality_check,
)


def test_event_reality_check_classifications() -> None:
    # 1. Positive news + drop -> Sell the News (e.g. RKAZ)
    rc_sell = classify_event_reality_check(
        sentiment="bullish",
        title="توزيع أرباح نقدية ونمو صافي الربح",
        change_pct=-2.1,
        r_vol=2.4,
    )
    assert rc_sell is not None
    assert rc_sell["code"] == "sell_the_news"
    assert rc_sell["tone"] == "warning"
    assert "بيع على الخبر" in rc_sell["label_ar"]

    # 2. Positive news + strong rally on volume -> Institutional Confirmation
    rc_conf = classify_event_reality_check(
        sentiment="bullish",
        action_type="buy",
        change_pct=3.4,
        r_vol=1.9,
    )
    assert rc_conf is not None
    assert rc_conf["code"] == "institutional_confirmation"
    assert rc_conf["tone"] == "positive"

    # 3. Negative news + selloff -> Confirmed Selloff
    rc_neg = classify_event_reality_check(
        sentiment="bearish",
        change_pct=-3.0,
        r_vol=1.6,
    )
    assert rc_neg is not None
    assert rc_neg["code"] == "confirmed_selloff"
    assert rc_neg["tone"] == "negative"

    # 4. Negative news + green close -> Bad-News Absorption
    rc_abs = classify_event_reality_check(
        sentiment="bearish",
        change_pct=1.4,
        r_vol=1.1,
    )
    assert rc_abs is not None
    assert rc_abs["code"] == "quiet_absorption"
    assert rc_abs["tone"] == "positive"

    # 5. Missing change_pct -> None
    assert classify_event_reality_check(sentiment="bullish", change_pct=None) is None


def test_calculate_corporate_action_all_four_types() -> None:
    # 1. Bonus shares: 1 free share for every 4 held (e.g. FWRY)
    res_bonus = calculate_corporate_action(
        action_type="bonus_shares",
        pre_ex_price=10.0,
        shares=5000,
        avg_buy_price=8.50,
        ratio_new=1,
        ratio_for=4,
        exchange="EGX",
        currency="ج.م",
        symbol="FWRY",
    )
    assert res_bonus["status"] == "success"
    assert res_bonus["theoretical_ex_price"] == pytest.approx(8.0, abs=1e-4)
    assert res_bonus["new_shares"] == pytest.approx(6250.0, abs=1e-2)
    assert res_bonus["added_shares"] == pytest.approx(1250.0, abs=1e-2)
    assert res_bonus["new_avg_cost"] == pytest.approx(6.8, abs=1e-4)
    assert res_bonus["old_market_value"] == pytest.approx(res_bonus["new_market_value"], abs=0.05)

    # 2. Stock split: 5-for-1
    res_split = calculate_corporate_action(
        action_type="stock_split",
        pre_ex_price=50.0,
        shares=200,
        avg_buy_price=40.0,
        ratio_new=5,
        ratio_for=1,
    )
    assert res_split["status"] == "success"
    assert res_split["theoretical_ex_price"] == pytest.approx(10.0, abs=1e-4)
    assert res_split["new_shares"] == pytest.approx(1000.0, abs=1e-2)
    assert res_split["new_avg_cost"] == pytest.approx(8.0, abs=1e-4)

    # 3. Cash dividend: EGX default 5% tax + Yield on Cost
    res_div = calculate_corporate_action(
        action_type="cash_dividend",
        pre_ex_price=25.0,
        shares=2000,
        avg_buy_price=20.0,
        dividend_per_share=2.0,
        exchange="EGX",
    )
    assert res_div["status"] == "success"
    assert res_div["theoretical_ex_price"] == pytest.approx(23.0, abs=1e-4)
    assert res_div["gross_dividend"] == pytest.approx(4000.0, abs=1e-2)
    assert res_div["tax_amount"] == pytest.approx(200.0, abs=1e-2)
    assert res_div["net_dividend"] == pytest.approx(3800.0, abs=1e-2)
    assert res_div["yield_on_cost_pct"] == pytest.approx(10.0, abs=1e-2)
    assert res_div["net_yield_on_cost_pct"] == pytest.approx(9.5, abs=1e-2)

    # 4. Rights issue: 1 new for 2 old at 1.00 when price is 4.00 -> TERP = (4*2 + 1*1)/3 = 3.00
    res_rights = calculate_corporate_action(
        action_type="rights_issue",
        pre_ex_price=4.0,
        shares=2000,
        avg_buy_price=3.5,
        ratio_new=1,
        ratio_for=2,
        subscription_price=1.0,
    )
    assert res_rights["status"] == "success"
    assert res_rights["theoretical_ex_price"] == pytest.approx(3.0, abs=1e-4)
    assert res_rights["theoretical_right_value"] == pytest.approx(1.0, abs=1e-4)
    assert res_rights["added_shares"] == pytest.approx(1000.0, abs=1e-2)
    assert res_rights["subscription_cost"] == pytest.approx(1000.0, abs=1e-2)
    # Old cost = 2000 * 3.5 = 7000 + 1000 = 8000 / 3000 = 2.667
    assert res_rights["new_avg_cost"] == pytest.approx(2.667, abs=1e-3)


def test_dispatch_calculate_corporate_action_autofills_price_and_portfolio() -> None:
    from api.agentic_chat.tools_execution import dispatch_tool

    class _MockRes:
        def __init__(self, data):
            self.data = data

    class _MockQuery:
        def __init__(self, tbl):
            self._tbl = tbl
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def limit(self, *_a): return self
        def execute(self):
            if self._tbl == "stock_technical_indicators":
                return _MockRes([{"close": 10.0}])
            if self._tbl == "positions":
                return _MockRes([{"symbol": "FWRY", "quantity": 4000, "entry_price": 8.0}])
            return _MockRes([])

    class _MockSB:
        def from_(self, tbl): return _MockQuery(tbl)

    with (
        patch("api.agentic_chat.tools_execution._get_sb", return_value=_MockSB()),
        patch("api.agentic_chat.tools_execution._resolve_symbol_and_market", return_value=("FWRY", "EGX")),
    ):
        res = asyncio.run(
            dispatch_tool(
                "calculate_corporate_action",
                {"action_type": "bonus_shares", "symbol": "FWRY", "ratio_new": 1, "ratio_for": 4},
                user_id="user-123",
            )
        )
    assert res["status"] == "success"
    assert res["used_portfolio_position"] is True
    assert res["old_shares"] == pytest.approx(4000.0)
    assert res["new_shares"] == pytest.approx(5000.0)
    assert res["new_avg_cost"] == pytest.approx(6.4, abs=1e-3)
    assert res["theoretical_ex_price"] == pytest.approx(8.0, abs=1e-3)
