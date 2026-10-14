import { Metadata } from "next";
import { getPublicStockDirectory } from "@/lib/seo/stock-directory";
import StocksClient from "./StocksClient";
import BrandedPageHeader from "@/components/BrandedPageHeader";

export const revalidate = 3600; // Cache for 1 hour

export const metadata: Metadata = {
  title: "دليل أسهم البورصة المصرية وتحليل الشركات",
  description: "تصفح أسهم البورصة المصرية وأسعارها المحفوظة وتقييمات الذكاء الاصطناعي والمؤشرات الفنية. راجع تاريخ البيانات وتغطية كل سهم قبل المقارنة.",
  keywords: [
    "دليل أسهم البورصة المصرية",
    "قائمة شركات البورصة المصرية",
    "أسهم البورصة المصرية",
    "تحليل الأسهم المصرية بالذكاء الاصطناعي",
    "مؤشر EGX30",
    "مؤشر EGX70",
    "أسهم CIB وبلتون وطلعت مصطفى",
    "EGX Directory",
    "EGX BOTS",
    "egxbots"
  ],
  alternates: {
    canonical: "https://egxbots.com/stocks",
  },
  openGraph: {
    title: "دليل أسهم البورصة المصرية | EGX BOTS",
    description: "تصفح أسهم البورصة المصرية مع تقييمات الذكاء الاصطناعي والمؤشرات الفنية وفق آخر بيانات محفوظة وتاريخ تحديثها.",
    type: "website",
    url: "https://egxbots.com/stocks",
    images: [
      {
        url: "https://egxbots.com/dashboard_preview.png",
        width: 1200,
        height: 630,
        alt: "EGX Bots Stocks Directory",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Egyptian Exchange Stocks Directory | EGX BOTS",
    description: "Complete directory of EGX listed companies with AI scores and technical analysis.",
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
      <BrandedPageHeader
        eyebrow="دليل السوق والشركات | EGX DIRECTORY"
        title="دليل أسهم البورصة المصرية بالذكاء الاصطناعي"
        description="تصفح جميع الشركات والأسهم المقيدة في البورصة المصرية، واكتشف التقييمات الفنية ونماذج تعلم الآلة ومستويات السيولة لكل سهم."
      />
      <StocksClient initialStocks={stocks} />
    </div>
  );
}
