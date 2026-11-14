/** Public datasets produced by the daily Python job. */
export const DAILY_CACHE_TAGS = {
  market: "daily-market-data",
  news: "daily-news-data",
  recommendations: "daily-recommendations",
  symbols: "daily-symbols",
  reports: "daily-public-reports",
  shortSwings: "daily-short-swings",
  disclosures: "daily-disclosures",
} as const;

export const DAILY_CACHE_TAG_VALUES = Object.values(DAILY_CACHE_TAGS);

export function dailyCacheHeaders(tag: string): Record<string, string> {
  return {
    "Cache-Control": "public, max-age=3600, s-maxage=604800, stale-while-revalidate=2592000",
    "Vercel-CDN-Cache-Control": "public, s-maxage=604800, stale-while-revalidate=2592000, stale-if-error=2592000",
    "Vercel-Cache-Tag": tag,
  };
}

/**
 * Tag a response so the daily job can invalidate it, without overriding the
 * freshness policy that route already chose for itself.
 */
export function withDailyTag<T extends Record<string, string>>(headers: T, tag: string): T & { "Vercel-Cache-Tag": string } {
  return { ...headers, "Vercel-Cache-Tag": tag };
}
