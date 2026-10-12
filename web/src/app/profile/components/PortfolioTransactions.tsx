"use client";
import { useEffect, useState } from "react";
import type { PortfolioSnapshot } from "@/contexts/PortfolioContext";
import type { PortfolioSaleEvent } from "@/lib/portfolio-performance";
const money = (v: unknown) =>
  v === null || v === undefined || !Number.isFinite(Number(v))
    ? "—"
    : Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 });
export default function PortfolioTransactions({
  snapshot,
  events,
  isAr,
  initialSale,
  onSaved,
}: {
  snapshot: PortfolioSnapshot | null;
  events: PortfolioSaleEvent[];
  isAr: boolean;
  initialSale?: { symbol: string; quantity: number | null; key: number } | null;
  onSaved: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [action, setAction] = useState("deposit"),
    [symbol, setSymbol] = useState(""),
    [quantity, setQuantity] = useState(""),
    [price, setPrice] = useState(""),
    [amount, setAmount] = useState(""),
    [fees, setFees] = useState("0"),
    [date, setDate] = useState(""),
    [requestId, setRequestId] = useState("");
  const start = (sell?: { symbol: string; quantity: number | null }) => {
    setAction(sell ? "sell" : "deposit");
    setSymbol(sell?.symbol || "");
    setQuantity(sell?.quantity == null ? "" : String(sell.quantity));
    setPrice("");
    setAmount("");
    setFees("0");
    setDate(
      new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
        .toISOString()
        .slice(0, 16),
    );
    setRequestId(crypto.randomUUID());
    setError("");
    setOpen(true);
  };
  useEffect(() => {
    if (initialSale) start(initialSale);
  }, [initialSale?.key]);
  const trade = action === "buy" || action === "sell";
  const change = (set: (value: string) => void, value: string) => {
    set(value);
    setError("");
    setRequestId(crypto.randomUUID());
  };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/portfolio/transactions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          symbol: trade ? symbol : "",
          quantity: trade ? quantity : null,
          price: trade ? price : null,
          amount: trade ? null : amount,
          fees: trade ? fees : 0,
          occurredAt: new Date(date).toISOString(),
          requestId,
        }),
      });
      const data = await response.json();
      if (!response.ok || data.ok !== true)
        throw new Error(data.message || "لم يتم تأكيد التسجيل.");
      setOpen(false);
      await onSaved();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : isAr
            ? "تعذر التسجيل"
            : "Recording failed",
      );
    } finally {
      setBusy(false);
    }
  };
  const labels: Record<string, string> = isAr
    ? {
        portfolio_add: "إضافة حيازة",
        portfolio_buy: "شراء مسجل",
        portfolio_sell: "بيع مسجل",
        portfolio_cash_add: "إيداع",
        portfolio_cash_withdraw: "سحب",
        portfolio_cash_set: "تعديل السيولة",
      }
    : {
        portfolio_add: "Holding added",
        portfolio_buy: "Recorded purchase",
        portfolio_sell: "Recorded sale",
        portfolio_cash_add: "Deposit",
        portfolio_cash_withdraw: "Withdrawal",
        portfolio_cash_set: "Cash correction",
      };
  const input =
    "mt-1 min-h-11 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm text-black dark:border-zinc-700 dark:bg-zinc-950 dark:text-white";
  return (
    <section className="space-y-3 rounded-2xl border border-zinc-200 dark:border-zinc-700 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-bold">
          {isAr ? "سجل العمليات" : "Transaction history"}
        </h3>
        <button
          type="button"
          onClick={() => start()}
          className="min-h-11 rounded-lg bg-sky-600 px-4 text-sm font-bold text-white"
        >
          {isAr ? "تسجيل عملية" : "Record transaction"}
        </button>
      </div>
      {open && (
        <form
          onSubmit={save}
          className="space-y-3 border-t border-zinc-200 dark:border-zinc-800 pt-3"
        >
          <p className="text-xs leading-relaxed text-zinc-500">
            {isAr
              ? "تسجيل يدوي لعملية نفذتها بالفعل؛ يغيّر الكمية والسيولة المسجلتين. الشراء يخصم القيمة والعمولات، والبيع يضيف صافي الحصيلة."
              : "Manual bookkeeping for an already executed transaction. Purchases deduct cost and fees; sales add net proceeds."}
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">
              {isAr ? "نوع العملية" : "Type"}
              <select
                className={input}
                value={action}
                onChange={(e) => change(setAction, e.target.value)}
              >
                <option value="deposit">
                  {isAr ? "إيداع سيولة" : "Deposit"}
                </option>
                <option value="withdraw">
                  {isAr ? "سحب سيولة" : "Withdrawal"}
                </option>
                <option value="buy">{isAr ? "شراء" : "Purchase"}</option>
                <option value="sell">
                  {isAr ? "بيع جزئي أو كامل" : "Partial or full sale"}
                </option>
              </select>
            </label>
            <label className="text-sm">
              {isAr ? "تاريخ ووقت التنفيذ" : "Execution date & time"}
              <input
                type="datetime-local"
                required
                className={input}
                value={date}
                onChange={(e) => change(setDate, e.target.value)}
              />
            </label>
            {trade ? (
              <>
                <label className="text-sm">
                  {isAr ? "السهم" : "Stock"}
                  <input
                    required
                    className={input}
                    list="portfolio-transaction-symbols"
                    value={symbol}
                    onChange={(e) =>
                      change(setSymbol, e.target.value.toUpperCase())
                    }
                  />
                  <datalist id="portfolio-transaction-symbols">
                    {(snapshot?.market_symbols || []).map((s) => (
                      <option key={s.symbol} value={s.symbol}>
                        {s.name}
                      </option>
                    ))}
                  </datalist>
                </label>
                <label className="text-sm">
                  {isAr ? "الكمية المنفذة" : "Executed quantity"}
                  <input
                    type="number"
                    min="0.000001"
                    step="any"
                    required
                    className={input}
                    value={quantity}
                    onChange={(e) => change(setQuantity, e.target.value)}
                  />
                </label>
                <label className="text-sm">
                  {isAr ? "سعر التنفيذ — ج.م" : "Execution price — EGP"}
                  <input
                    type="number"
                    min="0.000001"
                    step="any"
                    required
                    className={input}
                    value={price}
                    onChange={(e) => change(setPrice, e.target.value)}
                  />
                </label>
                <label className="text-sm">
                  {isAr ? "إجمالي العمولات — ج.م" : "Total fees — EGP"}
                  <input
                    type="number"
                    min="0"
                    step="any"
                    required
                    className={input}
                    value={fees}
                    onChange={(e) => change(setFees, e.target.value)}
                  />
                </label>
              </>
            ) : (
              <label className="text-sm">
                {isAr ? "المبلغ — ج.م" : "Amount — EGP"}
                <input
                  type="number"
                  min="0.01"
                  step="any"
                  required
                  className={input}
                  value={amount}
                  onChange={(e) => change(setAmount, e.target.value)}
                />
              </label>
            )}
          </div>
          {error && (
            <p
              role="alert"
              className="text-sm text-rose-600 dark:text-rose-400"
            >
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={busy}
              className="min-h-11 rounded-lg bg-emerald-600 px-4 text-sm font-bold text-white disabled:opacity-50"
            >
              {busy
                ? isAr
                  ? "جارٍ التسجيل…"
                  : "Recording…"
                : isAr
                  ? "تأكيد تسجيل العملية"
                  : "Confirm transaction"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setOpen(false)}
              className="min-h-11 rounded-lg border border-zinc-300 dark:border-zinc-700 px-4 text-sm"
            >
              {isAr ? "إلغاء" : "Cancel"}
            </button>
          </div>
        </form>
      )}
      <div className="space-y-2">
        {events.length === 0 ? (
          <p className="text-sm text-zinc-500">
            {isAr
              ? "لا توجد عمليات محفوظة للعرض."
              : "No saved transactions to display."}
          </p>
        ) : (
          events.map((event) => (
            <div
              key={event.id}
              className="flex flex-wrap items-start justify-between gap-2 border-t border-zinc-200 dark:border-zinc-800 pt-2 text-sm"
            >
              <div>
                <b>
                  {labels[event.event_type] || event.event_type}{" "}
                  {String(event.payload?.symbol || "")}
                </b>
                <p className="mt-1 text-xs text-zinc-500">
                  {new Date(event.event_at).toLocaleString(
                    isAr ? "ar-EG" : "en-GB",
                  )}
                </p>
              </div>
              <div className="text-end text-xs">
                <p>
                  {event.payload?.quantity != null
                    ? `${money(event.payload.quantity)} ${isAr ? "سهم" : "shares"} · `
                    : ""}
                  {money(
                    event.payload?.sell_price ??
                      event.payload?.price ??
                      event.payload?.entry_price ??
                      event.payload?.amount,
                  )}{" "}
                  {isAr ? "ج.م" : "EGP"}
                </p>
                {event.payload?.fees != null && (
                  <p className="mt-1 text-zinc-500">
                    {isAr ? "عمولات" : "Fees"}: {money(event.payload.fees)}
                  </p>
                )}
              </div>
            </div>
          ))
        )}
      </div>
      <p className="text-xs text-zinc-500">
        {isAr
          ? "أحدث 50 عملية محفوظة؛ إضافة الحيازات وتعديل السيولة لا يثبتان سجل تداول كاملًا."
          : "Latest 50 saved entries; imported holdings and cash corrections do not establish a complete trading history."}
      </p>
    </section>
  );
}
