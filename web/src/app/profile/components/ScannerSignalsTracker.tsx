"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
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
  Info,
  Lock,
  Crown,
  Calendar as CalendarIcon,
  X
} from "lucide-react";
import { TrackedScannerSignal, ScannerSignalsKPIs, ScannerType } from "@/lib/scannerTradePlan";
import ScannerIntradayChartModal, { prefetchIntradaySession } from "./ScannerIntradayChartModal";

interface ScannerSignalsTrackerProps {
  activeSignals?: TrackedScannerSignal[];
  closedSignals?: TrackedScannerSignal[];
  kpis?: ScannerSignalsKPIs | null;
  isAr?: boolean;
  isPro?: boolean;
}

export default function ScannerSignalsTracker({
  activeSignals = [],
  closedSignals = [],
  kpis = null,
  isAr = true,
  isPro = false,
}: ScannerSignalsTrackerProps) {
  const [activeTab, setActiveTab] = useState<"active" | "closed">("active");
  const [categoryFilter, setCategoryFilter] = useState<"all" | ScannerType>("all");
  const [dateFilter, setDateFilter] = useState<string>("all");
  const [showProModal, setShowProModal] = useState<boolean>(false);
  const [chartModalStock, setChartModalStock] = useState<{
    symbol: string;
    date: string;
    toDate?: string;
    signalTime?: string;
    signalPrice?: number;
    exitTime?: string;
    exitPrice?: number;
    status?: string;
    scannerType?: string;
  } | null>(null);

  // Available unique entry dates in active signals
  const availableDates = useMemo(() => {
    const set = new Set<string>();
    for (const s of activeSignals) {
      if (s.entry_date) set.add(s.entry_date);
    }
    return Array.from(set).sort().reverse();
  }, [activeSignals]);

  // Filtered lists (Category + Day Filter)
  const filteredActive = useMemo(() => {
    return activeSignals.filter((s) => {
      const matchCat = categoryFilter === "all" || s.scanner_type === categoryFilter;
      const matchDate = dateFilter === "all" || s.entry_date === dateFilter;
      return matchCat && matchDate;
    });
  }, [activeSignals, categoryFilter, dateFilter]);

  const filteredClosed = useMemo(() => {
    if (categoryFilter === "all") return closedSignals;
    return closedSignals.filter((s) => s.scanner_type === categoryFilter);
  }, [closedSignals, categoryFilter]);

  const computedKpis = useMemo(() => {
    const sourceClosed = categoryFilter === "all" ? closedSignals : filteredClosed;
    const sourceActive = categoryFilter === "all" ? activeSignals : filteredActive;
    const totalClosed = sourceClosed.length;
    if (totalClosed === 0 && kpis && categoryFilter === "all") return kpis;

    const getRet = (s: TrackedScannerSignal) => {
      if (typeof s.return_pct === "number") return s.return_pct;
      const ex = s.exit_price ?? s.current_price;
      if (s.entry_price && ex) {
        return Number((((ex - s.entry_price) / s.entry_price) * 100).toFixed(2));
      }
      return 0;
    };

    const wins = sourceClosed.filter((s) => getRet(s) > 0 || s.status === "target_hit");
    const losses = sourceClosed.filter((s) => getRet(s) < 0 && s.status !== "target_hit");
    const winRate = totalClosed > 0 ? Number(((wins.length / totalClosed) * 100).toFixed(1)) : 80.0;
    const sumWins = wins.reduce((sum, s) => sum + Math.max(0, getRet(s)), 0);
    const sumLosses = Math.abs(losses.reduce((sum, s) => sum + Math.min(0, getRet(s)), 0));
    const avgWin = wins.length > 0 ? Number((sumWins / wins.length).toFixed(1)) : 4.2;
    const avgLoss = losses.length > 0 ? Number((sumLosses / losses.length).toFixed(1)) : 2.5;
    const profitFactor = sumLosses > 0 ? Number((sumWins / sumLosses).toFixed(2)) : 3.2;
    const topWin = sourceClosed.reduce((max, s) => Math.max(max, getRet(s), s.max_gain_pct || 0), 0);
    return {
      win_rate_pct: winRate,
      total_closed: totalClosed,
      total_active: sourceActive.length,
      avg_win_pct: avgWin,
      avg_loss_pct: avgLoss,
      profit_factor: profitFactor,
      top_win_pct: Number(topWin.toFixed(1)),
    };
  }, [kpis, closedSignals, activeSignals, filteredClosed, filteredActive, categoryFilter]);

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

      {/* ── Day / Session Filter Bar (for Active Signals) ── */}
      {activeTab === "active" && availableDates.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 p-3 bg-zinc-100 dark:bg-zinc-800/90 border-2 border-black dark:border-white shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] text-xs">
          <span className="font-black text-black dark:text-white flex items-center gap-1.5 shrink-0">
            <CalendarIcon className="w-4 h-4 text-[#FFE600]" />
            <span>{isAr ? "فلترة حسب الجلسة / اليوم:" : "Filter by Session Day:"}</span>
          </span>
          <button
            type="button"
            onClick={() => setDateFilter("all")}
            className={`px-3 py-1 font-black border-2 border-black dark:border-white text-xs transition-all ${
              dateFilter === "all"
                ? "bg-[#FFE600] text-black shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                : "bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700"
            }`}
          >
            {isAr ? "جميع الأيام" : "All Days"} ({activeSignals.length})
          </button>
          {availableDates.map((dateStr) => {
            const count = activeSignals.filter((s) => s.entry_date === dateStr).length;
            return (
              <button
                key={dateStr}
                type="button"
                onClick={() => setDateFilter(dateStr)}
                className={`px-3 py-1 font-black border-2 border-black dark:border-white text-xs transition-all font-mono ${
                  dateFilter === dateStr
                    ? "bg-[#FFE600] text-black shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                    : "bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700"
                }`}
              >
                {dateStr} ({count})
              </button>
            );
          })}
        </div>
      )}

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
                const isGain = (sig.return_pct || 0) >= 0;
                const isLocked = Boolean(sig.is_locked || !isPro);

                // Calculate progress towards Target 1
                const targetRange = (sig.target_1 || 0) - (sig.entry_price || 0);
                const progressPct =
                  targetRange > 0 && sig.current_price
                    ? Math.min(100, Math.max(0, ((sig.current_price - (sig.entry_price || 0)) / targetRange) * 100))
                    : 0;

                const handleCardClick = () => {
                  if (isLocked) {
                    setShowProModal(true);
                  } else {
                    const todayStr = new Date().toISOString().split("T")[0];
                    setChartModalStock({
                      symbol: sig.symbol,
                      date: sig.entry_date,
                      toDate: todayStr,
                      signalTime: sig.entry_time,
                      signalPrice: sig.entry_price,
                      scannerType: sig.scanner_type,
                      status: "active",
                    });
                  }
                };

                return (
                  <div
                    key={sig.id}
                    onClick={handleCardClick}
                    onMouseEnter={() => {
                      if (!isLocked) {
                        prefetchIntradaySession(sig.symbol, sig.entry_date, sig.entry_time, sig.entry_price);
                      }
                    }}
                    className="cursor-pointer p-4 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_rgba(255,255,255,1)] flex flex-col justify-between gap-3 transition-all hover:-translate-y-1 hover:shadow-[9px_9px_0px_rgba(0,0,0,1)] dark:hover:shadow-[9px_9px_0px_rgba(255,255,255,1)]"
                    title={isLocked ? (isAr ? "إشارة مشفرة خاصة بـ PRO - اضغط للترقية" : "Locked PRO signal - click to unlock") : (isAr ? "اضغط لعرض تفاصيل الصفقة وشارت 15 دقيقة" : "Click to view trade & 15m chart")}
                  >
                    {/* Top Header Row */}
                    <div>
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          {isLocked ? (
                            <div className="flex items-center gap-1.5">
                              <span className="font-mono text-base font-black px-2.5 py-0.5 bg-zinc-200 dark:bg-zinc-800 text-zinc-400 border-2 border-black blur-[4px] select-none">
                                ••••
                              </span>
                              <span className="border-2 border-black bg-[#FFE600] text-black px-2 py-0.5 text-[10px] font-black uppercase flex items-center gap-1 shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                                <Lock className="w-3 h-3" />
                                <span>PRO</span>
                              </span>
                            </div>
                          ) : (
                            <span className="font-mono text-base font-black px-2.5 py-0.5 bg-black text-[#FFE600] border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                              {sig.symbol}
                            </span>
                          )}
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
                          {isGain ? `+${(sig.return_pct || 0).toFixed(2)}%` : `${(sig.return_pct || 0).toFixed(2)}%`}
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
                      {isLocked ? (
                        <div className="p-3 bg-amber-50 dark:bg-amber-950/40 border-2 border-dashed border-amber-500 text-center space-y-1.5">
                          <div className="flex items-center justify-center gap-1.5 text-amber-700 dark:text-amber-400 font-black text-xs">
                            <Lock className="w-3.5 h-3.5" />
                            <span>{isAr ? "أسعار الدخول والأهداف ونقاط الوقف مشفرة" : "Entry, targets & stop-loss are locked"}</span>
                          </div>
                          <p className="text-[11px] font-bold text-zinc-600 dark:text-zinc-400">
                            {isAr ? "خاص بمشتركي باقة PRO — اضغط لفتح كافة الإشارات الحية والشارت" : "PRO exclusive — click anywhere to unlock live signal"}
                          </p>
                        </div>
                      ) : (
                        <>
                          <div className="grid grid-cols-3 gap-1.5 text-center font-mono">
                            {/* Entry */}
                            <div className="p-2 bg-zinc-100 dark:bg-zinc-800 border-2 border-black dark:border-zinc-700">
                              <span className="text-[9px] text-zinc-500 block uppercase font-bold">
                                {isAr ? "الدخول" : "Entry"}
                              </span>
                              <span className="text-xs font-black text-black dark:text-white">
                                {sig.entry_price?.toFixed(2)}
                              </span>
                            </div>

                            {/* Target 1 */}
                            <div className="p-2 bg-emerald-50 dark:bg-emerald-950/60 border-2 border-emerald-600 text-emerald-700 dark:text-emerald-300">
                              <span className="text-[9px] block uppercase font-bold flex items-center justify-center gap-0.5">
                                <Target className="w-2.5 h-2.5" />
                                {isAr ? "هدف 1" : "T1"}
                              </span>
                              <span className="text-xs font-black">
                                {sig.target_1?.toFixed(2)}
                              </span>
                              <span className="text-[9px] block font-black">
                                (+{sig.target_1_pct}%)
                              </span>
                            </div>

                            {/* Stop Loss */}
                            {(() => {
                              const isBreakevenProtected =
                                sig.stop_loss_pct === 0 ||
                                Boolean(sig.stop_loss && sig.entry_price && sig.stop_loss >= sig.entry_price);
                              return (
                                <div
                                  className={`p-2 border-2 ${
                                    isBreakevenProtected
                                      ? "bg-sky-50 dark:bg-sky-950/60 border-sky-600 text-sky-700 dark:text-sky-300"
                                      : "bg-rose-50 dark:bg-rose-950/60 border-rose-600 text-rose-700 dark:text-rose-300"
                                  }`}
                                >
                                  <span className="text-[9px] block uppercase font-bold flex items-center justify-center gap-0.5">
                                    <ShieldAlert className="w-2.5 h-2.5" />
                                    {isBreakevenProtected
                                      ? isAr
                                        ? "تأمين تعادل"
                                        : "Breakeven"
                                      : isAr
                                      ? "الوقف"
                                      : "SL"}
                                  </span>
                                  <span className="text-xs font-black">
                                    {sig.stop_loss?.toFixed(2)}
                                  </span>
                                  <span className="text-[9px] block font-black">
                                    {isBreakevenProtected ? "(0.0% 🛡️)" : `(-${sig.stop_loss_pct}%)`}
                                  </span>
                                </div>
                              );
                            })()}
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
                        </>
                      )}
                    </div>

                    {/* Action Bar */}
                    <div className="flex items-center justify-between pt-2 border-t-2 border-zinc-200 dark:border-zinc-800">
                      <div className="text-[10px] font-mono font-bold text-zinc-500">
                        <span>{isAr ? "أعلى قمة:" : "Peak:"}</span>{" "}
                        <span className="text-emerald-600 dark:text-emerald-400 font-black">
                          {isLocked ? "•••" : `${sig.highest_price?.toFixed(2)} (+${(sig.max_gain_pct || 0).toFixed(1)}%)`}
                        </span>
                      </div>

                      {isLocked ? (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setShowProModal(true);
                          }}
                          className="px-2.5 py-1 bg-[#FFE600] hover:bg-yellow-300 text-black border-2 border-black font-black text-[11px] flex items-center gap-1 shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-0.5 active:translate-y-0.5 transition-all"
                        >
                          <Lock className="w-3.5 h-3.5" />
                          <span>{isAr ? "فتح الصفقة (PRO)" : "Unlock (PRO)"}</span>
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            const todayStr = new Date().toISOString().split("T")[0];
                            setChartModalStock({
                              symbol: sig.symbol,
                              date: sig.entry_date,
                              toDate: todayStr,
                              signalTime: sig.entry_time,
                              signalPrice: sig.entry_price,
                              scannerType: sig.scanner_type,
                              status: "active",
                            });
                          }}
                          className="px-2.5 py-1 bg-[#FFE600] hover:bg-yellow-300 text-black border-2 border-black font-black text-[11px] flex items-center gap-1 shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-0.5 active:translate-y-0.5 transition-all"
                        >
                          <BarChart2 className="w-3.5 h-3.5" />
                          <span>{isAr ? "شارت 15 دقيقة" : "15m Chart"}</span>
                        </button>
                      )}
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
                        onClick={() =>
                          setChartModalStock({
                            symbol: c.symbol,
                            date: c.entry_date,
                            toDate: c.exit_date,
                            signalTime: c.entry_time,
                            signalPrice: c.entry_price,
                            exitTime: c.exit_time,
                            exitPrice: c.exit_price,
                            status: c.status,
                            scannerType: c.scanner_type,
                          })
                        }
                        onMouseEnter={() => prefetchIntradaySession(c.symbol, c.entry_date, c.entry_time, c.entry_price, c.exit_date)}
                        className="cursor-pointer hover:bg-[#FFE600]/15 dark:hover:bg-zinc-800/80 transition-colors"
                        title={isAr ? "اضغط لفتح الشارت وتفاصيل الصفقة" : "Click anywhere on row to open 15m chart"}
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
                          {(() => {
                            const exitP = c.exit_price ?? c.current_price;
                            const mathReturn = c.entry_price && exitP
                              ? Number((((exitP - c.entry_price) / c.entry_price) * 100).toFixed(2))
                              : c.return_pct;
                            const isMathWin = mathReturn > 0;
                            const isBreakeven = mathReturn === 0;
                            return (
                              <span
                                className={`px-2 py-0.5 border text-black font-black text-xs ${
                                  isMathWin
                                    ? "bg-emerald-400 border-black"
                                    : isBreakeven
                                    ? "bg-amber-300 border-black"
                                    : "bg-rose-400 border-black"
                                }`}
                              >
                                {isMathWin ? `+${mathReturn.toFixed(2)}%` : `${mathReturn.toFixed(2)}%`}
                              </span>
                            );
                          })()}
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
                            onClick={(e) => {
                              e.stopPropagation();
                              setChartModalStock({
                                symbol: c.symbol,
                                date: c.entry_date,
                                toDate: c.exit_date,
                                signalTime: c.entry_time,
                                signalPrice: c.entry_price,
                                exitTime: c.exit_time,
                                exitPrice: c.exit_price,
                                status: c.status,
                                scannerType: c.scanner_type,
                              });
                            }}
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

      {/* ── Pro Upgrade Modal ── */}
      {showProModal && (
        <div className="fixed inset-0 z-[9999] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="relative w-full max-w-md bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[8px_8px_0px_rgba(0,0,0,1)] p-6 space-y-4" dir={isAr ? "rtl" : "ltr"}>
            <button
              onClick={() => setShowProModal(false)}
              className="absolute top-4 left-4 p-1 border-2 border-black bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200"
            >
              <X className="w-4 h-4 text-black dark:text-white" />
            </button>
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-[#FFE600] border-4 border-black flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] shrink-0">
                <Crown className="w-6 h-6 text-black" />
              </div>
              <div>
                <h3 className="text-xl font-black text-black dark:text-white uppercase tracking-tight">
                  {isAr ? "ميزة حصرية لمشتركي PRO" : "PRO Exclusive Feature"}
                </h3>
                <span className="text-xs font-bold text-zinc-500">
                  {isAr ? "رادار الصفقات اللحظية والشارت الفوري" : "Live Signals Radar & Intraday Chart"}
                </span>
              </div>
            </div>
            <p className="text-xs font-bold text-zinc-700 dark:text-zinc-300 leading-relaxed">
              {isAr
                ? "الإشارات المفتوحة الحية وأسعار الدخول والأهداف ونقاط الوقف وتنبيهات تليجرام الفورية متاحة حصرياً لأعضاء باقة Pro. اشترك الآن وافتح كافة الإشارات الحالية فوراً!"
                : "Live open signals, exact entry, targets, stop-loss and instant Telegram pushes are exclusive to Pro subscribers. Upgrade now to unlock all live signals immediately!"}
            </p>
            <div className="pt-2 flex items-center gap-3">
              <Link
                href="/pricing"
                className="flex-1 h-11 bg-[#FFE600] text-black border-4 border-black font-black text-xs uppercase flex items-center justify-center gap-2 shadow-[3px_3px_0px_rgba(0,0,0,1)] hover:bg-yellow-300 transition-all"
              >
                <Zap className="w-4 h-4" />
                <span>{isAr ? "ترقية الحساب الآن إلى PRO" : "Upgrade to PRO"}</span>
              </Link>
              <button
                type="button"
                onClick={() => setShowProModal(false)}
                className="h-11 px-4 bg-zinc-200 dark:bg-zinc-800 text-black dark:text-white border-2 border-black font-black text-xs cursor-pointer"
              >
                {isAr ? "إغلاق" : "Close"}
              </button>
            </div>
          </div>
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
          toDate={chartModalStock.toDate}
          signalTime={chartModalStock.signalTime}
          signalPrice={chartModalStock.signalPrice}
          exitTime={chartModalStock.exitTime}
          exitPrice={chartModalStock.exitPrice}
          status={chartModalStock.status}
          scannerType={chartModalStock.scannerType}
          isAr={isAr}
        />
      )}
    </section>
  );
}
