-- Fix Postgres error 42883: operator does not exist: text = uuid in start_pro_trial
-- public.local_payment_orders.user_id is text, while p_user_id is uuid.
create or replace function public.start_pro_trial(p_user_id uuid)
returns jsonb
language plpgsql
security definer
as $$
declare
    v_existing_trial record;
    v_existing_sub record;
    v_expires_at timestamptz;
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

    v_expires_at := now() + interval '3 days';

    -- 4. Record trial
    insert into public.subscription_trials (user_id, started_at, expires_at)
    values (p_user_id, now(), v_expires_at);

    -- 5. Upsert subscription with status 'trialing'
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
