"""
Golden Regression Gate for ARTORO AI Chat & 4-Market Financial Engine.

Run before every push (`pytest tests/test_golden_chat_regressions.py -q`).
Zero network / zero LLM cost — strictly deterministic structural guarantees
for every real production incident caught in user chat audits.
"""

import datetime as dt
from unittest.mock import patch


def test_cache_structural_allowlist_blocks_complaints_and_long_sentences():
    from api.agentic_chat.analysis_cache import build_analysis_cache_key

    # Short & multi-word canonical single-stock requests MUST remain cacheable
    assert build_analysis_cache_key("FCMD") == "vip_stock_FCMD"
    assert build_analysis_cache_key("حلل سهم فوري") == "vip_stock_FWRY"
    assert build_analysis_cache_key("حلل ابوقير ماليا") == "vip_stock_ABUK_financials"
    assert build_analysis_cache_key("التحليل الاساسي لسهم 2222", market="TADAWUL") == "vip_stock_2222_financials"
    assert build_analysis_cache_key("حلل سهم QNBK.QA", market="QSE") == "vip_stock_QNBK"
    assert build_analysis_cache_key("عايز تحليل فني ومالي لسهم البنك التجاري الدولي") == "vip_stock_COMI_financials"
    assert build_analysis_cache_key("عايز تحليل فني شامل لسهم البنك التجاري الدولي") == "vip_stock_COMI"
    assert build_analysis_cache_key("قارن بين COMI و فوري") == "vip_compare_COMI_FWRY"
    assert build_analysis_cache_key("حلل اعمار", market="EGX") == "vip_stock_EMFD"

    # Cross-market EGX alias MUST NOT hijack GCC queries in early cache
    assert build_analysis_cache_key("حلل اعمار", market="DFM") is None

    # Short & long complaints, objections, custom comparisons, or conversational messages MUST NEVER hit blind cache
    assert build_analysis_cache_key("قارن بين COMI و فوري بس قوليلي مين احسن للزكاة") is None
    assert build_analysis_cache_key("سهم FCMD ده سعره بايظ عندكم") is None
    assert build_analysis_cache_key("طلبت تحليل fcmd والأرقام غير محدثة وده بيضعف مصداقية التطبيق") is None
    assert build_analysis_cache_key("ايه رايك في سهم السعودية المصرية للاستثمار واشتري علي كام") is None
    assert build_analysis_cache_key("السعر ده قديم جدا ومش صح يا عم شوف FCMD تاني") is None


def test_db_catalog_fuzzy_lookup_finds_typos_and_arabic_names_without_regex():
    from api.agentic_chat.tools_execution import _search_catalog_candidates

    fake_catalog = [
        {"symbol": "INEG", "name": "Integrated Engineering Group", "name_ar": "المجموعة المتكاملة للأعمال الهندسية"},
        {"symbol": "NHPS", "name": "National Housing for Professional Syndicates", "name_ar": "الوطنية للإسكان للنقابات المهنية"},
        {"symbol": "PHGC", "name": "Premium HealthCare Group", "name_ar": "بريميم هيلث كير جروب"},
        {"symbol": "CERA", "name": "Arab Ceramics (Remas)", "name_ar": "العربية للخزف سيراميكا ريماس"},
        {"symbol": "PRCL", "name": "General Company for Ceramic & Porcelain", "name_ar": "العامة لمنتجات الخزف والصيني"},
    ]

    with patch("api.agentic_chat.tools_execution._get_market_stocks_catalog", return_value=fake_catalog):
        # Typo IENG -> suggests INEG
        typo_hits = [c["symbol"] for c in _search_catalog_candidates("IENG", exchange="EGX")]
        assert "INEG" in typo_hits

        # Arabic name -> suggests NHPS
        ar_hits = [c["symbol"] for c in _search_catalog_candidates("الوطنية للإسكان", exchange="EGX")]
        assert ar_hits and ar_hits[0] == "NHPS"

        # Truncated English header PREMIUM -> suggests PHGC
        en_hits = [c["symbol"] for c in _search_catalog_candidates("PREMIUM", exchange="EGX")]
        assert en_hits and en_hits[0] == "PHGC"


def test_vision_general_name_resolution_without_hardcoded_swaps():
    from api.agentic_chat.vision import validate_vision_output

    norm = validate_vision_output({
        "image_type": "portfolio",
        "symbols": [
            {"symbol": "PREMIUM", "name": "بريميم هيلث كير", "visible_values": {"price": 0.078}},
            {"symbol": "SM", "name": "سماد مصر", "visible_values": {"price": 216.65}},
            {"symbol": "COMI", "name": "التجاري الدولي", "visible_values": {"price": 127.5}},
        ],
    })
    assert [s["symbol"] for s in norm["symbols"]] == ["PHGC", "SMFR", "COMI"]


def test_currency_fidelity_across_egx_usd_and_gcc():
    from api.agentic_chat.market_registry import currency_for_symbol

    assert currency_for_symbol("FAITA", "EGX") == "$"
    assert currency_for_symbol("EGBE", "EGX") == "$"
    assert currency_for_symbol("MOIL", "EGX") == "$"
    assert currency_for_symbol("FAIT", "EGX") == "ج.م"
    assert currency_for_symbol("COMI", "EGX") == "ج.م"
    assert currency_for_symbol("2222", "TADAWUL") == "ر.س"
    assert currency_for_symbol("QNBK", "QSE") == "ر.ق"
    assert currency_for_symbol("EMAAR", "DFM") == "د.إ"


