"use client";

import React, { useState, useEffect } from "react";
import { 
  Zap, 
  ArrowUpRight, 
  Target, 
  Star, 
  Newspaper, 
  Send, 
  CheckCircle2, 
  AlertTriangle, 
  Lock, 
  Sparkles,
  ExternalLink,
  Loader2,
  Globe,
  Calendar as CalendarIcon,
  Activity,
  SlidersHorizontal,
  BookOpen,
  ChevronDown,
  ChevronUp
} from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import ScannerStatsCalendar from "./ScannerStatsCalendar";
import ScannerDefinitionsGuide from "./ScannerDefinitionsGuide";
import ScannerSignalsTracker from "./ScannerSignalsTracker";

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
  const { user } = useAuth();
  const { language } = useLanguage();
  const isAr = language === "ar";

  const [activeMainTab, setActiveMainTab] = useState<"tracker" | "calendar" | "settings" | "guide">("tracker");
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [isPro, setIsPro] = useState(false);
  const [telegramLinked, setTelegramLinked] = useState(initialTelegramLinked);
  const [prefs, setPrefs] = useState<ScannerPreferences>(DEFAULT_PREFS);
  const [history, setHistory] = useState<any[]>([]);
  const [lastScan, setLastScan] = useState<any>(null);
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

  const botUsername = "egxbots_bot";
  const connectBotUrl = user?.id ? `https://t.me/${botUsername}?start=${user.id}` : `https://t.me/${botUsername}`;
  const connectBotWebUrl = user?.id
    ? `https://web.telegram.org/a/#?tgaddr=${encodeURIComponent(`tg://resolve?domain=${botUsername}&start=${user.id}`)}`
    : `https://web.telegram.org/a/#?tgaddr=${encodeURIComponent(`tg://resolve?domain=${botUsername}`)}`;

  useEffect(() => {
    if (initialTelegramLinked) {
      setTelegramLinked(true);
    }
  }, [initialTelegramLinked]);

  useEffect(() => {
    let isMounted = true;
    async function loadAlerts() {
      try {
        const res = await fetch("/api/user/scanner-alerts", { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          if (isMounted && data.ok) {
            setIsPro(Boolean(data.is_pro));
            setTelegramLinked(Boolean(data.telegram_linked));
            if (data.preferences) {
              setPrefs(data.preferences);
            }
            if (data.history) {
              setHistory(data.history);
            }
            if (data.last_scan) {
              setLastScan(data.last_scan);
            }
            if (data.active_signals) {
              setActiveSignals(data.active_signals);
            }
            if (data.closed_signals) {
              setClosedSignals(data.closed_signals);
            }
            if (data.signals_kpis) {
              setSignalsKpis(data.signals_kpis);
            }
          }
        }
      } catch (e) {
        console.error("Failed to load scanner alerts:", e);
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadAlerts();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleToggle = async (key: keyof ScannerPreferences) => {
    if (!isPro) {
      toast.info(
        isAr 
          ? "🔒 تنبيهات الإسكانر الفورية حصرية لمشتركي باقة Pro. اشترك لتفعيل الرادار اللحظي!" 
          : "🔒 Live scanner alerts are exclusive to Pro members. Upgrade to activate!"
      );
      return;
    }

    const updated = { ...prefs, [key]: !prefs[key] };
    setPrefs(updated);
    setSavingKey(key);

    try {
      const res = await fetch("/api/user/scanner-alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences: updated }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.preferences) setPrefs(data.preferences);
        toast.success(
          isAr 
            ? `تم ${updated[key] ? "تفعيل" : "إيقاف"} التنبيه بنجاح` 
            : `Alert ${updated[key] ? "activated" : "deactivated"} successfully`
        );
      } else {
        // Revert on error
        setPrefs(prefs);
        toast.error(isAr ? "تعذر حفظ التغييرات، حاول مجدداً" : "Failed to save settings");
      }
    } catch {
      setPrefs(prefs);
      toast.error(isAr ? "حدث خطأ في الاتصال" : "Connection error");
    } finally {
      setSavingKey(null);
    }
  };

  const alertTypes = [
    {
      id: "volume_surge" as const,
      icon: Zap,
      color: "bg-amber-300 text-black",
      badgeColor: "bg-amber-400 text-black",
      titleAr: "رادار السيولة الذكية والتجميع",
      titleEn: "Smart Money & Volume Surge",
      descAr: "رصد فوري للأسهم التي تشهد قفزة غير معتادة في أحجام التنفيذ والسيولة (أعلى من 150% من متوسط 20 جلسة) مع اتجاه صاعد.",
      descEn: "Real-time alert for stocks experiencing unusual volume surge (>150% of 20-day average) with upward momentum.",
    },
    {
      id: "breakout" as const,
      icon: ArrowUpRight,
      color: "bg-emerald-400 text-black",
      badgeColor: "bg-emerald-500 text-black",
      titleAr: "ماسح الاختراق وكسر المقاومات",
      titleEn: "Breakout & Resistance Scanner",
      descAr: "تنبيه لحظي عند اختراق سهم لقمته السابقة أو مقاومة فنية رئيسية بشمعة إيجابية قوية.",
      descEn: "Instant alert when a stock breaks through key resistance levels or 30-day highs with strong confirmation.",
    },
    {
      id: "rsi_oversold" as const,
      icon: Target,
      color: "bg-sky-400 text-black",
      badgeColor: "bg-sky-500 text-black",
      titleAr: "ماسح الارتداد والتشبع البيعي (RSI)",
      titleEn: "Oversold Bounce & Reversal",
      descAr: "رصد الأسهم القوية التي هبطت لمناطق تشبع بيعي حاد (RSI أقل من 30) وبدأت في تكوين شمعة ارتداد إيجابية.",
      descEn: "Catches quality stocks entering severe oversold territory (RSI < 30) forming reversal candlestick patterns.",
    },
    {
      id: "portfolio_watchlist" as const,
      icon: Star,
      color: "bg-purple-400 text-black",
      badgeColor: "bg-purple-500 text-white",
      titleAr: "تنبيهات محفظتي وقائمتي الخاصة فقط",
      titleEn: "My Portfolio & Watchlist Alerts",
      descAr: "تنبيهات مخصصة حصراً للأسهم التي تمتلكها في محفظتك أو تتابعها في قائمتك عند كسر الدعم أو اقترابها من الهدف.",
      descEn: "Custom alerts strictly filtered for stocks in your portfolio or watchlist approaching key targets or stop-loss.",
    },
    {
      id: "disclosures" as const,
      icon: Newspaper,
      color: "bg-rose-400 text-black",
      badgeColor: "bg-rose-500 text-white",
      titleAr: "رادار الإفصاحات والأخبار الرسمية",
      titleEn: "Official Disclosures & Corporate News",
      descAr: "إشعار فوري بأي إفصاح رسمي لشركات البورصة (توزيعات أرباح، زيادة رأسمال، صفقات استحواذ، نتائج أعمال).",
      descEn: "Instant push notification for official EGX disclosures (dividends, capital increases, M&A, earnings releases).",
    },
  ];

  return (
    <section className={`relative z-10 min-w-0 rounded-2xl p-4 sm:p-6 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_rgba(255,255,255,1)] transition-all duration-200 ${isCollapsed ? "space-y-0" : "space-y-6"}`}>
      {/* ── Section Header & Toggle Button ── */}
      <div className={`flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between ${isCollapsed ? "" : "border-b-4 border-black dark:border-white pb-5"}`}>
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 border-4 border-black dark:border-white bg-[#FFE600] text-black flex items-center justify-center shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] shrink-0">
              <Activity className="h-5 w-5" />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-black text-black dark:text-white uppercase tracking-tight italic">
                {isAr ? "رادار وإسكانر الصفقات اللحظية" : "Live Signals & Scanner Radar"}
              </h2>
              <span className="border-2 border-black dark:border-white bg-black text-[#FFE600] dark:bg-white dark:text-black px-2 py-0.5 text-[10px] font-black uppercase tracking-widest shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                {isPro ? "PRO VIP" : "PRO RADAR"}
              </span>
              {isCollapsed && (
                <span className="border-2 border-black dark:border-white bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 px-2 py-0.5 text-[10px] font-black uppercase tracking-wider shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                  {isAr ? "مطوي" : "Collapsed"}
                </span>
              )}
            </div>
          </div>
          {!isCollapsed ? (
            <p className="text-xs text-zinc-600 dark:text-zinc-400 font-black uppercase tracking-widest leading-relaxed">
              {isAr
                ? "متابعة دقيقة للصفقات اللحظية المفتوحة والمغلقة، سجل الجلسات، وتنبيهات التليجرام الفورية"
                : "Live tracking of active & closed trades, historical calendar sessions, and Telegram alerts"}
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-2 text-xs font-bold mt-1 text-zinc-600 dark:text-zinc-400">
              <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 font-black border border-emerald-500/40 rounded">
                {activeSignals.length} {isAr ? "إشارة مفتوحة حالياً" : "Active Signals"}
              </span>
              <span className="text-zinc-300 dark:text-zinc-600">•</span>
              <span className="px-2 py-0.5 bg-sky-500/20 text-sky-600 dark:text-sky-400 font-black border border-sky-500/40 rounded">
                {closedSignals.length} {isAr ? "صفقة مغلقة" : "Closed Trades"}
              </span>
              {signalsKpis?.winRate != null && (
                <>
                  <span className="text-zinc-300 dark:text-zinc-600">•</span>
                  <span className="font-mono font-black text-emerald-600 dark:text-emerald-400">
                    {isAr ? "نسبة النجاح:" : "Win Rate:"} {signalsKpis.winRate}%
                  </span>
                </>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleCollapse}
            className="h-10 px-3 flex items-center justify-center gap-1.5 border-4 border-black dark:border-white bg-[#FFE600] text-black font-black text-xs uppercase tracking-wider shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all cursor-pointer"
            title={isCollapsed ? (isAr ? "فتح السيكشن" : "Expand Section") : (isAr ? "طي السيكشن" : "Collapse Section")}
          >
            {isCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
            <span>{isCollapsed ? (isAr ? "عرض الإسكانر" : "Expand") : (isAr ? "طي السيكشن" : "Collapse")}</span>
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <div className="space-y-6 pt-1">
          {/* ── Main Tab Navigation Bar (Neobrutal) ── */}
          <div className="flex flex-wrap items-center gap-2 p-2 bg-zinc-100 dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
            <button
              type="button"
              onClick={() => setActiveMainTab("tracker")}
              className={`flex items-center gap-2 px-4 py-2.5 font-black text-sm uppercase transition-all border-2 border-black dark:border-white ${
            activeMainTab === "tracker"
              ? "bg-[#FFE600] text-black shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] -translate-x-0.5 -translate-y-0.5"
              : "bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700"
          }`}
        >
          <Activity className="w-4 h-4" />
          <span>{isAr ? "متابعة الصفقات والإشارات" : "Signals & Trades"}</span>
          {activeSignals.length > 0 && (
            <span className="px-1.5 py-0.5 bg-emerald-500 text-black text-[11px] font-black border border-black rounded-full animate-pulse">
              {activeSignals.length}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setActiveMainTab("calendar")}
          className={`flex items-center gap-2 px-4 py-2.5 font-black text-sm uppercase transition-all border-2 border-black dark:border-white ${
            activeMainTab === "calendar"
              ? "bg-[#FFE600] text-black shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] -translate-x-0.5 -translate-y-0.5"
              : "bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700"
          }`}
        >
          <CalendarIcon className="w-4 h-4" />
          <span>{isAr ? "سجل الجلسات التاريخي" : "Sessions Calendar"}</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveMainTab("settings")}
          className={`flex items-center gap-2 px-4 py-2.5 font-black text-sm uppercase transition-all border-2 border-black dark:border-white ${
            activeMainTab === "settings"
              ? "bg-[#FFE600] text-black shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] -translate-x-0.5 -translate-y-0.5"
              : "bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700"
          }`}
        >
          <SlidersHorizontal className="w-4 h-4" />
          <span>{isAr ? "تفضيلات التنبيهات" : "Alert Preferences"}</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveMainTab("guide")}
          className={`flex items-center gap-2 px-4 py-2.5 font-black text-sm uppercase transition-all border-2 border-black dark:border-white ${
            activeMainTab === "guide"
              ? "bg-[#FFE600] text-black shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] -translate-x-0.5 -translate-y-0.5"
              : "bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700"
          }`}
        >
          <BookOpen className="w-4 h-4" />
          <span>{isAr ? "دليل استراتيجيات الإسكانر" : "Scanner Guide"}</span>
        </button>
      </div>

      {/* ── Active Main Tab View ── */}
      {activeMainTab === "tracker" && (
        <ScannerSignalsTracker
          activeSignals={activeSignals}
          closedSignals={closedSignals}
          kpis={signalsKpis}
          isAr={isAr}
        />
      )}

      {activeMainTab === "calendar" && (
        <ScannerStatsCalendar
          history={history}
          lastScan={lastScan}
          isAr={isAr}
        />
      )}

      {activeMainTab === "guide" && (
        <ScannerDefinitionsGuide isAr={isAr} />
      )}

      {activeMainTab === "settings" && (
        <section className="neobrutal-card p-6 sm:p-8 space-y-6 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_rgba(255,255,255,1)] relative z-10">
      {/* ── Section Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-4 border-black dark:border-white pb-5">
        <div className="flex items-center gap-3">
          <div className="h-12 w-12 border-4 border-black dark:border-white bg-[#FFE600] text-black flex items-center justify-center shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)]">
            <Zap className="h-6 w-6 fill-black" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-2xl font-black text-black dark:text-white uppercase tracking-tight italic">
                {isAr ? "تفضيلات تنبيهات الإسكانر" : "Scanner Alerts Preferences"}
              </h2>
              <span className="border-2 border-black dark:border-white bg-black text-[#FFE600] dark:bg-white dark:text-black px-2 py-0.5 text-[10px] font-black uppercase tracking-widest shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                {isPro ? "PRO VIP" : "PRO FEATURE"}
              </span>
            </div>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 font-bold mt-1">
              {isAr
                ? "حدد أنواع الإشارات والتنبيهات الفنية والإفصاحات التي تريد استلامها فورياً على تليجرام."
                : "Choose which technical signals and disclosure alerts you want to receive directly on Telegram."}
            </p>
          </div>
        </div>

        {/* Pro / Free Badge */}
        {!isPro && (
          <Link
            href="/pricing"
            className="inline-flex items-center gap-2 px-4 py-2 bg-[#FFE600] hover:bg-amber-400 text-black border-4 border-black font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] hover:-translate-x-0.5 hover:-translate-y-0.5 transition-all shrink-0"
          >
            <Sparkles className="w-4 h-4 fill-black" />
            {isAr ? "ترقية لتفعيل التنبيهات (50 ج.م)" : "Upgrade to Activate (50 EGP)"}
          </Link>
        )}
      </div>

      {/* ── Telegram Connection Banner (If Not Linked) ── */}
      {!telegramLinked && (
        <div className="border-4 border-black dark:border-white bg-[#FFE600] text-black p-5 shadow-[4px_4px_0px_rgba(0,0,0,1)] flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2.5 bg-black text-[#FFE600] border-2 border-black shrink-0 shadow-[2px_2px_0px_rgba(0,0,0,1)]">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-black uppercase tracking-tight">
                {isAr ? "⚠️ تنبيهات التليجرام غير متصلة بحسابك!" : "⚠️ Telegram Alerts Are Not Connected Yet!"}
              </h3>
              <p className="text-xs font-bold mt-1 text-black/80 leading-relaxed max-w-xl">
                {isAr
                  ? "لتصلك التنبيهات والإشارات الفورية لحظياً على هاتفك، اضغط على الزر أدناه لبدء المحادثة مع البوت وربطه بحسابك بضغطة زر واحدة مجاناً."
                  : "To receive instant push alerts on your phone, click below to start a conversation with the bot and link your account in 1 click."}
              </p>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-center gap-2.5 shrink-0 w-full md:w-auto">
            <a
              href={connectBotUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 px-4 py-3 bg-black text-[#FFE600] hover:bg-zinc-800 border-4 border-black font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] hover:-translate-x-0.5 hover:-translate-y-0.5 active:translate-x-[1px] active:translate-y-[1px] transition-all w-full sm:w-auto"
            >
              <Send className="w-4 h-4 fill-[#FFE600]" />
              {isAr ? "فتح التطبيق (App)" : "Open in App"}
              <ExternalLink className="w-3.5 h-3.5 ml-0.5" />
            </a>
            <a
              href={connectBotWebUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 px-4 py-3 bg-white text-black hover:bg-zinc-100 border-4 border-black font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] hover:-translate-x-0.5 hover:-translate-y-0.5 active:translate-x-[1px] active:translate-y-[1px] transition-all w-full sm:w-auto"
            >
              <Globe className="w-4 h-4" />
              {isAr ? "فتح ويب (Telegram Web)" : "Open in Web"}
              <ExternalLink className="w-3.5 h-3.5 ml-0.5" />
            </a>
          </div>
        </div>
      )}

      {/* ── Connected Confirmation (If Linked) ── */}
      {telegramLinked && (
        <div className="border-4 border-black dark:border-white bg-emerald-400 text-black px-4 py-3 shadow-[3px_3px_0px_rgba(0,0,0,1)] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-black shrink-0" />
            <span className="text-xs font-black uppercase tracking-wider">
              {isAr ? "بوت التليجرام متصل بنجاح — التنبيهات المحددة ستصلك فورياً على هاتفك" : "Telegram bot connected — Selected alerts will be sent directly to your phone"}
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <a
              href={connectBotWebUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 border-2 border-black bg-white hover:bg-zinc-100 text-black px-2.5 py-1 text-[11px] font-black uppercase shadow-[1.5px_1.5px_0px_#000] transition-transform active:translate-y-0.5"
            >
              <Globe className="w-3.5 h-3.5" />
              {isAr ? "فتح تليجرام ويب" : "Open Web"}
            </a>
            <span className="text-[10px] font-mono font-black border-2 border-black bg-white px-2 py-0.5">
              @{botUsername}
            </span>
          </div>
        </div>
      )}

      {/* ── Scanner Alert Toggles Grid ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-2">
        {alertTypes.map((item) => {
          const isEnabled = prefs[item.id];
          const isSaving = savingKey === item.id;
          const Icon = item.icon;

          return (
            <div
              key={item.id}
              className={`border-4 border-black dark:border-white p-5 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] flex flex-col justify-between transition-all ${
                isEnabled && isPro
                  ? "bg-zinc-50 dark:bg-zinc-800/80"
                  : "bg-zinc-100/60 dark:bg-zinc-950/40 opacity-80"
              }`}
            >
              <div>
                {/* Card Top Row */}
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={`h-10 w-10 border-4 border-black dark:border-white flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] ${item.color}`}
                    >
                      <Icon className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="text-sm font-black text-black dark:text-white uppercase tracking-tight">
                        {isAr ? item.titleAr : item.titleEn}
                      </h3>
                      <span className="text-[10px] font-mono font-bold text-zinc-500 uppercase tracking-widest block">
                        {item.id}
                      </span>
                    </div>
                  </div>

                  {/* Toggle Switch */}
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
                        className={`relative inline-flex h-7 w-14 shrink-0 cursor-pointer border-4 border-black dark:border-white transition-colors duration-200 ease-in-out focus:outline-none shadow-[2px_2px_0px_rgba(0,0,0,1)] ${
                          isEnabled ? "bg-emerald-400" : "bg-zinc-300 dark:bg-zinc-700"
                        }`}
                        role="switch"
                        aria-checked={isEnabled}
                        title={isAr ? "تشغيل/إيقاف التنبيه" : "Toggle Alert"}
                      >
                        <span
                          className={`pointer-events-none inline-block h-4 w-4 transform border-2 border-black bg-white transition duration-200 ease-in-out mt-0.5 ${
                            isEnabled ? "translate-x-7" : "translate-x-0.5"
                          }`}
                        />
                      </button>
                    )}
                  </div>
                </div>

                {/* Description */}
                <p className="text-xs font-bold text-zinc-700 dark:text-zinc-300 leading-relaxed mt-2">
                  {isAr ? item.descAr : item.descEn}
                </p>
              </div>

              {/* Status footer */}
              <div className="mt-4 pt-3 border-t-2 border-black/10 dark:border-white/10 flex items-center justify-between text-[11px] font-mono font-bold">
                <span className="text-zinc-500">
                  {isAr ? "الحالة:" : "Status:"}
                </span>
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
                    <span className="text-zinc-400 font-black">
                      {isAr ? "متوقف" : "Muted"}
                    </span>
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
    </section>
      )}
        </div>
      )}
    </section>
  );
}
