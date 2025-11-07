-- Supabase schema for The Silent Room subscriptions

create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text,
    stripe_customer_id text,
    subscription_status text default 'trialing',
    trial_ends_at timestamptz,
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
