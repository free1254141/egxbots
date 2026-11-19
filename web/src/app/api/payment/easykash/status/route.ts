import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

const NO_STORE_HEADERS = { "Cache-Control": "private, no-store, max-age=0" };
const VIP_ELIGIBLE_PLAN_IDS = new Set([
  "pro",
  "pro_renewal",
  "pro_6m",
  "pro_1y",
  "lifetime",
  "pro_lifetime",
  "vip_only",
]);

function mergeCustomerNote(existing: unknown, addition: string): string {
  const existingClean = String(existing || "").trim();
  const addClean = String(addition || "").trim();
  if (!existingClean) return addClean;
  if (!addClean) return existingClean;
  const parts = existingClean.split("|").map((p) => p.trim()).filter(Boolean);
  for (const seg of addClean.split("|").map((s) => s.trim()).filter(Boolean)) {
    if (!parts.includes(seg)) parts.push(seg);
  }
  return parts.join(" | ");
}

function isSubmittedLeaseExpired(updatedAt: unknown, ttlMs = 300_000): boolean {
  if (!updatedAt) return true;
  const ts = Date.parse(String(updatedAt));
  if (!Number.isFinite(ts)) return true;
  return Date.now() - ts > ttlMs;
}

// Short 8-second in-memory cache to debounce rapid consecutive status requests for the same order
const orderStatusCache = new Map<string, { payload: any; expiresAt: number }>();

