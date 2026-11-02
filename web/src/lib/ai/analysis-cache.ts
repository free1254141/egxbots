import { normalizeArabicIntent } from "./intent-policy";

/**
 * Shared AI answer cache (website chat + Telegram VIP chat).
 *
 * Rules:
 *  - Demand-driven only ("السؤال يتسئل مره يتحد نوعه ويتسخن"): no background cron
 *    warming of the whole market. When a user asks a canonical repeatable question
 *    for the first time, the full 9-tool Agentic Pipeline runs and warms the cache.
 *  - Smart intent filtering: open-ended dialogues ("حوارات"), "why/how/what-if"
 *    questions, custom numeric conditions, custom screener filters, backtests, and
 *    personal/portfolio questions return `null` so they bypass the cache and go
 *    directly to the 9 Agentic Tools.
 *  - Strict portfolio privacy: user-specific portfolio sentences are stripped and
 *    the `📌 حالة السهم في محفظتك` line is neutralized before saving, then
 *    re-injected dynamically per requesting user from `positions`.
 *  - Session-aware freshness: 15 minutes during the EGX live trading session
 *    (or before the 17:00 after-close job finishes), and once computed after the
 *    17:00 close job finishes (17:15 Cairo time) it stays valid until the next
 *    market session opens at 10:00 AM Cairo time.
 */

export const ANALYSIS_CACHE_TTL_MS = 15 * 60 * 1000; // live-session TTL (15 minutes)
const MAX_OFF_HOURS_AGE_MS = 4 * 24 * 60 * 60 * 1000; // never serve anything older than 4 days

const CAIRO_TZ = "Africa/Cairo";
const SESSION_OPEN_MIN = 10 * 60; // 10:00 Cairo
const SESSION_CLOSE_MIN = 14 * 60 + 30; // 14:30 Cairo
const DATA_READY_MIN = 17 * 60 + 15; // 17:15 Cairo (after the 17:00 close job completes)
const TRADING_WEEKDAYS = new Set([0, 1, 2, 3, 4]); // Sunday..Thursday

export interface CachedVipAnalysis {
    reply: string;
    tables: any[];
    tools: any;
    summary_state?: any;
    extra?: any;
    computed_at_ms: number;
}

const NEUTRAL_PORTFOLIO_LINE =
    "📌 **حالة السهم في محفظتك:** السهم غير مسجل ضمن مراكز محفظتك الاستثمارية المحفوظة.";
const PORTFOLIO_LINE_SOURCE = "(?:•\\s*)?📌\\s*(?:\\*\\*)?حالة السهم في محفظتك:(?:\\*\\*)?[^\\n]+";
const PERSONAL_SYNTHESIS_REGEX = /مركزك الحالي عند [0-9.]+[^\n,،.]*[,،.]?\s*/g;
const PERSONAL_SENTENCE_REGEX = /(?:مركزك|مراكزك|محفظتك|محفظتي|متوسط شراء|لديك\s+\d+\s+سهم)/;
const LINE_PLACEHOLDER = "\uE000";

// Tier 1 In-Memory Cache (0ms latency, 0 CPU)
const memoryCache = new Map<string, CachedVipAnalysis>();

function pruneMemoryCache(): void {
    if (memoryCache.size <= 500) return;
    const now = Date.now();
    for (const [key, val] of memoryCache.entries()) {
        if (now - val.computed_at_ms > MAX_OFF_HOURS_AGE_MS) memoryCache.delete(key);
    }
    if (memoryCache.size > 500) {
        for (const k of Array.from(memoryCache.keys()).slice(0, 100)) memoryCache.delete(k);
    }
}

// ---------------------------------------------------------------------------
// Cairo market-session helpers
// ---------------------------------------------------------------------------

const cairoFormatter = new Intl.DateTimeFormat("en-US", {
    timeZone: CAIRO_TZ,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    weekday: "short",
});

const WEEKDAY_INDEX: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

function cairoParts(ms: number) {
    const parts: Record<string, string> = {};
    for (const p of cairoFormatter.formatToParts(new Date(ms))) parts[p.type] = p.value;
    return {
        y: Number(parts.year),
        m: Number(parts.month),
        d: Number(parts.day),
        h: Number(parts.hour) % 24,
        min: Number(parts.minute),
        wd: WEEKDAY_INDEX[parts.weekday] ?? 0,
    };
}

