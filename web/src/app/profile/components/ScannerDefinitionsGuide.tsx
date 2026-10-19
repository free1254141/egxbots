"use client";

import React, { useState } from "react";
import {
  Zap,
  ArrowUpRight,
  Target,
  Newspaper,
  BookOpen,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
  Clock,
  Sparkles,
  HelpCircle,
  ExternalLink,
  Sliders,
  CheckCircle2
} from "lucide-react";

interface ScannerDefinitionsGuideProps {
  isAr?: boolean;
}

export default function ScannerDefinitionsGuide({ isAr = true }: ScannerDefinitionsGuideProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<string>("volume_surge");

  const definitions = [
    {
      id: "volume_surge",
      titleAr: "رادار السيولة الذكية والتجميع",
      titleEn: "Smart Money & Volume Surge",
      subtitleAr: "انفجار أحجام التداول وتدفق السيولة المؤسسية غير المعتادة",
      subtitleEn: "Unusual institutional liquidity injection and accumulation",
      icon: Zap,
      colorBg: "bg-amber-400 text-black",
      badgeClass: "bg-amber-100 text-amber-900 border-amber-500 dark:bg-amber-950 dark:text-amber-200",
      borderAccent: "border-amber-400",
      formula: "rVol = Volume / SMA(Volume, 20) ≥ 2.5x  AND  Change% ≥ 0.0%",
      formulaAr: "مضاعف السيولة النسبية (rVol) أكبر من أو يساوي 2.5 ضعف متوسط 20 جلسة مع ثبات أو صعود في السعر.",
      explanationAr:
        "يرصد هذا الإسكانر الأسهم التي يدخلها صانع السوق أو مؤسسات مالية بأحجام تداول ضخمة تفوق المعدل الطبيعي بـ 150% إلى 300% في وقت مبكر من الجلسة. عندما يرتفع حجم التداول دون هبوط في السعر، فهذا يعني وجود امتصاص وتجميع للكميات المعروضة تمهيداً لحركة صاعدة.",
      explanationEn:
        "Tracks stocks experiencing massive buying volume 2.5x higher than the 20-day moving average, signaling smart money accumulation before the price takes off.",
      tradingTipsAr: [
        "راقب أول 30 إلى 60 دقيقة من ظهور الإشارة للتأكد من استمرار تدفق عروض الشراء في دفتر الأوامر (Market Depth).",
        "يكون الدخول الأمثل مع اختراق السهم لأعلى سعر حققته شمعة السيولة الانفجارية.",
        "وقف الخسارة المثالي: كسر قاع الشمعة التي ظهر فيها انفجار السيولة مع إغلاق نصف ساعة."
      ],
      tradingTipsEn: [
        "Monitor order book depth in the first 30-60 mins to confirm steady bid pressure.",
        "Best entry is on a break above the volume candle's high.",
        "Stop-loss: Under the low of the surge candle."
      ],
      scanIntervalAr: "فحص لحظي كل 5 دقائق طوال ساعات جلسة البورصة المصرية.",
    },
    {
      id: "breakout",
      titleAr: "ماسح الاختراقات الفنية وكسر القمم",
      titleEn: "Technical Breakouts & Highs",
      subtitleAr: "تجاوز المقاومات التاريخية وقمم 20 جلسة بزخم سيولة مؤكد",
      subtitleEn: "Clearing 20-day high resistance with confirming trading volume",
      icon: ArrowUpRight,
      colorBg: "bg-emerald-400 text-black",
      badgeClass: "bg-emerald-100 text-emerald-900 border-emerald-500 dark:bg-emerald-950 dark:text-emerald-200",
      borderAccent: "border-emerald-500",
      formula: "Close > High(20)  AND  Close ≥ (High × 0.98)  AND  rVol ≥ 1.5x",
      formulaAr: "سعر الإغلاق يتجاوز أعلى قمة خلال 20 جلسة تداول سابقة، والإغلاق بالقرب من أعلى نقطة في الشمعة مع حجم تداول لا يقل عن 1.5x.",
      explanationAr:
        "يعتبر كسر القمم والمقاومات الفنية الرئيسية من أقوى الإشارات الكلاسيكية في التحليل الفني. يضمن الإسكانر عدم الوقوع في فخ الاختراق الوهمي (Fakeout) باشتراط تأكيد السيولة ($rVol \ge 1.5$) وإغلاق السعر قرب أعلى مستوى يومي.",
      explanationEn:
        "Detects true bullish breakouts clearing 20-day resistance levels with confirmed volume to filter out fake breakouts.",
      tradingTipsAr: [
        "شراء الاختراق المباشر للمضاربين السريعين، أو انتظار اختبار المقاومة المخترقة بعد تحولها لدعم (Retest).",
        "تأكد من عدم وجود مقاومات عنيفة قريبة على الفاصل الزمني الأسبوعي (Weekly).",
        "وقف الخسارة: الإغلاق العكسي أسفل خط المقاومة المخترقة."
      ],
      tradingTipsEn: [
        "Aggressive entry at breakout trigger, or conservative entry on retest of broken resistance.",
        "Ensure no major weekly resistances are directly overhead.",
        "Stop-loss: Daily close back below the broken resistance level."
      ],
      scanIntervalAr: "فحص لحظي كل 5 دقائق طوال ساعات الجلسة.",
    },
    {
      id: "rsi_oversold",
      titleAr: "ماسح التشبع البيعي وصيد القيعان",
      titleEn: "RSI Oversold & Bottom Fishing",
      subtitleAr: "اقتناص الأسهم التي بالغت في الهبوط عند مستويات ارتداد قوية",
      subtitleEn: "Spotting deeply oversold stocks hitting historical support zones",
      icon: Target,
      colorBg: "bg-sky-400 text-black",
      badgeClass: "bg-sky-100 text-sky-900 border-sky-500 dark:bg-sky-950 dark:text-sky-200",
      borderAccent: "border-sky-500",
      formula: "RSI(14) ≤ 30.0  AND  Price near Support",
      formulaAr: "مؤشر القوة النسبية RSI لفترة 14 شمعة أقل من أو يساوي 30 نقطة، مع تواجد السعر قرب دعوم تاريخية.",
      explanationAr:
        "يحدث التشبع البيعي عندما تسيطر موجة خوف أو بيع عاطفي مفرط على السهم. وصول مؤشر RSI إلى ما دون 30 نقطة يعكس استنزاف قوى البائعين واقتراب حدوث ارتداد فني سريع (Mean Reversion) نحو متوسطات السعر الطبيعية.",
      explanationEn:
        "Identifies heavily oversold stocks where selling exhaustion is reached, preparing for a strong mean-reversion technical bounce.",
      tradingTipsAr: [
        "لا تدخل بمجرد ملامسة RSI للرقم 30؛ انتظر ظهور أول شمعة خضراء انعكاسية (مطرقة Hammer أو ابتلاع شرائي Engulfing).",
        "قسّم الدخول على دفعتين؛ دفعة عند بداية الانعكاس ودفعة ثانية بعد تأكيد كسر خط اتجاه هابط فرعي.",
        "الأهداف الأولية: الوصول لمستوى RSI = 50 أو متوسط الحركة 20 يوم (SMA20)."
      ],
      tradingTipsEn: [
        "Do not enter blindly; wait for a confirmed bullish reversal candle (Hammer or Engulfing).",
        "Scale in with 2 tranches: first upon reversal signal, second upon crossing RSI 40.",
        "Primary targets: SMA(20) or RSI returning to 50 midpoint."
      ],
      scanIntervalAr: "فحص دوري كل 5 دقائق لحساب مستويات RSI بدقة.",
    },
    {
      id: "disclosures",
      titleAr: "رادار الإفصاحات الرسمية وأخبار الشركات",
      titleEn: "Corporate & Official Disclosures",
      subtitleAr: "المراقبة اللحظية لبيانات البورصة، قرارات مجالس الإدارة، والأرباح",
      subtitleEn: "Real-time feed of official EGX corporate disclosures, dividends, and earnings",
      icon: Newspaper,
      colorBg: "bg-purple-400 text-black",
      badgeClass: "bg-purple-100 text-purple-900 border-purple-500 dark:bg-purple-950 dark:text-purple-200",
      borderAccent: "border-purple-500",
      formula: "Direct Live Sync with EGX Disclosure Engine",
      formulaAr: "ربط آلي مباشر مع محرك إفصاحات البورصة المصرية وتصفية البيانات الجوهرية.",
      explanationAr:
        "الأخبار الجوهرية هي المحرك الأساسي للقفزات السعرية في البورصة. يرصد هذا الرادار تلقائياً كافة إعلانات الشركات: توزيع الكوبونات النقدية، أسهم مجانية، عروض الشراء والاستحواذ، القوائم المالية، وقرارات الجمعيات العمومية لحظة نشرها رسمياً.",
      explanationEn:
        "Direct algorithmic tracking of all market-moving disclosures: dividends, M&A, earnings reports, and board decisions.",
      tradingTipsAr: [
        "اربط الإفصاح دائماً بالرسم البياني؛ إذا كان السهم متجمعاً مسبقاً فالخبر سيعطي انطلاقة قوية.",
        "احذر من 'البيع على الخبر' (Buy the rumor, sell the news) إذا كان السهم قد صعد صعوداً صاروخياً قبل صدور الإفصاح.",
        "إفصاحات شراء أسهم الخزينة أو دخول مستثمر استراتيجي غالباً ما تشكل قيعان دعم قوية للسهم."
      ],
      tradingTipsEn: [
        "Cross-reference the disclosure with chart patterns to spot pre-accumulated movers.",
        "Beware of 'sell the news' reactions if the stock already rallied heavily into the release.",
        "Treasury share buybacks and strategic acquisitions typically form firm support floors."
      ],
      scanIntervalAr: "مزامنة لحظية مباشرة مع منصة إفصاحات البورصة.",
    },
  ];

  const currentDef = definitions.find((d) => d.id === activeTab) || definitions[0];
  const Icon = currentDef.icon;

  return (
    <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_rgba(255,255,255,1)]" dir={isAr ? "rtl" : "ltr"}>
      {/* ── Toggle Header ── */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full p-5 sm:p-6 bg-zinc-50 dark:bg-zinc-800/80 hover:bg-zinc-100 dark:hover:bg-zinc-800 flex items-center justify-between text-right transition-all group"
      >
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 border-2 border-black dark:border-white bg-[#FFE600] text-black flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] shrink-0">
            <BookOpen className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-lg sm:text-xl font-black text-black dark:text-white uppercase tracking-tight">
                {isAr ? "دليل ومعايير عمل رادار الإسكانرات" : "Scanner Technical Guide & Formulas"}
              </h4>
              <span className="border border-black dark:border-white bg-black dark:bg-white text-white dark:text-black text-[10px] font-mono font-black px-2 py-0.5 uppercase tracking-widest hidden sm:inline-block">
                DOCS
              </span>
            </div>
            <p className="text-xs font-bold text-zinc-600 dark:text-zinc-400 mt-1">
              {isAr
                ? "تعرف على شروط الاقتناص الفني، المعادلات الرياضية، وكيفية الاستفادة من إشارات كل نوع إسكانر."
                : "Learn trigger parameters, mathematical formulas, and optimal execution strategies for every scanner."}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs font-mono font-black text-black dark:text-white hidden sm:inline">
            {isOpen ? (isAr ? "إخفاء الدليل" : "Hide Guide") : (isAr ? "فتح الدليل والتفاصيل" : "View Formulas")}
          </span>
          <div className="h-8 w-8 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)]">
            {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        </div>
      </button>

      {/* ── Expandable Body ── */}
      {isOpen && (
        <div className="border-t-4 border-black dark:border-white p-5 sm:p-7 space-y-6 bg-zinc-50 dark:bg-zinc-950 animate-in fade-in slide-in-from-top-2 duration-200">
          {/* Scanner Tabs */}
          <div className="flex flex-wrap gap-2.5 border-b-2 border-black dark:border-white pb-4">
            {definitions.map((def) => {
              const isActive = activeTab === def.id;
              const DefIcon = def.icon;
              return (
                <button
                  key={def.id}
                  type="button"
                  onClick={() => setActiveTab(def.id)}
                  className={`h-10 px-4 border-2 sm:border-4 border-black dark:border-white font-black text-xs uppercase tracking-wide flex items-center gap-2 shadow-[2px_2px_0px_rgba(0,0,0,1)] transition-all ${
                    isActive
                      ? def.colorBg
                      : "bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                  }`}
                >
                  <DefIcon className="w-4 h-4" />
                  <span>{isAr ? def.titleAr : def.titleEn}</span>
                </button>
              );
            })}
          </div>

          {/* Active Scanner Detailed Card */}
          <div className={`border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-5 sm:p-7 shadow-[5px_5px_0px_rgba(0,0,0,1)] space-y-6`}>
            {/* Top Info Banner */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-black dark:border-white pb-5">
              <div className="flex items-center gap-3">
                <div className={`h-12 w-12 border-2 border-black ${currentDef.colorBg} flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)] shrink-0`}>
                  <Icon className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-xl font-black text-black dark:text-white uppercase tracking-tight">
                    {isAr ? currentDef.titleAr : currentDef.titleEn}
                  </h3>
                  <p className="text-xs font-bold text-zinc-500 mt-0.5">
                    {isAr ? currentDef.subtitleAr : currentDef.subtitleEn}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 text-xs font-mono font-black">
                <span className="flex items-center gap-1.5 bg-zinc-100 dark:bg-zinc-800 border-2 border-black dark:border-white px-3 py-1 text-zinc-800 dark:text-zinc-200">
                  <Clock className="w-3.5 h-3.5 text-amber-500" />
                  {isAr ? "فحص دوري كل 5 دقائق" : "Scans every 5 mins"}
                </span>
              </div>
            </div>

            {/* Grid Breakdown: Formula & Explanation */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {/* Formula & Criteria Card */}
              <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800/60 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-black uppercase text-zinc-500 flex items-center gap-1.5">
                    <Sliders className="w-3.5 h-3.5 text-indigo-500" />
                    {isAr ? "معادلة وشروط الرصد الفني" : "Trigger Criteria & Formula"}
                  </span>
                  <span className="text-[10px] font-mono font-black bg-black text-[#FFE600] px-2 py-0.5">
                    ALGO CRITERIA
                  </span>
                </div>
                <div className="font-mono font-black text-xs sm:text-sm bg-black text-emerald-400 p-3 border-2 border-black tracking-wide leading-relaxed">
                  {currentDef.formula}
                </div>
                <p className="text-xs font-bold text-zinc-700 dark:text-zinc-300 leading-relaxed">
                  {isAr ? currentDef.formulaAr : currentDef.formula}
                </p>
              </div>

              {/* Technical Overview & Rationale */}
              <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800/60 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-black uppercase text-zinc-500 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                    {isAr ? "الهدف والدلالة السوقية" : "Market Mechanics & Rationale"}
                  </span>
                  <span className="text-[10px] font-mono font-black bg-indigo-100 text-indigo-900 border border-indigo-500 px-2 py-0.5">
                    ANALYSIS
                  </span>
                </div>
                <p className="text-xs sm:text-sm font-bold text-zinc-800 dark:text-zinc-200 leading-relaxed">
                  {isAr ? currentDef.explanationAr : currentDef.explanationEn}
                </p>
              </div>
            </div>

            {/* Actionable Strategy & Trading Tips */}
            <div className="border-2 border-black dark:border-white bg-[#FFE600]/10 dark:bg-zinc-800 p-5 space-y-3">
              <span className="text-xs font-black uppercase text-black dark:text-white flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                {isAr ? "إرشادات واستراتيجية التداول على هذه الإشارة:" : "Actionable Trading Playbook:"}
              </span>
              <ul className="space-y-2 text-xs font-bold text-zinc-800 dark:text-zinc-200">
                {(isAr ? currentDef.tradingTipsAr : currentDef.tradingTipsEn).map((tip, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="h-5 w-5 bg-black text-white dark:bg-white dark:text-black font-mono font-black text-[10px] flex items-center justify-center shrink-0 border border-black mt-0.5">
                      {idx + 1}
                    </span>
                    <span className="leading-relaxed">{tip}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Risk Disclaimer */}
            <div className="border-2 border-black bg-rose-50 dark:bg-rose-950/40 p-3 flex items-center gap-2 text-xs font-bold text-rose-800 dark:text-rose-300">
              <ShieldAlert className="w-4 h-4 shrink-0 text-rose-600" />
              <span>
                {isAr
                  ? "تنبيه المخاطر: إشارات الإسكانر تمثل أدوات كشف وتنبيه آلي لمساعدتك في اتخاذ القرار، وليست توصيات شراء أو بيع مباشرة. التزم دائماً بإدارة رأس المال وتحديد أمر وقف الخسارة قبل الدخول."
                  : "Risk Disclaimer: Scanner signals are automated intelligence tools designed to assist decision-making, not financial advice. Always adhere to strict risk management."}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
