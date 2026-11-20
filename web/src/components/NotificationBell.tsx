"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Bell, CheckCheck, Coins, Calendar, ArrowUpLeft, Sparkles } from "lucide-react";
import StockLogo from "@/components/StockLogo";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

interface UserNotificationRow {
  id: string;
  type: string;
  title: string;
  body: string;
  href?: string | null;
  is_read: boolean;
  created_at: string;
  metadata?: {
    symbol?: string;
    gross_amount?: number;
    currency?: string;
    ex_date?: string;
    pay_date?: string;
  } | null;
}

export default function NotificationBell() {
  const { user } = useAuth();
  const { language } = useLanguage();
  const isAr = language === "ar";
  const supabase = useMemo(() => createSupabaseBrowserClient(), []);

  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<UserNotificationRow[]>([]);
  const fetchedUserRef = useRef<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const loadNotifications = useCallback(async () => {
    if (!user) {
      setItems([]);
      return;
    }
    try {
      const { data, error } = await supabase
        .from("user_notifications")
        .select("id,type,title,body,href,is_read,created_at,metadata")
        .eq("user_id", user.id)
        .order("created_at", { ascending: false })
        .limit(15);

      if (!error && Array.isArray(data) && data.length > 0) {
        setItems(data as UserNotificationRow[]);
        return;
      }

      // Lightweight graceful fallback: synthesize upcoming dividend alerts directly from user's open positions
      const { data: posRows } = await supabase
        .from("positions")
        .select("symbol,quantity")
        .eq("user_id", user.id)
        .eq("status", "open")
        .limit(30);

      if (!posRows || posRows.length === 0) {
        setItems([]);
        return;
      }
      const heldQty = new Map<string, number>();
      for (const p of posRows) {
        const s = String(p.symbol || "").toUpperCase();
        const q = Number(p.quantity || 0);
        if (s && q > 0) heldQty.set(s, (heldQty.get(s) || 0) + q);
      }
      if (heldQty.size === 0) return;

      const res = await fetch("/api/market/dividends?market=egx");
      if (!res.ok) return;
      const cal = await res.json();
      const divs = Array.isArray(cal?.dividends) ? cal.dividends : [];
      const synth: UserNotificationRow[] = [];
      for (const d of divs) {
        const sym = String(d.symbol || "").toUpperCase();
        if ((d.status === "upcoming" || d.status === "pending_pay") && heldQty.has(sym)) {
          const qty = heldQty.get(sym) || 0;
          const gross = qty * Number(d.amount || 0);
          const currAr = d.currency_ar || "ج.م";
          synth.push({
            id: `synth-${sym}-${d.ex_date}`,
            type: "dividend_upcoming",
            title: isAr
              ? `كوبون قادم في محفظتك: ${d.name_ar || sym} (${sym})`
              : `Upcoming Dividend: ${sym}`,
            body: isAr
              ? `تمتلك ${qty.toLocaleString()} سهم × ${d.amount} ${currAr} = إجمالي ${gross.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${currAr}`
              : `${qty.toLocaleString()} shares × ${d.amount} ${d.currency} = ${gross.toFixed(2)}`,
            href: `/stocks/${sym}`,
            is_read: false,
            created_at: new Date().toISOString(),
            metadata: {
              symbol: sym,
              gross_amount: gross,
              currency: currAr,
              ex_date: d.ex_date,
              pay_date: d.pay_date,
            },
          });
        }
      }
      setItems(synth);
    } catch {
      // Never disrupt header rendering
    }
  }, [user, supabase, isAr]);

  useEffect(() => {
    if (!user) {
      fetchedUserRef.current = null;
      setItems([]);
      return;
    }
    if (fetchedUserRef.current === user.id) return;
    fetchedUserRef.current = user.id;
    void loadNotifications();
  }, [user, loadNotifications]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;

  const unreadCount = items.filter((n) => !n.is_read).length;

  const handleMarkAllRead = async () => {
    setItems((prev) => prev.map((x) => ({ ...x, is_read: true })));
    const dbIds = items.filter((x) => !x.is_read && !x.id.startsWith("synth-")).map((x) => x.id);
    if (dbIds.length > 0) {
      try {
        await supabase
          .from("user_notifications")
          .update({ is_read: true })
          .eq("user_id", user.id)
          .in("id", dbIds);
      } catch {
        // ignore
      }
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={isAr ? "الإشعارات وتوزيعات الكوبونات" : "Notifications & Dividends"}
        title={isAr ? "إشعارات المحفظة والكوبونات" : "Portfolio & Dividend Notifications"}
        className={`relative h-9 w-9 flex items-center justify-center rounded-xl transition-all cursor-pointer ${
          open
            ? "bg-[#FFE600] text-black shadow-[0_0_16px_rgba(255,230,0,0.35)]"
            : "app-icon-button hover:text-white"
        }`}
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[17px] h-[17px] px-1 rounded-full bg-emerald-500 text-black text-[10px] font-black flex items-center justify-center leading-none ring-2 ring-zinc-950">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          dir={isAr ? "rtl" : "ltr"}
          className="fixed sm:absolute top-16 sm:top-full right-3 sm:right-0 sm:mt-2.5 w-[calc(100vw-1.5rem)] sm:w-[390px] rounded-2xl border border-zinc-200 dark:border-zinc-700/90 bg-white dark:bg-[#0d1117] shadow-[0_24px_60px_rgba(0,0,0,0.55)] z-[80] overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        >
          {/* Top Accent Bar */}
          <div className="h-1 w-full bg-gradient-to-r from-emerald-500 via-[#FFE600] to-amber-500" />

          {/* Header */}
          <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800/90 flex items-center justify-between gap-2 bg-zinc-50/90 dark:bg-zinc-900/70">
            <div className="flex items-center gap-2 min-w-0">
              <div className="h-7 w-7 rounded-lg bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center shrink-0">
                <Coins className="w-4 h-4 text-emerald-500" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs sm:text-[13px] font-black text-zinc-950 dark:text-white truncate">
                    {isAr ? "إشعارات الكوبونات والمحفظة" : "Dividend & Portfolio Alerts"}
                  </span>
                  {unreadCount > 0 && (
                    <span className="px-1.5 py-0.5 rounded-full text-[10px] font-black bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                      {unreadCount} {isAr ? "جديد" : "new"}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {unreadCount > 0 && (
              <button
                type="button"
                onClick={handleMarkAllRead}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-bold text-indigo-600 dark:text-indigo-400 hover:bg-indigo-500/10 transition-colors cursor-pointer shrink-0"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                <span>{isAr ? "تحديد كمقروء" : "Mark read"}</span>
              </button>
            )}
          </div>

          {/* Notification List */}
          <div className="max-h-[340px] overflow-y-auto divide-y divide-zinc-200/80 dark:divide-zinc-800/80">
            {items.length === 0 ? (
              <div className="p-7 text-center space-y-2.5">
                <div className="w-11 h-11 rounded-2xl bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 flex items-center justify-center mx-auto">
                  <Calendar className="w-5 h-5 text-zinc-400" />
                </div>
                <div className="text-xs font-black text-zinc-700 dark:text-zinc-300">
                  {isAr ? "لا توجد إشعارات كوبونات جديدة حالياً" : "No new dividend notifications yet"}
                </div>
                <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
                  {isAr
                    ? "عند اقتراب موعد أي كوبون لأسهم محفظتك سيظهر تنبيهك هنا فوراً."
                    : "Upcoming coupons for stocks in your portfolio will appear here automatically."}
                </p>
                <Link
                  href="/dividends"
                  onClick={() => setOpen(false)}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[#FFE600] text-black text-xs font-black hover:bg-yellow-300 transition-colors"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>{isAr ? "استعرض تقويم الكوبونات القادمة" : "Browse Upcoming Dividends"}</span>
                </Link>
              </div>
            ) : (
              items.map((n) => {
                const sym = n.metadata?.symbol;
                const gross = n.metadata?.gross_amount;
                const curr = n.metadata?.currency || "ج.م";
                const exDate = n.metadata?.ex_date;
                const payDate = n.metadata?.pay_date;
                return (
                  <Link
                    key={n.id}
                    href={n.href || "/profile#portfolio"}
                    onClick={() => setOpen(false)}
                    className={`block p-3.5 hover:bg-zinc-50 dark:hover:bg-zinc-900/80 transition-colors ${
                      !n.is_read ? "bg-emerald-500/[0.06]" : ""
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      {sym ? (
                        <StockLogo symbol={sym} size="sm" className="h-9 w-9 rounded-xl mt-0.5 shrink-0" />
                      ) : (
                        <div className="h-9 w-9 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center shrink-0 mt-0.5">
                          <Coins className="w-4 h-4 text-emerald-500" />
                        </div>
                      )}

                      <div className="min-w-0 flex-1 space-y-1.5">
                        <div className="flex items-start justify-between gap-2">
                          <div className="text-xs font-black text-zinc-950 dark:text-white leading-snug">
                            {n.title}
                          </div>
                          {!n.is_read && (
                            <span className="w-2 h-2 rounded-full bg-emerald-500 mt-1 shrink-0 shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
                          )}
                        </div>

                        <p className="text-[11px] text-zinc-600 dark:text-zinc-300 leading-relaxed">
                          {n.body}
                        </p>

                        {(gross !== undefined || exDate || payDate) && (
                          <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                            {typeof gross === "number" && gross > 0 && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30 font-mono text-[10px] font-black">
                                +{gross.toLocaleString(undefined, { maximumFractionDigits: 2 })} {curr}
                              </span>
                            )}
                            {exDate && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-zinc-100 dark:bg-zinc-800/90 text-zinc-700 dark:text-zinc-300 font-mono text-[10px] font-bold">
                                <Calendar className="w-2.5 h-2.5 text-amber-500" />
                                Ex: {exDate}
                              </span>
                            )}
                            {payDate && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 font-mono text-[10px] font-bold">
                                {isAr ? "صرف:" : "Pay:"} {payDate}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </Link>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-2.5 border-t border-zinc-200 dark:border-zinc-800/90 bg-zinc-50/90 dark:bg-zinc-900/70 flex items-center justify-between text-[11px] font-black">
            <Link
              href="/dividends"
              onClick={() => setOpen(false)}
              className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 hover:underline"
            >
              <span>{isAr ? "تقويم الكوبونات (4 أسواق)" : "Dividend Calendar"}</span>
              <ArrowUpLeft className="w-3.5 h-3.5" />
            </Link>
            <Link
              href="/profile#portfolio"
              onClick={() => setOpen(false)}
              className="text-zinc-600 dark:text-zinc-400 hover:text-zinc-950 dark:hover:text-white transition-colors"
            >
              {isAr ? "إدارة محفظتي" : "My Portfolio"}
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
