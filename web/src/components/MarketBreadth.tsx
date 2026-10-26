"use client";

import React from "react";
import {
    Activity,
    TrendingUp,
    TrendingDown,
    BarChart3,
    Gauge,
    Droplets,
    Layers,
    Flame,
    ShieldCheck,
} from "lucide-react";

export interface LiquiditySectorItem {
    sector: string;
    sector_ar: string;
    turnover_million_egp: number;
    market_share_pct: number;
    weighted_change_pct: number;
    weighted_cmf_20: number;
    stocks_count: number;
    advancing: number;
    declining: number;
    top_stock_symbol: string;
    top_stock_name: string;
    top_stock_turnover_million_egp: number;
    top_stock_change_pct: number;
}

export interface LiquidityStockItem {
    symbol: string;
    name: string;
    sector: string;
    sector_ar: string;
    close: number;
    change_pct: number;
    turnover_million_egp: number;
    market_share_pct: number;
    r_vol: number;
    cmf_20: number;
    rsi_14: number;
}

export interface DailyLiquidityData {
    date: string;
    total_turnover_egp: number;
    total_turnover_million_egp: number;
    total_turnover_billion_egp: number;
    avg_20d_turnover_million_egp: number;
    turnover_vs_20d_ratio: number;
    turnover_vs_20d_pct: number;
    advancing_turnover_million_egp: number;
    advancing_turnover_pct: number;
    declining_turnover_million_egp: number;
    declining_turnover_pct: number;
    unchanged_turnover_million_egp: number;
    unchanged_turnover_pct: number;
    top5_concentration_pct: number;
    top10_concentration_pct: number;
    unusual_volume_surge_count: number;
    positive_cmf_count: number;
    negative_cmf_count: number;
    accumulation_count: number;
    strong_accumulation_count: number;
    distribution_count: number;
    strong_distribution_count: number;
    flow_verdict: "inflow" | "outflow" | "balanced";
    flow_verdict_ar: string;
    flow_verdict_en: string;
    daily_summary_ar: string;
    daily_summary_en: string;
    top_sectors: LiquiditySectorItem[];
    top_liquidity_stocks: LiquidityStockItem[];
}

export interface BreadthData {
    health_score: number;
    health_label: string;
    advancing: number;
    declining: number;
    unchanged: number;
    pct_above_ema50: number;
    pct_above_ema200: number;
    avg_rsi: number;
    volume_ratio: number;
    total_stocks: number;
    date: string;
    liquidity?: DailyLiquidityData;
}

/* ── Health Score Arc ─────────────────────────────────────── */
const HealthArc = ({ score }: { score: number }) => {
    const r = 54;
    const circ = 2 * Math.PI * r;
    const pct = Math.max(0, Math.min(100, score));
    const offset = circ - (pct / 100) * circ * 0.75; // 270° arc
    const color =
        pct >= 70 ? "#10b981" :
        pct >= 45 ? "#f59e0b" :
        "#ef4444";
    return (
        <svg viewBox="0 0 120 100" className="w-32 h-28 mx-auto">
            {/* background arc */}
            <circle
                cx={60} cy={60} r={r}
                fill="none" stroke="#27272a" strokeWidth={10}
                strokeDasharray={`${circ * 0.75} ${circ * 0.25}`}
                strokeDashoffset={0}
                strokeLinecap="round"
                transform="rotate(135 60 60)"
            />
            {/* progress arc */}
            <circle
                cx={60} cy={60} r={r}
                fill="none" stroke={color} strokeWidth={10}
                strokeDasharray={circ}
                strokeDashoffset={offset}
                strokeLinecap="round"
                transform="rotate(135 60 60)"
                className="transition-all duration-700 ease-out"
            />
            <text x={60} y={55} textAnchor="middle" className="fill-zinc-950 dark:fill-white text-2xl font-black" style={{ fontSize: 28 }}>{Math.round(pct)}</text>
            <text x={60} y={72} textAnchor="middle" className="fill-zinc-500 dark:fill-zinc-400 text-xs font-bold" style={{ fontSize: 10 }}>/ 100</text>
        </svg>
    );
};

