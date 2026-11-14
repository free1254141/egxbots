import "./globals.css";
import type { ReactNode } from "react";
import { Suspense } from "react";
import Providers from "@/app/providers";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import ChatWidget from "@/components/ChatWidget";
import SupportChatWidget from "@/components/SupportChatWidget";
import PwaInstallPrompt from "@/components/PwaInstallPrompt";
import TrialWelcomePrompt from "@/components/TrialWelcomePrompt";
import MarketWelcomeDialog from "@/components/MarketWelcomeDialog";
import { Analytics } from "@vercel/analytics/react";
import type { Metadata, Viewport } from "next";

export const viewport: Viewport = {
  themeColor: "#09090b",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export const metadata: Metadata = {
  metadataBase: new URL('https://egxbots.com'),
  alternates: {
    canonical: 'https://egxbots.com',
  },
  title: {
    default: "EGX BOTS | تحليل الأسهم المصرية والسعودية (EGX & TASI) بالذكاء الاصطناعي",
    template: "%s | EGX BOTS"
  },
  description: "EGX BOTS منصة تحليل الأسهم المصرية (EGX) والسعودية (تداول تاسي TASI) بالذكاء الاصطناعي: تقييمات AI يومية، ماسح فني، اختبارات تاريخية، ومساعد تفاعلي عربي وإنجليزي.",
  keywords: [
    "EGX BOTS",
    "egxbots",
    "egx bot",
    "egx bots",
    "egx ai analyzer",
    "تحليل الأسهم المصرية بالذكاء الاصطناعي",
    "محلل الأسهم المصرية بالذكاء الاصطناعي",
    "تحليل الأسهم السعودية بالذكاء الاصطناعي",
    "توصيات تاسي",
    "سهم أرامكو 2222",
    "سهم الراجحي 1120",
    "تداول السعودية",
    "السوق السعودي تاسي TASI",
    "أفضل برنامج تحليل الأسهم المصرية والسعودية",
    "بوت تحليل الاسهم",
    "إي جي إكس بوتس",
    "البورصة المصرية",
    "EGX",
    "TASI",
    "ذكاء اصطناعي",
    "تحليل أسهم",
    "ماسح البورصة المصرية والسعودية",
    "مؤشرات البورصة المصرية وتاسي",
    "تداول آلي",
    "إشارات تداول",
    "شات بوت ذكي",
    "AI Chatbot",
    "مساعد ذكي للبورصة"
  ],
  authors: [{ name: "EGX BOTS Team" }],
  creator: "EGX BOTS",
  openGraph: {
    type: "website",
    locale: "ar_EG",
    url: "https://egxbots.com",
    title: "EGX BOTS | تحليل الأسهم المصرية والسعودية (EGX & TASI) بالذكاء الاصطناعي",
    description: "منصة EGX BOTS لتحليل أسهم البورصة المصرية (EGX) والسوق السعودي تداول (TASI) بالذكاء الاصطناعي: رادار الصفقات، تقييمات AI Score، المحاكاة التاريخية، ومستويات الدعم والمقاومة.",
    siteName: "EGX BOTS",
    images: [
      {
        url: "https://egxbots.com/opengraph-image.png",
        secureUrl: "https://egxbots.com/opengraph-image.png",
        width: 1200,
        height: 630,
        type: "image/png",
        alt: "EGX BOTS - منصة تحليل الأسهم المصرية والسعودية بالذكاء الاصطناعي",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "EGX BOTS | EGX & Saudi TASI AI Stock Analyzer | محلل الأسهم المصرية والسعودية",
    description: "Advanced AI Stock Analyzer for the Egyptian Exchange (EGX) and Saudi Tadawul (TASI) with technical scanning, daily AI scores, backtests, and AI chatbot.",
    images: ["https://egxbots.com/dashboard_preview.png"],
  },
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "ARTORO",
  },
  icons: {
    icon: [
      { url: "/favicon_io/favicon.ico", type: "image/x-icon" },
      { url: "/favicon_io/favicon-32x32.png", type: "image/png", sizes: "32x32" },
      { url: "/favicon_io/favicon-16x16.png", type: "image/png", sizes: "16x16" }
    ],
    shortcut: "/favicon_io/favicon.ico",
    apple: "/favicon_io/apple-touch-icon.png",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-video-preview': -1,
      'max-image-preview': 'large',
      'max-snippet': -1,
    },
  },
  verification: {
    other: {
      'msvalidate.01': '0A096C457F5CBA6563B74FAF4EBB0F47',
    },
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="ar" dir="ltr" suppressHydrationWarning>
      <head>
        {/* Google Tag (GTM / Google Ads) */}
        <script async src="https://www.googletagmanager.com/gtm.js?id=GTM-532ZRZ68" />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              window.dataLayer = window.dataLayer || [];
              function gtag(){dataLayer.push(arguments);}
              gtag('js', new Date());
            `,
          }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@graph": [
                {
                  "@type": "WebSite",
                  "@id": "https://egxbots.com/#website",
                  "url": "https://egxbots.com",
                  "name": "EGX BOTS",
                  "alternateName": ["ARTORO", "ARTORO AI", "EGX AI Analyzer", "egxbots", "محلل الأسهم المصرية والسعودية بالذكاء الاصطناعي"],
                  "description": "منصة تحليل الأسهم المصرية (EGX) والسعودية (تداول تاسي TASI) بتقييمات يومية، ماسح فني، ونتائج تاريخية.",
                  "inLanguage": "ar-EG",
                  "publisher": { "@id": "https://egxbots.com/#organization" },
                  "potentialAction": {
                    "@type": "SearchAction",
                    "target": "https://egxbots.com/stocks?q={search_term_string}",
                    "query-input": "required name=search_term_string"
                  }
                },
                {
                  "@type": "Organization",
                  "@id": "https://egxbots.com/#organization",
                  "name": "EGX BOTS",
                  "url": "https://egxbots.com",
                  "logo": "https://egxbots.com/favicon_io/android-chrome-512x512.png",
                  "image": "https://egxbots.com/dashboard_preview.png",
                  "description": "منصة لتحليل بيانات البورصة المصرية (EGX) والسوق السعودي تداول (TASI) باستخدام نماذج كمية وماسح فني ونتائج تاريخية.",
                  "sameAs": [
                    "https://t.me/egxbots",
                    "https://www.facebook.com/egxbots"
                  ],
                  "address": {
                    "@type": "PostalAddress",
                    "addressCountry": "EG"
                  }
                },
                {
                  "@type": "SoftwareApplication",
                  "@id": "https://egxbots.com/#software-application",
                  "name": "EGX BOTS - AI Stock Analyzer",
                  "alternateName": ["ARTORO", "ARTORO AI", "egx ai analyzer", "محلل الأسهم المصرية"],
                  "operatingSystem": "Web",
                  "applicationCategory": "FinanceApplication",
                  "description": "EGX BOTS (egxbots) is an advanced AI-driven stock analyzer for the Egyptian Exchange (EGX) and Saudi Tadawul (TASI) featuring daily AI scores, quantitative scanners, and market chatbot.",
                  "offers": {
                    "@type": "Offer",
                    "price": "0",
                    "priceCurrency": "EGP"
                  },
                  "provider": { "@id": "https://egxbots.com/#organization" }
                }
              ]
            })
          }}
        />
        {/* Script to prevent FOUC (Flash of Unstyled Content) */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  const saved = localStorage.getItem('theme');
                  const preferred = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
                  const theme = saved || preferred;
                  
                  if (theme === 'light') {
                    document.documentElement.classList.remove('dark');
                    document.documentElement.classList.add('light');
                  } else {
                    document.documentElement.classList.remove('light');
                    document.documentElement.classList.add('dark');
                  }
                } catch (e) {}
              })();
            `,
          }}
        />
      </head>
      <body className="app-shell antialiased selection:dark:bg-blue-500/30 selection:light:bg-blue-300/30">
        <noscript>
          <iframe
            src="https://www.googletagmanager.com/ns.html?id=GTM-532ZRZ68"
            height="0"
            width="0"
            style={{ display: "none", visibility: "hidden" }}
          />
        </noscript>
        <Providers>
          <Suspense fallback={null}><Header /></Suspense>
          <main id="main-content" className="app-content-shell w-full pt-[var(--header-offset,88px)] pb-12 px-3 sm:px-6 md:px-8 mx-auto max-w-[1800px]">
            {children}
          </main>
          <Footer />
          <ChatWidget />
          <SupportChatWidget />
          <PwaInstallPrompt />
          <TrialWelcomePrompt />
          <MarketWelcomeDialog />
          <Analytics />
        </Providers>
      </body>
    </html>
  );
}
