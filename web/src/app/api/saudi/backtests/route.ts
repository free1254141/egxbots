import { NextResponse } from "next/server";
import { getMarketSupabaseClient } from "@/lib/supabase/route-data";

export const runtime = "nodejs";

export async function GET() {
  try {
    const saudiClient = getMarketSupabaseClient("tasi");
    const { data, error } = await saudiClient
      .from("market_cache")
      .select("payload")
      .eq("cache_key", "saudi_backtests_v1")
      .maybeSingle();

    if (error) {
      console.error("[SAUDI_BACKTESTS_API] Error fetching saudi_backtests_v1:", error);
      return NextResponse.json(
        { backtests: [], models: [] },
        { status: 500, headers: { "Cache-Control": "no-store" } },
      );
    }

    const rawPayload = data?.payload;
    const parsed = typeof rawPayload === "string" ? JSON.parse(rawPayload) : (rawPayload || {});
    const backtests = Array.isArray(parsed?.backtests) ? parsed.backtests : [];
    const models = Array.isArray(parsed?.models) ? parsed.models : [];

    return NextResponse.json(
      { backtests, models },
      {
        headers: {
          "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=7200",
        },
      },
    );
  } catch (err) {
    console.error("[SAUDI_BACKTESTS_API] Unexpected error:", err);
    return NextResponse.json(
      { backtests: [], models: [] },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
