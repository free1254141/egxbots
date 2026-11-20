"""
api/agentic_chat/pipeline.py
Core Agentic Chat Pipeline for DeepSeek V3 with Function Calling and SSE Streaming.
100% Async, Non-blocking, and Prefix-Cache Optimized.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple
import httpx
import pytz

from api.agentic_chat.prompts import AGENTIC_SYSTEM_PROMPT
from api.agentic_chat.tools_schema import AGENTIC_TOOLS_SCHEMA
from api.agentic_chat.tools_execution import (
    CAIRO_TZ,
    RIYADH_TZ,
    _BUILTIN_SAUDI_ALIASES,
    _EXT_SAUDI_MAPPINGS,
    _normalize_market_code,
    _resolve_symbol_and_market,
    _ui_market_label,
    dispatch_tool,
    reset_active_market_context,
    reset_allow_recommendations_context,
    reset_group_portfolio_blocked_context,
    reset_telegram_portfolio_context,
    set_active_market_context,
    set_allow_recommendations_context,
    set_group_portfolio_blocked_context,
    set_telegram_portfolio_context,
)
from api.agentic_chat.auth_guard import filter_output, strip_dsml
from api.agentic_chat.vision import (
    analyze_image,
    reconcile_vision_with_market,
    safe_image_evidence_reply,
    safe_portfolio_image_reply,
    format_vision_context_for_prompt,
)
from api.stock_ai import _init_supabase, supabase
from api.agentic_chat.market_registry import (
    currency_for_market,
    detect_market_from_text,
    get_market_config,
    normalize_exchange_code,
    ui_market_label,
)
from api.agentic_chat.analysis_cache import (
    get_vip_analysis_cache,
    is_recommendation_cache_key,
    is_uncacheable_error_reply,
    set_vip_analysis_cache,
    build_analysis_cache_key,
    inspect_tool_calls_followup_flags,
    resolve_tool_call_to_cache_key,
    resolve_tool_calls_to_cache_key,
    get_cached_analysis,
    set_cached_analysis,
)

logger = logging.getLogger("agentic_chat")

# Official DeepSeek-V3 (deepseek-chat) API pricing in USD per token
DEEPSEEK_CACHE_HIT_USD_PER_TOKEN = 0.028 / 1_000_000
DEEPSEEK_CACHE_MISS_USD_PER_TOKEN = 0.28 / 1_000_000
DEEPSEEK_OUTPUT_USD_PER_TOKEN = 0.42 / 1_000_000


def _new_usage_accumulator() -> Dict[str, Any]:
    return {
        "llm_rounds": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
        "tools_used": [],
    }


def _accumulate_deepseek_usage(
    acc: Dict[str, Any],
    raw_usage: Optional[Dict[str, Any]],
    tools_called: Optional[List[str]] = None,
) -> None:
    """Aggregate DeepSeek response usage metrics across tool-calling and synthesis rounds."""
    if isinstance(raw_usage, dict) and raw_usage:
        acc["llm_rounds"] = int(acc.get("llm_rounds", 0)) + 1
        prompt_t = int(raw_usage.get("prompt_tokens") or 0)
        comp_t = int(raw_usage.get("completion_tokens") or 0)
        total_t = int(raw_usage.get("total_tokens") or (prompt_t + comp_t))
        hit_t = int(raw_usage.get("prompt_cache_hit_tokens") or 0)
        miss_raw = raw_usage.get("prompt_cache_miss_tokens")
        miss_t = int(miss_raw) if miss_raw is not None else max(prompt_t - hit_t, 0)

        acc["prompt_tokens"] += prompt_t
        acc["completion_tokens"] += comp_t
        acc["total_tokens"] += total_t
        acc["prompt_cache_hit_tokens"] += hit_t
        acc["prompt_cache_miss_tokens"] += miss_t

    if tools_called:
        existing = acc.setdefault("tools_used", [])
        for name in tools_called:
            if name:
                existing.append(str(name))


def _finalize_usage_cost(acc: Dict[str, Any], cached: bool = False) -> Dict[str, Any]:
    """Compute final USD cost and prefix-cache hit percentage from accumulated token counts."""
    prompt_t = int(acc.get("prompt_tokens") or 0)
    comp_t = int(acc.get("completion_tokens") or 0)
    total_t = int(acc.get("total_tokens") or (prompt_t + comp_t))
    hit_t = int(acc.get("prompt_cache_hit_tokens") or 0)
    miss_t = int(acc.get("prompt_cache_miss_tokens") or 0)

    cost_usd = round(
        (hit_t * DEEPSEEK_CACHE_HIT_USD_PER_TOKEN)
        + (miss_t * DEEPSEEK_CACHE_MISS_USD_PER_TOKEN)
        + (comp_t * DEEPSEEK_OUTPUT_USD_PER_TOKEN),
        6,
    )
    prefix_cache_hit_pct = round((hit_t / prompt_t) * 100.0, 1) if prompt_t > 0 else 0.0
    return {
        "llm_rounds": int(acc.get("llm_rounds") or 0),
        "prompt_tokens": prompt_t,
        "completion_tokens": comp_t,
        "total_tokens": total_t,
        "prompt_cache_hit_tokens": hit_t,
        "prompt_cache_miss_tokens": miss_t,
        "prefix_cache_hit_pct": prefix_cache_hit_pct,
        "cost_usd": cost_usd,
        "tools_used": list(acc.get("tools_used") or []),
        "vip_response_cached": bool(cached),
    }


_ARABIC_WEEKDAYS = ("الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")


def _compact_history_content(content: Any, *, is_recent: bool) -> str:
    """
    Preserve BOTH head and tail of truncated history messages so ARTORO never forgets
    numbered questions or conclusions at the bottom of its previous reply, while keeping
    older turns compact to cut multi-turn uncached prompt token costs.
    """
    text = str(content or "")
    max_len = 2800 if is_recent else 700
    if len(text) <= max_len:
        return text
    if is_recent:
        head_len, tail_len = 1500, 1250
        sep = "\n[...تم اختصار الوسط للاحتفاظ ببداية ونهاية الرد...]\n"
    else:
        head_len, tail_len = 420, 260
        sep = "\n...\n"
    return f"{text[:head_len].rstrip()}{sep}{text[-tail_len:].lstrip()}"


def _collect_structured_outputs(
    result: Any,
    tables_data: List[Any],
    recommendations_data: List[Any],
    visuals_data: Optional[Dict[str, Any]] = None,
    *,
    acc_fallback_rows: Optional[List[Any]] = None,
) -> None:
    """Collect structured stock/recommendation/visual rows from a single tool output."""
    if not isinstance(result, dict):
        return
    if "stocks" in result and isinstance(result["stocks"], list):
        tables_data.extend(result["stocks"])
    elif "accumulation_stocks" in result and isinstance(result["accumulation_stocks"], list):
        if acc_fallback_rows is not None:
            acc_fallback_rows.extend(result["accumulation_stocks"])
        else:
            tables_data.extend(result["accumulation_stocks"])
    if "recommendations" in result and isinstance(result["recommendations"], list):
        recommendations_data.extend(result["recommendations"])

    if visuals_data is None:
        return

    # 1. Portfolio Donut & Per-Position P&L Visuals (view operation)
    if result.get("operation") == "view" and isinstance(result.get("positions"), list) and result["positions"]:
        visuals_data["portfolio"] = {
            "cash_balance": result.get("cash_balance") or 0.0,
            "totals": result.get("totals") or {},
            "totals_by_market": result.get("totals_by_market"),
            "positions": [
                {
                    "symbol": p.get("symbol"),
                    "name": p.get("name"),
                    "market": p.get("market") or "EGX",
                    "currency": p.get("currency") or "ج.م",
                    "quantity": p.get("quantity"),
                    "market_value": p.get("market_value"),
                    "cost_basis": p.get("cost_basis"),
                    "profit_value": p.get("profit_value"),
                    "profit_pct": p.get("profit_pct"),
                }
                for p in result["positions"][:20]
                if isinstance(p, dict) and p.get("symbol")
            ],
        }

    # 2. Market Breadth Visual (All Exchanges: EGX, TASI, QSE, DFM, ADX, KSE, ...)
    breadth = result.get("breadth")
    if isinstance(breadth, dict) and breadth.get("total_stocks"):
        idx_close = next(
            (result.get(k) for k in ("index_close", "egx30_close", "tasi_close") if result.get(k) is not None),
            None,
        )
        idx_chg = next(
            (result.get(k) for k in ("index_change_pct", "egx30_change_pct", "tasi_change_pct") if result.get(k) is not None),
            None,
        )
        visuals_data["market_breadth"] = {
            "market": result.get("market"),
            "index_name": result.get("index_name"),
            "index_close": idx_close,
            "index_change_pct": idx_chg,
            "currency": result.get("currency") or "ج.م",
            "date": result.get("date"),
            "advancing": breadth.get("advancing") or 0,
            "declining": breadth.get("declining") or 0,
            "unchanged": breadth.get("unchanged") or 0,
            "total_stocks": breadth.get("total_stocks") or 0,
        }

    # 3. Accumulation Heatmap Visual
    acc_list = result.get("accumulation_stocks")
    if isinstance(acc_list, list) and len(acc_list) >= 2:
        visuals_data["accumulation"] = [
            {
                "symbol": item.get("symbol"),
                "name_ar": item.get("name_ar") or item.get("name") or item.get("symbol"),
                "accumulation_score": item.get("accumulation_score") or item.get("acc_score"),
                "r_vol": item.get("r_vol") or item.get("vol_ratio"),
                "consecutive_acc_days": item.get("consecutive_acc_days"),
                "close": item.get("close"),
                "change_pct": item.get("change_pct"),
                "currency": item.get("currency") or "ج.م",
            }
            for item in acc_list[:8]
            if isinstance(item, dict) and item.get("symbol")
        ]

    # 4. Fair Value Gauge Visual
    fv_list = result.get("fair_value_stocks")
    if isinstance(fv_list, list) and fv_list:
        fv_clean = [
            {
                "symbol": item.get("symbol"),
                "currency": item.get("currency") or "ج.م",
                "current_price": item.get("current_price"),
                "fair_value": item.get("fair_value"),
                "upside_pct": item.get("upside_pct"),
                "status": item.get("status"),
                "model": item.get("model"),
                "pe_ratio": item.get("pe_ratio"),
                "sector": item.get("sector"),
            }
            for item in fv_list[:6]
            if isinstance(item, dict) and item.get("symbol") and item.get("current_price") and item.get("fair_value")
        ]
        if fv_clean:
            visuals_data["fair_value"] = fv_clean

    # 5. Recommendations Progress Tracker Visual
    recs_list = result.get("recommendations")
    if isinstance(recs_list, list) and recs_list:
        recs_clean = [
            {
                "symbol": r.get("symbol"),
                "currency": r.get("currency") or "ج.م",
                "entry_price": r.get("entry_price"),
                "target_price": r.get("target_price"),
                "stop_loss": r.get("stop_loss"),
                "last_close": r.get("last_close"),
                "date": r.get("date"),
                "status": r.get("status"),
                "timeframe": r.get("timeframe"),
            }
            for r in recs_list[:8]
            if isinstance(r, dict) and r.get("symbol") and r.get("entry_price")
        ]
        if recs_clean:
            visuals_data["recommendations"] = recs_clean

    # 6. Sharia & Purification Visual
    if "purification_rate_pct" in result and result.get("symbol"):
        visuals_data["sharia"] = {
            "symbol": result.get("symbol"),
            "currency": result.get("currency") or "ج.م",
            "is_sharia_compliant": result.get("is_sharia_compliant"),
            "sharia_index": result.get("sharia_index"),
            "shares_count": result.get("shares_count"),
            "coupon_per_share": result.get("coupon_per_share"),
            "total_dividends": result.get("total_dividends"),
            "purification_rate_pct": result.get("purification_rate_pct"),
            "purification_amount": result.get("purification_amount"),
            "zakat_amount": result.get("zakat_amount"),
        }

    # 7. Price Traps Radar Visual
    if "bearTraps" in result or "bullTraps" in result:
        bears = [
            {
                "symbol": t.get("symbol"),
                "close": t.get("close"),
                "wickPct": t.get("wickPct"),
                "relativeVolume": t.get("relativeVolume"),
                "changePct": t.get("changePct"),
                "conviction": t.get("conviction"),
            }
            for t in (result.get("bearTraps") or [])[:5]
            if isinstance(t, dict) and t.get("symbol")
        ]
        bulls = [
            {
                "symbol": t.get("symbol"),
                "close": t.get("close"),
                "wickPct": t.get("wickPct"),
                "relativeVolume": t.get("relativeVolume"),
                "changePct": t.get("changePct"),
                "conviction": t.get("conviction"),
            }
            for t in (result.get("bullTraps") or [])[:5]
            if isinstance(t, dict) and t.get("symbol")
        ]
        if bears or bulls:
            visuals_data["price_traps"] = {
                "market": result.get("market"),
                "currency": result.get("currency") or "ج.م",
                "asOf": result.get("asOf"),
                "bearTraps": bears,
                "bullTraps": bulls,
            }

    # 8. Disclosures / News Sentiment Timeline Visual
    disc_list = result.get("disclosures")
    news_list = result.get("news")
    if isinstance(disc_list, list) and disc_list:
        visuals_data["disclosures"] = [
            {
                "symbol": d.get("symbol"),
                "company_name": d.get("company_name"),
                "disclosure_type": d.get("disclosure_type"),
                "disclosure_date": str(d.get("disclosure_date") or "")[:10],
                "title": d.get("title"),
                "sentiment": d.get("sentiment"),
                "source_url": d.get("source_url"),
            }
            for d in disc_list[:8]
            if isinstance(d, dict) and (d.get("title") or d.get("symbol"))
        ]
    elif isinstance(news_list, list) and news_list and "disclosures" not in visuals_data:
        visuals_data["disclosures"] = [
            {
                "symbol": n.get("symbol"),
                "company_name": n.get("company_name"),
                "disclosure_type": n.get("type") or "news",
                "disclosure_date": str(n.get("date") or "")[:10],
                "title": n.get("title"),
                "sentiment": n.get("sentiment") or n.get("sentiment_score"),
                "source_url": n.get("source_url"),
            }
            for n in news_list[:8]
            if isinstance(n, dict) and (n.get("title") or n.get("symbol"))
        ]


def _strip_ui_only_fields_for_llm(result: Any) -> Any:
    """Strip client-only chart payloads before serializing tool output to the LLM (saves tokens)."""
    if not isinstance(result, dict):
        return result
    stocks = result.get("stocks")
    if not isinstance(stocks, list):
        return result
    sanitized_stocks = []
    changed = False
    for item in stocks:
        if isinstance(item, dict) and "_ui_chart" in item:
            copy_item = {k: v for k, v in item.items() if k != "_ui_chart"}
            sanitized_stocks.append(copy_item)
            changed = True
        else:
            sanitized_stocks.append(item)
    if not changed:
        return result
    return {**result, "stocks": sanitized_stocks}


def _append_tool_results(
    tool_calls: List[Dict[str, Any]],
    tool_results: List[Any],
    formatted_messages: List[Dict[str, Any]],
    tables_data: List[Any],
    recommendations_data: List[Any],
    visuals_data: Optional[Dict[str, Any]] = None,
    *,
    acc_fallback_rows: Optional[List[Any]] = None,
) -> None:
    """Serialize tool outputs into DeepSeek tool messages and collect structured table rows."""
    for tc, result in zip(tool_calls, tool_results):
        tc_id = tc.get("id", f"call_{int(time.time() * 1000)}")
        if isinstance(result, Exception):
            content_str = json.dumps({"status": "error", "message": str(result)}, ensure_ascii=False)
        else:
            _collect_structured_outputs(
                result,
                tables_data,
                recommendations_data,
                visuals_data,
                acc_fallback_rows=acc_fallback_rows,
            )
            content_str = json.dumps(_strip_ui_only_fields_for_llm(result), ensure_ascii=False)

        formatted_messages.append({
            "role": "tool",
            "tool_call_id": tc_id,
            "content": content_str,
        })


def _get_deepseek_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_OFFICIAL_API_KEY") or ""
    return key.strip()


def _norm_ar_hint(text: str) -> str:
    t = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", text)
    t = re.sub(r"[أإآ]", "ا", t)
    t = re.sub(r"ة", "ه", t)
    t = re.sub(r"ى", "ي", t)
    return t.lower()


def known_symbol_hints(message: str) -> List[Dict[str, Any]]:
    """
    Extract EGX and Saudi (TASI) stock symbol hints from Arabic names, aliases, Latin tickers,
    and 4-digit Tadawul tickers.
    """
    if not message:
        return []
    try:
        from api.stock_aliases import ARABIC_STOCK_MAPPINGS, _KNOWN_SYMBOLS, resolve_stock_symbol
    except Exception:
        ARABIC_STOCK_MAPPINGS = {}
        _KNOWN_SYMBOLS = frozenset()
        resolve_stock_symbol = lambda x: None  # noqa: E731

    norm_msg = _norm_ar_hint(message)
    norm_msg = re.sub(r"(?:بورص[ةه]|سوق|مؤشر)\s+النيل", " ", norm_msg)

    hints: List[Dict[str, Any]] = []
    seen_symbols = set()

    # 1a. Match Egyptian Arabic full names and aliases, sorted longest first
    sorted_egx = sorted(ARABIC_STOCK_MAPPINGS.items(), key=lambda x: len(x[0]), reverse=True)
    for ar_name, sym in sorted_egx:
        norm_key = _norm_ar_hint(ar_name)
        if len(norm_key) < 2:
            continue

        escaped = re.escape(norm_key)
        if norm_key.startswith("ال"):
            without_al = re.escape(norm_key[2:])
            pattern = rf"(?:^|[^\w\u0621-\u064a])(?:(?:و|ف|ب|ل|ك|ال)?{escaped}|لل{without_al})(?:$|[^\w\u0621-\u064a])"
        else:
            pattern = rf"(?:^|[^\w\u0621-\u064a])(?:و|ف|ب|ل|ك|ال)?{escaped}(?:$|[^\w\u0621-\u064a])"

        if re.search(pattern, norm_msg, re.IGNORECASE):
            s_upper = sym.upper()
            if s_upper not in seen_symbols:
                seen_symbols.add(s_upper)
                hints.append({"name": ar_name, "symbols": [s_upper], "market": "EGX"})

    # 1b. Match Saudi Arabic & English company aliases, sorted longest first
    merged_saudi: Dict[str, str] = {}
    merged_saudi.update(_BUILTIN_SAUDI_ALIASES)
    merged_saudi.update(_EXT_SAUDI_MAPPINGS or {})
    sorted_saudi = sorted(merged_saudi.items(), key=lambda x: len(str(x[0])), reverse=True)
    for sa_name, sym in sorted_saudi:
        norm_key = _norm_ar_hint(str(sa_name))
        if len(norm_key) < 3:
            continue
        escaped = re.escape(norm_key)
        if norm_key.startswith("ال"):
            without_al = re.escape(norm_key[2:])
            pattern = rf"(?:^|[^\w\u0621-\u064a])(?:(?:و|ف|ب|ل|ك|ال)?{escaped}|لل{without_al})(?:$|[^\w\u0621-\u064a])"
        else:
            pattern = rf"(?:^|[^\w\u0621-\u064a])(?:و|ف|ب|ل|ك|ال)?{escaped}(?:$|[^\w\u0621-\u064a])"
        if re.search(pattern, norm_msg, re.IGNORECASE):
            s_upper = str(sym).upper().strip()
            if s_upper not in seen_symbols:
                seen_symbols.add(s_upper)
                hints.append({"name": sa_name, "symbols": [s_upper], "market": "TASI"})

    # 2. Match known EGX Latin tickers (ignore slash commands, suffixes like .AD/.QA/.DU, and suffixed tickers like ADIB.AD)
    latin_scan_msg = re.sub(r"\.(?:CA|EGX)\b", "", message, flags=re.IGNORECASE)
    latin_matches = re.findall(r"(?<![/.])\b([A-Za-z]{2,6})\b(?!\.[A-Za-z0-9])", latin_scan_msg)
    stopwords = {
        "EGX", "TASI", "KSA", "BUY", "SELL", "HOLD", "THE", "AND", "FOR",
        "RSI", "MACD", "EMA", "SMA", "VIP", "PRO", "API", "NOW", "TODAY",
        "NEWS", "USD", "EGP", "SAR", "VALUE", "FAIR", "SCAN", "HELP",
        "START", "PRICE", "LEVEL", "SWING", "OTC",
    }
    for tok in latin_matches:
        u = tok.upper()
        if u in stopwords:
            continue
        if u not in _KNOWN_SYMBOLS and u not in ARABIC_STOCK_MAPPINGS:
            continue
        res = resolve_stock_symbol(u)
        if res and res not in seen_symbols:
            seen_symbols.add(res)
            hints.append({"name": tok, "symbols": [res], "market": "EGX"})

    # 3. Match 4-digit Tadawul tickers while filtering dates, years, and round cash/share amounts
    scrubbed_msg = re.sub(r"\b\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?\b", " ", message)
    for m in re.finditer(r"(?<!\d)(\d{4})(\.(?:SR|SA|TADAWUL))?(?!\d)", scrubbed_msg, re.IGNORECASE):
        num = m.group(1)
        has_saudi_suffix = bool(m.group(2))
        if num in seen_symbols:
            continue
        if not has_saudi_suffix:
            val = int(num)
            # Tadawul stock codes are >= 1010 and never end in 000
            if val < 1010 or val % 500 == 0:
                continue
            # Filter obvious calendar years (keep 2010 SABIC & 2020 SABIC Nutri unless prefixed with year words)
            after_ctx = scrubbed_msg[m.end() : m.end() + 18].lower()
            before_ctx = scrubbed_msg[max(0, m.start() - 18) : m.start()].lower()
            if (1900 <= val <= 2009 or 2021 <= val <= 2035) or (
                val in (2010, 2020) and re.search(r"(?:عام|سنة|سنه|year|in)\s*$", before_ctx)
            ):
                continue
            # Filter amounts/quantities such as '1500 سهم' or '2200 جنيه' or '1200 ريال'
            if re.match(
                r"^\s*(?:%|جنيه|ج\.م|egp|ريال|ر\.س|sar|دولار|نقطة|مليون|الف|ألف|سهم|أسهم|اسهم)\b",
                after_ctx,
            ):
                continue
        seen_symbols.add(num)
        hints.append({"name": num, "symbols": [num], "market": "TASI"})

    return hints[:10]


def _resolve_query_market(
    message: str,
    active_market: Optional[str] = None,
    hints: Optional[List[Dict[str, Any]]] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, bool]:
    """
    Resolve `(canonical_exchange, is_cross_market)` for ANY exchange (EGX, TADAWUL, QSE, DFM, ADX, ...).
    Enables the exact same VIP cache, Fast-Track, and history-stripping path across all exchanges.
    """
    detected: List[str] = []

    base_active = normalize_exchange_code(active_market)
    tok_outer = set_active_market_context(base_active)
    try:
        for tc in (tool_calls or []):
            try:
                args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except Exception:
                args = {}
            arg_mkt = normalize_exchange_code(args.get("market")) if args.get("market") else None
            if arg_mkt and arg_mkt not in detected:
                detected.append(arg_mkt)
            syms = args.get("symbols") or ([args["symbol"]] if args.get("symbol") else [])
            tok_inner = set_active_market_context(arg_mkt) if arg_mkt else None
            try:
                for s in syms:
                    _, m = _resolve_symbol_and_market(s, explicit_market=args.get("market"))
                    if m and m not in detected:
                        detected.append(m)
            finally:
                if tok_inner is not None:
                    reset_active_market_context(tok_inner)
    finally:
        reset_active_market_context(tok_outer)

    if not detected:
        for h in (hints or []):
            if isinstance(h, dict) and h.get("market"):
                m = normalize_exchange_code(h.get("market"))
                if m not in detected:
                    detected.append(m)

    msg_str = str(message or "")
    if not tool_calls:
        text_mkt = detect_market_from_text(msg_str)
        if text_mkt and text_mkt not in detected:
            detected.append(text_mkt)
        # Detect 4-digit Tadawul stock codes with strict guards against years, cash amounts, and index points
        _NON_TICKER_NUM_NEIGHBOR_RE = re.compile(
            r"^\s*(?:جنيه|ج\.م|ريال|ر\.س|درهم|دينار|دولار|سهم|أسهم|اسهم|نقطة|نقطه|ألف|الف|مليون|مليار|EGP|SAR|USD|AED|QAR|KWD|%)",
            re.IGNORECASE,
        )
        _STOCK_PREFIX_RE = re.compile(r"(?:سهم|كود|رمز|شركة|تداول)\s*$", re.IGNORECASE)
        for m_num in re.finditer(r"(?<!\d)([1-9]\d{3})(?!\d)", msg_str):
            num_tok = m_num.group(1)
            num_val = int(num_tok)
            if 1990 <= num_val <= 2035:
                continue
            after_ctx = msg_str[m_num.end() : m_num.end() + 20]
            before_ctx = msg_str[max(0, m_num.start() - 16) : m_num.start()]
            if _NON_TICKER_NUM_NEIGHBOR_RE.match(after_ctx):
                continue
            if num_val % 500 == 0 and not _STOCK_PREFIX_RE.search(before_ctx):
                continue
            if "TADAWUL" not in detected:
                detected.append("TADAWUL")
                break
        # Detect cross-market queries combining a non-EGX exchange with an explicit EGX ticker/keyword
        if detected and "EGX" not in detected:
            msg_up = msg_str.upper()
            has_egx_kw = any(kw in msg_up for kw in ("EGX", ".CA", "البورصة المصرية", "السوق المصري", "مصر"))
            if not has_egx_kw:
                try:
                    from api.stock_aliases import _KNOWN_SYMBOLS as _EGX_KNOWN_SYMS
                    # Strip any non-EGX suffixed tickers (e.g. QNBK.QA, EMAAR.DU, ALDAR.AD, 2222.SR) first
                    stripped_up = re.sub(
                        r"\b[A-Z0-9]{2,12}\.(?:SR|SA|TADAWUL|QA|QE|QSE|DU|DFM|AE|AD|ADX|KW|KSE)\b",
                        " ",
                        msg_up,
                    )
                    for tok in re.findall(r"\b([A-Z]{3,6})\b", stripped_up):
                        if tok in _EGX_KNOWN_SYMS:
                            has_egx_kw = True
                            break
                except Exception:
                    pass
            if has_egx_kw:
                detected.append("EGX")

    if len(detected) > 1:
        return (detected[0], True)
    if len(detected) == 1:
        return (detected[0], False)
    return (normalize_exchange_code(active_market), False)


def _is_saudi_related_query(
    message: str,
    active_market: Optional[str] = None,
    hints: Optional[List[Dict[str, Any]]] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """Backward-compatible helper returning True when query targets TADAWUL/TASI."""
    exch, is_cross = _resolve_query_market(
        message, active_market=active_market, hints=hints, tool_calls=tool_calls
    )
    if exch == "TADAWUL":
        return True
    if is_cross:
        msg_up = (message or "").upper()
        if any(kw in msg_up for kw in ("TASI", "TADAWUL", ".SR", ".SA", "SAR", "تاسي", "تداول", "السعود")):
            return True
    return False


_CANONICAL_BUTTON_INPUTS = frozenset({
    "📈 أفضل أسهم السوق اليوم",
    "أفضل أسهم السوق اليوم",
    "أقوى أسهم التجميع والسيولة الذكية اليوم",
    "هات كل التوصيات المفتوحة حالياً",
    "ملخص السوق اليوم",
    "أهم أخبار وإفصاحات السوق اليوم",
    "أفضل الأسهم فنياً اليوم حسب المسح الفني والمؤشرات",
})


def _is_unambiguous_standalone_input(msg: Optional[str], market: str = "EGX") -> bool:
    """
    Return True ONLY when user input is unmistakably self-contained:
    - a bare 1-token stock symbol (e.g. 'TYCN', 'crst', '2222', 'QNBK.QA') resolving to `vip_stock_*`, OR
    - an exact canonical quick-action button string.
    Multi-word prompts like 'حلل سهم PHDC' return False to preserve explicit contextual-followup semantics.
    """
    clean = " ".join(str(msg or "").strip().split())
    if not clean:
        return False
    if clean in _CANONICAL_BUTTON_INPUTS:
        return True
    if re.fullmatch(r"[A-Za-z0-9]{2,12}(?:\.[A-Za-z]{2,8})?", clean):
        cand_key = build_analysis_cache_key(clean, market=market)
        if cand_key and cand_key.startswith("vip_stock_"):
            return True
    return False


def parse_dsml_tool_calls(text: str) -> List[Dict[str, Any]]:
    """
    Parse DeepSeek internal DSML tool invocations if emitted in message content:
    Handles all variants:
    - Standard: <｜DSML｜invoke name="..."> ... </｜DSML｜invoke>
    - Spaced & piped: <'DSML | | calls | | > ... <DSML | | invoke name="..." | | > ... </ | | DSML | | parameter | | >
    - Minimal / tagless close: <DSML | | invoke | | >
    """
    if not text or ("DSML" not in text and "dsml" not in text):
        return []
    tool_calls = []

    tag_prefix = r"<['\"]?\s*[|｜\s]*\s*(?:DSML)?\s*[|｜\s]*\s*"
    close_prefix = r"<\/?\s*[|｜\s]*\s*(?:DSML)?\s*[|｜\s]*\s*"

    invoke_pattern = re.compile(
        rf"{tag_prefix}invoke\s+name=[\"']?([a-zA-Z0-9_-]+)[\"']?[^>]*>(.*?){close_prefix}invoke[^>]*>",
        re.IGNORECASE | re.DOTALL,
    )
    param_pattern = re.compile(
        rf"{tag_prefix}parameter\s+name=[\"']?([a-zA-Z0-9_-]+)[\"']?(?:\s+string=[\"']?(true|false)[\"']?)?[^>]*>(.*?){close_prefix}parameter[^>]*>",
        re.IGNORECASE | re.DOTALL,
    )

    for i, match in enumerate(invoke_pattern.finditer(text)):
        fn_name = match.group(1).strip()
        body = match.group(2)
        args = {}
        for pmatch in param_pattern.finditer(body):
            pname = pmatch.group(1).strip()
            is_str = (pmatch.group(2) or "").lower()
            pval = pmatch.group(3).strip()
            if is_str == "false":
                if pval.lower() == "true":
                    args[pname] = True
                elif pval.lower() == "false":
                    args[pname] = False
                elif pval.isdigit():
                    args[pname] = int(pval)
                else:
                    try:
                        args[pname] = float(pval)
                    except ValueError:
                        args[pname] = pval
            else:
                args[pname] = pval
        tool_calls.append({
            "id": f"call_dsml_{int(time.time()*1000)}_{i}",
            "type": "function",
            "function": {
                "name": fn_name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        })
    return tool_calls


async def run_agentic_chat_stream(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    images: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    model: str = "deepseek-chat",
    autonomous_recommendations: bool = False,
    is_pro: bool = True,
    remaining_quota: int = 999,
    quota_limit: int = 999,
    market: Optional[str] = None,
    allow_recommendations: bool = True,
    is_b2b: bool = False,
    telegram_user_id: Optional[int] = None,
    block_group_portfolio: Optional[bool] = None,
):
    """
    Main agentic streaming generator (supports EGX & Saudi TASI simultaneously).
    Yields Server-Sent Events (SSE) formatted as: `data: <json_or_marker>\\n\\n`
    """
    ui_exch = _normalize_market_code(market)
    eff_block_group_pf = bool(is_b2b) if block_group_portfolio is None else bool(block_group_portfolio)
    mkt_token = set_active_market_context(ui_exch)
    tg_pf_token = set_telegram_portfolio_context(telegram_user_id)
    recs_token = set_allow_recommendations_context(allow_recommendations)
    group_pf_token = set_group_portfolio_blocked_context(eff_block_group_pf)
    try:
        async for ev in _run_agentic_chat_stream_impl(
            message=message,
            history=history,
            images=images,
            session_id=session_id,
            user_id=user_id,
            model=model,
            autonomous_recommendations=autonomous_recommendations,
            is_pro=is_pro,
            remaining_quota=remaining_quota,
            quota_limit=quota_limit,
            ui_exch=ui_exch,
            allow_recommendations=allow_recommendations,
            is_b2b=is_b2b,
            telegram_user_id=telegram_user_id,
        ):
            yield ev
    finally:
        reset_group_portfolio_blocked_context(group_pf_token)
        reset_allow_recommendations_context(recs_token)
        reset_telegram_portfolio_context(tg_pf_token)
        reset_active_market_context(mkt_token)


async def _run_agentic_chat_stream_impl(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    images: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    model: str = "deepseek-chat",
    autonomous_recommendations: bool = False,
    is_pro: bool = True,
    remaining_quota: int = 999,
    quota_limit: int = 999,
    ui_exch: str = "EGX",
    allow_recommendations: bool = True,
    is_b2b: bool = False,
    telegram_user_id: Optional[int] = None,
):
    start_time = time.time()
    usage_acc = _new_usage_accumulator()
    ui_label = _ui_market_label(ui_exch)
    api_key = _get_deepseek_key()
    if not api_key:
        err_event = {
            "type": "error",
            "detail": "مفتاح الذكاء الاصطناعي (DEEPSEEK_API_KEY) غير متاح في السيرفر."
        }
        yield f"data: {json.dumps(err_event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    # Yield initial thinking status (data-driven across all registered exchanges)
    active_cfg = get_market_config(ui_exch)
    thinking_msg = (
        f"جاري تحليل استفسارك في {active_cfg.name_ar} ({active_cfg.ui_code})..."
        if ui_exch != "EGX"
        else "جاري تحليل استفسارك عبر EGX BOTS..."
    )
    yield f"data: {json.dumps({'type': 'status', 'status': 'thinking', 'message': thinking_msg}, ensure_ascii=False)}\n\n"

    # Static system prompt first (enables DeepSeek prefix caching)
    formatted_messages = [{"role": "system", "content": AGENTIC_SYSTEM_PROMPT}]

    # Inject dynamic Cairo & Riyadh timestamps plus active UI market tie-breaker hint
    now_cairo = datetime.now(CAIRO_TZ)
    now_riyadh = datetime.now(RIYADH_TZ)
    active_mkt_desc = f"{active_cfg.name_ar} ({active_cfg.ui_code} — {active_cfg.currency_ar})"
    if is_b2b:
        telegram_channel_guidance = (
            "سياق مجموعة شريك (B2B): يُمنع منعاً باتاً الترويج أو ذكر روابط قنوات EGX BOTS (مثل t.me/egxbots أو /profile#telegram أو @egxbots_support أو /pricing) داخل رد المجموعة. "
            "إذا طلب العضو تسجيل أو تحليل محفظته الخاصة، وجّهه فقط لفتح الشات الخاص مع البوت (https://t.me/egxbots_bot?start=b2b_portfolio) حيث يمكنه حفظ وتحليل محفظته بسرية وبدون تسجيل دخول للموقع."
        )
        if not allow_recommendations:
            telegram_channel_guidance += (
                " تنبيه صارم: ميزة توصيات الشراء والبيع المفتوحة من EGX BOTS مقفولة نهائياً لهذه المجموعة بأمر الإدارة. "
                "يُمنع منعاً باتاً إعطاء توصيات شراء/بيع مفتوحة أو ترشيح أسهم للعضو، واقتصر على التحليل الفني، الدعوم والمقاومات، المؤشرات، القيمة العادلة، المقارنات، وكاشف المصائد فقط."
            )
    else:
        if ui_label == "TASI":
            telegram_channel_guidance = (
                "السوق النشط الآن هو السعودي TASI: عند الإشارة لقناة تليجرام اذكر قناة VIP السعودية فقط "
                "(https://web.telegram.org/a/#-1004397045436 ورابطها في /profile#telegram) ولا تذكر القناة المصرية المجانية (t.me/egxbots) لأن السوق السعودي لا يملك قناة مجانية."
            )
        elif ui_exch == "EGX":
            telegram_channel_guidance = (
                "السوق النشط الآن هو المصري EGX: عند الإشارة لقناة تليجرام تتوفر قناة VIP للمشتركين (/profile#telegram) والقناة العامة المجانية (https://t.me/egxbots)."
            )
        else:
            telegram_channel_guidance = (
                f"السوق النشط الآن هو {active_cfg.name_ar} ({active_cfg.ui_code} — {active_cfg.currency_ar}): التزم بعملة السوق ({active_cfg.currency_ar}) دون خلط العملات."
            )
    cairo_day_ar = _ARABIC_WEEKDAYS[now_cairo.weekday()]
    riyadh_day_ar = _ARABIC_WEEKDAYS[now_riyadh.weekday()]
    date_context = (
        f"📅 التوقيت الحالي: القاهرة {cairo_day_ar} {now_cairo.strftime('%Y-%m-%d %H:00')} | "
        f"الرياض {riyadh_day_ar} {now_riyadh.strftime('%Y-%m-%d %H:00')} (الجمعة والسبت عطلة البورصات العربية). "
        f"تبويب السوق النشط حالياً في الواجهة: {active_mkt_desc} "
        "(يُستخدم فقط كخيار افتراضي للأسئلة العامة غير المحددة، ويمكنك دائماً خدمة جميع الأسواق المتاحة في قاعدة البيانات معاً). "
        f"{telegram_channel_guidance} "
        "التزم دائماً بالعملة الراجعة في كل أداة (`currency`) دون خلط العملات بين الأسواق. "
        f"وضع التوصيات الحرة: {'مفعل' if (autonomous_recommendations and allow_recommendations) else 'غير مفعل'}."
    )
    formatted_messages.append({"role": "system", "content": date_context})

    # Load and inject standing per-user rules / preferences (profiles.custom_ai_rules)
    user_rules: Optional[str] = None
    if user_id and user_id != "00000000-0000-0000-0000-000000000000":
        try:
            _init_supabase()
            p_res = supabase.table("profiles").select("custom_ai_rules").eq("id", user_id).limit(1).execute()
            if p_res and p_res.data:
                user_rules = p_res.data[0].get("custom_ai_rules")
        except Exception as e:
            logger.warning(f"[agentic_chat] Could not load custom_ai_rules: {e}")

    has_user_rules = bool(user_rules and str(user_rules).strip())
    if has_user_rules:
        from api.agentic_chat.user_preferences import build_user_rules_prompt
        user_rules_prompt = build_user_rules_prompt(user_rules)
        if user_rules_prompt:
            formatted_messages.append({"role": "system", "content": user_rules_prompt})

    # Add bounded conversation history (last 8 turns: recent 2 preserve head+tail up to 2800 chars, older compact to 700 chars)
    has_conversation_history = False
    history_start_idx = len(formatted_messages)
    if history and isinstance(history, list):
        trimmed_history = history[-8:]
        n_hist = len(trimmed_history)
        for h_idx, msg in enumerate(trimmed_history):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            img_url = msg.get("image_url") or msg.get("imageUrl")
            is_recent_turn = h_idx >= n_hist - 2
            if role in ("user", "assistant") and (content or img_url):
                has_conversation_history = True
                compact_text = _compact_history_content(content, is_recent=is_recent_turn) if content else ""
                if role == "user" and img_url:
                    formatted_messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": compact_text if compact_text else "صورة مرفقة"},
                            {"type": "image_url", "image_url": {"url": img_url}}
                        ]
                    })
                else:
                    formatted_messages.append({"role": role, "content": compact_text})
    history_end_idx = len(formatted_messages)

    # 1. Vision Analysis Pipeline (Ported 1:1 from legacy Vercel system)
    valid_images = [img for img in (images or []) if img and isinstance(img, str) and img.strip()]
    vision_data = None
    if valid_images:
        yield f"data: {json.dumps({'type': 'status', 'status': 'vision', 'message': 'قراءة الصورة مع حفظ درجة الثقة وحدودها...'}, ensure_ascii=False)}\n\n"
        try:
            vision_data, vision_err = await analyze_image(
                image_url=valid_images,
                user_message=message,
                api_key=api_key,
                message_id=session_id or "",
            )
        except Exception as v_ex:
            logger.error(f"[agentic_chat] Vision exception: {v_ex}")
            vision_data, vision_err = None, str(v_ex)

        if vision_data:
            try:
                _init_supabase()
                vision_data = reconcile_vision_with_market(vision_data, supabase)
            except Exception as rec_ex:
                logger.warning(f"[agentic_chat] Reconcile error: {rec_ex}")

            # Send vision result events to client immediately
            yield f"data: {json.dumps({'type': 'vision_result', 'data': vision_data}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'vision', 'data': vision_data}, ensure_ascii=False)}\n\n"
        else:
            # Fallback when vision cannot extract anything from the image
            fallback_text = "وصلت الصورة إلى الشات، لكن تعذّر تحليلها بخدمة قراءة الصور حالياً. لذلك لم أستخرج منها رموزاً أو أرقاماً، ولم أعتمد على صورة أو بيانات سابقة. جرّب إعادة إرفاقها لاحقاً."
            words = fallback_text.split(" ")
            for i in range(0, len(words), 4):
                chunk = " ".join(words[i : i + 4]) + " "
                yield f"data: {json.dumps({'type': 'token', 'token': chunk}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.015)

            total_lat = int((time.time() - start_time) * 1000)
            done_ev = {
                "type": "done",
                "reply": fallback_text,
                "session_id": session_id,
                "suggested_buttons": ["تحليل سهم معين", "أقوى الأسهم اليوم"],
                "tables": [],
                "latency_ms": total_lat,
                "is_pro": is_pro,
                "remaining_quota": remaining_quota,
                "quota_limit": quota_limit,
                "vision": None,
                "vision_error": vision_err or "vision_analysis_failed",
                "usage": _finalize_usage_cost(usage_acc, cached=False),
            }
            yield f"data: {json.dumps(done_ev, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

    # Inject symbol hints if detected in user message, context, or vision
    hints = known_symbol_hints(message)
    if vision_data:
        vision_symbols = [
            s["symbol"].upper()
            for s in vision_data.get("symbols", [])
            if s.get("symbol")
        ]
        for vsym in vision_symbols:
            if not any(vsym in h.get("symbols", []) for h in hints):
                hints.insert(0, {"name": vsym, "symbols": [vsym]})

    if hints:
        hints_payload = {"symbol_hints": hints}
        hints_text = (
            "سياق رموز الأسهم المكتشفة في استفسار المستخدم والصور المرفقة (EGX / TASI symbol_hints):\n"
            f"{json.dumps(hints_payload, ensure_ascii=False)}\n"
            "التزم بدقة بهذه الرموز عند استدعاء الأدوات get_stock و get_stock_levels و get_comparison ولا تخترع رمزاً بديلاً."
        )
        formatted_messages.append({"role": "system", "content": hints_text})

    # Append vision context and user message
    if vision_data:
        vision_context_str = format_vision_context_for_prompt(vision_data)
        formatted_messages.append({"role": "system", "content": vision_context_str})

        if message and message.strip():
            clean_user_text = message.strip()
        elif vision_symbols or vision_data.get("image_type") in ("portfolio", "chart", "table", "market_depth"):
            clean_user_text = "تم إرفاق صورة مالية (محفظة / شارت / جدول أسعار). قم بقراءتها وتحليل البيانات الظاهرة فيها."
        else:
            clean_user_text = "تم إرفاق صورة."
        formatted_messages.append({"role": "user", "content": clean_user_text})

        if vision_symbols:
            prompt_instruction = (
                f"استدعِ فوراً الأدوات get_stock و get_stock_levels للرموز المستخرجة من الصورة: {', '.join(vision_symbols)} "
                f"لجلب أسعار الإغلاق اللحظية ومستويات الدعم والمقاومة، لمقارنتها بأسعار الشراء وكميات المراكز المستخرجة من الصورة وتقديم تحليل مالي وفني متكامل."
            )
            formatted_messages.append({"role": "system", "content": prompt_instruction})
    else:
        formatted_messages.append({"role": "user", "content": message})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    accumulated_reply = ""
    tables_data: List[Any] = []
    acc_fallback_rows: List[Any] = []
    recommendations_data: List[Any] = []
    visuals_data: Dict[str, Any] = {}
    tools_executed_count = 0
    candidate_cache_key: Optional[str] = None
    has_followup_flag = False
    model_confirmed_standalone = False
    effective_market, is_cross_market = _resolve_query_market(message, active_market=ui_exch, hints=hints)

    # 0. Check Two-Tier Analysis Cache for Direct Repeatable Canonical Queries (ALL Markets: EGX, TASI, QSE, DFM, ADX, ...)
    if (
        not is_cross_market
        and not has_conversation_history
        and not has_user_rules
        and not vision_data
        and (not images or len(images) == 0)
    ):
        early_key = build_analysis_cache_key(message, market=effective_market)
        if not allow_recommendations and is_recommendation_cache_key(early_key):
            early_key = None
        if early_key:
            candidate_cache_key = early_key
            cached_hit = get_vip_analysis_cache(
                early_key,
                user_id=user_id,
                telegram_user_id=telegram_user_id,
                is_b2b=is_b2b,
                allow_recommendations=allow_recommendations,
                market=effective_market,
            )
            if cached_hit:
                origin_label = "قاعدة البيانات السحابية" if cached_hit.get("origin") == "supabase_market_cache" else "الذاكرة اللحظية"
                logger.info(f"[agentic_chat] Serving from Early Two-Tier Cache: {early_key} ({cached_hit.get('origin')})")
                yield f"data: {json.dumps({'type': 'status', 'status': 'cached', 'message': f'تم استرجاع أحدث قراءة فنية موثقة من {origin_label}...'}, ensure_ascii=False)}\n\n"

                cached_reply = cached_hit["reply"]
                words = cached_reply.split(" ")
                chunk_size = 20
                for i in range(0, len(words), chunk_size):
                    chunk = " ".join(words[i : i + chunk_size]) + " "
                    yield f"data: {json.dumps({'type': 'token', 'token': chunk}, ensure_ascii=False)}\n\n"

                total_lat = int((time.time() - start_time) * 1000)
                suggested_buttons = ["📊 تحديث المستويات الفنية", "🎯 أهداف السهم القادمة", "📈 ترشيح فرص بديلة"]
                done_ev = {
                    "type": "done",
                    "reply": cached_reply,
                    "session_id": session_id,
                    "suggested_buttons": suggested_buttons,
                    "tables": cached_hit.get("tables") or [],
                    "recommendations": cached_hit.get("recommendations") or [],
                    "latency_ms": max(total_lat, 180),
                    "is_pro": is_pro,
                    "remaining_quota": remaining_quota,
                    "quota_limit": quota_limit,
                    "cached": True,
                    "cache_key": early_key,
                    "usage": _finalize_usage_cost(usage_acc, cached=True),
                }
                yield f"data: {json.dumps(done_ev, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

    max_rounds = 3
    round_count = 0

    # Single-Stock Fast-Track: works identically across ALL registered exchanges (EGX, TASI, QSE, DFM, ADX, ...).
    # Covers both general analysis (`vip_stock_SYM`) and dedicated financial/fundamental analysis (`vip_stock_SYM_financials`).
    fast_stock_match = (
        re.fullmatch(r"vip_stock_([A-Z0-9]{2,12})(_financials)?", candidate_cache_key)
        if (
            candidate_cache_key
            and not has_conversation_history
            and not has_user_rules
            and not is_cross_market
            and not vision_data
            and (not images or len(images) == 0)
        )
        else None
    )
    if fast_stock_match:
        fast_sym = fast_stock_match.group(1)
        is_financials_fast = bool(fast_stock_match.group(2))
        fast_mkt_ui = ui_market_label(effective_market)
        if is_financials_fast:
            fast_tool_specs = [
                ("get_stock", {"symbols": [fast_sym], "market": fast_mkt_ui}),
                ("get_fair_value", {"symbols": [fast_sym], "mode": "specific_stocks", "market": fast_mkt_ui}),
                ("get_news", {"symbols": [fast_sym], "market": fast_mkt_ui}),
                ("get_disclosures", {"symbol": fast_sym, "market": fast_mkt_ui}),
            ]
        else:
            fast_tool_specs = [
                ("get_stock", {"symbols": [fast_sym], "market": fast_mkt_ui}),
                ("get_fair_value", {"symbols": [fast_sym], "mode": "specific_stocks", "market": fast_mkt_ui}),
                ("get_news", {"symbols": [fast_sym], "market": fast_mkt_ui}),
                ("get_disclosures", {"symbol": fast_sym, "market": fast_mkt_ui}),
                ("get_price_traps", {"symbol": fast_sym, "market": fast_mkt_ui}),
            ]
        yield f"data: {json.dumps({'type': 'status', 'status': 'executing_tools', 'message': f'جاري جلب أحدث بيانات السوق ({len(fast_tool_specs)} مصادر)...'}, ensure_ascii=False)}\n\n"
        t_tools_start = time.time()
        fast_results = await asyncio.gather(
            *[
                dispatch_tool(t_name, t_args, user_id=user_id, user_prompt=message, default_market=effective_market)
                for t_name, t_args in fast_tool_specs
            ],
            return_exceptions=True,
        )
        t_tools = time.time() - t_tools_start
        logger.info(f"[agentic_chat] Single-Stock Fast-Track ({fast_sym}, fin={is_financials_fast}): Tools({len(fast_tool_specs)})={t_tools:.2f}s (skipped Round 1 LLM)")
        fast_ctx_payload: Dict[str, Any] = {}
        for (t_name, _), r in zip(fast_tool_specs, fast_results):
            if isinstance(r, Exception):
                fast_ctx_payload[t_name] = {"status": "error", "message": str(r)}
            else:
                _collect_structured_outputs(r, tables_data, recommendations_data, visuals_data)
                fast_ctx_payload[t_name] = _strip_ui_only_fields_for_llm(r)

        fast_mode_note = (
            "السؤال يطلب تحليلاً مالياً وأساسياً: طبّق قاعدة التحليل المالي والأساسي الاحترافي (ابدأ بـ «🎯 الخلاصة من الآخر»، اشرح الأرقام بمعناها العملي، اعتمد على `fundamental_diagnosis`، وإذا ورد في الأخبار نتائج مالية ربعية أحدث تتعارض مع آخر قوائم سنوية فنبّه المستخدم بوضوح لهذا الفرق الزمني، اعرض نقاط القوة مقابل المخاطر بوضوح، واختصر الفني في سطرين للتوقيت فقط)، وذلك بدون كتابة أي وسوم استدعاء أدوات أو DSML."
            if is_financials_fast
            else "اكتب الآن التقرير التحليلي الكامل مباشرة للمستخدم اعتماداً على هذه الأرقام الموثقة فقط، وبدون كتابة أي وسوم استدعاء أدوات أو DSML."
        )
        fast_ctx_msg = {
            "role": "system",
            "content": (
                f"بيانات السوق الموثقة المستخرجة فعلياً من قاعدة البيانات لسهم {fast_sym} "
                f"(نتائج {', '.join(t_name for t_name, _ in fast_tool_specs)}):\n"
                f"{json.dumps(fast_ctx_payload, ensure_ascii=False)}\n"
                f"تم تنفيذ جميع الأدوات المطلوبة بنجاح. {fast_mode_note}"
            ),
        }
        # Build clean grounded messages excluding any prior conversational turns
        fast_messages = [m for m in formatted_messages if m.get("role") == "system"]
        fast_messages.append(fast_ctx_msg)
        if formatted_messages and formatted_messages[-1].get("role") == "user":
            fast_messages.append(formatted_messages[-1])
        formatted_messages = fast_messages
        tools_executed_count += len(fast_tool_specs)
        usage_acc["tools_used"].extend([t_name for t_name, _ in fast_tool_specs])
        max_rounds = 0  # Proceed straight to DeepSeek single-call synthesis without tools schema

    active_tools_schema = (
        AGENTIC_TOOLS_SCHEMA
        if allow_recommendations
        else [t for t in AGENTIC_TOOLS_SCHEMA if (t.get("function") or {}).get("name") != "get_recommendations"]
    )

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            while round_count < max_rounds:
                round_count += 1

                req_payload = {
                    "model": "deepseek-chat",
                    "messages": formatted_messages,
                    "tools": active_tools_schema,
                    "tool_choice": "auto",
                    "temperature": 0.2,
                    "max_tokens": 3000,
                }

                t_turn1_start = time.time()
                resp = None
                for attempt in range(2):
                    try:
                        resp = await client.post(
                            "https://api.deepseek.com/chat/completions",
                            headers=headers,
                            json=req_payload,
                        )
                        if resp.status_code == 200:
                            break
                        if resp.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                            logger.warning(f"[agentic_chat] DeepSeek HTTP {resp.status_code}, retrying in 1.5s...")
                            await asyncio.sleep(1.5)
                            continue
                        break
                    except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                        if attempt == 0:
                            logger.warning(f"[agentic_chat] DeepSeek network glitch {net_err}, retrying in 1.5s...")
                            await asyncio.sleep(1.5)
                            continue
                        raise

                t_turn1 = time.time() - t_turn1_start

                if resp.status_code != 200:
                    logger.error(f"[agentic_chat] DeepSeek error: HTTP {resp.status_code} - {resp.text[:300]}")
                    yield f"data: {json.dumps({'type': 'error', 'detail': 'تعذر الاتصال بمحرك الذكاء الاصطناعي، يرجى المحاولة بعد قليل.'}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                res_json = resp.json()
                choice = res_json.get("choices", [{}])[0]
                assistant_msg = choice.get("message", {})
                tool_calls = assistant_msg.get("tool_calls")

                # Fallback: Intercept raw DSML markup in content if emitted instead of tool_calls
                content_raw = assistant_msg.get("content", "")
                if not tool_calls and content_raw and ("DSML" in content_raw or "dsml" in content_raw):
                    dsml_calls = parse_dsml_tool_calls(content_raw)
                    if dsml_calls:
                        logger.info(f"[agentic_chat] Intercepted {len(dsml_calls)} tool calls from raw DSML markup in content")
                        tool_calls = dsml_calls
                        assistant_msg["tool_calls"] = tool_calls
                        cleaned_content = strip_dsml(content_raw)
                        assistant_msg["content"] = cleaned_content if cleaned_content else None

                _accumulate_deepseek_usage(
                    usage_acc,
                    res_json.get("usage"),
                    [tc.get("function", {}).get("name", "") for tc in (tool_calls or []) if isinstance(tc, dict)],
                )

                # If DeepSeek has NO more tool calls to make:
                if not tool_calls:
                    content = assistant_msg.get("content", "")
                    if not content and vision_data:
                        content = safe_image_evidence_reply(vision_data, message)
                    if content:
                        accumulated_reply = filter_output(content)
                    
                    if not accumulated_reply and content_raw and ("DSML" in content_raw or "dsml" in content_raw):
                        accumulated_reply = "أهلاً بك! 👋 يرجى كتابة اسم أو كود السهم أو تحديد السؤال وسأقوم بجلبه وتحليله فوراً."

                    if accumulated_reply:
                        # Stream the reply smoothly in natural word chunks
                        words = accumulated_reply.split(" ")
                        chunk_size = 4
                        for i in range(0, len(words), chunk_size):
                            chunk = " ".join(words[i:i+chunk_size]) + " "
                            yield f"data: {json.dumps({'type': 'token', 'token': chunk}, ensure_ascii=False)}\n\n"
                            await asyncio.sleep(0.015)
                    break

                # -------------------------------------------------------------------
                # Dynamic Model-Driven Cache Check (Zero-Regex Intent Resolution, All Markets)
                # Works in both single-turn AND multi-turn conversations across EGX, TASI, QSE, DFM, ADX, ...
                # -------------------------------------------------------------------
                tc_market, tc_cross = _resolve_query_market(
                    message, active_market=effective_market, hints=hints, tool_calls=tool_calls
                )
                effective_market = tc_market
                if tc_cross:
                    is_cross_market = True

                batch_followup_true, batch_explicit_standalone = inspect_tool_calls_followup_flags(tool_calls)
                cache_tool_calls = tool_calls
                if batch_followup_true and _is_unambiguous_standalone_input(message, market=effective_market):
                    normalized_calls = []
                    for tc in tool_calls:
                        if isinstance(tc, dict) and isinstance(tc.get("function"), dict):
                            tc_copy = dict(tc)
                            fn_copy = dict(tc["function"])
                            try:
                                a = json.loads(fn_copy.get("arguments", "{}") or "{}")
                            except Exception:
                                a = {}
                            if isinstance(a, dict) and a.get("is_contextual_followup") is True:
                                a = {**a, "is_contextual_followup": False}
                                fn_copy["arguments"] = json.dumps(a, ensure_ascii=False)
                            tc_copy["function"] = fn_copy
                            normalized_calls.append(tc_copy)
                        else:
                            normalized_calls.append(tc)
                    if resolve_tool_calls_to_cache_key(normalized_calls) is not None:
                        batch_followup_true = False
                        batch_explicit_standalone = True
                        cache_tool_calls = normalized_calls

                if batch_followup_true:
                    has_followup_flag = True
                    candidate_cache_key = None
                    model_confirmed_standalone = False

                if round_count >= 2 and candidate_cache_key:
                    round2_key = resolve_tool_calls_to_cache_key(cache_tool_calls)
                    if not round2_key or round2_key != candidate_cache_key:
                        candidate_cache_key = None
                        model_confirmed_standalone = False

                cache_allowed_for_turn = (
                    (not has_followup_flag and not has_conversation_history)
                    or (has_conversation_history and not has_followup_flag and batch_explicit_standalone)
                )

                if (
                    not is_cross_market
                    and not has_user_rules
                    and cache_allowed_for_turn
                    and round_count == 1
                    and len(tool_calls) >= 1
                    and not vision_data
                    and (not images or len(images) == 0)
                ):
                    dynamic_key = resolve_tool_calls_to_cache_key(cache_tool_calls)
                    if not dynamic_key:
                        candidate_cache_key = None
                        model_confirmed_standalone = False
                    else:
                        preserved_special = False
                        if candidate_cache_key and candidate_cache_key.startswith("vip_stock_"):
                            cand_parts = candidate_cache_key.split("_")
                            if len(cand_parts) >= 4:
                                cand_sym = cand_parts[2]
                                if dynamic_key in (
                                    f"vip_stock_{cand_sym}",
                                    f"vip_news_{cand_sym}",
                                    f"vip_fair_value_{cand_sym}",
                                ):
                                    preserved_special = True
                        if not preserved_special:
                            candidate_cache_key = dynamic_key
                        lookup_key = candidate_cache_key
                        if not allow_recommendations and is_recommendation_cache_key(lookup_key):
                            lookup_key = None
                            candidate_cache_key = None
                        model_confirmed_standalone = bool(candidate_cache_key) and (
                            batch_explicit_standalone or not has_conversation_history
                        )
                        cached_hit = (
                            get_vip_analysis_cache(
                                lookup_key,
                                user_id=user_id,
                                telegram_user_id=telegram_user_id,
                                is_b2b=is_b2b,
                                allow_recommendations=allow_recommendations,
                                market=effective_market,
                            )
                            if lookup_key
                            else None
                        )
                        if cached_hit and cached_hit.get("reply"):
                            origin_label = "قاعدة البيانات السحابية" if cached_hit.get("origin") == "supabase_market_cache" else "الذاكرة اللحظية"
                            logger.info(f"[agentic_chat] Serving from Model-Driven Two-Tier Cache: {lookup_key} ({cached_hit.get('origin')})")
                            yield f"data: {json.dumps({'type': 'status', 'status': 'cached', 'message': f'تم استرجاع أحدث قراءة فنية موثقة من {origin_label}...'}, ensure_ascii=False)}\n\n"

                            cached_reply = cached_hit["reply"]
                            words = cached_reply.split(" ")
                            chunk_size = 20
                            for i in range(0, len(words), chunk_size):
                                chunk = " ".join(words[i : i + chunk_size]) + " "
                                yield f"data: {json.dumps({'type': 'token', 'token': chunk}, ensure_ascii=False)}\n\n"

                            total_lat = int((time.time() - start_time) * 1000)
                            suggested_buttons = ["📊 تحديث المستويات الفنية", "🎯 أهداف السهم القادمة", "📈 ترشيح فرص بديلة"]
                            done_ev = {
                                "type": "done",
                                "reply": cached_reply,
                                "session_id": session_id,
                                "suggested_buttons": suggested_buttons,
                                "tables": cached_hit.get("tables") or [],
                                "recommendations": cached_hit.get("recommendations") or [],
                                "latency_ms": max(total_lat, 180),
                                "is_pro": is_pro,
                                "remaining_quota": remaining_quota,
                                "quota_limit": quota_limit,
                                "cached": True,
                                "cache_key": lookup_key,
                                "usage": _finalize_usage_cost(usage_acc, cached=True),
                            }
                            yield f"data: {json.dumps(done_ev, ensure_ascii=False)}\n\n"
                            yield "data: [DONE]\n\n"
                            return
                elif round_count == 1:
                    candidate_cache_key = None
                    model_confirmed_standalone = False

                # Tool calls requested:
                tools_executed_count += len(tool_calls)
                yield f"data: {json.dumps({'type': 'status', 'status': 'executing_tools', 'message': f'جاري جلب أحدث بيانات السوق ({len(tool_calls)} مصادر)...'}, ensure_ascii=False)}\n\n"

                # Append assistant tool-call intent to message history
                formatted_messages.append(assistant_msg)

                # Execute tools: serialize mutating manage_portfolio calls before any portfolio view
                # to prevent read-after-write races (e.g., add_cash + view in the same round).
                t_tools_start = time.time()
                prepared_calls: List[Tuple[int, str, Dict[str, Any]]] = []
                for idx, tc in enumerate(tool_calls):
                    fn_name = tc.get("function", {}).get("name", "")
                    try:
                        fn_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                    except Exception:
                        fn_args = {}
                    if isinstance(fn_args, dict):
                        fn_args.pop("is_contextual_followup", None)
                    else:
                        fn_args = {}
                    if has_user_rules:
                        from api.agentic_chat.user_preferences import apply_user_rules_to_tool_args
                        fn_args = apply_user_rules_to_tool_args(fn_name, fn_args, user_rules)
                    prepared_calls.append((idx, fn_name, fn_args))

                pf_calls = [c for c in prepared_calls if c[1] == "manage_portfolio"]
                if len(pf_calls) > 1:
                    # Run mutating manage_portfolio ops sequentially first, then read-only/view ops
                    pf_writes = [c for c in pf_calls if str(c[2].get("operation") or "view").strip().lower() not in ("view", "get")]
                    tool_default_mkt = effective_market if not is_cross_market else ui_exch
                    pf_reads = [c for c in pf_calls if str(c[2].get("operation") or "view").strip().lower() in ("view", "get")]
                    other_calls = [c for c in prepared_calls if c[1] != "manage_portfolio"]
                    results_by_idx: Dict[int, Any] = {}
                    for idx, fn_name, fn_args in pf_writes:
                        try:
                            results_by_idx[idx] = await dispatch_tool(
                                fn_name, fn_args, user_id=user_id, user_prompt=message, default_market=tool_default_mkt
                            )
                        except Exception as exc:
                            results_by_idx[idx] = exc
                    parallel_calls = pf_reads + other_calls
                    if parallel_calls:
                        par_res = await asyncio.gather(
                            *[
                                dispatch_tool(fn_name, fn_args, user_id=user_id, user_prompt=message, default_market=tool_default_mkt)
                                for _, fn_name, fn_args in parallel_calls
                            ],
                            return_exceptions=True,
                        )
                        for (idx, _, _), res_item in zip(parallel_calls, par_res):
                            results_by_idx[idx] = res_item
                    tool_results = [results_by_idx[i] for i in range(len(prepared_calls))]
                else:
                    tool_default_mkt = effective_market if not is_cross_market else ui_exch
                    # Deduplicate identical read-only tool calls within the same round (e.g. duplicate get_accumulation_stocks)
                    sig_to_first_idx: Dict[str, int] = {}
                    unique_calls: List[Tuple[int, str, Dict[str, Any]]] = []
                    dup_map: Dict[int, int] = {}
                    for idx, fn_name, fn_args in prepared_calls:
                        is_mutating = fn_name in ("manage_portfolio", "manage_automations", "manage_user_preferences")
                        sig = None if is_mutating else f"{fn_name}:{json.dumps(fn_args, sort_keys=True, ensure_ascii=False)}"
                        if sig and sig in sig_to_first_idx:
                            dup_map[idx] = sig_to_first_idx[sig]
                        else:
                            if sig:
                                sig_to_first_idx[sig] = idx
                            unique_calls.append((idx, fn_name, fn_args))
                    unique_results = await asyncio.gather(
                        *[
                            dispatch_tool(
                                fn_name,
                                fn_args,
                                user_id=user_id,
                                user_prompt=message,
                                default_market=tool_default_mkt,
                            )
                            for _, fn_name, fn_args in unique_calls
                        ],
                        return_exceptions=True,
                    )
                    res_by_idx: Dict[int, Any] = {idx: r for (idx, _, _), r in zip(unique_calls, unique_results)}
                    tool_results = [
                        {"status": "duplicate_omitted", "note": "Identical call already returned in this round."}
                        if i in dup_map
                        else res_by_idx[i]
                        for i in range(len(prepared_calls))
                    ]
                t_tools = time.time() - t_tools_start
                logger.info(f"[agentic_chat] Phase timing: Turn{round_count}={t_turn1:.2f}s, Tools({len(tool_calls)})={t_tools:.2f}s")

                _append_tool_results(
                    tool_calls,
                    list(tool_results),
                    formatted_messages,
                    tables_data,
                    recommendations_data,
                    visuals_data,
                    acc_fallback_rows=acc_fallback_rows,
                )

                # For confirmed standalone requests inside a multi-turn session, strip prior turns
                # before Round 2 synthesis so saved shared cache contains zero cross-stock bleed and saves input tokens.
                if (
                    round_count == 1
                    and has_conversation_history
                    and model_confirmed_standalone
                    and candidate_cache_key
                    and not has_user_rules
                    and not is_cross_market
                    and history_end_idx > history_start_idx
                ):
                    formatted_messages = (
                        formatted_messages[:history_start_idx] + formatted_messages[history_end_idx:]
                    )
                    history_end_idx = history_start_idx

                # If Round 1 already fetched stock price/indicators/levels (via get_stock), go straight to synthesis
                called_names = {tc.get("function", {}).get("name", "") for tc in tool_calls}
                if (
                    round_count == 1
                    and candidate_cache_key
                    and re.fullmatch(r"vip_stock_[A-Z0-9]{2,12}", candidate_cache_key)
                    and "get_stock" in called_names
                ):
                    break

                # If reached max_rounds, break to final synthesis
                if round_count >= max_rounds:
                    break

            # If all rounds were consumed by tool calls and no text reply was generated yet:
            if tools_executed_count > 0 and not accumulated_reply:
                synthesis_payload: Dict[str, Any] = {
                    "model": "deepseek-chat",
                    "messages": formatted_messages,
                    "temperature": 0.3,
                    "max_tokens": 3000,
                }
                if not fast_stock_match:
                    synthesis_payload["tools"] = active_tools_schema
                    synthesis_payload["tool_choice"] = "none"  # Forbid tools so DeepSeek produces only synthesis text

                yield f"data: {json.dumps({'type': 'status', 'status': 'generating', 'message': 'جاري صياغة التقرير والتحليل الفني...'}, ensure_ascii=False)}\n\n"

                t_turn2_start = time.time()
                synth_resp = None
                last_synth_err: Optional[Exception] = None
                for synth_attempt in range(2):
                    try:
                        synth_resp = await client.post(
                            "https://api.deepseek.com/chat/completions",
                            headers=headers,
                            json=synthesis_payload,
                        )
                        if synth_resp.status_code == 200:
                            break
                        logger.warning(
                            f"[agentic_chat] Synthesis error HTTP {synth_resp.status_code} (attempt {synth_attempt + 1}/2)"
                        )
                        if synth_resp.status_code not in (429, 500, 502, 503, 504) or synth_attempt == 1:
                            break
                    except httpx.HTTPError as http_err:
                        last_synth_err = http_err
                        logger.warning(
                            f"[agentic_chat] Synthesis HTTP error (attempt {synth_attempt + 1}/2): {http_err}"
                        )
                        if synth_attempt == 1:
                            break
                    await asyncio.sleep(0.5)

                if synth_resp is not None and synth_resp.status_code == 200:
                    synth_json = synth_resp.json()
                    _accumulate_deepseek_usage(usage_acc, synth_json.get("usage"))
                    synth_content = synth_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if synth_content:
                        filtered_synth = filter_output(synth_content)
                        # DSML safety fallback: if synthesis emitted only DSML tool calls, execute them and synthesize once cleanly
                        if not filtered_synth and ("DSML" in synth_content or "dsml" in synth_content):
                            dsml_extra_calls = parse_dsml_tool_calls(synth_content)
                            if dsml_extra_calls:
                                logger.warning(f"[agentic_chat] Synthesis emitted DSML fallback ({len(dsml_extra_calls)} calls); executing cleanly")
                                extra_default_mkt = effective_market if not is_cross_market else ui_exch
                                extra_results = await asyncio.gather(
                                    *[
                                        dispatch_tool(
                                            tc.get("function", {}).get("name", ""),
                                            json.loads(tc.get("function", {}).get("arguments", "{}") or "{}"),
                                            user_id=user_id,
                                            user_prompt=message,
                                            default_market=extra_default_mkt,
                                        )
                                        for tc in dsml_extra_calls
                                    ],
                                    return_exceptions=True,
                                )
                                formatted_messages.append({"role": "assistant", "content": None, "tool_calls": dsml_extra_calls})
                                _append_tool_results(
                                    dsml_extra_calls,
                                    list(extra_results),
                                    formatted_messages,
                                    tables_data,
                                    recommendations_data,
                                    visuals_data,
                                    acc_fallback_rows=acc_fallback_rows,
                                )
                                retry_payload = {
                                    **synthesis_payload,
                                    "tools": active_tools_schema,
                                    "tool_choice": "none",
                                }
                                retry_resp = await client.post(
                                    "https://api.deepseek.com/chat/completions",
                                    headers=headers,
                                    json=retry_payload,
                                )
                                if retry_resp.status_code == 200:
                                    retry_json = retry_resp.json()
                                    _accumulate_deepseek_usage(
                                        usage_acc,
                                        retry_json.get("usage"),
                                        [tc.get("function", {}).get("name", "") for tc in dsml_extra_calls if isinstance(tc, dict)],
                                    )
                                    retry_content = retry_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                                    filtered_synth = filter_output(retry_content)
                        accumulated_reply = filtered_synth
                        if accumulated_reply:
                            words = accumulated_reply.split(" ")
                            chunk_size = 24 if len(words) > 300 else 12
                            sleep_sec = 0.004 if len(words) > 300 else 0.008
                            for i in range(0, len(words), chunk_size):
                                chunk = " ".join(words[i : i + chunk_size]) + " "
                                yield f"data: {json.dumps({'type': 'token', 'token': chunk}, ensure_ascii=False)}\n\n"
                                await asyncio.sleep(sleep_sec)
                else:
                    status_info = f"HTTP {synth_resp.status_code}" if synth_resp is not None else str(last_synth_err)
                    logger.error(f"[agentic_chat] Synthesis error: {status_info}")
                    yield f"data: {json.dumps({'type': 'error', 'detail': 'تعذر الاتصال بمحرك التحليل الذكي حالياً، يرجى المحاولة مرة أخرى.'}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                if not accumulated_reply:
                    logger.error("[agentic_chat] Synthesis produced empty filtered reply")
                    yield f"data: {json.dumps({'type': 'error', 'detail': 'لم يتمكن المساعد من صياغة الرد، يرجى إعادة المحاولة.'}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                t_turn2 = time.time() - t_turn2_start
                logger.info(f"[agentic_chat] Synthesis finished: Turn2={t_turn2:.2f}s, Total={time.time()-start_time:.2f}s")

    except Exception as e:
        logger.exception(f"[agentic_chat] Unexpected exception in chat stream: {e}")
        yield f"data: {json.dumps({'type': 'error', 'detail': 'حدث خطأ أثناء معالجة المحادثة، يرجى المحاولة مرة أخرى.'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    # Apply compliance filter on final reply
    accumulated_reply = filter_output(accumulated_reply)

    # Suggest dynamic follow-up buttons based on context
    if "تحليل سهم" in accumulated_reply or "الدعم" in accumulated_reply or "المقاومة" in accumulated_reply:
        suggested_buttons = ["📊 تحديث المستويات الفنية", "🎯 أهداف السهم القادمة", "📈 ترشيح فرص بديلة"]
    elif "توصيات" in accumulated_reply or "شراء" in accumulated_reply:
        suggested_buttons = ["⚡ إشارات المضاربة اللحظية", "🎯 صفقات السوينغ", "🛡️ كاشف المصائد"]
    else:
        suggested_buttons = ["📈 أفضل أسهم السوق اليوم", "🔍 تحليل سهم محدد", "💼 فحص محفظتي"]

    total_latency_ms = int((time.time() - start_time) * 1000)

    def _row_currency(item: Dict[str, Any]) -> str:
        c = item.get("currency")
        if c:
            return str(c)
        mkt = item.get("market") or item.get("exchange")
        if mkt:
            return currency_for_market(mkt)
        if re.fullmatch(r"\d{4}", str(item.get("symbol") or "").strip()):
            return "ر.س"
        return "ج.م"

    def _row_sharia_label(item: Dict[str, Any]) -> str:
        flag = item.get("is_sharia_compliant")
        if flag is True:
            idx = item.get("sharia_index") or "الشريعة"
            return f"متوافق ({idx})"
        if flag is False:
            return "غير متوافق"
        return "غير مصنف"

    # Format tables into standard ExcelTable schema expected by frontend
    excel_tables = []

    # 1. Recommendations Table
    if recommendations_data:
        rec_rows = []
        seen_rec = set()
        for r in recommendations_data:
            if isinstance(r, dict):
                sym = r.get("symbol") or ""
                if not sym or sym in seen_rec:
                    continue
                seen_rec.add(sym)
                curr = _row_currency(r)
                name = (r.get("name") or r.get("name_ar") or sym).split(",")[0].strip()
                sig = r.get("signal") or "BUY"
                ep = f"{r.get('entry_price', '—')} {curr}" if r.get('entry_price') is not None else "—"
                tp = f"{r.get('target_price', '—')} {curr}" if r.get('target_price') is not None else "—"
                sl = f"{r.get('stop_loss', '—')} {curr}" if r.get('stop_loss') is not None else "—"
                status_txt = r.get("status") or "نشطة (مفتوحة)"
                d_str = str(r.get("date") or "")
                sharia_txt = _row_sharia_label(r)
                rec_rows.append([sym, name, sig, ep, tp, sl, status_txt, d_str, sharia_txt])
        if rec_rows:
            excel_tables.append({
                "id": f"recs_{int(time.time())}",
                "title": "توصيات وإشارات التداول",
                "headers": ["الكود", "اسم الشركة", "الإشارة", "سعر الدخول", "المستهدف", "وقف الخسارة", "الحالة", "التاريخ", "التوافق الشرعي"],
                "rows": rec_rows,
                "source": "EGX BOTS",
                "data_time": time.strftime("%Y-%m-%d"),
            })

    # 2. Stocks Comparison Matrix or Stock Analysis Table
    # Use accumulation_stocks as table rows ONLY when no explicit get_stock/get_comparison rows exist
    # (prevents single-stock queries like FWRY from mixing with 10 unrelated market accumulation stocks).
    effective_table_rows = tables_data if tables_data else acc_fallback_rows
    if effective_table_rows:
        merged_stocks = {}
        for s in effective_table_rows:
            if not isinstance(s, dict) or not s.get("symbol"):
                continue
            sym = str(s["symbol"]).upper().strip()
            if sym not in merged_stocks:
                merged_stocks[sym] = dict(s)
            else:
                for k, v in s.items():
                    if v is not None and v != "" and v != "—":
                        if merged_stocks[sym].get(k) is None or merged_stocks[sym].get(k) == "" or merged_stocks[sym].get(k) == "—":
                            merged_stocks[sym][k] = v

        stocks_with_symbol = list(merged_stocks.values())[:10]  # Cap at 10 columns for clean UI display
        charts_map = {
            str(item.get("symbol")).upper().strip(): item["_ui_chart"]
            for item in stocks_with_symbol
            if item.get("symbol") and isinstance(item.get("_ui_chart"), dict)
        }
        if len(stocks_with_symbol) >= 2:
            visuals_data["comparison"] = [
                {
                    "symbol": s.get("symbol"),
                    "name_ar": (s.get("name_ar") or s.get("name") or s.get("symbol")).split(",")[0].strip(),
                    "close": s.get("close"),
                    "change_pct": s.get("change_pct"),
                    "rsi_14": s.get("rsi_14"),
                    "r_vol": s.get("r_vol"),
                    "king_ai_score": s.get("king_ai_score"),
                    "support_1": s.get("support_1"),
                    "resistance_1": s.get("resistance_1"),
                    "currency": _row_currency(s),
                    "is_sharia_compliant": s.get("is_sharia_compliant"),
                }
                for s in stocks_with_symbol[:4]
                if s.get("symbol")
            ]
            headers = ["المعيار"] + [f"{(s.get('name_ar') or s.get('symbol')).split(',')[0].strip()} ({s.get('symbol')})" for s in stocks_with_symbol]
            rows_list = [
                ["السعر الحالي"] + [f"{s.get('close', '—')} {_row_currency(s)}" if s.get('close') is not None else "—" for s in stocks_with_symbol],
                ["التغير اليومي"] + [f"{s.get('change_pct', '—')}%" if s.get('change_pct') is not None else "—" for s in stocks_with_symbol],
                ["مؤشر RSI"] + [str(s.get('rsi_14', '—')) for s in stocks_with_symbol],
                ["التقييم الفني"] + [str(s.get('verdict', '—')) for s in stocks_with_symbol],
                ["الدعم الأول"] + [f"{s.get('support_1', '—')} {_row_currency(s)}" if s.get('support_1') is not None else "—" for s in stocks_with_symbol],
                ["المقاومة الأولى"] + [f"{s.get('resistance_1', '—')} {_row_currency(s)}" if s.get('resistance_1') is not None else "—" for s in stocks_with_symbol],
                ["مؤشر King AI"] + [str(s.get('king_ai_score', '—')) for s in stocks_with_symbol],
                ["التوافق الشرعي"] + [_row_sharia_label(s) for s in stocks_with_symbol],
            ]
            comp_tbl: Dict[str, Any] = {
                "id": f"comparison_{int(time.time())}",
                "title": "مقارنة الأسهم الفنية والمالية",
                "headers": headers,
                "rows": rows_list,
                "source": "EGX BOTS",
                "data_time": time.strftime("%Y-%m-%d"),
            }
            if charts_map:
                comp_tbl["charts"] = charts_map
            excel_tables.append(comp_tbl)
        elif len(stocks_with_symbol) == 1:
            s = stocks_with_symbol[0]
            sym = s.get("symbol") or ""
            curr = _row_currency(s)
            name = (s.get("name_ar") or sym).split(",")[0].strip()
            close_str = f"{s.get('close', '—')} {curr}" if s.get('close') is not None else "—"
            chg_str = f"{s.get('change_pct', '—')}%" if s.get('change_pct') is not None else "—"
            rsi_str = str(s.get('rsi_14', '—'))
            verdict_str = s.get('verdict') or "—"
            s1_str = f"{s.get('support_1', '—')} {curr}" if s.get('support_1') is not None else "—"
            r1_str = f"{s.get('resistance_1', '—')} {curr}" if s.get('resistance_1') is not None else "—"
            king_str = str(s.get('king_ai_score', '—'))
            sharia_str = _row_sharia_label(s)
            single_tbl: Dict[str, Any] = {
                "id": f"table_{int(time.time())}",
                "title": f"التحليل الفني لسهم {name} ({sym})",
                "headers": ["الكود", "اسم الشركة", "السعر", "التغير %", "RSI", "الدعم الأول", "المقاومة الأولى", "مؤشر King AI", "التقييم الفني", "التوافق الشرعي"],
                "rows": [[sym, name, close_str, chg_str, rsi_str, s1_str, r1_str, king_str, verdict_str, sharia_str]],
                "source": "EGX BOTS",
                "data_time": time.strftime("%Y-%m-%d"),
            }
            if charts_map:
                single_tbl["charts"] = charts_map
            excel_tables.append(single_tbl)

    # Attach non-empty client-side SVG visual payloads onto excel_tables
    clean_visuals = {k: v for k, v in visuals_data.items() if v}
    if clean_visuals:
        if excel_tables:
            excel_tables[0]["visuals"] = clean_visuals
        else:
            excel_tables.append({
                "id": f"visuals_{int(time.time())}",
                "title": "",
                "headers": [],
                "rows": [],
                "source": "EGX BOTS",
                "data_time": time.strftime("%Y-%m-%d"),
                "visuals": clean_visuals,
            })

    # Cache repeatable public analyses in Two-Tier Cache (Tier 1 RAM + Tier 2 Supabase market_cache)
    # Placed after excel_tables formatting so cached hits return structured ExcelTable objects ready for Web & Telegram.
    saved_cache_key: Optional[str] = None
    can_save_for_history = (
        (not has_conversation_history and not has_followup_flag)
        or (has_conversation_history and model_confirmed_standalone and tools_executed_count > 0)
    )
    if (
        not is_cross_market
        and can_save_for_history
        and not has_user_rules
        and not visuals_data.get("portfolio")
        and accumulated_reply
        and not vision_data
        and (not images or len(images) == 0)
    ):
        effective_key = (
            candidate_cache_key
            if (tools_executed_count > 0 or has_conversation_history)
            else (candidate_cache_key or build_analysis_cache_key(message, market=effective_market))
        )
        if (
            effective_key
            and not is_uncacheable_error_reply(accumulated_reply)
            and not (not allow_recommendations and is_recommendation_cache_key(effective_key))
        ):
            saved_cache_key = effective_key
            try:
                set_vip_analysis_cache(
                    cache_key=effective_key,
                    reply=accumulated_reply,
                    tables=excel_tables if excel_tables else tables_data,
                    recommendations=recommendations_data,
                    is_b2b=is_b2b,
                    allow_recommendations=allow_recommendations,
                    market=effective_market,
                )
                logger.info(f"[agentic_chat] Saved to Two-Tier Cache ({effective_market}): {effective_key}")
            except Exception as cache_err:
                logger.warning(f"[agentic_chat] Cache set warning: {cache_err}")

    # Final done event with accurate quota and pro status
    done_event = {
        "type": "done",
        "reply": accumulated_reply,
        "session_id": session_id,
        "suggested_buttons": suggested_buttons,
        "tables": excel_tables,
        "latency_ms": total_latency_ms,
        "is_pro": is_pro,
        "remaining_quota": remaining_quota,
        "quota_limit": quota_limit,
        "vision": vision_data,
        "cached": False,
        "cache_key": saved_cache_key or candidate_cache_key,
        "usage": _finalize_usage_cost(usage_acc, cached=False),
    }

    yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
