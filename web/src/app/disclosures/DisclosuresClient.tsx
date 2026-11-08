"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  FileText,
  Download,
  LayoutList,
  LayoutGrid,
  Search,
  Bot,
  ExternalLink,
  TrendingUp,
  TrendingDown,
  Calendar,
  Users,
  Filter,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Eye,
  ZoomIn,
  X,
  Hash,
  ChevronDown,
  Sparkles,
} from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import { useChat } from "@/contexts/ChatContext";
import BrandedPageHeader from "@/components/BrandedPageHeader";
import StockLogo from "@/components/StockLogo";

export interface DisclosureItem {
  id: string;
  symbol: string | null;
  company_name: string;
  disclosure_type: string;
  disclosure_date: string;
  title: string;
  raw_content: string | null;
  ai_summary: string;
  sentiment: "bullish" | "bearish" | "neutral" | string;
  action_type: string | null;
  shares_count: number | null;
  stake_before?: number | null;
  stake_after?: number | null;
  party_name: string | null;
  party_role: string | null;
  source_url: string | null;
  metadata?: {
    key_takeaway?: string;
    free_float_before?: number;
    free_float_after?: number;
    session?: string;
  };
}

export interface DisclosuresInitialStats {
  total: number;
  buys: number;
  sells: number;
  shareholding: number;
}

interface DisclosuresClientProps {
  initialDisclosures: DisclosureItem[];
  initialStats: DisclosuresInitialStats;
}

const PAGE_BATCH_SIZE = 12;

