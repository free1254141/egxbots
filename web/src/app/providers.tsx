"use client";

import type { ReactNode } from "react";
import { AuthProvider } from "@/contexts/AuthContext";
import { LanguageProvider } from "@/contexts/LanguageContext";
import { MarketProvider } from "@/contexts/MarketContext";
import { WatchlistProvider } from "@/contexts/WatchlistContext";
import { AppStateProvider } from "@/contexts/AppStateContext";
import { AIScannerProvider } from "@/contexts/AIScannerContext";
import { TechnicalScannerProvider } from "@/contexts/TechnicalScannerContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { NotificationProvider } from "@/contexts/NotificationContext";
import { ChatProvider } from "@/contexts/ChatContext";
import { PortfolioProvider } from "@/contexts/PortfolioContext";
import { TelegramProProvider } from "@/contexts/TelegramProContext";
import { AffiliateProvider } from "@/contexts/AffiliateContext";
import { SupportChatProvider } from "@/contexts/SupportChatContext";
import UserActivityTracker from "@/components/UserActivityTracker";

if (typeof window !== "undefined") {
  // Proactive ChunkLoadError auto-recovery (handles deployment skew / stale client chunks)
  const handleChunkError = (err: any) => {
    const msg = err?.message || String(err || '');
    const isChunk =
      err?.name === 'ChunkLoadError' ||
      msg.includes('Loading chunk') ||
      msg.includes('ChunkLoadError') ||
      msg.includes('Failed to fetch dynamically imported module');

    if (isChunk) {
      const key = `chunk_retry_${window.location.pathname}`;
      const hasRetried = sessionStorage.getItem(key);
      if (!hasRetried) {
        sessionStorage.setItem(key, Date.now().toString());
        window.location.reload();
      }
    }
  };

  window.addEventListener('error', (e) => handleChunkError(e.error || e));
  window.addEventListener('unhandledrejection', (e) => handleChunkError(e.reason));

  const resolveActiveMarketHeader = (): "egx" | "tasi" => {
    try {
      const param = new URLSearchParams(window.location.search).get("market")?.trim().toLowerCase();
      if (param === "tasi" || param === "tadawul" || param === "saudi") return "tasi";
      if (param === "egx" || param === "egypt") return "egx";
    } catch {
      // Ignore URL parsing errors
    }
    try {
      return localStorage.getItem("egxbots_market") === "tasi" ? "tasi" : "egx";
    } catch {
      return "egx";
    }
  };

  const originalFetch = window.fetch;
  window.fetch = async (input, init) => {
    let url = "";
    if (typeof input === "string") {
      url = input;
    } else if (input instanceof URL) {
      url = input.toString();
    } else if (input && typeof input === "object" && "url" in input) {
      url = (input as any).url || "";
    }

    if (
      url.includes("ngrok-free.app") ||
      url.startsWith("/") ||
      url.includes("/api/") ||
      url.startsWith("http://localhost") ||
      url.startsWith("http://127.0.0.1")
    ) {
      const isRequestInput = typeof Request !== "undefined" && input instanceof Request;
      const newInit = { ...init };
      const headers = new Headers(
        newInit.headers || (isRequestInput ? input.headers : undefined)
      );
      headers.set("ngrok-skip-browser-warning", "true");
      if (!headers.has("x-egxbots-market")) {
        headers.set("x-egxbots-market", resolveActiveMarketHeader());
      }
      newInit.headers = headers;

      if (isRequestInput) {
        const clonedRequest = new Request(input, {
          headers: newInit.headers,
        });
        return originalFetch(clonedRequest, newInit);
      }

      return originalFetch(input, newInit);
    }
    return originalFetch(input, init);
  };
}

export default function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>
        <UserActivityTracker />
        <TelegramProProvider>
          <AffiliateProvider>
            <LanguageProvider>
            <MarketProvider>
            <NotificationProvider>
              <PortfolioProvider>
               <WatchlistProvider>
                <AppStateProvider>
                  <AIScannerProvider>
                    <TechnicalScannerProvider>
                      <ChatProvider>
                        <SupportChatProvider>
                          {children}
                        </SupportChatProvider>
                      </ChatProvider>
                    </TechnicalScannerProvider>
                  </AIScannerProvider>
                </AppStateProvider>
               </WatchlistProvider>
              </PortfolioProvider>
            </NotificationProvider>
            </MarketProvider>
          </LanguageProvider>
          </AffiliateProvider>
        </TelegramProProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
