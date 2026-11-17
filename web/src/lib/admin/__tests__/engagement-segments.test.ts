import { summarizeUsersEngagement } from "@/lib/admin/engagement-segments";

describe("summarizeUsersEngagement", () => {
  const now = new Date("2026-11-16T10:00:00Z");

  it("segments chat, recommendations, active subscribers, paid ever, excludes admins, and checks 350/month cap", () => {
    const summary = summarizeUsersEngagement({
      now,
      users: [
        { id: "u-both-sub", email: "both.sub@example.com", display_name: "Both Sub" },
        { id: "u-chat-only", email: "chat.only@example.com", display_name: "Chat Only" },
        { id: "u-recs-only", email: "recs.only@example.com", display_name: "Recs Only" },
        { id: "u-passive", email: "passive@example.com", display_name: null },
        { id: "ba9c27e8-f62d-452f-8a29-dc77fd092207", email: "weeessd57@gmail.com" }, // admin excluded
        { id: "u-test", email: "test1@gmail.com" }, // admin/test email excluded
      ],
      chatbotLimits: [
        { user_id: "u-both-sub", date: "2026-11-05", chat_count: 100 },
        { user_id: "u-both-sub", date: "2026-11-10", chat_count: 72 }, // 172 in 2026-11
        { user_id: "u-both-sub", date: "2026-10-15", chat_count: 40 }, // previous month -> not added to Nov
        { user_id: "ba9c27e8-f62d-452f-8a29-dc77fd092207", date: "2026-11-01", chat_count: 999 }, // admin excluded
      ],
      chatMessages: [
        { user_id: "u-chat-only", created_at: "2026-11-12T10:00:00Z" },
      ],
      activityEvents: [
        { user_id: "u-recs-only", event_name: "page_view", path: "/scanner/technical" },
        { user_id: "u-both-sub", event_name: "feature_use", path: "/scanner/backtests?tab=similarity" },
        { user_id: "u-passive", event_name: "page_view", path: "/" },
      ],
      botSubscriptionUserIds: [],
      proTelegramInviteUserIds: [],
      scannerPositionUserIds: [],
      subscriptions: [
        { user_id: "u-both-sub", plan_id: "pro", status: "active", current_period_end: "2026-12-01T00:00:00Z" },
        { user_id: "u-chat-only", plan_id: "pro", status: "trialing", current_period_end: "2026-11-18T00:00:00Z" },
      ],
      paidEverUserIds: ["u-both-sub", "u-recs-only"],
    });

    expect(summary.total_users).toBe(4);
    expect(summary.subscribers.active_paid_count).toBe(1);
    expect(summary.subscribers.active_paid_pct).toBe(25);
    expect(summary.subscribers.paid_ever_count).toBe(2);
    expect(summary.subscribers.paid_ever_pct).toBe(50);
    expect(summary.subscribers.active_trial_count).toBe(1);

    expect(summary.interests.chat_messaged_count).toBe(2);
    expect(summary.interests.chat_interested_count).toBe(2);
    expect(summary.interests.chat_interested_pct).toBe(50);
    expect(summary.interests.recs_interested_count).toBe(2);
    expect(summary.interests.recs_interested_pct).toBe(50);

    expect(summary.overlap.both_count).toBe(1);
    expect(summary.overlap.chat_only_count).toBe(1);
    expect(summary.overlap.recs_only_count).toBe(1);
    expect(summary.overlap.neither_count).toBe(1);

    expect(summary.chat_limit_350.hit_350_months_count).toBe(0);
    expect(summary.chat_limit_350.max_month_chats_ever).toBe(172);
    expect(summary.chat_limit_350.max_month_leader?.user_id).toBe("u-both-sub");
    expect(summary.chat_limit_350.max_month_leader?.month).toBe("2026-11");
    expect(summary.chat_limit_350.top_monthly_chatters[0].all_time_chats).toBe(212);
    expect(summary.chat_limit_350.approached_150_users_count).toBe(1);
  });

  it("detects when a non-admin user reaches or exceeds 350 chats in one month", () => {
    const summary = summarizeUsersEngagement({
      now,
      users: [{ id: "u-heavy", email: "heavy@example.com" }],
      chatbotLimits: [
        { user_id: "u-heavy", date: "2026-11-01", chat_count: 200 },
        { user_id: "u-heavy", date: "2026-11-20", chat_count: 155 },
      ],
      chatMessages: [],
      activityEvents: [],
      subscriptions: [],
    });

    expect(summary.chat_limit_350.hit_350_months_count).toBe(1);
    expect(summary.chat_limit_350.users_ever_hit_350_count).toBe(1);
    expect(summary.chat_limit_350.max_month_chats_ever).toBe(355);
    const capBucket = summary.chat_limit_350.peak_buckets.find((b) => b.id === "350_plus");
    expect(capBucket?.count).toBe(1);
  });
});
