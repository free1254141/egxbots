import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getBackendUrl(): string {
  return (
    process.env.PYTHON_BACKEND_URL ||
    process.env.TRADING_SIGNALS_API_URL ||
    (process.env.VERCEL ? "https://weeasdwee-ai-bot.hf.space" : "http://127.0.0.1:8000")
  ).replace(/\/$/, "");
}

// POST /api/automations/[id]/test — Trigger immediate test execution via Python HF worker
export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = await createSupabaseServerClient(req);
  const { data: { user } } = await auth.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  try {
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
