"use client";

import React, { useMemo, useState } from "react";
import { Activity, AlertTriangle, Award, BarChart3, Briefcase, Clock, Compass, Eye, EyeOff, Flame, HelpCircle, Scale, ShieldCheck, Target, TrendingUp } from "lucide-react";
import type { ChatTable } from "@/contexts/ChatContext";

export type ChatVisualsPayload = NonNullable<ChatTable["visuals"]>;

export interface StockChartPoint {
    d: string;
    c: number;
    v?: number | null;
}

export interface StockChartSeries {
    series: StockChartPoint[];
    ema50?: number | null;
    support1?: number | null;
    resistance1?: number | null;
}

interface PriceLadderProps {
    price?: number;
    stopLoss?: number;
    support1?: number;
    support2?: number;
    resistance1?: number;
    target1?: number;
    target2?: number;
    currency?: string;
}

interface LadderMarker {
    id: string;
    label: string;
    shortVal: string;
    val: number;
    color: string;
    pct: number;
    tier: "stop" | "support" | "current" | "target";
}

function fmtCoord(v: number): string {
    return v >= 100 ? v.toFixed(1) : v.toFixed(2);
}

/**
 * Interactive SVG horizontal Price Ladder showing Stop Loss, Support, Current Price, and Targets
 * with live Risk:Reward ratio calculation and scenario switching (Current/Support vs Breakout).
 */
export function PriceLadderSvg({
    price,
    stopLoss,
    support1,
    support2,
    resistance1,
    target1,
    target2,
    currency = "ج.م",
}: PriceLadderProps) {
    const [scenario, setScenario] = useState<"current" | "breakout">("current");

    const curPrice = typeof price === "number" && Number.isFinite(price) && price > 0 ? price : undefined;
    const primaryTarget = target1 ?? resistance1;
    const primaryStop = stopLoss ?? support2 ?? support1;

    const canSwitchBreakout = Boolean(
        curPrice &&
            resistance1 &&
            resistance1 > curPrice &&
            ((target2 && target2 > resistance1) || (resistance1 > curPrice * 1.01))
    );

    const effectiveEntry =
        scenario === "breakout" && resistance1
            ? resistance1
            : curPrice ?? support1;
    const effectiveStop =
        scenario === "breakout" && resistance1 && curPrice
            ? Number((resistance1 * 0.965).toFixed(2))
            : primaryStop;
    const effectiveTarget =
        scenario === "breakout" && resistance1
            ? (target2 && target2 > resistance1 ? target2 : Number((resistance1 * 1.08).toFixed(2)))
            : primaryTarget;

    const markers = useMemo<LadderMarker[]>(() => {
        const raw: Array<Omit<LadderMarker, "pct">> = [];
        if (effectiveStop && effectiveStop > 0) {
            raw.push({
                id: "stop",
                label: scenario === "breakout" ? "وقف الاختراق" : "وقف/دعم",
                shortVal: `SL:${fmtCoord(effectiveStop)}`,
                val: effectiveStop,
                color: "#f43f5e",
                tier: "stop",
            });
        }
        if (scenario === "current" && support1 && support1 > 0 && (!effectiveStop || Math.abs(support1 - effectiveStop) > 0.01)) {
            raw.push({
                id: "s1",
                label: "دعم 1",
                shortVal: `د1:${fmtCoord(support1)}`,
                val: support1,
                color: "#f59e0b",
                tier: "support",
            });
        }
        if (curPrice && curPrice > 0) {
            raw.push({
                id: "cur",
                label: scenario === "breakout" ? "السعر الآن" : "الحالي",
                shortVal: `الآن:${fmtCoord(curPrice)}`,
                val: curPrice,
                color: "#0ea5e9",
                tier: "current",
            });
        }
        if (scenario === "breakout" && effectiveEntry && effectiveEntry > 0) {
            raw.push({
                id: "breakout_entry",
                label: "دخول الاختراق",
                shortVal: `دخول:${fmtCoord(effectiveEntry)}`,
                val: effectiveEntry,
                color: "#f59e0b",
                tier: "support",
            });
        }
        if (effectiveTarget && effectiveTarget > 0) {
            raw.push({
                id: "t1",
                label: scenario === "breakout" ? "هدف الاختراق" : (target1 ? "هدف 1" : "مقاومة 1"),
                shortVal: `${target1 ? "هـ1" : "م1"}:${fmtCoord(effectiveTarget)}`,
                val: effectiveTarget,
                color: "#10b981",
                tier: "target",
            });
        }
        if (scenario === "current" && target2 && target2 > 0 && (!effectiveTarget || target2 > effectiveTarget * 1.005)) {
            raw.push({
                id: "t2",
                label: "هدف 2",
                shortVal: `هـ2:${fmtCoord(target2)}`,
                val: target2,
                color: "#06b6d4",
                tier: "target",
            });
        }

        if (raw.length < 2) return [];
        raw.sort((a, b) => a.val - b.val);
        const minV = raw[0].val;
        const maxV = raw[raw.length - 1].val;
        const span = maxV - minV;

        const positioned = raw.map((m, i) => ({
            ...m,
            pct: span > 1e-6 ? 10 + ((m.val - minV) / span) * 80 : 18 + (i / Math.max(1, raw.length - 1)) * 64,
        }));

        // Enforce minimum 14% horizontal gap between adjacent markers to prevent text collision
        for (let i = 1; i < positioned.length; i++) {
            if (positioned[i].pct - positioned[i - 1].pct < 14) {
                positioned[i].pct = Math.min(92, positioned[i - 1].pct + 14);
            }
        }
        return positioned;
    }, [curPrice, effectiveEntry, effectiveStop, effectiveTarget, scenario, support1, target1, target2]);

    if (markers.length < 2) return null;

    const rrCalc = (() => {
        if (!effectiveEntry || !effectiveStop || !effectiveTarget) return null;
        const risk = Math.abs(effectiveEntry - effectiveStop);
        const reward = Math.abs(effectiveTarget - effectiveEntry);
        if (risk <= 1e-6 || reward <= 0) return null;
        return (reward / risk).toFixed(1);
    })();

    const stopMarker = markers.find((m) => m.id === "stop");
    const entryOrCurMarker =
        scenario === "breakout"
            ? markers.find((m) => m.id === "breakout_entry") ?? markers.find((m) => m.id === "cur") ?? markers[0]
            : markers.find((m) => m.id === "cur") ?? markers.find((m) => m.id === "s1");
    const targetMarker = markers.find((m) => m.id === "t1") ?? markers[markers.length - 1];

    const toSvgX = (pct: number) => (pct / 100) * 600;
    const riskX1 = stopMarker ? toSvgX(stopMarker.pct) : toSvgX(10);
    const riskX2 = entryOrCurMarker ? toSvgX(entryOrCurMarker.pct) : riskX1;
    const rewardX1 = entryOrCurMarker ? toSvgX(entryOrCurMarker.pct) : toSvgX(50);
    const rewardX2 = targetMarker ? toSvgX(targetMarker.pct) : rewardX1;

    return (
        <div
            className="mt-2.5 sm:mt-3 p-2.5 sm:p-3 rounded-xl sm:rounded-2xl bg-zinc-50 dark:bg-zinc-900/60 border border-zinc-200 dark:border-white/10 relative z-10"
            data-testid="price-ladder-svg"
        >
            <div className="flex flex-wrap items-center justify-between gap-1.5 mb-1.5">
                <div className="flex items-center gap-1.5 text-[10px] sm:text-[11px] font-black text-zinc-700 dark:text-zinc-200">
                    <Scale className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                    <span>مسطرة السعر وخطة المخاطرة</span>
                    {rrCalc && (
                        <span
                            dir="ltr"
                            className="px-1.5 py-0.5 rounded-md bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30 font-mono text-[10px]"
                        >
                            R:R 1:{rrCalc}
                        </span>
                    )}
                </div>

                {canSwitchBreakout && (
                    <div className="flex items-center gap-1 text-[10px] font-bold">
                        <button
                            type="button"
                            onClick={() => setScenario("current")}
                            className={`px-2 py-0.5 rounded-md border transition cursor-pointer ${
                                scenario === "current"
                                    ? "bg-amber-500/20 text-amber-800 dark:text-amber-300 border-amber-500/50"
                                    : "bg-transparent text-zinc-500 border-zinc-300 dark:border-white/15"
                            }`}
                        >
                            السيناريو الحالي
                        </button>
                        <button
                            type="button"
                            onClick={() => setScenario("breakout")}
                            className={`px-2 py-0.5 rounded-md border transition cursor-pointer ${
                                scenario === "breakout"
                                    ? "bg-sky-500/20 text-sky-700 dark:text-sky-300 border-sky-500/50"
                                    : "bg-transparent text-zinc-500 border-zinc-300 dark:border-white/15"
                            }`}
                        >
                            اختراق {fmtCoord(resistance1!)} {currency}
                        </button>
                    </div>
                )}
            </div>

            <svg viewBox="0 0 600 96" className="w-full h-24 select-none overflow-visible" aria-label="خريطة مستويات السهم">
                {/* Base Axis */}
                <line x1="50" y1="48" x2="550" y2="48" stroke="currentColor" strokeOpacity="0.18" strokeWidth="3" strokeLinecap="round" />

                {/* Risk Range Bar */}
                {riskX2 > riskX1 && (
                    <rect
                        x={riskX1}
                        y="41"
                        width={Math.max(4, riskX2 - riskX1)}
                        height="14"
                        rx="4"
                        fill="#f43f5e"
                        fillOpacity="0.22"
                        stroke="#f43f5e"
                        strokeOpacity="0.5"
                    />
                )}

                {/* Reward Range Bar */}
                {rewardX2 > rewardX1 && (
                    <rect
                        x={rewardX1}
                        y="41"
                        width={Math.max(4, rewardX2 - rewardX1)}
                        height="14"
                        rx="4"
                        fill="#10b981"
                        fillOpacity="0.24"
                        stroke="#10b981"
                        strokeOpacity="0.55"
                    />
                )}

                {/* Markers */}
                {markers.map((m, idx) => {
                    const cx = toSvgX(m.pct);
                    const topY = idx % 2 === 0 ? 18 : 26;
                    const botY = idx % 2 === 0 ? 78 : 89;
                    return (
                        <g key={m.id}>
                            {m.tier === "current" && (
                                <circle cx={cx} cy="48" r="10" fill={m.color} fillOpacity="0.22" />
                            )}
                            <circle
                                cx={cx}
                                cy="48"
                                r={m.tier === "current" ? 6 : 5}
                                fill={m.color}
                                stroke="#09090b"
                                strokeWidth="1.5"
                            />
                            <text
                                x={cx}
                                y={topY}
                                textAnchor="middle"
                                fill={m.color}
                                fontSize="11"
                                fontWeight="700"
                            >
                                {m.label}
                            </text>
                            <text
                                x={cx}
                                y={botY}
                                textAnchor="middle"
                                fill="currentColor"
                                fontSize="10.5"
                                fontWeight="700"
                                fontFamily="monospace"
                            >
                                {m.shortVal}
                            </text>
                        </g>
                    );
                })}
            </svg>
        </div>
    );
}

