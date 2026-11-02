"""
Daily Trap Detector Engine (Bull Traps / Upthrusts & Bear Traps / Wyckoff Springs).
Runs in the closing pipeline (5:00 PM Cairo) after full daily candles settle.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _finite(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        f = float(val)
        return f if f == f and abs(f) != float("inf") else None
    except Exception:
        return None


def detect_daily_traps(
    indicators: List[Dict[str, Any]],
    bars_by_symbol: Dict[str, Dict[str, Any]],
    as_of: Optional[str] = None,
    max_per_side: int = 8,
) -> Dict[str, Any]:
    bear_traps: List[Dict[str, Any]] = []
    bull_traps: List[Dict[str, Any]] = []

    for ind in indicators or []:
        sym = str(ind.get("symbol") or "").strip().upper()
        if not sym:
            continue
        bar = bars_by_symbol.get(sym)
        if not bar:
            continue

        high = _finite(bar.get("high"))
        low = _finite(bar.get("low"))
        close = _finite(bar.get("close")) or _finite(ind.get("close"))
        open_p = _finite(bar.get("open")) or close
        if not high or not low or not close or close <= 0 or high <= low:
            continue

        rng = high - low
        range_pct = (rng / close) * 100.0
        if range_pct < 1.5:
            continue

        recovery_ratio = (close - low) / rng
        rejection_ratio = (high - close) / rng
        r_vol = _finite(ind.get("r_vol")) or 1.0
        rsi = _finite(ind.get("rsi_14"))
        change_pct = _finite(ind.get("change_pct"))
        sma20 = _finite(ind.get("sma_20")) or _finite(ind.get("ema_20")) or close
        bb_lower = _finite(ind.get("bb_lower")) or (sma20 * 0.95)
        bb_upper = _finite(ind.get("bb_upper")) or (sma20 * 1.05)
        ai_raw = _finite(ind.get("egx_ai_score"))
        ai_score = round(ai_raw * 100, 1) if ai_raw is not None and 0 <= ai_raw <= 1 else ai_raw

        # 1. Bear Trap (Wyckoff Spring / Fake Breakdown)
        support_ref = bb_lower if abs(low - bb_lower) < abs(low - sma20) else sma20
        dipped_support = low <= support_ref * 1.005
        reclaimed_support = close >= support_ref * 0.992
        if dipped_support and reclaimed_support and recovery_ratio >= 0.62 and r_vol >= 0.8:
            conviction = min(99, round(recovery_ratio * 65 + min(r_vol, 3.0) * 11, 1))
            bear_traps.append({
                "symbol": sym,
                "trapType": "BEAR_TRAP",
                "close": round(close, 2),
                "low": round(low, 2),
                "high": round(high, 2),
                "keyLevel": round(support_ref, 2),
                "wickPct": round(recovery_ratio * 100, 1),
                "relativeVolume": round(r_vol, 2),
                "changePct": round(change_pct, 2) if change_pct is not None else None,
                "rsi": round(rsi, 1) if rsi is not None else None,
                "aiScore": ai_score,
                "conviction": conviction,
            })
            continue

        # 2. Bull Trap (Wyckoff Upthrust / Fake Breakout)
        resistance_ref = bb_upper if high >= bb_upper * 0.985 else sma20 * 1.015
        spiked_resistance = high >= resistance_ref
        failed_breakout = close < resistance_ref * 0.998
        if spiked_resistance and failed_breakout and rejection_ratio >= 0.62 and r_vol >= 0.8:
            conviction = min(99, round(rejection_ratio * 65 + min(r_vol, 3.0) * 11, 1))
            bull_traps.append({
                "symbol": sym,
                "trapType": "BULL_TRAP",
                "close": round(close, 2),
                "low": round(low, 2),
                "high": round(high, 2),
                "keyLevel": round(resistance_ref, 2),
                "wickPct": round(rejection_ratio * 100, 1),
                "relativeVolume": round(r_vol, 2),
                "changePct": round(change_pct, 2) if change_pct is not None else None,
                "rsi": round(rsi, 1) if rsi is not None else None,
                "aiScore": ai_score,
                "conviction": conviction,
            })

    bear_traps.sort(key=lambda x: x["conviction"], reverse=True)
    bull_traps.sort(key=lambda x: x["conviction"], reverse=True)

    return {
        "asOf": as_of,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "bearTraps": bear_traps[:max_per_side],
        "bullTraps": bull_traps[:max_per_side],
        "totalBearTraps": len(bear_traps),
        "totalBullTraps": len(bull_traps),
    }


def sync_daily_traps_to_market_cache(supabase_client: Any) -> Dict[str, Any]:
    """Compute traps for the latest EGX session and persist to market_cache."""
    if not supabase_client:
        return {"ok": False, "message": "No Supabase client"}
    latest = (
        supabase_client.table("stock_technical_indicators")
        .select("date")
        .eq("exchange", "EGX")
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    as_of = str(latest.data[0]["date"])[:10] if latest.data else None
    if not as_of:
        return {"ok": False, "message": "No latest technical indicator date"}

    ind_res = (
        supabase_client.table("stock_technical_indicators")
        .select("symbol,close,change_pct,rsi_14,r_vol,ema_20,sma_20,bb_upper,bb_lower,egx_ai_score")
        .eq("exchange", "EGX")
        .eq("date", as_of)
        .limit(400)
        .execute()
    )
    bars_res = (
        supabase_client.table("stock_prices")
        .select("symbol,open,high,low,close")
        .eq("exchange", "EGX")
        .eq("date", as_of)
        .limit(400)
        .execute()
    )
    bars_map = {str(b["symbol"]).strip().upper(): b for b in (bars_res.data or []) if b.get("symbol")}
    snapshot = detect_daily_traps(ind_res.data or [], bars_map, as_of=as_of)

    supabase_client.table("market_cache").upsert({
        "cache_key": "daily_traps_snapshot",
        "country": "Egypt",
        "payload": snapshot,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="cache_key,country").execute()

    return {
        "ok": True,
        "asOf": as_of,
        "bearTraps": snapshot["totalBearTraps"],
        "bullTraps": snapshot["totalBullTraps"],
    }

