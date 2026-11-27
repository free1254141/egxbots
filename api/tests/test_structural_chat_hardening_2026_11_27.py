"""Offline unit tests for 5-Pillar Structural Hardening (2026-11-27)."""

from __future__ import annotations

from unittest.mock import patch

from api.agentic_chat.analysis_cache import (
    _EOD_SCAN_CACHE_KEYS,
    build_analysis_cache_key,
    is_cache_write_intent_safe,
    is_recommendation_cache_key,
)
from api.agentic_chat.output_guard import verify_and_guard_reply
from api.agentic_chat.pipeline import (
    _CANONICAL_BUTTON_INPUTS,
    _compact_history_content,
)
from api.agentic_chat.tools_execution import _sync_manage_automations
from api.stock_aliases import resolve_stock_symbol


def test_pillar1_write_intent_parity_and_sharia_and_vlmra() -> None:
    # Sector question must NEVER poison vip_accumulation or any shared market bucket
    sector_q = "ما هو أنشط قطاع في البورصة المصرية حالياً ولماذا؟"
    assert is_cache_write_intent_safe(sector_q, "vip_accumulation", market="EGX") is False
    assert is_cache_write_intent_safe(sector_q, "vip_market_summary", market="EGX") is False

    # Genuine accumulation query MUST be allowed to write to vip_accumulation
    acc_q = "إيه أقوى الأسهم اللي بتجمع سيولة وأحجام تداول النهاردة؟"
    assert build_analysis_cache_key(acc_q, market="EGX") == "vip_accumulation"
    assert is_cache_write_intent_safe(acc_q, "vip_accumulation", market="EGX") is True

    # Bespoke stock trading/personal questions (including punctuated!) must NEVER write to vip_stock_*
    assert is_cache_write_intent_safe("ايه رايك سعم ركاز ممكن ادنى هبوط ليه يبقى كام", "vip_stock_RKAZ") is False
    assert is_cache_write_intent_safe("ابيع على كام في سهم COSG", "vip_stock_COSG") is False
    assert is_cache_write_intent_safe("سهم COSG ابيع بكام؟", "vip_stock_COSG") is False
    assert is_cache_write_intent_safe("سهم COSG خلال شهر؟", "vip_stock_COSG") is False
    assert is_cache_write_intent_safe("حلل سهم COSG", "vip_stock_COSG") is True

    # Market-wide vip_fair_value_undervalued must reject sector/bespoke writes; compare/traps are entity keys
    assert is_cache_write_intent_safe("أرخص أسهم قطاع العقارات", "vip_fair_value_undervalued", market="EGX") is False
    assert is_cache_write_intent_safe("قارن COMI و TMGH", "vip_compare_COMI_TMGH", market="EGX") is True
    assert is_cache_write_intent_safe("قارن COMI و TMGH ليه؟", "vip_compare_COMI_TMGH", market="EGX") is False
    assert is_cache_write_intent_safe("مصائد سهم COMI", "vip_traps_COMI", market="EGX") is True

    # Every canonical quick-action button must resolve to a non-None cache key & pass write gate
    for btn_text in _CANONICAL_BUTTON_INPUTS:
        btn_key = build_analysis_cache_key(btn_text, market="EGX")
        assert btn_key is not None, f"Canonical button has no cache key: {btn_text}"
        assert is_cache_write_intent_safe(btn_text, btn_key, market="EGX") is True

    # Sharia recommendations dedicated cache key & button (but single-stock Sharia query stays stock-scoped)
    sharia_q = "التوصيات الشريعه"
    assert sharia_q in _CANONICAL_BUTTON_INPUTS
    ck_sharia = build_analysis_cache_key(sharia_q, market="EGX")
    assert ck_sharia == "vip_open_recommendations_sharia"
    assert ck_sharia in _EOD_SCAN_CACHE_KEYS
    assert is_recommendation_cache_key(ck_sharia) is True
    assert is_cache_write_intent_safe(sharia_q, ck_sharia, market="EGX") is True
    assert build_analysis_cache_key("توصيات شرعية لسهم فوري", market="EGX") != "vip_open_recommendations_sharia"

    # VLMRA resolves directly to vip_stock_VLMRA for Single-Stock Fast-Track
    assert build_analysis_cache_key("حلل سهم Vlmra", market="EGX") == "vip_stock_VLMRA"

    # Dynamic DB ticker loader merges newly listed Supabase tickers when not in test mode
    import api.agentic_chat.analysis_cache as ac_mod

    class _MockStocksRes:
        data = [{"symbol": "NEWX"}, {"symbol": "COMI"}]

    class _MockStocksQuery:
        def select(self, *_a): return self
        def limit(self, *_a): return self
        def execute(self): return _MockStocksRes()

    class _MockStocksSB:
        def table(self, _name): return _MockStocksQuery()

    old_set, old_at = ac_mod._DYNAMIC_TICKERS_SET, ac_mod._DYNAMIC_TICKERS_AT
    try:
        ac_mod._DYNAMIC_TICKERS_AT = 0.0
        with (
            patch.object(ac_mod, "is_test_environment", return_value=False),
            patch("api.stock_ai._init_supabase", return_value=None),
            patch("api.stock_ai.supabase", _MockStocksSB()),
        ):
            dyn = ac_mod._get_valid_latin_tickers()
            assert "NEWX" in dyn
    finally:
        ac_mod._DYNAMIC_TICKERS_SET = old_set
        ac_mod._DYNAMIC_TICKERS_AT = old_at


