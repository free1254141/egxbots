import { Metadata } from "next";
import BlogsClient from "./BlogsClient";

export const metadata: Metadata = {
  title: "مدونة EGX BOTS: تحليلات البورصة المصرية والسعودية بالذكاء الاصطناعي",
  description: "مقالات وأدلة معمقة لحركة الأسهم في البورصة المصرية (EGX) والسوق السعودي (تداول TASI)، الأسهم النقية شرعياً، ومؤشرات التحليل الكمي بالذكاء الاصطناعي.",
  keywords: [
    "تحليلات البورصة المصرية",
    "تحليل الأسهم السعودية تاسي",
    "الأسهم السعودية النقية شرعيا",
    "تحليل سهم أرامكو والراجحي",
    "تحليل الأسهم بالذكاء الاصطناعي",
    "EGX BOTS Blog",
    "TASI BOTS",
    "البورصة المصرية",
    "تداول تاسي"
  ],
  alternates: {
    canonical: "https://egxbots.com/blogs",
  },
  openGraph: {
    title: "مدونة وتحليلات البورصة المصرية والسوق السعودي بالذكاء الاصطناعي | EGX & TASI Bots",
    description: "أدلة ومقالات معمقة للأسهم في البورصة المصرية والسوق السعودي تاسي ومؤشرات التداول الكمي بالذكاء الاصطناعي.",
    url: "https://egxbots.com/blogs",
    type: "website",
    images: [
      {
        url: "https://egxbots.com/opengraph-image.png",
        width: 1200,
        height: 630,
        alt: "مدونة EGX BOTS لتحليلات البورصة المصرية والسعودية",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "مدونة EGX BOTS | تحليلات البورصة المصرية والسعودية",
    description: "مقالات وأدلة معمقة للأسهم المصرية والسعودية والأسهم النقية شرعياً ومؤشرات الذكاء الاصطناعي.",
    images: ["https://egxbots.com/opengraph-image.png"],
  },
};

const blogsSchema = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "الرئيسية", item: "https://egxbots.com" },
        { "@type": "ListItem", position: 2, name: "المدونة", item: "https://egxbots.com/blogs" },
      ],
    },
    {
      "@type": "CollectionPage",
      "@id": "https://egxbots.com/blogs#webpage",
      name: "مدونة وتحليلات البورصة المصرية والسوق السعودي (تاسي)",
      url: "https://egxbots.com/blogs",
      description:
        "مقالات وأدلة معمقة لحركة الأسهم في البورصة المصرية (EGX) والسوق السعودي (تداول TASI)، الأسهم النقية شرعياً، ومؤشرات التحليل الكمي بالذكاء الاصطناعي.",
      publisher: { "@type": "Organization", name: "EGX BOTS", url: "https://egxbots.com" },
    },
  ],
};

export default function BlogsPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(blogsSchema).replace(/</g, "\\u003c") }}
      />
      <BlogsClient />
    </>
  );
}
