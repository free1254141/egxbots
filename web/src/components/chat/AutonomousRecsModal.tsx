"use client";

import React, { useEffect } from "react";
import { X, Sparkles, AlertTriangle, Check } from "lucide-react";

interface AutonomousRecsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  isAr?: boolean;
}

export function AutonomousRecsModal({
  isOpen,
  onClose,
  onConfirm,
  isAr = true,
}: AutonomousRecsModalProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="autonomous-recs-title"
      className="fixed inset-0 z-[100] flex items-center justify-center p-3 sm:p-4 bg-black/60 dark:bg-black/80 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl border-2 border-amber-500/40 bg-white dark:bg-zinc-950 p-5 sm:p-6 text-zinc-900 dark:text-white shadow-2xl transition-all"
        onClick={(e) => e.stopPropagation()}
        dir={isAr ? "rtl" : "ltr"}
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 ltr:right-4 rtl:left-4 grid h-8 w-8 place-items-center rounded-xl border border-zinc-200 dark:border-white/10 bg-zinc-100 dark:bg-white/5 text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white transition active:scale-95 cursor-pointer"
          aria-label={isAr ? "إغلاق" : "Close"}
        >
          <X className="h-4 w-4" />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-amber-500/20 to-emerald-500/20 border border-amber-500/30 text-amber-500 dark:text-amber-400 shadow-inner shrink-0">
            <Sparkles className="h-6 w-6 text-amber-500 dark:text-amber-400" />
          </div>
          <div>
            <h3 id="autonomous-recs-title" className="text-base sm:text-lg font-black text-zinc-900 dark:text-white flex items-center gap-2 flex-wrap">
              <span>{isAr ? "وضع التوصيات الحرة المستقلة" : "AI Autonomous Recommendations"}</span>
              <span className="text-[10px] font-black px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400 border border-emerald-500/30">
                AI Autonomous Mode
              </span>
            </h3>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
              {isAr
                ? "تمكين الذكاء الاصطناعي من تحليل السوق واقتراح فرص فنية برؤيته المستقلة"
                : "Empower AI to analyze market data and suggest trading setups with independent digital insights"}
            </p>
          </div>
        </div>

        {/* Disclaimer Warning Card */}
        <div className="rounded-xl border border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 p-3.5 mb-4 space-y-1.5">
          <div className="flex items-center gap-2 text-amber-800 dark:text-amber-300 font-bold text-xs sm:text-sm">
            <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0" />
            <span>{isAr ? "إخلاء مسؤولية استثمارية وقانونية كاملة" : "Full Investment & Legal Disclaimer"}</span>
          </div>
          <p className="text-[11px] sm:text-xs text-amber-900/90 dark:text-amber-200/90 leading-relaxed">
            {isAr
              ? "يُرجى قراءة الشروط التالية بعناية قبل تفعيل هذا الوضع. التفعيل يعني موافقتك الصريحة والكاملة عليها."
              : "Please review the following terms carefully before enabling this mode. Activation indicates your explicit agreement."}
          </p>
        </div>

        {/* Terms Breakdown */}
        <div className="space-y-3 mb-6 text-xs text-zinc-700 dark:text-zinc-300 leading-relaxed">
          <div className="flex items-start gap-2.5">
            <div className="grid h-5 w-5 place-items-center rounded-md bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5 font-bold text-[10px]">
              1
            </div>
            <div>
              <strong className="text-zinc-900 dark:text-white">
                {isAr ? "رؤية رقمية استرشادية مستقلة:" : "Independent Digital Guidance:"}
              </strong>
              <p className="text-zinc-500 dark:text-zinc-400 text-[11px] mt-0.5">
                {isAr
                  ? "يقوم المساعد الذكي ARTORO بتحليل بيانات ومؤشرات المنصة (الأسعار، أحجام التداول، مناطق التجميع، والسيولة) لاقتراح فرص وتوصيات تداول فنية برؤيته الرقمية المستقلة دون التقيد بالإشارات الرسمية المفتوحة."
                  : "ARTORO AI analyzes platform data and market indicators (prices, volume, accumulation zones, liquidity) to suggest technical opportunities based on its independent perspective without being restricted to official open signals."}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2.5">
            <div className="grid h-5 w-5 place-items-center rounded-md bg-amber-500/20 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5 font-bold text-[10px]">
              2
            </div>
            <div>
              <strong className="text-zinc-900 dark:text-white">
                {isAr ? "أغراض التعليم والمتابعة الفنية:" : "Educational & Research Purpose:"}
              </strong>
              <p className="text-zinc-500 dark:text-zinc-400 text-[11px] mt-0.5">
                {isAr
                  ? "جميع المخرجات والأفكار ونقاط الدخول والمستهدفات ووقف الخسارة هي نماذج استرشادية لأغراض الدراسة والبحث، وليست نصائح مالية أو دعوة للشراء أو البيع."
                  : "All outputs, ideas, proposed entries, targets, and stop-loss levels are technical models for research and study, not financial advice or solicitation to buy or sell."}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2.5">
            <div className="grid h-5 w-5 place-items-center rounded-md bg-rose-500/20 text-rose-600 dark:text-rose-400 shrink-0 mt-0.5 font-bold text-[10px]">
              3
            </div>
            <div>
              <strong className="text-zinc-900 dark:text-white">
                {isAr ? "المسؤولية الكاملة تقع على عاتقك:" : "100% User Liability:"}
              </strong>
              <p className="text-zinc-500 dark:text-zinc-400 text-[11px] mt-0.5">
                {isAr
                  ? "منصة StokScan وإدارتها ومطوروها يخلون مسؤوليتهم القانونية والمالية تماماً عن أي قرارات أو صفقات أو خسائر ناتجة عن استخدام هذه التوصيات، وقرارك الاستثماري يقع على مسؤوليتك الشخصية بالكامل."
                  : "StokScan, its management, and developers are completely disclaimed of any financial or legal liability for any decisions, trades, or losses resulting from these recommendations. Your investment decisions remain entirely your personal responsibility."}
              </p>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-col sm:flex-row items-center gap-2 pt-2 border-t border-zinc-200 dark:border-white/10">
          <button
            type="button"
            onClick={() => {
              onConfirm();
              onClose();
            }}
            className="flex items-center justify-center gap-2 w-full sm:flex-1 py-2.5 px-4 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-white font-extrabold text-xs sm:text-sm shadow-md transition-all active:scale-95 cursor-pointer"
          >
            <Check className="h-4 w-4" />
            <span>{isAr ? "أوافق وأتحمل المسؤولية — تفعيل الوضع" : "I Agree & Accept Responsibility — Enable"}</span>
          </button>
          <button
            type="button"
            onClick={onClose}
            className="flex items-center justify-center w-full sm:w-auto py-2.5 px-4 rounded-xl bg-zinc-100 hover:bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700 font-bold text-xs sm:text-sm transition-all active:scale-95 cursor-pointer border border-zinc-200 dark:border-transparent"
          >
            <span>{isAr ? "إلغاء" : "Cancel"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
