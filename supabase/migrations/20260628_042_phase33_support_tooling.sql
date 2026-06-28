-- Phase 33: Support Tooling & Controlled Intervention
-- Migration: 042
-- Tables: 6 + RLS + immutable audit trigger + indexes + views

-- 1. support_sessions (impersonation log)
CREATE TABLE IF NOT EXISTS support_sessions (
    session_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor            TEXT NOT NULL,
    target_user_id   TEXT NOT NULL,
    tenant_id        TEXT NOT NULL,
    role             TEXT NOT NULL CHECK (role IN ('viewer','agent','lead','admin')),
    reason           TEXT NOT NULL,
    ticket_ref       TEXT,
    mfa_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at         TIMESTAMPTZ,
    ttl_seconds      INTEGER NOT NULL DEFAULT 1800,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE support_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY support_sessions_tenant_policy ON support_sessions
    USING (tenant_id = current_setting('app.current_tenant', TRUE));

-- 2. device_reset_log
CREATE TABLE IF NOT EXISTS device_reset_log (
    reset_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id        TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    tenant_id        TEXT NOT NULL,
    actor            TEXT NOT NULL,
    reason           TEXT NOT NULL,
    action           TEXT NOT NULL CHECK (action IN ('reset','unlock')),
    slot_freed       BOOLEAN NOT NULL DEFAULT FALSE,
    ts               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE device_reset_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY device_reset_log_tenant_policy ON device_reset_log
    USING (tenant_id = current_setting('app.current_tenant', TRUE));

-- 3. subscription_extensions
CREATE TABLE IF NOT EXISTS subscription_extensions (
    ext_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          TEXT NOT NULL,
    tenant_id        TEXT NOT NULL,
    actor            TEXT NOT NULL,
    reason           TEXT NOT NULL,
    days_added       INTEGER NOT NULL CHECK (days_added > 0),
    approved_by      TEXT,
    auto_approved    BOOLEAN NOT NULL DEFAULT FALSE,
    ts               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE subscription_extensions ENABLE ROW LEVEL SECURITY;
CREATE POLICY subscription_extensions_tenant_policy ON subscription_extensions
    USING (tenant_id = current_setting('app.current_tenant', TRUE));

-- 4. artifact_resend_log
CREATE TABLE IF NOT EXISTS artifact_resend_log (
    resend_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id      TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    tenant_id        TEXT NOT NULL,
    actor            TEXT NOT NULL,
    download_url     TEXT NOT NULL,
    ttl_seconds      INTEGER NOT NULL DEFAULT 3600,
    ts               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE artifact_resend_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY artifact_resend_log_tenant_policy ON artifact_resend_log
    USING (tenant_id = current_setting('app.current_tenant', TRUE));

-- 5. support_tickets
CREATE TABLE IF NOT EXISTS support_tickets (
    ticket_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          TEXT NOT NULL,
    tenant_id        TEXT NOT NULL,
    subject          TEXT NOT NULL,
    description      TEXT NOT NULL,
    priority         TEXT NOT NULL CHECK (priority IN ('low','medium','high','urgent')),
    status           TEXT NOT NULL CHECK (status IN ('open','claimed','resolved','escalated','closed'))
                     DEFAULT 'open',
    claimed_by       TEXT,
    escalated_to     TEXT,
    tags             TEXT[] DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at      TIMESTAMPTZ
);

ALTER TABLE support_tickets ENABLE ROW LEVEL SECURITY;
CREATE POLICY support_tickets_tenant_policy ON support_tickets
    USING (tenant_id = current_setting('app.current_tenant', TRUE));

-- 6. support_audit_log (immutable)
CREATE TABLE IF NOT EXISTS support_audit_log (
    id               BIGSERIAL PRIMARY KEY,
    entry_id         UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    action           TEXT NOT NULL,
    actor            TEXT NOT NULL,
    tenant_id        TEXT NOT NULL,
    target_id        TEXT NOT NULL,
    reason           TEXT,
    detail           JSONB NOT NULL DEFAULT '{}',
    ts               DOUBLE PRECISION NOT NULL,
    seq              INTEGER NOT NULL,
    chain_hash       CHAR(64) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE support_audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY support_audit_log_tenant_policy ON support_audit_log
    USING (tenant_id = current_setting('app.current_tenant', TRUE));

-- Immutable trigger
CREATE OR REPLACE FUNCTION prevent_support_audit_modification()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'support_audit_log is immutable: % on % is not allowed',
        TG_OP, TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER support_audit_log_immutable
    BEFORE UPDATE OR DELETE ON support_audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_support_audit_modification();

-- recovery_cases
CREATE TABLE IF NOT EXISTS recovery_cases (
    case_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          TEXT NOT NULL,
    tenant_id        TEXT NOT NULL,
    actor            TEXT NOT NULL,
    reason           TEXT NOT NULL,
    steps_done       TEXT[] DEFAULT '{}',
    current_step     TEXT NOT NULL,
    completed        BOOLEAN NOT NULL DEFAULT FALSE,
    aborted          BOOLEAN NOT NULL DEFAULT FALSE,
    abort_reason     TEXT,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at     TIMESTAMPTZ
);

ALTER TABLE recovery_cases ENABLE ROW LEVEL SECURITY;
CREATE POLICY recovery_cases_tenant_policy ON recovery_cases
    USING (tenant_id = current_setting('app.current_tenant', TRUE));

-- Indexes
CREATE INDEX IF NOT EXISTS idx_support_sessions_actor ON support_sessions (actor, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_sessions_tenant ON support_sessions (tenant_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_device_reset_log_user ON device_reset_log (user_id, tenant_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_sub_extensions_user ON subscription_extensions (user_id, tenant_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_resend_artifact ON artifact_resend_log (artifact_id, user_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_support_tickets_tenant_status ON support_tickets (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_tickets_priority ON support_tickets (priority, status);
CREATE INDEX IF NOT EXISTS idx_support_audit_log_action ON support_audit_log (action, tenant_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_support_audit_log_actor ON support_audit_log (actor, ts DESC);
CREATE INDEX IF NOT EXISTS idx_support_audit_log_target ON support_audit_log (target_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_recovery_cases_tenant ON recovery_cases (tenant_id, completed, aborted);

-- Cleanup function
CREATE OR REPLACE FUNCTION cleanup_old_support_audit_logs(keep_days INTEGER DEFAULT 365)
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE deleted_count INTEGER;
BEGIN
    DELETE FROM support_audit_log WHERE created_at < NOW() - (keep_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

-- Views
CREATE OR REPLACE VIEW vw_active_support_sessions AS
SELECT session_id, actor, target_user_id, tenant_id, role, reason, ticket_ref, mfa_verified,
       started_at, ttl_seconds, started_at + (ttl_seconds || ' seconds')::INTERVAL AS expires_at
FROM support_sessions
WHERE ended_at IS NULL AND started_at + (ttl_seconds || ' seconds')::INTERVAL > NOW();

CREATE OR REPLACE VIEW vw_open_tickets_summary AS
SELECT tenant_id, priority, COUNT(*) AS ticket_count, MIN(created_at) AS oldest_ticket
FROM support_tickets WHERE status IN ('open','claimed','escalated')
GROUP BY tenant_id, priority;

CREATE OR REPLACE VIEW vw_support_audit_summary AS
SELECT action, tenant_id, COUNT(*) AS event_count, MAX(ts) AS last_event_ts
FROM support_audit_log GROUP BY action, tenant_id ORDER BY last_event_ts DESC;
