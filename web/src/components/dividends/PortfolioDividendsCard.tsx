"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Coins, Calendar, CheckCircle2, Clock, ArrowUpRight } from "lucide-react";
import StockLogo from "@/components/StockLogo";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAuth } from "@/contexts/AuthContext";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import type { StockDividendItem } from "@/lib/market/dividends-server";
import { hfPublicFetch } from "@/lib/hf-browser-client";

interface HeldPositionLite {
  symbol: string;
  quantity: number | null;
}

interface CreditedEventRow {
  id: string;
  symbol: string;
  shares_held: number;
  coupon_per_share: number;
  gross_amount: number;
  net_amount: number;
  currency: string;
  ex_date: string;
  pay_date: string | null;
  status: string;
  credited_to_cash: boolean;
}

export default function PortfolioDividendsCard({
  positions,
}: {
  positions: HeldPositionLite[];
}) {
  const { language } = useLanguage();
  const isAr = language === "ar";
  const { user } = useAuth();
  const supabase = useMemo(() => createSupabaseBrowserClient(), []);

  const [egxCalendar, setEgxCalendar] = useState<StockDividendItem[]>([]);
  const [creditedEvents, setCreditedEvents] = useState<CreditedEventRow[]>([]);

  const heldMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const p of positions || []) {
      const sym = (p.symbol || "").trim().toUpperCase().split(".")[0];
      const qty = Number(p.quantity || 0);
      if (sym && qty > 0) {
        map.set(sym, (map.get(sym) || 0) + qty);
      }
    }
    return map;
  }, [positions]);

  useEffect(() => {
    let active = true;
    hfPublicFetch("/api/market/dividends?market=egx", undefined, { cacheTtlMs: 300_000 })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (active && Array.isArray(d?.dividends)) {
          setEgxCalendar(d.dividends);
        }
      })
      .catch(() => {});

    if (user) {
      Promise.resolve(
        supabase
          .from("user_dividend_events")
          .select("id,symbol,shares_held,coupon_per_share,gross_amount,net_amount,currency,ex_date,pay_date,status,credited_to_cash")
          .eq("user_id", user.id)
          .order("ex_date", { ascending: false })
          .limit(12)
      )
        .then(({ data }) => {
          if (active && Array.isArray(data)) {
            setCreditedEvents(data as CreditedEventRow[]);
          }
        })
        .catch(() => {});
    }

    return () => {
      active = false;
    };
  }, [user, supabase]);

  const myUpcoming = useMemo(() => {
    return egxCalendar
      .filter((d) => (d.status === "upcoming" || d.status === "pending_pay") && heldMap.has(d.symbol.toUpperCase()))
      .map((d) => {
        const qty = heldMap.get(d.symbol.toUpperCase()) || 0;
        const gross = qty * d.amount;
        const net = d.exchange === "EGX" ? gross * 0.95 : gross;
        return { ...d, qty, gross, net };
      });
  }, [egxCalendar, heldMap]);

  const marketSoon = useMemo(
    () => egxCalendar.filter((d) => d.status === "upcoming").slice(0, 4),
    [egxCalendar]
  );

  if (myUpcoming.length === 0 && creditedEvents.length === 0 && marketSoon.length === 0) {
    return null;
  }

  return (
    <div
      dir={isAr ? "rtl" : "ltr"}
      className="border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-950 p-4 sm:p-5 space-y-4 shadow-[3px_3px_0_0_#000] dark:shadow-[3px_3px_0_0_#27272a]"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-[#FFE600] text-black border-2 border-black">
            <Coins className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm sm:text-base font-black text-zinc-950 dark:text-white">
              {isAr ? "توزيعات الكوبونات (محفظتك والسوق)" : "Cash Dividends (Portfolio & Market)"}
            </h3>
            <p className="text-[11px] font-bold text-zinc-500">
              {isAr
                ? "تُضاف كوبونات أسهمك تلقائياً إلى رصيد الكاش في تاريخ الصرف مع إشعار فوري"
                : "Eligible dividends are tracked and credited automatically on pay date"}
            </p>
          </div>
        </div>

        <Link
          href="/dividends"
          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-black border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900 hover:bg-[#FFE600] hover:text-black transition-colors"
          prefetch={false}
        >
          <span>{isAr ? "تقويم الكوبونات (4 أسواق)" : "4-Market Calendar"}</span>
          <ArrowUpRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      {/* Held Stocks Upcoming Dividends */}
      {myUpcoming.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-black text-emerald-700 dark:text-emerald-400">
            {isAr ? `🎁 كوبونات قادمة لأسهم في محفظتك (${myUpcoming.length})` : `Upcoming Dividends for Your Holdings (${myUpcoming.length})`}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
            {myUpcoming.map((item) => (
              <div
                key={`${item.symbol}-${item.ex_date}`}
                className="p-3 border-2 border-emerald-600/50 bg-emerald-50/60 dark:bg-emerald-950/25 flex items-center justify-between gap-3"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <StockLogo symbol={item.symbol} size="sm" className="h-8 w-8 rounded-lg" />
                  <div className="min-w-0">
                    <div className="font-black text-xs sm:text-sm text-zinc-950 dark:text-white truncate">
                      {item.symbol} — {isAr ? item.name_ar : item.name_en}
                    </div>
                    <div className="text-[11px] font-mono text-zinc-600 dark:text-zinc-400 flex items-center gap-2">
                      <span>{item.qty.toLocaleString()} × {item.amount} {item.currency_ar}</span>
                      <span>• Ex: {item.ex_date}</span>
                    </div>
                  </div>
                </div>
                <div className="text-end shrink-0 font-mono">
                  <div className="text-sm font-black text-emerald-700 dark:text-emerald-400">
                    +{item.gross.toLocaleString(undefined, { maximumFractionDigits: 2 })} {item.currency_ar}
                  </div>
                  <div className="text-[10px] font-bold text-zinc-500">
                    {item.pay_date ? `${isAr ? "صرف:" : "Pay:"} ${item.pay_date}` : (isAr ? "تحت الصرف" : "Pending")}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Credited Dividends History (from user_dividend_events) */}
      {creditedEvents.some((e) => e.credited_to_cash) && (
        <div className="space-y-2">
          <div className="text-xs font-black text-indigo-700 dark:text-indigo-400">
            {isAr ? "✅ كوبونات تم صرفها وإضافتها لرصيد الكاش" : "Credited to Cash Balance"}
          </div>
          <div className="space-y-1.5">
            {creditedEvents
              .filter((e) => e.credited_to_cash)
              .slice(0, 5)
              .map((ev) => (
                <div
                  key={ev.id}
                  className="px-3 py-2 border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/60 flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span className="font-black">{ev.symbol}</span>
                    <span className="text-zinc-500 font-mono">
                      ({ev.shares_held.toLocaleString()} × {ev.coupon_per_share})
                    </span>
                  </div>
                  <span className="font-mono font-black text-emerald-600 dark:text-emerald-400">
                    +{ev.gross_amount.toLocaleString(undefined, { maximumFractionDigits: 2 })} {ev.currency}
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Quick Market Upcoming Strip when user holds none */}
      {myUpcoming.length === 0 && marketSoon.length > 0 && (
        <div className="space-y-2">
          <div className="text-[11px] font-black text-zinc-600 dark:text-zinc-400 flex items-center gap-1">
            <Clock className="w-3.5 h-3.5 text-amber-500" />
            <span>{isAr ? "أقرب الكوبونات القادمة في البورصة المصرية:" : "Nearest Upcoming EGX Dividends:"}</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {marketSoon.map((m) => (
              <Link
                key={`${m.symbol}-${m.ex_date}`}
                href={`/stocks/${m.symbol}`}
                className="p-2.5 border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/60 hover:border-black dark:hover:border-[#FFE600] transition-colors"
                prefetch={false}
              >
                <div className="flex items-center gap-1.5">
                  <StockLogo symbol={m.symbol} size="sm" className="h-5 w-5 rounded-md" />
                  <span className="font-black text-xs text-zinc-950 dark:text-white">{m.symbol}</span>
                </div>
                <div className="mt-1 font-mono text-xs font-black text-emerald-700 dark:text-emerald-400">
                  {m.amount.toFixed(m.amount < 1 ? 3 : 2)} {m.currency_ar}
                </div>
                <div className="text-[10px] font-mono text-zinc-500 flex items-center gap-1 mt-0.5">
                  <Calendar className="w-2.5 h-2.5" />
                  <span>{m.ex_date}</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
