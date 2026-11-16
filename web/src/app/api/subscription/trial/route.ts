import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { invalidateViewerPlanCache } from "@/lib/supabase/viewer-context";
import {
  extractClientIp,
  hashTrialSignal,
  isDisposableEmail,
  normalizeCanonicalEmail,
} from "@/lib/trial-anti-abuse";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Cache trial status per-user for 5 minutes (private = only browser, not CDN)
// stale-while-revalidate=600 means serve stale for 10 more minutes while refreshing
const TRIAL_CACHE_HEADERS = {
  "Cache-Control": "private, max-age=300, stale-while-revalidate=600",
};

type AbuseCheckInput = {
  userId: string;
  email: string | null | undefined;
  telegramChatId: string | null;
  ipHash: string | null;
  deviceHash: string | null;
};

type AbuseCheckResult =
  | { blocked: false; canonicalEmail: string }
  | { blocked: true; error: string; message: string };

async function checkTrialAbuse(client: any, input: AbuseCheckInput): Promise<AbuseCheckResult> {
  if (isDisposableEmail(input.email)) {
    return {
      blocked: true,
      error: "DISPOSABLE_EMAIL_NOT_ALLOWED",
      message: "التجربة المجانية غير متاحة لعناوين البريد الإلكتروني المؤقتة",
    };
  }

  const canonicalEmail = normalizeCanonicalEmail(input.email);
  const thirtyDaysAgoMs = Date.now() - 30 * 24 * 60 * 60 * 1000;
  const fourteenDaysAgoMs = Date.now() - 14 * 24 * 60 * 60 * 1000;

  // 1. Check active profiles & permanent telegram_linked audit trail across accounts
  if (input.telegramChatId) {
    const [{ data: sameTgProfiles }, { data: tgLinkEvents }] = await Promise.all([
      client
        .from("profiles")
        .select("id")
        .eq("telegram_chat_id", input.telegramChatId)
        .neq("id", input.userId)
        .limit(10),
      client
        .from("user_activity_events")
        .select("user_id")
        .eq("event_name", "telegram_linked")
        .contains("metadata", { telegram_chat_id: input.telegramChatId })
        .neq("user_id", input.userId)
        .limit(20),
    ]);

    const siblingIds = Array.from(
      new Set<string>(
        [...(sameTgProfiles || []), ...(tgLinkEvents || [])]
          .map((p: any) => String(p?.id || p?.user_id || ""))
          .filter(Boolean)
      )
    );
    if (siblingIds.length > 0) {
      const { data: tgTrials } = await client
        .from("subscription_trials")
        .select("user_id")
        .in("user_id", siblingIds)
        .limit(1);
      if (tgTrials && tgTrials.length > 0) {
        return {
          blocked: true,
          error: "TRIAL_ABUSE_TELEGRAM",
          message: "حساب تليجرام المرتبط استخدم الفترة التجريبية مسبقاً على حساب آخر",
        };
      }
    }
  }

  // 2. Check all historical server-logged trial_started events
  const { data: trialEvents } = await client
    .from("user_activity_events")
    .select("user_id, metadata, created_at")
    .eq("event_name", "trial_started")
    .order("created_at", { ascending: false })
    .limit(2000);

  const ipUserIds = new Set<string>();
  for (const row of trialEvents || []) {
    if (!row || row.user_id === input.userId) continue;
    const meta = (row.metadata && typeof row.metadata === "object" ? row.metadata : {}) as Record<string, any>;
    const createdAtMs = row.created_at ? new Date(row.created_at).getTime() : 0;

    if (canonicalEmail && meta.canonical_email === canonicalEmail) {
      return {
        blocked: true,
        error: "TRIAL_ABUSE_EMAIL",
        message: "تم استخدام الفترة التجريبية مسبقاً لهذا البريد الإلكتروني",
      };
    }

    if (input.telegramChatId && meta.telegram_chat_id === input.telegramChatId) {
      return {
        blocked: true,
        error: "TRIAL_ABUSE_TELEGRAM",
        message: "حساب تليجرام المرتبط استخدم الفترة التجريبية مسبقاً على حساب آخر",
      };
    }

    if (input.deviceHash && meta.device_hash === input.deviceHash && createdAtMs >= thirtyDaysAgoMs) {
      return {
        blocked: true,
        error: "TRIAL_ABUSE_DEVICE",
        message: "تم تفعيل فترة تجريبية على هذا الجهاز مسبقاً خلال آخر 30 يوماً",
      };
    }

    if (input.ipHash && meta.ip_hash === input.ipHash && createdAtMs >= fourteenDaysAgoMs && row.user_id) {
      ipUserIds.add(String(row.user_id));
    }
  }

  if (ipUserIds.size >= 2) {
    return {
      blocked: true,
      error: "TRIAL_ABUSE_IP",
      message: "تم تجاوز الحد المسموح للفترات التجريبية من هذه الشبكة",
    };
  }

  return { blocked: false, canonicalEmail };
}

