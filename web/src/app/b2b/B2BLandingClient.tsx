"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLanguage } from "@/contexts/LanguageContext";
import { useMarket } from "@/contexts/MarketContext";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { B2B_CONTACT, B2B_TIERS, B2BTierId, toB2BDisplayAmount } from "@/lib/b2b-plans";
import {
  ArrowRight,
  Bot,
  Building2,
  Check,
  CheckCircle2,
  Copy,
  Cpu,
  Crown,
  ExternalLink,
  Flame,
  GraduationCap,
  Loader2,
  MessageSquare,
  Newspaper,
  Rocket,
  Scale,
  Send,
  Sparkles,
  X,
  Zap,
} from "lucide-react";

interface ExistingLicenseSummary {
  id: string;
  tier: B2BTierId;
  status: string;
  group_title: string | null;
}

export default function B2BLandingClient() {
  const { language } = useLanguage();
  const isAr = language === "ar";
  const { isSaudi, currencyLabel, currencyCode } = useMarket();
  const brandName = isSaudi ? "TASI BOTS" : "EGX BOTS";
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [demoMarket, setDemoMarket] = useState<"egx" | "tasi">(isSaudi ? "tasi" : "egx");
  const [customSigPreview, setCustomSigPreview] = useState(
    isAr ? "⚡ تحليلات قناة النخبة بالتعاون مع EGX BOTS" : "⚡ Elite Community Insights powered by EGX BOTS"
  );
  const [startingTier, setStartingTier] = useState<string | null>(null);
  const [existingLicense, setExistingLicense] = useState<ExistingLicenseSummary | null>(null);
  const [openFaqIdx, setOpenFaqIdx] = useState<number | null>(0);
  const [trialModal, setTrialModal] = useState<{
    open: boolean;
    code: string;
    connectUrl: string;
    tier: string;
  } | null>(null);

  const autoStartedRef = useRef(false);

  useEffect(() => {
    setDemoMarket(isSaudi ? "tasi" : "egx");
  }, [isSaudi]);

  useEffect(() => {
    let active = true;
    async function checkExistingLicense() {
      if (!user) {
        if (active) setExistingLicense(null);
        return;
      }
      try {
        const res = await fetch("/api/b2b/license", { cache: "no-store" });
        if (!res.ok) return;
        const data = await res.json();
        if (active && data.ok && data.license) {
          setExistingLicense({
            id: data.license.id,
            tier: data.license.tier,
            status: data.license.status,
            group_title: data.license.group_title,
          });
        }
      } catch {
        // Ignore silent status probe error
      }
    }
    if (!authLoading) {
      checkExistingLicense();
    }
    return () => {
      active = false;
    };
  }, [user, authLoading]);

  const handleStartTrial = async (tier: B2BTierId = "b2b_pro") => {
    if (!user) {
      toast.info(
        isAr
          ? "سجّل دخولك أو أنشئ حساباً في ثوانٍ لتفعيل تجربة الـ 3 أيام المجانية فوراً"
          : "Sign in to immediately activate your 3-day free B2B trial"
      );
      router.push(`/login?redirect=${encodeURIComponent(`/b2b?start_trial=1&tier=${tier}`)}`);
      return;
    }

    try {
      setStartingTier(tier);
      const res = await fetch("/api/b2b/trial", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier }),
      });
      const data = await res.json();
      if (res.ok && data.ok) {
        toast.success(
          isAr
            ? "🎉 تم تفعيل رخصتك التجريبية لمدة 3 أيام بنجاح!"
            : "🎉 Your 3-day B2B free trial is active!"
        );
        setTrialModal({
          open: true,
          code: data.activation_code || String(data.license?.id || "").slice(0, 8),
          connectUrl:
            data.connect_url ||
            `https://t.me/${B2B_CONTACT.telegramBotHandle}?startgroup=activate_${String(data.license?.id || "").slice(0, 8)}&admin=delete_messages+pin_messages`,
          tier,
        });
        if (data.license) {
          setExistingLicense({
            id: data.license.id,
            tier: data.license.tier,
            status: data.license.status,
            group_title: data.license.group_title,
          });
        }
      } else if (data.error === "trial_already_claimed") {
        toast.info(data.message || (isAr ? "تم استخدام التجربة سابقاً" : "Trial already claimed"));
        router.push("/b2b/dashboard");
      } else {
        toast.error(data.message || data.error || (isAr ? "تعذر تفعيل التجربة" : "Could not start trial"));
      }
    } catch (err: any) {
      toast.error(err?.message || (isAr ? "خطأ في الاتصال بالخادم" : "Network error"));
    } finally {
      setStartingTier(null);
    }
  };

  useEffect(() => {
    if (authLoading || !user || autoStartedRef.current) return;
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("start_trial") === "1") {
      autoStartedRef.current = true;
      const tierParam = params.get("tier") as B2BTierId | null;
      const targetTier: B2BTierId =
        tierParam && ["b2b_starter", "b2b_pro", "b2b_enterprise"].includes(tierParam)
          ? tierParam
          : "b2b_pro";
      handleStartTrial(targetTier);
    }
  }, [authLoading, user]);

  const formatPrice = (egp: number) =>
    `${toB2BDisplayAmount(egp, isSaudi).toLocaleString()} ${currencyLabel}`;

  const whatsappSalesHref = `https://wa.me/${B2B_CONTACT.whatsappNumber}?text=${encodeURIComponent(
    isAr
      ? `مرحباً فريق ${brandName}، أود الاستفسار عن حلول الشركات وبوت التليجرام (B2B)`
      : `Hello ${brandName} team, I would like to inquire about B2B solutions & Telegram group licensing.`
  )}`;

  const segments = [
    {
      icon: Bot,
      tag: isAr ? "جاهز للتفعيل الفوري" : "READY SELF-SERVE",
      title: isAr ? "أصحاب القنوات ومجتمعات المستثمرين (Telegram VIP)" : "Telegram Channels & Investor Communities",
      desc: isAr
        ? "أعضاء جروبك يسألون عن عشرات الأسهم يومياً وأنت لا تملك وقتاً للرد على كل عضو؟ البوت يرد في ثوانٍ بتوقيع قناتك الرسمي ويمنع السبام بمهلة 90 ثانية."
        : "Turn repetitive member stock questions into instant 24/7 value with your group brand signature and built-in anti-spam controls.",
      priceHint: isAr ? "من 1,000 إلى 2,500 ج.م / شهر" : "1,000 – 2,500 EGP / mo",
      accent: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/40",
    },
    {
      icon: GraduationCap,
      tag: isAr ? "شراكة وخصومات جماعية" : "ACADEMIES & EDUCATORS",
      title: isAr ? "أكاديميات التداول والمدربين" : "Trading Academies & Mentors",
      desc: isAr
        ? "امنح متدربيك اشتراكات Pro جماعية بأسعار الجملة لتطبيق المؤشرات والقيمة العادلة عملياً، أو اربح 25% عمولة متكررة عبر رابط الشركاء."
        : "Equip your students with bulk Pro seats to practice real market screening, plus earn 25% recurring revenue via our partner program.",
      priceHint: isAr ? "باقات جماعية أو عمولة 25%" : "Bulk Seats or 25% Affiliate",
      accent: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/40",
    },
    {
      icon: Newspaper,
      tag: isAr ? "محتوى آلي ورعاية" : "MEDIA & PORTALS",
      title: isAr ? "المواقع والصفحات المالية والإعلامية" : "Financial Media & Economic Pages",
      desc: isAr
        ? "احصل على ملخصات يومية آلية لأهم إفصاحات البورصة وتقارير التجميع والسيولة لنشرها سريعاً لجمهورك أو حجز مساحات رعاية ذكية."
        : "Streamline daily market wrap-ups, automated disclosures summaries, and sponsored placements across our market reports.",
      priceHint: isAr ? "باقات محتوى وشراكات إعلامية" : "Media Feed & Sponsorships",
      accent: "bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/40",
    },
    {
      icon: Building2,
      tag: isAr ? "حلول مؤسسية مخصصة" : "CUSTOM ENTERPRISE",
      title: isAr ? "شركات السمسرة وتطبيقات الفنتك" : "Brokerages & FinTech Apps",
      desc: isAr
        ? "زد معدلات تداول عملائك عبر دمج محرك ARTORO كمساعد تحليلي ذكي داخل موقعك أو تطبيقك أو قناة عملائك (White-label أو ربط مخصص)."
        : "Boost client trading engagement by embedding ARTORO analytical engine inside your brokerage portal or wealth app.",
      priceHint: isAr ? "عقود وتعاقدات مخصصة للشركات" : "Custom Enterprise Contracts",
      accent: "bg-purple-500/15 text-purple-700 dark:text-purple-400 border-purple-500/40",
    },
  ];

  const faqs = [
    {
      q: isAr
        ? "كيف يتم ربط البوت بمجموعتي على تليجرام خلال التجربة المجانية؟"
        : "How do I connect the bot to my Telegram group during the free trial?",
      a: isAr
        ? "بعد الضغط على «جرّب البوت 3 أيام مجاناً» يظهر لك زر مباشر يفتح تليجرام لاختيار مجموعتك. فور إضافة البوت (@egxbots_bot) ورفعه كمشرف، يتعرف البوت على المجموعة آلياً برمز التفعيل ويرسل رسالة ترحيب ويبدأ الرد فوراً."
        : "Click Start 3-Day Free Trial to receive an automated Telegram deep-link. Once you add @egxbots_bot to your group as an admin, it binds automatically and begins replying right away.",
    },
    {
      q: isAr
        ? "هل يسرق البوت أعضاء مجموعتي أو يضع روابط لقنوات أخرى؟"
        : "Does the bot promote external channels inside my group?",
      a: isAr
        ? "أبداً. كل رد يخرج داخل مجموعتك يحمل التوقيع المخصص الذي تكتبه بنفسك في لوحة تحكم B2B (مثل اسم قناتك أو رابط التواصل معك)، بدون الترويج لأي مجموعات منافسة."
        : "Never. Every response inside your community carries your own custom footer signature configured inside your B2B dashboard.",
    },
    {
      q: isAr
        ? "كيف تمنعون الأعضاء من استهلاك الكوتة اليومية في ثوانٍ (السبام)؟"
        : "How do you prevent members from spamming and exhausting the daily quota?",
      a: isAr
        ? "البوت لا يرد على الدردشة العادية بين الأعضاء إطلاقاً، بل يرد فقط عند مناداته الصريحة (@egxbots_bot أو /ask)، مع مانع تكرار (Cooldown) مدته 90 ثانية بين كل سؤال والآخر لنفس العضو."
        : "The bot ignores casual banter and only responds to explicit triggers (@egxbots_bot or /ask), enforced by an automatic 90-second per-member cooldown.",
    },
    {
      q: isAr
        ? "ما الوضع القانوني والرقابي لاستخدام أدواتكم في شركات السمسرة والأكاديميات؟"
        : "What is the regulatory positioning for licensed brokerages and academies?",
      a: isAr
        ? "تُقدم المنصة خدمات تحليلية وتقنية بحتة (مؤشرات فنية، نسب مالية، حسابات القيمة العادلة، توافق شرعي، وتلخيص آلي لإفصاحات البورصة)، ولا تصدر تعليمات شراء أو بيع مباشرة نيابة عن الغير، مما يجعلها متوافقة كأداة دعم قرار وبنية تقنية للشركات والأكاديميات."
        : "Our B2B offering provides technical analytics, financial ratios, fair value models, Sharia screening, and automated disclosure summaries strictly as analytical software tools.",
    },
  ];

  return (
    <div
      className="min-h-screen bg-zinc-50 dark:bg-black text-zinc-950 dark:text-zinc-100 pb-20 transition-colors duration-200"
      dir={isAr ? "rtl" : "ltr"}
    >
      {/* Existing Active License Banner */}
      {existingLicense && (
        <div className="bg-emerald-600 text-white border-b-2 border-black dark:border-zinc-800 px-4 py-2.5">
          <div className="max-w-6xl mx-auto flex flex-wrap items-center justify-between gap-2 text-xs font-black">
            <span className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              {isAr
                ? `لديك رخصة B2B مسجلة على حسابك (${existingLicense.group_title || existingLicense.tier})`
                : `You already have a B2B license on your account (${existingLicense.tier})`}
            </span>
            <Link
              href="/b2b/dashboard"
              className="inline-flex items-center gap-1.5 bg-black text-white px-3 py-1 rounded-lg hover:bg-zinc-900 transition-colors"
            >
              <span>{isAr ? "فتح لوحة تحكم البوت ←" : "Open B2B Dashboard →"}</span>
            </Link>
          </div>
        </div>
      )}

      {/* 1. HERO SECTION */}
      <section className="relative overflow-hidden border-b-4 border-black dark:border-zinc-800 bg-gradient-to-b from-zinc-950 via-zinc-900 to-zinc-950 text-white pt-14 pb-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-6xl mx-auto grid lg:grid-cols-12 gap-10 items-center">
          <div className="lg:col-span-7 space-y-6 text-start">
            <div className="inline-flex flex-wrap items-center gap-2 border border-emerald-500/40 bg-emerald-500/15 px-3 py-1 rounded-full text-[11px] font-black text-emerald-300">
              <Crown className="w-3.5 h-3.5 text-amber-400" />
              <span>
                {isAr
                  ? `حلول الشركات وقنوات التداول (B2B) · البورصة المصرية وتاسي السعودي`
                  : `Enterprise & Community AI Solutions · EGX & Saudi TASI`}
              </span>
            </div>

            <h1 className="text-3xl sm:text-5xl font-black leading-[1.18] tracking-tight text-white">
              {isAr ? (
                <>
                  خلّي بوت <span className="text-emerald-400">ARTORO</span> يرد على أعضاء قناتك وعملاء شركتك{" "}
                  <span className="underline decoration-amber-400 decoration-4 underline-offset-4">بتوقيعك الخاص 24/7</span>
                </>
              ) : (
                <>
                  Deploy <span className="text-emerald-400">ARTORO AI</span> Inside Your Trading Community{" "}
                  <span className="underline decoration-amber-400 decoration-4 underline-offset-4">With Your Brand</span>
                </>
              )}
            </h1>

            <p className="text-sm sm:text-base text-zinc-300 font-semibold leading-relaxed max-w-2xl">
              {isAr
                ? "بدل ما تقضي ساعات بترد يدوياً على أسئلة «سهم فوري رايح فين؟» و«دعم أرامكو كام؟»، فعّل رخصة البوت في جروب التليجرام خلال 60 ثانية بتوقيع باسم قناتك، أو اطلب حلولاً مخصصة لشركات السمسرة والأكاديميات والمواقع المالية."
                : "Eliminate manual repetitive stock replies inside your VIP Telegram groups. Get instant technicals, support/resistance, fair value & Sharia checks branded with your own community signature in 60 seconds."}
            </p>

            {/* Primary CTA Buttons */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <button
                type="button"
                disabled={startingTier === "b2b_pro"}
                onClick={() => handleStartTrial("b2b_pro")}
                className="inline-flex items-center justify-center gap-2.5 border-3 border-black bg-amber-400 hover:bg-amber-300 text-black font-black px-6 py-4 text-xs sm:text-sm uppercase shadow-[5px_5px_0px_#10b981] hover:-translate-y-0.5 active:translate-y-0 transition-all cursor-pointer disabled:opacity-60"
              >
                {startingTier === "b2b_pro" ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4" />
                )}
                <span>
                  {isAr ? "🎁 جرّب البوت في جروبك 3 أيام مجاناً" : "🎁 Start 3-Day Free Group Trial"}
                </span>
              </button>

              <a
                href={whatsappSalesHref}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-2 border-2 border-zinc-600 hover:border-emerald-400 bg-zinc-900 hover:bg-zinc-800 text-white font-black px-5 py-4 text-xs sm:text-sm transition-colors"
              >
                <MessageSquare className="w-4 h-4 text-emerald-400" />
                <span>{isAr ? "تواصل مع مبيعات الشركات (واتساب)" : "WhatsApp B2B Sales"}</span>
              </a>

              <Link
                href="/b2b/dashboard"
                className="inline-flex items-center gap-1.5 text-xs font-bold text-zinc-400 hover:text-emerald-400 px-2 py-2 transition-colors"
              >
                <span>{isAr ? "لديك رخصة بالفعل؟ افتح لوحة التحكم" : "Already licensed? Dashboard"}</span>
                <ArrowRight className={`w-3.5 h-3.5 ${isAr ? "rotate-180" : ""}`} />
              </Link>
            </div>

            {/* Trust Micro-Metrics */}
            <div className="grid grid-cols-3 gap-3 pt-4 border-t border-zinc-800 max-w-xl text-xs">
              <div>
                <span className="text-emerald-400 font-black text-lg block">60 ثانية</span>
                <span className="text-zinc-400 font-semibold">
                  {isAr ? "ربط آلي بضغطة زر" : "1-Click Group Setup"}
                </span>
              </div>
              <div>
                <span className="text-amber-300 font-black text-lg block">EGX + TASI</span>
                <span className="text-zinc-400 font-semibold">
                  {isAr ? "تغطية مصر والسعودية" : "Egypt & Saudi Stocks"}
                </span>
              </div>
              <div>
                <span className="text-sky-400 font-black text-lg block">90s Guard</span>
                <span className="text-zinc-400 font-semibold">
                  {isAr ? "مانع سبام وتوقيع خاص" : "Anti-Spam + Branding"}
                </span>
              </div>
            </div>
          </div>

          {/* Right Side: Interactive Telegram Group Live Simulation */}
          <div className="lg:col-span-5">
            <div className="border-4 border-black bg-zinc-900 shadow-[8px_8px_0px_#10b981] rounded-2xl overflow-hidden">
              {/* Mock Telegram Header */}
              <div className="bg-zinc-950 border-b border-zinc-800 px-4 py-3 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-full bg-emerald-500 text-black flex items-center justify-center font-black text-sm border border-black">
                    VIP
                  </div>
                  <div>
                    <div className="text-xs font-black text-white flex items-center gap-1.5">
                      <span>{isAr ? "جروب متداولي النخبة VIP" : "VIP Traders Community"}</span>
                      <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
                    </div>
                    <span className="text-[10px] text-zinc-400 font-semibold">
                      {isAr ? "معاينة حية لردود البوت داخل الجروب" : "Live group response preview"}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-700 rounded-lg p-0.5 text-[10px] font-black">
                  <button
                    type="button"
                    onClick={() => setDemoMarket("egx")}
                    className={`px-2 py-1 rounded-md cursor-pointer transition-colors ${
                      demoMarket === "egx" ? "bg-emerald-500 text-black" : "text-zinc-400 hover:text-white"
                    }`}
                  >
                    🇪🇬 EGX
                  </button>
                  <button
                    type="button"
                    onClick={() => setDemoMarket("tasi")}
                    className={`px-2 py-1 rounded-md cursor-pointer transition-colors ${
                      demoMarket === "tasi" ? "bg-emerald-500 text-black" : "text-zinc-400 hover:text-white"
                    }`}
                  >
                    🇸🇦 TASI
                  </button>
                </div>
              </div>

              {/* Chat Body */}
              <div className="p-4 space-y-3 bg-[#0b141a] text-xs">
                {/* User Message */}
                <div className="flex justify-start">
                  <div className="bg-zinc-800 border border-zinc-700 rounded-xl px-3.5 py-2.5 max-w-[85%] space-y-1">
                    <span className="text-[10px] font-black text-amber-400 block">
                      {isAr ? "عضو في الجروب · الآن" : "Group Member · Now"}
                    </span>
                    <p className="text-zinc-100 font-bold" dir="rtl">
                      {demoMarket === "egx"
                        ? "@egxbots_bot تحليل سريع لسهم فوري FWRY ودعومه إيه؟"
                        : "@egxbots_bot تحليل سهم أرامكو 2222 والمستويات الحالية؟"}
                    </p>
                  </div>
                </div>

                {/* Bot Reply */}
                <div className="flex justify-end">
                  <div className="bg-emerald-950/70 border border-emerald-500/40 rounded-xl px-3.5 py-3 max-w-[95%] space-y-2 shadow-lg">
                    <div className="flex items-center justify-between gap-2 border-b border-emerald-500/20 pb-1.5">
                      <span className="text-[10px] font-black text-emerald-300 flex items-center gap-1">
                        <Bot className="w-3.5 h-3.5" />
                        ARTORO AI · EGX BOTS
                      </span>
                      <span className="text-[9px] text-zinc-400 font-mono">1.4s</span>
                    </div>

                    <div className="space-y-1 text-[11px] text-zinc-200 leading-relaxed font-medium">
                      <p className="font-black text-white">
                        {demoMarket === "egx"
                          ? "📊 ملخص فوري (FWRY — نموذج معاينة)"
                          : "📊 ملخص أرامكو السعودية (2222 — نموذج معاينة)"}
                      </p>
                      <p>
                        {demoMarket === "egx"
                          ? "• السعر التوضيحي: منطقة التداول الحالية · مؤشر RSI و MACD والدعوم والمقاومات المستخرجة مباشرة من قاعدة البيانات اليومية"
                          : "• السعر التوضيحي بالريال السعودي (ر.س) · قراءة المؤشرات الفنية والدعوم والمقاومات والتوافق الشرعي من قاعدة بيانات تاسي"}
                      </p>
                      <p className="text-emerald-300 font-bold">
                        {isAr
                          ? "• يتم إرفاق التقييم الفني، نقاط الدعم والمقاومة، ومؤشرات السيولة تلقائياً."
                          : "• Automatically includes technical verdict, support/resistance & liquidity signals."}
                      </p>
                    </div>

                    {/* Editable Branded Footer */}
                    <div className="mt-2 pt-2 border-t border-emerald-500/30 text-[10px] font-black text-amber-300">
                      {customSigPreview || "⚡ EGX BOTS VIP"}
                    </div>
                  </div>
                </div>

                {/* Interactive Signature Preview Input */}
                <div className="pt-2 border-t border-zinc-800 space-y-1.5">
                  <label className="text-[10px] font-bold text-zinc-400 block">
                    {isAr ? "✍️ جرّب كتابة توقيع قناتك وشاهده في الرسالة أعلاه:" : "✍️ Test your custom group signature:"}
                  </label>
                  <input
                    type="text"
                    value={customSigPreview}
                    onChange={(e) => setCustomSigPreview(e.target.value)}
                    maxLength={85}
                    className="w-full bg-zinc-950 border border-zinc-700 focus:border-emerald-400 rounded-lg px-3 py-1.5 text-[11px] text-white outline-none"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 space-y-16 pt-14">
        {/* 2. WHO IT'S FOR (4 B2B VERTICALS) */}
        <section className="space-y-6">
          <div className="text-center max-w-2xl mx-auto space-y-2">
            <span className="inline-block border-2 border-black dark:border-white bg-amber-300 text-black px-3 py-0.5 text-[10px] font-black uppercase">
              {isAr ? "لمن صُممت باقات الأعمال؟" : "WHO WE SERVE"}
            </span>
            <h2 className="text-2xl sm:text-3xl font-black text-zinc-950 dark:text-white">
              {isAr ? "4 مسارات جاهزة للربح والتعاون مع الشركات والمجتمعات" : "4 Proven B2B Partner Verticals"}
            </h2>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {segments.map((seg, i) => {
              const Icon = seg.icon;
              return (
                <div
                  key={i}
                  className="border-3 border-black dark:border-zinc-700 bg-white dark:bg-zinc-900 p-5 shadow-[5px_5px_0px_#000] dark:shadow-[5px_5px_0px_#10b981] flex flex-col justify-between gap-4"
                >
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="p-2 border-2 border-black dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800">
                        <Icon className="w-5 h-5 text-emerald-500" />
                      </span>
                      <span className={`text-[10px] font-black px-2 py-0.5 border rounded-full ${seg.accent}`}>
                        {seg.tag}
                      </span>
                    </div>
                    <h3 className="text-base font-black text-zinc-950 dark:text-white leading-snug">
                      {seg.title}
                    </h3>
                    <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400 leading-relaxed">
                      {seg.desc}
                    </p>
                  </div>
                  <div className="pt-3 border-t border-zinc-200 dark:border-zinc-800 text-[11px] font-black text-emerald-600 dark:text-emerald-400">
                    {seg.priceHint}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* 3. SELF-SERVE ONBOARDING STEPS */}
        <section className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 sm:p-8 shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#10b981] space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <span className="text-[10px] font-black uppercase tracking-wider text-emerald-600 dark:text-emerald-400 block">
                {isAr ? "تفعيل فوري بدون مراسلات معقدة" : "SELF-SERVE ONBOARDING"}
              </span>
              <h2 className="text-xl sm:text-2xl font-black text-zinc-950 dark:text-white">
                {isAr ? "⚡ كيف يعمل البوت في مجموعتك خلال 3 خطوات؟" : "⚡ Activate the Bot in Your Group in 3 Steps"}
              </h2>
            </div>
            <button
              type="button"
              disabled={startingTier === "b2b_pro"}
              onClick={() => handleStartTrial("b2b_pro")}
              className="shrink-0 inline-flex items-center gap-2 border-3 border-black bg-emerald-400 hover:bg-emerald-300 text-black font-black px-5 py-3 text-xs uppercase shadow-[3px_3px_0px_#000] cursor-pointer disabled:opacity-50"
            >
              {startingTier === "b2b_pro" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
              <span>{isAr ? "تفعيل تجربة الـ 3 أيام الآن" : "Activate 3-Day Free Trial"}</span>
            </button>
          </div>

          <div className="grid md:grid-cols-3 gap-5">
            <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950 p-4 space-y-2">
              <div className="w-8 h-8 border-2 border-black bg-amber-300 text-black font-black flex items-center justify-center text-sm">
                1
              </div>
              <h3 className="text-sm font-black">{isAr ? "أصدر رخصة التجربة بضغطة زر" : "1-Click Trial License"}</h3>
              <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {isAr
                  ? "بدون بطاقة بنكية. تصدر رخصة لمدة 3 أيام وبها كود ربط فوري لـ 120 استفسار يومياً."
                  : "No credit card required. Instantly provisions a 3-day trial license with 120 daily group queries."}
              </p>
            </div>

            <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950 p-4 space-y-2">
              <div className="w-8 h-8 border-2 border-black bg-emerald-400 text-black font-black flex items-center justify-center text-sm">
                2
              </div>
              <h3 className="text-sm font-black">{isAr ? "أضف @egxbots_bot كمشرف" : "Add @egxbots_bot as Admin"}</h3>
              <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {isAr
                  ? "افتح رابط الربط المباشر لتختار مجموعتك على تليجرام؛ يتعرف البوت تلقائياً على كود التفعيل ويربط الرخصة."
                  : "Use the direct Telegram deep-link to pick your group. The bot binds your license automatically on arrival."}
              </p>
            </div>

            <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950 p-4 space-y-2">
              <div className="w-8 h-8 border-2 border-black bg-sky-400 text-black font-black flex items-center justify-center text-sm">
                3
              </div>
              <h3 className="text-sm font-black">{isAr ? "خصّص التوقيع وراقب الاستهلاك" : "Brand Signature & Analytics"}</h3>
              <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {isAr
                  ? "من لوحة التحكم (/b2b/dashboard) اكتب توقيع قناتك ليظهر أسفل كل تحليل يطلبه الأعضاء."
                  : "Set your custom brand signature in /b2b/dashboard so every member query reinforces your channel identity."}
              </p>
            </div>
          </div>
        </section>

        {/* 4. TRANSPARENT PRICING TIERS */}
        <section id="plans" className="space-y-8">
          <div className="text-center max-w-2xl mx-auto space-y-2">
            <span className="inline-block border-2 border-black dark:border-white bg-emerald-400 text-black px-3 py-0.5 text-[10px] font-black uppercase">
              {isAr ? "باقات ترخيص القنوات والمجموعات" : "TELEGRAM GROUP LICENSING PLANS"}
            </span>
            <h2 className="text-2xl sm:text-3xl font-black text-zinc-950 dark:text-white">
              {isAr ? "خطط واضحة تبدأ من 1,000 ج.م شهرياً + 3 أيام تجربة مجانية" : "Transparent Plans With 3-Day Free Trial"}
            </h2>
            <p className="text-xs sm:text-sm font-bold text-zinc-600 dark:text-zinc-400">
              {isAr
                ? "أسعار موحدة تشمل تغطية السوق المصري (EGX) والسعودي (TASI) · الدفع بالفيزا، فودافون كاش، أو إنستاباي."
                : "Includes full coverage of EGX & Saudi TASI · Cards, Vodafone Cash, or InstaPay."}
            </p>
          </div>

          <div className="grid lg:grid-cols-3 gap-6 items-stretch">
            {B2B_TIERS.map((tier) => (
              <div
                key={tier.id}
                className={`border-4 p-6 sm:p-7 flex flex-col justify-between relative ${
                  tier.is_featured
                    ? "border-emerald-500 bg-gradient-to-b from-emerald-50 via-white to-emerald-50/40 dark:from-emerald-950/40 dark:via-zinc-950 dark:to-emerald-950/20 shadow-[8px_8px_0px_#10b981]"
                    : "border-black dark:border-white bg-white dark:bg-zinc-950 shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#fff]"
                }`}
              >
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                  <span
                    className={`border-2 border-black text-[11px] font-black uppercase px-3 py-0.5 shadow-[2px_2px_0px_#000] whitespace-nowrap flex items-center gap-1 ${
                      tier.is_featured ? "bg-emerald-400 text-black" : "bg-amber-300 text-black"
                    }`}
                  >
                    {tier.is_featured && <Flame className="w-3.5 h-3.5 fill-black" />}
                    {isAr ? tier.max_members_ar : tier.max_members_en}
                  </span>
                </div>

                <div className="space-y-4 pt-2">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-lg sm:text-xl font-black text-zinc-950 dark:text-white">
                      {isAr ? tier.name_ar : tier.name_en}
                    </h3>
                    <span className="text-[10px] font-black border-2 border-black dark:border-white px-2 py-0.5 bg-zinc-200 dark:bg-zinc-800 shrink-0">
                      {tier.tag}
                    </span>
                  </div>

                  <div className="border-b-2 border-zinc-200 dark:border-zinc-800 pb-4">
                    <div className="flex items-baseline gap-2">
                      <span className="text-4xl font-black text-zinc-950 dark:text-white">
                        {toB2BDisplayAmount(tier.amount_egp, isSaudi).toLocaleString()}
                      </span>
                      <span className="text-xs font-bold text-zinc-500">
                        {isAr ? `${currencyLabel} / شهرياً` : `${currencyCode} / mo`}
                      </span>
                    </div>
                    <p className="text-xs font-bold text-emerald-600 dark:text-emerald-400 mt-1.5 flex items-center gap-1">
                      <Zap className="w-3.5 h-3.5" />
                      {isAr
                        ? `${tier.daily_limit} استفسار يومياً (~${tier.monthly_est} شهرياً)`
                        : `${tier.daily_limit} queries/day (~${tier.monthly_est}/mo)`}
                    </p>
                  </div>

                  <ul className="space-y-2.5 text-xs font-bold text-zinc-800 dark:text-zinc-200">
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span>
                        {isAr
                          ? `ترخيص ${tier.groups_count === 2 ? "جروبين منفصلين" : "جروب تليجرام واحد"}`
                          : `License ${tier.groups_count} Telegram VIP group(s)`}
                      </span>
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span>{isAr ? "توقيع تسويقي مخصص باسم قناتك" : "Custom branded signature footer"}</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span>{isAr ? "مانع سبام وتكرار ذكي (90 ثانية)" : "Smart 90s anti-spam cooldown"}</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span>{isAr ? "لوحة تحكم حية لمتابعة الاستهلاك" : "Live B2B usage dashboard"}</span>
                    </li>
                  </ul>
                </div>

                <div className="pt-6 space-y-2.5">
                  <Link
                    href={`/pricing?mode=b2b&plan=${tier.id}`}
                    className={`w-full flex items-center justify-center gap-2 border-3 border-black dark:border-white py-3.5 px-4 text-xs font-black uppercase shadow-[3px_3px_0px_#000] transition-transform hover:-translate-y-0.5 ${
                      tier.is_featured
                        ? "bg-emerald-500 hover:bg-emerald-400 text-black"
                        : "bg-zinc-900 hover:bg-black text-white dark:bg-white dark:text-black"
                    }`}
                  >
                    <Rocket className="w-4 h-4" />
                    <span>{isAr ? `اشترك الآن (${formatPrice(tier.amount_egp)})` : `Subscribe (${formatPrice(tier.amount_egp)})`}</span>
                  </Link>
                  <button
                    type="button"
                    disabled={startingTier === tier.id}
                    onClick={() => handleStartTrial(tier.id)}
                    className="w-full flex items-center justify-center gap-2 border-2 border-black dark:border-white bg-amber-300 hover:bg-amber-200 text-black py-2.5 px-3 text-xs font-black uppercase cursor-pointer disabled:opacity-50"
                  >
                    {startingTier === tier.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                    <span>{isAr ? "🎁 تجربة مجانية 3 أيام" : "🎁 3-Day Free Trial"}</span>
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Custom Brokerage / Fintech / Academy Desk */}
          <div className="border-4 border-black dark:border-emerald-500 bg-gradient-to-r from-zinc-950 via-zinc-900 to-emerald-950 text-white p-6 sm:p-8 shadow-[6px_6px_0px_#000] flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
            <div className="space-y-2 max-w-3xl">
              <div className="inline-flex items-center gap-2 bg-purple-500/20 border border-purple-400/40 px-3 py-1 rounded-full text-[11px] font-black text-purple-200">
                <Cpu className="w-3.5 h-3.5" />
                <span>{isAr ? "لشركات السمسرة وتطبيقات الفنتك والأكاديميات الكبرى" : "BROKERAGES, FINTECH & ACADEMIES"}</span>
              </div>
              <h3 className="text-xl sm:text-2xl font-black">
                {isAr
                  ? "هل تحتاج باقة مقاعد جماعية لطلابك أو دمج تحليلات ARTORO لشركتك؟"
                  : "Need Bulk Student Accounts, Custom Brokerage Integration, or Media Feeds?"}
              </h3>
              <p className="text-xs sm:text-sm text-zinc-300 font-semibold leading-relaxed">
                {isAr
                  ? "نوفر خططاً مخصصة للأكاديميات (خصومات حتى 40% على حسابات Pro الجماعية) واتفاقيات شراكة تقنية لشركات السمسرة والمنصات المالية لتقديم أدوات الفحص الفني، القيمة العادلة، التوافق الشرعي، وملخصات الإفصاحات تحت هويتكم."
                  : "We structure tailored agreements for trading academies (bulk Pro discounts) and brokerages/fintechs seeking analytical tools, disclosures summaries, and Sharia/Fair-Value engines."}
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-3 shrink-0 w-full lg:w-auto">
              <a
                href={whatsappSalesHref}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-2 border-2 border-black bg-emerald-400 hover:bg-emerald-300 text-black font-black px-5 py-3.5 text-xs uppercase shadow-[3px_3px_0px_#000]"
              >
                <MessageSquare className="w-4 h-4" />
                <span>{isAr ? "تواصل مبيعات الشركات (واتساب)" : "WhatsApp Enterprise"}</span>
              </a>
              <a
                href={`https://t.me/${B2B_CONTACT.telegramSupportHandle}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-2 border-2 border-zinc-600 hover:border-white bg-zinc-900 text-white font-black px-5 py-3.5 text-xs uppercase"
              >
                <Send className="w-4 h-4 text-sky-400" />
                <span>@{B2B_CONTACT.telegramSupportHandle}</span>
              </a>
            </div>
          </div>
        </section>

        {/* 5. REGULATORY & TECHNICAL CLARITY */}
        <section className="border-3 border-black dark:border-zinc-700 bg-amber-50 dark:bg-amber-950/20 p-6 space-y-3">
          <div className="flex items-center gap-2 text-amber-800 dark:text-amber-300 font-black text-sm">
            <Scale className="w-5 h-5 shrink-0" />
            <span>
              {isAr
                ? "الوضوح الرقابي والمهني لشركات السمسرة والمؤسسات (FRA & CMA Aligned)"
                : "Regulatory Clarity for Brokerages & Institutions"}
            </span>
          </div>
          <p className="text-xs sm:text-sm font-semibold text-zinc-700 dark:text-zinc-300 leading-relaxed">
            {isAr
              ? "توفر خدمات B2B في منصتنا بنية تقنية وتحليلية مساعدة لاتخاذ القرار (مؤشرات السيولة الفنية، حسابات القيمة العادلة التاريخية، تنقية الأسهم الشرعية، وترجمة وتلخيص إفصاحات البورصة الآلي)، وليست بديلاً عن المستشار المالي المرخص ولا تصدر توصيات استثمارية ملزمة."
              : "Our B2B infrastructure delivers technical indicators, valuation metrics, Sharia screening, and automated disclosure summaries strictly as analytical software tools."}
          </p>
          <div className="pt-1">
            <Link href="/legal-status" className="text-xs font-black text-emerald-700 dark:text-emerald-400 hover:underline">
              {isAr ? "اطلع على صفحة الوضع القانوني وإخلاء المسؤولية ←" : "View Legal Status & Disclaimer ←"}
            </Link>
          </div>
        </section>

        {/* 6. B2B FAQ */}
        <section className="space-y-4">
          <h2 className="text-xl sm:text-2xl font-black text-zinc-950 dark:text-white text-center">
            {isAr ? "الأسئلة الشائعة حول باقات الشركات والقنوات (B2B)" : "Frequently Asked B2B Questions"}
          </h2>
          <div className="grid gap-3 max-w-4xl mx-auto">
            {faqs.map((item, idx) => {
              const isOpen = openFaqIdx === idx;
              return (
                <div
                  key={idx}
                  className="border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-900 overflow-hidden"
                >
                  <button
                    type="button"
                    onClick={() => setOpenFaqIdx(isOpen ? null : idx)}
                    className="w-full px-5 py-4 flex items-center justify-between gap-4 text-start font-black text-xs sm:text-sm cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/60"
                  >
                    <span>{item.q}</span>
                    <span className="text-emerald-500 text-lg leading-none">{isOpen ? "−" : "+"}</span>
                  </button>
                  {isOpen && (
                    <div className="px-5 pb-4 pt-1 text-xs font-semibold text-zinc-600 dark:text-zinc-400 leading-relaxed border-t border-zinc-200 dark:border-zinc-800">
                      {item.a}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      </div>

      {/* 3-Day Free Trial Success Modal */}
      {trialModal?.open && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div
            className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 max-w-lg w-full p-6 sm:p-8 shadow-[8px_8px_0px_#000] dark:shadow-[8px_8px_0px_#fff] space-y-5 relative"
            dir={isAr ? "rtl" : "ltr"}
          >
            <button
              type="button"
              onClick={() => setTrialModal(null)}
              className="absolute top-4 left-4 border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 p-1.5 cursor-pointer"
              aria-label="Close"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="text-center space-y-2">
              <div className="w-16 h-16 border-4 border-black bg-amber-300 text-black flex items-center justify-center mx-auto shadow-[4px_4px_0px_#000]">
                <Bot className="w-8 h-8" />
              </div>
              <h3 className="text-xl sm:text-2xl font-black text-zinc-900 dark:text-white">
                {isAr ? "🎉 تم تفعيل رخصة الـ 3 أيام بنجاح!" : "🎉 3-Day B2B Trial Activated!"}
              </h3>
              <p className="text-xs font-bold text-zinc-600 dark:text-zinc-400">
                {isAr
                  ? "اضغط الزر بالأسفل لاختيار مجموعتك على تليجرام وسيتم ربط الرخصة تلقائياً فور إضافة البوت كمشرف:"
                  : "Click below to pick your Telegram group and auto-activate the bot:"}
              </p>
            </div>

            <a
              href={trialModal.connectUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full flex items-center justify-center gap-2 border-4 border-black bg-emerald-500 hover:bg-emerald-400 text-black py-4 px-4 text-xs sm:text-sm font-black uppercase shadow-[4px_4px_0px_#000]"
            >
              <ExternalLink className="w-4 h-4 shrink-0" />
              <span>{isAr ? "🚀 ربط وتفعيل البوت في مجموعتي الآن (تليجرام)" : "🚀 Connect Bot to Telegram Group"}</span>
            </a>

            <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 p-3 flex items-center justify-between gap-2 text-xs">
              <div>
                <span className="text-[10px] font-bold text-zinc-500 block">
                  {isAr ? "أمر التفعيل اليدوي داخل الجروب (اختياري):" : "Manual Group Command (Optional):"}
                </span>
                <code className="font-mono font-black text-emerald-600 dark:text-emerald-400" dir="ltr">
                  /activate {trialModal.code}
                </code>
              </div>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(`/activate ${trialModal.code}`);
                  toast.success(isAr ? "تم نسخ أمر التفعيل" : "Copied activation command");
                }}
                className="border-2 border-black bg-white dark:bg-zinc-900 px-3 py-1.5 text-[11px] font-black flex items-center gap-1 cursor-pointer"
              >
                <Copy className="w-3.5 h-3.5" />
                <span>{isAr ? "نسخ" : "Copy"}</span>
              </button>
            </div>

            <div className="flex items-center justify-between text-xs pt-1">
              <Link
                href="/b2b/dashboard"
                onClick={() => setTrialModal(null)}
                className="font-black text-emerald-600 dark:text-emerald-400 hover:underline"
              >
                {isAr ? "الانتقال للوحة التحكم وتعديل التوقيع ←" : "Open B2B Dashboard →"}
              </Link>
              <span className="font-mono text-[11px] text-zinc-400">#{trialModal.code}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
