import { Metadata } from "next";
import { getPublicGccMetalsDirectoryWithPrices } from "@/lib/seo/stock-directory";
import MarketDirectoryPage from "@/components/seo/MarketDirectoryPage";

export const preferredRegion = "fra1";
export const revalidate = 604800;

export const metadata: Metadata = {
  title: "دليل أسهم الإمارات (دبي DFM وأبوظبي ADX) والتحليل بالذكاء الاصطناعي | EGX BOTS",
  description:
    "تصفح أسعار أسهم سوق دبي المالي (DFM) وسوق أبوظبي للأوراق المالية (ADX) مثل إعمار والدار وأدنوك وبنك أبوظبي الأول مع مؤشرات RSI والدعم والمقاومة وتحليل الشات بوت AI.",
  keywords: [
    "أسهم الإمارات",
    "سوق دبي المالي DFM",
    "سوق أبوظبي للأوراق المالية ADX",
    "سهم إعمار العقارية EMAAR",
    "سهم الدار العقارية ALDAR",
    "أسهم أدنوك",
    "تحليل الأسهم الإماراتية بالذكاء الاصطناعي",
    "EGX BOTS",
  ],
  alternates: { canonical: "https://egxbots.com/markets/uae" },
  openGraph: {
    title: "دليل أسهم الإمارات (سوق دبي DFM وسوق أبوظبي ADX) | EGX BOTS",
    description: "أسعار ومؤشرات أسهم دبي وأبوظبي محدثة يومياً مع تحليل الذكاء الاصطناعي ومستويات الدعم والمقاومة.",
    type: "website",
    url: "https://egxbots.com/markets/uae",
    images: [{ url: "https://egxbots.com/opengraph-image.png", width: 1200, height: 630, alt: "أسهم الإمارات DFM & ADX" }],
  },
};

export default async function UaeMarketPage() {
  const all = await getPublicGccMetalsDirectoryWithPrices().catch(() => []);
  const items = all.filter((s) => s.exchange === "DFM" || s.exchange === "ADX");

  return (
    <MarketDirectoryPage
      canonicalUrl="https://egxbots.com/markets/uae"
      badge="🇦🇪 سوق دبي المالي (DFM) وسوق أبوظبي (ADX)"
      title="دليل أسهم الإمارات (دبي وأبوظبي) بالذكاء الاصطناعي"
      subtitle="تابع أسعار ومؤشرات أبرز أسهم سوق دبي المالي وسوق أبوظبي للأوراق المالية (إعمار، الدار، العالمية القابضة، أدنوك، بنك أبوظبي الأول، سالك، ديوا) مع تحليل فني ومستويات دعم ومقاومة محدثة يومياً."
      currencyLabel="د.إ"
      items={items}
      otherMarketLinks={[
        { href: "/markets/qatar", label: "🇶🇦 بورصة قطر (QSE)" },
        { href: "/markets/gold-silver", label: "🥇 الذهب والفضة" },
        { href: "/stocks", label: "🇪🇬🇸🇦 مصر والسعودية" },
      ]}
      faqs={[
        {
          q: "ما هي الأسواق الإماراتية المدعومة في EGX BOTS؟",
          a: "يدعم EGX BOTS كلاً من سوق دبي المالي (DFM) وسوق أبوظبي للأوراق المالية (ADX) ببيانات تاريخية تمتد حتى عام 2010 وتحديث يومي للأسعار والمؤشرات الفنية.",
        },
        {
          q: "هل يمكنني تحليل أي سهم إماراتي عبر الشات بوت؟",
          a: "نعم، يمكنك سؤال الشات بوت ARTORO مباشرة بالعربية أو الإنجليزية عن أي سهم إماراتي (مثل إعمار أو الدار أو أدنوك للغاز) للحصول على الدعم والمقاومة ومؤشرات RSI وMACD.",
        },
      ]}
    />
  );
}