export default function DisclosuresClient({
  initialDisclosures,
  initialStats,
}: DisclosuresClientProps) {
  const { language } = useLanguage();
  const isAr = language === "ar";
  const { setIsOpen, sendMessage } = useChat();

  const [disclosures, setDisclosures] = useState<DisclosureItem[]>(initialDisclosures);
  const [totalCount, setTotalCount] = useState<number>(initialStats.total || initialDisclosures.length);
  const [hasMore, setHasMore] = useState<boolean>(
    (initialStats.total || initialDisclosures.length) > initialDisclosures.length
  );
  const [loading, setLoading] = useState<boolean>(false);
  const [loadingMore, setLoadingMore] = useState<boolean>(false);

  const [search, setSearch] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [selectedType, setSelectedType] = useState<string>("all");
  const [selectedSentiment, setSelectedSentiment] = useState<string>("all");
  const [layoutMode, setLayoutMode] = useState<"list" | "grid">("list");

  // Modal state for full-screen disclosure image / PDF inspection
  const [previewItem, setPreviewItem] = useState<DisclosureItem | null>(null);
  const [previewMode, setPreviewMode] = useState<"image" | "pdf">("image");

  const loadMoreTriggerRef = useRef<HTMLDivElement | null>(null);
  const isInitialMountRef = useRef<boolean>(true);

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const fetchBatch = useCallback(
    async (offsetVal: number, append: boolean, signal?: AbortSignal) => {
      if (append) setLoadingMore(true);
      else setLoading(true);

      try {
        const params = new URLSearchParams({
          limit: String(PAGE_BATCH_SIZE),
          offset: String(offsetVal),
          type: selectedType,
          sentiment: selectedSentiment,
        });
        if (debouncedSearch.trim()) {
          params.set("search", debouncedSearch.trim());
        }

        const res = await fetch(`/api/disclosures?${params.toString()}`, { signal });
        if (!res.ok) throw new Error("Failed to load disclosures");
        const json = await res.json();
        if (signal?.aborted) return;

        const incoming: DisclosureItem[] = json.data || [];
        setDisclosures((prev) => (append ? [...prev, ...incoming] : incoming));
        setTotalCount(json.total ?? incoming.length);
        setHasMore(Boolean(json.hasMore));
      } catch (err) {
        if (signal?.aborted) return;
        console.error("Error loading disclosures batch:", err);
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [debouncedSearch, selectedType, selectedSentiment]
  );

  // Trigger fresh fetch when filters or search change (skip initial SSR render if default filters)
  useEffect(() => {
    if (isInitialMountRef.current) {
      isInitialMountRef.current = false;
      if (!debouncedSearch && selectedType === "all" && selectedSentiment === "all") {
        return;
      }
    }
    const controller = new AbortController();
    void fetchBatch(0, false, controller.signal);
    return () => controller.abort();
  }, [debouncedSearch, selectedType, selectedSentiment, fetchBatch]);

  // Progressive infinite scroll observer ("يحمل شوية بشوية")
  useEffect(() => {
    const node = loadMoreTriggerRef.current;
    if (!node || !hasMore || loading || loadingMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !loading && !loadingMore) {
          void fetchBatch(disclosures.length, true);
        }
      },
      { rootMargin: "280px" }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loading, loadingMore, disclosures.length, fetchBatch]);

  // Open floating ChatWidget directly on the current page without navigating away!
  const handleDiscussInFloatingChat = (item: DisclosureItem) => {
    const symPart = item.symbol ? ` (${item.symbol})` : "";
    const prompt = isAr
      ? `ما هو تحليلك المالي والفني لإفصاح شركة ${item.company_name}${symPart} الصادر بتاريخ ${item.disclosure_date} بعنوان: "${item.title}"؟ وما تأثيره المتوقع على السهم ومستويات التداول؟ واعرض لي مستند الـ PDF المعتمد للإفصاح.`
      : `What is your financial and technical analysis of the disclosure from ${item.company_name}${symPart} dated ${item.disclosure_date} titled: "${item.title}"? What is the expected impact on the stock? Please provide the official filing PDF document.`;

    setIsOpen(true);
    void sendMessage(prompt);
  };

  const handleOpenGeneralFloatingChat = () => {
    const prompt = isAr
      ? "ما هي أهم إفصاحات الشركات وتعاملات الداخليين الإيجابية والسلبية المسجلة مؤخراً في البورصة المصرية؟"
      : "What are the most important recent company disclosures and bullish/bearish insider transactions on the EGX?";
    setIsOpen(true);
    void sendMessage(prompt);
  };

  const getTypeLabel = (type: string) => {
    switch (type) {
      case "insider_trading":
        return isAr ? "تعاملات داخليين" : "Insider Trading";
      case "major_shareholders":
        return isAr ? "هيكل المساهمين (مادة 30)" : "Shareholding (Art. 30)";
      case "board_resolution":
        return isAr ? "قرارات مجلس الإدارة" : "Board Resolutions";
      case "financial_results":
        return isAr ? "نتائج وقوائم مالية" : "Financial Results";
      default:
        return isAr ? "إفصاح جوهري" : "Material Disclosure";
    }
  };

  const getSentimentBadge = (item: DisclosureItem) => {
    const isBullish = item.sentiment === "bullish" || item.action_type === "buy";
    const isBearish = item.sentiment === "bearish" || item.action_type === "sell";

    if (isBullish) {
      return (
        <span className="flex items-center gap-1 px-3 py-1 text-xs font-black bg-[#00FF66] text-black border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
          <TrendingUp className="w-3.5 h-3.5" />
          {isAr ? "إيجابي / تجميع" : "Bullish / Buy"}
        </span>
      );
    }
    if (isBearish) {
      return (
        <span className="flex items-center gap-1 px-3 py-1 text-xs font-black bg-[#FF3366] text-white border-2 border-black dark:border-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
          <TrendingDown className="w-3.5 h-3.5" />
          {isAr ? "سلبي / تسييل" : "Bearish / Sell"}
        </span>
      );
    }
    return (
      <span className="px-3 py-1 text-xs font-black bg-[#FFE600] text-black border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
        {isAr ? "محايد / إداري" : "Neutral / Filing"}
      </span>
    );
  };

  return (
    <div className="w-full pt-5 sm:pt-7 pb-16" dir={isAr ? "rtl" : "ltr"}>
      <BrandedPageHeader
        eyebrow={
          isAr
            ? "رادار إفصاحات البورصة المصرية • بالذكاء الاصطناعي"
            : "EGX FILINGS & INSIDER RADAR • AI POWERED"
        }
        title={
          isAr
            ? "إفصاحات الشركات وتعاملات الداخليين"
            : "Company Disclosures & Insider Filings"
        }
        description={
          isAr
            ? "رصد يومي مباشر لنماذج المادة 30، تعاملات كبار المساهمين والداخليين، ومعاينة صور الإفصاحات الرسمية مع التحليل الفوري للأثر المالي على الأسهم."
            : "Live tracking of Article 30 shareholding reports, insider transactions, and official disclosure scans with instant AI financial impact analysis."
        }
        action={
          <button
            type="button"
            onClick={handleOpenGeneralFloatingChat}
            className="inline-flex items-center gap-2 px-4 py-2.5 text-xs sm:text-sm font-black uppercase tracking-wider bg-[#00FF66] text-black border-4 border-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] hover:bg-[#FFE600] active:translate-y-0.5 transition-all cursor-pointer"
          >
            <Bot className="w-4 h-4" />
            {isAr ? "اسأل المساعد الذكي عن أي إفصاح" : "Ask AI Assistant About Filings"}
          </button>
        }
      />

      {/* Neo-Brutalist KPI Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div className="p-4 border-4 border-black dark:border-white bg-white dark:bg-zinc-900 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.4)]">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-black uppercase text-zinc-600 dark:text-zinc-300">
              {isAr ? "إجمالي الإفصاحات" : "Total Filings"}
            </span>
            <FileText className="w-4 h-4 text-black dark:text-white" />
          </div>
          <div className="text-2xl sm:text-3xl font-black text-black dark:text-white">
            {initialStats.total}
          </div>
          <span className="text-[11px] font-bold text-zinc-500 dark:text-zinc-400">
            {isAr ? "مؤرشفة ومحللة بالذكاء الاصطناعي" : "Archived & AI-analyzed"}
          </span>
        </div>

        <div className="p-4 border-4 border-black dark:border-white bg-[#00FF66]/20 dark:bg-[#00FF66]/10 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.4)]">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-black uppercase text-emerald-900 dark:text-[#00FF66]">
              {isAr ? "شراء مطلعين وتجميع" : "Insider Buys & Bullish"}
            </span>
            <TrendingUp className="w-4 h-4 text-emerald-700 dark:text-[#00FF66]" />
          </div>
          <div className="text-2xl sm:text-3xl font-black text-emerald-800 dark:text-[#00FF66]">
            {initialStats.buys}
          </div>
          <span className="text-[11px] font-bold text-emerald-800/80 dark:text-emerald-300/80">
            {isAr ? "إشارات تجميع ودعم شرائي" : "Accumulation & positive catalysts"}
          </span>
        </div>

        <div className="p-4 border-4 border-black dark:border-white bg-[#FF3366]/15 dark:bg-[#FF3366]/10 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.4)]">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-black uppercase text-rose-900 dark:text-[#FF3366]">
              {isAr ? "بيع داخلي وتخارج" : "Insider Sells & Bearish"}
            </span>
            <TrendingDown className="w-4 h-4 text-rose-700 dark:text-[#FF3366]" />
          </div>
          <div className="text-2xl sm:text-3xl font-black text-rose-800 dark:text-[#FF3366]">
            {initialStats.sells}
          </div>
          <span className="text-[11px] font-bold text-rose-800/80 dark:text-rose-300/80">
            {isAr ? "تسييل يستوجب المتابعة" : "Distribution & liquidity exits"}
          </span>
        </div>

        <div className="p-4 border-4 border-black dark:border-white bg-[#FFE600]/35 dark:bg-[#FFE600]/15 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.4)]">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-black uppercase text-black dark:text-[#FFE600]">
              {isAr ? "هياكل المساهمين (مادة 30)" : "Shareholding (Art. 30)"}
            </span>
            <Users className="w-4 h-4 text-black dark:text-[#FFE600]" />
          </div>
          <div className="text-2xl sm:text-3xl font-black text-black dark:text-[#FFE600]">
            {initialStats.shareholding}
          </div>
          <span className="text-[11px] font-bold text-zinc-700 dark:text-zinc-300">
            {isAr ? "حصص الملاك والتداول الحر" : "Major stakes & free float"}
          </span>
        </div>
      </div>

      {/* Controls Bar: Search + Type Filters + Sentiment Filters */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 mb-8">
        {/* Search Input */}
        <div className="lg:col-span-4 relative flex items-center">
          <Search className="absolute left-3.5 w-4 h-4 text-black/70 dark:text-white/70 pointer-events-none" />
          <input
            type="text"
            placeholder={
              isAr
                ? "ابحث برمز السهم (COMI, FWRY, PRMH) أو اسم الشركة..."
                : "Search symbol (COMI, FWRY, PRMH) or company..."
            }
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-11 w-full rounded-none pl-10 pr-8 text-xs font-black outline-none border-4 border-black bg-white dark:bg-zinc-900 text-black dark:text-white dark:border-white focus:bg-[#FFE600] focus:text-black transition-none shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.4)]"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              className="absolute right-2.5 px-1.5 py-0.5 text-[10px] font-black bg-black text-white dark:bg-white dark:text-black"
            >
              ×
            </button>
          )}
        </div>

        {/* Disclosure Type Filter Buttons */}
        <div className="lg:col-span-5 flex flex-wrap gap-1.5 items-center">
          <span className="text-xs font-black uppercase tracking-wider flex items-center gap-1 text-black dark:text-white me-1">
            <Filter className="w-3.5 h-3.5" />
            {isAr ? "النوع:" : "Type:"}
          </span>
          {[
            { id: "all", ar: "الكل", en: "All" },
            { id: "insider_trading", ar: "تعاملات داخليين", en: "Insiders" },
            { id: "major_shareholders", ar: "مادة 30", en: "Art. 30" },
            { id: "board_resolution", ar: "مجلس الإدارة", en: "Board" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setSelectedType(tab.id)}
              className={`px-2.5 py-1.5 text-xs font-black rounded-none border-3 border-black dark:border-white transition-none cursor-pointer ${
                selectedType === tab.id
                  ? "bg-black text-white dark:bg-white dark:text-black shadow-[2px_2px_0px_0px_#FFE600]"
                  : "bg-white text-black dark:bg-zinc-900 dark:text-white hover:bg-[#FFE600] hover:text-black"
              }`}
            >
              {isAr ? tab.ar : tab.en}
            </button>
          ))}
        </div>

        {/* Sentiment Filter Buttons */}
        <div className="lg:col-span-3 flex flex-wrap gap-1.5 items-center">
          <span className="text-xs font-black uppercase tracking-wider text-black dark:text-white me-1">
            {isAr ? "الأثر:" : "Impact:"}
          </span>
          {[
            { id: "all", ar: "الكل", en: "All" },
            { id: "bullish", ar: "إيجابي", en: "Bullish" },
            { id: "bearish", ar: "سلبي", en: "Bearish" },
            { id: "neutral", ar: "محايد", en: "Neutral" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setSelectedSentiment(tab.id)}
              className={`px-2.5 py-1.5 text-xs font-black rounded-none border-3 border-black dark:border-white transition-none cursor-pointer ${
                selectedSentiment === tab.id
                  ? "bg-black text-white dark:bg-white dark:text-black shadow-[2px_2px_0px_0px_#FFE600]"
                  : "bg-white text-black dark:bg-zinc-900 dark:text-white hover:bg-[#FFE600] hover:text-black"
              }`}
            >
              {isAr ? tab.ar : tab.en}
            </button>
          ))}
        </div>
      </div>

      {/* Status Bar with View Mode Toggle */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5 px-3 py-2 border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900 text-xs font-black text-black dark:text-white">
        <span>
          {isAr
            ? `المعروض حالياً: ${disclosures.length} من أصل ${totalCount} إفصاح (تحميل ذكي تدريجي)`
            : `Showing ${disclosures.length} of ${totalCount} disclosures (progressive smart loading)`}
        </span>

        <div className="flex items-center gap-2">
          {/* List / Grid Mode Switcher */}
          <div className="flex border-2 border-black dark:border-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_0px_rgba(255,255,255,0.4)]">
            <button
              type="button"
              onClick={() => setLayoutMode("list")}
              className={`px-2.5 py-1 flex items-center gap-1.5 text-xs font-black transition-none cursor-pointer ${
                layoutMode === "list"
                  ? "bg-black text-white dark:bg-white dark:text-black"
                  : "bg-white text-black dark:bg-zinc-800 dark:text-white hover:bg-[#FFE600] hover:text-black"
              }`}
              title={isAr ? "عرض أفقي (قائمة)" : "List View"}
            >
              <LayoutList className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{isAr ? "أفقي (قائمة)" : "List"}</span>
            </button>
            <button
              type="button"
              onClick={() => setLayoutMode("grid")}
              className={`px-2.5 py-1 flex items-center gap-1.5 text-xs font-black transition-none cursor-pointer ${
                layoutMode === "grid"
                  ? "bg-black text-white dark:bg-white dark:text-black"
                  : "bg-white text-black dark:bg-zinc-800 dark:text-white hover:bg-[#FFE600] hover:text-black"
              }`}
              title={isAr ? "عرض شبكي (كروت)" : "Grid View"}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{isAr ? "شبكي (جريد)" : "Grid"}</span>
            </button>
          </div>

          {(search || selectedType !== "all" || selectedSentiment !== "all") && (
            <button
              type="button"
              onClick={() => {
                setSearch("");
                setSelectedType("all");
                setSelectedSentiment("all");
              }}
              className="px-2.5 py-1 bg-[#FFE600] text-black border-2 border-black font-black text-xs cursor-pointer hover:bg-white transition-none"
            >
              {isAr ? "إعادة ضبط الفلاتر" : "Reset Filters"}
            </button>
          )}
        </div>
      </div>

      {/* Disclosures Feed */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 border-4 border-dashed border-black/30 dark:border-white/30 bg-zinc-50 dark:bg-zinc-900/40">
          <Loader2 className="w-10 h-10 animate-spin text-yellow-500" />
          <span className="text-sm font-black uppercase tracking-widest text-zinc-600 dark:text-zinc-300">
            {isAr ? "جاري تحميل الإفصاحات..." : "Loading disclosures..."}
          </span>
        </div>
      ) : disclosures.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 border-4 border-dashed border-black/30 dark:border-white/30 bg-zinc-50 dark:bg-zinc-900/40 text-zinc-600 dark:text-zinc-300">
          <AlertCircle className="w-10 h-10 text-zinc-400" />
          <span className="text-sm font-black uppercase tracking-widest">
            {isAr
              ? "لا توجد إفصاحات مطابقة للفلاتر الحالية"
              : "No disclosures matching current filters"}
          </span>
        </div>
      ) : (
        <>
          {layoutMode === "grid" ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {disclosures.map((item) => {
              const isPdfSource = Boolean(
                item.source_url && item.source_url.toLowerCase().includes(".pdf")
              );
              const shortCode = item.id.slice(0, 8).toUpperCase();

              return (
                <article
                  key={item.id}
                  className="flex flex-col justify-between p-4 rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-900 shadow-[5px_5px_0px_0px_rgba(0,0,0,1)] dark:shadow-[5px_5px_0px_0px_rgba(255,255,255,0.4)] transition-all"
                >
                  <div className="flex flex-col gap-3">
                    {/* Grid Card Top Header */}
                    <div className="flex items-center justify-between gap-2 pb-2.5 border-b-2 border-black/15 dark:border-white/15">
                      <div className="flex items-center gap-2">
                        <StockLogo
                          symbol={item.symbol || "EGX"}
                          size="sm"
                          className="border-2 border-black dark:border-white rounded-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
                        />
                        {item.symbol ? (
                          <Link
                            prefetch={false}
                            href={`/stocks/${item.symbol.toLowerCase()}`}
                            className="px-2 py-0.5 text-xs font-black uppercase tracking-wider bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white hover:bg-[#FFE600] hover:text-black transition-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
                          >
                            {item.symbol}
                          </Link>
                        ) : (
                          <span className="px-2 py-0.5 text-xs font-black uppercase bg-zinc-200 dark:bg-zinc-800 text-black dark:text-white border-2 border-black">
                            EGX
                          </span>
                        )}
                        <span className="text-xs font-mono font-black text-zinc-500 dark:text-zinc-400">
                          #{shortCode}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {getSentimentBadge(item)}
                      </div>
                    </div>

                    {/* Company Name & Date & Type */}
                    <div className="flex items-center justify-between text-xs font-bold text-zinc-600 dark:text-zinc-400">
                      <span className="font-black text-black dark:text-white truncate max-w-[170px]" title={item.company_name}>
                        {item.company_name}
                      </span>
                      <span className="flex items-center gap-1 shrink-0 text-[11px] font-black">
                        <Calendar className="w-3 h-3" />
                        {item.disclosure_date}
                      </span>
                    </div>

                    <div className="inline-block self-start px-2 py-0.5 text-[10px] font-black bg-zinc-100 dark:bg-zinc-800 text-black dark:text-white border border-black dark:border-white">
                      {getTypeLabel(item.disclosure_type)}
                    </div>

                    {/* Title */}
                    <h2 className="text-sm font-black text-black dark:text-white line-clamp-2 leading-snug">
                      {item.title}
                    </h2>

                    {/* Quant chips if present */}
                    {(item.party_name || item.shares_count || item.stake_before != null || item.stake_after != null) && (
                      <div className="flex flex-wrap items-center gap-1.5 p-2 bg-zinc-50 dark:bg-zinc-950 border border-black dark:border-zinc-700 text-[11px] font-bold text-black dark:text-white">
                        {item.party_name && (
                          <span className="truncate max-w-full">
                            {isAr ? "الطرف: " : "Party: "}
                            <strong className="font-black">{item.party_name}</strong>
                          </span>
                        )}
                        {item.shares_count != null && (
                          <span className="px-1.5 py-0.5 bg-[#FFE600] text-black font-black text-[10px] border border-black">
                            {Number(item.shares_count).toLocaleString()} {isAr ? "سهم" : "sh"}
                          </span>
                        )}
                        {(item.stake_before != null || item.stake_after != null) && (
                          <span className="font-black text-[10px]">
                            {item.stake_before ?? "—"}% → {item.stake_after ?? "—"}%
                          </span>
                        )}
                      </div>
                    )}

                    {/* AI Analysis Box */}
                    <div className="p-2.5 bg-yellow-50 dark:bg-yellow-950/25 border-2 border-dashed border-yellow-600 dark:border-yellow-500/60">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Sparkles className="w-3.5 h-3.5 text-yellow-600 dark:text-yellow-400 shrink-0" />
                        <span className="text-[10px] font-black uppercase text-yellow-800 dark:text-yellow-400">
                          {isAr ? "تحليل الذكاء الاصطناعي:" : "AI Analysis:"}
                        </span>
                      </div>
                      <p className="text-xs font-bold text-zinc-800 dark:text-zinc-200 line-clamp-3 leading-relaxed">
                        {item.ai_summary}
                      </p>
                    </div>

                    {/* Authentic PDF Viewer inside Grid Card */}
                    <div className="border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-950 overflow-hidden shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                      <div className="flex items-center justify-between px-2 py-1 bg-black text-white text-[10px] font-black">
                        <span className="flex items-center gap-1 text-[#FFE600]">
                          <FileText className="w-3 h-3" />
                          {isAr ? "مستند الـ PDF الأصلي" : "Official PDF Document"}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            setPreviewItem(item);
                            setPreviewMode("pdf");
                          }}
                          className="text-black bg-[#FFE600] px-1.5 py-0.2 hover:bg-white flex items-center gap-0.5 font-black text-[9px] cursor-pointer"
                        >
                          <ZoomIn className="w-2.5 h-2.5" />
                          {isAr ? "تكبير" : "Zoom"}
                        </button>
                      </div>
                      <iframe
                        src={`/api/disclosures/pdf/${item.id}#toolbar=0&navpanes=0`}
                        title={item.title}
                        className="w-full h-[180px] border-0 bg-white"
                      />
                    </div>
                  </div>

                  {/* Grid Card Footer Action Buttons */}
                  <div className="flex flex-col gap-2 pt-3 mt-3 border-t-2 border-black/15 dark:border-white/15">
                    <button
                      type="button"
                      onClick={() => handleDiscussInFloatingChat(item)}
                      className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-black bg-[#00FF66] text-black border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:bg-[#FFE600] active:translate-y-0.5 transition-all cursor-pointer"
                    >
                      <Bot className="w-3.5 h-3.5" />
                      {isAr ? "ناقش في الشات" : "Discuss in Chat"}
                    </button>

                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => {
                          setPreviewItem(item);
                          setPreviewMode("pdf");
                        }}
                        className="flex-1 inline-flex items-center justify-center gap-1 px-2 py-1.5 text-[11px] font-black bg-white dark:bg-zinc-800 text-black dark:text-white border-2 border-black dark:border-white hover:bg-[#FFE600] hover:text-black transition-all cursor-pointer"
                      >
                        <ZoomIn className="w-3 h-3" />
                        {isAr ? "معاينة كاملة" : "Preview"}
                      </button>

                      <a
                        href={`/api/disclosures/pdf/${item.id}`}
                        download={`egx_disclosure_${item.symbol || 'official'}.pdf`}
                        className="flex-1 inline-flex items-center justify-center gap-1 px-2 py-1.5 text-[11px] font-black bg-zinc-100 dark:bg-zinc-800 text-black dark:text-white border-2 border-black dark:border-white hover:bg-[#FFE600] hover:text-black transition-all"
                      >
                        <Download className="w-3 h-3" />
                        {isAr ? "تحميل PDF" : "Download"}
                      </a>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="flex flex-col gap-6">
          {disclosures.map((item) => {
            const docImageUrl = `/api/disclosures/image/${item.id}`;
            const isPdfSource = Boolean(
              item.source_url && item.source_url.toLowerCase().includes(".pdf")
            );
            const shortCode = item.id.slice(0, 8).toUpperCase();

            return (
              <article
                key={item.id}
                className="p-5 md:p-6 rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-900 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.5)] transition-all"
              >
                {/* Card Top Header Row */}
                <div className="flex flex-wrap justify-between items-center gap-3 mb-4 pb-3 border-b-2 border-black/15 dark:border-white/15">
                  <div className="flex items-center gap-3 flex-wrap">
                    <StockLogo
                      symbol={item.symbol || "EGX"}
                      size="sm"
                      className="border-2 border-black dark:border-white rounded-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
                    />
                    {item.symbol ? (
                      <Link
                        prefetch={false}
                        href={`/stocks/${item.symbol.toLowerCase()}`}
                        className="px-2.5 py-1 text-xs font-black uppercase tracking-wider bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white hover:bg-[#FFE600] hover:text-black transition-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
                      >
                        {item.symbol}.EGX
                      </Link>
                    ) : (
                      <span className="px-2.5 py-1 text-xs font-black uppercase tracking-wider bg-zinc-200 dark:bg-zinc-800 text-black dark:text-white border-2 border-black dark:border-white">
                        EGX
                      </span>
                    )}
                    <span className="text-sm font-black text-black dark:text-white">
                      {item.company_name}
                    </span>
                    <span
                      title={item.id}
                      className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono font-black bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border border-black/40 dark:border-white/40"
                    >
                      <Hash className="w-3 h-3" />
                      {shortCode}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="px-2.5 py-1 text-[11px] font-black bg-zinc-100 dark:bg-zinc-800 text-black dark:text-white border-2 border-black dark:border-white">
                      {getTypeLabel(item.disclosure_type)}
                    </span>
                    <span className="flex items-center gap-1 text-xs font-black text-zinc-600 dark:text-zinc-300">
                      <Calendar className="w-3.5 h-3.5" />
                      {item.disclosure_date}
                    </span>
                    {getSentimentBadge(item)}
                  </div>
                </div>

                {/* Main Content Grid: Left/Right — Details + AI Analysis & Inline Document Image */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
                  {/* Text & AI Explanation (7 cols on desktop) */}
                  <div className="lg:col-span-7 flex flex-col gap-3.5">
                    <h2 className="text-base sm:text-lg font-black text-black dark:text-white leading-snug">
                      {item.title}
                    </h2>

                    {/* Quantitative Transaction Metadata Chips */}
                    {(item.party_name || item.shares_count || item.stake_before != null || item.stake_after != null) && (
                      <div className="flex flex-wrap items-center gap-2 p-3 bg-zinc-50 dark:bg-zinc-950 border-2 border-black dark:border-zinc-700 text-xs font-bold text-black dark:text-white">
                        {item.party_name && (
                          <span className="px-2 py-1 bg-white dark:bg-zinc-900 border border-black dark:border-zinc-700">
                            {isAr ? "الطرف المفصح: " : "Party: "}
                            <strong className="font-black">{item.party_name}</strong>
                          </span>
                        )}
                        {item.shares_count != null && (
                          <span className="px-2 py-1 bg-[#FFE600] text-black border border-black font-black">
                            {isAr ? "الكمية: " : "Shares: "}
                            {Number(item.shares_count).toLocaleString()}{" "}
                            {isAr ? "سهم" : "sh"}
                          </span>
                        )}
                        {(item.stake_before != null || item.stake_after != null) && (
                          <span className="px-2 py-1 bg-white dark:bg-zinc-900 border border-black dark:border-zinc-700 font-black">
                            {isAr ? "الحصة: " : "Stake: "}
                            {item.stake_before ?? "—"}% ← {item.stake_after ?? "—"}%
                          </span>
                        )}
                      </div>
                    )}

                    {/* AI Analysis Box */}
                    <div className="p-4 bg-yellow-50 dark:bg-yellow-950/25 border-3 border-dashed border-yellow-600 dark:border-yellow-500/60">
                      <div className="flex items-center gap-2 mb-1.5">
                        <Sparkles className="w-4 h-4 text-yellow-600 dark:text-yellow-400 shrink-0" />
                        <span className="text-xs font-black uppercase tracking-wider text-yellow-800 dark:text-yellow-400">
                          {isAr
                            ? "تحليل الذكاء الاصطناعي ومعنى الإفصاح للمتداول:"
                            : "AI Financial Analysis & Market Meaning:"}
                        </span>
                      </div>
                      <p className="text-xs sm:text-sm font-bold text-zinc-800 dark:text-zinc-200 leading-relaxed">
                        {item.ai_summary}
                      </p>

                      {item.metadata?.key_takeaway && (
                        <div className="mt-3 pt-2.5 border-t border-yellow-600/30 flex items-center gap-1.5 text-xs font-black text-emerald-700 dark:text-[#00FF66]">
                          <CheckCircle2 className="w-4 h-4 shrink-0" />
                          <span>
                            {isAr ? "الخلاصة: " : "Key Takeaway: "}
                            {item.metadata.key_takeaway}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Action Buttons Row */}
                    <div className="flex flex-wrap items-center gap-2.5 pt-1">
                      <button
                        type="button"
                        onClick={() => handleDiscussInFloatingChat(item)}
                        className="inline-flex items-center gap-2 px-4 py-2 text-xs font-black bg-[#00FF66] text-black border-3 border-black shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:bg-[#FFE600] active:translate-y-0.5 transition-all cursor-pointer"
                      >
                        <Bot className="w-4 h-4" />
                        {isAr
                          ? "ناقش هذا الإفصاح في الشات العائم"
                          : "Discuss in Floating AI Chat"}
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setPreviewItem(item);
                          setPreviewMode("pdf");
                        }}
                        className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-black bg-white dark:bg-zinc-800 text-black dark:text-white border-3 border-black dark:border-white shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:bg-[#FFE600] hover:text-black transition-all cursor-pointer"
                      >
                        <ZoomIn className="w-3.5 h-3.5" />
                        {isAr ? "معاينة ملف الـ PDF الأصلي" : "View Original PDF"}
                      </button>

                      {item.symbol && (
                        <Link
                          prefetch={false}
                          href={`/stocks/${item.symbol.toLowerCase()}`}
                          className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-black bg-white dark:bg-zinc-800 text-black dark:text-white border-3 border-black dark:border-white shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:bg-[#FFE600] hover:text-black transition-all"
                        >
                          {isAr ? `صفحة سهم ${item.symbol}` : `${item.symbol} Stock Page`}
                        </Link>
                      )}

                      {item.source_url && (
                        <a
                          href={item.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-black bg-zinc-100 dark:bg-zinc-800 text-black dark:text-white border-3 border-black dark:border-white shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:bg-[#FFE600] hover:text-black transition-all"
                        >
                          <span>
                            {isAr
                              ? isPdfSource
                                ? "ملف PDF الأصلي"
                                : "رابط المصدر الأصلي"
                              : isPdfSource
                              ? "Original PDF Link"
                              : "Original Source Link"}
                          </span>
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </div>
                  </div>

                  {/* Inline Official PDF Document Preview (5 cols on desktop) */}
                  <div className="lg:col-span-5">
                    <div className="border-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-950 p-2 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.3)]">
                      <div className="flex items-center justify-between px-2.5 py-1.5 mb-2 bg-black text-white text-[11px] font-black">
                        <span className="flex items-center gap-1.5 text-[#FFE600]">
                          <FileText className="w-4 h-4" />
                          {isAr ? "مستند الإفصاح الرسمي (PDF معتمد)" : "Official Filing Document (PDF)"}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            setPreviewItem(item);
                            setPreviewMode("pdf");
                          }}
                          className="text-black bg-[#FFE600] px-2 py-0.5 border border-black hover:bg-white flex items-center gap-1 cursor-pointer font-black text-[10px]"
                        >
                          <ZoomIn className="w-3 h-3" />
                          {isAr ? "تكبير المستند" : "Fullscreen"}
                        </button>
                      </div>

                      <div className="relative border-2 border-black bg-white overflow-hidden">
                        <iframe
                          src={`/api/disclosures/pdf/${item.id}#toolbar=0&navpanes=0`}
                          title={item.title}
                          className="w-full h-[360px] border-0 bg-white"
                        />
                        <div className="p-2 bg-zinc-50 dark:bg-zinc-900 border-t-2 border-black dark:border-white flex items-center justify-between gap-2 text-xs">
                          <span className="text-[11px] font-black text-zinc-700 dark:text-zinc-300 truncate">
                            {isAr ? "ملف الإفصاح الأصلي - البورصة المصرية" : "Authentic EGX Filing Document"}
                          </span>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <a
                              href={`/api/disclosures/pdf/${item.id}`}
                              download={`egx_disclosure_${item.symbol || 'official'}.pdf`}
                              className="px-2 py-1 bg-white dark:bg-zinc-800 text-black dark:text-white border border-black dark:border-white font-black text-[10px] hover:bg-[#FFE600] hover:text-black transition-all flex items-center gap-1"
                            >
                              <Download className="w-3 h-3" />
                              {isAr ? "تحميل PDF" : "Download"}
                            </a>
                            <button
                              type="button"
                              onClick={() => {
                                setPreviewItem(item);
                                setPreviewMode("pdf");
                              }}
                              className="px-2 py-1 bg-[#00FF66] text-black border border-black font-black text-[10px] hover:bg-[#FFE600] transition-all flex items-center gap-1 cursor-pointer"
                            >
                              <ZoomIn className="w-3 h-3" />
                              {isAr ? "عرض كامل" : "Full View"}
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
          </div>
        )}

          {/* Progressive Load More Trigger & Button */}
          <div ref={loadMoreTriggerRef} className="pt-4 flex flex-col items-center justify-center">
            {hasMore ? (
              <button
                type="button"
                disabled={loadingMore}
                onClick={() => void fetchBatch(disclosures.length, true)}
                className="inline-flex items-center gap-2 px-6 py-3 text-xs sm:text-sm font-black uppercase bg-[#FFE600] text-black border-4 border-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] hover:bg-[#00FF66] disabled:opacity-50 cursor-pointer"
              >
                {loadingMore ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {isAr ? "جاري تحميل دفعة جديدة..." : "Loading next batch..."}
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-4 h-4" />
                    {isAr
                      ? `تحميل المزيد من الإفصاحات (${totalCount - disclosures.length} متبقي)`
                      : `Load More Disclosures (${totalCount - disclosures.length} remaining)`}
                  </>
                )}
              </button>
            ) : (
              <span className="text-xs font-black uppercase text-zinc-500 dark:text-zinc-400">
                {isAr
                  ? `تم عرض جميع الإفصاحات المطابقة (${disclosures.length})`
                  : `All matching disclosures loaded (${disclosures.length})`}
              </span>
            )}
          </div>
        </>
      )}

      {/* Full-Screen PDF Document Viewer Lightbox Modal */}
      {previewItem && (
        <div
          className="fixed inset-0 z-[200] bg-black/85 backdrop-blur-sm flex items-center justify-center p-2 sm:p-5"
          onClick={() => setPreviewItem(null)}
        >
          <div
            className="relative w-full max-w-6xl max-h-[95vh] h-[92vh] flex flex-col border-4 border-black dark:border-white bg-white dark:bg-zinc-900 shadow-[10px_10px_0px_0px_#FFE600] overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 bg-black text-white border-b-4 border-black dark:border-white">
              <div className="flex items-center gap-2 min-w-0">
                <span className="px-2 py-0.5 text-xs font-black bg-[#FFE600] text-black">
                  {previewItem.symbol || "EGX"}
                </span>
                <span className="text-xs sm:text-sm font-black truncate">
                  {previewItem.company_name} — #{previewItem.id.slice(0, 8).toUpperCase()}
                </span>
                <span className="hidden sm:inline-block px-2 py-0.5 text-[10px] font-black bg-zinc-800 text-zinc-300 border border-zinc-700">
                  {previewItem.disclosure_date}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <a
                  href={`/api/disclosures/pdf/${previewItem.id}`}
                  download={`egx_disclosure_${previewItem.symbol || 'official'}.pdf`}
                  className="px-3 py-1 text-xs font-black bg-[#FFE600] text-black border-2 border-white hover:bg-white transition-all flex items-center gap-1 cursor-pointer"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">{isAr ? "تحميل الـ PDF" : "Download PDF"}</span>
                </a>

                {previewItem.source_url && (
                  <a
                    href={previewItem.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-2.5 py-1 text-xs font-black bg-zinc-800 text-white border-2 border-white hover:bg-[#FFE600] hover:text-black transition-all flex items-center gap-1"
                  >
                    <ExternalLink className="w-3 h-3" />
                    <span className="hidden sm:inline">{isAr ? "المصدر الأصلي" : "Original"}</span>
                  </a>
                )}

                <button
                  type="button"
                  onClick={() => {
                    const itemToDiscuss = previewItem;
                    setPreviewItem(null);
                    handleDiscussInFloatingChat(itemToDiscuss);
                  }}
                  className="px-3 py-1 text-xs font-black bg-[#00FF66] text-black border-2 border-white hover:bg-[#FFE600] transition-all flex items-center gap-1 cursor-pointer"
                >
                  <Bot className="w-3.5 h-3.5" />
                  <span>{isAr ? "ناقش في الشات" : "Discuss in Chat"}</span>
                </button>

                <button
                  type="button"
                  onClick={() => setPreviewItem(null)}
                  className="h-8 w-8 flex items-center justify-center bg-[#FF3366] text-white border-2 border-white font-black hover:bg-black transition-all cursor-pointer"
                  aria-label="Close preview"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Modal Body: Full Live PDF Iframe */}
            <div className="flex-1 w-full h-full bg-zinc-800 p-2 overflow-hidden">
              <iframe
                src={`/api/disclosures/pdf/${previewItem.id}#view=FitH`}
                title={previewItem.title}
                className="w-full h-full border-2 border-black bg-white shadow-2xl"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
