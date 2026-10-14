import { NextRequest } from "next/server";
import { cookies } from "next/headers";
import { createClient } from "@supabase/supabase-js";
import { createSupabaseServerClient } from "../supabase/server";

jest.mock("next/headers", () => ({ cookies: jest.fn() }));
jest.mock("@supabase/supabase-js", () => ({ createClient: jest.fn(() => ({ bearerClient: true })) }));

const savedEnv = { ...process.env };
beforeEach(() => {
  jest.clearAllMocks();
  process.env = { ...savedEnv, NEXT_PUBLIC_SUPABASE_URL: "https://example.supabase.co", NEXT_PUBLIC_SUPABASE_ANON_KEY: "legacy-public" };
  delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
});
afterAll(() => { process.env = savedEnv; });

it("awaits Next 15 cookies and decodes access token without refresh writes", async () => {
  const raw =
    "base64-" +
    Buffer.from(
      JSON.stringify({
        access_token: "cookie-access-token",
        refresh_token: "never-read",
        user: { id: "test-user" },
      }),
    ).toString("base64url");
  const store = { get: jest.fn((name) => name === "sb-example-auth-token" ? { value: raw } : undefined) };
  (cookies as jest.Mock).mockResolvedValue(store);
  await createSupabaseServerClient();
  expect(createClient).toHaveBeenCalledWith("https://example.supabase.co", "legacy-public", {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    global: { headers: { Authorization: "Bearer cookie-access-token" } },
  });
  expect(store.get).toHaveBeenCalled();
});

it("uses request cookies without accessing the ambient cookie store", async () => {
  const raw =
    "base64-" +
    Buffer.from(
      JSON.stringify({
        access_token: "request-cookie-token",
        refresh_token: "never-read",
      }),
    ).toString("base64url");
  const request = new NextRequest("https://egxbots.example/api/user/quota", {
    headers: { cookie: `sb-example-auth-token=${raw}` },
  });
  await createSupabaseServerClient(request);
  expect(cookies).not.toHaveBeenCalled();
  expect(createClient).toHaveBeenCalledWith("https://example.supabase.co", "legacy-public", {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    global: { headers: { Authorization: "Bearer request-cookie-token" } },
  });
});

it("uses the user's bearer token and public key, never a privileged credential", async () => {
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "public-new";
  process.env.SUPABASE_SECRET_KEY = "private-test-value";
  await createSupabaseServerClient(new NextRequest("https://egxbots.example/api/user/quota", { headers: { authorization: "Bearer user-token" } }));
  expect(createClient).toHaveBeenCalledWith("https://example.supabase.co", "public-new", {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    global: { headers: { Authorization: "Bearer user-token" } },
  });
  expect(cookies).not.toHaveBeenCalled();
});

it("fails closed when only a service credential is configured", async () => {
  delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
  process.env.SUPABASE_SECRET_KEY = "private-test-value";
  await expect(createSupabaseServerClient()).rejects.toThrow("Missing Supabase environment variables");
  expect(createClient).not.toHaveBeenCalled();
});
