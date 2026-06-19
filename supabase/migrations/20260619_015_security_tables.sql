-- Migration 015: Security tables
-- revoked_tokens (JWT jti blocklist)
-- refresh_tokens (for rotation + revocation)
-- login_attempts (audit log)
-- RLS policies for all tables

BEGIN;

-- ============================================================
-- revoked_tokens: stores revoked JWT jti values
-- TTL: auto-delete after token expires
-- ============================================================
CREATE TABLE IF NOT EXISTS revoked_tokens (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    jti         TEXT        NOT NULL UNIQUE,
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_revoked_tokens_jti         ON revoked_tokens(jti);
CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires_at  ON revoked_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_revoked_tokens_user_id     ON revoked_tokens(user_id);

-- RLS
ALTER TABLE revoked_tokens ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS revoked_tokens_self ON revoked_tokens;
CREATE POLICY revoked_tokens_self ON revoked_tokens
    FOR SELECT
    USING (user_id = auth.uid());

DROP POLICY IF EXISTS revoked_tokens_service ON revoked_tokens;
CREATE POLICY revoked_tokens_service ON revoked_tokens
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Auto-delete expired tokens (cleanup function)
CREATE OR REPLACE FUNCTION cleanup_expired_revoked_tokens()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    DELETE FROM revoked_tokens WHERE expires_at < NOW();
END;
$$;

-- ============================================================
-- refresh_tokens: stores valid refresh token jti values
-- ============================================================
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    jti         TEXT        NOT NULL UNIQUE,
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_jti      ON refresh_tokens(jti);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id  ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires  ON refresh_tokens(expires_at);

-- RLS
ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS refresh_tokens_self ON refresh_tokens;
CREATE POLICY refresh_tokens_self ON refresh_tokens
    FOR SELECT
    USING (user_id = auth.uid());

DROP POLICY IF EXISTS refresh_tokens_service ON refresh_tokens;
CREATE POLICY refresh_tokens_service ON refresh_tokens
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Auto-delete expired refresh tokens
CREATE OR REPLACE FUNCTION cleanup_expired_refresh_tokens()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    DELETE FROM refresh_tokens WHERE expires_at < NOW();
END;
$$;

-- ============================================================
-- login_attempts: audit log for failed logins
-- ============================================================
CREATE TABLE IF NOT EXISTS login_attempts (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ip_address  TEXT        NOT NULL,
    email       TEXT,
    success     BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_login_attempts_ip   ON login_attempts(ip_address, created_at);
CREATE INDEX IF NOT EXISTS idx_login_attempts_time ON login_attempts(created_at);

-- RLS: only service_role can read/write
ALTER TABLE login_attempts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS login_attempts_service ON login_attempts;
CREATE POLICY login_attempts_service ON login_attempts
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================
-- users table: ensure RLS is enabled + policies
-- ============================================================
ALTER TABLE IF EXISTS users ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_self_select ON users;
CREATE POLICY users_self_select ON users
    FOR SELECT
    USING (id = auth.uid());

DROP POLICY IF EXISTS users_self_update ON users;
CREATE POLICY users_self_update ON users
    FOR UPDATE
    USING (id = auth.uid())
    WITH CHECK (id = auth.uid());

DROP POLICY IF EXISTS users_service ON users;
CREATE POLICY users_service ON users
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================
-- Scheduled cleanup (pg_cron if available)
-- ============================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'
    ) THEN
        PERFORM cron.schedule(
            'cleanup-expired-tokens',
            '0 * * * *',  -- every hour
            $$SELECT cleanup_expired_revoked_tokens(); SELECT cleanup_expired_refresh_tokens();$$
        );
    END IF;
END;
$$;

COMMIT;
