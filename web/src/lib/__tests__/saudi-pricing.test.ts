import {
  EGP_PER_SAR,
  SAUDI_SAR_EXCHANGE_MAP,
  computeCheckoutPricing,
  lifetimeBreakevenMonths,
  toCheckoutChargeEgp,
  toDisplayAmount,
} from "../saudi-pricing";

describe("Saudi (TASI / SAR) pricing parity & EasyKash billing helpers", () => {
  test("preserves 20 SAR/mo anchor and exact Egyptian tier ratios across retail, founders, and B2B", () => {
    expect(SAUDI_SAR_EXCHANGE_MAP[200]).toBe(20);
    expect(toDisplayAmount(200, true)).toBe(20); // 1x monthly Pro
    expect(toDisplayAmount(1000, true)).toBe(100); // 5x 6-month (-17%)
    expect(toDisplayAmount(1800, true)).toBe(180); // 9x 1-year (-25%)
    expect(toDisplayAmount(2250, true)).toBe(225); // 11.25x Lifetime VIP

    // Founders / grandfathered rates
    expect(toDisplayAmount(50, true)).toBe(5);
    expect(toDisplayAmount(100, true)).toBe(10);
    expect(toDisplayAmount(500, true)).toBe(50);

    // B2B tiers
    expect(toDisplayAmount(1500, true)).toBe(150);
    expect(toDisplayAmount(2500, true)).toBe(250);

    // Egypt retains EGP amounts verbatim
    expect(toDisplayAmount(200, false)).toBe(200);
    expect(toDisplayAmount(1800, false)).toBe(1800);
  });

  test("converts SAR display amounts honestly to EasyKash EGP invoice totals", () => {
    expect(EGP_PER_SAR).toBe(12.75);
    expect(toCheckoutChargeEgp(200, true)).toBe(255); // 20 * 12.75
    expect(toCheckoutChargeEgp(1000, true)).toBe(1275); // 100 * 12.75
    expect(toCheckoutChargeEgp(1800, true)).toBe(2295); // 180 * 12.75
    expect(toCheckoutChargeEgp(2250, true)).toBe(2869); // Math.round(225 * 12.75)

    // Egypt bills exact EGP
    expect(toCheckoutChargeEgp(200, false)).toBe(200);
  });

  test("applies promo discounts consistently to both display SAR and EasyKash charge EGP", () => {
    const proWith15Pct = computeCheckoutPricing(200, 15, true);
    expect(proWith15Pct).toEqual({
      baseDisplay: 20,
      finalDisplay: 17,
      discountDisplay: 3,
      chargeEgp: 217, // 255 - round(255 * 0.15) = 255 - 38 = 217
    });

    const proEgyptWith15Pct = computeCheckoutPricing(200, 15, false);
    expect(proEgyptWith15Pct).toEqual({
      baseDisplay: 200,
      finalDisplay: 170,
      discountDisplay: 30,
      chargeEgp: 170,
    });
  });

  test("computes accurate Lifetime breakeven duration (< 1 year at 200 EGP/20 SAR monthly)", () => {
    expect(lifetimeBreakevenMonths(2250, 200)).toBe(11.3);
    expect(lifetimeBreakevenMonths(2250, 0)).toBe(11.3);
  });

  test("maps split plans (100 EGP -> 10 SAR -> 128 EGP) and full bundle tiers (150/750/1350 EGP)", () => {
    expect(SAUDI_SAR_EXCHANGE_MAP[100]).toBe(10);
    expect(SAUDI_SAR_EXCHANGE_MAP[150]).toBe(15);
    expect(SAUDI_SAR_EXCHANGE_MAP[750]).toBe(75);
    expect(SAUDI_SAR_EXCHANGE_MAP[1350]).toBe(135);

    expect(toDisplayAmount(100, true)).toBe(10);
    expect(toDisplayAmount(150, true)).toBe(15);
    expect(toDisplayAmount(750, true)).toBe(75);
    expect(toDisplayAmount(1350, true)).toBe(135);

    expect(toCheckoutChargeEgp(100, true)).toBe(128);
    expect(toCheckoutChargeEgp(150, true)).toBe(191);
    expect(toCheckoutChargeEgp(750, true)).toBe(956);
    expect(toCheckoutChargeEgp(1350, true)).toBe(1721);

    // Egypt retains exact EGP
    expect(toCheckoutChargeEgp(100, false)).toBe(100);
    expect(toCheckoutChargeEgp(150, false)).toBe(150);
  });
});
