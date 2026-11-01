"use client";

import React, { useState, useEffect } from "react";
import {
  Clock,
  Bot,
  Play,
  Trash2,
  Edit3,
  Plus,
  Send,
  CheckCircle2,
  AlertTriangle,
  Power,
  Sparkles,
  RefreshCw,
  X,
  ExternalLink,
} from "lucide-react";
import Link from "next/link";

interface Automation {
  id: string;
  user_id: string;
  name: string;
  prompt: string;
  scheduled_time: string;
  days_of_week: string;
  telegram_chat_id: string | null;
  is_active: boolean;
  last_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  created_at: string;
}

interface Props {
  isPro?: boolean;
  language?: string;
  telegramLinked?: boolean;
  onQuotaConsumed?: () => void;
}

const PRESET_PROMPTS = [
  {
    title: "ملخص ما قبل الجلسة",
    prompt: "ما هو ملخص وضع السوق اليوم وأهم الأخبار ومستويات الدعم والمقاومة للأسهم القيادية؟",
    defaultTime: "08:30",
  },
  {
    title: "أسهم السيولة والزخم",
    prompt: "إيه أقوى الأسهم اللي بتجمع سيولة ذكية وأحجام تداول متزايدة اليوم مع مناطق الدخول الآمنة؟",
    defaultTime: "10:30",
  },
  {
    title: "فحص أسهم المحفظة",
    prompt: "حلل أسهم محفظتي المسجلة وحدد مستويات الدعم والمقاومة ونقاط وقف الخسارة المحسوبة لكل سهم.",
    defaultTime: "12:00",
  },
  {
    title: "تجميع وايكوف والارتداد",
    prompt: "هل توجد أسهم حالياً في مناطق تجميع وايكوف ومؤشرات RSI إيجابية جاهزة للارتداد؟",
    defaultTime: "14:00",
  },
];

