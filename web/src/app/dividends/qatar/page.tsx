import type { Metadata } from "next";
import DividendCalendarClient from "@/components/dividends/DividendCalendarClient";
import { getServerDividendsCalendar } from "@/lib/market/dividends-server";

export const revalidate = 604800;
export const preferredRegion = "fra1";

export const metadata: Metadata = {
  title: { absolute: "تقويم توزيعات الأرباح في بورصة قطر (QSE) 2026 | مواعيد الصرف والعائد" },
  description:
    "مواعيد استحقاق وصرف التوزيعات النقدية لأسهم بورصة قطر (QSE) بالريال القطري مع العائد وحاسبة الكوبونات.",
  alternates: { canonical: "https://egxbots.com/dividends/qatar" },
  openGraph: {
    title: "تقويم توزيعات الأرباح في بورصة قطر (QSE)",
    description: "مواعيد استحقاق وصرف التوزيعات النقدية لأسهم بورصة قطر بالريال القطري.",
    url: "https://egxbots.com/dividends/qatar",
    type: "website",
    images: [{ url: "https://egxbots.com/opengraph-image.png", width: 1200, height: 630, alt: "توزيعات أرباح بورصة قطر QSE" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "تقويم توزيعات الأرباح في بورصة قطر (QSE)",
    description: "مواعيد استحقاق وصرف الأرباح النقدية لأسهم بورصة قطر.",
    images: ["https://egxbots.com/opengraph-image.png"],
  },
};

export default async function QatarDividendsPage() {
  const data = await getServerDividendsCalendar("qatar");
  return <DividendCalendarClient initialData={data} />;
}
