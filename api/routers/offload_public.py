"""Public SEO page snapshots, market breadth, and scanner endpoints hosted on Hugging Face.

Eliminates Vercel Fluid Active CPU consumption for:
- Stock page SSR/client snapshots & directories (/stocks/[symbol], /stocks)
- Fair Value & Sharia reports (/fair-value, /sharia)
- Verified daily reports archive & blog sitemap (/reports/*, /sitemap.xml)
- Scanners (/api/scan/technical, news, similarity, sectors, traps, unusual-activity)
- Market analytics (/api/market/breadth, fair-value, scan-settings, macro-correlation/*)
- EGX30, benchmark, corporate chart-events, models, adaptive recommendation, and SVG disclosures
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import escape as xml_escape
import json
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from api.daily_job_outcome import effective_daily_steps
from api.egx_canonical_names import CANONICAL_EGX_STOCK_NAMES
from api.perf_utils import (
    BoundedTTLCache,
    SingleFlight,
    get_cairo_date_str,
    get_market_exchange,
    get_market_exchanges,
    get_market_supabase,
    get_primary_supabase,
    resolve_request_market,
)
from api.saudi_stock_aliases import SAUDI_STOCK_NAMES_AR, is_saudi_symbol
from api.sharia_stocks import is_sharia_compliant

router = APIRouter()

_RUN_TO_RUN_TTL = 86400.0
_SAUDI_SYMBOL_RE = re.compile(r"^\d{4}(\.(sr|sa|tadawul))?$", re.IGNORECASE)
_EGX_SYMBOL_DIR_RE = re.compile(r"^[A-Z][A-Z0-9]{1,11}$")
_SYMBOL_PARAM_RE = re.compile(r"^[A-Z0-9._-]{1,24}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DISCLOSURE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")

_PUBLIC_STOCK_PAGE_CACHE = BoundedTTLCache(max_entries=1024, default_ttl=_RUN_TO_RUN_TTL)
_PUBLIC_STOCK_PAGE_SF = SingleFlight()
_PUBLIC_DIR_CACHE = BoundedTTLCache(max_entries=8, default_ttl=_RUN_TO_RUN_TTL)
_PUBLIC_DIR_SF = SingleFlight()
_FAIR_VALUE_CACHE = BoundedTTLCache(max_entries=8, default_ttl=_RUN_TO_RUN_TTL)
_FAIR_VALUE_SF = SingleFlight()
_REPORTS_ARCHIVE_CACHE = BoundedTTLCache(max_entries=4, default_ttl=_RUN_TO_RUN_TTL)
_REPORTS_ARCHIVE_SF = SingleFlight()
_SITEMAP_POSTS_CACHE = BoundedTTLCache(max_entries=4, default_ttl=3600.0)
_SITEMAP_POSTS_SF = SingleFlight()
_TECH_DATASET_CACHE = BoundedTTLCache(max_entries=4, default_ttl=_RUN_TO_RUN_TTL)
_TECH_DATASET_SF = SingleFlight()
_NEWS_CACHE = BoundedTTLCache(max_entries=32, default_ttl=_RUN_TO_RUN_TTL)
_NEWS_SF = SingleFlight()
_SECTOR_CACHE = BoundedTTLCache(max_entries=8, default_ttl=_RUN_TO_RUN_TTL)
_SECTOR_SF = SingleFlight()
_SIMILARITY_CACHE = BoundedTTLCache(max_entries=8, default_ttl=_RUN_TO_RUN_TTL)
_SIMILARITY_SF = SingleFlight()
_HEATMAP_CACHE = BoundedTTLCache(max_entries=32, default_ttl=_RUN_TO_RUN_TTL)
_HEATMAP_SF = SingleFlight()
_TIMELINE_CACHE = BoundedTTLCache(max_entries=16, default_ttl=_RUN_TO_RUN_TTL)
_TIMELINE_SF = SingleFlight()
_TRAPS_CACHE = BoundedTTLCache(max_entries=8, default_ttl=_RUN_TO_RUN_TTL)
_TRAPS_SF = SingleFlight()
_UNUSUAL_CACHE = BoundedTTLCache(max_entries=8, default_ttl=_RUN_TO_RUN_TTL)
_UNUSUAL_SF = SingleFlight()
_BREADTH_CACHE = BoundedTTLCache(max_entries=8, default_ttl=_RUN_TO_RUN_TTL)
_BREADTH_SF = SingleFlight()
_MACRO_CACHE = BoundedTTLCache(max_entries=128, default_ttl=_RUN_TO_RUN_TTL)
_MACRO_SF = SingleFlight()
_EGX30_CACHE = BoundedTTLCache(max_entries=32, default_ttl=_RUN_TO_RUN_TTL)
_EGX30_SF = SingleFlight()
_BENCHMARK_CACHE = BoundedTTLCache(max_entries=32, default_ttl=_RUN_TO_RUN_TTL)
_BENCHMARK_SF = SingleFlight()
_EVENTS_CACHE = BoundedTTLCache(max_entries=128, default_ttl=3600.0)
_EVENTS_SF = SingleFlight()
_MODELS_CACHE = BoundedTTLCache(max_entries=16, default_ttl=3600.0)
_MODELS_SF = SingleFlight()
_SCAN_SETTINGS_CACHE = BoundedTTLCache(max_entries=2, default_ttl=300.0)
_SVG_CACHE = BoundedTTLCache(max_entries=128, default_ttl=_RUN_TO_RUN_TTL)
_DISCLOSURES_PAGE_CACHE = BoundedTTLCache(max_entries=4, default_ttl=_RUN_TO_RUN_TTL)
_DISCLOSURES_PAGE_SF = SingleFlight()
_GCC_METALS_DIR_CACHE = BoundedTTLCache(max_entries=4, default_ttl=_RUN_TO_RUN_TTL)
_GCC_METALS_DIR_SF = SingleFlight()

_PUBLIC_TAG_TO_CACHES: Dict[str, Tuple[Tuple[str, BoundedTTLCache], ...]] = {
    "daily-symbols": (
        ("public_directory", _PUBLIC_DIR_CACHE),
        ("gcc_metals_dir", _GCC_METALS_DIR_CACHE),
        ("public_stock_page", _PUBLIC_STOCK_PAGE_CACHE),
        ("macro", _MACRO_CACHE),
    ),
    "daily-market-data": (
        ("public_stock_page", _PUBLIC_STOCK_PAGE_CACHE),
        ("public_directory", _PUBLIC_DIR_CACHE),
        ("gcc_metals_dir", _GCC_METALS_DIR_CACHE),
        ("fair_value", _FAIR_VALUE_CACHE),
        ("tech_dataset", _TECH_DATASET_CACHE),
        ("similarity", _SIMILARITY_CACHE),
        ("heatmap", _HEATMAP_CACHE),
        ("timeline", _TIMELINE_CACHE),
        ("traps", _TRAPS_CACHE),
        ("unusual", _UNUSUAL_CACHE),
        ("breadth", _BREADTH_CACHE),
        ("macro", _MACRO_CACHE),
        ("egx30", _EGX30_CACHE),
        ("benchmark", _BENCHMARK_CACHE),
    ),
    "daily-recommendations": (
        ("public_stock_page", _PUBLIC_STOCK_PAGE_CACHE),
        ("tech_dataset", _TECH_DATASET_CACHE),
    ),
    "daily-news-data": (
        ("news", _NEWS_CACHE),
        ("news_sectors", _SECTOR_CACHE),
        ("chart_events", _EVENTS_CACHE),
    ),
    "daily-public-reports": (
        ("reports_archive", _REPORTS_ARCHIVE_CACHE),
        ("sitemap_posts", _SITEMAP_POSTS_CACHE),
    ),
    "daily-disclosures": (
        ("disclosures_page", _DISCLOSURES_PAGE_CACHE),
        ("disclosure_svg", _SVG_CACHE),
    ),
}

_FALLBACK_EGX_SYMBOLS: Tuple[str, ...] = (
    "AALR", "ABUK", "ACAMD", "ACAP", "ACGC", "ACRO", "ACTF", "ADCI", "ADIB", "ADPC",
    "ADRI", "AFDI", "AFMC", "AGIG", "AIDC", "AIH", "AIND", "AIVCB", "AJWA", "ALCN",
    "ALEX", "ALRA", "ALUM", "AMER", "AMES", "AMIA", "AMII", "AMOC", "AMPI", "ANFI",
    "APPC", "APSW", "ARAB", "ARCC", "AREH", "AREHA", "ARVA", "ASCM", "ASPI", "ATLC",
    "ATQA", "AUTO", "AXPH", "BCAP", "BIDI", "BIGP", "BINV", "BIOC", "BONY", "BTFH",
    "CAED", "CANA", "CCAP", "CCRS", "CEFM", "CERA", "CFGH", "CICH", "CIEB", "CILB",
    "CIRA", "CIRF", "CLHO", "CNFN", "COMI", "COPR", "COSG", "CPCI", "CPME", "CRST",
    "CSAG", "DAPH", "DCRC", "DEIN", "DGTZ", "DOMT", "DSCW", "DTPP", "EALR", "EASB",
    "EAST", "EBSC", "ECAP", "EDBM", "EDFM", "EEII", "EFIC", "EFID", "EFIH", "EGAL",
    "EGAS", "EGBE", "EGCH", "EGREF", "EGSA", "EGTS", "EHDR", "EITP", "EKHOA", "ELEC",
    "ELKA", "ELNA", "ELSH", "ELWA", "EMFD", "ENGC", "EOSB", "EPCO", "EPPK", "ESRS",
    "ETEL", "ETRS", "EXPA", "FAIT", "FAITA", "FCMD", "FERC", "FIRE", "FNAR", "FTNS",
    "FWRY", "GBCO", "GDWA", "GGCC", "GGRN", "GIHD", "GMCI", "GOUR", "GPIM", "GPPL",
    "GRCA", "GSSC", "GTEX", "GTHE", "GTWL", "HBCO", "HDBK", "HELI", "HRHO", "IBCT",
    "ICFC", "ICID", "ICLE", "IDRE", "IEEC", "IFAP", "INEG", "INFI", "IRAX", "IRON",
    "ISMA", "ISMQ", "ISPH", "JUFO", "KABO", "KASABF", "KORA", "KRDI", "KWIN", "KZPC",
    "LCSW", "LUTS", "MAAL", "MASR", "MATD", "MBEG", "MBSC", "MCQE", "MCRO", "MEDP",
    "MEGM", "MENA", "MEPA", "MFPC", "MFSC", "MHOT", "MICH", "MILS", "MIPH", "MKIT",
    "MOED", "MOIL", "MOIN", "MOSC", "MPCI", "MPCO", "MPRC", "MTIE", "NAHO", "NAPR",
    "NARE", "NBKE", "NCCW", "NCGC", "NDRL", "NEDA", "NHPS", "NINH", "NIPH", "OBRI",
    "OCDI", "OCPH", "ODIN", "OFH", "OIH", "OLFI", "ORAS", "ORHD", "ORMT", "ORWE",
    "PACH", "PHAR", "PHDC", "PHGC", "PHTV", "PIOH", "POUL", "PRCL", "PRDC", "PRMH",
    "QNBA", "QNBE", "RACC", "RAKT", "RAYA", "RKAZ", "RMDA", "ROTO", "RREI", "RTVC",
    "RUBX", "SAIB", "SAUD", "SCEM", "SCFM", "SCTS", "SDTI", "SEIG", "SEIGA", "SIMO",
    "SIPC", "SKPC", "SMFR", "SMPP", "SNFC", "SPHT", "SPIN", "SPMD", "SRWA", "SUGR",
    "SVCE", "SWDY", "TALM", "TANM", "TAQA", "TMGH", "TORA", "TRTO", "TWSA", "TYCN",
    "UASG", "UBEE", "UEFM", "UEGC", "UNIP", "UNIT", "UPMS", "UTOP", "VALU", "VERT",
    "VLMR", "VLMRA", "WCDF", "WKOL", "ZEOT", "ZMID",
)

_POPULAR_TASI_FALLBACK = [
    ("2222", "Saudi Aramco", "أرامكو السعودية"),
    ("1120", "Al Rajhi Bank", "مصرف الراجحي"),
    ("1180", "Saudi National Bank", "البنك الأهلي السعودي"),
    ("7010", "stc", "إس تي سي (الاتصالات السعودية)"),
    ("2010", "SABIC", "سابك"),
    ("1211", "Maaden", "معادن"),
    ("2082", "ACWA Power", "أكوا باور"),
    ("1150", "Alinma Bank", "مصرف الإنماء"),
    ("4013", "Dr. Sulaiman Al Habib", "سليمان الحبيب"),
    ("2280", "Almarai", "المراعي"),
    ("7203", "Elm", "علم"),
    ("4190", "Jarir", "جرير"),
]

_SECTOR_AR_MAP: Dict[str, str] = {
    "finance": "بنوك وخدمات مالية",
    "regional banks": "بنوك",
    "investment banks/brokers": "خدمات مالية غير مصرفية",
    "real estate development": "عقارات وإنشاءات",
    "homebuilding": "عقارات وإنشاءات",
    "process industries": "صناعات تحويلية وأسمدة",
    "chemicals: agricultural": "أسمدة وكيماويات",
    "chemicals: major diversified": "بتروكيماويات وكيماويات",
    "producer manufacturing": "صناعات هندسية وكهربائية",
    "health technology": "رعاية صحية وأدوية",
    "pharmaceuticals: major": "رعاية صحية وأدوية",
    "health services": "مستشفيات وخدمات طبية",
    "consumer non-durables": "أغذية ومشروبات ومطاحن",
    "food: major diversified": "أغذية ومشروبات",
    "food: meat/fish/dairy": "أغذية ودواجن وألبان",
    "technology services": "تكنولوجيا ومدفوعات رقمية",
    "communications": "اتصالات وتكنولوجيا",
    "energy minerals": "بترول وطاقة",
    "non-energy minerals": "مواد بناء، أسمنت وتعدين",
    "construction materials": "مواد بناء وأسمنت",
    "transportation": "نقل وشحن ولوجستيات",
    "consumer services": "سياحة وخدمات",
    "commercial services": "مقاولات وخدمات تجارية",
    "distribution services": "تجارة وتوزيع",
    "retail trade": "تجارة وتجزئة",
    "consumer durables": "سلع معمرة وعقارات",
    "utilities": "طاقة ومرافق",
    "electric utilities": "طاقة ومرافق",
    "energy": "بترول وطاقة",
    "integrated oil": "بترول وطاقة",
    "banks": "بنوك",
    "major banks": "بنوك",
    "materials": "مواد أساسية وبتروكيماويات",
    "health care": "رعاية صحية وأدوية",
    "real estate": "عقارات وإنشاءات",
    "telecommunication services": "اتصالات وتكنولوجيا",
    "information technology": "تكنولوجيا ومدفوعات رقمية",
    "industrials": "صناعات هندسية وكهربائية",
    "consumer staples": "أغذية ومشروبات",
    "consumer discretionary": "تجارة وتجزئة",
}

_NEWS_SECTOR_MAP: Dict[str, Dict[str, str]] = {
    "bank": {"ar": "بنوك", "en": "Banks"},
    "banking": {"ar": "بنوك", "en": "Banks"},
    "financial": {"ar": "خدمات مالية", "en": "Financial Services"},
    "finance": {"ar": "خدمات مالية", "en": "Financial Services"},
    "real estate": {"ar": "عقارات وتطوير", "en": "Real Estate"},
    "homebuilding": {"ar": "عقارات وتطوير", "en": "Real Estate"},
    "housing": {"ar": "عقارات وتطوير", "en": "Real Estate"},
    "construction": {"ar": "عقارات وتطوير", "en": "Real Estate"},
    "development": {"ar": "عقارات وتطوير", "en": "Real Estate"},
    "pharma": {"ar": "أدوية ورعاية صحية", "en": "Healthcare & Pharma"},
    "pharmaceutical": {"ar": "أدوية ورعاية صحية", "en": "Healthcare & Pharma"},
    "health": {"ar": "أدوية ورعاية صحية", "en": "Healthcare & Pharma"},
    "food": {"ar": "أغذية ومشروبات", "en": "Food & Beverages"},
    "beverage": {"ar": "أغذية ومشروبات", "en": "Food & Beverages"},
    "consumer non-durables": {"ar": "أغذية ومشروبات", "en": "Food & Beverages"},
    "agriculture": {"ar": "زراعة واستصلاح", "en": "Agriculture"},
    "agricultural": {"ar": "زراعة واستصلاح", "en": "Agriculture"},
    "farming": {"ar": "زراعة واستصلاح", "en": "Agriculture"},
    "reclamation": {"ar": "زراعة واستصلاح", "en": "Agriculture"},
    "materials": {"ar": "مواد أساسية ومقاولات", "en": "Basic Materials"},
    "building": {"ar": "مواد أساسية ومقاولات", "en": "Basic Materials"},
    "cement": {"ar": "مواد أساسية ومقاولات", "en": "Basic Materials"},
    "steel": {"ar": "مواد أساسية ومقاولات", "en": "Basic Materials"},
    "mining": {"ar": "مواد أساسية ومقاولات", "en": "Basic Materials"},
    "telecom": {"ar": "اتصالات وتكنولوجيا", "en": "Telecom & Tech"},
    "telecommunications": {"ar": "اتصالات وتكنولوجيا", "en": "Telecom & Tech"},
    "communications": {"ar": "اتصالات وتكنولوجيا", "en": "Telecom & Tech"},
    "technology": {"ar": "اتصالات وتكنولوجيا", "en": "Telecom & Tech"},
    "tourism": {"ar": "سياحة وترفيه", "en": "Tourism & Leisure"},
    "travel": {"ar": "سياحة وترفيه", "en": "Tourism & Leisure"},
    "hotel": {"ar": "سياحة وترفيه", "en": "Tourism & Leisure"},
    "energy": {"ar": "طاقة وبترول", "en": "Energy & Oil"},
    "oil": {"ar": "طاقة وبترول", "en": "Energy & Oil"},
    "gas": {"ar": "طاقة وبترول", "en": "Energy & Oil"},
    "petroleum": {"ar": "طاقة وبترول", "en": "Energy & Oil"},
    "process industries": {"ar": "صناعات تحويلية", "en": "Process Industries"},
    "transportation": {"ar": "خدمات النقل والشحن", "en": "Transportation"},
    "consumer durables": {"ar": "سلع استهلاكية معمرة", "en": "Consumer Durables"},
    "distribution services": {"ar": "خدمات لوجستية وتوزيع", "en": "Distribution & Logistics"},
    "consumer services": {"ar": "خدمات المستهلكين", "en": "Consumer Services"},
    "non-energy minerals": {"ar": "معادن وتعدين", "en": "Non-Energy Minerals"},
    "retail trade": {"ar": "تجارة التجزئة", "en": "Retail Trade"},
    "industrial services": {"ar": "خدمات صناعية ومقاولات", "en": "Industrial Services"},
    "producer manufacturing": {"ar": "التصنيع والإنتاج", "en": "Producer Manufacturing"},
    "utilities": {"ar": "المرافق والخدمات العامة", "en": "Utilities"},
    "commercial services": {"ar": "خدمات تجارية وأعمال", "en": "Commercial Services"},
    "miscellaneous": {"ar": "متنوع", "en": "Miscellaneous"},
    "health services": {"ar": "رعاية صحية ومستشفيات", "en": "Health Services"},
    "technology services": {"ar": "خدمات تكنولوجية وبرمجيات", "en": "Technology Services"},
}


def invalidate_public_offload_caches(tags: Iterable[str]) -> List[str]:
    """Clear HF RAM caches associated with refreshed daily cache tags."""
    cleared: List[str] = []
    seen: set[int] = set()
    for tag in tags:
        for name, cache_obj in _PUBLIC_TAG_TO_CACHES.get(tag, ()):
            if id(cache_obj) not in seen:
                cache_obj.clear()
                seen.add(id(cache_obj))
                cleared.append(name)
    return cleared


def _daily_headers(tag: str) -> Dict[str, str]:
    return {
        "Cache-Control": "public, max-age=3600, s-maxage=604800, stale-while-revalidate=2592000",
        "Vercel-CDN-Cache-Control": "public, s-maxage=604800, stale-while-revalidate=2592000, stale-if-error=2592000",
        "Vercel-Cache-Tag": tag,
    }


def _private_headers(tag: Optional[str] = None) -> Dict[str, str]:
    h = {"Cache-Control": "private, no-store, max-age=0"}
    if tag:
        h["Vercel-Cache-Tag"] = tag
    return h


def _explicit_market_param(request: Request) -> bool:
    qp = request.query_params
    return ("market" in qp) or ("country" in qp) or ("exchange" in qp)


def _finite(val: Any) -> Optional[float]:
    if val is None or val == "" or isinstance(val, bool):
        return None
    try:
        num = float(val)
        return num if math.isfinite(num) else None
    except (TypeError, ValueError):
        return None


def _num(val: Any, default: float = 0.0) -> float:
    parsed = _finite(val)
    return parsed if parsed is not None else default


def _parse_json_obj(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return None
    return raw


def _valid_iso_ts(raw: Any) -> Optional[str]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    txt = raw.strip()
    try:
        parsed = datetime.fromisoformat(txt.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed <= datetime.now(timezone.utc):
            return parsed.isoformat().replace("+00:00", "Z")
    except Exception:
        return None
    return None


def _valid_iso_date(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    clean = raw.strip()[:10]
    if not _ISO_DATE_RE.match(clean):
        return None
    try:
        parsed = datetime.strptime(clean, "%Y-%m-%d")
        return clean if parsed.strftime("%Y-%m-%d") == clean else None
    except ValueError:
        return None


# ── Public Stock Directory & Snapshot ────────────────────────────────────────

def _fetch_egx_directory() -> List[Dict[str, Any]]:
    sb = get_primary_supabase()
    if sb is None:
        return [
            {
                "symbol": s,
                "name": CANONICAL_EGX_STOCK_NAMES.get(s, {}).get("name_en", s),
                "sector": CANONICAL_EGX_STOCK_NAMES.get(s, {}).get("sector", ""),
                "marketCap": None,
            }
            for s in _FALLBACK_EGX_SYMBOLS
        ]
    res = (
        sb.table("stock_fundamentals")
        .select("symbol,exchange,updated_at,data")
        .eq("exchange", "EGX")
        .order("symbol")
        .limit(501)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    by_sym: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.get("exchange") != "EGX" or not isinstance(row.get("symbol"), str):
            continue
        sym = row["symbol"].strip().upper()
        if not _EGX_SYMBOL_DIR_RE.match(sym):
            continue
        data = _parse_json_obj(row.get("data")) or {}
        if not isinstance(data, dict):
            data = {}
        updated_at = _valid_iso_ts(row.get("updated_at"))
        prev = by_sym.get(sym)
        if prev and (not updated_at or (prev.get("updatedAt") and prev["updatedAt"] >= updated_at)):
            continue
        cap = _finite(data.get("marketCap"))
        entry: Dict[str, Any] = {
            "symbol": sym,
            "name": str(data.get("name") or data.get("Name") or CANONICAL_EGX_STOCK_NAMES.get(sym, {}).get("name_en") or sym),
            "sector": str(data.get("sector") or data.get("Sector") or ""),
            "marketCap": cap,
        }
        if updated_at:
            entry["updatedAt"] = updated_at
        by_sym[sym] = entry
    if not by_sym:
        return [
            {
                "symbol": s,
                "name": CANONICAL_EGX_STOCK_NAMES.get(s, {}).get("name_en", s),
                "sector": CANONICAL_EGX_STOCK_NAMES.get(s, {}).get("sector", ""),
                "marketCap": None,
            }
            for s in _FALLBACK_EGX_SYMBOLS
        ]
    return [by_sym[k] for k in sorted(by_sym.keys())]


def _fetch_tasi_directory() -> List[Dict[str, Any]]:
    sb = get_market_supabase("tasi")
    if sb is None:
        return [
            {
                "symbol": sym,
                "name": name_en,
                "nameAr": name_ar,
                "sector": "",
                "marketCap": None,
                "exchange": "TADAWUL",
                "currency": "SAR",
            }
            for sym, name_en, name_ar in _POPULAR_TASI_FALLBACK
        ]

    def _q_funds():
        return (
            sb.table("stock_fundamentals")
            .select("symbol,exchange,updated_at,data")
            .eq("exchange", "TADAWUL")
            .order("symbol")
            .limit(1000)
            .execute()
        )

    def _q_stocks():
        try:
            return (
                sb.table("stocks")
                .select("symbol,exchange,name,name_ar,sector,currency")
                .eq("exchange", "TADAWUL")
                .order("symbol")
                .limit(1000)
                .execute()
            )
        except Exception:
            return (
                sb.table("stocks")
                .select("symbol,exchange,name,sector")
                .eq("exchange", "TADAWUL")
                .order("symbol")
                .limit(1000)
                .execute()
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_funds = pool.submit(_q_funds)
        f_stocks = pool.submit(_q_stocks)
        fund_rows = getattr(f_funds.result(), "data", None) or []
        stock_rows = getattr(f_stocks.result(), "data", None) or []

    by_sym: Dict[str, Dict[str, Any]] = {}
    for row in [*stock_rows, *fund_rows]:
        raw_sym = str(row.get("symbol") or "").strip().upper()
        base_sym = re.sub(r"\.(SR|SA|TADAWUL)$", "", raw_sym)
        if not base_sym or not is_saudi_symbol(base_sym):
            continue
        data = _parse_json_obj(row.get("data")) or {}
        if not isinstance(data, dict):
            data = {}
        existing = by_sym.get(base_sym) or {}
        name_en = str(row.get("name") or data.get("name") or data.get("Name") or "").strip()
        name_ar = str(row.get("name_ar") or data.get("name_ar") or SAUDI_STOCK_NAMES_AR.get(base_sym) or "").strip()
        sector = str(row.get("sector") or data.get("sector") or data.get("Sector") or "").strip()
        cap = _finite(data.get("marketCap"))
        updated_at = _valid_iso_ts(row.get("updated_at")) or existing.get("updatedAt")
        entry: Dict[str, Any] = {
            "symbol": base_sym,
            "name": name_en or name_ar or existing.get("name") or base_sym,
            "sector": sector or existing.get("sector") or "",
            "marketCap": cap if cap is not None else existing.get("marketCap"),
            "exchange": "TADAWUL",
            "currency": str(row.get("currency") or existing.get("currency") or "SAR"),
        }
        if name_ar or existing.get("nameAr"):
            entry["nameAr"] = name_ar or existing.get("nameAr")
        if updated_at:
            entry["updatedAt"] = updated_at
        by_sym[base_sym] = entry

    if not by_sym:
        return [
            {
                "symbol": sym,
                "name": name_en,
                "nameAr": name_ar,
                "sector": "",
                "marketCap": None,
                "exchange": "TADAWUL",
                "currency": "SAR",
            }
            for sym, name_en, name_ar in _POPULAR_TASI_FALLBACK
        ]
    return [by_sym[k] for k in sorted(by_sym.keys())]


def _get_public_directory(market: str) -> List[Dict[str, Any]]:
    key = "tasi" if market == "tasi" else "egx"
    found, cached = _PUBLIC_DIR_CACHE.get(key)
    if found:
        return cached
    data = _PUBLIC_DIR_SF.do(key, lambda: _fetch_tasi_directory() if key == "tasi" else _fetch_egx_directory())
    _PUBLIC_DIR_CACHE.set(key, data, ttl=_RUN_TO_RUN_TTL)
    return data


@router.get("/api/public/stock-directory")
async def api_public_stock_directory(market: str = Query(default="egx")):
    resolved = "tasi" if market.strip().lower() in ("tasi", "tadawul", "sa", "saudi") else "egx"
    stocks = _get_public_directory(resolved)
    return JSONResponse(
        {"market": resolved, "stocks": stocks},
        headers=_daily_headers("daily-symbols"),
    )


def _select_related_links(directory: List[Dict[str, Any]], symbol: str, sector: str) -> Dict[str, Any]:
    other = [s for s in directory if s.get("symbol") != symbol]
    sec_l = sector.strip().lower()
    peers = [s for s in other if sec_l and str(s.get("sector") or "").strip().lower() == sec_l] if sec_l else []
    pool = peers if peers else ([s for s in other if s["symbol"] > symbol] + [s for s in other if s["symbol"] < symbol])
    basis = "sector" if peers else "directory"
    return {
        "basis": basis,
        "stocks": [{"symbol": s["symbol"], "name": s["name"]} for s in pool[:7]],
    }


def _load_gcc_stock_page_data(clean_sym: str, exchanges: List[str]) -> Dict[str, Any]:
    sb = get_market_supabase("uae")
    if sb is None:
        return {
            "snapshot": {"fundamentals": None, "latestPrice": None, "latestTech": None, "latestScan": None, "historicalPrices": []},
            "related": {"basis": "directory", "stocks": []},
        }

    def _read_gcc_meta():
        try:
            res = (
                sb.table("stocks")
                .select("symbol,exchange,country,currency,name,name_ar,sector,updated_at")
                .in_("exchange", exchanges)
                .eq("symbol", clean_sym)
                .limit(1)
                .execute()
            )
            return getattr(res, "data", None) or []
        except Exception:
            return []

    def _read_gcc_peers():
        try:
            res = (
                sb.table("stocks")
                .select("symbol,exchange,name,name_ar,sector")
                .in_("exchange", exchanges)
                .eq("is_active", True)
                .limit(120)
                .execute()
            )
            return getattr(res, "data", None) or []
        except Exception:
            return []

    def _read_gcc_table(table: str, fields: str, order_col: str, limit: int):
        try:
            res = (
                sb.table(table)
                .select(fields)
                .in_("exchange", exchanges)
                .eq("symbol", clean_sym)
                .order(order_col, desc=True)
                .limit(limit)
                .execute()
            )
            return getattr(res, "data", None) or []
        except Exception:
            return []

    def _read_gcc_disclosures():
        try:
            res = (
                sb.table("egx_disclosures")
                .select("id,symbol,disclosure_type,disclosure_date,title,ai_summary,sentiment")
                .eq("symbol", clean_sym)
                .order("disclosure_date", desc=True)
                .limit(3)
                .execute()
            )
            return getattr(res, "data", None) or []
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=6) as pool:
        f_meta = pool.submit(_read_gcc_meta)
        f_price = pool.submit(_read_gcc_table, "stock_prices", "symbol,exchange,date,open,high,low,close,volume,updated_at", "date", 1)
        f_tech = pool.submit(
            _read_gcc_table,
            "stock_technical_indicators",
            "symbol,exchange,date,close,change_pct,adx_14,rsi_14,macd,macd_signal,ema_50,ema_200,sma_50,sma_200,calculated_at",
            "date",
            1,
        )
        f_hist = pool.submit(_read_gcc_table, "stock_prices", "date,open,high,low,close,volume", "date", 30)
        f_peers = pool.submit(_read_gcc_peers)
        f_disc = pool.submit(_read_gcc_disclosures)
        meta_rows = f_meta.result()
        price_rows = f_price.result()
        tech_rows = f_tech.result()
        hist_rows = f_hist.result()
        peer_rows = f_peers.result()
        disc_rows = f_disc.result()

    stock_row = meta_rows[0] if meta_rows else None
    latest_price = price_rows[0] if price_rows else None
    latest_tech = tech_rows[0] if tech_rows else None

    if latest_price is None or len(hist_rows) < 10:
        try:
            from api.saudi_storage_history import load_storage_symbol_bars, merge_bars_storage_with_live

            cand_exchanges = (
                [str(stock_row.get("exchange")).upper()]
                if (stock_row and stock_row.get("exchange"))
                else list(exchanges)
            )
            for cand_ex in cand_exchanges:
                st_bars = load_storage_symbol_bars(sb, cand_ex, clean_sym)
                if st_bars:
                    merged_bars = merge_bars_storage_with_live(st_bars, list(reversed(hist_rows)))
                    if merged_bars:
                        hist_rows = list(reversed(merged_bars[-30:]))
                        if latest_price is None:
                            lb = merged_bars[-1]
                            latest_price = {
                                "symbol": clean_sym,
                                "exchange": cand_ex,
                                "date": lb["date"],
                                "open": lb["open"],
                                "high": lb["high"],
                                "low": lb["low"],
                                "close": lb["close"],
                                "volume": lb["volume"],
                            }
                    break
        except Exception:
            pass

    if not stock_row and not latest_price:
        return {
            "snapshot": {"fundamentals": None, "latestPrice": None, "latestTech": None, "latestScan": None, "historicalPrices": [], "recentDisclosures": []},
            "related": {"basis": "directory", "stocks": []},
        }

    resolved_ex = str((stock_row or {}).get("exchange") or (latest_price or {}).get("exchange") or exchanges[0]).upper()
    country = (stock_row or {}).get("country") or ("Qatar" if resolved_ex == "QSE" else "Global" if resolved_ex == "COMMODITIES" else "UAE")
    currency = (stock_row or {}).get("currency") or ("QAR" if resolved_ex == "QSE" else "USD" if resolved_ex == "COMMODITIES" else "AED")
    name_en = str((stock_row or {}).get("name") or clean_sym)
    name_ar = str((stock_row or {}).get("name_ar") or clean_sym)
    sector = str((stock_row or {}).get("sector") or "")
    fundamentals = {
        "symbol": clean_sym,
        "exchange": resolved_ex,
        "updated_at": (stock_row or {}).get("updated_at") or (latest_price or {}).get("updated_at"),
        "data": {
            "country": country,
            "currency": currency,
            "exchange": resolved_ex,
            "name": name_en,
            "Name": name_en,
            "name_ar": name_ar,
            "sector": sector,
        },
    }
    peer_group = {"QSE"} if resolved_ex == "QSE" else ({"DFM", "ADX"} if resolved_ex in ("DFM", "ADX") else {resolved_ex})
    directory = [
        {"symbol": str(r.get("symbol") or "").upper(), "name": str(r.get("name_ar") or r.get("name") or r.get("symbol") or ""), "sector": str(r.get("sector") or "")}
        for r in peer_rows
        if r.get("symbol") and (not r.get("exchange") or str(r.get("exchange")).upper() in peer_group)
    ]
    return {
        "snapshot": {
            "fundamentals": fundamentals,
            "latestPrice": latest_price,
            "latestTech": latest_tech,
            "latestScan": None,
            "historicalPrices": list(reversed(hist_rows)),
            "recentDisclosures": disc_rows,
        },
        "related": _select_related_links(directory, clean_sym, sector),
    }


def _load_stock_page_data(symbol: str, market: str, explicit_exchange: Optional[str] = None) -> Dict[str, Any]:
    raw_upper = symbol.strip().upper()
    gcc_match = re.match(r"^([A-Z0-9._-]+)\.(DFM|ADX|QSE|COMMODITIES)$", raw_upper)
    if gcc_match:
        return _load_gcc_stock_page_data(gcc_match.group(1), [gcc_match.group(2)])

    clean_sym = re.sub(r"\.(SR|SA|TADAWUL)$", "", raw_upper)
    if explicit_exchange in ("DFM", "ADX", "QSE", "COMMODITIES"):
        return _load_gcc_stock_page_data(clean_sym, [explicit_exchange])
    if market in ("uae", "qatar"):
        return _load_gcc_stock_page_data(clean_sym, get_market_exchanges(market))

    is_saudi = market == "tasi"
    sb = get_market_supabase("tasi" if is_saudi else "egx")
    exchange = "TADAWUL" if is_saudi else "EGX"
    candidates = list(dict.fromkeys([clean_sym, f"{clean_sym}.SR"])) if is_saudi else [clean_sym]

    def _read_one(table: str, fields: str, order_col: str, limit: int):
        q = sb.table(table).select(fields).eq("exchange", exchange)
        q = q.in_("symbol", candidates) if is_saudi else q.eq("symbol", clean_sym)
        res = q.order(order_col, desc=True).limit(limit).execute()
        return getattr(res, "data", None) or []

    def _read_stock_meta():
        if not is_saudi:
            return []
        try:
            res = (
                sb.table("stocks")
                .select("symbol,exchange,name,name_ar,sector,currency")
                .eq("exchange", "TADAWUL")
                .in_("symbol", candidates)
                .limit(1)
                .execute()
            )
            return getattr(res, "data", None) or []
        except Exception:
            res = (
                sb.table("stocks")
                .select("symbol,exchange,name,sector")
                .eq("exchange", "TADAWUL")
                .in_("symbol", candidates)
                .limit(1)
                .execute()
            )
            return getattr(res, "data", None) or []

    def _read_recent_disclosures():
        try:
            q = sb.table("egx_disclosures").select("id,symbol,disclosure_type,disclosure_date,title,ai_summary,sentiment")
            q = q.in_("symbol", candidates) if is_saudi else q.eq("symbol", clean_sym)
            res = q.order("disclosure_date", desc=True).limit(3).execute()
            return getattr(res, "data", None) or []
        except Exception:
            return []

    if sb is None:
        directory = _get_public_directory(market)
        return {
            "snapshot": {
                "fundamentals": None,
                "latestPrice": None,
                "latestTech": None,
                "latestScan": None,
                "historicalPrices": [],
                "recentDisclosures": [],
            },
            "related": _select_related_links(directory, clean_sym, ""),
        }

    with ThreadPoolExecutor(max_workers=7) as pool:
        f_fund = pool.submit(_read_one, "stock_fundamentals", "symbol,exchange,data,updated_at", "updated_at", 1)
        f_price = pool.submit(_read_one, "stock_prices", "symbol,exchange,date,open,high,low,close,volume,updated_at", "date", 1)
        f_tech = pool.submit(
            _read_one,
            "stock_technical_indicators",
            "symbol,exchange,date,close,change_pct,adx_14,rsi_14,macd,macd_signal,ema_50,ema_200,sma_50,sma_200",
            "date",
            1,
        )
        f_hist = pool.submit(_read_one, "stock_prices", "date,open,high,low,close,volume", "date", 30)
        f_scan = pool.submit(_read_one, "scan_results", "symbol,exchange,created_at,precision,signal,top_reasons", "created_at", 1)
        f_meta = pool.submit(_read_stock_meta)
        f_disc = pool.submit(_read_recent_disclosures)
        fund_rows = f_fund.result()
        price_rows = f_price.result()
        tech_rows = f_tech.result()
        hist_rows = f_hist.result()
        scan_rows = f_scan.result()
        meta_rows = f_meta.result()
        disc_rows = f_disc.result()

    raw_fund = fund_rows[0] if fund_rows else None
    latest_price = price_rows[0] if price_rows else None
    latest_tech = tech_rows[0] if tech_rows else None
    latest_scan = scan_rows[0] if scan_rows else None
    stock_meta = meta_rows[0] if meta_rows else None

    if is_saudi and (latest_price is None or len(hist_rows) < 10):
        try:
            from api.saudi_storage_history import load_storage_symbol_bars, merge_bars_storage_with_live

            st_bars = load_storage_symbol_bars(sb, "TADAWUL", clean_sym)
            if st_bars:
                merged_bars = merge_bars_storage_with_live(st_bars, list(reversed(hist_rows)))
                if merged_bars:
                    hist_rows = list(reversed(merged_bars[-30:]))
                    if latest_price is None:
                        lb = merged_bars[-1]
                        latest_price = {
                            "symbol": clean_sym,
                            "exchange": "TADAWUL",
                            "date": lb["date"],
                            "open": lb["open"],
                            "high": lb["high"],
                            "low": lb["low"],
                            "close": lb["close"],
                            "volume": lb["volume"],
                        }
        except Exception:
            pass

    if not is_saudi and not raw_fund and not latest_price:
        gcc_res = _load_gcc_stock_page_data(clean_sym, ["DFM", "ADX", "QSE", "COMMODITIES"])
        if gcc_res["snapshot"]["fundamentals"] or gcc_res["snapshot"]["latestPrice"]:
            return gcc_res

    fundamentals = raw_fund
    if is_saudi and (raw_fund or stock_meta or latest_price):
        raw_data = dict(raw_fund.get("data") or {}) if raw_fund and isinstance(raw_fund.get("data"), dict) else {}
        known_ar = (stock_meta or {}).get("name_ar") or SAUDI_STOCK_NAMES_AR.get(clean_sym) or ""
        known_en = (stock_meta or {}).get("name") or raw_data.get("name") or raw_data.get("Name") or ""
        merged_data = {
            "country": "Saudi Arabia",
            "currency": (stock_meta or {}).get("currency") or "SAR",
            **raw_data,
        }
        if known_en:
            merged_data["name"] = known_en
            merged_data["Name"] = known_en
        if known_ar:
            merged_data["name_ar"] = known_ar
        if not raw_data.get("sector") and not raw_data.get("Sector") and (stock_meta or {}).get("sector"):
            merged_data["sector"] = stock_meta["sector"]
        fundamentals = {
            **(raw_fund or {"symbol": clean_sym, "exchange": "TADAWUL", "updated_at": None}),
            "exchange": "TADAWUL",
            "data": merged_data,
        }

    directory = _get_public_directory("tasi" if is_saudi else "egx")
    fund_data = (fundamentals or {}).get("data") or {}
    canonical_sec = "" if is_saudi else CANONICAL_EGX_STOCK_NAMES.get(clean_sym, {}).get("sector", "")
    sec = str(fund_data.get("sector") or fund_data.get("Sector") or canonical_sec or "")
    related = _select_related_links(directory, clean_sym, sec)

    return {
        "snapshot": {
            "fundamentals": fundamentals,
            "latestPrice": latest_price,
            "latestTech": latest_tech,
            "latestScan": latest_scan,
            "historicalPrices": list(reversed(hist_rows)),
            "recentDisclosures": disc_rows,
        },
        "related": related,
    }


@router.get("/api/public/stock-page-data")
async def api_public_stock_page_data(
    symbol: str = Query(default=""),
    market: str = Query(default=""),
    exchange: str = Query(default=""),
):
    clean = symbol.strip().upper()
    if not clean or not _SYMBOL_PARAM_RE.match(clean):
        return JSONResponse({"error": "Invalid symbol"}, status_code=400)
    ex_hint = exchange.strip().upper()
    if ex_hint and ex_hint not in ("EGX", "TADAWUL", "DFM", "ADX", "QSE", "COMMODITIES"):
        return JSONResponse({"error": "Invalid exchange"}, status_code=400)
    gcc_match = re.match(r"^([A-Z0-9._-]+)\.(DFM|ADX|QSE|COMMODITIES)$", clean)
    if gcc_match and not ex_hint:
        ex_hint = gcc_match.group(2)
    stripped = re.sub(r"\.(SR|SA|TADAWUL|DFM|ADX|QSE|COMMODITIES)$", "", clean)
    m_hint = market.strip().lower()
    if ex_hint == "QSE" or m_hint in ("qatar", "qse", "qa"):
        resolved = "qatar"
    elif ex_hint in ("DFM", "ADX", "COMMODITIES") or m_hint in ("uae", "dfm", "adx", "ae"):
        resolved = "uae"
    elif m_hint == "tasi" or is_saudi_symbol(clean) or bool(re.match(r"^\d{4}$", stripped)):
        resolved = "tasi"
    else:
        resolved = "egx"
    cache_key = f"{resolved}:{ex_hint}:{stripped if resolved in ('tasi', 'uae', 'qatar') else clean}"
    found, cached = _PUBLIC_STOCK_PAGE_CACHE.get(cache_key)
    if found:
        return JSONResponse(cached, headers=_daily_headers("daily-market-data"))
    payload = _PUBLIC_STOCK_PAGE_SF.do(cache_key, lambda: _load_stock_page_data(clean, resolved, ex_hint or None))
    _PUBLIC_STOCK_PAGE_CACHE.set(cache_key, payload, ttl=_RUN_TO_RUN_TTL)
    return JSONResponse(payload, headers=_daily_headers("daily-market-data"))


# ── Fair Value Report ────────────────────────────────────────────────────────

from api.fair_value_engine import (
    compute_unified_fair_value,
    default_sector_multiples as _default_sector_multiples,
    normalize_fundamentals_for_valuation as _normalize_fv_fundamentals,
    resolve_sector_ar as _resolve_sector_ar_unified,
)


def _resolve_sector_ar(symbol: str, raw_sector: Any, raw_industry: Any) -> str:
    return _resolve_sector_ar_unified(symbol, raw_sector, raw_industry)


def _median(values: List[float], fallback: float) -> float:
    if not values:
        return fallback
    s = sorted(values)
    mid = len(s) // 2
    return (s[mid - 1] + s[mid]) / 2.0 if len(s) % 2 == 0 else s[mid]


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _fmt_num(val: float) -> str:
    if val.is_integer():
        return str(int(val))
    return f"{val:.2f}".rstrip("0").rstrip(".")


def _compute_single_fair_value(
    *,
    symbol: str,
    close: float,
    fund_row: Optional[Dict[str, Any]],
    ind: Optional[Dict[str, Any]],
    sector_median_pe: float,
    sector_median_pb: float,
    market: str,
) -> Dict[str, Any]:
    return compute_unified_fair_value(
        symbol=symbol,
        close=close,
        fund_row=fund_row,
        ind=ind,
        sector_median_pe=sector_median_pe,
        sector_median_pb=sector_median_pb,
        market=market,
    )


_MARKET_CURRENCY_MAP = {
    "egx": "EGP",
    "tasi": "SAR",
    "uae": "AED",
    "qatar": "QAR",
}


def _build_fair_value_report(market: str) -> Dict[str, Any]:
    norm_market = market if market in _MARKET_CURRENCY_MAP else "egx"
    currency_code = _MARKET_CURRENCY_MAP[norm_market]
    sb = get_market_supabase(norm_market)
    exchanges = ["TADAWUL", "TASI"] if norm_market == "tasi" else get_market_exchanges(norm_market)
    if sb is None:
        return {
            "market": norm_market,
            "currencyCode": currency_code,
            "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "latestSessionDate": None,
            "summary": {"totalEvaluated": 0, "undervaluedCount": 0, "fairCount": 0, "overvaluedCount": 0, "fundamentalCoverageCount": 0},
            "sectors": [],
            "stocks": [],
        }

    def _q_funds():
        return (
            sb.table("stock_fundamentals")
            .select("symbol,name,name_ar,data,updated_at")
            .in_("exchange", exchanges)
            .limit(400)
            .execute()
        )

    def _q_ind():
        return (
            sb.table("stock_technical_indicators")
            .select("symbol,date,close,volume,ema_50,ema_200,sma_200,vwap_20,change_pct,rsi_14")
            .in_("exchange", exchanges)
            .order("date", desc=True)
            .limit(600)
            .execute()
        )

    def _q_stocks():
        cols = "symbol,name,name_ar" if norm_market == "egx" else "symbol,name,name_ar,sector"
        return (
            sb.table("stocks")
            .select(cols)
            .in_("exchange", exchanges)
            .eq("is_active", True)
            .limit(400)
            .execute()
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_f = pool.submit(_q_funds)
        f_i = pool.submit(_q_ind)
        f_s = pool.submit(_q_stocks)
        fund_rows = getattr(f_f.result(), "data", None) or []
        ind_rows = getattr(f_i.result(), "data", None) or []
        stock_rows = getattr(f_s.result(), "data", None) or []

    fund_map: Dict[str, Dict[str, Any]] = {}
    for row in fund_rows:
        sym = str(row.get("symbol") or "").strip().upper()
        if sym:
            fund_map[sym] = row
    for srow in stock_rows:
        sym = str(srow.get("symbol") or "").strip().upper()
        if not sym:
            continue
        if sym not in fund_map:
            fund_map[sym] = {
                "symbol": sym,
                "name": srow.get("name"),
                "name_ar": srow.get("name_ar"),
                "data": {"sector": srow.get("sector"), "name": srow.get("name")},
            }

    sector_pes: Dict[str, List[float]] = {}
    sector_pbs: Dict[str, List[float]] = {}
    all_pes: List[float] = []
    all_pbs: List[float] = []
    seen_for_medians: set[str] = set()

    for ind in ind_rows:
        sym = str(ind.get("symbol") or "").strip().upper()
        close = _finite(ind.get("close"))
        if not sym or not close or close <= 0 or sym in seen_for_medians:
            continue
        seen_for_medians.add(sym)
        f_row = fund_map.get(sym) or {}
        raw_data = f_row.get("data") if isinstance(f_row.get("data"), dict) else {}
        if raw_data.get("isListed") is False:
            continue
        norm_data, _ = _normalize_fv_fundamentals(raw_data, close, symbol=sym, market=norm_market)
        sec_ar = _resolve_sector_ar(sym, norm_data.get("sector"), norm_data.get("industry"))
        eps = _finite(norm_data.get("eps"))
        bvps = _finite(norm_data.get("bookValuePerShare"))
        net_inc = _finite(norm_data.get("netIncome"))
        roe_v = _finite(norm_data.get("roe"))
        loss_mk = bool((eps is not None and eps <= 0) or (net_inc is not None and net_inc < 0) or (roe_v is not None and roe_v < 0))
        pe = (close / eps) if (not loss_mk and eps and eps > 0) else (_finite(norm_data.get("peRatio")) if not loss_mk else None)
        pb = (close / bvps) if (bvps and bvps > 0) else _finite(norm_data.get("pbRatio"))
        if pe is not None and 2.0 < pe <= 35.0:
            sector_pes.setdefault(sec_ar, []).append(pe)
            all_pes.append(pe)
        if not loss_mk and pb is not None and 0.30 < pb <= 8.0:
            sector_pbs.setdefault(sec_ar, []).append(pb)
            all_pbs.append(pb)

    max_pe_cap = 18.0 if norm_market == "tasi" else 13.5
    max_pb_cap = 3.0 if norm_market == "tasi" else 2.6
    global_pe = _clamp(_median(all_pes, 9.5), 7.0, max_pe_cap) if len(all_pes) >= 5 else (13.0 if norm_market == "tasi" else 9.5)
    global_pb = _clamp(_median(all_pbs, 1.75), 1.35, max_pb_cap) if len(all_pbs) >= 5 else (2.1 if norm_market == "tasi" else 1.75)

    items: List[Dict[str, Any]] = []
    latest_session: Optional[str] = None
    seen: set[str] = set()
    for ind in ind_rows:
        sym = str(ind.get("symbol") or "").strip().upper()
        close = _finite(ind.get("close"))
        if not sym or not close or close <= 0 or sym in seen:
            continue
        seen.add(sym)
        f_row = fund_map.get(sym) or {}
        data = f_row.get("data") if isinstance(f_row.get("data"), dict) else {}
        if data.get("isListed") is False:
            continue
        rdate = str(ind.get("date"))[:10] if ind.get("date") else None
        if rdate and (not latest_session or rdate > latest_session):
            latest_session = rdate
        sec_ar = _resolve_sector_ar(sym, data.get("sector"), data.get("industry"))
        def_pe, def_pb = _default_sector_multiples(sec_ar, norm_market)
        p_pes = sector_pes.get(sec_ar) or []
        p_pbs = sector_pbs.get(sec_ar) or []
        min_pe_floor = 8.5 if ("بنوك" in sec_ar and "غير مصرفية" not in sec_ar) else 7.0
        s_pe = round(_clamp(_median(p_pes, def_pe) if len(p_pes) >= 3 else def_pe, min_pe_floor, max_pe_cap), 2)
        s_pb = round(_clamp(_median(p_pbs, def_pb) if len(p_pbs) >= 3 else def_pb, 1.15, max_pb_cap), 2)
        items.append(
            _compute_single_fair_value(
                symbol=sym,
                close=close,
                fund_row=f_row,
                ind=ind,
                sector_median_pe=s_pe,
                sector_median_pb=s_pb,
                market=norm_market,
            )
        )

    items.sort(key=lambda x: (-x["upsidePct"], 0 if x["modelType"] == "graham_fundamental" else 1))
    return {
        "market": norm_market,
        "currencyCode": currency_code,
        "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "latestSessionDate": latest_session,
        "summary": {
            "totalEvaluated": len(items),
            "undervaluedCount": sum(1 for x in items if x["status"] == "undervalued"),
            "fairCount": sum(1 for x in items if x["status"] == "fair"),
            "overvaluedCount": sum(1 for x in items if x["status"] == "overvalued"),
            "fundamentalCoverageCount": sum(1 for x in items if x["modelType"] != "quant_vwap"),
        },
        "sectors": sorted({x["sectorAr"] for x in items}),
        "stocks": items,
    }


def _get_fair_value(market: str) -> Dict[str, Any]:
    key = market if market in _MARKET_CURRENCY_MAP else "egx"
    found, cached = _FAIR_VALUE_CACHE.get(key)
    if found:
        return cached
    report = _FAIR_VALUE_SF.do(key, lambda: _build_fair_value_report(key))
    _FAIR_VALUE_CACHE.set(key, report, ttl=_RUN_TO_RUN_TTL)
    return report


@router.get("/api/public/fair-value-report")
@router.get("/api/market/fair-value")
async def api_public_fair_value(request: Request):
    market = resolve_request_market(request)
    report = _get_fair_value(market)
    headers = _daily_headers("daily-market-data") if _explicit_market_param(request) else _private_headers("daily-market-data")
    return JSONResponse(report, headers=headers)


# ── Reports Archive & Blog Sitemap Posts ────────────────────────────────────

def _load_reports_archive() -> List[Dict[str, Any]]:
    sb = get_primary_supabase()
    if sb is None:
        return []
    res = (
        sb.table("daily_social_reports")
        .select("session_date,kind,content,created_at,updated_at,evidence,job_run_id")
        .in_("kind", ["market", "accumulation"])
        .eq("status", "ready")
        .eq("validation->>ok", "true")
        .gte("session_date", "2026-10-04")
        .order("session_date", desc=True)
        .limit(2000)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return []
    job_ids = list({r.get("job_run_id") for r in rows if r.get("job_run_id")})
    if not job_ids:
        return []
    jobs_res = (
        sb.table("daily_job_runs")
        .select("id,status,job_type,started_at,steps")
        .in_("id", job_ids[:2000])
        .limit(2000)
        .execute()
    )
    jobs_by_id = {j.get("id"): j for j in (getattr(jobs_res, "data", None) or []) if j.get("id")}
    out: List[Dict[str, Any]] = []
    for r in rows:
        job = jobs_by_id.get(r.get("job_run_id"))
        if not job or job.get("status") != "completed" or job.get("job_type") != "daily_bot":
            continue
        if not str(r.get("content") or "").strip():
            continue
        steps_raw = _parse_json_obj(job.get("steps")) or []
        if not isinstance(steps_raw, list):
            continue
        steps = effective_daily_steps(steps_raw)
        statuses = {s.get("step"): s.get("status") for s in steps if s.get("step")}
        sync = next((s for s in steps if s.get("step") == "sync_prices"), None) or {}
        prices_ok = sync.get("status") == "success"
        if not prices_ok and sync.get("status") in ("failed", "partial"):
            details = str(sync.get("details") or "")
            m = re.search(r"(?:Synced|Recovered)\s+(\d+)\s*/\s*(\d+)", details)
            if m and int(m.group(2)) > 0 and (int(m.group(1)) / int(m.group(2))) >= 0.8:
                prices_ok = True
        try:
            started_str = str(job.get("started_at") or "").replace("Z", "+00:00")
            started_dt = datetime.fromisoformat(started_str)
            job_date = get_cairo_date_str(started_dt)
        except Exception:
            continue
        needed = "refresh_market_status" if r.get("kind") == "market" else "accumulation_scan"
        if job_date == r.get("session_date") and prices_ok and statuses.get("calculate_indicators") == "success" and statuses.get(needed) == "success":
            out.append({
                "session_date": r.get("session_date"),
                "kind": r.get("kind"),
                "content": r.get("content"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
                "evidence": r.get("evidence") if isinstance(r.get("evidence"), list) else [],
            })
    return out


@router.get("/api/public/reports-archive")
async def api_public_reports_archive():
    found, cached = _REPORTS_ARCHIVE_CACHE.get("all")
    if found:
        return JSONResponse({"reports": cached}, headers=_daily_headers("daily-public-reports"))
    reports = _REPORTS_ARCHIVE_SF.do("all", _load_reports_archive)
    _REPORTS_ARCHIVE_CACHE.set("all", reports, ttl=_RUN_TO_RUN_TTL)
    return JSONResponse({"reports": reports}, headers=_daily_headers("daily-public-reports"))


@router.get("/api/public/sitemap-posts")
async def api_public_sitemap_posts():
    found, cached = _SITEMAP_POSTS_CACHE.get("posts")
    if found:
        return JSONResponse({"posts": cached}, headers={"Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400"})

    def _fetch():
        sb = get_primary_supabase()
        if sb is None:
            return []
        res = (
            sb.table("shared_chat_posts")
            .select("slug,is_published,created_at,updated_at")
            .eq("is_published", True)
            .order("created_at", desc=True)
            .limit(1000)
            .execute()
        )
        return getattr(res, "data", None) or []

    posts = _SITEMAP_POSTS_SF.do("posts", _fetch)
    _SITEMAP_POSTS_CACHE.set("posts", posts, ttl=3600.0)
    return JSONResponse({"posts": posts}, headers={"Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400"})


# ── Technical Scanner ────────────────────────────────────────────────────────

def _fetch_technical_dataset(market: str) -> Dict[str, List[Dict[str, Any]]]:
    sb = get_market_supabase(market)
    exchanges = get_market_exchanges(market)
    if sb is None:
        return {"stocks": [], "indicators": [], "fundamentals": [], "scanResults": []}

    def _q_stocks():
        for fields in ("symbol, name, name_ar, sector, industry", "symbol, name, name_ar, sector", "symbol, name, sector", "symbol"):
            try:
                res = sb.table("stocks").select(fields).in_("exchange", exchanges).eq("is_active", True).limit(1000).execute()
                return getattr(res, "data", None) or []
            except Exception:
                continue
        return []

    def _q_ind():
        fields_list = (
            "symbol, exchange, date, close, rsi_14, ema_20, ema_50, ema_200, atr_14, adx_14, stoch_k, stoch_d, volume, change_pct, vol_sma20, momentum_10, roc_12, macd, macd_signal, r_vol, vwap_20, rsi_divergence, macd_divergence, stoch_divergence, divergence_strength, divergence_periods, divergence_summary",
            "symbol, exchange, date, close, rsi_14, ema_20, ema_50, ema_200, atr_14, adx_14, stoch_k, stoch_d, volume, change_pct, volume_sma_20, momentum_10, roc_12, macd, macd_signal, r_vol, vwap_20, rsi_divergence, macd_divergence, stoch_divergence, divergence_strength, divergence_periods, divergence_summary",
            "symbol, exchange, date, close, rsi_14, ema_50, ema_200, atr_14, adx_14, stoch_k, stoch_d, volume, change_pct, volume_sma_20, momentum_10, roc_12, macd, macd_signal, r_vol, vwap_20",
            "symbol, exchange, date, close, rsi_14, ema_50, ema_200, volume, change_pct",
        )
        for f in fields_list:
            try:
                res = sb.table("stock_technical_indicators").select(f).in_("exchange", exchanges).order("date", desc=True).limit(1000).execute()
                return getattr(res, "data", None) or []
            except Exception:
                continue
        return []

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_st = pool.submit(_q_stocks)
        f_in = pool.submit(_q_ind)
        stocks = f_st.result()
        indicators = f_in.result()

    unique_syms = list({row.get("symbol") for row in indicators if row.get("symbol")})
    if not unique_syms:
        return {"stocks": stocks, "indicators": [], "fundamentals": [], "scanResults": []}

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_fu = pool.submit(lambda: getattr(sb.table("stock_fundamentals").select("symbol, name, fund_score, data").in_("exchange", exchanges).in_("symbol", unique_syms).limit(len(unique_syms) + 20).execute(), "data", None) or [])
        f_sc = pool.submit(lambda: getattr(sb.table("scan_results").select("symbol, precision").in_("exchange", exchanges).in_("symbol", unique_syms).order("created_at", desc=True).limit(min(len(unique_syms) * 3, 2000)).execute(), "data", None) or [])
        fundamentals = f_fu.result()
        scan_results = f_sc.result()

    return {"stocks": stocks, "indicators": indicators, "fundamentals": fundamentals, "scanResults": scan_results}


@router.post("/api/scan/technical")
async def api_scan_technical(request: Request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    market = resolve_request_market(request, body.get("market") or body.get("country") or body.get("exchange"))
    exchange = get_market_exchange(market)
    currency = _MARKET_CURRENCY_MAP.get(market, "EGP")
    limit = max(1, min(int(_num(body.get("limit"), 50)), 500))

    found, dataset = _TECH_DATASET_CACHE.get(market)
    if not found:
        dataset = _TECH_DATASET_SF.do(market, lambda: _fetch_technical_dataset(market))
        _TECH_DATASET_CACHE.set(market, dataset, ttl=_RUN_TO_RUN_TTL)

    indicators = dataset.get("indicators") or []
    if not indicators:
        return JSONResponse({"results": [], "scanned_count": 0}, headers=_private_headers())

    sorted_ind = sorted(indicators, key=lambda a: str(a.get("date") or ""), reverse=True)
    dedup: Dict[str, Dict[str, Any]] = {}
    for row in sorted_ind:
        k = f"{row.get('symbol')}-{row.get('exchange')}"
        if k not in dedup:
            dedup[k] = row

    stock_map = {s["symbol"]: s for s in (dataset.get("stocks") or []) if s.get("symbol")}
    fund_map = {f["symbol"]: f for f in (dataset.get("fundamentals") or []) if f.get("symbol")}
    scan_map = {s["symbol"]: _num(s.get("precision")) for s in (dataset.get("scanResults") or []) if s.get("symbol")}

    rsi_min = _finite(body.get("rsi_min"))
    rsi_max = _finite(body.get("rsi_max"))
    min_price = _finite(body.get("min_price"))
    above_ema50 = bool(body.get("above_ema50"))
    below_ema50 = bool(body.get("below_ema50"))
    above_ema200 = bool(body.get("above_ema200"))
    adx_min = _finite(body.get("adx_min"))
    adx_max = _finite(body.get("adx_max"))
    atr_min = _finite(body.get("atr_min"))
    atr_max = _finite(body.get("atr_max"))
    stoch_k_min = _finite(body.get("stoch_k_min"))
    stoch_k_max = _finite(body.get("stoch_k_max"))
    roc_min = _finite(body.get("roc_min"))
    roc_max = _finite(body.get("roc_max"))
    above_vwap20 = bool(body.get("above_vwap20"))
    volume_above_sma20 = bool(body.get("volume_above_sma20"))
    mcap_min = _finite(body.get("market_cap_min"))
    mcap_max = _finite(body.get("market_cap_max"))
    sector_f = str(body.get("sector") or "").strip().lower()
    industry_f = str(body.get("industry") or "").strip().lower()
    golden_cross = bool(body.get("golden_cross"))
    use_ai = bool(body.get("use_ai_filter"))
    min_ai_prec = _num(body.get("min_ai_precision"), 0.6)
    avoid_dist = bool(body.get("avoid_distribution"))
    req_acc = bool(body.get("require_accumulation"))
    cmf_min = _finite(body.get("cmf_min"))
    div_type = str(body.get("divergence_type") or "")
    div_ind = str(body.get("divergence_indicator") or "ANY").upper()
    div_min_str = _finite(body.get("divergence_min_strength"))

    scanned: List[Dict[str, Any]] = []
    for tech in dedup.values():
        close = _num(tech.get("close"))
        rsi = _num(tech.get("rsi_14"))
        ema20 = _num(tech.get("ema_20"))
        ema50 = _num(tech.get("ema_50"))
        ema200 = _num(tech.get("ema_200"))
        volume = _num(tech.get("volume"))
        atr14 = _num(tech.get("atr_14"))
        adx14 = _num(tech.get("adx_14"))
        stoch_k = _num(tech.get("stoch_k"))
        stoch_d = _num(tech.get("stoch_d"))
        mom10 = _num(tech.get("momentum_10"))
        roc12 = _num(tech.get("roc_12"))
        macd = _num(tech.get("macd"))
        macd_sig = _num(tech.get("macd_signal"))
        vol_sma20 = _num(tech.get("vol_sma20") if tech.get("vol_sma20") is not None else tech.get("volume_sma_20"))
        r_vol = _num(tech.get("r_vol"))
        chg_p = _num(tech.get("change_pct"))
        cmf_20 = _num(tech.get("cmf_20"))
        mm_acc = _num(tech.get("mm_accumulation"))
        mm_dist = _num(tech.get("mm_distribution"))
        dist_blocked = mm_dist > 0.5 or cmf_20 < -0.10
        dist_reason = "market_maker_distribution" if mm_dist > 0.5 else ("negative_money_flow" if cmf_20 < -0.10 else None)

        f_rec = fund_map.get(tech.get("symbol")) or {}
        f_data = f_rec.get("data") if isinstance(f_rec.get("data"), dict) else {}
        s_rec = stock_map.get(tech.get("symbol")) or {}
        name = (
            (s_rec.get("name_ar") or f_rec.get("name") or f_data.get("name") or s_rec.get("name") or tech.get("symbol"))
            if market != "egx"
            else (f_rec.get("name") or f_data.get("name") or s_rec.get("name") or tech.get("symbol"))
        )
        m_cap = _num(f_data.get("marketCap"))
        pe_r = _num(f_data.get("peRatio"))
        eps = _num(f_data.get("eps"))
        div_y = _num(f_data.get("dividendYield"))
        sec = str(f_data.get("sector") or s_rec.get("sector") or "")
        ind_str = str(f_data.get("industry") or s_rec.get("industry") or "")
        beta = _num(f_data.get("beta"))

        if rsi_min is not None and (tech.get("rsi_14") is None or rsi < rsi_min):
            continue
        if rsi_max is not None and (tech.get("rsi_14") is None or rsi > rsi_max):
            continue
        if min_price is not None and (tech.get("close") is None or close < min_price):
            continue
        if adx_min is not None and (tech.get("adx_14") is None or adx14 < adx_min):
            continue
        if adx_max is not None and (tech.get("adx_14") is None or adx14 > adx_max):
            continue
        if above_ema50 and close <= ema50:
            continue
        if below_ema50 and close >= ema50:
            continue
        if above_ema200 and close <= ema200:
            continue
        if atr_min is not None and atr14 < atr_min:
            continue
        if atr_max is not None and atr14 > atr_max:
            continue
        if stoch_k_min is not None and stoch_k < stoch_k_min:
            continue
        if stoch_k_max is not None and stoch_k > stoch_k_max:
            continue
        if roc_min is not None and roc12 < roc_min:
            continue
        if roc_max is not None and roc12 > roc_max:
            continue
        if above_vwap20 and tech.get("vwap_20") and close <= _num(tech.get("vwap_20")):
            continue
        if volume_above_sma20 and vol_sma20 > 0 and volume <= vol_sma20:
            continue
        if golden_cross and ema50 <= ema200:
            continue
        if mcap_min is not None and m_cap < mcap_min:
            continue
        if mcap_max is not None and m_cap > mcap_max:
            continue
        if sector_f and sector_f not in sec.lower():
            continue
        if industry_f and industry_f not in ind_str.lower():
            continue
        if avoid_dist and dist_blocked:
            continue
        if req_acc and mm_acc <= 0.5:
            continue
        if cmf_min is not None and cmf_20 < cmf_min:
            continue

        precision = scan_map.get(tech.get("symbol"))
        if use_ai and (precision is None or precision < min_ai_prec):
            continue

        if div_type and div_type != "NONE":
            to_check = ["rsi", "macd", "stoch"] if div_ind in ("ANY", "") else [div_ind.lower()]
            has_div = False
            for ind_name in to_check:
                val = tech.get(f"{ind_name}_divergence") or "NONE"
                if (div_type == "ANY" and val != "NONE") or val == div_type:
                    has_div = True
            if not has_div:
                continue
            if div_min_str is not None and _num(tech.get("divergence_strength")) < div_min_str:
                continue

        trend_pts = 0.0
        if close > 0 and ema50 > 0 and ema200 > 0:
            if ema20 > 0 and close > ema20 and ema20 > ema50 > ema200:
                trend_pts = 3.0
            elif close > ema50 > ema200:
                trend_pts = 2.5
            elif close > ema50 and close > ema200:
                trend_pts = 2.0
            elif close > ema50:
                trend_pts = 1.5
            elif close > ema200:
                trend_pts = 1.0
            if ema50 > ema200:
                trend_pts = min(3.0, trend_pts + 0.5)

        calc_rvol = r_vol if r_vol > 0 else (volume / vol_sma20 if vol_sma20 > 0 and volume > 0 else 0.0)
        vol_pts = 2.5 if calc_rvol >= 3.0 else (2.0 if calc_rvol >= 2.0 else (1.5 if calc_rvol >= 1.5 else (1.0 if calc_rvol >= 1.2 else (0.5 if calc_rvol >= 0.8 else 0.0))))

        eff_mom = roc12 if abs(roc12) > 0 else mom10
        mom_pts = 1.0 if eff_mom > 0.05 else (0.75 if eff_mom > 0.02 else (0.5 if eff_mom > 0 else 0.0))
        if macd > macd_sig and macd > 0:
            mom_pts += 1.0
        elif macd > macd_sig:
            mom_pts += 0.5
        elif macd > 0:
            mom_pts += 0.25
        mom_pts = min(2.0, mom_pts)

        adx_pts = 1.5 if adx14 >= 50 else (1.25 if adx14 >= 35 else (1.0 if adx14 >= 25 else (0.5 if adx14 >= 20 else 0.0)))
        rsi_pts = 1.0 if rsi >= 70 else (0.75 if rsi >= 55 else (0.5 if rsi >= 45 else (0.25 if rsi >= 30 else 0.0)))
        raw_t = trend_pts + vol_pts + mom_pts + adx_pts + rsi_pts
        if mm_dist > 0.5:
            raw_t -= 3.0
        elif cmf_20 < -0.05:
            raw_t -= 1.5
        if mm_acc > 0.5:
            raw_t += 1.0
        elif cmf_20 > 0.10:
            raw_t += 0.5
        t_score = int(round(min(10.0, max(0.0, raw_t))))

        f_val = (3 if 0 < pe_r <= 15 else (2 if pe_r <= 25 else (1 if pe_r <= 40 else 0))) + (3 if eps > 1 else (2 if eps > 0 else (1 if eps > -0.5 else 0))) + (2 if div_y > 3 else (1 if div_y > 1 else 0)) + (2 if m_cap > 10_000_000_000 else (1 if m_cap > 1_000_000_000 else 0))
        f_score = int(round(min(10, max(1, f_val))))

        s_val = 5 + (2 if mom10 > 0.03 else (1 if mom10 > 0 else (-2 if mom10 < -0.03 else (-1 if mom10 < 0 else 0)))) + (2 if rsi > 70 else (1 if rsi > 55 else (-2 if rsi < 25 else (-1 if rsi < 40 else 0)))) + (2 if calc_rvol > 2.0 else (1 if calc_rvol > 1.3 else (-1 if calc_rvol < 0.5 else 0))) + (1 if adx14 > 40 else 0) + (1 if macd > macd_sig and macd > 0 else 0)
        s_score = int(round(min(10, max(1, s_val))))

        ai_score = None
        if precision is not None:
            denom = max(0.01, 1.0 - min_ai_prec)
            ai_score = int(round(min(max(6 + (precision - min_ai_prec) / denom * 4, 6), 10)))

        dt_str = tech.get("date")
        year_val = int(str(dt_str)[:4]) if dt_str and str(dt_str)[:4].isdigit() else None
        item: Dict[str, Any] = {
            "symbol": tech.get("symbol"),
            "exchange": tech.get("exchange") or exchange,
            "currency": currency,
            "name": name,
            "date": dt_str,
            "year": year_val,
            "last_close": close,
            "rsi": rsi,
            "volume": volume,
            "ema50": ema50,
            "ema200": ema200,
            "momentum": mom10,
            "atr14": atr14,
            "adx14": adx14,
            "stoch_k": stoch_k,
            "stoch_d": stoch_d,
            "change_p": chg_p,
            "market_cap": m_cap,
            "pe_ratio": pe_r,
            "eps": eps,
            "dividend_yield": div_y,
            "sector": sec or None,
            "industry": ind_str or None,
            "beta": beta or None,
            "ai_precision": precision or None,
            "ai_signal": "BUY" if precision else None,
            "logo_url": f_data.get("logoUrl") or None,
            "ai_score": ai_score,
            "fundamental_score": f_score,
            "technical_score": t_score,
            "sentiment_score": s_score,
            "vwap20": _num(tech.get("vwap_20")) if tech.get("vwap_20") else 0,
            "cmf_20": cmf_20,
            "mm_accumulation": mm_acc > 0.5,
            "mm_distribution": mm_dist > 0.5,
            "distribution_blocked": dist_blocked,
            "distribution_reason": dist_reason,
            "rsi_divergence": tech.get("rsi_divergence") or "NONE",
            "macd_divergence": tech.get("macd_divergence") or "NONE",
            "stoch_divergence": tech.get("stoch_divergence") or "NONE",
            "divergence_strength": _num(tech.get("divergence_strength")),
            "divergence_periods": _num(tech.get("divergence_periods")),
            "divergence_summary": tech.get("divergence_summary") or None,
        }
        if s_rec.get("name_ar"):
            item["name_ar"] = s_rec["name_ar"]
        scanned.append(item)
        if len(scanned) >= limit:
            break

    return JSONResponse({"results": scanned, "scanned_count": len(indicators)}, headers=_private_headers("daily-market-data"))


# ── News Scan & Stats ────────────────────────────────────────────────────────

def _normalize_news_sector(raw_sector: str) -> Dict[str, str]:
    if not raw_sector:
        return {"ar": "أخرى", "en": "Other"}
    low = raw_sector.lower()
    for key in sorted(_NEWS_SECTOR_MAP.keys(), key=len, reverse=True):
        val = _NEWS_SECTOR_MAP[key]
        if low == val["en"].lower() or low == val["ar"] or key in low:
            return val
    return {"ar": "أخرى", "en": "Other"}


def _get_symbol_sectors_for_news(market: str) -> Dict[str, Dict[str, str]]:
    found, cached = _SECTOR_CACHE.get(market)
    if found:
        return cached

    def _load():
        sb = get_market_supabase(market)
        if sb is None:
            return {}
        exchanges = get_market_exchanges(market)
        fund_rows = getattr(sb.table("stock_fundamentals").select("symbol,data").in_("exchange", exchanges).limit(1000).execute(), "data", None) or []
        meta_rows = (
            getattr(sb.table("stocks").select("symbol,sector").in_("exchange", exchanges).limit(1000).execute(), "data", None) or []
            if market in ("tasi", "uae", "qatar")
            else []
        )
        mapping: Dict[str, Dict[str, str]] = {}
        for row in fund_rows:
            sym = str(row.get("symbol") or "").upper()
            if not sym:
                continue
            parsed = _parse_json_obj(row.get("data")) or {}
            sec = (parsed.get("sector") or parsed.get("Sector") or parsed.get("sector_ar") or parsed.get("industry") or "Other") if isinstance(parsed, dict) else "Other"
            mapping[sym] = _normalize_news_sector(str(sec))
        for row in meta_rows:
            sym = str(row.get("symbol") or "").upper()
            if not sym or not row.get("sector"):
                continue
            if sym in mapping and mapping[sym]["en"] != "Other":
                continue
            mapping[sym] = _normalize_news_sector(str(row["sector"]))
        return mapping

    data = _SECTOR_SF.do(market, _load)
    _SECTOR_CACHE.set(market, data, ttl=_RUN_TO_RUN_TTL)
    return data


def _load_news_rows(market: str, exact: str, month: str, period: str) -> List[Dict[str, Any]]:
    cache_key = f"{market}:{exact}:{month}:{period}"
    found, cached = _NEWS_CACHE.get(cache_key)
    if found:
        return cached

    def _fetch():
        sb = get_market_supabase(market)
        if sb is None:
            return []
        exchanges = get_market_exchanges(market)
        tz_hours = 4 if market == "uae" else (3 if market in ("tasi", "qatar") else 2)
        tz_offset = timezone(timedelta(hours=tz_hours))
        today = datetime.now(tz_offset).strftime("%Y-%m-%d")
        start = exact or (f"{month}-01" if month else today)
        end = exact or today
        if not exact and month:
            y, m = map(int, month.split("-"))
            next_m = datetime(y + (m // 12), (m % 12) + 1, 1) - timedelta(days=1)
            end = next_m.strftime("%Y-%m-%d")
        elif not exact:
            base = datetime.strptime(today, "%Y-%m-%d")
            delta_days = 90 if period == "3m" else (30 if period in ("1m", "15d", "") else 30)
            start = (base - timedelta(days=delta_days)).strftime("%Y-%m-%d")

        cur = datetime.strptime(start[:7] + "-01", "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        rows: List[Dict[str, Any]] = []
        while cur <= end_dt:
            nxt = datetime(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)
            from_s = cur.strftime("%Y-%m-%d")
            until_s = nxt.strftime("%Y-%m-%d")
            offset = 0
            while True:
                res = (
                    sb.table("stock_news_sentiment")
                    .select("id,symbol,exchange,date,sentiment_score,news_count,headlines,sources")
                    .in_("exchange", exchanges)
                    .gt("news_count", 0)
                    .gte("date", from_s)
                    .lt("date", until_s)
                    .order("date", desc=True)
                    .order("id", desc=False)
                    .range(offset, offset + 499)
                    .execute()
                )
                batch = getattr(res, "data", None) or []
                rows.extend(batch)
                if len(batch) < 500:
                    break
                offset += 500
            cur = nxt

        in_range = [r for r in rows if start <= str(r.get("date") or "") <= end]
        if not exact and not month and period in ("", "15d"):
            dates_15 = set(sorted({str(r.get("date")) for r in in_range if r.get("date")})[-15:])
            in_range = [r for r in in_range if str(r.get("date")) in dates_15]
        return in_range

    rows = _NEWS_SF.do(cache_key, _fetch)
    _NEWS_CACHE.set(cache_key, rows, ttl=_RUN_TO_RUN_TTL)
    return rows


def _news_label(score: float) -> str:
    return "positive" if score > 0.15 else ("negative" if score < -0.15 else "neutral")


@router.get("/api/scan/news")
async def api_scan_news(request: Request):
    qp = request.query_params
    market = resolve_request_market(request)
    exact = qp.get("date") or ""
    month = qp.get("month") or ""
    if (exact and not _ISO_DATE_RE.match(exact)) or (month and not _ISO_MONTH_RE.match(month)):
        return JSONResponse({"data": [], "total": 0}, status_code=400)
    period = qp.get("period") or "15d"
    limit = max(1, min(int(_num(qp.get("limit"), 20)), 100))
    offset = max(0, int(_num(qp.get("offset"), 0)))
    sentiment = qp.get("sentiment") or "all"
    sector = qp.get("sector") or ""
    search = (qp.get("search") or "").strip().upper()
    sort_by = qp.get("sort") or "newest"

    rows = list(_load_news_rows(market, exact, month, period))
    if search:
        rows = [r for r in rows if search in str(r.get("symbol") or "").upper()]
    if sector:
        sec_map = _get_symbol_sectors_for_news(market)
        sym_set = {s for s, val in sec_map.items() if val["en"] == sector or val["ar"] == sector}
        rows = [r for r in rows if str(r.get("symbol") or "").upper() in sym_set]
    if sentiment != "all":
        rows = [r for r in rows if _news_label(_num(r.get("sentiment_score"))) == sentiment]

    if sort_by == "highest_sent":
        rows.sort(key=lambda r: (-_num(r.get("sentiment_score")), str(r.get("symbol") or ""), int(r.get("id") or 0)))
    elif sort_by == "lowest_sent":
        rows.sort(key=lambda r: (_num(r.get("sentiment_score")), str(r.get("symbol") or ""), int(r.get("id") or 0)))
    elif sort_by == "oldest":
        rows.sort(key=lambda r: (str(r.get("date") or ""), str(r.get("symbol") or ""), int(r.get("id") or 0)))
    else:
        rows.sort(key=lambda r: str(r.get("date") or ""), reverse=True)

    total = len(rows)
    items = []
    for row in rows[offset : offset + limit]:
        sc = _num(row.get("sentiment_score"))
        hl = row.get("headlines") if isinstance(row.get("headlines"), list) else []
        items.append({
            "id": row.get("id"),
            "symbol": row.get("symbol"),
            "exchange": row.get("exchange"),
            "date": row.get("date"),
            "sentiment_score": sc,
            "sentiment_label": _news_label(sc),
            "news_count": row.get("news_count") if isinstance(row.get("news_count"), int) else len(hl),
            "headlines": hl,
            "sources": row.get("sources") if isinstance(row.get("sources"), list) else [],
        })
    headers = _daily_headers("daily-news-data") if _explicit_market_param(request) else _private_headers("daily-news-data")
    return JSONResponse({"data": items, "total": total}, headers=headers)


@router.get("/api/scan/news/stats")
async def api_scan_news_stats(request: Request):
    qp = request.query_params
    market = resolve_request_market(request)
    exact = qp.get("date") or ""
    month = qp.get("month") or ""
    if (exact and not _ISO_DATE_RE.match(exact)) or (month and not _ISO_MONTH_RE.match(month)):
        return JSONResponse({"error": "Invalid date/month"}, status_code=400)
    period = qp.get("period") or "15d"
    search = (qp.get("search") or "").strip().upper()
    req_sector = qp.get("sector") or ""

    sec_map = _get_symbol_sectors_for_news(market)
    news_rows = _load_news_rows(market, exact, month, period)
    if search:
        news_rows = [r for r in news_rows if search in str(r.get("symbol") or "").upper()]

    pos = neg = neu = 0
    sector_agg: Dict[str, Dict[str, Any]] = {}
    date_agg: Dict[str, Dict[str, Any]] = {}

    for row in news_rows:
        sym = str(row.get("symbol") or "").upper()
        sc = _num(row.get("sentiment_score"))
        cnt = int(_num(row.get("news_count"), 1) or 1)
        dt = row.get("date")
        if sc > 0.15:
            pos += 1
        elif sc < -0.15:
            neg += 1
        else:
            neu += 1
        sec = sec_map.get(sym, {"ar": "أخرى", "en": "Other"})
        sk = sec["en"]
        if sk not in sector_agg:
            sector_agg[sk] = {"ar": sec["ar"], "en": sec["en"], "totalScore": 0.0, "count": 0, "newsCount": 0, "stocks": {}}
        sa = sector_agg[sk]
        sa["totalScore"] += sc
        sa["count"] += 1
        sa["newsCount"] += cnt
        st = sa["stocks"].setdefault(sym, {"totalScore": 0.0, "count": 0, "newsCount": 0})
        st["totalScore"] += sc
        st["count"] += 1
        st["newsCount"] += cnt
        if dt:
            da = date_agg.setdefault(dt, {"totalScore": 0.0, "count": 0, "newsCount": 0})
            da["totalScore"] += sc
            da["count"] += 1
            da["newsCount"] += cnt

    sector_stats = sorted(
        [
            {
                "nameAr": s["ar"],
                "nameEn": s["en"],
                "averageSentiment": round(s["totalScore"] / s["count"], 2) if s["count"] > 0 else 0,
                "newsCount": s["newsCount"],
                "stocksCount": len(s["stocks"]),
                "stocks": sorted(
                    [
                        {
                            "symbol": sym,
                            "averageSentiment": round(st["totalScore"] / st["count"], 2) if st["count"] > 0 else 0,
                            "newsCount": st["newsCount"],
                        }
                        for sym, st in s["stocks"].items()
                    ],
                    key=lambda x: x["averageSentiment"],
                    reverse=True,
                ),
            }
            for s in sector_agg.values()
        ],
        key=lambda x: x["averageSentiment"],
        reverse=True,
    )

    slice_cnt = None if (exact or month) else (90 if period == "3m" else (30 if period == "1m" else 15))
    timeline_all = sorted(
        [
            {
                "date": d,
                "averageSentiment": round(v["totalScore"] / v["count"], 2) if v["count"] > 0 else 0,
                "newsCount": v["newsCount"],
            }
            for d, v in date_agg.items()
        ],
        key=lambda x: x["date"],
    )
    timeline_stats = timeline_all[-slice_cnt:] if slice_cnt else timeline_all

    sector_timeline = None
    if req_sector:
        match_sec = next((s for s in sector_agg.values() if s["en"] == req_sector or s["ar"] == req_sector), None)
        if match_sec:
            top_syms = [
                sym
                for sym, _ in sorted(match_sec["stocks"].items(), key=lambda kv: kv[1]["newsCount"], reverse=True)[:8]
            ]
            top_set = set(top_syms)
            by_date: Dict[str, Dict[str, Dict[str, float]]] = {}
            for row in news_rows:
                sym = str(row.get("symbol") or "").upper()
                dt = row.get("date")
                if sym not in top_set or not dt:
                    continue
                cell = by_date.setdefault(dt, {}).setdefault(sym, {"total": 0.0, "count": 0.0})
                cell["total"] += _num(row.get("sentiment_score"))
                cell["count"] += 1
            t_rows = []
            for dt in sorted(by_date.keys())[(-slice_cnt if slice_cnt else None) :]:
                row_out: Dict[str, Any] = {"date": dt}
                for sym in top_syms:
                    cell = by_date[dt].get(sym)
                    row_out[sym] = round(cell["total"] / cell["count"], 2) if (cell and cell["count"] > 0) else None
                t_rows.append(row_out)
            sector_timeline = {"symbols": top_syms, "rows": t_rows}

    headers = _daily_headers("daily-news-data") if _explicit_market_param(request) else _private_headers("daily-news-data")
    return JSONResponse(
        {
            "summary": {"positive": pos, "negative": neg, "neutral": neu, "total": pos + neg + neu},
            "sectors": sector_stats,
            "timeline": timeline_stats,
            "sectorTimeline": sector_timeline,
        },
        headers=headers,
    )


# ── Historical Similarity Published ──────────────────────────────────────────

def _quantile(vals: List[float], q: float) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    idx = (len(s) - 1) * q
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    return s[lo] + (s[hi] - s[lo]) * (idx % 1.0)


def _wilson_interval(wins: int, total: int) -> Optional[List[float]]:
    if not total:
        return None
    z = 1.96
    p = wins / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _calc_sim_stats(matches: List[Dict[str, Any]], forward_days: int, target: float, stop: float) -> Dict[str, Any]:
    completed = [m for m in matches if m.get("outcome") in ("win", "loss", "flat") and _finite(m.get("final_return")) is not None]
    returns = [float(m["final_return"]) for m in completed]
    wins = sum(1 for r in returns if r > 0)
    losses = sum(1 for r in returns if r < 0)
    gains = sum(max(0.0, r) for r in returns)
    loss_sum = -sum(min(0.0, r) for r in returns)
    exit_counts = {"target": 0, "stop": 0, "horizon_positive": 0, "horizon_negative": 0, "horizon_flat": 0, "incomplete": 0}
    for m in matches:
        fr = _finite(m.get("final_return"))
        reason = m.get("exit_reason") or (
            "incomplete" if fr is None
            else ("target" if abs(fr - target) < 1e-8 else ("stop" if abs(fr - stop) < 1e-8 else ("horizon_positive" if fr > 0 else ("horizon_negative" if fr < 0 else "horizon_flat"))))
        )
        exit_counts[reason] = exit_counts.get(reason, 0) + 1
    h_stats: Dict[str, Any] = {}
    for h in [5, 10, 20]:
        if h > forward_days:
            continue
        vals = []
        for m in matches:
            fp = m.get("forward_path") or []
            pt = next((p for p in fp if p.get("day") == h), None)
            if pt and _finite(pt.get("return")) is not None:
                vals.append(float(pt["return"]))
        h_stats[str(h)] = {
            "sessions": h,
            "sample_size": len(vals),
            "positive_rate": sum(1 for v in vals if v > 0) / len(vals) if vals else 0,
            "average_return": sum(vals) / len(vals) if vals else None,
            "median_return": _quantile(vals, 0.5),
            "lower_quartile": _quantile(vals, 0.25),
            "upper_quartile": _quantile(vals, 0.75),
            "best_return": max(vals) if vals else None,
            "worst_return": min(vals) if vals else None,
        }
    return {
        "total_matches": len(completed),
        "observed_matches": len(matches),
        "wins": wins,
        "losses": losses,
        "flat": len(completed) - wins - losses,
        "win_rate": wins / len(completed) if completed else None,
        "average_return": sum(returns) / len(returns) if returns else None,
        "median_return": _quantile(returns, 0.5),
        "profit_factor": (gains / loss_sum) if loss_sum else None,
        "win_interval": _wilson_interval(wins, len(completed)),
        "average_similarity": sum(float(m.get("similarity") or 0) for m in matches) / len(matches) if matches else None,
        "exit_counts": exit_counts,
        "horizon_stats": h_stats,
    }


def _prepare_similarity_report(raw: Dict[str, Any], minimum: float = 0.8) -> Dict[str, Any]:
    scans = raw.get("scans") if isinstance(raw.get("scans"), list) else []
    valid_dates = sorted(str(s.get("target_date")) for s in scans if _valid_iso_date(s.get("target_date")))
    as_of = valid_dates[-1] if valid_dates else None
    report_dt = datetime.strptime(as_of, "%Y-%m-%d") if as_of else None
    fwd_days = int(_num(raw.get("forward_days"), 20) or 20)
    target_r = _num(raw.get("target_return"), 0.05) or 0.05
    stop_l = _num(raw.get("stop_loss"), -0.03) or -0.03
    excluded = {"stale": 0, "indices": 0}
    cleaned: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for scan in scans:
        sym = scan.get("symbol")
        if not sym or sym in seen:
            continue
        seen.add(sym)
        if re.match(r"^EGX\d", str(sym), re.IGNORECASE):
            excluded["indices"] += 1
            continue
        td = _valid_iso_date(scan.get("target_date"))
        if not td:
            excluded["stale"] += 1
            continue
        if report_dt and (report_dt - datetime.strptime(td, "%Y-%m-%d")).days > 5:
            excluded["stale"] += 1
            continue
        orig = scan.get("matches") if isinstance(scan.get("matches"), list) else []
        accepted: List[Dict[str, Any]] = []
        for cand in sorted(orig, key=lambda c: _num(c.get("similarity")), reverse=True):
            sim = _finite(cand.get("similarity"))
            cdate = str(cand.get("date") or "")
            if sim is None or sim < minimum or cdate >= td:
                continue
            cfwd = cand.get("forward_path") or []
            overlaps = False
            for acc in accepted:
                adate = str(acc.get("date") or "")
                afwd = acc.get("forward_path") or []
                if adate == cdate or (adate < cdate and any(str(p.get("date") or "") >= cdate for p in afwd)) or (cdate < adate and any(str(p.get("date") or "") >= adate for p in cfwd)):
                    overlaps = True
                    break
            if not overlaps:
                accepted.append(cand)
        cleaned.append({
            "symbol": sym,
            "name": scan.get("name") or str(sym).split(".")[0],
            "sector": scan.get("sector") or "Other",
            "target_date": td,
            "target_path": scan.get("target_path") or [],
            "matches": accepted,
            "stats": _calc_sim_stats(accepted, fwd_days, target_r, stop_l),
            "rejected_matches": len(orig) - len(accepted),
        })
    cleaned.sort(key=lambda s: (-s["stats"]["total_matches"], -(s["stats"]["average_similarity"] if s["stats"]["average_similarity"] is not None else -1e9)))
    return {
        "id": raw.get("id") or None,
        "name": raw.get("name") or "",
        "updated_at": raw.get("updated_at") or None,
        "as_of": as_of,
        "k": int(_num(raw.get("k"), 10) or 10),
        "forward_days": fwd_days,
        "target_return": target_r,
        "stop_loss": stop_l,
        "minimum_similarity": minimum,
        "scans": cleaned,
        "excluded": excluded,
    }


def _market_regime_at(rows: List[Dict[str, Any]], date: str) -> Optional[str]:
    prices = sorted(
        [r for r in rows if str(r.get("date") or "") <= date and (_finite(r.get("close")) or 0) > 0],
        key=lambda r: str(r.get("date")),
    )
    if len(prices) < 21:
        return None
    last_d = _valid_iso_date(prices[-1].get("date"))
    cur_d = _valid_iso_date(date)
    if not last_d or not cur_d or (datetime.strptime(cur_d, "%Y-%m-%d") - datetime.strptime(last_d, "%Y-%m-%d")).days > 5:
        return None
    last_c = float(prices[-1]["close"])
    short = last_c / float(prices[-6]["close"]) - 1.0
    long = last_c / float(prices[-21]["close"]) - 1.0
    if short < -0.015 or long < -0.04:
        return "down"
    if short > 0.01 and long > 0.01:
        return "up"
    return "range"


def _sector_flow_at(rows: List[Dict[str, Any]], date: str) -> Optional[str]:
    avail = sorted(
        [r for r in rows if str(r.get("date") or "") <= date and _finite(r.get("cmf")) is not None],
        key=lambda r: str(r.get("date")),
    )
    if not avail:
        return None
    last_d = _valid_iso_date(avail[-1].get("date"))
    cur_d = _valid_iso_date(date)
    if not last_d or not cur_d or (datetime.strptime(cur_d, "%Y-%m-%d") - datetime.strptime(last_d, "%Y-%m-%d")).days > 5:
        return None
    cmf = float(avail[-1]["cmf"])
    return "outflow" if cmf < -0.05 else ("inflow" if cmf > 0.05 else "balanced")


@router.get("/api/scan/similarity/published")
async def api_scan_similarity_published(request: Request):
    qp = request.query_params
    req_limit = int(_num(qp.get("limit"), 0))
    view = qp.get("view")
    sel_sym = str(qp.get("symbol") or "").upper()
    context_mode = qp.get("context")

    def _load_base() -> Dict[str, Any]:
        sb = get_primary_supabase()
        if sb is None:
            return {"raw": None, "names": {}, "market": {}}
        rep_res = sb.table("similarity_reports").select("id,name,scans,k,forward_days,target_return,stop_loss,updated_at").order("updated_at", desc=True).limit(1).execute()
        raw = (getattr(rep_res, "data", None) or [None])[0]
        if not raw:
            return {"raw": None, "names": {}, "market": {}}
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_n = pool.submit(lambda: getattr(sb.table("stock_fundamentals").select("symbol,data").eq("exchange", "EGX").limit(1000).execute(), "data", None) or [])
            f_m = pool.submit(lambda: getattr(sb.table("market_cache").select("payload").eq("cache_key", "market_status_Egypt").limit(1).execute(), "data", None) or [])
            n_rows = f_n.result()
            m_rows = f_m.result()
        names = {r["symbol"]: (_parse_json_obj(r.get("data")) or {}) for r in n_rows if r.get("symbol")}
        mkt = _parse_json_obj(m_rows[0].get("payload")) if m_rows else {}
        return {"raw": raw, "names": names, "market": mkt or {}}

    found, base = _SIMILARITY_CACHE.get("latest")
    if not found:
        base = _SIMILARITY_SF.do("latest", _load_base)
        _SIMILARITY_CACHE.set("latest", base, ttl=_RUN_TO_RUN_TTL)

    raw = base.get("raw")
    if not raw:
        if view == "summary" or sel_sym:
            return JSONResponse(_prepare_similarity_report({"scans": []}), headers={"Cache-Control": "public, s-maxage=60"})
        return JSONResponse({"scans": [], "name": "No Active Similarity Report", "updated_at": None}, headers={"Cache-Control": "public, s-maxage=60, stale-while-revalidate=120"})

    scans = _parse_json_obj(raw.get("scans")) or []
    if view == "summary" or sel_sym:
        report = _prepare_similarity_report({**raw, "scans": scans})
        names = base.get("names") or {}
        mkt = base.get("market") or {}
        egx30 = mkt.get("egx30") or []
        egx100 = mkt.get("egx100") or []

        def _ctx_at(dt: str) -> Optional[str]:
            r1 = _market_regime_at(egx30, dt)
            r2 = _market_regime_at(egx100, dt)
            if r1 and r2:
                return r1 if r1 == r2 else "mixed"
            return None

        for scan in report["scans"]:
            ident = names.get(scan["symbol"].split(".")[0], {})
            scan["name"] = ident.get("name_ar") or ident.get("arabic_name") or ident.get("name") or ident.get("Name") or scan["name"]
            scan["sector"] = ident.get("sector") or ident.get("Sector") or "Other"
            scan["current_market"] = _ctx_at(scan["target_date"])

        if view == "summary":
            trimmed = [{k: v for k, v in s.items() if k not in ("matches", "target_path")} for s in report["scans"]]
            return JSONResponse({**report, "scans": trimmed}, headers=_daily_headers("daily-market-data"))

        scan = next((s for s in report["scans"] if s["symbol"] == sel_sym), None)
        if not scan:
            return JSONResponse({"error": "Symbol not in current report"}, status_code=404, headers={"Cache-Control": "no-store"})
        scan_copy = {**scan}
        sb = get_primary_supabase()
        heat_rows = getattr(sb.table("market_heatmap").select("symbol,cmf_20,captured_at").eq("exchange", "EGX").eq("sector", scan_copy["sector"]).order("captured_at", desc=True).limit(5000).execute(), "data", None) or [] if sb else []
        trunc_day = str(heat_rows[-1].get("captured_at"))[:10] if len(heat_rows) == 5000 else None
        captures: Dict[str, Dict[str, Any]] = {}
        for row in heat_rows:
            cmf = _finite(row.get("cmf_20"))
            if cmf is None:
                continue
            d = str(row.get("captured_at"))[:10]
            if d == trunc_day:
                continue
            k = f"{d}:{row.get('symbol')}"
            prev = captures.get(k)
            if not prev or str(row.get("captured_at")) > prev["captured"]:
                captures[k] = {"date": d, "cmf": cmf, "captured": str(row.get("captured_at"))}
        by_day: Dict[str, List[float]] = {}
        for c in captures.values():
            by_day.setdefault(c["date"], []).append(c["cmf"])
        sec_hist = [{"date": d, "cmf": sum(vs) / len(vs)} for d, vs in by_day.items()]
        scan_copy["current_sector"] = _sector_flow_at(sec_hist, scan_copy["target_date"])
        matches = [{**m, "market_context": _ctx_at(m["date"]), "sector_context": _sector_flow_at(sec_hist, m["date"])} for m in (scan_copy.get("matches") or [])]
        same_ctx = lambda m: bool(scan_copy.get("current_market") and scan_copy.get("current_sector") and m.get("market_context") == scan_copy["current_market"] and m.get("sector_context") == scan_copy["current_sector"])
        scan_copy["context_coverage"] = {
            "observed": len(matches),
            "market": sum(1 for m in matches if m.get("market_context")),
            "sector": sum(1 for m in matches if m.get("sector_context")),
            "matched": sum(1 for m in matches if same_ctx(m)),
        }
        if context_mode == "matched":
            matches = [m for m in matches if same_ctx(m)]
            scan_copy["stats"] = _calc_sim_stats(matches, report["forward_days"], report["target_return"], report["stop_loss"])
        scan_copy["matches"] = matches
        return JSONResponse({**report, "scans": [scan_copy]}, headers=_daily_headers("daily-market-data"))

    if req_limit > 0 and isinstance(scans, list):
        scans = scans[:req_limit]
    return JSONResponse(
        {
            "id": raw.get("id"),
            "name": raw.get("name"),
            "scans": scans,
            "k": raw.get("k"),
            "forward_days": raw.get("forward_days"),
            "target_return": raw.get("target_return"),
            "stop_loss": raw.get("stop_loss"),
            "updated_at": raw.get("updated_at"),
        },
        headers=_daily_headers("daily-market-data"),
    )


# ── Sector Heatmap & Timeline ────────────────────────────────────────────────

def _enrich_heatmap_symbol_metadata(
    sb: Any,
    exchanges: List[str],
    syms: List[str],
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    fundamentals: Dict[str, Dict[str, Any]] = {}
    stocks_meta: Dict[str, Dict[str, Any]] = {}
    is_egx_only = exchanges == ["EGX"]
    for i in range(0, len(syms), 200):
        chunk = syms[i : i + 200]
        try:
            f_data = getattr(sb.table("stock_fundamentals").select("symbol,name,name_ar,data").in_("exchange", exchanges).in_("symbol", chunk).limit(len(chunk)).execute(), "data", None) or []
        except Exception:
            f_data = getattr(sb.table("stock_fundamentals").select("symbol,data").in_("exchange", exchanges).in_("symbol", chunk).limit(len(chunk)).execute(), "data", None) or []
        for row in f_data:
            if row.get("symbol"):
                fundamentals[row["symbol"]] = {"name": row.get("name"), "name_ar": row.get("name_ar"), "data": _parse_json_obj(row.get("data")) or {}}
        stock_cols = "symbol,name,name_ar" if is_egx_only else "symbol,name,name_ar,sector"
        stock_cols_fb = "symbol,name" if is_egx_only else "symbol,name,sector"
        try:
            s_data = getattr(sb.table("stocks").select(stock_cols).in_("exchange", exchanges).in_("symbol", chunk).limit(len(chunk)).execute(), "data", None) or []
        except Exception:
            s_data = getattr(sb.table("stocks").select(stock_cols_fb).in_("exchange", exchanges).in_("symbol", chunk).limit(len(chunk)).execute(), "data", None) or []
        for row in s_data:
            if row.get("symbol"):
                stocks_meta[row["symbol"]] = row
    return fundamentals, stocks_meta


def _compute_heatmap_from_indicators(
    sb: Any,
    market: str,
    exchange: str,
    exchanges: List[str],
    currency: str,
    sel_date: Optional[str],
    start_d: Optional[str],
    end_d: Optional[str],
) -> Dict[str, Any]:
    d_rows = getattr(sb.table("stock_technical_indicators").select("date").in_("exchange", exchanges).order("date", desc=True).limit(3000).execute(), "data", None) or []
    avail = sorted({str(r.get("date") or "")[:10] for r in d_rows if r.get("date")}, reverse=True)[:60]
    if not avail:
        return {"rows": [], "available_dates": [], "market": market, "exchange": exchange, "currency": currency}
    eff_date = sel_date if (sel_date and sel_date in avail) else (next((d for d in avail if sel_date and d <= sel_date), avail[0]))
    s = start_d or eff_date
    e = end_d or eff_date
    f_d, t_d = (s, e) if s <= e else (e, s)
    ind_rows: List[Dict[str, Any]] = []
    for cols in (
        "symbol,exchange,date,close,volume,change_pct,cmf_20",
        "symbol,exchange,date,close,volume,change_pct",
        "symbol,date,close,volume,change_pct",
    ):
        try:
            ind_rows = getattr(
                sb.table("stock_technical_indicators")
                .select(cols)
                .in_("exchange", exchanges)
                .gte("date", f_d)
                .lte("date", t_d)
                .order("date", desc=False)
                .limit(10000)
                .execute(),
                "data",
                None,
            ) or []
            break
        except Exception:
            continue

    dedup: Dict[str, Dict[str, Any]] = {}
    for row in ind_rows:
        sym = row.get("symbol")
        day = str(row.get("date") or "")[:10]
        if not sym or not day:
            continue
        dedup[f"{day}|{sym}"] = row

    syms = list({r.get("symbol") for r in dedup.values() if r.get("symbol")})
    fundamentals, stocks_meta = _enrich_heatmap_symbol_metadata(sb, exchanges, syms)
    rows_out: List[Dict[str, Any]] = []
    for row in dedup.values():
        sym = str(row["symbol"])
        close_v = _num(row.get("close"))
        vol = _num(row.get("volume"))
        if close_v <= 0 or vol <= 0:
            continue
        f_rec = fundamentals.get(sym) or {}
        f_data = f_rec.get("data") or {}
        s_meta = stocks_meta.get(sym) or {}
        name_ar = s_meta.get("name_ar") or f_rec.get("name_ar") or f_data.get("name_ar") or f_data.get("NameAr")
        name_en = f_data.get("name") or f_data.get("Name") or f_data.get("companyName") or f_rec.get("name") or s_meta.get("name")
        resolved_name = (name_ar or name_en or sym) if market != "egx" else (name_en or name_ar or sym)
        raw_sec = f_data.get("sector") or f_data.get("Sector") or s_meta.get("sector") or "Other"
        item: Dict[str, Any] = {
            "symbol": sym,
            "exchange": row.get("exchange") or exchange,
            "currency": currency,
            "date": str(row.get("date"))[:10],
            "close": close_v,
            "volume": vol,
            "change_pct": _num(row.get("change_pct")),
            "cmf_20": _num(row.get("cmf_20")),
            "sector": raw_sec,
            "name": resolved_name,
        }
        if name_ar:
            item["name_ar"] = name_ar
        rows_out.append(item)

    return {
        "rows": rows_out,
        "selected_date": eff_date,
        "requested_date": sel_date,
        "available_dates": avail,
        "range_start": f_d,
        "range_end": t_d,
        "range_dates": [d for d in avail if f_d <= d <= t_d],
        "market": market,
        "exchange": exchange,
        "currency": currency,
    }


def _load_sector_heatmap(market: str, sel_date: Optional[str], start_d: Optional[str], end_d: Optional[str]) -> Dict[str, Any]:
    sb = get_market_supabase(market)
    exchange = get_market_exchange(market)
    exchanges = get_market_exchanges(market)
    currency = _MARKET_CURRENCY_MAP.get(market, "EGP")
    if sb is None:
        return {"rows": [], "available_dates": [], "market": market, "exchange": exchange, "currency": currency}
    d_rows = getattr(sb.table("market_heatmap").select("captured_at").in_("exchange", exchanges).order("captured_at", desc=True).limit(12000).execute(), "data", None) or []
    avail = sorted({str(r.get("captured_at") or "")[:10] for r in d_rows if r.get("captured_at")}, reverse=True)
    if not avail:
        return _compute_heatmap_from_indicators(sb, market, exchange, exchanges, currency, sel_date, start_d, end_d)
    eff_date = sel_date if (sel_date and sel_date in avail) else (next((d for d in avail if sel_date and d <= sel_date), avail[0]))
    s = start_d or eff_date
    e = end_d or eff_date
    f_d, t_d = (s, e) if s <= e else (e, s)
    c_rows = getattr(
        sb.table("market_heatmap")
        .select("symbol,exchange,sector,change_pct,cmf_20,volume,cap,captured_at")
        .in_("exchange", exchanges)
        .gte("captured_at", f"{f_d}T00:00:00Z")
        .lte("captured_at", f"{t_d}T23:59:59.999Z")
        .order("captured_at", desc=False)
        .limit(10000)
        .execute(),
        "data",
        None,
    ) or []
    if not c_rows:
        return _compute_heatmap_from_indicators(sb, market, exchange, exchanges, currency, sel_date, start_d, end_d)
    dedup: Dict[str, Dict[str, Any]] = {}
    for row in c_rows:
        day = str(row.get("captured_at") or "")[:10]
        k = f"{day}|{row.get('symbol')}"
        prev = dedup.get(k)
        if not prev or str(row.get("captured_at")) > str(prev.get("captured_at")):
            dedup[k] = row

    syms = list({r.get("symbol") for r in dedup.values() if r.get("symbol")})
    fundamentals, stocks_meta = _enrich_heatmap_symbol_metadata(sb, exchanges, syms)

    rows_out: List[Dict[str, Any]] = []
    for row in dedup.values():
        sym = row["symbol"]
        vol = _num(row.get("volume"))
        traded_v = _num(row.get("cap"))
        f_rec = fundamentals.get(sym) or {}
        f_data = f_rec.get("data") or {}
        s_meta = stocks_meta.get(sym) or {}
        name_ar = s_meta.get("name_ar") or f_rec.get("name_ar") or f_data.get("name_ar") or f_data.get("NameAr")
        name_en = f_data.get("name") or f_data.get("Name") or f_data.get("companyName") or f_rec.get("name") or s_meta.get("name")
        resolved_name = (name_ar or name_en or sym) if market != "egx" else (name_en or name_ar or sym)
        item: Dict[str, Any] = {
            "symbol": sym,
            "exchange": row.get("exchange") or exchange,
            "currency": currency,
            "date": str(row.get("captured_at"))[:10],
            "close": traded_v / vol if vol > 0 else 0,
            "volume": vol,
            "change_pct": _num(row.get("change_pct")),
            "cmf_20": _num(row.get("cmf_20")),
            "sector": row.get("sector") or f_data.get("sector") or f_data.get("Sector") or s_meta.get("sector") or "Other",
            "name": resolved_name,
        }
        if name_ar:
            item["name_ar"] = name_ar
        rows_out.append(item)

    return {
        "rows": rows_out,
        "selected_date": eff_date,
        "requested_date": sel_date,
        "available_dates": avail,
        "range_start": f_d,
        "range_end": t_d,
        "range_dates": [d for d in avail if f_d <= d <= t_d],
        "market": market,
        "exchange": exchange,
        "currency": currency,
    }


@router.get("/api/scan/sectors/heatmap")
async def api_scan_sectors_heatmap(request: Request):
    qp = request.query_params
    market = resolve_request_market(request)
    sel_d = _valid_iso_date(qp.get("date") or qp.get("single_date"))
    s_d = _valid_iso_date(qp.get("start") or qp.get("start_date"))
    e_d = _valid_iso_date(qp.get("end") or qp.get("end_date"))
    key = f"{market}:{sel_d}:{s_d}:{e_d}"
    found, cached = _HEATMAP_CACHE.get(key)
    if not found:
        cached = _HEATMAP_SF.do(key, lambda: _load_sector_heatmap(market, sel_d, s_d, e_d))
        _HEATMAP_CACHE.set(key, cached, ttl=_RUN_TO_RUN_TTL)
    headers = {"Cache-Control": "public, s-maxage=86400, stale-while-revalidate=86400", "Vercel-Cache-Tag": "daily-market-data"} if _explicit_market_param(request) else _private_headers("daily-market-data")
    return JSONResponse(cached, headers=headers)


def _compute_sector_timeline_from_indicators(
    sb: Any,
    market: str,
    country: str,
    months_i: int,
) -> Optional[Dict[str, Any]]:
    exchanges = get_market_exchanges(market)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=min(months_i, 12) * 32)).strftime("%Y-%m-%d")
    ind_rows: List[Dict[str, Any]] = []
    for cols in (
        "symbol,date,close,volume,cmf_20,change_pct",
        "symbol,date,close,volume,change_pct",
    ):
        try:
            ind_rows = getattr(
                sb.table("stock_technical_indicators")
                .select(cols)
                .in_("exchange", exchanges)
                .gte("date", cutoff)
                .order("date", desc=True)
                .limit(12000)
                .execute(),
                "data",
                None,
            ) or []
            break
        except Exception:
            continue
    if not ind_rows:
        return None
    syms = list({str(r.get("symbol") or "").upper() for r in ind_rows if r.get("symbol")})
    fundamentals, stocks_meta = _enrich_heatmap_symbol_metadata(sb, exchanges, syms)
    sym_sector: Dict[str, Dict[str, str]] = {}
    for sym in syms:
        f_data = (fundamentals.get(sym) or {}).get("data") or {}
        s_meta = stocks_meta.get(sym) or {}
        sym_sector[sym] = _classify_market_sector(
            str(f_data.get("sector") or f_data.get("Sector") or s_meta.get("sector") or ""),
            str(f_data.get("industry") or f_data.get("Industry") or ""),
        )

    monthly_totals: Dict[str, float] = {}
    sector_monthly: Dict[str, Dict[str, Any]] = {}
    for row in ind_rows:
        sym = str(row.get("symbol") or "").upper()
        day = str(row.get("date") or "")[:10]
        if not sym or len(day) < 7:
            continue
        month = day[:7]
        close_v = _num(row.get("close"))
        vol_v = _num(row.get("volume"))
        if close_v <= 0 or vol_v <= 0:
            continue
        flow = close_v * vol_v
        cmf = _finite(row.get("cmf_20"))
        chg = _num(row.get("change_pct"))
        net = flow * (cmf if cmf is not None else (1.0 if chg > 0 else (-1.0 if chg < 0 else 0.0)))
        sec_info = sym_sector.get(sym) or {"sector": "Other Sectors", "sector_ar": "قطاعات متنوعة أخرى"}
        sec_name = sec_info["sector"]
        monthly_totals[month] = monthly_totals.get(month, 0.0) + flow
        bucket = sector_monthly.setdefault(
            sec_name,
            {"sector": sec_name, "sector_ar": sec_info["sector_ar"], "total_flow": 0.0, "months": {}},
        )
        bucket["total_flow"] += flow
        m_entry = bucket["months"].setdefault(month, {"flow": 0.0, "net": 0.0})
        m_entry["flow"] += flow
        m_entry["net"] += net

    if not monthly_totals:
        return None
    months_sorted = sorted(monthly_totals.keys())[-months_i:]
    monthly = [{"month": m, "total_flow": round(monthly_totals[m], 2)} for m in months_sorted]
    sectors_out = []
    for b in sorted(sector_monthly.values(), key=lambda x: x["total_flow"], reverse=True):
        series = [
            {
                "month": m,
                "flow": round(b["months"].get(m, {}).get("flow", 0.0), 2),
                "net": round(b["months"].get(m, {}).get("net", 0.0), 2),
            }
            for m in months_sorted
        ]
        sectors_out.append({
            "sector": b["sector"],
            "sector_ar": b["sector_ar"],
            "total_flow": round(sum(p["flow"] for p in series), 2),
            "series": series,
        })
    return {
        "months": months_sorted,
        "monthly": monthly,
        "sectors": sectors_out,
        "market": market,
        "country": country,
        "cached": False,
        "computed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@router.get("/api/scan/sectors/timeline")
async def api_scan_sectors_timeline(request: Request):
    qp = request.query_params
    market = resolve_request_market(request, qp.get("country"))
    country = {"tasi": "Saudi Arabia", "uae": "UAE", "qatar": "Qatar"}.get(market, "Egypt")
    m_val = _num(qp.get("months"), 6)
    months_i = int(m_val) if m_val > 0 else 6
    cache_key = f"sector_timeline_{months_i}m"
    c_key = f"{market}:{months_i}"
    found, cached = _TIMELINE_CACHE.get(c_key)
    if not found:
        def _load():
            sb = get_market_supabase(market)
            if sb is None:
                return None
            if market in ("egx", "tasi"):
                res = sb.table("market_cache").select("payload,computed_at").eq("cache_key", cache_key).eq("country", country).order("computed_at", desc=True).limit(1).execute()
                row = (getattr(res, "data", None) or [None])[0]
                if row and row.get("payload"):
                    pl = _parse_json_obj(row["payload"]) or {}
                    return {**pl, "market": market, "country": country, "cached": True, "computed_at": row.get("computed_at")}
            if market != "egx":
                return _compute_sector_timeline_from_indicators(sb, market, country, months_i)
            return None
        cached = _TIMELINE_SF.do(c_key, _load)
        if cached:
            _TIMELINE_CACHE.set(c_key, cached, ttl=_RUN_TO_RUN_TTL)

    explicit = _explicit_market_param(request)
    if cached:
        return JSONResponse(cached, headers={"Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400"} if explicit else _private_headers())
    return JSONResponse(
        {"months": [], "monthly": [], "sectors": [], "market": market, "country": country, "cached": False, "computed_at": None},
        headers={"Cache-Control": "public, s-maxage=60, stale-while-revalidate=120"} if explicit else _private_headers(),
    )


# ── Traps & Unusual Activity & Market Breadth ───────────────────────────────

def _load_traps_snapshot(market: str) -> Dict[str, Any]:
    sb = get_market_supabase(market)
    exchange = get_market_exchange(market)
    exchanges = get_market_exchanges(market)
    currency = _MARKET_CURRENCY_MAP.get(market, "EGP")
    if sb is None:
        return {"asOf": None, "exchange": exchange, "currency": currency, "bearTraps": [], "bullTraps": [], "totalBearTraps": 0, "totalBullTraps": 0}
    if market in ("egx", "tasi"):
        c_keys = ["scanner_traps_TADAWUL", "scanner_traps_TASI", "daily_traps_snapshot_tasi"] if market == "tasi" else ["scanner_traps_EGX", "daily_traps_snapshot"]
        try:
            c_rows = getattr(sb.table("market_cache").select("payload,computed_at").in_("cache_key", c_keys).order("computed_at", desc=True).limit(1).execute(), "data", None) or []
            if c_rows and isinstance(c_rows[0].get("payload"), dict):
                pl = c_rows[0]["payload"]
                bear = pl.get("bearTraps") or []
                bull = pl.get("bullTraps") or []
                if bear or bull:
                    return {
                        "asOf": pl.get("asOf"),
                        "exchange": exchange,
                        "currency": currency,
                        "bearTraps": bear[:8],
                        "bullTraps": bull[:8],
                        "totalBearTraps": pl.get("totalBearTraps", len(bear)),
                        "totalBullTraps": pl.get("totalBullTraps", len(bull)),
                    }
        except Exception:
            pass

    latest = getattr(sb.table("stock_technical_indicators").select("date").in_("exchange", exchanges).order("date", desc=True).limit(1).execute(), "data", None) or []
    as_of = str(latest[0]["date"])[:10] if latest and latest[0].get("date") else None
    if not as_of:
        return {"asOf": None, "exchange": exchange, "currency": currency, "bearTraps": [], "bullTraps": [], "totalBearTraps": 0, "totalBullTraps": 0}

    def _q_ind():
        for f in ("symbol,exchange,close,change_pct,rsi_14,r_vol,ema_20,sma_20,bb_upper,bb_lower,egx_ai_score", "symbol,exchange,close,change_pct,rsi_14,r_vol,ema_20,sma_20,bb_upper,bb_lower", "symbol,close,change_pct,rsi_14,ema_20"):
            try:
                return getattr(sb.table("stock_technical_indicators").select(f).in_("exchange", exchanges).eq("date", as_of).limit(500).execute(), "data", None) or []
            except Exception:
                continue
        return []

    def _q_names():
        if market == "egx":
            return []
        try:
            return getattr(sb.table("stocks").select("symbol,name_ar,name").in_("exchange", exchanges).limit(500).execute(), "data", None) or []
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_i = pool.submit(_q_ind)
        f_b = pool.submit(lambda: getattr(sb.table("stock_prices").select("symbol,open,high,low,close").in_("exchange", exchanges).eq("date", as_of).limit(500).execute(), "data", None) or [])
        f_n = pool.submit(_q_names)
        ind_rows = f_i.result()
        bars_map = {str(b["symbol"]).strip().upper(): b for b in f_b.result() if b.get("symbol")}
        stock_names_map = {
            str(s["symbol"]).strip().upper(): (s.get("name_ar") or s.get("name") or "")
            for s in f_n.result()
            if s.get("symbol")
        }

    bears: List[Dict[str, Any]] = []
    bulls: List[Dict[str, Any]] = []
    for ind in ind_rows:
        sym = str(ind.get("symbol") or "").strip().upper()
        bar = bars_map.get(sym)
        if not sym or not bar:
            continue
        high = _finite(bar.get("high"))
        low = _finite(bar.get("low"))
        close = _finite(bar.get("close")) or _finite(ind.get("close"))
        if not high or not low or not close or close <= 0 or high <= low:
            continue
        rng = high - low
        if (rng / close) * 100 < 1.5:
            continue
        rec_r = (close - low) / rng
        rej_r = (high - close) / rng
        r_vol = _finite(ind.get("r_vol")) or 1.0
        rsi = _finite(ind.get("rsi_14"))
        chg = _finite(ind.get("change_pct"))
        sma20 = _finite(ind.get("sma_20")) or _finite(ind.get("ema_20")) or close
        bb_lo = _finite(ind.get("bb_lower")) or sma20 * 0.95
        bb_hi = _finite(ind.get("bb_upper")) or sma20 * 1.05
        ai_raw = _finite(ind.get("egx_ai_score"))
        ai_sc = round(ai_raw * 100) if (ai_raw is not None and 0 <= ai_raw <= 1) else ai_raw
        name_ar = (
            stock_names_map.get(sym) or SAUDI_STOCK_NAMES_AR.get(sym)
            if market != "egx"
            else CANONICAL_EGX_STOCK_NAMES.get(sym, {}).get("name_ar")
        ) or sym

        sup_ref = bb_lo if abs(low - bb_lo) < abs(low - sma20) else sma20
        if low <= sup_ref * 1.005 and close >= sup_ref * 0.992 and rec_r >= 0.62 and r_vol >= 0.8:
            conv = min(99.0, round(rec_r * 65 + min(r_vol, 3.0) * 11, 1))
            bears.append({
                "symbol": sym, "nameAr": name_ar, "trapType": "BEAR_TRAP", "close": round(close, 2),
                "low": round(low, 2), "high": round(high, 2), "keyLevel": round(sup_ref, 2),
                "wickPct": round(rec_r * 100, 1), "relativeVolume": round(r_vol, 2),
                "changePct": round(chg, 2) if chg is not None else None,
                "rsi": round(rsi, 1) if rsi is not None else None,
                "aiScore": ai_sc, "conviction": conv,
            })
            continue
        res_ref = bb_hi if high >= bb_hi * 0.985 else sma20 * 1.015
        if high >= res_ref and close < res_ref * 0.998 and rej_r >= 0.62 and r_vol >= 0.8:
            conv = min(99.0, round(rej_r * 65 + min(r_vol, 3.0) * 11, 1))
            bulls.append({
                "symbol": sym, "nameAr": name_ar, "trapType": "BULL_TRAP", "close": round(close, 2),
                "low": round(low, 2), "high": round(high, 2), "keyLevel": round(res_ref, 2),
                "wickPct": round(rej_r * 100, 1), "relativeVolume": round(r_vol, 2),
                "changePct": round(chg, 2) if chg is not None else None,
                "rsi": round(rsi, 1) if rsi is not None else None,
                "aiScore": ai_sc, "conviction": conv,
            })

    bears.sort(key=lambda x: x["conviction"], reverse=True)
    bulls.sort(key=lambda x: x["conviction"], reverse=True)
    return {
        "asOf": as_of, "exchange": exchange, "currency": currency,
        "bearTraps": bears[:8], "bullTraps": bulls[:8],
        "totalBearTraps": len(bears), "totalBullTraps": len(bulls),
    }


@router.get("/api/scan/traps")
async def api_scan_traps(request: Request):
    market = resolve_request_market(request)
    found, payload = _TRAPS_CACHE.get(market)
    if not found:
        payload = _TRAPS_SF.do(market, lambda: _load_traps_snapshot(market))
        _TRAPS_CACHE.set(market, payload, ttl=_RUN_TO_RUN_TTL)
    headers = _daily_headers("daily-market-data") if _explicit_market_param(request) else _private_headers("daily-market-data")
    return JSONResponse(payload, headers=headers)


def _load_unusual_activity(market: str) -> Dict[str, Any]:
    sb = get_market_supabase(market)
    exchange = get_market_exchange(market)
    exchanges = get_market_exchanges(market)
    currency = _MARKET_CURRENCY_MAP.get(market, "EGP")
    if sb is None:
        return {"asOf": None, "exchange": exchange, "currency": currency, "coverage": 0, "totalMatches": 0, "threshold": 2, "rows": []}
    latest = getattr(sb.table("stock_technical_indicators").select("date").in_("exchange", exchanges).order("date", desc=True).limit(1).execute(), "data", None) or []
    as_of = str(latest[0]["date"])[:10] if latest and latest[0].get("date") else None
    if not as_of:
        return {"asOf": None, "exchange": exchange, "currency": currency, "coverage": 0, "totalMatches": 0, "threshold": 2, "rows": []}
    ind_rows = []
    for f in ("symbol,exchange,close,change_pct,rsi_14,r_vol,vol_sma20,volume,egx_ai_score", "symbol,exchange,close,change_pct,rsi_14,r_vol,vol_sma20,volume", "symbol,close,change_pct,rsi_14,volume_sma_20,volume"):
        try:
            ind_rows = getattr(sb.table("stock_technical_indicators").select(f).in_("exchange", exchanges).eq("date", as_of).limit(1000).execute(), "data", None) or []
            break
        except Exception:
            continue
    by_sym: Dict[str, Dict[str, Any]] = {}
    for row in ind_rows:
        if row.get("symbol"):
            by_sym[str(row["symbol"])] = row

    enriched: List[Dict[str, Any]] = []
    for row in by_sym.values():
        avg_v = _finite(row.get("vol_sma20") if row.get("vol_sma20") is not None else row.get("volume_sma_20")) or 0.0
        vol = _finite(row.get("volume")) or 0.0
        r_vol = _finite(row.get("r_vol"))
        if r_vol is None:
            r_vol = (vol / avg_v) if (avg_v > 0 and vol > 0) else 0.0
        if avg_v > 0 and vol > 0:
            enriched.append({**row, "_rvol": r_vol})

    threshold: float = 2
    unusual = [r for r in enriched if r["_rvol"] >= threshold]
    if market in ("uae", "qatar") and len(unusual) < 3:
        threshold = 1.25
        unusual = [r for r in enriched if r["_rvol"] >= threshold]

    unusual.sort(key=lambda x: x["_rvol"], reverse=True)
    candidates = unusual[:15]
    cand_syms = [r["symbol"] for r in candidates]
    history: Dict[str, List[float]] = {}
    stock_names_map: Dict[str, str] = {}
    if cand_syms:
        from_d = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=75)).strftime("%Y-%m-%d")
        def _q_bars():
            return getattr(sb.table("stock_prices").select("symbol,date,high").in_("exchange", exchanges).in_("symbol", cand_syms).gte("date", from_d).lt("date", as_of).order("date", desc=True).limit(1000).execute(), "data", None) or []
        def _q_stock_names():
            if market == "egx":
                return []
            try:
                return getattr(sb.table("stocks").select("symbol,name_ar,name").in_("exchange", exchanges).in_("symbol", cand_syms).limit(len(cand_syms)).execute(), "data", None) or []
            except Exception:
                return []
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_bars = pool.submit(_q_bars)
            f_names = pool.submit(_q_stock_names)
            for b in f_bars.result():
                h = _finite(b.get("high"))
                if h is not None and len(history.get(b["symbol"], [])) < 20:
                    history.setdefault(b["symbol"], []).append(h)
            for s in f_names.result():
                su = str(s.get("symbol") or "").strip().upper()
                lbl = s.get("name_ar") or s.get("name") or ""
                if su and lbl:
                    stock_names_map[su] = str(lbl)

    rows_out = []
    for r in candidates:
        sym = str(r["symbol"])
        sym_u = sym.strip().upper()
        close = _finite(r.get("close"))
        hi_list = history.get(sym) or []
        res_20 = max(hi_list) if hi_list else None
        score = _finite(r.get("egx_ai_score"))
        name_ar = (
            stock_names_map.get(sym_u) or SAUDI_STOCK_NAMES_AR.get(sym_u)
            if market != "egx"
            else CANONICAL_EGX_STOCK_NAMES.get(sym_u, {}).get("name_ar")
        )
        rows_out.append({
            "symbol": sym,
            "exchange": str(r.get("exchange") or exchange),
            "nameAr": name_ar or sym,
            "relativeVolume": float(r["_rvol"]),
            "close": close,
            "changePct": _finite(r.get("change_pct")),
            "rsi": _finite(r.get("rsi_14")),
            "aiScore": (score * 100.0) if (score is not None and 0 <= score <= 1) else None,
            "resistance": res_20,
            "distanceToResistancePct": ((res_20 - close) / res_20) * 100.0 if (res_20 and close is not None) else None,
        })
    return {"asOf": as_of, "exchange": exchange, "currency": currency, "coverage": len(by_sym), "totalMatches": len(unusual), "threshold": threshold, "rows": rows_out}


@router.get("/api/scan/unusual-activity")
async def api_scan_unusual_activity(request: Request):
    market = resolve_request_market(request)
    found, payload = _UNUSUAL_CACHE.get(market)
    if not found:
        payload = _UNUSUAL_SF.do(market, lambda: _load_unusual_activity(market))
        _UNUSUAL_CACHE.set(market, payload, ttl=_RUN_TO_RUN_TTL)
    headers = _daily_headers("daily-market-data") if _explicit_market_param(request) else _private_headers("daily-market-data")
    return JSONResponse(payload, headers=headers)


def _classify_market_sector(raw_sec: str, raw_ind: str) -> Dict[str, str]:
    comb = f"{raw_ind or ''} {raw_sec or ''}".lower()
    sec_l = str(raw_sec or "").lower()
    ind_l = str(raw_ind or "").lower()
    if "reit" in comb or "صناديق عقارية" in comb or "ريت" in comb:
        return {"sector": "REITs", "sector_ar": "الصناديق العقارية المتداولة (ريت)"}
    if "real estate" in comb or "homebuilding" in ind_l or "عقار" in comb:
        return {"sector": "Real Estate", "sector_ar": "العقارات والتطوير العقاري"}
    if ("bank" in comb and "investment" not in ind_l and "broker" not in ind_l) or "بنوك" in comb or "مصارف" in comb:
        return {"sector": "Banks", "sector_ar": "البنوك"}
    if "finance" in sec_l or "financial" in comb or "investment" in ind_l or "insurance" in comb or "تأمين" in comb or "مالية" in comb:
        return {"sector": "Financial Services", "sector_ar": "الخدمات المالية والتأمين"}
    if any(w in comb for w in ("chemical", "fertilizer", "petrochemical", "كيماويات", "أسمدة")):
        return {"sector": "Chemicals & Fertilizers", "sector_ar": "الكيماويات والأسمدة والبتروكيماويات"}
    if any(w in comb for w in ("construction", "engineering", "contracting", "cement", "building", "مقاولات", "بناء", "تشييد")):
        return {"sector": "Construction & Building Materials", "sector_ar": "التشييد ومواد البناء"}
    if any(w in comb for w in ("steel", "mining", "metal", "non-energy minerals", "حديد", "تعدين", "material", "مواد أساسية")):
        return {"sector": "Materials & Basic Resources", "sector_ar": "المواد الأساسية والتعدين"}
    if any(w in comb for w in ("food", "beverage", "milling", "poultry", "agricultural", "consumer non-durables", "أغذية", "مشروبات")):
        return {"sector": "Food & Beverages", "sector_ar": "الأغذية والمشروبات والزراعة"}
    if any(w in comb for w in ("pharma", "health", "medical", "hospital", "أدوية", "صحية")):
        return {"sector": "Healthcare & Pharmaceuticals", "sector_ar": "الرعاية الصحية والأدوية"}
    if any(w in comb for w in ("telecom", "technology", "communications", "software", "electronic", "media", "اتصالات", "تقنية")):
        return {"sector": "Telecom & Technology", "sector_ar": "الاتصالات وتكنولوجيا المعلومات"}
    if any(w in comb for w in ("energy", "oil", "gas", "طاقة")):
        return {"sector": "Energy", "sector_ar": "الطاقة"}
    if any(w in comb for w in ("utilities", "utility", "مرافق")):
        return {"sector": "Utilities", "sector_ar": "المرافق العامة"}
    if any(w in comb for w in ("transport", "shipping", "logistics", "container", "نقل")):
        return {"sector": "Transportation & Shipping", "sector_ar": "النقل والشحن والخدمات اللوجستية"}
    if any(w in comb for w in ("tourism", "hotel", "resort", "سياحة")):
        return {"sector": "Tourism & Leisure", "sector_ar": "السياحة والترفيه"}
    if any(w in comb for w in ("retail", "consumer", "apparel", "durables", "تجزئة", "استهلاك")):
        return {"sector": "Retail & Consumer Services", "sector_ar": "التجزئة والخدمات الاستهلاكية"}
    if any(w in comb for w in ("industrial", "capital goods", "commercial", "manufacturing", "paper", "صناعات", "رأسمالية")):
        return {"sector": "Industrial Goods", "sector_ar": "الصناعات التحويلية والسلع الرأسمالية"}
    return {"sector": "Other Sectors", "sector_ar": "قطاعات متنوعة أخرى"}


def _load_market_breadth(market: str) -> Optional[Dict[str, Any]]:
    sb = get_market_supabase(market)
    exchange = get_market_exchange(market)
    exchanges = get_market_exchanges(market)
    currency = "SAR" if market == "tasi" else ("AED" if market == "uae" else ("QAR" if market == "qatar" else "EGP"))
    curr_ar = "ر.س" if market == "tasi" else ("د.إ" if market == "uae" else ("ر.ق" if market == "qatar" else "ج.م"))
    if sb is None:
        return None
    d_rows = getattr(sb.table("stock_technical_indicators").select("date").in_("exchange", exchanges).order("date", desc=True).limit(1).execute(), "data", None) or []
    if not d_rows:
        return None
    latest_date = d_rows[0]["date"]

    def _q_ind():
        for f in ("symbol, exchange, close, volume, ema_50, ema_200, rsi_14, vol_sma20, r_vol, cmf_20, change_pct", "symbol, exchange, close, volume, ema_50, ema_200, rsi_14, vol_sma20, r_vol, change_pct", "symbol, close, volume, ema_50, ema_200, rsi_14, vol_sma20, r_vol, cmf_20, change_pct", "symbol, close, volume, ema_50, ema_200, rsi_14, volume_sma_20, r_vol, change_pct", "symbol, close, volume, change_pct"):
            try:
                return getattr(sb.table("stock_technical_indicators").select(f).in_("exchange", exchanges).eq("date", latest_date).limit(500).execute(), "data", None) or []
            except Exception:
                continue
        return []

    def _q_funds():
        for f in ("symbol, exchange, name, name_ar, data", "symbol, name, name_ar, data", "symbol, name, data", "symbol, data"):
            try:
                return getattr(sb.table("stock_fundamentals").select(f).in_("exchange", exchanges).limit(500).execute(), "data", None) or []
            except Exception:
                continue
        return []

    def _q_scans():
        try:
            return getattr(sb.table("stock_scans_summary").select("symbol, scan_date, acc_score, dist_score, wyckoff_phase").eq("scan_date", latest_date).order("acc_score", desc=True).limit(500).execute(), "data", None) or []
        except Exception:
            return []

    def _q_tasi():
        if market not in ("tasi", "uae", "qatar"):
            return []
        for f in ("symbol, exchange, name, name_ar, sector", "symbol, name, name_ar, sector", "symbol, name, sector"):
            try:
                return getattr(sb.table("stocks").select(f).in_("exchange", exchanges).eq("is_active", True).limit(500).execute(), "data", None) or []
            except Exception:
                continue
        return []

    with ThreadPoolExecutor(max_workers=4) as pool:
        f_i = pool.submit(_q_ind)
        f_f = pool.submit(_q_funds)
        f_s = pool.submit(_q_scans)
        f_t = pool.submit(_q_tasi)
        indicators = f_i.result()
        fund_rows = f_f.result()
        scan_rows = f_s.result()
        saudi_rows = f_t.result()

    if not indicators:
        return None

    name_map: Dict[str, str] = {}
    sector_map: Dict[str, Dict[str, str]] = {}
    exchange_map: Dict[str, str] = {}
    for s in saudi_rows:
        sym = str(s.get("symbol") or "").upper()
        if not sym:
            continue
        if s.get("exchange"):
            exchange_map[sym] = str(s["exchange"]).upper()
        lbl = s.get("name_ar") or s.get("name") or ""
        if lbl:
            name_map[sym] = str(lbl)
        if s.get("sector"):
            sector_map[sym] = _classify_market_sector(str(s["sector"]), "")

    for r in fund_rows:
        sym = str(r.get("symbol") or "").upper()
        if not sym:
            continue
        pl = _parse_json_obj(r.get("data")) or {}
        if not isinstance(pl, dict):
            pl = {}
        nm = r.get("name_ar") or pl.get("name_ar") or (name_map.get(sym, "") if market in ("tasi", "uae", "qatar") else "") or r.get("name") or pl.get("name") or pl.get("Name") or ""
        if r.get("name_ar") or (nm and sym not in name_map):
            name_map[sym] = str(r.get("name_ar") or nm)
        rs = str(pl.get("sector") or pl.get("Sector") or "")
        ri = str(pl.get("industry") or pl.get("Industry") or "")
        if rs or ri or sym not in sector_map:
            sector_map[sym] = _classify_market_sector(rs, ri)

    acc_c = sum(1 for r in scan_rows if _num(r.get("acc_score")) >= 50)
    strong_acc = sum(1 for r in scan_rows if _num(r.get("acc_score")) >= 70)
    dist_c = sum(1 for r in scan_rows if _num(r.get("dist_score")) >= 50)
    strong_dist = sum(1 for r in scan_rows if _num(r.get("dist_score")) >= 70)

    adv = dec = unch = above50 = above200 = 0
    rsi_sum = rsi_cnt = vol_sum = vol_cnt = 0.0
    tot_to = avg20_to = adv_to = dec_to = unch_to = 0.0
    surge_c = pos_cmf = neg_cmf = 0
    buckets: Dict[str, Dict[str, Any]] = {}
    valid_stocks: List[Dict[str, Any]] = []

    for ind in indicators:
        sym = str(ind.get("symbol") or "").upper()
        close = _num(ind.get("close"))
        if not close:
            continue
        chg = _num(ind.get("change_pct"))
        if chg > 0:
            adv += 1
        elif chg < 0:
            dec += 1
        else:
            unch += 1
        ema50 = _num(ind.get("ema_50"))
        ema200 = _num(ind.get("ema_200"))
        if ema50 and close > ema50:
            above50 += 1
        if ema200 and close > ema200:
            above200 += 1
        rsi = _finite(ind.get("rsi_14"))
        if rsi is not None:
            rsi_sum += rsi
            rsi_cnt += 1
        vol = _num(ind.get("volume"))
        vsma = _num(ind.get("vol_sma20") if ind.get("vol_sma20") is not None else ind.get("volume_sma_20"))
        rvol = _finite(ind.get("r_vol"))
        if rvol is None:
            rvol = (vol / vsma) if (vol and vsma) else 0.0
        cmf = _num(ind.get("cmf_20"))
        if vol and vsma:
            vol_sum += vol / vsma
            vol_cnt += 1
        if rvol >= 2.0:
            surge_c += 1
        if cmf > 0.05:
            pos_cmf += 1
        elif cmf < -0.05:
            neg_cmf += 1

        to_v = close * max(0.0, vol)
        avg20_to += close * max(0.0, vsma)
        tot_to += to_v
        if chg > 0:
            adv_to += to_v
        elif chg < 0:
            dec_to += to_v
        else:
            unch_to += to_v

        sname = name_map.get(sym) or sym
        sym_ex = str(ind.get("exchange") or exchange_map.get(sym) or exchange).upper()
        s_info = sector_map.get(sym) or {"sector": "Other Sectors", "sector_ar": "قطاعات متنوعة أخرى"}
        sec, sec_ar = s_info["sector"], s_info["sector_ar"]
        if to_v > 0:
            b = buckets.setdefault(sec, {
                "sector": sec, "sector_ar": sec_ar, "turnover_value": 0.0, "w_chg": 0.0, "w_cmf": 0.0,
                "stocks_count": 0, "advancing": 0, "declining": 0, "top_sym": sym, "top_ex": sym_ex, "top_name": sname, "top_to": to_v, "top_chg": chg,
            })
            b["turnover_value"] += to_v
            b["w_chg"] += chg * to_v
            b["w_cmf"] += cmf * to_v
            b["stocks_count"] += 1
            if chg > 0:
                b["advancing"] += 1
            elif chg < 0:
                b["declining"] += 1
            if to_v > b["top_to"]:
                b["top_sym"], b["top_ex"], b["top_name"], b["top_to"], b["top_chg"] = sym, sym_ex, sname, to_v, chg

        valid_stocks.append({
            "symbol": sym, "exchange": sym_ex, "name": sname, "sector": sec, "sector_ar": sec_ar,
            "change_pct": chg, "close": close, "volume": vol, "turnover_egp": to_v,
            "r_vol": round(rvol, 2), "cmf_20": round(cmf, 3), "rsi_14": rsi if rsi is not None else 50.0,
        })

    tot_st = len(valid_stocks) or 1
    pct50 = (above50 / tot_st) * 100.0
    pct200 = (above200 / tot_st) * 100.0
    avg_rsi = (rsi_sum / rsi_cnt) if rsi_cnt > 0 else 50.0
    avg_vr = (vol_sum / vol_cnt) if vol_cnt > 0 else 1.0
    ad_ratio = adv / (adv + dec) if (adv + dec) > 0 else 0.5
    rsi_sc = (100 - abs(avg_rsi - 50) * 2.5) if (30 <= avg_rsi <= 70) else (max(10.0, avg_rsi * 1.6) if avg_rsi < 30 else max(10.0, (100 - avg_rsi) * 1.6))
    vol_sc = min(100.0, (avg_vr / 2.0) * 100.0)
    health_score = round((ad_ratio * 100.0) * 0.3 + pct50 * 0.2 + pct200 * 0.2 + rsi_sc * 0.15 + vol_sc * 0.15)
    health_lbl = "strong" if health_score >= 70 else ("weak" if health_score < 45 else "moderate")

    movers = sorted(valid_stocks, key=lambda x: x["change_pct"], reverse=True)
    by_to = sorted(valid_stocks, key=lambda x: x["turnover_egp"], reverse=True)
    top5_sum = sum(x["turnover_egp"] for x in by_to[:5])
    top10_sum = sum(x["turnover_egp"] for x in by_to[:10])
    tot_m = round(tot_to / 1_000_000, 2)
    tot_b = round(tot_to / 1_000_000_000, 3)
    avg_m = round(avg20_to / 1_000_000, 2)
    adv_pct = round((adv_to / tot_to) * 100, 2) if tot_to > 0 else 0.0
    dec_pct = round((dec_to / tot_to) * 100, 2) if tot_to > 0 else 0.0
    top_sectors = [
        {
            "sector": b["sector"], "sector_ar": b["sector_ar"],
            "turnover_million_egp": round(b["turnover_value"] / 1_000_000, 2),
            "market_share_pct": round((b["turnover_value"] / tot_to) * 100, 2) if tot_to > 0 else 0,
            "weighted_change_pct": round(b["w_chg"] / b["turnover_value"], 2) if b["turnover_value"] > 0 else 0,
            "weighted_cmf_20": round(b["w_cmf"] / b["turnover_value"], 3) if b["turnover_value"] > 0 else 0,
            "stocks_count": b["stocks_count"], "advancing": b["advancing"], "declining": b["declining"],
            "top_stock_symbol": b["top_sym"], "top_stock_exchange": b["top_ex"], "top_stock_name": b["top_name"],
            "top_stock_turnover_million_egp": round(b["top_to"] / 1_000_000, 2),
            "top_stock_change_pct": round(b["top_chg"], 2),
        }
        for b in sorted(buckets.values(), key=lambda x: x["turnover_value"], reverse=True)[:6]
    ]
    top_liq = [
        {
            "symbol": s["symbol"], "exchange": s["exchange"], "name": s["name"], "sector": s["sector"], "sector_ar": s["sector_ar"],
            "close": round(s["close"], 2), "change_pct": round(s["change_pct"], 2),
            "turnover_million_egp": round(s["turnover_egp"] / 1_000_000, 2),
            "market_share_pct": round((s["turnover_egp"] / tot_to) * 100, 2) if tot_to > 0 else 0,
            "r_vol": s["r_vol"], "cmf_20": s["cmf_20"], "rsi_14": round(s["rsi_14"]),
        }
        for s in by_to[:8]
    ]
    verdict = "inflow" if adv_pct >= 58 else ("outflow" if dec_pct >= 58 else "balanced")
    v_ar = "دخول سيولة شرائية وتجميع" if verdict == "inflow" else ("ضغط بيعي وتصريف سيولة" if verdict == "outflow" else "توازن وتدوير سيولة انتقائي")
    v_en = "Net Liquidity Inflow & Accumulation" if verdict == "inflow" else ("Selling Pressure & Liquidity Outflow" if verdict == "outflow" else "Balanced & Selective Rotation")
    to_pct_20 = round((tot_to / avg20_to) * 100, 2) if avg20_to > 0 else 100.0
    lead_sec = top_sectors[0] if top_sectors else None
    lead_stk = top_liq[0] if top_liq else None
    sec_part_ar = f"، وتصدر قطاع «{lead_sec['sector_ar']}» التداولات بحصة {lead_sec['market_share_pct']:.1f}%" if lead_sec else ""
    stk_part_ar = f" بقيادة سهم {lead_stk['symbol']} ({lead_stk['turnover_million_egp']:.1f} مليون {curr_ar})" if lead_stk else ""
    sec_part_en = f", led by {lead_sec['sector']} ({lead_sec['market_share_pct']:.1f}% share)" if lead_sec else ""
    stk_part_en = f" and top stock {lead_stk['symbol']} ({lead_stk['turnover_million_egp']:.1f}M {currency})" if lead_stk else ""

    return {
        "market": market, "exchange": exchange, "currency": currency,
        "health_score": health_score, "health_label": health_lbl,
        "advancing": adv, "declining": dec, "unchanged": unch,
        "pct_above_ema50": pct50, "pct_above_ema200": pct200,
        "avg_rsi": avg_rsi, "volume_ratio": avg_vr,
        "top_gainers": movers[:5], "top_losers": list(reversed(movers))[:5],
        "date": latest_date, "total_stocks": tot_st,
        "liquidity": {
            "market": market, "exchange": exchange, "currency": currency, "date": latest_date,
            "total_turnover_egp": round(tot_to),
            "total_turnover_million_egp": tot_m, "total_turnover_billion_egp": tot_b,
            "avg_20d_turnover_million_egp": avg_m,
            "turnover_vs_20d_ratio": round(tot_to / avg20_to, 2) if avg20_to > 0 else 1.0,
            "turnover_vs_20d_pct": to_pct_20,
            "advancing_turnover_million_egp": round(adv_to / 1_000_000, 2),
            "advancing_turnover_pct": adv_pct,
            "declining_turnover_million_egp": round(dec_to / 1_000_000, 2),
            "declining_turnover_pct": dec_pct,
            "unchanged_turnover_million_egp": round(unch_to / 1_000_000, 2),
            "unchanged_turnover_pct": round((unch_to / tot_to) * 100, 2) if tot_to > 0 else 0,
            "top5_concentration_pct": round((top5_sum / tot_to) * 100, 2) if tot_to > 0 else 0,
            "top10_concentration_pct": round((top10_sum / tot_to) * 100, 2) if tot_to > 0 else 0,
            "unusual_volume_surge_count": surge_c,
            "positive_cmf_count": pos_cmf, "negative_cmf_count": neg_cmf,
            "accumulation_count": acc_c, "strong_accumulation_count": strong_acc,
            "distribution_count": dist_c, "strong_distribution_count": strong_dist,
            "flow_verdict": verdict, "flow_verdict_ar": v_ar, "flow_verdict_en": v_en,
            "daily_summary_ar": f"بلغ إجمالي السيولة المتداولة في السوق {tot_b:.2f} مليار {curr_ar} ({tot_m:,.2f} مليون {curr_ar}) بنسبة {to_pct_20:.1f}% من متوسط 20 جلسة ({avg_m:,.2f} مليون {curr_ar}). استحوذت الأسهم الصاعدة على {adv_pct:.1f}% من السيولة مقابل {dec_pct:.1f}% للأسهم الهابطة{sec_part_ar}{stk_part_ar}.",
            "daily_summary_en": f"Total market turnover reached {tot_b:.2f}B {currency} ({tot_m:,.2f}M {currency}), at {to_pct_20:.1f}% of the 20-day average ({avg_m:,.2f}M {currency}). Advancing stocks captured {adv_pct:.1f}% of liquidity vs {dec_pct:.1f}% in declining stocks{sec_part_en}{stk_part_en}.",
            "top_sectors": top_sectors, "top_liquidity_stocks": top_liq,
        },
    }


@router.get("/api/market/breadth")
async def api_market_breadth(request: Request):
    market = resolve_request_market(request)
    found, payload = _BREADTH_CACHE.get(market)
    if not found:
        payload = _BREADTH_SF.do(market, lambda: _load_market_breadth(market))
        if payload:
            _BREADTH_CACHE.set(market, payload, ttl=_RUN_TO_RUN_TTL)
    if not payload:
        return JSONResponse({"error": "Failed to fetch indicators"}, status_code=500, headers=_private_headers("daily-market-data"))
    headers = _daily_headers("daily-market-data") if _explicit_market_param(request) else _private_headers("daily-market-data")
    return JSONResponse(payload, headers=headers)


@router.get("/api/market/scan-settings")
async def api_market_scan_settings():
    found, scan_days = _SCAN_SETTINGS_CACHE.get("scan_days")
    if not found:
        scan_days = 450
        try:
            from api.routers.admin import _load_config
            val = (_load_config() or {}).get("scanDays")
            if isinstance(val, int) and 0 < val <= 10000:
                scan_days = val
        except Exception:
            pass
        _SCAN_SETTINGS_CACHE.set("scan_days", scan_days, ttl=300.0)
    return JSONResponse({"scanDays": scan_days}, headers={"Cache-Control": "public, s-maxage=300, stale-while-revalidate=600"})


# ── Macro Correlation (Fast Supabase market_cache reads) ─────────────────────

@router.get("/api/market/macro-correlation/symbols")
async def api_macro_symbols():
    found, cached = _MACRO_CACHE.get("symbols")
    if not found:
        def _load():
            sb = get_primary_supabase()
            if sb is None:
                return ["FWRY", "ABUK", "AMOC", "EAST", "SWDY", "HRHO", "CIEB", "MASR", "COSG", "ETEL"]
            rows = getattr(sb.table("stocks").select("symbol").eq("country", "Egypt").limit(500).execute(), "data", None) or []
            syms = sorted({r["symbol"] for r in rows if r.get("symbol")})
            return syms or ["FWRY", "ABUK", "AMOC", "EAST", "SWDY", "HRHO", "CIEB", "MASR", "COSG", "ETEL"]
        cached = _MACRO_SF.do("symbols", _load)
        _MACRO_CACHE.set("symbols", cached, ttl=3600.0)
    return JSONResponse({"symbols": cached}, headers={"Cache-Control": "public, max-age=300", "Vercel-CDN-Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400", "Vercel-Cache-Tag": "daily-market-data"})


@router.get("/api/market/macro-correlation/data")
async def api_macro_data(symbol: str = Query(default="FWRY")):
    sym = symbol.strip().upper() or "FWRY"
    if not _SYMBOL_PARAM_RE.match(sym):
        return JSONResponse({"error": "Invalid symbol"}, status_code=400)
    ck = f"data:{sym}"
    found, cached = _MACRO_CACHE.get(ck)
    if not found:
        def _load():
            sb = get_primary_supabase()
            if sb is None:
                return None
            rows = getattr(sb.table("market_cache").select("payload,computed_at").eq("cache_key", f"macro_correlation_{sym}").eq("country", "Egypt").order("computed_at", desc=True).limit(1).execute(), "data", None) or []
            if rows and rows[0].get("payload"):
                pl = _parse_json_obj(rows[0]["payload"]) or {}
                return {**pl, "computed_at": rows[0].get("computed_at")}
            return None
        cached = _MACRO_SF.do(ck, _load)
        if cached:
            _MACRO_CACHE.set(ck, cached, ttl=_RUN_TO_RUN_TTL)
    if cached:
        return JSONResponse(cached, headers=_daily_headers("daily-market-data"))
    return JSONResponse(
        {
            "symbol": sym, "corr_usd_official": 0.0, "corr_usd_parallel": 0.0, "corr_gold": 0.0,
            "rating": "Low Protection", "chart_data": [],
            "insights": "Macro-correlation data is not yet available. It will be computed during the next daily update.",
        },
        headers={"Vercel-CDN-Cache-Control": "public, s-maxage=300, stale-while-revalidate=900"},
    )


@router.get("/api/market/macro-correlation/network")
async def api_macro_network(symbol: str = Query(default="FWRY")):
    sym = symbol.strip().upper() or "FWRY"
    found, raw_pl = _MACRO_CACHE.get("hedge_scan_cache")
    if not found:
        def _load():
            sb = get_primary_supabase()
            if sb is None:
                return None
            rows = getattr(sb.table("market_cache").select("payload").eq("cache_key", "hedge_scan_cache").eq("country", "Egypt").order("computed_at", desc=True).limit(1).execute(), "data", None) or []
            return _parse_json_obj(rows[0]["payload"]) if rows and rows[0].get("payload") else None
        raw_pl = _MACRO_SF.do("hedge_scan_cache", _load)
        if raw_pl:
            _MACRO_CACHE.set("hedge_scan_cache", raw_pl, ttl=_RUN_TO_RUN_TTL)

    if not raw_pl:
        dflt = [("ABUK", 85), ("AMOC", 79), ("EAST", 74), ("SWDY", 70), ("HRHO", 65)]
        return JSONResponse({"nodes": [{"symbol": s, "weight": w} for s, w in dflt], "links": [{"source": sym, "target": s} for s, _ in dflt]}, headers={"Cache-Control": "public, s-maxage=300, stale-while-revalidate=900"})

    syms_list = raw_pl.get("symbols") or []
    root = next((s for s in syms_list if s.get("symbol") == sym), None)
    if not root:
        top5 = syms_list[:5]
        return JSONResponse({"nodes": [{"symbol": s["symbol"], "weight": 80} for s in top5], "links": [{"source": sym, "target": s["symbol"]} for s in top5]}, headers=_daily_headers("daily-market-data"))
    peers = []
    for s in syms_list:
        if s.get("symbol") == sym:
            continue
        dist = abs((s.get("corr_usd_official") or 0) - (root.get("corr_usd_official") or 0)) + abs((s.get("corr_usd_parallel") or 0) - (root.get("corr_usd_parallel") or 0)) + abs((s.get("corr_gold") or 0) - (root.get("corr_gold") or 0))
        peers.append({"symbol": s["symbol"], "weight": min(99, max(30, round((1 - dist / 3.0) * 100)))})
    peers.sort(key=lambda x: x["weight"], reverse=True)
    peers = peers[:8]
    return JSONResponse({"nodes": peers, "links": [{"source": sym, "target": p["symbol"]} for p in peers]}, headers=_daily_headers("daily-market-data"))


@router.get("/api/market/macro-correlation/scan")
async def api_macro_scan():
    found, cached = _MACRO_CACHE.get("macro_scan")
    if not found:
        def _load():
            sb = get_primary_supabase()
            if sb is None:
                return None
            rows = getattr(sb.table("market_cache").select("payload,computed_at").eq("cache_key", "macro_correlation_scan").eq("country", "Egypt").order("computed_at", desc=True).limit(1).execute(), "data", None) or []
            if rows and rows[0].get("payload"):
                return {**(_parse_json_obj(rows[0]["payload"]) or {}), "computed_at": rows[0].get("computed_at")}
            return None
        cached = _MACRO_SF.do("macro_scan", _load)
        if cached:
            _MACRO_CACHE.set("macro_scan", cached, ttl=_RUN_TO_RUN_TTL)
    if cached:
        return JSONResponse(cached, headers=_daily_headers("daily-market-data"))
    return JSONResponse({"updated_at": datetime.now(timezone.utc).isoformat(), "symbols": []})


# ── EGX30, Benchmark, Chart Events, Models, Adaptive, Disclosures SVG ───────

@router.get("/api/egx30/monthly")
async def api_egx30_monthly():
    found, cached = _EGX30_CACHE.get("monthly")
    if not found:
        def _load():
            sb = get_primary_supabase()
            if sb is None:
                return []
            rows: List[Dict[str, Any]] = []
            offset = 0
            while True:
                batch = getattr(sb.table("stock_prices").select("date,open,high,low,close").eq("symbol", "EGX30").eq("exchange", "INDX").order("date", desc=False).range(offset, offset + 999).execute(), "data", None) or []
                rows.extend(batch)
                if len(batch) < 1000:
                    break
                offset += 1000
            grouped: Dict[str, Dict[str, Any]] = {}
            for r in sorted((r for r in rows if isinstance(r.get("date"), str) and len(r["date"]) >= 10), key=lambda x: x["date"]):
                c = _finite(r.get("close"))
                if c is None:
                    continue
                o = _finite(r.get("open")) or c
                h = _finite(r.get("high")) or c
                lo = _finite(r.get("low")) or c
                mk = r["date"][:7]
                g = grouped.get(mk)
                if not g:
                    grouped[mk] = {"month": mk, "start_date": r["date"], "end_date": r["date"], "open": o, "high": h, "low": lo, "close": c}
                else:
                    if r["date"] < g["start_date"]:
                        g["start_date"], g["open"] = r["date"], o
                    if r["date"] > g["end_date"]:
                        g["end_date"], g["close"] = r["date"], c
                    g["high"] = max(g["high"], h)
                    g["low"] = min(g["low"], lo)
            return [grouped[k] for k in sorted(grouped.keys())]
        cached = _EGX30_SF.do("monthly", _load)
        _EGX30_CACHE.set("monthly", cached, ttl=_RUN_TO_RUN_TTL)
    return JSONResponse({"months": cached}, headers=_daily_headers("daily-market-data"))


@router.get("/api/egx30/range")
async def api_egx30_range(start: str = Query(default=""), end: str = Query(default="")):
    if not start or not end:
        return JSONResponse({"error": "Missing start/end"}, status_code=400)
    s_str = start.split("T")[0]
    e_str = end.split("T")[0]
    ck = f"range:{s_str}:{e_str}"
    found, cached = _EGX30_CACHE.get(ck)
    if not found:
        def _load():
            sb = get_primary_supabase()
            if sb is None:
                return None
            period = getattr(sb.table("stock_prices").select("date,open,close").eq("symbol", "EGX30").eq("exchange", "INDX").gte("date", s_str).lte("date", e_str).order("date", desc=False).limit(2000).execute(), "data", None) or []
            if len(period) < 2:
                return None
            p0 = _finite(period[0].get("open")) or _finite(period[0].get("close"))
            p1 = _finite(period[-1].get("close"))
            if not p0 or p1 is None:
                return None
            return round(((p1 - p0) / p0) * 100.0, 2)
        cached = _EGX30_SF.do(ck, _load)
        _EGX30_CACHE.set(ck, cached, ttl=_RUN_TO_RUN_TTL)
    return JSONResponse({"return_pct": cached}, headers=_daily_headers("daily-market-data"))


@router.get("/api/recommendations/benchmark")
async def api_recommendations_benchmark(
    from_date: str = Query(default="", alias="from"),
    to_date: str = Query(default="", alias="to"),
):
    v_from = _valid_iso_date(from_date)
    v_to = _valid_iso_date(to_date)
    if not v_from or not v_to or v_from > v_to:
        return JSONResponse({"error": "Valid from and to dates are required."}, status_code=400)
    if (datetime.strptime(v_to, "%Y-%m-%d") - datetime.strptime(v_from, "%Y-%m-%d")).days > 5 * 366:
        return JSONResponse({"error": "Benchmark range is limited to five years."}, status_code=400)

    ck = f"{v_from}:{v_to}"
    found, cached = _BENCHMARK_CACHE.get(ck)
    if not found:
        def _load():
            sb = get_primary_supabase()
            if sb is None:
                raise RuntimeError("Benchmark unavailable")
            q_from = (datetime.strptime(v_from, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
            assets_cfg = (
                {"symbol": "EGX30", "exchange": "INDX", "kind": "index", "nameAr": "مؤشر EGX30", "nameEn": "EGX30 Index"},
                {"symbol": "EGREF", "exchange": "EGX", "kind": "fund", "nameAr": "صندوق المصريين العقاري", "nameEn": "Egyptians Real Estate Fund"},
                {"symbol": "KASABF", "exchange": "EGX", "kind": "fund", "nameAr": "وثائق كاسب", "nameEn": "KASAB Fund Certificates"},
            )

            def _load_asset(cfg):
                prices = []
                offset = 0
                while offset < 5000:
                    rows = getattr(sb.table("stock_prices").select("date,close").eq("symbol", cfg["symbol"]).eq("exchange", cfg["exchange"]).gte("date", q_from).lte("date", v_to).order("date", desc=False).range(offset, min(offset + 999, 4999)).execute(), "data", None) or []
                    for r in rows:
                        c = _finite(r.get("close"))
                        if r.get("date") and c is not None and c > 0:
                            prices.append({"date": str(r["date"])[:10], "close": c})
                    if len(rows) < 1000:
                        break
                    offset += 1000
                return {**cfg, "prices": prices, "truncated": len(prices) >= 5000, "asOf": prices[-1]["date"] if prices else None}

            with ThreadPoolExecutor(max_workers=3) as pool:
                return {"from": v_from, "to": v_to, "assets": list(pool.map(_load_asset, assets_cfg))}

        try:
            cached = _BENCHMARK_SF.do(ck, _load)
            _BENCHMARK_CACHE.set(ck, cached, ttl=_RUN_TO_RUN_TTL)
        except Exception:
            return JSONResponse({"error": "Benchmark market data is temporarily unavailable."}, status_code=503, headers={"Cache-Control": "public, s-maxage=300, stale-if-error=86400"})
    return JSONResponse(cached, headers=_daily_headers("daily-market-data"))


_CHART_EVENTS_WARNING = "إعلانات مصنفة من مصادر عامة وليست أحداثًا متحققًا منها. راجع المصدر وتاريخ تنفيذ الحدث؛ عدم وجود نتائج لا يؤكد عدم وجود أحداث."


@router.get("/api/chart-events")
async def api_chart_events(request: Request):
    qp = request.query_params
    sym = re.sub(r"\.CA$", "", (qp.get("symbol") or "").strip().upper())
    if not _SYMBOL_PARAM_RE.match(sym) or ("exchange" in qp and qp.get("exchange") != "EGX"):
        return JSONResponse({"error": "Invalid EGX symbol"}, status_code=400, headers={"Cache-Control": "no-store"})
    today = get_cairo_date_str()
    today_dt = datetime.strptime(today, "%Y-%m-%d")
    start = qp.get("start_date") or (today_dt - timedelta(days=90)).strftime("%Y-%m-%d")
    end = qp.get("end_date") or (today_dt + timedelta(days=365)).strftime("%Y-%m-%d")
    v_s, v_e = _valid_iso_date(start), _valid_iso_date(end)
    if not v_s or not v_e or v_s > v_e or (datetime.strptime(v_e, "%Y-%m-%d") - datetime.strptime(v_s, "%Y-%m-%d")).days > 730:
        return JSONResponse({"error": "Invalid date range (maximum 730 days)"}, status_code=400, headers={"Cache-Control": "no-store"})

    ck = f"{sym}:{v_s}:{v_e}"
    found, events = _EVENTS_CACHE.get(ck)
    if not found:
        def _load():
            sb = get_primary_supabase()
            if sb is None:
                return []
            rows = getattr(sb.table("corporate_actions").select("symbol,action_date,title,action_type,url,source,confidence").eq("exchange", "EGX").eq("symbol", sym).gte("action_date", v_s).lte("action_date", v_e).not_.is_("action_date", "null").not_.is_("url", "null").order("action_date", desc=False).limit(30).execute(), "data", None) or []
            seen: set[str] = set()
            out: List[Dict[str, Any]] = []
            for r in rows:
                ad = _valid_iso_date(r.get("action_date"))
                title = r.get("title")
                raw_url = r.get("url")
                if r.get("symbol") != sym or not ad or ad < v_s or ad > v_e or not isinstance(title, str) or not title.strip() or not isinstance(raw_url, str):
                    continue
                if not re.match(r"^https?://", raw_url, re.IGNORECASE) or "@" in raw_url.split("/")[2]:
                    continue
                k = f"{ad}|{raw_url}|{title}"
                if k in seen:
                    continue
                seen.add(k)
                conf = _finite(r.get("confidence"))
                out.append({
                    "symbol": sym, "date": ad, "title": title.strip()[:500],
                    "type": str(r.get("action_type") or "other")[:80],
                    "url": raw_url,
                    "source": str(r.get("source") or raw_url.split("/")[2]).strip()[:200],
                    "confidence": conf if (conf is not None and 0 <= conf <= 1) else None,
                })
                if len(out) >= 30:
                    break
            return sorted(out, key=lambda x: x["date"])
        events = _EVENTS_SF.do(ck, _load)
        _EVENTS_CACHE.set(ck, events, ttl=3600.0)
    return JSONResponse({"events": events, "warning": _CHART_EVENTS_WARNING}, headers=_daily_headers("daily-news-data"))


@router.get("/api/models/list")
async def api_models_list():
    found, models = _MODELS_CACHE.get("list")
    if not found:
        def _load():
            sb = get_primary_supabase()
            if sb is None:
                return [{"name": "EGX_DEFAULT", "accuracy": 0.75, "exchange": "EGX"}]
            rows = getattr(sb.table("model_metadata").select("name,accuracy,exchange,created_at,metadata").order("created_at", desc=True).limit(100).execute(), "data", None) or []
            return [{"name": r.get("name"), "accuracy": r.get("accuracy") or 0.0, "exchange": r.get("exchange") or "EGX", "created_at": r.get("created_at"), "metadata": r.get("metadata") or {}} for r in rows]
        models = _MODELS_SF.do("list", _load)
        _MODELS_CACHE.set("list", models, ttl=3600.0)
    return JSONResponse({"models": models}, headers={"Cache-Control": "public, max-age=300", "Vercel-CDN-Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400"})


@router.get("/api/models/local")
async def api_models_local():
    found, models = _MODELS_CACHE.get("local")
    if not found:
        def _load():
            sb = get_primary_supabase()
            if sb is None:
                return []
            return getattr(sb.table("model_metadata").select("name,accuracy,exchange,created_at,metadata").order("created_at", desc=True).limit(100).execute(), "data", None) or []
        models = _MODELS_SF.do("local", _load)
        _MODELS_CACHE.set("local", models, ttl=3600.0)
    return JSONResponse({"models": models}, headers={"Cache-Control": "public, max-age=300", "Vercel-CDN-Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400"})


@router.get("/api/adaptive/recommendation")
async def api_adaptive_recommendation(exchange: str = Query(default="EGX")):
    ex = exchange.strip().upper() or "EGX"
    country = "Egypt" if ex == "EGX" else ex
    found, cached = _MODELS_CACHE.get(f"adaptive:{ex}")
    if not found:
        def _load():
            sb = get_primary_supabase()
            if sb is None:
                return None
            rows = getattr(sb.table("market_cache").select("payload,computed_at").eq("cache_key", f"adaptive_recommendation_{ex}").eq("country", country).order("computed_at", desc=True).limit(1).execute(), "data", None) or []
            if rows and rows[0].get("payload"):
                pl = _parse_json_obj(rows[0]["payload"]) or {}
                return {**pl, "cached": True, "computed_at": rows[0].get("computed_at")}
            m_rows = getattr(sb.table("model_metadata").select("name,exchange,accuracy,metadata,created_at").eq("exchange", ex).order("accuracy", desc=True).limit(5).execute(), "data", None) or []
            if not m_rows:
                return None
            best = m_rows[0]
            acc = _num(best.get("accuracy"))
            return {
                "exchange": ex, "recommended_model": best["name"], "recommended_model_path": best["name"],
                "regime": "cached_model_metadata", "confidence": acc, "momentum_score": 0, "volatility_score": 0,
                "trend_strength": 0, "reason": "Served from model_metadata (daily update pending).",
                "candidate_models": [m["name"] for m in m_rows if m.get("name")], "candidate_count": len(m_rows),
                "meets_min_confidence": acc >= 0.55, "min_confidence": 0.55, "as_of": best.get("created_at"),
            }
        cached = _MODELS_SF.do(f"adaptive:{ex}", _load)
        if cached:
            _MODELS_CACHE.set(f"adaptive:{ex}", cached, ttl=3600.0)
    return JSONResponse(cached or {"exchange": ex, "recommended_model": None}, headers={"Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400"})


def _wrap_svg_lines(text: str, max_chars: int, max_lines: int) -> List[str]:
    words = re.sub(r"\s+", " ", (text or "")).strip().split(" ")
    lines: List[str] = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if len(cand) <= max_chars:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) >= max_lines - 1:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


@router.get("/api/disclosures/image/{item_id}")
async def api_disclosure_image(item_id: str):
    if not _DISCLOSURE_ID_RE.match(item_id):
        return Response(status_code=400)
    found, svg = _SVG_CACHE.get(item_id)
    if not found:
        sb = get_primary_supabase()
        item = None
        if sb is not None:
            rows = getattr(sb.table("egx_disclosures").select("id,symbol,company_name,disclosure_type,disclosure_date,title,raw_content,ai_summary,sentiment,action_type,party_name,party_role,shares_count,stake_before,stake_after,metadata").eq("id", item_id).limit(1).execute(), "data", None) or []
            item = rows[0] if rows else None
        if not item:
            item = {
                "id": item_id, "symbol": "EGX", "company_name": "البورصة المصرية",
                "disclosure_type": "material_event", "disclosure_date": get_cairo_date_str(),
                "title": "مستند إفصاح رسمي مسجل بقاعدة بيانات البورصة المصرية",
                "raw_content": "تم أرشفة هذا الإفصاح في سجل إفصاحات البورصة المصرية.",
                "ai_summary": "إفصاح رسمي مسجل.", "sentiment": "neutral",
            }
        dt = item.get("disclosure_type")
        type_map = {
            "insider_trading": "نموذج إفصاح تعاملات داخليين ومجموعات مرتبطة",
            "major_shareholders": "نموذج إفصاح هيكل المساهمين (المادة 30)",
            "board_resolution": "نموذج إفصاح قرارات مجلس الإدارة",
            "financial_results": "نموذج إفصاح نتائج أعمال وقوائم مالية",
        }
        type_lbl = xml_escape(type_map.get(dt, "نموذج إفصاح جوهري - البورصة المصرية"))
        is_bull = item.get("sentiment") == "bullish" or item.get("action_type") == "buy"
        is_bear = item.get("sentiment") == "bearish" or item.get("action_type") == "sell"
        accent = "#00C853" if is_bull else ("#FF1744" if is_bear else "#D97706")
        stamp = "إشارة إيجابية • تجميع / دعم" if is_bull else ("إشارة بيعية • تسييل / تخارج" if is_bear else "إفصاح رسمي محايد • موثق")
        shares_str = f"{int(_num(item.get('shares_count'))):,} سهم" if item.get("shares_count") else "غير محدد كمياً"
        stake_str = f"{item.get('stake_before') or '—'}% ← {item.get('stake_after') or '—'}%" if (item.get("stake_before") is not None or item.get("stake_after") is not None) else "وفق هيكل الملكية المودع"
        t_lines = _wrap_svg_lines(str(item.get("title") or ""), 68, 3)
        r_lines = _wrap_svg_lines(str(item.get("raw_content") or item.get("title") or ""), 74, 4)
        a_lines = _wrap_svg_lines(str(item.get("ai_summary") or ""), 72, 4)
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        takeaway = xml_escape(str(meta.get("key_takeaway") or ""))
        t_svg = "\n  ".join(f'<text x="840" y="{332 + i * 24}" font-family="Tahoma, Arial, sans-serif" font-size="15" font-weight="bold" fill="#111827" text-anchor="end" direction="rtl">{xml_escape(l)}</text>' for i, l in enumerate(t_lines))
        r_svg = "\n  ".join(f'<text x="840" y="{332 + len(t_lines) * 24 + 8 + i * 20}" font-family="Tahoma, Arial, sans-serif" font-size="12.5" fill="#4b5563" text-anchor="end" direction="rtl">{xml_escape(l)}</text>' for i, l in enumerate(r_lines[:2]))
        a_svg = "\n  ".join(f'<text x="840" y="{505 + i * 22}" font-family="Tahoma, Arial, sans-serif" font-size="13.5" font-weight="bold" fill="#1f2937" text-anchor="end" direction="rtl">{xml_escape(l)}</text>' for i, l in enumerate(a_lines))
        tk_svg = f'<text x="840" y="588" font-family="Tahoma, Arial, sans-serif" font-size="12.5" font-weight="bold" fill="{accent}" text-anchor="end" direction="rtl">★ الخلاصة الاستثمارية: {takeaway}</text>' if takeaway else ""
        svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 680" width="900" height="680">
  <defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M 24 0 L 0 0 0 24" fill="none" stroke="#e5e7eb" stroke-width="0.7"/></pattern></defs>
  <rect width="900" height="680" fill="#fcfaf2" /><rect width="900" height="680" fill="url(#grid)" opacity="0.55" />
  <rect x="18" y="18" width="864" height="644" fill="#ffffff" stroke="#111827" stroke-width="4" />
  <rect x="26" y="26" width="848" height="628" fill="none" stroke="#111827" stroke-width="1.5" stroke-dasharray="6,4" />
  <rect x="18" y="18" width="864" height="88" fill="#111827" /><rect x="18" y="102" width="864" height="6" fill="#FFE600" />
  <text x="855" y="54" font-family="Tahoma, Arial, sans-serif" font-size="22" font-weight="bold" fill="#FFE600" text-anchor="end" direction="rtl">البورصة المصرية • سجل الإفصاحات الرسمية والشفافية</text>
  <text x="855" y="82" font-family="Tahoma, Arial, sans-serif" font-size="14" font-weight="bold" fill="#ffffff" text-anchor="end" direction="rtl">{type_lbl}</text>
  <rect x="38" y="34" width="185" height="54" fill="#1f2937" stroke="#FFE600" stroke-width="2" />
  <text x="130" y="55" font-family="Courier New, monospace" font-size="13" font-weight="bold" fill="#FFE600" text-anchor="middle">REF #{xml_escape(str(item.get('id', ''))[:8].upper())}</text>
  <text x="130" y="77" font-family="Courier New, monospace" font-size="13" font-weight="bold" fill="#e5e7eb" text-anchor="middle">DATE: {xml_escape(str(item.get('disclosure_date') or ''))}</text>
  <rect x="42" y="124" width="816" height="64" fill="#f3f4f6" stroke="#111827" stroke-width="2.5" />
  <rect x="42" y="124" width="140" height="64" fill="#FFE600" stroke="#111827" stroke-width="2.5" />
  <text x="112" y="163" font-family="Arial, sans-serif" font-size="24" font-weight="900" fill="#111827" text-anchor="middle">{xml_escape(str(item.get('symbol') or 'EGX'))}</text>
  <text x="838" y="152" font-family="Tahoma, Arial, sans-serif" font-size="13" font-weight="bold" fill="#6b7280" text-anchor="end" direction="rtl">الشركة المفصحة / الجهة المصدرة:</text>
  <text x="838" y="176" font-family="Tahoma, Arial, sans-serif" font-size="18" font-weight="bold" fill="#111827" text-anchor="end" direction="rtl">{xml_escape(str(item.get('company_name') or 'البورصة المصرية'))}</text>
  <rect x="42" y="202" width="816" height="68" fill="#ffffff" stroke="#111827" stroke-width="2" />
  <line x1="314" y1="202" x2="314" y2="270" stroke="#111827" stroke-width="2" /><line x1="586" y1="202" x2="586" y2="270" stroke="#111827" stroke-width="2" />
  <text x="842" y="224" font-family="Tahoma, Arial, sans-serif" font-size="11" font-weight="bold" fill="#6b7280" text-anchor="end" direction="rtl">الطرف المفصح / الصفة:</text>
  <text x="842" y="246" font-family="Tahoma, Arial, sans-serif" font-size="13" font-weight="bold" fill="#111827" text-anchor="end" direction="rtl">{xml_escape(str(item.get('party_name') or 'إدارة الشركة / المساهمون'))}</text>
  <text x="842" y="263" font-family="Tahoma, Arial, sans-serif" font-size="11" fill="#4b5563" text-anchor="end" direction="rtl">({xml_escape(str(item.get('party_role') or 'مفصح رسمي'))})</text>
  <text x="570" y="224" font-family="Tahoma, Arial, sans-serif" font-size="11" font-weight="bold" fill="#6b7280" text-anchor="end" direction="rtl">حجم التعامل / الكمية المسجلة:</text>
  <text x="570" y="250" font-family="Tahoma, Arial, sans-serif" font-size="15" font-weight="bold" fill="{accent}" text-anchor="end" direction="rtl">{xml_escape(shares_str)}</text>
  <text x="298" y="224" font-family="Tahoma, Arial, sans-serif" font-size="11" font-weight="bold" fill="#6b7280" text-anchor="end" direction="rtl">نسبة المساهمة (قبل / بعد):</text>
  <text x="298" y="250" font-family="Tahoma, Arial, sans-serif" font-size="13" font-weight="bold" fill="#111827" text-anchor="end" direction="rtl">{xml_escape(stake_str)}</text>
  <rect x="42" y="284" width="816" height="155" fill="#fafafa" stroke="#111827" stroke-width="2" />
  <rect x="688" y="284" width="170" height="26" fill="#111827" />
  <text x="773" y="302" font-family="Tahoma, Arial, sans-serif" font-size="12" font-weight="bold" fill="#FFE600" text-anchor="middle" direction="rtl">نص بيان الإفصاح الرسمي</text>
  {t_svg}
  {r_svg}
  <rect x="42" y="454" width="816" height="145" fill="#fffbeb" stroke="#111827" stroke-width="2.5" />
  <rect x="648" y="454" width="210" height="28" fill="#FFE600" stroke="#111827" stroke-width="2" />
  <text x="753" y="473" font-family="Tahoma, Arial, sans-serif" font-size="12.5" font-weight="bold" fill="#111827" text-anchor="middle" direction="rtl">تحليل الذكاء الاصطناعي • EGX BOTS</text>
  {a_svg}
  {tk_svg}
  <rect x="42" y="610" width="260" height="34" fill="{accent}" stroke="#111827" stroke-width="2" />
  <text x="172" y="632" font-family="Tahoma, Arial, sans-serif" font-size="13" font-weight="bold" fill="#ffffff" text-anchor="middle" direction="rtl">{xml_escape(stamp)}</text>
  <text x="855" y="632" font-family="Courier New, Tahoma, sans-serif" font-size="12" font-weight="bold" fill="#374151" text-anchor="end">EGX-DISCLOSURE-ID: {xml_escape(str(item.get('id')))} • VERIFIED BY EGXBOTS.COM</text>
</svg>"""
        _SVG_CACHE.set(item_id, svg, ttl=_RUN_TO_RUN_TTL)
    return Response(content=svg, media_type="image/svg+xml; charset=utf-8", headers={"Cache-Control": "public, s-maxage=86400, stale-while-revalidate=604800"})


