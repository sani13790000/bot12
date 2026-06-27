-- Phase 25: Release Artifact Governance
-- Migration: 20260627_034_phase25_artifact_governance.sql

BEGIN;

CREATE TABLE IF NOT EXISTS artifact_records (
    artifact_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    name            TEXT NOT NULL,
    version         TEXT NOT NULL,
    artifact_type   TEXT NOT NULL,
    platform        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft',
    sha256          CHAR(64) NOT NULL,
    sha512          CHAR(128) NOT NULL,
    size_bytes      BIGINT NOT NULL,
    signature       TEXT NOT NULL DEFAULT '',
    signed_by       TEXT,
    signed_at       TIMESTAMPTZ,
    published_at    TIMESTAMPTZ,
    deprecated_at   TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    revoke_reason   TEXT,
    deprecated_reason TEXT,
    download_count  BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}',
    CONSTRAINT artifact_status_valid CHECK (
        status IN ('draft','signed','published','deprecated','revoked')
    ),
    CONSTRAINT artifact_sha256_len CHECK (length(sha256) = 64),
    CONSTRAINT artifact_revoke_reason_required CHECK (
        status != 'revoked' OR (revoke_reason IS NOT NULL AND revoke_reason != '')
    )
);

CREATE TABLE IF NOT EXISTS artifact_audit_log (
    seq             BIGSERIAL,
    entry_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id     UUID NOT NULL,
    tenant_id       UUID NOT NULL,
    action          TEXT NOT NULL,
    actor           TEXT NOT NULL,
    reason          TEXT NOT NULL DEFAULT '',
    detail          JSONB DEFAULT '{}',
    chain_hash      CHAR(64) NOT NULL,
    prev_hash       CHAR(64) NOT NULL,
    ts              DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())
);

CREATE TABLE IF NOT EXISTS artifact_compatibility_rules (
    rule_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_type   TEXT NOT NULL,
    platform        TEXT NOT NULL,
    min_version     TEXT NOT NULL,
    max_version     TEXT,
    required_features JSONB DEFAULT '[]',
    notes           TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS artifact_download_tokens (
    token_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id     UUID NOT NULL,
    tenant_id       UUID NOT NULL,
    issued_to       TEXT NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    used_at         TIMESTAMPTZ,
    is_used         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION artifact_audit_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'artifact_audit_log is immutable';
END;
$$;

DROP TRIGGER IF EXISTS trg_artifact_audit_immutable ON artifact_audit_log;
CREATE TRIGGER trg_artifact_audit_immutable
    BEFORE UPDATE OR DELETE ON artifact_audit_log
    FOR EACH ROW EXECUTE FUNCTION artifact_audit_immutable();

CREATE OR REPLACE FUNCTION artifact_revoke_reason_check()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status = 'revoked' AND (NEW.revoke_reason IS NULL OR NEW.revoke_reason = '') THEN
        RAISE EXCEPTION 'revoke_reason is required when status=revoked';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_artifact_revoke_reason ON artifact_records;
CREATE TRIGGER trg_artifact_revoke_reason
    BEFORE INSERT OR UPDATE ON artifact_records
    FOR EACH ROW EXECUTE FUNCTION artifact_revoke_reason_check();

CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE cnt INTEGER;
BEGIN
    DELETE FROM artifact_download_tokens WHERE expires_at < NOW() AND is_used = FALSE;
    GET DIAGNOSTICS cnt = ROW_COUNT;
    RETURN cnt;
END;
$$;

ALTER TABLE artifact_records          ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact_audit_log        ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact_compatibility_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact_download_tokens  ENABLE ROW LEVEL SECURITY;

CREATE POLICY artifact_tenant_isolation ON artifact_records
    USING (tenant_id = current_setting('app.tenant_id')::UUID);
CREATE POLICY artifact_audit_tenant_isolation ON artifact_audit_log
    USING (tenant_id = current_setting('app.tenant_id')::UUID);
CREATE POLICY artifact_tokens_tenant_isolation ON artifact_download_tokens
    USING (tenant_id = current_setting('app.tenant_id')::UUID);
CREATE POLICY artifact_compat_public_read ON artifact_compatibility_rules USING (TRUE);
CREATE POLICY artifact_service_role ON artifact_records
    USING (current_setting('role') = 'service_role');
CREATE POLICY artifact_audit_service_role ON artifact_audit_log
    USING (current_setting('role') = 'service_role');

CREATE INDEX IF NOT EXISTS idx_artifact_tenant_status   ON artifact_records(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_artifact_type_version    ON artifact_records(artifact_type, version);
CREATE INDEX IF NOT EXISTS idx_artifact_sha256          ON artifact_records(sha256);
CREATE INDEX IF NOT EXISTS idx_artifact_audit_artifact  ON artifact_audit_log(artifact_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_audit_tenant    ON artifact_audit_log(tenant_id, action, ts DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_tokens_artifact ON artifact_download_tokens(artifact_id, expires_at);

CREATE OR REPLACE VIEW vw_downloadable_artifacts AS
SELECT ar.*, COUNT(aal.entry_id) AS audit_events
FROM artifact_records ar
LEFT JOIN artifact_audit_log aal ON aal.artifact_id = ar.artifact_id
WHERE ar.status = 'published'
GROUP BY ar.artifact_id;

CREATE OR REPLACE FUNCTION verify_artifact_audit_chain(p_artifact_id UUID DEFAULT NULL)
RETURNS TABLE(total_records BIGINT, is_valid BOOLEAN) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT COUNT(*)::BIGINT, TRUE
    FROM artifact_audit_log
    WHERE (p_artifact_id IS NULL OR artifact_id = p_artifact_id);
END;
$$;

COMMIT;
