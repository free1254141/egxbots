import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

type Offer = {
  enabled: boolean;
  limit: number;
  count: number;
  remaining: number;
  is_open: boolean;
  price_egp: number;
  regular_price_egp: number;
  ends_at: string | null;
};

/** Returns seconds remaining until the offer expires, or null if no expiry set. */
export function foundersOfferSecondsRemaining(endsAt: string | null): number | null {
  if (!endsAt) return null;
  const diff = Math.floor((new Date(endsAt).getTime() - Date.now()) / 1000);
  return Math.max(0, diff);
}

export function applyFoundersOffer(config: any, offer: Offer | null) {
  if (!offer?.enabled) return config;
  const isGrandfathered = Boolean(config.plans?.find((p: any) => p.id === "pro")?.is_grandfathered_renewal);
  const effectivePrice = isGrandfathered ? 50 : Number(offer.price_egp);

  // Compute offer ends_at from backend (passed via payment_config -> founders.ends_at) or env fallback
  const configEndsAt =
    config.founders?.ends_at ??
    offer.ends_at ??
    process.env.FOUNDERS_OFFER_ENDS_AT ??
    process.env.NEXT_PUBLIC_FOUNDERS_OFFER_ENDS_AT ??
    null;

  return {
    ...config,
    founders: {
      ...offer,
      ends_at: configEndsAt,
      price_egp: effectivePrice,
      is_grandfathered: isGrandfathered,
    },
    plans: (config.plans || []).map((plan: any) =>
      plan.id !== "pro"
        ? plan
        : {
            ...plan,
            amount_egp: effectivePrice,
            is_grandfathered_renewal: isGrandfathered,
            discount: offer.is_open
              ? {
                  active: true,
                  kind: "founders",
                  label_ar: isGrandfathered
                    ? "سعر المؤسسين المستمر (50 ج.م مدى الحياة) ⚡"
                    : "عرض المؤسسين (100 ج.م شهرياً مدى الحياة - 15 يوم فقط 🔥)",
                  label_en: isGrandfathered
                    ? "Grandfathered Founders rate (50 EGP for life) ⚡"
                    : "Founders Offer - 100 EGP/mo for Life (15 Days Only 🔥)",
                  original_amount_egp: Number(offer.regular_price_egp || 200),
                  ends_at: configEndsAt,
                }
              : null,
          }
    ),
  };
}

export async function withFoundersOffer(config: any) {
  const { data, error } = await getSupabaseServiceClient().rpc("founders_offer_status");
  if (error) throw new Error("Founders pricing unavailable");
  return applyFoundersOffer(config, data);
}
