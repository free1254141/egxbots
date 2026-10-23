import { NextRequest, NextResponse } from "next/server";
import { getSupabaseClient } from "@/lib/supabase/route-data";
import { requireAdmin } from "@/lib/admin-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

const PRO_PLANS = new Set(["pro", "lifetime", "pro_lifetime", "pro_6m", "pro_1y"]);

function preferredSubscription(rows: any[]): any | null {
  return [...rows].sort((a, b) => {
    const active = (value: any) => String(value?.status || "").toLowerCase() === "active" ? 1 : 0;
    const lifetime = (value: any) => ["lifetime", "pro_lifetime"].includes(String(value?.plan_id || "").toLowerCase()) ? 1 : 0;
    return active(b) - active(a) || lifetime(b) - lifetime(a) || new Date(b.current_period_end || b.created_at || 0).getTime() - new Date(a.current_period_end || a.created_at || 0).getTime();
  })[0] || null;
}

export async function GET(req: NextRequest) {
  try {
    const auth = await requireAdmin(req);
    if (auth instanceof Response) return auth;
    const url = new URL(req.url);
    const page = Math.max(0, Number(url.searchParams.get("page") || 0));
    const pageSize = Math.min(Math.max(Number(url.searchParams.get("page_size") || 20), 1), 100);
    const search = String(url.searchParams.get("search") || "").trim();
    const plan = String(url.searchParams.get("plan") || "ALL").toUpperCase();
    const supabase = getSupabaseClient();

    // Older deployments do not expose a foreign-key relationship between
    // profiles and subscriptions. Resolve cohorts explicitly instead of using
    // a nested PostgREST join that silently falls back to incomplete data.
    let cohortUserIds: string[] | null = null;
    if (plan === "PRO" || plan === "FREE") {
      const { data: subscriptionRows } = await supabase
        .from("subscriptions")
        .select("user_id,plan_id,status,current_period_end,created_at");
      const nowMs = Date.now();
      const activePro = new Set((subscriptionRows || [])
        .filter((row: any) => {
          if (!PRO_PLANS.has(String(row.plan_id || "").toLowerCase())) return false;
          if (String(row.status || "").toLowerCase() !== "active") return false;
          if (!row.current_period_end) return true;
          const end = new Date(String(row.current_period_end)).getTime();
          return Number.isFinite(end) && end > nowMs;
        })
        .map((row: any) => String(row.user_id)));
      if (plan === "PRO") cohortUserIds = Array.from(activePro) as string[];
      else {
        const { data: profilesForFree } = await supabase.from("profiles").select("id");
        cohortUserIds = (profilesForFree || []).map((row: any) => String(row.id)).filter((id: string) => !activePro.has(id));
      }
      if (!cohortUserIds || !cohortUserIds.length) return NextResponse.json({ users: [], total: 0 });
    } else if (plan === "TELEGRAM") {
      const { data: telegramProfiles } = await supabase.from("profiles").select("id").not("telegram_chat_id", "is", null);
      cohortUserIds = (telegramProfiles || []).map((row: any) => String(row.id));
      if (!cohortUserIds || !cohortUserIds.length) return NextResponse.json({ users: [], total: 0 });
    }

    // Auth emails and metadata names are stored in auth.users.
    let authUsers: any[] = [];
    try {
      const authRes = await supabase.auth.admin.listUsers({ page: 1, perPage: 2000 });
      authUsers = authRes.data?.users || [];
    } catch {
      authUsers = [];
    }
    const emailById = new Map(authUsers.map((user: any) => [String(user.id), user.email || null]));
    const nameById = new Map(authUsers.map((user: any) => [
      String(user.id),
      user.user_metadata?.full_name || user.user_metadata?.name || null
    ]));

    if (search) {
      const searchLower = search.toLowerCase();
      const safeSearch = search.replace(/[(),]/g, " ").trim();

      // 1. Search in authUsers (email, full_name, name, phone, user.id)
      const matchingAuthIds = authUsers
        .filter((user: any) => {
          const email = String(user.email || "").toLowerCase();
          const fullName = String(user.user_metadata?.full_name || "").toLowerCase();
          const name = String(user.user_metadata?.name || "").toLowerCase();
          const phone = String(user.phone || "");
          const id = String(user.id || "").toLowerCase();
          return (
            email.includes(searchLower) ||
            fullName.includes(searchLower) ||
            name.includes(searchLower) ||
            phone.includes(search) ||
            id.includes(searchLower)
          );
        })
        .map((user: any) => String(user.id));

      // 2. Search in profiles table (whatsapp_number, display_name, username)
      let profileMatchIds: string[] = [];
      if (safeSearch) {
        try {
          const { data: pMatches } = await supabase
            .from("profiles")
            .select("id")
            .or(`display_name.ilike.%${safeSearch}%,username.ilike.%${safeSearch}%,whatsapp_number.ilike.%${safeSearch}%`);
          if (pMatches) {
            profileMatchIds = pMatches.map((p: any) => String(p.id));
          }
        } catch {
          // ignore profile search error
        }
      }

      const combinedMatchingIds = Array.from(new Set([...matchingAuthIds, ...profileMatchIds]));
      cohortUserIds = cohortUserIds
        ? cohortUserIds.filter((id) => combinedMatchingIds.includes(id))
        : combinedMatchingIds;

      if (!cohortUserIds.length) {
        return NextResponse.json({ users: [], total: 0 });
      }
    }

    const profileFields = "id, username, display_name, avatar_url, language, telegram_chat_id, whatsapp_number, notification_channel, default_target_pct, default_stop_pct, custom_ai_rules, created_at, updated_at";
    let query = supabase.from("profiles").select(profileFields, { count: "exact" }).order("created_at", { ascending: false });
    if (cohortUserIds) query = query.in("id", cohortUserIds);

    const { data: allMatchingProfiles, error: profileError } = await query;
    if (profileError) return NextResponse.json({ detail: profileError.message }, { status: 500 });
    const matchingProfiles = allMatchingProfiles || [];
    const total = matchingProfiles.length;
    const pageProfiles = matchingProfiles.slice(page * pageSize, page * pageSize + pageSize);
    const pageIds = pageProfiles.map((profile: any) => String(profile.id));

    const [{ data: subscriptionRows }, { data: botRows }, { data: localPaymentRows }] = await Promise.all([
      pageIds.length ? supabase.from("subscriptions").select("user_id,plan_id,status,current_period_end,created_at").in("user_id", pageIds) : Promise.resolve({ data: [] }),
      pageIds.length ? supabase.from("bot_subscriptions").select("user_id,service_type,notifications_enabled").in("user_id", pageIds) : Promise.resolve({ data: [] }),
      pageIds.length ? supabase.from("local_payment_orders").select("user_id,status,payment_review_status,created_at").in("user_id", pageIds).eq("status", "approved").order("created_at", { ascending: false }) : Promise.resolve({ data: [] }),
    ]);
    const subscriptionsByUser = new Map<string, any[]>();
    for (const row of subscriptionRows || []) {
      const id = String(row.user_id);
      subscriptionsByUser.set(id, [...(subscriptionsByUser.get(id) || []), row]);
    }
    const botsByUser = new Map<string, any[]>();
    for (const row of botRows || []) {
      const id = String(row.user_id);
      botsByUser.set(id, [...(botsByUser.get(id) || []), row]);
    }
    const paymentReviewByUser = new Map<string, string>();
    for (const row of localPaymentRows || []) {
      const id = String(row.user_id);
      if (!paymentReviewByUser.has(id)) paymentReviewByUser.set(id, String(row.payment_review_status || "pending_review"));
    }

    const formattedUsers = pageProfiles.map((profile: any) => {
      const bots = botsByUser.get(String(profile.id)) || [];
      return {
        ...profile,
        email: emailById.get(String(profile.id)) || null,
        full_name: nameById.get(String(profile.id)) || profile.display_name || null,
        subscription: preferredSubscription(subscriptionsByUser.get(String(profile.id)) || []),
        bot_subscriptions: bots,
        bot_count: bots.filter((bot: any) => bot.notifications_enabled).length,
        payment_review_status: paymentReviewByUser.get(String(profile.id)) || null,
      };
    });
    return NextResponse.json({ users: formattedUsers, total });
  } catch (e) {
    console.error("[admin/users] list failed:", e);
    return NextResponse.json({ detail: "Internal error" }, { status: 500 });
  }
}
