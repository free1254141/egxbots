-- Migration: create scheduled_chat_automations table for Pro users AI chat scheduling
create table if not exists public.scheduled_chat_automations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null default 'استشارة مجدولة',
  prompt text not null,
  scheduled_time text not null, -- format "HH:MM" e.g. "08:30" Cairo Time
  days_of_week text not null default 'trading_days', -- 'trading_days' (Sun-Thu) or 'all_days'
  telegram_chat_id text, -- optional override, defaults to profile telegram_chat_id
  is_active boolean not null default true,
  last_run_at timestamptz,
  last_run_date date,
  last_status text, -- 'success', 'quota_exceeded', 'error'
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_scheduled_automations_active_time 
  on public.scheduled_chat_automations(is_active, scheduled_time);

create index if not exists idx_scheduled_automations_user 
  on public.scheduled_chat_automations(user_id);

alter table public.scheduled_chat_automations enable row level security;

create policy "Users can view their own automations" on public.scheduled_chat_automations for select using (auth.uid() = user_id);
create policy "Users can insert their own automations" on public.scheduled_chat_automations for insert with check (auth.uid() = user_id);
create policy "Users can update their own automations" on public.scheduled_chat_automations for update using (auth.uid() = user_id);
create policy "Users can delete their own automations" on public.scheduled_chat_automations for delete using (auth.uid() = user_id);

grant all on public.scheduled_chat_automations to authenticated, service_role;
