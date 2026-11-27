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
