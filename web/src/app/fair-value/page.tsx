import { Metadata } from "next";
import Link from "next/link";
import FairValueClient from "./FairValueClient";
import { getCachedFairValueReport } from "@/lib/market/fair-value-server";

export const revalidate = 604800;
export const preferredRegion = "fra1";

export const metadata: Metadata = {
  title: "السعر العادل ومؤشر الرخص للأسهم المصرية والسعودية (EGX & TASI)",
  description:
    "اكتشف أرخص أسهم البورصة المصرية (EGX) والسوق السعودي (تاسي TASI) يومياً ومقارنتها بالسعر العادل المحسوب بمعادلة بنجامين جراهام ومضاعفات الربحية والقيمة الدفترية والتوازن الكمي.",
  keywords: [
    "السعر العادل للأسهم المصرية",
    "السعر العادل للأسهم السعودية",
    "أرخص أسهم البورصة المصرية",
    "أرخص أسهم تاسي TASI",
    "مضاعف الربحية EGX TASI",
    "القيمة الدفترية للأسهم",
    "معادلة جراهام للأسهم",
    "EGX TASI Fair Value Screener",
    "Undervalued Saudi & Egyptian Stocks",
  ],
  alternates: {
    canonical: "https://egxbots.com/fair-value",
  },
  openGraph: {
    title: "السعر العادل ومؤشر الرخص للأسهم المصرية والسعودية | EGX BOTS",
    description:
      "فحص السعر العادل ومضاعفات الربحية والقيمة الدفترية لأسهم البورصة المصرية والسوق السعودي تاسي باستخدام النماذج الكمية.",
    url: "https://egxbots.com/fair-value",
    type: "website",
    images: [
      {
        url: "https://egxbots.com/opengraph-image.png",
        width: 1200,
        height: 630,
        alt: "السعر العادل للأسهم المصرية والسعودية - EGX BOTS",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "السعر العادل ومؤشر الرخص للأسهم المصرية والسعودية | EGX BOTS",
    description:
      "فحص السعر العادل ومضاعفات الربحية والقيمة الدفترية لأسهم البورصة المصرية والسوق السعودي تاسي.",
    images: ["https://egxbots.com/opengraph-image.png"],
  },
};

export default async function FairValuePage() {
  let initialReport = null;
  try {
    initialReport = await getCachedFairValueReport();
  } catch (err) {
    console.error("[FairValuePage] Failed to pre-fetch cached report:", err);
  }

  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "SoftwareApplication",
        "@id": "https://egxbots.com/fair-value#tool",
        name: "حاسبة السعر العادل ومؤشر الرخص للأسهم المصرية والسعودية",
        alternateName: ["EGX & TASI Fair Value Screener", "حاسبة السعر العادل"],
        applicationCategory: "FinanceApplication",
        operatingSystem: "Web",
        url: "https://egxbots.com/fair-value",
        description:
          "أداة مجانية لحساب السعر العادل للأسهم المصرية والسعودية (تاسي) بمعادلة بنجامين جراهام ومضاعف الربحية P/E ومضاعف القيمة الدفترية P/B واكتشاف الأسهم الرخيصة.",
        offers: {
          "@type": "Offer",
          price: "0",
          priceCurrency: "EGP",
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "الرئيسية", item: "https://egxbots.com" },
          { "@type": "ListItem", position: 2, name: "السعر العادل ومؤشر الرخص", item: "https://egxbots.com/fair-value" },
        ],
      },
      {
        "@type": "FAQPage",
        mainEntity: [
          {
            "@type": "Question",
            name: "كيف يتم حساب السعر العادل للأسهم المصرية والسعودية في هذه الأداة المجانية؟",
            acceptedAnswer: {
              "@type": "Answer",
              text: "تجمع الأداة بين معادلة بنجامين جراهام للقيمة الجوهرية (Graham Number)، ومقارنة مضاعف الربحية P/E ومضاعف القيمة الدفترية P/B مع متوسط القطاع لتحديد هامش الأمان ونسبة الخصم أو التضخم.",
            },
          },
          {
            "@type": "Question",
            name: "هل تغطي الأداة سوق تداول السعودي (تاسي) والبورصة المصرية معاً؟",
            acceptedAnswer: {
              "@type": "Answer",
              text: "نعم، تدعم الأداة كلاً من البورصة المصرية (EGX) بالجنيه المصري والسوق السعودي تداول (TASI) بالريال السعودي مجاناً وبشكل محدث.",
            },
          },
        ],
      },
    ],
  };

  const slimInitialReport =
    initialReport && Array.isArray(initialReport.stocks)
      ? { ...initialReport, stocks: initialReport.stocks.slice(0, 40) }
      : initialReport;

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }}
      />
      <FairValueClient initialReport={slimInitialReport} />
      <section dir="rtl" aria-label="أدوات التحليل المجانية ذات الصلة" className="mx-auto max-w-6xl px-4 pb-8">
        <nav className="flex flex-wrap items-center gap-3 border border-black/15 dark:border-white/15 bg-white/70 dark:bg-zinc-900/60 p-4 text-xs font-bold">
          <span className="text-zinc-900 dark:text-white font-black">أدوات مجانية مكملة:</span>
          <Link href="/disclosures" className="underline text-amber-700 dark:text-amber-400" prefetch={false}>رادار إفصاحات البورصة وتعاملات الداخليين</Link>
          <Link href="/sharia" className="underline text-emerald-700 dark:text-emerald-400" prefetch={false}>الأسهم الحلال وحاسبة تطهير الكوبونات</Link>
          <Link href="/scanner/technical" className="underline text-indigo-700 dark:text-indigo-400" prefetch={false}>الماسح الفني للأسهم</Link>
          <Link href="/stocks" className="underline text-zinc-700 dark:text-zinc-300" prefetch={false}>دليل الأسهم المصرية والسعودية</Link>
        </nav>
      </section>
    </>
  );
}
