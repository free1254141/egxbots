"""
Daily signal-performance engine for the technical page.

Measures how the two end-of-session scanners actually behaved afterwards:
  * Unusual Activity  — volume >= 2x the prior 20-session average.
  * Trap Detector     — Wyckoff Springs (bullish) and Upthrusts (bearish).

Runs once in the closing pipeline (after prices/indicators, BEFORE the trap
snapshot is overwritten and BEFORE cache revalidation) and stores one payload
in market_cache["signal_performance_EGX"]. The web route caches it on Vercel
with the daily-market-data tag until the next closing run.

Outcomes are deterministic and computed only from stored daily bars:
  * T+1 close return, best high / worst low over the next 3 sessions.
  * Bullish signal "win"  = next session closes above the signal close.
  * Bearish signal "win"  = next session closes below the signal close.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any, Dict, List, Optional

from api.trap_detector import detect_daily_traps

CACHE_KEY = "signal_performance_EGX"
UNUSUAL_RVOL = 2.0
WINDOW_SESSIONS = 40      # evaluation window (signal dates)
HISTORY_DAYS = 120        # calendar days of bars to load (window + 20-day warmup)
PAGE = 1000


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def _load_bars(client: Any, since: str) -> Dict[str, List[Dict[str, Any]]]:
    """Bounded, paginated read of EGX daily bars since `since` (explicit columns)."""
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        res = (client.table("stock_prices")
               .select("symbol,date,open,high,low,close,volume")
               .eq("exchange", "EGX").gte("date", since)
               .order("date", desc=False).order("symbol", desc=False)
               .range(start, start + PAGE - 1).execute())
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < PAGE or start > 60000:
            break
        start += PAGE
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        sym = str(r.get("symbol") or "").strip().upper()
        if sym:
            by_symbol.setdefault(sym, []).append(r)
    for bars in by_symbol.values():
        bars.sort(key=lambda b: str(b["date"]))
    return by_symbol


def _enrich(bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add r_vol (vs prior 20 sessions), sma_20 and Bollinger bands per bar."""
    out = []
    for i, b in enumerate(bars):
        close, vol = _f(b.get("close")), _f(b.get("volume"))
        item = dict(b, date=str(b["date"])[:10], close=close, high=_f(b.get("high")),
                    low=_f(b.get("low")), open=_f(b.get("open")), volume=vol,
                    r_vol=None, sma_20=None, bb_upper=None, bb_lower=None)
        if i >= 20:
            prev_vols = [_f(x.get("volume")) or 0.0 for x in bars[i - 20:i]]
            avg = sum(prev_vols) / 20
            if avg > 0 and vol:
                item["r_vol"] = vol / avg
            closes = [_f(x.get("close")) for x in bars[i - 19:i + 1]]
            if all(c for c in closes):
                m = sum(closes) / 20
                sd = (sum((c - m) ** 2 for c in closes) / 20) ** 0.5
                item.update(sma_20=m, bb_upper=m + 2 * sd, bb_lower=m - 2 * sd)
        out.append(item)
    return out


def _outcome(bars: List[Dict[str, Any]], i: int) -> Optional[Dict[str, float]]:
    c0 = bars[i]["close"]
    if not c0 or i + 1 >= len(bars) or not bars[i + 1]["close"]:
        return None
    nxt = bars[i + 1:i + 4]
    highs = [b["high"] for b in nxt if b["high"]]
    lows = [b["low"] for b in nxt if b["low"]]
    return {
        "ret1": (bars[i + 1]["close"] - c0) / c0 * 100,
        "maxUp3": ((max(highs) - c0) / c0 * 100) if highs else 0.0,
        "maxDown3": ((min(lows) - c0) / c0 * 100) if lows else 0.0,
        "full3": len(nxt) >= 3,
    }


def _summary(events: List[Dict[str, Any]], bullish: bool) -> Dict[str, Any]:
    if not events:
        return {"events": 0, "winRate": None, "hitRate3d": None, "avgRet1": None, "avgBest3d": None}
    wins = [e for e in events if (e["ret1"] > 0 if bullish else e["ret1"] < 0)]
    full = [e for e in events if e["full3"]]
    hits = [e for e in full if (e["maxUp3"] >= 3 if bullish else e["maxDown3"] <= -3)]
    best = [e["maxUp3"] if bullish else e["maxDown3"] for e in full]
    return {
        "events": len(events),
        "winRate": round(len(wins) / len(events) * 100, 1),
        "hitRate3d": round(len(hits) / len(full) * 100, 1) if full else None,
        "avgRet1": round(mean(e["ret1"] for e in events), 2),
        "avgBest3d": round(mean(best), 2) if best else None,
    }


def _row(sym: str, bars: List[Dict[str, Any]], i: int, extra: Dict[str, Any]) -> Dict[str, Any]:
    o = _outcome(bars, i) or {}
    return {
        "symbol": sym,
        "signalClose": round(bars[i]["close"], 3),
        "nextClose": round(bars[i + 1]["close"], 3) if i + 1 < len(bars) else None,
        "nextHigh": round(bars[i + 1]["high"], 3) if i + 1 < len(bars) and bars[i + 1]["high"] else None,
        "retPct": round(o["ret1"], 2) if o else None,
        "intradayHighPct": round((bars[i + 1]["high"] - bars[i]["close"]) / bars[i]["close"] * 100, 2)
        if o and bars[i + 1]["high"] else None,
        **extra,
    }


