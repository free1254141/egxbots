"use client";

import { useEffect } from "react";
import { RefreshCw, Sparkles } from "lucide-react";

export default function GlobalError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        console.error("Global application error:", error);
        const msg = error?.message || "";
        if (
            error?.name === "ChunkLoadError" ||
            msg.includes("Loading chunk") ||
            msg.includes("Failed to fetch dynamically imported module")
        ) {
            const key = `chunk_global_reload_${typeof window !== "undefined" ? window.location.pathname : ""}`;
            if (typeof window !== "undefined" && !sessionStorage.getItem(key)) {
                sessionStorage.setItem(key, "1");
                window.location.reload();
            }
        }
    }, [error]);

    const handleReload = () => {
        if (typeof window !== "undefined") {
            window.location.reload();
        } else {
            reset();
        }
    };

    return (
        <html lang="ar" dir="rtl">
            <body className="bg-zinc-950 text-white min-h-screen flex items-center justify-center p-6 font-sans">
                <div className="max-w-md w-full text-center space-y-6 p-8 rounded-2xl bg-zinc-900/80 border border-zinc-800 shadow-2xl">
                    <div className="mx-auto w-16 h-16 rounded-2xl bg-[#FFE600]/10 border border-[#FFE600]/20 flex items-center justify-center">
                        <Sparkles className="w-8 h-8 text-[#FFE600]" />
                    </div>

                    <div className="space-y-2">
                        <h1 className="text-xl sm:text-2xl font-black uppercase tracking-tight text-white">
                            تحديث متاح للمنصة
                        </h1>
                        <p className="text-sm text-zinc-400 leading-relaxed">
                            تم تحديث ملفات المنصة بنسخة أحدث. اضغط على الزر أدناه لتحديث الصفحة فوراً.
                        </p>
                    </div>

                    <button
                        onClick={handleReload}
                        className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-[#FFE600] hover:bg-[#ffea33] text-black font-black text-sm uppercase tracking-wider transition-all cursor-pointer shadow-[0_0_20px_rgba(255,230,0,0.2)]"
                    >
                        <RefreshCw className="w-4 h-4" />
                        تحديث الصفحة الآن (Refresh)
                    </button>
                </div>
            </body>
        </html>
    );
}
