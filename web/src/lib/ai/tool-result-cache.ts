import { createHash } from "node:crypto";
import { resolveCacheValidity } from "./analysis-cache";

/**
 * Day-level cache for read-only agentic tool results.
 *
 * Every chat message that misses the answer cache re-runs the whole tool loop.
 * Most of those tools only read public daily data (prices, indicators, news,
 * fair value, Sharia screening), so their output is identical for every user
 * asking the same question on the same trading day.
 *
 * Only tools that never read `userId` and never mutate state are eligible —
 * portfolio, alert, automation and live-quote tools are explicitly excluded.
 * Nothing here changes an answer's content: it just avoids recomputing a value
 * that has already been computed for the same inputs today.
 */

const CACHEABLE_TOOLS = new Set([
  "get_stock",
  "get_stock_levels",
  "get_market",
  "get_recommendations",
  "get_technical_scan",
  "get_accumulation_stocks",
  "get_news",
  "get_comparison",
  "get_fair_value",
  "get_sharia_cleanser",
  "get_price_traps",
  "screen_stocks",
]);

const ENABLED =
  process.env.NODE_ENV !== "test" && process.env.TOOL_RESULT_CACHE !== "off";

const MAX_MEMORY_ENTRIES = 400;
const STALE_TOOL_CACHE_MS = 36 * 60 * 60 * 1000; // prune tool_% rows older than 36h
const memoryCache = new Map<string, { payload: any; computed_at_ms: number }>();
let lastPrunedCairoDay = "";

export function isToolResultPayloadCacheable(result: any): boolean {
  if (!result || typeof result !== "object") return false;
  const status = String(result.status || "").toLowerCase();
  const availability = String(result.availability || "").toLowerCase();
  if (status === "error" || status === "unavailable") return false;
  if (availability === "error" || availability === "unavailable") return false;
  return true;
}

function pruneMemory(): void {
  if (memoryCache.size <= MAX_MEMORY_ENTRIES) return;
  const now = Date.now();
  for (const [key, value] of memoryCache) {
    if (now - value.computed_at_ms > 60 * 60 * 1000) memoryCache.delete(key);
  }
  while (memoryCache.size > MAX_MEMORY_ENTRIES) {
    const oldest = memoryCache.keys().next().value;
    if (oldest === undefined) break;
    memoryCache.delete(oldest);
  }
}

/** Stable JSON so `{a:1,b:2}` and `{b:2,a:1}` produce one key. */
export function stableStringify(value: any): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(value[k])}`).join(",")}}`;
}

export function cairoDateKey(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Cairo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

export function isToolResultCacheEnabled(): boolean {
  return ENABLED;
}

/** Allowlist check only — the env switch is separate so it stays testable. */
export function isToolResultCacheable(toolName: string): boolean {
  return CACHEABLE_TOOLS.has(toolName);
}

export function buildToolResultCacheKey(
  toolName: string,
  args: Record<string, any>,
  now: Date = new Date()
): string {
  const digest = createHash("sha256")
    .update(`${toolName}|${stableStringify(args || {})}`)
    .digest("hex")
    .slice(0, 24);
  return `tool_${toolName}_${cairoDateKey(now)}_${digest}`;
}

export function clearToolResultMemoryCache(): void {
  memoryCache.clear();
  lastPrunedCairoDay = "";
}

export async function getCachedToolResult(
  cacheKey: string,
  supabase: any
): Promise<any | null> {
  const now = Date.now();

  const mem = memoryCache.get(cacheKey);
  if (mem) {
    if (resolveCacheValidity(mem.computed_at_ms, now)) return mem.payload;
    memoryCache.delete(cacheKey);
  }

  if (!supabase) return null;
  try {
    const { data, error } = await supabase
      .from("market_cache")
      .select("payload, computed_at")
      .eq("cache_key", cacheKey)
      .maybeSingle();
    if (error || !data?.payload || !data.computed_at) return null;

    const computedAtMs = new Date(data.computed_at).getTime();
    if (!Number.isFinite(computedAtMs) || !resolveCacheValidity(computedAtMs, now)) {
      return null;
    }

    const payload = data.payload?.result ?? data.payload;
    memoryCache.set(cacheKey, { payload, computed_at_ms: computedAtMs });
    pruneMemory();
    return payload;
  } catch {
    return null;
  }
}

export async function setCachedToolResult(
  cacheKey: string,
  result: any,
  supabase: any
): Promise<void> {
  if (!isToolResultPayloadCacheable(result)) return;
  const now = Date.now();
  memoryCache.set(cacheKey, { payload: result, computed_at_ms: now });
  pruneMemory();

  if (!supabase) return;
  try {
    await supabase.from("market_cache").upsert({
      cache_key: cacheKey,
      country: "Egypt",
      payload: { result },
      computed_at: new Date(now).toISOString(),
    });

    const todayKey = cairoDateKey(new Date(now));
    if (todayKey !== lastPrunedCairoDay) {
      lastPrunedCairoDay = todayKey;
      const cutoffIso = new Date(now - STALE_TOOL_CACHE_MS).toISOString();
      Promise.resolve(
        supabase
          .from("market_cache")
          .delete()
          .like("cache_key", "tool_%")
          .lt("computed_at", cutoffIso)
      ).catch(() => {});
    }
  } catch {
    // Caching must never break a tool call.
  }
}
