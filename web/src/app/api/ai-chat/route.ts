/**
 * Dedicated Python Chatbot Proxy Route.
 * All chatbot execution has been migrated 100% to Python FastAPI (api/agentic_chat)
 * running permanently on Hugging Face Space (weeasdwee-ai-bot.hf.space) in production.
 *
 * This completely eliminates Vercel Active CPU consumption for chatbot requests.
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

async function proxyToPythonChatbot(req: NextRequest, pathSuffix: string = "") {
  const backendBase = getPythonBackendUrl();
  const search = req.nextUrl.search;
  const targetUrl = `${backendBase}/api/ai_chat${pathSuffix}${search}`;

  const headers = new Headers();
  req.headers.forEach((val, key) => {
    const k = key.toLowerCase();
    if (
      k === "authorization" ||
      k === "cookie" ||
      k === "content-type" ||
      k === "accept" ||
      k === "x-benchmark-test"
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

    const responseHeaders = new Headers();
    res.headers.forEach((val, key) => {
      const k = key.toLowerCase();
      if (
        k === "content-type" ||
        k === "cache-control" ||
        k === "connection" ||
        k === "x-accel-buffering"
      ) {
        responseHeaders.set(k, val);
      }
    });

    return new NextResponse(res.body, {
      status: res.status,
      statusText: res.statusText,
      headers: responseHeaders,
    });
  } catch (err: any) {
    return NextResponse.json(
      {
        error: "PYTHON_CHATBOT_PROXY_ERROR",
        detail: `تعذر الاتصال بخادم الشات بوت (Hugging Face): ${err?.message || String(err)}`,
      },
      { status: 502 }
    );
  }
}

export async function GET(req: NextRequest) {
  return proxyToPythonChatbot(req);
}

export async function POST(req: NextRequest) {
  return proxyToPythonChatbot(req, "/stream");
}

export async function PUT(req: NextRequest) {
  return proxyToPythonChatbot(req);
}

export async function DELETE(req: NextRequest) {
  return proxyToPythonChatbot(req);
}
