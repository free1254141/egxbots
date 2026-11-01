import { calculateStockCompositeScore } from "../stock-scoring";

describe("EGX Stock Composite Deal Scoring Engine", () => {
    test("calculates high score (Grade A+) for strong bullish stock with high KING AI and accumulation", () => {
        const strongStock = {
            symbol: "AFMC",
            close: 124.50,
            ema_50: 110.0,
            ema_200: 95.0,
            rsi_14: 55.0,
            macd: 1.5,
            macd_signal: 1.0,
            macd_hist: 0.5,
            king_ai_score: 0.68,
            pe_ratio: 7.5,
            eps: 4.20,
            accumulation_score: 85,
            consecutive_acc_days: 3,
            relative_volume: 2.5,
            is_sharia_compliant: true,
        };

        const result = calculateStockCompositeScore(strongStock);
        expect(result.totalScore).toBeGreaterThanOrEqual(80);
        expect(result.grade).toBe("A+");
        expect(result.badgeColor).toBe("emerald");
        expect(result.verdictLabel).toContain("ممتازة");
        expect(result.breakdown.technicalMomentum.score).toBe(30);
        expect(result.breakdown.kingAiConfidence.score).toBe(25);
        expect(result.breakdown.shariaAndLiquidity.score).toBe(10);
    });

    test("calculates neutral / cautious score for stock under EMAs with negative MACD and lower KING score", () => {
        const weakStock = {
            symbol: "DTRR",
            close: 15.20,
            ema_50: 22.0,
            ema_200: 25.0,
            rsi_14: 32.0,
            macd: -2.5,
            macd_signal: -1.8,
            macd_hist: -0.7,
            king_ai_score: 0.38,
            pe_ratio: 28.0,
            eps: -0.50,
            accumulation_score: 20,
            consecutive_acc_days: 0,
            relative_volume: 0.6,
            is_sharia_compliant: false,
        };

        const result = calculateStockCompositeScore(weakStock);
        expect(result.totalScore).toBeLessThan(50);
        expect(["C", "D"]).toContain(result.grade);
        expect(result.badgeColor).toBe("rose");
        expect(result.breakdown.technicalMomentum.score).toBeLessThanOrEqual(15);
    });

    test("handles missing / partial indicators gracefully without throwing NaN or crashing", () => {
        const minimalStock = {
            symbol: "UNKNOWN",
        };

        const result = calculateStockCompositeScore(minimalStock);
        expect(result.totalScore).toBeGreaterThanOrEqual(0);
        expect(result.totalScore).toBeLessThanOrEqual(100);
        expect(Number.isFinite(result.totalScore)).toBe(true);
        expect(result.summaryArabic).toBeTruthy();
    });
});
