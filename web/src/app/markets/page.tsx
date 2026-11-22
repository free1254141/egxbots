import { Metadata } from "next";
import Link from "next/link";
import {
  getPublicStockDirectoryWeekly,
  getPublicTasiStockDirectoryWeekly,
  getPublicGccMetalsDirectoryWeekly,
} from "@/lib/seo/stock-directory";

export const preferredRegion = "fra1";
export const revalidate = 604800;

export const metadata: Metadata = {
  title: "الأسواق العربية والخليجية والذهب (مصر، السعودية، الإمارات، قطر) | EGX BOTS",
  description:
    "دليل شامل لتحليل أسهم الأسواق العربية والخليجية بالذكاء الاصطناعي: البورصة المصرية (EGX)، السوق السعودي تاسي (TASI)، أسهم الإمارات (دبي DFM وأبوظبي ADX)، بورصة قطر (QSE)، والذهب والفضة (XAUUSD & XAGUSD).",
  keywords: [
    "الأسواق الخليجية",
    "تحليل الأسهم الخليجية بالذكاء الاصطناعي",
    "البورصة المصرية EGX",
    "السوق السعودي تاسي TASI",
    "سوق دبي المالي DFM",
    "سوق أبوظبي ADX",
    "بورصة قطر QSE",
    "سعر الذهب XAUUSD",
    "EGX BOTS",
  ],
  alternates: { canonical: "https://egxbots.com/markets" },
  openGraph: {
    title: "الأسواق العربية والخليجية والذهب بالذكاء الاصطناعي | EGX BOTS",
    description:
      "تصفح أدلة الأسهم والمؤشرات الفنية ومستويات الدعم والمقاومة لأسواق مصر والسعودية والإمارات وقطر والذهب والفضة.",
    type: "website",
    url: "https://egxbots.com/markets",
    images: [
      {
        url: "https://egxbots.com/opengraph-image.png",
        width: 1200,
        height: 630,
        alt: "الأسواق العربية والخليجية والذهب EGX BOTS",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "الأسواق العربية والخليجية والذهب | EGX BOTS",
    description:
      "تحليل فني وكمي بالذكاء الاصطناعي لأسهم مصر والسعودية والإمارات وقطر والذهب والفضة.",
    images: ["https://egxbots.com/opengraph-image.png"],
  },
};

export default async function MarketsHubPage() {
  const [egx, tasi, gcc] = await Promise.all([
    getPublicStockDirectoryWeekly().catch(() => []),
    getPublicTasiStockDirectoryWeekly().catch(() => []),
    getPublicGccMetalsDirectoryWeekly().catch(() => []),
  ]);

  const uaeCount = gcc.filter((s) => s.exchange === "DFM" || s.exchange === "ADX").length;
  const qatarCount = gcc.filter((s) => s.exchange === "QSE").length;
  const metalsCount = gcc.filter((s) => s.exchange === "COMMODITIES").length;

  const markets = [
    {
      href: "/stocks",
      badge: "🇪🇬 مصر · EGX",
      title: "البورصة المصرية (EGX)",
      desc: "تغطية كاملة لأسهم EGX30 و EGX70 و EGX100 مع السعر العادل، التوافق الشرعي EGX33، ومستويات الدعم والمقاومة.",
      count: egx.length > 0 ? `${egx.length} سهم` : "جميع الأسهم المصرية",
      accent: "bg-amber-400",
    },
    {
      href: "/stocks?market=tasi",
      badge: "🇸🇦 السعودية · TASI",
      title: "السوق السعودي (تداول / تاسي)",
      desc: "تحليل فني وكمي للأسهم السعودية بالريال (أرامكو، الراجحي، سابك، STC) مع التطهير الشرعي ومؤشرات الزخم.",
      count: tasi.length > 0 ? `${tasi.length} سهم` : "جميع أسهم تاسي",
      accent: "bg-emerald-400",
    },
    {
      href: "/markets/uae",
      badge: "🇦🇪 الإمارات · DFM & ADX",
      title: "أسهم الإمارات (دبي وأبوظبي)",
      desc: "أسهم سوق دبي المالي وسوق أبوظبي للأوراق المالية (إعمار، الدار، أدنوك، العالمية القابضة، بنك أبوظبي الأول).",
      count: uaeCount > 0 ? `${uaeCount} سهم` : "دبي وأبوظبي",
      accent: "bg-sky-400",
    },
    {
      href: "/markets/qatar",
      badge: "🇶🇦 قطر · QSE",
      title: "بورصة قطر (QSE)",
      desc: "أسهم بورصة قطر بالريال القطري (بنك قطر الوطني، مصرف قطر الإسلامي، صناعات قطر، ناقلات، أوريدو).",
      count: qatarCount > 0 ? `${qatarCount} سهم` : "الأسهم القطرية",
      accent: "bg-rose-400",
    },
    {
      href: "/markets/gold-silver",
      badge: "🥇🥈 المعادن العالمية",
      title: "الذهب والفضة (XAUUSD & XAGUSD)",
      desc: "تحليل فني يومي لأونصة الذهب والفضة العالمية بالدولار الأمريكي مع مؤشرات RSI وMACD ونقاط الدعم والمقاومة.",
      count: metalsCount > 0 ? `${metalsCount} أداة` : "XAUUSD & XAGUSD",
      accent: "bg-[#FFE600]",
    },
  ];

  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "الرئيسية", item: "https://egxbots.com" },
          { "@type": "ListItem", position: 2, name: "الأسواق", item: "https://egxbots.com/markets" },
        ],
      },
      {
        "@type": "CollectionPage",
        "@id": "https://egxbots.com/markets#webpage",
        name: "الأسواق العربية والخليجية والذهب | EGX BOTS",
        description:
          "بوابة الأسواق المالية العربية والخليجية المدعومة بالذكاء الاصطناعي: مصر، السعودية، الإمارات، قطر، والذهب والفضة.",
        url: "https://egxbots.com/markets",
        mainEntity: {
          "@type": "ItemList",
          numberOfItems: markets.length,
          itemListElement: markets.map((m, idx) => ({
            "@type": "ListItem",
            position: idx + 1,
            name: m.title,
            url: `https://egxbots.com${m.href}`,
          })),
        },
      },
      {
        "@type": "FAQPage",
        mainEntity: [
          {
            "@type": "Question",
            name: "ما هي الأسواق العربية والخليجية التي يدعمها EGX BOTS؟",
            acceptedAnswer: {
              "@type": "Answer",
              text: "يدعم EGX BOTS البورصة المصرية (EGX)، السوق السعودي تداول (TASI)، أسهم الإمارات في سوق دبي المالي (DFM) وسوق أبوظبي (ADX)، بورصة قطر (QSE)، بالإضافة إلى الذهب والفضة (XAUUSD & XAGUSD).",
            },
          },
          {
            "@type": "Question",
            name: "هل يتم تحديث الأسعار والمؤشرات الفنية يومياً لجميع الأسواق؟",
            acceptedAnswer: {
              "@type": "Answer",
              text: "نعم، يتم تحديث أسعار الإغلاق ومؤشرات التحليل الفني ومستويات الدعم والمقاومة يومياً بعد انتهاء جلسات التداول في كل سوق.",
            },
          },
        ],
      },
    ],
  };

  return (
    <main dir="rtl" className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }}
      />

      <header className="mb-8 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)]">
        <div className="inline-block px-3 py-1 mb-3 text-xs font-black uppercase bg-[#FFE600] text-black border-2 border-black shadow-[2px_2px_0px_#000]">
          🌍 بوابة الأسواق العربية والخليجية والمعادن
        </div>
        <h1 className="text-2xl sm:text-3xl font-black text-black dark:text-white mb-2">
          الأسواق العربية والخليجية والذهب بالذكاء الاصطناعي
        </h1>
        <p className="text-sm sm:text-base font-bold text-zinc-700 dark:text-zinc-300 leading-relaxed mb-4">
          اختر السوق المالي لاستعراض دليل الأسهم، الأسعار اليومية، مؤشرات الزخم RSI وMACD، ومستويات الدعم والمقاومة المحسوبة كمياً.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/chat"
            className="px-4 py-2 text-xs sm:text-sm font-black bg-[#00FF66] text-black border-2 border-black shadow-[3px_3px_0px_#000] hover:bg-[#FFE600] transition-colors"
            prefetch={false}
          >
            اسأل الشات بوت AI عن أي سهم خليجي أو مصري
          </Link>
        </div>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-10">
        {markets.map((m) => (
          <Link
            key={m.href}
            href={m.href}
            className="group flex flex-col justify-between border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 shadow-[5px_5px_0px_0px_rgba(0,0,0,1)] dark:shadow-[5px_5px_0px_0px_rgba(255,255,255,0.25)] hover:-translate-y-0.5 transition-transform"
            prefetch={false}
          >
            <div>
              <div className="flex items-center justify-between gap-2 mb-3">
                <span className={`px-2.5 py-0.5 text-[11px] font-black text-black border-2 border-black ${m.accent}`}>
                  {m.badge}
                </span>
                <span className="text-[11px] font-black text-zinc-500 dark:text-zinc-400">
                  {m.count}
                </span>
              </div>
              <h2 className="text-lg font-black text-black dark:text-white mb-2 group-hover:underline">
                {m.title}
              </h2>
              <p className="text-xs sm:text-sm font-bold text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {m.desc}
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-black/10 dark:border-white/10 text-xs font-black text-emerald-700 dark:text-emerald-400">
              استعراض الأسهم والتحليلات ←
            </div>
          </Link>
        ))}
      </section>
    </main>
  );
}
