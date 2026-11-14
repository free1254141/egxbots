"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Sparkles,
  X,
  BellRing,
  HelpCircle,
  Loader2,
  CheckCircle2,
  ExternalLink,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { toast } from "sonner";
import QuickProfitGuideModal from "@/components/QuickProfitGuideModal";
import { prepareTrialAutostart, clearTrialAutostart, TRIAL_AUTOSTART_EVENT } from "@/lib/trial-onboarding";
import { fetchUserQuotaCached, invalidateUserQuotaCache } from "@/lib/user-quota-client";
import { broadcastEntitlements } from "@/lib/entitlements";

export default function TrialWelcomePrompt() {
  const { user } = useAuth();
  const { language } = useLanguage();
  const router = useRouter();
  const isAr = language === "ar";

  const [eligible, setEligible] = useState<boolean>(false);
  const [loadingTrial, setLoadingTrial] = useState<boolean>(false);
  const [dismissed, setDismissed] = useState<boolean>(true);
  const [guideOpen, setGuideOpen] = useState<boolean>(false);
  const [telegramUnlinked, setTelegramUnlinked] = useState<boolean>(false);

  useEffect(() => {
    if (!user) {
      setDismissed(true);
      return;
    }

    // Check if dismissed recently (within 24 hours)
    const dismissedUntil = localStorage.getItem("egxbots_trial_prompt_dismissed_v1");
    if (dismissedUntil && Number(dismissedUntil) > Date.now()) {
      setDismissed(true);
      return;
    }

    // ── SESSION CACHE ──────────────────────────────────────────────────────────
    // Cache trial+quota check in sessionStorage for the full browser session.
    // This cuts /api/subscription/trial & /api/user/quota calls from N (one per
    // page navigation) down to 1 (once per tab open), saving ~95% of invocations
    // and dramatically reducing Supabase Egress bandwidth.
    const SESSION_KEY = "egxbots_trial_status_v2";
    try {
      const cached = sessionStorage.getItem(SESSION_KEY);
      if (cached) {
        const parsed = JSON.parse(cached) as { eligible: boolean; telegramUnlinked: boolean; ts: number };
        // Honour cache for up to 5 minutes (matches server-side Cache-Control max-age)
        if (parsed.ts && Date.now() - parsed.ts < 5 * 60 * 1000) {
          if (parsed.eligible) {
            setEligible(true);
            setDismissed(false);
          } else if (parsed.telegramUnlinked) {
            const tgDismissed = localStorage.getItem("egxbots_tg_prompt_dismissed_v1");
            if (!tgDismissed || Number(tgDismissed) < Date.now()) {
              setTelegramUnlinked(true);
              setDismissed(false);
            }
          }
          return;
        }
      }
    } catch {
      // sessionStorage blocked (e.g. private browsing) – fall through to fetch
    }
    // ── END SESSION CACHE ──────────────────────────────────────────────────────

    let active = true;
    // Unified session-cached quota+trial check (eliminates duplicate /api/subscription/trial GET calls).
    void fetchUserQuotaCached(user.id)
      .then((quota) => {
        if (!active || !quota?.ok) return;
        const isEligible = Boolean(quota?.plan?.trial_eligible);
        if (isEligible) {
          setEligible(true);
          setDismissed(false);
          try {
            sessionStorage.setItem(SESSION_KEY, JSON.stringify({ eligible: true, telegramUnlinked: false, ts: Date.now() }));
          } catch { /* ignore */ }
        } else {
          setEligible(false);
          const isProOrTrial = Boolean(quota?.plan?.is_pro || quota?.plan?.is_trial);
          const tgLinked = Boolean(quota?.plan?.telegram_linked);
          const tgUnlinked = isProOrTrial && !tgLinked;
          try {
            sessionStorage.setItem(SESSION_KEY, JSON.stringify({ eligible: false, telegramUnlinked: tgUnlinked, ts: Date.now() }));
          } catch { /* ignore */ }
          if (tgUnlinked) {
            const tgDismissed = localStorage.getItem("egxbots_tg_prompt_dismissed_v1");
            if (!tgDismissed || Number(tgDismissed) < Date.now()) {
              setTelegramUnlinked(true);
              setDismissed(false);
            }
          }
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
    setLoadingTrial(true);
    try {
      const variant = prepareTrialAutostart();
      const res = await fetch("/api/subscription/trial", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ variant }),
      });
      const data = await res.json();
      if (res.ok && data?.success) {
        invalidateUserQuotaCache(user.id);
        broadcastEntitlements(true);
        toast.success(isAr ? "🎉 مبروك! تم تفعيل تجربة Pro المجانية لمدة 3 أيام بنجاح!" : "🎉 Congrats! 3-day Pro trial activated!");
        setEligible(false);
        setDismissed(true);
        window.dispatchEvent(new CustomEvent(TRIAL_AUTOSTART_EVENT));
      } else {
        clearTrialAutostart();
        toast.error(data?.message || (isAr ? "تعذر تفعيل التجربة" : "Could not activate trial"));
      }
    } catch {
      clearTrialAutostart();
      toast.error(isAr ? "حدث خطأ في الاتصال" : "Network error");
    } finally {
      setLoadingTrial(false);
    }
  };

  const handleDismiss = () => {
    setDismissed(true);
    if (telegramUnlinked) {
      localStorage.setItem("egxbots_tg_prompt_dismissed_v1", (Date.now() + 24 * 3600 * 1000).toString());
    } else {
      localStorage.setItem("egxbots_trial_prompt_dismissed_v1", (Date.now() + 24 * 3600 * 1000).toString());
    }
  };

  if (dismissed || !user) return null;

  return (
    <>
      <div
        className="fixed bottom-4 ltr:right-4 rtl:left-4 z-[999] max-w-sm sm:max-w-md w-[calc(100vw-2rem)] animate-in fade-in slide-in-from-bottom-5 duration-300"
        dir={isAr ? "rtl" : "ltr"}
      >
        <div className="relative p-4 sm:p-5 rounded-2xl bg-zinc-950/95 text-white border-2 border-emerald-500 shadow-2xl shadow-emerald-500/20 backdrop-blur-md">
          {/* Close button */}
          <button
            type="button"
            onClick={handleDismiss}
            className="absolute top-3 ltr:right-3 rtl:left-3 p-1 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
            aria-label={isAr ? "إغلاق" : "Close"}
          >
            <X className="w-4 h-4" />
          </button>

          {eligible ? (
            /* Trial Activation Mode */
            <div className="space-y-3 pe-6">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-full bg-emerald-500 text-black text-[10px] font-black uppercase tracking-wider flex items-center gap-1">
                  <Sparkles className="w-3 h-3 text-black fill-black" />
                  <span>{isAr ? "هدية ترحيبية 🎁" : "WELCOME GIFT 🎁"}</span>
                </span>
                <span className="text-[11px] font-bold text-amber-400">
                  {isAr ? "بدون أي بطاقة بنكية" : "No credit card"}
                </span>
              </div>

              <div>
                <h4 className="text-sm sm:text-base font-black text-white leading-tight">
                  {isAr ? "فترتك التجريبية المجانية جاهزة (3 أيام PRO)" : "Your Free 3-Day Pro Trial is Ready"}
                </h4>
                <p className="text-xs text-zinc-300 mt-1 leading-relaxed">
                  {isAr
                    ? "استمتع بالماسح الفني اللحظي، شات الذكاء الاصطناعي بدون حدود، وتنبيهات تليجرام الفورية مجاناً بالكامل."
                    : "Full access to live scanner, unlimited AI stock chat, and instant Telegram alerts."}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={handleStartTrial}
                  disabled={loadingTrial}
                  className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-black text-xs uppercase tracking-wider transition-all cursor-pointer shadow-md shadow-emerald-500/30 flex items-center gap-1.5"
                >
                  {loadingTrial ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>{isAr ? "تفعيل التجربة الآن ⚡" : "Activate Trial Now ⚡"}</span>
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => setGuideOpen(true)}
                  className="px-3 py-2 rounded-xl border border-zinc-700 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-xs font-bold transition-all cursor-pointer flex items-center gap-1"
                >
                  <HelpCircle className="w-3.5 h-3.5 text-[#FFE600]" />
                  <span>{isAr ? "كيف أربح؟" : "How to win?"}</span>
                </button>
              </div>
            </div>
          ) : telegramUnlinked ? (
            /* Telegram Linking Reminder Mode */
            <div className="space-y-3 pe-6">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-full bg-purple-500 text-white text-[10px] font-black uppercase tracking-wider flex items-center gap-1">
                  <BellRing className="w-3 h-3" />
                  <span>{isAr ? "خطوة مهمة 📲" : "IMPORTANT 📲"}</span>
                </span>
                <span className="text-[11px] font-bold text-emerald-400">
                  {isAr ? "تنبيهات فورية على هاتفك" : "Mobile alerts"}
                </span>
              </div>

              <div>
                <h4 className="text-sm sm:text-base font-black text-white leading-tight">
                  {isAr ? "اربط تليجرام لتصلك صفقات الجلسة أولاً بأول" : "Link Telegram for Instant Market Alerts"}
                </h4>
                <p className="text-xs text-zinc-300 mt-1 leading-relaxed">
                  {isAr
                    ? "لا تفوّت انفجارات السيولة؛ تصلك إشعارات الاختراق ووقف الخسارة مباشرة على هاتفك دون فتح الشاشات."
                    : "Get real-time breakout and stop-loss signals sent directly to your phone."}
                </p>
              </div>

              <div className="pt-1">
                <Link
                  href="/profile#telegram"
                  onClick={() => setDismissed(true)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-black text-xs uppercase tracking-wider transition-all cursor-pointer shadow-md shadow-purple-600/30"
                >
                  <BellRing className="w-3.5 h-3.5" />
                  <span>{isAr ? "ربط تليجرام الآن (ثانية واحدة) 💬" : "Link Telegram Now 💬"}</span>
                </Link>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* 60-Second Onboarding Guide Modal */}
      <QuickProfitGuideModal
        isOpen={guideOpen}
        onClose={() => setGuideOpen(false)}
        onStartTrial={handleStartTrial}
        trialEligible={eligible}
      />
    </>
  );
}
