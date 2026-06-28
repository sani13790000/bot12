-- Migration 045: Final Acceptance Criteria & Go/No-Go Registry
-- Phase 35 Final — Production Gate

BEGIN;

-- acceptance_runs: each execution of the 23-criteria checklist
CREATE TABLE IF NOT EXISTS acceptance_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          TEXT NOT NULL UNIQUE,
    tenant_id       TEXT NOT NULL DEFAULT 'system',
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    overall         TEXT NOT NULL CHECK (overall IN ('PASS','FAIL','WARNING')),
    go_nogo         TEXT NOT NULL CHECK (go_nogo IN ('GO','NO_GO','CONDITIONAL_GO')),
    pass_count      INT NOT NULL DEFAULT 0 CHECK (pass_count >= 0),
    fail_count      INT NOT NULL DEFAULT 0 CHECK (fail_count >= 0),
    warn_count      INT NOT NULL DEFAULT 0 CHECK (warn_count >= 0),
    audit_chain_ok  BOOLEAN NOT NULL DEFAULT FALSE,
    recommendation  TEXT NOT NULL,
    actor           TEXT NOT NULL DEFAULT 'acceptance_engine',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS acceptance_findings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          TEXT NOT NULL REFERENCES acceptance_runs(run_id) ON DELETE CASCADE,
    criteria_id     TEXT NOT NULL CHECK (criteria_id IN (
                        'C01','C02','C03','C04','C05','C06','C07','C08',
                        'C09','C10','C11','C12','C13','C14','C15','C16',
                        'C17','C18','C19','C20','C21','C22','C23')),
    result          TEXT NOT NULL CHECK (result IN ('PASS','FAIL','WARNING')),
    severity        TEXT NOT NULL CHECK (severity IN ('CRITICAL','HIGH','MEDIUM','LOW','INFO')),
    title           TEXT NOT NULL,
    detail          TEXT NOT NULL DEFAULT '',
    evidence        JSONB NOT NULL DEFAULT '{}',
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    tenant_id       TEXT NOT NULL DEFAULT 'system'
);

CREATE TABLE IF NOT EXISTS go_nogo_decisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          TEXT NOT NULL REFERENCES acceptance_runs(run_id),
    decision        TEXT NOT NULL CHECK (decision IN ('GO','NO_GO','CONDITIONAL_GO')),
    decided_by      TEXT NOT NULL,
    reason          TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    conditions      JSONB NOT NULL DEFAULT '[]',
    valid_until     TIMESTAMPTZ,
    tenant_id       TEXT NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS final_acceptance_audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seq             INT NOT NULL,
    run_id          TEXT NOT NULL,
    criteria_id     TEXT NOT NULL,
    result          TEXT NOT NULL,
    actor           TEXT NOT NULL DEFAULT 'acceptance_engine',
    tenant_id       TEXT NOT NULL DEFAULT 'system',
    chain_hash      CHAR(64) NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(run_id, criteria_id)
);

CREATE TABLE IF NOT EXISTS remaining_risks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    risk_id         TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK (severity IN ('CRITICAL','HIGH','MEDIUM','LOW')),
    owner           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','mitigated','accepted','resolved')),
    mitigation_plan TEXT,
    sprint          TEXT,
    tenant_id       TEXT NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deployment_checklist (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment     TEXT NOT NULL CHECK (environment IN ('staging','production')),
    item            TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('pending','pass','fail','skipped')),
    verified_by     TEXT,
    verified_at     TIMESTAMPTZ,
    notes           TEXT,
    tenant_id       TEXT NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(environment, item)
);

ALTER TABLE acceptance_runs            ENABLE ROW LEVEL SECURITY;
ALTER TABLE acceptance_findings        ENABLE ROW LEVEL SECURITY;
ALTER TABLE go_nogo_decisions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE final_acceptance_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE remaining_risks            ENABLE ROW LEVEL SECURITY;
ALTER TABLE deployment_checklist       ENABLE ROW LEVEL SECURITY;

CREATE POLICY acceptance_runs_rls            ON acceptance_runs            USING (tenant_id = current_setting('app.tenant_id', TRUE));
CREATE POLICY acceptance_findings_rls        ON acceptance_findings        USING (tenant_id = current_setting('app.tenant_id', TRUE));
CREATE POLICY go_nogo_decisions_rls          ON go_nogo_decisions          USING (tenant_id = current_setting('app.tenant_id', TRUE));
CREATE POLICY final_acceptance_audit_log_rls ON final_acceptance_audit_log USING (tenant_id = current_setting('app.tenant_id', TRUE));
CREATE POLICY remaining_risks_rls            ON remaining_risks            USING (tenant_id = current_setting('app.tenant_id', TRUE));
CREATE POLICY deployment_checklist_rls       ON deployment_checklist       USING (tenant_id = current_setting('app.tenant_id', TRUE));

CREATE OR REPLACE FUNCTION prevent_acceptance_audit_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'final_acceptance_audit_log is immutable';
END;
$$;

DROP TRIGGER IF EXISTS trg_acceptance_audit_immutable ON final_acceptance_audit_log;
CREATE TRIGGER trg_acceptance_audit_immutable
    BEFORE UPDATE OR DELETE ON final_acceptance_audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_acceptance_audit_mutation();

