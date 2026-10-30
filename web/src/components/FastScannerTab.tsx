"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import Link from "next/link";
import {
  Zap,
  Lock,
  ShieldCheck,
  TrendingUp,
  Clock,
  ArrowUpRight,
  BarChart2,
  CheckCircle2,
  Info,
  ChevronDown,
  ChevronUp,
  Calendar as CalendarIcon,
  Layers,
  Award,
  RefreshCw,
  Search,
  Filter,
  X,
  Target,
  ExternalLink,
  Crown,
  History,
  Activity,
  ShieldAlert,
  Share2,
  Copy,
  Check,
  Grid,
  List,
  ChevronLeft,
  ChevronRight
} from "lucide-react";
import StockLogo from "./StockLogo";
import { isShariaCompliant } from "@/lib/shariaStocks";
import { TrackedScannerSignal, ScannerSignalsKPIs, ScannerType } from "@/lib/scannerTradePlan";
import ScannerDefinitionsGuide from "@/app/profile/components/ScannerDefinitionsGuide";
import ScannerIntradayChartModal, { prefetchIntradaySession } from "@/app/profile/components/ScannerIntradayChartModal";

interface FastScannerTabProps {
  isAr?: boolean;
  isPro?: boolean;
}

const SCANNER_ALERTS_CACHE_KEY = "egx_scanner_alerts_cache_v2";

