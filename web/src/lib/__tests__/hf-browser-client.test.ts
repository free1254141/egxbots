import {
  HF_DIRECT_ORIGIN,
  hfPublicFetch,
  resetHfBrowserClientForTests,
  shouldUseDirectHf,
} from "@/lib/hf-browser-client";

describe("hf-browser-client", () => {
  const originalFetch = global.fetch;
  const originalWindow = (global as any).window;
  const originalJestWorkerId = process.env.JEST_WORKER_ID;
  const originalDirectEnv = process.env.NEXT_PUBLIC_DIRECT_HF;

  beforeEach(() => {
    resetHfBrowserClientForTests();
    delete process.env.NEXT_PUBLIC_DIRECT_HF;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    if (originalWindow === undefined) {
      delete (global as any).window;
    } else {
      (global as any).window = originalWindow;
    }
    if (originalJestWorkerId === undefined) {
      delete process.env.JEST_WORKER_ID;
    } else {
      process.env.JEST_WORKER_ID = originalJestWorkerId;
    }
    if (originalDirectEnv === undefined) {
      delete process.env.NEXT_PUBLIC_DIRECT_HF;
    } else {
      process.env.NEXT_PUBLIC_DIRECT_HF = originalDirectEnv;
    }
    jest.restoreAllMocks();
  });

  it("uses same-origin fetch in Jest / localhost environments", async () => {
    (global as any).window = { location: { hostname: "localhost" } };
    const fetchMock = jest.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );
    global.fetch = fetchMock as any;

    expect(shouldUseDirectHf()).toBe(false);
    const res = await hfPublicFetch("/api/market/status?market=egx");
    expect(res.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith("/api/market/status?market=egx", undefined);
  });

  it("calls HF directly with credentials: omit on egxbots.com", async () => {
    delete process.env.JEST_WORKER_ID;
    (global as any).window = { location: { hostname: "egxbots.com" } };
    const fetchMock = jest.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true, src: "hf" }), { status: 200 })
    );
    global.fetch = fetchMock as any;

    expect(shouldUseDirectHf()).toBe(true);
    const res = await hfPublicFetch("/api/market/breadth?market=egx");
    expect(await res.json()).toEqual({ ok: true, src: "hf" });
    expect(fetchMock).toHaveBeenCalledWith(
      `${HF_DIRECT_ORIGIN}/api/market/breadth?market=egx`,
      expect.objectContaining({ credentials: "omit" })
    );
  });

  it("deduplicates concurrent GETs and serves subsequent hits from TTL cache", async () => {
    delete process.env.JEST_WORKER_ID;
    (global as any).window = { location: { hostname: "www.egxbots.com" } };
    const fetchMock = jest.fn().mockImplementation(
      async () => new Response(JSON.stringify({ dividends: [1, 2] }), { status: 200 })
    );
    global.fetch = fetchMock as any;

    const [r1, r2] = await Promise.all([
      hfPublicFetch("/api/market/dividends?market=egx", undefined, { cacheTtlMs: 60_000 }),
      hfPublicFetch("/api/market/dividends?market=egx", undefined, { cacheTtlMs: 60_000 }),
    ]);
    expect(await r1.json()).toEqual({ dividends: [1, 2] });
    expect(await r2.json()).toEqual({ dividends: [1, 2] });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const r3 = await hfPublicFetch("/api/market/dividends?market=egx", undefined, { cacheTtlMs: 60_000 });
    expect(await r3.json()).toEqual({ dividends: [1, 2] });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("falls back to same-origin when direct HF throws a network error", async () => {
    delete process.env.JEST_WORKER_ID;
    (global as any).window = { location: { hostname: "egxbots.com" } };
    const fetchMock = jest
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ fallback: true }), { status: 200 })
      );
    global.fetch = fetchMock as any;

    const res = await hfPublicFetch("/api/scan/traps?market=egx");
    expect(await res.json()).toEqual({ fallback: true });
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      `${HF_DIRECT_ORIGIN}/api/scan/traps?market=egx`,
      expect.objectContaining({ credentials: "omit" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/scan/traps?market=egx", undefined);
    // Subsequent call within cooldown uses same-origin directly
    expect(shouldUseDirectHf()).toBe(false);
  });
});
