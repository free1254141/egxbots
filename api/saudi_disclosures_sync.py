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

from api.saudi_stock_aliases import (
    SAUDI_STOCK_NAMES_AR,
    extract_all_saudi_symbols,
    resolve_saudi_symbol,
)

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


def _clean_saudi_title(raw_title: str, source_name: str = "") -> str:
    title = (raw_title or "").strip()
    if " - " in title:
        left, right = title.rsplit(" - ", 1)
        if source_name or any(k in right for k in ("ارقام", "أرقام", "معلومات", "تداول", "مباشر", "العربية")):
            title = left.strip()
    title = re.sub(r"\s*-\s*ارقام\s*:.*$", "", title).strip()
    title = re.sub(r"\s*بواسطة\s+المتداول.*$", "", title).strip()
    return title


def _match_symbol(title: str, matcher: List[Tuple[str, str, List[str]]]) -> Tuple[Optional[str], str]:
    matcher_names = {sym: disp for sym, disp, _ in matcher}

    # 1. Exact 4-digit Tadawul code in title
    m_code = re.search(r"\b([1-8]\d{3})\b", title)
    if m_code:
        code = m_code.group(1)
        if code in matcher_names:
            return code, matcher_names[code]
        if code in SAUDI_STOCK_NAMES_AR:
            return code, SAUDI_STOCK_NAMES_AR[code]

    # 2. Position-ordered word-boundary alias extraction (earliest company in headline wins)
    extracted = extract_all_saudi_symbols(title)
    if extracted:
        sym = extracted[0]
        return sym, matcher_names.get(sym) or SAUDI_STOCK_NAMES_AR.get(sym, sym)

    resolved = resolve_saudi_symbol(title)
    if resolved:
        return resolved, matcher_names.get(resolved) or SAUDI_STOCK_NAMES_AR.get(resolved, resolved)

    # 3. Fallback: DB company aliases scored by earliest position, longest alias on ties
    norm_title = _normalize_ar(title)
    best_match: Optional[Tuple[int, int, str, str]] = None
    for sym, disp, aliases in matcher:
        for alias in aliases:
            if len(alias) < 4:
                continue
            pos = norm_title.find(alias)
            if pos != -1:
                cand = (pos, -len(alias), sym, disp)
                if best_match is None or cand < best_match:
                    best_match = cand

    if best_match is not None:
        return best_match[2], best_match[3]

    return None, "السوق السعودي (تداول)"


_EXPLICIT_BEAR_PHRASES = (
    "تراجع ارباح", "انخفاض ارباح", "هبوط ارباح", "تراجع صافي", "انخفاض صافي",
    "هبوط صافي", "تراجعت", "انخفضت", "يهبط", "خسائر", "خساره", "تراجع ", "انخفاض ",
    "تهبط ", "تنخفض ", "تخفض ارباح",
)


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

    # Sentiment & action: check explicit earnings-drop / loss phrases BEFORE generic bullish words like "ارباح"
    explicit_bear_phrases = list(_EXPLICIT_BEAR_PHRASES)
    explicit_bull_phrases = [
        "ارتفاع ارباح", "نمو ارباح", "قفزه", "تقفز", "تتجاوز التوقعات", "توزيع ارباح",
        "توزيعات نقديه", "ترسيه", "توقيع عقد", "توقع عقد", "موافقه على زياده راس المال",
    ]
    bull_words = ["ارتفاع", "نمو", "قفزه", "توزيع", "عقد", "ترسيه", "فوز", "استحواذ", "منحه", "ايجابي"]
    bear_words = ["خساره", "خسائر", "انخفاض", "تراجع", "هبوط", "خفض راس", "ايقاف", "تعليق", "تسييل", "بيع", "ضغوط"]

    has_explicit_bear = any(p in t for p in explicit_bear_phrases)
    has_explicit_bull = any(p in t for p in explicit_bull_phrases)

    if has_explicit_bear and not any(k in t for k in ["تتجاوز التوقعات", "توزيع"]):
        sentiment = "bearish"
    elif has_explicit_bull and not has_explicit_bear:
        sentiment = "bullish"
    else:
        bull_hits = sum(1 for w in bull_words if w in t)
        bear_hits = sum(1 for w in bear_words if w in t)
        if bull_hits > bear_hits:
            sentiment = "bullish"
        elif bear_hits > bull_hits:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

    if d_type == "shareholding_change" and sentiment == "bullish":
        action_type = "buy"
    elif d_type == "shareholding_change" and sentiment == "bearish":
        action_type = "sell"
    else:
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


_SAUDI_TITLE_STOPWORDS = {
    "في", "عن", "من", "الي", "على", "خلال", "بقيمه", "نسبه", "بنسبه", "الربع",
    "الاول", "الثاني", "الثالث", "الرابع", "عام", "السعوديه", "شركه", "تعلن",
    "ريال", "دولار", "مليون", "مليار", "تداول", "الاسهم", "السعودي",
}


