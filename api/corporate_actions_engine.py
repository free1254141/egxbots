"""
Corporate Actions Engine — free, keyless EGX corporate-action news pipeline.

Detects and stores corporate actions (حقوق الاكتتاب، التجزئة، توزيعات الأرباح،
الأسهم المجانية، زيادة/تخفيض رأس المال، إعادة الشراء، الاستحواذ، النتائج)
into the Supabase `corporate_actions` table so the chatbot can ground its
answers on them.

Sources (all free, no API key):
    - Google News RSS (reuses news_sentiment_engine.fetch_google_news)
    - Classification is rule-based (bilingual regex), mirroring the sentiment
      lexicon approach used for `stock_news_sentiment`.

Two entry points:
    1. `process_news_list_for_corporate_actions()` — classify an already-fetched
       news list (called from process_exchange_news; zero extra network calls).
    2. `process_exchange_corporate_actions()` — full standalone pass
       (fetch + classify + save), used by run_corporate_actions_update.py.
"""

from api.rss_budget import RSSBudget, RSSUnavailable
import re
import hashlib
import datetime as dt
from typing import List, Dict, Any, Optional, Tuple

from api.news_sentiment_engine import (
    fetch_google_news,
    analyze_sentiment,
    is_relevant_news,
    is_unrelated_news,
    parse_pub_date,
)

# ---------------------------------------------------------------------------
# Arabic normalization (same conventions as the rest of the codebase)
# ---------------------------------------------------------------------------

def _normalize_arabic(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
        .replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
        .replace("\u0640", "")
        .lower()
    )


# ---------------------------------------------------------------------------
# Corporate-action taxonomy + bilingual patterns (ordered by specificity:
# first match wins so "حقوق اكتتاب" beats the generic "زيادة رأس المال"
# when both appear in one headline)
# ---------------------------------------------------------------------------

CORPORATE_ACTION_TYPES: List[Tuple[str, str, List[str], float]] = [
    (
        "rights_issue",
        "حقوق اكتتاب",
        [
            r"حق(?:وق)?\s*(?:ال)?اكتتاب",
            r"اكتتاب\s*(?:في|فى)?\s*(?:حق|زياده)",
            r"(?:ال)?اكتتاب\s*(?:في|فى)\s*زياده\s*راس",
            r"حق\s*الاولويه",
            r"نهايه\s*حق\s*(?:ال)?اكتتاب",
            r"سعر\s*فتح\s*حق",
            r"\brights?\s+(?:issue|offering|subscription)\b",
            r"\bsubscription\s+rights\b",
        ],
        0.9,
    ),
    (
        "dividend",
        "توزيعات أرباح",
        [
            r"توزيعات", r"توزيع\s*ارباح", r"كوبون", r"توزيع\s*نقدي",
            r"\bdividend", r"cash\s+distribution",
        ],
        0.85,
    ),
    (
        "bonus_shares",
        "أسهم مجانية (منحة)",
        [
            r"اسهم?\s*مجاني[هة]?", r"منح[هة]\s*(?:اسهم|حصص|سهم)", r"حصص\s*مجاني[هة]?",
            r"\bbonus\s+shares?\b", r"\bfree\s+shares?\b", r"\bstock\s+dividend\b",
        ],
        0.85,
    ),
    (
        "stock_split",
        "تجزئة السهم",
        [
            r"تجزئ[ةه]?\s*(?:ال)?سهم", r"سهم.{0,12}تجزئ", r"تجزئ[ةه]?.{0,12}الاسمي[هة]",
            r"تقسيم\s*(?:ال)?سهم", r"\bstock\s+split\b", r"\bshare\s+split\b",
        ],
        0.85,
    ),
    (
        "par_value_reduction",
        "تخفيض القيمة الاسمية",
        [
            r"تخفيض.{0,12}الاسمي[هة]", r"الاسمي[هة].{0,12}تخفيض",
            r"\bpar\s+value\s+reduction\b",
        ],
        0.8,
    ),
    (
        "capital_increase",
        "زيادة رأس المال",
        [
            r"زياده.{0,10}راس\s*(?:ال)?مال", r"زياده.{0,20}(?:المصدر|المدفوع)",
            r"رفع.{0,15}راس\s*(?:ال)?مال", r"\bcapital\s+increase\b",
            r"rais\w*\s+capital\b", r"\bshare\s+issue\b",
        ],
        0.8,
    ),
    (
        "capital_reduction",
        "تخفيض رأس المال",
        [
            r"تخفيض.{0,10}راس\s*(?:ال)?مال", r"تخفيض.{0,20}(?:المصدر|غير\s*المدفوع)",
            r"\bcapital\s+reduction\b", r"reduc\w*\s+capital\b",
        ],
        0.8,
    ),
    (
        "buyback",
        "إعادة شراء الأسهم",
        [
            r"اعاده\s*شراء", r"برنامج\s*استرداد", r"استرداد\s*اسهم",
            r"\bbuy-?back\b", r"\brepurchas", r"\btreasury\s+shares?\b",
        ],
        0.8,
    ),
    (
        "merger_acquisition",
        "استحواذ / اندماج",
        [
            r"استحواذ", r"اندماج", r"صفقه\s*(?:شراء|استحواذ|دمج)",
            r"\bacquisition\b", r"\bmerger\b", r"\bacquir\w*\b",
        ],
        0.75,
    ),
    (
        "earnings",
        "نتائج أعمال",
        [
            r"نتائج\s*(?:الاعمال|الربع|اعمال|النصف)", r"ارباح.{0,15}(?:الربع|النصف|العام|السنه|9|تسعه)",
            r"بيانات?\s*مالي[هة]", r"قوائم?\s*مالي[هة]", r"\bearnings\b",
            r"\bquarterly\s+results?\b", r"\bresults?\s+announcement\b",
        ],
        0.6,
    ),
]

