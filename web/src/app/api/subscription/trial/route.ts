import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const supabase = await createSupabaseServerClient();
    const {
      data: { user },
      error: authError,
    } = await supabase.auth.getUser();

    if (authError || !user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    let serviceClient: any = null;
    try {
      serviceClient = getSupabaseServiceClient();
    } catch {
      serviceClient = supabase;
    }
    const client = serviceClient || supabase;

    // Check existing trial
    const { data: trialRow } = await client
      .from("subscription_trials")
      .select("started_at, expires_at")
      .eq("user_id", user.id)
      .maybeSingle();

    if (trialRow) {
      const isStillActive = trialRow.expires_at && new Date(trialRow.expires_at).getTime() > Date.now();
      return NextResponse.json({
        ok: true,
        eligible: false,
        has_used_trial: true,
        is_active: isStillActive,
        expires_at: trialRow.expires_at,
        reason: isStillActive ? "فترتك التجريبية نشطة حالياً" : "لقد استخدمت الفترة التجريبية من قبل",
      });
    }

    // Check active paid Pro subscription
    const { data: subRows } = await client
      .from("subscriptions")
      .select("id, plan_id, status, current_period_end")
      .eq("user_id", user.id)
      .eq("status", "active")
      .in("plan_id", ["pro", "lifetime", "pro_lifetime"])
      .limit(1);

    const hasActivePro = (subRows || []).some((r: any) => {
      if (!r.current_period_end) return true;
      return new Date(r.current_period_end).getTime() > Date.now();
    });

    if (hasActivePro) {
      return NextResponse.json({
        ok: true,
        eligible: false,
        has_used_trial: false,
        reason: "لديك بالفعل اشتراك Pro نشط",
      });
    }

    return NextResponse.json({
      ok: true,
      eligible: true,
      has_used_trial: false,
    });
  } catch (err: any) {
    console.error("[api/subscription/trial] GET error:", err);
    return NextResponse.json(
      { ok: false, error: err?.message || "Internal error" },
      { status: 500 }
    );
  }
}

export async function POST() {
  try {
    const supabase = await createSupabaseServerClient();
    const {
      data: { user },
      error: authError,
    } = await supabase.auth.getUser();

    if (authError || !user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    let serviceClient: any = null;
    try {
      serviceClient = getSupabaseServiceClient();
    } catch {
      serviceClient = supabase;
    }
    const client = serviceClient || supabase;

    // Call RPC start_pro_trial
    const { data, error } = await client.rpc("start_pro_trial", {
      p_user_id: user.id,
    });

    if (error) {
      console.error("[api/subscription/trial] RPC error:", error);
      return NextResponse.json(
        { ok: false, error: error.message || "Failed to start trial" },
        { status: 400 }
      );
    }

    if (!data?.success) {
      return NextResponse.json(
        { ok: false, error: data?.error, message: data?.message },
        { status: 400 }
      );
    }

    return NextResponse.json({
      ok: true,
      success: true,
      message: data.message || "تم تفعيل تجربة Pro بنجاح!",
      expires_at: data.expires_at,
    });
  } catch (err: any) {
    console.error("[api/subscription/trial] POST error:", err);
    return NextResponse.json(
      { ok: false, error: err?.message || "Internal error" },
      { status: 500 }
    );
  }
}
