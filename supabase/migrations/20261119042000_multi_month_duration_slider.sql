-- Support 1-12 month duration slider across standalone ('chat_only', 'vip_only')
-- and Full Bundle ('pro') plans by persisting duration_days on local_payment_orders,
-- accepting 30..365 day durations in activate_easykash_subscription(), and exempting
-- multi-month orders (duration_days != 30) from the 1-month Founders amount trigger.

ALTER TABLE public.local_payment_orders
  ADD COLUMN IF NOT EXISTS duration_days integer;

CREATE OR REPLACE FUNCTION public.activate_easykash_subscription(
  p_user_id uuid,
  p_plan_id text,
  p_duration_days integer,
  p_provider text,
  p_payment_order_id uuid,
  p_price_monthly_cents integer
)
RETURNS timestamptz
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  v_now timestamptz := now();
  v_start timestamptz;
  v_end timestamptz;
  v_subscription public.subscriptions%rowtype;
  v_claimed_order_id uuid;
  v_has_subscription boolean := false;
BEGIN
  IF p_plan_id NOT IN ('pro', 'pro_6m', 'pro_1y', 'lifetime', 'chat_only', 'vip_only')
     OR p_duration_days NOT IN (30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 365, 36500) THEN
    RAISE EXCEPTION 'Unsupported Pro plan';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

  INSERT INTO public.payment_entitlement_events (payment_order_id, user_id)
  VALUES (p_payment_order_id, p_user_id)
  ON CONFLICT (payment_order_id) DO NOTHING
  RETURNING payment_order_id INTO v_claimed_order_id;

  IF NOT FOUND THEN
    SELECT current_period_end INTO v_end
    FROM public.subscriptions
    WHERE user_id = p_user_id
    ORDER BY current_period_end DESC NULLS LAST
    LIMIT 1;
    RETURN v_end;
  END IF;

  INSERT INTO public.pricing_plans (id, name, price_monthly_cents, is_active)
  VALUES (
    p_plan_id,
    CASE p_plan_id
      WHEN 'chat_only' THEN 'AI Chat Pro'
      WHEN 'vip_only' THEN 'VIP Telegram Radar'
      WHEN 'lifetime' THEN 'Lifetime'
      ELSE 'Pro'
    END,
    p_price_monthly_cents,
    true
  )
  ON CONFLICT (id) DO UPDATE SET
    name = excluded.name,
    price_monthly_cents = excluded.price_monthly_cents,
    is_active = true;

  -- public.subscriptions enforces UNIQUE (user_id), so look up by user_id directly
  SELECT * INTO v_subscription
  FROM public.subscriptions
  WHERE user_id = p_user_id
  ORDER BY current_period_end DESC NULLS LAST
  LIMIT 1
  FOR UPDATE;

  v_has_subscription := FOUND;

  IF v_has_subscription AND v_subscription.last_payment_order_id = p_payment_order_id THEN
    RETURN v_subscription.current_period_end;
  END IF;

  IF p_plan_id = 'lifetime' THEN
    v_start := v_now;
  ELSIF v_has_subscription
        AND v_subscription.plan_id = p_plan_id
        AND v_subscription.status = 'active'
        AND v_subscription.current_period_end > v_now THEN
    v_start := v_subscription.current_period_end;
  ELSE
    v_start := v_now;
  END IF;

  v_end := v_start + make_interval(days => p_duration_days);

  IF v_has_subscription THEN
    UPDATE public.subscriptions
    SET plan_id = p_plan_id,
        status = 'active',
        provider = p_provider,
        current_period_start = v_start,
        current_period_end = v_end,
        last_payment_order_id = p_payment_order_id,
        updated_at = v_now
    WHERE id = v_subscription.id;
  ELSE
    INSERT INTO public.subscriptions (
      user_id, plan_id, status, provider, current_period_start,
      current_period_end, last_payment_order_id, created_at, updated_at
    ) VALUES (
      p_user_id, p_plan_id, 'active', p_provider, v_start, v_end,
      p_payment_order_id, v_now, v_now
    );
  END IF;

  RETURN v_end;
END;
$$;

REVOKE ALL ON FUNCTION public.activate_easykash_subscription(uuid, text, integer, text, uuid, integer) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.activate_easykash_subscription(uuid, text, integer, text, uuid, integer) TO service_role;

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
