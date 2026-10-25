-- Marketing ad tracking: provider message id, click/open/delivery events and a campaign report.

alter table public.marketing_message_log
    add column if not exists provider_message_id text;

create index if not exists idx_marketing_log_provider_id
    on public.marketing_message_log(provider_message_id)
    where provider_message_id is not null;

create table if not exists public.marketing_events (
    id uuid primary key default gen_random_uuid(),
    event_type text not null check (event_type in ('delivered','opened','clicked','bounced','complained','delivery_delayed','unsubscribed')),
    channel text not null default 'email' check (channel in ('email','telegram')),
    campaign text,
    message_id uuid references public.marketing_message_log(id) on delete set null,
    provider_message_id text,
    user_id uuid references auth.users(id) on delete set null,
    target text,
    svix_id text,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_marketing_events_svix on public.marketing_events(svix_id) where svix_id is not null;
create index if not exists idx_marketing_events_campaign on public.marketing_events(campaign, event_type, created_at);
create index if not exists idx_marketing_events_message on public.marketing_events(message_id);

alter table public.marketing_events enable row level security;

-- Aggregated campaign report (service_role only). Conversion = paid Pro subscription activated
-- by the same user within 7 days after the message was sent.
create or replace function public.marketing_campaign_report(p_days integer default 30)
returns table (
    channel text,
    campaign text,
    sent bigint,
    delivered bigint,
    opened bigint,
    clicked bigint,
    bounced bigint,
    converted bigint
)
language sql
security definer
set search_path = public
as $$
    with msgs as (
        select id, user_id, message_type, channel, sent_at
        from marketing_message_log
        where sent_at >= now() - make_interval(days => greatest(p_days, 1))
    ),
    ev as (
        select e.message_id,
               bool_or(e.event_type = 'delivered') as delivered,
               bool_or(e.event_type = 'opened') as opened,
               bool_or(e.event_type = 'clicked') as clicked,
               bool_or(e.event_type in ('bounced','complained')) as bounced
        from marketing_events e
        where e.message_id is not null
        group by e.message_id
    ),
    conv as (
        select m.id as message_id
        from msgs m
        join subscriptions s on s.user_id = m.user_id
        where s.status = 'active'
          and s.plan_id in ('pro','lifetime','pro_lifetime')
          and coalesce(s.current_period_start, s.created_at) >= m.sent_at
          and coalesce(s.current_period_start, s.created_at) <= m.sent_at + interval '7 days'
        group by m.id
    )
    select m.channel,
           m.message_type as campaign,
           count(*) as sent,
           count(*) filter (where ev.delivered) as delivered,
           count(*) filter (where ev.opened) as opened,
           count(*) filter (where ev.clicked) as clicked,
           count(*) filter (where ev.bounced) as bounced,
           count(conv.message_id) as converted
    from msgs m
    left join ev on ev.message_id = m.id
    left join conv on conv.message_id = m.id
    group by m.channel, m.message_type
    union all
    -- Telegram has no per-user message log: report clicks only.
    select 'telegram'::text, e.campaign, 0::bigint, 0::bigint, 0::bigint,
           count(*) filter (where e.event_type = 'clicked'), 0::bigint, 0::bigint
    from marketing_events e
    where e.channel = 'telegram'
      and e.created_at >= now() - make_interval(days => greatest(p_days, 1))
    group by e.campaign;
$$;

revoke all on function public.marketing_campaign_report(integer) from public, anon, authenticated;
grant execute on function public.marketing_campaign_report(integer) to service_role;
