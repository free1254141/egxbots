"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  Bot,
  CheckCircle2,
  Crown,
  Flame,
  Loader2,
  MessageSquare,
  PieChart,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  Users,
  X,
} from "lucide-react";
import { toast } from "sonner";
import type { ChatterLeaderRow, UsersEngagementSummary } from "@/lib/admin/engagement-segments";
import FounderUserUsageDialog, { type UsageDialogUserSummary } from "./FounderUserUsageDialog";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onFilterUser?: (email: string) => void;
  isAr?: boolean;
}

export default function UsersEngagementModal({
  isOpen,
  onClose,
  onFilterUser,
  isAr = true,
}: Props) {
  const [data, setData] = useState<UsersEngagementSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [leaderTab, setLeaderTab] = useState<"monthly" | "all_time">("monthly");
  const [selectedUser, setSelectedUser] = useState<UsageDialogUserSummary | null>(null);

  const loadEngagement = useCallback(async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetch("/api/admin/users/engagement", { cache: "no-store" });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(json.detail || json.error || "Failed to load engagement analytics");
      }
      setData(json as UsersEngagementSummary);
    } catch (err: any) {
      const msg = err?.message || (isAr ? "تعذر تحميل إحصائيات الاهتمامات وحد الـ 350" : "Failed to load engagement stats");
      setErrorMsg(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [isAr]);

  useEffect(() => {
    if (isOpen) {
      void loadEngagement();
    }
  }, [isOpen, loadEngagement]);

  if (!isOpen) return null;

  const openChatterUsage = (row: ChatterLeaderRow) => {
    setSelectedUser({
      user_id: row.user_id,
      email: row.email,
      display_name: row.display_name,
      badge_label: row.is_active_paid
        ? isAr ? "مشترك Pro نشط" : "Active Pro"
        : row.is_paid_ever
        ? isAr ? "دفع سابقاً" : "Past Paid"
        : isAr ? "مجاني / تجريبي" : "Free / Trial",
    });
  };

  const limit350 = data?.chat_limit_350;
  const activeLeaderList = leaderTab === "monthly"
    ? limit350?.top_monthly_chatters || []
    : limit350?.top_all_time_chatters || [];

  return (
    <div
      dir={isAr ? "rtl" : "ltr"}
      role="dialog"
      aria-modal="true"
      aria-label={isAr ? "تحليل اهتمامات المستخدمين وحد الـ 350 شات" : "User Engagement & 350 Chat Limit"}
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/75 backdrop-blur-xs animate-in fade-in duration-150"
    >
      <div className="relative w-full max-w-6xl max-h-[92vh] flex flex-col border-4 border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[8px_8px_0px_rgba(0,0,0,1)] dark:shadow-[8px_8px_0px_rgba(255,255,255,1)]">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 p-4 sm:p-5 border-b-4 border-black dark:border-white bg-sky-100 dark:bg-sky-950/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 border-2 border-black dark:border-white bg-sky-400 text-black flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)]">
              <PieChart className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base sm:text-lg font-black uppercase tracking-wider text-black dark:text-white flex items-center gap-2">
                {isAr ? "اهتمامات المستخدمين وحد الـ 350 رسالة شهرياً" : "User Interests & 350/mo Chat Cap Analytics"}
                {data && (
                  <span className="text-xs px-2 py-0.5 border border-black dark:border-white bg-sky-400 text-black font-mono">
                    {data.total_users}
                  </span>
                )}
              </h2>
              <p className="text-xs text-zinc-700 dark:text-zinc-300 font-bold mt-0.5">
                {isAr
                  ? "توزيع الاهتمام بالشات AI مقابل التوصيات والماسحات والمشتركين، والتحقق الحي من الوصول لسقف 350 رسالة/شهر"
                  : "Segmentation of AI Chat vs Recommendations/Scanners vs Subscribers, and monthly 350-message ceiling monitor"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void loadEngagement()}
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
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5">
          {loading && !data ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-zinc-500 font-bold text-sm">
              <Loader2 className="w-8 h-8 animate-spin text-sky-500" />
              <span>{isAr ? "جاري تحليل اهتمامات المستخدمين وسجل الشات..." : "Analyzing user engagement & 350/mo usage..."}</span>
            </div>
          ) : errorMsg && !data ? (
            <div className="border-2 border-red-500 bg-red-50 dark:bg-red-950/30 p-4 text-sm font-bold text-red-700 dark:text-red-300 flex items-center justify-between gap-3">
              <span>{errorMsg}</span>
              <button
                type="button"
                onClick={() => void loadEngagement()}
                className="px-3 py-1.5 bg-red-600 text-white text-xs font-black border border-black"
              >
                {isAr ? "إعادة المحاولة" : "Retry"}
              </button>
            </div>
          ) : data && limit350 ? (
            <>
              {/* 350 Monthly Limit Highlight Banner */}
              <div
                className={`border-4 border-black dark:border-white p-4 flex flex-col lg:flex-row lg:items-center justify-between gap-4 shadow-[4px_4px_0px_rgba(0,0,0,1)] ${
                  limit350.hit_350_months_count === 0
                    ? "bg-emerald-50 dark:bg-emerald-950/30"
                    : "bg-amber-50 dark:bg-amber-950/30"
                }`}
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    {limit350.hit_350_months_count === 0 ? (
                      <ShieldCheck className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                    ) : (
                      <Flame className="w-5 h-5 text-orange-600" />
                    )}
                    <h3 className="text-sm sm:text-base font-black text-black dark:text-white">
                      {limit350.hit_350_months_count === 0
                        ? isAr
                          ? "هل وصل أحد لحد الـ 350 رسالة شهرياً؟ لا — لم يصل أي مستخدم (0)"
                          : "Has anyone hit 350 chats/month? No — 0 users"
                        : isAr
                        ? `وصول لحد 350 رسالة/شهر: ${limit350.users_ever_hit_350_count} مستخدم (${limit350.hit_350_months_count} شهر)`
                        : `${limit350.users_ever_hit_350_count} user(s) hit 350/mo (${limit350.hit_350_months_count} months)`}
                    </h3>
                  </div>
                  <p className="text-xs font-bold text-zinc-700 dark:text-zinc-300">
                    {limit350.max_month_leader ? (
                      isAr
                        ? `أعلى استهلاك شهري تاريخياً: ${limit350.max_month_chats_ever} رسالة (${Math.round((limit350.max_month_chats_ever / 350) * 1000) / 10}% من حد 350) بواسطة ${limit350.max_month_leader.email} في شهر ${limit350.max_month_leader.month} · وأعلى رسائل محفوظة شهرياً: ${limit350.max_month_messages_ever}`
                        : `Highest monthly peak ever: ${limit350.max_month_chats_ever} chats by ${limit350.max_month_leader.email} (${limit350.max_month_leader.month})`
                    ) : isAr ? "لا توجد بيانات استخدام مسجلة بعد" : "No chat usage recorded yet"}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3 shrink-0">
                  <div className="border-2 border-black dark:border-white bg-white dark:bg-zinc-900 px-3 py-2 text-center">
                    <div className="text-[10px] font-black text-zinc-500">{isAr ? "وصلوا لـ 350+" : "Hit 350+"}</div>
                    <div className="text-xl font-black font-mono text-black dark:text-white">{limit350.users_ever_hit_350_count}</div>
                  </div>
                  <div className="border-2 border-black dark:border-white bg-white dark:bg-zinc-900 px-3 py-2 text-center">
                    <div className="text-[10px] font-black text-zinc-500">{isAr ? "أعلى شهر مسجل" : "Peak Month"}</div>
                    <div className="text-xl font-black font-mono text-sky-600 dark:text-sky-400">
                      {limit350.max_month_chats_ever} / 350
                    </div>
                  </div>
                  <div className="border-2 border-black dark:border-white bg-white dark:bg-zinc-900 px-3 py-2 text-center">
                    <div className="text-[10px] font-black text-zinc-500">{isAr ? "فوق 50 رسالة/شهر" : "50+ / mo"}</div>
                    <div className="text-xl font-black font-mono text-amber-600 dark:text-amber-400">
                      {limit350.approached_50_users_count}
                    </div>
                  </div>
                </div>
              </div>

              {/* 4 Headline Interest & Subscriber Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900 p-3.5">
                  <div className="flex items-center justify-between text-[11px] font-black text-zinc-600 dark:text-zinc-400">
                    <span>{isAr ? "إجمالي المستخدمين" : "Total Users"}</span>
                    <Users className="w-4 h-4" />
                  </div>
                  <div className="text-2xl font-black font-mono mt-1 text-black dark:text-white">
                    {data.total_users}
                  </div>
                  <div className="text-[10px] font-bold text-zinc-500 mt-1">
                    {isAr
                      ? `تجربة مجانية نشطة الآن: ${data.subscribers.active_trial_count} (${data.subscribers.active_trial_pct}%)`
                      : `Active trials: ${data.subscribers.active_trial_count} (${data.subscribers.active_trial_pct}%)`}
                  </div>
                </div>

                <div className="border-2 border-black dark:border-white bg-amber-50 dark:bg-amber-950/30 p-3.5">
                  <div className="flex items-center justify-between text-[11px] font-black text-amber-800 dark:text-amber-300">
                    <span>{isAr ? "المشتركون المدفوعون" : "Paid Subscribers"}</span>
                    <Crown className="w-4 h-4" />
                  </div>
                  <div className="text-2xl font-black font-mono mt-1 text-amber-950 dark:text-amber-100">
                    {data.subscribers.active_paid_pct}%{" "}
                    <span className="text-sm font-bold text-amber-700 dark:text-amber-300">
                      ({data.subscribers.active_paid_count} {isAr ? "نشط" : "active"})
                    </span>
                  </div>
                  <div className="text-[10px] font-bold text-amber-800 dark:text-amber-300 mt-1">
                    {isAr
                      ? `دفعوا إجمالاً (نشط + سابق): ${data.subscribers.paid_ever_count} (${data.subscribers.paid_ever_pct}%)`
                      : `Paid ever: ${data.subscribers.paid_ever_count} (${data.subscribers.paid_ever_pct}%)`}
                  </div>
                </div>

                <div className="border-2 border-black dark:border-white bg-sky-50 dark:bg-sky-950/30 p-3.5">
                  <div className="flex items-center justify-between text-[11px] font-black text-sky-800 dark:text-sky-300">
                    <span>{isAr ? "المهتمون بالشات AI" : "AI Chat Interested"}</span>
                    <MessageSquare className="w-4 h-4" />
                  </div>
                  <div className="text-2xl font-black font-mono mt-1 text-sky-950 dark:text-sky-100">
                    {data.interests.chat_interested_pct}%{" "}
                    <span className="text-sm font-bold text-sky-700 dark:text-sky-300">
                      ({data.interests.chat_interested_count})
                    </span>
                  </div>
                  <div className="text-[10px] font-bold text-sky-800 dark:text-sky-300 mt-1">
                    {isAr
                      ? `أرسلوا رسائل فعلاً: ${data.interests.chat_messaged_count} (${data.interests.chat_messaged_pct}%)`
                      : `Sent >=1 msg: ${data.interests.chat_messaged_count} (${data.interests.chat_messaged_pct}%)`}
                  </div>
                </div>

                <div className="border-2 border-black dark:border-white bg-emerald-50 dark:bg-emerald-950/30 p-3.5">
                  <div className="flex items-center justify-between text-[11px] font-black text-emerald-800 dark:text-emerald-300">
                    <span>{isAr ? "المهتمون بالتوصيات والماسحات" : "Recommendations Interested"}</span>
                    <TrendingUp className="w-4 h-4" />
                  </div>
                  <div className="text-2xl font-black font-mono mt-1 text-emerald-950 dark:text-emerald-100">
                    {data.interests.recs_interested_pct}%{" "}
                    <span className="text-sm font-bold text-emerald-700 dark:text-emerald-300">
                      ({data.interests.recs_interested_count})
                    </span>
                  </div>
                  <div className="text-[10px] font-bold text-emerald-800 dark:text-emerald-300 mt-1">
                    {isAr
                      ? `الويب: ${data.interests.recs_web_scanner_count} · بوتات/VIP: ${data.interests.recs_bot_or_vip_count}`
                      : `Web: ${data.interests.recs_web_scanner_count} · Bot/VIP: ${data.interests.recs_bot_or_vip_count}`}
                  </div>
                </div>
              </div>

              {/* Overlap Breakdown + Subscribers Overlap + Peak Distribution */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* 4-Way Mutually Exclusive Interest Matrix */}
                <div className="border-2 border-black dark:border-white p-4 bg-white dark:bg-zinc-900 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-black uppercase text-black dark:text-white flex items-center gap-1.5">
                      <Bot className="w-4 h-4 text-sky-600" />
                      {isAr ? "تقسيم التداخل بين الشات والتوصيات (100% من المستخدمين)" : "Chat vs Recommendations Overlap Matrix"}
                    </h3>
                  </div>

                  <div className="space-y-2.5">
                    {[
                      {
                        label: isAr ? "مهتم بالشات + التوصيات معاً" : "Both Chat & Recs",
                        count: data.overlap.both_count,
                        pct: data.overlap.both_pct,
                        bar: "bg-violet-500",
                      },
                      {
                        label: isAr ? "مهتم بالشات AI فقط" : "AI Chat Only",
                        count: data.overlap.chat_only_count,
                        pct: data.overlap.chat_only_pct,
                        bar: "bg-sky-500",
                      },
                      {
                        label: isAr ? "مهتم بالتوصيات والماسحات فقط" : "Recommendations Only",
                        count: data.overlap.recs_only_count,
                        pct: data.overlap.recs_only_pct,
                        bar: "bg-emerald-500",
                      },
                      {
                        label: isAr ? "مسجل دون تفاعل مسجل في الشات أو التوصيات" : "Registered / Passive",
                        count: data.overlap.neither_count,
                        pct: data.overlap.neither_pct,
                        bar: "bg-zinc-400",
                      },
                    ].map((seg) => (
                      <div key={seg.label} className="space-y-1">
                        <div className="flex items-center justify-between text-xs font-bold text-black dark:text-white">
                          <span>{seg.label}</span>
                          <span className="font-mono">
                            {seg.count} ({seg.pct}%)
                          </span>
                        </div>
                        <div className="h-2.5 w-full bg-zinc-200 dark:bg-zinc-800 border border-black/30 dark:border-white/20 overflow-hidden">
                          <div className={`h-full ${seg.bar}`} style={{ width: `${Math.min(100, seg.pct)}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Inside Paid Subscribers Box */}
                  <div className="border-t-2 border-dashed border-zinc-300 dark:border-zinc-700 pt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] font-bold">
                    <span className="text-black dark:text-white flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      {isAr ? "داخل المشتركين النشطين:" : "Among Active Pro:"}
                    </span>
                    <div className="flex flex-wrap gap-2 font-mono">
                      <span className="px-2 py-0.5 bg-sky-100 dark:bg-sky-950 text-sky-800 dark:text-sky-200 border border-sky-400">
                        {isAr ? `شات: ${data.paid_breakdown.active_paid_chat_pct}% (${data.paid_breakdown.active_paid_chat_count})` : `Chat: ${data.paid_breakdown.active_paid_chat_pct}%`}
                      </span>
                      <span className="px-2 py-0.5 bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-200 border border-emerald-400">
                        {isAr ? `توصيات: ${data.paid_breakdown.active_paid_recs_pct}% (${data.paid_breakdown.active_paid_recs_count})` : `Recs: ${data.paid_breakdown.active_paid_recs_pct}%`}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Peak Monthly Usage Distribution vs 350 Limit */}
                <div className="border-2 border-black dark:border-white p-4 bg-white dark:bg-zinc-900 space-y-3">
                  <h3 className="text-xs font-black uppercase text-black dark:text-white flex items-center gap-1.5">
                    <Activity className="w-4 h-4 text-amber-500" />
                    {isAr ? "توزيع أعلى استهلاك شهري لكل مستخدم (مقارنة بحد 350)" : "Peak Monthly Chat Distribution vs 350 Cap"}
                  </h3>
                  <div className="space-y-2">
                    {limit350.peak_buckets.map((b) => (
                      <div key={b.id} className="space-y-1">
                        <div className="flex items-center justify-between text-xs font-bold text-black dark:text-white">
                          <span>{isAr ? b.label_ar : b.label_en}</span>
                          <span className="font-mono">
                            {b.count} {isAr ? "مستخدم" : "users"} ({b.pct}%)
                          </span>
                        </div>
                        <div className="h-2.5 w-full bg-zinc-200 dark:bg-zinc-800 border border-black/30 dark:border-white/20 overflow-hidden">
                          <div
                            className={`h-full ${b.id === "350_plus" ? "bg-rose-600" : b.id === "151_349" ? "bg-amber-500" : "bg-sky-500"}`}
                            style={{ width: `${Math.min(100, b.pct)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Top Heavy Chatters Leaderboard */}
              <div className="border-2 border-black dark:border-white">
                <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-zinc-100 dark:bg-zinc-900 border-b-2 border-black dark:border-white">
                  <h3 className="text-xs font-black text-black dark:text-white">
                    {isAr ? "أعلى المستخدمين استهلاكاً للشات (اضغط لفتح تفاصيل الاستخدام)" : "Top AI Chat Users (click row for full usage)"}
                  </h3>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setLeaderTab("monthly")}
                      className={`px-2.5 py-1 text-[11px] font-black border border-black dark:border-white cursor-pointer ${
                        leaderTab === "monthly" ? "bg-sky-400 text-black" : "bg-white dark:bg-zinc-950 text-black dark:text-white"
                      }`}
                    >
                      {isAr ? "أعلى استهلاك في شهر واحد" : "Peak Single Month"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setLeaderTab("all_time")}
                      className={`px-2.5 py-1 text-[11px] font-black border border-black dark:border-white cursor-pointer ${
                        leaderTab === "all_time" ? "bg-sky-400 text-black" : "bg-white dark:bg-zinc-950 text-black dark:text-white"
                      }`}
                    >
                      {isAr ? "الإجمالي التراكمي" : "All-Time Total"}
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-start border-collapse">
                    <thead className="bg-zinc-50 dark:bg-zinc-900/60 border-b border-zinc-300 dark:border-zinc-700 text-[11px] font-black text-zinc-700 dark:text-zinc-300">
                      <tr>
                        <th className="p-2.5 text-start">#</th>
                        <th className="p-2.5 text-start">{isAr ? "المستخدم" : "User"}</th>
                        <th className="p-2.5 text-center">{isAr ? "الاشتراك" : "Plan"}</th>
                        <th className="p-2.5 text-center">{isAr ? "الشهر الذروة" : "Peak Month"}</th>
                        <th className="p-2.5 text-center">{isAr ? "رسائل الشهر (% من 350)" : "Month Chats (% of 350)"}</th>
                        <th className="p-2.5 text-center">{isAr ? "الإجمالي الكلي" : "All-Time"}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800 bg-white dark:bg-zinc-950">
                      {activeLeaderList.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="p-6 text-center text-zinc-400 font-bold">
                            {isAr ? "لا توجد رسائل مسجلة بعد" : "No chat usage yet"}
                          </td>
                        </tr>
                      ) : (
                        activeLeaderList.map((row, idx) => (
                          <tr
                            key={`${row.user_id}-${row.month}-${idx}`}
                            onClick={() => openChatterUsage(row)}
                            className="hover:bg-sky-50/70 dark:hover:bg-sky-950/30 cursor-pointer transition-colors"
                          >
                            <td className="p-2.5 font-mono font-bold text-zinc-500">{idx + 1}</td>
                            <td className="p-2.5">
                              <div className="font-mono font-bold text-black dark:text-white">{row.email}</div>
                              {row.display_name && <div className="text-[10px] text-zinc-500">{row.display_name}</div>}
                            </td>
                            <td className="p-2.5 text-center">
                              {row.is_active_paid ? (
                                <span className="px-2 py-0.5 text-[10px] font-black border border-black bg-emerald-400 text-black">
                                  {isAr ? "مشترك Pro نشط" : "Active Pro"}
                                </span>
                              ) : row.is_paid_ever ? (
                                <span className="px-2 py-0.5 text-[10px] font-black border border-black bg-amber-300 text-black">
                                  {isAr ? "دفع سابقاً" : "Past Paid"}
                                </span>
                              ) : (
                                <span className="px-2 py-0.5 text-[10px] font-black border border-zinc-400 bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300">
                                  {isAr ? "مجاني / تجربة" : "Free / Trial"}
                                </span>
                              )}
                            </td>
                            <td className="p-2.5 text-center font-mono font-bold">{row.month}</td>
                            <td className="p-2.5 text-center">
                              <div className="font-mono font-black text-black dark:text-white">
                                {row.month_chats}{" "}
                                <span className="text-[10px] text-sky-600 dark:text-sky-400">({row.pct_of_350}%)</span>
                              </div>
                            </td>
                            <td className="p-2.5 text-center font-mono font-black text-zinc-700 dark:text-zinc-300">
                              {row.all_time_chats}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>

      {/* Stacked User Usage Dialog on top when clicking any chatter */}
      <FounderUserUsageDialog
        userSummary={selectedUser}
        onClose={() => setSelectedUser(null)}
        onJumpToTable={(email) => {
          setSelectedUser(null);
          onFilterUser?.(email);
        }}
        isAr={isAr}
      />
    </div>
  );
}
