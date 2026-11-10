/**
 * Dedicated Python Telegram VIP Chat Proxy Route.
 * All Telegram VIP chat execution has been migrated 100% to Python FastAPI (api/native_telegram_vip_chat)
 * running permanently on Hugging Face Space (weeasdwee-ai-bot.hf.space) in production.
 *
 * This completely eliminates Vercel Active CPU consumption for Telegram chat requests.
 * Legacy Node.js pipeline is archived in route.legacy.bak.
 */

import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getPythonBackendUrl(): string {
  let backendUrl =
    process.env.TRADING_SIGNALS_API_URL ||
    process.env.PYTHON_BACKEND_URL ||
    (process.env.NODE_ENV === "production"
      ? "https://weeasdwee-ai-bot.hf.space"
      : "http://127.0.0.1:8000");

  if (process.env.NODE_ENV === "production" && /localhost|127\.0\.0\.1/.test(backendUrl)) {
    backendUrl = "https://weeasdwee-ai-bot.hf.space";
  }
  return backendUrl.replace(/\/$/, "");
}

async function proxyToPythonTelegram(req: NextRequest) {
  const backendBase = getPythonBackendUrl();
  const search = req.nextUrl.search;
  const targetUrl = `${backendBase}/api/telegram/vip-chat${search}`;

  const headers = new Headers();
  req.headers.forEach((val, key) => {
    const k = key.toLowerCase();
    if (
      k === "authorization" ||
      k === "content-type" ||
      k === "accept" ||
      k === "x-admin-key"
    ) {
      headers.set(k, val);
    }
  });

  const init: RequestInit = {
    method: req.method,
    headers,
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  try {
    const res = await fetch(targetUrl, init);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: any) {
    return NextResponse.json(
      {
        ok: false,
        error: `Python Telegram Backend unreachable: ${err?.message || String(err)}`,
      },
      { status: 502 }
    );
  }
}

export async function GET(req: NextRequest) {
  return proxyToPythonTelegram(req);
}

export async function POST(req: NextRequest) {
  return proxyToPythonTelegram(req);
}
