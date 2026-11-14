"use client";

import React, {
  Suspense,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useSearchParams } from "next/navigation";
import { useLanguage } from "@/contexts/LanguageContext";

export type MarketMode = "egx" | "tasi";

export const MARKET_STORAGE_KEY = "egxbots_market";
export const MARKET_COOKIE_NAME = "egxbots_market";
export const MARKET_CHANGE_EVENT = "egxbots:market-change";

export interface MarketContextValue {
  market: MarketMode;
  setMarket: (m: MarketMode) => void;
  toggleMarket: () => void;
  isSaudi: boolean;
  country: "Egypt" | "Saudi Arabia";
  exchange: "EGX" | "TADAWUL";
  currencyLabel: string;
  currencyCode: "EGP" | "SAR";
  indexLabel: "EGX30" | "TASI";
}

const DEFAULT_MARKET_CONTEXT: MarketContextValue = {
  market: "egx",
  setMarket: () => {},
  toggleMarket: () => {},
  isSaudi: false,
  country: "Egypt",
  exchange: "EGX",
  currencyLabel: "ج.م",
  currencyCode: "EGP",
  indexLabel: "EGX30",
};

const MarketContext = createContext<MarketContextValue | undefined>(undefined);

const SAUDI_VALUES = new Set(["tasi", "tadawul", "saudi", "saudi arabia", "ksa", "sa"]);
const EGX_VALUES = new Set(["egx", "egypt", "eg"]);

function normalizeMarket(value: string | null | undefined): MarketMode | null {
  if (!value) return null;
  const clean = value.trim().toLowerCase();
  if (SAUDI_VALUES.has(clean)) return "tasi";
  if (EGX_VALUES.has(clean)) return "egx";
  return null;
}

function readMarketFromSearch(search: string): MarketMode | null {
  try {
    const params = new URLSearchParams(search);
    return normalizeMarket(params.get("market"));
  } catch {
    return null;
  }
}

function readMarketFromStorage(): MarketMode | null {
  if (typeof window === "undefined") return null;
  try {
    return normalizeMarket(window.localStorage.getItem(MARKET_STORAGE_KEY));
  } catch {
    return null;
  }
}

function readMarketFromCookie(): MarketMode | null {
  if (typeof document === "undefined") return null;
  try {
    const parts = document.cookie.split(";");
    for (const part of parts) {
      const idx = part.indexOf("=");
      if (idx === -1) continue;
      const name = part.slice(0, idx).trim();
      if (name === MARKET_COOKIE_NAME) {
        const val = decodeURIComponent(part.slice(idx + 1).trim());
        return normalizeMarket(val);
      }
    }
  } catch {
    return null;
  }
  return null;
}

function persistMarket(next: MarketMode): void {
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(MARKET_STORAGE_KEY, next);
    } catch {
      // Storage may be unavailable in restricted contexts
    }
  }
  if (typeof document !== "undefined") {
    try {
      document.cookie = `${MARKET_COOKIE_NAME}=${next}; path=/; max-age=31536000; SameSite=Lax`;
    } catch {
      // Cookie write may be blocked
    }
  }
}

function useOptionalLanguage(): "ar" | "en" {
  try {
    return useLanguage().language;
  } catch {
    if (typeof document !== "undefined" && document.documentElement.lang === "en") {
      return "en";
    }
    return "ar";
  }
}

function MarketSearchParamsSync({
  onMarketParam,
}: {
  onMarketParam: (market: MarketMode) => void;
}) {
  const searchParams = useSearchParams();
  const marketParam = searchParams?.get("market") ?? null;

  useEffect(() => {
    const normalized = normalizeMarket(marketParam);
    if (normalized) {
      onMarketParam(normalized);
    }
  }, [marketParam, onMarketParam]);

  return null;
}

