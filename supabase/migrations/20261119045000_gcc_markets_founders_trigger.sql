-- Exempt UAE and Qatar EasyKash checkout orders alongside Saudi (tasi)
-- from the domestic EGP 1-month Founders amount trigger check.

CREATE OR REPLACE FUNCTION public.check_founders_checkout_amount()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
AS $function$
DECLARE
  v_settings public.local_billing_settings%rowtype;
  v_expected numeric;
BEGIN
  IF new.plan_id = 'pro'
     AND new.affiliate_code IS NULL
     AND COALESCE(new.discount_amount_egp, 0) = 0
     AND COALESCE(new.customer_note, '') NOT ILIKE 'Market: tasi%'
     AND COALESCE(new.customer_note, '') NOT ILIKE 'Market: uae%'
     AND COALESCE(new.customer_note, '') NOT ILIKE 'Market: qatar%'
     AND COALESCE(new.duration_days, 30) = 30 THEN
    SELECT * INTO v_settings FROM public.local_billing_settings WHERE id = 1 FOR UPDATE;
    v_expected := CASE
      WHEN v_settings.founders_offer_enabled
           AND (v_settings.founders_offer_ends_at IS NULL OR NOW() < v_settings.founders_offer_ends_at)
      THEN v_settings.founders_price_egp
      ELSE v_settings.founders_regular_price_egp
    END;
    IF v_settings.founders_offer_enabled
       AND new.amount_egp <> v_expected
       AND new.amount_egp NOT IN (50, 100, 150, 200) THEN
      RAISE EXCEPTION 'Monthly price changed; refresh pricing before checkout' USING errcode = '23514';
    END IF;
  END IF;
  RETURN new;
END $function$;
