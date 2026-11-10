"""
api/agentic_chat/tools_execution.py
Asynchronous, non-blocking execution of agentic financial tools against Supabase.
All I/O calls are offloaded via asyncio.to_thread to ensure the FastAPI event loop
never blocks.
"""

import asyncio
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
import pytz

from api.stock_ai import _init_supabase, supabase
from api.stock_aliases import resolve_stock_symbol
from api.sharia_stocks import is_sharia_compliant
from api.stock_aliases import ARABIC_STOCK_MAPPINGS

CAIRO_TZ = pytz.timezone("Africa/Cairo")


def _get_sb():
    """Ensure Supabase client is initialized and return it."""
    _init_supabase()
    return supabase


def _normalize_symbol(sym: Any) -> str:
    """Normalize stock symbol: strip .CA suffix, resolve Arabic names / aliases to official ticker."""
    if not sym:
        return ""
    raw = str(sym).strip()
    clean = raw.upper()
    if clean.endswith(".CA"):
        clean = clean[:-3]
    resolved = resolve_stock_symbol(clean)
    if resolved:
        return resolved
    resolved_ar = resolve_stock_symbol(raw)
    if resolved_ar:
        return resolved_ar
    return clean


def _safe_float(val: Any, decimals: int = 2) -> Optional[float]:
    """Safely cast value to float with bounded precision."""
    try:
        if val is None or val == "":
            return None
        f = float(val)
        if f != f:  # NaN check
            return None
        return round(f, decimals)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tool: get_stock
# ---------------------------------------------------------------------------
def _sync_get_stock(symbols: List[str]) -> Dict[str, Any]:
    sb = _get_sb()
    clean_symbols = [_normalize_symbol(s) for s in symbols if s][:10]
    if not clean_symbols:
        return {"status": "error", "message": "لم يتم تحديد رموز أسهم صالحة"}

    stocks_data = []
    for sym in clean_symbols:
        stock_name_ar = None
        stock_name_en = sym
        try:
            res_stock = sb.from_("stocks").select("symbol,name,name_ar").eq("symbol", sym).limit(1).execute()
            if res_stock.data:
                stock_name_ar = res_stock.data[0].get("name_ar")
                stock_name_en = res_stock.data[0].get("name") or sym
        except Exception:
            pass

        if not stock_name_ar:
            for ar_name, mapped_sym in ARABIC_STOCK_MAPPINGS.items():
                if mapped_sym == sym:
                    stock_name_ar = ar_name
                    break

        latest_tech = {}
        try:
            res_tech = (
                sb.from_("stock_technical_indicators")
                .select(
                    "date,close,change_pct,volume,r_vol,rsi_14,macd,macd_signal,macd_histogram,"
                    "bb_upper,bb_lower,ema_50,ema_200,vwap_20,king_ai_score,egx_ai_score"
                )
                .eq("exchange", "EGX")
                .eq("symbol", sym)
                .order("date", desc=True)
                .limit(1)
                .execute()
            )
            if res_tech.data:
                latest_tech = res_tech.data[0]
        except Exception:
            pass

        wyckoff_info = {}
        try:
            res_wyckoff = (
                sb.from_("stock_scans_summary")
                .select("scan_date,acc_score,dist_score,wyckoff_phase,vol_ratio,signal,consecutive_acc_days,consecutive_dist_days")
                .eq("symbol", sym)
                .order("scan_date", desc=True)
                .limit(1)
                .execute()
            )
            if res_wyckoff.data:
                wyckoff_info = res_wyckoff.data[0]
        except Exception:
            pass

        fundamentals = {}
        try:
            res_fund = (
                sb.from_("stock_fundamentals")
                .select("data")
                .eq("exchange", "EGX")
                .eq("symbol", sym)
                .limit(1)
                .execute()
            )
            if res_fund.data and isinstance(res_fund.data[0].get("data"), dict):
                fd = res_fund.data[0]["data"]
                fundamentals = {
                    "pe_ratio": _safe_float(fd.get("pe_ratio") or fd.get("trailing_pe")),
                    "eps": _safe_float(fd.get("eps") or fd.get("trailing_eps")),
                    "market_cap": fd.get("market_cap"),
                }
        except Exception:
            pass

        close_price = _safe_float(latest_tech.get("close"))
        change_pct = _safe_float(latest_tech.get("change_pct"))
        sharia = is_sharia_compliant(sym)

        king_score = _safe_float(latest_tech.get("king_ai_score"))
        acc_score = _safe_float(wyckoff_info.get("acc_score"))
        rsi = _safe_float(latest_tech.get("rsi_14"))

        if change_pct is not None and change_pct > 0 and rsi is not None and 45 <= rsi <= 68:
            verdict = "🟢 إيجابي / فرصة جيدة"
        elif change_pct is not None and change_pct < -2 or (rsi is not None and rsi > 75):
            verdict = "🔴 سلبي / مخاطرة مرتفعة"
        else:
            verdict = "🟡 حيادي للمراقبة"

        stocks_data.append({
            "symbol": sym,
            "name_ar": stock_name_ar or sym,
            "name": stock_name_en,
            "is_sharia_compliant": sharia,
            "sharia_index": "EGX33" if sharia else None,
            "date": latest_tech.get("date"),
            "close": close_price,
            "change_pct": change_pct,
            "rsi_14": rsi,
            "macd": _safe_float(latest_tech.get("macd"), 3),
            "macd_signal": _safe_float(latest_tech.get("macd_signal"), 3),
            "macd_histogram": _safe_float(latest_tech.get("macd_histogram"), 3),
            "ema_50": _safe_float(latest_tech.get("ema_50")),
            "ema_200": _safe_float(latest_tech.get("ema_200")),
            "r_vol": _safe_float(latest_tech.get("r_vol")),
            "volume": latest_tech.get("volume"),
            "king_ai_score": king_score,
            "egx_ai_score": _safe_float(latest_tech.get("egx_ai_score")),
            "wyckoff_phase": wyckoff_info.get("wyckoff_phase"),
            "accumulation_score": acc_score,
            "distribution_score": _safe_float(wyckoff_info.get("dist_score")),
            "consecutive_acc_days": wyckoff_info.get("consecutive_acc_days"),
            "verdict": verdict,
            **fundamentals,
        })

    return {"status": "success", "stocks": stocks_data}


