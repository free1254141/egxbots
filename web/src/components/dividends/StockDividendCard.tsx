"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Calendar, Coins, Clock, CheckCircle2, Calculator, ArrowUpRight } from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import type { DividendMarketKey, StockDividendItem } from "@/lib/market/dividends-server";
import { hfPublicFetch } from "@/lib/hf-browser-client";

export default function StockDividendCard({
  symbol,
  market = "egx",
}: {
  symbol: string;
  market?: DividendMarketKey;
}) {
  const { language } = useLanguage();
  const isAr = language === "ar";
  const [item, setItem] = useState<StockDividendItem | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [shares, setShares] = useState("1000");

  useEffect(() => {
    let active = true;
    const sym = (symbol || "").trim().toUpperCase().split(".")[0];
    if (!sym) return;
    hfPublicFetch(`/api/market/dividends?market=${encodeURIComponent(market)}&symbol=${encodeURIComponent(sym)}`, undefined, { cacheTtlMs: 300_000 })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!active) return;
        const rows = Array.isArray(d?.dividends) ? (d.dividends as StockDividendItem[]) : [];
        setItem(rows[0] || null);
        setLoaded(true);
      })
      .catch(() => {
        if (active) setLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [symbol, market]);

  if (!loaded || !item) return null;

  const sharesNum = Math.max(0, Number(shares) || 0);
  const gross = sharesNum * item.amount;
  const net = market === "egx" ? gross * 0.95 : gross;
  const calHref = market === "egx" ? "/dividends" : `/dividends/${market}`;
  const isUpcoming = item.status === "upcoming" || item.status === "pending_pay";
  const hist = Array.isArray(item.history) ? item.history : [];

  return (
    <div
      dir={isAr ? "rtl" : "ltr"}
      className="app-panel p-5 sm:p-6 bg-white dark:bg-zinc-900 rounded-none border-2 border-black dark:border-white shadow-[4px_4px_0px_0px_#000] dark:shadow-[4px_4px_0px_0px_#fff] space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-[#FFE600] text-black border-2 border-black">
            <Coins className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg sm:text-xl font-black text-zinc-950 dark:text-white">
              {isAr ? "توزيعات الكوبونات النقدية" : "Cash Dividend Schedule"}
            </h2>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 font-bold">
              {isUpcoming
                ? isAr
                  ? "يوجد توزيع نقدي قادم / تحت الصرف لهذا السهم"
                  : "Upcoming or pending cash dividend for this stock"
                : isAr
                ? "أحدث كوبون نقدي مسجل وتاريخ التوزيعات"
                : "Latest recorded cash dividend and payout history"}
            </p>
          </div>
        </div>

        <Link
          href={calHref}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-black border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 text-zinc-950 dark:text-white hover:bg-[#FFE600] hover:text-black transition-colors"
          prefetch={false}
        >
          <span>{isAr ? "تقويم الكوبونات الكامل" : "Full Dividend Calendar"}</span>
          <ArrowUpRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      {/* Main Coupon Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3 border-2 border-black/80 dark:border-zinc-700 bg-emerald-50/70 dark:bg-emerald-950/30">
          <div className="text-[11px] font-bold text-zinc-600 dark:text-zinc-400">
            {isAr ? "قيمة الكوبون / سهم" : "Coupon / Share"}
          </div>
          <div className="text-lg sm:text-xl font-black font-mono text-emerald-700 dark:text-emerald-400 mt-0.5">
            {item.amount.toFixed(item.amount < 1 ? 3 : 2)} {item.currency_ar}
          </div>
          {typeof item.yield_pct === "number" && (
            <div className="text-[11px] font-bold text-emerald-600 dark:text-emerald-300 font-mono">
              {isAr ? `عائد الكوبون: ${item.yield_pct.toFixed(2)}%` : `Yield: ${item.yield_pct.toFixed(2)}%`}
            </div>
          )}
        </div>

        <div className="p-3 border-2 border-black/80 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950">
          <div className="text-[11px] font-bold text-zinc-600 dark:text-zinc-400 flex items-center gap-1">
            <Calendar className="w-3 h-3" />
            <span>{isAr ? "بدون كوبون (Ex-Date)" : "Ex-Dividend Date"}</span>
          </div>
          <div className="text-base font-black font-mono text-zinc-950 dark:text-white mt-1">
            {item.ex_date}
          </div>
          <div className="mt-0.5">
            {item.status === "upcoming" ? (
              <span className="inline-flex items-center gap-1 text-[10px] font-black text-emerald-600 dark:text-emerald-400">
                <Clock className="w-3 h-3" />
                {typeof item.days_until_ex === "number"
                  ? isAr
                    ? item.days_until_ex === 0
                      ? "اليوم!"
                      : `بعد ${item.days_until_ex} يوم`
                    : `In ${item.days_until_ex}d`
                  : isAr
                  ? "قادم"
                  : "Upcoming"}
              </span>
            ) : item.status === "pending_pay" ? (
              <span className="text-[10px] font-black text-amber-600 dark:text-amber-400">
                {isAr ? "تحت الصرف" : "Pending Pay"}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold text-zinc-500">
                <CheckCircle2 className="w-3 h-3" />
                {isAr ? "تم الصرف" : "Paid"}
              </span>
            )}
          </div>
        </div>

        <div className="p-3 border-2 border-black/80 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950">
          <div className="text-[11px] font-bold text-zinc-600 dark:text-zinc-400">
            {isAr ? "تاريخ نهاية الحق" : "Record Date"}
          </div>
          <div className="text-base font-black font-mono text-zinc-950 dark:text-white mt-1">
            {item.record_date || "—"}
          </div>
        </div>

        <div className="p-3 border-2 border-black/80 dark:border-zinc-700 bg-indigo-50/70 dark:bg-indigo-950/30">
          <div className="text-[11px] font-bold text-zinc-600 dark:text-zinc-400">
            {isAr ? "تاريخ الصرف الفعلي" : "Pay Date"}
          </div>
          <div className="text-base font-black font-mono text-indigo-700 dark:text-indigo-300 mt-1">
            {item.pay_date || (isAr ? "يُعلن قريباً" : "TBA")}
          </div>
        </div>
      </div>

      {/* Interactive Payout Calculator */}
      <div className="p-3.5 border-2 border-dashed border-zinc-400 dark:border-zinc-700 bg-zinc-50/80 dark:bg-zinc-950/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Calculator className="w-4 h-4 text-amber-600 dark:text-[#FFE600] shrink-0" />
          <span className="text-xs font-black text-zinc-900 dark:text-zinc-100">
            {isAr ? "احسب نصيبك من الكوبون:" : "Estimate your payout:"}
          </span>
          <input
            type="number"
            min={0}
            value={shares}
            onChange={(e) => setShares(e.target.value)}
            className="w-24 px-2 py-1 text-xs font-mono font-black border-2 border-black dark:border-zinc-600 bg-white dark:bg-zinc-900 text-zinc-950 dark:text-white"
          />
          <span className="text-xs font-bold text-zinc-500">{isAr ? "سهم" : "shares"}</span>
        </div>

        <div className="text-xs sm:text-sm font-mono font-black text-emerald-700 dark:text-emerald-400">
          {isAr ? "الإجمالي:" : "Gross:"} {gross.toLocaleString(undefined, { maximumFractionDigits: 2 })} {item.currency_ar}
          {market === "egx" && (
            <span className="ms-2 text-zinc-500 dark:text-zinc-400 font-bold text-xs">
              ({isAr ? "صافي بعد 5%:" : "Net 95%:"} {net.toLocaleString(undefined, { maximumFractionDigits: 2 })} {item.currency_ar})
            </span>
          )}
        </div>
      </div>

      {/* Historical Payouts Table */}
      {hist.length > 1 && (
        <div className="pt-2">
          <div className="text-xs font-black text-zinc-700 dark:text-zinc-300 mb-2">
            {isAr ? "سجل التوزيعات السابقة للسهم" : "Historical Dividend Payouts"}
          </div>
          <div className="overflow-x-auto border border-zinc-200 dark:border-zinc-800">
            <table className="w-full text-xs text-right border-collapse">
              <thead>
                <tr className="bg-zinc-100 dark:bg-zinc-800/80 text-[11px] font-black text-zinc-600 dark:text-zinc-300">
                  <th className="p-2">{isAr ? "Ex-Date" : "Ex-Date"}</th>
                  <th className="p-2">{isAr ? "الكوبون" : "Amount"}</th>
                  <th className="p-2">{isAr ? "نهاية الحق" : "Record"}</th>
                  <th className="p-2">{isAr ? "الصرف" : "Pay Date"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800 font-mono">
                {hist.slice(0, 5).map((h, idx) => (
                  <tr key={`${h.ex_date}-${idx}`}>
                    <td className="p-2 font-bold text-zinc-900 dark:text-zinc-100">{h.ex_date}</td>
                    <td className="p-2 font-black text-emerald-700 dark:text-emerald-400">
                      {h.amount.toFixed(h.amount < 1 ? 3 : 2)} {item.currency_ar}
                    </td>
                    <td className="p-2 text-zinc-500">{h.record_date || "—"}</td>
                    <td className="p-2 text-zinc-600 dark:text-zinc-300">{h.pay_date || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
