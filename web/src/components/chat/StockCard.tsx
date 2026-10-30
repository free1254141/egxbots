"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { 
    TrendingUp, 
    TrendingDown, 
    Minus, 
    Activity, 
    Zap, 
    BarChart2, 
    Copy, 
    Check, 
    ArrowUpRight, 
    Briefcase,
    Newspaper,
    Target,
    ShieldAlert,
    Scale,
    Building2,
    CheckCircle2,
    Share2,
    Sparkles
} from "lucide-react";

export interface StockData {
    symbol: string;
    nameAr?: string;
    nameEn?: string;
    companyName?: string;
    name?: string;
    price: number | string;
    currency?: string;
    changePercent?: number | string;
    change_percent?: number | string;
    change?: number | string;

    // Quantitative Trading Plan Metrics
    entryRange?: string;
    entry_range?: string;
    entryPrice?: number | string;
    entry_price?: number | string;
    target1?: string | number;
    target_1?: string | number;
    target2?: string | number;
    target_2?: string | number;
    stopLoss?: string | number;
    stop_loss?: string | number;
    riskReward?: string | number;
    risk_reward?: string | number;
    timeframe?: string;

    // Technical Indicators & Liquidity
    rsi?: number | string;
    macdSignal?: string;
    macd_signal?: string;
    macd?: number | string | { signal?: string; value?: number | string; histogram?: number | string };
    volume?: number | string;
    rVol?: number | string;
    r_vol?: number | string;
    high?: number | string;
    low?: number | string;

    // Classification & Badges
    sector?: string;
    isShariah?: boolean;
    is_sharia_compliant?: boolean;
    sharia_index?: string;
    signalType?: "opportunity" | "breakout" | "accumulation" | "swing" | "scalp" | "momentum" | string;
    signal_type?: string;
    signalStrength?: string;
    recommendation?: string;
    updatedAt?: string;
    [key: string]: any;
}

export interface StockCardProps {
    stock?: StockData;
    data?: StockData;
    className?: string;
    onSymbolClick?: (symbol: string) => void;
    onNewsClick?: (symbol: string) => void;
    onAddToPortfolio?: (symbol: string) => void;
}

