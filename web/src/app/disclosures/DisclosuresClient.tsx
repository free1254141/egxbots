"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  FileText,
  Search,
  Bot,
  ExternalLink,
  TrendingUp,
  TrendingDown,
  Minus,
  Sparkles,
  Building2,
  Calendar,
  Users,
  ShieldCheck,
  ChevronRight,
  Filter,
  CheckCircle2,
  AlertTriangle
} from "lucide-react";

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

interface DisclosuresClientProps {
  initialDisclosures: DisclosureItem[];
}

export default function DisclosuresClient({ initialDisclosures }: DisclosuresClientProps) {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [selectedType, setSelectedType] = useState<string>("all");
  const [selectedSentiment, setSelectedSentiment] = useState<string>("all");

  // Filter logic
  const filteredDisclosures = useMemo(() => {
    return initialDisclosures.filter((item) => {
      // Search match
      if (search.trim()) {
        const q = search.trim().toLowerCase();
        const matchSym = item.symbol?.toLowerCase().includes(q);
        const matchName = item.company_name?.toLowerCase().includes(q);
        const matchTitle = item.title?.toLowerCase().includes(q);
        const matchParty = item.party_name?.toLowerCase().includes(q);
        if (!matchSym && !matchName && !matchTitle && !matchParty) return false;
      }

      // Type match
      if (selectedType !== "all" && item.disclosure_type !== selectedType) {
        return false;
      }

      // Sentiment match
      if (selectedSentiment !== "all" && item.sentiment !== selectedSentiment) {
        return false;
      }

      return true;
    });
  }, [initialDisclosures, search, selectedType, selectedSentiment]);

  // KPIs
  const stats = useMemo(() => {
    const total = initialDisclosures.length;
    const buys = initialDisclosures.filter(d => d.action_type === "buy" || d.sentiment === "bullish").length;
    const sells = initialDisclosures.filter(d => d.action_type === "sell" || d.sentiment === "bearish").length;
    const shareholding = initialDisclosures.filter(d => d.disclosure_type === "major_shareholders").length;
    return { total, buys, sells, shareholding };
  }, [initialDisclosures]);

  const handleDiscussWithAI = (item: DisclosureItem) => {
    const prompt = `اشرح لي بالتفصيل إفصاح ${item.company_name} (${item.symbol || ""}) الصادر بتاريخ ${item.disclosure_date}: "${item.title}". ما هو معناه للمستثمر وما تأثيره المالي والفني المتوقع على السهم؟`;
    router.push(`/chat?prompt=${encodeURIComponent(prompt)}`);
  };

  const getTypeLabel = (type: string) => {
    switch (type) {
      case "insider_trading":
        return "تعاملات داخليين";
      case "major_shareholders":
        return "هيكل المساهمين (مادة 30)";
      case "board_resolution":
        return "قرارات مجلس الإدارة";
      case "financial_results":
        return "نتائج وقوائم مالية";
      default:
        return "إفصاح جوهري";
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-white pb-20" dir="rtl">
      {/* Hero Banner */}
      <section className="relative overflow-hidden border-b border-zinc-800 bg-gradient-to-b from-zinc-900/60 via-zinc-950 to-zinc-950 pt-12 pb-10 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-bold mb-4">
                <Sparkles className="w-3.5 h-3.5" />
                رادار إفصاحات البورصة المصرية اللحظي • بالذكاء الاصطناعي
              </div>
              <h1 className="text-3xl sm:text-4xl lg:text-5xl font-black tracking-tight text-white mb-3">
                إفصاحات الشركات وتعاملات الداخليين
              </h1>
              <p className="text-sm sm:text-base text-zinc-400 max-w-2xl font-medium">
                رصد يومي مباشر لنماذج المادة 30، تعاملات كبار المساهمين والداخليين، وتجفيف الأسهم الحرة، مع تحليل وشرح فوري للأثر المالي على الأسهم من محرك الذكاء الاصطناعي.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <Link
                href="/chat"
                className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 text-black font-black text-sm shadow-lg shadow-emerald-500/20 hover:scale-105 transition-all"
              >
                <Bot className="w-4 h-4" />
                اسأل المساعد عن أي إفصاح
              </Link>
            </div>
          </div>

          {/* Quick KPIs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 mt-8">
            <div className="p-4 rounded-xl bg-zinc-900/50 border border-zinc-800/80">
              <div className="flex items-center justify-between text-zinc-400 mb-1">
                <span className="text-xs font-bold">إجمالي الإفصاحات</span>
                <FileText className="w-4 h-4 text-blue-400" />
              </div>
              <div className="text-2xl font-black text-white">{stats.total}</div>
              <span className="text-[10px] text-zinc-500 font-medium">محدثة لحظة بلحظة</span>
            </div>

            <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-500/20">
              <div className="flex items-center justify-between text-emerald-400 mb-1">
                <span className="text-xs font-bold">شراء مطلعين وتجميع</span>
                <TrendingUp className="w-4 h-4" />
              </div>
              <div className="text-2xl font-black text-emerald-400">{stats.buys}</div>
              <span className="text-[10px] text-emerald-500/80 font-medium">إشارات إيجابية داعمة</span>
            </div>

            <div className="p-4 rounded-xl bg-red-950/20 border border-red-500/20">
              <div className="flex items-center justify-between text-red-400 mb-1">
                <span className="text-xs font-bold">بيع داخلي وتخارج</span>
                <TrendingDown className="w-4 h-4" />
              </div>
              <div className="text-2xl font-black text-red-400">{stats.sells}</div>
              <span className="text-[10px] text-red-500/80 font-medium">تسييل يستوجب المتابعة</span>
            </div>

            <div className="p-4 rounded-xl bg-purple-950/20 border border-purple-500/20">
              <div className="flex items-center justify-between text-purple-400 mb-1">
                <span className="text-xs font-bold">هياكل المساهمين (مادة 30)</span>
                <Users className="w-4 h-4" />
              </div>
              <div className="text-2xl font-black text-purple-400">{stats.shareholding}</div>
              <span className="text-[10px] text-purple-500/80 font-medium">حصص الملاك والتداول الحر</span>
            </div>
          </div>
        </div>
      </section>

      {/* Control Bar: Search & Filters */}
      <section className="sticky top-[64px] z-30 bg-zinc-950/90 backdrop-blur-md border-b border-zinc-800/80 py-3 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
          {/* Search */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
            <input
              type="text"
              placeholder="ابحث برمز السهم (FWRY, SCCD...) أو اسم الشركة أو المساهم..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pr-10 pl-4 py-2 text-xs sm:text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-emerald-500 transition-colors"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-zinc-500 hover:text-white"
              >
                مسح
              </button>
            )}
          </div>

          {/* Filter Pills */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 md:pb-0 scrollbar-none">
            {/* Type selector */}
            <div className="flex items-center gap-1 bg-zinc-900 p-1 rounded-xl border border-zinc-800 text-xs">
              {[
                { id: "all", label: "كل الأنواع" },
                { id: "insider_trading", label: "تعاملات داخليين" },
                { id: "major_shareholders", label: "هيكل المساهمين" },
                { id: "board_resolution", label: "مجلس الإدارة" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setSelectedType(tab.id)}
                  className={`px-2.5 py-1 rounded-lg font-bold transition-all whitespace-nowrap ${
                    selectedType === tab.id
                      ? "bg-zinc-800 text-white shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Sentiment selector */}
            <div className="flex items-center gap-1 bg-zinc-900 p-1 rounded-xl border border-zinc-800 text-xs">
              {[
                { id: "all", label: "الكل" },
                { id: "bullish", label: "إيجابي 🟢" },
                { id: "bearish", label: "سلبي 🔴" },
                { id: "neutral", label: "محايد ⚪" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setSelectedSentiment(tab.id)}
                  className={`px-2.5 py-1 rounded-lg font-bold transition-all whitespace-nowrap ${
                    selectedSentiment === tab.id
                      ? "bg-zinc-800 text-white shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Disclosures Feed */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8">
        <div className="flex items-center justify-between mb-4 text-xs text-zinc-400">
          <span>
            عرض <strong className="text-white font-bold">{filteredDisclosures.length}</strong> من أصل {initialDisclosures.length} إفصاح
          </span>
          {(search || selectedType !== "all" || selectedSentiment !== "all") && (
            <button
              onClick={() => { setSearch(""); setSelectedType("all"); setSelectedSentiment("all"); }}
              className="text-emerald-400 hover:underline"
            >
              إعادة ضبط الفلاتر
            </button>
          )}
        </div>

        {filteredDisclosures.length === 0 ? (
          <div className="text-center py-20 bg-zinc-900/30 rounded-2xl border border-zinc-800">
            <AlertTriangle className="w-10 h-10 text-zinc-600 mx-auto mb-3" />
            <h3 className="text-base font-bold text-white mb-1">لم يتم العثور على إفصاحات مطابقة</h3>
            <p className="text-xs text-zinc-500">جرب تغيير كلمات البحث أو إزالة الفلاتر المحددة.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredDisclosures.map((item) => {
              const isBullish = item.sentiment === "bullish" || item.action_type === "buy";
              const isBearish = item.sentiment === "bearish" || item.action_type === "sell";

              return (
                <div
                  key={item.id}
                  className={`group relative rounded-2xl p-5 bg-zinc-900/40 border transition-all hover:bg-zinc-900/70 hover:shadow-xl ${
                    isBullish
                      ? "border-emerald-500/20 hover:border-emerald-500/40"
                      : isBearish
                      ? "border-red-500/20 hover:border-red-500/40"
                      : "border-zinc-800 hover:border-zinc-700"
                  }`}
                >
                  {/* Top Row: Symbol + Type + Date */}
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2 min-w-0">
                      {item.symbol ? (
                        <Link
                          href={`/stocks/${item.symbol.toLowerCase()}`}
                          className="px-2.5 py-1 rounded-lg bg-zinc-800 text-emerald-400 hover:bg-emerald-500 hover:text-black font-black text-xs transition-colors shrink-0"
                          title="عرض صفحة السهم"
                        >
                          {item.symbol}
                        </Link>
                      ) : (
                        <span className="px-2.5 py-1 rounded-lg bg-zinc-800 text-zinc-400 font-black text-xs shrink-0">
                          سوق EGX
                        </span>
                      )}
                      <span className="text-xs font-bold text-zinc-200 truncate">
                        {item.company_name}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span className="inline-flex items-center gap-1 text-[10px] text-zinc-400 font-mono">
                        <Calendar className="w-3 h-3 text-zinc-500" />
                        {item.disclosure_date}
                      </span>
                      <span
                        className={`text-[10px] font-black px-2 py-0.5 rounded-full ${
                          isBullish
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                            : isBearish
                            ? "bg-red-500/10 text-red-400 border border-red-500/20"
                            : "bg-zinc-800 text-zinc-300"
                        }`}
                      >
                        {getTypeLabel(item.disclosure_type)}
                      </span>
                    </div>
                  </div>

                  {/* Title */}
                  <h3 className="text-sm font-bold text-white mb-2 leading-relaxed">
                    {item.title}
                  </h3>

                  {/* Transaction details if present */}
                  {(item.shares_count || item.party_name) && (
                    <div className="flex flex-wrap items-center gap-2 mb-3 text-xs text-zinc-300 bg-zinc-950/60 p-2.5 rounded-xl border border-zinc-800/60">
                      {item.party_name && (
                        <span className="font-semibold text-zinc-400">
                          الطرف: <strong className="text-white">{item.party_name}</strong>
                        </span>
                      )}
                      {item.shares_count && (
                        <span className="font-semibold text-zinc-400">
                          الكمية: <strong className="text-emerald-400 font-mono">{item.shares_count.toLocaleString()} سهم</strong>
                        </span>
                      )}
                      {item.action_type && (
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          item.action_type === 'buy' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'
                        }`}>
                          {item.action_type === 'buy' ? 'شراء' : 'بيع'}
                        </span>
                      )}
                    </div>
                  )}

                  {/* AI Analysis Box */}
                  <div className="rounded-xl p-3.5 bg-zinc-950 border border-zinc-800/90 mb-4">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-zinc-300 mb-1.5">
                      <Bot className="w-3.5 h-3.5 text-emerald-400" />
                      <span>تحليل الذكاء الاصطناعي والأثر المالي:</span>
                    </div>
                    <p className="text-xs text-zinc-300 leading-relaxed font-normal">
                      {item.ai_summary}
                    </p>

                    {item.metadata?.key_takeaway && (
                      <div className="mt-2.5 pt-2 border-t border-zinc-900 flex items-center gap-1.5 text-[11px] text-emerald-400 font-bold">
                        <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                        <span>الخلاصة: {item.metadata.key_takeaway}</span>
                      </div>
                    )}
                  </div>

                  {/* Actions Bar */}
                  <div className="flex items-center justify-between gap-2 pt-2 border-t border-zinc-800/50">
                    <button
                      onClick={() => handleDiscussWithAI(item)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500 hover:text-black text-emerald-400 font-bold text-xs transition-all"
                    >
                      <Bot className="w-3.5 h-3.5" />
                      ناقش هذا الإفصاح في الشات
                    </button>

                    <div className="flex items-center gap-2">
                      {item.symbol && (
                        <Link
                          href={`/stocks/${item.symbol.toLowerCase()}`}
                          className="text-xs text-zinc-400 hover:text-white font-medium inline-flex items-center gap-1"
                        >
                          تحليل السهم
                          <ChevronRight className="w-3 h-3 rotate-180" />
                        </Link>
                      )}

                      {item.source_url && (
                        <a
                          href={item.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1.5 rounded-lg text-zinc-500 hover:text-white hover:bg-zinc-800 transition-colors"
                          title="المستند الأصلي / الإفصاح"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
