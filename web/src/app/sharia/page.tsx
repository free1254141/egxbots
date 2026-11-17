import { Metadata } from "next";
import Link from "next/link";
import ShariaCleanserClient from "./ShariaCleanserClient";
import { getCachedFairValueReport } from "@/lib/market/fair-value-server";

export const revalidate = 604800;
export const preferredRegion = "fra1";

export const metadata: Metadata = {
  title: "التوافق الشرعي وتطهير التوزيعات للأسهم المصرية والسعودية (EGX33 & TASI)",
  description:
    "قائمة الأسهم المتوافقة مع الشريعة الإسلامية في البورصة المصرية (EGX33) والسوق السعودي (تاسي TASI) مع حاسبة تطهير الكوبونات والتوزيعات النقدية وحاسبة زكاة الأسهم.",
  keywords: [
    "الأسهم الحلال في البورصة المصرية",
    "الأسهم النقية في السوق السعودي تاسي",
    "الأسهم المتوافقة مع الشريعة في تاسي",
    "مؤشر الشريعة EGX33",
    "حاسبة تطهير الأسهم السعودية والمصرية",
    "تطهير توزيعات الأسهم تاسي",
    "زكاة الأسهم",
    "EGX TASI Sharia Stocks",
  ],
  alternates: {
    canonical: "https://egxbots.com/sharia",
  },
  openGraph: {
    title: "الأسهم المتوافقة مع الشريعة (EGX33 & TASI) وحاسبة التطهير | EGX BOTS",
    description:
      "دليل الأسهم المتوافقة مع الشريعة الإسلامية في البورصة المصرية والسوق السعودي تاسي مع حاسبة تطهير التوزيعات وحاسبة الزكاة.",
    url: "https://egxbots.com/sharia",
    type: "website",
    images: [
      {
        url: "https://egxbots.com/opengraph-image.png",
        width: 1200,
        height: 630,
        alt: "الأسهم المتوافقة مع الشريعة في البورصة المصرية والسعودية - EGX BOTS",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "الأسهم المتوافقة مع الشريعة (EGX33 & TASI) وحاسبة التطهير | EGX BOTS",
    description:
      "دليل الأسهم المتوافقة مع الشريعة الإسلامية في البورصة المصرية والسوق السعودي تاسي مع حاسبة التطهير.",
    images: ["https://egxbots.com/opengraph-image.png"],
  },
};

export default async function ShariaPage() {
  let initialReport = null;
  try {
    initialReport = await getCachedFairValueReport();
  } catch (err) {
    console.error("[ShariaPage] Failed to pre-fetch cached report:", err);
  }

  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "SoftwareApplication",
        "@id": "https://egxbots.com/sharia#tool",
        name: "دليل الأسهم المتوافقة مع الشريعة وحاسبة التطهير (EGX33 & TASI)",
        alternateName: ["EGX33 & TASI Sharia Stock Screener", "حاسبة تطهير الأسهم"],
        applicationCategory: "FinanceApplication",
        operatingSystem: "Web",
        url: "https://egxbots.com/sharia",
        description:
          "أداة مجانية لفحص الأسهم المتوافقة مع الشريعة الإسلامية في البورصة المصرية (EGX33) والسوق السعودي (تاسي TASI) مع حاسبة تطهير الكوبونات والتوزيعات النقدية وحاسبة الزكاة.",
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
          { "@type": "ListItem", position: 2, name: "التوافق الشرعي وحاسبة التطهير", item: "https://egxbots.com/sharia" },
        ],
      },
      {
        "@type": "FAQPage",
        mainEntity: [
          {
            "@type": "Question",
            name: "كيف يتم فحص الأسهم الحلال في البورصة المصرية (EGX33) والسوق السعودي (تاسي)؟",
            acceptedAnswer: {
              "@type": "Answer",
              text: "تعتمد الأداة على الضوابط الشرعية المعتمدة (نشاط الشركة المباح، نسبة الديون الربوية والأصول السائلة إلى القيمة السوقية أو إجمالي الأصول، ونسبة الإيرادات غير التشغيلية) مع توفير نسبة التطهير لكل سهم.",
            },
          },
          {
            "@type": "Question",
            name: "كيف تعمل حاسبة تطهير التوزيعات والكوبونات وزكاة الأسهم؟",
            acceptedAnswer: {
              "@type": "Answer",
              text: "أدخل عدد الأسهم أو قيمة التوزيعات النقدية، وتقوم الأداة المجانية فوراً بحساب المبلغ الواجب إخراجه للتطهير وفق نسبة التطهير الشرعية لكل شركة.",
            },
          },
        ],
      },
    ],
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }}
      />
      <ShariaCleanserClient initialReport={initialReport} />
      <section dir="rtl" aria-label="أدوات التحليل المجانية ذات الصلة" className="mx-auto max-w-6xl px-4 pb-8">
        <nav className="flex flex-wrap items-center gap-3 border border-black/15 dark:border-white/15 bg-white/70 dark:bg-zinc-900/60 p-4 text-xs font-bold">
          <span className="text-zinc-900 dark:text-white font-black">أدوات مجانية مكملة:</span>
          <Link href="/fair-value" className="underline text-emerald-700 dark:text-emerald-400">محدد السعر العادل ومؤشر الرخص</Link>
          <Link href="/disclosures" className="underline text-amber-700 dark:text-amber-400">رادار إفصاحات البورصة وتعاملات الداخليين</Link>
          <Link href="/scanner/technical" className="underline text-indigo-700 dark:text-indigo-400">الماسح الفني للأسهم</Link>
          <Link href="/stocks" className="underline text-zinc-700 dark:text-zinc-300">دليل الأسهم المصرية والسعودية</Link>
        </nav>
      </section>
    </>
  );
}