export default function ScheduledAutomationsCard({
  isPro = false,
  language = "ar",
  telegramLinked = false,
  onQuotaConsumed,
}: Props) {
  const isAr = language === "ar";
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [serverTgLinked, setServerTgLinked] = useState(false);
  const [serverTgChatId, setServerTgChatId] = useState<string | null>(null);

  // Form State
  const [formName, setFormName] = useState("");
  const [formPrompt, setFormPrompt] = useState("");
  const [formTime, setFormTime] = useState("08:30");
  const [formDays, setFormDays] = useState("trading_days");
  const [formCustomChatId, setFormCustomChatId] = useState("");

  const loadAutomations = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/automations", { cache: "no-store" });
      const data = await res.json();
      if (res.ok) {
        setAutomations(data.automations || []);
        setServerTgLinked(Boolean(data.telegram_linked));
        setServerTgChatId(data.default_telegram_chat_id || null);
      } else {
        setErrorMsg(data.error || "تعذر تحميل المهام المجدولة");
      }
    } catch {
      setErrorMsg("خطأ في الاتصال بالخادم");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAutomations();
  }, []);

  const handleSelectPreset = (preset: typeof PRESET_PROMPTS[0]) => {
    setFormName(preset.title);
    setFormPrompt(preset.prompt);
    setFormTime(preset.defaultTime);
  };

  const resetForm = () => {
    setFormName("");
    setFormPrompt("");
    setFormTime("08:30");
    setFormDays("trading_days");
    setFormCustomChatId("");
    setEditingId(null);
    setShowAddForm(false);
    setErrorMsg(null);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!formPrompt.trim() || formPrompt.trim().length < 3) {
      setErrorMsg("يرجى كتابة سؤال أو استفسار للبوت (3 أحرف على الأقل)");
      return;
    }

    if (!telegramLinked && !serverTgLinked && !formCustomChatId.trim()) {
      setErrorMsg(isAr ? "يجب تفعيل وربط بوت تليجرام أولاً لتتمكن من إنشاء أو تفعيل الأتمتة المجدولة" : "Please link your Telegram bot before creating an automation");
      return;
    }

    setSaving(true);
    try {
      if (editingId) {
        // Edit existing
        const res = await fetch(`/api/automations/${editingId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: formName || "استشارة مجدولة",
            prompt: formPrompt,
            scheduled_time: formTime,
            days_of_week: formDays,
            telegram_chat_id: formCustomChatId || null,
          }),
        });
        const data = await res.json();
        if (res.ok) {
          setSuccessMsg("تم تعديل الاستشارة المجدولة بنجاح!");
          resetForm();
          loadAutomations();
        } else {
          setErrorMsg(data.error || "فشل التعديل");
        }
      } else {
        // Create new
        const res = await fetch("/api/automations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: formName || "استشارة مجدولة",
            prompt: formPrompt,
            scheduled_time: formTime,
            days_of_week: formDays,
            telegram_chat_id: formCustomChatId || null,
          }),
        });
        const data = await res.json();
        if (res.ok) {
          setSuccessMsg("تمت إضافة الاستشارة المجدولة بنجاح! سيتم إرسالها يومياً على التليجرام.");
          resetForm();
          loadAutomations();
        } else {
          setErrorMsg(data.error || "فشل الحفظ");
        }
      }
    } catch {
      setErrorMsg("خطأ أثناء حفظ البيانات");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (auto: Automation) => {
    try {
      const res = await fetch(`/api/automations/${auto.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !auto.is_active }),
      });
      if (res.ok) {
        setAutomations((prev) =>
          prev.map((a) => (a.id === auto.id ? { ...a, is_active: !auto.is_active } : a))
        );
      }
    } catch {
      // silent
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(isAr ? "هل أنت متأكد من حذف هذه الاستشارة المجدولة؟" : "Are you sure you want to delete this scheduled automation?")) {
      return;
    }
    try {
      const res = await fetch(`/api/automations/${id}`, { method: "DELETE" });
      if (res.ok) {
        setAutomations((prev) => prev.filter((a) => a.id !== id));
        setSuccessMsg(isAr ? "تم حذف المهمة المجدولة بنجاح" : "Automation deleted");
      }
    } catch {
      setErrorMsg("تعذر حذف المهمة");
    }
  };

  const handleTestRun = async (auto: Automation) => {
    setTestingId(auto.id);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch(`/api/automations/${auto.id}/test`, { method: "POST" });
      const data = await res.json();
      if (res.ok && data.ok) {
        setSuccessMsg("تم إرسال الاستشارة التجريبية فوراً إلى حساب التليجرام بنجاح! 🚀");
        if (onQuotaConsumed) onQuotaConsumed();
        loadAutomations();
      } else {
        const reasonText =
          data.error === "pro_required" || data.reason === "pro_required"
            ? "هذه الميزة تتطلب اشتراك Pro نشط أو باقة Lifetime."
            : data.error === "no_telegram_linked" || data.reason === "no_telegram_linked"
            ? "لم يتم العثور على حساب أو قناة تليجرام مربوطة لاستلام الاستشارة."
            : data.error === "quota_exceeded" || data.reason === "quota_exceeded"
            ? "تم استهلاك كوتتك الشهرية من رسائل الذكاء الاصطناعي."
            : data.error || data.reason || "تعذر إرسال التجربة، تأكد من ربط حساب التليجرام وتوفر الرصيد";
        setErrorMsg(reasonText);
      }
    } catch {
      setErrorMsg("فشل الاتصال بالخادم لتنفيذ التجربة");
    } finally {
      setTestingId(null);
    }
  };

  const handleStartEdit = (auto: Automation) => {
    setEditingId(auto.id);
    setFormName(auto.name);
    setFormPrompt(auto.prompt);
    setFormTime(auto.scheduled_time);
    setFormDays(auto.days_of_week || "trading_days");
    setFormCustomChatId(auto.telegram_chat_id || "");
    setShowAddForm(true);
    window.scrollTo({ top: 400, behavior: "smooth" });
  };

  return (
    <section className="relative z-10 min-w-0 rounded-xl sm:rounded-2xl p-4 sm:p-6 bg-white dark:bg-zinc-900 border-2 sm:border-4 border-black dark:border-white shadow-[4px_4px_0px_rgba(0,0,0,1)] sm:shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)] transition-all space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b-4 border-black dark:border-white pb-4">
        <div className="flex items-center gap-3">
          <div className="h-11 w-11 border-4 border-black dark:border-white bg-[#FFE600] text-black flex items-center justify-center shadow-[3px_3px_0px_rgba(0,0,0,1)] shrink-0">
            <Clock className="h-6 w-6" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl sm:text-2xl font-black text-black dark:text-white uppercase tracking-tight">
                {isAr ? "أتمتة استشارات الذكاء الاصطناعي اليومية" : "Scheduled Daily AI Automations"}
              </h2>
              <span className="border-2 border-black dark:border-white bg-sky-400 text-black px-2 py-0.5 text-xs font-black uppercase tracking-wider shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                PRO EXCLUSIVE
              </span>
            </div>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 font-bold mt-1">
              {isAr
                ? "حدد وقتك وسؤالك يومياً، وسيقوم أرتورو AI ببحث السوق وإرسال الاستشارة لقناتك أو شاتك بتليجرام تلقائياً."
                : "Schedule daily stock prompts sent to your Telegram channel or bot at your chosen time."}
            </p>
          </div>
        </div>

        {/* Counter & Action */}
        <div className="flex items-center gap-3">
          <div className="border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 px-3 py-1.5 font-mono text-sm font-black text-black dark:text-white shadow-[2px_2px_0px_rgba(0,0,0,1)]">
            {automations.length} / 5 {isAr ? "مهام" : "tasks"}
          </div>
          {!showAddForm && automations.length < 5 && isPro && (
            <button
              onClick={() => {
                resetForm();
                setShowAddForm(true);
              }}
              className="px-4 py-2 flex items-center gap-2 border-2 sm:border-4 border-black dark:border-white bg-emerald-500 hover:bg-emerald-400 text-white font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] cursor-pointer active:translate-x-[1px] active:translate-y-[1px]"
            >
              <Plus className="w-4 h-4" />
              <span>{isAr ? "إضافة استشارة مجدولة" : "New Automation"}</span>
            </button>
          )}
        </div>
      </div>

      {/* Telegram Link Warning */}
      {(!telegramLinked && !serverTgLinked) ? (
        <div className="border-3 border-amber-500 bg-amber-50 dark:bg-amber-950/40 p-3 sm:p-4 rounded-lg flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-amber-900 dark:text-amber-200">
          <div className="flex items-start gap-3 text-xs">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-black text-sm">
                {isAr ? "تنبيه: حساب التليجرام غير متصل" : "Warning: Telegram is not linked"}
              </p>
              <p className="font-bold text-zinc-700 dark:text-zinc-300">
                {isAr
                  ? "ميزة الأتمتة تتطلب تفعيل وربط بوت تليجرام أولاً لاستلام الاستشارات المجدولة تلقائياً."
                  : "Scheduled AI automations require linking your Telegram bot first."}
              </p>
            </div>
          </div>
          <a
            href="https://t.me/egxbots_bot"
            target="_blank"
            rel="noreferrer"
            className="px-4 py-2 bg-[#0088cc] hover:bg-[#0077b5] text-white font-black text-xs border-2 border-black shadow-[2px_2px_0_0_#000] flex items-center gap-1.5 shrink-0 whitespace-nowrap"
          >
            <Send className="w-3.5 h-3.5" />
            <span>{isAr ? "ربط وتفعيل البوت الآن" : "Link Bot Now"}</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      ) : (
        <div className="border-2 border-emerald-500 bg-emerald-50 dark:bg-emerald-950/30 p-2.5 rounded-lg flex items-center justify-between gap-2 text-emerald-900 dark:text-emerald-200 text-xs font-bold">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            <span>{isAr ? "بوت تليجرام مفعل ومتصل جاهز لاستلام الاستشارات" : "Telegram Bot active and ready for automations"}:</span>
            {serverTgChatId && <span className="font-mono font-black text-emerald-700 dark:text-emerald-300">{serverTgChatId}</span>}
          </div>
          <span className="text-[10px] bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 px-2 py-0.5 rounded font-black">متصل 🟢</span>
        </div>
      )}

      {/* Pro Lock Banner if not pro */}
      {!isPro && (
        <div className="border-3 border-purple-600 bg-purple-50 dark:bg-purple-950/40 p-4 rounded-lg flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Sparkles className="w-6 h-6 text-purple-600 shrink-0" />
            <div>
              <p className="font-black text-sm text-purple-950 dark:text-purple-200">
                {isAr ? "ميزة حصرية لمشتركي باقة Pro واللايف تايم" : "Exclusive Pro & Lifetime Feature"}
              </p>
              <p className="text-xs text-purple-800 dark:text-purple-300 font-medium">
                {isAr
                  ? "قم بالترقية الآن واستمتع بـ 5 مهام أتمتة يومية تُرسل لتحليلات البورصة والأسهم مباشرة إلى هاتفك."
                  : "Upgrade to Pro to automate up to 5 daily Telegram AI consultations."}
              </p>
            </div>
          </div>
          <Link
            href="/pricing"
            className="px-4 py-2 border-2 border-black bg-purple-600 hover:bg-purple-500 text-white font-black text-xs uppercase tracking-wider shadow-[2px_2px_0px_rgba(0,0,0,1)] shrink-0"
          >
            {isAr ? "الترقية إلى Pro" : "Upgrade to Pro"}
          </Link>
        </div>
      )}

      {/* Messages */}
      {errorMsg && (
        <div className="p-3 border-2 border-red-500 bg-red-100 dark:bg-red-950/40 text-red-900 dark:text-red-200 text-xs font-bold rounded flex items-center justify-between">
          <span>{errorMsg}</span>
          <button onClick={() => setErrorMsg(null)}><X className="w-4 h-4" /></button>
        </div>
      )}
      {successMsg && (
        <div className="p-3 border-2 border-emerald-500 bg-emerald-100 dark:bg-emerald-950/40 text-emerald-900 dark:text-emerald-200 text-xs font-bold rounded flex items-center justify-between">
          <span className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> {successMsg}</span>
          <button onClick={() => setSuccessMsg(null)}><X className="w-4 h-4" /></button>
        </div>
      )}

      {/* Add / Edit Form Modal / Inline */}
      {showAddForm && (
        <form onSubmit={handleSave} className="p-4 sm:p-5 border-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800/80 rounded-xl space-y-4 shadow-[4px_4px_0px_rgba(0,0,0,1)]">
          <div className="flex items-center justify-between border-b-2 border-black dark:border-white pb-3">
            <h3 className="font-black text-base flex items-center gap-2 text-black dark:text-white">
              <Bot className="w-5 h-5 text-sky-500" />
              <span>{editingId ? (isAr ? "تعديل الاستشارة المجدولة" : "Edit Automation") : (isAr ? "إضافة استشارة مجدولة جديدة" : "Add New Automation")}</span>
            </h3>
            <button
              type="button"
              onClick={resetForm}
              className="p-1 border border-black bg-zinc-200 hover:bg-zinc-300 text-black font-bold"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Quick Presets */}
          {!editingId && (
            <div className="space-y-1.5">
              <label className="text-xs font-black uppercase text-zinc-500 dark:text-zinc-400">
                {isAr ? "أو اختر نموذجاً جاهزاً سريعاً:" : "Or pick a popular preset:"}
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {PRESET_PROMPTS.map((p, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleSelectPreset(p)}
                    className="p-2 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 hover:bg-[#FFE600] text-black dark:text-white hover:text-black font-bold text-xs text-right shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer transition-colors"
                  >
                    <div className="font-black">{p.title}</div>
                    <div className="text-[10px] text-zinc-500">{p.defaultTime} ص</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Name */}
            <div>
              <label className="block text-xs font-black uppercase mb-1 text-black dark:text-white">
                {isAr ? "اسم المهمة / العنوان:" : "Task Name:"}
              </label>
              <input
                type="text"
                required
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder={isAr ? "مثال: تقرير قبل الجلسة" : "e.g. Pre-Market Brief"}
                className="w-full p-2.5 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 text-black dark:text-white font-bold text-sm shadow-[2px_2px_0px_rgba(0,0,0,1)]"
              />
            </div>

            {/* Time */}
            <div>
              <label className="block text-xs font-black uppercase mb-1 text-black dark:text-white">
                {isAr ? "موعد الإرسال اليومي (بتوقيت القاهرة 🇪🇬):" : "Daily Time (Cairo Time):"}
              </label>
              <input
                type="time"
                required
                value={formTime}
                onChange={(e) => setFormTime(e.target.value)}
                className="w-full p-2.5 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 text-black dark:text-white font-mono font-bold text-sm shadow-[2px_2px_0px_rgba(0,0,0,1)]"
              />
            </div>
          </div>

          {/* Days */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-black uppercase mb-1 text-black dark:text-white">
                {isAr ? "أيام التشغيل:" : "Operating Days:"}
              </label>
              <select
                value={formDays}
                onChange={(e) => setFormDays(e.target.value)}
                className="w-full p-2.5 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 text-black dark:text-white font-bold text-sm shadow-[2px_2px_0px_rgba(0,0,0,1)]"
              >
                <option value="trading_days">{isAr ? "أيام جلسات التداول فقط (الأحد - الخميس)" : "Trading Days Only (Sun - Thu)"}</option>
                <option value="all_days">{isAr ? "كل الأيام طوال الأسبوع (طوال الـ 7 أيام)" : "All Days (Daily)"}</option>
              </select>
            </div>

            {/* Optional Channel / Chat ID */}
            <div>
              <label className="block text-xs font-black uppercase mb-1 text-black dark:text-white">
                {isAr ? "معرف القناة أو الشات (اختياري):" : "Telegram Chat ID (Optional):"}
              </label>
              <input
                type="text"
                value={formCustomChatId}
                onChange={(e) => setFormCustomChatId(e.target.value)}
                placeholder={isAr ? "اتركه فارغاً لاستخدام شاتك الأساسي المسجل" : "Leave empty to use linked Telegram profile"}
                className="w-full p-2.5 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 text-black dark:text-white font-mono font-bold text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)]"
              />
            </div>
          </div>

          {/* Prompt */}
          <div>
            <label className="block text-xs font-black uppercase mb-1 text-black dark:text-white">
              {isAr ? "السؤال أو الاستفسار المطلوب من الذكاء الاصطناعي إجابته:" : "AI Prompt / Question:"}
            </label>
            <textarea
              required
              rows={3}
              value={formPrompt}
              onChange={(e) => setFormPrompt(e.target.value)}
              placeholder={isAr ? "اكتب السؤال الذي ترغب في أن يحلله لك البوت كل يوم ويرسله لقناتك..." : "Write the stock analysis question the AI should answer daily..."}
              className="w-full p-3 border-2 border-black dark:border-white bg-white dark:bg-zinc-900 text-black dark:text-white font-medium text-sm shadow-[2px_2px_0px_rgba(0,0,0,1)]"
            />
          </div>

          {/* Form Actions */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={resetForm}
              className="px-4 py-2 border-2 border-black bg-zinc-200 text-black font-bold text-xs uppercase"
            >
              {isAr ? "إلغاء" : "Cancel"}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-6 py-2 border-2 sm:border-4 border-black dark:border-white bg-[#FFE600] text-black font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] cursor-pointer hover:bg-yellow-400 disabled:opacity-50"
            >
              {saving ? (isAr ? "جاري الحفظ..." : "Saving...") : (editingId ? (isAr ? "تحديث المهمة" : "Update") : (isAr ? "حفظ وتفعيل الأتمتة" : "Save & Activate"))}
            </button>
          </div>
        </form>
      )}

      {/* List of Automations */}
      {loading ? (
        <div className="p-8 text-center text-zinc-500 font-bold flex items-center justify-center gap-2">
          <RefreshCw className="w-5 h-5 animate-spin" />
          <span>{isAr ? "جاري تحميل المهام المجدولة..." : "Loading automations..."}</span>
        </div>
      ) : automations.length === 0 ? (
        <div className="p-8 border-2 border-dashed border-zinc-300 dark:border-zinc-700 rounded-xl text-center space-y-3">
          <Bot className="w-12 h-12 text-zinc-400 mx-auto" />
          <p className="font-black text-base text-zinc-700 dark:text-zinc-300">
            {isAr ? "لا توجد لديك استشارات مجدولة حالياً" : "No scheduled automations configured yet"}
          </p>
          <p className="text-xs text-zinc-500 max-w-md mx-auto">
            {isAr
              ? "يمكنك إنشاء حتى 5 استشارات يومية مجدولة. حدد وقتك وسؤالك المفضل وسيتولى أرتورو AI الباقي تلقائياً كل يوم."
              : "Set up to 5 daily automations to receive real-time technical analysis on Telegram at specific times."}
          </p>
          {isPro && !showAddForm && (
            <button
              onClick={() => setShowAddForm(true)}
              className="px-5 py-2.5 border-4 border-black dark:border-white bg-[#FFE600] text-black font-black text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] hover:bg-yellow-400 cursor-pointer"
            >
              <Plus className="w-4 h-4 inline-block mr-1" />
              <span>{isAr ? "إنشاء أول استشارة مجدولة الآن" : "Create First Automation"}</span>
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {automations.map((auto) => (
            <div
              key={auto.id}
              className={`p-4 border-3 border-black dark:border-white rounded-xl bg-white dark:bg-zinc-900 shadow-[3px_3px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_rgba(255,255,255,1)] flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all ${!auto.is_active ? "opacity-60 bg-zinc-100 dark:bg-zinc-800/40" : ""}`}
            >
              {/* Info */}
              <div className="space-y-1.5 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-black text-base text-black dark:text-white">
                    {auto.name}
                  </span>
                  <span className="border border-black dark:border-white bg-[#FFE600] text-black font-mono font-black text-xs px-2 py-0.5 shadow-[1px_1px_0px_rgba(0,0,0,1)]">
                    ⏰ {auto.scheduled_time} {isAr ? "بتوقيت القاهرة" : "Cairo"}
                  </span>
                  <span className="border border-black dark:border-white bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 font-bold text-[10px] px-2 py-0.5">
                    {auto.days_of_week === "all_days" ? (isAr ? "كل الأيام" : "Daily") : (isAr ? "أيام التداول (أحد-خميس)" : "Trading Days")}
                  </span>
                  {auto.is_active ? (
                    <span className="text-emerald-600 dark:text-emerald-400 text-xs font-black flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                      {isAr ? "نشط" : "Active"}
                    </span>
                  ) : (
                    <span className="text-zinc-400 text-xs font-bold">
                      {isAr ? "متوقف مؤقتاً" : "Paused"}
                    </span>
                  )}
                </div>

                <p className="text-xs text-zinc-600 dark:text-zinc-300 font-medium bg-zinc-50 dark:bg-zinc-800 p-2 rounded border border-zinc-200 dark:border-zinc-700">
                  <span className="font-bold text-zinc-400 mr-1">السؤال:</span>
                  &quot;{auto.prompt}&quot;
                </p>

                {auto.last_run_at && (
                  <div className="flex flex-wrap items-center gap-2 text-[10px] text-zinc-500">
                    <span>
                      {isAr ? "آخر إرسال:" : "Last run:"} {new Date(auto.last_run_at).toLocaleString("ar-EG")}
                    </span>
                    {auto.last_status === "success" && (
                      <span className="text-emerald-600 font-black flex items-center gap-0.5">
                        <CheckCircle2 className="w-3 h-3" /> {isAr ? "ناجح" : "Success"}
                      </span>
                    )}
                    {auto.last_status === "quota_exceeded" && (
                      <span className="text-amber-600 font-black flex items-center gap-0.5">
                        <AlertTriangle className="w-3 h-3" /> {isAr ? "الكوتا الشهرية منتهية" : "Quota Exceeded"}
                      </span>
                    )}
                    {auto.last_status === "telegram_delivery_failed" && (
                      <span className="text-red-600 font-black">
                        {isAr ? "تعذر الإرسال لتليجرام" : "Telegram Failed"}
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 shrink-0">
                {/* Test Run button */}
                <button
                  type="button"
                  disabled={testingId === auto.id || !isPro}
                  onClick={() => handleTestRun(auto)}
                  className="px-3 py-1.5 border-2 border-black dark:border-white bg-sky-500 hover:bg-sky-400 text-white font-black text-xs uppercase shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer flex items-center gap-1 active:translate-x-[1px] active:translate-y-[1px] disabled:opacity-50"
                  title={isAr ? "تجربة الإرسال على التليجرام الآن" : "Test run immediately"}
                >
                  <Send className={`w-3.5 h-3.5 ${testingId === auto.id ? "animate-spin" : ""}`} />
                  <span>{testingId === auto.id ? (isAr ? "جاري الإرسال..." : "Sending...") : (isAr ? "تجربة الآن" : "Test Run")}</span>
                </button>

                {/* Toggle On/Off */}
                <button
                  type="button"
                  onClick={() => handleToggleActive(auto)}
                  className={`p-1.5 border-2 border-black dark:border-white font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer active:translate-x-[1px] active:translate-y-[1px] ${auto.is_active ? "bg-emerald-400 text-black" : "bg-zinc-300 text-zinc-600"}`}
                  title={auto.is_active ? (isAr ? "إيقاف مؤقت" : "Pause") : (isAr ? "تفعيل" : "Activate")}
                >
                  <Power className="w-4 h-4" />
                </button>

                {/* Edit */}
                <button
                  type="button"
                  onClick={() => handleStartEdit(auto)}
                  className="p-1.5 border-2 border-black dark:border-white bg-[#FFE600] text-black font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer active:translate-x-[1px] active:translate-y-[1px]"
                  title={isAr ? "تعديل" : "Edit"}
                >
                  <Edit3 className="w-4 h-4" />
                </button>

                {/* Delete */}
                <button
                  type="button"
                  onClick={() => handleDelete(auto.id)}
                  className="p-1.5 border-2 border-black dark:border-white bg-red-500 hover:bg-red-400 text-white font-black text-xs shadow-[2px_2px_0px_rgba(0,0,0,1)] cursor-pointer active:translate-x-[1px] active:translate-y-[1px]"
                  title={isAr ? "حذف" : "Delete"}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