_DIVIDENDS_CACHE = BoundedTTLCache(max_entries=64, default_ttl=1800.0)
_DIVIDENDS_SF = SingleFlight()


@router.get("/api/market/dividends")
async def api_market_dividends(
    market: str = Query(default="egx"),
    symbol: Optional[str] = Query(default=None),
):
    norm_mkt = (market or "egx").strip().lower()
    if norm_mkt in ("tadawul", "sa", "saudi"):
        norm_mkt = "tasi"
    elif norm_mkt in ("qse", "qe"):
        norm_mkt = "qatar"
    elif norm_mkt in ("dfm", "adx"):
        norm_mkt = "uae"
    if norm_mkt not in ("egx", "tasi", "qatar", "uae"):
        norm_mkt = "egx"

    clean_sym = (symbol or "").strip().upper().split(".")[0] or None
    if clean_sym and not _SYMBOL_PARAM_RE.match(clean_sym):
        return JSONResponse({"error": "Invalid symbol"}, status_code=400)

    ck = f"div:{norm_mkt}:{clean_sym or 'all'}"
    found, cached = _DIVIDENDS_CACHE.get(ck)
    if not found:
        def _load():
            from api.dividends_engine import get_cached_market_dividends
            return get_cached_market_dividends(norm_mkt, symbol=clean_sym)

        cached = _DIVIDENDS_SF.do(ck, _load)
        _DIVIDENDS_CACHE.set(ck, cached, ttl=1800.0)

    return JSONResponse(
        cached,
        headers={
            "Cache-Control": "public, s-maxage=900, stale-while-revalidate=3600",
            "Vercel-CDN-Cache-Control": "public, s-maxage=1800, stale-while-revalidate=86400",
            "Vercel-Cache-Tag": "daily-market-data",
        },
    )


