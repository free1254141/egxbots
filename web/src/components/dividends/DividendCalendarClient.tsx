"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Calendar, Coins, Search, Calculator, Sparkles, Clock, CheckCircle2, ArrowUpRight } from "lucide-react";
import StockLogo from "@/components/StockLogo";
import { EgyptFlag, SaudiFlag, UaeFlag, QatarFlag } from "@/components/MarketFlag";
import { useLanguage } from "@/contexts/LanguageContext";
import { useMarket, MARKET_CHANGE_EVENT, type MarketMode } from "@/contexts/MarketContext";
import { getStockHref } from "@/lib/stock-href";
import type { DividendMarketKey, DividendsCalendarPayload } from "@/lib/market/dividends-server";

function MarketFlagIcon({ market, className = "w-4 h-3 rounded-[2px] shrink-0" }: { market: DividendMarketKey; className?: string }) {
  if (market === "tasi") return <SaudiFlag className={className} />;
  if (market === "qatar") return <QatarFlag className={className} />;
  if (market === "uae") return <UaeFlag className={className} />;
  return <EgyptFlag className={className} />;
}

const MARKET_META: Record<
  DividendMarketKey,
  {
    href: string;
    labelAr: string;
    labelEn: string;
    shortAr: string;
    shortEn: string;
    flag: string;
    taxNoteAr: string;
    taxNoteEn: string;
  }
> = {
  egx: {
    href: "/dividends",
    labelAr: "البورصة المصرية (EGX)",
    labelEn: "Egyptian Exchange (EGX)",
    shortAr: "مصر EGX",
    shortEn: "Egypt EGX",
    flag: "🇪🇬",
    taxNoteAr: "تنويه: تخضع توزيعات الشركات المقيدة في البورصة المصرية لضريبة توزيعات 5% تُخصم عند الصرف.",
    taxNoteEn: "Note: EGX-listed dividend payouts are subject to a 5% withholding tax at distribution.",
  },
  tasi: {
    href: "/dividends/tasi",
    labelAr: "السوق السعودي (تداول TASI)",
    labelEn: "Saudi Exchange (Tadawul)",
    shortAr: "السعودية TASI",
    shortEn: "Saudi TASI",
    flag: "🇸🇦",
    taxNoteAr: "توزيعات السوق السعودي بالريال السعودي (ر.س) وفق مواعيد الاستحقاق والصرف المعلنة.",
    taxNoteEn: "Saudi Tadawul cash dividends in SAR based on announced ex-dividend and pay dates.",
  },
  qatar: {
    href: "/dividends/qatar",
    labelAr: "بورصة قطر (QSE)",
    labelEn: "Qatar Stock Exchange (QSE)",
    shortAr: "قطر QSE",
    shortEn: "Qatar QSE",
    flag: "🇶🇦",
    taxNoteAr: "توزيعات بورصة قطر بالريال القطري (ر.ق) وفق مواعيد الاستحقاق والصرف المعلنة.",
    taxNoteEn: "Qatar Stock Exchange cash dividends in QAR based on announced dates.",
  },
  uae: {
    href: "/dividends/uae",
    labelAr: "أسواق الإمارات (دبي DFM & أبوظبي ADX)",
    labelEn: "UAE Markets (DFM & ADX)",
    shortAr: "الإمارات UAE",
    shortEn: "UAE Markets",
    flag: "🇦🇪",
    taxNoteAr: "توزيعات سوقي دبي وأبوظبي بالدرهم الإماراتي (د.إ) وفق مواعيد الاستحقاق والصرف المعلنة.",
    taxNoteEn: "Dubai (DFM) and Abu Dhabi (ADX) cash dividends in AED.",
  },
};

