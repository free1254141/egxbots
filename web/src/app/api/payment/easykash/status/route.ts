import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

export async function GET(req: NextRequest) {
  const auth = await createSupabaseServerClient(req);
  const { data: { user } } = await auth.auth.getUser();
  if (!user) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });

  const orderId = req.nextUrl.searchParams.get("order_id") || "";
  if (!orderId) return NextResponse.json({ detail: "Missing order_id" }, { status: 400 });

  try {
    const service = getSupabaseServiceClient();
    const { data: order, error } = await service
      .from("local_payment_orders")
      .select("id,plan_id,amount_egp,status,provider,telegram_invite_link,telegram_invite_expires_at,customer_note")
      .eq("id", orderId)
      .eq("user_id", user.id)
      .maybeSingle();

    if (error || !order) {
      // Fallback to python backend if not found in direct query
      const BACKEND_URL = (process.env.PYTHON_BACKEND_URL || process.env.TRADING_SIGNALS_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
      const { data: { session } } = await auth.auth.getSession();
      if (session?.access_token) {
        const response = await fetch(
          `${BACKEND_URL}/payment/easykash/status?order_id=${encodeURIComponent(orderId)}&user_id=${encodeURIComponent(user.id)}`,
          {
            headers: { Authorization: `Bearer ${session.access_token}` },
            cache: "no-store",
            signal: AbortSignal.timeout(6000),
          }
        );
        if (response.ok) return NextResponse.json(await response.json());
      }
      return NextResponse.json({ detail: "Payment order not found" }, { status: 404 });
    }

    let end: string | null = null;
    let inviteLink = order.telegram_invite_link || "";

    if (order.status === "approved") {
      const { data: sub } = await service
        .from("subscriptions")
        .select("current_period_end")
        .eq("user_id", user.id)
        .in("plan_id", ["pro", "pro_6m", "pro_1y", "lifetime", "pro_lifetime"])
        .eq("status", "active")
        .order("current_period_end", { ascending: false })
        .limit(1)
        .maybeSingle();

      end = sub?.current_period_end || null;

      if (!inviteLink) {
        const { data: invite } = await service
          .from("pro_telegram_invites")
          .select("invite_link")
          .eq("user_id", user.id)
          .maybeSingle();
        inviteLink = invite?.invite_link || "";
      }

      const customerNote = String(order.customer_note || "");
      if (!customerNote.includes("tg_welcomed")) {
        const { data: profile } = await service
          .from("profiles")
          .select("telegram_chat_id, display_name, username")
          .eq("id", user.id)
          .maybeSingle();

        const tgChatId = profile?.telegram_chat_id ? String(profile.telegram_chat_id).trim() : null;
        if (tgChatId) {
          const botToken = (process.env.ARTORO_AI_BOT || process.env.TELEGRAM_BOT_TOKEN)?.trim();
          const relayUrl = (process.env.TELEGRAM_RELAY_URL || "https://api.telegram.org").replace(/\/$/, "");
          if (botToken) {
            const rawDisplayName = profile?.display_name || profile?.username || "المستثمر";
            const displayName = rawDisplayName.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
            const buttons: { text: string; url: string }[][] = [];
            if (inviteLink) {
              buttons.push([{ text: "💎 الانضمام لقناة VIP", url: inviteLink }]);
            }
            buttons.push([{ text: "🌐 فتح حسابك والتقارير", url: "https://egxbots.com/reports" }]);

            const welcomeMsg = `🎉 <b>أهلاً وسهلاً بك يا ${displayName}!</b>\n\n` +
              `✅ <b>تم تأكيد دفع اشتراكك وتفعيل باقة Pro بنجاح!</b> 🚀\n\n` +
              `━━━━━━━━━━━━━━━━━━━━\n` +
              (inviteLink ? `💎 <b>رابط انضمامك الخاص لقناة التوصيات VIP:</b>\n${inviteLink}\n<i>(هذا الرابط شخصي وخاص بحسابك للدخول المباشر)</i>\n\n` : "") +
              `📊 <b>مزايا باقتك المفعّلة الآن:</b>\n` +
              `• إشارات دخول وتنبيهات الأهداف ووقف الخسارة لحظياً على قناة VIP\n` +
              `• وصول كامل لكافة تقارير البورصة المصرية ومساعد الذكاء الاصطناعي ARTORO\n` +
              `• استشارات وتحليلات ذكية لأي سهم تريده عبر هذا الشات\n\n` +
              `━━━━━━━━━━━━━━━━━━━━\n` +
              `💡 <b>كيف تبدأ؟</b>\n` +
              `1. اضغط زر <b>الانضمام لقناة VIP</b> أدناه لمتابعة الإشارات أولاً بأول.\n` +
              `2. اسألني هنا عن أي سهم في البورصة المصرية (مثلاً: اكتب رمز السهم مثل <code>COMI</code> أو <code>TMGH</code>).\n\n` +
              `نتمنى لك تداولات موفقة ومربحة دائماً! 📈`;

            try {
              const tgResp = await fetch(`${relayUrl}/bot${botToken}/sendMessage`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  chat_id: tgChatId,
                  text: welcomeMsg,
                  parse_mode: "HTML",
                  reply_markup: { inline_keyboard: buttons },
                }),
                signal: AbortSignal.timeout(5000),
              });
              if (tgResp.ok) {
                await service
                  .from("local_payment_orders")
                  .update({ customer_note: `${customerNote} | tg_welcomed`.trim() })
                  .eq("id", orderId);
              }
            } catch (err) {
              console.warn("[easykash/status] Telegram welcome dispatch error:", err);
            }
          }
        }
      }
    }

    return NextResponse.json({
      ...order,
      subscription: end ? { current_period_end: end } : null,
      telegram_pro_url: inviteLink,
    });
  } catch (err: any) {
    console.error("[api/payment/easykash/status] error:", err);
    return NextResponse.json({ detail: "Payment status is unavailable" }, { status: 503 });
  }
}

