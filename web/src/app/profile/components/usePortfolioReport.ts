"use client";
import { useEffect, useState } from "react";
import { fetchPortfolioPerformance } from "@/lib/api";
import type { PortfolioPerformance } from "@/lib/portfolio-performance";
import type { PortfolioSnapshot } from "@/contexts/PortfolioContext";
export function usePortfolioReport(
  userId: string | null,
  snapshot: PortfolioSnapshot | null,
) {
  const fingerprint = JSON.stringify(
    (snapshot?.positions || [])
      .map((p) => [p.id, p.symbol, p.quantity, p.entry_price])
      .sort((a, b) => String(a[0]).localeCompare(String(b[0]))),
  );
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
      setLoading(false);
      setError(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    fetchPortfolioPerformance(controller.signal)
      .then((report) => {
        if (!controller.signal.aborted) setState({ key, report });
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
