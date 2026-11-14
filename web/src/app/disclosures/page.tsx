import { Metadata } from "next";
import { createClient } from "@supabase/supabase-js";
import DisclosuresClient, { DisclosuresInitialStats } from "./DisclosuresClient";
import type { DisclosureItem } from "@/lib/disclosures-analytics";
import { analyzeDisclosures, DisclosuresAnalyticsResult, SymbolPriceInfo } from "@/lib/disclosures-analytics";

export const revalidate = 86400; // 24-hour cache (until next trading day run)

export const metadata: Metadata = {
  title: "رادار إفصاحات البورصة المصرية وتعاملات الداخليين | EGX BOTS",
  description:
    "متابعة حية ولحظية لإفصاحات الشركات المقيدة بالبورصة المصرية، نماذج المادة 30، تعاملات كبار المساهمين والمطلعين، مع التحليل المالي الفوري بالذكاء الاصطناعي وخريطة السيولة الحصرية.",
  openGraph: {
    title: "رادار إفصاحات البورصة المصرية وتعاملات الداخليين | EGX BOTS",
    description:
      "متابعة حية ولحظية لإفصاحات الشركات المقيدة بالبورصة المصرية، نماذج المادة 30، وتحليل تدفقات السيولة ومتوسط تكلفة الداخليين.",
    url: "https://egxbots.com/disclosures",
    siteName: "EGX BOTS",
    locale: "ar_EG",
    type: "website",
  },
};

const INITIAL_PAGE_SIZE = 24;

async function getInitialDisclosuresData(): Promise<{
  items: DisclosureItem[];
  allPool: DisclosureItem[];
  stats: DisclosuresInitialStats;
  analytics: DisclosuresAnalyticsResult;
  priceMap: Record<string, SymbolPriceInfo>;
}> {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const supabaseKey =
    process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseKey) {
    const emptyAnalytics = analyzeDisclosures([], {});
    return {
      items: [],
      allPool: [],
      stats: { total: 0, buys: 0, sells: 0, shareholding: 0 },
      analytics: emptyAnalytics,
      priceMap: {},
    };
  }

  const supabase = createClient(supabaseUrl, supabaseKey);

  // Fetch initial batch of disclosures, stats pool, latest prices, and company fundamentals in parallel
  const [pageRes, statsRes, pricesRes, fundamentalsRes] = await Promise.all([
    supabase
      .from("egx_disclosures")
      .select(
        "id, symbol, company_name, disclosure_type, disclosure_date, title, raw_content, ai_summary, sentiment, action_type, shares_count, stake_before, stake_after, party_name, party_role, source_url, metadata",
        { count: "exact" }
      )
      .order("disclosure_date", { ascending: false })
      .order("created_at", { ascending: false })
      .limit(INITIAL_PAGE_SIZE),
    supabase
      .from("egx_disclosures")
      .select(
        "id, symbol, company_name, disclosure_type, disclosure_date, title, raw_content, ai_summary, sentiment, action_type, shares_count, stake_before, stake_after, party_name, party_role, source_url, metadata"
      )
      .order("disclosure_date", { ascending: false })
      .limit(2000),
    supabase
      .from("stock_technical_indicators")
      .select("symbol, close, change_pct")
      .limit(350),
    supabase
      .from("stock_fundamentals")
      .select("symbol, data")
      .limit(350),
  ]);

  const allDisclosures = (statsRes.data || []) as DisclosureItem[];
  const priceMap: Record<string, SymbolPriceInfo> = {};
  if (pricesRes.data) {
    for (const p of pricesRes.data) {
      if (p.symbol && p.close != null) {
        priceMap[p.symbol.toUpperCase()] = {
          close: Number(p.close),
          change_pct: p.change_pct != null ? Number(p.change_pct) : 0,
        };
      }
    }
  }

  // Enrich priceMap with verified marketCap and totalShares from fundamentals
  if (fundamentalsRes.data) {
    for (const f of fundamentalsRes.data) {
      if (f.symbol && f.data && typeof f.data === "object") {
        const sym = f.symbol.toUpperCase();
        const mc = (f.data as Record<string, unknown>).marketCap;
        if (typeof mc === "number" && mc > 0) {
          if (priceMap[sym]) {
            priceMap[sym].market_cap = mc;
            if (priceMap[sym].close > 0) {
              priceMap[sym].total_shares = Math.round(mc / priceMap[sym].close);
            }
          } else {
            priceMap[sym] = {
              close: 0,
              change_pct: 0,
              market_cap: mc,
            };
          }
        }
      }
    }
  }

  const analytics = analyzeDisclosures(allDisclosures, priceMap);

  const total = pageRes.count ?? allDisclosures.length;
  const buys = allDisclosures.filter((d) => d.action_type === "buy" || d.sentiment === "bullish").length;
  const sells = allDisclosures.filter((d) => d.action_type === "sell" || d.sentiment === "bearish").length;
  const shareholding = allDisclosures.filter(
    (d) => d.disclosure_type === "major_shareholders" || d.stake_after != null
  ).length;

  return {
    items: (pageRes.data || []) as DisclosureItem[],
    allPool: allDisclosures,
    stats: { total, buys, sells, shareholding },
    analytics,
    priceMap,
  };
}

export default async function DisclosuresPage() {
  const { items, allPool, stats, analytics, priceMap } = await getInitialDisclosuresData();

  return (
    <DisclosuresClient
      initialDisclosures={items}
      initialPool={allPool}
      initialStats={stats}
      initialAnalytics={analytics}
      priceMap={priceMap}
    />
  );
}
