import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { createSupabaseServerClient } from "@/lib/supabase/server";

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
      .select("id,user_id,code,name,discount_percent,commission_percent,is_active,clicks_count,notes")
      .eq("code", rawCode)
      .eq("is_active", true)
      .maybeSingle();

    if (error || !aff) {
      return NextResponse.json({
        valid: false,
        error: "كود الخصم غير صحيح أو منتهي الصلاحية",
      });
    }

    // Check expiration date in notes if configured
    if (aff.notes) {
      try {
        const notesObj = typeof aff.notes === "string" ? JSON.parse(aff.notes) : aff.notes;
        if (notesObj?.expires_at) {
          const expTime = new Date(notesObj.expires_at).getTime();
          if (!isNaN(expTime) && Date.now() > expTime) {
            // Auto deactivate in database
            await supabase
              .from("affiliates")
              .update({
                is_active: false,
                updated_at: new Date().toISOString(),
              })
              .eq("id", aff.id);

            return NextResponse.json({
              valid: false,
              error: "عذراً، هذا الكود الترويجي انتهت صلاحيته",
            });
          }
        }
      } catch {
        // ignore parse errors
      }
    }

    // Prevent self-referral for commission-earning affiliates
    try {
      const auth = await createSupabaseServerClient(req);
      const { data: { user } } = await auth.auth.getUser();
      if (
        user?.id &&
        aff.user_id &&
        String(aff.user_id) === String(user.id) &&
        Number(aff.commission_percent || 0) > 0
      ) {
        return NextResponse.json({
          valid: false,
          self_referral: true,
          error: "لا يمكنك استخدام كود الإحالة الخاص بك على حسابك الشخصي",
        });
      }
    } catch {
      // Guest user or session check skipped
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
