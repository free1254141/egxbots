export interface SaudiStockInfo {
  symbol: string;
  name: string;
  name_ar: string;
  exchange: "TADAWUL";
  country: "Saudi Arabia";
}

export const POPULAR_TASI_STOCKS: SaudiStockInfo[] = [
  { symbol: "2222", name: "Saudi Aramco", name_ar: "أرامكو السعودية", exchange: "TADAWUL", country: "Saudi Arabia" },
  { symbol: "1120", name: "Al Rajhi Bank", name_ar: "مصرف الراجحي", exchange: "TADAWUL", country: "Saudi Arabia" },
  { symbol: "2010", name: "SABIC", name_ar: "سابك", exchange: "TADAWUL", country: "Saudi Arabia" },
  { symbol: "7010", name: "Saudi Telecom (stc)", name_ar: "إس تي سي", exchange: "TADAWUL", country: "Saudi Arabia" },
  { symbol: "1180", name: "Saudi National Bank", name_ar: "البنك الأهلي السعودي", exchange: "TADAWUL", country: "Saudi Arabia" },
  { symbol: "1211", name: "Ma'aden", name_ar: "معادن", exchange: "TADAWUL", country: "Saudi Arabia" },
  { symbol: "4013", name: "Dr. Sulaiman Al Habib", name_ar: "سليمان الحبيب", exchange: "TADAWUL", country: "Saudi Arabia" },
  { symbol: "2082", name: "ACWA Power", name_ar: "أكوا باور", exchange: "TADAWUL", country: "Saudi Arabia" },
  { symbol: "1150", name: "Alinma Bank", name_ar: "مصرف الإنماء", exchange: "TADAWUL", country: "Saudi Arabia" },
  { symbol: "2280", name: "Almarai", name_ar: "المراعي", exchange: "TADAWUL", country: "Saudi Arabia" },
];

export const SAUDI_STOCK_NAMES_AR: Record<string, string> = {
  "1010": "بنك الرياض",
  "1020": "بنك الجزيرة",
  "1030": "البنك السعودي للاستثمار",
  "1050": "البنك السعودي الفرنسي",
  "1060": "البنك السعودي الأول",
  "1080": "البنك العربي الوطني",
  "1120": "مصرف الراجحي",
  "1140": "بنك البلاد",
  "1150": "مصرف الإنماء",
  "1180": "البنك الأهلي السعودي",
  "1182": "أملاك العالمية",
  "1183": "سهل للتمويل",
  "1211": "معادن",
  "1304": "اليمامة للحديد",
  "1320": "أنابيب السعودية",
  "1322": "أماك",
  "1830": "لجام للرياضة",
  "2001": "كيمانول",
  "2010": "سابك",
  "2020": "سابك للمغذيات الزراعية",
  "2040": "الخزف السعودي",
  "2050": "مجموعة صافولا",
  "2060": "التصنيع الوطنية",
  "2082": "أكوا باور",
  "2083": "مرافق",
  "2170": "اللجين",
  "2222": "أرامكو السعودية",
  "2223": "لوبريف",
  "2270": "سدافكو",
  "2280": "المراعي",
  "2290": "ينساب",
  "2310": "سبكيم العالمية",
  "2330": "المتقدمة",
  "2350": "كيان السعودية",
  "2380": "بترورابغ",
  "2381": "الحفر العربية",
  "2382": "أديس القابضة",
  "3010": "أسمنت العربية",
  "3020": "أسمنت اليمامة",
  "3030": "أسمنت السعودية",
  "3050": "أسمنت الجنوب",
  "4001": "أسواق العثيم",
  "4002": "المواساة",
  "4003": "إكسترا",
  "4004": "دله الصحية",
  "4005": "رعاية",
  "4009": "المستشفى السعودي الألماني",
  "4013": "سليمان الحبيب",
  "4030": "البحري",
  "4031": "الخدمات الأرضية",
  "4090": "طيبة للاستثمار",
  "4100": "مكة للإنشاء",
  "4190": "جرير",
  "4200": "الدريس",
  "4220": "إعمار المدينة الاقتصادية",
  "4250": "جبل عمر",
  "4260": "بدجت السعودية",
  "4261": "ذيب لتأجير السيارات",
  "4300": "دار الأركان",
  "4321": "المراكز العربية",
  "5110": "كهرباء السعودية",
  "7010": "إس تي سي",
  "7020": "موبايلي",
  "7030": "زين السعودية",
  "7200": "أم آي إس",
  "7202": "سلوشنز",
  "7203": "علم",
  "8010": "التعاونية",
  "8210": "بوبا العربية",
};

const SAUDI_SYMBOL_PATTERN = /^\d{4}(\.(SR|SA|TADAWUL))?$/i;

/** Returns true when a ticker matches Tadawul's 4-digit format or known TASI symbols. */
export function isSaudiSymbol(symbol: string): boolean {
  const clean = String(symbol || "").trim().toUpperCase();
  if (!clean) return false;
  if (SAUDI_SYMBOL_PATTERN.test(clean)) return true;
  const base = clean.split(".")[0];
  return Object.prototype.hasOwnProperty.call(SAUDI_STOCK_NAMES_AR, base);
}
