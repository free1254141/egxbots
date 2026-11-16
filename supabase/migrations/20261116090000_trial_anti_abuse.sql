-- Trial anti-abuse guard: prevent multi-account free-trial farming via
-- canonical email normalization (Gmail dot/+alias stripping), device hash,
-- IP rate window, and Telegram chat ID linkage.

create table if not exists public.trial_abuse_guards (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    canonical_email text not null,
    ip_hash text,
    device_hash text,
    telegram_chat_id text,
    created_at timestamptz not null default now()
);

create index if not exists idx_trial_abuse_guards_email
    on public.trial_abuse_guards (canonical_email);
create index if not exists idx_trial_abuse_guards_device_created
    on public.trial_abuse_guards (device_hash, created_at desc)
    where device_hash is not null;
create index if not exists idx_trial_abuse_guards_ip_created
    on public.trial_abuse_guards (ip_hash, created_at desc)
    where ip_hash is not null;
create index if not exists idx_trial_abuse_guards_tg
    on public.trial_abuse_guards (telegram_chat_id)
    where telegram_chat_id is not null;

alter table public.trial_abuse_guards enable row level security;

-- Backfill existing trial users so past trials cannot re-claim via alias/Telegram
insert into public.trial_abuse_guards (user_id, canonical_email, telegram_chat_id, created_at)
select
    st.user_id,
    case
        when lower(split_part(coalesce(u.email, ''), '@', 2)) in ('gmail.com', 'googlemail.com') then
            replace(split_part(lower(split_part(coalesce(u.email, ''), '@', 1)), '+', 1), '.', '') || '@gmail.com'
        when coalesce(u.email, '') like '%@%' then
            split_part(lower(split_part(u.email, '@', 1)), '+', 1) || '@' || lower(split_part(u.email, '@', 2))
        else
            'uid:' || st.user_id::text
    end as canonical_email,
    nullif(trim(p.telegram_chat_id), '') as telegram_chat_id,
    coalesce(st.started_at, now()) as created_at
from public.subscription_trials st
left join auth.users u on u.id = st.user_id
left join public.profiles p on p.id = st.user_id
where not exists (
    select 1 from public.trial_abuse_guards g where g.user_id = st.user_id
);

drop function if exists public.start_pro_trial(uuid);

