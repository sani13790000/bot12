-- supabase/migrations/20260623_024_phase_s_hardening.sql
-- Phase S -- Production Hardening Indexes + Constraints

-- S-25: Missing index: audit_logs lookup by user_id + action
CREATE INDEX IF NOT EXISTS idx_audit_user_action
    ON audit_logs (user_id, action, created_at DESC);

-- S-25: Missing index: audit_logs by severity for alerting
CREATE INDEX IF NOT EXISTS idx_audit_severity
    ON audit_logs (severity, created_at DESC)
    WHERE severity IN ('warning', 'critical', 'error');

-- S-26: signals table -- composite for expiry sweep
CREATE INDEX IF NOT EXISTS idx_signals_expires_status
    ON signals (expires_at, status)
    WHERE status NOT IN ('EXECUTED', 'EXPIRED', 'CANCELLED');

-- S-27: trades -- index for open position queries
CREATE INDEX IF NOT EXISTS idx_trades_open_user
    ON trades (user_id, status, symbol)
    WHERE status = 'OPEN';

-- S-28: order_journal -- lookup by order_id
CREATE INDEX IF NOT EXISTS idx_order_journal_order_id
    ON order_journal (order_id, created_at DESC);

-- S-29: Add missing NOT NULL constraints
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='signals' AND column_name='user_id'
        AND is_nullable='YES'
    ) THEN
        IF NOT EXISTS (SELECT 1 FROM signals WHERE user_id IS NULL) THEN
            ALTER TABLE signals ALTER COLUMN user_id SET NOT NULL;
        END IF;
    END IF;
END $$;

-- S-30: Partial index for orphan_positions pending review
CREATE INDEX IF NOT EXISTS idx_orphan_pending
    ON orphan_positions (detected_at DESC)
    WHERE status = 'PENDING_REVIEW';

-- S-31: Refresh token storage (for S-12 rotation)
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_hash  TEXT PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    issued_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    used        BOOLEAN NOT NULL DEFAULT FALSE,
    replaced_by TEXT,
    CONSTRAINT refresh_tokens_expires_check CHECK (expires_at > issued_at)
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user
    ON refresh_tokens (user_id, expires_at DESC)
    WHERE NOT used;

-- Auto-purge expired refresh tokens
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.schedule(
            'purge-refresh-tokens',
            '0 3 * * *',
            $$DELETE FROM refresh_tokens WHERE expires_at < NOW() - INTERVAL '1 day'$$
        );
    END IF;
END $$;

-- S-32: RLS policies for new tables
ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY refresh_tokens_owner ON refresh_tokens
    USING (user_id = auth.uid());

-- Comments
COMMENT ON TABLE refresh_tokens IS 'Phase S: Single-use refresh token store with rotation support';
COMMENT ON INDEX idx_audit_user_action IS 'Phase S: Fast audit log lookup by user+action';
COMMENT ON INDEX idx_signals_expires_status IS 'Phase S: Efficient expiry sweep for active signals';
