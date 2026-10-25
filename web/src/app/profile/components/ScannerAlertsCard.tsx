"use client";

import React, { useState, useEffect } from "react";
import {
  Zap,
  ArrowUpRight,
  Target,
  Star,
  Newspaper,
  Send,
  Lock,
  Sparkles,
  ExternalLink,
  Loader2,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp
} from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";
import { useLanguage } from "@/contexts/LanguageContext";
import { useTelegramPro } from "@/contexts/TelegramProContext";

interface ScannerPreferences {
  volume_surge: boolean;
  breakout: boolean;
  rsi_oversold: boolean;
  portfolio_watchlist: boolean;
  disclosures: boolean;
}

const DEFAULT_PREFS: ScannerPreferences = {
  volume_surge: true,
  breakout: true,
  rsi_oversold: true,
  portfolio_watchlist: true,
  disclosures: true,
};

interface ScannerAlertsCardProps {
  initialTelegramLinked?: boolean;
}

export default function ScannerAlertsCard({ initialTelegramLinked = false }: ScannerAlertsCardProps) {
  const { language } = useLanguage();
  const { invite: proInvite, loading: proInviteLoading, refresh: refreshProInvite } = useTelegramPro();
  const isAr = language === "ar";

  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [isPro, setIsPro] = useState(false);
  const [telegramLinked, setTelegramLinked] = useState(initialTelegramLinked);
  const [prefs, setPrefs] = useState<ScannerPreferences>(DEFAULT_PREFS);
  const [activeSignals, setActiveSignals] = useState<any[]>([]);
  const [closedSignals, setClosedSignals] = useState<any[]>([]);
  const [signalsKpis, setSignalsKpis] = useState<any>(null);

  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      try {
        return localStorage.getItem("egx_profile_scanner_collapsed") === "true";
      } catch {
        return false;
      }
    }
    return false;
  });

  const toggleCollapse = () => {
    setIsCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("egx_profile_scanner_collapsed", String(next));
      } catch {}
      return next;
    });
  };

  const vipChannelUrl = proInvite.is_pro && proInvite.invite_link ? proInvite.invite_link : "";

  useEffect(() => {
    if (initialTelegramLinked) {
      setTelegramLinked(true);
    }
  }, [initialTelegramLinked]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const checkHash = () => {
      const hash = window.location.hash;
      if (hash === "#scanner-signals" || hash === "#scanner-alerts" || hash === "#scanner") {
        setIsCollapsed(false);
        setTimeout(() => {
          const el = document.getElementById("scanner-signals");
          if (el) el.scrollIntoView({ behavior: "smooth" });
        }, 150);
      }
    };
    checkHash();
    window.addEventListener("hashchange", checkHash);
    return () => window.removeEventListener("hashchange", checkHash);
  }, []);

  const SCANNER_ALERTS_CACHE_KEY = "egx_scanner_alerts_cache_v2";

  useEffect(() => {
    let active = true;

    try {
      const cachedRaw = localStorage.getItem(SCANNER_ALERTS_CACHE_KEY);
      if (cachedRaw) {
        const cached = JSON.parse(cachedRaw);
        if (cached && cached.ok && active) {
          setIsPro(Boolean(cached.is_pro));
          if (cached.telegram_linked) setTelegramLinked(true);
          if (cached.preferences) setPrefs({ ...DEFAULT_PREFS, ...cached.preferences });
          if (Array.isArray(cached.active_signals)) setActiveSignals(cached.active_signals);
          if (Array.isArray(cached.closed_signals)) setClosedSignals(cached.closed_signals);
          if (cached.signals_kpis) setSignalsKpis(cached.signals_kpis);
        }
      }
    } catch {
      // ignore cache errors
    }

    async function fetchPrefs() {
      try {
        const res = await fetch("/api/user/scanner-alerts", {
          cache: "no-store",
        });
        if (!active) return;
        if (res.ok) {
          const data = await res.json();
          if (data.ok) {
            setIsPro(Boolean(data.is_pro));
            if (data.telegram_linked) setTelegramLinked(true);
            if (data.preferences) {
              setPrefs({ ...DEFAULT_PREFS, ...data.preferences });
            }
            if (Array.isArray(data.active_signals)) setActiveSignals(data.active_signals);
            if (Array.isArray(data.closed_signals)) setClosedSignals(data.closed_signals);
            if (data.signals_kpis) setSignalsKpis(data.signals_kpis);
            try {
              localStorage.setItem(SCANNER_ALERTS_CACHE_KEY, JSON.stringify(data));
            } catch {}
          }
        }
      } catch (err) {
        console.error("Failed to fetch scanner preferences:", err);
      }
    }

    void fetchPrefs();
    return () => {
      active = false;
    };
  }, []);

  const handleToggle = async (key: keyof ScannerPreferences) => {
    if (!isPro) {
      toast.error(
        isAr
          ? "تنبيهات الرادار اللحظية متاحة حصرياً لمشتركي باقة Pro."
          : "Live Scanner Alerts are exclusively available for Pro subscribers."
      );
      return;
    }

    const nextValue = !prefs[key];
    const updatedPrefs = { ...prefs, [key]: nextValue };
    setPrefs(updatedPrefs);
    setSavingKey(key);

    try {
      const res = await fetch("/api/user/scanner-alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences: updatedPrefs }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Failed to update");
      }
      toast.success(
        isAr ? "تم تحديث تفضيلات تنبيهات الرادار بنجاح" : "Scanner alert preferences updated"
      );
    } catch {
      setPrefs(prefs);
      toast.error(
        isAr ? "تعذر حفظ الإعدادات، يرجى المحاولة مرة أخرى" : "Could not save preferences, please try again"
      );
    } finally {
      setSavingKey(null);
    }
  };

  const alertTypes = [
    {
      id: "volume_surge" as const,
      icon: Zap,
      color: "bg-amber-400 text-black",
      titleAr: "رادار السيولة المؤسسية غير المعتادة",
      titleEn: "Unusual Institutional Volume Surge",
      descAr: "إشعار فوري عندما يشهد السهم تدفق سيولة يتجاوز ضعف المتوسط اليومي (2x+) أثناء الجلسة.",
      descEn: "Instant alert when a stock experiences 2x+ normal trading volume with institutional inflow.",
    },
    {
      id: "breakout" as const,
      icon: ArrowUpRight,
      color: "bg-emerald-400 text-black",
      titleAr: "ماسح الاختراق الفني وكسر المقاومات",
      titleEn: "Breakout & Resistance Scanner",
      descAr: "تنبيه لحظي عند اختراق سهم لقمته السابقة أو مقاومة فنية رئيسية بشمعة إيجابية قوية.",
      descEn: "Instant alert when a stock breaks through key resistance levels or 30-day highs with strong confirmation.",
    },
    {
      id: "rsi_oversold" as const,
      icon: Target,
      color: "bg-sky-400 text-black",
      titleAr: "ماسح الارتداد الفني والتشبع البيعي (RSI)",
      titleEn: "Oversold Technical Rebound (RSI)",
      descAr: "رصد الأسهم التي وصلت لمناطق تشبع بيعي حاد (RSI أقل من 28) وبدأت في تكوين شمعة ارتداد فني.",
      descEn: "Detects stocks entering deep oversold territory (RSI <= 28) forming technical reversal patterns.",
    },
    {
      id: "portfolio_watchlist" as const,
      icon: Star,
      color: "bg-purple-400 text-black",
      titleAr: "تنبيهات محفظتي وقائمة المتابعة فقط",
      titleEn: "My Portfolio & Watchlist Alerts",
      descAr: "تنبيهات مخصصة للأسهم المدرجة في محفظتك أو قائمة متابعتك عند اقترابها من المستويات الفنية الهامة.",
      descEn: "Custom alerts filtered for stocks in your portfolio or watchlist approaching key technical levels.",
    },
    {
      id: "disclosures" as const,
      icon: Newspaper,
      color: "bg-rose-400 text-black",
      titleAr: "رادار الإفصاحات والأخبار الرسمية",
      titleEn: "Official Disclosures & Corporate News",
      descAr: "إشعار فوري بأي إفصاح رسمي لشركات البورصة (توزيعات أرباح، زيادة رأسمال، صفقات استحواذ، نتائج أعمال).",
      descEn: "Instant notification for official EGX disclosures (dividends, capital increases, M&A, earnings releases).",
    },
  ];

  return (
    <section
      className={`relative z-10 min-w-0 rounded-xl sm:rounded-2xl p-3 sm:p-6 bg-white dark:bg-zinc-900 border-2 sm:border-4 border-black dark:border-white shadow-[3px_3px_0px_rgba(0,0,0,1)] sm:shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] sm:dark:shadow-[6px_6px_0px_rgba(255,255,255,1)] transition-all duration-200 ${
        isCollapsed ? "space-y-0" : "space-y-4 sm:space-y-6"
      }`}
    >
      {/* ── Section Header & Toggle Button ── */}
      <div
        className={`flex flex-col gap-3 sm:gap-4 sm:flex-row sm:items-center sm:justify-between ${
          isCollapsed ? "" : "border-b-2 sm:border-b-4 border-black dark:border-white pb-3 sm:pb-5"
        }`}
      >
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            <div className="h-8 w-8 sm:h-10 sm:w-10 border-2 sm:border-4 border-black dark:border-white bg-[#FFE600] text-black flex items-center justify-center shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] shrink-0">
              <SlidersHorizontal className="h-4 w-4 sm:h-5 sm:w-5" />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg sm:text-2xl font-black text-black dark:text-white uppercase tracking-tight italic">
                {isAr ? "تفضيلات تنبيهات الرصد اللحظي وتليجرام" : "Intraday Radar & Telegram Alert Preferences"}
              </h2>
              <span className="border-2 border-black dark:border-white bg-black text-[#FFE600] dark:bg-white dark:text-black px-2 py-0.5 text-[10px] font-black uppercase tracking-widest shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                {isPro ? "PRO VIP" : "PRO RADAR"}
              </span>
            </div>
          </div>
          <p className="text-xs text-zinc-600 dark:text-zinc-400 font-bold leading-relaxed">
            {isAr
              ? "تحكم في إشعارات التليجرام اللحظية، وانتقل مباشرة إلى لوحة إشارات الرصد اللحظي الموحدة بجانب إشارات المدى المتوسط والقصير."
              : "Manage instant Telegram notifications and jump directly to the unified Intraday Fast Signals hub."}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/scanner/backtests?tab=fast_scanner"
            className="h-8 sm:h-10 px-3 sm:px-4 flex items-center justify-center gap-1.5 border-2 sm:border-4 border-black bg-emerald-400 hover:bg-emerald-300 text-black font-black text-xs uppercase tracking-wider shadow-[2px_2px_0px_rgba(0,0,0,1)] transition-all"
          >
            <Target className="w-4 h-4" />
            <span>{isAr ? "فتح لوحة إشارات الرصد اللحظي 🎯" : "Open Intraday Signals Hub 🎯"}</span>
          </Link>

          <button
            type="button"
            onClick={toggleCollapse}
            className="h-8 sm:h-10 px-2.5 sm:px-3 flex items-center justify-center gap-1.5 border-2 sm:border-4 border-black dark:border-white bg-[#FFE600] text-black font-black text-xs uppercase tracking-wider shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,1)] transition-all cursor-pointer"
          >
            {isCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
            <span>{isCollapsed ? (isAr ? "عرض الإعدادات" : "Expand") : (isAr ? "طي السيكشن" : "Collapse")}</span>
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <div className="space-y-5 pt-1">
          {/* ── Unified Hub Relocation Callout Banner ── */}
          <div className="border-2 sm:border-4 border-black dark:border-white bg-emerald-50 dark:bg-emerald-950/30 p-3.5 sm:p-4 shadow-[3px_3px_0px_rgba(0,0,0,1)] flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="px-2 py-0.5 bg-emerald-400 text-black border border-black text-[11px] font-black">
                  {isAr ? "تحديث جديد ✨" : "New Unified View ✨"}
                </span>
                <h3 className="text-sm sm:text-base font-black text-black dark:text-white">
                  {isAr
                    ? "تم توحيد «إشارات الرصد اللحظي 🎯» بجانب إشارات المدى المتوسط والقصير!"
                    : "Intraday Fast Signals 🎯 is now unified alongside Medium & Short-Term Signals!"}
                </h3>
              </div>
              <p className="text-xs font-bold text-zinc-700 dark:text-zinc-300">
                {isAr
                  ? `يمكنك الآن متابعة الـ ${activeSignals.length} إشارة نشطة، الـ ${closedSignals.length} إشارة مغلقة، شارت الـ 15 دقيقة، وتقويم الأداء في صفحة الأنظمة الموحدة.`
                  : `Track all ${activeSignals.length} active signals, ${closedSignals.length} closed signals, 15m charts, and performance calendar in the unified systems hub.`}
              </p>
            </div>
            <Link
              href="/scanner/backtests?tab=fast_scanner"
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-black text-[#FFE600] hover:bg-zinc-800 border-2 border-black font-black text-xs uppercase shrink-0 shadow-[2px_2px_0px_#000]"
            >
              <Target className="w-4 h-4" />
              <span>{isAr ? "الانتقال إلى إشارات الرصد اللحظي" : "Go to Intraday Signals"}</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </Link>
          </div>

          {/* ── VIP Telegram Channel Access ── */}
          <div className="border-2 sm:border-4 border-black dark:border-white bg-[#FFE600] text-black p-3 sm:p-5 shadow-[3px_3px_0px_rgba(0,0,0,1)] sm:shadow-[4px_4px_0px_rgba(0,0,0,1)] flex flex-col md:flex-row items-start md:items-center justify-between gap-3 sm:gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2.5 bg-black text-[#FFE600] border-2 border-black shrink-0 shadow-[2px_2px_0px_rgba(0,0,0,1)]">
                <Send className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-black uppercase tracking-tight">
                  {isAr
                    ? "إشارات الرصد اللحظي (فريم 15 دقيقة) تُنشر فورياً في قناة Telegram VIP"
                    : "15-minute intraday radar signals are posted in the Telegram VIP channel"}
                </h3>
                <p className="text-xs font-bold mt-1 text-black/80 leading-relaxed max-w-2xl">
                  {isAr
                    ? "اشترك في قناة VIP من رابط الدعوة الخاص باشتراكك لمتابعة الإشارات لحظة بلحظة أثناء الجلسة."
                    : "Join the VIP channel using your subscription invite to follow intraday signals in real time."}
                </p>
              </div>
            </div>
            <div className="flex flex-col sm:flex-row items-center gap-2.5 shrink-0 w-full md:w-auto">
              {isPro ? (
                vipChannelUrl ? (
                  <>
                    <a
                      href={vipChannelUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center justify-center gap-2 px-4 py-3 bg-black text-[#FFE600] hover:bg-zinc-800 border-4 border-black font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] transition-all w-full sm:w-auto"
                    >
                      <Send className="w-4 h-4" />
                      {isAr ? "فتح قناة VIP" : "Open VIP Channel"}
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                    <button
                      type="button"
                      onClick={() => void refreshProInvite()}
                      disabled={proInviteLoading}
                      className="inline-flex items-center justify-center gap-2 px-3 py-3 bg-white text-black hover:bg-zinc-100 border-4 border-black font-black text-[10px] uppercase tracking-wider shadow-[2px_2px_0px_rgba(0,0,0,1)] disabled:opacity-50 w-full sm:w-auto cursor-pointer"
                    >
                      <Loader2 className={`w-3.5 h-3.5 ${proInviteLoading ? "animate-spin" : ""}`} />
                      {isAr ? "تجديد الرابط" : "Refresh Link"}
                    </button>
                  </>
                ) : (
                  <span className="text-xs font-black border-2 border-black bg-white px-3 py-2">
                    {proInviteLoading
                      ? isAr
                        ? "جاري تجهيز رابط الدعوة..."
                        : "Loading invite..."
                      : isAr
                      ? "رابط دعوة VIP غير متاح حالياً؛ حدّث الصفحة."
                      : "VIP invite unavailable. Refresh page."}
                  </span>
                )
              ) : (
                <Link
                  href="/pricing"
                  className="inline-flex items-center justify-center gap-2 px-4 py-3 bg-black text-[#FFE600] hover:bg-zinc-800 border-4 border-black font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] transition-all w-full sm:w-auto"
                >
                  <Sparkles className="w-4 h-4" />
                  {isAr ? "اشترك في Pro للوصول إلى VIP" : "Upgrade to Pro for VIP access"}
                </Link>
              )}
            </div>
          </div>

          {/* ── Scanner Alert Toggles Grid ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-5 pt-1 sm:pt-2">
            {alertTypes.map((item) => {
              const isEnabled = prefs[item.id];
              const isSaving = savingKey === item.id;
              const Icon = item.icon;

              return (
                <div
                  key={item.id}
                  className={`border-2 sm:border-4 border-black dark:border-white p-3.5 sm:p-5 shadow-[3px_3px_0px_rgba(0,0,0,1)] sm:shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] sm:dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] flex flex-col justify-between transition-all ${
                    isEnabled && isPro
                      ? "bg-zinc-50 dark:bg-zinc-800/80"
                      : "bg-zinc-100/60 dark:bg-zinc-950/40 opacity-80"
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between gap-2.5 mb-2">
                      <div className="flex items-center gap-2.5 min-w-0 flex-1">
                        <div
                          className={`h-9 w-9 sm:h-10 sm:w-10 border-2 sm:border-4 border-black dark:border-white flex items-center justify-center shrink-0 shadow-[2px_2px_0px_rgba(0,0,0,1)] ${item.color}`}
                        >
                          <Icon className="h-4 w-4 sm:h-5 sm:w-5" />
                        </div>
                        <div>
                          <h3 className="text-xs sm:text-sm font-black text-black dark:text-white uppercase tracking-tight leading-snug truncate">
                            {isAr ? item.titleAr : item.titleEn}
                          </h3>
                          <span className="text-[9px] sm:text-[10px] font-mono font-bold text-zinc-500 uppercase tracking-widest block truncate">
                            {item.id}
                          </span>
                        </div>
                      </div>

                      <div className="shrink-0 flex items-center">
                        {!isPro ? (
                          <span className="inline-flex items-center gap-1 border-2 border-black bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 px-2 py-1 text-[10px] font-black uppercase shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                            <Lock className="w-3 h-3" />
                            PRO
                          </span>
                        ) : (
                          <button
                            type="button"
                            dir="ltr"
                            onClick={() => handleToggle(item.id)}
                            disabled={isSaving}
                            className={`relative inline-flex h-6 w-12 sm:h-7 sm:w-14 shrink-0 cursor-pointer border-2 sm:border-4 border-black dark:border-white transition-colors duration-200 ease-in-out focus:outline-none shadow-[2px_2px_0px_rgba(0,0,0,1)] ${
                              isEnabled ? "bg-emerald-400" : "bg-zinc-300 dark:bg-zinc-700"
                            }`}
                            role="switch"
                            aria-checked={isEnabled}
                          >
                            <span
                              className={`pointer-events-none inline-block h-3.5 w-3.5 sm:h-4 sm:w-4 transform border-2 border-black bg-white transition duration-200 ease-in-out mt-0.5 ${
                                isEnabled ? "translate-x-6 sm:translate-x-7" : "translate-x-0.5"
                              }`}
                            />
                          </button>
                        )}
                      </div>
                    </div>

                    <p className="text-[11px] sm:text-xs font-bold text-zinc-700 dark:text-zinc-300 leading-relaxed mt-1">
                      {isAr ? item.descAr : item.descEn}
                    </p>
                  </div>

                  <div className="mt-2.5 pt-2 border-t-2 border-black/10 dark:border-white/10 flex items-center justify-between text-[10px] sm:text-[11px] font-mono font-bold">
                    <span className="text-zinc-500">{isAr ? "الحالة:" : "Status:"}</span>
                    {isSaving ? (
                      <span className="flex items-center gap-1 text-zinc-600 dark:text-zinc-400">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        {isAr ? "جاري الحفظ..." : "Saving..."}
                      </span>
                    ) : isPro ? (
                      isEnabled ? (
                        <span className="text-emerald-600 dark:text-emerald-400 font-black flex items-center gap-1">
                          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                          {isAr ? "مفعّل ونشط" : "Active & Armed"}
                        </span>
                      ) : (
                        <span className="text-zinc-400 font-black">{isAr ? "متوقف" : "Muted"}</span>
                      )
                    ) : (
                      <span className="text-amber-600 dark:text-amber-400 font-black flex items-center gap-1">
                        <Lock className="w-3 h-3" />
                        {isAr ? "متاح مع باقة Pro" : "Pro Plan Required"}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
