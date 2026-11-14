import { NextRequest, NextResponse } from "next/server";
import { unstable_cache } from "next/cache";
import {
  resolveRequestMarket,
  getMarketExchange,
  getMarketSupabaseServiceClient,
  type MarketMode,
} from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS } from "@/lib/cache/daily";

/**
 * Public proof numbers for the landing page (recommendation count, closed
 * outcomes and win rate).
 *
 * Only aggregate counts are exposed — never a symbol, user id or trade level.
 * The result is cached for 24 hours per market and served from the Edge CDN when
 * the request URL explicitly selects `?market=`.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

type ProofStats = {
  recommendations: number | null;
  closed: number | null;
  win_rate: number | null;
};

async function fetchProofStats(market: MarketMode): Promise<ProofStats> {
  const db = getMarketSupabaseServiceClient(market, { cacheMarketData: true });
  const exchange = getMarketExchange(market);
  const [all, wins, losses] = await Promise.all([
    db
      .from("scan_results")
      .select("id", { count: "exact", head: true })
      .eq("is_public", true)
      .eq("exchange", exchange),
    db
      .from("scan_results")
      .select("id", { count: "exact", head: true })
      .eq("is_public", true)
      .eq("exchange", exchange)
      .eq("status", "win"),
    db
      .from("scan_results")
      .select("id", { count: "exact", head: true })
      .eq("is_public", true)
      .eq("exchange", exchange)
      .eq("status", "loss"),
  ]);

  const winCount = wins.count || 0;
  const lossCount = losses.count || 0;
  const closed = winCount + lossCount;

  return {
    recommendations: all.count || 0,
    closed,
    win_rate: closed > 0 ? Math.round((winCount / closed) * 100) : null,
  };
}

const loadEgxProofStats = unstable_cache(
  async (): Promise<ProofStats> => fetchProofStats("egx"),
  ["market-proof-stats-egx-v1"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.recommendations] }
);

const loadTasiProofStats = unstable_cache(
  async (): Promise<ProofStats> => fetchProofStats("tasi"),
  ["market-proof-stats-tasi-v1"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.recommendations] }
);

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const market = resolveRequestMarket(req);
    const explicitMarketParam =
      url.searchParams.has("market") ||
      url.searchParams.has("country") ||
      url.searchParams.has("exchange");

    const stats =
      market === "tasi" ? await loadTasiProofStats() : await loadEgxProofStats();

    const headers: Record<string, string> = explicitMarketParam
      ? {
          "Cache-Control": "public, max-age=3600",
          "Vercel-CDN-Cache-Control": "public, s-maxage=86400, stale-while-revalidate=86400",
          // Purged by the daily pipeline right after recommendations are
          // generated/evaluated, so 24 hours never means stale numbers.
          "Vercel-Cache-Tag": DAILY_CACHE_TAGS.recommendations,
        }
      : {
          "Cache-Control": "private, no-store, max-age=0",
          "Vercel-Cache-Tag": DAILY_CACHE_TAGS.recommendations,
        };

    return NextResponse.json(stats, { headers });
  } catch {
    return NextResponse.json(
      { recommendations: null, closed: null, win_rate: null },
      { status: 200, headers: { "Cache-Control": "private, no-store, max-age=0" } }
    );
  }
}
