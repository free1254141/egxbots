"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, RefreshCw, Sparkles } from "lucide-react";

export default function Error({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    const [isChunkError, setIsChunkError] = useState(false);

    useEffect(() => {
        console.error("Application error:", error);

        const msg = error?.message || "";
        const isChunk =
            error?.name === "ChunkLoadError" ||
            msg.includes("Loading chunk") ||
            msg.includes("ChunkLoadError") ||
            msg.includes("Failed to fetch dynamically imported module");

        if (isChunk) {
            setIsChunkError(true);
            const key = `chunk_reload_${typeof window !== "undefined" ? window.location.pathname : ""}`;
            if (typeof window !== "undefined" && !sessionStorage.getItem(key)) {
                sessionStorage.setItem(key, Date.now().toString());
                window.location.reload();
            }
        }
    }, [error]);

    const handleRetry = () => {
        if (typeof window !== "undefined") {
            window.location.reload();
        } else {
            reset();
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center p-6 bg-zinc-950 text-white" dir="rtl">
            <div className="max-w-md w-full text-center space-y-6 p-6 rounded-2xl bg-zinc-900/60 border border-zinc-800 shadow-2xl">
                <div className="mx-auto w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                    {isChunkError ? (
                        <Sparkles className="w-8 h-8 text-[#FFE600]" />
                    ) : (
                        <AlertTriangle className="w-8 h-8 text-red-500" />
                    )}
                </div>

                <div className="space-y-2">
                    <h1 className="text-xl sm:text-2xl font-black text-white uppercase tracking-tight">
                        {isChunkError ? "تم تحديث المنصة بنسخة جديدة" : "حدث خطأ غير متوقع"}
                    </h1>
                    <p className="text-sm text-zinc-400 leading-relaxed">
                        {isChunkError
                            ? "تم نشر تحديثات جديدة للمنصة. يرجى تحديث الصفحة لتحميل النسخة الأخيرة فوراً والاستمتاع بكافة الميزات."
                            : "يرجى المحاولة مرة أخرى أو تحديث الصفحة."}
                    </p>
                    {error.message && !isChunkError && (
                        <p className="text-xs text-red-400/60 font-mono mt-4 p-3 rounded-xl bg-red-500/5 border border-red-500/10 text-left" dir="ltr">
                            {error.message}
                        </p>
                    )}
                </div>

                <button
                    onClick={handleRetry}
                    className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-[#FFE600] hover:bg-[#ffea33] text-black font-black text-sm uppercase tracking-wider transition-all shadow-[0_0_20px_rgba(255,230,0,0.2)] cursor-pointer"
                >
                    <RefreshCw className="w-4 h-4" />
                    {isChunkError ? "تحديث الصفحة الآن (Reload)" : "إعادة المحاولة (Try Again)"}
                </button>
            </div>
        </div>
    );
}