_DISCLOSURE_PAGE_COLS = (
    "id, symbol, company_name, disclosure_type, disclosure_date, title, "
    "ai_summary, sentiment, action_type, shares_count, stake_before, stake_after, "
    "party_name, party_role, source_url, metadata"
)
_GCC_METALS_EXCHANGES = ("DFM", "ADX", "QSE", "COMMODITIES")


def _load_disclosures_page_data() -> Dict[str, Any]:
    sb = get_primary_supabase()
    if sb is None:
        return {
            "items": [],
            "allPool": [],
            "stats": {"total": 0, "buys": 0, "sells": 0, "shareholding": 0},
            "priceMap": {},
        }

    def _run_page():
        return (
            sb.table("egx_disclosures")
            .select(_DISCLOSURE_PAGE_COLS, count="exact")
            .order("disclosure_date", desc=True)
            .order("created_at", desc=True)
            .limit(24)
            .execute()
        )

    def _run_pool():
        return (
            sb.table("egx_disclosures")
            .select(_DISCLOSURE_PAGE_COLS)
            .order("disclosure_date", desc=True)
            .limit(2000)
            .execute()
        )

    def _run_prices():
        return sb.table("stock_technical_indicators").select("symbol, close, change_pct, r_vol").limit(350).execute()

    def _run_fundamentals():
        return sb.table("stock_fundamentals").select("symbol, data").limit(350).execute()

    with ThreadPoolExecutor(max_workers=4) as pool:
        f_page = pool.submit(_run_page)
        f_pool = pool.submit(_run_pool)
        f_prices = pool.submit(_run_prices)
        f_fund = pool.submit(_run_fundamentals)
        page_res = f_page.result()
        pool_res = f_pool.result()
        prices_res = f_prices.result()
        fund_res = f_fund.result()

    all_disclosures = list(getattr(pool_res, "data", None) or [])
    items = list(getattr(page_res, "data", None) or [])

    price_map: Dict[str, Dict[str, Any]] = {}
    for row in getattr(prices_res, "data", None) or []:
        sym = str(row.get("symbol") or "").strip().upper()
        if sym and row.get("close") is not None:
            close_val = float(row["close"])
            price_map[sym] = {
                "close": close_val,
                "change_pct": float(row["change_pct"]) if row.get("change_pct") is not None else 0.0,
                "r_vol": float(row["r_vol"]) if row.get("r_vol") is not None else None,
            }

    from api.corporate_events_engine import classify_event_reality_check

    def _attach_rc(rows_list: List[Dict[str, Any]]) -> None:
        for d in rows_list:
            sym_d = str(d.get("symbol") or "").strip().upper()
            pinfo = price_map.get(sym_d)
            if not pinfo:
                continue
            rc = classify_event_reality_check(
                sentiment=d.get("sentiment"),
                action_type=d.get("action_type"),
                title=d.get("title"),
                change_pct=pinfo.get("change_pct"),
                r_vol=pinfo.get("r_vol"),
            )
            if rc:
                d["reality_check"] = rc

    _attach_rc(items)
    _attach_rc(all_disclosures)

    for row in getattr(fund_res, "data", None) or []:
        sym = str(row.get("symbol") or "").strip().upper()
        raw_data = row.get("data")
        if isinstance(raw_data, str):
            try:
                raw_data = json.loads(raw_data)
            except Exception:
                raw_data = None
        if not sym or not isinstance(raw_data, dict):
            continue
        mc = raw_data.get("marketCap")
        if isinstance(mc, (int, float)) and not isinstance(mc, bool) and mc > 0:
            if sym in price_map:
                price_map[sym]["market_cap"] = mc
                if price_map[sym]["close"] > 0:
                    price_map[sym]["total_shares"] = round(mc / price_map[sym]["close"])
            else:
                price_map[sym] = {
                    "close": 0.0,
                    "change_pct": 0.0,
                    "market_cap": mc,
                }

    total = getattr(page_res, "count", None)
    if total is None:
        total = len(all_disclosures)
    buys = sum(1 for d in all_disclosures if d.get("action_type") == "buy" or d.get("sentiment") == "bullish")
    sells = sum(1 for d in all_disclosures if d.get("action_type") == "sell" or d.get("sentiment") == "bearish")
    shareholding = sum(
        1
        for d in all_disclosures
        if d.get("disclosure_type") == "major_shareholders" or d.get("stake_after") is not None
    )

    return {
        "items": items,
        "allPool": all_disclosures,
        "stats": {
            "total": int(total),
            "buys": buys,
            "sells": sells,
            "shareholding": shareholding,
        },
        "priceMap": price_map,
    }


