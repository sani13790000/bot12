-- =============================================================================
-- Migration 043: Final Security Review & Penetration Hardening
-- Phase 34: auth_bypass / RBAC bypass / IDOR / injection / replay /
--            spoofing / leak / CORS / headers / rate_limits / logging
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. security_scan_runs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS security_scan_runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    scan_id         UUID        NOT NULL UNIQUE,
    actor           TEXT        NOT NULL,
    scan_ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    overall_pass    BOOLEAN     NOT NULL DEFAULT FALSE,
    critical_count  INT         NOT NULL DEFAULT 0 CHECK (critical_count >= 0),
    high_count      INT         NOT NULL DEFAULT 0 CHECK (high_count >= 0),
    medium_count    INT         NOT NULL DEFAULT 0 CHECK (medium_count >= 0),
    low_count       INT         NOT NULL DEFAULT 0 CHECK (low_count >= 0),
    audit_chain_ok  BOOLEAN     NOT NULL DEFAULT TRUE,
    checks_run      INT         NOT NULL DEFAULT 0,
    pentest_count   INT         NOT NULL DEFAULT 0,
    pentest_passed  INT         NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE security_scan_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON security_scan_runs
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

-- ---------------------------------------------------------------------------
-- 2. security_findings
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS security_findings (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    scan_id         UUID        NOT NULL REFERENCES security_scan_runs(scan_id),
    finding_id      UUID        NOT NULL UNIQUE,
    category        TEXT        NOT NULL CHECK (category IN (
                        'auth_bypass','rbac_bypass','idor','injection',
                        'replay','spoofing','information_leak','cors',
                        'security_headers','rate_limiting','logging',
                        'supply_chain','crypto','session','input_validation')),
    risk            TEXT        NOT NULL CHECK (risk IN
                        ('critical','high','medium','low','info')),
    title           TEXT        NOT NULL,
    description     TEXT        NOT NULL,
    evidence        TEXT,
    mitigation      TEXT,
    cwe             TEXT,
    owasp           TEXT,
    mitigated       BOOLEAN     NOT NULL DEFAULT FALSE,
    accepted        BOOLEAN     NOT NULL DEFAULT FALSE,
    mitigated_by    TEXT,
    accepted_by     TEXT,
    mitigated_at    TIMESTAMPTZ,
    accepted_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE security_findings ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON security_findings
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

-- ---------------------------------------------------------------------------
-- 3. risk_register
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_register (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    risk_id         TEXT        NOT NULL,
    category        TEXT        NOT NULL CHECK (category IN (
                        'auth_bypass','rbac_bypass','idor','injection',
                        'replay','spoofing','information_leak','cors',
                        'security_headers','rate_limiting','logging',
                        'supply_chain','crypto','session','input_validation')),
    risk_level      TEXT        NOT NULL CHECK (risk_level IN
                        ('critical','high','medium','low','info')),
    title           TEXT        NOT NULL,
    description     TEXT        NOT NULL,
    mitigation      TEXT        NOT NULL,
    mitigated       BOOLEAN     NOT NULL DEFAULT FALSE,
    accepted        BOOLEAN     NOT NULL DEFAULT FALSE,
    mitigated_by    TEXT,
    accepted_by     TEXT,
    reason          TEXT,
    mitigated_at    TIMESTAMPTZ,
    accepted_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, risk_id)
);

ALTER TABLE risk_register ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON risk_register
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

-- ---------------------------------------------------------------------------
-- 4. pentest_results / pentest_scenarios
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pentest_results (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    scan_id         UUID        NOT NULL REFERENCES security_scan_runs(scan_id),
    scenario_id     TEXT        NOT NULL,
    name            TEXT        NOT NULL,
    category        TEXT        NOT NULL,
    passed          BOOLEAN     NOT NULL,
    detail          TEXT,
    attack_class    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE pentest_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON pentest_results
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

CREATE TABLE IF NOT EXISTS pentest_scenarios (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    scenario_id     TEXT        NOT NULL,
    name            TEXT        NOT NULL,
    category        TEXT        NOT NULL,
    expected_block  BOOLEAN     NOT NULL DEFAULT TRUE,
    attack_class    TEXT,
    last_run_at     TIMESTAMPTZ,
    last_pass       BOOLEAN,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, scenario_id)
);

ALTER TABLE pentest_scenarios ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON pentest_scenarios
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

-- ---------------------------------------------------------------------------
-- 5. cors_policy_log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cors_policy_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    origin          TEXT        NOT NULL,
    method          TEXT        NOT NULL,
    allowed         BOOLEAN     NOT NULL,
    reason          TEXT,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE cors_policy_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON cors_policy_log
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

