import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { requireAdmin } from "@/lib/admin-auth";

export const runtime = "nodejs";

function getSupabaseAdminClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || "";
  const key = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || "";
  return createClient(url, key);
}

export async function GET(request: Request) {
  const auth = await requireAdmin(request);
  if (auth instanceof Response) return auth;

  try {
    const supabase = getSupabaseAdminClient();

    const { data: licenses, error } = await supabase
      .from("b2b_group_licenses")
      .select("*")
      .order("created_at", { ascending: false });

    if (error) {
      return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
    }

    // Attempt to enrich with owner emails if available
    let enriched = licenses || [];
    try {
      const { data: usersData } = await supabase.auth.admin.listUsers({ perPage: 1000 });
      const userMap = new Map((usersData?.users || []).map((u) => [u.id, u.email || u.phone || ""]));
      enriched = enriched.map((lic) => ({
        ...lic,
        owner_email: userMap.get(lic.owner_user_id) || lic.order_id || "غير معروف",
      }));
    } catch {
      // Fallback without user emails
    }

    // Today's aggregate stats
    const today = new Date().toISOString().slice(0, 10);
    const activeLicenses = enriched.filter((l) => l.status === "active" && new Date(l.expires_at) > new Date());
    const totalDailyUsed = activeLicenses.reduce((sum, l) => sum + (l.daily_used || 0), 0);
    const totalDailyLimit = activeLicenses.reduce((sum, l) => sum + (l.daily_limit || 0), 0);

    const tierPrices: Record<string, number> = {
      b2b_starter: 1000,
      b2b_pro: 1500,
      b2b_enterprise: 2500,
    };
    const estimatedMRR = activeLicenses.reduce((sum, l) => sum + (tierPrices[l.tier] || 1000), 0);

    return NextResponse.json({
      ok: true,
      licenses: enriched,
      stats: {
        total_licenses: enriched.length,
        active_licenses: activeLicenses.length,
        total_daily_used: totalDailyUsed,
        total_daily_limit: totalDailyLimit,
        estimated_mrr_egp: estimatedMRR,
        today_date: today,
      },
    });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const auth = await requireAdmin(request);
  if (auth instanceof Response) return auth;

  try {
    const supabase = getSupabaseAdminClient();
    const body = await request.json().catch(() => ({}));
    const { action, license_id } = body;

    if (!action) {
      return NextResponse.json({ ok: false, error: "action is required" }, { status: 400 });
    }

    // 1. Create a manual B2B license
    if (action === "create") {
      const {
        tier = "b2b_pro",
        group_title = "مجموعة تجريبية",
        telegram_chat_id,
        custom_signature = "⚡ تحليلات خاصة بقناتنا بالتعاون مع EGX BOTS",
        duration_days = 30,
        daily_limit,
        owner_email,
      } = body;

      let owner_user_id: string | null = null;
      if (owner_email) {
        try {
          const { data: usersData } = await supabase.auth.admin.listUsers({ perPage: 1000 });
          const matched = (usersData?.users || []).find((u) => u.email?.toLowerCase() === owner_email.toLowerCase());
          if (matched) owner_user_id = matched.id;
        } catch {}
      }

      const tierLimits: Record<string, number> = {
        b2b_starter: 50,
        b2b_pro: 120,
        b2b_enterprise: 250,
      };
      const finalLimit = daily_limit || tierLimits[tier] || 120;
      const now = new Date();
      const expiresAt = new Date(now.getTime() + duration_days * 24 * 60 * 60 * 1000);

      const parsedChatId = telegram_chat_id ? Number(telegram_chat_id) : null;

      const { data, error } = await supabase
        .from("b2b_group_licenses")
        .insert({
          owner_user_id,
          order_id: `MANUAL_ADMIN_${Date.now()}`,
          tier,
          daily_limit: finalLimit,
          group_title: group_title.slice(0, 100),
          telegram_chat_id: parsedChatId,
          custom_signature: custom_signature.slice(0, 150),
          status: "active",
          starts_at: now.toISOString(),
          expires_at: expiresAt.toISOString(),
        })
        .select()
        .single();

      if (error) {
        return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
      }

      return NextResponse.json({ ok: true, license: data });
    }

    // For all other actions, license_id is required
    if (!license_id) {
      return NextResponse.json({ ok: false, error: "license_id is required" }, { status: 400 });
    }

    // 2. Toggle pause / resume
    if (action === "toggle_pause") {
      const { current_status } = body;
      const newStatus = current_status === "paused" ? "active" : "paused";
      const { data, error } = await supabase
        .from("b2b_group_licenses")
        .update({ status: newStatus, updated_at: new Date().toISOString() })
        .eq("id", license_id)
        .select()
        .single();

      if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
      return NextResponse.json({ ok: true, license: data });
    }

    // 3. Extend license (+30 days)
    if (action === "extend") {
      const days = Number(body.days) || 30;
      const { data: existing } = await supabase
        .from("b2b_group_licenses")
        .select("expires_at")
        .eq("id", license_id)
        .single();

      const currentExp = existing?.expires_at ? new Date(existing.expires_at) : new Date();
      const baseDate = currentExp > new Date() ? currentExp : new Date();
      const newExp = new Date(baseDate.getTime() + days * 24 * 60 * 60 * 1000);

      const { data, error } = await supabase
        .from("b2b_group_licenses")
        .update({
          expires_at: newExp.toISOString(),
          status: "active",
          updated_at: new Date().toISOString(),
        })
        .eq("id", license_id)
        .select()
        .single();

      if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
      return NextResponse.json({ ok: true, license: data });
    }

    // 4. Update configuration (limits, signature, chat_id, group_title)
    if (action === "update") {
      const updates: Record<string, any> = {
        updated_at: new Date().toISOString(),
      };
      if (body.custom_signature !== undefined) updates.custom_signature = String(body.custom_signature).slice(0, 150).trim();
      if (body.group_title !== undefined) updates.group_title = String(body.group_title).slice(0, 100).trim();
      if (body.daily_limit !== undefined) updates.daily_limit = Math.max(1, Number(body.daily_limit) || 50);
      if (body.tier !== undefined) updates.tier = body.tier;
      if (body.telegram_chat_id !== undefined) {
        updates.telegram_chat_id = body.telegram_chat_id ? Number(body.telegram_chat_id) : null;
      }
      if (body.status !== undefined) updates.status = body.status;

      const { data, error } = await supabase
        .from("b2b_group_licenses")
        .update(updates)
        .eq("id", license_id)
        .select()
        .single();

      if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
      return NextResponse.json({ ok: true, license: data });
    }

    // 5. Delete license
    if (action === "delete") {
      const { error } = await supabase
        .from("b2b_group_licenses")
        .delete()
        .eq("id", license_id);

      if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
      return NextResponse.json({ ok: true, deleted: true });
    }

    return NextResponse.json({ ok: false, error: "Unknown action" }, { status: 400 });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 });
  }
}
