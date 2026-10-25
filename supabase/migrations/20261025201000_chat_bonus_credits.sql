create table if not exists public.chat_bonus_credits (
    user_id uuid not null references auth.users(id) on delete cascade,
    source text not null,
    credits_granted integer not null,
    credits_used integer not null default 0,
    granted_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint chat_bonus_credits_pkey primary key (user_id, source),
    constraint chat_bonus_credits_non_negative check (credits_used <= credits_granted and credits_used >= 0)
);

alter table public.chat_bonus_credits enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies where schemaname = 'public' and tablename = 'chat_bonus_credits' and policyname = 'Users can view their own bonus credits'
    ) then
        create policy "Users can view their own bonus credits" on public.chat_bonus_credits
            for select to authenticated
            using (auth.uid() = user_id);
    end if;
end $$;

create or replace function public.grant_chat_bonus(p_user_id uuid, p_source text, p_credits integer)
returns boolean
language plpgsql
security definer
as $$
begin
    insert into public.chat_bonus_credits (user_id, source, credits_granted, credits_used, granted_at, updated_at)
    values (p_user_id, p_source, p_credits, 0, now(), now())
    on conflict (user_id, source) do nothing;
    return true;
end;
$$;

create or replace function public.consume_chat_bonus(p_user_id uuid)
returns jsonb
language plpgsql
security definer
as $$
declare
    v_row record;
begin
    select * into v_row
    from public.chat_bonus_credits
    where user_id = p_user_id and credits_used < credits_granted
    order by granted_at asc
    limit 1
    for update;

    if not found then
        return jsonb_build_object('allowed', false);
    end if;

    update public.chat_bonus_credits
    set credits_used = credits_used + 1,
        updated_at = now()
    where user_id = p_user_id and source = v_row.source;

    return jsonb_build_object(
        'allowed', true,
        'source', v_row.source,
        'remaining_in_bucket', (v_row.credits_granted - (v_row.credits_used + 1))
    );
end;
$$;

create or replace function public.get_chat_bonus_balance(p_user_id uuid)
returns integer
language sql
security definer
stable
as $$
    select coalesce(sum(credits_granted - credits_used), 0)::integer
    from public.chat_bonus_credits
    where user_id = p_user_id;
$$;

create or replace function public.trg_grant_telegram_link_bonus()
returns trigger
language plpgsql
security definer
as $$
begin
    if new.telegram_chat_id is not null 
       and length(trim(new.telegram_chat_id)) > 0 
       and (old.telegram_chat_id is null or length(trim(old.telegram_chat_id)) = 0) then
        perform public.grant_chat_bonus(new.id, 'telegram_link', 10);
    end if;
    return new;
end;
$$;

do $$
begin
    if not exists (
        select 1 from pg_trigger where tgname = 'trg_profiles_telegram_link_bonus'
    ) then
        create trigger trg_profiles_telegram_link_bonus
            after insert or update of telegram_chat_id on public.profiles
            for each row
            execute function public.trg_grant_telegram_link_bonus();
    end if;
end $$;

-- Backfill existing users with telegram_chat_id
insert into public.chat_bonus_credits (user_id, source, credits_granted, credits_used, granted_at, updated_at)
select id, 'telegram_link', 10, 0, now(), now()
from public.profiles
where telegram_chat_id is not null and length(trim(telegram_chat_id)) > 0
on conflict (user_id, source) do nothing;
