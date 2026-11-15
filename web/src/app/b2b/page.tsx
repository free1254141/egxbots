import type { Metadata } from "next";
import B2BLandingClient from "./B2BLandingClient";

export const metadata: Metadata = {
  title: "حلول الشركات وقنوات المتابعة والأكاديميات (B2B SaaS) | EGX BOTS & TASI BOTS",
  description:
    "فعّل أداة البيانات الذكية ARTORO داخل مجتمعات التليجرام بتوقيعك الخاص، ووفّر أدوات القراءة الإحصائية للمؤشرات وتلخيص الإفصاحات والقيمة العادلة لشركات السمسرة والأكاديميات والمواقع المالية مع تجربة مجانية 3 أيام.",
  alternates: {
    canonical: "https://egxbots.com/b2b",
  },
  openGraph: {
    title: "حلول الشركات وقنوات التداول (B2B) | EGX BOTS & TASI BOTS",
    description:
      "بوت تليجرام ذكي يرد على أعضاء قناتك 24/7 بتوقيعك المخصص، وحلول مؤسسية للأكاديميات وشركات السمسرة والفنتك في مصر والسعودية.",
    url: "https://egxbots.com/b2b",
    type: "website",
  },
};

export default function B2BIndexPage() {
  return <B2BLandingClient />;
}
