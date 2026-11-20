import { getPublicStockSnapshot, getPublicStockPageBundle } from "@/lib/seo/stock-snapshot";
import { notFound, redirect } from "next/navigation";
import StockDetailClient from "./StockDetailClient";
import { Metadata } from "next";
import {
  getPublicStockDirectory,
  getPublicStockDirectoryWeekly,
  getPublicTasiStockDirectoryWeekly,
  getPublicGccMetalsDirectoryWeekly,
} from "@/lib/seo/stock-directory";
import { selectStockLinks } from "@/lib/seo/sitemap-entries";
import { getCanonicalStockName } from "@/lib/ai/stock-names";
import { SAUDI_STOCK_NAMES_AR, isSaudiSymbol } from "@/lib/saudi-stocks";
import type { MarketMode } from "@/lib/supabase/route-data";

// Pin to Frankfurt so every ISR render shares the same market-query-cache
// KV namespace. Without this, Vercel routes /stocks/* to the edge region
// closest to the visitor (iad1, sfo1...) and each region cold-fills Supabase
// independently -- wasting CPU and multiplying DB reads for identical data.
export const preferredRegion = "fra1";

// Stock price and technical data is invalidated on-demand via POST /api/revalidate
// after each trading day's pipeline finishes. A 7-day (604800s) ISR TTL prevents
// cache expiration across Thursday->Sunday weekends and multi-day holidays.
export const revalidate = 604800;

// Complete Egyptian stock exchange symbol directory for 100% pre-rendering at build time.
// Pre-rendering both lowercase and uppercase eliminates dynamic Lambda executions when crawlers request either format.
const ALL_FALLBACK_EGX_SYMBOLS = [
  "aalr","abuk","acamd","acap","acgc","acro","actf","adci","adib","adpc","adri","afdi","afmc","agig","aidc","aih","aind","aivcb","ajwa","alcn","alex","alra","alum","amer","ames","amia","amii","amoc","ampi","anfi","appc","apsw","arab","arcc","areh","areha","arva","ascm","aspi","atlc","atqa","auto","axph","bcap","bidi","bigp","binv","bioc","bony","btfh","caed","cana","ccap","ccrs","cefm","cera","cfgh","cich","cieb","cilb","cira","cirf","clho","cnfn","comi","copr","cosg","cpci","cpme","crst","csag","daph","dcrc","dein","dgtz","domt","dscw","dtpp","ealr","easb","east","ebsc","ecap","edbm","edfm","eeii","efic","efid","efih","egal","egas","egbe","egch","egref","egsa","egts","ehdr","eitp","ekhoa","elec","elka","elna","elsh","elwa","emfd","engc","eosb","epco","eppk","esrs","etel","etrs","expa","fait","faita","fcmd","ferc","fire","fnar","ftns","fwry","gbco","gdwa","ggcc","ggrn","gihd","gmci","gour","gpim","gppl","grca","gssc","gtex","gthe","gtwl","hbco","hdbk","heli","hrho","ibct","icfc","icid","icle","idre","ieec","ifap","ineg","infi","irax","iron","isma","ismq","isph","jufo","kabo","kasabf","kora","krdi","kwin","kzpc","lcsw","luts","maal","masr","matd","mbeg","mbsc","mcqe","mcro","medp","megm","mena","mepa","mfpc","mfsc","mhot","mich","mils","miph","mkit","moed","moil","moin","mosc","mpci","mpco","mprc","mtie","naho","napr","nare","nbke","nccw","ncgc","ndrl","neda","nhps","ninh","niph","obri","ocdi","ocph","odin","ofh","oih","olfi","oras","orhd","ormt","orwe","pach","phar","phdc","phgc","phtv","pioh","poul","prcl","prdc","prmh","qnba","qnbe","racc","rakt","raya","rkaz","rmda","roto","rrei","rtvc","rubx","saib","saud","scem","scfm","scts","sdti","seig","seiga","simo","sipc","skpc","smfr","smpp","snfc","spht","spin","spmd","srwa","sugr","svce","swdy","talm","tanm","taqa","tmgh","tora","trto","twsa","tycn","uasg","ubee","uefm","uegc","unip","unit","upms","utop","valu","vert","vlmr","vlmra","wcdf","wkol","zeot","zmid"
];

