"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAuth } from "@/contexts/AuthContext";
import { prepareTrialAutostart, clearTrialAutostart, TRIAL_AUTOSTART_EVENT } from "@/lib/trial-onboarding";
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
} from "lucide-react";
import { toast } from "sonner";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import { trackEvent } from "@/lib/gtm";

import { broadcastEntitlements } from "@/lib/entitlements";
export { broadcastEntitlements };

type Step = "plans" | "payment" | "submitted";

export default function PricingClient() {
  const { language } = useLanguage();
  const isAr = language === "ar";
  const { user } = useAuth();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [localConfig, setLocalConfig] = useState<any>(null);
  const [localOrder, setLocalOrder] = useState<string | null>(null);
  const [customerMobile, setCustomerMobile] = useState("");
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
  const [subscriptionEnd, setSubscriptionEnd] = useState<string | null>(null);
  const [telegramProUrl, setTelegramProUrl] = useState("");
  const [isPro, setIsPro] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState("pro");
  const [activeProDuration, setActiveProDuration] = useState<"pro" | "pro_6m" | "pro_1y">("pro");
  const proCardRef = useRef<HTMLDivElement>(null);
  const [promoInput, setPromoInput] = useState("");
  const [appliedPromo, setAppliedPromo] = useState<{ code: string; name: string; discount_percent: number } | null>(null);
  const [promoChecking, setPromoChecking] = useState(false);

  const [trialEligible, setTrialEligible] = useState(false);
  const [trialLoading, setTrialLoading] = useState(false);
  const [trialExpiresAt, setTrialExpiresAt] = useState<string | null>(null);
  const [pricingCategory, setPricingCategory] = useState<"retail" | "b2b">("retail");

  useEffect(() => {
    if (!user) {
      setTrialEligible(true);
      return;
    }
    let active = true;
    fetch("/api/subscription/trial", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (active && data?.eligible) {
          setTrialEligible(true);
        } else if (active) {
          setTrialEligible(false);
          if (data?.expires_at) setTrialExpiresAt(data.expires_at);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [user]);

  const handleStartTrial = async () => {
    if (!user) {
      router.push("/login?redirect=/pricing");
      return;
    }
    setTrialLoading(true);
    try {
      const variant = prepareTrialAutostart();
      const res = await fetch("/api/subscription/trial", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ variant }),
      });
      const data = await res.json();
      if (res.ok && data?.success) {
        toast.success(isAr ? "تم تفعيل تجربة Pro المجانية لمدة 3 أيام بنجاح!" : "Pro 3-day trial activated successfully!");
        setIsPro(true);
        broadcastEntitlements(true);
        setTrialEligible(false);
        setTrialExpiresAt(data.expires_at || null);
        // Open the assistant and ask the first question instead of leaving the
        // new subscriber on the pricing page with an unused trial.
        window.dispatchEvent(new CustomEvent(TRIAL_AUTOSTART_EVENT));
      } else {
        clearTrialAutostart();
        toast.error(data?.message || (isAr ? "تعذر تفعيل التجربة" : "Could not activate trial"));
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
      const planParam = params.get("plan");
      if (planParam && ["pro", "pro_6m", "pro_1y", "lifetime", "b2b_starter", "b2b_pro", "b2b_enterprise"].includes(planParam)) {
        setSelectedPlan(planParam);
        if (["pro", "pro_6m", "pro_1y"].includes(planParam)) {
          setActiveProDuration(planParam as "pro" | "pro_6m" | "pro_1y");
          setPricingCategory("retail");
        }
        if (["b2b_starter", "b2b_pro", "b2b_enterprise"].includes(planParam)) {
          setPricingCategory("b2b");
        }
      }
    }
  }, []);

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
          setCustomerMobile(data.whatsapp_number);
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

  const normalizedMobile = customerMobile.trim().replace(/[\s-]/g, "").replace(/^\+20/, "0").replace(/^0020/, "0");
  const isMobileValid = /^01[0125]\d{8}$/.test(normalizedMobile);

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
        if (!telegramProUrl) {
          const vip = await fetch("/api/profile/telegram-pro", { cache: "no-store", signal: AbortSignal.timeout(12_000) })
            .then((r) => (r.ok ? r.json() : null))
            .catch(() => null);
          if (!stopped && vip?.invite_link) setTelegramProUrl(vip.invite_link);
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
        if (settledStatus === "approved") {
          setIsPro(true);
          broadcastEntitlements(true);
        }
        if (data.plan_id) setSelectedPlan(data.plan_id);
        setSubscriptionEnd(data.subscription?.current_period_end || null);
        setTelegramProUrl(data.telegram_pro_url || "");
        if (settledStatus === "approved" && !data.telegram_pro_url) {
          const vip = await fetch("/api/profile/telegram-pro", { cache: "no-store", signal: AbortSignal.timeout(12_000) })
            .then((response) => (response.ok ? response.json() : null))
            .catch(() => null);
          if (!stopped && vip?.invite_link) {
            setTelegramProUrl(vip.invite_link);
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
  }, [step, localOrder, pollRestart, isPro, telegramProUrl]);

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
        const response = await fetch(
          user ? "/api/payment/easykash/config" : "/api/payment/public-config",
          {
            headers,
            // Anonymous visitors share one CDN-cached document; signed-in
            // visitors need their own grandfathered/promo state, so only that
            // request must bypass the cache.
            cache: user ? "no-store" : "default",
          }
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
    trackEvent("pricing_view", { signed_in: Boolean(user?.id) });
  }, [user?.id]);

  useEffect(() => {
    if (!user) {
      setIsPro(false);
      setSubscriptionEnd(null);
      return;
    }
    let active = true;
    let inFlight = false;
    const refreshPlan = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const response = await fetch("/api/user/quota");
        if (!response.ok) return;
        const data = await response.json();
        if (!active) return;
        const proActive = data?.plan?.is_pro === true;
        setIsPro(proActive);
        setSubscriptionEnd(data?.plan?.current_period_end || null);
        if (proActive) {
          broadcastEntitlements(true);
        }
      } catch {
        // Keep the last known state on a temporary network failure.
      } finally {
        inFlight = false;
      }
    };
    setIsPro(false);
    void refreshPlan();
    const onFocus = () => void refreshPlan();
    const onVisible = () => {
      if (document.visibilityState === "visible") void refreshPlan();
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

  const handleDurationSelect = (id: "pro" | "pro_6m" | "pro_1y", shouldScroll = false) => {
    setActiveProDuration(id);
    setSelectedPlan(id);
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
      toast.error(isAr ? "أدخل رقم موبايل مصري صحيح من أي شبكة (010 / 011 / 012 / 015)" : "Enter a valid Egyptian mobile number");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/payment/easykash/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plan_id: planId,
          mobile: normalizedMobile,
          promo_code: appliedPromo?.code || "",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || (isAr ? "تعذر إنشاء طلب الدفع" : "Could not start checkout"));
      setLocalOrder(data.order_id);
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
          {isAr ? "خطط وأسعار باقات EGX BOTS" : "EGX BOTS Subscription Plans & Pricing"}
        </h1>
        <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
      </div>
    );
  }

  if (!localConfig) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center p-6 text-center space-y-4 font-bold text-zinc-900 dark:text-white">
        <h1 className="text-xl sm:text-2xl font-black">
          {isAr ? "خطط وأسعار باقات EGX BOTS" : "EGX BOTS Subscription Plans & Pricing"}
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
  const monthlyPrice = Number(monthlyDiscount?.original_amount_egp ?? localConfig?.plans?.find((item: any) => item.id === "pro")?.amount_egp ?? 200);
  const paidPlans = [
    { id: "pro", name_ar: "شهر واحد", name_en: "1 Month", days: 30, amount_egp: 200, badge: null, isLifetime: false },
    { id: "pro_6m", name_ar: "6 شهور", name_en: "6 Months", days: 180, amount_egp: 1000, badge: isAr ? "الأكثر طلباً ⭐" : "Most Popular ⭐", isLifetime: false },
    { id: "pro_1y", name_ar: "سنة كاملة", name_en: "1 Year", days: 365, amount_egp: 1850, badge: isAr ? "أكبر توفير 💎" : "Max Value 💎", isLifetime: false },
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
    let amount = Number(configured?.amount_egp ?? plan.amount_egp);
    let originalAmount: number | null = configured?.discount?.original_amount_egp
      ? Number(configured.discount.original_amount_egp)
      : null;
    if (plan.id === "pro") {
      if (isGrandfathered) {
        amount = 50;
        originalAmount = monthlyPrice || 200;
      } else if (isGrandfathered100) {
        amount = 100;
        originalAmount = monthlyPrice || 200;
      } else if (!foundersIsOpen) {
        amount = monthlyPrice || 200;
        originalAmount = null;
      } else {
        amount = 100;
        originalAmount = monthlyPrice || 200;
      }
    } else if (plan.id === "pro_6m") {
      const hasFounder6m = foundersIsOpen || isGrandfathered || isGrandfathered100;
      amount = hasFounder6m ? 500 : 1000;
      originalAmount = hasFounder6m ? 1000 : null;
    } else if (plan.id === "pro_1y") {
      const hasFounder1y = foundersIsOpen || isGrandfathered || isGrandfathered100;
      amount = hasFounder1y ? 1000 : 1850;
      originalAmount = hasFounder1y ? 1850 : null;
    }
    const days = Number(configured?.days ?? plan.days);
    const monthlyEquivalent = plan.isLifetime ? null : Math.round((amount / days) * 30);
    const unbundledBase = (days / 30) * (monthlyPrice || 200);
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
        { text: isAr ? "تحليل فني ومالي لجميع أسهم البورصة المصرية بلحظة" : "Instant AI analysis for all 280+ EGX stocks", icon: <BarChart3 className="w-3.5 h-3.5" /> },
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
  ];

  const allAvailablePlans = [...paidPlans, ...b2bPlans];
  const selectedPlanDetails = allAvailablePlans.find((plan: any) => plan.id === selectedPlan) || paidPlans[0];
  const activeProDetails = paidPlans.find((plan: any) => plan.id === activeProDuration) || paidPlans[0];
  const baseProPrice = selectedPlanDetails?.amount_egp ?? (paidPlans[0]?.amount_egp || 100);
  const promoDiscountAmount =
    appliedPromo && appliedPromo.discount_percent > 0
      ? Math.min(Math.max(0, baseProPrice - 20), Math.round((baseProPrice * appliedPromo.discount_percent) / 100))
      : 0;
  const proPrice = Math.max(20, baseProPrice - promoDiscountAmount);
  const freeLimits = localConfig.limits?.free || { signal_delay_days: 15, chat_messages_per_month: 10, portfolio_stocks: 5 };
  const proLimits = localConfig.limits?.pro || { chat_messages_per_month: 350, portfolio_stocks: 10 };
  const chartFeatures = [
    { icon: <BarChart3 className="w-4 h-4" />, text: isAr ? "معمل الشارت: حتى 8 نوافذ، مؤشرات واستراتيجيات ومقارنة تاريخية" : "Chart workspace: up to 8 panels, indicators, strategies and historical comparison", included: true },
    { icon: <Sparkles className="w-4 h-4" />, text: isAr ? "تحليل AI من الشارت حسب السهم والاستراتيجيات والمؤشرات المختارة — ضمن حصة رسائل خطتك" : "AI chart analysis based on your selected stock, strategies and indicators — within your plan's chat allowance", included: true },
  ];
  const freeFeatures = [
    { icon: <Zap className="w-4 h-4" />, text: isAr ? `تأخير الإشارات المتوسطة ${freeLimits.signal_delay_days} يوماً` : `Medium swings delayed ${freeLimits.signal_delay_days} days`, included: true },
    { icon: <Zap className="w-4 h-4" />, text: isAr ? "الصفقات القصيرة ⚡ PRO (متاحة بأرشيف متأخر 15 يوماً فقط)" : "Short Swings ⚡ PRO (15-day delayed archive only)", included: false },
    { icon: <MessageSquare className="w-4 h-4" />, text: isAr ? "10 رسائل شات بوت شهرياً (لتجربة تحليل الأسهم)" : "10 chatbot messages / month (stock analysis trial)", included: true },
    { icon: <Sparkles className="w-4 h-4" />, text: isAr ? "التوصيات المفتوحة وإشارات الدخول الحية في الشات 🔒 PRO" : "Open Recommendations & Live Entry Signals in Chat 🔒 PRO", included: false },
    { icon: <Sparkles className="w-4 h-4" />, text: isAr ? "رفع وتحليل صور المحفظة والشارت بالذكاء الاصطناعي (Vision AI) 📸 PRO" : "Portfolio & Chart Image Analysis (Vision AI) 📸 PRO", included: false },
    ...chartFeatures,
    { icon: <BarChart3 className="w-4 h-4" />, text: isAr ? `حتى ${freeLimits.portfolio_stocks} أسهم في المحفظة` : `Up to ${freeLimits.portfolio_stocks} portfolio stocks`, included: true },
    { icon: <Activity className="w-4 h-4" />, text: isAr ? "النشاط غير الطبيعي (أسهم ارتفع حجمها بشكل غير طبيعي)" : "Unusual Activity (volume spike detection)", included: false },
    { icon: <ShieldCheck className="w-4 h-4" />, text: isAr ? "قناة تليجرام الفورية (تنبيهات فنية ومؤشرات الخوارزميات)" : "Instant Telegram Channel (daily technical signals)", included: false },
    { icon: <BellRing className="w-4 h-4" />, text: isAr ? "رادار وتنبيهات الإسكانر الفورية على تليجرام (سيولة واختراقات)" : "Live Telegram Scanner Alerts (Volume & Breakouts)", included: false },
    { icon: <Clock className="w-4 h-4" />, text: isAr ? "أتمتة استشارات الذكاء الاصطناعي اليومية المجدولة عبر تليجرام" : "Daily Scheduled Telegram AI Chat Automations", included: false },
  ];

  const proFeatures = [
    { icon: <ShieldCheck className="w-4 h-4" />, text: isAr ? "قناة تليجرام الفورية (تنبيهات فنية وخوارزمية فورية بدون تأخير)" : "Instant Telegram Channel (daily algorithmic signals without delay)", included: true },
    { icon: <Zap className="w-4 h-4" />, text: isAr ? "الصفقات القصيرة ⚡ PRO — صفقات زخم، وقف صارم 4%، وتتبع أرباح EMA10 بدون تشفير" : "Short Swings ⚡ PRO — momentum trades, tight 4% stop, and EMA10 runners unmasked", included: true },
    { icon: <BellRing className="w-4 h-4 text-amber-500 fill-amber-500" />, text: isAr ? "رادار وتنبيهات الإسكانر الفورية على تليجرام — سيولة ذكية، اختراقات، تشبع بيعي، وإفصاحات" : "Live Telegram Scanner Alerts — smart volume, breakouts, oversold bounce & disclosures", included: true },
    { icon: <MessageSquare className="w-4 h-4" />, text: isAr ? `${proLimits.chat_messages_per_month} رسالة شات بوت ذكي شهرياً` : `${proLimits.chat_messages_per_month} smart chatbot messages / month`, included: true },
    { icon: <Clock className="w-4 h-4 text-sky-500" />, text: isAr ? "أتمتة استشارات الذكاء الاصطناعي اليومية (حتى 5 استشارات مجدولة يومياً تُرسل لتليجرام في المواعيد التي تختارها)" : "Daily Scheduled AI Chat Automations (up to 5 scheduled consults/day sent to your Telegram at your preferred times)", included: true },
    { icon: <Sparkles className="w-4 h-4 text-amber-500" />, text: isAr ? "فتح كافة التوصيات المفتوحة وإشارات الدخول اللحظية وتفعيل وضع التوصيات الحرة في الشات" : "Full access to open recommendations, live entry signals & autonomous recs mode in chat", included: true },
    { icon: <Sparkles className="w-4 h-4 text-amber-500" />, text: isAr ? "رفع وتحليل لقطات شاشة المحفظة والشارت بالذكاء الاصطناعي (Vision AI) 📸" : "Upload & analyze portfolio and chart screenshots with Vision AI 📸", included: true },
    ...chartFeatures,
    { icon: <BarChart3 className="w-4 h-4" />, text: isAr ? `حتى ${proLimits.portfolio_stocks} أسهم نشطة في المحفظة` : `Up to ${proLimits.portfolio_stocks} active portfolio stocks`, included: true },
    { icon: <Activity className="w-4 h-4" />, text: isAr ? "النشاط غير الطبيعي — أسهم بحجم تداول غير طبيعي + تقييم AI" : "Unusual Activity — volume spikes + AI scoring", included: true },
  ];

  const lifetimeFeatures = [
    { icon: <Crown className="w-4 h-4 text-purple-600 dark:text-yellow-400" />, text: isAr ? "صلاحية كاملة مدى الحياة للأبد (36,500 يوم بدون أي تجديد أو اشتراك متكرر)" : "Permanent lifetime access (never expires, zero recurring renewals)", included: true },
    { icon: <ShieldCheck className="w-4 h-4 text-emerald-500" />, text: isAr ? "قناة تليجرام الفورية (تنبيهات فنية وخوارزمية فورية للأبد)" : "Instant Telegram Channel forever", included: true },
    { icon: <BellRing className="w-4 h-4 text-emerald-500 fill-emerald-500" />, text: isAr ? "رادار وتنبيهات الإسكانر الفورية على تليجرام بكافة مراحله للأبد" : "Live Telegram Scanner Alerts forever across all stages", included: true },
    { icon: <Zap className="w-4 h-4 text-emerald-500" />, text: isAr ? "الصفقات القصيرة ⚡ PRO ومتابعة الأرباح كاملة بدون تشفير" : "Short Swings ⚡ PRO momentum trades unmasked", included: true },
    { icon: <MessageSquare className="w-4 h-4 text-emerald-500" />, text: isAr ? `${proLimits.chat_messages_per_month} استشارة شات بوت شهرياً تتجدد تلقائياً للأبد` : `${proLimits.chat_messages_per_month} AI chat messages refreshed monthly for life`, included: true },
    { icon: <Clock className="w-4 h-4 text-emerald-500" />, text: isAr ? "أتمتة استشارات الذكاء الاصطناعي اليومية (حتى 5 استشارات مجدولة يومياً للأبد)" : "Daily Scheduled AI Chat Automations (up to 5 scheduled consults/day forever)", included: true },
    { icon: <Sparkles className="w-4 h-4 text-emerald-500" />, text: isAr ? "فتح كافة التوصيات المفتوحة وإشارات الدخول + تحليل صور المحفظة والشارت (Vision AI) 📸" : "Unrestricted open recommendations + Vision AI portfolio & chart analysis 📸", included: true },
    ...chartFeatures,
    { icon: <Activity className="w-4 h-4 text-emerald-500" />, text: isAr ? "النشاط غير الطبيعي للأسهم + المحفظة الموسعة (10 أسهم)" : "Unusual Activity + 10 portfolio stock slots", included: true },
    { icon: <Sparkles className="w-4 h-4 text-yellow-500" />, text: isAr ? "أولوية قصوى لكافة التحديثات والميزات المستقبلية" : "VIP priority for all future updates", included: true },
  ];

  // ── STEP 3: SUBMITTED / PAYMENT RESULT ─────────────────────────────────────
  if (step === "submitted") {
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
                  ? selectedPlanDetails?.id === "lifetime"
                    ? "bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300"
                    : "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                  : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
              }`}
            >
              {orderStatus === "failed"
                ? isAr ? "فشلت العملية" : "Payment Incomplete"
                : orderStatus === "approved"
                ? selectedPlanDetails?.id === "lifetime"
                  ? isAr ? "تم تفعيل باقة مدى الحياة (LIFETIME VIP) 👑" : "Lifetime VIP Activated 👑"
                  : isAr ? "تم التفعيل بنجاح" : "Pro Activated"
                : isAr ? "جاري التحقق من الدفع" : "Verifying Payment"}
            </span>
            <h1 className="text-2xl sm:text-3xl font-black text-zinc-950 dark:text-white">
              {orderStatus === "failed"
                ? isAr ? "لم تكتمل عملية الدفع" : "Payment was not completed"
                : orderStatus === "approved"
                ? selectedPlanDetails?.id === "lifetime"
                  ? isAr ? "أهلاً بك في نخبة EGX BOTS مدى الحياة! 👑🎉" : "Welcome to EGX BOTS Lifetime VIP! 👑🎉"
                  : isAr ? "أهلاً بك في EGX BOTS Pro! 🎉" : "Welcome to EGX BOTS Pro! 🎉"
                : isAr ? "في انتظار إشعار تأكيد الدفع ⏳" : "Awaiting payment confirmation ⏳"}
            </h1>
            <p className="text-sm font-semibold text-zinc-600 dark:text-zinc-300 leading-relaxed max-w-md mx-auto">
              {orderStatus === "failed"
                ? isAr
                  ? "لم نتلقَ تأكيد إتمام الدفع من EasyKash. يمكنك المحاولة مجددًا باختيار وسيلة أخرى أو التواصل معنا للمساعدة."
                  : "We didn't receive payment confirmation from EasyKash. You can try again or reach out to our team."
                : orderStatus === "approved"
                ? isAr
                  ? selectedPlanDetails?.id === "lifetime"
                    ? "تم تفعيل اشتراكك الدائم في باقة مدى الحياة (Lifetime VIP) بنجاح للأبد! حسابك نشط الآن بكامل الصلاحيات مدى الحياة وبدون أي تجديدات شهرية."
                    : `تم تأكيد اشتراكك في باقة Pro لمدة ${selectedPlanDetails?.days || 30} يوماً بنجاح. حسابك نشط الآن بكامل الصلاحيات!`
                  : selectedPlanDetails?.id === "lifetime"
                  ? "Your Lifetime VIP subscription is now active forever! Full access granted for life with zero recurring renewals."
                  : `Your Pro plan is now active for ${selectedPlanDetails?.days || 30} days with full benefits!`
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

          {/* Approved VIP Actions */}
          {orderStatus === "approved" && (
            <div className="space-y-4 pt-2">
              {subscriptionEnd && (
                <p className="text-xs font-black text-emerald-600 dark:text-emerald-400">
                  {selectedPlanDetails?.id === "lifetime"
                    ? isAr
                      ? "مدة الاشتراك: مدى الحياة للأبد (اشتراك دائم) 👑"
                      : "Subscription Duration: Lifetime Forever 👑"
                    : isAr
                    ? `تاريخ انتهاء الاشتراك: ${new Date(subscriptionEnd).toLocaleDateString("ar-EG")}`
                    : `Valid until: ${new Date(subscriptionEnd).toLocaleDateString()}`}
                </p>
              )}
              {telegramProUrl ? (
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
                onClick={() => router.push("/profile")}
                className="w-full border-2 border-black dark:border-white bg-white dark:bg-zinc-900 py-3 text-xs font-black hover:bg-zinc-100 transition-all"
              >
                {isAr ? "الانتقال إلى الملف الشخصي والكوتا ←" : "Go to Profile & Quota Dashboard →"}
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
                  {isAr
                    ? "إذا رفض البنك المعاملة أو تأخر كود التأكيد (OTP) أو لا تتوفر معك بطاقة فيزا، يمكنك أيضاً التحويل المباشر عبر أي محفظة إلكترونية أو إنستاباي والتفعيل الفوري لحسابك بدون أي انتظار."
                    : "If your bank declined the transaction or OTP was delayed, you can also pay directly via mobile wallet / InstaPay for instant activation."}
                </p>
                <div className="pt-2 flex flex-col sm:flex-row gap-2">
                  <a
                    href="https://wa.me/201024359100?text=%D9%85%D8%B1%D8%AD%D8%A8%D8%A7%D8%8C%20%D9%88%D8%A7%D8%AC%D9%87%D8%AA%20%D9%85%D8%B4%D9%83%D9%84%D8%A9%20%D9%81%D9%8A%20%D8%A7%D9%84%D8%AF%D9%81%D8%B9%20%D8%B9%D9%84%D9%89%20EGX%20BOTS%20%D9%88%D8%A3%D8%B1%D9%8A%D8%AF%20%D8%A7%D9%84%D9%85%D8%B3%D8%A7%D8%B9%D8%AF%D8%A9%20%D9%88%D8%A7%D9%84%D8%AF%D9%81%D8%B9%20%D8%A8%D8%A7%D9%84%D9%85%D8%AD%D9%81%D8%B8%D8%A9"
                    target="_blank"
                    rel="noreferrer"
                    className="flex-1 inline-flex items-center justify-center gap-1.5 border-2 border-emerald-600 bg-emerald-600 hover:bg-emerald-700 text-white font-black py-2.5 px-4 text-xs transition-colors"
                  >
                    <MessageSquare className="w-4 h-4" />
                    {isAr ? "تواصل معنا عبر واتساب للمساعدة الفورية" : "Chat on WhatsApp"}
                  </a>
                  <a
                    href="https://t.me/SharksZone_support_bot"
                    target="_blank"
                    rel="noreferrer"
                    className="flex-1 inline-flex items-center justify-center gap-1.5 border-2 border-black dark:border-white bg-zinc-900 hover:bg-zinc-800 text-white dark:bg-white dark:text-black dark:hover:bg-zinc-200 font-black py-2.5 px-4 text-xs transition-colors"
                  >
                    <ExternalLink className="w-4 h-4" />
                    {isAr ? "الدعم الفني على تليجرام" : "Telegram Support"}
                  </a>
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
                <Image src="/favicon_io/apple-touch-icon.png" alt="EGX Bots" width={36} height={36} className="h-8 w-8 object-contain" />
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
                      ? "رقم موبايل مصري لتلقي كود ورسالة التأكيد من بوابة الدفع."
                      : "Egyptian mobile number to receive confirmation code."}
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
                    {isAr ? "رقم الموبايل المصري (11 رقم)" : "Egyptian Mobile (11 digits)"}
                  </label>
                  <div className="flex items-center gap-3 border-3 border-black dark:border-white bg-white dark:bg-zinc-900 px-4 py-3 focus-within:ring-2 focus-within:ring-emerald-500">
                    <Smartphone className="w-5 h-5 text-emerald-600 shrink-0" />
                    <input
                      id="mobile-input"
                      type="tel"
                      value={customerMobile}
                      onChange={(e) => setCustomerMobile(e.target.value)}
                      placeholder="01012345678"
                      className="w-full bg-transparent font-mono text-base font-black outline-none placeholder:text-zinc-400 text-zinc-950 dark:text-white"
                      dir="ltr"
                    />
                  </div>
                  <div className="flex items-center justify-between text-xs font-bold pt-0.5">
                    <span className={isMobileValid ? "text-emerald-600 dark:text-emerald-400" : "text-zinc-500"}>
                      {isMobileValid
                        ? isAr ? "✓ رقم مصري صحيح" : "✓ Valid Egyptian number"
                        : isAr ? "مقبول: 010 أو 011 أو 012 أو 015" : "Accepted: 010, 011, 012 or 015"}
                    </span>
                    <span className="text-[10px] text-zinc-400 font-mono">
                      {customerMobile.length > 0 ? `${customerMobile.length} / 11` : ""}
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
                        : isAr ? `المتابعة للدفع الآمن (${proPrice.toLocaleString()} ج.م) 🔒` : `Proceed to Secure Checkout (${proPrice.toLocaleString()} EGP) 🔒`}
                    </>
                  )}
                </button>
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
              <div className="border-b border-zinc-800 pb-4">
                <span className="text-[10px] font-black uppercase tracking-widest text-emerald-400 block mb-1">
                  {isAr ? "فاتورة الاشتراك" : "ORDER INVOICE"}
                </span>
                <h3 className="text-2xl font-black flex items-center gap-2">
                  {selectedPlanDetails.isLifetime && <Crown className="w-6 h-6 text-yellow-400" />}
                  {selectedPlanDetails.isLifetime ? "EGX BOTS Lifetime VIP" : "EGX BOTS Pro"}
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
                    {selectedPlanDetails.isLifetime ? (isAr ? "مدى الحياة (Lifetime VIP)" : "Lifetime VIP") : "Pro VIP"}
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
                {promoDiscountAmount > 0 && appliedPromo && (
                  <div className="space-y-1 text-xs font-bold">
                    <div className="flex justify-between text-zinc-400">
                      <span>{isAr ? "السعر قبل كود الخصم:" : "Subtotal:"}</span>
                      <span className="line-through">{baseProPrice.toLocaleString()} ج.م</span>
                    </div>
                    <div className="flex justify-between text-amber-400 font-black">
                      <span>{isAr ? `خصم كود (${appliedPromo.code} - ${appliedPromo.discount_percent}%):` : `Promo (${appliedPromo.code}):`}</span>
                      <span>-{promoDiscountAmount.toLocaleString()} ج.م</span>
                    </div>
                  </div>
                )}
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-black">{isAr ? "المبلغ الإجمالي:" : "Total Amount:"}</span>
                  <div className="text-end">
                    <span className="text-3xl font-black text-emerald-400">{proPrice.toLocaleString()}</span>
                    <span className="text-xs font-bold text-zinc-400 ms-1">ج.م</span>
                  </div>
                </div>
              </div>

              {/* Included Benefits List */}
              <div className="space-y-2 text-xs font-bold">
                <span className="text-[10px] font-black uppercase text-zinc-400 tracking-wider block">
                  {selectedPlanDetails.isLifetime
                    ? (isAr ? "ميزات باقة مدى الحياة VIP:" : "INCLUDED WITH LIFETIME VIP:")
                    : (isAr ? "الميزات المشمولة فوراً:" : "INCLUDED WITH PRO:")}
                </span>
                {selectedPlanDetails.isLifetime ? (
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
                      <span>{isAr ? "الصفقات القصيرة ⚡ PRO ومتابعة الأرباح" : "Short Swings ⚡ PRO unmasked"}</span>
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
                ) : (
                  <>
                    <div className="flex items-center gap-2 text-zinc-300">
                      <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      <span>{isAr ? "قناة تليجرام الفورية (تنبيهات فنية وخوارزمية فورية بدون تأخير)" : "Instant Telegram Channel (daily signals without delay)"}</span>
                    </div>
                    <div className="flex items-center gap-2 text-zinc-300">
                      <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      <span>{isAr ? "رادار وتنبيهات الإسكانر الفورية على تليجرام (سيولة واختراقات وإفصاحات)" : "Live Telegram Scanner Alerts (volume, breakouts & filings)"}</span>
                    </div>
                    <div className="flex items-center gap-2 text-zinc-300">
                      <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      <span>{isAr ? "الصفقات القصيرة ⚡ PRO (إشارات الزخم السريعة والوقف المتحرك بدون تشفير)" : "Short Swings ⚡ PRO (instant momentum runners unmasked)"}</span>
                    </div>
                    <div className="flex items-center gap-2 text-zinc-300">
                      <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      <span>{isAr ? `${proLimits.chat_messages_per_month} رسالة ذكاء اصطناعي شهرياً` : `${proLimits.chat_messages_per_month} monthly AI chat messages`}</span>
                    </div>
                    <div className="flex items-center gap-2 text-zinc-300">
                      <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      <span>{isAr ? `محفظة تداول حتى ${proLimits.portfolio_stocks} أسهم` : `${proLimits.portfolio_stocks} active portfolio stock slots`}</span>
                    </div>
                  </>
                )}
              </div>

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
            EGX BOTS PRO · خطط واشتراكات
          </span>
          <h1 className="text-3xl sm:text-5xl font-black text-zinc-950 dark:text-white tracking-tight">
            {isAr ? "اختر باقة الاشتراك البرمجي" : "Choose Your Software Plan"}
          </h1>
          <p className="text-sm sm:text-base font-bold text-zinc-600 dark:text-zinc-300 max-w-2xl mx-auto leading-relaxed">
            {isAr
              ? "تحليلات كمية، ونماذج فنية مدعومة بالذكاء الاصطناعي، وقناة تنبيهات فورية لمتابعة البورصة المصرية."
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

        {/* ── PRICING CATEGORY SWITCHER: RETAIL VS B2B ── */}
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
        <div id="pricing-duration-navbar" className="sticky top-[var(--header-h,72px)] z-30 py-3 bg-white/90 dark:bg-zinc-950/90 backdrop-blur-md transition-all space-y-2 -mx-4 px-4 sm:-mx-6 sm:px-6 border-y border-zinc-200/80 dark:border-zinc-800/80">
          <div className="text-center">
            <span className="text-xs font-black uppercase tracking-wider text-zinc-500 dark:text-zinc-400 block mb-1">
              {isAr ? "اختر مدة اشتراك باقة EGX BOTS PRO:" : "SELECT PRO BILLING CYCLE:"}
            </span>
          </div>

          <div className="flex justify-center">
            <div className="inline-flex p-1.5 rounded-2xl bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-sm flex-wrap justify-center gap-1.5 sm:gap-2 max-w-full">
              {[
                {
                  id: "pro" as const,
                  name_ar: "شهر واحد",
                  name_en: "1 Month",
                  badge_ar: isGrandfathered
                    ? "50 ج.م (تجديد حصري مدى الحياة) ⚡"
                    : isGrandfathered100 && !foundersIsOpen
                    ? "100 ج.م (تجديد المؤسسين مدى الحياة) ⚡"
                    : foundersIsOpen
                    ? (foundersCountdown ? `100 ج.م ⏰ ${foundersCountdown} (تثبيت مدى الحياة)` : "100 ج.م مدى الحياة 🔥")
                    : `${monthlyPrice || 200} ج.م / شهر`,
                  badge_en: isGrandfathered
                    ? "50 EGP (Renewal for life) ⚡"
                    : isGrandfathered100 && !foundersIsOpen
                    ? "100 EGP (Renewal for life) ⚡"
                    : foundersIsOpen
                    ? "100 EGP (Locked for life) 🔥"
                    : `${monthlyPrice || 200} EGP / mo`,
                  badgeBg: "bg-amber-400 text-black",
                },
                {
                  id: "pro_6m" as const,
                  name_ar: "6 شهور",
                  name_en: "6 Months",
                  badge_ar: (foundersIsOpen || isGrandfathered || isGrandfathered100) ? "500 بدل 1,000 ج.م ⭐ (تثبيت مدى الحياة)" : "الأكثر طلباً ⭐",
                  badge_en: (foundersIsOpen || isGrandfathered || isGrandfathered100) ? "500 EGP (Locked for life) ⭐" : "Most Popular ⭐",
                  badgeBg: "bg-emerald-400 text-black",
                },
                {
                  id: "pro_1y" as const,
                  name_ar: "سنة كاملة",
                  name_en: "1 Year",
                  badge_ar: (foundersIsOpen || isGrandfathered || isGrandfathered100) ? "1,000 بدل 1,850 ج.م 💎 (تثبيت مدى الحياة)" : "أكبر توفير 💎",
                  badge_en: (foundersIsOpen || isGrandfathered || isGrandfathered100) ? "1,000 EGP (Locked for life) 💎" : "Save 46% 💎",
                  badgeBg: "bg-sky-400 text-black",
                },
              ].map((tab) => {
                const isSelected = activeProDuration === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => handleDurationSelect(tab.id, true)}
                    className={`flex items-center gap-2 px-4 sm:px-6 py-2.5 sm:py-3 rounded-xl transition-all text-xs sm:text-sm font-black cursor-pointer ${
                      isSelected
                        ? "bg-emerald-500 text-black shadow-md shadow-emerald-500/20 font-black"
                        : "bg-transparent hover:bg-zinc-200/60 dark:hover:bg-zinc-800/60 text-zinc-600 dark:text-zinc-400"
                    }`}
                  >
                    <span>{isAr ? tab.name_ar : tab.name_en}</span>
                    <span
                      className={`text-[10px] font-black uppercase px-2 py-0.5 rounded-full whitespace-nowrap ${tab.badgeBg}`}
                    >
                      {isAr ? tab.badge_ar : tab.badge_en}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* ── 3 DISTINCT CARDS: FREE | PRO (WITH SWITCHER) | LIFETIME VIP ── */}
        <div className="grid lg:grid-cols-3 gap-6 items-stretch">
          {/* ── 01. Free Plan Card ── */}
          <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800/80 bg-white dark:bg-zinc-900/60 p-6 sm:p-7 space-y-6 flex flex-col justify-between shadow-sm hover:border-zinc-300 dark:hover:border-zinc-700 transition-all">
            <div className="space-y-5">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-2xl font-black text-zinc-950 dark:text-white">
                    {isAr ? "الخطة المجانية" : "Free Plan"}
                  </h3>
                  <span className="text-xs font-bold text-zinc-500 block mt-0.5">
                    {isAr ? "استكشاف المنصة وتجربة التحليلات" : "Explore platform basics"}
                  </span>
                </div>
                <span className="text-[10px] font-bold uppercase px-2.5 py-1 rounded-full border border-zinc-200 dark:border-zinc-800 bg-zinc-100 dark:bg-zinc-800/70 text-zinc-600 dark:text-zinc-400">
                  {isPro ? (isAr ? "متاحة" : "Available") : isAr ? "الخطة الحالية" : "Current"}
                </span>
              </div>

              <div className="border-b border-zinc-200 dark:border-zinc-800/80 pb-5">
                <div className="flex items-baseline gap-1">
                  <span className="text-5xl font-black text-zinc-950 dark:text-white">0</span>
                  <span className="text-sm font-bold text-zinc-500">ج.م / للأبد</span>
                </div>
                <p className="text-xs font-medium text-zinc-500 mt-1">
                  {isAr ? "بدون أي بطاقة بنكية أو رسوم خفية" : "No credit card required"}
                </p>
              </div>

              <div className="space-y-3">
                <span className="text-[11px] font-black uppercase tracking-wider text-zinc-400 block">
                  {isAr ? "الميزات المشمولة في المجاني:" : "INCLUDED IN FREE:"}
                </span>
                <ul className="space-y-3.5">
                  {freeFeatures.map((f, i) => (
                    <li
                      key={i}
                      className={`flex items-start gap-2.5 text-xs sm:text-[13px] font-medium leading-snug ${
                        f.included
                          ? "text-zinc-800 dark:text-zinc-200"
                          : "text-zinc-400 dark:text-zinc-400/80 line-through decoration-zinc-400 dark:decoration-zinc-500"
                      }`}
                    >
                      <span className="shrink-0 mt-0.5">
                        {f.included ? (
                          <Check className="w-4 h-4 text-emerald-500" />
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

            {trialEligible && !isPro ? (
              <div className="space-y-2 mt-4">
                <button
                  type="button"
                  onClick={handleStartTrial}
                  disabled={trialLoading}
                  className="w-full rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-white py-3.5 px-4 text-xs font-black uppercase tracking-wider shadow-md shadow-emerald-500/20 hover:shadow-emerald-500/30 hover:-translate-y-0.5 active:translate-y-0 transition-all cursor-pointer flex items-center justify-center gap-2"
                >
                  {trialLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4 text-yellow-300" />
                      <span>{isAr ? "جرّب Pro مجاناً لمدة 3 أيام ⚡" : "Try Pro Free for 3 Days ⚡"}</span>
                    </>
                  )}
                </button>
                <p className="text-[10px] text-center font-bold text-emerald-600 dark:text-emerald-400">
                  {isAr ? "✨ تجربة كاملة وفورية بدون أي دفع أو بطاقة بنكية" : "Instant full access, no card required"}
                </p>
              </div>
            ) : (
              <button
                type="button"
                disabled
                className="w-full rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-100 dark:bg-zinc-800/50 text-zinc-400 dark:text-zinc-500 py-3.5 text-xs font-bold uppercase tracking-wider cursor-not-allowed mt-4"
              >
                {isPro ? (isAr ? "الخطة المجانية متاحة" : "Free plan available") : (isAr ? "خطتك الحالية" : "Current Plan")}
              </button>
            )}
          </div>

          {/* ── 02. Pro Plan Card (The Hero Tier) ── */}
          {(() => {
            const isFeatured = activeProDuration === "pro_6m";
            const isAnnual = activeProDuration === "pro_1y";
            const isMonthly = activeProDuration === "pro";
            const planDiscount =
              isMonthly && monthlyDiscount?.active && (foundersIsOpen || isGrandfathered || isGrandfathered100)
                ? monthlyDiscount
                : (!isMonthly && foundersIsOpen && activeProDetails.original_amount_egp)
                ? {
                    active: true,
                    original_amount_egp: activeProDetails.original_amount_egp,
                    label_ar: isFeatured
                      ? "عرض المؤسسين خصم 50% (500 بدل 1,000 ج.م) ⭐"
                      : "عرض المؤسسين (1,000 بدل 1,850 ج.م) 💎",
                  }
                : null;

            return (
              <div
                id="pro-plan-card"
                ref={proCardRef}
                className="scroll-mt-48 rounded-2xl border-2 border-emerald-500 bg-white dark:bg-zinc-900/95 p-6 sm:p-7 space-y-6 flex flex-col justify-between relative shadow-2xl shadow-emerald-500/10 ring-1 ring-emerald-500/30 transition-all duration-300"
              >
                {/* Floating Top Badge */}
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                  <span className="rounded-full bg-emerald-500 text-black text-xs font-black uppercase px-4 py-1 tracking-wider shadow-md shadow-emerald-500/30 whitespace-nowrap flex items-center gap-1.5">
                    {isMonthly && planDiscount ? (
                      foundersCountdown
                        ? `عرض المؤسسين 100 ج.م شهرياً (ينتهي خلال ⏰ ${foundersCountdown})`
                        : (planDiscount.label_ar || "عرض المؤسسين (100 ج.م شهرياً مدى الحياة) 🔥")
                    ) : isMonthly ? (
                      isAr ? "⚡ باقة التداول الاحترافي" : "⚡ Monthly Pro Plan"
                    ) : isFeatured ? (
                      foundersIsOpen
                        ? (isAr ? "⭐ الأكثر طلباً · خصم المؤسسين 50%" : "⭐ Most Popular · 50% OFF")
                        : (isAr ? "⭐ الخطة الأكثر طلباً" : "⭐ Most Popular")
                    ) : (
                      foundersIsOpen
                        ? (isAr ? "💎 أكبر توفير · عرض المؤسسين (1,000 بدل 1,850 ج.م)" : "💎 Max Value · Founders Offer")
                        : (isAr ? "💎 أكبر توفير وقيمة سنوية" : "💎 Max Value")
                    )}
                  </span>
                </div>

                <div className="space-y-5 pt-1">
                  {/* Header & Tag */}
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-2xl font-black text-zinc-950 dark:text-white flex items-center gap-2">
                        EGX BOTS Pro
                      </h3>
                      <span className="text-xs font-bold text-zinc-500 block mt-0.5">
                        {isAr ? activeProDetails.name_ar : activeProDetails.name_en} · {activeProDetails.days} {isAr ? "يوماً" : "days"}
                      </span>
                    </div>
                    <span className="text-xs font-black rounded-lg border border-emerald-500/30 px-2.5 py-1 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                      PRO
                    </span>
                  </div>

                  {/* Price Section */}
                  <div className="border-b border-zinc-200 dark:border-zinc-800/80 pb-5">
                    <div className="flex items-baseline gap-2">
                      <span className="text-4xl sm:text-5xl font-black text-zinc-950 dark:text-white">
                        {activeProDetails.amount_egp.toLocaleString()}
                      </span>
                      <span className="text-sm font-bold text-zinc-500">ج.م</span>
                      {planDiscount && (
                        <span className="ms-2 text-lg sm:text-xl font-black text-zinc-400 dark:text-zinc-500 line-through decoration-red-500/80 decoration-2">
                          {isAr ? "بدل " : "was "}
                          {Number(planDiscount.original_amount_egp).toLocaleString()} {isAr ? "ج.م" : "EGP"}
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-2 mt-2">
                      <span className="text-xs font-bold text-zinc-600 dark:text-zinc-400">
                        {isAr ? `ما يعادل ${activeProDetails.monthlyEquivalent} ج.م / شهر` : `EGP ${activeProDetails.monthlyEquivalent}/mo`}
                      </span>
                      {activeProDetails.savingsPct > 0 && (
                        <span className="rounded-md border border-emerald-500/30 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 px-2 py-0.5 text-xs font-black">
                          {isAr ? `توفير ${activeProDetails.savingsPct}%` : `${activeProDetails.savingsPct}% OFF`}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Founding perk callout across all Pro durations */}
                  {(foundersIsOpen || isGrandfathered || isGrandfathered100) && (
                    <div className="rounded-xl bg-amber-50 dark:bg-amber-950/20 border border-amber-500/30 p-3.5 space-y-1 text-black dark:text-amber-200">
                      <div className="flex items-center gap-1.5 text-xs font-black text-amber-900 dark:text-amber-300">
                        <Clock className="w-3.5 h-3.5" />
                        <span>{isAr ? "🔒 ميزة المؤسسين الأوائل (تثبيت السعر مدى الحياة):" : "🔒 Founding Member Lifetime Price Lock:"}</span>
                      </div>
                      <p className="text-[11px] font-semibold leading-relaxed text-zinc-800 dark:text-zinc-300">
                        {isFeatured
                          ? (isAr
                            ? "باشتراكك في باقة الـ 6 شهور (500 ج.م بدلاً من 1,000 ج.م — أي 83 ج.م/شهر) يتثبّت حسابك كمؤسس مدى الحياة! عند التجديد مستقبلاً يظل سعر الشهر 100 ج.م (أو 500 ج.م للـ 6 شهور) للأبد حتى بعد عودة السعر الأساسي إلى 200 ج.م."
                            : "Subscribing to the 6-Month plan (500 EGP instead of 1,000 EGP — 83 EGP/mo) locks your Founding Member status for life at the 100 EGP/mo (or 500 EGP/6m) rate upon renewal!")
                          : isAnnual
                          ? (isAr
                            ? "باشتراكك في باقة السنة الكاملة (1,000 ج.م بدلاً من 1,850 ج.م — أي 83 ج.م/شهر) يتثبّت حسابك كمؤسس مدى الحياة! عند التجديد مستقبلاً يظل سعر الشهر 100 ج.م (أو 1,000 ج.م للسنة) للأبد حتى بعد عودة السعر الأساسي إلى 200 ج.م."
                            : "Subscribing to the 1-Year plan (1,000 EGP instead of 1,850 EGP — 83 EGP/mo) locks your Founding Member status for life at the 100 EGP/mo (or 1,000 EGP/yr) rate upon renewal!")
                          : isGrandfathered
                          ? (isAr
                            ? "50 ج.م شهرياً (سعر المؤسسين المستمر لحسابك مدى الحياة ما دمت مجدداً لاشتراكك أو خلال مهلة الـ 72 ساعة)."
                            : "50 EGP/mo grandfathered founders rate active for your account as long as renewed.")
                          : isGrandfathered100 && !foundersIsOpen
                          ? (isAr
                            ? "100 ج.م شهرياً (سعر المؤسسين المثبت لحسابك مدى الحياة ما دمت مجدداً لاشتراكك أو خلال مهلة الـ 72 ساعة)."
                            : "100 EGP/mo grandfathered founders rate active for your account as long as renewed.")
                          : (isAr
                            ? "100 ج.م شهرياً عرض باقة المؤسسين (بدلاً من 200 ج.م) — يثبّت سعرك بـ 100 ج.م مدى الحياة طول ما بتجدد (أو 500 ج.م للـ 6 شهور / 1,000 ج.م للسنة)، مع مهلة سماح 72 ساعة عند كل تجديد."
                            : "100 EGP/mo limited founders offer (instead of 200 EGP) — locks your 100 EGP/mo rate for life as long as renewed, with 72h renewal grace period.")}
                      </p>
                    </div>
                  )}

                  {/* Features List */}
                  <div className="space-y-3">
                    <span className="text-[11px] font-black uppercase tracking-wider text-zinc-500 dark:text-zinc-400 block">
                      {isAr ? "الميزات المشمولة في باقة Pro:" : "INCLUDED IN PRO:"}
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
                    onClick={() => openPaymentStep(activeProDetails.id)}
                    className="w-full flex items-center justify-center gap-2 rounded-xl py-4 px-4 text-xs sm:text-sm font-black uppercase tracking-wider shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30 hover:-translate-y-0.5 active:translate-y-0 transition-all cursor-pointer bg-emerald-500 hover:bg-emerald-400 text-black"
                  >
                    <LockKeyhole className="w-3.5 h-3.5" />
                    {isPro
                      ? (isAr ? `تجديد باقة Pro (${activeProDetails.amount_egp.toLocaleString()} ج.م)` : `Renew Pro (${activeProDetails.amount_egp} EGP)`)
                      : (isAr ? `اشترك في Pro (${activeProDetails.amount_egp.toLocaleString()} ج.م)` : `Subscribe to Pro (${activeProDetails.amount_egp} EGP)`)}
                  </button>
                  <div className="flex items-center justify-center gap-2 text-[10px] font-bold text-zinc-500">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                    <span>{isAr ? "دفع رسمي مشفر · تفعيل تلقائي" : "Encrypted checkout · Instant unlock"}</span>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* ── 03. Lifetime VIP Card ── */}
          <div className="relative rounded-2xl border-2 border-amber-400/80 dark:border-amber-500/40 bg-gradient-to-b from-amber-50/90 via-white to-amber-50/40 dark:from-amber-950/30 dark:via-zinc-900/95 dark:to-zinc-900/95 p-6 sm:p-7 space-y-6 flex flex-col justify-between shadow-xl shadow-amber-500/10 dark:shadow-amber-500/5 transition-all">
            {/* Floating Top Badge */}
            <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
              <span className="rounded-full bg-gradient-to-r from-amber-400 to-yellow-400 text-black text-xs font-black uppercase px-4 py-1 tracking-wider shadow-md shadow-amber-500/20 whitespace-nowrap flex items-center gap-1.5">
                <Crown className="w-3.5 h-3.5 fill-black" />
                {lifetimeIsOpen
                  ? (isAr ? `حصري · متبقي ${lifetimeRemaining} مقعداً فقط` : `${lifetimeRemaining} Spots Left`)
                  : (isAr ? "اكتملت المقاعد (Sold Out)" : "Sold Out (20/20)")}
              </span>
            </div>

            <div className="space-y-5 pt-1">
              {/* Header & Tag */}
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-2xl font-black text-zinc-950 dark:text-white flex items-center gap-2">
                    <Crown className="w-6 h-6 text-amber-500 dark:text-amber-400 shrink-0" />
                    <span>{isAr ? "مدى الحياة VIP" : "Lifetime VIP"}</span>
                  </h3>
                  <span className="text-xs font-bold text-zinc-600 dark:text-zinc-400 block mt-0.5">
                    {isAr ? "صلاحية دائمة للأبد (36,500 يوم)" : "Permanent access for life"}
                  </span>
                </div>
                <span className="text-xs font-black rounded-lg border border-amber-300 dark:border-amber-500/30 px-2.5 py-1 bg-amber-100 dark:bg-amber-500/15 text-amber-800 dark:text-amber-400">
                  VIP 20
                </span>
              </div>

              {/* Price Section */}
              <div className="border-b border-zinc-200 dark:border-zinc-800/80 pb-5">
                <div className="flex items-baseline gap-2">
                  <span className="text-4xl sm:text-5xl font-black text-zinc-950 dark:text-white">2,250</span>
                  <span className="text-sm font-bold text-zinc-600 dark:text-zinc-400">ج.م</span>
                </div>
                <div className="flex flex-wrap items-center gap-2 mt-2">
                  <span className="text-xs font-bold text-amber-800 dark:text-amber-300 flex items-center gap-1 bg-amber-100/90 dark:bg-amber-500/10 border border-amber-300/80 dark:border-amber-500/20 rounded-md px-2 py-0.5">
                    <Sparkles className="w-3 h-3 text-amber-600 dark:text-amber-400" />
                    {isAr ? "دفعة واحدة للأبد · بدون أي تجديد" : "One-time payment · Zero renewals"}
                  </span>
                  <span className="rounded-md border border-amber-300 dark:border-amber-500/30 bg-amber-200/60 dark:bg-amber-500/15 text-amber-900 dark:text-amber-300 px-2 py-0.5 text-xs font-black">
                    {isAr ? "وفر للأبد 👑" : "Save Forever 👑"}
                  </span>
                </div>
              </div>

              {/* Breakeven Value Analysis Box */}
              <div className="rounded-xl bg-amber-50/90 dark:bg-amber-950/30 border border-amber-300/80 dark:border-amber-500/25 p-3.5 space-y-1">
                <div className="flex items-center gap-1.5 text-xs font-black text-amber-900 dark:text-amber-400">
                  <Sparkles className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
                  <span>{isAr ? "💡 حساب نقطة التعادل والقيمة:" : "💡 Breakeven Value Analysis:"}</span>
                </div>
                <p className="text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 leading-relaxed">
                  {isAr
                    ? "سعر الباقة (2,250 ج.م) يعادل اشتراك 22.5 شهر فقط في باقة Pro — أي بعد أقل من عامين تصبح كافة تحليلات وتنبيهات المنصة مجانية بالكامل لحسابك مدى الحياة للأبد!"
                    : "At 2,250 EGP, this equals just ~22 months of Pro. After less than 2 years, all platform AI models, alerts, and updates are 100% free forever!"}
                </p>
              </div>

              {/* Spots Tracker Box */}
              <div className="rounded-xl bg-amber-50/60 dark:bg-zinc-950/80 border border-amber-200/90 dark:border-zinc-800 p-3.5 space-y-2">
                <div className="flex items-center justify-between text-xs font-bold">
                  <span className="text-amber-800 dark:text-amber-400 flex items-center gap-1">
                    <Award className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                    {isAr ? "المقاعد المتبقية:" : "Remaining Spots:"}
                  </span>
                  <span className="font-mono text-zinc-800 dark:text-zinc-300 text-[11px] font-bold">
                    {lifetimeIsOpen
                      ? (isAr ? `${lifetimeRemaining} من ${lifetimeLimit} مقعداً` : `${lifetimeRemaining}/${lifetimeLimit}`)
                      : (isAr ? "اكتملت (20/20) ❌" : "Sold Out ❌")}
                  </span>
                </div>
                <div className="w-full rounded-full bg-zinc-200 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 h-2 overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-amber-400 to-yellow-400 transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(5, (lifetimeCount / lifetimeLimit) * 100))}%` }}
                  />
                </div>
              </div>

              {/* Features List */}
              <div className="space-y-3">
                <span className="text-[11px] font-black uppercase tracking-wider text-zinc-500 dark:text-zinc-400 block">
                  {isAr ? "الميزات المشمولة مدى الحياة:" : "INCLUDED FOR LIFE:"}
                </span>
                <ul className="space-y-3.5">
                  {lifetimeFeatures.map((f, i) => (
                    <li key={i} className="flex items-start gap-2.5 text-xs sm:text-[13px] font-medium leading-snug text-zinc-800 dark:text-zinc-200">
                      <span className="shrink-0 mt-0.5 text-amber-500 dark:text-amber-400">{f.icon || <Check className="w-3.5 h-3.5" />}</span>
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
                disabled={!lifetimeIsOpen}
                onClick={() => {
                  setSelectedPlan("lifetime");
                  setStep("payment");
                }}
                className={`w-full flex items-center justify-center gap-2 rounded-xl py-4 px-4 text-xs sm:text-sm font-black uppercase tracking-wider shadow-lg transition-all ${
                  lifetimeIsOpen
                    ? "bg-gradient-to-r from-amber-400 to-yellow-400 hover:from-amber-300 hover:to-yellow-300 text-black shadow-amber-500/20 hover:shadow-amber-500/30 hover:-translate-y-0.5 active:translate-y-0 cursor-pointer"
                    : "bg-zinc-200 dark:bg-zinc-800 text-zinc-400 dark:text-zinc-500 cursor-not-allowed"
                }`}
              >
                <Crown className="w-4 h-4 fill-current" />
                {lifetimeIsOpen
                  ? isPro
                    ? (isAr ? "ترقية لحساب مدى الحياة (2,250 ج.م)" : "Upgrade to Lifetime")
                    : (isAr ? "احجز مقعدك مدى الحياة الآن (2,250 ج.م) 👑" : "Get Lifetime Deal 👑")
                  : (isAr ? "اكتملت المقاعد (Sold Out)" : "Sold Out (20/20)")}
              </button>
              <div className="flex items-center justify-center gap-2 text-[10px] font-bold text-zinc-500 dark:text-zinc-400">
                <Sparkles className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400" />
                <span>{isAr ? "صلاحية 36,500 يوم · بدون أي تجديد" : "36,500 days · Zero renewals"}</span>
              </div>
            </div>
          </div>
        </div>

          </>
        ) : (
          /* ── B2B CHANNELS & COMMUNITIES SECTION ── */
          <div className="space-y-8">
            {/* B2B Header Pitch Banner */}
            <div className="border-4 border-purple-600 dark:border-purple-400 bg-gradient-to-r from-purple-900 via-indigo-950 to-zinc-950 p-6 sm:p-8 text-white shadow-[8px_8px_0px_#a855f7] space-y-3">
              <div className="inline-flex items-center gap-2 px-3 py-1 border-2 border-yellow-400 bg-purple-900/80 text-yellow-300 text-xs font-black uppercase">
                <Crown className="w-4 h-4 text-yellow-300" />
                <span>{isAr ? "حلول الذكاء الاصطناعي للمجتمعات وقنوات التوصيات (B2B)" : "Enterprise AI for Trading Channels & Communities"}</span>
              </div>
              <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-white">
                {isAr ? "🤖 إيجار بوت التليجرام الذكي لقناتك أو مجموعتك المدفوعة" : "License EGX BOTS Inside Your Telegram Group"}
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
                  {isAr ? "🎁 جرّب بوت EGX BOTS في قناتك أو مجموعتك مجاناً لمدة 3 أيام" : "🎁 Try the Bot in Your Channel or Group Free for 3 Days"}
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
                        <div className="flex items-baseline gap-2">
                          <span className="text-4xl sm:text-5xl font-black text-zinc-950 dark:text-white">
                            {plan.amount_egp.toLocaleString()}
                          </span>
                          <span className="text-sm font-bold text-zinc-500">{isAr ? "ج.م / شهرياً" : "EGP / mo"}</span>
                        </div>
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
                        <span>{isAr ? `اشترك في ${plan.name_ar} (${plan.amount_egp.toLocaleString()} ج.م)` : `Subscribe to ${plan.name_en}`}</span>
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
                    {isAr ? "اختر باقة تناسب حجم قناتك ومعدل الاستفسارات اليومي، وادفع بسهولة عبر EasyKash (فودافون كاش أو بطاقة بنكية)." : "Choose Starter, Pro VIP, or Enterprise based on your community size."}
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
                    {isAr ? "اكتب من لوحة تحكمك سطر التوقيع الذي تريده أسفل كل رد (مثلاً: «تحليلات قناة الأستاذ فلان بالتعاون مع EGX Bots»)." : "Set your custom branding footer that appears below every analysis in your group."}
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
                  ? "منصة EGX BOTS هي شركة وأداة برمجيات مالية (FinTech SaaS) وليست وسيط تداول أو مستشاراً مالياً معتمداً من الهيئة العامة للرقابة المالية (FRA). المنصة لا تدير أموالاً ولا تتلقى ودائع ولا تضمن أي أرباح. مخرجات الذكاء الاصطناعي والإشارات الفنية هي مؤشرات إحصائية مؤتمتة لأغراض البحث والدراسة الذاتية، وقرار التداول يقع على عاتق المستثمر وحده عبر وسيطه المرخص."
                  : "EGX BOTS is a FinTech Software-as-a-Service (SaaS) provider and not a broker or financial advisor certified by the FRA. The platform does not manage funds, receive deposits, or guarantee returns. All algorithmic signals and technical indicators are statistical tools for educational and personal research purposes only."}
              </p>
              <div className="pt-1">
                <Link
                  href="/legal-status"
                  className="inline-flex items-center gap-1.5 text-xs font-black text-amber-800 dark:text-amber-400 hover:text-amber-950 dark:hover:text-amber-300 transition-colors"
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
                {isAr ? "عبر بوابة EasyKash المشفرة برخصة البنك المركزي المصري" : "Licensed 256-bit encrypted checkout via Central Bank of Egypt"}
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
                {isAr ? "يتم فتح الصلاحيات وتوليد رابط VIP فور اكتمال الدفع آلياً" : "Pro perks unlock instantly upon automated payment"}
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
                {isAr ? "اربح 25% كاش شهرياً أو أعلن أمام آلاف المتداولين في البورصة المصرية" : "Earn 25% Recurring Cash or Advertise to Thousands of Active EGX Traders"}
              </h3>
              <p className="text-xs sm:text-sm font-medium text-zinc-700 dark:text-zinc-300 leading-relaxed">
                {isAr
                  ? "هل تدير قناة تليجرام، صفحة فيسبوك، أو منصة استثمارية؟ انضم لبرنامج التسويق بالعمولة واربح 25% كاش شهرياً عن كل مشترك مستمر، أو احجز مساحات رعاية إعلانية ذكية في تقاريرنا اليومية ورادار الأسهم."
                  : "Manage a trading group, media channel, or financial community? Join our 25% recurring affiliate program or sponsor our daily market outlook reports reaching active Egyptian market investors."}
              </p>
            </div>
            <div className="flex flex-col sm:flex-row md:flex-col gap-3 w-full md:w-auto shrink-0">
              <a
                href="https://wa.me/201024359109?text=مرحباً، أود الاستفسار عن الشراكة الإعلانية وبرنامج الأفلييت مع EGX BOTS"
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

