"use client";

import React, { useState, useEffect } from "react";
import {
  Sparkles,
  X,
  Send,
  Bot,
  ExternalLink,
  CheckCircle2,
  TrendingUp,
  Zap,
} from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import {
  TRIAL_AUTOSTART_EVENT,
  TRIAL_SUCCESS_EVENT,
  type TrialSuccessEventDetail,
} from "@/lib/trial-onboarding";

export default function TrialSuccessModal() {
  const { language } = useLanguage();
  const isAr = language === "ar";

  const [isOpen, setIsOpen] = useState(false);
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [telegramSent, setTelegramSent] = useState(false);

  useEffect(() => {
    const handleSuccessEvent = (event: Event) => {
      const customEvent = event as CustomEvent<TrialSuccessEventDetail>;
      const detail = customEvent.detail || {};
      setInviteLink(detail.invite_link || null);
      setTelegramSent(Boolean(detail.telegram_sent));
      setIsOpen(true);
    };

    window.addEventListener(TRIAL_SUCCESS_EVENT, handleSuccessEvent);
    return () => {
      window.removeEventListener(TRIAL_SUCCESS_EVENT, handleSuccessEvent);
    };
  }, []);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose(true);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  const handleClose = (startChat = true) => {
    setIsOpen(false);
    if (startChat) {
      window.dispatchEvent(new CustomEvent(TRIAL_AUTOSTART_EVENT));
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200"
      dir={isAr ? "rtl" : "ltr"}
      onClick={() => handleClose(true)}
      role="dialog"
      aria-modal="true"
      aria-labelledby="trial-success-title"
    >
      <div
        className="relative w-full max-w-lg rounded-3xl bg-zinc-950 text-white border-2 border-emerald-500/80 shadow-[0_0_50px_rgba(16,185,129,0.25)] p-5 sm:p-7 overflow-hidden animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Glow ambient background elements */}
        <div className="absolute -top-24 -left-24 w-52 h-52 bg-emerald-500/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -right-24 w-52 h-52 bg-blue-500/20 rounded-full blur-3xl pointer-events-none" />

        {/* Close Button */}
        <button
          type="button"
          onClick={() => handleClose(true)}
          className="absolute top-4 ltr:right-4 rtl:left-4 p-2 rounded-xl text-zinc-400 hover:text-white hover:bg-zinc-800/80 transition-colors cursor-pointer"
          aria-label={isAr ? "إغلاق" : "Close"}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header section */}
        <div className="space-y-3 text-center sm:text-start">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-xs font-black uppercase tracking-wider">
            <Sparkles className="w-3.5 h-3.5 fill-emerald-400" />
            <span>{isAr ? "مبروك! اشتراكك التجريبي نشط 3 أيام" : "Congrats! 3-Day Pro Trial Active"}</span>
          </div>

          <h3
            id="trial-success-title"
            className="text-xl sm:text-2xl font-black text-white leading-tight tracking-tight"
          >
            {isAr
              ? "أهلاً بك في باقة Stokscan Pro 🚀"
              : "Welcome to Stokscan Pro 🚀"}
          </h3>

          <p className="text-xs sm:text-sm text-zinc-300 leading-relaxed">
            {isAr
              ? "تم فتح كافة أدوات الماسح الفني اللحظي، مؤشرات السيولة، ومساعد الذكاء الاصطناعي مجاناً بالكامل لمدة 3 أيام."
              : "Full access to real-time technical scanner, volume radars, and AI assistant unlocked for 3 days."}
          </p>
        </div>

        {/* Highlight Card: VIP Telegram Channel */}
        <div className="mt-5 p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-emerald-950/40 via-zinc-900/90 to-blue-950/30 border border-emerald-500/40 space-y-3.5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="p-2 rounded-xl bg-[#229ED9]/20 text-[#229ED9] border border-[#229ED9]/40">
                <Send className="w-4 h-4 rtl:rotate-180" />
              </span>
              <div>
                <h4 className="text-sm font-black text-white flex items-center gap-1.5">
                  <span>{isAr ? "قناة توصيات VIP على تليجرام" : "VIP Telegram Recommendations"}</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold">
                    {isAr ? "صفقات حية" : "Live Signals"}
                  </span>
                </h4>
                <p className="text-[11px] text-zinc-400 mt-0.5">
                  {isAr
                    ? "إشارات الدخول، الأهداف، وتنبيهات وقف الخسارة اللحظية"
                    : "Instant buy signals, targets, and adaptive stop-losses"}
                </p>
              </div>
            </div>
          </div>

          {inviteLink ? (
            <div className="space-y-2">
              <a
                href={inviteLink}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => {
                  // Keep modal or user may return, but link opened in new tab
                }}
                className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-black font-black text-sm shadow-lg shadow-emerald-500/25 transition-all transform hover:scale-[1.02] active:scale-[0.98] cursor-pointer"
              >
                <Send className="w-4 h-4 rtl:rotate-180 text-black" />
                <span>{isAr ? "🚀 انضم الآن لقناة توصيات VIP" : "🚀 Join VIP Telegram Channel Now"}</span>
                <ExternalLink className="w-3.5 h-3.5 text-black/70" />
              </a>

              {telegramSent && (
                <div className="flex items-center gap-1.5 text-[11px] text-emerald-400/90 font-medium justify-center pt-1">
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                  <span>
                    {isAr
                      ? "تم إرسال رابط القناة أيضاً إلى محادثتك على بوت تليجرام"
                      : "The invite link has also been sent to your Telegram bot chat"}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <a
              href="/profile#telegram-pro"
              className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-[#229ED9] hover:bg-[#1f8ec4] text-white font-black text-sm shadow-lg transition-all cursor-pointer"
            >
              <Send className="w-4 h-4 rtl:rotate-180" />
              <span>{isAr ? "عرض رابط قناة VIP في حسابك" : "View VIP Channel Link in Profile"}</span>
            </a>
          )}
        </div>

        {/* Feature quick badges */}
        <div className="grid grid-cols-2 gap-2 mt-4 text-[11px] text-zinc-300">
          <div className="flex items-center gap-2 p-2 rounded-xl bg-zinc-900/60 border border-zinc-800">
            <TrendingUp className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{isAr ? "ماسح السيولة والفرص" : "Volume & Breakout Radar"}</span>
          </div>
          <div className="flex items-center gap-2 p-2 rounded-xl bg-zinc-900/60 border border-zinc-800">
            <Zap className="w-4 h-4 text-amber-400 shrink-0" />
            <span>{isAr ? "تحليل غير محدود للأسهم" : "Unlimited Stock Analysis"}</span>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="mt-5 pt-4 border-t border-zinc-800/80 flex flex-col sm:flex-row items-center gap-2.5">
          <button
            type="button"
            onClick={() => handleClose(true)}
            className="w-full sm:flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-white font-bold text-xs sm:text-sm border border-zinc-700 transition-colors cursor-pointer"
          >
            <Bot className="w-4 h-4 text-emerald-400" />
            <span>{isAr ? "🤖 ابدأ تجربة شات الذكاء الاصطناعي" : "🤖 Start AI Chat Assistant"}</span>
          </button>

          <button
            type="button"
            onClick={() => handleClose(false)}
            className="w-full sm:w-auto px-4 py-2.5 text-xs text-zinc-400 hover:text-white transition-colors cursor-pointer text-center"
          >
            {isAr ? "تصفح المنصة" : "Browse Platform"}
          </button>
        </div>
      </div>
    </div>
  );
}
