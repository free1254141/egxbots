import os
import sys

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
