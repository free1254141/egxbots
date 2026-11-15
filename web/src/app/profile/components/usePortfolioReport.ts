"use client";
import { useEffect, useState } from "react";
import { fetchPortfolioPerformance } from "@/lib/api";
import type { PortfolioPerformance } from "@/lib/portfolio-performance";
import type { PortfolioSnapshot } from "@/contexts/PortfolioContext";
const PORTFOLIO_PERF_CACHE_PREFIX = "egxbots_portfolio_perf_v1:";
const PORTFOLIO_PERF_CACHE_TTL_MS = 30 * 60 * 1000;

export function usePortfolioReport(
  userId: string | null,
  snapshot: PortfolioSnapshot | null,
) {
  const fingerprint = JSON.stringify({
    cash: snapshot?.cash_balance ?? null,
    positions: (snapshot?.positions || [])
      .map((p) => [p.id, p.symbol, p.quantity, p.entry_price])
      .sort((a, b) => String(a[0]).localeCompare(String(b[0]))),
  });
  const key = userId && snapshot ? `${userId}:${fingerprint}` : null;
  const [state, setState] = useState<{
    key: string;
    report: PortfolioPerformance;
  } | null>(null);
  const [loading, setLoading] = useState(false),
    [error, setError] = useState(false),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!key) {
      setState(null);
      setLoading(false);
      setError(false);
      return;
    }
    const cacheKey = `${PORTFOLIO_PERF_CACHE_PREFIX}${key}`;
    if (revision === 0 && typeof window !== "undefined") {
      try {
        const raw = window.sessionStorage.getItem(cacheKey);
        if (raw) {
          const parsed = JSON.parse(raw) as { ts: number; report: PortfolioPerformance };
          if (parsed?.ts && Date.now() - parsed.ts < PORTFOLIO_PERF_CACHE_TTL_MS && parsed.report) {
            setState({ key, report: parsed.report });
            setLoading(false);
            setError(false);
            return;
          }
        }
      } catch {
        // ignore storage errors
      }
    }
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    fetchPortfolioPerformance(controller.signal)
      .then((report) => {
        if (!controller.signal.aborted) {
          setState({ key, report });
          if (typeof window !== "undefined") {
            try {
              window.sessionStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), report }));
            } catch {
              // ignore storage quota errors
            }
          }
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [key, revision]);
  return {
    report: state?.key === key ? state.report : null,
    loading,
    error,
    refresh: () => setRevision((n) => n + 1),
  };
}
