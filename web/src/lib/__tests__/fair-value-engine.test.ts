import { computeFairValueReport } from "../market/fair-value";

describe("computeFairValueReport (3-Tier Fair Value Engine)", () => {
  it("computes Tier 1 Graham + Sector Multiples for profitable stocks with book value", () => {
    const fundamentals = [
      {
        symbol: "COMI",
        name: "Commercial International Bank",
        data: {
          eps: 20,
          bookValuePerShare: 70,
          peRatio: 5.9,
          pbRatio: 1.68,
          sector: "Finance",
          industry: "Regional Banks",
          isListed: true,
        },
      },
      {
        symbol: "CIEB",
        name: "Credit Agricole Egypt",
        data: {
          eps: 8,
          bookValuePerShare: 20,
          peRatio: 6.5,
          pbRatio: 1.6,
          sector: "Finance",
          industry: "Regional Banks",
          isListed: true,
        },
      },
    ];
    const indicators = [
      { symbol: "COMI", date: "2026-11-01", close: 118, change_pct: 1.2, rsi_14: 54 },
      { symbol: "CIEB", date: "2026-11-01", close: 52, change_pct: 0.5, rsi_14: 50 },
    ];

    const report = computeFairValueReport(fundamentals, indicators);
    expect(report.summary.totalEvaluated).toBe(2);
    expect(report.summary.fundamentalCoverageCount).toBe(2);

    const comi = report.stocks.find((s) => s.symbol === "COMI")!;
    expect(comi).toBeDefined();
    expect(comi.modelType).toBe("graham_fundamental");
    expect(comi.grahamValue).toBeCloseTo(Math.sqrt(22.5 * 20 * 70), 1);
    expect(comi.fairValue).toBeGreaterThan(comi.currentPrice);
    expect(comi.status).toBe("undervalued");
  });

  it("falls back to Tier 2B (P/B Multiple) when EPS is negative/null but BVPS is positive", () => {
    const fundamentals = [
      {
        symbol: "TMGH",
        data: {
          eps: null,
          bookValuePerShare: 45,
          pbRatio: 1.5,
          sector: "Finance",
          industry: "Real Estate Development",
          isListed: true,
        },
      },
    ];
    const indicators = [
      { symbol: "TMGH", date: "2026-11-01", close: 60, change_pct: -0.5, rsi_14: 48 },
    ];

    const report = computeFairValueReport(fundamentals, indicators);
    const tmgh = report.stocks[0];
    expect(tmgh.modelType).toBe("pb_multiple");
    expect(tmgh.bvps).toBe(45);
    expect(tmgh.fairValue).toBeGreaterThan(60);
  });

  it("falls back to Tier 3 (Quant VWAP + EMA200) when fundamentals are absent", () => {
    const fundamentals = [{ symbol: "SMLC", data: { isListed: true } }];
    const indicators = [
      {
        symbol: "SMLC",
        date: "2026-11-01",
        close: 2.0,
        ema_200: 2.6,
        vwap_20: 2.4,
        change_pct: 0,
      },
    ];

    const report = computeFairValueReport(fundamentals, indicators);
    const smlc = report.stocks[0];
    expect(smlc.modelType).toBe("quant_vwap");
    expect(smlc.fairValue).toBeCloseTo(0.6 * 2.6 + 0.4 * 2.4, 2);
    expect(smlc.status).toBe("undervalued");
  });
});
