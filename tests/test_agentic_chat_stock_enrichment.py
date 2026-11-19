import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.agentic_chat.tools_execution import (
    _compute_stock_context_metrics,
    _compute_stock_verdict,
    _distinct_secondary_levels,
    _enrich_rec_distances,
    _summarize_breadth,
)


def test_distinct_secondary_levels_splits_coincident_extremes():
    s2, r2 = _distinct_secondary_levels(
        support_1=15.27,
        support_2=15.27,
        resistance_1=18.65,
        resistance_2=18.65,
        bb_low=14.80,
        bb_up=19.20,
    )
    assert s2 < 15.27
    assert s2 == 14.80
    assert r2 > 18.65
    assert r2 == 19.20


def test_compute_stock_verdict_uses_trend_and_flow_not_just_one_day():
    # Uptrend above EMA50 and EMA200 with healthy pullback (-0.5%) should NOT be negative
    verdict_up = _compute_stock_verdict(
        close=20.0,
        change_pct=-0.5,
        rsi=56.0,
        macd_hist=0.12,
        ema_50=19.0,
        ema_200=17.5,
        acc_score=65.0,
        dist_score=10.0,
    )
    assert verdict_up.startswith("🟢")

    # Downtrend below EMA50 & EMA200 even on a +0.4% green day should NOT be labeled bullish
    verdict_down = _compute_stock_verdict(
        close=16.95,
        change_pct=0.4,
        rsi=46.0,
        macd_hist=-0.05,
        ema_50=17.98,
        ema_200=18.02,
        acc_score=0.0,
        dist_score=30.0,
    )
    assert verdict_down.startswith("🔴")


def test_compute_stock_context_metrics_accuracy():
    m = _compute_stock_context_metrics(
        close=10.0,
        ema_50=9.5,
        ema_200=10.5,
        vwap_20=9.8,
        support_1=9.0,
        resistance_1=12.0,
        stop_loss=8.8,
    )
    assert m["above_ema50"] is True
    assert m["above_ema200"] is False
    assert m["above_vwap"] is True
    assert m["dist_to_support_pct"] == -10.0
    assert m["dist_to_resistance_pct"] == 20.0
    # reward = 12 - 10 = 2.0; risk = 10 - 8.8 = 1.2 => 1.67
    assert m["risk_reward_from_close"] == 1.67


def test_summarize_breadth_and_enrich_rec_distances():
    b_up = _summarize_breadth({"advancing": 120, "declining": 40})
    assert b_up["advance_decline_ratio"] == 3.0
    assert b_up["breadth_verdict"].startswith("🟢")

    b_down = _summarize_breadth({"advancing": 25, "declining": 100})
    assert b_down["advance_decline_ratio"] == 0.25
    assert b_down["breadth_verdict"].startswith("🔴")

    b_zero = _summarize_breadth({"advancing": 0, "declining": 50})
    assert b_zero["advance_decline_ratio"] == 0.0
    assert b_zero["breadth_verdict"].startswith("🔴")

    rec = {"entry_price": 10.0, "target_price": 12.0, "stop_loss": 9.0, "last_close": 11.0}
    _enrich_rec_distances(rec)
    assert rec["pnl_since_entry_pct"] == 10.0
    assert rec["remaining_upside_pct"] == 9.09
    assert rec["dist_to_stop_pct"] == -18.18


