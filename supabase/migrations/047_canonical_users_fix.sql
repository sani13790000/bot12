-- migration 047: Canonical users table audit fix
-- Resolves ambiguity between public.users and public.user_profiles
-- This migration makes public.user_profiles the CANONICAL table
-- and adds a compatibility view for any code still referencing public.users
--
-- Background:
-- migration 001 created public.user_profiles
-- migration 014 created public.users (standalone, no timestamp prefix)
-- Both tables have overlapping columns causing ORM confusion
--
-- Resolution: DROP public.users if empty, CREATE VIEW users AS SELECT FROM user_profiles

BEGIN;

-- Step 1: Verify public.user_profiles exists (canonical)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'user_profiles'
  ) THEN
    RAISE EXCEPTION 'FATAL: public.user_profiles does not exist. Check migration 001.';
  END IF;
END;
$$;

-- Step 2: If public.users exists as a TABLE (not view), migrate data and drop
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'users'
      AND table_type = 'BASE TABLE'
  ) THEN
    -- Migrate any rows from users not in user_profiles
    INSERT INTO public.user_profiles (
      id, telegram_id, username, first_name, last_name,
      language_code, is_active, created_at, updated_at
    )
    SELECT
      id,
      telegram_id,
      COALESCE(username, ''),
      COALESCE(first_name, ''),
      COALESCE(last_name, ''),
      COALESCE(language_code, 'en'),
      COALESCE(is_active, true),
      COALESCE(created_at, NOW()),
      COALESCE(updated_at, NOW())
    FROM public.users u
    WHERE NOT EXISTS (
      SELECT 1 FROM public.user_profiles p
      WHERE p.id = u.id
    )
    ON CONFLICT (id) DO NOTHING;

    -- Drop the old table
    DROP TABLE public.users CASCADE;

    RAISE NOTICE 'public.users TABLE dropped and data migrated to user_profiles';
  END IF;
END;
$$;

-- Step 3: Create compatibility view public.users -> user_profiles
-- Code that still SELECT * FROM public.users will work transparently
CREATE OR REPLACE VIEW public.users AS
SELECT
  id,
  telegram_id,
  username,
  first_name,
  last_name,
  language_code,
  is_active,
  created_at,
  updated_at
FROM public.user_profiles;

-- Step 4: Grant same permissions as user_profiles
GRANT SELECT ON public.users TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_profiles TO authenticated;
GRANT SELECT ON public.user_profiles TO anon;

-- Step 5: Add missing index on user_profiles.telegram_id if not exists
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'user_profiles'
      AND indexname = 'idx_user_profiles_telegram_id'
  ) THEN
    CREATE INDEX CONCURRENTLY idx_user_profiles_telegram_id
      ON public.user_profiles(telegram_id);
    RAISE NOTICE 'Created idx_user_profiles_telegram_id';
  END IF;
END;
$$;

-- Step 6: Add missing index on trades.symbol + opened_at for live trading queries
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'trades'
      AND indexname = 'idx_trades_symbol_opened_at'
  ) THEN
    CREATE INDEX CONCURRENTLY idx_trades_symbol_opened_at
      ON public.trades(symbol, opened_at DESC);
    RAISE NOTICE 'Created idx_trades_symbol_opened_at';
  END IF;
END;
$$;

-- Step 7: Add missing index on signals.symbol + created_at
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'signals'
      AND indexname = 'idx_signals_symbol_created_at'
  ) THEN
    IF EXISTS (
      SELECT 1 FROM information_schema.tables
      WHERE table_schema = 'public' AND table_name = 'signals'
    ) THEN
      CREATE INDEX CONCURRENTLY idx_signals_symbol_created_at
        ON public.signals(symbol, created_at DESC);
      RAISE NOTICE 'Created idx_signals_symbol_created_at';
    END IF;
  END IF;
END;
$$;

COMMIT;

-- Verification query (run manually to confirm):
-- SELECT COUNT(*) FROM public.user_profiles;   -- should have data
-- SELECT COUNT(*) FROM public.users;            -- same count via view
-- \d public.users                               -- should show Type: view
