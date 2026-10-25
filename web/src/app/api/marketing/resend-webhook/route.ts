import { NextRequest, NextResponse } from "next/server";
import crypto from "node:crypto";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Resend signs webhooks with Svix. Set RESEND_WEBHOOK_SECRET (whsec_...) from the Resend dashboard.
const EVENT_MAP: Record<string, string> = {
  "email.delivered": "delivered",
  "email.opened": "opened",
  "email.clicked": "clicked",
  "email.bounced": "bounced",
  "email.complained": "complained",
  "email.delivery_delayed": "delivery_delayed",
};

function verifySvix(body: string, id: string, timestamp: string, signatureHeader: string, secret: string): boolean {
  const ts = Number(timestamp);
  if (!Number.isFinite(ts) || Math.abs(Date.now() / 1000 - ts) > 5 * 60) return false;
  const key = Buffer.from(secret.startsWith("whsec_") ? secret.slice(6) : secret, "base64");
  const expected = crypto.createHmac("sha256", key).update(`${id}.${timestamp}.${body}`).digest("base64");
  const expectedBuf = Buffer.from(expected);
  return signatureHeader.split(" ").some((part) => {
    const [version, sig] = part.split(",");
    if (version !== "v1" || !sig) return false;
    const sigBuf = Buffer.from(sig);
    return sigBuf.length === expectedBuf.length && crypto.timingSafeEqual(sigBuf, expectedBuf);
  });
}

export async function POST(req: NextRequest) {
  const secret = process.env.RESEND_WEBHOOK_SECRET?.trim();
  if (!secret) return NextResponse.json({ error: "webhook_not_configured" }, { status: 503 });

  const body = await req.text();
  const svixId = req.headers.get("svix-id") || "";
  const svixTs = req.headers.get("svix-timestamp") || "";
  const svixSig = req.headers.get("svix-signature") || "";
  if (!svixId || !svixTs || !svixSig || !verifySvix(body, svixId, svixTs, svixSig, secret)) {
    return NextResponse.json({ error: "invalid_signature" }, { status: 401 });
  }

  let payload: { type?: string; data?: { email_id?: string } };
  try {
    payload = JSON.parse(body);
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const eventType = EVENT_MAP[payload.type || ""];
  const providerId = payload.data?.email_id;
  if (!eventType || !providerId) return NextResponse.json({ ok: true, ignored: true });

  try {
    const service = getSupabaseServiceClient();
    const { data: msg } = await service
      .from("marketing_message_log")
      .select("id,user_id,message_type")
      .eq("provider_message_id", providerId)
      .limit(1)
      .maybeSingle();
    // Not a marketing email (e.g. transactional): nothing to attribute.
    if (!msg) return NextResponse.json({ ok: true, ignored: true });

    const { error } = await service.from("marketing_events").insert({
      event_type: eventType,
      channel: "email",
      campaign: msg.message_type,
      message_id: msg.id,
      provider_message_id: providerId,
      user_id: msg.user_id,
      svix_id: svixId,
    });
    // Duplicate svix-id (retry) violates the unique index: treat as success.
    if (error && error.code !== "23505") {
      console.warn("[marketing/resend-webhook] insert failed:", error.code || "database_error");
      return NextResponse.json({ error: "db_error" }, { status: 500 });
    }
  } catch (err) {
    console.warn("[marketing/resend-webhook] error:", err instanceof Error ? err.message : "error");
    return NextResponse.json({ error: "server_error" }, { status: 500 });
  }
  return NextResponse.json({ ok: true });
}