@router.get("/api/public/disclosures-page-data")
async def api_public_disclosures_page_data():
    """Cached initial payload for SSR /disclosures page (excludes unused raw_content)."""
    found, cached = _DISCLOSURES_PAGE_CACHE.get("egx")
    if not found:
        cached = _DISCLOSURES_PAGE_SF.do("egx", _load_disclosures_page_data)
        if cached.get("allPool") or cached.get("items"):
            _DISCLOSURES_PAGE_CACHE.set("egx", cached, ttl=_RUN_TO_RUN_TTL)
    return JSONResponse(cached, headers=_daily_headers("daily-disclosures"))


def _load_gcc_metals_directory_with_prices() -> List[Dict[str, Any]]:
    sb = get_market_supabase("tasi")
    if sb is None:
        return []

    exchanges = list(_GCC_METALS_EXCHANGES)

    def _run_stocks():
        return (
            sb.table("stocks")
            .select("symbol,exchange,name,name_ar,sector,currency,updated_at")
            .in_("exchange", exchanges)
            .eq("is_active", True)
            .order("symbol", desc=False)
            .limit(500)
            .execute()
        )

    def _run_indicators():
        return (
            sb.table("stock_technical_indicators")
            .select("symbol,exchange,close,change_pct,rsi_14,date")
            .in_("exchange", exchanges)
            .limit(500)
            .execute()
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_stocks = pool.submit(_run_stocks)
        f_ind = pool.submit(_run_indicators)
        stocks_res = f_stocks.result()
        ind_res = f_ind.result()

    ind_map: Dict[str, Dict[str, Any]] = {}
    for row in getattr(ind_res, "data", None) or []:
        ex = str(row.get("exchange") or "").strip().upper()
        sym = str(row.get("symbol") or "").strip().upper()
        if sym:
            ind_map[f"{ex}:{sym}"] = row

    by_sym: Dict[str, Dict[str, Any]] = {}
    for row in getattr(stocks_res, "data", None) or []:
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        ex = str(row.get("exchange") or "").strip()
        ind = ind_map.get(f"{ex.upper()}:{sym}") or {}
        entry: Dict[str, Any] = {
            "symbol": sym,
            "name": str(row.get("name") or sym).strip(),
            "sector": str(row.get("sector") or "").strip(),
            "marketCap": None,
            "exchange": ex,
            "currency": str(row.get("currency") or "USD").strip(),
            "close": float(ind["close"]) if ind.get("close") is not None else None,
            "changePct": float(ind["change_pct"]) if ind.get("change_pct") is not None else None,
            "rsi14": float(ind["rsi_14"]) if ind.get("rsi_14") is not None else None,
            "priceDate": str(ind["date"])[:10] if ind.get("date") else None,
        }
        if row.get("name_ar"):
            entry["nameAr"] = str(row["name_ar"]).strip()
        if row.get("updated_at"):
            entry["updatedAt"] = str(row["updated_at"])
        by_sym[sym] = entry

    return sorted(by_sym.values(), key=lambda x: x["symbol"])


@router.get("/api/public/gcc-metals-directory")
async def api_public_gcc_metals_directory():
    """Cached GCC (UAE/Qatar) & Metals directory with latest prices/RSI."""
    found, cached = _GCC_METALS_DIR_CACHE.get("all")
    if not found:
        cached = _GCC_METALS_DIR_SF.do("all", _load_gcc_metals_directory_with_prices)
        if cached:
            _GCC_METALS_DIR_CACHE.set("all", cached, ttl=_RUN_TO_RUN_TTL)
    return JSONResponse({"stocks": cached}, headers=_daily_headers("daily-symbols"))
