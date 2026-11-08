"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useLanguage } from "@/contexts/LanguageContext";
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
  HelpCircle,
  Sparkles,
  ArrowRight,
  RefreshCw,
  Check,
  Loader2,
  Eye,
  Lock,
  KeyRound,
  AlertTriangle,
  MessageCircle,
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
  order_id?: string;
  owner_user_id?: string;
}

const TIER_DETAILS = {
  b2b_starter: {
    name_ar: "Starter B2B (جروبات حتى 150 عضو)",
    name_en: "Starter B2B (Up to 150 members)",
    members_ar: "حتى 150 عضو",
    members_en: "Up to 150 members",
    limit: 50,
    price: 1000,
    badgeColor: "bg-blue-400 text-black",
  },
  b2b_pro: {
    name_ar: "Pro VIP B2B (جروبات حتى 500 عضو 🔥)",
    name_en: "Pro VIP B2B (Up to 500 members 🔥)",
    members_ar: "حتى 500 عضو",
    members_en: "Up to 500 members",
    limit: 120,
    price: 1500,
    badgeColor: "bg-emerald-400 text-black",
  },
  b2b_enterprise: {
    name_ar: "Enterprise B2B (جروبات كبرى 💎)",
    name_en: "Enterprise B2B (Enterprise Communities 💎)",
    members_ar: "حتى 1,500 عضو",
    members_en: "Up to 1,500 members",
    limit: 250,
    price: 2500,
    badgeColor: "bg-purple-400 text-black",
  },
};

