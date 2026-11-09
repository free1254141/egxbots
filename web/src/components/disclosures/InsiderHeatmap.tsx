"use client";

import React, { useState } from "react";
import { HeatmapItem } from "@/lib/disclosures-analytics";
import { TrendingUp, TrendingDown, Layers, Sparkles } from "lucide-react";
import StockLogo from "@/components/StockLogo";

interface InsiderHeatmapProps {
  items: HeatmapItem[];
  isAr: boolean;
  onSelectSymbol?: (symbol: string) => void;
  selectedSymbol?: string;
}

export default function InsiderHeatmap({
  items,
  isAr,
  onSelectSymbol,
  selectedSymbol,
}: InsiderHeatmapProps) {
  const [hoveredItem, setHoveredItem] = useState<HeatmapItem | null>(null);
  const [filterMode, setFilterMode] = useState<"all" | "accumulating" | "distributing">("all");

  const filteredItems = items.filter((item) => {
    if (filterMode === "accumulating") return item.action_bias === "accumulating";
    if (filterMode === "distributing") return item.action_bias === "distributing";
    return true;
  });

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

  return (
    <section className="relative overflow-hidden rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-6 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)] text-black dark:text-white transition-colors">
      {/* Heatmap Header */}
      <div className={`flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b-2 border-black/15 dark:border-white/10 pb-4 mb-5 ${isAr ? "sm:flex-row-reverse text-right" : ""}`}>
        <div className={`flex items-center gap-3 ${isAr ? "flex-row-reverse" : ""}`}>
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-none bg-[#FFE600] text-black border-2 border-black shadow-[2px_2px_0px_#000]">
            <Layers className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base sm:text-lg font-black tracking-tight text-black dark:text-white">
                {isAr ? "الخريطة الحرارية لسيولة الداخليين والكبار" : "Smart Money Insider Liquidity Heatmap"}
              </h3>
              <span className="hidden sm:inline-block px-2 py-0.5 border-2 border-black bg-[#FFE600] text-black text-[10px] font-black uppercase shadow-[1px_1px_0px_#000]">
                {isAr ? "مباشر" : "LIVE"}
              </span>
            </div>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-0.5 font-bold">
              {isAr
                ? "توزيع أحجام سيولة الشراء والبيع لمجالس الإدارات وكبار المساهمين (حجم المربع يعبر عن قيمة التعاملات)"
                : "Volume and flow distribution of insider transactions (box size reflects trade value)"}
            </p>
          </div>
        </div>

        {/* Filter Toggle */}
        <div className={`flex items-center gap-1.5 self-start sm:self-auto ${isAr ? "flex-row-reverse" : ""}`}>
          <button
            type="button"
            onClick={() => setFilterMode("all")}
            className={`px-3 py-1.5 text-xs font-black transition-all border-2 border-black cursor-pointer ${
              filterMode === "all"
                ? "bg-black text-white dark:bg-white dark:text-black shadow-[2px_2px_0px_#000]"
                : "bg-white text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 hover:bg-[#FFE600] hover:text-black"
            }`}
          >
            {isAr ? "الكل" : "All"} ({items.length})
          </button>
          <button
            type="button"
            onClick={() => setFilterMode("accumulating")}
            className={`px-3 py-1.5 text-xs font-black transition-all border-2 border-black flex items-center gap-1 cursor-pointer ${
              filterMode === "accumulating"
                ? "bg-[#00FF66] text-black shadow-[2px_2px_0px_#000]"
                : "bg-white text-emerald-800 dark:bg-zinc-900 dark:text-emerald-400 hover:bg-emerald-50"
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>{isAr ? "تجميع" : "Accumulation"}</span>
          </button>
          <button
            type="button"
            onClick={() => setFilterMode("distributing")}
            className={`px-3 py-1.5 text-xs font-black transition-all border-2 border-black flex items-center gap-1 cursor-pointer ${
              filterMode === "distributing"
                ? "bg-[#FF3366] text-white shadow-[2px_2px_0px_#000]"
                : "bg-white text-rose-800 dark:bg-zinc-900 dark:text-rose-400 hover:bg-rose-50"
            }`}
          >
            <TrendingDown className="w-3.5 h-3.5" />
            <span>{isAr ? "تصريف" : "Distribution"}</span>
          </button>
        </div>
      </div>

      {/* Heatmap Grid */}
      {filteredItems.length === 0 ? (
        <div className="py-12 text-center text-zinc-500 font-bold text-sm">
          {isAr ? "لا توجد أسهم مطابقة لهذا الفلتر حالياً." : "No stocks matching this filter."}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {filteredItems.map((item) => {
            const isBuy = item.action_bias === "accumulating";
            const isSell = item.action_bias === "distributing";
            const isSelected = selectedSymbol === item.symbol;

            // Box styling based on bias - optimized for Light and Dark modes!
            let cardClasses = "relative p-3 rounded-none border-2 transition-all cursor-pointer flex flex-col justify-between select-none ";
            if (isBuy) {
              cardClasses += isSelected
                ? "bg-emerald-100 dark:bg-emerald-900/60 border-black dark:border-[#FFE600] shadow-[3px_3px_0px_#000] dark:shadow-[3px_3px_0px_#FFE600] ring-2 ring-[#00FF66] "
                : "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-600 dark:border-emerald-500/40 hover:border-black dark:hover:border-emerald-400 hover:bg-emerald-100/80 dark:hover:bg-emerald-950/50 shadow-[2px_2px_0px_#000] ";
            } else if (isSell) {
              cardClasses += isSelected
                ? "bg-rose-100 dark:bg-rose-900/60 border-black dark:border-[#FFE600] shadow-[3px_3px_0px_#000] dark:shadow-[3px_3px_0px_#FFE600] ring-2 ring-[#FF3366] "
                : "bg-rose-50 dark:bg-rose-950/30 border-rose-600 dark:border-rose-500/40 hover:border-black dark:hover:border-rose-400 hover:bg-rose-100/80 dark:hover:bg-rose-950/50 shadow-[2px_2px_0px_#000] ";
            } else {
              cardClasses += isSelected
                ? "bg-zinc-200 dark:bg-zinc-800 border-black dark:border-[#FFE600] shadow-[3px_3px_0px_#000] "
                : "bg-zinc-100 dark:bg-zinc-900/40 border-zinc-400 dark:border-zinc-700/50 hover:border-black shadow-[2px_2px_0px_#000] ";
            }

            // Box height according to weight
            const heightClass = item.weight >= 4 ? "min-h-[110px]" : "min-h-[92px]";

            return (
              <div
                key={item.symbol}
                onClick={() => onSelectSymbol && onSelectSymbol(item.symbol)}
                onMouseEnter={() => setHoveredItem(item)}
                onMouseLeave={() => setHoveredItem(null)}
                className={`${cardClasses} ${heightClass}`}
              >
                {/* Top Row: Symbol + Badge */}
                <div className="flex items-center justify-between gap-1 mb-1.5">
                  <div className="flex items-center gap-1.5">
                    <StockLogo symbol={item.symbol} size="sm" />
                    <span className="font-black text-xs sm:text-sm text-black dark:text-white tracking-wider">
                      {item.symbol}
                    </span>
                  </div>
                  <span
                    className={`text-[10px] font-black px-1.5 py-0.5 border border-black ${
                      isBuy
                        ? "bg-[#00FF66] text-black"
                        : isSell
                        ? "bg-[#FF3366] text-white"
                        : "bg-zinc-200 dark:bg-zinc-800 text-black dark:text-zinc-300"
                    }`}
                  >
                    {isBuy ? (isAr ? "شراء" : "BUY") : isSell ? (isAr ? "بيع" : "SELL") : "⚪"}
                  </span>
                </div>

                {/* Middle: Company Name & Value */}
                <div>
                  <p className="text-[11px] font-bold text-zinc-700 dark:text-zinc-300 truncate mb-1" title={item.company_name}>
                    {item.company_name}
                  </p>
                  <p
                    className={`text-xs font-black tracking-tight ${
                      isBuy ? "text-emerald-800 dark:text-emerald-400" : isSell ? "text-rose-800 dark:text-rose-400" : "text-zinc-800 dark:text-zinc-300"
                    }`}
                  >
                    {formatEgp(item.net_value_egp)}
                  </p>
                </div>

                {/* Bottom: Discount Badge or Volume */}
                <div className="mt-2 pt-1.5 border-t border-black/10 dark:border-white/10 flex items-center justify-between text-[10px]">
                  {item.discount_pct < -1.0 && isBuy ? (
                    <span className="text-amber-800 dark:text-amber-300 font-black flex items-center gap-0.5" title={isAr ? "يتداول تحت تكلفة الداخلي" : "Trading below insider cost"}>
                      <Sparkles className="w-2.5 h-2.5 text-amber-600 dark:text-amber-400" />
                      <span>{isAr ? `خصم ${Math.abs(item.discount_pct)}%` : `-${Math.abs(item.discount_pct)}%`}</span>
                    </span>
                  ) : (
                    <span className="text-zinc-600 dark:text-zinc-400 font-bold">
                      {isAr ? `${item.volume.toLocaleString()} سهم` : `${item.volume.toLocaleString()} sh`}
                    </span>
                  )}

                  <span className="text-black dark:text-zinc-300 font-mono font-bold text-[10px]">
                    {item.current_price > 0 ? `${item.current_price.toFixed(2)} ج` : ""}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Floating Detailed Inspection Card when hovered */}
      {hoveredItem && (
        <div
          className={`mt-5 p-4 rounded-none border-4 border-black dark:border-white bg-[#FFE600]/25 dark:bg-zinc-900 shadow-[4px_4px_0px_#000] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-xs ${
            isAr ? "text-right" : ""
          }`}
        >
          <div className="flex items-center gap-3">
            <StockLogo symbol={hoveredItem.symbol} size="md" />
            <div>
              <div className="flex items-center gap-2">
                <span className="font-black text-sm text-black dark:text-white">{hoveredItem.symbol}</span>
                <span className="text-zinc-700 dark:text-zinc-300 text-xs font-bold">— {hoveredItem.company_name}</span>
              </div>
              <p className="text-[11px] text-zinc-600 dark:text-zinc-400 mt-0.5 font-bold">
                {isAr
                  ? `إجمالي تعاملات الداخليين: ${hoveredItem.buy_count} شراء مقابل ${hoveredItem.sell_count} بيع`
                  : `Total Insider Trades: ${hoveredItem.buy_count} buys vs ${hoveredItem.sell_count} sells`}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 border-t sm:border-t-0 sm:border-l sm:border-r border-black/15 dark:border-white/10 px-0 sm:px-4 py-2 sm:py-0">
            <div>
              <span className="text-[10px] text-zinc-600 dark:text-zinc-400 block font-bold">{isAr ? "صافي السيولة" : "Net Flow"}</span>
              <span
                className={`font-black text-xs ${
                  hoveredItem.action_bias === "accumulating" ? "text-emerald-800 dark:text-emerald-400" : "text-rose-800 dark:text-rose-400"
                }`}
              >
                {formatEgp(hoveredItem.net_value_egp)}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-zinc-600 dark:text-zinc-400 block font-bold">{isAr ? "السعر الحالي" : "Current Price"}</span>
              <span className="font-black text-xs text-black dark:text-white">
                {hoveredItem.current_price > 0 ? `${hoveredItem.current_price.toFixed(2)} ج.م` : "-"}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-zinc-600 dark:text-zinc-400 block font-bold">{isAr ? "متوسط تكلفة الداخلي" : "Insider VWAP"}</span>
              <span className="font-black text-xs text-amber-900 dark:text-amber-300">
                {hoveredItem.insider_vwap > 0 ? `${hoveredItem.insider_vwap.toFixed(2)} ج.م` : "-"}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-zinc-600 dark:text-zinc-400 block font-bold">{isAr ? "الفارق السعري" : "Price vs Cost"}</span>
              <span
                className={`font-black text-xs ${
                  hoveredItem.discount_pct < 0 ? "text-emerald-800 dark:text-emerald-400" : "text-amber-800 dark:text-amber-400"
                }`}
              >
                {hoveredItem.discount_pct < 0
                  ? isAr ? `أرخص بـ ${Math.abs(hoveredItem.discount_pct)}% 🟢` : `-${Math.abs(hoveredItem.discount_pct)}% Discount`
                  : isAr ? `أعلى بـ +${hoveredItem.discount_pct}%` : `+${hoveredItem.discount_pct}% Premium`}
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={() => onSelectSymbol && onSelectSymbol(hoveredItem.symbol)}
            className="px-4 py-2 border-2 border-black bg-[#FFE600] text-black font-black text-xs shadow-[2px_2px_0px_#000] hover:bg-white transition-all text-center shrink-0 cursor-pointer"
          >
            {isAr ? "فلترة إفصاحات السهم ↗" : "Filter Disclosures ↗"}
          </button>
        </div>
      )}
    </section>
  );
}
