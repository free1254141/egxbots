import { getPublicStockSnapshot } from "@/lib/seo/stock-snapshot";
import { notFound, redirect } from "next/navigation";
import StockDetailClient from "./StockDetailClient";
import { Metadata } from "next";
import { getPublicStockDirectory } from "@/lib/seo/stock-directory";
import { selectStockLinks } from "@/lib/seo/sitemap-entries";
import { getCanonicalStockName } from "@/lib/ai/stock-names";

// Pin to Frankfurt so every ISR render shares the same market-query-cache
// KV namespace. Without this, Vercel routes /stocks/* to the edge region
// closest to the visitor (iad1, sfo1...) and each region cold-fills Supabase
// independently -- wasting CPU and multiplying DB reads for identical data.
export const preferredRegion = "fra1";

// Stock price and technical data is updated once per day by the daily job.
// 1-hour ISR was overly aggressive; 24h matches actual data cadence and
// drastically cuts the number of re-renders Vercel has to run per symbol.
export const revalidate = 86400;

// Complete Egyptian stock exchange symbol directory for 100% pre-rendering at build time.
// Pre-rendering both lowercase and uppercase eliminates dynamic Lambda executions when crawlers request either format.
const ALL_FALLBACK_EGX_SYMBOLS = [
  "aalr","abuk","acamd","acap","acgc","acro","actf","adci","adib","adpc","adri","afdi","afmc","agig","aidc","aih","aind","aivcb","ajwa","alcn","alex","alra","alum","amer","ames","amia","amii","amoc","ampi","anfi","appc","apsw","arab","arcc","areh","areha","arva","ascm","aspi","atlc","atqa","auto","axph","bcap","bidi","bigp","binv","bioc","bony","btfh","caed","cana","ccap","ccrs","cefm","cera","cfgh","cich","cieb","cilb","cira","cirf","clho","cnfn","comi","copr","cosg","cpci","cpme","crst","csag","daph","dcrc","dein","dgtz","domt","dscw","dtpp","ealr","easb","east","ebsc","ecap","edbm","edfm","eeii","efic","efid","efih","egal","egas","egbe","egch","egref","egsa","egts","ehdr","eitp","ekhoa","elec","elka","elna","elsh","elwa","emfd","engc","eosb","epco","eppk","esrs","etel","etrs","expa","fait","faita","fcmd","ferc","fire","fnar","ftns","fwry","gbco","gdwa","ggcc","ggrn","gihd","gmci","gour","gpim","gppl","grca","gssc","gtex","gthe","gtwl","hbco","hdbk","heli","hrho","ibct","icfc","icid","icle","idre","ieec","ifap","ineg","infi","irax","iron","isma","ismq","isph","jufo","kabo","kasabf","kora","krdi","kwin","kzpc","lcsw","luts","maal","masr","matd","mbeg","mbsc","mcqe","mcro","medp","megm","mena","mepa","mfpc","mfsc","mhot","mich","mils","miph","mkit","moed","moil","moin","mosc","mpci","mpco","mprc","mtie","naho","napr","nare","nbke","nccw","ncgc","ndrl","neda","nhps","ninh","niph","obri","ocdi","ocph","odin","ofh","oih","olfi","oras","orhd","ormt","orwe","pach","phar","phdc","phgc","phtv","pioh","poul","prcl","prdc","prmh","qnba","qnbe","racc","rakt","raya","rkaz","rmda","roto","rrei","rtvc","rubx","saib","saud","scem","scfm","scts","sdti","seig","seiga","simo","sipc","skpc","smfr","smpp","snfc","spht","spin","spmd","srwa","sugr","svce","swdy","talm","tanm","taqa","tmgh","tora","trto","twsa","tycn","uasg","ubee","uefm","uegc","unip","unit","upms","utop","valu","vert","vlmr","vlmra","wcdf","wkol","zeot","zmid"
];

export async function generateStaticParams() {
  const symbolSet = new Set<string>();
  try {
    const directory = await getPublicStockDirectory();
    if (Array.isArray(directory) && directory.length > 0) {
      for (const stock of directory) {
        if (stock.symbol) {
          symbolSet.add(stock.symbol.toLowerCase());
        }
      }
    }
  } catch (err) {
    console.warn("[stocks] Failed to load full directory for static params, falling back to all catalog symbols:", err);
  }

  // Ensure 100% catalog coverage even if live directory query failed or was incomplete
  for (const s of ALL_FALLBACK_EGX_SYMBOLS) {
    symbolSet.add(s.toLowerCase());
  }

  const params: Array<{ symbol: string }> = [];
  for (const sym of symbolSet) {
    params.push({ symbol: sym.toLowerCase() });
    params.push({ symbol: sym.toUpperCase() });
  }
  return params;
}

