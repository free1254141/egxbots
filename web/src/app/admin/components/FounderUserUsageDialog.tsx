"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  Bell,
  Bot,
  Calendar,
  CheckCircle2,
  CreditCard,
  ExternalLink,
  Eye,
  Loader2,
  Mail,
  MessageSquare,
  MousePointerClick,
  RefreshCw,
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
} from "@/lib/admin/founders-analytics";

export interface UsageDialogUserSummary {
  user_id: string;
  email?: string | null;
  display_name?: string | null;
  badge_label?: string | null;
}

interface Props {
  founder?: FounderAnalyticsRow | null;
  userSummary?: UsageDialogUserSummary | null;
  onClose: () => void;
  onJumpToTable?: (email: string) => void;
  isAr?: boolean;
}

interface DetailedUserPayload {
  usage?: {
    pageViews?: number;
    uniquePages?: number;
    activeDays?: number;
    topPages?: { path: string; views: number }[];
    chatMessages?: number;
    chatSessions?: number;
    aiRequests?: number;
    totalQuotaChats?: number;
    bonusCreditsGranted?: number;
    bonusCreditsUsed?: number;
    bonusCreditsRemaining?: number;
    chatByDay?: { date: string; chat_count: number }[];
    recentQuestions?: { content: string; created_at: string }[];
    lastActiveAt?: string | null;
  };
  notifications?: {
    telegramReminders?: {
      reminder_days: number;
      status: string;
      error?: string | null;
      sent_at?: string | null;
      created_at: string;
    }[];
    emailLogs?: {
      id: string;
      message_type: string;
      channel: string;
      status: string;
      sent_at: string;
      delivered?: boolean;
      opened?: boolean;
      clicked?: boolean;
      bounced?: boolean;
    }[];
  };
  payments?: {
    attempts?: number;
    successful?: number;
    totalPaid?: number;
    currency?: string;
    recent?: {
      plan_id?: string | null;
      amount?: number;
      status?: string;
      provider?: string;
      created_at: string;
    }[];
  };
  open_positions?: {
    symbol: string;
    entry_price?: number;
    status?: string;
    quantity?: number;
  }[];
  bot_subscriptions?: {
    service_type: string;
    notifications_enabled: boolean;
  }[];
}

