import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { requireAdmin } from "@/lib/admin-auth";

export const runtime = "nodejs";

function getSupabaseAdminClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || "";
  const key = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || "";
  return createClient(url, key);
}

const AFFILIATE_COLS =
  "id,code,name,phone,payment_method,discount_percent,commission_percent,is_active,clicks_count,total_sales_count,total_revenue_egp,total_commission_egp,paid_commission_egp,notes,created_at,updated_at";

export async function GET(request: Request) {
  const auth = await requireAdmin(request);
  if (auth instanceof Response) return auth;
  try {
    const supabase = getSupabaseAdminClient();
    const [affRes, ordersRes] = await Promise.all([
      supabase
        .from("affiliates")
        .select(AFFILIATE_COLS)
        .order("created_at", { ascending: false })
        .limit(100),
      supabase
        .from("local_payment_orders")
        .select(
          "id,user_id,plan_id,amount_egp,status,affiliate_code,discount_amount_egp,commission_amount_egp,commission_status,created_at"
        )
        .not("affiliate_code", "is", null)
        .order("created_at", { ascending: false })
        .limit(50),
    ]);

    if (affRes.error) {
      return NextResponse.json({ error: affRes.error.message }, { status: 500 });
    }

    return NextResponse.json({
      affiliates: affRes.data || [],
      recent_orders: ordersRes.data || [],
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const auth = await requireAdmin(request);
  if (auth instanceof Response) return auth;

  try {
    const body = await request.json();
    const action = String(body.action || "create");
    const supabase = getSupabaseAdminClient();
    const now = new Date().toISOString();

    if (action === "mark_paid") {
      const id = String(body.id || "").trim();
      if (!id) return NextResponse.json({ error: "Missing affiliate id" }, { status: 400 });

      const { data: current, error: fetchErr } = await supabase
        .from("affiliates")
        .select("id,total_commission_egp")
        .eq("id", id)
        .maybeSingle();
      if (fetchErr || !current) {
        return NextResponse.json({ error: "لم يتم العثور على المسوق" }, { status: 404 });
      }

      const { error: updErr } = await supabase
        .from("affiliates")
        .update({
          paid_commission_egp: Number(current.total_commission_egp || 0),
          updated_at: now,
        })
        .eq("id", id);
      if (updErr) return NextResponse.json({ error: updErr.message }, { status: 500 });

      await supabase
        .from("local_payment_orders")
        .update({ commission_status: "paid", updated_at: now })
        .eq("affiliate_id", id)
        .eq("commission_status", "earned");

      return NextResponse.json({ ok: true });
    }

    if (action === "toggle_active") {
      const id = String(body.id || "").trim();
      const isActive = Boolean(body.is_active);
      if (!id) return NextResponse.json({ error: "Missing affiliate id" }, { status: 400 });

      const { error } = await supabase
        .from("affiliates")
        .update({ is_active: isActive, updated_at: now })
        .eq("id", id);
      if (error) return NextResponse.json({ error: error.message }, { status: 500 });
      return NextResponse.json({ ok: true });
    }

    if (action === "delete") {
      const id = String(body.id || "").trim();
      if (!id) return NextResponse.json({ error: "Missing affiliate id" }, { status: 400 });

      const { error } = await supabase.from("affiliates").delete().eq("id", id);
      if (error) return NextResponse.json({ error: error.message }, { status: 500 });
      return NextResponse.json({ ok: true });
    }

    // Create or update affiliate
    const code = String(body.code || "")
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9_-]/g, "");
    const name = String(body.name || "").trim();
    const phone = String(body.phone || "").trim();
    const paymentMethod = String(body.payment_method || "vodafone_cash").trim();
    const discountPercent = Number(body.discount_percent ?? 10);
    const commissionPercent = Number(body.commission_percent ?? 25);
    const notes = String(body.notes || "").trim();

    if (!code || code.length < 2 || code.length > 24) {
      return NextResponse.json(
        { error: "أدخل كود خصم صحيح باللغة الإنجليزية والأرقام (مثال: AMR15)" },
        { status: 400 }
      );
    }
    if (!name) {
      return NextResponse.json({ error: "أدخل اسم المسوق أو القناة" }, { status: 400 });
    }
    if (
      !Number.isFinite(discountPercent) ||
      discountPercent < 0 ||
      discountPercent > 50
    ) {
      return NextResponse.json(
        { error: "نسبة خصم المشتري يجب أن تكون بين 0% و 50%" },
        { status: 400 }
      );
    }
    if (
      !Number.isFinite(commissionPercent) ||
      commissionPercent <= 0 ||
      commissionPercent > 80
    ) {
      return NextResponse.json(
        { error: "نسبة عمولة المسوق يجب أن تكون بين 1% و 80%" },
        { status: 400 }
      );
    }

    const { data, error } = await supabase
      .from("affiliates")
      .upsert(
        {
          code,
          name,
          phone,
          payment_method: paymentMethod,
          discount_percent: discountPercent,
          commission_percent: commissionPercent,
          notes,
          is_active: true,
          updated_at: now,
        },
        { onConflict: "code" }
      )
      .select(AFFILIATE_COLS)
      .single();

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({ ok: true, affiliate: data });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
