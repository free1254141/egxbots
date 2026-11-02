import { computeSingleStockFairValue } from "../market/fair-value";
import {
    executePriceTrapsTool,
    executeShariaCleanserTool,
    executeFairValueTool,
    executeRebalancePortfolioTool
} from "../ai/feature-tools";

describe("3-Tier Fair Value Engine & Feature Tools", () => {
    describe("computeSingleStockFairValue", () => {
        test("Tier 1: Graham Fundamental Formula when EPS > 0 and BV > 0", () => {
            const result = computeSingleStockFairValue({
                symbol: "SWDY",
                close: 40.0,
                fundRow: {
                    name_ar: "السويدي إليكتريك",
                    data: {
                        eps: 4.5,
                        bookValuePerShare: 20.0,
                        sector: "صناعي وهندسي",
                        industry: "Electrical Equipment",
                    },
                },
                fundData: {
                    eps: 4.5,
                    bookValuePerShare: 20.0,
                    sector: "صناعي وهندسي",
                },
                latestTech: {
                    ema_200: 38.0,
                    vwap_20: 39.5,
                },
            });

            expect(result.modelType).toBe("graham_fundamental");
            expect(result.fairValue).toBeGreaterThan(0);
            expect(result.formulaEquationAr).toContain("جراهام");
            expect(result.formulaSubstitutionAr).toContain("45");
            expect(result.formulaStepsAr[0]).toContain("4.5");
            expect(result.formulaStepsAr.length).toBeGreaterThan(0);
        });

        test("Tier 2: P/E Sector Multiple when EPS > 0 but BV <= 0", () => {
            const result = computeSingleStockFairValue({
                symbol: "TEST1",
                close: 10.0,
                fundRow: {
                    name_ar: "شركة تجريبية",
                    data: {
                        eps: 1.2,
                        bookValuePerShare: 0,
                        sector: "عقارات",
                    },
                },
                fundData: {
                    eps: 1.2,
                    bookValuePerShare: 0,
                    sector: "عقارات",
                },
            });

            expect(result.modelType).toBe("pe_multiple");
            expect(result.fairValue).toBeGreaterThan(0);
            expect(result.formulaEquationAr).toContain("P/E");
        });

        test("Tier 2: P/B Sector Multiple when EPS <= 0 but BV > 0", () => {
            const result = computeSingleStockFairValue({
                symbol: "TEST2",
                close: 5.0,
                fundRow: {
                    name_ar: "شركة أصول",
                    data: {
                        eps: -0.5,
                        bookValuePerShare: 8.0,
                        sector: "عقارات",
                    },
                },
                fundData: {
                    eps: -0.5,
                    bookValuePerShare: 8.0,
                    sector: "عقارات",
                },
            });

            expect(result.modelType).toBe("pb_multiple");
            expect(result.fairValue).toBeGreaterThan(0);
            expect(result.formulaEquationAr).toContain("P/B");
        });

        test("Tier 3: Quantitative VWAP + EMA200 when no fundamentals", () => {
            const result = computeSingleStockFairValue({
                symbol: "TEST3",
                close: 25.0,
                latestTech: {
                    ema_200: 22.0,
                    vwap_20: 24.0,
                },
            });

            expect(result.modelType).toBe("quant_vwap");
            expect(result.fairValue).toBeGreaterThan(0);
            expect(result.formulaEquationAr).toContain("VWAP");
        });
    });

    describe("executePriceTrapsTool - Pro Encryption & Masking", () => {
        const createMockDb = () => ({
            from: (table: string) => ({
                select: () => {
                    const chain: any = {
                        eq: () => chain,
                        limit: () => chain,
                        maybeSingle: async () => ({
                            data: {
                                payload: {
                                    asOf: "2026-11-01",
                                    totalBearTraps: 1,
                                    totalBullTraps: 1,
                                    bearTraps: [
                                        {
                                            symbol: "COMI",
                                            nameAr: "البنك التجاري الدولي",
                                            trapType: "BEAR_TRAP",
                                            close: 80.0,
                                            keyLevel: 79.0,
                                            wickPct: 3.2,
                                            conviction: 85,
                                        },
                                    ],
                                    bullTraps: [
                                        {
                                            symbol: "FWRY",
                                            nameAr: "فوري لتكنولوجيا البنوك",
                                            trapType: "BULL_TRAP",
                                            close: 6.2,
                                            keyLevel: 6.5,
                                            wickPct: 2.8,
                                            conviction: 75,
                                        },
                                    ],
                                },
                            },
                        }),
                    };
                    return chain;
                },
            }),
        });

        test("Free user (isPro=false): Symbols MUST be masked and encrypted", async () => {
            const result = await executePriceTrapsTool({ trap_type: "all" }, createMockDb(), false);
            expect(result.status).toBe("success");
            expect(result.is_pro).toBe(false);
            expect(result.access_tier).toBe("free");
            expect(result.total_bear_traps).toBe(1);
            expect(result.total_bull_traps).toBe(1);

            // Verify no real symbol is leaked in the traps array
            expect(result.bear_traps[0].symbol).toBe("🔒 [سهم محمي لمشتركي PRO]");
            expect(result.bear_traps[0].name_ar).toBe("🔒 [اشترك في PRO لإظهار كود السهم]");
            expect(result.bear_traps[0].is_locked).toBe(true);

            expect(result.bull_traps[0].symbol).toBe("🔒 [سهم محمي لمشتركي PRO]");
            expect(result.bull_traps[0].name_ar).toBe("🔒 [اشترك في PRO لإظهار كود السهم]");
            expect(result.bull_traps[0].is_locked).toBe(true);
        });

        test("Pro user (isPro=true): Symbols are completely unmasked", async () => {
            const result = await executePriceTrapsTool({ trap_type: "all" }, createMockDb(), true);
            expect(result.status).toBe("success");
            expect(result.is_pro).toBe(true);
            expect(result.access_tier).toBe("pro");

            // Verify real symbols are preserved
            expect(result.bear_traps[0].symbol).toBe("COMI");
            expect(result.bear_traps[0].name_ar).toBe("البنك التجاري الدولي");
            expect(result.bear_traps[0].is_locked).toBe(false);

            expect(result.bull_traps[0].symbol).toBe("FWRY");
            expect(result.bull_traps[0].name_ar).toBe("فوري لتكنولوجيا البنوك");
            expect(result.bull_traps[0].is_locked).toBe(false);
        });
    });

    describe("executeShariaCleanserTool", () => {
        const createShariaMockDb = () => ({
            from: (table: string) => ({
                select: () => {
                    const chain: any = {
                        eq: () => chain,
                        order: () => chain,
                        limit: async () => ({
                            data: [
                                {
                                    symbol: "ABUK",
                                    close: 60.0,
                                    data: {
                                        sector: "كيماويات وأسمدة",
                                        last_dividend: 4.5,
                                    },
                                },
                            ],
                        }),
                    };
                    return chain;
                },
            }),
        });

        test("Computes purification and zakat amounts accurately", async () => {
            const result = await executeShariaCleanserTool(
                {
                    symbol: "ABUK",
                    shares_count: 1000,
                    coupon_per_share: 5.0,
                },
                createShariaMockDb()
            );

            expect(result.status).toBe("success");
            expect(result.is_sharia_compliant).toBe(true);
            expect(result.purification_rate_pct).toBe(2.4); // From SECTOR_PURIFICATION_RATES
            expect(result.dividend_purification.total_dividend_egp).toBe(5000);
            expect(result.dividend_purification.purification_amount_egp).toBe(120); // 5000 * 2.4% = 120
            expect(result.dividend_purification.net_halal_dividend_egp).toBe(4880);
            expect(result.zakat_calculation.zakat_due_egp).toBe(1500); // 60,000 * 2.5% = 1500
        });
    });

    describe("executeFairValueTool", () => {
        const createFairValueDb = () => ({
            from: (table: string) => {
                const chain: any = {
                    select: () => chain,
                    eq: () => chain,
                    in: () => chain,
                    order: () => chain,
                    limit: async () => {
                        if (table === "stock_fundamentals") {
                            return {
                                data: [
                                    {
                                        symbol: "COMI",
                                        name: "Commercial Bank",
                                        name_ar: "البنك التجاري الدولي",
                                        data: { eps: 8.5, bookValuePerShare: 45.0, sector: "بنوك" },
                                    },
                                ],
                            };
                        }
                        if (table === "stock_technical_indicators") {
                            return {
                                data: [
                                    {
                                        symbol: "COMI",
                                        date: "2026-11-01",
                                        close: 80.0,
                                        change_pct: 1.2,
                                        volume: 500000,
                                        ema_50: 78.0,
                                        ema_200: 72.0,
                                        vwap_20: 79.0,
                                        rsi_14: 55.0,
                                    },
                                ],
                            };
                        }
                        return { data: [] };
                    },
                };
                return chain;
            },
        });

        test("Evaluates specific stocks and returns fair value with calculation steps", async () => {
            const result = await executeFairValueTool({ symbols: ["COMI"] }, createFairValueDb());
            expect(result.status).toBe("success");
            expect(result.mode).toBe("specific_stocks");
            expect(result.count).toBe(1);
            expect(result.stocks[0].symbol).toBe("COMI");
            expect(result.stocks[0].fair_value).toBeGreaterThan(0);
            expect(result.stocks[0].calculation_steps_ar.length).toBeGreaterThan(0);
        });
    });

    describe("executeRebalancePortfolioTool", () => {
        const createRebalanceDb = () => ({
            from: (table: string) => {
                const chain: any = {
                    select: () => chain,
                    eq: () => chain,
                    in: () => chain,
                    order: () => chain,
                    limit: async () => {
                        if (table === "positions") {
                            return {
                                data: [{ symbol: "COMI", quantity: 100, entry_price: 75.0, status: "open" }],
                            };
                        }
                        if (table === "stock_technical_indicators") {
                            return {
                                data: [
                                    { symbol: "COMI", date: "2026-11-01", close: 80.0, ema_50: 78.0, ema_200: 72.0 },
                                ],
                            };
                        }
                        if (table === "stock_scans_summary") {
                            return {
                                data: [{ symbol: "COMI", acc_score: 75, dist_score: 10, consecutive_dist_days: 0 }],
                            };
                        }
                        if (table === "stock_fundamentals") {
                            return {
                                data: [{ symbol: "COMI", data: { eps: 8.5, bookValuePerShare: 45.0 } }],
                            };
                        }
                        return { data: [] };
                    },
                };
                return chain;
            },
        });

        test("Rebalances user portfolio and returns quota notice", async () => {
            const result = await executeRebalancePortfolioTool({}, createRebalanceDb(), "user-123");
            expect(result.status).toBe("success");
            expect(result.total_positions_evaluated).toBe(1);
            expect(result.healthy_count).toBe(1);
            expect(result.dead_capital_count).toBe(0);
            expect(result.quota_notice).toContain("كوتا الذكاء الاصطناعي");
        });
    });
});
