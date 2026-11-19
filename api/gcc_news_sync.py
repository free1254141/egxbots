"""
api/gcc_news_sync.py — UAE (DFM & ADX) & Qatar (QSE) Stock News & Sentiment Sync.

Fetches Arabic & English Google News RSS (gl=AE / gl=QA) for UAE and Qatar
stocks, scores sentiment deterministically, and upserts into
SAUDI_SUPABASE.stock_news_sentiment (on_conflict="symbol,date") with each
stock's exchange ('DFM', 'ADX', 'QSE').
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import sys
import time
from typing import Any, Dict, List

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from api.news_sentiment_engine import analyze_sentiment
from api.saudi_news_sync import (
    _fetch_rss_items,
    _load_saudi_supabase,
)

_EXCHANGE_GEO = {
    "DFM": ("AE", "AE:ar", "AE:en", "سهم دبي"),
    "ADX": ("AE", "AE:ar", "AE:en", "سهم أبوظبي"),
    "QSE": ("QA", "QA:ar", "QA:en", "بورصة قطر"),
}


def sync_gcc_market_news(
    market: str = "all",
    max_symbols: int = 40,
    days_back: int = 15,
    dry_run: bool = False,
) -> Dict[str, Any]:
    sb = _load_saudi_supabase()
    if market == "uae":
        exchanges = ["DFM", "ADX"]
    elif market == "qatar":
        exchanges = ["QSE"]
    else:
        exchanges = ["DFM", "ADX", "QSE"]

    stocks_res = (
        sb.table("stocks")
        .select("symbol,exchange,name,name_ar")
        .in_("exchange", exchanges)
        .eq("is_active", True)
        .order("symbol")
        .limit(max_symbols)
        .execute()
    )
    stocks = getattr(stocks_res, "data", None) or []
    if not stocks:
        return {"ok": True, "market": market, "synced_rows": 0, "reason": "no_stocks"}

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    synced_rows = 0
    matched_symbols = 0

    for st in stocks:
        sym = str(st.get("symbol") or "").strip().upper()
        ex = str(st.get("exchange") or "").strip().upper()
        if not sym or ex not in _EXCHANGE_GEO:
            continue

        gl, ceid_ar, ceid_en, suffix_ar = _EXCHANGE_GEO[ex]
        name_ar = str(st.get("name_ar") or "").strip()
        name_en = str(st.get("name") or "").strip()

        queries: List[tuple[str, str, str]] = []
        if name_ar:
            queries.append((f'"{name_ar}" {suffix_ar}', "ar", ceid_ar))
        if name_en:
            clean_en = name_en.split("(")[0].strip()
            if clean_en:
                queries.append((f'"{clean_en}" {ex} stock', "en", ceid_en))
        if not queries:
            queries.append((f"{sym} {ex} stock", "en", ceid_en))

        seen_titles: set[str] = set()
        collected: List[Dict[str, str]] = []
        for q, hl, ceid in queries[:2]:
            for item in _fetch_rss_items(q, hl=hl, gl=gl, ceid=ceid, days_back=days_back):
                tkey = item["title"].lower()
                if tkey not in seen_titles:
                    seen_titles.add(tkey)
                    collected.append(item)

        if not collected:
            continue

        matched_symbols += 1
        by_date: Dict[str, List[Dict[str, str]]] = {}
        for item in collected[:10]:
            d = item.get("date") or today_str
            by_date.setdefault(d, []).append(item)

        for news_date, items in by_date.items():
            sent = analyze_sentiment(items)
            payload = {
                "symbol": sym,
                "exchange": ex,
                "date": news_date,
                "sentiment_score": sent["sentiment_score"],
                "positive_flag": 1 if sent["positive_flag"] else 0,
                "negative_flag": 1 if sent["negative_flag"] else 0,
                "news_count": sent["news_count"],
                "headlines": sent["headlines"][:8],
                "sources": sent["sources"][:5],
            }
            if not dry_run:
                sb.table("stock_news_sentiment").upsert(payload, on_conflict="symbol,date").execute()
            synced_rows += 1

        time.sleep(0.15)

    return {
        "ok": True,
        "market": market,
        "dry_run": dry_run,
        "stocks_checked": len(stocks),
        "matched_symbols": matched_symbols,
        "synced_rows": synced_rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync UAE & Qatar Stock News & Sentiment")
    parser.add_argument("--market", choices=["all", "uae", "qatar"], default="all")
    parser.add_argument("--max-symbols", type=int, default=40)
    parser.add_argument("--days", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(sync_gcc_market_news(market=args.market, max_symbols=args.max_symbols, days_back=args.days, dry_run=args.dry_run))