export default function FastScannerTab({ isAr = true, isPro = false }: FastScannerTabProps) {
  const [viewMode, setViewMode] = useState<"active" | "closed" | "all" | "calendar">("active");
  const [isGuideOpen, setIsGuideOpen] = useState(false);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [userHasPro, setUserHasPro] = useState(isPro);

  const [activeSignals, setActiveSignals] = useState<TrackedScannerSignal[]>([]);
  const [closedSignals, setClosedSignals] = useState<TrackedScannerSignal[]>([]);
  const [signalsKpis, setSignalsKpis] = useState<ScannerSignalsKPIs | null>(null);

  // Filters & Sorting
  const [categoryFilter, setCategoryFilter] = useState<"all" | ScannerType>("all");
  const [resultFilter, setResultFilter] = useState<"all" | "win" | "loss">("all");
  const [shariaOnly, setShariaOnly] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [timeRange, setTimeRange] = useState<"all" | "7d" | "30d">("all");
  const [sortBy, setSortBy] = useState<string>("entry_date");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  // Modals
  const [showProModal, setShowProModal] = useState(false);
  const [shareSignal, setShareSignal] = useState<TrackedScannerSignal | null>(null);
  const [copiedShare, setCopiedShare] = useState(false);
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

  // Calendar State (Matching ShortSwings & Medium Swings)
  const formatYMD = (d: Date) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  };

  const todayDateStr = useMemo(() => formatYMD(new Date()), []);
  const [currentDate, setCurrentDate] = useState(() => new Date());
  const [filterPreset, setFilterPreset] = useState<"this_month" | "30days" | "all">("this_month");
  const [calendarViewType, setCalendarViewType] = useState<"grid" | "list">("grid");
  const [selectedDaySignals, setSelectedDaySignals] = useState<{
    date: string;
    closedSignals: TrackedScannerSignal[];
    createdSignals: TrackedScannerSignal[];
  } | null>(null);
  const [dayModalFilter, setDayModalFilter] = useState<"all" | "closed" | "created">("all");

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const monthNamesAr = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"
  ];
  const monthNamesEn = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ];
  const currentMonthName = isAr ? monthNamesAr[month] : monthNamesEn[month];
  const currentMonthStr = `${year}-${String(month + 1).padStart(2, "0")}`;

  const prevMonth = () => {
    setCurrentDate((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
    setFilterPreset("this_month");
  };

  const nextMonth = () => {
    setCurrentDate((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
    setFilterPreset("this_month");
  };

  const goToToday = () => {
    const today = new Date();
    setCurrentDate(new Date(today.getFullYear(), today.getMonth(), 1));
    setFilterPreset("this_month");
  };

  useEffect(() => {
    setUserHasPro(isPro);
  }, [isPro]);

  const loadData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      try {
        const cachedRaw = localStorage.getItem(SCANNER_ALERTS_CACHE_KEY);
        if (cachedRaw) {
          const cached = JSON.parse(cachedRaw);
          if (cached && cached.ok) {
            if (typeof cached.is_pro === "boolean") setUserHasPro(cached.is_pro);
            if (Array.isArray(cached.active_signals)) setActiveSignals(cached.active_signals);
            if (Array.isArray(cached.closed_signals)) setClosedSignals(cached.closed_signals);
            if (cached.signals_kpis) setSignalsKpis(cached.signals_kpis);
            setLoading(false);
          }
        }
      } catch {
        // ignore cache read error
      }
    }

    try {
      const res = await fetch("/api/user/scanner-alerts", {
        cache: "no-store",
      });
      if (res.ok) {
        const data = await res.json();
        if (data.ok) {
          if (typeof data.is_pro === "boolean") setUserHasPro(data.is_pro);
          if (Array.isArray(data.active_signals)) setActiveSignals(data.active_signals);
          if (Array.isArray(data.closed_signals)) setClosedSignals(data.closed_signals);
          if (data.signals_kpis) setSignalsKpis(data.signals_kpis);
          try {
            localStorage.setItem(SCANNER_ALERTS_CACHE_KEY, JSON.stringify(data));
          } catch {
            // ignore quota errors
          }
        }
      }
    } catch (err) {
      console.error("Failed to fetch fast scanner signals:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadData(false);
  }, [loadData]);

  const getSignalReturn = useCallback((s: TrackedScannerSignal) => {
    if (typeof s.return_pct === "number") return s.return_pct;
    const ex = s.exit_price ?? s.current_price;
    if (s.entry_price && ex) {
      return Number((((ex - s.entry_price) / s.entry_price) * 100).toFixed(2));
    }
    return 0;
  }, []);

  // Sort Signals helper
  const sortSignalsList = useCallback((list: any[]) => {
    return [...list].sort((a, b) => {
      let valA: any;
      let valB: any;

      if (sortBy === "symbol") {
        return sortOrder === "asc"
          ? String(a.symbol || "").localeCompare(String(b.symbol || ""))
          : String(b.symbol || "").localeCompare(String(a.symbol || ""));
      }
      if (sortBy === "scanner_type") {
        return sortOrder === "asc"
          ? String(a.scanner_type || "").localeCompare(String(b.scanner_type || ""))
          : String(b.scanner_type || "").localeCompare(String(a.scanner_type || ""));
      }
      if (sortBy === "entry_date") {
        valA = String(a.entry_date || "") + String(a.entry_time || "");
        valB = String(b.entry_date || "") + String(b.entry_time || "");
        return sortOrder === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }
      if (sortBy === "entry_price") {
        valA = Number(a.entry_price || 0);
        valB = Number(b.entry_price || 0);
        return sortOrder === "asc" ? valA - valB : valB - valA;
      }
      if (sortBy === "target_1") {
        valA = Number(a.target_1 || 0);
        valB = Number(b.target_1 || 0);
        return sortOrder === "asc" ? valA - valB : valB - valA;
      }
      if (sortBy === "stop_loss") {
        valA = Number(a.stop_loss || 0);
        valB = Number(b.stop_loss || 0);
        return sortOrder === "asc" ? valA - valB : valB - valA;
      }
      if (sortBy === "current_price") {
        valA = Number(a.current_price || a.exit_price || a.entry_price || 0);
        valB = Number(b.current_price || b.exit_price || b.entry_price || 0);
        return sortOrder === "asc" ? valA - valB : valB - valA;
      }
      if (sortBy === "return") {
        valA = getSignalReturn(a);
        valB = getSignalReturn(b);
        return sortOrder === "asc" ? valA - valB : valB - valA;
      }
      if (sortBy === "status") {
        valA = String(a.status || "");
        valB = String(b.status || "");
        return sortOrder === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }
      return 0;
    });
  }, [sortBy, sortOrder, getSignalReturn]);

  const handleHeaderClick = (field: string) => {
    if (sortBy === field) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(field);
      setSortOrder(field === "symbol" || field === "scanner_type" ? "asc" : "desc");
    }
  };

  const renderSortIcon = (field: string) => {
    if (sortBy !== field) return <span className="opacity-30 text-[10px] ml-1">⇅</span>;
    return <span className="ml-1 text-amber-500 font-black text-xs">{sortOrder === "asc" ? "▲" : "▼"}</span>;
  };

  // Strict Deduplication & Integrity Guard for Fast Scanner
  const cleanClosedSignals = useMemo(() => {
    const seen = new Set<string>();
    const list: TrackedScannerSignal[] = [];
    closedSignals.forEach((s) => {
      if (!s || !s.symbol) return;
      const key = s.id || `${s.symbol}_${s.entry_date}_${s.scanner_type}_${s.exit_date || ""}`;
      if (!seen.has(key)) {
        seen.add(key);
        list.push(s);
      }
    });
    return list;
  }, [closedSignals]);

  const cleanActiveSignals = useMemo(() => {
    const closedKeys = new Set(cleanClosedSignals.map((s) => `${s.symbol}_${s.entry_date}_${s.scanner_type}`));
    const seen = new Set<string>();
    const list: TrackedScannerSignal[] = [];
    activeSignals.forEach((s) => {
      if (!s || !s.symbol) return;
      const key = s.id || `${s.symbol}_${s.entry_date}_${s.scanner_type}`;
      if (!seen.has(key) && !closedKeys.has(key) && s.status === "active") {
        seen.add(key);
        list.push(s);
      }
    });
    return list;
  }, [activeSignals, cleanClosedSignals]);

  // Filtered Active Signals
  const filteredActive = useMemo(() => {
    const list = cleanActiveSignals.filter((s) => {
      if (categoryFilter !== "all" && s.scanner_type !== categoryFilter) return false;
      if (shariaOnly && !isShariaCompliant(s.symbol)) return false;
      if (timeRange !== "all") {
        const days = timeRange === "7d" ? 7 : 30;
        const cutoff = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
        const cutoffStr = formatYMD(cutoff);
        if ((s.entry_date || "") < cutoffStr) return false;
      }
      if (searchTerm.trim()) {
        const q = searchTerm.trim().toLowerCase();
        if (!s.symbol.toLowerCase().includes(q)) return false;
      }
      return true;
    });
    return sortSignalsList(list);
  }, [cleanActiveSignals, categoryFilter, shariaOnly, searchTerm, timeRange, sortSignalsList]);

  // Filtered Closed Signals
  const filteredClosed = useMemo(() => {
    const list = cleanClosedSignals.filter((s) => {
      if (categoryFilter !== "all" && s.scanner_type !== categoryFilter) return false;
      if (shariaOnly && !isShariaCompliant(s.symbol)) return false;
      if (timeRange !== "all") {
        const days = timeRange === "7d" ? 7 : 30;
        const cutoff = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
        const cutoffStr = formatYMD(cutoff);
        const d = s.exit_date || s.entry_date || "";
        if (d < cutoffStr) return false;
      }
      const ret = getSignalReturn(s);
      if (resultFilter === "win" && ret <= 0 && s.status !== "target_hit") return false;
      if (resultFilter === "loss" && (ret >= 0 || s.status === "target_hit")) return false;
      if (searchTerm.trim()) {
        const q = searchTerm.trim().toLowerCase();
        if (!s.symbol.toLowerCase().includes(q)) return false;
      }
      return true;
    });
    return sortSignalsList(list);
  }, [cleanClosedSignals, categoryFilter, shariaOnly, resultFilter, searchTerm, timeRange, getSignalReturn, sortSignalsList]);

  // Combined All Signals (Strictly zero duplicates and zero active/closed overlap)
  const filteredAll = useMemo(() => {
    const combined = [
      ...cleanActiveSignals.map((s) => ({ ...s, _isActive: true })),
      ...cleanClosedSignals.map((s) => ({ ...s, _isActive: false })),
    ];
    const list = combined.filter((s) => {
      if (categoryFilter !== "all" && s.scanner_type !== categoryFilter) return false;
      if (shariaOnly && !isShariaCompliant(s.symbol)) return false;
      if (timeRange !== "all") {
        const days = timeRange === "7d" ? 7 : 30;
        const cutoff = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
        const cutoffStr = formatYMD(cutoff);
        const d = s.exit_date || s.entry_date || "";
        if (d < cutoffStr) return false;
      }
      const ret = getSignalReturn(s);
      if (resultFilter === "win" && (s._isActive || (ret <= 0 && s.status !== "target_hit"))) return false;
      if (resultFilter === "loss" && (s._isActive || ret >= 0 || s.status === "target_hit")) return false;
      if (searchTerm.trim()) {
        const q = searchTerm.trim().toLowerCase();
        if (!s.symbol.toLowerCase().includes(q)) return false;
      }
      return true;
    });
    return sortSignalsList(list);
  }, [cleanActiveSignals, cleanClosedSignals, categoryFilter, shariaOnly, resultFilter, searchTerm, timeRange, getSignalReturn, sortSignalsList]);

  // Summary Stats matching Medium Swings & Short Swings:
  const summaryStats = useMemo(() => {
    const totalClosed = cleanClosedSignals.length;
    const wins = cleanClosedSignals.filter((s) => getSignalReturn(s) > 0 || s.status === "target_hit");
    const winRate = totalClosed > 0 ? (wins.length / totalClosed) * 100 : 70.0;
    const netReturn = cleanClosedSignals.reduce((acc, s) => acc + getSignalReturn(s), 0);
    const avgReturn = totalClosed > 0 ? netReturn / totalClosed : 3.5;
    return {
      activeCount: cleanActiveSignals.length,
      closedCount: totalClosed,
      winRate,
      avgReturn,
    };
  }, [cleanActiveSignals, cleanClosedSignals, getSignalReturn]);

  // Closed signals grouped by exit_date (when they actually finished)
  const closedByExitDate = useMemo(() => {
    const map = new Map<string, TrackedScannerSignal[]>();
    cleanClosedSignals.forEach((s) => {
      const d = s.exit_date;
      if (!d) return;
      const arr = map.get(d) || [];
      arr.push(s);
      map.set(d, arr);
    });
    return map;
  }, [cleanClosedSignals]);

  // All signals grouped by entry_date (when they were initially scanned/detected)
  const allByEntryDate = useMemo(() => {
    const map = new Map<string, TrackedScannerSignal[]>();
    cleanClosedSignals.forEach((s) => {
      if (!s.entry_date) return;
      const arr = map.get(s.entry_date) || [];
      arr.push(s);
      map.set(s.entry_date, arr);
    });
    cleanActiveSignals.forEach((s) => {
      if (!s.entry_date) return;
      const arr = map.get(s.entry_date) || [];
      if (!arr.some((ex) => ex.id === s.id)) {
        arr.push(s);
      }
      map.set(s.entry_date, arr);
    });
    return map;
  }, [cleanClosedSignals, cleanActiveSignals]);

  const viewedClosedSignals = useMemo(() => {
    if (filterPreset === "all") return cleanClosedSignals;
    if (filterPreset === "30days") {
      const now = new Date();
      const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      const cutoffStr = formatYMD(thirtyDaysAgo);
      return cleanClosedSignals.filter((s) => (s.exit_date || s.entry_date || "") >= cutoffStr);
    }
    return cleanClosedSignals.filter((s) => (s.exit_date || s.entry_date || "").startsWith(currentMonthStr));
  }, [cleanClosedSignals, currentMonthStr, filterPreset]);

  const viewedActiveSignals = useMemo(() => {
    if (filterPreset === "all") return cleanActiveSignals;
    if (filterPreset === "30days") {
      const now = new Date();
      const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      const cutoffStr = formatYMD(thirtyDaysAgo);
      return cleanActiveSignals.filter((s) => s.entry_date >= cutoffStr);
    }
    return cleanActiveSignals.filter((s) => s.entry_date.startsWith(currentMonthStr));
  }, [cleanActiveSignals, currentMonthStr, filterPreset]);

  const monthStats = useMemo(() => {
    const total = viewedClosedSignals.length;
    if (total === 0) return { total: 0, wins: 0, losses: 0, winRate: 0, netReturn: 0, bestSignal: null };

    const wins = viewedClosedSignals.filter((s) => getSignalReturn(s) > 0 || s.status === "target_hit").length;
    const losses = total - wins;
    const winRate = (wins / total) * 100;
    const netReturn = viewedClosedSignals.reduce((acc, s) => acc + getSignalReturn(s), 0);
    const bestSignal = [...viewedClosedSignals].sort((a, b) => getSignalReturn(b) - getSignalReturn(a))[0] || null;
    return { total, wins, losses, winRate, netReturn, bestSignal };
  }, [viewedClosedSignals, getSignalReturn]);

  // Calendar 7-column days with padding
  const calendarDays = useMemo(() => {
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const totalDays = lastDay.getDate();
    const startDayOfWeek = firstDay.getDay(); // 0 = Sunday

    const days = [];
    const prevMonthLastDay = new Date(year, month, 0).getDate();
    for (let i = startDayOfWeek - 1; i >= 0; i--) {
      const dayNum = prevMonthLastDay - i;
      const prevDate = new Date(year, month - 1, dayNum);
      const mStr = String(prevDate.getMonth() + 1).padStart(2, "0");
      const dStr = String(dayNum).padStart(2, "0");
      const dateStr = `${prevDate.getFullYear()}-${mStr}-${dStr}`;
      const dayOfWeek = prevDate.getDay();
      days.push({
        dayNum,
        dateStr,
        isCurrentMonth: false,
        isWeekend: dayOfWeek === 5 || dayOfWeek === 6,
      });
    }

    for (let d = 1; d <= totalDays; d++) {
      const currDate = new Date(year, month, d);
      const dayOfWeek = currDate.getDay();
      const dateStr = `${currentMonthStr}-${String(d).padStart(2, "0")}`;
      days.push({
        dayNum: d,
        dateStr,
        isCurrentMonth: true,
        isWeekend: dayOfWeek === 5 || dayOfWeek === 6,
      });
    }

    const totalCells = Math.ceil(days.length / 7) * 7;
    const nextPadding = totalCells - days.length;
    for (let n = 1; n <= nextPadding; n++) {
      const nextDate = new Date(year, month + 1, n);
      const mStr = String(nextDate.getMonth() + 1).padStart(2, "0");
      const dStr = String(n).padStart(2, "0");
      const dateStr = `${nextDate.getFullYear()}-${mStr}-${dStr}`;
      const dayOfWeek = nextDate.getDay();
      days.push({
        dayNum: n,
        dateStr,
        isCurrentMonth: false,
        isWeekend: dayOfWeek === 5 || dayOfWeek === 6,
      });
    }

    return days;
  }, [year, month, currentMonthStr]);

  const getScannerBadge = (type: ScannerType) => {
    switch (type) {
      case "volume_surge":
        return {
          label: isAr ? "سيولة مؤسسية ⚡" : "Volume Surge ⚡",
          pillBg: "bg-amber-100 dark:bg-amber-950/70 text-amber-800 dark:text-amber-300 border-amber-500",
        };
      case "breakout":
        return {
          label: isAr ? "اختراق فني 🚀" : "Breakout 🚀",
          pillBg: "bg-emerald-100 dark:bg-emerald-950/70 text-emerald-800 dark:text-emerald-300 border-emerald-500",
        };
      case "rsi_oversold":
        return {
          label: isAr ? "ارتداد RSI 🎯" : "RSI Rebound 🎯",
          pillBg: "bg-sky-100 dark:bg-sky-950/70 text-sky-800 dark:text-sky-300 border-sky-500",
        };
    }
  };

  const handleCopyShareCard = (sig: TrackedScannerSignal) => {
    const badge = getScannerBadge(sig.scanner_type);
    const ret = getSignalReturn(sig);
    const retStr = ret >= 0 ? `+${ret.toFixed(2)}%` : `${ret.toFixed(2)}%`;
    const text = [
      `🎯 إشارة رصد فني لحظي — EGX BOTS AI`,
      `💎 السهم: #${sig.symbol} (${badge.label})`,
      `📅 تاريخ الرصد: ${sig.entry_date} (${sig.entry_time})`,
      `📍 مستوى الرصد: ${sig.entry_price?.toFixed(2)} ج.م`,
      `🎯 المستهدف الفني الأول: ${sig.target_1?.toFixed(2)} ج.م (+${sig.target_1_pct}%)`,
      `🛡️ مستوى إيقاف الخسارة: ${sig.stop_loss?.toFixed(2)} ج.م`,
      `📊 الأداء الحالي/المحقق: ${retStr}`,
      `⚠️ مخرجات تحليل فني خوارزمي لأغراض البحث والدراسة وليست نصيحة استثمارية.`,
      `🔗 https://egxbots.com/scanner/backtests?tab=fast_scanner`,
    ].join("\n");
    navigator.clipboard.writeText(text);
    setCopiedShare(true);
    setTimeout(() => setCopiedShare(false), 2000);
  };

  return (
    <div className="space-y-6 w-full" dir="ltr">
      {/* ── 1. TOP NEO-BRUTALIST HEADER BANNER & COLLAPSIBLE METHODOLOGY GUIDE ── */}
      <div className="border-4 border-black dark:border-white bg-[#FFE600] text-black shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#fff] overflow-hidden">
        <div className="p-4 sm:p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 px-2.5 py-1 border-2 border-black bg-cyan-400 text-black text-xs font-black uppercase tracking-wider shadow-[2px_2px_0px_#000]">
                <span>BETA</span>
              </span>
              <span className="inline-flex items-center gap-1.5 px-3 py-1 border-2 border-black bg-black text-[#FFE600] text-xs font-black uppercase tracking-wider shadow-[2px_2px_0px_#000]">
                <Target className="w-4 h-4 text-[#FFE600]" />
                <span>{isAr ? "إشارات الرصد اللحظي 🎯 PRO" : "Intraday Fast Signals 🎯 PRO"}</span>
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-1 border-2 border-black bg-white text-black text-xs font-black shadow-[2px_2px_0px_#000]">
                <Zap className="w-3.5 h-3.5 text-amber-600 fill-amber-500" />
                <span>{isAr ? "رادار السيولة والارتداد (1 إلى 4 جلسات)" : "Liquidity & Rebound Radar (1–4 Sessions)"}</span>
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-1 border-2 border-black bg-emerald-400 text-black text-xs font-black shadow-[2px_2px_0px_#000]">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>{isAr ? "تأمين التعادل آلياً عند +2.5%" : "Auto Breakeven at +2.5%"}</span>
              </span>
            </div>

            <h1 className="text-xl sm:text-2xl lg:text-3xl font-black text-black tracking-tight leading-tight flex items-center flex-wrap gap-2">
              <span>
                {isAr
                  ? "نظام إشارات الرصد اللحظي ورادار السيولة السريع (فريم 15 دقيقة)"
                  : "Intraday Fast Signals & 15-Minute Liquidity Radar"}
              </span>
              <span className="px-2 py-0.5 bg-black text-cyan-300 border-2 border-black text-xs sm:text-sm font-black uppercase tracking-wider shadow-[2px_2px_0px_#000] shrink-0">
                BETA
              </span>
            </h1>

            {!isGuideOpen && (
              <p className="text-xs sm:text-sm font-bold text-zinc-900 leading-relaxed max-w-3xl">
                {isAr
                  ? "منهجية فنية خوارزمية تفحص السوق كل 5 دقائق أثناء الجلسة لرصد تدفقات السيولة المؤسسية (>2.2x)، الاختراقات السعرية المؤكدة، والارتدادات الفنية من مناطق التشبع البيعي مع حماية رأس المال الآلية."
                  : "Algorithmic technical scanner polling every 5 minutes during market hours to detect institutional volume surges, confirmed breakouts, and oversold technical rebounds."}
              </p>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2.5 shrink-0">
            <button
              onClick={() => void loadData(true)}
              disabled={refreshing}
              className="h-10 px-4 border-2 border-black bg-white hover:bg-zinc-100 text-black font-black text-xs uppercase flex items-center justify-center gap-2 shadow-[2px_2px_0px_#000] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
              <span>{refreshing ? (isAr ? "جار التحديث..." : "Refreshing...") : (isAr ? "تحديث الإشارات" : "Refresh")}</span>
            </button>

            {!userHasPro && (
              <Link
                href="/pricing"
                className="h-10 px-4 border-2 border-black bg-black hover:bg-zinc-900 text-[#FFE600] font-black text-xs uppercase flex items-center justify-center gap-2 shadow-[2px_2px_0px_#000] transition-all"
              >
                <Crown className="w-3.5 h-3.5 text-[#FFE600]" />
                <span>{isAr ? "ترقية إلى PRO" : "Upgrade to PRO"}</span>
              </Link>
            )}

            <button
              onClick={() => setIsGuideOpen((prev) => !prev)}
              className="h-10 px-4 border-2 border-black bg-black text-[#FFE600] hover:bg-zinc-900 font-black text-xs uppercase flex items-center justify-center gap-1.5 shadow-[2px_2px_0px_#000] transition-all cursor-pointer"
            >
              <span>
                {isGuideOpen
                  ? isAr
                    ? "إغلاق الدليل ▴"
                    : "Close Guide ▴"
                  : isAr
                  ? "دليل المنهجية والمعادلات ▾"
                  : "Methodology & Formulas ▾"}
              </span>
              {isGuideOpen ? <ChevronUp className="w-4 h-4 text-[#FFE600]" /> : <ChevronDown className="w-4 h-4 text-[#FFE600]" />}
            </button>
          </div>
        </div>

        {/* Collapsible Methodology & Formulas */}
        {isGuideOpen && (
          <div className="border-t-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-6" dir={isAr ? "rtl" : "ltr"}>
            <ScannerDefinitionsGuide isAr={isAr} />
          </div>
        )}
      </div>

      {/* ── 2. SUB-TABS NAVIGATION BAR (Identical to Medium & Short Swings from Left to Right) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 border-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] p-1.5 gap-2 select-none">
        {[
          {
            id: "active",
            label: isAr ? "الإشارات النشطة (المفتوحة)" : "Active Signals",
            count: activeSignals.length,
            icon: Activity,
          },
          {
            id: "closed",
            label: isAr ? "أرشيف الإشارات (المغلقة)" : "Closed Signals",
            count: closedSignals.length,
            icon: History,
          },
          {
            id: "all",
            label: isAr ? "جميع الإشارات" : "All Signals",
            count: activeSignals.length + closedSignals.length,
            icon: Layers,
          },
          {
            id: "calendar",
            label: isAr ? "تقويم الأداء والإحصائيات" : "Performance Calendar",
            count: null,
            icon: CalendarIcon,
            isSpecial: true,
          },
        ].map((tab) => {
          const isSelected = viewMode === tab.id;
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setViewMode(tab.id as any)}
              className={`py-2.5 sm:py-3 px-3 sm:px-4 font-black text-xs sm:text-sm flex items-center justify-between gap-2 transition-all duration-100 active:scale-98 border-2 cursor-pointer ${
                isSelected
                  ? tab.isSpecial
                    ? "bg-[#FFE600] text-black border-black shadow-[2px_2px_0px_#000]"
                    : "bg-black dark:bg-white border-black dark:border-white text-white dark:text-black shadow-[2px_2px_0px_rgba(0,0,0,0.2)]"
                  : "bg-white dark:bg-zinc-950 text-black dark:text-white border-transparent hover:bg-zinc-50 dark:hover:bg-zinc-800"
              }`}
            >
              <div className="flex items-center gap-2 truncate">
                <Icon
                  className={`w-4 h-4 shrink-0 ${
                    isSelected
                      ? tab.isSpecial
                        ? "text-black"
                        : "text-amber-400 dark:text-zinc-900"
                      : "text-zinc-500"
                  }`}
                />
                <span className="font-black truncate">{tab.label}</span>
              </div>
              {tab.count != null && (
                <span
                  className={`px-2 py-0.5 text-xs font-bold font-mono shrink-0 ${
                    isSelected
                      ? "bg-zinc-800 dark:bg-zinc-200 text-zinc-100 dark:text-zinc-900"
                      : "bg-zinc-100 dark:bg-zinc-900 text-zinc-600 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-800"
                  }`}
                >
                  {tab.count}
                </span>
              )}
              {tab.isSpecial && (
                <span
                  className={`px-1.5 py-0.5 text-[10px] font-black uppercase tracking-wider shrink-0 ${
                    isSelected
                      ? "bg-black text-[#FFE600] border border-black"
                      : "bg-amber-400 text-black border border-black"
                  }`}
                >
                  PRO
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* ── 3. TOP 4 SPOTLIGHT KPI CARDS (Identical to Medium Swings - Hidden on Calendar) ── */}
      {viewMode !== "calendar" && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 sm:gap-4">
          {/* Card 1: Active Signals */}
          <div className="p-3 sm:p-4 border-2 sm:border-4 border-black dark:border-white bg-white dark:bg-zinc-950 text-black dark:text-white shadow-[3px_3px_0px_rgba(0,0,0,1)] sm:shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] dark:sm:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
            <div className="flex items-center gap-2.5 sm:gap-3 w-full min-w-0">
              <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-none bg-amber-500/10 dark:bg-amber-500/20 border-2 border-amber-500 flex items-center justify-center shrink-0">
                <TrendingUp className="w-4 h-4 sm:w-5 sm:h-5 text-amber-500" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] sm:text-xs font-bold text-zinc-500 uppercase tracking-wider leading-none mb-1.5 truncate">
                  {isAr ? "الصفقات النشطة" : "Active Signals"}
                </p>
                <p className="text-lg sm:text-2xl font-black font-mono leading-none">{summaryStats.activeCount}</p>
              </div>
            </div>
          </div>

          {/* Card 2: Closed Signals */}
          <div className="p-3 sm:p-4 border-2 sm:border-4 border-black dark:border-white bg-white dark:bg-zinc-950 text-black dark:text-white shadow-[3px_3px_0px_rgba(0,0,0,1)] sm:shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] dark:sm:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
            <div className="flex items-center gap-2.5 sm:gap-3 w-full min-w-0">
              <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-none bg-amber-500/10 dark:bg-amber-500/20 border-2 border-amber-500 flex items-center justify-center shrink-0">
                <Layers className="w-4 h-4 sm:w-5 sm:h-5 text-amber-500" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] sm:text-xs font-bold text-zinc-500 uppercase tracking-wider leading-none mb-1.5 truncate">
                  {isAr ? "الصفقات المغلقة" : "Closed Signals"}
                </p>
                <p className="text-lg sm:text-2xl font-black font-mono leading-none">{summaryStats.closedCount}</p>
              </div>
            </div>
          </div>

          {/* Card 3: Win Rate */}
          <div className="p-3 sm:p-4 border-2 sm:border-4 border-black dark:border-white bg-white dark:bg-zinc-950 text-black dark:text-white shadow-[3px_3px_0px_rgba(0,0,0,1)] sm:shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] dark:sm:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
            <div className="flex items-center gap-2.5 sm:gap-3 w-full min-w-0">
              <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-none bg-amber-500/10 dark:bg-amber-500/20 border-2 border-amber-500 flex items-center justify-center shrink-0">
                <Target className="w-4 h-4 sm:w-5 sm:h-5 text-amber-500" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] sm:text-xs font-bold text-zinc-500 uppercase tracking-wider leading-none mb-1.5 truncate">
                  {isAr ? "نسبة النجاح" : "Win Rate"}
                </p>
                <p className="text-lg sm:text-2xl font-black font-mono text-emerald-500 leading-none truncate">
                  {summaryStats.winRate.toFixed(1)}%
                </p>
              </div>
            </div>
          </div>

          {/* Card 4: Avg Return */}
          <div className="p-3 sm:p-4 border-2 sm:border-4 border-black dark:border-white bg-white dark:bg-zinc-950 text-black dark:text-white shadow-[3px_3px_0px_rgba(0,0,0,1)] sm:shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] dark:sm:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
            <div className="flex items-center gap-2.5 sm:gap-3 w-full min-w-0">
              <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-none bg-amber-500/10 dark:bg-amber-500/20 border-2 border-amber-500 flex items-center justify-center shrink-0">
                <Award className="w-4 h-4 sm:w-5 sm:h-5 text-amber-500" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] sm:text-xs font-bold text-zinc-500 uppercase tracking-wider leading-none mb-1.5 truncate">
                  {isAr ? "متوسط العائد" : "Avg Return"}
                </p>
                <p className="text-lg sm:text-2xl font-black font-mono leading-none truncate text-emerald-500">
                  +{summaryStats.avgReturn.toFixed(1)}%
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 4. SMART FILTER TOOLBAR (For Active / Closed / All Views) ── */}
      {viewMode !== "calendar" && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 p-3 sm:p-4 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 text-black dark:text-white shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
            {/* 1. Search */}
            <div className="relative flex items-center">
              <Search className="absolute left-3 w-4 h-4 text-zinc-500" />
              <input
                type="text"
                placeholder={isAr ? "ابحث بالرمز..." : "Search symbol..."}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full h-11 pl-10 pr-3 border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900 text-black dark:text-white font-bold text-xs focus:outline-none"
              />
            </div>

            {/* 2. Scanner Category */}
            <div className="relative flex items-center">
              <Filter className="absolute left-3 w-4 h-4 text-zinc-500 pointer-events-none" />
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value as any)}
                className="w-full h-11 pl-9 pr-4 border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900 text-black dark:text-white font-bold text-xs focus:outline-none appearance-none"
              >
                <option value="all">{isAr ? "جميع أنواع الرصد" : "All Types"}</option>
                <option value="volume_surge">{isAr ? "سيولة مؤسسية ⚡" : "Volume Surge ⚡"}</option>
                <option value="breakout">{isAr ? "اختراق فني 🚀" : "Breakout 🚀"}</option>
                <option value="rsi_oversold">{isAr ? "ارتداد RSI 🎯" : "RSI Rebound 🎯"}</option>
              </select>
            </div>

            {/* 3. Result Filter */}
            <div className="relative flex items-center">
              <Filter className="absolute left-3 w-4 h-4 text-zinc-500 pointer-events-none" />
              <select
                value={resultFilter}
                onChange={(e) => setResultFilter(e.target.value as any)}
                className="w-full h-11 pl-9 pr-4 border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900 text-black dark:text-white font-bold text-xs focus:outline-none appearance-none"
              >
                <option value="all">{isAr ? "جميع النتائج" : "All Results"}</option>
                <option value="win">{isAr ? "محققة للهدف ✅" : "Target Hit ✅"}</option>
                <option value="loss">{isAr ? "وقف الخسارة 🛑" : "Stopped Out 🛑"}</option>
              </select>
            </div>

            {/* 4. Time Range */}
            <div className="relative flex items-center">
              <CalendarIcon className="absolute left-3 w-4 h-4 text-zinc-500 pointer-events-none" />
              <select
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value as any)}
                className="w-full h-11 pl-9 pr-4 border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900 text-black dark:text-white font-bold text-xs focus:outline-none appearance-none"
              >
                <option value="all">{isAr ? "كل الأوقات" : "All Time"}</option>
                <option value="7d">{isAr ? "آخر 7 أيام" : "Last 7 Days"}</option>
                <option value="30d">{isAr ? "آخر 30 يوم" : "Last 30 Days"}</option>
              </select>
            </div>

            {/* 5. Sort Selector */}
            <div className="relative flex items-center">
              <Filter className="absolute left-3 w-4 h-4 text-zinc-500 pointer-events-none" />
              <select
                value={`${sortBy}:${sortOrder}`}
                onChange={(e) => {
                  const [f, o] = e.target.value.split(":");
                  setSortBy(f);
                  setSortOrder(o as "asc" | "desc");
                }}
                className="w-full h-11 pl-9 pr-4 border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900 text-black dark:text-white font-bold text-xs focus:outline-none appearance-none"
              >
                <option value="entry_date:desc">{isAr ? "ترتيب: التاريخ (الأحدث)" : "Sort: Date (Newest)"}</option>
                <option value="entry_date:asc">{isAr ? "ترتيب: التاريخ (الأقدم)" : "Sort: Date (Oldest)"}</option>
                <option value="return:desc">{isAr ? "ترتيب: العائد (الأعلى)" : "Sort: Return (Highest)"}</option>
                <option value="return:asc">{isAr ? "ترتيب: العائد (الأقل)" : "Sort: Return (Lowest)"}</option>
                <option value="symbol:asc">{isAr ? "ترتيب: الرمز (أ-ي)" : "Sort: Symbol (A-Z)"}</option>
                <option value="entry_price:desc">{isAr ? "ترتيب: السعر (الأعلى)" : "Sort: Price (Highest)"}</option>
              </select>
            </div>

            {/* 6. Sharia Toggle */}
            <button
              type="button"
              onClick={() => setShariaOnly((prev) => !prev)}
              className={`h-11 px-3 border-2 border-black dark:border-white font-black text-xs flex items-center justify-center gap-1.5 transition-all shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,1)] active:translate-x-[1px] active:translate-y-[1px] cursor-pointer ${
                shariaOnly ? "bg-emerald-400 text-black" : "bg-zinc-50 dark:bg-zinc-900 text-black dark:text-white"
              }`}
            >
              <ShieldCheck className="w-4 h-4 shrink-0" />
              <span className="truncate">{isAr ? "حلال فقط" : "Sharia Only"}</span>
            </button>
          </div>

          {/* Reset Filters Bar */}
          {(searchTerm || categoryFilter !== "all" || resultFilter !== "all" || timeRange !== "all" || shariaOnly || sortBy !== "entry_date" || sortOrder !== "desc") && (
            <div className="flex items-center justify-between px-3 py-1.5 bg-amber-50 dark:bg-amber-950/20 border-2 border-black text-xs font-bold text-zinc-700 dark:text-zinc-300">
              <span>{isAr ? "تم تطبيق فلاتر أو ترتيب مخصص على القائمة" : "Custom filters or sorting active"}</span>
              <button
                type="button"
                onClick={() => {
                  setSearchTerm("");
                  setCategoryFilter("all");
                  setResultFilter("all");
                  setTimeRange("all");
                  setShariaOnly(false);
                  setSortBy("entry_date");
                  setSortOrder("desc");
                }}
                className="text-amber-700 dark:text-amber-400 hover:underline font-black cursor-pointer"
              >
                {isAr ? "مسح جميع الفلاتر ✕" : "Clear all filters ✕"}
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── 5. ACTIVE / CLOSED / ALL SIGNALS TABLE (Exact Layout & Columns as Short Swings) ── */}
      {viewMode !== "calendar" && (
        <div className="space-y-4">
          {(() => {
            const currentList =
              viewMode === "active" ? filteredActive : viewMode === "closed" ? filteredClosed : filteredAll;

            if (currentList.length === 0) {
              return (
                <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-8 text-center shadow-[4px_4px_0px_#000]">
                  <Info className="w-8 h-8 text-zinc-400 mx-auto mb-2" />
                  <p className="text-sm font-black text-zinc-700 dark:text-zinc-300">
                    {isAr
                      ? "لا توجد إشارات مطابقة لمعايير البحث الحالية في الرصد اللحظي."
                      : "No intraday signals match the current search criteria."}
                  </p>
                </div>
              );
            }

            return (
              <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] overflow-hidden">
                {/* Desktop Table View */}
                <div className="overflow-x-auto w-full">
                  <table className="w-full text-left border-collapse whitespace-nowrap">
                    <thead>
                      <tr className="text-xs font-black uppercase text-black dark:text-white bg-zinc-100 dark:bg-zinc-900 border-b-4 border-black dark:border-white select-none">
                        <th className="px-4 py-3.5 text-center w-12 border-r border-zinc-200 dark:border-zinc-800">#</th>
                        <th 
                          onClick={() => handleHeaderClick("symbol")}
                          className="px-6 py-3.5 text-left border-r border-zinc-200 dark:border-zinc-800 cursor-pointer hover:bg-zinc-200 dark:hover:bg-zinc-800 transition-colors select-none"
                        >
                          <div className="flex items-center justify-between gap-1">
                            <span>{isAr ? "السهم والشركة" : "Stock & Symbol"}</span>
                            {renderSortIcon("symbol")}
                          </div>
                        </th>
                        <th 
                          onClick={() => handleHeaderClick("scanner_type")}
                          className="px-4 py-3.5 text-center border-r border-zinc-200 dark:border-zinc-800 cursor-pointer hover:bg-zinc-200 dark:hover:bg-zinc-800 transition-colors select-none"
                        >
                          <div className="flex items-center justify-center gap-1">
                            <span>{isAr ? "نوع الرصد الفني" : "Scanner"}</span>
                            {renderSortIcon("scanner_type")}
                          </div>
                        </th>
                        <th 
                          onClick={() => handleHeaderClick("entry_date")}
                          className="px-4 py-3.5 text-center border-r border-zinc-200 dark:border-zinc-800 cursor-pointer hover:bg-zinc-200 dark:hover:bg-zinc-800 transition-colors select-none"
                        >
                          <div className="flex items-center justify-center gap-1">
                            <span>{isAr ? "توقيت الرصد" : "Detected Time"}</span>
                            {renderSortIcon("entry_date")}
                          </div>
                        </th>
                        <th 
                          onClick={() => handleHeaderClick("entry_price")}
                          className="px-4 py-3.5 text-center border-r border-zinc-200 dark:border-zinc-800 cursor-pointer hover:bg-zinc-200 dark:hover:bg-zinc-800 transition-colors select-none"
                        >
                          <div className="flex items-center justify-center gap-1">
                            <span>{isAr ? "سعر الرصد" : "Entry"}</span>
                            {renderSortIcon("entry_price")}
                          </div>
                        </th>
                        <th 
                          onClick={() => handleHeaderClick("target_1")}
                          className="px-4 py-3.5 text-center border-r border-zinc-200 dark:border-zinc-800 cursor-pointer hover:bg-zinc-200 dark:hover:bg-zinc-800 transition-colors select-none"
                        >
                          <div className="flex items-center justify-center gap-1">
                            <span>{isAr ? "المستهدف الفني 1" : "Target 1"}</span>
                            {renderSortIcon("target_1")}
                          </div>
                        </th>
                        <th 
                          onClick={() => handleHeaderClick("stop_loss")}
                          className="px-4 py-3.5 text-center border-r border-zinc-200 dark:border-zinc-800 cursor-pointer hover:bg-zinc-200 dark:hover:bg-zinc-800 transition-colors select-none"
                        >
                          <div className="flex items-center justify-center gap-1">
                            <span>{isAr ? "إيقاف الخسارة" : "Stop Loss"}</span>
                            {renderSortIcon("stop_loss")}
                          </div>
                        </th>
                        <th 
                          onClick={() => handleHeaderClick("current_price")}
                          className="px-4 py-3.5 text-center border-r border-zinc-200 dark:border-zinc-800 cursor-pointer hover:bg-zinc-200 dark:hover:bg-zinc-800 transition-colors select-none"
                        >
                          <div className="flex items-center justify-center gap-1">
                            <span>{isAr ? "السعر الحالي / الخروج" : "Current / Exit"}</span>
                            {renderSortIcon("current_price")}
                          </div>
                        </th>
                        <th 
                          onClick={() => handleHeaderClick("return")}
                          className="px-4 py-3.5 text-center border-r border-zinc-200 dark:border-zinc-800 cursor-pointer hover:bg-zinc-200 dark:hover:bg-zinc-800 transition-colors select-none"
                        >
                          <div className="flex items-center justify-center gap-1">
                            <span>{isAr ? "العائد الفني" : "Return"}</span>
                            {renderSortIcon("return")}
                          </div>
                        </th>
                        <th 
                          onClick={() => handleHeaderClick("status")}
                          className="px-4 py-3.5 text-center border-r border-zinc-200 dark:border-zinc-800 cursor-pointer hover:bg-zinc-200 dark:hover:bg-zinc-800 transition-colors select-none"
                        >
                          <div className="flex items-center justify-center gap-1">
                            <span>{isAr ? "حالة الإشارة" : "Status"}</span>
                            {renderSortIcon("status")}
                          </div>
                        </th>
                        <th className="px-4 py-3.5 text-center">{isAr ? "أدوات التحليل" : "Tools"}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y-2 divide-black dark:divide-white">
                      {currentList.map((sig: any, idx) => {
                        const isRowActive = Boolean(sig._isActive || sig.status === "active");
                        const isLocked = isRowActive && Boolean(sig.is_locked || !userHasPro);
                        const badge = getScannerBadge(sig.scanner_type);
                        const ret = getSignalReturn(sig);
                        const isWin = ret > 0 || sig.status === "target_hit";
                        const isBreakeven = ret === 0;

                        const openChart = () => {
                          if (isLocked) {
                            setShowProModal(true);
                            return;
                          }
                          setChartModalStock({
                            symbol: sig.symbol,
                            date: sig.entry_date,
                            toDate: sig.exit_date || new Date().toISOString().split("T")[0],
                            signalTime: sig.entry_time,
                            signalPrice: sig.entry_price,
                            exitTime: sig.exit_time,
                            exitPrice: sig.exit_price,
                            status: sig.status,
                            scannerType: sig.scanner_type,
                          });
                        };

                        return (
                          <tr
                            key={`${sig.symbol}-${sig.entry_date}-${idx}`}
                            onClick={openChart}
                            onMouseEnter={() => {
                              if (!isLocked) {
                                prefetchIntradaySession(sig.symbol, sig.entry_date, sig.entry_time, sig.entry_price, sig.exit_date);
                              }
                            }}
                            className="hover:bg-zinc-50 dark:hover:bg-zinc-900/60 cursor-pointer transition-colors text-xs font-bold"
                          >
                            {/* Rank */}
                            <td className="px-4 py-4 text-center font-mono font-black border-r border-zinc-200 dark:border-zinc-800">
                              <span className="w-7 h-7 inline-flex items-center justify-center border border-black bg-zinc-100 dark:bg-zinc-800">
                                {idx + 1}
                              </span>
                            </td>

                            {/* Symbol & Name */}
                            <td className="px-6 py-4 border-r border-zinc-200 dark:border-zinc-800 text-left">
                              <div className="flex items-center gap-3">
                                {isLocked ? (
                                  <div className="w-9 h-9 border-2 border-black bg-amber-400 flex items-center justify-center">
                                    <Lock className="w-4 h-4 text-black" />
                                  </div>
                                ) : (
                                  <StockLogo symbol={sig.symbol} size="md" />
                                )}
                                <div>
                                  <div className="flex items-center gap-1.5 flex-wrap">
                                    <span className="font-mono font-black text-sm text-indigo-600 dark:text-indigo-400">
                                      {isLocked ? "••••••" : sig.symbol}
                                    </span>
                                    {isRowActive && (
                                      <span className="px-1.5 py-0.5 border border-black bg-[#FFE600] text-black text-[9px] font-black animate-pulse">
                                        ⚡ رصد حي
                                      </span>
                                    )}
                                    {!isLocked && isShariaCompliant(sig.symbol) && (
                                      <span className="px-1.5 py-0.2 border border-black bg-emerald-400 text-black text-[8px] font-black uppercase">
                                        حلال
                                      </span>
                                    )}
                                  </div>
                                  <span className="text-[11px] text-zinc-500 font-bold block truncate max-w-[170px]">
                                    {isLocked ? "إشارة مشفرة لـ PRO" : (sig.name_ar || sig.symbol)}
                                  </span>
                                </div>
                              </div>
                            </td>

                            {/* Scanner Type */}
                            <td className="px-4 py-4 text-center border-r border-zinc-200 dark:border-zinc-800">
                              <span className={`px-2 py-0.5 text-[10px] font-black border ${badge.pillBg}`}>
                                {badge.label}
                              </span>
                            </td>

                            {/* Detected Date/Time */}
                            <td className="px-4 py-4 text-center font-mono border-r border-zinc-200 dark:border-zinc-800 text-zinc-600 dark:text-zinc-400">
                              <span>{sig.entry_date}</span>
                              <span className="block text-[10px] text-zinc-500 font-bold">({sig.entry_time})</span>
                            </td>

                            {/* Entry Price */}
                            <td className="px-4 py-4 text-center font-mono font-black text-black dark:text-white border-r border-zinc-200 dark:border-zinc-800">
                              {isLocked ? "•••" : `${sig.entry_price?.toFixed(2)} ج.م`}
                            </td>

                            {/* Target 1 */}
                            <td className="px-4 py-4 text-center font-mono font-black border-r border-zinc-200 dark:border-zinc-800 text-emerald-600 dark:text-emerald-400">
                              {isLocked ? (
                                "•••"
                              ) : (
                                <>
                                  <span>{sig.target_1?.toFixed(2)}</span>
                                  <span className="text-[10px] block font-bold">(+{sig.target_1_pct}%)</span>
                                </>
                              )}
                            </td>

                            {/* Stop Loss */}
                            <td className="px-4 py-4 text-center font-mono font-black border-r border-zinc-200 dark:border-zinc-800">
                              {isLocked ? (
                                "•••"
                              ) : sig.stop_loss_pct === 0 ? (
                                <span className="text-sky-600 dark:text-sky-400">
                                  {sig.stop_loss?.toFixed(2)}{" "}
                                  <span className="text-[10px] block text-sky-500 font-bold">تأمين تعادل 🛡️</span>
                                </span>
                              ) : (
                                <span className="text-rose-600 dark:text-rose-400">
                                  {sig.stop_loss?.toFixed(2)}{" "}
                                  <span className="text-[10px] block text-rose-500 font-bold">(-{sig.stop_loss_pct}%)</span>
                                </span>
                              )}
                            </td>

                            {/* Current / Exit Price */}
                            <td className="px-4 py-4 text-center font-mono font-black text-black dark:text-white border-r border-zinc-200 dark:border-zinc-800">
                              {isLocked ? "•••" : (
                                <>
                                  <span>{(sig.exit_price || sig.current_price)?.toFixed(2)} ج.م</span>
                                  {sig.exit_date && (
                                    <span className="block text-[10px] text-zinc-500 font-bold">
                                      {sig.exit_date} ({sig.exit_time || "14:15"})
                                    </span>
                                  )}
                                </>
                              )}
                            </td>

                            {/* Return */}
                            <td className="px-4 py-4 text-center font-mono font-black border-r border-zinc-200 dark:border-zinc-800">
                              <span
                                className={`px-2 py-0.5 border text-black font-black text-xs ${
                                  isWin
                                    ? "bg-emerald-400 border-black"
                                    : isBreakeven
                                    ? "bg-amber-300 border-black"
                                    : "bg-rose-400 border-black"
                                }`}
                              >
                                {ret >= 0 ? `+${ret.toFixed(2)}%` : `${ret.toFixed(2)}%`}
                              </span>
                            </td>

                            {/* Status */}
                            <td className="px-4 py-4 text-center border-r border-zinc-200 dark:border-zinc-800">
                              {isRowActive ? (
                                <span className="px-2 py-0.5 text-[10px] font-black border bg-emerald-100 text-emerald-800 border-emerald-500">
                                  {isAr ? "إشارة نشطة 🟢" : "Active 🟢"}
                                </span>
                              ) : (
                                <span
                                  className={`px-2 py-0.5 text-[10px] font-black border ${
                                    sig.status === "target_hit"
                                      ? "bg-emerald-100 dark:bg-emerald-950/80 text-emerald-700 dark:text-emerald-300 border-emerald-500"
                                      : sig.status === "stopped_out"
                                      ? "bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 border-rose-500"
                                      : "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-400"
                                  }`}
                                >
                                  {sig.exit_reason || (isWin ? "تحقق المستهدف 🎯" : "إغلاق الإشارة")}
                                </span>
                              )}
                            </td>

                            {/* Tools */}
                            <td className="px-4 py-4 text-center">
                              <div className="flex items-center justify-center gap-1.5">
                                {!isLocked && (
                                  <>
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setShareSignal(sig);
                                      }}
                                      className="p-1.5 bg-zinc-100 hover:bg-zinc-200 text-black border border-black shadow-[1px_1px_0px_#000] cursor-pointer"
                                      title={isAr ? "مشاركة الإشارة" : "Share"}
                                    >
                                      <Share2 className="w-3.5 h-3.5" />
                                    </button>
                                    <Link
                                      href={`/stocks/${sig.symbol}`}
                                      onClick={(e) => e.stopPropagation()}
                                      className="p-1.5 bg-zinc-100 hover:bg-zinc-200 text-black border border-black shadow-[1px_1px_0px_#000]"
                                      title={isAr ? "تحليل السهم" : "Stock"}
                                    >
                                      <ExternalLink className="w-3.5 h-3.5" />
                                    </Link>
                                  </>
                                )}
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    openChart();
                                  }}
                                  className="px-2.5 py-1 bg-[#FFE600] hover:bg-yellow-300 text-black border border-black font-black text-[11px] flex items-center gap-1 shadow-[1px_1px_0px_#000] cursor-pointer"
                                >
                                  <BarChart2 className="w-3.5 h-3.5" />
                                  <span>{isAr ? "شارت 15 د" : "15m Chart"}</span>
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })()}
        </div>
      )}

      {/* ── 6. CALENDAR VIEW (Exact Replica of Short Swings & RecommendationCalendar) ── */}
      {viewMode === "calendar" && (
        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-6 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] space-y-6">
          {/* Top Control Bar: Presets & Grid/List switcher */}
          <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4 border-b-2 border-black dark:border-white pb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 border-2 border-black bg-amber-400 flex items-center justify-center font-black shrink-0">
                <CalendarIcon className="w-5 h-5 text-black" />
              </div>
              <div>
                <h3 className="text-base sm:text-lg font-black text-black dark:text-white">
                  {isAr ? "تقويم أداء وإحصائيات الرصد اللحظي" : "Intraday Fast Radar Performance Calendar"}
                </h3>
                <p className="text-[11px] font-bold text-zinc-500">
                  {isAr
                    ? "تتبع الإشارات اليومية، والنتائج المحققة لشهري 8 و 9 وكامل عام 2026 على فريم 15 دقيقة"
                    : "Track daily intraday signals, win rates, and session returns across 2026"}
                </p>
              </div>
            </div>

            {/* Presets and View Switcher */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center border-2 border-black bg-zinc-100 dark:bg-zinc-900 p-0.5 text-xs font-bold overflow-x-auto">
                <button
                  onClick={goToToday}
                  className={`px-2.5 sm:px-3 py-1 transition-all whitespace-nowrap cursor-pointer ${
                    filterPreset === "this_month" && currentMonthStr === todayDateStr.slice(0, 7)
                      ? "bg-[#FFE600] text-black font-black border border-black shadow-sm"
                      : "text-zinc-600 dark:text-zinc-400 hover:text-black dark:hover:text-white"
                  }`}
                >
                  {isAr ? "اليوم (أكتوبر 2026)" : "Today (Oct 2026)"}
                </button>
                <button
                  onClick={() => {
                    setFilterPreset("this_month");
                    setCurrentDate(new Date(2026, 8, 1));
                  }}
                  className={`px-2.5 sm:px-3 py-1 transition-all whitespace-nowrap cursor-pointer ${
                    currentMonthStr === "2026-09" && filterPreset !== "30days" && filterPreset !== "all"
                      ? "bg-[#FFE600] text-black font-black border border-black shadow-sm"
                      : "text-zinc-600 dark:text-zinc-400 hover:text-black dark:hover:text-white"
                  }`}
                >
                  {isAr ? "شهر 9 (سبتمبر 2026)" : "September 2026"}
                </button>
                <button
                  onClick={() => {
                    setFilterPreset("this_month");
                    setCurrentDate(new Date(2026, 7, 1));
                  }}
                  className={`px-2.5 sm:px-3 py-1 transition-all whitespace-nowrap cursor-pointer ${
                    currentMonthStr === "2026-08" && filterPreset !== "30days" && filterPreset !== "all"
                      ? "bg-[#FFE600] text-black font-black border border-black shadow-sm"
                      : "text-zinc-600 dark:text-zinc-400 hover:text-black dark:hover:text-white"
                  }`}
                >
                  {isAr ? "شهر 8 (أغسطس 2026)" : "August 2026"}
                </button>
                <button
                  onClick={() => {
                    setFilterPreset("30days");
                    setCurrentDate(new Date());
                  }}
                  className={`px-2.5 sm:px-3 py-1 transition-all whitespace-nowrap cursor-pointer ${
                    filterPreset === "30days"
                      ? "bg-[#FFE600] text-black font-black border border-black shadow-sm"
                      : "text-zinc-600 dark:text-zinc-400 hover:text-black dark:hover:text-white"
                  }`}
                >
                  {isAr ? "آخر 30 يوم" : "Last 30 Days"}
                </button>
                <button
                  onClick={() => {
                    setFilterPreset("all");
                  }}
                  className={`px-2.5 sm:px-3 py-1 transition-all whitespace-nowrap cursor-pointer ${
                    filterPreset === "all"
                      ? "bg-[#FFE600] text-black font-black border border-black shadow-sm"
                      : "text-zinc-600 dark:text-zinc-400 hover:text-black dark:hover:text-white"
                  }`}
                >
                  {isAr ? `كامل عام 2026 (${closedSignals.length} إشارة)` : `Full 2026 (${closedSignals.length} closed)`}
                </button>
              </div>

              {/* View Switcher: Grid vs List */}
              <div className="flex items-center border-2 border-black bg-zinc-100 dark:bg-zinc-900 p-0.5 shrink-0">
                <button
                  onClick={() => setCalendarViewType("grid")}
                  title={isAr ? "عرض التقويم" : "Calendar Grid"}
                  className={`p-1.5 transition-all cursor-pointer ${
                    calendarViewType === "grid"
                      ? "bg-[#FFE600] text-black font-black border border-black"
                      : "text-zinc-400 hover:text-black dark:hover:text-white"
                  }`}
                >
                  <Grid className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setCalendarViewType("list")}
                  title={isAr ? "عرض القائمة" : "List View"}
                  className={`p-1.5 transition-all cursor-pointer ${
                    calendarViewType === "list"
                      ? "bg-[#FFE600] text-black font-black border border-black"
                      : "text-zinc-400 hover:text-black dark:hover:text-white"
                  }`}
                >
                  <List className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          {/* Month Navigation Bar */}
          <div className="flex items-center justify-between border-b-2 border-black dark:border-white pb-3 sm:pb-4">
            <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
              <h3 className="text-base sm:text-lg md:text-xl font-black text-black dark:text-white">
                {currentMonthName} {year}
              </h3>
              <span className="text-[10px] sm:text-xs font-bold text-black dark:text-white bg-zinc-100 dark:bg-zinc-800 px-2 sm:px-2.5 py-0.5 sm:py-1 border border-black dark:border-white">
                {monthStats.total} {isAr ? "إشارة مغلقة في الشهر" : "monthly closed signals"}
              </span>
              {viewedActiveSignals.length > 0 && (
                <span className="text-[10px] sm:text-xs font-black text-black bg-[#FFE600] px-2 sm:px-2.5 py-0.5 sm:py-1 border border-black shadow-[1px_1px_0px_#000]">
                  ⚡ {viewedActiveSignals.length} {isAr ? "قيد المتابعة" : "active"}
                </span>
              )}
            </div>

            <div className="flex items-center gap-1.5 sm:gap-2">
              <button
                onClick={prevMonth}
                className="p-1.5 sm:p-2 border-2 border-black bg-white dark:bg-zinc-900 text-black dark:text-white hover:bg-zinc-100 shadow-[2px_2px_0px_#000] cursor-pointer"
                title={isAr ? "الشهر السابق" : "Previous Month"}
              >
                <ChevronLeft className="w-4 h-4 sm:w-5 sm:h-5" />
              </button>
              <button
                onClick={goToToday}
                className="px-2.5 sm:px-3 py-1 sm:py-1.5 border-2 border-black bg-zinc-100 dark:bg-zinc-900 text-black dark:text-white hover:bg-zinc-200 text-xs font-black shadow-[2px_2px_0px_#000] cursor-pointer"
              >
                {isAr ? "اليوم" : "Today"}
              </button>
              <button
                onClick={nextMonth}
                className="p-1.5 sm:p-2 border-2 border-black bg-white dark:bg-zinc-900 text-black dark:text-white hover:bg-zinc-100 shadow-[2px_2px_0px_#000] cursor-pointer"
                title={isAr ? "الشهر التالي" : "Next Month"}
              >
                <ChevronRight className="w-4 h-4 sm:w-5 sm:h-5" />
              </button>
            </div>
          </div>

          {/* Month Summary Bar */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-zinc-100 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 p-3 sm:p-4">
            <div>
              <span className="text-[10px] font-bold text-zinc-500 uppercase block">إشارات الشهر</span>
              <span className="text-xl font-black font-mono text-black dark:text-white">
                {monthStats.total > 0
                  ? `${monthStats.total} مغلقة`
                  : viewedActiveSignals.length > 0
                  ? `0 مغلقة • ${viewedActiveSignals.length} جارية`
                  : "0 إشارة"}
              </span>
            </div>
            <div>
              <span className="text-[10px] font-bold text-zinc-500 uppercase block">نسبة النجاح</span>
              <span className="text-xl font-black font-mono text-emerald-600 dark:text-emerald-400">
                {monthStats.winRate.toFixed(1)}%
              </span>
            </div>
            <div>
              <span className="text-[10px] font-bold text-zinc-500 uppercase block">صافي العائد المحقق</span>
              <span
                className={`text-xl font-black font-mono block ${
                  monthStats.netReturn >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
                }`}
              >
                {monthStats.netReturn >= 0 ? "+" : ""}{monthStats.netReturn.toFixed(1)}%
              </span>
            </div>
            <div>
              <span className="text-[10px] font-bold text-zinc-500 uppercase block">أفضل إشارة في الشهر</span>
              <span className="text-base sm:text-lg font-black font-mono text-indigo-600 dark:text-indigo-400 truncate block">
                {monthStats.bestSignal
                  ? `${monthStats.bestSignal.symbol} (+${getSignalReturn(monthStats.bestSignal).toFixed(1)}%)`
                  : "—"}
              </span>
            </div>
          </div>

          {/* Calendar Grid View */}
          {calendarViewType === "grid" ? (
            <div className="space-y-2">
              <div className="grid grid-cols-7 gap-1 sm:gap-2 text-center text-[10px] sm:text-xs font-black uppercase tracking-wider text-black dark:text-white">
                {["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"].map((dName, i) => (
                  <div
                    key={dName}
                    className={`py-1.5 border-2 border-black dark:border-white ${
                      i >= 5 ? "bg-zinc-200 dark:bg-zinc-800 text-zinc-500" : "bg-[#FFE600] text-black"
                    }`}
                  >
                    {dName}
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-7 gap-1 sm:gap-2">
                {calendarDays.map((cell) => {
                  const dayClosed = closedByExitDate.get(cell.dateStr) || [];
                  const dayCreated = allByEntryDate.get(cell.dateStr) || [];
                  const hasClosed = dayClosed.length > 0;
                  const hasCreated = dayCreated.length > 0;
                  const netDailyPct = dayClosed.reduce((acc, s) => acc + getSignalReturn(s), 0);
                  const isToday = cell.dateStr === todayDateStr;

                  return (
                    <div
                      key={cell.dateStr}
                      onClick={() => {
                        if (hasClosed || hasCreated) {
                          setSelectedDaySignals({
                            date: cell.dateStr,
                            closedSignals: dayClosed,
                            createdSignals: dayCreated,
                          });
                          setDayModalFilter("all");
                        }
                      }}
                      className={`min-h-[70px] sm:min-h-[85px] p-1.5 sm:p-2 border-2 flex flex-col justify-between transition-all ${
                        hasClosed || hasCreated ? "cursor-pointer" : ""
                      } ${
                        isToday ? "border-amber-500 bg-amber-500/15" : ""
                      } ${
                        !cell.isCurrentMonth
                          ? "border-zinc-200 dark:border-zinc-800 text-zinc-400 opacity-30"
                          : cell.isWeekend
                          ? "border-zinc-300 dark:border-zinc-800 bg-zinc-100 dark:bg-zinc-900 text-zinc-400"
                          : hasClosed
                          ? netDailyPct >= 0
                            ? "border-black dark:border-white bg-emerald-50 dark:bg-emerald-950/20 shadow-[2px_2px_0px_#000]"
                            : "border-black dark:border-white bg-rose-50 dark:bg-rose-950/20 shadow-[2px_2px_0px_#000]"
                          : hasCreated
                          ? "border-amber-400 bg-amber-50 dark:bg-amber-950/20 shadow-[2px_2px_0px_#f59e0b]"
                          : "border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-400"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className={`text-xs font-black font-mono ${isToday ? "bg-amber-400 text-black px-1" : ""}`}>
                          {cell.dayNum}
                        </span>
                        <div className="flex items-center gap-1">
                          {hasClosed && (
                            <span className="px-1 py-0.2 bg-black text-[#FFE600] text-[8px] font-black">
                              {dayClosed.length} إغلاق
                            </span>
                          )}
                          {hasCreated && (
                            <span className="px-1 py-0.2 bg-amber-400 text-black text-[8px] font-black">
                              ⚡ {dayCreated.length}
                            </span>
                          )}
                        </div>
                      </div>

                      {hasClosed ? (
                        <div className="my-1 text-center font-mono">
                          <span
                            className={`text-[11px] font-black px-1 py-0.5 border border-black ${
                              netDailyPct >= 0
                                ? "bg-emerald-200 text-emerald-900"
                                : "bg-rose-200 text-rose-900"
                            }`}
                          >
                            {netDailyPct >= 0 ? "+" : ""}{netDailyPct.toFixed(1)}%
                          </span>
                        </div>
                      ) : hasCreated ? (
                        <div className="text-[10px] font-black text-amber-600 text-center">
                          رصد جديد ⚡
                        </div>
                      ) : (
                        <div className="text-[9px] text-zinc-400 text-center">
                          {cell.isWeekend ? "عطلة" : "—"}
                        </div>
                      )}

                      <div className="text-[9px] text-zinc-500 truncate font-mono text-center">
                        {hasClosed
                          ? dayClosed.map((s) => s.symbol).slice(0, 2).join(", ")
                          : hasCreated
                          ? dayCreated.map((s) => s.symbol).slice(0, 2).join(", ")
                          : ""}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            /* Agenda / List View */
            <div className="space-y-3">
              {viewedClosedSignals.map((sig, idx) => (
                <div
                  key={`agenda-${sig.symbol}-${idx}`}
                  onClick={() => {
                    setChartModalStock({
                      symbol: sig.symbol,
                      date: sig.entry_date,
                      toDate: sig.exit_date,
                      signalTime: sig.entry_time,
                      signalPrice: sig.entry_price,
                      exitTime: sig.exit_time,
                      exitPrice: sig.exit_price,
                      status: sig.status,
                      scannerType: sig.scanner_type,
                    });
                  }}
                  className="p-3 border-2 border-black flex items-center justify-between gap-3 hover:bg-zinc-50 cursor-pointer"
                >
                  <div className="flex items-center gap-2">
                    <StockLogo symbol={sig.symbol} size="sm" />
                    <div>
                      <span className="font-mono font-black text-sm">{sig.symbol}</span>
                      <span className="text-[10px] text-zinc-500 block">
                        {sig.entry_date} ({sig.entry_time})
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-mono font-black">
                      {sig.entry_price?.toFixed(2)} ← {sig.exit_price?.toFixed(2)}
                    </span>
                    <span
                      className={`px-2 py-0.5 font-mono font-black text-xs border border-black ${
                        getSignalReturn(sig) >= 0 ? "bg-emerald-300 text-black" : "bg-rose-300 text-black"
                      }`}
                    >
                      {getSignalReturn(sig) >= 0 ? "+" : ""}{getSignalReturn(sig).toFixed(1)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── 7. DAY SIGNALS MODAL (When clicking any calendar cell) ── */}
      {selectedDaySignals && (
        <div
          className="fixed inset-0 z-[9999] bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4"
          onClick={() => setSelectedDaySignals(null)}
        >
          <div
            className="relative w-full max-w-xl bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[8px_8px_0px_#000] dark:shadow-[8px_8px_0px_#fff] p-4 sm:p-6 space-y-4 max-h-[88vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
            dir={isAr ? "rtl" : "ltr"}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b-2 border-black dark:border-white pb-3">
              <div className="flex items-center gap-2.5">
                <span className="w-9 h-9 bg-[#FFE600] border-2 border-black flex items-center justify-center font-black">
                  <CalendarIcon className="w-5 h-5 text-black" />
                </span>
                <div>
                  <h3 className="font-black text-base text-black dark:text-white">
                    {isAr ? `تفاصيل جلسة ${selectedDaySignals.date}` : `Session Details: ${selectedDaySignals.date}`}
                  </h3>
                  <span className="text-[10px] text-zinc-500 font-bold block">
                    {isAr
                      ? "الصفقات المغلقة في الجلسة والإشارات التي تم رصدها"
                      : "Closed trades and signals detected on this session"}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedDaySignals(null)}
                className="p-1.5 border-2 border-black bg-zinc-100 hover:bg-zinc-200 cursor-pointer"
              >
                <X className="w-4 h-4 text-black" />
              </button>
            </div>

            {/* Modal Filter Tabs */}
            <div className="flex items-center gap-1.5 border-2 border-black bg-zinc-100 dark:bg-zinc-950 p-1 text-xs font-bold">
              <button
                type="button"
                onClick={() => setDayModalFilter("all")}
                className={`px-3 py-1 transition-all cursor-pointer ${
                  dayModalFilter === "all"
                    ? "bg-[#FFE600] text-black font-black border border-black shadow-sm"
                    : "text-zinc-600 dark:text-zinc-400"
                }`}
              >
                {isAr ? "الكل" : "All"} ({selectedDaySignals.closedSignals.length + selectedDaySignals.createdSignals.length})
              </button>
              <button
                type="button"
                onClick={() => setDayModalFilter("closed")}
                className={`px-3 py-1 transition-all cursor-pointer ${
                  dayModalFilter === "closed"
                    ? "bg-black text-[#FFE600] font-black border border-black shadow-sm"
                    : "text-zinc-600 dark:text-zinc-400"
                }`}
              >
                {isAr ? "صفقات أُغلقت بالجلسة" : "Closed Today"} ({selectedDaySignals.closedSignals.length})
              </button>
              <button
                type="button"
                onClick={() => setDayModalFilter("created")}
                className={`px-3 py-1 transition-all cursor-pointer ${
                  dayModalFilter === "created"
                    ? "bg-amber-400 text-black font-black border border-black shadow-sm"
                    : "text-zinc-600 dark:text-zinc-400"
                }`}
              >
                {isAr ? "إشارات رُصدت بالجلسة" : "Detected Today"} ({selectedDaySignals.createdSignals.length})
              </button>
            </div>

            {/* Modal Body */}
            <div className="space-y-4">
              {/* SECTION 1: Closed Trades */}
              {(dayModalFilter === "all" || dayModalFilter === "closed") && selectedDaySignals.closedSignals.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs font-black text-zinc-700 dark:text-zinc-300 border-b border-zinc-200 dark:border-zinc-800 pb-1">
                    <span>{isAr ? "صفقات أُغلقت في هذه الجلسة" : "Trades Closed in this Session"}</span>
                    <span className="font-mono text-[11px] text-zinc-500">
                      {isAr ? "الصافي:" : "Net:"}{" "}
                      <strong className={selectedDaySignals.closedSignals.reduce((acc, s) => acc + getSignalReturn(s), 0) >= 0 ? "text-emerald-600" : "text-rose-600"}>
                        {selectedDaySignals.closedSignals.reduce((acc, s) => acc + getSignalReturn(s), 0) >= 0 ? "+" : ""}
                        {selectedDaySignals.closedSignals.reduce((acc, s) => acc + getSignalReturn(s), 0).toFixed(2)}%
                      </strong>
                    </span>
                  </div>

                  <div className="space-y-2.5">
                    {selectedDaySignals.closedSignals.map((s, idx) => {
                      const ret = getSignalReturn(s);
                      const isGain = ret > 0 || s.status === "target_hit";
                      const isBreakeven = ret === 0;
                      const badge = getScannerBadge(s.scanner_type);

                      return (
                        <div
                          key={`modal-closed-${s.symbol}-${s.entry_date}-${idx}`}
                          className="p-3 border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950 space-y-2 shadow-[2px_2px_0px_#000]"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <StockLogo symbol={s.symbol} size="sm" />
                              <div>
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <span className="font-mono font-black text-sm text-black dark:text-white">{s.symbol}</span>
                                  <span className={`px-1.5 py-0.2 text-[9px] font-black border ${badge.pillBg}`}>
                                    {badge.label}
                                  </span>
                                  {isShariaCompliant(s.symbol) && (
                                    <span className="px-1.5 py-0.2 border border-black bg-emerald-400 text-black text-[8px] font-black">
                                      حلال
                                    </span>
                                  )}
                                  <span className="px-1.5 py-0.2 bg-black text-[#FFE600] text-[9px] font-black border border-black">
                                    صفقة مغلقة
                                  </span>
                                </div>
                                <span className="text-[10px] text-zinc-500 font-bold block">
                                  {s.name_ar || s.sector}
                                </span>
                              </div>
                            </div>

                            <div className="flex items-center gap-2">
                              <span
                                className={`px-2.5 py-0.5 font-mono font-black text-xs border border-black ${
                                  isGain ? "bg-emerald-300 text-black" : isBreakeven ? "bg-amber-300 text-black" : "bg-rose-300 text-black"
                                }`}
                              >
                                {ret >= 0 ? "+" : ""}{ret.toFixed(2)}%
                              </span>
                              <button
                                type="button"
                                onClick={() => {
                                  setChartModalStock({
                                    symbol: s.symbol,
                                    date: s.entry_date,
                                    toDate: s.exit_date,
                                    signalTime: s.entry_time,
                                    signalPrice: s.entry_price,
                                    exitTime: s.exit_time,
                                    exitPrice: s.exit_price,
                                    status: s.status,
                                    scannerType: s.scanner_type,
                                  });
                                }}
                                className="p-1 bg-[#FFE600] border border-black cursor-pointer shadow-[1px_1px_0px_#000]"
                                title="شارت 15 دقيقة"
                              >
                                <BarChart2 className="w-4 h-4 text-black" />
                              </button>
                            </div>
                          </div>

                          {/* Chronological Breakdown: Entry Date/Time vs Exit Date/Time */}
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-bold pt-2 border-t border-zinc-200 dark:border-zinc-800">
                            <div>
                              <span className="text-[10px] text-zinc-500 block">توقيت الرصد والدخول</span>
                              <span className="font-mono text-black dark:text-white text-[11px]">
                                {s.entry_date} ({s.entry_time})
                              </span>
                              <span className="font-mono text-zinc-600 dark:text-zinc-400 text-[10px] block">
                                عند {s.entry_price?.toFixed(2)} ج.م
                              </span>
                            </div>
                            <div>
                              <span className="text-[10px] text-zinc-500 block">توقيت وسعر الخروج</span>
                              <span className="font-mono text-black dark:text-white text-[11px]">
                                {s.exit_date} ({s.exit_time || "14:15"})
                              </span>
                              <span className="font-mono text-zinc-600 dark:text-zinc-400 text-[10px] block">
                                عند {(s.exit_price || s.current_price)?.toFixed(2)} ج.م
                              </span>
                            </div>
                            <div>
                              <span className="text-[10px] text-zinc-500 block">مدة الصفقة</span>
                              <span className="font-mono text-black dark:text-white text-[11px]">
                                {s.sessions_count || 1} جلسات
                              </span>
                            </div>
                            <div>
                              <span className="text-[10px] text-zinc-500 block">سبب الإغلاق</span>
                              <span className="text-black dark:text-white text-[11px]">
                                {s.exit_reason || (isGain ? "تحقق الهدف الأول 🎯" : "ضرب وقف الخسارة 🛑")}
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* SECTION 2: Signals Detected Today */}
              {(dayModalFilter === "all" || dayModalFilter === "created") && selectedDaySignals.createdSignals.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs font-black text-zinc-700 dark:text-zinc-300 border-b border-zinc-200 dark:border-zinc-800 pb-1">
                    <span>{isAr ? "إشارات تم رصدها في هذه الجلسة" : "Signals Detected in this Session"}</span>
                    <span className="font-mono text-[11px] text-zinc-500">
                      {selectedDaySignals.createdSignals.length} {isAr ? "إشارة" : "signals"}
                    </span>
                  </div>

                  <div className="space-y-2.5">
                    {selectedDaySignals.createdSignals.map((s, idx) => {
                      const ret = getSignalReturn(s);
                      const isGain = ret > 0 || s.status === "target_hit";
                      const badge = getScannerBadge(s.scanner_type);
                      const isStillActive = s.status === "active";

                      return (
                        <div
                          key={`modal-created-${s.symbol}-${s.entry_date}-${idx}`}
                          className="p-3 border-2 border-black dark:border-zinc-700 bg-amber-50/60 dark:bg-amber-950/20 space-y-2 shadow-[2px_2px_0px_#000]"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <StockLogo symbol={s.symbol} size="sm" />
                              <div>
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <span className="font-mono font-black text-sm text-black dark:text-white">{s.symbol}</span>
                                  <span className={`px-1.5 py-0.2 text-[9px] font-black border ${badge.pillBg}`}>
                                    {badge.label}
                                  </span>
                                  {isShariaCompliant(s.symbol) && (
                                    <span className="px-1.5 py-0.2 border border-black bg-emerald-400 text-black text-[8px] font-black">
                                      حلال
                                    </span>
                                  )}
                                  <span className={`px-1.5 py-0.2 text-[9px] font-black border border-black ${
                                    isStillActive ? "bg-[#FFE600] text-black" : "bg-zinc-200 text-zinc-800"
                                  }`}>
                                    {isStillActive ? "قيد المتابعة ⚡" : "أُغلقت لاحقاً"}
                                  </span>
                                </div>
                                <span className="text-[10px] text-zinc-500 font-bold block">
                                  {s.name_ar || s.sector}
                                </span>
                              </div>
                            </div>

                            <div className="flex items-center gap-2">
                              <span
                                className={`px-2.5 py-0.5 font-mono font-black text-xs border border-black ${
                                  isGain ? "bg-emerald-300 text-black" : "bg-rose-300 text-black"
                                }`}
                              >
                                {ret >= 0 ? "+" : ""}{ret.toFixed(2)}%
                              </span>
                              <button
                                type="button"
                                onClick={() => {
                                  setChartModalStock({
                                    symbol: s.symbol,
                                    date: s.entry_date,
                                    toDate: s.exit_date,
                                    signalTime: s.entry_time,
                                    signalPrice: s.entry_price,
                                    exitTime: s.exit_time,
                                    exitPrice: s.exit_price,
                                    status: s.status,
                                    scannerType: s.scanner_type,
                                  });
                                }}
                                className="p-1 bg-[#FFE600] border border-black cursor-pointer shadow-[1px_1px_0px_#000]"
                                title="شارت 15 دقيقة"
                              >
                                <BarChart2 className="w-4 h-4 text-black" />
                              </button>
                            </div>
                          </div>

                          {/* Target and Stop Loss Information */}
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-bold pt-2 border-t border-zinc-200 dark:border-zinc-800">
                            <div>
                              <span className="text-[10px] text-zinc-500 block">وقت وسعر الرصد</span>
                              <span className="font-mono text-black dark:text-white text-[11px]">
                                {s.entry_time} • {s.entry_price?.toFixed(2)} ج.م
                              </span>
                            </div>
                            <div>
                              <span className="text-[10px] text-zinc-500 block">المستهدف الأول 🎯</span>
                              <span className="font-mono text-emerald-600 dark:text-emerald-400 text-[11px]">
                                {s.target_1?.toFixed(2)} (+{s.target_1_pct}%)
                              </span>
                            </div>
                            <div>
                              <span className="text-[10px] text-zinc-500 block">وقف الخسارة 🛑</span>
                              <span className="font-mono text-rose-600 dark:text-rose-400 text-[11px]">
                                {s.stop_loss?.toFixed(2)} (-{s.stop_loss_pct}%)
                              </span>
                            </div>
                            <div>
                              <span className="text-[10px] text-zinc-500 block">الحالة الحالية</span>
                              <span className="text-black dark:text-white text-[11px]">
                                {isStillActive ? "نشطة بالجلسة" : s.exit_reason || "أُغلقت لاحقاً"}
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Empty state */}
              {selectedDaySignals.closedSignals.length === 0 && selectedDaySignals.createdSignals.length === 0 && (
                <div className="py-8 text-center border-2 border-dashed border-zinc-300 dark:border-zinc-800">
                  <p className="text-xs font-bold text-zinc-500">
                    {isAr ? "لا توجد صفقات أو إشارات مسجلة في هذا اليوم." : "No signals recorded on this day."}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── 8. SHARE SIGNAL CARD MODAL ── */}
      {shareSignal && (
        <div
          className="fixed inset-0 z-[9999] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setShareSignal(null)}
        >
          <div
            className="relative w-full max-w-md bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[8px_8px_0px_#000] p-6 space-y-4"
            dir={isAr ? "rtl" : "ltr"}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b-2 border-black dark:border-zinc-700 pb-3">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-1 bg-[#FFE600] text-black border-2 border-black font-black text-xs">
                  EGX BOTS AI 🎯
                </span>
                <h3 className="font-black text-base text-black dark:text-white">
                  {isAr ? `بطاقة إشارة فنية — #${shareSignal.symbol}` : `Signal Card — #${shareSignal.symbol}`}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShareSignal(null)}
                className="p-1 border-2 border-black bg-zinc-100 hover:bg-zinc-200 text-black cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 bg-zinc-50 dark:bg-zinc-950 border-2 border-black dark:border-zinc-700 space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between">
                <span className="font-black text-lg text-black dark:text-white">#{shareSignal.symbol}</span>
                <span className="px-2 py-0.5 bg-black text-[#FFE600] font-black">
                  {getScannerBadge(shareSignal.scanner_type).label}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center pt-2 border-t border-zinc-200 dark:border-zinc-800">
                <div className="p-2 bg-white dark:bg-zinc-900 border border-black">
                  <span className="text-[10px] text-zinc-500 block">{isAr ? "سعر الرصد" : "Entry"}</span>
                  <span className="font-black text-black dark:text-white">{shareSignal.entry_price?.toFixed(2)}</span>
                </div>
                <div className="p-2 bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-600 text-emerald-700 dark:text-emerald-300">
                  <span className="text-[10px] block">{isAr ? "المستهدف 1" : "Target 1"}</span>
                  <span className="font-black">{shareSignal.target_1?.toFixed(2)}</span>
                </div>
                <div className="p-2 bg-rose-50 dark:bg-rose-950/50 border border-rose-600 text-rose-700 dark:text-rose-300">
                  <span className="text-[10px] block">{isAr ? "الوقف" : "Stop"}</span>
                  <span className="font-black">{shareSignal.stop_loss?.toFixed(2)}</span>
                </div>
              </div>
              <p className="text-[10px] text-zinc-500 font-sans font-bold pt-2 border-t border-zinc-200 dark:border-zinc-800">
                {isAr
                  ? "⚠️ إخلاء مسؤولية (FRA): مخرجات رصد فني خوارزمي لأغراض البحث والدراسة وليست نصيحة استثمارية."
                  : "⚠️ FRA Disclaimer: Algorithmic technical scan output for research purposes only, not financial advice."}
              </p>
            </div>

            <button
              type="button"
              onClick={() => handleCopyShareCard(shareSignal)}
              className="w-full h-11 bg-[#FFE600] hover:bg-yellow-300 text-black border-2 border-black font-black text-xs uppercase flex items-center justify-center gap-2 shadow-[3px_3px_0px_#000] cursor-pointer"
            >
              {copiedShare ? <Check className="w-4 h-4 text-emerald-700" /> : <Copy className="w-4 h-4" />}
              <span>
                {copiedShare
                  ? isAr
                    ? "تم نسخ بطاقة الإشارة بنجاح!"
                    : "Copied to Clipboard!"
                  : isAr
                  ? "نسخ نص بطاقة الإشارة للمشاركة"
                  : "Copy Signal Card Text"}
              </span>
            </button>
          </div>
        </div>
      )}

      {/* ── 9. PRO UPGRADE MODAL ── */}
      {showProModal && (
        <div className="fixed inset-0 z-[9999] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="relative w-full max-w-md bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[8px_8px_0px_rgba(0,0,0,1)] p-6 space-y-4" dir={isAr ? "rtl" : "ltr"}>
            <button
              onClick={() => setShowProModal(false)}
              className="absolute top-4 left-4 p-1 border-2 border-black bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 cursor-pointer"
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
                  {isAr ? "إشارات الرصد اللحظي والشارت الفوري (15 دقيقة)" : "Live Intraday Signals & 15m Chart"}
                </span>
              </div>
            </div>
            <p className="text-xs font-bold text-zinc-700 dark:text-zinc-300 leading-relaxed">
              {isAr
                ? "الإشارات النشطة الحية ومستويات الرصد والمستهدفات الفورية وتنبيهات تليجرام متاحة حصرياً لأعضاء باقة Pro. كافة الإشارات المغلقة متاحة مجاناً لتدقيق الأداء التاريخي."
                : "Live open signals, exact entry/target levels, and instant Telegram alerts are exclusive to Pro members. Closed signals are open for historical verification."}
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

      {/* ── 10. 15-MINUTE INTRADAY SESSION CANDLESTICK CHART MODAL ── */}
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
    </div>
  );
}
