-- Migration 016: Phase-13 and Phase-14 Security AI Tables
BEGIN;

CREATE TABLE IF NOT EXISTS security_ai_analysis (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type       TEXT NOT NULL DEFAULT 'api_request'
                         CHECK (event_type IN ('api_request','login_attempt','trade_activity','session_anomaly','websocket')),
    ip_address       INET,
    user_id          UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    endpoint         TEXT,
    is_anomaly       BOOLEAN NOT NULL DEFAULT FALSE,
    anomaly_score    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    risk_level       TEXT NOT NULL DEFAULT 'low' CHECK (risk_level IN ('low','medium','high','critical')),
    confidence       DOUBLE PRECISION NOT NULL DEFAULT 0.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    features         JSONB,
    explanation      JSONB,
    self_heal_action TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_security_ai_analysis_created_at ON security_ai_analysis (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_ai_analysis_anomaly ON security_ai_analysis (is_anomaly, created_at DESC) WHERE is_anomaly = TRUE;
CREATE INDEX IF NOT EXISTS idx_security_ai_analysis_ip ON security_ai_analysis (ip_address, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_ai_analysis_risk ON security_ai_analysis (risk_level, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_ai_analysis_user ON security_ai_analysis (user_id, created_at DESC) WHERE user_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS security_scores (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    overall_score    DOUBLE PRECISION NOT NULL CHECK (overall_score >= 0 AND overall_score <= 100),
    status           TEXT NOT NULL CHECK (status IN ('critical','warning','fair','good','excellent')),
    trend            TEXT NOT NULL DEFAULT 'stable' CHECK (trend IN ('improving','stable','degrading')),
    score_delta_1h   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    alert_triggered  BOOLEAN NOT NULL DEFAULT FALSE,
    dimensions       JSONB,
    top_risks        JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_security_scores_created_at ON security_scores (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_scores_alert ON security_scores (alert_triggered, created_at DESC) WHERE alert_triggered = TRUE;

CREATE TABLE IF NOT EXISTS security_blocked_ips (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ip_address   INET NOT NULL,
    reason       TEXT NOT NULL DEFAULT 'auto_block',
    blocked_by   TEXT NOT NULL DEFAULT 'security_ai',
    blocked_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    unblock_at   TIMESTAMPTZ,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_security_blocked_ips_ip_active ON security_blocked_ips (ip_address) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_security_blocked_ips_unblock ON security_blocked_ips (unblock_at) WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS security_model_metadata (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_type      TEXT NOT NULL DEFAULT 'IsolationForest',
    n_samples       INTEGER NOT NULL DEFAULT 0,
    n_features      INTEGER NOT NULL DEFAULT 12,
    contamination   DOUBLE PRECISION DEFAULT 0.05,
    trained_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    performance     JSONB,
    is_current      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_security_model_current ON security_model_metadata (model_type) WHERE is_current = TRUE;

ALTER TABLE security_ai_analysis    ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_scores         ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_blocked_ips    ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_model_metadata ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all_security_ai_analysis" ON security_ai_analysis FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "service_role_all_security_scores" ON security_scores FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "service_role_all_security_blocked_ips" ON security_blocked_ips FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "service_role_all_security_model_metadata" ON security_model_metadata FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "users_read_own_analysis" ON security_ai_analysis FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE OR REPLACE FUNCTION auto_unblock_expired_ips()
RETURNS INTEGER LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE n INTEGER;
BEGIN
    UPDATE security_blocked_ips SET is_active = FALSE
    WHERE is_active = TRUE AND unblock_at IS NOT NULL AND unblock_at < NOW();
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$;

COMMIT;
