import { NextRequest } from "next/server";
import crypto from "node:crypto";
import { GET, POST } from "../route";

const mockInsert = jest.fn();
const mockMaybeSingle = jest.fn();

jest.mock("@/lib/supabase/route-data", () => ({
  getSupabaseServiceClient: jest.fn(() => ({
    from: jest.fn((table: string) => {
      if (table === "marketing_message_log") {
        return {
          select: jest.fn().mockReturnThis(),
          eq: jest.fn().mockReturnThis(),
          order: jest.fn().mockReturnThis(),
          limit: jest.fn().mockReturnThis(),
          maybeSingle: mockMaybeSingle,
        };
      }
      if (table === "marketing_events") {
        return {
          insert: mockInsert.mockResolvedValue({ error: null }),
        };
      }
      return {};
    }),
  })),
}));

const savedEnv = { ...process.env };

beforeEach(() => {
  jest.clearAllMocks();
  process.env = {
    ...savedEnv,
    RESEND_WEBHOOK_SECRET: "whsec_dGVzdHNlY3JldDEyMzQ1Njc4OTA=",
  };
});

afterAll(() => {
  process.env = savedEnv;
});

function signPayload(body: string, svixId: string, timestamp: string, secret: string) {
  const key = Buffer.from(secret.startsWith("whsec_") ? secret.slice(6) : secret, "base64");
  const sig = crypto.createHmac("sha256", key).update(`${svixId}.${timestamp}.${body}`).digest("base64");
  return `v1,${sig}`;
}

describe("Resend Webhook Route", () => {
  it("returns status from GET endpoint", async () => {
    const res = await GET();
    const data = await res.json();
    expect(res.status).toBe(200);
    expect(data.ok).toBe(true);
    expect(data.configured).toBe(true);
  });

  it("rejects unauthorized webhook when signature is missing", async () => {
    const req = new NextRequest("https://egxbots.com/api/marketing/resend-webhook", {
      method: "POST",
      body: JSON.stringify({ type: "email.opened" }),
    });
    const res = await POST(req);
    expect(res.status).toBe(401);
  });

  it("processes signed email.opened webhook and logs event into marketing_events", async () => {
    const payload = JSON.stringify({
      type: "email.opened",
      data: {
        email_id: "resend-msg-123",
        to: ["trader@example.com"],
      },
    });

    const svixId = "msg_test_123";
    const svixTs = Math.floor(Date.now() / 1000).toString();
    const svixSig = signPayload(payload, svixId, svixTs, process.env.RESEND_WEBHOOK_SECRET!);

    mockMaybeSingle.mockResolvedValueOnce({
      data: {
        id: "log-uuid-1",
        user_id: "user-uuid-1",
        message_type: "founders_offer",
      },
    });

    const req = new NextRequest("https://egxbots.com/api/marketing/resend-webhook", {
      method: "POST",
      headers: {
        "svix-id": svixId,
        "svix-timestamp": svixTs,
        "svix-signature": svixSig,
      },
      body: payload,
    });

    const res = await POST(req);
    const data = await res.json();
    expect(res.status).toBe(200);
    expect(data.ok).toBe(true);
    expect(data.tracked).toBe("opened");

    expect(mockInsert).toHaveBeenCalledWith(
      expect.objectContaining({
        event_type: "opened",
        channel: "email",
        campaign: "founders_offer",
        message_id: "log-uuid-1",
        provider_message_id: "resend-msg-123",
        user_id: "user-uuid-1",
        svix_id: svixId,
      })
    );
  });
});
