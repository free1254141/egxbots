import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

function getSupabaseAdminClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || "";
  const key = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || "";
  return createClient(url, key);
}

const AFFILIATE_COLS =
  "id,user_id,code,name,phone,payment_method,discount_percent,commission_percent,is_active,clicks_count,total_sales_count,total_revenue_egp,total_commission_egp,paid_commission_egp,created_at,updated_at";

function generateUserCode(email: string, userId: string): string {
  const emailPart = (email.split("@")[0] || "EGX")
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "")
    .slice(0, 6);
  const idSuffix = userId.replace(/-/g, "").toUpperCase().slice(0, 3);
  const base = emailPart.length >= 3 ? emailPart : "EGX";
  return `${base}${idSuffix}`;
}

export async function GET(req: NextRequest) {
  const auth = await createSupabaseServerClient(req);
  const {
    data: { user },
  } = await auth.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const supabase = getSupabaseAdminClient();

    let { data: aff } = await supabase
      .from("affiliates")
      .select(AFFILIATE_COLS)
      .eq("user_id", user.id)
      .maybeSingle();

    if (!aff) {
      const { data: profile } = await supabase
        .from("profiles")
        .select("display_name, username, whatsapp_number")
        .eq("id", user.id)
        .maybeSingle();

      const displayName =
        profile?.display_name ||
        profile?.username ||
        user.user_metadata?.full_name ||
        user.user_metadata?.name ||
        (user.email ? user.email.split("@")[0] : "شريك EGX BOTS");

      let candidateCode = generateUserCode(user.email || "", user.id);
      const { data: existingCode } = await supabase
        .from("affiliates")
        .select("id")
        .eq("code", candidateCode)
        .maybeSingle();
      if (existingCode) {
        candidateCode = `EGX${user.id.replace(/-/g, "").toUpperCase().slice(0, 6)}`;
      }

      // Leave phone empty initially so user must enter their mobile wallet number to unlock their link
      const { data: created, error: createErr } = await supabase
        .from("affiliates")
        .insert({
          user_id: user.id,
          code: candidateCode,
          name: String(displayName).slice(0, 80),
          phone: "",
          payment_method: "vodafone_cash",
          discount_percent: 10,
          commission_percent: 25,
          is_active: true,
        })
        .select(AFFILIATE_COLS)
        .single();

      if (createErr) {
        return NextResponse.json({ error: createErr.message }, { status: 500 });
      }
      aff = created;
    }

    const { data: referrals } = await supabase
      .from("local_payment_orders")
      .select("id,plan_id,amount_egp,status,commission_amount_egp,commission_status,created_at")
      .eq("affiliate_id", aff.id)
      .eq("status", "approved")
      .order("created_at", { ascending: false })
      .limit(20);

    return NextResponse.json({
      affiliate: aff,
      referrals: referrals || [],
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  const auth = await createSupabaseServerClient(req);
  const {
    data: { user },
  } = await auth.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await req.json().catch(() => ({}));
    const supabase = getSupabaseAdminClient();

    const { data: current } = await supabase
      .from("affiliates")
      .select("id,code")
      .eq("user_id", user.id)
      .maybeSingle();

    if (!current) {
      return NextResponse.json({ error: "Affiliate profile not found" }, { status: 404 });
    }

    const normalizedPhone = String(body.phone || "").replace(/[\s-]/g, "");
    if (!/^01[0125]\d{8}$/.test(normalizedPhone)) {
      return NextResponse.json(
        {
          error:
            "أدخل رقم موبايل مصري صحيح (11 رقم: 010 / 011 / 012 / 015) مسجل عليه محفظة إلكترونية",
        },
        { status: 400 }
      );
    }

    const patch: Record<string, unknown> = {
      phone: normalizedPhone,
      payment_method: "vodafone_cash",
      updated_at: new Date().toISOString(),
    };

    if (typeof body.name === "string" && body.name.trim()) {
      patch.name = body.name.trim().slice(0, 80);
    }
    if (typeof body.code === "string" && body.code.trim()) {
      const cleanCode = body.code
        .trim()
        .toUpperCase()
        .replace(/[^A-Z0-9_-]/g, "");
      if (cleanCode.length < 3 || cleanCode.length > 20) {
        return NextResponse.json(
          { error: "الكود يجب أن يكون بين 3 و 20 حرفاً أو رقماً بالإنجليزية" },
          { status: 400 }
        );
      }
      if (cleanCode !== current.code) {
        const { data: taken } = await supabase
          .from("affiliates")
          .select("id")
          .eq("code", cleanCode)
          .neq("id", current.id)
          .maybeSingle();
        if (taken) {
          return NextResponse.json(
            { error: "هذا الكود مستخدم بالفعل، اختر كوداً آخر" },
            { status: 400 }
          );
        }
        patch.code = cleanCode;
      }
    }

    const { data: updated, error } = await supabase
      .from("affiliates")
      .update(patch)
      .eq("id", current.id)
      .select(AFFILIATE_COLS)
      .single();

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({ ok: true, affiliate: updated });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
