import { Metadata } from "next";
import Link from "next/link";
import { createClient } from "@supabase/supabase-js";
import DisclosuresClient, { DisclosuresInitialStats } from "./DisclosuresClient";
import type { DisclosureItem } from "@/lib/disclosures-analytics";
import { analyzeDisclosures, DisclosuresAnalyticsResult, SymbolPriceInfo } from "@/lib/disclosures-analytics";

export const revalidate = 604800; // 7-day weekend-proof ISR; invalidated via /api/revalidate

export const metadata: Metadata = {
  title: "رادار إفصاحات البورصة المصرية وتعاملات الداخليين (أداة مجانية)",
  description:
    "أداة مجانية لمتابعة إفصاحات البورصة المصرية لحظياً: نماذج المادة 30، تعاملات كبار المساهمين والمطلعين (Insiders)، متوسط تكلفة الشراء VWAP، وخريطة السيولة بالذكاء الاصطناعي.",
  keywords: [
    "إفصاحات البورصة المصرية",
    "رادار إفصاحات البورصة",
    "تعاملات الداخليين البورصة المصرية",
    "تعاملات كبار المساهمين",
    "نماذج المادة 30 البورصة المصرية",
    "أخبار وإفصاحات الشركات المقيدة",
    "تجميع الداخليين",
    "إفصاحات EGX اليوم",
    "أداة تحليل الإفصاحات مجانا",
    "EGX Disclosures Radar",
    "EGX BOTS",
  ],
  alternates: {
    canonical: "https://egxbots.com/disclosures",
  },
  openGraph: {
    title: "رادار إفصاحات البورصة المصرية وتعاملات الداخليين (مجاناً) | EGX BOTS",
    description:
      "متابعة حية لإفصاحات الشركات المقيدة بالبورصة المصرية، نماذج المادة 30، وتحليل تدفقات السيولة ومتوسط تكلفة الداخليين بالذكاء الاصطناعي.",
    url: "https://egxbots.com/disclosures",
    siteName: "EGX BOTS",
    locale: "ar_EG",
    type: "website",
    images: [
      {
        url: "https://egxbots.com/opengraph-image.png",
        width: 1200,
        height: 630,
        alt: "رادار إفصاحات البورصة المصرية وتعاملات الداخليين - EGX BOTS",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "رادار إفصاحات البورصة المصرية وتعاملات الداخليين | EGX BOTS",
    description:
      "تابع إفصاحات البورصة المصرية، نماذج المادة 30، وصفقات الداخليين وكبار المساهمين مع ملخص الذكاء الاصطناعي مجاناً.",
    images: ["https://egxbots.com/opengraph-image.png"],
  },
};

const INITIAL_PAGE_SIZE = 24;

async function getInitialDisclosuresData(): Promise<{
  items: DisclosureItem[];
  allPool: DisclosureItem[];
  stats: DisclosuresInitialStats;
  analytics: DisclosuresAnalyticsResult;
  priceMap: Record<string, SymbolPriceInfo>;
}> {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const supabaseKey =
    process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseKey) {
    const emptyAnalytics = analyzeDisclosures([], {});
    return {
      items: [],
      allPool: [],
      stats: { total: 0, buys: 0, sells: 0, shareholding: 0 },
      analytics: emptyAnalytics,
      priceMap: {},
    };
  }

  const supabase = createClient(supabaseUrl, supabaseKey);

  // Fetch initial batch of disclosures, stats pool, latest prices, and company fundamentals in parallel
  const [pageRes, statsRes, pricesRes, fundamentalsRes] = await Promise.all([
    supabase
      .from("egx_disclosures")
      .select(
        "id, symbol, company_name, disclosure_type, disclosure_date, title, raw_content, ai_summary, sentiment, action_type, shares_count, stake_before, stake_after, party_name, party_role, source_url, metadata",
        { count: "exact" }
      )
      .order("disclosure_date", { ascending: false })
      .order("created_at", { ascending: false })
      .limit(INITIAL_PAGE_SIZE),
    supabase
      .from("egx_disclosures")
      .select(
        "id, symbol, company_name, disclosure_type, disclosure_date, title, raw_content, ai_summary, sentiment, action_type, shares_count, stake_before, stake_after, party_name, party_role, source_url, metadata"
      )
      .order("disclosure_date", { ascending: false })
      .limit(2000),
    supabase
      .from("stock_technical_indicators")
      .select("symbol, close, change_pct")
      .limit(350),
    supabase
      .from("stock_fundamentals")
      .select("symbol, data")
      .limit(350),
  ]);

  const allDisclosures = (statsRes.data || []) as DisclosureItem[];
  const priceMap: Record<string, SymbolPriceInfo> = {};
  if (pricesRes.data) {
    for (const p of pricesRes.data) {
      if (p.symbol && p.close != null) {
        priceMap[p.symbol.toUpperCase()] = {
          close: Number(p.close),
          change_pct: p.change_pct != null ? Number(p.change_pct) : 0,
        };
      }
    }
  }

  // Enrich priceMap with verified marketCap and totalShares from fundamentals
  if (fundamentalsRes.data) {
    for (const f of fundamentalsRes.data) {
      if (f.symbol && f.data && typeof f.data === "object") {
        const sym = f.symbol.toUpperCase();
        const mc = (f.data as Record<string, unknown>).marketCap;
        if (typeof mc === "number" && mc > 0) {
          if (priceMap[sym]) {
            priceMap[sym].market_cap = mc;
            if (priceMap[sym].close > 0) {
              priceMap[sym].total_shares = Math.round(mc / priceMap[sym].close);
            }
          } else {
            priceMap[sym] = {
              close: 0,
              change_pct: 0,
              market_cap: mc,
            };
          }
        }
      }
    }
  }

  const analytics = analyzeDisclosures(allDisclosures, priceMap);

  const total = pageRes.count ?? allDisclosures.length;
  const buys = allDisclosures.filter((d) => d.action_type === "buy" || d.sentiment === "bullish").length;
  const sells = allDisclosures.filter((d) => d.action_type === "sell" || d.sentiment === "bearish").length;
  const shareholding = allDisclosures.filter(
    (d) => d.disclosure_type === "major_shareholders" || d.stake_after != null
  ).length;

  return {
    items: (pageRes.data || []) as DisclosureItem[],
    allPool: allDisclosures,
    stats: { total, buys, sells, shareholding },
    analytics,
    priceMap,
  };
}

export default async function DisclosuresPage() {
  const { items, allPool, stats, analytics, priceMap } = await getInitialDisclosuresData();

  const recentSymbols = Array.from(
    new Map(
      items
        .filter((d) => d.symbol && d.symbol.trim().length > 0)
        .map((d) => [d.symbol!.trim().toUpperCase(), d.company_name || d.symbol!.trim().toUpperCase()])
    ).entries()
  ).slice(0, 14);

  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "SoftwareApplication",
        "@id": "https://egxbots.com/disclosures#tool",
        name: "رادار إفصاحات البورصة المصرية وتعاملات الداخليين",
        alternateName: ["EGX Disclosures & Insider Radar", "رادار المادة 30"],
        applicationCategory: "FinanceApplication",
        operatingSystem: "Web",
        url: "https://egxbots.com/disclosures",
        description:
          "أداة مجانية لتحليل إفصاحات الشركات المقيدة بالبورصة المصرية، صفقات الداخليين (Insiders)، نماذج المادة 30، وحساب متوسط تكلفة الشراء VWAP وخريطة السيولة.",
        offers: {
          "@type": "Offer",
          price: "0",
          priceCurrency: "EGP",
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "الرئيسية", item: "https://egxbots.com" },
          { "@type": "ListItem", position: 2, name: "رادار الإفصاحات والداخليين", item: "https://egxbots.com/disclosures" },
        ],
      },
      {
        "@type": "FAQPage",
        mainEntity: [
          {
            "@type": "Question",
            name: "ما هي أداة رادار إفصاحات البورصة المصرية في EGX BOTS وهل هي مجانية؟",
            acceptedAnswer: {
              "@type": "Answer",
              text: "نعم، رادار الإفصاحات أداة مجانية بالكامل تتابع إفصاحات الشركات الرسمية في البورصة المصرية، قرارات مجالس الإدارة، نماذج المادة 30 لهيكل كبار المساهمين، وصفقات الشراء والبيع للداخليين والمطلعين مع تلخيص فوري بالذكاء الاصطناعي.",
            },
          },
          {
            "@type": "Question",
            name: "ما أهمية متابعة تعاملات الداخليين ومتوسط تكلفتهم (VWAP)؟",
            acceptedAnswer: {
              "@type": "Answer",
              text: "تُظهر صفقات الداخليين والمؤسسات ما إذا كان المساهمون الرئيسيون وأعضاء مجلس الإدارة يقومون بتجميع السهم أم بيعه. تساعدك أداة مقارنة السعر الحالي بمتوسط تكلفة الداخليين على معرفة الأسهم التي تتداول قرب أو أسفل سعر شراء المطلعين.",
            },
          },
          {
            "@type": "Question",
            name: "ما هي نماذج المادة 30 لهيكل المساهمين؟",
            acceptedAnswer: {
              "@type": "Answer",
              text: "نماذج المادة 30 هي إفصاحات دورية رسمية تصدرها الشركات المقيدة في البورصة المصرية توضح نسب ملكية المؤسسين وكبار المساهمين فوق 5% ونسبة الأسهم حرة التداول (Free Float).",
            },
          },
        ],
      },
    ],
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }}
      />
      <DisclosuresClient
        initialDisclosures={items}
        initialPool={allPool}
        initialStats={stats}
        initialAnalytics={analytics}
        priceMap={priceMap}
      />
      <section
        dir="rtl"
        aria-label="دليل أداة الإفصاحات والأدوات المجانية"
        className="mx-auto max-w-[1600px] px-4 pb-10 sm:px-6"
      >
        <div className="border-2 border-black/15 dark:border-white/15 bg-white/80 dark:bg-zinc-900/70 p-5 sm:p-6 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs sm:text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
            <div>
              <h2 className="font-black text-zinc-950 dark:text-white mb-1.5">
                ما هي أداة رادار الإفصاحات والداخليين؟
              </h2>
              <p>
                أداة مجانية لقراءة وتحليل إفصاحات البورصة المصرية لحظياً بالذكاء الاصطناعي، مع تصنيف فوري لصفقات شراء وبيع الداخليين والمطلعين، ومتابعة نماذج المادة 30 لهيكل كبار المساهمين.
              </p>
            </div>
            <div>
              <h2 className="font-black text-zinc-950 dark:text-white mb-1.5">
                لماذا نراقب متوسط تكلفة الداخليين (VWAP)؟
              </h2>
              <p>
                يحسب الرادار صافي كمية الأسهم المجمّعة أو المباعة لكل شركة ويقارن السعر السوقي الحالي بمتوسط سعر تنفيذ صفقات المساهمين الرئيسيين لاكتشاف مناطق التجميع مبكراً.
              </p>
            </div>
            <div>
              <h2 className="font-black text-zinc-950 dark:text-white mb-1.5">
                أدوات مجانية مكملة على المنصة
              </h2>
              <nav className="flex flex-wrap gap-2 pt-1 font-bold text-xs">
                <Link href="/fair-value" className="underline underline-offset-4 text-emerald-700 dark:text-emerald-400 hover:text-emerald-500">
                  محدد السعر العادل (EGX & TASI)
                </Link>
                <Link href="/sharia" className="underline underline-offset-4 text-emerald-700 dark:text-emerald-400 hover:text-emerald-500">
                  الأسهم الحلال وحاسبة التطهير
                </Link>
                <Link href="/scanner/technical" className="underline underline-offset-4 text-amber-700 dark:text-amber-400 hover:text-amber-500">
                  الماسح الفني المجاني
                </Link>
                <Link href="/scanner/market" className="underline underline-offset-4 text-indigo-700 dark:text-indigo-400 hover:text-indigo-500">
                  مؤشرات واتساع السوق
                </Link>
                <Link href="/reports" className="underline underline-offset-4 text-zinc-800 dark:text-zinc-200 hover:text-amber-500">
                  التقارير اليومية
                </Link>
              </nav>
            </div>
          </div>

          {recentSymbols.length > 0 && (
            <div className="pt-4 border-t border-black/10 dark:border-white/10">
              <h3 className="text-xs font-black text-zinc-900 dark:text-white mb-2.5">
                أحدث الشركات في رادار الإفصاحات (انتقل لصفحة تحليل السهم):
              </h3>
              <div className="flex flex-wrap gap-2">
                {recentSymbols.map(([sym, name]) => (
                  <Link
                    key={sym}
                    href={`/stocks/${sym.toLowerCase()}`}
                    prefetch={false}
                    className="px-2.5 py-1 text-[11px] font-bold bg-zinc-100 dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 border border-zinc-300 dark:border-zinc-700 hover:border-amber-500 transition-colors"
                  >
                    {name} ({sym})
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </>
  );
}
