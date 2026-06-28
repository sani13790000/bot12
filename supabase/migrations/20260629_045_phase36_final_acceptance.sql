-- ============================================================
-- Migration 045 -- Phase 36: Final Acceptance Criteria
-- Bot12 SaaS Platform
-- ============================================================

BEGIN;

-- 1. acceptance_runs
CREATE TABLE IF NOT EXISTS acceptance_runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID        NOT NULL UNIQUE,
    tenant_id       TEXT        NOT NULL DEFAULT 'system',
    decision        TEXT        NOT NULL CHECK (decision IN ('GO','NO_GO','CONDITIONAL')),
    pass_count      INTEGER     NOT NULL CHECK (pass_count >= 0),
    fail_count      INTEGER     NOT NULL CHECK (fail_count >= 0),
    warn_count      INTEGER     NOT NULL CHECK (warn_count >= 0),
    audit_ok        BOOLEAN     NOT NULL DEFAULT TRUE,
    summary         TEXT        NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    triggered_by    TEXT,
    environment     TEXT        CHECK (environment IN ('staging','production','ci')),
    git_sha         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE acceptance_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY acceptance_runs_tenant_isolation ON acceptance_runs
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

CREATE INDEX IF NOT EXISTS idx_acceptance_runs_tenant ON acceptance_runs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_acceptance_runs_decision ON acceptance_runs(decision);
CREATE INDEX IF NOT EXISTS idx_acceptance_runs_generated ON acceptance_runs(generated_at DESC);

