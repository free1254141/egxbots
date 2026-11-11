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
  const proPlan = config.plans?.find((p: any) => p.id === "pro");
  const isGrandfathered50 = Boolean(proPlan?.is_grandfathered_renewal);
  const isGrandfathered100 = Boolean(proPlan?.is_grandfathered_100);

  // Compute offer ends_at from backend (passed via payment_config -> founders.ends_at) or env fallback
  const configEndsAt =
    config.founders?.ends_at ||
    offer.ends_at ||
    process.env.FOUNDERS_OFFER_ENDS_AT ||
    process.env.NEXT_PUBLIC_FOUNDERS_OFFER_ENDS_AT ||
    "2026-11-14T01:00:00Z";

  const notExpired = !configEndsAt || new Date(configEndsAt).getTime() > Date.now();
  const isOpen = Boolean(offer.is_open && notExpired);
  const regularPrice = Number(offer.regular_price_egp || 200);
  const foundersPrice = Number(offer.price_egp || 100);

  const effectivePrice = isGrandfathered50
    ? 50
    : isGrandfathered100
    ? 100
    : isOpen
    ? foundersPrice
    : regularPrice;

  const hasSpecialRate = isGrandfathered50 || isGrandfathered100 || isOpen;

  return {
    ...config,
    founders: {
      ...offer,
      limit: null,
      count: null,
      remaining: null,
      is_open: isOpen,
      ends_at: configEndsAt,
      price_egp: effectivePrice,
      is_grandfathered: isGrandfathered50,
      is_grandfathered_100: isGrandfathered100,
    },
    plans: (config.plans || []).map((plan: any) => {
      if (plan.id === "pro") {
        return {
          ...plan,
          amount_egp: effectivePrice,
          is_grandfathered_renewal: isGrandfathered50,
          is_grandfathered_100: isGrandfathered100,
          discount: hasSpecialRate
            ? {
                active: true,
                kind: "founders",
                label_ar: isGrandfathered50
                  ? "سعر المؤسسين المستمر (50 ج.م مدى الحياة) ⚡"
                  : isGrandfathered100 && !isOpen
                  ? "سعر المؤسسين المثبت لحسابك (100 ج.م مدى الحياة) ⚡"
                  : "عرض المؤسسين (100 ج.م شهرياً مدى الحياة - 15 يوم فقط 🔥)",
                label_en: isGrandfathered50
                  ? "Grandfathered Founders rate (50 EGP for life) ⚡"
                  : isGrandfathered100 && !isOpen
                  ? "Locked Founders rate (100 EGP/mo for life) ⚡"
                  : "Founders Offer - 100 EGP/mo for Life (15 Days Only 🔥)",
                original_amount_egp: regularPrice,
                ends_at: isOpen ? configEndsAt : null,
              }
            : null,
        };
      }
      if (plan.id === "pro_6m") {
        return {
          ...plan,
          amount_egp: hasSpecialRate ? 500 : 1000,
          founders_lock_rate: hasSpecialRate ? 100 : null,
          discount: hasSpecialRate
            ? {
                active: true,
                kind: "founders",
                label_ar: "عرض المؤسسين خصم 50% (500 بدل 1,000 ج.م + تثبيت 100 ج.م/شهر مدى الحياة) 🔥",
                label_en: "Founders Offer 50% OFF (500 instead of 1,000 EGP + locks 100 EGP/mo for life) 🔥",
                original_amount_egp: 1000,
                ends_at: isOpen ? configEndsAt : null,
              }
            : null,
        };
      }
      if (plan.id === "pro_1y") {
        return {
          ...plan,
          amount_egp: hasSpecialRate ? 1000 : 1850,
          founders_lock_rate: hasSpecialRate ? 100 : null,
          discount: hasSpecialRate
            ? {
                active: true,
                kind: "founders",
                label_ar: "عرض المؤسسين (1,000 بدل 1,850 ج.م + تثبيت 100 ج.م/شهر مدى الحياة) 🔥",
                label_en: "Founders Offer (1,000 instead of 1,850 EGP + locks 100 EGP/mo for life) 🔥",
                original_amount_egp: 1850,
                ends_at: isOpen ? configEndsAt : null,
              }
            : null,
        };
      }
      return plan;
    }),
  };
}

export async function withFoundersOffer(config: any) {
  const { data, error } = await getSupabaseServiceClient().rpc("founders_offer_status");
  if (error) throw new Error("Founders pricing unavailable");
  return applyFoundersOffer(config, data);
}
