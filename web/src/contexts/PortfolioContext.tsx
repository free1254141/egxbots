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
      setLoading(true);
      try {
        const response = await fetch("/api/portfolio", { cache: "no-store" });
        if (response.ok) {
          const next = await response.json();
          if (generation.current === version)
            setStored({ owner: user.id, snapshot: next });
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
