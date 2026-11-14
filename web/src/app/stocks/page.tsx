import { Metadata } from "next";
import { getPublicStockDirectory } from "@/lib/seo/stock-directory";
import StocksClient from "./StocksClient";

export const revalidate = 86400; // Cache for 24 hours (daily market job cadence)

export const metadata: Metadata = {
  title: "دليل أسهم البورصة المصرية والسعودية (EGX & TASI) وتحليل الشركات",
  description: "تصفح أسهم البورصة المصرية (EGX) والسوق السعودي تداول (تاسي TASI) وأسعارها المحفوظة وتقييمات الذكاء الاصطناعي والمؤشرات الفنية. راجع تاريخ البيانات وتغطية كل سهم قبل المقارنة.",
  keywords: [
    "دليل أسهم البورصة المصرية",
    "دليل الأسهم السعودية تاسي",
    "قائمة شركات البورصة المصرية وتداول",
    "أسهم البورصة المصرية",
    "الأسهم السعودية TASI",
    "تحليل الأسهم المصرية بالذكاء الاصطناعي",
    "تحليل الأسهم السعودية بالذكاء الاصطناعي",
    "مؤشر EGX30",
    "مؤشر TASI",
    "سهم أرامكو 2222",
    "سهم الراجحي 1120",
    "أسهم CIB وبلتون وطلعت مصطفى",
    "EGX & TASI Directory",
    "EGX BOTS",
    "egxbots"
  ],
  alternates: {
    canonical: "https://egxbots.com/stocks",
  },
  openGraph: {
    title: "دليل أسهم البورصة المصرية والسعودية (EGX & TASI) | EGX BOTS",
    description: "تصفح أسهم البورصة المصرية والسوق السعودي تداول مع تقييمات الذكاء الاصطناعي والمؤشرات الفنية وفق آخر بيانات محفوظة وتاريخ تحديثها.",
    type: "website",
    url: "https://egxbots.com/stocks",
    images: [
      {
        url: "https://egxbots.com/dashboard_preview.png",
        width: 1200,
        height: 630,
        alt: "EGX & TASI Bots Stocks Directory",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "EGX & Saudi TASI Stocks Directory | EGX BOTS",
    description: "Complete directory of Egyptian Exchange (EGX) and Saudi Tadawul (TASI) listed companies with AI scores and technical analysis.",
    images: ["https://egxbots.com/dashboard_preview.png"],
  },
};

export default async function StocksPage() {
  const stocks = await getPublicStockDirectory();

  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "CollectionPage",
        "@id": "https://egxbots.com/stocks#webpage",
        "name": "دليل أسهم وشركات البورصة المصرية",
        "description": "قائمة كاملة لأسهم البورصة المصرية والتحليل الفني والذكاء الاصطناعي.",
        "url": "https://egxbots.com/stocks",
        "breadcrumb": {
          "@type": "BreadcrumbList",
          "itemListElement": [
            {
              "@type": "ListItem",
              "position": 1,
              "name": "الرئيسية",
              "item": "https://egxbots.com"
            },
            {
              "@type": "ListItem",
              "position": 2,
              "name": "دليل الأسهم",
              "item": "https://egxbots.com/stocks"
            }
          ]
        }
      },
      {
        "@type": "ItemList",
        "@id": "https://egxbots.com/stocks#itemlist",
        "name": "Egyptian Exchange (EGX) Listed Stocks",
        "numberOfItems": stocks.length,
        "itemListElement": stocks.slice(0, 100).map((s, idx) => ({
          "@type": "ListItem",
          "position": idx + 1,
          "name": `${s.name} (${s.symbol})`,
          "url": `https://egxbots.com/stocks/${s.symbol.toLowerCase()}`
        }))
      }
    ]
  };

  return (
    <div className="w-full pt-5 sm:pt-7">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />
      <StocksClient initialStocks={stocks} />
    </div>
  );
}
