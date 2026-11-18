"use client";

import React, { useMemo, useState } from "react";
import { DisclosureItem } from "@/lib/disclosures-analytics";
import { BarChart3, TrendingUp, TrendingDown, ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import StockLogo from "@/components/StockLogo";

interface SaudiDisclosuresChartsProps {
  disclosures: DisclosureItem[];
  isAr: boolean;
  timeframeLabel?: string;
  onSelectSymbol?: (symbol: string) => void;
}

export default function SaudiDisclosuresCharts({
  disclosures,
  isAr,
  timeframeLabel,
  onSelectSymbol,
}: SaudiDisclosuresChartsProps) {
  const [showAll, setShowAll] = useState(false);

  const stats = useMemo(() => {
    let bullish = 0;
    let bearish = 0;
    let neutral = 0;

    let dividends = 0;
    let earnings = 0;
    let contracts = 0;
    let board = 0;

    const bySymbol = new Map<
      string,
      { symbol: string; companyName: string; total: number; bullish: number; bearish: number; neutral: number }
    >();

    for (const d of disclosures) {
      const isBull = d.sentiment === "bullish" || d.action_type === "buy";
      const isBear = d.sentiment === "bearish" || d.action_type === "sell";
      if (isBull) bullish += 1;
      else if (isBear) bearish += 1;
      else neutral += 1;

      const dtype = (d.disclosure_type || "").toLowerCase();
      const text = `${d.title || ""} ${d.ai_summary || ""} ${dtype}`.toLowerCase();
      if (dtype === "dividend" || /توزيع|أرباح نقدية|أسهم منحة|dividend/.test(text)) dividends += 1;
      else if (dtype === "earnings" || /نتائج|مالية|ربح|خسارة|إيرادات|earning|quarter|annual/.test(text)) earnings += 1;
      else if (/عقد|ترسية|مشروع|اتفاقية|مذكرة|تعاون|contract|award|agreement/.test(text)) contracts += 1;
      else if (dtype === "board_decision" || dtype === "board_resolution" || /مجلس|جمعية|رئيس|تنفيذي|board|assembly|ceo/.test(text)) {
        board += 1;
      }

      const sym = (d.symbol || "").trim().toUpperCase();
      if (!sym) continue;
      let row = bySymbol.get(sym);
      if (!row) {
        row = {
          symbol: sym,
          companyName: d.company_name || sym,
          total: 0,
          bullish: 0,
          bearish: 0,
          neutral: 0,
        };
        bySymbol.set(sym, row);
      }
      row.total += 1;
      if (isBull) row.bullish += 1;
      else if (isBear) row.bearish += 1;
      else row.neutral += 1;
    }

    const topSymbols = Array.from(bySymbol.values())
      .sort((a, b) => b.total - a.total || b.bullish - a.bullish)
      .slice(0, 12);

    const total = Math.max(disclosures.length, 1);
    return {
      total: disclosures.length,
      bullish,
      bearish,
      neutral,
      bullPct: Math.round((bullish / total) * 100),
      bearPct: Math.round((bearish / total) * 100),
      neutPct: Math.max(0, 100 - Math.round((bullish / total) * 100) - Math.round((bearish / total) * 100)),
      categories: [
        { key: "dividends", ar: "توزيعات أرباح ومنح", en: "Dividends & Distributions", count: dividends, color: "bg-[#00FF66]" },
        { key: "earnings", ar: "نتائج مالية وأرباح", en: "Financial Results", count: earnings, color: "bg-[#FFE600]" },
        { key: "contracts", ar: "عقود وترسيات ومشاريع", en: "Contracts & Projects", count: contracts, color: "bg-sky-400" },
        { key: "board", ar: "مجالس إدارة وجمعيات", en: "Board & Assemblies", count: board, color: "bg-zinc-400" },
      ],
      topSymbols,
    };
  }, [disclosures]);

  if (disclosures.length === 0) return null;

  const displayedSymbols = showAll ? stats.topSymbols : stats.topSymbols.slice(0, 6);
  const maxSymbolCount = Math.max(...stats.topSymbols.map((s) => s.total), 1);

  return (
    <div className="space-y-6 my-6">
      {/* SECTION 1: Top Active Saudi Companies Breakdown */}
      <div className="rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-6 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)] text-black dark:text-white transition-colors">
        <div className={`flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b-2 border-black/15 dark:border-white/10 pb-4 mb-5 ${isAr ? "sm:flex-row-reverse text-right" : ""}`}>
          <div className={`flex items-center gap-3 ${isAr ? "flex-row-reverse" : ""}`}>
            <div className="grid h-10 w-10 shrink-0 place-items-center bg-[#00FF66] text-black border-2 border-black shadow-[2px_2px_0px_#000]">
              <BarChart3 className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base sm:text-lg font-black tracking-tight">
                {isAr ? "توزيع نشاط الإفصاحات ومعنويات أبرز الشركات" : "Top Active Tadawul Companies & Sentiment Breakdown"}
              </h3>
              <p className="text-xs font-bold text-zinc-600 dark:text-zinc-400 mt-0.5">
                {timeframeLabel
                  ? `${isAr ? "النطاق:" : "Range:"} ${timeframeLabel} • ${isAr ? "اضغط على أي شركة لفتح ملف الإفصاحات" : "Click any company to inspect"}`
                  : isAr ? "اضغط على أي شركة لفتح سجل إفصاحاتها الكامل" : "Click any company to view full filing history"}
              </p>
            </div>
          </div>

          {stats.topSymbols.length > 6 && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-black border-2 border-black bg-[#FFE600] text-black shadow-[2px_2px_0px_#000] hover:bg-[#00FF66] cursor-pointer self-start sm:self-auto"
            >
              {showAll ? (
                <>
                  <ChevronUp className="w-3.5 h-3.5" />
                  <span>{isAr ? "عرض أقل" : "Show Less"}</span>
                </>
              ) : (
                <>
                  <ChevronDown className="w-3.5 h-3.5" />
                  <span>{isAr ? `عرض الكل (${stats.topSymbols.length})` : `Show All (${stats.topSymbols.length})`}</span>
                </>
              )}
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {displayedSymbols.map((item) => {
            const bullW = (item.bullish / item.total) * 100;
            const bearW = (item.bearish / item.total) * 100;
            const neutW = Math.max(0, 100 - bullW - bearW);
            const relWidth = Math.max(20, Math.round((item.total / maxSymbolCount) * 100));

            return (
              <button
                key={item.symbol}
                type="button"
                onClick={() => onSelectSymbol?.(item.symbol)}
                className="text-start p-3.5 border-2 border-black dark:border-white/40 bg-zinc-50 dark:bg-zinc-900 hover:bg-[#FFE600]/20 dark:hover:bg-zinc-800 transition-colors cursor-pointer"
              >
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <StockLogo symbol={item.symbol} size="sm" />
                    <div className="min-w-0">
                      <div className="font-mono text-xs font-black">{item.symbol}</div>
                      <div className="text-[11px] font-bold text-zinc-600 dark:text-zinc-400 truncate">{item.companyName}</div>
                    </div>
                  </div>
                  <span className="px-2 py-0.5 text-[11px] font-black bg-black text-white dark:bg-white dark:text-black shrink-0">
                    {item.total} {isAr ? "إفصاح" : "filings"}
                  </span>
                </div>

                {/* Progress Bar */}
                <div className="w-full h-3 bg-zinc-200 dark:bg-zinc-800 border border-black overflow-hidden flex" style={{ width: `${relWidth}%` }}>
                  {bullW > 0 && <div className="bg-[#00FF66] h-full" style={{ width: `${bullW}%` }} />}
                  {neutW > 0 && <div className="bg-[#FFE600] h-full" style={{ width: `${neutW}%` }} />}
                  {bearW > 0 && <div className="bg-[#FF3366] h-full" style={{ width: `${bearW}%` }} />}
                </div>

                <div className="flex items-center justify-between text-[10px] font-black mt-2">
                  <span className="text-emerald-700 dark:text-[#00FF66] flex items-center gap-0.5">
                    <TrendingUp className="w-3 h-3" /> {item.bullish} {isAr ? "إيجابي" : "Bull"}
                  </span>
                  <span className="text-zinc-500 dark:text-zinc-400">{item.neutral} {isAr ? "محايد" : "Neut"}</span>
                  <span className="text-rose-700 dark:text-rose-400 flex items-center gap-0.5">
                    <TrendingDown className="w-3 h-3" /> {item.bearish} {isAr ? "سلبي" : "Bear"}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* SECTION 2: Overall Sentiment Ratio & Category Breakdown */}
      <div className="rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-6 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)] text-black dark:text-white">
        <div className={`flex items-center gap-2 mb-4 ${isAr ? "flex-row-reverse text-right" : ""}`}>
          <Sparkles className="w-4 h-4 text-amber-500" />
          <h3 className="text-sm sm:text-base font-black">
            {isAr ? "مؤشر المعنويات العام وتصنيفات إفصاحات السوق السعودي" : "Tadawul Sentiment Ratio & Filing Categories"}
          </h3>
        </div>

        {/* Sentiment Stacked Bar */}
        <div className="mb-5">
          <div className="flex items-center justify-between text-xs font-black mb-1.5">
            <span className="text-emerald-700 dark:text-[#00FF66]">
              {isAr ? `إيجابي ${stats.bullPct}% (${stats.bullish})` : `Bullish ${stats.bullPct}% (${stats.bullish})`}
            </span>
            <span className="text-zinc-600 dark:text-zinc-300">
              {isAr ? `محايد ${stats.neutPct}% (${stats.neutral})` : `Neutral ${stats.neutPct}% (${stats.neutral})`}
            </span>
            <span className="text-rose-700 dark:text-rose-400">
              {isAr ? `سلبي ${stats.bearPct}% (${stats.bearish})` : `Bearish ${stats.bearPct}% (${stats.bearish})`}
            </span>
          </div>
          <div className="w-full h-5 border-2 border-black dark:border-white flex overflow-hidden bg-zinc-200 dark:bg-zinc-800">
            {stats.bullPct > 0 && <div className="bg-[#00FF66] h-full" style={{ width: `${stats.bullPct}%` }} />}
            {stats.neutPct > 0 && <div className="bg-[#FFE600] h-full" style={{ width: `${stats.neutPct}%` }} />}
            {stats.bearPct > 0 && <div className="bg-[#FF3366] h-full" style={{ width: `${stats.bearPct}%` }} />}
          </div>
        </div>

        {/* Category Pills */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {stats.categories.map((cat) => (
            <div key={cat.key} className="p-3 border-2 border-black dark:border-white/30 bg-zinc-50 dark:bg-zinc-900">
              <div className="flex items-center gap-2 mb-1">
                <span className={`w-2.5 h-2.5 border border-black ${cat.color}`} />
                <span className="text-[11px] font-black truncate">{isAr ? cat.ar : cat.en}</span>
              </div>
              <div className="text-xl font-black font-mono">{cat.count}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
