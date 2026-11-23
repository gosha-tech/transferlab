-- TransferLab personal browsing history.
-- Run once in your OWN Supabase project SQL editor before enabling accounts.
-- Never publish a service_role key. This script stores only player IDs and times.

create table if not exists public.player_history (
  user_id uuid not null references auth.users(id) on delete cascade,
  player_id text not null check (char_length(player_id) between 1 and 128),
  viewed_at timestamptz not null default now(),
  primary key(user_id,player_id)
);
create index if not exists player_history_recent_idx
  on public.player_history(user_id,viewed_at desc);
alter table public.player_history enable row level security;

-- Re-runnable policies. Authenticated clients may only use their OWN rows.
drop policy if exists "history_read_own" on public.player_history;
drop policy if exists "history_create_own" on public.player_history;
drop policy if exists "history_update_own" on public.player_history;
drop policy if exists "history_delete_own" on public.player_history;

create policy "history_read_own" on public.player_history
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "history_create_own" on public.player_history
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "history_update_own" on public.player_history
  for update to authenticated using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
create policy "history_delete_own" on public.player_history
  for delete to authenticated using ((select auth.uid()) = user_id);

revoke all on public.player_history from anon;
grant select, insert, update, delete on public.player_history to authenticated;

-- Index and row-level security are needed even though this is a static site.
-- Email addresses stay in Supabase Auth; we do not store them in history.
