/**
 * Canonical Egyptian Stock Names Map (EGX)
 * Maps ticker symbols to verified official Arabic and English company names.
 * Prevents LLM hallucinations, name mix-ups (e.g. TALM vs TMGH, CEFM vs CCAP, MBEG vs EGBE),
 * and missing names when database records have null name_ar.
 */

export interface CanonicalStockInfo {
    name_ar: string;
    name_en: string;
    sector?: string;
}

export const CANONICAL_STOCK_NAMES: Record<string, CanonicalStockInfo> = {
    // ── Most Active & Commonly Traded EGX Stocks ─────────────────────────────
    TMGH: { name_ar: "مجموعة طلعت مصطفى القابضة", name_en: "Talaat Moustafa Group Holding", sector: "عقارات" },
    TALM: { name_ar: "تعليم لخدمات الإدارة", name_en: "Taaleem Management Services", sector: "خدمات تعليمية" },
    COMI: { name_ar: "البنك التجاري الدولي - مصر", name_en: "Commercial International Bank", sector: "بنوك" },
    FWRY: { name_ar: "فوري لتكنولوجيا البنوك والمدفوعات الإلكترونية", name_en: "Fawry for Banking Technology", sector: "تكنولوجيا مالية" },
    SWDY: { name_ar: "السويدي إليكتريك", name_en: "Elsewedy Electric", sector: "صناعي وهندسي" },
    ETEL: { name_ar: "المصرية للاتصالات - وي", name_en: "Telecom Egypt", sector: "اتصالات" },
    ABUK: { name_ar: "أبو قير للأسمدة والصناعات الكيماوية", name_en: "Abu Qir Fertilizers", sector: "كيماويات وأسمدة" },
    MFPC: { name_ar: "مصر لإنتاج الأسمدة - موبكو", name_en: "Misr Fertilizers Production Co. - MOPCO", sector: "كيماويات وأسمدة" },
    SKPC: { name_ar: "سيدي كرير للبتروكيماويات", name_en: "Sidi Kerir Petrochemicals", sector: "كيماويات وبتروكيماويات" },
    AMOC: { name_ar: "الإسكندرية للزيوت المعدنية - أموك", name_en: "Alexandria Mineral Oils Co.", sector: "طاقة وبترول" },
    EKHO: { name_ar: "القابضة المصرية الكويتية", name_en: "Egypt Kuwait Holding", sector: "استثمار وخدمات مالية" },
    BTFH: { name_ar: "بلتون المالية القابضة", name_en: "Beltone Holding", sector: "خدمات مالية غير مصرفية" },
    HRHO: { name_ar: "المجموعة المالية هيرميس القابضة", name_en: "EFG Holding", sector: "خدمات مالية غير مصرفية" },
    CICH: { name_ar: "سي آي كابيتال القابضة", name_en: "CI Capital Holding", sector: "خدمات مالية غير مصرفية" },
    EFIH: { name_ar: "إي فاينانس للاستثمارات المالية والرقمية", name_en: "eFinance Investment Group", sector: "تكنولوجيا مالية" },
    ISPH: { name_ar: "ابن سينا فارما", name_en: "Ibnsina Pharma", sector: "رعاية صحية وأدوية" },
    PHAR: { name_ar: "المصرية الدولية للصناعات الدوائية - إيبيكو", name_en: "EIPICO", sector: "رعاية صحية وأدوية" },
    MPCI: { name_ar: "ممفيس للأدوية والصناعات الكيماوية", name_en: "Memphis Pharmaceutical & Chemical", sector: "رعاية صحية وأدوية" },
    NIPH: { name_ar: "النيل للأدوية والصناعات الكيماوية", name_en: "Nile Pharmaceuticals", sector: "رعاية صحية وأدوية" },
    AXPH: { name_ar: "الإسكندرية للأدوية والصناعات الكيماوية", name_en: "Alexandria Pharmaceuticals", sector: "رعاية صحية وأدوية" },
    CPCI: { name_ar: "القاهرة للأدوية والصناعات الكيماوية", name_en: "Cairo Pharmaceuticals", sector: "رعاية صحية وأدوية" },
    AMES: { name_ar: "المركز الطبي الجديد بالإسكندرية", name_en: "Alexandria New Medical Center Co.", sector: "رعاية صحية وأدوية" },
    CLHO: { name_ar: "مستشفى كليوباترا", name_en: "Cleopatra Hospital", sector: "رعاية صحية وأدوية" },
    SIPC: { name_ar: "سبأ الدولية للأدوية والصناعات الكيماوية", name_en: "Sabaa International Pharmaceutical", sector: "رعاية صحية وأدوية" },
    SPMD: { name_ar: "سبيد ميديكال", name_en: "Speed Medical", sector: "رعاية صحية وأدوية" },
    RMDA: { name_ar: "العاشر من رمضان للصناعات الدوائية - راميدا", name_en: "Rameda Pharmaceuticals", sector: "رعاية صحية وأدوية" },
    ADCI: { name_ar: "العربية للأدوية والصناعات الكيماوية", name_en: "Arab Pharmaceuticals", sector: "رعاية صحية وأدوية" },

    // ── Mills & Bakeries (مطاحن ومخابز) ───────────────────────────────────────
    CEFM: { name_ar: "مطاحن مصر الوسطى", name_en: "Middle Egypt Flour Mills", sector: "أغذية ومطاحن" },
    EDFM: { name_ar: "مطاحن شرق الدلتا", name_en: "East Delta Flour Mills Co.", sector: "أغذية ومطاحن" },
    SCFM: { name_ar: "مطاحن ومخابز جنوب القاهرة والجيزة", name_en: "South Cairo & Giza Mills", sector: "أغذية ومطاحن" },
    MILS: { name_ar: "مطاحن ومخابز شمال القاهرة", name_en: "North Cairo Mills Co.", sector: "أغذية ومطاحن" },
    AFMC: { name_ar: "مطاحن ومخابز الإسكندرية", name_en: "Alexandria Flour Mills Co.", sector: "أغذية ومطاحن" },
    WCDF: { name_ar: "مطاحن ومخابز وسط وغرب الدلتا", name_en: "Middle & West Delta Flour Mills", sector: "أغذية ومطاحن" },
    UEFM: { name_ar: "مطاحن مصر العليا", name_en: "Upper Egypt Flour Mills", sector: "أغذية ومطاحن" },

    // ── Food & Beverages ─────────────────────────────────────────────────────
    JUFO: { name_ar: "جهينة للصناعات الغذائية", name_en: "Juhayna Food Industries", sector: "أغذية ومشروبات" },
    DOMT: { name_ar: "الصناعات الغذائية العربية - دومتي", name_en: "Arabian Food Industries - Domty", sector: "أغذية ومشروبات" },
    EFID: { name_ar: "إيديتا للصناعات الغذائية", name_en: "Edita Food Industries", sector: "أغذية ومشروبات" },
    OLFI: { name_ar: "عبور لاند للصناعات الغذائية", name_en: "Obour Land for Food Industries", sector: "أغذية ومشروبات" },
    POUL: { name_ar: "القاهرة للدواجن", name_en: "Cairo Poultry", sector: "أغذية ودواجن" },
    ISMA: { name_ar: "الإسماعيلية مصر للدواجن", name_en: "Ismailia Misr Poultry", sector: "أغذية ودواجن" },
    MPCO: { name_ar: "المنصورة للدواجن", name_en: "Mansoura Poultry", sector: "أغذية ودواجن" },
    SUGR: { name_ar: "الدلتا للسكر", name_en: "Delta Sugar", sector: "أغذية ومشروبات" },
    EAST: { name_ar: "الشرقية - إيسترن كومباني", name_en: "Eastern Co.", sector: "سلع استهلاكية" },

    // ── Real Estate & Construction ───────────────────────────────────────────
    HELI: { name_ar: "مصر الجديدة للإسكان والتعمير", name_en: "Heliopolis Housing", sector: "عقارات" },
    PHDC: { name_ar: "بالم هيلز للتعمير", name_en: "Palm Hills Developments", sector: "عقارات" },
    MASR: { name_ar: "مدينة مصر للإسكان والتعمير", name_en: "Madinet Masr for Housing & Development", sector: "عقارات" },
    MNHD: { name_ar: "مدينة مصر للإسكان والتعمير", name_en: "Madinet Masr Housing (MNHD)", sector: "عقارات" },
    OCDI: { name_ar: "السادس من أكتوبر للتنمية والاستثمار - سوديك", name_en: "SODIC", sector: "عقارات" },
    EMFD: { name_ar: "إعمار مصر للتنمية", name_en: "Emaar Misr for Development", sector: "عقارات" },
    ELSH: { name_ar: "الشمس للإسكان والتعمير", name_en: "El Shams Housing & Urbanization", sector: "عقارات" },
    ELKA: { name_ar: "القاهرة للإسكان والتعمير", name_en: "Cairo Housing and Development", sector: "عقارات" },
    UNIT: { name_ar: "المتحدة للإسكان والتعمير", name_en: "United Housing & Development", sector: "عقارات" },
    ZMID: { name_ar: "زهراء المعادي للاستثمار والتعمير", name_en: "Zahraa Maadi Investment & Development", sector: "عقارات" },
    ORHD: { name_ar: "أوراسكوم للتنمية مصر", name_en: "Orascom Development Egypt", sector: "عقارات وسياحة" },
    ORAS: { name_ar: "أوراسكوم كونستراكشون بي إل سي", name_en: "Orascom Construction PLC", sector: "مقاولات وتشييد" },
    CRST: { name_ar: "كريست مارك للمقاولات والتطوير العقاري", name_en: "Crest Mark for Contracting & Real Estate", sector: "خدمات واستثمار" },
    RREI: { name_ar: "العربية للاستثمار العقاري", name_en: "Arab Real Estate Investment Co.", sector: "عقارات" },
    MAAL: { name_ar: "مرسيليا المصرية الخليجية للاستثمار العقاري", name_en: "Marseilla Al Masreia Al Khalegeya", sector: "عقارات وسياحة" },
    OBRI: { name_ar: "العبور للاستثمار العقاري", name_en: "El Obour Real Estate Investment", sector: "عقارات" },
    NCCW: { name_ar: "النصر للأعمال المدنية", name_en: "Al Nasr for Civil Works", sector: "مقاولات وتشييد" },

    // ── Cement & Building Materials ──────────────────────────────────────────
    MCQE: { name_ar: "مصر للأسمنت - قنا", name_en: "Misr Cement Co. (Qena)", sector: "مواد بناء وأسمنت" },
    MBSC: { name_ar: "مصر بني سويف للأسمنت", name_en: "Misr Beni Suef Cement", sector: "مواد بناء وأسمنت" },
    ARCC: { name_ar: "العربية للأسمنت", name_en: "Arabian Cement Co.", sector: "مواد بناء وأسمنت" },
    SVCE: { name_ar: "أسمنت جنوب الوادي", name_en: "South Valley Cement", sector: "مواد بناء وأسمنت" },
    SCEM: { name_ar: "أسمنت سيناء", name_en: "Sinai Cement", sector: "مواد بناء وأسمنت" },
    LCSW: { name_ar: "ليسيكو مصر", name_en: "Lecico Egypt", sector: "مواد بناء وسيراميك" },
    ECAP: { name_ar: "العز للسيراميك والبورسلين - الجوهرة", name_en: "Al Ezz Ceramics & Porcelain - Gemma", sector: "مواد بناء وسيراميك" },
    CERA: { name_ar: "العربية للخزف - ريماس", name_en: "Arab Ceramic Co. - Remas", sector: "مواد بناء وسيراميك" },
    ESRS: { name_ar: "حديد عز", name_en: "Ezz Steel", sector: "مواد بناء وحديد" },
    IRAX: { name_ar: "العز الدخيلة للصلب - الإسكندرية", name_en: "Al Ezz Dekheila Steel - Alexandria", sector: "مواد بناء وحديد" },
    ATQA: { name_ar: "مصر الوطنية للصلب - عتاقة", name_en: "Misr National Steel - Ataqa", sector: "مواد بناء وحديد" },
    IRON: { name_ar: "الحديد والصلب المصرية", name_en: "Egyptian Iron & Steel", sector: "مواد بناء وحديد" },

    // ── Engineering, Industrial & Technology ──────────────────────────────────
    MBEG: { name_ar: "إم بي للهندسة", name_en: "MB for Engineering & Contracting", sector: "صناعي وهندسي" },
    IEEC: { name_ar: "المشروعات الصناعية والهندسية", name_en: "Industrial & Engineering Projects", sector: "صناعي وهندسي" },
    EEII: { name_ar: "العربية للصناعات الهندسية", name_en: "Arab Engineering Industries", sector: "صناعي وهندسي" },
    EGAL: { name_ar: "مصر للألومنيوم", name_en: "Egypt Aluminum", sector: "تعدين وصناعات معدنية" },
    ALUM: { name_ar: "العربية للألومنيوم", name_en: "Arab Aluminum", sector: "صناعي وهندسي" },
    KORA: { name_ar: "قرة لمشروعات الطاقة والاستثمار", name_en: "Kora Energy Projects & Investment", sector: "طاقة وخدمات هندسية" },
    TAQA: { name_ar: "طاقة عربية", name_en: "TAQA Arabia", sector: "طاقة ومرافق" },
    EGAS: { name_ar: "غاز مصر", name_en: "Egypt Gas", sector: "طاقة ومرافق" },
    ELEC: { name_ar: "الكابلات الكهربائية المصرية", name_en: "Electro Cable Egypt", sector: "صناعي وهندسي" },
    RAYA: { name_ar: "راية القابضة للاستثمارات المالية", name_en: "Raya Holding for Financial Investments", sector: "تكنولوجيا واتصالات" },
    RACC: { name_ar: "راية لمراكز الاتصالات", name_en: "Raya Contact Center", sector: "تكنولوجيا واتصالات" },
    GBCO: { name_ar: "جي بي كوربوريشن", name_en: "GB Corp", sector: "سيارات وتجارة" },
    AUTO: { name_ar: "جي بي أوتو", name_en: "GB Auto", sector: "سيارات وتجارة" },
    ETRS: { name_ar: "المصرية لخدمات النقل - إيجيترانس", name_en: "Egytrans", sector: "نقل ولوجستيات" },
    ALCN: { name_ar: "الإسكندرية لتداول الحاويات والبضائع", name_en: "Alexandria Container and Cargo Handling", sector: "نقل ولوجستيات" },

    // ── Financial Services & Banks ───────────────────────────────────────────
    EGBE: { name_ar: "البنك المصري الخليجي", name_en: "Egyptian Gulf Bank", sector: "بنوك" },
    ADIB: { name_ar: "مصرف أبوظبي الإسلامي - مصر", name_en: "Abu Dhabi Islamic Bank - Egypt", sector: "بنوك" },
    CIEB: { name_ar: "بنك كريدي أجريكول - مصر", name_en: "Credit Agricole Egypt", sector: "بنوك" },
    QNBE: { name_ar: "بنك قطر الوطني الأهلي - QNB", name_en: "Qatar National Bank Alahli", sector: "بنوك" },
    QNBA: { name_ar: "بنك قطر الوطني الأهلي - QNB", name_en: "Qatar National Bank Alahli", sector: "بنوك" },
    FAIT: { name_ar: "بنك فيصل الإسلامي المصري", name_en: "Faisal Islamic Bank of Egypt", sector: "بنوك" },
    SAUD: { name_ar: "بنك البركة مصر", name_en: "Al Baraka Bank Egypt", sector: "بنوك" },
    EXPA: { name_ar: "بنك تنمية الصادرات - EBank", name_en: "Export Development Bank of Egypt", sector: "بنوك" },
    HDBK: { name_ar: "بنك التعمير والإسكان", name_en: "Housing & Development Bank", sector: "بنوك" },
    CANA: { name_ar: "بنك قناة السويس", name_en: "Suez Canal Bank", sector: "بنوك" },
    UBEE: { name_ar: "البنك المتحد", name_en: "The United Bank", sector: "بنوك" },
    SEIG: { name_ar: "السعودية المصرية للاستثمار والتمويل", name_en: "Saudi Egyptian Investment & Finance", sector: "استثمار وخدمات مالية" },
    ODIN: { name_ar: "أودن للاستثمارات المالية", name_en: "ODIN Investments", sector: "استثمار وخدمات مالية" },
    CCAP: { name_ar: "القلعة للاستشارات المالية", name_en: "Qalaa Holdings", sector: "استثمار وخدمات مالية" },
    CNFN: { name_ar: "كونتكت المالية القابضة", name_en: "Contact Financial Holding", sector: "خدمات مالية غير مصرفية" },
    VALU: { name_ar: "فاليو لتمويل المستهلكين", name_en: "valU", sector: "تكنولوجيا مالية" },
    ATLC: { name_ar: "التوفيق للتأجير التمويلي - أية تي ليز", name_en: "Al Tawfeek Leasing - A.T. Lease", sector: "خدمات مالية غير مصرفية" },
    PRMH: { name_ar: "برايم القابضة للاستثمارات المالية", name_en: "Prime Holding", sector: "خدمات مالية غير مصرفية" },

    // ── Textiles & Apparel ───────────────────────────────────────────────────
    GTWL: { name_ar: "جولدن تكس للأصواف", name_en: "Golden Textiles & Clothes Wool", sector: "غزل ونسيج" },
    ACGC: { name_ar: "العربية لحليج الأقطان", name_en: "Arab Cotton Ginning", sector: "غزل ونسيج" },
    DEIN: { name_ar: "دايس للملابس الجاهزة", name_en: "Dice Sport & Casual Wear", sector: "ملابس ومنسوجات" },
    DSCW: { name_ar: "دايس للملابس الجاهزة", name_en: "Dice Sport & Casual Wear", sector: "ملابس ومنسوجات" },
    ORWE: { name_ar: "النساجون الشرقيون للسجاد", name_en: "Oriental Weavers", sector: "غزل ونسيج ومنسوجات" },
    KABO: { name_ar: "النصر للملابس والمنسوجات - كابو", name_en: "El Nasr Clothing & Textiles - KABO", sector: "غزل ونسيج" },
    SPIN: { name_ar: "الإسكندرية للغزل والنسيج - سبينالكس", name_en: "Alexandria Spinning & Weaving - SPINALEX", sector: "غزل ونسيج" },

    // ── Chemicals & Fertilizers ──────────────────────────────────────────────
    EGCH: { name_ar: "الصناعات الكيماوية المصرية - كيما", name_en: "Egyptian Chemical Industries - KIMA", sector: "كيماويات وأسمدة" },
    EFIC: { name_ar: "المالية والصناعية المصرية", name_en: "Egyptian Financial & Industrial Co.", sector: "كيماويات وأسمدة" },
    KZPC: { name_ar: "كفر الزيات للمبيدات والكيماويات", name_en: "Kafr El Zayat Pesticides & Chemicals", sector: "كيماويات وأسمدة" },
    FERC: { name_ar: "فيركيم مصر للأسمدة والكيماويات", name_en: "Ferchem Misr for Fertilizers & Chemicals", sector: "كيماويات وأسمدة" },
};

/**
 * Returns canonical Arabic and English names for any given symbol.
 * Falls back to clean ticker code if entirely unknown.
 */
export function getCanonicalStockName(symbol: string): CanonicalStockInfo {
    const cleanSym = String(symbol || "").toUpperCase().trim();
    if (CANONICAL_STOCK_NAMES[cleanSym]) {
        return CANONICAL_STOCK_NAMES[cleanSym];
    }
    return {
        name_ar: cleanSym,
        name_en: cleanSym,
        sector: "سوق الأسهم المصرية",
    };
}
