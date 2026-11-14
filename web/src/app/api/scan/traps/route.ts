import { NextRequest, NextResponse } from "next/server";
import { unstable_cache } from "next/cache";
import {
  resolveRequestMarket,
  getMarketExchange,
  getMarketSupabaseServiceClient,
  type MarketMode,
} from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS, dailyCacheHeaders } from "@/lib/cache/daily";
import { CANONICAL_STOCK_NAMES } from "@/lib/ai/stock-names";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1";

export interface TrapSignalRow {
  symbol: string;
  nameAr: string;
  trapType: "BEAR_TRAP" | "BULL_TRAP";
  close: number;
  low: number;
  high: number;
  keyLevel: number;
  wickPct: number;
  relativeVolume: number;
  changePct: number | null;
  rsi: number | null;
  aiScore: number | null;
  conviction: number;
}

export interface TrapsSnapshot {
  asOf: string | null;
  exchange?: string;
  currency?: string;
  bearTraps: TrapSignalRow[];
  bullTraps: TrapSignalRow[];
  totalBearTraps: number;
  totalBullTraps: number;
}

function finite(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

async function fetchTrapsIndicators(supabase: any, exchange: string, asOf: string) {
  const attempts = [
    "symbol,close,change_pct,rsi_14,r_vol,ema_20,sma_20,bb_upper,bb_lower,egx_ai_score",
    "symbol,close,change_pct,rsi_14,r_vol,ema_20,sma_20,bb_upper,bb_lower",
    "symbol,close,change_pct,rsi_14,r_vol,ema_20,sma_20",
    "symbol,close,change_pct,rsi_14,ema_20",
  ];
  let lastError: any = null;
  for (const selectFields of attempts) {
    const res = await supabase
      .from("stock_technical_indicators")
      .select(selectFields)
      .eq("exchange", exchange)
      .eq("date", asOf)
      .limit(500);
    if (!res.error) return res;
    lastError = res.error;
  }
  return { data: null, error: lastError };
}

async function loadTrapsSnapshot(market: MarketMode): Promise<TrapsSnapshot> {
  const supabase = getMarketSupabaseServiceClient(market, { cacheMarketData: true });
  const exchange = getMarketExchange(market);
  const currency = market === "tasi" ? "SAR" : "EGP";
  const cacheKeys =
    market === "tasi"
      ? ["scanner_traps_TADAWUL", "scanner_traps_TASI", "daily_traps_snapshot_tasi"]
      : ["scanner_traps_EGX", "daily_traps_snapshot"];

  // 1. Try precomputed daily traps cache first
  try {
    const { data: cacheRows } = await supabase
      .from("market_cache")
      .select("payload, computed_at")
      .in("cache_key", cacheKeys)
      .order("computed_at", { ascending: false })
      .limit(1);

    const cacheRow = cacheRows?.[0];

    if (
      cacheRow?.payload &&
      Array.isArray(cacheRow.payload.bearTraps) &&
      (cacheRow.payload.bearTraps.length > 0 || (cacheRow.payload.bullTraps || []).length > 0)
    ) {
      return {
        asOf: cacheRow.payload.asOf || null,
        exchange,
        currency,
        bearTraps: cacheRow.payload.bearTraps.slice(0, 8),
        bullTraps: (cacheRow.payload.bullTraps || []).slice(0, 8),
        totalBearTraps: cacheRow.payload.totalBearTraps ?? cacheRow.payload.bearTraps.length,
        totalBullTraps: cacheRow.payload.totalBullTraps ?? (cacheRow.payload.bullTraps || []).length,
      };
    }
  } catch (e) {
    console.warn(`[api/scan/traps:${market}] market_cache read fallback:`, e);
  }

  const { data: latestRows, error: latestError } = await supabase
    .from("stock_technical_indicators")
    .select("date")
    .eq("exchange", exchange)
    .order("date", { ascending: false })
    .limit(1);
  if (latestError) throw latestError;

  const asOf = latestRows?.[0]?.date ? String(latestRows[0].date).slice(0, 10) : null;
  if (!asOf) {
    return { asOf: null, exchange, currency, bearTraps: [], bullTraps: [], totalBearTraps: 0, totalBullTraps: 0 };
  }

  const [indRes, barsRes] = await Promise.all([
    fetchTrapsIndicators(supabase, exchange, asOf),
    supabase
      .from("stock_prices")
      .select("symbol,open,high,low,close")
      .eq("exchange", exchange)
      .eq("date", asOf)
      .limit(500),
  ]);

  if (indRes.error) throw indRes.error;
  if (barsRes.error) throw barsRes.error;

  const barsBySym = new Map<string, any>();
  for (const b of barsRes.data || []) {
    if (b.symbol) barsBySym.set(String(b.symbol).trim().toUpperCase(), b);
  }

  const bearTraps: TrapSignalRow[] = [];
  const bullTraps: TrapSignalRow[] = [];

  for (const ind of indRes.data || []) {
    const sym = String(ind.symbol || "").trim().toUpperCase();
    if (!sym) continue;
    const bar = barsBySym.get(sym);
    if (!bar) continue;

    const high = finite(bar.high);
    const low = finite(bar.low);
    const close = finite(bar.close) ?? finite(ind.close);
    if (!high || !low || !close || close <= 0 || high <= low) continue;

    const rng = high - low;
    if ((rng / close) * 100 < 1.5) continue;

    const recoveryRatio = (close - low) / rng;
    const rejectionRatio = (high - close) / rng;
    const rVol = finite(ind.r_vol) ?? 1.0;
    const rsi = finite(ind.rsi_14);
    const changePct = finite(ind.change_pct);
    const sma20 = finite(ind.sma_20) ?? finite(ind.ema_20) ?? close;
    const bbLower = finite(ind.bb_lower) ?? sma20 * 0.95;
    const bbUpper = finite(ind.bb_upper) ?? sma20 * 1.05;
    const aiRaw = finite(ind.egx_ai_score);
    const aiScore = aiRaw !== null && aiRaw >= 0 && aiRaw <= 1 ? Math.round(aiRaw * 100) : aiRaw;
    const nameAr = CANONICAL_STOCK_NAMES[sym]?.name_ar || sym;

    // Bear Trap (Wyckoff Spring / Fake Breakdown & Reclaim)
    const supportRef = Math.abs(low - bbLower) < Math.abs(low - sma20) ? bbLower : sma20;
    if (low <= supportRef * 1.005 && close >= supportRef * 0.992 && recoveryRatio >= 0.62 && rVol >= 0.8) {
      const conviction = Math.min(99, Number((recoveryRatio * 65 + Math.min(rVol, 3.0) * 11).toFixed(1)));
      bearTraps.push({
        symbol: sym,
        nameAr,
        trapType: "BEAR_TRAP",
        close: Number(close.toFixed(2)),
        low: Number(low.toFixed(2)),
        high: Number(high.toFixed(2)),
        keyLevel: Number(supportRef.toFixed(2)),
        wickPct: Number((recoveryRatio * 100).toFixed(1)),
        relativeVolume: Number(rVol.toFixed(2)),
        changePct: changePct !== null ? Number(changePct.toFixed(2)) : null,
        rsi: rsi !== null ? Number(rsi.toFixed(1)) : null,
        aiScore,
        conviction,
      });
      continue;
    }

    // Bull Trap (Wyckoff Upthrust / Fake Breakout & Rejection)
    const resistanceRef = high >= bbUpper * 0.985 ? bbUpper : sma20 * 1.015;
    if (high >= resistanceRef && close < resistanceRef * 0.998 && rejectionRatio >= 0.62 && rVol >= 0.8) {
      const conviction = Math.min(99, Number((rejectionRatio * 65 + Math.min(rVol, 3.0) * 11).toFixed(1)));
      bullTraps.push({
        symbol: sym,
        nameAr,
        trapType: "BULL_TRAP",
        close: Number(close.toFixed(2)),
        low: Number(low.toFixed(2)),
        high: Number(high.toFixed(2)),
        keyLevel: Number(resistanceRef.toFixed(2)),
        wickPct: Number((rejectionRatio * 100).toFixed(1)),
        relativeVolume: Number(rVol.toFixed(2)),
        changePct: changePct !== null ? Number(changePct.toFixed(2)) : null,
        rsi: rsi !== null ? Number(rsi.toFixed(1)) : null,
        aiScore,
        conviction,
      });
    }
  }

  bearTraps.sort((a, b) => b.conviction - a.conviction);
  bullTraps.sort((a, b) => b.conviction - a.conviction);

  const topBear = bearTraps.slice(0, 8);
  const topBull = bullTraps.slice(0, 8);

  if (market === "tasi" && (topBear.length > 0 || topBull.length > 0)) {
    const matchedSyms = Array.from(new Set([...topBear, ...topBull].map((r) => r.symbol)));
    let { data: stockNames, error: namesErr } = await supabase
      .from("stocks")
      .select("symbol,name_ar,name")
      .eq("exchange", exchange)
      .in("symbol", matchedSyms)
      .limit(matchedSyms.length);
    if (namesErr) {
      ({ data: stockNames } = await supabase
        .from("stocks")
        .select("symbol,name")
        .eq("exchange", exchange)
        .in("symbol", matchedSyms)
        .limit(matchedSyms.length));
    }
    const nameMap = new Map<string, string>();
    for (const s of stockNames || []) {
      const symKey = String(s?.symbol || "").trim().toUpperCase();
      const label = s?.name_ar || s?.name;
      if (symKey && label) nameMap.set(symKey, String(label));
    }
    for (const row of [...topBear, ...topBull]) {
      row.nameAr = nameMap.get(row.symbol) || CANONICAL_STOCK_NAMES[row.symbol]?.name_ar || row.symbol;
    }
  }

  return {
    asOf,
    exchange,
    currency,
    bearTraps: topBear,
    bullTraps: topBull,
    totalBearTraps: bearTraps.length,
    totalBullTraps: bullTraps.length,
  };
}

const getCachedEgxTrapsSnapshot = unstable_cache(
  async (): Promise<TrapsSnapshot> => loadTrapsSnapshot("egx"),
  ["trap-detector-egx-daily"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market] }
);

const getCachedTasiTrapsSnapshot = unstable_cache(
  async (): Promise<TrapsSnapshot> => loadTrapsSnapshot("tasi"),
  ["trap-detector-tasi-daily"],
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
        ? await getCachedTasiTrapsSnapshot()
        : await getCachedEgxTrapsSnapshot();
    const headers = explicitMarketParam
      ? dailyCacheHeaders(DAILY_CACHE_TAGS.market)
      : {
          "Cache-Control": "private, no-store, max-age=0",
          "Vercel-Cache-Tag": DAILY_CACHE_TAGS.market,
        };
    return NextResponse.json(payload, { headers });
  } catch (error) {
    console.error("[TRAP_DETECTOR] Failed to load latest trap signals", error);
    return NextResponse.json({ error: "Trap detector is temporarily unavailable." }, { status: 503 });
  }
}
