import MarketClient from "./MarketClient";
import { Metadata } from "next";

export const metadata: Metadata = {
  title: "تحليل البورصة المصرية والسعودية (EGX30 & TASI)",
  description: "تابع اتجاه البورصة المصرية (EGX30 وEGX100) والسوق السعودي تداول (تاسي TASI) واتساع السوق والسيولة وفق آخر بيانات محفوظة، مع توضيح تاريخ التحديث.",
  keywords: [
    "تحليل البورصة المصرية",
    "تحليل السوق السعودي تاسي",
    "مؤشر EGX30",
    "مؤشر TASI",
    "تداول السعودية",
    "السوق المصري والسعودي",
    "تحليل الأسهم المصرية والسعودية بالذكاء الاصطناعي",
    "سيولة البورصة المصرية وتاسي",
    "توقعات تاسي والبورصة المصرية",
    "EGX BOTS",
    "egxbots"
  ],
  alternates: {
    canonical: "https://egxbots.com/scanner/market",
  },
  openGraph: {
    title: "تحليل سوق البورصة المصرية ومؤشر تاسي السعودي (EGX30 & TASI) | EGX BOTS",
    description: "اتجاه السوق ومؤشرات EGX30 وEGX100 وTASI وحركة السيولة وفق آخر تحديث محفوظ، مع تاريخ البيانات وسياق التحليل.",
    type: "website",
    url: "https://egxbots.com/scanner/market",
    images: [
      {
        url: "https://egxbots.com/dashboard_preview.png",
        width: 1200,
        height: 630,
        alt: "EGX & TASI Market Analysis Dashboard",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "EGX & Saudi TASI Market Analysis | EGX BOTS",
    description: "EGX30, EGX100 and Saudi TASI market direction, breadth and liquidity from the latest saved update, with the data timestamp.",
    images: ["https://egxbots.com/dashboard_preview.png"],
  },
};

const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebPage",
      "@id": "https://egxbots.com/scanner/market#webpage",
      "name": "تحليل سوق البورصة المصرية ومؤشر EGX30",
      "description": "تحليل مؤشري EGX30 وEGX100 واتجاه السوق والسيولة وفق آخر بيانات محفوظة.",
      "url": "https://egxbots.com/scanner/market"
    },
    {
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
          "name": "تحليل السوق ومؤشر EGX30",
          "item": "https://egxbots.com/scanner/market"
        }
      ]
    }
  ]
};

export default function MarketPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />
      <MarketClient />
    </>
  );
}
