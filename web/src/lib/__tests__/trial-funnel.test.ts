import { summarizeTrialFunnel, type MessageRow, type SubscriptionRow, type TrialEventRow, type TrialRow } from "../trial-funnel";

const NOW = new Date("2026-11-06T12:00:00Z");

const trials: TrialRow[] = [
  { user_id: "u1", started_at: "2026-11-01T10:00:00Z", expires_at: "2026-11-04T10:00:00Z" }, // finished, activated, paid
  { user_id: "u2", started_at: "2026-11-01T10:00:00Z", expires_at: "2026-11-04T10:00:00Z" }, // finished, activated, not paid
  { user_id: "u3", started_at: "2026-11-01T10:00:00Z", expires_at: "2026-11-04T10:00:00Z" }, // finished, never chatted
  { user_id: "u4", started_at: "2026-11-05T10:00:00Z", expires_at: "2026-11-08T10:00:00Z" }, // active
];

const subscriptions: SubscriptionRow[] = [
  { user_id: "u1", plan_id: "pro", status: "active", provider: "easykash", current_period_start: "2026-11-03T10:00:00Z" },
  { user_id: "u2", plan_id: "pro", status: "canceled", provider: "easykash", current_period_start: "2026-11-03T10:00:00Z" },
  { user_id: "u3", plan_id: "pro", status: "active", provider: "trial", current_period_start: "2026-11-01T10:00:00Z" },
];

const messages: MessageRow[] = [
  { user_id: "u1", created_at: "2026-11-01T11:00:00Z" },
  { user_id: "u2", created_at: "2026-11-02T11:00:00Z" },
  { user_id: "u4", created_at: "2026-11-05T12:00:00Z" },
];

const events: TrialEventRow[] = [
  { user_id: "u1", event_name: "trial_started", metadata: { variant: "A" } },
  { user_id: "u2", event_name: "trial_started", metadata: { variant: "B" } },
];

describe("summarizeTrialFunnel", () => {
  it("counts activation and paid conversion only inside the trial", () => {
    const funnel = summarizeTrialFunnel(trials, subscriptions, messages, events, NOW);
    expect(funnel.total).toBe(4);
    expect(funnel.finished).toBe(3);
    expect(funnel.active).toBe(1);
    expect(funnel.activated).toBe(3);
    expect(funnel.activatedFinished).toBe(2);
    expect(funnel.converted).toBe(1);
    expect(funnel.convertedFinished).toBe(1);
    expect(funnel.conversionRateFinished).toBeCloseTo(33.3, 1);
    expect(funnel.activationRateFinished).toBeCloseTo(66.7, 1);
  });

  it("breaks the funnel down by prompt variant", () => {
    const funnel = summarizeTrialFunnel(trials, subscriptions, messages, events, NOW);
    expect(funnel.variants.A).toEqual({ started: 1, activated: 1, converted: 1 });
    expect(funnel.variants.B).toEqual({ started: 1, activated: 1, converted: 0 });
  });

  it("ignores payments made before the trial started", () => {
    const early: SubscriptionRow[] = [
      { user_id: "u4", plan_id: "pro", status: "active", provider: "easykash", current_period_start: "2026-10-20T10:00:00Z" },
    ];
    const funnel = summarizeTrialFunnel(trials, early, messages, [], NOW);
    expect(funnel.converted).toBe(0);
  });

  it("returns zero rates when no trial has finished", () => {
    const funnel = summarizeTrialFunnel([trials[3]], [], [], [], NOW);
    expect(funnel.finished).toBe(0);
    expect(funnel.conversionRateFinished).toBe(0);
    expect(funnel.activationRateFinished).toBe(0);
  });
});
