/** @jest-environment node */

import { NextRequest } from "next/server";
import { GET } from "../route";

const mockRequireAdmin = jest.fn();
const mockGetSupabaseServiceClient = jest.fn();

jest.mock("@/lib/admin-auth", () => ({
  requireAdmin: (...args: any[]) => mockRequireAdmin(...args),
}));

jest.mock("@/lib/supabase/route-data", () => ({
  getSupabaseClient: () => mockGetSupabaseServiceClient(),
  getSupabaseServiceClient: () => mockGetSupabaseServiceClient(),
}));

describe("GET /api/admin/users/[userId]", () => {
  const uid = "c634fe18-9e6f-4f35-b2aa-1fa7a22ad78d";

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("returns 401 when requireAdmin rejects and 400 on invalid UUID", async () => {
    mockRequireAdmin.mockResolvedValueOnce(new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 }));
    const unauth = await GET(new NextRequest(`http://localhost/api/admin/users/${uid}`), {
      params: Promise.resolve({ userId: uid }),
    });
    expect(unauth.status).toBe(401);

    mockRequireAdmin.mockResolvedValueOnce({ user: { id: "admin" } });
    const badId = await GET(new NextRequest("http://localhost/api/admin/users/bad-id"), {
      params: Promise.resolve({ userId: "bad-id" }),
    });
    expect(badId.status).toBe(400);
  });

  it("returns bounded usage, preferred subscription, recentQuestions, and telegram/email notifications with private no-store header", async () => {
    mockRequireAdmin.mockResolvedValueOnce({ user: { id: "admin" } });

    const builder = (result: any) => {
      const chain: any = {
        select: () => chain,
        eq: () => chain,
        order: () => chain,
        limit: async () => result,
        single: async () => result,
      };
      return chain;
    };

    const tableData: Record<string, any> = {
      profiles: { data: { id: uid, display_name: "Founder", telegram_chat_id: "8893903002" }, error: null },
      subscriptions: {
        data: [
          { id: "s1", user_id: uid, plan_id: "pro", status: "canceled", current_period_end: "2026-11-13T18:57:53Z" },
        ],
        error: null,
      },
      bot_subscriptions: { data: [], error: null },
      positions: { data: [], error: null },
      user_activity_events: {
        data: [
          { user_id: uid, event_name: "page_view", path: "/pricing", created_at: "2026-11-07T16:12:52Z" },
          { user_id: uid, event_name: "page_view", path: "/chat", created_at: "2026-11-07T16:14:26Z" },
          { user_id: uid, event_name: "page_view", path: "/pricing", created_at: "2026-10-15T10:00:00Z" },
        ],
        error: null,
      },
      ai_chat_messages: {
        data: [
          { user_id: uid, role: "assistant", content: "reply", created_at: "2026-11-07T16:15:01Z" },
          { user_id: uid, role: "user", content: "هات كل التوصيات المفتوحه", created_at: "2026-11-07T16:14:59Z" },
        ],
        error: null,
      },
      ai_chat_sessions: { data: [{ id: "sess1", user_id: uid }], error: null },
      ai_analytics: { data: [], error: null },
      local_payment_orders: {
        data: [
          { plan_id: "pro", amount_egp: 50, status: "approved", provider: "easykash", created_at: "2026-10-14T18:55:50Z" },
          { plan_id: "pro", amount_egp: 50, status: "pending", provider: "easykash", created_at: "2026-10-14T18:54:51Z" },
        ],
        error: null,
      },
      ai_chatbot_limits: {
        data: [
          { date: "2026-11-10", chat_count: 4 },
          { date: "2026-10-15", chat_count: 10 },
        ],
        error: null,
      },
      chat_bonus_credits: {
        data: [{ source: "telegram_link", credits_granted: 10, credits_used: 0 }],
        error: null,
      },
      telegram_subscription_reminder_log: {
        data: [{ reminder_days: 3, status: "failed", error: "HTTP 403", created_at: "2026-11-10T08:08:00Z" }],
        error: null,
      },
      marketing_message_log: {
        data: [{ id: "m1", message_type: "pro_session_report", channel: "email", status: "sent", sent_at: "2026-11-03T16:38:19Z", provider_message_id: "p1" }],
        error: null,
      },
      marketing_events: {
        data: [
          { message_id: "m1", provider_message_id: "p1", event_type: "delivered", created_at: "2026-11-03T16:38:21Z" },
          { message_id: "m1", provider_message_id: "p1", event_type: "opened", created_at: "2026-11-03T17:45:35Z" },
        ],
        error: null,
      },
    };

    mockGetSupabaseServiceClient.mockReturnValue({
      from: (table: string) => builder(tableData[table]),
    });

    const res = await GET(new NextRequest(`http://localhost/api/admin/users/${uid}`), {
      params: Promise.resolve({ userId: uid }),
    });
    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toBe("private, no-store, max-age=0");

    const body = await res.json();
    expect(body.usage.activeDays).toBe(2);
    expect(body.usage.totalQuotaChats).toBe(14);
    expect(body.usage.bonusCreditsRemaining).toBe(10);
    expect(body.usage.recentQuestions).toHaveLength(1);
    expect(body.usage.recentQuestions[0].content).toBe("هات كل التوصيات المفتوحه");
    expect(body.notifications.telegramReminders[0].error).toBe("HTTP 403");
    expect(body.notifications.emailLogs[0].opened).toBe(true);
    expect(body.payments.successful).toBe(1);
    expect(body.payments.totalPaid).toBe(50);
  });
});
