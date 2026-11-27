import { Metadata } from "next";
import { getPublicGccMetalsDirectoryWithPrices } from "@/lib/seo/stock-directory";
import MarketDirectoryPage from "@/components/seo/MarketDirectoryPage";

export const preferredRegion = "fra1";
export const revalidate = 604800;

export const metadata: Metadata = {
  title: { absolute: "سعر الذهب والفضة اليوم (XAUUSD & XAGUSD) والتحليل الفني ومستويات الدعم والمقاومة" },
  description:
    "تابع سعر أونصة الذهب العالمي XAUUSD وسعر أونصة الفضة XAGUSD اليوم بالدولار الأمريكي مع التحليل الفني، مؤشر القوة النسبية RSI، ومستويات الدعم والمقاومة بالذكاء الاصطناعي.",
  keywords: [
    "سعر الذهب اليوم",
    "تحليل الذهب XAUUSD",
    "سعر أونصة الذهب بالدولار",
    "سعر الفضة اليوم XAGUSD",
    "تحليل الفضة الفني",
    "توقعات الذهب بالذكاء الاصطناعي",
    "EGX BOTS",
  ],
  alternates: { canonical: "https://egxbots.com/markets/gold-silver" },
  openGraph: {
    title: "سعر وتحليل الذهب والفضة اليوم (XAUUSD & XAGUSD) | EGX BOTS",
    description: "تحليل فني يومي لأونصة الذهب والفضة العالمية بالدولار مع مستويات الدعم والمقاومة.",
    type: "website",
    url: "https://egxbots.com/markets/gold-silver",
    images: [{ url: "https://egxbots.com/opengraph-image.png", width: 1200, height: 630, alt: "تحليل الذهب والفضة XAUUSD XAGUSD" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "سعر الذهب والفضة اليوم (XAUUSD & XAGUSD) | EGX BOTS",
    description: "تحليل فني يومي لأونصة الذهب والفضة العالمية بالدولار مع مؤشر RSI ومستويات الدعم والمقاومة.",
    images: ["https://egxbots.com/opengraph-image.png"],
  },
};

export default async function GoldSilverMarketPage() {
  const all = await getPublicGccMetalsDirectoryWithPrices().catch(() => []);
  const items = all.filter((s) => s.exchange === "COMMODITIES");

  return (
    <MarketDirectoryPage
      canonicalUrl="https://egxbots.com/markets/gold-silver"
      badge="🥇🥈 المعادن الثمينة العالمية"
      title="أسعار وتحليل الذهب والفضة اليوم (XAUUSD & XAGUSD)"
      subtitle="تابع حركة أونصة الذهب والفضة العالمية بالدولار الأمريكي كأداة تحوط وملاذ آمن مع مؤشرات الزخم RSI وMACD ونقاط الدعم والمقاومة المحدثة يومياً."
      currencyLabel="دولار"
      items={items}
      otherMarketLinks={[
        { href: "/markets/uae", label: "🇦🇪 أسهم الإمارات" },
        { href: "/markets/qatar", label: "🇶🇦 بورصة قطر" },
        { href: "/stocks", label: "🇪🇬🇸🇦 مصر والسعودية" },
      ]}
      faqs={[
        {
          q: "هل يشمل تحليل الذهب والفضة البيانات التاريخية؟",
          a: "نعم، تتوفر بيانات يومية تاريخية للذهب (XAUUSD) والفضة (XAGUSD) منذ عام 2010 مع حساب مستمر للمؤشرات الفنية ومستويات الدعم والمقاومة.",
        },
        {
          q: "كيف أسأل الشات بوت عن الذهب أو الفضة؟",
          a: "يمكنك كتابة (حلل الذهب) أو (مستويات الفضة) أو (XAUUSD) في الشات بوت من أي سوق للحصول على التحليل الفني الفوري.",
        },
      ]}
    />
  );
}
