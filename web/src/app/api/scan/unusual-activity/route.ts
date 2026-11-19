import { NextRequest, NextResponse } from "next/server";
import { unstable_cache } from "next/cache";
import {
  resolveRequestMarket,
  getMarketExchange,
  getMarketExchanges,
  getMarketSupabaseServiceClient,
  type MarketMode,
} from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS, dailyCacheHeaders } from "@/lib/cache/daily";
import { priorTwentySessionHigh } from "@/lib/unusualActivity";
import { CANONICAL_STOCK_NAMES } from "@/lib/ai/stock-names";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

const MIN_RELATIVE_VOLUME = 2;
const MAX_RESULTS = 15;

function finite(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

async function fetchUnusualIndicators(supabase: any, exchanges: string[], asOf: string) {
  const attempts = [
    "symbol,exchange,close,change_pct,rsi_14,r_vol,vol_sma20,volume,egx_ai_score",
    "symbol,exchange,close,change_pct,rsi_14,r_vol,vol_sma20,volume",
    "symbol,close,change_pct,rsi_14,r_vol,volume_sma_20,volume",
    "symbol,close,change_pct,rsi_14,volume_sma_20,volume",
  ];
  let lastError: any = null;
  for (const selectFields of attempts) {
    const res = await supabase
      .from("stock_technical_indicators")
      .select(selectFields)
      .in("exchange", exchanges)
      .eq("date", asOf)
      .limit(1000);
    if (!res.error) return res;
    lastError = res.error;
  }
  return { data: null, error: lastError };
}

async function loadUnusualActivity(market: MarketMode) {
  const supabase = getMarketSupabaseServiceClient(market, { cacheMarketData: true });
  const exchange = getMarketExchange(market);
  const exchanges = getMarketExchanges(market);
  const currency =
    market === "uae" ? "AED" : market === "qatar" ? "QAR" : market === "tasi" ? "SAR" : "EGP";

  const { data: latestRows, error: latestError } = await supabase
    .from("stock_technical_indicators")
    .select("date")
    .in("exchange", exchanges)
    .order("date", { ascending: false })
    .limit(1);
  if (latestError) throw latestError;
  const asOf = latestRows?.[0]?.date ? String(latestRows[0].date).slice(0, 10) : null;
  if (!asOf) {
    return { asOf: null, exchange, currency, coverage: 0, totalMatches: 0, threshold: MIN_RELATIVE_VOLUME, rows: [] };
  }

  const { data: indicators, error: indicatorsError } = await fetchUnusualIndicators(supabase, exchanges, asOf);
  if (indicatorsError) throw indicatorsError;

  const bySymbol = new Map<string, any>();
  for (const row of indicators || []) {
    if (row.symbol) bySymbol.set(String(row.symbol), row);
  }
  const enriched = [...bySymbol.values()]
    .map((row) => {
      const avgVol = finite(row.vol_sma20 ?? row.volume_sma_20) ?? 0;
      const vol = finite(row.volume) ?? 0;
      const rVol = finite(row.r_vol) ?? (avgVol > 0 && vol > 0 ? vol / avgVol : 0);
      return { ...row, _resolvedRVol: rVol, _resolvedAvgVol: avgVol, _resolvedVol: vol };
    })
    .filter((row) => row._resolvedAvgVol > 0 && row._resolvedVol > 0);

  let effectiveThreshold = MIN_RELATIVE_VOLUME;
  let unusual = enriched
    .filter((row) => row._resolvedRVol >= effectiveThreshold)
    .sort((a, b) => b._resolvedRVol - a._resolvedRVol);
  if ((market === "uae" || market === "qatar") && unusual.length < 3) {
    effectiveThreshold = 1.25;
    unusual = enriched
      .filter((row) => row._resolvedRVol >= effectiveThreshold)
      .sort((a, b) => b._resolvedRVol - a._resolvedRVol);
  }
  const candidates = unusual.slice(0, MAX_RESULTS);

  const history = new Map<string, Array<{ date: string; high: number | string | null }>>();
  const nameMap = new Map<string, string>();
  if (candidates.length) {
    const candidateSymbols = candidates.map((row) => row.symbol);
    const from = new Date(Date.parse(`${asOf}T00:00:00Z`) - 75 * 86_400_000).toISOString().slice(0, 10);
    const { data: bars, error: barsError } = await supabase
      .from("stock_prices")
      .select("symbol,date,high")
      .in("exchange", exchanges)
      .in("symbol", candidateSymbols)
      .gte("date", from)
      .lt("date", asOf)
      .order("date", { ascending: false })
      .limit(1000);
    if (barsError) throw barsError;
    for (const bar of bars || []) {
      const symbol = String(bar.symbol);
      const items = history.get(symbol) || [];
      items.push({ date: String(bar.date).slice(0, 10), high: bar.high });
      history.set(symbol, items);
    }

    if (market !== "egx") {
      let { data: stockNames, error: namesErr } = await supabase
        .from("stocks")
        .select("symbol,name_ar,name")
        .in("exchange", exchanges)
        .in("symbol", candidateSymbols)
        .limit(candidateSymbols.length);
      if (namesErr) {
        ({ data: stockNames } = await supabase
          .from("stocks")
          .select("symbol,name")
          .in("exchange", exchanges)
          .in("symbol", candidateSymbols)
          .limit(candidateSymbols.length));
      }
      for (const s of stockNames || []) {
        const symKey = String(s?.symbol || "").trim().toUpperCase();
        const label = s?.name_ar || s?.name;
        if (symKey && label) nameMap.set(symKey, String(label));
      }
    }
  }

  const rows = candidates.map((row) => {
    const symbol = String(row.symbol);
    const symKey = symbol.trim().toUpperCase();
    const close = finite(row.close);
    const resistance = priorTwentySessionHigh(history.get(symbol) || [], asOf);
    const score = finite(row.egx_ai_score);
    return {
      symbol,
      exchange: String(row.exchange || exchange),
      nameAr: nameMap.get(symKey) || CANONICAL_STOCK_NAMES[symKey]?.name_ar || symbol,
      relativeVolume: Number(row._resolvedRVol),
      close,
      changePct: finite(row.change_pct),
      rsi: finite(row.rsi_14),
      aiScore: score !== null && score >= 0 && score <= 1 ? score * 100 : null,
      resistance,
      distanceToResistancePct: resistance && close !== null ? ((resistance - close) / resistance) * 100 : null,
    };
  });

  return { asOf, exchange, currency, coverage: bySymbol.size, totalMatches: unusual.length, threshold: effectiveThreshold, rows };
}

const getCachedEgxUnusualActivity = unstable_cache(
  async () => loadUnusualActivity("egx"),
  ["unusual-activity-egx-daily"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market] }
);

