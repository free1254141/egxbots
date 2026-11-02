import { NextResponse } from "next/server";
import { getCachedFairValueReport } from "@/lib/market/fair-value-server";
import { DAILY_CACHE_TAGS, dailyCacheHeaders } from "@/lib/cache/daily";

export const runtime = "nodejs";
export const revalidate = 86400;
export const preferredRegion = "fra1";

export async function GET() {
  try {
    const report = await getCachedFairValueReport();

    return NextResponse.json(report, {
      headers: dailyCacheHeaders(DAILY_CACHE_TAGS.market),
    });
  } catch (err) {
    console.error("[api/market/fair-value] error:", err);
    return NextResponse.json(
      { error: "Failed to load market valuation data" },
      { status: 503 }
    );
  }
}
