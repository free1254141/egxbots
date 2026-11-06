/**
 * IndexNow submission helper.
 *
 * Bing (and other IndexNow participants) use this protocol to discover changed
 * pages immediately instead of waiting for the next crawl. The key is public by
 * design: it is served from `/<key>.txt` so the engine can verify ownership.
 */

export const INDEXNOW_KEY = "0b1fb5f854a1e5ffa567dc068238d844";
export const SITE_HOST = "egxbots.com";
export const SITE_ORIGIN = `https://${SITE_HOST}`;

const INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow";
const MAX_URLS_PER_REQUEST = 500;

/** Public pages affected by each daily cache tag (used after invalidation). */
export const INDEXNOW_URLS_BY_TAG: Record<string, string[]> = {
  "daily-market-data": ["/", "/stocks", "/scanner/market", "/scanner/technical"],
  "daily-news-data": ["/news"],
  "daily-recommendations": ["/", "/scanner/backtests", "/stocks"],
  "daily-symbols": ["/stocks"],
  "daily-short-swings": ["/scanner/backtests"],
  "daily-public-reports": ["/reports"],
};

export function indexNowUrlsForTags(tags: string[]): string[] {
  return [...new Set(tags.flatMap((tag) => INDEXNOW_URLS_BY_TAG[tag] || []))];
}

/** Convert a path or absolute URL into a canonical, deduplicated URL list. */
export function normalizeIndexNowUrls(inputs: string[]): string[] {
  const seen = new Set<string>();
  for (const raw of inputs) {
    if (!raw) continue;
    const trimmed = String(raw).trim();
    if (!trimmed) continue;
    let url: URL;
    try {
      url = trimmed.startsWith("http")
        ? new URL(trimmed)
        : new URL(trimmed.startsWith("/") ? trimmed : `/${trimmed}`, SITE_ORIGIN);
    } catch {
      continue;
    }
    if (url.hostname !== SITE_HOST && url.hostname !== `www.${SITE_HOST}`) continue;
    url.hash = "";
    url.search = "";
    seen.add(url.toString());
    if (seen.size >= MAX_URLS_PER_REQUEST) break;
  }
  return Array.from(seen);
}

/**
 * Submit URLs to IndexNow. Never throws: indexing must not break a page render
 * or the daily pipeline.
 */
export async function submitToIndexNow(
  inputs: string[],
  options: { timeoutMs?: number } = {}
): Promise<{ submitted: number; ok: boolean; status?: number }> {
  const urlList = normalizeIndexNowUrls(inputs);
  if (!urlList.length) return { submitted: 0, ok: false };

  try {
    const response = await fetch(INDEXNOW_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify({
        host: SITE_HOST,
        key: INDEXNOW_KEY,
        keyLocation: `${SITE_ORIGIN}/${INDEXNOW_KEY}.txt`,
        urlList,
      }),
      signal: AbortSignal.timeout(options.timeoutMs ?? 8000),
    });
    return { submitted: urlList.length, ok: response.ok, status: response.status };
  } catch (error) {
    console.warn("[indexnow] submission failed:", error);
    return { submitted: urlList.length, ok: false };
  }
}
