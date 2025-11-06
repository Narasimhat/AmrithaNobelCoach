alter table public.profiles
    add column if not exists display_name text,
    add column if not exists hero_dream text,
    add column if not exists avatar_theme text;

comment on column public.profiles.display_name is 'Child-friendly name or nickname shown in the coach';
comment on column public.profiles.hero_dream is 'Short sentence about the child''s dream mission as a hero';
comment on column public.profiles.avatar_theme is 'Preferred visual theme/avatar selection for the interface';
