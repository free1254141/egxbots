import { CANONICAL_STOCK_NAMES } from "@/lib/ai/stock-names";
import { isShariaCompliant } from "@/lib/shariaStocks";

export type FairValueModelType =
  | "graham_fundamental"
  | "pe_multiple"
  | "pb_multiple"
  | "quant_vwap";

export type FairValueStatus = "undervalued" | "fair" | "overvalued";

export interface FairValueStockItem {
  symbol: string;
  nameAr: string;
  nameEn: string;
  sectorAr: string;
  logoUrl: string | null;
  currentPrice: number;
  changePct: number | null;
  fairValue: number;
  grahamValue: number | null;
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

const SECTOR_AR_MAP: Record<string, string> = {
  finance: "بنوك وخدمات مالية",
  "regional banks": "بنوك",
  "investment banks/brokers": "خدمات مالية غير مصرفية",
  "real estate development": "عقارات وإنشاءات",
  homebuilding: "عقارات وإنشاءات",
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
  communications: "اتصالات وتكنولوجيا",
  "energy minerals": "بترول وطاقة",
  "non-energy minerals": "مواد بناء، أسمنت وتعدين",
  "construction materials": "مواد بناء وأسمنت",
  transportation: "نقل وشحن ولوجستيات",
  "consumer services": "سياحة وخدمات",
  "commercial services": "مقاولات وخدمات تجارية",
  "distribution services": "تجارة وتوزيع",
  "retail trade": "تجارة وتجزئة",
  "consumer durables": "سلع معمرة وعقارات",
};

export function resolveSectorAr(
  symbol: string,
  rawSector?: string | null,
  rawIndustry?: string | null
): string {
  const canonical = CANONICAL_STOCK_NAMES[symbol]?.sector;
  if (canonical) return canonical;
  const indKey = String(rawIndustry || "").trim().toLowerCase();
  if (indKey && SECTOR_AR_MAP[indKey]) return SECTOR_AR_MAP[indKey];
  const secKey = String(rawSector || "").trim().toLowerCase();
  if (secKey && SECTOR_AR_MAP[secKey]) return SECTOR_AR_MAP[secKey];
  if (rawSector && /[\u0600-\u06FF]/.test(rawSector)) return rawSector;
  return "قطاعات متنوعة";
}

function finiteNum(val: unknown): number | null {
  if (val === null || val === undefined || val === "") return null;
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

export function computeSingleStockFairValue(params: {
  symbol: string;
  close: number;
  fundRow?: Record<string, any> | null;
  fundData?: Record<string, any> | null;
  latestTech?: Record<string, any> | null;
  sectorMedianPe?: number;
  sectorMedianPb?: number;
}): FairValueStockItem {
  const sym = String(params.symbol || "").trim().toUpperCase();
  const close = Number(params.close || 0);
  const fundRow = params.fundRow || {};
  const data =
    params.fundData && typeof params.fundData === "object"
      ? params.fundData
      : fundRow?.data && typeof fundRow.data === "object"
      ? fundRow.data
      : {};
  const ind = params.latestTech || {};

  const canonical = CANONICAL_STOCK_NAMES[sym];
  const nameAr =
    canonical?.name_ar ||
    fundRow?.name_ar ||
    data.name_ar ||
    fundRow?.name ||
    data.name ||
    sym;
  const nameEn =
    canonical?.name_en || fundRow?.name || data.name || sym;
  const sectorAr = resolveSectorAr(sym, data.sector, data.industry);

  const sectorMedianPe = Number((params.sectorMedianPe ?? 9.0).toFixed(2));
  const sectorMedianPb = Number((params.sectorMedianPb ?? 1.75).toFixed(2));

  const rawPe = finiteNum(data.peRatio ?? data.pe_ratio);
  const rawPb = finiteNum(data.pbRatio ?? data.pb_ratio);
  let eps = finiteNum(data.eps);
  if ((eps === null || eps === 0) && rawPe && rawPe > 0 && close > 0) {
    eps = Number((close / rawPe).toFixed(4));
  }
  let bvps = finiteNum(
    data.bookValuePerShare ??
      data.book_value_per_share ??
      data.book_value ??
      data.bvps
  );
  if ((bvps === null || bvps === 0) && rawPb && rawPb > 0 && close > 0) {
    bvps = Number((close / rawPb).toFixed(4));
  }

  const peRatio =
    eps && eps > 0
      ? Number((close / eps).toFixed(2))
      : rawPe
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

  let fairValue = close;
  let grahamValue: number | null = null;
  let modelType: FairValueModelType = "quant_vwap";
  let modelLabelAr = "التوازن الكمي (VWAP + EMA200)";
  let formulaEquationAr = "";
  let formulaSubstitutionAr = "";
  let formulaStepsAr: string[] = [];

  const isFinancial =
    sectorAr.includes("بنوك") ||
    sectorAr.includes("خدمات مالية") ||
    sectorAr.includes("استثمار");

  if (eps !== null && eps > 0 && bvps !== null && bvps > 0) {
    const epsRound = Number(eps.toFixed(2));
    const bvpsRound = Number(bvps.toFixed(2));
    const peFair = Number((eps * sectorMedianPe).toFixed(2));
    const pbFair = Number((bvps * sectorMedianPb).toFixed(2));

    if (isFinancial) {
      // Financial sector (banks/brokerages): Graham sqrt is not applicable to leveraged institutions;
      // standard valuation uses sector-calibrated P/E and P/B peer multiples.
      const blended = 0.55 * peFair + 0.45 * pbFair;
      fairValue = clamp(blended, close * 0.55, close * 1.65);
      fairValue = Number(fairValue.toFixed(2));
      modelType = "graham_fundamental";
      modelLabelAr = "مضاعفات القطاع المالي (P/E + P/B)";
      formulaEquationAr =
        "السعر العادل = (55% × هدف مكرر ربحية القطاع) + (45% × هدف القيمة الدفترية للقطاع)";
      formulaSubstitutionAr = `(0.55 × ${peFair}) + (0.45 × ${pbFair}) = ${fairValue} ج.م`;
      formulaStepsAr = [
        `1️⃣ تقييم مضاعف ربحية القطاع (${sectorAr}): ربحية السهم (${epsRound} ج) × وسيط مكرر القطاع (${sectorMedianPe}x) = ${peFair} ج.م (وزن 55%)`,
        `2️⃣ تقييم مضاعف القيمة الدفترية للقطاع: القيمة الدفترية (${bvpsRound} ج) × وسيط مضاعف القطاع (${sectorMedianPb}x) = ${pbFair} ج.م (وزن 45%)`,
        `✅ السعر العادل المعتمد = ${fairValue} ج.م (تقييم مؤسسي متوازن للقطاع المالي بدون تضخيم).`,
      ];
    } else {
      // Non-financial: EGX-calibrated Graham benchmark based on Egyptian market realities (8.0 - 14.0)
      const egxGrahamMult = Number(clamp(sectorMedianPe * sectorMedianPb, 8.0, 14.0).toFixed(2));
      const rawGraham = Math.sqrt(egxGrahamMult * eps * bvps);
      grahamValue = Number(rawGraham.toFixed(2));
      const blended = 0.40 * rawGraham + 0.35 * peFair + 0.25 * pbFair;
      fairValue = clamp(blended, close * 0.55, close * 1.65);
      fairValue = Number(fairValue.toFixed(2));
      modelType = "graham_fundamental";
      modelLabelAr = "نموذج جراهام المصري + مضاعف القطاع";
      formulaEquationAr =
        "السعر العادل = (40% × قيمة جراهام المعدلة) + (35% × هدف مكرر ربحية القطاع) + (25% × هدف القيمة الدفترية للقطاع)";
      formulaSubstitutionAr = `(0.40 × ${grahamValue}) + (0.35 × ${peFair}) + (0.25 × ${pbFair}) = ${fairValue} ج.م`;
      formulaStepsAr = [
        `1️⃣ معادلة بنجامين جراهام المعدلة للبورصة المصرية: √(مضاعف السوق ${egxGrahamMult} × ربحية السهم ${epsRound} × القيمة الدفترية ${bvpsRound}) = ${grahamValue} ج.م (وزن 40%)`,
        `2️⃣ تقييم مضاعف ربحية القطاع (${sectorAr}): ربحية السهم (${epsRound}) × وسيط مكرر القطاع (${sectorMedianPe}x) = ${peFair} ج.م (وزن 35%)`,
        `3️⃣ تقييم مضاعف القيمة الدفترية للقطاع: القيمة الدفترية (${bvpsRound}) × وسيط مضاعف القطاع (${sectorMedianPb}x) = ${pbFair} ج.م (وزن 25%)`,
        `✅ السعر العادل المرجح للسهم = ${fairValue} ج.م (مع صمام أمان سعري للمحافظة على واقعية ومصداقية التقييم).`,
      ];
    }
  } else if (eps !== null && eps > 0) {
    const epsRound = Number(eps.toFixed(2));
    const peFair = Number((eps * sectorMedianPe).toFixed(2));
    fairValue = clamp(eps * sectorMedianPe, close * 0.50, close * 1.65);
    fairValue = Number(fairValue.toFixed(2));
    modelType = "pe_multiple";
    modelLabelAr = "مضاعف الربحية القطاعي (P/E)";
    formulaEquationAr = "السعر العادل = ربحية السهم (EPS) × وسيط مضاعف ربحية القطاع (Sector P/E)";
    formulaSubstitutionAr = `${epsRound} × ${sectorMedianPe} = ${fairValue} ج.م`;
    formulaStepsAr = [
      `1️⃣ ربحية السهم السنوية المحققة (EPS) = ${epsRound} ج.م`,
      `2️⃣ وسيط مضاعف الربحية لقطاع (${sectorAr}) = ${sectorMedianPe} مرة`,
      `✅ السعر العادل = ${epsRound} × ${sectorMedianPe} = ${peFair} ج.م -> المعتمد ${fairValue} ج.م.`,
    ];
  } else if (bvps !== null && bvps > 0) {
    const bvpsRound = Number(bvps.toFixed(2));
    const pbFair = Number((bvps * sectorMedianPb).toFixed(2));
    fairValue = clamp(bvps * sectorMedianPb, close * 0.50, close * 1.65);
    fairValue = Number(fairValue.toFixed(2));
    modelType = "pb_multiple";
    modelLabelAr = "مضاعف القيمة الدفترية (P/B)";
    formulaEquationAr = "السعر العادل = القيمة الدفترية للسهم (BVPS) × وسيط مضاعف القيمة الدفترية للقطاع (Sector P/B)";
    formulaSubstitutionAr = `${bvpsRound} × ${sectorMedianPb} = ${fairValue} ج.م`;
    formulaStepsAr = [
      `1️⃣ القيمة الدفترية للسهم من حقوق الملكية (BVPS) = ${bvpsRound} ج.م`,
      `2️⃣ وسيط مضاعف القيمة الدفترية لقطاع (${sectorAr}) = ${sectorMedianPb} مرة`,
      `✅ السعر العادل = ${bvpsRound} × ${sectorMedianPb} = ${pbFair} ج.م -> المعتمد ${fairValue} ج.م.`,
    ];
  } else {
    const ema200 = Number((ema200Val ?? close).toFixed(2));
    const vwap20 = Number((vwap20Val ?? close).toFixed(2));
    const quantFair = 0.6 * ema200 + 0.4 * vwap20;
    fairValue = clamp(quantFair, close * 0.60, close * 1.50);
    fairValue = Number(fairValue.toFixed(2));
    modelType = "quant_vwap";
    modelLabelAr = "التوازن الكمي (VWAP + EMA200)";
    formulaEquationAr = "السعر العادل الكمي = (60% × المتوسط الأسي EMA200) + (40% × متوسط التكلفة المرجح بالسيولة VWAP20)";
    formulaSubstitutionAr = `(0.60 × ${ema200}) + (0.40 × ${vwap20}) = ${fairValue} ج.م`;
    formulaStepsAr = [
      `1️⃣ متوسط التوازن السعري طويل الأجل (EMA 200) = ${ema200} ج.م (وزن 60%)`,
      `2️⃣ متوسط سعر التكلفة المرجح بالسيولة لآخر 20 جلسة (VWAP 20) = ${vwap20} ج.م (وزن 40%)`,
      `✅ السعر العادل التوازني = (0.60 × ${ema200}) + (0.40 × ${vwap20}) = ${fairValue} ج.م.`,
    ];
  }

  const upsidePct = close > 0 ? Number((((fairValue - close) / close) * 100).toFixed(2)) : 0;

  let status: FairValueStatus = "fair";
  if (upsidePct >= 15) {
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
    logoUrl: typeof data.logoUrl === "string" ? data.logoUrl : null,
    currentPrice: Number(close.toFixed(2)),
    changePct:
      finiteNum(ind?.change_pct) !== null
        ? Number(Number(ind.change_pct).toFixed(2))
        : null,
    fairValue,
    grahamValue,
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
    isSharia: isShariaCompliant(sym),
    date: rowDate,
  };
}

export function computeFairValueReport(
  fundamentalsRows: Array<Record<string, any>>,
  indicatorRows: Array<Record<string, any>>
): FairValueReport {
  const fundMap = new Map<string, Record<string, any>>();
  for (const row of fundamentalsRows || []) {
    const sym = String(row?.symbol || "").trim().toUpperCase();
    if (!sym) continue;
    fundMap.set(sym, row);
  }

  // Group valid P/E and P/B by Arabic sector to calculate peer medians
  const sectorPes = new Map<string, number[]>();
  const sectorPbs = new Map<string, number[]>();
  const allValidPes: number[] = [];
  const allValidPbs: number[] = [];

  for (const ind of indicatorRows || []) {
    const sym = String(ind?.symbol || "").trim().toUpperCase();
    const close = finiteNum(ind?.close);
    if (!sym || !close || close <= 0) continue;

    const fundRow = fundMap.get(sym);
    const data =
      fundRow?.data && typeof fundRow.data === "object" ? fundRow.data : {};
    if (data.isListed === false) continue;

    const sectorAr = resolveSectorAr(sym, data.sector, data.industry);
    const eps = finiteNum(data.eps);
    const bvps = finiteNum(data.bookValuePerShare);
    const pe = eps && eps > 0 ? close / eps : finiteNum(data.peRatio);
    const pb = bvps && bvps > 0 ? close / bvps : finiteNum(data.pbRatio);

    if (pe !== null && pe > 1.5 && pe <= 45) {
      const list = sectorPes.get(sectorAr) || [];
      list.push(pe);
      sectorPes.set(sectorAr, list);
      allValidPes.push(pe);
    }
    if (pb !== null && pb > 0.25 && pb <= 12) {
      const list = sectorPbs.get(sectorAr) || [];
      list.push(pb);
      sectorPbs.set(sectorAr, list);
      allValidPbs.push(pb);
    }
  }

  const globalMedianPe =
    allValidPes.length >= 5
      ? clamp(median(allValidPes, 9.0), 7.5, 14.0)
      : 9.0;
  const globalMedianPb =
    allValidPbs.length >= 5
      ? clamp(median(allValidPbs, 1.75), 1.45, 3.0)
      : 1.75;

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
    const peerPes = sectorPes.get(sectorAr) || [];
    const peerPbs = sectorPbs.get(sectorAr) || [];
    const sectorMedianPe = Number(
      clamp(
        peerPes.length >= 2 ? median(peerPes, globalMedianPe) : globalMedianPe,
        6.0,
        15.0
      ).toFixed(2)
    );
    const sectorMedianPb = Number(
      clamp(
        peerPbs.length >= 2 ? median(peerPbs, globalMedianPb) : globalMedianPb,
        1.0,
        3.2
      ).toFixed(2)
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
      })
    );
  }

  // Sort primarily by highest upside (most undervalued first), preferring fundamental models on ties
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
