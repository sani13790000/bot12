-- Migration 018: Phase 7-10 support tables
-- security_scores + scheduler_log + alert_log

BEGIN;

-- security_scores: Phase-10 score snapshots
CREATE TABLE IF NOT EXISTS security_scores (
    id         UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    score      FLOAT       NOT NULL CHECK (score BETWEEN 0 AND 100),
    level      TEXT        NOT NULL CHECK (level IN ('secure','moderate','high_risk','critical')),
    trend      TEXT        NOT NULL CHECK (trend IN ('improving','stable','degrading')),
    dimensions JSONB       NOT NULL DEFAULT '[]',
    top_risks  JSONB       NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_security_scores_created ON security_scores (created_at DESC);

-- security_alert_log: Phase-9 Telegram alert dedup tracking
CREATE TABLE IF NOT EXISTS security_alert_log (
    id           UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_type   TEXT        NOT NULL,
    severity     TEXT        NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    target       TEXT,
    message_hash TEXT        NOT NULL,
    admin_ids    JSONB       DEFAULT '[]',
    metadata     JSONB       DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alert_log_hash ON security_alert_log (message_hash, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_log_type ON security_alert_log (alert_type, created_at DESC);

-- security_scheduler_log: Phase-7 report run history
CREATE TABLE IF NOT EXISTS security_scheduler_log (
    id           UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id    TEXT,
    label        TEXT        NOT NULL DEFAULT 'scheduled',
    period_hours INT         NOT NULL DEFAULT 24,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_s   FLOAT,
    exports      JSONB       DEFAULT '{}',
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_scheduler_log_created ON security_scheduler_log (created_at DESC);

-- RLS
ALTER TABLE security_scores        ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_alert_log     ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_scheduler_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY scores_service_rw        ON security_scores        FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY alert_log_service_rw     ON security_alert_log     FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY scheduler_log_service_rw ON security_scheduler_log FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY scores_anon_none         ON security_scores        FOR ALL TO anon USING (false);
CREATE POLICY alert_log_anon_none      ON security_alert_log     FOR ALL TO anon USING (false);
CREATE POLICY scheduler_log_anon_none  ON security_scheduler_log FOR ALL TO anon USING (false);

-- Cleanup function
CREATE OR REPLACE FUNCTION cleanup_old_security_scores()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    DELETE FROM security_scores     WHERE created_at < NOW() - INTERVAL '7 days';
    DELETE FROM security_alert_log  WHERE created_at < NOW() - INTERVAL '30 days';
    DELETE FROM security_scheduler_log WHERE created_at < NOW() - INTERVAL '90 days';
END;
$$;

COMMIT;
