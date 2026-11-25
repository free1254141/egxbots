"use client";

import { useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { Search, Filter, ArrowUpRight, Sparkles } from "lucide-react";
import StockLogo from "@/components/StockLogo";
import BrandedPageHeader from "@/components/BrandedPageHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { useMarket } from "@/contexts/MarketContext";
import { getCanonicalStockName } from "@/lib/ai/stock-names";
import { POPULAR_TASI_STOCKS, SAUDI_STOCK_NAMES_AR } from "@/lib/saudi-stocks";
import { hfPublicFetch } from "@/lib/hf-browser-client";

interface StockItem {
  symbol: string;
  name: string;
  nameAr?: string;
  sector: string;
  marketCap?: number | null;
}

const FALLBACK_TASI_STOCKS: StockItem[] = (() => {
  const bySymbol = new Map<string, StockItem>();
  for (const s of POPULAR_TASI_STOCKS) {
    bySymbol.set(s.symbol, {
      symbol: s.symbol,
      name: s.name,
      nameAr: s.name_ar,
      sector: "السوق السعودي (تاسي)",
      marketCap: null,
    });
  }
  for (const [symbol, nameAr] of Object.entries(SAUDI_STOCK_NAMES_AR)) {
    if (!bySymbol.has(symbol)) {
      bySymbol.set(symbol, {
        symbol,
        name: nameAr,
        nameAr,
        sector: "السوق السعودي (تاسي)",
        marketCap: null,
      });
    }
  }
  return Array.from(bySymbol.values()).sort((a, b) => a.symbol.localeCompare(b.symbol));
})();

export default function StocksClient({
  initialStocks,
  initialTasiStocks = [],
}: {
  initialStocks: StockItem[];
  initialTasiStocks?: StockItem[];
}) {
  const { language } = useLanguage();
  const { market, isSaudi } = useMarket();
  const isAr = language === "ar";

  const [query, setQuery] = useState("");
  const [selectedSector, setSelectedSector] = useState("all");
  const [showAll, setShowAll] = useState(false);
  const [tasiStocks, setTasiStocks] = useState<StockItem[] | null>(
    initialTasiStocks.length > 0 ? initialTasiStocks : null
  );
  const [isLoadingTasi, setIsLoadingTasi] = useState(false);

  useEffect(() => {
    setSelectedSector("all");
    if (!isSaudi || tasiStocks !== null) return;

    const TASI_DIR_CACHE_KEY = "egxbots_tasi_stocks_dir_v1";
    const TASI_DIR_TTL_MS = 6 * 60 * 60 * 1000;
    if (typeof window !== "undefined") {
      try {
        const raw = window.sessionStorage.getItem(TASI_DIR_CACHE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw) as { ts: number; data: StockItem[] };
          if (parsed?.ts && Date.now() - parsed.ts < TASI_DIR_TTL_MS && Array.isArray(parsed.data) && parsed.data.length > 0) {
            setTasiStocks(parsed.data);
            setIsLoadingTasi(false);
            return;
          }
        }
      } catch {
        // ignore storage errors
      }
    }

    const controller = new AbortController();
    setIsLoadingTasi(true);

    hfPublicFetch("/api/symbols/search?q=&limit=500&market=tasi", { signal: controller.signal }, { cacheTtlMs: 300_000 })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error("HTTP " + res.status))))
      .then((payload) => {
        const results = Array.isArray(payload?.results) ? payload.results : [];
        const bySymbol = new Map<string, StockItem>();
        for (const item of results) {
          const cleanSym = String(item?.symbol || item?.Symbol || "")
            .trim()
            .toUpperCase()
            .replace(/\.(SR|SA|TADAWUL)$/i, "");
          if (!cleanSym) continue;
          const nameAr = String(item?.name_ar || item?.NameAr || SAUDI_STOCK_NAMES_AR[cleanSym] || "").trim();
          const nameEn = String(item?.name || item?.Name || nameAr || cleanSym).trim();
          const sector = String(item?.sector || item?.Sector || "").trim();
          bySymbol.set(cleanSym, {
            symbol: cleanSym,
            name: nameEn || cleanSym,
            nameAr: nameAr || undefined,
            sector,
            marketCap: null,
          });
        }
        const parsed = Array.from(bySymbol.values()).sort((a, b) => a.symbol.localeCompare(b.symbol));
        const finalStocks = parsed.length > 0 ? parsed : FALLBACK_TASI_STOCKS;
        if (parsed.length > 0 && typeof window !== "undefined") {
          try {
            window.sessionStorage.setItem(TASI_DIR_CACHE_KEY, JSON.stringify({ ts: Date.now(), data: parsed }));
          } catch {
            // ignore storage quota errors
          }
        }
        setTasiStocks(finalStocks);
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          console.warn("Failed to load TASI directory, using fallback list:", err);
          setTasiStocks(FALLBACK_TASI_STOCKS);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoadingTasi(false);
      });

    return () => controller.abort();
  }, [market, isSaudi, tasiStocks]);

  const enrichedStocks = useMemo(() => {
    const sourceStocks = isSaudi ? (tasiStocks ?? FALLBACK_TASI_STOCKS) : initialStocks;
    return sourceStocks.map((s) => {
      if (isSaudi) {
        const cleanSym = s.symbol.toUpperCase().replace(/\.(SR|SA|TADAWUL)$/i, "");
        const nameAr = s.nameAr || SAUDI_STOCK_NAMES_AR[cleanSym] || s.name || cleanSym;
        const nameEn = s.name && s.name !== cleanSym ? s.name : (nameAr || cleanSym);
        const defaultSector = isAr ? "السوق السعودي (تاسي)" : "Saudi Exchange (TASI)";
        return {
          ...s,
          symbol: cleanSym,
          nameAr,
          nameEn,
          sectorDisplay: s.sector || defaultSector,
        };
      }

      const canonical = getCanonicalStockName(s.symbol);
      const nameAr = canonical.name_ar && canonical.name_ar !== s.symbol ? canonical.name_ar : (s.name || s.symbol);
      const nameEn = canonical.name_en && canonical.name_en !== s.symbol ? canonical.name_en : (s.name || s.symbol);
      const sectorAr = canonical.sector || s.sector || "سوق الأسهم المصرية";
      return {
        ...s,
        nameAr,
        nameEn,
        sectorDisplay: isAr ? sectorAr : (s.sector || sectorAr),
      };
    });
  }, [initialStocks, tasiStocks, isSaudi, isAr]);

  const sectors = useMemo(() => {
    const set = new Set<string>();
    enrichedStocks.forEach((s) => {
      if (s.sectorDisplay && s.sectorDisplay.trim()) {
        set.add(s.sectorDisplay.trim());
      }
    });
    return Array.from(set).sort();
  }, [enrichedStocks]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return enrichedStocks.filter((s) => {
      const matchQuery =
        !q ||
        s.symbol.toLowerCase().includes(q) ||
        s.nameAr.toLowerCase().includes(q) ||
        s.nameEn.toLowerCase().includes(q) ||
        (s.name && s.name.toLowerCase().includes(q));
      const matchSector =
        selectedSector === "all" || s.sectorDisplay === selectedSector;
      return matchQuery && matchSector;
    });
  }, [enrichedStocks, query, selectedSector]);

  return (
    <div dir={isAr ? "rtl" : "ltr"} className="w-full">
      <div className="mb-8">
        <BrandedPageHeader
          dir={isAr ? "rtl" : "ltr"}
          badgeIcon={<Sparkles className="w-5 h-5 text-amber-500" />}
          eyebrow={
            isSaudi
              ? (isAr ? "دليل السوق السعودي والشركات | TASI DIRECTORY" : "TASI MARKET & COMPANIES DIRECTORY")
              : (isAr ? "دليل السوق والشركات | EGX DIRECTORY" : "EGX MARKET & COMPANIES DIRECTORY")
          }
          title={
            isSaudi
              ? (isAr ? "دليل أسهم السوق السعودي (تاسي) بالذكاء الاصطناعي" : "Saudi Exchange (TASI) AI Stocks Directory")
              : (isAr ? "دليل أسهم البورصة المصرية بالذكاء الاصطناعي" : "Egyptian Exchange (EGX) AI Stocks Directory")
          }
          description={
            isSaudi
              ? (isAr
                  ? "تصفح جميع الشركات والأسهم المدرجة في السوق السعودي (تداول / تاسي) بالاسم العربي والرمز (4 أرقام)، واستعرض التقييمات الفنية ومستويات الدعم والمقاومة لكل سهم بالريال السعودي (ر.س)."
                  : "Browse all listed companies on the Saudi Exchange (Tadawul / TASI) by Arabic/English name or 4-digit ticker, and explore technical indicators, AI scores, and key price levels in SAR.")
              : (isAr
                  ? "تصفح جميع الشركات والأسهم المقيدة في البورصة المصرية بالاسم العربي والرمز، واستعرض التقييمات الفنية ونماذج التعلم الآلي ومستويات السيولة لكل سهم."
                  : "Browse all listed companies on the Egyptian Exchange (EGX) by Arabic/English name or ticker, and explore technical indicators, machine learning scores, and liquidity metrics.")
          }
        />

        {/* Quick Regional & Gulf Markets Navigation */}
        <div className="mt-4 flex flex-wrap gap-2">
          {[
            { href: "/markets", ar: "🌍 كل الأسواق", en: "🌍 All Markets" },
            { href: "/stocks", ar: "🇪🇬 مصر (EGX)", en: "🇪🇬 Egypt (EGX)" },
            { href: "/stocks?market=tasi", ar: "🇸🇦 السعودية (TASI)", en: "🇸🇦 Saudi (TASI)" },
            { href: "/markets/uae", ar: "🇦🇪 الإمارات (DFM & ADX)", en: "🇦🇪 UAE (DFM & ADX)" },
            { href: "/markets/qatar", ar: "🇶🇦 قطر (QSE)", en: "🇶🇦 Qatar (QSE)" },
            { href: "/markets/gold-silver", ar: "🥇 الذهب والفضة", en: "🥇 Gold & Silver" },
          ].map((tab) => (
            <Link
              key={tab.href}
              href={tab.href}
              className="px-3 py-1.5 text-xs font-black bg-white dark:bg-zinc-900 text-black dark:text-white border-2 border-black dark:border-white shadow-[2px_2px_0px_#000] dark:shadow-[2px_2px_0px_rgba(255,255,255,0.25)] hover:bg-[#FFE600] hover:text-black transition-colors"
              prefetch={false}
            >
              {isAr ? tab.ar : tab.en}
            </Link>
          ))}
        </div>
      </div>

      {/* Search & Sector Filters Bar */}
      <div className="mb-8 p-4 bg-white dark:bg-zinc-900 border-4 border-black dark:border-white shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.4)] flex flex-col md:flex-row gap-4 items-stretch md:items-center justify-between">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              isSaudi
                ? (isAr
                    ? "ابحث بالاسم العربي أو الإنجليزي أو الرمز (مثال: أرامكو، الراجحي، 2222، 1120)..."
                    : "Search by company name or symbol (e.g., 2222, 1120, Aramco, Al Rajhi)...")
                : (isAr
                    ? "ابحث بالاسم العربي أو الإنجليزي أو الرمز (مثال: العربية للألومنيوم، طلعت مصطفى، COMI، ALUM)..."
                    : "Search by company name or symbol (e.g., COMI, ALUM, Talaat Moustafa)...")
            }
            className="w-full h-11 pl-10 pr-4 text-xs font-black border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-950 text-black dark:text-white outline-none focus:bg-[#FFE600] focus:text-black transition-none"
          />
        </div>

        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-zinc-500 shrink-0" />
          <select
            value={selectedSector}
            onChange={(e) => setSelectedSector(e.target.value)}
            className="h-11 px-3 text-xs font-black border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-950 text-black dark:text-white outline-none cursor-pointer focus:bg-[#FFE600] focus:text-black"
          >
            <option value="all">{isAr ? "جميع القطاعات" : "All Sectors"}</option>
            {sectors.map((sec) => (
              <option key={sec} value={sec}>
                {sec}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Stocks Count Indicator */}
      <div className="mb-4 flex justify-between items-center text-xs font-black text-zinc-600 dark:text-zinc-400 uppercase tracking-widest">
        <span>
          {isSaudi && isLoadingTasi
            ? (isAr ? "جاري تحميل دليل السوق السعودي..." : "Loading TASI directory...")
            : isAr
            ? `عرض ${filtered.length} سهم من أصل ${enrichedStocks.length}`
            : `Showing ${filtered.length} of ${enrichedStocks.length} stocks`}
        </span>
        {selectedSector !== "all" && (
          <button
            onClick={() => setSelectedSector("all")}
            className="text-red-500 hover:underline cursor-pointer"
          >
            {isAr ? "إلغاء الفلتر" : "Clear filter"}
          </button>
        )}
      </div>

      {/* Grid of Stocks */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {(showAll || query.trim() || selectedSector !== "all" ? filtered : filtered.slice(0, 48)).map((stock) => (
          <Link
            prefetch={false}
            key={stock.symbol}
            href={`/stocks/${stock.symbol.toLowerCase()}`}
            className="group block p-4 bg-white dark:bg-zinc-900 border-3 border-black dark:border-white shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.3)] hover:-translate-y-1 hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.5)] transition-all"
          >
            <div className="flex items-center justify-between gap-3 mb-3">
              <div className="flex items-center gap-2.5">
                <StockLogo
                  symbol={stock.symbol}
                  size="sm"
                  className="border-2 border-black dark:border-white rounded-none"
                />
                <div>
                  <span className="font-mono font-black text-base text-black dark:text-white group-hover:text-yellow-600 dark:group-hover:text-yellow-400">
                    {stock.symbol}
                  </span>
                  <span className="block text-[10px] text-zinc-500 font-bold uppercase">
                    {isSaudi ? "TASI" : "EGX"}
                  </span>
                </div>
              </div>
              <ArrowUpRight className="w-4 h-4 text-zinc-400 group-hover:text-black dark:group-hover:text-white transition-colors" />
            </div>

            <p className="text-xs font-black text-zinc-900 dark:text-zinc-100 line-clamp-1 mb-1">
              {isAr ? stock.nameAr : stock.nameEn}
            </p>
            <p className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400 line-clamp-1 mb-2">
              {isAr ? stock.nameEn : stock.nameAr}
            </p>

            <div className="flex items-center justify-between pt-2 border-t border-zinc-200 dark:border-zinc-800 text-[10px] font-bold text-zinc-500">
              <span className="truncate max-w-[150px]">{stock.sectorDisplay}</span>
              <span className="text-emerald-600 dark:text-emerald-400 font-black">
                {isAr ? "تحليل فني و AI" : "AI & Technical"}
              </span>
            </div>
          </Link>
        ))}
      </div>

      {!showAll && !query.trim() && selectedSector === "all" && filtered.length > 48 && (
        <div className="mt-6 flex justify-center">
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="px-5 py-2.5 text-xs font-black border-2 border-black dark:border-white bg-[#FFE600] text-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.4)] hover:-translate-y-0.5 transition-transform cursor-pointer"
          >
            {isAr ? `عرض كل الأسهم (+${filtered.length - 48})` : `Show all stocks (+${filtered.length - 48})`}
          </button>
        </div>
      )}

      {filtered.length === 0 && (
        <div className="py-16 text-center border-4 border-dashed border-zinc-300 dark:border-zinc-800">
          <p className="text-sm font-black text-zinc-500">
            {isAr
              ? "لا يوجد أسهم مطابقة لخيارات البحث"
              : "No stocks found matching the criteria"}
          </p>
        </div>
      )}

      {/* Companion Market SSR Directory for Dual-Market Discovery & SEO */}
      <section
        aria-label={
          isSaudi
            ? (isAr ? "تصفح أسهم البورصة المصرية EGX" : "Browse Egyptian Exchange EGX Stocks")
            : (isAr ? "تصفح أسهم السوق السعودي تاسي TASI" : "Browse Saudi Tadawul TASI Stocks")
        }
        className="mt-12 border-2 border-black/15 dark:border-white/15 bg-white/75 dark:bg-zinc-900/60 p-5 sm:p-6"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
          <h2 className="text-sm font-black text-zinc-900 dark:text-white">
            {isSaudi
              ? (isAr ? "🇪🇬 دليل أسهم البورصة المصرية (EGX)" : "🇪🇬 Egyptian Exchange (EGX) Directory")
              : (isAr ? "🇸🇦 دليل أسهم السوق السعودي (تداول / تاسي TASI)" : "🇸🇦 Saudi Tadawul (TASI) Stocks Directory")}
          </h2>
          <Link
            href={isSaudi ? "/stocks?market=egx" : "/stocks?market=tasi"}
            className="text-xs font-black text-emerald-700 dark:text-emerald-400 hover:underline"
            prefetch={false}
          >
            {isSaudi
              ? (isAr ? "عرض الدليل المصري الكامل ←" : "Switch to full EGX directory ←")
              : (isAr ? "عرض دليل السوق السعودي الكامل ←" : "Switch to full TASI directory ←")}
          </Link>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(isSaudi ? initialStocks : (tasiStocks ?? FALLBACK_TASI_STOCKS)).map((s) => {
            const cleanSym = s.symbol.toUpperCase().replace(/\.(SR|SA|TADAWUL)$/i, "");
            const canonical = !isSaudi ? null : getCanonicalStockName(cleanSym);
            const labelAr = isSaudi
              ? (canonical && canonical.name_ar !== cleanSym ? canonical.name_ar : (s.nameAr || s.name || cleanSym))
              : (s.nameAr || SAUDI_STOCK_NAMES_AR[cleanSym] || s.name || cleanSym);
            const labelEn = s.name || cleanSym;
            return (
              <Link
                key={cleanSym}
                href={`/stocks/${cleanSym.toLowerCase()}`}
                prefetch={false}
                className="px-2 py-1 text-[11px] font-bold bg-zinc-100 dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 border border-zinc-300 dark:border-zinc-800 hover:border-amber-500 transition-colors"
              >
                {isAr ? `${labelAr} (${cleanSym})` : `${labelEn} (${cleanSym})`}
              </Link>
            );
          })}
        </div>
      </section>
    </div>
  );
}
