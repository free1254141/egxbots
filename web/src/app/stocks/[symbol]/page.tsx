import { getPublicStockSnapshot } from "@/lib/seo/stock-snapshot";
import { notFound, redirect } from "next/navigation";
import StockDetailClient from "./StockDetailClient";
import { Metadata } from "next";
import { getPublicStockDirectory } from "@/lib/seo/stock-directory";
import { selectStockLinks } from "@/lib/seo/sitemap-entries";

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
  const companyName = fund.name || fund.Name || symbol;
  const sector = fund.sector || fund.Sector || "";

  const title = `تحليل وسعر سهم ${companyName} (${symbol}) بالذكاء الاصطناعي`;
  const description = `تحليل سهم ${companyName} (${symbol}) بالإغلاقات اليومية المسجلة، تقييم AI Score، ومؤشرات التحليل الفني في البورصة المصرية. راجع تاريخ البيانات الظاهر بالصفحة.`;

  return {
    title,
    description,
    keywords: [
      symbol,
      companyName,
      `تحليل سهم ${companyName}`,
      `سعر سهم ${companyName}`,
      `تحليل سهم ${symbol}`,
      `توقعات سهم ${symbol}`,
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
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
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
  const companyName = fund.name || fund.Name || symbol;
  const related = selectStockLinks(await getPublicStockDirectory(), symbol, String(fund.sector || fund.Sector || ""));
  const priceDate = (latestPrice as any)?.date || (latestTech as any)?.date;

  // Complete Schema.org Breadcrumbs + WebPage structure for Google Search Console
  const structuredDataGraph = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "BreadcrumbList",
        "itemListElement": [
          { "@type": "ListItem", "position": 1, "name": "الرئيسية", "item": "https://egxbots.com" },
          { "@type": "ListItem", "position": 2, "name": "الأسهم", "item": "https://egxbots.com/stocks" },
          { "@type": "ListItem", "position": 3, "name": companyName, "item": `https://egxbots.com/stocks/${symbol.toLowerCase()}` }
        ]
      },
      {
        "@type": "WebPage",
        "name": `بيانات وتحليل سهم ${companyName} (${symbol})`,
        "url": `https://egxbots.com/stocks/${symbol.toLowerCase()}`,
        ...(priceDate ? { dateModified: priceDate } : {}),
        "description": "إغلاقات ومؤشرات يومية محفوظة؛ بيانات تعليمية وليست أسعارًا لحظية.",
        "publisher": { "@type": "Organization", "name": "EGX BOTS" }
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
