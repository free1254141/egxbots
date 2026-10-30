import { NextResponse } from "next/server";
import { getSupabaseClient } from "@/lib/supabase/route-data";

export const runtime = "nodejs";
export const revalidate = 3600;
const headers = {
  "Cache-Control": "public, max-age=300",
  "Vercel-CDN-Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
};

export async function GET() {
  try {
    const supabase = getSupabaseClient();
    const { data, error } = await supabase.from("model_metadata").select("*").order("created_at", { ascending: false });
    if (error) return NextResponse.json({ models: [] });
    return NextResponse.json({ models: data || [] }, { headers });
  } catch (error) {
    console.error("Local models route error:", error);
    return NextResponse.json({ models: [] });
  }
}
