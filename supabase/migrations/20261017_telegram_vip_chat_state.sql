create table if not exists public.telegram_vip_chat_state (
  telegram_user_id bigint primary key,
  telegram_username text,
  linked_user_id uuid,
  quota_date date not null default current_date,
  daily_count integer not null default 0,
  session_state jsonb not null default '{}'::jsonb,
  session_summary jsonb not null default '{}'::jsonb,
  chat_history jsonb not null default '[]'::jsonb,
  pending_prompt jsonb,
  updated_at timestamptz not null default now()
);

alter table public.telegram_vip_chat_state enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'telegram_vip_chat_state'
      and policyname = 'Service role full access on telegram_vip_chat_state'
  ) then
    create policy "Service role full access on telegram_vip_chat_state"
      on public.telegram_vip_chat_state
      for all
      to service_role
      using (true)
      with check (true);
  end if;
end $$;
