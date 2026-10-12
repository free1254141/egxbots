import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import {
  parsePortfolioTransaction,
  transactionErrors,
} from "@/lib/portfolio-transactions";
export const dynamic = "force-dynamic";
const headers = {
  "Cache-Control": "private, no-store",
  "Vercel-CDN-Cache-Control": "no-store",
  "CDN-Cache-Control": "no-store",
  Vary: "Cookie",
};
export async function POST(req: NextRequest) {
  const client = await createSupabaseServerClient(req);
  const {
    data: { user },
    error: authError,
  } = await client.auth.getUser();
  if (authError || !user)
    return NextResponse.json(
      { ok: false, message: "Unauthorized" },
      { status: 401, headers },
    );
  let input;
  try {
    input = parsePortfolioTransaction(await req.json());
  } catch (error) {
    const code = error instanceof Error ? error.message : "";
    return NextResponse.json(
      {
        ok: false,
        message: transactionErrors[code] || "بيانات العملية غير صالحة.",
      },
      { status: 400, headers },
    );
  }
  try {
    // No Pro gate: authenticated Free accounts have the same ledger operations.
    const { data, error } = await client.rpc("record_portfolio_transaction", {
      p_action: input.action,
      p_symbol: input.symbol,
      p_quantity: input.quantity,
      p_price: input.price,
      p_amount: input.amount,
      p_fees: input.fees,
      p_occurred_at: input.occurredAt,
      p_request_id: input.requestId,
    });
    if (error) {
      const code = Object.keys(transactionErrors).find((key) =>
        String(error.message).includes(key),
      );
      return NextResponse.json(
        {
          ok: false,
          message: code
            ? transactionErrors[code]
            : "سجل العمليات غير متاح حاليًا. لم نؤكد حفظ العملية.",
        },
        { status: code ? 400 : 503, headers },
      );
    }
    if (data?.ok !== true) throw new Error("Unconfirmed transaction");
    return NextResponse.json(
      { ok: true, message: "تم تسجيل العملية وتحديث المحفظة والسيولة." },
      { headers },
    );
  } catch {
    return NextResponse.json(
      {
        ok: false,
        message: "تعذر تأكيد حفظ العملية. أعد المحاولة بنفس الطلب.",
      },
      { status: 503, headers },
    );
  }
}
