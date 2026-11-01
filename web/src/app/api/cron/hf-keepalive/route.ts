import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

/**
 * HF Keep-Alive & Wakeup Ping.
 * Pings the Python backend on Hugging Face Spaces during morning & market hours
 * to prevent cold sleep before user-scheduled morning chat automations.
 */
export async function GET(req: NextRequest) {
  const backendUrl = (
    process.env.PYTHON_BACKEND_URL ||
    process.env.TRADING_SIGNALS_API_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");

  try {
    const res = await fetch(`${backendUrl}/automations/status`, {
      method: "GET",
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });

    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      return NextResponse.json({
        ok: true,
        status: "awake",
        backend: backendUrl,
        cached_automations: data.cached_automations ?? 0,
      });
    }

    return NextResponse.json({
      ok: false,
      status: `backend_http_${res.status}`,
    }, { status: 502 });
  } catch (err: any) {
    return NextResponse.json({
      ok: false,
      error: err.message || "Failed to reach backend",
    }, { status: 503 });
  }
}
