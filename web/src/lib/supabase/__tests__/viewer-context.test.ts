let mockSubscriptionRows: Array<{
  plan_id: string;
  status: string;
  current_period_end: string;
}> = [];
let mockSubscriptionError: unknown = null;
let mockSubscriptionLookups = 0;
let mockIdentityLookups = 0;
let mockIdentityError: unknown = null;
const mockPlanEq = jest.fn();
const mockPlanOrder = jest.fn();
const mockPlanLimit = jest.fn();

jest.mock("@supabase/ssr", () => ({
  createServerClient: () => ({
    auth: {
      getSession: async () => ({
        data: { session: { access_token: "test-token" } },
      }),
    },
  }),
}));

jest.mock("@supabase/supabase-js", () => ({
  createClient: (_url: string, _key: string, options: any) => {
    if (options?.global?.headers?.Authorization) {
      return {
        auth: {
          getUser: async (token: string) => {
            mockIdentityLookups++;
            return {
              data: {
                user: {
                  id: token === "bAsuffix8" ? "second-user" : "test-user",
                },
              },
              error: mockIdentityError,
            };
          },
        },
      };
    }
    return {
      from: () => ({
        select: () => {
          const chain: any = {
            eq: mockPlanEq,
            order: mockPlanOrder,
            limit: mockPlanLimit,
          };
          mockPlanEq.mockReturnValue(chain);
          mockPlanOrder.mockReturnValue(chain);
          mockPlanLimit.mockImplementation(async () => {
            mockSubscriptionLookups += 1;
            return {
              data: mockSubscriptionRows,
              error: mockSubscriptionError,
            };
          });
          return chain;
        },
      }),
    };
  },
}));

const request = {
  headers: { get: () => null },
  cookies: {
    get: (name: string) =>
      name === "sb-example-auth-token"
        ? { value: JSON.stringify({ access_token: "test-token" }) }
        : undefined,
  },
} as any;

describe("viewer plan freshness", () => {
  const oldEnv = { ...process.env };

  beforeEach(() => {
    jest.resetModules();
    jest.useFakeTimers().setSystemTime(new Date("2026-09-27T12:00:00Z"));
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "test-anon";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "test-service";
    process.env.NEXT_PUBLIC_PAYMENTS_ENABLED = "true";
    mockSubscriptionRows = [];
    mockSubscriptionError = null;
    mockSubscriptionLookups = 0;
    mockIdentityLookups = 0;
    mockIdentityError = null;
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.useRealTimers();
    process.env = { ...oldEnv };
  });

  it("refreshes a previously Free user within one minute after activation", async () => {
    const { getViewerContext } = await import("../viewer-context");
    expect((await getViewerContext(request)).pro).toBe(false);
    mockSubscriptionRows = [
      {
        plan_id: "pro",
        status: "active",
        current_period_end: "2026-10-27T00:00:00Z",
      },
    ];
    expect((await getViewerContext(request)).pro).toBe(false);
    expect(mockSubscriptionLookups).toBe(1);

    jest.advanceTimersByTime(61_000);
    expect((await getViewerContext(request)).pro).toBe(true);
    expect(mockSubscriptionLookups).toBe(2);
    expect(mockPlanEq).toHaveBeenCalledWith("user_id", "test-user");
    expect(mockPlanEq).toHaveBeenCalledWith("status", "active");
    expect(mockPlanOrder).toHaveBeenCalledWith("current_period_end", {
      ascending: false,
      nullsFirst: true,
    });
    expect(mockPlanLimit).toHaveBeenCalledWith(20);
  });

  it("does not cache Free when the subscription lookup failed", async () => {
    const { getViewerContext } = await import("../viewer-context");
    mockSubscriptionError = { code: "PGRST000" };
    expect((await getViewerContext(request)).pro).toBe(false);
    mockSubscriptionError = null;
    mockSubscriptionRows = [
      {
        plan_id: "pro",
        status: "active",
        current_period_end: "2026-10-27T00:00:00Z",
      },
    ];
    expect((await getViewerContext(request)).pro).toBe(true);
    expect(mockSubscriptionLookups).toBe(2);
  });
  it("verifies identity before private plan reads and deduplicates concurrent views", async () => {
    const { getViewerContext } = await import("../viewer-context");
    mockIdentityError = { message: "invalid" };
    expect((await getViewerContext(request)).authenticated).toBe(false);
    expect(mockSubscriptionLookups).toBe(0);
    mockIdentityError = null;
    await Promise.all([
      getViewerContext(request),
      getViewerContext(request),
      getViewerContext(request),
    ]);
    expect(mockIdentityLookups).toBe(2);
    expect(mockSubscriptionLookups).toBe(1);
  });
  it("SHA256 token identity separates collisions from the former short hash", async () => {
    const { getViewerContext } = await import("../viewer-context");
    const make = (token: string) =>
      ({ headers: { get: () => `Bearer ${token}` } }) as any;
    expect((await getViewerContext(make("absuffix8"))).userId).toBe(
      "test-user",
    );
    expect((await getViewerContext(make("bAsuffix8"))).userId).toBe(
      "second-user",
    );
    expect(mockIdentityLookups).toBe(2);
  });
  it.each(["lifetime", "pro_lifetime"])(
    "preserves active %s without changing free portfolio limits",
    async (plan) => {
      const { getViewerContext } = await import("../viewer-context");
      mockSubscriptionRows = [
        { plan_id: plan, status: "active", current_period_end: "" },
      ];
      expect((await getViewerContext(request)).pro).toBe(true);
      const { planLimits } = await import("@/lib/ai/plan-gate");
      expect(planLimits("free").portfolio_stocks).toBe(5);
    },
  );
  it("never reuses verified identity beyond its access token expiry", async () => {
    const { getViewerContext } = await import("../viewer-context");
    const exp = Math.floor(Date.now() / 1000) + 10;
    const token =
      "header." +
      Buffer.from(JSON.stringify({ exp })).toString("base64url") +
      ".signature";
    const req = { headers: { get: () => `Bearer ${token}` } } as any;
    expect((await getViewerContext(req)).authenticated).toBe(true);
    jest.advanceTimersByTime(11000);
    expect((await getViewerContext(req)).authenticated).toBe(false);
    expect(mockIdentityLookups).toBe(1);
    expect(mockSubscriptionLookups).toBe(1);
  });
});
