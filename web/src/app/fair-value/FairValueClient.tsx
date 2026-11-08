"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Scale,
  TrendingUp,
  TrendingDown,
  Search,
  Filter,
  Sparkles,
  ShieldCheck,
  Info,
  ArrowUpRight,
  BarChart3,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Calculator,
  ChevronDown,
  ChevronUp,
  BookOpen,
  Flame,
  X,
} from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import type {
  FairValueReport,
  FairValueStockItem,
  FairValueStatus,
} from "@/lib/market/fair-value";

type QuickPreset =
  | "all"
  | "deep_discount"
  | "graham_only"
  | "low_rsi_undervalued";

const POPULAR_SEARCH_SYMBOLS = ["COMI", "TMGH", "SWDY", "FWRY", "ABUK", "FAIT", "EKHO", "ORHD"];

export default function FairValueClient({
  initialReport = null,
}: {
  initialReport?: FairValueReport | null;
}) {
  const { language } = useLanguage();
  const isAr = language === "ar";

  const [report, setReport] = useState<FairValueReport | null>(initialReport);
  const [loading, setLoading] = useState(!initialReport);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | FairValueStatus>("all");
  const [sectorFilter, setSectorFilter] = useState<string>("all");
  const [shariaOnly, setShariaOnly] = useState(false);
  const [quickPreset, setQuickPreset] = useState<QuickPreset>("all");
  const [sortBy, setSortBy] = useState<
    "upside_desc" | "upside_asc" | "pe_asc" | "pb_asc" | "yield_desc"
  >("upside_desc");
  const [chartTab, setChartTab] = useState<"bars" | "zones">("bars");
  const [selectedChartStock, setSelectedChartStock] =
    useState<FairValueStockItem | null>(null);
  const [showAllRows, setShowAllRows] = useState(false);

  useEffect(() => {
    if (initialReport) {
      if (initialReport.stocks?.length) {
        setSelectedChartStock(initialReport.stocks[0]);
      }
      return;
    }
    let active = true;
    async function load() {
      try {
        setLoading(true);
        const res = await fetch("/api/market/fair-value");
        if (!res.ok) throw new Error(isAr ? "تعذر تحميل بيانات السعر العادل" : "Failed to load fair value data");
        const data: FairValueReport = await res.json();
        if (active) {
          setReport(data);
          if (data.stocks?.length) {
            setSelectedChartStock(data.stocks[0]);
          }
        }
      } catch (err: any) {
        if (active) setError(err?.message || (isAr ? "حدث خطأ غير متوقع" : "Unexpected error occurred"));
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [initialReport, isAr]);

  const valuationZones = useMemo(() => {
    const stocks = report?.stocks || [];
    const total = Math.max(1, stocks.length);
    const deepDiscount = stocks.filter((s) => s.upsidePct >= 30).length;
    const undervalued = stocks.filter(
      (s) => s.upsidePct >= 15 && s.upsidePct < 30
    ).length;
    const fair = stocks.filter(
      (s) => s.upsidePct > -12 && s.upsidePct < 15
    ).length;
    const overvalued = stocks.filter(
      (s) => s.upsidePct <= -12 && s.upsidePct > -25
    ).length;
    const extremeOvervalued = stocks.filter((s) => s.upsidePct <= -25).length;

    return [
      {
        id: "deep",
        label: isAr ? "خصم سعري عميق (+30% فأكثر)" : "Deep Discount (>+30%)",
        shortLabel: isAr ? "خصم عميق >+30%" : "Deep >+30%",
        count: deepDiscount,
        pct: Math.round((deepDiscount / total) * 100),
        color: "bg-emerald-500",
        textColor: "text-emerald-600 dark:text-emerald-400",
        borderColor: "border-emerald-500/40",
        onClick: () => {
          setStatusFilter("undervalued");
          setQuickPreset("deep_discount");
        },
      },
      {
        id: "undervalued",
        label: isAr ? "أقل من السعر العادل (+15% إلى +30%)" : "Undervalued (+15% to +30%)",
        shortLabel: isAr ? "فرص صعود +15%..30%" : "Upside +15%..30%",
        count: undervalued,
        pct: Math.round((undervalued / total) * 100),
        color: "bg-teal-500",
        textColor: "text-teal-600 dark:text-teal-400",
        borderColor: "border-teal-500/40",
        onClick: () => {
          setStatusFilter("undervalued");
          setQuickPreset("all");
        },
      },
      {
        id: "fair",
        label: isAr ? "في النطاق العادل (-12% إلى +15%)" : "Fair Valuation (-12% to +15%)",
        shortLabel: isAr ? "نطاق عادل -12%..+15%" : "Fair Range -12%..+15%",
        count: fair,
        pct: Math.round((fair / total) * 100),
        color: "bg-amber-500",
        textColor: "text-amber-600 dark:text-amber-400",
        borderColor: "border-amber-500/40",
        onClick: () => {
          setStatusFilter("fair");
          setQuickPreset("all");
        },
      },
      {
        id: "overvalued",
        label: isAr ? "أعلى من السعر العادل (-12% إلى -25%)" : "Overvalued (-12% to -25%)",
        shortLabel: isAr ? "متضخم -12%..-25%" : "Overvalued -12%..-25%",
        count: overvalued,
        pct: Math.round((overvalued / total) * 100),
        color: "bg-orange-500",
        textColor: "text-orange-600 dark:text-orange-400",
        borderColor: "border-orange-500/40",
        onClick: () => {
          setStatusFilter("overvalued");
          setQuickPreset("all");
        },
      },
      {
        id: "extreme_overvalued",
        label: isAr ? "تضخم سعري مفرط (أقل من -25%)" : "Extreme Overvalued (<-25%)",
        shortLabel: isAr ? "تضخم مفرط <-25%" : "Extreme <-25%",
        count: extremeOvervalued,
        pct: Math.round((extremeOvervalued / total) * 100),
        color: "bg-rose-500",
        textColor: "text-rose-600 dark:text-rose-400",
        borderColor: "border-rose-500/40",
        onClick: () => {
          setStatusFilter("overvalued");
          setQuickPreset("all");
        },
      },
    ];
  }, [report, isAr]);

  const topUndervaluedStocks = useMemo(() => {
    return [...(report?.stocks || [])]
      .filter((s) => s.upsidePct > 5)
      .sort((a, b) => b.upsidePct - a.upsidePct)
      .slice(0, 8);
  }, [report]);

  const topOvervaluedStocks = useMemo(() => {
    return [...(report?.stocks || [])]
      .filter((s) => s.upsidePct < -10)
      .sort((a, b) => a.upsidePct - b.upsidePct)
      .slice(0, 8);
  }, [report]);

  const sectors = useMemo(() => {
    const set = new Set<string>();
    for (const s of report?.stocks || []) {
      if (s.sectorAr) set.add(s.sectorAr);
    }
    return Array.from(set).sort();
  }, [report]);

  const filteredStocks = useMemo(() => {
    let list = report?.stocks || [];

    // Search filter
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(
        (s) =>
          s.symbol.toLowerCase().includes(q) ||
          s.nameAr.toLowerCase().includes(q) ||
          s.nameEn.toLowerCase().includes(q) ||
          (s.sectorAr && s.sectorAr.toLowerCase().includes(q))
      );
    }

    // Status filter
    if (statusFilter !== "all") {
      list = list.filter((s) => s.status === statusFilter);
    }

    // Sector filter
    if (sectorFilter !== "all") {
      list = list.filter((s) => s.sectorAr === sectorFilter);
    }

    // Sharia only
    if (shariaOnly) {
      list = list.filter((s) => s.isSharia);
    }

    // Quick presets
    if (quickPreset === "deep_discount") {
      list = list.filter((s) => s.upsidePct >= 25);
    } else if (quickPreset === "graham_only") {
      list = list.filter((s) => s.modelType === "graham_fundamental");
    } else if (quickPreset === "low_rsi_undervalued") {
      list = list.filter((s) => s.upsidePct >= 15 && s.rsi14 !== null && s.rsi14 < 45);
    }

    // Sorting
    list = [...list].sort((a, b) => {
      if (sortBy === "upside_desc") return b.upsidePct - a.upsidePct;
      if (sortBy === "upside_asc") return a.upsidePct - b.upsidePct;
      if (sortBy === "pe_asc") {
        if (!a.peRatio) return 1;
        if (!b.peRatio) return -1;
        return a.peRatio - b.peRatio;
      }
      if (sortBy === "pb_asc") {
        if (!a.pbRatio) return 1;
        if (!b.pbRatio) return -1;
        return a.pbRatio - b.pbRatio;
      }
      if (sortBy === "yield_desc") {
        return (b.dividendYield || 0) - (a.dividendYield || 0);
      }
      return 0;
    });

    return list;
  }, [
    report,
    search,
    statusFilter,
    sectorFilter,
    shariaOnly,
    quickPreset,
    sortBy,
  ]);

  const displayedStocks = showAllRows
    ? filteredStocks
    : filteredStocks.slice(0, 60);

  return (
    <div
      className="min-h-screen bg-zinc-50 dark:bg-[#07090e] text-zinc-900 dark:text-zinc-100 pb-20 transition-colors duration-200"
      dir={isAr ? "rtl" : "ltr"}
    >
      {/* Hero Banner */}
      <section className="relative overflow-hidden border-b-2 border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 pt-8 pb-8 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto space-y-6">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
            <div className="space-y-3 max-w-3xl">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 dark:bg-emerald-500/20 border border-emerald-500/30 text-emerald-700 dark:text-emerald-400 text-xs font-black">
                <Scale className="w-3.5 h-3.5" />
                <span>
                  {isAr
                    ? "محرك التقييم المالي والكمي (3-Tier Engine) — تحديث يومي بعد إغلاق الجلسة"
                    : "3-Tier Valuation Engine (Graham & Multiples) — Updated Daily Post-Close"}
                </span>
              </div>
              <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-zinc-950 dark:text-white">
                {isAr ? "محدد السعر العادل ومؤشر الرخص" : "Fair Value Screener & Margin of Safety"}{" "}
                <span className="text-emerald-600 dark:text-emerald-400 font-mono text-xl sm:text-3xl">
                  (Fair Value Screener)
                </span>
              </h1>
              <p className="text-sm sm:text-base text-zinc-600 dark:text-zinc-300 leading-relaxed">
                {isAr ? (
                  <>
                    تقييم شامل لجميع أسهم البورصة المصرية النشطة يدمج{" "}
                    <strong className="text-zinc-950 dark:text-white">معادلة بنجامين جراهام</strong>{" "}
                    مع{" "}
                    <strong className="text-zinc-950 dark:text-white">
                      مضاعفات الربحية والقيمة الدفترية للقطاع
                    </strong>{" "}
                    والتوازن الكمي، مع كشف طريقة الحساب التفصيلية لكل سهم.
                  </>
                ) : (
                  <>
                    Comprehensive valuation of all active EGX stocks blending{" "}
                    <strong className="text-zinc-950 dark:text-white">Benjamin Graham Formula</strong>{" "}
                    with{" "}
                    <strong className="text-zinc-950 dark:text-white">Sector P/E & P/B Multiples</strong>{" "}
                    and Quantitative Equilibrium (VWAP20 & EMA200).
                  </>
                )}
              </p>
            </div>

            {report && (
              <div className="flex flex-col items-start md:items-end gap-2 shrink-0">
                <div className="px-4 py-2.5 rounded-xl bg-zinc-100 dark:bg-zinc-800/80 border border-zinc-200 dark:border-zinc-700 text-xs text-zinc-700 dark:text-zinc-300 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span>
                      {isAr ? "تاريخ إغلاق الجلسة:" : "Session Close Date:"}{" "}
                      <strong className="text-zinc-950 dark:text-white font-mono">
                        {report.latestSessionDate || "2026-11-01"}
                      </strong>
                    </span>
                  </div>
                  <div className="text-[11px] text-zinc-500 dark:text-zinc-400">
                    {isAr
                      ? `تغطية القوائم المالية المباشرة: ${report.summary.fundamentalCoverageCount} من ${report.summary.totalEvaluated} سهم نشط`
                      : `Fundamental coverage: ${report.summary.fundamentalCoverageCount} of ${report.summary.totalEvaluated} active stocks`}
                  </div>
                </div>

                <Link
                  href="/sharia"
                  className="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-600 dark:text-emerald-400 hover:underline"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>{isAr ? "انتقل إلى حاسبة التطهير الشرعي وزكاة الأسهم ↗" : "Go to Sharia & Dividend Cleanser ↗"}</span>
                </Link>
              </div>
            )}
          </div>

          {/* 🔍 Prominent Search Bar (محرك بحث بارز وسريع) */}
          <div className="relative pt-2">
            <div className="relative flex items-center">
              <Search className={`absolute ${isAr ? "right-4" : "left-4"} w-5 h-5 text-zinc-400 pointer-events-none`} />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={
                  isAr
                    ? "ابحث باسم الشركة أو الرمز... (مثال: طلعت مصطفى، TMGH، السويدي، SWDY، فوري، أبو قير)"
                    : "Search by company name or ticker... (e.g. TMGH, SWDY, FWRY, COMI, ABUK)"
                }
                className={`w-full h-13 ${isAr ? "pr-12 pl-12" : "pl-12 pr-12"} rounded-2xl bg-white dark:bg-zinc-800 border-2 border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white placeholder:text-zinc-400 font-bold text-sm sm:text-base focus:outline-none focus:border-emerald-500 dark:focus:border-emerald-400 shadow-sm transition-all`}
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch("")}
                  className={`absolute ${isAr ? "left-4" : "right-4"} p-1.5 rounded-full hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-400 hover:text-zinc-700 dark:hover:text-white transition-colors cursor-pointer`}
                  title={isAr ? "مسح البحث" : "Clear search"}
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Quick Chips */}
            <div className="flex items-center gap-2 mt-2.5 overflow-x-auto pb-1 text-xs">
              <span className="text-zinc-500 dark:text-zinc-400 font-bold shrink-0">
                {isAr ? "⚡ بحث سريع:" : "⚡ Popular:"}
              </span>
              {POPULAR_SEARCH_SYMBOLS.map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => setSearch(sym)}
                  className={`px-2.5 py-1 rounded-lg border font-mono font-bold transition-colors cursor-pointer ${
                    search.toUpperCase() === sym
                      ? "bg-emerald-500 text-white border-emerald-600"
                      : "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700 hover:border-emerald-500"
                  }`}
                >
                  {sym}
                </button>
              ))}
              {search && (
                <span className="text-emerald-600 dark:text-emerald-400 font-bold shrink-0 ms-2">
                  {isAr ? `(عثرنا على ${filteredStocks.length} سهم مطابقة)` : `(${filteredStocks.length} matches)`}
                </span>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Main Content Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 space-y-8">
        {/* KPI Stats Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          <div className="p-4 sm:p-5 rounded-2xl bg-white dark:bg-zinc-900 border-2 border-zinc-200 dark:border-zinc-800 shadow-sm space-y-1">
            <div className="flex items-center justify-between text-xs font-bold text-zinc-500 dark:text-zinc-400">
              <span>{isAr ? "إجمالي الأسهم المقيمة" : "Total Stocks Evaluated"}</span>
              <Layers className="w-4 h-4 text-zinc-400" />
            </div>
            <div className="text-2xl sm:text-3xl font-black font-mono text-zinc-900 dark:text-white">
              {report?.summary?.totalEvaluated || 254}
            </div>
            <div className="text-[11px] text-zinc-500 dark:text-zinc-400 font-medium">
              {isAr ? "مكيشة يومياً بعد التشغيل الثاني" : "Cached daily after 2nd run"}
            </div>
          </div>

          <div
            onClick={() => {
              setStatusFilter("undervalued");
              setQuickPreset("all");
            }}
            className="p-4 sm:p-5 rounded-2xl bg-emerald-50 dark:bg-emerald-950/20 border-2 border-emerald-300 dark:border-emerald-800/60 shadow-sm space-y-1 cursor-pointer hover:border-emerald-500 transition-colors"
          >
            <div className="flex items-center justify-between text-xs font-bold text-emerald-700 dark:text-emerald-400">
              <span>{isAr ? "أقل من السعر العادل (فرص رخص)" : "Undervalued (Bargains)"}</span>
              <TrendingUp className="w-4 h-4" />
            </div>
            <div className="text-2xl sm:text-3xl font-black font-mono text-emerald-600 dark:text-emerald-400">
              {report?.summary.undervaluedCount || 87}
            </div>
            <div className="text-[11px] text-emerald-700 dark:text-emerald-400 font-medium">
              {isAr ? "تتداول بخصم +15% أو أكثر عن قيمتها" : "Trading at >15% discount to fair value"}
            </div>
          </div>

          <div
            onClick={() => {
              setStatusFilter("fair");
              setQuickPreset("all");
            }}
            className="p-4 sm:p-5 rounded-2xl bg-amber-50 dark:bg-amber-950/20 border-2 border-amber-300 dark:border-amber-800/60 shadow-sm space-y-1 cursor-pointer hover:border-amber-500 transition-colors"
          >
            <div className="flex items-center justify-between text-xs font-bold text-amber-700 dark:text-amber-400">
              <span>{isAr ? "في النطاق العادل" : "In Fair Range"}</span>
              <CheckCircle2 className="w-4 h-4" />
            </div>
            <div className="text-2xl sm:text-3xl font-black font-mono text-amber-600 dark:text-amber-400">
              {report?.summary.fairCount || 51}
            </div>
            <div className="text-[11px] text-amber-700 dark:text-amber-400 font-medium">
              {isAr ? "قريبة من قيمتها العادلة (-12% إلى +15%)" : "Close to fair value (-12% to +15%)"}
            </div>
          </div>

          <div
            onClick={() => {
              setStatusFilter("overvalued");
              setQuickPreset("all");
            }}
            className="p-4 sm:p-5 rounded-2xl bg-rose-50 dark:bg-rose-950/20 border-2 border-rose-300 dark:border-rose-800/60 shadow-sm space-y-1 cursor-pointer hover:border-rose-500 transition-colors"
          >
            <div className="flex items-center justify-between text-xs font-bold text-rose-700 dark:text-rose-400">
              <span>{isAr ? "أعلى من السعر العادل (متضخم)" : "Overvalued (Premium)"}</span>
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div className="text-2xl sm:text-3xl font-black font-mono text-rose-600 dark:text-rose-400">
              {report?.summary.overvaluedCount || 116}
            </div>
            <div className="text-[11px] text-rose-700 dark:text-rose-400 font-medium">
              {isAr ? "تتداول بعلاوة سعرية تتجاوز قيمتها العادلة" : "Trading at significant premium"}
            </div>
          </div>
        </div>

        {/* 📊 Interactive Valuation Chart (الشارت التفاعلي للخريطة السعرية) */}
        <section className="bg-white dark:bg-zinc-900 border-2 border-zinc-200 dark:border-zinc-800 rounded-3xl p-5 sm:p-7 shadow-sm space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b-2 border-zinc-100 dark:border-zinc-800 pb-5">
            <div>
              <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-400 text-xs font-bold mb-1.5">
                <BarChart3 className="w-3.5 h-3.5" />
                <span>{isAr ? "تحليل مرئي تفاعلي" : "Interactive Visualizer"}</span>
              </div>
              <h2 className="text-lg sm:text-2xl font-black text-zinc-950 dark:text-white">
                {isAr
                  ? "الشارت التفاعلي لخريطة السعر العادل في البورصة المصرية"
                  : "Interactive EGX Fair Value Map & Valuation Inspector"}
              </h2>
              <p className="text-xs sm:text-sm text-zinc-500 dark:text-zinc-400 mt-1">
                {isAr
                  ? "اضغط على أي سهم أو شريحة تقييم في الشارت لعرض معادلاته الحسابية أو فلترة القائمة مباشرة"
                  : "Click any stock or spectrum zone in the chart to inspect its mathematical formula and filter"}
              </p>
            </div>

            {/* Chart Mode Tabs */}
            <div className="inline-flex p-1 rounded-xl bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 shrink-0">
              <button
                type="button"
                onClick={() => setChartTab("bars")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  chartTab === "bars"
                    ? "bg-white dark:bg-zinc-900 text-emerald-600 dark:text-emerald-400 shadow-sm border border-zinc-200 dark:border-zinc-700"
                    : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white"
                }`}
              >
                {isAr ? "⚖️ مقارنة الأسهم (تحت العادل vs فوق العادل)" : "⚖️ Undervalued vs Overvalued"}
              </button>
              <button
                type="button"
                onClick={() => setChartTab("zones")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  chartTab === "zones"
                    ? "bg-white dark:bg-zinc-900 text-emerald-600 dark:text-emerald-400 shadow-sm border border-zinc-200 dark:border-zinc-700"
                    : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white"
                }`}
              >
                {isAr ? "📊 توزيع شرائح السوق (254 سهم)" : "📊 Market Spectrum (254 Stocks)"}
              </button>
            </div>
          </div>

          {chartTab === "bars" ? (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              {/* Selected Stock Live Inspector Box */}
              <div className="lg:col-span-5 bg-zinc-50 dark:bg-zinc-800/60 border-2 border-zinc-200 dark:border-zinc-700 rounded-2xl p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-700 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded-md bg-zinc-200 dark:bg-zinc-700 font-mono text-xs font-black text-zinc-900 dark:text-white">
                      {selectedChartStock?.symbol || "COMI"}
                    </span>
                    <span className="text-xs text-zinc-500 dark:text-zinc-400">
                      {isAr ? selectedChartStock?.sectorAr : selectedChartStock?.sectorAr}
                    </span>
                  </div>
                  <Link
                    prefetch={false}
                    href={`/stocks/${(selectedChartStock?.symbol || "COMI").toLowerCase()}`}
                    className="inline-flex items-center gap-1 text-xs font-bold text-emerald-600 dark:text-emerald-400 hover:underline"
                  >
                    <span>{isAr ? "صفحة السهم" : "View Stock"}</span>
                    <ArrowUpRight className="w-3.5 h-3.5" />
                  </Link>
                </div>

                <div>
                  <div className="text-lg font-black text-zinc-950 dark:text-white">
                    {isAr ? selectedChartStock?.nameAr : selectedChartStock?.nameEn || selectedChartStock?.nameAr}
                  </div>
                  <div className="text-xs text-zinc-500 dark:text-zinc-400 font-mono">
                    {selectedChartStock?.nameEn}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-1">
                  <div className="p-3 rounded-xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700">
                    <div className="text-[11px] text-zinc-500 dark:text-zinc-400 font-medium">
                      {isAr ? "سعر الإغلاق الحالي" : "Current Price"}
                    </div>
                    <div className="text-xl font-black font-mono text-zinc-950 dark:text-white mt-0.5">
                      {selectedChartStock?.currentPrice.toFixed(2)} {isAr ? "ج.م" : "EGP"}
                    </div>
                  </div>

                  <div className="p-3 rounded-xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700">
                    <div className="text-[11px] text-zinc-500 dark:text-zinc-400 font-medium">
                      {isAr ? "السعر العادل المحسوب" : "Calculated Fair Value"}
                    </div>
                    <div className="text-xl font-black font-mono text-emerald-600 dark:text-emerald-400 mt-0.5">
                      {selectedChartStock?.fairValue.toFixed(2)} {isAr ? "ج.م" : "EGP"}
                    </div>
                  </div>
                </div>

                {/* Upside Badge */}
                <div
                  className={`p-3 rounded-xl border flex items-center justify-between text-xs font-bold ${
                    (selectedChartStock?.upsidePct || 0) >= 0
                      ? "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-300 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300"
                      : "bg-rose-50 dark:bg-rose-950/30 border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-300"
                  }`}
                >
                  <span>{isAr ? "نسبة التقييم للسعر العادل:" : "Valuation to Fair Value:"}</span>
                  <span className="font-mono text-sm font-black">
                    {(selectedChartStock?.upsidePct || 0) >= 0 ? "+" : ""}
                    {selectedChartStock?.upsidePct.toFixed(2)}%
                  </span>
                </div>

                {/* Calculation Details */}
                <div className="space-y-2 pt-2 border-t border-zinc-200 dark:border-zinc-700 text-xs">
                  <div className="flex items-center gap-1.5 text-zinc-700 dark:text-zinc-300 font-bold">
                    <Calculator className="w-3.5 h-3.5 text-emerald-500" />
                    <span>
                      {isAr ? "طريقة الحسبة" : "Calculation Method"}:{" "}
                      <span className="text-emerald-600 dark:text-emerald-400">
                        ({selectedChartStock?.modelLabelAr})
                      </span>
                    </span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700/60 font-mono text-[11px] text-zinc-600 dark:text-zinc-300 break-words leading-relaxed">
                    {selectedChartStock?.formulaSubstitutionAr ||
                      selectedChartStock?.formulaEquationAr ||
                      "حساب مرجح للبيانات المالية"}
                  </div>

                  {selectedChartStock?.formulaStepsAr?.map((step, idx) => (
                    <div
                      key={idx}
                      className="text-[11px] text-zinc-600 dark:text-zinc-400 leading-relaxed ps-2 border-s-2 border-emerald-500/40"
                    >
                      {step}
                    </div>
                  ))}
                </div>
              </div>

              {/* Side by Side Bar Charts */}
              <div className="lg:col-span-7 grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Undervalued column */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs font-bold text-emerald-600 dark:text-emerald-400 border-b border-zinc-200 dark:border-zinc-800 pb-2">
                    <span className="flex items-center gap-1">
                      <TrendingUp className="w-3.5 h-3.5" />
                      <span>{isAr ? "أكبر الأسهم خصماً (تحت السعر العادل)" : "Top Undervalued (Discount)"}</span>
                    </span>
                    <span className="text-[11px] text-zinc-400">
                      {isAr ? "السعر الحالي / العادل" : "Current / Target"}
                    </span>
                  </div>

                  <div className="space-y-2">
                    {topUndervaluedStocks.map((s) => {
                      const isSelected = selectedChartStock?.symbol === s.symbol;
                      const barWidth = Math.min(100, Math.max(15, s.upsidePct));
                      return (
                        <div
                          key={s.symbol}
                          onClick={() => setSelectedChartStock(s)}
                          className={`p-2.5 rounded-xl border transition-all cursor-pointer ${
                            isSelected
                              ? "bg-emerald-50 dark:bg-emerald-950/40 border-emerald-500 shadow-sm"
                              : "bg-zinc-50 dark:bg-zinc-800/40 border-zinc-200 dark:border-zinc-800 hover:border-emerald-400 dark:hover:border-emerald-600"
                          }`}
                        >
                          <div className="flex items-center justify-between text-xs mb-1.5">
                            <div className="flex items-center gap-1.5">
                              <span className="font-mono font-bold text-zinc-950 dark:text-white">
                                {s.symbol}
                              </span>
                              <span className="text-zinc-500 dark:text-zinc-400 text-[11px] truncate max-w-[120px]">
                                {isAr ? s.nameAr : s.nameEn || s.nameAr}
                              </span>
                            </div>
                            <span className="font-mono font-black text-emerald-600 dark:text-emerald-400 text-xs">
                              +{s.upsidePct.toFixed(1)}%
                            </span>
                          </div>

                          {/* Bar */}
                          <div className="w-full bg-zinc-200 dark:bg-zinc-700/60 h-2 rounded-full overflow-hidden">
                            <div
                              className="bg-emerald-500 h-full rounded-full transition-all duration-500"
                              style={{ width: `${barWidth}%` }}
                            />
                          </div>

                          <div className="flex items-center justify-between text-[10px] text-zinc-500 dark:text-zinc-400 mt-1.5 font-mono">
                            <span>{isAr ? "الحالي:" : "Cur:"} {s.currentPrice.toFixed(2)} ج.م</span>
                            <span className="text-emerald-600 dark:text-emerald-400 font-bold">
                              {isAr ? "العادل:" : "Fair:"} {s.fairValue.toFixed(2)} ج.م
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Overvalued column */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs font-bold text-rose-600 dark:text-rose-400 border-b border-zinc-200 dark:border-zinc-800 pb-2">
                    <span className="flex items-center gap-1">
                      <TrendingDown className="w-3.5 h-3.5" />
                      <span>{isAr ? "أكثر الأسهم علاوة (فوق السعر العادل)" : "Top Overvalued (Premium)"}</span>
                    </span>
                    <span className="text-[11px] text-zinc-400">
                      {isAr ? "السعر الحالي / العادل" : "Current / Target"}
                    </span>
                  </div>

                  <div className="space-y-2">
                    {topOvervaluedStocks.map((s) => {
                      const isSelected = selectedChartStock?.symbol === s.symbol;
                      const barWidth = Math.min(100, Math.max(15, Math.abs(s.upsidePct)));
                      return (
                        <div
                          key={s.symbol}
                          onClick={() => setSelectedChartStock(s)}
                          className={`p-2.5 rounded-xl border transition-all cursor-pointer ${
                            isSelected
                              ? "bg-rose-50 dark:bg-rose-950/40 border-rose-500 shadow-sm"
                              : "bg-zinc-50 dark:bg-zinc-800/40 border-zinc-200 dark:border-zinc-800 hover:border-rose-400 dark:hover:border-rose-600"
                          }`}
                        >
                          <div className="flex items-center justify-between text-xs mb-1.5">
                            <div className="flex items-center gap-1.5">
                              <span className="font-mono font-bold text-zinc-950 dark:text-white">
                                {s.symbol}
                              </span>
                              <span className="text-zinc-500 dark:text-zinc-400 text-[11px] truncate max-w-[120px]">
                                {isAr ? s.nameAr : s.nameEn || s.nameAr}
                              </span>
                            </div>
                            <span className="font-mono font-black text-rose-600 dark:text-rose-400 text-xs">
                              {s.upsidePct.toFixed(1)}%
                            </span>
                          </div>

                          {/* Bar */}
                          <div className="w-full bg-zinc-200 dark:bg-zinc-700/60 h-2 rounded-full overflow-hidden">
                            <div
                              className="bg-rose-500 h-full rounded-full transition-all duration-500"
                              style={{ width: `${barWidth}%` }}
                            />
                          </div>

                          <div className="flex items-center justify-between text-[10px] text-zinc-500 dark:text-zinc-400 mt-1.5 font-mono">
                            <span>{isAr ? "الحالي:" : "Cur:"} {s.currentPrice.toFixed(2)} ج.م</span>
                            <span className="text-rose-600 dark:text-rose-400 font-bold">
                              {isAr ? "العادل:" : "Fair:"} {s.fairValue.toFixed(2)} ج.م
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* Valuation Spectrum Zones View */
            <div className="space-y-6">
              {/* Stacked Spectrum Bar */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-bold text-zinc-500 dark:text-zinc-400">
                  <span>{isAr ? "طيف توزيع أسهم البورصة المصرية الكامل (254 سهماً):" : "Full EGX Valuation Distribution Spectrum (254 Stocks):"}</span>
                  <span>{isAr ? "اضغط على أي شريحة لتطبيق الفلتر فوراً" : "Click any segment to filter list"}</span>
                </div>
                <div className="h-6 rounded-xl overflow-hidden flex bg-zinc-200 dark:bg-zinc-800 p-0.5 border border-zinc-300 dark:border-zinc-700 gap-0.5">
                  {valuationZones.map((z) => (
                    <div
                      key={z.id}
                      onClick={z.onClick}
                      title={`${z.label}: ${z.count} (${z.pct}%)`}
                      className={`${z.color} h-full transition-all hover:opacity-80 cursor-pointer first:rounded-s-lg last:rounded-e-lg relative group`}
                      style={{ width: `${z.pct}%` }}
                    />
                  ))}
                </div>
              </div>

              {/* Cards Grid for 5 Zones */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                {valuationZones.map((z) => (
                  <div
                    key={z.id}
                    onClick={z.onClick}
                    className="p-4 rounded-2xl bg-zinc-50 dark:bg-zinc-800/50 border-2 border-zinc-200 dark:border-zinc-700/70 hover:border-emerald-500 transition-all cursor-pointer space-y-1.5"
                  >
                    <div className="flex items-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded-full ${z.color}`} />
                      <span className="text-xs font-bold text-zinc-900 dark:text-white truncate">
                        {z.shortLabel}
                      </span>
                    </div>
                    <div className={`text-2xl font-black font-mono ${z.textColor}`}>
                      {z.count}
                    </div>
                    <div className="text-[11px] text-zinc-500 dark:text-zinc-400">
                      {isAr ? `يمثل ${z.pct}% من البورصة` : `${z.pct}% of market`}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* 🎛️ Filters & Control Bar */}
        <section className="bg-white dark:bg-zinc-900 border-2 border-zinc-200 dark:border-zinc-800 rounded-3xl p-5 shadow-sm space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            {/* Quick Filter Pills */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-bold text-zinc-500 dark:text-zinc-400 me-1">
                <Filter className="w-3.5 h-3.5 inline me-1" />
                {isAr ? "فلاتر سريعة:" : "Quick Filters:"}
              </span>

              <button
                type="button"
                onClick={() => {
                  setQuickPreset("all");
                  setStatusFilter("all");
                }}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-colors cursor-pointer ${
                  quickPreset === "all" && statusFilter === "all"
                    ? "bg-zinc-950 dark:bg-white text-white dark:text-zinc-950 border-zinc-950 dark:border-white shadow-sm"
                    : "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700 hover:border-zinc-400"
                }`}
              >
                {isAr ? "الكل (254 سهم)" : "All (254 Stocks)"}
              </button>

              <button
                type="button"
                onClick={() => {
                  setQuickPreset("deep_discount");
                  setStatusFilter("undervalued");
                }}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-colors cursor-pointer flex items-center gap-1 ${
                  quickPreset === "deep_discount"
                    ? "bg-emerald-600 text-white border-emerald-700 shadow-sm"
                    : "bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800 hover:border-emerald-400"
                }`}
              >
                <Flame className="w-3.5 h-3.5" />
                <span>{isAr ? "خصم عميق (>25%)" : "Deep Discount (>25%)"}</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setQuickPreset("graham_only");
                  setStatusFilter("all");
                }}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-colors cursor-pointer flex items-center gap-1 ${
                  quickPreset === "graham_only"
                    ? "bg-indigo-600 text-white border-indigo-700 shadow-sm"
                    : "bg-indigo-50 dark:bg-indigo-950/30 text-indigo-700 dark:text-indigo-400 border-indigo-200 dark:border-indigo-800 hover:border-indigo-400"
                }`}
              >
                <BookOpen className="w-3.5 h-3.5" />
                <span>{isAr ? "معادلة جراهام فقط" : "Graham Model Only"}</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setQuickPreset("low_rsi_undervalued");
                  setStatusFilter("undervalued");
                }}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-colors cursor-pointer flex items-center gap-1 ${
                  quickPreset === "low_rsi_undervalued"
                    ? "bg-teal-600 text-white border-teal-700 shadow-sm"
                    : "bg-teal-50 dark:bg-teal-950/30 text-teal-700 dark:text-teal-400 border-teal-200 dark:border-teal-800 hover:border-teal-400"
                }`}
              >
                <TrendingUp className="w-3.5 h-3.5" />
                <span>{isAr ? "رخيص + تشبع بيعي (RSI<45)" : "Oversold & Cheap (RSI<45)"}</span>
              </button>

              <button
                type="button"
                onClick={() => setShariaOnly((prev) => !prev)}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-colors cursor-pointer flex items-center gap-1 ${
                  shariaOnly
                    ? "bg-emerald-600 text-white border-emerald-700 shadow-sm"
                    : "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700 hover:border-emerald-400"
                }`}
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>{isAr ? "أسهم الشريعة (EGX33)" : "EGX33 Sharia Only"}</span>
              </button>
            </div>

            {/* Dropdowns (Sector & Sorting) */}
            <div className="flex items-center gap-3 w-full sm:w-auto">
              {/* Sector */}
              <select
                value={sectorFilter}
                onChange={(e) => setSectorFilter(e.target.value)}
                className="h-10 px-3 rounded-xl bg-zinc-100 dark:bg-zinc-800 border-2 border-zinc-300 dark:border-zinc-700 text-xs font-bold text-zinc-900 dark:text-white focus:outline-none focus:border-emerald-500"
              >
                <option value="all">{isAr ? "جميع القطاعات" : "All Sectors"}</option>
                {sectors.map((sec) => (
                  <option key={sec} value={sec}>
                    {sec}
                  </option>
                ))}
              </select>

              {/* Sorting */}
              <select
                value={sortBy}
                onChange={(e: any) => setSortBy(e.target.value)}
                className="h-10 px-3 rounded-xl bg-zinc-100 dark:bg-zinc-800 border-2 border-zinc-300 dark:border-zinc-700 text-xs font-bold text-zinc-900 dark:text-white focus:outline-none focus:border-emerald-500"
              >
                <option value="upside_desc">{isAr ? "الأعلى خصماً (أرخص الأسهم)" : "Highest Upside (Cheapest)"}</option>
                <option value="upside_asc">{isAr ? "الأكثر تضخماً (أعلى علاوة)" : "Most Overvalued"}</option>
                <option value="pe_asc">{isAr ? "أقل مكرر ربحية P/E" : "Lowest P/E"}</option>
                <option value="pb_asc">{isAr ? "أقل مضاعف دفتري P/B" : "Lowest P/B"}</option>
                <option value="yield_desc">{isAr ? "أعلى عائد توزيع كوبون" : "Highest Dividend Yield"}</option>
              </select>
            </div>
          </div>
        </section>

        {/* 📋 Stock Cards Grid */}
        <section className="space-y-4">
          <div className="flex items-center justify-between text-xs font-bold text-zinc-500 dark:text-zinc-400">
            <span>
              {isAr
                ? `عرض ${displayedStocks.length} من إجمالي ${filteredStocks.length} سهم مطابق للفلاتر`
                : `Showing ${displayedStocks.length} of ${filteredStocks.length} matched stocks`}
            </span>
            {filteredStocks.length > 60 && !showAllRows && (
              <button
                type="button"
                onClick={() => setShowAllRows(true)}
                className="text-emerald-600 dark:text-emerald-400 font-bold hover:underline cursor-pointer"
              >
                {isAr ? "عرض باقي الأسهم كاملة (+200 سهم) ↓" : "Show all stocks (+200 stocks) ↓"}
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {displayedStocks.map((stock) => (
              <StockValuationCard key={stock.symbol} stock={stock} isAr={isAr} />
            ))}
          </div>

          {filteredStocks.length === 0 && (
            <div className="py-16 text-center rounded-3xl border-2 border-dashed border-zinc-300 dark:border-zinc-700 p-8 space-y-3">
              <Scale className="w-10 h-10 text-zinc-400 mx-auto" />
              <div className="text-base font-bold text-zinc-700 dark:text-zinc-300">
                {isAr ? "لا توجد أسهم مطابقة لشروط البحث والفلاتر المحددة" : "No stocks matched the search criteria"}
              </div>
              <button
                type="button"
                onClick={() => {
                  setSearch("");
                  setStatusFilter("all");
                  setSectorFilter("all");
                  setQuickPreset("all");
                  setShariaOnly(false);
                }}
                className="px-4 py-2 rounded-xl bg-emerald-500 text-white font-bold text-xs hover:bg-emerald-600 transition-colors cursor-pointer"
              >
                {isAr ? "إعادة ضبط جميع الفلاتر" : "Reset all filters"}
              </button>
            </div>
          )}
        </section>

        {/* 📖 Comprehensive Methodology Guide Section (دليل المنهجية) */}
        <section className="bg-white dark:bg-zinc-900 border-2 border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 sm:p-8 shadow-sm space-y-6">
          <div className="border-b-2 border-zinc-100 dark:border-zinc-800 pb-4">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-600 dark:text-indigo-400 text-xs font-bold mb-1.5">
              <BookOpen className="w-3.5 h-3.5" />
              <span>{isAr ? "شفافية الحساب والمنهجية العلمية" : "Scientific Valuation Methodology"}</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-black text-zinc-950 dark:text-white">
              {isAr
                ? "دليل محرك التقييم المالي والكمي الثلاثي (3-Tier Engine)"
                : "The 3-Tier Fair Value Methodology Explained"}
            </h2>
            <p className="text-xs sm:text-sm text-zinc-500 dark:text-zinc-400 mt-1">
              {isAr
                ? "كيف يتم استخراج السعر العادل لكل سهم من بيانات القوائم المالية والتداول اليومية؟"
                : "How is the fair value calculated for each Egyptian stock from financial statements?"}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-5 rounded-2xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/80 space-y-3">
              <div className="inline-flex p-2.5 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-bold text-sm">
                1️⃣ {isAr ? "المستوى الأول: نموذج جراهام" : "Tier 1: Graham Model"}
              </div>
              <h3 className="text-base font-black text-zinc-900 dark:text-white">
                {isAr ? "معادلة القيمة الجوهرية لبنجامين جراهام" : "Benjamin Graham Intrinsic Value"}
              </h3>
              <p className="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed font-mono">
                Fair Value = √(22.5 × EPS × BVPS)
              </p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">
                {isAr
                  ? "يطبق على الشركات ذات الأرباح التشغيلية وحقوق الملكية الموجبة، مدمجاً بوزن 50% مع مكررات القطاع لضمان صمام أمان سعري للمستثمر."
                  : "Applied to profitable companies with positive book value, blended 50% with sector median P/E & P/B."}
              </p>
            </div>

            <div className="p-5 rounded-2xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/80 space-y-3">
              <div className="inline-flex p-2.5 rounded-xl bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 font-bold text-sm">
                2️⃣ {isAr ? "المستوى الثاني: مضاعفات القطاع" : "Tier 2: Sector Multiples"}
              </div>
              <h3 className="text-base font-black text-zinc-900 dark:text-white">
                {isAr ? "مكررات الربحية والقيمة الدفترية" : "P/E & P/B Sector Medians"}
              </h3>
              <p className="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed font-mono">
                Fair Value = EPS × Median_Sector_PE
              </p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">
                {isAr
                  ? "للشركات في مرحلة نمو أو إعادة هيكلة، نقارن ربحية السهم أو قيمته الدفترية بوسيط القطاع الفعلي في البورصة المصرية (بنوك، عقارات، كيماويات)."
                  : "Benchmark against actual EGX sector medians for companies with single positive metrics."}
              </p>
            </div>

            <div className="p-5 rounded-2xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/80 space-y-3">
              <div className="inline-flex p-2.5 rounded-xl bg-teal-500/10 text-teal-600 dark:text-teal-400 font-bold text-sm">
                3️⃣ {isAr ? "المستوى الثالث: التوازن الكمي" : "Tier 3: Quant Equilibrium"}
              </div>
              <h3 className="text-base font-black text-zinc-900 dark:text-white">
                {isAr ? "توازن التكلفة والسيولة (VWAP + EMA)" : "Volume-Weighted Cost Balance"}
              </h3>
              <p className="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed font-mono">
                Fair Value = 0.6 × EMA200 + 0.4 × VWAP20
              </p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">
                {isAr
                  ? "للشركات حديثة القيد أو التي لم تنشر قوائمها المالية بعد، يعتمد المحرك على متوسط التكلفة المرجح بالسيولة لآخر 20 جلسة والمتوسط طويل الأجل."
                  : "For newly listed stocks without published fundamentals, blending VWAP20 and long-term EMA200."}
              </p>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

function StockValuationCard({
  stock,
  isAr,
}: {
  stock: FairValueStockItem;
  isAr: boolean;
}) {
  const [openFormula, setOpenFormula] = useState(false);

  const isPositive = stock.upsidePct >= 0;
  const isDeep = stock.upsidePct >= 25;
  const isOver = stock.upsidePct <= -12;

  return (
    <div className="rounded-2xl bg-white dark:bg-zinc-900 border-2 border-zinc-200 dark:border-zinc-800 p-5 space-y-4 hover:border-zinc-400 dark:hover:border-zinc-600 transition-all shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono font-black text-sm text-zinc-950 dark:text-white">
              {stock.symbol}
            </span>
            {stock.isSharia && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 text-[10px] font-bold">
                <ShieldCheck className="w-3 h-3" />
                <span>EGX33</span>
              </span>
            )}
            <span className="text-[11px] text-zinc-500 dark:text-zinc-400">
              {stock.sectorAr}
            </span>
          </div>
          <div className="text-sm font-bold text-zinc-900 dark:text-zinc-100 mt-1">
            {isAr ? stock.nameAr : stock.nameEn || stock.nameAr}
          </div>
        </div>

        {/* Status Badge */}
        <div
          className={`px-2.5 py-1 rounded-xl text-xs font-black shrink-0 ${
            isDeep
              ? "bg-emerald-500 text-white"
              : isPositive
              ? "bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800"
              : isOver
              ? "bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800"
              : "bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800"
          }`}
        >
          {isPositive ? `+${stock.upsidePct.toFixed(1)}%` : `${stock.upsidePct.toFixed(1)}%`}
        </div>
      </div>

      {/* Prices Grid */}
      <div className="grid grid-cols-2 gap-3 p-3 rounded-xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/60">
        <div>
          <div className="text-[11px] text-zinc-500 dark:text-zinc-400 font-medium">
            {isAr ? "السعر الحالي" : "Current Price"}
          </div>
          <div className="text-lg font-black font-mono text-zinc-900 dark:text-white mt-0.5">
            {stock.currentPrice.toFixed(2)} {isAr ? "ج.م" : "EGP"}
          </div>
        </div>

        <div>
          <div className="text-[11px] text-zinc-500 dark:text-zinc-400 font-medium">
            {isAr ? "السعر العادل" : "Fair Value Target"}
          </div>
          <div className="text-lg font-black font-mono text-emerald-600 dark:text-emerald-400 mt-0.5">
            {stock.fairValue.toFixed(2)} {isAr ? "ج.م" : "EGP"}
          </div>
        </div>
      </div>

      {/* Visual Meter Bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[11px] text-zinc-500 dark:text-zinc-400 font-mono">
          <span>{isAr ? "تقييم السعر:" : "Valuation Meter:"}</span>
          <span className="font-bold">
            {stock.status === "undervalued"
              ? isAr ? "أقل من العادل (رخيص) 🟢" : "Undervalued 🟢"
              : stock.status === "overvalued"
              ? isAr ? "متضخم سعرياً 🔴" : "Overvalued 🔴"
              : isAr ? "نطاق عادل ⚖️" : "Fair Range ⚖️"}
          </span>
        </div>
        <div className="w-full bg-zinc-200 dark:bg-zinc-700 h-2 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              isPositive ? "bg-emerald-500" : "bg-rose-500"
            }`}
            style={{ width: `${Math.min(100, Math.max(10, Math.abs(stock.upsidePct)))}%` }}
          />
        </div>
      </div>

      {/* Collapsible Formula Calculation */}
      <div className="pt-2 border-t border-zinc-200 dark:border-zinc-800">
        <button
          type="button"
          onClick={() => setOpenFormula((prev) => !prev)}
          className="w-full flex items-center justify-between text-xs font-bold text-zinc-600 dark:text-zinc-400 hover:text-zinc-950 dark:hover:text-white cursor-pointer py-1"
        >
          <span className="flex items-center gap-1.5">
            <Calculator className="w-3.5 h-3.5 text-emerald-500" />
            <span>{isAr ? "طريقة الحسبة بالأرقام" : "Step-by-Step Formula"}</span>
          </span>
          {openFormula ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>

        {openFormula && (
          <div className="mt-2.5 p-3 rounded-xl bg-zinc-100 dark:bg-zinc-800/80 border border-zinc-200 dark:border-zinc-700 text-xs space-y-2">
            <div className="text-[11px] font-bold text-emerald-600 dark:text-emerald-400">
              {stock.modelLabelAr}
            </div>
            <div className="font-mono text-[11px] text-zinc-700 dark:text-zinc-300 break-words bg-white dark:bg-zinc-900 p-2 rounded-lg border border-zinc-200 dark:border-zinc-700/60">
              {stock.formulaSubstitutionAr || stock.formulaEquationAr}
            </div>
            {stock.formulaStepsAr?.map((step, idx) => (
              <div key={idx} className="text-[10px] text-zinc-600 dark:text-zinc-400 leading-relaxed ps-1.5 border-s-2 border-emerald-500/50">
                {step}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Action link */}
      <Link
        prefetch={false}
        href={`/stocks/${stock.symbol.toLowerCase()}`}
        className="block text-center py-2 px-3 rounded-xl bg-zinc-100 dark:bg-zinc-800 hover:bg-emerald-500 hover:text-white dark:hover:bg-emerald-500 dark:hover:text-white text-xs font-bold text-zinc-700 dark:text-zinc-300 transition-colors"
      >
        {isAr ? "التحليل الفني والمالي الكامل للسهم ←" : "Full Technical & Financial Analysis →"}
      </Link>
    </div>
  );
}
