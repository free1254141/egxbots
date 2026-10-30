"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Layers,
  Zap,
  TrendingUp,
  Target,
  ShieldAlert,
  Award,
  Scale,
  ShieldCheck,
  BarChart3
} from "lucide-react";

interface SystemsComparisonTabProps {
  isAr?: boolean;
  isPro?: boolean;
}

export default function SystemsComparisonTab({
  isAr = true,
  isPro = false
}: SystemsComparisonTabProps) {
  const [selectedPeriod, setSelectedPeriod] = useState<"august" | "september" | "full_year">("full_year");

  // Performance data per period across all 3 algorithmic systems (FRA-compliant terminology)
  const periodData = {
    august: {
      titleAr: "شهر أغسطس (شهر زخم وصعود قوي)",
      titleEn: "August 2026 (Strong Bullish Momentum)",
      medium: {
        winRate: 78.0,
        totalReturn: 1208.3,
        tradeCount: 41,
        avgHolding: "29.5 يوم",
        bestTrade: "CRST +143.2%",
        profitFactor: 3.85,
        summaryAr: "شهر استثنائي حققت فيه إشارات المدى المتوسط طفرات قياسية بقيادة سهم CRST (+143.2%)، مع نسبة تحقق 78% ومجموع عوائد موثق بالتقويم بلغ +1208.3%."
      },
      short: {
        winRate: 58.3,
        totalReturn: 493.2,
        tradeCount: 115,
        avgHolding: "2.8 جلسات",
        bestTrade: "EDBM +81.5% و GGCC +71.0%",
        profitFactor: 3.04,
        summaryAr: "كثافة عالية في رصد الفرص الفنية (115 إشارة سريعة)؛ حقق النظام +493.2% مع قفزات وصلت إلى +81.5% عبر تتبع موجات الزخم ومتوسط EMA10."
      },
      fast: {
        winRate: 74.5,
        totalReturn: 186.4,
        tradeCount: 52,
        avgHolding: "1.6 جلسة",
        bestTrade: "FWRY +6.0% و ABUK +5.8%",
        profitFactor: 3.92,
        summaryAr: "رصد لحظي عالي الدقة على فريم 15 دقيقة؛ التقط تدفقات السيولة المؤسسية والاختراقات السريعة بمعدل تحقق أهداف 74.5% وتأمين فوري لنقطة التعادل."
      }
    },
    september: {
      titleAr: "شهر سبتمبر (سوق تصحيحي وهابط)",
      titleEn: "September 2026 (Correction & Bearish Pressure)",
      medium: {
        winRate: 36.1,
        totalReturn: -66.3,
        tradeCount: 61,
        avgHolding: "25.0 يوم",
        bestTrade: "KASABF +101.4%",
        profitFactor: 0.82,
        summaryAr: "تأثرت إشارات المدى المتوسط بالهبوط العام للمؤشر وتفعيل مستويات إيقاف الخسارة الأوسع (-8% إلى -12%)، رغم رصد طفرة KASABF القياسية (+101.4%)."
      },
      short: {
        winRate: 40.8,
        totalReturn: -74.9,
        tradeCount: 71,
        avgHolding: "3.1 جلسات",
        bestTrade: "KORA +19.4% و CERA +19.6%",
        profitFactor: 0.69,
        summaryAr: "حدّ النظام من التراجعات بفضل مستوى الوقف الصارم (-4%) وتأمين نقطة الرصد عند +4.5%، مع إغلاق سريع في أقل من 3 جلسات لتحرير السيولة."
      },
      fast: {
        winRate: 62.5,
        totalReturn: 34.2,
        tradeCount: 24,
        avgHolding: "1.4 جلسة",
        bestTrade: "ELNA +4.9% و TMGH +4.5%",
        profitFactor: 2.45,
        summaryAr: "تفوق دفاعي واضح أثناء هبوط السوق بفضل فلتر اتساع السوق (Market Breadth Gate) وتأمين التعادل الذكي عند +2.5% وتركيز الرصد على ارتدادات RSI العميقة."
      }
    },
    full_year: {
      titleAr: "إجمالي عام 2026 (كامل العينة التاريخية)",
      titleEn: "Full 2026 Backtest (Complete Sample)",
      medium: {
        winRate: 58.1,
        totalReturn: 1379.5,
        tradeCount: 136,
        avgHolding: "28.0 يوم",
        bestTrade: "CRST +143.2%",
        profitFactor: 2.65,
        summaryAr: "منهجية فنية تراكمية قوية للمتابع متوسط المدى؛ حققت عائداً تراكمياً يتجاوز +1379.5% على مدار العام دون حاجة لمتابعة الشاشة لحظة بلحظة."
      },
      short: {
        winRate: 55.0,
        totalReturn: 1002.2,
        tradeCount: 511,
        avgHolding: "2.9 جلسات",
        bestTrade: "EDBM +81.5% و GGCC +71.0%",
        profitFactor: 1.95,
        summaryAr: "محرك زخم فني عالي الكفاءة يضاعف سرعة دوران السيولة (511 إشارة قصيرة) ويحقق عائداً تراكمياً (+1002.2%) مع أفق متابعة أقل من 3 جلسات."
      },
      fast: {
        winRate: 70.0,
        totalReturn: 312.8,
        tradeCount: 95,
        avgHolding: "1.5 جلسة",
        bestTrade: "breakout +6.0% و ELNA +4.98%",
        profitFactor: 4.03,
        summaryAr: "رادار لحظي على فريم 15 دقيقة يفحص السوق كل 5 دقائق؛ يتميز بأعلى نسبة تحقق أهداف (70.0%) وأعلى عامل ربح (4.03x) بفضل تأمين التعادل الآلي عند +2.5%."
      }
    }
  };

  const current = periodData[selectedPeriod];

  return (
    <div className="space-y-6" dir={isAr ? "rtl" : "ltr"}>
      {/* ── 1. Header Banner (Neo-Brutalist) ── */}
      <div className="border-4 border-black dark:border-white bg-[#FFE600] text-black p-5 sm:p-6 shadow-[5px_5px_0px_#000] dark:shadow-[5px_5px_0px_#fff]">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 border-3 border-black bg-white flex items-center justify-center font-black text-black shadow-[2px_2px_0px_#000]">
              <Scale className="w-6 h-6" />
            </div>
            <div>
              <span className="text-[10px] font-black uppercase tracking-wider bg-black text-[#FFE600] px-2 py-0.5 border border-black inline-block mb-1">
                {isAr ? "دليل المقارنة الفنية والكمية للأنظمة الثلاثة" : "3-Systems Quantitative & Technical Comparison"}
              </span>
              <h2 className="text-xl sm:text-2xl font-black">
                {isAr
                  ? "مقارنة الأنظمة الثلاثة: المدى المتوسط 📈 vs المدى القصير ⚡ vs الرصد اللحظي 🎯"
                  : "3-Systems Comparison: Medium-Term 📈 vs Short-Term ⚡ vs Intraday Fast 🎯"}
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {!isPro && (
              <Link
                href="/pricing"
                className="inline-flex items-center gap-1.5 px-4 py-2 border-2 border-black bg-black text-[#FFE600] text-xs font-black shadow-[2px_2px_0px_#000] hover:bg-zinc-800 transition-all"
              >
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>{isAr ? "فتح كافة الأنظمة فوراً (PRO)" : "Unlock All Systems (PRO)"}</span>
              </Link>
            )}
          </div>
        </div>

        <p className="mt-3 text-xs sm:text-sm font-bold text-zinc-900 leading-relaxed border-t-2 border-black/20 pt-3">
          {isAr
            ? "يوفر EGX BOTS ثلاثة أنظمة رصد خوارزمية متكاملة في البورصة المصرية تتفق في أدوات التحليل وتتكامل في الأفق الزمني: إشارات المدى المتوسط (2–6 أسابيع)، وإشارات المدى القصير (3–10 جلسات)، وإشارات الرصد اللحظي السريع على فريم 15 دقيقة (1–4 جلسات)."
            : "EGX BOTS provides three complementary algorithmic technical scanning systems across different time horizons: Medium-Term (2–6 weeks), Short-Term (3–10 sessions), and Intraday Fast Radar on 15m candles (1–4 sessions)."}
        </p>
      </div>

      {/* ── 2. Period Selector Buttons ── */}
      <div className="flex flex-wrap items-center gap-2 border-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900 p-1.5 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff]">
        <button
          onClick={() => setSelectedPeriod("full_year")}
          className={`flex-1 sm:flex-none py-2.5 px-4 border-2 border-black font-black text-xs sm:text-sm flex items-center justify-center gap-2 transition-all cursor-pointer ${
            selectedPeriod === "full_year"
              ? "bg-[#FFE600] text-black shadow-[2px_2px_0px_#000]"
              : "bg-white dark:bg-zinc-950 text-black dark:text-white hover:bg-zinc-200 dark:hover:bg-zinc-800"
          }`}
        >
          <Award className="w-4 h-4 text-black dark:text-amber-400" />
          <span>{isAr ? "كامل عام 2026 (العينة الإجمالية)" : "Full Year 2026"}</span>
        </button>

        <button
          onClick={() => setSelectedPeriod("august")}
          className={`flex-1 sm:flex-none py-2.5 px-4 border-2 border-black font-black text-xs sm:text-sm flex items-center justify-center gap-2 transition-all cursor-pointer ${
            selectedPeriod === "august"
              ? "bg-[#FFE600] text-black shadow-[2px_2px_0px_#000]"
              : "bg-white dark:bg-zinc-950 text-black dark:text-white hover:bg-zinc-200 dark:hover:bg-zinc-800"
          }`}
        >
          <TrendingUp className="w-4 h-4 text-emerald-600" />
          <span>{isAr ? "شهر أغسطس 2026 (سوق صاعد قوي)" : "August 2026 (Bull Market)"}</span>
        </button>

        <button
          onClick={() => setSelectedPeriod("september")}
          className={`flex-1 sm:flex-none py-2.5 px-4 border-2 border-black font-black text-xs sm:text-sm flex items-center justify-center gap-2 transition-all cursor-pointer ${
            selectedPeriod === "september"
              ? "bg-[#FFE600] text-black shadow-[2px_2px_0px_#000]"
              : "bg-white dark:bg-zinc-950 text-black dark:text-white hover:bg-zinc-200 dark:hover:bg-zinc-800"
          }`}
        >
          <ShieldAlert className="w-4 h-4 text-rose-600" />
          <span>{isAr ? "شهر سبتمبر 2026 (سوق تصحيحي وهابط)" : "September 2026 (Correction)"}</span>
        </button>
      </div>

      {/* ── 3. Head-to-Head 3-Systems Period Scorecard ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Card 1: إشارات المدى المتوسط */}
        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between border-b-2 border-black pb-3">
              <div className="flex items-center gap-2">
                <span className="w-8 h-8 border-2 border-black bg-blue-400 text-black flex items-center justify-center font-black">
                  <Layers className="w-4 h-4" />
                </span>
                <div>
                  <h3 className="font-black text-base text-black dark:text-white">إشارات المدى المتوسط 📈</h3>
                  <span className="text-[11px] font-bold text-zinc-500">تحليل الاتجاه الفني (2 - 6 أسابيع)</span>
                </div>
              </div>
              <span className="text-xs font-black px-2 py-0.5 border border-black bg-zinc-100 dark:bg-zinc-800 text-black dark:text-white">
                {current.medium.tradeCount} إشارة
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2.5 my-4">
              <div className="p-3 border-2 border-black bg-zinc-50 dark:bg-zinc-900">
                <span className="text-[10px] font-bold text-zinc-500 block">نسبة تحقق الأهداف</span>
                <span className="text-lg font-black font-mono text-black dark:text-white" dir="ltr">
                  {current.medium.winRate.toFixed(1)}%
                </span>
              </div>

              <div className="p-3 border-2 border-black bg-zinc-50 dark:bg-zinc-900">
                <span className="text-[10px] font-bold text-zinc-500 block">مجموع عوائد الإشارات</span>
                <span
                  className={`text-lg font-black font-mono ${
                    current.medium.totalReturn >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
                  }`}
                  dir="ltr"
                >
                  {current.medium.totalReturn >= 0 ? "+" : ""}{current.medium.totalReturn.toFixed(1)}%
                </span>
              </div>

              <div className="p-3 border-2 border-black bg-zinc-50 dark:bg-zinc-900">
                <span className="text-[10px] font-bold text-zinc-500 block">عامل الربح (PF)</span>
                <span className="text-lg font-black font-mono text-black dark:text-white">
                  {current.medium.profitFactor.toFixed(2)}x
                </span>
              </div>

              <div className="p-3 border-2 border-black bg-zinc-50 dark:bg-zinc-900">
                <span className="text-[10px] font-bold text-zinc-500 block">متوسط مدة المتابعة</span>
                <span className="text-sm font-black text-black dark:text-white">
                  {current.medium.avgHolding}
                </span>
              </div>

              <div className="p-3 border-2 border-black bg-zinc-50 dark:bg-zinc-900 col-span-2">
                <span className="text-[10px] font-bold text-zinc-500 block">أبرز إشارة رابحة</span>
                <span className="text-sm font-black text-emerald-600 dark:text-emerald-400 truncate block" dir="ltr">
                  {current.medium.bestTrade}
                </span>
              </div>
            </div>
          </div>

          <p className="text-xs font-bold text-zinc-700 dark:text-zinc-300 bg-blue-50 dark:bg-blue-950/30 p-3 border-2 border-blue-400">
            📈 <strong>تحليل الفترة:</strong> {current.medium.summaryAr}
          </p>
        </div>

        {/* Card 2: إشارات المدى القصير */}
        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between border-b-2 border-black pb-3">
              <div className="flex items-center gap-2">
                <span className="w-8 h-8 border-2 border-black bg-[#FFE600] text-black flex items-center justify-center font-black">
                  <Zap className="w-4 h-4" />
                </span>
                <div>
                  <h3 className="font-black text-base text-black dark:text-white">إشارات المدى القصير ⚡</h3>
                  <span className="text-[11px] font-bold text-amber-600 dark:text-amber-400">رصد الزخم الفني (3 - 10 جلسات)</span>
                </div>
              </div>
              <span className="text-xs font-black px-2 py-0.5 border-2 border-black bg-[#FFE600] text-black">
                {current.short.tradeCount} إشارة
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2.5 my-4">
              <div className="p-3 border-2 border-black bg-amber-500/10 border-amber-500/40">
                <span className="text-[10px] font-bold text-zinc-500 block">نسبة تحقق الأهداف</span>
                <span className="text-lg font-black font-mono text-emerald-600 dark:text-emerald-400" dir="ltr">
                  {current.short.winRate.toFixed(1)}%
                </span>
              </div>

              <div className="p-3 border-2 border-black bg-amber-500/10 border-amber-500/40">
                <span className="text-[10px] font-bold text-zinc-500 block">مجموع عوائد الإشارات</span>
                <span
                  className={`text-lg font-black font-mono ${
                    current.short.totalReturn >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
                  }`}
                  dir="ltr"
                >
                  {current.short.totalReturn >= 0 ? "+" : ""}{current.short.totalReturn.toFixed(1)}%
                </span>
              </div>

              <div className="p-3 border-2 border-black bg-amber-500/10 border-amber-500/40">
                <span className="text-[10px] font-bold text-zinc-500 block">عامل الربح (PF)</span>
                <span className="text-lg font-black font-mono text-black dark:text-white">
                  {current.short.profitFactor.toFixed(2)}x
                </span>
              </div>

              <div className="p-3 border-2 border-black bg-amber-500/10 border-amber-500/40">
                <span className="text-[10px] font-bold text-zinc-500 block">متوسط مدة المتابعة</span>
                <span className="text-sm font-black text-black dark:text-white">
                  {current.short.avgHolding}
                </span>
              </div>

              <div className="p-3 border-2 border-black bg-amber-500/10 border-amber-500/40 col-span-2">
                <span className="text-[10px] font-bold text-zinc-500 block">أبرز إشارة رابحة</span>
                <span className="text-sm font-black text-emerald-600 dark:text-emerald-400 truncate block" dir="ltr">
                  {current.short.bestTrade}
                </span>
              </div>
            </div>
          </div>

          <p className="text-xs font-bold text-zinc-900 dark:text-zinc-100 bg-amber-200/60 dark:bg-amber-950/40 p-3 border-2 border-amber-500">
            ⚡ <strong>ميزة الزخم القصير:</strong> {current.short.summaryAr}
          </p>
        </div>

        {/* Card 3: إشارات الرصد اللحظي */}
        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between border-b-2 border-black pb-3">
              <div className="flex items-center gap-2">
                <span className="w-8 h-8 border-2 border-black bg-emerald-400 text-black flex items-center justify-center font-black">
                  <Target className="w-4 h-4" />
                </span>
                <div>
                  <h3 className="font-black text-base text-black dark:text-white">إشارات الرصد اللحظي 🎯</h3>
                  <span className="text-[11px] font-bold text-emerald-600 dark:text-emerald-400">رادار السيولة السريع (1 - 4 جلسات)</span>
                </div>
              </div>
              <span className="text-xs font-black px-2 py-0.5 border-2 border-black bg-emerald-400 text-black">
                {current.fast.tradeCount} إشارة
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2.5 my-4">
              <div className="p-3 border-2 border-black bg-emerald-500/10 border-emerald-500/40">
                <span className="text-[10px] font-bold text-zinc-500 block">نسبة تحقق الأهداف</span>
                <span className="text-lg font-black font-mono text-emerald-600 dark:text-emerald-400" dir="ltr">
                  {current.fast.winRate.toFixed(1)}%
                </span>
              </div>

              <div className="p-3 border-2 border-black bg-emerald-500/10 border-emerald-500/40">
                <span className="text-[10px] font-bold text-zinc-500 block">مجموع عوائد الإشارات</span>
                <span
                  className={`text-lg font-black font-mono ${
                    current.fast.totalReturn >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
                  }`}
                  dir="ltr"
                >
                  {current.fast.totalReturn >= 0 ? "+" : ""}{current.fast.totalReturn.toFixed(1)}%
                </span>
              </div>

              <div className="p-3 border-2 border-black bg-emerald-500/10 border-emerald-500/40">
                <span className="text-[10px] font-bold text-zinc-500 block">عامل الربح (PF)</span>
                <span className="text-lg font-black font-mono text-black dark:text-white">
                  {current.fast.profitFactor.toFixed(2)}x
                </span>
              </div>

              <div className="p-3 border-2 border-black bg-emerald-500/10 border-emerald-500/40">
                <span className="text-[10px] font-bold text-zinc-500 block">متوسط مدة المتابعة</span>
                <span className="text-sm font-black text-black dark:text-white">
                  {current.fast.avgHolding}
                </span>
              </div>

              <div className="p-3 border-2 border-black bg-emerald-500/10 border-emerald-500/40 col-span-2">
                <span className="text-[10px] font-bold text-zinc-500 block">أبرز إشارة رابحة</span>
                <span className="text-sm font-black text-emerald-600 dark:text-emerald-400 truncate block" dir="ltr">
                  {current.fast.bestTrade}
                </span>
              </div>
            </div>
          </div>

          <p className="text-xs font-bold text-zinc-900 dark:text-zinc-100 bg-emerald-200/60 dark:bg-emerald-950/40 p-3 border-2 border-emerald-500">
            🎯 <strong>ميزة الرصد اللحظي:</strong> {current.fast.summaryAr}
          </p>
        </div>
      </div>

      {/* ── 4. Deep Structural Comparison Table (All 3 Systems) ── */}
      <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 sm:p-6 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] space-y-4">
        <div className="flex items-center gap-2 border-b-2 border-black pb-3">
          <BarChart3 className="w-5 h-5 text-amber-500" />
          <h3 className="text-base sm:text-lg font-black text-black dark:text-white">
            جدول المقارنة الهيكلية وقواعد إدارة المخاطر للأنظمة الثلاثة
          </h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-start border-collapse border-2 border-black">
            <thead>
              <tr className="bg-zinc-900 text-white dark:bg-zinc-100 dark:text-black">
                <th className="p-3 border border-black font-black text-start">وجه المقارنة الفني</th>
                <th className="p-3 border border-black font-black text-start bg-blue-600/90 text-white">إشارات المدى المتوسط 📈</th>
                <th className="p-3 border border-black font-black text-start bg-[#FFE600] text-black">إشارات المدى القصير ⚡</th>
                <th className="p-3 border border-black font-black text-start bg-emerald-400 text-black">إشارات الرصد اللحظي 🎯</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-black font-bold text-zinc-800 dark:text-zinc-200">
              <tr className="hover:bg-zinc-50 dark:hover:bg-zinc-900/50">
                <td className="p-3 border border-black font-black bg-zinc-100 dark:bg-zinc-900 text-black dark:text-white">
                  ⏱️ أفق المتابعة الزمني
                </td>
                <td className="p-3 border border-black">2 إلى 6 أسابيع (متوسط 28 يوماً)</td>
                <td className="p-3 border border-black bg-amber-50 dark:bg-amber-950/20 text-black dark:text-white font-black">
                  3 إلى 10 جلسات (متوسط 2.9 جلسة)
                </td>
                <td className="p-3 border border-black bg-emerald-50 dark:bg-emerald-950/20 text-black dark:text-white font-black">
                  1 إلى 4 جلسات (فريم 15 دقيقة)
                </td>
              </tr>

              <tr className="hover:bg-zinc-50 dark:hover:bg-zinc-900/50">
                <td className="p-3 border border-black font-black bg-zinc-100 dark:bg-zinc-900 text-black dark:text-white">
                  🛡️ مستوى إيقاف الخسارة وتأمين التعادل
                </td>
                <td className="p-3 border border-black">-8% إلى -12% (وقف فني واسع لتحمل التذبذب)</td>
                <td className="p-3 border border-black bg-amber-50 dark:bg-amber-950/20 text-black dark:text-white font-black">
                  -4.0% صارم + تأمين التعادل عند +4.5%
                </td>
                <td className="p-3 border border-black bg-emerald-50 dark:bg-emerald-950/20 text-black dark:text-white font-black">
                  -2.8% إلى -3.5% + تأمين التعادل آلياً عند +2.5%
                </td>
              </tr>

              <tr className="hover:bg-zinc-50 dark:hover:bg-zinc-900/50">
                <td className="p-3 border border-black font-black bg-zinc-100 dark:bg-zinc-900 text-black dark:text-white">
                  🎯 منهجية المستهدفات الفنية
                </td>
                <td className="p-3 border border-black">مستهدفات سعرية مرحلية (مستهدف أول وثانٍ)</td>
                <td className="p-3 border border-black bg-amber-50 dark:bg-amber-950/20 text-black dark:text-white font-black">
                  تتبع موجات الصعود عبر الوقف المتحرك EMA10
                </td>
                <td className="p-3 border border-black bg-emerald-50 dark:bg-emerald-950/20 text-black dark:text-white font-black">
                  مستهدف فني سريع (+4.0% إلى +6.0%)
                </td>
              </tr>

              <tr className="hover:bg-zinc-50 dark:hover:bg-zinc-900/50">
                <td className="p-3 border border-black font-black bg-zinc-100 dark:bg-zinc-900 text-black dark:text-white">
                  🔍 المعادلة الخوارزمية والفلاتر
                </td>
                <td className="p-3 border border-black">نماذج فنية كلاسيكية + تقييم الذكاء الاصطناعي الشامل</td>
                <td className="p-3 border border-black bg-amber-50 dark:bg-amber-950/20 text-black dark:text-white font-black">
                  انفجار سيولة &gt;140% + اختراق قمة تماسك 20 جلسة
                </td>
                <td className="p-3 border border-black bg-emerald-50 dark:bg-emerald-950/20 text-black dark:text-white font-black">
                  3 ماسحات لحظية: سيولة (rVol≥2.2x)، اختراق BB، وارتداد RSI≤28
                </td>
              </tr>

              <tr className="hover:bg-zinc-50 dark:hover:bg-zinc-900/50">
                <td className="p-3 border border-black font-black bg-zinc-100 dark:bg-zinc-900 text-black dark:text-white">
                  📊 أدوات التحليل المتاحة بالمنصة
                </td>
                <td className="p-3 border border-black">شارت يومي + تقويم الأداء + تفسير الذكاء الاصطناعي + مشاركة</td>
                <td className="p-3 border border-black bg-amber-50 dark:bg-amber-950/20 text-black dark:text-white font-black">
                  شارت مسار EMA10 + تقويم الأداء + فلتر الشريعة + مشاركة
                </td>
                <td className="p-3 border border-black bg-emerald-50 dark:bg-emerald-950/20 text-black dark:text-white font-black">
                  شارت 15 دقيقة تفاعلي + تقويم الجلسات + فلتر الشريعة + مشاركة
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* ── 5. Integrated Portfolio Research Framework ── */}
      <div className="border-4 border-black dark:border-white bg-zinc-950 text-white p-5 sm:p-6 shadow-[5px_5px_0px_#000] dark:shadow-[5px_5px_0px_#fff] space-y-4">
        <div className="flex items-center gap-2 border-b border-zinc-800 pb-3">
          <ShieldCheck className="w-5 h-5 text-emerald-400" />
          <h3 className="text-base sm:text-lg font-black text-white">
            كيف تتكامل الأنظمة الثلاثة في تغطية كافة ظروف السوق؟
          </h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="border-2 border-zinc-700 bg-zinc-900 p-4 space-y-2">
            <span className="text-xs font-black text-blue-400 block uppercase">
              1. إشارات المدى المتوسط 📈 (الركيزة الاتجاهية)
            </span>
            <p className="text-xs text-zinc-300 font-bold leading-relaxed">
              تركز على الأسهم القيادية والواعدة ذات التقييم الأساسي والفني القوي لمتابعة الموجات السعرية الكبرى على مدى عدة أسابيع بهدوء.
            </p>
          </div>

          <div className="border-2 border-zinc-700 bg-zinc-900 p-4 space-y-2">
            <span className="text-xs font-black text-amber-400 block uppercase">
              2. إشارات المدى القصير ⚡ (محرك الزخم)
            </span>
            <p className="text-xs text-zinc-300 font-bold leading-relaxed">
              تلتقط الأسهم التي تخترق مناطق التجميع بسيولة مؤسسية كثيفة، وتتبع موجة الصعود عبر متوسط EMA10 بدون سقف للمستهدفات.
            </p>
          </div>

          <div className="border-2 border-zinc-700 bg-zinc-900 p-4 space-y-2">
            <span className="text-xs font-black text-emerald-400 block uppercase">
              3. إشارات الرصد اللحظي 🎯 (رادار الـ 15 دقيقة)
            </span>
            <p className="text-xs text-zinc-300 font-bold leading-relaxed">
              يراقب الجلسة كل 5 دقائق لرصد التدفقات اللحظية والارتدادات الفنية السريعة مع نقل الوقف لنقطة التعادل فور صعود +2.5%.
            </p>
          </div>
        </div>

        <p className="text-[11px] font-bold text-zinc-400 pt-2 border-t border-zinc-800">
          ⚠️ إخلاء مسؤولية تنظيمي (FRA): جميع الأرقام والإحصائيات التاريخية المعروضة هي نتائج اختبارات قياسية ورصد فني خوارزمي لأغراض البحث والدراسة العلمية، ولا تُعد نصيحة استثمارية أو ضماناً لتحقيق عوائد مستقبلية.
        </p>
      </div>
    </div>
  );
}
