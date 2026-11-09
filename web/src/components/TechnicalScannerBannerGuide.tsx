"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Activity,
  Flame,
  Zap,
  ShieldCheck,
  ShieldAlert,
  Target,
  TrendingUp,
  TrendingDown,
  Layers,
  Info,
  ChevronDown,
  ChevronUp,
  Sparkles,
  LineChart,
  Crown,
  Scale,
  Crosshair,
  BarChart3,
  AlertTriangle,
} from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAuth } from "@/contexts/AuthContext";

export default function TechnicalScannerBannerGuide() {
  const { language } = useLanguage();
  const { user } = useAuth();
  const isAr = language === "ar";
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="px-3 sm:px-6 py-4 bg-[#0c0d12]" dir={isAr ? "rtl" : "ltr"}>
      {/* ── Outer Neo-Brutalist Card matching Backtests/Deals ── */}
      <div className="border-4 border-black dark:border-white bg-[#FFE600] text-black shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#fff] overflow-hidden transition-all">
        {/* Header Bar */}
        <div className="p-4 sm:p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 border-2 border-black bg-black text-[#FFE600] text-xs font-black uppercase tracking-wider shadow-[2px_2px_0px_#000]">
                <Activity className="w-4 h-4 text-[#FFE600]" />
                <span>{isAr ? "الماسح الفني اللحظي ⚡ TS" : "Live Technical Screener ⚡ TS"}</span>
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-1 border-2 border-black bg-white text-black text-xs font-black shadow-[2px_2px_0px_#000]">
                <Flame className="w-3.5 h-3.5 text-amber-600 fill-amber-500" />
                <span>{isAr ? "الانفجارات السعرية والمصائد (Spring & Upthrust)" : "Price Explosions & Wyckoff Traps"}</span>
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-1 border-2 border-black bg-emerald-400 text-black text-xs font-black shadow-[2px_2px_0px_#000]">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>{isAr ? "منهجية وايكوف • إدارة المخاطر الرقمية" : "Wyckoff Method • Quant Risk Control"}</span>
              </span>
            </div>

            <h1 className="text-xl sm:text-2xl lg:text-3xl font-black text-black tracking-tight leading-tight">
              {isAr
                ? "دليل ومنهجية رصد الانفجارات السعرية وكاشف المصائد والانعكاسات"
                : "Methodology Guide: Price Explosions & Wyckoff Trap Detector"}
            </h1>

            {!isOpen && (
              <p className="text-xs sm:text-sm font-bold text-zinc-900 leading-relaxed max-w-4xl">
                {isAr
                  ? "خوارزميات فنية كمية ترصد تدفق السيولة المؤسسية غير المعتادة وفخاخ صانع السوق لاقتناص الصفقات الرابحة قبل انطلاق الموجات السعرية مع حماية رأس المال."
                  : "Quantitative algorithmic engine tracking abnormal institutional volume surges and smart money traps (Spring & Upthrust) to capture high-probability reversals while safeguarding capital."}
              </p>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2.5 shrink-0">
            <button
              onClick={() => setIsOpen((prev) => !prev)}
              className="h-10 px-4 border-2 border-black bg-black text-[#FFE600] hover:bg-zinc-900 font-black text-xs uppercase flex items-center justify-center gap-1.5 shadow-[2px_2px_0px_#000] active:translate-x-[1px] active:translate-y-[1px] transition-all cursor-pointer"
            >
              <span>{isOpen ? (isAr ? "إغلاق السيكشن ▴" : "Close Guide ▴") : (isAr ? "عرض الدليل والمعادلات ▾" : "Show Guide & Formulas ▾")}</span>
              {isOpen ? <ChevronUp className="w-4 h-4 text-[#FFE600]" /> : <ChevronDown className="w-4 h-4 text-[#FFE600]" />}
            </button>
          </div>
        </div>

        {/* ── Collapsible Content: Detailed Guide ── */}
        {isOpen && (
          <div className="border-t-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-7 space-y-8 text-black dark:text-zinc-100 transition-all">
            
            {/* ══════════════════════════════════════════════════════════════════
                SECTION 1: نشاط غير طبيعي وانفجار سعري
            ══════════════════════════════════════════════════════════════════ */}
            <div className="space-y-4">
              <div className="border-2 border-black dark:border-amber-500/40 bg-amber-50 dark:bg-amber-950/30 p-4 sm:p-5 space-y-2">
                <div className="flex items-center gap-2 text-amber-800 dark:text-amber-400 font-black text-sm sm:text-base uppercase">
                  <Flame className="w-5 h-5 fill-amber-500 text-amber-600" />
                  <span>{isAr ? "القسم الأول: نشاط غير طبيعي وانفجار سعري (Unusual Activity & Volume Spikes)" : "Section 1: Unusual Activity & Volume Breakouts"}</span>
                </div>
                <p className="text-xs sm:text-sm font-bold text-zinc-800 dark:text-zinc-200 leading-relaxed max-w-5xl">
                  {isAr
                    ? "نظام كمي يرصد تدفق السيولة الضخمة وغير المعتادة على أسهم البورصة المصرية مقارنة بمتوسطاتها التاريخية، مع فحص نطاقات التماسك لاقتناص بداية تفريغ الطاقة السعرية وانطلاق الموجة."
                    : "Quantitative screener detecting abnormal institutional volume surges compared to historical baselines, identifying consolidation breakouts at the onset of major momentum waves."}
                </p>
              </div>

              {/* 3 Steps Grid for Section 1 */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* 1. إزاي بنجيبها؟ */}
                <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/80 p-4 sm:p-5 space-y-3 relative shadow-[2px_2px_0px_#000] dark:shadow-[2px_2px_0px_#fff]">
                  <div className="flex items-center gap-2 border-b-2 border-black dark:border-zinc-700 pb-2">
                    <div className="w-6 h-6 border-2 border-black bg-[#FFE600] flex items-center justify-center font-black text-xs text-black">1</div>
                    <h3 className="font-black text-xs sm:text-sm text-black dark:text-white">
                      {isAr ? "إزاي بنجيبها؟ (المعادلات ومصادر البيانات)" : "How is it Calculated? (Formulas & Data)"}
                    </h3>
                  </div>
                  <ul className="text-xs font-bold text-zinc-700 dark:text-zinc-300 space-y-2 leading-relaxed">
                    <li className="flex items-start gap-1.5">
                      <span className="text-amber-600 dark:text-amber-400 font-black">•</span>
                      <span><strong>السيولة النسبية (r_vol):</strong> نقسم حجم تداول الجلسة الحالية على متوسط حجم 20 جلسة (<code className="bg-zinc-200 dark:bg-zinc-800 px-1 py-0.5 rounded text-[11px]">Volume / SMA20</code>). السهم يُدرج فقط إذا كان الحجم مضاعفاً (1.5x إلى 8.5x+).</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="text-amber-600 dark:text-amber-400 font-black">•</span>
                      <span><strong>نطاق تماسك 20 جلسة:</strong> فحص موقع السعر بالنسبة لأعلى وأدنى نقطة مسجلة في آخر 20 جلسة لتحديد هل هو كسر قمة تماسك أم بداية انعكاس من قاع.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="text-amber-600 dark:text-amber-400 font-black">•</span>
                      <span><strong>إحصائيات النجاح الموثقة:</strong> فحص تلقائي لآخر 40 جلسة لقياس نسبة صعود السهم خلال 5 أيام تداول ومتوسط أقصى صعود محقق (Avg Max Gain).</span>
                    </li>
                  </ul>
                </div>

                {/* 2. استخداماتها إيه للمستخدم؟ */}
                <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/80 p-4 sm:p-5 space-y-3 relative shadow-[2px_2px_0px_#000] dark:shadow-[2px_2px_0px_#fff]">
                  <div className="flex items-center gap-2 border-b-2 border-black dark:border-zinc-700 pb-2">
                    <div className="w-6 h-6 border-2 border-black bg-blue-400 flex items-center justify-center font-black text-xs text-black">2</div>
                    <h3 className="font-black text-xs sm:text-sm text-black dark:text-white">
                      {isAr ? "استخداماتها إيه بالنسبة للمستخدم؟" : "What is it Used For?"}
                    </h3>
                  </div>
                  <ul className="text-xs font-bold text-zinc-700 dark:text-zinc-300 space-y-2 leading-relaxed">
                    <li className="flex items-start gap-1.5">
                      <span className="text-blue-600 dark:text-blue-400 font-black">•</span>
                      <span><strong>رصد السيولة الساخنة في مهدها:</strong> معرفة الأسهم التي تدخلها محافظ المؤسسات وحيتان السوق قبل انتشار الخبر وصعود السهم.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="text-blue-600 dark:text-blue-400 font-black">•</span>
                      <span><strong>اقتناص صفقات السوينج السريعة:</strong> مثالية للمتداولين الباحثين عن فرص زخم مكثفة تتراوح مدتها بين 3 إلى 10 جلسات تداول.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="text-blue-600 dark:text-blue-400 font-black">•</span>
                      <span><strong>فلترة الأسهم الحية:</strong> التمييز الفوري بين الأسهم التي تتحرك بسيولة حقيقية تدعم الصعود، وتلك التي ترتفع بأحجام هشة وهمية.</span>
                    </li>
                  </ul>
                </div>

                {/* 3. إزاي يستفيد منها في التداول؟ */}
                <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/80 p-4 sm:p-5 space-y-3 relative shadow-[2px_2px_0px_#000] dark:shadow-[2px_2px_0px_#fff]">
                  <div className="flex items-center gap-2 border-b-2 border-black dark:border-zinc-700 pb-2">
                    <div className="w-6 h-6 border-2 border-black bg-emerald-400 flex items-center justify-center font-black text-xs text-black">3</div>
                    <h3 className="font-black text-xs sm:text-sm text-black dark:text-white">
                      {isAr ? "إزاي تستفيد منها عملياً في التداول؟" : "How to Profit from it in Trading?"}
                    </h3>
                  </div>
                  <ul className="text-xs font-bold text-zinc-700 dark:text-zinc-300 space-y-2 leading-relaxed">
                    <li className="flex items-start gap-1.5">
                      <span className="text-emerald-600 dark:text-emerald-400 font-black">•</span>
                      <span><strong>قاعدة الدخول:</strong> الشراء مع تأكيد اختراق المقاومة بسيولة &gt;1.5x؛ تجنب الشراء إذا كان RSI متضخماً (&gt;75) لتفادي جني الأرباح السريع.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="text-emerald-600 dark:text-emerald-400 font-black">•</span>
                      <span><strong>وقف الخسارة الصارم:</strong> وضع وقف خسارة محدد بين <strong>2.5% إلى 3.5%</strong> أسفل سعر الشراء أو تحت أدنى قاع لشمعة الانفجار.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="text-emerald-600 dark:text-emerald-400 font-black">•</span>
                      <span><strong>جني الأرباح:</strong> بيع نصف الكمية عند أقرب مقاومة أو سقف بولينجر، وترك النصف الآخر يركب الاتجاه بوقف متحرك (Trailing Stop).</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            {/* ══════════════════════════════════════════════════════════════════
                SECTION 2: كاشف المصائد والانعكاسات (Spring & Upthrust)
            ══════════════════════════════════════════════════════════════════ */}
            <div className="space-y-4">
              <div className="border-2 border-black dark:border-purple-500/40 bg-purple-50 dark:bg-purple-950/30 p-4 sm:p-5 space-y-2">
                <div className="flex items-center gap-2 text-purple-900 dark:text-purple-300 font-black text-sm sm:text-base uppercase">
                  <ShieldAlert className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                  <span>{isAr ? "القسم الثاني: كاشف المصائد والانعكاسات اللحظية (Wyckoff Spring & Upthrust Traps)" : "Section 2: Smart Money Trap Detector (Wyckoff Spring & Upthrust)"}</span>
                </div>
                <p className="text-xs sm:text-sm font-bold text-zinc-800 dark:text-zinc-200 leading-relaxed max-w-5xl">
                  {isAr
                    ? "مستوحى من مدرسة التحليل الحجمي (Wyckoff VSA) لرصد فخاخ صانع السوق عند مستويات الدعم والمقاومة الحاسمة: اصطياد ارتدادات القيعان (Spring) والحماية من الاختراقات الكاذبة (Upthrust)."
                    : "Based on Wyckoff Volume Spread Analysis (VSA) to detect smart money traps at key technical pivots: capturing bottom springs and evading deceptive bull traps."}
                </p>
              </div>

              {/* 3 Steps Grid for Section 2 */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* 1. إزاي بنجيبها؟ */}
                <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/80 p-4 sm:p-5 space-y-3 relative shadow-[2px_2px_0px_#000] dark:shadow-[2px_2px_0px_#fff]">
                  <div className="flex items-center gap-2 border-b-2 border-black dark:border-zinc-700 pb-2">
                    <div className="w-6 h-6 border-2 border-black bg-[#FFE600] flex items-center justify-center font-black text-xs text-black">1</div>
                    <h3 className="font-black text-xs sm:text-sm text-black dark:text-white">
                      {isAr ? "إزاي بنجيبها؟ (منهجية وايكوف الحسابية)" : "How is it Detected? (Wyckoff Logic)"}
                    </h3>
                  </div>
                  <ul className="text-xs font-bold text-zinc-700 dark:text-zinc-300 space-y-2 leading-relaxed">
                    <li className="flex items-start gap-1.5">
                      <span className="text-purple-600 dark:text-purple-400 font-black">•</span>
                      <span><strong>مصيدة الدببة (Spring):</strong> هبوط السعر تحت مستوى دعم رئيسي لضرب وقوف الخسارة، يعقبه ارتداد فوري داخل الجلسة وتكوين ذيل سفلي طويل (Rejection Tail) مع امتصاص بيعي قوي.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="text-purple-600 dark:text-purple-400 font-black">•</span>
                      <span><strong>مصيدة الثيران (Upthrust):</strong> اختراق صاعد وهمي لمقاومة يجذب المشترين في القمة، ثم ينعكس هبوطاً أسفل المقاومة بذيل علوي طويل، محذراً من تصريف محترف.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="text-purple-600 dark:text-purple-400 font-black">•</span>
                      <span><strong>قوة الإشارة ومعدل الصعود:</strong> قياس خوارزمي لنسبة استرداد الدعم/المقاومة، مع قياس دقة الارتداد التاريخية لـ 3 أيام تداول عبر 40 جلسة.</span>
                    </li>
                  </ul>
                </div>

                {/* 2. استخداماتها إيه للمستخدم؟ */}
                <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/80 p-4 sm:p-5 space-y-3 relative shadow-[2px_2px_0px_#000] dark:shadow-[2px_2px_0px_#fff]">
                  <div className="flex items-center gap-2 border-b-2 border-black dark:border-zinc-700 pb-2">
                    <div className="w-6 h-6 border-2 border-black bg-purple-400 flex items-center justify-center font-black text-xs text-black">2</div>
                    <h3 className="font-black text-xs sm:text-sm text-black dark:text-white">
                      {isAr ? "استخداماتها إيه بالنسبة للمستخدم؟" : "What is it Used For?"}
                    </h3>
                  </div>
                  <ul className="text-xs font-bold text-zinc-700 dark:text-zinc-300 space-y-2 leading-relaxed">
                    <li className="flex items-start gap-1.5">
                      <span className="text-purple-600 dark:text-purple-400 font-black">•</span>
                      <span><strong>صيد القيعان بأقل نسبة مخاطرة (Spring):</strong> الشراء جنباً إلى جنب مع صانع السوق فور انتهاء موجة الترهيب وطرد البائعين المذعورين.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="text-purple-600 dark:text-purple-400 font-black">•</span>
                      <span><strong>حماية رأس المال من التعليق (Upthrust):</strong> تجنب فخ الشراء في القمم السعرية والابتعاد عن الأسهم التي تشهد تصريفاً خفياً.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="text-purple-600 dark:text-purple-400 font-black">•</span>
                      <span><strong>تحديد نقاط الدخول فائقة الدقة:</strong> الدخول عند مستويات فنية حرجة توفر أعلى نسبة عائد إلى مخاطرة (Risk-to-Reward تصل إلى 1:3 و 1:4).</span>
                    </li>
                  </ul>
                </div>

                {/* 3. إزاي يستفيد منها في التداول؟ */}
                <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/80 p-4 sm:p-5 space-y-3 relative shadow-[2px_2px_0px_#000] dark:shadow-[2px_2px_0px_#fff]">
                  <div className="flex items-center gap-2 border-b-2 border-black dark:border-zinc-700 pb-2">
                    <div className="w-6 h-6 border-2 border-black bg-emerald-400 flex items-center justify-center font-black text-xs text-black">3</div>
                    <h3 className="font-black text-xs sm:text-sm text-black dark:text-white">
                      {isAr ? "إزاي تستفيد منها عملياً في التداول؟" : "How to Profit from it in Trading?"}
                    </h3>
                  </div>
                  <ul className="text-xs font-bold text-zinc-700 dark:text-zinc-300 space-y-2 leading-relaxed">
                    <li className="flex items-start gap-1.5">
                      <span className="text-emerald-600 dark:text-emerald-400 font-black">•</span>
                      <span><strong>توقيت الشراء في الـ Spring:</strong> الدخول فور عودة السعر والإغلاق أعلى مستوى الدعم المكسور وهمياً.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="text-emerald-600 dark:text-emerald-400 font-black">•</span>
                      <span><strong>الوقف النقطي المحكم:</strong> وضع أمر وقف الخسارة أسفل أدنى قاع لذيل الشمعة (Low of the Tail)؛ المخاطرة هنا صغيرة جداً لا تتجاوز 1.5% - 2.5%.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="text-emerald-600 dark:text-emerald-400 font-black">•</span>
                      <span><strong>التعامل مع الـ Upthrust:</strong> إذا كنت تمتلك السهم، يُعد خروجاً أو جني أرباح فوري؛ إذا كنت تفكر في الشراء، ابتعد تماماً وانتظر استقرار السعر.</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            {/* ══════════════════════════════════════════════════════════════════
                SECTION 3: مصفوفة المقارنة السريعة وإدارة رأس المال
            ══════════════════════════════════════════════════════════════════ */}
            <div className="space-y-4">
              <div className="flex items-center gap-2.5 border-b-2 border-black dark:border-zinc-700 pb-2">
                <div className="w-7 h-7 border-2 border-black bg-[#FFE600] flex items-center justify-center font-black">
                  <Scale className="w-4 h-4 text-black" />
                </div>
                <div>
                  <h3 className="text-sm sm:text-base font-black text-black dark:text-white">
                    {isAr ? "مصفوفة المقارنة السريعة وقواعد إدارة رأس المال" : "Quick Comparison Matrix & Capital Management"}
                  </h3>
                  <p className="text-xs font-bold text-zinc-500 dark:text-zinc-400">
                    {isAr ? "دليل سريع لاختيار الإشارة وتوزيع السيولة بأمان" : "Quick guide for signal selection and capital allocation"}
                  </p>
                </div>
              </div>

              {/* Table Matrix */}
              <div className="overflow-x-auto border-2 border-black dark:border-zinc-700">
                <table className="w-full text-xs text-left rtl:text-right border-collapse">
                  <thead className="bg-black text-[#FFE600] dark:bg-zinc-900 dark:text-[#FFE600] uppercase font-black">
                    <tr>
                      <th className="p-3 border-b-2 border-black dark:border-zinc-700">{isAr ? "نوع الإشارة" : "Signal Type"}</th>
                      <th className="p-3 border-b-2 border-black dark:border-zinc-700">{isAr ? "طبيعة الحركة" : "Market Behavior"}</th>
                      <th className="p-3 border-b-2 border-black dark:border-zinc-700">{isAr ? "الأفق الزمني" : "Timeframe"}</th>
                      <th className="p-3 border-b-2 border-black dark:border-zinc-700">{isAr ? "مكان وقف الخسارة" : "Stop Loss Placement"}</th>
                      <th className="p-3 border-b-2 border-black dark:border-zinc-700">{isAr ? "الهدف الرئيسي" : "Primary Objective"}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800 bg-white dark:bg-zinc-950 font-bold">
                    <tr className="hover:bg-amber-50/50 dark:hover:bg-amber-950/20">
                      <td className="p-3 font-black text-amber-600 dark:text-amber-400">
                        {isAr ? "⚡ نشاط غير طبيعي وانفجار سعري" : "⚡ Unusual Volume Explosion"}
                      </td>
                      <td className="p-3">{isAr ? "اختراق زخم مدعوم بسيولة مؤسسية &gt;1.5x" : "Momentum breakout backed by &gt;1.5x institutional volume"}</td>
                      <td className="p-3">{isAr ? "3 إلى 10 جلسات" : "3 to 10 sessions"}</td>
                      <td className="p-3">{isAr ? "2.5% – 3.5% أسفل شمعة الكسر أو EMA20" : "2.5% – 3.5% below breakout bar or EMA20"}</td>
                      <td className="p-3">{isAr ? "ركوب موجة الصعود والانطلاق السعري" : "Riding high-velocity expansion waves"}</td>
                    </tr>
                    <tr className="hover:bg-emerald-50/50 dark:hover:bg-emerald-950/20">
                      <td className="p-3 font-black text-emerald-600 dark:text-emerald-400">
                        {isAr ? "🟢 مصيدة الدببة (Spring)" : "🟢 Bear Trap (Spring Reversal)"}
                      </td>
                      <td className="p-3">{isAr ? "كسر وهمي لدعم وارتداد فوري بذيل سفلي" : "False support break & instant rejection with lower tail"}</td>
                      <td className="p-3">{isAr ? "2 إلى 6 جلسات" : "2 to 6 sessions"}</td>
                      <td className="p-3">{isAr ? "نقطي أسفل أدنى قاع للذيل (Low of Tail)" : "Tight stop right below lowest tail point"}</td>
                      <td className="p-3">{isAr ? "صيد قاع الموجة بنسبة عائد لمخاطرة 1:3+" : "Bottom fishing with 1:3+ Risk-Reward"}</td>
                    </tr>
                    <tr className="hover:bg-rose-50/50 dark:hover:bg-rose-950/20">
                      <td className="p-3 font-black text-rose-600 dark:text-rose-400">
                        {isAr ? "🔴 مصيدة الثيران (Upthrust)" : "🔴 Bull Trap (Upthrust Reversal)"}
                      </td>
                      <td className="p-3">{isAr ? "اختراق كاذب لمقاومة يعقبه هبوط وتصريف" : "Deceptive resistance break followed by sharp dump"}</td>
                      <td className="p-3">{isAr ? "تحذير فوري لحظي" : "Instant intraday alert"}</td>
                      <td className="p-3">{isAr ? "خروج فوري لحاملي السهم / تجنب الشراء" : "Immediate exit for holders / Avoid buying"}</td>
                      <td className="p-3">{isAr ? "حماية رأس المال من التعليق في القمم" : "Preserving capital from top buying traps"}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Capital Protection Rules */}
              <div className="p-3.5 border-2 border-black dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 text-xs font-bold flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-[2px_2px_0px_#000] dark:shadow-[2px_2px_0px_#fff]">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                  <span>
                    {isAr
                      ? "القاعدة الذهبية: لا تخصص أكثر من 15% - 20% من إجمالي المحفظة في صفقة انفجار واحدة، والتزم دائماً بوقف الخسارة المكتوب لحماية الأرباح ورأس المال."
                      : "Golden Rule: Never allocate more than 15% - 20% of your portfolio into a single breakout trade, and always strictly honor stop loss levels."}
                  </span>
                </div>
                <button
                  onClick={() => setIsOpen(false)}
                  className="px-3 py-1.5 border-2 border-black bg-[#FFE600] text-black hover:bg-amber-400 text-xs font-black shrink-0 transition-all shadow-[2px_2px_0px_#000]"
                >
                  {isAr ? "إغلاق الدليل ▴" : "Close Guide ▴"}
                </button>
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
}
