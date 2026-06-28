-- Phase 29: Secure Secrets Rotation & Key Lifecycle
-- Migration 038
BEGIN;

-- key_versions: all key versions with lifecycle state
CREATE TABLE IF NOT EXISTS key_versions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id         UUID NOT NULL,
    key_type       TEXT NOT NULL CHECK (key_type IN (
                       'jwt_signing','jwt_refresh','encryption_dek',
                       'encryption_kek','signing_artifact','webhook_hmac',
                       'audit_chain','api_secret','backup_encrypt',
                       'tenant_isolation')),
    version        INTEGER NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                       'active','grace','revoked','expired','pending')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at   TIMESTAMPTZ,
    expires_at     TIMESTAMPTZ,
    rotated_at     TIMESTAMPTZ,
    revoked_at     TIMESTAMPTZ,
    revoke_reason  TEXT,
    use_count      BIGINT NOT NULL DEFAULT 0,
    tenant_id      UUID,
    signature      CHAR(64) NOT NULL DEFAULT '',
    rotation_trigger TEXT NOT NULL DEFAULT 'bootstrap' CHECK (rotation_trigger IN (
                       'scheduled','compromise','manual',
                       'policy_age','policy_use','bootstrap')),
    UNIQUE (key_id, version)
);

-- rotation_policies: per-type, per-tenant rotation configuration
CREATE TABLE IF NOT EXISTS rotation_policies (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_type       TEXT NOT NULL,
    tenant_id      UUID,
    max_age_days   INTEGER NOT NULL DEFAULT 90 CHECK (max_age_days > 0),
    grace_days     INTEGER NOT NULL DEFAULT 14 CHECK (grace_days >= 0),
    max_uses       BIGINT NOT NULL DEFAULT 0,
    auto_rotate    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (key_type, tenant_id)
);

-- compromise_reports: tracks key compromise incidents
CREATE TABLE IF NOT EXISTS compromise_reports (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id         UUID NOT NULL,
    key_type       TEXT NOT NULL,
    version        INTEGER NOT NULL,
    reported_by    TEXT NOT NULL,
    reported_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason         TEXT NOT NULL CHECK (reason <> ''),
    new_key_id     UUID,
    resolved       BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at    TIMESTAMPTZ,
    resolved_by    TEXT,
    steps_taken    JSONB NOT NULL DEFAULT '[]'
);

-- key_audit_log: immutable tamper-evident HMAC chain
CREATE TABLE IF NOT EXISTS key_audit_log (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seq            BIGINT NOT NULL,
    action         TEXT NOT NULL,
    key_id         TEXT NOT NULL,
    key_type       TEXT NOT NULL,
    version        INTEGER NOT NULL,
    actor          TEXT NOT NULL,
    tenant_id      UUID,
    reason         TEXT,
    detail         JSONB NOT NULL DEFAULT '{}',
    ts             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    prev_hash      CHAR(64) NOT NULL,
    chain_hash     CHAR(64) NOT NULL
);

-- Prevent UPDATE/DELETE on audit log (immutable)
CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'key_audit_log is immutable: % not allowed', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS key_audit_immutable ON key_audit_log;
CREATE TRIGGER key_audit_immutable
    BEFORE UPDATE OR DELETE ON key_audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();

-- RLS on all tables
ALTER TABLE key_versions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE rotation_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE compromise_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE key_audit_log    ENABLE ROW LEVEL SECURITY;

-- RLS policies
DROP POLICY IF EXISTS tenant_isolation_key_versions ON key_versions;
CREATE POLICY tenant_isolation_key_versions ON key_versions
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID
           OR current_setting('app.role', TRUE) = 'admin');

DROP POLICY IF EXISTS tenant_isolation_rotation_policies ON rotation_policies;
CREATE POLICY tenant_isolation_rotation_policies ON rotation_policies
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID
           OR tenant_id IS NULL
           OR current_setting('app.role', TRUE) = 'admin');

DROP POLICY IF EXISTS tenant_isolation_compromise_reports ON compromise_reports;
CREATE POLICY tenant_isolation_compromise_reports ON compromise_reports
    USING (current_setting('app.role', TRUE) = 'admin');