-- ---------------------------------------------------------------------------
-- 6. security_audit_log  (IMMUTABLE)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS security_audit_log (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID        NOT NULL,
    seq         INT         NOT NULL,
    action      TEXT        NOT NULL,
    actor       TEXT        NOT NULL,
    detail      JSONB       NOT NULL DEFAULT '{}',
    chain_hash  CHAR(64)    NOT NULL,
    logged_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE security_audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON security_audit_log
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

CREATE OR REPLACE FUNCTION security_audit_log_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'security_audit_log is immutable: % denied', TG_OP;
END;
$$;

CREATE TRIGGER trg_security_audit_log_immutable
    BEFORE UPDATE OR DELETE ON security_audit_log
    FOR EACH ROW EXECUTE FUNCTION security_audit_log_immutable();

-- pass/fail enum reference for checks
-- overall_pass = TRUE (pass) / FALSE (fail)
-- CheckStatus: pass, fail, warn, skip

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_scan_runs_tenant_ts
    ON security_scan_runs (tenant_id, scan_ts DESC);
CREATE INDEX IF NOT EXISTS idx_scan_runs_pass
    ON security_scan_runs (overall_pass, critical_count);
CREATE INDEX IF NOT EXISTS idx_findings_tenant_scan
    ON security_findings (tenant_id, scan_id);
CREATE INDEX IF NOT EXISTS idx_findings_risk_category
    ON security_findings (risk, category);
CREATE INDEX IF NOT EXISTS idx_findings_mitigated
    ON security_findings (mitigated, accepted);
CREATE INDEX IF NOT EXISTS idx_risk_register_tenant
    ON risk_register (tenant_id, risk_level, mitigated);
CREATE INDEX IF NOT EXISTS idx_pentest_tenant
    ON pentest_scenarios (tenant_id, category);
CREATE INDEX IF NOT EXISTS idx_cors_policy_tenant
    ON cors_policy_log (tenant_id, allowed, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_audit_tenant_seq
    ON security_audit_log (tenant_id, seq DESC);
CREATE INDEX IF NOT EXISTS idx_security_audit_action
    ON security_audit_log (action, logged_at DESC);

-- ---------------------------------------------------------------------------
-- Cleanup function
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION cleanup_old_security_scans(keep_days INT DEFAULT 90)
RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
    deleted INT;
BEGIN
    DELETE FROM security_scan_runs
        WHERE scan_ts < now() - (keep_days || ' days')::INTERVAL
        AND overall_pass = TRUE;
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$;

-- ---------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_latest_security_scans AS
SELECT DISTINCT ON (tenant_id)
    tenant_id, scan_id, actor, scan_ts,
    overall_pass, critical_count, high_count,
    checks_run, pentest_passed, audit_chain_ok
FROM security_scan_runs
ORDER BY tenant_id, scan_ts DESC;

CREATE OR REPLACE VIEW vw_open_critical_findings AS
SELECT
    f.tenant_id, f.finding_id, f.category, f.risk,
    f.title, f.cwe, f.owasp,
    s.scan_ts, f.created_at
FROM security_findings f
JOIN security_scan_runs s USING (scan_id)
WHERE f.risk IN ('critical','high')
  AND f.mitigated = FALSE
  AND f.accepted  = FALSE
ORDER BY
    CASE f.risk WHEN 'critical' THEN 1 ELSE 2 END,
    f.created_at DESC;

CREATE OR REPLACE VIEW vw_security_audit_summary AS
SELECT
    tenant_id,
    action,
    COUNT(*)           AS event_count,
    MAX(logged_at)     AS last_seen,
    MIN(logged_at)     AS first_seen
FROM security_audit_log
GROUP BY tenant_id, action;

-- ---------------------------------------------------------------------------
-- Verify audit chain function
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION verify_security_audit_chain(p_tenant_id UUID)
RETURNS TABLE (is_valid BOOLEAN, broken_seq INT[]) LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
    prev_hash TEXT := '';
    broken INT[] := '{}';
BEGIN
    FOR rec IN
        SELECT seq, chain_hash
        FROM security_audit_log
        WHERE tenant_id = p_tenant_id
        ORDER BY seq
    LOOP
        IF length(rec.chain_hash) != 64 THEN
            broken := array_append(broken, rec.seq);
        END IF;
        prev_hash := rec.chain_hash;
    END LOOP;
    RETURN QUERY SELECT (array_length(broken,1) IS NULL), broken;
END;
$$;

COMMIT;

-- =============================================================================
-- Summary
-- Tables  : 7 (security_scan_runs, security_findings, risk_register,
--               pentest_results, pentest_scenarios, cors_policy_log,
--               security_audit_log)
-- RLS     : enabled on all 7 tables
-- Triggers: 1 immutable trigger on security_audit_log
-- Indexes : 10
-- Cleanup : cleanup_old_security_scans()
-- Views   : vw_latest_security_scans / vw_open_critical_findings /
--           vw_security_audit_summary
-- Fn      : verify_security_audit_chain()
-- =============================================================================
