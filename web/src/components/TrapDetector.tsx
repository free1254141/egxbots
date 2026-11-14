"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Flame,
  LockKeyhole,
  Rocket,
  ShieldAlert,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import { useMarket } from "@/contexts/MarketContext";
import { useAuth } from "@/contexts/AuthContext";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import { isPro } from "@/lib/ai/plan-gate";
import type { TrapsSnapshot, TrapSignalRow } from "@/app/api/scan/traps/route";
import type { SignalPerformancePayload } from "@/app/api/scan/signal-performance/route";

export default function TrapDetector() {
  const { language } = useLanguage();
  const { market, isSaudi, currencyLabel } = useMarket();
  const { user } = useAuth();
  const ar = language === "ar";
  const supabase = useMemo(() => createSupabaseBrowserClient(), []);
  const [snapshot, setSnapshot] = useState<TrapsSnapshot | null>(null);
  const [perf, setPerf] = useState<SignalPerformancePayload | null>(null);
  const [showReview, setShowReview] = useState(false);
  const [error, setError] = useState(false);
  const [activeTab, setActiveTab] = useState<"BEAR_TRAP" | "BULL_TRAP">("BEAR_TRAP");
  const [pro, setPro] = useState(false);

  useEffect(() => {
    let mounted = true;
    const checkLocalStorage = () => {
      try {
        if (typeof window !== "undefined" && localStorage.getItem("egx_pro_active") === "true") {
          if (mounted) setPro(true);
        }
      } catch {}
    };

    checkLocalStorage();

    const handleEntitlements = (event: Event) => {
      const customEvent = event as CustomEvent<{ is_pro?: boolean }>;
      if (typeof customEvent?.detail?.is_pro === "boolean") {
        if (mounted) setPro(customEvent.detail.is_pro);
      } else {
        checkLocalStorage();
      }
    };

    window.addEventListener("egx:entitlements-updated", handleEntitlements);

    if (!user) {
      setPro(false);
      return () => {
        mounted = false;
        window.removeEventListener("egx:entitlements-updated", handleEntitlements);
      };
    }
    void (async () => {
      try {
        const { data } = await supabase
          .from("subscriptions")
          .select("plan_id,status,current_period_end")
          .eq("user_id", user.id)
          .limit(10);
        if (mounted) setPro(isPro(data || []));
      } catch {
        if (mounted) setPro(false);
      }
    })();
    return () => {
      mounted = false;
      window.removeEventListener("egx:entitlements-updated", handleEntitlements);
    };
  }, [supabase, user]);

  // Fetch data for all users (free and Pro)
  useEffect(() => {
    const controller = new AbortController();
    setSnapshot(null);
    setError(false);
    setShowReview(false);

    const requests: Promise<unknown>[] = [
      fetch(`/api/scan/traps?market=${market}`, { signal: controller.signal })
        .then((res) => {
          if (!res.ok) throw new Error("Failed");
          return res.json();
        })
        .then(setSnapshot)
        .catch((cause) => {
          if (cause?.name !== "AbortError") setError(true);
        }),
    ];

    if (isSaudi) {
      setPerf(null);
    } else {
      requests.push(
        fetch("/api/scan/signal-performance", { signal: controller.signal })
          .then((res) => (res.ok ? res.json() : null))
          .then((data) => {
            if (data?.ok) setPerf(data);
          })
          .catch(() => {})
      );
    }

    void Promise.allSettled(requests);

    return () => controller.abort();
  }, [market, isSaudi]);

  const rows: TrapSignalRow[] =
    activeTab === "BEAR_TRAP" ? snapshot?.bearTraps || [] : snapshot?.bullTraps || [];

  const reviewSprings = perf?.review?.springs || [];
  const reviewUpthrusts = perf?.review?.upthrusts || [];
  const currentReviewList = activeTab === "BEAR_TRAP" ? reviewSprings : reviewUpthrusts;

  return (
    <section
      className="border-b-2 border-zinc-200 bg-zinc-50 px-3 py-4 text-zinc-950 dark:border-[#2a2e39] dark:bg-[#10151e] dark:text-white sm:px-6 sm:py-5"
      aria-label={ar ? "كاشف المصائد والانعكاسات" : "Trap Detector"}
      dir={ar ? "rtl" : "ltr"}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-emerald-500 shrink-0" />
          <h2 className="text-sm font-black uppercase tracking-wide">
            🪤 {ar ? `كاشف المصائد والانعكاسات — ${isSaudi ? "تاسي" : "EGX"} (إغلاق الجلسة)` : `Trap Detector — ${isSaudi ? "TASI" : "EGX"} (Daily Close)`}
          </h2>
          {snapshot?.asOf && (
            <span className="text-[11px] font-semibold text-zinc-500 dark:text-zinc-400">
              ({snapshot.asOf})
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setActiveTab("BEAR_TRAP");
              setShowReview(false);
            }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-black border-2 cursor-pointer transition-colors ${
              activeTab === "BEAR_TRAP"
                ? "border-emerald-500 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                : "border-zinc-300 dark:border-[#303744] text-zinc-500 hover:text-white"
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>
              {ar ? "مصيدة الدببة — ارتداد شرائي (Spring)" : "Bear Traps (Spring)"} (
              {snapshot?.totalBearTraps ?? 0})
            </span>
          </button>

          <button
            type="button"
            onClick={() => {
              setActiveTab("BULL_TRAP");
              setShowReview(false);
            }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-black border-2 cursor-pointer transition-colors ${
              activeTab === "BULL_TRAP"
                ? "border-rose-500 bg-rose-500/15 text-rose-600 dark:text-rose-400"
                : "border-zinc-300 dark:border-[#303744] text-zinc-500 hover:text-white"
            }`}
          >
            <TrendingDown className="w-3.5 h-3.5" />
            <span>
              {ar ? "مصيدة الثيران — اختراق وهمي (Upthrust)" : "Bull Traps (Upthrust)"} (
              {snapshot?.totalBullTraps ?? 0})
            </span>
          </button>
        </div>
      </div>

      {/* ── Model Track Record Banner ──────────────────────────────────── */}
      {perf && (
        <div className="mt-3 rounded border border-emerald-500/30 bg-emerald-500/5 p-3 text-xs dark:border-[#303744] dark:bg-[#151c27]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              {activeTab === "BEAR_TRAP" ? (
                <>
                  <span className="inline-flex items-center gap-1 font-bold text-emerald-600 dark:text-emerald-400">
                    <Target className="h-3.5 w-3.5" />
                    {ar ? "دقة الارتداد الشرائي (Spring - 40 جلسة):" : "Wyckoff Spring 40-Session Track Record:"}
                  </span>
                  <span className="rounded bg-emerald-500/15 px-2 py-0.5 font-mono font-bold text-emerald-600 dark:text-emerald-400">
                    {ar ? `نسبة صعود 3 أيام: ${perf.springs.hitRate3d}%` : `3-Day Rebound Hit: ${perf.springs.hitRate3d}%`}
                  </span>
                  <span className="text-zinc-600 dark:text-zinc-400 text-[11px]">
                    {ar
                      ? `(متوسط أقصى ربح: +${perf.springs.avgBest3d}% · تم اختبار ${perf.springs.events} نموذج)`
                      : `(Avg max gain: +${perf.springs.avgBest3d}% across ${perf.springs.events} signals)`}
                  </span>
                </>
              ) : (
                <>
                  <span className="inline-flex items-center gap-1 font-bold text-rose-600 dark:text-rose-400">
                    <ShieldCheck className="h-3.5 w-3.5" />
                    {ar ? "دقة تجنب فخاخ القمة (Upthrust - 40 جلسة):" : "Upthrust 40-Session Protection Record:"}
                  </span>
                  <span className="rounded bg-rose-500/15 px-2 py-0.5 font-mono font-bold text-rose-600 dark:text-rose-400">
                    {ar
                      ? `تأكيد هبوط اليوم التالي: ${perf.upthrusts.winRate}%`
                      : `Next-Day Drop: ${perf.upthrusts.winRate}%`}
                  </span>
                  <span className="text-zinc-600 dark:text-zinc-400 text-[11px]">
                    {ar
                      ? `(متوسط تجنب خسارة: ${perf.upthrusts.avgBest3d}% · تم اختبار ${perf.upthrusts.events} نموذج)`
                      : `(Avg drop: ${perf.upthrusts.avgBest3d}% across ${perf.upthrusts.events} signals)`}
                  </span>
                </>
              )}
            </div>

            {currentReviewList.length > 0 && (
              <button
                type="button"
                onClick={() => setShowReview(!showReview)}
                className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700 hover:underline dark:text-emerald-400 cursor-pointer"
              >
                <span>
                  {ar
                    ? `نتائج إشارات الأمس في تداول اليوم (${perf.review?.outcomeDate || "اليوم"})`
                    : `Yesterday's Signals in Today's Session (${perf.review?.outcomeDate || "Today"})`}
                </span>
                {showReview ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </button>
            )}
          </div>

          {/* Collapsible Review Table for Traps */}
          {showReview && currentReviewList.length > 0 && (
            <div className="mt-3 overflow-x-auto border-t border-emerald-500/20 pt-2">
              <table className="w-full text-left text-[11px]" dir={ar ? "rtl" : "ltr"}>
                <thead>
                  <tr className="text-zinc-500 dark:text-zinc-400">
                    <th className="py-1 px-2">{ar ? "السهم" : "Symbol"}</th>
                    <th className="py-1 px-2">{ar ? "إغلاق الإشارة" : "Signal Close"}</th>
                    <th className="py-1 px-2">
                      {activeTab === "BEAR_TRAP"
                        ? ar
                          ? "أعلى قمة اليوم"
                          : "Today's High"
                        : ar
                        ? "أدنى قاع اليوم"
                        : "Today's Low"}
                    </th>
                    <th className="py-1 px-2">{ar ? "إغلاق اليوم" : "Today's Close"}</th>
                    <th className="py-1 px-2">{ar ? "عائد الإغلاق" : "Return"}</th>
                    <th className="py-1 px-2">{ar ? "ارتداد الذيل" : "Wick %"}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200/50 dark:divide-zinc-800">
                  {currentReviewList.map((row) => (
                    <tr key={row.symbol} className="hover:bg-emerald-500/5">
                      <td className="py-1 px-2 font-mono font-black text-zinc-950 dark:text-white">
                        <Link
                          prefetch={false}
                          href={`/stocks/${row.symbol.toLowerCase()}${isSaudi ? "?market=tasi" : ""}`}
                          className="hover:text-emerald-500"
                        >
                          {row.symbol}
                        </Link>
                      </td>
                      <td className="py-1 px-2 font-mono">
                        {row.signalClose != null ? `${row.signalClose.toFixed(2)} ${currencyLabel}` : "—"}
                      </td>
                      <td className="py-1 px-2 font-mono font-bold">
                        {activeTab === "BEAR_TRAP" ? (
                          <span className="text-emerald-600 dark:text-emerald-400">
                            {row.nextHigh != null ? `${row.nextHigh.toFixed(2)} ${currencyLabel}` : "—"}{" "}
                            {row.intradayHighPct != null && (
                              <span className="text-[10px] font-normal">
                                (+{row.intradayHighPct}%)
                              </span>
                            )}
                          </span>
                        ) : (
                          <span className="text-rose-600 dark:text-rose-400">
                            {row.nextLow != null ? `${row.nextLow.toFixed(2)} ${currencyLabel}` : "—"}{" "}
                            {row.intradayLowPct != null && (
                              <span className="text-[10px] font-normal">
                                ({row.intradayLowPct}%)
                              </span>
                            )}
                          </span>
                        )}
                      </td>
                      <td className="py-1 px-2 font-mono">
                        {row.nextClose != null ? `${row.nextClose.toFixed(2)} ${currencyLabel}` : "—"}
                      </td>
                      <td className="py-1 px-2 font-mono font-bold">
                        <span
                          className={
                            row.retPct != null && row.retPct > 0
                              ? "text-emerald-600 dark:text-emerald-400"
                              : row.retPct != null && row.retPct < 0
                              ? "text-rose-600 dark:text-rose-400"
                              : "text-zinc-500"
                          }
                        >
                          {row.retPct != null ? `${row.retPct > 0 ? "+" : ""}${row.retPct}%` : "—"}
                        </span>
                      </td>
                      <td className="py-1 px-2 font-mono text-zinc-500">
                        {row.wickPct != null ? `${row.wickPct}%` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {error ? (
        <p className="mt-3 text-xs font-bold text-rose-600 dark:text-rose-400">
          {ar ? "تعذر تحميل إشارات المصائد حالياً." : "Unable to load trap signals."}
        </p>
      ) : !snapshot ? (
        <p className="mt-3 text-xs font-semibold text-zinc-500 dark:text-zinc-400">
          {ar ? "جاري فحص شموع الإغلاق ومستويات الدعم والمقاومة..." : "Scanning closing candles..."}
        </p>
      ) : rows.length === 0 ? (
        <p className="mt-3 text-xs font-semibold text-zinc-500 dark:text-zinc-400">
          {ar ? "لا توجد مصائد مرصودة في هذا الاتجاه لجلسة الإغلاق الحالية." : "No traps detected in this direction."}
        </p>
      ) : (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {rows.map((row) => {
            const isBearTrap = row.trapType === "BEAR_TRAP";
            return (
              <Link
                prefetch={false}
                key={row.symbol}
                href={`/stocks/${row.symbol.toLowerCase()}${isSaudi ? "?market=tasi" : ""}`}
                className="group border-2 border-zinc-200 bg-white p-3 transition hover:border-emerald-500 dark:border-[#303744] dark:bg-[#171e29]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-sm font-black">{row.symbol}</span>
                      <span
                        className={`px-1.5 py-0.5 text-[10px] font-black border ${
                          isBearTrap
                            ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500"
                            : "border-rose-500/40 bg-rose-500/10 text-rose-400"
                        }`}
                      >
                        {isBearTrap
                          ? ar
                            ? "كسر وهمي ارتدادي 🟢"
                            : "Spring 🟢"
                          : ar
                          ? "اختراق كاذب 🔴"
                          : "Upthrust 🔴"}
                      </span>
                    </div>
                    <p className="text-[11px] font-bold text-zinc-500 dark:text-zinc-400 line-clamp-1">
                      {row.nameAr}
                    </p>
                  </div>
                  <ArrowUpRight className="h-4 w-4 shrink-0 text-zinc-400 transition group-hover:text-emerald-500" />
                </div>

                <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-[11px]">
                  <div className="flex justify-between gap-1">
                    <dt className="text-zinc-500 dark:text-zinc-400">{ar ? "الإغلاق" : "Close"}</dt>
                    <dd className="font-mono font-bold">
                      {row.close} {currencyLabel}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-1">
                    <dt className="text-zinc-500 dark:text-zinc-400">
                      {isBearTrap ? (ar ? "الدعم" : "Support") : ar ? "المقاومة" : "Resist"}
                    </dt>
                    <dd className="font-mono font-bold text-amber-500">
                      {row.keyLevel} {currencyLabel}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-1">
                    <dt className="text-zinc-500 dark:text-zinc-400">
                      {isBearTrap ? (ar ? "ارتداد الذيل" : "Rebound") : ar ? "رفض الذيل" : "Reject"}
                    </dt>
                    <dd className="font-mono font-black text-emerald-500">{row.wickPct}%</dd>
                  </div>
                  <div className="flex justify-between gap-1">
                    <dt className="text-zinc-500 dark:text-zinc-400">{ar ? "قوة الإشارة" : "Score"}</dt>
                    <dd className="font-mono font-black text-indigo-400">{row.conviction}%</dd>
                  </div>
                </dl>
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}
