-- Restrict reads on support_messages.
--
-- Previously the only policy was `Allow select on support_messages` for role
-- `public` with USING (true), which let anyone holding the public anon key read
-- every user's support conversation.
--
-- All server routes use the service role (bypasses RLS), so only browser-side
-- Realtime subscriptions depend on these policies:
--   * users subscribe to their own session (session_id = auth.uid())
--   * admins subscribe to all sessions in the admin Support tab
--
-- Admin detection mirrors web/src/lib/admin-auth.ts: app_metadata.role = 'admin'
-- or one of the hard-coded admin emails. Admins added only through the
-- NEXT_PUBLIC_ADMIN_EMAILS env var should be given app_metadata.role = 'admin'
-- to receive realtime events (the 30s API fallback still works for them).

create or replace function public.is_support_admin()
returns boolean
language sql
stable
set search_path = ''
as $$
  select coalesce(
    (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
    or lower(auth.jwt() ->> 'email') in (
      'weeeessd57@gmail.com',
      'weeessd57@gmail.com',
      'weeasd57@gmail.com',
      'weeeenew@gmail.com'
    ),
    false
  );
$$;

revoke all on function public.is_support_admin() from public, anon;
grant execute on function public.is_support_admin() to authenticated;

alter table public.support_messages enable row level security;

drop policy if exists "Allow select on support_messages" on public.support_messages;
drop policy if exists "support_messages_select_own" on public.support_messages;
drop policy if exists "support_messages_select_admin" on public.support_messages;

create policy "support_messages_select_own"
  on public.support_messages
  for select
  to authenticated
  using (
    session_id = (select auth.uid())::text
    or user_id = (select auth.uid())
  );

create policy "support_messages_select_admin"
  on public.support_messages
  for select
  to authenticated
  using ((select public.is_support_admin()));
