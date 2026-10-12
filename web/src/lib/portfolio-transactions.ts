export type PortfolioTransaction = {
  action: "buy" | "sell" | "deposit" | "withdraw";
  symbol: string;
  quantity: number | null;
  price: number | null;
  amount: number | null;
  fees: number;
  occurredAt: string;
  requestId: string;
};
export function parsePortfolioTransaction(
  body: Record<string, unknown>,
  now = Date.now(),
): PortfolioTransaction {
  const action = String(body.action),
    symbol = String(body.symbol || "")
      .trim()
      .toUpperCase();
  const number = (v: unknown) =>
    v === null || v === undefined || v === "" ? null : Number(v);
  const quantity = number(body.quantity),
    price = number(body.price),
    amount = number(body.amount),
    fees = number(body.fees) ?? 0;
  const occurredAt = String(body.occurredAt || ""),
    requestId = String(body.requestId || "");
  if (!["buy", "sell", "deposit", "withdraw"].includes(action))
    throw new Error("invalid_action");
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      requestId,
    ) ||
    !Number.isFinite(Date.parse(occurredAt)) ||
    Date.parse(occurredAt) > now
  )
    throw new Error("invalid_date_or_request");
  if (!Number.isFinite(fees) || fees < 0) throw new Error("invalid_fees");
  if (action === "buy" || action === "sell") {
    if (
      !/^[A-Z0-9]{2,10}$/.test(symbol) ||
      quantity === null ||
      price === null ||
      !Number.isFinite(quantity) ||
      !Number.isFinite(price) ||
      quantity <= 0 ||
      price <= 0
    )
      throw new Error("invalid_trade");
  } else if (
    amount === null ||
    !Number.isFinite(amount) ||
    amount <= 0 ||
    fees !== 0
  )
    throw new Error("invalid_cash_amount");
  return {
    action: action as PortfolioTransaction["action"],
    symbol,
    quantity,
    price,
    amount,
    fees,
    occurredAt: new Date(occurredAt).toISOString(),
    requestId,
  };
}
export const transactionErrors: Record<string, string> = {
  invalid_action: "نوع العملية غير صالح.",
  invalid_date_or_request: "تحقق من التاريخ؛ لا يمكن تسجيل عملية مستقبلية.",
  invalid_fees: "العمولات يجب أن تكون صفرًا أو أكثر.",
  invalid_trade: "اختر السهم وأدخل كمية وسعرًا أكبر من صفر.",
  invalid_cash_amount: "أدخل مبلغًا أكبر من صفر.",
  insufficient_cash: "السيولة المسجلة لا تكفي لهذه العملية.",
  quantity_exceeds_holding: "كمية البيع أكبر من حيازتك الحالية.",
  unknown_symbol: "السهم غير موجود في دليل الأسهم.",
  fees_exceed_proceeds: "العمولات أكبر من حصيلة البيع.",
  holding_limit: "وصلت لحد عدد الأسهم في خطتك الحالية.",
  date_before_last_transaction:
    "التاريخ أقدم من آخر عملية مسجلة؛ سجّل العمليات بالترتيب.",
  request_conflict: "تغيّرت بيانات طلب سابق. أغلق النموذج وافتحه لطلب جديد.",
  duplicate_holdings: "توجد حيازات مكررة للسهم؛ راجعها قبل التسجيل.",
};
