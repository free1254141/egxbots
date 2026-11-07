import { requireAdmin } from "@/lib/admin-auth";
import { NextRequest, NextResponse } from "next/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1";

const PAID_PLANS = new Set(["pro", "lifetime", "pro_lifetime"]);

export async function GET(req: NextRequest) {
  const auth = await requireAdmin(req);
  if (auth instanceof Response) return auth;

  try {
    const supabase = getSupabaseServiceClient();
    const now = new Date();
    const nowIso = now.toISOString();
    const sevenDaysAgo = new Date(Date.now() - 7 * 86400000).toISOString();
    const thirtyDaysAgo = new Date(Date.now() - 30 * 86400000).toISOString();

    const [
      profilesCountRes,
      recentProfilesCountRes,
      trialsRes,
      subsRes,
      ordersRes,
      foundersRes,
      messagesRes,
      marketingLogsRes,
      recentProfilesRes,
    ] = await Promise.all([
      supabase.from("profiles").select("id", { count: "exact", head: true }),
      supabase.from("profiles").select("id", { count: "exact", head: true }).gte("created_at", sevenDaysAgo),
      supabase.from("subscription_trials").select("user_id,started_at,expires_at").limit(3000),
      supabase.from("subscriptions").select("user_id,plan_id,status,created_at,current_period_start").limit(3000),
      supabase.from("local_payment_orders").select("id,user_id,plan_id,amount_egp,status,created_at").limit(3000),
      supabase.from("founders_offer_members").select("user_id,joined_at").limit(3000),
      supabase.from("ai_chat_messages").select("user_id,created_at").eq("role", "user").gte("created_at", thirtyDaysAgo).limit(5000),
      supabase.from("marketing_message_log").select("id,user_id,email,message_type,sent_at,status").limit(5000),
      supabase.from("profiles").select("id,display_name,username,created_at").order("created_at", { ascending: false }).limit(25),
    ]);

    const totalSignups = profilesCountRes.count || 0;
    const recentSignups7d = recentProfilesCountRes.count || 0;

    const trials = trialsRes.data || [];
    const totalTrials = trials.length;
    let activeTrials = 0;
    let finishedTrials = 0;
    const trialUserIds = new Set<string>();

    for (const t of trials) {
      trialUserIds.add(t.user_id);
      if (t.expires_at && new Date(t.expires_at).getTime() >= now.getTime()) {
        activeTrials += 1;
      } else {
        finishedTrials += 1;
      }
    }

    // Active paid subscribers
    const subs = subsRes.data || [];
    const paidUserIds = new Set<string>();
    for (const s of subs) {
      if (s.status === "active" && s.plan_id && PAID_PLANS.has(s.plan_id)) {
        paidUserIds.add(s.user_id);
      }
    }
    const paidCount = paidUserIds.size;

    // Checkout initiated users
    const orders = ordersRes.data || [];
    const checkoutUserIds = new Set<string>();
    let totalOrdersCount = 0;
    let approvedOrdersCount = 0;
    for (const o of orders) {
      totalOrdersCount += 1;
      if (o.user_id) checkoutUserIds.add(o.user_id);
      if (o.status === "approved") approvedOrdersCount += 1;
    }

    // Founders offer members
    const foundersMembers = foundersRes.data || [];
    const foundersCount = foundersMembers.length;

    // Chat activity among trial users
    const messages = messagesRes.data || [];
    const userMessageCount = new Map<string, number>();
    for (const m of messages) {
      userMessageCount.set(m.user_id, (userMessageCount.get(m.user_id) || 0) + 1);
    }

    let activatedTrials = 0;
    for (const t of trials) {
      if ((userMessageCount.get(t.user_id) || 0) > 0) {
        activatedTrials += 1;
      }
    }

    // Marketing campaigns breakdown
    const logs = marketingLogsRes.data || [];
    const campaignMap = new Map<string, { type: string; count: number; users: Set<string>; lastSent: string }>();
    for (const l of logs) {
      const type = l.message_type || "other";
      const existing = campaignMap.get(type) || { type, count: 0, users: new Set<string>(), lastSent: l.sent_at };
      existing.count += 1;
      if (l.user_id) existing.users.add(l.user_id);
      if (new Date(l.sent_at) > new Date(existing.lastSent)) {
        existing.lastSent = l.sent_at;
      }
      campaignMap.set(type, existing);
    }

    const campaigns = Array.from(campaignMap.values()).map((c) => ({
      type: c.type,
      sent_count: c.count,
      unique_users: c.users.size,
      last_sent_at: c.lastSent,
    })).sort((a, b) => b.sent_count - a.sent_count);

    // Recent users list with their step in the funnel
    const recentProfiles = recentProfilesRes.data || [];
    const recentUsers = recentProfiles.map((p: any) => {
      const hasTrial = trialUserIds.has(p.id);
      const isPaid = paidUserIds.has(p.id);
      const hasCheckout = checkoutUserIds.has(p.id);
      const msgCount = userMessageCount.get(p.id) || 0;
      let stage = "Registered";
      let stageColor = "zinc";
      if (isPaid) {
        stage = "Paid Subscriber 👑";
        stageColor = "emerald";
      } else if (hasCheckout) {
        stage = "Checkout Initiated 💳";
        stageColor = "amber";
      } else if (hasTrial && msgCount > 0) {
        stage = "Trial Activated (Asked Chat) ⚡";
        stageColor = "sky";
      } else if (hasTrial) {
        stage = "Trial Started 🚀";
        stageColor = "purple";
      }

      return {
        id: p.id,
        name: p.display_name || p.username || "User",
        created_at: p.created_at,
        hasTrial,
        hasCheckout,
        isPaid,
        messagesCount: msgCount,
        stage,
        stageColor,
      };
    });

    // Funnel math
    const trialStartRate = totalSignups > 0 ? Math.round((totalTrials / totalSignups) * 1000) / 10 : 0;
    const trialActivationRate = totalTrials > 0 ? Math.round((activatedTrials / totalTrials) * 1000) / 10 : 0;
    const checkoutRate = totalSignups > 0 ? Math.round((checkoutUserIds.size / totalSignups) * 1000) / 10 : 0;
    const paidConversionRate = totalSignups > 0 ? Math.round((paidCount / totalSignups) * 1000) / 10 : 0;
    const trialToPaidRate = totalTrials > 0 ? Math.round((paidCount / totalTrials) * 1000) / 10 : 0;

    return NextResponse.json({
      ok: true,
      timestamp: nowIso,
      funnel: {
        totalSignups,
        recentSignups7d,
        totalTrials,
        activeTrials,
        finishedTrials,
        activatedTrials,
        checkoutUsers: checkoutUserIds.size,
        totalOrdersCount,
        approvedOrdersCount,
        paidCount,
        foundersCount,
        rates: {
          trialStartRate,
          trialActivationRate,
          checkoutRate,
          paidConversionRate,
          trialToPaidRate,
        },
      },
      campaigns,
      recentUsers,
    });
  } catch (error: any) {
    console.error("[admin/growth/funnel]", error);
    return NextResponse.json({ error: error.message || "Growth funnel unavailable" }, { status: 500 });
  }
}
