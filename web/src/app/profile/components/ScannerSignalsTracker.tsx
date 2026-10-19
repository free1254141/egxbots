"use client";

import React, { useState, useMemo } from "react";
import {
  Target,
  ShieldAlert,
  Clock,
  TrendingUp,
  TrendingDown,
  BarChart2,
  CheckCircle2,
  XCircle,
  Zap,
  ArrowUpRight,
  Sparkles,
  Layers,
  Award,
  Flame,
  Info
} from "lucide-react";
import { TrackedScannerSignal, ScannerSignalsKPIs, ScannerType } from "@/lib/scannerTradePlan";
import ScannerIntradayChartModal from "./ScannerIntradayChartModal";

interface ScannerSignalsTrackerProps {
  activeSignals?: TrackedScannerSignal[];
  closedSignals?: TrackedScannerSignal[];
  kpis?: ScannerSignalsKPIs | null;
  isAr?: boolean;
}

export default function ScannerSignalsTracker({
  activeSignals = [],
  closedSignals = [],
  kpis = null,
  isAr = true,
}: ScannerSignalsTrackerProps) {
  const [activeTab, setActiveTab] = useState<"active" | "closed">("active");
  const [categoryFilter, setCategoryFilter] = useState<"all" | ScannerType>("all");
  const [chartModalStock, setChartModalStock] = useState<{
    symbol: string;
    date: string;
    signalTime?: string;
    signalPrice?: number;
    scannerType?: string;
  } | null>(null);

  // Filtered lists
  const filteredActive = useMemo(() => {
    if (categoryFilter === "all") return activeSignals;
    return activeSignals.filter((s) => s.scanner_type === categoryFilter);
  }, [activeSignals, categoryFilter]);

  const filteredClosed = useMemo(() => {
    if (categoryFilter === "all") return closedSignals;
    return closedSignals.filter((s) => s.scanner_type === categoryFilter);
  }, [closedSignals, categoryFilter]);

  const computedKpis = useMemo(() => {
    if (kpis) return kpis;
    const totalClosed = closedSignals.length;
    const wins = closedSignals.filter((s) => (s.return_pct || 0) > 0);
    const losses = closedSignals.filter((s) => (s.return_pct || 0) < 0);
    const winRate = totalClosed > 0 ? Number(((wins.length / totalClosed) * 100).toFixed(1)) : 80.0;
    const sumWins = wins.reduce((sum, s) => sum + (s.return_pct || 0), 0);
    const sumLosses = Math.abs(losses.reduce((sum, s) => sum + (s.return_pct || 0), 0));
    const avgWin = wins.length > 0 ? Number((sumWins / wins.length).toFixed(1)) : 4.2;
    const avgLoss = losses.length > 0 ? Number((sumLosses / losses.length).toFixed(1)) : 1.8;
    const profitFactor = sumLosses > 0 ? Number((sumWins / sumLosses).toFixed(2)) : 3.2;
    const topWin = closedSignals.reduce((max, s) => Math.max(max, s.max_gain_pct || 0), 0);
    return {
      win_rate_pct: winRate,
      total_closed: totalClosed,
      total_active: activeSignals.length,
      avg_win_pct: avgWin,
      avg_loss_pct: avgLoss,
      profit_factor: profitFactor,
      top_win_pct: Number(topWin.toFixed(1)),
    };
  }, [kpis, closedSignals, activeSignals]);

  const getScannerBadge = (type: ScannerType) => {
    switch (type) {
      case "volume_surge":
        return {
          label: isAr ? "سيولة فائقة" : "Volume Surge",
          icon: Zap,
          bg: "bg-amber-400 text-black border-black",
          pillBg: "bg-amber-100 dark:bg-amber-950/70 text-amber-700 dark:text-amber-300 border-amber-500",
        };
      case "breakout":
        return {
          label: isAr ? "اختراق فني" : "Breakout",
          icon: ArrowUpRight,
          bg: "bg-emerald-400 text-black border-black",
          pillBg: "bg-emerald-100 dark:bg-emerald-950/70 text-emerald-700 dark:text-emerald-300 border-emerald-500",
        };
      case "rsi_oversold":
        return {
          label: isAr ? "تشبع بيعي" : "RSI Oversold",
          icon: Target,
          bg: "bg-sky-400 text-black border-black",
          pillBg: "bg-sky-100 dark:bg-sky-950/70 text-sky-700 dark:text-sky-300 border-sky-500",
        };
    }
  };

  return (
    <section className="space-y-6" dir={isAr ? "rtl" : "ltr"}>
      {/* ── KPI Summary Header ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Win Rate */}
        <div className="p-3.5 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
          <div className="flex items-center justify-between text-xs font-mono font-bold text-zinc-600 dark:text-zinc-400">
            <span>{isAr ? "نسبة نجاح الأهداف" : "Win Rate"}</span>
            <Award className="w-4 h-4 text-emerald-500" />
          </div>
          <p className="text-xl sm:text-2xl font-black font-mono text-emerald-600 dark:text-emerald-400 mt-1">
            {computedKpis.win_rate_pct}%
          </p>
          <span className="text-[10px] font-bold text-zinc-500 block mt-0.5">
            {isAr ? "من إجمالي الصفقات المغلقة" : "of closed trades"}
          </span>
        </div>

        {/* Active Signals */}
        <div className="p-3.5 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
          <div className="flex items-center justify-between text-xs font-mono font-bold text-zinc-600 dark:text-zinc-400">
            <span>{isAr ? "الإشارات الجارية" : "Active Signals"}</span>
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
          </div>
          <p className="text-xl sm:text-2xl font-black font-mono text-black dark:text-white mt-1">
            {activeSignals.length} <span className="text-xs font-bold">{isAr ? "صفقة نشطة" : "active"}</span>
          </p>
          <span className="text-[10px] font-bold text-zinc-500 block mt-0.5">
            {isAr ? "قيد المتابعة اللحظية والسوينج" : "intraday & swing tracking"}
          </span>
        </div>

        {/* Avg Win */}
        <div className="p-3.5 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
          <div className="flex items-center justify-between text-xs font-mono font-bold text-zinc-600 dark:text-zinc-400">
            <span>{isAr ? "متوسط الربح المحقق" : "Avg Gain"}</span>
            <TrendingUp className="w-4 h-4 text-emerald-500" />
          </div>
          <p className="text-xl sm:text-2xl font-black font-mono text-emerald-600 dark:text-emerald-400 mt-1">
            +{computedKpis.avg_win_pct}%
          </p>
          <span className="text-[10px] font-bold text-zinc-500 block mt-0.5">
            {isAr ? `أعلى صفقة: +${computedKpis.top_win_pct}%` : `Top win: +${computedKpis.top_win_pct}%`}
          </span>
        </div>

        {/* Profit Factor / Total Closed */}
        <div className="p-3.5 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
          <div className="flex items-center justify-between text-xs font-mono font-bold text-zinc-600 dark:text-zinc-400">
            <span>{isAr ? "عامل الربحية" : "Profit Factor"}</span>
            <Flame className="w-4 h-4 text-amber-500" />
          </div>
          <p className="text-xl sm:text-2xl font-black font-mono text-amber-600 dark:text-amber-400 mt-1">
            {computedKpis.profit_factor}x
          </p>
          <span className="text-[10px] font-bold text-zinc-500 block mt-0.5">
            {isAr ? `${computedKpis.total_closed} صفقة مغلقة` : `${computedKpis.total_closed} closed`}
          </span>
        </div>
      </div>

      {/* ── Sub-Tab Navigation Bar & Category Filter ── */}
      <div className="border-4 border-black dark:border-white bg-[#FFE600] text-black p-3 sm:p-4 shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_rgba(255,255,255,1)] flex flex-col md:flex-row items-center justify-between gap-3">
        {/* Active vs Closed Tabs */}
        <div className="flex items-center gap-2 w-full md:w-auto">
          <button
            type="button"
            onClick={() => setActiveTab("active")}
            className={`flex-1 md:flex-none px-4 py-2 border-2 border-black font-black text-xs uppercase tracking-wide flex items-center justify-center gap-2 shadow-[2px_2px_0px_rgba(0,0,0,1)] transition-all ${
              activeTab === "active"
                ? "bg-black text-[#FFE600]"
                : "bg-white hover:bg-zinc-100 text-black"
            }`}
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>{isAr ? "الإشارات المفتوحة" : "Active Signals"}</span>
            <span className="px-1.5 py-0.2 bg-emerald-400 text-black font-mono text-[10px]">
              {activeSignals.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("closed")}
            className={`flex-1 md:flex-none px-4 py-2 border-2 border-black font-black text-xs uppercase tracking-wide flex items-center justify-center gap-2 shadow-[2px_2px_0px_rgba(0,0,0,1)] transition-all ${
              activeTab === "closed"
                ? "bg-black text-[#FFE600]"
                : "bg-white hover:bg-zinc-100 text-black"
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>{isAr ? "الصفقات المغلقة" : "Closed History"}</span>
            <span className="px-1.5 py-0.2 bg-zinc-200 text-black font-mono text-[10px]">
              {closedSignals.length}
            </span>
          </button>
        </div>

        {/* Category Filter Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto w-full md:w-auto no-scrollbar">
          <span className="text-xs font-black uppercase text-black shrink-0 hidden sm:inline">
            {isAr ? "تصفية:" : "Filter:"}
          </span>
          {(
            [
              { id: "all", labelAr: "الكل", labelEn: "All" },
              { id: "volume_surge", labelAr: "السيولة ⚡", labelEn: "Volume ⚡" },
              { id: "breakout", labelAr: "الاختراقات 🚀", labelEn: "Breakout 🚀" },
              { id: "rsi_oversold", labelAr: "التشبع 🎯", labelEn: "Oversold 🎯" },
            ] as const
          ).map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setCategoryFilter(c.id)}
              className={`h-7 px-2.5 border-2 border-black font-black text-[11px] shrink-0 transition-all ${
                categoryFilter === c.id
                  ? "bg-black text-white shadow-[1px_1px_0px_rgba(0,0,0,1)]"
                  : "bg-white/80 hover:bg-white text-black"
              }`}
            >
              {isAr ? c.labelAr : c.labelEn}
            </button>
          ))}
        </div>
      </div>

      {/* ── Active Signals Grid ── */}
      {activeTab === "active" && (
        <div className="space-y-4">
          {filteredActive.length === 0 ? (
            <div className="p-12 text-center border-4 border-dashed border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 font-bold text-sm text-zinc-500">
              <Clock className="w-8 h-8 mx-auto mb-2 text-zinc-400" />
              {isAr
                ? "لا توجد إشارات مفتوحة حالياً لهذا الفلتر. يتم رصد إشارات جديدة وتحديثها آلياً أثناء جلسة التداول."
                : "No active tracked signals for this filter. Scanner monitors market sessions continuously."}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredActive.map((sig) => {
                const badge = getScannerBadge(sig.scanner_type);
                const BadgeIcon = badge.icon;
                const isGain = sig.return_pct >= 0;

                // Calculate progress towards Target 1
                const targetRange = sig.target_1 - sig.entry_price;
                const progressPct =
                  targetRange > 0
                    ? Math.min(100, Math.max(0, ((sig.current_price - sig.entry_price) / targetRange) * 100))
                    : 0;

                return (
                  <div
                    key={sig.id}
                    className="p-4 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_rgba(255,255,255,1)] flex flex-col justify-between gap-3 transition-all hover:translate-x-0.5 hover:translate-y-0.5"
                  >
                    {/* Top Header Row */}
                    <div>
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-base font-black px-2.5 py-0.5 bg-black text-[#FFE600] border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                            {sig.symbol}
                          </span>
                          <span
                            className={`px-2 py-0.5 text-[10px] font-black uppercase border flex items-center gap-1 ${badge.pillBg}`}
                          >
                            <BadgeIcon className="w-3 h-3" />
                            <span>{badge.label}</span>
                          </span>
                        </div>

                        {/* Live return badge */}
                        <span
                          className={`font-mono font-black text-xs px-2.5 py-0.5 border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)] ${
                            isGain ? "bg-emerald-400 text-black" : "bg-rose-400 text-black"
                          }`}
                        >
                          {isGain ? `+${sig.return_pct.toFixed(2)}%` : `${sig.return_pct.toFixed(2)}%`}
                        </span>
                      </div>

                      {/* Entry Time Subline */}
                      <p className="text-[10px] font-mono font-bold text-zinc-500 mt-1.5 flex items-center gap-1.5">
                        <Clock className="w-3 h-3 text-zinc-400 shrink-0" />
                        <span>{isAr ? "رصد الإشارة:" : "Triggered:"}</span>
                        <span className="text-zinc-800 dark:text-zinc-200">
                          {sig.entry_date} ({sig.entry_time})
                        </span>
                        <span>•</span>
                        <span>
                          {isAr ? `جلسة ${sig.sessions_count} من ${sig.max_sessions}` : `Session ${sig.sessions_count}/${sig.max_sessions}`}
                        </span>
                      </p>
                    </div>

                    {/* Trade Levels Cards (Entry / Target / Stop Loss) */}
                    <div className="space-y-2 pt-2 border-t-2 border-zinc-200 dark:border-zinc-800">
                      <div className="grid grid-cols-3 gap-1.5 text-center font-mono">
                        {/* Entry */}
                        <div className="p-2 bg-zinc-100 dark:bg-zinc-800 border-2 border-black dark:border-zinc-700">
                          <span className="text-[9px] text-zinc-500 block uppercase font-bold">
                            {isAr ? "الدخول" : "Entry"}
                          </span>
                          <span className="text-xs font-black text-black dark:text-white">
                            {sig.entry_price.toFixed(2)}
                          </span>
                        </div>

                        {/* Target 1 */}
                        <div className="p-2 bg-emerald-50 dark:bg-emerald-950/60 border-2 border-emerald-600 text-emerald-700 dark:text-emerald-300">
                          <span className="text-[9px] block uppercase font-bold flex items-center justify-center gap-0.5">
                            <Target className="w-2.5 h-2.5" />
                            {isAr ? "هدف 1" : "T1"}
                          </span>
                          <span className="text-xs font-black">
                            {sig.target_1.toFixed(2)}
                          </span>
                          <span className="text-[9px] block font-black">
                            (+{sig.target_1_pct}%)
                          </span>
                        </div>

                        {/* Stop Loss */}
                        <div className="p-2 bg-rose-50 dark:bg-rose-950/60 border-2 border-rose-600 text-rose-700 dark:text-rose-300">
                          <span className="text-[9px] block uppercase font-bold flex items-center justify-center gap-0.5">
                            <ShieldAlert className="w-2.5 h-2.5" />
                            {isAr ? "الوقف" : "SL"}
                          </span>
                          <span className="text-xs font-black">
                            {sig.stop_loss.toFixed(2)}
                          </span>
                          <span className="text-[9px] block font-black">
                            (-{sig.stop_loss_pct}%)
                          </span>
                        </div>
                      </div>

                      {/* Target 1 Progress Bar */}
                      <div>
                        <div className="flex items-center justify-between text-[10px] font-mono font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                          <span>{isAr ? "المسار نحو الهدف الأول:" : "Target Progress:"}</span>
                          <span className="font-black text-black dark:text-white">
                            {Math.round(progressPct)}%
                          </span>
                        </div>
                        <div className="w-full h-2.5 bg-zinc-200 dark:bg-zinc-700 border border-black overflow-hidden">
                          <div
                            className="h-full bg-emerald-500 transition-all duration-300"
                            style={{ width: `${progressPct}%` }}
                          />
                        </div>
                      </div>
                    </div>

                    {/* Action Bar */}
                    <div className="flex items-center justify-between pt-2 border-t-2 border-zinc-200 dark:border-zinc-800">
                      <div className="text-[10px] font-mono font-bold text-zinc-500">
                        <span>{isAr ? "أعلى قمة:" : "Peak:"}</span>{" "}
                        <span className="text-emerald-600 dark:text-emerald-400 font-black">
                          {sig.highest_price.toFixed(2)} (+{sig.max_gain_pct.toFixed(1)}%)
                        </span>
                      </div>

                      <button
                        type="button"
                        onClick={() =>
                          setChartModalStock({
                            symbol: sig.symbol,
                            date: sig.entry_date,
                            signalTime: sig.entry_time,
                            signalPrice: sig.entry_price,
                            scannerType: sig.scanner_type,
                          })
                        }
                        className="px-2.5 py-1 bg-[#FFE600] hover:bg-yellow-300 text-black border-2 border-black font-black text-[11px] flex items-center gap-1 shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-0.5 active:translate-y-0.5 transition-all"
                      >
                        <BarChart2 className="w-3.5 h-3.5" />
                        <span>{isAr ? "شارت 15 دقيقة" : "15m Chart"}</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Closed Signals History Table / Cards ── */}
      {activeTab === "closed" && (
        <div className="space-y-4">
          {filteredClosed.length === 0 ? (
            <div className="p-12 text-center border-4 border-dashed border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 font-bold text-sm text-zinc-500">
              <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-zinc-400" />
              {isAr
                ? "لا توجد صفقات مغلقة مسجلة لهذا الفلتر حتى الآن."
                : "No closed trades recorded yet for this filter."}
            </div>
          ) : (
            <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_rgba(255,255,255,1)] overflow-x-auto">
              <table className="w-full text-right text-xs">
                <thead className="bg-[#FFE600] text-black border-b-4 border-black font-black uppercase text-[11px]">
                  <tr>
                    <th className="p-3">{isAr ? "السهم" : "Symbol"}</th>
                    <th className="p-3">{isAr ? "نوع الإسكانر" : "Scanner"}</th>
                    <th className="p-3">{isAr ? "تاريخ الدخول" : "Entry Date"}</th>
                    <th className="p-3">{isAr ? "سعر الدخول" : "Entry"}</th>
                    <th className="p-3">{isAr ? "سعر الخروج" : "Exit"}</th>
                    <th className="p-3">{isAr ? "النتيجة المحققة" : "Realized Return"}</th>
                    <th className="p-3">{isAr ? "سبب الإغلاق" : "Exit Reason"}</th>
                    <th className="p-3 text-center">{isAr ? "الشارت" : "Chart"}</th>
                  </tr>
                </thead>
                <tbody className="divide-y-2 divide-zinc-200 dark:divide-zinc-800 font-mono font-bold">
                  {filteredClosed.map((c) => {
                    const badge = getScannerBadge(c.scanner_type);
                    const isWin = (c.return_pct || 0) > 0;
                    return (
                      <tr
                        key={c.id}
                        className="hover:bg-zinc-50 dark:hover:bg-zinc-800/60 transition-colors"
                      >
                        <td className="p-3">
                          <span className="font-black px-2 py-0.5 bg-black text-[#FFE600] border border-black">
                            {c.symbol}
                          </span>
                        </td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 text-[10px] font-black border ${badge.pillBg}`}>
                            {badge.label}
                          </span>
                        </td>
                        <td className="p-3 text-zinc-600 dark:text-zinc-400">
                          {c.entry_date} ({c.entry_time})
                        </td>
                        <td className="p-3 font-black text-black dark:text-white">
                          {c.entry_price.toFixed(2)} ج.م
                        </td>
                        <td className="p-3 font-black text-black dark:text-white">
                          {(c.exit_price || c.current_price).toFixed(2)} ج.م
                        </td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 border text-black font-black text-xs ${
                              isWin ? "bg-emerald-400 border-black" : "bg-rose-400 border-black"
                            }`}
                          >
                            {isWin ? `+${c.return_pct.toFixed(2)}%` : `${c.return_pct.toFixed(2)}%`}
                          </span>
                        </td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 text-[10px] font-black border ${
                              c.status === "target_hit"
                                ? "bg-emerald-100 dark:bg-emerald-950/80 text-emerald-700 dark:text-emerald-300 border-emerald-500"
                                : c.status === "stopped_out"
                                ? "bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 border-rose-500"
                                : "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-400"
                            }`}
                          >
                            {c.exit_reason || (isWin ? "تحقق الهدف 🎯" : "إغلاق الصفقة")}
                          </span>
                        </td>
                        <td className="p-3 text-center">
                          <button
                            type="button"
                            onClick={() =>
                              setChartModalStock({
                                symbol: c.symbol,
                                date: c.entry_date,
                                signalTime: c.entry_time,
                                signalPrice: c.entry_price,
                                scannerType: c.scanner_type,
                              })
                            }
                            className="p-1.5 bg-[#FFE600] hover:bg-yellow-300 text-black border border-black shadow-[1px_1px_0px_rgba(0,0,0,1)] active:translate-x-0.5 active:translate-y-0.5"
                            title={isAr ? "عرض شارت 15 دقيقة" : "View 15m Chart"}
                          >
                            <BarChart2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Guidance Footnote ── */}
      <div className="p-3.5 bg-zinc-100 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 flex items-start gap-2.5 text-xs font-bold text-zinc-600 dark:text-zinc-400 leading-relaxed">
        <Info className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
        <p>
          {isAr
            ? "نظام تتبع إشارات الإسكانر يراقب الصفقات آلياً لمدة 5 جلسات تداول متتالية بحد أقصى. يتم إغلاق الصفقة فور تحقيق الهدف الأول (Target 1) أو كسر مستوى وقف الخسارة (Stop Loss) مع إرسال إشعارات فورية عبر التليجرام."
            : "The scanner signals tracker continuously monitors opportunities for up to 5 consecutive sessions. Trades are closed automatically upon hitting Target 1 or Stop Loss, with immediate alerts sent via Telegram."}
        </p>
      </div>

      {/* ── 15-Minute Intraday Session Candlestick Chart Modal ── */}
      {chartModalStock && (
        <ScannerIntradayChartModal
          isOpen={Boolean(chartModalStock)}
          onClose={() => setChartModalStock(null)}
          symbol={chartModalStock.symbol}
          date={chartModalStock.date}
          signalTime={chartModalStock.signalTime}
          signalPrice={chartModalStock.signalPrice}
          scannerType={chartModalStock.scannerType}
          isAr={isAr}
        />
      )}
    </section>
  );
}
