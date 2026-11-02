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
        throw new Error(data?.detail || data?.error || "تعذر تشغيل إعادة تدوير المحفظة");
      }
      setResult(data);
    } catch (err: any) {
      setError(err?.message || "حدث خطأ غير متوقع");
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
            className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto bg-zinc-950 text-zinc-100 border-4 border-black dark:border-white rounded-2xl p-5 sm:p-7 shadow-[8px_8px_0px_rgba(0,0,0,1)]"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-start justify-between gap-4 border-b-2 border-zinc-800 pb-4">
              <div>
                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/15 border border-amber-500/40 text-amber-300 text-[11px] font-black mb-2">
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>محرك إعادة تدوير السيولة الذكي · يخصم 1 رسالة من كوتا الشات</span>
                </div>
                <h3 className="text-xl sm:text-2xl font-black text-white">
                  🔄 تشخيص وإعادة تدوير المحفظة بالذكاء الاصطناعي
                </h3>
              </div>

              <button
                type="button"
                onClick={() => setOpen(false)}
                className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 border-2 border-zinc-700 text-zinc-300 cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            {loading ? (
              <div className="py-16 flex flex-col items-center justify-center text-center gap-4">
                <Loader2 className="w-10 h-10 text-amber-400 animate-spin" />
                <div className="space-y-1">
                  <div className="text-base font-black text-white">
                    جاري فحص مراكز محفظتك ومقارنتها بالسعر العادل والسيولة المؤسسية...
                  </div>
                  <div className="text-xs text-zinc-400">
                    يتم تحليل الأسهم الراكدة واستخراج أفضل بدائل التجميع في البورصة المصرية
                  </div>
                </div>
              </div>
            ) : error ? (
              <div className="py-10 text-center space-y-4">
                <div className="inline-flex p-3 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30">
                  <AlertTriangle className="w-8 h-8" />
                </div>
                <p className="text-sm sm:text-base font-bold text-rose-300 max-w-lg mx-auto leading-relaxed">
                  {error}
                </p>
                {limitReached && (
                  <Link
                    href="/pricing"
                    className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-black text-sm"
                  >
                    <Rocket className="w-4 h-4" />
                    <span>الترقية إلى باقة PRO الآن</span>
                  </Link>
                )}
              </div>
            ) : result ? (
              <div className="space-y-6 mt-5">
                {/* Summary KPI Row */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="bg-zinc-900 border-2 border-zinc-800 rounded-xl p-3.5">
                    <div className="text-[11px] text-zinc-400 font-bold">كفاءة وتوازن المحفظة</div>
                    <div
                      className={`text-2xl font-black mt-1 ${
                        result.healthScore >= 75
                          ? "text-emerald-400"
                          : result.healthScore >= 55
                          ? "text-amber-400"
                          : "text-rose-400"
                      }`}
                    >
                      {result.healthScore} / 100
                    </div>
                  </div>

                  <div className="bg-zinc-900 border-2 border-zinc-800 rounded-xl p-3.5">
                    <div className="text-[11px] text-zinc-400 font-bold">السيولة المقترح تحريرها</div>
                    <div className="text-xl font-black text-amber-400 mt-1">
                      {result.totalFreedCash.toLocaleString("en-US")} ج.م
                    </div>
                  </div>

                  <div className="bg-zinc-900 border-2 border-zinc-800 rounded-xl p-3.5">
                    <div className="text-[11px] text-zinc-400 font-bold">إجمالي القوة الشرائية للتدوير</div>
                    <div className="text-xl font-black text-emerald-400 mt-1">
                      {result.deployableCash.toLocaleString("en-US")} ج.م
                    </div>
                  </div>

                  <div className="bg-zinc-900 border-2 border-zinc-800 rounded-xl p-3.5">
                    <div className="text-[11px] text-zinc-400 font-bold">المتبقي في كوتا الشات</div>
                    <div className="text-xl font-black text-indigo-400 mt-1">
                      {result.remainingQuota} رسالة
                    </div>
                  </div>
                </div>

                {/* AI Executive Advisory */}
                <div className="bg-gradient-to-r from-amber-950/35 via-zinc-900 to-emerald-950/30 border-2 border-amber-500/40 rounded-2xl p-4">
                  <div className="text-xs font-black text-amber-300 flex items-center gap-1.5 mb-1.5">
                    <Sparkles className="w-4 h-4" />
                    <span>توصية المستشار الذكي (DeepSeek-V3):</span>
                  </div>
                  <p className="text-xs sm:text-sm text-zinc-200 leading-relaxed font-semibold">
                    {result.aiAdvisory}
                  </p>
                </div>

                {/* Step 1: Current Holdings Diagnosis */}
                <div className="space-y-3">
                  <h4 className="text-sm sm:text-base font-black text-white flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    <span>أولاً: تشخيص مراكزك الحالية وخطة التخفيف/التدوير</span>
                  </h4>

                  <div className="space-y-2.5">
                    {result.holdings.map((h) => {
                      const badgeCls =
                        h.action === "ROTATE_OUT"
                          ? "bg-rose-500/15 text-rose-400 border-rose-500/40"
                          : h.action === "TRIM_PROFIT"
                          ? "bg-amber-500/15 text-amber-300 border-amber-500/40"
                          : "bg-emerald-500/15 text-emerald-400 border-emerald-500/40";
                      return (
                        <div
                          key={h.symbol}
                          className="bg-zinc-900/90 border-2 border-zinc-800 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                        >
                          <div className="space-y-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-mono text-base font-black text-white">
                                {h.symbol}
                              </span>
                              <span className="text-xs font-bold text-zinc-300">{h.nameAr}</span>
                              <span className={`px-2.5 py-0.5 rounded-lg text-[11px] font-black border ${badgeCls}`}>
                                {h.actionLabelAr}
                              </span>
                              <span className="text-[11px] text-zinc-400">
                                الوزن: <strong>{h.weightPct}%</strong>
                              </span>
                            </div>
                            <p className="text-xs text-zinc-400">{h.reasonAr}</p>
                          </div>

                          <div className="shrink-0 flex sm:flex-col items-center sm:items-end justify-between gap-1 border-t sm:border-t-0 border-zinc-800 pt-2 sm:pt-0 text-xs">
                            <div>
                              <span className="text-zinc-400">الحالي: </span>
                              <strong className="text-white">{h.currentPrice} ج.م</strong>
                              {h.fairValue && (
                                <span className="text-emerald-400 mr-2">
                                  (العادل: {h.fairValue})
                                </span>
                              )}
                            </div>
                            {h.freedCashEgp > 0 && (
                              <div className="text-amber-300 font-black">
                                تحرير {h.suggestedTrimPct}% ≈ {h.freedCashEgp.toLocaleString("en-US")} ج.م
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
                    <h4 className="text-sm sm:text-base font-black text-white flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-emerald-400" />
                      <span>ثانياً: الفرص البديلة المرشحة لتوجيه السيولة (تجميع + سعر عادل)</span>
                    </h4>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      {result.replacements.map((rep) => (
                        <div
                          key={rep.symbol}
                          className="bg-zinc-900 border-2 border-emerald-500/35 rounded-xl p-4 flex flex-col justify-between space-y-3"
                        >
                          <div>
                            <div className="flex items-center justify-between">
                              <Link
                                href={`/stocks/${rep.symbol}`}
                                className="font-mono text-base font-black text-white hover:text-emerald-400"
                              >
                                {rep.symbol}
                              </Link>
                              <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 text-[11px] font-black border border-emerald-500/30">
                                رخيص بـ +{rep.upsidePct}%
                              </span>
                            </div>
                            <div className="text-xs font-bold text-zinc-300 mt-0.5">
                              {rep.nameAr}
                            </div>
                            <p className="text-[11px] text-zinc-400 mt-2 leading-relaxed">
                              {rep.catalystAr}
                            </p>
                          </div>

                          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-[11px] space-y-1">
                            <div className="flex justify-between">
                              <span className="text-zinc-400">سعر الدخول / العادل:</span>
                              <span className="font-black text-white">
                                {rep.currentPrice} ←{" "}
                                <span className="text-emerald-400">{rep.fairValue} ج.م</span>
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-zinc-400">المستهدف / وقف الخسارة:</span>
                              <span className="font-bold">
                                <span className="text-emerald-400">{rep.targetPrice}</span> /{" "}
                                <span className="text-rose-400">{rep.stopLoss}</span>
                              </span>
                            </div>
                            <div className="flex justify-between border-t border-zinc-800 pt-1">
                              <span className="text-amber-300 font-bold">الكمية المقترحة:</span>
                              <span className="font-black text-amber-300">
                                {rep.suggestedShares.toLocaleString("en-US")} سهم
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Footer Actions */}
                <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
                  <button
                    type="button"
                    onClick={() => void runRebalance()}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-xs font-bold text-zinc-300 cursor-pointer"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>إعادة الفحص (يخصم 1 رسالة)</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="px-5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-black text-xs cursor-pointer"
                  >
                    إغلاق
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
