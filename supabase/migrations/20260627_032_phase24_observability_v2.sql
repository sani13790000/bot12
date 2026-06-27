-- Migration 032: Phase 24 Observability v2
-- P24-SQL-1: slo_records table
-- P24-SQL-2: alert_history table
-- P24-SQL-3: anomaly_events table
-- P24-SQL-4: health_snapshots table
-- P24-SQL-5: metric_aggregates table
-- P24-SQL-6: oncall_schedule table
-- P24-SQL-7: RLS on all 6 tables
-- P24-SQL-8: indexes for query performance

BEGIN;

CREATE TABLE IF NOT EXISTS slo_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    slo_name        TEXT NOT NULL,
    is_good         BOOLEAN NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    burn_rate       NUMERIC(10,4),
    error_budget    NUMERIC(10,6),
    status          TEXT NOT NULL DEFAULT 'ok'
                    CHECK (status IN ('ok','warning','critical','breached'))
);

CREATE TABLE IF NOT EXISTS alert_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id        TEXT NOT NULL,
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    rule_name       TEXT NOT NULL,
    severity        TEXT NOT NULL,
    message         TEXT NOT NULL,
    detail          JSONB,
    channels        TEXT[],
    runbook_url     TEXT,
    deduped         BOOLEAN NOT NULL DEFAULT FALSE,
    fired_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS anomaly_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    metric_name     TEXT NOT NULL,
    anomaly_type    TEXT NOT NULL CHECK (anomaly_type IN ('zscore','cusum')),
    value           NUMERIC,
    z_score         NUMERIC(10,4),
    cusum_pos       NUMERIC(10,4),
    cusum_neg       NUMERIC(10,4),
    mean            NUMERIC(10,6),
    std             NUMERIC(10,6),
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS health_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    status          TEXT NOT NULL CHECK (status IN ('healthy','degraded','unhealthy')),
    components      JSONB,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS metric_aggregates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    metric_name     TEXT NOT NULL,
    metric_type     TEXT NOT NULL CHECK (metric_type IN ('counter','gauge','histogram','summary')),
    labels          JSONB,
    value           NUMERIC,
    p50             NUMERIC,
    p95             NUMERIC,
    p99             NUMERIC,
    count           INTEGER,
    aggregated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    window_start    TIMESTAMPTZ,
    window_end      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS oncall_schedule (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    name            TEXT NOT NULL,
    channel         TEXT NOT NULL,
    address         TEXT NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 0 CHECK (priority IN (0,1,2)),
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE slo_records       ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_history     ENABLE ROW LEVEL SECURITY;
ALTER TABLE anomaly_events    ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_snapshots  ENABLE ROW LEVEL SECURITY;
ALTER TABLE metric_aggregates ENABLE ROW LEVEL SECURITY;
ALTER TABLE oncall_schedule   ENABLE ROW LEVEL SECURITY;

CREATE POLICY slo_tenant ON slo_records
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)
           OR current_setting('app.is_admin', TRUE) = 'true');
CREATE POLICY alert_tenant ON alert_history
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)
           OR current_setting('app.is_admin', TRUE) = 'true');
CREATE POLICY anomaly_tenant ON anomaly_events
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)
           OR current_setting('app.is_admin', TRUE) = 'true');
CREATE POLICY health_tenant ON health_snapshots
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)
           OR current_setting('app.is_admin', TRUE) = 'true');
CREATE POLICY metric_tenant ON metric_aggregates
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)
           OR current_setting('app.is_admin', TRUE) = 'true');
CREATE POLICY oncall_tenant ON oncall_schedule
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)
           OR current_setting('app.is_admin', TRUE) = 'true');

CREATE INDEX IF NOT EXISTS idx_slo_tenant_name_ts ON slo_records(tenant_id, slo_name, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_slo_status ON slo_records(status, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_tenant_rule ON alert_history(tenant_id, rule_name, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_severity ON alert_history(severity, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_metric_ts ON anomaly_events(metric_name, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_tenant_ts ON health_snapshots(tenant_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_metric_name_ts ON metric_aggregates(metric_name, aggregated_at DESC);
CREATE INDEX IF NOT EXISTS idx_oncall_tenant_priority ON oncall_schedule(tenant_id, priority) WHERE active = TRUE;

CREATE OR REPLACE FUNCTION cleanup_old_observability_data(
    p_slo_days INT DEFAULT 90,
    p_metric_days INT DEFAULT 30,
    p_anomaly_days INT DEFAULT 30
) RETURNS TABLE(slo_deleted INT, metric_deleted INT, anomaly_deleted INT) AS $$
DECLARE
    v_slo    INT;
    v_metric INT;
    v_anomaly INT;
BEGIN
    DELETE FROM slo_records WHERE recorded_at < now() - (p_slo_days || ' days')::INTERVAL;
    GET DIAGNOSTICS v_slo = ROW_COUNT;
    DELETE FROM metric_aggregates WHERE aggregated_at < now() - (p_metric_days || ' days')::INTERVAL;
    GET DIAGNOSTICS v_metric = ROW_COUNT;
    DELETE FROM anomaly_events WHERE detected_at < now() - (p_anomaly_days || ' days')::INTERVAL;
    GET DIAGNOSTICS v_anomaly = ROW_COUNT;
    RETURN QUERY SELECT v_slo, v_metric, v_anomaly;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE VIEW vw_slo_summary AS
SELECT tenant_id, slo_name,
    COUNT(*) FILTER (WHERE is_good) AS good_count,
    COUNT(*) FILTER (WHERE NOT is_good) AS bad_count,
    COUNT(*) AS total_count,
    ROUND(COUNT(*) FILTER (WHERE is_good)::NUMERIC / NULLIF(COUNT(*),0), 6) AS success_rate,
    MAX(recorded_at) AS last_recorded
FROM slo_records
WHERE recorded_at > now() - INTERVAL '30 days'
GROUP BY tenant_id, slo_name;

CREATE OR REPLACE VIEW vw_active_alerts AS
SELECT tenant_id, rule_name, severity,
    COUNT(*) FILTER (WHERE NOT deduped) AS fired_count,
    MAX(fired_at) AS last_fired
FROM alert_history
WHERE fired_at > now() - INTERVAL '24 hours'
GROUP BY tenant_id, rule_name, severity
ORDER BY last_fired DESC;

COMMIT;
