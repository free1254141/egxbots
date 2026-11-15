"""
api/saudi_disclosures_sync.py — Saudi Market (TASI / Tadawul) Disclosures & Announcements Sync.
Fetches Saudi corporate announcements (توزيعات الأرباح، النتائج المالية، العقود،
تغيرات كبار الملاك، زيادة/خفض رأس المال) via Google News SA RSS, matches each
to its 4-digit Tadawul symbol, generates a concise Arabic AI summary (DeepSeek
with deterministic fallback), and upserts into SAUDI_SUPABASE.egx_disclosures.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import json
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from supabase import Client, create_client

from api.saudi_stock_aliases import SAUDI_STOCK_NAMES_AR

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}

DISCLOSURE_QUERIES: List[str] = [
    '"تداول السعودية" (توزيع أرباح OR نتائج مالية OR عقد OR استحواذ)',
    '"تعلن شركة" "تداول" (أرباح OR خسائر OR توزيعات OR مشروع OR عقد)',
    '"مجلس إدارة" "تداول" (توصية OR توزيع أرباح OR زيادة رأس مال OR خفض رأس مال)',
    '"تغيرات كبار الملاك" تداول السعودية',
    '"تاسي" إعلان (أرباح ربعية OR نتائج سنوية OR توزيع نقدي OR ترسية عقد)',
    '"أرامكو السعودية" OR "مصرف الراجحي" OR "سابك" OR "أكوا باور" (نتائج OR أرباح OR توزيعات OR عقد)',
    '"البنك الأهلي السعودي" OR "إس تي سي" OR "معادن" OR "المراعي" (نتائج OR أرباح OR توزيعات OR عقد)',
]


def _load_env_and_client() -> Tuple[Client, str]:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(repo_root, "web", ".env.local"))
    load_dotenv(os.path.join(repo_root, ".env"))
    url = (os.getenv("SAUDI_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_URL") or "").strip()
    key = (os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("Missing SAUDI_SUPABASE_URL / SAUDI_SUPABASE_SERVICE_ROLE_KEY")
    ds_key = (os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_OFFICIAL_API_KEY") or "").strip()
    return create_client(url, key), ds_key


def _normalize_ar(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    return text.lower().strip()


def _build_stock_matcher(sb: Client) -> List[Tuple[str, str, List[str]]]:
    res = sb.table("stocks").select("symbol,name,name_ar").eq("exchange", "TADAWUL").execute()
    entries: List[Tuple[str, str, List[str]]] = []
    for row in res.data or []:
        sym = str(row.get("symbol") or "").strip().split(".")[0]
        if not sym:
            continue
        display_name = SAUDI_STOCK_NAMES_AR.get(sym) or str(row.get("name_ar") or row.get("name") or sym).strip()
        aliases: List[str] = []
        for candidate in [display_name, row.get("name_ar"), row.get("name")]:
            if not candidate:
                continue
            for part in re.split(r"[,،|/()]", str(candidate)):
                clean = _normalize_ar(part)
                if len(clean) >= 3 and clean not in {"شركه", "الشركه", "السعوديه", "القابضه", "مجموعه", "للاستثمار", "التجاريه", "الصناعيه"}:
                    aliases.append(clean)
        # Prioritize longer / more specific aliases first
        aliases = sorted(set(aliases), key=len, reverse=True)
        entries.append((sym, display_name, aliases))
    return entries


def _match_symbol(title: str, matcher: List[Tuple[str, str, List[str]]]) -> Tuple[Optional[str], str]:
    # 1. Exact 4-digit Tadawul code in title
    m_code = re.search(r"\b([1-8]\d{3})\b", title)
    if m_code:
        code = m_code.group(1)
        for sym, disp, _ in matcher:
            if sym == code:
                return sym, disp

    # 2. Best Arabic/English company name match
    norm_title = _normalize_ar(title)
    for sym, disp, aliases in matcher:
        for alias in aliases:
            if len(alias) >= 4 and alias in norm_title:
                return sym, disp

    return None, "السوق السعودي (تداول)"


def _classify_disclosure(title: str) -> Tuple[str, str, str, str]:
    """Returns (disclosure_type, sentiment, action_type, ai_summary)."""
    t = _normalize_ar(title)

    # Type
    if any(k in t for k in ["كبار الملاك", "تملك", "حصة", "حصه", "ملاك", "تنفيذي", "داخلي"]):
        d_type = "shareholding_change"
    elif any(k in t for k in ["توزيع", "ارباح نقديه", "كوبون", "احقيه"]):
        d_type = "dividend"
    elif any(k in t for k in ["نتائج", "ربح", "خساره", "خسائر", "ايرادات", "ربع", "السنويه"]):
        d_type = "earnings"
    elif any(k in t for k in ["راس مال", "زيادة راس", "خفض راس", "اسهم منحه", "اكتتاب"]):
        d_type = "capital_change"
    elif any(k in t for k in ["مجلس الاداره", "جمعيه", "عموميه", "توصيه"]):
        d_type = "board_decision"
    else:
        d_type = "material_event"

    # Sentiment & action
    bull_words = ["ارتفاع", "نمو", "قفزه", "توزيع", "عقد", "ترسيه", "فوز", "استحواذ", "ارباح", "ربح", "منحه", "ايجابي"]
    bear_words = ["خساره", "خسائر", "انخفاض", "تراجع", "هبوط", "خفض راس", "ايقاف", "تعليق", "تسييل", "بيع"]
    bull_hits = sum(1 for w in bull_words if w in t)
    bear_hits = sum(1 for w in bear_words if w in t)

    if bull_hits > bear_hits:
        sentiment = "bullish"
        action_type = "buy" if d_type in ("shareholding_change", "dividend") else "general"
    elif bear_hits > bull_hits:
        sentiment = "bearish"
        action_type = "sell" if d_type == "shareholding_change" else "general"
    else:
        sentiment = "neutral"
        action_type = "general"

    type_labels = {
        "shareholding_change": "تغيّر في ملكية كبار المساهمين",
        "dividend": "إعلان توزيعات أرباح نقدية / منحة",
        "earnings": "إعلان نتائج مالية",
        "capital_change": "إعلان بشأن تعديل رأس المال",
        "board_decision": "قرار مجلس إدارة / جمعية عمومية",
        "material_event": "إفصاح جوهري في تداول السعودية",
    }
    sent_label = "إيجابي" if sentiment == "bullish" else ("سلبي يستدعي الحذر" if sentiment == "bearish" else "محايد للمتابعة")
    summary = f"{type_labels.get(d_type, 'إعلان تداول')}: {title}. الأثر المبدئي يُصنف كـ {sent_label} ويُستحسن مراجعة تفاصيل الإعلان الكاملة على تداول."
    return d_type, sentiment, action_type, summary


def _enrich_with_deepseek(items: List[Dict[str, Any]], ds_key: str) -> None:
    if not ds_key or not items:
        return
    try:
        batch = [{"idx": i, "title": it["title"], "company": it["company_name"]} for i, it in enumerate(items[:20])]
        prompt = (
            "أنت محلل مالي للسوق السعودي (تداول تاسي). لكل إعلان في القائمة التالية اكتب ملخصاً احترافياً "
            "من جملتين باللغة العربية وحدد sentiment (bullish أو bearish أو neutral). "
            "أرجع JSON array فقط بصيغة [{\"idx\": 0, \"ai_summary\": \"...\", \"sentiment\": \"...\"}].\n"
            + json.dumps(batch, ensure_ascii=False)
        )
        r = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {ds_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 1800,
            },
            timeout=25,
        )
        if r.status_code != 200:
            return
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\[.*\]", content, re.DOTALL)
        if not m:
            return
        parsed = json.loads(m.group(0))
        for entry in parsed:
            idx = entry.get("idx")
            if isinstance(idx, int) and 0 <= idx < len(items):
                if entry.get("ai_summary"):
                    items[idx]["ai_summary"] = str(entry["ai_summary"]).strip()
                if entry.get("sentiment") in ("bullish", "bearish", "neutral"):
                    items[idx]["sentiment"] = entry["sentiment"]
    except Exception:
        pass


def run_saudi_disclosures_sync(days_back: int = 30) -> Dict[str, Any]:
    sb, ds_key = _load_env_and_client()
    matcher = _build_stock_matcher(sb)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_back)

    seen_urls = set()
    seen_titles = set()
    rows: List[Dict[str, Any]] = []

    for query in DISCLOSURE_QUERIES:
        encoded = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}+when:{days_back}d&hl=ar&gl=SA&ceid=SA:ar"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=12)
            if resp.status_code != 200 or "<item>" not in resp.text:
                continue
            root = ET.fromstring(resp.text)
        except Exception:
            continue

        for item in root.findall("./channel/item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            source_el = item.find("source")
            if title_el is None or not title_el.text or link_el is None or not link_el.text:
                continue

            raw_title = title_el.text.strip()
            source_name = source_el.text.strip() if source_el is not None and source_el.text else "تداول / أخبار"
            if " - " in raw_title and source_name:
                raw_title = raw_title.rsplit(" - ", 1)[0].strip()
            link = link_el.text.strip()

            if link in seen_urls or raw_title in seen_titles:
                continue

            pub_date = dt.date.today().isoformat()
            if pub_el is not None and pub_el.text:
                try:
                    pdt = email.utils.parsedate_to_datetime(pub_el.text.strip())
                    if pdt.tzinfo is None:
                        pdt = pdt.replace(tzinfo=dt.timezone.utc)
                    if pdt < cutoff:
                        continue
                    pub_date = pdt.date().isoformat()
                except Exception:
                    pass

            sym, company_name = _match_symbol(raw_title, matcher)
            d_type, sentiment, action_type, ai_summary = _classify_disclosure(raw_title)

            seen_urls.add(link)
            seen_titles.add(raw_title)
            rows.append({
                "symbol": sym,
                "company_name": company_name,
                "disclosure_type": d_type,
                "disclosure_date": pub_date,
                "title": raw_title,
                "raw_content": raw_title,
                "ai_summary": ai_summary,
                "sentiment": sentiment,
                "action_type": action_type,
                "shares_count": None,
                "stake_before": None,
                "stake_after": None,
                "party_name": "الشركة / كبار المساهمين",
                "party_role": source_name,
                "source_url": link,
                "metadata": {"exchange": "TADAWUL", "source": source_name},
            })

        time.sleep(0.2)

    # Sort newest first and enrich top announcements via DeepSeek
    rows.sort(key=lambda r: r["disclosure_date"], reverse=True)
    _enrich_with_deepseek(rows[:20], ds_key)

    existing_res = sb.table("egx_disclosures").select("source_url").limit(1000).execute()
    existing_urls = {r.get("source_url") for r in (existing_res.data or []) if r.get("source_url")}
    new_rows = [r for r in rows if r.get("source_url") not in existing_urls]
    saved = 0
    for i in range(0, len(new_rows), 25):
        chunk = new_rows[i:i + 25]
        sb.table("egx_disclosures").insert(chunk).execute()
        saved += len(chunk)

    return {"ok": True, "fetched": len(rows), "saved": saved}


if __name__ == "__main__":
    print(run_saudi_disclosures_sync(days_back=30))
