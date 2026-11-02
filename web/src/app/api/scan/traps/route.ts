import { NextResponse } from "next/server";
import { unstable_cache } from "next/cache";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS, dailyCacheHeaders } from "@/lib/cache/daily";
import { CANONICAL_STOCK_NAMES } from "@/lib/ai/stock-names";

export const runtime = "nodejs";
export const revalidate = 3600;
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

const getCachedTrapsSnapshot = unstable_cache(
  async (): Promise<TrapsSnapshot> => {
    const supabase = getSupabaseServiceClient({ cacheMarketData: true });

    // 1. Try precomputed daily traps cache first
    try {
      const { data: cacheRow } = await supabase
        .from("market_cache")
        .select("payload, computed_at")
        .eq("cache_key", "scanner_traps_EGX")
        .limit(1)
        .maybeSingle();

      if (
        cacheRow?.payload &&
        Array.isArray(cacheRow.payload.bearTraps) &&
        cacheRow.payload.bearTraps.length > 0
      ) {
        return {
          asOf: cacheRow.payload.asOf || null,
          bearTraps: cacheRow.payload.bearTraps.slice(0, 8),
          bullTraps: (cacheRow.payload.bullTraps || []).slice(0, 8),
          totalBearTraps: cacheRow.payload.totalBearTraps ?? cacheRow.payload.bearTraps.length,
          totalBullTraps: cacheRow.payload.totalBullTraps ?? (cacheRow.payload.bullTraps || []).length,
        };
      }
    } catch (e) {
      console.warn("[api/scan/traps] market_cache read fallback:", e);
    }

    const { data: latestRows, error: latestError } = await supabase
      .from("stock_technical_indicators")
      .select("date")
      .eq("exchange", "EGX")
      .order("date", { ascending: false })
      .limit(1);
    if (latestError) throw latestError;

    const asOf = latestRows?.[0]?.date ? String(latestRows[0].date).slice(0, 10) : null;
    if (!asOf) {
      return { asOf: null, bearTraps: [], bullTraps: [], totalBearTraps: 0, totalBullTraps: 0 };
    }

    const [indRes, barsRes] = await Promise.all([
      supabase
        .from("stock_technical_indicators")
        .select("symbol,close,change_pct,rsi_14,r_vol,ema_20,sma_20,bb_upper,bb_lower,egx_ai_score")
        .eq("exchange", "EGX")
        .eq("date", asOf)
        .limit(400),
      supabase
        .from("stock_prices")
        .select("symbol,open,high,low,close")
        .eq("exchange", "EGX")
        .eq("date", asOf)
        .limit(400),
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

    return {
      asOf,
      bearTraps: bearTraps.slice(0, 8),
      bullTraps: bullTraps.slice(0, 8),
      totalBearTraps: bearTraps.length,
      totalBullTraps: bullTraps.length,
    };
  },
  ["trap-detector-egx-daily"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market] }
);

export async function GET() {
  try {
    const payload = await getCachedTrapsSnapshot();
    return NextResponse.json(payload, { headers: dailyCacheHeaders(DAILY_CACHE_TAGS.market) });
  } catch (error) {
    console.error("[TRAP_DETECTOR] Failed to load latest trap signals", error);
    return NextResponse.json({ error: "Trap detector is temporarily unavailable." }, { status: 503 });
  }
}
