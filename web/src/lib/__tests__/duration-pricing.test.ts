import {
  DURATION_SLIDER_SCHEDULE,
  computeDurationPlanPricing,
  formatDurationLabel,
} from "../duration-pricing";
import { computeCheckoutPricing, toCheckoutChargeEgp, toDisplayAmount } from "../saudi-pricing";

describe("1-12 month progressive duration pricing schedule", () => {
  it("computes exact multiples of 5 EGP for 50, 100, and 150 monthly bases with strictly increasing discounts", () => {
    const expectedPro = [150, 285, 405, 525, 645, 750, 855, 960, 1065, 1170, 1260, 1350];
    const expected100 = [100, 190, 270, 350, 430, 500, 570, 640, 710, 780, 840, 900];
    const expected50 = [50, 95, 135, 175, 215, 250, 285, 320, 355, 390, 420, 450];
    const expectedDays = [30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 365];

    let prevDiscount = -1;
    DURATION_SLIDER_SCHEDULE.forEach((entry, idx) => {
      const m = idx + 1;
      expect(entry.months).toBe(m);
      expect(entry.days).toBe(expectedDays[idx]);
      expect(entry.discountPct).toBeGreaterThan(prevDiscount);
      prevDiscount = entry.discountPct;

      const p150 = computeDurationPlanPricing(150, m);
      const p100 = computeDurationPlanPricing(100, m);
      const p50 = computeDurationPlanPricing(50, m);

      expect(p150.totalEgp).toBe(expectedPro[idx]);
      expect(p150.totalEgp % 5).toBe(0);
      expect(p100.totalEgp).toBe(expected100[idx]);
      expect(p100.totalEgp % 5).toBe(0);
      expect(p50.totalEgp).toBe(expected50[idx]);
      expect(p50.totalEgp % 5).toBe(0);
      expect(p150.days).toBe(expectedDays[idx]);
    });
  });

  it("matches backend ROUND_HALF_UP GCC SAR/AED/QAR display and EGP EasyKash invoice conversions", () => {
    const sarCases: Array<[number, number, number]> = [
      [285, 29, 370],
      [405, 41, 523],
      [525, 53, 676],
      [750, 75, 956],
      [1350, 135, 1721],
    ];
    for (const [egp, expectedSar, expectedCharge] of sarCases) {
      expect(toDisplayAmount(egp, true)).toBe(expectedSar);
      expect(toCheckoutChargeEgp(egp, true)).toBe(expectedCharge);
      expect(toDisplayAmount(egp, "tasi")).toBe(expectedSar);
      expect(toCheckoutChargeEgp(egp, "tasi")).toBe(expectedCharge);
    }

    const uaeCases: Array<[number, number, number]> = [
      [100, 10, 130],
      [150, 15, 195],
      [405, 41, 533],
    ];
    for (const [egp, expectedAed, expectedCharge] of uaeCases) {
      expect(toDisplayAmount(egp, "uae")).toBe(expectedAed);
      expect(toCheckoutChargeEgp(egp, "uae")).toBe(expectedCharge);
      const pricing = computeCheckoutPricing(egp, 0, "uae");
      expect(pricing.finalDisplay).toBe(expectedAed);
      expect(pricing.chargeEgp).toBe(expectedCharge);
    }

    const qatarCases: Array<[number, number, number]> = [
      [100, 10, 132],
      [150, 15, 197],
      [405, 41, 539],
    ];
    for (const [egp, expectedQar, expectedCharge] of qatarCases) {
      expect(toDisplayAmount(egp, "qatar")).toBe(expectedQar);
      expect(toCheckoutChargeEgp(egp, "qatar")).toBe(expectedCharge);
      const pricing = computeCheckoutPricing(egp, 0, "qatar");
      expect(pricing.finalDisplay).toBe(expectedQar);
      expect(pricing.chargeEgp).toBe(expectedCharge);
    }
  });

  it("formats clear Arabic and English labels for 1..12 months", () => {
    expect(formatDurationLabel(1, true)).toBe("شهر واحد");
    expect(formatDurationLabel(2, true)).toBe("شهران");
    expect(formatDurationLabel(3, true)).toBe("3 شهور");
    expect(formatDurationLabel(11, true)).toBe("11 شهراً");
    expect(formatDurationLabel(12, true)).toBe("سنة كاملة (12 شهراً)");

    expect(formatDurationLabel(1, false)).toBe("1 Month");
    expect(formatDurationLabel(6, false)).toBe("6 Months");
    expect(formatDurationLabel(12, false)).toBe("1 Year (12 Months)");
  });
});
