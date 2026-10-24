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

// Pre-render the top Egyptian stocks at build time for instant 0ms responses to
// search engine crawlers and users. The remaining symbols are statically cached
// on first hit via ISR.
const TOP_EGX_SYMBOLS = [
  "comi", "fwry", "hrho", "east", "tmgh", "swdy", "ekho", "abuk",
  "amoc", "mfpc", "etel", "cich", "heli", "btfh", "alfa",
  "acro", "adib", "cieb", "efid", "efih", "egal", "egas", "oras",
  "talm", "esrs", "clho", "orwe", "phdc", "spmd", "alcn"
];

export async function generateStaticParams() {
  return TOP_EGX_SYMBOLS.map((symbol) => ({ symbol }));
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
