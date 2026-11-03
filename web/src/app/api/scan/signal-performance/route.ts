import { NextResponse } from "next/server";
import { unstable_cache } from "next/cache";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS, dailyCacheHeaders } from "@/lib/cache/daily";

export const runtime = "nodejs";
export const revalidate = 3600;
export const preferredRegion = "fra1";

export interface SignalWinSummary {
  events: number;
  winRate: number | null;
  hitRate3d: number | null;
  avgRet1: number | null;
  avgBest3d: number | null;
}

export interface SignalReviewRow {
  symbol: string;
  signalClose: number | null;
  nextClose: number | null;
  nextHigh: number | null;
  nextLow?: number | null;
  retPct: number | null;
  intradayHighPct?: number | null;
  intradayLowPct?: number | null;
  relativeVolume?: number | null;
  wickPct?: number | null;
  conviction?: number | null;
}

export interface SignalPerformancePayload {
  ok: boolean;
  asOf: string | null;
  updatedAt: string;
  windowSessions: number;
  windowStart: string | null;
  methodology: {
    unusual: string;
    win: string;
    hit3d: string;
  };
  unusual: SignalWinSummary;
  springs: SignalWinSummary;
  upthrusts: SignalWinSummary;
  review?: {
    signalDate: string | null;
    outcomeDate: string | null;
    trapsSource?: string;
    unusual: SignalReviewRow[];
    unusualScore: { total: number; wins: number };
    springs: SignalReviewRow[];
    springsScore: { total: number; wins: number };
    upthrusts: SignalReviewRow[];
    upthrustsScore: { total: number; wins: number };
    topMover: (SignalReviewRow & { symbol: string }) | null;
  };
}

const getCachedSignalPerformance = unstable_cache(
  async (): Promise<SignalPerformancePayload | null> => {
    try {
      const supabase = getSupabaseServiceClient({ cacheMarketData: true });
      const { data, error } = await supabase
        .from("market_cache")
        .select("payload, computed_at")
        .eq("cache_key", "signal_performance_EGX")
        .order("computed_at", { ascending: false })
        .limit(1);

      if (error) {
        console.warn("[signal-performance] Supabase error:", error.message);
        return null;
      }

      const row = data?.[0];
      if (row?.payload && typeof row.payload === "object") {
        return row.payload as SignalPerformancePayload;
      }
      return null;
    } catch (err) {
      console.warn("[signal-performance] Fetch fallback:", err);
      return null;
    }
  },
  ["signal-performance-egx-daily"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market] }
);

export async function GET() {
  try {
    const payload = await getCachedSignalPerformance();
    if (!payload) {
      return NextResponse.json(
        { ok: false, message: "Signal performance stats are not yet computed." },
        { status: 404 }
      );
    }
    return NextResponse.json(payload, { headers: dailyCacheHeaders(DAILY_CACHE_TAGS.market) });
  } catch (error) {
    console.error("[SIGNAL_PERFORMANCE] Failed to load signal performance stats", error);
    return NextResponse.json(
      { ok: false, error: "Signal performance service temporarily unavailable." },
      { status: 503 }
    );
  }
}
