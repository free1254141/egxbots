import type { Metadata } from "next";
import DividendCalendarClient from "@/components/dividends/DividendCalendarClient";
import { getServerDividendsCalendar } from "@/lib/market/dividends-server";

export const revalidate = 604800;
export const preferredRegion = "fra1";

export const metadata: Metadata = {
  title: { absolute: "تقويم توزيعات الأرباح في أسواق الإمارات (سوق دبي DFM وأبوظبي ADX) 2026" },
  description:
    "مواعيد استحقاق وصرف التوزيعات النقدية لأسهم سوق دبي المالي (DFM) وسوق أبوظبي للأوراق المالية (ADX) بالدرهم الإماراتي مع العائد.",
  alternates: { canonical: "https://egxbots.com/dividends/uae" },
  openGraph: {
    title: "تقويم توزيعات الأرباح في أسواق الإمارات (DFM & ADX)",
    description: "مواعيد استحقاق وصرف الأرباح النقدية لأسهم دبي وأبوظبي بالدرهم.",
    url: "https://egxbots.com/dividends/uae",
    type: "website",
    images: [{ url: "https://egxbots.com/opengraph-image.png", width: 1200, height: 630, alt: "توزيعات أرباح أسهم الإمارات DFM ADX" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "توزيعات أرباح أسهم الإمارات (DFM & ADX)",
    description: "مواعيد استحقاق وصرف الأرباح النقدية لأسهم سوق دبي وأبوظبي.",
    images: ["https://egxbots.com/opengraph-image.png"],
  },
};

export default async function UaeDividendsPage() {
  const data = await getServerDividendsCalendar("uae");
  return <DividendCalendarClient initialData={data} />;
}