def test_pillar2_history_compaction_never_triggers_fake_truncation() -> None:
    # A 3,800-char latest assistant reply (like [35] with 3 recommended stocks) stays 100% intact
    reply_3800 = ("جدول المرشحين: LCSW و FAIT و ORAS\n" + ("تفاصيل فنية وأرقام " * 190))[:3800]
    out_latest = _compact_history_content(reply_3800, is_recent=True, is_latest_turn=True)
    assert out_latest == reply_3800
    assert "..." not in out_latest

    # Even a 6,000-char latest reply preserves tickers and NEVER emits bare "..."
    reply_6000 = "LCSW FAIT ORAS " + ("سطر تحليل مفصل طويل جدا " * 260)
    out_long = _compact_history_content(reply_6000, is_recent=True, is_latest_turn=True)
    assert "..." not in out_long
    assert "LCSW" in out_long and "FAIT" in out_long and "ORAS" in out_long
    assert "الرد الأصلي وصل للمستخدم كاملاً" in out_long

    # Older turns stay compact AND never emit bare "..."
    out_old = _compact_history_content("A" * 2000, is_recent=False)
    assert len(out_old) <= 560
    assert "..." not in out_old


def test_pillar3_output_guard_localizes_all_portfolio_enum_codes() -> None:
    raw_reply = (
        "| السهم | القرار |\n|---|---|\n"
        "| FAIT | **HOLD_CORE** |\n"
        "| LCSW | **TRIM_EXCESS** |\n"
        "| ICFC | **HOLD_WATCH** |\n"
        "| AJWA | **EXIT_PRIORITY** |\n"
    )
    res = verify_and_guard_reply(raw_reply, [])
    guarded = res["reply"]
    for bad_code in ("HOLD_CORE", "TRIM_EXCESS", "HOLD_WATCH", "EXIT_PRIORITY"):
        assert bad_code not in guarded
    assert "احتفاظ أساسي" in guarded
    assert "تخفيف التركّز" in guarded
    assert "مراقبة دون تعزيز" in guarded
    assert "أولوية خروج" in guarded


