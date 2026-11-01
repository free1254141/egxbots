"use client";

import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import {
  Clock,
  Sparkles,
  Bot,
  CheckCircle2,
  AlertTriangle,
  Play,
  Trash2,
  Power,
  X,
  ExternalLink,
  Loader2,
  Calendar,
  Send,
  Plus,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useNotification } from "@/contexts/NotificationContext";
import { toast } from "sonner";
import Link from "next/link";

interface Automation {
  id: string;
  name: string;
  prompt: string;
  scheduled_time: string;
  days_of_week: string;
  telegram_chat_id: string | null;
  is_active: boolean;
  last_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
}

interface ScheduleAutomationModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialPrompt?: string;
  initialTitle?: string;
}

const TIME_PRESETS = [
  { label: "08:30 ص (قبل الجلسة)", time: "08:30" },
  { label: "10:30 ص (افتتاح التداول)", time: "10:30" },
  { label: "02:00 م (ملخص الإغلاق)", time: "14:00" },
  { label: "08:00 م (التحليل المسائي)", time: "20:00" },
];

export default function ScheduleAutomationModal({
  isOpen,
  onClose,
  initialPrompt = "",
  initialTitle = "",
}: ScheduleAutomationModalProps) {
  const { user } = useAuth();
  const { botUsername, telegramLinked, telegramChatId } = useNotification();

  const [mounted, setMounted] = useState(false);
  const [activeTab, setActiveTab] = useState<"create" | "manage">("create");
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [isPro, setIsPro] = useState(true);
  const [serverTelegramLinked, setServerTelegramLinked] = useState(false);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);

  // Form State
  const [name, setName] = useState(initialTitle || "");
  const [prompt, setPrompt] = useState(initialPrompt || "");
  const [scheduledTime, setScheduledTime] = useState("08:30");
  const [daysOfWeek, setDaysOfWeek] = useState<"all_days" | "trading_days">("all_days");
  const [customChatId, setCustomChatId] = useState("");

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (initialPrompt) {
      setPrompt(initialPrompt);
      if (!name) {
        const cleanPrompt = initialPrompt.replace(/[\n\r]+/g, " ").trim();
        setName(cleanPrompt.length > 25 ? `استشارة: ${cleanPrompt.slice(0, 25)}...` : `استشارة: ${cleanPrompt}`);
      }
    }
  }, [initialPrompt]);

  const loadAutomations = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/automations", { cache: "no-store" });
      const data = await res.json();
      if (res.ok) {
        setAutomations(data.automations || []);
        setIsPro(Boolean(data.is_pro));
        setServerTelegramLinked(Boolean(data.telegram_linked));
      }
    } catch {
      // silently ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadAutomations();
      // Lock body scroll on mobile
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  // Handle ESC key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !mounted) return null;

  const isTgConnected = telegramLinked || serverTelegramLinked;
  const tgConnectUrl = `https://t.me/${botUsername || "egxbots_bot"}?start=${user?.id || ""}`;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || prompt.trim().length < 3) {
      toast.error("يرجى كتابة نص السؤال أو الاستشارة بوضوح (3 أحرف على الأقل)");
      return;
    }

    if (!isTgConnected && !customChatId.trim()) {
      toast.error("يجب تفعيل وربط بوت تليجرام أولاً لاستلام الإجابة يومياً");
      return;
    }

    if (automations.length >= 5) {
      toast.error("وصلت للحد الأقصى (5 مهام). يمكنك تعديل أو حذف مهمة من تبويب الإدارة.");
      setActiveTab("manage");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch("/api/automations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim() || "استشارة مجدولة",
          prompt: prompt.trim(),
          scheduled_time: scheduledTime,
          days_of_week: daysOfWeek,
          telegram_chat_id: customChatId.trim() || null,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        toast.success("تمت جدولة الاستشارة بنجاح! سيصلك التحليل يومياً على تليجرام 🎯");
        await loadAutomations();
        setActiveTab("manage");
      } else {
        toast.error(data.error || "تعذر إنشاء الأتمتة المجدولة");
      }
    } catch {
      toast.error("حدث خطأ أثناء الاتصال بالخادم");
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggle = async (auto: Automation) => {
    try {
      const res = await fetch(`/api/automations/${auto.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !auto.is_active }),
      });
      const data = await res.json();
      if (res.ok) {
        setAutomations((prev) =>
          prev.map((a) => (a.id === auto.id ? { ...a, is_active: !auto.is_active } : a))
        );
        toast.success(!auto.is_active ? "تم تفعيل المهمة ✅" : "تم إيقاف المهمة مؤقتاً ⏸️");
      } else {
        toast.error(data.error || "فشل تغيير الحالة");
      }
    } catch {
      toast.error("تعذر تحديث الحالة");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("هل أنت متأكد من حذف هذه الاستشارة المجدولة؟")) return;
    try {
      const res = await fetch(`/api/automations/${id}`, { method: "DELETE" });
      if (res.ok) {
        setAutomations((prev) => prev.filter((a) => a.id !== id));
        toast.success("تم حذف المهمة المجدولة بنجاح");
      } else {
        toast.error("فشل حذف المهمة");
      }
    } catch {
      toast.error("خطأ أثناء الحذف");
    }
  };

  const handleTestRun = async (id: string) => {
    setTestingId(id);
    try {
      const res = await fetch(`/api/automations/${id}/test`, { method: "POST" });
      const data = await res.json();
      if (res.ok && data.ok) {
        toast.success("تم إرسال استشارة تجريبية فورياً إلى تليجرام! تفقد هاتفك 📱");
        loadAutomations();
      } else {
        const reason =
          data.error === "pro_required" || data.detail === "pro_required"
            ? "هذه الميزة تتطلب اشتراك Pro نشط."
            : data.error || data.detail || "فشل إرسال التجربة، تأكد من ربط البوت وباقة Pro";
        toast.error(reason);
      }
    } catch {
      toast.error("تعذر تنفيذ التشغيل التجريبي");
    } finally {
      setTestingId(null);
    }
  };

  const modalContent = (
    <div
      className="fixed inset-0 z-[9999999] flex items-center justify-center bg-black/85 backdrop-blur-md p-2 sm:p-4 animate-in fade-in duration-200"
      onClick={onClose}
      dir="rtl"
    >
      <div
        className="relative w-full max-w-xl max-h-[94vh] sm:max-h-[90vh] bg-white dark:bg-zinc-950 border-3 sm:border-4 border-black dark:border-white shadow-[6px_6px_0_0_#000] dark:shadow-[6px_6px_0_0_#FFE600] flex flex-col overflow-hidden rounded-xl sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Fixed Header */}
        <div className="relative px-4 py-3 sm:px-6 sm:py-4 border-b-3 sm:border-b-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900/80 flex items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            <div className="w-10 h-10 sm:w-11 sm:h-11 bg-[#FFE600] text-black border-2 sm:border-3 border-black dark:border-white flex items-center justify-center shadow-[2px_2px_0_0_#000] shrink-0">
              <Clock className="w-5 h-5 sm:w-6 sm:h-6 stroke-[2.5]" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-base sm:text-lg font-black text-black dark:text-white truncate">
                  أتمتة استشارات أرتورو الذكية
                </h3>
                <span className="bg-sky-400 text-black text-[10px] font-black px-1.5 py-0.5 border border-black uppercase tracking-wider">
                  PRO
                </span>
              </div>
              <p className="text-[11px] sm:text-xs text-zinc-600 dark:text-zinc-400 font-bold truncate">
                استشارات يومية تلقائية تصلك على تليجرام في الموعد الذي تختاره
              </p>
            </div>
          </div>

          {/* Close button */}
          <button
            onClick={onClose}
            type="button"
            className="p-1.5 sm:p-2 border-2 border-black dark:border-white bg-[#FFE600] hover:bg-yellow-400 text-black font-black shadow-[2px_2px_0_0_#000] active:translate-x-0.5 active:translate-y-0.5 transition-all cursor-pointer shrink-0"
            title="إغلاق النافذة"
          >
            <X className="w-4 h-4 sm:w-5 sm:h-5 stroke-[2.5]" />
          </button>
        </div>

        {/* Navigation Tabs (Mobile Optimized) */}
        <div className="px-4 pt-3 pb-2 sm:px-6 bg-zinc-100 dark:bg-zinc-900 border-b-2 border-zinc-200 dark:border-zinc-800 flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setActiveTab("create")}
            className={`flex-1 py-2 px-2 text-xs font-black border-2 border-black dark:border-white transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
              activeTab === "create"
                ? "bg-[#FFE600] text-black shadow-[2px_2px_0_0_#000] translate-x-0.5 translate-y-0.5"
                : "bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50"
            }`}
          >
            <Plus className="w-3.5 h-3.5" />
            <span>جدولة استشارة</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("manage")}
            className={`flex-1 py-2 px-2 text-xs font-black border-2 border-black dark:border-white transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
              activeTab === "manage"
                ? "bg-[#FFE600] text-black shadow-[2px_2px_0_0_#000] translate-x-0.5 translate-y-0.5"
                : "bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50"
            }`}
          >
            <Bot className="w-3.5 h-3.5" />
            <span>مهامي ({automations.length}/5)</span>
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 text-right">
          {/* Telegram Warning Banner */}
          {!isTgConnected && (
            <div className="p-3 bg-amber-50 dark:bg-amber-950/40 border-2 border-amber-500 rounded-lg flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2.5 text-amber-900 dark:text-amber-200 text-xs">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <p className="font-black text-xs sm:text-sm">بوت تليجرام غير مفعل</p>
                  <p className="font-bold text-[11px] sm:text-xs text-zinc-700 dark:text-zinc-300">
                    يلزم ربط البوت أولاً لاستلام التقارير اليومية في موعدها.
                  </p>
                </div>
              </div>
              <a
                href={tgConnectUrl}
                target="_blank"
                rel="noreferrer"
                className="w-full sm:w-auto px-3 py-1.5 bg-[#0088cc] hover:bg-[#0077b5] text-white font-black text-xs border-2 border-black shadow-[2px_2px_0_0_#000] flex items-center justify-center gap-1.5 shrink-0"
              >
                <Send className="w-3.5 h-3.5" />
                <span>ربط البوت الآن</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          )}

          {/* TAB 1: Create Form */}
          {activeTab === "create" && (
            <form onSubmit={handleCreate} className="space-y-3.5 sm:space-y-4">
              {/* Title / Name */}
              <div>
                <label className="block text-xs font-black text-zinc-800 dark:text-zinc-200 mb-1">
                  اسم أو عنوان المهمة:
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="مثال: متابعة سهم بلتون الصباحية"
                  maxLength={80}
                  className="w-full p-2.5 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-white font-bold text-sm sm:text-base text-black dark:text-white outline-none rounded-lg focus:bg-yellow-50 dark:focus:bg-zinc-800 transition-colors"
                />
              </div>

              {/* Prompt Textarea */}
              <div>
                <label className="block text-xs font-black text-zinc-800 dark:text-zinc-200 mb-1">
                  نص السؤال المطلوب سؤاله للبوت يومياً:
                </label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={3}
                  placeholder="اكتب السؤال أو التحليل المطلوب..."
                  className="w-full p-2.5 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-white font-bold text-sm sm:text-base text-black dark:text-white outline-none rounded-lg focus:bg-yellow-50 dark:focus:bg-zinc-800 resize-none leading-relaxed transition-colors"
                  required
                />
              </div>

              {/* Time Picker & Presets (Mobile Grid) */}
              <div className="space-y-1.5">
                <label className="block text-xs font-black text-zinc-800 dark:text-zinc-200">
                  ⏰ موعد الإرسال اليومي (بتوقيت القاهرة 🇪🇬):
                </label>
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                  <input
                    type="time"
                    value={scheduledTime}
                    onChange={(e) => setScheduledTime(e.target.value)}
                    className="p-2 sm:p-2.5 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-white font-mono font-black text-sm text-black dark:text-white outline-none rounded-lg text-center shrink-0"
                    required
                  />
                  <div className="grid grid-cols-2 gap-1.5 flex-1">
                    {TIME_PRESETS.map((p) => (
                      <button
                        key={p.time}
                        type="button"
                        onClick={() => setScheduledTime(p.time)}
                        className={`py-1.5 px-2 text-[11px] sm:text-xs font-bold border-2 transition-all rounded-md truncate cursor-pointer ${
                          scheduledTime === p.time
                            ? "bg-[#FFE600] text-black border-black font-black shadow-[1px_1px_0_0_#000]"
                            : "bg-zinc-100 dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 border-zinc-300 dark:border-zinc-700 hover:border-black"
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Days of Week (Mobile Responsive Stack) */}
              <div>
                <label className="block text-xs font-black text-zinc-800 dark:text-zinc-200 mb-1">
                  📅 أيام التشغيل والتكرار:
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setDaysOfWeek("all_days")}
                    className={`p-2.5 sm:p-3 border-2 text-right text-xs transition-all rounded-lg cursor-pointer ${
                      daysOfWeek === "all_days"
                        ? "bg-[#FFE600] text-black border-black shadow-[2px_2px_0_0_#000] font-black"
                        : "bg-zinc-50 dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 border-zinc-300 dark:border-zinc-700 hover:border-black font-bold"
                    }`}
                  >
                    <p className="font-black text-xs">☀️ يومياً (طوال الأسبوع - 7 أيام)</p>
                    <p className="text-[10px] opacity-80 mt-0.5">يعمل كل يوم بما فيه الجمعة والسبت والعطلات</p>
                  </button>

                  <button
                    type="button"
                    onClick={() => setDaysOfWeek("trading_days")}
                    className={`p-2.5 sm:p-3 border-2 text-right text-xs transition-all rounded-lg cursor-pointer ${
                      daysOfWeek === "trading_days"
                        ? "bg-[#FFE600] text-black border-black shadow-[2px_2px_0_0_#000] font-black"
                        : "bg-zinc-50 dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 border-zinc-300 dark:border-zinc-700 hover:border-black font-bold"
                    }`}
                  >
                    <p className="font-black text-xs">🏛️ أيام جلسات البورصة (الأحد - الخميس)</p>
                    <p className="text-[10px] opacity-80 mt-0.5">يعمل في أيام التداول فقط ويتوقف في العطلات</p>
                  </button>
                </div>
              </div>

              {/* Quota Info Box */}
              <div className="p-2.5 bg-zinc-100 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-800 rounded-lg text-[11px] font-bold text-zinc-600 dark:text-zinc-400">
                💡 <span className="font-black text-black dark:text-white">الخصم من الكوتا:</span> يتم استهلاك رسالة واحدة فقط عند تشغيل الاستشارة وإرسالها لتليجرام يومياً في موعدها.
              </div>

              {/* Submit Button */}
              <div className="pt-1">
                <button
                  type="submit"
                  disabled={submitting || automations.length >= 5 || (!isTgConnected && !customChatId)}
                  className="w-full py-3 bg-[#FFE600] hover:bg-yellow-300 disabled:opacity-50 text-black font-black text-xs sm:text-sm border-2 sm:border-3 border-black dark:border-white shadow-[3px_3px_0_0_#000] dark:shadow-[3px_3px_0_0_#fff] cursor-pointer flex items-center justify-center gap-2 active:translate-x-0.5 active:translate-y-0.5 transition-all rounded-xl"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>جاري حفظ الأتمتة...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4 stroke-[2.5]" />
                      <span>تأكيد وجدولة الاستشارة اليومية ({automations.length}/5)</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          {/* TAB 2: Manage Automations */}
          {activeTab === "manage" && (
            <div className="space-y-3">
              {loading ? (
                <div className="py-12 text-center text-xs font-bold text-zinc-500 flex items-center justify-center gap-2">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>جاري تحميل المهام المجدولة...</span>
                </div>
              ) : automations.length === 0 ? (
                <div className="py-10 text-center border-2 border-dashed border-zinc-300 dark:border-zinc-700 p-6 space-y-2 rounded-xl">
                  <Bot className="w-10 h-10 text-zinc-400 mx-auto" />
                  <p className="font-black text-sm text-black dark:text-white">لا توجد مهام أتمتة مجدولة حتى الآن</p>
                  <p className="text-xs text-zinc-500 font-bold">يمكنك إضافة ما يصل إلى 5 مهام يومية مجدولة.</p>
                  <button
                    type="button"
                    onClick={() => setActiveTab("create")}
                    className="mt-3 px-4 py-2 bg-[#FFE600] text-black font-black text-xs border-2 border-black shadow-[2px_2px_0_0_#000] inline-flex items-center gap-1.5 rounded-lg"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>جدولة أول استشارة الآن</span>
                  </button>
                </div>
              ) : (
                <div className="space-y-2.5">
                  {automations.map((auto) => (
                    <div
                      key={auto.id}
                      className="p-3 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-white shadow-[2px_2px_0_0_#000] dark:shadow-[2px_2px_0_0_#fff] flex flex-col gap-2 rounded-xl"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                            <h4 className="font-black text-xs sm:text-sm text-black dark:text-white truncate">
                              {auto.name}
                            </h4>
                            <span
                              className={`text-[10px] font-mono font-black px-1.5 py-0.5 rounded border ${
                                auto.is_active
                                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                                  : "bg-zinc-200 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 border-zinc-300"
                              }`}
                            >
                              {auto.is_active ? "نشط 🟢" : "متوقف ⏸️"}
                            </span>
                          </div>
                          <p className="text-[11px] font-mono font-bold text-zinc-500 mt-1 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            <span>{auto.scheduled_time} بتوقيت القاهرة</span>
                            <span>• {auto.days_of_week === "all_days" ? "يومياً" : "أيام التداول"}</span>
                          </p>
                          <p className="text-xs text-zinc-600 dark:text-zinc-400 font-medium line-clamp-2 mt-1">
                            {auto.prompt}
                          </p>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex items-center gap-1.5 shrink-0">
                          {/* Toggle Power */}
                          <button
                            type="button"
                            onClick={() => handleToggle(auto)}
                            className={`p-2 border border-black dark:border-white text-xs font-bold transition-all rounded-lg cursor-pointer ${
                              auto.is_active
                                ? "bg-emerald-500 text-white"
                                : "bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300"
                            }`}
                            title={auto.is_active ? "إيقاف مؤقت" : "تفعيل"}
                          >
                            <Power className="w-3.5 h-3.5" />
                          </button>

                          {/* Test Run */}
                          <button
                            type="button"
                            onClick={() => handleTestRun(auto.id)}
                            disabled={testingId === auto.id}
                            className="px-2.5 py-1.5 bg-[#67E8F9] hover:bg-cyan-300 text-black font-black text-xs border border-black shadow-[1px_1px_0_0_#000] flex items-center gap-1 cursor-pointer disabled:opacity-50 rounded-lg"
                            title="تجربة الإرسال على تليجرام فوراً"
                          >
                            {testingId === auto.id ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Play className="w-3.5 h-3.5" />
                            )}
                            <span>تجربة</span>
                          </button>

                          {/* Delete */}
                          <button
                            type="button"
                            onClick={() => handleDelete(auto.id)}
                            className="p-2 bg-rose-500 text-white border border-black hover:bg-rose-600 cursor-pointer rounded-lg"
                            title="حذف المهمة"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>

                      {/* Status footer */}
                      {auto.last_run_at && (
                        <div className="text-[10px] font-mono text-zinc-500 pt-1.5 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
                          <span>آخر تشغيل: {new Date(auto.last_run_at).toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" })}</span>
                          <span className={auto.last_status === "success" ? "text-emerald-500 font-bold" : "text-amber-500 font-bold"}>
                            {auto.last_status === "success" ? "تم الإرسال بنجاح ✅" : auto.last_status}
                          </span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}
