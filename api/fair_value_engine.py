"""
Unified Institutional Fair Value Engine (Single Source of Truth).

Used identically across:
1. Public `/fair-value` report (`api/routers/offload_public.py`)
2. AI Chatbot (`get_fair_value`, `get_stock`, and `quant_engine` in `api/agentic_chat/tools_execution.py`)
3. Mirrored in TypeScript (`web/src/lib/market/fair-value.ts`) for `/stocks/[symbol]`.

Key guarantees:
- Eliminates generic placeholder sectors ("سوق الأسهم المصرية") so peer medians reflect true sectors.
- Normalizes EGP-denominated per-share fundamentals on USD-traded EGX symbols (e.g. NDRL, FAITA, SAIB, EGBE).
- Normalizes full or partial stock-split artifacts (e.g. POUL, ORHD) without corrupting post-split fields.
- Applies realistic ROE-tiered haircuts (0.65x–0.80x BVPS) on loss-making companies (e.g. COSG, SVCE, EPPK)
  and never labels a loss-making company as "fair" ("في النطاق العادل").
- Does NOT artificially prop up speculative overvalued stocks with a `0.55 * close` bubble floor, and keeps
  `formulaSubstitutionAr` 100% arithmetically accurate even when the `+65%` upper safety cap triggers.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from api.egx_canonical_names import CANONICAL_EGX_STOCK_NAMES
from api.saudi_stock_aliases import SAUDI_STOCK_NAMES_AR, is_saudi_symbol
from api.sharia_stocks import is_sharia_compliant

try:
    from api.agentic_chat.market_registry import EGX_USD_SYMBOLS
except Exception:
    EGX_USD_SYMBOLS = frozenset({
        "ADPC", "ANFI", "APSW", "CERA", "DAPH", "EGBE", "EGSA", "EGTS",
        "EKHO", "FAITA", "GPPL", "GRCA", "GMCI", "MAFI", "MENA", "MOIL",
        "MOSC_USD", "NAHO", "NDRL", "NINH", "PHTV", "SAIB", "SCTS",
        "SMFR", "TRTO", "UNIP_USD", "VERT",
    })

GENERIC_PLACEHOLDER_SECTORS = frozenset({
    "",
    "سوق الأسهم المصرية",
    "البورصة المصرية",
    "سوق الأسهم السعودية",
    "تداول",
    "قطاعات متنوعة",
    "غير مصنف",
})

SECTOR_AR_MAP: Dict[str, str] = {
    # Banking & Financial Services
    "regional banks": "بنوك",
    "major banks": "بنوك",
    "banks": "بنوك",
    "investment banks/brokers": "خدمات مالية غير مصرفية",
    "financial conglomerates": "خدمات مالية غير مصرفية",
    "investment managers": "خدمات مالية غير مصرفية",
    "finance/rental/leasing": "خدمات مالية غير مصرفية",
    "multi-line insurance": "تأمين وخدمات مالية",
    "property/casualty insurance": "تأمين وخدمات مالية",
    "life/health insurance": "تأمين وخدمات مالية",
    "insurance": "تأمين وخدمات مالية",
    "finance": "بنوك وخدمات مالية",
    # Real Estate & Construction
    "real estate development": "عقارات وإنشاءات",
    "real estate": "عقارات وإنشاءات",
    "homebuilding": "عقارات وإنشاءات",
    "engineering & construction": "عقارات ومقاولات وإنشاءات",
    "industrial services": "عقارات ومقاولات وإنشاءات",
    # Food, Milling, Oils & Consumer Staples
    "agricultural commodities/milling": "أغذية ومطاحن وزيوت",
    "household/personal care": "أغذية وسلع استهلاكية",
    "consumer non-durables": "أغذية وسلع استهلاكية",
    "consumer staples": "أغذية ومشروبات",
    "food: major diversified": "أغذية ومشروبات",
    "food: meat/fish/dairy": "أغذية ودواجن وألبان",
    "food: specialty/candy": "أغذية ومشروبات",
    "beverages: non-alcoholic": "أغذية ومشروبات",
    # Fertilizers, Chemicals & Basic Materials
    "chemicals: agricultural": "أسمدة وكيماويات",
    "chemicals: major diversified": "بتروكيماويات وكيماويات",
    "chemicals: specialty": "أسمدة وكيماويات",
    "process industries": "صناعات تحويلية وكيماويات",
    "materials": "مواد أساسية وبتروكيماويات",
    "non-energy minerals": "مواد بناء، أسمنت وتعدين",
    "construction materials": "مواد بناء وأسمنت",
    "building products": "مواد بناء وأسمنت",
    "steel": "مواد بناء، أسمنت وتعدين",
    "aluminum": "مواد بناء، أسمنت وتعدين",
    "containers/packaging": "تعبئة وتغليف وصناعات",
    "paper & forest products": "تعبئة وتغليف وصناعات",
    "textiles": "غزل ونسيج وملابس",
    "apparel/footwear": "غزل ونسيج وملابس",
    # Industrials & Manufacturing
    "producer manufacturing": "صناعات هندسية وكهربائية",
    "electrical products": "صناعات هندسية وكهربائية",
    "electrical equipment": "صناعات هندسية وكهربائية",
    "metal fabrication": "صناعات هندسية وكهربائية",
    "industrials": "صناعات هندسية وكهربائية",
    "consumer durables": "سلع معمرة وصناعات",
    # Healthcare & Pharma
    "health technology": "رعاية صحية وأدوية",
    "pharmaceuticals: major": "رعاية صحية وأدوية",
    "pharmaceuticals: other": "رعاية صحية وأدوية",
    "medical specialties": "رعاية صحية وأدوية",
    "health care": "رعاية صحية وأدوية",
    "health services": "مستشفيات وخدمات طبية",
    "medical/nursing services": "مستشفيات وخدمات طبية",
    "hospital/nursing management": "مستشفيات وخدمات طبية",
    # Tech & Telecom
    "technology services": "تكنولوجيا ومدفوعات رقمية",
    "packaged software": "تكنولوجيا ومدفوعات رقمية",
    "information technology": "تكنولوجيا ومدفوعات رقمية",
    "communications": "اتصالات وتكنولوجيا",
    "telecommunication services": "اتصالات وتكنولوجيا",
    "wireless telecommunications": "اتصالات وتكنولوجيا",
    "major telecommunications": "اتصالات وتكنولوجيا",
    # Energy, Utilities, Transport & Services
    "energy minerals": "بترول وطاقة",
    "energy": "بترول وطاقة",
    "integrated oil": "بترول وطاقة",
    "oil & gas production": "بترول وطاقة",
    "utilities": "طاقة ومرافق",
    "electric utilities": "طاقة ومرافق",
    "transportation": "نقل وشحن ولوجستيات",
    "marine shipping": "نقل وشحن ولوجستيات",
    "other transportation": "نقل وشحن ولوجستيات",
    "air freight/couriers": "نقل وشحن ولوجستيات",
    "consumer services": "سياحة وفنادق وخدمات",
    "hotels/resorts/cruise lines": "سياحة وفنادق وخدمات",
    "other consumer services": "سياحة وفنادق وخدمات",
    "commercial services": "خدمات تجارية ولوجستية",
    "miscellaneous commercial services": "خدمات تجارية ولوجستية",
    "distribution services": "تجارة وتوزيع",
    "wholesale distributors": "تجارة وتوزيع",
    "retail trade": "تجارة وتجزئة",
    "food retail": "تجارة وتجزئة",
    "consumer discretionary": "تجارة وتجزئة",
}


def _finite(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool) or val == "":
        return None
    try:
        f = float(val)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _median(values: List[float], fallback: float) -> float:
    if not values:
        return fallback
    s = sorted(values)
    mid = len(s) // 2
    return (s[mid - 1] + s[mid]) / 2.0 if len(s) % 2 == 0 else s[mid]


def resolve_sector_ar(symbol: str, raw_sector: Any = None, raw_industry: Any = None) -> str:
    sym = str(symbol or "").strip().upper()
    ind_k = str(raw_industry or "").strip().lower()
    if ind_k and ind_k in SECTOR_AR_MAP:
        return SECTOR_AR_MAP[ind_k]

    canonical = str(CANONICAL_EGX_STOCK_NAMES.get(sym, {}).get("sector") or "").strip()
    if canonical and canonical not in GENERIC_PLACEHOLDER_SECTORS:
        return canonical

    sec_k = str(raw_sector or "").strip().lower()
    if sec_k and sec_k in SECTOR_AR_MAP:
        return SECTOR_AR_MAP[sec_k]

    if raw_sector and re.search(r"[\u0600-\u06FF]", str(raw_sector)):
        cleaned = str(raw_sector).strip()
        if cleaned not in GENERIC_PLACEHOLDER_SECTORS:
            return cleaned

    return "قطاعات متنوعة"


def is_financial_sector_ar(sector_ar: str, raw_sector: Any = None, raw_industry: Any = None) -> bool:
    ind_k = str(raw_industry or "").strip().lower()
    if "real estate" in ind_k or "homebuilding" in ind_k:
        return False
    return (
        ("بنوك" in sector_ar)
        or ("خدمات مالية" in sector_ar)
        or ("تأمين" in sector_ar)
        or ("استثمار" in sector_ar)
    )


def is_tech_sector_ar(sector_ar: str, raw_sector: Any = None, raw_industry: Any = None) -> bool:
    return ("تكنولوجيا" in sector_ar) or ("مدفوعات" in sector_ar) or ("اتصالات" in sector_ar)


def default_sector_multiples(sector_ar: str, market: str = "egx") -> Tuple[float, float]:
    """Deterministic fallback sector (P/E, P/B) benchmarks when peer-group medians are unavailable."""
    mkt = str(market or "egx").strip().lower()
    if "بنوك" in sector_ar and "غير مصرفية" not in sector_ar:
        pe, pb = 9.0, 1.75
    elif ("خدمات مالية" in sector_ar) or ("تأمين" in sector_ar) or ("استثمار" in sector_ar):
        pe, pb = 8.5, 1.65
    elif ("تكنولوجيا" in sector_ar) or ("مدفوعات" in sector_ar) or ("اتصالات" in sector_ar):
        pe, pb = 14.5, 2.90
    elif ("رعاية صحية" in sector_ar) or ("أدوية" in sector_ar) or ("مستشفيات" in sector_ar):
        pe, pb = 10.5, 2.10
    elif ("أسمدة" in sector_ar) or ("بتروكيماويات" in sector_ar) or ("كيماويات" in sector_ar):
        pe, pb = 9.5, 2.00
    elif ("أغذية" in sector_ar) or ("سلع استهلاكية" in sector_ar) or ("مطاحن" in sector_ar):
        pe, pb = 10.0, 1.85
    elif ("عقارات" in sector_ar) or ("إنشاءات" in sector_ar) or ("مقاولات" in sector_ar):
        pe, pb = 10.0, 1.80
    else:
        pe, pb = 9.5, 1.75

    if mkt in ("tasi", "tadawul", "sa", "saudi"):
        pe, pb = round(pe * 1.40, 2), round(pb * 1.25, 2)
    elif mkt in ("uae", "dfm", "adx", "qatar", "qse", "qe"):
        pe, pb = round(pe * 1.25, 2), round(pb * 1.15, 2)
    return round(pe, 2), round(pb, 2)


def is_egx_usd_symbol(symbol: str, market: str = "egx") -> bool:
    mkt = str(market or "egx").strip().lower()
    if mkt not in ("egx", "egypt"):
        return False
    return str(symbol or "").strip().upper() in EGX_USD_SYMBOLS


def normalize_fundamentals_for_valuation(
    fd: Any,
    close_price: Optional[float],
    *,
    symbol: str = "",
    market: str = "egx",
    split_factor: Optional[float] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Normalize raw fundamentals dict for valuation:
    1. Converts EGP per-share figures (EPS, BVPS, DPS) into USD on USD-traded EGX symbols (e.g. NDRL, FAITA, SAIB).
    2. Scales pre-split EPS / BVPS on full or partial stock splits (e.g. POUL, ORHD) without corrupting post-split fields.
    """
    if not isinstance(fd, dict):
        return {}, False
    out = dict(fd)
    if not close_price or close_price <= 0:
        return out, False

    changed = False
    sym_u = str(symbol or out.get("symbol") or "").strip().upper()

    eps = _finite(out.get("eps") if out.get("eps") is not None else out.get("trailing_eps"))
    bvps = _finite(
        out.get("bookValuePerShare")
        if out.get("bookValuePerShare") is not None
        else (
            out.get("book_value_per_share")
            if out.get("book_value_per_share") is not None
            else (out.get("book_value") if out.get("book_value") is not None else out.get("bvps"))
        )
    )
    pe = _finite(out.get("peRatio") if out.get("peRatio") is not None else out.get("pe_ratio"))
    pb = _finite(out.get("pbRatio") if out.get("pbRatio") is not None else out.get("pb_ratio"))

    # 1. USD-traded EGX symbol with EGP-denominated financial statements
    fin_curr = str(out.get("financialCurrency") or out.get("currency") or "").strip().upper()
    if is_egx_usd_symbol(sym_u, market) and fin_curr == "EGP":
        fx_rate: Optional[float] = None
        if eps is not None and eps > 0 and pe is not None and pe > 0:
            r_ep = (eps * pe) / close_price
            if 20.0 <= r_ep <= 95.0:
                fx_rate = r_ep
        if fx_rate is None and bvps is not None and bvps > 0 and pb is not None and pb > 0:
            r_bp = (bvps * pb) / close_price
            if 20.0 <= r_bp <= 95.0:
                fx_rate = r_bp
        if fx_rate is None:
            mcap = _finite(out.get("marketCap") if out.get("marketCap") is not None else out.get("market_cap"))
            sh = _finite(out.get("sharesOutstanding") if out.get("sharesOutstanding") is not None else out.get("shares_outstanding"))
            if mcap and mcap > 0 and sh and sh > 0:
                r_mc = (mcap / sh) / close_price
                if 20.0 <= r_mc <= 95.0:
                    fx_rate = r_mc
        if fx_rate is None and ((bvps is not None and bvps > close_price * 25.0) or (eps is not None and abs(eps) > close_price * 5.0)):
            fx_rate = 50.5

        if fx_rate is not None and fx_rate >= 20.0:
            if eps is not None:
                eps = round(eps / fx_rate, 4)
                out["eps"] = eps
                if "trailing_eps" in out:
                    out["trailing_eps"] = eps
                if eps > 0:
                    pe = round(close_price / eps, 2)
                    out["peRatio"] = pe
                    if "pe_ratio" in out:
                        out["pe_ratio"] = pe
            if bvps is not None:
                bvps = round(bvps / fx_rate, 4)
                out["bookValuePerShare"] = bvps
                for k in ("book_value_per_share", "book_value", "bvps"):
                    if k in out:
                        out[k] = bvps
                if bvps > 0:
                    pb = round(close_price / bvps, 2)
                    out["pbRatio"] = pb
                    if "pb_ratio" in out:
                        out["pb_ratio"] = pb
            dps_egp = _finite(out.get("dividendPerShare") if out.get("dividendPerShare") is not None else out.get("dividend_per_share"))
            if dps_egp is not None and dps_egp > 0:
                out["dividendPerShare"] = round(dps_egp / fx_rate, 4)
            out["fx_adjusted_from_egp"] = round(fx_rate, 2)
            changed = True

    # 2. Stock-split adjustment (full or partial pre-split EPS / BVPS)
    adj: Optional[float] = None
    bvps_ratio = ((bvps * pb) / close_price) if (bvps is not None and bvps > 0 and pb is not None and pb > 0) else None
    eps_ratio = ((eps * pe) / close_price) if (eps is not None and eps > 0 and pe is not None and pe > 0) else None
    if bvps_ratio is not None and bvps_ratio > 1.85:
        adj = close_price / (bvps * pb)  # type: ignore[operator]
    if adj is None and eps_ratio is not None and eps_ratio > 1.85:
        adj = close_price / (eps * pe)  # type: ignore[operator]
    if (
        adj is None
        and split_factor is not None
        and 0.05 < split_factor < 0.45
        and eps is not None
        and eps > 0
        and (close_price / eps) < 2.5
    ):
        adj = split_factor

    if adj is not None and 0.05 < adj < 0.55:
        eps_already_post = bool(eps_ratio is not None and 0.55 <= eps_ratio <= 1.85)
        bvps_already_post = bool(bvps_ratio is not None and 0.55 <= bvps_ratio <= 1.85)
        if eps is not None and not eps_already_post:
            new_eps = round(eps * adj, 4)
            out["eps"] = new_eps
            if "trailing_eps" in out:
                out["trailing_eps"] = new_eps
            if new_eps > 0:
                out["peRatio"] = round(close_price / new_eps, 2)
                if "pe_ratio" in out:
                    out["pe_ratio"] = out["peRatio"]
        if bvps is not None and not bvps_already_post:
            new_bvps = round(bvps * adj, 4)
            out["bookValuePerShare"] = new_bvps
            for k in ("book_value_per_share", "book_value", "bvps"):
                if k in out:
                    out[k] = new_bvps
            if new_bvps > 0:
                out["pbRatio"] = round(close_price / new_bvps, 2)
                if "pb_ratio" in out:
                    out["pb_ratio"] = out["pbRatio"]
        dps = _finite(out.get("dividendPerShare") if out.get("dividendPerShare") is not None else out.get("dividend_per_share"))
        if dps is not None and dps > close_price * 0.25:
            out["dividendPerShare"] = round(dps * adj, 4)
        out["fundamentals_split_adjusted"] = True
        changed = True

    return out, changed


