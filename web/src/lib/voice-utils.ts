/**
 * Utility functions for ARTORO Voice Call, Voice Notes, and Speech Synthesis.
 */

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
        parts.push("القرار الفني هو المتابعة بحذر لحين وضوح السيولة والاتجاه.");
        result = parts.join("، ");
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
    TMGH: "طلعت مصطفى",
    COMI: "التجاري الدولي",
    FWRY: "فوري",
    SWDY: "السويدي إليكتريك",
    ETEL: "المصرية للاتصالات",
    MFPC: "موبكو",
    SKPC: "سيدي كرير",
    AMOC: "أموك",
    EKHO: "المصرية الكويتية",
    BTFH: "بلتون",
    HRHO: "هيرميس",
    CICH: "سي آي كابيتال",
    EFIH: "إي فاينانس",
    ISPH: "ابن سينا فارما",
    PHAR: "إيبيكو",
    ESRS: "حديد عز",
    HELI: "مصر الجديدة للإسكان",
    PHDC: "بالم هيلز",
    MASR: "مدينة مصر للإسكان",
    MNHD: "مدينة مصر للإسكان",
    OCDI: "سوديك",
    EMFD: "إعمار مصر",
    ORHD: "أوراسكوم للتنمية",
    ORAS: "أوراسكوم كونستراكشون",
    EGAL: "مصر للألومنيوم",
    TAQA: "طاقة عربية",
    EGAS: "غاز مصر",
    AUTO: "جي بي أوتو",
    GBCO: "جي بي كوربوريشن",
    ADIB: "أبوظبي الإسلامي",
    CIEB: "كريدي أجريكول",
    QNBE: "بنك قطر الوطني",
    QNBA: "بنك قطر الوطني",
    FAIT: "فيصل الإسلامي",
    HDBK: "بنك التعمير والإسكان",
    CCAP: "القلعة",
    VALU: "فاليو",
    ORWE: "النساجون الشرقيون",
    EGCH: "كيما",
    EFIC: "المالية والصناعية",
    KZPC: "كفر الزيات للمبيدات",
    FERC: "فيركيم مصر",
    JUFO: "جهينة",
    DOMT: "دومتي",
    EFID: "إيديتا",
    OLFI: "عبور لاند",
    POUL: "القاهرة للدواجن",
    ISMA: "الإسماعيلية للدواجن",
    MPCO: "المنصورة للدواجن",
    SUGR: "الدلتا للسكر",
    EAST: "إيسترن كومباني",
    MCQE: "أسمنت قنا",
    MBSC: "أسمنت بني سويف",
    ARCC: "العربية للأسمنت",
    SVCE: "أسمنت جنوب الوادي",
    SCEM: "أسمنت سيناء",
    LCSW: "ليسيكو مصر",
    ECAP: "العز للسيراميك",
    CERA: "ريماس",
    IRAX: "العز الدخيلة للصلب",
    ATQA: "مصر الوطنية للصلب",
    IRON: "الحديد والصلب",
    MBEG: "إم بي للهندسة",
    IEEC: "المشروعات الصناعية والهندسية",
    EEII: "العربية للصناعات الهندسية",
    ALUM: "العربية للألومنيوم",
    KORA: "قرة للطاقة",
    ELEC: "الكابلات الكهربائية",
    RAYA: "راية القابضة",
    RACC: "راية لمراكز الاتصالات",
    ETRS: "إيجيترانس",
    ALCN: "الإسكندرية لتداول الحاويات",
    EGBE: "البنك المصري الخليجي",
    SAUD: "بنك البركة",
    EXPA: "بنك تنمية الصادرات",
    CANA: "بنك قناة السويس",
    UBEE: "البنك المتحد",
    SEIG: "السعودية المصرية للاستثمار",
    ODIN: "أودن للاستثمارات",
    CNFN: "كونتكت المالية",
    ATLC: "التوفيق للتأجير",
    PRMH: "برايم القابضة",
    GTWL: "جولدن تكس",
    ACGC: "العربية لحليج الأقطان",
    DEIN: "دايس للملابس",
    DSCW: "دايس للملابس",
    KABO: "كابو",
    SPIN: "سبينالكس",
    TALM: "تعليم لخدمات الإدارة",
    CEFM: "مطاحن مصر الوسطى",
    EDFM: "مطاحن شرق الدلتا",
    SCFM: "مطاحن جنوب القاهرة",
    MILS: "مطاحن شمال القاهرة",
    AFMC: "مطاحن الإسكندرية",
    WCDF: "مطاحن وسط وغرب الدلتا",
    UEFM: "مطاحن مصر العليا",
    MPCI: "ممفيس للأدوية",
    NIPH: "النيل للأدوية",
    AXPH: "الإسكندرية للأدوية",
    CPCI: "القاهرة للأدوية",
    AMES: "المركز الطبي الجديد",
    CLHO: "مستشفى كليوباترا",
    SIPC: "سبأ الدولية للأدوية",
    SPMD: "سبيد ميديكال",
    RMDA: "راميدا للأدوية",
    ADCI: "العربية للأدوية",
    ELSH: "الشمس للإسكان",
    ELKA: "القاهرة للإسكان",
    UNIT: "المتحدة للإسكان",
    ZMID: "زهراء المعادي",
    CRST: "كريست مارك",
    RREI: "العربية للاستثمار العقاري",
    MAAL: "مرسيليا المصرية الخليجية",
    OBRI: "العبور للاستثمار العقاري",
    NCCW: "النصر للأعمال المدنية",
};

