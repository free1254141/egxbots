"use client";

import Link from "next/link";
import { useChat } from "@/contexts/ChatContext";
import { useLanguage } from "@/contexts/LanguageContext";
import BrandedPageHeader from "@/components/BrandedPageHeader";
import {
  Brain,
  Zap,
  TrendingUp,
  ShieldCheck,
  BarChart3,
  Bot,
  ChevronDown,
  LineChart,
  Search,
  MessageSquare,
  Sparkles,
} from "lucide-react";
import { useState } from "react";

export default function AIScannerClient() {
  const { setIsOpen } = useChat();
  const { language } = useLanguage();
  const isAr = language === "ar";
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  const toggleFaq = (idx: number) => {
    setOpenFaq(openFaq === idx ? null : idx);
  };

  const openAIChat = () => {
    setIsOpen(true);
  };

  const pillars = [
    {
      icon: Brain,
      badgeBg: "bg-amber-400 text-black",
      title: isAr ? "تصنيف كمّي ذكي (AI Score)" : "Quantitative AI Score (1-10)",
      desc: isAr
        ? "نموذج احتمالي يقيّم كل سهم من 1 إلى 10 بناءً على بيانات التداول التاريخية، ليوضح حالة الزخم الفني ومناطق التجميع أو التصريف المحتملة."
        : "A probabilistic model scoring each stock from 1 to 10 based on historical market data, highlighting technical momentum and potential accumulation or distribution zones.",
    },
    {
      icon: ShieldCheck,
      badgeBg: "bg-emerald-400 text-black",
      title: isAr
        ? "محاكاة واختبار تاريخي (Backtesting)"
        : "Historical Backtesting Engine",
      desc: isAr
        ? "لا نعتمد على التخمين؛ خوارزمياتنا تم اختبارها تاريخياً بطريقة الحاجز الثلاثي (Triple Barrier) مع منع تسرب البيانات المستقبلية لقياس الأداء الإحصائي بدقة."
        : "Zero guesswork. Our algorithms are historically tested using the Triple Barrier Method with strict look-ahead bias prevention to measure statistical performance.",
    },
    {
      icon: MessageSquare,
      badgeBg: "bg-cyan-400 text-black",
      title: isAr
        ? "المساعد الذكي التفاعلي للبورصة"
        : "Interactive EGX AI Assistant",
      desc: isAr
        ? "تحاور مع المساعد الذكي، استعرض مستويات الدعم والمقاومة المحسوبة، قارن بين المؤشرات الفنية لسهمين في ثوانٍ، أو ارفع صورة الشارت لقراءتها آلياً."
        : "Chat with the AI assistant to inspect calculated support and resistance levels, compare technical indicators between two stocks in seconds, or upload a chart image.",
    },
    {
      icon: TrendingUp,
      badgeBg: "bg-purple-400 text-black",
      title: isAr
        ? "رصد السيولة والتقاطعات الفنية"
        : "Liquidity & Technical Crossovers",
      desc: isAr
        ? "مسح آلي لتقاطعات المتوسطات المتحركة (EMA50/EMA200)، مؤشر القوة النسبية RSI، واختراقات أحجام التداول غير الاعتيادية في البورصة المصرية."
        : "Automated scanning for moving average crossovers (EMA50/EMA200), RSI momentum shifts, and unusual volume breakouts across the Egyptian Exchange.",
    },
    {
      icon: BarChart3,
      badgeBg: "bg-orange-400 text-black",
      title: isAr
        ? "فلترة الأسهم المتوافقة مع الشريعة"
        : "Sharia-Compliant Stock Filtering",
      desc: isAr
        ? "تصنيف وفلترة فورية للأسهم المتوافقة مع الضوابط الشرعية المعتمدة في السوق المصري لتسهيل البحث والمقارنة الفنية."
        : "Instant filtering for stocks listed under Sharia-compliant criteria on the Egyptian market to streamline your technical research and screening.",
    },
    {
      icon: Zap,
      badgeBg: "bg-pink-400 text-black",
      title: isAr
        ? "معالجة يومية بعد إغلاق الجلسة"
        : "Daily Post-Session Model Updates",
      desc: isAr
        ? "مع نهاية كل جلسة تداول بالبورصة المصرية، تتم معالجة البيانات وإعادة تشغيل النماذج الكمية لتحديث المؤشرات قبل الجلسة التالية."
        : "After every EGX trading session closes, market data is processed and quantitative models are re-evaluated before the next market open.",
    },
  ];

  const faqs = [
    {
      q: isAr
        ? "كيف يعمل محلل الأسهم بالذكاء الاصطناعي (EGX AI Analyzer)؟"
        : "How does the EGX AI Stock Analyzer work?",
      a: isAr
        ? "يعتمد المحلل على نماذج تعلم آلي كمّية (Machine Learning) تم تدريبها على سنوات من بيانات التداول التاريخية في البورصة المصرية (EGX). يقوم النظام بفحص حركة السعر، السيولة، ومؤشرات الزخم (RSI, MACD, ADX) لتوليد تقييم رقمي موضوعي لكل سهم دون أي تحيز بشري."
        : "The analyzer relies on quantitative machine learning models trained on years of historical Egyptian Exchange (EGX) trading data. It evaluates price action, liquidity flow, and momentum indicators (RSI, MACD, ADX) to generate an objective numerical score for every stock without human bias.",
    },
    {
      q: isAr
        ? "ما هو مقياس الذكاء الاصطناعي (AI Score) من 1 إلى 10؟"
        : "What is the 1 to 10 AI Score scale?",
      a: isAr
        ? "المقياس هو تصنيف إحصائي لحالة السهم الفنية: من 1 إلى 3 يمثل مؤشراً سلبياً وضغطاً بيعياً (Bearish / Negative Momentum)، ومن 4 إلى 6 يمثل اتجاهاً محايداً واستقراراً عرضياً (Neutral)، ومن 7 إلى 10 يمثل مؤشر زخم إيجابي وتوافقاً في السيولة (Bullish / Positive Momentum)."
        : "The scale is a statistical classification of a stock's technical posture: 1 to 3 indicates negative momentum and selling pressure (Bearish), 4 to 6 indicates sideways consolidation (Neutral), and 7 to 10 indicates positive momentum and liquidity alignment (Bullish).",
    },
    {
      q: isAr
        ? "كيف يمكنني استخدام الشات بوت التفاعلي لتحليل بيانات الأسهم؟"
        : "How can I use the interactive AI chatbot to analyze stock data?",
      a: isAr
        ? "يمكنك الضغط على زر 'تشغيل المساعد الذكي' في أي وقت، وكتابة اسم أو رمز أي سهم مصري (مثل COMI أو ETEL أو ABUK)، أو رفع لقطة شاشة للشارت، وسيقوم المساعد الذكي بعرض المؤشرات الفنية ومستويات الدعم والمقاومة المحسوبة فوراً."
        : "Click the 'Launch AI Assistant' button anytime, type the name or ticker symbol of any Egyptian stock (such as COMI, ETEL, or ABUK), or upload a chart screenshot, and the assistant will immediately display calculated technical indicators and support/resistance levels.",
    },
    {
      q: isAr
        ? "هل تحليلات المنصة تعتبر توصيات شراء أو بيع؟"
        : "Are the platform's analytics considered buy or sell recommendations?",
      a: isAr
        ? "لا، جميع المخرجات والتقييمات المعروضة على منصة EGX BOTS هي أدوات برمجية ومؤشرات فنية وإحصائية عامة لأغراض البحث والدراسة فقط، ولا تُعد استشارة مالية أو توصية بالشراء أو البيع."
        : "No. All outputs and scores displayed on EGX BOTS are automated software tools and general statistical/technical indicators for research and educational purposes only, and do not constitute financial advice or buy/sell recommendations.",
    },
  ];

  return (
    <main
      dir={isAr ? "rtl" : "ltr"}
      className="neobrutal-layout flex flex-col gap-10 pb-20 pt-2 relative -mx-3 sm:-mx-6 md:-mx-8 px-4 md:px-8 min-h-screen neobrutal-grid-bg text-zinc-900 dark:text-zinc-100 selection:bg-yellow-400 selection:text-black"
    >
      <div className="mx-auto w-full max-w-6xl">
        <BrandedPageHeader
          dir={isAr ? "rtl" : "ltr"}
          badgeIcon={<Sparkles className="w-5 h-5 text-amber-500" />}
          eyebrow={
            isAr
              ? "محرك الذكاء الاصطناعي الكمي"
              : "EGX AI ANALYZER & QUANTITATIVE ENGINE"
          }
          title={
            isAr
              ? "محلل الأسهم المصرية بالذكاء الاصطناعي"
              : "EGX AI Stock Market Analyzer"
          }
          description={
            isAr
              ? "يفحص النظام أكثر من 270 سهمًا مصريًا باستخدام نماذج كمية وبيانات تاريخية لتقديم تقييمات ومؤشرات تحليلية منهجية."
              : "Quantitative models evaluate 270+ Egyptian stocks using historical data to provide systematic analytical scores and technical indicators."
          }
        />

        {/* Hero Actions & Key Stats Bar */}
        <section className="mt-8 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 sm:p-8 shadow-[6px_6px_0px_0px_#000] dark:shadow-[6px_6px_0px_0px_#fff]">
          <div className="mx-auto max-w-5xl text-center">
            {/* Primary CTAs */}
            <div className="flex flex-wrap items-center justify-center gap-4">
              <button
                onClick={openAIChat}
                className="inline-flex items-center gap-2 border-2 border-black bg-[#FFE600] px-6 py-3.5 text-sm font-black text-black shadow-[4px_4px_0_0_#000] dark:shadow-[4px_4px_0_0_#fff] transition hover:translate-y-0.5 hover:shadow-none sm:text-base cursor-pointer"
              >
                <Bot className="h-5 w-5" />
                <span>
                  {isAr
                    ? "تشغيل المساعد الذكي والمحلل الآن"
                    : "Launch AI Assistant & Analyzer Now"}
                </span>
              </button>

              <Link
                href="/scanner/backtests"
                className="inline-flex items-center gap-2 border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 px-6 py-3.5 text-sm font-black text-zinc-900 dark:text-white shadow-[4px_4px_0_0_#000] dark:shadow-[4px_4px_0_0_#fff] transition hover:translate-y-0.5 hover:shadow-none sm:text-base"
              >
                <LineChart className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
                <span>
                  {isAr
                    ? "محرك المحاكاة والتقييمات (Backtests)"
                    : "Backtest & Simulation Engine"}
                </span>
              </Link>

              <Link
                href="/scanner/technical"
                className="inline-flex items-center gap-2 border-2 border-black dark:border-white bg-white dark:bg-zinc-950 px-5 py-3.5 text-sm font-black text-zinc-800 dark:text-zinc-200 shadow-[4px_4px_0_0_#000] dark:shadow-[4px_4px_0_0_#fff] transition hover:translate-y-0.5 hover:shadow-none"
              >
                <Search className="h-4 w-4 text-amber-500" />
                <span>
                  {isAr ? "الماسح الفني للأسهم" : "Technical Stock Scanner"}
                </span>
              </Link>
            </div>

            {/* Key Stats Bar */}
            <div className="mt-10 grid grid-cols-2 gap-4 border-t-2 border-black dark:border-zinc-700 pt-8 sm:grid-cols-4">
              <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/80 p-4 shadow-[3px_3px_0_0_#000] dark:shadow-[3px_3px_0_0_#fff]">
                <div className="text-2xl font-black text-amber-600 dark:text-yellow-400 sm:text-3xl">
                  279+
                </div>
                <div className="mt-1 text-xs font-bold text-zinc-700 dark:text-zinc-300">
                  {isAr ? "سهم مصري تحت الرصد" : "EGX Stocks Tracked"}
                </div>
              </div>
              <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/80 p-4 shadow-[3px_3px_0_0_#000] dark:shadow-[3px_3px_0_0_#fff]">
                <div className="text-2xl font-black text-emerald-600 dark:text-emerald-400 sm:text-3xl">
                  1 - 10
                </div>
                <div className="mt-1 text-xs font-bold text-zinc-700 dark:text-zinc-300">
                  {isAr ? "مقياس الذكاء الاصطناعي" : "Quantitative AI Score"}
                </div>
              </div>
              <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/80 p-4 shadow-[3px_3px_0_0_#000] dark:shadow-[3px_3px_0_0_#fff]">
                <div className="text-2xl font-black text-cyan-600 dark:text-cyan-400 sm:text-3xl">
                  24/7
                </div>
                <div className="mt-1 text-xs font-bold text-zinc-700 dark:text-zinc-300">
                  {isAr ? "شات بوت تفاعلي مباشر" : "Live Interactive AI Chat"}
                </div>
              </div>
              <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/80 p-4 shadow-[3px_3px_0_0_#000] dark:shadow-[3px_3px_0_0_#fff]">
                <div className="text-2xl font-black text-purple-600 dark:text-purple-400 sm:text-3xl">
                  0%
                </div>
                <div className="mt-1 text-xs font-bold text-zinc-700 dark:text-zinc-300">
                  {isAr ? "تحيز عاطفي أو بشري" : "Emotional or Human Bias"}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Pillars Section */}
        <section className="mt-12">
          <div className="text-center mb-10">
            <h2 className="text-2xl font-black text-zinc-950 dark:text-white sm:text-3xl">
              {isAr
                ? "ما الذي يقدمه لك محلل البورصة المصرية (EGX AI Analyzer)؟"
                : "What Does the EGX AI Analyzer Offer You?"}
            </h2>
            <p className="mx-auto mt-3 max-w-2xl text-sm font-semibold text-zinc-700 dark:text-zinc-300 sm:text-base">
              {isAr
                ? "تم بناء المنصة لسد الفجوة بين التحليل الفني الكلاسيكي والتحليل الكمّي الحديث المعتمد على خوارزميات التعلم الآلي."
                : "Built to bridge the gap between classical technical charting and modern quantitative analysis powered by machine learning."}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {pillars.map((item, index) => {
              const IconComp = item.icon;
              return (
                <div
                  key={index}
                  className="border-2 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 shadow-[5px_5px_0px_0px_#000] dark:shadow-[5px_5px_0px_0px_#fff] transition hover:-translate-y-1"
                >
                  <div
                    className={`flex h-12 w-12 items-center justify-center border-2 border-black ${item.badgeBg} shadow-[2px_2px_0_0_#000]`}
                  >
                    <IconComp className="h-6 w-6" />
                  </div>
                  <h3 className="mt-4 text-lg font-black text-zinc-950 dark:text-white">
                    {item.title}
                  </h3>
                  <p className="mt-2 text-sm font-medium leading-relaxed text-zinc-700 dark:text-zinc-300">
                    {item.desc}
                  </p>
                </div>
              );
            })}
          </div>
        </section>

        {/* Interactive Score Explainer */}
        <section className="mt-12 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 sm:p-10 shadow-[6px_6px_0px_0px_#000] dark:shadow-[6px_6px_0px_0px_#fff]">
          <div className="mx-auto max-w-4xl text-center">
            <h2 className="text-2xl font-black text-zinc-950 dark:text-white sm:text-3xl">
              {isAr
                ? "كيف تقرأ درجات الـ AI Score في المنصة؟"
                : "How to Read the Platform's AI Score"}
            </h2>
            <p className="mt-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300 sm:text-base">
              {isAr
                ? "نظام تصنيف مكون من 10 مستويات يترجم ملايين العمليات الحسابية إلى قراءة فنية واضحة"
                : "A 10-level quantitative scale translating complex technical computations into a clear analytical reading"}
            </p>

            <div className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-3">
              <div className="border-2 border-black dark:border-red-500/70 bg-red-50 dark:bg-red-950/30 p-5 text-start shadow-[4px_4px_0_0_#000] dark:shadow-[4px_4px_0_0_#ef4444]">
                <div className="flex items-center justify-between gap-2">
                  <span className="border border-black bg-red-500 px-2.5 py-1 font-mono text-xs font-black text-white">
                    1 - 3
                  </span>
                  <span className="text-sm font-black text-red-700 dark:text-red-400">
                    {isAr ? "زخم سلبي (Bearish)" : "Negative Momentum (Bearish)"}
                  </span>
                </div>
                <p className="mt-3 text-xs font-semibold leading-relaxed text-zinc-800 dark:text-zinc-200">
                  {isAr
                    ? "مؤشرات تدل على ضغط بيعي مرتفع، كسر مستويات دعم فنية، أو ضعف في السيولة الداخلة."
                    : "Indicators point to elevated selling pressure, broken technical supports, or weakening liquidity inflows."}
                </p>
              </div>

              <div className="border-2 border-black dark:border-amber-500/70 bg-amber-50 dark:bg-amber-950/30 p-5 text-start shadow-[4px_4px_0_0_#000] dark:shadow-[4px_4px_0_0_#f59e0b]">
                <div className="flex items-center justify-between gap-2">
                  <span className="border border-black bg-amber-400 px-2.5 py-1 font-mono text-xs font-black text-black">
                    4 - 6
                  </span>
                  <span className="text-sm font-black text-amber-800 dark:text-amber-400">
                    {isAr ? "نطاق محايد (Neutral)" : "Sideways Range (Neutral)"}
                  </span>
                </div>
                <p className="mt-3 text-xs font-semibold leading-relaxed text-zinc-800 dark:text-zinc-200">
                  {isAr
                    ? "السهم يتحرك داخل نطاق عرضي أو مرحلة ترقب وتوازن بين القوى الشرائية والبيعية."
                    : "The stock is trading within a horizontal range or equilibrium phase between buying and selling forces."}
                </p>
              </div>

              <div className="border-2 border-black dark:border-emerald-500/70 bg-emerald-50 dark:bg-emerald-950/30 p-5 text-start shadow-[4px_4px_0_0_#000] dark:shadow-[4px_4px_0_0_#10b981]">
                <div className="flex items-center justify-between gap-2">
                  <span className="border border-black bg-emerald-500 px-2.5 py-1 font-mono text-xs font-black text-black">
                    7 - 10
                  </span>
                  <span className="text-sm font-black text-emerald-800 dark:text-emerald-400">
                    {isAr ? "زخم إيجابي (Bullish)" : "Positive Momentum (Bullish)"}
                  </span>
                </div>
                <p className="mt-3 text-xs font-semibold leading-relaxed text-zinc-800 dark:text-zinc-200">
                  {isAr
                    ? "توافق إيجابي بين تدفق السيولة ومؤشرات الزخم الفني مع استقرار السعر أعلى المتوسطات المحورية."
                    : "Positive alignment between liquidity inflows and technical momentum indicators above key moving averages."}
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* FAQ Accordion Section */}
        <section className="mt-12 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 sm:p-10 shadow-[6px_6px_0px_0px_#000] dark:shadow-[6px_6px_0px_0px_#fff]">
          <div className="text-center">
            <h2 className="text-2xl font-black text-zinc-950 dark:text-white sm:text-3xl">
              {isAr
                ? "الأسئلة الشائعة عن محلل الأسهم بالذكاء الاصطناعي"
                : "Frequently Asked Questions About EGX AI Analyzer"}
            </h2>
            <p className="mt-2 text-sm font-semibold text-zinc-600 dark:text-zinc-400">
              {isAr
                ? "إجابات واضحة على كل ما يهمك حول المنصة والنماذج الكمية"
                : "Clear answers to everything you need to know about our platform and quantitative models"}
            </p>
          </div>

          <div className="mt-8 space-y-4 max-w-4xl mx-auto">
            {faqs.map((faq, idx) => {
              const isOpen = openFaq === idx;
              return (
                <div
                  key={idx}
                  className="overflow-hidden border-2 border-black dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800 shadow-[3px_3px_0px_0px_#000] dark:shadow-[3px_3px_0px_0px_#27272a]"
                >
                  <button
                    onClick={() => toggleFaq(idx)}
                    className="flex w-full items-center justify-between gap-4 px-5 py-4 text-start font-black text-zinc-950 dark:text-zinc-100 transition hover:bg-zinc-200 dark:hover:bg-zinc-700/80 cursor-pointer"
                  >
                    <span className="text-sm sm:text-base">{faq.q}</span>
                    <ChevronDown
                      className={`h-5 w-5 shrink-0 text-zinc-700 dark:text-zinc-300 transition-transform duration-200 ${
                        isOpen ? "rotate-180 text-amber-500" : ""
                      }`}
                    />
                  </button>
                  {isOpen && (
                    <div className="border-t-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-900 px-5 py-4 text-xs sm:text-sm font-medium leading-relaxed text-zinc-800 dark:text-zinc-200">
                      {faq.a}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* Bottom CTA Banner */}
        <section className="mt-12 border-4 border-black bg-amber-400 dark:bg-amber-500 p-8 sm:p-12 text-center text-black shadow-[8px_8px_0px_0px_#000] dark:shadow-[8px_8px_0px_0px_#fff]">
          <div className="mx-auto max-w-3xl">
            <h2 className="text-2xl font-black text-black sm:text-3xl uppercase">
              {isAr
                ? "ابدأ تحليلك الفني القادم في البورصة المصرية ببيانات دقيقة"
                : "Start Your Next EGX Technical Analysis with Data Precision"}
            </h2>
            <p className="mt-3 text-sm font-bold text-zinc-900 sm:text-base">
              {isAr
                ? "استفد من أدوات المسح الكمي والذكاء الاصطناعي في فحص مؤشرات الأسهم ومراقبة مستويات السيولة."
                : "Leverage quantitative screening and AI tools to inspect stock indicators and monitor market liquidity."}
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-4">
              <button
                onClick={openAIChat}
                className="inline-flex items-center gap-2 border-2 border-black bg-black px-6 py-3.5 text-sm font-black text-white shadow-[4px_4px_0_0_#fff] transition hover:translate-y-0.5 hover:shadow-none sm:text-base cursor-pointer"
              >
                <Bot className="h-5 w-5 text-amber-400" />
                <span>
                  {isAr
                    ? "جرب الشات بوت الذكي الآن مجاناً"
                    : "Try the AI Chatbot Free Now"}
                </span>
              </button>
              <Link
                href="/stocks"
                className="inline-flex items-center gap-2 border-2 border-black bg-white px-6 py-3.5 text-sm font-black text-black shadow-[4px_4px_0_0_#000] transition hover:translate-y-0.5 hover:shadow-none sm:text-base"
              >
                <span>
                  {isAr
                    ? "تصفح دليل أسهم البورصة المصرية"
                    : "Browse EGX Stocks Directory"}
                </span>
              </Link>
            </div>
          </div>
        </section>

        {/* Mandatory FRA Legal Disclaimer */}
        <div className="mt-8 p-4 border-2 border-zinc-400 dark:border-zinc-700 bg-white/90 dark:bg-zinc-900/90 text-xs text-zinc-700 dark:text-zinc-400 leading-relaxed text-center font-semibold">
          {isAr
            ? "⚠️ تنويه قانوني هام: جميع البيانات والمؤشرات ومخرجات النماذج الكمية المعروضة على منصة EGX BOTS هي أدوات برمجية إحصائية لأغراض البحث والدراسة فقط، ولا تمثل بأي حال من الأحوال استشارة مالية أو توصية بالشراء أو البيع. التداول في الأوراق المالية ينطوي على مخاطر، وقرار الاستثمار يقع على عاتق المستخدم وحده عبر شركات السمسرة المرخصة من الهيئة العامة للرقابة المالية."
            : "⚠️ Important Legal Disclaimer: All data, indicators, and quantitative model outputs displayed on EGX BOTS are statistical software tools for research and educational purposes only, and do not constitute financial advice or a recommendation to buy or sell any security. Trading involves risk, and investment decisions are the sole responsibility of the user through FRA-licensed brokerages."}
        </div>
      </div>
    </main>
  );
}
