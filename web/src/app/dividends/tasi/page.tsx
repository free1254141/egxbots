import type { Metadata } from "next";
import DividendCalendarClient from "@/components/dividends/DividendCalendarClient";
import { getServerDividendsCalendar } from "@/lib/market/dividends-server";

export const revalidate = 604800;
export const preferredRegion = "fra1";

export const metadata: Metadata = {
  title: { absolute: "تقويم توزيعات الأرباح والكوبونات في السوق السعودي (تداول TASI) 2026 | TASI BOTS" },
  description:
    "تابع مواعيد استحقاق وصرف الأرباح النقدية لأسهم السوق السعودي تداول (TASI) بالريال السعودي مع العائد وحاسبة الأرباح الفورية.",
  alternates: { canonical: "https://egxbots.com/dividends/tasi" },
  openGraph: {
    title: "تقويم توزيعات الأرباح والكوبونات في السوق السعودي (TASI) | TASI BOTS",
    description: "مواعيد استحقاق وصرف التوزيعات النقدية لأسهم السوق السعودي تداول بالريال.",
    url: "https://egxbots.com/dividends/tasi",
    type: "website",
    images: [{ url: "https://egxbots.com/opengraph-image.png", width: 1200, height: 630, alt: "توزيعات أرباح السوق السعودي تاسي" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "تقويم توزيعات الأرباح في السوق السعودي (تاسي) | TASI BOTS",
    description: "مواعيد استحقاق وصرف الأرباح النقدية في تداول السعودية مع العائد.",
    images: ["https://egxbots.com/opengraph-image.png"],
  },
};

export default async function TasiDividendsPage() {
  const data = await getServerDividendsCalendar("tasi");
  return <DividendCalendarClient initialData={data} />;
}