def test_deepseek_usage_and_cost_calculation():
    from api.agentic_chat.pipeline import (
        _accumulate_deepseek_usage,
        _finalize_usage_cost,
        _new_usage_accumulator,
    )

    acc = _new_usage_accumulator()
    # Round 1: tool selection
    _accumulate_deepseek_usage(
        acc,
        {
            "prompt_tokens": 5000,
            "completion_tokens": 80,
            "total_tokens": 5080,
            "prompt_cache_hit_tokens": 4500,
            "prompt_cache_miss_tokens": 500,
        },
        tools_called=["get_stock", "get_fair_value"],
    )
    # Round 2: synthesis
    _accumulate_deepseek_usage(
        acc,
        {
            "prompt_tokens": 6000,
            "completion_tokens": 920,
            "total_tokens": 6920,
            "prompt_cache_hit_tokens": 5000,
        },
    )

    final = _finalize_usage_cost(acc, cached=False)
    assert final["llm_rounds"] == 2
    assert final["prompt_tokens"] == 11000
    assert final["completion_tokens"] == 1000
    assert final["prompt_cache_hit_tokens"] == 9500
    assert final["prompt_cache_miss_tokens"] == 1500
    assert final["prefix_cache_hit_pct"] == 86.4
    assert final["tools_used"] == ["get_stock", "get_fair_value"]
    assert final["vip_response_cached"] is False
    # 9500 * 0.028/1e6 + 1500 * 0.28/1e6 + 1000 * 0.42/1e6 = 0.000266 + 0.000420 + 0.000420 = 0.001106
    assert final["cost_usd"] == 0.001106

    cached_final = _finalize_usage_cost(_new_usage_accumulator(), cached=True)
    assert cached_final["cost_usd"] == 0.0
    assert cached_final["vip_response_cached"] is True


def test_resolve_enriched_single_stock_tool_calls_to_cache_key():
    import json
    from api.agentic_chat.analysis_cache import resolve_tool_calls_to_cache_key

    batch = [
        {"function": {"name": "get_stock", "arguments": json.dumps({"symbols": ["SEIG"], "is_contextual_followup": False})}},
        {"function": {"name": "get_fair_value", "arguments": json.dumps({"symbols": ["SEIG"], "mode": "specific_stocks", "is_contextual_followup": False})}},
        {"function": {"name": "get_news", "arguments": json.dumps({"symbols": ["SEIG"], "is_contextual_followup": False})}},
        {"function": {"name": "get_disclosures", "arguments": json.dumps({"symbol": "SEIG", "is_contextual_followup": False})}},
        {"function": {"name": "get_price_traps", "arguments": json.dumps({"symbol": "SEIG"})}},
    ]
    assert resolve_tool_calls_to_cache_key(batch) == "vip_stock_SEIG"

    # Market-wide trap/fair-value mixed with stock should NOT cache under vip_stock_SEIG
    mixed_batch = [
        {"function": {"name": "get_stock", "arguments": json.dumps({"symbols": ["SEIG"], "is_contextual_followup": False})}},
        {"function": {"name": "get_price_traps", "arguments": json.dumps({"market": "EGX"})}},
    ]
    assert resolve_tool_calls_to_cache_key(mixed_batch) is None