_COMPILED_PATTERNS = [
    (action_type, label_ar, [re.compile(p) for p in patterns], base_conf)
    for action_type, label_ar, patterns, base_conf in CORPORATE_ACTION_TYPES
]


# ---------------------------------------------------------------------------
# Detail extraction (amounts / percentages / ratios inside the headline)
# ---------------------------------------------------------------------------

def _extract_details(title: str) -> Dict[str, Any]:
    details: Dict[str, Any] = {}
    pct = re.search(r"(\d+(?:\.\d+)?)\s*%", title)
    if pct:
        details["percentage"] = float(pct.group(1))
    amount = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:جنيه|ج\.?م\.?|le|egp)\b",
        _normalize_arabic(title),
    )
    if amount:
        details["amount_egp"] = float(amount.group(1))
    per_shares = re.search(r"(\d+(?:\.\d+)?)\s*(?:جنيه|ج\.?م\.?|le|egp)\s*(?:لكل|لـ|ا?ل?|لل)?\s*سهم", _normalize_arabic(title))
    if per_shares:
        details["amount_per_share_egp"] = float(per_shares.group(1))
    ratio = re.search(r"لكل\s*(?:سهم|اسهم)\s*(\d+(?:\.\d+)?\s*(?:سهم|اسهم))", _normalize_arabic(title))
    if ratio:
        details["ratio_per_share"] = ratio.group(1)
    return details


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_corporate_action(title: str) -> Optional[Dict[str, Any]]:
    """
    Classify a headline as a corporate action.
    Returns None when the headline is not a corporate action.
    """
    if not title:
        return None
    normalized = _normalize_arabic(title)
    for action_type, label_ar, patterns, base_conf in _COMPILED_PATTERNS:
        if action_type == "dividend" and re.search(
            r"stock\s+dividend|اسهم?\s*مجاني|منح[هة]?\s*(?:اسهم|سهم)|توزيعات?\s*(?:ال)?مجاني", normalized, re.I
        ):
            continue
        if action_type == "bonus_shares" and re.search(r"توزيعات?\s*(?:ال)?مجاني[هة]", normalized):
            return {"action_type": action_type, "action_type_ar": label_ar, "confidence": base_conf, "details": _extract_details(title) or None}
        for pattern in patterns:
            if pattern.search(normalized) or pattern.search(title.lower()):
                details = _extract_details(title)
                return {
                    "action_type": action_type,
                    "action_type_ar": label_ar,
                    "confidence": round(base_conf + (0.1 if details else 0.0), 2),
                    "details": details or None,
                }
    return None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _dedupe_key(exchange: str, symbol: str, action_type: str, url: str, title: str) -> str:
    if url:
        identity = url.strip().lower()
    else:
        identity = hashlib.md5(_normalize_arabic(title).encode("utf-8")).hexdigest()[:20]
    return f"{exchange}|{symbol}|{action_type}|{identity}"