async def execute_get_stock(symbols: List[str]) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_stock, symbols)


# ---------------------------------------------------------------------------
# Tool: get_stock_levels
# ---------------------------------------------------------------------------
def _sync_get_stock_levels(symbols: List[str]) -> Dict[str, Any]:
    sb = _get_sb()
    clean_symbols = [_normalize_symbol(s) for s in symbols if s][:10]
    levels = []

    for sym in clean_symbols:
        try:
            res_p = (
                sb.from_("stock_prices")
                .select("high,low,close,date")
                .eq("exchange", "EGX")
                .eq("symbol", sym)
                .order("date", desc=True)
                .limit(60)
                .execute()
            )
            rows = res_p.data or []
        except Exception:
            rows = []

        if not rows:
            levels.append({
                "symbol": sym,
                "status": "missing",
                "message": f"لا توجد بيانات أسعار تاريخية كافية لسهم {sym}"
            })
            continue

        close = _safe_float(rows[0].get("close"))
        date = rows[0].get("date")

        recent_20 = rows[:20]
        recent_lows = [float(r["low"]) for r in recent_20 if r.get("low")]
        recent_highs = [float(r["high"]) for r in recent_20 if r.get("high")]
        all_lows = [float(r["low"]) for r in rows if r.get("low")]
        all_highs = [float(r["high"]) for r in rows if r.get("high")]

        support_1 = _safe_float(min(recent_lows)) if recent_lows else None
        resistance_1 = _safe_float(max(recent_highs)) if recent_highs else None
        support_2 = _safe_float(min(all_lows)) if all_lows else (round(support_1 * 0.96, 2) if support_1 else None)
        resistance_2 = _safe_float(max(all_highs)) if all_highs else (round(resistance_1 * 1.05, 2) if resistance_1 else None)

        stop_loss = round(support_1 * 0.98, 2) if support_1 else None
        entry_zone = f"{support_1} – {round(support_1 * 1.02, 2)}" if support_1 else "غير محدد"

        has_rec = False
        rec_data = None
        try:
            res_rec = (
                sb.from_("scan_results")
                .select("signal,entry_price,target_price,stop_loss,status,created_at")
                .eq("exchange", "EGX")
                .eq("symbol", sym)
                .in_("status", ["open", "active"])
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if res_rec.data:
                has_rec = True
                r = res_rec.data[0]
                rec_data = {
                    "signal": r.get("signal"),
                    "entry_price": _safe_float(r.get("entry_price")),
                    "target_price": _safe_float(r.get("target_price")),
                    "stop_loss": _safe_float(r.get("stop_loss")),
                    "status": r.get("status"),
                    "signal_date": str(r.get("created_at") or "")[:10]
                }
        except Exception:
            pass

        levels.append({
            "symbol": sym,
            "close": close,
            "date": date,
            "support_1": support_1,
            "support_2": support_2,
            "resistance_1": resistance_1,
            "resistance_2": resistance_2,
            "stop_loss": stop_loss,
            "target_1": resistance_1,
            "target_2": resistance_2,
            "entry_zone": entry_zone,
            "has_active_recommendation": has_rec,
            "active_recommendation": rec_data,
        })

    return {"status": "success", "levels": levels}


async def execute_get_stock_levels(symbols: List[str]) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_stock_levels, symbols)


# ---------------------------------------------------------------------------
# Tool: get_market
# ---------------------------------------------------------------------------
def _sync_get_market() -> Dict[str, Any]:
    sb = _get_sb()
    payload = {}
    try:
        res = sb.from_("market_cache").select("payload").eq("cache_key", "market_status_Egypt").limit(1).execute()
        if res.data and isinstance(res.data[0].get("payload"), dict):
            payload = res.data[0]["payload"]
    except Exception:
        pass

    egx30_info = {}
    try:
        res_egx30 = (
            sb.from_("stock_technical_indicators")
            .select("date,close,change_pct,volume")
            .eq("symbol", "EGX30")
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        if res_egx30.data:
            egx30_info = res_egx30.data[0]
    except Exception:
        pass

    return {
        "status": "success",
        "market": "EGX (البورصة المصرية)",
        "egx30_close": _safe_float(egx30_info.get("close")) or payload.get("egx30_close"),
        "egx30_change_pct": _safe_float(egx30_info.get("change_pct")) or payload.get("egx30_change_pct"),
        "date": egx30_info.get("date") or payload.get("date"),
        "top_gainers": payload.get("top_gainers", []),
        "top_losers": payload.get("top_losers", []),
        "liquidity_summary": payload.get("liquidity", "سيولة متوازنة في جلسة اليوم"),
    }


async def execute_get_market() -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_market)


# ---------------------------------------------------------------------------
# Tool: get_recommendations
# ---------------------------------------------------------------------------
def _sync_get_recommendations(
    status: str = "open",
    timeframe: str = "all",
    symbols: Optional[List[str]] = None,
    sharia_only: bool = False,
    limit: int = 20,
) -> Dict[str, Any]:
    sb = _get_sb()
    try:
        query = sb.from_("scan_results").select(
            "symbol,signal,entry_price,target_price,stop_loss,status,created_at,strategy,timeframe"
        )
        if status == "open":
            query = query.in_("status", ["open", "active"])
        elif status == "closed":
            query = query.eq("status", "closed")

        if symbols:
            clean_syms = [_normalize_symbol(s) for s in symbols if s]
            query = query.in_("symbol", clean_syms)

        query = query.order("created_at", desc=True).limit(min(limit or 20, 30))
        res = query.execute()
        rows = res.data or []
    except Exception as e:
        return {"status": "error", "message": f"تعذر استرجاع التوصيات: {str(e)}"}

    recs = []
    for r in rows:
        sym = r.get("symbol")
        if sharia_only and not is_sharia_compliant(sym):
            continue

        recs.append({
            "symbol": sym,
            "signal": r.get("signal", "BUY"),
            "entry_price": _safe_float(r.get("entry_price")),
            "target_price": _safe_float(r.get("target_price")),
            "stop_loss": _safe_float(r.get("stop_loss")),
            "status": r.get("status"),
            "timeframe": r.get("timeframe") or "سوينغ قصير 🎯",
            "strategy": r.get("strategy") or "خوارزمية الذكاء الاصطناعي",
            "date": str(r.get("created_at") or "")[:10],
            "is_sharia_compliant": is_sharia_compliant(sym),
        })

    return {
        "status": "success",
        "count": len(recs),
        "filter_status": status,
        "sharia_only": sharia_only,
        "recommendations": recs,
    }


