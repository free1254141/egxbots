import { NextRequest, NextResponse } from "next/server";
import {
  resolveRequestMarket,
  getMarketExchange,
  getMarketSupabaseClient,
} from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS, withDailyTag } from "@/lib/cache/daily";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PUBLIC_CACHE_HEADERS = withDailyTag(
  { "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=86400" },
  DAILY_CACHE_TAGS.market,
);

const PRIVATE_NO_STORE_HEADERS = withDailyTag(
  { "Cache-Control": "private, no-store, max-age=0" },
  DAILY_CACHE_TAGS.market,
);

const normalizeDate = (value: string | null): string | null => {
  const date = String(value || "").trim().slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : null;
};

const pickFundamentalText = (payload: any, keys: string[]): string | null => {
  if (!payload || typeof payload !== "object") return null;
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
};

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const market = resolveRequestMarket(req);
  const exchange = getMarketExchange(market);
  const currency = market === "tasi" ? "SAR" : "EGP";
  const explicitMarketParam =
    url.searchParams.has("market") ||
    url.searchParams.has("country") ||
    url.searchParams.has("exchange");
  const responseHeaders = explicitMarketParam ? PUBLIC_CACHE_HEADERS : PRIVATE_NO_STORE_HEADERS;

  const selectedDate = normalizeDate(url.searchParams.get("date") || url.searchParams.get("single_date"));
  const requestedStart = normalizeDate(url.searchParams.get("start") || url.searchParams.get("start_date"));
  const requestedEnd = normalizeDate(url.searchParams.get("end") || url.searchParams.get("end_date"));

  try {
    const supabase = getMarketSupabaseClient(market);
    const { data: dateRows, error: dateError } = await supabase
      .from("market_heatmap")
      .select("captured_at")
      .eq("exchange", exchange)
      .order("captured_at", { ascending: false })
      .limit(12000);
    if (dateError) throw dateError;

    const availableDates: string[] = Array.from(new Set<string>(
      (dateRows || []).map((row: any) => String(row.captured_at || "").slice(0, 10)).filter(Boolean),
    )).sort().reverse();
    if (!availableDates.length) {
      return NextResponse.json(
        { rows: [], available_dates: [], market, exchange, currency },
        { headers: responseHeaders },
      );
    }

    const effectiveDate = selectedDate && availableDates.includes(selectedDate)
      ? selectedDate
      : (selectedDate ? availableDates.find((date) => date <= selectedDate) : availableDates[0]) || availableDates[0];
    const start = requestedStart || effectiveDate;
    const end = requestedEnd || effectiveDate;
    const fromDate = start <= end ? start : end;
    const toDate = start <= end ? end : start;

    const { data: capturedRows, error: rowsError } = await supabase
      .from("market_heatmap")
      .select("symbol,exchange,sector,change_pct,cmf_20,volume,cap,captured_at")
      .eq("exchange", exchange)
      .gte("captured_at", `${fromDate}T00:00:00Z`)
      .lte("captured_at", `${toDate}T23:59:59.999Z`)
      .order("captured_at", { ascending: true })
      .limit(10000);
    if (rowsError) throw rowsError;

    const deduped = new Map<string, any>();
    for (const row of capturedRows || []) {
      const day = String(row.captured_at || "").slice(0, 10);
      const key = `${day}|${row.symbol}`;
      const existing = deduped.get(key);
      if (!existing || String(row.captured_at) > String(existing.captured_at)) deduped.set(key, row);
    }

    const symbols = Array.from(new Set(Array.from(deduped.values()).map((row) => row.symbol).filter(Boolean)));
    const fundamentals = new Map<string, { name?: string | null; name_ar?: string | null; data: any }>();
    const stocksMeta = new Map<string, { name?: string | null; name_ar?: string | null; sector?: string | null }>();

    for (let index = 0; index < symbols.length; index += 200) {
      const chunk = symbols.slice(index, index + 200);
      let { data, error: fundErr } = await supabase
        .from("stock_fundamentals")
        .select("symbol,name,name_ar,data")
        .eq("exchange", exchange)
        .in("symbol", chunk);
      if (fundErr) {
        ({ data } = await supabase
          .from("stock_fundamentals")
          .select("symbol,data")
          .eq("exchange", exchange)
          .in("symbol", chunk));
      }
      for (const row of data || []) {
        fundamentals.set(row.symbol, {
          name: row.name || null,
          name_ar: row.name_ar || null,
          data: row.data || {},
        });
      }

      try {
        let { data: stockRows, error: stockErr } = await supabase
          .from("stocks")
          .select("symbol,name,name_ar,sector")
          .eq("exchange", exchange)
          .in("symbol", chunk);
        if (stockErr) {
          ({ data: stockRows } = await supabase
            .from("stocks")
            .select("symbol,name,sector")
            .eq("exchange", exchange)
            .in("symbol", chunk));
        }
        for (const s of stockRows || []) {
          if (s?.symbol) stocksMeta.set(s.symbol, s);
        }
      } catch {
        // Non-fatal fallback
      }
    }

    const rows = Array.from(deduped.values()).map((row) => {
      const volume = Number(row.volume || 0);
      const tradedValue = Number(row.cap || 0);
      const fundRecord = fundamentals.get(row.symbol);
      const data = fundRecord?.data || {};
      const stockMeta = stocksMeta.get(row.symbol);
      const nameAr =
        stockMeta?.name_ar ||
        fundRecord?.name_ar ||
        pickFundamentalText(data, ["name_ar", "NameAr"]) ||
        null;
      const nameEn =
        pickFundamentalText(data, ["name", "Name", "companyName", "CompanyName"]) ||
        fundRecord?.name ||
        stockMeta?.name ||
        null;
      const resolvedName =
        market === "tasi"
          ? nameAr || nameEn || row.symbol
          : nameEn || nameAr || row.symbol;
      return {
        symbol: row.symbol,
        exchange: row.exchange || exchange,
        currency,
        date: String(row.captured_at).slice(0, 10),
        close: volume > 0 ? tradedValue / volume : 0,
        volume,
        change_pct: Number(row.change_pct || 0),
        cmf_20: Number(row.cmf_20 || 0),
        sector:
          row.sector ||
          pickFundamentalText(data, ["sector", "Sector", "sectorName"]) ||
          stockMeta?.sector ||
          "Other",
        name: resolvedName,
        ...(nameAr ? { name_ar: nameAr } : {}),
      };
    });

    return NextResponse.json(
      {
        rows,
        selected_date: effectiveDate,
        requested_date: selectedDate,
        available_dates: availableDates,
        range_start: fromDate,
        range_end: toDate,
        range_dates: availableDates.filter((date) => date >= fromDate && date <= toDate),
        market,
        exchange,
        currency,
      },
      { headers: responseHeaders },
    );
  } catch (error) {
    console.error("Heatmap API error:", error);
    return NextResponse.json(
      { error: "Failed to load heatmap data" },
      { status: 500, headers: PRIVATE_NO_STORE_HEADERS },
    );
  }
}