DROP POLICY IF EXISTS tenant_isolation_key_audit ON key_audit_log;
CREATE POLICY tenant_isolation_key_audit ON key_audit_log
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID
           OR current_setting('app.role', TRUE) = 'admin');

-- Indexes
CREATE INDEX IF NOT EXISTS idx_key_versions_key_id     ON key_versions (key_id);
CREATE INDEX IF NOT EXISTS idx_key_versions_type_status ON key_versions (key_type, status);
CREATE INDEX IF NOT EXISTS idx_key_versions_tenant      ON key_versions (tenant_id);
CREATE INDEX IF NOT EXISTS idx_key_versions_expires     ON key_versions (expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_compromise_reports_key   ON compromise_reports (key_id);
CREATE INDEX IF NOT EXISTS idx_compromise_resolved      ON compromise_reports (resolved);
CREATE INDEX IF NOT EXISTS idx_key_audit_log_key_id     ON key_audit_log (key_id);
CREATE INDEX IF NOT EXISTS idx_key_audit_log_seq        ON key_audit_log (seq);
CREATE INDEX IF NOT EXISTS idx_key_audit_log_tenant     ON key_audit_log (tenant_id);
CREATE INDEX IF NOT EXISTS idx_key_audit_log_action     ON key_audit_log (action);

-- Cleanup function: expire grace keys past their expiry
CREATE OR REPLACE FUNCTION cleanup_expired_grace_keys()
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE key_versions
    SET status = 'expired'
    WHERE status = 'grace'
      AND expires_at IS NOT NULL
      AND expires_at < NOW();
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$;

-- View: active keys by type
CREATE OR REPLACE VIEW vw_active_keys AS
SELECT
    key_id,
    key_type,
    version,
    tenant_id,
    activated_at,
    rotated_at,
    use_count,
    signature
FROM key_versions
WHERE status = 'active'
ORDER BY key_type, tenant_id, version DESC;

-- View: keys due for rotation
CREATE OR REPLACE VIEW vw_keys_due_rotation AS
SELECT
    kv.key_id,
    kv.key_type,
    kv.version,
    kv.tenant_id,
    kv.activated_at,
    kv.use_count,
    rp.max_age_days,
    EXTRACT(EPOCH FROM NOW() - kv.activated_at)/86400 AS age_days
FROM key_versions kv
LEFT JOIN rotation_policies rp
    ON rp.key_type = kv.key_type
    AND (rp.tenant_id = kv.tenant_id OR rp.tenant_id IS NULL)
WHERE kv.status = 'active'
  AND kv.activated_at IS NOT NULL
  AND EXTRACT(EPOCH FROM NOW() - kv.activated_at)/86400
      >= COALESCE(rp.max_age_days, 90) * 0.8;

-- View: open compromise reports
CREATE OR REPLACE VIEW vw_open_compromise_reports AS
SELECT
    id AS report_id,
    key_id,
    key_type,
    version,
    reported_by,
    reported_at,
    reason
FROM compromise_reports
WHERE resolved = FALSE
ORDER BY reported_at DESC;

-- Seed default rotation policies
INSERT INTO rotation_policies (key_type, max_age_days, grace_days, max_uses, auto_rotate)
VALUES
    ('jwt_signing',      30,  7,  0,        TRUE),
    ('jwt_refresh',      90,  14, 0,        TRUE),
    ('encryption_dek',   90,  30, 1000000,  TRUE),
    ('encryption_kek',   365, 60, 0,        FALSE),
    ('signing_artifact', 180, 30, 0,        TRUE),
    ('webhook_hmac',     60,  14, 0,        TRUE),
    ('audit_chain',      365, 90, 0,        FALSE),
    ('api_secret',       90,  7,  0,        TRUE),
    ('backup_encrypt',   365, 60, 0,        FALSE),
    ('tenant_isolation', 180, 30, 0,        TRUE)
ON CONFLICT (key_type, tenant_id) DO NOTHING;

COMMIT;
