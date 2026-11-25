"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { useMarket } from "@/contexts/MarketContext";
import { useWatchlist, type SavedSymbol } from "@/contexts/WatchlistContext";
import { useTelegramPro } from "@/contexts/TelegramProContext";
import { usePortfolio } from "@/contexts/PortfolioContext";
import { fetchUserQuotaCached, invalidateUserQuotaCache } from "@/lib/user-quota-client";
import {
  Loader2,
  Send,
  Globe,
  Star,
  Trash2,
  Edit3,
  X,
  Check,
  ExternalLink,
  User,
  CheckCircle2,
  Smartphone,
  Bot,
  Copy,
  Briefcase,
  Clock,
  Settings,
  Search,
  Crown,
  Zap,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Gift,
} from "lucide-react";
import { toast } from "sonner";
import MyPortfolioSection from "./components/MyPortfolioSection";
import PlanQuotaCard from "./components/PlanQuotaCard";
import ScheduledAutomationsCard from "./components/ScheduledAutomationsCard";
import FoundingMemberBanner from "./components/FoundingMemberBanner";
import PaymentWelcomeModal from "./components/PaymentWelcomeModal";

type ProfileTab = "portfolio" | "automations" | "watchlist" | "account";

const money = (v: number | null | undefined, digits = 0) => {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
};

