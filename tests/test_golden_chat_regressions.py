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


def test_alias_dictionary_has_zero_generic_city_collisions_or_dead_mnhd():
    from api.agentic_chat.pipeline import known_symbol_hints
    from api.stock_aliases import ARABIC_STOCK_MAPPINGS, resolve_stock_symbol

    for bad_generic in ("الاسكندرية", "الإسكندرية", "اسكندرية", "اسكندريه", "النصر", "جولدن", "فاينانس", "النيل", "جراند"):
        assert bad_generic not in ARABIC_STOCK_MAPPINGS
    assert "MNHD" not in ARABIC_STOCK_MAPPINGS.values()

    assert resolve_stock_symbol("فتنس برايم") == "FTNS"
    assert resolve_stock_symbol("اسكندرية زيوت") == "AMOC"
    assert resolve_stock_symbol("مدينة نصر للإسكان") == "MASR"
    assert resolve_stock_symbol("اسمنت بورتلاند طرة") == "TORA"

    ftns_hints = known_symbol_hints("هل سهم فتنس برايم ممكن ينهار")
    assert any("FTNS" in h.get("symbols", []) for h in ftns_hints)
    assert not any("PRMH" in h.get("symbols", []) for h in ftns_hints)

    amoc_hints = known_symbol_hints("اسكندريه زيوت")
    assert any("AMOC" in h.get("symbols", []) for h in amoc_hints)
    assert not any("ALCN" in h.get("symbols", []) for h in amoc_hints)


def test_universal_tool_identity_enricher_fills_names_and_usd_currency():
    from api.agentic_chat.tools_execution import _enrich_tool_result_identities

    with patch("api.agentic_chat.tools_execution._get_market_stocks_catalog", return_value=[]):
        out = _enrich_tool_result_identities(
            {
                "items": [
                    {"symbol": "MASR", "fair_value": 10.74},
                    {"symbol": "FAITA", "close": 1.01},
                ]
            },
            default_market="EGX",
        )
    assert "مدينة مصر" in out["items"][0]["name_ar"]
    assert out["items"][0]["currency"] == "ج.م"
    assert out["items"][1]["currency"] == "$"


def test_search_stocks_tool_resolves_colloquial_arabic_names():
    from api.agentic_chat.tools_execution import _sync_search_stocks

    fake_catalog = [
        {"symbol": "AMOC", "name": "Alexandria Mineral Oils Co.", "name_ar": "الإسكندرية للزيوت المعدنية"},
        {"symbol": "FTNS", "name": "Fitness Prime", "name_ar": "فتنس برايم"},
        {"symbol": "ADIB", "name": "Abu Dhabi Islamic Bank-Egypt", "name_ar": "مصرف أبوظبي الإسلامي"},
    ]
    with patch("api.agentic_chat.tools_execution._get_market_stocks_catalog", return_value=fake_catalog):
        res = _sync_search_stocks(["اسكندريه زيوت", "فتنس برايم", "بنك ابو ظبي"], market="EGX")
    top_syms = [row["matches"][0]["symbol"] for row in res["results"]]
    assert top_syms == ["AMOC", "FTNS", "ADIB"]


def test_output_guard_enforces_stale_warning_blocks_currency_mismatch_and_sanitizes_tool_leaks():
    from api.agentic_chat.output_guard import verify_and_guard_reply

    # 1. Stale stock omitted in reply -> prepends warning + blocks cache
    g1 = verify_and_guard_reply(
        "سعر السهم 7.30 جنيه والوضع إيجابي.",
        [{"stocks": [{"symbol": "FCMD", "date": "2026-09-23", "close": 7.30, "currency": "ج.م", "data_is_stale": True, "stale_data_warning": "⚠️ تنبيه شفافية مهم: آخر جلسة 2026-09-23"}]}],
    )
    assert g1["prepended_warning"] is True
    assert g1["block_cache"] is True
    assert "2026-09-23" in g1["reply"]

    # 2. USD stock quoted with ج.م -> flags currency_mismatch + blocks cache
    g2 = verify_and_guard_reply(
        "سهم FAITA يتداول عند 1.01 ج.م حالياً.",
        [{"stocks": [{"symbol": "FAITA", "close": 1.01, "currency": "$"}]}],
    )
    assert any("currency_mismatch" in w for w in g2["warnings"])
    assert g2["block_cache"] is True

    # 3. Leaked Python tool identifier -> sanitized cleanly
    g3 = verify_and_guard_reply("يمكنك فحص التطهير عبر `get_sharia_cleanser` مباشرة.", [])
    assert "get_sharia_cleanser" not in g3["reply"]
    assert "tool_name_leaked:get_sharia_cleanser" in g3["warnings"]

    # 4. Clean reply -> zero warnings, cache allowed
    g4 = verify_and_guard_reply("سهم COMI عند 127.50 ج.م.", [{"stocks": [{"symbol": "COMI", "close": 127.5, "currency": "ج.م"}]}])
    assert g4["warnings"] == []
    assert g4["block_cache"] is False


def test_usd_egx_stock_flags_egp_financials_currency():
    from api.agentic_chat.tools_execution import _extract_rich_fundamentals

    res_usd = _extract_rich_fundamentals(
        {"currency": "EGP", "dividendPerShare": 0.7619, "dividendYield": 3.15},
        close_price=0.50,
        trade_currency="$",
    )
    assert res_usd["financials_currency"] == "ج.م"
    assert res_usd.get("financials_currency_note_ar")

    res_egp = _extract_rich_fundamentals(
        {"currency": "EGP", "dividendPerShare": 2.30, "dividendYield": 6.57},
        close_price=35.0,
        trade_currency="ج.م",
    )
    assert "financials_currency_note_ar" not in res_egp


def test_output_guard_strips_leaked_boolean_debug_fields():
    from api.agentic_chat.output_guard import verify_and_guard_reply

    g = verify_and_guard_reply("⚠️ الاتنين غير متوافقين مع الشريعة (is_sharia_compliant = false).", [])
    assert "is_sharia_compliant" not in g["reply"]
    assert g["reply"] == "⚠️ الاتنين غير متوافقين مع الشريعة."
    assert g["warnings"]