def test_blended_fair_value_tactical_levels_and_math_consistency():
    from api.agentic_chat.tools_execution import (
        _build_fair_value_gap,
        _compute_fundamental_fair_value,
        _compute_stock_context_metrics,
        _normalize_king_ai_score,
    )

    # ABUK with Forward P/E = 6.27x must not return raw 1934 Graham (~39 EGP)
    fv, _, extra = _compute_fundamental_fair_value(
        76.36, 75.0, 74.0,
        {"peRatio": 20.7, "forwardPe": 6.27, "pbRatio": 4.15, "eps": 3.69, "bookValuePerShare": 18.4, "roe": 16.5, "sector": "Basic Materials"},
        market="EGX",
    )
    assert 60.0 <= fv <= 82.0
    assert extra["graham_value"] == round((22.5 * 3.69 * 18.4) ** 0.5, 2)

    # Unambiguous Fair Value gap math (no +45% vs +81.8% confusion)
    gap = _build_fair_value_gap(306.20, 168.41)
    assert "+81.8%" in gap["valuation_gap_ar"]
    assert "45.0%" in gap["valuation_gap_ar"]

    # Tactical support/stop when structural support is > 12% away
    ctx = _compute_stock_context_metrics(306.20, 297.39, 229.97, 292.09, 205.00, 365.50, 200.90)
    assert ctx["support_1_is_distant"] is True
    assert ctx["tactical_support"] == 297.39
    assert ctx["tactical_risk_reward"] > 2.0

    # King AI unified 0-100 scale
    assert _normalize_king_ai_score(0.494) == 49.4
    assert _normalize_king_ai_score(84.0) == 84.0


def test_missing_stock_detector_prevents_poisoned_error_cache():
    from api.agentic_chat.pipeline import _tool_result_has_missing_stock

    assert _tool_result_has_missing_stock({"stocks": [{"symbol": "IENG", "close": None}]}) is True
    assert _tool_result_has_missing_stock({"suggested_matches": {"IENG": [{"symbol": "INEG"}]}}) is True
    assert _tool_result_has_missing_stock({"stocks": [{"symbol": "COMI", "close": 127.5}]}) is False


def test_catalog_tie_break_prefers_shorter_parent_symbol_for_emaar():
    from api.agentic_chat.tools_execution import _search_catalog_candidates

    fake_dfm = [
        {"symbol": "EMAARDEV", "name": "Emaar Development", "name_ar": "إعمار للتطوير"},
        {"symbol": "EMAAR", "name": "Emaar Properties", "name_ar": "إعمار العقارية"},
    ]
    with patch("api.agentic_chat.tools_execution._get_market_stocks_catalog", return_value=fake_dfm):
        hits = _search_catalog_candidates("اعمار", exchange="DFM", limit=2)
        assert hits and hits[0]["symbol"] == "EMAAR"


def test_prioritize_active_market_hints_remaps_to_dfm_without_breaking_egx():
    from api.agentic_chat.pipeline import _prioritize_active_market_hints

    egx_sa_hints = [
        {"name": "إعمار", "symbols": ["EMFD"], "market": "EGX"},
        {"name": "إعمار", "symbols": ["4220"], "market": "TASI"},
    ]
    with patch(
        "api.agentic_chat.tools_execution._search_catalog_candidates",
        return_value=[{"symbol": "EMAAR", "name_ar": "إعمار العقارية"}],
    ):
        remapped = _prioritize_active_market_hints(egx_sa_hints, "DFM", "حلل اعمار")
        assert remapped == [{"name": "إعمار", "symbols": ["EMAAR"], "market": "DFM"}]

        unchanged = _prioritize_active_market_hints(egx_sa_hints, "EGX", "حلل اعمار")
        assert unchanged == egx_sa_hints


def test_sharia_cleanser_honest_market_value_zakat_and_no_invented_purification():
    from api.agentic_chat.tools_execution import _sync_get_sharia_cleanser

    with patch(
        "api.agentic_chat.tools_execution._resolve_symbol_and_market",
        return_value=("COMI", "EGX"),
    ), patch(
        "api.agentic_chat.tools_execution._sync_get_stock",
        return_value={"stocks": [{"symbol": "COMI", "close": 127.5}]},
    ), patch(
        "api.agentic_chat.tools_execution._lookup_upcoming_dividend",
        return_value=None,
    ), patch(
        "api.agentic_chat.tools_execution.is_sharia_compliant",
        return_value=False,
    ):
        res = _sync_get_sharia_cleanser("COMI", 1000)
        assert res["market_value"] == 127500.0
        assert res["zakat_amount"] == 3187.5
        assert res["purification_amount"] is None
        assert res["purification_rate_pct"] is None
        assert res.get("purification_note_ar")


def test_graham_gap_and_support_risk_reward_eliminate_mental_math():
    from api.agentic_chat.tools_execution import _build_graham_gap_ar, _compute_stock_context_metrics

    g_text = _build_graham_gap_ar(18.11, 22.32)
    assert g_text is not None and "+23.2%" in g_text and "18.9%" in g_text

    ctx = _compute_stock_context_metrics(11.62, 12.53, 12.28, 11.69, 10.54, 12.80, 10.12)
    assert ctx["risk_reward_from_support"] == 5.38
