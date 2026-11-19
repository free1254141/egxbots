-- Add split plans ('chat_only', 'vip_only') alongside the Full Bundle ('pro')
-- at competitive regular pricing (100 / 100 / 150 EGP, 750 EGP/6m, 1350 EGP/1y),
-- fix UNIQUE(user_id) lookup in activate_easykash_subscription when switching plans,
-- and preserve grandfathered Founders 50 & 100 pricing.

create or replace function public.activate_easykash_subscription(
  p_user_id uuid,
  p_plan_id text,
  p_duration_days integer,
  p_provider text,
  p_payment_order_id uuid,
  p_price_monthly_cents integer
)
returns timestamptz
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_now timestamptz := now();
  v_start timestamptz;
  v_end timestamptz;
  v_subscription public.subscriptions%rowtype;
  v_claimed_order_id uuid;
  v_has_subscription boolean := false;
begin
  if p_plan_id not in ('pro', 'pro_6m', 'pro_1y', 'lifetime', 'chat_only', 'vip_only')
     or p_duration_days not in (30, 180, 365, 36500) then
    raise exception 'Unsupported Pro plan';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

  insert into public.payment_entitlement_events (payment_order_id, user_id)
  values (p_payment_order_id, p_user_id)
  on conflict (payment_order_id) do nothing
  returning payment_order_id into v_claimed_order_id;

  if not found then
    select current_period_end into v_end
    from public.subscriptions
    where user_id = p_user_id
    order by current_period_end desc nulls last
    limit 1;
    return v_end;
  end if;

  insert into public.pricing_plans (id, name, price_monthly_cents, is_active)
  values (
    p_plan_id,
    case p_plan_id
      when 'chat_only' then 'AI Chat Pro'
      when 'vip_only' then 'VIP Telegram Radar'
      when 'lifetime' then 'Lifetime'
      else 'Pro'
    end,
    p_price_monthly_cents,
    true
  )
  on conflict (id) do update set
    name = excluded.name,
    price_monthly_cents = excluded.price_monthly_cents,
    is_active = true;

  -- public.subscriptions enforces UNIQUE (user_id), so look up by user_id directly
  select * into v_subscription
  from public.subscriptions
  where user_id = p_user_id
  order by current_period_end desc nulls last
  limit 1
  for update;

  v_has_subscription := found;

  if v_has_subscription and v_subscription.last_payment_order_id = p_payment_order_id then
    return v_subscription.current_period_end;
  end if;

  if p_plan_id = 'lifetime' then
    v_start := v_now;
  elsif v_has_subscription
        and v_subscription.plan_id = p_plan_id
        and v_subscription.status = 'active'
        and v_subscription.current_period_end > v_now then
    v_start := v_subscription.current_period_end;
  else
    v_start := v_now;
  end if;

  v_end := v_start + make_interval(days => p_duration_days);

  if v_has_subscription then
    update public.subscriptions
    set plan_id = p_plan_id,
        status = 'active',
        provider = p_provider,
        current_period_start = v_start,
        current_period_end = v_end,
        last_payment_order_id = p_payment_order_id,
        updated_at = v_now
    where id = v_subscription.id;
  else
    insert into public.subscriptions (
      user_id, plan_id, status, provider, current_period_start,
      current_period_end, last_payment_order_id, created_at, updated_at
    ) values (
      p_user_id, p_plan_id, 'active', p_provider, v_start, v_end,
      p_payment_order_id, v_now, v_now
    );
  end if;

  return v_end;
end;
$$;

revoke all on function public.activate_easykash_subscription(uuid, text, integer, text, uuid, integer) from public, anon, authenticated;
grant execute on function public.activate_easykash_subscription(uuid, text, integer, text, uuid, integer) to service_role;

insert into public.pricing_plans (id, name, price_monthly_cents, is_active)
values
  ('chat_only', 'AI Chat Pro', 10000, true),
  ('vip_only', 'VIP Telegram Radar', 10000, true),
  ('pro', 'Pro', 15000, true)
on conflict (id) do update set
  name = excluded.name,
  price_monthly_cents = excluded.price_monthly_cents,
  is_active = true;

update public.local_billing_settings
set
  pro_price_egp = 150,
  founders_regular_price_egp = 150,
  pro_6m_price_egp = 750,
  pro_1y_price_egp = 1350,
  updated_at = now()
where id = 1;