interface PageProps {
  params: Promise<{
    symbol: string;
  }>;
}

// Generate dynamic metadata for SEO search indexers
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const raw = (await params).symbol;
  const symbol = raw.toUpperCase();
  const snapshot = await getPublicStockSnapshot(symbol);
  if (!snapshot.fundamentals && !snapshot.latestPrice) notFound();
  const fundRow = snapshot.fundamentals;
  const fund = fundRow?.data || {};

  // Always resolve official Arabic and English company names for high-CTR Egyptian Google searches
  const canonical = getCanonicalStockName(symbol);
  const nameAr = canonical.name_ar || fund.name || fund.Name || symbol;
  const nameEn = canonical.name_en && canonical.name_en !== symbol
    ? canonical.name_en
    : String(fund.name || fund.Name || symbol);

  // Short Arabic display name for title (e.g., "العربية للألومنيوم", "أبو قير للأسمدة", "إم بي للهندسة")
  const shortAr = nameAr
    .replace(/^(?:شركة|مجموعة|بنك)\s+/g, (m: string) => (m.includes("بنك") ? "بنك " : ""))
    .trim();

  const title = shortAr && shortAr !== symbol
    ? `سعر سهم ${shortAr} (${symbol}) اليوم | تحليل فني ودعم ومقاومة`
    : `سعر وتحليل سهم ${symbol} اليوم | نقاط الدعم والمقاومة`;

  const latest = (snapshot.latestPrice || null) as { close?: number | string; date?: string } | null;
  const lastClose = Number(latest?.close ?? 0);
  const lastDate = String(latest?.date ?? "").slice(0, 10);
  const pricePart =
    Number.isFinite(lastClose) && lastClose > 0
      ? `آخر سعر إغلاق ${lastClose.toLocaleString("en-US", { maximumFractionDigits: 2 })} ج.م${lastDate ? ` (${lastDate})` : ""}. `
      : "";
  const description = `${pricePart}تعرف على سعر سهم ${nameAr} (${symbol}${nameEn !== symbol ? ` - ${nameEn}` : ""}) اليوم في البورصة المصرية: مستويات الدعم والمقاومة، السعر العادل، ومؤشر الذكاء الاصطناعي AI Score.`;

  return {
    title,
    description,
    keywords: [
      symbol,
      nameAr,
      nameEn,
      `سعر سهم ${nameAr}`,
      `سهم ${nameAr}`,
      `تحليل سهم ${nameAr}`,
      `توقعات سهم ${nameAr}`,
      `سعر سهم ${symbol}`,
      `تحليل سهم ${symbol}`,
      `${symbol} stock price`,
      "تحليل الأسهم المصرية بالذكاء الاصطناعي",
      "EGX BOTS",
      "egxbots",
      "البورصة المصرية",
      "EGX"
    ],
    alternates: {
      canonical: `https://egxbots.com/stocks/${symbol.toLowerCase()}`,
    },
    openGraph: {
      title,
      description,
      type: "website",
      url: `https://egxbots.com/stocks/${symbol.toLowerCase()}`,
      images: [
        {
          url: "https://egxbots.com/opengraph-image.png",
          width: 1200,
          height: 630,
          alt: title,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: ["https://egxbots.com/opengraph-image.png"],
    },
  };
}

export default async function StockDetailPage({ params }: PageProps) {
  const rawSymbol = (await params).symbol;
  // Enforce lowercase canonical URL: redirect uppercase visits (e.g. /stocks/COMI -> /stocks/comi)
  if (rawSymbol !== rawSymbol.toLowerCase()) {
    redirect(`/stocks/${rawSymbol.toLowerCase()}`);
  }

  const symbol = rawSymbol.toUpperCase();
  const snapshot = await getPublicStockSnapshot(symbol);
  const { fundamentals: fundRow, latestPrice, latestTech, historicalPrices, latestScan } = snapshot;
  if (!fundRow && !latestPrice) notFound();
  const exchange = 'EGX';

  const fund = fundRow?.data || {};
  const canonical = getCanonicalStockName(symbol);
  const nameAr = canonical.name_ar || fund.name || fund.Name || symbol;
  const nameEn = canonical.name_en && canonical.name_en !== symbol
    ? canonical.name_en
    : String(fund.name || fund.Name || symbol);

  const related = selectStockLinks(await getPublicStockDirectory(), symbol, String(fund.sector || fund.Sector || canonical.sector || ""));
  const priceDate = (latestPrice as any)?.date || (latestTech as any)?.date;

  const lastPriceVal = Number((latestPrice as any)?.close ?? 0);

  // Complete Schema.org Breadcrumbs + WebPage + FinancialProduct + FAQPage for Google & AI Engines (GEO)
  const structuredDataGraph = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "BreadcrumbList",
        "itemListElement": [
          { "@type": "ListItem", "position": 1, "name": "الرئيسية", "item": "https://egxbots.com" },
          { "@type": "ListItem", "position": 2, "name": "دليل الأسهم المصرية", "item": "https://egxbots.com/stocks" },
          { "@type": "ListItem", "position": 3, "name": `سهم ${nameAr} (${symbol})`, "item": `https://egxbots.com/stocks/${symbol.toLowerCase()}` }
        ]
      },
      {
        "@type": "WebPage",
        "name": `سعر وتحليل سهم ${nameAr} (${symbol}) في البورصة المصرية`,
        "alternateName": `${nameEn} (${symbol}) Stock Analysis`,
        "url": `https://egxbots.com/stocks/${symbol.toLowerCase()}`,
        ...(priceDate ? { dateModified: priceDate } : {}),
        "description": `بيانات فنية وسعر إغلاق سهم ${nameAr} (${symbol} - ${nameEn}) بالبورصة المصرية مع تقييمات الذكاء الاصطناعي ومستويات الدعم والمقاومة.`,
        "publisher": { "@type": "Organization", "name": "EGX BOTS", "url": "https://egxbots.com" }
      },
      ...(Number.isFinite(lastPriceVal) && lastPriceVal > 0 ? [{
        "@type": "FinancialProduct",
        "name": `سهم ${nameAr} (${symbol})`,
        "alternateName": `${nameEn} (${symbol})`,
        "tickerSymbol": symbol,
        "exchange": "EGX",
        "currency": "EGP",
        "description": `سهم ${nameAr} (${nameEn}) المتداول في البورصة المصرية تحت رمز ${symbol}.`,
        "offers": {
          "@type": "Offer",
          "price": lastPriceVal,
          "priceCurrency": "EGP",
          ...(priceDate ? { "priceValidUntil": priceDate } : {})
        }
      }] : []),
      {
        "@type": "FAQPage",
        "mainEntity": [
          {
            "@type": "Question",
            "name": `ما هو سعر سهم ${nameAr} (${symbol}) اليوم في البورصة المصرية؟`,
            "acceptedAnswer": {
              "@type": "Answer",
              "text": Number.isFinite(lastPriceVal) && lastPriceVal > 0
                ? `بلغ آخر سعر إغلاق مسجل لسهم ${nameAr} (${symbol}) ما قيمته ${lastPriceVal} جنيه مصري ${priceDate ? `بتاريخ ${priceDate}` : ''}.`
                : `يمكنك الاطلاع على أحدث سعر إغلاق وبيانات التداول لسهم ${nameAr} (${symbol}) مباشرة عبر منصة EGX BOTS.`
            }
          },
          {
            "@type": "Question",
            "name": `ما هي مستويات الدعم والمقاومة لسهم ${nameAr} (${symbol})؟`,
            "acceptedAnswer": {
              "@type": "Answer",
              "text": `تعتمد منصة EGX BOTS على خوارزميات التحليل الفني الكمي لحساب مستويات الدعم والمقاومة المحورية (Pivot Points S1, S2, R1, R2) ومؤشرات الزخم RSI و MACD لسهم ${nameAr} (${symbol}) بشكل يومي بعد إغلاق الجلسة.`
            }
          },
          {
            "@type": "Question",
            "name": `كيف يتم حساب السعر العادل وتقييم الذكاء الاصطناعي لسهم ${nameAr} (${symbol})؟`,
            "acceptedAnswer": {
              "@type": "Answer",
              "text": `يتم حساب التقييم الكمي AI Score ومؤشر السعر العادل لسهم ${nameAr} (${symbol}) عبر دمج مضاعفات الربحية والقيمة الدفترية مع مؤشرات السيولة التاريخية دون أي تحيز بشري، لأغراض البحث والدراسة الإحصائية.`
            }
          }
        ]
      }
    ]
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredDataGraph).replace(/</g, '\\u003c') }}
      />
      <StockDetailClient
        symbol={symbol}
        exchange={exchange}
        fundamentals={fundRow}
        latestPrice={latestPrice}
        latestTech={latestTech}
        historicalPrices={historicalPrices}
        latestScan={latestScan}
        relatedStocks={related.stocks}
        relatedBasis={related.basis}
      />
    </>
  );
}
