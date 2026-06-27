-- Phase 24: Feature Flags & Safe Rollout Control
-- Migration: 20260627_033_phase24_feature_flags.sql

BEGIN;

CREATE TABLE IF NOT EXISTS feature_flags (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flag_key        TEXT NOT NULL UNIQUE,
    enabled         BOOLEAN NOT NULL DEFAULT FALSE,
    strategy        TEXT NOT NULL DEFAULT 'none',
    rollout_pct     NUMERIC(5,2) NOT NULL DEFAULT 0,
    allowlist_users JSONB NOT NULL DEFAULT '[]',
    allowlist_tenants JSONB NOT NULL DEFAULT '[]',
    blocklist_users JSONB NOT NULL DEFAULT '[]',
    blocklist_tenants JSONB NOT NULL DEFAULT '[]',
    min_ring        TEXT,
    min_plan        TEXT,
    description     TEXT NOT NULL DEFAULT '',
    owner           TEXT NOT NULL DEFAULT 'platform',
    tenant_id       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_rollout_pct CHECK (rollout_pct BETWEEN 0 AND 100),
    CONSTRAINT valid_strategy CHECK (strategy IN ('none','percentage','canary','ring','allowlist','blocklist'))
);

CREATE TABLE IF NOT EXISTS flag_kill_overrides (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flag_key     TEXT NOT NULL,
    actor_id     TEXT NOT NULL,
    tenant_id    TEXT,
    reason       TEXT NOT NULL,
    ttl_seconds  NUMERIC,
    activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT reason_not_empty CHECK (char_length(trim(reason)) > 0)
);

CREATE TABLE IF NOT EXISTS flag_audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seq         BIGINT NOT NULL,
    flag_key    TEXT NOT NULL,
    action      TEXT NOT NULL,
    actor_id    TEXT NOT NULL,
    tenant_id   TEXT,
    reason      TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}',
    ts          DOUBLE PRECISION NOT NULL,
    chain_hash  CHAR(64) NOT NULL,
    prev_hash   CHAR(64) NOT NULL,
    CONSTRAINT reason_not_empty CHECK (char_length(trim(reason)) > 0),
    CONSTRAINT chain_hash_length CHECK (char_length(chain_hash) = 64)
);

CREATE TABLE IF NOT EXISTS flag_rollout_history (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flag_key    TEXT NOT NULL,
    rollout_pct NUMERIC(5,2) NOT NULL,
    actor_id    TEXT NOT NULL,
    tenant_id   TEXT,
    reason      TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION prevent_flag_audit_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'flag_audit_log is append-only: % denied', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS flag_audit_immutable ON flag_audit_log;
CREATE TRIGGER flag_audit_immutable
    BEFORE UPDATE OR DELETE ON flag_audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_flag_audit_mutation();

ALTER TABLE feature_flags       ENABLE ROW LEVEL SECURITY;
ALTER TABLE flag_kill_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE flag_audit_log      ENABLE ROW LEVEL SECURITY;
ALTER TABLE flag_rollout_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY flag_tenant_isolation ON feature_flags
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', TRUE));
CREATE POLICY kill_tenant_isolation ON flag_kill_overrides
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', TRUE));
CREATE POLICY audit_tenant_isolation ON flag_audit_log
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', TRUE));
CREATE POLICY rollout_tenant_isolation ON flag_rollout_history
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', TRUE));

CREATE INDEX IF NOT EXISTS idx_feature_flags_key         ON feature_flags(flag_key);
CREATE INDEX IF NOT EXISTS idx_feature_flags_tenant      ON feature_flags(tenant_id);
CREATE INDEX IF NOT EXISTS idx_flag_audit_flag_key       ON flag_audit_log(flag_key, ts DESC);
CREATE INDEX IF NOT EXISTS idx_flag_audit_actor          ON flag_audit_log(actor_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_flag_audit_seq            ON flag_audit_log(seq);
CREATE INDEX IF NOT EXISTS idx_flag_kill_key             ON flag_kill_overrides(flag_key);
CREATE INDEX IF NOT EXISTS idx_flag_rollout_key          ON flag_rollout_history(flag_key, created_at DESC);

CREATE OR REPLACE FUNCTION cleanup_expired_kills()
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE deleted INTEGER;
BEGIN
    DELETE FROM flag_kill_overrides
    WHERE ttl_seconds IS NOT NULL
      AND activated_at + (ttl_seconds * INTERVAL '1 second') < NOW();
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$;

CREATE OR REPLACE VIEW vw_active_flag_kills AS
SELECT k.*, f.description, f.enabled
FROM flag_kill_overrides k
LEFT JOIN feature_flags f ON f.flag_key = k.flag_key
WHERE k.ttl_seconds IS NULL
   OR k.activated_at + (k.ttl_seconds * INTERVAL '1 second') > NOW();

COMMIT;