/**
 * Cleans rich markdown chat replies into natural spoken Egyptian Arabic sentences.
 * Strips markdown tables, links, disclaimers, and technical syntax so audio synthesis speaks cleanly.
 * Guarantees ZERO English tickers or letters in speech audio: replaces tickers with Arabic company names.
 */
export function cleanVoiceText(rawText: string, maxChars: number = 10000): string {
    if (!rawText) return "";

    let text = rawText;

    // 1. Convert markdown table rows into spoken text instead of wiping them out
    text = text.replace(/\|[\s:\-]+\|[\s:\-]*[\r\n]+/g, "\n");
    text = text.replace(/\|/g, "، ");

    // 2. Remove markdown links [text](url) -> text
    text = text.replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1");

    // 3. Remove markdown bold, italic, code, headers
    text = text.replace(/#{1,6}\s*/g, "");
    text = text.replace(/[*`_~]/g, "");

    // 4. Strip parenthesized English tickers like (ABUK), ( TMGH ), (COMI.CA)
    text = text.replace(/[\(\[\{]\s*[A-Za-z0-9\.\-]{2,10}\s*[\)\]\}]/g, "");

    // 5. Strip ONLY trailing generic disclaimer sentences at the very bottom
    text = text.replace(/(?:إخلاء مسؤولية|تنبيه):\s*هذا التحليل لأغراض تعليمية[\s\S]*$/gi, "");
    text = text.replace(/منصة EGX BOTS ليست وسيطاً[\s\S]*$/gi, "");
    text = text.replace(/هذا التحليل لأغراض العمل الفني والتعليم فقط[\s\S]*$/gi, "");

    // 6. Remove emojis and decorative icons
    text = text.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "");
    text = text.replace(/[•–—▶️◀️⚡📈📉🎯🚨✅❌🔍⚖️💼📊💎👑🤖🔥📌💡⚠️🛑~_\^]/g, "");

    // 7. Clean prefixes before English words (e.g. والـ P/E -> مضاعف الربحية)
    text = text.replace(/(?:والـ|الـ)\s*(?=[A-Za-z])/g, " ");

    // 8. Natural spoken currency, indices, and stock terms into clear Arabic
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
    text = text.replace(/\bEPS\b/gi, " ربحية السهم ");
    text = text.replace(/(?:وقف الخسارة\s*)?\bSL\b/gi, " وقف الخسارة ");
    text = text.replace(/(?:جني الأرباح\s*|الهدف\s*)?\bTP\b/gi, " المستهدف ");
    text = text.replace(/\bBUY\b/gi, " شراء ");
    text = text.replace(/\bSELL\b/gi, " بيع ");
    text = text.replace(/\bHOLD\b/gi, " احتفاظ ");

    // 9. Replace standalone stock tickers with full Arabic company names
    for (const [sym, arName] of Object.entries(EGX_STOCK_TICKERS)) {
        const re = new RegExp(`\\b${sym}(?:\\.CA)?\\b`, "gi");
        text = text.replace(re, ` ${arName} `);
    }

    // 10. Clean any remaining English characters/words so the voice engine NEVER pronounces English
    text = text.replace(/[A-Za-z]+(?:\.[A-Za-z]+)?/g, "");

    // 11. Normalize whitespace and clean punctuation
    text = text.replace(/\s+/g, " ").trim();
    text = text.replace(/([،\.!؟])\s*\1+/g, "$1");

    // 12. Truncate smoothly at sentence boundary ONLY if exceeding maxChars (default 10,000)
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
