import {
  ADMIN_EXCLUDED_EMAILS,
  ADMIN_EXCLUDED_USER_IDS,
  isExcludedAdminUser,
} from "@/lib/admin/admin-exclusions";

export type FounderCohort = "50_EGP" | "100_EGP" | "REGULAR" | "LIFETIME" | "B2B";

export type FounderStatus =
  | "renewed_active"
  | "active_first_term"
  | "in_grace_72h"
  | "churned";

export interface FounderMemberInput {
  user_id: string;
  joined_at?: string | null;
}

export interface FounderOrderInput {
  user_id: string;
  plan_id?: string | null;
  amount_egp?: number | string | null;
  provider?: string | null;
  status?: string | null;
  created_at?: string | null;
}

export interface FounderSubInput {
  user_id: string;
  plan_id?: string | null;
  status?: string | null;
  provider?: string | null;
  current_period_start?: string | null;
  current_period_end?: string | null;
  updated_at?: string | null;
  created_at?: string | null;
}

export interface FounderProfileInput {
  id: string;
  email?: string | null;
  display_name?: string | null;
  username?: string | null;
  whatsapp_number?: string | null;
  telegram_chat_id?: string | null;
}

export interface FounderAnalyticsRow {
  user_id: string;
  email: string | null;
  display_name: string | null;
  whatsapp_number: string | null;
  telegram_chat_id: string | null;
  cohort: FounderCohort;
  is_founder: boolean;
  joined_at: string | null;
  approved_orders_count: number;
  total_paid_egp: number;
  plan_id: string | null;
  sub_status: string | null;
  provider: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  is_active: boolean;
  is_lifetime: boolean;
  in_grace_72h: boolean;
  status: FounderStatus;
  days_until_expiry: number | null;
  hours_until_expiry: number | null;
}

export interface FoundersCohortSummary {
  total: number;
  active: number;
  renewed: number;
  first_term_active: number;
  expired: number;
  in_grace_72h: number;
  matured_total: number;
  overall_retention_rate: number;
  matured_retention_rate: number;
}

export interface FoundersRetentionSummary {
  generated_at: string;
  total_founders: number;
  total_paid_users: number;
  founders_count: number;
  non_founder_paid_count: number;
  active_count: number;
  renewed_count: number;
  first_term_active_count: number;
  expired_count: number;
  in_grace_72h_count: number;
  churned_past_grace_count: number;
  matured_count: number;
  due_within_3_days_count: number;
  overall_retention_rate: number;
  matured_retention_rate: number;
  total_revenue_egp: number;
  cohort_50: FoundersCohortSummary;
  cohort_100: FoundersCohortSummary;
  cohort_regular: FoundersCohortSummary;
  cohort_lifetime: FoundersCohortSummary;
  cohort_b2b: FoundersCohortSummary;
  founders_only: FoundersCohortSummary;
  non_founders_paid: FoundersCohortSummary;
  members: FounderAnalyticsRow[];
}

export const FOUNDERS_ADMIN_USER_IDS = ADMIN_EXCLUDED_USER_IDS;
export const FOUNDERS_ADMIN_EMAILS = ADMIN_EXCLUDED_EMAILS;

const FIFTY_ERA_CUTOFF_MS = Date.parse("2026-11-01T00:00:00Z");
const GRACE_WINDOW_MS = 72 * 60 * 60 * 1000;
const THREE_DAYS_MS = 72 * 60 * 60 * 1000;
const MS_PER_HOUR = 60 * 60 * 1000;
const MS_PER_DAY = 24 * MS_PER_HOUR;

function toMs(val?: string | null): number {
  if (!val) return 0;
  const parsed = Date.parse(val);
  return Number.isFinite(parsed) ? parsed : 0;
}

function roundPct(numerator: number, denominator: number): number {
  if (denominator <= 0) return 0;
  return Math.round((numerator / denominator) * 1000) / 10;
}

function subscriptionPriority(sub: FounderSubInput, nowMs: number): [number, number, number, number] {
  const status = String(sub.status || "").toLowerCase().trim();
  const endIso = sub.current_period_end;
  const endMs = toMs(endIso);
  const isUnexpired = !endIso || endMs > nowMs;
  const statusRank =
    status === "active" && isUnexpired
      ? 3
      : status === "trialing" && isUnexpired
      ? 2
      : status === "active" || status === "trialing"
      ? 1
      : 0;
  const plan = String(sub.plan_id || "").toLowerCase().trim();
  const lifetimeRank = plan === "lifetime" || plan === "pro_lifetime" ? 1 : 0;
  const effectiveEnd = !endIso && isUnexpired ? Number.MAX_SAFE_INTEGER : endMs;
  const updated = Math.max(toMs(sub.updated_at), toMs(sub.created_at));
  return [statusRank, lifetimeRank, effectiveEnd, updated];
}

