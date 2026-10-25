import { NextRequest, NextResponse } from "next/server";
import crypto from "node:crypto";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SECRET =
  process.env.SUPABASE_JWT_SECRET ||
  process.env.RESEND_API_KEY ||
  "egxbots-marketing-secret-key-2026";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CAMPAIGN_RE = /^[a-z0-9_:-]{1,40}$/;
// Only these external hosts may be reached through a *signed* link.
const ALLOWED_EXTERNAL_HOSTS = new Set(["t.me"]);

function expectedSig(channel: string, campaign: string, messageId: string, target: string): string {
  return crypto
    .createHmac("sha256", SECRET)
    .update(`click:${channel}:${campaign}:${messageId}:${target}`)
    .digest("hex")
    .slice(0, 32);
}

function validSig(sig: string, expected: string): boolean {
  const a = Buffer.from(sig);
  const b = Buffer.from(expected);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function isInternalPath(target: string): boolean {
  return target.startsWith("/") && !target.startsWith("//") && !target.includes("\\");
}

/**
 * Records a marketing click and redirects.
 * - Signed links (emails): internal path or allow-listed external host.
 * - Unsigned links (Telegram text messages): internal paths only, so it can never be an open redirect.
 */
export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const channel = sp.get("ch") === "telegram" ? "telegram" : "email";
  const campaign = sp.get("c") || "";
  const messageId = sp.get("m") || "";
  const target = sp.get("to") || "/";
  const sig = sp.get("sig") || "";

  const origin = req.nextUrl.origin;
  const fallback = NextResponse.redirect(new URL("/", origin), 302);

  let destination: string | null = null;
  let signed = false;
  if (sig) {
    signed = validSig(sig, expectedSig(channel, campaign, messageId, target));
    if (!signed) return fallback;
  }

  if (isInternalPath(target)) {
    destination = new URL(target, origin).toString();
  } else if (signed) {
    try {
      const u = new URL(target);
      if (u.protocol === "https:" && ALLOWED_EXTERNAL_HOSTS.has(u.hostname)) destination = u.toString();
    } catch {
      destination = null;
    }
  }
  if (!destination) return fallback;

  if (CAMPAIGN_RE.test(campaign) && (signed || channel === "telegram")) {
    try {
      const service = getSupabaseServiceClient();
      const msgId = UUID_RE.test(messageId) ? messageId : null;
      let userId: string | null = null;
      if (msgId) {
        const { data } = await service
          .from("marketing_message_log")
          .select("user_id")
          .eq("id", msgId)
          .limit(1)
          .maybeSingle();
        userId = data?.user_id ?? null;
      }
      await service.from("marketing_events").insert({
        event_type: "clicked",
        channel,
        campaign,
        message_id: msgId,
        user_id: userId,
        target: target.slice(0, 200),
      });
    } catch (err) {
      console.warn("[marketing/click] could not record click:", err instanceof Error ? err.message : "error");
    }
  }

  const res = NextResponse.redirect(destination, 302);
  res.headers.set("Cache-Control", "no-store");
  return res;
}
