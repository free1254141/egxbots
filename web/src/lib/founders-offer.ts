import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

type Offer = { enabled: boolean; limit: number; count: number; remaining: number; is_open: boolean;
  price_egp: number; regular_price_egp: number; ends_at: null };

export function applyFoundersOffer(config: any, offer: Offer | null) {
  if (!offer?.enabled) return config;
  return {
    ...config,
    founders: { ...offer, ends_at: null },
    plans: (config.plans || []).map((plan: any) => plan.id !== "pro" ? plan : {
      ...plan, amount_egp: Number(offer.price_egp),
      discount: offer.is_open ? {
        active: true, kind: "founders", label_ar: "عرض أول 100 مشترك", label_en: "First 100 subscribers",
        original_amount_egp: Number(offer.regular_price_egp), ends_at: null,
      } : null,
    }),
  };
}

export async function withFoundersOffer(config: any) {
  const { data, error } = await getSupabaseServiceClient().rpc("founders_offer_status");
  if (error) throw new Error("Founders pricing unavailable");
  return applyFoundersOffer(config, data);
}
