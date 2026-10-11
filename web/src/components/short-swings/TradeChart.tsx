"use client";

import { useMemo, useState, useCallback } from "react";
import TradingViewChart from "../TradingViewChartDynamic";
import type { CustomMarker } from "../TradingViewChart";
import type { ShortSwingTrade } from "../ShortSwingsTab";
import { formatShortSwingReturn } from "@/lib/short-swings-view";
import type { Candle } from "@/lib/indicators";

type Overlay = {
  id: string;
  label: string;
  kind: "line";
  points: { time: number; value: number }[];
  color: string;
};

function timestamp(date?: string | null) {
  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return undefined;
  const value = Date.parse(`${date}T00:00:00Z`) / 1000;
  return Number.isFinite(value) ? value : undefined;
}

export default function ShortSwingTradeChart({
  trade,
  isAr,
  theme,
  computedAt,
}: {
  trade: ShortSwingTrade;
  isAr: boolean;
  theme: "dark" | "light";
  computedAt?: string;
}) {
  const [candles, setCandles] = useState<Candle[]>([]);
  const onCandlesLoaded = useCallback((rows: Candle[]) => setCandles(rows), []);
  const closed = !!trade.exit_date;
  const pending = !!trade.is_pending_entry;
  const entryTime = timestamp(pending ? trade.signal_date : trade.entry_date);
  const exitTime = timestamp(trade.exit_date);
  const endTime =
    exitTime ?? candles.at(-1)?.time ?? timestamp(trade.price_date);
  const markers = useMemo<CustomMarker[]>(() => {
    const result: CustomMarker[] = [];
    if (entryTime !== undefined)
      result.push({
        time: entryTime,
        position: "belowBar",
        color: pending ? "#f59e0b" : "#10b981",
        shape: pending ? "circle" : "arrowUp",
        text: pending
          ? isAr
            ? "إشارة · انتظار التنفيذ"
            : "Signal · awaiting entry"
          : isAr
            ? "دخول"
            : "Entry",
      });
    if (exitTime !== undefined)
      result.push({
        time: exitTime,
        position: "aboveBar",
        color: "#f43f5e",
        shape: "arrowDown",
        text: isAr ? "خروج" : "Exit",
      });
    return result;
  }, [entryTime, exitTime, pending, isAr]);
  const overlays = useMemo<Overlay[]>(() => {
    if (entryTime === undefined || endTime === undefined) return [];
    const result: Overlay[] = [];
    const level = (
      id: string,
      label: string,
      value: number | null | undefined,
      color: string,
    ) => {
      if (typeof value === "number" && Number.isFinite(value) && value > 0)
        result.push({
          id,
          label,
          kind: "line",
          color,
          points: [
            { time: entryTime, value },
            { time: Math.max(entryTime, endTime), value },
          ],
        });
    };
    level(
      "swing-entry",
      pending
        ? isAr
          ? "الإغلاق المرجعي"
          : "Reference close"
        : isAr
          ? "سعر الدخول"
          : "Entry price",
      pending ? trade.reference_close : trade.entry_price,
      "#10b981",
    );
    level(
      "swing-stop",
      isAr ? "الوقف المسجل" : "Recorded stop",
      trade.trailing_stop ?? trade.stop_loss,
      "#f59e0b",
    );
    if (closed)
      level(
        "swing-exit",
        isAr ? "سعر الخروج" : "Exit price",
        trade.exit_price,
        "#f43f5e",
      );
    return result;
  }, [
    entryTime,
    endTime,
    trade.entry_price,
    trade.reference_close,
    trade.trailing_stop,
    trade.stop_loss,
    trade.exit_price,
    pending,
    closed,
    isAr,
  ]);
  if (trade.is_locked) return null;
  const price = (value?: number | null) =>
    typeof value === "number" && Number.isFinite(value)
      ? `${value.toFixed(3)} ${isAr ? "ج.م" : "EGP"}`
      : "—";
  const reasons: Record<string, string> = {
    ema10_break: isAr ? "كسر EMA10" : "EMA10 break",
    stop_be: isAr ? "وقف التعادل" : "Breakeven stop",
    stop_loss: isAr ? "وقف الخسارة" : "Stop loss",
  };
  const reason = trade.exit_reason || trade.reason;
  const details = [
    [
      isAr ? "حالة الصفقة" : "Trade status",
      closed
        ? isAr
          ? "مغلقة"
          : "Closed"
        : pending
          ? isAr
            ? "انتظار التنفيذ"
            : "Awaiting entry"
          : isAr
            ? "مفتوحة"
            : "Open",
    ],
    [isAr ? "تاريخ الإشارة" : "Signal date", trade.signal_date || "—"],
    [
      isAr ? "تاريخ الدخول" : "Entry date",
      pending ? "—" : trade.entry_date || "—",
    ],
    [
      pending
        ? isAr
          ? "الإغلاق المرجعي"
          : "Reference close"
        : isAr
          ? "سعر الدخول"
          : "Entry price",
      price(pending ? trade.reference_close : trade.entry_price),
    ],
    [
      closed
        ? isAr
          ? "سعر الخروج"
          : "Exit price"
        : isAr
          ? "السعر الحالي"
          : "Current price",
      price(closed ? trade.exit_price : trade.current_price),
    ],
    [isAr ? "الوقف المبدئي" : "Initial stop", price(trade.stop_loss)],
    [
      isAr ? "الوقف المتحرك المسجل" : "Recorded trailing stop",
      price(trade.trailing_stop),
    ],
    [
      isAr ? "العائد" : "Return",
      pending ? "—" : formatShortSwingReturn(trade.return_pct, 2),
    ],
    [
      isAr ? "مدة الاحتفاظ" : "Holding period",
      trade.sessions != null
        ? `${trade.sessions} ${isAr ? "جلسات" : "sessions"}`
        : "—",
    ],
    ...(closed
      ? [
          [isAr ? "تاريخ الخروج" : "Exit date", trade.exit_date || "—"],
          [
            isAr ? "سبب الخروج" : "Exit reason",
            reason ? reasons[reason] || reason : "—",
          ],
        ]
      : [[isAr ? "تاريخ السعر" : "Price date", trade.price_date || "—"]]),
  ];
  return (
    <section
      className="grid grid-cols-1 lg:grid-cols-3 gap-4"
      dir={isAr ? "rtl" : "ltr"}
    >
      <aside className="border border-zinc-300 dark:border-zinc-800 bg-zinc-50 dark:bg-black p-4 space-y-2 h-fit">
        <h4 className="text-xs font-black mb-3">
          {isAr ? "تفاصيل الصفقة القصيرة" : "Short trade details"}
        </h4>
        {details.map(([label, value]) => (
          <div
            key={label}
            className="flex justify-between gap-3 border-b border-zinc-200 dark:border-zinc-800 py-2 text-xs"
          >
            <span className="text-zinc-500 dark:text-zinc-400">{label}</span>
            <span className="font-bold text-end" dir="auto">
              {value}
            </span>
          </div>
        ))}
        {trade.trigger_type && (
          <p className="text-xs leading-relaxed pt-2">{trade.trigger_type}</p>
        )}
        {computedAt && (
          <p className="text-[11px] text-zinc-500 dark:text-zinc-400 pt-2">
            {isAr ? "آخر تحديث للصفقات: " : "Trades updated: "}
            {new Date(computedAt).toLocaleString(isAr ? "ar-EG" : "en-GB", {
              timeZone: "Africa/Cairo",
            })}{" "}
            {isAr ? "بتوقيت القاهرة" : "Cairo time"}
          </p>
        )}
      </aside>
      <div className="lg:col-span-2 min-w-0 border-2 border-zinc-300 dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden">
        <div className="flex flex-wrap justify-between gap-2 px-4 py-3 bg-zinc-100 dark:bg-black border-b border-zinc-300 dark:border-zinc-800 text-xs font-bold">
          <span>{isAr ? "الشارت التفاعلي" : "Interactive chart"}</span>
          <span dir="ltr">{trade.symbol}</span>
        </div>
      <div className="h-[520px]" dir="ltr">
          <TradingViewChart
            key={`${trade.symbol}-${trade.entry_date}-${trade.exit_date || "open"}`}
            symbol={trade.symbol}
            exchange="EGX"
            theme={theme}
            showApiMarkers={false}
            customMarkers={markers}
            focusTimestamp={entryTime}
            onCandlesLoaded={onCandlesLoaded}
            strategyOverlays={overlays}
          />
        </div>
        <p className="px-4 py-2 text-[11px] text-zinc-500 dark:text-zinc-400">
          {isAr
            ? "علامات الدخول والخروج تخص هذه الصفقة. خط الوقف يعرض آخر مستوى مسجل."
            : "Entry and exit markers belong to this trade. The stop line shows the last recorded level."}
        </p>
      </div>
    </section>
  );
}
