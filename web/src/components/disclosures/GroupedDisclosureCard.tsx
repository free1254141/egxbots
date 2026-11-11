"use client";

import React, { useState } from "react";
import {
  FileText,
  Download,
  Bot,
  ExternalLink,
  Calendar,
  Users,
  Target,
  Sparkles,
  ZoomIn,
  Layers,
  Scale,
} from "lucide-react";
import StockLogo from "@/components/StockLogo";
import type {
  GroupedStockDisclosure,
  DisclosureItem,
  InsiderMetric,
} from "@/lib/disclosures-analytics";

interface GroupedDisclosureCardProps {
  group: GroupedStockDisclosure;
  metric?: InsiderMetric | null;
  layoutMode: "grid" | "list";
  isAr: boolean;
  onSelectSymbol: (symbol: string) => void;
  onInspectShareholders: (symbol: string) => void;
  onDiscussInFloatingChat: (item: DisclosureItem) => void;
  onPreviewPdf: (item: DisclosureItem) => void;
}

export default function GroupedDisclosureCard({
  group,
  metric,
  layoutMode,
  isAr,
  onSelectSymbol,
  onInspectShareholders,
  onDiscussInFloatingChat,
  onPreviewPdf,
}: GroupedDisclosureCardProps) {
  const [activeIdx, setActiveIdx] = useState<number>(0);

  const activeItem = group.items[activeIdx] || group.items[0];
  const shortCode = activeItem ? activeItem.id.slice(0, 8).toUpperCase() : "";

  const getTypeLabel = (type: string) => {
    switch (type) {
      case "insider_trading":
        return isAr ? "تعاملات مطلعين وداخليين" : "Insider Trading";
      case "major_shareholders":
        return isAr ? "هيكل مساهمين (مادة 30)" : "Shareholding Structure";
      case "board_resolution":
        return isAr ? "قرارات مجلس إدارة" : "Board Resolution";
      case "material_event":
        return isAr ? "أحداث جوهرية" : "Material Event";
      default:
        return isAr ? "إفصاح رسمي" : "Official Disclosure";
    }
  };

  const getItemSentimentBadge = (item: DisclosureItem) => {
    if (item.action_type === "buy" || item.sentiment === "bullish") {
      return (
        <span className="px-2 py-0.5 text-[10px] font-black bg-[#00FF66] text-black border border-black shadow-[1px_1px_0px_#000]">
          {item.action_type === "buy"
            ? isAr ? "شراء داخلي" : "Buy"
            : isAr ? "إيجابي" : "Bullish"}
        </span>
      );
    }
    if (item.action_type === "sell" || item.sentiment === "bearish") {
      return (
        <span className="px-2 py-0.5 text-[10px] font-black bg-[#FF3366] text-white border border-black shadow-[1px_1px_0px_#000]">
          {item.action_type === "sell"
            ? isAr ? "بيع داخلي" : "Sell"
            : isAr ? "سلبي" : "Bearish"}
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 text-[10px] font-black bg-[#FFE600] text-black border border-black shadow-[1px_1px_0px_#000]">
        {isAr ? "محايد" : "Neutral"}
      </span>
    );
  };

  const getGroupSentimentBadge = () => {
    if (group.overall_sentiment === "mixed") {
      return (
        <span className="px-2.5 py-1 text-xs font-black bg-[#FFE600] text-black border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
          {isAr ? group.sentiment_badge_ar : group.sentiment_badge_en}
        </span>
      );
    }
    if (group.overall_sentiment === "bullish") {
      return (
        <span className="px-2.5 py-1 text-xs font-black bg-[#00FF66] text-black border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
          {isAr ? group.sentiment_badge_ar : group.sentiment_badge_en}
        </span>
      );
    }
    if (group.overall_sentiment === "bearish") {
      return (
        <span className="px-2.5 py-1 text-xs font-black bg-[#FF3366] text-white border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
          {isAr ? group.sentiment_badge_ar : group.sentiment_badge_en}
        </span>
      );
    }
    return (
      <span className="px-2.5 py-1 text-xs font-black bg-zinc-200 dark:bg-zinc-800 text-black dark:text-white border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
        {isAr ? group.sentiment_badge_ar : group.sentiment_badge_en}
      </span>
    );
  };

  // ------------------ GRID LAYOUT ------------------
  if (layoutMode === "grid") {
    return (
      <article className="flex flex-col justify-between p-4 rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-900 shadow-[5px_5px_0px_0px_rgba(0,0,0,1)] dark:shadow-[5px_5px_0px_0px_rgba(255,255,255,0.4)] transition-all">
        <div className="flex flex-col gap-3">
          {/* Top Header */}
          <div className="flex items-center justify-between gap-2 pb-2.5 border-b-2 border-black/15 dark:border-white/15">
            <div className="flex items-center gap-2">
              <StockLogo
                symbol={group.symbol || "EGX"}
                size="sm"
                className="border-2 border-black dark:border-white rounded-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
              />
              {group.symbol ? (
                <button
                  type="button"
                  onClick={() => onSelectSymbol(group.symbol!)}
                  className="px-2 py-0.5 text-xs font-black uppercase tracking-wider bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white hover:bg-[#FFE600] hover:text-black transition-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] cursor-pointer"
                  title={isAr ? "تحليل شامل لهذا السهم" : "Stock Deep-Dive"}
                >
                  {group.symbol}
                </button>
              ) : (
                <span className="px-2 py-0.5 text-xs font-black uppercase bg-zinc-200 dark:bg-zinc-800 text-black dark:text-white border-2 border-black">
                  EGX
                </span>
              )}
              {group.items.length > 1 ? (
                <span className="px-1.5 py-0.5 bg-[#FFE600] text-black border border-black font-black text-[10px] shadow-[1px_1px_0px_#000]">
                  {group.items.length} {isAr ? "إفصاحات" : "filings"}
                </span>
              ) : (
                <span className="text-xs font-mono font-black text-zinc-500 dark:text-zinc-400">
                  #{shortCode}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              {getGroupSentimentBadge()}
            </div>
          </div>

          {/* Company Name & Latest Date */}
          <div className="flex items-center justify-between text-xs font-bold text-zinc-600 dark:text-zinc-400">
            <button
              type="button"
              onClick={() => group.symbol && onSelectSymbol(group.symbol)}
              className="font-black text-black dark:text-white truncate max-w-[180px] text-right hover:text-amber-500 transition-colors cursor-pointer"
              title={group.company_name}
            >
              {group.company_name}
            </button>
            <span className="flex items-center gap-1 shrink-0 text-[11px] font-black">
              <Calendar className="w-3 h-3" />
              {group.latest_date}
            </span>
          </div>

          {/* Net Insider Trade Status Strip (Daily Netting: "بيع الغى شراء") */}
          {group.has_insider_trades && group.trade_summary.status !== "none" && (
            <div
              className={`p-2 border-2 border-black text-[11px] font-black flex items-center justify-between gap-1 shadow-[2px_2px_0px_#000] ${
                group.trade_summary.status === "offset"
                  ? "bg-amber-100 dark:bg-amber-950/60 text-amber-950 dark:text-amber-200 border-amber-600"
                  : group.trade_summary.status === "net_accumulation"
                  ? "bg-emerald-100 dark:bg-emerald-950/60 text-emerald-950 dark:text-emerald-200 border-emerald-600"
                  : "bg-rose-100 dark:bg-rose-950/60 text-rose-950 dark:text-rose-200 border-rose-600"
              }`}
            >
              <div className="flex items-center gap-1.5 truncate">
                <Scale className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{group.trade_summary.message_ar}</span>
              </div>
              <span className="px-1.5 py-0.2 shrink-0 text-[9px] font-black border border-black bg-white dark:bg-zinc-900 text-black dark:text-white">
                {group.trade_summary.status === "offset"
                  ? isAr ? "تعادل كامل" : "Offset"
                  : group.trade_summary.status === "net_accumulation"
                  ? isAr ? "صافي شراء" : "Net Buy"
                  : isAr ? "صافي بيع" : "Net Sell"}
              </span>
            </div>
          )}

          {/* Multiple Filings Tabs (Unified Card Switcher) */}
          {group.items.length > 1 && (
            <div className="flex flex-col gap-1.5 p-2 bg-zinc-100 dark:bg-zinc-800/60 border-2 border-black dark:border-white">
              <div className="flex items-center justify-between text-[10px] font-black text-zinc-600 dark:text-zinc-300">
                <span className="flex items-center gap-1">
                  <Layers className="w-3 h-3 text-amber-500" />
                  {isAr ? "إفصاحات السهم خلال الفترة:" : "Filings in period:"}
                </span>
                <span>{activeIdx + 1} من {group.items.length}</span>
              </div>
              <div className="flex flex-wrap gap-1">
                {group.items.map((it, idx) => {
                  const isActive = idx === activeIdx;
                  return (
                    <button
                      key={it.id}
                      type="button"
                      onClick={() => setActiveIdx(idx)}
                      className={`flex-1 min-w-[120px] px-2 py-1 text-[10px] font-black border border-black flex items-center justify-between gap-1 transition-none cursor-pointer ${
                        isActive
                          ? "bg-black text-white dark:bg-white dark:text-black shadow-[1px_1px_0px_#FFE600]"
                          : "bg-white text-black dark:bg-zinc-900 dark:text-white hover:bg-[#FFE600] hover:text-black"
                      }`}
                    >
                      <span className="truncate text-right">
                        {isAr ? `إفصاح #${idx + 1}` : `Filing #${idx + 1}`}
                      </span>
                      {getItemSentimentBadge(it)}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Active Item Title & Type */}
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <span className="inline-block px-2 py-0.5 text-[10px] font-black bg-zinc-100 dark:bg-zinc-800 text-black dark:text-white border border-black dark:border-white">
                {getTypeLabel(activeItem.disclosure_type)}
              </span>
              {group.symbol && (
                <button
                  type="button"
                  onClick={() => onSelectSymbol(group.symbol!)}
                  className="text-[10px] font-black text-emerald-700 dark:text-[#00FF66] hover:text-black dark:hover:text-[#FFE600] underline flex items-center gap-1 cursor-pointer"
                >
                  <Target className="w-3 h-3" />
                  <span>{isAr ? "تحليل شامل بالسهم 🔍" : "Deep-Dive 🔍"}</span>
                </button>
              )}
            </div>

            <h2 className="text-sm font-black text-black dark:text-white line-clamp-2 leading-snug">
              {activeItem.title}
            </h2>
          </div>

          {/* Insider Cost (VWAP) & Discount Badge */}
          {metric && metric.insider_vwap > 0 && (
            <div className="p-2.5 rounded-none border-2 border-black dark:border-white bg-[#FFE600]/20 dark:bg-[#FFE600]/10 flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5">
                <Target className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                <div>
                  <span className="text-[10px] text-zinc-500 dark:text-zinc-400 block">
                    {isAr ? "متوسط تكلفة الداخلي:" : "Insider VWAP:"}
                  </span>
                  <span className="font-mono font-black text-black dark:text-white">
                    {metric.insider_vwap.toFixed(2)} ج.م
                  </span>
                </div>
              </div>

              <div className="text-right">
                {metric.discount_pct < -1.0 && metric.net_shares > 0 ? (
                  <span className="px-2 py-0.5 rounded border border-emerald-500 bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 font-black text-[10px]">
                    {isAr ? `خصم -${Math.abs(metric.discount_pct)}% 🟢` : `-${Math.abs(metric.discount_pct)}% Discount`}
                  </span>
                ) : (
                  <span className="text-[10px] font-mono text-zinc-600 dark:text-zinc-400">
                    {isAr ? `سعر اليوم: ${metric.current_price.toFixed(2)} ج` : `${metric.current_price.toFixed(2)} EGP`}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Quant chips if present on active filing */}
          {(activeItem.party_name || activeItem.shares_count || activeItem.stake_before != null || activeItem.stake_after != null) && (
            <div className="flex flex-wrap items-center gap-1.5 p-2 bg-zinc-50 dark:bg-zinc-950 border border-black dark:border-zinc-700 text-[11px] font-bold text-black dark:text-white">
              {activeItem.party_name && (
                <span className="truncate max-w-full">
                  {isAr ? "الطرف: " : "Party: "}
                  <strong className="font-black">{activeItem.party_name}</strong>
                </span>
              )}
              {activeItem.shares_count != null && (
                <span className="px-1.5 py-0.5 bg-[#FFE600] text-black font-black text-[10px] border border-black">
                  {Number(activeItem.shares_count).toLocaleString()} {isAr ? "سهم" : "sh"}
                </span>
              )}
              {(activeItem.stake_before != null || activeItem.stake_after != null) && (
                <span className="font-black text-[10px]">
                  {activeItem.stake_before ?? "—"}% → {activeItem.stake_after ?? "—"}%
                </span>
              )}
            </div>
          )}

          {/* AI Analysis Box */}
          <div className="p-2.5 bg-yellow-50 dark:bg-yellow-950/25 border-2 border-dashed border-yellow-600 dark:border-yellow-500/60">
            <div className="flex items-center gap-1.5 mb-1">
              <Sparkles className="w-3.5 h-3.5 text-yellow-600 dark:text-yellow-400 shrink-0" />
              <span className="text-[10px] font-black uppercase text-yellow-800 dark:text-yellow-400">
                {isAr ? "تحليل الذكاء الاصطناعي:" : "AI Analysis:"}
              </span>
            </div>
            <p className="text-xs font-bold text-zinc-800 dark:text-zinc-200 line-clamp-3 leading-relaxed">
              {activeItem.ai_summary}
            </p>
          </div>

          {/* Authentic PDF Viewer inside Grid Card */}
          <div className="border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-950 overflow-hidden shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
            <div className="flex items-center justify-between px-2 py-1 bg-black text-white text-[10px] font-black">
              <span className="flex items-center gap-1 text-[#FFE600]">
                <FileText className="w-3 h-3" />
                {isAr ? "مستند الـ PDF الأصلي" : "Official PDF Document"}
              </span>
              <button
                type="button"
                onClick={() => onPreviewPdf(activeItem)}
                className="text-black bg-[#FFE600] px-1.5 py-0.2 hover:bg-white flex items-center gap-0.5 font-black text-[9px] cursor-pointer"
              >
                <ZoomIn className="w-2.5 h-2.5" />
                {isAr ? "تكبير" : "Full View"}
              </button>
            </div>
            <iframe
              src={`/api/disclosures/pdf/${activeItem.id}#view=FitH&toolbar=0&navpanes=0`}
              title={activeItem.title}
              loading="lazy"
              className="w-full h-[220px] border-0 bg-white"
            />
          </div>
        </div>

        {/* Bottom Actions */}
        <div className="flex items-center justify-between gap-2 pt-3 mt-3 border-t-2 border-black/15 dark:border-white/15 text-xs">
          <button
            type="button"
            onClick={() => onDiscussInFloatingChat(activeItem)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#00FF66] text-black border-2 border-black font-black text-[11px] shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:bg-[#FFE600] cursor-pointer"
          >
            <Bot className="w-3.5 h-3.5" />
            <span>{isAr ? "ناقش في الشات" : "Discuss"}</span>
          </button>

          {activeItem.source_url && (
            <a
              href={activeItem.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[11px] font-black text-zinc-600 dark:text-zinc-400 hover:text-black dark:hover:text-white"
            >
              <ExternalLink className="w-3 h-3" />
              <span>{isAr ? "المصدر" : "Source"}</span>
            </a>
          )}
        </div>
      </article>
    );
  }

  // ------------------ LIST LAYOUT (HORIZONTAL) ------------------
  return (
    <article className="p-5 border-4 border-black dark:border-white bg-white dark:bg-zinc-900 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.4)] transition-all">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Column 1: Info & AI Summary (7 cols) */}
        <div className="lg:col-span-7 flex flex-col justify-between space-y-3">
          <div>
            {/* Header row */}
            <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b-2 border-black/15 dark:border-white/15 mb-2">
              <div className="flex items-center gap-2">
                <StockLogo
                  symbol={group.symbol || "EGX"}
                  size="sm"
                  className="border-2 border-black dark:border-white rounded-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
                />
                {group.symbol ? (
                  <button
                    type="button"
                    onClick={() => onSelectSymbol(group.symbol!)}
                    className="px-2.5 py-0.5 text-xs font-black uppercase tracking-wider bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white hover:bg-[#FFE600] hover:text-black transition-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] cursor-pointer"
                    title={isAr ? "اضغط لفتح بطاقة التحليل الشامل للسهم" : "Click to open stock deep-dive"}
                  >
                    {group.symbol}
                  </button>
                ) : (
                  <span className="px-2.5 py-0.5 text-xs font-black uppercase bg-zinc-200 dark:bg-zinc-800 text-black dark:text-white border-2 border-black">
                    EGX
                  </span>
                )}
                <span className="font-black text-black dark:text-white text-xs">
                  {group.company_name}
                </span>
                {group.items.length > 1 ? (
                  <span className="px-2 py-0.5 bg-[#FFE600] text-black border border-black font-black text-xs shadow-[1px_1px_0px_#000]">
                    {group.items.length} {isAr ? "إفصاحات مجمعة" : "filings"}
                  </span>
                ) : (
                  <span className="text-xs font-mono font-bold text-zinc-500">
                    #{shortCode}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-black text-zinc-500 flex items-center gap-1">
                  <Calendar className="w-3.5 h-3.5" />
                  {group.latest_date}
                </span>
                {getGroupSentimentBadge()}
              </div>
            </div>

            {/* Net Insider Trade Status Strip (Daily Netting: "بيع الغى شراء") */}
            {group.has_insider_trades && group.trade_summary.status !== "none" && (
              <div
                className={`p-2.5 mb-2.5 border-2 border-black text-xs font-black flex items-center justify-between gap-2 shadow-[2px_2px_0px_#000] ${
                  group.trade_summary.status === "offset"
                    ? "bg-amber-100 dark:bg-amber-950/60 text-amber-950 dark:text-amber-200 border-amber-600"
                    : group.trade_summary.status === "net_accumulation"
                    ? "bg-emerald-100 dark:bg-emerald-950/60 text-emerald-950 dark:text-emerald-200 border-emerald-600"
                    : "bg-rose-100 dark:bg-rose-950/60 text-rose-950 dark:text-rose-200 border-rose-600"
                }`}
              >
                <div className="flex items-center gap-2">
                  <Scale className="w-4 h-4 shrink-0" />
                  <span>{group.trade_summary.message_ar}</span>
                </div>
                <span className="px-2 py-0.5 text-[10px] font-black border border-black bg-white dark:bg-zinc-900 text-black dark:text-white shrink-0">
                  {group.trade_summary.status === "offset"
                    ? isAr ? "تعادل كامل (الصافي = 0)" : "Offset (Net = 0)"
                    : group.trade_summary.status === "net_accumulation"
                    ? isAr ? "صافي شراء إيجابي" : "Net Accumulation"
                    : isAr ? "صافي تخارج وتسييل" : "Net Distribution"}
                </span>
              </div>
            )}

            {/* Multiple Filings Tabs (Unified Card Switcher) */}
            {group.items.length > 1 && (
              <div className="mb-3 p-2 bg-zinc-100 dark:bg-zinc-800/60 border-2 border-black dark:border-white">
                <div className="flex items-center justify-between text-xs font-black text-zinc-600 dark:text-zinc-300 mb-1.5">
                  <span className="flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-amber-500" />
                    {isAr ? "تنقل بين إفصاحات السهم خلال هذه الفترة:" : "Navigate filings for this stock:"}
                  </span>
                  <span>{activeIdx + 1} من {group.items.length}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {group.items.map((it, idx) => {
                    const isActive = idx === activeIdx;
                    return (
                      <button
                        key={it.id}
                        type="button"
                        onClick={() => setActiveIdx(idx)}
                        className={`flex-1 min-w-[150px] px-3 py-1.5 text-xs font-black border-2 border-black flex items-center justify-between gap-1.5 transition-none cursor-pointer ${
                          isActive
                            ? "bg-black text-white dark:bg-white dark:text-black shadow-[2px_2px_0px_#FFE600]"
                            : "bg-white text-black dark:bg-zinc-900 dark:text-white hover:bg-[#FFE600] hover:text-black"
                        }`}
                      >
                        <span className="truncate text-right">
                          {isAr ? `إفصاح #${idx + 1}: ${it.title.slice(0, 26)}...` : `Filing #${idx + 1}`}
                        </span>
                        {getItemSentimentBadge(it)}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Title */}
            <h2 className="text-base font-black text-black dark:text-white leading-snug mb-2">
              {activeItem.title}
            </h2>

            {/* Insider Cost and VWAP bar */}
            {metric && metric.insider_vwap > 0 && (
              <div className="p-3 mb-2 border-2 border-black dark:border-white bg-[#FFE600]/20 dark:bg-[#FFE600]/10 flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2">
                  <Target className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                  <span className="font-bold text-zinc-700 dark:text-zinc-300">
                    {isAr ? "متوسط تكلفة شراء الداخليين:" : "Insider VWAP Cost:"}
                  </span>
                  <span className="font-mono font-black text-sm text-black dark:text-white">
                    {metric.insider_vwap.toFixed(2)} ج.م
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  {metric.discount_pct < -1.0 && metric.net_shares > 0 ? (
                    <span className="px-2.5 py-0.5 rounded border border-emerald-500 bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 font-black text-xs">
                      {isAr ? `فرصة: يتداول بأقل من التكلفة بـ -${Math.abs(metric.discount_pct)}% 🟢` : `-${Math.abs(metric.discount_pct)}% Discount`}
                    </span>
                  ) : (
                    <span className="text-xs font-mono text-zinc-600 dark:text-zinc-400">
                      {isAr ? `السعر الحالي: ${metric.current_price.toFixed(2)} ج.م` : `Price: ${metric.current_price.toFixed(2)} EGP`}
                    </span>
                  )}

                  <span className="text-[11px] font-bold text-zinc-500">
                    ({metric.buy_count} {isAr ? "عمليات تجميع" : "buys"})
                  </span>
                </div>
              </div>
            )}

            {/* Quant details */}
            {(activeItem.party_name || activeItem.shares_count || activeItem.stake_before != null || activeItem.stake_after != null) && (
              <div className="flex flex-wrap items-center gap-2 p-2.5 mb-2 bg-zinc-100 dark:bg-zinc-950 border-2 border-black dark:border-zinc-700 text-xs font-bold text-black dark:text-white">
                {activeItem.party_name && (
                  <span>
                    {isAr ? "الطرف: " : "Party: "}
                    <strong className="font-black text-emerald-700 dark:text-emerald-400">
                      {activeItem.party_name}
                    </strong>
                  </span>
                )}
                {activeItem.shares_count != null && (
                  <span className="px-2 py-0.5 bg-[#FFE600] text-black font-black text-xs border border-black">
                    {isAr ? "الكمية:" : "Shares:"} {Number(activeItem.shares_count).toLocaleString()} {isAr ? "سهم" : "sh"}
                  </span>
                )}
                {(activeItem.stake_before != null || activeItem.stake_after != null) && (
                  <span className="font-black text-xs">
                    {isAr ? "نسبة المساهمة:" : "Stake:"} {activeItem.stake_before ?? "—"}% → {activeItem.stake_after ?? "—"}%
                  </span>
                )}
              </div>
            )}

            {/* AI Analysis */}
            <div className="p-3 bg-yellow-50 dark:bg-yellow-950/25 border-2 border-dashed border-yellow-600 dark:border-yellow-500/60">
              <div className="flex items-center gap-1.5 mb-1">
                <Sparkles className="w-4 h-4 text-yellow-600 dark:text-yellow-400 shrink-0" />
                <span className="text-xs font-black uppercase text-yellow-800 dark:text-yellow-400">
                  {isAr ? "تحليل الذكاء الاصطناعي والأثر المالي:" : "AI Financial Analysis & Impact:"}
                </span>
              </div>
              <p className="text-xs font-bold text-zinc-800 dark:text-zinc-200 leading-relaxed">
                {activeItem.ai_summary}
              </p>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center gap-2 pt-3 border-t-2 border-black/15 dark:border-white/15">
            <button
              type="button"
              onClick={() => onDiscussInFloatingChat(activeItem)}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-[#00FF66] text-black border-2 border-black font-black text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:bg-[#FFE600] cursor-pointer"
            >
              <Bot className="w-4 h-4" />
              <span>{isAr ? "ناقش هذا الإفصاح في الشات" : "Discuss in Chat"}</span>
            </button>

            {group.symbol && (
              <button
                type="button"
                onClick={() => onInspectShareholders(group.symbol!)}
                className="inline-flex items-center gap-1 px-3 py-2 bg-zinc-100 dark:bg-zinc-800 text-black dark:text-white border-2 border-black dark:border-white font-black text-xs hover:bg-[#FFE600] hover:text-black transition-all cursor-pointer"
              >
                <Users className="w-3.5 h-3.5" />
                <span>{isAr ? "فحص هيكل المساهمين" : "Shareholders Registry"}</span>
              </button>
            )}

            {group.symbol && (
              <button
                type="button"
                onClick={() => onSelectSymbol(group.symbol!)}
                className="inline-flex items-center gap-1.5 px-3 py-2 bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white font-black text-xs hover:bg-[#FFE600] hover:text-black transition-all cursor-pointer shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
              >
                <Target className="w-3.5 h-3.5" />
                <span>{isAr ? `تحليل شامل لسهم ${group.symbol} 🔍` : `Deep-Dive ${group.symbol} 🔍`}</span>
              </button>
            )}

            {activeItem.source_url && (
              <a
                href={activeItem.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs font-black text-zinc-600 dark:text-zinc-400 hover:text-black dark:hover:text-white ms-auto"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>{isAr ? "المصدر الأصلي" : "Original Source"}</span>
              </a>
            )}
          </div>
        </div>

        {/* Column 2: Authentic PDF Viewer (5 cols) */}
        <div className="lg:col-span-5 flex flex-col justify-between border-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-950 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 bg-black text-white text-xs font-black border-b-2 border-black">
            <span className="flex items-center gap-1.5 text-[#FFE600]">
              <FileText className="w-4 h-4" />
              {isAr ? "مستند الإفصاح الرسمي (PDF معتمد)" : "Official Disclosure Document (PDF)"}
            </span>
            <button
              type="button"
              onClick={() => onPreviewPdf(activeItem)}
              className="text-black bg-[#FFE600] px-2 py-0.5 hover:bg-white flex items-center gap-1 font-black text-[10px] cursor-pointer"
            >
              <ZoomIn className="w-3 h-3" />
              {isAr ? "تكبير" : "Full View"}
            </button>
          </div>

          <iframe
            src={`/api/disclosures/pdf/${activeItem.id}#view=FitH&toolbar=0&navpanes=0`}
            title={activeItem.title}
            loading="lazy"
            className="w-full h-[360px] border-0 bg-white"
          />

          <div className="p-2 bg-zinc-50 dark:bg-zinc-900 border-t-2 border-black dark:border-white flex items-center justify-between gap-2 text-xs">
            <span className="text-[11px] font-black text-zinc-700 dark:text-zinc-300 truncate">
              {isAr ? "ملف الإفصاح الأصلي - البورصة المصرية" : "Authentic EGX Filing Document"}
            </span>
            <div className="flex items-center gap-1.5 shrink-0">
              <a
                href={`/api/disclosures/pdf/${activeItem.id}`}
                download={`egx_disclosure_${activeItem.symbol || 'official'}.pdf`}
                className="px-2 py-1 bg-white dark:bg-zinc-800 text-black dark:text-white border border-black dark:border-white font-black text-[10px] hover:bg-[#FFE600] hover:text-black transition-all flex items-center gap-1"
              >
                <Download className="w-3 h-3" />
                {isAr ? "تحميل PDF" : "Download"}
              </a>
              <button
                type="button"
                onClick={() => onPreviewPdf(activeItem)}
                className="px-2 py-1 bg-[#00FF66] text-black border border-black font-black text-[10px] hover:bg-[#FFE600] transition-all flex items-center gap-1 cursor-pointer"
              >
                <ZoomIn className="w-3 h-3" />
                {isAr ? "عرض كامل" : "Full View"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}
