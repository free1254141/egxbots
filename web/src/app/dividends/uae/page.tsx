import type { Metadata } from "next";
import DividendCalendarClient from "@/components/dividends/DividendCalendarClient";
import { getServerDividendsCalendar } from "@/lib/market/dividends-server";

export const revalidate = 86400;
export const preferredRegion = "fra1";

export const metadata: Metadata = {
  title: "تقويم توزيعات الأرباح في أسواق الإمارات (دبي DFM وأبوظبي ADX) | EGX BOTS",
  description:
    "مواعيد استحقاق وصرف التوزيعات النقدية لأسهم سوق دبي المالي (DFM) وسوق أبوظبي للأوراق المالية (ADX).",
  alternates: { canonical: "https://egxbots.com/dividends/uae" },
};

export default async function UaeDividendsPage() {
  const data = await getServerDividendsCalendar("uae");
  return <DividendCalendarClient initialData={data} />;
}
