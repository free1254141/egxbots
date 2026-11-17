import { NextRequest, NextResponse } from "next/server";
import { requireAdmin } from "@/lib/admin-auth";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { fetchAllPages, listAllAuthUsers } from "@/lib/admin/supabase-admin-query";
import {
  summarizeUsersEngagement,
  type ActivityEventRow,
  type ChatbotLimitRow,
  type ChatMessageMetaRow,
  type EngagementUserInput,
  type SubscriptionStatusRow,
} from "@/lib/admin/engagement-segments";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1";

export async function GET(req: NextRequest) {
  const auth = await requireAdmin(req);
  if (auth instanceof Response) return auth;

  try {
    const supabase = getSupabaseServiceClient();

    const [
      authUsers,
      profiles,
      chatbotLimits,
      chatMessages,
      chatLogs,
      schedAutomations,
      activityEvents,
      botSubs,
      vipInvites,
      scannerPositions,
      subscriptions,
      founderMembers,
      approvedLocalOrders,
      kashierPaidOrders,
    ] = await Promise.all([
      listAllAuthUsers(supabase),
      fetchAllPages<{ id: string; display_name?: string | null; username?: string | null }>((from, to) =>
        supabase
          .from("profiles")
          .select("id, display_name, username")
          .range(from, to)
      ),
      fetchAllPages<ChatbotLimitRow>((from, to) =>
        supabase
          .from("ai_chatbot_limits")
          .select("user_id, date, chat_count")
          .range(from, to)
      ),
      fetchAllPages<ChatMessageMetaRow>((from, to) =>
        supabase
          .from("ai_chat_messages")
          .select("user_id, created_at")
          .eq("role", "user")
          .range(from, to)
      ),
      fetchAllPages<{ user_id?: string | null }>((from, to) =>
        supabase
          .from("ai_chatbot_logs")
          .select("user_id")
          .range(from, to)
      ),
      fetchAllPages<{ user_id?: string | null }>((from, to) =>
        supabase
          .from("scheduled_chat_automations")
          .select("user_id")
          .range(from, to)
      ),
      fetchAllPages<ActivityEventRow>((from, to) =>
        supabase
          .from("user_activity_events")
          .select("user_id, event_name, path")
          .not("user_id", "is", null)
          .range(from, to)
      ),
      fetchAllPages<{ user_id?: string | null }>((from, to) =>
        supabase
          .from("bot_subscriptions")
          .select("user_id")
          .range(from, to)
      ),
      fetchAllPages<{ user_id?: string | null }>((from, to) =>
        supabase
          .from("pro_telegram_invites")
          .select("user_id")
          .range(from, to)
      ),
      fetchAllPages<{ user_id?: string | null }>((from, to) =>
        supabase
          .from("positions")
          .select("user_id")
          .eq("source", "tech_scanner")
          .range(from, to)
      ),
      fetchAllPages<SubscriptionStatusRow>((from, to) =>
        supabase
          .from("subscriptions")
          .select("user_id, plan_id, status, current_period_end")
          .range(from, to)
      ),
      fetchAllPages<{ user_id?: string | null }>((from, to) =>
        supabase
          .from("founders_offer_members")
          .select("user_id")
          .range(from, to)
      ),
      fetchAllPages<{ user_id?: string | null }>((from, to) =>
        supabase
          .from("local_payment_orders")
          .select("user_id")
          .eq("status", "approved")
          .range(from, to)
      ),
      fetchAllPages<{ user_id?: string | null }>((from, to) =>
        supabase
          .from("kashier_payments")
          .select("user_id")
          .in("status", ["success", "approved", "paid"])
          .range(from, to)
      ),
    ]);

    const usersById = new Map<string, EngagementUserInput>();
    const excludeAdminIds = new Set<string>();

    for (const p of profiles) {
      const id = String(p.id || "").trim();
      if (!id) continue;
      usersById.set(id, {
        id,
        display_name: p.display_name?.trim() || p.username?.trim() || null,
      });
    }

    for (const [uid, u] of authUsers.entries()) {
      if (u.is_admin) {
        excludeAdminIds.add(uid);
      }
      const prev = usersById.get(uid);
      usersById.set(uid, {
        id: uid,
        email: u.email || prev?.email || null,
        display_name: prev?.display_name || u.display_name || null,
      });
    }

    const extractIds = (rows: Array<{ user_id?: string | null }>) =>
      rows.map((r) => String(r.user_id || "").trim()).filter(Boolean);

    const summary = summarizeUsersEngagement({
      users: Array.from(usersById.values()),
      excludeUserIds: excludeAdminIds,
      chatbotLimits,
      chatMessages,
      chatLogUserIds: extractIds(chatLogs),
      scheduledAutomationUserIds: extractIds(schedAutomations),
      activityEvents,
      botSubscriptionUserIds: extractIds(botSubs),
      proTelegramInviteUserIds: extractIds(vipInvites),
      scannerPositionUserIds: extractIds(scannerPositions),
      subscriptions,
      paidEverUserIds: [
        ...extractIds(founderMembers),
        ...extractIds(approvedLocalOrders),
        ...extractIds(kashierPaidOrders),
      ],
    });

    return NextResponse.json(summary, {
      headers: { "Cache-Control": "private, no-store, max-age=0" },
    });
  } catch (error) {
    console.error("[admin/users/engagement] failed:", error);
    return NextResponse.json({ detail: "Failed to load user engagement segments" }, { status: 500 });
  }
}
