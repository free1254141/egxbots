/**
 * Shared Saudi (TASI / SAR) pricing & EasyKash settlement conversion helpers.
 *
 * Saudi tiers keep a clean 20 SAR/month anchor and preserve the exact Egyptian
 * multi-period / B2B ratios (6m = 5x, 1y = 9x, lifetime = 11.25x, b2b = 5x/7.5x/12.5x).
 * Because EasyKash DirectPayV1 bills in EGP, Saudi checkout requests convert the
 * SAR price to EGP using EGP_PER_SAR so the customer's card is billed the honest
 * equivalent of the displayed SAR price.
 */

export const EGP_PER_SAR = 12.75;

/** Canonical EGP tier prices -> Saudi SAR display prices (20 SAR base = EGP / 10). */
export const SAUDI_SAR_EXCHANGE_MAP: Record<number, number> = {
  50: 5,
  83: 8,
  100: 10,
  200: 20,
  500: 50,
  1000: 100,
  1500: 150,
  1800: 180,
  1850: 185,
  2250: 225,
  2500: 250,
  25000: 2500,
  40000: 4000,
};

/** Convert an internal EGP price to the active market's display currency (SAR for TASI, EGP for EGX). */
export function toDisplayAmount(amountEgp: number, isSaudi: boolean): number {
  if (!isSaudi) return amountEgp;
  if (!Number.isFinite(amountEgp) || amountEgp <= 0) return 0;
  const rounded = Math.round(amountEgp);
  if (SAUDI_SAR_EXCHANGE_MAP[rounded] !== undefined) {
    return SAUDI_SAR_EXCHANGE_MAP[rounded];
  }
  return Math.max(1, Math.round(amountEgp / 10));
}

/** Compute the base EasyKash EGP invoice amount corresponding to the displayed price. */
export function toCheckoutChargeEgp(baseEgp: number, isSaudi: boolean): number {
  if (!Number.isFinite(baseEgp) || baseEgp <= 0) return 0;
  if (!isSaudi) return Math.round(baseEgp);
  const sarAmount = toDisplayAmount(baseEgp, true);
  return Math.round(sarAmount * EGP_PER_SAR);
}

/**
 * Compute consistent display & EasyKash billing amounts with an optional promo percent.
 * Mirrors the backend EasyKash promo calculation (percent discount clamped to 20 EGP min).
 */
export function computeCheckoutPricing(
  baseEgp: number,
  discountPercent: number,
  isSaudi: boolean,
): {
  baseDisplay: number;
  finalDisplay: number;
  discountDisplay: number;
  chargeEgp: number;
} {
  const baseDisplay = toDisplayAmount(baseEgp, isSaudi);
  const chargeBaseEgp = toCheckoutChargeEgp(baseEgp, isSaudi);
  if (!Number.isFinite(discountPercent) || discountPercent <= 0) {
    return {
      baseDisplay,
      finalDisplay: baseDisplay,
      discountDisplay: 0,
      chargeEgp: chargeBaseEgp,
    };
  }
  const discountChargeEgp = Math.min(
    Math.max(0, chargeBaseEgp - 20),
    Math.round((chargeBaseEgp * discountPercent) / 100),
  );
  const chargeEgp = Math.max(20, chargeBaseEgp - discountChargeEgp);
  const finalDisplay = isSaudi
    ? Math.max(2, Math.round(chargeEgp / EGP_PER_SAR))
    : chargeEgp;
  return {
    baseDisplay,
    finalDisplay,
    discountDisplay: Math.max(0, baseDisplay - finalDisplay),
    chargeEgp,
  };
}

/** Compute Lifetime breakeven duration in months relative to monthly Pro (e.g. 2250/200 = 11.3). */
export function lifetimeBreakevenMonths(lifetimeEgp: number, monthlyEgp: number): number {
  const safeMonthly = monthlyEgp > 0 ? monthlyEgp : 200;
  return Math.round((lifetimeEgp / safeMonthly) * 10) / 10;
}
