jest.mock("@/lib/supabase/route-data", () => ({ getSupabaseServiceClient: jest.fn() }));
import { applyFoundersOffer, withFoundersOffer } from "../founders-offer";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

const config = { enabled: true, plans: [{ id: "pro", amount_egp: 200 }, { id: "pro_6m", amount_egp: 1000 }], founders: { count: 0 } };
const offer = { enabled: true, limit: 100, count: 99, remaining: 1, is_open: true, price_egp: 100, regular_price_egp: 200, ends_at: null };

it("uses time-limited offer with 15-day fallback and leaves other plans intact", () => {
  const result = applyFoundersOffer(config, offer);
  expect(result.plans[0]).toMatchObject({
    amount_egp: 100,
    discount: { active: true, ends_at: "2026-11-14T01:00:00Z", original_amount_egp: 200 },
  });
  expect(result.founders.ends_at).toBe("2026-11-14T01:00:00Z");
  expect(result.plans[1]).toEqual(config.plans[1]);
  expect(config.plans[0].amount_egp).toBe(200);
});

it("closes at 100 and removes the old timed discount", () => {
  const result = applyFoundersOffer(config, { ...offer, count: 100, remaining: 0, is_open: false, price_egp: 200 });
  expect(result.plans[0]).toMatchObject({ amount_egp: 200, discount: null });
  expect(result.founders.is_open).toBe(false);
});

it("reverts to regular 200 EGP when time is expired in the past", () => {
  const pastOffer = { ...offer, is_open: true, ends_at: "2026-11-01T00:00:00Z" };
  const result = applyFoundersOffer(config, pastOffer);
  expect(result.plans[0]).toMatchObject({ amount_egp: 200, discount: null });
  expect(result.founders.is_open).toBe(false);
});

it("preserves 100 EGP for grandfathered-100 users even after offer expires", () => {
  const expiredOffer = { ...offer, is_open: false, ends_at: "2026-11-01T00:00:00Z" };
  const grandfatheredConfig = {
    ...config,
    plans: [{ id: "pro", amount_egp: 200, is_grandfathered_100: true }, { id: "pro_6m", amount_egp: 1000 }],
  };
  const result = applyFoundersOffer(grandfatheredConfig, expiredOffer);
  expect(result.plans[0]).toMatchObject({
    amount_egp: 100,
    is_grandfathered_100: true,
    discount: { active: true, ends_at: null, original_amount_egp: 200 },
  });
  expect(result.founders.is_grandfathered_100).toBe(true);
});

it("preserves 50 EGP for grandfathered-50 users even after offer expires", () => {
  const expiredOffer = { ...offer, is_open: false, ends_at: "2026-11-01T00:00:00Z" };
  const grandfatheredConfig = {
    ...config,
    plans: [{ id: "pro", amount_egp: 200, is_grandfathered_renewal: true }, { id: "pro_6m", amount_egp: 1000 }],
  };
  const result = applyFoundersOffer(grandfatheredConfig, expiredOffer);
  expect(result.plans[0]).toMatchObject({
    amount_egp: 50,
    is_grandfathered_renewal: true,
    discount: { active: true, ends_at: null, original_amount_egp: 200 },
  });
  expect(result.founders.is_grandfathered).toBe(true);
});

it("preserves configured pricing when the offer is disabled", () => {
  expect(applyFoundersOffer(config, { ...offer, enabled: false })).toBe(config);
});

it("refuses to invent pricing on a failed authoritative read", async () => {
  (getSupabaseServiceClient as jest.Mock).mockReturnValue({ rpc: jest.fn().mockResolvedValue({ error: { message: "offline" } }) });
  await expect(withFoundersOffer(config)).rejects.toThrow("Founders pricing unavailable");
});
