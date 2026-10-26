/**
 * plan-gate.ts — centralized plan tier + feature gating for the frontend.
 *
 * Mirrors api/plan_limits.py. Single source of truth for the two tiers and the
 * PASTYMENTS_ENABLED master flag. When payments are disabled (default) the
 * platform is FREE-UNLIMITED (no signal delay, no message cap, no stock cap);
 * the site stays completely free until the operator flips the env flag.
 */

export interface PlanLimits {
  name: string;
  signal_delay_days: number;
  chat_messages_daily: number;
  chat_messages_per_month: number;
  portfolio_stocks: number;
  price_egp: number;
  billing: "enabled" | "disabled";
}

export function paymentsEnabled(): boolean {
  // Client bundles only receive NEXT_PUBLIC_* values. Keep the server
  // fallback so API routes and local development use the same policy.
  const v = (process.env.NEXT_PUBLIC_PAYMENTS_ENABLED || process.env.PAYMENTS_ENABLED || "false").trim().toLowerCase();
  return !["0", "false", "no", "off", ""].includes(v);
}

const FREE: PlanLimits = {
  name: "free",
  signal_delay_days: Number(process.env.FREE_SIGNAL_DELAY_DAYS || "15"),
  chat_messages_daily: Number(process.env.FREE_CHAT_DAILY_MESSAGES || "5"),
  chat_messages_per_month: Number(process.env.FREE_CHAT_MESSAGES || "150"),
  portfolio_stocks: Number(process.env.FREE_PORTFOLIO_STOCKS || "5"),
  price_egp: 0,
  billing: "enabled",
};

const PRO: PlanLimits = {
  name: "pro",
  signal_delay_days: 0,
  chat_messages_daily: Number(process.env.PRO_CHAT_DAILY_MESSAGES || "350"),
  chat_messages_per_month: Number(process.env.PRO_CHAT_MESSAGES || "350"),
  portfolio_stocks: Number(process.env.PRO_PORTFOLIO_STOCKS || "10"),
  price_egp: Number(process.env.NEXT_PUBLIC_PRO_PRICE_EGP || process.env.PRO_PRICE_EGP || "200"),
  billing: "enabled",
};

const UNLIMITED: PlanLimits = {
  ...FREE,
  signal_delay_days: 0,
  chat_messages_daily: Number.MAX_SAFE_INTEGER,
  chat_messages_per_month: Number.MAX_SAFE_INTEGER,
  portfolio_stocks: Number.MAX_SAFE_INTEGER,
  billing: "disabled",
};

export const PRO_PLAN_IDS = ["pro", "pro_6m", "pro_1y", "lifetime", "pro_lifetime"] as const;

export function planLimits(planId?: string | null): PlanLimits {
  if (!paymentsEnabled()) {
    return { ...UNLIMITED };
  }
  const p = (planId || "").toLowerCase();
  return (PRO_PLAN_IDS as readonly string[]).includes(p) ? { ...PRO, name: planId || "pro" } : { ...FREE };
}

export function isPro(rows: Array<{ plan_id?: unknown; status?: unknown; current_period_end?: unknown | null }>): boolean {
  if (!paymentsEnabled()) {
    return true; // free site: everything available
  }
  const now = Date.now();
  for (const row of rows || []) {
    const plan = String(row.plan_id || "").toLowerCase();
    if (!(PRO_PLAN_IDS as readonly string[]).includes(plan) || !["active", "trialing"].includes(String(row.status || "").toLowerCase())) {
      continue;
    }
    if (row.current_period_end) {
      const end = new Date(String(row.current_period_end)).getTime();
      if (Number.isFinite(end) && end <= now) {
        continue; // expired
      }
    }
    return true;
  }
  return false;
}

