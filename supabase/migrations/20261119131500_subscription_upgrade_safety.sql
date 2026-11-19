-- Protect active subscriptions from silent downgrade/wipeout on UNIQUE(user_id):
-- 1. Never overwrite an active 'lifetime' subscription with a timed plan.
-- 2. Never downgrade an active 'pro' subscription to 'chat_only' or 'vip_only'
--    (extend existing 'pro' period instead as defense-in-depth).
-- 3. Auto-promote complementary split plans (active 'chat_only' + 'vip_only' or vice versa)
--    to 'pro' while preserving remaining paid days.
-- 4. Preserve remaining paid days when upgrading from 'chat_only'/'vip_only' to 'pro'.

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
  v_effective_plan text := p_plan_id;
  v_subscription public.subscriptions%rowtype;
  v_claimed_order_id uuid;
  v_has_subscription boolean := false;
  v_is_active_unexpired boolean := false;
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

  -- 1. Never overwrite an active lifetime subscription with a timed plan
  IF v_has_subscription
     AND v_subscription.plan_id IN ('lifetime', 'pro_lifetime')
     AND v_subscription.status = 'active'
     AND p_plan_id <> 'lifetime' THEN
    RETURN v_subscription.current_period_end;
  END IF;

  v_is_active_unexpired := v_has_subscription
    AND v_subscription.status = 'active'
    AND v_subscription.current_period_end > v_now;

  -- 2. Defense-in-depth: never silently downgrade active Pro or wipe complementary split tier
  IF v_is_active_unexpired THEN
    IF v_subscription.plan_id IN ('pro', 'pro_6m', 'pro_1y')
       AND p_plan_id IN ('chat_only', 'vip_only') THEN
      v_effective_plan := 'pro';
    ELSIF (v_subscription.plan_id = 'chat_only' AND p_plan_id = 'vip_only')
       OR (v_subscription.plan_id = 'vip_only' AND p_plan_id = 'chat_only') THEN
      v_effective_plan := 'pro';
    END IF;
  END IF;

  INSERT INTO public.pricing_plans (id, name, price_monthly_cents, is_active)
  VALUES (
    v_effective_plan,
    CASE v_effective_plan
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

  IF v_effective_plan = 'lifetime' THEN
    v_start := v_now;
    v_end := v_now + make_interval(days => p_duration_days);
  ELSIF v_is_active_unexpired THEN
    v_start := v_now;
    v_end := v_subscription.current_period_end + make_interval(days => p_duration_days);
  ELSE
    v_start := v_now;
    v_end := v_now + make_interval(days => p_duration_days);
  END IF;

  IF v_has_subscription THEN
    UPDATE public.subscriptions
    SET plan_id = v_effective_plan,
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
      p_user_id, v_effective_plan, 'active', p_provider, v_start, v_end,
      p_payment_order_id, v_now, v_now
    );
  END IF;

  RETURN v_end;
END;
$$;

REVOKE ALL ON FUNCTION public.activate_easykash_subscription(uuid, text, integer, text, uuid, integer) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.activate_easykash_subscription(uuid, text, integer, text, uuid, integer) TO service_role;
