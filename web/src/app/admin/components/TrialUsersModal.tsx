"use client";

import { useState, useMemo } from "react";
import {
  X,
  Clock,
  Search,
  Copy,
  Check,
  Calendar,
  ShieldCheck,
  MessageSquare,
  Crown,
  ExternalLink,
  Bot,
  Filter,
  CheckCircle2,
  AlertCircle,
  Smartphone,
  Send,
  UserCheck,
} from "lucide-react";
import { toast } from "sonner";

export interface TrialUserItem {
  user_id: string;
  email: string | null;
  display_name: string | null;
  username: string | null;
  telegram_chat_id: string | null;
  whatsapp_number: string | null;
  notification_channel: string | null;
  started_at: string;
  expires_at: string;
  status: "active" | "converted" | "expired";
  time_left_ms: number;
  chat_count: number;
  created_at: string;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  trials: TrialUserItem[];
  activeTrialCount: number;
  totalTrialCount: number;
  convertedTrialCount: number;
  expiredTrialCount: number;
  onFilterMainTable?: (specificUserSearch?: string) => void;
  isAr?: boolean;
}

function formatRemainingTime(expiresAt: string, isAr: boolean) {
  const exp = new Date(expiresAt).getTime();
  const diffMs = exp - Date.now();
  if (diffMs <= 0) {
    return isAr ? "منتهي" : "Expired";
  }
  const totalHours = Math.floor(diffMs / (1000 * 60 * 60));
  const days = Math.floor(totalHours / 24);
  const hours = totalHours % 24;

  if (days > 0) {
    return isAr ? `متبقي ${days} يوم و ${hours} ساعة` : `${days}d ${hours}h left`;
  }
  if (hours > 0) {
    const mins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
    return isAr ? `متبقي ${hours} ساعة و ${mins} دقيقة` : `${hours}h ${mins}m left`;
  }
  const mins = Math.max(1, Math.floor(diffMs / (1000 * 60)));
  return isAr ? `متبقي ${mins} دقيقة` : `${mins}m left`;
}

