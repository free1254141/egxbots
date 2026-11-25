"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { useLanguage } from "@/contexts/LanguageContext";
import { useMarket } from "@/contexts/MarketContext";
import { useAuth } from "@/contexts/AuthContext";
import { hfPublicFetch } from "@/lib/hf-browser-client";
import {
  prepareTrialAutostart,
  clearTrialAutostart,
  TRIAL_AUTOSTART_EVENT,
  triggerTrialSuccessModal,
} from "@/lib/trial-onboarding";
import {
  Loader2,
  Rocket,
  Check,
  X,
  Smartphone,
  CheckCircle2,
  ShieldCheck,
  Zap,
  MessageSquare,
  BarChart3,
  ArrowLeft,
  ArrowRight,
  LockKeyhole,
  Sparkles,
  Shield,
  Clock,
  HelpCircle,
  Copy,
  ExternalLink,
  Info,
  Activity,
  Crown,
  Flame,
  Award,
  BellRing,
  Bot,
  Send,
} from "lucide-react";
import { toast } from "sonner";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import { trackEvent } from "@/lib/gtm";

import { broadcastEntitlements } from "@/lib/entitlements";
import { fetchUserQuotaCached, invalidateUserQuotaCache } from "@/lib/user-quota-client";
import {
  computeCheckoutPricing,
  lifetimeBreakevenMonths,
  toDisplayAmount,
} from "@/lib/saudi-pricing";
import {
  DURATION_SLIDER_PLANS,
  DURATION_SLIDER_SCHEDULE,
  computeDurationPlanPricing,
  formatDurationLabel,
  getDurationScheduleEntry,
} from "@/lib/duration-pricing";
import { SAUDI_VIP_TELEGRAM_WEB_URL } from "@/lib/telegramProInvite";
import { getTrialDeviceFingerprint, notifyTrialActivationError } from "@/lib/device-fingerprint";
export { broadcastEntitlements };

type Step = "plans" | "payment" | "submitted";

/** Strip an accidentally repeated or pasted leading dial prefix from local phone digits. */
function stripDialPrefix(digits: string, dialCode: string): string {
  let clean = digits.replace(/[^\d]/g, "");
  const dialDigits = dialCode.replace(/^\+/, "");
  if (dialDigits && clean.startsWith(`00${dialDigits}`) && clean.length - dialDigits.length - 2 >= 7) {
    clean = clean.slice(dialDigits.length + 2);
  } else if (dialDigits.length >= 2 && clean.startsWith(dialDigits) && clean.length - dialDigits.length >= 7) {
    clean = clean.slice(dialDigits.length);
  } else if (dialDigits === "1" && clean.startsWith("1") && clean.length === 11) {
    clean = clean.slice(1);
  }
  return clean.replace(/^0+/, "");
}

