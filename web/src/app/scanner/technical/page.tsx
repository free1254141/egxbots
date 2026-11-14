import TechnicalScannerLoader from "./TechnicalScannerLoader";
import TechnicalScannerGuide from "./TechnicalScannerGuide";
import { Metadata } from "next";

export const dynamic = "force-static";
export const revalidate = 86400;

export const metadata: Metadata = {
  title: "الماسح الفني للأسهم المصرية والسعودية (EGX & TASI) | Technical Stock Screener",
  description: "فحص أسهم البورصة المصرية (EGX) والسوق السعودي تداول (تاسي TASI) بمؤشرات RSI وMACD والمتوسطات المتحركة والحجم، وفق البيانات المحفوظة وتاريخ تحديثها، مع فلاتر قابلة للتخصيص.",
  keywords: [
    "الماسح الفني للأسهم المصرية",
    "الماسح الفني للأسهم السعودية تاسي",
    "فحص فني للأسهم",
    "مؤشر RSI",
    "مؤشر MACD",
    "التقاطع الذهبي",
    "دعم ومقاومة",
    "البورصة المصرية",
    "تداول السعودية TASI",
    "تحليل فني مباشر",
    "EGX & TASI Screener",
    "EGX BOTS",
    "egxbots"
  ],
  alternates: {
    canonical: "https://egxbots.com/scanner/technical",
  },
  openGraph: {
    title: "الماسح الفني للأسهم المصرية والسعودية (EGX & TASI) | Technical Screener | EGX BOTS",
    description: "فحص فني لأسهم البورصة المصرية والسوق السعودي تداول بالمؤشرات والسيولة، وفق آخر بيانات محفوظة وتاريخها.",
    type: "website",
    url: "https://egxbots.com/scanner/technical",
    images: [
      {
        url: "https://egxbots.com/dashboard_preview.png",
        width: 1200,
        height: 630,
        alt: "EGX & TASI Technical Scanner",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Technical Stock Screener (EGX & Saudi TASI) | EGX BOTS",
    description: "Screen Egyptian Exchange (EGX) and Saudi Tadawul (TASI) stocks with RSI, MACD, EMA crossover, VWAP, and volume filters.",
    images: ["https://egxbots.com/dashboard_preview.png"],
  },
};

const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "SoftwareApplication",
      "@id": "https://egxbots.com/scanner/technical#tool",
      "name": "EGX Technical Screener",
      "alternateName": "الماسح الفني للبورصة المصرية",
      "applicationCategory": "FinanceApplication",
      "operatingSystem": "Web",
      "description": "ماسح فني للأسهم المصرية بمؤشرات التحليل الفني وفلاتر السيولة، وفق آخر بيانات محفوظة وتاريخها.",
      "url": "https://egxbots.com/scanner/technical"
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
          "name": "الماسح الفني",
          "item": "https://egxbots.com/scanner/technical"
        }
      ]
    }
  ]
};

export default function TechnicalScannerPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />
      <TechnicalScannerGuide />
      <TechnicalScannerLoader />
    </>
  );
}
