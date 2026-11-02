import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { createSupabaseServerClient } from "@/lib/supabase/server";

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

// PUT /api/automations/[id] — Update an automation
export async function PUT(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = await createSupabaseServerClient(req);
  const { data: { user } } = await auth.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  try {
    const supabase = getSupabaseAdminClient();
    const body = await req.json();

    const updates: Record<string, any> = {
      updated_at: new Date().toISOString(),
    };

    if (body.name !== undefined) updates.name = String(body.name).trim().slice(0, 80);
    if (body.prompt !== undefined) updates.prompt = String(body.prompt).trim();
    if (body.scheduled_time !== undefined) {
      const t = String(body.scheduled_time).trim();
      if (!/^([01]\d|2[0-3]):([0-5]\d)$/.test(t)) {
        return NextResponse.json({ error: "صيغة الوقت غير صالحة (HH:MM)" }, { status: 400 });
      }
      updates.scheduled_time = t;
      // Reset last_run_date when user changes scheduled time so the new time can fire today
      updates.last_run_date = null;
    }
    if (body.days_of_week !== undefined) {
      updates.days_of_week = body.days_of_week === "all_days" ? "all_days" : "trading_days";
      updates.last_run_date = null;
    }
    if (body.telegram_chat_id !== undefined) {
      updates.telegram_chat_id = body.telegram_chat_id ? String(body.telegram_chat_id).trim() : null;
    }
    if (body.is_active !== undefined) {
      if (body.is_active === true) {
        const { data: profile } = await supabase
          .from("profiles")
          .select("telegram_chat_id")
          .eq("id", user.id)
          .maybeSingle();

        const hasChat = body.telegram_chat_id || profile?.telegram_chat_id;
        if (!hasChat) {
          return NextResponse.json(
            { error: "لا يمكن تفعيل الأتمتة بدون ربط بوت تليجرام أولاً.", requires_telegram: true },
            { status: 400 }
          );
        }
      }
      updates.is_active = Boolean(body.is_active);
    }

    const { data: updated, error } = await supabase
      .from("scheduled_chat_automations")
      .update(updates)
      .eq("id", id)
      .eq("user_id", user.id)
      .select()
      .maybeSingle();

    if (error || !updated) {
      return NextResponse.json({ error: error?.message || "Automation not found" }, { status: 404 });
    }

    // Ping HF worker cache sync
    fetch(`${getBackendUrl()}/automations/sync`, { method: "POST" }).catch(() => {});

    return NextResponse.json({ ok: true, automation: updated });
  } catch (err: any) {
    return NextResponse.json({ error: err.message || "Failed to update automation" }, { status: 500 });
  }
}

// DELETE /api/automations/[id] — Delete an automation
export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = await createSupabaseServerClient(req);
  const { data: { user } } = await auth.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  try {
    const supabase = getSupabaseAdminClient();
    const { error } = await supabase
      .from("scheduled_chat_automations")
      .delete()
      .eq("id", id)
      .eq("user_id", user.id);

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    // Ping HF worker cache sync
    fetch(`${getBackendUrl()}/automations/sync`, { method: "POST" }).catch(() => {});

    return NextResponse.json({ ok: true, message: "Deleted successfully" });
  } catch (err: any) {
    return NextResponse.json({ error: err.message || "Failed to delete automation" }, { status: 500 });
  }
}

// POST /api/automations/[id]/test — Execute immediate test run via HF
export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = await createSupabaseServerClient(req);
  const { data: { user } } = await auth.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  try {
    // Forward test-run execution request to Python backend
    const resp = await fetch(`${getBackendUrl()}/automations/test-run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ automation_id: id }),
      cache: "no-store",
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      return NextResponse.json({ error: data.detail || "Test run execution failed" }, { status: resp.status });
    }

    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message || "Could not reach Python backend for test run" }, { status: 503 });
  }
}
