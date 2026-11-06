/**
 * Trial funnel math shared by the admin API and its tests.
 *
 * Definitions:
 * - activated: the trial user sent at least one chat message after starting
 *   the trial. This is the step that actually predicts conversion.
 * - converted: a paid subscription started at/after the trial start.
 */

export type TrialRow = {
  user_id: string;
  started_at: string;
  expires_at: string;
};

export type SubscriptionRow = {
  user_id: string;
  plan_id?: string | null;
  status?: string | null;
  provider?: string | null;
  current_period_start?: string | null;
  created_at?: string | null;
};

export type MessageRow = {
  user_id: string;
  created_at: string;
};

export type TrialEventRow = {
  user_id: string;
  event_name: string;
  metadata?: Record<string, unknown> | null;
};

const PAID_PLANS = new Set(["pro", "lifetime", "pro_lifetime"]);

function time(value?: string | null): number {
  if (!value) return NaN;
  return new Date(value).getTime();
}

export type TrialFunnelVariant = {
  started: number;
  activated: number;
  converted: number;
};

export type TrialFunnel = {
  total: number;
  active: number;
  finished: number;
  activated: number;
  activatedFinished: number;
  converted: number;
  convertedFinished: number;
  conversionRateFinished: number;
  activationRateFinished: number;
  variants: Record<"A" | "B", TrialFunnelVariant>;
};

export function summarizeTrialFunnel(
  trials: TrialRow[],
  subscriptions: SubscriptionRow[],
  messages: MessageRow[],
  trialEvents: TrialEventRow[],
  now: Date = new Date(),
): TrialFunnel {
  const nowMs = now.getTime();

  const paidByUser = new Map<string, number[]>();
  for (const sub of subscriptions) {
    if (sub.provider === "trial") continue;
    if (!sub.plan_id || !PAID_PLANS.has(sub.plan_id)) continue;
    if (sub.status !== "active") continue;
    const startedAt = time(sub.current_period_start) || time(sub.created_at);
    if (!Number.isFinite(startedAt)) continue;
    const list = paidByUser.get(sub.user_id) || [];
    list.push(startedAt);
    paidByUser.set(sub.user_id, list);
  }

  const messageTimesByUser = new Map<string, number[]>();
  for (const message of messages) {
    const at = time(message.created_at);
    if (!Number.isFinite(at)) continue;
    const list = messageTimesByUser.get(message.user_id) || [];
    list.push(at);
    messageTimesByUser.set(message.user_id, list);
  }

  const variantByUser = new Map<string, "A" | "B">();
  for (const event of trialEvents) {
    if (event.event_name !== "trial_started") continue;
    const variant = event.metadata?.variant === "B" ? "B" : "A";
    variantByUser.set(event.user_id, variant);
  }

  const variants: Record<"A" | "B", TrialFunnelVariant> = {
    A: { started: 0, activated: 0, converted: 0 },
    B: { started: 0, activated: 0, converted: 0 },
  };

  let active = 0;
  let finished = 0;
  let activated = 0;
  let activatedFinished = 0;
  let converted = 0;
  let convertedFinished = 0;

  for (const trial of trials) {
    const startedAt = time(trial.started_at);
    const expiresAt = time(trial.expires_at);
    const isFinished = Number.isFinite(expiresAt) ? expiresAt <= nowMs : false;
    const isActivated = (messageTimesByUser.get(trial.user_id) || [])
      .some((at) => Number.isFinite(startedAt) && at >= startedAt);
    const isConverted = (paidByUser.get(trial.user_id) || [])
      .some((at) => Number.isFinite(startedAt) && at >= startedAt);

    if (isFinished) finished += 1;
    else active += 1;
    if (isActivated) activated += 1;
    if (isActivated && isFinished) activatedFinished += 1;
    if (isConverted) converted += 1;
    if (isConverted && isFinished) convertedFinished += 1;

    const variant = variantByUser.get(trial.user_id);
    if (variant) {
      variants[variant].started += 1;
      if (isActivated) variants[variant].activated += 1;
      if (isConverted) variants[variant].converted += 1;
    }
  }

  return {
    total: trials.length,
    active,
    finished,
    activated,
    activatedFinished,
    converted,
    convertedFinished,
    conversionRateFinished: finished ? Math.round((convertedFinished / finished) * 1000) / 10 : 0,
    activationRateFinished: finished ? Math.round((activatedFinished / finished) * 1000) / 10 : 0,
    variants,
  };
}
