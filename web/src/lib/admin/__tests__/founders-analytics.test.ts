import {
  isQualifyingFoundersOrder,
  summarizeFoundersRetention,
  type FounderProfileInput,
} from "@/lib/admin/founders-analytics";

describe("summarizeFoundersRetention", () => {
  const now = new Date("2026-11-16T09:50:00Z");

  it("classifies renewed, first-term active, 72h grace, churned, excludes admins, and computes exact rates", () => {
    const profiles = new Map<string, FounderProfileInput>([
      ["u-renewed", { id: "u-renewed", email: "renewed@example.com", whatsapp_number: "01000000001" }],
      ["u-lifetime", { id: "u-lifetime", email: "life@example.com" }],
      ["u-due-soon", { id: "u-due-soon", email: "soon@example.com" }],
      ["u-nov-100", { id: "u-nov-100", email: "nov@example.com" }],
      ["u-grace", { id: "u-grace", email: "grace@example.com" }],
      ["u-churned", { id: "u-churned", email: "churned@example.com" }],
      ["ba9c27e8-f62d-452f-8a29-dc77fd092207", { id: "ba9c27e8-f62d-452f-8a29-dc77fd092207", email: "weeessd57@gmail.com" }],
    ]);

    const summary = summarizeFoundersRetention({
      now,
      profilesById: profiles,
      founderMembers: [
        { user_id: "u-renewed", joined_at: "2026-10-01T00:00:00Z" },
        { user_id: "u-lifetime", joined_at: "2026-10-01T09:00:00Z" },
        { user_id: "u-due-soon", joined_at: "2026-10-18T19:00:00Z" },
        { user_id: "u-nov-100", joined_at: "2026-11-05T10:00:00Z" },
        { user_id: "u-grace", joined_at: "2026-10-14T18:00:00Z" },
        { user_id: "u-churned", joined_at: "2026-10-05T10:00:00Z" },
        { user_id: "ba9c27e8-f62d-452f-8a29-dc77fd092207", joined_at: "2026-11-09T10:00:00Z" },
      ],
      approvedOrders: [
        { user_id: "u-renewed", plan_id: "pro", amount_egp: 50, status: "approved", created_at: "2026-10-01T00:00:00Z" },
        { user_id: "u-renewed", plan_id: "pro", amount_egp: 50, status: "approved", created_at: "2026-11-01T00:00:00Z" },
        { user_id: "u-lifetime", plan_id: "pro", amount_egp: 50, status: "approved", created_at: "2026-10-01T09:00:00Z" },
        { user_id: "u-lifetime", plan_id: "lifetime", amount_egp: 2250, status: "approved", created_at: "2026-10-20T06:00:00Z" },
        { user_id: "u-due-soon", plan_id: "pro", amount_egp: 50, status: "approved", created_at: "2026-10-18T19:00:00Z" },
        { user_id: "u-nov-100", plan_id: "pro", amount_egp: 100, status: "approved", created_at: "2026-11-05T10:00:00Z" },
        { user_id: "u-grace", plan_id: "pro", amount_egp: 50, status: "approved", created_at: "2026-10-14T18:00:00Z" },
        { user_id: "u-churned", plan_id: "pro", amount_egp: 50, status: "approved", created_at: "2026-10-05T10:00:00Z" },
      ],
      subscriptions: [
        { user_id: "u-renewed", plan_id: "pro", status: "active", current_period_end: "2026-12-01T00:00:00Z" },
        { user_id: "u-lifetime", plan_id: "lifetime", status: "active", current_period_end: "2126-10-20T06:00:00Z" },
        { user_id: "u-due-soon", plan_id: "pro", status: "active", current_period_end: "2026-11-17T19:00:00Z" },
        { user_id: "u-nov-100", plan_id: "pro", status: "active", current_period_end: "2026-12-05T10:00:00Z" },
        { user_id: "u-grace", plan_id: "pro", status: "canceled", current_period_end: "2026-11-14T18:00:00Z" },
        { user_id: "u-churned", plan_id: "pro", status: "canceled", current_period_end: "2026-11-04T10:00:00Z" },
        { user_id: "ba9c27e8-f62d-452f-8a29-dc77fd092207", plan_id: "pro", status: "active", current_period_end: "2126-11-21T00:00:00Z" },
      ],
    });

    expect(summary.total_founders).toBe(6);
    expect(summary.active_count).toBe(4);
    expect(summary.renewed_count).toBe(2);
    expect(summary.first_term_active_count).toBe(2);
    expect(summary.expired_count).toBe(2);
    expect(summary.in_grace_72h_count).toBe(1);
    expect(summary.churned_past_grace_count).toBe(1);
    expect(summary.due_within_3_days_count).toBe(1);
    expect(summary.matured_count).toBe(4);
    expect(summary.matured_retention_rate).toBe(50);
    expect(summary.overall_retention_rate).toBe(66.7);
    expect(summary.total_revenue_egp).toBe(2650);
    expect(summary.cohort_50.total).toBe(5);
    expect(summary.cohort_100.total).toBe(1);

    // Active members ordered soonest renewal first, lifetime last among active
    expect(summary.members[0].user_id).toBe("u-due-soon");
    expect(summary.members[0].status).toBe("active_first_term");
    expect(summary.members[3].user_id).toBe("u-lifetime");
    expect(summary.members[4].status).toBe("in_grace_72h");
    expect(summary.members[5].status).toBe("churned");
  });

  it("identifies qualifying founders orders across plans accurately", () => {
    expect(isQualifyingFoundersOrder({ user_id: "u", plan_id: "pro", amount_egp: 100, status: "approved" })).toBe(true);
    expect(isQualifyingFoundersOrder({ user_id: "u", plan_id: "pro", amount_egp: 200, status: "approved" })).toBe(false);
    expect(isQualifyingFoundersOrder({ user_id: "u", plan_id: "pro_6m", amount_egp: 500, status: "approved" })).toBe(true);
    expect(isQualifyingFoundersOrder({ user_id: "u", plan_id: "pro_1y", amount_egp: 1000, status: "approved" })).toBe(true);
  });

  it("prioritizes active subscriptions over canceled later-dated or dated expired rows", () => {
    const profiles = new Map<string, FounderProfileInput>([
      ["u-1", { id: "u-1", email: "multi-sub@example.com" }],
      ["u-2", { id: "u-2", email: "null-end@example.com" }],
    ]);

    const summary = summarizeFoundersRetention({
      now,
      profilesById: profiles,
      founderMembers: [
        { user_id: "u-1", joined_at: "2026-10-05T00:00:00Z" },
        { user_id: "u-2", joined_at: "2026-10-05T00:00:00Z" },
      ],
      approvedOrders: [
        { user_id: "u-1", plan_id: "pro", amount_egp: 50, status: "approved", created_at: "2026-10-05T00:00:00Z" },
        { user_id: "u-1", plan_id: "pro", amount_egp: 50, status: "approved", created_at: "2026-11-05T00:00:00Z" },
        { user_id: "u-2", plan_id: "pro", amount_egp: 50, status: "approved", created_at: "2026-10-05T00:00:00Z" },
      ],
      subscriptions: [
        // Canceled longer-term row with a later date MUST NOT shadow active monthly row
        { user_id: "u-1", plan_id: "pro_6m", status: "canceled", current_period_end: "2027-04-01T00:00:00Z" },
        { user_id: "u-1", plan_id: "pro", status: "active", current_period_end: "2026-12-05T00:00:00Z" },
        // Active row with null current_period_end MUST beat older canceled row with non-null date
        { user_id: "u-2", plan_id: "pro", status: "canceled", current_period_end: "2026-11-10T00:00:00Z" },
        { user_id: "u-2", plan_id: "lifetime", status: "active", current_period_end: null },
      ],
    });

    expect(summary.active_count).toBe(2);
    expect(summary.expired_count).toBe(0);
    const u1 = summary.members.find((m) => m.user_id === "u-1")!;
    const u2 = summary.members.find((m) => m.user_id === "u-2")!;
    expect(u1.status).toBe("renewed_active");
    expect(u1.plan_id).toBe("pro");
    expect(u2.status).toBe("renewed_active");
    expect(u2.is_lifetime).toBe(true);
  });

  it("includes ALL paying subscribers (regular 200 EGP Pro, Kashier, direct Lifetime, B2B) alongside founders", () => {
    const profiles = new Map<string, FounderProfileInput>([
      ["u-founder", { id: "u-founder", email: "f@example.com" }],
      ["u-regular", { id: "u-regular", email: "reg200@example.com" }],
      ["u-life-new", { id: "u-life-new", email: "lifenew@example.com" }],
    ]);

    const summary = summarizeFoundersRetention({
      now,
      profilesById: profiles,
      founderMembers: [{ user_id: "u-founder", joined_at: "2026-10-05T00:00:00Z" }],
      approvedOrders: [
        { user_id: "u-founder", plan_id: "pro", amount_egp: 50, status: "approved", created_at: "2026-10-05T00:00:00Z" },
        { user_id: "u-regular", plan_id: "pro", amount_egp: 200, status: "approved", created_at: "2026-11-10T00:00:00Z" },
        { user_id: "u-life-new", plan_id: "lifetime", amount_egp: 2250, status: "success", provider: "kashier", created_at: "2026-11-12T00:00:00Z" },
      ],
      subscriptions: [
        { user_id: "u-founder", plan_id: "pro", status: "canceled", current_period_end: "2026-11-05T00:00:00Z" },
        { user_id: "u-regular", plan_id: "pro", status: "active", current_period_end: "2026-12-10T00:00:00Z" },
        { user_id: "u-life-new", plan_id: "lifetime", status: "active", current_period_end: "2126-11-12T00:00:00Z" },
      ],
    });

    expect(summary.total_paid_users).toBe(3);
    expect(summary.founders_count).toBe(1);
    expect(summary.non_founder_paid_count).toBe(2);
    expect(summary.active_count).toBe(2);
    expect(summary.total_revenue_egp).toBe(2500);
    expect(summary.cohort_regular.total).toBe(1);
    expect(summary.cohort_lifetime.total).toBe(1);
    expect(summary.members.find((m) => m.user_id === "u-regular")?.is_founder).toBe(false);
    expect(summary.members.find((m) => m.user_id === "u-life-new")?.cohort).toBe("LIFETIME");
  });
});
