"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  X,
  Sparkles,
  Zap,
  Bot,
  BellRing,
  ShieldCheck,
  TrendingUp,
  Target,
  ArrowRight,
  CheckCircle2,
  PlayCircle,
  HelpCircle,
  ExternalLink,
} from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAuth } from "@/contexts/AuthContext";

interface QuickProfitGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
  onStartTrial?: () => void;
  trialEligible?: boolean;
}

export default function QuickProfitGuideModal({
  isOpen,
  onClose,
  onStartTrial,
  trialEligible = true,
}: QuickProfitGuideModalProps) {
  const { language } = useLanguage();
  const { user } = useAuth();
  const router = useRouter();
  const isAr = language === "ar";
  const [activeStep, setActiveStep] = useState<number>(1);

  // Close on ESC
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const steps = [
    {
      step: 1,
      badge: isAr ? "الخطوة الأولى · التوقيت والسيولة" : "Step 1 · Timing & Flow",
      title: isAr ? "اقتنص السهم من الماسح اللحظي (Fast Scanner)" : "Spot Surging Stocks on Fast Scanner",
      icon: <Zap className="w-6 h-6 text-amber-500" />,
      color: "border-amber-500 bg-amber-500/10 text-amber-600 dark:text-amber-400",
      description: isAr
        ? "خلال جلسة التداول (10:00 ص إلى 2:30 م)، افتح صفحة الماسح الفني. الخوارزمية تمسح آلياً كافة أسهم البورصة المصرية وترصد الأسهم التي تخترق قمم 20 جلسة مصحوبة بانفجار في أحجام التداول (Volume Spike)."
        : "During market hours (10:00 AM - 2:30 PM), check the Fast Scanner. Algorithms scan all EGX stocks to catch 20-session breakouts with explosive volume.",
      proTips: [
        isAr ? "اختر الأسهم التي يتجاوز معدل سيولتها 1.5x متوسطها المعتاد." : "Focus on stocks with volume ratio > 1.5x normal average.",
        isAr ? "التزم بالأسهم المدرجة في قطاعات نشطة متصدرة للسيولة." : "Stick to stocks in active leading sectors.",
      ],
      actionLabel: isAr ? "معاينة الماسح اللحظي" : "Open Fast Scanner",
      actionHref: "/scanner/technical",
    },
    {
      step: 2,
      badge: isAr ? "الخطوة الثانية · التحقق الذكي" : "Step 2 · AI Validation",
      title: isAr ? "تأكيد الدعم والهدف مع شات الذكاء الاصطناعي" : "Verify Levels with AI Agentic Chat",
      icon: <Bot className="w-6 h-6 text-[#00FF66]" />,
      color: "border-[#00FF66] bg-[#00FF66]/10 text-emerald-700 dark:text-[#00FF66]",
      description: isAr
        ? "قبل تنفيذ أمر الشراء، اسأل شات البوت الذكي مباشرة: 'ما هو التحليل الفني ومناطق الدخول لسهم [الرمز]؟'. يحلل الذكاء الاصطناعي الشارت لحظياً ويحدد لك بدقة مناطق الأمان وأول مقاومة ومستوى وقف الخسارة الصارم."
        : "Before buying, ask the AI Chat: 'What are safe entry levels and stop-loss for [SYMBOL]?'. It evaluates support, resistance, and stop-loss instantly.",
      proTips: [
        isAr ? "اسأل البوت عن متوسط تكلفة شراء الداخليين (VWAP) للتأكد من عدم الشراء بقمة متضخمة." : "Ask about Insider VWAP to avoid buying at overextended peaks.",
        isAr ? "البوت يفهم اللهجة المصرية العامية ورموز وأسماء الشركات بالعربي أو الإنجليزي." : "AI understands Egyptian Arabic dialect and company names seamlessly.",
      ],
      actionLabel: isAr ? "تجربة شات الذكاء الاصطناعي" : "Try AI Chat",
      actionHref: "/chat",
    },
    {
      step: 3,
      badge: isAr ? "الخطوة الثالثة · حماية الأرباح" : "Step 3 · Profit Protection",
      title: isAr ? "تفعيل تنبيهات تليجرام والالتزام بوقف الخسارة" : "Activate Telegram Alerts & Strict Stops",
      icon: <BellRing className="w-6 h-6 text-purple-500" />,
      color: "border-purple-500 bg-purple-500/10 text-purple-600 dark:text-purple-400",
      description: isAr
        ? "لا داعي للجلوس مشدود الأعصاب أمام شاشات البورصة طوال 4 ساعات! اربط حسابك بتليجرام لتصلك تنبيهات الصفقات اللحظية ومستويات وقف التعادل (Breakeven) لحماية أرباحك من الانعكاس."
        : "No need to stare at market screens for 4 hours! Link Telegram to receive real-time breakout alerts and trailing breakeven stops directly on your mobile.",
      proTips: [
        isAr ? "الخوارزمية تطبق وقف خسارة أولي صارم (-4%) لمنع أي انهيار بمحفظتك." : "Strict initial -4% stop-loss prevents catastrophic portfolio drawdowns.",
        isAr ? "عند صعود السهم للهدف الأول، ارفع الوقف فوراً لسعر الدخول (وقف تعادل)." : "Raise stop to breakeven once stock hits Target 1.",
      ],
      actionLabel: isAr ? "ربط تليجرام الفوري" : "Link Telegram",
      actionHref: "/profile#telegram",
    },
  ];

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center p-3 sm:p-5 bg-black/80 backdrop-blur-md overflow-y-auto"
      onClick={onClose}
      dir={isAr ? "rtl" : "ltr"}
    >
      <div
        className="relative w-full max-w-2xl bg-white dark:bg-zinc-950 text-black dark:text-white border-4 border-black dark:border-white shadow-[10px_10px_0px_#000] dark:shadow-[10px_10px_0px_#fff] p-5 sm:p-7 my-auto transition-all"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 ltr:right-4 rtl:left-4 grid h-9 w-9 place-items-center bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white hover:bg-[#FF3366] hover:text-white transition-colors cursor-pointer z-10"
          aria-label={isAr ? "إغلاق" : "Close"}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Modal Header */}
        <div className="border-b-4 border-black dark:border-white pb-4 mb-5">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="px-2.5 py-0.5 text-xs font-black uppercase tracking-wider bg-[#FFE600] text-black border border-black shadow-[2px_2px_0px_#000]">
              {isAr ? "دليل الـ 60 ثانية" : "60-Second Profit Guide"}
            </span>
            <span className="text-xs font-bold text-zinc-500">
              {isAr ? "خطة التداول العملية" : "Actionable Trading Plan"}
            </span>
          </div>
          <h2 className="text-xl sm:text-2xl font-black text-black dark:text-white tracking-tight flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-amber-500 fill-amber-400" />
            {isAr ? "كيف تحقق أرباحاً في 3 خطوات مع EGX BOTS؟" : "How to Profit in 3 Steps with EGX BOTS"}
          </h2>
        </div>

        {/* Step Tabs Navigation */}
        <div className="grid grid-cols-3 gap-2 mb-6">
          {steps.map((s) => {
            const isActive = activeStep === s.step;
            return (
              <button
                key={s.step}
                type="button"
                onClick={() => setActiveStep(s.step)}
                className={`p-2.5 sm:p-3 text-center border-2 border-black transition-all cursor-pointer ${
                  isActive
                    ? "bg-black text-white dark:bg-white dark:text-black font-black shadow-[3px_3px_0px_#FFE600]"
                    : "bg-zinc-100 dark:bg-zinc-900 text-zinc-600 dark:text-zinc-400 font-bold hover:bg-zinc-200 dark:hover:bg-zinc-800"
                }`}
              >
                <div className="text-[10px] sm:text-xs uppercase tracking-wider mb-0.5 opacity-80">
                  {isAr ? `خطوة ${s.step}` : `Step ${s.step}`}
                </div>
                <div className="text-xs sm:text-sm font-black truncate">
                  {s.step === 1 ? (isAr ? "1. اقتنص السهم" : "1. Scanner") : s.step === 2 ? (isAr ? "2. استشر الشات" : "2. AI Chat") : (isAr ? "3. التزم بالوقف" : "3. Stops & Alerts")}
                </div>
              </button>
            );
          })}
        </div>

        {/* Active Step Content Card */}
        {(() => {
          const current = steps.find((s) => s.step === activeStep) || steps[0];
          return (
            <div className="p-4 sm:p-5 border-3 border-black dark:border-white/30 bg-zinc-50 dark:bg-zinc-900/90 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] space-y-4 mb-6">
              <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-xl border-2 flex items-center justify-center shrink-0 ${current.color}`}>
                  {current.icon}
                </div>
                <div>
                  <span className="text-[11px] font-black uppercase text-zinc-500 block">
                    {current.badge}
                  </span>
                  <h3 className="text-base sm:text-lg font-black text-black dark:text-white leading-tight">
                    {current.title}
                  </h3>
                </div>
              </div>

              <p className="text-xs sm:text-sm font-medium text-zinc-800 dark:text-zinc-200 leading-relaxed">
                {current.description}
              </p>

              <div className="space-y-2 border-t-2 border-black/10 dark:border-white/10 pt-3">
                <span className="text-[11px] font-black text-amber-600 dark:text-amber-400 uppercase tracking-wider block">
                  {isAr ? "💡 نصائح احترافية للاستفادة القصوى:" : "💡 Pro Tips:"}
                </span>
                <ul className="space-y-1.5">
                  {current.proTips.map((tip, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-xs font-bold text-zinc-700 dark:text-zinc-300">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                      <span>{tip}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="pt-2 flex justify-end">
                <Link
                  href={current.actionHref}
                  onClick={onClose}
                  className="inline-flex items-center gap-1.5 text-xs font-black text-black dark:text-white hover:text-amber-500 underline underline-offset-4"
                >
                  <span>{current.actionLabel}</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          );
        })()}

        {/* Footer Actions */}
        <div className="pt-2 border-t-2 border-black/10 dark:border-white/10 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="text-xs font-bold text-zinc-600 dark:text-zinc-400 text-center sm:text-right">
            {isAr ? "جاهز لتطبيق المعادلة؟ جرب باقة PRO مجاناً 3 أيام" : "Ready to profit? Try Pro free for 3 days"}
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            {trialEligible && onStartTrial ? (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onStartTrial();
                }}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-[#FFE600] hover:bg-[#ffea33] text-black font-black text-xs uppercase tracking-wider border-2 border-black shadow-[2px_2px_0px_#000] cursor-pointer flex items-center justify-center gap-1.5 transition-all"
              >
                <Sparkles className="w-4 h-4" />
                <span>{isAr ? "ابدأ التجربة المجانية 3 أيام ⚡" : "Start 3-Day Free Trial ⚡"}</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  router.push("/pricing");
                }}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-black text-xs uppercase tracking-wider border-2 border-black shadow-[2px_2px_0px_#000] cursor-pointer flex items-center justify-center gap-1.5 transition-all"
              >
                <span>{isAr ? "استكشف باقات PRO 💎" : "Explore Pro Plans 💎"}</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
