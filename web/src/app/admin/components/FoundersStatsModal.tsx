"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Calendar,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  Crown,
  ExternalLink,
  Loader2,
  RefreshCw,
  Search,
  Send,
  Smartphone,
  TrendingUp,
  X,
} from "lucide-react";
import { toast } from "sonner";
import {
  buildWhatsAppUrl,
  formatCairoDateTime,
  getPaidCohortMeta,
  type FounderAnalyticsRow,
  type FounderCohort,
  type FoundersRetentionSummary,
} from "@/lib/admin/founders-analytics";
import FounderUserUsageDialog from "./FounderUserUsageDialog";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onFilterUser?: (email: string) => void;
  isAr?: boolean;
}

type FilterMode = "all" | "active" | "renewed" | "expired" | "urgent";
type CohortFilter = "ALL" | "FOUNDERS" | "NON_FOUNDERS" | FounderCohort;

function summarizeScopedMetrics(rows: FounderAnalyticsRow[]) {
  const total = rows.length;
  const active = rows.filter((r) => r.is_active).length;
  const renewed = rows.filter((r) => r.status === "renewed_active").length;
  const firstTerm = rows.filter((r) => r.status === "active_first_term").length;
  const expired = rows.filter((r) => !r.is_active).length;
  const inGrace = rows.filter((r) => r.status === "in_grace_72h").length;
  const matured = renewed + expired;
  const dueSoon = rows.filter(
    (r) => r.is_active && !r.is_lifetime && r.hours_until_expiry !== null && r.hours_until_expiry > 0 && r.hours_until_expiry <= 72
  ).length;
  const revenue = Math.round(rows.reduce((sum, r) => sum + (r.total_paid_egp || 0), 0) * 100) / 100;
  return {
    total,
    active,
    renewed,
    firstTerm,
    expired,
    inGrace,
    matured,
    dueSoon,
    urgent: dueSoon + inGrace,
    revenue,
    overallRate: total > 0 ? Math.round((active / total) * 1000) / 10 : 0,
    maturedRate: matured > 0 ? Math.round((renewed / matured) * 1000) / 10 : 0,
  };
}

function formatExpiryCountdown(row: FounderAnalyticsRow, isAr: boolean): string {
  if (row.is_lifetime) return isAr ? "مدى الحياة 👑" : "Lifetime 👑";
  if (row.hours_until_expiry === null || row.days_until_expiry === null) return "—";

  const hrs = row.hours_until_expiry;
  if (hrs > 0) {
    if (hrs < 48) {
      const hRounded = Math.max(1, Math.round(hrs));
      return isAr ? `متبقي ${hRounded} ساعة` : `${hRounded}h left`;
    }
    const days = Math.floor(hrs / 24);
    const remHours = Math.round(hrs % 24);
    return isAr
      ? `متبقي ${days} يوم${remHours > 0 ? ` و${remHours} س` : ""}`
      : `${days}d ${remHours}h left`;
  }

  const agoHours = Math.abs(hrs);
  if (agoHours < 72) {
    const hAgo = Math.max(1, Math.round(agoHours));
    return isAr ? `انتهى منذ ${hAgo} ساعة` : `Expired ${hAgo}h ago`;
  }
  const dAgo = Math.floor(agoHours / 24);
  return isAr ? `انتهى منذ ${dAgo} يوم` : `Expired ${dAgo}d ago`;
}

