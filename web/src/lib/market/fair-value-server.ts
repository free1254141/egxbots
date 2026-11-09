import { unstable_cache } from "next/cache";
import { getPublicMarketClient } from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS } from "@/lib/cache/daily";
import { computeFairValueReport, type FairValueReport } from "./fair-value";

async function fetchAndComputeFairValueReport(): Promise<FairValueReport> {
  const client = getPublicMarketClient();

  // Order by date descending so the latest session row for each symbol comes first
  const [fundRes, indRes] = await Promise.all([
    client
      .from("stock_fundamentals")
      .select("symbol, name, name_ar, data, updated_at")
      .eq("exchange", "EGX")
      .limit(400),
    client
      .from("stock_technical_indicators")
      .select(
        "symbol, date, close, volume, ema_50, ema_200, sma_200, vwap_20, change_pct, rsi_14"
      )
      .eq("exchange", "EGX")
      .order("date", { ascending: false })
      .limit(400),
  ]);

  if (fundRes.error) {
    throw new Error(`Failed to fetch stock_fundamentals: ${fundRes.error.message}`);
  }
  if (indRes.error) {
    throw new Error(
      `Failed to fetch stock_technical_indicators: ${indRes.error.message}`
    );
  }

  return computeFairValueReport(fundRes.data || [], indRes.data || []);
}

/**
 * Cached daily on Vercel Data Cache + Runtime Cache.
 * Automatically revalidated when the 2nd daily bot run (phase="close") finishes
 * and invalidates DAILY_CACHE_TAGS.market ("daily-market-data").
 */
export const getCachedFairValueReport = unstable_cache(
  fetchAndComputeFairValueReport,
  ["fair-value-egx-daily-v3"],
  {
    revalidate: 86400,
    tags: [DAILY_CACHE_TAGS.market],
  }
);
