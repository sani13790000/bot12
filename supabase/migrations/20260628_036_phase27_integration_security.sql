-- Phase 27: External Integration Security
-- Migration 036
-- Tables: integration_keys, replay_log, idempotency_store, integration_audit_log
-- RLS: tenant isolation on all tables
-- Features: immutable audit trigger, cleanup functions, views

BEGIN;

CREATE TABLE IF NOT EXISTS integration_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    kind            TEXT NOT NULL,
    key_ref         TEXT NOT NULL,
    scheme          TEXT NOT NULL DEFAULT 'hmac_sha256',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    revoked_at      TIMESTAMPTZ,
    revoke_reason   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      UUID NOT NULL,
    CONSTRAINT integration_keys_kind_check
        CHECK (kind IN ('payment','email','telegram','webhook_in','webhook_out','market_data','auth_provider')),
    CONSTRAINT integration_keys_scheme_check
        CHECK (scheme IN ('hmac_sha256','hmac_sha512','rsa_sha256','ed25519','plain_token','none'))
);

CREATE TABLE IF NOT EXISTS replay_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    kind            TEXT NOT NULL,
    event_id        TEXT NOT NULL,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    provider_ts     TIMESTAMPTZ,
    source_ip       TEXT,
    CONSTRAINT replay_log_unique_event UNIQUE (tenant_id, kind, event_id)
);

CREATE TABLE IF NOT EXISTS idempotency_store (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    kind            TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_hash    CHAR(64) NOT NULL,
    result_json     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    CONSTRAINT idempotency_store_unique_key UNIQUE (tenant_id, kind, idempotency_key)
);

CREATE TABLE IF NOT EXISTS integration_audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    kind            TEXT NOT NULL,
    event_id        TEXT NOT NULL,
    action          TEXT NOT NULL,
    actor           TEXT NOT NULL DEFAULT 'system',
    detail          JSONB,
    chain_hash      CHAR(64) NOT NULL,
    prev_hash       CHAR(64),
    seq             BIGINT NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT integration_audit_log_action_check
        CHECK (action IN ('call.ok','call.fail','sig.verified','sig.rejected','replay.blocked','replay.accepted','idempotent.hit','idempotent.new','circuit.tripped','circuit.reset','key.revoked','dead.lettered','retry.attempt'))
);

CREATE TABLE IF NOT EXISTS integration_circuit_state (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    kind            TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'closed',
    failure_count   INT NOT NULL DEFAULT 0,
    opened_at       TIMESTAMPTZ,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT circuit_state_kind_unique UNIQUE (tenant_id, kind),
    CONSTRAINT circuit_state_check CHECK (state IN ('closed','open','half_open'))
);

CREATE INDEX IF NOT EXISTS idx_integration_keys_tenant_kind ON integration_keys (tenant_id, kind) WHERE active = TRUE;
CREATE INDEX IF NOT EXISTS idx_replay_log_tenant_kind_ts ON replay_log (tenant_id, kind, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_replay_log_event_id ON replay_log (event_id);
CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON idempotency_store (expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_idempotency_tenant_kind ON idempotency_store (tenant_id, kind, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_kind_ts ON integration_audit_log (tenant_id, kind, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action_ts ON integration_audit_log (action, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_event_id ON integration_audit_log (event_id);
CREATE INDEX IF NOT EXISTS idx_circuit_state_tenant_kind ON integration_circuit_state (tenant_id, kind);

CREATE OR REPLACE FUNCTION prevent_audit_log_mutation() RETURNS TRIGGER AS $$ BEGIN RAISE EXCEPTION 'integration_audit_log is immutable'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_audit_log_immutable ON integration_audit_log;
CREATE TRIGGER trg_audit_log_immutable BEFORE UPDATE OR DELETE ON integration_audit_log FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();

CREATE OR REPLACE FUNCTION cleanup_expired_replay_log(cutoff_hours INT DEFAULT 24) RETURNS INT AS $$ DECLARE deleted_count INT; BEGIN DELETE FROM replay_log WHERE received_at < NOW() - (cutoff_hours || ' hours')::INTERVAL; GET DIAGNOSTICS deleted_count = ROW_COUNT; RETURN deleted_count; END; $$ LANGUAGE plpgsql;
CREATE OR REPLACE FUNCTION cleanup_expired_idempotency_keys() RETURNS INT AS $$ DECLARE deleted_count INT; BEGIN DELETE FROM idempotency_store WHERE expires_at < NOW(); GET DIAGNOSTICS deleted_count = ROW_COUNT; RETURN deleted_count; END; $$ LANGUAGE plpgsql;

ALTER TABLE integration_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE replay_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_store ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_circuit_state ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all_integration_keys" ON integration_keys FOR ALL TO service_role USING (TRUE);
CREATE POLICY "service_role_all_replay_log" ON replay_log FOR ALL TO service_role USING (TRUE);
CREATE POLICY "service_role_all_idempotency" ON idempotency_store FOR ALL TO service_role USING (TRUE);
CREATE POLICY "service_role_all_audit_log" ON integration_audit_log FOR ALL TO service_role USING (TRUE);
CREATE POLICY "service_role_all_circuit_state" ON integration_circuit_state FOR ALL TO service_role USING (TRUE);

CREATE POLICY "tenant_integration_keys" ON integration_keys FOR ALL TO authenticated USING (tenant_id = (current_setting('app.tenant_id', TRUE))::UUID);
CREATE POLICY "tenant_replay_log" ON replay_log FOR ALL TO authenticated USING (tenant_id = (current_setting('app.tenant_id', TRUE))::UUID);
CREATE POLICY "tenant_idempotency" ON idempotency_store FOR ALL TO authenticated USING (tenant_id = (current_setting('app.tenant_id', TRUE))::UUID);
CREATE POLICY "tenant_audit_log" ON integration_audit_log FOR SELECT TO authenticated USING (tenant_id IS NULL OR tenant_id = (current_setting('app.tenant_id', TRUE))::UUID);
CREATE POLICY "tenant_circuit_state" ON integration_circuit_state FOR ALL TO authenticated USING (tenant_id = (current_setting('app.tenant_id', TRUE))::UUID);

CREATE OR REPLACE VIEW vw_active_integration_keys AS SELECT id, tenant_id, kind, scheme, key_ref, created_at, created_by FROM integration_keys WHERE active = TRUE AND revoked_at IS NULL;
CREATE OR REPLACE VIEW vw_open_circuits AS SELECT tenant_id, kind, failure_count, opened_at, last_updated FROM integration_circuit_state WHERE state = 'open';
CREATE OR REPLACE VIEW vw_integration_audit_summary AS SELECT kind, action, COUNT(*) AS total, MAX(ts) AS last_seen FROM integration_audit_log GROUP BY kind, action;

COMMIT;
