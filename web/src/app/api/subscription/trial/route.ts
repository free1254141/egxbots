import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { invalidateViewerPlanCache } from "@/lib/supabase/viewer-context";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Cache trial status per-user for 5 minutes (private = only browser, not CDN)
// stale-while-revalidate=600 means serve stale for 10 more minutes while refreshing
const TRIAL_CACHE_HEADERS = {
  "Cache-Control": "private, max-age=300, stale-while-revalidate=600",
};

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
      return NextResponse.json(
        {
          ok: true,
          eligible: false,
          has_used_trial: true,
          is_active: isStillActive,
          expires_at: trialRow.expires_at,
          reason: isStillActive ? "فترتك التجريبية نشطة حالياً" : "لقد استخدمت الفترة التجريبية من قبل",
        },
        { headers: TRIAL_CACHE_HEADERS }
      );
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
      return NextResponse.json(
        {
          ok: true,
          eligible: false,
          has_used_trial: false,
          reason: "لديك بالفعل اشتراك Pro نشط",
        },
        { headers: TRIAL_CACHE_HEADERS }
      );
    }

    // Check if user previously had an approved paid subscription or is a founders offer member
    const [{ data: approvedOrders }, { data: founderMember }] = await Promise.all([
      client
        .from("local_payment_orders")
        .select("id")
        .eq("user_id", user.id)
        .eq("status", "approved")
        .limit(1),
      client
        .from("founders_offer_members")
        .select("user_id")
        .eq("user_id", user.id)
        .limit(1),
    ]);

    if ((approvedOrders && approvedOrders.length > 0) || (founderMember && founderMember.length > 0)) {
      return NextResponse.json(
        {
          ok: true,
          eligible: false,
          has_used_trial: false,
          reason: "التجربة المجانية متاحة فقط للمشتركين الجدد الذين لم يسبق لهم الاشتراك",
        },
        { headers: TRIAL_CACHE_HEADERS }
      );
    }

    return NextResponse.json(
      {
        ok: true,
        eligible: true,
        has_used_trial: false,
      },
      { headers: TRIAL_CACHE_HEADERS }
    );
  } catch (err: any) {
    console.error("[api/subscription/trial] GET error:", err);
    return NextResponse.json(
      { ok: false, error: err?.message || "Internal error" },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
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

    // Reject users who previously had an approved paid subscription or are founders offer members
    const [{ data: approvedOrders }, { data: founderMember }] = await Promise.all([
      client
        .from("local_payment_orders")
        .select("id")
        .eq("user_id", user.id)
        .eq("status", "approved")
        .limit(1),
      client
        .from("founders_offer_members")
        .select("user_id")
        .eq("user_id", user.id)
        .limit(1),
    ]);

    if ((approvedOrders && approvedOrders.length > 0) || (founderMember && founderMember.length > 0)) {
      return NextResponse.json(
        { ok: false, error: "PREVIOUS_SUBSCRIBER", message: "التجربة المجانية متاحة فقط للمشتركين الجدد الذين لم يسبق لهم الاشتراك" },
        { status: 400 }
      );
    }

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

    try {
      invalidateViewerPlanCache(user.id);
    } catch {
      // ignore
    }

    // Activation telemetry powers the trial funnel (started -> chat -> paid).
    // It is inserted server-side so a closed tab or a blocked analytics call
    // cannot hide the activation.
    try {
      const body = await request.json().catch(() => ({}));
      const variant = body?.variant === "B" ? "B" : "A";
      await client.from("user_activity_events").insert({
        user_id: user.id,
        event_name: "trial_started",
        path: "/pricing",
        metadata: { variant, source: "trial_activation" },
      });
    } catch (logError) {
      console.warn("[api/subscription/trial] trial_started log skipped:", logError);
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
