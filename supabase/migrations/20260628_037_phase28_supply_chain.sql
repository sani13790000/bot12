-- =============================================================
-- Phase 28: Dependency, Supply-Chain & Build Security
-- Migration: 037
-- =============================================================
BEGIN;

-- -----------------------------------------------------------
-- 1. supply_chain_runs  (per-CI-run record)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS supply_chain_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    run_type        TEXT NOT NULL CHECK (run_type IN ('full_scan','policy_gate','sbom','build')),
    actor           TEXT NOT NULL,
    commit_sha      TEXT NOT NULL DEFAULT '',
    branch          TEXT NOT NULL DEFAULT '',
    passed          BOOLEAN NOT NULL DEFAULT FALSE,
    total_deps      INT NOT NULL DEFAULT 0,
    unpinned_count  INT NOT NULL DEFAULT 0,
    banned_count    INT NOT NULL DEFAULT 0,
    vuln_count      INT NOT NULL DEFAULT 0,
    critical_vulns  INT NOT NULL DEFAULT 0,
    drift_count     INT NOT NULL DEFAULT 0,
    dyn_load_count  INT NOT NULL DEFAULT 0,
    reasons         JSONB NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE supply_chain_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY sc_runs_tenant ON supply_chain_runs
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

CREATE TABLE IF NOT EXISTS lockfile_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    lockfile_hash   CHAR(64) NOT NULL,
    entry_count     INT NOT NULL DEFAULT 0,
    recorded_by     TEXT NOT NULL,
    commit_sha      TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE lockfile_records ENABLE ROW LEVEL SECURITY;
CREATE POLICY lf_records_tenant ON lockfile_records
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

CREATE TABLE IF NOT EXISTS build_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    build_id        UUID NOT NULL UNIQUE,
    commit_sha      TEXT NOT NULL,
    branch          TEXT NOT NULL DEFAULT 'main',
    python_ver      TEXT NOT NULL,
    lockfile_hash   CHAR(64) NOT NULL,
    deps_count      INT NOT NULL DEFAULT 0,
    built_by        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'unsigned'
                    CHECK (status IN ('unsigned','signed','verified','tampered','reproducing')),
    signature       CHAR(64),
    env_vars_hash   TEXT NOT NULL DEFAULT '',
    artifact_ids    JSONB NOT NULL DEFAULT '[]',
    built_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE build_records ENABLE ROW LEVEL SECURITY;
CREATE POLICY build_records_tenant ON build_records
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

CREATE TABLE IF NOT EXISTS vuln_scan_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    run_id          UUID REFERENCES supply_chain_runs(id) ON DELETE CASCADE,
    cve_id          TEXT NOT NULL,
    package         TEXT NOT NULL,
    affected_ver    TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    fix_version     TEXT,
    description     TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE vuln_scan_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY vuln_scan_tenant ON vuln_scan_results
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

CREATE TABLE IF NOT EXISTS dynamic_load_violations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    run_id          UUID REFERENCES supply_chain_runs(id) ON DELETE CASCADE,
    file_path       TEXT NOT NULL,
    line_no         INT NOT NULL,
    pattern         TEXT NOT NULL,
    line_content    TEXT NOT NULL DEFAULT '',
    severity        TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE dynamic_load_violations ENABLE ROW LEVEL SECURITY;
CREATE POLICY dyn_load_tenant ON dynamic_load_violations
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

CREATE TABLE IF NOT EXISTS supply_chain_audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    seq         BIGINT NOT NULL,
    action      TEXT NOT NULL,
    actor       TEXT NOT NULL,
    detail      JSONB NOT NULL DEFAULT '{}',
    chain_hash  CHAR(64) NOT NULL,
    prev_hash   CHAR(64) NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE supply_chain_audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY sc_audit_tenant ON supply_chain_audit_log
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);

CREATE OR REPLACE FUNCTION supply_chain_audit_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'supply_chain_audit_log is immutable';
END;
$$;

CREATE TRIGGER supply_chain_audit_no_update
    BEFORE UPDATE ON supply_chain_audit_log
    FOR EACH ROW EXECUTE FUNCTION supply_chain_audit_immutable();

CREATE TRIGGER supply_chain_audit_no_delete
    BEFORE DELETE ON supply_chain_audit_log
    FOR EACH ROW EXECUTE FUNCTION supply_chain_audit_immutable();

CREATE INDEX IF NOT EXISTS idx_sc_runs_tenant_created ON supply_chain_runs(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lf_records_hash ON lockfile_records(lockfile_hash);
CREATE INDEX IF NOT EXISTS idx_build_records_commit ON build_records(tenant_id, commit_sha);
CREATE INDEX IF NOT EXISTS idx_vuln_scan_severity ON vuln_scan_results(tenant_id, severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_vuln_scan_cve ON vuln_scan_results(cve_id);
CREATE INDEX IF NOT EXISTS idx_dyn_load_severity ON dynamic_load_violations(tenant_id, severity);
CREATE INDEX IF NOT EXISTS idx_sc_audit_seq ON supply_chain_audit_log(tenant_id, seq);
CREATE INDEX IF NOT EXISTS idx_sc_audit_action ON supply_chain_audit_log(tenant_id, action, ts DESC);

CREATE OR REPLACE FUNCTION cleanup_old_supply_chain_runs(p_tenant_id UUID, p_days_to_keep INT DEFAULT 90)
RETURNS INT LANGUAGE plpgsql AS $$
DECLARE deleted_count INT;
BEGIN
    DELETE FROM supply_chain_runs WHERE tenant_id = p_tenant_id AND created_at < NOW() - (p_days_to_keep || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

CREATE OR REPLACE VIEW vw_latest_build_per_branch AS
    SELECT DISTINCT ON (tenant_id, branch) id, tenant_id, build_id, commit_sha, branch, python_ver, lockfile_hash, deps_count, status, built_at
    FROM build_records ORDER BY tenant_id, branch, built_at DESC;

CREATE OR REPLACE VIEW vw_critical_vulns_open AS
    SELECT v.*, r.commit_sha, r.actor FROM vuln_scan_results v
    JOIN supply_chain_runs r ON r.id = v.run_id
    WHERE v.severity = 'critical' AND r.passed = FALSE ORDER BY v.created_at DESC;

CREATE OR REPLACE VIEW vw_supply_chain_audit_summary AS
    SELECT tenant_id, COUNT(*) AS total_events, MAX(ts) AS last_event_at, COUNT(DISTINCT actor) AS distinct_actors
    FROM supply_chain_audit_log GROUP BY tenant_id;

CREATE OR REPLACE FUNCTION verify_supply_chain_audit_chain(p_tenant_id UUID) RETURNS BOOLEAN LANGUAGE plpgsql AS $$
DECLARE prev_hash TEXT := NULL; rec RECORD;
BEGIN
    FOR rec IN SELECT chain_hash, prev_hash AS ph, seq FROM supply_chain_audit_log WHERE tenant_id = p_tenant_id ORDER BY seq ASC
    LOOP
        IF prev_hash IS NOT NULL AND rec.ph != prev_hash THEN RETURN FALSE; END IF;
        prev_hash := rec.chain_hash;
    END LOOP;
    RETURN TRUE;
END;
$$;

COMMIT;
