import { NextResponse } from "next/server";
import { withFoundersOffer } from "@/lib/founders-offer";

/**
 * Anonymous, shareable payment configuration.
 *
 * `/api/payment/easykash/config` resolves the caller's Supabase session so it
 * can return a personalized `is_grandfathered_renewal` flag, which forces
 * `no-store` and a serverless invocation on every pricing page view. Most
 * visitors are anonymous and never need that flag, so this endpoint serves the
 * public configuration from the Edge CDN and the client only falls back to the
 * private route once a user is signed in.
 */
export const runtime = "nodejs";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

const BACKEND_URL = (
  process.env.PYTHON_BACKEND_URL ||
  process.env.TRADING_SIGNALS_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const PUBLIC_CONFIG_HEADERS = {
  "Cache-Control": "public, max-age=60, must-revalidate",
  "Vercel-CDN-Cache-Control": "public, s-maxage=300, stale-while-revalidate=3600",
};

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/payment/easykash/config`, { cache: "no-store" });
    const config = await response.json().catch(() => ({ enabled: false }));
    const finalConfig = response.ok ? await withFoundersOffer(config) : config;

    return NextResponse.json(finalConfig, { status: 200, headers: PUBLIC_CONFIG_HEADERS });
  } catch {
    return NextResponse.json(
      { enabled: false, mode: "disabled", provider: "easykash" },
      { status: 200, headers: { "Cache-Control": "public, max-age=30" } }
    );
  }
}
