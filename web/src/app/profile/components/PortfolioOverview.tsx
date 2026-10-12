"use client";
import { useState } from "react";
import type { PortfolioPerformance } from "@/lib/portfolio-performance";
import type { PortfolioSnapshot } from "@/contexts/PortfolioContext";
import {
  portfolioConcentration,
  simulatePortfolioDrop,
} from "@/lib/portfolio-overview";
const money = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v)
    ? "—"
    : v.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
export default function PortfolioOverview({
  report,
  snapshot,
  isAr,
  loading,
  error,
  onRefresh,
}: {
  report: PortfolioPerformance | null;
  snapshot: PortfolioSnapshot | null;
  isAr: boolean;
  loading: boolean;
  error: boolean;
  onRefresh: () => void;
}) {
  const [drop, setDrop] = useState(10);
  const daily = report?.daily;
  const concentration = portfolioConcentration(
    report?.daily?.holdings || [],
    snapshot?.cash_balance ?? null,
  );
  const scenario = report
    ? simulatePortfolioDrop(
        concentration.stockValue,
        snapshot?.cash_balance ?? null,
        drop,
      )
    : null;
  const biggest =
    daily?.holdings
      .filter((p) => p.change !== null)
      .sort((a, b) => Math.abs(b.change!) - Math.abs(a.change!))
      .slice(0, 3) || [];
  return (
    <div className="space-y-4" data-testid="portfolio-overview">
      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-bold">
              {isAr
                ? "إيه اللي اتغيّر في أسهمك؟"
                : "What changed in your holdings?"}
            </h3>
            <p
              dir="ltr"
              className={`mt-1 text-xs text-zinc-500 ${isAr ? "text-right" : ""}`}
            >
              {daily?.previousDate || "—"} → {daily?.date || "—"}
            </p>
          </div>
          <span className="rounded-lg bg-emerald-500/10 px-3 py-1 text-xs font-bold text-emerald-700 dark:text-emerald-400">
            {isAr ? "متاح لكل الحسابات" : "Available on every plan"}
          </span>
        </div>
        {loading && !report ? (
          <p role="status" className="py-4 text-sm">
            {isAr ? "تحميل ملخص الحيازات…" : "Loading holdings summary…"}
          </p>
        ) : error ? (
          <div role="alert" className="mt-3 text-sm">
            {isAr ? "تعذر تحميل الملخص." : "Summary unavailable."}{" "}
            <button type="button" onClick={onRefresh} className="underline">
              {isAr ? "إعادة المحاولة" : "Retry"}
            </button>
          </div>
        ) : (
          <>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs text-zinc-500">
                  {isAr
                    ? "حركة الحيازات الحالية — ج.م"
                    : "Current holdings change — EGP"}
                </p>
                <p
                  dir="ltr"
                  className={`mt-1 text-2xl font-bold ${daily?.change == null ? "text-zinc-500" : daily.change < 0 ? "text-rose-600 dark:text-rose-400" : "text-emerald-600 dark:text-emerald-400"}`}
                >
                  {daily?.change != null && daily.change > 0 ? "+" : ""}
                  {money(daily?.change)}
                </p>
                <p dir="ltr" className="text-sm">
                  {money(daily?.changePct)}%
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">
                  {isAr
                    ? "حركة EGX30 لنفس الجلستين"
                    : "EGX30 over the same sessions"}
                </p>
                <p dir="ltr" className="mt-1 text-2xl font-bold">
                  {money(daily?.benchmarkPct)}%
                </p>
              </div>
            </div>
            {biggest.length > 0 && (
              <div className="mt-4 space-y-2">
                {biggest.map((p) => (
                  <div
                    key={p.symbol}
                    className="flex items-center justify-between gap-3 border-t border-zinc-200 dark:border-zinc-800 pt-2 text-sm"
                  >
                    <b>{p.symbol}</b>
                    <span
                      dir="ltr"
                      className={
                        p.change! < 0
                          ? "text-rose-600 dark:text-rose-400"
                          : "text-emerald-600 dark:text-emerald-400"
                      }
                    >
                      <bdi dir="ltr">{money(p.change)}</bdi>{" "}
                      <bdi>{isAr ? "ج.م" : "EGP"}</bdi> ·{" "}
                      <bdi dir="ltr">{money(p.changePct)}%</bdi>
                    </span>
                  </div>
                ))}
              </div>
            )}
            {daily && !daily.complete && (
              <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">
                {daily.holdings.length === 0
                  ? isAr
                    ? "أضف حيازاتك لعرض حركة الأسهم."
                    : "Add holdings to see their daily change."
                  : isAr
                    ? "الملخص غير مكتمل لغياب أسعار جلستين متطابقتين لبعض الأسهم."
                    : "Summary incomplete: some holdings lack prices for both matching sessions."}
              </p>
            )}
            <p className="mt-3 text-xs leading-relaxed text-zinc-500">
              {isAr
                ? "محاكاة للكميات الموجودة الآن بين آخر جلستين مخزنتين؛ تستبعد عملياتك والسيولة والرسوم، ولا تمثل عائد حسابك الفعلي."
                : "A simulation of current quantities across the latest two stored sessions; excludes trades, cash and fees, not your actual account return."}
            </p>
            {daily && !daily.adjusted && (
              <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
                {isAr
                  ? "أسعار معدّلة غير مكتملة؛ التجزئة والمنح قد تؤثر على الحركة."
                  : "Adjusted prices are incomplete; splits and bonus shares may affect the change."}
              </p>
            )}
          </>
        )}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-2xl border border-zinc-200 dark:border-zinc-700 p-4">
          <h3 className="font-bold">
            {isAr ? "تركيز المحفظة والسيولة" : "Concentration & cash"}
          </h3>
          <p className="mt-1 text-xs text-zinc-500">
            {isAr
              ? "الأوزان من إجمالي الأسهم والسيولة"
              : "Weights include shares and cash"}
          </p>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs text-zinc-500">
                {isAr ? "أكبر مركز" : "Largest holding"}
              </p>
              <p className="mt-1 font-bold">
                {concentration.top?.symbol || "—"}{" "}
                <span dir="ltr">
                  {report ? money(concentration.top?.pct) : "—"}%
                </span>
              </p>
            </div>
            <div>
              <p className="text-xs text-zinc-500">
                {isAr ? "نسبة السيولة" : "Cash weight"}
              </p>
              <p className="mt-1 font-bold" dir="ltr">
                {report ? money(concentration.cashPct) : "—"}%
              </p>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {report &&
              concentration.sectors.map((s) => (
                <div key={s.sector}>
                  <div className="mb-1 flex justify-between gap-2 text-xs">
                    <span>
                      {s.sector === "unknown"
                        ? isAr
                          ? "قطاع غير متاح"
                          : "Unknown sector"
                        : s.sector}
                    </span>
                    <span dir="ltr">{money(s.pct)}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                    <div
                      className="h-full bg-sky-500"
                      style={{ width: `${s.pct}%` }}
                    />
                  </div>
                </div>
              ))}
          </div>
          {report && !concentration.complete && (
            <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">
              {isAr
                ? "تعذر حساب الأوزان لوجود قيم سوقية ناقصة."
                : "Weights unavailable because some market values are missing."}
            </p>
          )}
        </section>
        <section className="rounded-2xl border border-zinc-200 dark:border-zinc-700 p-4">
          <h3 className="font-bold">
            {isAr ? "لو الأسهم هبطت…" : "If shares declined…"}
          </h3>
          <p className="mt-1 text-xs text-zinc-500">
            {isAr
              ? "حساب افتراضي مع ثبات السيولة"
              : "Hypothetical calculation, cash held constant"}
          </p>
          <div className="my-4 flex flex-wrap gap-2">
            {[5, 10, 20].map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={drop === n}
                onClick={() => setDrop(n)}
                className={`min-h-11 rounded-lg border px-4 text-sm font-bold ${drop === n ? "border-sky-500 bg-sky-500/10 text-sky-700 dark:text-sky-300" : "border-zinc-300 dark:border-zinc-700"}`}
              >
                −{n}%
              </button>
            ))}
          </div>
          <div aria-live="polite" className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs text-zinc-500">
                {isAr
                  ? "الانخفاض الافتراضي — ج.م"
                  : "Hypothetical decline — EGP"}
              </p>
              <p className="mt-1 font-bold" dir="ltr">
                {money(scenario?.loss)}
              </p>
            </div>
            <div>
              <p className="text-xs text-zinc-500">
                {isAr ? "القيمة المتبقية — ج.م" : "Remaining equity — EGP"}
              </p>
              <p className="mt-1 font-bold" dir="ltr">
                {money(scenario?.remaining)}
              </p>
            </div>
          </div>
          <p className="mt-4 text-xs leading-relaxed text-zinc-500">
            {isAr
              ? "نفس الهبوط لكل الأسهم، وليس توقعًا. لا يغيّر كمياتك أو سيولتك."
              : "Same decline applied to all shares, not a forecast. Does not change holdings or cash."}
          </p>
        </section>
      </div>
    </div>
  );
}
