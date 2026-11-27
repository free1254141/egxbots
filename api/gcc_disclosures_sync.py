"""
api/gcc_disclosures_sync.py — UAE (DFM & ADX) & Qatar (QSE) Disclosures Sync.

Fetches Arabic & English corporate disclosure news (earnings, dividends, board
decisions, insider/major-shareholder moves, capital actions) via Google News RSS
(gl=AE for UAE, gl=QA for Qatar), matches each item to its DFM/ADX/QSE symbol,
generates an Arabic AI summary (DeepSeek with deterministic fallback), and
inserts into SAUDI_SUPABASE.egx_disclosures tagged with metadata.exchange.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import requests

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from api.saudi_disclosures_sync import (
    _HEADERS,
    _classify_disclosure,
    _clean_saudi_title,
    _enrich_with_deepseek,
    _is_duplicate_saudi_event,
    _load_env_and_client,
    _normalize_ar,
)

_MARKET_CONFIG: Dict[str, Dict[str, Any]] = {
    "uae": {
        "exchanges": ["DFM", "ADX"],
        "gl": "AE",
        "ceid_ar": "AE:ar",
        "ceid_en": "AE:en",
        "default_source": "سوق دبي / أبوظبي",
        "queries_ar": [
            '"سوق دبي المالي" إفصاح OR أرباح OR توزيعات OR استحواذ',
            '"سوق أبوظبي" إفصاح OR أرباح OR توزيعات OR استحواذ',
            'سهم "إعمار" OR "الدار" OR "أدنوك" OR "العالمية القابضة" أرباح OR توزيعات',
            'سهم "دبي الإسلامي" OR "أبوظبي الأول" OR "ديوا" OR "سالك" نتائج OR إفصاح',
            'سهم "طاقة" OR "اتصالات" OR "موانئ دبي" OR "أبوظبي التجاري" أرباح OR مجلس إدارة',
        ],
        "queries_en": [
            '"Dubai Financial Market" OR "DFM" dividend OR earnings OR disclosure',
            '"Abu Dhabi Securities Exchange" OR "ADX" dividend OR earnings OR disclosure',
        ],
    },
    "qatar": {
        "exchanges": ["QSE"],
        "gl": "QA",
        "ceid_ar": "QA:ar",
        "ceid_en": "QA:en",
        "default_source": "بورصة قطر",
        "queries_ar": [
            '"بورصة قطر" إفصاح OR أرباح OR توزيعات OR مجلس إدارة',
            '"بورصة قطر" نتائج OR عقد OR جمعية OR استحواذ OR صفقة',
            'سهم "قطر الوطني" OR "صناعات قطر" OR "ناقلات" أرباح OR توزيعات OR إفصاح',
            'سهم "مصرف قطر الإسلامي" OR "مصرف الريان" OR "أوريدو" OR "مسيعيد" نتائج OR إفصاح',
            'سهم "بروة" OR "قطر للوقود" OR "الملاحة القطرية" OR "بنك الدوحة" أرباح OR توزيعات',
            'سهم "التجاري" OR "الدولي الإسلامي" OR "دخان" OR "فودافون قطر" OR "الخليج الدولية" نتائج OR إفصاح',
        ],
        "queries_en": [
            '"Qatar Stock Exchange" OR "QSE" dividend OR earnings OR disclosure OR profit OR AGM',
            '"QNB" OR "Qatar Islamic Bank" OR "Industries Qatar" OR "Ooredoo" OR "Nakilat" profit OR dividend OR disclosure',
        ],
    },
}


def _build_gcc_matcher(sb, exchanges: List[str]) -> List[Tuple[str, str, str, List[str]]]:
    """Return [(symbol, exchange, display_name, aliases)] for DFM/ADX/QSE stocks."""
    res = (
        sb.table("stocks")
        .select("symbol,exchange,name,name_ar")
        .in_("exchange", exchanges)
        .eq("is_active", True)
        .limit(500)
        .execute()
    )
    matcher: List[Tuple[str, str, str, List[str]]] = []
    for row in getattr(res, "data", None) or []:
        sym = str(row.get("symbol") or "").strip().upper()
        ex = str(row.get("exchange") or "").strip().upper()
        if not sym or not ex:
            continue
        name_ar = str(row.get("name_ar") or "").strip()
        name_en = str(row.get("name") or "").strip()
        aliases: List[str] = []
        for raw in (name_ar, name_en):
            norm = _normalize_ar(raw)
            if len(norm) >= 4:
                aliases.append(norm)
            tokens = [t for t in norm.split() if len(t) >= 4 and t not in ("شركة", "بنك", "مصرف", "مجموعة", "القابضة", "corp", "group", "bank", "company")]
            if len(tokens) >= 2:
                aliases.append(" ".join(tokens[:2]))
        matcher.append((sym, ex, name_ar or name_en or sym, list(dict.fromkeys(aliases))))
    return matcher


_AMBIGUOUS_SINGLE_WORD_ALIASES = frozenset(
    _normalize_ar(w) for w in ("أعمال", "ناقلات", "وقود", "ميزة", "سالك", "تبريد", "الدار")
)

_FOREIGN_MARKET_MARKERS: Dict[str, Tuple[str, ...]] = {
    "qatar": (
        "السعودية",
        "سعودية",
        "الشركات السعودية",
        "تاسي",
        "تداول السعودية",
        "جنيه",
        "بورصة مصر",
        "البورصة المصرية",
        "هشام عز العرب",
        "البنك التجاري الدولي",
        "الكويت",
        "جزائرية",
        "شيفرون",
        "بورصة فلسطين",
    ),
    "uae": (
        "السعودية",
        "سعودية",
        "الشركات السعودية",
        "تاسي",
        "جنيه",
        "بورصة مصر",
        "البورصة المصرية",
        "هشام عز العرب",
        "بنك أبوظبي الأول مصر",
        "جزائرية",
    ),
}

_EGYPT_WORD_BOUNDARY_RE = re.compile(
    r"(?<![a-z0-9\u0621-\u064a])(?:و?ب?مصر|المصري(?:ه|ون|ين)?|مصري(?:ه|ون|ين)?)(?![a-z0-9\u0621-\u064a])",
    re.IGNORECASE,
)

_JUNK_TITLE_PATTERNS = re.compile(
    r"(stock\s+price|share\s+price|price\s+today|stock\s+quote|share\s+quote|price\s+forecast|stock\s+analysis|"
    r"سعر\s+سهم|اخبار\s+سهم|توقعات\s+سهم|تحليل\s+سهم|معلومات\s+مباشر|"
    r"التحليل\s+الفني\s+لسهم|تحليل\s+فني\s+لسهم|لماذا\s+(?:تراجع|ارتفع|استقر|هبط)\s+سهم)",
    re.IGNORECASE,
)

_DISCLOSURE_SIGNAL_KEYWORDS = (
    "أرباح", "ارباح", "خسائر", "خساره", "ايرادات", "إيرادات", "توزيع", "توزيعات", "كوبون",
    "افصاح", "إفصاح", "مجلس", "عموميه", "عمومية", "جمعيه", "جمعية", "استحواذ", "اندماج",
    "عقد", "صفقه", "صفقة", "ترسيه", "ترسية", "مشروع", "صكوك", "سندات", "راس مال", "رأس مال",
    "نتائج", "الربع", "النصف", "تراجع", "نمو", "ارتفاع", "قفز", "يصادق", "يقر", "توافق", "يوافق",
    "شراء اسهم", "خزينه", "خزينة", "زياده", "زيادة", "تخفيض", "اعلان", "إعلان", "اتفاقيه", "اتفاقية",
    "profit", "loss", "earnings", "revenue", "dividend", "distribution", "board", "agm", "egm",
    "merger", "acquisition", "contract", "award", "deal", "sukuk", "bond", "capital", "results",
    "q1", "q2", "q3", "q4", "fy", "quarter", "nine-month", "9-month", "half-year", "disclosure",
    "stake", "buyback", "listing", "approval", "rise", "rises", "surge", "drop", "falls", "decline",
)


def _is_junk_disclosure_title(title: str) -> bool:
    """Reject quote/stock-profile pages and non-disclosure headlines lacking event keywords."""
    clean = (title or "").strip()
    if len(clean) < 12:
        return True
    norm = _normalize_ar(clean)
    if _JUNK_TITLE_PATTERNS.search(norm) or _JUNK_TITLE_PATTERNS.search(clean):
        return True
    lower = clean.lower()
    return not any((kw in norm or kw in lower) for kw in _DISCLOSURE_SIGNAL_KEYWORDS)


def _is_foreign_market_headline(title: str, market: str) -> bool:
    markers = _FOREIGN_MARKET_MARKERS.get(market, ())
    if not markers:
        return False
    norm_title = _normalize_ar(title)
    if market in ("qatar", "uae") and _EGYPT_WORD_BOUNDARY_RE.search(norm_title):
        return True
    return any(_normalize_ar(m) in norm_title for m in markers)


def _match_gcc_symbol(
    title: str, matcher: List[Tuple[str, str, str, List[str]]], default_exchange: str
) -> Tuple[Optional[str], str, str]:
    upper = title.upper()
    norm_title = _normalize_ar(title)

    # 1. Explicit ticker match for >= 3-char tickers (ignore exchange prefix like "DFM:GFH")
    for sym, ex, name, _ in matcher:
        if sym == "DFM":
            if "سهم سوق دبي" in title or "شركة سوق دبي المالي" in title:
                return sym, ex, name
            continue
        if len(sym) >= 3 and re.search(rf"\b{re.escape(sym)}\b(?!:)", upper):
            return sym, ex, name

    # 2. Longest company-name alias match (with strict context for DFM & generic single words)
    best_match: Optional[Tuple[int, str, str, str]] = None
    for sym, ex, name, aliases in matcher:
        if sym == "DFM":
            continue
        for alias in aliases:
            if len(alias) < 4 or alias not in norm_title:
                continue
            if alias in _AMBIGUOUS_SINGLE_WORD_ALIASES:
                context_phrases = (
                    f"شركه {alias}",
                    f"سهم {alias}",
                    f"مجموعه {alias}",
                    f"{alias} القطريه",
                    f"{alias} العقاريه",
                )
                if not any(phrase in norm_title for phrase in context_phrases):
                    continue
            elif len(alias) < 5:
                continue
            score = len(alias)
            if best_match is None or score > best_match[0]:
                best_match = (score, sym, ex, name)
    if best_match:
        return best_match[1], best_match[2], best_match[3]

    return None, default_exchange, ""


def _fetch_rss(query: str, hl: str, gl: str, ceid: str, days_back: int) -> List[Dict[str, str]]:
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}+when:{days_back}d&hl={hl}&gl={gl}&ceid={ceid}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        if resp.status_code != 200 or not resp.text:
            return []
        root = ET.fromstring(resp.text)
    except Exception:
        return []

    out: List[Dict[str, str]] = []
    for item in root.findall(".//item"):
        raw_title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source_name = source_el.text.strip() if source_el is not None and source_el.text else ""
        if raw_title and link:
            out.append({
                "title": _clean_saudi_title(raw_title, source_name),
                "link": link,
                "pub_date": pub_date,
                "source": source_name,
            })
    return out


def sync_gcc_market_disclosures(
    market: str, days_back: int = 30, dry_run: bool = False
) -> Dict[str, Any]:
    cfg = _MARKET_CONFIG.get(market)
    if not cfg:
        raise ValueError(f"Unsupported GCC disclosures market: {market}")

    sb, ds_key = _load_env_and_client()
    exchanges = cfg["exchanges"]
    matcher = _build_gcc_matcher(sb, exchanges)
    if not matcher:
        return {"ok": True, "market": market, "inserted": 0, "reason": "no_stocks"}

    seen_urls: set[str] = set()
    candidates: List[Dict[str, Any]] = []

    rss_jobs = [(q, "ar", cfg["gl"], cfg["ceid_ar"]) for q in cfg["queries_ar"]] + [
        (q, "en", cfg["gl"], cfg["ceid_en"]) for q in cfg["queries_en"]
    ]
    for query, hl, gl, ceid in rss_jobs:
        for item in _fetch_rss(query, hl, gl, ceid, days_back):
            link = item["link"]
            if link in seen_urls:
                continue
            seen_urls.add(link)

            if _is_foreign_market_headline(item["title"], market) or _is_junk_disclosure_title(item["title"]):
                continue

            sym, ex, company_name = _match_gcc_symbol(item["title"], matcher, exchanges[0])
            if not sym:
                continue

            try:
                dt = parsedate_to_datetime(item["pub_date"]).astimezone(timezone.utc)
                disc_date = dt.strftime("%Y-%m-%d")
            except Exception:
                disc_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            d_type, sentiment, impact, action = _classify_disclosure(item["title"])
            raw_source = (item["source"] or "").strip()
            source_name = "أرقام" if ("ارقام" in raw_source or "أرقام" in raw_source) else (raw_source or cfg["default_source"])
            candidates.append({
                "symbol": sym,
                "company_name": company_name,
                "disclosure_type": d_type,
                "disclosure_date": disc_date,
                "title": item["title"][:280],
                "ai_summary": f"{company_name}: {item['title'][:200]}",
                "sentiment": sentiment,
                "action_type": action,
                "party_name": source_name,
                "party_role": source_name,
                "source_url": link,
                "metadata": {"exchange": ex, "market": market, "source": source_name, "impact_level": impact},
            })

    if not candidates:
        return {"ok": True, "market": market, "fetched": 0, "inserted": 0}

    candidates.sort(key=lambda x: x["disclosure_date"], reverse=True)
    ex_rows = (
        sb.table("egx_disclosures")
        .select("id, symbol, disclosure_type, disclosure_date, title, sentiment, source_url")
        .order("disclosure_date", desc=True)
        .limit(400)
        .execute()
        .data
        or []
    )

    to_insert: List[Dict[str, Any]] = []
    for cand in candidates:
        if _is_duplicate_saudi_event(cand, ex_rows):
            continue
        if _is_duplicate_saudi_event(cand, to_insert):
            continue
        to_insert.append(cand)
        if len(to_insert) >= 25:
            break

    if to_insert and not dry_run:
        _enrich_with_deepseek(to_insert, ds_key)
        for i in range(0, len(to_insert), 15):
            sb.table("egx_disclosures").insert(to_insert[i : i + 15]).execute()

    return {
        "ok": True,
        "market": market,
        "dry_run": dry_run,
        "candidates": len(candidates),
        "inserted": 0 if dry_run else len(to_insert),
        "would_insert": len(to_insert),
    }


def run_gcc_disclosures_sync(
    market: str = "all", days_back: int = 30, dry_run: bool = False
) -> Dict[str, Any]:
    targets = ["uae", "qatar"] if market == "all" else [market]
    results = {m: sync_gcc_market_disclosures(m, days_back=days_back, dry_run=dry_run) for m in targets}
    return {"ok": True, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync UAE & Qatar Disclosures")
    parser.add_argument("--market", choices=["all", "uae", "qatar"], default="all")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(run_gcc_disclosures_sync(market=args.market, days_back=args.days, dry_run=args.dry_run))
