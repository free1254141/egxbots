import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const runtime = "nodejs";

function getSupabaseAdminClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || "";
  const key = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || "";
  return createClient(url, key);
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const rawCode = (searchParams.get("code") || "").trim().toUpperCase();
  const track = searchParams.get("track") === "1";

  if (!rawCode || rawCode.length > 32) {
    return NextResponse.json({ valid: false, error: "كود الخصم غير صالح" }, { status: 400 });
  }

  try {
    const supabase = getSupabaseAdminClient();
    const { data: aff, error } = await supabase
      .from("affiliates")
      .select("id,code,name,discount_percent,is_active,clicks_count")
      .eq("code", rawCode)
      .eq("is_active", true)
      .maybeSingle();

    if (error || !aff) {
      return NextResponse.json({
        valid: false,
        error: "كود الخصم غير صحيح أو منتهي الصلاحية",
      });
    }

    if (track) {
      await supabase
        .from("affiliates")
        .update({
          clicks_count: Number(aff.clicks_count || 0) + 1,
          updated_at: new Date().toISOString(),
        })
        .eq("id", aff.id);
    }

    return NextResponse.json({
      valid: true,
      code: aff.code,
      name: aff.name,
      discount_percent: Number(aff.discount_percent || 0),
    });
  } catch {
    return NextResponse.json({
      valid: false,
      error: "تعذر التحقق من الكود حالياً",
    }, { status: 500 });
  }
}
