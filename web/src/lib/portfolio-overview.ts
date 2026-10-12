import type { DailyPrice, PerformanceHolding } from "./portfolio-performance";

export type DailyHoldingChange = {
  symbol: string;
  value: number | null;
  change: number | null;
  changePct: number | null;
  sector: string | null;
};
export type PortfolioDailyOverview = {
  date: string | null;
  previousDate: string | null;
  change: number | null;
  changePct: number | null;
  benchmarkPct: number | null;
  complete: boolean;
  adjusted: boolean;
  holdings: DailyHoldingChange[];
};
const positive = (v: unknown): number | null =>
  v !== null &&
  v !== undefined &&
  v !== "" &&
  Number.isFinite(Number(v)) &&
  Number(v) > 0
    ? Number(v)
    : null;

/** Today's quantities on the same two market sessions, never an account-return claim. */
export function buildDailyOverview(
  positions: Array<PerformanceHolding & { sector?: string | null }>,
  histories: Record<string, DailyPrice[]>,
  benchmark: DailyPrice[],
): PortfolioDailyOverview {
  const sessions = benchmark
    .filter((p) => positive(p.close) !== null)
    .sort((a, b) => a.date.localeCompare(b.date));
  const latest = sessions.at(-1),
    previous = sessions.at(-2);
  let adjusted = true;
  const holdings = positions
    .filter((p) => p.status === "open" && positive(p.quantity) !== null)
    .map((p) => {
      const current =
        latest && histories[p.symbol]?.find((r) => r.date === latest.date);
      const prior =
        previous && histories[p.symbol]?.find((r) => r.date === previous.date);
      const raw = positive(current?.close),
        oldRaw = positive(prior?.close);
      const currentAdjusted = positive(current?.adjusted_close),
        priorAdjusted = positive(prior?.adjusted_close);
      const useAdjusted = currentAdjusted !== null && priorAdjusted !== null;
      if (!useAdjusted) adjusted = false;
      const ratio =
        raw !== null && oldRaw !== null
          ? useAdjusted
            ? currentAdjusted! / priorAdjusted!
            : raw / oldRaw
          : null;
      const value = raw !== null ? raw * Number(p.quantity) : null;
      // Express the return on the current quantities/current price basis after splits.
      const change =
        ratio !== null && ratio > 0 && value !== null
          ? value - value / ratio
          : null;
      return {
        symbol: p.symbol,
        sector: p.sector || null,
        value,
        change,
        changePct: ratio === null ? null : (ratio - 1) * 100,
      };
    });
  const complete =
    holdings.length > 0 && holdings.every((p) => p.change !== null);
  const change = complete ? holdings.reduce((n, p) => n + p.change!, 0) : null;
  const currentValue = complete
    ? holdings.reduce((n, p) => n + p.value!, 0)
    : null;
  const priorValue =
    currentValue !== null && change !== null ? currentValue - change : null;
  return {
    date: latest?.date || null,
    previousDate: previous?.date || null,
    holdings,
    complete,
    adjusted,
    change,
    changePct:
      priorValue && change !== null ? (change / priorValue) * 100 : null,
    benchmarkPct:
      latest && previous
        ? (Number(latest.close) / Number(previous.close) - 1) * 100
        : null,
  };
}

export function portfolioConcentration(
  holdings: Array<{
    symbol: string;
    value: number | null;
    sector?: string | null;
  }>,
  cash: number | null,
) {
  const complete =
    cash !== null &&
    Number.isFinite(cash) &&
    cash >= 0 &&
    holdings.every(
      (p) => p.value !== null && Number.isFinite(p.value) && p.value >= 0,
    );
  if (!complete)
    return {
      complete: false,
      stockValue: null,
      equity: null,
      cashPct: null,
      top: null,
      sectors: [] as Array<{ sector: string; value: number; pct: number }>,
    };
  const stockValue = holdings.reduce((n, p) => n + p.value!, 0),
    equity = stockValue + cash!;
  const sectors = new Map<string, number>();
  for (const p of holdings)
    sectors.set(
      p.sector || "unknown",
      (sectors.get(p.sector || "unknown") || 0) + p.value!,
    );
  const top = [...holdings].sort((a, b) => b.value! - a.value!)[0];
  return {
    complete: true,
    stockValue,
    equity,
    cashPct: equity > 0 ? (cash! / equity) * 100 : 0,
    top:
      top && equity > 0
        ? { symbol: top.symbol, pct: (top.value! / equity) * 100 }
        : null,
    sectors: [...sectors]
      .map(([sector, value]) => ({
        sector,
        value,
        pct: equity > 0 ? (value / equity) * 100 : 0,
      }))
      .sort((a, b) => b.value - a.value),
  };
}

/** Read-only parallel shock to shares, cash held constant. */
export function simulatePortfolioDrop(
  stockValue: number | null,
  cash: number | null,
  dropPct: number,
) {
  if (
    stockValue === null ||
    cash === null ||
    !Number.isFinite(stockValue) ||
    !Number.isFinite(cash) ||
    stockValue < 0 ||
    cash < 0 ||
    !Number.isFinite(dropPct) ||
    dropPct < 0 ||
    dropPct > 100
  )
    return null;
  const loss = (stockValue * dropPct) / 100;
  return {
    loss,
    remaining: stockValue - loss + cash,
    equity: stockValue + cash,
  };
}