/** Epoch ms of a Cairo wall-clock time (handles Egypt's DST offset). */
function cairoWallToMs(y: number, m: number, d: number, minuteOfDay: number): number {
    const guess = Date.UTC(y, m - 1, d, Math.floor(minuteOfDay / 60), minuteOfDay % 60);
    const p = cairoParts(guess);
    const asUtc = Date.UTC(p.y, p.m - 1, p.d, p.h, p.min);
    return guess - (asUtc - guess);
}

/** Close/ready timestamps of the most recent completed trading session. */
function lastCompletedSession(nowMs: number): { closeMs: number; readyMs: number } | null {
    const now = cairoParts(nowMs);
    const minutes = now.h * 60 + now.min;
    for (let back = 0; back < 8; back++) {
        const probeMs = nowMs - back * 24 * 60 * 60 * 1000;
        const p = cairoParts(probeMs);
        if (!TRADING_WEEKDAYS.has(p.wd)) continue;
        if (back === 0 && minutes < SESSION_CLOSE_MIN) continue; // today's session not finished yet
        return {
            closeMs: cairoWallToMs(p.y, p.m, p.d, SESSION_CLOSE_MIN),
            readyMs: cairoWallToMs(p.y, p.m, p.d, DATA_READY_MIN),
        };
    }
    return null;
}

/**
 * Decide whether a cached entry may still be served.
 *  - Always valid for the first 15 minutes.
 *  - During the live session (10:00–14:30 Sun–Thu): never valid beyond 15 minutes.
 *  - Outside the session: if computed after the 17:00 after-close job finished
 *    (>= 17:15 Cairo time on the last completed session), valid all night/weekend
 *    until the next trading session opens at 10:00 AM Cairo time.
 */
export function resolveCacheValidity(
    computedAtMs: number,
    nowMs: number = Date.now()
): boolean {
    const age = nowMs - computedAtMs;
    if (age < -60_000) return false; // clock skew guard
    if (age < ANALYSIS_CACHE_TTL_MS) return true;
    if (age > MAX_OFF_HOURS_AGE_MS) return false;

    const now = cairoParts(nowMs);
    const minutes = now.h * 60 + now.min;
    const inSession = TRADING_WEEKDAYS.has(now.wd) && minutes >= SESSION_OPEN_MIN && minutes < SESSION_CLOSE_MIN;
    if (inSession) return false;

    const last = lastCompletedSession(nowMs);
    if (!last) return false;
    return computedAtMs >= last.readyMs;
}

// ---------------------------------------------------------------------------
// Privacy: neutralise / re-inject portfolio information
// ---------------------------------------------------------------------------

/**
 * Remove anything user-specific from an answer before it enters the shared cache.
 * `keepPortfolioLine` keeps a neutral (not-in-portfolio) line that is replaced
 * per user when served; otherwise the line is dropped (multi-stock answers).
 */
export function sanitizeAnalysisForCache(reply: string, keepPortfolioLine: boolean = true): string {
    if (!reply) return reply;

    let text = reply.replace(PERSONAL_SYNTHESIS_REGEX, "");
    text = text.replace(new RegExp(PORTFOLIO_LINE_SOURCE, "g"), keepPortfolioLine ? LINE_PLACEHOLDER : "");

    const cleanedLines: string[] = [];
    for (const line of text.split("\n")) {
        if (line.trim() === LINE_PLACEHOLDER) {
            cleanedLines.push(LINE_PLACEHOLDER);
            continue;
        }
        if (!PERSONAL_SENTENCE_REGEX.test(line)) {
            cleanedLines.push(line);
            continue;
        }
        if (line.trim().startsWith("|")) continue; // personal table row
        const kept = line
            .split(/(?<=[.؟!؛])\s+/)
            .filter((sentence) => !PERSONAL_SENTENCE_REGEX.test(sentence))
            .join(" ")
            .trim();
        if (kept) cleanedLines.push(kept);
    }

    return cleanedLines.join("\n").split(LINE_PLACEHOLDER).join(NEUTRAL_PORTFOLIO_LINE);
}

/**
 * Re-inject the requesting user's real position into a cached stock analysis.
 * User A's holdings can never reach user B: the cache only holds the neutral line.
 */
