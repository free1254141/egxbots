import { Metadata } from "next";
import { createClient } from "@supabase/supabase-js";
import DisclosuresClient, { DisclosureItem, DisclosuresInitialStats } from "./DisclosuresClient";

export const revalidate = 3600; // Cache on Vercel CDN for 1 hour

export const metadata: Metadata = {
  title: "رادار إفصاحات البورصة المصرية وتعاملات الداخليين | EGX BOTS",
  description:
    "متابعة حية ولحظية لإفصاحات الشركات المقيدة بالبورصة المصرية، نماذج المادة 30، تعاملات كبار المساهمين والمطلعين، مع التحليل المالي الفوري بالذكاء الاصطناعي.",
  openGraph: {
    title: "رادار إفصاحات البورصة المصرية وتعاملات الداخليين | EGX BOTS",
    description:
      "متابعة حية ولحظية لإفصاحات الشركات المقيدة بالبورصة المصرية مع التحليل المالي بالذكاء الاصطناعي.",
    url: "https://egxbots.com/disclosures",
    siteName: "EGX BOTS",
    locale: "ar_EG",
    type: "website",
  },
};

const INITIAL_PAGE_SIZE = 12;

async function getInitialDisclosuresData(): Promise<{
  items: DisclosureItem[];
  stats: DisclosuresInitialStats;
}> {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const supabaseKey =
    process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseKey) {
    return {
      items: [],
      stats: { total: 0, buys: 0, sells: 0, shareholding: 0 },
    };
  }

  const supabase = createClient(supabaseUrl, supabaseKey);

  // Fetch initial 12 items for fast progressive rendering + lightweight KPI projection
  const [pageRes, statsRes] = await Promise.all([
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
      .select("disclosure_type, sentiment, action_type")
      .limit(300),
  ]);

  const rows = statsRes.data || [];
  const total = pageRes.count ?? rows.length;
  const buys = rows.filter((d) => d.action_type === "buy" || d.sentiment === "bullish").length;
  const sells = rows.filter((d) => d.action_type === "sell" || d.sentiment === "bearish").length;
  const shareholding = rows.filter((d) => d.disclosure_type === "major_shareholders").length;

  return {
    items: (pageRes.data || []) as DisclosureItem[],
    stats: { total, buys, sells, shareholding },
  };
}

export default async function DisclosuresPage() {
  const { items, stats } = await getInitialDisclosuresData();

  return <DisclosuresClient initialDisclosures={items} initialStats={stats} />;
}