def test_pillar4_deterministic_one_edit_arabic_fuzzy_rescue() -> None:
    assert resolve_stock_symbol("ايه رايك فى الماليه الصناغيه") == "EFIC"
    assert resolve_stock_symbol("ايه رايك فى الماليه الصناغيه؟") == "EFIC"
    assert resolve_stock_symbol("سهم القاهره للزيةت") == "COSG"
    assert resolve_stock_symbol("سهم القاهره للزيةت؟") == "COSG"
    assert resolve_stock_symbol("Vlmra") == "VLMRA"
    assert resolve_stock_symbol("فالمور أ") == "VLMRA"
    assert resolve_stock_symbol("حلل سهم فالمور أ؟") == "VLMRA"
    # Critical false-positive guards (never hijack حالياً/حالي -> HALN or Class B / prefix words -> VLMRA!)
    assert resolve_stock_symbol("افضل سهم حالياً للشراء") is None
    assert resolve_stock_symbol("رشحلي سهم حاليا للشراء") is None
    assert resolve_stock_symbol("عايز احسن شركة حالياً") is None
    assert resolve_stock_symbol("سهم حالي") is None
    assert resolve_stock_symbol("سهم فالمور ب") is None
    assert resolve_stock_symbol("سهم فالمور القابضة ب") is None
    assert resolve_stock_symbol("سهم فالمور أحسن ولا فوري") == "FWRY"
    assert resolve_stock_symbol("بنان على الدعوم والمقاومات") is None


def test_pillar5_manage_automations_create_is_idempotent_in_one_call() -> None:
    existing = [
        {"id": "a1", "name": "تقرير 1", "prompt": "أقوى 3 أسهم", "scheduled_time": "10:30", "days_of_week": "trading_days", "is_active": True},
        {"id": "a2", "name": "تقرير 2", "prompt": "أقوى 3 أسهم", "scheduled_time": "12:15", "days_of_week": "trading_days", "is_active": True},
        {"id": "a3", "name": "تقرير 3", "prompt": "أقوى 3 أسهم", "scheduled_time": "13:45", "days_of_week": "trading_days", "is_active": True},
    ]
    insert_called = False

    class _MockRes:
        def __init__(self, data):
            self.data = data

    class _MockQuery:
        def __init__(self, tbl):
            self._tbl = tbl
            self._is_insert = False
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def limit(self, *_a): return self
        def insert(self, rows):
            nonlocal insert_called
            insert_called = True
            self._is_insert = True
            return self
        def execute(self):
            if self._tbl == "profiles":
                return _MockRes([{"telegram_chat_id": "123456", "is_pro": True}])
            if self._tbl == "subscriptions":
                return _MockRes([{"status": "active", "plan_type": "pro", "expires_at": "2099-01-01T00:00:00Z"}])
            if self._tbl == "scheduled_chat_automations":
                return _MockRes(existing)
            return _MockRes([])

    class _MockSB:
        def from_(self, tbl): return _MockQuery(tbl)

    with (
        patch("api.agentic_chat.tools_execution._get_sb", return_value=_MockSB()),
        patch("api.plan_limits.has_chat_pro_user", return_value=True),
    ):
        res = _sync_manage_automations(
            user_id="u-auto",
            operation="create",
            prompt="أقوى 3 أسهم بالزخم والسيولة",
            scheduled_times=["10:30", "12:15", "13:45"],
        )

    assert res["status"] == "already_exists"
    assert res["created_count"] == 0
    assert res["already_exists_times"] == ["10:30", "12:15", "13:45"]
    assert res["skip_followup_list"] is True
    assert insert_called is False