def test_cache_key_guards_and_aliases():
    import json
    from unittest.mock import patch
    from api.agentic_chat.analysis_cache import (
        is_uncacheable_error_reply,
        resolve_tool_call_to_cache_key,
        resolve_tool_calls_to_cache_key,
    )
    from api.stock_aliases import resolve_stock_symbol
    from api.native_telegram_vip_chat import _resolve_telegram_user, _USER_RESOLVE_CACHE

    # 1. Generic non-ticker words like STOCKS must never become vip_stock_STOCKS
    assert resolve_tool_call_to_cache_key("get_stock", {"symbols": ["STOCKS"]}) is None
    assert is_uncacheable_error_reply("# ⚠️ لم يتم العثور على بيانات لسهم بهذا الرمز") is True
    assert is_uncacheable_error_reply("### 📊 تحليل سهم فوري (FWRY)") is False

    # 2. get_market + get_technical_scan must not collide with pure vip_tech_screener
    mkt_scan_batch = [
        {"function": {"name": "get_market", "arguments": json.dumps({"is_contextual_followup": False})}},
        {"function": {"name": "get_technical_scan", "arguments": json.dumps({"is_contextual_followup": False})}},
    ]
    assert resolve_tool_calls_to_cache_key(mkt_scan_batch) == "vip_market_and_screener"

    # 3. Arabia alias resolves to AIH
    assert resolve_stock_symbol("ارابيا") == "AIH"
    assert resolve_stock_symbol("أرابيا") == "AIH"

    # 4. Cross-account hijack via pro_telegram_invites blocked when profile already bound to another tg_chat_id
    _USER_RESOLVE_CACHE.clear()

    def fake_sb_req(path, *args, **kwargs):
        if path.startswith("telegram_vip_chat_state"):
            return [{"telegram_user_id": 6246816221, "linked_user_id": "owner-uuid"}]
        if path.startswith("profiles?telegram_chat_id=eq.6246816221"):
            return []
        if path.startswith("pro_telegram_invites?vip_telegram_user_id=eq.6246816221"):
            return [{"user_id": "owner-uuid"}]
        if path.startswith("profiles?id=in.(owner-uuid)"):
            return [{"id": "owner-uuid", "telegram_chat_id": "5149631436"}]
        return []

    with patch("api.native_telegram_vip_chat._supabase_request", side_effect=fake_sb_req):
        info = _resolve_telegram_user(6246816221, "Aziz Zizo")
        assert info["linked_user_id"] is None
        assert info["is_pro"] is False


def test_unified_multi_market_registry_cache_and_routing():
    from api.agentic_chat.market_registry import (
        detect_exchange_from_suffix,
        detect_market_from_text,
        get_market_config,
        get_supabase_for_exchange,
        normalize_exchange_code,
    )
    from api.agentic_chat.analysis_cache import (
        build_analysis_cache_key,
        resolve_scoped_cache_key,
    )
    from api.agentic_chat.pipeline import _resolve_query_market

    # 1. Registry normalization & dynamic synthesis for future exchanges
    assert normalize_exchange_code("EGX") == "EGX"
    assert normalize_exchange_code("TASI") == "TADAWUL"
    assert normalize_exchange_code("قطر") == "QSE"
    assert normalize_exchange_code("دبي") == "DFM"
    assert normalize_exchange_code("ابوظبي") == "ADX"
    assert normalize_exchange_code("الكويت") == "KSE"
    assert normalize_exchange_code("OMAN") == "OMAN"

    qse_cfg = get_market_config("QSE")
    assert qse_cfg.currency_ar == "ر.ق"
    assert qse_cfg.ui_code == "QSE"

    oman_cfg = get_market_config("OMAN")
    assert oman_cfg.exchange == "OMAN"
    assert oman_cfg.ui_code == "OMAN"

    # 2. Suffix & text detection
    assert detect_exchange_from_suffix("2222.SR") == ("2222", "TADAWUL")
    assert detect_exchange_from_suffix("QNBK.QA") == ("QNBK", "QSE")
    assert detect_exchange_from_suffix("EMAAR.DU") == ("EMAAR", "DFM")
    assert detect_market_from_text("ايه وضع بورصة قطر النهاردة؟") == "QSE"
    assert detect_market_from_text("رشح لي اسهم في سوق دبي") == "DFM"

    # 3. DB routing: future exchange without dedicated DB falls back to Primary Supabase;
    #    GCC exchanges (QSE/DFM/ADX/COMMODITIES) prefer dedicated DB / SAUDI_SUPABASE and fall back to Primary if unconfigured
    fake_primary = MagicMock(name="primary_sb")
    fake_gcc = MagicMock(name="gcc_sb")
    assert get_supabase_for_exchange("OMAN", primary_sb=fake_primary) is fake_primary
    with patch("api.agentic_chat.market_registry.get_dedicated_supabase_client", return_value=fake_gcc):
        assert get_supabase_for_exchange("QSE", primary_sb=fake_primary) is fake_gcc
    with patch("api.agentic_chat.market_registry.get_dedicated_supabase_client", return_value=None):
        assert get_supabase_for_exchange("QSE", primary_sb=fake_primary) is fake_primary

    # 4. Multi-market cache key namespacing & fast-track key building
    assert resolve_scoped_cache_key("vip_stock_COMI", allow_recommendations=True, market="EGX") == "vip_stock_COMI"
    assert resolve_scoped_cache_key("vip_stock_2222", allow_recommendations=True, market="TADAWUL") == "mkt_TADAWUL__vip_stock_2222"
    assert resolve_scoped_cache_key("vip_stock_QNBK", allow_recommendations=False, market="QSE") == "std_norecs:mkt_QSE__vip_stock_QNBK"
    assert build_analysis_cache_key("حلل سهم 2222", market="TADAWUL") == "vip_stock_2222"
    assert build_analysis_cache_key("حلل سهم QNBK.QA", market="QSE") == "vip_stock_QNBK"

    # 5. Pipeline _resolve_query_market single-market vs cross-market
    assert _resolve_query_market("حلل سهم 2222", active_market="EGX") == ("TADAWUL", False)
    assert _resolve_query_market("وضع بورصة قطر النهاردة", active_market="EGX") == ("QSE", False)
    _, is_cross = _resolve_query_market("قارن بين 2222 و COMI", active_market="EGX")
    assert is_cross is True


