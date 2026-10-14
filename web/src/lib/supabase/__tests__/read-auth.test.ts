/** @jest-environment node */
import { readAccessToken } from "../read-session";
import { createSupabaseServerClient } from "../server";
import { createClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";
jest.mock("@supabase/supabase-js", () => ({ createClient: jest.fn() }));
jest.mock("next/headers", () => ({ cookies: jest.fn() }));
const store = (raw: string) => ({
  get: (name: string) =>
    name === "sb-project-auth-token" ? { value: raw } : undefined,
});
describe("read-only server credentials", () => {
  const oldEnv = { ...process.env };
  beforeEach(() => {
    jest.clearAllMocks();
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "public-key";
  });
  afterEach(() => {
    process.env = { ...oldEnv };
  });
  test("decodes chunked SSR cookies without exposing refresh credential", () => {
    const raw =
      "base64-" +
      Buffer.from(
        JSON.stringify({
          access_token: "credential",
          refresh_token: "never-read",
          user: { id: "unverified" },
        }),
      ).toString("base64url");
    expect(
      readAccessToken(
        {
          get: (name) =>
            name === "sb-project-auth-token.0"
              ? { value: raw.slice(0, 40) }
              : name === "sb-project-auth-token.1"
                ? { value: raw.slice(40) }
                : undefined,
        },
        "https://project.supabase.co",
      ),
    ).toBe("credential");
    expect(
      readAccessToken(store("garbage"), "https://project.supabase.co"),
    ).toBeNull();
  });
  test("verifies cookie identity before returning forwarding session; no SSR refresh or write", async () => {
    const getUser = jest
      .fn()
      .mockResolvedValue({
        data: { user: { id: "verified-owner" } },
        error: null,
      });
    const refreshSession = jest.fn();
    (createClient as jest.Mock).mockReturnValue({
      auth: { getUser, getSession: jest.fn(), refreshSession },
    });
    (cookies as jest.Mock).mockResolvedValue(
      store(
        JSON.stringify({
          access_token: "access",
          refresh_token: "refresh",
          user: { id: "attacker-cookie" },
        }),
      ),
    );
    const client = await createSupabaseServerClient();
    const [{ data: identity }, { data: session }] = await Promise.all([
      client.auth.getUser(),
      client.auth.getSession(),
    ]);
    expect(identity.user?.id).toBe("verified-owner");
    expect(session.session?.user.id).toBe("verified-owner");
    expect(session.session?.refresh_token).toBe("");
    expect(getUser).toHaveBeenCalledTimes(1);
    expect(getUser).toHaveBeenCalledWith("access");
    expect(refreshSession).not.toHaveBeenCalled();
    expect(createClient).toHaveBeenCalledWith(
      "https://project.supabase.co",
      "public-key",
      expect.objectContaining({
        auth: {
          persistSession: false,
          autoRefreshToken: false,
          detectSessionInUrl: false,
        },
        global: { headers: { Authorization: "Bearer access" } },
      }),
    );
  });
  test("rejects forged cookie identity and prefers explicit bearer without reading cookies", async () => {
    const getUser = jest
      .fn()
      .mockResolvedValue({
        data: { user: null },
        error: { message: "invalid token" },
      });
    (createClient as jest.Mock).mockReturnValue({
      auth: { getUser, getSession: jest.fn() },
    });
    const client = await createSupabaseServerClient({
      headers: { get: () => "Bearer forged" },
    } as any);
    expect((await client.auth.getSession()).data.session).toBeNull();
    expect(getUser).toHaveBeenCalledWith("forged");
    expect(cookies).not.toHaveBeenCalled();
  });
});
