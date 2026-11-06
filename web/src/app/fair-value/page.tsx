import { Metadata } from "next";
import FairValueClient from "./FairValueClient";
import { getCachedFairValueReport } from "@/lib/market/fair-value-server";

export const revalidate = 86400;
export const preferredRegion = "fra1";

export const metadata: Metadata = {
  title: "السعر العادل ومؤشر الرخص للأسهم المصرية",
  description:
    "اكتشف أرخص أسهم البورصة المصرية (EGX) يومياً ومقارنتها بالسعر العادل المحسوب بمعادلة بنجامين جراهام ومضاعفات الربحية والقيمة الدفترية والتوازن الكمي.",
  keywords: [
    "السعر العادل للأسهم المصرية",
    "أرخص أسهم البورصة المصرية",
    "مضاعف الربحية EGX",
    "القيمة الدفترية للأسهم المصرية",
    "معادلة جراهام للأسهم",
    "EGX Fair Value Screener",
    "Undervalued Egyptian Stocks",
  ],
  alternates: {
    canonical: "https://egxbots.com/fair-value",
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
