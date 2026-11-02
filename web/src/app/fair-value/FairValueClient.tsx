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
} from "lucide-react";
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

export default function FairValueClient({
  initialReport = null,
}: {
  initialReport?: FairValueReport | null;
}) {
  const [report, setReport] = useState<FairValueReport | null>(initialReport);
  const [loading, setLoading] = useState(!initialReport);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | FairValueStatus>(
    "all"
  );
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
        if (!res.ok) throw new Error("تعذر تحميل بيانات السعر العادل");
        const data: FairValueReport = await res.json();
        if (active) {
          setReport(data);
          if (data.stocks?.length) {
            setSelectedChartStock(data.stocks[0]);
          }
        }
      } catch (err: any) {
        if (active) setError(err?.message || "حدث خطأ غير متوقع");
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [initialReport]);

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
        label: "خصم سعري عميق (+30% فأكثر)",
        shortLabel: "خصم عميق >+30%",
        count: deepDiscount,
        pct: Math.round((deepDiscount / total) * 100),
        color: "bg-emerald-500",
        textColor: "text-emerald-400",
        borderColor: "border-emerald-500/40",
        onClick: () => {
          setStatusFilter("undervalued");
          setQuickPreset("deep_discount");
        },
      },
      {
        id: "under",
        label: "أقل من السعر العادل (+15% إلى +30%)",
        shortLabel: "أقل من العادل",
        count: undervalued,
        pct: Math.round((undervalued / total) * 100),
        color: "bg-teal-500",
        textColor: "text-teal-400",
        borderColor: "border-teal-500/40",
        onClick: () => {
          setStatusFilter("undervalued");
          setQuickPreset("all");
        },
      },
      {
        id: "fair",
        label: "في النطاق العادل (-12% إلى +15%)",
        shortLabel: "نطاق عادل",
        count: fair,
        pct: Math.round((fair / total) * 100),
        color: "bg-amber-500",
        textColor: "text-amber-400",
        borderColor: "border-amber-500/40",
        onClick: () => {
          setStatusFilter("fair");
          setQuickPreset("all");
        },
      },
      {
        id: "over",
        label: "أعلى من السعر العادل (-12% إلى -25%)",
        shortLabel: "فوق العادل",
        count: overvalued,
        pct: Math.round((overvalued / total) * 100),
        color: "bg-orange-500",
        textColor: "text-orange-400",
        borderColor: "border-orange-500/40",
        onClick: () => {
          setStatusFilter("overvalued");
          setQuickPreset("all");
        },
      },
      {
        id: "extreme",
        label: "متضخم سعرياً بشدة (أقل من -25%)",
        shortLabel: "تضخم شديد <-25%",
        count: extremeOvervalued,
        pct: Math.round((extremeOvervalued / total) * 100),
        color: "bg-rose-500",
        textColor: "text-rose-400",
        borderColor: "border-rose-500/40",
        onClick: () => {
          setStatusFilter("overvalued");
          setSortBy("upside_asc");
          setQuickPreset("all");
        },
      },
    ];
  }, [report]);

  const chartComparisonData = useMemo(() => {
    const stocks = report?.stocks || [];
    const topUndervalued = [...stocks]
      .filter((s) => s.upsidePct > 0)
      .sort((a, b) => b.upsidePct - a.upsidePct)
      .slice(0, 8);
    const topOvervalued = [...stocks]
      .filter((s) => s.upsidePct < 0)
      .sort((a, b) => a.upsidePct - b.upsidePct)
      .slice(0, 8);
    return { topUndervalued, topOvervalued };
  }, [report]);

  const filteredStocks = useMemo(() => {
    if (!report?.stocks) return [];
    const q = search.trim().toLowerCase();

    const list = report.stocks.filter((item) => {
      if (statusFilter !== "all" && item.status !== statusFilter) return false;
      if (sectorFilter !== "all" && item.sectorAr !== sectorFilter) return false;
      if (shariaOnly && !item.isSharia) return false;
      if (quickPreset === "deep_discount" && item.upsidePct < 25) return false;
      if (
        quickPreset === "graham_only" &&
        item.modelType !== "graham_fundamental"
      )
        return false;
      if (
        quickPreset === "low_rsi_undervalued" &&
        (item.upsidePct < 15 || (item.rsi14 !== null && item.rsi14 > 55))
      )
        return false;

      if (q) {
        const matchSym = item.symbol.toLowerCase().includes(q);
        const matchAr = item.nameAr.toLowerCase().includes(q);
        const matchEn = item.nameEn.toLowerCase().includes(q);
        const matchSec = item.sectorAr.toLowerCase().includes(q);
        if (!matchSym && !matchAr && !matchEn && !matchSec) return false;
      }
      return true;
    });

    list.sort((a, b) => {
      if (sortBy === "upside_desc") return b.upsidePct - a.upsidePct;
      if (sortBy === "upside_asc") return a.upsidePct - b.upsidePct;
      if (sortBy === "pe_asc") {
        const peA = a.peRatio && a.peRatio > 0 ? a.peRatio : 9999;
        const peB = b.peRatio && b.peRatio > 0 ? b.peRatio : 9999;
        return peA - peB;
      }
      if (sortBy === "pb_asc") {
        const pbA = a.pbRatio && a.pbRatio > 0 ? a.pbRatio : 9999;
        const pbB = b.pbRatio && b.pbRatio > 0 ? b.pbRatio : 9999;
        return pbA - pbB;
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
      className="min-h-screen bg-[#07090e] text-slate-100 pb-20"
      dir="rtl"
    >
      {/* Hero Banner */}
      <section className="relative overflow-hidden border-b border-white/10 bg-gradient-to-b from-emerald-950/30 via-[#0b101b] to-[#07090e] pt-10 pb-8 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
            <div className="space-y-3 max-w-3xl">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-bold">
                <Scale className="w-3.5 h-3.5" />
                <span>
                  محرك التقييم المالي والكمي (3-Tier Valuation Engine) — تحديث
                  يومي بعد إغلاق الجلسة
                </span>
              </div>
              <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-white">
                محدد السعر العادل ومؤشر الرخص{" "}
                <span className="text-emerald-400">(Fair Value Screener)</span>
              </h1>
              <p className="text-sm sm:text-base text-slate-300 leading-relaxed">
                تقييم شامل لجميع أسهم البورصة المصرية النشطة يدمج{" "}
                <strong className="text-white">معادلة بنجامين جراهام</strong>{" "}
                مع{" "}
                <strong className="text-white">
                  مضاعفات الربحية والقيمة الدفترية للقطاع
                </strong>{" "}
                والتوازن الكمي، مع عرض طريقة الحساب التفصيلية لكل سهم.
              </p>
            </div>

            {report && (
              <div className="flex flex-col items-start md:items-end gap-2 shrink-0">
                <div className="px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-xs text-slate-300 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                    <span>
                      تاريخ إغلاق الجلسة:{" "}
                      <strong className="text-white">
                        {report.latestSessionDate || "أحدث جلسة"}
                      </strong>
                    </span>
                  </div>
                  <div className="text-slate-400">
                    تغطية القوائم المالية المباشرة:{" "}
                    <strong className="text-emerald-400">
                      {report.summary.fundamentalCoverageCount}
                    </strong>{" "}
                    من{" "}
                    <strong className="text-white">
                      {report.summary.totalEvaluated}
                    </strong>{" "}
                    سهم نشط
                  </div>
                </div>
                <Link
                  href="/sharia"
                  className="inline-flex items-center gap-1.5 text-xs font-bold text-amber-400 hover:text-amber-300 transition-colors"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>انتقل إلى حاسبة التطهير الشرعي وزكاة الأسهم</span>
                  <ArrowUpRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            )}
          </div>

          {/* Summary KPI Cards */}
          {report && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mt-8">
              <button
                type="button"
                onClick={() => {
                  setStatusFilter("all");
                  setQuickPreset("all");
                }}
                className={`text-right p-4 rounded-2xl border transition-all cursor-pointer ${
                  statusFilter === "all" && quickPreset === "all"
                    ? "bg-white/[0.07] border-white/30 shadow-lg"
                    : "bg-white/[0.02] border-white/10 hover:bg-white/[0.04]"
                }`}
              >
                <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                  <span>إجمالي الأسهم المقيّمة</span>
                  <Layers className="w-4 h-4 text-slate-400" />
                </div>
                <div className="text-2xl sm:text-3xl font-black text-white">
                  {report.summary.totalEvaluated}
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  مكيشة يومياً بعد التشغيل الثاني
                </div>
              </button>

              <button
                type="button"
                onClick={() => {
                  setStatusFilter("undervalued");
                  setQuickPreset("all");
                }}
                className={`text-right p-4 rounded-2xl border transition-all cursor-pointer ${
                  statusFilter === "undervalued"
                    ? "bg-emerald-500/15 border-emerald-500/50 shadow-lg shadow-emerald-950/30"
                    : "bg-emerald-500/5 border-emerald-500/20 hover:bg-emerald-500/10"
                }`}
              >
                <div className="flex items-center justify-between text-xs text-emerald-300 mb-1">
                  <span>أقل من السعر العادل (فرص رخص)</span>
                  <TrendingUp className="w-4 h-4 text-emerald-400" />
                </div>
                <div className="text-2xl sm:text-3xl font-black text-emerald-400">
                  {report.summary.undervaluedCount}
                </div>
                <div className="text-[11px] text-emerald-300/80 mt-1">
                  يتداول بخصم +15% أو أكثر عن قيمته
                </div>
              </button>

              <button
                type="button"
                onClick={() => {
                  setStatusFilter("fair");
                  setQuickPreset("all");
                }}
                className={`text-right p-4 rounded-2xl border transition-all cursor-pointer ${
                  statusFilter === "fair"
                    ? "bg-amber-500/15 border-amber-500/50 shadow-lg"
                    : "bg-amber-500/5 border-amber-500/20 hover:bg-amber-500/10"
                }`}
              >
                <div className="flex items-center justify-between text-xs text-amber-300 mb-1">
                  <span>في النطاق العادل</span>
                  <CheckCircle2 className="w-4 h-4 text-amber-400" />
                </div>
                <div className="text-2xl sm:text-3xl font-black text-amber-400">
                  {report.summary.fairCount}
                </div>
                <div className="text-[11px] text-amber-300/80 mt-1">
                  قريب من قيمته العادلة (-12% إلى +15%)
                </div>
              </button>

              <button
                type="button"
                onClick={() => {
                  setStatusFilter("overvalued");
                  setQuickPreset("all");
                }}
                className={`text-right p-4 rounded-2xl border transition-all cursor-pointer ${
                  statusFilter === "overvalued"
                    ? "bg-rose-500/15 border-rose-500/50 shadow-lg"
                    : "bg-rose-500/5 border-rose-500/20 hover:bg-rose-500/10"
                }`}
              >
                <div className="flex items-center justify-between text-xs text-rose-300 mb-1">
                  <span>أعلى من السعر العادل (متضخم)</span>
                  <AlertTriangle className="w-4 h-4 text-rose-400" />
                </div>
                <div className="text-2xl sm:text-3xl font-black text-rose-400">
                  {report.summary.overvaluedCount}
                </div>
                <div className="text-[11px] text-rose-300/80 mt-1">
                  يتداول بعلاوة سعرية تتجاوز قيمته العادلة
                </div>
              </button>
            </div>
          )}
        </div>
      </section>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-6 space-y-6">
        {/* Interactive Valuation Chart Section */}
        {report && (
          <div className="rounded-2xl bg-[#0d1321] border border-white/10 p-4 sm:p-6 shadow-xl">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-white/10">
              <div>
                <h2 className="text-base sm:text-lg font-black text-white flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-emerald-400" />
                  <span>
                    الشارت التفاعلي لخريطة السعر العادل في البورصة المصرية
                  </span>
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  اضغط على أي سهم أو شريحة تقييم في الشارت لعرض معادلته الحسابية
                  أو فلترة القائمة مباشرة
                </p>
              </div>

              <div className="flex items-center gap-2 self-start sm:self-auto">
                <button
                  type="button"
                  onClick={() => setChartTab("bars")}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                    chartTab === "bars"
                      ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-300"
                      : "bg-white/[0.03] border-white/10 text-slate-400 hover:text-white"
                  }`}
                >
                  📊 مقارنة الأسهم (تحت العادل vs فوق العادل)
                </button>
                <button
                  type="button"
                  onClick={() => setChartTab("zones")}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                    chartTab === "zones"
                      ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-300"
                      : "bg-white/[0.03] border-white/10 text-slate-400 hover:text-white"
                  }`}
                >
                  🎯 توزيع شرائح السوق ({report.summary.totalEvaluated} سهم)
                </button>
              </div>
            </div>

            {chartTab === "bars" ? (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mt-5">
                {/* Left/Right interactive bar charts */}
                <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-2 gap-5">
                  {/* Top Undervalued */}
                  <div className="p-4 rounded-xl bg-emerald-950/15 border border-emerald-500/20">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-black text-emerald-400 flex items-center gap-1.5">
                        <TrendingUp className="w-4 h-4" />
                        أكبر الأسهم خصماً (تحت السعر العادل)
                      </span>
                      <span className="text-[10px] text-slate-400">
                        السعر الحالي مقابل العادل
                      </span>
                    </div>
                    <div className="space-y-2.5">
                      {chartComparisonData.topUndervalued.map((st) => {
                        const widthPct = Math.min(
                          100,
                          Math.max(20, Math.round((st.upsidePct / 120) * 100))
                        );
                        const isSelected =
                          selectedChartStock?.symbol === st.symbol;
                        return (
                          <button
                            key={st.symbol}
                            type="button"
                            onClick={() => setSelectedChartStock(st)}
                            className={`w-full text-right p-2 rounded-lg border transition-all cursor-pointer ${
                              isSelected
                                ? "bg-emerald-500/20 border-emerald-400"
                                : "bg-black/25 border-white/5 hover:border-emerald-500/40"
                            }`}
                          >
                            <div className="flex items-center justify-between text-xs mb-1">
                              <div className="flex items-center gap-1.5">
                                <span className="font-black text-white">
                                  {st.symbol}
                                </span>
                                <span className="text-[11px] text-slate-400 truncate max-w-[110px]">
                                  {st.nameAr}
                                </span>
                              </div>
                              <span className="font-mono font-black text-emerald-400">
                                +{st.upsidePct.toFixed(1)}%
                              </span>
                            </div>
                            <div className="w-full h-2 rounded-full bg-white/5 overflow-hidden">
                              <div
                                className="h-full rounded-full bg-gradient-to-l from-emerald-400 to-teal-500"
                                style={{ width: `${widthPct}%` }}
                              />
                            </div>
                            <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                              <span>الحالي: {st.currentPrice} ج.م</span>
                              <span className="text-emerald-300 font-bold">
                                العادل: {st.fairValue} ج.م
                              </span>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Top Overvalued */}
                  <div className="p-4 rounded-xl bg-rose-950/15 border border-rose-500/20">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-black text-rose-400 flex items-center gap-1.5">
                        <TrendingDown className="w-4 h-4" />
                        أكثر الأسهم علاوة (فوق السعر العادل)
                      </span>
                      <span className="text-[10px] text-slate-400">
                        السعر الحالي مقابل العادل
                      </span>
                    </div>
                    <div className="space-y-2.5">
                      {chartComparisonData.topOvervalued.map((st) => {
                        const widthPct = Math.min(
                          100,
                          Math.max(
                            20,
                            Math.round((Math.abs(st.upsidePct) / 60) * 100)
                          )
                        );
                        const isSelected =
                          selectedChartStock?.symbol === st.symbol;
                        return (
                          <button
                            key={st.symbol}
                            type="button"
                            onClick={() => setSelectedChartStock(st)}
                            className={`w-full text-right p-2 rounded-lg border transition-all cursor-pointer ${
                              isSelected
                                ? "bg-rose-500/20 border-rose-400"
                                : "bg-black/25 border-white/5 hover:border-rose-500/40"
                            }`}
                          >
                            <div className="flex items-center justify-between text-xs mb-1">
                              <div className="flex items-center gap-1.5">
                                <span className="font-black text-white">
                                  {st.symbol}
                                </span>
                                <span className="text-[11px] text-slate-400 truncate max-w-[110px]">
                                  {st.nameAr}
                                </span>
                              </div>
                              <span className="font-mono font-black text-rose-400">
                                {st.upsidePct.toFixed(1)}%
                              </span>
                            </div>
                            <div className="w-full h-2 rounded-full bg-white/5 overflow-hidden">
                              <div
                                className="h-full rounded-full bg-gradient-to-l from-rose-500 to-orange-500"
                                style={{ width: `${widthPct}%` }}
                              />
                            </div>
                            <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                              <span>الحالي: {st.currentPrice} ج.م</span>
                              <span className="text-rose-300 font-bold">
                                العادل: {st.fairValue} ج.م
                              </span>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Live Inspector Panel for Selected Chart Stock */}
                <div className="lg:col-span-4 rounded-xl bg-black/40 border border-white/10 p-4 flex flex-col justify-between">
                  {selectedChartStock ? (
                    <div className="space-y-4">
                      <div className="flex items-start justify-between gap-2 border-b border-white/10 pb-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-lg font-black text-white">
                              {selectedChartStock.symbol}
                            </span>
                            <span className="text-[11px] px-2 py-0.5 rounded-md bg-white/10 text-slate-300">
                              {selectedChartStock.sectorAr}
                            </span>
                          </div>
                          <p className="text-xs text-slate-400 mt-0.5">
                            {selectedChartStock.nameAr}
                          </p>
                        </div>
                        <Link
                          href={`/stocks/${selectedChartStock.symbol}`}
                          className="px-2.5 py-1.5 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs font-bold hover:bg-emerald-500/25 flex items-center gap-1"
                        >
                          <span>صفحة السهم</span>
                          <ArrowUpRight className="w-3.5 h-3.5" />
                        </Link>
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div className="p-2.5 rounded-lg bg-white/[0.03] border border-white/5">
                          <div className="text-[11px] text-slate-400">
                            سعر الإغلاق الحالي
                          </div>
                          <div className="text-base font-black text-white">
                            {selectedChartStock.currentPrice.toFixed(2)} ج.م
                          </div>
                        </div>
                        <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
                          <div className="text-[11px] text-emerald-300">
                            السعر العادل المحسوب
                          </div>
                          <div className="text-base font-black text-emerald-400">
                            {selectedChartStock.fairValue.toFixed(2)} ج.م
                          </div>
                        </div>
                      </div>

                      <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10 space-y-2">
                        <div className="flex items-center gap-1.5 text-xs font-bold text-amber-300">
                          <Calculator className="w-3.5 h-3.5" />
                          <span>
                            طريقة الحسبة ({selectedChartStock.modelLabelAr}):
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-300 font-mono bg-black/40 p-2 rounded border border-white/5">
                          {selectedChartStock.formulaSubstitutionAr}
                        </p>
                        <ul className="space-y-1.5 text-[11px] text-slate-300 leading-relaxed">
                          {selectedChartStock.formulaStepsAr.map((step, i) => (
                            <li key={i}>{step}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center text-slate-400 text-xs py-12">
                      اضغط على أي سهم في الشارت لعرض تفاصيل معادلته الحسابية
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="mt-5 space-y-4">
                {/* Stacked Spectrum Bar */}
                <div className="h-5 w-full rounded-full overflow-hidden flex bg-black/40 p-0.5 gap-0.5 border border-white/10">
                  {valuationZones.map((z) =>
                    z.pct > 0 ? (
                      <div
                        key={z.id}
                        style={{ width: `${Math.max(4, z.pct)}%` }}
                        className={`${z.color} h-full first:rounded-r-full last:rounded-l-full transition-all`}
                        title={`${z.label}: ${z.count} سهم (${z.pct}%)`}
                      />
                    ) : null
                  )}
                </div>

                {/* Clickable Zone Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                  {valuationZones.map((z) => (
                    <button
                      key={z.id}
                      type="button"
                      onClick={z.onClick}
                      className={`text-right p-3.5 rounded-xl bg-black/30 border ${z.borderColor} hover:bg-white/[0.04] transition-all cursor-pointer`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className={`text-xs font-black ${z.textColor}`}>
                          {z.shortLabel}
                        </span>
                        <span className="text-[11px] font-mono text-slate-400">
                          {z.pct}%
                        </span>
                      </div>
                      <div className="text-2xl font-black text-white">
                        {z.count}{" "}
                        <span className="text-xs font-normal text-slate-400">
                          سهم
                        </span>
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1">
                        اضغط لفلترة هذه الشريحة
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Easy Filters Bar */}
        <div className="p-4 rounded-2xl bg-[#0d1321] border border-white/10 space-y-3">
          {/* Quick One-Click Filter Pills */}
          <div className="flex flex-wrap items-center gap-2 pb-3 border-b border-white/10">
            <span className="text-xs font-bold text-slate-400 ml-1">
              فلاتر سريعة:
            </span>
            <button
              type="button"
              onClick={() => {
                setStatusFilter("all");
                setQuickPreset("all");
                setShariaOnly(false);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition-all cursor-pointer ${
                statusFilter === "all" &&
                quickPreset === "all" &&
                !shariaOnly
                  ? "bg-emerald-500 text-slate-950 border-emerald-400"
                  : "bg-white/[0.03] border-white/10 text-slate-300 hover:bg-white/[0.06]"
              }`}
            >
              كل الأسهم ({report?.summary.totalEvaluated ?? 0})
            </button>

            <button
              type="button"
              onClick={() => {
                setStatusFilter("undervalued");
                setQuickPreset("deep_discount");
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition-all cursor-pointer flex items-center gap-1 ${
                quickPreset === "deep_discount"
                  ? "bg-emerald-500/25 border-emerald-400 text-emerald-300"
                  : "bg-white/[0.03] border-white/10 text-slate-300 hover:bg-white/[0.06]"
              }`}
            >
              <Flame className="w-3.5 h-3.5 text-emerald-400" />
              <span>خصم قوي (+25% فأكثر)</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setQuickPreset(
                  quickPreset === "graham_only" ? "all" : "graham_only"
                );
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition-all cursor-pointer ${
                quickPreset === "graham_only"
                  ? "bg-indigo-500/25 border-indigo-400 text-indigo-300"
                  : "bg-white/[0.03] border-white/10 text-slate-300 hover:bg-white/[0.06]"
              }`}
            >
              💎 تقييم جراهام المالي الكامل
            </button>

            <button
              type="button"
              onClick={() => {
                setQuickPreset(
                  quickPreset === "low_rsi_undervalued"
                    ? "all"
                    : "low_rsi_undervalued"
                );
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition-all cursor-pointer ${
                quickPreset === "low_rsi_undervalued"
                  ? "bg-cyan-500/25 border-cyan-400 text-cyan-300"
                  : "bg-white/[0.03] border-white/10 text-slate-300 hover:bg-white/[0.06]"
              }`}
            >
              🎯 رخيص مالياً + RSI غير متضخم (&lt;55)
            </button>

            <button
              type="button"
              onClick={() => setShariaOnly(!shariaOnly)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition-all cursor-pointer flex items-center gap-1 ${
                shariaOnly
                  ? "bg-amber-500/20 border-amber-500/50 text-amber-300"
                  : "bg-white/[0.03] border-white/10 text-slate-300 hover:bg-white/[0.06]"
              }`}
            >
              <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
              <span>متوافق مع الشريعة (EGX33)</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
            {/* Search */}
            <div className="md:col-span-5 relative">
              <Search className="w-4 h-4 text-slate-400 absolute right-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="ابحث بكود السهم أو الاسم العربي أو القطاع (مثال: COMI، فوري، بنوك)..."
                className="w-full pr-10 pl-4 py-2.5 rounded-xl bg-black/40 border border-white/10 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500/50"
              />
            </div>

            {/* Sector Filter */}
            <div className="md:col-span-4 flex items-center gap-2">
              <Filter className="w-4 h-4 text-slate-400 shrink-0" />
              <select
                value={sectorFilter}
                onChange={(e) => setSectorFilter(e.target.value)}
                className="w-full px-3 py-2.5 rounded-xl bg-black/40 border border-white/10 text-xs sm:text-sm text-white focus:outline-none focus:border-emerald-500/50"
              >
                <option value="all" className="bg-slate-900">
                  جميع القطاعات ({report?.sectors.length || 0})
                </option>
                {report?.sectors.map((sec) => (
                  <option key={sec} value={sec} className="bg-slate-900">
                    {sec}
                  </option>
                ))}
              </select>
            </div>

            {/* Sort By */}
            <div className="md:col-span-3">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="w-full px-3 py-2.5 rounded-xl bg-black/40 border border-white/10 text-xs sm:text-sm text-white focus:outline-none focus:border-emerald-500/50"
              >
                <option value="upside_desc" className="bg-slate-900">
                  الأكثر رخصاً (أعلى عائد للسعر العادل)
                </option>
                <option value="upside_asc" className="bg-slate-900">
                  الأكثر تضخماً (أعلى من السعر العادل)
                </option>
                <option value="pe_asc" className="bg-slate-900">
                  الأقل مضاعف ربحية (P/E)
                </option>
                <option value="pb_asc" className="bg-slate-900">
                  الأقل مضاعف قيمة دفترية (P/B)
                </option>
                <option value="yield_desc" className="bg-slate-900">
                  الأعلى عائد توزيعات نقدية (Yield)
                </option>
              </select>
            </div>
          </div>
        </div>

        {/* Loading / Error / Table */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 py-8">
            {Array.from({ length: 9 }).map((_, i) => (
              <div
                key={i}
                className="h-56 rounded-2xl bg-white/[0.02] border border-white/5 animate-pulse p-5"
              />
            ))}
          </div>
        ) : error ? (
          <div className="p-8 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-center text-rose-300">
            {error}
          </div>
        ) : filteredStocks.length === 0 ? (
          <div className="p-12 rounded-2xl bg-white/[0.02] border border-white/10 text-center text-slate-400">
            لا توجد أسهم مطابقة لمعايير البحث الحالية. جرب تغيير الفلتر أو
            القطاع.
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between text-xs text-slate-400 px-1">
              <span>
                عدد الأسهم المطابقة:{" "}
                <strong className="text-white">{filteredStocks.length}</strong>{" "}
                سهم
              </span>
              {!showAllRows && filteredStocks.length > 60 && (
                <button
                  type="button"
                  onClick={() => setShowAllRows(true)}
                  className="text-emerald-400 hover:underline font-bold cursor-pointer"
                >
                  عرض جميع الأسهم الـ {filteredStocks.length} دفعة واحدة
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {displayedStocks.map((stock) => (
                <FairValueCard key={stock.symbol} stock={stock} />
              ))}
            </div>

            {!showAllRows && filteredStocks.length > 60 && (
              <div className="text-center pt-4">
                <button
                  type="button"
                  onClick={() => setShowAllRows(true)}
                  className="px-6 py-3 rounded-xl bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-xs font-black hover:bg-emerald-500/25 transition-all cursor-pointer"
                >
                  إظهار كامل قائمة الأسهم ({filteredStocks.length} سهم)
                </button>
              </div>
            )}
          </>
        )}

        {/* Comprehensive Feature Explanation & Methodology Guide */}
        <section className="rounded-2xl bg-[#0d1321] border border-white/10 p-5 sm:p-7 space-y-6 mt-10">
          <div className="flex items-start gap-3">
            <BookOpen className="w-6 h-6 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <h2 className="text-lg sm:text-xl font-black text-white">
                كيف يعمل محرك السعر العادل ومؤشر الرخص (3-Tier Valuation Engine)؟
              </h2>
              <p className="text-xs sm:text-sm text-slate-300 mt-1 leading-relaxed">
                يعتمد المحرك على منهجية تقييم هرمية من 3 مستويات لضمان تغطية
                شاملة لجميع أسهم البورصة المصرية الـ 254 النشطة يومياً بعد
                إغلاق الجلسة، مع مراعاة الفروق الهيكلية بين القطاعات (كالبنوك،
                العقارات، البتروكيماويات، والأغذية).
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-white/[0.02] border border-emerald-500/20 space-y-2">
              <div className="text-xs font-black text-emerald-400">
                المستوى الأول (Tier 1): نموذج جراهام + مضاعفات القطاع
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                يطبق على الشركات الرابحة ذات القيمة الدفترية الموجبة، ويدمج{" "}
                <strong>معادلة بنجامين جراهام</strong>{" "}
                <span className="font-mono text-emerald-300">
                  √(22.5 × EPS × BVPS)
                </span>{" "}
                بوزن 50%، مع السعر المستهدف وفق{" "}
                <strong>مكرر ربحية القطاع (P/E)</strong> بوزن 30%، و
                <strong>مضاعف القيمة الدفترية للقطاع (P/B)</strong> بوزن 20%.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-white/[0.02] border border-amber-500/20 space-y-2">
              <div className="text-xs font-black text-amber-400">
                المستوى الثاني (Tier 2): المضاعف القطاعي النسبي (P/E أو P/B)
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                للشركات التي يتوفر لها ربحية سهم موجبة أو قيمة دفترية صافية، يتم
                تقييم السهم بمقارنته مع{" "}
                <strong>وسيط مضاعفات الشركات المثيلة في نفس القطاع</strong> داخل
                البورصة المصرية لاكتشاف الأسهم المتداولة بخصم عن أقرانها.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-white/[0.02] border border-indigo-500/20 space-y-2">
              <div className="text-xs font-black text-indigo-400">
                المستوى الثالث (Tier 3): التوازن الكمي (VWAP20 + EMA200)
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                للشركات الناشئة أو التي تمر بدورات إعادة هيكلة، يُحسب السعر
                التوازني من{" "}
                <strong>60% متوسط 200 يوم + 40% متوسط التكلفة المرجح بالسيولة (VWAP 20)</strong>{" "}
                لتحديد مركز ثقل القيمة السوقية.
              </p>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20 text-xs text-slate-300 flex items-start gap-2.5">
            <Info className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <strong className="text-white">نصيحة استثمارية ذكية:</strong> السهم
              الأقل من سعره العادل يمثل <strong>فرصة قيمة (Value)</strong>، ولكن
              أفضل توقيت للدخول يتحقق عندما يجتمع الرخص المالي مع{" "}
              <strong>إشارة تجميع فنية أو ارتداد من دعم (Spring)</strong>. يمكنك
              أيضاً سؤال <strong>البوت الذكي (AI Chat)</strong> مباشرة عن السعر
              العادل وطريقة حسابه لأي سهم!
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function FairValueCard({ stock }: { stock: FairValueStockItem }) {
  const [showFormula, setShowFormula] = useState(false);
  const isUnder = stock.status === "undervalued";
  const isOver = stock.status === "overvalued";

  const badgeStyles = isUnder
    ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
    : isOver
    ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
    : "bg-amber-500/15 text-amber-300 border-amber-500/30";

  const statusLabel = isUnder
    ? "أقل من السعر العادل 🟢"
    : isOver
    ? "أعلى من السعر العادل 🔴"
    : "في النطاق العادل ⚖️";

  // Meter bar position (0% = heavily overvalued, 50% = fair, 100% = deeply undervalued)
  const meterPct = Math.max(
    6,
    Math.min(94, Math.round(50 + stock.upsidePct * 0.9))
  );

  return (
    <div className="group rounded-2xl bg-[#0d1321] border border-white/10 hover:border-emerald-500/40 transition-all p-5 flex flex-col justify-between shadow-lg">
      <div>
        {/* Top Row */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <Link
                href={`/stocks/${stock.symbol}`}
                className="text-lg font-black text-white group-hover:text-emerald-400 transition-colors"
              >
                {stock.symbol}
              </Link>
              {stock.isSharia && (
                <span
                  title="متوافق مع الشريعة الإسلامية - مؤشر EGX33"
                  className="px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-[10px] font-bold text-amber-300"
                >
                  شريعة EGX33
                </span>
              )}
            </div>
            <p className="text-xs text-slate-300 font-medium line-clamp-1 mt-0.5">
              {stock.nameAr}
            </p>
            <span className="inline-block text-[11px] text-slate-400 mt-0.5">
              {stock.sectorAr}
            </span>
          </div>

          <span
            className={`px-2.5 py-1 rounded-lg border text-[11px] font-bold shrink-0 ${badgeStyles}`}
          >
            {statusLabel}
          </span>
        </div>

        {/* Price vs Fair Value Box */}
        <div className="grid grid-cols-3 gap-2 my-4 p-3 rounded-xl bg-black/40 border border-white/5">
          <div>
            <div className="text-[11px] text-slate-400">السعر الحالي</div>
            <div className="text-base font-black text-white mt-0.5">
              {stock.currentPrice.toFixed(2)}{" "}
              <span className="text-[10px] font-normal text-slate-400">
                ج.م
              </span>
            </div>
          </div>

          <div className="border-x border-white/10 px-2">
            <div className="text-[11px] text-emerald-300/90">السعر العادل</div>
            <div className="text-base font-black text-emerald-400 mt-0.5">
              {stock.fairValue.toFixed(2)}{" "}
              <span className="text-[10px] font-normal text-emerald-400/70">
                ج.م
              </span>
            </div>
          </div>

          <div className="text-left">
            <div className="text-[11px] text-slate-400">هامش الأمان / الفرق</div>
            <div
              className={`text-base font-black mt-0.5 flex items-center justify-end gap-0.5 ${
                stock.upsidePct > 0
                  ? "text-emerald-400"
                  : stock.upsidePct < 0
                  ? "text-rose-400"
                  : "text-slate-300"
              }`}
              dir="ltr"
            >
              {stock.upsidePct > 0 ? "+" : ""}
              {stock.upsidePct.toFixed(1)}%
            </div>
          </div>
        </div>

        {/* Visual Meter */}
        <div className="space-y-1 mb-4">
          <div className="flex justify-between text-[10px] text-slate-400">
            <span>متضخم سعرياً</span>
            <span className="text-slate-300 font-medium">
              {stock.modelLabelAr}
            </span>
            <span>رخيص (فرصة)</span>
          </div>
          <div className="h-2 w-full rounded-full bg-gradient-to-l from-emerald-500/40 via-amber-500/30 to-rose-500/40 relative overflow-hidden">
            <div
              className="absolute top-0 bottom-0 w-2.5 rounded-full bg-white shadow-[0_0_8px_#fff]"
              style={{ right: `calc(${meterPct}% - 5px)` }}
            />
          </div>
        </div>

        {/* Fundamental Multiples Grid */}
        <div className="grid grid-cols-4 gap-1.5 text-center text-[11px] bg-white/[0.02] rounded-xl p-2 border border-white/5">
          <div>
            <div className="text-slate-400">مكرر P/E</div>
            <div className="font-bold text-white mt-0.5">
              {stock.peRatio ? `${stock.peRatio}x` : "—"}
            </div>
          </div>
          <div>
            <div className="text-slate-400">الدفترية P/B</div>
            <div className="font-bold text-white mt-0.5">
              {stock.pbRatio ? `${stock.pbRatio}x` : "—"}
            </div>
          </div>
          <div>
            <div className="text-slate-400">ربحية EPS</div>
            <div className="font-bold text-white mt-0.5">
              {stock.eps !== null ? stock.eps : "—"}
            </div>
          </div>
          <div>
            <div className="text-slate-400">دفترية السهم</div>
            <div className="font-bold text-white mt-0.5">
              {stock.bvps !== null ? stock.bvps : "—"}
            </div>
          </div>
        </div>

        {/* Collapsible Formula Calculation Method */}
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowFormula(!showFormula)}
            className="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.06] border border-white/10 text-[11px] font-bold text-emerald-300 transition-colors cursor-pointer"
          >
            <span className="flex items-center gap-1.5">
              <Calculator className="w-3.5 h-3.5" />
              <span>طريقة حساب السعر العادل للسهم</span>
            </span>
            {showFormula ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>

          {showFormula && (
            <div className="mt-2 p-3 rounded-xl bg-black/50 border border-emerald-500/20 text-[11px] text-slate-300 space-y-1.5 leading-relaxed">
              <div className="font-bold text-white">
                {stock.formulaEquationAr}
              </div>
              <div
                className="font-mono text-emerald-300 bg-white/[0.03] px-2 py-1 rounded border border-white/5 text-left"
                dir="ltr"
              >
                {stock.formulaSubstitutionAr}
              </div>
              <ul className="space-y-1 pt-1 text-slate-300">
                {stock.formulaStepsAr.map((step, idx) => (
                  <li key={idx}>{step}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Footer Link */}
      <div className="mt-3 pt-2.5 border-t border-white/5 flex items-center justify-between text-[11px] text-slate-400">
        <span>
          وسيط القطاع: P/E {stock.sectorMedianPe}x | P/B {stock.sectorMedianPb}x
        </span>
        <Link
          href={`/stocks/${stock.symbol}`}
          className="inline-flex items-center gap-1 text-emerald-400 font-bold hover:text-emerald-300"
        >
          <span>تحليل السهم</span>
          <ArrowUpRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  );
}
