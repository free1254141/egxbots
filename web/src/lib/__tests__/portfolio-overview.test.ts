import {
  buildDailyOverview,
  portfolioConcentration,
  simulatePortfolioDrop,
} from "../portfolio-overview";
const positions = [
  {
    id: "1",
    symbol: "COMI",
    quantity: 10,
    entry_price: 5,
    status: "open",
    sector: "Banks",
  },
];
const benchmark = [
  { date: "2026-10-07", close: 100 },
  { date: "2026-10-08", close: 101 },
];
it("compares the same two dates, excludes future prices, and weights actual quantities", () => {
  const r = buildDailyOverview(
    positions,
    {
      COMI: [
        { date: "2026-10-07", close: 10 },
        { date: "2026-10-08", close: 11 },
        { date: "2026-10-09", close: 999 },
      ],
    },
    benchmark,
  );
  expect(r.change).toBeCloseTo(10);
  expect(r.changePct).toBeCloseTo(10);
  expect(r.benchmarkPct).toBeCloseTo(1);
  expect(r.date).toBe("2026-10-08");
});
it("never invents zero change when a matching session is missing", () => {
  const r = buildDailyOverview(
    positions,
    { COMI: [{ date: "2026-10-08", close: 11 }] },
    benchmark,
  );
  expect(r.complete).toBe(false);
  expect(r.change).toBeNull();
  expect(r.changePct).toBeNull();
});
it("avoids treating a documented split as a daily loss", () => {
  const r = buildDailyOverview(
    positions,
    {
      COMI: [
        { date: "2026-10-07", close: 20, adjusted_close: 10 },
        { date: "2026-10-08", close: 10, adjusted_close: 10 },
      ],
    },
    benchmark,
  );
  expect(r.change).toBe(0);
  expect(r.adjusted).toBe(true);
});
it("includes cash in the denominator and keeps unknown sectors visible", () => {
  const r = portfolioConcentration(
    [
      { symbol: "COMI", value: 600, sector: "Banks" },
      { symbol: "SWDY", value: 200, sector: null },
    ],
    200,
  );
  expect(r.top).toEqual({ symbol: "COMI", pct: 60 });
  expect(r.cashPct).toBe(20);
  expect(r.sectors.find((s) => s.sector === "unknown")?.pct).toBe(20);
});
it("fails closed on missing valuation and cannot shock cash or mutate holdings", () => {
  expect(
    portfolioConcentration([{ symbol: "COMI", value: null }], 200).complete,
  ).toBe(false);
  expect(simulatePortfolioDrop(800, 200, 10)).toEqual({
    loss: 80,
    remaining: 920,
    equity: 1000,
  });
  expect(simulatePortfolioDrop(null, 200, 10)).toBeNull();
  expect(simulatePortfolioDrop(800, 200, 101)).toBeNull();
});