def compute_signal_performance(client: Any, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    since = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    raw = _load_bars(client, since)
    data = {sym: _enrich(bars) for sym, bars in raw.items() if len(bars) > 21}

    all_dates = sorted({b["date"] for bars in data.values() for b in bars})
    if len(all_dates) < 3:
        return {"ok": False, "message": "insufficient price history"}
    latest, prev = all_dates[-1], all_dates[-2]
    # Signal dates must have a following session to be evaluated.
    window = set(all_dates[-(WINDOW_SESSIONS + 1):-1])

    idx = {sym: {b["date"]: i for i, b in enumerate(bars)} for sym, bars in data.items()}
    unusual, springs, upthrusts = [], [], []
    review_unusual, recomputed_springs, recomputed_upthrusts = [], [], []

    for d in sorted(window):
        inds, bars_map = [], {}
        for sym, bars in data.items():
            i = idx[sym].get(d)
            if i is None or i + 1 >= len(bars) or bars[i + 1]["date"] not in (all_dates[all_dates.index(d) + 1],):
                continue
            b = bars[i]
            if b["r_vol"] is not None and b["r_vol"] >= UNUSUAL_RVOL and (b["volume"] or 0) > 0:
                o = _outcome(bars, i)
                if o:
                    unusual.append({**o, "symbol": sym, "date": d})
                    if d == prev:
                        review_unusual.append(_row(sym, bars, i, {"relativeVolume": round(b["r_vol"], 2)}))
            if b["sma_20"] is not None:
                inds.append({"symbol": sym, "close": b["close"], "r_vol": b["r_vol"] or 1.0,
                             "sma_20": b["sma_20"], "bb_upper": b["bb_upper"], "bb_lower": b["bb_lower"]})
                bars_map[sym] = b
        snap = detect_daily_traps(inds, bars_map, as_of=d, max_per_side=10_000)
        for kind, bucket, rec in (("bearTraps", springs, recomputed_springs), ("bullTraps", upthrusts, recomputed_upthrusts)):
            for t in snap[kind]:
                sym = t["symbol"]
                i = idx[sym][d]
                o = _outcome(data[sym], i)
                if o:
                    bucket.append({**o, "symbol": sym, "date": d})
                    if d == prev:
                        rec.append(_row(sym, data[sym], i, {"keyLevel": t["keyLevel"], "conviction": t["conviction"]}))

    # Review the traps that were actually PUBLISHED for the previous session when available.
    review_springs, review_upthrusts, review_source = recomputed_springs, recomputed_upthrusts, "recomputed"
    try:
        snap_row = (client.table("market_cache").select("payload")
                    .eq("cache_key", "daily_traps_snapshot").limit(1).execute().data or [])
        published = (snap_row[0].get("payload") if snap_row else None) or {}
        if str(published.get("asOf") or "") == prev:
            def _pub(rows):
                out = []
                for t in rows or []:
                    sym = str(t.get("symbol") or "").upper()
                    i = idx.get(sym, {}).get(prev)
                    if i is not None and sym in data:
                        out.append(_row(sym, data[sym], i, {"keyLevel": t.get("keyLevel"), "conviction": t.get("conviction")}))
                return out
            review_springs, review_upthrusts = _pub(published.get("bearTraps")), _pub(published.get("bullTraps"))
            review_source = "published"
    except Exception as exc:  # review falls back to the recomputed list
        print(f"[SIGNAL_PERF] published traps read failed: {exc}")

    for lst, key in ((review_unusual, "retPct"), (review_springs, "retPct"), (review_upthrusts, "retPct")):
        lst.sort(key=lambda r: (r.get(key) is None, -(r.get(key) or 0)))
    review_unusual = review_unusual[:15]
    movers = [r for r in review_unusual + review_springs if r.get("retPct") is not None]
    top_mover = max(movers, key=lambda r: r["retPct"]) if movers else None

    def _count(rows, bullish=True):
        valid = [r for r in rows if r.get("retPct") is not None]
        good = [r for r in valid if (r["retPct"] > 0 if bullish else r["retPct"] < 0)]
        return {"total": len(valid), "wins": len(good)}

    return {
        "ok": True,
        "asOf": latest,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "windowSessions": len(window),
        "windowStart": min(window) if window else None,
        "methodology": {
            "unusual": f"volume >= {UNUSUAL_RVOL}x prior 20-session average",
            "win": "bullish: next close > signal close; bearish: next close < signal close",
            "hit3d": "bullish: high within 3 sessions >= +3%; bearish: low within 3 sessions <= -3%",
        },
        "unusual": _summary(unusual, True),
        "springs": _summary(springs, True),
        "upthrusts": _summary(upthrusts, False),
        "review": {
            "signalDate": prev,
            "outcomeDate": latest,
            "trapsSource": review_source,
            "unusual": review_unusual,
            "unusualScore": _count(review_unusual),
            "springs": review_springs,
            "springsScore": _count(review_springs),
            "upthrusts": review_upthrusts,
            "upthrustsScore": _count(review_upthrusts, bullish=False),
            "topMover": top_mover,
        },
    }


def sync_signal_performance_to_market_cache(client: Any) -> Dict[str, Any]:
    if not client:
        return {"ok": False, "message": "No Supabase client"}
    payload = compute_signal_performance(client)
    if not payload.get("ok"):
        return payload
    client.table("market_cache").upsert({
        "cache_key": CACHE_KEY,
        "country": "Egypt",
        "payload": payload,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="cache_key,country").execute()
    return {
        "ok": True, "asOf": payload["asOf"],
        "unusual": payload["unusual"], "springs": payload["springs"], "upthrusts": payload["upthrusts"],
    }