def test_answer_stages_persisted_and_reconstructed_on_reload() -> None:
    from api.agentic_chat.router import (
        _build_persisted_answer_stages,
        _extract_message_answer_stages,
    )

    # 1. Full 4-stage tool + quant flow
    full_events = [
        {"type": "status", "status": "thinking", "step_id": "understand", "message": "فهم السؤال وتحديد سهم COMI"},
        {"type": "status", "status": "executing_tools", "step_id": "fetch_data", "message": "جلب البيانات الحية (الأسعار والمؤشرات • القيمة العادلة)"},
        {"type": "status", "status": "quant_engine", "step_id": "quant_verify", "message": "تشغيل المحرك الكمي ومحاكاة مونت كارلو (5,000 مسار)"},
        {"type": "status", "status": "generating", "step_id": "synthesize", "message": "جاري صياغة التقرير النهائي ومراجعة الحارس الآلي للأرقام..."},
    ]
    full_stages = _build_persisted_answer_stages(full_events, tools_used=["get_stock", "get_fair_value"], cached=False)
    assert [s["id"] for s in full_stages] == ["understand", "fetch_data", "quant_verify", "synthesize"]
    assert all(s["status"] == "done" for s in full_stages)
    assert "الأسعار والمؤشرات" in full_stages[1]["label"]

    # 2. Cached 3-stage shortcut
    cached_events = [
        {"type": "status", "status": "thinking", "step_id": "understand", "message": "فهم السؤال"},
        {"type": "status", "status": "cached", "step_id": "fetch_data", "message": "تم استرجاع أحدث قراءة فنية موثقة من الذاكرة اللحظية..."},
    ]
    cached_stages = _build_persisted_answer_stages(cached_events, cached=True)
    assert [s["id"] for s in cached_stages] == ["understand", "fetch_data", "synthesize"]
    assert all(s["status"] == "done" for s in cached_stages)
    assert "الذاكرة اللحظية" in cached_stages[1]["label"]

    # 3. Direct conversational reply (no tools, no cache) -> 2 stages
    direct_stages = _build_persisted_answer_stages(
        [{"type": "status", "status": "thinking", "step_id": "understand", "message": "thinking"}],
        cached=False,
    )
    assert [s["id"] for s in direct_stages] == ["understand", "synthesize"]
    # Raw English status code must NOT overwrite Arabic label
    assert direct_stages[0]["label"] != "thinking"

    # 4. Stored metadata returns exact persisted stages; user role returns None
    assert _extract_message_answer_stages("user", {"answer_stages": full_stages}) is None
    extracted = _extract_message_answer_stages("assistant", {"answer_stages": full_stages})
    assert extracted == full_stages

    # 5. Legacy historical assistant rows without answer_stages reconstruct cleanly
    legacy_tools = _extract_message_answer_stages(
        "assistant",
        {"engine": "deepseek-v3", "cached": False, "usage": {"tools_used": ["get_stock", "get_fair_value"]}},
    )
    assert legacy_tools is not None
    assert [s["id"] for s in legacy_tools] == ["understand", "fetch_data", "quant_verify", "synthesize"]
    assert all(s["status"] == "done" for s in legacy_tools)

    legacy_cached = _extract_message_answer_stages("assistant", {"engine": "deepseek-v3", "cached": True})
    assert legacy_cached is not None
    assert [s["id"] for s in legacy_cached] == ["understand", "fetch_data", "synthesize"]


