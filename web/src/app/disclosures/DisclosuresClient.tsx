"use client";

import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
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
  Layers,
  Target,
  ShieldCheck,
  Scale,
  DollarSign,
  Briefcase,
  PieChart,
} from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import { useChat } from "@/contexts/ChatContext";
import BrandedPageHeader from "@/components/BrandedPageHeader";
import StockLogo from "@/components/StockLogo";
import {
  DisclosuresAnalyticsResult,
  EGX_SECTORS,
  TimeframePeriod,
  filterDisclosuresByTimeframeAndSector,
  analyzeDisclosures,
  SymbolPriceInfo,
} from "@/lib/disclosures-analytics";
import InsiderHeatmap from "@/components/disclosures/InsiderHeatmap";
import InsiderCharts from "@/components/disclosures/InsiderCharts";
import MajorShareholdersTab from "@/components/disclosures/MajorShareholdersTab";
import DisclosuresGlossary from "@/components/disclosures/DisclosuresGlossary";
import StockDetailModal from "@/components/disclosures/StockDetailModal";

export interface DisclosureItem {
  id: string;
  symbol: string | null;
  company_name: string;
  disclosure_type: string;
  disclosure_date: string;
  title: string;
  raw_content?: string | null;
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
    execution_price?: number;
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
  initialPool?: DisclosureItem[];
  initialStats: DisclosuresInitialStats;
  initialAnalytics?: DisclosuresAnalyticsResult;
  priceMap?: Record<string, SymbolPriceInfo>;
}

const PAGE_BATCH_SIZE = 12;

