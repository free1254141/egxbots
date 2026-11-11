"use client";

import React, { useState } from "react";
import { CostComparisonItem, FlowDistribution, TimeframePeriod } from "@/lib/disclosures-analytics";
import { BarChart3, Sparkles, TrendingUp, TrendingDown, Target, ChevronDown, ChevronUp } from "lucide-react";
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
  onSelectTimeframe,
  onSelectSymbol,
  onFilterBelowCost,
}: InsiderChartsProps) {
  const [showAllDiscounts, setShowAllDiscounts] = useState(false);

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

  const displayedDiscounts = showAllDiscounts ? costDiscounts : costDiscounts.slice(0, 5);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 my-6">
      {/* Chart 1: Cost vs Current Market Price (The Discount Detector) */}
      <div className="rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)] text-black dark:text-white flex flex-col justify-between transition-colors">
        <div>
          <div className={`flex items-center justify-between border-b-2 border-black/15 dark:border-white/10 pb-3 mb-4 ${isAr ? "flex-row-reverse text-right" : ""}`}>
            <div className={`flex items-center gap-2.5 ${isAr ? "flex-row-reverse" : ""}`}>
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-none bg-amber-400 text-black border-2 border-black shadow-[2px_2px_0px_#000]">
                <Target className="h-5 w-5" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-sm sm:text-base font-black text-black dark:text-white">
                    {isAr ? "مقارنة تكلفة الداخلي بسعر السوق (خصم استثنائي)" : "Insider Cost vs Market Price"}
                  </h4>
                  {timeframeLabel && (
                    <span className="px-2 py-0.5 bg-black text-white dark:bg-white dark:text-black font-black text-[10px] uppercase shadow-[1px_1px_0px_#FFE600]">
                      {timeframeLabel}
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-zinc-600 dark:text-zinc-400 font-bold">
                  {isAr ? "أسهم يتداول فيها السوق حالياً بأقل من تكلفة شراء أصحاب الشركة (بعد خصم أي عمليات بيع)" : "Stocks trading below insider cost (net of any insider sales)"}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1.5 shrink-0">
              {costDiscounts.length > 5 && (
                <button
                  type="button"
                  onClick={() => setShowAllDiscounts(!showAllDiscounts)}
                  className="px-2 py-0.5 border-2 border-black bg-amber-400 hover:bg-[#FFE600] text-black text-[10px] font-black uppercase shadow-[1px_1px_0px_#000] cursor-pointer transition-colors flex items-center gap-0.5"
                  title={isAr ? "إظهار أو طي كافة الأسهم" : "Toggle all stocks"}
                >
                  <span>{showAllDiscounts ? (isAr ? "عرض 5 فقط" : "Show 5") : (isAr ? `عرض الكل (${costDiscounts.length})` : `All (${costDiscounts.length})`)}</span>
                  {showAllDiscounts ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </button>
              )}
              <span className="px-2 py-0.5 border-2 border-black bg-[#FFE600] text-black text-[10px] font-black uppercase shadow-[1px_1px_0px_#000]">
                {isAr ? "فرص ذهبية" : "OPPORTUNITIES"}
              </span>
            </div>
          </div>

          {costDiscounts.length === 0 ? (
            <div className="py-8 px-4 text-center border-2 border-dashed border-black/20 dark:border-white/20 bg-zinc-50 dark:bg-zinc-900/40 my-3">
              <div className="text-zinc-700 dark:text-zinc-200 font-black text-xs sm:text-sm mb-1.5">
                {isAr
                  ? `لا توجد أسهم تتداول بأقل من تكلفة الداخليين خلال فترة (${timeframeLabel || "المحددة"}).`
                  : `No stocks trading below insider cost during (${timeframeLabel || "selected period"}).`}
              </div>
              <p className="text-[11px] text-zinc-500 font-bold mb-3 max-w-md mx-auto leading-relaxed">
                {isAr
                  ? "جميع الأسهم التي شهدت تجميعاً داخلياً تتداول حالياً عند أو فوق تكلفة الشراء، أو أن عمليات البيع ألغت الشراء (الصافي صفر أو سالب)."
                  : "All accumulated stocks trade at/above insider cost, or sells offset buys (net <= 0)."}
              </p>
              {onSelectTimeframe && (
                <div className="flex flex-wrap items-center justify-center gap-2">
                  <button
                    type="button"
                    onClick={() => onSelectTimeframe("30d")}
                    className="px-3 py-1 bg-[#FFE600] text-black border-2 border-black font-black text-[11px] hover:bg-black hover:text-white transition-colors cursor-pointer shadow-[2px_2px_0px_#000]"
                  >
                    {isAr ? "🔍 استعراض فرص آخر 30 يوماً" : "View 30-Day Discounts"}
                  </button>
                  <button
                    type="button"
                    onClick={() => onSelectTimeframe("all")}
                    className="px-3 py-1 bg-white dark:bg-zinc-800 text-black dark:text-white border-2 border-black font-black text-[11px] hover:bg-[#00FF66] hover:text-black transition-colors cursor-pointer shadow-[2px_2px_0px_#000]"
                  >
                    {isAr ? "عرض كامل السجل" : "View All-Time"}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className={`space-y-3.5 ${showAllDiscounts ? "max-h-[460px] overflow-y-auto pr-1 sm:pr-2" : ""}`}>
              {displayedDiscounts.map((item) => {
                const maxPrice = Math.max(item.insider_vwap, item.current_price) * 1.15;
                const costWidth = Math.min(100, Math.max(15, (item.insider_vwap / maxPrice) * 100));
                const curWidth = Math.min(100, Math.max(15, (item.current_price / maxPrice) * 100));

                return (
                  <div
                    key={item.symbol}
                    onClick={() => onSelectSymbol && onSelectSymbol(item.symbol)}
                    className="p-3 rounded-none border-2 border-black/20 dark:border-white/10 bg-zinc-50 dark:bg-zinc-900/50 hover:border-black dark:hover:border-amber-400/50 transition-all cursor-pointer group shadow-[2px_2px_0px_rgba(0,0,0,0.8)]"
                  >
                    <div className="flex items-center justify-between text-xs mb-2">
                      <div className="flex items-center gap-2">
                        <StockLogo symbol={item.symbol} size="sm" />
                        <span className="font-black text-black dark:text-white text-xs">{item.symbol}</span>
                        <span className="text-[11px] text-zinc-600 dark:text-zinc-400 font-bold truncate max-w-[140px] sm:max-w-[200px]">
                          {item.company_name}
                        </span>
                      </div>
                      <span className="px-2 py-0.5 border border-black bg-[#00FF66] text-black font-black text-[11px] flex items-center gap-1 shadow-[1px_1px_0px_#000]">
                        <Sparkles className="w-3 h-3 text-black" />
                        <span>{isAr ? `خصم -${item.discount_pct}%` : `-${item.discount_pct}%`}</span>
                      </span>
                    </div>

                    {/* Dual Comparative Visual Bars */}
                    <div className="space-y-1.5 text-[10px]">
                      {/* Insider VWAP Bar */}
                      <div className="flex items-center gap-2">
                        <span className="w-20 text-zinc-600 dark:text-zinc-400 font-bold text-right truncate">
                          {isAr ? "تكلفة الداخلي:" : "Insider Cost:"}
                        </span>
                        <div className="flex-1 bg-zinc-200 dark:bg-zinc-800 border border-black/20 dark:border-white/10 h-3.5 overflow-hidden">
                          <div
                            className="bg-amber-400 h-full transition-all duration-500"
                            style={{ width: `${costWidth}%` }}
                          />
                        </div>
                        <span className="font-mono font-black text-amber-800 dark:text-amber-300 w-16 text-left">
                          {item.insider_vwap.toFixed(2)} ج
                        </span>
                      </div>

                      {/* Current Market Price Bar */}
                      <div className="flex items-center gap-2">
                        <span className="w-20 text-zinc-600 dark:text-zinc-400 font-bold text-right truncate">
                          {isAr ? "سعر السوق:" : "Market Price:"}
                        </span>
                        <div className="flex-1 bg-zinc-200 dark:bg-zinc-800 border border-black/20 dark:border-white/10 h-3.5 overflow-hidden">
                          <div
                            className="bg-[#00FF66] h-full transition-all duration-500"
                            style={{ width: `${curWidth}%` }}
                          />
                        </div>
                        <span className="font-mono font-black text-emerald-800 dark:text-emerald-400 w-16 text-left">
                          {item.current_price.toFixed(2)} ج
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Interactive Toggle & Filter Action Strip */}
          {costDiscounts.length > 5 && (
            <div className="mt-4 pt-3 border-t-2 border-black/15 dark:border-white/10 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setShowAllDiscounts(!showAllDiscounts)}
                className="flex-1 py-2 px-3 bg-[#FFE600] hover:bg-black hover:text-white text-black border-2 border-black font-black text-xs uppercase shadow-[2px_2px_0px_#000] flex items-center justify-center gap-1.5 cursor-pointer active:translate-y-0.5 transition-all"
              >
                <Target className="w-3.5 h-3.5" />
                <span>
                  {showAllDiscounts
                    ? (isAr ? "طي القائمة (إظهار أول 5 أسهم فقط) ▴" : "Collapse to Top 5 ▴")
                    : (isAr ? `عرض جميع الأسهم الـ (${costDiscounts.length}) التي تتداول بأقل من التكلفة ▾` : `Show all (${costDiscounts.length}) discounted stocks ▾`)}
                </span>
              </button>

              {onFilterBelowCost && (
                <button
                  type="button"
                  onClick={onFilterBelowCost}
                  className="py-2 px-3 bg-white dark:bg-zinc-900 hover:bg-[#00FF66] text-black dark:text-white hover:text-black border-2 border-black dark:border-white font-black text-xs uppercase shadow-[2px_2px_0px_#000] flex items-center justify-center gap-1.5 cursor-pointer active:translate-y-0.5 transition-all"
                  title={isAr ? "تصفية جدول الإفصاحات بهذه الأسهم فقط" : "Filter table for these stocks"}
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>{isAr ? "تصفية الجدول بهذه الأسهم" : "Filter Table"}</span>
                </button>
              )}
            </div>
          )}
        </div>

        <div className="mt-4 pt-3 border-t-2 border-black/10 dark:border-white/10 flex items-center justify-between text-[11px] text-zinc-600 dark:text-zinc-400 font-bold">
          <span>{isAr ? "💡 محسوب استناداً إلى متوسط أسعار تنفيذ عمليات الشراء" : "Calculated from execution average prices"}</span>
          <button
            type="button"
            onClick={() => setShowAllDiscounts(!showAllDiscounts)}
            className="text-amber-600 dark:text-amber-400 font-black hover:underline cursor-pointer flex items-center gap-1"
          >
            <span>{costDiscounts.length} {isAr ? "أسهم تحت التكلفة" : "stocks discounted"}</span>
            <span className="text-[10px]">{showAllDiscounts ? (isAr ? "(طي ▴)" : "(less ▴)") : (isAr ? "(عرض الكل ▾)" : "(all ▾)")}</span>
          </button>
        </div>
      </div>

      {/* Chart 2: Net Flow Ratio & Distribution Balance */}
      <div className="rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)] text-black dark:text-white flex flex-col justify-between transition-colors">
        <div>
          <div className={`flex items-center justify-between border-b-2 border-black/15 dark:border-white/10 pb-3 mb-4 ${isAr ? "flex-row-reverse text-right" : ""}`}>
            <div className={`flex items-center gap-2.5 ${isAr ? "flex-row-reverse" : ""}`}>
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-none bg-[#00FF66] text-black border-2 border-black shadow-[2px_2px_0px_#000]">
                <BarChart3 className="h-5 w-5" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-sm sm:text-base font-black text-black dark:text-white">
                    {isAr ? "ميزان تدفق السيولة الكلية للداخليين" : "Total Insider Net Flow Balance"}
                  </h4>
                  {timeframeLabel && (
                    <span className="px-2 py-0.5 bg-black text-white dark:bg-white dark:text-black font-black text-[10px] uppercase shadow-[1px_1px_0px_#00FF66]">
                      {timeframeLabel}
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-zinc-600 dark:text-zinc-400 font-bold">
                  {isAr ? "مقارنة إجمالي قيمة الشراء والتجميع مقابل البيع والتصريف في السوق" : "Aggregate buy vs sell transaction values across all tracked symbols"}
                </p>
              </div>
            </div>
            <span className="px-2 py-0.5 border-2 border-black bg-[#FFE600] text-black text-[10px] font-black uppercase shadow-[1px_1px_0px_#000]">
              {flowDistribution.buy_ratio_pct >= 50 ? (isAr ? "تجميع غالب" : "BUY BIAS") : (isAr ? "تصريف غالب" : "SELL BIAS")}
            </span>
          </div>

          {/* Ratio Progress Bar */}
          <div className="space-y-3 mb-6">
            <div className="flex justify-between items-center text-xs font-black">
              <span className="text-emerald-800 dark:text-emerald-400 flex items-center gap-1">
                <TrendingUp className="w-3.5 h-3.5" />
                <span>{isAr ? "شراء وتجميع:" : "Buys:"} {flowDistribution.buy_ratio_pct}%</span>
              </span>
              <span className="text-rose-800 dark:text-rose-400 flex items-center gap-1">
                <TrendingDown className="w-3.5 h-3.5" />
                <span>{isAr ? "بيع وتخارج:" : "Sells:"} {flowDistribution.sell_ratio_pct}%</span>
              </span>
            </div>

            <div className="h-6 w-full bg-zinc-200 dark:bg-zinc-800 border-2 border-black dark:border-white flex p-0.5 shadow-inner">
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

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="p-3.5 border-2 border-emerald-600 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-950/20 text-center shadow-[2px_2px_0px_#000]">
              <span className="text-[11px] text-zinc-600 dark:text-zinc-400 block mb-1 font-bold">
                {isAr ? "إجمالي قيمة الشراء الداخلي" : "Total Buy Value"}
              </span>
              <span className="text-base sm:text-lg font-black text-emerald-800 dark:text-emerald-400">
                {formatEgp(flowDistribution.total_buy_value_egp)}
              </span>
            </div>

            <div className="p-3.5 border-2 border-rose-600 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-950/20 text-center shadow-[2px_2px_0px_#000]">
              <span className="text-[11px] text-zinc-600 dark:text-zinc-400 block mb-1 font-bold">
                {isAr ? "إجمالي قيمة البيع الداخلي" : "Total Sell Value"}
              </span>
              <span className="text-base sm:text-lg font-black text-rose-800 dark:text-rose-400">
                {formatEgp(flowDistribution.total_sell_value_egp)}
              </span>
            </div>
          </div>

          <div className="p-3 border-2 border-black dark:border-white/20 bg-zinc-100 dark:bg-zinc-900/60 flex items-center justify-between text-xs">
            <span className="text-zinc-700 dark:text-zinc-300 font-bold">
              {isAr ? "صافي تدفق السيولة الكلي:" : "Net Insider Liquidity:"}
            </span>
            <span
              className={`font-black text-sm ${
                flowDistribution.net_value_egp >= 0 ? "text-emerald-800 dark:text-emerald-400" : "text-rose-800 dark:text-rose-400"
              }`}
            >
              {flowDistribution.net_value_egp >= 0 ? "+" : ""}
              {formatEgp(flowDistribution.net_value_egp)}
            </span>
          </div>
        </div>

        <div className="mt-4 pt-3 border-t-2 border-black/10 dark:border-white/10 flex items-center justify-between text-[11px] text-zinc-600 dark:text-zinc-400 font-bold">
          <span>{isAr ? "تغطية الشركات:" : "Companies Tracked:"} {flowDistribution.total_companies_tracked} {isAr ? "شركة مقيدة" : "listed companies"}</span>
          <span className="text-black dark:text-white font-black">EGX Smart Money</span>
        </div>
      </div>
    </div>
  );
}
