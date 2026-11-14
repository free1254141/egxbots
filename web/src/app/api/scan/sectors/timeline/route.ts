import { NextRequest, NextResponse } from "next/server";
import {
  resolveRequestMarket,
  getMarketSupabaseClient,
} from "@/lib/supabase/route-data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

export async function GET(req: NextRequest) {
  const incomingUrl = new URL(req.url);
  const market = resolveRequestMarket(req, incomingUrl.searchParams.get("country"));
  const country = market === "tasi" ? "Saudi Arabia" : "Egypt";
  const explicitMarketParam =
    incomingUrl.searchParams.has("country") ||
    incomingUrl.searchParams.has("market") ||
    incomingUrl.searchParams.has("exchange");
  const months = Number(incomingUrl.searchParams.get("months") || 6);
  const safeMonths = Number.isFinite(months) && months > 0 ? months : 6;
  const cacheKey = `sector_timeline_${safeMonths}m`;

  try {
    const supabase = getMarketSupabaseClient(market);

    const { data: cached, error } = await supabase
      .from("market_cache")
      .select("payload, computed_at")
      .eq("cache_key", cacheKey)
      .eq("country", country)
      .order("computed_at", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error) {
      console.error("Timeline cache fetch error:", error);
    }

    if (cached?.payload) {
      const payload =
        typeof cached.payload === "string"
          ? JSON.parse(cached.payload)
          : cached.payload;
      return NextResponse.json(
        {
          ...payload,
          market,
          country,
          cached: true,
          computed_at: cached.computed_at,
        },
        {
          headers: {
            "Cache-Control": explicitMarketParam
              ? "public, s-maxage=3600, stale-while-revalidate=86400"
              : "private, no-store, max-age=0",
          },
        },
      );
    }

    // No cached data yet — return empty structure (backend will populate on next daily run)
    return NextResponse.json(
      {
        months: [],
        monthly: [],
        sectors: [],
        market,
        country,
        cached: false,
        computed_at: null,
      },
      {
        headers: {
          "Cache-Control": explicitMarketParam
            ? "public, s-maxage=60, stale-while-revalidate=120"
            : "private, no-store, max-age=0",
        },
      },
    );
  } catch (error: any) {
    console.error("Timeline API error:", error);
    return NextResponse.json(
      {
        months: [],
        monthly: [],
        sectors: [],
        market,
        country,
        cached: false,
        error: "Failed to load timeline data",
      },
      { status: 200, headers: { "Cache-Control": "private, no-store, max-age=0" } },
    );
  }
}