def test_future_exchange_qse_works_end_to_end_with_zero_custom_code():
    from api.agentic_chat.tools_execution import _sync_get_stock, _sync_get_market

    class _FakeTableQuery:
        def __init__(self, rows):
            self._rows = list(rows)
            self._eqs = {}
            self._ins = {}

        def select(self, *args, **kwargs):
            return self

        def eq(self, col, val):
            self._eqs[col] = val
            return self

        def in_(self, col, vals):
            self._ins[col] = set(vals)
            return self

        def not_(self):
            return self

        def gte(self, *args, **kwargs):
            return self

        def neq(self, *args, **kwargs):
            return self

        def order(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def range(self, *args, **kwargs):
            return self

        def execute(self):
            out = []
            for r in self._rows:
                ok = True
                for k, v in self._eqs.items():
                    if k in r and r[k] != v:
                        ok = False
                        break
                for k, vs in self._ins.items():
                    if k in r and r[k] not in vs:
                        ok = False
                        break
                if ok:
                    out.append(r)
            return MagicMock(data=out)

    qse_ti_rows = [
        {
            "symbol": "QNBK",
            "exchange": "QSE",
            "date": "2026-11-18",
            "updated_at": "2026-11-18T12:00:00Z",
            "close": 16.80,
            "change_pct": 1.45,
            "volume": 3200000,
            "vol_sma20": 2000000,
            "r_vol": 1.6,
            "rsi_14": 58.2,
            "macd": 0.14,
            "macd_signal": 0.10,
            "macd_histogram": 0.04,
            "bb_upper": 17.50,
            "bb_lower": 16.00,
            "ema_20": 16.40,
            "ema_50": 16.10,
            "ema_200": 15.50,
            "vwap_20": 16.55,
            "cmf_20": 0.12,
            "king_ai_score": 81.0,
        }
    ]
    qse_stocks_rows = [{"symbol": "QNBK", "exchange": "QSE", "name_ar": "بنك قطر الوطني", "name": "QNB Group", "sector": "Banks"}]
    qse_rec_rows = [
        {
            "symbol": "QNBK",
            "exchange": "QSE",
            "signal": "BUY",
            "entry_price": 16.50,
            "target_price": 18.00,
            "stop_loss": 15.80,
            "status": "open",
            "created_at": "2026-11-18T09:00:00Z",
            "model_name": "KING_QSE",
        }
    ]

    mock_sb = MagicMock()

    def _from_tbl(name):
        if name == "stock_technical_indicators":
            return _FakeTableQuery(qse_ti_rows)
        if name == "stocks":
            return _FakeTableQuery(qse_stocks_rows)
        if name in ("scan_results", "current_public_recommendations"):
            return _FakeTableQuery(qse_rec_rows)
        return _FakeTableQuery([])

    mock_sb.from_.side_effect = _from_tbl
    mock_sb.table.side_effect = _from_tbl

    with patch("api.agentic_chat.tools_execution._get_sb", return_value=mock_sb), \
         patch("api.agentic_chat.tools_execution._get_sb_for_market", return_value=mock_sb):
        stock_res = _sync_get_stock(["QNBK.QA"])
        assert stock_res["status"] == "success"
        assert stock_res["stocks"], f"Expected QNBK in QSE result, got {stock_res}"
        item = stock_res["stocks"][0]
        assert item["symbol"] == "QNBK"
        assert item["market"] == "QSE"
        assert item["exchange"] == "QSE"
        assert item["currency"] == "ر.ق"
        assert item["name_ar"] == "بنك قطر الوطني"
        assert item["vwap_20"] == 16.55
        assert item["has_active_recommendation"] is True
        assert item["active_recommendation"]["target_price"] == 18.0

        mkt_res = _sync_get_market(market="QSE")
        assert mkt_res["status"] == "success"
        assert mkt_res["market"] == "QSE"
        assert mkt_res["exchange"] == "QSE"
        assert mkt_res["currency"] == "ر.ق"
        assert mkt_res["top_gainers"] or mkt_res["breadth"] is not None


def test_qa_multi_market_regressions_zero_bleed_and_false_positives():
    from api.agentic_chat.analysis_cache import _normalize_ticker_for_cache, personalize_cached_analysis
    from api.agentic_chat.market_registry import detect_market_from_text
    from api.agentic_chat.pipeline import _collect_structured_outputs, _resolve_query_market
    from api.agentic_chat.tools_execution import (
        _resolve_symbol_and_market,
        _sync_get_recommendations,
        reset_active_market_context,
        set_active_market_context,
    )

    # 1. No false positives on EGX prose, golden cross, English words, or cash/point amounts
    assert detect_market_from_text("ملخص السوق وأحجام التداول") is None
    assert detect_market_from_text("هات أسهم التقاطع الذهبي") is None
    assert detect_market_from_text("is COMI necessary today?") is None
    assert _resolve_query_market("ملخص السوق وأحجام التداول", active_market="EGX") == ("EGX", False)
    assert _resolve_query_market("هات أسهم التقاطع الذهبي", active_market="EGX") == ("EGX", False)
    assert _resolve_query_market("رشح لي فرص شراء ب 5000 جنيه", active_market="EGX") == ("EGX", False)
    assert _resolve_query_market("ملخص السوق اليوم 4500 نقطة", active_market="EGX") == ("EGX", False)

    # 2. Single-market GCC / Metals / English Saudi queries must stay single-market (is_cross_market=False)
    assert _resolve_query_market("حلل سهم QNBK.QA", active_market="EGX") == ("QSE", False)
    assert _resolve_query_market("حلل سهم EMAAR.DU", active_market="EGX") == ("DFM", False)
    assert _resolve_query_market("حلل سهم ALDAR.AD", active_market="EGX") == ("ADX", False)
    assert _resolve_query_market("حلل سهم XAUUSD", active_market="EGX") == ("COMMODITIES", False)
    assert _resolve_query_market("price of 2222", active_market="EGX") == ("TADAWUL", False)

    # 3. _normalize_ticker_for_cache must NEVER mangle QNBK.QA -> QNBE or AIRARABIA -> AIH
    assert _normalize_ticker_for_cache("QNBK.QA") == "QNBK"
    assert _normalize_ticker_for_cache("AIRARABIA") == "AIRARABIA"
    assert _normalize_ticker_for_cache("EMIRATESNBD") == "EMIRATESNBD"
    assert _normalize_ticker_for_cache("فوري") == "FWRY"

    # 4. _resolve_symbol_and_market honors active non-EGX market without EGX mangling
    tok = set_active_market_context("QSE")
    try:
        with patch("api.agentic_chat.tools_execution._lookup_symbol_in_db", return_value=None), \
             patch("api.agentic_chat.tools_execution._lookup_symbol_in_gcc_and_metals", return_value=None):
            assert _resolve_symbol_and_market("QNBK") == ("QNBK", "QSE")
    finally:
        reset_active_market_context(tok)

    tok_dfm = set_active_market_context("DFM")
    try:
        with patch("api.agentic_chat.tools_execution._lookup_symbol_in_db", return_value=None), \
             patch("api.agentic_chat.tools_execution._lookup_symbol_in_gcc_and_metals", return_value=None):
            assert _resolve_symbol_and_market("AIRARABIA") == ("AIRARABIA", "DFM")
            assert _resolve_symbol_and_market("EMAAR") == ("EMAAR", "DFM")
    finally:
        reset_active_market_context(tok_dfm)

    # 5. _sync_get_recommendations(market="QSE") NEVER drops exchange filter when QSE has 0 rows
    class _StrictRecQuery:
        def __init__(self, rows):
            self._rows = rows
            self._exch = None
        def select(self, *a, **k): return self
        def eq(self, col, val):
            if col == "exchange":
                self._exch = val
            return self
        def in_(self, *a, **k): return self
        def order(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self):
            if self._exch is None:
                return MagicMock(data=self._rows)
            return MagicMock(data=[r for r in self._rows if r.get("exchange") == self._exch])

    saudi_only_rows = [{"symbol": "2222", "exchange": "TADAWUL", "signal": "BUY", "status": "open", "entry_price": 28.0}]
    fake_shared_sb = MagicMock()
    fake_shared_sb.from_.side_effect = lambda tbl: _StrictRecQuery(saudi_only_rows if tbl == "scan_results" else [])
    with patch("api.agentic_chat.tools_execution._get_sb_for_market", return_value=fake_shared_sb), \
         patch("api.agentic_chat.tools_execution._get_saudi_table_columns", return_value={"id", "symbol", "signal", "status", "exchange", "entry_price", "created_at"}):
        qse_recs = _sync_get_recommendations(market="QSE")
        assert qse_recs["status"] == "success"
        assert qse_recs["recommendations"] == []

    # 6. personalize_cached_analysis formats with the market's own currency (never hardcoded ج.م)
    fake_pf_sb = MagicMock()
    fake_pf_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"quantity": 50, "entry_price": 28.5, "status_price": 30.0}]
    )
    base_sa = "### 📊 تحليل سهم أرامكو (2222)\n**السعر الأخير:** 30.00 ر.س\n📌 **حالة السهم في محفظتك:** غير مسجل."
    with patch("api.stock_ai._init_supabase"), patch("api.stock_ai.supabase", fake_pf_sb):
        pers = personalize_cached_analysis(base_sa, user_id="u-1", symbol="2222", market="TADAWUL")
        assert "ر.س" in pers and "ج.م" not in pers

    # 7. _collect_structured_outputs preserves index_close & 0.0 index_change_pct for QSE
    vis = {}
    _collect_structured_outputs(
        {
            "market": "QSE",
            "index_name": "QSI",
            "index_close": 10450.5,
            "index_change_pct": 0.0,
            "currency": "ر.ق",
            "date": "2026-11-18",
            "breadth": {"advancing": 10, "declining": 5, "unchanged": 2, "total_stocks": 17},
        },
        [],
        [],
        vis,
    )
    assert vis["market_breadth"]["index_close"] == 10450.5
    assert vis["market_breadth"]["index_change_pct"] == 0.0
    assert vis["market_breadth"]["currency"] == "ر.ق"


