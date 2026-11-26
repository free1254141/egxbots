import type { Metadata } from "next";
import DividendCalendarClient from "@/components/dividends/DividendCalendarClient";
import { getServerDividendsCalendar } from "@/lib/market/dividends-server";

export const revalidate = 604800;
export const preferredRegion = "fra1";

export const metadata: Metadata = {
  title: "تقويم توزيعات الأرباح والكوبونات في السوق السعودي (تداول TASI) | EGX BOTS",
  description:
    "تابع مواعيد استحقاق وصرف الأرباح النقدية لأسهم السوق السعودي تداول (TASI) مع حاسبة الأرباح الفورية.",
  alternates: { canonical: "https://egxbots.com/dividends/tasi" },
};

export default async function TasiDividendsPage() {
  const data = await getServerDividendsCalendar("tasi");
  return <DividendCalendarClient initialData={data} />;
}
