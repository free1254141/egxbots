import { Metadata } from "next";
import ShariaCleanserClient from "./ShariaCleanserClient";
import { getCachedFairValueReport } from "@/lib/market/fair-value-server";

export const revalidate = 86400;
export const preferredRegion = "fra1";

export const metadata: Metadata = {
  title: "التوافق الشرعي وتطهير الكوبونات للأسهم المصرية (EGX33)",
  description:
    "قائمة الأسهم المتوافقة مع الشريعة الإسلامية في البورصة المصرية (EGX33) مع حاسبة تطهير الكوبونات والتوزيعات النقدية وحاسبة زكاة الأسهم.",
  keywords: [
    "الأسهم الحلال في البورصة المصرية",
    "الأسهم المتوافقة مع الشريعة في البورصة المصرية",
    "مؤشر الشريعة EGX33",
    "حاسبة تطهير الأسهم المصرية",
    "تطهير كوبونات البورصة المصرية",
    "زكاة الأسهم المصرية",
    "EGX Sharia Stocks",
  ],
  alternates: {
    canonical: "https://egxbots.com/sharia",
  },
  openGraph: {
    title: "الأسهم المتوافقة مع الشريعة (EGX33) وحاسبة التطهير | EGX BOTS",
    description:
      "دليل الأسهم المتوافقة مع الشريعة الإسلامية في البورصة المصرية مع حاسبة تطهير الكوبونات وحاسبة الزكاة.",
    url: "https://egxbots.com/sharia",
    type: "website",
    images: [
      {
        url: "https://egxbots.com/opengraph-image.png",
        width: 1200,
        height: 630,
        alt: "الأسهم المتوافقة مع الشريعة في البورصة المصرية - EGX BOTS",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "الأسهم المتوافقة مع الشريعة (EGX33) وحاسبة التطهير | EGX BOTS",
    description:
      "دليل الأسهم المتوافقة مع الشريعة الإسلامية في البورصة المصرية مع حاسبة تطهير الكوبونات.",
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
  return <ShariaCleanserClient initialReport={initialReport} />;
}