async def execute_get_recommendations(
    status: str = "open",
    timeframe: str = "all",
    symbols: Optional[List[str]] = None,
    sharia_only: bool = False,
    limit: int = 20,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_recommendations, status, timeframe, symbols, sharia_only, limit)


# ---------------------------------------------------------------------------
# Tool: get_technical_scan
# ---------------------------------------------------------------------------
def _sync_get_technical_scan(preset: str, sharia_only: bool = False) -> Dict[str, Any]:
    sb = _get_sb()
    try:
        query = sb.from_("stock_technical_indicators").select(
            "symbol,date,close,change_pct,volume,r_vol,rsi_14,macd,macd_signal,macd_histogram"
        ).eq("exchange", "EGX")

        if preset == "rsi_oversold":
            query = query.lte("rsi_14", 35).order("rsi_14", desc=False).limit(30)
        elif preset == "top_gainers":
            query = query.order("change_pct", desc=True).limit(30)
        elif preset == "top_losers":
            query = query.order("change_pct", desc=False).limit(30)
        elif preset == "momentum_and_volume":
            query = query.gte("r_vol", 1.2).gte("change_pct", 0).order("r_vol", desc=True).limit(30)
        elif preset == "macd_cross":
            query = query.gte("macd_histogram", 0).order("macd_histogram", desc=True).limit(30)
        else:
            query = query.order("volume", desc=True).limit(30)

        res = query.execute()
        rows = res.data or []
    except Exception as e:
        return {"status": "error", "message": f"تعذر تنفيذ المسح الفني: {str(e)}"}

    results = []
    seen = set()
    for r in rows:
        sym = r.get("symbol")
        if not sym or sym in seen:
            continue
        seen.add(sym)

        if sharia_only and not is_sharia_compliant(sym):
            continue

        results.append({
            "symbol": sym,
            "close": _safe_float(r.get("close")),
            "change_pct": _safe_float(r.get("change_pct")),
            "rsi_14": _safe_float(r.get("rsi_14")),
            "r_vol": _safe_float(r.get("r_vol")),
            "macd": _safe_float(r.get("macd"), 3),
            "date": r.get("date"),
            "is_sharia_compliant": is_sharia_compliant(sym),
        })
        if len(results) >= 10:
            break

    return {"status": "success", "preset": preset, "stocks": results}


async def execute_get_technical_scan(preset: str, sharia_only: bool = False) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_technical_scan, preset, sharia_only)


# ---------------------------------------------------------------------------
# Tool: get_accumulation_stocks
# ---------------------------------------------------------------------------
def _sync_get_accumulation_stocks(sharia_only: bool = False) -> Dict[str, Any]:
    sb = _get_sb()
    try:
        res = (
            sb.from_("stock_scans_summary")
            .select("symbol,scan_date,acc_score,dist_score,wyckoff_phase,vol_ratio,signal,consecutive_acc_days")
            .gte("acc_score", 50)
            .order("acc_score", desc=True)
            .limit(30)
            .execute()
        )
        rows = res.data or []
    except Exception as e:
        return {"status": "error", "message": f"تعذر جلب أسهم التجميع: {str(e)}"}

    stocks = []
    seen = set()
    for r in rows:
        sym = r.get("symbol")
        if not sym or sym in seen:
            continue
        seen.add(sym)

        if sharia_only and not is_sharia_compliant(sym):
            continue

        stocks.append({
            "symbol": sym,
            "accumulation_score": _safe_float(r.get("acc_score")),
            "distribution_score": _safe_float(r.get("dist_score")),
            "wyckoff_phase": r.get("wyckoff_phase") or "تجميع مؤسسي (Accumulation)",
            "consecutive_acc_days": r.get("consecutive_acc_days") or 1,
            "date": r.get("scan_date"),
            "is_sharia_compliant": is_sharia_compliant(sym),
        })
        if len(stocks) >= 10:
            break

    return {"status": "success", "accumulation_stocks": stocks}


async def execute_get_accumulation_stocks(sharia_only: bool = False) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_accumulation_stocks, sharia_only)


# ---------------------------------------------------------------------------
# Tool: get_news
# ---------------------------------------------------------------------------
def _sync_get_news(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    sb = _get_sb()
    try:
        query = sb.from_("disclosures").select("symbol,title,date,source_url,pdf_url").order("date", desc=True).limit(10)
        if symbols:
            clean_syms = [_normalize_symbol(s) for s in symbols if s][:10]
            query = query.in_("symbol", clean_syms)

        res = query.execute()
        rows = res.data or []
    except Exception:
        rows = []

    news_items = []
    for r in rows:
        news_items.append({
            "symbol": r.get("symbol"),
            "title": r.get("title"),
            "date": r.get("date"),
            "pdf_url": r.get("pdf_url"),
            "source_url": r.get("source_url"),
        })

    return {"status": "success", "count": len(news_items), "news": news_items}


async def execute_get_news(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_news, symbols)


# ---------------------------------------------------------------------------
# Tool: get_comparison
# ---------------------------------------------------------------------------
def _sync_get_comparison(symbols: List[str]) -> Dict[str, Any]:
    clean_syms = [_normalize_symbol(s) for s in symbols if s][:10]
    stock_res = _sync_get_stock(clean_syms)
    levels_res = _sync_get_stock_levels(clean_syms)
    levels_map = {}
    for item in levels_res.get("levels", []):
        if isinstance(item, dict) and item.get("symbol"):
            levels_map[item["symbol"]] = item

    stocks = stock_res.get("stocks", [])
    for s in stocks:
        sym = s.get("symbol")
        lvl = levels_map.get(sym, {})
        s["support_1"] = lvl.get("support_1")
        s["resistance_1"] = lvl.get("resistance_1")
        s["support_2"] = lvl.get("support_2")
        s["resistance_2"] = lvl.get("resistance_2")

    return {"status": "success", "stocks": stocks}


async def execute_get_comparison(symbols: List[str]) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_comparison, symbols)


