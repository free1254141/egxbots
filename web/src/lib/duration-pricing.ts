/**
 * Canonical 1-12 month progressive duration discount helpers for standalone
 * ('chat_only', 'vip_only') and Full Bundle ('pro') plans.
 *
 * Mirrors api/payment_common.py DURATION_SLIDER_SCHEDULE identically so the UI,
 * Saudi SAR display conversion, and EasyKash backend order amounts always match.
 */

export interface DurationScheduleEntry {
  readonly months: number;
  readonly days: number;
  readonly billedMonths: number;
  readonly discountPct: number;
}

export const DURATION_SLIDER_SCHEDULE: readonly DurationScheduleEntry[] = [
  { months: 1, days: 30, billedMonths: 1.0, discountPct: 0 },
  { months: 2, days: 60, billedMonths: 1.9, discountPct: 5 },
  { months: 3, days: 90, billedMonths: 2.7, discountPct: 10 },
  { months: 4, days: 120, billedMonths: 3.5, discountPct: 13 },
  { months: 5, days: 150, billedMonths: 4.3, discountPct: 14 },
  { months: 6, days: 180, billedMonths: 5.0, discountPct: 17 },
  { months: 7, days: 210, billedMonths: 5.7, discountPct: 19 },
  { months: 8, days: 240, billedMonths: 6.4, discountPct: 20 },
  { months: 9, days: 270, billedMonths: 7.1, discountPct: 21 },
  { months: 10, days: 300, billedMonths: 7.8, discountPct: 22 },
  { months: 11, days: 330, billedMonths: 8.4, discountPct: 24 },
  { months: 12, days: 365, billedMonths: 9.0, discountPct: 25 },
] as const;

export const DURATION_SLIDER_PLANS = new Set(["pro", "chat_only", "vip_only"]);

export interface ComputedDurationPricing {
  months: number;
  days: number;
  discountPct: number;
  undiscountedEgp: number;
  totalEgp: number;
  savingsEgp: number;
  effectiveMonthlyEgp: number;
}

/** Resolve duration entry clamped cleanly to 1..12 months. */
export function getDurationScheduleEntry(months: number): DurationScheduleEntry {
  const safeMonths = Math.min(12, Math.max(1, Math.round(Number(months) || 1)));
  return DURATION_SLIDER_SCHEDULE[safeMonths - 1] ?? DURATION_SLIDER_SCHEDULE[0];
}

/**
 * Compute progressive duration pricing from a 1-month EGP base.
 * Uses integer tenths (`Math.round(billedMonths * 10)`) to avoid IEEE-754 drift.
 */
export function computeDurationPlanPricing(
  monthlyBaseEgp: number,
  months: number,
): ComputedDurationPricing {
  const entry = getDurationScheduleEntry(months);
  const safeBase = Math.max(0, Math.round(Number(monthlyBaseEgp) || 0));
  const undiscountedEgp = safeBase * entry.months;
  const tenths = Math.round(entry.billedMonths * 10);
  const totalEgp = Math.round((safeBase * tenths) / 10);
  const savingsEgp = Math.max(0, undiscountedEgp - totalEgp);
  const effectiveMonthlyEgp = Math.round(totalEgp / entry.months);

  return {
    months: entry.months,
    days: entry.days,
    discountPct: entry.discountPct,
    undiscountedEgp,
    totalEgp,
    savingsEgp,
    effectiveMonthlyEgp,
  };
}

/** Format human-readable bilingual duration labels for 1..12 months. */
export function formatDurationLabel(months: number, isAr: boolean): string {
  const m = Math.min(12, Math.max(1, Math.round(Number(months) || 1)));
  if (!isAr) {
    if (m === 1) return "1 Month";
    if (m === 12) return "1 Year (12 Months)";
    return `${m} Months`;
  }
  if (m === 1) return "شهر واحد";
  if (m === 2) return "شهران";
  if (m === 12) return "سنة كاملة (12 شهراً)";
  if (m === 11) return "11 شهراً";
  return `${m} شهور`;
}
