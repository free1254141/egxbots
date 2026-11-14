import { unstable_cache } from "next/cache";
import {
  getMarketSupabaseClient,
  getPublicMarketClient,
  type MarketMode,
} from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS } from "@/lib/cache/daily";
import { computeFairValueReport, type FairValueReport } from "./fair-value";

async function fetchAndComputeFairValueReport(
  market: MarketMode = "egx"
): Promise<FairValueReport> {
  const isTasi = market === "tasi";
  const client = isTasi
    ? getMarketSupabaseClient("tasi")
    : getPublicMarketClient();

  const fundQuery = client
    .from("stock_fundamentals")
    .select("symbol, name, name_ar, data, updated_at");
  const indQuery = client
    .from("stock_technical_indicators")
    .select(
      "symbol, date, close, volume, ema_50, ema_200, sma_200, vwap_20, change_pct, rsi_14"
    );

  // Order by date descending so the latest session row for each symbol comes first
  const [fundRes, indRes] = await Promise.all([
    (isTasi
      ? fundQuery.in("exchange", ["TADAWUL", "TASI"])
      : fundQuery.eq("exchange", "EGX")
    ).limit(400),
    (isTasi
      ? indQuery.in("exchange", ["TADAWUL", "TASI"])
      : indQuery.eq("exchange", "EGX")
    )
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

  return computeFairValueReport(fundRes.data || [], indRes.data || [], market);
}

const getCachedEgxFairValueReport = unstable_cache(
  () => fetchAndComputeFairValueReport("egx"),
  ["fair-value-egx-daily-v3"],
  {
    revalidate: 86400,
    tags: [DAILY_CACHE_TAGS.market],
  }
);

const getCachedTasiFairValueReport = unstable_cache(
  () => fetchAndComputeFairValueReport("tasi"),
  ["fair-value-tasi-daily-v1"],
  {
    revalidate: 86400,
    tags: [DAILY_CACHE_TAGS.market],
  }
);

/**
 * Cached daily on Vercel Data Cache + Runtime Cache.
 * Automatically revalidated when the 2nd daily bot run (phase="close") finishes
 * and invalidates DAILY_CACHE_TAGS.market ("daily-market-data").
 */
export async function getCachedFairValueReport(
  market: MarketMode = "egx"
): Promise<FairValueReport> {
  return market === "tasi"
    ? getCachedTasiFairValueReport()
    : getCachedEgxFairValueReport();
}
