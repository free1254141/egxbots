"""
Offline deterministic unit tests for the 2026-11-22 production chat audit fixes.
No live LLM, network, or Supabase calls are executed.
"""

import json
from unittest.mock import patch


# ---------------------------------------------------------------------------
# 1. Entity Resolution Aliases (CRST, MCRO, INEG, HALN)
# ---------------------------------------------------------------------------

def test_aliases_resolve_audit_symbols():
    from api.stock_aliases import resolve_stock_symbol
    from api.agentic_chat.analysis_cache import build_analysis_cache_key
    from api.telegram_vip_chat import detect_topic_query_intent

    assert resolve_stock_symbol("هل كريست ممكن يرفع تاني") == "CRST"
    assert resolve_stock_symbol("سهم كريست") == "CRST"
    assert resolve_stock_symbol("تحليل سهم Macro") == "MCRO"
    assert resolve_stock_symbol("أخبار سهم المتكاملة للأعمال الهندسية") == "INEG"
    assert resolve_stock_symbol("ما هو تحليلك لسهم حالا") == "HALN"
    assert resolve_stock_symbol("سهم إم إن تي حالا") == "HALN"

    # Negative guards: everyday adverb "حالا / حالاً" ("right now") must NEVER collide with HALN
    assert resolve_stock_symbol("هل السوق فاتح حالا") is None
    assert resolve_stock_symbol("حالات الطوارئ") is None
    assert build_analysis_cache_key("الوضع ايه حالا") is None
    assert build_analysis_cache_key("سعر سهم فوري حالاً") == "vip_stock_FWRY"
    assert build_analysis_cache_key("افضل سهم للدخول حالاً") == "vip_open_recommendations"
    assert build_analysis_cache_key("رشحلي سهم حالا") is None
    assert detect_topic_query_intent("عايز التوصيات حالا") == ("free", "عايز التوصيات حالا")


# ---------------------------------------------------------------------------
# 2. Deterministic Stop-Loss vs Support Distance Metrics
# ---------------------------------------------------------------------------

def test_compute_stock_context_metrics_stop_loss_distance_ftns_case():
    from api.agentic_chat.tools_execution import _compute_stock_context_metrics

    # Real audit #126 numbers: FTNS close=0.914, S1=0.903 (-1.2%), stop_loss=0.8849 (-3.18%)
    metrics = _compute_stock_context_metrics(
        close=0.914,
        ema_50=0.99,
        ema_200=1.05,
        vwap_20=0.96,
        support_1=0.903,
        resistance_1=1.02,
        stop_loss=0.8849,
    )
    assert metrics["dist_to_support_pct"] == -1.2
    assert metrics["dist_to_stop_loss_pct"] == -3.18
    assert metrics["dist_to_resistance_pct"] == 11.6
    dist_ar = metrics["levels_distance_ar"]
    assert "الدعم الأول (0.903): -1.20%" in dist_ar
    assert "وقف الخسارة (0.8849): -3.18%" in dist_ar


# ---------------------------------------------------------------------------
# 3. Pipeline Token/Cost Reduction Helpers
# ---------------------------------------------------------------------------

def test_dedupe_redundant_levels_calls():
    from api.agentic_chat.pipeline import _dedupe_redundant_levels_calls

    prepared = [
        (0, "get_stock", {"symbols": ["COMI", "FWRY"]}),
        (1, "get_stock_levels", {"symbols": ["COMI"]}),
        (2, "get_stock_levels", {"symbols": ["FWRY", "SWDY"]}),
        (3, "get_stock_levels", {"symbol": "TMGH"}),
        (4, "get_news", {"symbols": ["COMI"]}),
    ]
    active, short_circuits = _dedupe_redundant_levels_calls(prepared)

    assert 1 in short_circuits
    assert short_circuits[1]["status"] == "already_included_in_get_stock"

    active_by_idx = {idx: (fn, args) for idx, fn, args in active}
    assert 0 in active_by_idx
    assert 1 not in active_by_idx
    # FWRY stripped because already in get_stock; SWDY preserved
    assert active_by_idx[2] == ("get_stock_levels", {"symbols": ["SWDY"]})
    # Uncovered standalone TMGH preserved
    assert active_by_idx[3] == ("get_stock_levels", {"symbol": "TMGH"})
    assert 4 in active_by_idx