def test_qa2_accumulation_recs_no_bleed_and_suffixed_round1_routing():
    import json as _json
    from api.agentic_chat.pipeline import _resolve_query_market, known_symbol_hints
    from api.agentic_chat.tools_execution import (
        _resolve_symbol_and_market,
        _sync_get_accumulation_stocks,
        _sync_get_recommendations,
    )

    # 1. _sync_get_accumulation_stocks(market="QSE") MUST skip exchange-less stock_scans_summary on real shared DB
    saudi_summary_rows = [
        {"symbol": "2222", "scan_date": "2026-11-18", "acc_score": 88.0, "dist_score": 10.0, "wyckoff_phase": "accumulation"}
    ]

    class _NoExchTable:
        def __init__(self, rows):
            self._rows = rows
        def select(self, *a, **k): return self
        @property
        def not_(self): return self
        def is_(self, *a, **k): return self
        def gte(self, *a, **k): return self
        def neq(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def order(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self): return MagicMock(data=self._rows)

    fake_real_shared_sb = MagicMock()
    fake_real_shared_sb.from_.side_effect = lambda tbl: _NoExchTable(saudi_summary_rows if tbl == "stock_scans_summary" else [])
    with patch("api.agentic_chat.tools_execution._get_sb_for_market", return_value=fake_real_shared_sb), \
         patch("api.agentic_chat.tools_execution._is_real_saudi_sb", return_value=True), \
         patch("api.agentic_chat.tools_execution._get_saudi_table_columns", return_value={"symbol", "scan_date", "acc_score", "dist_score", "wyckoff_phase"}), \
         patch("api.agentic_chat.tools_execution._get_saudi_computed_market_indicators", return_value=[]) as mock_computed:
        acc_qse = _sync_get_accumulation_stocks(market="QSE")
        assert acc_qse["status"] == "success"
        assert acc_qse["accumulation_stocks"] == []
        mock_computed.assert_called_once()
        assert mock_computed.call_args.kwargs.get("exchange") == "QSE"

    # 2. _sync_get_recommendations(market="QSE") MUST skip tables lacking an `exchange` column on shared DBs
    fake_rec_sb = MagicMock()
    fake_rec_sb.from_.side_effect = lambda tbl: _NoExchTable([{"symbol": "2222", "signal": "BUY", "status": "open"}])
    with patch("api.agentic_chat.tools_execution._get_sb_for_market", return_value=fake_rec_sb), \
         patch("api.agentic_chat.tools_execution._get_saudi_table_columns", return_value={"id", "symbol", "signal", "status", "created_at"}):
        rec_qse = _sync_get_recommendations(market="QSE")
        assert rec_qse["status"] == "success"
        assert rec_qse["recommendations"] == []

    # 3A. Suffixed dual-listed ticker ADIB.AD must NOT emit an EGX hint in known_symbol_hints
    adib_hints = known_symbol_hints("حلل سهم ADIB.AD")
    assert all(h.get("market") != "EGX" for h in adib_hints)
    assert _resolve_query_market("حلل سهم ADIB.AD", active_market="EGX", hints=adib_hints) == ("ADX", False)

    # 3B. Round-1 get_stock(symbols=["NBK"]) on KSE query (with ui_exch="EGX") must NOT be overwritten to EGX
    with patch("api.agentic_chat.tools_execution._lookup_symbol_in_db", return_value=None), \
         patch("api.agentic_chat.tools_execution._lookup_symbol_in_gcc_and_metals", return_value=None):
        tc_kse = [{"function": {"name": "get_stock", "arguments": _json.dumps({"symbols": ["NBK"], "is_contextual_followup": False})}}]
        assert _resolve_query_market("سعر سهم NBK في الكويت", active_market="KSE", hints=[], tool_calls=tc_kse) == ("KSE", False)

        # Explicit non-EGX market on dual-listed symbol resolves to that exchange cleanly
        assert _resolve_symbol_and_market("ADIB", explicit_market="ADX") == ("ADIB", "ADX")
