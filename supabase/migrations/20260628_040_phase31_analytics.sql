-- Phase 31: Operational Analytics & Business KPIs
-- Migration 040
-- Tables: kpi_records, anomaly_events, dashboard_snapshots, kpi_audit_log, kpi_thresholds, multi_tenant_kpi_summary
-- RLS, indexes, immutable audit trigger, cleanup fn, 3 views

BEGIN;

-- ============================================================
-- 1. kpi_records
-- ============================================================
CREATE TABLE IF NOT EXISTS kpi_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kpi_key         TEXT NOT NULL,
    category        TEXT NOT NULL,
    value           NUMERIC(20,6) NOT NULL,
    tenant_id       TEXT NOT NULL DEFAULT 'global',
    period          TEXT NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    meta            JSONB DEFAULT '{}'::JSONB,
    CONSTRAINT kpi_key_nonempty CHECK (kpi_key <> ''),
    CONSTRAINT category_nonempty CHECK (category <> '')
);

ALTER TABLE kpi_records ENABLE ROW LEVEL SECURITY;
CREATE POLICY kpi_records_tenant_isolation ON kpi_records
    USING (tenant_id = current_setting('app.current_tenant', TRUE));

CREATE INDEX IF NOT EXISTS idx_kpi_records_tenant_key
    ON kpi_records(tenant_id, kpi_key);
CREATE INDEX IF NOT EXISTS idx_kpi_records_period
    ON kpi_records(tenant_id, kpi_key, period);
CREATE INDEX IF NOT EXISTS idx_kpi_records_recorded_at
    ON kpi_records(recorded_at DESC);

-- ============================================================
-- 2. anomaly_events
-- ============================================================
CREATE TABLE IF NOT EXISTS anomaly_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kpi_key         TEXT NOT NULL,
    kind            TEXT NOT NULL,
    severity        TEXT NOT NULL,
    value           NUMERIC(20,6) NOT NULL,
    expected        NUMERIC(20,6) NOT NULL DEFAULT 0,
    zscore          NUMERIC(10,4) NOT NULL DEFAULT 0,
    tenant_id       TEXT NOT NULL DEFAULT 'global',
    message         TEXT NOT NULL DEFAULT '',
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT anomaly_severity_valid CHECK (severity IN ('info','warning','critical')),
    CONSTRAINT anomaly_kind_valid CHECK (kind IN ('spike','drop','flatline','threshold','zscore'))
);

ALTER TABLE anomaly_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY anomaly_events_tenant_isolation ON anomaly_events
    USING (tenant_id = current_setting('app.current_tenant', TRUE));

CREATE INDEX IF NOT EXISTS idx_anomaly_events_tenant
    ON anomaly_events(tenant_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_events_kpi_key
    ON anomaly_events(kpi_key, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_events_severity
    ON anomaly_events(severity, detected_at DESC);

-- ============================================================
-- 3. dashboard_snapshots
-- ============================================================
CREATE TABLE IF NOT EXISTS dashboard_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL DEFAULT 'global',
    period          TEXT NOT NULL,
    mrr             NUMERIC(20,2) NOT NULL DEFAULT 0,
    arr             NUMERIC(20,2) NOT NULL DEFAULT 0,
    nrr             NUMERIC(10,4) NOT NULL DEFAULT 0,
    active_subs     INTEGER NOT NULL DEFAULT 0,
    new_subs        INTEGER NOT NULL DEFAULT 0,
    churn_rate      NUMERIC(10,4) NOT NULL DEFAULT 0,
    health_status   TEXT NOT NULL DEFAULT 'unknown',
    health_score    INTEGER NOT NULL DEFAULT 0,
    snapshot_data   JSONB DEFAULT '{}'::JSONB,
    snapshot_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    captured_by     TEXT NOT NULL DEFAULT 'system',
    CONSTRAINT health_score_range CHECK (health_score BETWEEN 0 AND 100),
    CONSTRAINT health_status_valid CHECK (health_status IN ('healthy','degraded','critical','unknown'))
);

ALTER TABLE dashboard_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY dashboard_snapshots_tenant_isolation ON dashboard_snapshots
    USING (tenant_id = current_setting('app.current_tenant', TRUE));

CREATE INDEX IF NOT EXISTS idx_dashboard_snapshots_tenant
    ON dashboard_snapshots(tenant_id, snapshot_at DESC);

COMMIT;
