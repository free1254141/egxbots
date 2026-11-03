import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const BACKEND_URL = (
    process.env.PYTHON_BACKEND_URL ||
    process.env.TRADING_SIGNALS_API_URL ||
    "http://127.0.0.1:8000"
).replace(/\/$/, "");

export async function POST(req: NextRequest) {
    try {
        const body = await req.json().catch(() => ({}));
        const text = String(body?.text || "").trim();
        if (!text) {
            return NextResponse.json({ detail: "Text is required for TTS" }, { status: 400 });
        }

        const voice = String(body?.voice || "ar-EG-ShakirNeural");
        const rate = String(body?.rate || "+0%");
        const pitch = String(body?.pitch || "+0Hz");

        const backendRes = await fetch(`${BACKEND_URL}/api/voice/tts`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ text, voice, rate, pitch }),
            cache: "no-store",
        });

        if (!backendRes.ok) {
            const errText = await backendRes.text().catch(() => "Backend TTS failed");
            return NextResponse.json({ detail: errText }, { status: backendRes.status });
        }

        const audioBuffer = await backendRes.arrayBuffer();

        return new NextResponse(audioBuffer, {
            status: 200,
            headers: {
                "Content-Type": "audio/mpeg",
                "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
                "Content-Length": String(audioBuffer.byteLength),
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

    const syntheticReq = new NextRequest(req.url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice }),
    });

    return POST(syntheticReq);
}
