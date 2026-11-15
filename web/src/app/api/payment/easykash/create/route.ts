import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";
const BACKEND_URL = (process.env.PYTHON_BACKEND_URL || process.env.TRADING_SIGNALS_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export async function POST(req: NextRequest) {
  const auth = await createSupabaseServerClient(req);
  const { data: { user } } = await auth.auth.getUser();
  if (!user) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  const { data: { session } } = await auth.auth.getSession();
  if (!session?.access_token) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const rawMobile = String(body?.mobile || "").trim().replace(/[\s\-()]/g, "");
  // Accept Egyptian numbers (01XXXXXXXXX or +201XXXXXXXXX -> normalize to 01XXXXXXXXX)
  // as well as international GCC/global E.164 numbers (+CCXXXXXXXXX).
  let mobile = rawMobile.startsWith("00") ? `+${rawMobile.slice(2)}` : rawMobile;
  if (/^\+?20(?:20)?0?(1[0125]\d{8})$/.test(mobile)) {
    mobile = `0${mobile.replace(/^\+?20(?:20)?0?/, "")}`;
  }
  // Collapse accidentally duplicated GCC dial prefixes (e.g. +9669665... -> +9665...)
  mobile = mobile.replace(/^\+(966|971|965|974|973|968|962|961)\1/, "+$1");
  const isEgyptianMobile = /^01[0125]\d{8}$/.test(mobile);
  const isInternationalMobile =
    (/^\+[1-9]\d{6,14}$/.test(mobile)) ||
    (!mobile.startsWith("0") && /^[1-9]\d{6,14}$/.test(mobile));
  if (!isEgyptianMobile && !isInternationalMobile) {
    return NextResponse.json(
      { detail: "أدخل رقم موبايل صحيح (مصري 01XXXXXXXXX أو دولي بمفتاح الدولة مثل +9665XXXXXXXX)" },
      { status: 400 }
    );
  }
  const promoCode = typeof body?.promo_code === "string" ? body.promo_code.trim().toUpperCase().slice(0, 32) : "";
  const market = String(body?.market || "").trim().toLowerCase() === "tasi" ? "tasi" : "egx";

  // Save/update phone number in profiles so the user never has to enter it again
  try {
    await auth
      .from("profiles")
      .update({ whatsapp_number: mobile, updated_at: new Date().toISOString() })
      .eq("id", user.id);
  } catch (err) {
    console.error("Failed to update profile whatsapp_number:", err);
  }

  try {
    const response = await fetch(`${BACKEND_URL}/payment/easykash/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.access_token}` },
      body: JSON.stringify({
        user_id: user.id,
        plan_id: typeof body?.plan_id === "string" ? body.plan_id : "pro",
        email: user.email || "",
        name: String(user.user_metadata?.full_name || user.user_metadata?.name || "EGX Bots user").slice(0, 100),
        mobile,
        promo_code: promoCode,
        market,
      }),
      cache: "no-store",
    });
    return NextResponse.json(await response.json().catch(() => ({})), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "تعذر الاتصال بخدمة الدفع" }, { status: 503 });
  }
}