/** Provides active market state (`egx` | `tasi`) synced across state, storage, cookie, and URL. */
export function MarketProvider({ children }: { children: ReactNode }) {
  const language = useOptionalLanguage();
  const [market, setMarketState] = useState<MarketMode>("egx");
  const marketRef = useRef<MarketMode>("egx");

  const commitMarket = useCallback(
    (next: MarketMode, options: { syncUrl?: boolean; forceDispatch?: boolean } = {}) => {
      const normalized: MarketMode = next === "tasi" ? "tasi" : "egx";
      const changed = marketRef.current !== normalized;
      marketRef.current = normalized;
      setMarketState(normalized);
      persistMarket(normalized);

      if (typeof window === "undefined") return;

      if (options.syncUrl !== false) {
        try {
          const url = new URL(window.location.href);
          if (url.searchParams.has("market")) {
            url.searchParams.set("market", normalized);
            window.history.replaceState(window.history.state, "", url.toString());
          }
        } catch {
          // Ignore URL sync failures
        }
      }

      if (options.forceDispatch || changed) {
        window.dispatchEvent(
          new CustomEvent(MARKET_CHANGE_EVENT, { detail: { market: normalized } })
        );
      }
    },
    []
  );

  const setMarket = useCallback(
    (next: MarketMode) => commitMarket(next, { syncUrl: true, forceDispatch: true }),
    [commitMarket]
  );

  const toggleMarket = useCallback(() => {
    setMarket(marketRef.current === "tasi" ? "egx" : "tasi");
  }, [setMarket]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const resolved =
      readMarketFromSearch(window.location.search) ??
      readMarketFromStorage() ??
      readMarketFromCookie() ??
      "egx";

    if (resolved !== marketRef.current) {
      marketRef.current = resolved;
      setMarketState(resolved);
    }
    persistMarket(resolved);

    const handleStorage = (e: StorageEvent) => {
      if (e.key !== MARKET_STORAGE_KEY) return;
      const next = normalizeMarket(e.newValue);
      if (next && next !== marketRef.current) {
        marketRef.current = next;
        setMarketState(next);
        persistMarket(next);
      }
    };

    const handleMarketEvent = (e: Event) => {
      const detailMarket = normalizeMarket(
        (e as CustomEvent<{ market?: string }>).detail?.market
      );
      if (detailMarket && detailMarket !== marketRef.current) {
        marketRef.current = detailMarket;
        setMarketState(detailMarket);
        persistMarket(detailMarket);
      }
    };

    window.addEventListener("storage", handleStorage);
    window.addEventListener(MARKET_CHANGE_EVENT, handleMarketEvent);
    return () => {
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener(MARKET_CHANGE_EVENT, handleMarketEvent);
    };
  }, []);

  const handleParamMarket = useCallback(
    (paramMarket: MarketMode) => commitMarket(paramMarket, { syncUrl: false, forceDispatch: false }),
    [commitMarket]
  );

  const value = useMemo<MarketContextValue>(() => {
    const isSaudi = market === "tasi";
    const isArabic = language === "ar";
    return {
      market,
      setMarket,
      toggleMarket,
      isSaudi,
      country: isSaudi ? "Saudi Arabia" : "Egypt",
      exchange: isSaudi ? "TADAWUL" : "EGX",
      currencyLabel: isSaudi ? (isArabic ? "ر.س" : "SAR") : isArabic ? "ج.م" : "EGP",
      currencyCode: isSaudi ? "SAR" : "EGP",
      indexLabel: isSaudi ? "TASI" : "EGX30",
    };
  }, [language, market, setMarket, toggleMarket]);

  return (
    <MarketContext.Provider value={value}>
      <Suspense fallback={null}>
        <MarketSearchParamsSync onMarketParam={handleParamMarket} />
      </Suspense>
      {children}
    </MarketContext.Provider>
  );
}

/** Reads the active market context, falling back to EGX outside a provider. */
export function useMarket(): MarketContextValue {
  const context = useContext(MarketContext);
  return context ?? DEFAULT_MARKET_CONTEXT;
}
