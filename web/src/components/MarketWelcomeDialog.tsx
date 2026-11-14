"use client";

import React, { useEffect, useState, useCallback } from "react";
import { X, ArrowLeft, ArrowRight, Sparkles } from "lucide-react";
import { useMarket } from "@/contexts/MarketContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { EgyptFlag, SaudiFlag } from "@/components/MarketFlag";

export default function MarketWelcomeDialog() {
  const { hasChosenMarket, setMarket } = useMarket();
  const { language } = useLanguage();
  const [mounted, setMounted] = useState(false);
  const isAr = language === "ar";

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleDismiss = useCallback(() => {
    setMarket("egx");
  }, [setMarket]);

  useEffect(() => {
    if (!mounted || hasChosenMarket) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        handleDismiss();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mounted, hasChosenMarket, handleDismiss]);

  if (!mounted || hasChosenMarket) return null;

  const ArrowIcon = isAr ? ArrowLeft : ArrowRight;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="market-welcome-title"
      dir={isAr ? "rtl" : "ltr"}
      className="fixed inset-0 z-[90] flex items-center justify-center p-4 bg-black/65 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={handleDismiss}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-xl rounded-2xl border-3 border-black dark:border-white bg-white dark:bg-zinc-950 text-zinc-950 dark:text-white shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.25)] p-5 sm:p-7"
      >
        <button
          type="button"
          onClick={handleDismiss}
          aria-label={isAr ? "إغلاق واختيار السوق المصري افتراضياً" : "Close and default to Egyptian Market"}
          className="absolute top-4 end-4 w-8 h-8 rounded-lg border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900 hover:bg-zinc-200 dark:hover:bg-zinc-800 flex items-center justify-center transition-colors cursor-pointer"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="mb-5 pe-8">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-100 dark:bg-zinc-900 border-2 border-black dark:border-white/30 text-[11px] font-black uppercase tracking-wider mb-3">
            <Sparkles className="w-3.5 h-3.5 text-amber-500" />
            <span>{isAr ? "مرحباً بك في EGX BOTS" : "Welcome to EGX BOTS"}</span>
          </div>
          <h2 id="market-welcome-title" className="text-xl sm:text-2xl font-black tracking-tight">
            {isAr ? "اختر السوق الذي تتابعه الآن" : "Choose Your Primary Market"}
          </h2>
          <p className="mt-1.5 text-xs sm:text-sm text-zinc-600 dark:text-zinc-400 leading-relaxed">
            {isAr
              ? "حدد سوق البداية لعرض الأسهم والماسح والتوصيات بالعملة والمؤشر المناسبين."
              : "Pick your starting market to display stocks, scanners, and signals in the matching currency and index."}
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
          {/* Egypt Card */}
          <button
            type="button"
            onClick={() => setMarket("egx")}
            className="group text-start flex flex-col justify-between p-4 rounded-xl border-3 border-black dark:border-white bg-[#FFE600]/15 hover:bg-[#FFE600] text-zinc-950 dark:text-white hover:text-black shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_0px_rgba(255,255,255,0.25)] hover:-translate-y-0.5 transition-all cursor-pointer"
          >
            <div>
              <div className="flex items-center justify-between gap-2 mb-3">
                <EgyptFlag className="w-9 h-6" />
                <span className="px-2 py-0.5 rounded-md bg-[#FFE600] text-black border-2 border-black text-[11px] font-black">
                  EGX
                </span>
              </div>
              <div className="text-base font-black">
                {isAr ? "السوق المصري (EGX)" : "Egyptian Market (EGX)"}
              </div>
              <p className="mt-1 text-xs font-medium text-zinc-700 dark:text-zinc-300 group-hover:text-black/85 leading-relaxed">
                {isAr
                  ? "البورصة المصرية · الأسهم والصفقات بالجنيه المصري (ج.م)"
                  : "Egyptian Exchange · Stocks & signals in Egyptian Pound (EGP)"}
              </p>
            </div>
            <div className="mt-4 inline-flex items-center gap-1.5 text-xs font-black">
              <span>{isAr ? "الدخول للسوق المصري" : "Enter EGX Market"}</span>
              <ArrowIcon className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5 rtl:group-hover:-translate-x-0.5" />
            </div>
          </button>

          {/* Saudi Card */}
          <button
            type="button"
            onClick={() => setMarket("tasi")}
            className="group text-start flex flex-col justify-between p-4 rounded-xl border-3 border-black dark:border-white bg-emerald-400/15 hover:bg-emerald-400 text-zinc-950 dark:text-white hover:text-black shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_0px_rgba(255,255,255,0.25)] hover:-translate-y-0.5 transition-all cursor-pointer"
          >
            <div>
              <div className="flex items-center justify-between gap-2 mb-3">
                <SaudiFlag className="w-9 h-6" />
                <div className="flex items-center gap-1.5">
                  <span className="px-2 py-0.5 rounded-md bg-black text-[#FFE600] border-2 border-black text-[10px] font-black uppercase tracking-wider">
                    BETA
                  </span>
                  <span className="px-2 py-0.5 rounded-md bg-emerald-400 text-black border-2 border-black text-[11px] font-black">
                    TASI
                  </span>
                </div>
              </div>
              <div className="text-base font-black">
                {isAr ? "السوق السعودي (تاسي TASI)" : "Saudi Market (TASI)"}
              </div>
              <p className="mt-1 text-xs font-medium text-zinc-700 dark:text-zinc-300 group-hover:text-black/85 leading-relaxed">
                {isAr
                  ? "السوق المالية السعودية (تداول) · الأسهم والصفقات بالريال السعودي (ر.س)"
                  : "Saudi Exchange (Tadawul) · Stocks & signals in Saudi Riyal (SAR)"}
              </p>
            </div>
            <div className="mt-4 inline-flex items-center gap-1.5 text-xs font-black">
              <span>{isAr ? "الدخول للسوق السعودي" : "Enter Saudi Market"}</span>
              <ArrowIcon className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5 rtl:group-hover:-translate-x-0.5" />
            </div>
          </button>
        </div>

        <p className="mt-4 pt-3 border-t border-zinc-200 dark:border-zinc-800 text-[11px] sm:text-xs text-zinc-600 dark:text-zinc-400 text-center leading-relaxed">
          {isAr
            ? "يمكنك التبديل بين السوقين في أي وقت من الشريط العلوي، وشات الذكاء الاصطناعي ARTORO مفتوح دائماً على السوقين معاً."
            : "You can switch between both markets anytime from the top bar, and ARTORO AI Chat is always open for both markets together."}
        </p>
      </div>
    </div>
  );
}