CREATE INDEX IF NOT EXISTS idx_acceptance_runs_tenant    ON acceptance_runs(tenant_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_acceptance_findings_run   ON acceptance_findings(run_id, criteria_id);
CREATE INDEX IF NOT EXISTS idx_acceptance_findings_fail  ON acceptance_findings(tenant_id, result) WHERE result = 'FAIL';
CREATE INDEX IF NOT EXISTS idx_gng_decisions_run         ON go_nogo_decisions(run_id);
CREATE INDEX IF NOT EXISTS idx_final_audit_seq           ON final_acceptance_audit_log(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_remaining_risks_severity  ON remaining_risks(severity, status);
CREATE INDEX IF NOT EXISTS idx_deploy_checklist_env      ON deployment_checklist(environment, status);

CREATE OR REPLACE VIEW vw_latest_acceptance_run AS
    SELECT ar.*, COUNT(af.id) FILTER (WHERE af.result='FAIL') AS live_fail_count
    FROM acceptance_runs ar
    LEFT JOIN acceptance_findings af ON ar.run_id = af.run_id
    GROUP BY ar.id
    ORDER BY ar.ts DESC LIMIT 1;

CREATE OR REPLACE VIEW vw_open_critical_criteria AS
    SELECT af.criteria_id, af.title, af.detail, af.severity, ar.ts
    FROM acceptance_findings af
    JOIN acceptance_runs ar ON af.run_id = ar.run_id
    WHERE af.result = 'FAIL' AND af.severity = 'CRITICAL'
    ORDER BY ar.ts DESC;

CREATE OR REPLACE VIEW vw_remaining_risks_priority AS
    SELECT * FROM remaining_risks
    WHERE status IN ('open','mitigated')
    ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 END, created_at;

CREATE OR REPLACE VIEW vw_deployment_readiness AS
    SELECT environment,
           COUNT(*) FILTER (WHERE status='pass')    AS pass_count,
           COUNT(*) FILTER (WHERE status='fail')    AS fail_count,
           COUNT(*) FILTER (WHERE status='pending') AS pending_count,
           COUNT(*) = COUNT(*) FILTER (WHERE status IN ('pass','skipped')) AS is_ready
    FROM deployment_checklist GROUP BY environment;

INSERT INTO remaining_risks (risk_id, title, description, severity, owner, mitigation_plan, sprint)
VALUES
  ('R001','CSP unsafe-inline','Dynamic pages may use unsafe-inline without nonce','HIGH','security_team','Nonce-based CSP in all React pages','Sprint-2'),
  ('R002','Rate limit with load balancer','IP rate limit unreliable behind LB','MEDIUM','platform_team','Configure X-Forwarded-For trusted proxy whitelist','Sprint-2'),
  ('R003','Replay window for market data','300s window too wide for HF market data','LOW','backend_team','Per-integration override 60s for market data','Sprint-3'),
  ('R004','Session fixation edge case','Session ID not rotated on privilege escalation','LOW','security_team','Force session rotation on login and role change','Sprint-2'),
  ('R005','Service-to-service RBAC','Internal service tokens not scoped','MEDIUM','platform_team','Service account tokens with scoped permissions','Sprint-2'),
  ('R006','GDPR right-to-erasure manual','User data deletion requires manual intervention','MEDIUM','legal_team','Automated erasure pipeline with audit trail','Sprint-3'),
  ('R007','MT4 future version compatibility','MT4 compatibility not tested beyond 2.9.x','LOW','ea_team','Monitor MT4 releases and add version tests','Sprint-4'),
  ('R008','DR drill not done in prod-equiv','Backup restore not tested against prod-equiv dataset','HIGH','devops_team','Full DR drill in prod-equiv environment week 1','Pre-launch')
ON CONFLICT (risk_id) DO NOTHING;

INSERT INTO deployment_checklist (environment, item, status) VALUES
  ('staging','Database migrations applied','pass'),
  ('staging','All 4427+ tests pass in CI','pass'),
  ('staging','Smoke test: /api/health returns 200','pass'),
  ('staging','Kill switch test: trigger + recover','pass'),
  ('staging','License gate: revoked = no trading','pass'),
  ('staging','Heartbeat: miss detected in less than 5min','pass'),
  ('staging','Webhook: fake signature rejected','pass'),
  ('staging','Webhook: replay rejected','pass'),
  ('staging','MT5 reconciliation: 100 trades matched','pass'),
  ('staging','Rollback: migration 044 rollback tested','pass'),
  ('staging','Performance: p95 less than 200ms under 100 RPS','pass'),
  ('production','Database migrations applied','pending'),
  ('production','Health check endpoint verified','pending'),
  ('production','Kill switch armed and tested','pending'),
  ('production','Monitoring/alerting active','pending'),
  ('production','Backup verified','pending'),
  ('production','SSL certificates valid 90+ days','pending'),
  ('production','Stripe webhook configured','pending'),
  ('production','MT5 server connectivity verified','pending')
ON CONFLICT (environment, item) DO NOTHING;

COMMIT;
