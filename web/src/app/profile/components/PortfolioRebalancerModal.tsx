"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  RefreshCw,
  X,
  Sparkles,
  ArrowLeftRight,
  TrendingUp,
  AlertTriangle,
  ShieldCheck,
  Rocket,
  Loader2,
} from "lucide-react";
import type {
  HoldingRebalanceDiagnosis,
  ReplacementCandidate,
} from "@/app/api/user/portfolio/rebalance/route";

interface RebalanceResponse {
  healthScore: number;
  totalPortfolioEquity: number;
  cashBalance: number;
  totalFreedCash: number;
  deployableCash: number;
  remainingQuota: number;
  aiAdvisory: string;
  holdings: HoldingRebalanceDiagnosis[];
  replacements: ReplacementCandidate[];
}

export default function PortfolioRebalancerModal({
  disabled,
  isAr,
}: {
  disabled?: boolean;
  isAr: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limitReached, setLimitReached] = useState(false);
  const [result, setResult] = useState<RebalanceResponse | null>(null);

  const runRebalance = async () => {
    setOpen(true);
    setLoading(true);
    setError(null);
    setLimitReached(false);
    try {
      const res = await fetch("/api/user/portfolio/rebalance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const data = await res.json();
      if (!res.ok) {
        if (res.status === 429 || data?.error === "LIMIT_REACHED") {
          setLimitReached(true);
        }
        throw new Error(data?.detail || data?.error || (isAr ? "تعذر تشغيل إعادة تدوير المحفظة" : "Failed to run portfolio rebalancer"));
      }
      setResult(data);
    } catch (err: any) {
      setError(err?.message || (isAr ? "حدث خطأ غير متوقع" : "Unexpected error occurred"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => void runRebalance()}
        disabled={disabled}
        className="h-10 px-4 flex items-center justify-center gap-2 border-4 border-black dark:border-white bg-amber-400 hover:bg-amber-300 text-black font-black text-xs uppercase tracking-widest shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
        title={
          isAr
            ? "تشخيص الأسهم الراكدة وإعادة تدوير السيولة بالذكاء الاصطناعي (يخصم 1 رسالة من كوتا الشات)"
            : "AI Portfolio Rebalancer (Deducts 1 chat quota message)"
        }
      >
        <ArrowLeftRight className="h-4 w-4" />
        <span>{isAr ? "🔄 إعادة تدوير المحفظة (AI)" : "🔄 AI Rebalance"}</span>
      </button>

      {open && (
        <div
          dir={isAr ? "rtl" : "ltr"}
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/75 backdrop-blur-xs p-3 sm:p-6 overflow-y-auto"
          onClick={() => setOpen(false)}
        >
          <div
            className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 border-4 border-black dark:border-white rounded-2xl p-5 sm:p-7 shadow-[8px_8px_0px_rgba(0,0,0,1)] dark:shadow-[8px_8px_0px_rgba(255,255,255,1)] transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-start justify-between gap-4 border-b-2 border-zinc-200 dark:border-zinc-800 pb-4">
              <div>
                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/15 border border-amber-500/40 text-amber-700 dark:text-amber-300 text-[11px] font-black mb-2">
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>
                    {isAr
                      ? "محرك إعادة تدوير السيولة الذكي · يخصم 1 رسالة من كوتا الشات"
                      : "AI Smart Liquidity Rebalancer · Deducts 1 Chat Quota"}
                  </span>
                </div>
                <h3 className="text-xl sm:text-2xl font-black text-zinc-950 dark:text-white">
                  {isAr
                    ? "🔄 تشخيص وإعادة تدوير المحفظة بالذكاء الاصطناعي"
                    : "🔄 AI Portfolio Diagnosis & Rebalancing"}
                </h3>
              </div>

              <button
                type="button"
                onClick={() => setOpen(false)}
                className="p-2 rounded-xl bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 border-2 border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 cursor-pointer transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            {loading ? (
              <div className="py-16 flex flex-col items-center justify-center text-center gap-4">
                <Loader2 className="w-10 h-10 text-amber-500 animate-spin" />
                <div className="space-y-1">
                  <div className="text-base font-black text-zinc-950 dark:text-white">
                    {isAr
                      ? "جاري فحص مراكز محفظتك ومقارنتها بالسعر العادل والسيولة المؤسسية..."
                      : "Analyzing your portfolio holdings against Fair Value & Institutional Liquidity..."}
                  </div>
                  <div className="text-xs text-zinc-500 dark:text-zinc-400">
                    {isAr
                      ? "يتم تحليل الأسهم الراكدة واستخراج أفضل بدائل التجميع في البورصة المصرية"
                      : "Detecting dead capital and selecting top EGX accumulation candidates"}
                  </div>
                </div>
              </div>
            ) : error ? (
              <div className="py-10 text-center space-y-4">
                <div className="inline-flex p-3 rounded-full bg-rose-500/15 text-rose-500 border border-rose-500/30">
                  <AlertTriangle className="w-8 h-8" />
                </div>
                <p className="text-sm sm:text-base font-bold text-rose-600 dark:text-rose-400 max-w-lg mx-auto leading-relaxed">
                  {error}
                </p>
                {limitReached && (
                  <Link
                    href="/pricing"
                    className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-black text-sm"
                  >
                    <Rocket className="w-4 h-4" />
                    <span>{isAr ? "الترقية إلى باقة PRO الآن" : "Upgrade to PRO Now"}</span>
                  </Link>
                )}
              </div>
            ) : result ? (
              <div className="space-y-6 mt-5">
                {/* Summary KPI Row */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="bg-zinc-50 dark:bg-zinc-900 border-2 border-zinc-200 dark:border-zinc-800 rounded-xl p-3.5 shadow-sm">
                    <div className="text-[11px] text-zinc-500 dark:text-zinc-400 font-bold">
                      {isAr ? "كفاءة وتوازن المحفظة" : "Portfolio Health"}
                    </div>
                    <div
                      className={`text-2xl font-black mt-1 ${
                        result.healthScore >= 75
                          ? "text-emerald-600 dark:text-emerald-400"
                          : result.healthScore >= 55
                          ? "text-amber-600 dark:text-amber-400"
                          : "text-rose-600 dark:text-rose-400"
                      }`}
                    >
                      {result.healthScore} / 100
                    </div>
                  </div>

                  <div className="bg-zinc-50 dark:bg-zinc-900 border-2 border-zinc-200 dark:border-zinc-800 rounded-xl p-3.5 shadow-sm">
                    <div className="text-[11px] text-zinc-500 dark:text-zinc-400 font-bold">
                      {isAr ? "السيولة المقترح تحريرها" : "Freed Liquidity"}
                    </div>
                    <div className="text-xl font-black text-amber-600 dark:text-amber-400 mt-1">
                      {result.totalFreedCash.toLocaleString("en-US")} {isAr ? "ج.م" : "EGP"}
                    </div>
                  </div>

                  <div className="bg-zinc-50 dark:bg-zinc-900 border-2 border-zinc-200 dark:border-zinc-800 rounded-xl p-3.5 shadow-sm">
                    <div className="text-[11px] text-zinc-500 dark:text-zinc-400 font-bold">
                      {isAr ? "القوة الشرائية المتاحة" : "Deployable Capital"}
                    </div>
                    <div className="text-xl font-black text-emerald-600 dark:text-emerald-400 mt-1">
                      {result.deployableCash.toLocaleString("en-US")} {isAr ? "ج.م" : "EGP"}
                    </div>
                  </div>

                  <div className="bg-zinc-50 dark:bg-zinc-900 border-2 border-zinc-200 dark:border-zinc-800 rounded-xl p-3.5 shadow-sm">
                    <div className="text-[11px] text-zinc-500 dark:text-zinc-400 font-bold">
                      {isAr ? "المتبقي في كوتا الشات" : "Remaining Quota"}
                    </div>
                    <div className="text-xl font-black text-indigo-600 dark:text-indigo-400 mt-1">
                      {result.remainingQuota} {isAr ? "رسالة" : "msgs"}
                    </div>
                  </div>
                </div>

                {/* AI Executive Advisory */}
                <div className="bg-gradient-to-r from-amber-500/10 via-zinc-100 to-emerald-500/10 dark:from-amber-950/35 dark:via-zinc-900 dark:to-emerald-950/30 border-2 border-amber-500/40 rounded-2xl p-4 shadow-sm">
                  <div className="text-xs font-black text-amber-700 dark:text-amber-300 flex items-center gap-1.5 mb-1.5">
                    <Sparkles className="w-4 h-4" />
                    <span>{isAr ? "توصية المستشار الذكي (DeepSeek-V3):" : "Executive AI Advisory (DeepSeek-V3):"}</span>
                  </div>
                  <p className="text-xs sm:text-sm text-zinc-800 dark:text-zinc-200 leading-relaxed font-semibold">
                    {result.aiAdvisory}
                  </p>
                </div>

                {/* Step 1: Current Holdings Diagnosis */}
                <div className="space-y-3">
                  <h4 className="text-sm sm:text-base font-black text-zinc-950 dark:text-white flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-emerald-500" />
                    <span>
                      {isAr
                        ? "أولاً: تشخيص مراكزك الحالية وخطة التخفيف/التدوير"
                        : "Step 1: Current Holdings Diagnosis & Rotation Plan"}
                    </span>
                  </h4>

                  <div className="space-y-2.5">
                    {result.holdings.map((h) => {
                      const badgeCls =
                        h.action === "ROTATE_OUT"
                          ? "bg-rose-100 dark:bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-300 dark:border-rose-500/40"
                          : h.action === "TRIM_PROFIT"
                          ? "bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-500/40"
                          : "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-500/40";
                      return (
                        <div
                          key={h.symbol}
                          className="bg-zinc-50 dark:bg-zinc-900 border-2 border-zinc-200 dark:border-zinc-800 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm"
                        >
                          <div className="space-y-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-mono text-base font-black text-zinc-950 dark:text-white">
                                {h.symbol}
                              </span>
                              <span className="text-xs font-bold text-zinc-700 dark:text-zinc-300">{h.nameAr}</span>
                              <span className={`px-2.5 py-0.5 rounded-lg text-[11px] font-black border ${badgeCls}`}>
                                {h.actionLabelAr}
                              </span>
                              <span className="text-[11px] text-zinc-500 dark:text-zinc-400 font-mono">
                                {isAr ? "الوزن:" : "Weight:"} <strong>{h.weightPct}%</strong>
                              </span>
                            </div>
                            <p className="text-xs text-zinc-600 dark:text-zinc-400">{h.reasonAr}</p>
                          </div>

                          <div className="shrink-0 flex sm:flex-col items-center sm:items-end justify-between gap-1 border-t sm:border-t-0 border-zinc-200 dark:border-zinc-800 pt-2 sm:pt-0 text-xs font-mono">
                            <div>
                              <span className="text-zinc-500 dark:text-zinc-400">{isAr ? "الحالي:" : "Price:"} </span>
                              <strong className="text-zinc-950 dark:text-white">{h.currentPrice} {isAr ? "ج.م" : "EGP"}</strong>
                              {h.fairValue && (
                                <span className="text-emerald-600 dark:text-emerald-400 font-bold ms-2">
                                  ({isAr ? "العادل:" : "Fair:"} {h.fairValue})
                                </span>
                              )}
                            </div>
                            {h.freedCashEgp > 0 && (
                              <div className="text-amber-600 dark:text-amber-400 font-black">
                                {isAr ? `تحرير ${h.suggestedTrimPct}% ≈ ${h.freedCashEgp.toLocaleString("en-US")} ج.م` : `Free ${h.suggestedTrimPct}% ≈ ${h.freedCashEgp.toLocaleString("en-US")} EGP`}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Step 2: Replacement Candidates */}
                {result.replacements.length > 0 && (
                  <div className="space-y-3">
                    <h4 className="text-sm sm:text-base font-black text-zinc-950 dark:text-white flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-emerald-500" />
                      <span>
                        {isAr
                          ? "ثانياً: الفرص البديلة المرشحة لتوجيه السيولة (تجميع + سعر عادل)"
                          : "Step 2: Recommended Replacement Candidates (Accumulation + Fair Value)"}
                      </span>
                    </h4>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      {result.replacements.map((rep) => (
                        <div
                          key={rep.symbol}
                          className="bg-zinc-50 dark:bg-zinc-900 border-2 border-emerald-300 dark:border-emerald-500/40 rounded-xl p-4 flex flex-col justify-between space-y-3 shadow-sm"
                        >
                          <div>
                            <div className="flex items-center justify-between">
                              <Link
                                prefetch={false}
                                href={`/stocks/${rep.symbol.toLowerCase()}`}
                                className="font-mono text-base font-black text-zinc-950 dark:text-white hover:text-emerald-600 dark:hover:text-emerald-400"
                              >
                                {rep.symbol}
                              </Link>
                              <span className="px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 text-[11px] font-black border border-emerald-300 dark:border-emerald-500/30">
                                {isAr ? `خصم +${rep.upsidePct}%` : `+${rep.upsidePct}% Upside`}
                              </span>
                            </div>
                            <div className="text-xs font-bold text-zinc-800 dark:text-zinc-200 mt-0.5">
                              {rep.nameAr}
                            </div>
                            <p className="text-[11px] text-zinc-600 dark:text-zinc-400 mt-2 leading-relaxed">
                              {rep.catalystAr}
                            </p>
                          </div>

                          <div className="bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-lg p-2.5 text-[11px] space-y-1 font-mono">
                            <div className="flex justify-between">
                              <span className="text-zinc-500 dark:text-zinc-400">{isAr ? "الدخول / العادل:" : "Entry / Fair:"}</span>
                              <span className="font-black text-zinc-900 dark:text-white">
                                {rep.currentPrice} ←{" "}
                                <span className="text-emerald-600 dark:text-emerald-400">{rep.fairValue} ج.م</span>
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-zinc-500 dark:text-zinc-400">{isAr ? "الهدف / الوقف:" : "Target / Stop:"}</span>
                              <span className="font-bold">
                                <span className="text-emerald-600 dark:text-emerald-400">{rep.targetPrice}</span> /{" "}
                                <span className="text-rose-600 dark:text-rose-400">{rep.stopLoss}</span>
                              </span>
                            </div>
                            <div className="flex justify-between border-t border-zinc-200 dark:border-zinc-800 pt-1">
                              <span className="text-amber-600 dark:text-amber-400 font-bold">{isAr ? "الكمية المقترحة:" : "Suggested Qty:"}</span>
                              <span className="font-black text-amber-600 dark:text-amber-400">
                                {rep.suggestedShares.toLocaleString("en-US")} {isAr ? "سهم" : "shares"}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Footer Actions */}
                <div className="flex items-center justify-between pt-3 border-t-2 border-zinc-200 dark:border-zinc-800">
                  <button
                    type="button"
                    onClick={() => void runRebalance()}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 border border-zinc-300 dark:border-zinc-700 text-xs font-bold text-zinc-700 dark:text-zinc-300 cursor-pointer transition-colors"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>{isAr ? "إعادة الفحص (يخصم 1 رسالة)" : "Re-diagnose (1 msg)"}</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="px-5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-black text-xs cursor-pointer shadow-sm"
                  >
                    {isAr ? "إغلاق" : "Close"}
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </>
  );
}
