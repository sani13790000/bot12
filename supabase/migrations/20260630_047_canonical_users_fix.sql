-- BUG-S2 FIX: Was '047_canonical_users_fix.sql' (no timestamp) — sorted before 001_initial_schema
-- Renamed to 20260630_047_canonical_users_fix.sql to ensure correct execution order
-- Original content preserved below:

-- Canonical users fix: ensure user_profiles view/table is correct post-migration
DO $$
BEGIN
  -- Drop VIEW if it exists (from earlier migrations that created it as VIEW)
  IF EXISTS (
    SELECT 1 FROM information_schema.views
    WHERE table_schema = 'public' AND table_name = 'user_profiles'
  ) THEN
    DROP VIEW public.user_profiles;
  END IF;
END;
$$;

-- Ensure user_profiles is a proper table
CREATE TABLE IF NOT EXISTS public.user_profiles (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name  TEXT,
  avatar_url    TEXT,
  role          TEXT        NOT NULL DEFAULT 'trader',
  license_tier  TEXT        NOT NULL DEFAULT 'basic',
  is_active     BOOLEAN     NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_user_profiles_user_id UNIQUE (user_id)
);

-- RLS
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "users_own_profile"
  ON public.user_profiles FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY IF NOT EXISTS "admin_all_profiles"
  ON public.user_profiles FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.user_profiles up
      WHERE up.user_id = auth.uid() AND up.role IN ('admin', 'superadmin')
    )
  );

-- Index
CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON public.user_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_role    ON public.user_profiles(role);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION public.update_user_profiles_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_user_profiles_updated_at ON public.user_profiles;
CREATE TRIGGER trg_user_profiles_updated_at
  BEFORE UPDATE ON public.user_profiles
  FOR EACH ROW EXECUTE FUNCTION public.update_user_profiles_updated_at();
