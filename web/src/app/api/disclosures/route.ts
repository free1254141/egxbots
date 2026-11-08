import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const revalidate = 3600;

export async function GET(req: NextRequest) {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseKey) {
    return NextResponse.json({ data: [], total: 0, stats: { total: 0, buys: 0, sells: 0, shareholding: 0 } });
  }

  const { searchParams } = new URL(req.url);
  const limit = Math.min(Math.max(parseInt(searchParams.get("limit") || "12", 10) || 12, 1), 50);
  const offset = Math.max(parseInt(searchParams.get("offset") || "0", 10) || 0, 0);
  const search = (searchParams.get("search") || "").trim();
  const type = (searchParams.get("type") || "all").trim();
  const sentiment = (searchParams.get("sentiment") || "all").trim();

  const supabase = createClient(supabaseUrl, supabaseKey);

  let query = supabase
    .from("egx_disclosures")
    .select(
      "id, symbol, company_name, disclosure_type, disclosure_date, title, raw_content, ai_summary, sentiment, action_type, shares_count, stake_before, stake_after, party_name, party_role, source_url, metadata",
      { count: "exact" }
    )
    .order("disclosure_date", { ascending: false })
    .order("created_at", { ascending: false });

  if (type !== "all") {
    query = query.eq("disclosure_type", type);
  }

  if (sentiment !== "all") {
    if (sentiment === "bullish") {
      query = query.or("sentiment.eq.bullish,action_type.eq.buy");
    } else if (sentiment === "bearish") {
      query = query.or("sentiment.eq.bearish,action_type.eq.sell");
    } else {
      query = query.eq("sentiment", sentiment);
    }
  }

  if (search) {
    const clean = search.replace(/[%_]/g, "");
    query = query.or(
      `symbol.ilike.%${clean}%,company_name.ilike.%${clean}%,title.ilike.%${clean}%,party_name.ilike.%${clean}%`
    );
  }

  const { data, count, error } = await query.range(offset, offset + limit - 1);

  if (error) {
    return NextResponse.json({ data: [], total: 0, error: error.message }, { status: 500 });
  }

  return NextResponse.json(
    {
      data: data || [],
      total: count || 0,
      hasMore: offset + (data?.length || 0) < (count || 0),
    },
    {
      status: 200,
      headers: {
        "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
        "Vercel-CDN-Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
      },
    }
  );
}
