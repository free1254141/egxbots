import { NextResponse } from "next/server";
import { unstable_cache } from "next/cache";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS } from "@/lib/cache/daily";

/**
 * Public proof numbers for the landing page (recommendation count, closed
 * outcomes and win rate).
 *
 * Only aggregate counts are exposed — never a symbol, user id or trade level.
 * The result is cached for 24 hours and served from the Edge CDN, so the
 * landing page can show verifiable numbers instead of vague claims without
 * adding a per-visitor database read. The daily pipeline purges the
 * `daily-recommendations` tag, so "24 hours" never means stale numbers.
 */
export const runtime = "nodejs";
export const revalidate = 86400;
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

type ProofStats = {
  recommendations: number | null;
  closed: number | null;
  win_rate: number | null;
};

const loadProofStats = unstable_cache(
  async (): Promise<ProofStats> => {
    const db = getSupabaseServiceClient({ cacheMarketData: true });
    const [all, wins, losses] = await Promise.all([
      db.from("scan_results").select("id", { count: "exact", head: true }).eq("is_public", true),
      db.from("scan_results").select("id", { count: "exact", head: true }).eq("is_public", true).eq("status", "win"),
      db.from("scan_results").select("id", { count: "exact", head: true }).eq("is_public", true).eq("status", "loss"),
    ]);

    const winCount = wins.count || 0;
    const lossCount = losses.count || 0;
    const closed = winCount + lossCount;

    return {
      recommendations: all.count || 0,
      closed,
      win_rate: closed > 0 ? Math.round((winCount / closed) * 100) : null,
    };
  },
  ["market-proof-stats-v1"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.recommendations] }
);

export async function GET() {
  try {
    const stats = await loadProofStats();
    return NextResponse.json(stats, {
      headers: {
        "Cache-Control": "public, max-age=3600",
        "Vercel-CDN-Cache-Control": "public, s-maxage=86400, stale-while-revalidate=86400",
        // Purged by the daily pipeline right after recommendations are
        // generated/evaluated, so 24 hours never means stale numbers.
        "Vercel-Cache-Tag": DAILY_CACHE_TAGS.recommendations,
      },
    });
  } catch {
    return NextResponse.json(
      { recommendations: null, closed: null, win_rate: null },
      { status: 200, headers: { "Cache-Control": "public, max-age=60" } }
    );
  }
}
