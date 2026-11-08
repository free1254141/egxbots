import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { isAllowedAdminEmail } from "@/lib/admin-auth-client";

export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  try {
    const supabase = await createSupabaseServerClient(req);
    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (!session?.user) {
      return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
    }

    const isAdmin = isAllowedAdminEmail(session.user.email);
    const url = new URL(req.url);
    const requestedLicenseId = url.searchParams.get("license_id");

    // 1. Fetch licenses owned by this user
    let query = supabase
      .from("b2b_group_licenses")
      .select("id, tier, daily_limit, daily_used, last_used_date, custom_signature, telegram_chat_id, group_title, status, starts_at, expires_at, order_id, owner_user_id")
      .order("expires_at", { ascending: false });

    if (requestedLicenseId && isAdmin) {
      query = query.eq("id", requestedLicenseId);
    } else if (!isAdmin) {
      query = query.eq("owner_user_id", session.user.id);
    }

    const { data: licenses, error } = await query;

    if (error) {
      return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
    }

    // If admin and no personal license found, fall back to the first available license in DB
    let activeList = licenses || [];
    if (activeList.length === 0 && isAdmin) {
      const { data: allLics } = await supabase
        .from("b2b_group_licenses")
        .select("id, tier, daily_limit, daily_used, last_used_date, custom_signature, telegram_chat_id, group_title, status, starts_at, expires_at, order_id, owner_user_id")
        .order("created_at", { ascending: false })
        .limit(10);
      activeList = allLics || [];
    }

    const primaryLicense = activeList[0] || null;

    return NextResponse.json({
      ok: true,
      has_license: Boolean(primaryLicense),
      license: primaryLicense,
      licenses: activeList,
      is_admin: isAdmin,
      user_email: session.user.email,
    });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const supabase = await createSupabaseServerClient(req);
    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (!session?.user) {
      return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
    }

    const isAdmin = isAllowedAdminEmail(session.user.email);
    const body = await req.json().catch(() => ({}));
    const { action, license_id, code, telegram_chat_id, custom_signature, group_title } = body;

    // Action: Claim license with activation code or order id
    if (action === "claim" || (code && !license_id)) {
      const searchCode = (code || "").trim();
      if (!searchCode) {
        return NextResponse.json({ ok: false, error: "كود التفعيل مطلوب" }, { status: 400 });
      }

      const { data: allLics } = await supabase
        .from("b2b_group_licenses")
        .select("id, order_id, owner_user_id")
        .in("status", ["active", "paused"]);

      const matched = (allLics || []).find((l: any) => {
        const lid = String(l.id || "").toLowerCase();
        const ord = String(l.order_id || "").toLowerCase();
        const sc = searchCode.toLowerCase();
        return lid.startsWith(sc) || ord.includes(sc) || lid === sc;
      });

      if (!matched) {
        return NextResponse.json({ ok: false, error: "كود الترخيص غير صحيح أو منتهي" }, { status: 404 });
      }

      // Link to this user
      const { data: updated, error: linkErr } = await supabase
        .from("b2b_group_licenses")
        .update({
          owner_user_id: session.user.id,
          updated_at: new Date().toISOString(),
        })
        .eq("id", matched.id)
        .select()
        .single();

      if (linkErr) {
        return NextResponse.json({ ok: false, error: linkErr.message }, { status: 500 });
      }

      return NextResponse.json({ ok: true, license: updated, message: "تم ربط الترخيص بحسابك بنجاح!" });
    }

    if (!license_id) {
      return NextResponse.json({ ok: false, error: "license_id is required" }, { status: 400 });
    }

    const updates: Record<string, any> = {
      updated_at: new Date().toISOString(),
    };

    if (typeof custom_signature === "string") {
      updates.custom_signature = custom_signature.slice(0, 150).trim();
    }

    if (typeof group_title === "string") {
      updates.group_title = group_title.slice(0, 100).trim();
    }

    if (telegram_chat_id !== undefined) {
      const parsedChatId = Number(telegram_chat_id);
      if (!isNaN(parsedChatId) && parsedChatId !== 0) {
        updates.telegram_chat_id = parsedChatId;
      }
    }

    let updateQuery = supabase
      .from("b2b_group_licenses")
      .update(updates)
      .eq("id", license_id);

    if (!isAdmin) {
      updateQuery = updateQuery.eq("owner_user_id", session.user.id);
    }

    const { data, error } = await updateQuery.select().single();

    if (error) {
      return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
    }

    return NextResponse.json({ ok: true, license: data });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 });
  }
}
