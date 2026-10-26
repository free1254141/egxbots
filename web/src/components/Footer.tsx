"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLanguage } from "@/contexts/LanguageContext";
import { ShieldCheck, Lock, Smartphone, ExternalLink, Download } from "lucide-react";

export default function Footer() {
  const { t, language } = useLanguage();
  const isAr = language === "ar";
  const pathname = usePathname();

  if (pathname === "/antigrafity" || pathname?.startsWith("/antigrafity") || pathname === "/chat" || pathname?.startsWith("/chat") || pathname === "/chart" || pathname?.startsWith("/chart")) {
    return null;
  }

  return (
    <footer className="app-footer-surface relative overflow-hidden w-full py-12 mt-20">
      {/* Left-side Hanging Palestine Watermelon Pennant (0% -> 75% of footer height, positioned next to logo on large screens) */}
      <div
        dir="ltr"
        aria-label={isAr ? "تضامناً مع إخوتنا في فلسطين" : "Standing in solidarity with Palestine"}
        title={isAr ? "في القلب يا فلسطين" : "Standing with Palestine"}
        className="pointer-events-none select-none absolute left-2 sm:left-4 md:left-6 lg:left-[max(1.5rem,calc(50%-33rem))] xl:left-[max(2rem,calc(50%-34.5rem))] top-0 h-[75%] w-11 sm:w-16 md:w-20 lg:w-24 z-10 flex flex-col items-stretch drop-shadow-[0_6px_12px_rgba(0,0,0,0.32)]"
      >
        {/* Top Section: Stripes + Red Downward Triangle (aspect-ratio preserved) */}
        <svg
          viewBox="0 0 128 68"
          className="w-full h-auto shrink-0 block"
          aria-hidden="true"
        >
          <rect x="0" y="0" width="43" height="68" fill="#15803D" />
          <rect x="43" y="0" width="42" height="68" fill="#F8FAFC" />
          <rect x="85" y="0" width="43" height="68" fill="#18181B" />
          <polygon points="0,0 128,0 64,66" fill="#B91C1C" />
          <polyline
            points="0,0 64,66 128,0"
            fill="none"
            stroke="#000000"
            strokeOpacity="0.22"
            strokeWidth="3"
          />
        </svg>

        {/* Middle Section: Flexible Vertical Flag Shaft + Undistorted Tilted Watermelon Slice */}
        <div className="relative flex-1 w-full flex items-center justify-center pb-4 -my-px">
          <svg
            viewBox="0 0 128 100"
            preserveAspectRatio="none"
            className="absolute inset-0 w-full h-full block"
            aria-hidden="true"
          >
            <rect x="0" y="0" width="43" height="100" fill="#15803D" />
            <rect x="43" y="0" width="42" height="100" fill="#F8FAFC" />
            <rect x="85" y="0" width="43" height="100" fill="#18181B" />
            <polygon points="0,30 128,0 128,100 0,100" fill="#000000" fillOpacity="0.08" />
          </svg>
          {/* Center Tilted Watermelon Slice */}
          <svg
            viewBox="0 0 128 110"
            className="relative z-10 w-[92%] h-auto object-contain drop-shadow-[0_4px_5px_rgba(0,0,0,0.38)]"
            aria-hidden="true"
          >
            <g transform="translate(66, 52) rotate(-28)">
              <path
                d="M -54 0 A 54 54 0 0 0 54 0 Z"
                fill="#16A34A"
                stroke="#14532D"
                strokeWidth="1.8"
                strokeLinejoin="round"
              />
              <path d="M -48 0 A 48 48 0 0 0 48 0 Z" fill="#ECFDF5" />
              <path d="M -45 0 A 45 45 0 0 0 45 0 Z" fill="#DCFCE7" />
              <path d="M -42 0 A 42 42 0 0 0 42 0 Z" fill="#EF4444" />
              <line
                x1="-42"
                y1="0.8"
                x2="42"
                y2="0.8"
                stroke="#FCA5A5"
                strokeWidth="1.2"
                strokeOpacity="0.5"
              />
              <ellipse cx="-19" cy="12" rx="2" ry="3.5" transform="rotate(28 -19 12)" fill="#18181B" />
              <ellipse cx="-6.5" cy="16" rx="2" ry="3.5" transform="rotate(10 -6.5 16)" fill="#18181B" />
              <ellipse cx="6.5" cy="16" rx="2" ry="3.5" transform="rotate(-10 6.5 16)" fill="#18181B" />
              <ellipse cx="19" cy="12" rx="2" ry="3.5" transform="rotate(-28 19 12)" fill="#18181B" />
              <ellipse cx="-28" cy="20" rx="2" ry="3.5" transform="rotate(40 -28 20)" fill="#18181B" />
              <ellipse cx="-15" cy="27" rx="2" ry="3.5" transform="rotate(20 -15 27)" fill="#18181B" />
              <ellipse cx="0" cy="30" rx="2" ry="3.5" fill="#18181B" />
              <ellipse cx="15" cy="27" rx="2" ry="3.5" transform="rotate(-20 15 27)" fill="#18181B" />
              <ellipse cx="28" cy="20" rx="2" ry="3.5" transform="rotate(-40 28 20)" fill="#18181B" />
            </g>
          </svg>
        </div>

        {/* Bottom Section: Pointed V-Tip + White Keffiyeh Fringes (aspect-ratio preserved) */}
        <svg
          viewBox="0 0 128 84"
          className="w-full h-auto shrink-0 block"
          aria-hidden="true"
        >
          <defs>
            <clipPath id="footerPennantBottomClip">
              <polygon points="0,0 128,0 128,10 64,56 0,10" />
            </clipPath>
          </defs>
          <g stroke="#E2E8F0" strokeWidth="2.4" strokeLinecap="round">
            <line x1="3" y1="12" x2="3" y2="36" />
            <line x1="8" y1="16" x2="8" y2="40" />
            <line x1="13" y1="19" x2="13" y2="43" />
            <line x1="18" y1="23" x2="18" y2="47" />
            <line x1="23" y1="26" x2="23" y2="50" />
            <line x1="28" y1="30" x2="28" y2="54" />
            <line x1="33" y1="34" x2="33" y2="58" />
            <line x1="38" y1="37" x2="38" y2="61" />
            <line x1="43" y1="41" x2="43" y2="65" />
            <line x1="48" y1="44" x2="48" y2="68" />
            <line x1="53" y1="48" x2="53" y2="72" />
            <line x1="58" y1="52" x2="58" y2="76" />
            <line x1="64" y1="55" x2="64" y2="80" />
            <line x1="70" y1="52" x2="70" y2="76" />
            <line x1="75" y1="48" x2="75" y2="72" />
            <line x1="80" y1="44" x2="80" y2="68" />
            <line x1="85" y1="41" x2="85" y2="65" />
            <line x1="90" y1="37" x2="90" y2="61" />
            <line x1="95" y1="34" x2="95" y2="58" />
            <line x1="100" y1="30" x2="100" y2="54" />
            <line x1="105" y1="26" x2="105" y2="50" />
            <line x1="110" y1="23" x2="110" y2="47" />
            <line x1="115" y1="19" x2="115" y2="43" />
            <line x1="120" y1="16" x2="120" y2="40" />
            <line x1="125" y1="12" x2="125" y2="36" />
          </g>
          <g stroke="#94A3B8" strokeWidth="1" strokeLinecap="round" opacity="0.65">
            <line x1="5.5" y1="14" x2="5.5" y2="34" />
            <line x1="15.5" y1="21" x2="15.5" y2="41" />
            <line x1="25.5" y1="28" x2="25.5" y2="48" />
            <line x1="35.5" y1="35" x2="35.5" y2="55" />
            <line x1="45.5" y1="43" x2="45.5" y2="63" />
            <line x1="55.5" y1="50" x2="55.5" y2="70" />
            <line x1="72.5" y1="50" x2="72.5" y2="70" />
            <line x1="82.5" y1="43" x2="82.5" y2="63" />
            <line x1="92.5" y1="35" x2="92.5" y2="55" />
            <line x1="102.5" y1="28" x2="102.5" y2="48" />
            <line x1="112.5" y1="21" x2="112.5" y2="41" />
            <line x1="122.5" y1="14" x2="122.5" y2="34" />
          </g>
          <g clipPath="url(#footerPennantBottomClip)">
            <rect x="0" y="0" width="43" height="60" fill="#15803D" />
            <rect x="43" y="0" width="42" height="60" fill="#F8FAFC" />
            <rect x="85" y="0" width="43" height="60" fill="#18181B" />
            <polygon points="0,0 128,0 128,60 0,60" fill="#000000" fillOpacity="0.1" />
          </g>
        </svg>
      </div>

      <div className="relative z-10 mx-auto max-w-5xl pr-6 pl-16 sm:pl-24 md:pl-32 lg:pl-36 xl:pl-24">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-12 mb-10">
          <div className="col-span-1 md:col-span-2 space-y-4">
            <h3 className="text-xl font-black dark:text-white light:text-gray-900 italic tracking-tighter uppercase">
              {t("app.title")}
            </h3>
            <p className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 max-w-xs leading-relaxed">
              {t("footer.tagline")}
            </p>
            <div className="pt-1 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 border border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs font-bold rounded">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                <span>{isAr ? "مدفوعات مشفرة ومعتمدة عبر EasyKash" : "Secured by EasyKash Payment Gateway"}</span>
              </span>

              <a
                href="/artoro.apk"
                download="artoro.apk"
                className="inline-flex items-center gap-1.5 px-2.5 py-1 border border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-bold rounded transition-colors shadow-2xs"
                title="تحميل تطبيق أندرويد APK"
              >
                <Smartphone className="w-3.5 h-3.5 text-emerald-500" />
                <span>{isAr ? "تطبيق أندرويد APK (3.5 MB)" : "Android App APK (3.5 MB)"}</span>
                <Download className="w-3 h-3" />
              </a>
            </div>
          </div>

          <div className="space-y-4">
            <h4 className="text-[10px] font-black dark:text-white light:text-gray-900 uppercase tracking-[0.3em]">
              {t("footer.platform")}
            </h4>
            <ul className="space-y-2">
              <li>
                <Link
                  href="/stocks"
                  className="text-sm font-bold text-yellow-600 dark:text-yellow-400 hover:underline transition-colors"
                >
                  {t("nav.stocks")}
                </Link>
              </li>
              <li>
                <Link
                  href="/scanner/ai"
                  className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 hover:text-indigo-400 dark:hover:text-indigo-400 light:hover:text-indigo-600 transition-colors font-bold text-indigo-400/80 dark:text-indigo-400/80 light:text-indigo-600/80"
                >
                  {t("nav.scanner.ai")}
                </Link>
              </li>
              <li>
                <Link
                  href="/news"
                  className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 hover:text-indigo-400 dark:hover:text-indigo-400 light:hover:text-indigo-600 transition-colors font-bold text-indigo-400/80 dark:text-indigo-400/80 light:text-indigo-600/80"
                >
                  {t("nav.scanner.news")}
                </Link>
              </li>
              <li>
                <Link
                  href="/scanner/technical"
                  className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 hover:text-indigo-400 dark:hover:text-indigo-400 light:hover:text-indigo-600 transition-colors"
                >
                  {t("nav.scanner.tech")}
                </Link>
              </li>
              <li>
                <Link
                  href="/scanner/market"
                  className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 hover:text-indigo-400 dark:hover:text-indigo-400 light:hover:text-indigo-600 transition-colors"
                >
                  {t("nav.scanner.market")}
                </Link>
              </li>
              <li>
                <Link
                  href="/scanner/backtests"
                  className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 hover:text-indigo-400 dark:hover:text-indigo-400 light:hover:text-indigo-600 transition-colors"
                >
                  {t("nav.scanner.backtests")}
                </Link>
              </li>
              <li>
                <a
                  href="/artoro.apk"
                  download="artoro.apk"
                  className="inline-flex items-center gap-1.5 text-sm font-bold text-emerald-600 dark:text-emerald-400 hover:underline transition-colors"
                >
                  <Smartphone className="w-3.5 h-3.5" />
                  <span>{isAr ? "تحميل تطبيق أندرويد (APK)" : "Download Android App (APK)"}</span>
                </a>
              </li>
            </ul>
          </div>

          <div className="space-y-4">
            <h4 className="text-[10px] font-black dark:text-white light:text-gray-900 uppercase tracking-[0.3em]">
              {t("footer.resources")}
            </h4>
            <ul className="space-y-2">
              <li>
                <Link
                  href="/blogs"
                  className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 hover:text-indigo-400 dark:hover:text-indigo-400 light:hover:text-indigo-600 transition-colors"
                >
                  {t("footer.blogs")}
                </Link>
              </li>
              <li><Link href="/reports" className="text-sm text-zinc-500 hover:text-amber-500">تقارير السوق والتجميع · Daily reports</Link></li>
              <li>
                <Link
                  href="/faq"
                  className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 hover:text-indigo-400 dark:hover:text-indigo-400 light:hover:text-indigo-600 transition-colors"
                >
                  {t("footer.faq")}
                </Link>
              </li>
              <li>
                <Link
                  href="/disclaimer"
                  className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 hover:text-indigo-400 dark:hover:text-indigo-400 light:hover:text-indigo-600 transition-colors"
                >
                  {t("footer.disclaimer")}
                </Link>
              </li>
              <li>
                <Link
                  href="/legal-status"
                  className="text-sm text-amber-500/90 dark:text-amber-400/90 light:text-amber-600 hover:text-amber-500 dark:hover:text-amber-300 transition-colors font-bold"
                >
                  {t("footer.legal_status")}
                </Link>
              </li>
              <li>
                <Link
                  href="/pricing"
                  className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 hover:text-indigo-400 dark:hover:text-indigo-400 light:hover:text-indigo-600 transition-colors"
                >
                  {t("footer.pricing")}
                </Link>
              </li>
              <li>
                <Link
                  href="/refund"
                  className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 hover:text-indigo-400 dark:hover:text-indigo-400 light:hover:text-indigo-600 transition-colors"
                >
                  {t("footer.refund")}
                </Link>
              </li>
              <li>
                <a
                  href="https://www.facebook.com/egxbots"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 hover:text-indigo-400 dark:hover:text-indigo-400 light:hover:text-indigo-600 transition-colors"
                >
                  {t("footer.facebook")}
                </a>
              </li>
              <li>
                <a
                  href="https://web.telegram.org/a/#-1002083067817_153"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-zinc-500 dark:text-zinc-500 light:text-gray-600 hover:text-indigo-400 dark:hover:text-indigo-400 light:hover:text-indigo-600 transition-colors"
                >
                  {t("footer.telegram")}
                </a>
              </li>
              <li>
                <a
                  href="https://wa.me/201024359109"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-bold text-emerald-500 hover:text-emerald-400 transition-colors"
                >
                  {isAr ? "الدعم عبر واتساب" : "WhatsApp Support"}
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* ── Official EasyKash Payment Gateway Integration ── */}
        <div className="border-2 border-black/10 dark:border-white/10 bg-zinc-50/80 dark:bg-zinc-900/60 p-5 sm:p-6 mb-10 shadow-sm transition-all hover:border-emerald-500/40">
          <div className="flex flex-col lg:flex-row items-center justify-between gap-6">
            {/* Identity & Legal Trust */}
            <div className="space-y-2 text-center lg:text-start max-w-xl">
              <div className="flex items-center justify-center lg:justify-start gap-2.5 flex-wrap">
                {/* EasyKash Badge */}
                <a
                  href="https://easykash.net"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group inline-flex items-center gap-2 px-3 py-1 bg-white dark:bg-zinc-950 border-2 border-black/20 dark:border-white/20 hover:border-emerald-500 transition-all shadow-[2px_2px_0px_rgba(0,0,0,0.1)]"
                  title="EasyKash Payment Gateway"
                >
                  {/* Stylized EasyKash Fintech Emblem */}
                  <div className="w-5 h-5 rounded bg-emerald-500 flex items-center justify-center text-white font-black text-xs shadow-xs">
                    E
                  </div>
                  <div className="flex items-baseline font-black font-mono tracking-tight text-sm">
                    <span className="text-zinc-900 dark:text-white">Easy</span>
                    <span className="text-emerald-500 font-extrabold">Kash</span>
                  </div>
                  <ExternalLink className="w-3 h-3 text-zinc-400 group-hover:text-emerald-500 transition-colors" />
                </a>

                <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-300 text-[11px] font-black">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                  <span>{isAr ? "شريك الدفع الإلكتروني الرسمي" : "Official Payment Partner"}</span>
                </span>

                <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-300 text-[11px] font-black">
                  <Lock className="w-3 h-3 text-amber-500" />
                  <span>{isAr ? "مرخص بضوابط البنك المركزي المصري" : "Central Bank of Egypt Compliant"}</span>
                </span>
              </div>

              <p className="text-xs text-zinc-600 dark:text-zinc-400 font-medium leading-relaxed">
                {isAr
                  ? "تتم جميع عمليات تحصيل الاشتراكات حصراً بالجنيه المصري من خلال بوابة EasyKash المشفرة برخصة البنك المركزي المصري بتشفير بنكي 256-bit SSL. المنصة لا تحفظ ولا تطلع على أي أرقام بطاقات أو بيانات سرية للمشتركين."
                  : "All subscription transactions are conducted exclusively in EGP via EasyKash, an authorized payment processor compliant with Central Bank of Egypt regulations with 256-bit SSL encryption. We never store sensitive card data."}
              </p>
            </div>

            {/* Supported Payment Channels in Egypt */}
            <div className="flex flex-col items-center lg:items-end gap-2 shrink-0">
              <span className="text-[10px] font-black tracking-widest text-zinc-500 dark:text-zinc-400 uppercase">
                {isAr ? "وسائل الدفع المعتمدة عبر EasyKash" : "Accepted Payment Methods"}
              </span>

              <div className="flex items-center gap-1.5 flex-wrap justify-center">
                {/* Meeza */}
                <div
                  className="px-2.5 py-1 bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-800 text-[11px] font-black text-emerald-700 dark:text-emerald-400 flex items-center gap-1 shadow-2xs"
                  title="كروت ميزة الوطنية المصرية"
                >
                  <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block"></span>
                  <span>ميزة Meeza</span>
                </div>

                {/* Visa */}
                <div
                  className="px-2.5 py-1 bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-800 text-[11px] font-black text-blue-600 dark:text-blue-400 shadow-2xs"
                  title="Visa"
                >
                  VISA
                </div>

                {/* Mastercard */}
                <div
                  className="px-2.5 py-1 bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-800 text-[11px] font-black text-zinc-900 dark:text-zinc-100 flex items-center gap-1.5 shadow-2xs"
                  title="Mastercard"
                >
                  <div className="flex -space-x-1">
                    <span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block"></span>
                    <span className="w-2.5 h-2.5 rounded-full bg-amber-500 opacity-80 inline-block"></span>
                  </div>
                  <span>Mastercard</span>
                </div>

                {/* Smart Wallets */}
                <div
                  className="px-2.5 py-1 bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-800 text-[11px] font-bold text-zinc-700 dark:text-zinc-300 flex items-center gap-1 shadow-2xs"
                  title="المحافظ الذكية: فودافون كاش، أورنج كاش، اتصالات كاش، وي باي"
                >
                  <Smartphone className="w-3 h-3 text-indigo-500" />
                  <span>{isAr ? "المحافظ الذكية" : "Smart Wallets"}</span>
                </div>

                {/* InstaPay */}
                <div
                  className="px-2.5 py-1 bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-800 text-[11px] font-black text-violet-600 dark:text-violet-400 shadow-2xs"
                  title="شبكة المدفوعات اللحظية انستاباي"
                >
                  <span>InstaPay</span>
                </div>

                {/* Cash & Aman */}
                <div
                  className="px-2.5 py-1 bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-800 text-[11px] font-bold text-amber-600 dark:text-amber-400 shadow-2xs"
                  title="أمان وفوري ومنافذ الدفع النقدي"
                >
                  <span>{isAr ? "منافذ التحصيل" : "Cash Outlets"}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="border-t border-white/5 dark:border-white/5 light:border-gray-300 pt-8 flex flex-col md:flex-row justify-between items-center gap-4 text-center md:text-left">
          <p className="text-[10px] font-black text-zinc-700 dark:text-zinc-700 light:text-gray-600 uppercase tracking-widest">
            {t("footer.copyright")}
          </p>

          <div className="flex items-center gap-2 text-[10px] font-bold text-zinc-500 dark:text-zinc-500">
            <Lock className="w-3 h-3 text-emerald-500" />
            <span>
              {isAr
                ? "بوابة الدفع مؤمنة ومشفرة بواسطة EasyKash"
                : "Payments securely powered & encrypted by EasyKash"}
            </span>
          </div>
        </div>

        <p className="mt-8 text-[9px] font-bold text-zinc-800 dark:text-zinc-800 light:text-gray-700 text-center uppercase tracking-widest leading-relaxed">
          {t("home.footer.disclaimer")}
        </p>
      </div>
    </footer>
  );
}

