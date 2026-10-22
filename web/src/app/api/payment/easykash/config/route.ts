import { NextResponse } from "next/server";
import { withFoundersOffer } from "@/lib/founders-offer";

export const runtime = "nodejs";
// Payment config includes Founders Offer pricing from Supabase RPC — changes
// are infrequent, so we allow the Edge CDN to cache for 5 minutes and serve
// stale while revalidating for up to 1 hour. This eliminates repeated cold
// serverless wakeups on every page-load from different users.
export const preferredRegion = "fra1"; // Prevent multi-region cold starts
const BACKEND_URL = (process.env.PYTHON_BACKEND_URL || process.env.TRADING_SIGNALS_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

// Cache-Control: 5-min Edge CDN cache, 1-hour stale-while-revalidate
const PAYMENT_CONFIG_HEADERS = {
  "Cache-Control": "public, s-maxage=300, stale-while-revalidate=3600, stale-if-error=86400",
};

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/payment/easykash/config`, { cache: "no-store" });
    const config = await response.json().catch(() => ({ enabled: false }));
    const finalConfig = response.ok ? await withFoundersOffer(config) : config;
    return NextResponse.json(finalConfig, {
      status: response.status,
      headers: PAYMENT_CONFIG_HEADERS,
    });
  } catch {
    return NextResponse.json({ enabled: false, mode: "disabled", provider: "easykash" }, { status: 503 });
  }
}
