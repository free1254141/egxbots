"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, Sparkles, ExternalLink } from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

export interface MetalPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

type MetalRange = "1M" | "3M" | "6M" | "1Y";

const RANGE_POINTS: Record<MetalRange, number> = {
  "1M": 23,
  "3M": 66,
  "6M": 132,
  "1Y": 260,
};

const RANGE_LABELS: Record<MetalRange, { ar: string; en: string }> = {
  "1M": { ar: "شهر", en: "1M" },
  "3M": { ar: "3 أشهر", en: "3M" },
  "6M": { ar: "6 أشهر", en: "6M" },
  "1Y": { ar: "سنة", en: "1Y" },
};

function computeMetalMetrics(points: MetalPoint[]) {
  if (!points || points.length === 0) {
    return {
      last: 0,
      dayChange: 0,
      dayChangePct: 0,
      periodChangePct: 0,
      periodHigh: 0,
      periodLow: 0,
      lastDate: "",
    };
  }
  const latest = points[points.length - 1];
  const prev = points.length >= 2 ? points[points.length - 2] : latest;
  const first = points[0];
  const dayChange = latest.close - prev.close;
  const dayChangePct = prev.close > 0 ? (dayChange / prev.close) * 100 : 0;
  const periodChangePct = first.close > 0 ? ((latest.close - first.close) / first.close) * 100 : 0;
  let periodHigh = latest.high || latest.close;
  let periodLow = latest.low || latest.close;
  for (const p of points) {
    const h = p.high > 0 ? p.high : p.close;
    const l = p.low > 0 ? p.low : p.close;
    if (h > periodHigh) periodHigh = h;
    if (l < periodLow) periodLow = l;
  }
  return {
    last: latest.close,
    dayChange,
    dayChangePct,
    periodChangePct,
    periodHigh,
    periodLow,
    lastDate: latest.date,
  };
}

