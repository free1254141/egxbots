import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND_URL = (
    process.env.PYTHON_BACKEND_URL ||
    process.env.TRADING_SIGNALS_API_URL ||
    "http://127.0.0.1:8000"
).replace(/\/$/, "");

// Global Node.js in-memory LRU cache for 0ms replay and instant audio delivery
const nodeTtsCache = new Map<string, Buffer>();
const MAX_NODE_CACHE_ENTRIES = 500;

function getCacheKey(voice: string, rate: string, pitch: string, text: string): string {
    return crypto.createHash("sha256").update(`${voice}:${rate}:${pitch}:${text}`).digest("hex");
}

function rememberAudio(cacheKey: string, buffer: Buffer): void {
    if (buffer.byteLength <= 500) return;
    if (!nodeTtsCache.has(cacheKey) && nodeTtsCache.size >= MAX_NODE_CACHE_ENTRIES) {
        const firstKey = nodeTtsCache.keys().next().value;
        if (firstKey) nodeTtsCache.delete(firstKey);
    }
    nodeTtsCache.set(cacheKey, buffer);
}

function audioResponse(buffer: Buffer, cacheState: string, provider?: string | null): NextResponse {
    return new NextResponse(new Uint8Array(buffer), {
        status: 200,
        headers: {
            "Content-Type": "audio/mpeg",
            "Content-Length": String(buffer.byteLength),
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-TTS-Cache": cacheState,
            ...(provider ? { "X-TTS-Provider": provider } : {}),
        },
    });
}

async function synthesize(
    text: string,
    voice: string,
    rate: string,
    pitch: string
): Promise<NextResponse> {
    const cacheKey = getCacheKey(voice, rate, pitch, text);

    // 1. Node.js memory cache (0ms instant response)
    const cached = nodeTtsCache.get(cacheKey);
    if (cached) {
        return audioResponse(cached, "HIT-NODE-RAM", "node-ram");
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

    const provider = backendRes.headers.get("X-TTS-Provider");
    const backendCacheState = backendRes.headers.get("X-TTS-Cache") || "MISS";

    // Fallback for runtimes where the backend body is not streamable
    if (!backendRes.body) {
        const arrayBuffer = await backendRes.arrayBuffer();
        const buffer = Buffer.from(arrayBuffer);
        rememberAudio(cacheKey, buffer);
        return audioResponse(buffer, backendCacheState, provider);
    }

    // 2. Stream through to the browser while accumulating the bytes for the
    // Node cache. The user starts receiving audio before the full MP3 is stored.
    const chunks: Buffer[] = [];
    const reader = backendRes.body.getReader();

    const stream = new ReadableStream<Uint8Array>({
        async pull(controller) {
            try {
                const { done, value } = await reader.read();
                if (done) {
                    rememberAudio(cacheKey, Buffer.concat(chunks));
                    controller.close();
                    return;
                }
                if (value && value.byteLength > 0) {
                    chunks.push(Buffer.from(value));
                    controller.enqueue(value);
                }
            } catch (err) {
                controller.error(err);
            }
        },
        cancel(reason) {
            void reader.cancel(reason).catch(() => {});
        },
    });

    return new NextResponse(stream, {
        status: 200,
        headers: {
            "Content-Type": "audio/mpeg",
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-TTS-Cache": backendCacheState,
            ...(provider ? { "X-TTS-Provider": provider } : {}),
        },
    });
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

        return await synthesize(text, voice, rate, pitch);
    } catch (err: any) {
        return NextResponse.json(
            { detail: `Failed to proxy TTS synthesis: ${err?.message || err}` },
            { status: 502 }
        );
    }
}

export async function GET(req: NextRequest) {
    try {
        const { searchParams } = new URL(req.url);
        const text = (searchParams.get("text") || "").trim();
        if (!text) {
            return NextResponse.json({ detail: "Query parameter 'text' is required" }, { status: 400 });
        }
        const voice = searchParams.get("voice") || "ar-EG-ShakirNeural";
        const rate = searchParams.get("rate") || "+10%";
        const pitch = searchParams.get("pitch") || "+0Hz";

        return await synthesize(text, voice, rate, pitch);
    } catch (err: any) {
        return NextResponse.json(
            { detail: `Failed to proxy TTS synthesis: ${err?.message || err}` },
            { status: 502 }
        );
    }
}
