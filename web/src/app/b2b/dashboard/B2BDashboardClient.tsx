"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import {
  Bot,
  Zap,
  ShieldCheck,
  CheckCircle2,
  Copy,
  ExternalLink,
  Edit3,
  Save,
  MessageSquare,
  AlertCircle,
  HelpCircle,
  Sparkles,
  ArrowRight,
  RefreshCw,
  Crown,
  Eye,
  Check,
  Loader2,
} from "lucide-react";

interface License {
  id: string;
  tier: "b2b_starter" | "b2b_pro" | "b2b_enterprise";
  daily_limit: number;
  daily_used: number;
  last_used_date: string | null;
  custom_signature: string | null;
  telegram_chat_id: number | null;
  group_title: string | null;
  status: "active" | "expired" | "paused";
  starts_at: string;
  expires_at: string;
}

const DEMO_LICENSE: License = {
  id: "b2b-demo-vip-001",
  tier: "b2b_pro",
  daily_limit: 120,
  daily_used: 28,
  last_used_date: new Date().toISOString().slice(0, 10),
  custom_signature: "📊 تم التحليل بواسطة بوت قناة التوصيات الذهبية بالتعاون مع EGX BOTS",
  telegram_chat_id: -100192847192,
  group_title: "قناة التوصيات الذهبية للبورصة 📊",
  status: "active",
  starts_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
  expires_at: new Date(Date.now() + 25 * 24 * 60 * 60 * 1000).toISOString(),
};

const TIER_DETAILS = {
  b2b_starter: {
    name: "Starter B2B",
    members: "حتى 150 عضو",
    limit: 50,
    price: 1000,
    badgeColor: "bg-blue-400 text-black",
  },
  b2b_pro: {
    name: "Pro VIP B2B (الأكثر طلباً 🔥)",
    members: "حتى 500 عضو",
    limit: 120,
    price: 1500,
    badgeColor: "bg-emerald-400 text-black",
  },
  b2b_enterprise: {
    name: "Enterprise B2B (كبرى القنوات 💎)",
    members: "حتى 1,500 عضو",
    limit: 250,
    price: 2500,
    badgeColor: "bg-purple-400 text-black",
  },
};