export default function PricingClient() {
  const { language } = useLanguage();
  const isAr = language === "ar";
  const { market, isSaudi, isUae, isQatar, isGccChatOnly, currencyLabel, currencyCode } = useMarket();
  const isGulfPricing = isSaudi || isGccChatOnly;
  const brandName = isSaudi ? "TASI BOTS" : isUae ? "UAE BOTS" : isQatar ? "QSE BOTS" : "EGX BOTS";
  const displayAmount = (egp: number) => toDisplayAmount(egp, market);
  const formatPrice = (egp: number) => `${displayAmount(egp).toLocaleString()} ${currencyLabel}`;
  const { user } = useAuth();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [localConfig, setLocalConfig] = useState<any>(null);
  const [localOrder, setLocalOrder] = useState<string | null>(null);
  const [customerMobile, setCustomerMobile] = useState("");
  const [selectedDialCode, setSelectedDialCode] = useState("+20");
  const userPickedDialCodeRef = useRef(false);
  const [dialDropdownOpen, setDialDropdownOpen] = useState(false);
  const [step, setStep] = useState<Step>("plans");
  const [b2bTrialModal, setB2bTrialModal] = useState<{
    open: boolean;
    license: any;
    connectUrl: string;
    code: string;
    tier: string;
  } | null>(null);
  const [startingB2BTrial, setStartingB2BTrial] = useState<string | null>(null);

  const handleStartB2BTrial = async (tier: string = "b2b_pro") => {
    if (!user) {
      toast.error(isAr ? "يرجى تسجيل الدخول أولاً لبدء التجربة المجانية لجروبك" : "Please sign in to start your 3-day free trial");
      router.push("/login?redirect=/pricing?mode=b2b");
      return;
    }

    try {
      setStartingB2BTrial(tier);
      const res = await fetch("/api/b2b/trial", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier }),
      });
      const data = await res.json();
      if (res.ok && data.ok && data.license) {
        toast.success(isAr ? "🎉 تم تفعيل رخصتك التجريبية (3 أيام) بنجاح!" : "🎉 3-day trial activated successfully!");
        setB2bTrialModal({
          open: true,
          license: data.license,
          connectUrl: data.connect_url,
          code: data.activation_code,
          tier,
        });
      } else {
        toast.error(data.message || data.error || (isAr ? "فشل إنشاء التجربة" : "Failed to start trial"));
        if (data.error === "trial_already_claimed") {
          openPaymentStep(tier);
        }
      }
    } catch (err: any) {
      toast.error(err.message || (isAr ? "خطأ في الشبكة" : "Network error"));
    } finally {
      setStartingB2BTrial(null);
    }
  };
  const [orderStatus, setOrderStatus] = useState<string>("submitted");
  const [orderDurationDays, setOrderDurationDays] = useState<number | null>(null);
  const [subscriptionEnd, setSubscriptionEnd] = useState<string | null>(null);
  const [telegramProUrl, setTelegramProUrl] = useState("");
  const [telegramSaudiProUrl, setTelegramSaudiProUrl] = useState("");
  const [b2bDashboardUrl, setB2bDashboardUrl] = useState("");
  const [isPro, setIsPro] = useState(false);
  const [activePlanId, setActivePlanId] = useState<string | null>(null);
  const [selectedPlan, setSelectedPlan] = useState("pro");
  const [selectedMonths, setSelectedMonths] = useState<number>(1);
  const proCardRef = useRef<HTMLDivElement>(null);
  const [promoInput, setPromoInput] = useState("");
  const [appliedPromo, setAppliedPromo] = useState<{ code: string; name: string; discount_percent: number } | null>(null);
  const [promoChecking, setPromoChecking] = useState(false);

  const [trialEligible, setTrialEligible] = useState(false);
  const [trialLoading, setTrialLoading] = useState(false);
  const [trialExpiresAt, setTrialExpiresAt] = useState<string | null>(null);
  const [pricingCategory, setPricingCategory] = useState<"retail" | "b2b">("retail");

  const handleStartTrial = async () => {
    if (!user) {
      router.push("/login?redirect=/pricing");
      return;
    }
    setTrialLoading(true);
    try {
      const variant = prepareTrialAutostart();
      const device_fp = await getTrialDeviceFingerprint();
      const res = await fetch("/api/subscription/trial", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ variant, device_fp }),
      });
      const data = await res.json();
      if (res.ok && data?.success) {
        invalidateUserQuotaCache(user.id);
        toast.success(isAr ? "تم تفعيل تجربة Pro المجانية لمدة 3 أيام بنجاح!" : "Pro 3-day trial activated successfully!");
        setIsPro(true);
        broadcastEntitlements(true);
        setTrialEligible(false);
        setTrialExpiresAt(data.expires_at || null);
        // Show celebratory success modal with VIP Telegram channel join link
        triggerTrialSuccessModal({
          invite_link: data.invite_link,
          expires_at: data.expires_at,
          telegram_sent: data.telegram_sent,
        });
      } else {
        clearTrialAutostart();
        notifyTrialActivationError(data, isAr, user?.id);
      }
    } catch {
      clearTrialAutostart();
      toast.error(isAr ? "حدث خطأ في الاتصال" : "Network error");
    } finally {
      setTrialLoading(false);
    }
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const modeParam = params.get("mode");
      if (modeParam === "b2b" || modeParam === "channels" || modeParam === "business") {
        setPricingCategory("b2b");
      }
      const monthsParam = Number(params.get("months"));
      if (Number.isInteger(monthsParam) && monthsParam >= 1 && monthsParam <= 12) {
        setSelectedMonths(monthsParam);
      }
      const planParam = params.get("plan");
      if (planParam && ["pro", "pro_6m", "pro_1y", "lifetime", "chat_only", "vip_only", "b2b_starter", "b2b_pro", "b2b_enterprise"].includes(planParam)) {
        if (planParam === "pro_6m") {
          setSelectedPlan("pro");
          setSelectedMonths(6);
          setPricingCategory("retail");
        } else if (planParam === "pro_1y") {
          setSelectedPlan("pro");
          setSelectedMonths(12);
          setPricingCategory("retail");
        } else {
          setSelectedPlan(planParam);
          if (["pro", "chat_only", "vip_only", "lifetime"].includes(planParam)) {
            setPricingCategory("retail");
          }
          if (["b2b_starter", "b2b_pro", "b2b_enterprise"].includes(planParam)) {
            setPricingCategory("b2b");
          }
        }
      }
    }
  }, []);

  // Clear vip_only when UAE/Qatar (chat-only markets without local VIP Telegram); B2B stays available for all markets
  useEffect(() => {
    if (isGccChatOnly && selectedPlan === "vip_only") {
      setSelectedPlan("chat_only");
    }
  }, [isGccChatOnly, selectedPlan]);

  // Default dial code to Saudi (+966), UAE (+971), Qatar (+974), or Egypt (+20) when phone is empty
  useEffect(() => {
    if (!userPickedDialCodeRef.current && !customerMobile.trim()) {
      setSelectedDialCode(isSaudi ? "+966" : isUae ? "+971" : isQatar ? "+974" : "+20");
    }
  }, [isSaudi, isUae, isQatar, customerMobile]);

  // Pre-fill customer mobile from their saved profile if available
  useEffect(() => {
    if (!user?.id) return;
    const currentUserId = user.id;
    let active = true;
    async function loadPhone() {
      try {
        const sb = createSupabaseBrowserClient();
        const { data } = await sb
          .from("profiles")
          .select("whatsapp_number")
          .eq("id", currentUserId)
          .maybeSingle();
        if (active && data?.whatsapp_number && typeof data.whatsapp_number === "string") {
          const cleanSaved = data.whatsapp_number.trim().replace(/[\s\-()]/g, "");
          const normalizedSaved = cleanSaved.startsWith("00") ? `+${cleanSaved.slice(2)}` : cleanSaved;
          const knownCodes = ["+966", "+971", "+965", "+974", "+973", "+968", "+962", "+961", "+249", "+218", "+216", "+212", "+20", "+44", "+1"];
          const matchedCode = knownCodes.find((code) => normalizedSaved.startsWith(code));
          if (matchedCode) {
            userPickedDialCodeRef.current = true;
            setSelectedDialCode(matchedCode);
            setCustomerMobile(stripDialPrefix(normalizedSaved.slice(matchedCode.length), matchedCode));
          } else if (/^01[0125]\d{8}$/.test(normalizedSaved)) {
            userPickedDialCodeRef.current = true;
            setSelectedDialCode("+20");
            setCustomerMobile(stripDialPrefix(normalizedSaved, "+20"));
          } else {
            setCustomerMobile(stripDialPrefix(normalizedSaved, selectedDialCode));
          }
        }
      } catch {}
    }
    void loadPhone();
    return () => {
      active = false;
    };
  }, [user?.id]);
  const [copiedOrder, setCopiedOrder] = useState(false);
  const [pollRestart, setPollRestart] = useState(0);
  const [pollingExhausted, setPollingExhausted] = useState(false);

  // Live founders counter from backend — refreshed every time localConfig is fetched
  const isGrandfathered = Boolean(
    localConfig?.founders?.is_grandfathered ||
    localConfig?.plans?.find((p: any) => p.id === "pro")?.is_grandfathered_renewal
  );
  const isGrandfathered100 = Boolean(
    localConfig?.founders?.is_grandfathered_100 ||
    localConfig?.plans?.find((p: any) => p.id === "pro")?.is_grandfathered_100
  );
  const foundersRemaining: number | null = null;
  const foundersEndsAt: string = localConfig?.founders?.ends_at || "2026-11-14T01:00:00Z";

  // Countdown timer for the time-limited founders offer
  const [foundersCountdown, setFoundersCountdown] = useState<string | null>(null);
  const [foundersTimeExpired, setFoundersTimeExpired] = useState<boolean>(false);
  useEffect(() => {
    if (!foundersEndsAt) { setFoundersCountdown(null); setFoundersTimeExpired(false); return; }
    const update = () => {
      const diffMs = new Date(foundersEndsAt).getTime() - Date.now();
      if (diffMs <= 0) {
        setFoundersCountdown(null);
        setFoundersTimeExpired(true);
        return;
      }
      setFoundersTimeExpired(false);
      const d = Math.floor(diffMs / 86400000);
      const h = Math.floor((diffMs % 86400000) / 3600000);
      const m = Math.floor((diffMs % 3600000) / 60000);
      const s = Math.floor((diffMs % 60000) / 1000);
      if (d > 0) setFoundersCountdown(`${d}ي ${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`);
      else setFoundersCountdown(`${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`);
    };
    update();
    const iv = setInterval(update, 1000);
    return () => clearInterval(iv);
  }, [foundersEndsAt]);
  const foundersIsOpen: boolean = Boolean((localConfig?.founders?.is_open ?? true) && !foundersTimeExpired);

  // Live lifetime spots counter from backend — strictly limited to 20 users
  const lifetimeLimit: number = localConfig?.lifetime?.limit ?? 20;
  const lifetimeCount: number = localConfig?.lifetime?.count ?? 0;
  const lifetimeRemaining: number = localConfig?.lifetime?.remaining ?? Math.max(0, lifetimeLimit - lifetimeCount);
  const lifetimeIsOpen: boolean = localConfig?.lifetime?.is_open ?? (lifetimeRemaining > 0);

  // ─── قائمة الدول المدعومة ───────────────────────────────────────────────────
  const DIAL_COUNTRIES = [
    { code: "+20",  flag: "🇪🇬", name: "مصر",      nameEn: "Egypt" },
    { code: "+966", flag: "🇸🇦", name: "السعودية", nameEn: "Saudi Arabia" },
    { code: "+971", flag: "🇦🇪", name: "الإمارات", nameEn: "UAE" },
    { code: "+965", flag: "🇰🇼", name: "الكويت",   nameEn: "Kuwait" },
    { code: "+974", flag: "🇶🇦", name: "قطر",      nameEn: "Qatar" },
    { code: "+973", flag: "🇧🇭", name: "البحرين",  nameEn: "Bahrain" },
    { code: "+968", flag: "🇴🇲", name: "عُمان",    nameEn: "Oman" },
    { code: "+962", flag: "🇯🇴", name: "الأردن",   nameEn: "Jordan" },
    { code: "+961", flag: "🇱🇧", name: "لبنان",    nameEn: "Lebanon" },
    { code: "+249", flag: "🇸🇩", name: "السودان",  nameEn: "Sudan" },
    { code: "+218", flag: "🇱🇾", name: "ليبيا",    nameEn: "Libya" },
    { code: "+216", flag: "🇹🇳", name: "تونس",     nameEn: "Tunisia" },
    { code: "+212", flag: "🇲🇦", name: "المغرب",   nameEn: "Morocco" },
    { code: "+1",   flag: "🇺🇸", name: "أمريكا",   nameEn: "USA" },
    { code: "+44",  flag: "🇬🇧", name: "بريطانيا", nameEn: "UK" },
  ];

  const selectedCountry = DIAL_COUNTRIES.find((c) => c.code === selectedDialCode) ?? DIAL_COUNTRIES[0];

  // بناء الرقم الكامل: 01XXXXXXXXX لمصر (للتوافق مع محافظ EasyKash) أو +CCXXXXXXXXX للدولي
  const localDigits = stripDialPrefix(customerMobile, selectedDialCode);
  const fullMobileNumber =
    localDigits.length === 0
      ? ""
      : selectedDialCode === "+20"
        ? `0${localDigits}`
        : `${selectedDialCode}${localDigits}`;

  const normalizedMobile = fullMobileNumber;

  const isEgyptianMobile =
    selectedDialCode === "+20" &&
    /^01[0125]\d{8}$/.test(normalizedMobile);
  const isInternationalMobile =
    selectedDialCode !== "+20" &&
    /^\+[1-9]\d{6,14}$/.test(normalizedMobile);
  const isMobileValid = (isEgyptianMobile || isInternationalMobile) && localDigits.length >= 7;

  useEffect(() => {
    if (step !== "submitted" || !localOrder) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    const startedAt = Date.now();
    setPollingExhausted(false);
    const schedule = () => {
      if (stopped) return;
      // Stop automatic polling after 4 attempts (~60 seconds) or if user navigates away.
      // The user can still click 'Check payment status again' manually.
      if (attempts >= 4 || Date.now() - startedAt >= 60_000 || document.visibilityState === "hidden") {
        setPollingExhausted(true);
        return;
      }
      const delay = Math.min(25_000, 6_000 * Math.pow(1.5, attempts));
      attempts += 1;
      timer = setTimeout(check, delay);
    };
    const check = async () => {
      if (stopped || document.visibilityState === "hidden") return;
      // Fast-path: if the quota endpoint already confirmed Pro, no need to poll
      if (isPro) {
        setOrderStatus("approved");
        broadcastEntitlements(true);
        // Fetch the invite link if we don't have it yet
        if (selectedPlan !== "chat_only" && !selectedPlan.startsWith("b2b_") && (!telegramProUrl || (isGulfPricing && !telegramSaudiProUrl))) {
          const vip = await fetch("/api/profile/telegram-pro", { cache: "no-store", signal: AbortSignal.timeout(12_000) })
            .then((r) => (r.ok ? r.json() : null))
            .catch(() => null);
          if (!stopped && vip?.invite_link) setTelegramProUrl(vip.invite_link);
          if (!stopped && vip?.saudi_invite_link) setTelegramSaudiProUrl(vip.saudi_invite_link);
          if (!stopped && vip?.current_period_end) setSubscriptionEnd(vip.current_period_end);
        }
        return;
      }
      try {
        const res = await fetch(`/api/payment/easykash/status?order_id=${encodeURIComponent(localOrder)}`, {
          cache: "no-store",
          signal: AbortSignal.timeout(12_000),
        });
        const data = res.ok ? await res.json().catch(() => ({})) : {};
        if (stopped) return;
        if (data.status) {
        const settledStatus = ["expired", "rejected", "failed", "canceled", "cancelled"].includes(String(data.status).toLowerCase())
          ? "failed"
          : data.status;
        setOrderStatus(settledStatus);
        if (settledStatus === "failed") {
          fetch("/api/payment/failed-recovery", { method: "POST" }).catch(() => {});
        }
        const resolvedPlan = String(data.plan_id || selectedPlan || "");
        if (settledStatus === "approved") {
          setIsPro(true);
          broadcastEntitlements(true, resolvedPlan !== "vip_only");
        }
        if (data.plan_id) setSelectedPlan(data.plan_id);
        if (typeof data.duration_days === "number" && data.duration_days > 0) {
          setOrderDurationDays(data.duration_days);
        }
        setSubscriptionEnd(data.subscription?.current_period_end || null);
        setTelegramProUrl(data.telegram_pro_url || "");
        if (data.telegram_saudi_pro_url) setTelegramSaudiProUrl(data.telegram_saudi_pro_url);
        setB2bDashboardUrl(String(data.b2b_dashboard_url || "").replace(/^https?:\/\/[^/]+/, ""));
        const isB2bResolved = resolvedPlan.startsWith("b2b_");
        if (settledStatus === "approved" && !isB2bResolved && resolvedPlan !== "chat_only" && (!data.telegram_pro_url || (isGulfPricing && !data.telegram_saudi_pro_url))) {
          const vip = await fetch("/api/profile/telegram-pro", { cache: "no-store", signal: AbortSignal.timeout(12_000) })
            .then((response) => (response.ok ? response.json() : null))
            .catch(() => null);
          if (!stopped && vip?.invite_link) {
            setTelegramProUrl(vip.invite_link);
          }
          if (!stopped && vip?.saudi_invite_link) {
            setTelegramSaudiProUrl(vip.saudi_invite_link);
          }
          if (!stopped && vip?.current_period_end) {
            setSubscriptionEnd(vip.current_period_end || data.subscription?.current_period_end || null);
          }
        }
        if (settledStatus === "approved" || settledStatus === "failed") return;
        }
      } catch {
        // Transient gateway/backend failures are retried with bounded backoff.
      }
      schedule();
    };
    const onVisible = () => {
      if (document.visibilityState === "visible" && !stopped) {
        if (timer) clearTimeout(timer);
        void check();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    void check();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [step, localOrder, pollRestart, isPro, isSaudi, isGulfPricing, telegramProUrl, telegramSaudiProUrl]);

  useEffect(() => {
    let cancelled = false;
    const loadConfig = async () => {
      try {
        const headers: Record<string, string> = {};
        if (user) {
          try {
            const sb = createSupabaseBrowserClient();
            const { data } = await sb.auth.getSession();
            if (data?.session?.access_token) {
              headers["Authorization"] = `Bearer ${data.session.access_token}`;
            }
          } catch {}
        }
        const response = user
          ? await fetch("/api/payment/easykash/config", {
              headers,
              cache: "no-store",
            })
          : await hfPublicFetch(
              "/api/payment/public-config",
              { headers, cache: "default" },
              { cacheTtlMs: 300_000 }
            );
        if (!response.ok) throw new Error("Payment configuration unavailable");
        const local = await response.json();
        if (!cancelled) setLocalConfig(local);
      } catch {
        if (!cancelled) setLocalConfig(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void loadConfig();
    return () => {
      cancelled = true;
    };
  }, [user]);

  // Funnel step 1 of 3 (GTM): the visitor reached pricing.
  useEffect(() => {
    trackEvent("pricing_view", { signed_in: Boolean(user?.id), market });
  }, [user?.id, market]);

  useEffect(() => {
    if (!user?.id) {
      setTrialEligible(true);
      setIsPro(false);
      setActivePlanId(null);
      setSubscriptionEnd(null);
      return;
    }
    let active = true;
    let inFlight = false;
    let lastKnownPro: boolean | null = null;
    let lastFocusRefreshAt = 0;
    const refreshPlan = async (force = false) => {
      if (inFlight) return;
      inFlight = true;
      try {
        const data = await fetchUserQuotaCached(user.id, { force });
        if (!active || !data || data.ok === false || !data.plan) return;
        const proActive = data?.plan?.is_pro === true;
        const paidPlanId = proActive && !data?.plan?.is_trial ? String(data?.plan?.id || "").trim().toLowerCase() : null;
        setIsPro(proActive);
        setActivePlanId(paidPlanId || null);
        setSubscriptionEnd(data?.plan?.current_period_end || null);
        if (data?.plan?.trial_eligible) {
          setTrialEligible(true);
        } else {
          setTrialEligible(false);
          if (data?.plan?.trial_expires_at) setTrialExpiresAt(data.plan.trial_expires_at);
        }
        if (proActive && lastKnownPro === false) {
          broadcastEntitlements(true, data?.plan?.has_chat_pro ?? data?.plan?.id !== "vip_only");
        }
        lastKnownPro = proActive;
      } catch {
        // Keep the last known state on a temporary network failure.
      } finally {
        inFlight = false;
      }
    };
    const refreshIfStaleOnReturn = () => {
      if (lastKnownPro === true && orderStatus !== "submitted") return;
      const now = Date.now();
      if (now - lastFocusRefreshAt < 5_000) return;
      lastFocusRefreshAt = now;
      void refreshPlan(true);
    };
    setIsPro(false);
    void refreshPlan(orderStatus === "approved");
    const onFocus = () => refreshIfStaleOnReturn();
    const onVisible = () => {
      if (document.visibilityState === "visible") refreshIfStaleOnReturn();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [user?.id, orderStatus]);

  const copyOrderId = () => {
    if (!localOrder) return;
    navigator.clipboard.writeText(localOrder);
    setCopiedOrder(true);
    toast.success(isAr ? "تم نسخ رقم الطلب" : "Order ID copied");
    setTimeout(() => setCopiedOrder(false), 2000);
  };

  const scrollToProCard = () => {
    if (typeof window === "undefined") return;
    const card = proCardRef.current || document.getElementById("pro-plan-card");
    if (!card) return;

    const headerH = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--header-h")) || 72;
    const stickyBar = document.getElementById("pricing-duration-navbar");
    const stickyH = stickyBar ? stickyBar.offsetHeight : 80;
    const totalStickyOffset = headerH + stickyH + 16;

    const cardRect = card.getBoundingClientRect();
    const targetScrollY = window.scrollY + cardRect.top - totalStickyOffset;

    window.scrollTo({
      top: Math.max(0, targetScrollY),
      behavior: "smooth",
    });
  };

  const handleDurationSliderChange = (months: number, shouldScroll = false) => {
    const safe = Math.min(12, Math.max(1, Math.round(Number(months) || 1)));
    setSelectedMonths(safe);
    if (shouldScroll) {
      setTimeout(() => {
        scrollToProCard();
      }, 50);
    }
  };

  // The plans view is much taller than the payment view. Reset scroll before
  // switching views so the browser cannot clamp the old scroll position to
  // the bottom of the shorter payment page.
  const openPaymentStep = (planId: string) => {
    setSelectedPlan(planId);
    setOrderDurationDays(null);
    window.scrollTo({ top: 0, behavior: "auto" });
    setStep("payment");
  };

  const applyPromoCode = async (rawCode: string, trackClick = false, silent = false) => {
    const clean = (rawCode || "").trim().toUpperCase();
    if (!clean) return;
    setPromoChecking(true);
    try {
      let shouldTrack = trackClick;
      if (shouldTrack) {
        try {
          if (sessionStorage.getItem(`egx_tracked_ref_${clean}`) === "1") {
            shouldTrack = false;
          }
        } catch {}
      }
      const res = await fetch(
        `/api/payment/easykash/validate-promo?code=${encodeURIComponent(clean)}${shouldTrack ? "&track=1" : ""}`,
        { cache: "no-store" }
      );
      const data = await res.json().catch(() => ({}));
      if (res.ok && data?.valid) {
        if (shouldTrack) {
          try {
            sessionStorage.setItem(`egx_tracked_ref_${clean}`, "1");
          } catch {}
        }
        setAppliedPromo({
          code: data.code,
          name: data.name,
          discount_percent: Number(data.discount_percent || 0),
        });
        setPromoInput(data.code);
        try {
          localStorage.setItem("egx_affiliate_ref", data.code);
        } catch {}
        if (!silent) {
          toast.success(
            isAr
              ? `🎉 تم تفعيل كود (${data.code}) بنجاح — خصم ${data.discount_percent}%!`
              : `🎉 Promo code (${data.code}) applied — ${data.discount_percent}% OFF!`
          );
        }
      } else {
        if (data?.self_referral) {
          setAppliedPromo(null);
          setPromoInput("");
          try {
            localStorage.removeItem("egx_affiliate_ref");
          } catch {}
        }
        if (!silent) {
          toast.error(data?.error || (isAr ? "كود الخصم غير صحيح أو منتهي الصلاحية" : "Invalid or expired promo code"));
        }
      }
    } catch {
      if (!silent) {
        toast.error(isAr ? "تعذر التحقق من الكود حالياً" : "Could not verify promo code");
      }
    } finally {
      setPromoChecking(false);
    }
  };

  const removePromoCode = () => {
    setAppliedPromo(null);
    setPromoInput("");
    try {
      localStorage.removeItem("egx_affiliate_ref");
    } catch {}
  };

  const startEasyKashPayment = async (planId = selectedPlan) => {
    if (!user) {
      trackEvent("checkout_login_required", { plan: planId });
      router.push(`/login?redirect=${encodeURIComponent("/pricing")}`);
      return;
    }
    if (!isMobileValid) {
      toast.error(
        isAr
          ? `أدخل رقم الموبايل بدون مفتاح الدولة — ${selectedDialCode} هيتضاف تلقائياً`
          : `Enter your number without country code — ${selectedDialCode} is added automatically`
      );
      return;
    }
    setBusy(true);
    const resolvedPlanId =
      planId === "pro_6m" || planId === "pro_1y" ? "pro" : planId;
    const includeSliderDuration = DURATION_SLIDER_PLANS.has(resolvedPlanId);
    const resolvedMonths =
      planId === "pro_6m" ? 6 : planId === "pro_1y" ? 12 : selectedMonths;
    try {
      const res = await fetch("/api/payment/easykash/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plan_id: resolvedPlanId,
          mobile: normalizedMobile,
          promo_code: appliedPromo?.code || "",
          market,
          ...(includeSliderDuration ? { duration_months: resolvedMonths } : {}),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || (isAr ? "تعذر إنشاء طلب الدفع" : "Could not start checkout"));
      setLocalOrder(data.order_id);
      if (typeof data.duration_days === "number" && data.duration_days > 0) {
        setOrderDurationDays(data.duration_days);
      } else if (includeSliderDuration) {
        setOrderDurationDays(selectedEntry.days);
      }
      const checkoutUrl = new URL(String(data.url || ""));
      const checkoutPath = checkoutUrl.pathname.split("/").filter(Boolean);
      if (
        !["https://easykash.net", "https://www.easykash.net"].includes(checkoutUrl.origin) ||
        checkoutUrl.search ||
        checkoutUrl.hash ||
        checkoutPath.length !== 2 ||
        checkoutPath[0] !== "DirectPayV1" ||
        !/^[A-Za-z0-9]+$/.test(checkoutPath[1])
      ) {
        throw new Error(isAr ? "رابط الدفع غير صالح" : "Invalid payment URL");
      }
      window.location.assign(`https://www.easykash.net/DirectPayV1/${checkoutPath[1]}`);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ref = params.get("customerReference");
    if (params.get("payment") === "easykash" && ref) {
      window.location.replace(`/profile?payment=easykash&customerReference=${encodeURIComponent(ref)}`);
      return;
    }
    const urlPromo = (params.get("ref") || params.get("promo") || params.get("code") || "").trim().toUpperCase();
    if (urlPromo) {
      applyPromoCode(urlPromo, true, false);
    } else {
      try {
        const savedPromo = (localStorage.getItem("egx_affiliate_ref") || "").trim().toUpperCase();
        if (savedPromo) {
          applyPromoCode(savedPromo, false, true);
        }
      } catch {}
    }
  }, []);

  useEffect(() => {
    if (user?.id && appliedPromo?.code) {
      applyPromoCode(appliedPromo.code, false, true);
    }
  }, [user?.id]);

  if (loading) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center py-12 px-4 text-center space-y-4">
        <h1 className="text-2xl sm:text-4xl font-black text-zinc-950 dark:text-white tracking-tight">
          {isAr ? `خطط وأسعار باقات ${brandName}` : `${brandName} Subscription Plans & Pricing`}
        </h1>
        <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
      </div>
    );
  }

  if (!localConfig) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center p-6 text-center space-y-4 font-bold text-zinc-900 dark:text-white">
        <h1 className="text-xl sm:text-2xl font-black">
          {isAr ? `خطط وأسعار باقات ${brandName}` : `${brandName} Subscription Plans & Pricing`}
        </h1>
        <p>{isAr ? "تعذر تحميل الخطط الآن. أعد تحميل الصفحة للمحاولة مجددًا." : "Plans are temporarily unavailable. Please reload and try again."}</p>
      </div>
    );
  }

  if (!localConfig.enabled) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-6">
        <div className="max-w-xl w-full border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-8 text-center space-y-4 shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_#10b981]">
          <div className="flex justify-center">
            <div className="h-16 w-16 border-4 border-black dark:border-white bg-emerald-500 text-white flex items-center justify-center shadow-[3px_3px_0px_rgba(0,0,0,1)]">
              <Rocket className="h-8 w-8" />
            </div>
          </div>
          <h1 className="text-3xl font-black text-black dark:text-white">
            {isAr ? "المنصة مجانية حاليًا" : "The platform is currently free"}
          </h1>
          <p className="text-zinc-600 dark:text-zinc-300 font-bold leading-relaxed">
            {isAr
              ? "نحن في فترة تجريبية مفتوحة. جميع المزايا متاحة بدون أي رسوم. سنعلن عن خطة الاشتراك المدفوع قريبًا."
              : "We are in an open preview period. All features are available with no charge. Our paid subscription plan will be announced soon."}
          </p>
        </div>
      </div>
    );
  }

  const monthlyDiscount = localConfig?.plans?.find((item: any) => item.id === "pro")?.discount || null;
  const monthlyPrice = Number(monthlyDiscount?.original_amount_egp ?? localConfig?.plans?.find((item: any) => item.id === "pro")?.amount_egp ?? 150);
  const paidPlans = [
    { id: "pro", name_ar: "شهر واحد", name_en: "1 Month", days: 30, amount_egp: 150, badge: null, isLifetime: false },
    { id: "pro_6m", name_ar: "6 شهور", name_en: "6 Months", days: 180, amount_egp: 750, badge: isAr ? "الأكثر طلباً ⭐" : "Most Popular ⭐", isLifetime: false },
    { id: "pro_1y", name_ar: "سنة كاملة", name_en: "1 Year", days: 365, amount_egp: 1350, badge: isAr ? "أكبر توفير 💎" : "Max Value 💎", isLifetime: false },
    {
      id: "chat_only",
      name_ar: "الشات الذكي فقط",
      name_en: "AI Chat Only",
      days: 30,
      amount_egp: 100,
      badge: null,
      isLifetime: false,
    },
    {
      id: "vip_only",
      name_ar: "رادار تليجرام VIP فقط",
      name_en: "VIP Telegram Radar Only",
      days: 30,
      amount_egp: 100,
      badge: null,
      isLifetime: false,
    },
    {
      id: "lifetime",
      name_ar: "مدى الحياة (VIP)",
      name_en: "Lifetime VIP",
      days: 36500,
      amount_egp: 2250,
      badge: isAr
        ? (lifetimeRemaining > 0 ? `حصري لـ ${lifetimeRemaining} مقعداً 🔥` : "اكتملت المقاعد ❌")
        : (lifetimeRemaining > 0 ? `${lifetimeRemaining} Spots Left 🔥` : "Sold Out ❌"),
      isLifetime: true,
    },
  ].map((plan) => {
    const configured = localConfig?.plans?.find((item: any) => item.id === plan.id);
    const hasConfiguredAmount = configured?.amount_egp != null && Number.isFinite(Number(configured.amount_egp));
    let amount = hasConfiguredAmount ? Number(configured.amount_egp) : plan.amount_egp;
    let originalAmount: number | null = configured?.discount?.original_amount_egp
      ? Number(configured.discount.original_amount_egp)
      : null;
    if (!hasConfiguredAmount) {
      if (plan.id === "pro") {
        if (isGrandfathered) {
          amount = 50;
          originalAmount = monthlyPrice || 150;
        } else if (isGrandfathered100) {
          amount = 100;
          originalAmount = monthlyPrice || 150;
        } else if (!foundersIsOpen) {
          amount = monthlyPrice || 150;
          originalAmount = null;
        } else {
          amount = 100;
          originalAmount = monthlyPrice || 150;
        }
      } else if (plan.id === "pro_6m") {
        const hasFounder6m = foundersIsOpen || isGrandfathered || isGrandfathered100;
        amount = isGrandfathered ? 250 : hasFounder6m ? 500 : 750;
        originalAmount = hasFounder6m ? 750 : null;
      } else if (plan.id === "pro_1y") {
        const hasFounder1y = foundersIsOpen || isGrandfathered || isGrandfathered100;
        amount = isGrandfathered ? 450 : hasFounder1y ? 900 : 1350;
        originalAmount = hasFounder1y ? 1350 : null;
      }
    }
    const days = Number(configured?.days ?? plan.days);
    const monthlyEquivalent = plan.isLifetime ? null : Math.round((amount / days) * 30);
    const unbundledBase = (days / 30) * (monthlyPrice || 150);
    const savingsPct = plan.isLifetime
      ? 95
      : originalAmount && originalAmount > amount
      ? Math.round((1 - amount / originalAmount) * 100)
      : unbundledBase > amount
      ? Math.round((1 - amount / unbundledBase) * 100)
      : 0;
    return {
      ...plan,
      amount_egp: amount,
      original_amount_egp: originalAmount,
      discount: configured?.discount || (originalAmount ? { active: true, original_amount_egp: originalAmount } : null),
      days,
      monthlyEquivalent,
      savingsPct,
    };
  });

  const annualPlan = paidPlans.find((p) => p.id === "pro_1y");
  const regular1yEgp = Number(
    annualPlan?.original_amount_egp ?? (annualPlan?.amount_egp && annualPlan.amount_egp > 1000 ? annualPlan.amount_egp : 1350)
  );
  const chatOnlyPlan = paidPlans.find((p) => p.id === "chat_only")!;
  const vipOnlyPlan = paidPlans.find((p) => p.id === "vip_only")!;
  const breakevenMonths = lifetimeBreakevenMonths(2250, monthlyPrice || 150);

  const b2bPlans = [
    {
      id: "b2b_starter",
      name_ar: "باقة القنوات الناشئة (Starter B2B)",
      name_en: "Channel Starter (B2B)",
      amount_egp: 1000,
      original_amount_egp: null as number | null,
      monthlyEquivalent: null as number | null,
      savingsPct: 0,
      badge: null as string | null,
      isLifetime: false,
      days: 30,
      daily_limit: 50,
      max_members: "حتى 150 عضو",
      monthly_est: "1,100",
      badge_ar: "للقنوات حتى 150 عضو",
      badge_en: "Up to 150 members",
      tag: "STARTER",
      border_class: "border-black dark:border-white",
      shadow_class: "shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_#10b981]",
      btn_class: "bg-zinc-900 hover:bg-black text-white dark:bg-white dark:text-black dark:hover:bg-zinc-100",
      is_featured: false,
      features: [
        { text: isAr ? "ترخيص وربط جروب تليجرام واحد" : "License 1 Telegram VIP Group", icon: <Check className="w-3.5 h-3.5" /> },
        { text: isAr ? "كوتة 50 استفسار يومياً (~1,100 استفسار شهرياً)" : "50 queries daily (~1,100/mo)", icon: <Zap className="w-3.5 h-3.5 text-emerald-500" /> },
        { text: isAr ? "توقيع مخصص باسم قناتك ومجتمعك أسفل كل تحليل" : "Custom signature footer on every bot reply", icon: <Sparkles className="w-3.5 h-3.5 text-amber-500" /> },
        {
          text: isAr
            ? isSaudi
              ? "تحليل فني ومالي لجميع أسهم السوق السعودي (تداول TASI) والذهب والفضة بلحظة"
              : isUae
              ? "تحليل فني ومالي لجميع أسهم الإمارات (دبي DFM وأبوظبي ADX) والذهب والفضة بلحظة"
              : isQatar
              ? "تحليل فني ومالي لجميع أسهم بورصة قطر (QSE) والذهب والفضة بلحظة"
              : "تحليل فني ومالي لجميع أسهم البورصة المصرية (EGX) والذهب والفضة بلحظة"
            : isSaudi
            ? "Instant AI analysis for all Saudi TASI stocks, Gold & Silver"
            : isUae
            ? "Instant AI analysis for all UAE (DFM & ADX) stocks, Gold & Silver"
            : isQatar
            ? "Instant AI analysis for all Qatar (QSE) stocks, Gold & Silver"
            : "Instant AI analysis for all 280+ EGX stocks, Gold & Silver",
          icon: <BarChart3 className="w-3.5 h-3.5" />,
        },
        { text: isAr ? "مانع التكرار والسبام الذكي (كولد داون 90 ثانية للعضو)" : "Anti-spam protection & 90s member cooldown", icon: <ShieldCheck className="w-3.5 h-3.5" /> },
        { text: isAr ? "لوحة تحكم لمتابعة الاستهلاك وتعديل التوقيع" : "Dashboard for usage tracking & signature editing", icon: <Check className="w-3.5 h-3.5" /> },
      ],
    },
    {
      id: "b2b_pro",
      name_ar: "باقة المحللين المحترفين (Pro VIP B2B)",
      name_en: "Channel Pro VIP (B2B)",
      amount_egp: 1500,
      original_amount_egp: null as number | null,
      monthlyEquivalent: null as number | null,
      savingsPct: 0,
      badge: null as string | null,
      isLifetime: false,
      days: 30,
      daily_limit: 120,
      max_members: "حتى 500 عضو",
      monthly_est: "2,640",
      badge_ar: "الأكثر طلباً 🔥 · حتى 500 عضو",
      badge_en: "Most Popular 🔥 · Up to 500 members",
      tag: "PRO VIP",
      border_class: "border-emerald-500",
      shadow_class: "shadow-[8px_8px_0px_#10b981]",
      btn_class: "bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-black",
      is_featured: true,
      features: [
        { text: isAr ? "كافة ميزات باقة Starter" : "All features in Starter Tier", icon: <Check className="w-3.5 h-3.5" /> },
        { text: isAr ? "كوتة مضاعفة: 120 استفسار يومياً (~2,640 استفسار شهرياً)" : "Doubled quota: 120 queries daily (~2,640/mo)", icon: <Zap className="w-3.5 h-3.5 text-emerald-500" /> },
        { text: isAr ? "سرعة استجابة فائقة وأولوية معالجة في ساعات التداول" : "Trading hours priority & sub-second response", icon: <Flame className="w-3.5 h-3.5 text-amber-500" /> },
        { text: isAr ? "تحديث وتخصيص نص التوقيع في أي وقت من لوحة التحكم" : "Edit custom signature anytime from dashboard", icon: <Sparkles className="w-3.5 h-3.5 text-yellow-500" /> },
        { text: isAr ? "دعم فني وتفعيل مخصص ومباشر عبر واتساب" : "Dedicated WhatsApp VIP support desk", icon: <ShieldCheck className="w-3.5 h-3.5" /> },
      ],
    },
    {
      id: "b2b_enterprise",
      name_ar: "باقة كبار المحللين والشركات (Enterprise B2B)",
      name_en: "Enterprise & Multi-Group",
      amount_egp: 2500,
      original_amount_egp: null as number | null,
      monthlyEquivalent: null as number | null,
      savingsPct: 0,
      badge: null as string | null,
      isLifetime: false,
      days: 30,
      daily_limit: 250,
      max_members: "حتى 1,500 عضو أو جروبين",
      monthly_est: "5,500",
      badge_ar: "للمجموعات الكبرى 💎 · حتى 1,500 عضو",
      badge_en: "Enterprise 💎 · Up to 1,500 members",
      tag: "ENTERPRISE",
      border_class: "border-purple-600 dark:border-purple-400",
      shadow_class: "shadow-[8px_8px_0px_#7c3aed] dark:shadow-[8px_8px_0px_#a855f7]",
      btn_class: "bg-[#FFE600] hover:bg-yellow-400 text-black font-black",
      is_featured: false,
      features: [
        { text: isAr ? "كوتة استفسارات ضخمة: 250 استفسار يومياً (~5,500 شهرياً)" : "Heavy quota: 250 queries daily (~5,500/mo)", icon: <Zap className="w-3.5 h-3.5 text-emerald-500" /> },
        { text: isAr ? "إمكانية ترخيص جروبين تليجرام منفصلين بنفس الاشتراك" : "License up to 2 separate Telegram VIP groups", icon: <Crown className="w-3.5 h-3.5 text-yellow-400" /> },
        { text: isAr ? "توقيع مخصص لكل جروب على حدة" : "Separate custom signature branding per group", icon: <Sparkles className="w-3.5 h-3.5 text-amber-500" /> },
        { text: isAr ? "إحصائيات تفصيلية لأكثر الأسهم طلباً داخل الجروب" : "Deep analytics on most queried stocks in community", icon: <BarChart3 className="w-3.5 h-3.5" /> },
        { text: isAr ? "خط تواصل ودعم مباشر مخصص لكبار المحللين والمديرين" : "Direct VIP line for fund managers and analysts", icon: <ShieldCheck className="w-3.5 h-3.5" /> },
      ],
    },
  ].map((plan) => {
    const configured = localConfig?.b2b_plans?.find((item: any) => item.id === plan.id);
    if (configured?.amount_egp != null && Number.isFinite(Number(configured.amount_egp))) {
      return { ...plan, amount_egp: Number(configured.amount_egp), days: Number(configured.days ?? plan.days) };
    }
    return plan;
  });

  const allAvailablePlans = [...paidPlans, ...b2bPlans];
  const proMonthlyPlan = paidPlans[0];
  const regularProMonthly = monthlyPrice || 150;
  const proMonthlyBase = proMonthlyPlan?.amount_egp || regularProMonthly;
  const selectedEntry = getDurationScheduleEntry(selectedMonths);
  const chatDurationPricing = computeDurationPlanPricing(chatOnlyPlan.amount_egp, selectedMonths);
  const vipDurationPricing = computeDurationPlanPricing(vipOnlyPlan.amount_egp, selectedMonths);
  const proDurationPricing = computeDurationPlanPricing(proMonthlyBase, selectedMonths);
  const proRegularDurationPricing = computeDurationPlanPricing(regularProMonthly, selectedMonths);
  const isChatHeroForGcc = isGccChatOnly && !(isGrandfathered || isGrandfathered100 || foundersIsOpen);
  const isLifetimeActive = activePlanId === "lifetime" || activePlanId === "pro_lifetime";
  const isFullProActive = activePlanId === "pro" || activePlanId === "pro_renewal" || activePlanId === "pro_6m" || activePlanId === "pro_1y";
  const isChatOnlyActive = activePlanId === "chat_only";
  const isVipOnlyActive = activePlanId === "vip_only";

  const normalizedSelectedPlanId =
    selectedPlan === "pro_6m" || selectedPlan === "pro_1y" ? "pro" : selectedPlan;
  const rawSelectedPlanDetails =
    allAvailablePlans.find((plan: any) => plan.id === normalizedSelectedPlanId) || proMonthlyPlan;
  const selectedPlanDetails = DURATION_SLIDER_PLANS.has(rawSelectedPlanDetails.id)
    ? (() => {
        const dp =
          rawSelectedPlanDetails.id === "chat_only"
            ? chatDurationPricing
            : rawSelectedPlanDetails.id === "vip_only"
            ? vipDurationPricing
            : proDurationPricing;
        return {
          ...rawSelectedPlanDetails,
          name_ar: formatDurationLabel(dp.months, true),
          name_en: formatDurationLabel(dp.months, false),
          amount_egp: dp.totalEgp,
          days: dp.days,
          monthlyEquivalent: dp.effectiveMonthlyEgp,
          savingsPct: dp.discountPct,
        };
      })()
    : rawSelectedPlanDetails;
  const promoPriceForPlan = (baseEgp: number) => {
    if (!appliedPromo || appliedPromo.discount_percent <= 0) {
      return { discountEgp: 0, finalEgp: baseEgp };
    }
    const discountEgp = Math.min(
      Math.max(0, baseEgp - 20),
      Math.round((baseEgp * appliedPromo.discount_percent) / 100)
    );
    return { discountEgp, finalEgp: Math.max(20, baseEgp - discountEgp) };
  };

  const baseProPrice = selectedPlanDetails?.amount_egp ?? (paidPlans[0]?.amount_egp || 100);
  const { discountEgp: promoDiscountAmount, finalEgp: proPrice } = promoPriceForPlan(baseProPrice);
  const checkoutPricing = computeCheckoutPricing(baseProPrice, appliedPromo?.discount_percent || 0, market);
  const proDisplayAmount = checkoutPricing.finalDisplay;
  const promoDiscountDisplay = checkoutPricing.discountDisplay;
  const easyKashChargeEgp = checkoutPricing.chargeEgp;
  const freeLimits = localConfig.limits?.free || { signal_delay_days: 15, chat_messages_per_month: 10, portfolio_stocks: 5 };
  const proLimits = localConfig.limits?.pro || { chat_messages_per_month: 350, portfolio_stocks: 15 };
  const freeFeatures = [
    ...(isGccChatOnly
      ? []
      : [
          { icon: <Zap className="w-4 h-4" />, text: isAr ? `تأخير الإشارات والمؤشرات ${freeLimits.signal_delay_days} يوماً (أرشيف تاريخي فقط)` : `Technical signals delayed ${freeLimits.signal_delay_days} days (historical archive only)`, included: true },
        ]),
    { icon: <MessageSquare className="w-4 h-4" />, text: isAr ? "10 استفسارات تحليلية مجانية بالشات (مرة واحدة لكل إيميل — لا تتجدد شهرياً)" : "10 free AI analytical queries (one-time per email — non-renewing)", included: true },
    { icon: <BarChart3 className="w-4 h-4" />, text: isAr ? `حفظ حتى ${freeLimits.portfolio_stocks} أسهم في محفظتك المتابعة` : `Up to ${freeLimits.portfolio_stocks} tracked portfolio stocks`, included: true },
    ...(isGccChatOnly
      ? []
      : [
          { icon: <Zap className="w-4 h-4" />, text: isAr ? "الماسح الفني والمؤشرات اللحظية 🔒 PRO" : "Live Technical Scanner & Signals 🔒 PRO", included: false },
          { icon: <BellRing className="w-4 h-4" />, text: isAr ? "تنبيهات ورادار تليجرام VIP الفوري 🔒 PRO" : "Instant Mobile Telegram VIP Radar 🔒 PRO", included: false },
        ]),
    { icon: <Sparkles className="w-4 h-4" />, text: isAr ? "تحليل صور المحفظة والشارت (Vision AI) 📸 PRO" : "Vision AI Portfolio Screenshot Analysis 📸 PRO", included: false },
  ];

  const chatOnlyFeatures = [
    {
      icon: <MessageSquare className="w-4 h-4 text-sky-500" />,
      text: isGccChatOnly
        ? (isAr ? "350 استفساراً تحليلياً بالذكاء الاصطناعي شهرياً عبر شات الموقع (الإمارات، قطر، السعودية، مصر، الذهب والفضة)" : "350 AI analytical queries / month via web chat (UAE, Qatar, Saudi, Egypt, Gold & Silver)")
        : (isAr ? "350 استفساراً تحليلياً بالذكاء الاصطناعي شهرياً عبر الموقع وبوت تليجرام الخاص" : "350 AI analytical queries / month across web & private Telegram bot"),
      included: true,
    },
    { icon: <Sparkles className="w-4 h-4 text-amber-500" />, text: isAr ? "تحليل صور المحفظة والشارت (Vision AI) 📸 لقراءة الدعوم والمقاومات" : "Vision AI Screenshot Analysis 📸 for support & resistance levels", included: true },
    ...(isGccChatOnly
      ? [
          { icon: <Clock className="w-4 h-4 text-indigo-500" />, text: isAr ? `متابعة يومية للمؤشرات الفنية والدعوم والمقاومات لأسهم ${isUae ? "دبي وأبوظبي" : "بورصة قطر"} والذهب والفضة` : `Daily updated technical indicators & key levels for ${isUae ? "UAE (DFM & ADX)" : "Qatar (QSE)"}, Gold & Silver`, included: true },
          { icon: <BarChart3 className="w-4 h-4 text-emerald-500" />, text: isAr ? `متابعة حتى ${proLimits.portfolio_stocks} سهماً في محفظتك وتحليلها بالذكاء الاصطناعي` : `Track up to ${proLimits.portfolio_stocks} stocks in your AI portfolio`, included: true },
          { icon: <X className="w-4 h-4 text-zinc-400" />, text: isAr ? "لا تشمل قنوات تليجرام VIP للسوق السعودي (TASI) والمصري (EGX)" : "Excludes Saudi TASI & Egypt EGX VIP Telegram channels", included: false },
        ]
      : [
          { icon: <Clock className="w-4 h-4 text-indigo-500" />, text: isAr ? "أتمتة حتى 5 استفسارات فنية مجدولة يومياً على تليجرام" : "Up to 5 daily scheduled AI analyses on Telegram", included: true },
          { icon: <BarChart3 className="w-4 h-4 text-emerald-500" />, text: isAr ? `متابعة حتى ${proLimits.portfolio_stocks} سهماً في محفظتك + إزالة تأخير أدوات الموقع` : `Track up to ${proLimits.portfolio_stocks} stocks + zero site delay`, included: true },
          { icon: <X className="w-4 h-4 text-zinc-400" />, text: isAr ? "لا تشمل دخول قناة رادار تليجرام VIP (متوفرة في الشاملة)" : "Excludes VIP Telegram Radar channel (included in Full Bundle)", included: false },
        ]),
  ];

  const vipOnlyFeatures = [
    { icon: <BellRing className="w-4 h-4 text-amber-500 fill-amber-500" />, text: isAr ? "دخول فوري لقناة تليجرام VIP الخاصة للتنبيهات الفنية الآلية" : "Instant access to Private VIP Telegram Technical Radar Channel", included: true },
    { icon: <Activity className="w-4 h-4 text-emerald-500" />, text: isAr ? "رصد آلي لاختراقات السيولة غير الطبيعية ونماذج التجميع الكمي" : "Automated liquidity breakouts & quantitative accumulation radar", included: true },
    { icon: <Zap className="w-4 h-4 text-emerald-500" />, text: isAr ? (isSaudi ? "يدعم السوق السعودي (تداول TASI) والبورصة المصرية (EGX)" : "يدعم البورصة المصرية (EGX) والسوق السعودي (TASI)") : "Covers both EGX (Egypt) & TASI (Saudi) VIP radar channels", included: true },
    { icon: <ShieldCheck className="w-4 h-4 text-emerald-500" />, text: isAr ? "تنبيهات الإفصاحات الرسمية والمؤشرات الفنية في الماسح بدون تأخير 15 يوماً" : "Real-time disclosures & unmasked scanner signals (no 15-day delay)", included: true },
    { icon: <X className="w-4 h-4 text-zinc-400" />, text: isAr ? "لا تشمل كوتة 350 رسالة للشات الذكي (متوفرة في الشاملة)" : "Excludes 350/mo AI Chat quota (included in Full Bundle)", included: false },
  ];

  const proFeatures = isGccChatOnly
    ? [
        {
          icon: <MessageSquare className="w-4 h-4 text-sky-500" />,
          text: isAr
            ? `كل مزايا باقة ${brandName} AI Pro (${formatPrice(100)}/ش) بالكامل: 350 استفساراً + Vision AI + محفظة ${proLimits.portfolio_stocks} سهماً`
            : `Full ${brandName} AI Pro perks (${formatPrice(100)}/mo): 350 queries + Vision AI + ${proLimits.portfolio_stocks}-stock portfolio`,
          included: true,
        },
        {
          icon: <BellRing className="w-4 h-4 text-amber-500 fill-amber-500" />,
          text: isAr
            ? "دخول فوري لقنوات تليجرام VIP الخاصة بالسوق السعودي (تداول TASI) والبورصة المصرية (EGX)"
            : "Instant access to Private VIP Telegram Channels for Saudi (TASI) & Egypt (EGX)",
          included: true,
        },
        {
          icon: <Zap className="w-4 h-4 text-emerald-500" />,
          text: isAr
            ? "رادار السيولة والاختراقات اللحظي وإزالة تأخير 15 يوماً لماسح السعودية ومصر"
            : "Real-time liquidity radar & zero 15-day delay on Saudi TASI & Egypt EGX scanners",
          included: true,
        },
        {
          icon: <Clock className="w-4 h-4 text-indigo-500" />,
          text: isAr
            ? "أتمتة حتى 5 تحليلات فنية مجدولة يومياً عبر بوت تليجرام الخاص"
            : "Up to 5 daily scheduled technical analyses via private Telegram bot",
          included: true,
        },
      ]
    : [
        {
          icon: <MessageSquare className="w-4 h-4 text-sky-500" />,
          text: isAr
            ? "تشمل باقة الشات الذكي بالكامل: 350 استفساراً تحليلياً/شهر + تحليل الصور Vision AI + 5 أتمتات يومية"
            : "Full AI Chat included: 350 analytical queries/mo + Vision AI + 5 daily automations",
          included: true,
        },
        {
          icon: <BellRing className="w-4 h-4 text-amber-500 fill-amber-500" />,
          text: isAr
            ? isSaudi
              ? "تشمل قناة تليجرام VIP للسوق السعودي (TASI) ورادار السيولة اللحظي بالكامل"
              : "تشمل قناة تليجرام VIP الفورية ورادار السيولة والاختراقات بالكامل"
            : isSaudi
            ? "Full Saudi TASI VIP Telegram Channel & real-time liquidity radar included"
            : "Full VIP Telegram Channel & real-time liquidity radar included",
          included: true,
        },
        {
          icon: <Zap className="w-4 h-4 text-emerald-500" />,
          text: isAr
            ? isSaudi
              ? "إزالة تأخير الـ 15 يوماً: كافة إشارات الأنظمة الثلاثة والماسح الفني للسوق السعودي بدون تشفير"
              : "إزالة تأخير الـ 15 يوماً: كافة الإشارات الفنية السريعة ومؤشرات الزخم بدون تشفير"
            : "Zero 15-day delay: all real-time technical scanner models & momentum signals unmasked",
          included: true,
        },
        {
          icon: <BarChart3 className="w-4 h-4 text-emerald-500" />,
          text: isAr
            ? `محفظة تداول موسعة حتى ${proLimits.portfolio_stocks} سهماً نشطاً مع متابعة المستويات الفنية`
            : `Expanded portfolio tracker up to ${proLimits.portfolio_stocks} active stocks`,
          included: true,
        },
        {
          icon: <ShieldCheck className="w-4 h-4 text-emerald-500" />,
          text: isAr
            ? `توفير فوري ${formatPrice(50)} شهرياً مقارنة بشراء الباقتين منفصلتين`
            : "Save instantly vs buying AI Chat & VIP Radar separately",
          included: true,
        },
      ];

  const lifetimeFeatures = isGccChatOnly
    ? [
        { icon: <Crown className="w-4 h-4 text-purple-600 dark:text-yellow-400" />, text: isAr ? "صلاحية كاملة مدى الحياة للأبد (36,500 يوم بدون أي تجديد أو اشتراك متكرر)" : "Permanent lifetime access (36,500 days, zero recurring renewals)", included: true },
        { icon: <MessageSquare className="w-4 h-4 text-emerald-500" />, text: isAr ? "350 استفساراً بالشات شهرياً + Vision AI تتجدد تلقائياً للأبد لكل الأسواق والذهب والفضة" : "350 AI chat queries/mo + Vision AI renewed monthly forever across all markets & Gold/Silver", included: true },
        { icon: <BellRing className="w-4 h-4 text-emerald-500 fill-emerald-500" />, text: isAr ? "تشمل قنوات تليجرام VIP للسوق السعودي (TASI) والمصري (EGX) وأتمتة تليجرام للأبد" : "Includes Saudi TASI & Egypt EGX VIP Telegram channels + Telegram automations forever", included: true },
      ]
    : [
        { icon: <Crown className="w-4 h-4 text-purple-600 dark:text-yellow-400" />, text: isAr ? "صلاحية كاملة مدى الحياة للأبد (36,500 يوم بدون أي تجديد أو اشتراك متكرر)" : "Permanent lifetime access (never expires, zero recurring renewals)", included: true },
        {
          icon: <Zap className="w-4 h-4 text-emerald-500" />,
          text: isAr
            ? isSaudi
              ? "كافة مؤشرات أنظمة التداول الثلاثة والماسح الفني للسوق السعودي للأبد"
              : "كافة مؤشرات المسح الكمي والإشارات الفنية اللحظية للأبد"
            : isSaudi
            ? "Full 3-Trading-Systems & Live TASI Scanner Signals forever"
            : "Full Live Technical Scanner Signals forever",
          included: true,
        },
        {
          icon: <BellRing className="w-4 h-4 text-emerald-500 fill-emerald-500" />,
          text: isAr
            ? isSaudi
              ? "قناة التليجرام VIP للسوق السعودي ورادار السيولة الفوري للأبد"
              : "قناة ورادار تليجرام VIP الفوري بكافة مراحله للأبد"
            : isSaudi
            ? "Saudi TASI VIP Telegram Channel & Alerts forever"
            : "Live Telegram VIP Channel & Alerts forever",
          included: true,
        },
        { icon: <MessageSquare className="w-4 h-4 text-emerald-500" />, text: isAr ? "350 استفساراً تحليلياً بالشات شهرياً تتجدد تلقائياً للأبد" : "350 AI analytical queries refreshed monthly for life", included: true },
        { icon: <Sparkles className="w-4 h-4 text-emerald-500" />, text: isAr ? "تحليل صور المحفظة والشارت (Vision AI) 📸 + أتمتة تليجرام اليومية للأبد" : "Vision AI Screenshot Analysis 📸 + Scheduled Telegram Automations for life", included: true },
        { icon: <Sparkles className="w-4 h-4 text-yellow-500" />, text: isAr ? "أولوية قصوى ودخول مجاني لكافة التحديثات والميزات المستقبلية" : "VIP priority for all future updates and releases", included: true },
      ];

  // ── STEP 3: SUBMITTED / PAYMENT RESULT ─────────────────────────────────────
  if (step === "submitted") {
    const isB2bSubmitted = Boolean(selectedPlanDetails?.id?.startsWith("b2b_"));
    const isLifetimeSubmitted = selectedPlanDetails?.id === "lifetime";
    const isChatOnlySubmitted = selectedPlanDetails?.id === "chat_only";
    const isVipOnlySubmitted = selectedPlanDetails?.id === "vip_only";
    const approvedBadgeText = isB2bSubmitted
      ? (isAr ? "تم تفعيل رخصة القنوات (B2B) 💼" : "B2B License Activated 💼")
      : isLifetimeSubmitted
      ? (isAr ? "تم تفعيل باقة مدى الحياة (LIFETIME VIP) 👑" : "Lifetime VIP Activated 👑")
      : isChatOnlySubmitted
      ? (isAr ? "تم تفعيل باقة الشات الذكي 🤖" : "AI Chat Activated 🤖")
      : isVipOnlySubmitted
      ? (isAr ? "تم تفعيل رادار تليجرام VIP 📡" : "VIP Radar Activated 📡")
      : (isAr ? "تم التفعيل بنجاح" : "Pro Activated");
    const approvedTitleText = isB2bSubmitted
      ? (isAr ? `أهلاً بك في شركاء ${brandName} (B2B)! 💼🎉` : `Welcome to ${brandName} B2B Partners! 💼🎉`)
      : isLifetimeSubmitted
      ? (isAr ? `أهلاً بك في نخبة ${brandName} مدى الحياة! 👑🎉` : `Welcome to ${brandName} Lifetime VIP! 👑🎉`)
      : isChatOnlySubmitted
      ? (isAr ? `أهلاً بك في باقة الشات الذكي على ${brandName}! 🤖🎉` : `Welcome to ${brandName} AI Chat! 🤖🎉`)
      : isVipOnlySubmitted
      ? (isAr ? `أهلاً بك في رادار تليجرام VIP على ${brandName}! 📡🎉` : `Welcome to ${brandName} VIP Radar! 📡🎉`)
      : (isAr ? `أهلاً بك في ${brandName} Pro! 🎉` : `Welcome to ${brandName} Pro! 🎉`);
    const approvedDays = Number(orderDurationDays || selectedPlanDetails?.days || 30);
    const approvedDescText = isB2bSubmitted
      ? (isAr
          ? `تم تفعيل باقة القنوات (${selectedPlanDetails?.name_ar || selectedPlanDetails?.id}) بنجاح لمدة ${approvedDays} يوماً! يمكنك الآن ربط البوت بجروب التليجرام وتخصيص التوقيع فوراً من لوحة تحكم القنوات.`
          : `Your ${selectedPlanDetails?.name_en || selectedPlanDetails?.id} license is active for ${approvedDays} days! Connect your Telegram group and configure your custom signature from the B2B dashboard.`)
      : isLifetimeSubmitted
      ? (isAr
          ? "تم تفعيل اشتراكك الدائم في باقة مدى الحياة (Lifetime VIP) بنجاح للأبد! حسابك نشط الآن بكامل الصلاحيات مدى الحياة وبدون أي تجديدات شهرية."
          : "Your Lifetime VIP subscription is now active forever! Full access granted for life with zero recurring renewals.")
      : isChatOnlySubmitted
      ? (isGccChatOnly
          ? (isAr
              ? `تم تفعيل باقة الشات الذكي (350 استفساراً تحليلياً/شهر + تحليل صور المحفظة Vision AI + محفظة متابعة موسعة) بنجاح لمدة ${approvedDays} يوماً.`
              : `Your AI Chat plan (350 consultations/mo + Vision AI + expanded portfolio tracker) is now active for ${approvedDays} days.`)
          : (isAr
              ? `تم تفعيل باقة الشات الذكي (350 استفساراً تحليلياً/شهر + تحليل صور المحفظة Vision AI + أتمتة تليجرام) بنجاح لمدة ${approvedDays} يوماً.`
              : `Your AI Chat plan (350 consultations/mo + Vision AI + Telegram automations) is now active for ${approvedDays} days.`))
      : isVipOnlySubmitted
      ? (isAr
          ? `تم تفعيل باقة رادار تليجرام VIP الخاصة لمدة ${approvedDays} يوماً! استخدم الرابط بالأسفل للدخول إلى قناة التنبيهات الفنية الفورية.`
          : `Your VIP Telegram Radar plan is active for ${approvedDays} days! Use the button below to join your private VIP channel.`)
      : (isAr
          ? `تم تأكيد اشتراكك في الباقة الشاملة Pro لمدة ${approvedDays} يوماً بنجاح. حسابك نشط الآن بكامل الصلاحيات!`
          : `Your Pro plan is now active for ${approvedDays} days with full benefits!`);
    const waFailureMsg = encodeURIComponent(
      isGulfPricing || selectedDialCode !== "+20"
        ? `مرحباً، واجهت مشكلة في الدفع الدولي على ${brandName} وأريد المساعدة في إتمام الاشتراك`
        : "مرحباً، واجهت مشكلة في الدفع عبر EasyKash على EGX BOTS وأريد المساعدة"
    );

    return (
      <div className="min-h-[75vh] flex items-center justify-center py-12 px-4" dir={isAr ? "rtl" : "ltr"}>
        <div className="max-w-xl w-full border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 sm:p-8 space-y-6 text-center shadow-[8px_8px_0px_rgba(0,0,0,1)] dark:shadow-[8px_8px_0px_#10b981]">
          {/* Status Icon */}
          <div className="flex justify-center">
            <div
              className={`h-20 w-20 border-4 border-black dark:border-white flex items-center justify-center shadow-[4px_4px_0px_rgba(0,0,0,1)] ${
                orderStatus === "failed"
                  ? "bg-red-500 text-white"
                  : orderStatus === "approved"
                  ? "bg-emerald-500 text-white"
                  : "bg-amber-400 text-zinc-950 animate-pulse"
              }`}
            >
              {orderStatus === "failed" ? (
                <X className="h-10 w-10" />
              ) : orderStatus === "approved" ? (
                <CheckCircle2 className="h-10 w-10" />
              ) : (
                <Clock className="h-10 w-10 animate-spin" />
              )}
            </div>
          </div>

          {/* Heading */}
          <div className="space-y-2">
            <span
              className={`inline-block border-2 border-black dark:border-white px-3 py-1 text-xs font-black uppercase tracking-widest ${
                orderStatus === "failed"
                  ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                  : orderStatus === "approved"
                  ? isLifetimeSubmitted
                    ? "bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300"
                    : "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                  : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
              }`}
            >
              {orderStatus === "failed"
                ? isAr ? "فشلت العملية" : "Payment Incomplete"
                : orderStatus === "approved"
                ? approvedBadgeText
                : isAr ? "جاري التحقق من الدفع" : "Verifying Payment"}
            </span>
            <h1 className="text-2xl sm:text-3xl font-black text-zinc-950 dark:text-white">
              {orderStatus === "failed"
                ? isAr ? "لم تكتمل عملية الدفع" : "Payment was not completed"
                : orderStatus === "approved"
                ? approvedTitleText
                : isAr ? "في انتظار إشعار تأكيد الدفع ⏳" : "Awaiting payment confirmation ⏳"}
            </h1>
            <p className="text-sm font-semibold text-zinc-600 dark:text-zinc-300 leading-relaxed max-w-md mx-auto">
              {orderStatus === "failed"
                ? isAr
                  ? "لم نتلقَ تأكيد إتمام الدفع من EasyKash. يمكنك المحاولة مجددًا أو التواصل معنا للمساعدة."
                  : "We didn't receive payment confirmation from EasyKash. You can try again or reach out to our team."
                : orderStatus === "approved"
                ? approvedDescText
                : isAr
                ? "تم استلام طلبك وجاري انتظار تأكيد السداد من EasyKash تلقائياً. الصفحة ستُحدّث الحالة فور وصول الإشعار."
                : "Checkout initiated. We are listening for EasyKash confirmation and will update automatically."}
            </p>
          </div>

          {/* Order Reference Box */}
          {localOrder && (
            <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900 p-3.5 flex items-center justify-between gap-3 text-start">
              <div>
                <span className="text-[10px] font-black uppercase tracking-wider text-zinc-500 block">
                  {isAr ? "رقم مرجع الطلب (Order ID)" : "Order Reference"}
                </span>
                <span className="font-mono font-bold text-xs text-zinc-900 dark:text-zinc-100 break-all">
                  {localOrder}
                </span>
              </div>
              <button
                type="button"
                onClick={copyOrderId}
                className="shrink-0 p-2 border-2 border-black dark:border-white bg-white dark:bg-zinc-800 hover:bg-zinc-100 text-xs font-bold"
                title={isAr ? "نسخ" : "Copy"}
              >
                {copiedOrder ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
          )}

          {/* Approved Actions */}
          {orderStatus === "approved" && (
            <div className="space-y-4 pt-2">
              {subscriptionEnd && (
                <p className="text-xs font-black text-emerald-600 dark:text-emerald-400">
                  {isLifetimeSubmitted
                    ? isAr
                      ? "مدة الاشتراك: مدى الحياة للأبد (اشتراك دائم) 👑"
                      : "Subscription Duration: Lifetime Forever 👑"
                    : isAr
                    ? `تاريخ انتهاء الاشتراك: ${new Date(subscriptionEnd).toLocaleDateString("ar-EG")}`
                    : `Valid until: ${new Date(subscriptionEnd).toLocaleDateString()}`}
                </p>
              )}
              {isB2bSubmitted ? (
                <Link
                  href={(b2bDashboardUrl || "/b2b/dashboard").replace(/^https?:\/\/[^/]+/, "") || "/b2b/dashboard"}
                  className="flex items-center justify-center gap-2 border-4 border-black dark:border-white bg-emerald-500 hover:bg-emerald-600 text-black font-black py-3.5 px-6 uppercase tracking-wider shadow-[4px_4px_0px_rgba(0,0,0,1)] hover:-translate-y-0.5 active:translate-y-0 transition-all text-sm"
                  prefetch={false}
                >
                  <ExternalLink className="w-4 h-4" />
                  {isAr ? "فتح لوحة تحكم القنوات (B2B) وتفعيل البوت" : "Open B2B Dashboard & Connect Bot"}
                </Link>
              ) : isChatOnlySubmitted ? (
                <Link
                  href="/chat"
                  className="flex items-center justify-center gap-2 border-4 border-black dark:border-white bg-sky-500 hover:bg-sky-400 text-black font-black py-3.5 px-6 uppercase tracking-wider shadow-[4px_4px_0px_rgba(0,0,0,1)] hover:-translate-y-0.5 active:translate-y-0 transition-all text-sm"
                  prefetch={false}
                >
                  <MessageSquare className="w-4 h-4" />
                  {isAr ? "ابدأ استخدام الشات الذكي الآن (350 استفساراً/شهر)" : "Start Using AI Chat Now (350/mo)"}
                </Link>
              ) : (isSaudi || isGccChatOnly) ? (
                <div className="space-y-2">
                  <a
                    href={telegramSaudiProUrl || SAUDI_VIP_TELEGRAM_WEB_URL}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-center gap-2 border-4 border-black dark:border-white bg-emerald-600 hover:bg-emerald-700 text-white font-black py-3.5 px-6 uppercase tracking-wider shadow-[4px_4px_0px_rgba(0,0,0,1)] hover:-translate-y-0.5 active:translate-y-0 transition-all text-sm"
                  >
                    <ExternalLink className="w-4 h-4" />
                    {isAr ? "انضم الآن إلى قناة TASI VIP على تليجرام" : "Join Saudi TASI VIP Telegram Channel"}
                  </a>
                  {telegramProUrl && (
                    <a
                      href={telegramProUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center justify-center gap-2 border-2 border-black dark:border-white bg-indigo-600 hover:bg-indigo-700 text-white font-black py-2.5 px-4 uppercase tracking-wider text-xs"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      {isAr ? "قناة VIP العامة والمصرية" : "Main & EGX VIP Channel"}
                    </a>
                  )}
                  {isGccChatOnly && (
                    <Link
                      href="/chat"
                      className="flex items-center justify-center gap-2 border-2 border-black dark:border-white bg-sky-500 hover:bg-sky-400 text-black font-black py-2.5 px-4 uppercase tracking-wider text-xs"
                      prefetch={false}
                    >
                      <MessageSquare className="w-3.5 h-3.5" />
                      {isAr ? "افتح الشات الذكي الآن (350 استفساراً/شهر)" : "Open AI Chat Now (350/mo)"}
                    </Link>
                  )}
                </div>
              ) : telegramProUrl ? (
                <a
                  href={telegramProUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-center gap-2 border-4 border-black dark:border-white bg-indigo-600 hover:bg-indigo-700 text-white font-black py-3.5 px-6 uppercase tracking-wider shadow-[4px_4px_0px_rgba(0,0,0,1)] hover:-translate-y-0.5 active:translate-y-0 transition-all text-sm"
                >
                  <ExternalLink className="w-4 h-4" />
                  {isAr ? "انضم الآن إلى قناة VIP على تليجرام" : "Join VIP Telegram Channel Now"}
                </a>
              ) : (
                <div className="p-3 border-2 border-amber-500 bg-amber-50 dark:bg-amber-950/40 text-xs font-bold text-amber-800 dark:text-amber-200">
                  {isAr ? "لم يتوفر رابط VIP بعد. ستجده في ملفك الشخصي؛ تواصل مع الدعم لو استمرت المشكلة." : "VIP invite is not ready yet. Check your profile or contact support if this persists."}
                </div>
              )}
              <button
                type="button"
                onClick={() => router.push(isB2bSubmitted ? "/b2b/dashboard" : "/profile")}
                className="w-full border-2 border-black dark:border-white bg-white dark:bg-zinc-900 py-3 text-xs font-black hover:bg-zinc-100 transition-all"
              >
                {isB2bSubmitted
                  ? (isAr ? "إدارة جروب التليجرام والكود ←" : "Manage Group License & Bot →")
                  : (isAr ? "الانتقال إلى الملف الشخصي والكوتا ←" : "Go to Profile & Quota Dashboard →")}
              </button>
            </div>
          )}

          {/* Failed Retry & Empathetic Recovery */}
          {orderStatus === "failed" && (
            <div className="space-y-4 pt-2">
              <div className="border-2 border-amber-500 bg-amber-50 dark:bg-amber-950/40 p-4 text-start space-y-2">
                <div className="flex items-center gap-2 text-amber-800 dark:text-amber-200 font-black text-sm">
                  <HelpCircle className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
                  <span>{isAr ? "واجهتك مشكلة أثناء الدفع؟ احكيلنا ونساعدك فوراً 💬" : "Had an issue during checkout? Talk to us 💬"}</span>
                </div>
                <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-300 leading-relaxed">
                  {isGulfPricing || selectedDialCode !== "+20"
                    ? isAr
                      ? "تأكد من تفعيل الشراء الدولي/الإنترنت على بطاقة Visa أو Mastercard وإدخال رمز التحقق (3D Secure / OTP) ثم أعد المحاولة عبر EasyKash. لو استمرت المشكلة تواصل معنا فوراً."
                      : "Ensure international/online payments are enabled on your Visa or Mastercard and complete the 3D Secure OTP step on EasyKash, or message our team for immediate help."
                    : isAr
                    ? "تأكد من رصيد البطاقة أو المحفظة الإلكترونية وإدخال رمز التأكيد (OTP) ثم أعد المحاولة عبر بوابة EasyKash الرسمية، أو تواصل معنا لمساعدتك فوراً."
                    : "Ensure sufficient balance and complete the OTP verification step on EasyKash, or message our support team for immediate assistance."}
                </p>
                <div className="pt-2 flex flex-col sm:flex-row gap-2">
                  <a
                    href={`https://wa.me/201024359100?text=${waFailureMsg}`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex-1 inline-flex items-center justify-center gap-1.5 border-2 border-emerald-600 bg-emerald-600 hover:bg-emerald-700 text-white font-black py-2.5 px-4 text-xs transition-colors"
                  >
                    <MessageSquare className="w-4 h-4" />
                    {isAr ? "تواصل معنا عبر واتساب للمساعدة الفورية" : "Chat on WhatsApp"}
                  </a>
                  {!isGccChatOnly && (
                  <a
                    href="https://t.me/SharksZone_support_bot"
                    target="_blank"
                    rel="noreferrer"
                    className="flex-1 inline-flex items-center justify-center gap-1.5 border-2 border-black dark:border-white bg-zinc-900 hover:bg-zinc-800 text-white dark:bg-white dark:text-black dark:hover:bg-zinc-200 font-black py-2.5 px-4 text-xs transition-colors"
                  >
                    <ExternalLink className="w-4 h-4" />
                    {isAr ? "الدعم الفني على تليجرام" : "Telegram Support"}
                  </a>
                  )}
                </div>
              </div>

              <button
                type="button"
                onClick={() => setStep("plans")}
                className="w-full border-4 border-black dark:border-white bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-zinc-950 dark:text-white font-black py-3 px-6 uppercase tracking-wider text-xs transition-all"
              >
                {isAr ? "المحاولة مجددًا باختيار باقة أخرى" : "Try Another Plan"}
              </button>
            </div>
          )}

          {pollingExhausted && orderStatus !== "approved" && orderStatus !== "failed" && (
            <button type="button" onClick={() => setPollRestart((value) => value + 1)} className="w-full border-2 border-black dark:border-white p-3 font-bold text-zinc-900 dark:text-white">
              {isAr ? "التحقق من حالة الدفع مجددًا" : "Check payment status again"}
            </button>
          )}

          {/* Support Hotline */}
          <div className="border-t-2 border-zinc-200 dark:border-zinc-800 pt-4">
            <a
              href="https://wa.me/201024359109"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-black text-emerald-600 dark:text-emerald-400 hover:underline"
            >
              <HelpCircle className="w-4 h-4" />
              {isAr ? "تحتاج مساعدة بخصوص الدفع؟ تواصل معنا عبر واتساب" : "Need help with payment? Contact us on WhatsApp"}
            </a>
          </div>
        </div>
      </div>
    );
  }

  // ── STEP 2: CHECKOUT / PAYMENT FORM ────────────────────────────────────────
  if (step === "payment") {
    return (
      <div className="min-h-[75vh] py-8 sm:py-12 px-4 relative" dir={isAr ? "rtl" : "ltr"}>
        <div className="max-w-6xl mx-auto space-y-6">
          {/* Top Bar Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-6 shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_#10b981]">
            <div className="flex items-center gap-3 sm:gap-4">
              <div className="shrink-0 border-2 border-black dark:border-white bg-white p-1.5 shadow-[2px_2px_0px_rgba(0,0,0,1)]">
                <Image src="/favicon_io/apple-touch-icon.png" alt={brandName} width={36} height={36} className="h-8 w-8 object-contain" unoptimized />
              </div>
              <div>
                <span className="inline-block border-2 border-black bg-amber-300 px-2 py-0.5 text-[10px] font-black uppercase tracking-widest text-black">
                  SECURE CHECKOUT · EASYKASH
                </span>
                <h1 className="text-xl sm:text-2xl font-black text-zinc-950 dark:text-white">
                  {isAr ? "إتمام وتأكيد الاشتراك" : "Complete Your Subscription"}
                </h1>
              </div>
            </div>

            <button
              type="button"
              onClick={() => {
                setStep("plans");
                setLocalOrder(null);
                setOrderDurationDays(null);
              }}
              className="inline-flex items-center justify-center gap-2 border-2 border-black dark:border-white bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 px-4 py-2 text-xs font-black text-zinc-950 dark:text-white shadow-[2px_2px_0px_rgba(0,0,0,1)] transition-transform active:translate-y-0.5 self-start sm:self-auto"
            >
              {isAr ? <ArrowRight className="h-4 w-4" /> : <ArrowLeft className="h-4 w-4" />}
              {isAr ? "تغيير الخطة" : "Change Plan"}
            </button>
          </div>

          {/* 2-Column Responsive Layout */}
          <div className="grid gap-6 lg:grid-cols-12 lg:items-start">
            {/* Form Column (Main) */}
            <div className="lg:col-span-8 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 sm:p-8 space-y-6 shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_#10b981]">
              {/* Step 1 Title */}
              <div className="border-b-2 border-zinc-200 dark:border-zinc-800 pb-4">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-black uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                    {isAr ? "01 / بوابة الدفع" : "01 / PAYMENT GATEWAY"}
                  </span>
                  <span className="flex items-center gap-1.5 text-xs font-black text-zinc-600 dark:text-zinc-300">
                    <ShieldCheck className="w-4 h-4 text-emerald-500" />
                    {isAr ? "دفع رسمي ومعتمد" : "Official & Certified"}
                  </span>
                </div>
                <h2 className="text-xl font-black text-zinc-950 dark:text-white mt-1">
                  {isAr ? "اختر وسيلة الدفع داخل EasyKash" : "Choose Your Method on EasyKash"}
                </h2>
              </div>

              <div className="border-2 border-black dark:border-white bg-emerald-50 dark:bg-emerald-950/30 p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                  <h3 className="text-xs font-black uppercase text-zinc-900 dark:text-white">
                    {isAr ? "كل وسائل حسابك المفعّلة تظهر داخل البوابة" : "All Enabled Methods Appear in the Gateway"}
                  </h3>
                </div>
                <p className="text-xs font-semibold leading-relaxed text-zinc-700 dark:text-zinc-300">
                  {isAr
                    ? "بعد المتابعة ستنتقل إلى صفحة EasyKash الرسمية، ومنها تختار البطاقة أو المحفظة أو الدفع النقدي أو أي وسيلة أخرى مفعّلة. بيانات الدفع لا تمر بموقعنا ولا نحفظها."
                    : "Continue to the official EasyKash page, then choose card, wallet, cash, or any other method enabled for this merchant. Payment details never pass through or get stored by our site."}
                </p>
              </div>

              {/* Contact Phone & Email */}
              <div className="border-t-2 border-zinc-200 dark:border-zinc-800 pt-5 space-y-4">
                <div>
                  <span className="text-xs font-black uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                    {isAr ? "02 / بيانات المشتري" : "02 / BUYER CONTACT"}
                  </span>
                  <h3 className="text-lg font-black text-zinc-950 dark:text-white mt-0.5">
                    {isAr ? "رقم الموبايل للتأكيد" : "Mobile Number for Confirmation"}
                  </h3>
                  <p className="text-xs font-semibold text-zinc-500 mt-1">
                    {isAr
                      ? "رقم موبايلك (مصري أو دولي) لتلقي رسالة التأكيد من بوابة الدفع."
                      : "Your mobile number (Egyptian or international) to receive confirmation from the payment gateway."}
                  </p>
                </div>

                {user?.email && (
                  <div className="flex items-center justify-between border-2 border-zinc-300 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 px-3.5 py-2.5 text-xs font-bold">
                    <span className="text-zinc-500">{isAr ? "حساب المستخدم:" : "Account:"}</span>
                    <span className="text-zinc-900 dark:text-white font-mono break-all">{user.email}</span>
                  </div>
                )}

                <div className="space-y-1.5">
                  <label htmlFor="mobile-input" className="block text-xs font-black text-zinc-800 dark:text-zinc-200">
                    {isAr ? "رقم الموبايل" : "Mobile Number"}
                  </label>

                  {/* ── Country Code Picker + Input ── */}
                  <div className="flex border-3 border-black dark:border-white bg-white dark:bg-zinc-900 focus-within:ring-2 focus-within:ring-emerald-500">

                    {/* Country selector */}
                    <div className="relative shrink-0">
                      <button
                        type="button"
                        onClick={() => setDialDropdownOpen((v) => !v)}
                        className="flex items-center gap-1.5 h-full px-3 py-3 border-e-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors font-black text-sm"
                      >
                        <span className="text-lg leading-none">{selectedCountry.flag}</span>
                        <span className="font-mono text-xs text-zinc-700 dark:text-zinc-300">{selectedDialCode}</span>
                        <svg className="w-3 h-3 text-zinc-500" viewBox="0 0 12 12" fill="currentColor">
                          <path d="M6 8L1 3h10z" />
                        </svg>
                      </button>

                      {dialDropdownOpen && (
                        <div className="absolute z-50 top-full start-0 mt-1 w-56 max-h-64 overflow-y-auto bg-white dark:bg-zinc-900 border-2 border-black dark:border-white shadow-xl">
                          {DIAL_COUNTRIES.map((country) => (
                            <button
                              key={country.code}
                              type="button"
                              onClick={() => {
                                userPickedDialCodeRef.current = true;
                                setSelectedDialCode(country.code);
                                setDialDropdownOpen(false);
                              }}
                              className={`flex items-center gap-2 w-full px-3 py-2 text-xs font-bold hover:bg-emerald-50 dark:hover:bg-emerald-950/30 transition-colors text-start
                                ${selectedDialCode === country.code ? "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300" : "text-zinc-800 dark:text-zinc-200"}`}
                            >
                              <span className="text-base">{country.flag}</span>
                              <span className="flex-1">{isAr ? country.name : country.nameEn}</span>
                              <span className="font-mono text-zinc-500">{country.code}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Number input */}
                    <div className="flex items-center flex-1 px-3 py-3 gap-2">
                      <Smartphone className="w-4 h-4 text-emerald-600 shrink-0" />
                      <input
                        id="mobile-input"
                        type="tel"
                        value={customerMobile}
                        onChange={(e) => {
                          setCustomerMobile(e.target.value.replace(/[^\d]/g, ""));
                        }}
                        placeholder={selectedDialCode === "+20" ? "1012345678" : "512345678"}
                        className="w-full bg-transparent font-mono text-base font-black outline-none placeholder:text-zinc-400 text-zinc-950 dark:text-white"
                        dir="ltr"
                        inputMode="numeric"
                      />
                    </div>
                  </div>

                  {/* Validation hint */}
                  <div className="flex items-center justify-between text-xs font-bold pt-0.5">
                    <span className={isMobileValid ? "text-emerald-600 dark:text-emerald-400" : "text-zinc-500"}>
                      {isMobileValid
                        ? `✓ ${selectedCountry.flag} ${normalizedMobile}`
                        : isAr
                          ? `أدخل رقمك بدون مفتاح الدولة (${selectedDialCode} تلقائي)`
                          : `Enter number without country code (${selectedDialCode} auto-added)`}
                    </span>
                    <span className="text-[10px] text-zinc-400 font-mono">
                      {localDigits.length > 0 ? `${selectedDialCode} ${localDigits}` : ""}
                    </span>
                  </div>
                </div>

                {/* Promo / Referral Code Input */}
                <div className="pt-3 border-t border-zinc-200 dark:border-zinc-800 space-y-2">
                  <label htmlFor="promo-input" className="block text-xs font-black text-zinc-800 dark:text-zinc-200">
                    {isAr ? "هل لديك كود خصم أو إحالة؟ (اختياري)" : "Have a Promo / Referral Code? (Optional)"}
                  </label>
                  {appliedPromo ? (
                    <div className="flex items-center justify-between gap-2 border-2 border-emerald-500 bg-emerald-50 dark:bg-emerald-950/30 px-3.5 py-2.5 text-xs font-black">
                      <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
                        <CheckCircle2 className="w-4 h-4 shrink-0" />
                        <span>
                          {isAr
                            ? `كود (${appliedPromo.code}) مفعّل — ${appliedPromo.name} (خصم ${appliedPromo.discount_percent}%)`
                            : `Code (${appliedPromo.code}) active — ${appliedPromo.discount_percent}% OFF`}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={removePromoCode}
                        className="text-[11px] font-black text-red-600 hover:underline shrink-0 cursor-pointer"
                      >
                        {isAr ? "إزالة" : "Remove"}
                      </button>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <input
                        id="promo-input"
                        type="text"
                        value={promoInput}
                        onChange={(e) => setPromoInput(e.target.value.toUpperCase())}
                        placeholder={isAr ? "أدخل الكود مثل: AMR15" : "Enter code e.g. AMR15"}
                        className="flex-1 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 px-3.5 py-2.5 font-mono text-sm font-black uppercase outline-none focus:ring-2 focus:ring-emerald-500 text-zinc-950 dark:text-white"
                        dir="ltr"
                      />
                      <button
                        type="button"
                        onClick={() => applyPromoCode(promoInput, false, false)}
                        disabled={promoChecking || !promoInput.trim()}
                        className="border-2 border-black dark:border-white bg-zinc-900 text-white dark:bg-white dark:text-black px-5 py-2.5 text-xs font-black uppercase tracking-wider hover:bg-emerald-500 hover:text-black transition-colors disabled:opacity-50 cursor-pointer"
                      >
                        {promoChecking ? (isAr ? "جاري التحقق..." : "Checking...") : (isAr ? "تطبيق الكود" : "Apply")}
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Submit Button */}
              <div className="pt-2 space-y-3">
                <button
                  type="button"
                  onClick={() => startEasyKashPayment()}
                  disabled={busy || (!!user && !isMobileValid) || (selectedPlan === "lifetime" && !lifetimeIsOpen)}
                  className="w-full flex items-center justify-center gap-3 border-4 border-black dark:border-white bg-emerald-500 hover:bg-emerald-600 text-zinc-950 dark:text-black font-black text-base py-4 px-6 uppercase tracking-wider shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_#ffffff] hover:-translate-y-0.5 active:translate-y-0 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {busy ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <>
                      <LockKeyhole className="w-5 h-5" />
                      {!user
                        ? isAr ? "سجّل الدخول للمتابعة" : "Sign in to Continue"
                        : selectedPlan === "lifetime" && !lifetimeIsOpen
                        ? isAr ? "عذراً، اكتملت جميع مقاعد باقة مدى الحياة (20/20)" : "Lifetime Deal is Sold Out"
                        : isAr ? `المتابعة للدفع الآمن (${proDisplayAmount.toLocaleString()} ${currencyLabel}) 🔒` : `Proceed to Secure Checkout (${proDisplayAmount.toLocaleString()} ${currencyLabel}) 🔒`}
                    </>
                  )}
                </button>
                {(selectedDialCode !== "+20" || isGulfPricing) && (
                  <p className="text-[11px] font-bold text-center text-zinc-600 dark:text-zinc-400">
                    {isGulfPricing
                      ? isAr
                        ? `يُعادل ${proDisplayAmount.toLocaleString()} ${currencyLabel} — تُعالج الفاتورة على بوابة EasyKash بقيمة ${easyKashChargeEgp.toLocaleString()} ج.م وتُخصم تلقائياً من بطاقتك الدولية (Visa / Mastercard عبر 3D Secure)`
                        : `Approx. ${proDisplayAmount.toLocaleString()} ${currencyCode} — EasyKash charges ${easyKashChargeEgp.toLocaleString()} EGP with automatic card conversion (Visa / Mastercard 3DS)`
                      : isAr
                      ? `للدفع الدولي من خارج مصر: تُعالج الفاتورة عبر EasyKash بقيمة ${easyKashChargeEgp.toLocaleString()} ج.م وتتحول تلقائياً بعملة بطاقتك (Visa / Mastercard عبر 3D Secure)`
                      : `International card checkout: EasyKash processes ${easyKashChargeEgp.toLocaleString()} EGP with automatic conversion to your card currency (Visa / Mastercard 3DS)`}
                  </p>
                )}
                <div className="flex items-center justify-center gap-3 text-[11px] font-bold text-zinc-500">
                  <span className="flex items-center gap-1">
                    <Shield className="w-3.5 h-3.5 text-emerald-500" />
                    {isAr ? "دفع آمن 256-bit" : "256-bit SSL"}
                  </span>
                  <span>•</span>
                  <span>{isAr ? "تفعيل فوري للاشتراك" : "Instant Activation"}</span>
                  <span>•</span>
                  <span>{isAr ? "دعم فني 24/7" : "24/7 Support"}</span>
                </div>
              </div>
            </div>

            {/* Sidebar Summary Column */}
            <div className="lg:col-span-4 border-4 border-black dark:border-white bg-zinc-950 text-white p-6 space-y-6 shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_#10b981] lg:sticky lg:top-24">
              {(() => {
                const isB2bCheckout = selectedPlanDetails.id.startsWith("b2b_");
                const b2bSelected = isB2bCheckout ? (b2bPlans.find((item) => item.id === selectedPlanDetails.id) ?? null) : null;
                return (
                  <>
              <div className="border-b border-zinc-800 pb-4">
                <span className="text-[10px] font-black uppercase tracking-widest text-emerald-400 block mb-1">
                  {isAr ? "فاتورة الاشتراك" : "ORDER INVOICE"}
                </span>
                <h3 className="text-2xl font-black flex items-center gap-2">
                  {selectedPlanDetails.isLifetime && <Crown className="w-6 h-6 text-yellow-400" />}
                  {isB2bCheckout
                    ? (isAr ? `${brandName} B2B للـ Telegram` : `${brandName} B2B License`)
                    : selectedPlanDetails.isLifetime
                    ? `${brandName} Lifetime VIP`
                    : selectedPlanDetails.id === "chat_only"
                    ? (isGccChatOnly ? `${brandName} AI Pro` : `${brandName} AI Chat Pro`)
                    : selectedPlanDetails.id === "vip_only"
                    ? `${brandName} VIP Radar`
                    : isGccChatOnly
                    ? (isAr ? "باقة كل الأسواق الشاملة (+ تليجرام VIP)" : "All-Markets Pro (+ VIP Telegram)")
                    : `${brandName} Pro Bundle`}
                </h3>
                <p className="text-xs font-semibold text-zinc-400 mt-1">
                  {isAr ? selectedPlanDetails.name_ar : selectedPlanDetails.name_en}
                </p>
              </div>

              {/* Items Breakdown */}
              <div className="space-y-3 border-b border-zinc-800 pb-4 text-xs font-bold">
                <div className="flex justify-between">
                  <span className="text-zinc-400">{isAr ? "الخطة:" : "Plan:"}</span>
                  <span className="font-black text-emerald-400">
                    {isB2bCheckout
                      ? (b2bSelected?.tag || "B2B VIP")
                      : selectedPlanDetails.isLifetime
                      ? (isAr ? "مدى الحياة (Lifetime VIP)" : "Lifetime VIP")
                      : selectedPlanDetails.id === "chat_only"
                      ? (isGccChatOnly ? `${brandName} AI Pro` : (isAr ? "شات بوت الذكاء الاصطناعي فقط" : "AI Chat Pro"))
                      : selectedPlanDetails.id === "vip_only"
                      ? (isAr ? "رادار وقنوات VIP فقط" : "VIP Radar Only")
                      : isGccChatOnly
                      ? (isAr ? "باقة كل الأسواق (+ تليجرام VIP)" : "All-Markets Pro (+ VIP Telegram)")
                      : (isAr ? "الباقة الشاملة (Pro Bundle)" : "Pro Full Bundle")}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">{isAr ? "فترة الاشتراك:" : "Duration:"}</span>
                  <span className="font-mono">
                    {selectedPlanDetails.isLifetime
                      ? (isAr ? "مدى الحياة للأبد (دائم)" : "Lifetime Forever")
                      : `${selectedPlanDetails.days} ${isAr ? "يوماً" : "days"}`}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">{isAr ? "وسيلة الدفع:" : "Method:"}</span>
                  <span>{isAr ? "تُحدد داخل EasyKash" : "Chosen on EasyKash"}</span>
                </div>
                {selectedPlanDetails.isLifetime ? (
                  <div className="flex justify-between text-yellow-400">
                    <span>{isAr ? "الميزة الكبرى:" : "Perk:"}</span>
                    <span>{isAr ? "بدون أي تجديد شهري للأبد" : "Zero recurring renewals"}</span>
                  </div>
                ) : (
                  selectedPlanDetails.savingsPct > 0 && (
                    <div className="flex justify-between text-emerald-400">
                      <span>{isAr ? "نسبة التوفير:" : "Savings:"}</span>
                      <span>{isAr ? `وفرت ${selectedPlanDetails.savingsPct}%` : `${selectedPlanDetails.savingsPct}% OFF`}</span>
                    </div>
                  )
                )}
              </div>

              {/* Total */}
              <div className="space-y-2 border-b border-zinc-800 pb-5">
                {promoDiscountDisplay > 0 && appliedPromo && (
                  <div className="space-y-1 text-xs font-bold">
                    <div className="flex justify-between text-zinc-400">
                      <span>{isAr ? "السعر قبل كود الخصم:" : "Subtotal:"}</span>
                      <span className="line-through">{formatPrice(baseProPrice)}</span>
                    </div>
                    <div className="flex justify-between text-amber-400 font-black">
                      <span>{isAr ? `خصم كود (${appliedPromo.code} - ${appliedPromo.discount_percent}%):` : `Promo (${appliedPromo.code}):`}</span>
                      <span>-{promoDiscountDisplay.toLocaleString()} {currencyLabel}</span>
                    </div>
                  </div>
                )}
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-black">{isAr ? "المبلغ الإجمالي:" : "Total Amount:"}</span>
                  <div className="text-end">
                    <span className="text-3xl font-black text-emerald-400">{proDisplayAmount.toLocaleString()}</span>
                    <span className="text-xs font-bold text-zinc-400 ms-1">{currencyLabel}</span>
                  </div>
                </div>
                {isGulfPricing && (
                  <p className="text-[11px] font-semibold text-amber-300/90 leading-relaxed pt-1">
                    {isAr
                      ? `يُعادل ${proDisplayAmount.toLocaleString()} ${currencyLabel} — قيمة الفاتورة الفعلية على بوابة EasyKash هي ${easyKashChargeEgp.toLocaleString()} ج.م (تحويل تلقائي بالبطاقة)`
                      : `Approx. ${proDisplayAmount.toLocaleString()} ${currencyCode} — EasyKash processes ${easyKashChargeEgp.toLocaleString()} EGP (auto-converted by your card)`}
                  </p>
                )}
              </div>

              {/* Included Benefits List */}
              <div className="space-y-2 text-xs font-bold">
                <span className="text-[10px] font-black uppercase text-zinc-400 tracking-wider block">
                  {isB2bCheckout
                    ? (isAr ? "ميزات رخصة القنوات B2B:" : "INCLUDED WITH B2B LICENSE:")
                    : selectedPlanDetails.isLifetime
                    ? (isAr ? "ميزات باقة مدى الحياة VIP:" : "INCLUDED WITH LIFETIME VIP:")
                    : (isAr ? "الميزات المشمولة فوراً:" : "INCLUDED WITH PRO:")}
                </span>
                {isB2bCheckout ? (
                  <>
                    {(b2bSelected?.features || []).map((feat, idx) => (
                      <div key={idx} className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{feat.text}</span>
                      </div>
                    ))}
                  </>
                ) : selectedPlanDetails.isLifetime ? (
                  isGccChatOnly ? (
                    <>
                      <div className="flex items-center gap-2 text-yellow-300 font-black">
                        <Crown className="w-3.5 h-3.5 text-yellow-400 shrink-0" />
                        <span>{isAr ? "صلاحية مدى الحياة للأبد بدون تجديد" : "Permanent lifetime access, zero renewals"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? `${proLimits.chat_messages_per_month} رسالة ذكاء اصطناعي تتجدد شهرياً للأبد لجميع الأسواق والذهب والفضة` : `${proLimits.chat_messages_per_month} AI chat messages renewed monthly for life across all markets & Gold/Silver`}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? "تحليل صور المحفظة والشارت (Vision AI) واستخراج الدعوم والمقاومات للأبد" : "Vision AI chart & portfolio analysis with key levels for life"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? "تشمل قنوات تليجرام VIP للسوق السعودي (TASI) والمصري (EGX) وأتمتة تليجرام للأبد" : "Includes Saudi TASI & Egypt EGX VIP Telegram channels + Telegram automations forever"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? `محفظة ذكية حتى ${proLimits.portfolio_stocks} سهماً + أولوية التحديثات المستقبلية` : `Up to ${proLimits.portfolio_stocks} portfolio stocks + priority future updates`}</span>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="flex items-center gap-2 text-yellow-300 font-black">
                        <Crown className="w-3.5 h-3.5 text-yellow-400 shrink-0" />
                        <span>{isAr ? "صلاحية مدى الحياة للأبد بدون تجديد" : "Permanent lifetime access, zero renewals"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? "قناة VIP على تليجرام فورية للأبد" : "VIP Telegram Channel for life"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? "إشارات الزخم قصيرة المدى ⚡ PRO بدون حجب" : "Short Momentum ⚡ PRO unmasked"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? `${proLimits.chat_messages_per_month} رسالة ذكاء اصطناعي تتجدد شهرياً للأبد` : `${proLimits.chat_messages_per_month} AI chat messages renewed monthly for life`}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? "رادار وتنبيهات الإسكانر الفورية على تليجرام للأبد" : "Live Telegram Scanner Alerts lifetime"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? `محفظة حتى ${proLimits.portfolio_stocks} أسهم + كشف السيولة غير الطبيعية` : `Up to ${proLimits.portfolio_stocks} portfolio stocks + volume spikes`}</span>
                      </div>
                    </>
                  )
                ) : (
                  selectedPlanDetails.id === "chat_only" ? (
                    isGccChatOnly ? (
                      <>
                        <div className="flex items-center gap-2 text-zinc-300">
                          <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                          <span>{isAr ? `${proLimits.chat_messages_per_month} رسالة شات ذكاء اصطناعي شهرياً (الإمارات وقطر والذهب والفضة)` : `${proLimits.chat_messages_per_month} monthly AI chat messages (UAE, Qatar, Gold & Silver)`}</span>
                        </div>
                        <div className="flex items-center gap-2 text-zinc-300">
                          <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                          <span>{isAr ? "تحليل الشارتات بالصور (Vision AI) والبحث المتعمق" : "Vision AI chart analysis & deep screening"}</span>
                        </div>
                        <div className="flex items-center gap-2 text-zinc-300">
                          <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                          <span>{isAr ? `محفظة ذكية حتى ${proLimits.portfolio_stocks} سهماً مع متابعة المستويات الفنية` : `${proLimits.portfolio_stocks} smart portfolio slots with technical levels`}</span>
                        </div>
                        <div className="flex items-center gap-2 text-zinc-300">
                          <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                          <span>{isAr ? "مؤشرات فنية محدثة يومياً للأسهم والذهب والفضة" : "Daily updated technical indicators for stocks, Gold & Silver"}</span>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="flex items-center gap-2 text-zinc-300">
                          <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                          <span>{isAr ? `${proLimits.chat_messages_per_month} رسالة شات ذكاء اصطناعي شهرياً (EGX & TASI)` : `${proLimits.chat_messages_per_month} monthly AI chat messages (EGX & TASI)`}</span>
                        </div>
                        <div className="flex items-center gap-2 text-zinc-300">
                          <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                          <span>{isAr ? "تحليل الشارتات بالصور (Vision AI) والبحث المتعمق" : "Vision AI chart analysis & deep screening"}</span>
                        </div>
                        <div className="flex items-center gap-2 text-zinc-300">
                          <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                          <span>{isAr ? `محفظة ذكية حتى ${proLimits.portfolio_stocks} أسهم + 5 أتمتة يومية` : `${proLimits.portfolio_stocks} smart portfolio slots + 5 daily automations`}</span>
                        </div>
                        <div className="flex items-center gap-2 text-zinc-300">
                          <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                          <span>{isAr ? "تحديث بيانات الموقع بدون تأخير زمني" : "Real-time site market metrics without delay"}</span>
                        </div>
                      </>
                    )
                  ) : selectedPlanDetails.id === "vip_only" ? (
                    <>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? "قناة تليجرام VIP الفورية (السوق المصري والسعودي)" : "Instant VIP Telegram Channel (EGX & Saudi TASI)"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? "رادار وتنبيهات الإسكانر الفورية على تليجرام (سيولة واختراقات وإفصاحات)" : "Live Telegram Scanner Alerts (volume, breakouts & filings)"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? "مؤشرات الزخم قصيرة المدى ⚡ PRO بدون حجب + صفر تأخير بالموقع" : "Short Momentum ⚡ PRO unmasked + zero site delay"}</span>
                      </div>
                    </>
                  ) : isGccChatOnly ? (
                    <>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? `${proLimits.chat_messages_per_month} رسالة شات ذكاء اصطناعي شهرياً + Vision AI (كل الأسواق والذهب والفضة)` : `${proLimits.chat_messages_per_month} monthly AI chat messages + Vision AI (All Markets, Gold & Silver)`}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? "دخول فوري لقنوات تليجرام VIP للسوق السعودي (TASI) والمصري (EGX) + 5 أتمتات يومية" : "Instant VIP Telegram channels for Saudi (TASI) & Egypt (EGX) + 5 daily automations"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? `محفظة ذكية حتى ${proLimits.portfolio_stocks} سهماً + إزالة تأخير ماسح السعودية ومصر` : `${proLimits.portfolio_stocks} smart portfolio slots + zero delay on Saudi & Egypt scanners`}</span>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? "قناة تليجرام VIP الفورية (تنبيهات فنية وخوارزمية بدون تأخير)" : "Instant VIP Telegram Channel (technical alerts without delay)"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? "رادار وتنبيهات الإسكانر الفورية على تليجرام (سيولة واختراقات وإفصاحات)" : "Live Telegram Scanner Alerts (volume, breakouts & filings)"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? "مؤشرات الزخم قصيرة المدى ⚡ PRO ومستويات الوقف بدون حجب" : "Short Momentum ⚡ PRO indicators & trailing zones unmasked"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? `${proLimits.chat_messages_per_month} رسالة شات ذكاء اصطناعي شهرياً + Vision AI` : `${proLimits.chat_messages_per_month} monthly AI chat messages + Vision AI`}</span>
                      </div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>{isAr ? `محفظة ذكية حتى ${proLimits.portfolio_stocks} أسهم + 5 أتمتة يومية` : `${proLimits.portfolio_stocks} smart portfolio slots + 5 daily automations`}</span>
                      </div>
                    </>
                  )
                )}
              </div>
                  </>
                );
              })()}

              {/* Secure Notice */}
              <div className="p-3 border-2 border-emerald-500/50 bg-emerald-950/30 text-[11px] font-semibold text-zinc-300 leading-relaxed">
                {isAr
                  ? "تتم المعاملة عبر بوابة EasyKash المرخصة. يُفعّل اشتراكك آلياً فور السداد دون الحاجة لتدخل يدوي."
                  : "Processed through certified EasyKash gateway. Account activates automatically upon payment."}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── STEP 1: PLANS COMPARISON GRID (DEFAULT) ────────────────────────────────
  return (
    <div className="min-h-[75vh] py-10 sm:py-14 px-4 relative overflow-x-clip" dir={isAr ? "rtl" : "ltr"}>
      <div className="max-w-6xl mx-auto space-y-10 relative">
        {/* Main Header */}
        <div className="text-center space-y-3">
          <span className="inline-block border-2 border-black dark:border-white bg-amber-300 px-3 py-1 text-xs font-black uppercase tracking-widest text-black shadow-[3px_3px_0px_rgba(0,0,0,1)]">
            {isSaudi
              ? (isAr ? "TASI BOTS PRO · باقات السوق السعودي (تداول TASI)" : "TASI BOTS PRO · SAUDI TADAWUL PLANS")
              : isUae
                ? (isAr ? "UAE BOTS PRO · باقات سوق الإمارات (دبي وأبوظبي)" : "UAE BOTS PRO · DFM & ADX PLANS")
                : isQatar
                  ? (isAr ? "QSE BOTS PRO · باقات بورصة قطر" : "QSE BOTS PRO · QATAR PLANS")
                  : "EGX BOTS PRO · خطط واشتراكات"}
          </span>
          <h1 className="text-3xl sm:text-5xl font-black text-zinc-950 dark:text-white tracking-tight">
            {isAr ? "اختر باقة الاشتراك البرمجي" : "Choose Your Software Plan"}
          </h1>
          <p className="text-sm sm:text-base font-bold text-zinc-600 dark:text-zinc-300 max-w-2xl mx-auto leading-relaxed">
            {isAr
              ? isSaudi
                ? "تحليلات كمية، ونماذج فنية مدعومة بالذكاء الاصطناعي، وقناة تنبيهات فورية لمتابعة السوق السعودي (تداول TASI)."
                : isUae
                  ? "شات بوت ذكي مدعوم بالذكاء الاصطناعي ومؤشرات فنية محدثة يومياً لأسهم سوق دبي (DFM) وسوق أبوظبي (ADX) والذهب والفضة."
                  : isQatar
                    ? "شات بوت ذكي مدعوم بالذكاء الاصطناعي ومؤشرات فنية محدثة يومياً لأسهم بورصة قطر (QSE) والذهب والفضة."
                    : "تحليلات كمية، ونماذج فنية مدعومة بالذكاء الاصطناعي، وقناة تنبيهات فورية لمتابعة البورصة المصرية."
              : isSaudi
                ? "Quantitative analysis, AI-driven stock indicators, and instant technical alerts for the Saudi Stock Exchange (Tadawul / TASI)."
                : isUae
                  ? "AI-powered chatbot & daily technical analysis for UAE (DFM & ADX) stocks plus Gold & Silver."
                  : isQatar
                    ? "AI-powered chatbot & daily technical analysis for Qatar Stock Exchange (QSE) plus Gold & Silver."
                    : "Quantitative analysis, AI-driven stock indicators, and instant technical alerts for the Egyptian Stock Exchange."}
          </p>
        </div>

        {isPro && (
          <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-5 py-3.5 text-center text-sm font-bold text-emerald-800 dark:text-emerald-200 shadow-sm" role="status">
            {isAr ? "اشتراك Pro نشط على حسابك الآن" : "Your Pro subscription is active"}
            {subscriptionEnd && ` · ${isAr ? "ساري حتى" : "Valid until"} ${new Intl.DateTimeFormat("en-GB", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(subscriptionEnd))}`}
          </div>
        )}

        {/* ── ACTIVE AFFILIATE / PROMO BANNER ── */}
        {appliedPromo && (
          <div className="rounded-xl border border-emerald-500/50 bg-emerald-500/10 text-emerald-950 dark:text-emerald-200 p-4 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 text-xs sm:text-sm font-bold">
              <Sparkles className="w-5 h-5 shrink-0 text-emerald-500" />
              <span>
                {isAr
                  ? `🎁 تم تفعيل كود الإحالة الخاص بـ (${appliedPromo.name}) — كود: ${appliedPromo.code}${
                      appliedPromo.discount_percent > 0 ? ` بخصم إضافي ${appliedPromo.discount_percent}% عند الدفع!` : ""
                    }`
                  : `🎁 Referral code (${appliedPromo.code}) by ${appliedPromo.name} is active${
                      appliedPromo.discount_percent > 0 ? ` — ${appliedPromo.discount_percent}% extra discount at checkout!` : ""
                    }`}
              </span>
            </div>
            <button
              type="button"
              onClick={removePromoCode}
              className="text-[11px] font-bold px-3 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-800 dark:text-zinc-200 shrink-0 cursor-pointer transition-colors"
            >
              {isAr ? "إلغاء الكود" : "Remove"}
            </button>
          </div>
        )}

        {/* ── PRICING CATEGORY SWITCHER: RETAIL VS B2B (available across all markets: EGX, Saudi, UAE, Qatar) ── */}
        <div className="flex justify-center mb-6">
          <div className="inline-flex p-1.5 rounded-2xl bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-sm gap-2 max-w-full flex-wrap justify-center">
            <button
              type="button"
              onClick={() => setPricingCategory("retail")}
              className={`flex items-center gap-2 px-5 sm:px-8 py-3 rounded-xl transition-all text-xs sm:text-sm font-black cursor-pointer ${
                pricingCategory === "retail"
                  ? "bg-emerald-500 text-black shadow-md shadow-emerald-500/20"
                  : "bg-transparent hover:bg-zinc-200/60 dark:hover:bg-zinc-800/60 text-zinc-600 dark:text-zinc-400"
              }`}
            >
              <span>👤 {isAr ? "خطط الأفراد والمستثمرين" : "Individual Traders"}</span>
            </button>

            <button
              type="button"
              onClick={() => setPricingCategory("b2b")}
              className={`flex items-center gap-2 px-5 sm:px-8 py-3 rounded-xl transition-all text-xs sm:text-sm font-black cursor-pointer ${
                pricingCategory === "b2b"
                  ? "bg-purple-600 text-yellow-300 shadow-md shadow-purple-600/20"
                  : "bg-transparent hover:bg-zinc-200/60 dark:hover:bg-zinc-800/60 text-zinc-600 dark:text-zinc-400"
              }`}
            >
              <Crown className="w-4 h-4 text-yellow-400 shrink-0" />
              <span>🤖 {isAr ? "باقات أصحاب القنوات والشركات (B2B)" : "Channel Bot Licensing (B2B)"}</span>
              <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded-full bg-amber-400 text-black">
                {isAr ? "جديد ⚡" : "NEW ⚡"}
              </span>
            </button>
          </div>
        </div>

        {pricingCategory === "retail" ? (
          <>
            {/* ── 3-DAY PRO FREE TRIAL HERO BANNER ── */}
            {trialEligible && !isPro && (
              <div className="relative overflow-hidden rounded-2xl border-2 border-emerald-500/80 bg-gradient-to-r from-emerald-500/15 via-teal-500/10 to-emerald-500/5 dark:from-emerald-950/50 dark:via-zinc-900 dark:to-teal-950/30 p-5 sm:p-6 shadow-xl shadow-emerald-500/10 flex flex-col md:flex-row items-center justify-between gap-4">
                <div className="space-y-1.5 text-center md:text-start">
                  <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500 text-black text-[10px] font-black uppercase">
                    <Sparkles className="w-3 h-3 fill-black" />
                    <span>{isAr ? "فرصة للمستخدمين الجدد · بدون أي بطاقة بنكية" : "Special Offer · Zero Card Required"}</span>
                  </div>
                  <h2 className="text-xl sm:text-2xl font-black text-zinc-950 dark:text-white">
                    {isAr ? `🎁 جرّب منصة ${brandName} PRO بالكامل مجاناً لمدة 3 أيام` : `🎁 Try ${brandName} PRO Free for 3 Full Days`}
                  </h2>
                  <p className="text-xs sm:text-sm font-semibold text-zinc-700 dark:text-zinc-300 max-w-2xl leading-relaxed">
                    {isGccChatOnly
                      ? (isAr
                          ? "افتح شات الذكاء الاصطناعي ARTORO وتحليل صور المحفظة والشارت (Vision AI) ومؤشرات أسهم الإمارات وقطر والذهب والفضة لمدة 3 أيام كاملة."
                          : "Unlock ARTORO AI Chat, Vision AI chart analysis, and daily indicators for UAE, Qatar, Gold & Silver for 3 days.")
                      : (isAr
                          ? "افتح مؤشرات الخوارزميات التحليلية، ورادار التجميع الذكي، وتنبيهات الإسكانر الفورية على تليجرام، وشات الذكاء الاصطناعي بدون أي قيود لمدة 3 أيام كاملة."
                          : "Unlock quantitative analytical indicators, smart money accumulation scans, live Telegram alerts, and AI chart analysis for 3 days.")}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleStartTrial}
                  disabled={trialLoading}
                  className="shrink-0 w-full md:w-auto inline-flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-black font-black text-xs sm:text-sm uppercase tracking-wider shadow-lg shadow-emerald-500/30 hover:-translate-y-0.5 active:translate-y-0 transition-transform cursor-pointer disabled:opacity-50"
                >
                  {trialLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Sparkles className="w-4 h-4 fill-black" />
                  )}
                  <span>{isAr ? "ابدأ التجربة المجانية 3 أيام الآن ⚡" : "Start 3-Day Free Trial Now ⚡"}</span>
                </button>
              </div>
            )}

            {/* ── GRANDFATHERED FOUNDERS 50 / 100 EGP FULL-BUNDLE PROTECTION BANNER ── */}
            {(isGrandfathered || isGrandfathered100) && (
              <div className="rounded-2xl border-2 border-amber-400/80 dark:border-amber-500/60 bg-gradient-to-r from-amber-50 via-emerald-50/60 to-white dark:from-amber-950/35 dark:via-emerald-950/20 dark:to-zinc-900 p-4 sm:p-5 shadow-md flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div className="space-y-1">
                  <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-amber-400 text-black text-[10px] font-black uppercase">
                    <Crown className="w-3 h-3 fill-black" />
                    <span>
                      {isGrandfathered
                        ? (isAr ? "عضو مؤسس · تسعير 50 ج.م محفوظ مدى الحياة" : "Founding Member · 50 EGP Locked for Life")
                        : (isAr ? "عضو مؤسس · تسعير 100 ج.م محفوظ مدى الحياة" : "Founding Member · 100 EGP Locked for Life")}
                    </span>
                  </div>
                  <h3 className="text-base sm:text-lg font-black text-zinc-950 dark:text-white">
                    {isAr
                      ? `سعرك في الباقة الشاملة (${brandName} Pro Bundle) محفوظ لك بالكامل بـ ${formatPrice(isGrandfathered ? 50 : 100)} / شهرياً`
                      : `Your Full Pro Bundle rate is grandfathered at ${formatPrice(isGrandfathered ? 50 : 100)}/mo`}
                  </h3>
                  <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-300 leading-relaxed">
                    {isGccChatOnly
                      ? (isAr
                          ? `بصفتك من المؤسسين الأوائل، تحصل على باقة الشات الذكي وأدوات المحفظة بسعر ${formatPrice(isGrandfathered ? 50 : 100)}/شهر (${formatPrice(isGrandfathered ? 250 : 500)} للـ 6 شهور / ${formatPrice(isGrandfathered ? 450 : 900)} للسنة) مع خصم تصاعدي حتى 25% عبر سلايدر المدة.`
                          : `As an early founder, you keep AI Chat Pro & portfolio tools at ${formatPrice(isGrandfathered ? 50 : 100)}/mo (${formatPrice(isGrandfathered ? 250 : 500)}/6m, ${formatPrice(isGrandfathered ? 450 : 900)}/1y) plus up to 25% slider discounts.`)
                      : (isAr
                          ? `بصفتك من المؤسسين الأوائل، تحصل على الشات بوت الذكي + قناة تليجرام VIP معاً بسعر ${formatPrice(isGrandfathered ? 50 : 100)}/شهر (${formatPrice(isGrandfathered ? 250 : 500)} للـ 6 شهور / ${formatPrice(isGrandfathered ? 450 : 900)} للسنة) — مع خصم تصاعدي على أي مدة حتى سنة.`
                          : `As an early founder, you keep BOTH AI Chat Pro + VIP Telegram Radar together at ${formatPrice(isGrandfathered ? 50 : 100)}/mo (${formatPrice(isGrandfathered ? 250 : 500)}/6m, ${formatPrice(isGrandfathered ? 450 : 900)}/1y) — plus progressive duration discounts up to 12 months.`)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => openPaymentStep("pro")}
                  className="shrink-0 w-full md:w-auto inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-black text-xs uppercase tracking-wider shadow-md cursor-pointer transition-all"
                >
                  <LockKeyhole className="w-3.5 h-3.5" />
                  <span>
                    {isAr
                      ? `تجديد باقتك الشاملة (${formatDurationLabel(selectedMonths, true)})`
                      : `Renew Founders Bundle (${formatDurationLabel(selectedMonths, false)})`}
                  </span>
                </button>
              </div>
            )}

        <div id="pricing-duration-navbar" className="sticky top-[var(--header-h,72px)] z-30 py-3.5 bg-white/95 dark:bg-zinc-950/95 backdrop-blur-md transition-all space-y-2.5 -mx-4 px-4 sm:-mx-6 sm:px-6 border-y border-zinc-200/80 dark:border-zinc-800/80 shadow-sm">
          <div className="max-w-3xl mx-auto space-y-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 flex-wrap">
                <Clock className="w-4 h-4 text-emerald-500 shrink-0" />
                <span className="text-xs sm:text-sm font-black text-zinc-900 dark:text-white">
                  {isAr ? "اختر المدة المناسبة لجميع الباقات:" : "Choose Plan Duration (1–12 Months):"}
                </span>
                <span className="inline-flex items-center gap-1 rounded-full bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-2.5 py-0.5 text-[11px] font-black">
                  <span>{formatDurationLabel(selectedMonths, isAr)}</span>
                  <span className="opacity-70">· {selectedEntry.days} {isAr ? "يوماً" : "days"}</span>
                </span>
              </div>

              <span className={`inline-flex items-center rounded-full px-3 py-1 text-[11px] font-black ${
                selectedMonths === 12
                  ? "bg-sky-400 text-black"
                  : selectedMonths >= 2
                  ? "bg-emerald-500 text-black"
                  : "bg-amber-300/90 text-black"
              }`}>
                {selectedMonths === 1
                  ? (isAr ? "شهر واحد · اسحب للزيادة ووفر حتى 25% 🔥" : "1 Month · Slide for up to 25% OFF 🔥")
                  : selectedMonths === 6
                  ? (isAr ? "خصم 17% ⭐ · ادفع 5 شهور واحصل على 6" : "Save 17% ⭐ · Pay 5 Months, Get 6")
                  : selectedMonths === 12
                  ? (isAr ? "أكبر خصم 25% 💎 · ادفع 9 شهور واحصل على سنة" : "Max 25% OFF 💎 · Pay 9 Months, Get 12")
                  : (isAr ? `خصم المدة التصاعدي -${selectedEntry.discountPct}% 🔥` : `Duration Discount -${selectedEntry.discountPct}% 🔥`)}
              </span>
            </div>

            {/* Keep range input and 1..12 ticks inside an explicit LTR box so values & ticks align identically in AR & EN */}
            <div dir="ltr" className="space-y-1.5 rounded-xl bg-zinc-100/90 dark:bg-zinc-900/90 border border-zinc-200 dark:border-zinc-800 px-3 py-2.5">
              <input
                type="range"
                min={1}
                max={12}
                step={1}
                value={selectedMonths}
                onChange={(e) => handleDurationSliderChange(Number(e.target.value), false)}
                aria-label={isAr ? "اختر مدة الاشتراك من 1 إلى 12 شهراً" : "Select subscription duration from 1 to 12 months"}
                style={{
                  background: `linear-gradient(to right, #10b981 0%, #10b981 ${((selectedMonths - 1) / 11) * 100}%, #d4d4d8 ${((selectedMonths - 1) / 11) * 100}%, #d4d4d8 100%)`,
                }}
                className="w-full h-2 rounded-lg appearance-none cursor-pointer accent-emerald-500"
              />
              <div className="grid grid-cols-12 gap-0.5 text-center">
                {DURATION_SLIDER_SCHEDULE.map((item) => {
                  const active = selectedMonths === item.months;
                  return (
                    <button
                      key={item.months}
                      type="button"
                      onClick={() => handleDurationSliderChange(item.months, false)}
                      className={`py-1 rounded-md text-[10px] sm:text-xs font-black transition-all cursor-pointer ${
                        active
                          ? "bg-emerald-500 text-black shadow-sm scale-105"
                          : "text-zinc-500 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-800 hover:text-zinc-900 dark:hover:text-white"
                      }`}
                    >
                      {item.months}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[11px] font-bold text-zinc-500 dark:text-zinc-400">
                {isAr
                  ? "ينطبق الخصم التصاعدي تلقائياً على الباقات الفردية والباقة الشاملة"
                  : "Progressive discount applies automatically to standalone & full bundle plans"}
              </span>
              <div className="flex flex-wrap items-center gap-1.5">
                {[
                  { m: 1, ar: "شهر", en: "1M" },
                  { m: 3, ar: "3 شهور (-10%)", en: "3M (-10%)" },
                  { m: 6, ar: "6 شهور (-17%)", en: "6M (-17%)" },
                  { m: 12, ar: "سنة (-25%)", en: "1Y (-25%)" },
                ].map((preset) => (
                  <button
                    key={preset.m}
                    type="button"
                    onClick={() => handleDurationSliderChange(preset.m, true)}
                    className={`px-2.5 py-1 rounded-lg text-[10px] font-black transition-all cursor-pointer border ${
                      selectedMonths === preset.m
                        ? "bg-emerald-500 text-black border-emerald-600 shadow-xs"
                        : "bg-zinc-100 dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 border-zinc-200 dark:border-zinc-800 hover:border-emerald-500/60"
                    }`}
                  >
                    {isAr ? preset.ar : preset.en}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ── INLINE PROMO / REFERRAL CODE INPUT ON MAIN PRICING VIEW ── */}
        {!appliedPromo && (
          <div className="max-w-xl mx-auto rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/90 dark:bg-zinc-900/70 px-4 py-3 flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 shadow-sm">
            <label htmlFor="pricing-main-promo" className="text-xs font-black text-zinc-700 dark:text-zinc-300 whitespace-nowrap flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-emerald-500 shrink-0" />
              <span>{isAr ? "عندك كود إحالة أو خصم؟" : "Have a referral or promo code?"}</span>
            </label>
            <div className="flex flex-1 gap-2">
              <input
                id="pricing-main-promo"
                type="text"
                value={promoInput}
                onChange={(e) => setPromoInput(e.target.value.toUpperCase())}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && promoInput.trim()) {
                    e.preventDefault();
                    applyPromoCode(promoInput, false, false);
                  }
                }}
                placeholder={isAr ? "أدخل الكود مثل: AMR15" : "Enter code e.g. AMR15"}
                className="flex-1 min-w-0 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-950 px-3 py-2 font-mono text-xs font-black uppercase text-zinc-950 dark:text-white outline-none focus:ring-2 focus:ring-emerald-500"
                dir="ltr"
              />
              <button
                type="button"
                onClick={() => applyPromoCode(promoInput, false, false)}
                disabled={promoChecking || !promoInput.trim()}
                className="rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black px-4 py-2 text-xs font-black uppercase tracking-wider transition-colors disabled:opacity-50 cursor-pointer shrink-0"
              >
                {promoChecking ? (isAr ? "جاري التحقق..." : "Checking...") : (isAr ? "تطبيق" : "Apply")}
              </button>
            </div>
          </div>
        )}

        {/* ── 3 CORE CARDS: AI CHAT ONLY | PRO BUNDLE | VIP RADAR (hidden for UAE/Qatar) ── */}
        <div className={`grid gap-6 items-stretch ${isGccChatOnly ? "lg:grid-cols-2 max-w-4xl mx-auto" : "lg:grid-cols-3"}`}>
          {/* ── 01. AI Chat Pro Only Card (100 EGP/mo * duration multiplier; Hero for UAE/Qatar) ── */}
          {(() => {
            const chatPricing = computeCheckoutPricing(chatDurationPricing.totalEgp, appliedPromo?.discount_percent || 0, market);
            const chatHasPromo = chatPricing.discountDisplay > 0;
            const durationText = formatDurationLabel(selectedMonths, isAr);
            return (
              <div
                className={
                  isChatHeroForGcc
                    ? "rounded-2xl border-2 border-emerald-500 bg-white dark:bg-zinc-900/95 p-6 sm:p-7 space-y-6 flex flex-col justify-between relative shadow-2xl shadow-emerald-500/15 ring-1 ring-emerald-500/30 transition-all duration-300"
                    : "rounded-2xl border border-zinc-200 dark:border-zinc-800/80 bg-white dark:bg-zinc-900/60 p-6 sm:p-7 space-y-6 flex flex-col justify-between shadow-sm hover:border-sky-500/60 transition-all"
                }
              >
                {isChatHeroForGcc && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                    <span className="rounded-full bg-emerald-500 text-black text-xs font-black uppercase px-4 py-1 tracking-wider shadow-md shadow-emerald-500/30 whitespace-nowrap flex items-center gap-1.5">
                      {selectedMonths === 1
                        ? (isAr ? `⭐ الباقة الأنسب لسوق ${isUae ? "الإمارات" : "قطر"} · شات ومحفظة` : `⭐ Best for ${isUae ? "UAE" : "Qatar"} · AI & Portfolio`)
                        : selectedMonths === 6
                        ? (isAr ? `⭐ ${brandName} AI Pro · 6 شهور (خصم 17%)` : `⭐ ${brandName} AI Pro · 6 Months (-17%)`)
                        : selectedMonths === 12
                        ? (isAr ? `💎 ${brandName} AI Pro · سنة كاملة (خصم 25%)` : `💎 ${brandName} AI Pro · 1 Year (-25%)`)
                        : (isAr ? `⭐ ${brandName} AI Pro · ${durationText} (خصم ${chatDurationPricing.discountPct}%)` : `⭐ ${brandName} AI Pro · ${durationText} (-${chatDurationPricing.discountPct}%)`)}
                    </span>
                  </div>
                )}

                <div className={`space-y-5${isChatHeroForGcc ? " pt-1" : ""}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <h3 className="text-2xl font-black text-zinc-950 dark:text-white flex items-center gap-2">
                        <Bot className={`w-5 h-5 shrink-0 ${isChatHeroForGcc ? "text-emerald-500" : "text-sky-500"}`} />
                        <span>{isChatHeroForGcc ? `${brandName} AI Pro` : (isAr ? "شات الذكاء الاصطناعي فقط" : "AI Chat Pro Only")}</span>
                      </h3>
                      <span className="text-xs font-bold text-zinc-500 block mt-0.5">
                        {isChatHeroForGcc
                          ? (isAr ? `الشات الذكي + Vision AI + المحفظة · ${durationText} (${chatDurationPricing.days} يوماً)` : `AI Chat + Vision AI + Portfolio · ${durationText} (${chatDurationPricing.days} days)`)
                          : (isAr ? `تحليل فوري بالشات · ${durationText} (${chatDurationPricing.days} يوماً)` : `Pure AI chat · ${durationText} (${chatDurationPricing.days} days)`)}
                      </span>
                    </div>
                    <span className={`text-[10px] font-black uppercase px-2.5 py-1 rounded-lg border shrink-0 ${
                      isChatHeroForGcc
                        ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                        : "border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400"
                    }`}>
                      {isChatHeroForGcc ? "AI PRO" : "CHAT PRO"}
                    </span>
                  </div>

                  <div className="border-b border-zinc-200 dark:border-zinc-800/80 pb-5">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="text-4xl sm:text-5xl font-black text-zinc-950 dark:text-white">
                        {chatPricing.finalDisplay.toLocaleString()}
                      </span>
                      <span className="text-sm font-bold text-zinc-500">{currencyLabel} / {durationText}</span>
                      {(chatHasPromo || selectedMonths > 1) && (
                        <span className="ms-2 text-lg font-black text-zinc-400 line-through decoration-red-500/80 decoration-2">
                          {formatPrice(chatHasPromo ? chatDurationPricing.totalEgp : chatDurationPricing.undiscountedEgp)}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 mt-2">
                      <span className="text-xs font-bold text-zinc-600 dark:text-zinc-400">
                        {isAr
                          ? `ما يعادل ${formatPrice(chatDurationPricing.effectiveMonthlyEgp)} / شهر`
                          : `${formatPrice(chatDurationPricing.effectiveMonthlyEgp)}/mo effective`}
                      </span>
                      {chatDurationPricing.discountPct > 0 && (
                        <span className={`rounded-md border px-2 py-0.5 text-xs font-black ${
                          isChatHeroForGcc
                            ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                            : "border-sky-500/30 bg-sky-500/15 text-sky-700 dark:text-sky-300"
                        }`}>
                          {isAr ? `وفر ${chatDurationPricing.discountPct}%` : `Save ${chatDurationPricing.discountPct}%`}
                        </span>
                      )}
                    </div>
                    {chatHasPromo && appliedPromo && (
                      <div className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-[11px] font-black text-emerald-700 dark:text-emerald-300">
                        <Sparkles className="w-3 h-3 shrink-0" />
                        <span>
                          {isAr
                            ? `🎁 خصم كود (${appliedPromo.code}) -${appliedPromo.discount_percent}%`
                            : `🎁 Promo (${appliedPromo.code}) -${appliedPromo.discount_percent}%`}
                        </span>
                      </div>
                    )}
                    <p className="text-xs font-semibold text-zinc-500 mt-2">
                      {isChatHeroForGcc
                        ? (isAr ? `مصممة لمستثمري ${isUae ? "الإمارات" : "قطر"} الباحثين عن الشات الذكي وتحليل المحفظة` : `Tailored for ${isUae ? "UAE" : "Qatar"} investors focused on AI Chat & portfolio analysis`)
                        : (isAr ? "أنسب خطة لمن يعتمد على التحليل الكمي والشات بالموقع" : "Best if you only need site AI analysis & portfolio tools")}
                    </p>
                  </div>

                  <div className="space-y-3">
                    <span className="text-[11px] font-black uppercase tracking-wider text-zinc-400 block">
                      {isAr ? "ما تشمله باقة الشات:" : "INCLUDED IN AI CHAT PRO:"}
                    </span>
                    <ul className="space-y-3.5">
                      {chatOnlyFeatures.map((f, i) => (
                        <li
                          key={i}
                          className={`flex items-start gap-2.5 text-xs sm:text-[13px] font-medium leading-snug ${
                            f.included
                              ? "text-zinc-800 dark:text-zinc-200"
                              : "text-zinc-400 dark:text-zinc-500 line-through decoration-zinc-400/70"
                          }`}
                        >
                          <span className="shrink-0 mt-0.5">
                            {f.included ? (
                              <Check className={`w-4 h-4 ${isChatHeroForGcc ? "text-emerald-500" : "text-sky-500"}`} />
                            ) : (
                              <X className="w-4 h-4 text-zinc-400 dark:text-zinc-500" />
                            )}
                          </span>
                          <span>{f.text}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="pt-4 space-y-2">
                  <button
                    type="button"
                    disabled={isLifetimeActive || isFullProActive}
                    onClick={() => openPaymentStep(isVipOnlyActive ? "pro" : "chat_only")}
                    className={
                      isLifetimeActive || isFullProActive
                        ? "w-full flex items-center justify-center gap-2 rounded-xl py-3.5 px-4 text-xs sm:text-sm font-black uppercase tracking-wider border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800/70 text-zinc-500 dark:text-zinc-400 cursor-not-allowed"
                        : isChatHeroForGcc
                        ? "w-full flex items-center justify-center gap-2 rounded-xl py-4 px-4 text-xs sm:text-sm font-black uppercase tracking-wider shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30 hover:-translate-y-0.5 active:translate-y-0 transition-all cursor-pointer bg-emerald-500 hover:bg-emerald-400 text-black"
                        : "w-full flex items-center justify-center gap-2 rounded-xl py-3.5 px-4 text-xs sm:text-sm font-black uppercase tracking-wider border-2 border-sky-500/40 bg-sky-500/10 hover:bg-sky-500 hover:text-black text-sky-700 dark:text-sky-300 transition-all cursor-pointer"
                    }
                  >
                    <Bot className="w-4 h-4" />
                    <span>
                      {isLifetimeActive || isFullProActive
                        ? (isAr ? "مشمولة بالفعل في باقتك الحالية ✓" : "Already included in your active plan ✓")
                        : isVipOnlyActive
                        ? (isAr ? "ترقية للشاملة Pro (شات + VIP معاً دون فقدان أيامك)" : "Upgrade to Full Bundle Pro (keeps remaining days)")
                        : isChatHeroForGcc
                        ? (isAr
                            ? `${isChatOnlyActive ? "تجديد" : "اشترك في"} ${brandName} AI Pro — ${durationText} (${chatPricing.finalDisplay.toLocaleString()} ${currencyLabel})`
                            : `${isChatOnlyActive ? "Renew" : "Get"} ${brandName} AI Pro — ${durationText} (${chatPricing.finalDisplay.toLocaleString()} ${currencyLabel})`)
                        : (isAr
                            ? `${isChatOnlyActive ? "تجديد باقة الشات" : "اشترك في الشات"} — ${durationText} (${chatPricing.finalDisplay.toLocaleString()} ${currencyLabel})`
                            : `${isChatOnlyActive ? "Renew AI Chat" : "Get AI Chat"} — ${durationText} (${chatPricing.finalDisplay.toLocaleString()} ${currencyLabel})`)}
                    </span>
                  </button>
                  <div className="flex items-center justify-center gap-1.5 text-[10px] font-bold text-zinc-500">
                    <ShieldCheck className={`w-3.5 h-3.5 ${isChatHeroForGcc ? "text-emerald-500" : "text-sky-500"}`} />
                    <span>{isAr ? "تفعيل فوري عبر EasyKash" : "Instant activation via EasyKash"}</span>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* ── 02. Pro Full Bundle Card (The Hero Tier for EGX/Saudi/Founders; Secondary All-Markets + VIP for UAE/Qatar) ── */}
          {(() => {
            const isFeatured = selectedMonths === 6;
            const isAnnual = selectedMonths === 12;
            const isMonthly = selectedMonths === 1;
            const hasFounderRate = isGrandfathered || isGrandfathered100 || foundersIsOpen;
            const proCardPricing = computeCheckoutPricing(
              proDurationPricing.totalEgp,
              appliedPromo?.discount_percent || 0,
              market,
            );
            const proCardHasPromo = proCardPricing.discountDisplay > 0;
            const founderTierRate = isGrandfathered ? 50 : 100;
            const durationText = formatDurationLabel(selectedMonths, isAr);
            const showBundleCompare = !isGccChatOnly && isMonthly && !hasFounderRate && !proCardHasPromo && proMonthlyBase < 200;
            const strikeOriginalEgp = proCardHasPromo
              ? proDurationPricing.totalEgp
              : hasFounderRate
              ? proRegularDurationPricing.totalEgp
              : selectedMonths > 1
              ? proDurationPricing.undiscountedEgp
              : showBundleCompare
              ? 200
              : null;

            return (
              <div
                id="pro-plan-card"
                ref={proCardRef}
                className={
                  isChatHeroForGcc
                    ? "scroll-mt-48 rounded-2xl border border-zinc-200 dark:border-zinc-800/80 bg-white dark:bg-zinc-900/60 p-6 sm:p-7 space-y-6 flex flex-col justify-between shadow-sm hover:border-emerald-500/60 transition-all"
                    : "scroll-mt-48 rounded-2xl border-2 border-emerald-500 bg-white dark:bg-zinc-900/95 p-6 sm:p-7 space-y-6 flex flex-col justify-between relative shadow-2xl shadow-emerald-500/15 ring-1 ring-emerald-500/30 transition-all duration-300"
                }
              >
                {/* Floating Top Badge */}
                {!isChatHeroForGcc && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                    <span className="rounded-full bg-emerald-500 text-black text-xs font-black uppercase px-4 py-1 tracking-wider shadow-md shadow-emerald-500/30 whitespace-nowrap flex items-center gap-1.5">
                      {hasFounderRate ? (
                        foundersCountdown && !isGrandfathered && isMonthly
                          ? `عرض المؤسسين ${formatPrice(100)} (ينتهي خلال ⏰ ${foundersCountdown})`
                          : isAr
                          ? `🔒 سعر المؤسسين (${formatPrice(founderTierRate)}/ش${proDurationPricing.discountPct > 0 ? ` · خصم ${proDurationPricing.discountPct}%` : ""})`
                          : `🔒 Founders (${formatPrice(founderTierRate)}/mo${proDurationPricing.discountPct > 0 ? ` · -${proDurationPricing.discountPct}%` : ""})`
                      ) : isMonthly ? (
                        isGccChatOnly
                          ? (isAr ? "⭐ الباقة الأكثر طلباً · شات ومؤشرات ومحفظة" : "⭐ Most Popular · AI Chat & Portfolio")
                          : (isAr ? `⭐ الباقة الشاملة · الأفضل قيمة (وفر ${formatPrice(50)})` : "⭐ Full Bundle · Best Value (Save 25%)")
                      ) : isFeatured ? (
                        (isAr ? "⭐ الباقة الشاملة · 6 شهور (خصم 17%)" : "⭐ Full Bundle · 6 Months (-17%)")
                      ) : isAnnual ? (
                        (isAr ? "💎 الباقة الشاملة · سنة كاملة (أكبر توفير 25%)" : "💎 Full Bundle · 1 Year (-25%)")
                      ) : (
                        (isAr ? `⭐ الباقة الشاملة · ${durationText} (خصم ${proDurationPricing.discountPct}%)` : `⭐ Full Bundle · ${durationText} (-${proDurationPricing.discountPct}%)`)
                      )}
                    </span>
                  </div>
                )}

                <div className={`space-y-5${!isChatHeroForGcc ? " pt-1" : ""}`}>
                  {/* Header & Tag */}
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <h3 className="text-2xl font-black text-zinc-950 dark:text-white flex items-center gap-2">
                        <Crown className="w-5 h-5 text-emerald-500 shrink-0" />
                        <span>
                          {isChatHeroForGcc
                            ? (isAr ? "باقة كل الأسواق الشاملة (+ تليجرام VIP)" : "All-Markets Pro (+ VIP Telegram)")
                            : (isAr ? `${brandName} Pro الشاملة` : `${brandName} Pro Bundle`)}
                        </span>
                      </h3>
                      <span className="text-xs font-bold text-zinc-500 block mt-0.5">
                        {isChatHeroForGcc
                          ? (isAr ? `كل مزايا الشات + قنوات VIP للسعودية ومصر · ${durationText} (${proDurationPricing.days} يوماً)` : `Full AI Chat + Saudi TASI & Egypt EGX VIP Channels · ${durationText} (${proDurationPricing.days} days)`)
                          : isGccChatOnly
                          ? (isAr ? `الشات الذكي + Vision AI + المحفظة + VIP · ${durationText} (${proDurationPricing.days} يوماً)` : `AI Chat + Vision AI + Portfolio + VIP · ${durationText} (${proDurationPricing.days} days)`)
                          : (isAr ? `الشات الذكي + تليجرام VIP معاً · ${durationText} (${proDurationPricing.days} يوماً)` : `AI Chat + VIP Telegram together · ${durationText} (${proDurationPricing.days} days)`)}
                      </span>
                    </div>
                    <span className="text-xs font-black rounded-lg border border-emerald-500/30 px-2.5 py-1 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 shrink-0">
                      {isChatHeroForGcc ? "ALL MARKETS + VIP" : "BUNDLE PRO"}
                    </span>
                  </div>

                  {/* Price Section */}
                  <div className="border-b border-zinc-200 dark:border-zinc-800/80 pb-5">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="text-4xl sm:text-5xl font-black text-zinc-950 dark:text-white">
                        {proCardPricing.finalDisplay.toLocaleString()}
                      </span>
                      <span className="text-sm font-bold text-zinc-500">{currencyLabel} / {durationText}</span>
                      {strikeOriginalEgp !== null && (
                        <span className="ms-2 text-lg sm:text-xl font-black text-zinc-400 dark:text-zinc-500 line-through decoration-red-500/80 decoration-2">
                          {isAr ? "بدل " : "was "}
                          {formatPrice(strikeOriginalEgp)}
                        </span>
                      )}
                    </div>

                    {proCardHasPromo && appliedPromo && (
                      <div className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-[11px] font-black text-emerald-700 dark:text-emerald-300">
                        <Sparkles className="w-3 h-3 shrink-0" />
                        <span>
                          {isAr
                            ? `🎁 مطبق خصم كود (${appliedPromo.code}) -${appliedPromo.discount_percent}%`
                            : `🎁 Promo (${appliedPromo.code}) -${appliedPromo.discount_percent}% applied`}
                        </span>
                      </div>
                    )}

                    <div className="flex flex-wrap items-center gap-2 mt-2">
                      <span className="text-xs font-bold text-zinc-600 dark:text-zinc-400">
                        {isAr
                          ? `ما يعادل ${formatPrice(proDurationPricing.effectiveMonthlyEgp)} / شهر`
                          : `${currencyCode} ${displayAmount(proDurationPricing.effectiveMonthlyEgp).toLocaleString()}/mo`}
                      </span>
                      {showBundleCompare ? (
                        <span className="rounded-md border border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 text-xs font-black">
                          {isAr ? `وفر ${formatPrice(50)} (25%)` : "Save 25% vs Split"}
                        </span>
                      ) : proDurationPricing.discountPct > 0 ? (
                        <span className="rounded-md border border-emerald-500/30 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 px-2 py-0.5 text-xs font-black">
                          {isAr ? `توفير ${proDurationPricing.discountPct}%` : `${proDurationPricing.discountPct}% OFF`}
                        </span>
                      ) : null}
                    </div>
                    {isChatHeroForGcc && (
                      <p className="text-xs font-semibold text-zinc-500 mt-2">
                        {isAr
                          ? `مخصصة لمن يتابع السوق السعودي (تداول TASI) أو المصري (EGX) بجانب ${isUae ? "الإمارات" : "قطر"}`
                          : `Built for investors tracking Saudi (TASI) or Egypt (EGX) alongside ${isUae ? "UAE" : "Qatar"}`}
                      </p>
                    )}
                  </div>

                  {/* Founding perk callout across all Pro durations */}
                  {(foundersIsOpen || isGrandfathered || isGrandfathered100) && (
                    <div className="rounded-xl bg-amber-50 dark:bg-amber-950/20 border border-amber-500/30 p-3.5 space-y-1 text-black dark:text-amber-200">
                      <div className="flex items-center gap-1.5 text-xs font-black text-amber-900 dark:text-amber-300">
                        <Clock className="w-3.5 h-3.5" />
                        <span>{isAr ? "🔒 ميزة المؤسسين الأوائل (تثبيت السعر مدى الحياة):" : "🔒 Founding Member Lifetime Price Lock:"}</span>
                      </div>
                      <p className="text-[11px] font-semibold leading-relaxed text-zinc-800 dark:text-zinc-300">
                        {isGccChatOnly
                          ? (isAr
                            ? `بصفتك من المؤسسين الأوائل، تحصل على باقة الشات الذكي وأدوات المحفظة + قنوات تليجرام VIP للسعودية ومصر مدى الحياة بسعر المؤسسين المحفوظ.`
                            : `As an early founder, you lock your Founding Member rate for AI Chat Pro, portfolio tools & Saudi TASI / Egypt EGX VIP Telegram channels for life.`)
                          : selectedMonths > 1
                          ? (isAr
                            ? `باشتراكك لمدة ${durationText} (${formatPrice(proDurationPricing.totalEgp)} بدلاً من ${formatPrice(proRegularDurationPricing.totalEgp)}) يظل حسابك مثبتاً على تسعير المؤسسين الشامل للباقتين معاً.`
                            : `Subscribing for ${durationText} (${formatPrice(proDurationPricing.totalEgp)} instead of ${formatPrice(proRegularDurationPricing.totalEgp)}) preserves your Founding Member status across both AI Chat + VIP Radar.`)
                          : isGrandfathered
                          ? (isAr
                            ? `${formatPrice(50)} شهرياً (سعر المؤسسين المستمر للباقة الشاملة ما دمت مجدداً أو خلال مهلة الـ 72 ساعة).`
                            : `${formatPrice(50)}/mo grandfathered Full Bundle rate active for your account as long as renewed.`)
                          : isGrandfathered100 && !foundersIsOpen
                          ? (isAr
                            ? `${formatPrice(100)} شهرياً (سعر المؤسسين المثبت للباقة الشاملة ما دمت مجدداً أو خلال مهلة الـ 72 ساعة).`
                            : `${formatPrice(100)}/mo grandfathered Full Bundle rate active for your account as long as renewed.`)
                          : (isAr
                            ? `${formatPrice(100)} شهرياً عرض باقة المؤسسين الشاملة — يثبّت سعرك بـ ${formatPrice(100)} مدى الحياة مع مهلة سماح 72 ساعة عند كل تجديد.`
                            : `${formatPrice(100)}/mo founders offer — locks your ${formatPrice(100)}/mo Full Bundle rate for life with 72h renewal grace period.`)}
                      </p>
                    </div>
                  )}

                  {/* Features List */}
                  <div className="space-y-3">
                    <span className="text-[11px] font-black uppercase tracking-wider text-zinc-500 dark:text-zinc-400 block">
                      {isChatHeroForGcc
                        ? (isAr ? "مزايا الشات + قنوات تليجرام VIP:" : "AI CHAT + VIP TELEGRAM INCLUDED:")
                        : isGccChatOnly
                        ? (isAr ? "مزايا الباقة الشاملة:" : "INCLUDED IN PRO:")
                        : (isAr ? "كل ما في الشات + تليجرام VIP معاً:" : "BOTH AI CHAT + VIP RADAR INCLUDED:")}
                    </span>
                    <ul className="space-y-3.5">
                      {proFeatures.map((f, i) => (
                        <li key={i} className="flex items-start gap-2.5 text-xs sm:text-[13px] font-medium leading-snug text-zinc-800 dark:text-zinc-200">
                          <span className="shrink-0 mt-0.5 text-emerald-500">{f.icon || <Check className="w-3.5 h-3.5" />}</span>
                          <span>{f.text}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Button */}
                <div className="pt-4 space-y-2">
                  <button
                    type="button"
                    disabled={isLifetimeActive}
                    onClick={() => openPaymentStep("pro")}
                    className={
                      isLifetimeActive
                        ? "w-full flex items-center justify-center gap-2 rounded-xl py-3.5 px-4 text-xs sm:text-sm font-black uppercase tracking-wider border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800/70 text-zinc-500 dark:text-zinc-400 cursor-not-allowed"
                        : isChatHeroForGcc
                        ? "w-full flex items-center justify-center gap-2 rounded-xl py-3.5 px-4 text-xs sm:text-sm font-black uppercase tracking-wider border-2 border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500 hover:text-black text-emerald-700 dark:text-emerald-300 transition-all cursor-pointer"
                        : "w-full flex items-center justify-center gap-2 rounded-xl py-4 px-4 text-xs sm:text-sm font-black uppercase tracking-wider shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30 hover:-translate-y-0.5 active:translate-y-0 transition-all cursor-pointer bg-emerald-500 hover:bg-emerald-400 text-black"
                    }
                  >
                    <LockKeyhole className="w-3.5 h-3.5" />
                    {isLifetimeActive
                      ? (isAr ? "عضويتك الدائمة مفعّلة للأبد 👑" : "Lifetime VIP active forever 👑")
                      : (isChatOnlyActive || isVipOnlyActive)
                      ? (isAr ? `ترقية للشاملة (مع حفظ أيامك) — ${durationText} (${proCardPricing.finalDisplay.toLocaleString()} ${currencyLabel})` : `Upgrade to Full Bundle (keeps days) — ${durationText} (${proCardPricing.finalDisplay.toLocaleString()} ${currencyLabel})`)
                      : isFullProActive
                      ? (isAr ? `تجديد الباقة الشاملة — ${durationText} (${proCardPricing.finalDisplay.toLocaleString()} ${currencyLabel})` : `Renew Bundle — ${durationText} (${proCardPricing.finalDisplay.toLocaleString()} ${currencyLabel})`)
                      : (isAr ? `اشترك في الباقة الشاملة — ${durationText} (${proCardPricing.finalDisplay.toLocaleString()} ${currencyLabel})` : `Get Full Bundle — ${durationText} (${proCardPricing.finalDisplay.toLocaleString()} ${currencyLabel})`)}
                  </button>
                  <div className="flex items-center justify-center gap-2 text-[10px] font-bold text-zinc-500">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                    <span>{isAr ? "دفع رسمي مشفر عبر EasyKash · تفعيل فوري" : "Encrypted checkout via EasyKash · Instant unlock"}</span>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* ── 03. VIP Telegram Radar Only Card (100 EGP/mo * duration multiplier; hidden for UAE/Qatar) ── */}
          {!isGccChatOnly && (() => {
            const vipPricing = computeCheckoutPricing(vipDurationPricing.totalEgp, appliedPromo?.discount_percent || 0, market);
            const vipHasPromo = vipPricing.discountDisplay > 0;
            const durationText = formatDurationLabel(selectedMonths, isAr);
            return (
              <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800/80 bg-white dark:bg-zinc-900/60 p-6 sm:p-7 space-y-6 flex flex-col justify-between shadow-sm hover:border-teal-500/60 transition-all">
                <div className="space-y-5">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <h3 className="text-2xl font-black text-zinc-950 dark:text-white flex items-center gap-2">
                        <Send className="w-5 h-5 text-teal-500 shrink-0" />
                        <span>{isAr ? "قنوات تليجرام VIP فقط" : "VIP Telegram Only"}</span>
                      </h3>
                      <span className="text-xs font-bold text-zinc-500 block mt-0.5">
                        {isAr ? `تنبيهات الرادار والقنوات الفورية · ${durationText} (${vipDurationPricing.days} يوماً)` : `Live Telegram radar · ${durationText} (${vipDurationPricing.days} days)`}
                      </span>
                    </div>
                    <span className="text-[10px] font-black uppercase px-2.5 py-1 rounded-lg border border-teal-500/30 bg-teal-500/10 text-teal-600 dark:text-teal-400 shrink-0">
                      VIP RADAR
                    </span>
                  </div>

                  <div className="border-b border-zinc-200 dark:border-zinc-800/80 pb-5">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="text-4xl sm:text-5xl font-black text-zinc-950 dark:text-white">
                        {vipPricing.finalDisplay.toLocaleString()}
                      </span>
                      <span className="text-sm font-bold text-zinc-500">{currencyLabel} / {durationText}</span>
                      {(vipHasPromo || selectedMonths > 1) && (
                        <span className="ms-2 text-lg font-black text-zinc-400 line-through decoration-red-500/80 decoration-2">
                          {formatPrice(vipHasPromo ? vipDurationPricing.totalEgp : vipDurationPricing.undiscountedEgp)}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 mt-2">
                      <span className="text-xs font-bold text-zinc-600 dark:text-zinc-400">
                        {isAr
                          ? `ما يعادل ${formatPrice(vipDurationPricing.effectiveMonthlyEgp)} / شهر`
                          : `${formatPrice(vipDurationPricing.effectiveMonthlyEgp)}/mo effective`}
                      </span>
                      {vipDurationPricing.discountPct > 0 && (
                        <span className="rounded-md border border-teal-500/30 bg-teal-500/15 text-teal-700 dark:text-teal-300 px-2 py-0.5 text-xs font-black">
                          {isAr ? `وفر ${vipDurationPricing.discountPct}%` : `Save ${vipDurationPricing.discountPct}%`}
                        </span>
                      )}
                    </div>
                    {vipHasPromo && appliedPromo && (
                      <div className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-[11px] font-black text-emerald-700 dark:text-emerald-300">
                        <Sparkles className="w-3 h-3 shrink-0" />
                        <span>
                          {isAr
                            ? `🎁 خصم كود (${appliedPromo.code}) -${appliedPromo.discount_percent}%`
                            : `🎁 Promo (${appliedPromo.code}) -${appliedPromo.discount_percent}%`}
                        </span>
                      </div>
                    )}
                    <p className="text-xs font-semibold text-zinc-500 mt-2">
                      {isAr ? "أنسب خطة لمن يتابع تنبيهات السيولة والزخم على تليجرام فقط" : "Best if you only want real-time Telegram radar alerts"}
                    </p>
                  </div>

                  <div className="space-y-3">
                    <span className="text-[11px] font-black uppercase tracking-wider text-zinc-400 block">
                      {isAr ? "ما تشمله باقة تليجرام VIP:" : "INCLUDED IN VIP RADAR:"}
                    </span>
                    <ul className="space-y-3.5">
                      {vipOnlyFeatures.map((f, i) => (
                        <li
                          key={i}
                          className={`flex items-start gap-2.5 text-xs sm:text-[13px] font-medium leading-snug ${
                            f.included
                              ? "text-zinc-800 dark:text-zinc-200"
                              : "text-zinc-400 dark:text-zinc-500 line-through decoration-zinc-400/70"
                          }`}
                        >
                          <span className="shrink-0 mt-0.5">
                            {f.included ? (
                              <Check className="w-4 h-4 text-teal-500" />
                            ) : (
                              <X className="w-4 h-4 text-zinc-400 dark:text-zinc-500" />
                            )}
                          </span>
                          <span>{f.text}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="pt-4 space-y-2">
                  <button
                    type="button"
                    disabled={isLifetimeActive || isFullProActive}
                    onClick={() => openPaymentStep(isChatOnlyActive ? "pro" : "vip_only")}
                    className={
                      isLifetimeActive || isFullProActive
                        ? "w-full flex items-center justify-center gap-2 rounded-xl py-3.5 px-4 text-xs sm:text-sm font-black uppercase tracking-wider border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800/70 text-zinc-500 dark:text-zinc-400 cursor-not-allowed"
                        : "w-full flex items-center justify-center gap-2 rounded-xl py-3.5 px-4 text-xs sm:text-sm font-black uppercase tracking-wider border-2 border-teal-500/40 bg-teal-500/10 hover:bg-teal-500 hover:text-black text-teal-700 dark:text-teal-300 transition-all cursor-pointer"
                    }
                  >
                    <Send className="w-4 h-4" />
                    <span>
                      {isLifetimeActive || isFullProActive
                        ? (isAr ? "مشمولة بالفعل في باقتك الحالية ✓" : "Already included in your active plan ✓")
                        : isChatOnlyActive
                        ? (isAr ? "ترقية للشاملة Pro (شات + VIP معاً دون فقدان أيامك)" : "Upgrade to Full Bundle Pro (keeps remaining days)")
                        : (isAr
                            ? `${isVipOnlyActive ? "تجديد تليجرام VIP" : "اشترك في تليجرام VIP"} — ${durationText} (${vipPricing.finalDisplay.toLocaleString()} ${currencyLabel})`
                            : `${isVipOnlyActive ? "Renew VIP Radar" : "Get VIP Radar"} — ${durationText} (${vipPricing.finalDisplay.toLocaleString()} ${currencyLabel})`)}
                    </span>
                  </button>
                  <div className="flex items-center justify-center gap-1.5 text-[10px] font-bold text-zinc-500">
                    <ShieldCheck className="w-3.5 h-3.5 text-teal-500" />
                    <span>{isAr ? "رابط دعوة شخصي فوري لمرة واحدة" : "Instant single-use Telegram VIP invite"}</span>
                  </div>
                </div>
              </div>
            );
          })()}
        </div>

        {/* ── COMPACT HORIZONTAL LIFETIME VIP DEAL STRIP ── */}
        {(() => {
          const lifetimePricing = computeCheckoutPricing(2250, appliedPromo?.discount_percent || 0, market);
          const lifetimeHasPromo = lifetimePricing.discountDisplay > 0;
          return (
            <div className="rounded-2xl border-2 border-amber-400/80 dark:border-amber-500/40 bg-gradient-to-r from-amber-50/90 via-white to-amber-50/40 dark:from-amber-950/25 dark:via-zinc-900/95 dark:to-zinc-900 p-5 sm:p-6 shadow-md flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
              <div className="space-y-2.5 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full bg-gradient-to-r from-amber-400 to-yellow-400 text-black text-[11px] font-black uppercase">
                    <Crown className="w-3.5 h-3.5 fill-black" />
                    {lifetimeIsOpen
                      ? (isAr ? `العضوية الدائمة · متبقي ${lifetimeRemaining} من ${lifetimeLimit} مقعداً` : `Lifetime VIP · ${lifetimeRemaining}/${lifetimeLimit} Spots Left`)
                      : (isAr ? "اكتملت المقاعد (Sold Out)" : "Sold Out (20/20)")}
                  </span>
                  <span className="text-[11px] font-bold text-amber-800 dark:text-amber-300">
                    {isAr ? "دفعة واحدة لـ 36,500 يوم · بدون أي تجديد مستقبلي" : "One-time payment · 36,500 days · Zero renewals"}
                  </span>
                </div>

                <div className="flex flex-wrap items-baseline gap-3">
                  <h3 className="text-xl sm:text-2xl font-black text-zinc-950 dark:text-white flex items-center gap-2">
                    <Crown className="w-5 h-5 text-amber-500 shrink-0" />
                    <span>{isAr ? `${brandName} Lifetime VIP الشاملة مدى الحياة` : `${brandName} Lifetime VIP Bundle`}</span>
                  </h3>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-2xl sm:text-3xl font-black text-amber-700 dark:text-amber-300">
                      {lifetimePricing.finalDisplay.toLocaleString()}
                    </span>
                    <span className="text-xs font-bold text-zinc-600 dark:text-zinc-400">{currencyLabel}</span>
                    {lifetimeHasPromo && (
                      <span className="text-sm font-black text-zinc-400 line-through">
                        {formatPrice(2250)}
                      </span>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 pt-1">
                  {lifetimeFeatures.slice(0, 3).map((f, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs font-medium text-zinc-700 dark:text-zinc-300">
                      <span className="shrink-0 mt-0.5 text-amber-500">{f.icon || <Check className="w-3.5 h-3.5" />}</span>
                      <span>{f.text}</span>
                    </div>
                  ))}
                </div>
                <p className="text-[11px] font-semibold text-zinc-600 dark:text-zinc-400">
                  {isGccChatOnly
                    ? (isAr
                        ? `نقطة التعادل خلال ${breakevenMonths} شهر فقط من الباقة الشهرية — وبعدها يبقى الشات الذكي وأدوات المحفظة مفعلة للأبد.`
                        : `Breaks even in ~${breakevenMonths} months — then AI Chat & portfolio tools stay unlocked permanently.`)
                    : (isAr
                        ? `نقطة التعادل خلال ${breakevenMonths} شهر فقط من الباقة الشاملة — وبعدها تبقى كامل أدوات المنصة وقنوات VIP مفعلة للأبد.`
                        : `Breaks even in ~${breakevenMonths} months of the Full Pro Bundle — then all tools & VIP channels stay unlocked permanently.`)}
                </p>
              </div>

              <div className="w-full lg:w-auto shrink-0 space-y-2 lg:min-w-[240px]">
                <button
                  type="button"
                  disabled={!lifetimeIsOpen || isLifetimeActive}
                  onClick={() => openPaymentStep("lifetime")}
                  className={`w-full flex items-center justify-center gap-2 rounded-xl py-3.5 px-5 text-xs sm:text-sm font-black uppercase tracking-wider shadow-md transition-all ${
                    lifetimeIsOpen && !isLifetimeActive
                      ? "bg-gradient-to-r from-amber-400 to-yellow-400 hover:from-amber-300 hover:to-yellow-300 text-black cursor-pointer"
                      : "bg-zinc-200 dark:bg-zinc-800 text-zinc-400 dark:text-zinc-500 cursor-not-allowed"
                  }`}
                >
                  <Crown className="w-4 h-4 fill-current" />
                  <span>
                    {isLifetimeActive
                      ? (isAr ? "عضويتك الدائمة مفعّلة للأبد 👑" : "Lifetime VIP Active Forever 👑")
                      : lifetimeIsOpen
                      ? isPro
                        ? (isAr ? `ترقية لمدى الحياة (${lifetimePricing.finalDisplay.toLocaleString()} ${currencyLabel})` : `Upgrade Lifetime (${lifetimePricing.finalDisplay.toLocaleString()} ${currencyLabel})`)
                        : (isAr ? `احجز مدى الحياة (${lifetimePricing.finalDisplay.toLocaleString()} ${currencyLabel}) 👑` : `Get Lifetime (${lifetimePricing.finalDisplay.toLocaleString()} ${currencyLabel}) 👑`)
                      : (isAr ? "اكتملت المقاعد (Sold Out)" : "Sold Out (20/20)")}
                  </span>
                </button>
              </div>
            </div>
          );
        })()}

        {/* ── COMPACT FREE PLAN COMPARISON BAR (NO UNCLUTTERED NOISE) ── */}
        <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/70 dark:bg-zinc-900/40 p-5 sm:p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="space-y-2 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-base font-black text-zinc-950 dark:text-white">
                {isAr ? "الخطة المجانية (0 " + currencyLabel + ")" : `Free Plan (0 ${currencyLabel})`}
              </span>
              <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-zinc-600 dark:text-zinc-400">
                {isPro ? (isAr ? "متاحة" : "Available") : (isAr ? "الخطة الحالية" : "Current")}
              </span>
            </div>
            <div className="flex flex-wrap gap-x-5 gap-y-1.5">
              {freeFeatures.filter((f) => f.included).map((f, i) => (
                <div key={i} className="flex items-center gap-1.5 text-xs font-medium text-zinc-700 dark:text-zinc-300">
                  <Check className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                  <span>{f.text}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="w-full md:w-auto shrink-0 md:min-w-[210px]">
            {trialEligible && !isPro ? (
              <button
                type="button"
                onClick={handleStartTrial}
                disabled={trialLoading}
                className="w-full rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black py-3 px-4 text-xs font-black uppercase tracking-wider shadow-sm transition-all cursor-pointer flex items-center justify-center gap-2"
              >
                {trialLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                <span>{isAr ? "جرّب Pro مجاناً 3 أيام ⚡" : "Try Pro Free for 3 Days ⚡"}</span>
              </button>
            ) : (
              <button
                type="button"
                disabled
                className="w-full rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-zinc-500 py-3 px-4 text-xs font-bold uppercase tracking-wider cursor-not-allowed"
              >
                {isPro ? (isAr ? "الخطة المجانية متاحة" : "Free plan available") : (isAr ? "خطتك الحالية" : "Current Plan")}
              </button>
            )}
          </div>
        </div>

        {/* ── FRA REGULATORY & EASYKASH DISCLOSURE NOTE ── */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800/80 bg-zinc-50/50 dark:bg-zinc-900/30 px-4 py-3 text-[11px] font-medium text-zinc-600 dark:text-zinc-400 leading-relaxed flex items-start gap-2.5">
          <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
          <p>
            {isAr
              ? "إفصاح تنظيمي: الاشتراكات هي مقابل برمجيات وأدوات تحليل فني وكمي مؤتمتة (SaaS) لأغراض البحث والتعليم الشخصي فقط؛ لا تقدم المنصة استشارات مالية أو توصيات استثمارية مرخصة ولا تضمن أي عوائد. تتم جميع المدفوعات حصراً عبر بوابة EasyKash المعتمدة."
              : "Regulatory Notice: Subscriptions provide access solely to automated technical and quantitative SaaS software tools for personal research and analysis; the platform does not provide licensed financial advice, investment recommendations, or return guarantees. All payments are processed exclusively through EasyKash."}
          </p>
        </div>

          </>
        ) : (
          /* ── B2B CHANNELS & COMMUNITIES SECTION ── */
          <div className="space-y-8">
            {/* B2B Header Pitch Banner */}
            <div className="border-4 border-purple-600 dark:border-purple-400 bg-gradient-to-r from-purple-900 via-indigo-950 to-zinc-950 p-6 sm:p-8 text-white shadow-[8px_8px_0px_#a855f7] space-y-3">
              <div className="inline-flex items-center gap-2 px-3 py-1 border-2 border-yellow-400 bg-purple-900/80 text-yellow-300 text-xs font-black uppercase">
                <Crown className="w-4 h-4 text-yellow-300" />
                <span>{isAr ? "حلول الذكاء الاصطناعي للقنوات التحليلية والمجتمعات (B2B)" : "Enterprise AI for Analytical Channels & Communities (B2B)"}</span>
              </div>
              <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-white">
                {isAr ? "🤖 إيجار بوت التليجرام الذكي لقناتك أو مجموعتك المدفوعة" : `License ${brandName} Inside Your Telegram Group`}
              </h2>
              <p className="text-xs sm:text-sm text-zinc-300 font-semibold max-w-3xl leading-relaxed">
                {isAr
                  ? "وفّر ساعات الإجابة المتكررة عن أهداف ودعوم ومقاومات الأسهم، وامنح مشتركي قناتك تجربة ذكية فورية تعمل 24/7. البوت يقرأ معرف مجموعتك ويرد على أسئلة الأعضاء تلقائياً مع توقيع باسم قناتك لتعزيز هويتك التجارية."
                  : "Automate technical analysis and stock queries for your VIP channel members with instant AI answers and your custom branded signature footer on every response."}
              </p>
            </div>

            {/* 3-Day Free Trial Auto-Activation Banner */}
            <div className="border-4 border-black dark:border-white bg-gradient-to-r from-amber-400 via-amber-300 to-yellow-300 dark:from-amber-500/30 dark:via-zinc-900 dark:to-yellow-500/20 p-5 sm:p-6 shadow-[6px_6px_0px_rgba(0,0,0,1)] flex flex-col md:flex-row items-center justify-between gap-5">
              <div className="space-y-1.5 text-center md:text-start">
                <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 bg-black text-white text-[10px] font-black uppercase">
                  <Sparkles className="w-3 h-3 text-amber-300" />
                  <span>{isAr ? "تفعيل تلقائي بدون دفع مليم وبدون بطاقة" : "Instant Auto-Linking · Zero Card Required"}</span>
                </div>
                <h3 className="text-xl sm:text-2xl font-black text-zinc-950 dark:text-white">
                  {isAr ? `🎁 جرّب بوت ${brandName} في قناتك أو مجموعتك مجاناً لمدة 3 أيام` : "🎁 Try the Bot in Your Channel or Group Free for 3 Days"}
                </h3>
                <p className="text-xs font-bold text-zinc-800 dark:text-zinc-300 max-w-2xl leading-relaxed">
                  {isAr
                    ? "ربط آلي بالكامل بضغطة زر واحدة! بمجرد إضافة البوت لمجموعتك، يتعرف عليها تلقائياً ويبدأ بالرد على أسئلة الأعضاء بالتوقيع المخصص لقناتك."
                    : "1-click fully automated group linking! As soon as the bot is added, it binds to your group and starts answering member stock queries."}
                </p>
              </div>
              <button
                type="button"
                disabled={startingB2BTrial === "b2b_pro"}
                onClick={() => handleStartB2BTrial("b2b_pro")}
                className="shrink-0 inline-flex items-center gap-2 px-6 py-3.5 border-4 border-black bg-zinc-950 text-white hover:bg-black font-black text-xs uppercase shadow-[4px_4px_0px_#000] hover:-translate-y-0.5 active:translate-y-0 transition-transform cursor-pointer disabled:opacity-50"
              >
                {startingB2BTrial === "b2b_pro" ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Bot className="w-4 h-4 text-emerald-400" />
                )}
                <span>{isAr ? "ابدأ التجربة المجانية 3 أيام الآن ←" : "Start 3-Day Free Trial Now ←"}</span>
              </button>
            </div>

            {/* 3 B2B Cards Grid */}
            <div className="grid lg:grid-cols-3 gap-6 items-stretch">
              {b2bPlans.map((plan) => {
                const b2bCardPricing = computeCheckoutPricing(
                  plan.amount_egp,
                  appliedPromo?.discount_percent || 0,
                  market,
                );
                const b2bHasPromo = b2bCardPricing.discountDisplay > 0;
                return (
                  <div
                    key={plan.id}
                    className={`border-4 ${plan.border_class} ${
                      plan.is_featured
                        ? "bg-gradient-to-b from-emerald-50 via-white to-emerald-50/40 dark:from-emerald-950/40 dark:via-zinc-950 dark:to-emerald-950/20"
                        : "bg-white dark:bg-zinc-950"
                    } ${plan.shadow_class} p-6 sm:p-7 space-y-6 flex flex-col justify-between relative transition-all`}
                  >
                    {/* Top Floating Badge */}
                    <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                      <span className={`border-2 border-black text-xs font-black uppercase px-3 py-0.5 tracking-wider shadow-[2px_2px_0px_rgba(0,0,0,1)] whitespace-nowrap flex items-center gap-1.5 ${
                        plan.is_featured ? "bg-emerald-400 text-black" : "bg-amber-300 text-black"
                      }`}>
                        {plan.is_featured && <Flame className="w-3.5 h-3.5 fill-black" />}
                        {isAr ? plan.badge_ar : plan.badge_en}
                      </span>
                    </div>

                    <div className="space-y-5 pt-1">
                      {/* Card Title & Tag */}
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-xl sm:text-2xl font-black text-zinc-950 dark:text-white flex items-center gap-2">
                            <span>{isAr ? plan.name_ar : plan.name_en}</span>
                          </h3>
                          <span className="text-xs font-bold text-zinc-500 block mt-0.5">
                            {isAr ? `سعة المجموعة: ${plan.max_members}` : plan.badge_en}
                          </span>
                        </div>
                        <span className={`text-[10px] font-black border-2 border-black dark:border-white px-2 py-0.5 ${
                          plan.is_featured ? "bg-emerald-500 text-white" : "bg-zinc-200 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200"
                        }`}>
                          {plan.tag}
                        </span>
                      </div>

                      {/* Price Section */}
                      <div className="border-b-2 border-zinc-200 dark:border-zinc-800 pb-5">
                        <div className="flex flex-wrap items-baseline gap-2">
                          <span className="text-4xl sm:text-5xl font-black text-zinc-950 dark:text-white">
                            {b2bCardPricing.finalDisplay.toLocaleString()}
                          </span>
                          <span className="text-sm font-bold text-zinc-500">{isAr ? `${currencyLabel} / شهرياً` : `${currencyCode} / mo`}</span>
                          {b2bHasPromo && (
                            <span className="ms-1 text-lg font-black text-zinc-400 line-through decoration-red-500/80 decoration-2">
                              {formatPrice(plan.amount_egp)}
                            </span>
                          )}
                        </div>
                        {b2bHasPromo && appliedPromo && (
                          <div className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-[11px] font-black text-emerald-700 dark:text-emerald-300">
                            <Sparkles className="w-3 h-3 shrink-0" />
                            <span>
                              {isAr
                                ? `🎁 خصم كود (${appliedPromo.code}) -${appliedPromo.discount_percent}%`
                                : `🎁 Promo (${appliedPromo.code}) -${appliedPromo.discount_percent}%`}
                            </span>
                          </div>
                        )}
                        <div className="flex flex-wrap items-center gap-2 mt-2">
                          <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                            <Zap className="w-3.5 h-3.5" />
                            {isAr ? `كوتة يومية: ${plan.daily_limit} استفسار (~${plan.monthly_est}/شهر)` : `${plan.daily_limit} queries/day (~${plan.monthly_est}/mo)`}
                          </span>
                        </div>
                      </div>

                      {/* Features List */}
                      <div className="space-y-3">
                        <span className="text-[11px] font-black uppercase tracking-wider text-zinc-500 dark:text-zinc-400 block">
                          {isAr ? "الميزات والضوابط المشمولة:" : "INCLUDED IN PLAN:"}
                        </span>
                        <ul className="space-y-3">
                          {plan.features.map((f, i) => (
                            <li key={i} className="flex items-start gap-2.5 text-xs font-bold leading-tight text-zinc-800 dark:text-zinc-200">
                              <span className="shrink-0 mt-0.5 text-emerald-500">{f.icon}</span>
                              <span>{f.text}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    {/* Action Button */}
                    <div className="pt-4 space-y-2">
                      <button
                        type="button"
                        onClick={() => openPaymentStep(plan.id)}
                        className={`w-full flex items-center justify-center gap-2 border-4 border-black dark:border-white py-4 px-4 text-xs font-black uppercase tracking-wider shadow-[3px_3px_0px_#000] hover:-translate-y-0.5 active:translate-y-0 transition-all cursor-pointer ${plan.btn_class}`}
                      >
                        <Rocket className="w-4 h-4 shrink-0" />
                        <span>{isAr ? `اشترك في ${plan.name_ar} (${b2bCardPricing.finalDisplay.toLocaleString()} ${currencyLabel})` : `Subscribe to ${plan.name_en} (${b2bCardPricing.finalDisplay.toLocaleString()} ${currencyCode})`}</span>
                      </button>
                      <div className="flex items-center justify-center gap-2 text-[10px] font-bold text-zinc-500">
                        <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                        <span>{isAr ? "تفعيل فوري · ربط مباشر للجروب" : "Instant Activation · Dedicated Setup"}</span>
                      </div>
                      <button
                        type="button"
                        disabled={startingB2BTrial === plan.id}
                        onClick={() => handleStartB2BTrial(plan.id)}
                        className="w-full flex items-center justify-center gap-2 border-2 border-black dark:border-white bg-amber-400 hover:bg-amber-300 text-black py-2.5 px-3 text-xs font-black uppercase tracking-wider shadow-[2px_2px_0px_#000] transition-transform active:scale-95 cursor-pointer disabled:opacity-50"
                      >
                        {startingB2BTrial === plan.id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Sparkles className="w-3.5 h-3.5" />
                        )}
                        <span>{isAr ? "🎁 ابدأ تجربة مجانية 3 أيام لجروبك" : "🎁 Start 3-Day Free Trial"}</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* How B2B Works 3-Step Guide */}
            <div className="border-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900/60 p-6 sm:p-8 shadow-[6px_6px_0px_rgba(0,0,0,1)]">
              <h3 className="text-lg font-black text-zinc-950 dark:text-white mb-6 text-center">
                {isAr ? "⚡ كيف يعمل ترخيص البوت لمجموعتك في 3 خطوات بسيطة؟" : "⚡ How Channel Bot Licensing Works in 3 Simple Steps"}
              </h3>
              <div className="grid sm:grid-cols-3 gap-6">
                <div className="border-2 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 space-y-2 shadow-[2px_2px_0px_#000]">
                  <div className="w-8 h-8 rounded-full border-2 border-black bg-amber-400 text-black font-black flex items-center justify-center text-sm">
                    1
                  </div>
                  <h4 className="text-sm font-black text-zinc-900 dark:text-white">
                    {isAr ? "اشترك في الباقة المناسبة" : "Select Your Tier"}
                  </h4>
                  <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed font-semibold">
                    {isAr
                      ? isGulfPricing
                        ? "اختر باقة تناسب حجم قناتك ومعدل الاستفسارات اليومي، وادفع بسهولة عبر بوابة EasyKash بالبطاقة الدولية (Visa / Mastercard عبر 3D Secure)."
                        : "اختر باقة تناسب حجم قناتك ومعدل الاستفسارات اليومي، وادفع بسهولة عبر EasyKash (بطاقة بنكية أو محفظة إلكترونية أو فوري)."
                      : "Choose Starter, Pro VIP, or Enterprise based on your community size and pay securely via EasyKash."}
                  </p>
                </div>

                <div className="border-2 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 space-y-2 shadow-[2px_2px_0px_#000]">
                  <div className="w-8 h-8 rounded-full border-2 border-black bg-emerald-400 text-black font-black flex items-center justify-center text-sm">
                    2
                  </div>
                  <h4 className="text-sm font-black text-zinc-900 dark:text-white">
                    {isAr ? "أضف البوت لجروبك" : "Add Bot to Group"}
                  </h4>
                  <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed font-semibold">
                    {isAr ? "أضف البوت الرسمي @egxbots_bot إلى مجموعتك وارفع صلاحياته لمشرف (Admin) ليتعرف على رسائل الأعضاء." : "Add @egxbots_bot as an admin in your group or supergroup."}
                  </p>
                </div>

                <div className="border-2 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 space-y-2 shadow-[2px_2px_0px_#000]">
                  <div className="w-8 h-8 rounded-full border-2 border-black bg-sky-400 text-black font-black flex items-center justify-center text-sm">
                    3
                  </div>
                  <h4 className="text-sm font-black text-zinc-900 dark:text-white">
                    {isAr ? "حدد توقيع قناتك المخصص" : "Set Custom Signature"}
                  </h4>
                  <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed font-semibold">
                    {isAr ? `اكتب من لوحة تحكمك سطر التوقيع الذي تريده أسفل كل رد (مثلاً: «تحليلات قناة الأستاذ فلان بالتعاون مع ${brandName}»).` : "Set your custom branding footer that appears below every analysis in your group."}
                  </p>
                </div>
              </div>

              {/* Direct WhatsApp Consultation */}
              <div className="mt-6 pt-6 border-t border-zinc-300 dark:border-zinc-800 text-center space-y-3">
                <p className="text-xs sm:text-sm font-bold text-zinc-700 dark:text-zinc-300">
                  {isAr ? "لديك متطلبات خاصة، قنوات متعددة، أو تحتاج تجربة حية للبوت في جروبك أولاً؟" : "Have custom requirements, multiple channels, or need a live trial in your group?"}
                </p>
                <a
                  href="https://wa.me/201024359109?text=مرحباً، أود الاستفسار عن باقات بوت التليجرام B2B للقنوات والمجموعات"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-6 py-3 border-3 border-black dark:border-white bg-[#FFE600] hover:bg-yellow-400 text-black text-xs font-black uppercase shadow-[3px_3px_0px_#000] hover:-translate-y-0.5 transition-all"
                >
                  <MessageSquare className="w-4 h-4" />
                  <span>{isAr ? "تواصل معنا مباشرة عبر واتساب لتخصيص الباقة 💬" : "WhatsApp Custom Setup Desk"}</span>
                </a>
              </div>
            </div>
          </div>
        )}

        {/* Notice: Market Data & Regulatory Position */}
        <div className="rounded-2xl border border-amber-300 dark:border-amber-500/30 bg-amber-50/70 dark:bg-gradient-to-r dark:from-zinc-900/90 dark:via-zinc-900/95 dark:to-amber-950/20 p-6 shadow-sm dark:shadow-xl dark:shadow-black/20">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className="p-3 rounded-xl border border-amber-300 dark:border-amber-500/30 bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 shrink-0 shadow-sm">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <h4 className="text-sm sm:text-base font-black text-zinc-950 dark:text-white">
                  {isAr ? "خلاصة الموقف القانوني وطبيعة التحليلات الفنية" : "Legal Notice on Market Data & Quantitative Models"}
                </h4>
                <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-400 border border-amber-300 dark:border-amber-500/30">
                  {isAr ? "الهيئة العامة للرقابة المالية (قانون 95 لسنة 1992)" : "FRA Regulatory Notice"}
                </span>
              </div>
              <p className="text-xs sm:text-[13px] font-medium text-zinc-800 dark:text-zinc-300 leading-relaxed">
                {isAr
                  ? `منصة ${brandName} هي شركة وأداة برمجيات مالية (FinTech SaaS) وليست وسيط تداول أو مستشاراً مالياً معتمداً من الهيئة العامة للرقابة المالية (FRA). المنصة لا تدير أموالاً ولا تتلقى ودائع ولا تضمن أي أرباح. مخرجات الذكاء الاصطناعي والإشارات الفنية هي مؤشرات إحصائية مؤتمتة لأغراض البحث والدراسة الذاتية، وقرار التداول يقع على عاتق المستثمر وحده عبر وسيطه المرخص.`
                  : `${brandName} is a FinTech Software-as-a-Service (SaaS) provider and not a broker or financial advisor certified by the FRA. The platform does not manage funds, receive deposits, or guarantee returns. All algorithmic signals and technical indicators are statistical tools for educational and personal research purposes only.`}
              </p>
              <div className="pt-1">
                <Link
                  href="/legal-status"
                  className="inline-flex items-center gap-1.5 text-xs font-black text-amber-800 dark:text-amber-400 hover:text-amber-950 dark:hover:text-amber-300 transition-colors"
                  prefetch={false}
                >
                  <span>{isAr ? "اقرأ بيان الموقف القانوني والتنظيمي الكامل للمنصة ←" : "Read our full Legal & Regulatory Compliance Statement →"}</span>
                </Link>
              </div>
            </div>
          </div>
        </div>

        {/* Guarantee Banner */}
        <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/80 dark:bg-zinc-900/50 p-6 sm:p-8 backdrop-blur-sm shadow-sm">
          <div className="grid sm:grid-cols-3 gap-6 text-center">
            <div className="space-y-2">
              <div className="w-12 h-12 rounded-xl border border-amber-300 dark:border-amber-500/30 bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-500 flex items-center justify-center mx-auto shadow-sm">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-black text-zinc-950 dark:text-white">
                {isAr ? "دفع رسمي ومعتمد" : "Certified Gateway"}
              </h4>
              <p className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                {isAr
                  ? isGulfPricing
                    ? "عبر بوابة EasyKash المشفرة — تدعم بطاقات Visa / Mastercard الدولية في السعودية والخليج"
                    : "عبر بوابة EasyKash المشفرة برخصة البنك المركزي المصري"
                  : isGulfPricing
                  ? "Encrypted 256-bit checkout via EasyKash — supports international Visa & Mastercard in Saudi & GCC"
                  : "Licensed 256-bit encrypted checkout via Central Bank of Egypt"}
              </p>
            </div>

            <div className="space-y-2">
              <div className="w-12 h-12 rounded-xl border border-emerald-300 dark:border-emerald-500/30 bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-500 flex items-center justify-center mx-auto shadow-sm">
                <Zap className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-black text-zinc-950 dark:text-white">
                {isAr ? "تفعيل تلقائي ولحظي" : "Instant Activation"}
              </h4>
              <p className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                {isGccChatOnly
                  ? (isAr ? "يتم فتح صلاحيات الشات الذكي فوراً بعد إتمام الدفع آلياً" : "AI Chat perks unlock instantly upon automated payment")
                  : (isAr ? "يتم فتح الصلاحيات وتوليد رابط VIP فور اكتمال الدفع آلياً" : "Pro perks unlock instantly upon automated payment")}
              </p>
            </div>

            <div className="space-y-2">
              <div className="w-12 h-12 rounded-xl border border-sky-300 dark:border-sky-500/30 bg-sky-100 text-sky-700 dark:bg-sky-500/10 dark:text-sky-400 flex items-center justify-center mx-auto shadow-sm">
                <HelpCircle className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-black text-zinc-950 dark:text-white">
                {isAr ? "دعم مستمر عبر واتساب" : "WhatsApp Support"}
              </h4>
              <p className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                {isAr ? "فريقنا متواجد للإجابة على أي استفسارات 01024359109" : "Direct human assistance anytime: 01024359109"}
              </p>
            </div>
          </div>
        </div>
        {/* ── AFFILIATE & ADVERTISING PARTNERSHIPS BANNER ── */}
        <div className="rounded-2xl border border-emerald-200 dark:border-emerald-500/30 bg-gradient-to-r from-emerald-50/80 via-teal-50/50 to-emerald-50/80 dark:from-emerald-950/30 dark:via-zinc-900/90 dark:to-teal-950/30 p-6 sm:p-8 shadow-sm dark:shadow-lg space-y-4">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="space-y-2 text-center md:text-start max-w-2xl">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-300 dark:border-emerald-500/30 bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-400 text-xs font-black uppercase">
                <Sparkles className="w-3.5 h-3.5" />
                <span>{isAr ? "برنامج الشركاء والرعاية الإعلانية" : "Affiliate & Media Partnerships"}</span>
              </div>
              <h3 className="text-xl sm:text-2xl font-black text-zinc-950 dark:text-white">
                {isAr
                  ? isSaudi
                    ? "اربح 25% كاش شهرياً أو أعلن أمام آلاف المتداولين في السوق السعودي (تداول)"
                    : isUae
                    ? "اربح 25% كاش شهرياً أو أعلن أمام آلاف المتداولين في سوق الإمارات (دبي وأبوظبي)"
                    : isQatar
                    ? "اربح 25% كاش شهرياً أو أعلن أمام آلاف المتداولين في بورصة قطر"
                    : "اربح 25% كاش شهرياً أو أعلن أمام آلاف المتداولين في البورصة المصرية"
                  : isSaudi
                  ? "Earn 25% Recurring Cash or Advertise to Thousands of Active Saudi TASI Traders"
                  : isUae
                  ? "Earn 25% Recurring Cash or Advertise to Thousands of Active UAE (DFM & ADX) Investors"
                  : isQatar
                  ? "Earn 25% Recurring Cash or Advertise to Thousands of Active Qatar (QSE) Investors"
                  : "Earn 25% Recurring Cash or Advertise to Thousands of Active EGX Traders"}
              </h3>
              <p className="text-xs sm:text-sm font-medium text-zinc-700 dark:text-zinc-300 leading-relaxed">
                {isAr
                  ? (isGccChatOnly
                      ? "هل تدير مجتمعاً استثمارياً أو صفحة مالية؟ انضم لبرنامج التسويق بالعمولة واربح 25% كاش شهرياً عن كل مشترك مستمر."
                      : "هل تدير قناة تليجرام، صفحة فيسبوك، أو منصة استثمارية؟ انضم لبرنامج التسويق بالعمولة واربح 25% كاش شهرياً عن كل مشترك مستمر، أو احجز مساحات رعاية إعلانية ذكية في تقاريرنا اليومية ورادار الأسهم.")
                  : isSaudi
                  ? "Manage a trading group, media channel, or financial community? Join our 25% recurring affiliate program or sponsor our daily market outlook reports reaching active Saudi TASI investors."
                  : "Manage a trading group, media channel, or financial community? Join our 25% recurring affiliate program or sponsor our daily market outlook reports reaching active investors."}
              </p>
            </div>
            <div className="flex flex-col sm:flex-row md:flex-col gap-3 w-full md:w-auto shrink-0">
              <a
                href={`https://wa.me/201024359109?text=${encodeURIComponent(`مرحباً، أود الاستفسار عن الشراكة الإعلانية وبرنامج الأفلييت مع ${brandName}`)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-2 rounded-xl py-3.5 px-6 text-xs font-black uppercase tracking-wider bg-emerald-500 hover:bg-emerald-400 text-black shadow-md shadow-emerald-500/20 hover:shadow-emerald-500/30 hover:-translate-y-0.5 transition-all text-center"
              >
                <MessageSquare className="w-4 h-4" />
                <span>{isAr ? "تواصل للشراكة عبر واتساب 💬" : "WhatsApp Partnership Desk"}</span>
              </a>
              <Link
                href="/affiliate"
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-300 dark:border-zinc-700 py-2.5 px-4 text-xs font-black bg-white dark:bg-zinc-800 text-zinc-900 dark:text-white shadow-sm hover:bg-zinc-50 dark:hover:bg-zinc-700 transition-all text-center"
                prefetch={false}
              >
                <span>{isAr ? "صفحة نظام الأفلييت (25%) ←" : "Affiliate Program Details →"}</span>
              </Link>
            </div>
          </div>
        </div>
      </div>
      {/* B2B 3-Day Free Trial Success Modal */}
      {b2bTrialModal?.open && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 max-w-lg w-full p-6 sm:p-8 shadow-[8px_8px_0px_#000] dark:shadow-[8px_8px_0px_#fff] space-y-6 relative" dir={isAr ? "rtl" : "ltr"}>
            <button
              onClick={() => setB2bTrialModal(null)}
              className="absolute top-4 left-4 border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 p-1.5 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200"
              aria-label="Close"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="text-center space-y-2">
              <div className="w-16 h-16 border-4 border-black dark:border-white bg-amber-300 text-black flex items-center justify-center mx-auto shadow-[4px_4px_0px_#000]">
                <Bot className="w-8 h-8" />
              </div>
              <h3 className="text-2xl font-black text-zinc-900 dark:text-white">
                {isAr ? "🎉 مبروك! تم تفعيل رخصتك التجريبية (3 أيام)" : "🎉 Congrats! 3-Day Trial Activated"}
              </h3>
              <p className="text-xs sm:text-sm font-bold text-zinc-600 dark:text-zinc-400">
                {isAr
                  ? "الآن اربط البوت بمجموعتك أو قناتك على تليجرام بضغطة زر واحدة وسيتم التفعيل آلياً بدون أي خطوات إضافية:"
                  : "Now connect the bot to your Telegram group with 1 click. Linking is 100% automated!"}
              </p>
            </div>

            <div className="space-y-4">
              <a
                href={b2bTrialModal.connectUrl}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => {
                  toast.success(isAr ? "جاري فتح تليجرام لاختيار المجموعة..." : "Opening Telegram...");
                }}
                className="w-full flex items-center justify-center gap-3 border-4 border-black bg-emerald-500 hover:bg-emerald-400 text-black py-4 px-4 text-sm font-black uppercase tracking-wider shadow-[4px_4px_0px_#000] hover:-translate-y-0.5 active:translate-y-0 transition-transform text-center"
              >
                <Bot className="w-5 h-5 shrink-0" />
                <span>{isAr ? "🚀 ربط وتفعيل البوت في مجموعتي فوراً (تليجرام)" : "🚀 1-Click Auto-Activate Bot on Telegram"}</span>
              </a>

              <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800 p-3.5 space-y-2 text-xs">
                <span className="font-bold text-zinc-500 block">
                  {isAr ? "💡 كيف يعمل الربط الآلي؟" : "💡 How does auto-linking work?"}
                </span>
                <p className="text-[11px] text-zinc-700 dark:text-zinc-300 font-semibold leading-relaxed">
                  {isAr
                    ? "عند الضغط على الزر أعلاه، سيفتح تليجرام لتختار مجموعتك. فور إضافة البوت ورفعه مشرفاً، سيتعرف البوت على مجموعتك تلقائياً ويرسل رسالة التفعيل والترحيب ويبدأ في الرد على الأعضاء فوراً!"
                    : "Clicking above opens Telegram to pick your group. Once added as admin, the bot automatically binds your group, posts a welcome greeting, and starts answering questions!"}
                </p>
              </div>

              <div className="flex items-center justify-between text-xs pt-2">
                <Link
                  href="/b2b/dashboard"
                  onClick={() => setB2bTrialModal(null)}
                  className="font-black text-emerald-600 dark:text-emerald-400 hover:underline"
                  prefetch={false}
                >
                  {isAr ? "الانتقال إلى لوحة تحكم البوت (B2B Dashboard) ←" : "Go to B2B Dashboard ←"}
                </Link>
                <span className="font-mono text-[11px] text-zinc-400">
                  Code: {b2bTrialModal.code}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

