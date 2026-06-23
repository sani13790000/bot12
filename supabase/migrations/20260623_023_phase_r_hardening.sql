-- Phase R: Production Hardening
-- R-16/R-17: High-traffic index coverage
-- R-18: signals composite index
-- R-19: audit_logs retention policy
-- R-20: order_journal FK to trades
-- R-21: circuit_breaker_events index
-- R-22: orphan_positions status index

BEGIN;

CREATE INDEX IF NOT EXISTS idx_trades_user_date
    ON trades (user_id, opened_at DESC)
    WHERE opened_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_trades_user_status
    ON trades (user_id, status)
    WHERE status = 'OPEN';

CREATE INDEX IF NOT EXISTS idx_trades_user_closed
    ON trades (user_id, closed_at DESC)
    WHERE closed_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_signals_user_status_expires
    ON signals (user_id, status, expires_at DESC)
    WHERE status IN ('PENDING', 'ACTIVE');

CREATE TABLE IF NOT EXISTS audit_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action      TEXT NOT NULL,
    user_id     UUID,
    ip_address  INET,
    details     JSONB DEFAULT '{}',
    severity    TEXT DEFAULT 'info',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs (user_id, created_at DESC) WHERE user_id IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.schedule('purge_audit_logs','0 3 * * *',
            $$DELETE FROM audit_logs WHERE created_at < NOW() - INTERVAL '90 days'$$);
    END IF;
END $$;

ALTER TABLE order_journal ADD COLUMN IF NOT EXISTS trade_id UUID REFERENCES trades(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_order_journal_trade ON order_journal (trade_id) WHERE trade_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_order_journal_signal ON order_journal (signal_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cb_events_name_ts ON circuit_breaker_events (breaker_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orphan_status ON orphan_positions (status, detected_at DESC) WHERE status = 'PENDING_REVIEW';

COMMIT;