export default function FoundersStatsModal({
  isOpen,
  onClose,
  onFilterUser,
  isAr = true,
}: Props) {
  const [data, setData] = useState<FoundersRetentionSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [cohortFilter, setCohortFilter] = useState<CohortFilter>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [selectedFounder, setSelectedFounder] = useState<FounderAnalyticsRow | null>(null);

  const loadFounders = useCallback(async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetch("/api/admin/users/founders", { cache: "no-store" });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(json.detail || json.error || "Failed to load paid subscribers data");
      }
      setData(json as FoundersRetentionSummary);
    } catch (err: any) {
      const msg = err?.message || (isAr ? "تعذر تحميل إحصائيات المشتركين المدفوعين" : "Failed to load paid stats");
      setErrorMsg(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [isAr]);

  useEffect(() => {
    if (isOpen) {
      void loadFounders();
    }
  }, [isOpen, loadFounders]);

  const scopedMembers = useMemo(() => {
    const members = data?.members || [];
    if (cohortFilter === "ALL") return members;
    if (cohortFilter === "FOUNDERS") return members.filter((r) => r.is_founder);
    if (cohortFilter === "NON_FOUNDERS") return members.filter((r) => !r.is_founder);
    return members.filter((r) => r.cohort === cohortFilter);
  }, [data, cohortFilter]);

  const scopedKpis = useMemo(() => summarizeScopedMetrics(scopedMembers), [scopedMembers]);

  const filteredMembers = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return scopedMembers.filter((row) => {
      if (filterMode === "active" && !row.is_active) return false;
      if (filterMode === "renewed" && row.status !== "renewed_active") return false;
      if (filterMode === "expired" && row.is_active) return false;
      if (filterMode === "urgent") {
        const expWithin3d =
          row.is_active &&
          !row.is_lifetime &&
          row.hours_until_expiry !== null &&
          row.hours_until_expiry <= 72;
        if (!expWithin3d && row.status !== "in_grace_72h") return false;
      }
      if (!q) return true;
      return (
        String(row.email || "").toLowerCase().includes(q) ||
        String(row.display_name || "").toLowerCase().includes(q) ||
        String(row.whatsapp_number || "").toLowerCase().includes(q) ||
        String(row.telegram_chat_id || "").toLowerCase().includes(q)
      );
    });
  }, [scopedMembers, filterMode, searchQuery]);

  if (!isOpen) return null;

  const totalPaidUsers = data?.total_paid_users ?? data?.total_founders ?? 0;
  const foundersCount = data?.founders_count ?? (data ? data.members.filter((m) => m.is_founder).length : 0);
  const nonFoundersCount = data?.non_founder_paid_count ?? Math.max(0, totalPaidUsers - foundersCount);
  const regularCohortStats = data?.cohort_regular ?? {
    total: (data?.members || []).filter((m) => m.cohort === "REGULAR" || m.cohort === "LIFETIME" || m.cohort === "B2B").length,
    active: 0,
    renewed: 0,
    first_term_active: 0,
    expired: 0,
    in_grace_72h: 0,
    matured_total: 0,
    overall_retention_rate: 0,
    matured_retention_rate: 0,
  };
  const nonFounderSummary = data?.non_founders_paid ?? regularCohortStats;

  const handleCopy = async (val: string, id: string) => {
    try {
      if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
        throw new Error("Clipboard unavailable");
      }
      await navigator.clipboard.writeText(val);
      setCopiedId(id);
      toast.success(isAr ? "تم النسخ" : "Copied");
      setTimeout(() => setCopiedId(null), 1800);
    } catch {
      toast.error(isAr ? "تعذر النسخ إلى الحافظة" : "Unable to copy to clipboard");
    }
  };

  return (
    <div
      dir={isAr ? "rtl" : "ltr"}
      role="dialog"
      aria-modal="true"
      aria-label={isAr ? "إحصائيات كل المدفوعين ونسبة الاحتفاظ" : "All Paid Subscribers & Retention Dialog"}
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/75 backdrop-blur-xs animate-in fade-in duration-150"
    >
      <div className="relative w-full max-w-6xl max-h-[92vh] flex flex-col border-4 border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[8px_8px_0px_rgba(0,0,0,1)] dark:shadow-[8px_8px_0px_rgba(255,255,255,1)]">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 p-4 sm:p-5 border-b-4 border-black dark:border-white bg-amber-100 dark:bg-amber-950/40">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 border-2 border-black dark:border-white bg-amber-400 text-black flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)]">
              <Crown className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base sm:text-lg font-black uppercase tracking-wider text-black dark:text-white flex items-center gap-2">
                {isAr ? "إحصائيات كل المدفوعين والمؤسسين ونسبة الاحتفاظ" : "All Paid Subscribers & Retention Analytics"}
                {data && (
                  <span className="text-xs px-2 py-0.5 border border-black dark:border-white bg-amber-400 text-black font-mono">
                    {totalPaidUsers}
                  </span>
                )}
              </h2>
              <p className="text-xs text-zinc-700 dark:text-zinc-300 font-bold mt-0.5">
                {isAr
                  ? "تشمل كل من دفع (المؤسسون 50/100 ج.م + باقات Pro 200+ ج.م + مدى الحياة + كاشير) مع متابعة التجديد ونسبة الاحتفاظ"
                  : "Tracks all paying customers (Founders 50/100 + Regular 200+ Pro + Lifetime + Kashier), renewal dates & retention"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void loadFounders()}
              disabled={loading}
              className="h-9 px-3 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-black dark:text-white font-black text-xs flex items-center gap-1.5 shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>{isAr ? "تحديث" : "Refresh"}</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="w-9 h-9 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 hover:bg-red-500 hover:text-white flex items-center justify-center font-black transition-colors shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer"
              title={isAr ? "إغلاق" : "Close"}
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
          {loading && !data ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-zinc-500 font-bold text-sm">
              <Loader2 className="w-8 h-8 animate-spin text-amber-500" />
              <span>{isAr ? "جاري حساب إحصائيات المدفوعين ومواعيد التجديد..." : "Loading paid retention analytics..."}</span>
            </div>
          ) : errorMsg && !data ? (
            <div className="border-2 border-red-500 bg-red-50 dark:bg-red-950/30 p-4 text-sm font-bold text-red-700 dark:text-red-300 flex items-center justify-between gap-3">
              <span>{errorMsg}</span>
              <button
                type="button"
                onClick={() => void loadFounders()}
                className="px-3 py-1.5 bg-red-600 text-white text-xs font-black border border-black"
              >
                {isAr ? "إعادة المحاولة" : "Retry"}
              </button>
            </div>
          ) : data ? (
            <>
              {/* Scope Segment Tabs: All Paid vs Founders Only vs Regular/Other */}
              <div className="flex flex-wrap items-center gap-2">
                {[
                  { id: "ALL" as const, label: isAr ? `كل من دفع (${totalPaidUsers})` : `All Paid (${totalPaidUsers})` },
                  { id: "FOUNDERS" as const, label: isAr ? `المؤسسون فقط (${foundersCount})` : `Founders Only (${foundersCount})` },
                  { id: "NON_FOUNDERS" as const, label: isAr ? `باقات عادية ومدى الحياة (${nonFoundersCount})` : `Regular / Lifetime (${nonFoundersCount})` },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setCohortFilter(tab.id)}
                    className={`px-3 py-1.5 border-2 border-black dark:border-white text-xs font-black cursor-pointer transition-all ${
                      cohortFilter === tab.id
                        ? "bg-amber-400 text-black shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                        : "bg-zinc-100 dark:bg-zinc-900 text-black dark:text-white hover:bg-zinc-200 dark:hover:bg-zinc-800"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Top 6 KPI Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                <button
                  type="button"
                  onClick={() => setFilterMode("all")}
                  className={`p-3 text-start border-2 border-black dark:border-white cursor-pointer transition-all ${
                    filterMode === "all"
                      ? "bg-amber-100 dark:bg-amber-950/60 ring-2 ring-amber-500 shadow-[3px_3px_0px_rgba(0,0,0,1)]"
                      : "bg-zinc-50 dark:bg-zinc-900 hover:bg-zinc-100"
                  }`}
                >
                  <div className="text-[10px] font-black text-zinc-600 dark:text-zinc-400">
                    {cohortFilter === "FOUNDERS"
                      ? isAr ? "إجمالي المؤسسين" : "Total Founders"
                      : isAr ? "إجمالي المدفوعين" : "Total Paid Users"}
                  </div>
                  <div className="text-2xl font-black font-mono mt-1 text-black dark:text-white">
                    {scopedKpis.total}
                  </div>
                  <div className="text-[10px] font-bold text-zinc-500 mt-0.5">
                    {isAr
                      ? `${data.cohort_50.total} (50ج) · ${data.cohort_100.total} (100ج) · ${nonFoundersCount} (عادي)`
                      : `${data.cohort_50.total} (50) · ${data.cohort_100.total} (100) · ${nonFoundersCount} (reg)`}
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setFilterMode("active")}
                  className={`p-3 text-start border-2 border-black dark:border-white cursor-pointer transition-all ${
                    filterMode === "active"
                      ? "bg-emerald-100 dark:bg-emerald-950/60 ring-2 ring-emerald-500 shadow-[3px_3px_0px_rgba(0,0,0,1)]"
                      : "bg-emerald-50/70 dark:bg-emerald-950/20 hover:bg-emerald-100/70"
                  }`}
                >
                  <div className="text-[10px] font-black text-emerald-700 dark:text-emerald-300 flex items-center justify-between">
                    <span>{isAr ? "الموجودون الآن" : "Active Now"}</span>
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  </div>
                  <div className="text-2xl font-black font-mono mt-1 text-emerald-900 dark:text-emerald-100">
                    {scopedKpis.active}
                  </div>
                  <div className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 mt-0.5">
                    {isAr
                      ? `احتفاظ كلي: ${scopedKpis.overallRate}%`
                      : `Overall: ${scopedKpis.overallRate}%`}
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setFilterMode("renewed")}
                  className={`p-3 text-start border-2 border-black dark:border-white cursor-pointer transition-all ${
                    filterMode === "renewed"
                      ? "bg-sky-100 dark:bg-sky-950/60 ring-2 ring-sky-500 shadow-[3px_3px_0px_rgba(0,0,0,1)]"
                      : "bg-sky-50/70 dark:bg-sky-950/20 hover:bg-sky-100/70"
                  }`}
                >
                  <div className="text-[10px] font-black text-sky-700 dark:text-sky-300 flex items-center justify-between">
                    <span>{isAr ? "جدد فعلياً (دورة 2+)" : "Renewed (2+ Paid)"}</span>
                    <TrendingUp className="w-3.5 h-3.5" />
                  </div>
                  <div className="text-2xl font-black font-mono mt-1 text-sky-900 dark:text-sky-100">
                    {scopedKpis.renewed}
                  </div>
                  <div className="text-[10px] font-bold text-sky-700 dark:text-sky-400 mt-0.5">
                    {isAr
                      ? `وشهر أول: ${scopedKpis.firstTerm}`
                      : `1st term: ${scopedKpis.firstTerm}`}
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setFilterMode("expired")}
                  className={`p-3 text-start border-2 border-black dark:border-white cursor-pointer transition-all ${
                    filterMode === "expired"
                      ? "bg-rose-100 dark:bg-rose-950/60 ring-2 ring-rose-500 shadow-[3px_3px_0px_rgba(0,0,0,1)]"
                      : "bg-rose-50/70 dark:bg-rose-950/20 hover:bg-rose-100/70"
                  }`}
                >
                  <div className="text-[10px] font-black text-rose-700 dark:text-rose-300 flex items-center justify-between">
                    <span>{isAr ? "لم يجدد / منتهي" : "Not Renewed"}</span>
                    <AlertCircle className="w-3.5 h-3.5" />
                  </div>
                  <div className="text-2xl font-black font-mono mt-1 text-rose-900 dark:text-rose-100">
                    {scopedKpis.expired}
                  </div>
                  <div className="text-[10px] font-bold text-rose-700 dark:text-rose-400 mt-0.5">
                    {isAr
                      ? `منهم ${scopedKpis.inGrace} بمَهلة 72س`
                      : `${scopedKpis.inGrace} in 72h grace`}
                  </div>
                </button>

                <div className="p-3 border-2 border-black dark:border-white bg-violet-50 dark:bg-violet-950/30">
                  <div className="text-[10px] font-black text-violet-700 dark:text-violet-300">
                    {isAr ? "نسبة الاحتفاظ الفعلية" : "Matured Retention"}
                  </div>
                  <div className="text-2xl font-black font-mono mt-1 text-violet-950 dark:text-violet-100">
                    {scopedKpis.maturedRate}%
                  </div>
                  <div className="text-[10px] font-bold text-violet-700 dark:text-violet-400 mt-0.5">
                    {isAr
                      ? `${scopedKpis.renewed} جدد من ${scopedKpis.matured} استحقوا التجديد`
                      : `${scopedKpis.renewed} of ${scopedKpis.matured} due`}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setFilterMode("urgent")}
                  className={`p-3 text-start border-2 border-black dark:border-white cursor-pointer transition-all ${
                    filterMode === "urgent"
                      ? "bg-orange-100 dark:bg-orange-950/60 ring-2 ring-orange-500 shadow-[3px_3px_0px_rgba(0,0,0,1)]"
                      : "bg-orange-50/70 dark:bg-orange-950/20 hover:bg-orange-100/70"
                  }`}
                >
                  <div className="text-[10px] font-black text-orange-700 dark:text-orange-300 flex items-center justify-between">
                    <span>{isAr ? "متابعة عاجلة (≤72س)" : "Urgent (≤72h)"}</span>
                    <Clock className="w-3.5 h-3.5" />
                  </div>
                  <div className="text-2xl font-black font-mono mt-1 text-orange-950 dark:text-orange-100">
                    {scopedKpis.urgent}
                  </div>
                  <div className="text-[10px] font-bold text-orange-700 dark:text-orange-400 mt-0.5">
                    {isAr
                      ? `${scopedKpis.dueSoon} قارب + ${scopedKpis.inGrace} مهلة`
                      : `${scopedKpis.dueSoon} due + ${scopedKpis.inGrace} grace`}
                  </div>
                </button>
              </div>

              {/* Cohort 50 vs 100 vs Regular 200+ Comparison Bar */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {[
                  {
                    key: "50_EGP" as const,
                    title: isAr ? "مؤسسو 50 ج.م (أكتوبر)" : "50 EGP Founders (Oct)",
                    stats: data.cohort_50,
                  },
                  {
                    key: "100_EGP" as const,
                    title: isAr ? "مؤسسو 100 ج.م (نوفمبر)" : "100 EGP Founders (Nov)",
                    stats: data.cohort_100,
                  },
                  {
                    key: "NON_FOUNDERS" as const,
                    title: isAr ? "الباقات العادية / 200+ / مدى الحياة" : "Regular 200+ / Lifetime / Kashier",
                    stats: nonFounderSummary,
                  },
                ].map((c) => (
                  <div
                    key={c.key}
                    onClick={() => setCohortFilter((prev) => (prev === c.key ? "ALL" : c.key))}
                    className={`border-2 border-black dark:border-white p-3 cursor-pointer transition-all ${
                      cohortFilter === c.key
                        ? "bg-amber-50 dark:bg-amber-950/30 ring-2 ring-amber-500"
                        : "bg-zinc-50 dark:bg-zinc-900/60 hover:bg-zinc-100 dark:hover:bg-zinc-900"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2 gap-2">
                      <span className="text-xs font-black text-black dark:text-white">{c.title}</span>
                      <span className="text-[10px] font-mono font-black px-2 py-0.5 border border-black dark:border-white bg-white dark:bg-zinc-950 shrink-0">
                        {isAr ? `الاحتفاظ: ${c.stats.overall_retention_rate}%` : `Active: ${c.stats.overall_retention_rate}%`}
                        {c.stats.matured_total > 0 && (
                          <span className="text-violet-600 dark:text-violet-400">
                            {" "}· {isAr ? `التجديد: ${c.stats.matured_retention_rate}%` : `Renewal: ${c.stats.matured_retention_rate}%`}
                          </span>
                        )}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 text-[11px] font-bold text-zinc-700 dark:text-zinc-300">
                      <span>{isAr ? `الإجمالي: ${c.stats.total}` : `Total: ${c.stats.total}`}</span>
                      <span className="text-emerald-600 dark:text-emerald-400">
                        {isAr ? `نشط: ${c.stats.active}` : `Active: ${c.stats.active}`}
                      </span>
                      <span className="text-sky-600 dark:text-sky-400">
                        {isAr ? `جدد: ${c.stats.renewed}` : `Renewed: ${c.stats.renewed}`}
                      </span>
                      <span className="text-rose-600 dark:text-rose-400">
                        {isAr ? `مجددش: ${c.stats.expired}` : `Expired: ${c.stats.expired}`}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Search & Filter Toolbar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-white p-3">
                <div className="relative flex-1">
                  <Search className="w-4 h-4 text-zinc-400 absolute top-1/2 -translate-y-1/2 start-3" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder={isAr ? "ابحث بالإيميل أو رقم الواتساب أو معرف تليجرام..." : "Search email, WhatsApp, or Telegram ID..."}
                    className="w-full h-9 ps-9 pe-3 border-2 border-black dark:border-white bg-white dark:bg-zinc-950 text-xs font-bold text-black dark:text-white outline-none focus:ring-2 focus:ring-amber-400"
                  />
                </div>
                <div className="flex items-center gap-2 text-xs font-black text-zinc-600 dark:text-zinc-300">
                  <span>{isAr ? `المعروض: ${filteredMembers.length}` : `Showing: ${filteredMembers.length}`}</span>
                  <span>•</span>
                  <span className="font-mono text-emerald-600 dark:text-emerald-400">
                    {isAr ? `الإيراد المعروض: ${scopedKpis.revenue.toLocaleString()} ج.م` : `Revenue: ${scopedKpis.revenue.toLocaleString()} EGP`}
                  </span>
                </div>
              </div>

              {/* Paid Members Table */}
              <div className="border-2 border-black dark:border-white overflow-x-auto">
                <table className="w-full text-xs text-start border-collapse">
                  <thead className="bg-zinc-100 dark:bg-zinc-900 border-b-2 border-black dark:border-white text-[11px] font-black uppercase text-zinc-700 dark:text-zinc-300">
                    <tr>
                      <th className="p-2.5 text-start">{isAr ? "المشترك / التواصل" : "Subscriber / Contact"}</th>
                      <th className="p-2.5 text-center">{isAr ? "الفوج / الباقة" : "Cohort / Tier"}</th>
                      <th className="p-2.5 text-center">{isAr ? "المدفوع / الدفعات" : "Paid"}</th>
                      <th className="p-2.5 text-center">{isAr ? "الحالة" : "Status"}</th>
                      <th className="p-2.5 text-start">{isAr ? "موعد التجديد / الانتهاء (القاهرة)" : "Renewal / Expiry (Cairo)"}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800 bg-white dark:bg-zinc-950">
                    {filteredMembers.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="p-8 text-center text-zinc-400 font-bold">
                          {isAr ? "لا توجد نتائج مطابقة للفلتر الحالي" : "No matching subscribers found"}
                        </td>
                      </tr>
                    ) : (
                      filteredMembers.map((row) => {
                        const wa = buildWhatsAppUrl(row.whatsapp_number);
                        const cohortBadge = getPaidCohortMeta(row.cohort, isAr);
                        const isDueSoon =
                          row.is_active &&
                          !row.is_lifetime &&
                          row.hours_until_expiry !== null &&
                          row.hours_until_expiry <= 72;

                        return (
                          <tr
                            key={row.user_id}
                            onClick={() => setSelectedFounder(row)}
                            className="hover:bg-sky-50/70 dark:hover:bg-sky-950/30 transition-colors cursor-pointer"
                            title={isAr ? "اضغط لعرض استخدام المستخدم وتنبيهاته" : "Click to view user usage and notifications"}
                          >
                            <td className="p-2.5">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedFounder(row);
                                  }}
                                  className="font-mono font-bold text-black dark:text-white hover:text-sky-600 dark:hover:text-sky-400 hover:underline cursor-pointer"
                                >
                                  {row.email || row.user_id.slice(0, 8)}
                                </button>
                                <span className="text-[9px] font-black px-1.5 py-0.5 bg-sky-100 dark:bg-sky-950 text-sky-700 dark:text-sky-300 border border-sky-400">
                                  {isAr ? "استخدامه" : "Usage"}
                                </span>
                                {row.email && (
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      void handleCopy(row.email!, row.user_id);
                                    }}
                                    className="p-1 text-zinc-400 hover:text-black dark:hover:text-white cursor-pointer"
                                    title={isAr ? "نسخ الإيميل" : "Copy email"}
                                  >
                                    {copiedId === row.user_id ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                                  </button>
                                )}
                              </div>
                              <div className="flex flex-wrap items-center gap-2 mt-1 text-[10px] font-bold">
                                {row.display_name && <span className="text-zinc-500">{row.display_name}</span>}
                                {wa && (
                                  <a
                                    href={wa}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    onClick={(e) => e.stopPropagation()}
                                    className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-400 hover:underline"
                                  >
                                    <Smartphone className="w-2.5 h-2.5" />
                                    <span className="font-mono">{row.whatsapp_number}</span>
                                    <ExternalLink className="w-2.5 h-2.5" />
                                  </a>
                                )}
                                {row.telegram_chat_id && (
                                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-sky-100 dark:bg-sky-950/60 text-sky-700 dark:text-sky-300 border border-sky-400 font-mono">
                                    <Send className="w-2.5 h-2.5" />
                                    TG:{row.telegram_chat_id}
                                  </span>
                                )}
                              </div>
                            </td>

                            <td className="p-2.5 text-center">
                              <span
                                className={`inline-block px-2 py-0.5 border border-black dark:border-white text-[10px] font-black ${cohortBadge.badgeClass}`}
                              >
                                {cohortBadge.label}
                              </span>
                            </td>

                            <td className="p-2.5 text-center font-mono">
                              <div className="font-black text-black dark:text-white">
                                {row.total_paid_egp.toLocaleString()} {isAr ? "ج.م" : "EGP"}
                              </div>
                              <div className="text-[10px] text-zinc-500">
                                {isAr ? `${row.approved_orders_count} دفعة` : `${row.approved_orders_count} order(s)`}
                              </div>
                            </td>

                            <td className="p-2.5 text-center">
                              {row.status === "renewed_active" ? (
                                <span className="inline-block px-2 py-0.5 bg-emerald-500 text-black border border-black font-black text-[10px]">
                                  {row.is_lifetime
                                    ? isAr ? "ترقى لمدى الحياة 👑" : "Upgraded Lifetime 👑"
                                    : isAr ? "مجدد ونشط ♻️" : "Renewed & Active ♻️"}
                                </span>
                              ) : row.status === "active_first_term" ? (
                                <span
                                  className={`inline-block px-2 py-0.5 border border-black font-black text-[10px] ${
                                    isDueSoon ? "bg-orange-400 text-black animate-pulse" : "bg-sky-300 text-black"
                                  }`}
                                >
                                  {isDueSoon
                                    ? isAr ? "ينتهي قريباً ⏰" : "Due Soon ⏰"
                                    : isAr ? "نشط (شهر أول)" : "Active (1st Term)"}
                                </span>
                              ) : row.status === "in_grace_72h" ? (
                                <span className="inline-block px-2 py-0.5 bg-amber-400 text-black border border-black font-black text-[10px]">
                                  {isAr ? "مهلة 72 ساعة ⚠️" : "72h Grace ⚠️"}
                                </span>
                              ) : (
                                <span className="inline-block px-2 py-0.5 bg-rose-600 text-white border border-black font-black text-[10px]">
                                  {isAr ? "لم يجدد ❌" : "Churned ❌"}
                                </span>
                              )}
                            </td>

                            <td className="p-2.5">
                              <div className="flex items-center gap-1.5 font-mono font-bold text-black dark:text-white">
                                <Calendar className="w-3 h-3 text-zinc-400 shrink-0" />
                                <span>{row.is_lifetime ? (isAr ? "دائم للأبد" : "Lifetime") : formatCairoDateTime(row.current_period_end, isAr)}</span>
                              </div>
                              <div
                                className={`text-[10px] font-black mt-0.5 ${
                                  row.status === "churned"
                                    ? "text-rose-600 dark:text-rose-400"
                                    : row.status === "in_grace_72h" || isDueSoon
                                    ? "text-orange-600 dark:text-orange-400"
                                    : "text-emerald-600 dark:text-emerald-400"
                                }`}
                              >
                                {formatExpiryCountdown(row, isAr)}
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </div>
      </div>

      {/* Stacked User Usage Dialog rendered on top when clicking any founder */}
      <FounderUserUsageDialog
        founder={selectedFounder}
        onClose={() => setSelectedFounder(null)}
        onJumpToTable={(email) => {
          setSelectedFounder(null);
          onFilterUser?.(email);
        }}
        isAr={isAr}
      />
    </div>
  );
}
