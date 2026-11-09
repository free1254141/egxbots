export const SHARIA_COMPLIANT_EGX_SYMBOLS: readonly string[] = [
  "ISPH",
  "AMOC",
  "ICFC",
  "IFAP",
  "OCDI",
  "RMDA",
  "ACGC",
  "ARCC",
  "CIRA",
  "ETRS",
  "ETEL",
  "MPCO",
  "ORWE",
  "MTIE",
  "ORAS",
  "ORHD",
  "EFIH",
  "EFID",
  "PHDC",
  "SAUD",
  "FAITA",
  "FAIT",
  "JUFO",
  "RACC",
  "SKPC",
  "OLFI",
  "EGAS",
  "LCSW",
  "TMGH",
  "MASR",
  "ATQA",
  "MCQE",
  "EGAL",
  "ADIB",
  "SWDY",
  "ABUK",
  "MFPC",
];

const SHARIA_SET = new Set(SHARIA_COMPLIANT_EGX_SYMBOLS.map((s) => s.toUpperCase()));

export function isShariaCompliant(symbol: string | null | undefined): boolean {
  if (!symbol) return false;
  const base = symbol.toUpperCase().split(".")[0];
  return SHARIA_SET.has(base);
}

export function getShariaCompliantCount(): number {
  return SHARIA_SET.size;
}

export interface ShariaStockMeta {
  symbol: string;
  purificationRatePct: number;
  isPureHalal?: boolean; // بنك أو مؤسسة إسلامية بالكامل بنسبة تطهير 0.0%
  notesAr: string;
  sourceLabelAr: string;
}

/**
 * نسب التطهير المدققة لأسهم مؤشر EGX 33 الشريعي وفق معيار (21) للأيوفي
 * المعادلة: نسبة التطهير = الفوائد الدائنة العارضة / إجمالي الإيرادات
 * تُخرج كنسبة مئوية من الكوبون النقدي الموزع فقط.
 */