export async function generateStaticParams() {
  const symbolSet = new Set<string>();
  const [egxResult, tasiResult, gccResult] = await Promise.allSettled([
    getPublicStockDirectoryWeekly(),
    getPublicTasiStockDirectoryWeekly(),
    getPublicGccMetalsDirectoryWeekly(),
  ]);

  if (egxResult.status === "fulfilled" && Array.isArray(egxResult.value)) {
    for (const stock of egxResult.value) {
      if (stock.symbol) {
        symbolSet.add(stock.symbol.toLowerCase());
      }
    }
  } else if (egxResult.status === "rejected") {
    console.warn("[stocks] Failed to load EGX directory for static params:", egxResult.reason);
  }

  if (tasiResult.status === "fulfilled" && Array.isArray(tasiResult.value)) {
    for (const stock of tasiResult.value) {
      if (stock.symbol) {
        symbolSet.add(stock.symbol.toLowerCase().replace(/\.(sr|sa|tadawul)$/i, ""));
      }
    }
  } else if (tasiResult.status === "rejected") {
    console.warn("[stocks] Failed to load TASI directory for static params:", tasiResult.reason);
  }

  if (gccResult.status === "fulfilled" && Array.isArray(gccResult.value)) {
    for (const stock of gccResult.value) {
      if (stock.symbol) {
        const lowerSym = stock.symbol.toLowerCase();
        const ex = String((stock as { exchange?: string }).exchange || "").toLowerCase();
        if (ex && symbolSet.has(lowerSym)) {
          symbolSet.add(`${lowerSym}.${ex}`);
        } else {
          symbolSet.add(lowerSym);
        }
      }
    }
  }
  symbolSet.add("adib.adx");
  symbolSet.add("taqa.adx");

  // Ensure 100% catalog coverage even if live directory query failed or was incomplete
  for (const s of ALL_FALLBACK_EGX_SYMBOLS) {
    symbolSet.add(s.toLowerCase());
  }
  for (const s of Object.keys(SAUDI_STOCK_NAMES_AR)) {
    symbolSet.add(s.toLowerCase());
  }

  const params: Array<{ symbol: string }> = [];
  for (const sym of symbolSet) {
    params.push({ symbol: sym.toLowerCase() });
  }
  return params;
}

interface PageProps {
  params: Promise<{
    symbol: string;
  }>;
}

function resolveSymbolAndMarket(rawSymbol: string): {
  cleanSymbol: string;
  marketMode: MarketMode;
  explicitExchange?: "DFM" | "ADX" | "QSE" | "COMMODITIES";
} {
  const upper = rawSymbol.toUpperCase();
  const gccMatch = upper.match(/^([A-Z0-9._-]+)\.(DFM|ADX|QSE|COMMODITIES)$/i);
  if (gccMatch) {
    const ex = gccMatch[2].toUpperCase() as "DFM" | "ADX" | "QSE" | "COMMODITIES";
    const mode: MarketMode = ex === "QSE" ? "qatar" : "uae";
    return {
      cleanSymbol: gccMatch[1],
      marketMode: mode,
      explicitExchange: ex,
    };
  }
  const stripped = upper.replace(/\.(SR|SA|TADAWUL)$/i, "");
  const saudi = isSaudiSymbol(upper) || /^\d{4}$/.test(stripped);
  return {
    cleanSymbol: saudi ? stripped : upper,
    marketMode: saudi ? "tasi" : "egx",
  };
}

