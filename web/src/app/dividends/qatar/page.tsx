import type { Metadata } from "next";
import DividendCalendarClient from "@/components/dividends/DividendCalendarClient";
import { getServerDividendsCalendar } from "@/lib/market/dividends-server";

export const revalidate = 604800;
export const preferredRegion = "fra1";

export const metadata: Metadata = {
  title: "تقويم توزيعات الأرباح في بورصة قطر (QSE) | EGX BOTS",
  description:
    "مواعيد استحقاق وصرف التوزيعات النقدية لأسهم بورصة قطر (QSE) مع العائد وحاسبة الكوبونات.",
  alternates: { canonical: "https://egxbots.com/dividends/qatar" },
};

export default async function QatarDividendsPage() {
  const data = await getServerDividendsCalendar("qatar");
  return <DividendCalendarClient initialData={data} />;
}
