import { NextRequest, NextResponse } from "next/server";
import {
  resolveRequestMarket,
  getMarketExchange,
  getMarketSupabaseClient,
} from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS, dailyCacheHeaders } from "@/lib/cache/daily";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getBackendBaseUrl() {
  return (
    process.env.PYTHON_BACKEND_URL ||
    process.env.TRADING_SIGNALS_API_URL ||
    process.env.BACKEND_URL ||
    process.env.API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
}

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const rawSymbol = (url.searchParams.get("symbol") || "").trim();
    const rawExchange = (url.searchParams.get("exchange") || "").trim();
    const rawExchangeUpper = rawExchange.toUpperCase();
    const rawLimit = Number(url.searchParams.get("limit") || 150);
    const limit =
      url.searchParams.get("all") === "true" || rawLimit > 1000
        ? Math.min(rawLimit || 5000, 5000)
        : Math.min(rawLimit, 1000);
    const bot_id = url.searchParams.get("bot_id") || "primary";
    const includeMarkers = url.searchParams.get("include_markers") !== "false";

    if (!rawSymbol) {
      return NextResponse.json({ candles: [], markers: [] }, { status: 400 });
    }

    const isSaudiSymbol =
      /^\d{4}(\.(SR|SA|TADAWUL))?$/i.test(rawSymbol) ||
      /^(\^)?TASI(\.SR)?$/i.test(rawSymbol);
    const isEgxSuffix = /\.CA$/i.test(rawSymbol);
    const isSaudiExchange = ["TADAWUL", "TASI", "SR"].includes(rawExchangeUpper);
    const isSupportedExchange =
      rawExchangeUpper === "" || rawExchangeUpper === "EGX" || isSaudiExchange;

    // Preserve 410 for non-Saudi, non-EGX explicit exchanges (e.g. AAPL with exchange=US),
    // while allowing legacy callers that pass exchange=US on 4-digit Saudi tickers.
    if (!isSaudiSymbol && !isEgxSuffix && !isSupportedExchange) {
      return NextResponse.json(
        { candles: [], markers: [], error: "Only EGX and Saudi Tadawul (TASI) market data is available." },
        { status: 410 }
      );
    }

    const explicitMarketHint =
      url.searchParams.get("market") ||
      url.searchParams.get("country") ||
      (isSaudiExchange ? "TADAWUL" : rawExchangeUpper === "EGX" ? "EGX" : null);

    const market =
      isSaudiSymbol || isSaudiExchange
        ? "tasi"
        : isEgxSuffix || rawExchangeUpper === "EGX"
          ? "egx"
          : resolveRequestMarket(req, explicitMarketHint);
    const exchange = getMarketExchange(market);
    const currency = market === "tasi" ? "SAR" : "EGP";
    const symbol =
      market === "tasi"
        ? rawSymbol.replace(/\.(SR|SA|TADAWUL)$/i, "").toUpperCase()
        : rawSymbol;

    const explicitMarketInUrl =
      url.searchParams.has("market") ||
      url.searchParams.has("country") ||
      isSaudiSymbol ||
      isSaudiExchange ||
      isEgxSuffix ||
      rawExchangeUpper === "EGX";
    const responseHeaders =
      market === "egx" || explicitMarketInUrl
        ? dailyCacheHeaders(DAILY_CACHE_TAGS.market)
        : {
            "Cache-Control": "private, no-store, max-age=0",
            "Vercel-Cache-Tag": DAILY_CACHE_TAGS.market,
          };

    // For EGX, the Python backend owns the canonical HF-history + Supabase-tail merge.
    // Skip Python for TASI and query SAUDI_SUPABASE stock_prices directly.
    if (market === "egx") {
      try {
        const backendUrl = new URL(`${getBackendBaseUrl()}/bot/candles`);
        backendUrl.searchParams.set("symbol", symbol);
        backendUrl.searchParams.set("exchange", "EGX");
        backendUrl.searchParams.set("limit", String(limit));
        backendUrl.searchParams.set("bot_id", bot_id);
        const backendResponse = await fetch(backendUrl, {
          next: { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market] },
          signal: AbortSignal.timeout(30000),
        });
        if (backendResponse.ok) {
          const payload = await backendResponse.json();
          return NextResponse.json(includeMarkers ? payload : { ...payload, markers: [] }, {
            headers: responseHeaders,
          });
        }
      } catch (error) {
        console.warn("Unified candle backend unavailable; using live-table fallback:", error);
      }
    }

    const supabase = getMarketSupabaseClient(market);
    let rawCandles: any[] = [];
    const timeframe = "1d";

    const { data, error } = await supabase
      .from("stock_prices")
      .select("date,open,high,low,close,volume")
      .eq("symbol", symbol)
      .eq("exchange", exchange)
      .order("date", { ascending: false })
      .limit(limit);

    if (!error && data) {
      rawCandles = [...data].reverse(); // reverse to chronological
    } else if (error) {
      console.error(`Failed to load ${exchange} candles for ${symbol}:`, error);
    }

    // Format for lightweight-charts
    const candles = rawCandles
      .map((c: any) => {
        const ts = c.ts || c.date;
        let unix_ts = 0;
        if (ts) {
          if (ts.includes("T") || ts.includes(" ")) {
            unix_ts = Math.floor(new Date(ts).getTime() / 1000);
          } else {
            // YYYY-MM-DD
            unix_ts = Math.floor(new Date(ts + "T00:00:00Z").getTime() / 1000);
          }
        }
        return {
          time: unix_ts,
          open: Number(c.open || 0),
          high: Number(c.high || 0),
          low: Number(c.low || 0),
          close: Number(c.close || 0),
          volume: Number(c.volume || 0),
        };
      })
      .filter((c) => c.time > 0);

    // Fetch markers from bot_trades
    if (!includeMarkers) {
      return NextResponse.json(
        { candles, markers: [], timeframe, exchange, currency },
        { headers: responseHeaders }
      );
    }

    let rawMarkers: any[] = [];
    try {
      const { data: markersData } = await supabase
        .from("bot_trades")
        .select("timestamp,action,price,entry_price,pnl")
        .eq("bot_id", bot_id)
        .eq("symbol", symbol)
        .order("timestamp", { ascending: true })
        .limit(200);
      rawMarkers = markersData || [];
    } catch {
      rawMarkers = [];
    }

    const markers = rawMarkers.map((m: any) => {
      const unix_ts = Math.floor(new Date(m.timestamp).getTime() / 1000);
      return {
        time: unix_ts,
        position: m.action.toUpperCase() === "BUY" ? "belowBar" : "aboveBar",
        color: m.action.toUpperCase() === "BUY" ? "#10B981" : "#EF4444",
        shape: m.action.toUpperCase() === "BUY" ? "arrowUp" : "arrowDown",
        text:
          m.action.toUpperCase() +
          (m.pnl != null ? ` (${m.pnl > 0 ? "+" : ""}${Number(m.pnl).toFixed(1)}%)` : ""),
        action: m.action,
        price: m.price,
      };
    });

    return NextResponse.json(
      {
        candles,
        markers,
        timeframe,
        exchange,
        currency,
      },
      { headers: responseHeaders }
    );
  } catch (err: any) {
    console.error("Candles endpoint error:", err);
    return NextResponse.json({ candles: [], markers: [] }, { status: 500 });
  }
}
