"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "@/contexts/AuthContext";
import { usePathname } from "next/navigation";

export interface AffiliateData {
  id: string;
  user_id: string;
  code: string;
  name: string;
  phone: string;
  payment_method: string;
  discount_percent: number;
  commission_percent: number;
  is_active: boolean;
  clicks_count: number;
  total_sales_count: number;
  total_revenue_egp: number;
  total_commission_egp: number;
  paid_commission_egp: number;
}

export interface ReferralOrder {
  id: string;
  plan_id: string;
  amount_egp: number;
  status: string;
  commission_amount_egp: number;
  commission_status: string;
  created_at: string;
}

interface AffiliateContextValue {
  affiliate: AffiliateData | null;
  referrals: ReferralOrder[];
  loading: boolean;
  isRefreshing: boolean;
  error: string | null;
  lastFetched: number | null;
  refreshAffiliate: (force?: boolean) => Promise<void>;
  saveAffiliateSettings: (params: {
    code: string;
    phone: string;
    payment_method?: string;
  }) => Promise<{ success: boolean; error?: string; affiliate?: AffiliateData }>;
}

const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes cache TTL
const STORAGE_KEY = "egxbots_affiliate_profile_cache";

const AffiliateContext = createContext<AffiliateContextValue | null>(null);

export function AffiliateProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const pathname = usePathname();
  const userId = user?.id ?? null;

  const [affiliate, setAffiliate] = useState<AffiliateData | null>(null);
  const [referrals, setReferrals] = useState<ReferralOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFetched, setLastFetched] = useState<number | null>(null);

  const inFlightRef = useRef<Promise<void> | null>(null);
  const activeUserIdRef = useRef<string | null>(userId);
  const lastFetchedRef = useRef<number | null>(null);
  const affiliateRef = useRef<AffiliateData | null>(null);
  const referralsRef = useRef<ReferralOrder[]>([]);

  // Keep refs in sync
  useEffect(() => {
    activeUserIdRef.current = userId;
  }, [userId]);

  useEffect(() => {
    lastFetchedRef.current = lastFetched;
  }, [lastFetched]);

  useEffect(() => {
    affiliateRef.current = affiliate;
  }, [affiliate]);

  useEffect(() => {
    referralsRef.current = referrals;
  }, [referrals]);

  // Try hydrating from sessionStorage on initial load or user change
  useEffect(() => {
    if (authLoading) return;

    if (!userId) {
      setAffiliate(null);
      setReferrals([]);
      setLoading(false);
      setError(null);
      setLastFetched(null);
      return;
    }

    try {
      const stored = sessionStorage.getItem(`${STORAGE_KEY}_${userId}`);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed && parsed.userId === userId) {
          setAffiliate(parsed.affiliate ?? null);
          setReferrals(Array.isArray(parsed.referrals) ? parsed.referrals : []);
          setLastFetched(parsed.timestamp ?? null);
          setLoading(false);
          return;
        }
      }
    } catch {
      // sessionStorage unavailable or parse error
    }
  }, [authLoading, userId]);

  const fetchProfile = useCallback(
    async (force: boolean = false) => {
      if (!userId) {
        setLoading(false);
        return;
      }

      const now = Date.now();
      const last = lastFetchedRef.current;
      const hasData = affiliateRef.current !== null;

      // Check TTL: avoid hammering if we already have fresh data and not forced
      if (!force && hasData && last && now - last < CACHE_TTL_MS) {
        setLoading(false);
        return;
      }

      // In-flight deduplication
      if (inFlightRef.current) {
        return inFlightRef.current;
      }

      if (!hasData) {
        setLoading(true);
      } else {
        setIsRefreshing(true);
      }

      const request = (async () => {
        try {
          const res = await fetch("/api/affiliate/me", { cache: "no-store" });
          if (!res.ok) {
            throw new Error(`Failed to load affiliate: ${res.status}`);
          }
          const data = await res.json();
          if (activeUserIdRef.current !== userId) return;

          const nextAffiliate: AffiliateData | null = data?.affiliate ?? null;
          const nextReferrals: ReferralOrder[] = Array.isArray(data?.referrals)
            ? data.referrals
            : [];
          const timestamp = Date.now();

          setAffiliate(nextAffiliate);
          setReferrals(nextReferrals);
          setLastFetched(timestamp);
          setError(null);

          // Persist to sessionStorage for instant restoration on tab navigation
          try {
            sessionStorage.setItem(
              `${STORAGE_KEY}_${userId}`,
              JSON.stringify({
                userId,
                affiliate: nextAffiliate,
                referrals: nextReferrals,
                timestamp,
              })
            );
          } catch {
            // ignore storage quota issues
          }
        } catch (err: any) {
          if (activeUserIdRef.current !== userId) return;
          setError(err?.message || "Failed to load affiliate profile");
        } finally {
          if (activeUserIdRef.current === userId) {
            setLoading(false);
            setIsRefreshing(false);
          }
        }
      })();

      inFlightRef.current = request;
      try {
        await request;
      } finally {
        if (inFlightRef.current === request) {
          inFlightRef.current = null;
        }
      }
    },
    [userId]
  );

  // Capture ?ref= or ?promo= referral links on any landing page across the site
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (pathname?.startsWith("/pricing")) return; // PricingClient handles /pricing directly with UI toast
    try {
      const params = new URLSearchParams(window.location.search);
      const rawRef = (params.get("ref") || params.get("promo") || "").trim().toUpperCase();
      if (!rawRef || rawRef.length > 32) return;

      const trackKey = `egx_tracked_ref_${rawRef}`;
      const alreadyTracked = sessionStorage.getItem(trackKey) === "1";

      fetch(
        `/api/payment/easykash/validate-promo?code=${encodeURIComponent(rawRef)}${alreadyTracked ? "" : "&track=1"}`,
        { cache: "no-store" }
      )
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data?.valid && data?.code) {
            localStorage.setItem("egx_affiliate_ref", data.code);
            sessionStorage.setItem(trackKey, "1");
          }
        })
        .catch(() => {});
    } catch {
      // ignore storage or URL parse errors
    }
  }, [pathname]);

  // Load only when relevant (e.g. on /affiliate page or when user opens affiliate feature)
  useEffect(() => {
    if (authLoading || !userId) return;

    const isAffiliatePath = pathname?.startsWith("/affiliate");
    if (isAffiliatePath) {
      fetchProfile(false);
    }
  }, [authLoading, userId, pathname, fetchProfile]);

  const refreshAffiliate = useCallback(
    async (force: boolean = true) => {
      await fetchProfile(force);
    },
    [fetchProfile]
  );

  const saveAffiliateSettings = useCallback(
    async (params: {
      code: string;
      phone: string;
      payment_method?: string;
    }): Promise<{ success: boolean; error?: string; affiliate?: AffiliateData }> => {
      if (!userId) {
        return { success: false, error: "User not authenticated" };
      }

      try {
        const res = await fetch("/api/affiliate/me", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            code: params.code.trim().toUpperCase(),
            phone: params.phone.replace(/[\s-]/g, ""),
            payment_method: params.payment_method || "vodafone_cash",
          }),
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          return { success: false, error: data?.error || "Failed to save settings" };
        }

        if (data?.affiliate) {
          const nextAffiliate = data.affiliate as AffiliateData;
          setAffiliate(nextAffiliate);
          const timestamp = Date.now();
          setLastFetched(timestamp);

          try {
            sessionStorage.setItem(
              `${STORAGE_KEY}_${userId}`,
              JSON.stringify({
                userId,
                affiliate: nextAffiliate,
                referrals: referralsRef.current,
                timestamp,
              })
            );
          } catch {
            // ignore
          }

          return { success: true, affiliate: nextAffiliate };
        }

        return { success: true };
      } catch (err: any) {
        return { success: false, error: err?.message || "Network error" };
      }
    },
    [userId]
  );

  return (
    <AffiliateContext.Provider
      value={{
        affiliate,
        referrals,
        loading,
        isRefreshing,
        error,
        lastFetched,
        refreshAffiliate,
        saveAffiliateSettings,
      }}
    >
      {children}
    </AffiliateContext.Provider>
  );
}

export function useAffiliate() {
  const context = useContext(AffiliateContext);
  if (!context) {
    throw new Error("useAffiliate must be used within an AffiliateProvider");
  }
  return context;
}