def _save_corporate_action(
    supabase,
    symbol: str,
    exchange: str,
    item: Dict[str, Any],
    classification: Dict[str, Any],
    origin: str,
) -> bool:
    title = item.get("title", "")
    url = item.get("link") or item.get("url")
    source = item.get("source") or "Google News"
    published = item.get("published") or item.get("publishedAt") or item.get("date")

    payload = {
        "symbol": symbol.split(".")[0].upper(),
        "exchange": exchange,
        "action_type": classification["action_type"],
        "title": title,
        "published_at": f"{published}T00:00:00Z" if published and len(str(published)) == 10 else published,
        "url": url,
        "source": source,
        "details": classification.get("details"),
        "confidence": classification.get("confidence", 0.5),
        "origin": origin,
        "dedupe_key": _dedupe_key(exchange, symbol, classification["action_type"], url or "", title),
        "updated_at": dt.datetime.utcnow().isoformat(),
    }

    sentiment = analyze_sentiment([item])
    payload["sentiment_score"] = sentiment.get("sentiment_score", 0.0)
    score = float(sentiment.get("sentiment_score", 0.0))
    payload["sentiment_label"] = "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"

    supabase.table("corporate_actions").upsert(payload, on_conflict="dedupe_key").execute()
    return True


PRICE_ADJUSTING_ACTION_TYPES = (
    "rights_issue",
    "bonus_shares",
    "stock_split",
    "par_value_reduction",
    "capital_increase",
    "capital_reduction",
    "dividend",
)


