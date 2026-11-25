import { CANONICAL_STOCK_NAMES } from "@/lib/ai/stock-names";
import { SAUDI_STOCK_NAMES_AR, isSaudiSymbol } from "@/lib/saudi-stocks";
import { isShariaCompliant } from "@/lib/shariaStocks";

export type FairValueModelType =
  | "graham_fundamental"
  | "pe_multiple"
  | "pb_multiple"
  | "pb_distressed"
  | "quant_vwap";

export type FairValueStatus = "undervalued" | "fair" | "overvalued";

export interface FairValueStockItem {
  symbol: string;
  nameAr: string;
  nameEn: string;
  sectorAr: string;
  currencySymbol?: string;
  logoUrl: string | null;
  currentPrice: number;
  changePct: number | null;
  fairValue: number;
  grahamValue: number | null;
  classicGrahamValue?: number | null;
  isLossMaking?: boolean;
  upsidePct: number;
  status: FairValueStatus;
  modelType: FairValueModelType;
  modelLabelAr: string;
  formulaEquationAr: string;
  formulaSubstitutionAr: string;
  formulaStepsAr: string[];
  eps: number | null;
  bvps: number | null;
  peRatio: number | null;
  pbRatio: number | null;
  sectorMedianPe: number;
  sectorMedianPb: number;
  dividendYield: number | null;
  roe: number | null;
  marketCap: number | null;
  rsi14: number | null;
  ema200: number | null;
  vwap20: number | null;
  isSharia: boolean;
  date: string | null;
}

export interface FairValueReport {
  market?: "egx" | "tasi" | "uae" | "qatar";
  currencyCode?: "EGP" | "SAR" | "AED" | "QAR";
  updatedAt: string;
  latestSessionDate: string | null;
  summary: {
    totalEvaluated: number;
    undervaluedCount: number;
    fairCount: number;
    overvaluedCount: number;
    fundamentalCoverageCount: number;
  };
  sectors: string[];
  stocks: FairValueStockItem[];
}

const EGX_USD_SYMBOLS = new Set([
  "ADPC", "ANFI", "APSW", "CERA", "DAPH", "EGBE", "EGSA", "EGTS",
  "EKHO", "FAITA", "GPPL", "GRCA", "GMCI", "MAFI", "MENA", "MOIL",
  "MOSC_USD", "NAHO", "NDRL", "NINH", "PHTV", "SAIB", "SCTS",
  "SMFR", "TRTO", "UNIP_USD", "VERT",
]);

const GENERIC_PLACEHOLDER_SECTORS = new Set([
  "",
  "سوق الأسهم المصرية",
  "البورصة المصرية",
  "سوق الأسهم السعودية",
  "تداول",
  "قطاعات متنوعة",
  "غير مصنف",
]);

const SECTOR_AR_MAP: Record<string, string> = {
  "regional banks": "بنوك",
  "major banks": "بنوك",
  banks: "بنوك",
  "investment banks/brokers": "خدمات مالية غير مصرفية",
  "financial conglomerates": "خدمات مالية غير مصرفية",
  "investment managers": "خدمات مالية غير مصرفية",
  "finance/rental/leasing": "خدمات مالية غير مصرفية",
  "multi-line insurance": "تأمين وخدمات مالية",
  "property/casualty insurance": "تأمين وخدمات مالية",
  "life/health insurance": "تأمين وخدمات مالية",
  insurance: "تأمين وخدمات مالية",
  finance: "بنوك وخدمات مالية",
  "real estate development": "عقارات وإنشاءات",
  "real estate": "عقارات وإنشاءات",
  homebuilding: "عقارات وإنشاءات",
  "engineering & construction": "عقارات ومقاولات وإنشاءات",
  "industrial services": "عقارات ومقاولات وإنشاءات",
  "agricultural commodities/milling": "أغذية ومطاحن وزيوت",
  "household/personal care": "أغذية وسلع استهلاكية",
  "consumer non-durables": "أغذية وسلع استهلاكية",
  "consumer staples": "أغذية ومشروبات",
  "food: major diversified": "أغذية ومشروبات",
  "food: meat/fish/dairy": "أغذية ودواجن وألبان",
  "food: specialty/candy": "أغذية ومشروبات",
  "beverages: non-alcoholic": "أغذية ومشروبات",
  "chemicals: agricultural": "أسمدة وكيماويات",
  "chemicals: major diversified": "بتروكيماويات وكيماويات",
  "chemicals: specialty": "أسمدة وكيماويات",
  "process industries": "صناعات تحويلية وكيماويات",
  materials: "مواد أساسية وبتروكيماويات",
  "non-energy minerals": "مواد بناء، أسمنت وتعدين",
  "construction materials": "مواد بناء وأسمنت",
  "building products": "مواد بناء وأسمنت",
  steel: "مواد بناء، أسمنت وتعدين",
  aluminum: "مواد بناء، أسمنت وتعدين",
  "containers/packaging": "تعبئة وتغليف وصناعات",
  "paper & forest products": "تعبئة وتغليف وصناعات",
  textiles: "غزل ونسيج وملابس",
  "apparel/footwear": "غزل ونسيج وملابس",
  "producer manufacturing": "صناعات هندسية وكهربائية",
  "electrical products": "صناعات هندسية وكهربائية",
  "electrical equipment": "صناعات هندسية وكهربائية",
  "metal fabrication": "صناعات هندسية وكهربائية",
  industrials: "صناعات هندسية وكهربائية",
  "consumer durables": "سلع معمرة وصناعات",
  "health technology": "رعاية صحية وأدوية",
  "pharmaceuticals: major": "رعاية صحية وأدوية",
  "pharmaceuticals: other": "رعاية صحية وأدوية",
  "medical specialties": "رعاية صحية وأدوية",
  "health care": "رعاية صحية وأدوية",
  "health services": "مستشفيات وخدمات طبية",
  "medical/nursing services": "مستشفيات وخدمات طبية",
  "hospital/nursing management": "مستشفيات وخدمات طبية",
  "technology services": "تكنولوجيا ومدفوعات رقمية",
  "packaged software": "تكنولوجيا ومدفوعات رقمية",
  "information technology": "تكنولوجيا ومدفوعات رقمية",
  communications: "اتصالات وتكنولوجيا",
  "telecommunication services": "اتصالات وتكنولوجيا",
  "wireless telecommunications": "اتصالات وتكنولوجيا",
  "major telecommunications": "اتصالات وتكنولوجيا",
  "energy minerals": "بترول وطاقة",
  energy: "بترول وطاقة",
  "integrated oil": "بترول وطاقة",
  "oil & gas production": "بترول وطاقة",
  utilities: "طاقة ومرافق",
  "electric utilities": "طاقة ومرافق",
  transportation: "نقل وشحن ولوجستيات",
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
};