def test_strip_ui_and_compact_preserves_meaningful_nulls():
    from api.agentic_chat.pipeline import _strip_ui_only_fields_for_llm, _compact_history_content

    payload = {
        "status": "success",
        "stocks": [
            {
                "symbol": f"S{i}",
                "close": 10.5,
                "fair_value": None,
                "purification_rate_pct": None,
                "unused_note": None,
                "_ui_chart": {"candles": [1, 2, 3]},
                "fundamental_diagnosis": {
                    "verdict": "strong",
                    "optional_note": None,
                    "strengths": ["a", "b", "c", "d"],
                    "weaknesses": ["w1", "w2", "w3", "w4", "w5"],
                    "risks": ["r1", "r2", "r3"],
                },
            }
            for i in range(6)
        ],
    }
    cleaned = _strip_ui_only_fields_for_llm(payload)
    first = cleaned["stocks"][0]
    assert "_ui_chart" not in first
    assert "unused_note" not in first
    # Critical financial/sharia nulls preserved explicitly so model won't hallucinate
    assert "purification_rate_pct" in first and first["purification_rate_pct"] is None
    assert "fair_value" in first and first["fair_value"] is None
    # Large batch (>=5 stocks) trims diagnosis lists to max 2 items (including production "weaknesses")
    assert len(first["fundamental_diagnosis"]["strengths"]) == 2
    assert len(first["fundamental_diagnosis"]["weaknesses"]) == 2
    assert len(first["fundamental_diagnosis"]["risks"]) == 2
    assert "optional_note" not in first["fundamental_diagnosis"]

    # History compaction limits
    long_msg = "A" * 3000
    assert len(_compact_history_content(long_msg, is_recent=True)) <= 2280
    assert len(_compact_history_content(long_msg, is_recent=False)) <= 560


# ---------------------------------------------------------------------------
# 4. VIP Cache Expansion & Scheduled Automations Cache Reuse
# ---------------------------------------------------------------------------

def test_analysis_cache_key_expanded_buttons_and_market_prompts():
    from api.agentic_chat.analysis_cache import build_analysis_cache_key

    assert build_analysis_cache_key("رايك في أداء السوق الان") == "vip_market_summary"
    assert build_analysis_cache_key("ايه رأيك في السوق دلوقتي") == "vip_market_summary"
    assert build_analysis_cache_key("افضل سهم للدخول الان") == "vip_open_recommendations"
    assert build_analysis_cache_key("📈 ترشيح فرص بديلة") == "vip_open_recommendations"
    # New aliases normalize seamlessly in cache keys too
    assert build_analysis_cache_key("تحليل سهم Macro") == "vip_stock_MCRO"
    assert build_analysis_cache_key("حلل سهم حالا") == "vip_stock_HALN"
    # Multi-intent stock/comparison queries must NOT be hijacked into vip_market_summary
    assert build_analysis_cache_key("ايه رايك في السوق واشتري فوري") is None
    assert build_analysis_cache_key("مقارنة اداء السوق مع سهم COMI") is None


def test_scheduled_automations_cache_safety_and_hourly_prefix():
    import api.scheduled_automations_worker as worker

    assert worker._is_cacheable_automation_prompt("أقوى الأسهم النهارده") is True
    assert worker._is_cacheable_automation_prompt("حلل أسهم محفظتي المسجلة") is False
    assert worker._is_cacheable_automation_prompt("اعلى عشرة اسهم حاصلين على سكور") is False
    assert worker._is_cacheable_automation_prompt("أعلى 5 أسهم اليوم") is False

    # Generic scheduled prompt hits VIP cache when available -> zero DeepSeek call
    worker._AUTO_METRICS_TLS.last_cached = False
    worker._AUTO_METRICS_TLS.last_cache_key = None
    with patch("api.agentic_chat.analysis_cache.get_vip_analysis_cache", return_value={"reply": "رد من الكاش", "key": "vip_top_stocks"}) as m_cache:
        reply = worker._generate_ai_consultation("أقوى الأسهم النهارده", "Tester", user_id="u1")
        assert reply == "رد من الكاش"
        assert worker._AUTO_METRICS_TLS.last_cached is True
        assert worker._AUTO_METRICS_TLS.last_cache_key == "vip_top_stocks"
        assert m_cache.call_args[0][0] == "vip_top_stocks"

    # Non-cached automation prompt builds hourly-bucket timestamp for DeepSeek Prefix Cache
    captured_payloads = []

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "choices": [{"message": {"content": "تحليل المحفظة"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "prompt_cache_hit_tokens": 80},
            }

    def fake_post(url, headers=None, json=None, timeout=None):
        captured_payloads.append(json)
        return FakeResp()

    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}), \
         patch.object(worker, "_fetch_market_indicators_brief", return_value=""), \
         patch.object(worker.requests, "post", side_effect=fake_post):
        out = worker._generate_ai_consultation("حلل أسهم محفظتي المسجلة", "Tester", user_id="u1")
        assert out == "تحليل المحفظة"
        sys_msg = captured_payloads[0]["messages"][0]["content"]
        assert ":00 القاهرة." in sys_msg


