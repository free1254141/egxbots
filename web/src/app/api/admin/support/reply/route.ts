import { NextRequest, NextResponse } from "next/server";
import { getSupabaseClient } from "@/lib/supabase/route-data";
import { getAdminChatId, sendTelegramMessage } from "@/lib/supportTelegram";
import { requireAdmin } from "@/lib/admin-auth";
import { uploadChatImage } from "@/lib/ai/chat-storage";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

export async function POST(req: NextRequest) {
  try {
    const auth = await requireAdmin(req);
    if (auth instanceof Response) return auth;
    const body = await req.json().catch(() => ({}));
    const sessionId = String(body.session_id || "");
    const rawContent = String(body.content || "").trim();
    const rawImage = typeof body.image === "string" ? body.image.trim() : null;

    if (!sessionId || (!rawContent && !rawImage)) {
      return NextResponse.json({ ok: false, error: "Missing session_id, content, or image" }, { status: 400 });
    }

    const content = rawContent || (rawImage ? "صورة مرفقة" : "");

    const supabase = getSupabaseClient();

    let imageUrl: string | null = null;
    if (rawImage) {
      imageUrl = await uploadChatImage(supabase, "admin", sessionId, rawImage);
    }

    const { data, error } = await supabase
      .from("support_messages")
        .insert({
          session_id: sessionId,
          sender: "admin",
          content,
          user_name: "Admin",
          user_id: sessionId,
          image_url: imageUrl
        })
      .select("*")
      .single();

    if (error) {
      console.error("admin support reply database error:", error);
      return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
    }

    // Fire and forget Telegram confirmation in background without blocking response to admin
    void (async () => {
      try {
        const adminChatId = await getAdminChatId();
        if (adminChatId) {
          const tgText = `✍️ <b>[Support Chat Reply]</b> (Replied via Admin Panel)\n` +
            `<b>Session:</b> <code>${sessionId}</code>\n` +
            `---------------------------------\n` +
            `${content}`;
          await sendTelegramMessage(adminChatId, tgText);
        }
      } catch (tgErr) {
        console.error("Failed to send admin reply confirmation to Telegram:", tgErr);
      }
    })();

    return NextResponse.json({ ok: true, message: data });
  } catch (err: any) {
    console.error("admin support reply route error:", err);
    return NextResponse.json({ ok: false, error: "Internal server error" }, { status: 500 });
  }
}