export function resolveSectorAr(
  symbol: string,
  rawSector?: string | null,
  rawIndustry?: string | null
): string {
  const sym = String(symbol || "").trim().toUpperCase();
  const indKey = String(rawIndustry || "").trim().toLowerCase();
  if (indKey && SECTOR_AR_MAP[indKey]) return SECTOR_AR_MAP[indKey];

  const canonical = String(CANONICAL_STOCK_NAMES[sym]?.sector || "").trim();
  if (canonical && !GENERIC_PLACEHOLDER_SECTORS.has(canonical)) return canonical;

  const secKey = String(rawSector || "").trim().toLowerCase();
  if (secKey && SECTOR_AR_MAP[secKey]) return SECTOR_AR_MAP[secKey];

  if (rawSector && /[\u0600-\u06FF]/.test(rawSector)) {
    const cleaned = String(rawSector).trim();
    if (!GENERIC_PLACEHOLDER_SECTORS.has(cleaned)) return cleaned;
  }
  return "قطاعات متنوعة";
}

function defaultSectorMultiples(
  sectorAr: string,
  market: "egx" | "tasi" | "uae" | "qatar" = "egx"
): [number, number] {
  let pe = 9.5;
  let pb = 1.75;
  if (sectorAr.includes("بنوك") && !sectorAr.includes("غير مصرفية")) {
    pe = 9.0;
    pb = 1.75;
  } else if (
    sectorAr.includes("خدمات مالية") ||
    sectorAr.includes("تأمين") ||
    sectorAr.includes("استثمار")
  ) {
    pe = 8.5;
    pb = 1.65;
  } else if (
    sectorAr.includes("تكنولوجيا") ||
    sectorAr.includes("مدفوعات") ||
    sectorAr.includes("اتصالات")
  ) {
    pe = 14.5;
    pb = 2.9;
  } else if (
    sectorAr.includes("رعاية صحية") ||
    sectorAr.includes("أدوية") ||
    sectorAr.includes("مستشفيات")
  ) {
    pe = 10.5;
    pb = 2.1;
  } else if (
    sectorAr.includes("أسمدة") ||
    sectorAr.includes("بتروكيماويات") ||
    sectorAr.includes("كيماويات")
  ) {
    pe = 9.5;
    pb = 2.0;
  } else if (
    sectorAr.includes("أغذية") ||
    sectorAr.includes("سلع استهلاكية") ||
    sectorAr.includes("مطاحن")
  ) {
    pe = 10.0;
    pb = 1.85;
  } else if (
    sectorAr.includes("عقارات") ||
    sectorAr.includes("إنشاءات") ||
    sectorAr.includes("مقاولات")
  ) {
    pe = 10.0;
    pb = 1.8;
  }

  if (market === "tasi") {
    pe = Number((pe * 1.4).toFixed(2));
    pb = Number((pb * 1.25).toFixed(2));
  } else if (market === "uae" || market === "qatar") {
    pe = Number((pe * 1.25).toFixed(2));
    pb = Number((pb * 1.15).toFixed(2));
  }
  return [Number(pe.toFixed(2)), Number(pb.toFixed(2))];
}

function finiteNum(val: unknown): number | null {
  if (val === null || val === undefined || val === "" || typeof val === "boolean") return null;
  const n = Number(val);
  return Number.isFinite(n) ? n : null;
}

