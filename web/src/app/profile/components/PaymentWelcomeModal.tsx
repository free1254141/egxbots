"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  X,
  ExternalLink,
  Copy,
  Check,
  Bot,
  Sparkles,
  Crown,
  Loader2,
  RefreshCw,
  AlertTriangle,
  ArrowRight,
  ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";
import type { TelegramProInvite } from "@/contexts/TelegramProContext";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  orderId?: string | null;
  userId?: string | null;
  isAr?: boolean;
  proInvite: TelegramProInvite;
  telegramLinked: boolean;
  onRefreshInvite: () => Promise<void>;
  onRefreshProfile: () => Promise<void>;
}

export default function PaymentWelcomeModal({
  isOpen,
  onClose,
  orderId,
  userId,
  isAr = true,
  proInvite,
  telegramLinked,
  onRefreshInvite,
  onRefreshProfile,
}: Props) {
  const [copied, setCopied] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [orderData, setOrderData] = useState<{
    status?: string;
    plan_id?: string;
    telegram_pro_url?: string;
    subscription?: { current_period_end?: string | null };
  } | null>(null);
  const [checkingBot, setCheckingBot] = useState(false);
  const pollCountRef = useRef(0);

  // Check order status if orderId is provided
  const checkStatus = useCallback(async () => {
    if (!orderId) return;
    try {
      const res = await fetch(`/api/payment/easykash/status?order_id=${encodeURIComponent(orderId)}`, {
        cache: "no-store",
        signal: AbortSignal.timeout(8000),
      });
      if (res.ok) {
        const data = await res.json();
        setOrderData(data);
        if (data.status === "approved") {
          void onRefreshInvite();
          void onRefreshProfile();
        }
      }
    } catch {
      // Ignore transient network errors
    }
  }, [orderId, onRefreshInvite, onRefreshProfile]);

  useEffect(() => {
    if (!isOpen) return;

    if (orderId && (!orderData || orderData.status === "pending" || orderData.status === "submitted")) {
      setVerifying(true);
      void checkStatus().finally(() => setVerifying(false));

      const interval = setInterval(() => {
        pollCountRef.current += 1;
        if (pollCountRef.current > 3) {
          clearInterval(interval);
          return;
        }
        void checkStatus();
      }, 6000);

      return () => clearInterval(interval);
    }
  }, [isOpen, orderId, checkStatus, orderData]);

  // When tab gains focus (e.g. user returns from Telegram), re-check bot status
  useEffect(() => {
    if (!isOpen) return;

    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        setCheckingBot(true);
        Promise.all([onRefreshProfile(), onRefreshInvite()]).finally(() => {
          setTimeout(() => setCheckingBot(false), 500);
        });
      }
    };

    window.addEventListener("focus", handleVisibility);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.removeEventListener("focus", handleVisibility);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [isOpen, onRefreshProfile, onRefreshInvite]);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const vipLink =
    proInvite.invite_link ||
    orderData?.telegram_pro_url ||
    "";

  const isBotActive = telegramLinked || Boolean(proInvite.bot_active) || Boolean(proInvite.telegram_chat_id);
  const botAppUrl = userId ? `https://t.me/egxbots_bot?start=${userId}` : "https://t.me/egxbots_bot";

  const periodEnd =
    proInvite.current_period_end ||
    orderData?.subscription?.current_period_end ||
    null;

  const formattedPeriodEnd = periodEnd
    ? new Date(periodEnd).toLocaleDateString(isAr ? "ar-EG" : "en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;

  const handleCopyLink = () => {
    if (!vipLink) return;
    try {
      navigator.clipboard.writeText(vipLink);
      setCopied(true);
      toast.success(isAr ? "تم نسخ رابط قناة VIP بنجاح!" : "VIP link copied!");
      setTimeout(() => setCopied(false), 2500);
    } catch {
      toast.error(isAr ? "تعذر نسخ الرابط تلقائياً" : "Failed to copy link");
    }
  };

  const handleManualCheck = async () => {
    setCheckingBot(true);
    await Promise.all([onRefreshProfile(), onRefreshInvite()]);
    setCheckingBot(false);
    toast.info(isAr ? "تم تحديث الحالة" : "Status refreshed");
  };

  return (
    <div
      dir={isAr ? "rtl" : "ltr"}
      className="fixed inset-0 z-[10000] flex items-center justify-center p-3 sm:p-5 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-lg bg-white dark:bg-zinc-950 border-4 border-black dark:border-white shadow-[8px_8px_0px_#000] dark:shadow-[8px_8px_0px_#10b981] overflow-hidden max-h-[92vh] flex flex-col">
        {/* Top Header Banner */}
        <div className="bg-gradient-to-r from-amber-400 via-yellow-400 to-amber-500 text-black px-4 sm:px-6 py-4 border-b-4 border-black flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-none bg-black text-amber-400 flex items-center justify-center border-2 border-black shadow-[2px_2px_0px_#000]">
              <Crown className="w-5 h-5 fill-amber-400" />
            </div>
            <div>
              <span className="inline-block px-2 py-0.5 bg-black text-amber-400 text-[10px] font-black uppercase tracking-wider mb-0.5">
                {isAr ? "تأكيد الاشتراك" : "SUBSCRIPTION CONFIRMED"}
              </span>
              <h2 className="text-lg sm:text-xl font-black text-black leading-tight">
                {isAr ? "🎉 مبروك! تم تفعيل اشتراكك" : "🎉 Congratulations! Plan Activated"}
              </h2>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 bg-black text-white hover:bg-zinc-800 flex items-center justify-center border-2 border-black transition-colors"
            aria-label={isAr ? "إغلاق" : "Close"}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Body Content */}
        <div className="p-4 sm:p-6 space-y-4 overflow-y-auto">
          {/* Plan Summary Card */}
          <div className="p-3.5 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 shadow-[3px_3px_0px_#000] dark:shadow-[3px_3px_0px_rgba(255,255,255,0.2)]">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0" />
                <div>
                  <span className="text-xs text-zinc-500 dark:text-zinc-400 font-bold block">
                    {isAr ? "الخطة المفعّلة" : "Active Plan"}
                  </span>
                  <span className="text-sm font-black text-zinc-900 dark:text-white">
                    {isAr ? "باقة Pro المتقدمة" : "Pro Plan"}
                  </span>
                </div>
              </div>
              <div className="text-left rtl:text-right">
                {(orderData?.status === "approved" || Boolean(proInvite.current_period_end) || isBotActive) ? (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-emerald-500 text-black text-xs font-black border border-black shadow-[1px_1px_0px_#000]">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    {isAr ? "مفعّل ونشط" : "Active"}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-amber-400 text-black text-xs font-black border border-black shadow-[1px_1px_0px_#000]">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    {isAr ? "جاري التأكيد" : "Verifying"}
                  </span>
                )}
              </div>
            </div>

            {formattedPeriodEnd && (
              <div className="mt-2 pt-2 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-between text-xs font-bold text-zinc-600 dark:text-zinc-300">
                <span>{isAr ? "تاريخ التجديد / الانتهاء:" : "Renewal / Expiry:"}</span>
                <span className="font-black text-zinc-900 dark:text-white">{formattedPeriodEnd}</span>
              </div>
            )}
          </div>

          {/* Section 1: Telegram VIP Channel */}
          <div className="p-4 bg-emerald-50 dark:bg-emerald-950/40 border-2 border-emerald-600 dark:border-emerald-500 shadow-[3px_3px_0px_#059669]">
            <div className="flex items-start gap-2.5 mb-2.5">
              <div className="w-7 h-7 bg-emerald-600 text-white flex items-center justify-center shrink-0 border border-black shadow-[1px_1px_0px_#000]">
                <Sparkles className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-black text-sm text-emerald-950 dark:text-emerald-200">
                  {isAr ? "💎 قناة التوصيات والإشارات الخاصة (VIP)" : "💎 VIP Signals & Trading Channel"}
                </h3>
                <p className="text-xs text-emerald-800 dark:text-emerald-300 font-bold mt-0.5 leading-relaxed">
                  {isAr
                    ? "انضم الآن لقناة تليجرام الخاصة بالمشتركين لمتابعة إشارات الدخول والأهداف السعرية وتنبيهات السوق لحظة بلحظة."
                    : "Join the private VIP channel to receive real-time buy signals, price targets, and market alerts."}
                </p>
              </div>
            </div>

            {vipLink ? (
              <div className="space-y-2 mt-3">
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={vipLink}
                    dir="ltr"
                    className="flex-1 px-3 py-2 text-xs font-mono bg-white dark:bg-zinc-900 border-2 border-black dark:border-zinc-600 text-zinc-800 dark:text-zinc-200 truncate select-all focus:outline-hidden"
                  />
                  <button
                    onClick={handleCopyLink}
                    className="px-3 py-2 bg-white dark:bg-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-700 text-black dark:text-white border-2 border-black dark:border-zinc-500 font-black text-xs flex items-center gap-1 shrink-0 shadow-[2px_2px_0px_#000] active:translate-x-0.5 active:translate-y-0.5"
                    title={isAr ? "نسخ الرابط" : "Copy Link"}
                  >
                    {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
                    <span>{copied ? (isAr ? "تم النسخ" : "Copied") : (isAr ? "نسخ" : "Copy")}</span>
                  </button>
                </div>

                <a
                  href={vipLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-black text-xs sm:text-sm border-2 border-black shadow-[3px_3px_0px_#000] active:translate-x-0.5 active:translate-y-0.5 transition-all"
                >
                  <span>{isAr ? "الانضمام لقناة VIP الآن 🚀" : "Join VIP Channel Now 🚀"}</span>
                  <ExternalLink className="w-4 h-4" />
                </a>
              </div>
            ) : (
              <div className="mt-2 p-2.5 bg-white dark:bg-zinc-900 border border-emerald-300 dark:border-emerald-800 text-xs text-emerald-800 dark:text-emerald-300 font-bold flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin shrink-0 text-emerald-600" />
                  <span>{isAr ? "جاري تجهيز وتأكيد الرابط..." : "Preparing your VIP link..."}</span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    pollCountRef.current = 0;
                    setVerifying(true);
                    void checkStatus().finally(() => setVerifying(false));
                  }}
                  disabled={verifying}
                  className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-black text-xs border border-black cursor-pointer shadow-[1px_1px_0px_#000] active:translate-x-0.5 active:translate-y-0.5"
                >
                  {verifying ? (isAr ? "جاري الفحص..." : "Checking...") : (isAr ? "تحقق الآن" : "Check now")}
                </button>
              </div>
            )}
          </div>

          {/* Section 2: Telegram Bot Activation Status */}
          {isBotActive ? (
            /* Bot is Active / Linked */
            <div className="p-3.5 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 shadow-[3px_3px_0px_#000]">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 bg-emerald-500 text-black flex items-center justify-center font-black border border-black shadow-[1px_1px_0px_#000]">
                    <Bot className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="font-black text-xs sm:text-sm text-zinc-900 dark:text-white flex items-center gap-1.5">
                      <span>{isAr ? "بوت التليجرام مفعّل ومربوط" : "Telegram Bot Connected"}</span>
                      <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                    </h4>
                    <p className="text-[11px] text-zinc-600 dark:text-zinc-400 font-bold mt-0.5">
                      {isAr
                        ? "تم إرسال رسالة ترحيبية وتفاصيل اشتراكك ورابط الـ VIP إلى تليجرام."
                        : "Welcome message & VIP invite were dispatched to your Telegram."}
                    </p>
                  </div>
                </div>
                <a
                  href="https://t.me/egxbots_bot"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-3 py-1.5 bg-black text-white hover:bg-zinc-800 dark:bg-white dark:text-black font-black text-xs flex items-center gap-1 shrink-0 border border-black shadow-[2px_2px_0px_rgba(0,0,0,0.5)]"
                >
                  <span>{isAr ? "فتح البوت" : "Open Bot"}</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </div>
          ) : (
            /* Bot is NOT Active / NOT Linked - Call to Action! */
            <div className="p-4 bg-amber-50 dark:bg-amber-950/40 border-2 border-amber-500 shadow-[3px_3px_0px_#f59e0b]">
              <div className="flex items-start gap-2.5">
                <div className="w-7 h-7 bg-amber-500 text-black flex items-center justify-center shrink-0 border border-black shadow-[1px_1px_0px_#000]">
                  <AlertTriangle className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="font-black text-sm text-amber-950 dark:text-amber-200">
                      {isAr ? "⚠️ خطوة مهمة: ربط وتفعيل بوت التليجرام" : "⚠️ Important: Link Telegram Bot"}
                    </h4>
                    <button
                      onClick={handleManualCheck}
                      disabled={checkingBot}
                      className="text-[11px] font-bold text-amber-900 dark:text-amber-300 hover:underline flex items-center gap-1"
                    >
                      <RefreshCw className={`w-3 h-3 ${checkingBot ? "animate-spin" : ""}`} />
                      <span>{isAr ? "تحقق الآن" : "Check"}</span>
                    </button>
                  </div>
                  <p className="text-xs text-amber-900 dark:text-amber-200/90 font-bold mt-1 leading-relaxed">
                    {isAr
                      ? "لم تقم بربط حسابك بالبوت بعد! فعّل البوت الآن لتصلك تنبيهات الأسهم الفورية وإشارات وقف الخسارة ورسالة الترحيب، واحصل على +10 رسائل هدية 🎁"
                      : "Connect your Telegram bot to receive live trade notifications, stop-loss alerts, and +10 bonus AI messages 🎁"}
                  </p>

                  <div className="mt-3">
                    <a
                      href={botAppUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-amber-500 hover:bg-amber-400 text-black font-black text-xs sm:text-sm border-2 border-black shadow-[3px_3px_0px_#000] active:translate-x-0.5 active:translate-y-0.5 transition-all"
                    >
                      <Bot className="w-4 h-4" />
                      <span>{isAr ? "🤖 تفعيل بوت التليجرام الآن (+10 رسائل هدية)" : "🤖 Activate Telegram Bot (+10 Bonus)"}</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                    <p className="text-[10px] text-amber-800 dark:text-amber-400 font-bold text-center mt-1.5">
                      {isAr
                        ? "بمجرد الضغط على Start في تليجرام، سيرسل لك البوت رسالة الترحيب ورابط الـ VIP فوراً!"
                        : "Once you tap Start in Telegram, the bot will link and send your VIP invite instantly!"}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Bottom Actions Bar */}
        <div className="p-3 sm:p-4 bg-zinc-100 dark:bg-zinc-900 border-t-4 border-black dark:border-white flex flex-col-reverse sm:flex-row items-center justify-between gap-2.5 shrink-0">
          <button
            onClick={onClose}
            className="w-full sm:w-auto px-4 py-2 bg-white dark:bg-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-900 dark:text-white font-black text-xs border-2 border-black dark:border-zinc-600 shadow-[2px_2px_0px_#000] transition-all"
          >
            {isAr ? "إغلاق والعودة للبروفايل" : "Close & Stay on Profile"}
          </button>

          <Link
            href="/reports"
            onClick={onClose}
            className="w-full sm:w-auto flex items-center justify-center gap-1.5 px-5 py-2 bg-black text-white hover:bg-zinc-800 dark:bg-emerald-500 dark:text-black dark:hover:bg-emerald-400 font-black text-xs border-2 border-black shadow-[2px_2px_0px_#000] transition-all"
          >
            <span>{isAr ? "تصفح تقارير السوق اليومية" : "Browse Market Reports"}</span>
            <ArrowRight className="w-3.5 h-3.5 rtl:rotate-180" />
          </Link>
        </div>
      </div>
    </div>
  );
}
