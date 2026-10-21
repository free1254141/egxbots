import { NextRequest, NextResponse } from "next/server";
import { getSupabaseServiceClient, getSupabaseClient } from "@/lib/supabase/route-data";

const MEM_CACHE = new Map<string, { payload: any; timestamp: number }>();

function computePostSignalPayload(
  candles: any[],
  targetDate: string,
  cleanSymbol: string,
  signalTime?: string | null,
  signalPrice?: string | null
) {
  if (!candles || candles.length === 0) return null;
  let targetSigTime = signalTime || "10:15";
  if (targetSigTime > "14:15" || targetSigTime < "10:00") {
    targetSigTime = "10:15";
  }

  let sigIdx = 0;
  for (let i = 0; i < candles.length; i++) {
    if (candles[i].time >= targetSigTime) {
      sigIdx = i;
      break;
    }
  }

  const signalCandle = candles[sigIdx];
  const parsedPrice = signalPrice ? parseFloat(signalPrice) : 0;
  const sPrice =
    parsedPrice > 0 && Math.abs(parsedPrice - signalCandle.close) / Math.max(0.01, signalCandle.close) < 0.3
      ? parsedPrice
      : signalCandle.close;

  // Search strictly from the signal candle forwards to find the peak AFTER the signal!
  const postSignalCandles = candles.slice(sigIdx);
  const peakCandle = postSignalCandles.length > 0
    ? postSignalCandles.reduce((max, c) => (c.high > max.high ? c : max), signalCandle)
    : signalCandle;

  const peakPrice = peakCandle.high;
  const peakTime = peakCandle.time;

  const sessionOpen = candles[0].open;
  const sessionClose = candles[candles.length - 1].close;
  const sessionGainPct = Number((((sessionClose - sessionOpen) / sessionOpen) * 100).toFixed(2));
  const sessionMaxGainPct = Number((((Math.max(...candles.map((c) => c.high)) - sessionOpen) / sessionOpen) * 100).toFixed(2));

  let gainFromSignalPct = Number((((peakPrice - sPrice) / sPrice) * 100).toFixed(2));
  if (gainFromSignalPct < 0) gainFromSignalPct = 0.0;

  return {
    symbol: cleanSymbol,
    date: targetDate,
    session_open: sessionOpen,
    session_close: sessionClose,
    session_high: peakPrice,
    peak_time: peakTime,
    session_low: Math.min(...candles.map((c) => c.low)),
    session_gain_pct: sessionGainPct,
    session_max_gain_pct: sessionMaxGainPct,
    signal: {
      time: targetSigTime,
      price: sPrice,
      max_gain_pct: gainFromSignalPct,
    },
    candles,
    bars_count: candles.length,
  };
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const rawSymbol = searchParams.get("symbol") || "";
    const date = searchParams.get("date") || "";
    const signalTime = searchParams.get("signal_time") || "";
    const signalPrice = searchParams.get("signal_price") || "";

    if (!rawSymbol) {
      return NextResponse.json({ error: "Missing symbol parameter" }, { status: 400 });
    }

    const cleanSymbol = rawSymbol.trim().toUpperCase().replace(".CA", "").replace(".EGX", "");
    const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Cairo", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    const targetDate = date || today;
    const cacheKey = `scanner_15m:${targetDate}:${cleanSymbol}`;
    const now = Date.now();

    const headers = {
      "Cache-Control": "public, max-age=600, stale-while-revalidate=86400",
    };

    // 1. In-memory fast cache (0ms instant hit)
    const isToday = targetDate === today;
    const cacheTtl = isToday ? 60_000 : 3_600_000;
    const mem = MEM_CACHE.get(cacheKey);
    if (mem && now - mem.timestamp < cacheTtl) {
      const payload = computePostSignalPayload(mem.payload.candles, targetDate, cleanSymbol, signalTime, signalPrice);
      if (payload?.data_source === "tvdatafeed") {
        return NextResponse.json(payload, { headers });
      }
    }

    // 2. Call local Python FastAPI backend first if available (uses fast singleton tvDatafeed & local memory)
    const pythonUrl = process.env.PYTHON_BACKEND_URL || "http://localhost:8000";
    try {
      const pyParams = new URLSearchParams({
        symbol: cleanSymbol,
        date: targetDate,
      });
      if (signalTime) pyParams.set("signal_time", signalTime);
      if (signalPrice) pyParams.set("signal_price", signalPrice);

      const pyRes = await fetch(`${pythonUrl}/api/scanner/intraday-session?${pyParams.toString()}`, {
        cache: "no-store",
        signal: AbortSignal.timeout(3500),
      });

      if (pyRes.ok) {
        const payload = await pyRes.json();
        if (payload?.data_source === "tvdatafeed" && Array.isArray(payload.candles) && payload.candles.length > 0) {
          MEM_CACHE.set(cacheKey, { payload, timestamp: now });
          return NextResponse.json(payload, { headers });
        }
      }
    } catch {
      // Backend busy or timeout, check Supabase or fallback
    }

    let serviceClient: any = null;
    try {
      serviceClient = getSupabaseServiceClient();
    } catch {
      try {
        serviceClient = getSupabaseClient();
      } catch {
        serviceClient = null;
      }
    }

    // 3. Try Supabase market_cache (only for past sessions)
    if (serviceClient && !isToday) {
      try {
        const { data: cached } = await serviceClient
          .from("market_cache")
          .select("payload")
          .eq("cache_key", cacheKey)
          .maybeSingle();

        if (cached?.payload?.data_source === "tvdatafeed" && cached.payload.candles?.length > 0) {
          const payload = computePostSignalPayload(cached.payload.candles, targetDate, cleanSymbol, signalTime, signalPrice);
          if (payload) {
            MEM_CACHE.set(cacheKey, { payload, timestamp: now });
            return NextResponse.json(payload, { headers });
          }
        }
      } catch (e) {
        console.warn("Supabase market_cache check failed:", e);
      }
    }

    // Do not invent intraday candles from daily prices.
    return NextResponse.json(
      { error: "Authentic 15-minute candles are unavailable for this symbol/date.", code: "INTRADAY_DATA_UNAVAILABLE", symbol: cleanSymbol, date: targetDate },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  } catch (err: any) {
    console.error("Error in GET /api/scanner/intraday-session:", err);
    return NextResponse.json({ error: "Failed to load session intraday data" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const date = body.date || new Date().toISOString().split("T")[0];
    const items: Array<{ symbol: string; signal_time?: string; signal_price?: number | string }> = body.items || [];

    if (!Array.isArray(items) || items.length === 0) {
      return NextResponse.json({ ok: true, gains: {} });
    }

    const gains: Record<string, { max_gain_pct: number; peak_price: number; peak_time: string; session_high: number }> = {};
    const now = Date.now();
    const missingItems: typeof items = [];

    // 1. Check in-memory MEM_CACHE first (instant)
    for (const item of items) {
      const cleanSymbol = (item.symbol || "").trim().toUpperCase().replace(".CA", "").replace(".EGX", "");
      if (!cleanSymbol) continue;
      const cacheKey = `scanner_15m:${date}:${cleanSymbol}`;
      const mem = MEM_CACHE.get(cacheKey);
      if (mem && now - mem.timestamp < 3600000 && mem.payload?.data_source === "tvdatafeed" && mem.payload?.candles?.length > 0) {
        const payload = computePostSignalPayload(
          mem.payload.candles,
          date,
          cleanSymbol,
          item.signal_time,
          item.signal_price ? String(item.signal_price) : undefined
        );
        if (payload?.signal) {
          gains[cleanSymbol] = {
            max_gain_pct: payload.signal.max_gain_pct,
            peak_price: payload.session_high,
            peak_time: payload.peak_time,
            session_high: payload.session_high,
          };
          continue;
        }
      }
      missingItems.push(item);
    }

    // 2. For items not in MEM_CACHE, batch query Supabase market_cache
    if (missingItems.length > 0) {
      let serviceClient: any = null;
      try {
        serviceClient = getSupabaseServiceClient();
      } catch {
        try {
          serviceClient = getSupabaseClient();
        } catch {
          serviceClient = null;
        }
      }

      if (serviceClient) {
        try {
          const cacheKeys = missingItems.map(
            (it) => `scanner_15m:${date}:${it.symbol.trim().toUpperCase().replace(".CA", "").replace(".EGX", "")}`
          );
          const { data: rows } = await serviceClient
            .from("market_cache")
            .select("cache_key, payload")
            .in("cache_key", cacheKeys);

          if (rows && rows.length > 0) {
            const rowMap = new Map<string, any>();
            rows.forEach((r: any) => rowMap.set(r.cache_key, r.payload));

            for (let i = missingItems.length - 1; i >= 0; i--) {
              const it = missingItems[i];
              const cleanSym = it.symbol.trim().toUpperCase().replace(".CA", "").replace(".EGX", "");
              const cKey = `scanner_15m:${date}:${cleanSym}`;
              const p = rowMap.get(cKey);
              if (p?.data_source === "tvdatafeed" && p?.candles?.length > 0) {
                const payload = computePostSignalPayload(
                  p.candles,
                  date,
                  cleanSym,
                  it.signal_time,
                  it.signal_price ? String(it.signal_price) : undefined
                );
                if (payload?.data_source === "tvdatafeed" && payload?.signal) {
                  MEM_CACHE.set(cKey, { payload, timestamp: now });
                  gains[cleanSym] = {
                    max_gain_pct: payload.signal.max_gain_pct,
                    peak_price: payload.session_high,
                    peak_time: payload.peak_time,
                    session_high: payload.session_high,
                  };
                  missingItems.splice(i, 1);
                }
              }
            }
          }
        } catch (e) {
          console.warn("Batch market_cache lookup error:", e);
        }
      }
    }

    // 3. For any remaining missing items, generate/fetch in parallel
    if (missingItems.length > 0) {
      await Promise.all(
        missingItems.map(async (it) => {
          try {
            const cleanSym = it.symbol.trim().toUpperCase().replace(".CA", "").replace(".EGX", "");
            const cacheKey = `scanner_15m:${date}:${cleanSym}`;
            const pyParams = new URLSearchParams({ symbol: cleanSym, date });
            if (it.signal_time) pyParams.set("signal_time", it.signal_time);
            if (it.signal_price) pyParams.set("signal_price", String(it.signal_price));
            const pythonUrl = process.env.PYTHON_BACKEND_URL || "http://localhost:8000";

            let payload: any = null;
            try {
              const pyRes = await fetch(`${pythonUrl}/api/scanner/intraday-session?${pyParams.toString()}`, {
                signal: AbortSignal.timeout(2000),
              });
              if (pyRes.ok) {
                payload = await pyRes.json();
              }
            } catch {
              // Ignore
            }

            // Never synthesize OHLCV for chart metrics.
            if (payload?.data_source !== "tvdatafeed") payload = null;

            if (payload?.signal) {
              MEM_CACHE.set(cacheKey, { payload, timestamp: now });
              gains[cleanSym] = {
                max_gain_pct: payload.signal.max_gain_pct,
                peak_price: payload.session_high,
                peak_time: payload.peak_time,
                session_high: payload.session_high,
              };
            }
          } catch {
            // Ignore item failure
          }
        })
      );
    }

    return NextResponse.json({ ok: true, gains });
  } catch (err: any) {
    console.error("Error in POST /api/scanner/intraday-session:", err);
    return NextResponse.json({ error: "Failed to process batch gains" }, { status: 500 });
  }
}
