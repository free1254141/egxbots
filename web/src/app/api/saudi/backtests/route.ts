import { NextResponse } from "next/server";
import { unstable_cache } from "next/cache";
import { getMarketSupabaseClient } from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS, dailyCacheHeaders } from "@/lib/cache/daily";

export const runtime = "nodejs";
export const revalidate = 86400;
export const preferredRegion = "fra1";

const getCachedSaudiBacktests = unstable_cache(
  async () => {
    const saudiClient = getMarketSupabaseClient("tasi");
    const { data, error } = await saudiClient
      .from("market_cache")
      .select("payload")
      .eq("cache_key", "saudi_backtests_v1")
      .maybeSingle();

    if (error) {
      throw error;
    }

    const rawPayload = data?.payload;
    const parsed = typeof rawPayload === "string" ? JSON.parse(rawPayload) : (rawPayload || {});
    return {
      backtests: Array.isArray(parsed?.backtests) ? parsed.backtests : [],
      models: Array.isArray(parsed?.models) ? parsed.models : [],
    };
  },
  ["saudi-backtests-v1"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market] },
);

export async function GET() {
  try {
    const result = await getCachedSaudiBacktests();
    return NextResponse.json(result, {
      headers: dailyCacheHeaders(DAILY_CACHE_TAGS.market),
    });
  } catch (err) {
    console.error("[SAUDI_BACKTESTS_API] Unexpected error:", err);
    return NextResponse.json(
      { backtests: [], models: [] },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