def load_price_adjusting_action_dates(
    client: Any,
    exchange: str = "EGX",
    since_days: int = 200,
) -> Dict[str, List[str]]:
    """Load recent price-adjusting corporate action dates keyed by uppercase symbol."""
    if client is None:
        return {}
    by_symbol: Dict[str, List[str]] = {}
    ex = str(exchange or "EGX").strip().upper()
    iso_since = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=since_days)
    ).strftime("%Y-%m-%dT00:00:00Z")
    try:
        res = (
            client.table("corporate_actions")
            .select("symbol,action_type,published_at,details")
            .eq("exchange", ex)
            .in_("action_type", list(PRICE_ADJUSTING_ACTION_TYPES))
            .gte("published_at", iso_since)
            .order("published_at", desc=True)
            .limit(2000)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        for row in rows:
            sym = str(row.get("symbol") or "").split(".")[0].strip().upper()
            details_obj = row.get("details") if isinstance(row.get("details"), dict) else {}
            raw_date = details_obj.get("action_date") or row.get("action_date") or row.get("published_at") or ""
            pub_str = str(raw_date)[:10]
            if not sym or len(pub_str) != 10:
                continue
            dates_list = by_symbol.setdefault(sym, [])
            if pub_str not in dates_list:
                dates_list.append(pub_str)
    except Exception as exc:
        print(f"[CA-ENGINE] Could not load price-adjusting action dates for {exchange}: {exc}")

    disc_table = "egx_disclosures" if ex in ("EGX", "TADAWUL", "TASI") else ""
    if disc_table:
        try:
            disc_res = (
                client.table(disc_table)
                .select("symbol,title,disclosure_date")
                .gte("disclosure_date", iso_since[:10])
                .order("disclosure_date", desc=True)
                .limit(1000)
                .execute()
            )
            for row in getattr(disc_res, "data", None) or []:
                sym = str(row.get("symbol") or "").split(".")[0].strip().upper()
                title = str(row.get("title") or "").strip()
                d_str = str(row.get("disclosure_date") or "")[:10]
                if not sym or len(d_str) != 10 or not title:
                    continue
                cls = classify_corporate_action(title)
                if cls and cls["action_type"] in PRICE_ADJUSTING_ACTION_TYPES:
                    dates_list = by_symbol.setdefault(sym, [])
                    if d_str not in dates_list:
                        dates_list.append(d_str)
        except Exception:
            pass

    return by_symbol


def verify_symbol_corporate_action_live(
    client: Any,
    symbol: str,
    exchange: str,
    event_day: str,
) -> Optional[Dict[str, Any]]:
    """Verify whether an extreme gap corresponds to a real corporate action via trusted sources."""
    clean_sym = str(symbol or "").split(".")[0].strip().upper()
    if not clean_sym:
        return None
    raw_ex = str(exchange or "EGX").strip().upper()
    ex = "TADAWUL" if raw_ex in {"TADAWUL", "TASI", "SA", "SR"} else raw_ex
    try:
        ev_date = dt.date.fromisoformat(str(event_day)[:10])
    except (ValueError, TypeError):
        return None
    min_date = ev_date - dt.timedelta(days=120)
    max_date = ev_date + dt.timedelta(days=2)

    def _in_window(raw_d: Any) -> Optional[str]:
        s = str(raw_d or "")[:10]
        if len(s) != 10:
            return None
        try:
            d = dt.date.fromisoformat(s)
        except (ValueError, TypeError):
            return None
        return s if min_date <= d <= max_date else None

    action_priority = {t: idx for idx, t in enumerate(PRICE_ADJUSTING_ACTION_TYPES)}

    # 1. Existing corporate_actions rows
    if client is not None:
        try:
            ca_res = (
                client.table("corporate_actions")
                .select("action_type,title,published_at,details")
                .eq("symbol", clean_sym)
                .eq("exchange", ex)
                .in_("action_type", list(PRICE_ADJUSTING_ACTION_TYPES))
                .order("published_at", desc=True)
                .limit(20)
                .execute()
            )
            for row in getattr(ca_res, "data", None) or []:
                details_obj = row.get("details") if isinstance(row.get("details"), dict) else {}
                d_str = _in_window(details_obj.get("action_date") or row.get("published_at"))
                if d_str:
                    atype = str(row.get("action_type") or "")
                    label_ar = next((lbl for t, lbl, _, _ in CORPORATE_ACTION_TYPES if t == atype), atype)
                    return {
                        "confirmed": True,
                        "action_type": atype,
                        "action_type_ar": label_ar,
                        "title": str(row.get("title") or ""),
                        "date": d_str,
                        "source": "corporate_actions",
                    }
        except Exception:
            pass

        # 2. Existing official disclosures
        disc_table = "egx_disclosures" if ex in ("EGX", "TADAWUL") else ""
        if disc_table:
            try:
                disc_res = (
                    client.table(disc_table)
                    .select("title,disclosure_date")
                    .eq("symbol", clean_sym)
                    .order("disclosure_date", desc=True)
                    .limit(20)
                    .execute()
                )
                for row in getattr(disc_res, "data", None) or []:
                    title = str(row.get("title") or "").strip()
                    d_str = _in_window(row.get("disclosure_date"))
                    if not title or not d_str:
                        continue
                    cls = classify_corporate_action(title)
                    if cls and cls["action_type"] in PRICE_ADJUSTING_ACTION_TYPES:
                        return {
                            "confirmed": True,
                            "action_type": cls["action_type"],
                            "action_type_ar": cls["action_type_ar"],
                            "title": title,
                            "date": d_str,
                            "source": disc_table,
                        }
            except Exception:
                pass

    # 3. On-demand Google News RSS corporate-action verification
    company_name = ""
    subject_name = ""
    try:
        from api.news_sentiment_engine import load_company_names
        aliases = load_company_names(client) if client is not None else {}
        sym_aliases = aliases.get(clean_sym) or []
        if sym_aliases:
            company_name = ", ".join(sym_aliases)
            arabic_aliases = [n for n in sym_aliases if any("\u0600" <= ch <= "\u06FF" for ch in n)]
            subject_name = max(arabic_aliases, key=len) if arabic_aliases else sym_aliases[0]
    except Exception:
        pass

    if not company_name and client is not None:
        try:
            st_rows = (
                client.table("stocks")
                .select("name,name_ar")
                .eq("symbol", clean_sym)
                .limit(1)
                .execute()
            ).data or []
            if st_rows:
                names = [str(st_rows[0].get(k) or "").strip() for k in ("name_ar", "name") if st_rows[0].get(k)]
                company_name = ", ".join(names)
                subject_name = str(st_rows[0].get("name_ar") or st_rows[0].get("name") or "").strip()
        except Exception:
            pass

    try:
        news_items = fetch_corporate_action_news(clean_sym, subject_name, days_back=60, exchange=ex)
        matched: List[Tuple[Tuple[int, int], Dict[str, Any], Dict[str, Any], str]] = []
        for item in news_items or []:
            title = str(item.get("title") or "").strip()
            if not title or not is_relevant_news(title, clean_sym, company_name) or is_unrelated_news(title):
                continue
            cls = classify_corporate_action(title)
            if not cls or cls["action_type"] not in PRICE_ADJUSTING_ACTION_TYPES:
                continue
            d_str = _in_window(item.get("published") or item.get("publishedAt") or item.get("date"))
            if not d_str:
                continue
            day_dist = abs((ev_date - dt.date.fromisoformat(d_str)).days)
            score_key = (day_dist, action_priority.get(cls["action_type"], 99))
            matched.append((score_key, item, cls, d_str))

        if matched:
            matched.sort(key=lambda x: x[0])
            best_item = matched[0][1]
            best_cls = matched[0][2]
            best_day = matched[0][3]
            if client is not None:
                try:
                    process_news_list_for_corporate_actions(
                        clean_sym,
                        ex,
                        [m[1] for m in matched],
                        supabase=client,
                        origin="auto_verify",
                        company_name=company_name,
                    )
                except Exception:
                    pass
            return {
                "confirmed": True,
                "action_type": best_cls["action_type"],
                "action_type_ar": best_cls["action_type_ar"],
                "title": str(best_item.get("title") or ""),
                "date": best_day,
                "source": "google_news_rss",
            }
    except Exception:
        pass

    # 3b. Yahoo Finance recorded splits fallback (tight window [-7d, +2d])
    try:
        import yfinance as yf
        suffix = ".SR" if ex == "TADAWUL" else ".CA"
        splits = yf.Ticker(f"{clean_sym}{suffix}").splits
        if splits is not None and not splits.empty:
            for ts, ratio in splits.items():
                try:
                    sp_date = ts.date() if hasattr(ts, "date") else dt.date.fromisoformat(str(ts)[:10])
                    if (ev_date - dt.timedelta(days=7)) <= sp_date <= max_date and float(ratio) not in (0.0, 1.0):
                        return {
                            "confirmed": True,
                            "action_type": "stock_split",
                            "action_type_ar": "تجزئة السهم",
                            "title": f"Yahoo Finance verified split factor {ratio} on {sp_date.isoformat()}",
                            "date": sp_date.isoformat(),
                            "source": "yfinance_splits",
                        }
                except Exception:
                    continue
    except Exception:
        pass

    return None


def process_news_list_for_corporate_actions(
    symbol: str,
    exchange: str,
    news_items: List[Dict[str, Any]],
    supabase=None,
    origin: str = "scheduler",
    company_name: str = "",
) -> int:
    """
    Classify an already-fetched news list and store corporate actions.
    Returns the number of stored actions (0 when nothing matched or on failure).

    Every headline is relevance-checked against the symbol first: a generic
    article returned by the RSS query (e.g. "EGX approves Edita's capital
    increase") must never be stored as an action for unrelated symbols.
    """
    try:
        if supabase is None:
            import api.stock_ai as stock_ai
            stock_ai._init_supabase()
            supabase = stock_ai.supabase
        if not supabase or not news_items:
            return 0

        saved = 0
        for item in news_items:
            title = item.get("title", "")
            if not is_relevant_news(title, symbol, company_name) or is_unrelated_news(title):
                continue
            classification = classify_corporate_action(title)
            if not classification:
                continue
            try:
                _save_corporate_action(supabase, symbol, exchange, item, classification, origin)
                saved += 1
            except Exception as e:
                print(f"[CA-ENGINE] Failed saving action for {symbol}: {e}")
        return saved
    except Exception as e:
        print(f"[CA-ENGINE] process_news_list error for {symbol}: {e}")
        return 0


def fetch_corporate_action_news(
    symbol: str,
    company_name: str = "",
    days_back: int = 30,
    rss_budget=None,
    exchange: str = "EGX",
) -> List[Dict[str, Any]]:
    """
    Fetch news likely to contain corporate actions for a symbol using
    keyless Google News RSS with targeted bilingual queries.
    """
    import urllib.parse
    import urllib.request
    import xml.etree.ElementTree as ET
    import email.utils

    rss_budget = rss_budget or RSSBudget(seconds=30)
    successful_before = rss_budget.succeeded
    clean_sym = symbol.split(".")[0].upper()
    subject = company_name or clean_sym
    ex_upper = str(exchange or "EGX").strip().upper()
    is_saudi = ex_upper in ("TADAWUL", "TASI", "SA", "SR")
    if is_saudi:
        queries = [
            f'{subject} (اكتتاب OR توزيعات OR تجزئة OR منحة OR "رأس المال") تداول',
            f'{clean_sym} (dividend OR split OR "rights issue" OR bonus) Tadawul',
        ]
        gl = "SA"
    else:
        queries = [
            f'{subject} (اكتتاب OR توزيعات OR تجزئة OR منحة OR "رأس المال")',
            f'{clean_sym} (dividend OR split OR "rights issue" OR bonus) EGX',
        ]
        gl = "EG"

    items: Dict[str, Dict[str, Any]] = {}
    cutoff_date = dt.date.today() - dt.timedelta(days=days_back)

    for query in queries:
        if rss_budget.stopped:
            break
        try:
            hl = "ar" if any("\u0600" <= ch <= "\u06FF" for ch in query) else "en"
            url = (
                "https://news.google.com/rss/search?q="
                + urllib.parse.quote(query) + f"&hl={hl}&gl={gl}&ceid={gl}:{hl}"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            root = rss_budget.fetch(req)

            for item_el in root.findall(".//item"):
                title_el = item_el.find("title")
                link_el = item_el.find("link")
                pub_el = item_el.find("pubDate")
                source_el = item_el.find("source")
                if title_el is None or link_el is None:
                    continue
                title = title_el.text or ""
                link = link_el.text or ""
                pub_str = pub_el.text if pub_el is not None else None
                # parse_pub_date returns a date so it compares safely with
                # cutoff_date (a datetime raises TypeError and silently kept
                # undated items before).
                published = parse_pub_date(pub_str)
                if published is not None and published < cutoff_date:
                    continue
                if link not in items:
                    items[link] = {
                        "title": title,
                        "link": link,
                        "published": published.isoformat() if published else None,
                        "source": source_el.text if source_el is not None else "Google News",
                    }
        except Exception as e:
            print(f"[CA-ENGINE] Query '{query}' failed: {e}")

    if rss_budget.succeeded == successful_before:
        raise RSSUnavailable("No valid corporate-action RSS response for this symbol")
    return list(items.values())


def process_exchange_corporate_actions(exchange: str, symbols: List[str], days_back: int = 30, progress_callback=None) -> Tuple[bool, int]:
    """
    Full standalone pass: fetch targeted CA news per symbol, classify, save.
    """
    import time

    try:
        import api.stock_ai as stock_ai
        stock_ai._init_supabase()
        if not stock_ai.supabase:
            print("[CA-ENGINE] Supabase not initialized. Skipping.")
            return False, 0
        supabase = stock_ai.supabase
    except Exception as e:
        print(f"[CA-ENGINE] Supabase init error: {e}")
        return False, 0

    # Company names improve recall (many headlines use the Arabic company name)
    # and are required for the relevance check that keeps generic market
    # articles from being stored as actions for unrelated symbols.
    name_map: Dict[str, str] = {}
    subject_map: Dict[str, str] = {}
    try:
        from api.news_sentiment_engine import load_company_names
        aliases = load_company_names(supabase)
        for sym, names in aliases.items():
            name_map[sym] = ", ".join(names)
            arabic = [n for n in names if any("\u0600" <= ch <= "\u06FF" for ch in n)]
            subject_map[sym] = max(arabic, key=len) if arabic else (names[0] if names else "")
    except Exception:
        pass

    saved_total = 0
    print(f"[CA-ENGINE] Processing corporate actions for {len(symbols)} symbols...")
    budget = RSSBudget()
    processed = 0
    for index, symbol in enumerate(symbols):
        if budget.stopped:
            break
        try:
            clean_sym = symbol.split(".")[0].upper()
            news = fetch_corporate_action_news(
                symbol,
                subject_map.get(clean_sym, ""),
                days_back=days_back,
                rss_budget=budget,
                exchange=exchange,
            )
            saved_total += process_news_list_for_corporate_actions(
                clean_sym,
                exchange,
                news,
                supabase=supabase,
                company_name=name_map.get(clean_sym, ""),
            )
            processed += 1
            time.sleep(0.15)
        except Exception as e:
            print(f"[CA-ENGINE] Error processing {symbol}: {e}")
        finally:
            if progress_callback and (index % 5 == 0 or budget.stopped or index == len(symbols)-1):
                progress_callback({"processed": index+1, "total": len(symbols), "saved": saved_total, **budget.summary()})

    print(f"[CA-ENGINE] Done — {saved_total} corporate actions stored/refreshed.")
    is_ok = not budget.is_outage and (budget.succeeded > 0 or processed == len(symbols))
    return is_ok, saved_total
