import { Metadata } from "next";
import { getPublicGccMetalsDirectoryWithPrices } from "@/lib/seo/stock-directory";
import MarketDirectoryPage from "@/components/seo/MarketDirectoryPage";

export const preferredRegion = "fra1";
export const revalidate = 604800;

export const metadata: Metadata = {
  title: "دليل أسهم بورصة قطر (QSE) والتحليل الفني بالذكاء الاصطناعي | EGX BOTS",
  description:
    "تصفح جميع أسهم بورصة قطر (QSE) مثل بنك قطر الوطني QNBK ومصرف قطر الإسلامي QIBK وصناعات قطر IQCD وناقلات وأوريدو مع الأسعار ومؤشر RSI وتحليل الذكاء الاصطناعي.",
  keywords: [
    "بورصة قطر QSE",
    "أسهم قطر",
    "سهم بنك قطر الوطني QNBK",
    "سهم صناعات قطر IQCD",
    "سهم مصرف الريان MARK",
    "سهم ناقلات QGTS",
    "تحليل الأسهم القطرية بالذكاء الاصطناعي",
    "EGX BOTS",
  ],
  alternates: { canonical: "https://egxbots.com/markets/qatar" },
  openGraph: {
    title: "دليل أسهم بورصة قطر (QSE) بالذكاء الاصطناعي | EGX BOTS",
    description: "قائمة أسهم بورصة قطر بالريال القطري مع الأسعار اليومية والمؤشرات الفنية ومستويات الدعم والمقاومة.",
    type: "website",
    url: "https://egxbots.com/markets/qatar",
    images: [{ url: "https://egxbots.com/opengraph-image.png", width: 1200, height: 630, alt: "بورصة قطر QSE" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "دليل أسهم بورصة قطر (QSE) | EGX BOTS",
    description: "قائمة أسهم بورصة قطر بالريال القطري مع الأسعار اليومية والمؤشرات الفنية ومستويات الدعم والمقاومة.",
    images: ["https://egxbots.com/opengraph-image.png"],
  },
};

export default async function QatarMarketPage() {
  const all = await getPublicGccMetalsDirectoryWithPrices().catch(() => []);
  const items = all.filter((s) => s.exchange === "QSE");

  return (
    <MarketDirectoryPage
      canonicalUrl="https://egxbots.com/markets/qatar"
      badge="🇶🇦 بورصة قطر (QSE)"
      title="دليل أسهم بورصة قطر (QSE) والتحليل الفني بالذكاء الاصطناعي"
      subtitle="استعرض أسعار ومؤشرات أسهم بورصة قطر (بنك قطر الوطني، مصرف قطر الإسلامي، صناعات قطر، ناقلات، أوريدو، بروة، مسيعيد) بالريال القطري مع مستويات الدعم والمقاومة وتحليل الشات بوت AI."
      currencyLabel="ر.ق"
      items={items}
      otherMarketLinks={[
        { href: "/markets/uae", label: "🇦🇪 أسهم الإمارات (دبي وأبوظبي)" },
        { href: "/markets/gold-silver", label: "🥇 الذهب والفضة" },
        { href: "/stocks", label: "🇪🇬🇸🇦 مصر والسعودية" },
      ]}
      faqs={[
        {
          q: "كم عدد الأسهم القطرية المتاحة للتحليل؟",
          a: "تضم التغطية 50 سهماً مدرجاً في بورصة قطر (QSE) تشمل البنوك والطاقة والصناعة والعقارات والاتصالات ببيانات تاريخية منذ 2010.",
        },
        {
          q: "كيف أستخدم الذكاء الاصطناعي لتحليل أسهم قطر؟",
          a: "افتح صفحة أي سهم قطري أو اسأل الشات بوت مباشرة عن الرمز (مثل QNBK أو IQCD) أو الاسم بالعربية للحصول على قراءة فنية فورية.",
        },
      ]}
    />
  );
}
