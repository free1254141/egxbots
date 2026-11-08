import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";

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

    const { data: licenses, error } = await supabase
      .from("b2b_group_licenses")
      .select("id, tier, daily_limit, daily_used, last_used_date, custom_signature, telegram_chat_id, group_title, status, starts_at, expires_at")
      .eq("owner_user_id", session.user.id)
      .order("expires_at", { ascending: false });

    if (error) {
      return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
    }

    return NextResponse.json({
      ok: true,
      has_license: Boolean(licenses && licenses.length > 0),
      license: licenses?.[0] || null,
      licenses: licenses || [],
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

    const body = await req.json().catch(() => ({}));
    const { license_id, telegram_chat_id, custom_signature, group_title } = body;

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

    const { data, error } = await supabase
      .from("b2b_group_licenses")
      .update(updates)
      .eq("id", license_id)
      .eq("owner_user_id", session.user.id)
      .select()
      .single();

    if (error) {
      return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
    }

    return NextResponse.json({ ok: true, license: data });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 });
  }
}
