import Link from "next/link";
import type { GccMarketStockRow } from "@/lib/seo/stock-directory";
import { getStockHref } from "@/lib/stock-href";

interface FaqItem {
  q: string;
  a: string;
}

interface MarketDirectoryPageProps {
  canonicalUrl: string;
  badge: string;
  title: string;
  subtitle: string;
  currencyLabel: string;
  items: GccMarketStockRow[];
  faqs: FaqItem[];
  otherMarketLinks: Array<{ href: string; label: string }>;
}

export default function MarketDirectoryPage({
  canonicalUrl,
  badge,
  title,
  subtitle,
  currencyLabel,
  items,
  faqs,
  otherMarketLinks,
}: MarketDirectoryPageProps) {
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "CollectionPage",
        "@id": `${canonicalUrl}#webpage`,
        name: title,
        description: subtitle,
        url: canonicalUrl,
        mainEntity: {
          "@type": "ItemList",
          numberOfItems: items.length,
          itemListElement: items.slice(0, 60).map((it, idx) => ({
            "@type": "ListItem",
            position: idx + 1,
            name: `${it.nameAr || it.name} (${it.symbol})`,
            url: `https://egxbots.com${getStockHref(it.symbol, { exchange: it.exchange })}`,
          })),
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "الرئيسية", item: "https://egxbots.com" },
          { "@type": "ListItem", position: 2, name: "الأسواق", item: "https://egxbots.com/markets" },
          { "@type": "ListItem", position: 3, name: title, item: canonicalUrl },
        ],
      },
      ...(faqs.length > 0
        ? [
            {
              "@type": "FAQPage",
              mainEntity: faqs.map((f) => ({
                "@type": "Question",
                name: f.q,
                acceptedAnswer: { "@type": "Answer", text: f.a },
              })),
            },
          ]
        : []),
    ],
  };

  return (
    <main dir="rtl" className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }}
      />

      {/* Hero Header */}
      <header className="mb-8 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)]">
        <div className="inline-block px-3 py-1 mb-3 text-xs font-black uppercase bg-[#FFE600] text-black border-2 border-black shadow-[2px_2px_0px_#000]">
          {badge}
        </div>
        <h1 className="text-2xl sm:text-3xl font-black text-black dark:text-white mb-2">{title}</h1>
        <p className="text-sm sm:text-base font-bold text-zinc-700 dark:text-zinc-300 leading-relaxed mb-4">
          {subtitle}
        </p>

        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/chat"
            className="px-4 py-2 text-xs sm:text-sm font-black bg-[#00FF66] text-black border-2 border-black shadow-[3px_3px_0px_#000] hover:bg-[#FFE600] transition-colors"
            prefetch={false}
          >
            اسأل الشات بوت AI عن أي سهم الآن
          </Link>
          {otherMarketLinks.map((lnk) => (
            <Link
              key={lnk.href}
              href={lnk.href}
              className="px-3 py-2 text-xs font-black bg-zinc-100 dark:bg-zinc-900 text-black dark:text-white border-2 border-black dark:border-white hover:bg-[#FFE600] hover:text-black transition-colors"
              prefetch={false}
            >
              {lnk.label}
            </Link>
          ))}
        </div>
      </header>

      {/* Stocks / Assets Grid */}
      <section aria-label={title} className="mb-10">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-black text-black dark:text-white">
            القائمة الكاملة ({items.length})
          </h2>
          <span className="text-xs font-bold text-zinc-500 dark:text-zinc-400">
            العملة: {currencyLabel}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((item) => {
            const chg = item.changePct;
            const chgColor =
              chg != null && chg > 0
                ? "text-emerald-700 dark:text-[#00FF66]"
                : chg != null && chg < 0
                ? "text-rose-700 dark:text-rose-400"
                : "text-zinc-600 dark:text-zinc-400";

            return (
              <Link
                key={`${item.exchange}-${item.symbol}`}
                href={getStockHref(item.symbol, { exchange: item.exchange })}
                className="block p-4 border-2 border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.25)] hover:bg-[#FFE600]/15 transition-colors"
                prefetch={false}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-black text-black dark:text-white">
                        {item.symbol}
                      </span>
                      <span className="px-1.5 py-0.5 text-[10px] font-black bg-zinc-200 dark:bg-zinc-800 text-black dark:text-white border border-black/30">
                        {item.exchange}
                      </span>
                    </div>
                    <h3 className="text-sm font-black text-zinc-900 dark:text-zinc-100 truncate mt-1">
                      {item.nameAr || item.name}
                    </h3>
                  </div>

                  <div className="text-left shrink-0">
                    <div className="font-mono text-sm font-black text-black dark:text-white">
                      {item.close != null
                        ? `${item.close.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${currencyLabel}`
                        : "—"}
                    </div>
                    {chg != null && (
                      <div className={`font-mono text-xs font-black ${chgColor}`}>
                        {chg > 0 ? `+${chg.toFixed(2)}%` : `${chg.toFixed(2)}%`}
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between text-[11px] font-bold text-zinc-600 dark:text-zinc-400 pt-2 border-t border-black/10 dark:border-white/10">
                  <span>{item.sector || item.name}</span>
                  <span>
                    {item.rsi14 != null ? `RSI: ${item.rsi14.toFixed(1)}` : ""}
                    {item.priceDate ? ` • ${item.priceDate}` : ""}
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      {/* FAQ Section */}
      {faqs.length > 0 && (
        <section className="border-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-950 p-6 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)]">
          <h2 className="text-lg font-black text-black dark:text-white mb-4">أسئلة شائعة</h2>
          <div className="space-y-4">
            {faqs.map((faq, idx) => (
              <div key={idx} className="border-b border-black/10 dark:border-white/10 pb-3 last:border-b-0 last:pb-0">
                <h3 className="text-sm font-black text-black dark:text-white mb-1">{faq.q}</h3>
                <p className="text-xs sm:text-sm font-bold text-zinc-700 dark:text-zinc-300 leading-relaxed">
                  {faq.a}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
