"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLanguage } from "@/contexts/LanguageContext";
import { useMarket } from "@/contexts/MarketContext";
import { useAuth } from "@/contexts/AuthContext";
import { useAffiliate } from "@/contexts/AffiliateContext";
import {
  Copy,
  Check,
  Sparkles,
  Wallet,
  Users,
  MousePointerClick,
  TrendingUp,
  Share2,
  Loader2,
  ShieldCheck,
  ArrowLeft,
  ArrowRight,
  Gift,
  Smartphone,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

function normalizeAffiliatePhone(raw: string): string {
  let clean = raw.trim().replace(/[\s\-()]/g, "");
  if (clean.startsWith("00")) {
    clean = `+${clean.slice(2)}`;
  }
  if (/^\+?20(1[0125]\d{8})$/.test(clean)) {
    return `0${clean.replace(/^\+?20/, "")}`;
  }
  if (/^05\d{8}$/.test(clean)) {
    return `+966${clean.slice(1)}`;
  }
  if (/^(966|971|974|965|973|968)\d{7,9}$/.test(clean)) {
    return `+${clean}`;
  }
  return clean;
}

function isValidAffiliatePhone(normalized: string): boolean {
  if (!normalized) return false;
  return /^01[0125]\d{8}$/.test(normalized) || /^(\+?[1-9]\d{7,14})$/.test(normalized);
}

function formatReferralPlanLabel(planId: string, isAr: boolean): string {
  const clean = (planId || "").trim().toLowerCase();
  const labels: Record<string, [string, string]> = {
    chat_only: ["الشات الذكي (AI Chat)", "AI Chat Pro"],
    vip_only: ["تليجرام VIP فقط", "VIP Telegram Only"],
    pro: ["الباقة الشاملة Pro", "Pro Full Bundle"],
    pro_renewal: ["تجديد Pro الشاملة", "Pro Renewal"],
    pro_6m: ["Pro الشاملة (6 شهور)", "Pro Bundle (6M)"],
    pro_1y: ["Pro الشاملة (سنوي)", "Pro Bundle (1Y)"],
    lifetime: ["مدى الحياة VIP", "Lifetime VIP"],
    b2b_starter: ["قنوات B2B Starter", "B2B Starter"],
    b2b_pro: ["قنوات B2B Pro VIP", "B2B Pro VIP"],
    b2b_enterprise: ["قنوات B2B Enterprise", "B2B Enterprise"],
  };
  const pair = labels[clean];
  return pair ? (isAr ? pair[0] : pair[1]) : planId;
}

export default function AffiliateClient() {
  const { language } = useLanguage();
  const isAr = language === "ar";
  const { market, isSaudi, isUae, isQatar, isGccChatOnly } = useMarket();
  const isGulfMarket = isSaudi || isGccChatOnly;
  const brandName = isSaudi ? "TASI BOTS" : isUae ? "UAE BOTS" : isQatar ? "QSE BOTS" : "EGX BOTS";
  const marketAr = isSaudi
    ? "السوق السعودي (تاسي)"
    : isUae
    ? "سوق الإمارات (دبي وأبوظبي)"
    : isQatar
    ? "بورصة قطر (QSE)"
    : "البورصة المصرية (EGX)";
  const marketEn = isSaudi
    ? "Saudi Stock Market (TASI)"
    : isUae
    ? "UAE Markets (DFM & ADX)"
    : isQatar
    ? "Qatar Stock Exchange (QSE)"
    : "Egyptian Exchange (EGX)";
  const defaultPayoutMethod = isSaudi ? "stc_pay" : isGccChatOnly ? "bank_transfer" : "vodafone_cash";
  const { user, loading: authLoading } = useAuth();
  const {
    affiliate,
    referrals,
    loading: affiliateLoading,
    isRefreshing,
    refreshAffiliate,
    saveAffiliateSettings,
  } = useAffiliate();

  const [saving, setSaving] = useState(false);
  const [codeInput, setCodeInput] = useState("");
  const [phoneInput, setPhoneInput] = useState("");
  const [paymentMethodInput, setPaymentMethodInput] = useState("vodafone_cash");
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedCode, setCopiedCode] = useState(false);

  // Sync inputs from context when affiliate data is available
  useEffect(() => {
    if (affiliate) {
      setCodeInput((prev) => (prev ? prev : affiliate.code || ""));
      setPhoneInput((prev) => (prev ? prev : affiliate.phone || ""));
      setPaymentMethodInput((prev) =>
        affiliate.payment_method ? affiliate.payment_method : prev || defaultPayoutMethod
      );
    }
  }, [affiliate, defaultPayoutMethod]);

  const loading = authLoading || (affiliateLoading && !affiliate);

  const normalizedPhoneInput = normalizeAffiliatePhone(phoneInput);
  const isPhoneEmpty = normalizedPhoneInput.length === 0;
  const isPhoneInputValid = !isPhoneEmpty && isValidAffiliatePhone(normalizedPhoneInput);
  const canSaveSettings =
    Boolean(codeInput.trim().length >= 3) && (isPhoneEmpty || isPhoneInputValid);
  const hasSavedWalletPhone = Boolean(
    affiliate?.phone && isValidAffiliatePhone(normalizeAffiliatePhone(affiliate.phone))
  );

  const marketQuerySuffix = market !== "egx" ? `&market=${encodeURIComponent(market)}` : "";
  const referralUrl = affiliate
    ? `https://egxbots.com/pricing?ref=${encodeURIComponent(affiliate.code)}${marketQuerySuffix}`
    : `https://egxbots.com/pricing${market !== "egx" ? `?market=${encodeURIComponent(market)}` : ""}`;

  const handleCopyLink = () => {
    navigator.clipboard.writeText(referralUrl);
    setCopiedLink(true);
    toast.success(isAr ? "تم نسخ رابط الإحالة الخاص بك بنجاح! 🔗" : "Referral link copied!");
    setTimeout(() => setCopiedLink(false), 2000);
  };

  const handleCopyCode = () => {
    if (!affiliate) return;
    navigator.clipboard.writeText(affiliate.code);
    setCopiedCode(true);
    toast.success(isAr ? `تم نسخ الكود (${affiliate.code})` : "Promo code copied!");
    setTimeout(() => setCopiedCode(false), 2000);
  };

  const handleShareWhatsApp = () => {
    if (!affiliate) return;
    const text = isAr
      ? `استخدم منصة ${brandName} لتحليل أسهم ${marketAr} بالذكاء الاصطناعي ورادار السيولة اللحظي 🚀\nاشترك الآن من الرابط واحصل على خصم ${affiliate.discount_percent}% بكود (${affiliate.code}):\n${referralUrl}`
      : `Join ${brandName} AI stock scanner for the ${marketEn} and get ${affiliate.discount_percent}% OFF with code (${affiliate.code}):\n${referralUrl}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener,noreferrer");
  };

  const handleShareTelegram = () => {
    if (!affiliate) return;
    const text = isAr
      ? `منصة ${brandName} لتحليل أسهم ${marketAr} بالذكاء الاصطناعي 🚀 خصم ${affiliate.discount_percent}% بكود (${affiliate.code})`
      : `${brandName} AI Stock Analysis (${marketEn}) — ${affiliate.discount_percent}% OFF with code (${affiliate.code})`;
    window.open(
      `https://t.me/share/url?url=${encodeURIComponent(referralUrl)}&text=${encodeURIComponent(text)}`,
      "_blank",
      "noopener,noreferrer"
    );
  };

  const handleSaveSettings = async () => {
    if (!isPhoneEmpty && !isPhoneInputValid) {
      toast.error(
        isAr
          ? "أدخل رقم موبايل صحيح (مصري 01XXXXXXXXX أو سعودي/دولي مثل +9665XXXXXXXX)"
          : "Enter a valid mobile number (e.g. 01012345678 or +9665XXXXXXXX)"
      );
      return;
    }
    setSaving(true);
    try {
      const res = await saveAffiliateSettings({
        code: codeInput.trim().toUpperCase(),
        phone: normalizedPhoneInput,
        payment_method: paymentMethodInput || defaultPayoutMethod,
      });
      if (!res.success) {
        throw new Error(res.error || (isAr ? "تعذر حفظ البيانات" : "Could not save settings"));
      }
      if (res.affiliate) {
        setCodeInput(res.affiliate.code);
        setPhoneInput(res.affiliate.phone || "");
        if (res.affiliate.payment_method) {
          setPaymentMethodInput(res.affiliate.payment_method);
        }
      }
      toast.success(
        isAr
          ? "✓ تم حفظ إعدادات الشريك بنجاح!"
          : "✓ Partner settings saved!"
      );
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const unpaidBalance = affiliate
    ? Math.max(0, Number(affiliate.total_commission_egp || 0) - Number(affiliate.paid_commission_egp || 0))
    : 0;

  return (
    <div className="min-h-[75vh] py-10 sm:py-14 px-4" dir={isAr ? "rtl" : "ltr"}>
      <div className="max-w-5xl mx-auto space-y-8">
        {/* Hero Header */}
        <div className="border-4 border-black dark:border-white bg-gradient-to-br from-emerald-500 via-emerald-600 to-teal-700 text-white p-6 sm:p-10 shadow-[8px_8px_0px_rgba(0,0,0,1)] dark:shadow-[8px_8px_0px_#ffffff] relative overflow-hidden">
          <div className="max-w-3xl space-y-3 relative z-10">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 border-2 border-black bg-[#FFE600] text-black text-xs font-black uppercase tracking-wider shadow-[2px_2px_0px_#000]">
              <Sparkles className="w-3.5 h-3.5 fill-black" />
              {isAr ? "برنامج شركاء النجاح · عمولة 25% كاش" : "PARTNER PROGRAM · 25% CASH COMMISSION"}
            </span>
            <h1 className="text-2xl sm:text-4xl font-black leading-tight text-white">
              {isAr
                ? "شارك رابط الإحالة الخاص بك واربح 25% كاش على محفظتك الإلكترونية 💰"
                : "Share Your Referral Link & Earn 25% Cash on Your Mobile Wallet 💰"}
            </h1>
            <p className="text-xs sm:text-sm font-bold text-emerald-50 leading-relaxed">
              {isAr
                ? "كل مستخدم يسجل ويشترك في أي باقة مدفوعة عن طريق رابطك أو كودك يحصل على خصم فوري 10%، وتحصل أنت على 25% عمولة نقدية تُحول مباشرة على وسيلة السحب المفضلة لديك (فودافون كاش / إنستاباي / STC Pay / تحويل بنكي)."
                : "Every user who subscribes using your referral link or promo code gets an instant 10% discount, and you earn a 25% cash commission transferred directly to your preferred payout method."}
            </p>
          </div>
        </div>

        {/* Auth / Loading Check */}
        {authLoading || loading ? (
          <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-12 flex items-center justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
          </div>
        ) : !user ? (
          /* Guest CTA Card */
          <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-8 text-center space-y-5 shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_#10b981]">
            <Gift className="w-12 h-12 text-emerald-500 mx-auto" />
            <h2 className="text-xl sm:text-2xl font-black text-zinc-950 dark:text-white">
              {isAr ? "سجّل الدخول لاستلام رابط الإحالة وكود الخصم الخاص بك فوراً" : "Sign in to get your personal referral link & promo code instantly"}
            </h2>
            <p className="text-xs sm:text-sm font-bold text-zinc-500 max-w-lg mx-auto">
              {isAr
                ? "بمجرد تسجيل الدخول سيظهر لك رابط الإحالة وكود الخصم الخاص بك فوراً لتبدأ مشاركته دون أي خطوات إضافية."
                : "Once signed in, your personal referral link and promo code appear immediately with zero extra steps."}
            </p>
            <div>
              <Link
                href="/login?redirect=%2Faffiliate"
                className="inline-flex items-center gap-2 border-4 border-black dark:border-white bg-emerald-500 hover:bg-emerald-600 text-black font-black px-8 py-4 text-sm uppercase tracking-wider shadow-[4px_4px_0px_rgba(0,0,0,1)] transition-all"
                prefetch={false}
              >
                <span>{isAr ? "تسجيل الدخول واستلام رابط الإحالة" : "Sign In & Get Referral Link"}</span>
                {isAr ? <ArrowLeft className="w-4 h-4" /> : <ArrowRight className="w-4 h-4" />}
              </Link>
            </div>
          </div>
        ) : affiliate ? (
          <>
            {/* Personal Link & Code Box */}
            <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 sm:p-8 space-y-6 shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_#10b981]">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b-2 border-zinc-200 dark:border-zinc-800 pb-4">
                <div>
                  <span className="text-[11px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400 block">
                    {isAr ? "رابط الإحالة وكود الخصم الخاص بك" : "YOUR PERSONAL REFERRAL LINK & CODE"}
                  </span>
                  <h2 className="text-xl font-black text-zinc-950 dark:text-white">
                    {isAr ? "انسخ الرابط وشاركه مع المتداولين أو أصدقائك" : "Copy & share with traders and friends"}
                  </h2>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="px-3 py-1 bg-emerald-100 dark:bg-emerald-950/60 border-2 border-emerald-500 text-emerald-700 dark:text-emerald-300 text-xs font-black">
                    {isAr ? `عمولتك: ${affiliate.commission_percent}%` : `Your Commission: ${affiliate.commission_percent}%`}
                  </span>
                  <span className="px-3 py-1 bg-amber-100 dark:bg-amber-950/60 border-2 border-amber-500 text-amber-800 dark:text-amber-300 text-xs font-black">
                    {isAr ? `خصم لصديقك: ${affiliate.discount_percent}%` : `Friend Discount: ${affiliate.discount_percent}%`}
                  </span>
                  <span className="px-3 py-1 bg-zinc-100 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 text-zinc-800 dark:text-zinc-200 text-xs font-black font-mono">
                    {hasSavedWalletPhone
                      ? `📱 ${affiliate.phone}`
                      : isAr
                      ? "💡 أضف رقم السحب بالأسفل"
                      : "💡 Add payout below"}
                  </span>
                  <button
                    type="button"
                    onClick={() => refreshAffiliate(true)}
                    disabled={isRefreshing}
                    title={isAr ? "تحديث البيانات" : "Refresh Data"}
                    className="p-1.5 border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900 hover:bg-zinc-200 dark:hover:bg-zinc-800 text-zinc-800 dark:text-zinc-200 cursor-pointer disabled:opacity-50 transition-colors"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-emerald-500" : ""}`} />
                  </button>
                </div>
              </div>

              <div className="grid lg:grid-cols-3 gap-4 items-stretch">
                {/* Link Copy Box */}
                <div className="lg:col-span-2 space-y-1.5">
                  <span className="text-xs font-black text-zinc-600 dark:text-zinc-400 block">
                    {isAr ? "رابط الإحالة المباشر (يُفعّل الخصم تلقائياً):" : "Direct Referral Link (auto-applies discount):"}
                  </span>
                  <div className="flex flex-col sm:flex-row gap-2">
                    <input
                      type="text"
                      readOnly
                      value={referralUrl}
                      className="flex-1 border-3 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900 px-3.5 py-3 font-mono text-xs sm:text-sm font-black text-zinc-900 dark:text-white outline-none"
                      dir="ltr"
                    />
                    <button
                      type="button"
                      onClick={handleCopyLink}
                      className="border-3 border-black dark:border-white bg-emerald-500 hover:bg-emerald-600 text-black font-black px-5 py-3 text-xs uppercase tracking-wider shadow-[3px_3px_0px_rgba(0,0,0,1)] flex items-center justify-center gap-2 cursor-pointer shrink-0"
                    >
                      {copiedLink ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                      <span>{copiedLink ? (isAr ? "تم النسخ ✓" : "Copied ✓") : (isAr ? "نسخ الرابط" : "Copy Link")}</span>
                    </button>
                  </div>
                </div>

                {/* Code Copy Box */}
                <div className="space-y-1.5">
                  <span className="text-xs font-black text-zinc-600 dark:text-zinc-400 block">
                    {isAr ? "كود الخصم الخاص بك:" : "Your Promo Code:"}
                  </span>
                  <div className="flex gap-2">
                    <div
                      className="flex-1 border-3 border-black dark:border-white bg-[#FFE600] text-black px-4 py-3 font-mono text-base font-black text-center tracking-wider"
                      dir="ltr"
                    >
                      {affiliate.code}
                    </div>
                    <button
                      type="button"
                      onClick={handleCopyCode}
                      className="border-3 border-black dark:border-white bg-zinc-900 text-white dark:bg-white dark:text-black font-black px-4 py-3 text-xs uppercase cursor-pointer"
                    >
                      {copiedCode ? "✓" : isAr ? "نسخ" : "Copy"}
                    </button>
                  </div>
                </div>
              </div>

              {/* Quick Share Buttons */}
              <div className="flex flex-wrap items-center gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleShareWhatsApp}
                  className="inline-flex items-center gap-2 border-2 border-black bg-[#25D366] text-black font-black px-4 py-2 text-xs shadow-[2px_2px_0px_#000] hover:-translate-y-0.5 transition-all cursor-pointer"
                >
                  <Share2 className="w-3.5 h-3.5" />
                  <span>{isAr ? "مشاركة عبر واتساب" : "Share on WhatsApp"}</span>
                </button>
                <button
                  type="button"
                  onClick={handleShareTelegram}
                  className="inline-flex items-center gap-2 border-2 border-black bg-[#229ED9] text-white font-black px-4 py-2 text-xs shadow-[2px_2px_0px_#000] hover:-translate-y-0.5 transition-all cursor-pointer"
                >
                  <Share2 className="w-3.5 h-3.5" />
                  <span>{isAr ? "مشاركة عبر تيليجرام" : "Share on Telegram"}</span>
                </button>
              </div>
            </div>

            {/* Live Stats Grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 shadow-[4px_4px_0px_rgba(0,0,0,1)] space-y-1">
                <div className="flex items-center justify-between text-zinc-400">
                  <span className="text-[11px] font-black uppercase">{isAr ? "الزيارات والنقرات" : "Link Clicks"}</span>
                  <MousePointerClick className="w-4 h-4 text-sky-500" />
                </div>
                <div className="text-3xl font-black text-zinc-950 dark:text-white">{affiliate.clicks_count || 0}</div>
                <p className="text-[10px] font-bold text-zinc-500">{isAr ? "زائر فتح رابطك" : "Visitors via your link"}</p>
              </div>

              <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 shadow-[4px_4px_0px_rgba(0,0,0,1)] space-y-1">
                <div className="flex items-center justify-between text-zinc-400">
                  <span className="text-[11px] font-black uppercase">{isAr ? "المشتركون الفعليون" : "Paid Referrals"}</span>
                  <Users className="w-4 h-4 text-emerald-500" />
                </div>
                <div className="text-3xl font-black text-emerald-600 dark:text-emerald-400">
                  {affiliate.total_sales_count || 0}
                </div>
                <p className="text-[10px] font-bold text-zinc-500">{isAr ? "عملية اشتراك مكتملة" : "Confirmed subscriptions"}</p>
              </div>

              <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 shadow-[4px_4px_0px_rgba(0,0,0,1)] space-y-1">
                <div className="flex items-center justify-between text-zinc-400">
                  <span className="text-[11px] font-black uppercase">{isAr ? "إجمالي أرباحك" : "Total Earned"}</span>
                  <TrendingUp className="w-4 h-4 text-amber-500" />
                </div>
                <div className="text-3xl font-black text-zinc-950 dark:text-white">
                  {Number(affiliate.total_commission_egp || 0).toLocaleString()}{" "}
                  <span className="text-xs font-bold text-zinc-500">ج.م</span>
                </div>
                <p className="text-[10px] font-bold text-zinc-500">
                  {isAr
                    ? `تم تحويل: ${Number(affiliate.paid_commission_egp || 0).toLocaleString()} ج.م`
                    : `Paid out: ${Number(affiliate.paid_commission_egp || 0).toLocaleString()} EGP`}
                </p>
              </div>

              <div className="border-4 border-black dark:border-white bg-emerald-50 dark:bg-emerald-950/30 p-5 shadow-[4px_4px_0px_#10b981] space-y-1">
                <div className="flex items-center justify-between text-emerald-700 dark:text-emerald-300">
                  <span className="text-[11px] font-black uppercase">{isAr ? "الرصيد المستحق للسحب" : "Available Balance"}</span>
                  <Wallet className="w-4 h-4 text-emerald-500" />
                </div>
                <div className="text-3xl font-black text-emerald-600 dark:text-emerald-400">
                  {unpaidBalance.toLocaleString()} <span className="text-xs font-bold">ج.م</span>
                </div>
                <p className="text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
                  {isAr ? "يُحول على رقم محفظتك الإلكترونية" : "Paid to your mobile wallet"}
                </p>
              </div>
            </div>

            {/* Settings: Customize Code & Update Payout Wallet/Account */}
            <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 sm:p-7 space-y-5 shadow-[6px_6px_0px_rgba(0,0,0,1)]">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <h3 className="text-lg font-black text-zinc-950 dark:text-white">
                    {isAr ? "تحديث وسيلة استلام الأرباح وكود الخصم" : "Update Payout Method & Promo Code"}
                  </h3>
                  <p className="text-xs font-bold text-zinc-500 mt-0.5">
                    {isAr
                      ? "يمكنك تخصيص كود الخصم فوراً، وإضافة رقم المحفظة الإلكترونية (فودافون كاش / إنستاباي / STC Pay) في أي وقت لتحويل أرباحك."
                      : "Customize your promo code anytime, and add your payout wallet/phone (Vodafone Cash / InstaPay / STC Pay) whenever you're ready for payouts."}
                  </p>
                </div>
              </div>

              {!hasSavedWalletPhone && (
                <div className="border-2 border-amber-500 bg-amber-50 dark:bg-amber-950/30 p-3.5 text-xs font-bold text-amber-900 dark:text-amber-200 flex items-center gap-2">
                  <Smartphone className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
                  <span>
                    {isAr
                      ? "رابط الإحالة وكود الخصم يعملان معك الآن! أضف رقم محفظتك الإلكترونية (مصري أو سعودي/دولي) هنا عندما تكون جاهزاً لاستلام العمولات."
                      : "Your link & promo code are already live! Add your payout number whenever you are ready to receive commissions."}
                  </span>
                </div>
              )}

              <div className="grid sm:grid-cols-3 gap-4">
                <label className="block">
                  <span className="block text-[11px] font-black uppercase text-zinc-500 mb-1">
                    {isAr ? "وسيلة استلام الأرباح" : "Payout Method"}
                  </span>
                  <select
                    value={paymentMethodInput}
                    onChange={(e) => setPaymentMethodInput(e.target.value)}
                    className="w-full border-2 border-black dark:border-white bg-white dark:bg-zinc-900 px-3.5 py-2.5 text-sm font-black text-zinc-950 dark:text-white outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value="vodafone_cash">{isAr ? "محفظة إلكترونية (فودافون/اتصالات/أورنج/WE)" : "Mobile Wallet (Vodafone / Orange / WE)"}</option>
                    <option value="instapay">{isAr ? "إنستاباي (InstaPay)" : "InstaPay (Egypt)"}</option>
                    <option value="stc_pay">{isAr ? "STC Pay / محفظة سعودية" : "STC Pay (Saudi Arabia)"}</option>
                    <option value="bank_transfer">{isAr ? "تحويل بنكي" : "Bank Transfer"}</option>
                  </select>
                </label>

                <label className="block">
                  <span className="block text-[11px] font-black uppercase text-zinc-500 mb-1">
                    {isAr ? "رقم الموبايل / المحفظة (مصري أو دولي)" : "Payout Mobile Number"}
                  </span>
                  <input
                    type="tel"
                    value={phoneInput}
                    onChange={(e) => setPhoneInput(e.target.value)}
                    placeholder={isSaudi ? "+9665XXXXXXXX" : isUae ? "+9715XXXXXXXX" : isQatar ? "+974XXXXXXXX" : "01012345678 / +9665XXXXXXXX"}
                    className="w-full border-2 border-black dark:border-white bg-white dark:bg-zinc-900 px-3.5 py-2.5 font-mono text-sm font-black text-zinc-950 dark:text-white outline-none focus:ring-2 focus:ring-emerald-500"
                    dir="ltr"
                  />
                </label>

                <label className="block">
                  <span className="block text-[11px] font-black uppercase text-zinc-500 mb-1">
                    {isAr ? "تخصيص كود الخصم" : "Custom Promo Code"}
                  </span>
                  <input
                    type="text"
                    value={codeInput}
                    onChange={(e) => setCodeInput(e.target.value.toUpperCase())}
                    placeholder="AMR15"
                    className="w-full border-2 border-black dark:border-white bg-white dark:bg-zinc-900 px-3.5 py-2.5 font-mono text-sm font-black uppercase text-zinc-950 dark:text-white outline-none focus:ring-2 focus:ring-emerald-500"
                    dir="ltr"
                  />
                </label>
              </div>

              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleSaveSettings}
                  disabled={saving || !canSaveSettings}
                  className="border-3 border-black dark:border-white bg-black text-white dark:bg-emerald-500 dark:text-black font-black px-6 py-2.5 text-xs uppercase tracking-wider shadow-[3px_3px_0px_#10b981] hover:-translate-y-0.5 transition-all cursor-pointer disabled:opacity-50"
                >
                  {saving
                    ? isAr ? "جاري الحفظ..." : "Saving..."
                    : isAr ? "حفظ التغييرات" : "Save Changes"}
                </button>
              </div>
            </div>

            {/* Recent Referrals Table */}
            {referrals.length > 0 && (
              <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 space-y-4 shadow-[6px_6px_0px_rgba(0,0,0,1)]">
                <h3 className="text-base font-black text-zinc-950 dark:text-white">
                  {isAr ? "سجل الاشتراكات المسجلة عن طريقك" : "Your Confirmed Referrals"}
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-start text-xs font-bold">
                    <thead>
                      <tr className="border-b-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900">
                        <th className="p-2.5 text-start">{isAr ? "التاريخ" : "Date"}</th>
                        <th className="p-2.5 text-start">{isAr ? "الباقة" : "Plan"}</th>
                        <th className="p-2.5 text-start">{isAr ? "قيمة الاشتراك" : "Order Amount"}</th>
                        <th className="p-2.5 text-start">{isAr ? "عمولتك" : "Your Commission"}</th>
                        <th className="p-2.5 text-end">{isAr ? "الحالة" : "Status"}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                      {referrals.map((r) => (
                        <tr key={r.id}>
                          <td className="p-2.5 font-mono text-zinc-500">
                            {new Date(r.created_at).toLocaleDateString(isAr ? "ar-EG" : "en-US")}
                          </td>
                          <td className="p-2.5 font-black">{formatReferralPlanLabel(r.plan_id, isAr)}</td>
                          <td className="p-2.5">{Number(r.amount_egp || 0).toLocaleString()} ج.م</td>
                          <td className="p-2.5 font-black text-emerald-600 dark:text-emerald-400">
                            +{Number(r.commission_amount_egp || 0).toLocaleString()} ج.م
                          </td>
                          <td className="p-2.5 text-end">
                            <span
                              className={`px-2 py-0.5 text-[10px] font-black border border-black ${
                                r.commission_status === "paid"
                                  ? "bg-emerald-400 text-black"
                                  : "bg-amber-300 text-black"
                              }`}
                            >
                              {r.commission_status === "paid"
                                ? isAr ? "تم التحويل ✓" : "Paid ✓"
                                : isAr ? "جاهز للتحويل" : "Earned"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        ) : null}

        {/* How It Works / Commission Examples */}
        <div className="border-4 border-black dark:border-white bg-zinc-950 text-white p-6 sm:p-8 space-y-5 shadow-[6px_6px_0px_#10b981]">
          <div className="flex items-center gap-2 text-emerald-400 text-xs font-black uppercase tracking-widest">
            <ShieldCheck className="w-4 h-4" />
            <span>{isAr ? "كيف يعمل النظام وكم تربح؟" : "HOW IT WORKS & COMMISSION EXAMPLES"}</span>
          </div>
          <div className="grid sm:grid-cols-3 gap-4 text-xs font-bold">
            <div className="border border-zinc-800 bg-zinc-900/70 p-4 space-y-1.5">
              <div className="text-amber-400 font-black text-sm">{isAr ? "1. انسخ رابطك وشاركه فوراً" : "1. Copy & Share Instantly"}</div>
              <p className="text-zinc-400 leading-relaxed">
                {isAr
                  ? "رابط الإحالة وكود الخصم جاهزان تلقائياً فور تسجيل دخولك. انسخه وشاركه مع المتداولين أو أصدقائك على واتساب وتليجرام."
                  : "Your referral link and promo code are ready immediately upon sign-in. Share them with traders anywhere."}
              </p>
            </div>
            <div className="border border-zinc-800 bg-zinc-900/70 p-4 space-y-1.5">
              <div className="text-emerald-400 font-black text-sm">{isAr ? "2. خصم فوري للمشترك" : "2. Instant Buyer Discount"}</div>
              <p className="text-zinc-400 leading-relaxed">
                {isAr
                  ? "يحصل المشترك على خصم 10% تلقائياً فور فتح رابطك أو إدخال كودك، ويظهر السعر الجديد مباشرة على باقات الاشتراك."
                  : "Your referral receives an automatic 10% discount shown directly on the pricing cards."}
              </p>
            </div>
            <div className="border border-zinc-800 bg-zinc-900/70 p-4 space-y-1.5">
              <div className="text-sky-400 font-black text-sm">{isAr ? "3. استلم 25% كاش أو إنستاباي / STC" : "3. Receive 25% Cash Payout"}</div>
              <p className="text-zinc-400 leading-relaxed">
                {isAr
                  ? isGulfMarket
                    ? "تُضاف عمولتك 25% على كل اشتراك مكتمل (أفراد أو باقات قنوات B2B) وتُحول لك عبر STC Pay أو تحويل بنكي أو فودافون كاش."
                    : "تُضاف عمولتك 25% على كل اشتراك مكتمل (169 ج.م على باقة 6 شهور، 304 ج.م على السنوية، 506 ج.م على مدى الحياة، وحتى 563 ج.م على باقات B2B) وتُحول لك على محفظتك أو إنستاباي."
                  : "Earn 25% commission per confirmed subscription (individual plans or B2B channel licenses), transferred via Vodafone Cash, InstaPay, STC Pay, or bank transfer."}
              </p>
            </div>
          </div>
        </div>
        {/* ── B2B Advertisers & Website Owners Section ── */}
        <div id="advertisers" className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 sm:p-8 space-y-6 shadow-[6px_6px_0px_#f59e0b]">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b-2 border-black/10 dark:border-white/10 pb-4">
            <div>
              <span className="inline-block px-2.5 py-0.5 bg-amber-400 text-black text-[10px] font-black uppercase tracking-wider mb-1">
                B2B & Partnerships
              </span>
              <h2 className="text-lg sm:text-xl font-black text-zinc-900 dark:text-white">
                {isAr ? "📢 لأصحاب المواقع، التطبيقات، والشركات الإعلانية" : "📢 For Publishers, Website Owners & Advertisers"}
              </h2>
              <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">
                {isAr
                  ? "هل تمتلك منصة أو موقعاً أو ترغب في الإعلان والرعاية والشراكة معنا؟ نرحب بالتعاون مع أصحاب الأعمال."
                  : "Looking to advertise, exchange traffic, sponsor market analysis, or build commercial affiliate partnerships with our platforms?"}
              </p>
            </div>
            <a
              href="https://wa.me/201024359109?text=مرحباً، أنا صاحب موقع / معلن وأود الاستفسار عن الشراكات الإعلانية والتبادل التسويقي مع منصاتكم"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-black text-xs rounded shadow transition-all hover:scale-105 shrink-0"
            >
              <span>{isAr ? "تواصل للأعمال والشراكات (واتساب) 💬" : "Direct Business Contact (WhatsApp) 💬"}</span>
            </a>
          </div>

          <div className="grid sm:grid-cols-3 gap-4 text-xs">
            <div className="p-4 border-2 border-black/10 dark:border-white/10 bg-zinc-50 dark:bg-zinc-950 space-y-2">
              <span className="text-xl">🎯</span>
              <h3 className="font-black text-zinc-900 dark:text-white">
                {isAr ? "1. الرعاية والإعلانات المستهدفة" : "1. Sponsorships & Targeted Ads"}
              </h3>
              <p className="text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {isAr
                  ? `ضع علامتك التجارية أو خدماتك أمام آلاف المتداولين والمستثمرين النشطين يومياً في ${marketAr} والأسواق المالية العربية.`
                  : `Promote your brand directly to thousands of high-intent active investors and traders across ${marketEn} and Arab markets.`}
              </p>
            </div>

            <div className="p-4 border-2 border-black/10 dark:border-white/10 bg-zinc-50 dark:bg-zinc-950 space-y-2">
              <span className="text-xl">🔄</span>
              <h3 className="font-black text-zinc-900 dark:text-white">
                {isAr ? "2. تبادل الترافيك والروابط المرجعية" : "2. Traffic & Media Exchange"}
              </h3>
              <p className="text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {isAr
                  ? "إذا كنت صاحب موقع أو مدونة في مجالات الاقتصاد والاستثمار أو العقارات، نوفر شراكات تبادل ترافيك ومقالات مشتركة تسهم في تعزيز ظهور الطرفين في محركات البحث."
                  : "Cross-platform traffic sharing, guest articles, and co-marketing initiatives designed to elevate mutual search ranking and referral volume."}
              </p>
            </div>

            <div className="p-4 border-2 border-black/10 dark:border-white/10 bg-zinc-50 dark:bg-zinc-950 space-y-2">
              <span className="text-xl">💼</span>
              <h3 className="font-black text-zinc-900 dark:text-white">
                {isAr ? "3. تكامل المنصات وتراخيص الـ API" : "3. API Licensing & Telegram Bots"}
              </h3>
              <p className="text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {isAr
                  ? "تكامل إشارات الرادار والتحليل الفني الذكي مع قنواتك الخاصة على تليجرام أو منصاتك التقنية بعقود شراكة B2B مخصصة."
                  : "License our AI quant scanning feeds, custom indicators, and automated Telegram bots directly into your VIP channels or fintech portals."}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 pt-3 border-t border-black/10 dark:border-white/10 text-xs">
            <span className="text-zinc-500 dark:text-zinc-400 font-bold">
              {isAr ? "قنوات تواصل مسؤولي الشراكات التجارية:" : "Business Development & Media Buying Desk:"}
            </span>
            <div className="flex items-center gap-3">
              <a
                href="https://wa.me/201024359109?text=مرحباً، أنا صاحب موقع / معلن وأود الاستفسار عن الشراكات الإعلانية والتبادل التسويقي مع منصاتكم"
                target="_blank"
                rel="noopener noreferrer"
                className="text-emerald-600 dark:text-emerald-400 font-black hover:underline"
              >
                واتساب: 01024359109 (+20)
              </a>
              <span className="text-zinc-400">•</span>
              <a
                href="https://t.me/egxbots"
                target="_blank"
                rel="noopener noreferrer"
                className="text-sky-600 dark:text-sky-400 font-black hover:underline"
              >
                {isAr ? "قناة تليجرام: egxbots@" : "Telegram Channel: @egxbots"}
              </a>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
