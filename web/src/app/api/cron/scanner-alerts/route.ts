import { NextRequest, NextResponse } from "next/server";
import { executeScannerEngine } from "@/lib/scannerAlertsEngine";

export const dynamic = "force-dynamic";
export const maxDuration = 60; // Max duration for Vercel Hobby

export async function GET(req: NextRequest) {
  return handleCron(req);
}

export async function POST(req: NextRequest) {
  return handleCron(req);
}

async function handleCron(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  const cronSecret = process.env.CRON_SECRET;
  const adminSecret = process.env.ADMIN_SECRET_KEY;
  const adminHeader = req.headers.get("x-admin-key");

  // Authentication check (allows Vercel CRON or internal admin key or local testing)
  const isAuthorized =
    !cronSecret ||
    authHeader === `Bearer ${cronSecret}` ||
    (adminSecret && adminHeader === adminSecret) ||
    req.headers.get("x-vercel-cron") === "1";

  if (!isAuthorized) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const url = new URL(req.url);
  const force = url.searchParams.get("force") === "true";
  const forceDispatch = url.searchParams.get("force_dispatch") === "true";

  const chatId = url.searchParams.get("chat_id") || undefined;

  try {
    const result = await executeScannerEngine({
      trigger: chatId ? `Test Run for Chat ${chatId}` : "Cron Scheduler",
      forceMarketHours: force,
      forceDispatch,
      singleRecipientChatId: chatId,
    });

    return NextResponse.json(result);
  } catch (err: any) {
    console.error("[CRON] scanner-alerts failed:", err);
    return NextResponse.json(
      { error: "Scanner alerts execution failed", message: err?.message || String(err) },
      { status: 500 }
    );
  }
}
