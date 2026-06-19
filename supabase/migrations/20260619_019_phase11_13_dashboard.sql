-- ============================================================
-- Migration 019 — Phase 11-13: Dashboard metrics + performance
-- Tables: security_metrics_cache, security_dashboard_snapshots
-- + performance indexes on existing security tables
-- ============================================================

BEGIN;

-- 1. security_metrics_cache
CREATE TABLE IF NOT EXISTS security_metrics_cache (
    key        TEXT        PRIMARY KEY,
    value      JSONB       NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE security_metrics_cache IS 'KV cache for security dashboard metrics.';
CREATE INDEX IF NOT EXISTS idx_security_metrics_cache_updated
    ON security_metrics_cache (updated_at);

-- 2. security_dashboard_snapshots
CREATE TABLE IF NOT EXISTS security_dashboard_snapshots (
    id             UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    score          FLOAT       NOT NULL CHECK (score >= 0 AND score <= 100),
    level          TEXT        NOT NULL,
    trend          TEXT        NOT NULL,
    anomaly_rate   FLOAT       NOT NULL DEFAULT 0,
    blocked_ips    INTEGER     NOT NULL DEFAULT 0,
    active_threats INTEGER     NOT NULL DEFAULT 0,
    failed_logins  INTEGER     NOT NULL DEFAULT 0,
    dimensions     JSONB,
    top_risks      JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sec_dashboard_created
    ON security_dashboard_snapshots (created_at DESC);

-- 3. RLS
ALTER TABLE security_metrics_cache       ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_dashboard_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY security_metrics_cache_service
    ON security_metrics_cache FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY security_dashboard_service
    ON security_dashboard_snapshots FOR ALL TO service_role USING (true) WITH CHECK (true);

-- 4. Performance indexes on existing security tables
CREATE INDEX IF NOT EXISTS idx_security_scores_created
    ON security_scores (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sec_ai_analysis_type_created
    ON security_ai_analysis (event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sec_ai_analysis_risk_created
    ON security_ai_analysis (risk_score DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_blocked_ips_expires
    ON security_blocked_ips (expires_at NULLS FIRST);

-- 5. Cleanup helpers
CREATE OR REPLACE FUNCTION purge_stale_security_metrics()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    DELETE FROM security_metrics_cache WHERE updated_at < NOW() - INTERVAL '10 minutes';
END;
$$;

CREATE OR REPLACE FUNCTION purge_old_dashboard_snapshots()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    DELETE FROM security_dashboard_snapshots
    WHERE id NOT IN (
        SELECT id FROM security_dashboard_snapshots ORDER BY created_at DESC LIMIT 2016
    );
END;
$$;

COMMIT;
