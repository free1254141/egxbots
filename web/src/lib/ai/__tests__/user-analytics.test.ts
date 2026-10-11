import { buildDailyActiveUsage, buildUserAnalytics, buildUserUsage } from "../../admin/user-analytics";

describe("admin user analytics", () => {
  const now = new Date("2026-09-23T12:00:00.000Z");

  it("separates active Pro page users from Pro chatbot users", () => {
    const result = buildUserAnalytics({
      now,
      profiles: [{ id: "pro-1" }, { id: "pro-2" }, { id: "free-1" }],
      subscriptions: [
        { user_id: "pro-1", plan_id: "pro", status: "active" },
        { user_id: "pro-2", plan_id: "pro", status: "active" },
      ],
      events: [
        { user_id: "pro-1", event_name: "page_view", path: "/scanner/backtests", created_at: "2026-09-22T10:00:00Z" },
        { user_id: "free-1", event_name: "page_view", path: "/scanner/technical", created_at: "2026-09-22T10:00:00Z" },
      ],
      chatMessages: [
        { user_id: "pro-2", role: "user", created_at: "2026-09-22T11:00:00Z" },
        { user_id: "pro-1", role: "assistant", created_at: "2026-09-22T11:01:00Z" },
      ],
      chatSessions: [{ id: "session-1", user_id: "pro-2" }],
    });
    expect(result.activeProUsers).toBe(2);
    expect(result.proPageUsers).toBe(1);
    expect(result.proChatUsers).toBe(1);
    expect(result.proPageOnlyUsers).toBe(1);
    expect(result.proChatOnlyUsers).toBe(1);
    expect(result.paidConversionRate).toBe(67);
  });

  it("builds a useful per-user usage summary", () => {
    const result = buildUserUsage({
      events: [
        { user_id: "u1", event_name: "page_view", path: "/scanner/ai", created_at: "2026-09-23T10:00:00Z" },
        { user_id: "u1", event_name: "page_view", path: "/scanner/ai", created_at: "2026-09-23T10:01:00Z" },
      ],
      chatMessages: [{ user_id: "u1", role: "user", created_at: "2026-09-23T10:02:00Z" }],
      chatSessions: [{ id: "s1", user_id: "u1" }],
      analytics: [{ intent: "stock_analysis", total_latency_ms: 1000, created_at: "2026-09-23T10:02:01Z" }],
    });
    expect(result.pageViews).toBe(2);
    expect(result.chatMessages).toBe(1);
    expect(result.topPages[0]).toMatchObject({ path: "/scanner/ai", views: 2, users: 1 });
    expect(result.topIntents[0]).toEqual({ intent: "stock_analysis", count: 1 });
  });

  it("counts registered unique users for MAU, WAU, and Cairo-day DAU and returns shares of all users", () => {
    const result = buildUserAnalytics({
      now: new Date("2026-09-23T12:00:00.000Z"),
      profiles: [{ id: "u1" }, { id: "u2" }, { id: "u3" }, { id: "u4" }, { id: "u5" }],
      totalProfileCount: 5,
      subscriptions: [],
      events: [
        { user_id: "u1", event_name: "page_view", path: "/", created_at: "2026-09-23T00:00:00Z" },
        { user_id: "u2", event_name: "page_view", path: "/", created_at: "2026-09-13T12:00:00Z" },
        { user_id: "u5", event_name: "page_view", path: "/", created_at: "2026-09-22T20:59:00Z" },
        { user_id: "orphan", event_name: "page_view", path: "/", created_at: "2026-09-23T10:00:00Z" },
        { user_id: "u4", event_name: "page_view", path: "/", created_at: "2026-09-25T10:00:00Z" },
      ],
      chatMessages: [
        { user_id: "u1", role: "user", created_at: "2026-09-23T10:00:00Z" },
        { user_id: "u3", role: "assistant", created_at: "2026-09-23T10:00:00Z" },
      ],
    });

    expect(result.activeUsers30Days).toBe(3);
    expect(result.activeUsers7Days).toBe(2);
    expect(result.dau).toBe(1);
    expect(result.activeUsers30DaysRate).toBe(60);
    expect(result.activeUsers7DaysRate).toBe(40);
    expect(result.dauRate).toBe(20);
  });

  it("deduplicates daily usage across pages and chat and separates signup-day activity", () => {
    const input = {
      now: new Date("2026-10-11T19:00:00Z"),
      profiles: [
        { id: "new", created_at: "2026-10-10T21:01:00Z" },
        { id: "old", created_at: "2026-10-10T20:59:00Z" },
        { id: "registered-only", created_at: "2026-10-11T10:00:00Z" },
        { id: "admin", created_at: "2026-09-01T00:00:00Z" },
      ],
      excludeUserIds: new Set(["admin"]),
      events: [
        { user_id: "new", event_name: "page_view", created_at: "2026-10-10T21:05:00Z" },
        { user_id: "new", event_name: "page_view", created_at: "2026-10-11T10:00:00Z" },
        { user_id: "old", event_name: "page_view", created_at: "2026-10-10T20:59:30Z" },
        { user_id: "admin", event_name: "page_view", created_at: "2026-10-11T10:00:00Z" },
        { user_id: "orphan", event_name: "page_view", created_at: "2026-10-11T10:00:00Z" },
        { user_id: "registered-only", event_name: "login", created_at: "2026-10-11T10:00:00Z" },
        { user_id: "old", event_name: "page_view", created_at: "2026-10-12T10:00:00Z" },
      ],
      chatMessages: [
        { user_id: "new", role: "user", created_at: "2026-10-11T11:00:00Z" },
        { user_id: "old", role: "user", created_at: "2026-10-11T11:00:00Z" },
        { user_id: "registered-only", role: "assistant", created_at: "2026-10-11T11:00:00Z" },
      ],
    };
    const rows = buildDailyActiveUsage(input);
    expect(rows).toHaveLength(90);
    expect(rows[0].fullDate).toBe("2026-07-14");
    expect(rows.at(-1)).toMatchObject({ fullDate: "2026-10-11", activeUsers: 2, newActiveUsers: 1, returningActiveUsers: 1, unknownSignupUsers: 0 });
    expect(rows.at(-2)).toMatchObject({ fullDate: "2026-10-10", activeUsers: 1, newActiveUsers: 1, returningActiveUsers: 0 });
    expect(rows.at(-3)?.activeUsers).toBe(0);
    const result = buildUserAnalytics({ ...input, subscriptions: [] });
    expect(result.dau).toBe(2);
    expect(result.activeUsers7Days).toBe(2);
    expect(result.dailyActiveUsage).toEqual(rows);
  });

  it("uses Cairo winter midnight and does not guess an unavailable signup date", () => {
    const rows = buildDailyActiveUsage({
      now: new Date("2026-12-01T22:30:00Z"),
      profiles: [{ id: "u1", created_at: "2026-12-01T22:05:00Z" }, { id: "unknown" }],
      events: [{ user_id: "u1", created_at: "2026-12-01T22:10:00Z" }, { user_id: "unknown", created_at: "2026-12-01T22:10:00Z" }],
    });
    expect(rows.at(-1)).toMatchObject({ fullDate: "2026-12-02", activeUsers: 2, newActiveUsers: 1, returningActiveUsers: 0, unknownSignupUsers: 1 });
  });
});
