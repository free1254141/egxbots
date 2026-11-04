/**
 * Utility functions for ARTORO Voice Call, Voice Notes, and Speech Synthesis.
 */

/**
 * Single source of truth for the voice-note TTS profile.
 *
 * The API route pre-warms audio with these exact values and the browser
 * requests with the same values, so the backend cache is always hit.
 * Changing one side without the other turns every voice note into a cold,
 * duplicated synthesis.
 */
export const VOICE_NOTE_TTS = {
    voice: "ar-EG-ShakirNeural",
    rate: "+10%",
    pitch: "+0Hz",
} as const;

/**
 * Robust Speech-to-Text cleaner for Arabic mobile browsers (Web Speech API).
 * 1. Deduplicates stuttered syllables within words (e.g. "حلحلحل" -> "حلل", "هلهلهل" -> "هل", "هتعصبهتعصب" -> "هتعصب").
 * 2. Corrects common phonetic Egyptian dialect misrecognitions (e.g. "لسام" -> "لسهم", "فوى" -> "فوري").
 * 3. Splits glued question words (e.g. "الساعههل" -> "الساعه هل").
 * 4. Deduplicates repeated consecutive words and repeated phrases (e.g. "هل الساعه هل الساعه" -> "هل الساعه").
 */
export function cleanVoiceTranscript(rawText: string): string {
    if (!rawText) return "";
    let text = rawText.trim();

    // 1. Phonetic Arabic financial corrections
    const phoneticFixes: Array<[RegExp, string]> = [
        [/(?<![\u0600-\u06FF])لسام(?![\u0600-\u06FF])/g, "لسهم"],
        [/(?<![\u0600-\u06FF])لسهام(?![\u0600-\u06FF])/g, "للأسهم"],
        [/(?<![\u0600-\u06FF])سهمسهم(?![\u0600-\u06FF])/g, "سهم"],
        [/(?<![\u0600-\u06FF])حللحلل(?![\u0600-\u06FF])/g, "حلل"],
        [/(?<![\u0600-\u06FF])حلحلحل(?![\u0600-\u06FF])/g, "حلل"],
        [/(?<![\u0600-\u06FF])فوى(?![\u0600-\u06FF])/g, "فوري"],
        [/(?<![\u0600-\u06FF])فوري\s+فوري(?![\u0600-\u06FF])/g, "فوري"],
        [/(?<![\u0600-\u06FF])تجاري\s+تجاري(?![\u0600-\u06FF])/g, "تجاري"],
    ];
    for (const [pattern, replacement] of phoneticFixes) {
        text = text.replace(pattern, replacement);
    }

    // 2. Syllable stutter deduplication within Arabic words
    const words = text.split(/\s+/);
    const cleanedWords: string[] = [];

    for (const w of words) {
        let token = w;
        if (/^[\u0600-\u06FF]+$/.test(token)) {
            for (let chunkLen = 2; chunkLen <= 5; chunkLen++) {
                if (token.length >= chunkLen * 2) {
                    const chunk = token.slice(0, chunkLen);
                    const repeatedPattern = new RegExp(`^(${chunk})+$`);
                    if (repeatedPattern.test(token)) {
                        token = chunk === "حل" ? "حلل" : chunk;
                        break;
                    }
                }
            }
            if (token === "حل") token = "حلل";
        }
        cleanedWords.push(token);
    }
    text = cleanedWords.join(" ");

    // 3. Handle attached word-gluing like "الساعههل" -> "الساعه هل"
    for (const prefix of ["هل", "كام", "مين", "ايه", "إيه", "شو", "فين"]) {
        const re = new RegExp(`([^\\s]+)(${prefix}\\s)`, "g");
        text = text.replace(re, "$1 $2");
    }

    // 4. Remove consecutive duplicate words and multi-word phrases (Arabic-safe without \b)
    let deduped = text.split(/\s+/).filter(Boolean);

    // Deduplicate repeated phrases of length 4 down to 1
    for (let phraseLen = 4; phraseLen >= 1; phraseLen--) {
        for (let i = 0; i <= deduped.length - phraseLen * 2; i++) {
            const phrase1 = deduped.slice(i, i + phraseLen).join(" ");
            const phrase2 = deduped.slice(i + phraseLen, i + phraseLen * 2).join(" ");
            if (phrase1.length > 0 && phrase1 === phrase2) {
                deduped.splice(i + phraseLen, phraseLen);
                i--; // re-check at same index
            }
        }
    }

    return deduped.join(" ").trim();
}