export async function GET(request: Request) {
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

    // Check previous subscriber / founder / profile Telegram status
    const [{ data: approvedOrders }, { data: founderMember }, { data: profileRow }] = await Promise.all([
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
      client
        .from("profiles")
        .select("telegram_chat_id")
        .eq("id", user.id)
        .maybeSingle(),
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

    const ipHash = hashTrialSignal(extractClientIp(request));
    const rawDeviceFp = request.headers.get("x-device-fp")?.trim() || null;
    const deviceHash = hashTrialSignal(rawDeviceFp);
    const telegramChatId = profileRow?.telegram_chat_id ? String(profileRow.telegram_chat_id).trim() : null;

    const abuse = await checkTrialAbuse(client, {
      userId: user.id,
      email: user.email,
      telegramChatId,
      ipHash,
      deviceHash,
    });

    if (abuse.blocked) {
      return NextResponse.json(
        {
          ok: true,
          eligible: false,
          has_used_trial: true,
          reason: abuse.message,
        },
        { headers: TRIAL_CACHE_HEADERS }
      );
    }

    return NextResponse.json(
      {
        ok: true,
        eligible: true,
        has_used_trial: false,
        telegram_linked: Boolean(telegramChatId),
        requires_telegram_link: !telegramChatId,
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

    const body = await request.json().catch(() => ({}));
    const variant = body?.variant === "B" ? "B" : "A";
    const rawDeviceFp =
      (typeof body?.device_fp === "string" && body.device_fp.trim()) ||
      request.headers.get("x-device-fp")?.trim() ||
      null;

    // Reject previous paid subscribers / founders & check Telegram link
    const [{ data: approvedOrders }, { data: founderMember }, { data: profileRow }] = await Promise.all([
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
      client
        .from("profiles")
        .select("telegram_chat_id")
        .eq("id", user.id)
        .maybeSingle(),
    ]);

    if ((approvedOrders && approvedOrders.length > 0) || (founderMember && founderMember.length > 0)) {
      return NextResponse.json(
        { ok: false, error: "PREVIOUS_SUBSCRIBER", message: "التجربة المجانية متاحة فقط للمشتركين الجدد الذين لم يسبق لهم الاشتراك" },
        { status: 400 }
      );
    }

    const telegramChatId = profileRow?.telegram_chat_id ? String(profileRow.telegram_chat_id).trim() : null;
    if (!telegramChatId) {
      return NextResponse.json(
        {
          ok: false,
          error: "TELEGRAM_LINK_REQUIRED",
          telegram_bot_url: `https://t.me/egxbots_bot?start=${user.id}`,
          message: "لتفعيل التجربة المجانية (3 أيام Pro)، اربط حسابك بتليجرام أولاً عبر البوت لحماية الحساب واستلام التنبيهات.",
        },
        { status: 400 }
      );
    }

    const ipHash = hashTrialSignal(extractClientIp(request));
    const deviceHash = hashTrialSignal(rawDeviceFp);

    const abuse = await checkTrialAbuse(client, {
      userId: user.id,
      email: user.email,
      telegramChatId,
      ipHash,
      deviceHash,
    });

    if (abuse.blocked) {
      return NextResponse.json(
        { ok: false, error: abuse.error, message: abuse.message },
        { status: 403 }
      );
    }

    // Call RPC start_pro_trial (try extended 5-arg signature first, fall back to legacy 1-arg signature)
    let rpcRes = await client.rpc("start_pro_trial", {
      p_user_id: user.id,
      p_canonical_email: abuse.canonicalEmail || null,
      p_ip_hash: ipHash,
      p_device_hash: deviceHash,
      p_telegram_chat_id: telegramChatId,
    });

    if (
      rpcRes.error &&
      (rpcRes.error.code === "PGRST202" || String(rpcRes.error.message || "").includes("start_pro_trial"))
    ) {
      rpcRes = await client.rpc("start_pro_trial", {
        p_user_id: user.id,
      });
    }

    const { data, error } = rpcRes;

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

    // Activation telemetry powers the trial funnel AND anti-abuse window checks.
    try {
      await client.from("user_activity_events").insert({
        user_id: user.id,
        event_name: "trial_started",
        path: "/pricing",
        metadata: {
          variant,
          source: "trial_activation",
          canonical_email: abuse.canonicalEmail,
          ip_hash: ipHash,
          device_hash: deviceHash,
          telegram_chat_id: telegramChatId,
        },
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
