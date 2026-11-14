import { Metadata } from "next";
import FairValueClient from "./FairValueClient";
import { getCachedFairValueReport } from "@/lib/market/fair-value-server";

export const revalidate = 86400;
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
  return <FairValueClient initialReport={initialReport} />;
}
