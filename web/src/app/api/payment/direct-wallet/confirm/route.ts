import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1";

export async function POST() {
  return NextResponse.json(
    { detail: "التحويل المباشر غير متاح؛ يتم الدفع والتفعيل الفوري عبر بوابة EasyKash المعتمدة فقط" },
    { status: 410, headers: { "Cache-Control": "private, no-store, max-age=0" } }
  );
}