interface MiniPriceChartProps {
    chartData: StockChartSeries;
    currency?: string;
    symbol: string;
    support1?: number;
    resistance1?: number;
}

/**
 * Pure client-side SVG 30-session price & volume mini-chart with interactive hover inspection
 * and optional EMA50 + Support/Resistance overlays. Zero server/Vercel overhead.
 */
export function MiniPriceChartSvg({
    chartData,
    currency = "ج.م",
    symbol,
    support1,
    resistance1,
}: MiniPriceChartProps) {
    const [showZones, setShowZones] = useState(true);
    const [showEma, setShowEma] = useState(true);
    const [hoverIdx, setHoverIdx] = useState<number | null>(null);

    const pts = chartData?.series || [];
    if (pts.length < 3) return null;

    const emaVal = typeof chartData.ema50 === "number" && chartData.ema50 > 0 ? chartData.ema50 : undefined;
    const s1Val = support1 ?? (typeof chartData.support1 === "number" ? chartData.support1 : undefined);
    const r1Val = resistance1 ?? (typeof chartData.resistance1 === "number" ? chartData.resistance1 : undefined);

    const closes = pts.map((p) => p.c);
    const rawMin = Math.min(...closes);
    const rawMax = Math.max(...closes);
    const rawSpan = Math.max(rawMax - rawMin, rawMax * 0.01 || 1);

    // Only expand domain for overlays reasonably near the 30-day trading range so outliers don't squash candles
    const domainCandidates = [...closes];
    const inReasonableBand = (v?: number) =>
        v !== undefined && Number.isFinite(v) && v > 0 && v >= rawMin - rawSpan * 0.65 && v <= rawMax + rawSpan * 0.65;
    if (showZones && inReasonableBand(s1Val)) domainCandidates.push(s1Val!);
    if (showZones && inReasonableBand(r1Val)) domainCandidates.push(r1Val!);
    if (showEma && inReasonableBand(emaVal)) domainCandidates.push(emaVal!);

    const minP = Math.min(...domainCandidates);
    const maxP = Math.max(...domainCandidates);
    const spanP = Math.max(maxP - minP, maxP * 0.01 || 1);
    const padMin = minP - spanP * 0.08;
    const padMax = maxP + spanP * 0.08;
    const ySpan = Math.max(padMax - padMin, 1e-6);

    const W = 580;
    const chartLeft = 18;
    const chartRight = 508;
    const chartTop = 14;
    const chartBottom = 114;
    const volBottom = 146;

    const toX = (idx: number) =>
        chartLeft + (idx / Math.max(1, pts.length - 1)) * (chartRight - chartLeft);
    const toY = (val: number) =>
        chartBottom - ((val - padMin) / ySpan) * (chartBottom - chartTop);

    const lineCoords = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.c).toFixed(1)}`);
    const polylinePoints = lineCoords.join(" ");
    const areaPath = `M ${toX(0).toFixed(1)},${chartBottom} L ${lineCoords.join(" L ")} L ${toX(pts.length - 1).toFixed(1)},${chartBottom} Z`;

    const isNetUp = pts[pts.length - 1].c >= pts[0].c;
    const strokeHex = isNetUp ? "#10b981" : "#f43f5e";
    const gradId = `miniChartGrad-${symbol.replace(/[^A-Za-z0-9_-]/g, "")}`;

    const vols = pts.map((p) => (typeof p.v === "number" && p.v > 0 ? p.v : 0));
    const maxVol = Math.max(...vols, 0);
    const barW = Math.max(4, Math.min(12, ((chartRight - chartLeft) / pts.length) * 0.62));

    const activeIdx = hoverIdx !== null && hoverIdx >= 0 && hoverIdx < pts.length ? hoverIdx : pts.length - 1;
    const activePt = pts[activeIdx];
    const periodPct = pts[0].c > 0 ? ((activePt.c - pts[0].c) / pts[0].c) * 100 : 0;

    return (
        <div
            className="rounded-xl border border-zinc-200 dark:border-white/10 bg-zinc-50 dark:bg-zinc-900/60 p-2.5 sm:p-3 space-y-2"
            data-testid="mini-price-chart"
        >
            <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] sm:text-xs">
                <div className="flex items-center gap-2 font-bold">
                    <span className="text-zinc-600 dark:text-zinc-300">{pts.length} جلسة:</span>
                    <span dir="ltr" className="font-mono text-zinc-900 dark:text-white">
                        {activePt.d} — {fmtCoord(activePt.c)} {currency}
                    </span>
                    <span
                        dir="ltr"
                        className={`font-mono px-1.5 py-0.5 rounded text-[10px] ${
                            periodPct >= 0
                                ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                                : "bg-rose-500/15 text-rose-700 dark:text-rose-400"
                        }`}
                    >
                        {periodPct >= 0 ? "+" : ""}{periodPct.toFixed(1)}%
                    </span>
                </div>

                <div className="flex items-center gap-2.5 text-[10px] font-bold">
                    {emaVal && (
                        <button
                            type="button"
                            onClick={() => setShowEma((v) => !v)}
                            className={`flex items-center gap-1 cursor-pointer ${showEma ? "text-amber-600 dark:text-amber-400" : "text-zinc-400 line-through"}`}
                        >
                            {showEma ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                            <span>EMA50</span>
                        </button>
                    )}
                    {(s1Val || r1Val) && (
                        <button
                            type="button"
                            onClick={() => setShowZones((v) => !v)}
                            className={`flex items-center gap-1 cursor-pointer ${showZones ? "text-emerald-600 dark:text-emerald-400" : "text-zinc-400 line-through"}`}
                        >
                            {showZones ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                            <span>دعم/مقاومة</span>
                        </button>
                    )}
                </div>
            </div>

            <svg
                viewBox={`0 0 ${W} 152`}
                className="w-full h-36 select-none"
                onMouseLeave={() => setHoverIdx(null)}
                onMouseMove={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    if (!rect.width) return;
                    const relX = ((e.clientX - rect.left) / rect.width) * W;
                    const norm = Math.max(0, Math.min(1, (relX - chartLeft) / (chartRight - chartLeft)));
                    setHoverIdx(Math.round(norm * (pts.length - 1)));
                }}
                aria-label={`ميني شارت ${symbol}`}
            >
                <defs>
                    <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={strokeHex} stopOpacity="0.28" />
                        <stop offset="100%" stopColor={strokeHex} stopOpacity="0.01" />
                    </linearGradient>
                </defs>

                {/* Support & Resistance Lines */}
                {showZones && inReasonableBand(r1Val) && (
                    <g>
                        <line x1={chartLeft} y1={toY(r1Val!)} x2={chartRight} y2={toY(r1Val!)} stroke="#f43f5e" strokeDasharray="4 3" strokeWidth="1.2" />
                        <text x={chartRight + 6} y={toY(r1Val!) + 3.5} fill="#f43f5e" fontSize="10" fontFamily="monospace" fontWeight="700">
                            R1 {fmtCoord(r1Val!)}
                        </text>
                    </g>
                )}
                {showZones && inReasonableBand(s1Val) && (
                    <g>
                        <line x1={chartLeft} y1={toY(s1Val!)} x2={chartRight} y2={toY(s1Val!)} stroke="#10b981" strokeDasharray="4 3" strokeWidth="1.2" />
                        <text x={chartRight + 6} y={toY(s1Val!) + 3.5} fill="#10b981" fontSize="10" fontFamily="monospace" fontWeight="700">
                            S1 {fmtCoord(s1Val!)}
                        </text>
                    </g>
                )}

                {/* EMA50 Reference Line */}
                {showEma && inReasonableBand(emaVal) && (
                    <g>
                        <line x1={chartLeft} y1={toY(emaVal!)} x2={chartRight} y2={toY(emaVal!)} stroke="#f59e0b" strokeDasharray="3 3" strokeWidth="1.4" />
                        <text x={chartRight + 6} y={toY(emaVal!) + 3.5} fill="#f59e0b" fontSize="9.5" fontFamily="monospace">
                            EMA {fmtCoord(emaVal!)}
                        </text>
                    </g>
                )}

                {/* Area + Main Price Path */}
                <path d={areaPath} fill={`url(#${gradId})`} />
                <polyline
                    points={polylinePoints}
                    fill="none"
                    stroke={strokeHex}
                    strokeWidth="2.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                />

                {/* Bottom Volume Bars */}
                {maxVol > 0 &&
                    pts.map((p, i) => {
                        const v = typeof p.v === "number" && p.v > 0 ? p.v : 0;
                        const h = (v / maxVol) * 24;
                        const upDay = i === 0 ? true : p.c >= pts[i - 1].c;
                        return (
                            <rect
                                key={i}
                                x={toX(i) - barW / 2}
                                y={volBottom - h}
                                width={barW}
                                height={Math.max(1.5, h)}
                                rx="1.5"
                                fill={upDay ? "#10b981" : "#f43f5e"}
                                fillOpacity={hoverIdx === i ? 0.85 : 0.35}
                            />
                        );
                    })}

                {/* Active / Hover Crosshair */}
                <line
                    x1={toX(activeIdx)}
                    y1={chartTop}
                    x2={toX(activeIdx)}
                    y2={chartBottom}
                    stroke="currentColor"
                    strokeOpacity="0.25"
                    strokeDasharray="2 2"
                />
                <circle
                    cx={toX(activeIdx)}
                    cy={toY(activePt.c)}
                    r="4.5"
                    fill={strokeHex}
                    stroke="#09090b"
                    strokeWidth="1.5"
                />
                <text x={chartRight + 6} y={toY(pts[pts.length - 1].c) + 3.5} fill={strokeHex} fontSize="10.5" fontFamily="monospace" fontWeight="800">
                    {fmtCoord(pts[pts.length - 1].c)}
                </text>
            </svg>
        </div>
    );
}