create or replace function public.start_pro_trial(
    p_user_id uuid,
    p_canonical_email text default null,
    p_ip_hash text default null,
    p_device_hash text default null,
    p_telegram_chat_id text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_existing_trial record;
    v_existing_sub record;
    v_expires_at timestamptz;
    v_email text := nullif(lower(trim(coalesce(p_canonical_email, ''))), '');
    v_ip text := nullif(trim(coalesce(p_ip_hash, '')), '');
    v_device text := nullif(trim(coalesce(p_device_hash, '')), '');
    v_tg text;
    v_ip_count integer := 0;
begin
    -- 1. Check if user already used a trial
    select * into v_existing_trial from public.subscription_trials where user_id::text = p_user_id::text;
    if found then
        return jsonb_build_object('success', false, 'error', 'TRIAL_ALREADY_USED', 'message', 'لقد استخدمت الفترة التجريبية من قبل');
    end if;

    -- 2. Check if user currently has an active paid subscription
    select * into v_existing_sub from public.subscriptions
    where user_id::text = p_user_id::text
      and status = 'active'
      and plan_id in ('pro', 'lifetime', 'pro_lifetime')
      and (current_period_end is null or current_period_end > now());
    if found then
        return jsonb_build_object('success', false, 'error', 'ALREADY_PRO', 'message', 'لديك بالفعل اشتراك Pro نشط');
    end if;

    -- 3. Check if user previously had an approved paid subscription or is a founders offer member
    if exists (
        select 1 from public.local_payment_orders
        where user_id::text = p_user_id::text and status = 'approved'
    ) or exists (
        select 1 from public.founders_offer_members
        where user_id::text = p_user_id::text
    ) then
        return jsonb_build_object('success', false, 'error', 'PREVIOUS_SUBSCRIBER', 'message', 'التجربة المجانية متاحة فقط للمشتركين الجدد الذين لم يسبق لهم الاشتراك');
    end if;

    -- 4. Require linked Telegram account resolved strictly from profiles (never trust caller arg)
    select nullif(trim(telegram_chat_id), '') into v_tg
    from public.profiles
    where id::text = p_user_id::text;
    if v_tg is null then
        return jsonb_build_object('success', false, 'error', 'TELEGRAM_LINK_REQUIRED', 'message', 'يجب ربط حسابك بتليجرام أولاً لتفعيل التجربة المجانية');
    end if;

    -- 5. Anti-abuse: canonical email alias check
    if v_email is not null and exists (
        select 1 from public.trial_abuse_guards
        where canonical_email = v_email and user_id::text <> p_user_id::text
    ) then
        return jsonb_build_object('success', false, 'error', 'TRIAL_ABUSE_EMAIL', 'message', 'تم استخدام الفترة التجريبية مسبقاً لهذا البريد الإلكتروني');
    end if;

    -- 5. Anti-abuse: linked Telegram ID check
    if v_tg is not null and exists (
        select 1 from public.trial_abuse_guards
        where telegram_chat_id = v_tg and user_id::text <> p_user_id::text
    ) then
        return jsonb_build_object('success', false, 'error', 'TRIAL_ABUSE_TELEGRAM', 'message', 'حساب تليجرام المرتبط استخدم الفترة التجريبية مسبقاً');
    end if;

    -- 6. Anti-abuse: device fingerprint check (30 days)
    if v_device is not null and exists (
        select 1 from public.trial_abuse_guards
        where device_hash = v_device
          and created_at > now() - interval '30 days'
          and user_id::text <> p_user_id::text
    ) then
        return jsonb_build_object('success', false, 'error', 'TRIAL_ABUSE_DEVICE', 'message', 'تم تفعيل فترة تجريبية على هذا الجهاز مسبقاً خلال آخر 30 يوماً');
    end if;

    -- 7. Anti-abuse: IP rate window (allows up to 2 distinct accounts per 14 days for CGNAT/shared Wi-Fi)
    if v_ip is not null then
        select count(distinct user_id) into v_ip_count
        from public.trial_abuse_guards
        where ip_hash = v_ip
          and created_at > now() - interval '14 days'
          and user_id::text <> p_user_id::text;
        if v_ip_count >= 2 then
            return jsonb_build_object('success', false, 'error', 'TRIAL_ABUSE_IP', 'message', 'تم تجاوز الحد المسموح للفترات التجريبية من هذه الشبكة');
        end if;
    end if;

    v_expires_at := now() + interval '3 days';

    -- 8. Record trial & anti-abuse guard
    insert into public.subscription_trials (user_id, started_at, expires_at)
    values (p_user_id, now(), v_expires_at);

    insert into public.trial_abuse_guards (user_id, canonical_email, ip_hash, device_hash, telegram_chat_id, created_at)
    values (
        p_user_id,
        coalesce(v_email, 'uid:' || p_user_id::text),
        v_ip,
        v_device,
        v_tg,
        now()
    );

    -- 9. Upsert subscription with status 'trialing'
    insert into public.subscriptions (
        user_id,
        plan_id,
        status,
        provider,
        current_period_start,
        current_period_end,
        updated_at
    ) values (
        p_user_id,
        'pro',
        'trialing',
        'trial',
        now(),
        v_expires_at,
        now()
    )
    on conflict (user_id) do update set
        plan_id = 'pro',
        status = 'trialing',
        provider = 'trial',
        current_period_start = now(),
        current_period_end = v_expires_at,
        updated_at = now();

    return jsonb_build_object(
        'success', true,
        'message', 'تم تفعيل تجربة Pro المجانية لمدة 3 أيام بنجاح!',
        'expires_at', v_expires_at
    );
end;
$$;

revoke all on function public.start_pro_trial(uuid, text, text, text, text) from public, anon, authenticated;
grant execute on function public.start_pro_trial(uuid, text, text, text, text) to service_role;
