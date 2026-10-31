import type { Metadata } from "next";
import AffiliateClient from "./AffiliateClient";

export const metadata: Metadata = {
  title: "برنامج التسويق بالعمولة وشركاء النجاح (اربح 25% كاش) | EGX BOTS",
  description:
    "احصل على رابط الإحالة وكود الخصم الخاص بك في منصة EGX BOTS لتحليل أسهم البورصة المصرية، وامنح أصدقاءك خصم 10% واربح 25% عمولة كاش على محفظتك الإلكترونية.",
};

export default function AffiliatePage() {
  return <AffiliateClient />;
}