function isBetterSubscription(candidate: FounderSubInput, existing: FounderSubInput, nowMs: number): boolean {
  const a = subscriptionPriority(candidate, nowMs);
  const b = subscriptionPriority(existing, nowMs);
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return a[i] > b[i];
  }
  return false;
}

export function pickPreferredSubscription<T extends FounderSubInput>(
  subscriptions: T[],
  now: Date = new Date()
): T | null {
  const nowMs = now.getTime();
  let best: T | null = null;
  for (const sub of subscriptions || []) {
    if (!best || isBetterSubscription(sub, best, nowMs)) {
      best = sub;
    }
  }
  return best;
}

export function formatCairoDateTime(dateStr?: string | null, isAr = true): string {
  if (!dateStr) return "—";
  try {
    return new Intl.DateTimeFormat(isAr ? "ar-EG" : "en-US", {
      timeZone: "Africa/Cairo",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(dateStr));
  } catch {
    return String(dateStr).slice(0, 16);
  }
}

export function buildWhatsAppUrl(phone?: string | null): string | null {
  if (!phone) return null;
  const digits = phone.replace(/[^0-9]/g, "");
  if (!digits) return null;
  const e164 = digits.startsWith("01")
    ? `20${digits.slice(1)}`
    : digits.startsWith("20")
    ? digits
    : `20${digits}`;
  return `https://wa.me/${e164}`;
}

export function getPaidCohortMeta(
  cohort: FounderCohort,
  isAr = true
): { label: string; badgeClass: string } {
  switch (cohort) {
    case "50_EGP":
      return {
        label: isAr ? "مؤسس 50 ج.م" : "Founder 50",
        badgeClass: "bg-amber-300 text-black",
      };
    case "100_EGP":
      return {
        label: isAr ? "مؤسس 100 ج.م" : "Founder 100",
        badgeClass: "bg-indigo-200 dark:bg-indigo-900 text-indigo-950 dark:text-indigo-100",
      };
    case "LIFETIME":
      return {
        label: isAr ? "مدى الحياة 👑" : "Lifetime 👑",
        badgeClass: "bg-yellow-300 text-black",
      };
    case "B2B":
      return {
        label: isAr ? "شركات B2B" : "B2B Group",
        badgeClass: "bg-cyan-200 dark:bg-cyan-900 text-cyan-950 dark:text-cyan-100",
      };
    case "REGULAR":
    default:
      return {
        label: isAr ? "باقة Pro عادية" : "Regular Pro",
        badgeClass: "bg-emerald-200 dark:bg-emerald-900 text-emerald-950 dark:text-emerald-100",
      };
  }
}

const APPROVED_ORDER_STATUSES = new Set(["approved", "success", "paid"]);

export function isQualifyingFoundersOrder(order: FounderOrderInput): boolean {
  const status = String(order.status || "").toLowerCase().trim();
  if (!APPROVED_ORDER_STATUSES.has(status)) return false;
  const plan = String(order.plan_id || "pro").toLowerCase().trim();
  const amount = Number(order.amount_egp ?? 0);
  if (!Number.isFinite(amount) || amount <= 0) return false;
  if (plan === "pro" || plan === "pro_renewal") return amount <= 100;
  if (plan === "pro_6m") return amount <= 500;
  if (plan === "pro_1y") return amount <= 1000;
  return false;
}

function classifyPaidCohort(params: {
  userOrders: FounderOrderInput[];
  inFoundersTable: boolean;
  joinedMs: number;
  subPlanId: string | null;
  isFounder: boolean;
}): FounderCohort {
  const firstOrder = params.userOrders[0];
  const firstPlan = String(firstOrder?.plan_id || params.subPlanId || "").toLowerCase().trim();
  const firstAmount = Number(firstOrder?.amount_egp ?? 0);
  const has50Order = params.userOrders.some((o) => {
    const amt = Number(o.amount_egp ?? 0);
    return amt > 0 && amt <= 50;
  });
  const has100Order = params.userOrders.some((o) => {
    const amt = Number(o.amount_egp ?? 0);
    return amt > 50 && amt <= 100;
  });

  if (firstPlan.startsWith("b2b") || String(params.subPlanId || "").startsWith("b2b")) {
    return "B2B";
  }
  if (has50Order) return "50_EGP";
  if (has100Order) return "100_EGP";
  if ((firstPlan === "lifetime" || firstPlan === "pro_lifetime") && !params.inFoundersTable) {
    return "LIFETIME";
  }
  if (
    params.inFoundersTable &&
    params.joinedMs > 0 &&
    params.joinedMs < FIFTY_ERA_CUTOFF_MS &&
    firstAmount <= 100
  ) {
    return "50_EGP";
  }
  if (firstAmount >= 150) {
    return "REGULAR";
  }
  if (params.subPlanId === "lifetime" || params.subPlanId === "pro_lifetime") {
    return "LIFETIME";
  }
  return params.isFounder ? "100_EGP" : "REGULAR";
}

function summarizeCohort(rows: FounderAnalyticsRow[]): FoundersCohortSummary {
  const total = rows.length;
  const active = rows.filter((r) => r.is_active).length;
  const renewed = rows.filter((r) => r.status === "renewed_active").length;
  const first_term_active = rows.filter((r) => r.status === "active_first_term").length;
  const expired = rows.filter((r) => !r.is_active).length;
  const in_grace_72h = rows.filter((r) => r.status === "in_grace_72h").length;
  const matured_total = renewed + expired;

  return {
    total,
    active,
    renewed,
    first_term_active,
    expired,
    in_grace_72h,
    matured_total,
    overall_retention_rate: roundPct(active, total),
    matured_retention_rate: roundPct(renewed, matured_total),
  };
}

export function summarizeFoundersRetention(params: {
  founderMembers: FounderMemberInput[];
  approvedOrders: FounderOrderInput[];
  subscriptions: FounderSubInput[];
  profilesById: Map<string, FounderProfileInput>;
  excludeUserIds?: Set<string>;
  now?: Date;
}): FoundersRetentionSummary {
  const nowDate = params.now ?? new Date();
  const nowMs = nowDate.getTime();
  const excludeIds = new Set<string>(ADMIN_EXCLUDED_USER_IDS);
  params.excludeUserIds?.forEach((id) => excludeIds.add(id));

  const memberJoinMap = new Map<string, string | null>();
  for (const row of params.founderMembers || []) {
    const uid = String(row.user_id || "").trim();
    if (!uid) continue;
    const prev = memberJoinMap.get(uid);
    if (!prev || (row.joined_at && toMs(row.joined_at) < toMs(prev))) {
      memberJoinMap.set(uid, row.joined_at ?? null);
    }
  }

  const ordersByUser = new Map<string, FounderOrderInput[]>();
  const qualifyingOrderUids = new Set<string>();
  const allOrderUids = new Set<string>();
  for (const order of params.approvedOrders || []) {
    const status = String(order.status || "").toLowerCase().trim();
    if (!APPROVED_ORDER_STATUSES.has(status)) continue;
    const uid = String(order.user_id || "").trim();
    if (!uid) continue;
    const list = ordersByUser.get(uid) ?? [];
    list.push(order);
    ordersByUser.set(uid, list);
    allOrderUids.add(uid);
    if (isQualifyingFoundersOrder(order)) {
      qualifyingOrderUids.add(uid);
    }
  }

  const latestSubByUser = new Map<string, FounderSubInput>();
  const nonTrialPaidSubUids = new Set<string>();
  for (const sub of params.subscriptions || []) {
    const uid = String(sub.user_id || "").trim();
    if (!uid) continue;
    const existing = latestSubByUser.get(uid);
    if (!existing || isBetterSubscription(sub, existing, nowMs)) {
      latestSubByUser.set(uid, sub);
    }
    const subStatus = String(sub.status || "").toLowerCase().trim();
    const subPlan = String(sub.plan_id || "").toLowerCase().trim();
    if (subStatus !== "trialing" && subPlan && subPlan !== "free") {
      nonTrialPaidSubUids.add(uid);
    }
  }

  // Track every customer who has paid (Founders 50/100 + Regular 200+ + 6m/1y + Lifetime + B2B + Kashier)
  const allCandidateIds = new Set<string>([
    ...memberJoinMap.keys(),
    ...allOrderUids,
    ...nonTrialPaidSubUids,
  ]);

  const members: FounderAnalyticsRow[] = [];
  let totalRevenue = 0;

  for (const uid of allCandidateIds) {
    const profile = params.profilesById.get(uid);
    const email = profile?.email ? String(profile.email).toLowerCase().trim() : null;
    if (isExcludedAdminUser(uid, email, excludeIds)) continue;

    const userOrders = (ordersByUser.get(uid) ?? []).sort(
      (a, b) => toMs(a.created_at) - toMs(b.created_at)
    );
    const inFoundersTable = memberJoinMap.has(uid);
    const isFounder = inFoundersTable || qualifyingOrderUids.has(uid);
    const joinedAt = memberJoinMap.get(uid) ?? userOrders[0]?.created_at ?? null;
    const joinedMs = toMs(joinedAt);

    const paidTotal = Math.round(
      userOrders.reduce((acc, o) => acc + (Number(o.amount_egp ?? 0) || 0), 0) * 100
    ) / 100;
    totalRevenue += paidTotal;

    const sub = latestSubByUser.get(uid) ?? null;
    const planId = sub?.plan_id ? String(sub.plan_id).toLowerCase().trim() : null;
    const subStatus = sub?.status ? String(sub.status).toLowerCase().trim() : null;
    const endIso = sub?.current_period_end ?? null;
    const endMs = toMs(endIso);
    const cohort = classifyPaidCohort({
      userOrders,
      inFoundersTable,
      joinedMs,
      subPlanId: planId,
      isFounder,
    });

    const isLifetime = planId === "lifetime" || planId === "pro_lifetime";
    const isActive = Boolean(
      sub &&
        (subStatus === "active" || subStatus === "trialing") &&
        (!endIso || endMs > nowMs)
    );

    const inGrace72h = Boolean(!isActive && endMs > 0 && endMs <= nowMs && nowMs - endMs <= GRACE_WINDOW_MS);
    const hasRenewed = isActive && (userOrders.length >= 2 || isLifetime);

    const status: FounderStatus = isActive
      ? hasRenewed
        ? "renewed_active"
        : "active_first_term"
      : inGrace72h
      ? "in_grace_72h"
      : "churned";

    const diffMs = endMs > 0 ? endMs - nowMs : null;
    const hoursUntil = diffMs !== null ? Math.round((diffMs / MS_PER_HOUR) * 10) / 10 : null;
    const daysUntil = diffMs !== null ? Math.round((diffMs / MS_PER_DAY) * 10) / 10 : null;

    members.push({
      user_id: uid,
      email,
      display_name: profile?.display_name?.trim() || profile?.username?.trim() || null,
      whatsapp_number: profile?.whatsapp_number?.trim() || null,
      telegram_chat_id: profile?.telegram_chat_id?.trim() || null,
      cohort,
      is_founder: isFounder,
      joined_at: joinedAt,
      approved_orders_count: userOrders.length,
      total_paid_egp: paidTotal,
      plan_id: planId,
      sub_status: subStatus,
      provider: sub?.provider ?? null,
      current_period_start: sub?.current_period_start ?? null,
      current_period_end: endIso,
      is_active: isActive,
      is_lifetime: isLifetime,
      in_grace_72h: inGrace72h,
      status,
      days_until_expiry: daysUntil,
      hours_until_expiry: hoursUntil,
    });
  }

  // Sort: Active first (soonest renewal first, lifetime last), then Expired (most recent expiry first)
  members.sort((a, b) => {
    if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
    if (a.is_active) {
      if (a.is_lifetime !== b.is_lifetime) return a.is_lifetime ? 1 : -1;
      const aEnd = toMs(a.current_period_end) || Number.MAX_SAFE_INTEGER;
      const bEnd = toMs(b.current_period_end) || Number.MAX_SAFE_INTEGER;
      return aEnd - bEnd;
    }
    return toMs(b.current_period_end) - toMs(a.current_period_end);
  });

  const overall = summarizeCohort(members);
  const cohort50 = summarizeCohort(members.filter((m) => m.cohort === "50_EGP"));
  const cohort100 = summarizeCohort(members.filter((m) => m.cohort === "100_EGP"));
  const cohortRegular = summarizeCohort(members.filter((m) => m.cohort === "REGULAR"));
  const cohortLifetime = summarizeCohort(members.filter((m) => m.cohort === "LIFETIME"));
  const cohortB2b = summarizeCohort(members.filter((m) => m.cohort === "B2B"));
  const foundersOnly = summarizeCohort(members.filter((m) => m.is_founder));
  const nonFoundersPaid = summarizeCohort(members.filter((m) => !m.is_founder));
  const dueWithin3Days = members.filter(
    (m) => m.is_active && !m.is_lifetime && toMs(m.current_period_end) > nowMs && toMs(m.current_period_end) - nowMs <= THREE_DAYS_MS
  ).length;

  return {
    generated_at: nowDate.toISOString(),
    total_founders: overall.total,
    total_paid_users: overall.total,
    founders_count: foundersOnly.total,
    non_founder_paid_count: nonFoundersPaid.total,
    active_count: overall.active,
    renewed_count: overall.renewed,
    first_term_active_count: overall.first_term_active,
    expired_count: overall.expired,
    in_grace_72h_count: overall.in_grace_72h,
    churned_past_grace_count: overall.expired - overall.in_grace_72h,
    matured_count: overall.matured_total,
    due_within_3_days_count: dueWithin3Days,
    overall_retention_rate: overall.overall_retention_rate,
    matured_retention_rate: overall.matured_retention_rate,
    total_revenue_egp: Math.round(totalRevenue * 100) / 100,
    cohort_50: cohort50,
    cohort_100: cohort100,
    cohort_regular: cohortRegular,
    cohort_lifetime: cohortLifetime,
    cohort_b2b: cohortB2b,
    founders_only: foundersOnly,
    non_founders_paid: nonFoundersPaid,
    members,
  };
}
