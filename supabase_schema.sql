-- Supabase schema for The Silent Room subscriptions

create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text,
    stripe_customer_id text,
    subscription_status text default 'trialing',
    trial_ends_at timestamptz,
    display_name text,
    hero_dream text,
    avatar_theme text,
    focus_goal_minutes integer default 21,
    updated_at timestamptz default timezone('utc', now())
);

alter table public.profiles enable row level security;

create policy "profiles are readable by owner"
    on public.profiles
    for select
    using (auth.uid() = id);

create policy "profiles are updatable by owner"
    on public.profiles
    for update
    using (auth.uid() = id);

create policy "profiles insert allowed via signup"
    on public.profiles
    for insert
    with check (auth.uid() = id);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, subscription_status, trial_ends_at)
  values (
    new.id,
    new.email,
    'trialing',
    timezone('utc', now()) + interval '30 days'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;

create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Silent Room data model (children, adventures, chats, progress)
-- ---------------------------------------------------------------------------

create table if not exists public.coach_children (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    name text not null,
    age integer,
    interests text,
    dream text,
    avatar_url text,
    theme text,
    timezone text,
    parent_notes text,
    created_at timestamptz default timezone('utc', now()),
    updated_at timestamptz default timezone('utc', now())
);

create table if not exists public.coach_adventures (
    id bigint generated always as identity primary key,
    child_id bigint not null references public.coach_children(id) on delete cascade,
    subject text,
    level text,
    name text not null,
    goal text,
    tags text,
    system_prompt text,
    progress_state text default 'exploring',
    archived boolean default false,
    last_activity_at timestamptz default timezone('utc', now()),
    created_at timestamptz default timezone('utc', now()),
    updated_at timestamptz default timezone('utc', now())
);

create table if not exists public.coach_threads (
    id bigint generated always as identity primary key,
    adventure_id bigint not null references public.coach_adventures(id) on delete cascade,
    title text,
    summary text,
    archived boolean default false,
    created_at timestamptz default timezone('utc', now())
);

create table if not exists public.coach_messages (
    id bigint generated always as identity primary key,
    thread_id bigint not null references public.coach_threads(id) on delete cascade,
    role text not null,
    content text not null,
    model text,
    tokens_in integer,
    tokens_out integer,
    mood text,
    created_at timestamptz default timezone('utc', now())
);

create table if not exists public.coach_attachments (
    id bigint generated always as identity primary key,
    message_id bigint not null references public.coach_messages(id) on delete cascade,
    file_url text,
    file_type text,
    file_size integer,
    created_at timestamptz default timezone('utc', now())
);

create table if not exists public.coach_points_log (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    child_id bigint references public.coach_children(id) on delete set null,
    ts timestamptz default timezone('utc', now()),
    delta integer not null,
    reason text not null,
    source text default 'coach'
);

create table if not exists public.coach_missions_log (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    child_id bigint references public.coach_children(id) on delete set null,
    ts timestamptz default timezone('utc', now()),
    date date,
    category text,
    mission text
);

create table if not exists public.coach_user_missions (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    child_id bigint references public.coach_children(id) on delete set null,
    created_ts timestamptz default timezone('utc', now()),
    title text not null,
    details text,
    tag text,
    mission_type text,
    due_at timestamptz,
    status text default 'todo'
);

create table if not exists public.coach_diary (
    user_id uuid not null references auth.users(id) on delete cascade,
    child_id bigint references public.coach_children(id) on delete set null,
    day date not null,
    big_question text,
    tried text,
    found text,
    ai_wrong text,
    next_step text,
    gratitude text,
    kindness text,
    planet text,
    primary key (user_id, child_id, day)
);

create table if not exists public.coach_health_log (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    child_id bigint references public.coach_children(id) on delete set null,
    ts timestamptz default timezone('utc', now()),
    water integer default 0,
    breaths integer default 0,
    moves integer default 0
);

create table if not exists public.coach_app_open (
    user_id uuid not null references auth.users(id) on delete cascade,
    child_id bigint references public.coach_children(id) on delete set null,
    day date not null,
    primary key (user_id, child_id, day)
);

create table if not exists public.coach_profile_settings (
    user_id uuid not null references auth.users(id) on delete cascade,
    key text not null,
    value text,
    primary key (user_id, key)
);

create table if not exists public.coach_ritual_schedule (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    child_id bigint references public.coach_children(id) on delete set null,
    weekday smallint,
    time_utc time,
    reminder_enabled boolean default false,
    created_at timestamptz default timezone('utc', now())
);

create table if not exists public.coach_lessons (
    id bigint generated always as identity primary key,
    title text not null,
    content text,
    tags text,
    age_range text,
    created_at timestamptz default timezone('utc', now()),
    updated_at timestamptz default timezone('utc', now())
);

-- Enable RLS and simple ownership policies
alter table public.coach_children enable row level security;
alter table public.coach_adventures enable row level security;
alter table public.coach_threads enable row level security;
alter table public.coach_messages enable row level security;
alter table public.coach_attachments enable row level security;
alter table public.coach_points_log enable row level security;
alter table public.coach_missions_log enable row level security;
alter table public.coach_user_missions enable row level security;
alter table public.coach_diary enable row level security;
alter table public.coach_health_log enable row level security;
alter table public.coach_app_open enable row level security;
alter table public.coach_profile_settings enable row level security;
alter table public.coach_ritual_schedule enable row level security;
alter table public.coach_lessons enable row level security;

create policy "children owned by user"
    on public.coach_children
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "adventures owned by user"
    on public.coach_adventures
    using (child_id in (select id from public.coach_children where user_id = auth.uid()))
    with check (child_id in (select id from public.coach_children where user_id = auth.uid()));

create policy "threads owned by user"
    on public.coach_threads
    using (adventure_id in (
        select id from public.coach_adventures
        where child_id in (select id from public.coach_children where user_id = auth.uid())
    ))
    with check (adventure_id in (
        select id from public.coach_adventures
        where child_id in (select id from public.coach_children where user_id = auth.uid())
    ));

create policy "messages owned by user"
    on public.coach_messages
    using (thread_id in (
        select coach_threads.id
        from public.coach_threads
        join public.coach_adventures on coach_adventures.id = coach_threads.adventure_id
        join public.coach_children on coach_children.id = coach_adventures.child_id
        where coach_children.user_id = auth.uid()
    ))
    with check (thread_id in (
        select coach_threads.id
        from public.coach_threads
        join public.coach_adventures on coach_adventures.id = coach_threads.adventure_id
        join public.coach_children on coach_children.id = coach_adventures.child_id
        where coach_children.user_id = auth.uid()
    ));

create policy "attachments owned by user"
    on public.coach_attachments
    using (message_id in (
        select coach_messages.id
        from public.coach_messages
        join public.coach_threads on coach_threads.id = coach_messages.thread_id
        join public.coach_adventures on coach_adventures.id = coach_threads.adventure_id
        join public.coach_children on coach_children.id = coach_adventures.child_id
        where coach_children.user_id = auth.uid()
    ))
    with check (message_id in (
        select coach_messages.id
        from public.coach_messages
        join public.coach_threads on coach_threads.id = coach_messages.thread_id
        join public.coach_adventures on coach_adventures.id = coach_threads.adventure_id
        join public.coach_children on coach_children.id = coach_adventures.child_id
        where coach_children.user_id = auth.uid()
    ));

create policy "points owned by user"
    on public.coach_points_log
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "missions log owned by user"
    on public.coach_missions_log
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "user missions owned by user"
    on public.coach_user_missions
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "diary owned by user"
    on public.coach_diary
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "health log owned by user"
    on public.coach_health_log
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "app open owned by user"
    on public.coach_app_open
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "profile settings owned by user"
    on public.coach_profile_settings
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "ritual schedule owned by user"
    on public.coach_ritual_schedule
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "lessons readable"
    on public.coach_lessons
    for select
    using (true);
