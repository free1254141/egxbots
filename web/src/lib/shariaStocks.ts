import { isSaudiSymbol } from "@/lib/saudi-stocks";

export type ShariaMarket = "egx" | "tasi";

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

/**
 * الأسهم السعودية المتوافقة مع الضوابط الشرعية في السوق السعودي (تاسي TASI)
 * وفق قوائم الهيئات الشرعية المعتمدة (الراجحي المالية، الإنماء، البلاد، ومعايير الأيوفي).
 */
export const SHARIA_COMPLIANT_TASI_SYMBOLS: readonly string[] = [
  "1120", // مصرف الراجحي
  "1150", // مصرف الإنماء
  "1140", // بنك البلاد
  "1020", // بنك الجزيرة
  "2222", // أرامكو السعودية
  "7010", // إس تي سي (stc)
  "2010", // سابك
  "2020", // سابك للمغذيات الزراعية
  "2280", // المراعي
  "4013", // سليمان الحبيب
  "1211", // معادن
  "2082", // أكوا باور
  "2083", // مرافق
  "4190", // جرير
  "4200", // الدريس
  "7020", // موبايلي
  "7202", // سلوشنز
  "7203", // علم
  "7200", // أم آي إس
  "4001", // أسواق العثيم
  "4002", // المواساة
  "4003", // إكسترا
  "4004", // دله الصحية
  "4005", // رعاية
  "4009", // المستشفى السعودي الألماني
  "2270", // سدافكو
  "2223", // لوبريف
  "2290", // ينساب
  "2310", // سبكيم العالمية
  "2330", // المتقدمة
  "3010", // أسمنت العربية
  "3020", // أسمنت اليمامة
  "3030", // أسمنت السعودية
  "3050", // أسمنت الجنوب
  "4300", // دار الأركان
  "4090", // طيبة للاستثمار
  "4100", // مكة للإنشاء
  "4250", // جبل عمر
  "5110", // كهرباء السعودية
  "1322", // أماك
  "1830", // لجام للرياضة
  "4030", // البحري
  "4260", // بدجت السعودية
  "4261", // ذيب لتأجير السيارات
];

const SHARIA_TASI_SET = new Set(SHARIA_COMPLIANT_TASI_SYMBOLS.map((s) => s.toUpperCase()));

function resolveShariaMarket(
  symbol: string,
  market?: ShariaMarket
): ShariaMarket {
  if (market === "tasi" || market === "egx") return market;
  return isSaudiSymbol(symbol) ? "tasi" : "egx";
}

export function getShariaSymbolsForMarket(market: ShariaMarket): readonly string[] {
  return market === "tasi" ? SHARIA_COMPLIANT_TASI_SYMBOLS : SHARIA_COMPLIANT_EGX_SYMBOLS;
}

export function isShariaCompliant(
  symbol: string | null | undefined,
  market?: ShariaMarket
): boolean {
  if (!symbol) return false;
  const base = symbol.trim().toUpperCase().split(".")[0];
  const resolved = resolveShariaMarket(symbol, market);
  return resolved === "tasi" ? SHARIA_TASI_SET.has(base) : SHARIA_SET.has(base);
}

