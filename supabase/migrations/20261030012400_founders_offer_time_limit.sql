-- Migration: Convert founders offer from seat-limited to time-limited (ends 2026-11-14T01:00:00Z)
-- Automatically reverts price_egp from 100 EGP to 200 EGP when NOW() >= founders_offer_ends_at.

-- 1. Add founders_offer_ends_at column to local_billing_settings
ALTER TABLE public.local_billing_settings
  ADD COLUMN IF NOT EXISTS founders_offer_ends_at TIMESTAMPTZ DEFAULT NULL;

-- 2. Drop the old founders_limit check constraint (only allowed = 100)
ALTER TABLE public.local_billing_settings
  DROP CONSTRAINT IF EXISTS local_billing_settings_founders_limit_check;

-- 3. Replace the trigger function: time-based open/close instead of seat-count
CREATE OR REPLACE FUNCTION public.enforce_founders_billing_settings()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  IF new.founders_offer_enabled THEN
    new.pro_price_egp := CASE
      WHEN new.founders_offer_ends_at IS NULL OR NOW() < new.founders_offer_ends_at
      THEN COALESCE(new.founders_price_egp, 100.00)
      ELSE COALESCE(new.founders_regular_price_egp, 200.00)
    END;
    new.discount_enabled := false;
    new.discount_price_egp := null;
    new.discount_label_ar := 'عرض المؤسسين - لفترة محدودة';
    new.discount_label_en := 'Founders Offer - Limited Time';
  END IF;
  RETURN new;
END $$;

-- 4. Set founders_offer_ends_at = 2026-11-14T01:00:00Z and founders_limit = 9999
UPDATE public.local_billing_settings
  SET founders_offer_ends_at = '2026-11-14T01:00:00Z'::timestamptz,
      founders_limit = 9999,
      founders_price_egp = 100.00,
      founders_regular_price_egp = 200.00,
      pro_price_egp = 100.00
  WHERE id = 1;

-- 5. Replace the founders_offer_status RPC to use time-based logic and auto-revert price_egp to 200
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
    'price_egp', CASE
      WHEN s.founders_offer_enabled AND (s.founders_offer_ends_at IS NULL OR NOW() < s.founders_offer_ends_at)
      THEN s.founders_price_egp
      ELSE s.founders_regular_price_egp
    END,
    'regular_price_egp', s.founders_regular_price_egp,
    'ends_at', s.founders_offer_ends_at
  )
  FROM public.local_billing_settings s
  CROSS JOIN (SELECT count(*)::integer AS n FROM public.founders_offer_members) c
  WHERE s.id = 1;
$$;

REVOKE ALL ON FUNCTION public.founders_offer_status() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.founders_offer_status() TO anon, authenticated, service_role;

-- 6. Update check_founders_checkout_amount so both open (100) and expired (200) + grandfathered (50, 100) work
CREATE OR REPLACE FUNCTION public.check_founders_checkout_amount()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_settings public.local_billing_settings%rowtype;
  v_expected numeric;
BEGIN
  IF new.plan_id = 'pro' AND new.affiliate_code IS NULL AND COALESCE(new.discount_amount_egp, 0) = 0 THEN
    SELECT * INTO v_settings FROM public.local_billing_settings WHERE id = 1 FOR UPDATE;
    v_expected := CASE
      WHEN v_settings.founders_offer_enabled AND (v_settings.founders_offer_ends_at IS NULL OR NOW() < v_settings.founders_offer_ends_at)
      THEN v_settings.founders_price_egp
      ELSE v_settings.founders_regular_price_egp
    END;
    IF v_settings.founders_offer_enabled AND new.amount_egp <> v_expected AND new.amount_egp NOT IN (50, 100, 200) THEN
      RAISE EXCEPTION 'Monthly price changed; refresh pricing before checkout' USING errcode = '23514';
    END IF;
  END IF;
  RETURN new;
END $$;

-- 7. Update record_founders_subscription_activation to only add to founders_offer_members while window is open
CREATE OR REPLACE FUNCTION public.record_founders_subscription_activation()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_settings public.local_billing_settings%rowtype;
BEGIN
  IF new.status <> 'active' OR new.plan_id NOT IN ('pro', 'lifetime') THEN
    RETURN new;
  END IF;
  SELECT * INTO v_settings FROM public.local_billing_settings WHERE id = 1 FOR UPDATE;
  IF NOT v_settings.founders_offer_enabled THEN
    RETURN new;
  END IF;
  IF v_settings.founders_offer_ends_at IS NULL OR NOW() < v_settings.founders_offer_ends_at THEN
    INSERT INTO public.founders_offer_members(user_id) VALUES(new.user_id) ON CONFLICT(user_id) DO NOTHING;
  END IF;
  UPDATE public.local_billing_settings SET updated_at = NOW() WHERE id = 1;
  RETURN new;
END $$;
