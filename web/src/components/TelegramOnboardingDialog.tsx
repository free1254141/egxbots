"use client";

/**
 * TelegramOnboardingDialog
 * ─────────────────────────
 * Simple centered welcome offer dialog shown to eligible logged-in users
 * right after login (and after MarketWelcomeDialog is resolved) so they
 * can link Telegram in one click and activate their free 3-day Pro trial.
 */

import React, { useEffect, useState, useCallback, useRef } from "react";
import {
  X,
  Send,
  Copy,
  CheckCircle2,
  ExternalLink,
  Sparkles,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { useMarket } from "@/contexts/MarketContext";
import { toast } from "sonner";
import {
  fetchUserQuotaCached,
  invalidateUserQuotaCache,
} from "@/lib/user-quota-client";
import { broadcastEntitlements } from "@/lib/entitlements";
import {
  prepareTrialAutostart,
  clearTrialAutostart,
  triggerTrialSuccessModal,
} from "@/lib/trial-onboarding";
import {
  getTrialDeviceFingerprint,
  notifyTrialActivationError,
} from "@/lib/device-fingerprint";

const DISMISS_KEY_PREFIX = "egxbots_tg_onboard_dismissed_v1:";
const DISMISS_TTL_MS = 24 * 3600 * 1000; // 24 hours

export default function TelegramOnboardingDialog() {
  const { user } = useAuth();
  const { language } = useLanguage();
  const { hasChosenMarket } = useMarket();
  const isAr = language === "ar";

  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [isPreview, setIsPreview] = useState(false);
  const [telegramLinked, setTelegramLinked] = useState(false);
  const [waitingForLink, setWaitingForLink] = useState(false);
  const [checkingStatus, setCheckingStatus] = useState(false);
  const [activatingTrial, setActivatingTrial] = useState(false);
  const [copied, setCopied] = useState(false);

  const waitingRef = useRef(false);
  waitingRef.current = waitingForLink;

  useEffect(() => {
    setMounted(true);
  }, []);

  const effectiveUserId = user?.id || "demo-user-id";
  const dismissKey = user?.id ? `${DISMISS_KEY_PREFIX}${user.id}` : null;

  const markDismissed = useCallback(
    (ttlMs: number = DISMISS_TTL_MS) => {
      setOpen(false);
      setWaitingForLink(false);
      if (isPreview || !dismissKey) return;
      try {
        localStorage.setItem(dismissKey, String(Date.now() + ttlMs));
      } catch {
        // ignore storage errors
      }
    },
    [dismissKey, isPreview]
  );

  // Check client-only preview query param first, otherwise check eligibility after login & MarketWelcomeDialog
  useEffect(() => {
    if (!mounted) return;

    try {
      const previewVal = new URLSearchParams(window.location.search).get("preview_tg_dialog");
      if (previewVal === "1" || previewVal === "true" || previewVal === "linked") {
        setIsPreview(true);
        setTelegramLinked(previewVal === "linked");
        setOpen(true);
        return;
      }
    } catch {
      // ignore URL parsing errors
    }

    setIsPreview(false);

    if (!user?.id || !hasChosenMarket) {
      if (!user) setOpen(false);
      return;
    }

    try {
      const dismissedUntil = localStorage.getItem(`${DISMISS_KEY_PREFIX}${user.id}`);
      if (dismissedUntil && Number(dismissedUntil) > Date.now()) {
        return;
      }
    } catch {
      // ignore storage errors
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    void fetchUserQuotaCached(user.id)
      .then((quota) => {
        if (cancelled || !quota?.ok) return;
        const plan = quota?.plan || {};
        const isEligible = Boolean(plan.trial_eligible);
        const isProOrTrial = Boolean(plan.is_pro || plan.is_trial);
        const isLinked = Boolean(plan.telegram_linked);

        if (!isEligible || isProOrTrial) {
          return;
        }

        setTelegramLinked(isLinked);
        timer = setTimeout(() => {
          if (!cancelled) setOpen(true);
        }, 600);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [mounted, user?.id, hasChosenMarket]);

  // Escape key closes the dialog
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") markDismissed();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, markDismissed]);

  // Re-check quota when user returns from Telegram app
  const recheckLinkStatus = useCallback(
    async (silent = false) => {
      if (!user?.id) return;
      setCheckingStatus(true);
      try {
        try {
          sessionStorage.removeItem("egxbots_trial_status_v2");
        } catch {
          // ignore
        }
        invalidateUserQuotaCache(user.id);
        const quota = await fetchUserQuotaCached(user.id, { force: true });
        const plan = quota?.plan || {};

        if (plan.is_trial || plan.is_pro) {
          broadcastEntitlements(true);
          toast.success(
            isAr
              ? "🎉 تم ربط تليجرام وتفعيل التجربة المجانية 3 أيام بنجاح!"
              : "🎉 Telegram linked & 3-day free Pro trial activated!"
          );
          markDismissed(30 * 24 * 3600 * 1000);
          return;
        }

        if (plan.telegram_linked) {
          setTelegramLinked(true);
          setWaitingForLink(false);
          toast.success(
            isAr
              ? "✅ تم ربط تليجرام بنجاح! اضغط الآن لتفعيل التجربة المجانية."
              : "✅ Telegram linked! Click below to activate your free trial."
          );
        } else if (!silent) {
          toast.info(
            isAr
              ? "لم يصل الربط بعد — تأكد من الضغط على Start داخل بوت @egxbots_bot"
              : "Not linked yet — make sure you tapped Start in @egxbots_bot"
          );
        }
      } catch {
        if (!silent) {
          toast.error(isAr ? "تعذّر التحقق من الحالة" : "Could not check status");
        }
      } finally {
        setCheckingStatus(false);
      }
    },
    [user?.id, isAr, markDismissed]
  );

  useEffect(() => {
    if (!open || !user?.id) return;
    const onVisibility = () => {
      if (document.visibilityState === "visible" && waitingRef.current) {
        void recheckLinkStatus(true);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [open, user?.id, recheckLinkStatus]);

  const handleOpenTelegram = useCallback(() => {
    setWaitingForLink(true);
    try {
      sessionStorage.removeItem("egxbots_trial_status_v2");
    } catch {
      // ignore
    }
    if (user?.id) invalidateUserQuotaCache(user.id);
  }, [user?.id]);

  const handleCopyCode = useCallback(async () => {
    const code = `/start ${effectiveUserId}`;
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setWaitingForLink(true);
      toast.success(
        isAr
          ? "✅ تم نسخ الكود — افتح @egxbots_bot في تليجرام وأرسله!"
          : "✅ Code copied — open @egxbots_bot on Telegram and send it!"
      );
      setTimeout(() => setCopied(false), 3000);
    } catch {
      toast.error(isAr ? "تعذّر نسخ الكود" : "Failed to copy code");
    }
  }, [effectiveUserId, isAr]);

  const handleActivateTrial = useCallback(async () => {
    if (isPreview && !user?.id) {
      toast.info(isAr ? "هذا وضع المعاينة فقط" : "Preview mode only");
      return;
    }
    if (!user?.id) return;
    setActivatingTrial(true);
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
        broadcastEntitlements(true);
        toast.success(
          isAr
            ? "🎉 مبروك! تم تفعيل تجربة Pro المجانية لمدة 3 أيام بنجاح!"
            : "🎉 Congrats! 3-day free Pro trial activated!"
        );
        markDismissed(30 * 24 * 3600 * 1000);
        triggerTrialSuccessModal({
          invite_link: data.invite_link,
          expires_at: data.expires_at,
          telegram_sent: data.telegram_sent,
        });
      } else {
        clearTrialAutostart();
        notifyTrialActivationError(data, isAr, user.id);
        if (data?.error === "TELEGRAM_LINK_REQUIRED") {
          setTelegramLinked(false);
        }
      }
    } catch {
      clearTrialAutostart();
      toast.error(isAr ? "حدث خطأ في الاتصال" : "Network error");
    } finally {
      setActivatingTrial(false);
    }
  }, [user?.id, isPreview, isAr, markDismissed]);

  if (!mounted || !open || (!user?.id && !isPreview)) return null;

  const botLink = `https://t.me/egxbots_bot?start=${effectiveUserId}`;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="tg-onboard-title"
      dir={isAr ? "rtl" : "ltr"}
      className="fixed inset-0 z-[1000] flex items-center justify-center p-4 bg-black/65 backdrop-blur-sm animate-in fade-in duration-200 overflow-y-auto"
      onClick={() => markDismissed()}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-md rounded-2xl border-3 border-black dark:border-white/20 bg-white dark:bg-zinc-950 text-zinc-950 dark:text-white shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[0_24px_64px_rgba(0,0,0,0.7)] overflow-hidden my-auto"
      >
        {/* Top accent strip */}
        <div className="h-1.5 w-full bg-gradient-to-r from-[#FFE600] via-emerald-400 to-sky-500" />

        {/* Close button */}
        <button
          type="button"
          onClick={() => markDismissed()}
          className="absolute top-3.5 ltr:right-3.5 rtl:left-3.5 p-1.5 rounded-lg text-zinc-500 hover:text-zinc-950 dark:text-zinc-400 dark:hover:text-white hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer"
          aria-label={isAr ? "إغلاق" : "Close"}
        >
          <X className="w-4 h-4" />
        </button>

        <div className="p-5 sm:p-6 space-y-4">
          {/* Badge + Heading */}
          <div className="flex flex-col items-center text-center gap-2 pt-1">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#FFE600] text-black text-xs font-black tracking-wide border border-black">
              <Sparkles className="w-3.5 h-3.5" />
              {isAr ? "هدية ترحيبية مجانية — بدون بطاقة بنكية" : "Free Welcome Gift — No Credit Card"}
            </span>

            <h2
              id="tg-onboard-title"
              className="text-xl font-black tracking-tight leading-snug mt-1"
            >
              {isAr
                ? "جرّب جميع أدوات Pro مجاناً لمدة 3 أيام 🎁"
                : "Try All Pro Tools Free for 3 Days 🎁"}
            </h2>

            <p className="text-xs sm:text-sm text-zinc-600 dark:text-zinc-400 leading-relaxed">
              {telegramLinked
                ? isAr
                  ? "حسابك مربوط بتليجرام وجاهز — اضغط الزر بالأسفل لبدء فترتك التجريبية فوراً."
                  : "Your Telegram is linked and ready — click below to start your free trial immediately."
                : isAr
                  ? "خطوة واحدة فقط (تستغرق 5 ثوانٍ): اربط حسابك ببوت تليجرام وسيتم تفعيل تجربتك المجانية تلقائياً!"
                  : "Just one 5-second step: link your account with our Telegram bot and your free trial activates automatically!"}
            </p>
          </div>

          {/* Feature highlights */}
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-xl bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 p-2.5">
              <div className="text-base">🤖</div>
              <div className="text-[11px] font-bold mt-0.5">
                {isAr ? "شات ARTORO" : "ARTORO AI"}
              </div>
            </div>
            <div className="rounded-xl bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 p-2.5">
              <div className="text-base">📡</div>
              <div className="text-[11px] font-bold mt-0.5">
                {isAr ? "رادار السيولة" : "Live Radar"}
              </div>
            </div>
            <div className="rounded-xl bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 p-2.5">
              <div className="text-base">📲</div>
              <div className="text-[11px] font-bold mt-0.5">
                {isAr ? "تنبيهات VIP" : "VIP Alerts"}
              </div>
            </div>
          </div>

          {telegramLinked ? (
            /* Already linked -> Direct 1-click trial activation */
            <div className="space-y-2.5 pt-1">
              <button
                type="button"
                onClick={handleActivateTrial}
                disabled={activatingTrial}
                className="flex items-center justify-center gap-2 w-full rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-black text-sm py-3 border-2 border-black shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] transition-all cursor-pointer disabled:opacity-60"
              >
                {activatingTrial ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4" />
                )}
                <span>
                  {isAr ? "تفعيل 3 أيام Pro مجاناً الآن ⚡" : "Activate 3-Day Pro Trial Now ⚡"}
                </span>
              </button>

              <button
                type="button"
                onClick={() => markDismissed()}
                className="w-full rounded-xl py-2 text-xs font-bold text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white transition-colors cursor-pointer"
              >
                {isAr ? "لاحقاً" : "Maybe later"}
              </button>
            </div>
          ) : (
            /* Needs Telegram link -> 1-click deep link + copyable fallback */
            <div className="space-y-3 pt-1">
              <a
                href={botLink}
                target="_blank"
                rel="noopener noreferrer"
                onClick={handleOpenTelegram}
                className="flex items-center justify-center gap-2 w-full rounded-xl bg-[#229ED9] hover:bg-[#1e8ec4] text-white font-black text-sm py-3 border-2 border-black dark:border-sky-300/40 shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] transition-all"
              >
                <Send className="w-4 h-4" />
                <span>
                  {isAr ? "اربط تليجرام وفعّل 3 أيام مجاناً" : "Link Telegram & Start 3 Free Days"}
                </span>
                <ExternalLink className="w-3.5 h-3.5 opacity-80" />
              </a>

              {waitingForLink && (
                <button
                  type="button"
                  onClick={() => void recheckLinkStatus(false)}
                  disabled={checkingStatus}
                  className="flex items-center justify-center gap-2 w-full rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/40 text-emerald-700 dark:text-emerald-300 font-bold text-xs py-2.5 transition-colors cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${checkingStatus ? "animate-spin" : ""}`} />
                  <span>
                    {isAr
                      ? "ضغطت Start في تليجرام؟ اضغط للتحقق الآن"
                      : "Tapped Start on Telegram? Check status now"}
                  </span>
                </button>
              )}

              {/* Compact copy fallback if t.me doesn't open */}
              <div className="flex items-center justify-between gap-2 rounded-xl bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 px-3 py-2">
                <div className="min-w-0">
                  <div className="text-[10px] font-bold text-zinc-500 dark:text-zinc-400">
                    {isAr
                      ? "الرابط لم يفتح؟ انسخ الكود وأرسله لبوت @egxbots_bot:"
                      : "Link didn't open? Copy & send to @egxbots_bot:"}
                  </div>
                  <code
                    dir="ltr"
                    className="block text-[11px] font-mono text-sky-700 dark:text-sky-300 truncate mt-0.5"
                  >
                    /start {effectiveUserId}
                  </code>
                </div>
                <button
                  type="button"
                  onClick={handleCopyCode}
                  className="flex-shrink-0 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-xs font-bold hover:bg-zinc-50 dark:hover:bg-zinc-700 transition-colors cursor-pointer"
                >
                  {copied ? (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      <span>{isAr ? "تم" : "Copied"}</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      <span>{isAr ? "نسخ" : "Copy"}</span>
                    </>
                  )}
                </button>
              </div>

              <button
                type="button"
                onClick={() => markDismissed()}
                className="w-full rounded-xl py-1.5 text-xs font-bold text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white transition-colors cursor-pointer"
              >
                {isAr ? "لاحقاً" : "Maybe later"}
              </button>
            </div>
          )}

          {/* FRA analytical tool disclaimer */}
          <p className="text-center text-[10px] text-zinc-500 dark:text-zinc-500 leading-relaxed">
            {isAr
              ? "EGX BOTS أداة تحليلية برمجية للأبحاث الشخصية والتعليمية فقط ولا تُعد نصيحة استثمارية."
              : "EGX BOTS is an analytical software tool for personal research & education only, not investment advice."}
          </p>
        </div>
      </div>
    </div>
  );
}
