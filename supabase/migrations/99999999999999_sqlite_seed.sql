-- Placeholder migration for deploying schema tweaks from local SQLite features.

alter table public.profiles
add column if not exists focus_goal_minutes integer default 21;