/* ── Market Health Score Card ─────────────────────────────── */
export function MarketHealthScore({ data, isAr }: { data: BreadthData | null; isAr: boolean }) {
    if (!data) return null;

    const verdictMap: Record<string, { ar: string; en: string; cls: string }> = {
        strong:   { ar: "السوق في حالة قوة — فرصة جيدة للشراء", en: "Market is strong — good buying opportunity", cls: "text-emerald-600 dark:text-emerald-400" },
        moderate: { ar: "السوق متذبذب — كن حذراً واختر بعناية", en: "Market is mixed — be selective", cls: "text-amber-600 dark:text-amber-400" },
        weak:     { ar: "السوق ضعيف — تجنب الشراء وراقب فقط", en: "Market is weak — avoid buying, watch only", cls: "text-rose-600 dark:text-rose-400" },
    };
    const verdict = verdictMap[data.health_label] || verdictMap.moderate;

    return (
        <div className="border-2 border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,0.15)] p-5">
            <div className={`flex items-center gap-4 ${isAr ? "flex-row-reverse text-right" : "flex-row text-left"}`}>
                <div className="shrink-0">
                    <HealthArc score={data.health_score} />
                </div>
                <div className="flex-1 space-y-2">
                    <div className={`flex items-center gap-2 ${isAr ? "flex-row-reverse" : ""}`}>
                        <Gauge className="w-4 h-4 text-[#FFDC58]" />
                        <h3 className="text-sm font-black uppercase tracking-wider text-zinc-950 dark:text-white">
                            {isAr ? "مؤشر صحة السوق" : "Market Health Score"}
                        </h3>
                    </div>
                    <p className={`text-sm font-bold leading-relaxed ${verdict.cls}`}>
                        {isAr ? verdict.ar : verdict.en}
                    </p>
                    <p className="text-[10px] font-mono text-zinc-500">
                        {isAr ? `بناءً على تحليل ${data.total_stocks} سهم — ${data.date}` : `Based on ${data.total_stocks} stocks — ${data.date}`}
                    </p>
                </div>
            </div>
        </div>
    );
}

/* ── Market Breadth Strip ─────────────────────────────────── */
export function MarketBreadthStrip({ data, isAr }: { data: BreadthData | null; isAr: boolean }) {
    if (!data) return null;

    const metrics = [
        {
            icon: <TrendingUp className="w-4 h-4 text-emerald-500" />,
            label: isAr ? "صاعدة" : "Advancing",
            value: `${data.advancing}`,
            sub: `/ ${data.declining} ${isAr ? "هابطة" : "declining"}`,
            cls: data.advancing > data.declining ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400",
        },
        {
            icon: <Activity className="w-4 h-4 text-indigo-400" />,
            label: isAr ? "فوق EMA200" : "Above EMA200",
            value: `${data.pct_above_ema200.toFixed(0)}%`,
            sub: isAr ? "اتجاه صاعد" : "long-term uptrend",
            cls: data.pct_above_ema200 > 50 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400",
        },
        {
            icon: <BarChart3 className="w-4 h-4 text-amber-400" />,
            label: isAr ? "متوسط RSI" : "Avg RSI",
            value: `${data.avg_rsi.toFixed(0)}`,
            sub: data.avg_rsi > 60 ? (isAr ? "مشبع شراء" : "overbought zone") : data.avg_rsi < 40 ? (isAr ? "مشبع بيع" : "oversold zone") : (isAr ? "منطقة متوسطة" : "neutral zone"),
            cls: data.avg_rsi > 60 ? "text-rose-600 dark:text-rose-400" : data.avg_rsi < 40 ? "text-emerald-600 dark:text-emerald-400" : "text-zinc-950 dark:text-zinc-300",
        },
        {
            icon: <TrendingDown className="w-4 h-4 text-cyan-400" />,
            label: isAr ? "نشاط السيولة" : "Volume Activity",
            value: `${data.volume_ratio.toFixed(1)}x`,
            sub: data.volume_ratio > 1.5 ? (isAr ? "نشاط عالي" : "high activity") : data.volume_ratio < 0.7 ? (isAr ? "نشاط منخفض" : "low activity") : (isAr ? "نشاط عادي" : "normal"),
            cls: data.volume_ratio > 1.5 ? "text-emerald-600 dark:text-emerald-400" : data.volume_ratio < 0.7 ? "text-rose-600 dark:text-rose-400" : "text-zinc-950 dark:text-zinc-300",
        },
    ];

    return (
        <div className={`grid grid-cols-2 md:grid-cols-4 gap-2 ${isAr ? "direction-rtl" : ""}`}>
            {metrics.map((m, i) => (
                <div key={i} className="border-2 border-black dark:border-zinc-800 bg-white dark:bg-zinc-950/80 p-3 shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,0.1)]">
                    <div className={`flex items-center gap-1.5 mb-1.5 ${isAr ? "flex-row-reverse" : ""}`}>
                        {m.icon}
                        <span className="text-[9px] font-black uppercase tracking-wider text-zinc-500">{m.label}</span>
                    </div>
                    <div className={`text-lg font-mono font-black ${m.cls}`}>{m.value}</div>
                    <div className="text-[9px] font-semibold text-zinc-500 mt-0.5">{m.sub}</div>
                </div>
            ))}
        </div>
    );
}

