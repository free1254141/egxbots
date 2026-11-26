"""Offline unit tests for 2026-11-26 chat audit P1/P2/P3 fixes."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from api.agentic_chat.analysis_cache import (
    _EOD_SCAN_CACHE_KEYS,
    build_analysis_cache_key,
    is_recommendation_cache_key,
)
from api.agentic_chat.pipeline import (
    _CANONICAL_BUTTON_INPUTS,
    _COMMODITY_FAST_RE,
    _is_unambiguous_standalone_input,
)
from api.agentic_chat.tools_execution import (
    _extract_rich_fundamentals,
    _sync_get_fair_value,
    _sync_get_stock,
    _sync_manage_portfolio,
)
from api.stock_aliases import resolve_stock_symbol
from jobs.daily_disclosures_sync import classify_disclosure_headline, clean_rss_title


def test_commodities_fair_value_suppressed() -> None:
    """COMMODITIES (XAUUSD/XAGUSD) must never receive equity Fair Value estimates."""
    fv_res = _sync_get_fair_value(symbols=["XAUUSD"], market="COMMODITIES")
    assert fv_res["status"] == "not_applicable"
    assert fv_res["exchange"] == "COMMODITIES"
    assert fv_res["stocks"] == []
    assert "للسلع والمعادن العالمية" in fv_res["message"]

    class _MockRes:
        def __init__(self, data):
            self.data = data

    class _MockQuery:
        def __init__(self, tbl):
            self._tbl = tbl
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def in_(self, *_a): return self
        def order(self, *_a, **_kw): return self
        def limit(self, *_a): return self
        def execute(self):
            if self._tbl == "stock_technical_indicators":
                return _MockRes([{
                    "symbol": "XAUUSD",
                    "exchange": "COMMODITIES",
                    "close": 3583.10,
                    "change_pct": 0.76,
                    "rsi_14": 22.2,
                    "macd": -138.27,
                    "macd_signal": -105.0,
                    "macd_histogram": -32.9,
                    "ema_50": 3996.28,
                    "ema_200": 4198.65,
                    "vwap_20": 3819.0,
                    "r_vol": 1.0,
                    "support_1": 3426.72,
                    "resistance_1": 4148.60,
                    "stop_loss": 3358.19,
                    "king_ai_score": 46.0,
                    "date": "2026-11-25",
                }])
            return _MockRes([])

    class _MockSB:
        def from_(self, tbl): return _MockQuery(tbl)

    with (
        patch("api.agentic_chat.tools_execution._get_sb_for_market", return_value=_MockSB()),
        patch("api.agentic_chat.tools_execution._get_saudi_table_columns", return_value={"symbol", "exchange", "close", "change_pct", "rsi_14", "macd", "macd_signal", "macd_histogram", "ema_50", "ema_200", "vwap_20", "r_vol", "support_1", "resistance_1", "stop_loss", "king_ai_score", "date"}),
        patch("api.agentic_chat.tools_execution._resolve_symbol_and_market", return_value=("XAUUSD", "COMMODITIES")),
        patch("api.agentic_chat.tools_execution._fetch_saudi_names_map", return_value={"XAUUSD": {"name_ar": "الذهب العالمي", "name": "Gold Spot"}}),
        patch("api.agentic_chat.tools_execution._fetch_saudi_ohlcv_for_symbols", return_value={"XAUUSD": []}),
    ):
        stock_res = _sync_get_stock(symbols=["XAUUSD"], market="COMMODITIES")

    assert stock_res["status"] == "success"
    item = stock_res["stocks"][0]
    assert item["fair_value"] is None
    assert "fair_value_note_ar" in item


def test_disclosures_sync_insider_classification_and_cleaning() -> None:
    """Daily disclosures sync must classify press insider/stake deals accurately even by EGP value."""
    raw_amer = "خروج من قائمة كبار الملاك.. محمد عمر يبيع حصة في عامر جروب بـ59 مليون جنيه - اليوم السابع"
    cleaned_amer = clean_rss_title(raw_amer)
    assert cleaned_amer.endswith("بـ59 مليون جنيه")
    d_type, act_type, shares_cnt = classify_disclosure_headline(cleaned_amer)
    assert d_type in ("insider_trading", "major_shareholders")
    assert act_type == "sell"
    assert shares_cnt is None

    raw_tmgh = "مساهم يرفع حصته في طلعت مصطفى بـ 2 مليون سهم - جريدة المال"
    cleaned_tmgh = clean_rss_title(raw_tmgh)
    d_type_2, act_type_2, shares_cnt_2 = classify_disclosure_headline(cleaned_tmgh)
    assert d_type_2 == "insider_trading"
    assert act_type_2 == "buy"
    assert shares_cnt_2 == 2_000_000


def test_manage_portfolio_buy_sell_skip_followup_view_and_trade_summary() -> None:
    """Portfolio buy/sell returns rich trade_summary + skip_followup_view=True with exact math."""

    class _MockRes:
        def __init__(self, data):
            self.data = data

    class _MockQuery:
        def __init__(self, tbl, state):
            self._tbl = tbl
            self._state = state
            self._upd = None
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def order(self, *_a, **_kw): return self
        def limit(self, *_a): return self
        def update(self, data):
            self._upd = data
            return self
        def execute(self):
            if self._tbl == "positions":
                if self._upd is not None:
                    self._state["pos"].update(self._upd)
                    return _MockRes([self._state["pos"]])
                return _MockRes([self._state["pos"]])
            if self._tbl == "profiles":
                if self._upd is not None and "cash_balance" in self._upd:
                    self._state["cash"] = self._upd["cash_balance"]
                return _MockRes([{"cash_balance": self._state["cash"]}])
            return _MockRes([])

    class _MockSB:
        def __init__(self, state):
            self._state = state
        def from_(self, tbl): return _MockQuery(tbl, self._state)

    state_buy = {
        "cash": 11922.63,
        "pos": {"id": 1, "symbol": "AMOC", "name": "أموك", "quantity": 701.0, "entry_price": 12.77, "status": "open"},
    }
    with (
        patch("api.agentic_chat.tools_execution._get_sb", return_value=_MockSB(state_buy)),
        patch("api.agentic_chat.tools_execution._resolve_symbol_and_market", return_value=("AMOC", "EGX")),
        patch("api.agentic_chat.tools_execution._fetch_compact_portfolio_summary", return_value={"cash_balance": 11922.63, "positions_count": 1}),
    ):
        res_buy = _sync_manage_portfolio(
            user_id="user-1",
            operation="buy",
            symbol="AMOC",
            quantity=300,
            price=12.01,
            user_prompt="تم شراء 300 سهم AMOC بسعر 12.01",
        )
    assert res_buy["status"] == "success"
    assert res_buy["skip_followup_view"] is True
    assert res_buy["trade_summary"]["new_quantity"] == pytest.approx(1001.0)
    assert res_buy["trade_summary"]["new_avg_price"] == pytest.approx(12.5422, abs=1e-3)
    assert res_buy["trade_summary"]["trade_value"] == pytest.approx(3603.0)

    state_sell = {
        "cash": 4038.63,
        "pos": {"id": 2, "symbol": "PRCL", "name": "الخزف والصيني", "quantity": 150.0, "entry_price": 22.52, "status": "open"},
    }
    with (
        patch("api.agentic_chat.tools_execution._get_sb", return_value=_MockSB(state_sell)),
        patch("api.agentic_chat.tools_execution._resolve_symbol_and_market", return_value=("PRCL", "EGX")),
        patch("api.agentic_chat.tools_execution._fetch_compact_portfolio_summary", return_value={"cash_balance": 4954.63, "positions_count": 1}),
    ):
        res_sell = _sync_manage_portfolio(
            user_id="user-1",
            operation="sell",
            symbol="PRCL",
            quantity=50,
            price=18.32,
            user_prompt="تم بيع 50 سهم PRCL بسعر 18.32",
        )
    assert res_sell["status"] == "success"
    assert res_sell["skip_followup_view"] is True
    assert res_sell["trade_summary"]["remaining_quantity"] == pytest.approx(100.0)
    assert res_sell["trade_summary"]["cash_before"] == pytest.approx(4038.63)
    assert res_sell["trade_summary"]["cash_after"] == pytest.approx(4954.63)
    assert res_sell["trade_summary"]["realized_pnl"] == pytest.approx(-210.0)


def test_vip_cache_aliases_commodity_fast_track_and_ratio_anomaly() -> None:
    """Verify VIP cache key, AMII/ZEOT aliases, XAUUSD fast-track regex, and anomaly note."""
    btn = "📈 ترشيح فرص بديلة"
    assert btn in _CANONICAL_BUTTON_INPUTS
    assert _is_unambiguous_standalone_input(btn, market="EGX") is True
    ck = build_analysis_cache_key(btn, market="EGX")
    assert ck == "vip_open_recommendations"
    assert ck in _EOD_SCAN_CACHE_KEYS
    assert is_recommendation_cache_key(ck) is True

    assert resolve_stock_symbol("العربية للصناعات المعدنية") == "AMII"
    assert resolve_stock_symbol("الزيوت المستخلصة") == "ZEOT"

    m = _COMMODITY_FAST_RE.match("حلل سعر الذهب العالمي (XAUUSD) فنياً الآن مع أهم مستويات الدعم والمقاومة والاتجاه القادم.")
    assert m is not None
    assert m.group(1).upper() == "XAUUSD"

    rich = _extract_rich_fundamentals({"peRatio": 0.16, "pbRatio": 0.01, "eps": 2.5}, fund_score=55.0)
    assert "ratio_anomaly_note_ar" in rich
