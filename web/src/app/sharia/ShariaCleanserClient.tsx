"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Scale,
  Calculator,
  Search,
  ShieldCheck,
  Sparkles,
  CheckCircle2,
  HeartHandshake,
  Coins,
  ArrowUpRight,
  Gem,
  AlertTriangle,
  Info,
  X,
  BookOpen,
} from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import {
  SHARIA_COMPLIANT_EGX_SYMBOLS,
  isShariaCompliant,
  getStockPurificationMeta,
  type ShariaStockMeta,
} from "@/lib/shariaStocks";
import { CANONICAL_STOCK_NAMES } from "@/lib/ai/stock-names";
import type { FairValueReport, FairValueStockItem } from "@/lib/market/fair-value";

const SECTOR_PURIFICATION_RATES: Record<string, number> = {
  "اتصالات": 2.8,
  "تكنولوجيا مالية": 2.2,
  "تكنولوجيا ومدفوعات رقمية": 2.2,
  "عقارات": 3.5,
  "عقارات وإنشاءات": 3.5,
  "كيماويات وأسمدة": 2.4,
  "أسمدة وكيماويات": 2.4,
  "كيماويات وبتروكيماويات": 2.5,
  "صناعي وهندسي": 2.9,
  "صناعات هندسية وكهربائية": 2.9,
  "رعاية صحية وأدوية": 1.8,
  "أغذية ومشروبات": 2.1,
  "أغذية ودواجن": 1.9,
  "طاقة وبترول": 2.6,
};

function getDefaultPurificationRate(sectorAr?: string): number {
  if (!sectorAr) return 2.5;
  return SECTOR_PURIFICATION_RATES[sectorAr] ?? 2.5;
}

const POPULAR_SHARIA_SYMBOLS = ["ABUK", "FAIT", "SWDY", "ORWE", "MASR", "MFPC", "RACC", "IFAP"];