// Generate dynamic metadata for SEO search indexers
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const raw = (await params).symbol;
  if (raw !== raw.toLowerCase()) {
    return {
      alternates: {
        canonical: `https://egxbots.com/stocks/${raw.toLowerCase().replace(/\.(sr|sa|tadawul)$/i, "")}`,
      },
    };
  }
  const { cleanSymbol: symbol, marketMode, explicitExchange } = resolveSymbolAndMarket(raw);
  const canonicalSlug = explicitExchange
    ? `${symbol.toLowerCase()}.${explicitExchange.toLowerCase()}`
    : symbol.toLowerCase();
  const isSaudi = marketMode === "tasi";
  const { snapshot } = typeof getPublicStockPageBundle === "function"
    ? await getPublicStockPageBundle(symbol, marketMode, explicitExchange)
    : { snapshot: await getPublicStockSnapshot(symbol, marketMode, explicitExchange) };
  if (!snapshot.fundamentals && !snapshot.latestPrice) notFound();
  const fundRow = snapshot.fundamentals;
  const fund = fundRow?.data || {};

  const actualExchange = String(
    fund.exchange || fundRow?.exchange || (snapshot.latestPrice as any)?.exchange || (isSaudi ? "TADAWUL" : "EGX")
  ).toUpperCase();
  const isCommodities = actualExchange === "COMMODITIES";
  const isUae = actualExchange === "DFM" || actualExchange === "ADX";
  const isQatar = actualExchange === "QSE";

  // Resolve official Arabic and English company names for high-CTR searches
  const canonical = isSaudi || isUae || isQatar || isCommodities
    ? { name_ar: symbol, name_en: symbol, sector: "" }
    : getCanonicalStockName(symbol);
  const nameAr = isSaudi || isUae || isQatar || isCommodities
    ? (fund.name_ar || SAUDI_STOCK_NAMES_AR[symbol] || fund.name || fund.Name || symbol)
    : (canonical.name_ar || fund.name || fund.Name || symbol);
  const nameEn = isSaudi || isUae || isQatar || isCommodities
    ? String(fund.name || fund.Name || SAUDI_STOCK_NAMES_AR[symbol] || symbol)
    : (canonical.name_en && canonical.name_en !== symbol
      ? canonical.name_en
      : String(fund.name || fund.Name || symbol));

  // Short Arabic display name for title
  const shortAr = nameAr
    .replace(/^(?:شركة|مجموعة|بنك|مصرف)\s+/g, (m: string) => (m.includes("بنك") ? "بنك " : m.includes("مصرف") ? "مصرف " : ""))
    .trim();

  const title = shortAr && shortAr !== symbol
    ? (isCommodities
      ? `سعر ${shortAr} (${symbol}) اليوم | التحليل الفني ومستويات الدعم والمقاومة`
      : isSaudi
        ? `سعر سهم ${shortAr} (${symbol}) اليوم في تاسي | تحليل فني ودعم ومقاومة`
        : isUae
          ? `سعر سهم ${shortAr} (${symbol}) اليوم في سوق ${actualExchange === "DFM" ? "دبي" : "أبوظبي"} | تحليل فني`
          : isQatar
            ? `سعر سهم ${shortAr} (${symbol}) اليوم في بورصة قطر | تحليل فني ودعم ومقاومة`
            : `سعر سهم ${shortAr} (${symbol}) اليوم | تحليل فني ودعم ومقاومة`)
    : `سعر وتحليل ${symbol} اليوم | نقاط الدعم والمقاومة`;

  const latest = (snapshot.latestPrice || null) as { close?: number | string; date?: string } | null;
  const lastClose = Number(latest?.close ?? 0);
  const lastDate = String(latest?.date ?? "").slice(0, 10);
  const currencyAr = isCommodities
    ? "دولار"
    : isUae
      ? "د.إ"
      : isQatar
        ? "ر.ق"
        : isSaudi
          ? "ر.س"
          : "ج.م";
  const marketAr = isCommodities
    ? "الأسواق العالمية (الذهب والفضة)"
    : actualExchange === "DFM"
      ? "سوق دبي المالي (DFM)"
      : actualExchange === "ADX"
        ? "سوق أبوظبي للأوراق المالية (ADX)"
        : isQatar
          ? "بورصة قطر (QSE)"
          : isSaudi
            ? "السوق السعودي (تداول / تاسي)"
            : "البورصة المصرية";
  const pricePart =
    Number.isFinite(lastClose) && lastClose > 0
      ? `آخر سعر إغلاق ${lastClose.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${currencyAr}${lastDate ? ` (${lastDate})` : ""}. `
      : "";
  const description = isCommodities
    ? `${pricePart}تابع سعر ${nameAr} (${symbol}) اليوم: التحليل الفني اللحظي، مؤشر القوة النسبية RSI، ومستويات الدعم والمقاومة بالذكاء الاصطناعي.`
    : `${pricePart}تعرف على سعر سهم ${nameAr} (${symbol}${nameEn !== symbol ? ` - ${nameEn}` : ""}) اليوم في ${marketAr}: مستويات الدعم والمقاومة، السعر العادل، ومؤشر الذكاء الاصطناعي AI Score.`;

  return {
    title,
    description,
    keywords: [
      symbol,
      nameAr,
      nameEn,
      isCommodities ? `سعر ${nameAr} اليوم` : `سعر سهم ${nameAr}`,
      isCommodities ? `تحليل ${nameAr}` : `سهم ${nameAr}`,
      `تحليل ${isCommodities ? nameAr : `سهم ${nameAr}`}`,
      `توقعات ${isCommodities ? nameAr : `سهم ${nameAr}`}`,
      `سعر ${symbol}`,
      `${symbol} price`,
      marketAr,
      "EGX BOTS",
      "egxbots",
      actualExchange,
    ],
    alternates: {
      canonical: `https://egxbots.com/stocks/${canonicalSlug}`,
    },
    openGraph: {
      title,
      description,
      type: "website",
      url: `https://egxbots.com/stocks/${canonicalSlug}`,
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
  const { cleanSymbol: symbol, marketMode, explicitExchange } = resolveSymbolAndMarket(rawSymbol);
  const canonicalSlug = explicitExchange
    ? `${symbol.toLowerCase()}.${explicitExchange.toLowerCase()}`
    : symbol.toLowerCase();
  const isSaudi = marketMode === "tasi";

  // Enforce lowercase canonical URL: redirect uppercase or suffixed visits
  if (rawSymbol !== rawSymbol.toLowerCase() || (isSaudi && rawSymbol.toLowerCase() !== symbol.toLowerCase())) {
    redirect(`/stocks/${canonicalSlug}`);
  }

  const bundle = typeof getPublicStockPageBundle === "function"
    ? await getPublicStockPageBundle(symbol, marketMode, explicitExchange)
    : { snapshot: await getPublicStockSnapshot(symbol, marketMode, explicitExchange), related: null };
  const snapshot = bundle.snapshot;
  const { fundamentals: fundRow, latestPrice, latestTech, historicalPrices, latestScan } = snapshot;
  if (!fundRow && !latestPrice) notFound();
  const snapshotExchange = String(
    (fundRow as any)?.data?.exchange || (fundRow as any)?.exchange || (latestPrice as any)?.exchange || ""
  ).toUpperCase();
  const isGccPage = !isSaudi && ["DFM", "ADX", "QSE", "COMMODITIES"].includes(snapshotExchange);
  const gccCurrencyNameAr = snapshotExchange === "QSE" ? "ريال قطري" : snapshotExchange === "COMMODITIES" ? "دولار" : "درهم إماراتي";
  const gccMarketLabelAr =
    snapshotExchange === "DFM"
      ? "سوق دبي المالي (DFM)"
      : snapshotExchange === "ADX"
        ? "سوق أبوظبي للأوراق المالية (ADX)"
        : snapshotExchange === "QSE"
          ? "بورصة قطر (QSE)"
          : "الأسواق العالمية (الذهب والفضة)";
  const gccDirectoryHref =
    snapshotExchange === "QSE" ? "/markets/qatar" : snapshotExchange === "COMMODITIES" ? "/markets/gold-silver" : "/markets/uae";
  const gccDirectoryNameAr =
    snapshotExchange === "QSE" ? "دليل أسهم بورصة قطر" : snapshotExchange === "COMMODITIES" ? "الذهب والفضة" : "دليل أسهم الإمارات";
  const exchange = isGccPage ? snapshotExchange : isSaudi ? "TADAWUL" : "EGX";
  const currencyCode = isGccPage
    ? String((fundRow as any)?.data?.currency || (snapshotExchange === "QSE" ? "QAR" : snapshotExchange === "COMMODITIES" ? "USD" : "AED"))
    : isSaudi ? "SAR" : "EGP";
  const currencyNameAr = isGccPage ? gccCurrencyNameAr : isSaudi ? "ريال سعودي" : "جنيه مصري";
  const marketLabelAr = isGccPage ? gccMarketLabelAr : isSaudi ? "السوق السعودي (تاسي)" : "البورصة المصرية";

  const fund = fundRow?.data || {};
  const canonical = isSaudi || isGccPage ? { name_ar: symbol, name_en: symbol, sector: "" } : getCanonicalStockName(symbol);
  const nameAr = isSaudi || isGccPage
    ? (fund.name_ar || SAUDI_STOCK_NAMES_AR[symbol] || fund.name || fund.Name || symbol)
    : (canonical.name_ar || fund.name || fund.Name || symbol);
  const nameEn = isSaudi || isGccPage
    ? String(fund.name || fund.Name || SAUDI_STOCK_NAMES_AR[symbol] || symbol)
    : (canonical.name_en && canonical.name_en !== symbol
      ? canonical.name_en
      : String(fund.name || fund.Name || symbol));

  const related = bundle.related ?? selectStockLinks(
    isGccPage
      ? await getPublicGccMetalsDirectoryWeekly().catch(() => [])
      : isSaudi && typeof getPublicTasiStockDirectoryWeekly === "function"
      ? await getPublicTasiStockDirectoryWeekly().catch(() => [])
      : typeof getPublicStockDirectoryWeekly === "function"
      ? await getPublicStockDirectoryWeekly()
      : await getPublicStockDirectory(),
    symbol,
    String(fund.sector || fund.Sector || canonical.sector || "")
  );
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
          {
            "@type": "ListItem",
            "position": 2,
            "name": isGccPage ? gccDirectoryNameAr : isSaudi ? "دليل الأسهم السعودية" : "دليل الأسهم المصرية",
            "item": isGccPage ? `https://egxbots.com${gccDirectoryHref}` : isSaudi ? "https://egxbots.com/stocks?market=tasi" : "https://egxbots.com/stocks"
          },
          { "@type": "ListItem", "position": 3, "name": `سهم ${nameAr} (${symbol})`, "item": `https://egxbots.com/stocks/${canonicalSlug}` }
        ]
      },
      {
        "@type": "WebPage",
        "name": `سعر وتحليل سهم ${nameAr} (${symbol}) في ${marketLabelAr}`,
        "alternateName": `${nameEn} (${symbol}) Stock Analysis`,
        "url": `https://egxbots.com/stocks/${canonicalSlug}`,
        ...(priceDate ? { dateModified: priceDate } : {}),
        "description": `بيانات فنية وسعر إغلاق سهم ${nameAr} (${symbol} - ${nameEn}) في ${marketLabelAr} مع تقييمات الذكاء الاصطناعي ومستويات الدعم والمقاومة.`,
        "publisher": { "@type": "Organization", "name": "EGX BOTS", "url": "https://egxbots.com" }
      },
      ...(Number.isFinite(lastPriceVal) && lastPriceVal > 0 ? [{
        "@type": "FinancialProduct",
        "name": `سهم ${nameAr} (${symbol})`,
        "alternateName": `${nameEn} (${symbol})`,
        "tickerSymbol": symbol,
        "exchange": exchange,
        "currency": currencyCode,
        "description": `سهم ${nameAr} (${nameEn}) المتداول في ${marketLabelAr} تحت رمز ${symbol}.`,
        "offers": {
          "@type": "Offer",
          "price": lastPriceVal,
          "priceCurrency": currencyCode,
          ...(priceDate ? { "priceValidUntil": priceDate } : {})
        }
      }] : []),
      {
        "@type": "FAQPage",
        "mainEntity": [
          {
            "@type": "Question",
            "name": `ما هو سعر سهم ${nameAr} (${symbol}) اليوم في ${marketLabelAr}؟`,
            "acceptedAnswer": {
              "@type": "Answer",
              "text": Number.isFinite(lastPriceVal) && lastPriceVal > 0
                ? `بلغ آخر سعر إغلاق مسجل لسهم ${nameAr} (${symbol}) ما قيمته ${lastPriceVal} ${currencyNameAr} ${priceDate ? `بتاريخ ${priceDate}` : ''}.`
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
        key={canonicalSlug}
        symbol={symbol}
        exchange={exchange}
        market={isGccPage ? (snapshotExchange === "QSE" ? "qatar" : "uae") : isSaudi ? "tasi" : "egx"}
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
