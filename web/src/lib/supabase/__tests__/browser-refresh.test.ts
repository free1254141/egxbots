import { createBrowserClient } from "@supabase/ssr";
import { createSupabaseBrowserClient } from "../browser";
jest.mock("@supabase/ssr", () => ({ createBrowserClient: jest.fn() }));
test("concurrent browser rotations share one operation and clear after settlement", async () => {
  const oldEnv = { ...process.env };
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "public";
  try {
    let resolve!: (value: any) => void;
    const refresh = jest.fn().mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    const sdk = {
      auth: { refreshSession: refresh, onAuthStateChange: jest.fn() },
    };
    (createBrowserClient as jest.Mock).mockReturnValue(sdk);
    const client = createSupabaseBrowserClient();
    expect(createSupabaseBrowserClient()).toBe(client);
    const first = client.auth.refreshSession(),
      second = client.auth.refreshSession();
    expect(first).toBe(second);
    expect(refresh).toHaveBeenCalledTimes(1);
    resolve({ data: { session: null }, error: null });
    await Promise.all([first, second]);
    const third = client.auth.refreshSession();
    expect(refresh).toHaveBeenCalledTimes(2);
    resolve({ data: { session: null }, error: null });
    await third;
  } finally {
    process.env = { ...oldEnv };
  }
});
test("refresh failure clears the shared operation for a later explicit retry", async () => {
  const oldEnv = { ...process.env };
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "public";
  try {
    const refresh = jest
      .fn()
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValue({ data: { session: null }, error: null });
    (createBrowserClient as jest.Mock).mockReturnValue({
      auth: { refreshSession: refresh, onAuthStateChange: jest.fn() },
    });
    const client = createSupabaseBrowserClient();
    const first = client.auth.refreshSession();
    await expect(first).rejects.toThrow("network");
    await client.auth.refreshSession();
    expect(refresh).toHaveBeenCalledTimes(2);
  } finally {
    process.env = { ...oldEnv };
  }
});
test("identity transitions separate pending rotations and reject former-account results", async () => {
  const oldEnv = { ...process.env };
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "public";
  try {
    let notify!: (event: string, session: any) => void;
    const completions: ((value: any) => void)[] = [];
    const refresh = jest
      .fn()
      .mockImplementation(() => new Promise((done) => completions.push(done)));
    (createBrowserClient as jest.Mock).mockReturnValue({
      auth: {
        refreshSession: refresh,
        onAuthStateChange: (callback: any) => {
          notify = callback;
        },
      },
    });
    const client = createSupabaseBrowserClient();
    notify("SIGNED_IN", { user: { id: "A" } });
    const old = client.auth.refreshSession();
    notify("TOKEN_REFRESHED", { user: { id: "A" } });
    expect(client.auth.refreshSession()).toBe(old);
    notify("SIGNED_OUT", null);
    notify("SIGNED_IN", { user: { id: "B" } });
    const current = client.auth.refreshSession();
    expect(current).not.toBe(old);
    expect(refresh).toHaveBeenCalledTimes(2);
    completions[0]({
      data: { session: { user: { id: "A" } }, user: { id: "A" } },
      error: null,
    });
    expect((await old).data.session).toBeNull();
    completions[1]({
      data: { session: { user: { id: "B" } }, user: { id: "B" } },
      error: null,
    });
    expect((await current).data.session?.user.id).toBe("B");
  } finally {
    process.env = { ...oldEnv };
  }
});
