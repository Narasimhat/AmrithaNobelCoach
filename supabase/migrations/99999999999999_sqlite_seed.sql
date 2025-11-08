-- Schema alignment migration for focus goal + hero profile fields.

alter table public.profiles
    add column if not exists display_name text;

alter table public.profiles
    add column if not exists hero_dream text;

alter table public.profiles
    add column if not exists avatar_theme text;

alter table public.profiles
    add column if not exists focus_goal_minutes integer default 21;