def _extract_event_features(title: str) -> Tuple[str, set, set]:
    norm = _normalize_ar(title)
    clean = re.sub(r"[^\w\s\u0600-\u06FF.]", " ", norm)
    tokens = {
        tok for tok in clean.split()
        if len(tok) >= 2 and tok not in _SAUDI_TITLE_STOPWORDS and not tok.isdigit()
    }
    nums = {
        n for n in re.findall(r"\d+(?:\.\d+)?", norm)
        if n not in {"1", "2", "3", "4", "9", "2024", "2025", "2026", "2027"}
    }
    compact = " ".join(clean.split())
    return compact, tokens, nums


def _is_duplicate_saudi_event(candidate: Dict[str, Any], existing_rows: List[Dict[str, Any]]) -> bool:
    cand_url = (candidate.get("source_url") or "").strip()
    cand_sym = (candidate.get("symbol") or "").strip().upper()
    cand_type = (candidate.get("disclosure_type") or "").strip().lower()
    cand_sent = (candidate.get("sentiment") or "").strip().lower()
    cand_date_s = (candidate.get("disclosure_date") or "")[:10]
    cand_compact, cand_tokens, cand_nums = _extract_event_features(candidate.get("title") or "")

    try:
        cand_dt = dt.date.fromisoformat(cand_date_s) if cand_date_s else None
    except ValueError:
        cand_dt = None

    for ex in existing_rows:
        ex_url = (ex.get("source_url") or "").strip()
        if cand_url and ex_url and cand_url == ex_url:
            return True

        ex_sym = (ex.get("symbol") or "").strip().upper()
        if not cand_sym or cand_sym != ex_sym:
            continue

        ex_compact, ex_tokens, ex_nums = _extract_event_features(ex.get("title") or "")
        if cand_compact and cand_compact == ex_compact:
            return True

        ex_date_s = (ex.get("disclosure_date") or "")[:10]
        try:
            ex_dt = dt.date.fromisoformat(ex_date_s) if ex_date_s else None
        except ValueError:
            ex_dt = None

        day_diff = abs((cand_dt - ex_dt).days) if (cand_dt and ex_dt) else 0
        if day_diff > 7:
            continue

        ex_type = (ex.get("disclosure_type") or "").strip().lower()
        ex_sent = (ex.get("sentiment") or "").strip().lower()
        if (
            cand_type in ("earnings", "dividend", "capital_change", "board_decision")
            and cand_type == ex_type
            and cand_sent == ex_sent
        ):
            return True

        if day_diff <= 5:
            if cand_nums and ex_nums and (cand_nums & ex_nums):
                return True
            if cand_tokens and ex_tokens:
                union = cand_tokens | ex_tokens
                if union and (len(cand_tokens & ex_tokens) / len(union)) >= 0.60:
                    return True

    return False


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
                norm_title = _normalize_ar(items[idx].get("title") or "")
                is_explicit_bear = (
                    any(p in norm_title for p in _EXPLICIT_BEAR_PHRASES)
                    and "تتجاوز التوقعات" not in norm_title
                )
                if entry.get("sentiment") in ("bullish", "bearish", "neutral"):
                    if is_explicit_bear and items[idx].get("sentiment") == "bearish":
                        items[idx]["sentiment"] = "bearish"
                    else:
                        items[idx]["sentiment"] = entry["sentiment"]
                if not items[idx].get("shares_count"):
                    items[idx]["action_type"] = "general"
    except Exception:
        pass


_NON_SAUDI_KEYWORDS = (
    "جنيه", "البورصة المصرية", "egx", "القاهرة للدواجن", "الرقابة المالية",
    "الصناعات التحويلية", "بورصة الكويت", "سوق دبي", "سوق أبوظبي", "بورصة قطر",
    "مسقط", "دينار", "درهم",
)


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
            raw_title = _clean_saudi_title(raw_title, source_name)
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

            raw_title_lower = raw_title.lower()
            if any(bad in raw_title_lower for bad in _NON_SAUDI_KEYWORDS):
                continue

            sym, company_name = _match_symbol(raw_title, matcher)
            if not sym:
                continue
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

    # Sort newest first and filter out both DB & cross-source duplicates before LLM enrichment
    rows.sort(key=lambda r: r["disclosure_date"], reverse=True)
    since_45d = (dt.date.today() - dt.timedelta(days=45)).isoformat()
    existing_res = (
        sb.table("egx_disclosures")
        .select("id, symbol, disclosure_type, disclosure_date, title, sentiment, source_url")
        .gte("disclosure_date", since_45d)
        .limit(1000)
        .execute()
    )
    existing_pool: List[Dict[str, Any]] = list(existing_res.data or [])
    new_rows: List[Dict[str, Any]] = []
    for candidate in rows:
        if _is_duplicate_saudi_event(candidate, existing_pool):
            continue
        existing_pool.append(candidate)
        new_rows.append(candidate)

    _enrich_with_deepseek(new_rows[:20], ds_key)

    saved = 0
    for i in range(0, len(new_rows), 25):
        chunk = new_rows[i:i + 25]
        sb.table("egx_disclosures").insert(chunk).execute()
        saved += len(chunk)

    return {"ok": True, "fetched": len(rows), "saved": saved}


if __name__ == "__main__":
    print(run_saudi_disclosures_sync(days_back=30))
