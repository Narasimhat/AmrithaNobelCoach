-- Coach Tables for Supabase
-- This schema matches the original db_supabase.py expectations

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================================
-- Children Profiles
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.coach_children (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  age INTEGER,
  interests TEXT DEFAULT '',
  dream TEXT DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_children_user ON public.coach_children(user_id);

-- ============================================================================
-- Adventures/Projects
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.coach_adventures (
  id BIGSERIAL PRIMARY KEY,
  child_id BIGINT REFERENCES public.coach_children(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  goal TEXT DEFAULT '',
  tags TEXT DEFAULT '',
  system_prompt TEXT DEFAULT '',
  archived BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_adventures_child ON public.coach_adventures(child_id);

-- ============================================================================
-- Threads/Chats
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.coach_threads (
  id BIGSERIAL PRIMARY KEY,
  adventure_id BIGINT NOT NULL REFERENCES public.coach_adventures(id) ON DELETE CASCADE,
  title TEXT,
  archived BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_threads_adventure ON public.coach_threads(adventure_id);

-- ============================================================================
-- Messages
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.coach_messages (
  id BIGSERIAL PRIMARY KEY,
  thread_id BIGINT NOT NULL REFERENCES public.coach_threads(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  model TEXT,
  tokens_in INTEGER DEFAULT 0,
  tokens_out INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_messages_thread ON public.coach_messages(thread_id);

-- ============================================================================
-- Points Log
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.coach_points_log (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  child_id BIGINT REFERENCES public.coach_children(id) ON DELETE SET NULL,
  delta INTEGER NOT NULL,
  reason TEXT,
  ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_points_user ON public.coach_points_log(user_id);
CREATE INDEX IF NOT EXISTS idx_coach_points_child ON public.coach_points_log(child_id);

-- ============================================================================
-- Missions Log
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.coach_missions_log (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  child_id BIGINT REFERENCES public.coach_children(id) ON DELETE SET NULL,
  date DATE NOT NULL,
  category TEXT NOT NULL,
  mission TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_missions_user ON public.coach_missions_log(user_id);
CREATE INDEX IF NOT EXISTS idx_coach_missions_child ON public.coach_missions_log(child_id);

-- ============================================================================
-- App Open Log (for streak tracking)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.coach_app_open (
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  child_id BIGINT REFERENCES public.coach_children(id) ON DELETE SET NULL,
  day DATE NOT NULL,
  PRIMARY KEY (user_id, child_id, day)
);

CREATE INDEX IF NOT EXISTS idx_coach_app_open_user ON public.coach_app_open(user_id);

-- ============================================================================
-- Row Level Security (RLS)
-- ============================================================================
ALTER TABLE public.coach_children ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_adventures ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_points_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_missions_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_app_open ENABLE ROW LEVEL SECURITY;

-- Grant permissions
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.coach_children TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.coach_adventures TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.coach_threads TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.coach_messages TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.coach_points_log TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.coach_missions_log TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.coach_app_open TO authenticated;

-- Grant sequence permissions for BIGSERIAL
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- ============================================================================
-- RLS Policies
-- ============================================================================

-- Children: users own their children
DROP POLICY IF EXISTS "children_owned_by_user" ON public.coach_children;
CREATE POLICY "children_owned_by_user" ON public.coach_children
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- Adventures: users own adventures for their children
DROP POLICY IF EXISTS "adventures_owned_by_user" ON public.coach_adventures;
CREATE POLICY "adventures_owned_by_user" ON public.coach_adventures
  FOR ALL TO authenticated
  USING (child_id IN (SELECT id FROM public.coach_children WHERE user_id = auth.uid()))
  WITH CHECK (child_id IN (SELECT id FROM public.coach_children WHERE user_id = auth.uid()));

-- Threads: users own threads via adventures
DROP POLICY IF EXISTS "threads_owned_by_user" ON public.coach_threads;
CREATE POLICY "threads_owned_by_user" ON public.coach_threads
  FOR ALL TO authenticated
  USING (adventure_id IN (
    SELECT a.id FROM public.coach_adventures a
    JOIN public.coach_children c ON a.child_id = c.id
    WHERE c.user_id = auth.uid()
  ))
  WITH CHECK (adventure_id IN (
    SELECT a.id FROM public.coach_adventures a
    JOIN public.coach_children c ON a.child_id = c.id
    WHERE c.user_id = auth.uid()
  ));

-- Messages: users own messages via threads
DROP POLICY IF EXISTS "messages_owned_by_user" ON public.coach_messages;
CREATE POLICY "messages_owned_by_user" ON public.coach_messages
  FOR ALL TO authenticated
  USING (thread_id IN (
    SELECT t.id FROM public.coach_threads t
    JOIN public.coach_adventures a ON t.adventure_id = a.id
    JOIN public.coach_children c ON a.child_id = c.id
    WHERE c.user_id = auth.uid()
  ))
  WITH CHECK (thread_id IN (
    SELECT t.id FROM public.coach_threads t
    JOIN public.coach_adventures a ON t.adventure_id = a.id
    JOIN public.coach_children c ON a.child_id = c.id
    WHERE c.user_id = auth.uid()
  ));

-- Points log: users own their points
DROP POLICY IF EXISTS "points_owned_by_user" ON public.coach_points_log;
CREATE POLICY "points_owned_by_user" ON public.coach_points_log
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- Missions log: users own their missions
DROP POLICY IF EXISTS "missions_owned_by_user" ON public.coach_missions_log;
CREATE POLICY "missions_owned_by_user" ON public.coach_missions_log
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- App open log: users own their app open records
DROP POLICY IF EXISTS "app_open_owned_by_user" ON public.coach_app_open;
CREATE POLICY "app_open_owned_by_user" ON public.coach_app_open
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());