def compute_unified_fair_value(
    *,
    symbol: str,
    close: float,
    fund_row: Optional[Dict[str, Any]] = None,
    fund_data: Optional[Dict[str, Any]] = None,
    ind: Optional[Dict[str, Any]] = None,
    sector_median_pe: Optional[float] = None,
    sector_median_pb: Optional[float] = None,
    market: str = "egx",
    split_factor: Optional[float] = None,
) -> Dict[str, Any]:
    sym = str(symbol or "").strip().upper()
    mkt_raw = str(market or "egx").strip().lower()
    is_saudi = mkt_raw in ("tasi", "tadawul", "sa", "saudi") or is_saudi_symbol(sym)
    is_uae = mkt_raw in ("uae", "dfm", "adx", "ae")
    is_qatar = mkt_raw in ("qatar", "qse", "qe", "qa")
    resolved_market = "uae" if is_uae else ("qatar" if is_qatar else ("tasi" if is_saudi else "egx"))
    is_usd_egx = is_egx_usd_symbol(sym, resolved_market)

    currency_ar = "$" if is_usd_egx else ("د.إ" if is_uae else ("ر.ق" if is_qatar else ("ر.س" if is_saudi else "ج.م")))
    currency_short = "$" if is_usd_egx else ("د.إ" if is_uae else ("ر.ق" if is_qatar else ("ر" if is_saudi else "ج")))
    market_title = "الإماراتي" if is_uae else ("القطري" if is_qatar else ("السعودي" if is_saudi else "المصري"))
    market_graham = "لسوق الإمارات" if is_uae else ("لبورصة قطر" if is_qatar else ("للسوق السعودي" if is_saudi else "للبورصة المصرية"))

    row = fund_row or {}
    raw_data = (
        fund_data
        if isinstance(fund_data, dict)
        else (row.get("data") if isinstance(row.get("data"), dict) else {})
    )
    data, _ = normalize_fundamentals_for_valuation(
        raw_data,
        close,
        symbol=sym,
        market=resolved_market,
        split_factor=split_factor,
    )
    tech = ind or {}

    canonical = CANONICAL_EGX_STOCK_NAMES.get(sym, {}) if resolved_market == "egx" else {}
    saudi_ar = SAUDI_STOCK_NAMES_AR.get(sym) if is_saudi else None
    name_ar = canonical.get("name_ar") or row.get("name_ar") or data.get("name_ar") or saudi_ar or row.get("name") or data.get("name") or sym
    name_en = canonical.get("name_en") or row.get("name") or data.get("name") or sym
    sector_ar = resolve_sector_ar(sym, data.get("sector"), data.get("industry"))

    def_pe, def_pb = default_sector_multiples(sector_ar, resolved_market)
    sec_pe = round(sector_median_pe if (sector_median_pe and sector_median_pe > 0) else def_pe, 2)
    sec_pb = round(sector_median_pb if (sector_median_pb and sector_median_pb > 0) else def_pb, 2)

    raw_pe = _finite(data.get("peRatio") if data.get("peRatio") is not None else data.get("pe_ratio"))
    raw_fwd_pe = _finite(data.get("forwardPe") if data.get("forwardPe") is not None else data.get("forward_pe"))
    raw_pb = _finite(data.get("pbRatio") if data.get("pbRatio") is not None else data.get("pb_ratio"))

    eps = _finite(data.get("eps") if data.get("eps") is not None else data.get("trailing_eps"))
    bvps = _finite(
        data.get("bookValuePerShare")
        if data.get("bookValuePerShare") is not None
        else (
            data.get("book_value_per_share")
            if data.get("book_value_per_share") is not None
            else (data.get("book_value") if data.get("book_value") is not None else data.get("bvps"))
        )
    )
    net_inc = _finite(data.get("netIncome") if data.get("netIncome") is not None else data.get("net_income"))
    roe_chk = _finite(data.get("roe"))
    is_loss_making = bool(
        (eps is not None and eps <= 0)
        or (net_inc is not None and net_inc < 0)
        or (roe_chk is not None and roe_chk < 0)
    )

    if eps is None and not is_loss_making and raw_pe and raw_pe > 0 and close > 0:
        eps = round(close / raw_pe, 4)
    if bvps is None and raw_pb and raw_pb > 0 and close > 0:
        bvps = round(close / raw_pb, 4)

    eff_eps = eps if (not is_loss_making and eps is not None and eps > 0) else None
    if not is_loss_making and raw_fwd_pe is not None and 2.0 <= raw_fwd_pe <= 60.0 and close > 0:
        fwd_eps = close / raw_fwd_pe
        if eff_eps is not None and eff_eps > 0:
            fwd_eps_clamped = _clamp(fwd_eps, eff_eps * 0.4, eff_eps * 3.0)
            eff_eps = round(0.50 * eff_eps + 0.50 * fwd_eps_clamped, 4)
        else:
            eff_eps = round(fwd_eps, 4)

    pe_ratio = round(close / eps, 2) if (eps and eps > 0 and not is_loss_making) else (round(raw_pe, 2) if (raw_pe and not is_loss_making) else None)
    pb_ratio = round(close / bvps, 2) if (bvps and bvps > 0) else (round(raw_pb, 2) if raw_pb else None)

    ema200_val = _finite(tech.get("ema_200")) or _finite(tech.get("sma_200"))
    vwap20_val = _finite(tech.get("vwap_20")) or _finite(tech.get("ema_50"))

    fair_value = round(close, 2)
    graham_value: Optional[float] = None
    classic_graham_value: Optional[float] = None
    pe_fair_out: Optional[float] = None
    pb_fair_out: Optional[float] = None
    loss_discount_applied = False
    model_type = "quant_vwap"
    model_label_ar = "التوازن الكمي (VWAP + EMA200)"
    eq_ar = ""
    sub_ar = ""
    steps_ar: List[str] = []

    is_financial = is_financial_sector_ar(sector_ar, data.get("sector"), data.get("industry"))
    is_tech = is_tech_sector_ar(sector_ar, data.get("sector"), data.get("industry"))

    def _cap_upside(raw_v: float) -> Tuple[float, float, bool]:
        raw_r = round(raw_v, 2)
        if close <= 0:
            return raw_r, raw_r, False
        # Upper cap (+65%) guards against dirty windfall EPS outliers; NO 0.55*close bubble floor!
        capped = round(_clamp(raw_v, close * 0.12, close * 1.65), 2)
        return capped, raw_r, abs(capped - raw_r) > 0.02

    if eff_eps is not None and eff_eps > 0 and bvps is not None and bvps > 0 and not is_loss_making:
        eps_r = round(eff_eps, 2)
        bvps_r = round(bvps, 2)
        pe_fair = round(eff_eps * sec_pe, 2)
        pb_fair = round(bvps * sec_pb, 2)
        pe_fair_out = pe_fair
        pb_fair_out = pb_fair
        classic_graham_value = round(math.sqrt(22.5 * eff_eps * bvps), 2)

        if is_financial:
            blended = 0.55 * pe_fair + 0.45 * pb_fair
            fair_value, raw_r, was_capped = _cap_upside(blended)
            model_type = "graham_fundamental"
            model_label_ar = "مضاعفات القطاع المالي (P/E + P/B)"
            eq_ar = "السعر العادل = (55% × هدف مكرر ربحية القطاع) + (45% × هدف القيمة الدفترية للقطاع)"
            sub_ar = (
                f"(0.55 × {pe_fair}) + (0.45 × {pb_fair}) = {raw_r} -> السقف التحفظي (+65%) = {fair_value} {currency_ar}"
                if was_capped
                else f"(0.55 × {pe_fair}) + (0.45 × {pb_fair}) = {fair_value} {currency_ar}"
            )
            steps_ar = [
                f"1️⃣ تقييم مضاعف ربحية القطاع ({sector_ar}): ربحية السهم ({eps_r} {currency_short}) × وسيط مكرر القطاع ({sec_pe}x) = {pe_fair} {currency_ar} (وزن 55%)",
                f"2️⃣ تقييم مضاعف القيمة الدفترية للقطاع: القيمة الدفترية ({bvps_r} {currency_short}) × وسيط مضاعف القطاع ({sec_pb}x) = {pb_fair} {currency_ar} (وزن 45%)",
                f"✅ السعر العادل المعتمد = {fair_value} {currency_ar}." if not was_capped else f"✅ المجموع الأساسي = {raw_r} {currency_ar} -> المعتمد بعد سقف الأمان (+65%) = {fair_value} {currency_ar}.",
            ]
        elif is_tech:
            blended = 0.70 * pe_fair + 0.30 * pb_fair
            fair_value, raw_r, was_capped = _cap_upside(blended)
            model_type = "graham_fundamental"
            model_label_ar = "مضاعفات قطاع التكنولوجيا والنمو الرقمي (P/E + P/B)"
            eq_ar = "السعر العادل = (70% × هدف مكرر ربحية قطاع التكنولوجيا) + (30% × هدف مضاعف القيمة الدفترية)"
            sub_ar = (
                f"(0.70 × {pe_fair}) + (0.30 × {pb_fair}) = {raw_r} -> السقف التحفظي (+65%) = {fair_value} {currency_ar}"
                if was_capped
                else f"(0.70 × {pe_fair}) + (0.30 × {pb_fair}) = {fair_value} {currency_ar}"
            )
            steps_ar = [
                f"1️⃣ تقييم مضاعف ربحية قطاع التكنولوجيا ({sector_ar}): ربحية السهم ({eps_r} {currency_short}) × وسيط مكرر القطاع ({sec_pe}x) = {pe_fair} {currency_ar} (وزن 70% للنمو الرقمي)",
                f"2️⃣ تقييم مضاعف القيمة الدفترية: القيمة الدفترية ({bvps_r} {currency_short}) × وسيط مضاعف القطاع ({sec_pb}x) = {pb_fair} {currency_ar} (وزن 30%)",
                f"✅ السعر العادل المعتمد = {fair_value} {currency_ar}." if not was_capped else f"✅ المجموع الأساسي = {raw_r} {currency_ar} -> المعتمد بعد سقف الأمان (+65%) = {fair_value} {currency_ar}.",
            ]
        else:
            max_mult = 22.5 if is_saudi else 16.0
            mult = round(_clamp(sec_pe * sec_pb, 8.0, max_mult), 2)
            raw_graham = math.sqrt(mult * eff_eps * bvps)
            graham_value = round(raw_graham, 2)
            blended = 0.40 * graham_value + 0.35 * pe_fair + 0.25 * pb_fair
            fair_value, raw_r, was_capped = _cap_upside(blended)
            model_type = "graham_fundamental"
            model_label_ar = f"نموذج جراهام {market_title} + مضاعف القطاع"
            eq_ar = "السعر العادل = (40% × قيمة جراهام المعدلة) + (35% × هدف مكرر ربحية القطاع) + (25% × هدف القيمة الدفترية للقطاع)"
            sub_ar = (
                f"(0.40 × {graham_value}) + (0.35 × {pe_fair}) + (0.25 × {pb_fair}) = {raw_r} -> السقف التحفظي (+65%) = {fair_value} {currency_ar}"
                if was_capped
                else f"(0.40 × {graham_value}) + (0.35 × {pe_fair}) + (0.25 × {pb_fair}) = {fair_value} {currency_ar}"
            )
            steps_ar = [
                f"1️⃣ معادلة بنجامين جراهام المعدلة {market_graham}: √(مضاعف القطاع {mult} × ربحية السهم {eps_r} × القيمة الدفترية {bvps_r}) = {graham_value} {currency_ar} (وزن 40%)",
                f"2️⃣ تقييم مضاعف ربحية القطاع ({sector_ar}): ربحية السهم ({eps_r}) × وسيط مكرر القطاع ({sec_pe}x) = {pe_fair} {currency_ar} (وزن 35%)",
                f"3️⃣ تقييم مضاعف القيمة الدفترية للقطاع: القيمة الدفترية ({bvps_r}) × وسيط مضاعف القطاع ({sec_pb}x) = {pb_fair} {currency_ar} (وزن 25%)",
                f"✅ السعر العادل المرجح للسهم = {fair_value} {currency_ar}." if not was_capped else f"✅ المجموع الأساسي = {raw_r} {currency_ar} -> المعتمد بعد سقف الأمان (+65%) = {fair_value} {currency_ar}.",
            ]
    elif eff_eps is not None and eff_eps > 0 and not is_loss_making:
        eps_r = round(eff_eps, 2)
        pe_fair = round(eff_eps * sec_pe, 2)
        pe_fair_out = pe_fair
        fair_value, raw_r, was_capped = _cap_upside(pe_fair)
        model_type = "pe_multiple"
        model_label_ar = "مضاعف الربحية القطاعي (P/E)"
        eq_ar = "السعر العادل = ربحية السهم (EPS) × وسيط مضاعف ربحية القطاع (Sector P/E)"
        sub_ar = (
            f"{eps_r} × {sec_pe} = {raw_r} -> السقف التحفظي (+65%) = {fair_value} {currency_ar}"
            if was_capped
            else f"{eps_r} × {sec_pe} = {fair_value} {currency_ar}"
        )
        steps_ar = [
            f"1️⃣ ربحية السهم السنوية المحققة (EPS) = {eps_r} {currency_ar}",
            f"2️⃣ وسيط مضاعف الربحية لقطاع ({sector_ar}) = {sec_pe} مرة",
            f"✅ السعر العادل المعتمد = {fair_value} {currency_ar}." if not was_capped else f"✅ القيمة الأساسية = {raw_r} {currency_ar} -> المعتمد بعد سقف الأمان (+65%) = {fair_value} {currency_ar}.",
        ]
    elif bvps is not None and bvps > 0:
        bvps_r = round(bvps, 2)
        if is_loss_making:
            if roe_chk is not None and roe_chk <= -10.0:
                distress_pb = 0.65
            elif roe_chk is not None and roe_chk <= -5.0:
                distress_pb = 0.75
            else:
                distress_pb = 0.80
            pb_fair = round(bvps * distress_pb, 2)
            pb_fair_out = pb_fair
            loss_discount_applied = True
            upper_cap = round(close * (0.90 if (roe_chk is not None and roe_chk <= -5.0) else 0.95), 2) if close > 0 else pb_fair
            fair_value = round(_clamp(pb_fair, close * 0.12, upper_cap), 2) if close > 0 else pb_fair
            was_capped = abs(fair_value - pb_fair) > 0.02
            model_type = "pb_distressed"
            model_label_ar = "قيمة دفترية مخفضة (شركة خاسرة)"
            eq_ar = "السعر العادل التحفظي = القيمة الدفترية (BVPS) × معامل خصم الخسائر (0.65x–0.80x P/B)"
            sub_ar = (
                f"{bvps_r} × {distress_pb} = {pb_fair} -> سقف خصم الخسائر = {fair_value} {currency_ar}"
                if was_capped
                else f"{bvps_r} × {distress_pb} = {fair_value} {currency_ar}"
            )
            steps_ar = [
                f"1️⃣ الشركة تسجّل صافي خسائر حالياً: القيمة الدفترية للسهم (BVPS) = {bvps_r} {currency_ar}",
                f"2️⃣ تطبيق معامل خصم تآكل الحقوق للشركات الخاسرة = {distress_pb}x من القيمة الدفترية",
                f"✅ السعر العادل التحفظي المعتمد = {fair_value} {currency_ar}." if not was_capped else f"✅ القيمة الدفترية المخفضة = {pb_fair} {currency_ar} -> المعتمد بسقف خصم الخسائر = {fair_value} {currency_ar}.",
            ]
        else:
            pb_fair = round(bvps * sec_pb, 2)
            pb_fair_out = pb_fair
            fair_value, raw_r, was_capped = _cap_upside(pb_fair)
            model_type = "pb_multiple"
            model_label_ar = "مضاعف القيمة الدفترية (P/B)"
            eq_ar = "السعر العادل = القيمة الدفترية للسهم (BVPS) × وسيط مضاعف القيمة الدفترية للقطاع (Sector P/B)"
            sub_ar = (
                f"{bvps_r} × {sec_pb} = {raw_r} -> السقف التحفظي (+65%) = {fair_value} {currency_ar}"
                if was_capped
                else f"{bvps_r} × {sec_pb} = {fair_value} {currency_ar}"
            )
            steps_ar = [
                f"1️⃣ القيمة الدفترية للسهم من حقوق الملكية (BVPS) = {bvps_r} {currency_ar}",
                f"2️⃣ وسيط مضاعف القيمة الدفترية لقطاع ({sector_ar}) = {sec_pb} مرة",
                f"✅ السعر العادل المعتمد = {fair_value} {currency_ar}." if not was_capped else f"✅ القيمة الأساسية = {raw_r} {currency_ar} -> المعتمد بعد سقف الأمان (+65%) = {fair_value} {currency_ar}.",
            ]
    else:
        ema200_v = round(ema200_val if ema200_val is not None else close, 2)
        vwap20_v = round(vwap20_val if vwap20_val is not None else close, 2)
        raw_q = round(0.6 * ema200_v + 0.4 * vwap20_v, 2)
        if is_loss_making and close > 0:
            loss_discount_applied = True
            fair_value = round(_clamp(raw_q, close * 0.45, close * 0.85), 2)
            was_capped = abs(fair_value - raw_q) > 0.02
            model_type = "pb_distressed"
            model_label_ar = "توازن كمي مخفض (شركة خاسرة)"
            eq_ar = "السعر التحفظي لشركة خاسرة بدون حقوق ملكية موجبة = التوازن الكمي بسقف خصم الخسائر"
            sub_ar = (
                f"(0.60 × {ema200_v}) + (0.40 × {vwap20_v}) = {raw_q} -> سقف خصم الخسائر = {fair_value} {currency_ar}"
                if was_capped
                else f"(0.60 × {ema200_v}) + (0.40 × {vwap20_v}) = {fair_value} {currency_ar}"
            )
            steps_ar = [
                f"1️⃣ الشركة تسجل خسائر وحقوق ملكية غير موجبة: متوسط التوازن (EMA200={ema200_v}، VWAP20={vwap20_v})",
                f"✅ السعر التحفظي المعتمد = {fair_value} {currency_ar}.",
            ]
        else:
            fair_value = round(_clamp(raw_q, close * 0.60, close * 1.50), 2) if close > 0 else raw_q
            was_capped = abs(fair_value - raw_q) > 0.02
            model_type = "quant_vwap"
            model_label_ar = "التوازن الكمي (VWAP + EMA200)"
            eq_ar = "السعر العادل الكمي = (60% × المتوسط الأسي EMA200) + (40% × متوسط التكلفة المرجح بالسيولة VWAP20)"
            sub_ar = (
                f"(0.60 × {ema200_v}) + (0.40 × {vwap20_v}) = {raw_q} -> المعتمد = {fair_value} {currency_ar}"
                if was_capped
                else f"(0.60 × {ema200_v}) + (0.40 × {vwap20_v}) = {fair_value} {currency_ar}"
            )
            steps_ar = [
                f"1️⃣ متوسط التوازن السعري طويل الأجل (EMA 200) = {ema200_v} {currency_ar} (وزن 60%)",
                f"2️⃣ متوسط سعر التكلفة المرجح بالسيولة لآخر 20 جلسة (VWAP 20) = {vwap20_v} {currency_ar} (وزن 40%)",
                f"✅ السعر العادل التوازني المعتمد = {fair_value} {currency_ar}.",
            ]

    upside = round(((fair_value - close) / close) * 100.0, 2) if close > 0 else 0.0
    if is_loss_making:
        status = "overvalued"
    else:
        status = "undervalued" if upside >= 15 else ("overvalued" if upside <= -12 else "fair")

    chg = _finite(tech.get("change_pct"))
    dy = _finite(data.get("dividendYield"))
    roe = _finite(data.get("roe"))
    rsi14 = _finite(tech.get("rsi_14"))

    return {
        "symbol": sym,
        "nameAr": name_ar,
        "nameEn": name_en,
        "sectorAr": sector_ar,
        "currencySymbol": currency_ar,
        "logoUrl": data.get("logoUrl") if isinstance(data.get("logoUrl"), str) else None,
        "currentPrice": round(close, 2),
        "changePct": round(chg, 2) if chg is not None else None,
        "fairValue": fair_value,
        "grahamValue": graham_value,
        "classicGrahamValue": classic_graham_value,
        "peFairValue": pe_fair_out,
        "pbFairValue": pb_fair_out,
        "isLossMaking": is_loss_making,
        "lossMakingDiscountApplied": loss_discount_applied,
        "upsidePct": upside,
        "status": status,
        "modelType": model_type,
        "modelLabelAr": model_label_ar,
        "formulaEquationAr": eq_ar,
        "formulaSubstitutionAr": sub_ar,
        "formulaStepsAr": steps_ar,
        "eps": round(eps, 2) if eps is not None else None,
        "bvps": round(bvps, 2) if bvps is not None else None,
        "peRatio": pe_ratio,
        "pbRatio": pb_ratio,
        "forwardPe": round(raw_fwd_pe, 2) if (raw_fwd_pe and raw_fwd_pe > 0) else None,
        "sectorMedianPe": sec_pe,
        "sectorMedianPb": sec_pb,
        "dividendYield": round(dy, 2) if dy is not None else None,
        "roe": round(roe, 2) if roe is not None else None,
        "marketCap": _finite(data.get("marketCap")),
        "rsi14": round(rsi14, 1) if rsi14 is not None else None,
        "ema200": round(ema200_val, 2) if ema200_val is not None else None,
        "vwap20": round(vwap20_val, 2) if vwap20_val is not None else None,
        "isSharia": is_sharia_compliant(sym, resolved_market),
        "date": str(tech.get("date"))[:10] if tech.get("date") else None,
    }