export default function FounderUserUsageDialog({
  founder = null,
  userSummary = null,
  onClose,
  onJumpToTable,
  isAr = true,
}: Props) {
  const targetUserId = founder?.user_id || userSummary?.user_id || null;
  const targetEmail = founder?.email || userSummary?.email || null;
  const targetDisplayName = founder?.display_name || userSummary?.display_name || null;

  const [detail, setDetail] = useState<DetailedUserPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const requestSeqRef = useRef(0);

  const loadDetail = useCallback(async () => {
    const targetId = targetUserId;
    abortRef.current?.abort();
    if (!targetId) {
      requestSeqRef.current += 1;
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    const reqId = ++requestSeqRef.current;

    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`/api/admin/users/${targetId}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      const json = await res.json().catch(() => ({}));
      if (controller.signal.aborted || reqId !== requestSeqRef.current) return;
      if (!res.ok) {
        throw new Error(json.detail || json.error || "Failed to load user usage");
      }
      setDetail(json as DetailedUserPayload);
    } catch (err: any) {
      if (controller.signal.aborted || err?.name === "AbortError" || reqId !== requestSeqRef.current) {
        return;
      }
      const msg = err?.message || (isAr ? "تعذر تحميل تفاصيل استخدام المستخدم" : "Failed to load user usage");
      setErrorMsg(msg);
      toast.error(msg);
    } finally {
      if (!controller.signal.aborted && reqId === requestSeqRef.current) {
        setLoading(false);
      }
    }
  }, [targetUserId, isAr]);

  useEffect(() => {
    setDetail(null);
    setErrorMsg(null);
    if (targetUserId) {
      void loadDetail();
    } else {
      abortRef.current?.abort();
      requestSeqRef.current += 1;
      setLoading(false);
    }
    return () => {
      abortRef.current?.abort();
      requestSeqRef.current += 1;
    };
  }, [targetUserId, loadDetail]);

  if (!targetUserId) return null;

  const waUrl = buildWhatsAppUrl(founder?.whatsapp_number);
  const cohortBadge = founder ? getPaidCohortMeta(founder.cohort, isAr) : null;
  const usage = detail?.usage;
  const tgReminders = detail?.notifications?.telegramReminders || [];
  const emailLogs = detail?.notifications?.emailLogs || [];
  const positions = detail?.open_positions || [];
  const botSubs = detail?.bot_subscriptions || [];
  const recentOrders = detail?.payments?.recent || [];

  return (
    <div
      dir={isAr ? "rtl" : "ltr"}
      role="dialog"
      aria-modal="true"
      aria-label={isAr ? `استخدام المستخدم ${targetEmail || ""}` : `User usage ${targetEmail || ""}`}
      className="fixed inset-0 z-[60] flex items-center justify-center p-3 sm:p-6 bg-black/70 backdrop-blur-xs animate-in fade-in duration-150"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-4xl max-h-[88vh] flex flex-col border-4 border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[10px_10px_0px_rgba(0,0,0,1)] dark:shadow-[10px_10px_0px_rgba(255,255,255,1)]">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 p-4 border-b-4 border-black dark:border-white bg-sky-100 dark:bg-sky-950/50">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Activity className="w-5 h-5 text-sky-600 dark:text-sky-400 shrink-0" />
              <h3 className="text-sm sm:text-base font-black text-black dark:text-white font-mono truncate">
                {targetEmail || targetUserId}
              </h3>
              {cohortBadge ? (
                <span className={`text-[10px] font-black px-2 py-0.5 border border-black ${cohortBadge.badgeClass}`}>
                  {cohortBadge.label}
                </span>
              ) : userSummary?.badge_label ? (
                <span className="text-[10px] font-black px-2 py-0.5 border border-black bg-sky-300 text-black">
                  {userSummary.badge_label}
                </span>
              ) : null}
              {founder?.in_grace_72h && (
                <span className="text-[10px] font-black px-2 py-0.5 border border-black bg-amber-400 text-black">
                  {isAr ? "مهلة 72 ساعة ⚠️" : "72h Grace ⚠️"}
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2 mt-1.5 text-[11px] font-bold text-zinc-700 dark:text-zinc-300">
              {targetDisplayName && <span>{targetDisplayName}</span>}
              {founder && (
                <span className="inline-flex items-center gap-1 font-mono">
                  <Calendar className="w-3 h-3 text-zinc-500" />
                  {founder.is_lifetime ? (isAr ? "مدى الحياة" : "Lifetime") : formatCairoDateTime(founder.current_period_end, isAr)}
                </span>
              )}
              {waUrl && founder?.whatsapp_number && (
                <a
                  href={waUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-400 hover:underline font-mono"
                >
                  <Smartphone className="w-3 h-3" />
                  <span>{founder.whatsapp_number}</span>
                  <ExternalLink className="w-2.5 h-2.5" />
                </a>
              )}
              {founder?.telegram_chat_id && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-sky-200/70 dark:bg-sky-900/60 text-sky-900 dark:text-sky-200 border border-sky-400 font-mono">
                  <Send className="w-3 h-3" />
                  TG:{founder.telegram_chat_id}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {targetEmail && onJumpToTable && (
              <button
                type="button"
                onClick={() => onJumpToTable(targetEmail)}
                className="h-8 px-2.5 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 hover:bg-zinc-100 text-[11px] font-black text-black dark:text-white cursor-pointer"
              >
                {isAr ? "فتح في الجدول" : "Find in Table"}
              </button>
            )}
            <button
              type="button"
              onClick={() => void loadDetail()}
              disabled={loading}
              className="h-8 px-2.5 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 hover:bg-zinc-100 text-[11px] font-black text-black dark:text-white flex items-center gap-1 cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
              <span>{isAr ? "تحديث" : "Refresh"}</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="w-8 h-8 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 hover:bg-red-500 hover:text-white flex items-center justify-center font-black cursor-pointer"
              title={isAr ? "رجوع للقائمة" : "Back to list"}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {loading && !detail ? (
            <div className="flex flex-col items-center justify-center py-14 gap-3 text-zinc-500 text-xs font-bold">
              <Loader2 className="w-7 h-7 animate-spin text-sky-500" />
              <span>{isAr ? "جاري جلب تفاصيل الاستخدام والأسئلة والتنبيهات..." : "Loading user usage & notifications..."}</span>
            </div>
          ) : errorMsg && !detail ? (
            <div className="border-2 border-red-500 bg-red-50 dark:bg-red-950/30 p-4 text-xs font-bold text-red-700 dark:text-red-300">
              {errorMsg}
            </div>
          ) : detail ? (
            <>
              {/* 4 Usage KPIs */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900">
                  <div className="text-[10px] font-black text-zinc-500 uppercase">
                    {isAr ? "الزيارات / أيام النشاط" : "Page Views / Active Days"}
                  </div>
                  <div className="text-xl font-black font-mono mt-1 text-black dark:text-white">
                    {usage?.pageViews || 0} <span className="text-xs text-sky-600">({usage?.activeDays || 0} {isAr ? "يوم" : "d"})</span>
                  </div>
                  <div className="text-[10px] font-bold text-zinc-500 mt-0.5 truncate">
                    {isAr ? "آخر ظهور:" : "Last:"} {formatCairoDateTime(usage?.lastActiveAt, isAr)}
                  </div>
                </div>

                <div className="p-3 border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900">
                  <div className="text-[10px] font-black text-zinc-500 uppercase">
                    {isAr ? "استخدام الشات الذكي" : "AI Chat Quota Used"}
                  </div>
                  <div className="text-xl font-black font-mono mt-1 text-black dark:text-white">
                    {usage?.totalQuotaChats ?? usage?.chatMessages ?? 0}{" "}
                    <span className="text-xs text-zinc-500">{isAr ? "رسالة" : "msgs"}</span>
                  </div>
                  <div className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 mt-0.5">
                    {isAr
                      ? `بونص تليجرام متبقي: ${usage?.bonusCreditsRemaining || 0}`
                      : `Bonus left: ${usage?.bonusCreditsRemaining || 0}`}
                  </div>
                </div>

                <div className="p-3 border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900">
                  <div className="text-[10px] font-black text-zinc-500 uppercase">
                    {isAr ? "إجمالي المدفوع" : "Payments Total"}
                  </div>
                  <div className="text-xl font-black font-mono mt-1 text-emerald-600 dark:text-emerald-400">
                    {Number(detail.payments?.totalPaid || founder?.total_paid_egp || 0).toLocaleString()} {isAr ? "ج.م" : "EGP"}
                  </div>
                  <div className="text-[10px] font-bold text-zinc-500 mt-0.5">
                    {isAr
                      ? `ناجح: ${detail.payments?.successful || 0} من ${detail.payments?.attempts || 0}`
                      : `Paid: ${detail.payments?.successful || 0} / ${detail.payments?.attempts || 0}`}
                  </div>
                </div>

                <div className="p-3 border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900">
                  <div className="text-[10px] font-black text-zinc-500 uppercase">
                    {isAr ? "المحفظة وتنبيهات البوت" : "Portfolio & Bots"}
                  </div>
                  <div className="text-xl font-black font-mono mt-1 text-black dark:text-white">
                    {positions.length} <span className="text-xs text-zinc-500">{isAr ? "سهم" : "stocks"}</span> · {botSubs.length}{" "}
                    <span className="text-xs text-zinc-500">{isAr ? "بوت" : "bots"}</span>
                  </div>
                  <div className="text-[10px] font-bold text-zinc-500 mt-0.5">
                    {botSubs.length === 0
                      ? isAr ? "لم يفعّل بوت التنبيهات الخاص" : "No private bot alerts"
                      : isAr ? "تنبيهات البوت مفعلة" : "Bot alerts configured"}
                  </div>
                </div>
              </div>

              {/* Pages & Daily Chat Usage */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900/60 p-3">
                  <h4 className="text-[11px] font-black uppercase text-zinc-600 dark:text-zinc-300 mb-2 flex items-center gap-1.5">
                    <TrendingUp className="w-3.5 h-3.5 text-sky-500" />
                    {isAr ? "أكثر الصفحات زيارة" : "Most Visited Pages"}
                  </h4>
                  {(usage?.topPages || []).length > 0 ? (
                    <div className="space-y-1 text-xs font-mono">
                      {(usage?.topPages || []).slice(0, 8).map((p) => (
                        <div key={p.path} className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 py-1 gap-2">
                          <span className="truncate text-black dark:text-zinc-100" dir="ltr">{p.path}</span>
                          <span className="font-black text-sky-600 dark:text-sky-400 shrink-0">{p.views}×</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-zinc-400 font-bold">{isAr ? "لا توجد زيارات مسجلة" : "No page telemetry"}</p>
                  )}
                </div>

                <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900/60 p-3">
                  <h4 className="text-[11px] font-black uppercase text-zinc-600 dark:text-zinc-300 mb-2 flex items-center gap-1.5">
                    <MessageSquare className="w-3.5 h-3.5 text-emerald-500" />
                    {isAr ? "استهلاك الشات حسب اليوم" : "AI Chat Usage by Day"}
                  </h4>
                  {(usage?.chatByDay || []).length > 0 ? (
                    <div className="space-y-1 text-xs font-mono">
                      {(usage?.chatByDay || []).slice(0, 8).map((d) => (
                        <div key={d.date} className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 py-1">
                          <span className="text-black dark:text-zinc-100">{d.date}</span>
                          <span className="font-black text-emerald-600 dark:text-emerald-400">
                            {d.chat_count} {isAr ? "رسالة" : "msgs"}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-zinc-400 font-bold">{isAr ? "لا يوجد استهلاك شات مسجل" : "No chat quota history"}</p>
                  )}
                </div>
              </div>

              {/* Recent User Questions */}
              <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900/60 p-3">
                <h4 className="text-[11px] font-black uppercase text-zinc-600 dark:text-zinc-300 mb-2 flex items-center gap-1.5">
                  <Bot className="w-3.5 h-3.5 text-violet-500" />
                  {isAr ? "آخر أسئلة الشات للمستخدم" : "Recent AI Chat Questions"}
                </h4>
                {(usage?.recentQuestions || []).length > 0 ? (
                  <div className="space-y-1.5">
                    {(usage?.recentQuestions || []).slice(0, 8).map((q, idx) => (
                      <div key={idx} className="flex items-start justify-between gap-2 text-xs bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-800 px-2.5 py-1.5">
                        <span className="font-bold text-black dark:text-zinc-100 break-words">{q.content}</span>
                        <span className="text-[10px] font-mono text-zinc-400 shrink-0 whitespace-nowrap">
                          {formatCairoDateTime(q.created_at, isAr)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-zinc-400 font-bold">{isAr ? "لا توجد أسئلة نصية مسجلة في الويب" : "No web chat questions recorded"}</p>
                )}
              </div>

              {/* Telegram Reminders & Email Delivery/Open History */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900/60 p-3">
                  <h4 className="text-[11px] font-black uppercase text-zinc-600 dark:text-zinc-300 mb-2 flex items-center gap-1.5">
                    <Bell className="w-3.5 h-3.5 text-amber-500" />
                    {isAr ? "سجل تنبيهات تجديد تليجرام" : "Telegram Renewal Reminders"}
                  </h4>
                  {tgReminders.length > 0 ? (
                    <div className="space-y-1.5 text-xs">
                      {tgReminders.map((r, idx) => {
                        const ok = String(r.status || "").toLowerCase() === "sent";
                        return (
                          <div key={idx} className="bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-800 p-2">
                            <div className="flex items-center justify-between gap-2 font-bold">
                              <span className="flex items-center gap-1">
                                {ok ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> : <AlertCircle className="w-3.5 h-3.5 text-rose-500" />}
                                {isAr ? `تذكير قبل ${r.reminder_days} يوم` : `${r.reminder_days}d reminder`}
                              </span>
                              <span className={`text-[10px] font-mono ${ok ? "text-emerald-600" : "text-rose-600"}`}>
                                {ok ? (isAr ? "وصل ✅" : "Sent ✅") : (isAr ? "فشل ❌" : "Failed ❌")} · {formatCairoDateTime(r.sent_at || r.created_at, isAr)}
                              </span>
                            </div>
                            {!ok && r.error && (
                              <div className="text-[10px] font-mono text-rose-600 dark:text-rose-400 mt-1 break-all" dir="ltr">
                                {r.error}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="text-xs text-zinc-400 font-bold">{isAr ? "لا توجد محاولات تذكير تليجرام مسجلة" : "No Telegram reminders logged"}</p>
                  )}
                </div>

                <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900/60 p-3">
                  <h4 className="text-[11px] font-black uppercase text-zinc-600 dark:text-zinc-300 mb-2 flex items-center gap-1.5">
                    <Mail className="w-3.5 h-3.5 text-blue-500" />
                    {isAr ? "حملات البريد والتفاعل معها" : "Emails Sent & Engagement"}
                  </h4>
                  {emailLogs.length > 0 ? (
                    <div className="space-y-1.5 text-xs">
                      {emailLogs.map((em) => (
                        <div key={em.id} className="bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-800 p-2 flex items-center justify-between gap-2">
                          <div className="min-w-0">
                            <div className="font-mono font-bold truncate text-black dark:text-zinc-100" dir="ltr">
                              {em.message_type}
                            </div>
                            <div className="text-[10px] font-mono text-zinc-400">
                              {formatCairoDateTime(em.sent_at, isAr)}
                            </div>
                          </div>
                          <div className="flex items-center gap-1 shrink-0 text-[10px] font-black">
                            {em.opened && (
                              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-emerald-100 text-emerald-800 border border-emerald-400">
                                <Eye className="w-2.5 h-2.5" /> {isAr ? "فتح" : "Open"}
                              </span>
                            )}
                            {em.clicked && (
                              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-sky-100 text-sky-800 border border-sky-400">
                                <MousePointerClick className="w-2.5 h-2.5" /> {isAr ? "نقر" : "Click"}
                              </span>
                            )}
                            {em.bounced && (
                              <span className="px-1.5 py-0.5 bg-rose-100 text-rose-800 border border-rose-400">
                                {isAr ? "ارتد" : "Bounced"}
                              </span>
                            )}
                            {!em.opened && !em.clicked && !em.bounced && (
                              em.delivered ? (
                                <span className="px-1.5 py-0.5 bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 border border-zinc-300 dark:border-zinc-700">
                                  {isAr ? "وصل ولم يُفتح" : "Delivered"}
                                </span>
                              ) : String(em.status || "").toLowerCase() === "failed" ? (
                                <span className="px-1.5 py-0.5 bg-rose-100 text-rose-800 border border-rose-400">
                                  {isAr ? "فشل" : "Failed"}
                                </span>
                              ) : (
                                <span className="px-1.5 py-0.5 bg-amber-50 dark:bg-amber-950/50 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-700">
                                  {isAr ? "تم الإرسال" : "Sent"}
                                </span>
                              )
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-zinc-400 font-bold">{isAr ? "لا توجد رسائل بريد مسجلة" : "No marketing emails logged"}</p>
                  )}
                </div>
              </div>

              {/* Payment History */}
              {recentOrders.length > 0 && (
                <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900/60 p-3">
                  <h4 className="text-[11px] font-black uppercase text-zinc-600 dark:text-zinc-300 mb-2 flex items-center gap-1.5">
                    <CreditCard className="w-3.5 h-3.5 text-emerald-500" />
                    {isAr ? "سجل طلبات الدفع" : "Payment Orders"}
                  </h4>
                  <div className="space-y-1 text-xs font-mono">
                    {recentOrders.slice(0, 6).map((ord, idx) => (
                      <div key={idx} className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 py-1 gap-2">
                        <span className="text-black dark:text-zinc-100">
                          {ord.plan_id || "pro"} · {Number(ord.amount || 0).toLocaleString()} {isAr ? "ج.م" : "EGP"} ({ord.provider || "easykash"})
                        </span>
                        <span className={`font-black ${String(ord.status || "").toLowerCase() === "approved" ? "text-emerald-600" : "text-amber-600"}`}>
                          {ord.status} · {formatCairoDateTime(ord.created_at, isAr)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