def test_audit_2026_11_27_eve_guard_false_positives_and_valuation_math() -> None:
    # 1. Check E real-world [05] replay: healthy downtrend stocks (POUL/ABUK/ORHD) with shadda negation -> 0 false alarms!
    opt_payload = {
        "excludedFromBuying": [
            {"symbol": "POUL", "reason": "السعر تحت EMA50 وEMA200 (اتجاه هابط — مراقبة دون تعزيز)"},
            {"symbol": "ORHD", "reason": "اتجاه هابط تحت المتوسطات الرئيسية (HOLD_WATCH)"},
            {"symbol": "ABUK", "reason": "تحت المتوسطات الرئيسية — مراقبة دون تعزيز"},
            {"symbol": "PRCL", "reason": "حقوق ملكية سالبة — أولوية تصفية"},
        ],
        "positions": [
            {"symbol": "POUL", "rotation_action": "HOLD_WATCH", "is_loss_making": False, "is_negative_equity": False, "is_illiquid": False},
            {"symbol": "ORHD", "rotation_action": "HOLD_WATCH", "is_loss_making": False, "is_negative_equity": False, "is_illiquid": False},
            {"symbol": "ABUK", "rotation_action": "HOLD_WATCH", "is_loss_making": False, "is_negative_equity": False, "is_illiquid": False},
            {"symbol": "PRCL", "rotation_action": "EXIT_PRIORITY", "is_negative_equity": True},
        ],
    }
    compliant_reply = (
        "- **POUL** (93/100) و**ABUK** (73/100) و**ORHD** (86/100): **احتفظ بيهم ولا تعزّز** — "
        "أساسياتهم ممتازة لكن السعر تحت EMA50 وEMA200، فالمحرك منع التعزيز التلقائي لحين استعادة الاتجاه."
    )
    res_ok = verify_and_guard_reply(compliant_reply, [opt_payload])
    assert res_ok["warnings"] == []
    assert "تنبيه اتساق المحفظة التلقائي" not in res_ok["reply"]

    # Genuine buy cue on healthy downtrend POUL gets accurate technical banner (NEVER accused of losses/liquidation!)
    bad_tech_buy = "نوصي بشراء وتعزيز POUL الآن بـ 5,000 ج.م."
    res_tech = verify_and_guard_reply(bad_tech_buy, [opt_payload])
    assert "downtrend_stock_buy_conflict:POUL" in res_tech["warnings"]
    assert "excluded_stock_buy_conflict:POUL" not in res_tech["warnings"]
    assert "خسائر صافية" not in res_tech["reply"]
    assert "مراقبة دون تعزيز" in res_tech["reply"]

    # Genuine buy cue on fundamental PRCL still triggers severe fundamental warning!
    bad_fund_buy = "قم بشراء وتعزيز PRCL الآن."
    res_fund = verify_and_guard_reply(bad_fund_buy, [opt_payload])
    assert "excluded_stock_buy_conflict:PRCL" in res_fund["warnings"]
    assert "تنبيه اتساق المحفظة التلقائي" in res_fund["reply"]

    # QA Issue 1 regression: bare "مراقبة" / "احتفظ بـ" must NOT bypass genuine buy hallucinations on PRCL!
    res_bypass1 = verify_and_guard_reply("نوصي بشراء PRCL الآن مع مراقبة الدعم 5.0", [opt_payload])
    assert "excluded_stock_buy_conflict:PRCL" in res_bypass1["warnings"]
    res_bypass2 = verify_and_guard_reply("احتفظ بـ PRCL وزود الكمية بشراء 500 سهم الآن", [opt_payload])
    assert "excluded_stock_buy_conflict:PRCL" in res_bypass2["warnings"]

    # QA Issue 1 regression: order-independence between positions and excludedFromBuying + weak_fund_downtrend stays fundamental!
    from api.agentic_chat.output_guard import _classify_excluded_portfolio_symbols

    pos_only = {"positions": [{"symbol": "POUL", "rotation_action": "HOLD_WATCH", "is_loss_making": False, "is_negative_equity": False, "is_illiquid": False}]}
    excl_only = {"excludedFromBuying": [
        {"symbol": "POUL", "reason": "مستبعد من الشراء"},
        {"symbol": "WEAK", "reason": "تقييم مالي ضعيف (32/100) ومسار هابط تحت المتوسط 50 — مستبعد من الشراء أو التعزيز"},
    ]}
    f1, t1 = _classify_excluded_portfolio_symbols([excl_only, pos_only])
    f2, t2 = _classify_excluded_portfolio_symbols([pos_only, excl_only])
    assert f1 == f2 and t1 == t2
    assert "POUL" in t1 and "POUL" not in f1
    assert "WEAK" in f1 and "WEAK" not in t1

    # 2. Check F real-world [22] COSG replay: colloquial negation ("مش رخيص ... عكس تماماً") -> 0 false alarms!
    cosg_payload = {"symbol": "COSG", "close": 1.34, "fair_value": 0.55, "upside_pct": -58.96, "currency": "ج.م"}
    cosg_compliant = (
        "القيمة العادلة 0.55 ج.م والسعر 1.34 ج.م (أعلى منها بـ +143.6%).\n"
        "السهم مش رخيص — هو غالي على شركة خاسرة. ده عكس تماماً فكرة «قيمته أقل من قيمته العادلة»."
    )
    res_cosg_ok = verify_and_guard_reply(cosg_compliant, [cosg_payload])
    assert res_cosg_ok["warnings"] == []
    assert "تدقيق التقييم الحتمي" not in res_cosg_ok["reply"]

    # Genuine hallucination calling overvalued COSG cheap -> banner states EXACT +143.6% above FV (and 59.0% below price)!
    cosg_halluc = "سهم COSG يعتبر سهم رخيص جداً وفرصة قيمة بخصم كبير."
    res_cosg_bad = verify_and_guard_reply(cosg_halluc, [cosg_payload])
    assert "valuation_direction_contradiction:COSG" in res_cosg_bad["warnings"]
    assert "+143.6%" in res_cosg_bad["reply"]
    assert "59.0%" in res_cosg_bad["reply"]

    # QA Issue 2 regression: never emit "+-50.0%" when close<=fv or contradictory "+99.5%" when upside<=-99
    res_edge1 = verify_and_guard_reply("سهم رخيص جداً", [{"symbol": "TEST", "close": 0.5, "fair_value": 1.0, "upside_pct": -50.0}])
    assert "+-" not in res_edge1["reply"]
    assert "+100.0%" in res_edge1["reply"]
    res_edge2 = verify_and_guard_reply("سهم رخيص جداً", [{"symbol": "TEST", "close": 10.0, "upside_pct": -99.5}])
    assert "+99.5%" not in res_edge2["reply"]
    assert "99.5%" in res_edge2["reply"]


