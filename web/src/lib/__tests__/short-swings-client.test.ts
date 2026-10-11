import { requestShortSwings, invalidateShortSwingsRequest } from "../short-swings-client";

beforeEach(() => {
  for (const key of ["viewer-a", "viewer-b"]) invalidateShortSwingsRequest(key);
});

test("prefetch and tab share one in-flight request and a brief completed result", async () => {
  let resolve!: (response: Response) => void;
  global.fetch = jest.fn(() => new Promise<Response>(done => { resolve = done; }));
  const first = requestShortSwings("viewer-a");
  const second = requestShortSwings("viewer-a");
  expect(second).toBe(first);
  expect(fetch).toHaveBeenCalledTimes(1);
  resolve({ ok: true, json: async () => ({ is_pro: true, active_trades: [], closed_trades: [] }) } as Response);
  await first;
  await requestShortSwings("viewer-a");
  expect(fetch).toHaveBeenCalledTimes(1);
  (fetch as jest.Mock).mockImplementation(async () => ({ ok: true, json: async () => ({ is_pro: true, active_trades: [], closed_trades: [] }) } as Response));
  await requestShortSwings("viewer-a", true);
  expect(fetch).toHaveBeenCalledTimes(2);
});

test("different viewers never share personalized responses and entitlement invalidation refetches", async () => {
  global.fetch = jest.fn(async () => ({ ok: true, json: async () => ({ is_pro: true, active_trades: [], closed_trades: [] }) }) as Response);
  await requestShortSwings("viewer-a");
  await requestShortSwings("viewer-b");
  expect(fetch).toHaveBeenCalledTimes(2);
  invalidateShortSwingsRequest("viewer-b");
  await requestShortSwings("viewer-b");
  expect(fetch).toHaveBeenCalledTimes(3);
});

test("errors are not cached", async () => {
  global.fetch = jest.fn(async () => ({ ok: false, status: 503 }) as Response);
  await expect(requestShortSwings("viewer-a")).rejects.toThrow("503");
  await expect(requestShortSwings("viewer-a")).rejects.toThrow("503");
  expect(fetch).toHaveBeenCalledTimes(2);
});
