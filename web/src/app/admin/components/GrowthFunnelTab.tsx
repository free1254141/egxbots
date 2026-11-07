"use client";

import { useState, useEffect } from "react";
import {
  TrendingUp,
  Users,
  Rocket,
  MessageSquare,
  CreditCard,
  Crown,
  RefreshCw,
  Clock,
  ArrowRight,
  Send,
  Zap,
  Target,
  Sparkles,
  Award,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { toast } from "sonner";

interface FunnelData {
  totalSignups: number;
  recentSignups7d: number;
  totalTrials: number;
  activeTrials: number;
  finishedTrials: number;
  activatedTrials: number;
  checkoutUsers: number;
  totalOrdersCount: number;
  approvedOrdersCount: number;
  paidCount: number;
  foundersCount: number;
  rates: {
    trialStartRate: number;
    trialActivationRate: number;
    checkoutRate: number;
    paidConversionRate: number;
    trialToPaidRate: number;
  };
}

interface CampaignItem {
  type: string;
  sent_count: number;
  unique_users: number;
  last_sent_at: string;
}

interface RecentUserItem {
  id: string;
  name: string;
  created_at: string;
  hasTrial: boolean;
  hasCheckout: boolean;
  isPaid: boolean;
  messagesCount: number;
  stage: string;
  stageColor: string;
}

const CAMPAIGN_LABELS: Record<string, { label: string; desc: string }> = {
  signup_welcome_deep: {
    label: "ترحيب المسجلين الجدد",
    desc: "إيميل ترحيبي وتوجيهي للبدء في 3 خطوات فور التسجيل",
  },
  trial_welcome: {
    label: "اليوم 0: تفعيل التجربة",
    desc: "توجيه المستخدم لسؤال البوت فور تفعيل تجربة الـ 3 أيام",
  },
  trial_day1: {
    label: "اليوم 1: حث وتنشيط التجربة",
    desc: "3 أسئلة مقترحة وتذكير بمزايا تليجرام وقناة VIP",
  },
  trial_day2: {
    label: "اليوم 2: دراسة حالة وصفقات الزخم",
    desc: "شرح عملي للصفقات القصيرة وإدارة المخاطر قبل انتهاء التجربة",
  },
  trial_expiring: {
    label: "اليوم 3: تنبيه انتهاء التجربة",
    desc: "تحذير انتهاء التجربة وعرض المؤسسين بخصم 50% وتثبيت السعر",
  },
  abandoned_checkout: {
    label: "استرجاع السلة المتروكة",
    desc: "تذكير لمن فتح صفحة الدفع ولم يكمل خلال 2-72 ساعة",
  },
  founders_final_48h: {
    label: "الساعات الـ 48 الأخيرة للعرض",
    desc: "حملة العد التنازلي قبل إغلاق باقة المؤسسين",
  },
  founders_offer: {
    label: "حملة عرض المؤسسين العامة",
    desc: "إرسال عرض المؤسسين لقاعدة المشتركين المسجلين",
  },
};

export default function GrowthFunnelTab() {
  const [data, setData] = useState<{
    funnel: FunnelData;
    campaigns: CampaignItem[];
    recentUsers: RecentUserItem[];
  } | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = async (showToast = false) => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/growth/funnel", { cache: "no-store" });
      if (!res.ok) throw new Error("Failed to load growth funnel");
      const json = await res.json();
      if (json.ok) {
        setData(json);
        if (showToast) toast.success("تم تحديث بيانات القمع بنجاح");
      }
    } catch (e: any) {
      toast.error(e.message || "حدث خطأ أثناء تحميل بيانات القمع");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(false);
  }, []);

  const f = data?.funnel;

  return (
    <div className="p-4 md:p-8 max-w-[1700px] mx-auto space-y-8 animate-in fade-in duration-500 text-zinc-900 dark:text-zinc-100" dir="rtl">
      {/* Header Banner */}
      <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 sm:p-8 shadow-[8px_8px_0px_#10b981] flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <span className="p-2 border-2 border-black bg-emerald-400 text-black shadow-[2px_2px_0px_#000]">
              <Target className="w-6 h-6" />
            </span>
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight">
              قمع النمو والتحويل (Growth & Conversion Funnel)
            </h1>
          </div>
          <p className="text-xs sm:text-sm font-bold text-zinc-600 dark:text-zinc-400 max-w-2xl leading-relaxed">
            متابعة شاملة لرحلة المستخدم من لحظة تسجيل الحساب المجاني، مروراً ببدء التجربة والتفاعل مع الذكاء الاصطناعي، وحتى التحويل للاشتراك وتثبيت سعر المؤسسين.
          </p>
        </div>

        <button
          type="button"
          onClick={() => loadData(true)}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 border-3 border-black dark:border-white bg-emerald-500 hover:bg-emerald-600 text-white font-black px-5 py-3 text-xs uppercase tracking-wider shadow-[4px_4px_0px_rgba(0,0,0,1)] hover:-translate-y-0.5 active:translate-y-0 transition-all cursor-pointer disabled:opacity-50 self-start md:self-auto"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          <span>تحديث الأرقام الآن</span>
        </button>
      </div>

      {/* 5-Step Visual Funnel Pipeline */}
      {f && (
        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 sm:p-8 shadow-[8px_8px_0px_rgba(0,0,0,1)] space-y-6">
          <div className="flex items-center justify-between border-b-2 border-zinc-200 dark:border-zinc-800 pb-3">
            <h2 className="text-lg font-black flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-emerald-500" />
              <span>مراحل القمع الرئيسية ونسب الانتقال (Conversion Pipeline)</span>
            </h2>
            <span className="text-xs font-mono font-bold text-zinc-500">
              معدل التحويل الكلي: <strong className="text-emerald-500">{f.rates.paidConversionRate}%</strong>
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {/* Step 1: Signups */}
            <div className="border-3 border-black dark:border-white p-4 bg-zinc-50 dark:bg-zinc-900 space-y-2 relative">
              <div className="flex items-center justify-between text-xs font-black text-zinc-500">
                <span>01. التسجيل</span>
                <span className="px-1.5 py-0.5 bg-black text-white text-[10px]">100%</span>
              </div>
              <div className="text-3xl font-black text-zinc-950 dark:text-white font-mono">
                {f.totalSignups}
              </div>
              <p className="text-[11px] font-bold text-zinc-500">
                +{f.recentSignups7d} مسجل خلال آخر 7 أيام
              </p>
              <div className="w-full bg-zinc-200 dark:bg-zinc-800 h-2 mt-2">
                <div className="bg-blue-500 h-full w-full"></div>
              </div>
            </div>

            {/* Step 2: Trials */}
            <div className="border-3 border-black dark:border-white p-4 bg-zinc-50 dark:bg-zinc-900 space-y-2 relative">
              <div className="flex items-center justify-between text-xs font-black text-zinc-500">
                <span>02. تجربة 3 أيام</span>
                <span className="px-1.5 py-0.5 bg-purple-500 text-white text-[10px]">{f.rates.trialStartRate}%</span>
              </div>
              <div className="text-3xl font-black text-purple-600 dark:text-purple-400 font-mono">
                {f.totalTrials}
              </div>
              <p className="text-[11px] font-bold text-zinc-500">
                {f.activeTrials} نشط حالياً · {f.finishedTrials} منتهي
              </p>
              <div className="w-full bg-zinc-200 dark:bg-zinc-800 h-2 mt-2">
                <div
                  className="bg-purple-500 h-full"
                  style={{ width: `${Math.min(100, Math.max(5, f.rates.trialStartRate))}%` }}
                ></div>
              </div>
            </div>

            {/* Step 3: Activation */}
            <div className="border-3 border-black dark:border-white p-4 bg-zinc-50 dark:bg-zinc-900 space-y-2 relative">
              <div className="flex items-center justify-between text-xs font-black text-zinc-500">
                <span>03. التفعيل بالشات</span>
                <span className="px-1.5 py-0.5 bg-sky-500 text-white text-[10px]">{f.rates.trialActivationRate}%</span>
              </div>
              <div className="text-3xl font-black text-sky-600 dark:text-sky-400 font-mono">
                {f.activatedTrials}
              </div>
              <p className="text-[11px] font-bold text-zinc-500">
                سألوا ARTORO سؤال فعلي أثناء/بعد التجربة
              </p>
              <div className="w-full bg-zinc-200 dark:bg-zinc-800 h-2 mt-2">
                <div
                  className="bg-sky-500 h-full"
                  style={{ width: `${Math.min(100, Math.max(5, f.rates.trialActivationRate))}%` }}
                ></div>
              </div>
            </div>

            {/* Step 4: Checkout */}
            <div className="border-3 border-black dark:border-white p-4 bg-zinc-50 dark:bg-zinc-900 space-y-2 relative">
              <div className="flex items-center justify-between text-xs font-black text-zinc-500">
                <span>04. بدء الدفع</span>
                <span className="px-1.5 py-0.5 bg-amber-400 text-black text-[10px]">{f.rates.checkoutRate}%</span>
              </div>
              <div className="text-3xl font-black text-amber-500 font-mono">
                {f.checkoutUsers}
              </div>
              <p className="text-[11px] font-bold text-zinc-500">
                أنشأوا {f.totalOrdersCount} طلب دفع في البوابة
              </p>
              <div className="w-full bg-zinc-200 dark:bg-zinc-800 h-2 mt-2">
                <div
                  className="bg-amber-400 h-full"
                  style={{ width: `${Math.min(100, Math.max(5, f.rates.checkoutRate))}%` }}
                ></div>
              </div>
            </div>

            {/* Step 5: Paid Conversion */}
            <div className="border-3 border-black dark:border-white p-4 bg-emerald-50 dark:bg-emerald-950/40 space-y-2 relative ring-2 ring-emerald-500">
              <div className="flex items-center justify-between text-xs font-black text-emerald-700 dark:text-emerald-300">
                <span>05. اشتراك مدفوع 👑</span>
                <span className="px-1.5 py-0.5 bg-emerald-500 text-white text-[10px]">{f.rates.paidConversionRate}%</span>
              </div>
              <div className="text-3xl font-black text-emerald-600 dark:text-emerald-400 font-mono">
                {f.paidCount}
              </div>
              <p className="text-[11px] font-bold text-emerald-800 dark:text-emerald-200">
                {f.foundersCount} عضو مثبت في باقة المؤسسين
              </p>
              <div className="w-full bg-zinc-200 dark:bg-zinc-800 h-2 mt-2">
                <div
                  className="bg-emerald-500 h-full"
                  style={{ width: `${Math.min(100, Math.max(5, f.rates.paidConversionRate * 3))}%` }}
                ></div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 2-Column Section: Lifecycle Email Sequences + Recent Funnel Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Automated Onboarding & Nurturing Sequences */}
        <div className="lg:col-span-6 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 space-y-6 shadow-[6px_6px_0px_rgba(0,0,0,1)]">
          <div className="border-b-2 border-zinc-200 dark:border-zinc-800 pb-3">
            <span className="text-[10px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400 block mb-1">
              AUTOMATED LIFECYCLE
            </span>
            <h2 className="text-lg font-black flex items-center gap-2">
              <Send className="w-5 h-5 text-indigo-500" />
              <span>إيميلات رحلة المسجل الجديد (Onboarding & Nurturing)</span>
            </h2>
          </div>

          <div className="space-y-3">
            {[
              {
                code: "signup_welcome_deep",
                step: "01",
                name: "إيميل الترحيب وتجربة أول سؤال",
                trigger: "فور التسجيل مباشرة",
                status: "مفعّل تلقائياً",
                features: "3 خطوات للبدء + 10 رسائل تليجرام + عرض المؤسسين 50%",
              },
              {
                code: "trial_welcome",
                step: "02",
                name: "اليوم 0: تفعيل تجربة Pro المجانية",
                trigger: "فور بدء الـ 3 أيام تجربة",
                status: "مفعّل تلقائياً",
                features: "توجيه لأول سؤال في الشات + فحص الأسهم وVision AI",
              },
              {
                code: "trial_day1",
                step: "03",
                name: "اليوم 1: حث وتنشيط الأسهم",
                trigger: "بعد 24 ساعة من التجربة",
                status: "مفعّل تلقائياً",
                features: "3 نماذج أسئلة مباشرة على المحفظة والقطاعات",
              },
              {
                code: "trial_day2",
                step: "04",
                name: "اليوم 2: دراسة حالة وصفقات الزخم ⚡",
                trigger: "قبل انتهاء التجربة بـ 24-36 ساعة",
                status: "جديد مفعّل ⭐",
                features: "شرح عملي للصفقات القصيرة والـ Breakout ونظام الوقف 4%",
              },
              {
                code: "trial_expiring",
                step: "05",
                name: "اليوم 3: تنبيه انتهاء التجربة وعرض الخصم",
                trigger: "قبل انتهاء التجربة بـ 12-24 ساعة",
                status: "مفعّل تلقائياً",
                features: "عرض الـ 3 باقات (100 / 500 / 900 ج.م) وتثبيت السعر مدى الحياة",
              },
              {
                code: "abandoned_checkout",
                step: "06",
                name: "استرجاع السلة المتروكة (Abandoned Checkout)",
                trigger: "ساعتين إلى 72 ساعة من فتح صفحة الدفع",
                status: "مفعّل تلقائياً",
                features: "رابط مباشر لإكمال الدفع وتثبيت عرض المؤسسين",
              },
            ].map((seq) => {
              const campaignStat = data?.campaigns.find((c) => c.type === seq.code);
              return (
                <div
                  key={seq.code}
                  className="border-2 border-black dark:border-zinc-800 p-4 bg-zinc-50 dark:bg-zinc-900/60 space-y-2 hover:border-emerald-500 transition-colors"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono font-black px-2 py-0.5 bg-black text-white">
                        {seq.step}
                      </span>
                      <h3 className="text-sm font-black text-zinc-900 dark:text-white">
                        {seq.name}
                      </h3>
                    </div>
                    <span className="text-[10px] font-black uppercase px-2 py-0.5 bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300 border border-emerald-500">
                      {seq.status}
                    </span>
                  </div>

                  <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400">
                    {seq.features}
                  </p>

                  <div className="flex items-center justify-between text-[11px] font-bold text-zinc-500 pt-1 border-t border-zinc-200 dark:border-zinc-800">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5 text-zinc-400" />
                      {seq.trigger}
                    </span>
                    <span className="font-mono">
                      تم إرسال: <strong className="text-zinc-900 dark:text-white">{campaignStat?.sent_count || 0}</strong> إيميل
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Live Recent Signups in Funnel */}
        <div className="lg:col-span-6 border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 space-y-6 shadow-[6px_6px_0px_rgba(0,0,0,1)]">
          <div className="border-b-2 border-zinc-200 dark:border-zinc-800 pb-3 flex items-center justify-between">
            <div>
              <span className="text-[10px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400 block mb-1">
                LIVE ACTIVITY
              </span>
              <h2 className="text-lg font-black flex items-center gap-2">
                <Users className="w-5 h-5 text-blue-500" />
                <span>أحدث المسجلين ومرحلتهم في القمع (Latest Leads)</span>
              </h2>
            </div>
            <span className="text-xs font-mono font-bold text-zinc-500">
              آخر 25 مستخدم
            </span>
          </div>

          <div className="divide-y divide-zinc-200 dark:divide-zinc-800 max-h-[620px] overflow-y-auto">
            {(!data?.recentUsers || data.recentUsers.length === 0) ? (
              <p className="text-xs font-bold text-zinc-400 py-6 text-center">
                لا توجد سجلات مسجلين حالياً.
              </p>
            ) : (
              data.recentUsers.map((u) => (
                <div key={u.id} className="py-3 px-1 flex items-center justify-between gap-3 text-xs">
                  <div className="space-y-0.5">
                    <div className="font-black text-zinc-900 dark:text-white flex items-center gap-2">
                      <span>{u.name}</span>
                      {u.messagesCount > 0 && (
                        <span className="text-[10px] font-mono px-1.5 py-0.2 bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300 border border-sky-400">
                          {u.messagesCount} سؤال شات
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-zinc-400 font-mono">
                      {new Date(u.created_at).toLocaleDateString("ar-EG", {
                        day: "numeric",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>

                  <div className="shrink-0 text-start">
                    <span
                      className={`inline-block px-2.5 py-1 text-[11px] font-black border ${
                        u.isPaid
                          ? "bg-emerald-500 text-white border-black"
                          : u.hasCheckout
                          ? "bg-amber-300 text-black border-black"
                          : u.hasTrial
                          ? "bg-purple-100 text-purple-900 dark:bg-purple-950 dark:text-purple-300 border-purple-500"
                          : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 border-zinc-400"
                      }`}
                    >
                      {u.stage}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
