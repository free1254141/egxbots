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
} from "lucide-react";
import { SHARIA_COMPLIANT_EGX_SYMBOLS } from "@/lib/shariaStocks";
import { CANONICAL_STOCK_NAMES } from "@/lib/ai/stock-names";
import type { FairValueReport, FairValueStockItem } from "@/lib/market/fair-value";

// Sector-estimated purification ratios (% of dividend/income from non-operating interest/treasury bills)
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

export default function ShariaCleanserClient({
  initialReport = null,
}: {
  initialReport?: FairValueReport | null;
}) {
  const [report, setReport] = useState<FairValueReport | null>(initialReport);
  const [loading, setLoading] = useState(!initialReport);
  const [search, setSearch] = useState("");

  // Calculator State
  const [selectedSymbol, setSelectedSymbol] = useState<string>("ABUK");
  const [sharesCount, setSharesCount] = useState<string>("1000");
  const [couponPerShare, setCouponPerShare] = useState<string>("5.00");
  const [purificationRate, setPurificationRate] = useState<string>("2.4");
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
        // Fallback to static list if API fails
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [initialReport]);

  const shariaStocks = useMemo<FairValueStockItem[]>(() => {
    if (report?.stocks?.length) {
      return report.stocks.filter((s) => s.isSharia);
    }
    return SHARIA_COMPLIANT_EGX_SYMBOLS.map((sym) => {
      const info = CANONICAL_STOCK_NAMES[sym];
      return {
        symbol: sym,
        nameAr: info?.name_ar || sym,
        nameEn: info?.name_en || sym,
        sectorAr: info?.sector || "مؤشر الشريعة EGX33",
        logoUrl: null,
        currentPrice: 0,
        changePct: null,
        fairValue: 0,
        grahamValue: null,
        upsidePct: 0,
        status: "fair",
        modelType: "quant_vwap",
        modelLabelAr: "مؤشر الشريعة",
        formulaEquationAr: "",
        formulaSubstitutionAr: "",
        formulaStepsAr: [],
        eps: null,
        bvps: null,
        peRatio: null,
        pbRatio: null,
        sectorMedianPe: 9,
        sectorMedianPb: 1.7,
        dividendYield: null,
        roe: null,
        marketCap: null,
        rsi14: null,
        ema200: null,
        vwap20: null,
        isSharia: true,
        date: null,
      };
    });
  }, [report]);

  // Update default coupon & purification rate when user picks a stock
  const selectedStockObj = useMemo(
    () => shariaStocks.find((s) => s.symbol === selectedSymbol) || null,
    [shariaStocks, selectedSymbol]
  );

  const handleSelectStock = (sym: string) => {
    setSelectedSymbol(sym);
    const st = shariaStocks.find((s) => s.symbol === sym);
    if (st) {
      const rate = getDefaultPurificationRate(st.sectorAr);
      setPurificationRate(String(rate));
      if (st.currentPrice > 0 && st.dividendYield && st.dividendYield > 0) {
        const estCoupon = (st.currentPrice * (st.dividendYield / 100)).toFixed(2);
        setCouponPerShare(estCoupon);
      }
    }
  };

  const filteredShariaStocks = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return shariaStocks;
    return shariaStocks.filter(
      (s) =>
        s.symbol.toLowerCase().includes(q) ||
        s.nameAr.toLowerCase().includes(q) ||
        s.nameEn.toLowerCase().includes(q) ||
        s.sectorAr.toLowerCase().includes(q)
    );
  }, [shariaStocks, search]);

  // Calculations
  const numShares = Math.max(0, Number(sharesCount) || 0);
  const numCoupon = Math.max(0, Number(couponPerShare) || 0);
  const numRate = Math.max(0, Math.min(100, Number(purificationRate) || 0));

  const totalDividends = numShares * numCoupon;
  const purificationAmount = totalDividends * (numRate / 100);
  const netHalalDividend = Math.max(0, totalDividends - purificationAmount);

  const stockPrice = selectedStockObj?.currentPrice || 0;
  const totalPositionValue = numShares * stockPrice;
  const zakatAmount = totalPositionValue * 0.025; // 2.5%

  return (
    <div dir="rtl" className="min-h-screen bg-zinc-950 text-zinc-100 pb-20">
      {/* Hero Banner */}
      <section className="border-b-2 border-zinc-800 bg-gradient-to-b from-emerald-950/35 via-zinc-950 to-zinc-950 pt-10 pb-10 px-4">
        <div className="max-w-7xl mx-auto">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-black mb-4">
            <Scale className="w-4 h-4" />
            <span>أداة مجانية · قائمة مؤشر الشريعة EGX33 وحاسبة تطهير الكوبونات والزكاة</span>
          </div>

          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6">
            <div>
              <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-white">
                ⚖️ حاسبة التوافق الشرعي وتطهير الكوبونات{" "}
                <span className="text-emerald-400">(Sharia Cleanser)</span>
              </h1>
              <p className="mt-3 text-sm sm:text-base text-zinc-400 max-w-3xl leading-relaxed">
                دليلك المتكامل للأسهم المتوافقة مع معايير الشريعة الإسلامية في البورصة المصرية،
                مع حاسبة فورية لحساب <strong className="text-zinc-200">مبلغ تطهير التوزيعات النقدية (الكوبونات)</strong>{" "}
                من عوائد أذون الخزانة والفوائد العرضية، وحاسبة زكاة الأسهم (2.5%).
              </p>
            </div>

            <Link
              href="/fair-value"
              className="shrink-0 inline-flex items-center gap-2 px-4 py-3 rounded-xl bg-zinc-900 hover:bg-zinc-800 border-2 border-emerald-500/40 text-emerald-400 text-xs sm:text-sm font-black transition-colors"
            >
              <Gem className="w-4 h-4" />
              <span>تصفح محدد السعر العادل ومؤشر الرخص ←</span>
            </Link>
          </div>
        </div>
      </section>

      <div className="max-w-7xl mx-auto px-4 mt-8 grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Right Column: Interactive Calculator (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="bg-zinc-900/90 border-2 border-emerald-500/40 rounded-2xl p-6 shadow-[0_0_30px_rgba(16,185,129,0.08)]">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2">
                <Calculator className="w-5 h-5 text-emerald-400" />
                <h2 className="text-lg font-black text-white">الحاسبة الشرعية الفورية</h2>
              </div>
              <div className="flex rounded-xl bg-zinc-950 p-1 border border-zinc-800 text-xs font-bold">
                <button
                  onClick={() => setCalcMode("dividend")}
                  className={`px-3 py-1.5 rounded-lg cursor-pointer transition-colors ${
                    calcMode === "dividend"
                      ? "bg-emerald-500 text-zinc-950 font-black"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  تطهير الكوبون
                </button>
                <button
                  onClick={() => setCalcMode("zakat")}
                  className={`px-3 py-1.5 rounded-lg cursor-pointer transition-colors ${
                    calcMode === "zakat"
                      ? "bg-emerald-500 text-zinc-950 font-black"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  زكاة الأسهم
                </button>
              </div>
            </div>

            <div className="space-y-4">
              {/* Select Stock */}
              <div>
                <label className="block text-xs font-bold text-zinc-300 mb-1.5">
                  1. اختر السهم من قائمة الشريعة ({shariaStocks.length} سهماً):
                </label>
                <select
                  value={selectedSymbol}
                  onChange={(e) => handleSelectStock(e.target.value)}
                  className="w-full bg-zinc-950 border-2 border-zinc-800 focus:border-emerald-500 rounded-xl px-3.5 py-2.5 text-sm font-bold text-white outline-none"
                >
                  {shariaStocks.map((s) => (
                    <option key={s.symbol} value={s.symbol}>
                      {s.symbol} — {s.nameAr} {s.currentPrice > 0 ? `(${s.currentPrice} ج.م)` : ""}
                    </option>
                  ))}
                </select>
              </div>

              {/* Number of Shares */}
              <div>
                <label className="block text-xs font-bold text-zinc-300 mb-1.5">
                  2. عدد الأسهم التي تمتلكها في محفظتك:
                </label>
                <input
                  type="number"
                  min="1"
                  value={sharesCount}
                  onChange={(e) => setSharesCount(e.target.value)}
                  className="w-full bg-zinc-950 border-2 border-zinc-800 focus:border-emerald-500 rounded-xl px-3.5 py-2.5 text-sm font-black text-white outline-none"
                  placeholder="مثال: 1000"
                />
              </div>

              {calcMode === "dividend" ? (
                <>
                  {/* Coupon Value */}
                  <div>
                    <label className="block text-xs font-bold text-zinc-300 mb-1.5">
                      3. قيمة الكوبون النقدي الموزع لكل سهم (بالجنيه):
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={couponPerShare}
                      onChange={(e) => setCouponPerShare(e.target.value)}
                      className="w-full bg-zinc-950 border-2 border-zinc-800 focus:border-emerald-500 rounded-xl px-3.5 py-2.5 text-sm font-black text-white outline-none"
                      placeholder="مثال: 5.00"
                    />
                  </div>

                  {/* Purification Ratio */}
                  <div>
                    <div className="flex items-center justify-between text-xs font-bold text-zinc-300 mb-1.5">
                      <span>4. نسبة التطهير المقدرة للدخل غير التشغيلي (%):</span>
                      <span className="text-emerald-400 font-black">{purificationRate}%</span>
                    </div>
                    <input
                      type="range"
                      min="0.5"
                      max="8.0"
                      step="0.1"
                      value={purificationRate}
                      onChange={(e) => setPurificationRate(e.target.value)}
                      className="w-full accent-emerald-500 cursor-pointer"
                    />
                    <div className="flex justify-between text-[11px] text-zinc-500 mt-1">
                      <span>0.5% (نقي جداً)</span>
                      <span>2.5% (متوسط معياري)</span>
                      <span>5%+ (سيولة بنكية عالية)</span>
                    </div>
                  </div>

                  {/* Output Card */}
                  <div className="mt-6 bg-zinc-950 border-2 border-emerald-500/40 rounded-2xl p-4 space-y-3">
                    <div className="flex items-center justify-between text-xs text-zinc-400">
                      <span>إجمالي الكوبون المستلم:</span>
                      <span className="font-bold text-zinc-200">
                        {totalDividends.toLocaleString("en-US", { maximumFractionDigits: 2 })} ج.م
                      </span>
                    </div>

                    <div className="flex items-center justify-between border-t border-zinc-800 pt-3">
                      <div className="flex items-center gap-1.5 text-rose-400 font-black text-sm">
                        <HeartHandshake className="w-4 h-4" />
                        <span>مبلغ التطهير الواجب إخراجه:</span>
                      </div>
                      <span className="text-xl font-black text-rose-400">
                        {purificationAmount.toLocaleString("en-US", {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}{" "}
                        ج.م
                      </span>
                    </div>

                    <div className="flex items-center justify-between border-t border-zinc-800 pt-3">
                      <span className="text-xs font-bold text-emerald-400">صافي الربح الحلال المصفّى:</span>
                      <span className="text-base font-black text-emerald-400">
                        {netHalalDividend.toLocaleString("en-US", {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}{" "}
                        ج.م
                      </span>
                    </div>
                  </div>
                </>
              ) : (
                <div className="mt-6 bg-zinc-950 border-2 border-emerald-500/40 rounded-2xl p-4 space-y-3">
                  <div className="flex items-center justify-between text-xs text-zinc-400">
                    <span>سعر السهم السوقي الحالي:</span>
                    <span className="font-bold text-zinc-200">{stockPrice} ج.م</span>
                  </div>
                  <div className="flex items-center justify-between text-xs text-zinc-400">
                    <span>إجمالي القيمة السوقية لمركزك:</span>
                    <span className="font-bold text-zinc-200">
                      {totalPositionValue.toLocaleString("en-US", { maximumFractionDigits: 2 })} ج.م
                    </span>
                  </div>
                  <div className="flex items-center justify-between border-t border-zinc-800 pt-3">
                    <div className="flex items-center gap-1.5 text-emerald-400 font-black text-sm">
                      <Coins className="w-4 h-4" />
                      <span>مقدار الزكاة السنوية (2.5%):</span>
                    </div>
                    <span className="text-xl font-black text-emerald-400">
                      {zakatAmount.toLocaleString("en-US", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}{" "}
                      ج.م
                    </span>
                  </div>
                </div>
              )}

              <p className="text-[11px] text-zinc-500 leading-relaxed pt-1">
                * ملاحظة شرعية: مبلغ التطهير يُخرج في مصارف البر العامة والفقراء بنية التخلص من الفوائد البنكية العرضية للشركة، ولا يُحتسب من أموال الزكاة المفروضة.
              </p>
            </div>
          </div>
        </div>

        {/* Left Column: Searchable Sharia Directory (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <div className="bg-zinc-900/80 border-2 border-zinc-800 rounded-2xl p-4 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-black text-white flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-400" />
                <span>قائمة أسهم الشريعة المعتمدة في البورصة المصرية ({filteredShariaStocks.length})</span>
              </h2>
              <p className="text-xs text-zinc-400 mt-0.5">
                اضغط على أي سهم لنقله فوراً إلى الحاسبة أو لعرض السعر العادل
              </p>
            </div>

            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 text-zinc-400 absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="ابحث عن سهم شرعي..."
                className="w-full bg-zinc-950 border-2 border-zinc-800 focus:border-emerald-500 rounded-xl pr-9 pl-3 py-2 text-xs text-white outline-none"
              />
            </div>
          </div>

          {loading ? (
            <div className="space-y-2.5">
              {Array.from({ length: 8 }).map((_, idx) => (
                <div key={idx} className="h-16 bg-zinc-900/50 border border-zinc-800 rounded-xl animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {filteredShariaStocks.map((st) => {
                const isSelected = st.symbol === selectedSymbol;
                const estPurif = getDefaultPurificationRate(st.sectorAr);
                return (
                  <div
                    key={st.symbol}
                    onClick={() => handleSelectStock(st.symbol)}
                    className={`p-4 rounded-xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
                      isSelected
                        ? "bg-emerald-950/30 border-emerald-500 shadow-[0_0_20px_rgba(16,185,129,0.15)]"
                        : "bg-zinc-900/70 border-zinc-800 hover:border-zinc-700"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-base font-black text-white">{st.symbol}</span>
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-black bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                            <CheckCircle2 className="w-3 h-3" />
                            متوافق شرعياً
                          </span>
                        </div>
                        <div className="text-xs font-bold text-zinc-300 mt-0.5">{st.nameAr}</div>
                        <div className="text-[11px] text-zinc-500 mt-0.5">{st.sectorAr}</div>
                      </div>

                      {st.currentPrice > 0 && (
                        <div className="text-left">
                          <div className="text-sm font-black text-white">{st.currentPrice} ج.م</div>
                          {st.fairValue > 0 && (
                            <div
                              className={`text-[11px] font-bold ${
                                st.upsidePct >= 15
                                  ? "text-emerald-400"
                                  : st.upsidePct <= -12
                                  ? "text-rose-400"
                                  : "text-amber-300"
                              }`}
                            >
                              العادل: {st.fairValue} ج.م
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-zinc-800/80 text-[11px]">
                      <span className="text-zinc-400">
                        نسبة التطهير المقدرة: <strong className="text-emerald-400">{estPurif}%</strong>
                      </span>

                      <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                        <Link
                          href={`/chat?q=${encodeURIComponent(`هل سهم ${st.symbol} متوافق مع الشريعة وما هي توصيته الفنية اليوم؟`)}`}
                          className="text-emerald-400 hover:text-emerald-300 font-bold inline-flex items-center gap-1"
                        >
                          <Sparkles className="w-3 h-3" />
                          <span>اسأل الشات</span>
                        </Link>
                        <Link
                          href={`/stocks/${st.symbol}`}
                          className="text-zinc-400 hover:text-white inline-flex items-center"
                        >
                          <ArrowUpRight className="w-3.5 h-3.5" />
                        </Link>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
