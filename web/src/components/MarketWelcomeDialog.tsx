"use client";

import React, { useEffect, useState, useCallback } from "react";
import { X, ArrowLeft, ArrowRight, Sparkles } from "lucide-react";
import { useMarket, type MarketMode } from "@/contexts/MarketContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { EgyptFlag, SaudiFlag, UaeFlag, QatarFlag } from "@/components/MarketFlag";

interface MarketCardOption {
  id: MarketMode;
  badge: string;
  betaBadge?: boolean;
  flag: React.ReactNode;
  titleAr: string;
  titleEn: string;
  descAr: string;
  descEn: string;
  ctaAr: string;
  ctaEn: string;
  cardTone: string;
  badgeTone: string;
}

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

  const marketOptions: MarketCardOption[] = [
    {
      id: "egx",
      badge: "EGX",
      flag: <EgyptFlag className="w-9 h-6" />,
      titleAr: "السوق المصري (EGX)",
      titleEn: "Egyptian Market (EGX)",
      descAr: "البورصة المصرية · الأسهم والإشارات والصفقات بالجنيه المصري (ج.م)",
      descEn: "Egyptian Exchange · Stocks, signals & disclosures in EGP",
      ctaAr: "الدخول للسوق المصري",
      ctaEn: "Enter EGX Market",
      cardTone: "bg-[#FFE600]/15 hover:bg-[#FFE600]",
      badgeTone: "bg-[#FFE600] text-black",
    },
    {
      id: "tasi",
      badge: "TASI",
      betaBadge: true,
      flag: <SaudiFlag className="w-9 h-6" />,
      titleAr: "السوق السعودي (تاسي TASI)",
      titleEn: "Saudi Market (TASI)",
      descAr: "السوق المالية السعودية (تداول) · الأسهم والإشارات بالريال السعودي (ر.س)",
      descEn: "Saudi Exchange (Tadawul) · Stocks & signals in SAR",
      ctaAr: "الدخول للسوق السعودي",
      ctaEn: "Enter Saudi Market",
      cardTone: "bg-emerald-400/15 hover:bg-emerald-400",
      badgeTone: "bg-emerald-400 text-black",
    },
    {
      id: "uae",
      badge: "UAE",
      flag: <UaeFlag className="w-9 h-6" />,
      titleAr: "سوق الإمارات (دبي وأبوظبي)",
      titleEn: "UAE Markets (DFM & ADX)",
      descAr: "سوق دبي المالي وأبوظبي · شات بوت AI وتحليل فني بالدرهم الإماراتي (د.إ)",
      descEn: "Dubai (DFM) & Abu Dhabi (ADX) · AI Chat & technical analysis in AED",
      ctaAr: "الدخول لسوق الإمارات",
      ctaEn: "Enter UAE Markets",
      cardTone: "bg-sky-400/15 hover:bg-sky-400",
      badgeTone: "bg-sky-400 text-black",
    },
    {
      id: "qatar",
      badge: "QSE",
      flag: <QatarFlag className="w-9 h-6" />,
      titleAr: "بورصة قطر (QSE)",
      titleEn: "Qatar Exchange (QSE)",
      descAr: "بورصة قطر · شات بوت AI وتحليل فني لجميع الأسهم بالريال القطري (ر.ق)",
      descEn: "Qatar Stock Exchange · AI Chat & technical analysis in QAR",
      ctaAr: "الدخول لبورصة قطر",
      ctaEn: "Enter Qatar Market",
      cardTone: "bg-rose-400/15 hover:bg-rose-400",
      badgeTone: "bg-rose-400 text-black",
    },
  ];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="market-welcome-title"
      dir={isAr ? "rtl" : "ltr"}
      className="fixed inset-0 z-[140] flex items-center justify-center p-4 bg-black/65 backdrop-blur-sm animate-in fade-in duration-200 overflow-y-auto"
      onClick={handleDismiss}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-2xl rounded-2xl border-3 border-black dark:border-white bg-white dark:bg-zinc-950 text-zinc-950 dark:text-white shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.25)] p-5 sm:p-7 my-auto"
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
              ? "حدد سوق البداية لعرض الأسهم والأدوات بالعملة والمؤشر المناسبين."
              : "Pick your starting market to display stocks and tools in the matching currency and index."}
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
          {marketOptions.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => setMarket(opt.id)}
              className={`group text-start flex flex-col justify-between p-4 rounded-xl border-3 border-black dark:border-white ${opt.cardTone} text-zinc-950 dark:text-white hover:text-black shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_0px_rgba(255,255,255,0.25)] hover:-translate-y-0.5 transition-all cursor-pointer`}
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-2.5">
                  {opt.flag}
                  <div className="flex items-center gap-1.5">
                    {opt.betaBadge && (
                      <span className="px-2 py-0.5 rounded-md bg-black text-[#FFE600] border-2 border-black text-[10px] font-black uppercase tracking-wider">
                        BETA
                      </span>
                    )}
                    <span className={`px-2 py-0.5 rounded-md border-2 border-black text-[11px] font-black ${opt.badgeTone}`}>
                      {opt.badge}
                    </span>
                  </div>
                </div>
                <div className="text-base font-black">
                  {isAr ? opt.titleAr : opt.titleEn}
                </div>
                <p className="mt-1 text-xs font-medium text-zinc-700 dark:text-zinc-300 group-hover:text-black/85 leading-relaxed">
                  {isAr ? opt.descAr : opt.descEn}
                </p>
              </div>
              <div className="mt-3.5 inline-flex items-center gap-1.5 text-xs font-black">
                <span>{isAr ? opt.ctaAr : opt.ctaEn}</span>
                <ArrowIcon className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5 rtl:group-hover:-translate-x-0.5" />
              </div>
            </button>
          ))}
        </div>

        <p className="mt-4 pt-3 border-t border-zinc-200 dark:border-zinc-800 text-[11px] sm:text-xs text-zinc-600 dark:text-zinc-400 text-center leading-relaxed">
          {isAr
            ? "يمكنك التبديل بين الأسواق الأربعة في أي وقت من القائمة العلوية، وشات الذكاء الاصطناعي ARTORO مفتوح دائماً لجميع الأسواق والذهب والفضة معاً."
            : "Switch between all 4 markets anytime from the top dropdown, and ARTORO AI Chat always covers all markets plus Gold & Silver."}
        </p>
      </div>
    </div>
  );
}
