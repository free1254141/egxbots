import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";

export const runtime = "nodejs";

const BACKEND_URL = (
    process.env.PYTHON_BACKEND_URL ||
    process.env.TRADING_SIGNALS_API_URL ||
    "http://127.0.0.1:8000"
).replace(/\/$/, "");

// Global Node.js in-memory LRU cache for 0ms replay and instant audio delivery
const nodeTtsCache = new Map<string, Buffer>();
const MAX_NODE_CACHE_ENTRIES = 500;

function getCacheKey(voice: string, rate: string, text: string): string {
    return crypto.createHash("sha256").update(`${voice}:${rate}:${text}`).digest("hex");
}

export async function POST(req: NextRequest) {
    try {
        const body = await req.json().catch(() => ({}));
        const text = String(body?.text || "").trim();
        if (!text) {
            return NextResponse.json({ detail: "Text is required for TTS" }, { status: 400 });
        }

        const voice = String(body?.voice || "ar-EG-ShakirNeural");
        const rate = String(body?.rate || "+10%");
        const pitch = String(body?.pitch || "+0Hz");

        const cacheKey = getCacheKey(voice, rate, text);

        // 1. Check Node.js memory cache (0ms instant response)
        const cached = nodeTtsCache.get(cacheKey);
        if (cached) {
            return new NextResponse(new Uint8Array(cached), {
                status: 200,
                headers: {
                    "Content-Type": "audio/mpeg",
                    "Content-Length": String(cached.byteLength),
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "X-TTS-Cache": "HIT-NODE-RAM",
                },
            });
        }

        const backendRes = await fetch(`${BACKEND_URL}/api/voice/tts`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ text, voice, rate, pitch }),
        });

        if (!backendRes.ok) {
            const errText = await backendRes.text().catch(() => "Backend TTS failed");
            return NextResponse.json({ detail: errText }, { status: backendRes.status });
        }

        const arrayBuffer = await backendRes.arrayBuffer();
        const buffer = Buffer.from(arrayBuffer);

        // Store in memory cache
        if (buffer.length > 500) {
            if (nodeTtsCache.size >= MAX_NODE_CACHE_ENTRIES) {
                const firstKey = nodeTtsCache.keys().next().value;
                if (firstKey) nodeTtsCache.delete(firstKey);
            }
            nodeTtsCache.set(cacheKey, buffer);
        }

        return new NextResponse(new Uint8Array(buffer), {
            status: 200,
            headers: {
                "Content-Type": "audio/mpeg",
                "Content-Length": String(buffer.byteLength),
                "Cache-Control": "public, max-age=31536000, immutable",
                "X-TTS-Cache": backendRes.headers.get("X-TTS-Cache") || "MISS",
            },
        });
    } catch (err: any) {
        return NextResponse.json(
            { detail: `Failed to proxy TTS synthesis: ${err?.message || err}` },
            { status: 502 }
        );
    }
}

export async function GET(req: NextRequest) {
    const { searchParams } = new URL(req.url);
    const text = (searchParams.get("text") || "").trim();
    if (!text) {
        return NextResponse.json({ detail: "Query parameter 'text' is required" }, { status: 400 });
    }
    const voice = searchParams.get("voice") || "ar-EG-ShakirNeural";
    const rate = searchParams.get("rate") || "+10%";

    const syntheticReq = new NextRequest(req.url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice, rate }),
    });

    return POST(syntheticReq);
}
