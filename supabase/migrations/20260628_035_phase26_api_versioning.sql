-- =============================================================
-- Phase 26: API Versioning & Backward Compatibility
-- Migration: 035
-- =============================================================
BEGIN;

-- 1. api_version_registry
CREATE TABLE IF NOT EXISTS api_version_registry (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version         VARCHAR(10) NOT NULL UNIQUE,
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','deprecated','sunset','experimental')),
    released_at     DATE NOT NULL,
    deprecated_at   DATE,
    sunset_at       DATE,
    deprecation_reason TEXT,
    deprecation_severity VARCHAR(10) DEFAULT 'info'
                        CHECK (deprecation_severity IN ('info','warning','critical')),
    successor_version VARCHAR(10),
    sunset_response_code INT NOT NULL DEFAULT 410,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO api_version_registry
    (version, status, released_at, deprecated_at, sunset_at,
     deprecation_reason, deprecation_severity, successor_version)
VALUES
    ('v1', 'deprecated', '2024-01-01', '2026-01-01', '2027-01-01',
     'V1 lacks tenant isolation and audit support', 'warning', 'v3'),
    ('v2', 'active', '2025-01-01', NULL, NULL, NULL, 'info', NULL),
    ('v3', 'active', '2026-01-01', NULL, NULL, NULL, 'info', NULL)
ON CONFLICT (version) DO NOTHING;

-- 2. endpoint_version_map
CREATE TABLE IF NOT EXISTS endpoint_version_map (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint        TEXT NOT NULL,
    version         VARCHAR(10) NOT NULL REFERENCES api_version_registry(version),
    tenant_id       UUID,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (endpoint, version)
);

-- 3. deprecation_notices
CREATE TABLE IF NOT EXISTS deprecation_notices (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version             VARCHAR(10) NOT NULL REFERENCES api_version_registry(version),
    endpoint            TEXT NOT NULL,
    message             TEXT NOT NULL,
    severity            VARCHAR(10) NOT NULL DEFAULT 'warning'
                            CHECK (severity IN ('info','warning','critical')),
    deprecated_at       DATE NOT NULL,
    sunset_at           DATE,
    successor_version   VARCHAR(10),
    successor_endpoint  TEXT,
    migration_guide_url TEXT,
    tenant_id           UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. version_audit_log (immutable)
CREATE TABLE IF NOT EXISTS version_audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id    UUID NOT NULL UNIQUE,
    action      VARCHAR(50) NOT NULL,
    version     VARCHAR(10) NOT NULL,
    endpoint    TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'system',
    tenant_id   UUID,
    detail      JSONB NOT NULL DEFAULT '{}',
    chain_hash  CHAR(64) NOT NULL,
    prev_hash   CHAR(64) NOT NULL,
    seq         BIGINT NOT NULL,
    ts          DOUBLE PRECISION NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Immutable trigger for version_audit_log
CREATE OR REPLACE FUNCTION prevent_version_audit_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'version_audit_log is immutable - UPDATE not allowed';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'version_audit_log is immutable - DELETE not allowed';
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_version_audit_immutable ON version_audit_log;
CREATE TRIGGER trg_version_audit_immutable
    BEFORE UPDATE OR DELETE ON version_audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_version_audit_mutation();

-- RLS
ALTER TABLE api_version_registry     ENABLE ROW LEVEL SECURITY;
ALTER TABLE endpoint_version_map     ENABLE ROW LEVEL SECURITY;
ALTER TABLE deprecation_notices      ENABLE ROW LEVEL SECURITY;
ALTER TABLE version_audit_log        ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY version_registry_service_rw ON api_version_registry
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY endpoint_map_tenant ON endpoint_version_map
    FOR ALL USING (
        tenant_id IS NULL OR
        tenant_id = (current_setting('app.tenant_id', TRUE))::UUID
    );

CREATE POLICY deprecation_tenant ON deprecation_notices
    FOR ALL USING (
        tenant_id IS NULL OR
        tenant_id = (current_setting('app.tenant_id', TRUE))::UUID
    );

CREATE POLICY version_audit_service ON version_audit_log
    FOR ALL TO service_role USING (TRUE);

CREATE POLICY version_audit_tenant ON version_audit_log
    FOR SELECT USING (
        tenant_id IS NULL OR
        tenant_id = (current_setting('app.tenant_id', TRUE))::UUID
    );

-- Indexes
CREATE INDEX IF NOT EXISTS idx_version_audit_version
    ON version_audit_log (version);

CREATE INDEX IF NOT EXISTS idx_version_audit_action
    ON version_audit_log (action);

CREATE INDEX IF NOT EXISTS idx_version_audit_tenant
    ON version_audit_log (tenant_id) WHERE tenant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_version_audit_seq
    ON version_audit_log (seq);

CREATE INDEX IF NOT EXISTS idx_version_audit_ts
    ON version_audit_log (ts DESC);

CREATE INDEX IF NOT EXISTS idx_endpoint_map_endpoint
    ON endpoint_version_map (endpoint, version);

CREATE INDEX IF NOT EXISTS idx_deprecation_version
    ON deprecation_notices (version);

-- Cleanup function
CREATE OR REPLACE FUNCTION cleanup_old_version_audit_logs(older_than_days INT DEFAULT 365)
RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
    deleted_count INT;
BEGIN
    deleted_count := 0;
    RETURN deleted_count;
END;
$$;

-- View: active versions
CREATE OR REPLACE VIEW vw_active_api_versions AS
SELECT
    version,
    status,
    released_at,
    deprecated_at,
    sunset_at,
    successor_version,
    deprecation_severity,
    CASE
        WHEN sunset_at IS NOT NULL
            THEN (sunset_at - CURRENT_DATE)
        ELSE NULL
    END AS days_until_sunset
FROM api_version_registry
WHERE status != 'sunset'
ORDER BY version;

-- View: version audit summary
CREATE OR REPLACE VIEW vw_version_audit_summary AS
SELECT
    version,
    action,
    COUNT(*) AS event_count,
    MAX(ts) AS last_event_ts
FROM version_audit_log
GROUP BY version, action
ORDER BY version, action;

COMMIT;
