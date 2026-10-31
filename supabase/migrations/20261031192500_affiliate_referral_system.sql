-- Migration: Affiliate & Referral Code System for EGX BOTS
-- Supports influencer promo codes, user referral links, buyer discounts, commission tracking, and payouts.

CREATE TABLE IF NOT EXISTS public.affiliates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid UNIQUE REFERENCES auth.users(id) ON DELETE SET NULL,
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  phone text NOT NULL DEFAULT '',
  payment_method text NOT NULL DEFAULT 'vodafone_cash',
  discount_percent numeric(5,2) NOT NULL DEFAULT 10 CHECK (discount_percent >= 0 AND discount_percent <= 50),
  commission_percent numeric(5,2) NOT NULL DEFAULT 25 CHECK (commission_percent > 0 AND commission_percent <= 80),
  is_active boolean NOT NULL DEFAULT true,
  clicks_count integer NOT NULL DEFAULT 0,
  total_sales_count integer NOT NULL DEFAULT 0,
  total_revenue_egp numeric(12,2) NOT NULL DEFAULT 0,
  total_commission_egp numeric(12,2) NOT NULL DEFAULT 0,
  paid_commission_egp numeric(12,2) NOT NULL DEFAULT 0,
  notes text DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS affiliates_code_idx ON public.affiliates (upper(code));
CREATE INDEX IF NOT EXISTS affiliates_user_id_idx ON public.affiliates (user_id);

ALTER TABLE public.affiliates ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.affiliates FROM anon, authenticated;
GRANT ALL ON public.affiliates TO service_role;

ALTER TABLE public.local_payment_orders
  ADD COLUMN IF NOT EXISTS affiliate_id uuid REFERENCES public.affiliates(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS affiliate_code text DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS discount_amount_egp numeric(10,2) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS commission_amount_egp numeric(10,2) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS commission_status text NOT NULL DEFAULT 'none';

CREATE INDEX IF NOT EXISTS local_payment_orders_affiliate_idx
  ON public.local_payment_orders (affiliate_id, status, created_at DESC);

-- Update check_founders_checkout_amount to allow discounted affiliate orders and grandfathered renewals
CREATE OR REPLACE FUNCTION public.check_founders_checkout_amount()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_settings public.local_billing_settings%rowtype;
BEGIN
  IF new.plan_id = 'pro' AND new.affiliate_code IS NULL AND COALESCE(new.discount_amount_egp, 0) = 0 THEN
    SELECT * INTO v_settings FROM public.local_billing_settings WHERE id = 1 FOR UPDATE;
    IF v_settings.founders_offer_enabled AND new.amount_egp <> v_settings.pro_price_egp AND new.amount_egp NOT IN (50, 100) THEN
      RAISE EXCEPTION 'Monthly price changed; refresh pricing before checkout' USING errcode = '23514';
    END IF;
  END IF;
  RETURN new;
END $$;
