-- Phase 35: Final Acceptance Runs
-- Migration: 20260628_045a_phase35_final_acceptance.sql

BEGIN;

CREATE TABLE IF NOT EXISTS acceptance_runs (
    run_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_type    TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','running','passed','failed','skipped')),
    tenant_id   TEXT        NOT NULL DEFAULT 'system',
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    duration_ms INTEGER,
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS acceptance_findings (
    id          BIGSERIAL   PRIMARY KEY,
    run_id      UUID        NOT NULL REFERENCES acceptance_runs(run_id),
    severity    TEXT        NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    category    TEXT        NOT NULL,
    description TEXT        NOT NULL,
    resolved    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_acceptance_runs_status   ON acceptance_runs(status);
CREATE INDEX IF NOT EXISTS idx_acceptance_runs_tenant   ON acceptance_runs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_acceptance_findings_run  ON acceptance_findings(run_id);
CREATE INDEX IF NOT EXISTS idx_acceptance_findings_sev  ON acceptance_findings(severity);

ALTER TABLE acceptance_runs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE acceptance_findings ENABLE ROW LEVEL SECURITY;

CREATE POLICY acceptance_runs_service     ON acceptance_runs     FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY acceptance_findings_service ON acceptance_findings FOR ALL USING (auth.role() = 'service_role');

COMMIT;
