import { NextRequest, NextResponse } from "next/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import crypto from "node:crypto";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const UNSUB_SECRET =
  process.env.SUPABASE_JWT_SECRET ||
  process.env.RESEND_API_KEY ||
  "egxbots-marketing-secret-key-2026";

function verifyToken(userId: string, email: string, token: string): boolean {
  const msg = `unsub:${userId}:${email.toLowerCase().trim()}`;
  const expected = crypto
    .createHmac("sha256", UNSUB_SECRET)
    .update(msg)
    .digest("hex")
    .slice(0, 32);
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(token));
}

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const uid = url.searchParams.get("uid") || "";
  const email = url.searchParams.get("email") || "";
  const token = url.searchParams.get("token") || "";

  if (!uid || !email || !token) {
    return new NextResponse("رابط غير صالح", { status: 400 });
  }

  let isValid = false;
  try {
    isValid = verifyToken(uid, email, token);
  } catch {
    isValid = false;
  }

  if (!isValid) {
    return new NextResponse("رمز التحقق غير صالح أو منتهي الصلاحية", { status: 403 });
  }

  try {
    const service = getSupabaseServiceClient();
    await service.from("marketing_preferences").upsert(
      {
        user_id: uid,
        email: email.toLowerCase().trim(),
        unsubscribed_all: true,
        unsubscribed_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      { onConflict: "user_id" }
    );

    const html = `<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <title>تم إلغاء الاشتراك بنجاح | EGX BOTS</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 40px 16px; background-color: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; direction: rtl; text-align: right;">
  <div style="max-width: 500px; margin: 40px auto; background: #fff; border: 3px solid #000; box-shadow: 6px 6px 0px #000; padding: 32px 24px; text-align: center;">
    <h1 style="margin: 0 0 16px; font-size: 22px; font-weight: 900; color: #111;">تم إلغاء الاشتراك بنجاح ✅</h1>
    <p style="font-size: 14px; line-height: 1.7; color: #4b5563; margin-bottom: 24px;">
      لن تتلقى أي رسائل تسويقية أو تذكيرات عروض على بريدك الإلكتروني (<strong>${email}</strong>) بعد الآن.
      ستظل تتلقى الإشعارات الهامة المتعلقة بحسابك أو معاملاتك المالية.
    </p>
    <a href="https://egxbots.com" style="display: inline-block; padding: 12px 24px; background: #FFE600; color: #000; text-decoration: none; font-weight: 900; font-size: 14px; border: 2px solid #000; box-shadow: 3px 3px 0px #000;">
      العودة للمنصة الرئيسية ←
    </a>
  </div>
</body>
</html>`;

    return new NextResponse(html, {
      status: 200,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  } catch (err: any) {
    console.error("[marketing/unsubscribe] error:", err);
    return new NextResponse("حدث خطأ أثناء معالجة الطلب", { status: 500 });
  }
}
