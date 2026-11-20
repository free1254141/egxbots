"""
api/gcc_news_sync.py — UAE (DFM & ADX) & Qatar (QSE) Stock News & Sentiment Sync.

Fetches Arabic & English Google News RSS (gl=AE / gl=QA) for priority UAE and
Qatar stocks, strictly validates that each headline matches the target stock
(blocking foreign-market news, generic market roundups, and bank-name collisions),
scores sentiment deterministically, and upserts into
SAUDI_SUPABASE.stock_news_sentiment (on_conflict="symbol,date") with each
stock's exchange ('DFM', 'ADX', 'QSE').
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import re
import sys
import time
from typing import Any, Dict, List, Tuple

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from api.gcc_disclosures_sync import _AMBIGUOUS_SINGLE_WORD_ALIASES, _is_foreign_market_headline
from api.news_sentiment_engine import analyze_sentiment, _normalize_arabic
from api.saudi_news_sync import (
    _fetch_rss_items,
    _load_saudi_supabase,
)

_EXCHANGE_GEO = {
    "DFM": ("AE", "AE:ar", "AE:en", "سهم دبي"),
    "ADX": ("AE", "AE:ar", "AE:en", "سهم أبوظبي"),
    "QSE": ("QA", "QA:ar", "QA:en", "بورصة قطر"),
}

PRIORITY_UAE_SYMBOLS: Tuple[str, ...] = (
    "EMAAR", "EMAARDEV", "ALDAR", "FAB", "DIB", "IHC", "ADNOCGAS", "ADNOCDIST",
    "ADNOCLS", "ADNOCDRILL", "DEWA", "SALIK", "EAND", "ADIB", "ADCB", "BOROUGE",
    "TAQA", "ARMX", "PARKIN", "TALABAT", "DU", "GFH", "MULTIPLY", "ALPHADHABI",
    "FERTIGLOBE", "LULU", "TABREED", "CBD", "UPP", "ADPORTS", "PUREHEALTH",
    "PRESIGHT", "SPACE42", "MODON", "AIRARABIA", "DSI", "DIC", "ENBD", "DFM",
)

PRIORITY_QATAR_SYMBOLS: Tuple[str, ...] = (
    "QNBK", "QIBK", "IQCD", "QGTS", "ORDS", "MARK", "QFLS", "CBQK", "BRES",
    "MPHC", "VFQS", "DHBK", "QIIK", "GISS", "QEWS", "MEZA", "BLDN", "DBIS",
    "MRDS", "QFBQ", "UDCD", "QNCD", "FALH", "WDAM", "ZHCD", "MKDM", "GWCS",
    "QAMC", "QNNS", "SIIS", "QIMD", "QATI", "DOHI", "DUBK",
)

# Explicit disambiguation patterns for banks and commonly confused GCC tickers
_STRICT_STOCK_REGEXES: Dict[str, str] = {
    "ADCB": r"ابو\s*ظبي\s+التجاري|abu\s+dhabi\s+commercial|\badcb\b",
    "FAB": r"ابو\s*ظبي\s+الاول|first\s+abu\s+dhabi|\bfab\b",
    "ADIB": r"ابو\s*ظبي\s+الاسلامي|abu\s+dhabi\s+islamic|\badib\b",
    "DIB": r"دبي\s+الاسلامي|dubai\s+islamic|\bdib\b",
    "CBD": r"دبي\s+التجاري|commercial\s+bank\s+of\s+dubai|\bcbd\b",
    "ENBD": r"الامارات\s+دبي\s+الوطني|emirates\s+nbd|\benbd\b",
    "AJMANBANK": r"مصرف\s+عجمان|بنك\s+عجمان|ajman\s+bank|\bajmanbank\b",
    "BOS": r"بنك\s+الشارقه|bank\s+of\s+sharjah|\bbos\b",
    "DFM": r"شركه\s+سوق\s+دبي\s+المالي|سهم\s+سوق\s+دبي",
    "QNBK": r"(?:بنك\s+قطر\s+الوطني|مجموعه\s+qnb|qatar\s+national\s+bank|\bqnbk\b|\bqnb\b)",
    "QIBK": r"مصرف\s+قطر\s+الاسلامي|قطر\s+الاسلامي|qatar\s+islamic\s+bank|\bqibk\b|\bqib\b",
    "CBQK": r"البنك\s+التجاري\s+القطري|التجاري\s+القطري|commercial\s+bank\s+of\s+qatar|\bcbqk\b",
    "DHBK": r"بنك\s+الدوحه|doha\s+bank|\bdhbk\b",
    "DUBK": r"بنك\s+دخان|dukhan\s+bank|\bdubk\b",
    "MARK": r"(?:مصرف|بنك)\s+الريان|masraf\s+al\s+rayan|\bmark\b",
    "QIIK": r"قطر\s+الدولي\s+الاسلامي|الدولي\s+الاسلامي|qatar\s+international\s+islamic|\bqiik\b",
    "QFBQ": r"بنك\s+لشا|بنك\s+قطر\s+الاول|lesha\s+bank|\bqfbq\b",
    "ADNOCGAS": r"ادنوك\s+للغاز|adnoc\s+gas|\badnocgas\b",
    "ADNOCDIST": r"ادنوك\s+للتوزيع|adnoc\s+distribution|\badnocdist\b",
    "ADNOCLS": r"ادنوك\s+للامداد|adnoc\s+logistics|\badnocls\b",
    "ADNOCDRILL": r"ادنوك\s+للحفر|adnoc\s+drilling|\badnocdrill\b",
    "EMAAR": r"اعمار\s+العقاريه|سهم\s+اعمار|emaar\s+properties|\bemaar\b",
    "EMAARDEV": r"اعمار\s+للتطوير|emaar\s+development|\bemaardev\b",
    "ADPORTS": r"موانئ\s+ابو\s*ظبي|مجموعة\s+موانئ\s+ابو\s*ظبي|ad\s+ports|\badports\b",
    "ADNH": r"ابو\s*ظبي\s+الوطنيه\s+للفنادق|abu\s+dhabi\s+national\s+hotels|\badnh\b",
}

_EXTRA_NOISE_MARKERS: Tuple[str, ...] = (
    "جنيه", "مليار جنيه", "مليون جنيه", "البورصه المصريه", "الروسي", "روسيا",
    "وزير الداخليه", "التعاون الامني", "كره القدم", "مباراه", "الدوري", "دوري نجوم",
    "بدوري", "كاس امير", "كاس العالم", "المنتخب", "الشوط الاول", "الجوله",
    "مناقشات اسواق الامارات", "مصر للطيران",
)

_GENERIC_EN_WORDS = frozenset({
    "qatar", "qatari", "dubai", "abu", "dhabi", "emirates", "uae", "bank",
    "islamic", "national", "commercial", "group", "holding", "company",
    "properties", "real", "estate", "financial", "services", "investment",
    "investments", "insurance", "energy", "gas", "power", "water", "pjsc",
    "qpsc", "psc", "corp", "corporation", "industries", "industrial",
    "development", "international", "global", "general", "capital", "co",
    "limited", "ltd", "inc", "retail", "food", "foods", "transport",
})

_GENERIC_AR_WORDS = frozenset({
    "قطر", "القطريه", "القطري", "دبي", "ابوظبي", "ابو", "ظبي", "الامارات",
    "الاماراتيه", "بنك", "مصرف", "شركه", "مجموعه", "القابضه", "للاستثمار",
    "العقاريه", "للتطوير", "العقاري", "للتامين", "التكافلي", "الماليه",
    "للخدمات", "الوطنيه", "الوطني", "الدوليه", "الدولي", "العالميه",
    "العامه", "المتحده", "الخليج", "الاسلامي", "التجاري", "للطاقه",
    "للصناعات", "للبترول", "للاتصالات", "الغذائيه", "للنقل", "سوق", "المالي",
})


def clean_gcc_headline(title: str) -> str:
    cleaned = str(title or "").strip()
    cleaned = re.sub(r"\s*[-–|]\s*(?:ارقام|أرقام)\s*:.*$", "", cleaned).strip()
    return cleaned


def clean_gcc_source(source: str) -> str:
    s = str(source or "").strip()
    if "ارقام" in s or "أرقام" in s:
        return "أرقام"
    return s


def is_gcc_headline_for_stock(
    title: str,
    symbol: str,
    exchange: str,
    name_ar: str = "",
    name_en: str = "",
) -> bool:
    """Return True only when the headline explicitly refers to this GCC stock."""
    if not title:
        return False
    sym = symbol.strip().upper()
    ex = exchange.strip().upper()
    market = "qatar" if ex == "QSE" else "uae"

    if _is_foreign_market_headline(title, market):
        return False

    norm_title = _normalize_arabic(title)
    if any(noise in norm_title for noise in _EXTRA_NOISE_MARKERS):
        return False

    # Strict explicit regex for banks, ADNOC subsidiaries, DFM, etc.
    strict_pat = _STRICT_STOCK_REGEXES.get(sym)
    if strict_pat:
        if sym == "QNBK" and ("مصر" in norm_title or "egypt" in norm_title):
            return False
        if sym == "EMAAR" and "اعمار للتطوير" in norm_title and "اعمار العقاريه" not in norm_title:
            return False
        return bool(re.search(strict_pat, norm_title, re.IGNORECASE))

    # 1. Explicit ticker match (ignoring exchange prefix like "DFM:GFH")
    if len(sym) >= 3 and sym not in ("DFM", "ADX", "QSE", "UAE", "GAS"):
        if re.search(rf"\b{re.escape(sym)}\b(?!:)", title.upper()):
            return True

    # 2. Arabic company name matching
    clean_ar = re.sub(r"\s*\([^)]*\)", "", str(name_ar or "")).strip()
    norm_ar = _normalize_arabic(clean_ar)
    if norm_ar:
        ar_words = [w for w in norm_ar.split() if len(w) >= 2]
        if len(ar_words) == 1:
            word = ar_words[0]
            if word in _AMBIGUOUS_SINGLE_WORD_ALIASES or word in _GENERIC_AR_WORDS:
                context_phrases = (
                    f"شركه {word}",
                    f"سهم {word}",
                    f"مجموعه {word}",
                    f'"{word}"',
                    f"«{word}»",
                    f"{word} القطريه",
                    f"{word} العقاريه",
                    f"{word} القابضه",
                )
                if any(p in norm_title or p in title for p in context_phrases):
                    return True
            elif len(word) >= 4 and word in norm_title:
                return True
        else:
            # Multi-word Arabic name: full name OR distinctive non-generic 2-word phrase / unique brand word
            if len(norm_ar) >= 6 and norm_ar in norm_title:
                return True
            distinctive_ar = [w for w in ar_words if len(w) >= 4 and w not in _GENERIC_AR_WORDS]
            if len(distinctive_ar) >= 2:
                phrase2 = f"{distinctive_ar[0]} {distinctive_ar[1]}"
                if phrase2 in norm_title:
                    return True
            if len(distinctive_ar) == 1 and len(distinctive_ar[0]) >= 5:
                tok = distinctive_ar[0]
                if tok not in _AMBIGUOUS_SINGLE_WORD_ALIASES and tok in norm_title:
                    return True

    # 3. English company name matching
    clean_en = re.sub(r"\s*\([^)]*\)", "", str(name_en or "")).strip()
    en_lower = re.sub(r"[^a-z0-9\s&'-]", " ", clean_en.lower())
    en_words = [w for w in en_lower.split() if len(w) >= 2]
    distinctive_en = [w for w in en_words if len(w) >= 4 and w not in _GENERIC_EN_WORDS]
    if len(clean_en) >= 5 and re.search(rf"\b{re.escape(clean_en.lower())}\b", norm_title):
        return True
    if len(distinctive_en) >= 2:
        phrase_en = f"{distinctive_en[0]} {distinctive_en[1]}"
        if re.search(rf"\b{re.escape(phrase_en)}\b", norm_title):
            return True
    elif len(distinctive_en) == 1 and len(distinctive_en[0]) >= 5:
        if re.search(rf"\b{re.escape(distinctive_en[0])}\b", norm_title):
            return True

    return False


def _order_priority_stocks(stocks: List[Dict[str, Any]], market: str, max_symbols: int) -> List[Dict[str, Any]]:
    uae_rank = {s: i for i, s in enumerate(PRIORITY_UAE_SYMBOLS)}
    qse_rank = {s: i for i, s in enumerate(PRIORITY_QATAR_SYMBOLS)}

    uae_stocks = [s for s in stocks if str(s.get("exchange") or "").upper() in ("DFM", "ADX")]
    qse_stocks = [s for s in stocks if str(s.get("exchange") or "").upper() == "QSE"]

    uae_stocks.sort(key=lambda s: (uae_rank.get(str(s.get("symbol") or "").upper(), 9999), str(s.get("symbol") or "")))
    qse_stocks.sort(key=lambda s: (qse_rank.get(str(s.get("symbol") or "").upper(), 9999), str(s.get("symbol") or "")))

    if market == "uae":
        return uae_stocks[:max_symbols]
    if market == "qatar":
        return qse_stocks[:max_symbols]

    # Balanced selection when syncing both UAE & Qatar together
    half_qse = max(1, min(len(qse_stocks), max_symbols // 2))
    half_uae = max(1, min(len(uae_stocks), max_symbols - half_qse))
    return uae_stocks[:half_uae] + qse_stocks[:half_qse]


def sync_gcc_market_news(
    market: str = "all",
    max_symbols: int = 50,
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
        .limit(300)
        .execute()
    )
    all_stocks = getattr(stocks_res, "data", None) or []
    if not all_stocks:
        return {"ok": True, "market": market, "synced_rows": 0, "reason": "no_stocks"}

    stocks = _order_priority_stocks(all_stocks, market, max_symbols)
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
        clean_ar = re.sub(r"\s*\([^)]*\)", "", name_ar).strip()
        clean_en = re.sub(r"\s*\([^)]*\)", "", name_en).strip()

        queries: List[Tuple[str, str, str]] = []
        if clean_ar:
            queries.append((f'"{clean_ar}" {suffix_ar}', "ar", ceid_ar))
        if clean_en:
            queries.append((f'"{clean_en}" {ex} stock', "en", ceid_en))
        if not queries:
            queries.append((f"{sym} {ex} stock", "en", ceid_en))

        seen_titles: set[str] = set()
        collected: List[Dict[str, str]] = []
        for q, hl, ceid in queries[:2]:
            for item in _fetch_rss_items(q, hl=hl, gl=gl, ceid=ceid, days_back=days_back):
                title = clean_gcc_headline(item["title"])
                if not is_gcc_headline_for_stock(title, sym, ex, name_ar=name_ar, name_en=name_en):
                    continue
                tkey = title.lower()
                if tkey not in seen_titles:
                    seen_titles.add(tkey)
                    collected.append({
                        **item,
                        "title": title,
                        "source": clean_gcc_source(item.get("source") or ""),
                    })

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
                "sources": list(dict.fromkeys(clean_gcc_source(s) for s in sent["sources"] if s))[:5],
            }
            if not dry_run:
                sb.table("stock_news_sentiment").upsert(payload, on_conflict="symbol,date").execute()
            synced_rows += 1

        time.sleep(0.12)

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
    parser.add_argument("--max-symbols", type=int, default=50)
    parser.add_argument("--days", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(sync_gcc_market_news(market=args.market, max_symbols=args.max_symbols, days_back=args.days, dry_run=args.dry_run))