# ---------------------------------------------------------------------------
# Tool: get_fair_value
# ---------------------------------------------------------------------------
def _sync_get_fair_value(
    symbols: Optional[List[str]] = None,
    mode: str = "screen_undervalued",
    sharia_only: bool = False,
    limit: int = 10,
) -> Dict[str, Any]:
    sb = _get_sb()
    try:
        query = (
            sb.from_("stock_technical_indicators")
            .select("symbol,close,change_pct,vwap_20,ema_50,ema_200")
            .eq("exchange", "EGX")
            .order("date", desc=True)
            .limit(50)
        )
        if symbols:
            clean_syms = [_normalize_symbol(s) for s in symbols if s][:10]
            query = query.in_("symbol", clean_syms)
        res = query.execute()
        rows = res.data or []
    except Exception as e:
        return {"status": "error", "message": f"تعذر حساب السعر العادل: {str(e)}"}

    items = []
    seen = set()
    for r in rows:
        sym = r.get("symbol")
        if not sym or sym in seen:
            continue
        seen.add(sym)

        if sharia_only and not is_sharia_compliant(sym):
            continue

        close = _safe_float(r.get("close"))
        if not close or close <= 0:
            continue

        vwap = _safe_float(r.get("vwap_20")) or close
        ema = _safe_float(r.get("ema_50")) or close
        fair_value = round((vwap * 0.6) + (ema * 0.4), 2)
        upside = round(((fair_value - close) / close) * 100, 2)

        items.append({
            "symbol": sym,
            "current_price": close,
            "fair_value": fair_value,
            "upside_pct": upside,
            "status": "undervalued" if upside > 5 else ("overvalued" if upside < -5 else "fair"),
            "status_ar": "أقل من السعر العادل (رخيص) 🟢" if upside > 5 else ("أعلى من السعر العادل (متضخم) 🔴" if upside < -5 else "في النطاق العادل ⚖️"),
            "model": "التوازن الكمي (VWAP & EMA)",
            "is_sharia_compliant": is_sharia_compliant(sym),
        })

    if mode == "screen_undervalued":
        items.sort(key=lambda x: x["upside_pct"], reverse=True)
    elif mode == "screen_overvalued":
        items.sort(key=lambda x: x["upside_pct"], reverse=False)

    return {"status": "success", "fair_value_stocks": items[:limit]}


async def execute_get_fair_value(
    symbols: Optional[List[str]] = None,
    mode: str = "screen_undervalued",
    sharia_only: bool = False,
    limit: int = 10,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_fair_value, symbols, mode, sharia_only, limit)


# ---------------------------------------------------------------------------
# Tool: get_sharia_cleanser
# ---------------------------------------------------------------------------
def _sync_get_sharia_cleanser(
    symbol: str,
    shares_count: float = 1000.0,
    coupon_per_share: Optional[float] = None,
    purification_rate_pct: Optional[float] = None,
) -> Dict[str, Any]:
    clean_sym = _normalize_symbol(symbol)
    sharia = is_sharia_compliant(clean_sym)
    rate = purification_rate_pct or 1.5
    coupon = coupon_per_share or 1.0
    total_coupon = shares_count * coupon
    purification_amount = round(total_coupon * (rate / 100.0), 2)
    zakat_amount = round(total_coupon * 0.025, 2)

    return {
        "status": "success",
        "symbol": clean_sym,
        "is_sharia_compliant": sharia,
        "sharia_index": "EGX33 Shariah" if sharia else "غير مدرج بمؤشر الشريعة",
        "shares_count": shares_count,
        "coupon_per_share": coupon,
        "total_dividends": total_coupon,
        "purification_rate_pct": rate,
        "purification_amount_egp": purification_amount,
        "zakat_amount_egp": zakat_amount,
        "verdict_ar": "السهم متوافق مع معايير الشريعة الإسلامية ومؤشر EGX33" if sharia else "السهم غير مصنف ضمن أسهم الشريعة المعتمدة EGX33",
    }


async def execute_get_sharia_cleanser(
    symbol: str,
    shares_count: float = 1000.0,
    coupon_per_share: Optional[float] = None,
    purification_rate_pct: Optional[float] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_get_sharia_cleanser, symbol, shares_count, coupon_per_share, purification_rate_pct)