export function StockCard({ 
    stock, 
    data, 
    className = "", 
    onSymbolClick,
    onNewsClick,
    onAddToPortfolio 
}: StockCardProps) {
    const router = useRouter();
    const [copied, setCopied] = useState(false);
    const [addedToPortfolio, setAddedToPortfolio] = useState(false);

    // Support flexible payload formats
    const stockData = stock || data;

    if (!stockData || !stockData.symbol) {
        return null;
    }

    const symbol = String(stockData.symbol).toUpperCase().replace(".CA", "");
    const nameAr = stockData.nameAr || stockData.companyName || stockData.name || symbol;
    const nameEn = stockData.nameEn || (stockData.nameAr ? symbol : undefined);
    
    // Parse price
    const rawPrice = typeof stockData.price === "number" ? stockData.price : parseFloat(String(stockData.price || "0"));
    const formattedPrice = isNaN(rawPrice) 
        ? "0.00" 
        : rawPrice.toLocaleString("ar-EG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    
    const currency = stockData.currency || "ج.م";

    // Parse change percentage
    const rawChangePct = stockData.changePercent ?? stockData.change_percent ?? stockData.change ?? 0;
    const changePctVal = typeof rawChangePct === "number" ? rawChangePct : parseFloat(String(rawChangePct || "0"));
    const isPositive = changePctVal > 0;
    const isNegative = changePctVal < 0;
    const formattedChangePct = `${isPositive ? "+" : ""}${changePctVal.toFixed(2)}%`;

    // Parse RSI
    const rawRsi = stockData.rsi;
    const rsiVal = typeof rawRsi === "number" 
        ? rawRsi 
        : rawRsi !== undefined 
            ? parseFloat(String(rawRsi)) 
            : undefined;

    let rsiLabel = "متوازن";
    let rsiColor = "text-amber-500 bg-amber-500/10 border-amber-500/30";
    let rsiProgressColor = "bg-amber-500";
    
    if (rsiVal !== undefined && !isNaN(rsiVal)) {
        if (rsiVal >= 70) {
            rsiLabel = "تشبع شرائي";
            rsiColor = "text-rose-500 bg-rose-500/10 border-rose-500/30";
            rsiProgressColor = "bg-rose-500";
        } else if (rsiVal <= 35) {
            rsiLabel = "تشبع بيعي (فرصة)";
            rsiColor = "text-emerald-500 bg-emerald-500/10 border-emerald-500/30";
            rsiProgressColor = "bg-emerald-500";
        } else if (rsiVal > 50) {
            rsiLabel = "زخم صاعد";
            rsiColor = "text-emerald-500 bg-emerald-500/10 border-emerald-500/30";
            rsiProgressColor = "bg-emerald-500";
        }
    }

    // Quantitative Trading Plan Values
    const entryRange = stockData.entryRange || stockData.entry_range || (
        stockData.entryPrice || stockData.entry_price 
            ? `${Number(stockData.entryPrice || stockData.entry_price).toFixed(2)} ج.م` 
            : undefined
    );
    
    const target1 = stockData.target1 || stockData.target_1 || stockData.target;
    const target2 = stockData.target2 || stockData.target_2;
    const stopLoss = stockData.stopLoss || stockData.stop_loss;
    const riskReward = stockData.riskReward || stockData.risk_reward;
    const relativeVol = stockData.rVol || stockData.r_vol;
    const sector = stockData.sector;
    const isShariah = Boolean(
        stockData.isShariah ?? stockData.is_sharia_compliant ?? (stockData.sharia_index === "EGX33")
    );

    const signalType = stockData.signalType || stockData.signal_type || stockData.recommendation || "فرصة رصد فني";

    const handleCopySignal = (e: React.MouseEvent) => {
        e.stopPropagation();
        const signalSummary = [
            `🎯 بطاقة سهم #${symbol} (${nameAr}) — EGX BOTS AI`,
            `📍 السعر الحالي: ${formattedPrice} ${currency} (${formattedChangePct})`,
            entryRange ? `🎯 نطاق الدخول: ${entryRange}` : null,
            target1 ? `🚀 المستهدف: ${target1}` : null,
            stopLoss ? `🛑 وقف الخسارة: ${stopLoss}` : null,
            riskReward ? `⚖️ العائد للمخاطرة: ${riskReward}` : null,
            rsiVal ? `📊 مؤشر RSI: ${rsiVal.toFixed(1)}` : null,
            `🔗 الشارت: https://egxbots.com/chart?symbol=${symbol}`
        ].filter(Boolean).join("\n");

        navigator.clipboard.writeText(signalSummary);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const handleOpenChart = (e: React.MouseEvent) => {
        e.stopPropagation();
        if (typeof window !== "undefined") {
            try {
                router.push(`/chart?symbol=${symbol}`);
            } catch {
                window.location.href = `/chart?symbol=${symbol}`;
            }
        }
    };

    const handleAddToPortfolio = (e: React.MouseEvent) => {
        e.stopPropagation();
        if (onAddToPortfolio) {
            onAddToPortfolio(symbol);
        } else if (onSymbolClick) {
            onSymbolClick(`أضف سهم ${symbol} لمحفظتي`);
        }
        setAddedToPortfolio(true);
        setTimeout(() => setAddedToPortfolio(false), 3000);
    };

    return (
        <div 
            dir="rtl"
            className={`my-3 relative overflow-hidden rounded-3xl border-2 border-zinc-200 dark:border-white/15 bg-white dark:bg-[#0c0c0e] p-4 sm:p-5 text-right shadow-xl transition-all duration-300 hover:border-amber-400/80 hover:shadow-2xl group ${className}`}
        >
            {/* Top ambient color glow */}
            <div 
                className={`absolute -top-16 -right-16 h-40 w-40 rounded-full blur-3xl pointer-events-none transition-all duration-500 ${
                    isPositive ? "bg-emerald-500/15" : isNegative ? "bg-rose-500/15" : "bg-amber-500/15"
                }`} 
            />

            {/* Top Header: Symbol Badge, Badges, & Share Actions */}
            <div className="flex items-start justify-between gap-2 relative z-10">
                <div className="flex items-center gap-2.5">
                    {/* Symbol Pill Badge */}
                    <div className="flex items-center justify-center rounded-xl bg-[#FFE600] text-black font-mono font-black text-xs sm:text-sm px-3 py-1.5 border-2 border-black shadow-[2px_2px_0_0_#000]">
                        #{symbol}
                    </div>

                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className="font-black text-base sm:text-lg text-zinc-950 dark:text-white tracking-wide">
                                {nameAr}
                            </h3>
                            {nameEn && nameEn !== nameAr && (
                                <span className="text-[11px] text-zinc-400 font-mono hidden sm:inline-block">
                                    ({nameEn})
                                </span>
                            )}
                        </div>

                        {sector && (
                            <div className="flex items-center gap-1 text-[11px] font-semibold text-zinc-500 dark:text-zinc-400 mt-0.5">
                                <Building2 className="w-3 h-3 text-amber-500" />
                                <span>{sector}</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* Badges on the Left */}
                <div className="flex items-center gap-1.5 flex-wrap justify-end">
                    {isShariah && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 text-[10px] font-black">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                            EGX33 شرعي
                        </span>
                    )}

                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30 text-[10px] font-black">
                        <Sparkles className="w-2.5 h-2.5" />
                        {signalType}
                    </span>

                    <button
                        type="button"
                        onClick={handleCopySignal}
                        className="grid h-7 w-7 place-items-center rounded-lg border border-zinc-200 dark:border-white/20 bg-zinc-100 dark:bg-zinc-900 text-zinc-600 dark:text-zinc-300 hover:text-black dark:hover:text-white transition-colors cursor-pointer"
                        title="نسخ ملخص الإشارة"
                        aria-label="نسخ ملخص الإشارة"
                    >
                        {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                </div>
            </div>

            {/* Price & Change Banner */}
            <div className="mt-3.5 pt-3 border-t border-zinc-200/80 dark:border-white/10 flex items-baseline justify-between gap-2 relative z-10">
                <div className="flex items-baseline gap-1.5">
                    <span className="font-mono font-black text-2xl sm:text-3xl text-zinc-950 dark:text-white tracking-tight">
                        {formattedPrice}
                    </span>
                    <span className="text-xs font-black text-amber-600 dark:text-amber-400">
                        {currency}
                    </span>
                </div>

                {/* Change Percent Pill */}
                <div className="flex items-center gap-2">
                    <div className={`flex items-center gap-1 px-2.5 py-1 rounded-xl font-mono text-xs sm:text-sm font-black border ${
                        isPositive 
                            ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-600 dark:text-emerald-400" 
                            : isNegative 
                                ? "bg-rose-500/15 border-rose-500/40 text-rose-600 dark:text-rose-400" 
                                : "bg-zinc-100 dark:bg-zinc-900 border-zinc-200 dark:border-white/20 text-zinc-700 dark:text-zinc-300"
                    }`}>
                        {isPositive && <TrendingUp className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 stroke-[2.5]" />}
                        {isNegative && <TrendingDown className="w-3.5 h-3.5 text-rose-600 dark:text-rose-400 stroke-[2.5]" />}
                        {!isPositive && !isNegative && <Minus className="w-3.5 h-3.5 text-zinc-500 stroke-[2.5]" />}
                        <span dir="ltr">{formattedChangePct}</span>
                    </div>

                    <div className="flex items-center gap-1 text-[10px] font-bold text-zinc-500 dark:text-zinc-400">
                        <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                        </span>
                        <span>لحظي</span>
                    </div>
                </div>
            </div>

            {/* Quantitative Trading Plan (2x2 Grid) — Domain Specific Specialty */}
            {(entryRange || target1 || stopLoss || riskReward) && (
                <div className="mt-3.5 grid grid-cols-2 gap-2 sm:gap-2.5 relative z-10">
                    {/* 1. Entry Range */}
                    <div className="p-2.5 rounded-2xl bg-zinc-50 dark:bg-zinc-900/70 border border-zinc-200 dark:border-white/10 flex flex-col justify-between">
                        <div className="flex items-center gap-1 text-[11px] font-extrabold text-zinc-500 dark:text-zinc-400">
                            <Zap className="w-3.5 h-3.5 text-amber-500" />
                            <span>نطاق الدخول</span>
                        </div>
                        <div className="font-mono font-black text-xs sm:text-sm text-zinc-900 dark:text-zinc-100 mt-1">
                            {entryRange || `${formattedPrice} ج.م`}
                        </div>
                    </div>

                    {/* 2. Target 1 */}
                    <div className="p-2.5 rounded-2xl bg-emerald-500/5 dark:bg-emerald-950/20 border border-emerald-500/20 flex flex-col justify-between">
                        <div className="flex items-center gap-1 text-[11px] font-extrabold text-emerald-600 dark:text-emerald-400">
                            <Target className="w-3.5 h-3.5" />
                            <span>المستهدف</span>
                        </div>
                        <div className="font-mono font-black text-xs sm:text-sm text-emerald-600 dark:text-emerald-400 mt-1">
                            {target1 ? String(target1) : "مستهدف مفتوح"}
                        </div>
                    </div>

                    {/* 3. Stop Loss */}
                    <div className="p-2.5 rounded-2xl bg-rose-500/5 dark:bg-rose-950/20 border border-rose-500/20 flex flex-col justify-between">
                        <div className="flex items-center gap-1 text-[11px] font-extrabold text-rose-600 dark:text-rose-400">
                            <ShieldAlert className="w-3.5 h-3.5" />
                            <span>وقف الخسارة</span>
                        </div>
                        <div className="font-mono font-black text-xs sm:text-sm text-rose-600 dark:text-rose-400 mt-1">
                            {stopLoss ? String(stopLoss) : "أسفل الدعم 3%"}
                        </div>
                    </div>

                    {/* 4. Risk / Reward */}
                    <div className="p-2.5 rounded-2xl bg-zinc-50 dark:bg-zinc-900/70 border border-zinc-200 dark:border-white/10 flex flex-col justify-between">
                        <div className="flex items-center gap-1 text-[11px] font-extrabold text-zinc-500 dark:text-zinc-400">
                            <Scale className="w-3.5 h-3.5 text-cyan-500" />
                            <span>العائد للمخاطرة</span>
                        </div>
                        <div className="font-mono font-black text-xs sm:text-sm text-zinc-900 dark:text-zinc-100 mt-1">
                            {riskReward ? String(riskReward) : "1 : 2.0 🎯"}
                        </div>
                    </div>
                </div>
            )}

            {/* Momentum & Liquidity Gauge (RSI + Relative Vol) */}
            <div className="mt-3 p-3 rounded-2xl bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-white/10 flex flex-wrap items-center justify-between gap-2 relative z-10">
                {/* RSI Meter */}
                <div className="flex items-center gap-2 flex-1 min-w-[140px]">
                    <div className="flex items-center gap-1 text-xs font-bold text-zinc-600 dark:text-zinc-400">
                        <Activity className="w-3.5 h-3.5 text-amber-500" />
                        <span>RSI:</span>
                        <span className="font-mono font-black text-zinc-900 dark:text-white">
                            {rsiVal !== undefined && !isNaN(rsiVal) ? rsiVal.toFixed(1) : "52.0"}
                        </span>
                    </div>

                    {rsiVal !== undefined && !isNaN(rsiVal) && (
                        <div className="w-16 bg-zinc-200 dark:bg-zinc-800 h-1.5 rounded-full overflow-hidden">
                            <div 
                                className={`h-full rounded-full ${rsiProgressColor}`}
                                style={{ width: `${Math.min(Math.max(rsiVal, 0), 100)}%` }}
                            />
                        </div>
                    )}

                    <span className={`text-[10px] font-extrabold px-1.5 py-0.5 rounded-md border ${rsiColor}`}>
                        {rsiLabel}
                    </span>
                </div>

                {/* Relative Volume Badge */}
                {relativeVol && (
                    <div className="text-[11px] font-black text-zinc-700 dark:text-zinc-300 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-lg flex items-center gap-1">
                        <BarChart2 className="w-3 h-3 text-amber-500" />
                        <span>السيولة: <strong>{String(relativeVol)}x</strong></span>
                    </div>
                )}
            </div>

            {/* Actionable CTAs — Just like the Broker card in the reference screenshot */}
            <div className="mt-4 pt-3 border-t border-zinc-200 dark:border-white/10 flex flex-col gap-2 relative z-10">
                {/* Primary CTA Button: Open Chart */}
                <button
                    type="button"
                    onClick={handleOpenChart}
                    className="w-full py-2.5 px-4 rounded-xl bg-[#FFE600] hover:bg-yellow-300 text-black font-black text-xs sm:text-sm border-2 border-black shadow-[3px_3px_0_0_#000] active:translate-x-0.5 active:translate-y-0.5 transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                    <BarChart2 className="w-4 h-4 stroke-[2.5]" />
                    <span>فتح الشارت والمستويات اللحظية</span>
                    <ArrowUpRight className="w-4 h-4 stroke-[2.5]" />
                </button>

                {/* Secondary Quick-Action Buttons */}
                <div className="grid grid-cols-2 gap-2">
                    <button
                        type="button"
                        onClick={handleAddToPortfolio}
                        className={`py-2 px-3 rounded-xl border text-xs font-black transition-all flex items-center justify-center gap-1.5 cursor-pointer active:scale-95 ${
                            addedToPortfolio 
                                ? "bg-emerald-500 text-white border-emerald-600 shadow-sm"
                                : "bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-900 dark:hover:bg-zinc-800 text-zinc-900 dark:text-white border-zinc-300 dark:border-white/20"
                        }`}
                    >
                        {addedToPortfolio ? (
                            <>
                                <CheckCircle2 className="w-3.5 h-3.5" />
                                <span>تمت الإضافة للمحفظة ✅</span>
                            </>
                        ) : (
                            <>
                                <Briefcase className="w-3.5 h-3.5 text-amber-500" />
                                <span>أضف للمحفظة</span>
                            </>
                        )}
                    </button>

                    <button
                        type="button"
                        onClick={(e) => {
                            e.stopPropagation();
                            if (onNewsClick) {
                                onNewsClick(symbol);
                            } else if (onSymbolClick) {
                                onSymbolClick(`أخبار سهم ${symbol}`);
                            }
                        }}
                        className="py-2 px-3 rounded-xl bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-900 dark:hover:bg-zinc-800 text-zinc-900 dark:text-white border border-zinc-300 dark:border-white/20 text-xs font-black transition-all flex items-center justify-center gap-1.5 cursor-pointer active:scale-95"
                    >
                        <Newspaper className="w-3.5 h-3.5 text-cyan-500" />
                        <span>آخر الأخبار</span>
                    </button>
                </div>
            </div>
        </div>
    );
}

export default StockCard;
