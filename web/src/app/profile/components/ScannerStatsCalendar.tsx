"use client";

import React, { useState, useMemo, useEffect } from "react";
import { createPortal } from "react-dom";
import {
  Calendar as CalendarIcon,
  ChevronLeft,
  ChevronRight,
  Zap,
  ArrowUpRight,
  Target,
  Newspaper,
  Layers,
  Sparkles,
  Clock,
  TrendingUp,
  Activity,
  Flame,
  Info,
  X,
  BarChart2
} from "lucide-react";
import ScannerIntradayChartModal from "./ScannerIntradayChartModal";

export type ScannerCategory = "all" | "volume_surge" | "breakout" | "rsi_oversold" | "disclosures";

export interface ScanHistoryItem {
  timestamp: string;
  duration_ms: number;
  volume_count: number;
  breakout_count: number;
  oversold_count: number;
  disclosures_count: number;
  recipients_count: number;
  triggered_by: string;
  stage_results?: {
    volume_surge: Array<{ symbol: string; close: number; change_pct: number; r_vol: number; signal_time?: string }>;
    breakout: Array<{ symbol: string; close: number; change_pct: number; r_vol: number; signal_time?: string }>;
    rsi_oversold: Array<{ symbol: string; close: number; rsi_14: number; change_pct: number; signal_time?: string }>;
    disclosures: Array<{ id: string; title: string; symbol?: string; published_at?: string }>;
  };
}

interface ScannerStatsCalendarProps {
  history: ScanHistoryItem[];
  lastScan?: any;
  isAr?: boolean;
}

