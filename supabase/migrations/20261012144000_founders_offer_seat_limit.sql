-- The monthly founders offer ends on the 100th distinct activation, never on a date.
-- Keep the deployed Python billing reader compatible: pro_price_egp is the
-- effective quote, while the normal price is stored separately.
alter table public.local_billing_settings
  add column founders_offer_enabled boolean not null default false,
  add column founders_limit integer not null default 100 check (founders_limit = 100),
  add column founders_price_egp numeric(10,2) not null default 50 check (founders_price_egp > 0),
  add column founders_regular_price_egp numeric(10,2) not null default 200 check (founders_regular_price_egp > founders_price_egp);

create table public.founders_offer_members (
  user_id uuid primary key,
  joined_at timestamptz not null default now()
);
alter table public.founders_offer_members enable row level security;
revoke all on public.founders_offer_members from anon, authenticated;
grant select, insert on public.founders_offer_members to service_role;

-- Preserve the 13 currently published active members; historical canceled
-- memberships were not in that counter. Future cancellation never frees a seat.
insert into public.founders_offer_members(user_id, joined_at)
select user_id, min(created_at) from public.subscriptions
where status = 'active' and plan_id in ('pro', 'lifetime')
group by user_id order by min(created_at), user_id limit 100;

create function public.enforce_founders_billing_settings()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_count integer;
begin
  if new.founders_offer_enabled then
    select count(*) into v_count from public.founders_offer_members;
    new.pro_price_egp := case when v_count < new.founders_limit then new.founders_price_egp else new.founders_regular_price_egp end;
    new.discount_enabled := false;
    new.discount_ends_at := null;
    new.discount_price_egp := null;
    new.discount_label_ar := 'عرض أول 100 مشترك';
    new.discount_label_en := 'First 100 subscribers';
  end if;
  return new;
end $$;
revoke all on function public.enforce_founders_billing_settings() from public, anon, authenticated;
create trigger enforce_founders_billing_settings before insert or update on public.local_billing_settings
for each row execute function public.enforce_founders_billing_settings();

create function public.record_founders_subscription_activation()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_settings public.local_billing_settings%rowtype; v_count integer;
begin
  if new.status <> 'active' or new.plan_id not in ('pro', 'lifetime') then return new; end if;
  -- Serialize concurrent activations; a renewal cannot claim another seat.
  select * into v_settings from public.local_billing_settings where id=1 for update;
  if not v_settings.founders_offer_enabled then return new; end if;
  select count(*) into v_count from public.founders_offer_members;
  if v_count < v_settings.founders_limit then
    insert into public.founders_offer_members(user_id) values(new.user_id) on conflict(user_id) do nothing;
  end if;
  update public.local_billing_settings set updated_at=now() where id=1;
  return new;
end $$;
revoke all on function public.record_founders_subscription_activation() from public, anon, authenticated;
create trigger record_founders_subscription_activation after insert or update of status,plan_id on public.subscriptions
for each row execute function public.record_founders_subscription_activation();

-- Refuse a stale cached amount before any hosted payment request is sent.
-- Previously issued payment orders retain their agreed price and can settle.
create function public.check_founders_checkout_amount()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_settings public.local_billing_settings%rowtype;
begin
  if new.plan_id = 'pro' then
    select * into v_settings from public.local_billing_settings where id=1 for update;
    if v_settings.founders_offer_enabled and new.amount_egp <> v_settings.pro_price_egp then
      raise exception 'Monthly price changed; refresh pricing before checkout' using errcode='23514';
    end if;
  end if;
  return new;
end $$;
revoke all on function public.check_founders_checkout_amount() from public, anon, authenticated;
create trigger check_founders_checkout_amount before insert on public.local_payment_orders
for each row execute function public.check_founders_checkout_amount();

create function public.founders_offer_status()
returns jsonb language sql stable security definer set search_path = '' as $$
  select jsonb_build_object('enabled',s.founders_offer_enabled,'limit',s.founders_limit,
    'count',c.n,'remaining',greatest(0,s.founders_limit-c.n),
    'is_open',s.founders_offer_enabled and c.n<s.founders_limit,
    'price_egp',s.pro_price_egp,'regular_price_egp',s.founders_regular_price_egp,'ends_at',null)
  from public.local_billing_settings s
  cross join (select count(*)::integer as n from public.founders_offer_members) c where s.id=1;
$$;
revoke all on function public.founders_offer_status() from public;
grant execute on function public.founders_offer_status() to anon, authenticated, service_role;

update public.local_billing_settings set founders_offer_enabled=true,
  founders_regular_price_egp=coalesce(pro_price_egp,200), updated_at=now() where id=1;
