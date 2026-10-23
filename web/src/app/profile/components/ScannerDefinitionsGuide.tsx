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
  CheckCircle2,
  ShieldCheck,
  Lock,
  Layers,
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
      subtitleAr: "انفجار أحجام التداول وتدفق السيولة المؤسسية في مسار صاعد مؤكد",
      subtitleEn: "Institutional liquidity injection and accumulation in confirmed uptrends",
      icon: Zap,
      colorBg: "bg-amber-400 text-black",
      badgeClass: "bg-amber-100 text-amber-900 border-amber-500 dark:bg-amber-950 dark:text-amber-200",
      borderAccent: "border-amber-400",
      formula: "Close ≥ EMA(20)  AND  rVol ≥ 2.2x  AND  Turnover ≥ 400K EGP  AND  Change% ≥ +1.5%  AND  RSI ∈ [35, 72]",
      formulaAr: "شرط اتجاه صاعد رئيسي (السعر أعلى من متوسط EMA 20) + انفجار سيولة نسبية (rVol ≥ 2.2x) + قيمة تداول لا تقل عن 400 ألف جنيه + صعود فعلي بنسبة +1.5% مع مؤشر RSI معتدل وغير متضخم.",
      explanationAr:
        "يرصد هذا الإسكانر التدفقات النقدية المؤسسية الحقيقية؛ حيث يشترط وجود تجميع بأحجام تداول تفوق المعدل بـ 120% على الأقل وقيمة تداول تتجاوز 400 ألف جنيه، مع ضرورة أن يكون السعر في اتجاه صاعد فوق متوسط 20 يوماً لضمان عدم الوقوع في مصائد التصريف والأسهم الهابطة.",
      explanationEn:
        "Tracks confirmed smart money inflows: requiring relative volume ≥ 2.2x, turnover ≥ 400K EGP, and price sustaining above EMA(20) to filter out fake spikes in downtrends.",
      tradingTipsAr: [
        "الهدف الربحي المقترح: +4.5% | وقف الخسارة الأولي: -3.0%.",
        "تأمين التعادل الذكي (Breakeven): بمجرد وصول السهم إلى ربح +2.5%، يتحول وقف الخسارة تلقائياً إلى سعر الدخول لضمان عدم تحول أي صفقة رابحة إلى خسارة.",
        "الدخول الأمثل مع اختراق قمة شمعة السيولة الانفجارية في أول 30 دقيقة من ظهور الإشارة مع متابعة عمق دفتر الأوامر."
      ],
      tradingTipsEn: [
        "Target: +4.5% | Initial Stop-Loss: -3.0%.",
        "Smart Breakeven Protection: Once the trade reaches +2.5% gain, the stop-loss automatically moves to entry price (0.0% risk).",
        "Optimal entry on breakout above the volume surge candle high with steady bid depth."
      ],
      scanIntervalAr: "فحص لحظي كل 5 دقائق طوال ساعات جلسة البورصة المصرية.",
    },
    {
      id: "breakout",
      titleAr: "ماسح الاختراقات الفنية وكسر القمم",
      titleEn: "Technical Breakouts & Highs",
      subtitleAr: "اختراق المقاومات العلوية للبولينجر باند وتجاوز القمم بزخم وسيولة مؤكدة",
      subtitleEn: "Bollinger Upper Band breakout clearing resistance with confirmed volume",
      icon: ArrowUpRight,
      colorBg: "bg-emerald-400 text-black",
      badgeClass: "bg-emerald-100 text-emerald-900 border-emerald-500 dark:bg-emerald-950 dark:text-emerald-200",
      borderAccent: "border-emerald-500",
      formula: "Close ≥ BB_Upper  AND  rVol ≥ 1.8x  AND  Turnover ≥ 500K EGP  AND  Change% ≥ +2.5%  AND  Close ≥ EMA(20)",
      formulaAr: "اختراق حقيقي للشريط العلوي لمؤشر بولينجر باند (BB Upper) مع سيولة قوية (rVol ≥ 1.8x) وقيمة تداول ≥ 500 ألف جنيه وارتفاع لا يقل عن +2.5% مع تأكيد المسار الصاعد فوق EMA(20).",
      explanationAr:
        "يعتبر اختراق القمم والشريط العلوي لمؤشر بولينجر باند إشارة كلاسيكية لبداية موجة اندفاع سعرية حادة. يضمن هذا الإسكانر استبعاد الاختراقات الوهمية (Fakeouts) عبر فرض شروط سيولة صارمة (500 ألف جنيه كحد أدنى) وزخم نسبي لا يقل عن 1.8 ضعف الطبيعي.",
      explanationEn:
        "Detects true bullish breakouts above the upper Bollinger Band with confirmed institutional turnover (≥ 500K EGP) to filter out deceptive fakeouts.",
      tradingTipsAr: [
        "الهدف الربحي المقترح: +6.0% | وقف الخسارة الأولي: -3.5%.",
        "تأمين التعادل الذكي (Breakeven): يرتفع وقف الخسارة إلى سعر الشراء فور وصول الربح إلى +2.5% لتأمين رأس المال.",
        "يفضل الشراء الفوري مع الإغلاق فوق المقاومة، أو الدخول مع إعادة الاختبار (Retest) إذا كان السوق في حالة تذبذب عام."
      ],
      tradingTipsEn: [
        "Target: +6.0% | Initial Stop-Loss: -3.5%.",
        "Smart Breakeven: Stop-loss automatically moves to breakeven at +2.5% gain.",
        "Buy breakout directly or on retest of the broken resistance level."
      ],
      scanIntervalAr: "فحص لحظي كل 5 دقائق طوال ساعات الجلسة.",
    },
    {
      id: "rsi_oversold",
      titleAr: "ماسح التشبع البيعي وصيد القيعان",
      titleEn: "RSI Oversold & Bottom Fishing",
      subtitleAr: "اقتناص الارتدادات السريعة للأسهم المتشبعة بيعياً مع حماية الهاوية السعرية",
      subtitleEn: "Precision bottom-fishing for deeply oversold stocks with cliff guard protection",
      icon: Target,
      colorBg: "bg-sky-400 text-black",
      badgeClass: "bg-sky-100 text-sky-900 border-sky-500 dark:bg-sky-950 dark:text-sky-200",
      borderAccent: "border-sky-500",
      formula: "RSI(14) ≤ 28.0  AND  Reversal Change% ≥ +1.0%  AND  Close ≥ EMA(20) × 0.85  AND  Turnover ≥ 250K EGP",
      formulaAr: "تشبع بيعي عميق وحقيقي (RSI ≤ 28) مع ظهور شمعة ارتداد خضراء مؤكدة (+1.0% على الأقل) وشرط أمان الهاوية (السعر لا يقل عن 85% من متوسط EMA 20 لمنع صيد السكاكين الساقطة).",
      explanationAr:
        "يحدث التشبع البيعي الحقيقي عندما يصل السهم لمرحلة استنزاف تام للبيع العاطفي. اشترطنا نزول RSI لما دون 28 مع بداية ارتداد سعري فعلي بنسبة 1%+، والأهم هو 'فلتر حماية الهاوية' الذي يستبعد الأسهم المنهارة كلياً التي تكسر متوسطاتها السعرية بعنف وتستمر في السقوط الحر.",
      explanationEn:
        "Catches strong technical bounces from deep oversold levels (RSI ≤ 28) with a confirmed green reversal tick (+1.0%) and a strict cliff guard to avoid falling knives.",
      tradingTipsAr: [
        "الهدف الربحي المقترح: +4.0% | وقف الخسارة الأولي الصارم: -2.8%.",
        "تأمين التعادل الذكي (Breakeven): يرتفع الوقف لسعر الدخول فورياً بمجرد لمس +2.5% ربح.",
        "هذه الاستراتيجية للمضاربة السريعة (Mean Reversion)؛ ينصح بجني الأرباح فور الوصول للهدف أو عودة RSI لمستوى 45-50."
      ],
      tradingTipsEn: [
        "Target: +4.0% | Strict Stop-Loss: -2.8%.",
        "Smart Breakeven: Stops trail to cost basis at +2.5% gain.",
        "Quick mean-reversion swing: take profits as RSI rebounds towards 45-50."
      ],
      scanIntervalAr: "فحص دوري كل 5 دقائق لحساب مستويات RSI بدقة.",
    },
    {
      id: "risk_rules",
      titleAr: "منظومة حماية رأس المال والتعادل الذكي",
      titleEn: "Capital Protection & Breakeven Guard",
      subtitleAr: "تأمين الأرباح التلقائي، سقف الصفقات المفتوحة، وفلاتر حماية المحفظة",
      subtitleEn: "Automated breakeven trails, portfolio exposure capping, and low-float traps exclusion",
      icon: ShieldCheck,
      colorBg: "bg-rose-500 text-white",
      badgeClass: "bg-rose-100 text-rose-900 border-rose-500 dark:bg-rose-950 dark:text-rose-200",
      borderAccent: "border-rose-500",
      formula: "Breakeven Stop at +2.5% Gain  |  Max Active Signals = 8  |  Min Turnover ≥ 400K EGP",
      formulaAr: "نقل الوقف لسعر الدخول فورياً عند +2.5% ربح، حد أقصى 8 صفقات مفتوحة متزامنة، وفلترة سيولة مؤسسية لمنع الأسهم الميتة.",
      explanationAr:
        "الهدف الأساسي للرادار ليس كثرة الصفقات بل استدامة نمو المحفظة وحماية رأس المال. تعتمد المنظومة على 4 حواجز دفاعية حديدية تمنع النزيف وتضمن أن أي صفقة حققت ربحاً مبدئياً لا تتحول أبداً إلى خسارة، مع عدم توريط المحفظة في عشرات الأسهم الضعيفة في نفس الوقت.",
      explanationEn:
        "Engineered for portfolio longevity and aggressive risk containment: automated breakeven stop-trail at +2.5%, maximum of 8 open positions, and institutional liquidity gating.",
      tradingTipsAr: [
        "وقف التعادل الذكي (Breakeven Stop): بمجرد أن يحقق السهم ربحاً يصل إلى +2.5%، يرتفع وقف الخسارة فورياً لسعر الشراء لتصبح مخاطرة الصفقة (0.0%).",
        "سقف الصفقات المفتوحة (Portfolio Cap): لا يسمح الرادار بفتح أكثر من 8 صفقات نشطة في نفس الوقت لمنع تكديس المخاطر وتشتيت رأس المال في فترات تقلب السوق.",
        "فلتر السيولة الإلزامي (Turnover Gate): استبعاد فوري لأي سهم يقل حجم تداوله عن 200,000 سهم أو قيمة تداوله عن 400,000 جنيه لحمايتك من الأسهم الميتة ومصائد المصيدة السعرية.",
        "فلتر الاتجاه الصارم (Trend Shield): اشتراط تواجد السعر فوق متوسط 20 يوم (EMA 20) لمنع شراء الأسهم الواقعة في مسار هابط رئيسي مهما كانت الإغراءات."
      ],
      tradingTipsEn: [
        "Breakeven Stop: Reaching +2.5% gain immediately adjusts stop-loss to entry price (0.0% capital risk).",
        "Portfolio Cap: Hard cap of 8 simultaneously open signals prevents overexposure and liquidity dilution.",
        "Turnover Gate: Mandatory minimum 200K volume and 400K EGP turnover keeps low-float traps away.",
        "Trend Shield: Mandatory Close ≥ EMA(20) prevents catching falling knives in established downtrends."
      ],
      scanIntervalAr: "مراقبة مستمرة كل ثانية لأوامر الوقف والأهداف.",
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

          {/* Institutional Guard Pillars Banner */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="border-2 border-black dark:border-white bg-emerald-500/10 dark:bg-emerald-950/40 p-3 flex items-center gap-3">
              <div className="h-8 w-8 bg-emerald-500 text-white font-black flex items-center justify-center shrink-0 border border-black shadow-[2px_2px_0px_rgba(0,0,0,1)]">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <div className="text-[11px] font-black uppercase text-emerald-800 dark:text-emerald-300">
                  {isAr ? "تأمين التعادل الذكي" : "Breakeven Stop Trail"}
                </div>
                <div className="text-[10px] font-bold text-zinc-600 dark:text-zinc-400">
                  {isAr ? "رفع الوقف لسعر الدخول فور صعود +2.5%" : "Auto trail to entry upon +2.5% gain"}
                </div>
              </div>
            </div>

            <div className="border-2 border-black dark:border-white bg-amber-500/10 dark:bg-amber-950/40 p-3 flex items-center gap-3">
              <div className="h-8 w-8 bg-amber-500 text-black font-black flex items-center justify-center shrink-0 border border-black shadow-[2px_2px_0px_rgba(0,0,0,1)]">
                <Layers className="w-5 h-5" />
              </div>
              <div>
                <div className="text-[11px] font-black uppercase text-amber-800 dark:text-amber-300">
                  {isAr ? "سقف صفقات المحفظة" : "Portfolio Exposure Cap"}
                </div>
                <div className="text-[10px] font-bold text-zinc-600 dark:text-zinc-400">
                  {isAr ? "حد أقصى 8 صفقات مفتوحة متزامنة" : "Max 8 concurrent open signals"}
                </div>
              </div>
            </div>

            <div className="border-2 border-black dark:border-white bg-blue-500/10 dark:bg-blue-950/40 p-3 flex items-center gap-3">
              <div className="h-8 w-8 bg-blue-500 text-white font-black flex items-center justify-center shrink-0 border border-black shadow-[2px_2px_0px_rgba(0,0,0,1)]">
                <Lock className="w-5 h-5" />
              </div>
              <div>
                <div className="text-[11px] font-black uppercase text-blue-800 dark:text-blue-300">
                  {isAr ? "حماية الاتجاه والسيولة" : "Trend & Liquidity Gate"}
                </div>
                <div className="text-[10px] font-bold text-zinc-600 dark:text-zinc-400">
                  {isAr ? "قيمة تداول ≥ 400K وسعر > EMA 20" : "Turnover ≥ 400K & Close > EMA20"}
                </div>
              </div>
            </div>
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
