-- Migration 020: Auth Hardening
-- Adds UNIQUE constraint on refresh_tokens.jti for FIX-5 (upsert support)
-- Adds expires_at to revoked_tokens for automated cleanup
-- Adds performance indexes for token lookups
-- Adds purge_expired_tokens() function

BEGIN;

-- 1. refresh_tokens: jti must be UNIQUE (required for upsert on_conflict=jti)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'refresh_tokens_jti_key'
    ) THEN
        ALTER TABLE refresh_tokens ADD CONSTRAINT refresh_tokens_jti_key UNIQUE (jti);
    END IF;
END $$;

-- 2. revoked_tokens: add expires_at for auto-purge
ALTER TABLE revoked_tokens
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- 3. Performance indexes
CREATE INDEX IF NOT EXISTS idx_revoked_tokens_jti
    ON revoked_tokens(jti);

CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires
    ON revoked_tokens(expires_at)
    WHERE expires_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_active
    ON refresh_tokens(user_id)
    WHERE expires_at > NOW();

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires
    ON refresh_tokens(expires_at);

-- 4. Token cleanup function
CREATE OR REPLACE FUNCTION purge_expired_tokens()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    deleted_refresh INTEGER;
    deleted_revoked INTEGER;
BEGIN
    DELETE FROM refresh_tokens WHERE expires_at < NOW() - INTERVAL '1 hour';
    GET DIAGNOSTICS deleted_refresh = ROW_COUNT;
    DELETE FROM revoked_tokens
    WHERE expires_at IS NOT NULL AND expires_at < NOW();
    GET DIAGNOSTICS deleted_revoked = ROW_COUNT;
    RAISE NOTICE 'purge_expired_tokens: deleted % refresh, % revoked',
        deleted_refresh, deleted_revoked;
    RETURN deleted_refresh + deleted_revoked;
END;
$$;

-- 5. RLS
ALTER TABLE IF EXISTS refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS revoked_tokens  ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'refresh_tokens' AND policyname = 'service_role_all'
    ) THEN
        CREATE POLICY service_role_all ON refresh_tokens USING (true) WITH CHECK (true);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'revoked_tokens' AND policyname = 'service_role_all'
    ) THEN
        CREATE POLICY service_role_all ON revoked_tokens USING (true) WITH CHECK (true);
    END IF;
END $$;

COMMIT;
