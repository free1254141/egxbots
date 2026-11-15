import { Metadata } from "next";
import BlogsClient from "./BlogsClient";

export const metadata: Metadata = {
  title: "مدونة وتحليلات البورصة المصرية والسوق السعودي (تاسي) بالذكاء الاصطناعي",
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
  },
};

export default function BlogsPage() {
  return <BlogsClient />;
}
