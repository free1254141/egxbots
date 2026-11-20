"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Bell, CheckCheck, Coins, Calendar } from "lucide-react";
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
        .select("id,type,title,body,href,is_read,created_at")
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
          synth.push({
            id: `synth-${sym}-${d.ex_date}`,
            type: "dividend_upcoming",
            title: isAr ? `💰 كوبون قادم في محفظتك: ${sym}` : `Upcoming Dividend: ${sym}`,
            body: isAr
              ? `لديك ${qty.toLocaleString()} سهم × ${d.amount} ${d.currency_ar} = ${gross.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${d.currency_ar} | Ex-Date: ${d.ex_date}`
              : `${qty.toLocaleString()} shares × ${d.amount} ${d.currency} = ${gross.toFixed(2)} | Ex: ${d.ex_date}`,
            href: `/stocks/${sym}`,
            is_read: false,
            created_at: new Date().toISOString(),
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
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
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
        className="relative h-9 w-9 flex items-center justify-center rounded-xl app-icon-button hover:text-white transition-all cursor-pointer"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -end-0.5 min-w-[16px] h-4 px-1 rounded-full bg-emerald-500 text-black text-[10px] font-black flex items-center justify-center leading-none">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          dir={isAr ? "rtl" : "ltr"}
          className="absolute end-0 mt-2 w-80 sm:w-96 rounded-2xl border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-950 shadow-2xl z-50 overflow-hidden"
        >
          <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between bg-zinc-50 dark:bg-zinc-900">
            <div className="flex items-center gap-1.5 text-xs font-black text-zinc-950 dark:text-white">
              <Coins className="w-4 h-4 text-emerald-500" />
              <span>{isAr ? "إشعارات الكوبونات والمحفظة" : "Dividend & Portfolio Alerts"}</span>
            </div>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={handleMarkAllRead}
                className="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-600 dark:text-indigo-400 hover:underline cursor-pointer"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                <span>{isAr ? "تحديد كمقروء" : "Mark read"}</span>
              </button>
            )}
          </div>

          <div className="max-h-80 overflow-y-auto divide-y divide-zinc-200 dark:divide-zinc-800">
            {items.length === 0 ? (
              <div className="p-6 text-center space-y-2">
                <Calendar className="w-7 h-7 text-zinc-400 mx-auto" />
                <div className="text-xs font-bold text-zinc-500">
                  {isAr ? "لا توجد إشعارات كوبونات جديدة حالياً" : "No new dividend notifications yet"}
                </div>
                <Link
                  href="/dividends"
                  onClick={() => setOpen(false)}
                  className="inline-block text-xs font-black text-emerald-600 dark:text-emerald-400 hover:underline"
                >
                  {isAr ? "تصفح تقويم الكوبونات القادمة ←" : "Browse upcoming dividend calendar →"}
                </Link>
              </div>
            ) : (
              items.map((n) => (
                <Link
                  key={n.id}
                  href={n.href || "/profile#portfolio"}
                  onClick={() => setOpen(false)}
                  className={`block p-3.5 hover:bg-zinc-50 dark:hover:bg-zinc-900/70 transition-colors ${
                    !n.is_read ? "bg-emerald-500/5" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-xs font-black text-zinc-950 dark:text-white">{n.title}</div>
                    {!n.is_read && <span className="w-2 h-2 rounded-full bg-emerald-500 mt-1 shrink-0" />}
                  </div>
                  <p className="mt-1 text-[11px] text-zinc-600 dark:text-zinc-400 leading-relaxed">{n.body}</p>
                </Link>
              ))
            )}
          </div>

          <div className="px-4 py-2.5 border-t border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900 flex items-center justify-between text-[11px] font-black">
            <Link href="/dividends" onClick={() => setOpen(false)} className="text-emerald-600 dark:text-emerald-400 hover:underline">
              {isAr ? "تقويم الكوبونات (4 أسواق)" : "Dividend Calendar"}
            </Link>
            <Link href="/profile#portfolio" onClick={() => setOpen(false)} className="text-zinc-600 dark:text-zinc-400 hover:underline">
              {isAr ? "محفظتي" : "My Portfolio"}
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