export const STOCK_PURIFICATION_RATES: Record<string, ShariaStockMeta> = {
  FAIT: {
    symbol: "FAIT",
    purificationRatePct: 0.0,
    isPureHalal: true,
    notesAr: "بنك إسلامي بإشراف هيئة رقابة شرعية مستقلة — لا يتطلب أي تطهير للكوبون (0.0%)",
    sourceLabelAr: "هيئة الرقابة الشرعية لبنك فيصل",
  },
  FAITA: {
    symbol: "FAITA",
    purificationRatePct: 0.0,
    isPureHalal: true,
    notesAr: "بنك إسلامي بإشراف هيئة رقابة شرعية مستقلة — لا يتطلب أي تطهير للكوبون (0.0%)",
    sourceLabelAr: "هيئة الرقابة الشرعية لبنك فيصل",
  },
  ADIB: {
    symbol: "ADIB",
    purificationRatePct: 0.0,
    isPureHalal: true,
    notesAr: "مصرف إسلامي متكامل بإشراف هيئة رقابة شرعية مستقلة — لا يتطلب أي تطهير للكوبون (0.0%)",
    sourceLabelAr: "هيئة الرقابة الشرعية لمصرف أبوظبي الإسلامي",
  },
  SAUD: {
    symbol: "SAUD",
    purificationRatePct: 0.0,
    isPureHalal: true,
    notesAr: "مؤسسة مصرفية إسلامية خاضعة لمعايير الأيوفي — لا يتطلب تطهيراً (0.0%)",
    sourceLabelAr: "الرقابة الشرعية للصيرفة الإسلامية",
  },
  ABUK: {
    symbol: "ABUK",
    purificationRatePct: 0.9,
    notesAr: "عوائد فوائد دائنة عارضة من فوائض الودائع (حوالي 0.9% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  MFPC: {
    symbol: "MFPC",
    purificationRatePct: 0.4,
    notesAr: "فوائد بنكية عارضة منخفضة جداً (حوالي 0.4% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  SWDY: {
    symbol: "SWDY",
    purificationRatePct: 1.2,
    notesAr: "عوائد تمويلية وفوائد أذون خزانة عارضة (حوالي 1.2% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  TMGH: {
    symbol: "TMGH",
    purificationRatePct: 3.2,
    notesAr: "عوائد أذون خزانة وودائع مقدمات الحجوزات العقارية (حوالي 3.2% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  ORWE: {
    symbol: "ORWE",
    purificationRatePct: 0.3,
    notesAr: "عوائد استثمارات مالية ضئيلة جداً (حوالي 0.3% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  EFIH: {
    symbol: "EFIH",
    purificationRatePct: 2.7,
    notesAr: "عوائد ودائع وأذون خزانة من إدارة متحصلات الدفع الرقمي (حوالي 2.7% من الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  EFID: {
    symbol: "EFID",
    purificationRatePct: 1.4,
    notesAr: "عوائد فوائد بنكية عارضة (حوالي 1.4% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  AMOC: {
    symbol: "AMOC",
    purificationRatePct: 0.8,
    notesAr: "عوائد تمويلية بنكية عارضة (حوالي 0.8% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  SKPC: {
    symbol: "SKPC",
    purificationRatePct: 1.1,
    notesAr: "عوائد فوائد دائنة عارضة (حوالي 1.1% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  JUFO: {
    symbol: "JUFO",
    purificationRatePct: 0.7,
    notesAr: "عوائد ودائع بنكية عارضة (حوالي 0.7% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  ETEL: {
    symbol: "ETEL",
    purificationRatePct: 2.6,
    notesAr: "إيرادات فوائد بنكية وتمويلية عارضة (حوالي 2.6% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  MASR: {
    symbol: "MASR",
    purificationRatePct: 2.8,
    notesAr: "عوائد ودائع وأذون خزانة من متحصلات المشروعات (حوالي 2.8% من الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  PHDC: {
    symbol: "PHDC",
    purificationRatePct: 2.9,
    notesAr: "عوائد ودائع وأذون خزانة للمقدمات العقارية (حوالي 2.9% من الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  OCDI: {
    symbol: "OCDI",
    purificationRatePct: 2.5,
    notesAr: "عوائد ودائع وأذون خزانة عارضة (حوالي 2.5% من الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  ISPH: {
    symbol: "ISPH",
    purificationRatePct: 1.2,
    notesAr: "عوائد فوائد بنكية عارضة (حوالي 1.2% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  RMDA: {
    symbol: "RMDA",
    purificationRatePct: 1.1,
    notesAr: "عوائد تمويلية عارضة منخفضة (حوالي 1.1% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  ETRS: {
    symbol: "ETRS",
    purificationRatePct: 0.6,
    notesAr: "عوائد ودائع بنكية ضئيلة (حوالي 0.6% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  RACC: {
    symbol: "RACC",
    purificationRatePct: 1.5,
    notesAr: "عوائد فوائد بنكية عارضة (حوالي 1.5% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  ATQA: {
    symbol: "ATQA",
    purificationRatePct: 0.8,
    notesAr: "عوائد فوائد بنكية عارضة (حوالي 0.8% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  EGAL: {
    symbol: "EGAL",
    purificationRatePct: 0.7,
    notesAr: "عوائد تمويلية عارضة (حوالي 0.7% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  ARCC: {
    symbol: "ARCC",
    purificationRatePct: 1.3,
    notesAr: "عوائد فوائد بنكية عارضة (حوالي 1.3% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  ACGC: {
    symbol: "ACGC",
    purificationRatePct: 0.9,
    notesAr: "عوائد فوائد بنكية عارضة (حوالي 0.9% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  ORAS: {
    symbol: "ORAS",
    purificationRatePct: 1.8,
    notesAr: "عوائد تمويلية وإيداعات دولية عارضة (حوالي 1.8% من الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  ORHD: {
    symbol: "ORHD",
    purificationRatePct: 2.4,
    notesAr: "عوائد فوائد وتدفقات فندقية (حوالي 2.4% من الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  MTIE: {
    symbol: "MTIE",
    purificationRatePct: 1.5,
    notesAr: "عوائد فوائد بنكية عارضة (حوالي 1.5% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  OLFI: {
    symbol: "OLFI",
    purificationRatePct: 0.6,
    notesAr: "عوائد فوائد بنكية ضئيلة (حوالي 0.6% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  EGAS: {
    symbol: "EGAS",
    purificationRatePct: 1.0,
    notesAr: "عوائد فوائد بنكية عارضة (حوالي 1.0% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  LCSW: {
    symbol: "LCSW",
    purificationRatePct: 0.8,
    notesAr: "عوائد تمويلية عارضة (حوالي 0.8% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  MCQE: {
    symbol: "MCQE",
    purificationRatePct: 1.2,
    notesAr: "عوائد فوائد بنكية عارضة (حوالي 1.2% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  CIRA: {
    symbol: "CIRA",
    purificationRatePct: 1.6,
    notesAr: "عوائد ودائع تعليمية عارضة (حوالي 1.6% من الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  ICFC: {
    symbol: "ICFC",
    purificationRatePct: 0.7,
    notesAr: "عوائد فوائد بنكية ضئيلة (حوالي 0.7% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  IFAP: {
    symbol: "IFAP",
    purificationRatePct: 0.5,
    notesAr: "عوائد تمويلية ضئيلة (حوالي 0.5% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
  MPCO: {
    symbol: "MPCO",
    purificationRatePct: 0.8,
    notesAr: "عوائد فوائد بنكية عارضة (حوالي 0.8% من إجمالي الإيرادات)",
    sourceLabelAr: "قوائم مالية سنوية مدققة - معيار 21 أيوفي",
  },
};

export function getStockPurificationMeta(symbol: string | null | undefined): ShariaStockMeta | null {
  if (!symbol) return null;
  const base = symbol.toUpperCase().split(".")[0];
  return STOCK_PURIFICATION_RATES[base] ?? null;
}
