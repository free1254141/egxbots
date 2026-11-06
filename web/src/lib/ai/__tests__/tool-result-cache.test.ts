import {
  buildToolResultCacheKey,
  cairoDateKey,
  clearToolResultMemoryCache,
  getCachedToolResult,
  isToolResultCacheable,
  setCachedToolResult,
  stableStringify,
} from "../tool-result-cache";

describe("tool result cache", () => {
  beforeEach(() => clearToolResultMemoryCache());

  it("builds the same key regardless of argument order", () => {
    const a = buildToolResultCacheKey("get_stock", { symbols: ["COMI"], limit: 5 });
    const b = buildToolResultCacheKey("get_stock", { limit: 5, symbols: ["COMI"] });
    expect(a).toBe(b);
  });

  it("separates different tools, different arguments and different days", () => {
    const base = buildToolResultCacheKey("get_stock", { symbols: ["COMI"] });
    expect(base).not.toBe(buildToolResultCacheKey("get_news", { symbols: ["COMI"] }));
    expect(base).not.toBe(buildToolResultCacheKey("get_stock", { symbols: ["ETEL"] }));
    expect(base).not.toBe(
      buildToolResultCacheKey("get_stock", { symbols: ["COMI"] }, new Date("2026-11-09T12:00:00Z"))
    );
  });

  it("keys on the Cairo trading day, not the UTC day", () => {
    // 22:30 UTC on Nov 6 is already Nov 7 in Cairo (UTC+2).
    expect(cairoDateKey(new Date("2026-11-06T22:30:00Z"))).toBe("2026-11-07");
    expect(cairoDateKey(new Date("2026-11-06T20:00:00Z"))).toBe("2026-11-06");
  });

  it("keeps the key stable for nested payloads", () => {
    expect(stableStringify({ b: [1, { d: 2, c: 3 }], a: null })).toBe(
      '{"a":null,"b":[1,{"c":3,"d":2}]}'
    );
  });

  it("only allows public, read-only tools", () => {
    for (const tool of [
      "get_stock",
      "get_market",
      "get_recommendations",
      "get_technical_scan",
      "get_news",
      "get_comparison",
      "get_fair_value",
      "get_sharia_cleanser",
    ]) {
      expect(isToolResultCacheable(tool)).toBe(true);
    }
    for (const tool of [
      "get_live_quote",
      "manage_portfolio",
      "rebalance_portfolio",
      "analyze_portfolio_risk",
      "enable_autonomous_recommendations",
    ]) {
      expect(isToolResultCacheable(tool)).toBe(false);
    }
  });

  it("round-trips through the in-memory layer without a database", async () => {
    const key = buildToolResultCacheKey("get_stock", { symbols: ["COMI"] });
    expect(await getCachedToolResult(key, null)).toBeNull();
    await setCachedToolResult(key, { status: "success", price: 100 }, null);
    expect(await getCachedToolResult(key, null)).toEqual({ status: "success", price: 100 });
  });
});
