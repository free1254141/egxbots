import { Metadata } from "next";
import { createClient } from "@supabase/supabase-js";
import DisclosuresClient, { DisclosureItem } from "./DisclosuresClient";

export const revalidate = 3600; // Cache on Vercel CDN for 1 hour

export const metadata: Metadata = {
  title: "رادار إفصاحات البورصة المصرية وتعاملات الداخليين | EGX BOTS",
  description: "متابعة حية ولحظية لإفصاحات الشركات المقيدة بالبورصة المصرية، نماذج المادة 30، تعاملات كبار المساهمين والمطلعين، مع التحليل المالي الفوري بالذكاء الاصطناعي.",
  openGraph: {
    title: "رادار إفصاحات البورصة المصرية وتعاملات الداخليين | EGX BOTS",
    description: "متابعة حية ولحظية لإفصاحات الشركات المقيدة بالبورصة المصرية مع التحليل المالي بالذكاء الاصطناعي.",
    url: "https://egxbots.com/disclosures",
    siteName: "EGX BOTS",
    locale: "ar_EG",
    type: "website",
  },
};

async function getDisclosures(): Promise<DisclosureItem[]> {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseKey) {
    return [];
  }

  const supabase = createClient(supabaseUrl, supabaseKey);

  const { data, error } = await supabase
    .from("egx_disclosures")
    .select("id, symbol, company_name, disclosure_type, disclosure_date, title, raw_content, ai_summary, sentiment, action_type, shares_count, party_name, party_role, source_url, metadata")
    .order("disclosure_date", { ascending: false })
    .limit(200);

  if (error || !data) {
    console.error("Failed to fetch disclosures:", error);
    return [];
  }

  return data as DisclosureItem[];
}

export default async function DisclosuresPage() {
  const disclosures = await getDisclosures();

  return (
    <DisclosuresClient initialDisclosures={disclosures} />
  );
}
