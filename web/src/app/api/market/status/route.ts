import { NextRequest, NextResponse } from "next/server";
import {
  resolveRequestMarket,
  getMarketExchange,
  getMarketSupabaseClient,
  toNumber,
} from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS, dailyCacheHeaders } from "@/lib/cache/daily";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function computeTrendRegime(points: Array<{ close: number; ret: number | null }>): {
  regime: string;
  tasiReturn: number;
  rejectBuys: boolean;
} {
  if (points.length === 0) {
    return { regime: "sideways", tasiReturn: 0, rejectBuys: false };
  }
  const latest = points[points.length - 1];
  const prev = points.length >= 2 ? points[points.length - 2] : null;
  const tasiReturn =
    prev && prev.close > 0
      ? (latest.close - prev.close) / prev.close
      : latest.ret !== null
        ? Math.abs(latest.ret) > 1
          ? latest.ret / 100
          : latest.ret
        : 0;

  const avgClose = (slice: Array<{ close: number }>) =>
    slice.length > 0 ? slice.reduce((sum, p) => sum + p.close, 0) / slice.length : latest.close;
  const sma20 = avgClose(points.slice(-20));
  const sma50 = avgClose(points.slice(-50));

  let regime = "sideways";
  if (tasiReturn <= -0.025) {
    regime = "panic";
  } else if (latest.close > sma20 * 1.005 && sma20 >= sma50 * 0.995) {
    regime = "trending_up";
  } else if (latest.close < sma20 * 0.995 && sma20 <= sma50 * 1.005) {
    regime = "trending_down";
  }

  return {
    regime,
    tasiReturn,
    rejectBuys: regime === "panic" || regime === "trending_down",
  };
}

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const market = resolveRequestMarket(req);
    const exchange = getMarketExchange(market);
    const explicitMarketParam =
      url.searchParams.has("market") ||
      url.searchParams.has("country") ||
      url.searchParams.has("exchange");
    const headers: Record<string, string> = explicitMarketParam
      ? dailyCacheHeaders(DAILY_CACHE_TAGS.market)
      : {
          "Cache-Control": "private, no-store, max-age=0",
          "Vercel-Cache-Tag": DAILY_CACHE_TAGS.market,
        };

    const supabase = getMarketSupabaseClient(market);
    const cacheKey = market === "tasi" ? "market_status_Saudi Arabia" : "market_status_Egypt";
    const { data, error } = await supabase
      .from("market_cache")
      .select("payload")
      .eq("cache_key", cacheKey)
      .maybeSingle();

    if (market === "egx") {
      if (error) throw error;
      if (!data?.payload) throw new Error("Market status snapshot is missing");

      const payload = (typeof data.payload === "string" ? JSON.parse(data.payload) : data.payload) || {};
      const safePayload = {
        ...payload,
        egx30: Array.isArray(payload.egx30) ? payload.egx30 : [],
        egx100: Array.isArray(payload.egx100) ? payload.egx100 : [],
        usdegp: Array.isArray(payload.usdegp) ? payload.usdegp : [],
      };

      // If usdegp is empty in cache, fallback to stock_prices
      if (safePayload.usdegp.length === 0) {
        try {
          const { data: usdRows } = await supabase
            .from("stock_prices")
            .select("date, open, high, low, close, volume")
            .eq("symbol", "USDEGP")
            .order("date", { ascending: false })
            .limit(365);
          if (usdRows && usdRows.length > 0) {
            safePayload.usdegp = [...usdRows].reverse().map((r: any) => ({
              date: r.date,
              open: toNumber(r.open, 0),
              high: toNumber(r.high, 0),
              low: toNumber(r.low, 0),
              close: toNumber(r.close, 0),
              volume: toNumber(r.volume, 0),
            }));
          }
        } catch (err) {
          console.error("Failed to fetch USD/EGP fallback prices:", err);
        }
      }

      return NextResponse.json(safePayload, { headers });
    }

    // Saudi Tadawul (TASI) path: prefer market_cache if present and populated, else fallback to market_index.
    let cachedPayload: Record<string, any> | null = null;
    if (!error && data?.payload) {
      try {
        cachedPayload = (typeof data.payload === "string" ? JSON.parse(data.payload) : data.payload) || null;
      } catch {
        cachedPayload = null;
      }
    }

    if (cachedPayload && Array.isArray(cachedPayload.tasi) && cachedPayload.tasi.length > 0) {
      return NextResponse.json(
        {
          ...cachedPayload,
          tasi: cachedPayload.tasi,
          egx30: Array.isArray(cachedPayload.egx30) ? cachedPayload.egx30 : [],
          egx100: Array.isArray(cachedPayload.egx100) ? cachedPayload.egx100 : [],
          usdegp: Array.isArray(cachedPayload.usdegp) ? cachedPayload.usdegp : [],
          market: "tasi",
          exchange,
          currency: "SAR",
        },
        { headers },
      );
    }

    const { data: indexRows, error: indexError } = await supabase
      .from("market_index")
      .select("date,close,ret,source")
      .eq("exchange", "TADAWUL")
      .order("date", { ascending: false })
      .limit(365);

    if (indexError) throw indexError;

    const ordered = [...(indexRows || [])]
      .reverse()
      .map((r: any) => {
        const close = toNumber(r.close, 0);
        return {
          date: r.date,
          open: close,
          high: close,
          low: close,
          close,
          volume: 0,
          ret: r.ret == null ? null : toNumber(r.ret, 0),
          source: r.source || "TADAWUL",
        };
      })
      .filter((r) => r.close > 0);

    if (ordered.length === 0) {
      throw new Error("TASI market status snapshot is missing");
    }

    const { regime, tasiReturn, rejectBuys } = computeTrendRegime(ordered);
    const updatedAt = ordered[ordered.length - 1]?.date || new Date().toISOString();

    return NextResponse.json(
      {
        ...(cachedPayload || {}),
        tasi: ordered,
        egx30: [],
        egx100: [],
        usdegp: [],
        regime: cachedPayload?.regime || regime,
        tasi_return:
          cachedPayload?.tasi_return !== undefined ? cachedPayload.tasi_return : tasiReturn,
        reject_buys:
          cachedPayload?.reject_buys !== undefined ? cachedPayload.reject_buys : rejectBuys,
        updated_at: cachedPayload?.updated_at || updatedAt,
        market: "tasi",
        exchange,
        currency: "SAR",
      },
      { headers },
    );
  } catch (error) {
    console.error("market status error:", error);
    return NextResponse.json(
      { error: "Market status temporarily unavailable" },
      { status: 503, headers: { "Cache-Control": "private, no-store, max-age=0" } },
    );
  }
}
