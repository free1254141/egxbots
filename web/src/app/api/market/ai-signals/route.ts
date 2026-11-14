import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import {
  resolveRequestMarket,
  getMarketExchange,
  getMarketSupabaseClient,
} from "@/lib/supabase/route-data";
import { getViewerContext } from "@/lib/supabase/viewer-context";
import { planLimits, paymentsEnabled } from "@/lib/ai/plan-gate";
import { savedSignalReasons } from "@/lib/signal-explanation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

function paymentsEnabledSafe(): boolean {
  try {
    return paymentsEnabled();
  } catch {
    return false;
  }
}

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const market = resolveRequestMarket(req);
    const exchange = getMarketExchange(market);
    const country = market === "tasi" ? "Saudi Arabia" : "Egypt";
    const currency = market === "tasi" ? "SAR" : "EGP";
    const explicitMarketParam =
      url.searchParams.has("market") ||
      url.searchParams.has("country") ||
      url.searchParams.has("exchange");

    const supabase = getMarketSupabaseClient(market);
    const billingEnabled = paymentsEnabledSafe();
    const responseHeaders: Record<string, string> = billingEnabled
      ? { "Cache-Control": "private, max-age=300, stale-while-revalidate=300" }
      : explicitMarketParam
        ? {
            "Cache-Control": "public, max-age=30",
            "Vercel-CDN-Cache-Control": "public, s-maxage=120, stale-while-revalidate=300",
          }
        : {
            "Cache-Control": "private, no-store, max-age=0",
          };

    // Determine the requesting user (if logged in) on Primary Supabase so we can apply
    // plan-gated visibility identically across EGX and TASI.
    let userIsPro = !billingEnabled; // the route is shared/cacheable while billing is disabled
    let userPlan = "free";
    if (billingEnabled) {
      const { authenticated, pro } = await getViewerContext(req);
      userIsPro = authenticated && pro;
      userPlan = userIsPro ? "pro" : "free";
    }

    // 1. Fetch latest open AI recommendations
    const { data: recommendations, error: recError } = await supabase
      .from("scan_results")
      .select("symbol, name, signal, entry_price, target_price, stop_loss, precision, top_reasons, model_name, created_at")
      .eq("country", country)
      .eq("status", "open")
      .eq("is_public", true)
      .order("created_at", { ascending: false })
      .limit(50);

    if (recError) {
      console.error("Failed to fetch scan results:", recError);
      return NextResponse.json({ error: "Failed to fetch AI signals" }, { status: 500 });
    }

    if (!recommendations || recommendations.length === 0) {
      return NextResponse.json({
        signals: [],
        total_open: 0,
        buy_count: 0,
        sell_count: 0,
        market,
        exchange,
        currency,
      }, { headers: responseHeaders });
    }

    // Visibility gate: Active open AI recommendations are strictly exclusive to PRO subscribers.
    if (!userIsPro) {
      return NextResponse.json({
        signals: [],
        total_open: recommendations.length,
        buy_count: recommendations.filter((r: any) => r.signal === "BUY").length,
        sell_count: recommendations.filter((r: any) => r.signal === "SELL").length,
        gated: true,
        is_pro: false,
        signal_delay_days: planLimits(userPlan).signal_delay_days,
        market,
        exchange,
        currency,
      }, { headers: responseHeaders });
    }

    const visible = recommendations;
    const symbols = visible.map((r: any) => r.symbol);

    // 2. Fetch latest prices for these symbols from stock_technical_indicators
    const { data: dateRows } = await supabase
      .from("stock_technical_indicators")
      .select("date")
      .eq("exchange", exchange)
      .order("date", { ascending: false })
      .limit(1);

    const latestDate = dateRows && dateRows.length > 0 ? dateRows[0].date : null;

    const pricesMap = new Map<string, number>();
    const priceDates = new Map<string, string>();
    if (latestDate) {
      const { data: priceRows } = await supabase
        .from("stock_technical_indicators")
        .select("symbol, close")
        .eq("exchange", exchange)
        .eq("date", latestDate)
        .in("symbol", symbols);

      if (priceRows) {
        for (const row of priceRows) {
          if (Number(row.close) > 0) {
            pricesMap.set(row.symbol.toUpperCase(), Number(row.close));
            priceDates.set(row.symbol.toUpperCase(), latestDate);
          }
        }
      }
    }

    // Fallback: if some symbols are missing or date failed, check stock_prices latest close
    const missingSymbols = symbols.filter((s: any) => !pricesMap.has(String(s).toUpperCase()));
    if (missingSymbols.length > 0) {
      const uniqueMissing = [...new Set(missingSymbols.map((symbol: any) => String(symbol).toUpperCase()))];
      const fallbackLimit = Math.min(Math.max(uniqueMissing.length * 30, 300), 2000);
      const { data: fallbackPrices } = await supabase
        .from("stock_prices")
        .select("symbol,close,date")
        .eq("exchange", exchange)
        .in("symbol", uniqueMissing)
        .order("date", { ascending: false })
        .limit(fallbackLimit);

      if (fallbackPrices) {
        for (const row of fallbackPrices) {
          const symbol = String(row.symbol || "").toUpperCase();
          if (symbol && !pricesMap.has(symbol) && Number(row.close) > 0) {
            pricesMap.set(symbol, Number(row.close));
            priceDates.set(symbol, row.date);
          }
        }
      }
    }

    // For TASI, resolve Arabic stock names from stocks.name_ar when available.
    const tasiNamesMap = new Map<string, string>();
    if (market === "tasi" && symbols.length > 0) {
      try {
        const uniqueSyms = Array.from(new Set(symbols.map((s: any) => String(s || "").trim()).filter(Boolean)));
        let { data: stockRows, error: stockErr } = await supabase
          .from("stocks")
          .select("symbol,name_ar,name")
          .eq("exchange", exchange)
          .in("symbol", uniqueSyms)
          .limit(uniqueSyms.length);
        if (stockErr) {
          ({ data: stockRows } = await supabase
            .from("stocks")
            .select("symbol,name")
            .eq("exchange", exchange)
            .in("symbol", uniqueSyms)
            .limit(uniqueSyms.length));
        }
        for (const row of stockRows || []) {
          const key = String(row?.symbol || "").trim().toUpperCase();
          const label = row?.name_ar || row?.name;
          if (key && label) tasiNamesMap.set(key, String(label));
        }
      } catch {
        // Non-fatal
      }
    }

    // 3. Process Signals
    let buyCount = 0;
    let sellCount = 0;
    const signals: any[] = [];

    for (const rec of visible) {
      const symbolUpper = String(rec.symbol || "").toUpperCase();
      const currentPrice = pricesMap.get(symbolUpper) || Number(rec.entry_price || 0);

      const entry = Number(rec.entry_price || 0);
      const isBuy = String(rec.signal || "").toUpperCase().includes("BUY");
      if (isBuy) buyCount++;
      else sellCount++;

      // Compute PnL %
      let pnlPct = 0;
      if (entry > 0) {
        pnlPct = isBuy
          ? ((currentPrice - entry) / entry) * 100
          : ((entry - currentPrice) / entry) * 100;
      }

      // Preserve rich JSON rationale as well as older arrays / serialized JSON.
      const reasons = savedSignalReasons(rec.top_reasons);

      signals.push({
        symbol: rec.symbol,
        name:
          market === "tasi"
            ? tasiNamesMap.get(symbolUpper) || rec.name || rec.symbol
            : rec.name || rec.symbol,
        signal: isBuy ? "BUY" : "SELL",
        entry_price: entry,
        current_price: currentPrice,
        price_date: priceDates.get(symbolUpper) || null,
        target_price: Number(rec.target_price || 0),
        stop_loss: Number(rec.stop_loss || 0),
        precision: Number(rec.precision || 0),
        pnl_pct: pnlPct,
        top_reasons: reasons,
        model_name: rec.model_name || "AI Council",
        created_at: rec.created_at,
        council_score: 0,
      });
    }

    return NextResponse.json({
      signals,
      total_open: recommendations.length,
      buy_count: buyCount,
      sell_count: sellCount,
      gated: false,
      is_pro: true,
      signal_delay_days: 0,
      market,
      exchange,
      currency,
    }, { headers: responseHeaders });
  } catch (error) {
    console.error("AI Signals API error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