/* ── Daily Market Liquidity Update Card ───────────────────── */
export function DailyLiquidityUpdateCard({ data, isAr }: { data: BreadthData | null; isAr: boolean }) {
    const liq = data?.liquidity;
    if (!liq) return null;

    const verdictStyles: Record<string, { badgeCls: string; dotCls: string }> = {
        inflow: {
            badgeCls: "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
            dotCls: "bg-emerald-500",
        },
        outflow: {
            badgeCls: "border-rose-500 bg-rose-500/10 text-rose-700 dark:text-rose-300",
            dotCls: "bg-rose-500",
        },
        balanced: {
            badgeCls: "border-amber-500 bg-amber-500/10 text-amber-700 dark:text-amber-300",
            dotCls: "bg-amber-500",
        },
    };
    const vStyle = verdictStyles[liq.flow_verdict] || verdictStyles.balanced;

    const advPct = Math.max(0, Math.min(100, liq.advancing_turnover_pct));
    const decPct = Math.max(0, Math.min(100, liq.declining_turnover_pct));
    const unchPct = Math.max(0, 100 - advPct - decPct);

    const sectors = Array.isArray(liq.top_sectors) ? liq.top_sectors.slice(0, 5) : [];
    const stocks = Array.isArray(liq.top_liquidity_stocks) ? liq.top_liquidity_stocks.slice(0, 6) : [];

    return (
        <section className="mb-10 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 sm:p-6 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.15)]">
            {/* Header */}
            <div className={`flex flex-col md:flex-row md:items-center justify-between gap-3 pb-4 border-b-2 border-black dark:border-zinc-800 ${isAr ? "md:flex-row-reverse text-right" : "md:flex-row text-left"}`}>
                <div className={`flex items-center gap-3 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                    <span className="flex items-center justify-center w-9 h-9 bg-[#FFDC58] text-black border-2 border-black shrink-0 shadow-[2px_2px_0px_rgba(0,0,0,1)]">
                        <Droplets className="w-5 h-5" />
                    </span>
                    <div>
                        <div className={`flex flex-wrap items-center gap-2 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                            <h3 className="text-base sm:text-lg font-black uppercase tracking-tight text-zinc-950 dark:text-white">
                                {isAr ? "تحديث السيولة اليومي للسوق ككل" : "Daily Market-Wide Liquidity Update"}
                            </h3>
                            <span className="font-mono text-[10px] font-black px-2 py-0.5 border border-black dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300">
                                {liq.date}
                            </span>
                        </div>
                        <p className="text-xs font-semibold text-zinc-500 dark:text-zinc-400 mt-0.5">
                            {isAr
                                ? "رصد يومي شامل لإجمالي قيم التداول، صافي اتجاه السيولة، تركز الأسهم القيادية، وتدفقات الأموال الذكية"
                                : "Daily overview of total market turnover, net liquidity direction, leader concentration, and smart money flow"}
                        </p>
                    </div>
                </div>

                <div className={`inline-flex items-center gap-2 px-3 py-1.5 border-2 font-black text-xs uppercase self-start md:self-auto ${vStyle.badgeCls} ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                    <span className={`w-2 h-2 rounded-full ${vStyle.dotCls}`} />
                    <span>{isAr ? liq.flow_verdict_ar : liq.flow_verdict_en}</span>
                </div>
            </div>

            {/* Narrative Summary Strip */}
            <div className={`mt-4 p-3.5 border-2 border-black/15 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/60 text-xs font-semibold leading-relaxed text-zinc-800 dark:text-zinc-200 ${isAr ? "text-right" : "text-left"}`}>
                {isAr ? liq.daily_summary_ar : liq.daily_summary_en}
            </div>

            {/* 4 Key Liquidity KPIs */}
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {/* 1. Total Turnover vs 20d Avg */}
                <div className={`border-2 border-black dark:border-zinc-800 bg-white dark:bg-zinc-950 p-3.5 shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,0.1)] ${isAr ? "text-right" : "text-left"}`}>
                    <div className={`flex items-center justify-between gap-2 mb-1.5 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                        <span className="text-[10px] font-black uppercase tracking-wider text-zinc-500">
                            {isAr ? "إجمالي سيولة السوق" : "Total Market Turnover"}
                        </span>
                        <Droplets className="w-4 h-4 text-indigo-500 shrink-0" />
                    </div>
                    <div className="text-xl font-mono font-black text-zinc-950 dark:text-white">
                        {liq.total_turnover_billion_egp.toFixed(2)}{" "}
                        <span className="text-xs font-bold text-zinc-500">{isAr ? "مليار ج.م" : "B EGP"}</span>
                    </div>
                    <div className="mt-1 flex items-center justify-between text-[10px] font-mono text-zinc-500">
                        <span>{liq.total_turnover_million_egp.toLocaleString("en-US")}M EGP</span>
                        <span className={`font-black ${liq.turnover_vs_20d_pct >= 100 ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}`}>
                            {liq.turnover_vs_20d_pct.toFixed(1)}% {isAr ? "من متوسط 20ي" : "of 20d avg"}
                        </span>
                    </div>
                </div>

                {/* 2. Advancing vs Declining Turnover Split */}
                <div className={`border-2 border-black dark:border-zinc-800 bg-white dark:bg-zinc-950 p-3.5 shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,0.1)] ${isAr ? "text-right" : "text-left"}`}>
                    <div className={`flex items-center justify-between gap-2 mb-1.5 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                        <span className="text-[10px] font-black uppercase tracking-wider text-zinc-500">
                            {isAr ? "ميزان سيولة الصاعد والهابط" : "Inflow vs Outflow Split"}
                        </span>
                        <Activity className="w-4 h-4 text-emerald-500 shrink-0" />
                    </div>
                    <div className="flex items-center justify-between text-xs font-mono font-black mb-1.5">
                        <span className="text-emerald-600 dark:text-emerald-400">
                            ↑ {liq.advancing_turnover_pct.toFixed(1)}% ({liq.advancing_turnover_million_egp.toFixed(0)}M)
                        </span>
                        <span className="text-rose-600 dark:text-rose-400">
                            ↓ {liq.declining_turnover_pct.toFixed(1)}% ({liq.declining_turnover_million_egp.toFixed(0)}M)
                        </span>
                    </div>
                    <div className="h-2.5 w-full flex overflow-hidden border border-black dark:border-zinc-700 bg-zinc-200 dark:bg-zinc-800" dir="ltr">
                        <div className="bg-emerald-500 h-full" style={{ width: `${advPct}%` }} title={`Advancing: ${advPct}%`} />
                        {unchPct > 0 && <div className="bg-zinc-400 h-full" style={{ width: `${unchPct}%` }} title={`Unchanged: ${unchPct.toFixed(1)}%`} />}
                        <div className="bg-rose-500 h-full" style={{ width: `${decPct}%` }} title={`Declining: ${decPct}%`} />
                    </div>
                    <div className="mt-1 text-[10px] font-semibold text-zinc-500">
                        {advPct >= decPct
                            ? (isAr ? "السيولة تميل للأسهم الصاعدة" : "Liquidity favors advancing stocks")
                            : (isAr ? "السيولة متركزة في الأسهم الهابطة" : "Liquidity skewed toward declining stocks")}
                    </div>
                </div>

                {/* 3. Concentration & Volume Surges */}
                <div className={`border-2 border-black dark:border-zinc-800 bg-white dark:bg-zinc-950 p-3.5 shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,0.1)] ${isAr ? "text-right" : "text-left"}`}>
                    <div className={`flex items-center justify-between gap-2 mb-1.5 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                        <span className="text-[10px] font-black uppercase tracking-wider text-zinc-500">
                            {isAr ? "تركز السيولة والانفجار الحجمي" : "Concentration & R.Vol Surges"}
                        </span>
                        <Flame className="w-4 h-4 text-amber-500 shrink-0" />
                    </div>
                    <div className="flex items-baseline justify-between gap-2">
                        <div>
                            <span className="text-lg font-mono font-black text-zinc-950 dark:text-white">{liq.top5_concentration_pct.toFixed(1)}%</span>
                            <span className="block text-[9px] font-semibold text-zinc-500">{isAr ? "حصة أعلى 5 أسهم" : "Top 5 stocks share"}</span>
                        </div>
                        <div>
                            <span className="text-lg font-mono font-black text-zinc-950 dark:text-white">{liq.top10_concentration_pct.toFixed(1)}%</span>
                            <span className="block text-[9px] font-semibold text-zinc-500">{isAr ? "حصة أعلى 10 أسهم" : "Top 10 stocks share"}</span>
                        </div>
                        <div>
                            <span className="text-lg font-mono font-black text-amber-600 dark:text-amber-400">{liq.unusual_volume_surge_count}</span>
                            <span className="block text-[9px] font-semibold text-zinc-500">{isAr ? "انفجار حجمي ≥2x" : "R.Vol ≥ 2x"}</span>
                        </div>
                    </div>
                </div>

                {/* 4. Smart Money CMF & Wyckoff Bias */}
                <div className={`border-2 border-black dark:border-zinc-800 bg-white dark:bg-zinc-950 p-3.5 shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,0.1)] ${isAr ? "text-right" : "text-left"}`}>
                    <div className={`flex items-center justify-between gap-2 mb-1.5 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                        <span className="text-[10px] font-black uppercase tracking-wider text-zinc-500">
                            {isAr ? "الأموال الذكية (CMF & Wyckoff)" : "Smart Money (CMF & Wyckoff)"}
                        </span>
                        <ShieldCheck className="w-4 h-4 text-cyan-500 shrink-0" />
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                        <div className="p-1.5 bg-emerald-500/10 border border-emerald-500/20">
                            <span className="block text-[9px] font-sans font-bold text-zinc-500">{isAr ? "تجميع / CMF+" : "Accum / CMF+"}</span>
                            <span className="font-black text-emerald-600 dark:text-emerald-400">
                                {liq.accumulation_count} / {liq.positive_cmf_count}
                            </span>
                        </div>
                        <div className="p-1.5 bg-rose-500/10 border border-rose-500/20">
                            <span className="block text-[9px] font-sans font-bold text-zinc-500">{isAr ? "تصريف / CMF-" : "Distrib / CMF-"}</span>
                            <span className="font-black text-rose-600 dark:text-rose-400">
                                {liq.distribution_count} / {liq.negative_cmf_count}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Top Sectors & Top Liquidity Stocks Tables */}
            <div className="mt-5 grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Top Sectors by Liquidity */}
                <div className="border-2 border-black dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden">
                    <div className={`flex items-center justify-between px-4 py-2.5 bg-zinc-100 dark:bg-zinc-900 border-b-2 border-black dark:border-zinc-800 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                        <div className={`flex items-center gap-2 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                            <Layers className="w-4 h-4 text-indigo-500" />
                            <span className="text-[11px] font-black uppercase tracking-wider text-zinc-950 dark:text-white">
                                {isAr ? "أعلى القطاعات جذباً للسيولة اليوم" : "Top Sectors by Liquidity Today"}
                            </span>
                        </div>
                        <span className="text-[10px] font-mono font-bold text-zinc-500">
                            {isAr ? "الحصة · التغير · القائد" : "Share · Change · Leader"}
                        </span>
                    </div>
                    <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
                        {sectors.map((sec, idx) => {
                            const up = sec.weighted_change_pct >= 0;
                            const cmfPositive = sec.weighted_cmf_20 >= 0;
                            return (
                                <div
                                    key={sec.sector}
                                    className={`flex items-center justify-between gap-2 px-4 py-2.5 hover:bg-zinc-50 dark:hover:bg-zinc-900/50 ${isAr ? "flex-row-reverse text-right" : "flex-row text-left"}`}
                                >
                                    <div className={`flex items-center gap-2 min-w-0 flex-1 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                                        <span className="text-[10px] font-mono font-black text-zinc-400 w-4">{idx + 1}</span>
                                        <div className="min-w-0 flex-1">
                                            <div className="text-xs font-black text-zinc-950 dark:text-white truncate">
                                                {isAr ? sec.sector_ar : sec.sector}
                                            </div>
                                            <div className="text-[10px] font-mono text-zinc-500 truncate">
                                                {isAr ? "القائد:" : "Leader:"}{" "}
                                                <a href={`/stocks/${sec.top_stock_symbol.toLowerCase()}`} className="font-bold text-indigo-500 hover:underline">
                                                    {sec.top_stock_symbol}
                                                </a>{" "}
                                                ({sec.top_stock_turnover_million_egp.toFixed(0)}M) · CMF {sec.weighted_cmf_20 >= 0 ? "+" : ""}{sec.weighted_cmf_20.toFixed(2)}
                                            </div>
                                        </div>
                                    </div>
                                    <div className={`flex items-center gap-3 font-mono shrink-0 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                                        <div className={isAr ? "text-left" : "text-right"}>
                                            <div className="text-xs font-black text-zinc-950 dark:text-zinc-200">
                                                {sec.turnover_million_egp.toFixed(0)}M
                                            </div>
                                            <div className={`text-[9px] font-bold ${cmfPositive ? "text-emerald-600 dark:text-emerald-400" : "text-zinc-500"}`}>
                                                {sec.market_share_pct.toFixed(1)}%
                                            </div>
                                        </div>
                                        <span className={`text-xs font-black min-w-[54px] ${up ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"} ${isAr ? "text-left" : "text-right"}`}>
                                            {up ? "+" : ""}{sec.weighted_change_pct.toFixed(2)}%
                                        </span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Top Stocks by Turnover */}
                <div className="border-2 border-black dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden">
                    <div className={`flex items-center justify-between px-4 py-2.5 bg-zinc-100 dark:bg-zinc-900 border-b-2 border-black dark:border-zinc-800 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                        <div className={`flex items-center gap-2 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                            <Droplets className="w-4 h-4 text-emerald-500" />
                            <span className="text-[11px] font-black uppercase tracking-wider text-zinc-950 dark:text-white">
                                {isAr ? "أعلى الأسهم استحواذاً على السيولة اليوم" : "Top Stocks by Liquidity Turnover"}
                            </span>
                        </div>
                        <span className="text-[10px] font-mono font-bold text-zinc-500">
                            {isAr ? "السيولة · الحصة · التغير" : "Turnover · Share · Change"}
                        </span>
                    </div>
                    <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
                        {stocks.map((st, idx) => {
                            const up = st.change_pct >= 0;
                            return (
                                <a
                                    key={st.symbol}
                                    href={`/stocks/${st.symbol.toLowerCase()}`}
                                    className={`flex items-center justify-between gap-2 px-4 py-2.5 hover:bg-zinc-50 dark:hover:bg-zinc-900/50 transition-colors ${isAr ? "flex-row-reverse text-right" : "flex-row text-left"}`}
                                >
                                    <div className={`flex items-center gap-2 min-w-0 flex-1 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                                        <span className="text-[10px] font-mono font-black text-zinc-400 w-4">{idx + 1}</span>
                                        <div className="min-w-0 flex-1">
                                            <div className={`flex items-center gap-1.5 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                                                <span className="text-xs font-black text-indigo-500">{st.symbol}</span>
                                                <span className="text-[10px] font-semibold text-zinc-500 truncate">{st.name}</span>
                                            </div>
                                            <div className="text-[9px] font-mono text-zinc-500">
                                                {st.close.toFixed(2)} EGP · R.Vol {st.r_vol.toFixed(1)}x · CMF {st.cmf_20 >= 0 ? "+" : ""}{st.cmf_20.toFixed(2)}
                                            </div>
                                        </div>
                                    </div>
                                    <div className={`flex items-center gap-3 font-mono shrink-0 ${isAr ? "flex-row-reverse" : "flex-row"}`}>
                                        <div className={isAr ? "text-left" : "text-right"}>
                                            <div className="text-xs font-black text-zinc-950 dark:text-zinc-200">
                                                {st.turnover_million_egp.toFixed(1)}M
                                            </div>
                                            <div className="text-[9px] font-bold text-zinc-500">
                                                {st.market_share_pct.toFixed(1)}%
                                            </div>
                                        </div>
                                        <span className={`text-xs font-black min-w-[54px] ${up ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"} ${isAr ? "text-left" : "text-right"}`}>
                                            {up ? "+" : ""}{st.change_pct.toFixed(2)}%
                                        </span>
                                    </div>
                                </a>
                            );
                        })}
                    </div>
                </div>
            </div>
        </section>
    );
}

/* ── Top Movers ───────────────────────────────────────────── */
interface Mover {
    symbol: string;
    name: string;
    change_pct: number;
    close: number;
    volume: number;
    rsi_14: number;
}

export function TopMovers({ gainers = [], losers = [], isAr }: { gainers?: Mover[]; losers?: Mover[]; isAr: boolean }) {
    const safeGainers = Array.isArray(gainers) ? gainers : [];
    const safeLosers = Array.isArray(losers) ? losers : [];
    if (!safeGainers.length && !safeLosers.length) return null;

    const renderTable = (items: Mover[], type: "gain" | "loss") => {
        const color = type === "gain" ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400";
        const headerBg = type === "gain" ? "bg-emerald-500/10" : "bg-rose-500/10";
        const icon = type === "gain"
            ? <TrendingUp className="w-4 h-4 text-emerald-500" />
            : <TrendingDown className="w-4 h-4 text-rose-500" />;
        const title = type === "gain"
            ? (isAr ? "أقوى 5 أسهم ↑" : "Top 5 Gainers ↑")
            : (isAr ? "أضعف 5 أسهم ↓" : "Top 5 Losers ↓");

        return (
            <div className="border-2 border-black dark:border-zinc-800 bg-white dark:bg-zinc-950 shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,0.1)] overflow-hidden">
                <div className={`flex items-center gap-2 px-4 py-2.5 ${headerBg} ${isAr ? "flex-row-reverse" : ""}`}>
                    {icon}
                    <span className="text-[10px] font-black uppercase tracking-wider text-zinc-950 dark:text-white">{title}</span>
                </div>
                <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
                    {items.map((m, i) => (
                        <a
                            key={m.symbol}
                            href={`/stocks/${m.symbol.toLowerCase()}`}
                            className={`flex items-center px-4 py-2.5 hover:bg-zinc-50 dark:hover:bg-zinc-900/50 transition-colors ${isAr ? "flex-row-reverse text-right" : "text-left"}`}
                        >
                            <span className="text-[10px] font-mono font-black text-zinc-500 w-5">{i + 1}</span>
                            <div className={`flex-1 min-w-0 ${isAr ? "mr-2" : "ml-2"}`}>
                                <div className="text-xs font-black text-indigo-500 truncate">{m.symbol}</div>
                                <div className="text-[9px] text-zinc-500 font-semibold truncate">{m.name || m.symbol}</div>
                            </div>
                            <div className={`text-right ${isAr ? "ml-3" : "mr-3"}`}>
                                <div className="text-xs font-mono font-bold text-zinc-950 dark:text-zinc-300">{m.close.toFixed(2)}</div>
                                <div className="text-[9px] font-mono text-zinc-500">RSI {m.rsi_14?.toFixed(0) || "—"}</div>
                            </div>
                            <div className={`font-mono font-black text-sm ${color} min-w-[60px] ${isAr ? "text-left" : "text-right"}`}>
                                {m.change_pct >= 0 ? "+" : ""}{m.change_pct.toFixed(2)}%
                            </div>
                        </a>
                    ))}
                    {items.length === 0 && (
                        <div className="px-4 py-6 text-center text-[10px] font-mono text-zinc-500">
                            {isAr ? "لا توجد بيانات" : "No data available"}
                        </div>
                    )}
                </div>
            </div>
        );
    };

    return (
        <div className="space-y-3">
            <div className={`flex items-center gap-2 ${isAr ? "flex-row-reverse" : ""}`}>
                <Activity className="w-5 h-5 text-[#FFDC58]" />
                <h3 className="text-sm font-black uppercase tracking-wider text-zinc-950 dark:text-white">
                    {isAr ? "أقوى وأضعف الأسهم اليوم" : "Today's Top Movers"}
                </h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {renderTable(gainers, "gain")}
                {renderTable(losers, "loss")}
            </div>
        </div>
    );
}