export default function ProfilePage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const { language } = useLanguage();
  const { isSaudi, isGccChatOnly, currencyLabel } = useMarket();
  const { watchlist, updateSymbol, removeSymbol } = useWatchlist();
  const { invite: proInvite, loading: inviteLoading, error: inviteError, refresh: refreshProInvite } = useTelegramPro();
  const { snapshot: portfolioSnapshot } = usePortfolio();
  const isAr = language === "ar";
  const supabase = useMemo(() => createSupabaseBrowserClient(), []);
  const userId = user?.id ?? null;
  const lastProfileRefreshAtRef = useRef(0);
  const pendingTelegramLinkRef = useRef(false);

  const [activeTab, setActiveTab] = useState<ProfileTab>("portfolio");
  const [username, setUsername] = useState<string | null>(null);
  const [telegramLinked, setTelegramLinked] = useState(false);
  const [whatsappNumber, setWhatsappNumber] = useState<string | null>(null);
  const [isEditingPhone, setIsEditingPhone] = useState(false);
  const [phoneDraft, setPhoneDraft] = useState("");
  const [savingPhone, setSavingPhone] = useState(false);
  const [quotaData, setQuotaData] = useState<any>(null);
  const [automationsCount, setAutomationsCount] = useState<number | null>(null);
  const [showWelcomeModal, setShowWelcomeModal] = useState(false);
  const [welcomeOrderId, setWelcomeOrderId] = useState<string | null>(null);

  const [editingSymbolId, setEditingSymbolId] = useState<string | null>(null);
  const [watchlistDraft, setWatchlistDraft] = useState({ name: "" });
  const [watchlistQuery, setWatchlistQuery] = useState("");
  const [portfolioVersion, setPortfolioVersion] = useState(0);

  // Payment redirect modal handling
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const payment = params.get("payment");
    const customerReference = params.get("customerReference") || params.get("order_id");

    if (payment === "easykash" || payment === "success" || customerReference) {
      setWelcomeOrderId(customerReference || null);
      setShowWelcomeModal(true);
    }
  }, []);

  const handleCloseWelcomeModal = () => {
    setShowWelcomeModal(false);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.delete("payment");
      url.searchParams.delete("customerReference");
      url.searchParams.delete("order_id");
      window.history.replaceState({}, "", url.pathname + (url.search ? url.search : ""));
    }
  };

  // Strict 3-tier capability isolation (fail closed until quotaData resolves)
  const isPro = Boolean(quotaData?.plan?.is_pro);
  const hasChatPro = Boolean(
    quotaData?.plan &&
      (quotaData.plan.has_chat_pro ?? (quotaData.plan.is_pro && quotaData.plan.id !== "vip_only"))
  );
  const hasVipAccess = Boolean(
    quotaData?.plan &&
      (quotaData.plan.has_vip_access ?? (quotaData.plan.is_pro && quotaData.plan.id !== "chat_only"))
  );
  const canSeeVipLinks = hasVipAccess && proInvite.is_pro;

  const proInviteUrl = canSeeVipLinks && proInvite.invite_link ? proInvite.invite_link : "";
  const saudiProInviteUrl = canSeeVipLinks
    ? proInvite.saudi_invite_link || "https://web.telegram.org/a/#-1004397045436"
    : "";
  const saudiTelegramWebUrl = "https://web.telegram.org/a/#-1004397045436";
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
  const botWebUrl = `https://web.telegram.org/k/#?tgaddr=${encodeURIComponent(
    `tg://resolve?domain=egxbots_bot&start=${userId || "alerts"}`
  )}`;

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, router, user]);

  // Pre-load deduplicated quota so summary KPI strip works immediately on any active tab
  useEffect(() => {
    if (!userId) return;
    let active = true;
    const loadQuota = (force = false) => {
      void fetchUserQuotaCached(userId, { force })
        .then((json) => {
          if (active && json?.ok) {
            setQuotaData(json);
          }
        })
        .catch(() => {});
    };
    loadQuota(portfolioVersion > 0);
    const onQuotaUpdate = () => loadQuota(true);
    window.addEventListener("egx:entitlements-updated", onQuotaUpdate);
    window.addEventListener("egx:chat-quota-updated", onQuotaUpdate);
    return () => {
      active = false;
      window.removeEventListener("egx:entitlements-updated", onQuotaUpdate);
      window.removeEventListener("egx:chat-quota-updated", onQuotaUpdate);
    };
  }, [userId, portfolioVersion]);

  // Seed automations count lazily from sessionStorage (zero extra API calls when viewing Portfolio tab)
  useEffect(() => {
    if (!userId || typeof window === "undefined") return;
    try {
      const raw = window.sessionStorage.getItem(`egxbots_automations_v1:${userId}`);
      if (raw) {
        const parsed = JSON.parse(raw) as { automations?: unknown[] };
        if (Array.isArray(parsed?.automations)) {
          setAutomationsCount(parsed.automations.length);
        }
      }
    } catch {
      // ignore storage errors
    }
  }, [userId]);

  const reloadProfile = useCallback(async () => {
    if (!userId) return;
    lastProfileRefreshAtRef.current = Date.now();
    const { data: profileRow } = await supabase
      .from("profiles")
      .select("username, display_name, telegram_chat_id, whatsapp_number")
      .eq("id", userId)
      .maybeSingle();
    if (profileRow) {
      const linked = Boolean((profileRow as any).telegram_chat_id);
      if (linked) pendingTelegramLinkRef.current = false;
      setUsername((profileRow as any).username || (profileRow as any).display_name || null);
      setTelegramLinked(linked);
      setWhatsappNumber((profileRow as any).whatsapp_number || null);
    }
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
      const cooldownMs = pendingTelegramLinkRef.current ? 3_000 : 10 * 60_000;
      if (Date.now() - lastProfileRefreshAtRef.current < cooldownMs) return;
      if (pendingTelegramLinkRef.current) {
        invalidateUserQuotaCache(userId);
        void refreshProInvite();
      }
      void reloadProfile();
    };
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => document.removeEventListener("visibilitychange", refreshWhenVisible);
  }, [reloadProfile, refreshProInvite, userId]);

  // Deep-link hash routing across workspace tabs (#portfolio, #automations, #watchlist, #telegram, #account, #plan)
  useEffect(() => {
    const syncTabFromHash = () => {
      if (typeof window === "undefined") return;
      const hash = window.location.hash.toLowerCase();
      if (hash === "#telegram" || hash === "#telegram-pro" || hash === "#account" || hash === "#plan") {
        setActiveTab("account");
        if (hash === "#telegram" || hash === "#telegram-pro") {
          setTimeout(() => {
            document.getElementById("telegram")?.scrollIntoView({ behavior: "smooth", block: "start" });
          }, 120);
        }
      } else if (hash === "#automations") {
        setActiveTab("automations");
      } else if (hash === "#watchlist") {
        setActiveTab("watchlist");
      } else if (hash === "#portfolio" || hash === "#my-portfolio") {
        setActiveTab("portfolio");
        setTimeout(() => {
          document.getElementById("portfolio")?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 160);
      }
    };
    syncTabFromHash();
    window.addEventListener("hashchange", syncTabFromHash);
    return () => window.removeEventListener("hashchange", syncTabFromHash);
  }, []);

  const openTelegramHub = () => {
    setActiveTab("account");
    setTimeout(() => {
      document.getElementById("telegram")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
  };

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

  const filteredWatchlist = useMemo(() => {
    const q = watchlistQuery.trim().toUpperCase();
    if (!q) return watchlist;
    return watchlist.filter(
      (item) =>
        item.symbol.toUpperCase().includes(q) ||
        (item.name || "").toUpperCase().includes(q)
    );
  }, [watchlist, watchlistQuery]);

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  if (!user) return null;

  const metaName =
    (user.user_metadata as Record<string, unknown> | undefined)?.full_name ||
    (user.user_metadata as Record<string, unknown> | undefined)?.name;
  const displayName = username || (typeof metaName === "string" && metaName.trim() ? metaName : null) || user.email?.split("@")[0] || "Trader";
  const initials = displayName.slice(0, 2).toUpperCase();

  const planBadgeLabel = quotaData?.plan?.is_lifetime
    ? "LIFETIME VIP 👑"
    : quotaData?.plan?.is_trial
    ? isAr
      ? "تجربة PRO ⚡"
      : "PRO TRIAL ⚡"
    : quotaData?.plan?.id === "chat_only"
    ? "AI CHAT PRO"
    : quotaData?.plan?.id === "vip_only"
    ? "VIP RADAR"
    : isPro
    ? "PRO"
    : isAr
    ? "مجاني"
    : "FREE";

  const chatQuota = quotaData?.quota?.chat_messages;
  const portfolioPositionsCount = portfolioSnapshot?.positions?.length ?? quotaData?.quota?.portfolio_stocks?.used ?? 0;
  const portfolioEquity = portfolioSnapshot?.totals?.equity ?? null;
  const portfolioProfitPct = portfolioSnapshot?.totals?.profit_pct ?? null;

  const tabs: Array<{
    id: ProfileTab;
    label: string;
    icon: typeof Briefcase;
    badge?: string | number | null;
    alert?: boolean;
  }> = [
    {
      id: "portfolio",
      label: isAr ? "محفظتي" : "Portfolio",
      icon: Briefcase,
      badge: portfolioPositionsCount > 0 ? portfolioPositionsCount : null,
    },
    {
      id: "automations",
      label: isAr ? "الأتمتة اليومية" : "Automations",
      icon: Clock,
      badge: automationsCount !== null ? `${automationsCount}/5` : null,
    },
    {
      id: "watchlist",
      label: isAr ? "قائمة المراقبة" : "Watchlist",
      icon: Star,
      badge: watchlist.length > 0 ? watchlist.length : null,
    },
    {
      id: "account",
      label: isAr ? "الحساب والباقة وتليجرام" : "Account & Telegram",
      icon: Settings,
      badge: !proInvite.bot_active && !isGccChatOnly ? "!" : null,
      alert: !proInvite.bot_active && !isGccChatOnly,
    },
  ];

  return (
    <div
      dir={isAr ? "rtl" : "ltr"}
      className="profile-page-shell neobrutal-layout flex flex-col gap-4 sm:gap-5 pb-20 max-w-[1600px] mx-auto mt-2 px-2 sm:px-4 neobrutal-grid-bg min-h-screen"
    >
      {/* ── Founding Member Announcement Banner ── */}
      {quotaData?.plan?.is_founding_member && (
        <div className="w-full relative z-20">
          <FoundingMemberBanner
            memberNumber={quotaData.plan.founding_member_number}
            language={language}
          />
        </div>
      )}

      {/* ── Compact Identity Command Header ── */}
      <header className="relative z-10 rounded-2xl border-2 sm:border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-4 sm:p-5 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="flex items-center gap-3.5 min-w-0">
            <div className="h-12 w-12 sm:h-14 sm:w-14 rounded-xl border-3 border-black dark:border-white bg-[#FFE600] text-black flex items-center justify-center font-black text-lg sm:text-xl shadow-[3px_3px_0px_rgba(0,0,0,1)] shrink-0">
              {initials}
            </div>
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl sm:text-2xl font-black tracking-tight text-black dark:text-white truncate">
                  {displayName}
                </h1>
                <span
                  className={`text-[11px] font-black uppercase px-2.5 py-0.5 border-2 border-black dark:border-white ${
                    quotaData?.plan?.is_lifetime
                      ? "bg-purple-600 text-yellow-300"
                      : isPro
                      ? "bg-emerald-500 text-white"
                      : "bg-zinc-200 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-100"
                  }`}
                >
                  {planBadgeLabel}
                </span>
                {quotaData?.plan?.is_founding_member && (
                  <span className="text-[10px] font-black px-2 py-0.5 border-2 border-black bg-[#FFE600] text-black">
                    ⭐ {isAr ? `مؤسس #${quotaData.plan.founding_member_number || ""}` : `FOUNDER #${quotaData.plan.founding_member_number || ""}`}
                  </span>
                )}
                {!isGccChatOnly && (
                  proInvite.bot_active ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-black px-2.5 py-0.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
                      🟢 {isAr ? "بوت تليجرام مفعل" : "Telegram Bot Active"}
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={openTelegramHub}
                      className="inline-flex items-center gap-1 text-[11px] font-black px-2.5 py-0.5 rounded-full border border-amber-500 bg-amber-100 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 hover:bg-amber-200 transition-colors cursor-pointer"
                    >
                      ⚠️ {isAr ? "فعّل البوت" : "Activate Bot"}
                    </button>
                  )
                )}
              </div>
              <p className="text-xs font-mono font-bold text-zinc-500 dark:text-zinc-400 truncate">
                {user.email}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <Link
              href="/affiliate"
              className="h-10 px-3.5 flex items-center gap-2 border-3 border-black dark:border-white bg-emerald-400 hover:bg-emerald-300 text-black font-black text-xs uppercase tracking-wider shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all cursor-pointer"
              prefetch={false}
            >
              <Gift className="w-3.5 h-3.5" />
              <span>{isAr ? "رابط الإحالة (25%)" : "Referral Link (25%)"}</span>
            </Link>
            {!isPro && (
              <Link
                href="/pricing"
                className="h-10 px-3.5 flex items-center gap-1.5 border-3 border-black dark:border-white bg-[#FFE600] hover:bg-amber-300 text-black font-black text-xs uppercase tracking-wider shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all cursor-pointer"
                prefetch={false}
              >
                <Crown className="w-3.5 h-3.5" />
                <span>{isAr ? "ترقية لـ Pro" : "Upgrade to Pro"}</span>
              </Link>
            )}
          </div>
        </div>
      </header>

      {/* ── Slim Actionable Bot Strip (ONLY when bot is NOT active & non-GCC chat-only) ── */}
      {!proInvite.bot_active && !isGccChatOnly && (
        <section className="relative z-10 w-full rounded-xl p-3 border-2 sm:border-3 border-black dark:border-white bg-[#FFE600] text-black shadow-[3px_3px_0px_rgba(0,0,0,1)]">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="h-9 w-9 border-2 border-black bg-black text-[#FFE600] flex items-center justify-center shrink-0">
                <Bot className="h-5 w-5" />
              </div>
              <p className="text-xs sm:text-sm font-black leading-snug">
                {telegramLinked || proInvite.telegram_chat_id
                  ? isAr
                    ? "⚠️ خطوة أخيرة: افتح البوت واضغط Start في الخاص لتصلك الإشارات والتنبيهات."
                    : "⚠️ Final step: Open the bot and press Start in DM to receive live alerts."
                  : isAr
                  ? "🔔 فعّل بوت التليجرام في الخاص لاستقبال إشارات الإسكانر وتنبيهات الأسهم مجاناً."
                  : "🔔 Activate your Telegram bot in private DM to receive scanner & target alerts."}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2 shrink-0">
              <a
                href={botAppUrl}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => {
                  pendingTelegramLinkRef.current = true;
                }}
                className="inline-flex h-9 px-3 items-center justify-center gap-1.5 border-2 border-black bg-black text-[#FFE600] font-black text-xs cursor-pointer"
              >
                <Smartphone className="w-3.5 h-3.5" />
                <span>App</span>
              </a>
              <a
                href={botWebUrl}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => {
                  pendingTelegramLinkRef.current = true;
                }}
                className="inline-flex h-9 px-3 items-center justify-center gap-1.5 border-2 border-black bg-white text-black font-black text-xs cursor-pointer"
              >
                <Globe className="w-3.5 h-3.5" />
                <span>Web</span>
              </a>
              {userId && (
                <button
                  type="button"
                  onClick={() => {
                    pendingTelegramLinkRef.current = true;
                    const cmd = `/start ${userId}`;
                    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
                      void navigator.clipboard.writeText(cmd);
                    }
                    toast.success(
                      isAr
                        ? "تم نسخ كود الربط! الصقه داخل محادثة @egxbots_bot"
                        : "Link command copied! Send it to @egxbots_bot"
                    );
                  }}
                  className="inline-flex h-9 px-3 items-center justify-center gap-1.5 border-2 border-black bg-emerald-300 text-black font-black text-xs cursor-pointer"
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span>{isAr ? "نسخ الكود" : "Copy Code"}</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  if (userId) invalidateUserQuotaCache(userId);
                  void refreshProInvite();
                  void reloadProfile();
                  toast.info(isAr ? "جاري التحقق..." : "Checking...");
                }}
                className="inline-flex h-9 px-3 items-center justify-center gap-1.5 border-2 border-black bg-zinc-200 text-black font-black text-xs cursor-pointer"
              >
                <Check className="w-3.5 h-3.5" />
                <span>{isAr ? "تحقق" : "Verify"}</span>
              </button>
            </div>
          </div>
        </section>
      )}

      {/* ── Compact 4-Card Live Summary Strip ── */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3 relative z-10">
        {/* Card 1: Portfolio */}
        <button
          type="button"
          onClick={() => setActiveTab("portfolio")}
          className={`text-start rounded-xl border-2 p-3.5 bg-white dark:bg-zinc-900 transition-all cursor-pointer ${
            activeTab === "portfolio"
              ? "border-emerald-500 shadow-[3px_3px_0px_rgba(16,185,129,0.35)]"
              : "border-zinc-200 dark:border-zinc-800 hover:border-black dark:hover:border-white"
          }`}
        >
          <div className="flex items-center justify-between gap-2 text-xs font-black text-zinc-500 dark:text-zinc-400">
            <span className="flex items-center gap-1.5">
              <Briefcase className="w-3.5 h-3.5 text-emerald-500" />
              {isAr ? "المحفظة" : "Portfolio"}
            </span>
            <span className="font-mono text-[11px]">
              {portfolioPositionsCount} {isAr ? "سهم" : "stocks"}
            </span>
          </div>
          <div className="mt-2 flex items-baseline justify-between gap-2">
            <span className="text-lg sm:text-xl font-black font-mono text-black dark:text-white" dir="ltr">
              {money(portfolioEquity)} <span className="text-[11px] font-bold text-zinc-500">{currencyLabel}</span>
            </span>
            {portfolioProfitPct !== null && (
              <span
                dir="ltr"
                className={`inline-flex items-center gap-0.5 text-xs font-black font-mono ${
                  portfolioProfitPct >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
                }`}
              >
                {portfolioProfitPct >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                {portfolioProfitPct >= 0 ? "+" : ""}
                {portfolioProfitPct.toFixed(1)}%
              </span>
            )}
          </div>
        </button>

        {/* Card 2: Plan & Quota */}
        <button
          type="button"
          onClick={() => setActiveTab("account")}
          className={`text-start rounded-xl border-2 p-3.5 bg-white dark:bg-zinc-900 transition-all cursor-pointer ${
            activeTab === "account"
              ? "border-indigo-500 shadow-[3px_3px_0px_rgba(99,102,241,0.35)]"
              : "border-zinc-200 dark:border-zinc-800 hover:border-black dark:hover:border-white"
          }`}
        >
          <div className="flex items-center justify-between gap-2 text-xs font-black text-zinc-500 dark:text-zinc-400">
            <span className="flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-indigo-500" />
              {isAr ? "الكوتا والباقة" : "Plan & Quota"}
            </span>
            <span className="text-[10px] font-black text-indigo-600 dark:text-indigo-400">{planBadgeLabel}</span>
          </div>
          <div className="mt-2 space-y-1.5">
            <div className="flex items-baseline justify-between">
              <span className="text-lg sm:text-xl font-black font-mono text-black dark:text-white" dir="ltr">
                {chatQuota ? `${chatQuota.used} / ${chatQuota.limit}` : "—"}
              </span>
              <span className="text-[11px] font-bold text-zinc-500">
                {chatQuota ? `${chatQuota.percent ?? 0}%` : isAr ? "جاري التحميل" : "Loading"}
              </span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
              <div
                className={`h-full transition-all ${
                  (chatQuota?.percent ?? 0) >= 90
                    ? "bg-rose-500"
                    : (chatQuota?.percent ?? 0) >= 70
                    ? "bg-amber-500"
                    : "bg-indigo-500"
                }`}
                style={{ width: `${Math.min(100, chatQuota?.percent ?? 0)}%` }}
              />
            </div>
          </div>
        </button>

        {/* Card 3: Daily Automations */}
        <button
          type="button"
          onClick={() => setActiveTab("automations")}
          className={`text-start rounded-xl border-2 p-3.5 bg-white dark:bg-zinc-900 transition-all cursor-pointer ${
            activeTab === "automations"
              ? "border-amber-500 shadow-[3px_3px_0px_rgba(245,158,11,0.35)]"
              : "border-zinc-200 dark:border-zinc-800 hover:border-black dark:hover:border-white"
          }`}
        >
          <div className="flex items-center justify-between gap-2 text-xs font-black text-zinc-500 dark:text-zinc-400">
            <span className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-amber-500" />
              {isAr ? "الأتمتة اليومية" : "Automations"}
            </span>
            <span className="text-[10px] font-black px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-700 dark:text-amber-300">
              {hasChatPro ? "ACTIVE" : "PRO"}
            </span>
          </div>
          <div className="mt-2 flex items-baseline justify-between gap-2">
            <span className="text-lg sm:text-xl font-black font-mono text-black dark:text-white" dir="ltr">
              {automationsCount !== null ? `${automationsCount} / 5` : "— / 5"}
            </span>
            <span className="text-[11px] font-bold text-zinc-500 truncate">
              {isAr ? "تقارير يومية" : "Daily AI runs"}
            </span>
          </div>
        </button>

        {/* Card 4: Watchlist */}
        <button
          type="button"
          onClick={() => setActiveTab("watchlist")}
          className={`text-start rounded-xl border-2 p-3.5 bg-white dark:bg-zinc-900 transition-all cursor-pointer ${
            activeTab === "watchlist"
              ? "border-sky-500 shadow-[3px_3px_0px_rgba(14,165,233,0.35)]"
              : "border-zinc-200 dark:border-zinc-800 hover:border-black dark:hover:border-white"
          }`}
        >
          <div className="flex items-center justify-between gap-2 text-xs font-black text-zinc-500 dark:text-zinc-400">
            <span className="flex items-center gap-1.5">
              <Star className="w-3.5 h-3.5 text-sky-500 fill-sky-500" />
              {isAr ? "قائمة المراقبة" : "Watchlist"}
            </span>
            <span className="text-[10px] font-bold text-sky-600 dark:text-sky-400">
              {isAr ? "سريع" : "Quick"}
            </span>
          </div>
          <div className="mt-2 flex items-baseline justify-between gap-2">
            <span className="text-lg sm:text-xl font-black font-mono text-black dark:text-white">
              {watchlist.length}{" "}
              <span className="text-xs font-bold text-zinc-500">{isAr ? "سهم" : "symbols"}</span>
            </span>
            <span className="text-[11px] font-bold text-zinc-500 truncate">
              {isAr ? "فتح الشارت بنقرة" : "1-click chart"}
            </span>
          </div>
        </button>
      </section>

      {/* ── Sticky Segmented Workspace Tab Bar ── */}
      <nav
        role="tablist"
        aria-label={isAr ? "أقسام الملف الشخصي" : "Profile workspace sections"}
        className="sticky top-[calc(var(--header-offset,88px)+8px)] z-20 flex items-center gap-2 overflow-x-auto rounded-2xl border-2 sm:border-3 border-black dark:border-white bg-white/95 dark:bg-zinc-900/95 backdrop-blur-md p-2 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)]"
      >
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-3.5 py-2.5 rounded-xl text-xs sm:text-sm font-black whitespace-nowrap transition-all cursor-pointer border-2 ${
                isActive
                  ? "border-black dark:border-white bg-[#FFE600] text-black shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                  : "border-transparent text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span>{tab.label}</span>
              {tab.badge !== null && tab.badge !== undefined && (
                <span
                  className={`px-1.5 py-0.5 rounded-full text-[10px] font-mono font-black ${
                    tab.alert
                      ? "bg-amber-500 text-black"
                      : isActive
                      ? "bg-black text-[#FFE600]"
                      : "bg-zinc-200 dark:bg-zinc-700 text-zinc-800 dark:text-zinc-100"
                  }`}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* ── Active Tab Workspace Panel ── */}
      <div role="tabpanel" className="min-w-0">
        {/* TAB 1: PORTFOLIO */}
        {activeTab === "portfolio" && (
          <div id="portfolio" className="scroll-mt-24">
            <MyPortfolioSection
              hideCollapseToggle
              onPortfolioUpdated={() => setPortfolioVersion((v) => v + 1)}
            />
          </div>
        )}

        {/* TAB 2: SCHEDULED AUTOMATIONS */}
        {activeTab === "automations" && (
          <ScheduledAutomationsCard
            isPro={hasChatPro}
            language={language}
            telegramLinked={telegramLinked || Boolean(proInvite.telegram_chat_id)}
            onQuotaConsumed={() => setPortfolioVersion((v) => v + 1)}
            onCountChange={setAutomationsCount}
          />
        )}

        {/* TAB 3: WATCHLIST */}
        {activeTab === "watchlist" && (
          <section className="relative z-10 min-w-0 rounded-2xl p-4 sm:p-6 bg-white dark:bg-zinc-900 border-2 sm:border-4 border-black dark:border-white shadow-[4px_4px_0px_rgba(0,0,0,1)] sm:shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] space-y-5">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b-2 sm:border-b-4 border-black dark:border-zinc-800 pb-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 border-3 border-black dark:border-white bg-indigo-500 text-white flex items-center justify-center shadow-[3px_3px_0px_rgba(0,0,0,1)] shrink-0">
                  <Star className="h-5 w-5 fill-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-xl sm:text-2xl font-black text-black dark:text-white uppercase tracking-tight">
                      {isAr ? "قائمة المراقبة" : "Watchlist"}
                    </h2>
                    <span className="px-2.5 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 text-xs font-black font-mono">
                      {watchlist.length}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-600 dark:text-zinc-400 font-bold mt-0.5">
                    {isAr
                      ? "أسهمك المحفوظة — افتح الشارت أو عدّل أو احذف من هنا"
                      : "Your saved symbols — open chart, edit or remove from here"}
                  </p>
                </div>
              </div>

              {watchlist.length > 4 && (
                <div className="relative w-full sm:w-64">
                  <Search className="w-4 h-4 text-zinc-400 absolute top-1/2 -translate-y-1/2 start-3 pointer-events-none" />
                  <input
                    type="text"
                    value={watchlistQuery}
                    onChange={(e) => setWatchlistQuery(e.target.value)}
                    placeholder={isAr ? "ابحث داخل قائمة المراقبة..." : "Search watchlist..."}
                    className="h-10 w-full ps-9 pe-3 rounded-xl border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-950 text-xs font-bold text-black dark:text-white outline-none"
                  />
                </div>
              )}
            </div>

            {watchlist.length === 0 ? (
              <div className="min-h-[180px] border-3 border-dashed border-black/30 dark:border-white/30 rounded-xl bg-zinc-50 dark:bg-zinc-950/30 flex flex-col items-center justify-center gap-4 text-center p-8">
                <Star className="h-8 w-8 text-zinc-400" />
                <p className="max-w-md text-sm font-bold text-zinc-600 dark:text-zinc-400">
                  {isAr
                    ? "لا توجد أسهم محفوظة حتى الآن. افتح صفحة الشارت واضغط النجمة لإضافة سهم لقائمتك."
                    : "No saved symbols yet. Open the chart page and press the star to add a symbol."}
                </p>
                <Link
                  href="/chart"
                  prefetch={false}
                  className="px-4 py-2 border-2 border-black dark:border-white bg-[#FFE600] text-black font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                >
                  {isAr ? "استكشاف الشارتات" : "Explore Charts"}
                </Link>
              </div>
            ) : filteredWatchlist.length === 0 ? (
              <div className="py-10 text-center text-sm font-bold text-zinc-500">
                {isAr ? "لا توجد أسهم مطابقة لبحثك." : "No matching symbols found."}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
                {filteredWatchlist.map((item) => {
                  const isEditing = editingSymbolId === item.id;
                  const exchange = item.metadata?.exchange || "EGX";

                  return (
                    <article
                      key={item.id}
                      className="rounded-xl border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-950/40 p-4 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] flex flex-col justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-lg font-black text-black dark:text-white uppercase tracking-tight">
                            {item.symbol}
                          </span>
                          <span className="border border-black dark:border-white bg-indigo-100 dark:bg-indigo-500/20 px-2 py-0.5 text-[10px] font-black text-indigo-700 dark:text-indigo-300 uppercase">
                            {exchange}
                          </span>
                        </div>
                        {isEditing ? (
                          <input
                            value={watchlistDraft.name}
                            onChange={(e) => setWatchlistDraft((prev) => ({ ...prev, name: e.target.value }))}
                            className="mt-2 h-9 w-full border-2 border-black dark:border-white bg-white dark:bg-zinc-900 px-2.5 text-xs font-black text-black dark:text-white outline-none"
                          />
                        ) : (
                          <p className="mt-1 truncate text-xs font-bold text-zinc-600 dark:text-zinc-300">
                            {item.name || item.symbol}
                          </p>
                        )}
                      </div>

                      <div className="flex items-center justify-between gap-2 pt-2 border-t border-zinc-200 dark:border-zinc-800">
                        {isEditing ? (
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => saveWatchlistItem(item)}
                              className="h-8 px-3 border-2 border-black dark:border-white bg-emerald-400 text-black font-black text-xs flex items-center gap-1 cursor-pointer"
                              title={isAr ? "حفظ" : "Save"}
                            >
                              <Check className="h-3.5 w-3.5" />
                              <span>{isAr ? "حفظ" : "Save"}</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingSymbolId(null)}
                              className="h-8 px-2.5 border-2 border-black dark:border-white bg-white dark:bg-zinc-800 text-black dark:text-white text-xs font-bold cursor-pointer"
                              title={isAr ? "إلغاء" : "Cancel"}
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() =>
                                router.push(`/chart?symbol=${encodeURIComponent(item.symbol)}&exchange=${encodeURIComponent(exchange)}`)
                              }
                              className="h-8 px-3 border-2 border-black dark:border-white bg-white dark:bg-zinc-800 text-black dark:text-white font-black text-xs flex items-center gap-1.5 hover:bg-[#FFE600] hover:text-black transition-colors cursor-pointer"
                              title={isAr ? "فتح الشارت" : "Open chart"}
                            >
                              <ExternalLink className="h-3.5 w-3.5" />
                              <span>{isAr ? "الشارت" : "Chart"}</span>
                            </button>
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => beginEditWatchlistItem(item)}
                                className="h-8 w-8 border-2 border-black dark:border-white bg-amber-300 text-black flex items-center justify-center cursor-pointer"
                                title={isAr ? "تعديل" : "Edit"}
                              >
                                <Edit3 className="h-3.5 w-3.5" />
                              </button>
                              <button
                                type="button"
                                onClick={() => removeSymbol(item.id)}
                                className="h-8 w-8 border-2 border-black dark:border-white bg-red-400 text-black flex items-center justify-center cursor-pointer"
                                title={isAr ? "حذف" : "Delete"}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        )}

        {/* TAB 4: ACCOUNT, PLAN QUOTA & TELEGRAM HUB */}
        {activeTab === "account" && (
          <div className="space-y-5">
            <PlanQuotaCard
              refreshTrigger={portfolioVersion}
              onQuotaLoaded={setQuotaData}
              hideCollapseToggle
            />

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
              {/* Left 5 cols: Account Info + WhatsApp + Affiliate Card */}
              <div className="lg:col-span-5 space-y-5">
                <section className="rounded-2xl p-5 bg-white dark:bg-zinc-900 border-2 sm:border-4 border-black dark:border-white shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] space-y-4">
                  <div className="flex items-center gap-3 border-b-2 border-zinc-200 dark:border-zinc-800 pb-3">
                    <div className="h-9 w-9 border-2 border-black dark:border-white bg-zinc-800 text-white flex items-center justify-center shrink-0">
                      <User className="h-4 w-4" />
                    </div>
                    <h3 className="text-base font-black text-black dark:text-white uppercase tracking-tight">
                      {isAr ? "بيانات الحساب" : "Account Details"}
                    </h3>
                  </div>

                  <div className="space-y-3.5 text-sm font-bold text-zinc-700 dark:text-zinc-300">
                    {username && (
                      <div>
                        <span className="text-zinc-500 uppercase text-[10px] tracking-wider block">
                          {isAr ? "اسم المستخدم" : "Name"}
                        </span>
                        <span className="text-black dark:text-white font-black">{username}</span>
                      </div>
                    )}
                    <div>
                      <span className="text-zinc-500 uppercase text-[10px] tracking-wider block">
                        {isAr ? "البريد الإلكتروني" : "Email"}
                      </span>
                      <span className="text-black dark:text-white font-black break-all">{user.email}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500 uppercase text-[10px] tracking-wider block">
                        {isAr ? "حالة الحساب" : "Status"}
                      </span>
                      <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-black">
                        <CheckCircle2 className="w-4 h-4" />
                        {isAr ? "نشط" : "Active"}
                      </span>
                    </div>
                    <div>
                      <span className="text-zinc-500 uppercase text-[10px] tracking-wider block">
                        {isAr ? "رقم الواتساب / الموبايل" : "WhatsApp / Mobile"}
                      </span>
                      {isEditingPhone ? (
                        <div className="flex flex-col gap-2 mt-1.5">
                          <input
                            type="tel"
                            value={phoneDraft}
                            onChange={(e) => setPhoneDraft(e.target.value)}
                            placeholder="01012345678"
                            className="w-full px-2.5 py-1.5 border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800 text-xs font-mono font-bold text-black dark:text-white outline-none"
                            dir="ltr"
                          />
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={handleSavePhone}
                              disabled={savingPhone}
                              className="px-3 py-1 bg-emerald-500 text-black border-2 border-black font-black text-xs hover:bg-emerald-400 transition-colors disabled:opacity-50"
                            >
                              {savingPhone ? (isAr ? "جاري الحفظ..." : "Saving...") : isAr ? "حفظ" : "Save"}
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
                            className="text-xs font-bold text-indigo-600 dark:text-indigo-400 underline hover:text-indigo-500 cursor-pointer"
                          >
                            {whatsappNumber ? (isAr ? "تعديل" : "Edit") : isAr ? "إضافة رقم" : "Add number"}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </section>

                {/* Referral Promo Card */}
                <section className="rounded-2xl p-5 bg-emerald-50 dark:bg-emerald-950/20 border-2 border-emerald-600 dark:border-emerald-500 space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-black text-sm text-emerald-900 dark:text-emerald-200 flex items-center gap-2">
                      <Gift className="w-4 h-4 text-emerald-600" />
                      {isAr ? "برنامج شركاء النجاح (عمولة 25%)" : "Affiliate Partner (25%)"}
                    </span>
                  </div>
                  <p className="text-xs font-bold text-emerald-800 dark:text-emerald-300 leading-relaxed">
                    {isAr
                      ? "شارك رابط الإحالة الخاص بك واحصل على عمولة 25% من اشتراك أي صديق يسجل عبرك."
                      : "Share your referral link and earn a 25% commission on every friend who subscribes."}
                  </p>
                  <Link
                    href="/affiliate"
                    prefetch={false}
                    className="inline-flex h-9 px-4 items-center gap-2 border-2 border-black bg-emerald-400 hover:bg-emerald-300 text-black font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                  >
                    <span>{isAr ? "لوحة الإحالة والأرباح" : "Open Affiliate Dashboard"}</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </Link>
                </section>
              </div>

              {/* Right 7 cols: Unified Telegram Hub (Bot DM + VIP/Free Channels) */}
              <section
                id="telegram"
                className="lg:col-span-7 scroll-mt-24 rounded-2xl p-5 sm:p-6 bg-white dark:bg-zinc-900 border-2 sm:border-4 border-black dark:border-white shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] space-y-5"
              >
                {/* Section A: Private Telegram Bot */}
                <div className="space-y-3 border-b-2 border-zinc-200 dark:border-zinc-800 pb-5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 border-2 border-black dark:border-white bg-sky-500 text-white flex items-center justify-center shrink-0">
                        <Bot className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="text-base sm:text-lg font-black text-black dark:text-white">
                          {isAr ? "بوت التليجرام الخاص (@egxbots_bot)" : "Private Telegram Bot (@egxbots_bot)"}
                        </h3>
                        <p className="text-xs font-bold text-zinc-500 dark:text-zinc-400">
                          {isAr ? "شات أرتورو AI + تنبيهات المحفظة والأسعار لحظياً" : "ARTORO AI Chat + live portfolio & price alerts"}
                        </p>
                      </div>
                    </div>

                    {proInvite.bot_active ? (
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/40 text-emerald-700 dark:text-emerald-300 text-xs font-black">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        {isAr ? "مفعل وشغال ✅" : "Active & Linked ✅"}
                      </span>
                    ) : telegramLinked || proInvite.telegram_chat_id ? (
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/15 border border-amber-500/40 text-amber-700 dark:text-amber-300 text-xs font-black">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {isAr ? "اضغط Start داخل الخاص" : "Press Start in DM"}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-500/15 border border-rose-500/40 text-rose-700 dark:text-rose-300 text-xs font-black">
                        {isAr ? "غير مفعل ❌" : "Not Linked ❌"}
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1">
                    <a
                      href={botAppUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={() => {
                        pendingTelegramLinkRef.current = true;
                      }}
                      className="inline-flex h-10 px-3 items-center justify-center gap-1.5 border-2 border-black dark:border-white bg-emerald-400 text-black font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer"
                    >
                      <Smartphone className="w-3.5 h-3.5 shrink-0" />
                      <span>{proInvite.bot_active ? (isAr ? "فتح (App)" : "Open (App)") : isAr ? "تفعيل (App)" : "Start (App)"}</span>
                    </a>
                    <a
                      href={botWebUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={() => {
                        pendingTelegramLinkRef.current = true;
                      }}
                      className="inline-flex h-10 px-3 items-center justify-center gap-1.5 border-2 border-black dark:border-white bg-teal-300 text-black font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer"
                    >
                      <Globe className="w-3.5 h-3.5 shrink-0" />
                      <span>{proInvite.bot_active ? (isAr ? "فتح (Web)" : "Open (Web)") : isAr ? "تفعيل (Web)" : "Start (Web)"}</span>
                    </a>
                    {!proInvite.bot_active && userId && (
                      <button
                        type="button"
                        onClick={() => {
                          pendingTelegramLinkRef.current = true;
                          const cmd = `/start ${userId}`;
                          if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
                            void navigator.clipboard.writeText(cmd);
                          }
                          toast.success(
                            isAr
                              ? "تم نسخ كود الربط! أرسله داخل @egxbots_bot"
                              : "Link command copied! Send to @egxbots_bot"
                          );
                        }}
                        className="inline-flex h-10 px-3 items-center justify-center gap-1.5 border-2 border-black dark:border-white bg-[#FFE600] text-black font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer"
                      >
                        <Copy className="w-3.5 h-3.5 shrink-0" />
                        <span>{isAr ? "نسخ الكود" : "Copy Code"}</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        if (userId) invalidateUserQuotaCache(userId);
                        void refreshProInvite();
                        void reloadProfile();
                        toast.info(isAr ? "جاري تحديث الحالة..." : "Refreshing status...");
                      }}
                      className="inline-flex h-10 px-3 items-center justify-center gap-1.5 border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 text-black dark:text-white font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer"
                    >
                      <Check className="w-3.5 h-3.5 shrink-0" />
                      <span>{isAr ? "تحقق الآن" : "Verify"}</span>
                    </button>
                  </div>
                </div>

                {/* Section B: VIP & Free Telegram Channels (hidden in GCC chat-only UAE/Qatar mode) */}
                {!isGccChatOnly ? (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      <Send className="w-4 h-4 text-sky-500" />
                      <h4 className="text-base font-black text-black dark:text-white">
                        {isSaudi
                          ? isAr
                            ? "قناة تليجرام VIP (السوق السعودي 🇸🇦)"
                            : "Saudi VIP Telegram Channel 🇸🇦"
                          : isAr
                          ? "قنوات إشارات التليجرام"
                          : "Telegram Signal Channels"}
                      </h4>
                    </div>

                    <p className="text-xs sm:text-sm font-bold text-zinc-600 dark:text-zinc-300 leading-relaxed">
                      {inviteLoading
                        ? isAr
                          ? "جاري التحقق من رابط قناة التليجرام..."
                          : "Checking your Telegram channel invite..."
                        : inviteError && !isSaudi
                        ? isAr
                          ? "تعذر تجهيز دعوة VIP حالياً. أعد المحاولة، وإذا استمرت المشكلة تواصل مع الدعم."
                          : "We couldn't prepare the VIP invite. Retry, or contact support."
                        : canSeeVipLinks
                        ? isSaudi
                          ? isAr
                            ? "اشتراكك VIP مفعل. استخدم رابط قناة VIP للسوق السعودي لمتابعة الإشارات الفورية."
                            : "Your VIP access is active. Use the Saudi VIP channel link below for live TASI signals."
                          : isAr
                          ? "اشتراكك VIP مفعل. استخدم روابط الدعوة الخاصة بك للدخول إلى القنوات الفورية."
                          : "Your VIP access is active. Use your private invite links below to join."
                        : isSaudi
                        ? isAr
                          ? "السوق السعودي (تاسي) له قناة VIP حصرية لمشتركي Pro و VIP Radar فقط."
                          : "The Saudi market (TASI) has an exclusive VIP channel for Pro & VIP Radar subscribers."
                        : isAr
                        ? "القناة المجانية تعرض الإشارات بتأخير 15 يوماً. الإشارات الفورية متاحة لمشتركي Pro و VIP Radar."
                        : "The free channel displays signals with a 15-day delay. Live alerts require Pro or VIP Radar."}
                    </p>

                    {canSeeVipLinks && (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {saudiProInviteUrl && (
                          <div className="rounded-xl border-2 border-emerald-600 bg-emerald-50 dark:bg-emerald-950/30 p-3.5 space-y-1.5">
                            <p className="text-xs font-black text-emerald-700 dark:text-emerald-300">
                              {isAr ? "قناة VIP — السوق السعودي 🇸🇦" : "VIP Channel — Saudi 🇸🇦"}
                            </p>
                            <a
                              href={saudiProInviteUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="block break-all text-[11px] font-mono font-bold text-emerald-700 dark:text-emerald-300 underline"
                            >
                              {saudiProInviteUrl}
                            </a>
                            <p className="text-[10px] font-bold text-zinc-500 dark:text-zinc-400">
                              {isAr
                                ? `صالح حتى ${proInvite.invite_expires_at ? new Date(proInvite.invite_expires_at).toLocaleDateString("ar-EG") : "نهاية اشتراكك"}`
                                : `Valid until ${proInvite.invite_expires_at ? new Date(proInvite.invite_expires_at).toLocaleDateString() : "subscription end"}`}
                            </p>
                          </div>
                        )}
                        {proInvite.invite_link && (
                          <div className="rounded-xl border-2 border-indigo-600 bg-indigo-50 dark:bg-indigo-950/30 p-3.5 space-y-1.5">
                            <p className="text-xs font-black text-indigo-700 dark:text-indigo-300">
                              {isAr ? "قناة VIP — السوق المصري 🇪🇬" : "VIP Channel — Egypt 🇪🇬"}
                            </p>
                            <a
                              href={proInvite.invite_link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="block break-all text-[11px] font-mono font-bold text-indigo-700 dark:text-indigo-300 underline"
                            >
                              {proInvite.invite_link}
                            </a>
                            <p className="text-[10px] font-bold text-zinc-500 dark:text-zinc-400">
                              {isAr
                                ? `صالح حتى ${proInvite.invite_expires_at ? new Date(proInvite.invite_expires_at).toLocaleDateString("ar-EG") : "نهاية اشتراكك"}`
                                : `Valid until ${proInvite.invite_expires_at ? new Date(proInvite.invite_expires_at).toLocaleDateString() : "subscription end"}`}
                            </p>
                          </div>
                        )}
                      </div>
                    )}

                    {(inviteError || inviteLoading) && (
                      <div className="flex items-center gap-3 text-xs font-bold text-amber-700 dark:text-amber-300">
                        <span>
                          {inviteLoading
                            ? isAr
                              ? "جاري تجهيز دعوة VIP..."
                              : "Preparing your VIP invite..."
                            : isAr
                            ? "تعذر تحميل دعوة VIP."
                            : "VIP invite unavailable."}
                        </span>
                        {!inviteLoading && (
                          <button type="button" onClick={() => void refreshProInvite()} className="underline cursor-pointer">
                            {isAr ? "إعادة المحاولة" : "Retry"}
                          </button>
                        )}
                      </div>
                    )}

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {isSaudi ? (
                        <>
                          {canSeeVipLinks ? (
                            <a
                              href={saudiProInviteUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex h-11 items-center justify-center gap-2 border-2 border-black dark:border-white bg-amber-300 text-black font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                            >
                              <Send className="w-4 h-4 shrink-0" />
                              {isAr ? "دخول قناة VIP السعودية 🇸🇦" : "Join Saudi VIP Channel 🇸🇦"}
                            </a>
                          ) : (
                            !inviteLoading && (
                              <Link
                                href="/pricing"
                                prefetch={false}
                                className="inline-flex h-11 items-center justify-center gap-2 border-2 border-black dark:border-white bg-amber-300 text-black font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                              >
                                <Send className="w-4 h-4 shrink-0" />
                                {isAr ? "ترقية لدخول VIP السعودية 👑" : "Upgrade for Saudi VIP 👑"}
                              </Link>
                            )
                          )}
                          {canSeeVipLinks && (
                            <a
                              href={saudiTelegramWebUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex h-11 items-center justify-center gap-2 border-2 border-black dark:border-white bg-white dark:bg-zinc-800 text-black dark:text-white font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                            >
                              <Globe className="w-4 h-4 shrink-0" />
                              {isAr ? "فتح قناة VIP السعودية (Web)" : "Open Saudi VIP (Web)"}
                            </a>
                          )}
                        </>
                      ) : (
                        (proInviteUrl || (!canSeeVipLinks && !inviteError && !inviteLoading)) && (
                          <>
                            <a
                              href={proInviteUrl || freeTelegramUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex h-11 items-center justify-center gap-2 border-2 border-black dark:border-white bg-amber-300 text-black font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                            >
                              <Send className="w-4 h-4 shrink-0" />
                              {proInviteUrl ? (isAr ? "دخول قناة Pro" : "Join Pro Telegram") : isAr ? "القناة المجانية" : "Free Channel"}
                            </a>
                            <a
                              href={telegramWebUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex h-11 items-center justify-center gap-2 border-2 border-black dark:border-white bg-white dark:bg-zinc-800 text-black dark:text-white font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                            >
                              <Globe className="w-4 h-4 shrink-0" />
                              {proInviteUrl ? (isAr ? "فتح دعوة Pro (Web)" : "Open Pro (Web)") : isAr ? "القناة المجانية (Web)" : "Free Channel (Web)"}
                            </a>
                          </>
                        )
                      )}
                    </div>
                  </div>
                ) : (
                  <p className="text-xs font-bold text-zinc-500 dark:text-zinc-400">
                    {isAr
                      ? "هذا السوق مخصص حالياً لمساعد الذكاء الاصطناعي ARTORO AI في الموقع والتطبيق وبوت التليجرام الخاص."
                      : "This market is currently focused on ARTORO AI Chat on web, mobile, and private Telegram bot."}
                  </p>
                )}
              </section>
            </div>
          </div>
        )}
      </div>

      <PaymentWelcomeModal
        isOpen={showWelcomeModal}
        onClose={handleCloseWelcomeModal}
        orderId={welcomeOrderId}
        userId={userId}
        isAr={isAr}
        proInvite={proInvite}
        telegramLinked={telegramLinked}
        onRefreshInvite={refreshProInvite}
        onRefreshProfile={reloadProfile}
      />
    </div>
  );
}