export async function personalizeCachedAnalysis(
    baseReply: string,
    userId: string | null | undefined,
    symbol: string | null | undefined,
    supabase: any
): Promise<string> {
    if (!baseReply) return baseReply;
    if (!new RegExp(PORTFOLIO_LINE_SOURCE).test(baseReply)) return baseReply;

    let userPortfolioLine = NEUTRAL_PORTFOLIO_LINE;

    if (userId && symbol && supabase) {
        try {
            const sym = symbol.toUpperCase().trim();
            const { data: pos } = await supabase
                .from("positions")
                .select("quantity, entry_price, status_price")
                .eq("user_id", userId)
                .eq("symbol", sym)
                .eq("status", "open")
                .maybeSingle();

            if (pos && Number(pos.quantity) > 0) {
                const qty = Number(pos.quantity);
                const entry = Number(pos.entry_price || 0);
                const priceMatch = baseReply.match(/السعر الأخير:\s*`?([0-9.]+)/);
                const currentPrice = priceMatch ? parseFloat(priceMatch[1]) : Number(pos.status_price || 0);

                let pnlStr = "";
                if (entry > 0 && currentPrice > 0) {
                    const pnlPct = ((currentPrice - entry) / entry) * 100;
                    const sign = pnlPct >= 0 ? "+" : "";
                    const label = pnlPct >= 0 ? "أرباح غير محققة" : "خسارة غير محققة";
                    pnlStr = ` (${label}: ${sign}${pnlPct.toFixed(2)}%)`;
                }
                userPortfolioLine = `📌 **حالة السهم في محفظتك:** مسجل لديك ${qty} سهم بمتوسط شراء ${entry.toFixed(2)} ج.م${pnlStr}.`;
            }
        } catch (err) {
            console.warn("[personalizeCachedAnalysis] Error fetching user position:", err);
        }
    }

    return baseReply.replace(new RegExp(PORTFOLIO_LINE_SOURCE, "g"), () => userPortfolioLine);
}

// ---------------------------------------------------------------------------
// Smart Intent Classification -> Canonical Cache Key (or null for direct tools)
// ---------------------------------------------------------------------------

function normalizeText(text: string): string {
    return normalizeArabicIntent(text)
        .replace(/[أإآ]/g, "ا")
        .replace(/ى/g, "ي")
        .replace(/ة/g, "ه")
        .replace(/[\u064b-\u065f\u0670]/g, "")
        .replace(/[\u0660-\u0669]/g, (d) => String(d.charCodeAt(0) - 0x0660))
        .toLowerCase();
}

const PERSONAL_SUBSTRINGS = [
    "محفظتي", "محفظتك", "محفظه", "اسهمي", "متوسطي", "شرائي", "اشتريت", "شريت", "بعت",
    "معايا", "عندي", "عالق", "متعلق", "علقت", "خسران", "خسرت", "كسبان", "رصيدي",
    "فلوسي", "مركزي", "مراكزي", "استثمر", "ادخر", "ابيع", "احتفظ",
];

const PERSONAL_TOKENS = new Set(["انا", "اني", "انى", "املك", "ملكي", "بيع"]);

// Pronouns / deictics that depend on previous conversation turns
const REFERENCE_TOKENS = new Set([
    "فيه", "فيها", "منه", "منها", "عنه", "عنها", "كمان", "التاني", "والتاني",
    "الاول", "والاول", "الاخير", "السابق", "بتاعه", "بتاعها", "نفسه", "نفسها",
    "ده", "دا", "دي", "ديه", "دول",
]);

// Open-ended dialogue ("حوارات"), why/how/what-if, educational, backtest, or custom condition markers
const DIALOGUE_OR_CUSTOM_TOKENS = new Set([
    "ليه", "لماذا", "ازاي", "كيف", "اشمعني", "اشمعنا", "امتي", "امتى", "متي", "متى",
    "لو", "اذا", "افرض", "فرضا", "تفتكر", "تتوقع", "طيب", "طب", "امال", "يعني",
    "اشرح", "اشرحلي", "عرفني", "فهمني", "اختبر", "استراتيجيه", "باك", "backtest",
    "دايفرجنس", "divergence", "شرط", "فلتر", "سيناريو", "فايده", "فائده", "دولار",
    "تضخم", "تعويم", "ذهب", "بيتكوين", "تاثير", "علاقه", "فرق", "سبب", "اسباب",
]);

const CUSTOM_PHRASE_REGEX =
    /توصيات\s*حره|بمزاجك|وضع\s*التوصيات|ما\s*معني|ما\s*هو\s*مؤشر|يعني\s*ايه/;

/**
 * Detect whether a query contains arbitrary numbers (prices, quantities, money
 * amounts, percentages, or custom indicator thresholds like "RSI تحت 30"),
 * ignoring standard EGX index names (EGX30, EGX70, EGX100, EGX33).
 */
function hasCustomNumbers(normalized: string, symbolTokens: string[]): boolean {
    let stripped = normalized
        .replace(/egx\s*(?:30|70|100|33)\b/g, " ")
        .replace(/(?:مؤشر|اسهم)\s*(?:ال)?\s*(?:30|70|100|33)\b/g, " ");
    for (const sym of symbolTokens) {
        stripped = stripped.replace(new RegExp(sym.toLowerCase(), "g"), " ");
    }
    return /\d/.test(stripped);
}

function stripArabicPrefix(token: string): string {
    return token.replace(/^(?:و|ف|ب|ك|ل)?(?:ال)?/, "");
}

function isPersonalOrDialogueOrCustom(normalized: string, symbolTokens: string[]): boolean {
    if (CUSTOM_PHRASE_REGEX.test(normalized)) return true;
    if (hasCustomNumbers(normalized, symbolTokens)) return true;
    if (PERSONAL_SUBSTRINGS.some((w) => normalized.includes(w))) return true;

    const tokens = normalized.split(/[\s،,.؟?!:؛/\\()-]+/).filter(Boolean);
    for (const t of tokens) {
        const bare = stripArabicPrefix(t);
        if (
            PERSONAL_TOKENS.has(t) ||
            PERSONAL_TOKENS.has(bare) ||
            REFERENCE_TOKENS.has(t) ||
            DIALOGUE_OR_CUSTOM_TOKENS.has(t) ||
            DIALOGUE_OR_CUSTOM_TOKENS.has(bare)
        ) {
            return true;
        }
    }
    return false;
}

const SINGLE_STOCK_SUB_INTENTS: Array<[string, RegExp]> = [
    ["levels", /دعم|دعوم|مقاوم|مستويات|نقاط\s*(?:ال)?دخول|نقاط\s*(?:ال)?خروج|وقف\s*(?:ال)?خسار|اهداف|هدف|levels?|support|resistance|targets?/],
    ["news", /اخبار|خبر|اعلان|افصاح|news/],
    ["divs", /توزيع|كوبون|dividend/],
    ["sharia", /شرعي|حلال|حرام|حكم\s*سهم|sharia/],
    ["liquidity", /سيوله|تجميع|تصريف|وايكوف|wyckoff|liquidity/],
    ["financials", /قوائم\s*(?:ال)?ماليه|تحليل\s*(?:ال)?مالي|مالي\s*لسهم|مضاعف\s*(?:ال)?ربحيه|ربحيه\s*(?:ال)?سهم|نتائج\s*(?:ال)?اعمال|قيمه\s*(?:ال)?دفتريه|قيمه\s*(?:ال)?عادله|\bpe\b|\beps\b|fundamental/],
];

const PURE_ANALYSIS_WORDS =
    /حلل|تحليل|تقييم|تقرير|رايك|شوف|شوفلي|اعرض|تفاصيل|حاله|وضع|analy/;

const NON_STANDARD_STOCK_WORDS =
    /اشتري|شراء|ادخل|اخرج|توقع|هيوصل|هيطلع|هينزل|مستقبل|مضاربه|استثمار|rsi|macd|ema|sma|adx|stoch|مؤشر|تشبع/;

/**
 * Classify a single-stock query into a strict canonical intent bucket, or return
 * `null` if the query is custom/specific/conversational and must go directly to tools.
 */
export function classifyStockIntent(normalized: string, symbolTokens: string[] = []): string | null {
    const tokens = normalized.split(/[\s،,.؟?!:؛/\\()-]+/).filter(Boolean);
    if (tokens.length > 8) return null;

    // If the user explicitly asks for comprehensive analysis ("حلل", "تحليل فني", "تقييم", "رايك في"),
    // and isn't asking solely for news/dividends/sharia/levels, route to the main analysis report.
    for (const [name, pattern] of SINGLE_STOCK_SUB_INTENTS) {
        if (pattern.test(normalized)) {
            return name;
        }
    }

    if (NON_STANDARD_STOCK_WORDS.test(normalized)) {
        return null;
    }

    const withoutSymbols = symbolTokens.reduce(
        (acc, s) => acc.replace(new RegExp(s.toLowerCase(), "g"), " "),
        normalized
    );
    const remainingWords = withoutSymbols.split(/\s+/).filter(Boolean);

    if (PURE_ANALYSIS_WORDS.test(normalized) || remainingWords.length <= 4) {
        return "analysis";
    }

    return null;
}

const SECTOR_NAMES_REGEX =
    /قطاع\s+(البنوك|العقارات|الخدمات\s*الماليه|البتروكيماويات|الاغذيه|الادويه|الاتصالات|التكنولوجيا|الموارد\s*الاساسيه|مواد\s*البناء|السياحه|النقل|المنسوجات|المقاولات)|^(البنوك|العقارات)\s+حالتها\s*ايه/;

/**
 * Build a deterministic cache key for repeatable canonical questions, or return
 * `null` when the question is personal, conversational ("حوارات"), or custom so
 * it passes straight through to the 9 Agentic Tools.
 */
export function buildAnalysisCacheKey(
    rawMessage: string,
    explicitSymbols: string[],
    isPortfolioIntent: boolean
): string | null {
    if (isPortfolioIntent) return null;

    const trimmed = (rawMessage || "").trim();
    if (!trimmed) return null;

    const normalized = normalizeText(trimmed);
    if (isPersonalOrDialogueOrCustom(normalized, explicitSymbols)) return null;

    // 1. Single stock canonical intents
    if (explicitSymbols.length === 1) {
        const sym = explicitSymbols[0].toUpperCase();
        const intent = classifyStockIntent(normalized, explicitSymbols);
        if (!intent) return null;
        return intent === "analysis" ? `vip_stock_${sym}` : `vip_stock_${sym}_${intent}`;
    }

    // 2. Two-stock canonical comparison
    if (explicitSymbols.length === 2) {
        const tokens = normalized.split(/\s+/).filter(Boolean);
        if (tokens.length > 8) return null;
        const sorted = explicitSymbols.map((s) => s.toUpperCase()).sort();
        if (/قارن|مقارن|ايهم|افضل|ام\b|vs|versus/.test(normalized)) {
            return `vip_compare_${sorted.join("_")}`;
        }
        return null;
    }

    if (explicitSymbols.length > 2) return null;

    // 3. Canonical Market-Wide Buttons & Repeatable Queries (only short, direct requests)
    const wordCount = normalized.split(/\s+/).filter(Boolean).length;
    if (wordCount > 7) return null;

    if (/ملخص\s+السوق|حاله\s+السوق|وضع\s+السوق|market\s+summary/.test(normalized)) {
        return "vip_market_summary";
    }
    if (/^(?:ايه\s+)?(?:اقوي|اقوى|افضل)\s+الاسهم(?:\s+النهارده|\s+اليوم|\s+الان)?$/.test(normalized)) {
        return "vip_top_stocks";
    }
    if (/اسهم\s+التجميع|تجميع\s+وسيوله|السيوله\s+والتجميع|accumulation/.test(normalized)) {
        return "vip_accumulation";
    }
    if (/المسح\s+الفني|مسح\s+فني|الماسح\s+الذكي|tech\s+screener/.test(normalized)) {
        return "vip_tech_screener";
    }
    if (/اخبار\s+السوق|اخبار\s+البورصه|market\s+news/.test(normalized)) {
        return "vip_market_news";
    }
    if (/توصيات\s+الاسبوع\s+(?:الحالي|ده|هذا)|هذا\s+الاسبوع/.test(normalized)) {
        return "vip_recs_this_week";
    }
    if (/توصيات\s+الاسبوع\s+(?:اللي\s+فات|الماضي|السابق)/.test(normalized)) {
        return "vip_recs_last_week";
    }
    if (/التوصيات\s+المفتوحه|كل\s+التوصيات|التوصيات\s+النشطه| التوصيات\s+الحاليه|open\s+recommendations/.test(normalized)) {
        return "vip_open_recommendations";
    }
    if (/(?:اقوي|اقوى|افضل)\s+(?:القطاعات|قطاع)|اي\s+القطاعات\s+الاقوي/.test(normalized)) {
        return "vip_top_sectors";
    }

    const sectorMatch = normalized.match(SECTOR_NAMES_REGEX);
    if (sectorMatch) {
        const sectorName = (sectorMatch[1] || sectorMatch[2] || "").replace(/\s+/g, "_");
        if (sectorName) return `vip_sector_${sectorName}`;
    }

    // Anything else (general chat, open-ended questions, custom screener criteria, macro discussions)
    // returns null so the pipeline invokes the 9 Agentic Tools directly.
    return null;
}

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------

const PORTFOLIO_TOOLS = new Set(["manage_portfolio", "analyze_portfolio_risk"]);

function lightTools(tools: any): { results: Array<{ tool: string }>; formattedText: string } {
    const results = Array.isArray(tools?.results) ? tools.results : [];
    return {
        results: results
            .filter((r: any) => r?.tool && !PORTFOLIO_TOOLS.has(r.tool))
            .map((r: any) => ({ tool: String(r.tool) })),
        formattedText: "",
    };
}

function publicTables(tables: any[] | undefined): any[] {
    return (tables || []).filter((t) => !/محفظ/.test(JSON.stringify(t?.title ?? t?.name ?? "")));
}

export async function getVipAnalysisCache(
    cacheKey: string,
    supabase: any,
    ttlMs?: number
): Promise<{
    reply: string;
    tables: any[];
    tools: any;
    summary_state?: any;
    extra?: any;
    age_ms: number;
} | null> {
    const now = Date.now();
    const isFresh = (computedAt: number) =>
        ttlMs !== undefined ? now - computedAt < ttlMs : resolveCacheValidity(computedAt, now);

    // Tier 1: in-memory
    const mem = memoryCache.get(cacheKey);
    if (mem) {
        if (isFresh(mem.computed_at_ms)) {
            return {
                reply: mem.reply,
                tables: mem.tables || [],
                tools: mem.tools || { results: [], formattedText: "" },
                summary_state: mem.summary_state,
                extra: mem.extra,
                age_ms: now - mem.computed_at_ms,
            };
        }
        memoryCache.delete(cacheKey);
    }

    // Tier 2: Supabase market_cache (cross-instance, survives cold starts)
    if (!supabase) return null;
    try {
        const { data: row, error } = await supabase
            .from("market_cache")
            .select("payload, computed_at")
            .eq("cache_key", cacheKey)
            .maybeSingle();

        if (error || !row?.payload || !row.computed_at) return null;

        const computedAtMs = new Date(row.computed_at).getTime();
        if (isFresh(computedAtMs) && typeof row.payload.reply === "string" && row.payload.reply.length > 50) {
            const entry: CachedVipAnalysis = {
                reply: row.payload.reply,
                tables: row.payload.tables || [],
                tools: row.payload.tools || { results: [], formattedText: "" },
                summary_state: row.payload.summary_state || null,
                extra: row.payload.extra || null,
                computed_at_ms: computedAtMs,
            };
            memoryCache.set(cacheKey, entry);
            pruneMemoryCache();
            return { ...entry, age_ms: now - computedAtMs };
        }
    } catch (err) {
        console.warn(`[getVipAnalysisCache] Error querying market_cache for ${cacheKey}:`, err);
    }
    return null;
}

/**
 * Persist an answer to the shared cache (memory + market_cache).
 */
export async function setVipAnalysisCache(
    cacheKey: string,
    payload: {
        reply: string;
        tables: any[];
        tools: any;
        summary_state?: any;
        extra?: any;
    },
    supabase: any
): Promise<void> {
    if (!payload.reply || payload.reply.length < 50) return;

    const reply = sanitizeAnalysisForCache(payload.reply, cacheKey.startsWith("vip_stock_"));
    if (reply.length < 50) return;

    const now = Date.now();
    const entry: CachedVipAnalysis = {
        reply,
        tables: publicTables(payload.tables),
        tools: lightTools(payload.tools),
        summary_state: null, // conversation state is per user, never shared
        extra: payload.extra || null,
        computed_at_ms: now,
    };

    memoryCache.set(cacheKey, entry);
    pruneMemoryCache();

    if (!supabase) return;
    try {
        await supabase.from("market_cache").upsert({
            cache_key: cacheKey,
            country: "Egypt",
            payload: {
                reply: entry.reply,
                tables: entry.tables,
                tools: entry.tools,
                summary_state: null,
                extra: entry.extra,
            },
            computed_at: new Date(now).toISOString(),
        });
    } catch (err) {
        console.warn(`[setVipAnalysisCache] Error saving to market_cache for ${cacheKey}:`, err);
    }
}
