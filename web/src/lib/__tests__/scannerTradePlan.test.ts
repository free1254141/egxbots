import { calculateScannerTradePlan, SCANNER_PROFILES, formatTelegramTradePlanSnippet } from "../scannerTradePlan";

describe("scannerTradePlan utility", () => {
  it("calculates accurate targets and stop loss for Volume Surge", () => {
    const entry = 100.0;
    const plan = calculateScannerTradePlan(entry, "volume_surge");

    expect(plan.entryPrice).toBe(100.0);
    expect(plan.target1).toBe(103.5); // +3.5%
    expect(plan.target1Pct).toBe(3.5);
    expect(plan.target2).toBe(106.0); // +6.0%
    expect(plan.target2Pct).toBe(6.0);
    expect(plan.stopLoss).toBe(98.0); // -2.0%
    expect(plan.stopLossPct).toBe(2.0);
    expect(plan.riskRewardRatio).toBeCloseTo(1.75, 1);
    expect(plan.maxHoldingSessions).toBe(4);
    expect(plan.recommendationTextAr).toContain("دخول عند 100.00 ج.م");
  });

  it("calculates accurate targets for Technical Breakouts", () => {
    const entry = 13.15;
    const plan = calculateScannerTradePlan(entry, "breakout");

    expect(plan.target1).toBe(Number((13.15 * 1.05).toFixed(2))); // +5.0%
    expect(plan.stopLoss).toBe(Number((13.15 * 0.975).toFixed(2))); // -2.5%
    expect(plan.riskRewardRatio).toBeCloseTo(2.0, 1);
  });

  it("calculates accurate targets for RSI Oversold", () => {
    const entry = 5.25;
    const plan = calculateScannerTradePlan(entry, "rsi_oversold");

    expect(plan.target1).toBe(Number((5.25 * 1.03).toFixed(2))); // +3.0%
    expect(plan.stopLoss).toBe(Number((5.25 * 0.98).toFixed(2))); // -2.0%
    expect(plan.maxHoldingSessions).toBe(3);
  });

  it("formats clean telegram snippet", () => {
    const snippet = formatTelegramTradePlanSnippet(20.0, "volume_surge");
    expect(snippet).toContain("🎯 <b>الهدف 1:</b> 20.70 ج.م (+3.5%)");
    expect(snippet).toContain("🛑 <b>الوقف:</b> 19.60 ج.م (-2%)");
  });
});