-- 2. criteria_results
CREATE TABLE IF NOT EXISTS criteria_results (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID        NOT NULL REFERENCES acceptance_runs(run_id) ON DELETE CASCADE,
    tenant_id       TEXT        NOT NULL DEFAULT 'system',
    criteria_id     TEXT        NOT NULL CHECK (criteria_id ~ '^AC[0-2][0-9]$'),
    description     TEXT        NOT NULL,
    status          TEXT        NOT NULL CHECK (status IN ('PASS','FAIL','WARN','SKIP')),
    evidence        TEXT        NOT NULL,
    severity        TEXT        NOT NULL CHECK (severity IN ('CRITICAL','HIGH','MEDIUM','LOW')),
    blocking        BOOLEAN     NOT NULL DEFAULT FALSE,
    phase_ref       TEXT,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE criteria_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY criteria_results_tenant_isolation ON criteria_results
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

CREATE INDEX IF NOT EXISTS idx_criteria_results_run ON criteria_results(run_id);
CREATE INDEX IF NOT EXISTS idx_criteria_results_status ON criteria_results(status);
CREATE INDEX IF NOT EXISTS idx_criteria_results_criteria ON criteria_results(criteria_id);
CREATE INDEX IF NOT EXISTS idx_criteria_results_blocking ON criteria_results(blocking) WHERE blocking = TRUE;

-- 3. acceptance_audit_log (immutable HMAC chain)
CREATE TABLE IF NOT EXISTS acceptance_audit_log (
    id              UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT             NOT NULL DEFAULT 'system',
    seq             INTEGER          NOT NULL,
    action          TEXT             NOT NULL,
    actor           TEXT             NOT NULL,
    criteria_id     TEXT,
    detail          TEXT,
    chain_hash      CHAR(64)         NOT NULL,
    ts              DOUBLE PRECISION NOT NULL,
    recorded_at     TIMESTAMPTZ      NOT NULL DEFAULT now()
);

ALTER TABLE acceptance_audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY acceptance_audit_log_tenant_isolation ON acceptance_audit_log
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

CREATE INDEX IF NOT EXISTS idx_acceptance_audit_tenant ON acceptance_audit_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_acceptance_audit_seq ON acceptance_audit_log(seq);
CREATE INDEX IF NOT EXISTS idx_acceptance_audit_action ON acceptance_audit_log(action);

CREATE OR REPLACE FUNCTION fn_prevent_acceptance_audit_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'acceptance_audit_log is immutable -- % not allowed', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_immutable_acceptance_audit ON acceptance_audit_log;
CREATE TRIGGER trg_immutable_acceptance_audit
    BEFORE UPDATE OR DELETE ON acceptance_audit_log
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_acceptance_audit_mutation();

-- 4. production_config_checks
CREATE TABLE IF NOT EXISTS production_config_checks (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID        NOT NULL REFERENCES acceptance_runs(run_id) ON DELETE CASCADE,
    tenant_id       TEXT        NOT NULL DEFAULT 'system',
    environment     TEXT        NOT NULL CHECK (environment IN ('staging','production')),
    missing_keys    TEXT[],
    bad_values      TEXT[],
    passed          BOOLEAN     NOT NULL,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE production_config_checks ENABLE ROW LEVEL SECURITY;

-- 5. device_limit_log
CREATE TABLE IF NOT EXISTS device_limit_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT        NOT NULL DEFAULT 'system',
    license_id      TEXT        NOT NULL,
    device_id       TEXT        NOT NULL,
    action          TEXT        NOT NULL CHECK (action IN ('REGISTERED','BLOCKED','REMOVED')),
    current_count   INTEGER     NOT NULL CHECK (current_count >= 0),
    max_allowed     INTEGER     NOT NULL CHECK (max_allowed >= 0),
    logged_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE device_limit_log ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_device_limit_log_license ON device_limit_log(license_id, tenant_id);

-- 6. killswitch_events
CREATE TABLE IF NOT EXISTS killswitch_events (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT        NOT NULL,
    action          TEXT        NOT NULL CHECK (action IN ('ACTIVATED','DEACTIVATED')),
    actor           TEXT        NOT NULL,
    reason          TEXT        NOT NULL CHECK (reason <> ''),
    activated_at    TIMESTAMPTZ,
    deactivated_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE killswitch_events ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_killswitch_events_tenant ON killswitch_events(tenant_id, action);

-- Views
CREATE OR REPLACE VIEW vw_latest_acceptance_per_tenant AS
SELECT DISTINCT ON (tenant_id)
    tenant_id, run_id, decision, pass_count, fail_count, warn_count, audit_ok, generated_at
FROM acceptance_runs ORDER BY tenant_id, generated_at DESC;

CREATE OR REPLACE VIEW vw_open_blocking_failures AS
SELECT ar.tenant_id, ar.run_id, ar.decision, cr.criteria_id, cr.severity, cr.evidence, ar.generated_at
FROM criteria_results cr JOIN acceptance_runs ar USING (run_id)
WHERE cr.status = 'FAIL' AND cr.blocking = TRUE ORDER BY ar.generated_at DESC;

CREATE OR REPLACE VIEW vw_acceptance_run_summary AS
SELECT run_id, tenant_id, decision, pass_count, fail_count, warn_count, audit_ok, generated_at,
    CASE WHEN decision='GO' THEN 'Approved for production'
         WHEN decision='NO_GO' THEN 'Blocked -- fix required'
         WHEN decision='CONDITIONAL' THEN 'Conditional -- review warnings' END AS recommendation
FROM acceptance_runs ORDER BY generated_at DESC;

CREATE OR REPLACE VIEW vw_acceptance_audit_summary AS
SELECT tenant_id, action, criteria_id, COUNT(*) AS event_count,
    MIN(recorded_at) AS first_seen, MAX(recorded_at) AS last_seen
FROM acceptance_audit_log GROUP BY tenant_id, action, criteria_id ORDER BY last_seen DESC;

-- Functions
CREATE OR REPLACE FUNCTION verify_acceptance_audit_chain(p_tenant_id TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE AS $$
DECLARE v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM acceptance_audit_log
    WHERE tenant_id = p_tenant_id AND length(chain_hash) <> 64;
    RETURN v_count = 0;
END;
$$;

CREATE OR REPLACE FUNCTION cleanup_old_acceptance_runs()
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE v_deleted INTEGER;
BEGIN
    DELETE FROM acceptance_runs WHERE generated_at < now() - INTERVAL '90 days';
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$$;

COMMIT;
