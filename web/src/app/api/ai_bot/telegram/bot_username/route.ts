import { NextResponse } from "next/server";

export const runtime = "edge";
// Bot username is a static string that never changes at runtime.
// Cache aggressively at the Edge CDN — no serverless function needed after first hit.
export const revalidate = 86400;

const BOT_USERNAME_HEADERS = {
  "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=86400, stale-if-error=604800",
};

export async function GET() {
  return NextResponse.json({ username: "egxbots_bot" }, { headers: BOT_USERNAME_HEADERS });
}