# ---------------------------------------------------------------------------
# Tool: calculate_position
# ---------------------------------------------------------------------------
def _sync_calculate_position(
    symbol: str,
    quantity: Optional[float] = None,
    entry_price: Optional[float] = None,
    total_cost: Optional[float] = None,
) -> Dict[str, Any]:
    clean_sym = _normalize_symbol(symbol)
    sb = _get_sb()

    close = 1.0
    try:
        res = (
            sb.from_("stock_technical_indicators")
            .select("close,date")
            .eq("exchange", "EGX")
            .eq("symbol", clean_sym)
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            close = _safe_float(res.data[0].get("close")) or 1.0
    except Exception:
        pass

    cost = total_cost or ((quantity or 0) * (entry_price or 0))
    qty = quantity or (cost / entry_price if entry_price else 0)
    current_val = qty * close
    profit_loss = round(current_val - cost, 2)
    profit_pct = round((profit_loss / cost * 100), 2) if cost > 0 else 0.0

    return {
        "status": "success",
        "symbol": clean_sym,
        "quantity": qty,
        "entry_price": entry_price,
        "close_price": close,
        "total_cost": round(cost, 2),
        "current_market_value": round(current_val, 2),
        "profit_loss_egp": profit_loss,
        "profit_loss_pct": profit_pct,
    }


async def execute_calculate_position(
    symbol: str,
    quantity: Optional[float] = None,
    entry_price: Optional[float] = None,
    total_cost: Optional[float] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_calculate_position, symbol, quantity, entry_price, total_cost)


# ---------------------------------------------------------------------------
# Tool: manage_portfolio (with prompt-injection safeguard)
# ---------------------------------------------------------------------------
def _sync_manage_portfolio(
    user_id: Optional[str],
    operation: str,
    symbol: Optional[str] = None,
    quantity: Optional[float] = None,
    price: Optional[float] = None,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """
    Secure portfolio management backed by Supabase `positions` table and `profiles.cash_balance`.
    Requires verified user_id.
    Enforces anti-injection: write operations (add/update/remove/sell) require explicit
    confirmation words in user_prompt to prevent autonomous hallucinated mutations.
    """
    if not user_id:
        return {
            "status": "error",
            "message": "يلزم تسجيل الدخول لعرض أو تعديل المحفظة الاستثمارية.",
            "requires_login": True,
        }

    sb = _get_sb()
    op = (operation or "view").lower().strip()

    if op in ("view", "get"):
        try:
            # 1. Fetch open positions from `positions` table
            res = (
                sb.from_("positions")
                .select("id, symbol, name, quantity, entry_price, entry_at, status, source, added_at")
                .eq("user_id", user_id)
                .eq("status", "open")
                .order("added_at", desc=True)
                .limit(100)
                .execute()
            )
            raw_positions = res.data or []

            # Filter real holdings (quantity > 0)
            holdings = [
                p for p in raw_positions
                if p.get("quantity") is not None and _safe_float(p.get("quantity")) is not None and _safe_float(p.get("quantity")) > 0
            ]

            # 2. Fetch cash balance from `profiles`
            cash = 0.0
            try:
                prof_res = sb.from_("profiles").select("cash_balance").eq("id", user_id).limit(1).execute()
                if prof_res.data:
                    cash = _safe_float(prof_res.data[0].get("cash_balance")) or 0.0
            except Exception:
                cash = 0.0

            if not holdings:
                return {
                    "status": "success",
                    "operation": "view",
                    "message": "محفظتك فاضية حالياً. تقدر تضيف أسهمك هنا بالكتابة أو برفع سكرين شوت لمحفظتك وهحللها فوراً.",
                    "positions_count": 0,
                    "positions": [],
                    "cash_balance": round(cash, 2),
                    "totals": {
                        "positions_count": 0,
                        "cost_basis": 0.0,
                        "market_value": 0.0,
                        "profit_value": 0.0,
                        "profit_pct": 0.0,
                        "equity": round(cash, 2),
                    },
                }

            # 3. Enrich holdings with latest market prices
            symbols = list({str(p.get("symbol", "")).upper() for p in holdings if p.get("symbol")})
            price_map: Dict[str, Optional[float]] = {}
            change_map: Dict[str, Optional[float]] = {}
            if symbols:
                try:
                    tech_res = (
                        sb.from_("stock_technical_indicators")
                        .select("symbol, close, change_pct, date")
                        .in_("symbol", symbols)
                        .order("date", desc=True)
                        .limit(len(symbols) * 3)
                        .execute()
                    )
                    for row in tech_res.data or []:
                        s = str(row.get("symbol", "")).upper()
                        if s and s not in price_map:
                            price_map[s] = _safe_float(row.get("close"))
                            change_map[s] = _safe_float(row.get("change_pct"))
                except Exception:
                    pass

                missing = [s for s in symbols if s not in price_map]
                if missing:
                    try:
                        sp_res = (
                            sb.from_("stock_prices")
                            .select("symbol, close, change_pct, date")
                            .in_("symbol", missing)
                            .order("date", desc=True)
                            .limit(len(missing) * 3)
                            .execute()
                        )
                        for row in sp_res.data or []:
                            s = str(row.get("symbol", "")).upper()
                            if s and s not in price_map:
                                price_map[s] = _safe_float(row.get("close"))
                                change_map[s] = _safe_float(row.get("change_pct"))
                    except Exception:
                        pass

            enriched = []
            for p in holdings:
                s = str(p.get("symbol", "")).upper()
                qty = _safe_float(p.get("quantity"))
                entry = _safe_float(p.get("entry_price"))
                last_price = price_map.get(s)
                change_pct = change_map.get(s)

                valid_entry = entry is not None and entry > 0
                cost_basis = (qty * entry) if (qty is not None and valid_entry) else None
                market_value = (qty * last_price) if (qty is not None and last_price is not None) else None
                profit_value = (market_value - cost_basis) if (cost_basis is not None and market_value is not None) else None
                profit_pct = ((profit_value / cost_basis) * 100) if (cost_basis and cost_basis > 0 and profit_value is not None) else None

                enriched.append({
                    "id": p.get("id"),
                    "symbol": s,
                    "name": p.get("name") or s,
                    "quantity": qty,
                    "entry_price": entry,
                    "last_price": last_price,
                    "change_pct": change_pct,
                    "market_value": round(market_value, 2) if market_value is not None else None,
                    "cost_basis": round(cost_basis, 2) if cost_basis is not None else None,
                    "profit_value": round(profit_value, 2) if profit_value is not None else None,
                    "profit_pct": round(profit_pct, 2) if profit_pct is not None else None,
                    "added_at": p.get("added_at"),
                })

            has_unknown_cost = any(p["cost_basis"] is None for p in enriched)
            total_cost = None if has_unknown_cost else sum(p["cost_basis"] or 0 for p in enriched)
            has_unknown_val = any(p["market_value"] is None for p in enriched)
            total_value = None if has_unknown_val else sum(p["market_value"] or 0 for p in enriched)
            total_profit = (total_value - total_cost) if (total_cost is not None and total_value is not None) else None
            total_profit_pct = ((total_profit / total_cost) * 100) if (total_cost and total_cost > 0 and total_profit is not None) else None
            equity = (total_value + cash) if total_value is not None else cash

            return {
                "status": "success",
                "operation": "view",
                "message": f"محفظتك تحتوي على {len(enriched)} سهم.",
                "positions_count": len(enriched),
                "positions": enriched,
                "cash_balance": round(cash, 2),
                "totals": {
                    "positions_count": len(enriched),
                    "cost_basis": round(total_cost, 2) if total_cost is not None else None,
                    "market_value": round(total_value, 2) if total_value is not None else None,
                    "profit_value": round(total_profit, 2) if total_profit is not None else None,
                    "profit_pct": round(total_profit_pct, 2) if total_profit_pct is not None else None,
                    "equity": round(equity, 2),
                },
            }
        except Exception as e:
            return {"status": "error", "message": f"تعذر استرجاع المحفظة: {str(e)}"}

    # Write operations require explicit intent in user's prompt (anti-injection guard)
    write_intent_patterns = r"(احفظ|سجل|اشتريت|شريت|ضف|اضف|بيع|بعت|احذف|امسح|عدل|عدلي|غير|حدث)"
    if not re.search(write_intent_patterns, user_prompt):
        return {
            "status": "blocked",
            "message": "لم يتم تأكيد طلب تعديل المحفظة من رسالة المستخدم صراحةً.",
        }

    clean_sym = _normalize_symbol(symbol)
    if not clean_sym:
        return {"status": "error", "message": "رمز السهم مطلوب لإجراء تعديل المحفظة."}

    try:
        res = (
            sb.from_("positions")
            .select("id, symbol, name, quantity, entry_price, status")
            .eq("user_id", user_id)
            .eq("symbol", clean_sym)
            .eq("status", "open")
            .limit(1)
            .execute()
        )
        existing = res.data[0] if res.data else None

        if op in ("add", "buy"):
            if existing:
                old_qty = _safe_float(existing.get("quantity")) or 0.0
                add_qty = _safe_float(quantity) or 0.0
                new_qty = old_qty + add_qty
                old_entry = _safe_float(existing.get("entry_price"))
                new_entry = _safe_float(price)
                if old_entry and new_entry and new_qty > 0:
                    avg_entry = ((old_entry * old_qty) + (new_entry * add_qty)) / new_qty
                else:
                    avg_entry = new_entry if new_entry is not None else old_entry
                sb.from_("positions").update({
                    "quantity": new_qty,
                    "entry_price": round(avg_entry, 4) if avg_entry is not None else None,
                }).eq("id", existing["id"]).execute()
                msg = f"تم بنجاح تحديث سهم {clean_sym}: إجمالي الرصيد الآن {new_qty} سهم بمتوسط سعر {round(avg_entry, 2) if avg_entry else '—'} ج.م."
            else:
                stock_name = clean_sym
                try:
                    s_res = sb.from_("stocks").select("name_ar, name").eq("symbol", clean_sym).limit(1).execute()
                    if s_res.data:
                        stock_name = s_res.data[0].get("name_ar") or s_res.data[0].get("name") or clean_sym
                except Exception:
                    pass
                row = {
                    "user_id": user_id,
                    "symbol": clean_sym,
                    "name": stock_name,
                    "quantity": quantity or 0,
                    "entry_price": price,
                    "status": "open",
                    "source": "chatbot",
                }
                try:
                    sb.from_("positions").insert(row).execute()
                except Exception as ins_err:
                    if "source" in str(ins_err).lower() or "enum" in str(ins_err).lower():
                        row.pop("source", None)
                        sb.from_("positions").insert(row).execute()
                    else:
                        raise
                msg = f"تم بنجاح إضافة {quantity or 0} سهم من {clean_sym} إلى محفظتك" + (f" بسعر {price} ج.م." if price else ".")

            return {
                "status": "success",
                "operation": op,
                "symbol": clean_sym,
                "message": msg,
            }

        elif op in ("update",):
            if not existing:
                return {"status": "error", "message": f"سهم {clean_sym} غير موجود في محفظتك المفتوحة."}
            updates = {}
            if quantity is not None:
                updates["quantity"] = quantity
            if price is not None:
                updates["entry_price"] = price
            if not updates:
                return {"status": "error", "message": "يلزم تحديد الكمية أو السعر لتعديل المركز."}
            sb.from_("positions").update(updates).eq("id", existing["id"]).execute()
            return {
                "status": "success",
                "operation": op,
                "symbol": clean_sym,
                "message": f"تم تعديل مركز سهم {clean_sym} بنجاح.",
            }

        elif op in ("remove", "delete"):
            if not existing:
                return {"status": "error", "message": f"سهم {clean_sym} غير موجود في محفظتك."}
            try:
                sb.from_("positions").update({"status": "removed"}).eq("id", existing["id"]).execute()
            except Exception:
                sb.from_("positions").delete().eq("id", existing["id"]).execute()
            return {
                "status": "success",
                "operation": op,
                "symbol": clean_sym,
                "message": f"تم حذف سهم {clean_sym} من محفظتك بنجاح.",
            }

        elif op in ("sell",):
            if not existing:
                return {"status": "error", "message": f"سهم {clean_sym} غير موجود في محفظتك المفتوحة."}
            held = _safe_float(existing.get("quantity")) or 0.0
            sell_qty = _safe_float(quantity) if quantity is not None else held
            if sell_qty <= 0:
                return {"status": "error", "message": "كمية البيع يجب أن تكون أكبر من الصفر."}
            if sell_qty >= held:
                update_data = {"status": "closed"}
                if price is not None:
                    update_data["status_price"] = price
                sb.from_("positions").update(update_data).eq("id", existing["id"]).execute()
                msg = f"تم تسجيل بيع كامل رصيد سهم {clean_sym} ({held} سهم)."
            else:
                rem = held - sell_qty
                sb.from_("positions").update({"quantity": rem}).eq("id", existing["id"]).execute()
                msg = f"تم تسجيل بيع {sell_qty} سهم من {clean_sym}، والمتبقي {rem} سهم."

            # Update cash if price provided
            if price and price > 0:
                proceeds = sell_qty * price
                try:
                    p_res = sb.from_("profiles").select("cash_balance").eq("id", user_id).limit(1).execute()
                    current_cash = _safe_float(p_res.data[0].get("cash_balance")) or 0.0 if p_res.data else 0.0
                    sb.from_("profiles").update({"cash_balance": current_cash + proceeds}).eq("id", user_id).execute()
                except Exception:
                    pass

            return {
                "status": "success",
                "operation": op,
                "symbol": clean_sym,
                "message": msg,
            }
        else:
            return {"status": "error", "message": f"العملية {op} غير مدعومة."}
    except Exception as e:
        return {"status": "error", "message": f"تعذر تحديث المحفظة: {str(e)}"}


async def execute_manage_portfolio(
    user_id: Optional[str],
    operation: str,
    symbol: Optional[str] = None,
    quantity: Optional[float] = None,
    price: Optional[float] = None,
    user_prompt: str = "",
) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_manage_portfolio, user_id, operation, symbol, quantity, price, user_prompt)


BENCHMARK_FIXTURES: Dict[str, Any] = {
    "get_stock": {
        "status": "success",
        "stocks": [
            {
                "symbol": "COMI",
                "name_ar": "البنك التجاري الدولي",
                "name_en": "Commercial International Bank",
                "close": 129.50,
                "change_pct": 1.25,
                "volume": 2450000,
                "rsi_14": 52.4,
                "macd": 0.85,
                "macd_signal": 0.60,
                "macd_histogram": 0.25,
                "bb_upper": 133.0,
                "bb_lower": 124.0,
                "ema_50": 125.2,
                "ema_200": 118.5,
                "sharia_compliant": True,
                "king_ai_score": 8.5,
                "egx_ai_score": 8.8,
            },
            {
                "symbol": "FWRY",
                "name_ar": "فوري لتكنولوجيا البنوك",
                "name_en": "Fawry",
                "close": 7.85,
                "change_pct": 2.10,
                "volume": 12400000,
                "rsi_14": 58.2,
                "macd": 0.12,
                "macd_signal": 0.08,
                "macd_histogram": 0.04,
                "bb_upper": 8.10,
                "bb_lower": 7.45,
                "ema_50": 7.55,
                "ema_200": 6.95,
                "sharia_compliant": True,
                "king_ai_score": 7.9,
                "egx_ai_score": 8.1,
            },
            {
                "symbol": "ETEL",
                "name_ar": "المصرية للاتصالات",
                "name_en": "Telecom Egypt",
                "close": 36.80,
                "change_pct": -0.54,
                "volume": 850000,
                "rsi_14": 46.8,
                "macd": -0.15,
                "macd_signal": -0.10,
                "macd_histogram": -0.05,
                "bb_upper": 38.5,
                "bb_lower": 35.2,
                "ema_50": 36.5,
                "ema_200": 34.8,
                "sharia_compliant": True,
                "king_ai_score": 7.2,
                "egx_ai_score": 7.5,
            }
        ]
    },
    "get_stock_levels": {
        "status": "success",
        "levels": [
            {
                "symbol": "COMI",
                "current_price": 129.50,
                "support_1": 126.00,
                "support_2": 122.50,
                "resistance_1": 132.50,
                "resistance_2": 136.00,
                "stop_loss": 123.50,
                "target_1": 132.50,
                "target_2": 136.00,
                "trend": "صاعد معتدل",
            },
            {
                "symbol": "FWRY",
                "current_price": 7.85,
                "support_1": 7.60,
                "support_2": 7.35,
                "resistance_1": 8.10,
                "resistance_2": 8.40,
                "stop_loss": 7.40,
                "target_1": 8.10,
                "target_2": 8.40,
                "trend": "صاعد قوي",
            }
        ]
    },
    "get_market": {
        "status": "success",
        "egx30": {"value": 30550.0, "change_pct": 0.65},
        "egx70": {"value": 7250.0, "change_pct": 1.15},
        "egx33_sharia": {"value": 3120.0, "change_pct": 0.80},
        "total_turnover_egp": "3.85 مليار جنيه",
        "advancers": 85,
        "decliners": 42,
        "market_sentiment": "إيجابي تجميعي",
        "top_gainers": [{"symbol": "FWRY", "change_pct": 2.10}, {"symbol": "COMI", "change_pct": 1.25}],
        "top_turnover": [{"symbol": "COMI", "turnover_egp": "450 مليون"}, {"symbol": "TMGH", "turnover_egp": "380 مليون"}],
    },
    "get_recommendations": {
        "status": "success",
        "total_open": 3,
        "recommendations": [
            {"symbol": "COMI", "timeframe": "سوينغ قصير 🎯", "entry": 128.0, "target": 135.0, "stop": 123.0, "gain_expected": "+5.5%"},
            {"symbol": "FWRY", "timeframe": "لحظية سريعة ⚡", "entry": 7.75, "target": 8.20, "stop": 7.45, "gain_expected": "+5.8%"},
            {"symbol": "SWDY", "timeframe": "سوينغ متوسط 📈", "entry": 44.5, "target": 49.0, "stop": 42.0, "gain_expected": "+10.1%"},
        ]
    },
    "get_comparison": {
        "status": "success",
        "comparison": [
            {"symbol": "COMI", "name": "البنك التجاري الدولي", "price": 129.5, "rsi": 52.4, "pe_ratio": 7.8, "trend": "صاعد"},
            {"symbol": "ETEL", "name": "المصرية للاتصالات", "price": 36.8, "rsi": 46.8, "pe_ratio": 6.2, "trend": "عرضي"},
        ]
    },
    "get_technical_scan": {
        "status": "success",
        "signals": [
            {"symbol": "FWRY", "type": "اختراق مقاومة", "strength": "قوي", "price": 7.85},
            {"symbol": "COMI", "type": "دايفرجنس إيجابي", "strength": "متوسط", "price": 129.50},
        ]
    },
    "get_accumulation_stocks": {
        "status": "success",
        "accumulation_stocks": [
            {"symbol": "COMI", "score": 92, "phase": "تجميع ذكي (Markup)"},
            {"symbol": "FWRY", "score": 88, "phase": "تجميع وايكوف"},
        ]
    },
    "get_news": {
        "status": "success",
        "news": [
            {"title": "نتائج أعمال قوية ونمو أرباح قياسي", "date": "اليوم", "impact": "إيجابي"}
        ]
    },
    "manage_portfolio": {
        "status": "success",
        "operation": "view",
        "message": "محفظتك تحتوي على 2 سهم.",
        "positions_count": 2,
        "positions": [
            {
                "id": "pos_1",
                "symbol": "COMI",
                "name": "البنك التجاري الدولي",
                "quantity": 500,
                "entry_price": 125.0,
                "last_price": 129.50,
                "change_pct": 1.25,
                "market_value": 64750.0,
                "cost_basis": 62500.0,
                "profit_value": 2250.0,
                "profit_pct": 3.6,
            },
            {
                "id": "pos_2",
                "symbol": "FWRY",
                "name": "فوري لتكنولوجيا البنوك",
                "quantity": 2000,
                "entry_price": 7.50,
                "last_price": 7.85,
                "change_pct": 2.10,
                "market_value": 15700.0,
                "cost_basis": 15000.0,
                "profit_value": 700.0,
                "profit_pct": 4.67,
            },
        ],
        "cash_balance": 25000.0,
        "totals": {
            "positions_count": 2,
            "cost_basis": 77500.0,
            "market_value": 80450.0,
            "profit_value": 2950.0,
            "profit_pct": 3.81,
            "equity": 105450.0,
        },
    },
    "calculate_position": {
        "status": "success",
        "symbol": "COMI",
        "quantity": 500,
        "entry_price": 125.0,
        "close_price": 129.50,
        "total_cost": 62500.0,
        "current_market_value": 64750.0,
        "profit_loss_egp": 2250.0,
        "profit_loss_pct": 3.6,
    }
}


# ---------------------------------------------------------------------------
# Master Tool Dispatcher
# ---------------------------------------------------------------------------
async def dispatch_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: Optional[str] = None,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """
    Main asynchronous dispatcher for all agentic tools.
    """
    # Safe benchmark guard: Return in-memory fixtures to protect Supabase DB and quotas
    if user_id == "00000000-0000-0000-0000-000000000000":
        if tool_name in BENCHMARK_FIXTURES:
            return BENCHMARK_FIXTURES[tool_name]
        return {"status": "success", "data": "Benchmark mode active."}

    try:
        if tool_name == "get_stock":
            symbols = arguments.get("symbols") or ([arguments["symbol"]] if "symbol" in arguments else [])
            return await execute_get_stock(symbols)

        elif tool_name == "get_stock_levels":
            symbols = arguments.get("symbols") or ([arguments["symbol"]] if "symbol" in arguments else [])
            return await execute_get_stock_levels(symbols)

        elif tool_name == "get_market":
            return await execute_get_market()

        elif tool_name == "get_recommendations":
            return await execute_get_recommendations(
                status=arguments.get("status", "open"),
                timeframe=arguments.get("timeframe", "all"),
                symbols=arguments.get("symbols"),
                sharia_only=arguments.get("sharia_only", False),
                limit=arguments.get("limit", 20),
            )

        elif tool_name == "get_technical_scan":
            return await execute_get_technical_scan(
                preset=arguments.get("preset", "top_gainers"),
                sharia_only=arguments.get("sharia_only", False),
            )

        elif tool_name == "get_accumulation_stocks":
            return await execute_get_accumulation_stocks(
                sharia_only=arguments.get("sharia_only", False)
            )

        elif tool_name == "get_news":
            return await execute_get_news(symbols=arguments.get("symbols"))

        elif tool_name == "get_comparison":
            return await execute_get_comparison(symbols=arguments.get("symbols", []))

        elif tool_name == "get_fair_value":
            return await execute_get_fair_value(
                symbols=arguments.get("symbols"),
                mode=arguments.get("mode", "screen_undervalued"),
                sharia_only=arguments.get("sharia_only", False),
                limit=arguments.get("limit", 10),
            )

        elif tool_name == "get_sharia_cleanser":
            return await execute_get_sharia_cleanser(
                symbol=arguments.get("symbol", ""),
                shares_count=arguments.get("shares_count", 1000.0),
                coupon_per_share=arguments.get("coupon_per_share"),
                purification_rate_pct=arguments.get("purification_rate_pct"),
            )

        elif tool_name == "manage_portfolio":
            return await execute_manage_portfolio(
                user_id=user_id,
                operation=arguments.get("operation", "view"),
                symbol=arguments.get("symbol"),
                quantity=arguments.get("quantity"),
                price=arguments.get("price"),
                user_prompt=user_prompt,
            )

        elif tool_name == "calculate_position":
            return await execute_calculate_position(
                symbol=arguments.get("symbol", ""),
                quantity=arguments.get("quantity"),
                entry_price=arguments.get("entry_price"),
                total_cost=arguments.get("total_cost"),
            )

        elif tool_name == "enable_autonomous_recommendations":
            return {
                "status": "success",
                "autonomous_recommendations_enabled": True,
                "message": "تم تفعيل وضع التوصيات الحرة المستقلة للذكاء الاصطناعي بنجاح في الواجهة.",
            }

        elif tool_name == "disable_autonomous_recommendations":
            return {
                "status": "success",
                "autonomous_recommendations_enabled": False,
                "message": "تم إيقاف وضع التوصيات الحرة المستقلة والعودة للوضع القياسي.",
            }

        else:
            return {"status": "error", "message": f"الأداة {tool_name} غير معروفة"}

    except Exception as e:
        return {"status": "error", "message": f"خطأ أثناء تنفيذ الأداة {tool_name}: {str(e)}"}