const getCachedTasiUnusualActivity = unstable_cache(
  async () => loadUnusualActivity("tasi"),
  ["unusual-activity-tasi-daily"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market] }
);

const getCachedUaeUnusualActivity = unstable_cache(
  async () => loadUnusualActivity("uae"),
  ["unusual-activity-uae-daily"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market] }
);

const getCachedQatarUnusualActivity = unstable_cache(
  async () => loadUnusualActivity("qatar"),
  ["unusual-activity-qatar-daily"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market] }
);

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const market = resolveRequestMarket(req);
    const explicitMarketParam =
      url.searchParams.has("market") ||
      url.searchParams.has("country") ||
      url.searchParams.has("exchange");
    const payload =
      market === "tasi"
        ? await getCachedTasiUnusualActivity()
        : market === "uae"
          ? await getCachedUaeUnusualActivity()
          : market === "qatar"
            ? await getCachedQatarUnusualActivity()
            : await getCachedEgxUnusualActivity();
    const headers = explicitMarketParam
      ? dailyCacheHeaders(DAILY_CACHE_TAGS.market)
      : {
          "Cache-Control": "private, no-store, max-age=0",
          "Vercel-Cache-Tag": DAILY_CACHE_TAGS.market,
        };
    return NextResponse.json(payload, { headers });
  } catch (error) {
    console.error("[UNUSUAL_ACTIVITY] Failed to load latest technical snapshot", error);
    return NextResponse.json({ error: "Unusual activity is temporarily unavailable." }, { status: 503 });
  }
}
