import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1";

const BACKEND_URL = (process.env.PYTHON_BACKEND_URL || process.env.TRADING_SIGNALS_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export async function POST(req: NextRequest) {
  try {
    const auth = await createSupabaseServerClient(req);
    const { data: { user } } = await auth.auth.getUser();
    if (!user) {
      return NextResponse.json({ detail: "يرجى تسجيل الدخول أولاً للمتابعة" }, { status: 401 });
    }

    const { data: { session } } = await auth.auth.getSession();
    if (!session?.access_token) {
      return NextResponse.json({ detail: "جلسة المستخدم غير صالحة" }, { status: 401 });
    }

    const body = await req.json().catch(() => ({}));
    const senderMobile = String(body?.sender_mobile || body?.mobile || "").replace(/[\s-]/g, "");
    if (!/^01[0125]\d{8}$/.test(senderMobile)) {
      return NextResponse.json({ detail: "أدخل رقم موبايل مصري صحيح (11 رقم) محول منه" }, { status: 400 });
    }

    const transactionId = String(body?.transaction_id || body?.ref || "").replace(/[\s\r\n\t]/g, "").trim();
    if (transactionId.length < 6) {
      return NextResponse.json({ detail: "أدخل رقم العملية أو المرجع من رسالة التحويل (6 خانات على الأقل)" }, { status: 400 });
    }

    const promoCode = typeof body?.promo_code === "string" ? body.promo_code.trim().toUpperCase().slice(0, 32) : "";
    const planId = typeof body?.plan_id === "string" ? body.plan_id : "pro";

    // Save/update phone number in profiles
    try {
      await auth
        .from("profiles")
        .update({ whatsapp_number: senderMobile, updated_at: new Date().toISOString() })
        .eq("id", user.id);
    } catch (err) {
      console.warn("[direct-wallet] update whatsapp_number warning:", err);
    }

    // Forward to Python backend for instant activation and telegram alert
    const response = await fetch(`${BACKEND_URL}/payment/direct-wallet/confirm`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({
        user_id: user.id,
        plan_id: planId,
        sender_mobile: senderMobile,
        transaction_id: transactionId,
        promo_code: promoCode,
      }),
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { detail: data?.detail || "تعذر تأكيد عملية التحويل، يرجى مراجعة البيانات" },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (err: any) {
    console.error("[api/payment/direct-wallet/confirm] error:", err);
    return NextResponse.json({ detail: "تعذر الاتصال بخدمة التحويل المباشر" }, { status: 503 });
  }
}
