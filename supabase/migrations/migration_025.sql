-- Migration 025 Phase T: Security + Performance Indexes

-- T-1/T-7: user_id NOT NULL
ALTER TABLE IF EXISTS signals ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE IF EXISTS trades ALTER COLUMN user_id SET NOT NULL;

-- T-5: expiry index
CREATE INDEX IF NOT EXISTS idx_signals_user_expires ON signals (user_id, expires_at DESC) WHERE expires_at IS NOT NULL;

-- T-10/T-11: trade list
CREATE INDEX IF NOT EXISTS idx_trades_user_status_opened ON trades (user_id, status, opened_at DESC);

-- T-8: ticket ownership
CREATE INDEX IF NOT EXISTS idx_trades_user_ticket ON trades (user_id, ticket) WHERE ticket IS NOT NULL;

-- T-3/T-9: signal ownership
CREATE INDEX IF NOT EXISTS idx_signals_user_id_id ON signals (user_id, id);

-- T-19: RBAC error audit
CREATE TABLE IF NOT EXISTS rbac_audit_errors (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid,
    permission text NOT NULL,
    error      text,
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE rbac_audit_errors ENABLE ROW LEVEL SECURITY;
CREATE POLICY rbac_audit_admin_only ON rbac_audit_errors FOR ALL USING (
    EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.role IN ('admin', 'super_admin'))
);
CREATE INDEX IF NOT EXISTS idx_rbac_audit_user ON rbac_audit_errors (user_id, created_at DESC);

-- T-24: rate limit events
CREATE TABLE IF NOT EXISTS rate_limit_events (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid,
    event_type text NOT NULL,
    ip_address inet,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- T-27: timestamptz enforcement
ALTER TABLE IF EXISTS refresh_tokens ALTER COLUMN expires_at TYPE timestamptz USING expires_at AT TIME ZONE 'UTC';

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_signals_active ON signals (user_id, created_at DESC) WHERE status IN ('PENDING', 'ACTIVE');
CREATE INDEX IF NOT EXISTS idx_trades_open_symbol ON trades (user_id, symbol) WHERE status = 'OPEN';
