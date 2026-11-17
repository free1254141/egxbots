import { NextRequest, NextResponse } from "next/server";
import { getSupabaseClient, getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { requireAdmin } from "@/lib/admin-auth";
import { buildUserUsage } from "@/lib/admin/user-analytics";
import { pickPreferredSubscription } from "@/lib/admin/founders-analytics";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function toCairoDay(iso?: string | null): string | null {
  if (!iso) return null;
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Cairo" }).format(new Date(iso));
  } catch {
    return null;
  }
}

export async function GET(
  _req: NextRequest,
  context: { params: Promise<{ userId: string }> }
) {
  try {
    const auth = await requireAdmin(_req);
    if (auth instanceof Response) return auth;
    const { userId } = await context.params;
    if (!UUID_RE.test(String(userId || "").trim())) {
      return NextResponse.json({ detail: "Invalid user ID" }, { status: 400 });
    }
    const supabase = getSupabaseServiceClient();

    // Query profile
    const { data: profile, error: profileErr } = await supabase
      .from("profiles")
      .select("id, username, display_name, avatar_url, language, telegram_chat_id, whatsapp_number, notification_channel, default_target_pct, default_stop_pct, custom_ai_rules, created_at, updated_at")
      .eq("id", userId)
      .single();

    if (profileErr) return NextResponse.json({ detail: profileErr.message }, { status: 404 });

    // Query related tables with targeted projections & bounded limits
    const [
      subRes,
      botSubRes,
      posRes,
      activityRes,
      chatMessagesRes,
      chatSessionsRes,
      aiAnalyticsRes,
      localPaymentsRes,
      quotaLimitsRes,
      bonusRes,
      tgReminderRes,
      emailLogsRes,
      marketingEvRes,
    ] = await Promise.all([
      supabase
        .from("subscriptions")
        .select("id,user_id,plan_id,status,provider,current_period_start,current_period_end,created_at,updated_at")
        .eq("user_id", userId)
        .order("current_period_end", { ascending: false })
        .limit(10),
      supabase
        .from("bot_subscriptions")
        .select("id,service_type,notifications_enabled,telegram_chat_id,updated_at")
        .eq("user_id", userId)
        .limit(25),
      supabase
        .from("positions")
        .select("id,symbol,name,entry_price,status,quantity,entry_at,created_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(50),
      supabase
        .from("user_activity_events")
        .select("user_id,event_name,path,created_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(1000),
      supabase
        .from("ai_chat_messages")
        .select("user_id,role,content,created_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(300),
      supabase
        .from("ai_chat_sessions")
        .select("id,user_id,title,created_at,updated_at")
        .eq("user_id", userId)
        .order("updated_at", { ascending: false })
        .limit(100),
      supabase
        .from("ai_analytics")
        .select("intent,total_latency_ms,created_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(1000),
      supabase
        .from("local_payment_orders")
        .select("plan_id,amount_egp,status,provider,customer_note,created_at,reviewed_at,payment_review_status,payment_reviewed_at,payment_reviewed_by,auto_activated_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(50),
      supabase
        .from("ai_chatbot_limits")
        .select("date,chat_count")
        .eq("user_id", userId)
        .order("date", { ascending: false })
        .limit(90),
      supabase
        .from("chat_bonus_credits")
        .select("source,credits_granted,credits_used,granted_at")
        .eq("user_id", userId)
        .limit(20),
      supabase
        .from("telegram_subscription_reminder_log")
        .select("reminder_days,status,error,sent_at,created_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(10),
      supabase
        .from("marketing_message_log")
        .select("id,message_type,channel,status,sent_at,provider_message_id")
        .eq("user_id", userId)
        .order("sent_at", { ascending: false })
        .limit(12),
      supabase
        .from("marketing_events")
        .select("message_id,provider_message_id,event_type,channel,created_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(60),
    ]);

    const activityEvents = activityRes?.error ? [] : activityRes?.data || [];
    const chatMessages = chatMessagesRes?.error ? [] : chatMessagesRes?.data || [];
    const chatSessions = chatSessionsRes?.error ? [] : chatSessionsRes?.data || [];
    const aiAnalytics = aiAnalyticsRes?.error ? [] : aiAnalyticsRes?.data || [];

    const activeDaySet = new Set<string>();
    for (const ev of activityEvents) {
      const day = toCairoDay(ev.created_at);
      if (day) activeDaySet.add(day);
    }

    const chatByDay = (quotaLimitsRes?.error ? [] : quotaLimitsRes?.data || []).map((row: any) => ({
      date: String(row.date || ""),
      chat_count: Number(row.chat_count || 0),
    }));
    const totalQuotaChats = chatByDay.reduce((sum: number, row: { chat_count: number }) => sum + row.chat_count, 0);

    const bonusRows = bonusRes?.error ? [] : bonusRes?.data || [];
    const bonusCreditsGranted = bonusRows.reduce((sum: number, r: any) => sum + Number(r.credits_granted || 0), 0);
    const bonusCreditsUsed = bonusRows.reduce((sum: number, r: any) => sum + Number(r.credits_used || 0), 0);

    const recentQuestions = chatMessages
      .filter((m: any) => m.role === "user" && typeof m.content === "string" && m.content.trim())
      .slice(0, 12)
      .map((m: any) => ({
        content: m.content.trim().slice(0, 180),
        created_at: m.created_at,
      }));

    const usage = {
      ...buildUserUsage({
        events: activityEvents,
        chatMessages,
        chatSessions,
        analytics: aiAnalytics,
      }),
      pageTrackingAvailable: !activityRes?.error,
      activeDays: activeDaySet.size,
      totalQuotaChats,
      bonusCreditsGranted,
      bonusCreditsUsed,
      bonusCreditsRemaining: Math.max(0, bonusCreditsGranted - bonusCreditsUsed),
      chatByDay: chatByDay.slice(0, 15),
      recentQuestions,
    };

    const rawEvents = marketingEvRes?.error ? [] : marketingEvRes?.data || [];
    const emailLogs = (emailLogsRes?.error ? [] : emailLogsRes?.data || []).map((log: any) => {
      const matching = rawEvents.filter(
        (ev: any) =>
          (ev.message_id && log.id && ev.message_id === log.id) ||
          (ev.provider_message_id && log.provider_message_id && ev.provider_message_id === log.provider_message_id)
      );
      const types = new Set(matching.map((ev: any) => String(ev.event_type || "").toLowerCase()));
      return {
        id: String(log.id || ""),
        message_type: String(log.message_type || ""),
        channel: String(log.channel || "email"),
        status: String(log.status || ""),
        sent_at: log.sent_at,
        delivered: types.has("delivered"),
        opened: types.has("opened"),
        clicked: types.has("clicked"),
        bounced: types.has("bounced") || types.has("failed"),
      };
    });

    const payments = [
      ...(localPaymentsRes?.error ? [] : localPaymentsRes?.data || []).map((row: any) => ({
        ...row,
        amount: row.amount_egp,
        source: row.provider || "legacy",
      })),
    ];
    const paidPayments = payments.filter((payment: any) =>
      ["success", "approved", "paid"].includes(String(payment.status || "").toLowerCase())
    );

    const subscription = pickPreferredSubscription(subRes?.error ? [] : subRes?.data || []);

    return NextResponse.json(
      {
        profile: profile || {},
        subscription,
        bot_subscriptions: botSubRes?.error ? [] : botSubRes?.data || [],
        open_positions: posRes?.error ? [] : posRes?.data || [],
        recent_scans: [],
        usage,
        notifications: {
          telegramReminders: tgReminderRes?.error ? [] : tgReminderRes?.data || [],
          emailLogs,
        },
        payments: {
          attempts: payments.length,
          successful: paidPayments.length,
          totalPaid: paidPayments.reduce((sum: number, payment: any) => sum + Number(payment.amount || 0), 0),
          currency: paidPayments.find((payment: any) => payment.currency)?.currency || "EGP",
          recent: payments.slice(0, 10),
        },
      },
      { headers: { "Cache-Control": "private, no-store, max-age=0" } }
    );
  } catch {
    return NextResponse.json({ detail: "Internal error" }, { status: 500 });
  }
}

export async function PATCH(
  req: NextRequest,
  context: { params: Promise<{ userId: string }> }
) {
  try {
    const auth = await requireAdmin(req);
    if (auth instanceof Response) return auth;
    const { userId } = await context.params;
    const body = await req.json();
    const allowedFields = [
      "display_name", "language", "telegram_chat_id", "whatsapp_number",
      "notification_channel", "default_target_pct", "default_stop_pct",
      "custom_ai_rules"
    ];
    const safeBody: Record<string, unknown> = {};
    for (const field of allowedFields) {
      if (field in body) safeBody[field] = body[field];
    }
    safeBody.updated_at = new Date().toISOString();

    const supabase = getSupabaseClient();
    const { data, error } = await supabase
      .from("profiles")
      .update(safeBody)
      .eq("id", userId)
      .select("id, username, display_name, avatar_url, language, telegram_chat_id, whatsapp_number, notification_channel, default_target_pct, default_stop_pct, custom_ai_rules, created_at, updated_at")
      .single();
    if (error) return NextResponse.json({ detail: error.message }, { status: 400 });
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ detail: "Internal error" }, { status: 500 });
  }
}

export async function DELETE(
  _req: NextRequest,
  context: { params: Promise<{ userId: string }> }
) {
  try {
    const auth = await requireAdmin(_req);
    if (auth instanceof Response) return auth;
    const { userId } = await context.params;
    const supabase = getSupabaseClient();
    const { error } = await supabase.from("profiles").delete().eq("id", userId);
    if (error) return NextResponse.json({ detail: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ detail: "Internal error" }, { status: 500 });
  }
}
