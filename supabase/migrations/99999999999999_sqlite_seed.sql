-- Placeholder migration for local-to-Supabase diff reconciliation.

alter table public.profiles
    add column if not exists focus_goal_minutes integer default 21;
