-- Ensure profiles table exists for subscription tracking
create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text,
    stripe_customer_id text,
    subscription_status text default 'created',
    trial_ends_at timestamptz,
    updated_at timestamptz default timezone('utc', now())
);

alter table public.profiles enable row level security;

drop policy if exists "profiles are readable by owner" on public.profiles;
create policy "profiles are readable by owner"
    on public.profiles
    for select
    using (auth.uid() = id);

drop policy if exists "profiles are updatable by owner" on public.profiles;
create policy "profiles are updatable by owner"
    on public.profiles
    for update
    using (auth.uid() = id);

drop policy if exists "profiles insert allowed via signup" on public.profiles;
create policy "profiles insert allowed via signup"
    on public.profiles
    for insert
    with check (auth.uid() = id);

-- Reset existing profiles to require checkout
update public.profiles
set subscription_status = 'created',
    trial_ends_at = null
where coalesce(stripe_customer_id, '') = '';

-- Ensure new users start in the created state until they choose a plan
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, subscription_status)
  values (
    new.id,
    new.email,
    'created'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;

create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure public.handle_new_user();
