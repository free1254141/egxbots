import { unstable_cache } from "next/cache";
import {
  getMarketSupabaseClient,
  getPublicMarketClient,
  type MarketMode,
} from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS } from "@/lib/cache/daily";
import { computeFairValueReport, type FairValueReport } from "./fair-value";
import { fetchHfPublicJson } from "@/lib/hf-public-read";

async function fetchAndComputeFairValueReport(
  market: MarketMode = "egx"
): Promise<FairValueReport> {
  const hf = await fetchHfPublicJson<FairValueReport>(
    `/api/public/fair-value-report?market=${market}`,
    604800,
    5000,
    [DAILY_CACHE_TAGS.market]
  );
  if (hf && Array.isArray(hf.stocks) && hf.stocks.length > 0) {
    return hf;
  }
  const isGcc = market === "tasi" || market === "uae" || market === "qatar";
  const exchanges =
    market === "tasi"
      ? ["TADAWUL", "TASI"]
      : market === "uae"
      ? ["DFM", "ADX"]
      : market === "qatar"
      ? ["QSE"]
      : ["EGX"];
  const client = isGcc
    ? getMarketSupabaseClient(market)
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
    fundQuery.in("exchange", exchanges).limit(400),
    indQuery
      .in("exchange", exchanges)
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
    revalidate: 604800,
    tags: [DAILY_CACHE_TAGS.market],
  }
);

const getCachedTasiFairValueReport = unstable_cache(
  () => fetchAndComputeFairValueReport("tasi"),
  ["fair-value-tasi-daily-v1"],
  {
    revalidate: 604800,
    tags: [DAILY_CACHE_TAGS.market],
  }
);

const getCachedUaeFairValueReport = unstable_cache(
  () => fetchAndComputeFairValueReport("uae"),
  ["fair-value-uae-daily-v1"],
  {
    revalidate: 604800,
    tags: [DAILY_CACHE_TAGS.market],
  }
);

const getCachedQatarFairValueReport = unstable_cache(
  () => fetchAndComputeFairValueReport("qatar"),
  ["fair-value-qatar-daily-v1"],
  {
    revalidate: 604800,
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
  if (market === "tasi") return getCachedTasiFairValueReport();
  if (market === "uae") return getCachedUaeFairValueReport();
  if (market === "qatar") return getCachedQatarFairValueReport();
  return getCachedEgxFairValueReport();
}
