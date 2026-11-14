"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  Activity,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Flame,
  LockKeyhole,
  Rocket,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { fetchUnusualActivity, type UnusualActivitySnapshot } from "@/lib/api";
import { useLanguage } from "@/contexts/LanguageContext";
import { useMarket } from "@/contexts/MarketContext";
import { useAuth } from "@/contexts/AuthContext";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import { isPro } from "@/lib/ai/plan-gate";
import type { SignalPerformancePayload } from "@/app/api/scan/signal-performance/route";

export default function UnusualActivity() {
  const { language } = useLanguage();
  const { market, isSaudi, currencyLabel } = useMarket();
  const { user } = useAuth();
  const ar = language === "ar";
  const supabase = useMemo(() => createSupabaseBrowserClient(), []);
  const [snapshot, setSnapshot] = useState<UnusualActivitySnapshot | null>(null);
  const [perf, setPerf] = useState<SignalPerformancePayload | null>(null);
  const [showReview, setShowReview] = useState(false);
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [pro, setPro] = useState(false);

  useEffect(() => {
    let mounted = true;
    if (!user) {
      setPro(false);
      return () => {
        mounted = false;
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
    };
  }, [supabase, user]);

  // Fetch data for all users (free and Pro) to inspect market volume spikes
  useEffect(() => {
    const controller = new AbortController();
    setSnapshot(null);
    setError(false);
    setShowReview(false);
    setExpanded(false);

    const requests: Promise<unknown>[] = [
      fetchUnusualActivity(controller.signal, market)
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

  const visible = expanded ? snapshot?.rows : snapshot?.rows?.slice(0, 6);

  // ── Full view (Free for all users) ─────────────────────────────────────────────────────────
  const reviewUnusual = perf?.review?.unusual || [];
  const topMover = perf?.review?.topMover;

  return (
    <section
      className="border-y-2 border-zinc-200 bg-zinc-50 px-3 py-4 text-zinc-950 dark:border-[#2a2e39] dark:bg-[#10151e] dark:text-white sm:px-6 sm:py-5"
      aria-label={ar ? "نشاط غير طبيعي" : "Unusual activity"}
      dir={ar ? "rtl" : "ltr"}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 border border-black bg-white p-1 dark:border-white">
            <Image
              src="/favicon_io/apple-touch-icon.png"
              alt="EGX Bots"
              width={20}
              height={20}
              className="h-5 w-5 object-contain"
            />
          </span>
          <Activity className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
          <h2 className="text-sm font-black text-zinc-950 dark:text-white">
            {ar ? `نشاط غير طبيعي وانفجار سعري — ${isSaudi ? "تاسي" : "EGX"}` : `Unusual Activity & Volume Breakout — ${isSaudi ? "TASI" : "EGX"}`}
          </h2>
          {snapshot && (
            <span className="shrink-0 border border-amber-500/40 bg-amber-100 px-2 py-0.5 text-[10px] font-black text-amber-900 dark:bg-amber-400/10 dark:text-amber-300">
              {snapshot.totalMatches}
            </span>
          )}
        </div>
        <span className="text-[10px] leading-5 text-zinc-600 dark:text-[#b4bac6] sm:text-right">
          {snapshot
            ? ar
              ? `جلسة ${snapshot.asOf} · تغطية ${snapshot.coverage} سهم · حجم ≥ ${snapshot.threshold}× المتوسط`
              : `Session ${snapshot.asOf} · ${snapshot.coverage} stocks covered · volume ≥ ${snapshot.threshold}× average`
            : null}
        </span>
      </div>

      {/* ── Daily Performance & Yesterday's Signal Review Banner ───────── */}
      {perf && (
        <div className="mt-3 rounded border border-amber-500/30 bg-amber-500/5 p-3 text-xs dark:border-amber-400/20 dark:bg-[#151c27]">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-500/20 pb-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 font-bold text-amber-700 dark:text-amber-400">
                <Target className="h-3.5 w-3.5" />
                {ar ? "إحصائيات النجاح (آخر 40 جلسة):" : "40-Session Track Record:"}
              </span>
              <span className="rounded bg-amber-500/15 px-2 py-0.5 font-mono font-bold text-amber-900 dark:text-amber-300">
                {ar ? `نسبة الانفجار 3 أيام: ${perf.unusual.hitRate3d}%` : `3-Day Breakout: ${perf.unusual.hitRate3d}%`}
              </span>
              <span className="text-zinc-600 dark:text-zinc-400 text-[11px]">
                {ar
                  ? `(متوسط أقصى صعود: +${perf.unusual.avgBest3d}% · تم فحص ${perf.unusual.events} إشارة)`
                  : `(Avg max gain: +${perf.unusual.avgBest3d}% across ${perf.unusual.events} events)`}
              </span>
            </div>

            {reviewUnusual.length > 0 && (
              <button
                type="button"
                onClick={() => setShowReview(!showReview)}
                className="inline-flex items-center gap-1 text-[11px] font-bold text-amber-700 hover:underline dark:text-amber-400 cursor-pointer"
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

          {/* Top Mover Highlight */}
          {topMover && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
              <span className="inline-flex items-center gap-1 font-bold text-emerald-600 dark:text-emerald-400">
                <Flame className="h-3.5 w-3.5 text-amber-500" />
                {ar
                  ? `أقوى تحرك اليوم (${perf.review?.outcomeDate || "اليوم"}) من إشارات الأمس (${perf.review?.signalDate || "أمس"}):`
                  : `Top Performer Today (${perf.review?.outcomeDate || "Today"}) from Yesterday:`}
              </span>
              <b className="font-mono text-zinc-950 dark:text-white">{topMover.symbol}</b>
              <span className="text-zinc-600 dark:text-zinc-400">
                {ar ? "سعر الإشارة:" : "Signal:"}{" "}
                <b className="font-mono">
                  {topMover.signalClose != null ? `${topMover.signalClose.toFixed(2)} ${currencyLabel}` : "—"}
                </b>
              </span>
              {topMover.intradayHighPct != null && (
                <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-mono font-bold text-emerald-600 dark:text-emerald-400">
                  {ar ? `أعلى قمة اليوم: +${topMover.intradayHighPct}%` : `Peak High: +${topMover.intradayHighPct}%`}
                </span>
              )}
              {topMover.retPct != null && (
                <span className="font-mono font-bold text-zinc-700 dark:text-zinc-300">
                  {ar ? `الإغلاق: ${topMover.retPct > 0 ? "+" : ""}${topMover.retPct}%` : `Close: ${topMover.retPct > 0 ? "+" : ""}${topMover.retPct}%`}
                </span>
              )}
              {topMover.relativeVolume != null && (
                <span className="text-zinc-500 text-[10px]">
                  ({ar ? `حجم ${topMover.relativeVolume.toFixed(1)}×` : `Vol ${topMover.relativeVolume.toFixed(1)}x`})
                </span>
              )}
            </div>
          )}

          {/* Collapsible Yesterday Signal Table */}
          {showReview && reviewUnusual.length > 0 && (
            <div className="mt-3 overflow-x-auto border-t border-amber-500/20 pt-2">
              <table className="w-full text-left text-[11px]" dir={ar ? "rtl" : "ltr"}>
                <thead>
                  <tr className="text-zinc-500 dark:text-zinc-400">
                    <th className="py-1 px-2">{ar ? "السهم" : "Symbol"}</th>
                    <th className="py-1 px-2">{ar ? "سعر الإشارة" : "Signal Close"}</th>
                    <th className="py-1 px-2">{ar ? "أعلى قمة اليوم" : "Today's High"}</th>
                    <th className="py-1 px-2">{ar ? "إغلاق اليوم" : "Today's Close"}</th>
                    <th className="py-1 px-2">{ar ? "العائد" : "Return"}</th>
                    <th className="py-1 px-2">{ar ? "الحجم النسبي" : "Rel Vol"}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200/50 dark:divide-zinc-800">
                  {reviewUnusual.map((row) => (
                    <tr key={row.symbol} className="hover:bg-amber-500/5">
                      <td className="py-1 px-2 font-mono font-black text-zinc-950 dark:text-white">
                        <Link
                          prefetch={false}
                          href={`/stocks/${row.symbol.toLowerCase()}${isSaudi ? "?market=tasi" : ""}`}
                          className="hover:text-amber-500"
                        >
                          {row.symbol}
                        </Link>
                      </td>
                      <td className="py-1 px-2 font-mono">
                        {row.signalClose != null ? `${row.signalClose.toFixed(2)} ${currencyLabel}` : "—"}
                      </td>
                      <td className="py-1 px-2 font-mono font-bold text-emerald-600 dark:text-emerald-400">
                        {row.nextHigh != null ? `${row.nextHigh.toFixed(2)} ${currencyLabel}` : "—"}{" "}
                        {row.intradayHighPct != null && (
                          <span className="text-[10px] font-normal">
                            (+{row.intradayHighPct}%)
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
                        {row.relativeVolume != null ? `${row.relativeVolume.toFixed(1)}×` : "—"}
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
        <p className="mt-3 text-xs font-semibold text-amber-800 dark:text-amber-300">
          {ar ? "تعذر تحميل النشاط الآن." : "Activity is temporarily unavailable."}
        </p>
      ) : !snapshot ? (
        <p className="mt-3 text-xs text-zinc-600 dark:text-[#b4bac6]">
          {ar ? "جاري تحميل آخر جلسة…" : "Loading latest session…"}
        </p>
      ) : !snapshot.rows.length ? (
        <p className="mt-3 text-xs text-zinc-600 dark:text-[#b4bac6]">
          {ar
            ? "لا توجد أسهم حققت شرط حجم التداول في آخر جلسة محفوظة."
            : "No stocks met the volume threshold in the latest stored session."}
        </p>
      ) : (
        <>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {visible?.map((row) => (
              <div
                key={row.symbol}
                className="group relative min-w-0 border-2 border-zinc-200 bg-white p-3 transition-colors hover:border-amber-500 dark:border-[#303744] dark:bg-[#171e29] dark:hover:border-amber-400/70"
              >
                <div className="flex items-center justify-between gap-2">
                  <b className="text-sm font-black text-zinc-950 dark:text-white">{row.symbol}</b>
                  <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-zinc-500 group-hover:text-amber-600 dark:text-[#b4bac6] dark:group-hover:text-amber-400" />
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
                  <span className="text-zinc-600 dark:text-[#b4bac6]">
                    {ar ? "السعر" : "Price"}{" "}
                    <b
                      className={
                        row.changePct != null && row.changePct >= 0
                          ? "text-emerald-700 dark:text-emerald-400"
                          : "text-rose-700 dark:text-rose-400"
                      }
                    >
                      {row.close != null ? `${row.close.toFixed(2)} ${currencyLabel}` : "—"}
                    </b>
                  </span>
                  <span className="text-zinc-600 dark:text-[#b4bac6]">
                    RSI <b className="text-zinc-950 dark:text-white">{row.rsi?.toFixed(0) ?? "—"}</b>
                  </span>
                  <span className="text-zinc-600 dark:text-[#b4bac6]">
                    {ar ? "الحجم" : "Volume"}{" "}
                    <b className="text-amber-700 dark:text-amber-300">{row.relativeVolume.toFixed(1)}×</b>
                  </span>
                  <span className="text-zinc-600 dark:text-[#b4bac6]">
                    {ar ? "تقييم AI" : "AI Score"}{" "}
                    <b className="text-zinc-950 dark:text-white">{row.aiScore?.toFixed(0) ?? "—"}/100</b>
                  </span>
                </div>
                <p className="mt-2 break-words text-[10px] leading-5 text-zinc-600 dark:text-[#b4bac6]">
                  {row.distanceToResistancePct == null
                    ? ar
                      ? "مقاومة 20 جلسة: تاريخ غير كافٍ"
                      : "20-session resistance: insufficient history"
                    : row.distanceToResistancePct >= 0
                    ? ar
                      ? `أسفل أعلى سعر في 20 جلسة بـ${row.distanceToResistancePct.toFixed(1)}%`
                      : `${row.distanceToResistancePct.toFixed(1)}% below prior 20-session high`
                    : ar
                    ? `أعلى من قمة 20 جلسة بـ${Math.abs(row.distanceToResistancePct).toFixed(1)}%`
                    : `${Math.abs(row.distanceToResistancePct).toFixed(1)}% above prior 20-session high`}
                </p>
                <Link
                  prefetch={false}
                  aria-label={`${ar ? "فتح" : "Open"} ${row.symbol}`}
                  href={`/chart?symbol=${encodeURIComponent(row.symbol)}&exchange=${isSaudi ? "TADAWUL" : "EGX"}`}
                  className="absolute inset-0"
                />
              </div>
            ))}
          </div>
          {snapshot.rows.length > 6 && (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              className="mt-3 text-xs font-bold text-amber-800 hover:underline dark:text-amber-300"
            >
              {expanded ? (ar ? "عرض أقل" : "Show fewer") : ar ? "عرض كل الحالات" : "Show all matches"}
            </button>
          )}
          <p className="mt-2 text-[10px] leading-5 text-zinc-600 dark:text-[#b4bac6]">
            {ar
              ? "بيانات نهاية آخر جلسة محفوظة، وليست أسعارًا لحظية أو إشارة شراء. يتم تحديث إحصائيات النجاح ومراجعة إشارات الأمس يومياً بعد إغلاق الجلسة."
              : "Latest stored end-of-session data, not live quotes or a buy signal. Performance statistics and yesterday signal reviews update daily after market close."}
          </p>
        </>
      )}
    </section>
  );
}
