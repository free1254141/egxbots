-- Migration: Convert founders offer from seat-limited to time-limited (15 days)
-- Removes the seat counter logic and replaces it with an expiry date approach.

-- 1. Add founders_offer_ends_at column to local_billing_settings
ALTER TABLE public.local_billing_settings
  ADD COLUMN IF NOT EXISTS founders_offer_ends_at TIMESTAMPTZ DEFAULT NULL;

-- 2. Drop the old founders_limit check constraint (only allowed = 100)
ALTER TABLE public.local_billing_settings
  DROP CONSTRAINT IF EXISTS local_billing_settings_founders_limit_check;

-- 3. Set founders_offer_ends_at = now + 15 days and founders_limit = 9999
UPDATE public.local_billing_settings
  SET founders_offer_ends_at = NOW() + INTERVAL '15 days',
      founders_limit = 9999
  WHERE id = 1;

-- 4. Replace the trigger function: time-based open/close instead of seat-count
CREATE OR REPLACE FUNCTION public.enforce_founders_billing_settings()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  IF new.founders_offer_enabled THEN
    -- Time-based check: offer is open if ends_at is in the future (or not set yet)
    new.discount_enabled := false;
    new.discount_price_egp := null;
    -- Note: do NOT reset discount_ends_at or founders_offer_ends_at here
    -- so that admin can freely update the expiry date
    new.discount_label_ar := 'عرض المؤسسين - لفترة محدودة';
    new.discount_label_en := 'Founders Offer - Limited Time';
  END IF;
  RETURN new;
END $$;

-- 5. Replace the founders_offer_status RPC to use time-based logic
CREATE OR REPLACE FUNCTION public.founders_offer_status()
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT jsonb_build_object(
    'enabled', s.founders_offer_enabled,
    'limit', s.founders_limit,
    'count', c.n,
    'remaining', GREATEST(0, s.founders_limit - c.n),
    'is_open', s.founders_offer_enabled AND (
      s.founders_offer_ends_at IS NULL OR NOW() < s.founders_offer_ends_at
    ),
    'price_egp', s.pro_price_egp,
    'regular_price_egp', s.founders_regular_price_egp,
    'ends_at', s.founders_offer_ends_at
  )
  FROM public.local_billing_settings s
  CROSS JOIN (SELECT count(*)::integer AS n FROM public.founders_offer_members) c
  WHERE s.id = 1;
$$;

-- Re-grant permissions on updated RPC
REVOKE ALL ON FUNCTION public.founders_offer_status() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.founders_offer_status() TO anon, authenticated, service_role;
