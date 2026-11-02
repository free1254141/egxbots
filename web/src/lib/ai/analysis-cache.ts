import { normalizeArabicIntent } from "./intent-policy";

export const ANALYSIS_CACHE_TTL_MS = 15 * 60 * 1000; // 15 minutes (900 seconds)

export interface CachedVipAnalysis {
    reply: string;
    tables: any[];
    tools: any;
    summary_state?: any;
    computed_at_ms: number;
}

// Tier 1 In-Memory Cache (0ms latency, 0 CPU)
const memoryCache = new Map<string, CachedVipAnalysis>();

function pruneMemoryCache(): void {
    if (memoryCache.size > 500) {
        const now = Date.now();
        for (const [key, val] of memoryCache.entries()) {
            if (now - val.computed_at_ms > ANALYSIS_CACHE_TTL_MS) {
                memoryCache.delete(key);
            }
        }
        if (memoryCache.size > 500) {
            const keysToDelete = Array.from(memoryCache.keys()).slice(0, 100);
            for (const k of keysToDelete) {
                memoryCache.delete(k);
            }
        }
    }
}

/**
 * Build a deterministic cache key for high-frequency repeated queries:
 * - Single stock analysis (e.g. FWRY, TMGH, COMI)
 * - Two-stock comparison
 * - Quick market tools (market summary, accumulation, technical scan, news, open recs)
 * Returns null if the query is personalized (portfolio, personal cost, conversational follow-up).
 */
export function buildAnalysisCacheKey(
    rawMessage: string,
    explicitSymbols: string[],
    isPortfolioIntent: boolean
): string | null {
    if (isPortfolioIntent) {
        return null;
    }

    const trimmed = rawMessage.trim();
    if (!trimmed) return null;

    const normalized = normalizeArabicIntent(trimmed);

    // Personal inquiries must never share cache across users
    const isPersonal = /انا|أنا|اشتريت|شاري|متعلق|خسران|متوسطي|سعري|محفظتي|اسهمي|أسهمي/.test(normalized);
    if (isPersonal) {
        return null;
    }

    // 1. Single stock analysis query (e.g. "فوري", "حلل فوري", "FWRY", "سهم طلعت مصطفى")
    if (explicitSymbols.length === 1) {
        const sym = explicitSymbols[0].toUpperCase();
        return `vip_stock_${sym}`;
    }

    // 2. Two-stock comparison (e.g. "قارن بين فوري وموبكو")
    if (explicitSymbols.length === 2) {
        const sorted = [...explicitSymbols].map((s) => s.toUpperCase()).sort();
        if (/قارن|مقارن|ايهم|أيهما|افضل|أفضل|vs|versus/.test(normalized)) {
            return `vip_compare_${sorted.join("_")}`;
        }
    }

    // 3. Quick tools and market overview buttons
    if (/ملخص\s+السوق|اقوى\s+الاسهم|أقوى\s+الأسهم|market\s+summary/.test(normalized)) {
        return "vip_market_summary";
    }
    if (/اسهم\s+التجميع|أسهم\s+التجميع|تجميع\s+وسيولة|تجميع\s+وسيوله|accumulation/.test(normalized)) {
        return "vip_accumulation";
    }
    if (/المسح\s+الفني|مسح\s+فني|tech\s+screener/.test(normalized)) {
        return "vip_tech_screener";
    }
    if (/اخبار\s+السوق|أخبار\s+السوق|market\s+news/.test(normalized)) {
        return "vip_market_news";
    }
    if (/التوصيات\s+المفتوحة|التوصيات\s+المفتوحه|open\s+recommendations/.test(normalized)) {
        return "vip_open_recommendations";
    }

    return null;
}

/**
 * Retrieve cached VIP analysis from Tier 1 (Memory) or Tier 2 (Supabase market_cache).
 */
export async function getVipAnalysisCache(
    cacheKey: string,
    supabase: any,
    ttlMs: number = ANALYSIS_CACHE_TTL_MS
): Promise<{
    reply: string;
    tables: any[];
    tools: any;
    summary_state?: any;
    age_ms: number;
} | null> {
    const now = Date.now();

    // Tier 1: In-memory Map (0ms)
    const mem = memoryCache.get(cacheKey);
    if (mem) {
        const age = now - mem.computed_at_ms;
        if (age < ttlMs) {
            return {
                reply: mem.reply,
                tables: mem.tables || [],
                tools: mem.tools || { results: [], formattedText: "" },
                summary_state: mem.summary_state,
                age_ms: age,
            };
        } else {
            memoryCache.delete(cacheKey);
        }
    }

    // Tier 2: Supabase market_cache (cross-instance & surviving cold starts)
    if (!supabase) return null;
    try {
        const { data: row, error } = await supabase
            .from("market_cache")
            .select("payload, computed_at")
            .eq("cache_key", cacheKey)
            .maybeSingle();

        if (error || !row || !row.payload || !row.computed_at) {
            return null;
        }

        const computedAtMs = new Date(row.computed_at).getTime();
        const age = now - computedAtMs;
        if (age < ttlMs && typeof row.payload.reply === "string" && row.payload.reply.length > 50) {
            const entry: CachedVipAnalysis = {
                reply: row.payload.reply,
                tables: row.payload.tables || [],
                tools: row.payload.tools || { results: [], formattedText: "" },
                summary_state: row.payload.summary_state || null,
                computed_at_ms: computedAtMs,
            };
            memoryCache.set(cacheKey, entry);
            pruneMemoryCache();
            return {
                ...entry,
                age_ms: age,
            };
        }
    } catch (err) {
        console.warn(`[getVipAnalysisCache] Error querying market_cache for ${cacheKey}:`, err);
    }

    return null;
}

/**
 * Persist VIP analysis to Tier 1 (Memory) and Tier 2 (Supabase market_cache).
 */
export async function setVipAnalysisCache(
    cacheKey: string,
    payload: {
        reply: string;
        tables: any[];
        tools: any;
        summary_state?: any;
    },
    supabase: any
): Promise<void> {
    if (!payload.reply || payload.reply.length < 50) {
        return;
    }

    const now = Date.now();
    const entry: CachedVipAnalysis = {
        reply: payload.reply,
        tables: payload.tables || [],
        tools: payload.tools || { results: [], formattedText: "" },
        summary_state: payload.summary_state || null,
        computed_at_ms: now,
    };

    // Tier 1: In-memory
    memoryCache.set(cacheKey, entry);
    pruneMemoryCache();

    // Tier 2: Supabase market_cache
    if (!supabase) return;
    try {
        await supabase.from("market_cache").upsert({
            cache_key: cacheKey,
            country: "Egypt",
            payload: {
                reply: payload.reply,
                tables: payload.tables || [],
                tools: payload.tools || { results: [], formattedText: "" },
                summary_state: payload.summary_state || null,
            },
            computed_at: new Date(now).toISOString(),
        });
    } catch (err) {
        console.warn(`[setVipAnalysisCache] Error saving to market_cache for ${cacheKey}:`, err);
    }
}
