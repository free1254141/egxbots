import { NextResponse } from "next/server";
import { withFoundersOffer } from "@/lib/founders-offer";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts
const BACKEND_URL = (process.env.PYTHON_BACKEND_URL || process.env.TRADING_SIGNALS_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/payment/easykash/config`, { cache: "no-store" });
    const config = await response.json().catch(() => ({ enabled: false }));
    return NextResponse.json(response.ok ? await withFoundersOffer(config) : config, { status: response.status });
  } catch {
    return NextResponse.json({ enabled: false, mode: "disabled", provider: "easykash" }, { status: 503 });
  }
}
