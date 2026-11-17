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

describe("GET /api/admin/users/founders", () => {
  const uid1 = "11111111-1111-4111-8111-111111111111";
  const uid2 = "22222222-2222-4222-8222-222222222222";
  const uid3 = "33333333-3333-4333-8333-333333333333";

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("returns 401 when requireAdmin rejects", async () => {
    mockRequireAdmin.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 })
    );
    const res = await GET(new NextRequest("http://localhost/api/admin/users/founders"));
    expect(res.status).toBe(401);
  });

  it("paginates founders_offer_members/orders/listUsers, ignores non-UUID order IDs, queries chunked subscriptions, and sets private no-store cache header", async () => {
    mockRequireAdmin.mockResolvedValueOnce({ user: { id: "admin" } });

    const inCalls: Array<{ table: string; ids: string[] }> = [];
    const listUsersPages: number[] = [];

    const fullPage = Array.from({ length: 1000 }, (_, i) => ({
      user_id: i === 0 ? uid1 : `33333333-3333-4333-8333-${String(i).padStart(12, "0")}`,
      joined_at: "2026-10-15T10:00:00Z",
    }));

    const supabaseMock = {
      from: (table: string) => {
        if (table === "founders_offer_members") {
          return {
            select: () => ({
              order: () => ({
                range: async (from: number) => ({
                  data: from === 0 ? fullPage.slice(0, 1) : [], // quick test with < 1000 batch too
                  error: null,
                }),
              }),
            }),
          };
        }
        if (table === "local_payment_orders") {
          return {
            select: () => ({
              eq: () => ({
                order: () => ({
                  range: async () => ({
                    data: [
                      { user_id: uid1, plan_id: "pro", amount_egp: 50, status: "approved", created_at: "2026-10-15T10:00:00Z" },
                      { user_id: uid2, plan_id: "pro", amount_egp: 200, status: "approved", created_at: "2026-11-05T10:00:00Z" },
                      { user_id: "not-a-uuid", plan_id: "pro", amount_egp: 50, status: "approved", created_at: "2026-11-05T10:00:00Z" },
                    ],
                    error: null,
                  }),
                }),
              }),
            }),
          };
        }
        if (table === "kashier_payments") {
          return {
            select: () => ({
              in: () => ({
                order: () => ({
                  range: async () => ({
                    data: [
                      { user_id: uid3, plan_id: "pro", amount_paid: 200, provider: "kashier", status: "success", paid_at: "2026-11-14T10:00:00Z", created_at: "2026-11-14T10:00:00Z" },
                    ],
                    error: null,
                  }),
                }),
              }),
            }),
          };
        }
        if (table === "profiles") {
          return {
            select: () => ({
              in: async (_col: string, ids: string[]) => {
                inCalls.push({ table: "profiles", ids });
                return {
                  data: ids.map((id) => ({ id, whatsapp_number: "01000000000", telegram_chat_id: "999" })),
                  error: null,
                };
              },
            }),
          };
        }
        if (table === "subscriptions") {
          return {
            select: () => ({
              in: (_col: string, ids: string[]) => {
                inCalls.push({ table: "subscriptions", ids });
                return {
                  range: async () => ({
                    data: [
                      { user_id: uid1, plan_id: "pro", status: "canceled", current_period_end: "2026-11-15T10:00:00Z" },
                      { user_id: uid2, plan_id: "pro", status: "active", current_period_end: "2026-12-05T10:00:00Z" },
                    ],
                    error: null,
                  }),
                };
              },
            }),
          };
        }
        throw new Error(`Unexpected table: ${table}`);
      },
      auth: {
        admin: {
          listUsers: async ({ page }: { page: number }) => {
            listUsersPages.push(page);
            if (page === 1) {
              const pageOneUsers = Array.from({ length: 1000 }, (_, i) => ({
                id: i === 0 ? uid1 : `44444444-4444-4444-8444-${String(i).padStart(12, "0")}`,
                email: i === 0 ? "one@example.com" : `filler${i}@example.com`,
                app_metadata: {},
                user_metadata: {},
              }));
              return { data: { users: pageOneUsers }, error: null };
            }
            return {
              data: {
                users: [
                  { id: uid2, email: "two@example.com", app_metadata: {}, user_metadata: {} },
                  { id: uid3, email: "three.kashier@example.com", app_metadata: {}, user_metadata: {} },
                ],
              },
              error: null,
            };
          },
        },
      },
    };

    mockGetSupabaseServiceClient.mockReturnValue(supabaseMock);

    const res = await GET(new NextRequest("http://localhost/api/admin/users/founders"));
    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toBe("private, no-store, max-age=0");

    const body = await res.json();
    expect(body.total_founders).toBe(3);
    expect(body.total_paid_users).toBe(3);
    expect(body.founders_count).toBe(1);
    expect(body.non_founder_paid_count).toBe(2);
    expect(body.active_count).toBe(1);
    expect(body.expired_count).toBe(2);
    expect(listUsersPages).toEqual([1, 2]);
    expect(inCalls.find((c) => c.table === "profiles")?.ids).toEqual([uid1, uid2, uid3]);
    expect(inCalls.find((c) => c.table === "subscriptions")?.ids).toEqual([uid1, uid2, uid3]);
    expect(body.members.map((m: any) => m.email).sort()).toEqual([
      "one@example.com",
      "three.kashier@example.com",
      "two@example.com",
    ]);
  });

  it("returns 500 when auth.admin.listUsers fails instead of returning partial metrics", async () => {
    mockRequireAdmin.mockResolvedValueOnce({ user: { id: "admin" } });
    mockGetSupabaseServiceClient.mockReturnValue({
      from: (table: string) => {
        if (table === "founders_offer_members") {
          return {
            select: () => ({ order: () => ({ range: async () => ({ data: [{ user_id: uid1, joined_at: "2026-10-15T10:00:00Z" }], error: null }) }) }),
          };
        }
        if (table === "local_payment_orders") {
          return {
            select: () => ({ eq: () => ({ order: () => ({ range: async () => ({ data: [], error: null }) }) }) }),
          };
        }
        if (table === "kashier_payments") {
          return {
            select: () => ({ in: () => ({ order: () => ({ range: async () => ({ data: [], error: null }) }) }) }),
          };
        }
        if (table === "profiles") {
          return { select: () => ({ in: async () => ({ data: [], error: null }) }) };
        }
        if (table === "subscriptions") {
          return { select: () => ({ in: () => ({ range: async () => ({ data: [], error: null }) }) }) };
        }
        throw new Error(table);
      },
      auth: {
        admin: {
          listUsers: async () => ({ data: null, error: { message: "Auth timeout" } }),
        },
      },
    });

    const res = await GET(new NextRequest("http://localhost/api/admin/users/founders"));
    expect(res.status).toBe(500);
  });
});
