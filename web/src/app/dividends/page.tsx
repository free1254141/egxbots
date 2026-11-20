import type { Metadata } from "next";
import DividendCalendarClient from "@/components/dividends/DividendCalendarClient";
import { getServerDividendsCalendar } from "@/lib/market/dividends-server";

export const revalidate = 86400;
export const preferredRegion = "fra1";

export const metadata: Metadata = {
  title: "تقويم توزيعات الكوبونات في البورصة المصرية (EGX) | EGX BOTS",
  description:
    "مواعيد توزيع الكوبونات النقدية القادمة في البورصة المصرية: تاريخ التداول بدون كوبون (Ex-Date)، نهاية الحق، تاريخ الصرف الفعلي، وحاسبة أرباح الكوبونات.",
  alternates: { canonical: "https://egxbots.com/dividends" },
};

export default async function EgxDividendsPage() {
  const data = await getServerDividendsCalendar("egx");
  return <DividendCalendarClient initialData={data} />;
}
