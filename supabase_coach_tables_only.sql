-- Essential Coach tables for The Silent Room
-- Run this in Supabase SQL Editor

-- Children/Explorers
CREATE TABLE IF NOT EXISTS public.coach_children (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    age INTEGER,
    interests TEXT,
    dream TEXT,
    created_at TIMESTAMPTZ DEFAULT timezone('utc', now())
);

-- Adventures/Projects
CREATE TABLE IF NOT EXISTS public.coach_adventures (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    child_id BIGINT NOT NULL REFERENCES public.coach_children(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    goal TEXT,
    tags TEXT,
    system_prompt TEXT,
    archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT timezone('utc', now())
);

-- Threads/Chat Pages
CREATE TABLE IF NOT EXISTS public.coach_threads (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    adventure_id BIGINT NOT NULL REFERENCES public.coach_adventures(id) ON DELETE CASCADE,
    title TEXT,
    archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT timezone('utc', now())
);

-- Messages
CREATE TABLE IF NOT EXISTS public.coach_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    thread_id BIGINT NOT NULL REFERENCES public.coach_threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    model TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    created_at TIMESTAMPTZ DEFAULT timezone('utc', now())
);

-- Points Log
CREATE TABLE IF NOT EXISTS public.coach_points_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    child_id BIGINT REFERENCES public.coach_children(id) ON DELETE SET NULL,
    ts TIMESTAMPTZ DEFAULT timezone('utc', now()),
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL
);

-- Missions Log
CREATE TABLE IF NOT EXISTS public.coach_missions_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    child_id BIGINT REFERENCES public.coach_children(id) ON DELETE SET NULL,
    ts TIMESTAMPTZ DEFAULT timezone('utc', now()),
    date DATE,
    category TEXT,
    mission TEXT
);

-- App Open Tracking (for streaks)
CREATE TABLE IF NOT EXISTS public.coach_app_open (
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    child_id BIGINT REFERENCES public.coach_children(id) ON DELETE SET NULL,
    day DATE NOT NULL,
    PRIMARY KEY (user_id, child_id, day)
);

-- Enable Row Level Security
ALTER TABLE public.coach_children ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_adventures ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_points_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_missions_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_app_open ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "children_owned_by_user" ON public.coach_children;
DROP POLICY IF EXISTS "adventures_owned_by_user" ON public.coach_adventures;
DROP POLICY IF EXISTS "threads_owned_by_user" ON public.coach_threads;
DROP POLICY IF EXISTS "messages_owned_by_user" ON public.coach_messages;
DROP POLICY IF EXISTS "points_owned_by_user" ON public.coach_points_log;
DROP POLICY IF EXISTS "missions_owned_by_user" ON public.coach_missions_log;
DROP POLICY IF EXISTS "app_open_owned_by_user" ON public.coach_app_open;

-- RLS Policies
CREATE POLICY "children_owned_by_user" ON public.coach_children
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "adventures_owned_by_user" ON public.coach_adventures
    USING (child_id IN (SELECT id FROM public.coach_children WHERE user_id = auth.uid()))
    WITH CHECK (child_id IN (SELECT id FROM public.coach_children WHERE user_id = auth.uid()));

CREATE POLICY "threads_owned_by_user" ON public.coach_threads
    USING (adventure_id IN (
        SELECT id FROM public.coach_adventures
        WHERE child_id IN (SELECT id FROM public.coach_children WHERE user_id = auth.uid())
    ))
    WITH CHECK (adventure_id IN (
        SELECT id FROM public.coach_adventures
        WHERE child_id IN (SELECT id FROM public.coach_children WHERE user_id = auth.uid())
    ));

CREATE POLICY "messages_owned_by_user" ON public.coach_messages
    USING (thread_id IN (
        SELECT coach_threads.id FROM public.coach_threads
        JOIN public.coach_adventures ON coach_adventures.id = coach_threads.adventure_id
        JOIN public.coach_children ON coach_children.id = coach_adventures.child_id
        WHERE coach_children.user_id = auth.uid()
    ))
    WITH CHECK (thread_id IN (
        SELECT coach_threads.id FROM public.coach_threads
        JOIN public.coach_adventures ON coach_adventures.id = coach_threads.adventure_id
        JOIN public.coach_children ON coach_children.id = coach_adventures.child_id
        WHERE coach_children.user_id = auth.uid()
    ));

CREATE POLICY "points_owned_by_user" ON public.coach_points_log
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "missions_owned_by_user" ON public.coach_missions_log
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "app_open_owned_by_user" ON public.coach_app_open
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());
