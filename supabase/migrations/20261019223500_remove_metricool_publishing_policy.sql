-- Migration: 20261019223500_remove_metricool_publishing_policy.sql
-- Removes legacy Metricool free-plan quota restrictions, scheduling constraints, and reservation functions.
-- Preserves public.daily_social_publications history and enables direct autonomous Facebook publishing.

-- 1. Neutralize trigger function so it never blocks inserts or enforces Metricool caps
create or replace function public.guard_social_publication_slot() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
  if new.publication_at is null then
    new.publication_at := now();
  end if;
  return new;
end $$;

-- 2. Allow publication_at to default to now() and be nullable
alter table public.daily_social_publications alter column publication_at drop not null;
alter table public.daily_social_publications alter column publication_at set default now();

-- 3. Drop legacy Metricool reservation function if exists
drop function if exists public.reserve_daily_social_publications(date, text, timestamptz);

-- 4. Expand primary key to (session_date, platform, kind) to support multiple daily slots
alter table public.daily_social_publications drop constraint if exists daily_social_publications_pkey;
alter table public.daily_social_publications add primary key (session_date, platform, kind);