export default function DisclosuresClient({
  initialDisclosures,
  initialPool,
  initialStats,
  initialAnalytics,
  priceMap,
}: DisclosuresClientProps) {
  const { language } = useLanguage();
  const isAr = language === "ar";
  const { setIsOpen, sendMessage } = useChat();

  // Active top-level subtab: Insider Radar & Liquidity VS Major Shareholders & Founders (Art. 30)
  const [activeTab, setActiveTab] = useState<"insider_radar" | "major_shareholders">("insider_radar");

  // Filters: Timeframe & Sector
  const [selectedTimeframe, setSelectedTimeframe] = useState<TimeframePeriod>("all");
  const [selectedSector, setSelectedSector] = useState<string>("all");

  // Stock Deep-Dive Modal state
  const [modalSymbol, setModalSymbol] = useState<string | null>(null);

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
  const [smartFilter, setSmartFilter] = useState<"all" | "below_cost" | "accumulating" | "distributing">("all");
  const [layoutMode, setLayoutMode] = useState<"list" | "grid">("list");

  // Modal state for full-screen disclosure image / PDF inspection
  const [previewItem, setPreviewItem] = useState<DisclosureItem | null>(null);
  const [previewMode, setPreviewMode] = useState<"image" | "pdf">("pdf");

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
          timeframe: selectedTimeframe,
          sector: selectedSector,
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
      } catch (err: any) {
        if (
          signal?.aborted ||
          err?.name === "AbortError" ||
          err?.name === "CanceledError" ||
          (err instanceof Error && (err.name === "AbortError" || err.message?.toLowerCase().includes("abort")))
        ) {
          return;
        }
        console.error("Error loading disclosures batch:", err);
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [debouncedSearch, selectedType, selectedSentiment, selectedTimeframe, selectedSector]
  );

  // Trigger fresh fetch when filters or search change (skip initial SSR render if default filters)
  useEffect(() => {
    if (isInitialMountRef.current) {
      isInitialMountRef.current = false;
      if (
        !debouncedSearch &&
        selectedType === "all" &&
        selectedSentiment === "all" &&
        selectedTimeframe === "all" &&
        selectedSector === "all"
      ) {
        return;
      }
    }
    const controller = new AbortController();
    fetchBatch(0, false, controller.signal).catch(() => {});
    return () => {
      try {
        controller.abort();
      } catch {}
    };
  }, [debouncedSearch, selectedType, selectedSentiment, selectedTimeframe, selectedSector, fetchBatch]);

  // Progressive infinite scroll observer ("يحمل شوية بشوية")
  useEffect(() => {
    const node = loadMoreTriggerRef.current;
    if (!node || !hasMore || loading || loadingMore || activeTab !== "insider_radar") return;

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
  }, [hasMore, loading, loadingMore, disclosures.length, fetchBatch, activeTab]);

  // Open floating ChatWidget directly on the current page without navigating away!
  const handleDiscussInFloatingChat = (item: DisclosureItem) => {
    const symPart = item.symbol ? ` (${item.symbol})` : "";
    const prompt = `ناقش معي بالتفصيل إفصاح ${item.company_name}${symPart} الصادر بتاريخ ${item.disclosure_date} بعنوان: "${item.title}". اشرح لي تفاصيله المخزنة وأثره المالي والفني على السهم، وجهز صورة الإفصاح إن طلبتها.`;

    setIsOpen(true);
    sendMessage(prompt);
  };

  const handleOpenGeneralFloatingChat = () => {
    setIsOpen(true);
    sendMessage(
      "لخص لي أهم إفصاحات وتعاملات الداخليين في البورصة المصرية لآخر جلسة، مع بيان أي أسهم تشهد تجميعاً صامتاً من مجالس الإدارة أو تتداول بأقل من تكلفة شرائهم."
    );
  };

  // Switch to Major Shareholders Tab and filter by symbol
  const handleInspectShareholders = (symbol: string) => {
    setActiveTab("major_shareholders");
    setSearch(symbol);
    window.scrollTo({ top: 380, behavior: "smooth" });
  };

  const formatEgp = (val: number) => {
    const abs = Math.abs(val);
    if (abs >= 1_000_000) {
      return `${(val / 1_000_000).toFixed(1)} ${isAr ? "مليون ج.م" : "M EGP"}`;
    }
    if (abs >= 1_000) {
      return `${(val / 1_000).toFixed(0)} ${isAr ? "ألف ج.م" : "k EGP"}`;
    }
    return `${val.toFixed(0)} ${isAr ? "ج.م" : "EGP"}`;
  };

  const getTypeLabel = (type: string) => {
    switch (type) {
      case "insider_trading":
        return isAr ? "تعاملات مطلعين وداخليين" : "Insider Trading";
      case "major_shareholders":
        return isAr ? "هيكل مساهمين (مادة 30)" : "Shareholding Structure";
      case "board_resolution":
        return isAr ? "قرارات مجلس إدارة" : "Board Resolution";
      case "material_event":
        return isAr ? "أحداث جوهرية" : "Material Event";
      default:
        return isAr ? "إفصاح رسمي" : "Official Disclosure";
    }
  };

  const getSentimentBadge = (item: DisclosureItem) => {
    if (item.action_type === "buy" || item.sentiment === "bullish") {
      return (
        <span className="px-3 py-1 text-xs font-black bg-[#00FF66] text-black border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
          {item.action_type === "buy"
            ? isAr ? "شراء داخلي / تجميع" : "Insider Buy"
            : isAr ? "إيجابي / محفز" : "Bullish"}
        </span>
      );
    }
    if (item.action_type === "sell" || item.sentiment === "bearish") {
      return (
        <span className="px-3 py-1 text-xs font-black bg-[#FF3366] text-white border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
          {item.action_type === "sell"
            ? isAr ? "بيع داخلي / تخارج" : "Insider Sell"
            : isAr ? "سلبي / تسييل" : "Bearish"}
        </span>
      );
    }
    return (
      <span className="px-3 py-1 text-xs font-black bg-[#FFE600] text-black border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
        {isAr ? "محايد / إداري" : "Neutral / Filing"}
      </span>
    );
  };

  // Analytical pool (all available disclosures in the dataset)
  const basePool = useMemo(() => {
    return initialPool && initialPool.length > 0 ? initialPool : disclosures;
  }, [initialPool, disclosures]);

  // Filter pool by active timeframe and sector
  const filteredPool = useMemo(() => {
    return filterDisclosuresByTimeframeAndSector(
      basePool,
      selectedTimeframe,
      selectedSector
    );
  }, [basePool, selectedTimeframe, selectedSector]);

  // Dynamically compute active analytics for the selected timeframe and sector
  const activeAnalytics = useMemo(() => {
    if (selectedTimeframe === "all" && selectedSector === "all" && initialAnalytics) {
      return initialAnalytics;
    }
    return analyzeDisclosures(filteredPool, priceMap || {});
  }, [filteredPool, priceMap, selectedTimeframe, selectedSector, initialAnalytics]);

  // Date range of the active timeframe
  const timeframeDateRange = useMemo(() => {
    if (filteredPool.length === 0) return null;
    const dates = filteredPool.map((d) => d.disclosure_date).filter(Boolean).sort();
    if (dates.length === 0) return null;
    return {
      from: dates[0],
      to: dates[dates.length - 1],
      count: filteredPool.length,
    };
  }, [filteredPool]);

  // Filter disclosures based on smart filter, timeframe, and sector
  const displayedDisclosures = useMemo(() => {
    let list = disclosures;
    if (selectedTimeframe !== "all" || selectedSector !== "all") {
      list = filterDisclosuresByTimeframeAndSector(list, selectedTimeframe, selectedSector);
    }
    const metrics = activeAnalytics.symbolMetrics;

    return list.filter((item) => {
      const sym = item.symbol ? item.symbol.toUpperCase() : null;
      if (!sym || !metrics[sym]) return true;

      const m = metrics[sym];
      if (smartFilter === "below_cost") {
        return m.discount_pct < -1.0;
      }
      if (smartFilter === "accumulating") {
        return m.action_bias === "accumulating";
      }
      if (smartFilter === "distributing") {
        return m.action_bias === "distributing";
      }
      return true;
    });
  }, [disclosures, selectedTimeframe, selectedSector, smartFilter, activeAnalytics]);

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

      {/* Legal & Regulatory Compliance Badge */}
      <div className="mb-6 p-3 rounded-none border-2 border-black dark:border-white/20 bg-emerald-950/20 dark:bg-emerald-950/30 flex items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2.5">
          <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
          <span className="font-bold text-zinc-800 dark:text-zinc-200">
            {isAr
              ? "بيانات مالية عامة معلنة رسمياً: تعاملات الداخليين ونماذج المادة (30) منشورة وفقاً لقواعد قيد وشطب الأوراق المالية بالبورصة المصرية والهيئة العامة للرقابة المالية."
              : "Official Public Market Data: All insider disclosures and Article 30 filings are sourced from official Egyptian Exchange (EGX) and FRA disclosures."}
          </span>
        </div>
        <span className="hidden md:inline-block px-2.5 py-0.5 border border-black bg-[#FFE600] text-black font-black text-[10px] uppercase shadow-[1px_1px_0px_#000]">
          {isAr ? "مستندات معتمدة 100%" : "VERIFIED DOCS"}
        </span>
      </div>

      {/* Executive KPI Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {/* KPI 1: Total Disclosures */}
        <div className="p-4 border-4 border-black dark:border-white bg-white dark:bg-zinc-900 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.4)]">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-black uppercase text-zinc-600 dark:text-zinc-300">
              {isAr ? "إجمالي الإفصاحات" : "Total Filings"}
            </span>
            <FileText className="w-4 h-4 text-black dark:text-white" />
          </div>
          <div className="text-2xl sm:text-3xl font-black text-black dark:text-white">
            {selectedTimeframe === "all" && selectedSector === "all"
              ? initialStats.total || filteredPool.length
              : filteredPool.length}
          </div>
          <span className="text-[11px] font-bold text-zinc-500 dark:text-zinc-400">
            {isAr ? "مؤرشفة ومحللة بالذكاء الاصطناعي" : "Archived & AI-analyzed"}
          </span>
        </div>

        {/* KPI 2: Net Insider Liquidity Flow (EGP) */}
        <div className="p-4 border-4 border-black dark:border-white bg-[#00FF66]/20 dark:bg-[#00FF66]/10 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.4)]">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-black uppercase text-emerald-900 dark:text-[#00FF66]">
              {isAr ? "صافي سيولة الداخليين" : "Net Insider Flow"}
            </span>
            <TrendingUp className="w-4 h-4 text-emerald-700 dark:text-[#00FF66]" />
          </div>
          <div className="text-xl sm:text-2xl font-black text-emerald-800 dark:text-[#00FF66] truncate">
            {activeAnalytics
              ? `${activeAnalytics.flowDistribution.net_value_egp >= 0 ? "+" : ""}${formatEgp(activeAnalytics.flowDistribution.net_value_egp)}`
              : `${initialStats.buys} شراء`}
          </div>
          <span className="text-[11px] font-bold text-emerald-800/80 dark:text-emerald-300/80">
            {activeAnalytics.flowDistribution.net_value_egp >= 0
              ? isAr ? "شراء تجميعي يفوق التخارج" : "Accumulation exceeds exits"
              : isAr ? "تخارج يفوق الشراء" : "Selling exceeds buys"}
          </span>
        </div>

        {/* KPI 3: Stocks Trading Below Insider Cost */}
        <div className="p-4 border-4 border-black dark:border-white bg-amber-400/25 dark:bg-amber-400/15 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.4)]">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-black uppercase text-amber-950 dark:text-amber-300">
              {isAr ? "أقل من تكلفة الداخلي" : "Below Insider Cost"}
            </span>
            <Target className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          </div>
          <div className="text-2xl sm:text-3xl font-black text-amber-950 dark:text-amber-300">
            {activeAnalytics ? activeAnalytics.costDiscountTop.length : 0}
          </div>
          <span className="text-[11px] font-bold text-amber-900/80 dark:text-amber-300/80">
            {isAr ? "فرص شراء بأقل من سعر صانعه" : "Discounted vs insider entry"}
          </span>
        </div>

        {/* KPI 4: Major Shareholders Structures */}
        <div className="p-4 border-4 border-black dark:border-white bg-[#FFE600]/35 dark:bg-[#FFE600]/15 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.4)]">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-black uppercase text-black dark:text-[#FFE600]">
              {isAr ? "هياكل كبار المساهمين" : "Major Shareholders"}
            </span>
            <Users className="w-4 h-4 text-black dark:text-[#FFE600]" />
          </div>
          <div className="text-2xl sm:text-3xl font-black text-black dark:text-[#FFE600]">
            {activeAnalytics ? activeAnalytics.majorShareholders.length : initialStats.shareholding}
          </div>
          <span className="text-[11px] font-bold text-zinc-700 dark:text-zinc-300">
            {isAr ? "نماذج المادة 30 والتداول الحر" : "Article 30 & Free Float"}
          </span>
        </div>
      </div>

      {/* Timeframe & Sector Filter Command Bar */}
      <div className="mb-8 p-4 sm:p-5 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)] space-y-4 text-black dark:text-white">
        {/* Row 1: Timeframe Period Selector */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-amber-500 shrink-0" />
            <span className="text-xs font-black uppercase tracking-wider">
              {isAr ? "المدة الزمنية للإفصاحات:" : "Timeframe Period:"}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {[
              { id: "all", ar: "كامل السجل (الكل)", en: "All Time" },
              { id: "today", ar: "جلسة اليوم / الأحدث", en: "Today / Latest" },
              { id: "7d", ar: "آخر 7 أيام", en: "Last 7 Days" },
              { id: "30d", ar: "آخر 30 يوماً", en: "Last 30 Days" },
              { id: "90d", ar: "آخر 90 يوماً", en: "Last 90 Days" },
            ].map((tf) => (
              <button
                key={tf.id}
                type="button"
                onClick={() => setSelectedTimeframe(tf.id as TimeframePeriod)}
                className={`px-3 py-1.5 text-xs font-black border-2 border-black transition-all cursor-pointer ${
                  selectedTimeframe === tf.id
                    ? "bg-[#FFE600] text-black shadow-[2px_2px_0px_#000]"
                    : "bg-white text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                }`}
              >
                {isAr ? tf.ar : tf.en}
              </button>
            ))}
          </div>
        </div>

        {/* Row 2: Sector Selector */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pt-3 border-t-2 border-black/10 dark:border-white/10">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
            <span className="text-xs font-black uppercase tracking-wider">
              {isAr ? "فلتر القطاعات الاقتصادية:" : "Economic Sector:"}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {EGX_SECTORS.map((sec) => (
              <button
                key={sec.id}
                type="button"
                onClick={() => setSelectedSector(sec.id)}
                className={`px-2.5 py-1 text-[11px] font-black border-2 border-black transition-all cursor-pointer whitespace-nowrap ${
                  selectedSector === sec.id
                    ? "bg-black text-white dark:bg-white dark:text-black shadow-[2px_2px_0px_#00FF66]"
                    : "bg-white text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 hover:bg-[#FFE600] hover:text-black"
                }`}
              >
                {isAr ? sec.label_ar : sec.label_en}
              </button>
            ))}
          </div>
        </div>

        {/* Row 3: Active Range & Verified Status Strip */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t-2 border-black/10 dark:border-white/10 text-xs font-bold text-zinc-600 dark:text-zinc-300">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-black dark:text-white font-black">
              {isAr ? "نطاق الإفصاحات النشط:" : "Active Period Range:"}
            </span>
            {timeframeDateRange ? (
              <span className="font-mono bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 border border-black dark:border-white/20 text-black dark:text-white">
                {isAr
                  ? `من ${timeframeDateRange.from} إلى ${timeframeDateRange.to} (${timeframeDateRange.count} إفصاح)`
                  : `${timeframeDateRange.from} to ${timeframeDateRange.to} (${timeframeDateRange.count} filings)`}
              </span>
            ) : (
              <span>{isAr ? "كامل السجل التاريخي" : "All Available History"}</span>
            )}
            {selectedSector !== "all" && (
              <span className="bg-[#00FF66] text-black px-2 py-0.5 border border-black font-black text-[10px]">
                {isAr
                  ? `قطاع: ${EGX_SECTORS.find((s) => s.id === selectedSector)?.label_ar}`
                  : `Sector: ${selectedSector}`}
              </span>
            )}
          </div>

          {(selectedTimeframe !== "all" || selectedSector !== "all" || smartFilter !== "all" || search) && (
            <button
              type="button"
              onClick={() => {
                setSelectedTimeframe("all");
                setSelectedSector("all");
                setSmartFilter("all");
                setSearch("");
              }}
              className="px-2.5 py-1 bg-black text-white dark:bg-white dark:text-black font-black text-[10px] uppercase hover:bg-[#FF3366] hover:text-white transition-colors cursor-pointer"
            >
              {isAr ? "إعادة ضبط الفلاتر ↺" : "Reset Filters ↺"}
            </button>
          )}
        </div>
      </div>

      {/* Main Subtabs Navigation */}
      <div className="flex border-4 border-black dark:border-white mb-8 bg-zinc-100 dark:bg-zinc-900 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.4)]">
        <button
          type="button"
          onClick={() => setActiveTab("insider_radar")}
          className={`flex-1 py-3.5 px-4 text-xs sm:text-sm font-black uppercase tracking-wider flex items-center justify-center gap-2 transition-all cursor-pointer ${
            activeTab === "insider_radar"
              ? "bg-[#FFE600] text-black shadow-inner"
              : "bg-white text-black dark:bg-zinc-950 dark:text-white hover:bg-zinc-100 dark:hover:bg-zinc-800"
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>{isAr ? "⚡ رادار الداخليين والسيولة اللحظية (Heatmap)" : "⚡ Insider Trading Radar & Heatmap"}</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("major_shareholders")}
          className={`flex-1 py-3.5 px-4 text-xs sm:text-sm font-black uppercase tracking-wider flex items-center justify-center gap-2 border-r-4 sm:border-r-4 border-black dark:border-white transition-all cursor-pointer ${
            activeTab === "major_shareholders"
              ? "bg-[#FFE600] text-black shadow-inner"
              : "bg-white text-black dark:bg-zinc-950 dark:text-white hover:bg-zinc-100 dark:hover:bg-zinc-800"
          }`}
        >
          <Users className="w-4 h-4" />
          <span>{isAr ? "👥 كبار المساهمين والمؤسسين (المادة 30)" : "👥 Major Shareholders & Ownership (Art. 30)"}</span>
        </button>
      </div>

      {/* TAB 1: Insider Trading Radar & Smart Money Flow */}
      {activeTab === "insider_radar" && (
        <>
          {/* Smart Money Liquidity Heatmap */}
          {activeAnalytics && (
            <div className="mb-6">
              <InsiderHeatmap
                items={activeAnalytics.heatmapItems}
                isAr={isAr}
                onSelectSymbol={(sym) => setModalSymbol(sym)}
                selectedSymbol={modalSymbol || search.trim().toUpperCase()}
              />
            </div>
          )}

          {/* Simple Analytical Charts */}
          {activeAnalytics && (
            <InsiderCharts
              costDiscounts={activeAnalytics.costDiscountTop}
              flowDistribution={activeAnalytics.flowDistribution}
              isAr={isAr}
              onSelectSymbol={(sym) => setModalSymbol(sym)}
            />
          )}

          {/* Controls Bar: Search + Type Filters + Sentiment + Smart Filter */}
          <div className="space-y-3 mb-8">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
              {/* Search Input */}
              <div className="lg:col-span-4 relative flex items-center">
                <Search className="absolute left-3.5 w-4 h-4 text-black/70 dark:text-white/70 pointer-events-none" />
                <input
                  type="text"
                  placeholder={
                    isAr
                      ? "ابحث برمز السهم (COMI, FWRY, PRMH) أو اسم الشركة أو الطرف..."
                      : "Search symbol (COMI, FWRY, PRMH) or party..."
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

            {/* Smart Filter Chips Bar */}
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-black/15 dark:border-white/15">
              <span className="text-xs font-black text-black dark:text-white flex items-center gap-1">
                <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                <span>{isAr ? "المؤشرات الذكية:" : "Smart Signals:"}</span>
              </span>

              <button
                type="button"
                onClick={() => setSmartFilter("all")}
                className={`px-2.5 py-1 text-xs font-black border-2 border-black transition-all ${
                  smartFilter === "all"
                    ? "bg-[#FFE600] text-black shadow-[2px_2px_0px_#000]"
                    : "bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100"
                }`}
              >
                {isAr ? "جميع الإفصاحات" : "All Disclosures"}
              </button>

              <button
                type="button"
                onClick={() => setSmartFilter("below_cost")}
                className={`px-2.5 py-1 text-xs font-black border-2 border-black transition-all flex items-center gap-1 ${
                  smartFilter === "below_cost"
                    ? "bg-amber-400 text-black shadow-[2px_2px_0px_#000]"
                    : "bg-white dark:bg-zinc-900 text-amber-600 dark:text-amber-400 hover:bg-amber-50"
                }`}
              >
                <Target className="w-3.5 h-3.5" />
                <span>{isAr ? "💎 أسهم تتداول بأقل من تكلفة الداخلي" : "💎 Trading Below Insider Cost"}</span>
              </button>

              <button
                type="button"
                onClick={() => setSmartFilter("accumulating")}
                className={`px-2.5 py-1 text-xs font-black border-2 border-black transition-all flex items-center gap-1 ${
                  smartFilter === "accumulating"
                    ? "bg-emerald-500 text-black shadow-[2px_2px_0px_#000]"
                    : "bg-white dark:bg-zinc-900 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50"
                }`}
              >
                <TrendingUp className="w-3.5 h-3.5" />
                <span>{isAr ? "🟢 أسهم تشهد تجميعاً صامتاً" : "🟢 Accumulating Stocks"}</span>
              </button>

              <button
                type="button"
                onClick={() => setSmartFilter("distributing")}
                className={`px-2.5 py-1 text-xs font-black border-2 border-black transition-all flex items-center gap-1 ${
                  smartFilter === "distributing"
                    ? "bg-rose-500 text-white shadow-[2px_2px_0px_#000]"
                    : "bg-white dark:bg-zinc-900 text-rose-600 dark:text-rose-400 hover:bg-rose-50"
                }`}
              >
                <TrendingDown className="w-3.5 h-3.5" />
                <span>{isAr ? "🔴 أسهم تشهد تصريفاً" : "🔴 Distributing Stocks"}</span>
              </button>
            </div>
          </div>

          {/* Status Bar with View Mode Toggle */}
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5 px-3 py-2 border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900 text-xs font-black text-black dark:text-white">
            <span>
              {isAr
                ? `المعروض حالياً: ${displayedDisclosures.length} من أصل ${totalCount} إفصاح (تحميل ذكي تدريجي)`
                : `Showing ${displayedDisclosures.length} of ${totalCount} disclosures`}
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

              {(search || selectedType !== "all" || selectedSentiment !== "all" || smartFilter !== "all") && (
                <button
                  type="button"
                  onClick={() => {
                    setSearch("");
                    setSelectedType("all");
                    setSelectedSentiment("all");
                    setSmartFilter("all");
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
          ) : displayedDisclosures.length === 0 ? (
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
                  {displayedDisclosures.map((item) => {
                    const shortCode = item.id.slice(0, 8).toUpperCase();
                    const symUpper = item.symbol ? item.symbol.toUpperCase() : null;
                    const metric = symUpper && activeAnalytics ? activeAnalytics.symbolMetrics[symUpper] : null;

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
                                <button
                                  type="button"
                                  onClick={() => setModalSymbol(item.symbol!)}
                                  className="px-2 py-0.5 text-xs font-black uppercase tracking-wider bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white hover:bg-[#FFE600] hover:text-black transition-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] cursor-pointer"
                                  title={isAr ? "تحليل شامل لهذا السهم" : "Stock Deep-Dive"}
                                >
                                  {item.symbol}
                                </button>
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
                            <button
                              type="button"
                              onClick={() => item.symbol && setModalSymbol(item.symbol)}
                              className="font-black text-black dark:text-white truncate max-w-[170px] text-right hover:text-amber-500 transition-colors cursor-pointer"
                              title={item.company_name}
                            >
                              {item.company_name}
                            </button>
                            <span className="flex items-center gap-1 shrink-0 text-[11px] font-black">
                              <Calendar className="w-3 h-3" />
                              {item.disclosure_date}
                            </span>
                          </div>

                          <div className="flex items-center justify-between gap-2">
                            <span className="inline-block px-2 py-0.5 text-[10px] font-black bg-zinc-100 dark:bg-zinc-800 text-black dark:text-white border border-black dark:border-white">
                              {getTypeLabel(item.disclosure_type)}
                            </span>

                            {item.symbol && (
                              <button
                                type="button"
                                onClick={() => setModalSymbol(item.symbol!)}
                                className="text-[10px] font-black text-emerald-700 dark:text-[#00FF66] hover:text-black dark:hover:text-[#FFE600] underline flex items-center gap-1 cursor-pointer"
                              >
                                <Target className="w-3 h-3" />
                                <span>{isAr ? "تحليل شامل بالسهم 🔍" : "Deep-Dive 🔍"}</span>
                              </button>
                            )}
                          </div>

                          {/* Title */}
                          <h2 className="text-sm font-black text-black dark:text-white line-clamp-2 leading-snug">
                            {item.title}
                          </h2>

                          {/* Insider Cost (VWAP) & Discount Badge */}
                          {metric && metric.insider_vwap > 0 && (
                            <div className="p-2.5 rounded-none border-2 border-black dark:border-white bg-[#FFE600]/20 dark:bg-[#FFE600]/10 flex items-center justify-between text-xs">
                              <div className="flex items-center gap-1.5">
                                <Target className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                                <div>
                                  <span className="text-[10px] text-zinc-500 dark:text-zinc-400 block">
                                    {isAr ? "متوسط تكلفة الداخلي:" : "Insider VWAP:"}
                                  </span>
                                  <span className="font-mono font-black text-black dark:text-white">
                                    {metric.insider_vwap.toFixed(2)} ج.م
                                  </span>
                                </div>
                              </div>

                              <div className="text-right">
                                {metric.discount_pct < -1.0 ? (
                                  <span className="px-2 py-0.5 rounded border border-emerald-500 bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 font-black text-[10px]">
                                    {isAr ? `خصم -${Math.abs(metric.discount_pct)}% 🟢` : `-${Math.abs(metric.discount_pct)}% Discount`}
                                  </span>
                                ) : (
                                  <span className="text-[10px] font-mono text-zinc-600 dark:text-zinc-400">
                                    {isAr ? `سعر اليوم: ${metric.current_price.toFixed(2)} ج` : `${metric.current_price.toFixed(2)} EGP`}
                                  </span>
                                )}
                              </div>
                            </div>
                          )}

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
                                {isAr ? "تكبير" : "Full View"}
                              </button>
                            </div>
                            <iframe
                              src={`/api/disclosures/pdf/${item.id}#view=FitH&toolbar=0&navpanes=0`}
                              title={item.title}
                              loading="lazy"
                              className="w-full h-[220px] border-0 bg-white"
                            />
                          </div>
                        </div>

                        {/* Bottom Actions */}
                        <div className="flex items-center justify-between gap-2 pt-3 mt-3 border-t-2 border-black/15 dark:border-white/15 text-xs">
                          <button
                            type="button"
                            onClick={() => handleDiscussInFloatingChat(item)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#00FF66] text-black border-2 border-black font-black text-[11px] shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:bg-[#FFE600] cursor-pointer"
                          >
                            <Bot className="w-3.5 h-3.5" />
                            <span>{isAr ? "ناقش في الشات" : "Discuss"}</span>
                          </button>

                          {item.source_url && (
                            <a
                              href={item.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-[11px] font-black text-zinc-600 dark:text-zinc-400 hover:text-black dark:hover:text-white"
                            >
                              <ExternalLink className="w-3 h-3" />
                              <span>{isAr ? "المصدر" : "Source"}</span>
                            </a>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                /* List View (Horizontal) */
                <div className="space-y-4">
                  {displayedDisclosures.map((item) => {
                    const shortCode = item.id.slice(0, 8).toUpperCase();
                    const symUpper = item.symbol ? item.symbol.toUpperCase() : null;
                    const metric = symUpper && activeAnalytics ? activeAnalytics.symbolMetrics[symUpper] : null;

                    return (
                      <article
                        key={item.id}
                        className="p-5 border-4 border-black dark:border-white bg-white dark:bg-zinc-900 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.4)] transition-all"
                      >
                        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                          {/* Column 1: Info & AI Summary (7 cols) */}
                          <div className="lg:col-span-7 flex flex-col justify-between space-y-3">
                            <div>
                              {/* Header row */}
                              <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b-2 border-black/15 dark:border-white/15 mb-2">
                                <div className="flex items-center gap-2">
                                  <StockLogo
                                    symbol={item.symbol || "EGX"}
                                    size="sm"
                                    className="border-2 border-black dark:border-white rounded-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
                                  />
                                  {item.symbol ? (
                                    <button
                                      type="button"
                                      onClick={() => setModalSymbol(item.symbol!)}
                                      className="px-2.5 py-0.5 text-xs font-black uppercase tracking-wider bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white hover:bg-[#FFE600] hover:text-black transition-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] cursor-pointer"
                                      title={isAr ? "اضغط لفتح بطاقة التحليل الشامل للسهم" : "Click to open stock deep-dive"}
                                    >
                                      {item.symbol}
                                    </button>
                                  ) : (
                                    <span className="px-2 py-0.5 text-xs font-black uppercase bg-zinc-200 dark:bg-zinc-800 text-black dark:text-white border-2 border-black">
                                      EGX
                                    </span>
                                  )}
                                  <span className="font-black text-black dark:text-white text-xs">
                                    {item.company_name}
                                  </span>
                                  <span className="text-xs font-mono font-bold text-zinc-500">
                                    #{shortCode}
                                  </span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-xs font-black text-zinc-500 flex items-center gap-1">
                                    <Calendar className="w-3.5 h-3.5" />
                                    {item.disclosure_date}
                                  </span>
                                  {getSentimentBadge(item)}
                                </div>
                              </div>

                              {/* Title */}
                              <h2 className="text-base font-black text-black dark:text-white leading-snug mb-2">
                                {item.title}
                              </h2>

                              {/* Insider Cost and VWAP bar */}
                              {metric && metric.insider_vwap > 0 && (
                                <div className="p-3 mb-2 border-2 border-black dark:border-white bg-[#FFE600]/20 dark:bg-[#FFE600]/10 flex flex-wrap items-center justify-between gap-2 text-xs">
                                  <div className="flex items-center gap-2">
                                    <Target className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                                    <span className="font-bold text-zinc-700 dark:text-zinc-300">
                                      {isAr ? "متوسط تكلفة شراء الداخليين:" : "Insider VWAP Cost:"}
                                    </span>
                                    <span className="font-mono font-black text-sm text-black dark:text-white">
                                      {metric.insider_vwap.toFixed(2)} ج.م
                                    </span>
                                  </div>

                                  <div className="flex items-center gap-2">
                                    {metric.discount_pct < -1.0 ? (
                                      <span className="px-2.5 py-0.5 rounded border border-emerald-500 bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 font-black text-xs">
                                        {isAr ? `فرصة: يتداول بأقل من التكلفة بـ -${Math.abs(metric.discount_pct)}% 🟢` : `-${Math.abs(metric.discount_pct)}% Discount`}
                                      </span>
                                    ) : (
                                      <span className="text-xs font-mono text-zinc-600 dark:text-zinc-400">
                                        {isAr ? `السعر الحالي: ${metric.current_price.toFixed(2)} ج.م` : `Price: ${metric.current_price.toFixed(2)} EGP`}
                                      </span>
                                    )}

                                    <span className="text-[11px] font-bold text-zinc-500">
                                      ({metric.buy_count} {isAr ? "عمليات تجميع" : "buys"})
                                    </span>
                                  </div>
                                </div>
                              )}

                              {/* Quant details */}
                              {(item.party_name || item.shares_count || item.stake_before != null || item.stake_after != null) && (
                                <div className="flex flex-wrap items-center gap-2 p-2.5 mb-2 bg-zinc-100 dark:bg-zinc-950 border-2 border-black dark:border-zinc-700 text-xs font-bold text-black dark:text-white">
                                  {item.party_name && (
                                    <span>
                                      {isAr ? "الطرف: " : "Party: "}
                                      <strong className="font-black text-emerald-700 dark:text-emerald-400">
                                        {item.party_name}
                                      </strong>
                                    </span>
                                  )}
                                  {item.shares_count != null && (
                                    <span className="px-2 py-0.5 bg-[#FFE600] text-black font-black text-xs border border-black">
                                      {isAr ? "الكمية:" : "Shares:"} {Number(item.shares_count).toLocaleString()} {isAr ? "سهم" : "sh"}
                                    </span>
                                  )}
                                  {(item.stake_before != null || item.stake_after != null) && (
                                    <span className="font-black text-xs">
                                      {isAr ? "نسبة المساهمة:" : "Stake:"} {item.stake_before ?? "—"}% → {item.stake_after ?? "—"}%
                                    </span>
                                  )}
                                </div>
                              )}

                              {/* AI Analysis */}
                              <div className="p-3 bg-yellow-50 dark:bg-yellow-950/25 border-2 border-dashed border-yellow-600 dark:border-yellow-500/60">
                                <div className="flex items-center gap-1.5 mb-1">
                                  <Sparkles className="w-4 h-4 text-yellow-600 dark:text-yellow-400 shrink-0" />
                                  <span className="text-xs font-black uppercase text-yellow-800 dark:text-yellow-400">
                                    {isAr ? "تحليل الذكاء الاصطناعي والأثر المالي:" : "AI Financial Analysis & Impact:"}
                                  </span>
                                </div>
                                <p className="text-xs font-bold text-zinc-800 dark:text-zinc-200 leading-relaxed">
                                  {item.ai_summary}
                                </p>
                              </div>
                            </div>

                            {/* Action Buttons */}
                            <div className="flex flex-wrap items-center gap-2 pt-3 border-t-2 border-black/15 dark:border-white/15">
                              <button
                                type="button"
                                onClick={() => handleDiscussInFloatingChat(item)}
                                className="inline-flex items-center gap-1.5 px-4 py-2 bg-[#00FF66] text-black border-2 border-black font-black text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:bg-[#FFE600] cursor-pointer"
                              >
                                <Bot className="w-4 h-4" />
                                <span>{isAr ? "ناقش هذا الإفصاح في الشات" : "Discuss in Chat"}</span>
                              </button>

                              {item.symbol && (
                                <button
                                  type="button"
                                  onClick={() => handleInspectShareholders(item.symbol!)}
                                  className="inline-flex items-center gap-1 px-3 py-2 bg-zinc-100 dark:bg-zinc-800 text-black dark:text-white border-2 border-black dark:border-white font-black text-xs hover:bg-[#FFE600] hover:text-black transition-all cursor-pointer"
                                >
                                  <Users className="w-3.5 h-3.5" />
                                  <span>{isAr ? "فحص هيكل المساهمين" : "Shareholders Registry"}</span>
                                </button>
                              )}

                              {item.symbol && (
                                <button
                                  type="button"
                                  onClick={() => setModalSymbol(item.symbol!)}
                                  className="inline-flex items-center gap-1.5 px-3 py-2 bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white font-black text-xs hover:bg-[#FFE600] hover:text-black transition-all cursor-pointer shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
                                >
                                  <Target className="w-3.5 h-3.5" />
                                  <span>{isAr ? `تحليل شامل لسهم ${item.symbol} 🔍` : `Deep-Dive ${item.symbol} 🔍`}</span>
                                </button>
                              )}

                              {item.source_url && (
                                <a
                                  href={item.source_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-xs font-black text-zinc-600 dark:text-zinc-400 hover:text-black dark:hover:text-white ms-auto"
                                >
                                  <ExternalLink className="w-3.5 h-3.5" />
                                  <span>{isAr ? "المصدر الأصلي" : "Original Source"}</span>
                                </a>
                              )}
                            </div>
                          </div>

                          {/* Column 2: Authentic PDF Viewer (5 cols) */}
                          <div className="lg:col-span-5 flex flex-col justify-between border-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-950 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] overflow-hidden">
                            <div className="flex items-center justify-between px-3 py-2 bg-black text-white text-xs font-black border-b-2 border-black">
                              <span className="flex items-center gap-1.5 text-[#FFE600]">
                                <FileText className="w-4 h-4" />
                                {isAr ? "مستند الإفصاح الرسمي (PDF معتمد)" : "Official Disclosure Document (PDF)"}
                              </span>
                              <button
                                type="button"
                                onClick={() => {
                                  setPreviewItem(item);
                                  setPreviewMode("pdf");
                                }}
                                className="text-black bg-[#FFE600] px-2 py-0.5 hover:bg-white flex items-center gap-1 font-black text-[10px] cursor-pointer"
                              >
                                <ZoomIn className="w-3 h-3" />
                                {isAr ? "تكبير" : "Full View"}
                              </button>
                            </div>

                            <iframe
                              src={`/api/disclosures/pdf/${item.id}#view=FitH&toolbar=0&navpanes=0`}
                              title={item.title}
                              loading="lazy"
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
                      </article>
                    );
                  })}
                </div>
              )}

              {/* Progressive Load More Trigger & Button */}
              <div ref={loadMoreTriggerRef} className="pt-6 flex flex-col items-center justify-center">
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
                      ? `تم عرض جميع الإفصاحات المطابقة (${displayedDisclosures.length})`
                      : `All matching disclosures loaded (${displayedDisclosures.length})`}
                  </span>
                )}
              </div>
            </>
          )}
        </>
      )}

      {/* TAB 2: Major Shareholders & Founders (Article 30 Registry) */}
      {activeTab === "major_shareholders" && (
        <MajorShareholdersTab
          companies={activeAnalytics?.majorShareholders?.length ? activeAnalytics.majorShareholders : (initialAnalytics?.majorShareholders || [])}
          isAr={isAr}
          onSelectSymbol={(sym) => setModalSymbol(sym)}
        />
      )}

      {/* Comprehensive Disclosures & Financial Terminology Glossary */}
      <DisclosuresGlossary isAr={isAr} />

      {/* Legal & Regulatory Comprehensive Disclaimer Footer */}
      <footer className="mt-8 p-5 rounded-2xl border-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-950 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.4)] text-xs text-zinc-700 dark:text-zinc-300 leading-relaxed">
        <div className="flex items-center gap-2 mb-2 font-black text-black dark:text-white text-sm">
          <Scale className="w-4 h-4 text-amber-500" />
          <span>{isAr ? "تنويه وإخلاء مسؤولية قانونية وتنظيمية (EGX & FRA Compliance):" : "Regulatory & Legal Disclaimer:"}</span>
        </div>
        <p>
          {isAr
            ? "جميع الإفصاحات ونماذج المادة (30) وتعاملات الداخليين المعروضة في هذه الصفحة مستقاة حصرياً من البيانات الرسمية المعلنة والمتاحة للجمهور الصادرة عن البورصة المصرية (EGX) والهيئة العامة للرقابة المالية (FRA) إعمالاً لمبدأ الشفافية وحرية تداول المعلومات المالية. مؤشرات 'متوسط تكلفة الداخليين (Insider VWAP)'، و'صافي السيولة'، و'الخريطة الحرارية' هي معالجات إحصائية رياضية لأغراض التحليل والدراسة والمتابعة الاستثمارية، ولا تمثل توصية بالبيع أو الشراء أو تتبعاً خاصاً للحياة الشخصية للأفراد، ولا تتحمل المنصة أي مسؤولية قانونية عن أي قرارات استثمارية تُتخذ بناءً على هذه البيانات."
            : "All disclosures, Article 30 filings, and insider transactions displayed on this page are compiled exclusively from official public disclosures issued by the Egyptian Exchange (EGX) and the Financial Regulatory Authority (FRA). 'Insider VWAP', 'Net Flow', and 'Liquidity Heatmap' are purely statistical algorithms for educational and research purposes and do not constitute financial advice or personal tracking."}
        </p>
      </footer>

      {/* Full-Screen PDF Document Viewer Lightbox Modal */}
      {previewItem && (
        <div
          className="fixed inset-0 z-[1100] bg-black/85 backdrop-blur-sm flex items-center justify-center p-2 sm:p-5"
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
      {/* Stock Deep-Dive Modal Dialog */}
      <StockDetailModal
        symbol={modalSymbol}
        isOpen={Boolean(modalSymbol)}
        onClose={() => setModalSymbol(null)}
        metric={modalSymbol ? activeAnalytics.symbolMetrics[modalSymbol] : undefined}
        ownership={
          modalSymbol
            ? (activeAnalytics.majorShareholders.find((s) => s.symbol === modalSymbol) ||
               initialAnalytics?.majorShareholders.find((s) => s.symbol === modalSymbol))
            : undefined
        }
        disclosures={basePool}
        isAr={isAr}
        onOpenPdfModal={(item) => {
          setPreviewItem(item);
          setPreviewMode("pdf");
        }}
        onDiscussInChat={(sym, name) => {
          setModalSymbol(null);
          setIsOpen(true);
          sendMessage(
            `قدم لي تحليلاً استثمارياً شاملاً ومفصلاً لسهم ${name} (${sym})، يتضمن تحليل تعاملات الداخليين وتكلفتهم (VWAP)، هيكل كبار المساهمين بنماذج المادة 30، وفرص التجميع أو التصريف.`
          );
        }}
        onFilterBySymbol={(sym) => {
          setSearch(sym);
          window.scrollTo({ top: 850, behavior: "smooth" });
        }}
      />
    </div>
  );
}