export async function GET(req: NextRequest) {
  const auth = await createSupabaseServerClient(req);
  const { data: { user } } = await auth.auth.getUser();
  if (!user) return NextResponse.json({ detail: "Unauthorized" }, { status: 401, headers: NO_STORE_HEADERS });

  const orderId = req.nextUrl.searchParams.get("order_id") || "";
  if (!orderId) return NextResponse.json({ detail: "Missing order_id" }, { status: 400, headers: NO_STORE_HEADERS });

  const now = Date.now();
  const cacheKey = `${user.id}:${orderId}`;
  const cached = orderStatusCache.get(cacheKey);
  if (orderStatusCache.size > 500) {
    orderStatusCache.clear();
  } else if (orderStatusCache.size > 200) {
    for (const [k, v] of orderStatusCache.entries()) {
      if (v.expiresAt <= now) orderStatusCache.delete(k);
    }
  }
  if (cached && now < cached.expiresAt) {
    return NextResponse.json(cached.payload, { headers: NO_STORE_HEADERS });
  }

  try {
    const service = getSupabaseServiceClient();
    const { data: order, error } = await service
      .from("local_payment_orders")
      .select("id,plan_id,amount_egp,duration_days,status,provider,updated_at,telegram_invite_link,telegram_invite_expires_at,customer_note,affiliate_id,affiliate_code,commission_amount_egp,commission_status")
      .eq("id", orderId)
      .eq("user_id", user.id)
      .eq("provider", "easykash")
      .maybeSingle();

    // If order is pending/submitted, reconcile in real time with EasyKash
    if (order && (order.status === "pending" || order.status === "submitted")) {
      const easykashKey = (process.env.EASYKASH_API_KEY || "").trim();
      if (easykashKey) {
        try {
          const inqRes = await fetch("https://back.easykash.net/api/cash-api/inquire", {
            method: "POST",
            headers: {
              authorization: easykashKey,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ customerReference: orderId }),
            signal: AbortSignal.timeout(6000),
          });

          if (inqRes.ok) {
            const inqData = await inqRes.json();
            const ekStatus = String(inqData?.status || "").toUpperCase();
            const easykashRef = String(inqData?.easykashRef || "");
            const method = String(inqData?.PaymentMethod || "");
            const nowIso = new Date().toISOString();

            if (ekStatus === "PAID") {
              const BACKEND_URL = (process.env.PYTHON_BACKEND_URL || process.env.TRADING_SIGNALS_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
              try {
                const { data: { session } } = await auth.auth.getSession();
                await fetch(`${BACKEND_URL}/payment/easykash/status?order_id=${encodeURIComponent(orderId)}&user_id=${encodeURIComponent(user.id)}`, {
                  headers: session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {},
                  signal: AbortSignal.timeout(6000),
                });
              } catch {}
              const { data: refreshed } = await service
                .from("local_payment_orders")
                .select("id,plan_id,amount_egp,duration_days,status,provider,telegram_invite_link,telegram_invite_expires_at,customer_note,affiliate_id,affiliate_code,commission_amount_egp,commission_status")
                .eq("id", orderId)
                .maybeSingle();
              if (refreshed) Object.assign(order, refreshed);
            } else if (["FAILED", "FAIL", "REJECTED"].includes(ekStatus)) {
              const canTransition =
                order.status === "pending" ||
                (order.status === "submitted" && isSubmittedLeaseExpired(order.updated_at));
              if (canTransition) {
                const note = mergeCustomerNote(
                  order.customer_note,
                  `EasyKash: ${ekStatus} (${method}) | ref: ${easykashRef}`.trim()
                );
                let updQ = service
                  .from("local_payment_orders")
                  .update({ status: "failed", payment_review_status: "rejected", customer_note: note, updated_at: nowIso })
                  .eq("id", orderId);
                if (order.status === "submitted") {
                  updQ = updQ.eq("status", "submitted");
                  if (order.updated_at) updQ = updQ.eq("updated_at", order.updated_at);
                } else {
                  updQ = updQ.eq("status", "pending");
                }
                const { data: updRows } = await updQ.select("id");
                if (updRows && updRows.length > 0) {
                  order.status = "failed";
                  order.customer_note = note;
                }
              }
            } else if (["EXPIRED", "CANCELLED", "CANCELED"].includes(ekStatus)) {
              const canTransition =
                order.status === "pending" ||
                (order.status === "submitted" && isSubmittedLeaseExpired(order.updated_at));
              if (canTransition) {
                const note = mergeCustomerNote(
                  order.customer_note,
                  `EasyKash: ${ekStatus} (${method}) | ref: ${easykashRef}`.trim()
                );
                let updQ = service
                  .from("local_payment_orders")
                  .update({ status: "expired", customer_note: note, updated_at: nowIso })
                  .eq("id", orderId);
                if (order.status === "submitted") {
                  updQ = updQ.eq("status", "submitted");
                  if (order.updated_at) updQ = updQ.eq("updated_at", order.updated_at);
                } else {
                  updQ = updQ.eq("status", "pending");
                }
                const { data: updRows } = await updQ.select("id");
                if (updRows && updRows.length > 0) {
                  order.status = "expired";
                  order.customer_note = note;
                }
              }
            }
          }
        } catch (inqErr) {
          console.warn("[easykash/status] real-time inquiry sync error:", inqErr);
        }
      }
    }

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
        if (response.ok) {
          const data = await response.json();
          orderStatusCache.set(cacheKey, { payload: data, expiresAt: now + 8000 });
          return NextResponse.json(data, { headers: NO_STORE_HEADERS });
        }
      }
      return NextResponse.json({ detail: "Payment order not found" }, { status: 404, headers: NO_STORE_HEADERS });
    }

    let end: string | null = null;
    let inviteLink = order.telegram_invite_link || "";
    let b2bDashboardUrl = "";
    const isB2BOrder = String(order.plan_id || "").trim().toLowerCase().startsWith("b2b_");

    if (order.status === "approved") {
      if (isB2BOrder) {
        const { data: lic } = await service
          .from("b2b_group_licenses")
          .select("expires_at")
          .eq("owner_user_id", user.id)
          .eq("status", "active")
          .order("expires_at", { ascending: false })
          .limit(1)
          .maybeSingle();

        end = lic?.expires_at || null;
        b2bDashboardUrl = "/b2b/dashboard";
      } else {
        const orderPlan = String(order.plan_id || "pro").trim().toLowerCase();
        const includeVip = VIP_ELIGIBLE_PLAN_IDS.has(orderPlan);
        const planTitleAr =
          orderPlan === "chat_only"
            ? "الشات الذكي (AI Chat Pro)"
            : orderPlan === "vip_only"
            ? "رادار وقنوات تليجرام VIP"
            : "الباقة الشاملة Pro";

        const { data: sub } = await service
          .from("subscriptions")
          .select("current_period_end")
          .eq("user_id", user.id)
          .in("plan_id", ["pro", "pro_renewal", "pro_6m", "pro_1y", "lifetime", "pro_lifetime", "chat_only", "vip_only"])
          .eq("status", "active")
          .order("current_period_end", { ascending: false })
          .limit(1)
          .maybeSingle();

        end = sub?.current_period_end || null;

        if (!includeVip) {
          inviteLink = "";
        } else if (!inviteLink) {
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
              if (includeVip && inviteLink) {
                buttons.push([{ text: "💎 الانضمام لقناة VIP", url: inviteLink }]);
              }
              buttons.push([{ text: "🌐 فتح حسابك والتقارير", url: "https://egxbots.com/reports" }]);

              const benefitsBlock =
                orderPlan === "chat_only"
                  ? `• 350 استفساراً تحليلياً بالذكاء الاصطناعي شهرياً عبر الموقع وبوت تليجرام\n• تحليل صور المحفظة والشارت (Vision AI) + 5 أتمتات يومية\n• إزالة تأخير الـ 15 يوماً في الموقع`
                  : orderPlan === "vip_only"
                  ? `• تنبيهات الرادار والمؤشرات الفنية الفورية على قناة تليجرام VIP (EGX & TASI)\n• إزالة تأخير الـ 15 يوماً من الماسح الفني في الموقع\n• ملاحظة: استخدام الشات الذكي يظل حسب رصيد الباقة المجانية`
                  : `• تنبيهات الرادار والمؤشرات الفنية الفورية على قناة VIP (EGX & TASI)\n• وصول كامل لمساعد الذكاء الاصطناعي ARTORO (350 استفساراً/شهر + Vision AI + 5 أتمتات)\n• إزالة تأخير الـ 15 يوماً بالكامل في الموقع`;

              const welcomeMsg = `🎉 <b>أهلاً وسهلاً بك يا ${displayName}!</b>\n\n` +
                `✅ <b>تم تأكيد دفع اشتراكك وتفعيل ${planTitleAr} بنجاح!</b> 🚀\n\n` +
                `━━━━━━━━━━━━━━━━━━━━\n` +
                (includeVip && inviteLink ? `💎 <b>رابط انضمامك الخاص لقناة تليجرام VIP:</b>\n${inviteLink}\n<i>(هذا الرابط شخصي وخاص بحسابك للدخول المباشر)</i>\n\n` : "") +
                `📊 <b>مزايا باقتك المفعّلة الآن:</b>\n` +
                `${benefitsBlock}\n\n` +
                `━━━━━━━━━━━━━━━━━━━━\n` +
                `💡 <b>كيف تبدأ؟</b>\n` +
                (includeVip
                  ? `1. اضغط زر <b>الانضمام لقناة VIP</b> أدناه لمتابعة تنبيهات الرادار أولاً بأول.\n`
                  : `1. افتح الشات الذكي الآن أو اكتب رمز أي سهم هنا في تليجرام لتحليله فوراً.\n`) +
                `2. تصفح أدوات السوق والتقارير اليومية عبر الموقع في أي وقت.\n\n` +
                `<i>تنويه: مخرجات المنصة أدوات تحليل فني وكمي مؤتمتة لأغراض البحث والمتابعة ولا تمثل توصية استثمارية.</i>`;

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
                    .update({ customer_note: mergeCustomerNote(customerNote, "tg_welcomed") })
                    .eq("id", orderId);
                }
              } catch (err) {
                console.warn("[easykash/status] Telegram welcome dispatch error:", err);
              }
            }
          }
        }
      }
    }

    const result = {
      ...order,
      subscription: end ? { current_period_end: end } : null,
      telegram_pro_url: inviteLink,
      b2b_dashboard_url: b2bDashboardUrl,
    };
    orderStatusCache.set(cacheKey, { payload: result, expiresAt: now + 8000 });
    return NextResponse.json(result, { headers: NO_STORE_HEADERS });
  } catch (err: any) {
    console.error("[api/payment/easykash/status] error:", err);
    return NextResponse.json({ detail: "Payment status is unavailable" }, { status: 503, headers: NO_STORE_HEADERS });
  }
}

