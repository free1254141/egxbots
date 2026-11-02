"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, LockKeyhole, Rocket, ShieldAlert, TrendingUp, TrendingDown } from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAuth } from "@/contexts/AuthContext";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import { isPro } from "@/lib/ai/plan-gate";
import type { TrapsSnapshot, TrapSignalRow } from "@/app/api/scan/traps/route";

export default function TrapDetector() {
  const { language } = useLanguage();
  const { user } = useAuth();
  const ar = language === "ar";
  const supabase = useMemo(() => createSupabaseBrowserClient(), []);
  const [snapshot, setSnapshot] = useState<TrapsSnapshot | null>(null);
  const [error, setError] = useState(false);
  const [activeTab, setActiveTab] = useState<"BEAR_TRAP" | "BULL_TRAP">("BEAR_TRAP");
  const [pro, setPro] = useState(false);

  useEffect(() => {
    let mounted = true;
    const checkLocalStorage = () => {
      try {
        if (typeof window !== "undefined" && localStorage.getItem("egx_pro_active") === "true") {
          if (mounted) setPro(true);
        }
      } catch {}
    };

    checkLocalStorage();

    const handleEntitlements = (event: Event) => {
      const customEvent = event as CustomEvent<{ is_pro?: boolean }>;
      if (typeof customEvent?.detail?.is_pro === "boolean") {
        if (mounted) setPro(customEvent.detail.is_pro);
      } else {
        checkLocalStorage();
      }
    };

    window.addEventListener("egx:entitlements-updated", handleEntitlements);

    if (!user) {
      setPro(false);
      return () => {
        mounted = false;
        window.removeEventListener("egx:entitlements-updated", handleEntitlements);
      };
    }
    void (async () => {
      try {
        const { data } = await supabase
          .from("subscriptions")
          .select("plan_id,status,current_period_end")
          .eq("user_id", user.id)
          .limit(10);
        if (mounted) setPro(isPro(data || []));
      } catch {
        if (mounted) setPro(false);
      }
    })();
    return () => {
      mounted = false;
      window.removeEventListener("egx:entitlements-updated", handleEntitlements);
    };
  }, [supabase, user]);

  useEffect(() => {
    if (!pro) return;
    const controller = new AbortController();
    fetch("/api/scan/traps", { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error("Failed");
        return res.json();
      })
      .then(setSnapshot)
      .catch((cause) => {
        if (cause?.name !== "AbortError") setError(true);
      });
    return () => controller.abort();
  }, [pro]);

  if (!pro) {
    return (
      <section
        className="relative border-b-2 border-zinc-200 bg-zinc-50 px-3 py-4 text-zinc-950 dark:border-[#2a2e39] dark:bg-[#10151e] dark:text-white sm:px-6 sm:py-5 overflow-hidden"
        aria-label={ar ? "كاشف المصائد والانعكاسات" : "Trap Detector"}
        dir={ar ? "rtl" : "ltr"}
      >
        <div className="relative flex flex-col sm:flex-row items-center justify-between gap-4 py-2">
          <div className="flex items-center gap-3 text-center sm:text-right">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center border-2 border-emerald-500 bg-emerald-50 dark:bg-emerald-400/10">
              <LockKeyhole className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <h2 className="text-sm font-black text-zinc-950 dark:text-white flex items-center gap-2 justify-center sm:justify-start">
                <span>🪤 {ar ? "كاشف المصائد والانعكاسات (Bull & Bear Traps)" : "Trap Detector (Bull & Bear Traps)"}</span>
                <span className="border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-black text-emerald-500">
                  PRO
                </span>
              </h2>
              <p className="text-[11px] font-semibold text-zinc-500 dark:text-zinc-400 mt-0.5">
                {ar
                  ? "يرصد الكسر الوهمي للتجميع (Wyckoff Spring) والاختراق الكاذب للتصريف (Upthrust) بعد اكتمال شمعة الإغلاق اليومي."
                  : "Detects Wyckoff Springs (Bear Traps) and Upthrusts (Bull Traps) after the daily closing candle settles."}
              </p>
            </div>
          </div>

          <Link
            href="/pricing"
            className="shrink-0 inline-flex items-center gap-2 border-2 border-emerald-500 bg-emerald-500 px-4 py-2 text-[11px] font-black uppercase tracking-widest text-zinc-950 shadow-[3px_3px_0px_rgba(0,0,0,0.2)] transition-all hover:-translate-y-0.5 hover:bg-emerald-400"
          >
            <Rocket className="h-3.5 w-3.5" />
            {ar ? "افتح كاشف المصائد (Pro)" : "Unlock Trap Detector"}
          </Link>
        </div>
      </section>
    );
  }

  const rows: TrapSignalRow[] =
    activeTab === "BEAR_TRAP" ? snapshot?.bearTraps || [] : snapshot?.bullTraps || [];

  return (
    <section
      className="border-b-2 border-zinc-200 bg-zinc-50 px-3 py-4 text-zinc-950 dark:border-[#2a2e39] dark:bg-[#10151e] dark:text-white sm:px-6 sm:py-5"
      aria-label={ar ? "كاشف المصائد والانعكاسات" : "Trap Detector"}
      dir={ar ? "rtl" : "ltr"}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-emerald-500 shrink-0" />
          <h2 className="text-sm font-black uppercase tracking-wide">
            🪤 {ar ? "كاشف المصائد والانعكاسات (إغلاق الجلسة)" : "Trap Detector (Daily Close)"}
          </h2>
          {snapshot?.asOf && (
            <span className="text-[11px] font-semibold text-zinc-500 dark:text-zinc-400">
              ({snapshot.asOf})
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("BEAR_TRAP")}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-black border-2 cursor-pointer transition-colors ${
              activeTab === "BEAR_TRAP"
                ? "border-emerald-500 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                : "border-zinc-300 dark:border-[#303744] text-zinc-500 hover:text-white"
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>
              {ar ? "مصيدة الدببة — ارتداد شرائي (Spring)" : "Bear Traps (Spring)"} (
              {snapshot?.totalBearTraps ?? 0})
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("BULL_TRAP")}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-black border-2 cursor-pointer transition-colors ${
              activeTab === "BULL_TRAP"
                ? "border-rose-500 bg-rose-500/15 text-rose-600 dark:text-rose-400"
                : "border-zinc-300 dark:border-[#303744] text-zinc-500 hover:text-white"
            }`}
          >
            <TrendingDown className="w-3.5 h-3.5" />
            <span>
              {ar ? "مصيدة الثيران — اختراق وهمي (Upthrust)" : "Bull Traps (Upthrust)"} (
              {snapshot?.totalBullTraps ?? 0})
            </span>
          </button>
        </div>
      </div>

      {error ? (
        <p className="mt-3 text-xs font-bold text-rose-600 dark:text-rose-400">
          {ar ? "تعذر تحميل إشارات المصائد حالياً." : "Unable to load trap signals."}
        </p>
      ) : !snapshot ? (
        <p className="mt-3 text-xs font-semibold text-zinc-500 dark:text-zinc-400">
          {ar ? "جاري فحص شموع الإغلاق ومستويات الدعم والمقاومة..." : "Scanning closing candles..."}
        </p>
      ) : rows.length === 0 ? (
        <p className="mt-3 text-xs font-semibold text-zinc-500 dark:text-zinc-400">
          {ar ? "لا توجد مصائد مرصودة في هذا الاتجاه لجلسة الإغلاق الحالية." : "No traps detected in this direction."}
        </p>
      ) : (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {rows.map((row) => {
            const isBearTrap = row.trapType === "BEAR_TRAP";
            return (
              <Link
                key={row.symbol}
                href={`/stocks/${row.symbol}`}
                className="group border-2 border-zinc-200 bg-white p-3 transition hover:border-emerald-500 dark:border-[#303744] dark:bg-[#171e29]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-sm font-black">{row.symbol}</span>
                      <span
                        className={`px-1.5 py-0.5 text-[10px] font-black border ${
                          isBearTrap
                            ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500"
                            : "border-rose-500/40 bg-rose-500/10 text-rose-400"
                        }`}
                      >
                        {isBearTrap
                          ? ar
                            ? "كسر وهمي ارتدادي 🟢"
                            : "Spring 🟢"
                          : ar
                          ? "اختراق كاذب 🔴"
                          : "Upthrust 🔴"}
                      </span>
                    </div>
                    <p className="text-[11px] font-bold text-zinc-500 dark:text-zinc-400 line-clamp-1">
                      {row.nameAr}
                    </p>
                  </div>
                  <ArrowUpRight className="h-4 w-4 shrink-0 text-zinc-400 transition group-hover:text-emerald-500" />
                </div>

                <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-[11px]">
                  <div className="flex justify-between gap-1">
                    <dt className="text-zinc-500 dark:text-zinc-400">{ar ? "الإغلاق" : "Close"}</dt>
                    <dd className="font-mono font-bold">{row.close}</dd>
                  </div>
                  <div className="flex justify-between gap-1">
                    <dt className="text-zinc-500 dark:text-zinc-400">
                      {isBearTrap ? (ar ? "الدعم" : "Support") : ar ? "المقاومة" : "Resist"}
                    </dt>
                    <dd className="font-mono font-bold text-amber-500">{row.keyLevel}</dd>
                  </div>
                  <div className="flex justify-between gap-1">
                    <dt className="text-zinc-500 dark:text-zinc-400">
                      {isBearTrap ? (ar ? "ارتداد الذيل" : "Rebound") : ar ? "رفض الذيل" : "Reject"}
                    </dt>
                    <dd className="font-mono font-black text-emerald-500">{row.wickPct}%</dd>
                  </div>
                  <div className="flex justify-between gap-1">
                    <dt className="text-zinc-500 dark:text-zinc-400">{ar ? "قوة الإشارة" : "Score"}</dt>
                    <dd className="font-mono font-black text-indigo-400">{row.conviction}%</dd>
                  </div>
                </dl>
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}
