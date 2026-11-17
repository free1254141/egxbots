/** @jest-environment node */

import { NextRequest } from "next/server";
import { GET } from "../route";

const mockRequireAdmin = jest.fn();
const mockGetSupabaseServiceClient = jest.fn();

jest.mock("@/lib/admin-auth", () => ({
  requireAdmin: (...args: any[]) => mockRequireAdmin(...args),
}));

jest.mock("@/lib/supabase/route-data", () => ({
  getSupabaseServiceClient: () => mockGetSupabaseServiceClient(),
}));

describe("GET /api/admin/users/engagement", () => {
  const uid1 = "11111111-1111-4111-8111-111111111111";
  const uid2 = "22222222-2222-4222-8222-222222222222";
  const adminUid = "99999999-9999-4999-8999-999999999999";

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("returns 401 when requireAdmin rejects", async () => {
    mockRequireAdmin.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 })
    );
    const res = await GET(new NextRequest("http://localhost/api/admin/users/engagement"));
    expect(res.status).toBe(401);
  });

  it("aggregates engagement segments, excludes app_metadata admin, checks 350/mo, and sets private no-store header", async () => {
    mockRequireAdmin.mockResolvedValueOnce({ user: { id: "admin" } });

    const rangeResult = (rows: any[]) => ({
      range: async (from: number) => ({ data: from === 0 ? rows : [], error: null }),
    });

    mockGetSupabaseServiceClient.mockReturnValue({
      auth: {
        admin: {
          listUsers: async () => ({
            data: {
              users: [
                { id: uid1, email: "heavy@example.com", app_metadata: {}, user_metadata: { full_name: "Heavy" } },
                { id: uid2, email: "scanner@example.com", app_metadata: {}, user_metadata: {} },
                { id: adminUid, email: "staff@example.com", app_metadata: { role: "admin" }, user_metadata: {} },
              ],
            },
            error: null,
          }),
        },
      },
      from: (table: string) => {
        if (table === "profiles") {
          return { select: () => rangeResult([{ id: uid1, display_name: "Heavy" }, { id: uid2 }, { id: adminUid }]) };
        }
        if (table === "ai_chatbot_limits") {
          return {
            select: () =>
              rangeResult([
                { user_id: uid1, date: "2026-11-05", chat_count: 172 },
                { user_id: adminUid, date: "2026-11-05", chat_count: 500 }, // excluded admin
              ]),
          };
        }
        if (table === "ai_chat_messages") {
          return {
            select: () => ({
              eq: () => rangeResult([{ user_id: uid1, created_at: "2026-11-05T10:00:00Z" }]),
            }),
          };
        }
        if (table === "user_activity_events") {
          return {
            select: () => ({
              not: () =>
                rangeResult([
                  { user_id: uid2, event_name: "page_view", path: "/scanner/technical" },
                ]),
            }),
          };
        }
        if (table === "subscriptions") {
          return {
            select: () =>
              rangeResult([
                { user_id: uid1, plan_id: "pro", status: "active", current_period_end: "2099-12-01T00:00:00Z" },
              ]),
          };
        }
        if (table === "positions") {
          return { select: () => ({ eq: () => rangeResult([]) }) };
        }
        if (table === "local_payment_orders") {
          return { select: () => ({ eq: () => rangeResult([{ user_id: uid1 }]) }) };
        }
        if (table === "kashier_payments") {
          return { select: () => ({ in: () => rangeResult([]) }) };
        }
        return { select: () => rangeResult([]) };
      },
    });

    const res = await GET(new NextRequest("http://localhost/api/admin/users/engagement"));
    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toBe("private, no-store, max-age=0");

    const body = await res.json();
    expect(body.total_users).toBe(2);
    expect(body.subscribers.active_paid_count).toBe(1);
    expect(body.interests.chat_interested_count).toBe(1);
    expect(body.interests.recs_interested_count).toBe(1);
    expect(body.chat_limit_350.hit_350_months_count).toBe(0);
    expect(body.chat_limit_350.max_month_chats_ever).toBe(172);
  });
});
