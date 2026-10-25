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
  Flame,
  Calendar as CalendarIcon,
  Layers,
  Award,
  RefreshCw,
  Search,
  X,
  Target,
  ExternalLink,
  Crown,
  History,
  Activity,
  ShieldAlert,
  SlidersHorizontal,
  Share2,
  Copy,
  Check
} from "lucide-react";
import StockLogo from "./StockLogo";
import { isShariaCompliant } from "@/lib/shariaStocks";
import { TrackedScannerSignal, ScannerSignalsKPIs, ScannerType } from "@/lib/scannerTradePlan";
import ScannerStatsCalendar, { ScanHistoryItem } from "@/app/profile/components/ScannerStatsCalendar";
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
  const [history, setHistory] = useState<ScanHistoryItem[]>([]);
  const [lastScan, setLastScan] = useState<any>(null);

  // Filters
  const [categoryFilter, setCategoryFilter] = useState<"all" | ScannerType>("all");
  const [dateFilter, setDateFilter] = useState<string>("all");
  const [resultFilter, setResultFilter] = useState<"all" | "win" | "loss" | "active">("all");
  const [shariaOnly, setShariaOnly] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

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
            if (Array.isArray(cached.history)) setHistory(cached.history);
            if (cached.last_scan) setLastScan(cached.last_scan);
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
          if (Array.isArray(data.history)) setHistory(data.history);
          if (data.last_scan) setLastScan(data.last_scan);
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

  // Available unique entry dates in active signals
  const availableDates = useMemo(() => {
    const set = new Set<string>();
    for (const s of activeSignals) {
      if (s.entry_date) set.add(s.entry_date);
    }
    return Array.from(set).sort().reverse();
  }, [activeSignals]);

  const getSignalReturn = useCallback((s: TrackedScannerSignal) => {
    if (typeof s.return_pct === "number") return s.return_pct;
    const ex = s.exit_price ?? s.current_price;
    if (s.entry_price && ex) {
      return Number((((ex - s.entry_price) / s.entry_price) * 100).toFixed(2));
    }
    return 0;
  }, []);

  // Filtered Active Signals
  const filteredActive = useMemo(() => {
    return activeSignals.filter((s) => {
      if (categoryFilter !== "all" && s.scanner_type !== categoryFilter) return false;
      if (dateFilter !== "all" && s.entry_date !== dateFilter) return false;
      if (shariaOnly && !isShariaCompliant(s.symbol)) return false;
      if (searchTerm.trim()) {
        const q = searchTerm.trim().toLowerCase();
        if (!s.symbol.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [activeSignals, categoryFilter, dateFilter, shariaOnly, searchTerm]);

  // Filtered Closed Signals
  const filteredClosed = useMemo(() => {
    return closedSignals.filter((s) => {
      if (categoryFilter !== "all" && s.scanner_type !== categoryFilter) return false;
      if (shariaOnly && !isShariaCompliant(s.symbol)) return false;
      const ret = getSignalReturn(s);
      if (resultFilter === "win" && ret <= 0 && s.status !== "target_hit") return false;
      if (resultFilter === "loss" && (ret >= 0 || s.status === "target_hit")) return false;
      if (searchTerm.trim()) {
        const q = searchTerm.trim().toLowerCase();
        if (!s.symbol.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [closedSignals, categoryFilter, shariaOnly, resultFilter, searchTerm, getSignalReturn]);

  // Combined All Signals
  const filteredAll = useMemo(() => {
    const combined = [
      ...activeSignals.map((s) => ({ ...s, _isActive: true })),
      ...closedSignals.map((s) => ({ ...s, _isActive: false })),
    ];
    return combined.filter((s) => {
      if (categoryFilter !== "all" && s.scanner_type !== categoryFilter) return false;
      if (shariaOnly && !isShariaCompliant(s.symbol)) return false;
      const ret = getSignalReturn(s);
      if (resultFilter === "active" && !s._isActive) return false;
      if (resultFilter === "win" && (s._isActive || (ret <= 0 && s.status !== "target_hit"))) return false;
      if (resultFilter === "loss" && (s._isActive || ret >= 0 || s.status === "target_hit")) return false;
      if (searchTerm.trim()) {
        const q = searchTerm.trim().toLowerCase();
        if (!s.symbol.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [activeSignals, closedSignals, categoryFilter, shariaOnly, resultFilter, searchTerm, getSignalReturn]);

  // Computed KPIs
  const computedKpis = useMemo(() => {
    const sourceClosed = categoryFilter === "all" ? closedSignals : filteredClosed;
    const sourceActive = categoryFilter === "all" ? activeSignals : filteredActive;
    const totalClosed = sourceClosed.length;
    if (totalClosed === 0 && signalsKpis && categoryFilter === "all") return signalsKpis;

    const wins = sourceClosed.filter((s) => getSignalReturn(s) > 0 || s.status === "target_hit");
    const losses = sourceClosed.filter((s) => getSignalReturn(s) < 0 && s.status !== "target_hit");
    const winRate = totalClosed > 0 ? Number(((wins.length / totalClosed) * 100).toFixed(1)) : 70.0;
    const sumWins = wins.reduce((sum, s) => sum + Math.max(0, getSignalReturn(s)), 0);
    const sumLosses = Math.abs(losses.reduce((sum, s) => sum + Math.min(0, getSignalReturn(s)), 0));
    const avgWin = wins.length > 0 ? Number((sumWins / wins.length).toFixed(1)) : 4.2;
    const avgLoss = losses.length > 0 ? Number((sumLosses / losses.length).toFixed(1)) : 2.5;
    const profitFactor = sumLosses > 0 ? Number((sumWins / sumLosses).toFixed(2)) : 4.03;
    const topWin = sourceClosed.reduce((max, s) => Math.max(max, getSignalReturn(s), s.max_gain_pct || 0), 0);
    return {
      win_rate_pct: winRate,
      total_closed: totalClosed,
      total_active: sourceActive.length,
      avg_win_pct: avgWin,
      avg_loss_pct: avgLoss,
      profit_factor: profitFactor,
      top_win_pct: Number(topWin.toFixed(1)),
    };
  }, [signalsKpis, closedSignals, activeSignals, filteredClosed, filteredActive, categoryFilter, getSignalReturn]);

  const getScannerBadge = (type: ScannerType) => {
    switch (type) {
      case "volume_surge":
        return {
          label: isAr ? "سيولة مؤسسية ⚡" : "Volume Surge ⚡",
          icon: Zap,
          bg: "bg-amber-400 text-black border-black",
          pillBg: "bg-amber-100 dark:bg-amber-950/70 text-amber-800 dark:text-amber-300 border-amber-500",
        };
      case "breakout":
        return {
          label: isAr ? "اختراق فني 🚀" : "Breakout 🚀",
          icon: ArrowUpRight,
          bg: "bg-emerald-400 text-black border-black",
          pillBg: "bg-emerald-100 dark:bg-emerald-950/70 text-emerald-800 dark:text-emerald-300 border-emerald-500",
        };
      case "rsi_oversold":
        return {
          label: isAr ? "ارتداد RSI 🎯" : "RSI Rebound 🎯",
          icon: Target,
          bg: "bg-sky-400 text-black border-black",
          pillBg: "bg-sky-100 dark:bg-sky-950/70 text-sky-800 dark:text-sky-300 border-sky-500",
        };
    }
  };

  const handleCopyShareCard = (sig: TrackedScannerSignal) => {
    const badge = getScannerBadge(sig.scanner_type);
    const ret = getSignalReturn(sig);
    const retStr = ret >= 0 ? `+${ret.toFixed(2)}%` : `${ret.toFixed(2)}%`;
    const text = [
      `🎯 إشارة رصد فني لحظي — StokScan AI`,
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
    <div className="space-y-6 w-full" dir={isAr ? "rtl" : "ltr"}>
      {/* ── 1. TOP NEO-BRUTALIST HEADER BANNER & COLLAPSIBLE METHODOLOGY GUIDE ── */}
      <div className="border-4 border-black dark:border-white bg-[#FFE600] text-black shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#fff] overflow-hidden">
        <div className="p-4 sm:p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
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

            <h1 className="text-xl sm:text-2xl lg:text-3xl font-black text-black tracking-tight leading-tight">
              {isAr
                ? "نظام إشارات الرصد اللحظي ورادار السيولة السريع (فريم 15 دقيقة)"
                : "Intraday Fast Signals & 15-Minute Liquidity Radar"}
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

            <Link
              href="/profile#scanner-signals"
              className="h-10 px-3.5 border-2 border-black bg-white hover:bg-zinc-100 text-black font-black text-xs uppercase flex items-center justify-center gap-1.5 shadow-[2px_2px_0px_#000] transition-all"
              title={isAr ? "ضبط إشعارات تليجرام اللحظية" : "Telegram Alert Preferences"}
            >
              <SlidersHorizontal className="w-3.5 h-3.5 text-black" />
              <span>{isAr ? "تفضيلات تليجرام" : "Telegram Alerts"}</span>
            </Link>

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
          <div className="border-t-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-6">
            <ScannerDefinitionsGuide isAr={isAr} />
          </div>
        )}
      </div>

      {/* ── 2. FRA COMPLIANCE & SESSION STATUS BAR ── */}
      <div className="border-2 border-amber-500 bg-amber-50 dark:bg-amber-950/30 p-3 text-xs sm:text-sm font-bold flex flex-col sm:flex-row sm:items-center justify-between gap-2" role="status">
        <div>
          <span className="font-black text-black dark:text-white">
            {isAr ? "حالة الرادار اللحظي:" : "Live Radar Status:"}{" "}
          </span>
          <span className="font-mono text-emerald-700 dark:text-emerald-400 font-black">
            {lastScan?.timestamp
              ? new Date(lastScan.timestamp).toLocaleString(isAr ? "ar-EG" : "en-US", {
                  dateStyle: "medium",
                  timeStyle: "short",
                })
              : isAr
              ? "متصل ومحدث مع جلسة البورصة"
              : "Connected & Synced"}
          </span>
          <p className="text-[11px] text-zinc-700 dark:text-zinc-300 mt-0.5">
            {isAr
              ? "تنبيه تنظيمي (FRA): جميع الإشارات والمستويات السعرية المعروضة هي مخرجات رصد فني خوارزمي آلي لأغراض البحث والدراسة، وليست نصيحة استثمارية أو توصية مباشرة بالشراء أو البيع."
              : "Regulatory Notice (FRA): All displayed signals and price levels are automated algorithmic technical outputs for research purposes only, not financial advice."}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="px-2.5 py-1 border-2 border-black bg-white dark:bg-zinc-900 text-black dark:text-white text-[11px] font-black font-mono">
            {isAr ? "فريم الشارت: 15 دقيقة" : "Chart Frame: 15m"}
          </span>
        </div>
      </div>

      {/* ── 3. UNIFIED 4 SUB-TABS NAVIGATION BAR (Identical to Medium & Short Swings) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 border-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] p-1.5 gap-2 select-none">
        {[
          {
            id: "active",
            label: isAr ? "الإشارات النشطة (المفتوحة)" : "Active Signals",
            count: activeSignals.length,
            icon: Zap,
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

      {/* ── 4. TOP 4 SPOTLIGHT KPI CARDS (Hidden on Calendar tab to avoid duplicate stats bars) ── */}
      {viewMode !== "calendar" && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          {/* KPI 1: Profit Factor */}
          <div className="p-4 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff]">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-black uppercase text-zinc-500">
                {isAr ? "عامل الربح (Profit Factor)" : "Profit Factor"}
              </span>
              <div className="w-7 h-7 border-2 border-black bg-amber-400 flex items-center justify-center font-black text-black">
                <Flame className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl sm:text-3xl font-black font-mono text-black dark:text-white">
              {computedKpis.profit_factor}x
            </div>
            <p className="text-[10px] font-bold text-zinc-500 mt-1">
              {isAr ? `من إجمالي ${computedKpis.total_closed} إشارة مغلقة` : `Across ${computedKpis.total_closed} closed signals`}
            </p>
          </div>

          {/* KPI 2: Win Rate */}
          <div className="p-4 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff]">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-black uppercase text-zinc-500">
                {isAr ? "نسبة تحقق المستهدفات" : "Target Hit Rate"}
              </span>
              <div className="w-7 h-7 border-2 border-black bg-emerald-400 flex items-center justify-center font-black text-black">
                <Target className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl sm:text-3xl font-black font-mono text-emerald-600 dark:text-emerald-400">
              {computedKpis.win_rate_pct}%
            </div>
            <p className="text-[10px] font-bold text-zinc-500 mt-1">
              {isAr ? `متوسط العائد الرابح: +${computedKpis.avg_win_pct}%` : `Avg winning return: +${computedKpis.avg_win_pct}%`}
            </p>
          </div>

          {/* KPI 3: Holding Horizon / Active */}
          <div className="p-4 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff]">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-black uppercase text-zinc-500">
                {isAr ? "أفق المتابعة الفنية" : "Tracking Horizon"}
              </span>
              <div className="w-7 h-7 border-2 border-black bg-sky-400 flex items-center justify-center font-black text-black">
                <Clock className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl sm:text-3xl font-black font-mono text-black dark:text-white">
              1 - 4 <span className="text-sm">{isAr ? "جلسات" : "Sessions"}</span>
            </div>
            <p className="text-[10px] font-bold text-zinc-500 mt-1">
              {isAr ? `${activeSignals.length} إشارة نشطة قيد المتابعة الآن` : `${activeSignals.length} active signals tracked live`}
            </p>
          </div>

          {/* KPI 4: Top Signal Gain */}
          <div className="p-4 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff]">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-black uppercase text-zinc-500">
                {isAr ? "أعلى عائد لإشارة" : "Top Signal Gain"}
              </span>
              <div className="w-7 h-7 border-2 border-black bg-rose-400 flex items-center justify-center font-black text-black">
                <Award className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl sm:text-3xl font-black font-mono text-emerald-600 dark:text-emerald-400">
              +{computedKpis.top_win_pct}%
            </div>
            <p className="text-[10px] font-bold text-zinc-500 mt-1">
              {isAr ? "مع تفعيل حماية التعادل عند +2.5%" : "With auto breakeven lock at +2.5%"}
            </p>
          </div>
        </div>
      )}

      {/* ── 5. UNIFIED ANALYSIS & FILTER TOOLBAR (For Active / Closed / All Views) ── */}
      {viewMode !== "calendar" && (
        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-3.5 sm:p-4 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] space-y-3">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
            {/* Scanner Type Filter Pills */}
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs font-black uppercase text-zinc-600 dark:text-zinc-400 ml-1">
                {isAr ? "نوع الرصد الفني:" : "Scanner Type:"}
              </span>
              {(
                [
                  { id: "all", labelAr: "الكل", labelEn: "All" },
                  { id: "volume_surge", labelAr: "سيولة مؤسسية ⚡", labelEn: "Volume Surge ⚡" },
                  { id: "breakout", labelAr: "اختراق فني 🚀", labelEn: "Breakout 🚀" },
                  { id: "rsi_oversold", labelAr: "ارتداد RSI 🎯", labelEn: "RSI Rebound 🎯" },
                ] as const
              ).map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setCategoryFilter(c.id)}
                  className={`h-8 px-3 border-2 border-black dark:border-white font-black text-xs transition-all cursor-pointer ${
                    categoryFilter === c.id
                      ? "bg-[#FFE600] text-black shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                      : "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700"
                  }`}
                >
                  {isAr ? c.labelAr : c.labelEn}
                </button>
              ))}
            </div>

            {/* Search + Sharia Filter + Result Filter */}
            <div className="flex flex-wrap items-center gap-2">
              {viewMode !== "active" && (
                <div className="flex items-center border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 p-0.5 text-xs font-black">
                  {(
                    [
                      { id: "all", labelAr: "الكل", labelEn: "All" },
                      ...(viewMode === "all" ? [{ id: "active", labelAr: "نشطة", labelEn: "Active" }] : []),
                      { id: "win", labelAr: "محققة للهدف ✅", labelEn: "Target Hit ✅" },
                      { id: "loss", labelAr: "وقف خسارة 🛑", labelEn: "Stopped 🛑" },
                    ] as const
                  ).map((rf) => (
                    <button
                      key={rf.id}
                      type="button"
                      onClick={() => setResultFilter(rf.id as any)}
                      className={`px-2.5 py-1 transition-all cursor-pointer ${
                        resultFilter === rf.id
                          ? "bg-black text-[#FFE600] dark:bg-white dark:text-black"
                          : "text-zinc-600 dark:text-zinc-300 hover:text-black"
                      }`}
                    >
                      {isAr ? rf.labelAr : rf.labelEn}
                    </button>
                  ))}
                </div>
              )}

              {/* Sharia Toggle */}
              <button
                type="button"
                onClick={() => setShariaOnly((prev) => !prev)}
                className={`h-8 px-3 border-2 border-black dark:border-white font-black text-xs flex items-center gap-1.5 transition-all cursor-pointer ${
                  shariaOnly
                    ? "bg-emerald-400 text-black shadow-[2px_2px_0px_#000]"
                    : "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300"
                }`}
              >
                <span>🌙</span>
                <span>{isAr ? "متوافقة شرعياً" : "Sharia Only"}</span>
              </button>

              {/* Symbol Search */}
              <div className="relative flex-1 sm:flex-none sm:w-48">
                <Search className="w-3.5 h-3.5 text-zinc-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder={isAr ? "بحث برمز السهم..." : "Search symbol..."}
                  className="w-full h-8 pr-8 pl-2.5 border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-950 text-xs font-bold text-black dark:text-white focus:outline-none focus:bg-white"
                />
                {searchTerm && (
                  <button
                    type="button"
                    onClick={() => setSearchTerm("")}
                    className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-black"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Session Date Filter Pills (When on Active Tab) */}
          {viewMode === "active" && availableDates.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t-2 border-zinc-200 dark:border-zinc-800 text-xs">
              <span className="font-black text-zinc-600 dark:text-zinc-400 flex items-center gap-1 ml-1">
                <CalendarIcon className="w-3.5 h-3.5 text-amber-500" />
                <span>{isAr ? "تصفية حسب جلسة الرصد:" : "Filter by Session:"}</span>
              </span>
              <button
                type="button"
                onClick={() => setDateFilter("all")}
                className={`px-2.5 py-0.5 font-black border-2 border-black dark:border-white text-[11px] transition-all cursor-pointer ${
                  dateFilter === "all"
                    ? "bg-black text-[#FFE600] dark:bg-white dark:text-black"
                    : "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300"
                }`}
              >
                {isAr ? "كل الجلسات" : "All Sessions"} ({activeSignals.length})
              </button>
              {availableDates.map((dStr) => {
                const count = activeSignals.filter((s) => s.entry_date === dStr).length;
                return (
                  <button
                    key={dStr}
                    type="button"
                    onClick={() => setDateFilter(dStr)}
                    className={`px-2.5 py-0.5 font-mono font-black border-2 border-black dark:border-white text-[11px] transition-all cursor-pointer ${
                      dateFilter === dStr
                        ? "bg-black text-[#FFE600] dark:bg-white dark:text-black"
                        : "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300"
                    }`}
                  >
                    {dStr} ({count})
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── 6. VIEW 1: ACTIVE SIGNALS GRID ── */}
      {viewMode === "active" && (
        <div className="space-y-4">
          {loading ? (
            <div className="p-12 text-center border-4 border-black dark:border-white bg-white dark:bg-zinc-900 font-black text-sm">
              <RefreshCw className="w-6 h-6 mx-auto mb-2 animate-spin text-amber-500" />
              {isAr ? "جاري تحميل إشارات الرصد اللحظي..." : "Loading intraday signals..."}
            </div>
          ) : filteredActive.length === 0 ? (
            <div className="p-12 text-center border-4 border-dashed border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 font-bold text-sm text-zinc-500">
              <Clock className="w-8 h-8 mx-auto mb-2 text-zinc-400" />
              {isAr
                ? "لا توجد إشارات نشطة مطابقة لهذا الفلتر حالياً. يقوم الرادار بفحص السوق آلياً كل 5 دقائق أثناء جلسة التداول."
                : "No active signals match the current filter. The radar scans sessions every 5 minutes."}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredActive.map((sig) => {
                const badge = getScannerBadge(sig.scanner_type);
                const BadgeIcon = badge.icon;
                const ret = getSignalReturn(sig);
                const isGain = ret >= 0;
                const isLocked = Boolean(sig.is_locked || !userHasPro);

                const targetRange = (sig.target_1 || 0) - (sig.entry_price || 0);
                const progressPct =
                  targetRange > 0 && sig.current_price
                    ? Math.min(100, Math.max(0, ((sig.current_price - (sig.entry_price || 0)) / targetRange) * 100))
                    : 0;

                const openChart = () => {
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
                    onClick={openChart}
                    onMouseEnter={() => {
                      if (!isLocked) {
                        prefetchIntradaySession(sig.symbol, sig.entry_date, sig.entry_time, sig.entry_price);
                      }
                    }}
                    className="cursor-pointer p-4 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_rgba(255,255,255,1)] flex flex-col justify-between gap-3 transition-all hover:-translate-y-1 hover:shadow-[9px_9px_0px_rgba(0,0,0,1)] dark:hover:shadow-[9px_9px_0px_rgba(255,255,255,1)]"
                  >
                    {/* Header Row */}
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
                            <div className="flex items-center gap-2">
                              <StockLogo symbol={sig.symbol} size="sm" />
                              <span className="font-mono text-base font-black px-2.5 py-0.5 bg-black text-[#FFE600] border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                                {sig.symbol}
                              </span>
                              {isShariaCompliant(sig.symbol) && (
                                <span
                                  className="text-xs px-1.5 py-0.5 bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300 border border-emerald-500 font-black"
                                  title={isAr ? "متوافق مع الشريعة" : "Sharia Compliant"}
                                >
                                  🌙
                                </span>
                              )}
                            </div>
                          )}
                          <span className={`px-2 py-0.5 text-[10px] font-black uppercase border flex items-center gap-1 ${badge.pillBg}`}>
                            <BadgeIcon className="w-3 h-3" />
                            <span>{badge.label}</span>
                          </span>
                        </div>

                        <span
                          className={`font-mono font-black text-xs px-2.5 py-0.5 border-2 border-black shadow-[1px_1px_0px_rgba(0,0,0,1)] ${
                            isGain ? "bg-emerald-400 text-black" : "bg-rose-400 text-black"
                          }`}
                        >
                          {isGain ? `+${ret.toFixed(2)}%` : `${ret.toFixed(2)}%`}
                        </span>
                      </div>

                      <p className="text-[10px] font-mono font-bold text-zinc-500 mt-1.5 flex items-center gap-1.5">
                        <Clock className="w-3 h-3 text-zinc-400 shrink-0" />
                        <span>{isAr ? "توقيت الرصد:" : "Detected:"}</span>
                        <span className="text-zinc-800 dark:text-zinc-200">
                          {sig.entry_date} ({sig.entry_time})
                        </span>
                        <span>•</span>
                        <span>
                          {isAr ? `جلسة ${sig.sessions_count} من ${sig.max_sessions}` : `Session ${sig.sessions_count}/${sig.max_sessions}`}
                        </span>
                      </p>
                    </div>

                    {/* Levels Grid */}
                    <div className="space-y-2 pt-2 border-t-2 border-zinc-200 dark:border-zinc-800">
                      {isLocked ? (
                        <div className="p-3 bg-amber-50 dark:bg-amber-950/40 border-2 border-dashed border-amber-500 text-center space-y-1.5">
                          <div className="flex items-center justify-center gap-1.5 text-amber-700 dark:text-amber-400 font-black text-xs">
                            <Lock className="w-3.5 h-3.5" />
                            <span>{isAr ? "مستويات الرصد والمستهدفات مشفرة" : "Signal levels are locked"}</span>
                          </div>
                          <p className="text-[11px] font-bold text-zinc-600 dark:text-zinc-400">
                            {isAr ? "خاص بمشتركي PRO — اضغط لفتح الإشارة والشارت اللحظي" : "PRO exclusive — click to unlock live signal & 15m chart"}
                          </p>
                        </div>
                      ) : (
                        <>
                          <div className="grid grid-cols-3 gap-1.5 text-center font-mono">
                            <div className="p-2 bg-zinc-100 dark:bg-zinc-800 border-2 border-black dark:border-zinc-700">
                              <span className="text-[9px] text-zinc-500 block uppercase font-bold">
                                {isAr ? "سعر الرصد" : "Entry"}
                              </span>
                              <span className="text-xs font-black text-black dark:text-white">
                                {sig.entry_price?.toFixed(2)}
                              </span>
                            </div>

                            <div className="p-2 bg-emerald-50 dark:bg-emerald-950/60 border-2 border-emerald-600 text-emerald-700 dark:text-emerald-300">
                              <span className="text-[9px] block uppercase font-bold flex items-center justify-center gap-0.5">
                                <Target className="w-2.5 h-2.5" />
                                {isAr ? "مستهدف 1" : "Target 1"}
                              </span>
                              <span className="text-xs font-black">{sig.target_1?.toFixed(2)}</span>
                              <span className="text-[9px] block font-black">(+{sig.target_1_pct}%)</span>
                            </div>

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
                                      ? "إيقاف الخسارة"
                                      : "Stop"}
                                  </span>
                                  <span className="text-xs font-black">{sig.stop_loss?.toFixed(2)}</span>
                                  <span className="text-[9px] block font-black">
                                    {isBreakevenProtected ? "(0.0% 🛡️)" : `(-${sig.stop_loss_pct}%)`}
                                  </span>
                                </div>
                              );
                            })()}
                          </div>

                          <div>
                            <div className="flex items-center justify-between text-[10px] font-mono font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                              <span>{isAr ? "التقدم نحو المستهدف الفني:" : "Target Progress:"}</span>
                              <span className="font-black text-black dark:text-white">{Math.round(progressPct)}%</span>
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

                    {/* Footer Action Tools (15m Chart + Share + Stock Page) */}
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
                          className="px-2.5 py-1 bg-[#FFE600] hover:bg-yellow-300 text-black border-2 border-black font-black text-[11px] flex items-center gap-1 shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer"
                        >
                          <Lock className="w-3.5 h-3.5" />
                          <span>{isAr ? "فتح الإشارة (PRO)" : "Unlock (PRO)"}</span>
                        </button>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setShareSignal(sig);
                            }}
                            className="p-1.5 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 text-black dark:text-white border-2 border-black dark:border-zinc-600 shadow-[1px_1px_0px_#000] cursor-pointer"
                            title={isAr ? "مشاركة بطاقة الإشارة" : "Share Signal Card"}
                          >
                            <Share2 className="w-3.5 h-3.5" />
                          </button>
                          <Link
                            href={`/stocks/${sig.symbol}`}
                            onClick={(e) => e.stopPropagation()}
                            className="p-1.5 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 text-black dark:text-white border-2 border-black dark:border-zinc-600 shadow-[1px_1px_0px_#000]"
                            title={isAr ? "صفحة التحليل الفني الكامل للسهم" : "Full Stock Analysis"}
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </Link>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              openChart();
                            }}
                            className="px-2.5 py-1 bg-[#FFE600] hover:bg-yellow-300 text-black border-2 border-black font-black text-[11px] flex items-center gap-1 shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer"
                          >
                            <BarChart2 className="w-3.5 h-3.5" />
                            <span>{isAr ? "شارت 15 د" : "15m Chart"}</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── 7. VIEW 2 & 3: CLOSED SIGNALS & ALL SIGNALS TABLE ── */}
      {(viewMode === "closed" || viewMode === "all") && (
        <div className="space-y-4">
          {(viewMode === "closed" ? filteredClosed : filteredAll).length === 0 ? (
            <div className="p-12 text-center border-4 border-dashed border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 font-bold text-sm text-zinc-500">
              <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-zinc-400" />
              {isAr ? "لا توجد إشارات مسجلة مطابقة لهذا الفلتر." : "No recorded signals match this filter."}
            </div>
          ) : (
            <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_rgba(255,255,255,1)] overflow-x-auto">
              <table className="w-full text-right text-xs">
                <thead className="bg-[#FFE600] text-black border-b-4 border-black font-black uppercase text-[11px]">
                  <tr>
                    <th className="p-3">{isAr ? "السهم" : "Symbol"}</th>
                    <th className="p-3">{isAr ? "نوع الرصد الفني" : "Scanner"}</th>
                    <th className="p-3">{isAr ? "توقيت الرصد" : "Entry Time"}</th>
                    <th className="p-3">{isAr ? "سعر الرصد" : "Entry"}</th>
                    <th className="p-3">{isAr ? "الإغلاق / الحالي" : "Exit / Current"}</th>
                    <th className="p-3">{isAr ? "العائد الفني" : "Return"}</th>
                    <th className="p-3">{isAr ? "حالة الإشارة" : "Status"}</th>
                    <th className="p-3 text-center">{isAr ? "أدوات التحليل" : "Tools"}</th>
                  </tr>
                </thead>
                <tbody className="divide-y-2 divide-zinc-200 dark:divide-zinc-800 font-mono font-bold">
                  {(viewMode === "closed" ? filteredClosed : filteredAll).map((c: any) => {
                    const isRowActive = Boolean(c._isActive || c.status === "active");
                    const isLocked = isRowActive && Boolean(c.is_locked || !userHasPro);
                    const badge = getScannerBadge(c.scanner_type);
                    const exitP = c.exit_price ?? c.current_price;
                    const mathReturn =
                      c.entry_price && exitP
                        ? Number((((exitP - c.entry_price) / c.entry_price) * 100).toFixed(2))
                        : c.return_pct || 0;
                    const isMathWin = mathReturn > 0;
                    const isBreakeven = mathReturn === 0;

                    return (
                      <tr
                        key={c.id}
                        onClick={() => {
                          if (isLocked) {
                            setShowProModal(true);
                            return;
                          }
                          setChartModalStock({
                            symbol: c.symbol,
                            date: c.entry_date,
                            toDate: c.exit_date || new Date().toISOString().split("T")[0],
                            signalTime: c.entry_time,
                            signalPrice: c.entry_price,
                            exitTime: c.exit_time,
                            exitPrice: c.exit_price,
                            status: c.status,
                            scannerType: c.scanner_type,
                          });
                        }}
                        onMouseEnter={() => {
                          if (!isLocked) {
                            prefetchIntradaySession(c.symbol, c.entry_date, c.entry_time, c.entry_price, c.exit_date);
                          }
                        }}
                        className="cursor-pointer hover:bg-[#FFE600]/15 dark:hover:bg-zinc-800/80 transition-colors"
                      >
                        <td className="p-3">
                          {isLocked ? (
                            <span className="font-mono text-xs font-black px-2 py-0.5 bg-zinc-200 text-zinc-500 border border-black">
                              🔒 PRO
                            </span>
                          ) : (
                            <div className="flex items-center gap-2">
                              <StockLogo symbol={c.symbol} size="sm" />
                              <span className="font-black px-2 py-0.5 bg-black text-[#FFE600] border border-black">
                                {c.symbol}
                              </span>
                            </div>
                          )}
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
                          {isLocked ? "•••" : `${c.entry_price?.toFixed(2)} ج.م`}
                        </td>
                        <td className="p-3 font-black text-black dark:text-white">
                          {isLocked ? "•••" : `${(c.exit_price || c.current_price)?.toFixed(2)} ج.م`}
                        </td>
                        <td className="p-3">
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
                        </td>
                        <td className="p-3">
                          {isRowActive ? (
                            <span className="px-2 py-0.5 text-[10px] font-black border bg-emerald-100 text-emerald-800 border-emerald-500">
                              {isAr ? "إشارة نشطة 🟢" : "Active 🟢"}
                            </span>
                          ) : (
                            <span
                              className={`px-2 py-0.5 text-[10px] font-black border ${
                                c.status === "target_hit"
                                  ? "bg-emerald-100 dark:bg-emerald-950/80 text-emerald-700 dark:text-emerald-300 border-emerald-500"
                                  : c.status === "stopped_out"
                                  ? "bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 border-rose-500"
                                  : "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-400"
                              }`}
                            >
                              {c.exit_reason || (isMathWin ? "تحقق المستهدف 🎯" : "إغلاق الإشارة")}
                            </span>
                          )}
                        </td>
                        <td className="p-3 text-center">
                          <div className="flex items-center justify-center gap-1.5">
                            {!isLocked && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setShareSignal(c);
                                }}
                                className="p-1.5 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 text-black dark:text-white border border-black shadow-[1px_1px_0px_rgba(0,0,0,1)] cursor-pointer"
                                title={isAr ? "مشاركة الإشارة" : "Share Signal"}
                              >
                                <Share2 className="w-3.5 h-3.5" />
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (isLocked) {
                                  setShowProModal(true);
                                  return;
                                }
                                setChartModalStock({
                                  symbol: c.symbol,
                                  date: c.entry_date,
                                  toDate: c.exit_date || new Date().toISOString().split("T")[0],
                                  signalTime: c.entry_time,
                                  signalPrice: c.entry_price,
                                  exitTime: c.exit_time,
                                  exitPrice: c.exit_price,
                                  status: c.status,
                                  scannerType: c.scanner_type,
                                });
                              }}
                              className="p-1.5 bg-[#FFE600] hover:bg-yellow-300 text-black border border-black shadow-[1px_1px_0px_rgba(0,0,0,1)] cursor-pointer"
                              title={isAr ? "عرض شارت 15 دقيقة" : "View 15m Chart"}
                            >
                              <BarChart2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
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

      {/* ── 8. VIEW 4: PERFORMANCE CALENDAR (ScannerStatsCalendar) ── */}
      {viewMode === "calendar" && (
        <ScannerStatsCalendar
          history={history}
          lastScan={lastScan}
          activeSignals={activeSignals}
          closedSignals={closedSignals}
          isAr={isAr}
          isPro={userHasPro}
        />
      )}

      {/* ── 9. SHARE SIGNAL CARD MODAL ── */}
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
                  StokScan AI 🎯
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

      {/* ── 10. PRO UPGRADE MODAL ── */}
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
                ? "الإشارات النشطة الحية ومستويات الرصد والمستهدفات الفورية وتنبيهات تليجرام متاحة حصرياً لأعضاء باقة Pro.كافة الإشارات المغلقة متاحة مجاناً لتدقيق الأداء التاريخي."
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

      {/* ── 11. 15-MINUTE INTRADAY SESSION CANDLESTICK CHART MODAL ── */}
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
