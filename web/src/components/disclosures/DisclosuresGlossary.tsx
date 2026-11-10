"use client";

import React, { useState } from "react";
import {
  HelpCircle,
  ChevronDown,
  BookOpen,
  PieChart,
  Target,
  TrendingDown,
  TrendingUp,
  FileCheck,
  Users,
  Shield,
  Layers,
  Sparkles,
} from "lucide-react";

interface DisclosuresGlossaryProps {
  isAr: boolean;
}

export default function DisclosuresGlossary({ isAr }: DisclosuresGlossaryProps) {
  const [isOpen, setIsOpen] = useState(true);

  const terms = [
    {
      id: "free_float",
      icon: <PieChart className="w-5 h-5 text-amber-500 shrink-0" />,
      title_ar: "الأسهم الحرة للتداول (Free Float)",
      title_en: "Free Float Shares",
      badge_ar: "هيكل السيولة",
      badge_en: "Liquidity Structure",
      desc_ar:
        "نسبة وعدد أسهم الشركة المتاحة للتداول الفعلي اليومي في البورصة بين عموم المستثمرين، بعد استبعاد حصص المؤسسين والمساهمين الاستراتيجيين (من يملكون 5% فأكثر) والأسهم المجمدة أو المحتجزة لضمان العضوية.\n\n• السهم الخفيف (Free Float أقل من 20%): أسهمه الحرة قليلة ويسهل على كبار المضاربين تحريكه وصعوده السريع لنقص المعروض.\n• السهم المؤسسي الثقيل (Free Float أكثر من 50%): أسهمه الحرة وفيرة ويتطلب سيولة ضخمة لتحريكه وتغلب عليه تعاملات الصناديق والمؤسسات.",
      desc_en:
        "The percentage and number of shares readily available for open market trading among public investors, excluding locked founders' stakes (>=5%) and strategic holdings. Low float stocks (<20%) exhibit higher volatility and faster price movements.",
    },
    {
      id: "insider_vwap",
      icon: <Target className="w-5 h-5 text-emerald-500 shrink-0" />,
      title_ar: "متوسط تكلفة الداخلي (Insider VWAP)",
      title_en: "Insider VWAP Cost",
      badge_ar: "تكلفة صانع السهم",
      badge_en: "Smart Money Cost",
      desc_ar:
        "متوسط السعر المرجح بالكميات (Volume-Weighted Average Price) لعمليات الشراء التي نفذها أعضاء مجلس الإدارة أو الإدارة العليا أو المجموعات المرتبطة خلال الفترة. يمثل هذا الرقم 'خط التكلفة الحقيقي' لصانع السهم وأصحاب الشركة.",
      desc_en:
        "Volume-Weighted Average Price of purchase orders executed by board members, executives, or related parties. It serves as the institutional baseline cost of company insiders.",
    },
    {
      id: "discount_to_cost",
      icon: <Sparkles className="w-5 h-5 text-yellow-500 shrink-0" />,
      title_ar: "الفارق عن تكلفة الداخلي (الخصم الاستثنائي والعلاوة)",
      title_en: "Discount to Insider Cost",
      badge_ar: "فرصة ذهبية",
      badge_en: "Value Opportunity",
      desc_ar:
        "النسبة المئوية للفرق بين سعر تداول السهم اللحظي في السوق ومتوسط تكلفة شراء الداخليين:\n\n• الخصم (رقم سالب باللون الأخضر مثل -7.1%): فرصة استثنائية تعني أن السهم يتداول بأقل من تكلفة شراء أصحاب الشركة أنفسهم ('السهم أرخص من أصحابه') مما يمنح المستثمر هامش أمان جذاب.\n• العلاوة (رقم موجب مثل +5%): السهم ارتفع بالفعل ويتداول بسعر أعلى من تكلفة دخول الداخليين.",
      desc_en:
        "Percentage variance between current market price and insider purchase VWAP. Negative values indicate a rare opportunity where the stock trades below the insiders' own purchase cost (margin of safety).",
    },
    {
      id: "article_30",
      icon: <FileCheck className="w-5 h-5 text-purple-500 shrink-0" />,
      title_ar: "نماذج المادة (30) — هيكل كبار المساهمين",
      title_en: "Article (30) Filings — Ownership Structure",
      badge_ar: "إفصاح قانوني دوري",
      badge_en: "Regulatory Filing",
      desc_ar:
        "إفصاحات دورية إلزامية بموجب قواعد قيد الأوراق المالية بالبورصة المصرية والهيئة العامة للرقابة المالية (FRA)، للإعلان عن هيكل ملكية كبار المساهمين الذين يملكون 5% فأكثر من رأسمال الشركة وحصص مجالس الإدارة ونسبة التداول الحر.\n\n⚠️ تنبيه هام: الأرقام الضخمة في هذا الإفصاح (مثل 700 مليون سهم أو 10 مليار ج.م) تمثل إجمالي الحصة المملوكة للمؤسس أو الصندوق في الشركة، وليست صفقات تداول يومية جديدة.",
      desc_en:
        "Mandatory periodic disclosures under EGX listing rules detailing ownership structures for shareholders holding 5%+ of capital and free float percentages. Total shares in these filings reflect cumulative stake holdings, not daily trading orders.",
    },
    {
      id: "insiders",
      icon: <Users className="w-5 h-5 text-blue-500 shrink-0" />,
      title_ar: "المطلعون والداخليون (Corporate Insiders)",
      title_en: "Corporate Insiders",
      badge_ar: "أطراف مرتبطة",
      badge_en: "Connected Parties",
      desc_ar:
        "يشمل هذا المصطلح رئيس وأعضاء مجلس الإدارة، والمديرين التنفيذيين، والمجموعات المرتبطة بهم، وأقاربهم حتى الدرجة الثانية. يتميز هؤلاء باطلاعهم على الخطط الاستراتيجية ونتائج الأعمال قبل إعلانها للجمهور، لذلك تعتبر تعاملاتهم بالبيع والشراء أدق بوصلة لتحديد اتجاه السهم.",
      desc_en:
        "Board members, top executives, and affiliated groups who possess material non-public insights into company operations. Their buying and selling actions serve as a vital gauge of internal corporate confidence.",
    },
    {
      id: "silent_accumulation",
      icon: <TrendingUp className="w-5 h-5 text-emerald-600 shrink-0" />,
      title_ar: "التجميع الصامت (Silent Accumulation)",
      title_en: "Silent Accumulation",
      badge_ar: "إشارة قاع",
      badge_en: "Bottoming Signal",
      desc_ar:
        "عمليات شراء متكررة ومتتالية يقوم بها المطلعون أو المساهم الرئيسي بكميات محسوبة على مدار عدة جلسات دون إحداث ضجيج أو قفزات سعرية مفاجئة، مما يدل على بناء مراكز استثمارية هادئة تمهيداً لانطلاقة صاعدة متوقعة أو نتائج أعمال قوية.",
      desc_en:
        "Successive, measured purchase orders executed by insiders over multiple sessions without driving prices sharply, indicating institutional position building ahead of positive catalysts.",
    },
    {
      id: "distribution",
      icon: <TrendingDown className="w-5 h-5 text-rose-600 shrink-0" />,
      title_ar: "التصريف والضغط البيعي (Distribution)",
      title_en: "Insider Distribution",
      badge_ar: "إشارة حذر",
      badge_en: "Caution Signal",
      desc_ar:
        "سلسلة مبيعات متتالية ينفذها المطلعون لتسييل جزء من أسهمهم أو جني الأرباح، وغالباً ما تتزامن مع قمم سعرية أو صعود قوي للسهم. استمرار البيع المتتالي يعتبر إشارة تحذيرية تستدعي مراجعة مستويات وقف الخسارة.",
      desc_en:
        "Successive selling operations by insiders taking profits near market peaks or high valuations, signaling potential downward pressure and warranting tighter risk management.",
    },
    {
      id: "net_flow",
      icon: <Layers className="w-5 h-5 text-teal-500 shrink-0" />,
      title_ar: "صافي تدفق سيولة الداخليين (Net Insider Flow)",
      title_en: "Net Insider Liquidity Flow",
      badge_ar: "ميزان السيولة",
      badge_en: "Liquidity Balance",
      desc_ar:
        "الفارق الصافي بين إجمالي القيمة النقدية لمشتريات الداخليين مطروحاً منها إجمالي مبيعاتهم بالجنيه المصري (مشتريات - مبيعات) خلال فترة محددة (اليوم / 7 أيام / 30 يوماً / 90 يوماً). إذا كان الرقم موجباً فالسيولة تجميعية، وإذا كان سالباً فالسيولة بيعية.",
      desc_en:
        "Net difference between total insider buy value and total insider sell value in EGP over a given timeframe (today / 7d / 30d / 90d), reflecting whether net smart money is entering or leaving the stock.",
    },
  ];

  return (
    <section
      id="glossary"
      className="mt-12 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 sm:p-7 shadow-[8px_8px_0px_#000] dark:shadow-[8px_8px_0px_#fff] text-black dark:text-white transition-colors"
    >
      {/* Glossary Header with Toggle */}
      <div className="flex items-center justify-between border-b-4 border-black dark:border-white pb-4 mb-6">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center bg-[#FFE600] text-black border-2 border-black shadow-[2px_2px_0px_#000]">
            <BookOpen className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base sm:text-xl font-black text-black dark:text-white uppercase tracking-tight flex items-center gap-2">
              <span>{isAr ? "دليل مفاهيم ومصطلحات رادار الإفصاحات وتعاملات الداخليين" : "Disclosures & Insider Trading Financial Glossary"}</span>
            </h2>
            <span className="text-xs font-bold text-zinc-600 dark:text-zinc-400 block mt-0.5">
              {isAr
                ? "دليلك الشامل لفهم مؤشرات البورصة المصرية، نماذج المادة 30، وحسابات الأسهم الحرة وتكلفة صانع السهم"
                : "Comprehensive guide to EGX disclosures, Article 30 filings, free float math, and Smart Money metrics"}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-black border-2 border-black bg-zinc-100 dark:bg-zinc-800 hover:bg-[#FFE600] hover:text-black dark:hover:bg-[#FFE600] dark:hover:text-black shadow-[2px_2px_0px_#000] cursor-pointer transition-colors"
          aria-expanded={isOpen}
        >
          <span>{isOpen ? (isAr ? "طي الدليل" : "Collapse") : (isAr ? "عرض الدليل" : "Expand")}</span>
          <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
        </button>
      </div>

      {/* Terms Grid */}
      {isOpen && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {terms.map((t) => (
            <div
              key={t.id}
              className="p-4 border-3 border-black dark:border-white/30 bg-zinc-50 dark:bg-zinc-900/80 shadow-[3px_3px_0px_#000] dark:shadow-[3px_3px_0px_rgba(255,255,255,0.2)] hover:border-amber-500 transition-colors"
            >
              <div className="flex items-center justify-between gap-2 mb-2 border-b border-black/10 dark:border-white/10 pb-2">
                <div className="flex items-center gap-2 min-w-0">
                  {t.icon}
                  <h3 className="font-black text-sm sm:text-base text-black dark:text-white truncate">
                    {isAr ? t.title_ar : t.title_en}
                  </h3>
                </div>
                <span className="shrink-0 px-2 py-0.5 text-[10px] font-black uppercase tracking-wider bg-[#FFE600] text-black border border-black shadow-[1px_1px_0px_#000]">
                  {isAr ? t.badge_ar : t.badge_en}
                </span>
              </div>
              <p className="text-xs sm:text-[13px] font-medium text-zinc-800 dark:text-zinc-200 leading-relaxed whitespace-pre-line">
                {isAr ? t.desc_ar : t.desc_en}
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