/**
 * Intelligently extracts human conversational analysis and ARTORO's opinion on a stock
 * from a full financial analysis response.
 * Completely strips technical indicator acronyms (RSI, MACD, EMA), raw formula numbers,
 * markdown tables, English tickers in parentheses, and disclaimers.
 * Produces 2-3 natural spoken Egyptian Arabic sentences (~45-65 words) suitable for a phone call.
 */
export function extractVoiceAnalysisSpeech(replyText: string, userQuery: string = ""): string {
    if (!replyText) {
        return "تمام يا فندم، تم تحديث بيانات السهم والتحليل على شاشتك.";
    }

    const text = replyText;

    // 0. If the text is already a concise conversational prose response (no markdown tables, no indicator acronyms, no section headers)
    if (!text.includes("|") && !/\b(RSI|MACD|EMA|SMA)\b/i.test(text) && !/(?:الرأي الفني|الرأي التوليفي|ملخص تنفيذي)/i.test(text) && text.length < 900) {
        const cleanShort = cleanVoiceText(text, 250);
        if (cleanShort && cleanShort.length > 25 && !/(?:تنبيه:|ملاحظة:|إخلاء مسؤولية)/i.test(cleanShort)) {
            return cleanShort;
        }
    }

    // 1. Look for explicit synthesized opinion/verdict sections first
    const opinionPatterns = [
        // الرأي التوليفي وخطة التحرك
        /(?:###\s*)?(?:💡\s*)?(?:الرأي التوليفي وخطة التحرك|الرأي التوليفي|خطة التحرك|القرار التنفيذي|الرأي الفني وخلاصة أرتورو|الرأي الفني|خلاصة أرتورو|خلاصة التحليل|النظرة الفنية|التوصية الفنية|توصية أرتورو|رأي أرتورو)[:\s*]+([^\n]+(?:\n[^\n]+){0,3})/i,
        // ملخص تنفيذي
        /(?:###\s*)?(?:📊\s*)?(?:ملخص تنفيذي|الخلاصة التنفيذية)[:\s*]+([^\n]+(?:\n[^\n]+){0,3})/i,
        // القرار
        /(?:[0-9]\.\s*)?\*\*(?:القرار التنفيذي|القرار|التوصية)\*\*[:\s*]+([^\n]+)/i,
    ];

    let extractedOpinion = "";
    for (const pat of opinionPatterns) {
        const m = text.match(pat);
        if (m && m[1]) {
            const candidate = m[1].trim();
            if (!/(?:تنبيه:|ملاحظة:|إخلاء مسؤولية|شهادة إغلاق|حدود البيانات)/i.test(candidate)) {
                extractedOpinion = candidate;
                break;
            }
        }
    }

    // 2. Look for stock accumulation / smart money (strictly liquidity & accumulation, never portfolio lines)
    const accumMatch = text.match(/(?:حركة السيولة والتجميع|درجة التجميع|وضع السيولة|حالة السيولة|تدفق السيولة الذكية)[:\s*]+([^\n]+)/i);
    let accumText = accumMatch && accumMatch[1] ? accumMatch[1].trim() : "";
    if (accumText.includes("محفظتك") || accumText.includes("غير مسجل") || accumText.includes("مسجل لديك")) {
        accumText = "";
    }

    // 3. Extract structured stock parameters for a complete human synthesis if opinion needs context
    let stockName = "";
    const nameM = text.match(/تحليل سهم ([^\n\(\)]+)/i);
    if (nameM) {
        stockName = nameM[1].trim();
    }

    let price = "";
    const priceM = text.match(/(?:السعر الأخير|السعر الحالي|الإغلاق الحالي)[:\s*]+\*?\*?([0-9.,]+)\s*(?:ج\.م|جم|جنيه)?/i);
    if (priceM) {
        price = priceM[1].trim() + " جنيه";
    }

    let trendBadge = "";
    const badgeM = text.match(/التقييم الفني العام[:\s*]+\*?\*?([^\n\|]+)/i);
    if (badgeM) {
        trendBadge = badgeM[1].replace(/[*#]/g, "").trim();
        trendBadge = trendBadge.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "").trim();
        trendBadge = trendBadge.replace(/\(سكور.*?\)/g, "").trim();
    }

    let support = "";
    const supM = text.match(/الدعم الأول\s*\|\s*([0-9.,]+)/i) || text.match(/(?:الدعم الأول|أقرب دعم حاسم)[:\s*]+([0-9.,]+)/i);
    if (supM) {
        support = supM[1].trim() + " جنيه";
    }

    let resistance = "";
    const resM = text.match(/المقاومة الأولى\s*\|\s*([0-9.,]+)/i) || text.match(/المقاومة الأولى[:\s*]+([0-9.,]+)/i);
    if (resM) {
        resistance = resM[1].trim() + " جنيه";
    }

    let result = "";
    if (extractedOpinion && extractedOpinion.length > 25) {
        let cleanOp = extractedOpinion;
        // Clean list markers: "1. الاتجاه: ... 2. القرار: ..."
        cleanOp = cleanOp.replace(/[0-9]+\.\s*\*\*[^*]+\*\*[:\s]*/g, "، ");
        cleanOp = cleanOp.replace(/[*#_`~|]/g, "");
        if (accumText && !cleanOp.includes(accumText)) {
            result = `${accumText}. ${cleanOp}`;
        } else {
            result = cleanOp;
        }
    } else {
        // Synthesize structured human opinion
        const parts: string[] = [];
        if (stockName && price) {
            parts.push(`سهم ${stockName} يتداول حالياً عند ${price}`);
        }
        if (trendBadge) {
            parts.push(`والتقييم العام للسهم ${trendBadge}`);
        }
        if (support && resistance) {
            parts.push(`أهم مستوى دعم هو ${support} والمقاومة المستهدفة عند ${resistance}`);
        } else if (support) {
            parts.push(`وأهم مستوى دعم للمتابعة هو ${support}`);
        }
        if (parts.length > 0) {
            parts.push("القرار الفني هو المتابعة بحذر لحين وضوح السيولة والاتجاه.");
            result = parts.join("، ");
        } else {
            // For general market screens, tables, or stock lists
            result = cleanVoiceText(text, 350);
        }
    }

    // Clean technical jargon, tickers, emojis, and disclaimers
    result = result.replace(/\([A-Za-z0-9_.]+\)/g, ""); // remove (FWRY)
    result = result.replace(/\b(RSI|MACD|EMA|SMA|P\/E|EPS|ATR|Bollinger)\b/gi, "");
    result = result.replace(/[*#_`~|•–—▶️◀️⚡📈📉🎯🚨✅❌🔍⚖️💼📊💎👑🤖🔥📌💡⚠️🛑]/g, " ");
    result = result.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, " ");
    result = result.replace(/(?<=\d)\s*(?:ج\.م\.?|جم|EGP)(?=\s|[^\w]|$)/gi, " جنيه");
    result = result.replace(/\b(?:ج\.م\.?|جم|EGP)\b/gi, " جنيه");
    result = result.replace(/%/g, " في المية ");
    result = result.replace(/إشارة نموذج لا إثبات لشراء مؤسسات\.?/g, "");
    result = result.replace(/حالة السهم في محفظتك.*$/g, "");
    result = result.replace(/\s+/g, " ").trim();

    // Limit to ~1500 chars smoothly at sentence boundary
    if (result.length > 1500) {
        const cut = result.slice(0, 1500);
        const lastPunct = Math.max(cut.lastIndexOf("."), cut.lastIndexOf("،"), cut.lastIndexOf("!"), cut.lastIndexOf("؟"));
        if (lastPunct > 150) {
            result = cut.slice(0, lastPunct + 1);
        } else {
            const lastSpace = cut.lastIndexOf(" ");
            result = (lastSpace > 0 ? cut.slice(0, lastSpace) : cut) + ".";
        }
    }

    return cleanVoiceText(result, 1500);
}

// Comprehensive Egyptian Stock Exchange (EGX) Symbol to Arabic Company Name Dictionary
// Guarantees that the TTS audio engine NEVER speaks English tickers/letters, and always speaks Arabic names.
export const EGX_STOCK_TICKERS: Record<string, string> = {
    ABUK: "أبو قير للأسمدة",
    ACAMD: "العربية لاستصلاح الأراضي",
    ACGC: "العربية لحليج الأقطان",
    ADCI: "العربية للأدوية",
    ADIB: "أبوظبي الإسلامي",
    AFMC: "مطاحن الإسكندرية",
    AIFI: "الإسكندرية للاستثمارات المالية",
    AIH: "العروبة للسمسرة",
    AJWA: "أجواء للصناعات الغذائية",
    ALCN: "الإسكندرية لتداول الحاويات",
    ALEX: "الإسكندرية للغزل والنسيج",
    ALUM: "العربية للألومنيوم",
    AMER: "عامر جروب",
    AMES: "المركز الطبي الجديد",
    AMIA: "العربية للمحابس",
    AMOC: "أموك",
    ANFI: "الإسكندرية الوطنية للإلكترونيات",
    ARAB: "المطورون العرب",
    ARCC: "العربية للأسمنت",
    ARVA: "الإسكندرية للخدمات الطبية",
    ATCP: "العربية للتجارة والتوزيع",
    ATLC: "التوفيق للتأجير",
    ATQA: "مصر الوطنية للصلب",
    AUTO: "جي بي أوتو",
    AXPH: "الإسكندرية للأدوية",
    BINV: "بي انفستمنتس",
    BIOC: "بي بي أو كابيتال",
    BOLA: "بدر الدين للمقاولات",
    BRAQ: "البراق للاستثمارات",
    BTFH: "بلتون",
    CANA: "بنك قناة السويس",
    CCAP: "القلعة للاستشارات",
    CEFM: "مطاحن مصر الوسطى",
    CERA: "ريماس",
    CFGH: "كونكريت فاشون",
    CHSH: "القناة للتوكيلات الملاحية",
    CICH: "سي آي كابيتال",
    CIEB: "كريدي أجريكول",
    CLHO: "مستشفى كليوباترا",
    CMRI: "العامة للصوامع والتخزين",
    CNFN: "كونتكت المالية",
    COMI: "التجاري الدولي",
    COSG: "القاهرة للزيوت",
    CPCI: "القاهرة للأدوية",
    CPPC: "القاهرة للأدوية",
    CRST: "كريست مارك",
    CSAG: "القناة للتوكيلات الملاحية",
    DAPH: "مصر للأسمنت قنا",
    DEIN: "دايس للملابس",
    DOMT: "دومتي",
    DSCW: "دايس للملابس",
    EAST: "الشرقية للدخان",
    ECAP: "العز للسيراميك الجوهرة",
    ECAZ: "العز للسيراميك الجوهرة",
    EDFM: "مطاحن شرق الدلتا",
    EEII: "العربية للصناعات الهندسية",
    EFIC: "المالية والصناعية المصرية",
    EFID: "إيديتا للصناعات الغذائية",
    EFIH: "إي فاينانس",
    EGAL: "مصر للألومنيوم",
    EGAS: "غاز مصر",
    EGBE: "البنك المصري الخليجي",
    EGCH: "كيما للأسمدة",
    EHDR: "المصريين للإسكان",
    EKHO: "المصرية الكويتية القابضة",
    EKHOA: "المصرية الكويتية",
    ELEC: "الكابلات الكهربائية",
    ELKA: "القاهرة للإسكان",
    ELNA: "النصر للملابس كابو",
    ELSH: "الشمس للإسكان",
    ELWA: "الوادى للاستثمار السياحي",
    EMFD: "إعمار مصر للتنمية",
    EPPC: "الأهرام للطباعة",
    EPPK: "الأهرام للطباعة",
    ESRS: "حديد عز",
    ETEL: "المصرية للاتصالات",
    ETRS: "إيجيترانس",
    EXPA: "بنك تنمية الصادرات",
    FAIT: "بنك فيصل الإسلامي",
    FENG: "فيركيم مصر للأسمدة",
    FERC: "فيركيم مصر للأسمدة",
    FWRY: "فوري للمدفوعات الإلكترونية",
    GBCO: "جي بي كوربوريشن",
    GDWA: "جدوى للتنمية الصناعية",
    GEBE: "المصرية لتطوير صناعة البناء ليفت سلاب",
    GMCI: "العامة لمنتجات الخزف والصيني شيني",
    GOCO: "الخليجية الكندية للاستثمار",
    GTWL: "جولدن تكس للأصواف",
    HDBK: "بنك التعمير والإسكان",
    HELI: "مصر الجديدة للإسكان",
    HRHO: "إي إف جي القابضة هيرميس",
    IBMD: "ابن سينا فارما",
    IDHC: "التشخيص المتكاملة القابضة",
    IDRE: "رواد السياحة",
    IEEC: "المشروعات الصناعية والهندسية",
    IFAP: "الدولية للأسمدة والكيماويات",
    IIOC: "الدولية للتأجير التمويلي إينكوليس",
    INCO: "المؤشر للبرمجيات",
    IPMC: "المطاحن المصرية",
    IRAX: "العز الدخيلة للصلب",
    IRON: "الحديد والصلب المصرية",
    ISMA: "الإسماعيلية للدواجن",
    ISPH: "ابن سينا فارما",
    JUFO: "جهينة للصناعات الغذائية",
    KABO: "كابو للملابس",
    KABR: "كفر الزيات للمبيدات",
    KORA: "قرة للطاقة",
    KZPC: "كفر الزيات للمبيدات",
    LCSW: "ليسيكو مصر",
    MAAL: "مرسيليا المصرية الخليجية",
    MASR: "مدينة مصر للإسكان والتعمير",
    MBEG: "إم بي للهندسة",
    MBSC: "أسمنت بني سويف",
    MCQE: "أسمنت قنا",
    MEPA: "الشرق الأوسط لصناعة الزجاج",
    MFPC: "موبكو للأسمدة",
    MILS: "مطاحن شمال القاهرة",
    MIPH: "مينا فارم للأدوية",
    MNHD: "مدينة مصر للإسكان",
    MOIL: "الخدمات الملاحية والبترولية ماريديف",
    MPCI: "ممفيس للأدوية",
    MPCO: "المنصورة للدواجن",
    MRCO: "مرسى علم للتنمية السياحية",
    NCCW: "النصر للأعمال المدنية",
    NDRL: "ناشيونال دريلنج",
    NIPH: "النيل للأدوية",
    OBRI: "العبور للاستثمار العقاري",
    OCDI: "سوديك السادس من أكتوبر للتنمية",
    ODIN: "أودن للاستثمارات المالية",
    OFH: "أوراسكوم المالية القابضة",
    OIFI: "أوراسكوم للاستثمار القابضة",
    OLFI: "عبور لاند للصناعات الغذائية",
    ORAS: "أوراسكوم كونستراكشون",
    ORHD: "أوراسكوم للتنمية مصر",
    ORWE: "النساجون الشرقيون",
    PHAR: "إيبيكو للأدوية",
    PHDC: "بالم هيلز للتعمير",
    POUL: "القاهرة للدواجن",
    PRCL: "العامة لمنتجات الخزف والصيني",
    PRDC: "الرواد للسياحة",
    PRMH: "برايم القابضة للاستثمارات",
    QNBA: "بنك قطر الوطني الأهلي",
    QNBE: "بنك قطر الوطني",
    RACC: "راية لمراكز الاتصالات",
    RAKT: "العامة لصناعة الورق راكتا",
    RAYA: "راية القابضة للاستثمارات المالية",
    REAC: "العقارية للبنوك الوطنية للتنمية",
    RMDA: "العاشر من رمضان للأدوية راميدا",
    ROTO: "رواد مصر للاستثمار السياحي",
    RREI: "العربية للاستثمار العقاري",
    SAIB: "بنك الشركة المصرفية",
    SAUD: "بنك البركة مصر",
    SCEM: "أسمنت سيناء",
    SCFM: "مطاحن جنوب القاهرة",
    SEIG: "السعودية المصرية للاستثمار والتمويل",
    SIPC: "سبأ الدولية للأدوية",
    SKPC: "سيدي كرير للبتروكيماويات",
    SNFC: "الشرقية الوطنية للأمن الغذائي",
    SPIN: "سبينالكس للإسكندرية للغزل والنسيج",
    SPMD: "سبيد ميديكال",
    SUGR: "الدلتا للسكر",
    SVCE: "أسمنت جنوب الوادي",
    SWDY: "السويدي إليكتريك",
    TALM: "تعليم لخدمات الإدارة",
    TAQA: "طاقة عربية",
    TMGH: "مجموعة طلعت مصطفى",
    TRTO: "ترانس أوكاشنز",
    UBEE: "البنك المتحد",
    UEFM: "مطاحن مصر العليا",
    UNIP: "يونيباك للورق والكرتون",
    UNIT: "المتحدة للإسكان والتعمير",
    VALU: "فاليو",
    VERT: "فيرتيكا للبرمجيات",
    WCDF: "مطاحن وسط وغرب الدلتا",
    ZMID: "زهراء المعادي للاستثمار والتعمير",
};


/**
 * Cleans rich markdown chat replies into natural spoken Egyptian Arabic sentences.
 * Strips markdown tables, links, disclaimers, and technical syntax so audio synthesis speaks cleanly.
 * Guarantees ZERO English tickers or letters in speech audio: replaces tickers with Arabic company names.
 */
/**
 * Cleans rich markdown chat replies into natural spoken Egyptian Arabic sentences.
 * Omits raw tables and numbers, speaking natural human insights and stock names in Arabic only.
 * Guarantees ZERO English tickers or letters in speech audio: replaces tickers with Arabic company names.
 */
/**
 * Cleans rich markdown chat replies into natural spoken Egyptian Arabic sentences.
 * Omits raw tables and numbers, speaking natural human insights and stock names in Arabic only.
 * Guarantees ZERO English tickers or letters in speech audio: replaces tickers with Arabic company names.
 */
export const ARABIC_MONTH_NAMES: Record<string, string> = {
    "01": "يناير", "1": "يناير",
    "02": "فبراير", "2": "فبراير",
    "03": "مارس", "3": "مارس",
    "04": "أبريل", "4": "أبريل",
    "05": "مايو", "5": "مايو",
    "06": "يونيو", "6": "يونيو",
    "07": "يوليو", "7": "يوليو",
    "08": "أغسطس", "8": "أغسطس",
    "09": "سبتمبر", "9": "سبتمبر",
    "10": "أكتوبر",
    "11": "نوفمبر",
    "12": "ديسمبر",
};

/**
 * Cleans rich markdown chat replies into natural spoken Egyptian Arabic sentences.
 * Omits raw tables and numbers, speaking natural human insights and stock names in Arabic only.
 * Guarantees ZERO English tickers or letters in speech audio: replaces tickers with Arabic company names.
 * Converts numbers >= 1,000 million into billions (مليار جنيه) to prevent '6 آلاف مليون' anomalies.
 */
export function cleanVoiceText(rawText: string, maxChars: number = 600): string {
    if (!rawText || !rawText.trim()) return "";

    let text = rawText;

    // 1. Strip code blocks
    text = text.replace(/```[\s\S]*?```/g, "");

    // 2. Extract prominent stock names ONLY from markdown stock screener/ranking tables
    const tableLines = text.split(/\r?\n/).map(l => l.trim()).filter(l => l.startsWith("|") && l.endsWith("|"));
    const extractedStocks: string[] = [];
    const NON_STOCK_TERMS = new Set([
        "الإغلاق", "الإغلاق الحالي", "الدعم", "الدعم الأول", "الدعم الثاني",
        "المقاومة", "المقاومة الأولى", "المقاومة الثانية", "المؤشر", "المقياس",
        "المستوى / النقطة", "المستوى", "النقطة", "القيمة", "الوصف الفني",
        "سكور التقييم الشامل", "القيمة السوقية", "السعر العادل", "التوزيعات النقدية",
        "التوافق الشرعي", "ربحية السهم", "مضاعف الربحية", "الاتجاه", "القرار", "الحجم النسبي"
    ]);

    if (tableLines.length >= 3) {
        // Strictly check if header row actually represents a list of stocks
        const headerRow = tableLines[0];
        const isStockListTable = headerRow.includes("السهم") || headerRow.includes("الشركة") || headerRow.includes("الرمز") || headerRow.includes("الكود");

        if (isStockListTable) {
            for (const row of tableLines.slice(2)) {
                const cells = row.split("|").map(c => c.trim()).filter(Boolean);
                if (cells.length > 0) {
                    let stockCell = cells[0];
                    stockCell = stockCell.replace(/\([A-Za-z0-9\.\-]+\)/g, "").trim();
                    for (const [sym, ar] of Object.entries(EGX_STOCK_TICKERS)) {
                        if (new RegExp(`\\b${sym}\\b`, "i").test(cells[0])) {
                            stockCell = ar;
                            break;
                        }
                    }
                    stockCell = stockCell.replace(/[A-Za-z0-9\.\-]+/g, "").trim();
                    if (
                        stockCell &&
                        !NON_STOCK_TERMS.has(stockCell) &&
                        !extractedStocks.includes(stockCell) &&
                        stockCell.length > 2
                    ) {
                        extractedStocks.push(stockCell);
                    }
                    if (extractedStocks.length >= 4) break;
                }
            }
        }
    }

    // Replace markdown table blocks with a single smooth transitional sentence
    const tableReplacement = extractedStocks.length > 0
        ? `\nومن أبرز الأسهم في القائمة: ${extractedStocks.join("، و")}، والجدول التفصيلي كامل بجميع الأسعار معروض على شاشتك.\n`
        : (tableLines.length > 0 ? "\nوالجدول التفصيلي كامل بجميع الأسعار والنسب معروض على شاشتك.\n" : "");

    // Completely remove all markdown table blocks
    text = text.replace(/(?:^[ \t]*\|[^\n]+\|[ \t]*(?:\r?\n)?)+/gm, () => tableReplacement);
    text = text.replace(/\|[^\n]+\|/g, "");

    // 2b. Strip market breadth statistical preamble and dense stock count parentheticals
    // E.g. 'سياق السوق: 184 سهم صاعد مقابل 41 هابط... وإجمالي تداول 6,750 مليون جنيه'
    text = text.replace(/(?:سياق السوق|سياق الجلسة|حالة السوق|أداء المؤشر)[:\s*]+[^\n]+(?:\r?\n)?/g, "");
    text = text.replace(/\b\d+\s+سهم\s+صاعد\s+مقابل\s+\d+\s+هابط[^\n\.]*[\.\n]?/g, "");
    text = text.replace(/\(من\s+\d+\s+سهماً:[^)]+\)/g, "");

    // 3. Strip visual table headers/titles (e.g. جدول أسهم التجميع)
    text = text.replace(/جدول\s+(?:أسهم\s+التجميع|فحص\s+كامل|الأسهم|الفرز|المؤشرات|التحليل)(?:\s*\([^)]*\))?[:\s]*/g, "");

    // 4. Convert numeric dates like 03-11-2026 or 2026-11-03 into spoken Arabic months
    text = text.replace(/\b(\d{1,2})[-/](\d{1,2})[-/](202\d)\b/g, (_, d, m, y) => `${parseInt(d, 10)} ${ARABIC_MONTH_NAMES[m] || m} ${y}`);
    text = text.replace(/\b(202\d)[-/](\d{1,2})[-/](\d{1,2})\b/g, (_, y, m, d) => `${parseInt(d, 10)} ${ARABIC_MONTH_NAMES[m] || m} ${y}`);

    // 5. Naturalize large financial numbers: convert >= 1,000 million to billions (مليار جنيه)
    // E.g. "6,750.79 مليون جنيه" -> "6.75 مليار جنيه"
    text = text.replace(/(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?)\s*مليون(?:\s*جنيه)?/g, (match, rawNum) => {
        const cleanVal = parseFloat(rawNum.replace(/,/g, ""));
        const hasCurrency = match.includes("جنيه");
        if (!isNaN(cleanVal) && cleanVal >= 1000) {
            const billions = (cleanVal / 1000.0).toFixed(2).replace(/\.?0+$/, "");
            return hasCurrency ? `${billions} مليار جنيه` : `${billions} مليار`;
        }
        return match;
    });

    // 6. Convert numerical ratios like 4.49:1 or 4.49 : 1 to "4.5 إلى 1"
    text = text.replace(/(\d+(?:\.\d+)?)\s*:\s*(\d+)/g, (_, r1, r2) => {
        const parsed = parseFloat(r1);
        const r1Str = !isNaN(parsed) ? parsed.toFixed(1).replace(/\.?0+$/, "") : r1;
        return `${r1Str} إلى ${r2}`;
    });

    // 7. Strip trailing boilerplate disclaimers
    text = text.replace(/تحليل EGX Bots مبني على أحدث البيانات[\s\S]*$/gi, "");
    text = text.replace(/تحليل مبني على أحدث البيانات المتاحة[\s\S]*$/gi, "");
    text = text.replace(/منصة EGX Bots لتحليل الأسهم المصرية[\s\S]*$/gi, "");
    text = text.replace(/(?:إخلاء مسؤولية|تنبيه):\s*هذا التحليل لأغراض تعليمية[\s\S]*$/gi, "");
    text = text.replace(/منصة EGX BOTS ليست وسيطاً[\s\S]*$/gi, "");
    text = text.replace(/هذا التحليل لأغراض العمل الفني والتعليم فقط[\s\S]*$/gi, "");

    // 8. Remove markdown links [text](url) -> text
    text = text.replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1");

    // 9. Remove markdown bold, italic, code, headers
    text = text.replace(/#{1,6}\s*/g, "");
    text = text.replace(/[*`_~]/g, "");

    // 10. Strip parenthesized English tickers like (ABUK), ( TMGH ), (COMI.CA)
    text = text.replace(/[\(\[\{]\s*[A-Za-z0-9\.\-]{2,10}\s*[\)\]\}]/g, "");

    // 11. Remove emojis and decorative icons
    text = text.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "");
    text = text.replace(/[•–—▶️◀️⚡📈📉🎯🚨✅❌🔍⚖️💼📊💎👑🤖🔥📌💡⚠️🛑~_\^]/g, "");

    // 12. Clean prefixes before English words (e.g. والـ P/E -> مضاعف الربحية)
    text = text.replace(/(?:والـ|الـ)\s*(?=[A-Za-z])/g, " ");

    // 13. Natural spoken currency, indices, and stock terms into clear Arabic
    text = text.replace(/(?<=\d)\s*(?:ج\.م\.?|جم|EGP)(?=\s|[^\w]|$)/gi, " جنيه");
    text = text.replace(/\b(?:ج\.م\.?|جم|EGP)\b/gi, " جنيه");
    text = text.replace(/%/g, " في المية ");
    text = text.replace(/\bEGX30\b/gi, " إيجي إكس 30 ");
    text = text.replace(/\bEGX70\b/gi, " إيجي إكس 70 ");
    text = text.replace(/\bEGX100\b/gi, " إيجي إكس 100 ");
    text = text.replace(/\bEGX\b/gi, " البورصة المصرية ");
    text = text.replace(/\bUSD\b/gi, " دولار ");
    text = text.replace(/(?:مؤشر\s*)?\bRSI\b/gi, " مؤشر القوة النسبية ");
    text = text.replace(/(?:مؤشر\s*)?\bMACD\b/gi, " مؤشر الماكد ");
    text = text.replace(/(?:متوسط\s*)?\bEMA\b/gi, " المتوسط المتحرك ");
    text = text.replace(/(?:متوسط\s*)?\bSMA\b/gi, " المتوسط المتحرك ");
    text = text.replace(/\bP\/E\b/gi, " مضاعف الربحية ");
    text = text.replace(/\bP\/B\b/gi, " القيمة الدفترية ");
    text = text.replace(/\bEPS\b/gi, " ربحية السهم ");
    text = text.replace(/(?:وقف الخسارة\s*)?\bSL\b/gi, " وقف الخسارة ");
    text = text.replace(/(?:جني الأرباح\s*|الهدف\s*)?\bTP\b/gi, " المستهدف ");
    text = text.replace(/\bBUY\b/gi, " شراء ");
    text = text.replace(/\bSELL\b/gi, " بيع ");
    text = text.replace(/\bHOLD\b/gi, " احتفاظ ");

    // 14. Replace standalone stock tickers with full Arabic company names
    for (const [sym, arName] of Object.entries(EGX_STOCK_TICKERS)) {
        const re = new RegExp(`\\b${sym}(?:\\.CA)?\\b`, "gi");
        text = text.replace(re, ` ${arName} `);
    }

    // 15. Clean any remaining English characters/words so the voice engine NEVER pronounces English
    text = text.replace(/[A-Za-z]+(?:\.[A-Za-z]+)?/g, "");

    // 16. Remove dense parenthesized number lists like (88.16 و 87.38)
    text = text.replace(/\([0-9.,\sو\+\-%]+\)/g, "");

    // 17. Normalize whitespace and clean punctuation
    text = text.replace(/\s+/g, " ").trim();
    text = text.replace(/([،\.!\؟])\s*\1+/g, "$1");

    // 18. Truncate smoothly at sentence boundary if exceeding maxChars
    if (text.length > maxChars) {
        const cut = text.slice(0, maxChars);
        const lastPunct = Math.max(
            cut.lastIndexOf("."),
            cut.lastIndexOf("،"),
            cut.lastIndexOf("!"),
            cut.lastIndexOf("؟"),
            cut.lastIndexOf("\n")
        );
        if (lastPunct > 50) {
            text = cut.slice(0, lastPunct + 1);
        } else {
            const lastSpace = cut.lastIndexOf(" ");
            text = (lastSpace > 0 ? cut.slice(0, lastSpace) : cut) + "...";
        }
    }

    return text.trim();
}


/**
 * Plays a soft dual-tone synthesizer chime via Web Audio API to indicate connection
 * and pre-unlock browser AudioContext on user interaction.
 */
export function playConnectionChime(): void {
    if (typeof window === "undefined") return;
    try {
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        if (ctx.state === "suspended") {
            ctx.resume();
        }

        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = "sine";
        osc.frequency.setValueAtTime(520, now); // C5
        osc.frequency.exponentialRampToValueAtTime(784, now + 0.12); // G5

        gain.gain.setValueAtTime(0.001, now);
        gain.gain.linearRampToValueAtTime(0.15, now + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(now);
        osc.stop(now + 0.26);
    } catch (e) {
        // Non-blocking fallback
    }
}