export default function B2BDashboardClient() {
  const { language } = useLanguage();
  const isAr = language === "ar";
  const { user, loading: authLoading } = useAuth();

  const [license, setLicense] = useState<License | null>(null);
  const [allLicenses, setAllLicenses] = useState<License[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);

  // Form states
  const [signatureInput, setSignatureInput] = useState("");
  const [groupTitleInput, setGroupTitleInput] = useState("");
  const [saving, setSaving] = useState(false);

  // Claim license code state
  const [claimCode, setClaimCode] = useState("");
  const [claiming, setClaiming] = useState(false);

  const fetchLicense = async (specificId?: string) => {
    setLoading(true);
    try {
      const url = specificId ? `/api/b2b/license?license_id=${encodeURIComponent(specificId)}` : "/api/b2b/license";
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) {
        setLicense(null);
        setLoading(false);
        return;
      }
      const data = await res.json();
      if (data.ok && data.license) {
        setLicense(data.license);
        setAllLicenses(data.licenses || [data.license]);
        setIsAdmin(Boolean(data.is_admin));
        setSignatureInput(data.license.custom_signature || "");
        setGroupTitleInput(data.license.group_title || "");
      } else {
        setLicense(null);
        setAllLicenses([]);
        setIsAdmin(Boolean(data.is_admin));
      }
    } catch (err: any) {
      console.error("Error fetching B2B license:", err);
      setLicense(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!authLoading) {
      fetchLicense();
    }
  }, [authLoading, user]);

  const tierInfo = license ? TIER_DETAILS[license.tier] || TIER_DETAILS.b2b_pro : TIER_DETAILS.b2b_pro;

  const usagePercent = license
    ? Math.min(100, Math.round(((license.daily_used || 0) / (license.daily_limit || 1)) * 100))
    : 0;

  const remainingDays = license
    ? Math.max(0, Math.ceil((new Date(license.expires_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24)))
    : 0;

  const isExpired = license ? new Date(license.expires_at) <= new Date() : false;

  const handleSaveSignature = async () => {
    if (!license) return;
    try {
      setSaving(true);
      const res = await fetch("/api/b2b/license", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          license_id: license.id,
          custom_signature: signatureInput,
          group_title: groupTitleInput,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        toast.success(
          isAr
            ? "تم حفظ التوقيع المخصص واسم الجروب بنجاح في قاعدة البيانات!"
            : "Custom signature and group title updated successfully!"
        );
        fetchLicense(license.id);
      } else {
        toast.error(data.error || (isAr ? "فشل حفظ التعديلات" : "Failed to save updates"));
      }
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClaimLicense = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!claimCode.trim()) return;
    try {
      setClaiming(true);
      const res = await fetch("/api/b2b/license", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "claim",
          code: claimCode.trim(),
        }),
      });
      const data = await res.json();
      if (data.ok) {
        toast.success(isAr ? "تم ربط الترخيص بحسابك بنجاح!" : "License successfully linked to your account!");
        setClaimCode("");
        fetchLicense();
      } else {
        toast.error(data.error || (isAr ? "كود غير صحيح" : "Invalid license code"));
      }
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setClaiming(false);
    }
  };

  const copyToClipboard = (text: string, labelAr: string, labelEn: string) => {
    navigator.clipboard.writeText(text);
    toast.success(isAr ? `تم نسخ ${labelAr}` : `Copied ${labelEn}`);
  };

  const activationCommand = license ? `/activate ${license.id.slice(0, 8)}` : "/activate";

  return (
    <div
      className="min-h-screen bg-zinc-50 dark:bg-black text-zinc-950 dark:text-zinc-100 py-8 px-4 sm:px-6 lg:px-8 transition-colors duration-200"
      dir={isAr ? "rtl" : "ltr"}
    >
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Loading State */}
        {loading || authLoading ? (
          <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-12 text-center shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#fff]">
            <Loader2 className="w-10 h-10 animate-spin text-emerald-500 mx-auto" />
            <p className="text-sm font-black mt-3 text-zinc-700 dark:text-zinc-300">
              {isAr ? "جاري جلب بيانات ترخيص البوت من سوبابيز..." : "Fetching live bot license data from Supabase..."}
            </p>
          </div>
        ) : !user ? (
          /* Unauthenticated State */
          <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-8 sm:p-12 text-center shadow-[8px_8px_0px_#000] dark:shadow-[8px_8px_0px_#fff] space-y-4">
            <div className="w-16 h-16 border-4 border-black dark:border-white bg-amber-300 text-black flex items-center justify-center mx-auto shadow-[4px_4px_0px_#000]">
              <Lock className="w-8 h-8" />
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-zinc-900 dark:text-white">
              {isAr ? "يرجى تسجيل الدخول لعرض رخصة البوت الخاصة بقناتك" : "Please Sign In to Access Your Bot Dashboard"}
            </h1>
            <p className="text-xs sm:text-sm text-zinc-600 dark:text-zinc-400 font-bold max-w-lg mx-auto leading-relaxed">
              {isAr
                ? "لوحة تحكم B2B مخصصة لأصحاب القنوات والمجموعات لإدارة رخصهم المعتمدة، استهلاك الكوتة اليومية، وتعديل التوقيع التسويقي."
                : "The B2B Dashboard allows channel and group owners to manage active licenses, track daily quotas, and configure custom signature footers."}
            </p>
            <div className="flex flex-wrap justify-center gap-3 pt-4">
              <Link
                href="/login?redirect=/b2b/dashboard"
                className="border-3 border-black dark:border-white bg-emerald-500 hover:bg-emerald-600 text-black font-black px-6 py-3 text-xs uppercase shadow-[3px_3px_0px_#000] active:translate-y-0.5"
              >
                {isAr ? "تسجيل الدخول الآن" : "Sign In Now"}
              </Link>
              <Link
                href="/pricing?mode=b2b"
                className="border-3 border-black dark:border-white bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 text-zinc-900 dark:text-white font-black px-6 py-3 text-xs uppercase shadow-[3px_3px_0px_#000] active:translate-y-0.5"
              >
                {isAr ? "استعراض باقات أصحاب القنوات (B2B)" : "Browse B2B Channel Plans"}
              </Link>
            </div>
          </div>
        ) : !license ? (
          /* Authenticated but No License in Supabase */
          <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-8 sm:p-12 shadow-[8px_8px_0px_#000] dark:shadow-[8px_8px_0px_#fff] space-y-6">
            <div className="text-center space-y-3">
              <div className="w-16 h-16 border-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-white flex items-center justify-center mx-auto shadow-[4px_4px_0px_#000]">
                <Bot className="w-8 h-8 text-emerald-500" />
              </div>
              <h1 className="text-2xl sm:text-3xl font-black text-zinc-900 dark:text-white">
                {isAr ? "لا توجد رخصة B2B نشطة مربوطة بحسابك" : "No Active B2B License Found For Your Account"}
              </h1>
              <p className="text-xs sm:text-sm text-zinc-600 dark:text-zinc-400 font-bold max-w-xl mx-auto leading-relaxed">
                {isAr
                  ? `حسابك (${user.email}) لا يملك رخصة نشطة في قاعدة البيانات حتى الآن. يمكنك ترخيص البوت فوراً لقناتك أو ربط رخصة سابقة عبر كود التفعيل.`
                  : `Your account (${user.email}) has no active B2B licenses in Supabase. You can subscribe to license the bot for your group or claim an existing order code.`}
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t-2 border-zinc-200 dark:border-zinc-800">
              {/* Option 1: Buy new license */}
              <div className="border-3 border-black dark:border-white p-6 bg-emerald-50 dark:bg-emerald-950/30 space-y-3">
                <span className="text-[10px] font-black uppercase tracking-wider text-emerald-700 dark:text-emerald-400 block">
                  {isAr ? "الخيار الأول: اشتراك جديد" : "OPTION 1: SUBSCRIBE"}
                </span>
                <h3 className="text-lg font-black text-zinc-900 dark:text-white">
                  {isAr ? "اختر باقة لقناتك من 1,000 ج.م/شهر" : "Choose a Plan Starting from 1,000 EGP/mo"}
                </h3>
                <p className="text-xs font-bold text-zinc-600 dark:text-zinc-400">
                  {isAr
                    ? "يتوفر 3 خطط (Starter 150 عضو، Pro VIP 500 عضو، و Enterprise 1,500 عضو) مع تفعيل فوري وتوقيع مخصص باسم قناتك."
                    : "Choose between Starter (150 members), Pro VIP (500 members), or Enterprise (1,500 members) with immediate activation."}
                </p>
                <Link
                  href="/pricing?mode=b2b"
                  className="inline-flex items-center gap-2 border-2 border-black bg-emerald-500 hover:bg-emerald-600 text-black font-black px-4 py-2.5 text-xs uppercase shadow-[2px_2px_0px_#000] active:translate-y-0.5 mt-2"
                >
                  <span>{isAr ? "عرض باقات القنوات والأسعار" : "View B2B Plans & Pricing"}</span>
                  <ArrowRight className={`w-3.5 h-3.5 ${isAr ? "rotate-180" : ""}`} />
                </Link>
              </div>

              {/* Option 2: Link by code */}
              <div className="border-3 border-black dark:border-white p-6 bg-zinc-50 dark:bg-zinc-800 space-y-3">
                <span className="text-[10px] font-black uppercase tracking-wider text-zinc-500 block">
                  {isAr ? "الخيار الثاني: تفعيل رخصة سابقة" : "OPTION 2: CLAIM LICENSE"}
                </span>
                <h3 className="text-lg font-black text-zinc-900 dark:text-white">
                  {isAr ? "لديك كود ترخيص أو رقم طلب؟" : "Have a License Code or Order ID?"}
                </h3>
                <p className="text-xs font-bold text-zinc-600 dark:text-zinc-400">
                  {isAr
                    ? "إذا كنت قد قمت بالدفع مسبقاً أو تم منحك ترخيصاً من الإدارة، أدخل الكود لربطه بحسابك:"
                    : "If you purchased previously or received an admin grant, enter your license code to bind it:"}
                </p>
                <form onSubmit={handleClaimLicense} className="flex gap-2 pt-1">
                  <input
                    type="text"
                    required
                    value={claimCode}
                    onChange={(e) => setClaimCode(e.target.value)}
                    placeholder={isAr ? "أدخل الكود مثل: B2B-LIVE-2026" : "Enter code e.g. B2B-LIVE-2026"}
                    className="flex-1 border-2 border-black dark:border-white p-2 text-xs font-mono font-bold bg-white dark:bg-zinc-900 text-zinc-900 dark:text-white outline-none"
                    dir="ltr"
                  />
                  <button
                    type="submit"
                    disabled={claiming}
                    className="border-2 border-black dark:border-white bg-zinc-900 text-white dark:bg-white dark:text-black px-4 py-2 text-xs font-black uppercase hover:bg-emerald-500 hover:text-black transition-colors"
                  >
                    {claiming ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : isAr ? "ربط" : "Link"}
                  </button>
                </form>
              </div>
            </div>
          </div>
        ) : (
          /* Live Authenticated License State (Real Supabase Data) */
          <>
            {/* Admin Switcher Bar (If viewing as Admin) */}
            {isAdmin && allLicenses.length > 1 && (
              <div className="border-3 border-black dark:border-white bg-fuchsia-200 dark:bg-fuchsia-950/60 p-3 shadow-[3px_3px_0px_#000] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs font-black">
                <span className="flex items-center gap-1.5 text-fuchsia-900 dark:text-fuchsia-200">
                  <ShieldCheck className="w-4 h-4" />
                  {isAr
                    ? "أنت تشاهد هذه اللوحة بصلاحيات الأدمن — اختر الرخصة المراد فحصها:"
                    : "Viewing with Administrator Privileges — Select license to inspect:"}
                </span>
                <select
                  value={license.id}
                  onChange={(e) => fetchLicense(e.target.value)}
                  className="border-2 border-black dark:border-white bg-white dark:bg-zinc-900 px-3 py-1.5 text-xs font-bold text-zinc-900 dark:text-white outline-none"
                >
                  {allLicenses.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.group_title || l.order_id || l.id.slice(0, 8)} ({l.tier})
                    </option>
                  ))}
                </select>
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
                        {isAr ? "لوحة إدارة رخصة B2B الحقيقية" : "LIVE B2B BOT LICENSE"}
                      </span>
                      <h1 className="text-2xl sm:text-3xl font-black text-zinc-900 dark:text-white">
                        {isAr ? "لوحة تحكم ترخيص بوت التليجرام للقنوات" : "B2B Telegram Bot Channel Dashboard"}
                      </h1>
                    </div>
                  </div>
                  <p className="text-xs text-zinc-600 dark:text-zinc-400 font-bold max-w-2xl leading-relaxed">
                    {isAr
                      ? "تحكم بالكامل في إعدادات البوت داخل مجموعتك، راقب استهلاك الأعضاء اليومي، وخصص التوقيع التسويقي الذي يظهر أسفل كل تحليل."
                      : "Manage your group bot settings, monitor member daily query consumption, and customize your promotional signature footer."}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <div className="border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 px-4 py-2 text-center">
                    <span className="text-[10px] text-zinc-500 font-bold uppercase block">
                      {isAr ? "الباقة المفعلة" : "Active Plan"}
                    </span>
                    <span className="text-xs font-black text-emerald-600 dark:text-emerald-400">
                      {isAr ? tierInfo.name_ar : tierInfo.name_en}
                    </span>
                  </div>
                  <div className="border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 px-4 py-2 text-center">
                    <span className="text-[10px] text-zinc-500 font-bold uppercase block">
                      {isAr ? "الحالة" : "Status"}
                    </span>
                    <span
                      className={`text-xs font-black flex items-center gap-1 justify-center ${
                        license.status === "active" && !isExpired
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-amber-600 dark:text-amber-400"
                      }`}
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      {license.status === "active" && !isExpired
                        ? isAr
                          ? "نشط ومفعل"
                          : "Active & Ready"
                        : isAr
                        ? "موقوف أو منتهي"
                        : "Paused / Expired"}
                    </span>
                  </div>
                  <div className="border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 px-4 py-2 text-center">
                    <span className="text-[10px] text-zinc-500 font-bold uppercase block">
                      {isAr ? "الأيام المتبقية" : "Days Remaining"}
                    </span>
                    <span className="text-xs font-black text-zinc-900 dark:text-white font-mono">
                      {remainingDays} {isAr ? "يوماً" : "days"}
                    </span>
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
                      {isAr ? "استهلاك الاستفسارات اليومي للجروب" : "Group Daily Query Consumption"}
                    </h2>
                  </div>
                  <span className="border-2 border-black bg-amber-300 text-black px-2 py-0.5 text-[10px] font-black font-mono">
                    {license.daily_used || 0} / {license.daily_limit} {isAr ? "استفسار" : "queries"}
                  </span>
                </div>

                {/* Progress Bar */}
                <div className="space-y-2">
                  <div className="flex justify-between text-xs font-bold">
                    <span className="text-zinc-600 dark:text-zinc-400">
                      {isAr ? "نسبة الاستهلاك اليومي:" : "Daily Consumption:"}
                    </span>
                    <span className="font-mono font-black text-emerald-600 dark:text-emerald-400">
                      {usagePercent}%
                    </span>
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
                    <span>
                      {isAr
                        ? `المتبقي اليوم: ${Math.max(0, license.daily_limit - (license.daily_used || 0))} استفسار`
                        : `Remaining today: ${Math.max(0, license.daily_limit - (license.daily_used || 0))} queries`}
                    </span>
                    <span>
                      {isAr ? `سعة الجروب: ${tierInfo.members_ar}` : `Group capacity: ${tierInfo.members_en}`}
                    </span>
                  </div>
                </div>

                {/* Quota Rules Box */}
                <div className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800/60 p-3.5 space-y-1.5 text-xs font-bold text-zinc-700 dark:text-zinc-300">
                  <div className="flex items-center gap-1.5 text-zinc-900 dark:text-white font-black">
                    <ShieldCheck className="w-4 h-4 text-emerald-500" />
                    <span>
                      {isAr
                        ? "حماية الاستخدام العادل (Fair Use Policy) مفعّلة:"
                        : "Fair Use Policy Protection Active:"}
                    </span>
                  </div>
                  <ul className="list-disc list-inside space-y-1 text-[11px] text-zinc-600 dark:text-zinc-400 pr-1">
                    <li>
                      {isAr
                        ? "كولد داون 90 ثانية للعضو الواحد بين كل سؤال وآخر لمنع الإغراق."
                        : "90-second cooldown per member between queries to prevent spam."}
                    </li>
                    <li>
                      {isAr
                        ? "حد أقصى 15 استفسار للشخص الواحد يومياً لضمان توزيع الحصة على جميع الأعضاء."
                        : "15 queries max per member daily to ensure fair distribution across the group."}
                    </li>
                    <li>
                      {isAr
                        ? "يتصفر العداد اليومي تلقائياً كل ليلة في تمام الساعة 12:00 منتصف الليل بتوقيت القاهرة."
                        : "Daily quota automatically resets at 12:00 Midnight Cairo time."}
                    </li>
                  </ul>
                </div>
              </div>

              {/* Telegram Group Connection Card */}
              <div className="lg:col-span-6 border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 shadow-[5px_5px_0px_#000] dark:shadow-[5px_5px_0px_#fff] space-y-4">
                <div className="flex items-center justify-between border-b-2 border-zinc-200 dark:border-zinc-800 pb-3">
                  <div className="flex items-center gap-2">
                    <Bot className="w-5 h-5 text-emerald-500" />
                    <h2 className="text-base font-black text-zinc-900 dark:text-white">
                      {isAr ? "حالة ربط المجموعة على تليجرام" : "Telegram Group Connection Status"}
                    </h2>
                  </div>
                  {license.telegram_chat_id ? (
                    <span className="inline-flex items-center gap-1 border-2 border-black bg-emerald-300 text-black px-2 py-0.5 text-[10px] font-black">
                      <Check className="w-3 h-3" />
                      {isAr ? "متصل وجاهز للرد" : "Connected & Ready"}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 border-2 border-black bg-amber-300 text-black px-2 py-0.5 text-[10px] font-black">
                      <AlertTriangle className="w-3 h-3" />
                      {isAr ? "بانتظار أمر التفعيل" : "Pending Activation"}
                    </span>
                  )}
                </div>

                <div className="space-y-3">
                  <div>
                    <label className="block text-[11px] font-black text-zinc-500 mb-1">
                      {isAr ? "اسم الجروب أو القناة" : "Group / Channel Title"}
                    </label>
                    <input
                      type="text"
                      value={groupTitleInput}
                      onChange={(e) => setGroupTitleInput(e.target.value)}
                      placeholder={isAr ? "مثلاً: قناة توصيات الأسهم المصرية 📊" : "e.g. VIP EGX Stock Signals 📊"}
                      className="w-full border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800 px-3.5 py-2 text-xs font-bold outline-none focus:ring-2 focus:ring-emerald-500 text-zinc-900 dark:text-white"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-black text-zinc-500 mb-1">
                      {isAr ? "معرف الجروب الرقمي (Chat ID)" : "Telegram Chat ID"}
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        readOnly
                        value={
                          license.telegram_chat_id
                            ? String(license.telegram_chat_id)
                            : isAr
                            ? "بانتظار أمر التفعيل في الجروب"
                            : "Awaiting activation command in group"
                        }
                        className="flex-1 border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 px-3.5 py-2 font-mono text-xs font-black text-zinc-900 dark:text-white"
                        dir="ltr"
                      />
                      {license.telegram_chat_id && (
                        <button
                          onClick={() => copyToClipboard(String(license.telegram_chat_id), "Chat ID", "Chat ID")}
                          className="border-2 border-black dark:border-white bg-zinc-200 hover:bg-zinc-300 dark:bg-zinc-700 p-2 text-xs font-bold"
                          title={isAr ? "نسخ" : "Copy"}
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
                      <span>
                        {isAr ? "خطوات ربط أو تفعيل البوت في مجموعتك:" : "Steps to activate bot in your group:"}
                      </span>
                    </div>
                    <div className="space-y-2 text-[11px] text-zinc-700 dark:text-zinc-300 font-bold">
                      <div className="flex items-center justify-between gap-2">
                        <span>
                          {isAr
                            ? "1. أضف البوت @egxbots_bot لمجموعتك وارفعه مشرفاً (Admin)."
                            : "1. Add @egxbots_bot to your group and promote to Admin."}
                        </span>
                        <a
                          href="https://t.me/egxbots_bot?startgroup=true"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="border border-black bg-emerald-500 text-black px-2 py-0.5 text-[10px] font-black shrink-0 hover:bg-emerald-600 inline-flex items-center gap-1"
                        >
                          <span>{isAr ? "إضافة البوت" : "Add Bot"}</span>
                          <ExternalLink className="w-2.5 h-2.5" />
                        </a>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span>
                          {isAr ? "2. اكتب في الجروب أمر التفعيل:" : "2. Send activation command in group:"}
                        </span>
                        <button
                          onClick={() =>
                            copyToClipboard(activationCommand, "أمر التفعيل", "Activation Command")
                          }
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
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b-2 border-zinc-200 dark:border-zinc-800 pb-3">
                <div className="flex items-center gap-2">
                  <Edit3 className="w-5 h-5 text-emerald-500" />
                  <div>
                    <h2 className="text-lg font-black text-zinc-900 dark:text-white">
                      {isAr
                        ? "تعديل سطر التوقيع المخصص (Custom Signature)"
                        : "Customize Promotional Signature Footer"}
                    </h2>
                    <p className="text-xs text-zinc-500 font-bold">
                      {isAr
                        ? "هذا السطر يظهر أسفل كل رد وتحليل للبوت داخل مجموعتك لترويج قناتك وبناء براندك أمام المشتركين"
                        : "This line appears beneath every bot analysis in your group to promote your brand to members"}
                    </p>
                  </div>
                </div>

                <button
                  onClick={handleSaveSignature}
                  disabled={saving}
                  className="flex items-center justify-center gap-2 border-2 border-black dark:border-white bg-emerald-500 hover:bg-emerald-600 text-black font-black px-5 py-2.5 text-xs uppercase shadow-[2px_2px_0px_#000] active:translate-y-0.5 shrink-0"
                >
                  {saving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Save className="w-4 h-4" />
                  )}
                  <span>{saving ? (isAr ? "جاري الحفظ..." : "Saving...") : isAr ? "حفظ التوقيع الآن" : "Save Signature"}</span>
                </button>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                {/* Input Form Column */}
                <div className="lg:col-span-6 space-y-3">
                  <label className="block text-xs font-black text-zinc-700 dark:text-zinc-300">
                    {isAr
                      ? "اكتب نص التوقيع التسويقي المخصص (بحد أقصى 150 حرفاً):"
                      : "Enter promotional signature text (Max 150 characters):"}
                  </label>
                  <textarea
                    rows={3}
                    maxLength={150}
                    value={signatureInput}
                    onChange={(e) => setSignatureInput(e.target.value)}
                    placeholder={
                      isAr
                        ? "مثلاً: 📊 تم التحليل بواسطة بوت قناة التوصيات الذهبية بالتعاون مع EGX BOTS"
                        : "e.g. 📊 Analysis powered by Golden Signals Channel in partnership with EGX BOTS"
                    }
                    className="w-full border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800 p-3.5 text-xs font-bold outline-none focus:ring-2 focus:ring-emerald-500 text-zinc-900 dark:text-white leading-relaxed"
                  />
                  <div className="flex items-center justify-between text-[11px] text-zinc-500 font-mono">
                    <span>{signatureInput.length} / 150 {isAr ? "حرفاً" : "chars"}</span>
                    <span>{isAr ? "يدعم الرموز التعبيرية (Emojis) ✨" : "Supports Emojis ✨"}</span>
                  </div>

                  {/* Suggestions Chips */}
                  <div className="space-y-1.5 pt-2">
                    <span className="text-[11px] font-black text-zinc-500 block">
                      {isAr ? "نماذج توقيع مقترحة (اضغط للتطبيق):" : "Suggested presets (click to apply):"}
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {(isAr
                        ? [
                            "📊 تم التحليل بواسطة بوت قناتنا بالتعاون مع EGX BOTS",
                            "⚡ إشارات خاصة بأعضاء قناة VIP Signals بالتعاون مع EGX BOTS",
                            "🎯 تحليلات البورصة المصرية الحصرية لقناتنا بالتعاون مع EGX BOTS",
                          ]
                        : [
                            "📊 Analysis powered by our channel in partnership with EGX BOTS",
                            "⚡ Exclusive member insights powered by VIP Signals & EGX BOTS",
                            "🎯 Institutional Egyptian market analytics by our VIP community & EGX BOTS",
                          ]
                      ).map((preset, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => setSignatureInput(preset)}
                          className="border border-zinc-300 dark:border-zinc-700 bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 px-2 py-1 text-[10px] font-bold text-zinc-700 dark:text-zinc-300 text-start transition-colors"
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
                      {isAr ? "معاينة حية فورية (شكل الرد داخل تليجرام):" : "Live Real-Time Preview (Telegram message mockup):"}
                    </span>
                    <span className="text-[10px] text-emerald-500 font-mono">
                      {isAr ? "تحديث فوري ⚡" : "Instant Update ⚡"}
                    </span>
                  </div>

                  {/* Telegram Dark Bubble Mockup */}
                  <div className="border-4 border-black dark:border-white bg-[#182533] text-white p-4 font-sans rounded-none shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] space-y-3">
                    {/* Simulated User Question */}
                    <div className="bg-[#243447] p-2.5 border-r-4 border-emerald-400 text-xs space-y-1">
                      <div className="font-bold text-emerald-400 text-[11px] flex items-center justify-between">
                        <span>{isAr ? "أحد أعضاء الجروب:" : "Group Member:"}</span>
                        <span className="text-[10px] text-zinc-400 font-mono">11:42 AM</span>
                      </div>
                      <div className="font-mono text-zinc-200 text-xs">
                        {isAr ? "@egxbots_bot تحليل سهم السويدي إليكتريك؟" : "@egxbots_bot analyze CIB stock"}
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

                      {isAr ? (
                        <div className="space-y-1.5 text-zinc-200 leading-relaxed font-sans text-xs">
                          <p className="font-bold">
                            📈 <b>سهم السويدي إليكتريك (SWDY.CA)</b>
                          </p>
                          <p>• السعر الحالي: <b>48.20 ج.م</b> (+1.85%)</p>
                          <p>• الاتجاه الفني: <b>صاعد متوسط المدى</b> مع اختراق مقاومة 47.50 ج.م.</p>
                          <p>• مستويات الدعم: 47.10 - 46.50 ج.م | المقاومة القادمة: 50.20 ج.م</p>
                          <p>• مؤشر السيولة: <b>شراء تجميعي قوي (72%)</b> ⚡</p>
                        </div>
                      ) : (
                        <div className="space-y-1.5 text-zinc-200 leading-relaxed font-sans text-xs">
                          <p className="font-bold">
                            📈 <b>Commercial International Bank (COMI.CA)</b>
                          </p>
                          <p>• Last Price: <b>84.50 EGP</b> (+1.20%)</p>
                          <p>• Technical Trend: <b>Medium-term Bullish</b> with breakout above 83.00 EGP.</p>
                          <p>• Key Supports: 82.00 - 80.50 EGP | Next Resistance: 88.00 EGP</p>
                          <p>• Accumulation Flow: <b>Strong Inflow (74%)</b> ⚡</p>
                        </div>
                      )}

                      {/* The Custom Signature Line */}
                      <div className="border-t border-[#3b4c5e] pt-2 mt-2">
                        <div className="text-[11px] font-bold text-amber-300 bg-[#1f2d3d] p-2 border-r-2 border-amber-400">
                          {signatureInput.trim() ||
                            (isAr
                              ? "✍️ [اكتب توقيعك في الصندوق المقابل وسيظهر هنا فوراً...]"
                              : "✍️ [Enter your signature in the box to preview it here...]")}
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
                  {isAr ? "كيف يتفاعل أعضاء مجموعتك مع البوت؟" : "How Group Members Interact with the Bot"}
                </h3>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2 text-xs font-bold text-zinc-700 dark:text-zinc-300">
                <div className="border-2 border-black dark:border-white p-3.5 bg-zinc-50 dark:bg-zinc-800/40 space-y-1.5">
                  <span className="font-black text-zinc-900 dark:text-white block">
                    {isAr ? "1. المنشن الصريح (@)" : "1. Direct Mention (@)"}
                  </span>
                  <p className="text-[11px] text-zinc-600 dark:text-zinc-400">
                    {isAr
                      ? "يكتب العضو: @egxbots_bot سهم التجاري الدولي فيرد البوت مباشرة بتحليل فوري شامل للسهم."
                      : "Members type: @egxbots_bot COMI to get instant, full technical analysis."}
                  </p>
                </div>

                <div className="border-2 border-black dark:border-white p-3.5 bg-zinc-50 dark:bg-zinc-800/40 space-y-1.5">
                  <span className="font-black text-zinc-900 dark:text-white block">
                    {isAr ? "2. الأوامر المباشرة (/)" : "2. Bot Commands (/)"}
                  </span>
                  <p className="text-[11px] text-zinc-600 dark:text-zinc-400">
                    {isAr
                      ? "يدعم البوت أوامر مثل: /ask أو /analyze أو !سهم لتحليل أي سهم أو مقارنة سهمين."
                      : "Supports commands such as /ask, /analyze, or !سهم to review any EGX stock."}
                  </p>
                </div>

                <div className="border-2 border-black dark:border-white p-3.5 bg-zinc-50 dark:bg-zinc-800/40 space-y-1.5">
                  <span className="font-black text-zinc-900 dark:text-white block">
                    {isAr ? "3. الرد المباشر (Reply)" : "3. Direct Reply"}
                  </span>
                  <p className="text-[11px] text-zinc-600 dark:text-zinc-400">
                    {isAr
                      ? "إذا عمل العضو Reply على أي رسالة تحليل سابقة للبوت وسأله عن وقف الخسارة أو الهدف، يستجيب البوت فوراً في نفس السياق."
                      : "Replying directly to any previous bot message allows members to ask follow-up questions in context."}
                  </p>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
