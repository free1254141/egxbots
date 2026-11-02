import { Metadata } from "next";
import ShariaCleanserClient from "./ShariaCleanserClient";
import { getCachedFairValueReport } from "@/lib/market/fair-value-server";

export const revalidate = 86400;
export const preferredRegion = "fra1";

export const metadata: Metadata = {
  title: "حاسبة التوافق الشرعي وتطهير الكوبونات للبورصة المصرية | Sharia Cleanser",
  description:
    "قائمة الأسهم المتوافقة مع الشريعة الإسلامية في البورصة المصرية (EGX33) مع حاسبة تطهير الكوبونات والتوزيعات النقدية وحاسبة زكاة الأسهم.",
  keywords: [
    "الأسهم الحلال في البورصة المصرية",
    "مؤشر الشريعة EGX33",
    "حاسبة تطهير الأسهم المصرية",
    "تطهير كوبونات البورصة المصرية",
    "زكاة الأسهم المصرية",
    "EGX Sharia Stocks",
  ],
  alternates: {
    canonical: "https://egxbots.com/sharia",
  },
};

export default async function ShariaPage() {
  let initialReport = null;
  try {
    initialReport = await getCachedFairValueReport();
  } catch (err) {
    console.error("[ShariaPage] Failed to pre-fetch cached report:", err);
  }
  return <ShariaCleanserClient initialReport={initialReport} />;
}
