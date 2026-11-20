import { createClient } from "@supabase/supabase-js";

export type DividendMarketKey = "egx" | "tasi" | "qatar" | "uae";

export interface DividendHistoryEntry {
  ex_date: string;
  amount: number;
  currency?: string | null;
  record_date?: string | null;
  pay_date?: string | null;
}

export interface StockDividendItem {
  exchange: string;
  market: DividendMarketKey;
  symbol: string;
  name_ar: string;
  name_en: string;
  amount: number;
  currency: string;
  currency_ar: string;
  ex_date: string;
  record_date?: string | null;
  pay_date?: string | null;
  close_price?: number | null;
  yield_pct?: number | null;
  annual_yield_pct?: number | null;
  days_until_ex?: number | null;
  days_until_pay?: number | null;
  status: "upcoming" | "pending_pay" | "paid";
  dates_estimated?: boolean;
  source?: string;
  history?: DividendHistoryEntry[];
}

export interface DividendsCalendarPayload {
  market: DividendMarketKey;
  updatedAt: string | null;
  summary: {
    total: number;
    upcomingCount: number;
    pendingPayCount: number;
    paidRecentCount: number;
  };
  dividends: StockDividendItem[];
}

export async function getServerDividendsCalendar(
  market: DividendMarketKey
): Promise<DividendsCalendarPayload> {
  const empty: DividendsCalendarPayload = {
    market,
    updatedAt: null,
    summary: { total: 0, upcomingCount: 0, pendingPayCount: 0, paidRecentCount: 0 },
    dividends: [],
  };

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const key =
    process.env.SUPABASE_SERVICE_ROLE_KEY ||
    process.env.SUPABASE_SECRET_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) return empty;

  try {
    const sb = createClient(url, key, { auth: { persistSession: false } });
    const { data } = await sb
      .from("market_cache")
      .select("payload,computed_at")
      .eq("cache_key", `dividends_calendar_${market}`)
      .limit(1);

    const row = Array.isArray(data) ? data[0] : null;
    const pl = row?.payload as DividendsCalendarPayload | undefined;
    if (pl && Array.isArray(pl.dividends)) {
      return {
        ...pl,
        market,
        updatedAt: pl.updatedAt || row?.computed_at || null,
      };
    }
  } catch (err) {
    console.error(`[dividends-server] Failed reading ${market}:`, err);
  }
  return empty;
}