export default function ScannerStatsCalendar({
  history = [],
  lastScan,
  isAr = true,
}: ScannerStatsCalendarProps) {
  const [selectedCategory, setSelectedCategory] = useState<ScannerCategory>("all");
  const [isDialogOpen, setIsDialogOpen] = useState<boolean>(false);
  const [isMounted, setIsMounted] = useState<boolean>(false);
  const [chartModalStock, setChartModalStock] = useState<{
    symbol: string;
    date: string;
    signalTime?: string;
    signalPrice?: number;
    scannerType?: string;
  } | null>(null);

  // Helper formatters for clean financial representation (1-2 decimals instead of 4-5)
  const formatPct = (val: number | string | undefined) => {
    if (val === undefined || val === null) return "0.0";
    const num = typeof val === "string" ? parseFloat(val) : val;
    if (isNaN(num)) return "0.0";
    return num.toFixed(1);
  };

  const formatVol = (val: number | string | undefined) => {
    if (val === undefined || val === null) return "1.0";
    const num = typeof val === "string" ? parseFloat(val) : val;
    if (isNaN(num)) return "1.0";
    return num.toFixed(1);
  };

  const formatPrice = (val: number | string | undefined) => {
    if (val === undefined || val === null) return "0.00";
    const num = typeof val === "string" ? parseFloat(val) : val;
    if (isNaN(num)) return "0.00";
    return num < 1 ? num.toFixed(3) : num.toFixed(2);
  };

  const formatRsi = (val: number | string | undefined) => {
    if (val === undefined || val === null) return "30";
    const num = typeof val === "string" ? parseFloat(val) : val;
    if (isNaN(num)) return "30";
    return Math.round(num);
  };

  // Format signal timestamp into localized Cairo time string (e.g., 10:15 ص or 10:15 AM)
  const formatSignalTime = (timeStr?: string) => {
    if (!timeStr) return isAr ? "10:15 ص" : "10:15 AM";
    try {
      const d = new Date(timeStr);
      if (isNaN(d.getTime())) {
        return timeStr.includes(":") ? timeStr : (isAr ? "10:15 ص" : "10:15 AM");
      }
      return d.toLocaleTimeString(isAr ? "ar-EG" : "en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
        timeZone: "Africa/Cairo",
      });
    } catch {
      return isAr ? "10:15 ص" : "10:15 AM";
    }
  };

  // Extract HH:MM for chart session marker lookup
  const getSignalHHMM = (timeStr?: string) => {
    if (!timeStr) return "10:15";
    try {
      const d = new Date(timeStr);
      if (isNaN(d.getTime())) {
        const match = timeStr.match(/\d{2}:\d{2}/);
        return match ? match[0] : "10:15";
      }
      const parts = new Intl.DateTimeFormat("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: "Africa/Cairo",
      }).formatToParts(d);
      const hour = parts.find((p) => p.type === "hour")?.value || "10";
      const minute = parts.find((p) => p.type === "minute")?.value || "15";
      return `${hour}:${minute}`;
    } catch {
      return "10:15";
    }
  };

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsDialogOpen(false);
    };
    if (isDialogOpen) {
      window.addEventListener("keydown", handleEsc);
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "unset";
    }
    return () => {
      window.removeEventListener("keydown", handleEsc);
      document.body.style.overflow = "unset";
    };
  }, [isDialogOpen]);
  
  // Current viewing month (default to latest history month or today)
  const [currentDate, setCurrentDate] = useState(() => {
    if (history.length > 0 && history[0].timestamp) {
      const d = new Date(history[0].timestamp);
      return new Date(d.getFullYear(), d.getMonth(), 1);
    }
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  // Selected date for day details breakdown (default to today / latest)
  const [selectedDateStr, setSelectedDateStr] = useState<string>(() => {
    if (history.length > 0 && history[0].timestamp) {
      return history[0].timestamp.split("T")[0];
    }
    return new Date().toISOString().split("T")[0];
  });

  // ── 1. Aggregate History Data By Date (YYYY-MM-DD) ──
  const dailyDataMap = useMemo(() => {
    const map = new Map<
      string,
      {
        date: string;
        scansCount: number;
        volumeCount: number;
        breakoutCount: number;
        oversoldCount: number;
        disclosuresCount: number;
        totalOpportunities: number;
        avgDurationMs: number;
        samples: ScanHistoryItem[];
        stocks: {
          volume: Array<{ symbol: string; close: number; change_pct: number; r_vol: number; signal_time?: string }>;
          breakout: Array<{ symbol: string; close: number; change_pct: number; r_vol: number; signal_time?: string }>;
          oversold: Array<{ symbol: string; close: number; rsi_14: number; change_pct: number; signal_time?: string }>;
          disclosures: Array<{ id: string; title: string; symbol?: string; published_at?: string }>;
        };
      }
    >();

    // Process all history items
    for (const h of history) {
      if (!h.timestamp) continue;
      const dateKey = h.timestamp.split("T")[0];
      if (!map.has(dateKey)) {
        map.set(dateKey, {
          date: dateKey,
          scansCount: 0,
          volumeCount: 0,
          breakoutCount: 0,
          oversoldCount: 0,
          disclosuresCount: 0,
          totalOpportunities: 0,
          avgDurationMs: 0,
          samples: [],
          stocks: { volume: [], breakout: [], oversold: [], disclosures: [] },
        });
      }

      const dEntry = map.get(dateKey)!;
      dEntry.scansCount += 1;
      dEntry.volumeCount += h.volume_count || 0;
      dEntry.breakoutCount += h.breakout_count || 0;
      dEntry.oversoldCount += h.oversold_count || 0;
      dEntry.disclosuresCount += h.disclosures_count || 0;
      dEntry.totalOpportunities +=
        (h.volume_count || 0) +
        (h.breakout_count || 0) +
        (h.oversold_count || 0) +
        (h.disclosures_count || 0);
      dEntry.avgDurationMs += h.duration_ms || 0;
      dEntry.samples.push(h);

      // Collect stocks if available in stage_results
      if (h.stage_results) {
        if (h.stage_results.volume_surge) {
          for (const s of h.stage_results.volume_surge) {
            if (!dEntry.stocks.volume.some((x: any) => x.symbol === s.symbol)) {
              dEntry.stocks.volume.push({ ...s, signal_time: s.signal_time || h.timestamp });
            }
          }
        }
        if (h.stage_results.breakout) {
          for (const s of h.stage_results.breakout) {
            if (!dEntry.stocks.breakout.some((x: any) => x.symbol === s.symbol)) {
              dEntry.stocks.breakout.push({ ...s, signal_time: s.signal_time || h.timestamp });
            }
          }
        }
        if (h.stage_results.rsi_oversold) {
          for (const s of h.stage_results.rsi_oversold) {
            if (!dEntry.stocks.oversold.some((x: any) => x.symbol === s.symbol)) {
              dEntry.stocks.oversold.push({ ...s, signal_time: s.signal_time || h.timestamp });
            }
          }
        }
        if (h.stage_results.disclosures) {
          for (const s of h.stage_results.disclosures) {
            if (!dEntry.stocks.disclosures.some((x: any) => x.title === s.title)) {
              dEntry.stocks.disclosures.push(s);
            }
          }
        }
      }
    }

    // If last_scan has stage results for today, merge them in as well
    if (lastScan?.stage_results && lastScan?.timestamp) {
      const todayKey = lastScan.timestamp.split("T")[0];
      if (map.has(todayKey)) {
        const dEntry = map.get(todayKey)!;
        if (dEntry.stocks.volume.length === 0 && lastScan.stage_results.volume_surge) {
          dEntry.stocks.volume = lastScan.stage_results.volume_surge.map((s: any) => ({
            ...s,
            signal_time: s.signal_time || lastScan.timestamp,
          }));
        }
        if (dEntry.stocks.breakout.length === 0 && lastScan.stage_results.breakout) {
          dEntry.stocks.breakout = lastScan.stage_results.breakout.map((s: any) => ({
            ...s,
            signal_time: s.signal_time || lastScan.timestamp,
          }));
        }
        if (dEntry.stocks.oversold.length === 0 && lastScan.stage_results.rsi_oversold) {
          dEntry.stocks.oversold = lastScan.stage_results.rsi_oversold.map((s: any) => ({
            ...s,
            signal_time: s.signal_time || lastScan.timestamp,
          }));
        }
        if (dEntry.stocks.disclosures.length === 0 && lastScan.stage_results.disclosures) {
          dEntry.stocks.disclosures = [...lastScan.stage_results.disclosures];
        }
      }
    }

    // Compute averages and normalize daily counts to UNIQUE stock opportunities (avoiding inflated repeating snapshot sums)
    for (const entry of map.values()) {
      if (entry.scansCount > 0) {
        entry.avgDurationMs = Math.round(entry.avgDurationMs / entry.scansCount);
      }

      // If unique stocks are collected in stage_results, use their true count.
      // Otherwise fallback to the peak snapshot count across scans for that day.
      entry.volumeCount = entry.stocks.volume.length > 0
        ? entry.stocks.volume.length
        : Math.max(0, ...entry.samples.map((s) => s.volume_count || 0));

      entry.breakoutCount = entry.stocks.breakout.length > 0
        ? entry.stocks.breakout.length
        : Math.max(0, ...entry.samples.map((s) => s.breakout_count || 0));

      entry.oversoldCount = entry.stocks.oversold.length > 0
        ? entry.stocks.oversold.length
        : Math.max(0, ...entry.samples.map((s) => s.oversold_count || 0));

      entry.disclosuresCount = entry.stocks.disclosures.length > 0
        ? entry.stocks.disclosures.length
        : Math.max(0, ...entry.samples.map((s) => s.disclosures_count || 0));

      entry.totalOpportunities =
        entry.volumeCount +
        entry.breakoutCount +
        entry.oversoldCount +
        entry.disclosuresCount;
    }

    return map;
  }, [history, lastScan]);

  // ── 2. Overall Category Filtered Metrics (KPIs) ──
  const statsSummary = useMemo(() => {
    let totalScans = 0;
    let totalMatches = 0;
    let daysWithSignals = 0;
    let highestSingleDayCount = 0;
    let highestDayDate = "";

    for (const d of dailyDataMap.values()) {
      totalScans += d.scansCount;
      let countForCategory = 0;
      if (selectedCategory === "all") countForCategory = d.totalOpportunities;
      else if (selectedCategory === "volume_surge") countForCategory = d.volumeCount;
      else if (selectedCategory === "breakout") countForCategory = d.breakoutCount;
      else if (selectedCategory === "rsi_oversold") countForCategory = d.oversoldCount;
      else if (selectedCategory === "disclosures") countForCategory = d.disclosuresCount;

      totalMatches += countForCategory;
      if (countForCategory > 0) daysWithSignals += 1;
      if (countForCategory > highestSingleDayCount) {
        highestSingleDayCount = countForCategory;
        highestDayDate = d.date;
      }
    }

    return {
      totalScans,
      totalMatches,
      daysWithSignals,
      highestSingleDayCount,
      highestDayDate,
      activeDaysCount: dailyDataMap.size,
    };
  }, [dailyDataMap, selectedCategory]);

  // ── 3. Calendar Grid Building (Days of Month) ──
  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDayIndex = new Date(year, month, 1).getDay(); // 0 is Sun, 6 is Sat

  const calendarDays = useMemo(() => {
    const days: Array<{
      dateStr: string;
      dayNum: number;
      isCurrentMonth: boolean;
      data?: (typeof dailyDataMap) extends Map<any, infer V> ? V : never;
    }> = [];

    // Preceding empty/padding days
    for (let i = 0; i < firstDayIndex; i++) {
      days.push({
        dateStr: `pad-${i}`,
        dayNum: 0,
        isCurrentMonth: false,
      });
    }

    // Days of the month
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const dayData = dailyDataMap.get(dateStr);
      days.push({
        dateStr,
        dayNum: d,
        isCurrentMonth: true,
        data: dayData,
      });
    }

    return days;
  }, [year, month, firstDayIndex, daysInMonth, dailyDataMap]);

  const handlePrevMonth = () => {
    setCurrentDate(new Date(year, month - 1, 1));
  };

  const handleNextMonth = () => {
    setCurrentDate(new Date(year, month + 1, 1));
  };

  // Selected Day Details
  const selectedDayData = selectedDateStr ? dailyDataMap.get(selectedDateStr) : null;

  // Pre-fetch intraday session charts in background for instantaneous modal opening
  useEffect(() => {
    if (!isDialogOpen || !selectedDayData) return;
    const stocksToPreload = [
      ...selectedDayData.stocks.volume.map((s) => ({ symbol: s.symbol, time: getSignalHHMM((s as any).signal_time), price: s.close })),
      ...selectedDayData.stocks.breakout.map((s) => ({ symbol: s.symbol, time: getSignalHHMM((s as any).signal_time), price: s.close })),
      ...selectedDayData.stocks.oversold.map((s) => ({ symbol: s.symbol, time: getSignalHHMM((s as any).signal_time), price: s.close })),
    ];
    // Warm up the cache for these symbols in the background
    stocksToPreload.slice(0, 8).forEach(({ symbol, time, price }) => {
      const p = new URLSearchParams({ symbol, date: selectedDateStr });
      if (time) p.set("signal_time", time);
      if (price) p.set("signal_price", String(price));
      fetch(`/api/scanner/intraday-session?${p.toString()}`).catch(() => {});
    });
  }, [isDialogOpen, selectedDateStr, selectedDayData]);

  // Filter categories config
  const categories: Array<{
    id: ScannerCategory;
    nameAr: string;
    nameEn: string;
    icon: any;
    colorClass: string;
    activeBg: string;
  }> = [
    {
      id: "all",
      nameAr: "جميع الإسكانرات",
      nameEn: "All Scanners",
      icon: Layers,
      colorClass: "text-zinc-900 dark:text-white",
      activeBg: "bg-black text-white dark:bg-white dark:text-black",
    },
    {
      id: "volume_surge",
      nameAr: "السيولة الذكية",
      nameEn: "Volume Surge",
      icon: Zap,
      colorClass: "text-amber-600",
      activeBg: "bg-amber-400 text-black",
    },
    {
      id: "breakout",
      nameAr: "الاختراقات الفنية",
      nameEn: "Breakouts",
      icon: ArrowUpRight,
      colorClass: "text-emerald-600",
      activeBg: "bg-emerald-400 text-black",
    },
    {
      id: "rsi_oversold",
      nameAr: "التشبع البيعي",
      nameEn: "RSI Oversold",
      icon: Target,
      colorClass: "text-sky-600",
      activeBg: "bg-sky-400 text-black",
    },
    {
      id: "disclosures",
      nameAr: "الإفصاحات الرسمية",
      nameEn: "Disclosures",
      icon: Newspaper,
      colorClass: "text-purple-600",
      activeBg: "bg-purple-400 text-black",
    },
  ];

  const monthNamesAr = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"
  ];
  const weekDaysAr = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"];
  const weekDaysEn = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  return (
    <section
      className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 sm:p-8 shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_rgba(255,255,255,1)] space-y-8 animate-in fade-in duration-300"
      dir={isAr ? "rtl" : "ltr"}
    >
      {/* ── Header ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b-4 border-black dark:border-white pb-6">
        <div className="flex items-center gap-3">
          <div className="h-12 w-12 border-4 border-black dark:border-white bg-[#FFE600] text-black flex items-center justify-center shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] shrink-0">
            <CalendarIcon className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-2xl font-black text-black dark:text-white uppercase tracking-tight">
                {isAr ? "تقويم إحصائيات رادار الإسكانرات" : "Scanner Intelligence Calendar"}
              </h3>
              <span className="border-2 border-black dark:border-white bg-emerald-300 text-black text-[10px] font-black px-2 py-0.5 uppercase tracking-widest hidden sm:inline-block">
                LIVE STATS
              </span>
            </div>
            <p className="text-xs font-bold text-zinc-600 dark:text-zinc-400 mt-1">
              {isAr
                ? "سجل زمني متكامل يرصد كثافة الإشارات، فرص السيولة، والاختراقات الفنية لكل يوم تداول."
                : "Comprehensive historical calendar tracking signal density, liquidity surges, and technical breakouts per trading day."}
            </p>
          </div>
        </div>

        {/* Month Selector Buttons */}
        <div className="flex items-center gap-2 border-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800 p-1.5 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] self-start md:self-auto">
          <button
            type="button"
            onClick={isAr ? handleNextMonth : handlePrevMonth}
            className="h-8 w-8 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 flex items-center justify-center hover:bg-zinc-200 dark:hover:bg-zinc-700 active:translate-x-[1px] active:translate-y-[1px] transition-all"
            title={isAr ? "الشهر السابق" : "Previous Month"}
          >
            {isAr ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
          <span className="font-mono font-black text-xs px-3 text-black dark:text-white min-w-[120px] text-center">
            {isAr ? `${monthNamesAr[month]} ${year}` : `${currentDate.toLocaleString("en-US", { month: "long" })} ${year}`}
          </span>
          <button
            type="button"
            onClick={isAr ? handlePrevMonth : handleNextMonth}
            className="h-8 w-8 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 flex items-center justify-center hover:bg-zinc-200 dark:hover:bg-zinc-700 active:translate-x-[1px] active:translate-y-[1px] transition-all"
            title={isAr ? "الشهر القادم" : "Next Month"}
          >
            {isAr ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* ── Category Filters (أزرار فلترة الإسكانر) ── */}
      <div className="space-y-2">
        <span className="text-[11px] font-black uppercase tracking-wider text-zinc-500 block">
          {isAr ? "فلترة نوع الإسكانر المعروض في التقويم:" : "Filter by scanner type:"}
        </span>
        <div className="flex flex-wrap gap-2.5">
          {categories.map((cat) => {
            const isSelected = selectedCategory === cat.id;
            const Icon = cat.icon;
            return (
              <button
                key={cat.id}
                type="button"
                onClick={() => setSelectedCategory(cat.id)}
                className={`h-10 px-4 border-4 border-black dark:border-white font-black text-xs uppercase tracking-wide flex items-center gap-2 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] transition-all active:translate-x-[1px] active:translate-y-[1px] ${
                  isSelected
                    ? cat.activeBg
                    : "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700"
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{isAr ? cat.nameAr : cat.nameEn}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Dynamic KPI Metrics (إحصائيات متجاوبة مع الفلتر) ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Matches for selected category */}
        <div className="border-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800/80 p-4 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)]">
          <div className="flex items-center justify-between text-zinc-500 text-[10px] font-black uppercase tracking-widest">
            <span>{isAr ? "إجمالي الفرص المرصودة" : "Total Signals"}</span>
            <Flame className="w-4 h-4 text-amber-500" />
          </div>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-3xl font-black font-mono text-black dark:text-white">
              {statsSummary.totalMatches}
            </span>
            <span className="text-xs font-bold text-zinc-500">{isAr ? "فرصة" : "signals"}</span>
          </div>
          <span className="inline-block mt-2 text-[10px] font-black text-amber-700 bg-amber-100 dark:bg-amber-950/40 px-2 py-0.5 border border-amber-400">
            {categories.find((c) => c.id === selectedCategory)?.[isAr ? "nameAr" : "nameEn"]}
          </span>
        </div>

        {/* KPI 2: Active Trading Days with Signals */}
        <div className="border-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800/80 p-4 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)]">
          <div className="flex items-center justify-between text-zinc-500 text-[10px] font-black uppercase tracking-widest">
            <span>{isAr ? "أيام الجلسات النشطة" : "Active Days"}</span>
            <Activity className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-3xl font-black font-mono text-emerald-600 dark:text-emerald-400">
              {statsSummary.daysWithSignals}
            </span>
            <span className="text-xs font-bold text-zinc-500">{isAr ? "يوم تداول" : "days"}</span>
          </div>
          <span className="inline-block mt-2 text-[10px] font-black text-emerald-700 bg-emerald-100 dark:bg-emerald-950/40 px-2 py-0.5 border border-emerald-400">
            {isAr ? "تغطية مستمرة للجلسات" : "Continuous session coverage"}
          </span>
        </div>

        {/* KPI 3: Total Executed Scans */}
        <div className="border-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800/80 p-4 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)]">
          <div className="flex items-center justify-between text-zinc-500 text-[10px] font-black uppercase tracking-widest">
            <span>{isAr ? "عمليات المسح المنفذة" : "Total Scans"}</span>
            <Clock className="w-4 h-4 text-purple-500" />
          </div>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-3xl font-black font-mono text-purple-600 dark:text-purple-400">
              {statsSummary.totalScans}
            </span>
            <span className="text-xs font-bold text-zinc-500">{isAr ? "عملية فحص" : "scans"}</span>
          </div>
          <span className="inline-block mt-2 text-[10px] font-black text-purple-700 bg-purple-100 dark:bg-purple-950/40 px-2 py-0.5 border border-purple-400">
            {isAr ? "مجدول آلي كل 15 دقيقة" : "Automated 15m intervals"}
          </span>
        </div>

        {/* KPI 4: Peak day activity */}
        <div className="border-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800/80 p-4 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)]">
          <div className="flex items-center justify-between text-zinc-500 text-[10px] font-black uppercase tracking-widest">
            <span>{isAr ? "أعلى كثافة إشارات" : "Peak Activity"}</span>
            <TrendingUp className="w-4 h-4 text-sky-500" />
          </div>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-3xl font-black font-mono text-sky-600 dark:text-sky-400">
              {statsSummary.highestSingleDayCount}
            </span>
            <span className="text-xs font-bold text-zinc-500">{isAr ? "في يوم واحد" : "in 1 day"}</span>
          </div>
          <span className="inline-block mt-2 text-[10px] font-black text-sky-700 bg-sky-100 dark:bg-sky-950/40 px-2 py-0.5 border border-sky-400 font-mono">
            {statsSummary.highestDayDate ? statsSummary.highestDayDate : "—"}
          </span>
        </div>
      </div>

      {/* ── Main Interactive Calendar Grid ── */}
      <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-6 shadow-[5px_5px_0px_rgba(0,0,0,1)] dark:shadow-[5px_5px_0px_rgba(255,255,255,1)] space-y-4">
        {/* Days of Week Header */}
        <div className="grid grid-cols-7 gap-1 sm:gap-2 text-center pb-2 border-b-4 border-black dark:border-white font-black text-xs sm:text-sm">
          {(isAr ? weekDaysAr : weekDaysEn).map((dName, idx) => {
            const isWeekend = isAr ? idx === 5 || idx === 6 : idx === 5 || idx === 6;
            return (
              <div
                key={idx}
                className={`p-2 uppercase tracking-wider ${
                  isWeekend ? "text-zinc-400 dark:text-zinc-600" : "text-black dark:text-white"
                }`}
              >
                {dName}
              </div>
            );
          })}
        </div>

        {/* Days Tiles */}
        <div className="grid grid-cols-7 gap-1 sm:gap-2">
          {calendarDays.map((cell, idx) => {
            if (!cell.isCurrentMonth) {
              return (
                <div
                  key={idx}
                  className="min-h-[85px] sm:min-h-[110px] border-2 border-dashed border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/20"
                />
              );
            }

            const dayData = cell.data;
            let displayCount = 0;
            if (dayData) {
              if (selectedCategory === "all") displayCount = dayData.totalOpportunities;
              else if (selectedCategory === "volume_surge") displayCount = dayData.volumeCount;
              else if (selectedCategory === "breakout") displayCount = dayData.breakoutCount;
              else if (selectedCategory === "rsi_oversold") displayCount = dayData.oversoldCount;
              else if (selectedCategory === "disclosures") displayCount = dayData.disclosuresCount;
            }

            const isSelected = selectedDateStr === cell.dateStr;
            const hasSignals = displayCount > 0;

            // Determine pill color depending on category & intensity
            let badgeColor = "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
            if (hasSignals) {
              if (selectedCategory === "all") badgeColor = "bg-[#FFE600] text-black border border-black";
              else if (selectedCategory === "volume_surge") badgeColor = "bg-amber-400 text-black border border-black";
              else if (selectedCategory === "breakout") badgeColor = "bg-emerald-400 text-black border border-black";
              else if (selectedCategory === "rsi_oversold") badgeColor = "bg-sky-400 text-black border border-black";
              else if (selectedCategory === "disclosures") badgeColor = "bg-purple-400 text-black border border-black";
            }

            return (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  setSelectedDateStr(cell.dateStr);
                  setIsDialogOpen(true);
                }}
                className={`min-h-[85px] sm:min-h-[110px] p-2 border-2 sm:border-4 border-black dark:border-white flex flex-col justify-between text-right transition-all group ${
                  isSelected
                    ? "bg-amber-100 dark:bg-zinc-800 ring-4 ring-black dark:ring-white scale-[1.02] shadow-[4px_4px_0px_rgba(0,0,0,1)] z-10"
                    : hasSignals
                    ? "bg-white dark:bg-zinc-900 hover:bg-zinc-50 dark:hover:bg-zinc-850 shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                    : "bg-zinc-50 dark:bg-zinc-900/60 opacity-80 hover:opacity-100"
                }`}
              >
                {/* Day Number */}
                <div className="flex items-center justify-between w-full">
                  <span
                    className={`font-black font-mono text-xs sm:text-sm ${
                      isSelected
                        ? "text-black dark:text-white underline decoration-2 font-black"
                        : "text-zinc-700 dark:text-zinc-300"
                    }`}
                  >
                    {cell.dayNum}
                  </span>
                  {dayData && (
                    <span className="text-[9px] font-mono text-zinc-400 font-bold hidden sm:inline">
                      {dayData.scansCount} {isAr ? "فحص" : "scans"}
                    </span>
                  )}
                </div>

                {/* Signals Badge */}
                <div className="mt-1 w-full">
                  {hasSignals ? (
                    <div
                      className={`w-full py-1 px-1.5 font-mono font-black text-[10px] sm:text-xs rounded-none flex items-center justify-center gap-1 ${badgeColor}`}
                    >
                      <Sparkles className="w-3 h-3 shrink-0" />
                      <span>
                        {displayCount} {isAr ? "فرصة" : ""}
                      </span>
                    </div>
                  ) : (
                    <span className="text-[10px] font-bold text-zinc-400 text-center block py-1">
                      —
                    </span>
                  )}
                </div>

                {/* Mini category pills (visible when 'all' is selected) */}
                {selectedCategory === "all" && dayData && hasSignals && (
                  <div className="hidden sm:flex items-center gap-1 justify-center mt-1 text-[8px] font-mono font-black">
                    {dayData.volumeCount > 0 && <span className="text-amber-600">⚡{dayData.volumeCount}</span>}
                    {dayData.breakoutCount > 0 && <span className="text-emerald-600">🚀{dayData.breakoutCount}</span>}
                    {dayData.oversoldCount > 0 && <span className="text-sky-600">🎯{dayData.oversoldCount}</span>}
                    {dayData.disclosuresCount > 0 && <span className="text-purple-600">📢{dayData.disclosuresCount}</span>}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Guidance Action Bar ── */}
      <div className="border-4 border-black dark:border-white bg-[#FFE600] text-black p-4 shadow-[4px_4px_0px_rgba(0,0,0,1)] flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <Sparkles className="w-5 h-5 shrink-0" />
          <span className="text-xs sm:text-sm font-black">
            {isAr
              ? "اضغط على أي يوم به إشارات لفتح نافذة منبثقة (Dialog) بتفاصيل الأسهم والفرص المكتشفة."
              : "Click any day tile with signals to open a popup dialog with detailed signals and stock breakdown."}
          </span>
        </div>
        {selectedDayData && (
          <button
            type="button"
            onClick={() => setIsDialogOpen(true)}
            className="border-2 border-black bg-black text-[#FFE600] px-4 py-2 font-mono font-black text-xs uppercase tracking-wider hover:bg-zinc-800 active:translate-x-0.5 active:translate-y-0.5 transition-all shrink-0 w-full sm:w-auto flex items-center justify-center gap-2 shadow-[2px_2px_0px_rgba(0,0,0,1)]"
          >
            <span>{isAr ? `عرض تفاصيل (${selectedDateStr})` : `Open (${selectedDateStr}) Details`}</span>
            <Info className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* ── Dialog / Modal for Selected Day Details ── */}
      {isMounted && isDialogOpen && createPortal(
        <div
          className="fixed inset-0 z-[10000] flex items-center justify-center p-3 sm:p-6"
          dir={isAr ? "rtl" : "ltr"}
        >
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/80 backdrop-blur-sm transition-opacity"
            onClick={() => setIsDialogOpen(false)}
          />

          {/* Dialog Card */}
          <div className="relative w-full max-w-5xl bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[8px_8px_0px_rgba(0,0,0,1)] dark:shadow-[8px_8px_0px_rgba(255,255,255,1)] flex flex-col max-h-[90vh] z-10 animate-in zoom-in-95 duration-150">
            {/* Dialog Header - High Contrast Neobrutal Yellow */}
            <div className="p-4 sm:p-5 border-b-4 border-black dark:border-white bg-[#FFE600] text-black flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="h-11 w-11 border-2 border-black bg-black text-[#FFE600] flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] shrink-0">
                  <CalendarIcon className="w-6 h-6" />
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-lg sm:text-xl font-black text-black uppercase tracking-tight">
                      {isAr ? "تفاصيل الفرص المرصودة ليوم:" : "Signals Ledger For Date:"}
                    </h3>
                    <span className="font-mono text-base sm:text-lg font-black text-[#FFE600] border-2 border-black bg-black px-3 py-0.5 shadow-[2px_2px_0px_rgba(0,0,0,1)]">
                      {selectedDateStr}
                    </span>
                  </div>
                  {selectedDayData && (
                    <div className="flex items-center gap-2 text-xs font-mono font-bold text-black mt-1.5 flex-wrap">
                      <span className="bg-white border-2 border-black px-2 py-0.5 shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                        ⚡ {selectedDayData.scansCount} {isAr ? "عمليات فحص" : "scans"}
                      </span>
                      <span className="bg-white border-2 border-black px-2 py-0.5 shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                        ⏱️ {Math.round(selectedDayData.avgDurationMs)}ms {isAr ? "متوسط السرعة" : "avg speed"}
                      </span>
                      <span className="bg-white border-2 border-black px-2 py-0.5 shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                        🎯 {selectedDayData.totalOpportunities} {isAr ? "إجمالي الفرص" : "total signals"}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Close Button */}
              <button
                type="button"
                onClick={() => setIsDialogOpen(false)}
                className="h-10 w-10 border-2 border-black bg-black hover:bg-rose-600 text-white flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] font-black transition-all active:translate-x-0.5 active:translate-y-0.5 self-end sm:self-auto shrink-0"
                title={isAr ? "إغلاق (Esc)" : "Close (Esc)"}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Quick Category Filter Inside Dialog */}
            <div className="px-4 sm:px-6 py-3 border-b-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 flex items-center gap-2 overflow-x-auto">
              <span className="text-xs font-black uppercase text-zinc-700 dark:text-zinc-300 shrink-0">
                {isAr ? "تصفية النوع:" : "Filter:"}
              </span>
              {categories.map((cat) => {
                const isSelected = selectedCategory === cat.id;
                const Icon = cat.icon;
                return (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => setSelectedCategory(cat.id)}
                    className={`h-8 px-3 border-2 border-black dark:border-white font-black text-xs uppercase tracking-wide flex items-center gap-1.5 shrink-0 shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,1)] transition-all ${
                      isSelected
                        ? cat.activeBg
                        : "bg-white dark:bg-zinc-900 text-zinc-800 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700"
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span>{isAr ? cat.nameAr : cat.nameEn}</span>
                  </button>
                );
              })}
            </div>

            {/* Dialog Scrollable Content */}
            <div className="p-4 sm:p-6 overflow-y-auto space-y-6 flex-1 bg-zinc-50 dark:bg-zinc-950">
              {!selectedDayData || selectedDayData.totalOpportunities === 0 ? (
                <div className="p-12 text-center border-4 border-dashed border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 font-bold text-sm text-zinc-500">
                  {isAr
                    ? "لا توجد فرص مسجلة في هذا اليوم لهذا الفلتر، أو أن اليوم كان عطلة بالبورصة المصرية."
                    : "No scanner signals recorded for this date or market was closed."}
                </div>
              ) : (
                <div className={`grid gap-5 ${selectedCategory === "all" ? "grid-cols-1 lg:grid-cols-2" : "grid-cols-1"}`}>
                  {/* Stage 1: Volume Surge */}
                  {(selectedCategory === "all" || selectedCategory === "volume_surge") && (
                    <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-4 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] space-y-3">
                      <div className="border-b-2 border-black dark:border-white pb-2.5 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-black text-sm sm:text-base flex items-center gap-2 text-amber-600 dark:text-amber-400">
                            <span className="p-1 bg-amber-100 dark:bg-amber-950/80 border border-amber-500 text-amber-600 dark:text-amber-400 shrink-0">
                              <Zap className="w-4 h-4 fill-amber-500" />
                            </span>
                            <span>{isAr ? "السيولة والتجميع (Volume Surge)" : "Volume Surge"}</span>
                          </span>
                          <span className="font-mono text-xs font-black bg-amber-400 text-black px-2.5 py-0.5 border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                            {selectedDayData.stocks.volume.length > 0 ? selectedDayData.stocks.volume.length : selectedDayData.volumeCount} {isAr ? "فرصة" : "signals"}
                          </span>
                        </div>
                        <p className="text-[10px] sm:text-xs font-mono font-bold text-zinc-600 dark:text-zinc-300">
                          {isAr ? "معيار الرصد: مضاعف السيولة rVol ≥ 2.5x مع اتجاه صاعد أو تجميع" : "Trigger: rVol ≥ 2.5x with positive/neutral price action"}
                        </p>
                      </div>
                      <div className="space-y-2.5 max-h-80 overflow-y-auto pr-1">
                        {selectedDayData.stocks.volume.length > 0 ? (
                          selectedDayData.stocks.volume.map((s, i) => (
                            <div
                              key={i}
                              className="p-3 bg-zinc-50 dark:bg-zinc-800/90 border-2 border-black dark:border-zinc-600 shadow-[2px_2px_0px_rgba(0,0,0,1)] flex flex-col gap-2"
                            >
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className="font-mono font-black text-xs text-black bg-white px-2 py-0.5 border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                                    {s.symbol}
                                  </span>
                                  <span className="font-mono font-black text-xs text-zinc-900 dark:text-white">
                                    {formatPrice(s.close)} ج.م
                                  </span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="font-mono font-black text-xs px-2 py-0.5 bg-emerald-400 text-black border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                                    +{formatPct(s.change_pct)}%
                                  </span>
                                  <span className="font-mono font-black text-xs px-2 py-0.5 bg-amber-400 text-black border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                                    {formatVol(s.r_vol)}x سيولة
                                  </span>
                                </div>
                              </div>
                              <div className="flex items-center justify-between pt-2 border-t border-zinc-200 dark:border-zinc-700/80 text-[11px] font-mono">
                                <span className="text-zinc-700 dark:text-zinc-300 flex items-center gap-1.5 font-bold">
                                  <Clock className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                                  <span>{isAr ? "وقت الإشارة:" : "Signal:"}</span>
                                  <span className="font-black text-black dark:text-white bg-zinc-200 dark:bg-zinc-700 px-1.5 py-0.5 border border-black dark:border-zinc-500">
                                    {formatSignalTime((s as any).signal_time)}
                                  </span>
                                </span>
                                <button
                                  type="button"
                                  onClick={() => setChartModalStock({
                                    symbol: s.symbol,
                                    date: selectedDateStr,
                                    signalTime: getSignalHHMM((s as any).signal_time),
                                    signalPrice: s.close,
                                    scannerType: "volume_surge"
                                  })}
                                  className="px-2.5 py-1 bg-[#FFE600] hover:bg-yellow-300 text-black border-2 border-black font-black text-[11px] flex items-center gap-1 shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-0.5 active:translate-y-0.5 transition-all"
                                  title={isAr ? "عرض شارت 15 دقيقة للجلسة وتتبع القمة" : "View 15m session chart & peak"}
                                >
                                  <BarChart2 className="w-3.5 h-3.5" />
                                  <span>{isAr ? "شارت 15 دقيقة" : "15m Chart"}</span>
                                </button>
                              </div>
                            </div>
                          ))
                        ) : (
                          <span className="text-xs text-zinc-500 font-bold block py-3 text-center">
                            {isAr ? `${selectedDayData.volumeCount} إشارات تم رصدها وإرسالها للمشتركين` : `${selectedDayData.volumeCount} signals captured`}
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Stage 2: Breakouts */}
                  {(selectedCategory === "all" || selectedCategory === "breakout") && (
                    <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-4 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] space-y-3">
                      <div className="border-b-2 border-black dark:border-white pb-2.5 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-black text-sm sm:text-base flex items-center gap-2 text-emerald-600 dark:text-emerald-300">
                            <span className="p-1 bg-emerald-100 dark:bg-emerald-950/80 border border-emerald-500 text-emerald-600 dark:text-emerald-300 shrink-0">
                              <ArrowUpRight className="w-4 h-4 stroke-[3]" />
                            </span>
                            <span>{isAr ? "الاختراقات الفنية (Breakouts)" : "Technical Breakouts"}</span>
                          </span>
                          <span className="font-mono text-xs font-black bg-emerald-400 text-black px-2.5 py-0.5 border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                            {selectedDayData.stocks.breakout.length > 0 ? selectedDayData.stocks.breakout.length : selectedDayData.breakoutCount} {isAr ? "فرصة" : "signals"}
                          </span>
                        </div>
                        <p className="text-[10px] sm:text-xs font-mono font-bold text-zinc-600 dark:text-zinc-300">
                          {isAr ? "معيار الرصد: كسر قمة 20 جلسة مع تأكيد سيولة rVol ≥ 1.5x" : "Trigger: High(20) breakout confirmed with rVol ≥ 1.5x"}
                        </p>
                      </div>
                      <div className="space-y-2.5 max-h-80 overflow-y-auto pr-1">
                        {selectedDayData.stocks.breakout.length > 0 ? (
                          selectedDayData.stocks.breakout.map((s, i) => (
                            <div
                              key={i}
                              className="p-3 bg-zinc-50 dark:bg-zinc-800/90 border-2 border-black dark:border-zinc-600 shadow-[2px_2px_0px_rgba(0,0,0,1)] flex flex-col gap-2"
                            >
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className="font-mono font-black text-xs text-black bg-white px-2 py-0.5 border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                                    {s.symbol}
                                  </span>
                                  <span className="font-mono font-black text-xs text-zinc-900 dark:text-white">
                                    {formatPrice(s.close)} ج.م
                                  </span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="font-mono font-black text-xs px-2 py-0.5 bg-emerald-400 text-black border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                                    +{formatPct(s.change_pct)}%
                                  </span>
                                  <span className="font-mono font-black text-xs px-2 py-0.5 bg-amber-400 text-black border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                                    {formatVol(s.r_vol)}x سيولة
                                  </span>
                                </div>
                              </div>
                              <div className="flex items-center justify-between pt-2 border-t border-zinc-200 dark:border-zinc-700/80 text-[11px] font-mono">
                                <span className="text-zinc-700 dark:text-zinc-300 flex items-center gap-1.5 font-bold">
                                  <Clock className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                                  <span>{isAr ? "وقت الإشارة:" : "Signal:"}</span>
                                  <span className="font-black text-black dark:text-white bg-zinc-200 dark:bg-zinc-700 px-1.5 py-0.5 border border-black dark:border-zinc-500">
                                    {formatSignalTime((s as any).signal_time)}
                                  </span>
                                </span>
                                <button
                                  type="button"
                                  onClick={() => setChartModalStock({
                                    symbol: s.symbol,
                                    date: selectedDateStr,
                                    signalTime: getSignalHHMM((s as any).signal_time),
                                    signalPrice: s.close,
                                    scannerType: "breakout"
                                  })}
                                  className="px-2.5 py-1 bg-emerald-400 hover:bg-emerald-300 text-black border-2 border-black font-black text-[11px] flex items-center gap-1 shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-0.5 active:translate-y-0.5 transition-all"
                                  title={isAr ? "عرض شارت 15 دقيقة للجلسة وتتبع القمة" : "View 15m session chart & peak"}
                                >
                                  <BarChart2 className="w-3.5 h-3.5" />
                                  <span>{isAr ? "شارت 15 دقيقة" : "15m Chart"}</span>
                                </button>
                              </div>
                            </div>
                          ))
                        ) : (
                          <span className="text-xs text-zinc-500 font-bold block py-3 text-center">
                            {isAr ? `${selectedDayData.breakoutCount} اختراقات تم رصدها` : `${selectedDayData.breakoutCount} breakouts captured`}
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Stage 3: Oversold */}
                  {(selectedCategory === "all" || selectedCategory === "rsi_oversold") && (
                    <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-4 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] space-y-3">
                      <div className="border-b-2 border-black dark:border-white pb-2.5 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-black text-sm sm:text-base flex items-center gap-2 text-sky-600 dark:text-sky-300">
                            <span className="p-1 bg-sky-100 dark:bg-sky-950/80 border border-sky-500 text-sky-600 dark:text-sky-300 shrink-0">
                              <Target className="w-4 h-4 stroke-[2.5]" />
                            </span>
                            <span>{isAr ? "التشبع البيعي (RSI Oversold)" : "RSI Oversold"}</span>
                          </span>
                          <span className="font-mono text-xs font-black bg-sky-400 text-black px-2.5 py-0.5 border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                            {selectedDayData.stocks.oversold.length > 0 ? selectedDayData.stocks.oversold.length : selectedDayData.oversoldCount} {isAr ? "فرصة" : "signals"}
                          </span>
                        </div>
                        <p className="text-[10px] sm:text-xs font-mono font-bold text-zinc-600 dark:text-zinc-300">
                          {isAr ? "معيار الرصد: مؤشر القوة RSI(14) ≤ 30 نقطة قرب دعوم ارتدادية" : "Trigger: RSI(14) ≤ 30 points near historical support floor"}
                        </p>
                      </div>
                      <div className="space-y-2.5 max-h-80 overflow-y-auto pr-1">
                        {selectedDayData.stocks.oversold.length > 0 ? (
                          selectedDayData.stocks.oversold.map((s, i) => (
                            <div
                              key={i}
                              className="p-3 bg-zinc-50 dark:bg-zinc-800/90 border-2 border-black dark:border-zinc-600 shadow-[2px_2px_0px_rgba(0,0,0,1)] flex flex-col gap-2"
                            >
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className="font-mono font-black text-xs text-black bg-white px-2 py-0.5 border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                                    {s.symbol}
                                  </span>
                                  <span className="font-mono font-black text-xs text-zinc-900 dark:text-white">
                                    {formatPrice(s.close)} ج.م
                                  </span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="font-mono font-black text-xs px-2 py-0.5 bg-sky-400 text-black border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                                    RSI: {formatRsi(s.rsi_14)}
                                  </span>
                                  <span className={`font-mono font-black text-xs px-2 py-0.5 border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)] text-black ${
                                    s.change_pct >= 0 ? "bg-emerald-400" : "bg-rose-400"
                                  }`}>
                                    {s.change_pct >= 0 ? `+${formatPct(s.change_pct)}%` : `${formatPct(s.change_pct)}%`}
                                  </span>
                                </div>
                              </div>
                              <div className="flex items-center justify-between pt-2 border-t border-zinc-200 dark:border-zinc-700/80 text-[11px] font-mono">
                                <span className="text-zinc-700 dark:text-zinc-300 flex items-center gap-1.5 font-bold">
                                  <Clock className="w-3.5 h-3.5 text-sky-500 shrink-0" />
                                  <span>{isAr ? "وقت الإشارة:" : "Signal:"}</span>
                                  <span className="font-black text-black dark:text-white bg-zinc-200 dark:bg-zinc-700 px-1.5 py-0.5 border border-black dark:border-zinc-500">
                                    {formatSignalTime((s as any).signal_time)}
                                  </span>
                                </span>
                                <button
                                  type="button"
                                  onClick={() => setChartModalStock({
                                    symbol: s.symbol,
                                    date: selectedDateStr,
                                    signalTime: getSignalHHMM((s as any).signal_time),
                                    signalPrice: s.close,
                                    scannerType: "rsi_oversold"
                                  })}
                                  className="px-2.5 py-1 bg-sky-400 hover:bg-sky-300 text-black border-2 border-black font-black text-[11px] flex items-center gap-1 shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-0.5 active:translate-y-0.5 transition-all"
                                  title={isAr ? "عرض شارت 15 دقيقة للجلسة وتتبع القمة" : "View 15m session chart & peak"}
                                >
                                  <BarChart2 className="w-3.5 h-3.5" />
                                  <span>{isAr ? "شارت 15 دقيقة" : "15m Chart"}</span>
                                </button>
                              </div>
                            </div>
                          ))
                        ) : (
                          <span className="text-xs text-zinc-500 font-bold block py-3 text-center">
                            {isAr ? `${selectedDayData.oversoldCount} فرص ارتداد قاع` : `${selectedDayData.oversoldCount} oversold bounces`}
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Stage 4: Disclosures */}
                  {(selectedCategory === "all" || selectedCategory === "disclosures") && (
                    <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-4 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] space-y-3">
                      <div className="border-b-2 border-black dark:border-white pb-2.5 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-black text-sm sm:text-base flex items-center gap-2 text-purple-600 dark:text-purple-300">
                            <span className="p-1 bg-purple-100 dark:bg-purple-950/80 border border-purple-500 text-purple-600 dark:text-purple-300 shrink-0">
                              <Newspaper className="w-4 h-4 stroke-[2.5]" />
                            </span>
                            <span>{isAr ? "الإفصاحات الرسمية (Disclosures)" : "Official Disclosures"}</span>
                          </span>
                          <span className="font-mono text-xs font-black bg-purple-400 text-black px-2.5 py-0.5 border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                            {selectedDayData.stocks.disclosures.length > 0 ? selectedDayData.stocks.disclosures.length : selectedDayData.disclosuresCount} {isAr ? "إفصاح" : "items"}
                          </span>
                        </div>
                        <p className="text-[10px] sm:text-xs font-mono font-bold text-zinc-600 dark:text-zinc-300">
                          {isAr ? "معيار الرصد: بث حي فوري لإعلانات وقرارات الشركات بالبورصة" : "Trigger: Live EGX algorithmic disclosure sync & filtering"}
                        </p>
                      </div>
                      <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                        {selectedDayData.stocks.disclosures.length > 0 ? (
                          selectedDayData.stocks.disclosures.map((d, i) => (
                            <div
                              key={i}
                              className="p-3 bg-zinc-50 dark:bg-zinc-800/90 border-2 border-black dark:border-zinc-600 shadow-[2px_2px_0px_rgba(0,0,0,1)] space-y-1.5"
                            >
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] font-mono font-black bg-purple-400 text-black border border-black px-2 py-0.5 shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                                  {d.symbol || (isAr ? "إفصاح رسمي" : "Official Disclosure")}
                                </span>
                              </div>
                              <p className="text-xs font-black text-zinc-900 dark:text-zinc-100 leading-snug">
                                {d.title}
                              </p>
                            </div>
                          ))
                        ) : (
                          <span className="text-xs text-zinc-500 font-bold block py-3 text-center">
                            {isAr ? `${selectedDayData.disclosuresCount} إفصاحات رسمية مرصودة` : `${selectedDayData.disclosuresCount} official disclosures`}
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Dialog Footer */}
            <div className="p-4 border-t-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 flex items-center justify-between text-black dark:text-white">
              <span className="text-xs font-mono font-bold text-zinc-600 dark:text-zinc-400">
                {isAr ? "اضغط Esc أو زر الإغلاق للعودة للتقويم" : "Press Esc or close button to return to calendar"}
              </span>
              <button
                type="button"
                onClick={() => setIsDialogOpen(false)}
                className="px-6 py-2 border-2 border-black bg-rose-500 hover:bg-rose-600 text-white font-black text-xs uppercase shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-0.5 active:translate-y-0.5 transition-all"
              >
                {isAr ? "إغلاق النافذة" : "Close Dialog"}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

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
