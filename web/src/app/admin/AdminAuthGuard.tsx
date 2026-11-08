"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Loader2 } from "lucide-react";
import { isAllowedAdminEmail, isLocalhost } from "@/lib/admin-auth-client";

export default function AdminAuthGuard({ children }: { children: React.ReactNode }) {
    const { user, loading } = useAuth();
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    // While determining auth or environment
    if (loading || !mounted) {
        return (
            <div className="min-h-screen bg-black flex items-center justify-center">
                <Loader2 className="w-10 h-10 text-indigo-500 animate-spin" />
            </div>
        );
    }

    const isLocal = isLocalhost();
    const isAllowed = isLocal || (user && isAllowedAdminEmail(user.email));

    // If not allowed, log unauthorized attempt silently and show 404 Not Found
    if (!isAllowed) {
        if (typeof window !== "undefined") {
            const hasLogged = sessionStorage.getItem("admin_blocked_logged");
            if (!hasLogged) {
                sessionStorage.setItem("admin_blocked_logged", "1");
                fetch("/api/admin-access-log", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        eventType: "unauthorized_attempt",
                        userEmail: user?.email || "anonymous_visitor",
                        userId: user?.id || null,
                    }),
                }).catch(() => {});
            }
        }

        // Render 404 page directly so /admin appears non-existent to outsiders
        return (
            <main className="min-h-screen bg-black text-zinc-100 flex items-center justify-center px-6">
                <div className="max-w-xl w-full text-center">
                    <div className="inline-flex items-center justify-center px-3 py-1 rounded-full bg-white/5 border border-white/10 text-[10px] font-black uppercase tracking-[0.25em] text-zinc-400">
                        404
                    </div>
                    <h1 className="mt-6 text-3xl md:text-4xl font-black tracking-tight text-white">
                        Page not found
                    </h1>
                    <p className="mt-3 text-sm text-zinc-400 leading-relaxed">
                        The page you&apos;re looking for doesn&apos;t exist or was moved.
                    </p>
                    <div className="mt-8 flex items-center justify-center gap-3">
                        <a
                            href="/"
                            className="px-5 py-3 rounded-2xl text-xs font-black uppercase tracking-wider bg-white text-black hover:bg-zinc-200 transition-colors"
                        >
                            Home
                        </a>
                    </div>
                </div>
            </main>
        );
    }

    return <>{children}</>;
}
