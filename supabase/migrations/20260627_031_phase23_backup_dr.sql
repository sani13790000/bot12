-- PHASE 23: Backup, Restore & Disaster Recovery
-- Migration: 20260627_031_phase23_backup_dr.sql

BEGIN;

CREATE TABLE IF NOT EXISTS backup_runs (
    backup_id           TEXT        PRIMARY KEY,
    tenant_id           TEXT        NOT NULL DEFAULT 'default',
    category            TEXT        NOT NULL,
    backup_type         TEXT        NOT NULL,
    status              TEXT        NOT NULL DEFAULT 'pending',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    size_bytes          BIGINT      NOT NULL DEFAULT 0,
    checksum_sha256     TEXT        NOT NULL DEFAULT '',
    encryption_key_id   TEXT,
    encrypted           BOOLEAN     NOT NULL DEFAULT TRUE,
    compressed          BOOLEAN     NOT NULL DEFAULT TRUE,
    offsite_url         TEXT,
    offsite_copy        BOOLEAN     NOT NULL DEFAULT TRUE,
    pitr_lsn            TEXT,
    manifest_id         TEXT,
    manifest_hmac_sig   TEXT,
    error_msg           TEXT,
    actor               TEXT        NOT NULL DEFAULT 'scheduler',
    retention_hours     INTEGER     NOT NULL DEFAULT 720,
    tags                JSONB       NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS restore_runs (
    restore_id      TEXT        PRIMARY KEY,
    tenant_id       TEXT        NOT NULL DEFAULT 'default',
    backup_id       TEXT        NOT NULL REFERENCES backup_runs(backup_id),
    target_env      TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'pending',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    pitr_target     DOUBLE PRECISION,
    validations     JSONB       NOT NULL DEFAULT '[]',
    error_msg       TEXT,
    actor           TEXT        NOT NULL DEFAULT 'ops'
);

CREATE TABLE IF NOT EXISTS pitr_records (
    pitr_id                 TEXT        PRIMARY KEY,
    tenant_id               TEXT        NOT NULL DEFAULT 'default',
    target_ts               DOUBLE PRECISION NOT NULL,
    base_backup_id          TEXT        NOT NULL REFERENCES backup_runs(backup_id),
    lsn                     TEXT,
    wal_segments_applied    INTEGER     NOT NULL DEFAULT 0,
    status                  TEXT        NOT NULL DEFAULT 'pending',
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ,
    error_msg               TEXT,
    actor                   TEXT        NOT NULL DEFAULT 'ops'
);

CREATE TABLE IF NOT EXISTS dr_drills (
    drill_id        TEXT        PRIMARY KEY,
    tenant_id       TEXT        NOT NULL DEFAULT 'default',
    drill_name      TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'scheduled',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    steps           JSONB       NOT NULL DEFAULT '[]',
    rto_seconds     DOUBLE PRECISION NOT NULL DEFAULT 14400,
    rpo_seconds     DOUBLE PRECISION NOT NULL DEFAULT 3600,
    actual_rto      DOUBLE PRECISION,
    actual_rpo      DOUBLE PRECISION,
    error_msg       TEXT,
    actor           TEXT        NOT NULL DEFAULT 'dr-operator'
);

CREATE TABLE IF NOT EXISTS backup_policy (
    policy_id           TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    tenant_id           TEXT        NOT NULL DEFAULT 'default',
    category            TEXT        NOT NULL,
    backup_type         TEXT        NOT NULL DEFAULT 'full',
    retention_hours     INTEGER     NOT NULL DEFAULT 720,
    encrypt             BOOLEAN     NOT NULL DEFAULT TRUE,
    compress            BOOLEAN     NOT NULL DEFAULT TRUE,
    verify_after        BOOLEAN     NOT NULL DEFAULT TRUE,
    offsite_copy        BOOLEAN     NOT NULL DEFAULT TRUE,
    max_size_mb         INTEGER     NOT NULL DEFAULT 10240,
    schedule_cron       TEXT        NOT NULL DEFAULT '0 2 * * *',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, category)
);

CREATE TABLE IF NOT EXISTS backup_audit_log (
    entry_id    TEXT        PRIMARY KEY,
    tenant_id   TEXT        NOT NULL DEFAULT 'default',
    event       TEXT        NOT NULL,
    backup_id   TEXT,
    actor       TEXT        NOT NULL,
    ts          DOUBLE PRECISION NOT NULL,
    detail      JSONB       NOT NULL DEFAULT '{}',
    chain_hash  TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION prevent_backup_audit_modification()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'backup_audit_log is immutable';
END;
$$;

DROP TRIGGER IF EXISTS backup_audit_immutable_upd ON backup_audit_log;
CREATE TRIGGER backup_audit_immutable_upd
    BEFORE UPDATE OR DELETE ON backup_audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_backup_audit_modification();

ALTER TABLE backup_runs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE restore_runs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE pitr_records     ENABLE ROW LEVEL SECURITY;
ALTER TABLE dr_drills        ENABLE ROW LEVEL SECURITY;
ALTER TABLE backup_policy    ENABLE ROW LEVEL SECURITY;
ALTER TABLE backup_audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY backup_runs_tenant_isolation ON backup_runs
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)
           OR current_setting('app.is_admin', TRUE) = 'true');

CREATE POLICY restore_runs_tenant_isolation ON restore_runs
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)
           OR current_setting('app.is_admin', TRUE) = 'true');

CREATE POLICY pitr_records_tenant_isolation ON pitr_records
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)
           OR current_setting('app.is_admin', TRUE) = 'true');

CREATE POLICY dr_drills_tenant_isolation ON dr_drills
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)
           OR current_setting('app.is_admin', TRUE) = 'true');

CREATE POLICY backup_policy_tenant_isolation ON backup_policy
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)
           OR current_setting('app.is_admin', TRUE) = 'true');

CREATE POLICY backup_audit_tenant_isolation ON backup_audit_log
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)
           OR current_setting('app.is_admin', TRUE) = 'true');

CREATE INDEX IF NOT EXISTS idx_backup_runs_tenant_category
    ON backup_runs (tenant_id, category, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_backup_runs_status
    ON backup_runs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_restore_runs_backup_id
    ON restore_runs (backup_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_pitr_records_tenant
    ON pitr_records (tenant_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_dr_drills_tenant_status
    ON dr_drills (tenant_id, status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_backup_audit_tenant_event
    ON backup_audit_log (tenant_id, event, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_backup_audit_backup_id
    ON backup_audit_log (backup_id, created_at DESC);

CREATE OR REPLACE FUNCTION cleanup_expired_backups()
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE purged_count INTEGER := 0;
BEGIN
    UPDATE backup_runs SET status = 'expired'
    WHERE status = 'success'
    AND created_at < NOW() - (retention_hours * INTERVAL '1 hour');
    GET DIAGNOSTICS purged_count = ROW_COUNT;
    RETURN purged_count;
END;
$$;

CREATE OR REPLACE VIEW vw_dr_drill_summary AS
SELECT tenant_id,
    COUNT(*) AS total_drills,
    COUNT(*) FILTER (WHERE status = 'passed') AS passed,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
    AVG(actual_rto) AS avg_rto_seconds,
    AVG(actual_rpo) AS avg_rpo_seconds,
    MAX(started_at) AS last_drill_at
FROM dr_drills GROUP BY tenant_id;

COMMIT;