def test_audit_2026_11_27_eve_cache_read_guard_penny_precision_dividends_and_dedupe() -> None:
    import time as _t
    import api.agentic_chat.analysis_cache as ac_mod
    from api.agentic_chat.pipeline import _dedupe_redundant_levels_calls
    from api.agentic_chat.tools_execution import _lookup_upcoming_dividend, _safe_price, _sync_get_dividends
    from api.portfolio_or_optimizer import AssetInput, build_smart_dca_plan, optimize_portfolio_or

    # 1. Read- & write-time sanity guard rejects poisoned payloads across ALL scoped keys
    poisoned = "## 🧭 أنشط قطاع في البورصة المصرية — جلسة 2026-11-26\n" + ("تفاصيل قطاعية " * 30)
    assert ac_mod.is_cached_reply_consistent_with_key("vip_accumulation", poisoned) is False
    assert ac_mod.is_cached_reply_consistent_with_key("std_recs:vip_accumulation", poisoned) is False
    assert ac_mod.is_cached_reply_consistent_with_key("b2b_norecs:vip_accumulation", poisoned) is False
    assert ac_mod.is_cached_reply_consistent_with_key("mkt_TADAWUL__vip_open_recommendations_sharia", poisoned) is False
    # Valid Sharia report mentioning exclusion of non-Sharia stocks must NOT be false-rejected
    valid_sharia = "التوصيات الشرعية المفتوحة — تم استبعاد أي سهم غير متوافق مع الشريعة بالكامل.\n" + ("توصية " * 30)
    assert ac_mod.is_cached_reply_consistent_with_key("vip_open_recommendations_sharia", valid_sharia) is True
    assert ac_mod.is_cached_reply_consistent_with_key("vip_accumulation", "## 🔥 أقوى أسهم التجميع والسيولة الذكية\n" + ("أسهم " * 30)) is True

    # Write-time defense-in-depth: set_vip_analysis_cache refuses poisoned payload
    ac_mod.set_vip_analysis_cache("vip_accumulation", poisoned, market="EGX")
    assert "vip_accumulation" not in ac_mod._memory_cache

    with ac_mod._memory_lock:
        ac_mod._memory_cache["vip_accumulation"] = {
            "reply": poisoned,
            "tables": [],
            "recommendations": [],
            "computed_at": _t.time(),
            "key": "vip_accumulation",
        }
    assert ac_mod.get_vip_analysis_cache("vip_accumulation", market="EGX") is None
    assert "vip_accumulation" not in ac_mod._memory_cache

    # Pure sector query maps to vip_top_sectors; bespoke/comparison/dividend/timeframe/why modifiers stay None
    assert build_analysis_cache_key("أنشط قطاع في البورصة المصرية", market="EGX") == "vip_top_sectors"
    assert is_cache_write_intent_safe("أنشط قطاع في البورصة المصرية", "vip_top_sectors", market="EGX") is True
    assert build_analysis_cache_key("ما هو أنشط قطاع بين البنوك والعقارات؟", market="EGX") is None
    assert build_analysis_cache_key("أفضل قطاع توزيعات أرباح", market="EGX") is None
    assert build_analysis_cache_key("أفضل قطاع خلال شهر", market="EGX") is None
    assert build_analysis_cache_key("ما هو أنشط قطاع في البورصة المصرية حالياً ولماذا؟", market="EGX") is None

    # 2. Penny-stock 4-decimal precision & finite guard preserved in optimizer, smart DCA & _safe_price
    assert _safe_price(float("inf")) is None
    assert _safe_price(float("nan")) is None
    assert _safe_price(0.634) == 0.634
    opt_res = optimize_portfolio_or(
        assets=[
            AssetInput(symbol="IEEC", price=0.634, current_shares=18771),
            AssetInput(symbol="PHGC", price=0.077, current_shares=100000),
        ],
        total_capital=19600.81,
        exchange="EGX",
    )
    by_sym = {row["symbol"]: row for row in opt_res.get("allocations", [])}
    assert by_sym["IEEC"]["price"] == 0.634
    assert by_sym["PHGC"]["price"] == 0.077

    dca_res = build_smart_dca_plan(
        symbol="IEEC",
        current_price=0.634,
        old_shares=18771,
        old_avg_price=0.7277,
        setup_regime="high_risk_avoid",
        fund_score=39.0,
    )
    assert dca_res["current_price"] == 0.634
    assert dca_res["old_avg_price"] == 0.7277

    # 3. Expired dividend (pay_date < today) excluded in BOTH _lookup_upcoming_dividend and _sync_get_dividends;
    #    paid row before newer upcoming row for SAME symbol does NOT prematurely break!
    fake_cal = {
        "dividends": [
            {"symbol": "COMI", "exchange": "EGX", "amount": 1.00, "ex_date": "2026-03-01", "pay_date": "2026-03-10", "status": "paid"},
            {"symbol": "COMI", "exchange": "EGX", "amount": 2.50, "ex_date": "2099-12-01", "pay_date": "2099-12-10", "status": "upcoming"},
            {"symbol": "BIOC", "exchange": "EGX", "amount": 0.75, "ex_date": "2026-11-24", "pay_date": "2026-11-26", "status": "pending_pay"},
            {"symbol": "FAIT", "exchange": "EGX", "amount": 2.00, "ex_date": "2099-12-01", "pay_date": "2099-12-10", "status": "upcoming"},
        ]
    }
    with patch("api.agentic_chat.tools_execution._load_dividends_calendar_cached", return_value=fake_cal):
        assert _lookup_upcoming_dividend("BIOC", "EGX") is None
        comi_div = _lookup_upcoming_dividend("COMI", "EGX")
        assert comi_div is not None and comi_div["amount"] == 2.50
        fait_div = _lookup_upcoming_dividend("FAIT", "EGX")
        assert fait_div is not None and fait_div["amount"] == 2.00
        div_list = _sync_get_dividends(upcoming_only=True, market="EGX")
        div_syms = [d["symbol"] for d in div_list["dividends"]]
        assert "BIOC" not in div_syms and "COMI" in div_syms and "FAIT" in div_syms

    # 4. Cross-round get_stock_levels dedupe: does NOT pre-mutate before execution & isolates markets (ADIB EGX vs ADX)!
    covered: set = set()
    active_r1, sc_r1 = _dedupe_redundant_levels_calls([(0, "get_stock", {"symbol": "ADIB", "market": "EGX"})], already_covered_syms=covered, default_market="EGX")
    assert len(active_r1) == 1 and not sc_r1 and len(covered) == 0  # must NOT pre-mutate before execution!
    # Simulate Round 1 EGX get_stock succeeded
    covered.add(("EGX", "ADIB"))
    # Round 2 ADIB on EGX is deduplicated, while ADIB on ADX is NOT blocked!
    active_egx, sc_egx = _dedupe_redundant_levels_calls([(0, "get_stock_levels", {"symbol": "ADIB", "market": "EGX"})], already_covered_syms=covered, default_market="EGX")
    assert len(active_egx) == 0 and 0 in sc_egx
    active_adx, sc_adx = _dedupe_redundant_levels_calls([(0, "get_stock_levels", {"symbol": "ADIB", "market": "ADX"})], already_covered_syms=covered, default_market="EGX")
    assert len(active_adx) == 1 and not sc_adx
