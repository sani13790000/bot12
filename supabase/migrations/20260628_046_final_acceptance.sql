-- =============================================================================
-- Migration 046 -- Final Acceptance Criteria Gate
-- Phase 36 -- Final Acceptance: Production Readiness Verification
-- =============================================================================

BEGIN;

-- acceptance_runs
CREATE TABLE IF NOT EXISTS acceptance_runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    run_by          TEXT        NOT NULL,
    decision        TEXT        NOT NULL CHECK (decision IN ('GO','NO_GO','CONDITIONAL_GO')),
    pass_count      INT         NOT NULL CHECK (pass_count >= 0),
    fail_count      INT         NOT NULL CHECK (fail_count >= 0),
    total_tests     INT         NOT NULL CHECK (total_tests >= 0),
    phases_completed INT        NOT NULL DEFAULT 30,
    audit_chain_ok  BOOLEAN     NOT NULL DEFAULT FALSE,
    notes           TEXT,
    run_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT acceptance_criteria_sum CHECK (pass_count + fail_count <= 23)
);
ALTER TABLE acceptance_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY acceptance_runs_tenant ON acceptance_runs
    USING (tenant_id = current_setting('app.tenant_id')::UUID);

-- acceptance_criteria
CREATE TABLE IF NOT EXISTS acceptance_criteria (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID        NOT NULL REFERENCES acceptance_runs(id) ON DELETE CASCADE,
    criteria_id     TEXT        NOT NULL,
    criteria_name   TEXT        NOT NULL,
    result          TEXT        NOT NULL CHECK (result IN ('PASS','FAIL','WARN')),
    details         TEXT,
    severity        TEXT        NOT NULL CHECK (severity IN ('CRITICAL','HIGH','MEDIUM','LOW')),
    is_blocking     BOOLEAN     NOT NULL DEFAULT TRUE,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE acceptance_criteria ENABLE ROW LEVEL SECURITY;
CREATE POLICY acceptance_criteria_tenant ON acceptance_criteria
    USING (run_id IN (SELECT id FROM acceptance_runs
                      WHERE tenant_id = current_setting('app.tenant_id')::UUID));

-- production_risks
CREATE TABLE IF NOT EXISTS production_risks (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    risk_id         TEXT        NOT NULL,
    description     TEXT        NOT NULL,
    risk_level      TEXT        NOT NULL CHECK (risk_level IN ('CRITICAL','HIGH','MEDIUM','LOW')),
    owner           TEXT        NOT NULL,
    sprint          TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'OPEN'
                    CHECK (status IN ('OPEN','MITIGATED','ACCEPTED','CLOSED')),
    mitigation_plan TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT production_risks_unique UNIQUE (tenant_id, risk_id)
);
ALTER TABLE production_risks ENABLE ROW LEVEL SECURITY;
CREATE POLICY production_risks_tenant ON production_risks
    USING (tenant_id = current_setting('app.tenant_id')::UUID);

-- deployment_manifests
CREATE TABLE IF NOT EXISTS deployment_manifests (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID        NOT NULL,
    version                 TEXT        NOT NULL,
    environment             TEXT        NOT NULL CHECK (environment IN ('staging','production')),
    has_dockerfile          BOOLEAN     NOT NULL DEFAULT FALSE,
    has_compose_prod        BOOLEAN     NOT NULL DEFAULT FALSE,
    has_compose_staging     BOOLEAN     NOT NULL DEFAULT FALSE,
    has_healthcheck         BOOLEAN     NOT NULL DEFAULT FALSE,
    non_root_user           BOOLEAN     NOT NULL DEFAULT FALSE,
    multi_stage_build       BOOLEAN     NOT NULL DEFAULT FALSE,
    pinned_base_image       BOOLEAN     NOT NULL DEFAULT FALSE,
    has_env_file_template   BOOLEAN     NOT NULL DEFAULT FALSE,
    has_migration_script    BOOLEAN     NOT NULL DEFAULT FALSE,
    has_rollback_plan       BOOLEAN     NOT NULL DEFAULT FALSE,
    readiness_score         INT         NOT NULL CHECK (readiness_score BETWEEN 0 AND 10),
    is_production_ready     BOOLEAN     NOT NULL DEFAULT FALSE,
    deployed_at             TIMESTAMPTZ,
    deployed_by             TEXT,
    git_sha                 CHAR(40),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE deployment_manifests ENABLE ROW LEVEL SECURITY;
CREATE POLICY deployment_manifests_tenant ON deployment_manifests
    USING (tenant_id = current_setting('app.tenant_id')::UUID);

-- acceptance_audit_log
CREATE TABLE IF NOT EXISTS acceptance_audit_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    seq             INT         NOT NULL,
    action          TEXT        NOT NULL,
    actor           TEXT        NOT NULL,
    criteria        TEXT        NOT NULL,
    result          TEXT        NOT NULL,
    detail          JSONB       NOT NULL DEFAULT '{}',
    chain_hash      CHAR(64)    NOT NULL,
    reason          TEXT,
    ts              DOUBLE PRECISION NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE acceptance_audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY acceptance_audit_tenant ON acceptance_audit_log
    USING (tenant_id = current_setting('app.tenant_id')::UUID);

CREATE OR REPLACE FUNCTION acceptance_audit_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'acceptance_audit_log is immutable: % on %', TG_OP, TG_TABLE_NAME;
END;
$$;
CREATE TRIGGER trg_acceptance_audit_immutable
    BEFORE UPDATE OR DELETE ON acceptance_audit_log
    FOR EACH ROW EXECUTE FUNCTION acceptance_audit_immutable();

-- checklist_items
CREATE TABLE IF NOT EXISTS checklist_items (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID        NOT NULL REFERENCES acceptance_runs(id) ON DELETE CASCADE,
    item_id         TEXT        NOT NULL,
    item_name       TEXT        NOT NULL,
    criteria_id     TEXT        NOT NULL,
    passed          BOOLEAN     NOT NULL DEFAULT FALSE,
    is_blocking     BOOLEAN     NOT NULL DEFAULT TRUE,
    note            TEXT,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE checklist_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY checklist_items_tenant ON checklist_items
    USING (run_id IN (SELECT id FROM acceptance_runs
                      WHERE tenant_id = current_setting('app.tenant_id')::UUID));

-- indexes
CREATE INDEX IF NOT EXISTS idx_acceptance_runs_tenant    ON acceptance_runs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_acceptance_runs_decision  ON acceptance_runs(decision);
CREATE INDEX IF NOT EXISTS idx_acceptance_runs_run_at    ON acceptance_runs(run_at DESC);
CREATE INDEX IF NOT EXISTS idx_acceptance_criteria_run   ON acceptance_criteria(run_id);
CREATE INDEX IF NOT EXISTS idx_production_risks_tenant   ON production_risks(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_production_risks_level    ON production_risks(risk_level);
CREATE INDEX IF NOT EXISTS idx_deployment_manifests_env  ON deployment_manifests(tenant_id, environment);
CREATE INDEX IF NOT EXISTS idx_acceptance_audit_tenant   ON acceptance_audit_log(tenant_id, seq);
CREATE INDEX IF NOT EXISTS idx_acceptance_audit_chain    ON acceptance_audit_log(chain_hash);
CREATE INDEX IF NOT EXISTS idx_checklist_run             ON checklist_items(run_id);

-- views
CREATE OR REPLACE VIEW vw_latest_acceptance_runs AS
SELECT DISTINCT ON (tenant_id)
    id, tenant_id, decision, pass_count, fail_count,
    total_tests, audit_chain_ok, run_at
FROM acceptance_runs
ORDER BY tenant_id, run_at DESC;

CREATE OR REPLACE VIEW vw_open_production_risks AS
SELECT tenant_id, risk_id, description, risk_level, owner, sprint, status, created_at
FROM production_risks
WHERE status = 'OPEN'
ORDER BY CASE risk_level WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 END;

CREATE OR REPLACE VIEW vw_acceptance_audit_summary AS
SELECT tenant_id, COUNT(*) AS total_events,
    COUNT(*) FILTER (WHERE result='PASS') AS pass_events,
    COUNT(*) FILTER (WHERE result='FAIL') AS fail_events,
    MIN(created_at) AS first_event, MAX(created_at) AS last_event
FROM acceptance_audit_log GROUP BY tenant_id;

CREATE OR REPLACE VIEW vw_production_readiness_summary AS
SELECT ar.tenant_id, ar.decision, ar.pass_count, ar.fail_count,
    ar.total_tests, ar.phases_completed, ar.audit_chain_ok,
    COUNT(pr.*) FILTER (WHERE pr.status='OPEN' AND pr.risk_level='CRITICAL') AS critical_risks_open,
    COUNT(pr.*) FILTER (WHERE pr.status='OPEN' AND pr.risk_level='HIGH') AS high_risks_open,
    ar.run_at
FROM vw_latest_acceptance_runs ar
LEFT JOIN production_risks pr ON pr.tenant_id = ar.tenant_id
GROUP BY ar.id, ar.tenant_id, ar.decision, ar.pass_count, ar.fail_count,
    ar.total_tests, ar.phases_completed, ar.audit_chain_ok, ar.run_at;

CREATE OR REPLACE FUNCTION cleanup_old_acceptance_runs(keep_days INT DEFAULT 90)
RETURNS INT LANGUAGE plpgsql AS $$
DECLARE deleted INT;
BEGIN
    DELETE FROM acceptance_runs
    WHERE run_at < NOW() - (keep_days || ' days')::INTERVAL AND decision = 'GO';
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$;

CREATE OR REPLACE FUNCTION verify_acceptance_audit_chain(p_tenant_id UUID)
RETURNS BOOLEAN LANGUAGE plpgsql AS $$
DECLARE r RECORD; chain_ok BOOLEAN := TRUE;
BEGIN
    FOR r IN SELECT chain_hash FROM acceptance_audit_log
        WHERE tenant_id = p_tenant_id ORDER BY seq ASC
    LOOP
        IF r.chain_hash IS NULL OR length(r.chain_hash) != 64 THEN
            chain_ok := FALSE;
        END IF;
    END LOOP;
    RETURN chain_ok;
END;
$$;

COMMIT;