/** Strict entitlement check for paid-only features, regardless of billing mode. */
export function hasActiveProSubscription(rows: Array<{ plan_id?: unknown; status?: unknown; current_period_end?: unknown | null }>): boolean {
  const now = Date.now();
  return (rows || []).some((row) => {
    const plan = String(row.plan_id || "").toLowerCase();
    if (!(PRO_PLAN_IDS as readonly string[]).includes(plan)) return false;
    if (!["active", "trialing"].includes(String(row.status || "").toLowerCase())) return false;
    if (!row.current_period_end) return true;
    const end = new Date(String(row.current_period_end)).getTime();
    return Number.isFinite(end) && end > now;
  });
}

/** Returns YYYY-MM-DD in Africa/Cairo timezone so Website and Telegram always share the exact same day/month boundary. */
export function getCairoDateString(now: Date = new Date()): string {
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Africa/Cairo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(now);
    const year = parts.find((p) => p.type === "year")?.value;
    const month = parts.find((p) => p.type === "month")?.value;
    const day = parts.find((p) => p.type === "day")?.value;
    if (year && month && day) return `${year}-${month}-${day}`;
  } catch {
    // Fallback to UTC date if Intl timeZone is unavailable
  }
  return now.toISOString().split("T")[0];
}

export interface SubscriptionQuotaWindow {
  isPro: boolean;
  activeSub: Record<string, any> | null;
  todayStr: string;
  calMonthStartStr: string;
  effectiveMonthStartStr: string;
  effectiveStartDate: Date;
}

/**
 * Single source of truth for calculating a user's active subscription & quota date window.
 * Used identically across /api/user/quota, /api/ai-chat (GET & POST), and /api/telegram/vip-chat.
 */
export function resolveSubscriptionQuotaWindow(
  rows: Array<Record<string, any>> | null | undefined,
  now: Date = new Date()
): SubscriptionQuotaWindow {
  const list = Array.isArray(rows) ? rows : [];
  const pro = hasActiveProSubscription(list);
  const nowMs = now.getTime();
  const activeSub =
    list.find((row) => {
      const plan = String(row?.plan_id || "").toLowerCase();
      const status = String(row?.status || "").toLowerCase();
      if (!(PRO_PLAN_IDS as readonly string[]).includes(plan)) return false;
      if (!["active", "trialing"].includes(status)) return false;
      if (!row?.current_period_end) return true;
      const end = new Date(String(row.current_period_end)).getTime();
      return Number.isFinite(end) && end > nowMs;
    }) ||
    list[0] ||
    null;

  const todayStr = getCairoDateString(now);
  const calMonthStartStr = `${todayStr.slice(0, 7)}-01`;
  let effectiveMonthStartStr = calMonthStartStr;
  let effectiveStartDate = new Date(`${calMonthStartStr}T00:00:00.000Z`);

  if (pro && activeSub?.current_period_start) {
    const parsed = new Date(String(activeSub.current_period_start));
    if (!Number.isNaN(parsed.getTime())) {
      const subStartStr = parsed.toISOString().split("T")[0];
      // Advance window start if subscription started mid-month (and is not a future early-renewal timestamp)
      if (
        /^\d{4}-\d{2}-\d{2}$/.test(subStartStr) &&
        subStartStr > calMonthStartStr &&
        subStartStr <= todayStr
      ) {
        effectiveMonthStartStr = subStartStr;
        effectiveStartDate = parsed;
      }
    }
  }

  return {
    isPro: pro,
    activeSub,
    todayStr,
    calMonthStartStr,
    effectiveMonthStartStr,
    effectiveStartDate,
  };
}

/** Filter recommendations to those at least N days old (for free users). */
export function filterByDelay<T extends { created_at?: string | null }>(
  rows: T[],
  delayDays: number,
): T[] {
  if (delayDays <= 0) {
    return rows;
  }
  const cutoff = Date.now() - delayDays * 24 * 60 * 60 * 1000;
  return rows.filter((r) => {
    if (!r.created_at) return false;
    return new Date(r.created_at).getTime() <= cutoff;
  });
}
