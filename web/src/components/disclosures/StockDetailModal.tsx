"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import {
  X,
  TrendingUp,
  TrendingDown,
  Target,
  Users,
  FileText,
  Bot,
  ExternalLink,
  ShieldCheck,
  Percent,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Sparkles,
  Brain,
  BarChart3,
  Calendar,
} from "lucide-react";
import StockLogo from "@/components/StockLogo";
import {
  InsiderMetric,
  CompanyOwnershipStructure,
  getSymbolSector,
  DisclosureItem,
} from "@/lib/disclosures-analytics";
// DisclosureItem imported from disclosures-analytics

interface StockDetailModalProps {
  symbol: string | null;
  isOpen: boolean;
  onClose: () => void;
  metric?: InsiderMetric;
  ownership?: CompanyOwnershipStructure;
  disclosures: DisclosureItem[];
  isAr: boolean;
  onOpenPdfModal?: (item: DisclosureItem) => void;
  onDiscussInChat?: (symbol: string, companyName: string) => void;
  onFilterBySymbol?: (symbol: string) => void;
}

export default function StockDetailModal({
  symbol,
  isOpen,
  onClose,
  metric,
  ownership,
  disclosures,
  isAr,
  onOpenPdfModal,
  onDiscussInChat,
  onFilterBySymbol,
}: StockDetailModalProps) {
  // ESC key listener
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !symbol) return null;

  const upperSym = symbol.toUpperCase();
  const sector = metric?.sector || getSymbolSector(upperSym);

  // Filter disclosures for this specific symbol
  const stockDisclosures = disclosures.filter(
    (d) => d.symbol && d.symbol.toUpperCase() === upperSym
  );

  const companyName =
    metric?.company_name ||
    ownership?.company_name ||
    (stockDisclosures.length > 0 ? stockDisclosures[0].company_name : upperSym);

  const currentPrice = metric?.current_price || 0;
  const changePct = metric?.change_pct || 0;
  const vwap = metric?.insider_vwap || 0;
  const discountPct = metric?.discount_pct || 0;
  const isBelowCost = discountPct < -1.0 && vwap > 0;

  const totalBuyShares = metric?.total_buy_shares || 0;
  const totalSellShares = metric?.total_sell_shares || 0;
  const totalShares = totalBuyShares + totalSellShares;
  const buyRatio = totalShares > 0 ? (totalBuyShares / totalShares) * 100 : 50;
  const sellRatio = totalShares > 0 ? (totalSellShares / totalShares) * 100 : 50;

  const formatEgp = (val: number) => {
    const abs = Math.abs(val);
    if (abs >= 1_000_000) {
      return `${(val / 1_000_000).toFixed(1)} ${isAr ? "مليون ج.م" : "M EGP"}`;
    }
    if (abs >= 1_000) {
      return `${(val / 1_000).toFixed(0)} ${isAr ? "ألف ج.م" : "k EGP"}`;
    }
    return `${val.toFixed(0)} ${isAr ? "ج.م" : "EGP"}`;
  };

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center p-3 sm:p-5 bg-black/75 backdrop-blur-sm overflow-y-auto"
      onClick={onClose}
      dir={isAr ? "rtl" : "ltr"}
    >
      <div
        className="relative w-full max-w-4xl max-h-[92vh] overflow-y-auto bg-white dark:bg-zinc-950 text-black dark:text-white border-4 border-black dark:border-white shadow-[10px_10px_0px_#000] dark:shadow-[10px_10px_0px_#fff] p-5 sm:p-7 transition-colors my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 ltr:right-4 rtl:left-4 sm:top-5 sm:ltr:right-5 sm:rtl:left-5 grid h-9 w-9 place-items-center bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white hover:bg-[#FF3366] hover:text-white transition-colors cursor-pointer z-10"
          aria-label={isAr ? "إغلاق" : "Close"}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header: Identity, Logo, Price, Sector */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b-4 border-black dark:border-white pb-5 mb-6">
          <div className="flex items-center gap-4">
            <StockLogo symbol={upperSym} size="lg" />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-black text-2xl sm:text-3xl tracking-tight text-black dark:text-white">
                  {upperSym}
                </span>
                <span className="px-2.5 py-0.5 text-xs font-black uppercase tracking-wider bg-[#FFE600] text-black border-2 border-black shadow-[2px_2px_0px_#000]">
                  {isAr ? sector.ar : sector.en}
                </span>
                {ownership?.free_float_pct != null && (
                  <span className="px-2.5 py-0.5 text-xs font-black bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 border-2 border-black dark:border-white/20">
                    {isAr
                      ? `تداول حر: ${ownership.free_float_pct}%`
                      : `Free Float: ${ownership.free_float_pct}%`}
                  </span>
                )}
              </div>
              <h2 className="text-base sm:text-lg font-bold text-zinc-700 dark:text-zinc-300 mt-1">
                {companyName}
              </h2>
            </div>
          </div>

          {/* Current Market Price & Daily Change */}
          <div className="flex items-center gap-3 sm:text-right rtl:sm:text-right pe-12 sm:pe-14">
            <div>
              <span className="text-[11px] font-black uppercase text-zinc-500 block">
                {isAr ? "سعر السوق الحالي" : "Current Market Price"}
              </span>
              <div className="flex items-center gap-2">
                <span className="text-2xl sm:text-3xl font-black text-black dark:text-white">
                  {currentPrice > 0 ? `${currentPrice.toFixed(2)} ج.م` : "—"}
                </span>
                {changePct !== 0 && (
                  <span
                    className={`inline-flex items-center gap-0.5 px-2 py-0.5 text-xs font-black border-2 border-black ${
                      changePct >= 0
                        ? "bg-[#00FF66] text-black shadow-[2px_2px_0px_#000]"
                        : "bg-[#FF3366] text-white shadow-[2px_2px_0px_#000]"
                    }`}
                  >
                    {changePct >= 0 ? (
                      <TrendingUp className="w-3.5 h-3.5" />
                    ) : (
                      <TrendingDown className="w-3.5 h-3.5" />
                    )}
                    <span>
                      {changePct >= 0 ? "+" : ""}
                      {changePct.toFixed(2)}%
                    </span>
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Opportunity Banner if stock is below insider cost */}
        {isBelowCost && (
          <div className="mb-6 p-4 border-4 border-black bg-[#FFE600] text-black shadow-[4px_4px_0px_#000] flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <Sparkles className="w-6 h-6 text-black shrink-0 animate-pulse" />
              <div>
                <span className="font-black text-sm block">
                  {isAr
                    ? `فرصة ذهبية: السهم يتداول بأقل من تكلفة شراء الداخليين بـ ${Math.abs(discountPct).toFixed(1)}%`
                    : `Golden Opportunity: Trading ${Math.abs(discountPct).toFixed(1)}% below insider purchase cost`}
                </span>
                <span className="text-xs font-bold text-black/80">
                  {isAr
                    ? `متوسط تكلفة شراء مجالس الإدارة والداخليين في هذا السهم هو ${vwap.toFixed(2)} ج.م، بينما يتداول الآن بـ ${currentPrice.toFixed(2)} ج.م.`
                    : `Insiders bought at an average VWAP of ${vwap.toFixed(2)} EGP vs current ${currentPrice.toFixed(2)} EGP.`}
                </span>
              </div>
            </div>
            <span className="shrink-0 px-3 py-1 bg-black text-[#FFE600] font-black text-xs uppercase border border-black shadow-[2px_2px_0px_#000]">
              {isAr ? "خصم استثنائي" : "DISCOUNT"}
            </span>
          </div>
        )}

        {/* Section 1: Smart Money & Insider Analytics KPIs */}
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <Target className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
            <h3 className="text-sm sm:text-base font-black text-black dark:text-white uppercase tracking-wider">
              {isAr
                ? "تحليل تكلفة صانع السهم وتدفق سيولة الداخليين"
                : "Insider VWAP Cost & Smart Money Liquidity"}
            </h3>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {/* KPI 1: Insider VWAP */}
            <div className="p-3.5 border-3 border-black dark:border-white/30 bg-zinc-50 dark:bg-zinc-900 shadow-[3px_3px_0px_#000]">
              <span className="text-[11px] font-black text-zinc-600 dark:text-zinc-400 block mb-1">
                {isAr ? "متوسط تكلفة الداخلي (VWAP)" : "Insider VWAP Cost"}
              </span>
              <div className="text-lg sm:text-xl font-black text-black dark:text-white">
                {totalBuyShares > 0 && vwap > 0 ? `${vwap.toFixed(2)} ج.م` : "—"}
              </div>
              <span className="text-[10px] font-bold text-zinc-500">
                {totalBuyShares > 0
                  ? (isAr ? "محسوب بالكميات المنفذة" : "Weighted by volume")
                  : (isAr ? "لا توجد مشتريات (بيع فقط)" : "No buy transactions")}
              </span>
            </div>

            {/* KPI 2: Price vs Insider Cost Discount */}
            <div
              className={`p-3.5 border-3 border-black dark:border-white/30 shadow-[3px_3px_0px_#000] ${
                isBelowCost && totalBuyShares > 0
                  ? "bg-amber-300 dark:bg-amber-950/40 text-black dark:text-amber-200"
                  : "bg-zinc-50 dark:bg-zinc-900 text-black dark:text-white"
              }`}
            >
              <span className="text-[11px] font-black block mb-1">
                {isAr ? "الفارق عن تكلفة الداخلي" : "Discount vs Insider"}
              </span>
              <div className="text-lg sm:text-xl font-black">
                {totalBuyShares > 0 && vwap > 0 ? (
                  <span
                    className={
                      Math.abs(discountPct) < 0.1
                        ? "text-zinc-600 dark:text-zinc-400"
                        : discountPct < 0
                        ? "text-emerald-700 dark:text-emerald-400"
                        : "text-rose-700 dark:text-rose-400"
                    }
                  >
                    {Math.abs(discountPct) < 0.1
                      ? "0.0%"
                      : `${discountPct < 0 ? "-" : "+"}${Math.abs(discountPct).toFixed(1)}%`}
                  </span>
                ) : (
                  "—"
                )}
              </div>
              <span className="text-[10px] font-bold">
                {totalBuyShares === 0
                  ? isAr
                    ? "لا ينطبق (لا توجد مشتريات)"
                    : "N/A (No buy orders)"
                  : Math.abs(discountPct) < 0.1
                  ? isAr
                    ? "السعر متطابق مع تكلفة الداخلي"
                    : "At insider cost"
                  : discountPct < 0
                  ? isAr
                    ? "السهم أرخص من أصحابه"
                    : "Trading at discount"
                  : isAr
                  ? "يتداول بعلاوة سعرية"
                  : "Trading at premium"}
              </span>
            </div>

            {/* KPI 3: Net Insider Cash Flow */}
            <div className="p-3.5 border-3 border-black dark:border-white/30 bg-zinc-50 dark:bg-zinc-900 shadow-[3px_3px_0px_#000]">
              <span className="text-[11px] font-black text-zinc-600 dark:text-zinc-400 block mb-1">
                {isAr ? "صافي سيولة الداخليين" : "Net Insider Flow"}
              </span>
              <div
                className={`text-lg sm:text-xl font-black ${
                  (metric?.net_value_egp || 0) >= 0
                    ? "text-emerald-700 dark:text-[#00FF66]"
                    : "text-rose-700 dark:text-[#FF3366]"
                }`}
              >
                {metric ? formatEgp(metric.net_value_egp) : "—"}
              </div>
              <span className="text-[10px] font-bold text-zinc-500">
                {metric?.action_bias === "accumulating"
                  ? isAr
                    ? "تجميع شرائي نشط"
                    : "Accumulating"
                  : metric?.action_bias === "distributing"
                  ? isAr
                    ? "تسييل وتخارج"
                    : "Distributing"
                  : isAr
                  ? "محايد / توازن"
                  : "Neutral"}
              </span>
            </div>

            {/* KPI 4: Insider Streak */}
            <div className="p-3.5 border-3 border-black dark:border-white/30 bg-zinc-50 dark:bg-zinc-900 shadow-[3px_3px_0px_#000]">
              <span className="text-[11px] font-black text-zinc-600 dark:text-zinc-400 block mb-1">
                {isAr ? "سلسلة العمليات المتتالية" : "Action Streak"}
              </span>
              <div className="text-lg sm:text-xl font-black text-black dark:text-white">
                {metric?.streak ? (
                  metric.streak > 0 ? (
                    <span className="text-emerald-600 dark:text-emerald-400">
                      {isAr
                        ? `${metric.streak} شراء متتالي`
                        : `${metric.streak} Buys`}
                    </span>
                  ) : (
                    <span className="text-rose-600 dark:text-rose-400">
                      {isAr
                        ? `${Math.abs(metric.streak)} بيع متتالي`
                        : `${Math.abs(metric.streak)} Sells`}
                    </span>
                  )
                ) : (
                  "—"
                )}
              </div>
              <span className="text-[10px] font-bold text-zinc-500">
                {isAr ? "سلوك مجلس الإدارة" : "Board behavior"}
              </span>
            </div>
          </div>

          {/* Buy vs Sell Volume Ratio Meter */}
          {totalShares > 0 && (
            <div className="mt-4 p-3.5 border-2 border-black dark:border-white/20 bg-zinc-100 dark:bg-zinc-900">
              <div className="flex items-center justify-between text-xs font-black mb-2">
                <span className="text-emerald-700 dark:text-[#00FF66] flex items-center gap-1">
                  <TrendingUp className="w-3.5 h-3.5" />
                  {isAr
                    ? `شراء داخلي: ${buyRatio.toFixed(1)}% (${totalBuyShares.toLocaleString()} سهم)`
                    : `Buys: ${buyRatio.toFixed(1)}% (${totalBuyShares.toLocaleString()} shares)`}
                </span>
                <span className="text-rose-700 dark:text-[#FF3366] flex items-center gap-1">
                  <TrendingDown className="w-3.5 h-3.5" />
                  {isAr
                    ? `بيع داخلي: ${sellRatio.toFixed(1)}% (${totalSellShares.toLocaleString()} سهم)`
                    : `Sells: ${sellRatio.toFixed(1)}% (${totalSellShares.toLocaleString()} shares)`}
                </span>
              </div>
              <div className="w-full h-3 border-2 border-black dark:border-white/30 flex overflow-hidden">
                <div
                  className="bg-[#00FF66] transition-all"
                  style={{ width: `${buyRatio}%` }}
                />
                <div
                  className="bg-[#FF3366] transition-all"
                  style={{ width: `${sellRatio}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Section: AI Financial Analysis & Strategic Insight */}
        <div className="mb-6 p-4 sm:p-5 border-3 border-black dark:border-white/30 bg-gradient-to-br from-yellow-50 via-amber-50/40 to-orange-50 dark:from-yellow-950/20 dark:via-zinc-900 dark:to-zinc-900 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff]">
          <div className="flex items-center justify-between gap-3 mb-3 border-b-2 border-black/10 dark:border-white/10 pb-2.5">
            <div className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-amber-500 fill-amber-400" />
              <h3 className="text-sm sm:text-base font-black text-black dark:text-white uppercase tracking-wider">
                {isAr ? "تحليل الذكاء الاصطناعي والأثر المالي" : "AI Financial Analysis & Impact"}
              </h3>
            </div>
            <span className="px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider bg-black text-[#FFE600] dark:bg-[#FFE600] dark:text-black border border-black shadow-[1px_1px_0px_#000]">
              {isAr ? "تحليل فوري معتمد" : "AI Financial Agent"}
            </span>
          </div>

          <div className="space-y-3">
            {/* Contextual Executive AI Opinion */}
            <div className="p-3 bg-white/90 dark:bg-zinc-950/80 border-2 border-black dark:border-white/20 text-xs sm:text-sm font-bold text-zinc-900 dark:text-zinc-100 leading-relaxed shadow-[2px_2px_0px_#000]">
              <div className="flex items-center gap-2 mb-1.5 font-black text-black dark:text-white text-xs">
                <Brain className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                <span>{isAr ? "الرؤية الاستثمارية لسلوك صانع السهم:" : "Smart Money Behavioral View:"}</span>
              </div>
              <p>
                {metric?.action_bias === "accumulating"
                  ? isAr
                    ? `رصد النظام تجميعاً شرائياً نشطاً من الداخليين في سهم ${companyName}، بإجمالي صافي تدفق نقدي موجب قدره ${formatEgp(metric.net_value_egp)} عبر ${metric.buy_count} صفقات شراء. ${
                        isBelowCost && totalBuyShares > 0
                          ? `السهم يتداول حالياً بخصم استثنائي قدره ${Math.abs(discountPct).toFixed(1)}% دون متوسط تكلفة الداخليين (${vwap.toFixed(2)} ج.م)، مما يمنح المستثمر هامش أمان جذاب.`
                          : totalBuyShares > 0
                          ? `يتداول السهم بعلاوة سعرية قدرها ${discountPct.toFixed(1)}% فوق تكلفة شراء الداخليين.`
                          : ""
                      } هذا السلوك يعكس ثقة الإدارة في نمو الشركة.`
                    : `Active accumulation detected from insiders in ${companyName} with net flow of ${formatEgp(metric.net_value_egp)} across ${metric.buy_count} buys.`
                  : metric?.action_bias === "distributing"
                  ? isAr
                    ? `رصد النظام ضغوطاً بيعية وتصريفاً من المطلعين في سهم ${companyName}، بصافي تدفق سلبي قدره ${formatEgp(metric.net_value_egp)} عبر ${metric.sell_count} عمليات بيع متتالية. يُنصح بالحذر ومتابعة مستويات الدعم الفنية.`
                    : `Selling pressure detected from insiders in ${companyName} with net outflow of ${formatEgp(metric.net_value_egp)}.`
                  : isAr
                  ? `حركة الداخليين في سهم ${companyName} متوازنة حالياً دون انحياز واضح للتجميع أو التصريف.`
                  : `Insider flow in ${companyName} is currently neutral.`}
              </p>
            </div>

            {/* Official Filing AI Summary (if available) */}
            {stockDisclosures.some((d) => d.ai_summary) && (
              <div className="p-3 bg-amber-100/70 dark:bg-amber-950/30 border-2 border-dashed border-amber-500/60 dark:border-amber-400/40 text-xs text-zinc-800 dark:text-zinc-200 leading-relaxed">
                <span className="font-black text-amber-900 dark:text-amber-300 block mb-1">
                  {isAr ? "ملخص أحدث إفصاح رسمي معتمد:" : "Latest Official Filing AI Summary:"}
                </span>
                <p className="font-medium">
                  {stockDisclosures.find((d) => d.ai_summary)?.ai_summary}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Section 2: Article 30 Major Shareholders Structure */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Users className="w-5 h-5 text-amber-500" />
              <h3 className="text-sm sm:text-base font-black text-black dark:text-white uppercase tracking-wider">
                {isAr
                  ? "هيكل كبار المساهمين والمؤسسين (المادة 30)"
                  : "Major Shareholders & Ownership (Article 30)"}
              </h3>
            </div>
            {ownership?.free_float_pct != null && (
              <span className="px-3 py-1 text-xs font-black bg-[#FFE600] text-black border-2 border-black shadow-[2px_2px_0px_#000]">
                {isAr
                  ? `الأسهم الحرة للتداول: ${ownership.free_float_pct}%`
                  : `Free Float: ${ownership.free_float_pct}%`}
              </span>
            )}
          </div>

          {/* Free Float & Liquidity Structure Breakdown */}
          {ownership?.free_float_pct != null && (
            <div className="mb-4 p-4 border-2 border-black dark:border-white/30 bg-zinc-50 dark:bg-zinc-900/90 shadow-[3px_3px_0px_#000]">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3 border-b border-black/10 dark:border-white/10 pb-2">
                <span className="text-xs font-black text-black dark:text-white uppercase flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4 text-amber-500" />
                  {isAr ? "تحليل هيكل الأسهم الحرة ومعدل خفة السهم:" : "Free Float & Liquidity Analysis:"}
                </span>
                <span className="text-[11px] font-bold px-2 py-0.5 border border-black bg-white dark:bg-zinc-800">
                  {ownership.free_float_pct < 20
                    ? isAr ? "⚡ سهم خفيف مضاربياً (تداول حر محدود)" : "High Volatility / Low Float"
                    : ownership.free_float_pct > 50
                    ? isAr ? "🏛️ سهم مؤسسي ثقيل (سيولة واسعة)" : "Heavy Institutional Float"
                    : isAr ? "⚖️ تداول حر متوازن" : "Balanced Float"}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-center">
                <div className="p-2 border border-black dark:border-white/20 bg-white dark:bg-zinc-950">
                  <span className="text-[10px] text-zinc-500 font-bold block">{isAr ? "نسبة الأسهم الحرة" : "Free Float %"}</span>
                  <span className="text-sm sm:text-base font-black text-amber-600 dark:text-amber-400 font-mono">
                    {ownership.free_float_pct}%
                  </span>
                </div>

                <div className="p-2 border border-black dark:border-white/20 bg-white dark:bg-zinc-950">
                  <span className="text-[10px] text-zinc-500 font-bold block">{isAr ? "عدد الأسهم الحرة" : "Free Float Shares"}</span>
                  <span className="text-sm sm:text-base font-black text-black dark:text-white font-mono">
                    {ownership.free_float_shares ? (
                      ownership.free_float_shares >= 1_000_000
                        ? `${(ownership.free_float_shares / 1_000_000).toFixed(1)} ${isAr ? "مليون" : "M"}`
                        : `${(ownership.free_float_shares / 1_000).toFixed(0)} ${isAr ? "ألف" : "k"}`
                    ) : "—"}
                  </span>
                </div>

                <div className="p-2 border border-black dark:border-white/20 bg-white dark:bg-zinc-950">
                  <span className="text-[10px] text-zinc-500 font-bold block">{isAr ? "القيمة السوقية الحرة" : "Float Market Cap"}</span>
                  <span className="text-sm sm:text-base font-black text-emerald-700 dark:text-[#00FF66] font-mono">
                    {ownership.free_float_market_cap_egp ? formatEgp(ownership.free_float_market_cap_egp) : "—"}
                  </span>
                </div>

                <div className="p-2 border border-black dark:border-white/20 bg-white dark:bg-zinc-950">
                  <span className="text-[10px] text-zinc-500 font-bold block">{isAr ? "الأسهم المجمدة للمؤسسين" : "Strategic Locked"}</span>
                  <span className="text-sm sm:text-base font-black text-purple-700 dark:text-purple-400 font-mono">
                    {ownership.locked_pct ? `${ownership.locked_pct}%` : `${(100 - ownership.free_float_pct).toFixed(1)}%`}
                  </span>
                </div>
              </div>
            </div>
          )}

          {ownership && ownership.shareholders.length > 0 ? (
            <div className="border-3 border-black dark:border-white/20 overflow-x-auto">
              <table className="w-full text-xs text-right border-collapse">
                <thead className="bg-black text-white dark:bg-white dark:text-black font-black uppercase text-[11px]">
                  <tr>
                    <th className="p-2.5">{isAr ? "اسم المساهم / الجهة" : "Shareholder Name"}</th>
                    <th className="p-2.5">{isAr ? "الصفة القانونية" : "Legal Role"}</th>
                    <th className="p-2.5 text-center">{isAr ? "الحصة السابقة" : "Before"}</th>
                    <th className="p-2.5 text-center">{isAr ? "الحصة الحالية" : "Current"}</th>
                    <th className="p-2.5 text-center">{isAr ? "التغير" : "Change"}</th>
                    <th className="p-2.5 text-center">{isAr ? "المستند" : "Doc"}</th>
                  </tr>
                </thead>
                <tbody className="divide-y-2 divide-black/10 dark:divide-white/10 font-bold bg-white dark:bg-zinc-900">
                  {ownership.shareholders.map((sh, idx) => (
                    <tr
                      key={idx}
                      className="hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
                    >
                      <td className="p-2.5 font-black text-black dark:text-white">
                        {sh.party_name}
                      </td>
                      <td className="p-2.5 text-zinc-600 dark:text-zinc-400">
                        {sh.party_role}
                      </td>
                      <td className="p-2.5 text-center font-mono">
                        {sh.stake_before != null ? `${sh.stake_before}%` : "—"}
                      </td>
                      <td className="p-2.5 text-center font-mono font-black text-black dark:text-white">
                        {sh.stake_after != null ? `${sh.stake_after}%` : "—"}
                      </td>
                      <td className="p-2.5 text-center">
                        {sh.change_direction === "increase" ? (
                          <span className="inline-flex items-center gap-0.5 px-2 py-0.5 text-[10px] font-black bg-[#00FF66] text-black border border-black">
                            <ArrowUpRight className="w-3 h-3" />
                            +{sh.change_amount_pct}%
                          </span>
                        ) : sh.change_direction === "decrease" ? (
                          <span className="inline-flex items-center gap-0.5 px-2 py-0.5 text-[10px] font-black bg-[#FF3366] text-white border border-black">
                            <ArrowDownRight className="w-3 h-3" />
                            -{sh.change_amount_pct}%
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-0.5 px-2 py-0.5 text-[10px] font-black bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300">
                            <Minus className="w-3 h-3" />
                            {isAr ? "ثابت" : "Unchanged"}
                          </span>
                        )}
                      </td>
                      <td className="p-2.5 text-center">
                        {sh.source_url ? (
                          <a
                            href={sh.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 px-2 py-1 text-[10px] font-black bg-[#FFE600] text-black border border-black hover:bg-black hover:text-white transition-colors"
                          >
                            <FileText className="w-3 h-3" />
                            PDF
                          </a>
                        ) : (
                          <span className="text-zinc-400">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-4 border-2 border-black/20 dark:border-white/10 bg-zinc-50 dark:bg-zinc-900 text-zinc-600 dark:text-zinc-400 text-xs font-bold text-center">
              {isAr
                ? "لا توجد تعديلات معلنة حديثاً بنماذج المادة (30) لكبار الملاك لهذا السهم، والتداول الحر متاح بالكامل للمستثمرين."
                : "No recent Article 30 major ownership filings on record for this symbol. Free float is fully accessible to public investors."}
            </div>
          )}
        </div>

        {/* Section 3: All Historical Insider Disclosures for this Stock */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
              <h3 className="text-sm sm:text-base font-black text-black dark:text-white uppercase tracking-wider">
                {isAr
                  ? `سجل إفصاحات وتعاملات السهم (${stockDisclosures.length})`
                  : `Historical Insider Filings (${stockDisclosures.length})`}
              </h3>
            </div>
          </div>

          {stockDisclosures.length > 0 ? (
            <div className="border-3 border-black dark:border-white/20 overflow-x-auto max-h-60 overflow-y-auto">
              <table className="w-full text-xs text-right border-collapse">
                <thead className="bg-black text-white dark:bg-white dark:text-black font-black uppercase text-[11px] sticky top-0">
                  <tr>
                    <th className="p-2.5">{isAr ? "التاريخ" : "Date"}</th>
                    <th className="p-2.5 text-center">{isAr ? "نوع العملية" : "Action"}</th>
                    <th className="p-2.5">{isAr ? "الطرف والصفة" : "Party & Role"}</th>
                    <th className="p-2.5 text-center">{isAr ? "عدد الأسهم" : "Shares"}</th>
                    <th className="p-2.5 text-center">{isAr ? "القيمة التقديرية" : "Estimated Value"}</th>
                    <th className="p-2.5 text-center">{isAr ? "المستند" : "Doc"}</th>
                  </tr>
                </thead>
                <tbody className="divide-y-2 divide-black/10 dark:divide-white/10 font-bold bg-white dark:bg-zinc-900">
                  {stockDisclosures.map((item) => {
                    const isMajorShareholder =
                      item.disclosure_type === "major_shareholders" || item.stake_after != null;
                    const shares = Math.abs(item.shares_count || 0);
                    const execPrice =
                      item.metadata?.execution_price || currentPrice || 1.0;
                    const val = shares * execPrice;

                    return (
                      <tr
                        key={item.id}
                        className="hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
                      >
                        <td className="p-2.5 text-zinc-600 dark:text-zinc-400 font-mono">
                          {item.disclosure_date}
                        </td>
                        <td className="p-2.5 text-center">
                          {isMajorShareholder ? (
                            <span className="px-2 py-0.5 text-[10px] font-black bg-purple-200 dark:bg-purple-900/60 text-purple-950 dark:text-purple-200 border border-purple-500">
                              {isAr ? "هيكل ملكية (مادة 30)" : "Ownership"}
                            </span>
                          ) : item.action_type === "buy" || item.sentiment === "bullish" ? (
                            <span className="px-2 py-0.5 text-[10px] font-black bg-[#00FF66] text-black border border-black">
                              {isAr ? "شراء داخلي" : "Buy"}
                            </span>
                          ) : item.action_type === "sell" || item.sentiment === "bearish" ? (
                            <span className="px-2 py-0.5 text-[10px] font-black bg-[#FF3366] text-white border border-black">
                              {isAr ? "بيع داخلي" : "Sell"}
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 text-[10px] font-black bg-[#FFE600] text-black border border-black">
                              {isAr ? "إفصاح عام" : "Filing"}
                            </span>
                          )}
                        </td>
                        <td className="p-2.5">
                          <span className="font-black text-black dark:text-white block">
                            {item.party_name || item.title}
                          </span>
                          {item.party_role && (
                            <span className="text-[10px] text-zinc-500 block">
                              {item.party_role}
                              {isMajorShareholder && (isAr ? " (إفصاح دوري عن الحصة)" : " (Periodic stake filing)")}
                            </span>
                          )}
                        </td>
                        <td className="p-2.5 text-center font-mono font-black">
                          {shares > 0 ? (
                            <>
                              <div>{shares.toLocaleString()}</div>
                              {item.stake_after != null && (
                                <div className="text-[10px] font-normal text-purple-700 dark:text-purple-300">
                                  {isAr ? `(حصة ${item.stake_after}%)` : `(${item.stake_after}%)`}
                                </div>
                              )}
                            </>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="p-2.5 text-center font-mono">
                          {val > 0 ? (
                            <>
                              <div className="font-black">{formatEgp(val)}</div>
                              {isMajorShareholder && (
                                <div className="text-[9px] text-purple-700 dark:text-purple-300 font-bold">
                                  {isAr ? "قيمة الحصة السوقية" : "Market Stake"}
                                </div>
                              )}
                            </>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="p-2.5 text-center">
                          {onOpenPdfModal ? (
                            <button
                              type="button"
                              onClick={() => onOpenPdfModal(item)}
                              className="px-2 py-1 text-[10px] font-black bg-zinc-200 dark:bg-zinc-800 hover:bg-[#FFE600] hover:text-black border border-black transition-colors cursor-pointer"
                            >
                              {isAr ? "معاينة" : "View"}
                            </button>
                          ) : item.source_url ? (
                            <a
                              href={item.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-2 py-1 text-[10px] font-black bg-[#FFE600] text-black border border-black"
                            >
                              PDF
                            </a>
                          ) : (
                            <span className="text-zinc-400">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-4 border-2 border-black/20 dark:border-white/10 bg-zinc-50 dark:bg-zinc-900 text-zinc-500 text-xs font-bold text-center">
              {isAr
                ? "لا توجد تعاملات منفصلة مسجلة في القائمة الحالية."
                : "No individual transaction records currently in view."}
            </div>
          )}
        </div>

        {/* Section 4: Quick Action CTAs */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t-4 border-black dark:border-white">
          <div className="flex flex-wrap items-center gap-2">
            {/* View Interactive Chart */}
            <Link
              href={`/chart?symbol=${upperSym}`}
              className="inline-flex items-center gap-2 px-4 py-2.5 text-xs font-black uppercase tracking-wider bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white shadow-[3px_3px_0px_#FFE600] hover:bg-[#FFE600] hover:text-black transition-all"
            >
              <BarChart3 className="w-4 h-4" />
              <span>{isAr ? "افتح الشارت التفاعلي المباشر" : "Open Live Chart"}</span>
            </Link>

            {/* Discuss in AI Chat */}
            {onDiscussInChat && (
              <button
                type="button"
                onClick={() => onDiscussInChat(upperSym, companyName)}
                className="inline-flex items-center gap-2 px-4 py-2.5 text-xs font-black uppercase tracking-wider bg-[#00FF66] text-black border-2 border-black shadow-[3px_3px_0px_#000] hover:bg-[#FFE600] active:translate-y-0.5 transition-all cursor-pointer"
              >
                <Bot className="w-4 h-4" />
                <span>{isAr ? "تحليل السهم بالذكاء الاصطناعي" : "Analyze in AI Chat"}</span>
              </button>
            )}

            {/* Filter disclosures by this symbol */}
            {onFilterBySymbol && (
              <button
                type="button"
                onClick={() => {
                  onFilterBySymbol(upperSym);
                  onClose();
                }}
                className="inline-flex items-center gap-2 px-3 py-2.5 text-xs font-black uppercase tracking-wider bg-zinc-100 dark:bg-zinc-800 text-black dark:text-white border-2 border-black dark:border-white/20 hover:bg-[#FFE600] hover:text-black transition-all cursor-pointer"
              >
                <Layers className="w-4 h-4" />
                <span>{isAr ? "تصفية صفحة الإفصاحات به" : "Filter Page by Stock"}</span>
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-black bg-zinc-200 dark:bg-zinc-800 text-black dark:text-white border-2 border-black hover:bg-black hover:text-white dark:hover:bg-white dark:hover:text-black transition-colors cursor-pointer"
          >
            {isAr ? "إغلاق النافذة" : "Close"}
          </button>
        </div>
      </div>
    </div>
  );
}