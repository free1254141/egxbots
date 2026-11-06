import { NextRequest, NextResponse } from "next/server";
import { SITE_ORIGIN, submitToIndexNow, normalizeIndexNowUrls } from "@/lib/indexnow";

/**
 * Manual / scripted IndexNow submission.
 *
 *   POST /api/indexnow                     -> core public pages
 *   POST /api/indexnow { "urls": [...] }   -> exactly those URLs
 *   POST /api/indexnow { "all": true }     -> every URL in the sitemap (chunked)
 *
 * Requires the same secret as /api/revalidate. IndexNow lets Bing discover
 * changed pages immediately instead of leaving them "discovered - not indexed".
 */
export const runtime = "nodejs";
export const maxDuration = 60;

const CORE_PATHS = [
  "/",
  "/stocks",
  "/pricing",
  "/news",
  "/blogs",
  "/chart",
  "/fair-value",
  "/sharia",
  "/scanner/market",
  "/scanner/technical",
  "/scanner/backtests",
  "/reports",
];

function isAuthorized(req: NextRequest): boolean {
  const secret =
    process.env.REVALIDATE_SECRET ||
    process.env.ADMIN_SECRET_KEY ||
    process.env.CRON_SECRET;
  if (!secret) return false;
  const url = new URL(req.url);
  const provided =
    url.searchParams.get("secret") ||
    (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
  return provided === secret;
}

async function collectSitemapUrls(): Promise<string[]> {
  const found = new Set<string>();
  const queue = [`${SITE_ORIGIN}/sitemap.xml`];
  const visited = new Set<string>();

  while (queue.length && found.size < 5000) {
    const next = queue.shift() as string;
    if (visited.has(next)) continue;
    visited.add(next);
    try {
      const res = await fetch(next, { signal: AbortSignal.timeout(10000) });
      if (!res.ok) continue;
      const xml = await res.text();
      for (const match of xml.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/g)) {
        const loc = match[1].replace(/&amp;/g, "&");
        if (/\.xml($|\?)/i.test(loc)) {
          queue.push(loc);
        } else {
          found.add(loc);
        }
      }
    } catch (error) {
      console.warn("[indexnow] sitemap read failed:", next, error);
    }
  }

  return Array.from(found);
}

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

export async function POST(req: NextRequest) {
  if (!isAuthorized(req)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({} as Record<string, unknown>));
  let urls: string[];

  if (body?.all === true) {
    urls = await collectSitemapUrls();
  } else if (Array.isArray(body?.urls) && body.urls.length) {
    urls = normalizeIndexNowUrls(body.urls.filter((u: unknown): u is string => typeof u === "string"));
  } else {
    urls = normalizeIndexNowUrls(CORE_PATHS);
  }

  if (!urls.length) {
    return NextResponse.json({ error: "No URLs to submit" }, { status: 400 });
  }

  const results = [];
  for (const batch of chunk(urls, 500)) {
    results.push(await submitToIndexNow(batch, { timeoutMs: 10000 }));
  }

  return NextResponse.json({
    total: urls.length,
    accepted: results.filter((r) => r.ok).reduce((sum, r) => sum + r.submitted, 0),
    batches: results,
  });
}

export async function GET(req: NextRequest) {
  return POST(req);
}
