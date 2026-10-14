"use client";

import { useEffect, useState } from "react";
import { Smartphone, Download, X } from "lucide-react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export default function PwaInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isStandalone, setIsStandalone] = useState(false);
  const [isDismissed, setIsDismissed] = useState(false);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    // Check if running in standalone mode (PWA/TWA already installed)
    const standalone = window.matchMedia("(display-mode: standalone)").matches ||
      (window.navigator as any).standalone === true;
    setIsStandalone(standalone);

    // Check if dismissed recently
    const dismissedAt = localStorage.getItem("artoro_pwa_dismissed");
    if (dismissedAt && Date.now() - Number(dismissedAt) < 7 * 24 * 60 * 60 * 1000) {
      setIsDismissed(true);
    }

    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };

    window.addEventListener("beforeinstallprompt", handleBeforeInstall);
    return () => window.removeEventListener("beforeinstallprompt", handleBeforeInstall);
  }, []);

  const handleInstallClick = async () => {
    if (deferredPrompt) {
      await deferredPrompt.prompt();
      const choice = await deferredPrompt.userChoice;
      if (choice.outcome === "accepted") {
        setDeferredPrompt(null);
      }
    } else {
      setShowModal(true);
    }
  };

  const handleDismiss = () => {
    setIsDismissed(true);
    localStorage.setItem("artoro_pwa_dismissed", String(Date.now()));
  };

  if (isStandalone || isDismissed) {
    return null;
  }

  return (
    <>
      <div className="fixed bottom-20 left-4 z-40 flex items-center gap-2.5 rounded-xl border border-emerald-500/30 bg-zinc-950/95 px-3 py-2 text-white shadow-2xl backdrop-blur-md md:bottom-6 md:left-6 transition-all duration-300 animate-in fade-in slide-in-from-bottom-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400">
          <Smartphone className="h-4 w-4" />
        </div>
        <div className="flex flex-col text-right">
          <span className="text-xs font-bold leading-tight">تطبيق ARTORO</span>
          <span className="text-[10px] text-zinc-400">تثبيت سريع وخفيف للأندرويد</span>
        </div>
        <button
          onClick={handleInstallClick}
          className="ml-2 flex items-center gap-1.5 rounded-lg bg-emerald-500 px-2.5 py-1 text-xs font-bold text-zinc-950 hover:bg-emerald-400 transition-colors shadow-sm"
        >
          <Download className="h-3.5 w-3.5" />
          تثبيت
        </button>
        <button
          onClick={handleDismiss}
          className="p-1 text-zinc-500 hover:text-zinc-300 transition-colors"
          title="إغلاق"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-2xl border border-zinc-800 bg-zinc-900 p-5 text-right text-white shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
              <button onClick={() => setShowModal(false)} className="text-zinc-400 hover:text-white">
                <X className="h-5 w-5" />
              </button>
              <h3 className="font-bold text-sm">تثبيت تطبيق ARTORO للأندرويد</h3>
            </div>
            <div className="py-4 space-y-3 text-xs text-zinc-300">
              <p className="font-medium text-emerald-400">لتثبيت التطبيق على هاتفك مباشرة:</p>
              <ol className="list-decimal list-inside space-y-1.5 pr-1 text-zinc-400">
                <li>اضغط على زر القائمة <span className="font-bold text-white">⋮</span> أعلى متصفح Chrome.</li>
                <li>اختر <span className="font-bold text-white">&quot;تثبيت التطبيق&quot; (Install app)</span> أو <span className="font-bold text-white">&quot;الإضافة إلى الشاشة الرئيسية&quot;</span>.</li>
                <li>سيتم تثبيت التطبيق فوراً والعمل كتطبيق أصلي فائق الخفة والسرعة.</li>
              </ol>

              <div className="pt-2 border-t border-zinc-800/80">
                <p className="text-[11px] text-zinc-400 mb-2">أو تحميل ملف التطبيق المباشر (APK):</p>
                <a
                  href="/artoro.apk"
                  download="artoro.apk"
                  className="flex items-center justify-center gap-1.5 w-full rounded-xl bg-emerald-500/15 border border-emerald-500/30 py-2 text-xs font-bold text-emerald-400 hover:bg-emerald-500/25 transition-colors"
                >
                  <Download className="h-3.5 w-3.5" />
                  تحميل ملف APK مباشرة (3.5 MB)
                </a>
              </div>
            </div>
            <button
              onClick={() => setShowModal(false)}
              className="w-full rounded-xl bg-zinc-800 py-2 text-xs font-semibold hover:bg-zinc-700 transition-colors"
            >
              إغلاق
            </button>
          </div>
        </div>
      )}
    </>
  );
}