interface MomentumGaugesProps {
    rsi?: number;
    rVol?: number;
    kingScore?: number;
    wyckoffPhase?: string;
    ema50?: number;
    ema200?: number;
    price?: number;
}

/**
 * Visual RSI Speedometer SVG + Liquidity & AI Alignment Meter rendered client-side.
 */
export function MomentumLiquidityGauges({
    rsi,
    rVol,
    kingScore,
    wyckoffPhase,
    ema50,
    ema200,
    price,
}: MomentumGaugesProps) {
    const hasRsi = typeof rsi === "number" && Number.isFinite(rsi);
    const hasVol = typeof rVol === "number" && Number.isFinite(rVol);
    const hasKing = typeof kingScore === "number" && Number.isFinite(kingScore);

    if (!hasRsi && !hasVol && !hasKing && !wyckoffPhase) return null;

    const clampedRsi = hasRsi ? Math.max(0, Math.min(100, rsi!)) : 50;
    const rad = Math.PI * (1 - clampedRsi / 100);
    const nx = 80 + 46 * Math.cos(rad);
    const ny = 74 - 46 * Math.sin(rad);

    const normKing = hasKing ? (kingScore! <= 1 ? kingScore! * 100 : kingScore!) : undefined;
    const volPct = hasVol ? Math.min(100, Math.round((rVol! / 3) * 100)) : 0;

    return (
        <div
            className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 rounded-xl border border-zinc-200 dark:border-white/10 bg-zinc-50 dark:bg-zinc-900/60 p-2.5 sm:p-3"
            data-testid="momentum-liquidity-gauges"
        >
            {/* RSI Speedometer */}
            <div className="flex flex-col items-center justify-center rounded-lg bg-white dark:bg-black/40 border border-zinc-200/70 dark:border-white/10 p-2">
                <span className="text-[10px] font-bold text-zinc-500 dark:text-zinc-400">بوصلة الزخم (RSI 14)</span>
                <svg viewBox="0 0 160 88" className="w-36 h-20 select-none">
                    <path d="M 22 74 A 58 58 0 0 1 54 22" fill="none" stroke="#10b981" strokeWidth="10" strokeLinecap="round" strokeOpacity="0.45" />
                    <path d="M 58 20 A 58 58 0 0 1 102 20" fill="none" stroke="#f59e0b" strokeWidth="10" strokeOpacity="0.55" />
                    <path d="M 106 22 A 58 58 0 0 1 138 74" fill="none" stroke="#f43f5e" strokeWidth="10" strokeLinecap="round" strokeOpacity="0.45" />
                    {hasRsi && (
                        <>
                            <line x1="80" y1="74" x2={nx.toFixed(1)} y2={ny.toFixed(1)} stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" />
                            <circle cx="80" cy="74" r="4.5" fill="#f59e0b" />
                        </>
                    )}
                    <text x="80" y="61" textAnchor="middle" fill="currentColor" fontSize="12" fontWeight="800" fontFamily="monospace">
                        {hasRsi ? `RSI ${rsi!.toFixed(1)}` : "RSI —"}
                    </text>
                </svg>
                <span className="text-[10px] font-bold text-zinc-600 dark:text-zinc-300">
                    {!hasRsi
                        ? "غير متاح"
                        : rsi! >= 70
                            ? "تشبع شرائي (حذر جني أرباح)"
                            : rsi! <= 35
                                ? "تشبع بيعي (منطقة ارتداد)"
                                : rsi! >= 50
                                    ? "زخم إيجابي صحي"
                                    : "تهدئة / ترقب"}
                </span>
            </div>

            {/* Smart Liquidity & Trend Alignment */}
            <div className="flex flex-col justify-between gap-2 rounded-lg bg-white dark:bg-black/40 border border-zinc-200/70 dark:border-white/10 p-2.5 text-[11px]">
                {hasVol && (
                    <div>
                        <div className="flex items-center justify-between font-bold mb-1">
                            <span className="flex items-center gap-1 text-zinc-600 dark:text-zinc-300">
                                <Activity className="w-3 h-3 text-amber-500" />
                                <span>السيولة النسبية</span>
                            </span>
                            <span dir="ltr" className={`font-mono ${rVol! >= 1.5 ? "text-emerald-600 dark:text-emerald-400" : "text-zinc-700 dark:text-zinc-200"}`}>
                                RVol {rVol!.toFixed(2)}x
                            </span>
                        </div>
                        <div className="w-full h-2 rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
                            <div
                                className={`h-full rounded-full ${rVol! >= 1.5 ? "bg-emerald-500" : "bg-amber-500"}`}
                                style={{ width: `${Math.max(8, volPct)}%` }}
                            />
                        </div>
                    </div>
                )}

                {normKing !== undefined && (
                    <div>
                        <div className="flex items-center justify-between font-bold mb-1">
                            <span className="flex items-center gap-1 text-zinc-600 dark:text-zinc-300">
                                <TrendingUp className="w-3 h-3 text-purple-500" />
                                <span>تقييم AI</span>
                            </span>
                            <span dir="ltr" className="font-mono text-purple-600 dark:text-purple-400">
                                {normKing.toFixed(0)}%
                            </span>
                        </div>
                        <div className="w-full h-2 rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
                            <div className="h-full rounded-full bg-purple-500" style={{ width: `${Math.min(100, Math.max(5, normKing))}%` }} />
                        </div>
                    </div>
                )}

                <div className="flex flex-wrap items-center gap-1.5 pt-0.5 text-[10px] font-bold">
                    {wyckoffPhase && (
                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20">
                            {wyckoffPhase}
                        </span>
                    )}
                    {price && ema50 && (
                        <span className={`px-1.5 py-0.5 rounded border ${price >= ema50 ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20" : "bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/20"}`}>
                            {price >= ema50 ? "أعلى EMA50 ✓" : "أدنى EMA50"}
                        </span>
                    )}
                    {price && ema200 && (
                        <span className={`px-1.5 py-0.5 rounded border ${price >= ema200 ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20" : "bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/20"}`}>
                            {price >= ema200 ? "أعلى EMA200 ✓" : "أدنى EMA200"}
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}

export type ConceptDiagramKey =
    | "wyckoff_spring"
    | "bear_trap"
    | "bull_trap"
    | "breakout_retest"
    | "oversold_bounce";

interface ConceptMeta {
    key: ConceptDiagramKey;
    title: string;
    subtitle: string;
}

const CONCEPT_META: Record<ConceptDiagramKey, ConceptMeta> = {
    wyckoff_spring: {
        key: "wyckoff_spring",
        title: "رسم توضيحي: تجميع وايكوف وكسر الدعم الوهمي (Spring)",
        subtitle: "امتصاص العرض داخل النطاق ثم كسر وهمي لطرد البائعين قبل الانطلاق",
    },
    bear_trap: {
        key: "bear_trap",
        title: "رسم توضيحي: مصيدة الدببة (Bear Trap)",
        subtitle: "كسر سريع للدعم يفعّل أوامر الوقف ثم يعود السعر فوق الدعم بسيولة شرائية",
    },
    bull_trap: {
        key: "bull_trap",
        title: "رسم توضيحي: مصيدة الثيران (Bull Trap)",
        subtitle: "اختراق كاذب أعلى المقاومة يجذب المشترين قبل التراجع والتصريف",
    },
    breakout_retest: {
        key: "breakout_retest",
        title: "رسم توضيحي: الاختراق وإعادة الاختبار (Breakout & Retest)",
        subtitle: "تحوّل المقاومة المكسورة إلى دعم جديد — نقطة دخول منخفضة المخاطرة",
    },
    oversold_bounce: {
        key: "oversold_bounce",
        title: "رسم توضيحي: تشبع بيعي مع بوادر ارتداد فني (RSI ≤ 30)",
        subtitle: "تباطؤ الهبوط عند الدعم مع ارتداد من منطقة ذروة البيع",
    },
};

/**
 * Detect up to 2 explanatory technical concepts mentioned in substantive AI prose.
 */
export function detectConceptDiagrams(text: string): ConceptDiagramKey[] {
    if (!text || text.trim().length < 110) return [];
    const found: ConceptDiagramKey[] = [];

    if (/(?:تجميع\s+وايكوف|wyckoff|مراحل\s+وايكوف|كسر\s+وهمي.{0,25}تجميع|\bspring\b)/i.test(text)) {
        found.push("wyckoff_spring");
    }
    if (/(?:مصيد[ةه]\s+الدبب[ةه]|bear\s*trap)/i.test(text)) {
        found.push("bear_trap");
    }
    if (/(?:مصيد[ةه]\s+الثيران|bull\s*trap|اختراق\s+كاذب\s+(?:للمقاومة|للتصريف))/i.test(text)) {
        found.push("bull_trap");
    }
    if (/(?:اختراق|كسر)\s+(?:ال)?مقاوم[ةه].{0,70}(?:إعادة\s+اختبار|اعاده\s+اختبار|تبادل\s+[أا]دوار)/i.test(text)) {
        found.push("breakout_retest");
    }
    if (/(?:ذرو[ةه]\s+البيع|تشبع\s+بيعي).{0,60}(?:ارتداد|دايفرجنس|انفراج\s+[إا]يجابي)/i.test(text)) {
        found.push("oversold_bounce");
    }

    return found.slice(0, 2);
}

/**
 * Renders lightweight educational SVG diagrams inline while the AI assistant explains market ideas.
 */
export function ConceptDiagramCard({ concept }: { concept: ConceptDiagramKey }) {
    const [collapsed, setCollapsed] = useState(false);
    const meta = CONCEPT_META[concept];
    if (!meta) return null;

    return (
        <div
            className="my-2.5 rounded-2xl border border-amber-500/30 bg-amber-500/5 dark:bg-zinc-900/75 p-3 text-right"
            dir="rtl"
            data-testid={`concept-diagram-${concept}`}
        >
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                    <HelpCircle className="w-4 h-4 text-amber-500 shrink-0" />
                    <span className="text-xs font-black text-zinc-900 dark:text-amber-300 truncate">{meta.title}</span>
                </div>
                <button
                    type="button"
                    onClick={() => setCollapsed((v) => !v)}
                    className="text-[10px] font-bold px-2 py-0.5 rounded-md border border-zinc-300 dark:border-white/15 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 cursor-pointer"
                >
                    {collapsed ? "إظهار الرسم" : "إخفاء"}
                </button>
            </div>

            {!collapsed && (
                <div className="mt-2 space-y-1.5">
                    <p className="text-[11px] text-zinc-600 dark:text-zinc-400">{meta.subtitle}</p>

                    {concept === "wyckoff_spring" && (
                        <svg viewBox="0 0 600 135" className="w-full h-32 select-none" aria-label={meta.title}>
                            <rect x="65" y="34" width="330" height="62" rx="6" fill="#0ea5e9" fillOpacity="0.06" stroke="currentColor" strokeOpacity="0.22" strokeDasharray="4 3" />
                            <line x1="50" y1="96" x2="560" y2="96" stroke="#10b981" strokeDasharray="5 4" strokeWidth="1.5" />
                            <line x1="50" y1="34" x2="560" y2="34" stroke="#f43f5e" strokeDasharray="5 4" strokeWidth="1.5" />
                            <text x="44" y="38" textAnchor="end" fill="#f43f5e" fontSize="10.5" fontWeight="700">مقاومة</text>
                            <text x="44" y="100" textAnchor="end" fill="#10b981" fontSize="10.5" fontWeight="700">دعم</text>
                            <path d="M 70 55 L 125 92 L 180 40 L 235 93 L 285 44 L 330 116 L 380 65 L 435 28 L 468 38 L 545 14"
                                fill="none" stroke="#0ea5e9" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
                            <circle cx="330" cy="116" r="5" fill="#f59e0b" />
                            <text x="330" y="130" textAnchor="middle" fill="#f59e0b" fontSize="10.5" fontWeight="700">1. كسر وهمي (Spring)</text>
                            <circle cx="435" cy="28" r="5" fill="#10b981" />
                            <text x="475" y="64" textAnchor="middle" fill="#10b981" fontSize="10.5" fontWeight="700">2. اختراق بسيولة</text>
                        </svg>
                    )}

                    {concept === "bear_trap" && (
                        <svg viewBox="0 0 600 135" className="w-full h-32 select-none" aria-label={meta.title}>
                            <line x1="50" y1="78" x2="560" y2="78" stroke="#10b981" strokeDasharray="5 4" strokeWidth="1.6" />
                            <text x="44" y="82" textAnchor="end" fill="#10b981" fontSize="10.5" fontWeight="700">الدعم</text>
                            <path d="M 70 42 L 155 75 L 220 52 L 290 112 L 340 72 L 425 46 L 540 20"
                                fill="none" stroke="#10b981" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
                            <circle cx="290" cy="112" r="5.5" fill="#f43f5e" />
                            <text x="290" y="128" textAnchor="middle" fill="#f43f5e" fontSize="10.5" fontWeight="700">كسر كاذب وضرب الوقف</text>
                            <circle cx="340" cy="72" r="5.5" fill="#10b981" />
                            <text x="405" y="96" textAnchor="middle" fill="#10b981" fontSize="10.5" fontWeight="700">إغلاق سريع أعلى الدعم (فخ)</text>
                        </svg>
                    )}

                    {concept === "bull_trap" && (
                        <svg viewBox="0 0 600 135" className="w-full h-32 select-none" aria-label={meta.title}>
                            <line x1="50" y1="58" x2="560" y2="58" stroke="#f43f5e" strokeDasharray="5 4" strokeWidth="1.6" />
                            <text x="44" y="62" textAnchor="end" fill="#f43f5e" fontSize="10.5" fontWeight="700">المقاومة</text>
                            <path d="M 70 98 L 155 62 L 220 82 L 290 22 L 345 64 L 440 94 L 540 120"
                                fill="none" stroke="#f43f5e" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
                            <circle cx="290" cy="22" r="5.5" fill="#f59e0b" />
                            <text x="290" y="14" textAnchor="middle" fill="#f59e0b" fontSize="10.5" fontWeight="700">اختراق وهمي لجذب المشترين</text>
                            <circle cx="345" cy="64" r="5.5" fill="#f43f5e" />
                            <text x="415" y="48" textAnchor="middle" fill="#f43f5e" fontSize="10.5" fontWeight="700">ارتداد سريع للأسفل</text>
                        </svg>
                    )}

                    {concept === "breakout_retest" && (
                        <svg viewBox="0 0 600 135" className="w-full h-32 select-none" aria-label={meta.title}>
                            <line x1="50" y1="68" x2="560" y2="68" stroke="#f59e0b" strokeDasharray="5 4" strokeWidth="1.6" />
                            <text x="44" y="72" textAnchor="end" fill="#f59e0b" fontSize="10.5" fontWeight="700">المستوى</text>
                            <path d="M 70 112 L 150 72 L 220 96 L 300 32 L 365 65 L 445 36 L 545 14"
                                fill="none" stroke="#0ea5e9" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
                            <circle cx="300" cy="32" r="5" fill="#0ea5e9" />
                            <text x="300" y="20" textAnchor="middle" fill="#0ea5e9" fontSize="10.5" fontWeight="700">1. اختراق المقاومة</text>
                            <circle cx="365" cy="65" r="5.5" fill="#10b981" />
                            <text x="395" y="96" textAnchor="middle" fill="#10b981" fontSize="10.5" fontWeight="700">2. إعادة الاختبار (تحول لدعم)</text>
                        </svg>
                    )}

                    {concept === "oversold_bounce" && (
                        <svg viewBox="0 0 600 135" className="w-full h-32 select-none" aria-label={meta.title}>
                            <rect x="55" y="78" width="500" height="34" rx="4" fill="#10b981" fillOpacity="0.12" />
                            <line x1="55" y1="78" x2="555" y2="78" stroke="#10b981" strokeDasharray="4 3" strokeWidth="1.3" />
                            <text x="48" y="96" textAnchor="end" fill="#10b981" fontSize="10">تشبع بيعي</text>
                            <path d="M 70 28 L 155 48 L 235 76 L 315 104 L 385 88 L 465 56 L 545 38"
                                fill="none" stroke="#10b981" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
                            <circle cx="315" cy="104" r="5.5" fill="#f59e0b" />
                            <text x="315" y="124" textAnchor="middle" fill="#f59e0b" fontSize="10.5" fontWeight="700">ذروة البيع (RSI ≤ 30) وتوقف الزخم الهابط</text>
                        </svg>
                    )}

                    <div className="flex items-center justify-between text-[10px] text-zinc-500 dark:text-zinc-400">
                        <span className="flex items-center gap-1">
                            <ShieldCheck className="w-3 h-3 text-emerald-500" />
                            <span>نموذج إرشادي للتحليل الفني (لا يغني عن وقف الخسارة)</span>
                        </span>
                    </div>
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// 5. Common Question Visuals (Zero Vercel CPU, 100% Client SVG)
// ---------------------------------------------------------------------------

type CompareStockInput = NonNullable<ChatVisualsPayload["comparison"]>[number];

/**
 * Visual side-by-side Mirror Bars comparing 2 stocks across KING AI, RVol, upside to Resistance, and RSI.
 */
export function ComparisonMirrorCard({ stocks }: { stocks: CompareStockInput[] }) {
    const validStocks = (stocks || []).filter((s) => s && s.symbol);
    const [pairIdx, setPairIdx] = useState<[number, number]>([0, 1]);

    if (validStocks.length < 2) return null;

    const a = validStocks[Math.min(pairIdx[0], validStocks.length - 1)] || validStocks[0];
    const b = validStocks[Math.min(pairIdx[1], validStocks.length - 1)] || validStocks[1];
    if (!a || !b || a.symbol === b.symbol) return null;

    const normKing = (v?: number | null) =>
        typeof v === "number" && Number.isFinite(v) ? (v <= 1 ? v * 100 : v) : undefined;
    const calcUpside = (s: CompareStockInput) =>
        typeof s.close === "number" &&
        s.close > 0 &&
        typeof s.resistance_1 === "number" &&
        s.resistance_1 > s.close
            ? ((s.resistance_1 - s.close) / s.close) * 100
            : undefined;

    const metrics = [
        {
            label: "تقييم الذكاء الاصطناعي (KING AI)",
            aVal: normKing(a.king_ai_score),
            bVal: normKing(b.king_ai_score),
            fmt: (v: number) => `${v.toFixed(0)}%`,
            max: 100,
            higherWins: true,
        },
        {
            label: "السيولة النسبية (RVol)",
            aVal: typeof a.r_vol === "number" && Number.isFinite(a.r_vol) ? a.r_vol : undefined,
            bVal: typeof b.r_vol === "number" && Number.isFinite(b.r_vol) ? b.r_vol : undefined,
            fmt: (v: number) => `${v.toFixed(2)}x`,
            max: 3,
            higherWins: true,
        },
        {
            label: "مسافة المقاومة الأولى (+%)",
            aVal: calcUpside(a),
            bVal: calcUpside(b),
            fmt: (v: number) => `+${v.toFixed(1)}%`,
            max: 25,
            higherWins: true,
        },
        {
            label: "مؤشر الزخم (RSI 14)",
            aVal: typeof a.rsi_14 === "number" && Number.isFinite(a.rsi_14) ? a.rsi_14 : undefined,
            bVal: typeof b.rsi_14 === "number" && Number.isFinite(b.rsi_14) ? b.rsi_14 : undefined,
            fmt: (v: number) => `${v.toFixed(1)}`,
            max: 100,
            higherWins: false,
        },
    ].filter((m) => m.aVal !== undefined || m.bVal !== undefined);

    if (metrics.length === 0) return null;

    let aWins = 0;
    let bWins = 0;
    for (const m of metrics) {
        if (m.aVal !== undefined && m.bVal !== undefined && Math.abs(m.aVal - m.bVal) > 1e-6) {
            if (m.higherWins) {
                if (m.aVal > m.bVal) aWins++;
                else bWins++;
            } else {
                // Healthier RSI score closer to 55 sweet spot without overbought >70
                const distA = Math.abs(m.aVal - 55) + (m.aVal > 70 ? 15 : 0);
                const distB = Math.abs(m.bVal - 55) + (m.bVal > 70 ? 15 : 0);
                if (distA < distB) aWins++;
                else bWins++;
            }
        }
    }
    const leaderLabel =
        aWins === bWins
            ? "تقارب متكافئ بين السهمين"
            : `أفضلية نسبية: ${aWins > bWins ? a.symbol : b.symbol} (${Math.max(aWins, bWins)}/${metrics.length})`;

    return (
        <div
            className="my-2.5 rounded-2xl border border-zinc-200 dark:border-white/15 bg-zinc-50 dark:bg-zinc-900/70 p-3 space-y-2.5 text-right"
            dir="rtl"
            data-testid="comparison-mirror-card"
        >
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-1.5 font-black">
                    <BarChart3 className="w-4 h-4 text-amber-500 shrink-0" />
                    <span>مقارنة بصرية سريعة:</span>
                    <span className="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-700 dark:text-sky-300 font-mono">{a.symbol}</span>
                    <span className="text-zinc-400">مقابل</span>
                    <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 font-mono">{b.symbol}</span>
                </div>
                <span className="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-800 dark:text-amber-300 border border-amber-500/30 text-[10px] font-bold">
                    {leaderLabel}
                </span>
            </div>

            {validStocks.length > 2 && (
                <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-bold">
                    <span className="text-zinc-500">اختر سهمي المقارنة:</span>
                    {validStocks.map((st, idx) => (
                        <button
                            key={st.symbol}
                            type="button"
                            onClick={() =>
                                setPairIdx((prev) =>
                                    prev[0] === idx || prev[1] === idx ? prev : [prev[1], idx]
                                )
                            }
                            className={`px-2 py-0.5 rounded border font-mono cursor-pointer ${
                                idx === pairIdx[0] || idx === pairIdx[1]
                                    ? "bg-amber-500/20 border-amber-500/50 text-amber-800 dark:text-amber-200"
                                    : "border-zinc-300 dark:border-white/15 text-zinc-500"
                            }`}
                        >
                            {st.symbol}
                        </button>
                    ))}
                </div>
            )}

            <div className="space-y-2 text-[11px]">
                {metrics.map((m) => {
                    const aPct = m.aVal !== undefined ? Math.min(100, Math.max(6, (m.aVal / m.max) * 100)) : 0;
                    const bPct = m.bVal !== undefined ? Math.min(100, Math.max(6, (m.bVal / m.max) * 100)) : 0;
                    return (
                        <div key={m.label} className="space-y-1">
                            <div className="flex items-center justify-between text-zinc-600 dark:text-zinc-300 font-semibold">
                                <span>{m.label}</span>
                                <span dir="ltr" className="font-mono text-[10.5px]">
                                    <strong className="text-sky-600 dark:text-sky-400">
                                        {m.aVal !== undefined ? m.fmt(m.aVal) : "—"} {a.symbol}
                                    </strong>
                                    {" vs "}
                                    <strong className="text-emerald-600 dark:text-emerald-400">
                                        {b.symbol} {m.bVal !== undefined ? m.fmt(m.bVal) : "—"}
                                    </strong>
                                </span>
                            </div>
                            <div className="grid grid-cols-2 gap-1.5 items-center">
                                <div className="h-2 rounded-full bg-zinc-200 dark:bg-zinc-800 flex justify-end overflow-hidden">
                                    <div className="h-full bg-sky-500 rounded-full" style={{ width: `${aPct}%` }} />
                                </div>
                                <div className="h-2 rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
                                    <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${bPct}%` }} />
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

type PortfolioVisualInput = NonNullable<ChatVisualsPayload["portfolio"]>;

const DONUT_COLORS = ["#0ea5e9", "#10b981", "#f59e0b", "#a855f7", "#ec4899", "#06b6d4"];

/**
 * SVG Donut Allocation & Per-Holding P&L Bars with dual-market isolation (EGX EGP vs TASI SAR).
 */
export function PortfolioVisualCard({ portfolio }: { portfolio: PortfolioVisualInput }) {
    const positions = portfolio?.positions || [];
    const markets = useMemo(() => {
        const seen = new Set<string>();
        for (const p of positions) {
            if (p.market) seen.add(p.market);
        }
        return seen.size > 0 ? Array.from(seen) : ["EGX"];
    }, [positions]);

    const [activeMarket, setActiveMarket] = useState<string>(markets[0] || "EGX");
    if (positions.length === 0) return null;

    const currentMkt = markets.includes(activeMarket) ? activeMarket : markets[0];
    const mktPositions = positions.filter((p) => (p.market || "EGX") === currentMkt);
    const currency = mktPositions[0]?.currency || (currentMkt === "TASI" ? "ر.س" : "ج.م");

    // Cash balance belongs to EGP base cash when dual-market
    const cashVal = currentMkt === "EGX" && typeof portfolio.cash_balance === "number" && portfolio.cash_balance > 0
        ? portfolio.cash_balance
        : 0;

    const valuedItems = mktPositions
        .map((p, idx) => ({
            symbol: p.symbol,
            value: typeof p.market_value === "number" && p.market_value > 0 ? p.market_value : 0,
            profitPct: typeof p.profit_pct === "number" && Number.isFinite(p.profit_pct) ? p.profit_pct : undefined,
            profitVal: typeof p.profit_value === "number" && Number.isFinite(p.profit_value) ? p.profit_value : undefined,
            color: DONUT_COLORS[idx % DONUT_COLORS.length],
        }))
        .sort((a, b) => b.value - a.value);

    const totalHoldingsVal = valuedItems.reduce((acc, it) => acc + it.value, 0);
    const totalCapital = totalHoldingsVal + cashVal;
    const topPos = valuedItems[0];
    const topWeightPct = totalCapital > 0 && topPos ? (topPos.value / totalCapital) * 100 : 0;

    const slices = [...valuedItems.slice(0, 5)];
    if (valuedItems.length > 5) {
        const restVal = valuedItems.slice(5).reduce((s, x) => s + x.value, 0);
        if (restVal > 0) slices.push({ symbol: "أخرى", value: restVal, profitPct: undefined, profitVal: undefined, color: "#64748b" });
    }
    if (cashVal > 0) {
        slices.push({ symbol: "كاش", value: cashVal, profitPct: undefined, profitVal: undefined, color: "#94a3b8" });
    }

    const circumference = 2 * Math.PI * 42;
    let dashOffset = 0;

    const pnlSorted = [...valuedItems]
        .filter((x) => x.profitPct !== undefined)
        .sort((a, b) => (b.profitPct ?? 0) - (a.profitPct ?? 0));
    const maxAbsPnl = Math.max(...pnlSorted.map((x) => Math.abs(x.profitPct ?? 0)), 1);

    return (
        <div
            className="my-2.5 rounded-2xl border border-zinc-200 dark:border-white/15 bg-zinc-50 dark:bg-zinc-900/70 p-3 space-y-2.5 text-right"
            dir="rtl"
            data-testid="portfolio-visual-card"
        >
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-1.5 font-black">
                    <Briefcase className="w-4 h-4 text-amber-500 shrink-0" />
                    <span>توزيع أوزان المحفظة والأرباح ({currentMkt})</span>
                </div>
                <div className="flex items-center gap-1.5">
                    {markets.length > 1 &&
                        markets.map((m) => (
                            <button
                                key={m}
                                type="button"
                                onClick={() => setActiveMarket(m)}
                                className={`px-2 py-0.5 rounded border text-[10px] font-bold cursor-pointer ${
                                    currentMkt === m
                                        ? "bg-amber-500/20 border-amber-500/50 text-amber-800 dark:text-amber-300"
                                        : "border-zinc-300 dark:border-white/15 text-zinc-500"
                                }`}
                            >
                                {m}
                            </button>
                        ))}
                    {topWeightPct >= 40 && topPos && (
                        <span className="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30 text-[10px] font-bold">
                            تركز مرتفع في {topPos.symbol} ({topWeightPct.toFixed(0)}%)
                        </span>
                    )}
                </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-center">
                {totalCapital > 0 && (
                    <div className="sm:col-span-5 flex flex-col items-center justify-center sm:border-l border-zinc-200 dark:border-white/10 sm:pl-3">
                        <div className="relative w-28 h-28">
                            <svg viewBox="0 0 110 110" className="w-full h-full -rotate-90" aria-label="توزيع المحفظة">
                                <circle cx="55" cy="55" r="42" fill="none" stroke="currentColor" strokeOpacity="0.1" strokeWidth="15" />
                                {slices.map((s) => {
                                    const frac = s.value / totalCapital;
                                    const len = Math.max(2, frac * circumference);
                                    const node = (
                                        <circle
                                            key={s.symbol}
                                            cx="55"
                                            cy="55"
                                            r="42"
                                            fill="none"
                                            stroke={s.color}
                                            strokeWidth="15"
                                            strokeDasharray={`${len.toFixed(1)} ${circumference.toFixed(1)}`}
                                            strokeDashoffset={(-dashOffset).toFixed(1)}
                                        />
                                    );
                                    dashOffset += frac * circumference;
                                    return node;
                                })}
                            </svg>
                            <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none">
                                <span className="text-[9px] text-zinc-500">القيمة ({currency})</span>
                                <span dir="ltr" className="font-mono font-black text-[11px] text-zinc-900 dark:text-white">
                                    {Math.round(totalCapital).toLocaleString("en-US")}
                                </span>
                            </div>
                        </div>
                        <div className="flex flex-wrap justify-center gap-2 text-[10px] font-bold mt-1.5">
                            {slices.map((s) => (
                                <span key={s.symbol} className="flex items-center gap-1">
                                    <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: s.color }} />
                                    <span className="font-mono">{s.symbol}</span>
                                    <span className="text-zinc-500">{((s.value / totalCapital) * 100).toFixed(0)}%</span>
                                </span>
                            ))}
                        </div>
                    </div>
                )}

                <div className={`${totalCapital > 0 ? "sm:col-span-7" : "sm:col-span-12"} space-y-1.5 text-[11px]`}>
                    {pnlSorted.length > 0 ? (
                        pnlSorted.slice(0, 6).map((p) => {
                            const pct = p.profitPct ?? 0;
                            const isGain = pct >= 0;
                            const barW = Math.max(8, Math.round((Math.abs(pct) / maxAbsPnl) * 100));
                            return (
                                <div key={p.symbol}>
                                    <div className="flex justify-between font-bold mb-0.5">
                                        <span className="font-mono">{p.symbol}</span>
                                        <span dir="ltr" className={`font-mono ${isGain ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                                            {isGain ? "+" : ""}{pct.toFixed(1)}%
                                            {p.profitVal !== undefined ? ` (${isGain ? "+" : ""}${Math.round(p.profitVal).toLocaleString("en-US")} ${currency})` : ""}
                                        </span>
                                    </div>
                                    <div className="w-full h-2 rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
                                        <div className={`h-full rounded-full ${isGain ? "bg-emerald-500" : "bg-rose-500"}`} style={{ width: `${barW}%` }} />
                                    </div>
                                </div>
                            );
                        })
                    ) : (
                        <p className="text-zinc-500 text-xs">لم تُحسب نسب الربح لبعض الأسهم لعدم توفر تكلفة الشراء.</p>
                    )}
                </div>
            </div>
        </div>
    );
}

/**
 * Market Breadth advancing/declining segmented bar + Accumulation Institutional Heatmap cards.
 */
export function MarketBreadthAccumulationCard({
    breadth,
    accumulation,
}: {
    breadth?: ChatVisualsPayload["market_breadth"];
    accumulation?: ChatVisualsPayload["accumulation"];
}) {
    const hasBreadth = Boolean(breadth && breadth.total_stocks > 0);
    const accList = (accumulation || []).filter((x) => x && x.symbol);
    const hasAcc = accList.length >= 2;
    if (!hasBreadth && !hasAcc) return null;

    const total = breadth?.total_stocks || 1;
    const advPct = breadth ? Math.round((breadth.advancing / total) * 100) : 0;
    const unchPct = breadth ? Math.round((breadth.unchanged / total) * 100) : 0;
    const decPct = breadth ? Math.max(0, 100 - advPct - unchPct) : 0;

    return (
        <div className="my-2.5 space-y-2.5 text-right" dir="rtl">
            {hasBreadth && breadth && (
                <div
                    className="rounded-2xl border border-zinc-200 dark:border-white/15 bg-zinc-50 dark:bg-zinc-900/70 p-3 space-y-2"
                    data-testid="market-breadth-card"
                >
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                        <span className="font-black text-zinc-900 dark:text-white">
                            مؤشر اتساع السوق ({breadth.market || breadth.index_name || "السوق"})
                        </span>
                        {breadth.index_close !== null && breadth.index_close !== undefined && (
                            <span dir="ltr" className="font-mono font-bold text-zinc-700 dark:text-zinc-200">
                                {breadth.index_name}: {Number(breadth.index_close).toLocaleString("en-US")}
                                {breadth.index_change_pct !== null && breadth.index_change_pct !== undefined && (
                                    <span className={breadth.index_change_pct >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}>
                                        {" "}({breadth.index_change_pct >= 0 ? "+" : ""}{Number(breadth.index_change_pct).toFixed(2)}%)
                                    </span>
                                )}
                            </span>
                        )}
                    </div>

                    <div className="w-full h-5 rounded-lg overflow-hidden flex text-[10px] font-black select-none">
                        {advPct > 0 && (
                            <div className="bg-emerald-500/85 text-white flex items-center justify-center truncate px-1" style={{ width: `${advPct}%` }}>
                                صاعد {breadth.advancing} ({advPct}%)
                            </div>
                        )}
                        {unchPct > 0 && (
                            <div className="bg-amber-400/80 text-black flex items-center justify-center truncate px-1" style={{ width: `${unchPct}%` }}>
                                {breadth.unchanged}
                            </div>
                        )}
                        {decPct > 0 && (
                            <div className="bg-rose-500/85 text-white flex items-center justify-center truncate px-1" style={{ width: `${decPct}%` }}>
                                هابط {breadth.declining} ({decPct}%)
                            </div>
                        )}
                    </div>
                </div>
            )}

            {hasAcc && (
                <div
                    className="rounded-2xl border border-zinc-200 dark:border-white/15 bg-zinc-50 dark:bg-zinc-900/70 p-3 space-y-2"
                    data-testid="accumulation-heatmap-card"
                >
                    <div className="flex items-center gap-1.5 text-xs font-black text-zinc-900 dark:text-white">
                        <Flame className="w-4 h-4 text-emerald-500 shrink-0" />
                        <span>خريطة حرارة السيولة الذكية والتجميع المؤسسي</span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                        {accList.slice(0, 8).map((item) => {
                            const score = Number(item.accumulation_score ?? 0);
                            const isHot = score >= 80;
                            return (
                                <div
                                    key={item.symbol}
                                    className={`p-2 rounded-xl border ${
                                        isHot
                                            ? "bg-emerald-500/15 border-emerald-500/40"
                                            : "bg-sky-500/10 border-sky-500/30"
                                    }`}
                                >
                                    <div className="flex items-center justify-between font-mono font-black">
                                        <span>{item.symbol}</span>
                                        <span className={isHot ? "text-emerald-600 dark:text-emerald-400" : "text-sky-600 dark:text-sky-400"}>
                                            {score > 0 ? `${score.toFixed(0)}/100` : "—"}
                                        </span>
                                    </div>
                                    <div className="text-[10px] text-zinc-600 dark:text-zinc-400 mt-0.5 flex items-center justify-between">
                                        <span>{item.r_vol ? `RVol ${Number(item.r_vol).toFixed(1)}x` : "تجميع"}</span>
                                        {item.consecutive_acc_days ? <span>{item.consecutive_acc_days} أيام</span> : null}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}

type FairValueItem = NonNullable<ChatVisualsPayload["fair_value"]>[number];

/**
 * Linear SVG Fair Value Discount/Premium Gauge plotting current price vs estimated fair value.
 */
export function FairValueGaugeCard({ items }: { items: FairValueItem[] }) {
    const valid = (items || []).filter((x) => x && x.symbol && x.current_price > 0 && x.fair_value > 0);
    const [selectedIdx, setSelectedIdx] = useState(0);
    if (valid.length === 0) return null;

    const item = valid[Math.min(selectedIdx, valid.length - 1)] || valid[0];
    const cur = item.current_price;
    const fv = item.fair_value;
    const curr = item.currency || "ج.م";
    const diffPct = item.upside_pct !== null && item.upside_pct !== undefined
        ? Number(item.upside_pct)
        : ((fv - cur) / cur) * 100;

    // Plot relative ratio cur / fv cleanly on [0.6 .. 1.4] -> [12% .. 88%]
    const ratio = cur / fv;
    const clampedRatio = Math.max(0.6, Math.min(1.4, ratio));
    const curX = 75 + ((clampedRatio - 0.6) / 0.8) * 450;
    const fvX = 300;
    const isCheap = diffPct >= 5;
    const isExpensive = diffPct <= -5;

    return (
        <div
            className="my-2.5 rounded-2xl border border-zinc-200 dark:border-white/15 bg-zinc-50 dark:bg-zinc-900/70 p-3 space-y-2 text-right"
            dir="rtl"
            data-testid="fair-value-gauge-card"
        >
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="font-black flex items-center gap-1.5">
                    <Scale className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>مقياس القيمة العادلة: <span className="font-mono">{item.symbol}</span></span>
                </div>
                <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                        isCheap
                            ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30"
                            : isExpensive
                                ? "bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30"
                                : "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30"
                    }`}
                >
                    {isCheap
                        ? `فرصة رخص (صعود محتمل +${diffPct.toFixed(1)}%)`
                        : isExpensive
                            ? `متضخم (${diffPct.toFixed(1)}%)`
                            : `قريب من القيمة العادلة (${diffPct >= 0 ? "+" : ""}${diffPct.toFixed(1)}%)`}
                </span>
            </div>

            {valid.length > 1 && (
                <div className="flex flex-wrap gap-1.5 text-[10px] font-bold">
                    {valid.map((v, idx) => (
                        <button
                            key={v.symbol}
                            type="button"
                            onClick={() => setSelectedIdx(idx)}
                            className={`px-2 py-0.5 rounded border font-mono cursor-pointer ${
                                idx === selectedIdx
                                    ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-800 dark:text-emerald-300"
                                    : "border-zinc-300 dark:border-white/15 text-zinc-500"
                            }`}
                        >
                            {v.symbol} ({v.upside_pct && v.upside_pct > 0 ? `+${Number(v.upside_pct).toFixed(0)}%` : `${Number(v.upside_pct ?? 0).toFixed(0)}%`})
                        </button>
                    ))}
                </div>
            )}

            <svg viewBox="0 0 600 84" className="w-full h-20 select-none" aria-label={`مقياس القيمة العادلة ${item.symbol}`}>
                <rect x="60" y="38" width="205" height="12" rx="4" fill="#10b981" fillOpacity="0.28" />
                <rect x="265" y="38" width="70" height="12" fill="#f59e0b" fillOpacity="0.28" />
                <rect x="335" y="38" width="205" height="12" rx="4" fill="#f43f5e" fillOpacity="0.28" />

                {/* Fair Value Center Line */}
                <line x1={fvX} y1="24" x2={fvX} y2="60" stroke="currentColor" strokeWidth="2.5" />
                <text x={fvX} y="16" textAnchor="middle" fill="currentColor" fontSize="11" fontWeight="700">
                    العادل: {fmtCoord(fv)} {curr}
                </text>

                {/* Current Price Marker */}
                <circle
                    cx={curX}
                    cy="44"
                    r="6.5"
                    fill={isCheap ? "#10b981" : isExpensive ? "#f43f5e" : "#f59e0b"}
                    stroke="#09090b"
                    strokeWidth="1.5"
                />
                <text
                    x={curX}
                    y="72"
                    textAnchor="middle"
                    fill={isCheap ? "#10b981" : isExpensive ? "#f43f5e" : "#f59e0b"}
                    fontSize="11"
                    fontWeight="800"
                >
                    الحالي: {fmtCoord(cur)} {curr}
                </text>
            </svg>
        </div>
    );
}

// ---------------------------------------------------------------------------
// 6. Round-3 Visuals: Recommendations Tracker, Sharia Purification, Price Traps, Disclosures Timeline
// ---------------------------------------------------------------------------

type RecTrackerItem = NonNullable<ChatVisualsPayload["recommendations"]>[number];

/**
 * Plots open recommendations along Stop Loss -> Historical Entry -> Target with live Current Price marker,
 * clearly warning when current price trades below historical issuance entry price.
 */
export function RecommendationsTrackerCard({ items }: { items: RecTrackerItem[] }) {
    const valid = (items || []).filter(
        (r) => r && r.symbol && typeof r.entry_price === "number" && r.entry_price > 0
    );
    if (valid.length === 0) return null;

    return (
        <div
            className="my-2.5 rounded-2xl border border-zinc-200 dark:border-white/15 bg-zinc-50 dark:bg-zinc-900/70 p-3 space-y-2.5 text-right"
            dir="rtl"
            data-testid="recommendations-tracker-card"
        >
            <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5 font-black">
                    <Target className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>مسار التوصيات مقارنةً بسعر الدخول التاريخي</span>
                </div>
                <span className="text-[10px] text-zinc-500 font-bold">{valid.length} توصيات</span>
            </div>

            <div className="space-y-2">
                {valid.slice(0, 6).map((rec) => {
                    const curr = rec.currency || "ج.م";
                    const entry = rec.entry_price;
                    const stop =
                        typeof rec.stop_loss === "number" && rec.stop_loss > 0 && rec.stop_loss < entry
                            ? rec.stop_loss
                            : entry * 0.94;
                    const target =
                        typeof rec.target_price === "number" && rec.target_price > entry
                            ? rec.target_price
                            : entry * 1.1;
                    const cur = typeof rec.last_close === "number" && rec.last_close > 0 ? rec.last_close : undefined;

                    const vals = [stop, entry, target, ...(cur ? [cur] : [])];
                    const minV = Math.min(...vals);
                    const maxV = Math.max(...vals);
                    const span = Math.max(maxV - minV, 1e-6);
                    const toX = (v: number) => 64 + ((v - minV) / span) * 452;

                    const stopX = toX(stop);
                    const entryX = toX(entry);
                    const targetX = toX(target);
                    let lblStopX = stopX;
                    let lblEntryX = Math.max(lblStopX + 90, entryX);
                    let lblTargetX = Math.max(lblEntryX + 90, targetX);
                    if (lblTargetX > 516) {
                        lblTargetX = 516;
                        lblEntryX = Math.min(lblEntryX, lblTargetX - 90);
                        lblStopX = Math.min(lblStopX, lblEntryX - 90);
                    }
                    lblStopX = Math.max(64, lblStopX);

                    const curX = cur !== undefined ? toX(cur) : 0;
                    const curLblX = cur !== undefined ? Math.max(76, Math.min(504, curX)) : 0;

                    const diffFromEntry = cur ? ((cur - entry) / entry) * 100 : undefined;
                    const isBelowEntry = diffFromEntry !== undefined && diffFromEntry < -0.5;
                    const isGain = diffFromEntry !== undefined && diffFromEntry >= 0.5;

                    return (
                        <div
                            key={`${rec.symbol}-${rec.date || ""}`}
                            className="p-2.5 rounded-xl bg-white dark:bg-black/40 border border-zinc-200/80 dark:border-white/10 space-y-1.5 text-xs"
                        >
                            <div className="flex flex-wrap items-center justify-between gap-1.5">
                                <div className="flex items-center gap-2 font-bold">
                                    <span className="font-mono font-black px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-800 dark:text-amber-300">
                                        {rec.symbol}
                                    </span>
                                    {rec.date && <span className="text-[10px] text-zinc-500">صدرت: {rec.date}</span>}
                                </div>
                                {diffFromEntry !== undefined && (
                                    <span
                                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                                            isBelowEntry
                                                ? "bg-amber-500/15 text-amber-800 dark:text-amber-300 border-amber-500/35"
                                                : isGain
                                                    ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/35"
                                                    : "bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/35"
                                        }`}
                                    >
                                        {isBelowEntry
                                            ? `تحت الدخول التاريخي (${diffFromEntry.toFixed(1)}%)`
                                            : isGain
                                                ? `صعود عن الدخول (+${diffFromEntry.toFixed(1)}%)`
                                                : "قريب من منطقة الدخول"}
                                    </span>
                                )}
                            </div>

                            <svg viewBox="0 0 580 56" className="w-full h-14 select-none overflow-visible" aria-label={`مسار توصية ${rec.symbol}`}>
                                <line x1="64" y1="27" x2="516" y2="27" stroke="currentColor" strokeOpacity="0.18" strokeWidth="4" strokeLinecap="round" />
                                <line x1={entryX} y1="27" x2={targetX} y2="27" stroke="#10b981" strokeOpacity="0.45" strokeWidth="6" strokeLinecap="round" />

                                {/* Stop */}
                                <circle cx={stopX} cy="27" r="4.5" fill="#f43f5e" />
                                <text x={lblStopX} y="48" textAnchor="middle" fill="#f43f5e" fontSize="10" fontFamily="monospace">
                                    وقف {fmtCoord(stop)}
                                </text>

                                {/* Historical Entry */}
                                <rect x={entryX - 2.5} y="19" width="5" height="16" rx="2" fill="currentColor" />
                                <text x={lblEntryX} y="48" textAnchor="middle" fill="currentColor" fontSize="10" fontWeight="700">
                                    دخول {fmtCoord(entry)}
                                </text>

                                {/* Current Price */}
                                {cur !== undefined && (
                                    <g>
                                        <circle
                                            cx={curX}
                                            cy="27"
                                            r="6"
                                            fill={isBelowEntry ? "#f59e0b" : "#0ea5e9"}
                                            stroke="#09090b"
                                            strokeWidth="1.5"
                                        />
                                        <text
                                            x={curLblX}
                                            y="13"
                                            textAnchor="middle"
                                            fill={isBelowEntry ? "#f59e0b" : "#0ea5e9"}
                                            fontSize="10.5"
                                            fontWeight="800"
                                        >
                                            الآن {fmtCoord(cur)} {curr}
                                        </text>
                                    </g>
                                )}

                                {/* Target */}
                                <circle cx={targetX} cy="27" r="4.5" fill="#10b981" />
                                <text x={lblTargetX} y="48" textAnchor="middle" fill="#10b981" fontSize="10" fontFamily="monospace">
                                    هدف {fmtCoord(target)}
                                </text>
                            </svg>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

type ShariaVisualInput = NonNullable<ChatVisualsPayload["sharia"]>;

/**
 * Interactive client-side Sharia Compliance & Coupon Purification Slider Calculator.
 */
export function ShariaPurificationCard({ sharia }: { sharia: ShariaVisualInput }) {
    const initialQty = typeof sharia?.shares_count === "number" && sharia.shares_count > 0 ? sharia.shares_count : 1000;
    const [qty, setQty] = useState<number>(initialQty);

    if (!sharia || !sharia.symbol) return null;

    const curr = sharia.currency || "ج.م";
    const coupon = typeof sharia.coupon_per_share === "number" && sharia.coupon_per_share > 0 ? sharia.coupon_per_share : 0;
    const rate = typeof sharia.purification_rate_pct === "number" && sharia.purification_rate_pct >= 0 ? sharia.purification_rate_pct : 0;
    const totalDiv = qty * coupon;
    const purifyAmt = totalDiv * (rate / 100);
    const netHalal = Math.max(0, totalDiv - purifyAmt);
    const pureSharePct = purifyAmt > 0 && totalDiv > 0 ? Math.max(5, Math.min(45, (purifyAmt / totalDiv) * 100)) : 0;

    return (
        <div
            className="my-2.5 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 dark:bg-zinc-900/75 p-3 space-y-2.5 text-right"
            dir="rtl"
            data-testid="sharia-purification-card"
        >
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-1.5 font-black">
                    <Award className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>بطاقة التوافق الشرعي والتطهير: <span className="font-mono">{sharia.symbol}</span></span>
                </div>
                <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                        sharia.is_sharia_compliant
                            ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/35"
                            : "bg-amber-500/15 text-amber-800 dark:text-amber-300 border-amber-500/35"
                    }`}
                >
                    {sharia.sharia_index || (sharia.is_sharia_compliant ? "EGX33 شرعي ✓" : "غير مدرج في EGX33")}
                </span>
            </div>

            {coupon > 0 && (
                <div className="space-y-2 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-zinc-600 dark:text-zinc-300">
                            توزيع السهم: <strong className="font-mono">{coupon.toFixed(2)} {curr}</strong> • نسبة التطهير:{" "}
                            <strong className="font-mono">{rate.toFixed(1)}%</strong>
                        </span>
                        <label className="flex items-center gap-2 text-[11px] font-bold">
                            <span>عدد الأسهم:</span>
                            <input
                                type="range"
                                min={100}
                                max={Math.max(10000, initialQty * 2)}
                                step={100}
                                value={qty}
                                onChange={(e) => setQty(Number(e.target.value))}
                                className="accent-emerald-500 w-24 cursor-pointer"
                                aria-label="عدد الأسهم لحساب التطهير"
                            />
                            <span dir="ltr" className="font-mono font-black text-zinc-900 dark:text-white">
                                {qty.toLocaleString("en-US")}
                            </span>
                        </label>
                    </div>

                    <div className="w-full h-6 rounded-lg overflow-hidden flex text-[10.5px] font-black select-none">
                        <div
                            className="bg-emerald-500/85 text-white flex items-center justify-center px-2 truncate"
                            style={{ width: `${100 - pureSharePct}%` }}
                        >
                            صافي حلال: {netHalal.toFixed(1)} {curr}
                        </div>
                        {purifyAmt > 0 && (
                            <div
                                className="bg-amber-400/90 text-black flex items-center justify-center px-2 truncate"
                                style={{ width: `${pureSharePct}%` }}
                            >
                                تطهير: {purifyAmt.toFixed(1)} {curr}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {typeof sharia.zakat_amount === "number" && sharia.zakat_amount > 0 && (
                <div className="text-[11px] text-zinc-600 dark:text-zinc-400">
                    زكاة الأسهم المقدرة (2.5%): <strong className="font-mono text-zinc-900 dark:text-white">{sharia.zakat_amount.toFixed(2)} {curr}</strong>
                </div>
            )}
        </div>
    );
}

type PriceTrapsInput = NonNullable<ChatVisualsPayload["price_traps"]>;

/**
 * Dual-panel Bull vs Bear Traps Detector Card showing wick rejection % and relative volume.
 */
export function PriceTrapsRadarCard({ traps }: { traps: PriceTrapsInput }) {
    const bears = traps?.bearTraps || [];
    const bulls = traps?.bullTraps || [];
    if (bears.length === 0 && bulls.length === 0) return null;
    const curr = traps.currency || "ج.م";

    return (
        <div
            className="my-2.5 grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-right"
            dir="rtl"
            data-testid="price-traps-radar-card"
        >
            {/* Bear Traps (Bounce setups) */}
            <div className="rounded-2xl border border-emerald-500/35 bg-zinc-50 dark:bg-zinc-900/70 p-3 space-y-2 text-xs">
                <div className="flex items-center justify-between font-black text-emerald-700 dark:text-emerald-400">
                    <span className="flex items-center gap-1.5">
                        <TrendingUp className="w-4 h-4 shrink-0" />
                        <span>مصائد الدببة (ارتداد محتمل)</span>
                    </span>
                    <span dir="ltr" className="font-mono text-[10px]">Bear Trap ({bears.length})</span>
                </div>
                {bears.length > 0 ? (
                    <div className="space-y-1.5">
                        {bears.slice(0, 4).map((t) => (
                            <div
                                key={`bear-${t.symbol}`}
                                className="p-2 rounded-lg bg-white dark:bg-black/40 border border-zinc-200/70 dark:border-white/10 flex items-center justify-between gap-2"
                            >
                                <div>
                                    <span className="font-mono font-black">{t.symbol}</span>
                                    {t.close ? <span className="text-[10.5px] text-zinc-500 mr-1.5 font-mono">{fmtCoord(t.close)} {curr}</span> : null}
                                </div>
                                <div dir="ltr" className="text-[10.5px] font-mono text-emerald-600 dark:text-emerald-400 font-bold">
                                    {t.conviction ? `ثقة ${t.conviction}%` : "ارتداد"}{t.relativeVolume ? ` • ${t.relativeVolume}x` : ""}
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <p className="text-[11px] text-zinc-500">لا توجد مصائد دببة مسجلة حالياً.</p>
                )}
            </div>

            {/* Bull Traps (Rejection / Caution) */}
            <div className="rounded-2xl border border-rose-500/35 bg-zinc-50 dark:bg-zinc-900/70 p-3 space-y-2 text-xs">
                <div className="flex items-center justify-between font-black text-rose-700 dark:text-rose-400">
                    <span className="flex items-center gap-1.5">
                        <AlertTriangle className="w-4 h-4 shrink-0" />
                        <span>مصائد الثيران (فخ تصريف)</span>
                    </span>
                    <span dir="ltr" className="font-mono text-[10px]">Bull Trap ({bulls.length})</span>
                </div>
                {bulls.length > 0 ? (
                    <div className="space-y-1.5">
                        {bulls.slice(0, 4).map((t) => (
                            <div
                                key={`bull-${t.symbol}`}
                                className="p-2 rounded-lg bg-white dark:bg-black/40 border border-zinc-200/70 dark:border-white/10 flex items-center justify-between gap-2"
                            >
                                <div>
                                    <span className="font-mono font-black">{t.symbol}</span>
                                    {t.close ? <span className="text-[10.5px] text-zinc-500 mr-1.5 font-mono">{fmtCoord(t.close)} {curr}</span> : null}
                                </div>
                                <div dir="ltr" className="text-[10.5px] font-mono text-rose-600 dark:text-rose-400 font-bold">
                                    {t.conviction ? `تحذير ${t.conviction}%` : "تصريف"}{t.wickPct ? ` • فتيل ${t.wickPct}%` : ""}
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <p className="text-[11px] text-zinc-500">لا توجد مصائد ثيران مسجلة حالياً.</p>
                )}
            </div>
        </div>
    );
}

type DisclosureTimelineItem = NonNullable<ChatVisualsPayload["disclosures"]>[number];

/**
 * Chronological Disclosures & News Sentiment Timeline card rendered client-side.
 */
export function DisclosuresTimelineCard({ items }: { items: DisclosureTimelineItem[] }) {
    const valid = (items || []).filter((d) => d && (d.title || d.symbol));
    if (valid.length === 0) return null;

    const classifySentiment = (s?: string | number | null): "pos" | "neg" | "neu" => {
        if (typeof s === "number") return s > 0.15 ? "pos" : s < -0.15 ? "neg" : "neu";
        const str = String(s || "").toLowerCase();
        if (/pos|bull|ايجاب|إيجاب/.test(str)) return "pos";
        if (/neg|bear|سلب/.test(str)) return "neg";
        return "neu";
    };

    const posCount = valid.filter((d) => classifySentiment(d.sentiment) === "pos").length;
    const negCount = valid.filter((d) => classifySentiment(d.sentiment) === "neg").length;
    const overallLabel = posCount > negCount ? "غالب إيجابي" : negCount > posCount ? "غالب سلبي" : "متوازن / محايد";

    return (
        <div
            className="my-2.5 rounded-2xl border border-zinc-200 dark:border-white/15 bg-zinc-50 dark:bg-zinc-900/70 p-3 space-y-2 text-right"
            dir="rtl"
            data-testid="disclosures-timeline-card"
        >
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-1.5 font-black">
                    <Clock className="w-4 h-4 text-sky-500 shrink-0" />
                    <span>خط زمني لأهم الإفصاحات والأخبار</span>
                </div>
                <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                        posCount > negCount
                            ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30"
                            : negCount > posCount
                                ? "bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30"
                                : "bg-zinc-200/70 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 border-zinc-300 dark:border-white/15"
                    }`}
                >
                    المزاج: {overallLabel}
                </span>
            </div>

            <div className="space-y-1.5 border-r-2 border-sky-500/60 pr-3 mr-1">
                {valid.slice(0, 6).map((item, idx) => {
                    const tone = classifySentiment(item.sentiment);
                    return (
                        <div
                            key={`${item.symbol || "mkt"}-${idx}`}
                            className="p-2 rounded-lg bg-white dark:bg-black/40 border border-zinc-200/70 dark:border-white/10 flex flex-wrap items-center justify-between gap-2 text-[11px]"
                        >
                            <div className="min-w-0 flex-1 flex items-center gap-1.5 flex-wrap">
                                <span
                                    className={`w-2 h-2 rounded-full shrink-0 ${
                                        tone === "pos" ? "bg-emerald-500" : tone === "neg" ? "bg-rose-500" : "bg-amber-400"
                                    }`}
                                />
                                {item.symbol && (
                                    <span className="font-mono font-black px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800">
                                        {item.symbol}
                                    </span>
                                )}
                                <span className="text-zinc-800 dark:text-zinc-200 font-semibold truncate max-w-[360px]">
                                    {item.title || item.company_name}
                                </span>
                            </div>
                            {item.disclosure_date && (
                                <span dir="ltr" className="font-mono text-[10px] text-zinc-500 shrink-0">
                                    {item.disclosure_date}
                                </span>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}


