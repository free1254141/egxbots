import { NextRequest, NextResponse } from "next/server";
import {
  resolveRequestMarket,
  getMarketExchange,
  getMarketSupabaseClient,
} from "@/lib/supabase/route-data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

function getBackendBaseUrl() {
  return (
    process.env.PYTHON_BACKEND_URL ||
    process.env.TRADING_SIGNALS_API_URL ||
    process.env.BACKEND_URL ||
    process.env.API_BASE_URL ||
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    "http://127.0.0.1:8000"
  );
}

function normalizeArabicSearch(text: string): string {
  return text
    .toLowerCase()
    .replace(/[\u064B-\u065F\u0670\u0640]/g, "")
    .replace(/[أإآ]/g, "ا")
    .replace(/ى/g, "ي")
    .replace(/ة/g, "ه")
    .trim();
}

function normalizeExchangeParam(raw?: string | null): string | null {
  const val = (raw || "").trim().toLowerCase();
  if (!val) return null;
  if (val === "tasi" || val === "sr" || val === "tadawul") return "tadawul";
  return val;
}

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const qRaw = (url.searchParams.get("q") || "").trim();
  const q = qRaw.toLowerCase();
  const qNorm = normalizeArabicSearch(qRaw);
  const country = url.searchParams.get("country");
  const rawExchange = url.searchParams.get("exchange");
  const exchange = normalizeExchangeParam(rawExchange);
  const limit = Math.min(Number(url.searchParams.get("limit") || 25), 100000);

  const looksLikeSaudiTicker = /^\d{4}(\.(sr|sa|tadawul))?$/i.test(qRaw);
  const explicitCountryIsEgypt = Boolean(country && country.toLowerCase().includes("egypt"));
  const explicitMarketHint =
    url.searchParams.get("market") || country || rawExchange || null;
  const market =
    looksLikeSaudiTicker && !explicitCountryIsEgypt && exchange !== "egx"
      ? "tasi"
      : resolveRequestMarket(req, explicitMarketHint);
  const targetExchange = getMarketExchange(market);
  const defaultCurrency = market === "tasi" ? "SAR" : "EGP";
  const defaultCountry = market === "tasi" ? "Saudi Arabia" : "Egypt";

  const explicitMarketInUrl =
    url.searchParams.has("market") ||
    url.searchParams.has("country") ||
    url.searchParams.has("exchange") ||
    looksLikeSaudiTicker;
  const responseHeaders: Record<string, string> = explicitMarketInUrl
    ? {
        "Cache-Control": "public, max-age=30",
        "Vercel-CDN-Cache-Control":
          limit > 1000
            ? "public, s-maxage=60, stale-while-revalidate=120"
            : "public, s-maxage=600, stale-while-revalidate=1800",
      }
    : {
        "Cache-Control": "private, no-store, max-age=0",
      };

  // 1. Prefer the Python backend for EGX. It honors source=local (local symbols
  //    inventory), the full limit (the admin Data Manager requests 100000),
  //    and performs its own multi-tier symbol resolution.
  //    Skip Python for TASI because the Python local symbols index is EGX-only.
  if (market === "egx") {
    try {
      const backendUrl = new URL("/symbols/search", getBackendBaseUrl());
      url.searchParams.forEach((value, key) => {
        backendUrl.searchParams.set(key, value);
      });

      const backendRes = await fetch(backendUrl.toString(), {
        next: { revalidate: 3600 },
        signal: AbortSignal.timeout(15000),
      });

      if (backendRes.ok) {
        const contentType = backendRes.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          const data = await backendRes.json();
          if (Array.isArray(data?.results)) {
            return NextResponse.json({ results: data.results }, { headers: responseHeaders });
          }
        }
      }
    } catch (error) {
      console.warn("Backend symbols search unavailable, falling back to Supabase:", error);
    }
  }

  // 2. Supabase lookups (EGX primary or SAUDI_SUPABASE for TASI).
  try {
    const supabase = getMarketSupabaseClient(market);
    const removedExchanges = new Set(["binance", "crypto", "forex", "lse"]);

    // market_cache keys are stored with canonical casing (e.g. symbols_Egypt, symbols_Saudi Arabia);
    // the incoming country may be any casing, so try the common variants.
    const cacheKeyCandidates =
      market === "tasi"
        ? [
            ...new Set([
              ...(country
                ? [
                    `symbols_${country}`,
                    `symbols_${country.charAt(0).toUpperCase()}${country.slice(1)}`,
                    `symbols_${country.toUpperCase()}`,
                  ]
                : []),
              "symbols_Saudi Arabia",
              "symbols_Saudi",
              "symbols_TADAWUL",
              "symbols_TASI",
              "all_symbols_by_country",
            ]),
          ]
        : country
          ? [
              ...new Set([
                `symbols_${country}`,
                `symbols_${country.charAt(0).toUpperCase()}${country.slice(1)}`,
                `symbols_${country.toUpperCase()}`,
              ]),
            ]
          : ["all_symbols_by_country"];

    let allSymbols: Array<any> = [];
    for (const cacheKey of cacheKeyCandidates) {
      const { data: cacheRow, error } = await supabase
        .from("market_cache")
        .select("payload")
        .eq("cache_key", cacheKey)
        .maybeSingle();
      if (!error && cacheRow?.payload && Array.isArray(cacheRow.payload)) {
        allSymbols = cacheRow.payload;
        break;
      }
    }

    if (allSymbols.length === 0) {
      // Fallback to the canonical stocks table (case-insensitive matches —
      // stocks.country stores "Egypt" / "Saudi Arabia", requests may carry lowercase).
      console.warn(`Cache miss for ${cacheKeyCandidates.join(", ")} — falling back to stocks table`);
      const selectAttempts = [
        "symbol, exchange, name, name_ar, country, currency",
        "symbol, exchange, name, name_ar, country",
        "symbol, exchange, name, country",
      ];
      let symbolRows: any[] | null = null;
      let symErr: any = null;
      for (const selectCols of selectAttempts) {
        let symbolQuery = supabase
          .from("stocks")
          .select(selectCols)
          .eq("is_active", true)
          .limit(5000);

        if (market === "tasi") {
          symbolQuery = symbolQuery.eq("exchange", targetExchange);
        } else {
          if (country) symbolQuery = symbolQuery.ilike("country", country);
          if (exchange) symbolQuery = symbolQuery.ilike("exchange", exchange);
        }

        const res = await symbolQuery;
        if (!res.error) {
          symbolRows = res.data;
          symErr = null;
          break;
        }
        symErr = res.error;
      }

      if (!symErr && symbolRows) {
        allSymbols = symbolRows.map((s: any) => ({
          Symbol: s.symbol,
          Exchange: s.exchange || targetExchange,
          Name: s.name,
          NameAr: s.name_ar || "",
          Country: s.country || defaultCountry,
          Type: "Common Stock",
          Currency: s.currency || defaultCurrency,
        }));
      } else if (symErr) {
        console.error("Failed to fetch symbols from stocks table:", symErr);
        return NextResponse.json({ results: [] }, { headers: { "Cache-Control": "no-store" } });
      }
    }

    if (!Array.isArray(allSymbols)) {
      return NextResponse.json({ results: [] }, { headers: { "Cache-Control": "no-store" } });
    }

    const qClean = q.replace(/\.(sr|sa|tadawul|ca)$/i, "");
    const rankedMatches: Array<{ rank: number; item: any }> = [];

    for (const item of allSymbols) {
      const rawSym = String(item.Symbol || item.symbol || item.Code || "");
      const sym = rawSym.toLowerCase();
      const symClean = sym.replace(/\.(sr|sa|tadawul|ca)$/i, "");
      const rawName = String(item.Name || item.name || "");
      const name = rawName.toLowerCase();
      const rawNameAr = String(item.NameAr || item.name_ar || item.arabic_name || "");
      const nameArNorm = normalizeArabicSearch(rawNameAr);
      const nameNorm = normalizeArabicSearch(rawName);
      const rawEx = String(item.Exchange || item.exchange || targetExchange);
      const ex = normalizeExchangeParam(rawEx) || "";
      const itemCountry = String(item.Country || item.country || country || defaultCountry);
      const itemCurrency = String(item.Currency || item.currency || defaultCurrency);

      // Apply exchange filter
      if (removedExchanges.has(ex)) continue;
      if (exchange && ex !== exchange) continue;

      // Apply query filter (matches symbol, English name, or Arabic name)
      const matches =
        !q ||
        sym.includes(q) ||
        (qClean && symClean.includes(qClean)) ||
        name.includes(q) ||
        (qNorm && (nameNorm.includes(qNorm) || nameArNorm.includes(qNorm)));

      if (!matches) continue;

      let rank = 4;
      if (!q) {
        rank = 0;
      } else if (sym === q || (qClean && symClean === qClean)) {
        rank = 0;
      } else if (sym.startsWith(q) || (qClean && symClean.startsWith(qClean))) {
        rank = 1;
      } else if (name.startsWith(q) || (qNorm && (nameNorm.startsWith(qNorm) || nameArNorm.startsWith(qNorm)))) {
        rank = 2;
      } else if (sym.includes(q) || (qClean && symClean.includes(qClean))) {
        rank = 3;
      }

      rankedMatches.push({
        rank,
        item: {
          symbol: rawSym,
          exchange: rawEx,
          name: rawName || rawNameAr || rawSym,
          ...(rawNameAr ? { name_ar: rawNameAr } : {}),
          country: itemCountry,
          currency: itemCurrency,
          hasLocal: true,
        },
      });
    }

    if (q) {
      rankedMatches.sort((a, b) => a.rank - b.rank || a.item.symbol.localeCompare(b.item.symbol));
    }

    const results = rankedMatches.slice(0, limit).map((entry) => entry.item);
    return NextResponse.json({ results }, { headers: responseHeaders });
  } catch (err) {
    console.error("Symbols search error:", err);
    return NextResponse.json({ results: [] }, { headers: { "Cache-Control": "no-store" } });
  }
}