export default function B2BDashboardClient() {
  const { user, loading: authLoading } = useAuth();
  const [license, setLicense] = useState<License | null>(null);
  const [loading, setLoading] = useState(true);
  const [isDemoMode, setIsDemoMode] = useState(false);

  // Form states
  const [signatureInput, setSignatureInput] = useState("");
  const [groupTitleInput, setGroupTitleInput] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchLicense = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/b2b/license");
      if (res.status === 401) {
        setIsDemoMode(true);
        setLicense(DEMO_LICENSE);
        setSignatureInput(DEMO_LICENSE.custom_signature || "");
        setGroupTitleInput(DEMO_LICENSE.group_title || "");
        setLoading(false);
        return;
      }
      const data = await res.json();
      if (data.ok && data.license) {
        setLicense(data.license);
        setSignatureInput(data.license.custom_signature || "");
        setGroupTitleInput(data.license.group_title || "");
        setIsDemoMode(false);
      } else {
        // No active license for this user, activate demo view so they can see how it works
        setIsDemoMode(true);
        setLicense(DEMO_LICENSE);
        setSignatureInput(DEMO_LICENSE.custom_signature || "");
        setGroupTitleInput(DEMO_LICENSE.group_title || "");
      }
    } catch {
      setIsDemoMode(true);
      setLicense(DEMO_LICENSE);
      setSignatureInput(DEMO_LICENSE.custom_signature || "");
      setGroupTitleInput(DEMO_LICENSE.group_title || "");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!authLoading) {
      fetchLicense();
    }
  }, [authLoading]);

  const activeLicense = license || DEMO_LICENSE;
  const tierInfo = TIER_DETAILS[activeLicense.tier] || TIER_DETAILS.b2b_pro;

  const usagePercent = Math.min(
    100,
    Math.round(((activeLicense.daily_used || 0) / (activeLicense.daily_limit || 1)) * 100)
  );

  const remainingDays = Math.max(
    0,
    Math.ceil((new Date(activeLicense.expires_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
  );

  const handleSaveSignature = async () => {
    if (isDemoMode) {
      toast.success("تم تحديث المعاينة الحية بنجاح! (في الوضع التجريبي)");
      setLicense((prev) => (prev ? { ...prev, custom_signature: signatureInput, group_title: groupTitleInput } : null));
      return;
    }

    try {
      setSaving(true);
      const res = await fetch("/api/b2b/license", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          license_id: activeLicense.id,
          custom_signature: signatureInput,
          group_title: groupTitleInput,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        toast.success("تم حفظ التوقيع المخصص واسم الجروب بنجاح! يظهر التعديل فوراً في جميع ردود البوت.");
        fetchLicense();
      } else {
        toast.error(`فشل الحفظ: ${data.error}`);
      }
    } catch (err: any) {
      toast.error(`خطأ أثناء الحفظ: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`تم نسخ ${label}`);
  };

  const activationCommand = `/activate ${activeLicense.id.slice(0, 8)}`;

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black text-zinc-950 dark:text-zinc-100 py-8 px-4 sm:px-6 lg:px-8" dir="rtl">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Demo Mode Notice Banner */}
        {isDemoMode && (
          <div className="border-4 border-black dark:border-white bg-amber-300 text-black p-4 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 shrink-0" />
              <div>
                <span className="font-black text-sm block sm:inline">
                  أنت تتصفح المعاينة الحية للوحة تحكم B2B (Demo Preview).
                </span>
                <span className="text-xs font-bold block opacity-90 sm:ms-2">
                  هذه هي اللوحة التي ستحصل عليها لإدارة استهلاك البوت وتخصيص توقيع قناتك.
                </span>
              </div>
            </div>
            <Link
              href="/pricing?mode=b2b"
              className="inline-flex items-center gap-1.5 border-2 border-black bg-emerald-500 hover:bg-emerald-600 text-black font-black px-4 py-2 text-xs uppercase shadow-[2px_2px_0px_#000] shrink-0 active:translate-y-0.5"
            >
              <span>اشترك ورخّص البوت لقناتك</span>
              <ArrowRight className="w-3.5 h-3.5 rotate-180" />
            </Link>
          </div>
        )}

        {/* Top Header Card */}
        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#fff]">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="p-2 border-2 border-black bg-emerald-400 text-black">
                  <Bot className="w-6 h-6" />
                </span>
                <div>
                  <span className="inline-block border border-black bg-emerald-100 dark:bg-emerald-950 text-emerald-900 dark:text-emerald-300 px-2 py-0.5 text-[10px] font-black uppercase">
                    B2B BOT LICENSING DASHBOARD
                  </span>
                  <h1 className="text-2xl sm:text-3xl font-black text-zinc-900 dark:text-white">
                    لوحة تحكم ترخيص بوت التليجرام للقنوات
                  </h1>
                </div>
              </div>
              <p className="text-xs text-zinc-600 dark:text-zinc-400 font-bold max-w-2xl">
                تحكم بالكامل في إعدادات البوت داخل مجموعتك، راقب استهلاك الأعضاء اليومي، وخصص التوقيع التسويقي الذي يظهر أسفل كل تحليل.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 px-4 py-2 text-center">
                <span className="text-[10px] text-zinc-500 font-bold uppercase block">الباقة المفعلة</span>
                <span className="text-xs font-black text-emerald-600 dark:text-emerald-400">{tierInfo.name}</span>
              </div>
              <div className="border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 px-4 py-2 text-center">
                <span className="text-[10px] text-zinc-500 font-bold uppercase block">الحالة</span>
                <span className="text-xs font-black text-emerald-600 dark:text-emerald-400 flex items-center gap-1 justify-center">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                  نشط ومفعل
                </span>
              </div>
              <div className="border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 px-4 py-2 text-center">
                <span className="text-[10px] text-zinc-500 font-bold uppercase block">الأيام المتبقية</span>
                <span className="text-xs font-black text-zinc-900 dark:text-white font-mono">{remainingDays} يوماً</span>
              </div>
            </div>
          </div>
        </div>

        {/* 2-Column Grid: Quota & Group Connection */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Daily Quota Card */}
          <div className="lg:col-span-6 border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 shadow-[5px_5px_0px_#000] dark:shadow-[5px_5px_0px_#fff] space-y-4">
            <div className="flex items-center justify-between border-b-2 border-zinc-200 dark:border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <Zap className="w-5 h-5 text-amber-500" />
                <h2 className="text-base font-black text-zinc-900 dark:text-white">
                  استهلاك الاستفسارات اليومي للجروب
                </h2>
              </div>
              <span className="border-2 border-black bg-amber-300 text-black px-2 py-0.5 text-[10px] font-black font-mono">
                {activeLicense.daily_used} / {activeLicense.daily_limit} استفسار
              </span>
            </div>

            {/* Progress Bar */}
            <div className="space-y-2">
              <div className="flex justify-between text-xs font-bold">
                <span className="text-zinc-600 dark:text-zinc-400">نسبة الاستهلاك اليومي:</span>
                <span className="font-mono font-black text-emerald-600 dark:text-emerald-400">{usagePercent}%</span>
              </div>
              <div className="w-full bg-zinc-200 dark:bg-zinc-800 h-4 border-2 border-black dark:border-white overflow-hidden p-0.5">
                <div
                  className={`h-full transition-all duration-500 ${
                    usagePercent >= 90 ? "bg-red-500" : usagePercent >= 70 ? "bg-amber-400" : "bg-emerald-500"
                  }`}
                  style={{ width: `${usagePercent}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-[11px] font-mono text-zinc-500 pt-1">
                <span>المتبقي اليوم: {Math.max(0, activeLicense.daily_limit - activeLicense.daily_used)} استفسار</span>
                <span>سعة الجروب: {tierInfo.members}</span>
              </div>
            </div>

            {/* Quota Rules Box */}
            <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800/60 p-3.5 space-y-1.5 text-xs font-bold text-zinc-700 dark:text-zinc-300">
              <div className="flex items-center gap-1.5 text-zinc-900 dark:text-white font-black">
                <ShieldCheck className="w-4 h-4 text-emerald-500" />
                <span>حماية الاستخدام العادل (Fair Use Policy) مفعّلة:</span>
              </div>
              <ul className="list-disc list-inside space-y-1 text-[11px] text-zinc-600 dark:text-zinc-400 pr-1">
                <li>كولد داون 90 ثانية للعضو الواحد بين كل سؤال وآخر لمنع الإغراق.</li>
                <li>حد أقصى 15 استفسار للشخص الواحد يومياً لضمان توزيع الحصة على جميع الأعضاء.</li>
                <li>يتصفر العداد اليومي تلقائياً كل ليلة في تمام الساعة 12:00 منتصف الليل بتوقيت القاهرة.</li>
              </ul>
            </div>
          </div>

          {/* Telegram Group Connection Card */}
          <div className="lg:col-span-6 border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 shadow-[5px_5px_0px_#000] dark:shadow-[5px_5px_0px_#fff] space-y-4">
            <div className="flex items-center justify-between border-b-2 border-zinc-200 dark:border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <Bot className="w-5 h-5 text-emerald-500" />
                <h2 className="text-base font-black text-zinc-900 dark:text-white">
                  حالة ربط المجموعة على تليجرام
                </h2>
              </div>
              <span className="inline-flex items-center gap-1 border-2 border-black bg-emerald-300 text-black px-2 py-0.5 text-[10px] font-black">
                <Check className="w-3 h-3" />
                متصل وجاهز للرد
              </span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-[11px] font-black text-zinc-500 mb-1">اسم الجروب أو القناة</label>
                <input
                  type="text"
                  value={groupTitleInput}
                  onChange={(e) => setGroupTitleInput(e.target.value)}
                  placeholder="مثلاً: قناة توصيات الأسهم المصرية 📊"
                  className="w-full border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800 px-3.5 py-2 text-xs font-bold outline-none focus:ring-2 focus:ring-emerald-500 text-zinc-900 dark:text-white"
                />
              </div>

              <div>
                <label className="block text-[11px] font-black text-zinc-500 mb-1">معرف الجروب الرقمي (Chat ID)</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={activeLicense.telegram_chat_id ? String(activeLicense.telegram_chat_id) : "بانتظار أمر التفعيل"}
                    className="flex-1 border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 px-3.5 py-2 font-mono text-xs font-black text-zinc-900 dark:text-white"
                    dir="ltr"
                  />
                  {activeLicense.telegram_chat_id && (
                    <button
                      onClick={() => copyToClipboard(String(activeLicense.telegram_chat_id), "Chat ID")}
                      className="border-2 border-black dark:border-white bg-zinc-200 hover:bg-zinc-300 dark:bg-zinc-700 p-2 text-xs font-bold"
                      title="نسخ المعرف"
                    >
                      <Copy className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>

              {/* Bot Activation Instructions */}
              <div className="border-2 border-black dark:border-white bg-emerald-50 dark:bg-emerald-950/30 p-3.5 space-y-2 text-xs">
                <div className="font-black text-emerald-800 dark:text-emerald-300 flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4" />
                  <span>خطوات ربط أو نقل البوت لمجموعة جديدة:</span>
                </div>
                <div className="space-y-2 text-[11px] text-zinc-700 dark:text-zinc-300 font-bold">
                  <div className="flex items-center justify-between gap-2">
                    <span>1. أضف البوت <code>@egxbots_bot</code> لمجموعتك وارفعه مشرفاً (Admin).</span>
                    <a
                      href="https://t.me/egxbots_bot?startgroup=true"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="border border-black bg-emerald-500 text-black px-2 py-0.5 text-[10px] font-black shrink-0 hover:bg-emerald-600 inline-flex items-center gap-1"
                    >
                      <span>إضافة البوت</span>
                      <ExternalLink className="w-2.5 h-2.5" />
                    </a>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span>2. اكتب في الجروب أمر التفعيل:</span>
                    <button
                      onClick={() => copyToClipboard(activationCommand, "أمر التفعيل")}
                      className="border border-black bg-zinc-200 dark:bg-zinc-700 text-zinc-900 dark:text-white px-2 py-0.5 text-[10px] font-mono font-black shrink-0 hover:bg-zinc-300 inline-flex items-center gap-1"
                    >
                      <span>{activationCommand}</span>
                      <Copy className="w-2.5 h-2.5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Custom Signature Editor & Live Telegram Mockup */}
        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#fff] space-y-5">
          <div className="flex items-center justify-between border-b-2 border-zinc-200 dark:border-zinc-800 pb-3">
            <div className="flex items-center gap-2">
              <Edit3 className="w-5 h-5 text-emerald-500" />
              <div>
                <h2 className="text-lg font-black text-zinc-900 dark:text-white">
                  تعديل سطر التوقيع المخصص (Custom Signature)
                </h2>
                <p className="text-xs text-zinc-500 font-bold">
                  هذا السطر يظهر أسفل كل رد وتحليل للبوت داخل مجموعتك لترويج قناتك وبناء براندك أمام المشتركين
                </p>
              </div>
            </div>

            <button
              onClick={handleSaveSignature}
              disabled={saving}
              className="flex items-center gap-2 border-2 border-black dark:border-white bg-emerald-500 hover:bg-emerald-600 text-black font-black px-5 py-2.5 text-xs uppercase shadow-[2px_2px_0px_#000] active:translate-y-0.5"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              <span>{saving ? "جاري الحفظ..." : "حفظ التوقيع الآن"}</span>
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Input Form Column */}
            <div className="lg:col-span-6 space-y-3">
              <label className="block text-xs font-black text-zinc-700 dark:text-zinc-300">
                اكتب نص التوقيع التسويقي المخصص (بحد أقصى 150 حرفاً):
              </label>
              <textarea
                rows={3}
                maxLength={150}
                value={signatureInput}
                onChange={(e) => setSignatureInput(e.target.value)}
                placeholder="مثلاً: 📊 تم التحليل بواسطة بوت قناة التوصيات الذهبية بالتعاون مع EGX BOTS"
                className="w-full border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800 p-3.5 text-xs font-bold outline-none focus:ring-2 focus:ring-emerald-500 text-zinc-900 dark:text-white leading-relaxed"
              />
              <div className="flex items-center justify-between text-[11px] text-zinc-500 font-mono">
                <span>{signatureInput.length} / 150 حرفاً</span>
                <span>يدعم الرموز التعبيرية (Emojis) ✨</span>
              </div>

              {/* Suggestions Chips */}
              <div className="space-y-1.5 pt-2">
                <span className="text-[11px] font-black text-zinc-500 block">نماذج توقيع مقترحة (اضغط للتطبيق):</span>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    "📊 تم التحليل بواسطة بوت قناة أستاذ فلان بالتعاون مع EGX BOTS",
                    "⚡ إشارات خاصة بأعضاء قناة VIP Signals بالتعاون مع EGX BOTS",
                    "🎯 تحليلات البورصة المصرية الحصرية لقناتنا بالتعاون مع EGX BOTS",
                  ].map((preset, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => setSignatureInput(preset)}
                      className="border border-zinc-300 dark:border-zinc-700 bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 px-2 py-1 text-[10px] font-bold text-zinc-700 dark:text-zinc-300 text-right transition-colors"
                    >
                      {preset}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Live Interactive Telegram Mockup Column */}
            <div className="lg:col-span-6 space-y-2">
              <div className="flex items-center justify-between text-xs font-black text-zinc-600 dark:text-zinc-400">
                <span className="flex items-center gap-1.5">
                  <Eye className="w-4 h-4 text-emerald-500" />
                  معاينة حية فورية (شكل الرد داخل تليجرام):
                </span>
                <span className="text-[10px] text-emerald-500 font-mono">تحديث فوري ⚡</span>
              </div>

              {/* Telegram Dark Bubble Mockup */}
              <div className="border-4 border-black dark:border-white bg-[#182533] text-white p-4 font-sans rounded-none shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] space-y-3">
                {/* Simulated User Question */}
                <div className="bg-[#243447] p-2.5 border-r-4 border-emerald-400 text-xs space-y-1">
                  <div className="font-bold text-emerald-400 text-[11px] flex items-center justify-between">
                    <span>أحد أعضاء الجروب:</span>
                    <span className="text-[10px] text-zinc-400 font-mono">11:42 AM</span>
                  </div>
                  <div className="font-mono text-zinc-200 text-xs">
                    @egxbots_bot تحليل سهم السويدي إليكتريك؟
                  </div>
                </div>

                {/* Simulated Bot Response */}
                <div className="space-y-2 pt-1 text-xs">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 font-black text-emerald-400 text-xs">
                      <span>EGX BOTS</span>
                      <span className="bg-emerald-500 text-black text-[9px] px-1 font-black">BOT</span>
                    </div>
                    <span className="text-[10px] text-zinc-400 font-mono">11:42 AM</span>
                  </div>

                  <div className="space-y-1.5 text-zinc-200 leading-relaxed font-sans text-xs">
                    <p className="font-bold">
                      📈 <b>سهم السويدي إليكتريك (SWDY.CA)</b>
                    </p>
                    <p>• السعر الحالي: <b>48.20 ج.م</b> (+1.85%)</p>
                    <p>• الاتجاه الفني: <b>صاعد متوسط المدى</b> مع اختراق مقاومة 47.50 ج.م.</p>
                    <p>• مستويات الدعم: 47.10 - 46.50 ج.م | المقاومة القادمة: 50.20 ج.م</p>
                    <p>• مؤشر السيولة: <b>شراء تجميعي قوي (72%)</b> ⚡</p>
                  </div>

                  {/* The Custom Signature Line */}
                  <div className="border-t border-[#3b4c5e] pt-2 mt-2">
                    <div className="text-[11px] font-bold text-amber-300 bg-[#1f2d3d] p-2 border-r-2 border-amber-400">
                      {signatureInput.trim() || "✍️ [اكتب توقيعك في الصندوق المقابل وسيظهر هنا فوراً...]"}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* How Bot Operates in Group Guide */}
        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 shadow-[5px_5px_0px_#000] dark:shadow-[5px_5px_0px_#fff] space-y-3">
          <div className="flex items-center gap-2 border-b-2 border-zinc-200 dark:border-zinc-800 pb-3">
            <HelpCircle className="w-5 h-5 text-emerald-500" />
            <h3 className="text-base font-black text-zinc-900 dark:text-white">
              كيف يتفاعل أعضاء مجموعتك مع البوت؟
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2 text-xs font-bold text-zinc-700 dark:text-zinc-300">
            <div className="border-2 border-black dark:border-white p-3.5 bg-zinc-50 dark:bg-zinc-800/40 space-y-1.5">
              <span className="font-black text-zinc-900 dark:text-white block">1. المنشن الصريح (@)</span>
              <p className="text-[11px] text-zinc-600 dark:text-zinc-400">
                يكتب العضو: <code>@egxbots_bot سهم التجاري الدولي</code> فيرد البوت مباشرة بتحليل فوري شامل للسهم.
              </p>
            </div>

            <div className="border-2 border-black dark:border-white p-3.5 bg-zinc-50 dark:bg-zinc-800/40 space-y-1.5">
              <span className="font-black text-zinc-900 dark:text-white block">2. الأوامر المباشرة (/)</span>
              <p className="text-[11px] text-zinc-600 dark:text-zinc-400">
                يدعم البوت أوامر مثل: <code>/ask</code> أو <code>/analyze</code> أو <code>!سهم</code> لتحليل أي سهم أو مقارنة سهمين.
              </p>
            </div>

            <div className="border-2 border-black dark:border-white p-3.5 bg-zinc-50 dark:bg-zinc-800/40 space-y-1.5">
              <span className="font-black text-zinc-900 dark:text-white block">3. الرد المباشر (Reply)</span>
              <p className="text-[11px] text-zinc-600 dark:text-zinc-400">
                إذا عمل العضو Reply على أي رسالة تحليل سابقة للبوت وسأله عن وقف الخسارة أو الهدف، يستجيب البوت فوراً في نفس السياق.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
