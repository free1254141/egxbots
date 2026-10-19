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
  signalTime?: string;
  signalPrice?: number;
  scannerType?: string;
  isAr?: boolean;
  onGainLoaded?: (data: { symbol: string; max_gain_pct: number; peak_price: number; peak_time: string }) => void;
}

interface IntradaySessionPayload {
  symbol: string;
  date: string;
  session_open: number;
  session_close: number;
  session_high: number;
  peak_time: string;
  session_low: number;
  session_gain_pct: number;
  session_max_gain_pct: number;
  signal: {
    time: string;
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
  signalPrice?: number
): Promise<IntradaySessionPayload | null> {
  const cacheKey = `${symbol}_${date}_${signalTime || "10:15"}`;
  if (CLIENT_SESSION_CACHE.has(cacheKey)) {
    return CLIENT_SESSION_CACHE.get(cacheKey)!;
  }
  try {
    const params = new URLSearchParams({ symbol, date });
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
  signalTime = "10:15",
  signalPrice,
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
    const cacheKey = `${symbol}_${date}_${signalTime || "10:15"}`;

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
  }, [isOpen, symbol, date, signalTime, signalPrice, isAr]);

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
    // Cairo is UTC+2 or UTC+3, we parse ISO date
    const formattedData = data.candles.map((c) => {
      const parsedTs = Math.floor(new Date(`${data.date}T${c.time}:00Z`).getTime() / 1000);
      return {
        time: (parsedTs || c.time) as any,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        origTime: c.time,
      };
    });

    series.setData(formattedData);

    // Build markers for Signal Time and Peak High
    const markers: any[] = [];

    // Find Signal Marker
    const targetSigTime = data.signal.time || signalTime || "10:15";
    const sigIndex = formattedData.findIndex((c) => c.origTime >= targetSigTime);
    const signalCandle = sigIndex !== -1 ? formattedData[sigIndex] : formattedData[1] || formattedData[0];

    if (signalCandle) {
      markers.push({
        time: signalCandle.time,
        position: "belowBar",
        color: "#FFE600",
        shape: "arrowUp",
        text: isAr
          ? `📍 إشارة (${signalCandle.origTime}) • ${data.signal.price || signalCandle.close} ج.م`
          : `📍 Signal (${signalCandle.origTime}) • ${data.signal.price || signalCandle.close} EGP`,
      });
    }

    // Find Session High Peak Marker
    const peakIndex = formattedData.findIndex((c) => c.origTime === data.peak_time);
    const peakCandle = peakIndex !== -1 ? formattedData[peakIndex] : formattedData.reduce((max, c) => (c.high > max.high ? c : max), formattedData[0]);

    if (peakCandle) {
      markers.push({
        time: peakCandle.time,
        position: "aboveBar",
        color: "#10b981",
        shape: "arrowDown",
        text: isAr
          ? `🎯 أعلى قمة بعد الإشارة (${peakCandle.origTime}) • ${data.session_high} ج.م (+${data.signal.max_gain_pct}%)`
          : `🎯 Peak After Signal (${peakCandle.origTime}) • ${data.session_high} EGP (+${data.signal.max_gain_pct}%)`,
      });
    }

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
  }, [data, isAr, signalTime]);

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
                  <span className="sm:hidden">{isAr ? "شارت 15 دقيقة • الجلسة" : "15M Candlestick"}</span>
                  <span className="hidden sm:inline">{isAr ? "شارت شمع 15 دقيقة • جلسة التداول الكاملة" : "15M Candlestick • Full Trading Session"}</span>
                </h3>
              </div>
              <p className="text-[10px] sm:text-xs font-mono font-bold text-black mt-0.5 sm:mt-1 flex items-center gap-1.5 sm:gap-2">
                <CalendarIcon className="w-3 h-3 sm:w-3.5 sm:h-3.5 shrink-0" />
                <span>{date}</span>
                <span>•</span>
                <span className="hidden sm:inline">10:00 ص إلى 02:30 م (EGX Session)</span>
                <span className="sm:hidden">10:00 - 14:30</span>
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
        {!loading && data && (
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
              <div className="p-2 sm:p-2.5 bg-emerald-950/40 border-2 border-emerald-500 text-emerald-300">
                <span className="text-[10px] text-emerald-400 block flex items-center gap-1 truncate">
                  <Target className="w-3 h-3 shrink-0" />
                  {isAr ? `أعلى قمة (${data.peak_time})` : `Peak (${data.peak_time})`}
                </span>
                <span className="text-xs sm:text-sm font-black">{data.session_high} ج.م</span>
              </div>

              {/* Max Gain from Signal */}
              <div className="p-2 sm:p-2.5 bg-emerald-500 text-black border-2 border-black font-black">
                <span className="text-[10px] uppercase block truncate">{isAr ? "أقصى ربح للإشارة" : "Max Gain"}</span>
                <span className="text-sm sm:text-base font-black">+{data.signal.max_gain_pct}%</span>
              </div>

              {/* Close */}
              <div className="p-2 sm:p-2.5 bg-zinc-900 border-2 border-zinc-700 col-span-2 sm:col-span-1">
                <span className="text-[10px] text-zinc-400 block">{isAr ? "إغلاق الجلسة" : "Session Close"}</span>
                <span className="text-xs sm:text-sm font-black text-white">{data.session_close} ج.م</span>
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
                  <>
                    <strong className="text-white">قراءة مسار الإشارة:</strong> رصد الإسكانر السهم في تمام الساعة{" "}
                    <span className="text-[#FFE600] font-mono font-black">{data.signal.time}</span> عند سعر{" "}
                    <span className="text-white font-mono font-black">{data.signal.price} ج.م</span>. واصل السهم صعوده
                    بعد الإشارة حتى سجل أعلى نقطة في تمام الساعة{" "}
                    <span className="text-emerald-400 font-mono font-black">{data.peak_time}</span> بسعر{" "}
                    <span className="text-emerald-400 font-mono font-black">{data.session_high} ج.م</span>، محققاً أقصى
                    فرصة ربح للمضارب بعد التنبيه بلغت{" "}
                    <span className="text-emerald-400 font-mono font-black">+{data.signal.max_gain_pct}%</span>.
                  </>
                ) : (
                  <>
                    <strong className="text-white">Signal Journey:</strong> Triggered at{" "}
                    <span className="text-[#FFE600] font-mono font-black">{data.signal.time}</span> at price{" "}
                    <span className="text-white font-mono font-black">{data.signal.price} EGP</span>. The stock moved
                    to reach its subsequent peak at <span className="text-emerald-400 font-mono font-black">{data.peak_time}</span> hitting{" "}
                    <span className="text-emerald-400 font-mono font-black">{data.session_high} EGP</span> (+
                    {data.signal.max_gain_pct}% max gain after signal).
                  </>
                )}
              </p>
            </div>
          </div>
        )}

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