function MetalChartCard({
  symbol,
  titleAr,
  titleEn,
  subtitleAr,
  subtitleEn,
  points,
  isAr,
  accentColor,
  gradientId,
  badgeClass,
  borderClass,
  aiPromptAr,
  aiPromptEn,
  rangeLabel,
}: {
  symbol: "XAUUSD" | "XAGUSD";
  titleAr: string;
  titleEn: string;
  subtitleAr: string;
  subtitleEn: string;
  points: MetalPoint[];
  isAr: boolean;
  accentColor: string;
  gradientId: string;
  badgeClass: string;
  borderClass: string;
  aiPromptAr: string;
  aiPromptEn: string;
  rangeLabel: string;
}) {
  const metrics = useMemo(() => computeMetalMetrics(points), [points]);
  const isUp = metrics.dayChangePct >= 0;
  const isPeriodUp = metrics.periodChangePct >= 0;

  const formatDate = (dateStr: string) => {
    if (!dateStr) return "";
    try {
      return new Date(dateStr).toLocaleDateString(isAr ? "ar-EG" : "en-US", {
        month: "short",
        day: "numeric",
      });
    } catch {
      return dateStr;
    }
  };

  const renderTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload || !payload.length) return null;
    const val = typeof payload[0]?.value === "number" ? payload[0].value : null;
    if (val === null) return null;
    const idx = points.findIndex((p) => p.date === label);
    const prevVal = idx > 0 ? points[idx - 1].close : val;
    const diff = val - prevVal;
    const diffPct = prevVal > 0 ? (diff / prevVal) * 100 : 0;
    const up = diff >= 0;
    return (
      <div
        className="border-2 border-black dark:border-white bg-white dark:bg-zinc-950 p-3 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,0.2)] text-xs space-y-1 min-w-[155px]"
        dir={isAr ? "rtl" : "ltr"}
      >
        <p className="text-zinc-500 font-black font-mono border-b border-black/10 dark:border-white/10 pb-1">
          {label}
        </p>
        <p className="flex items-baseline justify-between gap-3">
          <span className="text-[10px] font-bold text-zinc-400">{symbol}</span>
          <span className="font-mono font-black text-zinc-950 dark:text-white">
            ${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </p>
        <p className="flex items-center justify-between gap-3">
          <span className="text-[10px] font-bold text-zinc-400">{isAr ? "التغير اليومي" : "Daily"}</span>
          <span className={`font-mono font-black ${up ? "text-emerald-500" : "text-rose-500"}`}>
            {up ? "+" : ""}
            {diffPct.toFixed(2)}%
          </span>
        </p>
      </div>
    );
  };

  return (
    <div
      className={`relative flex flex-col justify-between overflow-hidden rounded-2xl border-2 bg-white dark:bg-zinc-950/90 p-5 shadow-sm transition-all ${borderClass}`}
    >
      {/* Top header */}
      <div className={`flex flex-wrap items-start justify-between gap-3 mb-4 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
        <div className={isAr ? "text-right" : "text-left"}>
          <div className={`flex items-center gap-2 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
            <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-black font-mono uppercase tracking-wider ${badgeClass}`}>
              {symbol}
            </span>
            <h4 className="text-base font-black text-zinc-950 dark:text-white">
              {isAr ? titleAr : titleEn}
            </h4>
          </div>
          <p className="text-[11px] font-semibold text-zinc-500 dark:text-zinc-400 mt-0.5">
            {isAr ? subtitleAr : subtitleEn}
          </p>
        </div>

        <div className={isAr ? "text-left" : "text-right"}>
          <div className="flex items-baseline gap-1 font-mono justify-end">
            <span className="text-2xl font-black text-zinc-950 dark:text-white leading-none">
              {metrics.last > 0
                ? `$${metrics.last.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : "—"}
            </span>
            <span className="text-[10px] font-bold text-zinc-500">USD/oz</span>
          </div>
          <div className="flex items-center justify-end gap-2 mt-1.5 font-mono text-xs">
            {points.length > 0 ? (
              <>
                <span className={`inline-flex items-center font-black ${isUp ? "text-emerald-500" : "text-rose-500"}`}>
                  {isUp ? "+" : ""}
                  {metrics.dayChangePct.toFixed(2)}%
                  {isUp ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                </span>
                <span className="text-zinc-300 dark:text-zinc-700">|</span>
                <span className={`text-[11px] font-bold ${isPeriodUp ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                  {rangeLabel}: {isPeriodUp ? "+" : ""}
                  {metrics.periodChangePct.toFixed(1)}%
                </span>
              </>
            ) : (
              <span className="text-zinc-400 dark:text-zinc-500">—</span>
            )}
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="h-[210px] w-full" dir="ltr">
        {points.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={accentColor} stopOpacity={0.32} />
                  <stop offset="95%" stopColor={accentColor} stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-black/[0.06] dark:text-white/[0.04]" />
              <XAxis
                dataKey="date"
                tickFormatter={formatDate}
                stroke="currentColor"
                className="text-zinc-500/70 dark:text-white/20"
                tick={{ fontSize: 10, fontFamily: "monospace" }}
                minTickGap={26}
              />
              <YAxis
                domain={["auto", "auto"]}
                stroke="currentColor"
                className="text-zinc-500/70 dark:text-white/20"
                tick={{ fontSize: 10, fontFamily: "monospace" }}
                orientation={isAr ? "left" : "right"}
                width={56}
                tickFormatter={(v: number) => `$${v >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 0 }) : v.toFixed(1)}`}
              />
              <Tooltip content={renderTooltip} />
              <Area
                type="monotone"
                dataKey="close"
                stroke={accentColor}
                strokeWidth={2.5}
                fillOpacity={1}
                fill={`url(#${gradientId})`}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-xs font-mono text-zinc-500">
            {isAr ? "لا توجد بيانات شارت متاحة حالياً" : "Chart data temporarily unavailable"}
          </div>
        )}
      </div>

      {/* Footer stats & quick actions */}
      <div className={`mt-4 pt-3 border-t border-zinc-200/80 dark:border-white/10 flex flex-wrap items-center justify-between gap-2 text-[11px] ${isAr ? "flex-row-reverse" : "flex-row"}`}>
        <div className="flex items-center gap-3 font-mono text-zinc-600 dark:text-zinc-400">
          <span>
            {isAr ? "الأعلى:" : "H:"}{" "}
            <strong className="text-zinc-900 dark:text-zinc-200">
              {points.length > 0 && metrics.periodHigh > 0
                ? `$${metrics.periodHigh.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                : "—"}
            </strong>
          </span>
          <span>
            {isAr ? "الأدنى:" : "L:"}{" "}
            <strong className="text-zinc-900 dark:text-zinc-200">
              {points.length > 0 && metrics.periodLow > 0
                ? `$${metrics.periodLow.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                : "—"}
            </strong>
          </span>
          {metrics.lastDate && (
            <span className="hidden sm:inline text-zinc-400 dark:text-zinc-500">
              ({metrics.lastDate})
            </span>
          )}
        </div>

        <div className={`flex items-center gap-2 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
          <button
            type="button"
            onClick={() => {
              window.dispatchEvent(
                new CustomEvent("open-chat-with-message", {
                  detail: isAr ? aiPromptAr : aiPromptEn,
                }),
              );
            }}
            className="inline-flex items-center gap-1 rounded-lg border border-amber-400/50 bg-amber-400/10 hover:bg-amber-400/20 px-2.5 py-1 text-[11px] font-bold text-amber-700 dark:text-amber-300 transition"
          >
            <Sparkles className="w-3 h-3" />
            <span>{isAr ? "تحليل AI" : "Ask AI"}</span>
          </button>
          <Link
            href={`/stocks/${symbol}`}
            className="inline-flex items-center gap-1 rounded-lg border border-zinc-200 dark:border-white/15 bg-zinc-50 dark:bg-white/5 hover:bg-zinc-100 dark:hover:bg-white/10 px-2.5 py-1 text-[11px] font-bold text-zinc-700 dark:text-zinc-200 transition"
            prefetch={false}
          >
            <span>{isAr ? "التفاصيل" : "Details"}</span>
            <ExternalLink className="w-3 h-3" />
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function GlobalMetalsCharts({
  gold,
  silver,
  isAr,
}: {
  gold?: MetalPoint[];
  silver?: MetalPoint[];
  isAr: boolean;
}) {
  const [range, setRange] = useState<MetalRange>("3M");

  const slicedGold = useMemo(() => {
    const arr = Array.isArray(gold) ? gold : [];
    const n = RANGE_POINTS[range];
    return arr.length > n ? arr.slice(-n) : arr;
  }, [gold, range]);

  const slicedSilver = useMemo(() => {
    const arr = Array.isArray(silver) ? silver : [];
    const n = RANGE_POINTS[range];
    return arr.length > n ? arr.slice(-n) : arr;
  }, [silver, range]);

  const rangeLabel = isAr ? RANGE_LABELS[range].ar : RANGE_LABELS[range].en;

  return (
    <section
      aria-label={isAr ? "الذهب والفضة العالميان" : "Global Gold & Silver"}
      className="border-4 border-black dark:border-white bg-gradient-to-br from-amber-50/60 via-white to-slate-50/70 dark:from-amber-950/15 dark:via-zinc-950 dark:to-slate-950/40 p-5 sm:p-6 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.15)] mb-10"
    >
      <div className={`flex flex-wrap items-center justify-between gap-4 mb-5 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
        <div className={isAr ? "text-right" : "text-left"}>
          <div className={`flex flex-wrap items-center gap-2 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
            <span className="inline-flex items-center rounded-md border border-amber-500/40 bg-amber-500/15 px-2 py-0.5 text-[10px] font-black text-amber-700 dark:text-amber-300">
              {isAr ? "ثابت في الأسواق الـ 4 · مصر · السعودية · الإمارات · قطر" : "Pinned Across All 4 Markets · EGX · TASI · UAE · QSE"}
            </span>
          </div>
          <h3 className="text-lg sm:text-xl font-black text-zinc-950 dark:text-white mt-1.5">
            {isAr ? "🥇 الذهب والفضة العالميان (XAUUSD & XAGUSD)" : "🥇 Global Gold & Silver (XAUUSD & XAGUSD)"}
          </h3>
          <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400 mt-0.5">
            {isAr
              ? "حركة الأونصة العالمية بالدولار كمؤشر تحوط وملاذ آمن موازٍ لجميع الأسواق العربية"
              : "Global spot/futures ounce trend in USD as a safe-haven benchmark alongside all 4 Arab markets"}
          </p>
        </div>

        <div className={`flex flex-wrap items-center gap-2 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
          <div className="inline-flex rounded-xl border border-zinc-300 dark:border-white/15 bg-white dark:bg-zinc-900 p-1">
            {(["1M", "3M", "6M", "1Y"] as MetalRange[]).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRange(r)}
                className={`px-2.5 py-1 rounded-lg text-xs font-black transition ${
                  range === r
                    ? "bg-amber-400 text-black shadow-sm"
                    : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-950 dark:hover:text-white"
                }`}
              >
                {isAr ? RANGE_LABELS[r].ar : RANGE_LABELS[r].en}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <MetalChartCard
          symbol="XAUUSD"
          titleAr="الذهب العالمي (أونصة)"
          titleEn="Global Gold (Ounce)"
          subtitleAr="سعر الأونصة الفوري/العقود الآجلة بالدولار الأمريكي"
          subtitleEn="Spot / Futures Ounce Price in USD"
          points={slicedGold}
          isAr={isAr}
          accentColor="#F59E0B"
          gradientId="goldMetalGrad"
          badgeClass="bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30"
          borderClass="border-amber-400/50 dark:border-amber-400/35"
          aiPromptAr="حلل سعر الذهب العالمي (XAUUSD) فنياً الآن مع أهم مستويات الدعم والمقاومة والاتجاه القادم."
          aiPromptEn="Analyze global Gold (XAUUSD) technically right now with key support, resistance, and trend outlook."
          rangeLabel={rangeLabel}
        />
        <MetalChartCard
          symbol="XAGUSD"
          titleAr="الفضة العالمية (أونصة)"
          titleEn="Global Silver (Ounce)"
          subtitleAr="سعر الأونصة الفوري/العقود الآجلة بالدولار الأمريكي"
          subtitleEn="Spot / Futures Ounce Price in USD"
          points={slicedSilver}
          isAr={isAr}
          accentColor="#64748B"
          gradientId="silverMetalGrad"
          badgeClass="bg-slate-500/15 text-slate-700 dark:text-slate-200 border border-slate-400/40"
          borderClass="border-slate-300 dark:border-slate-500/40"
          aiPromptAr="حلل سعر الفضة العالمية (XAGUSD) فنياً الآن مع أهم مستويات الدعم والمقاومة والاتجاه القادم."
          aiPromptEn="Analyze global Silver (XAGUSD) technically right now with key support, resistance, and trend outlook."
          rangeLabel={rangeLabel}
        />
      </div>
    </section>
  );
}
