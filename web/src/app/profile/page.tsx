"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { useWatchlist, type SavedSymbol } from "@/contexts/WatchlistContext";
import { useTelegramPro } from "@/contexts/TelegramProContext";
import { Loader2, Send, Globe, Star, Trash2, Edit3, X, Check, ExternalLink, User, Wallet, CheckCircle2, Smartphone, ChevronDown, ChevronUp, Bot } from "lucide-react";
import { toast } from "sonner";
import MyPortfolioSection from "./components/MyPortfolioSection";
import PlanQuotaCard from "./components/PlanQuotaCard";
import FoundingMemberBanner from "./components/FoundingMemberBanner";
import ScannerAlertsCard from "./components/ScannerAlertsCard";

export default function ProfilePage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const { t, language } = useLanguage();
  const { watchlist, updateSymbol, removeSymbol } = useWatchlist();
  const { invite: proInvite, loading: inviteLoading, error: inviteError, refresh: refreshProInvite } = useTelegramPro();
  const isAr = language === "ar";
  const supabase = useMemo(() => createSupabaseBrowserClient(), []);
  const userId = user?.id ?? null;
  const lastProfileRefreshAtRef = useRef(0);

  const [username, setUsername] = useState<string | null>(null);
  const [telegramLinked, setTelegramLinked] = useState(false);
  const [whatsappNumber, setWhatsappNumber] = useState<string | null>(null);
  const [isEditingPhone, setIsEditingPhone] = useState(false);
  const [phoneDraft, setPhoneDraft] = useState("");
  const [savingPhone, setSavingPhone] = useState(false);
  const [quotaData, setQuotaData] = useState<any>(null);
  const proInviteUrl = proInvite.is_pro && proInvite.invite_link ? proInvite.invite_link : "";
  const freeTelegramUrl = "https://t.me/egxbots/153";
  const freeTelegramWebUrl = "https://web.telegram.org/a/#@egxbots";
  const telegramWebUrl = (() => {
    const url = proInviteUrl || freeTelegramWebUrl;
    if (!proInviteUrl) return url;
    const match = url.match(/^https?:\/\/(?:www\.)?t\.me\/(?:\+|joinchat\/)([^/?#]+)/i);
    return match
      ? `https://web.telegram.org/k/#?tgaddr=${encodeURIComponent(`tg://join?invite=${match[1]}`)}`
      : url;
  })();
  const botAppUrl = userId ? `https://t.me/egxbots_bot?start=${userId}` : "https://t.me/egxbots_bot?start=alerts";
  const botWebUrl = `https://web.telegram.org/k/#?tgaddr=${encodeURIComponent(`tg://resolve?domain=egxbots_bot&start=${userId || "alerts"}`)}`;
  const [editingSymbolId, setEditingSymbolId] = useState<string | null>(null);
  const [watchlistDraft, setWatchlistDraft] = useState({ name: "" });
  const [portfolioVersion, setPortfolioVersion] = useState(0);

  const [accountCollapsed, setAccountCollapsed] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      try {
        return localStorage.getItem("egx_profile_account_collapsed") === "true";
      } catch {
        return false;
      }
    }
    return false;
  });

  const [watchlistCollapsed, setWatchlistCollapsed] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      try {
        return localStorage.getItem("egx_profile_watchlist_collapsed") === "true";
      } catch {
        return false;
      }
    }
    return false;
  });

  const toggleAccountCollapsed = () => {
    setAccountCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("egx_profile_account_collapsed", String(next));
      } catch {}
      return next;
    });
  };

  const toggleWatchlistCollapsed = () => {
    setWatchlistCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("egx_profile_watchlist_collapsed", String(next));
      } catch {}
      return next;
    });
  };

  const handleToggleAllSections = (collapse: boolean) => {
    try {
      localStorage.setItem("egx_portfolio_section_collapsed", String(collapse));
      localStorage.setItem("egx_profile_plan_collapsed", String(collapse));
      localStorage.setItem("egx_profile_scanner_collapsed", String(collapse));
      localStorage.setItem("egx_profile_account_collapsed", String(collapse));
      localStorage.setItem("egx_profile_watchlist_collapsed", String(collapse));
    } catch {}
    setAccountCollapsed(collapse);
    setWatchlistCollapsed(collapse);
    setPortfolioVersion((v) => v + 1);
  };

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, router, user]);

  const reloadProfile = useCallback(async () => {
    if (!userId) return;
    lastProfileRefreshAtRef.current = Date.now();
    const { data: profileRow } = await supabase
      .from("profiles")
      .select("username, display_name, telegram_chat_id, whatsapp_number")
      .eq("id", userId)
      .maybeSingle();
    if (profileRow) {
      setUsername((profileRow as any).username || (profileRow as any).display_name || null);
      setTelegramLinked(Boolean((profileRow as any).telegram_chat_id));
      setWhatsappNumber((profileRow as any).whatsapp_number || null);
    }

    try {
      const qRes = await fetch("/api/user/quota", { cache: "no-store" });
      if (qRes.ok) {
        const qJson = await qRes.json();
        if (qJson.ok) setQuotaData(qJson);
      }
    } catch {}
  }, [supabase, userId]);

  const handleSavePhone = async () => {
    if (!userId) return;
    const cleanPhone = phoneDraft.trim().replace(/[\s-]/g, "");
    if (cleanPhone && !/^01[0125]\d{8}$/.test(cleanPhone)) {
      toast.error(isAr ? "أدخل رقم موبايل مصري صحيح (11 رقم يبدأ بـ 01)" : "Enter a valid 11-digit Egyptian mobile number");
      return;
    }
    setSavingPhone(true);
    try {
      const { error } = await supabase
        .from("profiles")
        .update({ whatsapp_number: cleanPhone || null, updated_at: new Date().toISOString() })
        .eq("id", userId);
      if (error) throw error;
      setWhatsappNumber(cleanPhone || null);
      setIsEditingPhone(false);
      toast.success(isAr ? "تم حفظ رقم الواتساب بنجاح" : "Phone number saved successfully");
    } catch {
      toast.error(isAr ? "تعذر حفظ الرقم، حاول مجدداً" : "Could not save phone number");
    } finally {
      setSavingPhone(false);
    }
  };

  useEffect(() => {
    if (!userId) return;
    void reloadProfile();
  }, [reloadProfile, userId]);

  useEffect(() => {
    if (!userId) return;
    const refreshWhenVisible = () => {
      if (document.visibilityState !== "visible") return;
      if (Date.now() - lastProfileRefreshAtRef.current < 60_000) return;
      void reloadProfile();
    };
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => document.removeEventListener("visibilitychange", refreshWhenVisible);
  }, [reloadProfile, userId]);

  // Auto-scroll smoothly to portfolio section if hash is #portfolio
  useEffect(() => {
    const handleHashScroll = () => {
      if (typeof window !== "undefined" && (window.location.hash === "#portfolio" || window.location.hash === "#my-portfolio")) {
        const timer = setTimeout(() => {
          const el = document.getElementById("portfolio");
          if (el) {
            el.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        }, 200);
        return () => clearTimeout(timer);
      }
    };
    handleHashScroll();
    window.addEventListener("hashchange", handleHashScroll);
    return () => window.removeEventListener("hashchange", handleHashScroll);
  }, []);

  function beginEditWatchlistItem(item: SavedSymbol) {
    setEditingSymbolId(item.id);
    setWatchlistDraft({ name: item.name || item.symbol });
  }

  async function saveWatchlistItem(item: SavedSymbol) {
    const ok = await updateSymbol(item.id, {
      name: watchlistDraft.name.trim() || item.symbol,
    });
    if (ok) setEditingSymbolId(null);
  }

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div dir={isAr ? "rtl" : "ltr"} className="profile-page-shell neobrutal-layout flex flex-col gap-5 sm:gap-8 pb-20 max-w-[1600px] mx-auto mt-2 px-2 sm:px-4 neobrutal-grid-bg min-h-screen">
      {/* ── Founding Member Announcement Banner ── */}
      {quotaData?.plan?.is_founding_member && (
        <div className="w-full relative z-20">
          <FoundingMemberBanner
            memberNumber={quotaData.plan.founding_member_number}
            language={language}
          />
        </div>
      )}

      {/* ── Header ── */}
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 relative z-10 pt-2 border-b-4 border-black dark:border-white pb-4">
        <div>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tighter text-black dark:text-white uppercase italic drop-shadow-[3px_3px_0px_rgba(0,0,0,1)]">
            {t("nav.profile")}
          </h1>
          <p className="text-sm text-zinc-700 dark:text-zinc-400 font-bold max-w-lg mt-1">
            {isAr
              ? "أدر محفظتك، وتابع قناة التليجرام، واضبط قائمة المراقبة وإشارات الإسكانر من مكان واحد."
              : "Manage your portfolio, follow our Telegram channel, and keep your watchlist & scanner signals in one place."}
          </p>
        </div>

        {/* Global Collapse / Expand All controls */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => handleToggleAllSections(true)}
            className="h-10 px-3.5 flex items-center gap-2 border-4 border-black dark:border-white bg-zinc-200 dark:bg-zinc-800 text-black dark:text-white font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all hover:bg-zinc-300 dark:hover:bg-zinc-700 cursor-pointer"
            title={isAr ? "طي جميع الأقسام لعرض مختصر وسريع" : "Collapse all sections"}
          >
            <ChevronUp className="w-4 h-4" />
            <span>{isAr ? "طي الكل" : "Collapse All"}</span>
          </button>
          <button
            type="button"
            onClick={() => handleToggleAllSections(false)}
            className="h-10 px-3.5 flex items-center gap-2 border-4 border-black dark:border-white bg-[#FFE600] text-black font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all hover:bg-amber-300 cursor-pointer"
            title={isAr ? "فتح جميع الأقسام بالتفصيل" : "Expand all sections"}
          >
            <ChevronDown className="w-4 h-4" />
            <span>{isAr ? "فتح الكل" : "Expand All"}</span>
          </button>
        </div>
      </header>

      {/* ── Telegram Bot Activation Banner (تفعيل بوت التليجرام في الخاص) ── */}
      {proInvite.bot_active ? (
        <section className="relative z-20 w-full rounded-xl sm:rounded-2xl p-4 sm:p-5 border-4 border-black dark:border-white bg-emerald-400 dark:bg-emerald-500 text-black shadow-[4px_4px_0px_rgba(0,0,0,1)] sm:shadow-[6px_6px_0px_rgba(0,0,0,1)]">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div className="flex items-start sm:items-center gap-3">
              <div className="h-11 w-11 border-4 border-black bg-black text-emerald-400 flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] shrink-0">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="border-2 border-black bg-black text-white px-2 py-0.5 text-[10px] font-black uppercase tracking-wider">
                    {isAr ? "البوت مفعل بنجاح" : "Bot Active"}
                  </span>
                  <span className="text-xs font-black text-black uppercase tracking-wider">
                    {isAr ? "إشارات وتنبيهات الخاص متصلة" : "Private DM Alerts Active"}
                  </span>
                </div>
                <p className="text-xs sm:text-sm font-bold text-zinc-950 leading-snug max-w-2xl">
                  {isAr
                    ? "حسابك متصل ومفعل في الخاص مع بوت (@egxbots_bot). تصلك إشارات الإسكانر اللحظية وتنبيهات الأهداف وتذكيرات التجديد مباشرة."
                    : "Your account is linked and active in private with @egxbots_bot. You receive instant scanner signals, target alerts, and renewal reminders."}
                </p>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 shrink-0">
              <a
                href={botAppUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-10 px-4 items-center justify-center gap-2 border-3 border-black bg-black text-emerald-400 font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[4px_4px_0px_rgba(0,0,0,1)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-all cursor-pointer"
              >
                <Smartphone className="w-4 h-4 shrink-0" />
                <span>{isAr ? "فتح في التطبيق (App)" : "Open in App"}</span>
              </a>
              <a
                href={botWebUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-10 px-4 items-center justify-center gap-2 border-3 border-black bg-white text-black font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[4px_4px_0px_rgba(0,0,0,1)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-all cursor-pointer"
              >
                <Globe className="w-4 h-4 shrink-0" />
                <span>{isAr ? "فتح في الويب (Web)" : "Open in Web"}</span>
              </a>
            </div>
          </div>
        </section>
      ) : (
        <section className="relative z-20 w-full rounded-xl sm:rounded-2xl p-4 sm:p-5 border-4 border-black dark:border-white bg-[#FFE600] dark:bg-yellow-400 text-black shadow-[4px_4px_0px_rgba(0,0,0,1)] sm:shadow-[6px_6px_0px_rgba(0,0,0,1)]">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div className="flex items-start sm:items-center gap-3">
              <div className="h-11 w-11 border-4 border-black bg-black text-[#FFE600] flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] shrink-0">
                <Bot className="h-6 w-6" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="border-2 border-black bg-black text-white px-2 py-0.5 text-[10px] font-black uppercase tracking-wider">
                    {isAr ? "خطوة هامة لتفعيل التنبيهات" : "Action Required"}
                  </span>
                  <span className="text-xs font-black text-black uppercase tracking-wider">
                    {(telegramLinked || proInvite.telegram_chat_id)
                      ? (isAr ? "مسجل في القناة — مطلوب تفعيل شات البوت في الخاص" : "In Channel — Activate Bot DM")
                      : (isAr ? "تفعيل إشارات وتنبيهات البوت في الخاص" : "Activate Private Telegram Bot Alerts")}
                  </span>
                </div>
                <p className="text-xs sm:text-sm font-bold text-zinc-950 leading-snug max-w-2xl">
                  {(telegramLinked || proInvite.telegram_chat_id)
                    ? (isAr
                      ? "⚠️ البوت لا يستطيع إرسال إشارات الإسكانر أو تنبيهات الأهداف إليك حتى تبدأ المحادثة معه في الخاص. افتح البوت واضغط زر Start (بدء):"
                      : "⚠️ The bot cannot send scanner signals or target alerts until you start a private chat with it. Open the bot and press Start:")
                    : (isAr
                      ? "⚠️ لاستلام إشارات الإسكانر اللحظية وتنبيهات الأهداف وتذكيرات اشتراكك مباشرة في الخاص، افتح البوت واضغط زر Start (بدء):"
                      : "⚠️ To receive instant scanner signals, target alerts, and renewal reminders in private DM, open the bot and press Start:")}
                </p>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 shrink-0">
              <a
                href={botAppUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-11 px-4 items-center justify-center gap-2 border-3 border-black bg-black text-[#FFE600] font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[4px_4px_0px_rgba(0,0,0,1)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-all cursor-pointer"
              >
                <Smartphone className="w-4 h-4 shrink-0" />
                <span>{isAr ? "تطبيق تليجرام (App)" : "Telegram App"}</span>
              </a>
              <a
                href={botWebUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-11 px-4 items-center justify-center gap-2 border-3 border-black bg-white text-black font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[4px_4px_0px_rgba(0,0,0,1)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-all cursor-pointer"
              >
                <Globe className="w-4 h-4 shrink-0" />
                <span>{isAr ? "ويب تليجرام (Web)" : "Telegram Web"}</span>
              </a>
              <button
                type="button"
                onClick={() => {
                  void refreshProInvite();
                  void reloadProfile();
                  toast.info(isAr ? "جاري التحقق من تفعيل البوت..." : "Checking bot status...");
                }}
                className="inline-flex h-11 px-3 items-center justify-center gap-1.5 border-3 border-black bg-zinc-200 dark:bg-zinc-800 text-black dark:text-white font-black text-xs uppercase tracking-wider shadow-[2px_2px_0px_rgba(0,0,0,1)] hover:bg-zinc-300 dark:hover:bg-zinc-700 transition-all cursor-pointer"
                title={isAr ? "اضغط بعد تفعيل البوت للتحقق الفوري" : "Click after starting bot to verify"}
              >
                <Check className="w-3.5 h-3.5" />
                <span>{isAr ? "تحقق" : "Verify"}</span>
              </button>
            </div>
          </div>
        </section>
      )}

      {/* ── Plan & Quota (الخطة والكوتا) ── */}
      <PlanQuotaCard key={`quota-${portfolioVersion}`} refreshTrigger={portfolioVersion} />

      {/* ── My Portfolio (محفظتى) ── */}
      <div id="portfolio" className="scroll-mt-8">
        <MyPortfolioSection
          key={`portfolio-${portfolioVersion}`}
          onPortfolioUpdated={() => setPortfolioVersion((v) => v + 1)}
        />
      </div>

      {/* ── Scanner Alerts Preferences & Live Signals Tracker (تفضيلات وتتبع إشارات الإسكانر) ── */}
      <div id="scanner-signals" className="scroll-mt-24">
        <ScannerAlertsCard key={`scanner-${portfolioVersion}`} initialTelegramLinked={telegramLinked} />
      </div>

      {/* ── Account + Telegram ── */}
      <section className={`relative z-10 min-w-0 rounded-xl sm:rounded-2xl p-3 sm:p-6 bg-white dark:bg-zinc-900 border-2 sm:border-4 border-black dark:border-white shadow-[3px_3px_0px_rgba(0,0,0,1)] sm:shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] sm:dark:shadow-[6px_6px_0px_rgba(255,255,255,1)] transition-all duration-200 ${accountCollapsed ? "space-y-0" : "space-y-4 sm:space-y-6"}`}>
        <div className={`flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between ${accountCollapsed ? "" : "border-b-4 border-black dark:border-white pb-5"}`}>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 border-4 border-black dark:border-white bg-sky-500 text-white flex items-center justify-center shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] shrink-0">
                <User className="h-5 w-5" />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-2xl font-black text-black dark:text-white uppercase tracking-tight">
                  {isAr ? "معلومات الحساب وتليجرام" : "Account & Telegram"}
                </h2>
                {accountCollapsed && (
                  <span className="border-2 border-black dark:border-white bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 px-2 py-0.5 text-[10px] font-black uppercase tracking-wider shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                    {isAr ? "مطوي" : "Collapsed"}
                  </span>
                )}
              </div>
            </div>
            {!accountCollapsed ? (
              <p className="text-xs text-zinc-600 dark:text-zinc-400 font-black uppercase tracking-widest leading-relaxed">
                {isAr
                  ? "بيانات الدخول، رقم الواتساب، والربط مع قناة وتنبيهات تليجرام"
                  : "Login information, mobile number, and Telegram channel integration"}
              </p>
            ) : (
              <div className="flex flex-wrap items-center gap-2 text-xs font-bold mt-1 text-zinc-600 dark:text-zinc-400">
                <span className="font-mono text-black dark:text-white font-black">{user.email}</span>
                <span className="text-zinc-300 dark:text-zinc-600">•</span>
                <span className={telegramLinked ? "text-emerald-600 dark:text-emerald-400 font-black" : "text-zinc-500 font-bold"}>
                  {telegramLinked ? (isAr ? "بوت التليجرام متصل" : "Telegram Bot Linked") : (isAr ? "التليجرام غير متصل" : "Telegram Not Linked")}
                </span>
                {whatsappNumber && (
                  <>
                    <span className="text-zinc-300 dark:text-zinc-600">•</span>
                    <span className="font-mono font-bold">{whatsappNumber}</span>
                  </>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={toggleAccountCollapsed}
              className="h-10 px-3 flex items-center justify-center gap-1.5 border-4 border-black dark:border-white bg-[#FFE600] text-black font-black text-xs uppercase tracking-wider shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all cursor-pointer"
              title={accountCollapsed ? (isAr ? "فتح السيكشن" : "Expand Section") : (isAr ? "طي السيكشن" : "Collapse Section")}
            >
              {accountCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
              <span>{accountCollapsed ? (isAr ? "عرض الحساب" : "Expand") : (isAr ? "طي السيكشن" : "Collapse")}</span>
            </button>
          </div>
        </div>

        {!accountCollapsed && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-1">
            {/* Account info */}
            <div className="neobrutal-card p-6 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] space-y-4">
              <div className="flex items-center gap-3 mb-2">
                <div className="h-10 w-10 border-4 border-black dark:border-white bg-zinc-700 text-white flex items-center justify-center shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)]">
                  <User className="h-5 w-5" />
                </div>
                <h3 className="text-lg font-black text-black dark:text-white uppercase tracking-tight">
                  {isAr ? "معلومات الحساب" : "Account Details"}
                </h3>
              </div>
              <div className="space-y-4 text-sm font-bold text-zinc-700 dark:text-zinc-300">
                {username && (
                  <div>
                    <span className="text-zinc-500 uppercase text-[10px] tracking-wider block">{isAr ? "اسم المستخدم" : "Name"}</span>
                    <span className="text-black dark:text-white font-black">{username}</span>
                  </div>
                )}
                <div>
                  <span className="text-zinc-500 uppercase text-[10px] tracking-wider block">{isAr ? "البريد الإلكتروني" : "Email"}</span>
                  <span className="text-black dark:text-white font-black break-all">{user.email}</span>
                </div>
                <div>
                  <span className="text-zinc-500 uppercase text-[10px] tracking-wider block">{isAr ? "حالة الحساب" : "Status"}</span>
                  <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-black">
                    <CheckCircle2 className="w-4 h-4" />
                    {isAr ? "نشط" : "Active"}
                  </span>
                </div>
                <div>
                  <span className="text-zinc-500 uppercase text-[10px] tracking-wider block">{isAr ? "بوت التليجرام في الخاص" : "Private Telegram Bot"}</span>
                  {proInvite.bot_active ? (
                    <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-black">
                      <CheckCircle2 className="w-4 h-4" />
                      {isAr ? "مفعل وشغال في الخاص ✅" : "Active & Linked (DM) ✅"}
                    </span>
                  ) : (telegramLinked || proInvite.telegram_chat_id) ? (
                    <span className="flex items-center gap-1.5 text-amber-600 dark:text-yellow-400 font-black">
                      <Bot className="w-4 h-4" />
                      {isAr ? "مسجل بالقناة لكن غير مفعل بالخاص ⚠️" : "In Channel / DM Not Active ⚠️"}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-rose-600 dark:text-rose-400 font-black">
                      <X className="w-4 h-4" />
                      {isAr ? "غير مفعل ❌" : "Not Linked ❌"}
                    </span>
                  )}
                </div>
                <div>
                  <span className="text-zinc-500 uppercase text-[10px] tracking-wider block">
                    {isAr ? "رقم الواتساب / الموبايل" : "WhatsApp / Mobile"}
                  </span>
                  {isEditingPhone ? (
                    <div className="flex flex-col gap-2 mt-1.5">
                      <div className="flex items-center gap-2">
                        <input
                          type="tel"
                          value={phoneDraft}
                          onChange={(e) => setPhoneDraft(e.target.value)}
                          placeholder="01012345678"
                          className="w-full px-2.5 py-1.5 border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800 text-xs font-mono font-bold text-black dark:text-white outline-none"
                          dir="ltr"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={handleSavePhone}
                          disabled={savingPhone}
                          className="px-3 py-1 bg-emerald-500 text-black border-2 border-black font-black text-xs hover:bg-emerald-400 transition-colors disabled:opacity-50"
                        >
                          {savingPhone ? (isAr ? "جاري الحفظ..." : "Saving...") : (isAr ? "حفظ" : "Save")}
                        </button>
                        <button
                          type="button"
                          onClick={() => setIsEditingPhone(false)}
                          disabled={savingPhone}
                          className="px-2.5 py-1 bg-zinc-200 dark:bg-zinc-700 text-black dark:text-white border-2 border-black text-xs font-bold"
                        >
                          {isAr ? "إلغاء" : "Cancel"}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-black dark:text-white font-mono font-bold text-xs" dir="ltr">
                        {whatsappNumber || (isAr ? "غير مسجل" : "Not set")}
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          setPhoneDraft(whatsappNumber || "");
                          setIsEditingPhone(true);
                        }}
                        className="text-xs font-bold text-indigo-600 dark:text-indigo-400 underline hover:text-indigo-500"
                      >
                        {whatsappNumber ? (isAr ? "تعديل" : "Edit") : (isAr ? "إضافة رقم" : "Add number")}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Telegram channel subscribe (simple) */}
            <div className="neobrutal-card p-6 sm:p-8 space-y-5 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] md:col-span-2">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 border-4 border-black dark:border-white bg-sky-500 text-white flex items-center justify-center shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)]">
                  <Send className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-lg font-black text-black dark:text-white uppercase tracking-tight">
                    {isAr ? "قناة التليجرام" : "Telegram Channel"}
                  </h3>
                  {telegramLinked && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-black text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 className="w-3 h-3" />
                      {isAr ? "بوت التليجرام متصل بحسابك" : "Bot linked to your account"}
                    </span>
                  )}
                </div>
              </div>

              <p className="text-sm font-bold text-zinc-700 dark:text-zinc-300 leading-relaxed">
                 {inviteLoading
                   ? (isAr ? "جاري التحقق من رابط قناة التليجرام..." : "Checking your Telegram channel invite...")
                   : inviteError
                     ? (isAr ? "تعذر تجهيز دعوة VIP حالياً. أعد المحاولة، وإذا استمرت المشكلة تواصل مع الدعم من الموقع." : "We couldn't prepare the VIP invite. Retry, or contact support if the problem continues.")
                     : proInvite.is_pro
                       ? (isAr ? "أنت مشترك Pro. استخدم رابط الدعوة الخاص بك للوصول إلى قناة Pro." : "You are a Pro member. Use your private invite to join the Pro Telegram channel.")
                       : (isAr ? "القناة المجانية تعرض الإشارات الفنية السابقة والتحليلات بتأخير 15 يوماً. التحديث الفوري متاح في Pro." : "The free channel shows past technical signals and updates with a 15-day delay. Live updates are available in Pro.")}
              </p>

               {proInvite.is_pro && proInvite.invite_link && (
                 <div className="border-4 border-indigo-600 bg-indigo-50 dark:bg-indigo-950/30 p-4 space-y-2" dir={isAr ? "rtl" : "ltr"}>
                   <p className="text-sm font-black text-indigo-700 dark:text-indigo-300">{isAr ? "رابط قناة VIP الخاص بك" : "Your VIP channel invite"}</p>
                   <a href={proInvite.invite_link} target="_blank" rel="noopener noreferrer" className="block break-all text-xs font-mono font-bold text-indigo-700 dark:text-indigo-300 underline">{proInvite.invite_link}</a>
                   <p className="text-[11px] font-bold text-zinc-600 dark:text-zinc-400">{isAr ? `الرابط صالح حتى ${proInvite.invite_expires_at ? new Date(proInvite.invite_expires_at).toLocaleDateString("ar-EG") : "نهاية اشتراكك"}.` : `Valid until ${proInvite.invite_expires_at ? new Date(proInvite.invite_expires_at).toLocaleDateString() : "your subscription ends"}.`}</p>
                 </div>
               )}
               {(inviteError || inviteLoading) && (
                 <div className="flex items-center gap-3 text-xs font-bold text-amber-700 dark:text-amber-300">
                   <span>{inviteLoading ? (isAr ? "جاري تجهيز دعوة VIP..." : "Preparing your VIP invite...") : (isAr ? "تعذر تحميل دعوة VIP. لن يظهر رابط القناة المجانية كبديل لاشتراكك." : "VIP invite unavailable. The free channel is not a substitute for your subscription.")}</span>
                   {!inviteLoading && <button type="button" onClick={() => void refreshProInvite()} className="underline" aria-label={isAr ? "إعادة محاولة دعوة VIP" : "Retry VIP invite"}>{isAr ? "إعادة المحاولة" : "Retry"}</button>}
                 </div>
               )}
               <div className="flex flex-col sm:flex-row gap-3 pt-1">
                {(proInviteUrl || (!proInvite.is_pro && !inviteError && !inviteLoading)) && <>
                <a
                  href={proInviteUrl || freeTelegramUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-12 flex-1 items-center justify-center gap-2 border-4 border-black dark:border-white bg-amber-300 dark:bg-amber-400 text-black font-black text-xs uppercase tracking-[0.1em] shadow-[3px_3px_0px_rgba(0,0,0,1)] hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[4px_4px_0px_rgba(0,0,0,1)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-all"
                >
                  <Send className="w-4 h-4 shrink-0" />
                  {proInviteUrl ? (isAr ? "دخول قناة Pro" : "Join Pro Telegram") : (isAr ? "القناة المجانية" : "Free Channel")}
                </a>
                <a
                  href={botAppUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-12 flex-1 items-center justify-center gap-2 border-4 border-black dark:border-white bg-emerald-400 dark:bg-emerald-500 text-black font-black text-xs uppercase tracking-[0.1em] shadow-[3px_3px_0px_rgba(0,0,0,1)] hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[4px_4px_0px_rgba(0,0,0,1)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-all"
                >
                  <Smartphone className="w-4 h-4 shrink-0" />
                  {proInvite.bot_active
                    ? (isAr ? "فتح البوت (App)" : "Open Bot (App)")
                    : (isAr ? "تفعيل البوت (App)" : "Activate Bot (App)")}
                </a>
                <a
                  href={botWebUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-12 flex-1 items-center justify-center gap-2 border-4 border-black dark:border-white bg-teal-300 dark:bg-teal-400 text-black font-black text-xs uppercase tracking-[0.1em] shadow-[3px_3px_0px_rgba(0,0,0,1)] hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[4px_4px_0px_rgba(0,0,0,1)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-all"
                >
                  <Globe className="w-4 h-4 shrink-0" />
                  {proInvite.bot_active
                    ? (isAr ? "فتح البوت (Web)" : "Open Bot (Web)")
                    : (isAr ? "تفعيل البوت (Web)" : "Activate Bot (Web)")}
                </a>
                <a
                  href={telegramWebUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-12 flex-1 items-center justify-center gap-2 border-4 border-black dark:border-white bg-white dark:bg-zinc-800 text-black dark:text-white font-black text-xs uppercase tracking-[0.1em] shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all"
                >
                  <Globe className="w-4 h-4 shrink-0" />
                  {proInviteUrl ? (isAr ? "فتح دعوة Pro" : "Open Pro Invite") : (isAr ? "افتح القناة المجانية" : "Open Free Channel")}
                </a>
                </>}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* ── Watchlist ── */}
      <section className={`relative z-10 min-w-0 rounded-2xl p-4 sm:p-6 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_rgba(255,255,255,1)] transition-all duration-200 ${watchlistCollapsed ? "space-y-0" : "space-y-6"}`}>
        <div className={`flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between ${watchlistCollapsed ? "" : "border-b-4 border-black dark:border-zinc-800 pb-5"}`}>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 border-4 border-black dark:border-white bg-indigo-500 text-white flex items-center justify-center shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] shrink-0">
                <Star className="h-5 w-5 fill-white" />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-2xl font-black text-black dark:text-white uppercase tracking-tight">
                  {isAr ? "قائمة المراقبة" : "Watchlist"}
                </h2>
                {watchlistCollapsed && (
                  <span className="border-2 border-black dark:border-white bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 px-2 py-0.5 text-[10px] font-black uppercase tracking-wider shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                    {isAr ? "مطوية" : "Collapsed"}
                  </span>
                )}
              </div>
            </div>
            {!watchlistCollapsed ? (
              <p className="text-xs text-zinc-600 dark:text-zinc-400 font-black uppercase tracking-widest leading-relaxed">
                {isAr ? "أسهمك المحفوظة — افتح الشارت أو عدّل أو احذف من هنا" : "Your saved symbols — open chart, edit or remove from here"}
              </p>
            ) : (
              <div className="flex flex-wrap items-center gap-2 text-xs font-bold mt-1 text-zinc-600 dark:text-zinc-400">
                <span className="font-mono text-black dark:text-white font-black">
                  {watchlist.length} {isAr ? "أسهم في قائمتك" : "symbols in watchlist"}
                </span>
                {watchlist.slice(0, 5).map((w) => (
                  <span key={w.id} className="px-1.5 py-0.5 bg-zinc-100 dark:bg-zinc-800 border border-black dark:border-white font-mono text-[11px] font-black">
                    {w.symbol}
                  </span>
                ))}
                {watchlist.length > 5 && (
                  <span className="text-[11px] text-zinc-500 font-mono">+{watchlist.length - 5}</span>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <div className="inline-flex items-center justify-center gap-2 h-10 px-3 border-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-950 text-black dark:text-white font-black text-xs uppercase tracking-widest shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,1)]">
              {watchlist.length} {isAr ? "سهم" : "Symbols"}
            </div>
            <button
              type="button"
              onClick={toggleWatchlistCollapsed}
              className="h-10 px-3 flex items-center justify-center gap-1.5 border-4 border-black dark:border-white bg-[#FFE600] text-black font-black text-xs uppercase tracking-wider shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all cursor-pointer"
              title={watchlistCollapsed ? (isAr ? "فتح السيكشن" : "Expand Section") : (isAr ? "طي السيكشن" : "Collapse Section")}
            >
              {watchlistCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
              <span>{watchlistCollapsed ? (isAr ? "عرض القائمة" : "Expand") : (isAr ? "طي السيكشن" : "Collapse")}</span>
            </button>
          </div>
        </div>

        {!watchlistCollapsed && (
          <div>
            {watchlist.length === 0 ? (
              <div className="min-h-[180px] border-4 border-dashed border-black/40 dark:border-white/30 bg-zinc-50 dark:bg-zinc-950/30 flex flex-col items-center justify-center gap-4 text-center p-8">
                <Star className="h-8 w-8 text-zinc-400" />
                <p className="max-w-md text-sm font-bold text-zinc-600 dark:text-zinc-400">
                  {isAr ? "لا توجد أسهم محفوظة حتى الآن. افتح صفحة الشارت واضغط النجمة لإضافة سهم لقائمتك." : "No saved symbols yet. Open the chart page and press the star to add a symbol."}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
                {watchlist.map((item) => {
                  const isEditing = editingSymbolId === item.id;
                  const exchange = item.metadata?.exchange || "EGX";

                  return (
                    <article key={item.id} className="border-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-950/35 p-4 sm:p-5 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xl font-black text-black dark:text-white uppercase tracking-tight">{item.symbol}</span>
                            <span className="border-2 border-black dark:border-white bg-indigo-100 dark:bg-indigo-500/20 px-2 py-0.5 text-[10px] font-black text-indigo-700 dark:text-indigo-300 uppercase tracking-widest">{exchange}</span>
                          </div>

                          {isEditing ? (
                            <input
                              value={watchlistDraft.name}
                              onChange={(e) => setWatchlistDraft((prev) => ({ ...prev, name: e.target.value }))}
                              className="mt-3 h-10 w-full border-4 border-black dark:border-white bg-white dark:bg-zinc-900 px-3 text-sm font-black text-black dark:text-white outline-none shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,1)]"
                            />
                          ) : (
                            <p className="mt-1 truncate text-sm font-bold text-zinc-700 dark:text-zinc-300">{item.name || item.symbol}</p>
                          )}
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          {isEditing ? (
                            <>
                              <button
                                onClick={() => saveWatchlistItem(item)}
                                className="h-9 w-9 border-4 border-black dark:border-white bg-emerald-400 text-black flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none cursor-pointer"
                                title={isAr ? "حفظ" : "Save"}
                              >
                                <Check className="h-4 w-4" />
                              </button>
                              <button
                                onClick={() => setEditingSymbolId(null)}
                                className="h-9 w-9 border-4 border-black dark:border-white bg-white dark:bg-zinc-800 text-black dark:text-white flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none cursor-pointer"
                                title={isAr ? "إلغاء" : "Cancel"}
                              >
                                <X className="h-4 w-4" />
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                onClick={() => router.push(`/chart?symbol=${encodeURIComponent(item.symbol)}&exchange=${encodeURIComponent(exchange)}`)}
                                className="h-9 w-9 border-4 border-black dark:border-white bg-white dark:bg-zinc-800 text-black dark:text-white flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none cursor-pointer"
                                title={isAr ? "فتح الشارت" : "Open chart"}
                              >
                                <ExternalLink className="h-4 w-4" />
                              </button>
                              <button
                                onClick={() => beginEditWatchlistItem(item)}
                                className="h-9 w-9 border-4 border-black dark:border-white bg-amber-300 text-black flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none cursor-pointer"
                                title={isAr ? "تعديل" : "Edit"}
                              >
                                <Edit3 className="h-4 w-4" />
                              </button>
                              <button
                                onClick={() => removeSymbol(item.id)}
                                className="h-9 w-9 border-4 border-black dark:border-white bg-red-400 text-black flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none cursor-pointer"
                                title={isAr ? "حذف" : "Delete"}
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
