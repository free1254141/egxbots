import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1";

const BACKEND_URL = (process.env.PYTHON_BACKEND_URL || process.env.TRADING_SIGNALS_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export async function POST(req: NextRequest) {
  try {
    const auth = await createSupabaseServerClient(req);
    const { data: { user } } = await auth.auth.getUser();
    if (!user) {
      return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
    }

    const { data: { session } } = await auth.auth.getSession();
    if (!session?.access_token) {
      return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
    }

    // Call Python backend to trigger failed payment recovery
    const response = await fetch(`${BACKEND_URL}/payment/easykash/failed-recovery`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ user_id: user.id }),
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });

    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  } catch (err: any) {
    console.warn("[api/payment/failed-recovery] error:", err);
    return NextResponse.json({ ok: false, error: "Unavailable" }, { status: 200 });
  }
}
