import { NextRequest, NextResponse } from "next/server";
import { requireAdmin } from "@/lib/admin-auth";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { UUID_RE } from "@/lib/admin/admin-exclusions";
import { chunkIds, fetchAllPages, listAllAuthUsers } from "@/lib/admin/supabase-admin-query";
import {
  summarizeFoundersRetention,
  type FounderMemberInput,
  type FounderOrderInput,
  type FounderProfileInput,
  type FounderSubInput,
} from "@/lib/admin/founders-analytics";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1";

const IN_CHUNK_SIZE = 200;

export async function GET(req: NextRequest) {
  const auth = await requireAdmin(req);
  if (auth instanceof Response) return auth;

  try {
    const supabase = getSupabaseServiceClient();

    const [founderMembers, localOrders, kashierOrders] = await Promise.all([
      fetchAllPages<FounderMemberInput>((from, to) =>
        supabase
          .from("founders_offer_members")
          .select("user_id, joined_at")
          .order("joined_at", { ascending: true })
          .range(from, to)
      ),
      fetchAllPages<FounderOrderInput>((from, to) =>
        supabase
          .from("local_payment_orders")
          .select("user_id, plan_id, amount_egp, provider, status, created_at")
          .eq("status", "approved")
          .order("created_at", { ascending: true })
          .range(from, to)
      ),
      fetchAllPages<{
        user_id?: string | null;
        plan_id?: string | null;
        amount_paid?: number | string | null;
        provider?: string | null;
        status?: string | null;
        paid_at?: string | null;
        created_at?: string | null;
      }>((from, to) =>
        supabase
          .from("kashier_payments")
          .select("user_id, plan_id, amount_paid, provider, status, paid_at, created_at")
          .in("status", ["success", "approved", "paid"])
          .order("created_at", { ascending: true })
          .range(from, to)
      ),
    ]);

    const approvedOrders: FounderOrderInput[] = [
      ...localOrders,
      ...kashierOrders.map((k) => ({
        user_id: String(k.user_id || "").trim(),
        plan_id: k.plan_id ?? "pro",
        amount_egp: k.amount_paid ?? 0,
        provider: k.provider ?? "kashier",
        status: "approved",
        created_at: k.paid_at ?? k.created_at ?? null,
      })),
    ];

    const paidUserIds = new Set<string>();
    for (const m of founderMembers) {
      const uid = String(m.user_id || "").trim();
      if (UUID_RE.test(uid)) paidUserIds.add(uid);
    }
    for (const o of approvedOrders) {
      const uid = String(o.user_id || "").trim();
      if (UUID_RE.test(uid)) paidUserIds.add(uid);
    }

    const profilesById = new Map<string, FounderProfileInput>();
    const validUuidList = Array.from(paidUserIds);

    if (validUuidList.length === 0) {
      return NextResponse.json(
        summarizeFoundersRetention({
          founderMembers: [],
          approvedOrders: [],
          subscriptions: [],
          profilesById,
        }),
        { headers: { "Cache-Control": "private, no-store, max-age=0" } }
      );
    }

    const idChunks = chunkIds(validUuidList, IN_CHUNK_SIZE);
    const profilesList: Array<{
      id: string;
      display_name?: string | null;
      username?: string | null;
      whatsapp_number?: string | null;
      telegram_chat_id?: string | null;
    }> = [];
    const subscriptions: FounderSubInput[] = [];

    for (const chunk of idChunks) {
      const [profilesRes, subsBatch] = await Promise.all([
        supabase
          .from("profiles")
          .select("id, display_name, username, whatsapp_number, telegram_chat_id")
          .in("id", chunk),
        fetchAllPages<FounderSubInput>((from, to) =>
          supabase
            .from("subscriptions")
            .select("user_id, plan_id, status, provider, current_period_start, current_period_end, updated_at, created_at")
            .in("user_id", chunk)
            .range(from, to)
        ),
      ]);
      if (profilesRes.error) {
        throw new Error(`profiles: ${profilesRes.error.message || "query failed"}`);
      }
      profilesList.push(...(profilesRes.data || []));
      subscriptions.push(...subsBatch);
    }

    for (const p of profilesList) {
      profilesById.set(String(p.id), {
        id: String(p.id),
        display_name: p.display_name ?? null,
        username: p.username ?? null,
        whatsapp_number: p.whatsapp_number ?? null,
        telegram_chat_id: p.telegram_chat_id ?? null,
      });
    }

    const excludeAdminIds = new Set<string>();
    const authUsers = await listAllAuthUsers(supabase);
    for (const [uid, u] of authUsers.entries()) {
      if (u.is_admin) {
        excludeAdminIds.add(uid);
      }
      if (!paidUserIds.has(uid)) continue;
      const prev = profilesById.get(uid) || { id: uid };
      profilesById.set(uid, {
        ...prev,
        email: u.email || prev.email || null,
        display_name: prev.display_name || u.display_name || null,
      });
    }

    const validMembers = founderMembers.filter((m) => paidUserIds.has(String(m.user_id || "").trim()));
    const validOrders = approvedOrders.filter((o) => paidUserIds.has(String(o.user_id || "").trim()));

    const summary = summarizeFoundersRetention({
      founderMembers: validMembers,
      approvedOrders: validOrders,
      subscriptions,
      profilesById,
      excludeUserIds: excludeAdminIds,
    });

    return NextResponse.json(summary, {
      headers: { "Cache-Control": "private, no-store, max-age=0" },
    });
  } catch (error) {
    console.error("[admin/users/founders] failed:", error);
    return NextResponse.json({ detail: "Failed to load paid retention statistics" }, { status: 500 });
  }
}