export default function ShariaCleanserClient({
  initialReport = null,
}: {
  initialReport?: FairValueReport | null;
}) {
  const { language } = useLanguage();
  const isAr = language === "ar";

  const [report, setReport] = useState<FairValueReport | null>(initialReport);
  const [loading, setLoading] = useState(!initialReport);
  const [search, setSearch] = useState("");

  // Calculator State
  const [selectedSymbol, setSelectedSymbol] = useState<string>("ABUK");
  const [sharesCount, setSharesCount] = useState<string>("1000");
  const [couponPerShare, setCouponPerShare] = useState<string>("5.00");
  const [purificationRate, setPurificationRate] = useState<string>(() => {
    const meta = getStockPurificationMeta("ABUK");
    return meta ? meta.purificationRatePct.toString() : "0.9";
  });
  const [calcMode, setCalcMode] = useState<"dividend" | "zakat">("dividend");

  useEffect(() => {
    if (initialReport) return;
    let active = true;
    async function load() {
      try {
        setLoading(true);
        const res = await fetch("/api/market/fair-value");
        if (res.ok) {
          const data: FairValueReport = await res.json();
          if (active) setReport(data);
        }
      } catch {
        // Fallback
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [initialReport]);

  const allStocks = useMemo<FairValueStockItem[]>(() => {
    if (report?.stocks?.length) {
      return report.stocks;
    }
    return Object.keys(CANONICAL_STOCK_NAMES).map((sym) => {
      const info = CANONICAL_STOCK_NAMES[sym];
      return {
        symbol: sym,
        nameAr: info?.name_ar || sym,
        nameEn: info?.name_en || sym,
        sectorAr: info?.sector || (isAr ? "البورصة المصرية" : "EGX Market"),
        logoUrl: null,
        currentPrice: 0,
        changePct: null,
        fairValue: 0,
        grahamValue: null,
        upsidePct: 0,
        status: "fair",
        modelType: "quant_vwap",
        modelLabelAr: isAr ? "التوازن الكمي" : "Quant Equilibrium",
        formulaEquationAr: "",
        formulaSubstitutionAr: "",
        formulaStepsAr: [],
        peRatio: null,
        pbRatio: null,
        eps: null,
        bvps: null,
        sectorMedianPe: 0,
        sectorMedianPb: 0,
        dividendYield: null,
        roe: null,
        marketCap: null,
        rsi14: null,
        ema200: null,
        vwap20: null,
        isSharia: isShariaCompliant(sym),
        date: null,
      } as FairValueStockItem;
    });
  }, [report, isAr]);

  const selectedStock = useMemo(() => {
    return (
      allStocks.find((s) => s.symbol === selectedSymbol) || {
        symbol: selectedSymbol,
        nameAr: CANONICAL_STOCK_NAMES[selectedSymbol]?.name_ar || selectedSymbol,
        nameEn: CANONICAL_STOCK_NAMES[selectedSymbol]?.name_en || selectedSymbol,
        sectorAr: CANONICAL_STOCK_NAMES[selectedSymbol]?.sector || "صناعة",
        currentPrice: 60.0,
        fairValue: 84.55,
        upsidePct: 40.9,
        isSharia: isShariaCompliant(selectedSymbol),
      }
    );
  }, [allStocks, selectedSymbol]);

  const currentMeta = useMemo(() => {
    return getStockPurificationMeta(selectedSymbol);
  }, [selectedSymbol]);

  // When selected symbol changes, update default purification rate
  const onSelectStock = (sym: string) => {
    setSelectedSymbol(sym);
    const meta = getStockPurificationMeta(sym);
    if (meta) {
      setPurificationRate(meta.purificationRatePct.toString());
    } else {
      const st = allStocks.find((s) => s.symbol === sym);
      const rate = getDefaultPurificationRate(st?.sectorAr);
      setPurificationRate(rate.toString());
    }
  };

  // Filtered stocks for search
  const filteredStocks = useMemo(() => {
    if (!search.trim()) {
      return allStocks.filter((s) => s.isSharia);
    }
    const q = search.trim().toLowerCase();
    return allStocks.filter(
      (s) =>
        s.symbol.toLowerCase().includes(q) ||
        s.nameAr.toLowerCase().includes(q) ||
        s.nameEn.toLowerCase().includes(q) ||
        (s.sectorAr && s.sectorAr.toLowerCase().includes(q))
    );
  }, [allStocks, search]);

  // Calculation Math
  const numShares = Math.max(0, parseFloat(sharesCount) || 0);
  const numCoupon = Math.max(0, parseFloat(couponPerShare) || 0);
  const numRate = Math.max(0, parseFloat(purificationRate) || 0);
  const currentPrice = selectedStock.currentPrice > 0 ? selectedStock.currentPrice : 20.0;

  const totalDividend = numShares * numCoupon;
  const purificationAmount = totalDividend * (numRate / 100);
  const netHalalDividend = totalDividend - purificationAmount;

  // Zakat (2.5% on market value for trading/speculation)
  const totalMarketValue = numShares * currentPrice;
  const zakatAmount = totalMarketValue * 0.025;

  return (
    <div
      className="min-h-screen bg-zinc-50 dark:bg-[#07090e] text-zinc-900 dark:text-zinc-100 pb-20 transition-colors duration-200"
      dir={isAr ? "rtl" : "ltr"}
    >
      {/* Hero Header */}
      <section className="relative overflow-hidden border-b-2 border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 pt-8 pb-8 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto space-y-6">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
            <div className="space-y-3 max-w-3xl">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 dark:bg-emerald-500/20 border border-emerald-500/30 text-emerald-700 dark:text-emerald-400 text-xs font-black">
                <ShieldCheck className="w-4 h-4" />
                <span>
                  {isAr
                    ? "أداة مجانية · قائمة مؤشر الشريعة EGX33 وحاسبة تطهير الكوبونات والزكاة"
                    : "Free Tool · Official EGX33 Sharia Index & Dividend Cleanser Calculator"}
                </span>
              </div>
              <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-zinc-950 dark:text-white">
                {isAr ? "حاسبة التوافق الشرعي وتطهير الكوبونات" : "Sharia Cleanser & Zakat Calculator"}{" "}
                <span className="text-emerald-600 dark:text-emerald-400 font-mono text-xl sm:text-3xl">
                  (Sharia Cleanser)
                </span>
              </h1>
              <p className="text-sm sm:text-base text-zinc-600 dark:text-zinc-300 leading-relaxed">
                {isAr ? (
                  <>
                    دليلك المتكامل للأسهم المتوافقة مع معايير الشريعة الإسلامية في البورصة المصرية، مع حاسبة فورية لحساب{" "}
                    <strong className="text-zinc-950 dark:text-white">مبلغ تطهير التوزيعات النقدية (الكوبونات)</strong>{" "}
                    من عوائد أذون الخزانة والفوائد العرضية، وحاسبة{" "}
                    <strong className="text-zinc-950 dark:text-white">زكاة الأسهم (2.5%)</strong>.
                  </>
                ) : (
                  <>
                    Your complete guide to Sharia-compliant EGX33 stocks, featuring an instant calculator for{" "}
                    <strong className="text-zinc-950 dark:text-white">Dividend Purification Amounts</strong>{" "}
                    and <strong className="text-zinc-950 dark:text-white">Stock Zakat (2.5%)</strong>.
                  </>
                )}
              </p>
            </div>

            <div className="shrink-0 flex flex-col gap-2">
              <Link
                href="/fair-value"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-zinc-100 dark:bg-zinc-800 hover:bg-emerald-500 hover:text-white dark:hover:bg-emerald-500 dark:hover:text-white border-2 border-zinc-200 dark:border-zinc-700 text-xs font-bold text-zinc-700 dark:text-zinc-300 transition-colors"
              >
                <Scale className="w-4 h-4 text-emerald-500" />
                <span>{isAr ? "تصفح محدد السعر العادل ومؤشر الرخص ←" : "Browse Fair Value Screener →"}</span>
              </Link>
            </div>
          </div>

          {/* 🔍 Prominent Universal Search Bar (محرك بحث لجميع الأسهم المصرية) */}
          <div className="relative pt-2">
            <div className="relative flex items-center">
              <Search className={`absolute ${isAr ? "right-4" : "left-4"} w-5 h-5 text-zinc-400 pointer-events-none`} />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={
                  isAr
                    ? "ابحث عن أي سهم في البورصة المصرية لفحص شرعيته وتطهيره... (مثال: أبو قير، ABUK، موبكو، السويدي، فوري)"
                    : "Search any EGX stock to check Sharia status, purification & Zakat... (e.g. ABUK, MFPC, SWDY, FWRY)"
                }
                className={`w-full h-13 ${isAr ? "pr-12 pl-12" : "pl-12 pr-12"} rounded-2xl bg-white dark:bg-zinc-800 border-2 border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white placeholder:text-zinc-400 font-bold text-sm sm:text-base focus:outline-none focus:border-emerald-500 dark:focus:border-emerald-400 shadow-sm transition-all`}
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch("")}
                  className={`absolute ${isAr ? "left-4" : "right-4"} p-1.5 rounded-full hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-400 hover:text-zinc-700 dark:hover:text-white transition-colors cursor-pointer`}
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Quick Chips */}
            <div className="flex items-center gap-2 mt-2.5 overflow-x-auto pb-1 text-xs">
              <span className="text-zinc-500 dark:text-zinc-400 font-bold shrink-0">
                {isAr ? "⚡ أسهم شرعية بارزة:" : "⚡ Popular Sharia:"}
              </span>
              {POPULAR_SHARIA_SYMBOLS.map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => onSelectStock(sym)}
                  className={`px-2.5 py-1 rounded-lg border font-mono font-bold transition-colors cursor-pointer ${
                    selectedSymbol === sym
                      ? "bg-emerald-500 text-white border-emerald-600 shadow-sm"
                      : "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700 hover:border-emerald-500"
                  }`}
                >
                  {sym}
                </button>
              ))}
              <span className="text-emerald-600 dark:text-emerald-400 font-bold shrink-0 ms-2">
                {isAr
                  ? `(معروض ${filteredStocks.length} سهم)`
                  : `(${filteredStocks.length} stocks shown)`}
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Main Content Grid */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Interactive Calculator Box */}
        <section className="lg:col-span-5 bg-white dark:bg-zinc-900 border-2 border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 sm:p-7 shadow-sm space-y-6">
          <div className="flex items-center justify-between border-b-2 border-zinc-100 dark:border-zinc-800 pb-4">
            <div className="flex items-center gap-2">
              <Calculator className="w-5 h-5 text-emerald-500" />
              <h2 className="text-lg sm:text-xl font-black text-zinc-950 dark:text-white">
                {isAr ? "الحاسبة الشرعية الفورية" : "Instant Sharia Calculator"}
              </h2>
            </div>

            {/* Mode Switcher */}
            <div className="inline-flex p-1 rounded-xl bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700">
              <button
                type="button"
                onClick={() => setCalcMode("dividend")}
                className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  calcMode === "dividend"
                    ? "bg-white dark:bg-zinc-900 text-emerald-600 dark:text-emerald-400 shadow-sm font-black"
                    : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white"
                }`}
              >
                {isAr ? "تطهير الكوبون" : "Purification"}
              </button>
              <button
                type="button"
                onClick={() => setCalcMode("zakat")}
                className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  calcMode === "zakat"
                    ? "bg-white dark:bg-zinc-900 text-emerald-600 dark:text-emerald-400 shadow-sm font-black"
                    : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white"
                }`}
              >
                {isAr ? "زكاة الأسهم" : "Stock Zakat"}
              </button>
            </div>
          </div>

          {/* Active Stock Selector Card */}
          <div className="p-4 rounded-2xl bg-zinc-50 dark:bg-zinc-800/60 border-2 border-zinc-200 dark:border-zinc-700 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono font-black text-sm text-zinc-950 dark:text-white px-2 py-0.5 rounded-md bg-zinc-200 dark:bg-zinc-700">
                    {selectedStock.symbol}
                  </span>
                  {selectedStock.isSharia ? (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 text-xs font-bold">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>{isAr ? "متوافق مع EGX33 ✅" : "EGX33 Compliant ✅"}</span>
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-400 text-xs font-bold">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      <span>{isAr ? "غير مدرج بمؤشر الشريعة" : "Not in EGX33"}</span>
                    </span>
                  )}
                </div>
                <div className="text-base font-bold text-zinc-900 dark:text-white mt-1.5">
                  {isAr ? selectedStock.nameAr : selectedStock.nameEn || selectedStock.nameAr}
                </div>
                <div className="text-xs text-zinc-500 dark:text-zinc-400">
                  {selectedStock.sectorAr}
                </div>
              </div>

              <div className="text-end">
                <div className="text-xs text-zinc-500 dark:text-zinc-400">
                  {isAr ? "السعر الحالي" : "Current"}
                </div>
                <div className="text-base font-black font-mono text-zinc-950 dark:text-white">
                  {currentPrice.toFixed(2)} {isAr ? "ج.م" : "EGP"}
                </div>
                {selectedStock.fairValue > 0 && (
                  <div className="text-[11px] font-bold text-emerald-600 dark:text-emerald-400 font-mono mt-0.5">
                    {isAr ? "العادل:" : "Fair:"} {selectedStock.fairValue.toFixed(2)} ج.م
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Calculator Inputs */}
          <div className="space-y-4">
            {/* 1. Stock Selector Dropdown */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-zinc-700 dark:text-zinc-300">
                {isAr ? "1. اختر السهم:" : "1. Select Stock:"}
              </label>
              <select
                value={selectedSymbol}
                onChange={(e) => onSelectStock(e.target.value)}
                className="w-full h-11 px-3.5 rounded-xl bg-zinc-100 dark:bg-zinc-800 border-2 border-zinc-300 dark:border-zinc-700 text-xs font-bold text-zinc-900 dark:text-white focus:outline-none focus:border-emerald-500"
              >
                {allStocks.map((s) => (
                  <option key={s.symbol} value={s.symbol}>
                    {s.symbol} — {isAr ? s.nameAr : s.nameEn || s.nameAr} ({s.sectorAr})
                  </option>
                ))}
              </select>
            </div>

            {/* 2. Shares Count */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-zinc-700 dark:text-zinc-300">
                {isAr ? "2. عدد الأسهم التي تمتلكها في محفظتك:" : "2. Number of Shares Owned:"}
              </label>
              <input
                type="number"
                min="1"
                value={sharesCount}
                onChange={(e) => setSharesCount(e.target.value)}
                placeholder="1000"
                className="w-full h-11 px-3.5 rounded-xl bg-zinc-100 dark:bg-zinc-800 border-2 border-zinc-300 dark:border-zinc-700 text-sm font-mono font-bold text-zinc-900 dark:text-white focus:outline-none focus:border-emerald-500"
              />
            </div>

            {calcMode === "dividend" ? (
              <>
                {/* 3. Coupon per share */}
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-zinc-700 dark:text-zinc-300">
                    {isAr ? "3. قيمة الكوبون النقدي الموزع للسهم (بالجنيه):" : "3. Cash Dividend Per Share (EGP):"}
                  </label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    value={couponPerShare}
                    onChange={(e) => setCouponPerShare(e.target.value)}
                    placeholder="5.00"
                    className="w-full h-11 px-3.5 rounded-xl bg-zinc-100 dark:bg-zinc-800 border-2 border-zinc-300 dark:border-zinc-700 text-sm font-mono font-bold text-zinc-900 dark:text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>

                {/* 4. Purification Rate Slider */}
                <div className="space-y-2 pt-1">
                  <div className="flex items-center justify-between text-xs font-bold">
                    <span className="text-zinc-700 dark:text-zinc-300">
                      {isAr ? "4. نسبة التطهير المقدرة للدخل غير التشغيلي:" : "4. Estimated Purification Ratio:"}
                    </span>
                    <span className="text-emerald-600 dark:text-emerald-400 font-mono font-black text-sm">
                      {numRate}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0.0"
                    max="8.0"
                    step="0.1"
                    value={purificationRate}
                    onChange={(e) => setPurificationRate(e.target.value)}
                    className="w-full accent-emerald-500 cursor-pointer"
                  />
                  <div className="flex justify-between text-[10px] text-zinc-400 font-mono">
                    <span>0.0% ({isAr ? "نقي 100%" : "Pure Halal"})</span>
                    <span>2.5% ({isAr ? "متوسط معظم القطاعات" : "Sector Median"})</span>
                    <span>8.0% ({isAr ? "سيولة بنكية عالية" : "High Cash"})</span>
                  </div>

                  {/* Stock-specific Audited Rate Badge */}
                  {currentMeta && (
                    <div
                      className={`p-3 rounded-2xl border text-xs space-y-1 mt-2.5 transition-all ${
                        currentMeta.isPureHalal
                          ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-800 dark:text-emerald-300"
                          : "bg-blue-500/10 border-blue-500/30 text-blue-900 dark:text-blue-300"
                      }`}
                    >
                      <div className="flex items-center gap-1.5 font-black">
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                        <span>
                          {currentMeta.isPureHalal
                            ? isAr
                              ? "سهم إسلامي نقي 100% — لا يتطلب أي تطهير للكوبون (0.0%)"
                              : "100% Pure Islamic Institution — 0.0% Purification Required"
                            : isAr
                            ? `نسبة مالية مدققة للسهم: ${currentMeta.purificationRatePct}% (معيار 21 للأيوفي)`
                            : `Audited Financial Ratio: ${currentMeta.purificationRatePct}% (AAOIFI 21)`}
                        </span>
                      </div>
                      <div className="text-[11px] text-zinc-600 dark:text-zinc-300 leading-relaxed font-medium">
                        {currentMeta.notesAr}
                      </div>
                      <div className="text-[10px] text-zinc-500 dark:text-zinc-400 font-mono">
                        {isAr ? "المرجعية:" : "Source:"} {currentMeta.sourceLabelAr}
                      </div>
                    </div>
                  )}
                </div>

                {/* Calculated Result Box */}
                <div className="p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-950/30 border-2 border-emerald-300 dark:border-emerald-800 space-y-3 pt-4">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-zinc-600 dark:text-zinc-400 font-bold">
                      {isAr ? "إجمالي الكوبون المستلم:" : "Total Dividend Received:"}
                    </span>
                    <span className="font-mono font-black text-sm text-zinc-900 dark:text-white">
                      {totalDividend.toLocaleString("en-US", { minimumFractionDigits: 2 })} {isAr ? "ج.م" : "EGP"}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-sm font-black border-t border-emerald-200 dark:border-emerald-800/80 pt-2">
                    <span className="text-rose-700 dark:text-rose-400 flex items-center gap-1.5">
                      <HeartHandshake className="w-4 h-4" />
                      <span>{isAr ? "مبلغ التطهير الواجب إخراجه:" : "Required Purification Charity:"}</span>
                    </span>
                    <span className="font-mono text-xl text-rose-600 dark:text-rose-400">
                      {purificationAmount.toLocaleString("en-US", { minimumFractionDigits: 2 })} {isAr ? "ج.م" : "EGP"}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs font-bold border-t border-emerald-200 dark:border-emerald-800/80 pt-2">
                    <span className="text-emerald-700 dark:text-emerald-400">
                      {isAr ? "صافي الربح الحلال المصفى:" : "Net Halal Cleansed Dividend:"}
                    </span>
                    <span className="font-mono text-base font-black text-emerald-600 dark:text-emerald-400">
                      {netHalalDividend.toLocaleString("en-US", { minimumFractionDigits: 2 })} {isAr ? "ج.م" : "EGP"}
                    </span>
                  </div>
                </div>
              </>
            ) : (
              /* Zakat Mode */
              <>
                <div className="p-4 rounded-2xl bg-indigo-50 dark:bg-indigo-950/30 border-2 border-indigo-300 dark:border-indigo-800 space-y-3 pt-4">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-zinc-600 dark:text-zinc-400 font-bold">
                      {isAr ? "إجمالي القيمة السوقية للأسهم:" : "Total Market Value of Shares:"}
                    </span>
                    <span className="font-mono font-black text-sm text-zinc-900 dark:text-white">
                      {totalMarketValue.toLocaleString("en-US", { minimumFractionDigits: 2 })} {isAr ? "ج.م" : "EGP"}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-sm font-black border-t border-indigo-200 dark:border-indigo-800/80 pt-2">
                    <span className="text-indigo-700 dark:text-indigo-400 flex items-center gap-1.5">
                      <Coins className="w-4 h-4" />
                      <span>{isAr ? "مقدار زكاة عروض التجارة والمضاربة (2.5%):" : "Zakat Due on Speculation (2.5%):"}</span>
                    </span>
                    <span className="font-mono text-xl text-indigo-600 dark:text-indigo-400">
                      {zakatAmount.toLocaleString("en-US", { minimumFractionDigits: 2 })} {isAr ? "ج.م" : "EGP"}
                    </span>
                  </div>

                  <div className="text-[11px] text-zinc-500 dark:text-zinc-400 leading-relaxed border-t border-indigo-200 dark:border-indigo-800/80 pt-2">
                    {isAr
                      ? "💡 تجب زكاة الأسهم بنسبة 2.5% على القيمة السوقية إذا كانت نية الشراء هي المتاجرة والمضاربة وحال عليها الحول وبلغت النصاب الشرعي."
                      : "💡 2.5% Zakat applies to market value if purchased for trading/speculation and held for one lunar year reaching Nisab."}
                  </div>
                </div>
              </>
            )}
          </div>
        </section>

        {/* Right Column: Search Results & Approved EGX33 Sharia Stocks List */}
        <section className="lg:col-span-7 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-500" />
              <h2 className="text-lg sm:text-xl font-black text-zinc-950 dark:text-white">
                {isAr
                  ? `قائمة الأسهم المعتمدة والمطابقة للبحث (${filteredStocks.length})`
                  : `Approved Sharia & Searched Stocks (${filteredStocks.length})`}
              </h2>
            </div>
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {isAr ? "اضغط على أي سهم لنقله فوراً للحاسبة" : "Click any stock to load into calculator"}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {filteredStocks.map((stock) => {
              const isSelected = selectedSymbol === stock.symbol;
              const meta = getStockPurificationMeta(stock.symbol);
              const rate = meta ? meta.purificationRatePct : getDefaultPurificationRate(stock.sectorAr);
              return (
                <div
                  key={stock.symbol}
                  onClick={() => onSelectStock(stock.symbol)}
                  className={`p-4 rounded-2xl border-2 transition-all cursor-pointer space-y-2 ${
                    isSelected
                      ? "bg-emerald-50 dark:bg-emerald-950/40 border-emerald-500 shadow-sm"
                      : "bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800 hover:border-emerald-400 dark:hover:border-emerald-600"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono font-black text-sm text-zinc-950 dark:text-white">
                          {stock.symbol}
                        </span>
                        {stock.isSharia ? (
                          <span className="px-1.5 py-0.5 rounded-md bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 text-[10px] font-bold">
                            {isAr ? "متوافق شرعاً" : "Sharia Compliant"}
                          </span>
                        ) : (
                          <span className="px-1.5 py-0.5 rounded-md bg-zinc-200 dark:bg-zinc-700 text-zinc-600 dark:text-zinc-300 text-[10px] font-bold">
                            {isAr ? "سوق عام" : "Main Market"}
                          </span>
                        )}
                      </div>
                      <div className="text-xs font-bold text-zinc-800 dark:text-zinc-200 mt-1">
                        {isAr ? stock.nameAr : stock.nameEn || stock.nameAr}
                      </div>
                      <div className="text-[11px] text-zinc-500 dark:text-zinc-400">
                        {stock.sectorAr}
                      </div>
                    </div>

                    <div className="text-end shrink-0">
                      <div className="font-mono font-black text-sm text-zinc-950 dark:text-white">
                        {stock.currentPrice > 0 ? `${stock.currentPrice.toFixed(2)} ج.م` : "—"}
                      </div>
                      {stock.fairValue > 0 && (
                        <div className="text-[10px] font-mono text-emerald-600 dark:text-emerald-400 font-bold">
                          {isAr ? "العادل:" : "Fair:"} {stock.fairValue.toFixed(2)} ج.م
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="pt-2 border-t border-zinc-100 dark:border-zinc-800 flex items-center justify-between text-[11px]">
                    <span className="text-zinc-500 dark:text-zinc-400">
                      {isAr ? "نسبة التطهير:" : "Purification:"}
                    </span>
                    <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                      {meta?.isPureHalal ? (
                        <span className="text-emerald-600 dark:text-emerald-400 font-black">
                          0.0% ({isAr ? "نقي 100% ✅" : "Pure Halal ✅"})
                        </span>
                      ) : meta ? (
                        <span>%{rate} ({isAr ? "مدقق" : "Audited"})</span>
                      ) : (
                        <span>%{rate} ({isAr ? "تقديري" : "Est."})</span>
                      )}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {filteredStocks.length === 0 && (
            <div className="py-12 text-center rounded-3xl border-2 border-dashed border-zinc-300 dark:border-zinc-700 p-8 space-y-2">
              <ShieldCheck className="w-8 h-8 text-zinc-400 mx-auto" />
              <div className="text-sm font-bold text-zinc-700 dark:text-zinc-300">
                {isAr ? "لم نجد سهماً مطابقاً لكلمة البحث" : "No stocks matched your search query"}
              </div>
              <button
                type="button"
                onClick={() => setSearch("")}
                className="text-xs font-bold text-emerald-600 dark:text-emerald-400 hover:underline cursor-pointer"
              >
                {isAr ? "إظهار كافة أسهم الشريعة" : "Show all Sharia stocks"}
              </button>
            </div>
          )}
        </section>
      </main>

      {/* 📚 Educational & Transparency Methodology Guide (دليل معايير التطهير والشفافية) */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-12">
        <div className="bg-white dark:bg-zinc-900 border-2 border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 sm:p-8 shadow-sm space-y-6">
          <div className="flex items-center gap-3 border-b-2 border-zinc-100 dark:border-zinc-800 pb-4">
            <BookOpen className="w-6 h-6 text-emerald-500 shrink-0" />
            <div>
              <h2 className="text-lg sm:text-2xl font-black text-zinc-950 dark:text-white">
                {isAr
                  ? "دليل الشفافية الشرعية: لماذا تختلف نسب التطهير بين المنصات والمواقع؟"
                  : "Transparency Guide: Why Do Purification Rates Differ Across Platforms?"}
              </h2>
              <p className="text-xs sm:text-sm text-zinc-500 dark:text-zinc-400">
                {isAr
                  ? "توضيح الفوارق الفقهية والمحاسبية بين المعيار 21 للأيوفي والمنهجيات الأخرى في البورصة المصرية"
                  : "Clarification of accounting and Sharia differences between AAOIFI 21 and other methodologies"}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <div className="p-4 sm:p-5 rounded-2xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/80 space-y-2.5">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 text-xs font-bold">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>{isAr ? "1. تطهير الكوبون فقط (الأيوفي 21)" : "1. Dividend Only (AAOIFI 21)"}</span>
              </div>
              <p className="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed">
                {isAr
                  ? "وفق المعيار الشرعي رقم 21 للأيوفي، يُخرج التطهير كنسبة مئوية من الكوبونات النقدية الموزعة فقط. أرباح المضاربة الرأسمالية اليومية (فارق سعر البيع والشراء) لا تطهير فيها لأنها ناتجة عن قوى العرض والطلب السوقية."
                  : "Under AAOIFI 21, purification applies strictly to distributed cash dividends. Capital gains from market trading do not require purification as price movements reflect supply and demand."}
              </p>
            </div>

            <div className="p-4 sm:p-5 rounded-2xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/80 space-y-2.5">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-500/10 text-blue-700 dark:text-blue-400 text-xs font-bold">
                <Scale className="w-3.5 h-3.5" />
                <span>{isAr ? "2. نسب مدققة لكل شركة على حدة" : "2. Audited Per-Company Ratios"}</span>
              </div>
              <p className="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed">
                {isAr
                  ? "كل شركة تختلف نسبة الفوائد الدائنة في قوائمها المالية (مثلاً أبو قير 0.9%، موبكو 0.4%، السويدي 1.2%، طلعت مصطفى 3.2%). أما البنوك الإسلامية النقية (بنك فيصل ومصرف أبوظبي الإسلامي) فنصيبها 0.0% ولا تتطلب أي تطهير."
                  : "Each company has distinct incidental interest income in its financial statements (e.g. ABUK 0.9%, MFPC 0.4%, SWDY 1.2%, TMGH 3.2%). Pure Islamic banks (FAIT, ADIB) are 0.0% pure with zero cleansing."}
              </p>
            </div>

            <div className="p-4 sm:p-5 rounded-2xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/80 space-y-2.5">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 text-amber-700 dark:text-amber-400 text-xs font-bold">
                <Coins className="w-3.5 h-3.5" />
                <span>{isAr ? "3. الفارق بين الزكاة والتطهير" : "3. Zakat vs Purification"}</span>
              </div>
              <p className="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed">
                {isAr
                  ? "التطهير هو تخلص من كسب عارض بإنفاقه في وجوه الخير تبرؤاً منه، ولا يحتسب صدقة للمستثمر. أما الزكاة (2.5%) فهي فريضة شرعية سنوية على القيمة السوقية لمحفظة المضارب إذا حال عليها الحول وبلغت النصاب."
                  : "Purification is relinquishing incidental interest to charitable public benefit without expecting personal reward. Zakat (2.5%) is a religious obligation on speculation portfolio value after one lunar year."}
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
