import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import crypto from "crypto";

function getSupabaseAdmin() {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || "";
    const key = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
    return createClient(url, key);
}

export async function POST(req: Request) {
    try {
        const formData = await req.formData();
        const file = formData.get("file");
        if (!file || !(file instanceof Blob)) {
            return NextResponse.json({ error: "Missing audio file" }, { status: 400 });
        }

        const userId = (formData.get("userId") as string) || "anonymous";
        const sessionId = (formData.get("sessionId") as string) || "voice";
        const buffer = Buffer.from(await file.arrayBuffer());

        const mimeType = file.type || "audio/webm";
        let ext = "webm";
        if (mimeType.includes("mp4")) ext = "mp4";
        else if (mimeType.includes("ogg")) ext = "ogg";
        else if (mimeType.includes("wav")) ext = "wav";
        else if (mimeType.includes("mpeg") || mimeType.includes("mp3")) ext = "mp3";

        const fileId = crypto.randomUUID();
        const safeSession = sessionId.replace(/[^a-zA-Z0-9_-]/g, "_");
        const safeUser = userId.replace(/[^a-zA-Z0-9_-]/g, "_");
        const filePath = `${safeUser}/${safeSession}/${fileId}.${ext}`;

        const supabase = getSupabaseAdmin();
        const { error: uploadError } = await supabase.storage
            .from("chat-audio")
            .upload(filePath, buffer, {
                contentType: mimeType,
                upsert: true,
                cacheControl: "31536000",
            });

        if (uploadError) {
            console.error("[VoiceUpload] Storage upload error:", uploadError);
            return NextResponse.json({ error: uploadError.message }, { status: 500 });
        }

        const { data: publicUrlData } = supabase.storage
            .from("chat-audio")
            .getPublicUrl(filePath);

        return NextResponse.json({
            ok: true,
            url: publicUrlData?.publicUrl || null,
            filePath,
        });
    } catch (e: any) {
        console.error("[VoiceUpload] Error:", e);
        return NextResponse.json({ error: e?.message || "Internal server error" }, { status: 500 });
    }
}
