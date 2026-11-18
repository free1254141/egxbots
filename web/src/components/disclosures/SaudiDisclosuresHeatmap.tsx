"use client";

import React, { useMemo, useState } from "react";
import { DisclosureItem } from "@/lib/disclosures-analytics";
import { Layers, TrendingUp, TrendingDown, Minus } from "lucide-react";
import StockLogo from "@/components/StockLogo";

interface SaudiDisclosuresHeatmapProps {
  disclosures: DisclosureItem[];
  isAr: boolean;
  onSelectSymbol?: (symbol: string) => void;
  selectedSymbol?: string;
}

interface SaudiHeatmapTile {
  symbol: string;
  companyName: string;
  total: number;
  bullish: number;
  bearish: number;
  neutral: number;
  latestDate: string;
  bias: "bullish" | "bearish" | "neutral";
}

export default function SaudiDisclosuresHeatmap({
  disclosures,
  isAr,
  onSelectSymbol,
  selectedSymbol,
}: SaudiDisclosuresHeatmapProps) {
  const [filterMode, setFilterMode] = useState<"all" | "bullish" | "bearish" | "neutral">("all");

  const tiles = useMemo<SaudiHeatmapTile[]>(() => {
    const map = new Map<string, SaudiHeatmapTile>();

    for (const d of disclosures) {
      const sym = (d.symbol || "").trim().toUpperCase();
      if (!sym) continue;

      let entry = map.get(sym);
      if (!entry) {
        entry = {
          symbol: sym,
          companyName: d.company_name || sym,
          total: 0,
          bullish: 0,
          bearish: 0,
          neutral: 0,
          latestDate: d.disclosure_date || "",
          bias: "neutral",
        };
        map.set(sym, entry);
      }

      entry.total += 1;
      if (d.sentiment === "bullish" || d.action_type === "buy") {
        entry.bullish += 1;
      } else if (d.sentiment === "bearish" || d.action_type === "sell") {
        entry.bearish += 1;
      } else {
        entry.neutral += 1;
      }

      if (d.disclosure_date && d.disclosure_date > entry.latestDate) {
        entry.latestDate = d.disclosure_date;
      }
      if (!entry.companyName && d.company_name) {
        entry.companyName = d.company_name;
      }
    }

    const result = Array.from(map.values()).map((item) => {
      let bias: "bullish" | "bearish" | "neutral" = "neutral";
      if (item.bullish > item.bearish && item.bullish >= item.neutral) {
        bias = "bullish";
      } else if (item.bearish > item.bullish && item.bearish >= item.neutral) {
        bias = "bearish";
      } else if (item.bullish > item.bearish) {
        bias = "bullish";
      } else if (item.bearish > item.bullish) {
        bias = "bearish";
      }
      return { ...item, bias };
    });

    return result.sort((a, b) => b.total - a.total || b.bullish - a.bullish).slice(0, 24);
  }, [disclosures]);

  const filteredTiles = useMemo(() => {
    if (filterMode === "all") return tiles;
    return tiles.filter((t) => t.bias === filterMode);
  }, [tiles, filterMode]);

  if (tiles.length === 0) return null;

  return (
    <section className="relative overflow-hidden rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-6 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)] text-black dark:text-white transition-colors">
      {/* Header */}
      <div className={`flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b-2 border-black/15 dark:border-white/10 pb-4 mb-5 ${isAr ? "sm:flex-row-reverse text-right" : ""}`}>
        <div className={`flex items-center gap-3 ${isAr ? "flex-row-reverse" : ""}`}>
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-none bg-[#FFE600] text-black border-2 border-black shadow-[2px_2px_0px_#000]">
            <Layers className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base sm:text-lg font-black tracking-tight text-black dark:text-white">
                {isAr ? "الخريطة الحرارية لإفصاحات السوق السعودي (تداول)" : "Saudi Tadawul Disclosures Heatmap"}
              </h3>
              <span className="hidden sm:inline-block px-2 py-0.5 border-2 border-black bg-[#FFE600] text-black text-[10px] font-black uppercase shadow-[1px_1px_0px_#000]">
                {isAr ? "مباشر" : "LIVE"}
              </span>
            </div>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-0.5 font-bold">
              {isAr
                ? "أكثر الشركات السعودية نشاطاً في الإفصاحات مصنفة حسب الأثر المالي (اضغط على أي شركة لعرض التفاصيل)"
                : "Most active Tadawul companies by disclosure count & AI sentiment impact (click any tile for details)"}
            </p>
          </div>
        </div>

        {/* Filter Toggle */}
        <div className={`flex flex-wrap items-center gap-1.5 self-start sm:self-auto ${isAr ? "flex-row-reverse" : ""}`}>
          <button
            type="button"
            onClick={() => setFilterMode("all")}
            className={`px-3 py-1.5 text-xs font-black transition-all border-2 border-black cursor-pointer ${
              filterMode === "all"
                ? "bg-black text-white dark:bg-white dark:text-black shadow-[2px_2px_0px_#000]"
                : "bg-white text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 hover:bg-[#FFE600] hover:text-black"
            }`}
          >
            {isAr ? "الكل" : "All"} ({tiles.length})
          </button>
          <button
            type="button"
            onClick={() => setFilterMode("bullish")}
            className={`px-3 py-1.5 text-xs font-black transition-all border-2 border-black flex items-center gap-1 cursor-pointer ${
              filterMode === "bullish"
                ? "bg-[#00FF66] text-black shadow-[2px_2px_0px_#000]"
                : "bg-white text-emerald-800 dark:bg-zinc-900 dark:text-emerald-400 hover:bg-emerald-50"
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>{isAr ? "إيجابي" : "Bullish"}</span>
          </button>
          <button
            type="button"
            onClick={() => setFilterMode("bearish")}
            className={`px-3 py-1.5 text-xs font-black transition-all border-2 border-black flex items-center gap-1 cursor-pointer ${
              filterMode === "bearish"
                ? "bg-[#FF3366] text-white shadow-[2px_2px_0px_#000]"
                : "bg-white text-rose-800 dark:bg-zinc-900 dark:text-rose-400 hover:bg-rose-50"
            }`}
          >
            <TrendingDown className="w-3.5 h-3.5" />
            <span>{isAr ? "سلبي" : "Bearish"}</span>
          </button>
          <button
            type="button"
            onClick={() => setFilterMode("neutral")}
            className={`px-3 py-1.5 text-xs font-black transition-all border-2 border-black flex items-center gap-1 cursor-pointer ${
              filterMode === "neutral"
                ? "bg-[#FFE600] text-black shadow-[2px_2px_0px_#000]"
                : "bg-white text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 hover:bg-zinc-100"
            }`}
          >
            <Minus className="w-3.5 h-3.5" />
            <span>{isAr ? "محايد" : "Neutral"}</span>
          </button>
        </div>
      </div>

      {/* Heatmap Grid */}
      {filteredTiles.length === 0 ? (
        <div className="py-8 text-center text-xs font-black text-zinc-500 dark:text-zinc-400">
          {isAr ? "لا توجد شركات مطابقة لهذا التصنيف في الدفعة الحالية" : "No companies match this sentiment filter"}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5">
          {filteredTiles.map((item) => {
            const isSelected = selectedSymbol === item.symbol;
            const bgTone =
              item.bias === "bullish"
                ? "bg-[#00FF66]/20 dark:bg-[#00FF66]/15 border-emerald-700 dark:border-[#00FF66]"
                : item.bias === "bearish"
                ? "bg-[#FF3366]/15 dark:bg-[#FF3366]/15 border-rose-700 dark:border-[#FF3366]"
                : "bg-zinc-100 dark:bg-zinc-900 border-black dark:border-white/40";

            return (
              <button
                key={item.symbol}
                type="button"
                onClick={() => onSelectSymbol?.(item.symbol)}
                className={`text-start p-3 border-2 transition-all cursor-pointer hover:-translate-y-0.5 hover:shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[3px_3px_0px_0px_rgba(255,255,255,0.4)] ${bgTone} ${
                  isSelected ? "ring-2 ring-[#FFE600]" : ""
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <StockLogo symbol={item.symbol} size="sm" />
                    <span className="font-mono text-xs font-black truncate">{item.symbol}</span>
                  </div>
                  <span className="px-1.5 py-0.5 text-[10px] font-black bg-black text-white dark:bg-white dark:text-black shrink-0">
                    {item.total}
                  </span>
                </div>

                <div className="text-[11px] font-bold text-zinc-700 dark:text-zinc-300 truncate mb-2">
                  {item.companyName}
                </div>

                <div className="flex items-center justify-between text-[10px] font-black">
                  <span className="text-emerald-700 dark:text-[#00FF66]">+{item.bullish}</span>
                  <span className="text-zinc-500 dark:text-zinc-400">{item.neutral}</span>
                  <span className="text-rose-700 dark:text-rose-400">-{item.bearish}</span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
