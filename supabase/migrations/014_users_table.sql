-- Migration 014: users table with full RLS, indexes, and updated_at trigger
-- Safe to run multiple times (IF NOT EXISTS everywhere)

BEGIN;

-- ============================================================
-- 1. users table
-- ============================================================
CREATE TABLE IF NOT EXISTS public.users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username      TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin', 'viewer')),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 2. Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_users_username ON public.users (username);
CREATE INDEX IF NOT EXISTS idx_users_email    ON public.users (email);
CREATE INDEX IF NOT EXISTS idx_users_role     ON public.users (role);
CREATE INDEX IF NOT EXISTS idx_users_active   ON public.users (is_active) WHERE is_active = TRUE;

-- ============================================================
-- 3. updated_at auto-update trigger
-- ============================================================
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_users_updated_at ON public.users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- 4. Row Level Security
-- ============================================================
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (backend API uses service role key)
DROP POLICY IF EXISTS users_service_all ON public.users;
CREATE POLICY users_service_all ON public.users
    FOR ALL
    TO service_role
    USING (TRUE)
    WITH CHECK (TRUE);

-- Users can only read their own row
DROP POLICY IF EXISTS users_self_select ON public.users;
CREATE POLICY users_self_select ON public.users
    FOR SELECT
    TO authenticated
    USING (id::TEXT = auth.uid()::TEXT);

-- Users can update their own row (except role and id)
DROP POLICY IF EXISTS users_self_update ON public.users;
CREATE POLICY users_self_update ON public.users
    FOR UPDATE
    TO authenticated
    USING (id::TEXT = auth.uid()::TEXT)
    WITH CHECK (id::TEXT = auth.uid()::TEXT);

-- ============================================================
-- 5. refresh_tokens table for revocation list
-- ============================================================
CREATE TABLE IF NOT EXISTS public.refresh_tokens (
    jti        TEXT PRIMARY KEY,
    user_id    UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    revoked    BOOLEAN NOT NULL DEFAULT FALSE,
    issued_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id   ON public.refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_revoked   ON public.refresh_tokens (revoked) WHERE revoked = FALSE;
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires   ON public.refresh_tokens (expires_at);

ALTER TABLE public.refresh_tokens ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS refresh_tokens_service_all ON public.refresh_tokens;
CREATE POLICY refresh_tokens_service_all ON public.refresh_tokens
    FOR ALL
    TO service_role
    USING (TRUE)
    WITH CHECK (TRUE);

COMMIT;
