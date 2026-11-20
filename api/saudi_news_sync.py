"""
api/saudi_news_sync.py — Saudi Market (TASI / Tadawul) News & Sentiment Engine.
Fetches real Arabic & English Google News RSS (gl=SA) for Tadawul stocks,
scores sentiment via FINANCIAL_LEXICON, buckets by article publish date,
and upserts into SAUDI_SUPABASE.stock_news_sentiment (exchange='TADAWUL').
"""
from __future__ import annotations

import datetime as dt
import email.utils
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from supabase import Client, create_client

from api.news_sentiment_engine import (
    analyze_sentiment,
    is_relevant_news,
    is_unrelated_news,
)
from api.saudi_stock_aliases import SAUDI_STOCK_NAMES_AR

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}

# Priority liquid TASI stocks to always cover first (plus any stocks from DB)
PRIORITY_TASI_SYMBOLS: List[str] = [
    "2222", "1120", "2010", "7010", "1180", "1211", "2082", "1150", "2280", "4030",
    "1010", "1050", "1060", "1080", "1140", "1111", "2020", "2050", "2060", "2290",
    "2310", "2350", "2380", "3010", "3020", "3030", "3050", "4001", "4002", "4003",
    "4004", "4007", "4009", "4013", "4031", "4081", "4161", "4190", "4200", "4210",
    "4220", "4240", "4250", "4260", "4300", "4310", "4321", "5110", "6001", "6002",
    "6010", "6015", "6018", "7020", "7030", "7040", "7200", "7202", "7203", "8010",
    "8020", "8030", "8210", "8230", "3007", "1830", "1831", "1834", "2223", "2283",
]


def _load_saudi_supabase() -> Client:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(repo_root, "web", ".env.local"))
    load_dotenv(os.path.join(repo_root, ".env"))
    url = (os.getenv("SAUDI_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_URL") or "").strip()
    key = (os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("Missing SAUDI_SUPABASE_URL / SAUDI_SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def _fetch_rss_items(query: str, hl: str = "ar", gl: str = "SA", ceid: str = "SA:ar", days_back: int = 15) -> List[Dict[str, str]]:
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}+when:{days_back}d&hl={hl}&gl={gl}&ceid={ceid}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        if resp.status_code != 200 or "<item>" not in resp.text:
            return []
        root = ET.fromstring(resp.text)
    except Exception:
        return []

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_back)
    items: List[Dict[str, str]] = []
    for item in root.findall("./channel/item"):
        title_el = item.find("title")
        pub_el = item.find("pubDate")
        source_el = item.find("source")
        link_el = item.find("link")
        if title_el is None or not title_el.text:
            continue
        raw_title = title_el.text.strip()
        source = source_el.text.strip() if source_el is not None and source_el.text else "Google News"
        if source and source != "Google News":
            suffix = f" - {source}"
            if raw_title.endswith(suffix):
                raw_title = raw_title[: -len(suffix)].strip()
            elif " - " in raw_title:
                raw_title = raw_title.rsplit(" - ", 1)[0].strip()
        raw_title = re.sub(r"\s*[-–|]\s*(?:ارقام|أرقام)\s*:.*$", "", raw_title).strip()
        if "ارقام" in source or "أرقام" in source:
            source = "أرقام"

        pub_date = dt.date.today().isoformat()
        if pub_el is not None and pub_el.text:
            try:
                parsed_dt = email.utils.parsedate_to_datetime(pub_el.text.strip())
                if parsed_dt.tzinfo is None:
                    parsed_dt = parsed_dt.replace(tzinfo=dt.timezone.utc)
                if parsed_dt < cutoff:
                    continue
                pub_date = parsed_dt.date().isoformat()
            except Exception:
                pass

        if is_unrelated_news(raw_title):
            continue

        items.append({
            "title": raw_title,
            "source": source,
            "date": pub_date,
            "link": link_el.text.strip() if link_el is not None and link_el.text else "",
        })
    return items


def run_saudi_news_sync(max_symbols: int = 80, days_back: int = 15) -> Dict[str, Any]:
    sb = _load_saudi_supabase()
    stocks_res = sb.table("stocks").select("symbol,name,name_ar").eq("exchange", "TADAWUL").execute()
    stock_rows = stocks_res.data or []

    aliases_by_sym: Dict[str, List[str]] = {}
    for row in stock_rows:
        sym = str(row.get("symbol") or "").strip().split(".")[0]
        if not sym:
            continue
        names: List[str] = []
        if sym in SAUDI_STOCK_NAMES_AR:
            names.append(SAUDI_STOCK_NAMES_AR[sym])
        if row.get("name_ar"):
            for part in re.split(r"[,،|/]", str(row["name_ar"])):
                p = part.strip()
                if p:
                    names.append(p)
        if row.get("name"):
            names.append(str(row["name"]).strip())
        aliases_by_sym[sym] = list(dict.fromkeys(names))

    ordered_syms = [s for s in PRIORITY_TASI_SYMBOLS if s in aliases_by_sym]
    for s in aliases_by_sym:
        if s not in ordered_syms:
            ordered_syms.append(s)
    target_syms = ordered_syms[:max_symbols]

    rows_saved = 0
    symbols_with_news = 0
    total_headlines = 0

    for sym in target_syms:
        aliases = aliases_by_sym.get(sym, [sym])
        primary_ar = aliases[0] if aliases else sym
        # Clean parenthetical suffixes for a crisper Google News query
        clean_ar = re.sub(r"\s*\([^)]*\)", "", primary_ar).strip() or primary_ar

        fetched: List[Dict[str, str]] = []
        seen_titles = set()

        for q, hl, ceid in [
            (f'"{clean_ar}" سهم OR تداول', "ar", "SA:ar"),
            (f"{sym} تداول", "ar", "SA:ar"),
        ]:
            for item in _fetch_rss_items(q, hl=hl, gl="SA", ceid=ceid, days_back=days_back):
                t = item["title"]
                if t in seen_titles:
                    continue
                # Accept if headline mentions the company name or exact 4-digit symbol
                if any(is_relevant_news(t, sym, a) for a in aliases) or re.search(rf"\b{re.escape(sym)}\b", t):
                    seen_titles.add(t)
                    fetched.append(item)

        if not fetched:
            time.sleep(0.1)
            continue

        by_date: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        for item in fetched:
            by_date[item["date"]].append(item)

        symbols_with_news += 1
        for date_str, day_items in by_date.items():
            sent = analyze_sentiment(day_items)
            if sent["news_count"] <= 0:
                continue
            total_headlines += sent["news_count"]
            payload = {
                "symbol": sym,
                "exchange": "TADAWUL",
                "date": date_str,
                "sentiment_score": sent["sentiment_score"],
                "news_count": sent["news_count"],
                "negative_flag": sent["negative_flag"],
                "positive_flag": sent["positive_flag"],
                "headlines": sent["headlines"],
                "sources": sent["sources"],
            }
            sb.table("stock_news_sentiment").upsert(payload, on_conflict="symbol,date").execute()
            rows_saved += 1

        time.sleep(0.15)

    return {
        "ok": True,
        "symbols_scanned": len(target_syms),
        "symbols_with_news": symbols_with_news,
        "rows_saved": rows_saved,
        "total_headlines": total_headlines,
    }


if __name__ == "__main__":
    print(run_saudi_news_sync(max_symbols=70, days_back=15))