# ---------------------------------------------------------------------------
# 5. Telegram /sharia Fix & Non-Greeting Error Fallback
# ---------------------------------------------------------------------------

def test_telegram_non_ticker_words_and_greeting_fallback():
    from api.telegram_vip_chat import detect_topic_query_intent
    from api.native_telegram_vip_chat import _is_greeting_or_start_query

    # SHARIA / slash commands must NOT expand to "حلل سهم SHARIA"
    assert detect_topic_query_intent("SHARIA") == ("free", "SHARIA")
    assert detect_topic_query_intent("/sharia") == ("free", "/sharia")
    assert detect_topic_query_intent("halal") == ("free", "halal")
    # Real bare tickers still expand
    assert detect_topic_query_intent("HALN") == ("stock", "حلل سهم HALN")
    assert detect_topic_query_intent("COMI") == ("stock", "حلل سهم COMI")

    # Welcome greeting ONLY for greetings / /start, NEVER for real stock queries
    assert _is_greeting_or_start_query("/start") is True
    assert _is_greeting_or_start_query("أهلاً") is True
    assert _is_greeting_or_start_query("") is True
    assert _is_greeting_or_start_query("ما هو تحليلك لسهم حالا") is False
    assert _is_greeting_or_start_query("حلل سهم فوري") is False


# ---------------------------------------------------------------------------
# 6. Output Guard Expansion (r_vol, upcoming_events, without doubling labels)
# ---------------------------------------------------------------------------

def test_output_guard_sanitizes_r_vol_and_upcoming_events():
    from api.agentic_chat.output_guard import verify_and_guard_reply

    raw = (
        "| السيولة النسبية (r_vol) | 4.78x |\n"
        "- حقل موعد نتائج الأعمال (`upcoming_events` أو ما يعادله)"
    )
    res = verify_and_guard_reply(raw, tool_payloads=[], market="EGX")
    cleaned = res["reply"]

    assert "r_vol" not in cleaned
    assert "upcoming_events" not in cleaned
    # Avoid ugly "السيولة النسبية (السيولة النسبية)" duplication
    assert "السيولة النسبية (السيولة النسبية)" not in cleaned
    assert "السيولة النسبية" in cleaned
    assert "الأحداث القادمة ومواعيد النتائج" in cleaned
    assert any("r_vol" in w for w in res["warnings"])
    assert any("upcoming_events" in w for w in res["warnings"])


def test_automation_quota_rule_in_prompt_and_output_guard():
    from api.agentic_chat.prompts import AGENTIC_SYSTEM_PROMPT
    from api.agentic_chat.output_guard import verify_and_guard_reply

    assert "كل تنفيذ لتقرير مجدول يخصم رسالة واحدة" in AGENTIC_SYSTEM_PROMPT
    assert "يُمنع منعاً باتاً القول إن الأتمتة المجدولة لا تستهلك من الكوتة" in AGENTIC_SYSTEM_PROMPT

    wrong_reply = (
        "## اللي مش بيستهلك من الكوتة خالص\n"
        "- **قناة تليجرام VIP** — بث إشارات.\n"
        "- **الأتمتة المجدولة (Scheduled Automations)** — التقارير اليومية اللي بتتجدول بتتنفذ تلقائياً ومش بتاكل من كوتة الشات.\n"
    )
    res = verify_and_guard_reply(wrong_reply, tool_payloads=[], market="EGX")
    assert "مش بتاكل من كوتة الشات" not in res["reply"]
    assert "تستهلك من الكوتة" in res["reply"]
    assert "يخصم رسالة واحدة" in res["reply"]
    assert "automation_quota_misstatement_fixed" in res["warnings"]
    assert res["block_cache"] is True

