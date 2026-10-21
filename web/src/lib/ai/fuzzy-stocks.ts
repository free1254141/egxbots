import Fuse from "fuse.js";
import { ARABIC_STOCK_MAPPINGS } from "./symbol-aliases";
import { getSyncValidSymbols } from "./planner";

export interface FuzzySymbolMatch {
    symbol: string;
    matchedTerm: string;
    score: number;
}

interface FuzzyStockItem {
    symbol: string;
    alias: string;
    normalizedAlias: string;
    length: number;
}

let fuseInstance: Fuse<FuzzyStockItem> | null = null;
let fuseInitialized = false;

// Common Arabic stop words in chat prompts that must NOT match stock names
const STOP_WORDS = new Set([
    "ايه", "إيه", "ليه", "مين", "فين", "ازاي", "إزاي", "كام", "كم",
    "عايز", "عاوز", "نفسي", "محتاج", "اريد", "أريد",
    "اشتري", "أشتري", "شراء", "ابيع", "أبيع", "بيع", "ادخل", "أدخل", "دخول",
    "النهارده", "اليوم", "بكره", "بكرة", "امبارح", "أمس",
    "السوق", "البورصة", "البورصه", "اسهم", "الاسهم", "أسهم", "الأسهم", "سهم",
    "توصيات", "توصية", "توصيه", "فرص", "فرصة", "فرصه",
    "سيولة", "سيوله", "تجميع", "تصريف",
    "ازيك", "عامل", "شكرا", "تمام", "يا", "في", "من", "على", "الى", "إلى", "مع", "كل", "ده", "دي", "دا"
]);

function normalizeArabicText(text: string): string {
    return text
        .toLowerCase()
        .replace(/[\u064B-\u065F\u0670]/g, "") // tashkeel
        .replace(/\u0640/g, "")                 // tatweel
        .replace(/[أإآ]/g, "ا")
        .replace(/ة/g, "ه")
        .replace(/ى/g, "ي")
        .replace(/[،,.;!؟?#*]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}

/**
 * Builds or returns a singleton Fuse index over all mapped Arabic names, aliases,
 * and valid ticker symbols.
 */
export function getFuzzyStockSearcher(): Fuse<FuzzyStockItem> {
    if (fuseInstance && fuseInitialized) {
        return fuseInstance;
    }

    const items: FuzzyStockItem[] = [];
    const validSymbols = new Set(getSyncValidSymbols());

    for (const [alias, symOrArr] of Object.entries(ARABIC_STOCK_MAPPINGS)) {
        const symbols = Array.isArray(symOrArr) ? symOrArr : [symOrArr];
        const normAlias = normalizeArabicText(alias);
        if (normAlias.length < 3 || STOP_WORDS.has(normAlias)) continue;

        for (const s of symbols) {
            const sym = s.toUpperCase();
            items.push({
                symbol: sym,
                alias,
                normalizedAlias: normAlias,
                length: normAlias.length
            });
        }
    }

    // Also index valid tickers
    for (const sym of validSymbols) {
        if (sym.length >= 2 && !STOP_WORDS.has(sym.toLowerCase())) {
            items.push({
                symbol: sym,
                alias: sym,
                normalizedAlias: sym.toLowerCase(),
                length: sym.length
            });
        }
    }

    fuseInstance = new Fuse(items, {
        keys: [{ name: "normalizedAlias", weight: 1.0 }],
        threshold: 0.30,        // 0.30 comfortably captures 1-2 letter typos
        ignoreLocation: true,   // Essential for short words/typos
        minMatchCharLength: 3,
        includeScore: true,
        shouldSort: true
    });

    fuseInitialized = true;
    return fuseInstance;
}

/**
 * Clean common intent prefixes from the query (like "حلل", "سهم", "عايز تحليل")
 * to isolate the candidate stock name before searching.
 */
function extractCandidateTerms(message: string): string[] {
    const norm = normalizeArabicText(message);
    const cleaned = norm
        .replace(/^(?:حلل|تحليل|وريني|هات|اخبار|أخبار|سعر|سهم|معلومات|رايك في|رأيك في|ايه رايك في|إيه رأيك في|مستهدف|اهداف|أهداف|شركه|شركة|شراء|بيع|دخول)\s+/i, "")
        .replace(/\s+(?:النهارده|اليوم|دلوقتي|حاليا|بكره|بكرة|السوق)$/i, "")
        .trim();

    const terms: string[] = [];
    if (cleaned && cleaned.length >= 3 && !STOP_WORDS.has(cleaned)) {
        terms.push(cleaned);
    }

    const words = cleaned.split(/\s+/).filter(w => w.length >= 3 && !STOP_WORDS.has(w));
    for (const w of words) {
        if (!terms.includes(w)) {
            terms.push(w);
        }
    }

    return terms;
}

/**
 * Fast-path fuzzy matcher for Egyptian stocks.
 * Matches user query against EGX stock names/aliases with typo tolerance in < 2ms.
 */
export function fuzzyFindStockSymbol(message: string): FuzzySymbolMatch | null {
    if (!message || message.trim().length < 2) return null;

    const norm = normalizeArabicText(message);
    const wordsInMsg = norm.split(/\s+/).filter(Boolean);
    const nonStopWords = wordsInMsg.filter(w => !STOP_WORDS.has(w));
    if (nonStopWords.length === 0) {
        return null;
    }

    // Broad market query guard
    if (/(?:توصيات|توصية|توصيه|فرص|سيولة|سيوله|اعلى اسهم|اقوى اسهم|افضل اسهم|مين طلع|مين نزل|حالة السوق|ايه السوق)/i.test(norm)) {
        return null;
    }

    const fuse = getFuzzyStockSearcher();
    const candidateTerms = extractCandidateTerms(message);

    for (const term of candidateTerms) {
        if (STOP_WORDS.has(term) || term.length < 3) continue;

        const results = fuse.search(term);
        if (results && results.length > 0) {
            for (const res of results) {
                if (res.score === undefined || res.score > 0.30) continue;

                // Length ratio sanity check: difference shouldn't be huge
                const lenDiff = Math.abs(term.length - res.item.length);
                if (lenDiff > 4 && term.length < 6) continue;

                return {
                    symbol: res.item.symbol,
                    matchedTerm: res.item.alias,
                    score: res.score
                };
            }
        }
    }

    return null;
}
