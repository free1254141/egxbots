import {
  calculateScannerTradePlan,
  SCANNER_PROFILES,
  formatTelegramTradePlanSnippet,
  deriveTrackedSignalsFromHistory
} from "../scannerTradePlan";

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

  it("derives active and closed signals accurately from lastScan", () => {
    const mockLastScan = {
      timestamp: "2026-10-19T13:45:00.000Z",
      stage_results: {
        volume_surge: [
          { symbol: "MOIL", close: 0.67, change_pct: 1.51 }, // under 3.5% -> active
          { symbol: "POUL", close: 10.3, change_pct: 5.10 }, // over 3.5% -> target hit
        ],
        breakout: [
          { symbol: "NIPH", close: 296.0, change_pct: 17.58 }, // over 5.0% -> target hit
        ],
        rsi_oversold: [
          { symbol: "TYCN", close: 10.84, change_pct: 2.65 }, // under 3.0% -> active
        ],
      },
    };

    const derived = deriveTrackedSignalsFromHistory([], mockLastScan);
    expect(derived.activeSignals.length).toBe(2); // MOIL and TYCN
    expect(derived.closedSignals.length).toBe(2); // POUL and NIPH
    expect(derived.activeSignals.map((s) => s.symbol)).toEqual(["MOIL", "TYCN"]);
    expect(derived.closedSignals.map((s) => s.symbol)).toEqual(["POUL", "NIPH"]);
    expect(derived.kpis.total_active).toBe(2);
    expect(derived.kpis.total_closed).toBe(2);
    expect(derived.kpis.win_rate_pct).toBe(100);
  });
});
