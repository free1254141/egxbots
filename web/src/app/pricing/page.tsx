import PricingClient from "./PricingClient";

export const dynamic = "force-static";
export const revalidate = 86400;

export const metadata = {
  title: "خطط الأسعار والاشتراكات الشهرية والسنوية | البورصة المصرية EGX والسوق السعودي تداول TASI",
  description:
    "خطط الأسعار المتاحة لمنصة EGX Bots و TASI Bots في البورصة المصرية والسوق السعودي (تداول TASI). اشترك في خطة Pro أو Lifetime VIP للحصول على إشارات يومية، تحليلات الذكاء الاصطناعي، وقنوات التليجرام الفورية.",
  keywords: [
    "الأسعار",
    "الاشتراكات",
    "خطة",
    "EGX Bots",
    "TASI Bots",
    "البورصة المصرية",
    "السوق السعودي",
    "تداول",
    "TASI",
    "الاشتراك المدفوع",
  ],
  alternates: { canonical: "https://egxbots.com/pricing" },
};

export default function PricingPage() {
  return <PricingClient />;
}
