"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useLanguage } from "@/contexts/LanguageContext";
import { PillarArticle } from "@/lib/seo/pillar-articles";
import BrandedPageHeader from "@/components/BrandedPageHeader";
import {
  Sparkles,
  Calendar,
  Clock,
  User,
  ArrowRight,
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  HelpCircle,
  TrendingUp,
  Zap
} from "lucide-react";

interface PillarArticleClientProps {
  article: PillarArticle;
}

export default function PillarArticleClient({ article }: PillarArticleClientProps) {
  const { language } = useLanguage();
  const isAr = language === "ar";
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  const toggleFaq = (idx: number) => {
    setOpenFaq(openFaq === idx ? null : idx);
  };

  const title = article.title[isAr ? "ar" : "en"];
  const subtitle = article.subtitle[isAr ? "ar" : "en"];
  const author = article.author[isAr ? "ar" : "en"];
  const readingTime = article.readingTime[isAr ? "ar" : "en"];
  const contentHtml = article.content[isAr ? "ar" : "en"];

  return (
    <div
      dir={isAr ? "rtl" : "ltr"}
      className="neobrutal-layout flex flex-col gap-10 pb-20 pt-2 relative -mx-3 sm:-mx-6 md:-mx-8 px-4 md:px-8 min-h-screen neobrutal-grid-bg text-zinc-900 dark:text-zinc-100"
    >
      {/* 1. Official Branded Header */}
      <BrandedPageHeader
        eyebrow={isAr ? "دليل التداول والتحليل الذكي" : "Trading & Analysis Guide"}
        title={title}
        description={subtitle}
        dir={isAr ? "rtl" : "ltr"}
        badgeIcon={<Sparkles className="w-5 h-5 text-amber-500" />}
      />

      <div className="max-w-4xl mx-auto w-full">
        {/* Meta details bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 p-4 mb-8 bg-white dark:bg-zinc-900 border-2 border-black dark:border-white shadow-[4px_4px_0px_0px_#000] dark:shadow-[4px_4px_0px_0px_#fff]">
          <div className="flex flex-wrap items-center gap-6 text-xs sm:text-sm font-bold">
            <span className="flex items-center gap-1.5 text-zinc-800 dark:text-zinc-200">
              <User className="w-4 h-4 text-amber-500" />
              {author}
            </span>
            <span className="flex items-center gap-1.5 text-zinc-600 dark:text-zinc-400">
              <Calendar className="w-4 h-4" />
              {article.publishedAt}
            </span>
            <span className="flex items-center gap-1.5 text-zinc-600 dark:text-zinc-400">
              <Clock className="w-4 h-4" />
              {readingTime}
            </span>
          </div>

          <Link
            href="/blogs"
            className="text-xs font-black uppercase text-amber-600 dark:text-amber-400 hover:underline flex items-center gap-1"
          >
            <span>{isAr ? "العودة للمدونة" : "Back to Blog"}</span>
            {isAr ? <ArrowLeft className="w-3.5 h-3.5" /> : <ArrowRight className="w-3.5 h-3.5" />}
          </Link>
        </div>

        {/* Top Neobrutalist Callout Card */}
        <div className="p-6 mb-10 bg-amber-300 dark:bg-amber-500/20 border-2 border-black dark:border-white shadow-[5px_5px_0px_0px_#000] dark:shadow-[5px_5px_0px_0px_#fff] flex flex-col sm:flex-row items-center justify-between gap-6">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-black text-amber-400 border border-black hidden sm:flex shrink-0">
              <Zap className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-black text-black dark:text-white text-base sm:text-lg">
                {isAr ? "تداول بذكاء في البورصة المصرية" : "Trade Smart on the Egyptian Exchange"}
              </h3>
              <p className="text-xs sm:text-sm text-zinc-900 dark:text-zinc-200 mt-1 font-medium leading-relaxed">
                {isAr
                  ? "امسح أكثر من 200 سهم مصري واكتشف إشارات التجميع والدعم والمقاومة والسيولة لحظياً."
                  : "Scan 200+ Egyptian stocks and uncover real-time accumulation and volume signals."}
              </p>
            </div>
          </div>

          <Link
            href="/scanner/ai"
            className="whitespace-nowrap px-6 py-3 bg-black text-white hover:bg-zinc-800 dark:bg-white dark:text-black dark:hover:bg-zinc-200 font-black text-sm border-2 border-black dark:border-white shadow-[3px_3px_0px_0px_#f59e0b] transition-all flex items-center gap-2 shrink-0"
          >
            <span>{isAr ? "فتح الرادار مجاناً" : "Open Radar Free"}</span>
            {isAr ? <ArrowLeft className="w-4 h-4" /> : <ArrowRight className="w-4 h-4" />}
          </Link>
        </div>

        {/* Main Article Content Container */}
        <div className="p-6 sm:p-10 bg-white dark:bg-zinc-900 border-2 border-black dark:border-white shadow-[6px_6px_0px_0px_#000] dark:shadow-[6px_6px_0px_0px_#fff] mb-12">
          <article
            className="article-content space-y-6 text-zinc-900 dark:text-zinc-100 text-sm sm:text-base leading-relaxed
              [&>h3]:text-lg sm:[&>h3]:text-xl [&>h3]:font-black [&>h3]:text-black dark:[&>h3]:text-white [&>h3]:mt-8 [&>h3]:mb-3 [&>h3]:border-b-2 [&>h3]:border-black dark:[&>h3]:border-white [&>h3]:pb-1 [&>h3]:inline-block
              [&>p]:leading-loose [&>p]:text-zinc-800 dark:[&>p]:text-zinc-200
              [&>ul]:space-y-2.5 [&>ul]:pr-6 [&>ul]:list-disc [&>ul]:text-zinc-800 dark:[&>ul]:text-zinc-200
              [&>ol]:space-y-2.5 [&>ol]:pr-6 [&>ol]:list-decimal [&>ol]:text-zinc-800 dark:[&>ol]:text-zinc-200"
            dangerouslySetInnerHTML={{ __html: contentHtml }}
          />
        </div>

        {/* FAQ Section */}
        <div className="p-6 sm:p-8 bg-white dark:bg-zinc-900 border-2 border-black dark:border-white shadow-[6px_6px_0px_0px_#000] dark:shadow-[6px_6px_0px_0px_#fff] mb-12">
          <div className="flex items-center gap-3 mb-6 border-b-2 border-black dark:border-white pb-3">
            <HelpCircle className="w-6 h-6 text-amber-500" />
            <h2 className="text-xl sm:text-2xl font-black text-black dark:text-white">
              {isAr ? "الأسئلة الشائعة" : "Frequently Asked Questions"}
            </h2>
          </div>

          <div className="space-y-4">
            {article.faqs.map((faq, idx) => {
              const q = faq.question[isAr ? "ar" : "en"];
              const a = faq.answer[isAr ? "ar" : "en"];
              const isOpen = openFaq === idx;

              return (
                <div
                  key={idx}
                  className="border-2 border-black dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800 shadow-[3px_3px_0px_0px_#000] dark:shadow-[3px_3px_0px_0px_#27272a] overflow-hidden"
                >
                  <button
                    onClick={() => toggleFaq(idx)}
                    className="w-full p-4 text-start font-black text-sm sm:text-base flex items-center justify-between gap-4 text-zinc-950 dark:text-zinc-100 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700/80 transition-colors"
                  >
                    <span className="text-zinc-950 dark:text-zinc-100 font-bold">{q}</span>
                    {isOpen ? (
                      <ChevronUp className="w-5 h-5 text-amber-500 shrink-0" />
                    ) : (
                      <ChevronDown className="w-5 h-5 text-zinc-600 dark:text-zinc-400 shrink-0" />
                    )}
                  </button>
                  {isOpen && (
                    <div className="p-4 pt-3 text-xs sm:text-sm text-zinc-800 dark:text-zinc-200 leading-relaxed border-t-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-900">
                      {a}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Bottom CTA Conversion Box */}
        <div className="p-8 sm:p-12 bg-amber-400 dark:bg-amber-500 border-4 border-black text-black shadow-[8px_8px_0px_0px_#000] text-center">
          <TrendingUp className="w-12 h-12 mx-auto mb-4 text-black stroke-[2.5]" />
          <h2 className="text-2xl sm:text-3xl font-black tracking-tight mb-3 uppercase">
            {isAr ? "جاهز للتداول بقرارات مدروسة في البورصة المصرية؟" : "Ready to Trade with Precision on EGX?"}
          </h2>
          <p className="text-sm sm:text-base font-bold text-zinc-900 max-w-xl mx-auto mb-8 leading-relaxed">
            {isAr
              ? "انضم لمئات المتداولين الذين يعتمدون على الذكاء الاصطناعي لرصد السيولة والصفقات اللحظية في السوق المصري."
              : "Join hundreds of traders leveraging quantitative AI algorithms to track institutional liquidity and breakouts."}
          </p>

          <div className="flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/scanner/ai"
              className="px-8 py-3.5 bg-black text-white hover:bg-zinc-800 font-black text-base border-2 border-black shadow-[4px_4px_0px_0px_#fff] transition-all"
            >
              {isAr ? "جرب الرادار الآن مجاناً" : "Try Radar Free Now"}
            </Link>
            <Link
              href="/pricing"
              className="px-8 py-3.5 bg-white text-black hover:bg-zinc-100 font-black text-base border-2 border-black shadow-[4px_4px_0px_0px_#000] transition-all"
            >
              {isAr ? "باقات البرمجيات وتنبيهات تليجرام" : "SaaS Plans & Telegram Alerts"}
            </Link>
          </div>
        </div>

        {/* Mandatory FRA Regulatory Disclaimer */}
        <div className="mt-8 p-4 border-2 border-zinc-300 dark:border-zinc-700 bg-zinc-100/80 dark:bg-zinc-900/80 text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed text-center font-medium">
          {isAr
            ? "⚠️ تنويه هام: مخرجات النماذج الكمية والخوارزميات المعروضة على منصة EGX BOTS هي مؤشرات فنية وإحصائية عامة لأغراض الدراسة والبحث فقط، ولا تمثل توصية استثمارية أو دعوة للشراء أو البيع. قرار التداول مسؤوليتك المستقلة عبر شركة سمسرة مرخصة من الهيئة العامة للرقابة المالية."
            : "⚠️ Legal Disclaimer: All quantitative models and algorithmic outputs on EGX BOTS are general technical and statistical indicators for educational and research purposes only, and do not constitute investment advice or a solicitation to buy or sell. Trading decisions are your sole responsibility through an FRA-licensed brokerage."}
        </div>
      </div>
    </div>
  );
}
