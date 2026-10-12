import { NextRequest } from "next/server";
import { POST } from "../../app/api/portfolio/transactions/route";
import { createSupabaseServerClient } from "../supabase/server";
jest.mock("../supabase/server", () => ({
  createSupabaseServerClient: jest.fn(),
}));
const rpc = jest.fn();
const payload = {
  action: "withdraw",
  amount: 10,
  fees: 0,
  occurredAt: "2026-10-01T10:00:00Z",
  requestId: "12345678-1234-1234-1234-123456789012",
  user_id: "victim",
};
const request = () =>
  new NextRequest("http://localhost/api/portfolio/transactions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
beforeEach(() => {
  rpc.mockReset();
  (createSupabaseServerClient as jest.Mock).mockResolvedValue({
    auth: {
      getUser: async () => ({
        data: { user: { id: "free-owner", app_metadata: {} } },
        error: null,
      }),
    },
    rpc,
  });
});
it("allows authenticated Free users and lets the database derive ownership, never passing user_id", async () => {
  rpc.mockResolvedValue({ data: { ok: true }, error: null });
  const r = await POST(request());
  expect(r.status).toBe(200);
  expect(rpc.mock.calls[0][1]).not.toHaveProperty("user_id");
  expect(r.headers.get("Cache-Control")).toContain("private");
});
it("rejects anonymous requests without calling the ledger", async () => {
  (createSupabaseServerClient as jest.Mock).mockResolvedValue({
    auth: { getUser: async () => ({ data: { user: null }, error: null }) },
    rpc,
  });
  expect((await POST(request())).status).toBe(401);
  expect(rpc).not.toHaveBeenCalled();
});
it("does not report successful bookkeeping when the migration or RPC is unavailable", async () => {
  rpc.mockResolvedValue({
    data: null,
    error: { message: "function not found" },
  });
  const r = await POST(request());
  expect(r.status).toBe(503);
  expect((await r.json()).ok).toBe(false);
});
