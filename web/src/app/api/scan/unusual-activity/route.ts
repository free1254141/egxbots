import { NextRequest, NextResponse } from "next/server";
import { unstable_cache } from "next/cache";
import {
  resolveRequestMarket,
  getMarketExchange,
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

async function fetchUnusualIndicators(supabase: any, exchange: string, asOf: string) {
  const attempts = [
    "symbol,close,change_pct,rsi_14,r_vol,vol_sma20,volume,egx_ai_score",
    "symbol,close,change_pct,rsi_14,r_vol,vol_sma20,volume",
    "symbol,close,change_pct,rsi_14,r_vol,volume_sma_20,volume",
    "symbol,close,change_pct,rsi_14,volume_sma_20,volume",
  ];
  let lastError: any = null;
  for (const selectFields of attempts) {
    const res = await supabase
      .from("stock_technical_indicators")
      .select(selectFields)
      .eq("exchange", exchange)
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
  const currency = market === "tasi" ? "SAR" : "EGP";

  const { data: latestRows, error: latestError } = await supabase
    .from("stock_technical_indicators")
    .select("date")
    .eq("exchange", exchange)
    .order("date", { ascending: false })
    .limit(1);
  if (latestError) throw latestError;
  const asOf = latestRows?.[0]?.date ? String(latestRows[0].date).slice(0, 10) : null;
  if (!asOf) {
    return { asOf: null, exchange, currency, coverage: 0, totalMatches: 0, threshold: MIN_RELATIVE_VOLUME, rows: [] };
  }

  const { data: indicators, error: indicatorsError } = await fetchUnusualIndicators(supabase, exchange, asOf);
  if (indicatorsError) throw indicatorsError;

  const bySymbol = new Map<string, any>();
  for (const row of indicators || []) {
    if (row.symbol) bySymbol.set(String(row.symbol), row);
  }
  const unusual = [...bySymbol.values()]
    .map((row) => {
      const avgVol = finite(row.vol_sma20 ?? row.volume_sma_20) ?? 0;
      const vol = finite(row.volume) ?? 0;
      const rVol = finite(row.r_vol) ?? (avgVol > 0 && vol > 0 ? vol / avgVol : 0);
      return { ...row, _resolvedRVol: rVol, _resolvedAvgVol: avgVol, _resolvedVol: vol };
    })
    .filter((row) => row._resolvedRVol >= MIN_RELATIVE_VOLUME && row._resolvedAvgVol > 0 && row._resolvedVol > 0)
    .sort((a, b) => b._resolvedRVol - a._resolvedRVol);
  const candidates = unusual.slice(0, MAX_RESULTS);

  const history = new Map<string, Array<{ date: string; high: number | string | null }>>();
  const nameMap = new Map<string, string>();
  if (candidates.length) {
    const candidateSymbols = candidates.map((row) => row.symbol);
    const from = new Date(Date.parse(`${asOf}T00:00:00Z`) - 75 * 86_400_000).toISOString().slice(0, 10);
    const { data: bars, error: barsError } = await supabase
      .from("stock_prices")
      .select("symbol,date,high")
      .eq("exchange", exchange)
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

    if (market === "tasi") {
      let { data: stockNames, error: namesErr } = await supabase
        .from("stocks")
        .select("symbol,name_ar,name")
        .eq("exchange", exchange)
        .in("symbol", candidateSymbols)
        .limit(candidateSymbols.length);
      if (namesErr) {
        ({ data: stockNames } = await supabase
          .from("stocks")
          .select("symbol,name")
          .eq("exchange", exchange)
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

  return { asOf, exchange, currency, coverage: bySymbol.size, totalMatches: unusual.length, threshold: MIN_RELATIVE_VOLUME, rows };
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