function median(values: number[], fallback: number): number {
  if (!values.length) return fallback;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

function clamp(val: number, minVal: number, maxVal: number): number {
  return Math.max(minVal, Math.min(maxVal, val));
}

function normalizeFundamentalsForValuation(
  rawData: Record<string, any>,
  close: number,
  symbol: string,
  market: "egx" | "tasi" | "uae" | "qatar"
): Record<string, any> {
  const out: Record<string, any> = { ...(rawData || {}) };
  if (!close || close <= 0) return out;

  let eps = finiteNum(out.eps ?? out.trailing_eps);
  let bvps = finiteNum(
    out.bookValuePerShare ?? out.book_value_per_share ?? out.book_value ?? out.bvps
  );
  let pe = finiteNum(out.peRatio ?? out.pe_ratio);
  let pb = finiteNum(out.pbRatio ?? out.pb_ratio);

  const finCurr = String(out.financialCurrency || out.currency || "").trim().toUpperCase();
  if (market === "egx" && EGX_USD_SYMBOLS.has(symbol) && finCurr === "EGP") {
    let fxRate: number | null = null;
    if (eps !== null && eps > 0 && pe !== null && pe > 0) {
      const rEp = (eps * pe) / close;
      if (rEp >= 20 && rEp <= 95) fxRate = rEp;
    }
    if (fxRate === null && bvps !== null && bvps > 0 && pb !== null && pb > 0) {
      const rBp = (bvps * pb) / close;
      if (rBp >= 20 && rBp <= 95) fxRate = rBp;
    }
    if (fxRate === null) {
      const mcap = finiteNum(out.marketCap ?? out.market_cap);
      const sh = finiteNum(out.sharesOutstanding ?? out.shares_outstanding);
      if (mcap && mcap > 0 && sh && sh > 0) {
        const rMc = mcap / sh / close;
        if (rMc >= 20 && rMc <= 95) fxRate = rMc;
      }
    }
    if (
      fxRate === null &&
      ((bvps !== null && bvps > close * 25) || (eps !== null && Math.abs(eps) > close * 5))
    ) {
      fxRate = 50.5;
    }
    if (fxRate !== null && fxRate >= 20) {
      if (eps !== null) {
        eps = Number((eps / fxRate).toFixed(4));
        out.eps = eps;
        if (eps > 0) {
          pe = Number((close / eps).toFixed(2));
          out.peRatio = pe;
        }
      }
      if (bvps !== null) {
        bvps = Number((bvps / fxRate).toFixed(4));
        out.bookValuePerShare = bvps;
        if (bvps > 0) {
          pb = Number((close / bvps).toFixed(2));
          out.pbRatio = pb;
        }
      }
    }
  }

  let adj: number | null = null;
  const bvpsRatio =
    bvps !== null && bvps > 0 && pb !== null && pb > 0 ? (bvps * pb) / close : null;
  const epsRatio =
    eps !== null && eps > 0 && pe !== null && pe > 0 ? (eps * pe) / close : null;
  if (bvpsRatio !== null && bvpsRatio > 1.85) {
    adj = close / (bvps! * pb!);
  }
  if (adj === null && epsRatio !== null && epsRatio > 1.85) {
    adj = close / (eps! * pe!);
  }
  if (adj !== null && adj > 0.05 && adj < 0.55) {
    const epsAlreadyPost = epsRatio !== null && epsRatio >= 0.55 && epsRatio <= 1.85;
    const bvpsAlreadyPost = bvpsRatio !== null && bvpsRatio >= 0.55 && bvpsRatio <= 1.85;
    if (eps !== null && !epsAlreadyPost) {
      const newEps = Number((eps * adj).toFixed(4));
      out.eps = newEps;
      if (newEps > 0) out.peRatio = Number((close / newEps).toFixed(2));
    }
    if (bvps !== null && !bvpsAlreadyPost) {
      const newBvps = Number((bvps * adj).toFixed(4));
      out.bookValuePerShare = newBvps;
      if (newBvps > 0) out.pbRatio = Number((close / newBvps).toFixed(2));
    }
  }
  return out;
}

export function computeSingleStockFairValue(params: {
  symbol: string;
  close: number;
  fundRow?: Record<string, any> | null;
  fundData?: Record<string, any> | null;
  latestTech?: Record<string, any> | null;
  sectorMedianPe?: number;
  sectorMedianPb?: number;
  market?: "egx" | "tasi" | "uae" | "qatar";
}): FairValueStockItem {
  const sym = String(params.symbol || "").trim().toUpperCase();
  const close = Number(params.close || 0);
  const isSaudi = params.market === "tasi" || isSaudiSymbol(sym);
  const isUae = params.market === "uae";
  const isQatar = params.market === "qatar";
  const resolvedMarket: "egx" | "tasi" | "uae" | "qatar" = isUae
    ? "uae"
    : isQatar
    ? "qatar"
    : isSaudi
    ? "tasi"
    : "egx";
  const isUsdEgx = resolvedMarket === "egx" && EGX_USD_SYMBOLS.has(sym);

  const currencyAr = isUsdEgx ? "$" : isUae ? "د.إ" : isQatar ? "ر.ق" : isSaudi ? "ر.س" : "ج.م";
  const currencyShort = isUsdEgx ? "$" : isUae ? "د.إ" : isQatar ? "ر.ق" : isSaudi ? "ر" : "ج";
  const marketTitleLabel = isUae ? "الإماراتي" : isQatar ? "القطري" : isSaudi ? "السعودي" : "المصري";
  const marketGrahamLabel = isUae
    ? "لسوق الإمارات"
    : isQatar
    ? "لبورصة قطر"
    : isSaudi
    ? "للسوق السعودي"
    : "للبورصة المصرية";

  const fundRow = params.fundRow || {};
  const rawData =
    params.fundData && typeof params.fundData === "object"
      ? params.fundData
      : fundRow?.data && typeof fundRow.data === "object"
      ? fundRow.data
      : {};
  const data = normalizeFundamentalsForValuation(rawData, close, sym, resolvedMarket);
  const ind = params.latestTech || {};

  const canonical = resolvedMarket === "egx" ? CANONICAL_STOCK_NAMES[sym] : undefined;
  const saudiNameAr = isSaudi ? SAUDI_STOCK_NAMES_AR[sym] : undefined;
  const nameAr =
    canonical?.name_ar ||
    fundRow?.name_ar ||
    data.name_ar ||
    saudiNameAr ||
    fundRow?.name ||
    data.name ||
    sym;
  const nameEn = canonical?.name_en || fundRow?.name || data.name || sym;
  const sectorAr = resolveSectorAr(sym, data.sector, data.industry);

  const [defPe, defPb] = defaultSectorMultiples(sectorAr, resolvedMarket);
  const sectorMedianPe = Number(
    (params.sectorMedianPe && params.sectorMedianPe > 0 ? params.sectorMedianPe : defPe).toFixed(2)
  );
  const sectorMedianPb = Number(
    (params.sectorMedianPb && params.sectorMedianPb > 0 ? params.sectorMedianPb : defPb).toFixed(2)
  );

  const rawPe = finiteNum(data.peRatio ?? data.pe_ratio);
  const rawFwdPe = finiteNum(data.forwardPe ?? data.forward_pe);
  const rawPb = finiteNum(data.pbRatio ?? data.pb_ratio);
  let eps = finiteNum(data.eps ?? data.trailing_eps);
  let bvps = finiteNum(
    data.bookValuePerShare ??
      data.book_value_per_share ??
      data.book_value ??
      data.bvps
  );
  const netInc = finiteNum(data.netIncome ?? data.net_income);
  const roeChk = finiteNum(data.roe);
  const isLossMaking = Boolean(
    (eps !== null && eps <= 0) ||
      (netInc !== null && netInc < 0) ||
      (roeChk !== null && roeChk < 0)
  );

  if (eps === null && !isLossMaking && rawPe && rawPe > 0 && close > 0) {
    eps = Number((close / rawPe).toFixed(4));
  }
  if (bvps === null && rawPb && rawPb > 0 && close > 0) {
    bvps = Number((close / rawPb).toFixed(4));
  }

  let effEps = !isLossMaking && eps !== null && eps > 0 ? eps : null;
  if (!isLossMaking && rawFwdPe !== null && rawFwdPe >= 2 && rawFwdPe <= 60 && close > 0) {
    const fwdEps = close / rawFwdPe;
    if (effEps !== null && effEps > 0) {
      const fwdClamped = clamp(fwdEps, effEps * 0.4, effEps * 3.0);
      effEps = Number((0.5 * effEps + 0.5 * fwdClamped).toFixed(4));
    } else {
      effEps = Number(fwdEps.toFixed(4));
    }
  }

  const peRatio =
    !isLossMaking && eps && eps > 0
      ? Number((close / eps).toFixed(2))
      : !isLossMaking && rawPe
      ? Number(rawPe.toFixed(2))
      : null;
  const pbRatio =
    bvps && bvps > 0
      ? Number((close / bvps).toFixed(2))
      : rawPb
      ? Number(rawPb.toFixed(2))
      : null;

  const ema200Val = finiteNum(ind?.ema_200) ?? finiteNum(ind?.sma_200);
  const vwap20Val = finiteNum(ind?.vwap_20) ?? finiteNum(ind?.ema_50);

  let fairValue = Number(close.toFixed(2));
  let grahamValue: number | null = null;
  let classicGrahamValue: number | null = null;
  let modelType: FairValueModelType = "quant_vwap";
  let modelLabelAr = "التوازن الكمي (VWAP + EMA200)";
  let formulaEquationAr = "";
  let formulaSubstitutionAr = "";
  let formulaStepsAr: string[] = [];

  const indLower = String(data.industry || "").toLowerCase();
  const isRealEstateInd = indLower.includes("real estate") || indLower.includes("homebuilding");
  const isFinancial =
    !isRealEstateInd &&
    (sectorAr.includes("بنوك") ||
      sectorAr.includes("خدمات مالية") ||
      sectorAr.includes("تأمين") ||
      sectorAr.includes("استثمار"));

  const isTechGrowth =
    sectorAr.includes("تكنولوجيا") ||
    sectorAr.includes("مدفوعات") ||
    sectorAr.includes("اتصالات");

  const capUpside = (rawV: number): { fv: number; rawR: number; wasCapped: boolean } => {
    const rawR = Number(rawV.toFixed(2));
    if (close <= 0) return { fv: rawR, rawR, wasCapped: false };
    const fv = Number(clamp(rawV, close * 0.12, close * 1.65).toFixed(2));
    return { fv, rawR, wasCapped: Math.abs(fv - rawR) > 0.02 };
  };

  if (effEps !== null && effEps > 0 && bvps !== null && bvps > 0 && !isLossMaking) {
    const epsRound = Number(effEps.toFixed(2));
    const bvpsRound = Number(bvps.toFixed(2));
    const peFair = Number((effEps * sectorMedianPe).toFixed(2));
    const pbFair = Number((bvps * sectorMedianPb).toFixed(2));
    classicGrahamValue = Number(Math.sqrt(22.5 * effEps * bvps).toFixed(2));

    if (isFinancial) {
      const { fv, rawR, wasCapped } = capUpside(0.55 * peFair + 0.45 * pbFair);
      fairValue = fv;
      modelType = "graham_fundamental";
      modelLabelAr = "مضاعفات القطاع المالي (P/E + P/B)";
      formulaEquationAr =
        "السعر العادل = (55% × هدف مكرر ربحية القطاع) + (45% × هدف القيمة الدفترية للقطاع)";
      formulaSubstitutionAr = wasCapped
        ? `(0.55 × ${peFair}) + (0.45 × ${pbFair}) = ${rawR} -> السقف التحفظي (+65%) = ${fairValue} ${currencyAr}`
        : `(0.55 × ${peFair}) + (0.45 × ${pbFair}) = ${fairValue} ${currencyAr}`;
      formulaStepsAr = [
        `1️⃣ تقييم مضاعف ربحية القطاع (${sectorAr}): ربحية السهم (${epsRound} ${currencyShort}) × وسيط مكرر القطاع (${sectorMedianPe}x) = ${peFair} ${currencyAr} (وزن 55%)`,
        `2️⃣ تقييم مضاعف القيمة الدفترية للقطاع: القيمة الدفترية (${bvpsRound} ${currencyShort}) × وسيط مضاعف القطاع (${sectorMedianPb}x) = ${pbFair} ${currencyAr} (وزن 45%)`,
        wasCapped
          ? `✅ المجموع الأساسي = ${rawR} ${currencyAr} -> المعتمد بعد سقف الأمان (+65%) = ${fairValue} ${currencyAr}.`
          : `✅ السعر العادل المعتمد = ${fairValue} ${currencyAr}.`,
      ];
    } else if (isTechGrowth) {
      const { fv, rawR, wasCapped } = capUpside(0.7 * peFair + 0.3 * pbFair);
      fairValue = fv;
      modelType = "graham_fundamental";
      modelLabelAr = "مضاعفات قطاع التكنولوجيا والنمو الرقمي (P/E + P/B)";
      formulaEquationAr =
        "السعر العادل = (70% × هدف مكرر ربحية قطاع التكنولوجيا) + (30% × هدف مضاعف القيمة الدفترية)";
      formulaSubstitutionAr = wasCapped
        ? `(0.70 × ${peFair}) + (0.30 × ${pbFair}) = ${rawR} -> السقف التحفظي (+65%) = ${fairValue} ${currencyAr}`
        : `(0.70 × ${peFair}) + (0.30 × ${pbFair}) = ${fairValue} ${currencyAr}`;
      formulaStepsAr = [
        `1️⃣ تقييم مضاعف ربحية قطاع التكنولوجيا (${sectorAr}): ربحية السهم (${epsRound} ${currencyShort}) × وسيط مكرر القطاع (${sectorMedianPe}x) = ${peFair} ${currencyAr} (وزن 70% للنمو الرقمي)`,
        `2️⃣ تقييم مضاعف القيمة الدفترية: القيمة الدفترية (${bvpsRound} ${currencyShort}) × وسيط مضاعف القطاع (${sectorMedianPb}x) = ${pbFair} ${currencyAr} (وزن 30%)`,
        wasCapped
          ? `✅ المجموع الأساسي = ${rawR} ${currencyAr} -> المعتمد بعد سقف الأمان (+65%) = ${fairValue} ${currencyAr}.`
          : `✅ السعر العادل المعتمد = ${fairValue} ${currencyAr}.`,
      ];
    } else {
      const maxMult = isSaudi ? 22.5 : 16.0;
      const mult = Number(clamp(sectorMedianPe * sectorMedianPb, 8.0, maxMult).toFixed(2));
      grahamValue = Number(Math.sqrt(mult * effEps * bvps).toFixed(2));
      const { fv, rawR, wasCapped } = capUpside(
        0.4 * grahamValue + 0.35 * peFair + 0.25 * pbFair
      );
      fairValue = fv;
      modelType = "graham_fundamental";
      modelLabelAr = `نموذج جراهام ${marketTitleLabel} + مضاعف القطاع`;
      formulaEquationAr =
        "السعر العادل = (40% × قيمة جراهام المعدلة) + (35% × هدف مكرر ربحية القطاع) + (25% × هدف القيمة الدفترية للقطاع)";
      formulaSubstitutionAr = wasCapped
        ? `(0.40 × ${grahamValue}) + (0.35 × ${peFair}) + (0.25 × ${pbFair}) = ${rawR} -> السقف التحفظي (+65%) = ${fairValue} ${currencyAr}`
        : `(0.40 × ${grahamValue}) + (0.35 × ${peFair}) + (0.25 × ${pbFair}) = ${fairValue} ${currencyAr}`;
      formulaStepsAr = [
        `1️⃣ معادلة بنجامين جراهام المعدلة ${marketGrahamLabel}: √(مضاعف القطاع ${mult} × ربحية السهم ${epsRound} × القيمة الدفترية ${bvpsRound}) = ${grahamValue} ${currencyAr} (وزن 40%)`,
        `2️⃣ تقييم مضاعف ربحية القطاع (${sectorAr}): ربحية السهم (${epsRound}) × وسيط مكرر القطاع (${sectorMedianPe}x) = ${peFair} ${currencyAr} (وزن 35%)`,
        `3️⃣ تقييم مضاعف القيمة الدفترية للقطاع: القيمة الدفترية (${bvpsRound}) × وسيط مضاعف القطاع (${sectorMedianPb}x) = ${pbFair} ${currencyAr} (وزن 25%)`,
        wasCapped
          ? `✅ المجموع الأساسي = ${rawR} ${currencyAr} -> المعتمد بعد سقف الأمان (+65%) = ${fairValue} ${currencyAr}.`
          : `✅ السعر العادل المرجح للسهم = ${fairValue} ${currencyAr}.`,
      ];
    }
  } else if (effEps !== null && effEps > 0 && !isLossMaking) {
    const epsRound = Number(effEps.toFixed(2));
    const peFair = Number((effEps * sectorMedianPe).toFixed(2));
    const { fv, rawR, wasCapped } = capUpside(peFair);
    fairValue = fv;
    modelType = "pe_multiple";
    modelLabelAr = "مضاعف الربحية القطاعي (P/E)";
    formulaEquationAr = "السعر العادل = ربحية السهم (EPS) × وسيط مضاعف ربحية القطاع (Sector P/E)";
    formulaSubstitutionAr = wasCapped
      ? `${epsRound} × ${sectorMedianPe} = ${rawR} -> السقف التحفظي (+65%) = ${fairValue} ${currencyAr}`
      : `${epsRound} × ${sectorMedianPe} = ${fairValue} ${currencyAr}`;
    formulaStepsAr = [
      `1️⃣ ربحية السهم السنوية المحققة (EPS) = ${epsRound} ${currencyAr}`,
      `2️⃣ وسيط مضاعف الربحية لقطاع (${sectorAr}) = ${sectorMedianPe} مرة`,
      wasCapped
        ? `✅ القيمة الأساسية = ${rawR} ${currencyAr} -> المعتمد بعد سقف الأمان (+65%) = ${fairValue} ${currencyAr}.`
        : `✅ السعر العادل المعتمد = ${fairValue} ${currencyAr}.`,
    ];
  } else if (bvps !== null && bvps > 0) {
    const bvpsRound = Number(bvps.toFixed(2));
    if (isLossMaking) {
      const distressPb =
        roeChk !== null && roeChk <= -10
          ? 0.65
          : roeChk !== null && roeChk <= -5
          ? 0.75
          : 0.8;
      const pbFair = Number((bvps * distressPb).toFixed(2));
      const upperCap =
        close > 0
          ? Number((close * (roeChk !== null && roeChk <= -5 ? 0.9 : 0.95)).toFixed(2))
          : pbFair;
      fairValue = close > 0 ? Number(clamp(pbFair, close * 0.12, upperCap).toFixed(2)) : pbFair;
      const wasCapped = Math.abs(fairValue - pbFair) > 0.02;
      modelType = "pb_distressed";
      modelLabelAr = "قيمة دفترية مخفضة (شركة خاسرة)";
      formulaEquationAr =
        "السعر العادل التحفظي = القيمة الدفترية (BVPS) × معامل خصم الخسائر (0.65x–0.80x P/B)";
      formulaSubstitutionAr = wasCapped
        ? `${bvpsRound} × ${distressPb} = ${pbFair} -> سقف خصم الخسائر = ${fairValue} ${currencyAr}`
        : `${bvpsRound} × ${distressPb} = ${fairValue} ${currencyAr}`;
      formulaStepsAr = [
        `1️⃣ الشركة تسجّل صافي خسائر حالياً: القيمة الدفترية للسهم (BVPS) = ${bvpsRound} ${currencyAr}`,
        `2️⃣ تطبيق معامل خصم تآكل الحقوق للشركات الخاسرة = ${distressPb}x من القيمة الدفترية`,
        wasCapped
          ? `✅ القيمة الدفترية المخفضة = ${pbFair} ${currencyAr} -> المعتمد بسقف خصم الخسائر = ${fairValue} ${currencyAr}.`
          : `✅ السعر العادل التحفظي المعتمد = ${fairValue} ${currencyAr}.`,
      ];
    } else {
      const pbFair = Number((bvps * sectorMedianPb).toFixed(2));
      const { fv, rawR, wasCapped } = capUpside(pbFair);
      fairValue = fv;
      modelType = "pb_multiple";
      modelLabelAr = "مضاعف القيمة الدفترية (P/B)";
      formulaEquationAr =
        "السعر العادل = القيمة الدفترية للسهم (BVPS) × وسيط مضاعف القيمة الدفترية للقطاع (Sector P/B)";
      formulaSubstitutionAr = wasCapped
        ? `${bvpsRound} × ${sectorMedianPb} = ${rawR} -> السقف التحفظي (+65%) = ${fairValue} ${currencyAr}`
        : `${bvpsRound} × ${sectorMedianPb} = ${fairValue} ${currencyAr}`;
      formulaStepsAr = [
        `1️⃣ القيمة الدفترية للسهم من حقوق الملكية (BVPS) = ${bvpsRound} ${currencyAr}`,
        `2️⃣ وسيط مضاعف القيمة الدفترية لقطاع (${sectorAr}) = ${sectorMedianPb} مرة`,
        wasCapped
          ? `✅ القيمة الأساسية = ${rawR} ${currencyAr} -> المعتمد بعد سقف الأمان (+65%) = ${fairValue} ${currencyAr}.`
          : `✅ السعر العادل المعتمد = ${fairValue} ${currencyAr}.`,
      ];
    }
  } else {
    const ema200 = Number((ema200Val ?? close).toFixed(2));
    const vwap20 = Number((vwap20Val ?? close).toFixed(2));
    const rawQ = Number((0.6 * ema200 + 0.4 * vwap20).toFixed(2));
    if (isLossMaking && close > 0) {
      fairValue = Number(clamp(rawQ, close * 0.45, close * 0.85).toFixed(2));
      const wasCapped = Math.abs(fairValue - rawQ) > 0.02;
      modelType = "pb_distressed";
      modelLabelAr = "توازن كمي مخفض (شركة خاسرة)";
      formulaEquationAr =
        "السعر التحفظي لشركة خاسرة بدون حقوق ملكية موجبة = التوازن الكمي بسقف خصم الخسائر";
      formulaSubstitutionAr = wasCapped
        ? `(0.60 × ${ema200}) + (0.40 × ${vwap20}) = ${rawQ} -> سقف خصم الخسائر = ${fairValue} ${currencyAr}`
        : `(0.60 × ${ema200}) + (0.40 × ${vwap20}) = ${fairValue} ${currencyAr}`;
      formulaStepsAr = [
        `1️⃣ الشركة تسجل خسائر وحقوق ملكية غير موجبة: متوسط التوازن (EMA200=${ema200}، VWAP20=${vwap20})`,
        `✅ السعر التحفظي المعتمد = ${fairValue} ${currencyAr}.`,
      ];
    } else {
      fairValue = close > 0 ? Number(clamp(rawQ, close * 0.6, close * 1.5).toFixed(2)) : rawQ;
      const wasCapped = Math.abs(fairValue - rawQ) > 0.02;
      modelType = "quant_vwap";
      modelLabelAr = "التوازن الكمي (VWAP + EMA200)";
      formulaEquationAr =
        "السعر العادل الكمي = (60% × المتوسط الأسي EMA200) + (40% × متوسط التكلفة المرجح بالسيولة VWAP20)";
      formulaSubstitutionAr = wasCapped
        ? `(0.60 × ${ema200}) + (0.40 × ${vwap20}) = ${rawQ} -> المعتمد = ${fairValue} ${currencyAr}`
        : `(0.60 × ${ema200}) + (0.40 × ${vwap20}) = ${fairValue} ${currencyAr}`;
      formulaStepsAr = [
        `1️⃣ متوسط التوازن السعري طويل الأجل (EMA 200) = ${ema200} ${currencyAr} (وزن 60%)`,
        `2️⃣ متوسط سعر التكلفة المرجح بالسيولة لآخر 20 جلسة (VWAP 20) = ${vwap20} ${currencyAr} (وزن 40%)`,
        `✅ السعر العادل التوازني المعتمد = ${fairValue} ${currencyAr}.`,
      ];
    }
  }

  const upsidePct =
    close > 0 ? Number((((fairValue - close) / close) * 100).toFixed(2)) : 0;

  let status: FairValueStatus = "fair";
  if (isLossMaking) {
    status = "overvalued";
  } else if (upsidePct >= 15) {
    status = "undervalued";
  } else if (upsidePct <= -12) {
    status = "overvalued";
  }

  const rowDate = ind?.date ? String(ind.date).slice(0, 10) : null;

  return {
    symbol: sym,
    nameAr,
    nameEn,
    sectorAr,
    currencySymbol: currencyAr,
    logoUrl: typeof data.logoUrl === "string" ? data.logoUrl : null,
    currentPrice: Number(close.toFixed(2)),
    changePct:
      finiteNum(ind?.change_pct) !== null
        ? Number(Number(ind.change_pct).toFixed(2))
        : null,
    fairValue,
    grahamValue,
    classicGrahamValue,
    isLossMaking,
    upsidePct,
    status,
    modelType,
    modelLabelAr,
    formulaEquationAr,
    formulaSubstitutionAr,
    formulaStepsAr,
    eps: eps !== null ? Number(eps.toFixed(2)) : null,
    bvps: bvps !== null ? Number(bvps.toFixed(2)) : null,
    peRatio,
    pbRatio,
    sectorMedianPe,
    sectorMedianPb,
    dividendYield:
      finiteNum(data.dividendYield) !== null
        ? Number(Number(data.dividendYield).toFixed(2))
        : null,
    roe:
      finiteNum(data.roe) !== null
        ? Number(Number(data.roe).toFixed(2))
        : null,
    marketCap: finiteNum(data.marketCap),
    rsi14:
      finiteNum(ind?.rsi_14) !== null
        ? Number(Number(ind.rsi_14).toFixed(1))
        : null,
    ema200: ema200Val !== null ? Number(ema200Val.toFixed(2)) : null,
    vwap20: vwap20Val !== null ? Number(vwap20Val.toFixed(2)) : null,
    isSharia: isShariaCompliant(sym, params.market || (isSaudi ? "tasi" : "egx")),
    date: rowDate,
  };
}

export function computeFairValueReport(
  fundamentalsRows: Array<Record<string, any>>,
  indicatorRows: Array<Record<string, any>>,
  market: "egx" | "tasi" | "uae" | "qatar" = "egx"
): FairValueReport {
  const fundMap = new Map<string, Record<string, any>>();
  for (const row of fundamentalsRows || []) {
    const sym = String(row?.symbol || "").trim().toUpperCase();
    if (!sym) continue;
    fundMap.set(sym, row);
  }

  const sectorPes = new Map<string, number[]>();
  const sectorPbs = new Map<string, number[]>();
  const seenMedians = new Set<string>();

  for (const ind of indicatorRows || []) {
    const sym = String(ind?.symbol || "").trim().toUpperCase();
    const close = finiteNum(ind?.close);
    if (!sym || !close || close <= 0 || seenMedians.has(sym)) continue;
    seenMedians.add(sym);

    const fundRow = fundMap.get(sym);
    const rawData =
      fundRow?.data && typeof fundRow.data === "object" ? fundRow.data : {};
    if (rawData.isListed === false) continue;

    const data = normalizeFundamentalsForValuation(rawData, close, sym, market);
    const sectorAr = resolveSectorAr(sym, data.sector, data.industry);
    const eps = finiteNum(data.eps);
    const bvps = finiteNum(data.bookValuePerShare);
    const netInc = finiteNum(data.netIncome);
    const roe = finiteNum(data.roe);
    const lossMk = Boolean(
      (eps !== null && eps <= 0) ||
        (netInc !== null && netInc < 0) ||
        (roe !== null && roe < 0)
    );
    const pe = !lossMk && eps && eps > 0 ? close / eps : !lossMk ? finiteNum(data.peRatio) : null;
    const pb = bvps && bvps > 0 ? close / bvps : finiteNum(data.pbRatio);

    if (pe !== null && pe > 2.0 && pe <= 35) {
      const list = sectorPes.get(sectorAr) || [];
      list.push(pe);
      sectorPes.set(sectorAr, list);
    }
    if (!lossMk && pb !== null && pb > 0.3 && pb <= 8.0) {
      const list = sectorPbs.get(sectorAr) || [];
      list.push(pb);
      sectorPbs.set(sectorAr, list);
    }
  }

  const maxPeCap = market === "tasi" ? 18.0 : 13.5;
  const maxPbCap = market === "tasi" ? 3.0 : 2.6;

  const items: FairValueStockItem[] = [];
  let latestSessionDate: string | null = null;
  const seenSymbols = new Set<string>();

  for (const ind of indicatorRows || []) {
    const sym = String(ind?.symbol || "").trim().toUpperCase();
    const close = finiteNum(ind?.close);
    if (!sym || !close || close <= 0 || seenSymbols.has(sym)) continue;
    seenSymbols.add(sym);

    const fundRow = fundMap.get(sym);
    const data =
      fundRow?.data && typeof fundRow.data === "object" ? fundRow.data : {};
    if (data.isListed === false) continue;

    const rowDate = ind?.date ? String(ind.date).slice(0, 10) : null;
    if (rowDate && (!latestSessionDate || rowDate > latestSessionDate)) {
      latestSessionDate = rowDate;
    }

    const sectorAr = resolveSectorAr(sym, data.sector, data.industry);
    const [defPe, defPb] = defaultSectorMultiples(sectorAr, market);
    const peerPes = sectorPes.get(sectorAr) || [];
    const peerPbs = sectorPbs.get(sectorAr) || [];
    const sectorMedianPe = Number(
      clamp(peerPes.length >= 3 ? median(peerPes, defPe) : defPe, 6.0, maxPeCap).toFixed(2)
    );
    const sectorMedianPb = Number(
      clamp(peerPbs.length >= 3 ? median(peerPbs, defPb) : defPb, 1.0, maxPbCap).toFixed(2)
    );

    items.push(
      computeSingleStockFairValue({
        symbol: sym,
        close,
        fundRow,
        fundData: data,
        latestTech: ind,
        sectorMedianPe,
        sectorMedianPb,
        market,
      })
    );
  }

  items.sort((a, b) => {
    if (b.upsidePct !== a.upsidePct) return b.upsidePct - a.upsidePct;
    return a.modelType === "graham_fundamental" ? -1 : 1;
  });

  const undervaluedCount = items.filter((s) => s.status === "undervalued").length;
  const fairCount = items.filter((s) => s.status === "fair").length;
  const overvaluedCount = items.filter((s) => s.status === "overvalued").length;
  const fundamentalCoverageCount = items.filter(
    (s) => s.modelType !== "quant_vwap"
  ).length;
  const sectors = Array.from(new Set(items.map((s) => s.sectorAr))).sort(
    (a, b) => a.localeCompare(b, "ar")
  );

  return {
    market,
    currencyCode:
      market === "tasi"
        ? "SAR"
        : market === "uae"
        ? "AED"
        : market === "qatar"
        ? "QAR"
        : "EGP",
    updatedAt: new Date().toISOString(),
    latestSessionDate,
    summary: {
      totalEvaluated: items.length,
      undervaluedCount,
      fairCount,
      overvaluedCount,
      fundamentalCoverageCount,
    },
    sectors,
    stocks: items,
  };
}

/** Return true only when `candidate` carries newer fair-value data than `baseline`. */
export function shouldPreferFreshFairValueReport(
  candidate: FairValueReport | null | undefined,
  baseline: FairValueReport | null | undefined
): boolean {
  if (!candidate?.stocks?.length) return false;
  if (!baseline?.stocks?.length) return true;
  const candSession = candidate.latestSessionDate || "";
  const baseSession = baseline.latestSessionDate || "";
  if (candSession && baseSession && candSession !== baseSession) {
    return candSession > baseSession;
  }
  const candMs = Date.parse(candidate.updatedAt || "");
  const baseMs = Date.parse(baseline.updatedAt || "");
  if (Number.isFinite(candMs) && Number.isFinite(baseMs)) {
    return candMs > baseMs;
  }
  return Boolean(candSession && !baseSession) || !Number.isFinite(baseMs);
}
