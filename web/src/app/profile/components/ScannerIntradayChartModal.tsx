"use client";

import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  X,
  TrendingUp,
  Clock,
  Target,
  Zap,
  Activity,
  Calendar as CalendarIcon,
  Loader2,
  Sparkles,
  Info
} from "lucide-react";
import { createChart, ColorType, IChartApi, ISeriesApi, CrosshairMode } from "lightweight-charts";

interface ScannerIntradayChartModalProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string;
  date: string;
  toDate?: string;
  signalTime?: string;
  signalPrice?: number;
  exitTime?: string;
  exitPrice?: number;
  status?: string;
  scannerType?: string;
  isAr?: boolean;
  onGainLoaded?: (data: { symbol: string; max_gain_pct: number; peak_price: number; peak_time: string }) => void;
}

interface IntradaySessionPayload {
  symbol: string;
  date: string;
  to_date?: string;
  is_multiday?: boolean;
  session_open: number;
  session_close: number;
  session_high: number;
  peak_time: string;
  peak_datetime?: string;
  session_low: number;
  session_gain_pct: number;
  session_max_gain_pct: number;
  signal: {
    time: string;
    datetime?: string;
    price: number;
    max_gain_pct: number;
  };
  candles: Array<{
    time: string;
    datetime: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>;
  bars_count: number;
}

const CLIENT_SESSION_CACHE = new Map<string, IntradaySessionPayload>();

export async function prefetchIntradaySession(
  symbol: string,
  date: string,
  signalTime?: string,
  signalPrice?: number,
  toDate?: string
): Promise<IntradaySessionPayload | null> {
  const cacheKey = `${symbol}_${date}_${toDate || date}_${signalTime || "10:15"}`;
  if (CLIENT_SESSION_CACHE.has(cacheKey)) {
    return CLIENT_SESSION_CACHE.get(cacheKey)!;
  }
  try {
    const params = new URLSearchParams({ symbol, date });
    if (toDate && toDate !== date) params.set("to_date", toDate);
    if (signalTime) params.set("signal_time", signalTime);
    if (signalPrice) params.set("signal_price", String(signalPrice));
    const res = await fetch(`/api/scanner/intraday-session?${params.toString()}`);
    if (res.ok) {
      const json = await res.json();
      CLIENT_SESSION_CACHE.set(cacheKey, json);
      try {
        sessionStorage.setItem(`egx_intraday_${cacheKey}`, JSON.stringify(json));
      } catch {}
      return json;
    }
  } catch {}
  return null;
}

export default function ScannerIntradayChartModal({
  isOpen,
  onClose,
  symbol,
  date,
  toDate,
  signalTime = "10:15",
  signalPrice,
  exitTime,
  exitPrice,
  status,
  scannerType = "volume_surge",
  isAr = true,
  onGainLoaded,
}: ScannerIntradayChartModalProps) {
  const [data, setData] = useState<IntradaySessionPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  // Esc key listener
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      window.addEventListener("keydown", handleEsc);
      document.body.style.overflow = "hidden";
    }
    return () => {
      window.removeEventListener("keydown", handleEsc);
      document.body.style.overflow = "unset";
    };
  }, [isOpen, onClose]);

  // Fetch session data with intelligent caching (instant 0ms chart presentation)
  useEffect(() => {
    if (!isOpen || !symbol) return;

    let isCancelled = false;
    const cacheKey = `${symbol}_${date}_${toDate || date}_${signalTime || "10:15"}`;

    // 1. Instant cache check (in-memory or sessionStorage)
    let cached = CLIENT_SESSION_CACHE.get(cacheKey);
    if (!cached && typeof window !== "undefined") {
      try {
        const stored = sessionStorage.getItem(`egx_intraday_${cacheKey}`);
        if (stored) {
          cached = JSON.parse(stored);
          if (cached) CLIENT_SESSION_CACHE.set(cacheKey, cached);
        }
      } catch {}
    }

    if (cached) {
      setData(cached);
      setLoading(false);
      setError(null);
      if (cached?.signal && typeof cached.signal.max_gain_pct === "number") {
        onGainLoaded?.({
          symbol: cached.symbol || symbol,
          max_gain_pct: cached.signal.max_gain_pct,
          peak_price: cached.session_high,
          peak_time: cached.peak_time,
        });
      }
    } else {
      setLoading(true);
      setError(null);
    }

    const fetchData = async () => {
      try {
        const params = new URLSearchParams({
          symbol,
          date,
        });
        if (toDate && toDate !== date) params.set("to_date", toDate);
        if (signalTime) params.set("signal_time", signalTime);
        if (signalPrice) params.set("signal_price", String(signalPrice));

        const res = await fetch(`/api/scanner/intraday-session?${params.toString()}`);
        if (!res.ok) throw new Error("Failed to fetch session bars");

        const json: IntradaySessionPayload = await res.json();
        CLIENT_SESSION_CACHE.set(cacheKey, json);
        try {
          sessionStorage.setItem(`egx_intraday_${cacheKey}`, JSON.stringify(json));
        } catch {}

        if (!isCancelled) {
          setData(json);
          setLoading(false);
          if (json?.signal && typeof json.signal.max_gain_pct === "number") {
            onGainLoaded?.({
              symbol: json.symbol || symbol,
              max_gain_pct: json.signal.max_gain_pct,
              peak_price: json.session_high,
              peak_time: json.peak_time,
            });
          }
        }
      } catch (err: any) {
        if (!isCancelled) {
          console.error("Intraday fetch error:", err);
          if (!cached) {
            setError(isAr ? "تعذر تحميل شارت الجلسة، حاول مجدداً" : "Failed to load session chart");
          }
        }
      } finally {
        if (!isCancelled) setLoading(false);
      }
    };

    fetchData();

    return () => {
      isCancelled = true;
    };
  }, [isOpen, symbol, date, toDate, signalTime, signalPrice, isAr]);

  // Initialize and populate lightweight-chart
  useEffect(() => {
    if (!chartContainerRef.current || !data || data.candles.length === 0) return;

    // Clean up previous instance
    if (chartInstanceRef.current) {
      chartInstanceRef.current.remove();
      chartInstanceRef.current = null;
    }

    const container = chartContainerRef.current;
    const width = container.clientWidth || 800;
    const height = 360;
    const isMultiDay = Boolean(data.is_multiday || (data.to_date && data.to_date !== data.date));

    const chart = createChart(container, {
      width,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#09090b" },
        textColor: "#e4e4e7",
        fontSize: 11,
        fontFamily: "monospace",
      },
      grid: {
        vertLines: { color: "#27272a" },
        horzLines: { color: "#27272a" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      timeScale: {
        borderColor: "#3f3f46",
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
        tickMarkFormatter: (time: number) => {
          const d = new Date(time * 1000);
          const hours = String(d.getHours()).padStart(2, "0");
          const mins = String(d.getMinutes()).padStart(2, "0");
          if (isMultiDay) {
            const m = d.getMonth() + 1;
            const day = d.getDate();
            return `${m}/${day} ${hours}:${mins}`;
          }
          return `${hours}:${mins}`;
        },
      },
      localization: {
        timeFormatter: (time: number) => {
          const d = new Date(time * 1000);
          const hours = String(d.getHours()).padStart(2, "0");
          const mins = String(d.getMinutes()).padStart(2, "0");
          if (isMultiDay) {
            const m = d.getMonth() + 1;
            const day = d.getDate();
            return `${m}/${day} ${hours}:${mins}`;
          }
          return `${hours}:${mins}`;
        },
      },
      rightPriceScale: {
        borderColor: "#3f3f46",
        scaleMargins: {
          top: 0.15,
          bottom: 0.15,
        },
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#10b981",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });

    chartInstanceRef.current = chart;
    seriesRef.current = series;

    // Convert candles to timestamp seconds
    const formattedData = data.candles.map((c, index) => {
      const dtStr = c.datetime ? c.datetime.replace(" ", "T") + ":00" : `${data.date}T${c.time}:00`;
      const parsedTs = Math.floor(new Date(dtStr).getTime() / 1000);
      return {
        time: (parsedTs || index) as any,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        origTime: c.time,
        origDatetime: c.datetime || `${data.date} ${c.time}`,
      };
    });

    series.setData(formattedData);

    // Build markers for Signal Time, Peak High, and Exit
    const markers: any[] = [];

    // 1. Signal Marker
    const targetSigDt = data.signal.datetime || `${data.date} ${data.signal.time || signalTime || "10:15"}`;
    let sigIndex = formattedData.findIndex((c) => c.origDatetime >= targetSigDt);
    if (sigIndex === -1) {
      sigIndex = formattedData.findIndex((c) => c.origTime >= (data.signal.time || signalTime || "10:15"));
    }
    const signalCandle = sigIndex !== -1 ? formattedData[sigIndex] : formattedData[0];

    if (signalCandle) {
      markers.push({
        time: signalCandle.time,
        position: "belowBar",
        color: "#FFE600",
        shape: "arrowUp",
        text: isAr
          ? `📍 إشارة دخول (${signalCandle.origTime}) • ${data.signal.price || signalCandle.close} ج.م`
          : `📍 Signal Entry (${signalCandle.origTime}) • ${data.signal.price || signalCandle.close} EGP`,
      });
    }

    // 2. Peak High Marker (strictly after signal)
    const postCandles = formattedData.slice(sigIndex);
    const peakCandle = postCandles.length > 0
      ? postCandles.reduce((max, c) => (c.high > max.high ? c : max), signalCandle)
      : signalCandle;

    if (peakCandle) {
      const isPositiveGain = (data.signal.max_gain_pct || 0) > 0;
      markers.push({
        time: peakCandle.time,
        position: "aboveBar",
        color: isPositiveGain ? "#10b981" : "#a1a1aa",
        shape: "arrowDown",
        text: isAr
          ? (isPositiveGain
              ? `🎯 أعلى قمة بعد الإشارة (${peakCandle.origTime}) • ${data.session_high} ج.م (+${data.signal.max_gain_pct}%)`
              : `🔻 أعلى مستوى بعد الإشارة (${peakCandle.origTime}) • ${data.session_high} ج.م (0.0%)`)
          : (isPositiveGain
              ? `🎯 Peak After Signal (${peakCandle.origTime}) • ${data.session_high} EGP (+${data.signal.max_gain_pct}%)`
              : `🔻 Highest After Signal (${peakCandle.origTime}) • ${data.session_high} EGP (0.0%)`),
      });
    }

    // 3. Exit Marker (if closed or stopped out)
    if (exitPrice || status === "target_hit" || status === "stopped_out") {
      let exitIdx = -1;
      if (toDate && exitTime) {
        exitIdx = formattedData.findIndex((c) => c.origDatetime >= `${toDate} ${exitTime}`);
      }
      if (exitIdx === -1 && toDate) {
        for (let i = formattedData.length - 1; i >= 0; i--) {
          if (formattedData[i].origDatetime.startsWith(toDate)) {
            exitIdx = i;
            break;
          }
        }
      }
      const exitCandle = exitIdx !== -1 ? formattedData[exitIdx] : formattedData[formattedData.length - 1];
      const isWin = status === "target_hit" || (exitPrice && signalPrice && exitPrice > signalPrice);
      markers.push({
        time: exitCandle.time,
        position: isWin ? "aboveBar" : "belowBar",
        color: isWin ? "#10b981" : "#ef4444",
        shape: isWin ? "arrowDown" : "arrowUp",
        text: isAr
          ? (isWin ? `🏁 خروج / جني أرباح • ${exitPrice || exitCandle.close} ج.م` : `🛑 كسر الوقف / خروج • ${exitPrice || exitCandle.close} ج.م`)
          : (isWin ? `🏁 Exit / Target • ${exitPrice || exitCandle.close} EGP` : `🛑 Stop Loss Hit • ${exitPrice || exitCandle.close} EGP`),
      });
    }

    // Sort markers by time
    markers.sort((a, b) => (Number(a.time) || 0) - (Number(b.time) || 0));
    series.setMarkers(markers);
    chart.timeScale().fitContent();

    // Resize handler
    const handleResize = () => {
      if (chartContainerRef.current && chartInstanceRef.current) {
        chartInstanceRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (chartInstanceRef.current) {
        chartInstanceRef.current.remove();
        chartInstanceRef.current = null;
      }
    };
  }, [data, isAr, signalTime, toDate, status, exitPrice]);

  if (!isOpen) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[11000] flex items-center justify-center p-3 sm:p-6"
      dir={isAr ? "rtl" : "ltr"}
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/85 backdrop-blur-md transition-opacity"
        onClick={onClose}
      />

      {/* Modal Container */}
      <div className="relative w-full max-w-4xl bg-zinc-950 border-4 border-black dark:border-white shadow-[8px_8px_0px_rgba(0,0,0,1)] dark:shadow-[8px_8px_0px_rgba(255,255,255,1)] flex flex-col max-h-[92vh] z-10 animate-in zoom-in-95 duration-150 overflow-hidden text-white">
        {/* Modal Header */}
        <div className="p-2.5 sm:p-5 border-b-2 sm:border-b-4 border-black dark:border-white bg-[#FFE600] text-black flex items-center justify-between gap-2 sm:gap-4">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            <div className="hidden sm:flex h-10 w-10 border-2 border-black bg-black text-[#FFE600] items-center justify-center font-black shadow-[2px_2px_0px_rgba(0,0,0,1)] shrink-0">
              <TrendingUp className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                <span className="font-mono text-sm sm:text-xl font-black bg-black text-[#FFE600] px-2 py-0.5 border-2 border-black shadow-[2px_2px_0px_rgba(0,0,0,1)] shrink-0">
                  {symbol}
                </span>
                <h3 className="text-xs sm:text-lg font-black uppercase tracking-tight truncate">
                  <span className="sm:hidden">
                    {data?.is_multiday ? (isAr ? "مسار الصفقة الكامل" : "Trade Journey") : (isAr ? "شارت 15 دقيقة • الجلسة" : "15M Candlestick")}
                  </span>
                  <span className="hidden sm:inline">
                    {data?.is_multiday
                      ? (isAr ? `شارت شمع 15 دقيقة • مسار الصفقة الكامل (${data.date} إلى ${data.to_date})` : `15M Candlestick • Full Trade Path (${data.date} to ${data.to_date})`)
                      : (isAr ? `شارت شمع 15 دقيقة • جلسة التداول الكاملة (${date})` : `15M Candlestick • Full Trading Session (${date})`)}
                  </span>
                </h3>
              </div>
              <p className="text-[10px] sm:text-xs font-mono font-bold text-black mt-0.5 sm:mt-1 flex items-center gap-1.5 sm:gap-2">
                <CalendarIcon className="w-3 h-3 sm:w-3.5 sm:h-3.5 shrink-0" />
                <span>{data?.is_multiday ? `${data.date} ➔ ${data.to_date}` : date}</span>
                <span>•</span>
                <span dir="ltr" className="inline-block font-mono">
                  {data?.is_multiday ? (isAr ? "متابعة متواصلة من الدخول" : "Live Trajectory") : "10:00 AM - 02:30 PM (EGX Session)"}
                </span>
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="h-8 w-8 sm:h-10 sm:w-10 border-2 border-black bg-black hover:bg-rose-600 text-white flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] font-black transition-all active:translate-x-0.5 active:translate-y-0.5 shrink-0"
            title={isAr ? "إغلاق (Esc)" : "Close"}
          >
            <X className="w-4 h-4 sm:w-5 sm:h-5" />
          </button>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="p-16 flex flex-col items-center justify-center gap-3 bg-zinc-900">
            <Loader2 className="w-8 h-8 animate-spin text-[#FFE600]" />
            <span className="font-mono font-bold text-xs text-zinc-400">
              {isAr ? "جاري جلب شموع الـ 15 دقيقة للجلسة وحساب القمم..." : "Loading 15m session candles & peak metrics..."}
            </span>
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <div className="p-10 text-center bg-zinc-900 font-bold text-xs text-rose-400">
            {error}
          </div>
        )}

        {/* Content Body */}
        {!loading && data && (() => {
          const isStoppedOut = status === "stopped_out";
          const isTargetHit = status === "target_hit";
          const isClosed = isStoppedOut || isTargetHit || status === "expired";
          const entryP = signalPrice || data.signal.price || 1;
          const finalExitP = exitPrice || data.session_close;
          const realizedReturn = exitPrice
            ? Number((((exitPrice - entryP) / entryP) * 100).toFixed(2))
            : Number((((data.session_close - entryP) / entryP) * 100).toFixed(2));
          const isRealizedWin = realizedReturn > 0;

          return (
            <div className="p-3 sm:p-6 space-y-3 sm:space-y-4 overflow-y-auto flex-1">
              {/* Session Performance KPI Chips Bar */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-1.5 sm:gap-2.5 font-mono text-xs font-bold">
                {/* Open */}
                <div className="p-2 sm:p-2.5 bg-zinc-900 border-2 border-zinc-700">
                  <span className="text-[10px] text-zinc-400 block">{isAr ? "افتتاح الجلسة" : "Session Open"}</span>
                  <span className="text-xs sm:text-sm font-black text-white">{data.session_open} ج.م</span>
                </div>

                {/* Signal Trigger */}
                <div className="p-2 sm:p-2.5 bg-amber-950/40 border-2 border-amber-500 text-amber-300">
                  <span className="text-[10px] text-amber-400 block flex items-center gap-1 truncate">
                    <Clock className="w-3 h-3 shrink-0" />
                    {isAr ? `الإشارة (${data.signal.time})` : `Signal (${data.signal.time})`}
                  </span>
                  <span className="text-xs sm:text-sm font-black">{data.signal.price} ج.م</span>
                </div>

                {/* Peak High After Signal */}
                <div className="p-2 sm:p-2.5 bg-zinc-900 border-2 border-zinc-700 text-zinc-300">
                  <span className="text-[10px] text-zinc-400 block flex items-center gap-1 truncate">
                    <Target className="w-3 h-3 shrink-0" />
                    {isAr ? `أعلى قمة بعد الإشارة (${data.peak_time})` : `Peak (${data.peak_time})`}
                  </span>
                  <span className="text-xs sm:text-sm font-black text-white">{data.session_high} ج.م</span>
                </div>

                {/* Outcome Chip (Target Hit / Stopped Out / Active) */}
                {isStoppedOut ? (
                  <div className="p-2 sm:p-2.5 bg-rose-600 text-white border-2 border-black font-black">
                    <span className="text-[10px] uppercase block truncate">{isAr ? "نتيجة الصفقة (وقف الخسارة)" : "Stop Loss Hit"}</span>
                    <span className="text-sm sm:text-base font-black">{realizedReturn}%</span>
                  </div>
                ) : isTargetHit ? (
                  <div className="p-2 sm:p-2.5 bg-emerald-500 text-black border-2 border-black font-black">
                    <span className="text-[10px] uppercase block truncate">{isAr ? "نتيجة الصفقة (تحقق الهدف)" : "Target Hit"}</span>
                    <span className="text-sm sm:text-base font-black">+{realizedReturn}%</span>
                  </div>
                ) : (
                  <div className="p-2 sm:p-2.5 bg-amber-400 text-black border-2 border-black font-black">
                    <span className="text-[10px] uppercase block truncate">{isAr ? "أقصى صعود لحظي (نشطة)" : "Max Peak Gain"}</span>
                    <span className="text-sm sm:text-base font-black">+{data.signal.max_gain_pct}%</span>
                  </div>
                )}

                {/* Close / Exit Price */}
                <div className="p-2 sm:p-2.5 bg-zinc-900 border-2 border-zinc-700 col-span-2 sm:col-span-1">
                  <span className="text-[10px] text-zinc-400 block">
                    {isClosed ? (isAr ? "سعر الخروج" : "Exit Price") : (isAr ? "آخر سعر لحظي" : "Current Price")}
                  </span>
                  <span className="text-xs sm:text-sm font-black text-white">{finalExitP} ج.م</span>
                </div>
              </div>

              {/* Candlestick Chart Canvas */}
              <div className="border-2 sm:border-4 border-black dark:border-white p-1.5 sm:p-2 bg-[#09090b] shadow-[2px_2px_0px_rgba(0,0,0,1)] sm:shadow-[4px_4px_0px_rgba(0,0,0,1)]">
                <div ref={chartContainerRef} className="w-full h-[280px] sm:h-[360px]" />
              </div>

              {/* Narrative Timeline Explanation */}
              <div className="p-3.5 bg-zinc-900 border-2 border-zinc-700 flex items-start gap-2.5 text-xs font-bold text-zinc-300 leading-relaxed">
                <Info className="w-4 h-4 text-[#FFE600] shrink-0 mt-0.5" />
                <p>
                  {isAr ? (
                    isStoppedOut ? (
                      <>
                        <strong className="text-rose-400">إغلاق الصفقة (وقف الخسارة):</strong> رصد الإسكانر السهم في تمام الساعة{" "}
                        <span className="text-[#FFE600] font-mono font-black">{data.signal.time}</span> بسعر{" "}
                        <span className="text-white font-mono font-black">{data.signal.price} ج.م</span>.
                        {data.signal.max_gain_pct > 0 && (
                          <> سجل السهم قمة مؤقتة عند <span className="text-zinc-300 font-mono font-black">{data.session_high} ج.م</span> (+{data.signal.max_gain_pct}%)، ثم تراجع </>
                        )}
                        وكسر مستوى وقف الخسارة المحدد عند{" "}
                        <span className="text-rose-400 font-mono font-black">{exitPrice ? `${exitPrice} ج.م` : "نقطة الوقف"}</span> بنتيجة محققة{" "}
                        <span className="text-rose-400 font-mono font-black">{realizedReturn}%</span>. تم تفعيل الخروج الإجباري الصارم لحماية رأس المال ومنع الانزلاق مع الهبوط المتتالي.
                      </>
                    ) : isTargetHit ? (
                      <>
                        <strong className="text-emerald-400">نجاح الصفقة (تحقيق الهدف):</strong> رصد الإسكانر السهم في تمام الساعة{" "}
                        <span className="text-[#FFE600] font-mono font-black">{data.signal.time}</span> بسعر{" "}
                        <span className="text-white font-mono font-black">{data.signal.price} ج.م</span>. وواصل السهم صعوده بنجاح حتى حقق الهدف الأول عند سعر{" "}
                        <span className="text-emerald-400 font-mono font-black">{exitPrice || data.session_high} ج.م</span> محققاً عائداً صافياً بلغ{" "}
                        <span className="text-emerald-400 font-mono font-black">+{realizedReturn}%</span>.
                      </>
                    ) : (data.signal.max_gain_pct || 0) > 0 ? (
                      <>
                        <strong className="text-[#FFE600]">قراءة مسار الإشارة (صفقة نشطة):</strong> رصد الإسكانر السهم في تمام الساعة{" "}
                        <span className="text-[#FFE600] font-mono font-black">{data.signal.time}</span> عند سعر{" "}
                        <span className="text-white font-mono font-black">{data.signal.price} ج.م</span>. وواصل السهم صعوده
                        بعد الإشارة حتى سجل أعلى قمة حتى الآن في تمام الساعة{" "}
                        <span className="text-emerald-400 font-mono font-black">{data.peak_time}</span> بسعر{" "}
                        <span className="text-emerald-400 font-mono font-black">{data.session_high} ج.م</span> (+{data.signal.max_gain_pct}%)، والصفقة مستمرة قيد المتابعة الحية.
                      </>
                    ) : (
                      <>
                        <strong className="text-white">قراءة مسار الإشارة:</strong> رصد الإسكانر السهم في تمام الساعة{" "}
                        <span className="text-[#FFE600] font-mono font-black">{data.signal.time}</span> عند سعر{" "}
                        <span className="text-white font-mono font-black">{data.signal.price} ج.م</span>. لم يسجل السهم قمة
                        صاعدة إضافية بعد التنبيه وتراجع/استقر دون سعر الدخول ملتزماً بحدود إدارة المخاطر ووقف الخسارة.
                      </>
                    )
                  ) : (
                    isStoppedOut ? (
                      <>
                        <strong className="text-rose-400">Trade Closed (Stop Loss):</strong> Entered at{" "}
                        <span className="text-[#FFE600] font-mono font-black">{data.signal.time}</span> @{" "}
                        <span className="text-white font-mono font-black">{data.signal.price} EGP</span>. Broke stop loss at{" "}
                        <span className="text-rose-400 font-mono font-black">{exitPrice || "SL"} EGP</span> ({realizedReturn}%). Exited under disciplined capital protection.
                      </>
                    ) : isTargetHit ? (
                      <>
                        <strong className="text-emerald-400">Trade Successful (Target Hit):</strong> Entered at{" "}
                        <span className="text-[#FFE600] font-mono font-black">{data.signal.time}</span> @{" "}
                        <span className="text-white font-mono font-black">{data.signal.price} EGP</span>. Target 1 achieved at{" "}
                        <span className="text-emerald-400 font-mono font-black">{exitPrice || data.session_high} EGP</span> (+{realizedReturn}%).
                      </>
                    ) : (
                      <>
                        <strong className="text-[#FFE600]">Active Signal:</strong> Entered at{" "}
                        <span className="text-[#FFE600] font-mono font-black">{data.signal.time}</span> @{" "}
                        <span className="text-white font-mono font-black">{data.signal.price} EGP</span>. Peak reached:{" "}
                        <span className="text-emerald-400 font-mono font-black">{data.session_high} EGP</span> (+{data.signal.max_gain_pct}%).
                      </>
                    )
                  )}
                </p>
              </div>
            </div>
          );
        })()}

        {/* Modal Footer */}
        <div className="p-4 border-t-4 border-black dark:border-white bg-zinc-900 flex items-center justify-between">
          <span className="text-xs font-mono font-bold text-zinc-400">
            {isAr ? "البيانات محفوظة ومؤرشفة سحابياً في Supabase (market_cache)" : "Intraday session data cached in Supabase (market_cache)"}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 border-2 border-black bg-rose-500 hover:bg-rose-600 text-white font-black text-xs uppercase shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-0.5 active:translate-y-0.5 transition-all"
          >
            {isAr ? "إغلاق الشارت" : "Close Chart"}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
