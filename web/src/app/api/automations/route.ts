import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { isAllowedAdminEmail } from "@/lib/admin-auth-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getSupabaseAdminClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || "";
  const key = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || "";
  return createClient(url, key);
}

function getBackendUrl(): string {
  return (
    process.env.PYTHON_BACKEND_URL ||
    process.env.TRADING_SIGNALS_API_URL ||
    (process.env.VERCEL ? "https://weeasdwee-ai-bot.hf.space" : "http://127.0.0.1:8000")
  ).replace(/\/$/, "");
}

async function isUserPro(supabase: ReturnType<typeof getSupabaseAdminClient>, user: { id: string; email?: string | null }): Promise<boolean> {
  if (isAllowedAdminEmail(user.email)) return true;

  // `profiles` has no `role` column; selecting it raised 42703 on every call.
  // Entitlement is derived from the subscription rows below.
  const { data: subs } = await supabase
    .from("subscriptions")
    .select("plan_id,status,current_period_end")
    .eq("user_id", user.id)
    .in("status", ["active", "trialing"])
    .order("current_period_end", { ascending: false })
    .limit(1);

  if (subs && subs.length > 0) {
    const endStr = String(subs[0].current_period_end || "");
    if (endStr.includes("2126") || new Date(endStr).getTime() > Date.now()) {
      return true;
    }
  }

  return false;
}

// GET /api/automations — List user's automations
export async function GET(req: NextRequest) {
  const auth = await createSupabaseServerClient(req);
  const { data: { user } } = await auth.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const supabase = getSupabaseAdminClient();
    const pro = await isUserPro(supabase, user);

    const { data: profile } = await supabase
      .from("profiles")
      .select("telegram_chat_id")
      .eq("id", user.id)
      .maybeSingle();

    const { data: automations, error } = await supabase
      .from("scheduled_chat_automations")
      .select("id,user_id,name,prompt,scheduled_time,days_of_week,telegram_chat_id,is_active,last_run_at,last_status,last_error,created_at,updated_at")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    const tgLinked = Boolean(profile?.telegram_chat_id);

    return NextResponse.json({
      automations: automations || [],
      count: (automations || []).length,
      max_allowed: 5,
      is_pro: pro,
      telegram_linked: tgLinked,
      default_telegram_chat_id: profile?.telegram_chat_id || null,
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message || "Failed to load automations" }, { status: 500 });
  }
}

// POST /api/automations — Create new scheduled automation
export async function POST(req: NextRequest) {
  const auth = await createSupabaseServerClient(req);
  const { data: { user } } = await auth.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const supabase = getSupabaseAdminClient();
    const pro = await isUserPro(supabase, user);

    if (!pro) {
      return NextResponse.json(
        { error: "هذه الميزة متاحة فقط لمشتركي باقة Pro. يرجى ترقية حسابك للاستفادة من أتمتة الذكاء الاصطناعي." },
        { status: 403 }
      );
    }

    const { count } = await supabase
      .from("scheduled_chat_automations")
      .select("id", { count: "exact", head: true })
      .eq("user_id", user.id);

    if ((count || 0) >= 5) {
      return NextResponse.json(
        { error: "لقد وصلت إلى الحد الأقصى للمهام المجدولة (5 مهام). يمكنك تعديل أو حذف مهمة حالية." },
        { status: 400 }
      );
    }

    const body = await req.json();
    const name = String(body.name || "استشارة مجدولة").trim().slice(0, 80);
    const prompt = String(body.prompt || "").trim();
    const scheduledTime = String(body.scheduled_time || "").trim();
    const daysOfWeek = body.days_of_week === "all_days" ? "all_days" : "trading_days";
    const telegramChatId = body.telegram_chat_id ? String(body.telegram_chat_id).trim() : null;

    // Verify Telegram Bot is activated/linked for this user
    const { data: profile } = await supabase
      .from("profiles")
      .select("telegram_chat_id")
      .eq("id", user.id)
      .maybeSingle();

    const effectiveTgChatId = telegramChatId || (profile?.telegram_chat_id ? String(profile.telegram_chat_id).trim() : null);
    if (!effectiveTgChatId) {
      return NextResponse.json(
        {
          error: "يجب تفعيل وربط بوت تليجرام أولاً لتتمكن من إنشاء واستلام الأتمتة اليومية.",
          requires_telegram: true,
        },
        { status: 400 }
      );
    }

    if (!prompt || prompt.length < 3) {
      return NextResponse.json({ error: "يرجى كتابة سؤال أو استفسار واضح للبوت (3 أحرف على الأقل)." }, { status: 400 });
    }

    if (!/^([01]\d|2[0-3]):([0-5]\d)$/.test(scheduledTime)) {
      return NextResponse.json({ error: "صيغة الوقت غير صالحة. يجب أن تكون بتنسيق HH:MM (مثال 08:30)." }, { status: 400 });
    }

    const { data: created, error } = await supabase
      .from("scheduled_chat_automations")
      .insert({
        user_id: user.id,
        name: name || "استشارة مجدولة",
        prompt,
        scheduled_time: scheduledTime,
        days_of_week: daysOfWeek,
        telegram_chat_id: effectiveTgChatId,
        is_active: true,
      })
      .select()
      .single();

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    // Ping HF background worker to update its in-memory schedule cache immediately (non-blocking)
    fetch(`${getBackendUrl()}/automations/sync`, { method: "POST" }).catch(() => {});

    return NextResponse.json({ ok: true, automation: created }, { status: 201 });
  } catch (err: any) {
    return NextResponse.json({ error: err.message || "Failed to create automation" }, { status: 500 });
  }
}
