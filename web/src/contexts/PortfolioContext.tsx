"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "./AuthContext";

export type PortfolioRow = {
  id: string;
  symbol: string;
  name: string | null;
  quantity: number | null;
  entry_price: number | null;
  last_price: number | null;
  market_value: number | null;
  cost_basis: number | null;
  profit_pct: number | null;
  profit_value: number | null;
  price_updated_at?: string | null;
  price_source?: "live" | "stock_prices" | "unavailable";
};

export type PortfolioSnapshot = {
  ok: boolean;
  positions: PortfolioRow[];
  cash_balance: number;
  totals: {
    positions_count: number;
    cost_basis: number | null;
    market_value: number | null;
    profit_value: number | null;
    profit_pct: number | null;
    equity: number | null;
  };
  market_symbols?: Array<{ symbol: string; name: string | null }>;
  portfolio_limit?: number | null;
  is_pro?: boolean;
};

type PortfolioContextValue = {
  snapshot: PortfolioSnapshot | null;
  loading: boolean;
  refresh: (force?: boolean) => Promise<void>;
};

const PortfolioContext = createContext<PortfolioContextValue | null>(null);
const PORTFOLIO_CACHE_PREFIX = "egxbots_portfolio_snapshot_v1:";
const PORTFOLIO_CACHE_TTL_MS = 15 * 60 * 1000;

export function PortfolioProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [stored, setStored] = useState<{
    owner: string;
    snapshot: PortfolioSnapshot;
  } | null>(null);
  const snapshot = stored && stored.owner === user?.id ? stored.snapshot : null;
  const generation = useRef(0);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(
    async (force = false) => {
      const version = ++generation.current;
      if (!user) {
        setStored(null);
        setLoading(false);
        return;
      }
      const cacheKey = `${PORTFOLIO_CACHE_PREFIX}${user.id}`;
      if (!force && typeof window !== "undefined") {
        try {
          const raw = window.sessionStorage.getItem(cacheKey);
          if (raw) {
            const parsed = JSON.parse(raw) as { ts: number; data: PortfolioSnapshot };
            if (parsed?.ts && Date.now() - parsed.ts < PORTFOLIO_CACHE_TTL_MS && parsed.data?.ok) {
              setStored({ owner: user.id, snapshot: parsed.data });
              setLoading(false);
              return;
            }
          }
        } catch {
          // ignore storage errors
        }
      }
      setLoading(true);
      try {
        const response = await fetch("/api/portfolio", force ? { cache: "no-store" } : undefined);
        if (response.ok) {
          const next = await response.json();
          if (generation.current === version) {
            setStored({ owner: user.id, snapshot: next });
            if (typeof window !== "undefined" && next?.ok) {
              try {
                window.sessionStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), data: next }));
              } catch {
                // ignore quota errors
              }
            }
          }
        }
      } finally {
        if (generation.current === version) setLoading(false);
      }
    },
    [user?.id],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const handleUpdated = () => {
      void refresh(true);
    };
    const handleStorage = (e: StorageEvent) => {
      if (
        e.key === "egx_entitlements_timestamp" ||
        e.key === "egx_pro_active"
      ) {
        void refresh(true);
      }
    };
    window.addEventListener("portfolio-updated", handleUpdated);
    window.addEventListener("egx:entitlements-updated", handleUpdated);
    window.addEventListener("storage", handleStorage);
    return () => {
      window.removeEventListener("portfolio-updated", handleUpdated);
      window.removeEventListener("egx:entitlements-updated", handleUpdated);
      window.removeEventListener("storage", handleStorage);
    };
  }, [refresh]);

  return (
    <PortfolioContext.Provider value={{ snapshot, loading, refresh }}>
      {children}
    </PortfolioContext.Provider>
  );
}

export function usePortfolio() {
  const context = useContext(PortfolioContext);
  if (!context)
    throw new Error("usePortfolio must be used inside PortfolioProvider");
  return context;
}
