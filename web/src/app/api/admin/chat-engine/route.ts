import { NextRequest, NextResponse } from "next/server";
import { getSupabaseClient } from "@/lib/supabase/route-data";
import { runPipeline } from "@/lib/ai/pipeline";
import { getDeepSeekApiKey, getNvidiaApiKeys } from "@/lib/ai/server-secrets";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

export async function POST(req: NextRequest) {
    const adminKey = req.headers.get("x-admin-key") || req.headers.get("authorization")?.replace("Bearer ", "");
    const expectedKey = process.env.ADMIN_SECRET_KEY?.trim() || "";
    const host = req.headers.get("host") || "";
    const isLocal = host.includes("localhost") || host.includes("127.0.0.1");

    if (!isLocal && (!expectedKey || adminKey !== expectedKey)) {
        return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
    }

    try {
        const body = await req.json();
        const message = typeof body.message === "string" ? body.message.trim() : "";
        if (!message) {
            return NextResponse.json({ ok: false, error: "Message is required" }, { status: 400 });
        }

        const supabase = getSupabaseClient();
        const deepSeekKey = getDeepSeekApiKey();
        const apiKeys = [...getNvidiaApiKeys(), ...(deepSeekKey ? [deepSeekKey] : [])];

        const sessionState = { current_symbol: null, last_symbols: [], summary: null, current_sector: null };
        const images = Array.isArray(body.images) ? body.images : (typeof body.image === "string" ? [body.image] : []);
        const skipReview = body.skipReview !== undefined ? Boolean(body.skipReview) : true;
        const result = await runPipeline(
            message,
            images,
            sessionState,
            null,
            [],
            supabase,
            apiKeys,
            body.userId || "admin-benchmark",
            body.sessionId || "admin-bench-session",
            `admin-${Date.now()}`,
            "deepseek-flash",
            { isPro: true, chatSource: body.chatSource || "benchmark", skipReview }
        );

        return NextResponse.json({
            ok: true,
            response: result.response,
            tools: (result.tools?.results || []).map((r: any) => r.tool),
            usage: result.usage,
            publication_review: result.publication_review,
            response_origin: result.response_origin,
        });
    } catch (err: any) {
        return NextResponse.json({ ok: false, error: String(err?.message || err) }, { status: 500 });
    }
}