function formatCairoDateTime(dateStr: string, isAr: boolean) {
  try {
    const d = new Date(dateStr);
    return new Intl.DateTimeFormat(isAr ? "ar-EG" : "en-US", {
      timeZone: "Africa/Cairo",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return dateStr;
  }
}

function getWhatsAppUrl(phone?: string | null) {
  if (!phone) return null;
  const cleaned = phone.replace(/[^0-9]/g, "");
  if (!cleaned) return null;
  const num = cleaned.startsWith("01") ? `20${cleaned.slice(1)}` : cleaned.startsWith("20") ? cleaned : `20${cleaned}`;
  return `https://wa.me/${num}`;
}

export default function TrialUsersModal({
  isOpen,
  onClose,
  trials = [],
  activeTrialCount,
  totalTrialCount,
  convertedTrialCount,
  expiredTrialCount,
  onFilterMainTable,
  isAr = true,
}: Props) {
  const [search, setSearch] = useState("");
  const [selectedStatus, setSelectedStatus] = useState<"active" | "all" | "converted" | "expired">("active");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const filteredTrials = useMemo(() => {
    let list = trials;
    if (selectedStatus !== "all") {
      list = list.filter((t) => t.status === selectedStatus);
    }

    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((t) => {
        return (
          (t.email || "").toLowerCase().includes(q) ||
          (t.display_name || "").toLowerCase().includes(q) ||
          (t.username || "").toLowerCase().includes(q) ||
          (t.user_id || "").toLowerCase().includes(q) ||
          (t.whatsapp_number || "").includes(q) ||
          (t.telegram_chat_id || "").includes(q)
        );
      });
    }

    return list;
  }, [trials, selectedStatus, search]);

  const handleCopy = (id: string, text: string) => {
    try {
      navigator.clipboard.writeText(text);
      setCopiedId(id);
      toast.success(isAr ? "تم النسخ" : "Copied");
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      toast.error(isAr ? "فشل النسخ" : "Failed to copy");
    }
  };

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/70 backdrop-blur-xs animate-in fade-in duration-150"
    >
      <div className="relative w-full max-w-5xl max-h-[92vh] flex flex-col border-4 border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[8px_8px_0px_rgba(0,0,0,1)] dark:shadow-[8px_8px_0px_rgba(255,255,255,1)]">
        {/* Header */}
        <div className="flex items-center justify-between p-4 sm:p-5 border-b-4 border-black dark:border-white bg-amber-50 dark:bg-amber-950/40">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 border-2 border-black dark:border-white bg-amber-400 text-black flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)]">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base sm:text-lg font-black uppercase tracking-wider text-black dark:text-white flex items-center gap-2">
                {isAr ? "المستخدمون التجريبيون (Trial Users)" : "Trial Users & Active Subscriptions"}
                <span className="text-xs px-2 py-0.5 border border-black dark:border-white bg-amber-400 text-black font-mono">
                  {selectedStatus === "active" ? activeTrialCount : filteredTrials.length}
                </span>
              </h2>
              <p className="text-xs text-zinc-600 dark:text-zinc-400 font-bold mt-0.5">
                {isAr
                  ? "عرض تفصيلي لجميع فترات التجربة النشطة والتاريخية مع إحصائيات استهلاك رسائل الشات"
                  : "Complete breakdown of all active, expired, and converted trial users with chat quotas"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 hover:bg-red-500 hover:text-white dark:hover:bg-red-500 flex items-center justify-center font-black transition-colors shadow-[2px_2px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_rgba(255,255,255,1)]"
            title={isAr ? "إغلاق" : "Close"}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Top KPI Cards (Clickable Filters) */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 p-4 border-b-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900/60">
          {/* Active Now */}
          <button
            type="button"
            onClick={() => setSelectedStatus("active")}
            className={`p-3 text-start border-2 border-black dark:border-white transition-all cursor-pointer ${
              selectedStatus === "active"
                ? "bg-emerald-100 dark:bg-emerald-950/70 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] ring-2 ring-emerald-500"
                : "bg-white dark:bg-zinc-900 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            }`}
          >
            <div className="flex items-center justify-between text-xs font-black text-emerald-800 dark:text-emerald-300">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                {isAr ? "نشط حالياً" : "Active Now"}
              </span>
              <CheckCircle2 className="w-3.5 h-3.5" />
            </div>
            <div className="text-2xl font-black font-mono text-emerald-900 dark:text-emerald-100 mt-1">
              {activeTrialCount}
            </div>
            <div className="text-[10px] text-zinc-500 dark:text-zinc-400 font-bold mt-0.5">
              {isAr ? "لم تنتهِ صلاحيتهم بعد" : "Current unexpired"}
            </div>
          </button>

          {/* Converted to Pro */}
          <button
            type="button"
            onClick={() => setSelectedStatus("converted")}
            className={`p-3 text-start border-2 border-black dark:border-white transition-all cursor-pointer ${
              selectedStatus === "converted"
                ? "bg-purple-100 dark:bg-purple-950/70 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] ring-2 ring-purple-500"
                : "bg-white dark:bg-zinc-900 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            }`}
          >
            <div className="flex items-center justify-between text-xs font-black text-purple-800 dark:text-purple-300">
              <span className="flex items-center gap-1.5">
                <Crown className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
                {isAr ? "مشتركو برو" : "Converted to Pro"}
              </span>
            </div>
            <div className="text-2xl font-black font-mono text-purple-900 dark:text-purple-100 mt-1">
              {convertedTrialCount}
            </div>
            <div className="text-[10px] text-zinc-500 dark:text-zinc-400 font-bold mt-0.5">
              {isAr ? "قاموا بالترقية لبرو" : "Upgraded to Pro"}
            </div>
          </button>

          {/* Expired */}
          <button
            type="button"
            onClick={() => setSelectedStatus("expired")}
            className={`p-3 text-start border-2 border-black dark:border-white transition-all cursor-pointer ${
              selectedStatus === "expired"
                ? "bg-rose-100 dark:bg-rose-950/70 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] ring-2 ring-rose-500"
                : "bg-white dark:bg-zinc-900 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            }`}
          >
            <div className="flex items-center justify-between text-xs font-black text-rose-800 dark:text-rose-300">
              <span className="flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 text-rose-600 dark:text-rose-400" />
                {isAr ? "منتهي الصلاحية" : "Expired"}
              </span>
            </div>
            <div className="text-2xl font-black font-mono text-rose-900 dark:text-rose-100 mt-1">
              {expiredTrialCount}
            </div>
            <div className="text-[10px] text-zinc-500 dark:text-zinc-400 font-bold mt-0.5">
              {isAr ? "انتهت فترة الـ 3 أيام" : "Trial ended"}
            </div>
          </button>

          {/* Total Trials */}
          <button
            type="button"
            onClick={() => setSelectedStatus("all")}
            className={`p-3 text-start border-2 border-black dark:border-white transition-all cursor-pointer ${
              selectedStatus === "all"
                ? "bg-amber-100 dark:bg-amber-950/70 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] ring-2 ring-amber-500"
                : "bg-white dark:bg-zinc-900 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            }`}
          >
            <div className="flex items-center justify-between text-xs font-black text-amber-800 dark:text-amber-300">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                {isAr ? "إجمالي التجارب" : "Total Trials"}
              </span>
            </div>
            <div className="text-2xl font-black font-mono text-amber-900 dark:text-amber-100 mt-1">
              {totalTrialCount}
            </div>
            <div className="text-[10px] text-zinc-500 dark:text-zinc-400 font-bold mt-0.5">
              {isAr ? "كل من جرب المنصة" : "All cumulative"}
            </div>
          </button>
        </div>

        {/* Filter Controls & Search */}
        <div className="p-4 border-b-2 border-black dark:border-white flex flex-wrap items-center justify-between gap-3 bg-white dark:bg-zinc-950">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="w-4 h-4 absolute top-1/2 -translate-y-1/2 start-3 text-zinc-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={isAr ? "بحث بالبريد، الاسم، الهاتف، أو المعرف..." : "Search by email, name, phone, or UID..."}
              className="w-full h-10 ps-9 pe-3 text-xs font-bold border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900 text-black dark:text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="absolute top-1/2 -translate-y-1/2 end-3 text-xs font-bold text-zinc-400 hover:text-black dark:hover:text-white"
              >
                ✕
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            {onFilterMainTable && (
              <button
                type="button"
                onClick={() => onFilterMainTable()}
                className="h-10 px-3 border-2 border-black dark:border-white bg-amber-400 hover:bg-amber-500 text-black font-black text-xs uppercase tracking-wider flex items-center gap-1.5 shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                title={isAr ? "فلترة المستخدمين النشطين في الجدول الرئيسي" : "Filter active trials in main table"}
              >
                <Filter className="w-3.5 h-3.5" />
                <span>{isAr ? "فلترة بالجدول الرئيسي" : "Filter Main Table"}</span>
              </button>
            )}
          </div>
        </div>

        {/* Content Body / List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {filteredTrials.length === 0 ? (
            <div className="text-center py-12 border-2 border-dashed border-zinc-300 dark:border-zinc-800 p-8">
              <Clock className="w-10 h-10 mx-auto text-zinc-400 mb-2" />
              <p className="text-sm font-black text-zinc-700 dark:text-zinc-300">
                {isAr ? "لا توجد حسابات تجريبية مطابقة" : "No trial accounts match the filter"}
              </p>
              <p className="text-xs text-zinc-400 mt-1 font-bold">
                {search ? (isAr ? "جرب كلمة بحث أخرى" : "Try different search terms") : (isAr ? "لا يوجد مستخدمون في هذا التصنيف حالياً" : "No users under this status")}
              </p>
            </div>
          ) : (
            <div className="space-y-2.5">
              {filteredTrials.map((t) => {
                const isCopied = copiedId === t.user_id;
                const waUrl = getWhatsAppUrl(t.whatsapp_number);
                const isUserActive = t.status === "active";
                const isConverted = t.status === "converted";

                return (
                  <div
                    key={t.user_id}
                    className={`border-2 border-black dark:border-white p-3.5 transition-all ${
                      isUserActive
                        ? "bg-amber-50/50 dark:bg-amber-950/20 hover:border-amber-500"
                        : isConverted
                        ? "bg-purple-50/40 dark:bg-purple-950/20"
                        : "bg-white dark:bg-zinc-900 opacity-85"
                    } shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)]`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      {/* User Info */}
                      <div className="flex items-start gap-3 min-w-[240px] flex-1">
                        <div
                          className={`w-9 h-9 border-2 border-black dark:border-white flex items-center justify-center font-black text-sm shrink-0 shadow-[1px_1px_0px_rgba(0,0,0,1)] ${
                            isUserActive
                              ? "bg-amber-400 text-black"
                              : isConverted
                              ? "bg-purple-500 text-white"
                              : "bg-zinc-200 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300"
                          }`}
                        >
                          {(t.display_name || t.email || "U").charAt(0).toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-black text-xs text-black dark:text-white truncate max-w-[200px] sm:max-w-[280px]">
                              {t.display_name || t.username || (isAr ? "مستخدم بدون اسم" : "Anonymous")}
                            </span>

                            {/* Status Badge */}
                            {isUserActive && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 border border-emerald-600 bg-emerald-50 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-200 text-[10px] font-black">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                                {isAr ? "نشط الآن" : "Active"}
                              </span>
                            )}
                            {isConverted && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 border border-purple-600 bg-purple-50 dark:bg-purple-950/60 text-purple-800 dark:text-purple-200 text-[10px] font-black">
                                <Crown className="w-3 h-3 text-purple-600 dark:text-purple-400" />
                                {isAr ? "مشترك برو 👑" : "Pro 👑"}
                              </span>
                            )}
                            {!isUserActive && !isConverted && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 border border-zinc-400 bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 text-[10px] font-bold">
                                {isAr ? "منتهي" : "Expired"}
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-2 mt-1 text-xs text-zinc-600 dark:text-zinc-400 font-mono">
                            <span className="truncate max-w-[220px] sm:max-w-[320px]">{t.email || "—"}</span>
                            {t.email && (
                              <button
                                type="button"
                                onClick={() => handleCopy(t.user_id, t.email!)}
                                className="text-zinc-400 hover:text-black dark:hover:text-white transition-colors"
                                title={isAr ? "نسخ الإيميل" : "Copy email"}
                              >
                                {isCopied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                              </button>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Remaining Time & Quota */}
                      <div className="flex flex-wrap items-center gap-3 sm:gap-6">
                        {/* Remaining Time */}
                        <div className="text-start sm:text-end">
                          <div className="text-[10px] font-black text-zinc-500 uppercase tracking-wider">
                            {isAr ? "الوقت المتبقي" : "Time Remaining"}
                          </div>
                          <div className={`text-xs font-black mt-0.5 ${
                            isUserActive
                              ? "text-emerald-700 dark:text-emerald-300 font-mono"
                              : isConverted
                              ? "text-purple-700 dark:text-purple-300 font-bold"
                              : "text-zinc-400 line-through"
                          }`}>
                            {isConverted
                              ? (isAr ? "مفعل برو دائم" : "Subscribed Pro")
                              : formatRemainingTime(t.expires_at, isAr)}
                          </div>
                        </div>

                        {/* Chat Messages Quota */}
                        <div className="text-start sm:text-end">
                          <div className="text-[10px] font-black text-zinc-500 uppercase tracking-wider">
                            {isAr ? "استهلاك الشات" : "Chat Msgs"}
                          </div>
                          <div className="inline-flex items-center gap-1 text-xs font-black font-mono text-zinc-800 dark:text-zinc-200 mt-0.5">
                            <MessageSquare className="w-3 h-3 text-blue-500" />
                            <span>{isAr ? `${t.chat_count} رسالة` : `${t.chat_count} msgs`}</span>
                          </div>
                        </div>

                        {/* Dates */}
                        <div className="text-start sm:text-end text-[11px] font-bold text-zinc-500">
                          <div>
                            <span className="text-[9px] text-zinc-400 uppercase">{isAr ? "بدأ: " : "Start: "}</span>
                            <span className="font-mono text-zinc-700 dark:text-zinc-300">{formatCairoDateTime(t.started_at, isAr)}</span>
                          </div>
                          <div>
                            <span className="text-[9px] text-zinc-400 uppercase">{isAr ? "ينتهي: " : "End: "}</span>
                            <span className="font-mono text-zinc-700 dark:text-zinc-300">{formatCairoDateTime(t.expires_at, isAr)}</span>
                          </div>
                        </div>

                        {/* Actions & Contacts */}
                        <div className="flex items-center gap-1.5">
                          {/* WhatsApp Button */}
                          {waUrl && (
                            <a
                              href={waUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="h-8 px-2 border border-black dark:border-white bg-emerald-500 hover:bg-emerald-600 text-white font-black text-[11px] flex items-center gap-1 shadow-[1px_1px_0px_rgba(0,0,0,1)]"
                              title={isAr ? `مراسلة واتساب: ${t.whatsapp_number}` : `WhatsApp: ${t.whatsapp_number}`}
                            >
                              <Smartphone className="w-3.5 h-3.5" />
                              <span className="hidden sm:inline">واتساب</span>
                            </a>
                          )}

                          {/* Telegram Link */}
                          {t.telegram_chat_id && (
                            <span
                              className="h-8 px-2 border border-black dark:border-white bg-sky-500 text-white font-black text-[10px] flex items-center gap-1 font-mono shadow-[1px_1px_0px_rgba(0,0,0,1)]"
                              title={`Telegram ID: ${t.telegram_chat_id}`}
                            >
                              <Send className="w-3 h-3" />
                              <span className="hidden sm:inline">TG</span>
                            </span>
                          )}

                          {/* Filter in Main Table */}
                          {onFilterMainTable && (
                            <button
                              type="button"
                              onClick={() => onFilterMainTable(t.email || t.user_id)}
                              className="h-8 px-2.5 border border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 hover:bg-amber-400 hover:text-black dark:hover:bg-amber-400 dark:hover:text-black text-black dark:text-white font-black text-[11px] flex items-center gap-1 shadow-[1px_1px_0px_rgba(0,0,0,1)] transition-colors"
                              title={isAr ? "عرض هذا المستخدم في الجدول الرئيسي بالأسفل" : "View user in main table"}
                            >
                              <ExternalLink className="w-3 h-3" />
                              <span>{isAr ? "عرض" : "View"}</span>
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 sm:p-4 border-t-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900 flex items-center justify-between text-xs font-bold text-zinc-500">
          <div>
            {isAr
              ? `عرض ${filteredTrials.length} مستخدم من أصل ${trials.length} حساب تجريبي`
              : `Showing ${filteredTrials.length} of ${trials.length} trial accounts`}
          </div>
          <button
            onClick={onClose}
            className="h-8 px-4 border-2 border-black dark:border-white bg-white dark:bg-zinc-800 text-black dark:text-white font-black hover:bg-zinc-200 dark:hover:bg-zinc-700 shadow-[2px_2px_0px_rgba(0,0,0,1)]"
          >
            {isAr ? "إغلاق" : "Close"}
          </button>
        </div>
      </div>
    </div>
  );
}