export default function DividendCalendarClient({
  initialData,
}: {
  initialData: DividendsCalendarPayload;
}) {
  const router = useRouter();
  const { language } = useLanguage();
  const { setMarket } = useMarket();
  const isAr = language === "ar";
  const market = initialData.market;
  const meta = MARKET_META[market];

  // When user actively switches market in the top Header dropdown, navigate to that market's dividend calendar
  useEffect(() => {
    const onMarketChange = (e: Event) => {
      const next = (e as CustomEvent<MarketMode>)?.detail;
      if (next && next !== market && MARKET_META[next]) {
        router.push(MARKET_META[next].href);
      }
    };
    window.addEventListener(MARKET_CHANGE_EVENT, onMarketChange);
    return () => window.removeEventListener(MARKET_CHANGE_EVENT, onMarketChange);
  }, [market, router]);

  const [filter, setFilter] = useState<"upcoming" | "all" | "paid">(
    initialData.summary.upcomingCount + initialData.summary.pendingPayCount > 0 ? "upcoming" : "all"
  );
  const [search, setSearch] = useState("");
  const [calcShares, setCalcShares] = useState<string>("1000");

  const sharesNum = Math.max(0, Number(calcShares) || 0);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (initialData.dividends || []).filter((item) => {
      if (filter === "upcoming" && item.status !== "upcoming" && item.status !== "pending_pay") {
        return false;
      }
      if (filter === "paid" && item.status !== "paid") {
        return false;
      }
      if (!q) return true;
      return (
        item.symbol.toLowerCase().includes(q) ||
        (item.name_ar || "").toLowerCase().includes(q) ||
        (item.name_en || "").toLowerCase().includes(q)
      );
    });
  }, [initialData.dividends, filter, search]);

  const statusBadge = (status: string, daysUntilEx?: number | null) => {
    if (status === "upcoming") {
      const countdown =
        typeof daysUntilEx === "number"
          ? daysUntilEx === 0
            ? isAr
              ? "اليوم!"
              : "Today!"
            : daysUntilEx === 1
            ? isAr
              ? "غداً"
              : "Tomorrow"
            : isAr
            ? `بعد ${daysUntilEx} يوم`
            : `In ${daysUntilEx}d`
          : isAr
          ? "قادم"
          : "Upcoming";
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-black rounded-md bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30">
          <Clock className="w-3 h-3" />
          {countdown}
        </span>
      );
    }
    if (status === "pending_pay") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-black rounded-md bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30">
          <Coins className="w-3 h-3" />
          {isAr ? "تحت الصرف" : "Pending Pay"}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-bold rounded-md bg-zinc-500/10 text-zinc-600 dark:text-zinc-400 border border-zinc-500/20">
        <CheckCircle2 className="w-3 h-3" />
        {isAr ? "تم الصرف" : "Paid"}
      </span>
    );
  };

  return (
    <div dir={isAr ? "rtl" : "ltr"} className="max-w-7xl mx-auto px-4 sm:px-6 py-8 sm:py-10 space-y-6">
      {/* Header Banner */}
      <div className="border-2 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 sm:p-7 shadow-[4px_4px_0_0_#000] dark:shadow-[4px_4px_0_0_#fff]">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-[#FFE600] text-black text-xs font-black border-2 border-black">
              <Coins className="w-3.5 h-3.5" />
              <span>{isAr ? "تقويم توزيعات الكوبونات النقدية" : "Cash Dividend Calendar"}</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-zinc-950 dark:text-white flex items-center gap-2.5 flex-wrap">
              <MarketFlagIcon market={market} className="w-7 h-5 rounded-sm shrink-0 shadow-sm" />
              <span>{isAr ? `مواعيد توزيع كوبونات ${meta.labelAr}` : `${meta.labelEn} Dividend Calendar`}</span>
            </h1>
            <p className="text-xs sm:text-sm text-zinc-600 dark:text-zinc-400 max-w-3xl leading-relaxed">
              {isAr
                ? "تابع مواعيد التداول بدون كوبون (Ex-Date)، ونهاية الحق (Record Date)، وتاريخ الصرف الفعلي (Pay Date)، واحسب العائد النقدي المتوقع لأسهمك تلقائياً."
                : "Track upcoming Ex-Dividend dates, Record dates, and Pay dates across all stocks, and calculate your expected cash payout instantly."}
            </p>
          </div>

          <Link
            href="/profile#portfolio"
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-500 hover:bg-emerald-400 text-black font-black text-xs sm:text-sm border-2 border-black shadow-[3px_3px_0_0_#000] transition-all shrink-0"
            prefetch={false}
          >
            <Sparkles className="w-4 h-4" />
            <span>{isAr ? "كوبونات محفظتي والإشعارات" : "My Portfolio Dividends"}</span>
          </Link>
        </div>

        {/* 4-Market Switcher */}
        <div className="mt-5 pt-4 border-t border-zinc-200 dark:border-zinc-800 flex flex-wrap items-center gap-2">
          {(Object.keys(MARKET_META) as DividendMarketKey[]).map((mk) => {
            const m = MARKET_META[mk];
            const active = mk === market;
            return (
              <Link
                key={mk}
                href={m.href}
                onClick={() => setMarket(mk)}
                className={`inline-flex items-center gap-2 px-3.5 py-2 text-xs font-black border-2 transition-all ${
                  active
                    ? "bg-[#FFE600] text-black border-black shadow-[2px_2px_0_0_#000]"
                    : "bg-zinc-50 dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 border-zinc-300 dark:border-zinc-700 hover:border-black dark:hover:border-white"
                }`}
                prefetch={false}
              >
                <MarketFlagIcon market={mk} />
                <span>{isAr ? m.shortAr : m.shortEn}</span>
              </Link>
            );
          })}
        </div>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-900 p-4">
          <div className="text-[11px] font-bold text-zinc-500">{isAr ? "كوبونات قادمة" : "Upcoming"}</div>
          <div className="text-2xl font-black text-emerald-600 dark:text-emerald-400 font-mono mt-1">
            {initialData.summary.upcomingCount}
          </div>
        </div>
        <div className="border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-900 p-4">
          <div className="text-[11px] font-bold text-zinc-500">{isAr ? "تحت الصرف حالياً" : "Pending Pay"}</div>
          <div className="text-2xl font-black text-amber-600 dark:text-amber-400 font-mono mt-1">
            {initialData.summary.pendingPayCount}
          </div>
        </div>
        <div className="border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-900 p-4">
          <div className="text-[11px] font-bold text-zinc-500">{isAr ? "توزيعات مسجلة (آخر 8 شهور)" : "Recent Payouts"}</div>
          <div className="text-2xl font-black text-zinc-900 dark:text-white font-mono mt-1">
            {initialData.summary.total}
          </div>
        </div>
        <div className="border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-900 p-4">
          <div className="flex items-center gap-1.5 text-[11px] font-bold text-zinc-500">
            <Calculator className="w-3.5 h-3.5 text-amber-500" />
            <span>{isAr ? "حاسبة الكوبون (عدد الأسهم)" : "Payout Calc (Shares)"}</span>
          </div>
          <input
            type="number"
            min={0}
            value={calcShares}
            onChange={(e) => setCalcShares(e.target.value)}
            className="mt-1.5 w-full px-2.5 py-1 text-sm font-mono font-black bg-zinc-50 dark:bg-zinc-950 border-2 border-black dark:border-zinc-600 text-zinc-900 dark:text-white"
            placeholder="1000"
          />
        </div>
      </div>

      {/* Filters + Search */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {(
            [
              ["upcoming", isAr ? `القادمة وتحت الصرف (${initialData.summary.upcomingCount + initialData.summary.pendingPayCount})` : "Upcoming & Pending"],
              ["all", isAr ? `الكل (${initialData.summary.total})` : `All (${initialData.summary.total})`],
              ["paid", isAr ? `المصروفة حديثاً (${initialData.summary.paidRecentCount})` : "Recently Paid"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={`px-3 py-1.5 text-xs font-black border-2 cursor-pointer transition-all ${
                filter === key
                  ? "bg-black text-[#FFE600] dark:bg-[#FFE600] dark:text-black border-black dark:border-white"
                  : "bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 border-zinc-300 dark:border-zinc-700"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 text-zinc-400 absolute top-1/2 -translate-y-1/2 start-3" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={isAr ? "ابحث برمز السهم أو اسم الشركة..." : "Search symbol or company..."}
            className="w-full ps-9 pe-3 py-2 text-xs font-bold bg-white dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 text-zinc-900 dark:text-white"
          />
        </div>
      </div>

      {/* Main Dividends Table */}
      <div className="border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-950 overflow-hidden shadow-[4px_4px_0_0_#000] dark:shadow-[4px_4px_0_0_#27272a]">
        <div className="overflow-x-auto">
          <table className="w-full text-right border-collapse text-xs sm:text-sm">
            <thead>
              <tr className="bg-zinc-100 dark:bg-zinc-900 border-b-2 border-black dark:border-zinc-700 text-[11px] font-black text-zinc-700 dark:text-zinc-300">
                <th className="p-3 whitespace-nowrap">{isAr ? "السهم والشركة" : "Stock"}</th>
                <th className="p-3 whitespace-nowrap">{isAr ? "الحالة" : "Status"}</th>
                <th className="p-3 whitespace-nowrap">{isAr ? "قيمة الكوبون" : "Coupon"}</th>
                <th className="p-3 whitespace-nowrap">{isAr ? "عائد الكوبون %" : "Yield %"}</th>
                <th className="p-3 whitespace-nowrap">{isAr ? "بدون كوبون (Ex-Date)" : "Ex-Date"}</th>
                <th className="p-3 whitespace-nowrap">{isAr ? "نهاية الحق" : "Record Date"}</th>
                <th className="p-3 whitespace-nowrap">{isAr ? "تاريخ الصرف" : "Pay Date"}</th>
                {sharesNum > 0 && (
                  <th className="p-3 whitespace-nowrap text-emerald-700 dark:text-emerald-400">
                    {isAr ? `ربحك (${sharesNum.toLocaleString()} سهم)` : `Est. (${sharesNum.toLocaleString()} sh)`}
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={sharesNum > 0 ? 8 : 7} className="p-10 text-center text-zinc-500 font-bold">
                    {isAr ? "لا توجد توزيعات مطابقة للفلتر الحالي." : "No dividend events match your filter."}
                  </td>
                </tr>
              ) : (
                filtered.map((item) => {
                  const gross = sharesNum * item.amount;
                  const net = market === "egx" ? gross * 0.95 : gross;
                  const href = getStockHref(item.symbol, { market, exchange: item.exchange });
                  return (
                    <tr
                      key={`${item.exchange}-${item.symbol}-${item.ex_date}`}
                      className="hover:bg-amber-500/5 dark:hover:bg-zinc-900/80 transition-colors"
                    >
                      <td className="p-3 whitespace-nowrap">
                        <Link href={href} className="inline-flex items-center gap-2.5 group" prefetch={false}>
                          <StockLogo symbol={item.symbol} size="sm" className="h-7 w-7 rounded-lg" />
                          <div>
                            <div className="font-black text-zinc-950 dark:text-white group-hover:text-amber-600 dark:group-hover:text-[#FFE600] inline-flex items-center gap-1">
                              <span>{item.symbol}</span>
                              <ArrowUpRight className="w-3 h-3 opacity-60" />
                            </div>
                            <div className="text-[11px] text-zinc-500 dark:text-zinc-400 max-w-[180px] truncate">
                              {isAr ? item.name_ar : item.name_en}
                            </div>
                          </div>
                        </Link>
                      </td>
                      <td className="p-3 whitespace-nowrap">{statusBadge(item.status, item.days_until_ex)}</td>
                      <td className="p-3 whitespace-nowrap font-mono font-black text-emerald-700 dark:text-emerald-400">
                        {item.amount.toFixed(item.amount < 1 ? 3 : 2)} {item.currency_ar}
                      </td>
                      <td className="p-3 whitespace-nowrap font-mono font-bold text-zinc-800 dark:text-zinc-200">
                        {typeof item.yield_pct === "number" ? `${item.yield_pct.toFixed(2)}%` : "—"}
                      </td>
                      <td className="p-3 whitespace-nowrap font-mono font-bold text-zinc-900 dark:text-zinc-100">
                        <span className="inline-flex items-center gap-1">
                          <Calendar className="w-3 h-3 text-zinc-400" />
                          {item.ex_date}
                        </span>
                      </td>
                      <td className="p-3 whitespace-nowrap font-mono text-zinc-600 dark:text-zinc-400">
                        {item.record_date || "—"}
                      </td>
                      <td className="p-3 whitespace-nowrap font-mono font-bold text-indigo-700 dark:text-indigo-300">
                        {item.pay_date || (isAr ? "يُعلن قريباً" : "TBA")}
                      </td>
                      {sharesNum > 0 && (
                        <td className="p-3 whitespace-nowrap font-mono">
                          <div className="font-black text-emerald-700 dark:text-emerald-400">
                            {gross.toLocaleString(undefined, { maximumFractionDigits: 2 })} {item.currency_ar}
                          </div>
                          {market === "egx" && (
                            <div className="text-[10px] text-zinc-500">
                              {isAr ? "صافي:" : "Net:"} {net.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                            </div>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Footer Note */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[11px] font-bold text-zinc-500 dark:text-zinc-400">
        <span>{isAr ? meta.taxNoteAr : meta.taxNoteEn}</span>
        {initialData.updatedAt && (
          <span className="font-mono">
            {isAr ? "آخر تحديث:" : "Updated:"} {initialData.updatedAt.slice(0, 16).replace("T", " ")} UTC
          </span>
        )}
      </div>
    </div>
  );
}