export function getShariaCompliantCount(market?: ShariaMarket): number {
  return market === "tasi" ? SHARIA_TASI_SET.size : SHARIA_SET.size;
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

/**
 * نسب التطهير المدققة لأسهم السوق السعودي (تاسي TASI) وفق معايير الهيئات الشرعية
 * (الراجحي المالية، الإنماء، البلاد، ومجمع الفقه الإسلامي / معيار 21 للأيوفي).
 */
export const SAUDI_STOCK_PURIFICATION_RATES: Record<string, ShariaStockMeta> = {
  "1120": {
    symbol: "1120",
    purificationRatePct: 0.0,
    isPureHalal: true,
    notesAr: "مصرف إسلامي متكامل بإشراف هيئة شرعية مستقلة — لا يتطلب أي تطهير للتوزيعات (0.0%)",
    sourceLabelAr: "الهيئة الشرعية لمصرف الراجحي",
  },
  "1150": {
    symbol: "1150",
    purificationRatePct: 0.0,
    isPureHalal: true,
    notesAr: "مصرف إسلامي نقي جميع معاملاته متوافقة مع الضوابط الشرعية — لا يتطلب تطهيراً (0.0%)",
    sourceLabelAr: "الهيئة الشرعية لمصرف الإنماء",
  },
  "1140": {
    symbol: "1140",
    purificationRatePct: 0.0,
    isPureHalal: true,
    notesAr: "بنك إسلامي متكامل بإشراف هيئة شرعية مستقلة — لا يتطلب أي تطهير (0.0%)",
    sourceLabelAr: "الهيئة الشرعية لبنك البلاد",
  },
  "1020": {
    symbol: "1020",
    purificationRatePct: 0.0,
    isPureHalal: true,
    notesAr: "مصرف إسلامي متحول بالكامل إلى الصيرفة الإسلامية — نسبة التطهير (0.0%)",
    sourceLabelAr: "الهيئة الشرعية لبنك الجزيرة",
  },
  "2222": {
    symbol: "2222",
    purificationRatePct: 0.6,
    notesAr: "إيرادات مرابحات وودائع مالية عارضة من فوائض السيولة التشغيلية (حوالي 0.6% من الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - معايير الهيئة الشرعية والأيوفي",
  },
  "7010": {
    symbol: "7010",
    purificationRatePct: 1.1,
    notesAr: "عوائد استثمارات وودائع قصيرة الأجل عارضة (حوالي 1.1% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الراجحي المالية ومجمع الفقه",
  },
  "2010": {
    symbol: "2010",
    purificationRatePct: 1.4,
    notesAr: "عوائد فوائد وودائع بنكية عارضة من السيولة العالمية (حوالي 1.4% من الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - معايير الهيئة الشرعية والأيوفي",
  },
  "2020": {
    symbol: "2020",
    purificationRatePct: 0.8,
    notesAr: "إيرادات تمويلية وودائع عارضة منخفضة (حوالي 0.8% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الهيئة الشرعية السعودية",
  },
  "2280": {
    symbol: "2280",
    purificationRatePct: 0.5,
    notesAr: "عوائد ودائع بنكية عارضة محدودة جداً (حوالي 0.5% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الراجحي المالية",
  },
  "4013": {
    symbol: "4013",
    purificationRatePct: 0.4,
    notesAr: "نشاط طبي متوافق مع عوائد ودائع عارضة طفيفة (حوالي 0.4% من الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - معيار الأيوفي والهيئة الشرعية",
  },
  "1211": {
    symbol: "1211",
    purificationRatePct: 1.3,
    notesAr: "عوائد ودائع وتمويلات عارضة (حوالي 1.3% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الهيئة الشرعية السعودية",
  },
  "2082": {
    symbol: "2082",
    purificationRatePct: 1.8,
    notesAr: "عوائد تمويلية وإيداعات لمشاريع الطاقة والمياه (حوالي 1.8% من الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - معايير الهيئة الشرعية والأيوفي",
  },
  "4190": {
    symbol: "4190",
    purificationRatePct: 0.3,
    notesAr: "عوائد بنكية عارضة ضئيلة جداً في قطاع التجزئة (حوالي 0.3% من الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الراجحي المالية",
  },
  "4200": {
    symbol: "4200",
    purificationRatePct: 0.4,
    notesAr: "عوائد ودائع بنكية محدودة (حوالي 0.4% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الهيئة الشرعية السعودية",
  },
  "7020": {
    symbol: "7020",
    purificationRatePct: 0.9,
    notesAr: "إيرادات فوائد عارضة من أرصدة النقد (حوالي 0.9% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - معيار 21 أيوفي والهيئة الشرعية",
  },
  "7202": {
    symbol: "7202",
    purificationRatePct: 0.7,
    notesAr: "عوائد مرابحات وودائع قصيرة الأجل عارضة (حوالي 0.7% من الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الراجحي المالية",
  },
  "7203": {
    symbol: "7203",
    purificationRatePct: 0.9,
    notesAr: "عوائد استثمارية وودائع نقدية عارضة (حوالي 0.9% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الهيئة الشرعية السعودية",
  },
  "4001": {
    symbol: "4001",
    purificationRatePct: 0.3,
    notesAr: "عوائد ودائع بنكية طفيفة في قطاع التجزئة الغذائية (حوالي 0.3% من الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الراجحي المالية",
  },
  "4002": {
    symbol: "4002",
    purificationRatePct: 0.4,
    notesAr: "إيرادات تمويلية عارضة منخفضة جداً (حوالي 0.4% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - معايير الهيئة الشرعية السعودية",
  },
  "4003": {
    symbol: "4003",
    purificationRatePct: 0.6,
    notesAr: "عوائد ودائع ومبيعات آجلة متوافقة مع عوائد عارضة طفيفة (حوالي 0.6%)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الراجحي المالية",
  },
  "2270": {
    symbol: "2270",
    purificationRatePct: 0.5,
    notesAr: "عوائد ودائع نقدية عارضة منخفضة (حوالي 0.5% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - معيار الأيوفي والهيئة الشرعية",
  },
  "2290": {
    symbol: "2290",
    purificationRatePct: 1.0,
    notesAr: "عوائد ودائع ومرابحات عارضة (حوالي 1.0% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الهيئة الشرعية السعودية",
  },
  "2310": {
    symbol: "2310",
    purificationRatePct: 1.1,
    notesAr: "عوائد فوائد وودائع بنكية عارضة (حوالي 1.1% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الهيئة الشرعية السعودية",
  },
  "3020": {
    symbol: "3020",
    purificationRatePct: 0.5,
    notesAr: "عوائد ودائع عارضة محدودة في قطاع الأسمنت (حوالي 0.5% من الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الراجحي المالية",
  },
  "3030": {
    symbol: "3030",
    purificationRatePct: 0.6,
    notesAr: "عوائد ودائع بنكية عارضة منخفضة (حوالي 0.6% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الراجحي المالية",
  },
  "4300": {
    symbol: "4300",
    purificationRatePct: 1.5,
    notesAr: "عوائد ودائع وتمويلات عقارية عارضة (حوالي 1.5% من إجمالي الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - معايير الهيئة الشرعية ومجمع الفقه",
  },
  "5110": {
    symbol: "5110",
    purificationRatePct: 1.2,
    notesAr: "عوائد ودائع وتمويلات قطاع المرافق والطاقة (حوالي 1.2% من الإيرادات)",
    sourceLabelAr: "القوائم المالية المدققة - ضوابط الهيئة الشرعية السعودية",
  },
};

export function getStockPurificationMeta(
  symbol: string | null | undefined,
  market?: ShariaMarket
): ShariaStockMeta | null {
  if (!symbol) return null;
  const base = symbol.trim().toUpperCase().split(".")[0];
  const resolved = resolveShariaMarket(symbol, market);
  if (resolved === "tasi") {
    return SAUDI_STOCK_PURIFICATION_RATES[base] ?? null;
  }
  return STOCK_PURIFICATION_RATES[base] ?? null;
}
