import { NextResponse } from "next/server";
import { getSupabaseClient } from "@/lib/supabase/route-data";
import { getAdminChatId, sendTelegramMessage, sendTelegramPhoto } from "@/lib/supportTelegram";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { uploadChatImage } from "@/lib/ai/chat-storage";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

export async function POST(req: Request) {
  try {
    const authClient = await createSupabaseServerClient(req as any);
    const { data: { user } } = await authClient.auth.getUser();
    if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    const body = await req.json().catch(() => ({}));
    const sessionId = String(body.session_id || "");
    const rawContent = String(body.content || "").trim();
    const rawImage = typeof body.image === "string" ? body.image.trim() : null;
    const userName = String(user.user_metadata?.full_name || user.email || "User").slice(0, 120);

    if (!sessionId || (!rawContent && !rawImage)) {
      return NextResponse.json({ ok: false, error: "Missing content or image" }, { status: 400 });
    }
    if (rawContent.length > 5000 || sessionId.length > 128) {
      return NextResponse.json({ ok: false, error: "Invalid input" }, { status: 400 });
    }
    if (sessionId !== user.id) return NextResponse.json({ error: "Invalid support session" }, { status: 403 });

    const content = rawContent || (rawImage ? "صورة مرفقة" : "");

    const supabase = getSupabaseClient();

    let imageUrl: string | null = null;
    if (rawImage) {
      imageUrl = await uploadChatImage(supabase, user.id, sessionId, rawImage);
    }

    const { data, error } = await supabase
      .from("support_messages")
      .insert({
        session_id: sessionId,
        user_id: user.id,
        sender: "user",
        content,
        user_name: userName,
        image_url: imageUrl
      })
      .select("*")
      .single();

    if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 200 });

    // Profile lookup for admin telegram notifications
    const profileRes = await (async () => {
      try {
        return await supabase
          .from("profiles")
          .select("whatsapp_number")
          .eq("id", user.id)
          .maybeSingle();
      } catch {
        return { data: null } as { data: null };
      }
    })();

    let phoneLine = "";
    const profile = profileRes?.data;
    if (profile?.whatsapp_number) {
      phoneLine = `<b>واتساب / الموبايل:</b> <code>${profile.whatsapp_number}</code>\n`;
    }

    // Trigger DeepSeek Support AI Agent asynchronously in Python backend
    try {
      const backendBase =
        process.env.TRADING_SIGNALS_API_URL ||
        process.env.PYTHON_BACKEND_URL ||
        (process.env.NODE_ENV === "production"
          ? "https://weeasdwee-ai-bot.hf.space"
          : "http://127.0.0.1:8000");

      fetch(`${backendBase.replace(/\/$/, "")}/api/support/ai-process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          content,
          user_name: userName,
        }),
      }).catch((e) => {
        console.warn("[SUPPORT_MSG] Backend AI trigger warning:", e?.message);
      });
    } catch (aiTriggerErr) {
      console.warn("[SUPPORT_MSG] AI trigger failed:", aiTriggerErr);
    }

    // Forward to admin on Telegram with Session ID for instant Reply
    try {
      const adminChatId = await getAdminChatId();
      if (adminChatId) {
        const tgText = `👑 <b>[رسالة دعم VIP من عميل Pro]</b>\n` +
          `<b>Session:</b> <code>${sessionId}</code>\n` +
          `<b>العميل:</b> ${userName}\n` +
          `${phoneLine}` +
          `<b>الإيميل:</b> ${user.email || "—"}\n` +
          `---------------------------------\n` +
          `${content}\n\n` +
          `<i>(للرد على العميل: اضغط Reply على هذه الرسالة واكتب ردك)</i>`;

        let photoSent = false;
        if (imageUrl) {
          photoSent = await sendTelegramPhoto(adminChatId, imageUrl, tgText);
        }
        if (!photoSent) {
          const fallbackText = imageUrl ? `${tgText}\n\n🖼️ <b>الصورة المرفقة:</b> ${imageUrl}` : tgText;
          await sendTelegramMessage(adminChatId, fallbackText);
        }
      }
    } catch (tgErr) {
      console.error("Failed to forward support message to Telegram:", tgErr);
    }

    return NextResponse.json({ ok: true, message: data });
  } catch (error) {
    console.error("support message route error:", error);
    return NextResponse.json({ ok: false }, { status: 200 });
  }
}
