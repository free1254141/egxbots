create table if not exists public.marketing_message_log (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references auth.users(id) on delete cascade,
    email text not null,
    message_type text not null,
    channel text not null default 'email',
    status text not null default 'sent',
    sent_at timestamptz not null default now(),
    metadata jsonb default '{}'::jsonb
);

create index if not exists idx_marketing_log_user_type on public.marketing_message_log(user_id, message_type, sent_at);
create index if not exists idx_marketing_log_email_type on public.marketing_message_log(email, message_type);

create table if not exists public.marketing_preferences (
    user_id uuid primary key references auth.users(id) on delete cascade,
    email text,
    unsubscribed_all boolean not null default false,
    unsubscribed_at timestamptz,
    updated_at timestamptz not null default now()
);

alter table public.marketing_message_log enable row level security;
alter table public.marketing_preferences enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies where schemaname = 'public' and tablename = 'marketing_preferences' and policyname = 'Users can view their own marketing preferences'
    ) then
        create policy "Users can view their own marketing preferences" on public.marketing_preferences
            for select to authenticated
            using (auth.uid() = user_id);
    end if;
end $$;

create or replace function public.get_user_email_for_marketing(p_user_id uuid)
returns text
language plpgsql
security definer
as $$
declare
    v_email text;
begin
    select email into v_email
    from auth.users
    where id = p_user_id;

    return v_email;
end;
$$;
