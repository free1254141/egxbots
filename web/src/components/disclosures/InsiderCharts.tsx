"use client";

import React, { useState, useMemo } from "react";
import { CostComparisonItem, FlowDistribution, TimeframePeriod } from "@/lib/disclosures-analytics";
import {
  BarChart3,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Target,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  Lock,
  Calendar,
  Layers,
} from "lucide-react";
import StockLogo from "@/components/StockLogo";

interface InsiderChartsProps {
  costDiscounts: CostComparisonItem[];
  flowDistribution: FlowDistribution;
  isAr: boolean;
  timeframeLabel?: string;
  onSelectTimeframe?: (tf: TimeframePeriod) => void;
  onSelectSymbol?: (symbol: string) => void;
  onFilterBelowCost?: () => void;
}

export default function InsiderCharts({
  costDiscounts,
  flowDistribution,
  isAr,
  timeframeLabel,
  onSelectSymbol,
  onFilterBelowCost,
}: InsiderChartsProps) {
  const [costTab, setCostTab] = useState<"all" | "below_cost" | "held_above">("all");
  const [showAllCards, setShowAllCards] = useState(true);

  const formatEgp = (val: number) => {
    const abs = Math.abs(val);
    if (abs >= 1_000_000) {
      return `${(val / 1_000_000).toFixed(1)} ${isAr ? "مليون ج.م" : "M EGP"}`;
    }
    if (abs >= 1_000) {
      return `${(val / 1_000).toFixed(0)} ${isAr ? "ألف ج.م" : "k EGP"}`;
    }
    return `${val.toFixed(0)} ${isAr ? "ج.م" : "EGP"}`;
  };

  const formatShares = (shares: number) => {
    if (shares >= 1_000_000) {
      return `${(shares / 1_000_000).toFixed(2)} ${isAr ? "مليون سهم" : "M shares"}`;
    }
    if (shares >= 1_000) {
      return `${(shares / 1_000).toFixed(1)} ${isAr ? "ألف سهم" : "K shares"}`;
    }
    return `${shares.toLocaleString()} ${isAr ? "سهم" : "shares"}`;
  };

  const belowCostItems = useMemo(
    () => costDiscounts.filter((item) => item.is_below_cost || item.price_diff_pct <= 0),
    [costDiscounts]
  );

  const aboveCostItems = useMemo(
    () => costDiscounts.filter((item) => !item.is_below_cost && item.price_diff_pct > 0),
    [costDiscounts]
  );

  const activeList = useMemo(() => {
    if (costTab === "below_cost") return belowCostItems;
    if (costTab === "held_above") return aboveCostItems;
    return costDiscounts;
  }, [costTab, costDiscounts, belowCostItems, aboveCostItems]);

  const displayedList = showAllCards ? activeList : activeList.slice(0, 6);

  return (
    <div className="space-y-6 my-6">
      {/* SECTION 1: Full-Width Persistent Insider Cost vs Market Price Tracker */}
      <div
        id="insider-cost-comparison"
        className="rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-6 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)] text-black dark:text-white transition-colors"
      >
        {/* Header Row */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b-2 border-black/15 dark:border-white/10 pb-4 mb-4">
          <div className="flex items-start gap-3">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-none bg-amber-400 text-black border-2 border-black shadow-[3px_3px_0px_#000]">
              <Target className="h-6 w-6" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <h3 className="text-base sm:text-lg font-black text-black dark:text-white">
                  {isAr
                    ? "مقارنة تكلفة الداخلي بسعر السوق (خصم استثنائي وسجل التجميع المستمر)"
                    : "Insider Cost vs Market Price (Cumulative Active Accumulation)"}
                </h3>
                <span className="px-2.5 py-0.5 border-2 border-black bg-[#00FF66] text-black text-[10px] font-black uppercase shadow-[2px_2px_0px_#000] flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>
                    {isAr
                      ? `محتفظ بـ ${costDiscounts.length} سهم مفحوص بلا إفصاح بيع يلغيها`
                      : `${costDiscounts.length} Verified Held Stocks`}
                  </span>
                </span>
              </div>
              <p className="text-xs text-zinc-600 dark:text-zinc-400 font-bold leading-relaxed">
                {isAr
                  ? "يحتفظ هذا القسم تلقائياً بجميع الأسهم التي فحصها الرادار وثبت فيها شراء الداخليين أو كبار المساهمين دون صدور أي إفصاح بيع يلغي التجميع — حتى لو مر على الإفصاح عدة أسابيع."
                  : "Automatically retains all examined stocks with positive net insider accumulation and zero cancelling sell filings across the entire historical archive."}
              </p>
            </div>
          </div>

          {/* Sub-filter Tabs for Cost Comparison */}
          <div className="flex flex-wrap items-center gap-1.5 shrink-0">
            <button
              type="button"
              onClick={() => setCostTab("all")}
              className={`px-3 py-1.5 text-xs font-black border-2 border-black dark:border-white transition-all cursor-pointer flex items-center gap-1.5 ${
                costTab === "all"
                  ? "bg-[#FFE600] text-black shadow-[2px_2px_0px_#000]"
                  : "bg-zinc-100 dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-800"
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>
                {isAr
                  ? `كل الأسهم المحتفظ بها (${costDiscounts.length})`
                  : `All Retained (${costDiscounts.length})`}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setCostTab("below_cost")}
              className={`px-3 py-1.5 text-xs font-black border-2 border-black dark:border-white transition-all cursor-pointer flex items-center gap-1.5 ${
                costTab === "below_cost"
                  ? "bg-[#00FF66] text-black shadow-[2px_2px_0px_#000]"
                  : "bg-zinc-100 dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-800"
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>
                {isAr
                  ? `💎 أقل من تكلفة الداخلي (${belowCostItems.length})`
                  : `Below Insider Cost (${belowCostItems.length})`}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setCostTab("held_above")}
              className={`px-3 py-1.5 text-xs font-black border-2 border-black dark:border-white transition-all cursor-pointer flex items-center gap-1.5 ${
                costTab === "held_above"
                  ? "bg-amber-400 text-black shadow-[2px_2px_0px_#000]"
                  : "bg-zinc-100 dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-800"
              }`}
            >
              <Lock className="w-3.5 h-3.5" />
              <span>
                {isAr
                  ? `🔒 مستمرة في التجميع (${aboveCostItems.length})`
                  : `Held Above Cost (${aboveCostItems.length})`}
              </span>
            </button>
          </div>
        </div>

        {/* Cards Grid */}
        {displayedList.length === 0 ? (
          <div className="py-8 px-4 text-center border-2 border-dashed border-black/20 dark:border-white/20 bg-zinc-50 dark:bg-zinc-900/40 my-2">
            <div className="text-zinc-700 dark:text-zinc-200 font-black text-sm mb-1">
              {isAr ? "لا توجد أسهم مطابقة لهذا التصنيف حالياً." : "No stocks match this filter."}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3.5">
            {displayedList.map((item) => {
              const isDiscount = item.is_below_cost || item.price_diff_pct <= 0;
              const maxPrice = Math.max(item.insider_vwap, item.current_price, 0.01) * 1.12;
              const costWidth = Math.min(100, Math.max(18, (item.insider_vwap / maxPrice) * 100));
              const curWidth = Math.min(100, Math.max(18, (item.current_price / maxPrice) * 100));
              const pricePrecision = item.insider_vwap < 1 || item.current_price < 1 ? 3 : 2;

              return (
                <div
                  key={item.symbol}
                  onClick={() => onSelectSymbol && onSelectSymbol(item.symbol)}
                  className={`p-3.5 rounded-none border-2 transition-all cursor-pointer group flex flex-col justify-between ${
                    isDiscount
                      ? "border-black dark:border-emerald-500/40 bg-emerald-50/40 dark:bg-zinc-900/80 hover:border-emerald-500 shadow-[3px_3px_0px_rgba(0,0,0,0.9)]"
                      : "border-black/40 dark:border-white/20 bg-zinc-50 dark:bg-zinc-900/50 hover:border-amber-400 shadow-[3px_3px_0px_rgba(0,0,0,0.8)]"
                  }`}
                >
                  <div>
                    {/* Top Row: Stock Identity + Status Badge */}
                    <div className="flex items-start justify-between gap-2 mb-2.5">
                      <div className="flex items-center gap-2 min-w-0">
                        <StockLogo symbol={item.symbol} size="sm" />
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="font-black text-black dark:text-white text-sm group-hover:text-amber-500 transition-colors">
                              {item.symbol}
                            </span>
                            {item.sector && (
                              <span className="text-[10px] px-1.5 py-0.5 bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 font-bold truncate max-w-[110px]">
                                {isAr ? item.sector.ar : item.sector.en}
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-zinc-600 dark:text-zinc-400 font-bold truncate">
                            {item.company_name}
                          </div>
                        </div>
                      </div>

                      {isDiscount ? (
                        <span className="shrink-0 px-2 py-1 border-2 border-black bg-[#00FF66] text-black font-black text-[11px] flex items-center gap-1 shadow-[2px_2px_0px_#000]">
                          <Sparkles className="w-3 h-3 text-black shrink-0" />
                          <span>
                            {isAr
                              ? `خصم -${Math.abs(item.price_diff_pct).toFixed(1)}%`
                              : `-${Math.abs(item.price_diff_pct).toFixed(1)}%`}
                          </span>
                        </span>
                      ) : (
                        <span className="shrink-0 px-2 py-1 border-2 border-black bg-amber-400 text-black font-black text-[11px] flex items-center gap-1 shadow-[2px_2px_0px_#000]">
                          <Lock className="w-3 h-3 text-black shrink-0" />
                          <span>
                            {isAr
                              ? `محتفظ به +${item.price_diff_pct.toFixed(1)}%`
                              : `Held +${item.price_diff_pct.toFixed(1)}%`}
                          </span>
                        </span>
                      )}
                    </div>

                    {/* Dual Comparative Visual Bars */}
                    <div className="space-y-2 text-[11px] my-3 p-2.5 bg-white dark:bg-zinc-950 border border-black/15 dark:border-white/10">
                      {/* Insider VWAP Bar */}
                      <div className="flex items-center gap-2">
                        <span className="w-24 text-zinc-600 dark:text-zinc-400 font-bold truncate">
                          {isAr ? "تكلفة الداخلي:" : "Insider Cost:"}
                        </span>
                        <div className="flex-1 bg-zinc-200 dark:bg-zinc-800 border border-black/20 dark:border-white/10 h-3.5 overflow-hidden">
                          <div
                            className="bg-amber-400 h-full transition-all duration-500"
                            style={{ width: `${costWidth}%` }}
                          />
                        </div>
                        <span className="font-mono font-black text-amber-700 dark:text-amber-300 w-18 text-left shrink-0">
                          {item.insider_vwap.toFixed(pricePrecision)} {isAr ? "ج" : "EGP"}
                        </span>
                      </div>

                      {/* Current Market Price Bar */}
                      <div className="flex items-center gap-2">
                        <span className="w-24 text-zinc-600 dark:text-zinc-400 font-bold truncate">
                          {isAr ? "سعر السوق:" : "Market Price:"}
                        </span>
                        <div className="flex-1 bg-zinc-200 dark:bg-zinc-800 border border-black/20 dark:border-white/10 h-3.5 overflow-hidden">
                          <div
                            className={`${isDiscount ? "bg-[#00FF66]" : "bg-sky-400"} h-full transition-all duration-500`}
                            style={{ width: `${curWidth}%` }}
                          />
                        </div>
                        <span
                          className={`font-mono font-black w-18 text-left shrink-0 ${
                            isDiscount
                              ? "text-emerald-700 dark:text-emerald-400"
                              : "text-sky-700 dark:text-sky-300"
                          }`}
                        >
                          {item.current_price.toFixed(pricePrecision)} {isAr ? "ج" : "EGP"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Card Footer: Net Shares Held + Filing Date + No-Cancel Status */}
                  <div className="pt-2 border-t border-black/10 dark:border-white/10 flex items-center justify-between gap-2 text-[10px] font-bold text-zinc-600 dark:text-zinc-400">
                    <div className="flex items-center gap-1.5 truncate">
                      <span className="px-1.5 py-0.5 bg-emerald-500/15 text-emerald-800 dark:text-emerald-300 font-black">
                        {isAr ? "صافي التجميع:" : "Net Held:"} {formatShares(item.shares_accumulated)}
                      </span>
                      {item.buy_value_egp > 0 && (
                        <span className="text-zinc-500 dark:text-zinc-400">
                          ({formatEgp(item.buy_value_egp)})
                        </span>
                      )}
                    </div>
                    {item.last_action_date && (
                      <span className="flex items-center gap-1 shrink-0 text-zinc-500 dark:text-zinc-400">
                        <Calendar className="w-3 h-3 text-amber-500" />
                        <span>{item.last_action_date}</span>
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Bottom Action Bar */}
        <div className="mt-4 pt-3 border-t-2 border-black/15 dark:border-white/10 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <div className="text-[11px] text-zinc-600 dark:text-zinc-400 font-bold flex items-center gap-2">
            <span>
              {isAr
                ? "💡 يتم الاحتفاظ بالسهم في هذه القائمة طالما لم يصدر إفصاح بيع يلغي كمية الشراء المجمعة. اضغط على أي سهم لفتح ملفه الكامل."
                : "💡 Stocks remain in this list as long as no subsequent sell filing cancels out the accumulated shares. Click any card for full details."}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2 shrink-0">
            {activeList.length > 6 && (
              <button
                type="button"
                onClick={() => setShowAllCards(!showAllCards)}
                className="py-1.5 px-3 bg-[#FFE600] hover:bg-black hover:text-white text-black border-2 border-black font-black text-xs uppercase shadow-[2px_2px_0px_#000] flex items-center justify-center gap-1.5 cursor-pointer transition-all"
              >
                {showAllCards ? (
                  <>
                    <span>{isAr ? "عرض 6 أسهم فقط" : "Show 6 Only"}</span>
                    <ChevronUp className="w-3.5 h-3.5" />
                  </>
                ) : (
                  <>
                    <span>
                      {isAr ? `عرض الكل (${activeList.length} سهم)` : `Show All (${activeList.length})`}
                    </span>
                    <ChevronDown className="w-3.5 h-3.5" />
                  </>
                )}
              </button>
            )}

            {onFilterBelowCost && (
              <button
                type="button"
                onClick={onFilterBelowCost}
                className="py-1.5 px-3 bg-white dark:bg-zinc-900 hover:bg-[#00FF66] text-black dark:text-white hover:text-black border-2 border-black dark:border-white font-black text-xs uppercase shadow-[2px_2px_0px_#000] flex items-center justify-center gap-1.5 cursor-pointer transition-all"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>{isAr ? "تصفية سجل الإفصاحات بالأسهم تحت التكلفة" : "Filter Feed Below Cost"}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* SECTION 2: Total Insider Net Flow Balance Bar */}
      <div className="rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-5 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)] text-black dark:text-white transition-colors">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
          {/* Title & Bias */}
          <div className="lg:col-span-4 flex items-center gap-3">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-none bg-[#00FF66] text-black border-2 border-black shadow-[2px_2px_0px_#000]">
              <BarChart3 className="h-5 w-5" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h4 className="text-sm sm:text-base font-black text-black dark:text-white">
                  {isAr ? "ميزان تدفق السيولة الكلية للداخليين" : "Total Insider Net Flow Balance"}
                </h4>
                {timeframeLabel && (
                  <span className="px-2 py-0.5 bg-black text-white dark:bg-white dark:text-black font-black text-[10px] uppercase">
                    {timeframeLabel}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-zinc-600 dark:text-zinc-400 font-bold">
                {isAr
                  ? `مقارنة إجمالي الشراء مقابل البيع لـ ${flowDistribution.total_companies_tracked} شركة`
                  : `Buy vs Sell volume across ${flowDistribution.total_companies_tracked} companies`}
              </p>
            </div>
          </div>

          {/* Ratio Progress Bar */}
          <div className="lg:col-span-4 space-y-1.5">
            <div className="flex justify-between items-center text-xs font-black">
              <span className="text-emerald-800 dark:text-emerald-400 flex items-center gap-1">
                <TrendingUp className="w-3.5 h-3.5" />
                <span>
                  {isAr ? "شراء وتجميع:" : "Buys:"} {flowDistribution.buy_ratio_pct}%
                </span>
              </span>
              <span className="text-rose-800 dark:text-rose-400 flex items-center gap-1">
                <TrendingDown className="w-3.5 h-3.5" />
                <span>
                  {isAr ? "بيع وتخارج:" : "Sells:"} {flowDistribution.sell_ratio_pct}%
                </span>
              </span>
            </div>
            <div className="h-5 w-full bg-zinc-200 dark:bg-zinc-800 border-2 border-black dark:border-white flex p-0.5">
              <div
                className="bg-[#00FF66] h-full transition-all duration-700 flex items-center justify-center text-[10px] text-black font-black"
                style={{ width: `${flowDistribution.buy_ratio_pct}%` }}
              >
                {flowDistribution.buy_ratio_pct > 15 ? `${flowDistribution.buy_ratio_pct}%` : ""}
              </div>
              <div
                className="bg-[#FF3366] h-full transition-all duration-700 flex items-center justify-center text-[10px] text-white font-black"
                style={{ width: `${flowDistribution.sell_ratio_pct}%` }}
              >
                {flowDistribution.sell_ratio_pct > 15 ? `${flowDistribution.sell_ratio_pct}%` : ""}
              </div>
            </div>
          </div>

          {/* Buy / Sell / Net Numbers */}
          <div className="lg:col-span-4 grid grid-cols-3 gap-2 text-center">
            <div className="p-2 border-2 border-emerald-600/40 bg-emerald-50 dark:bg-emerald-950/20">
              <span className="text-[10px] text-zinc-600 dark:text-zinc-400 block font-bold">
                {isAr ? "إجمالي الشراء" : "Total Buys"}
              </span>
              <span className="text-xs sm:text-sm font-black text-emerald-800 dark:text-emerald-400">
                {formatEgp(flowDistribution.total_buy_value_egp)}
              </span>
            </div>
            <div className="p-2 border-2 border-rose-600/40 bg-rose-50 dark:bg-rose-950/20">
              <span className="text-[10px] text-zinc-600 dark:text-zinc-400 block font-bold">
                {isAr ? "إجمالي البيع" : "Total Sells"}
              </span>
              <span className="text-xs sm:text-sm font-black text-rose-800 dark:text-rose-400">
                {formatEgp(flowDistribution.total_sell_value_egp)}
              </span>
            </div>
            <div className="p-2 border-2 border-black dark:border-white/20 bg-zinc-100 dark:bg-zinc-900/60">
              <span className="text-[10px] text-zinc-600 dark:text-zinc-400 block font-bold">
                {isAr ? "صافي السيولة" : "Net Flow"}
              </span>
              <span
                className={`text-xs sm:text-sm font-black ${
                  flowDistribution.net_value_egp >= 0
                    ? "text-emerald-800 dark:text-emerald-400"
                    : "text-rose-800 dark:text-rose-400"
                }`}
              >
                {flowDistribution.net_value_egp >= 0 ? "+" : ""}
                {formatEgp(flowDistribution.net_value_egp)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
