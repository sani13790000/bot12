-- Migration 019: Phase 11-13 canonical tables
BEGIN;

CREATE TABLE IF NOT EXISTS security_ai_analysis (
    id           UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type   TEXT         NOT NULL CHECK (event_type IN ('api_request','login_attempt','trade_activity','session_anomaly','websocket')),
    risk_level   TEXT         NOT NULL DEFAULT 'low' CHECK (risk_level IN ('low','medium','high','critical')),
    risk_score   FLOAT        NOT NULL DEFAULT 0.0 CHECK (risk_score BETWEEN -1.0 AND 1.0),
    is_anomaly   BOOLEAN      NOT NULL DEFAULT FALSE,
    user_id      UUID         REFERENCES auth.users(id) ON DELETE SET NULL,
    ip_address   INET,
    endpoint     TEXT,
    features     JSONB        DEFAULT '[]',
    explanation  JSONB        DEFAULT '[]',
    metadata     JSONB        DEFAULT '{}',
    self_healed  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sec_ai_created  ON security_ai_analysis (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sec_ai_risk     ON security_ai_analysis (risk_level, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sec_ai_ip       ON security_ai_analysis (ip_address, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sec_ai_user     ON security_ai_analysis (user_id, created_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sec_ai_anomaly  ON security_ai_analysis (is_anomaly, created_at DESC) WHERE is_anomaly = TRUE;

CREATE TABLE IF NOT EXISTS security_blocked_ips (
    id           UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    ip_address   INET         NOT NULL UNIQUE,
    reason       TEXT         NOT NULL DEFAULT 'anomaly_detected',
    auto_blocked BOOLEAN      NOT NULL DEFAULT TRUE,
    expires_at   TIMESTAMPTZ,
    unblocked_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_blocked_ip   ON security_blocked_ips (ip_address);
CREATE INDEX IF NOT EXISTS idx_blocked_exp  ON security_blocked_ips (expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS security_scores (
    id         UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    score      FLOAT       NOT NULL CHECK (score BETWEEN 0 AND 100),
    level      TEXT        NOT NULL,
    trend      TEXT        NOT NULL,
    dimensions JSONB       DEFAULT '{}',
    top_risks  JSONB       DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_scores_created ON security_scores (created_at DESC);

CREATE OR REPLACE FUNCTION prune_old_security_scores() RETURNS void LANGUAGE plpgsql AS $$
BEGIN DELETE FROM security_scores WHERE created_at < NOW() - INTERVAL '30 days'; END;
$$;

CREATE TABLE IF NOT EXISTS self_healing_actions (
    id             UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    action_type    TEXT        NOT NULL,
    target         TEXT        NOT NULL,
    severity       TEXT        NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    anomaly_score  FLOAT,
    reason         TEXT,
    auto_expire_at TIMESTAMPTZ,
    reverted_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_healing_target ON self_healing_actions (target, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_healing_type   ON self_healing_actions (action_type, created_at DESC);

CREATE TABLE IF NOT EXISTS security_model_metadata (
    id               UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_type       TEXT        NOT NULL DEFAULT 'IsolationForest',
    training_samples INT         NOT NULL DEFAULT 0,
    contamination    FLOAT       NOT NULL DEFAULT 0.05,
    feature_dim      INT         NOT NULL DEFAULT 12,
    accuracy_proxy   FLOAT,
    trained_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS threat_intel_cache (
    id           UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    ip_address   INET        NOT NULL UNIQUE,
    provider     TEXT        NOT NULL DEFAULT 'local',
    risk_score   INT         NOT NULL DEFAULT 0 CHECK (risk_score BETWEEN 0 AND 100),
    is_malicious BOOLEAN     NOT NULL DEFAULT FALSE,
    is_tor       BOOLEAN     NOT NULL DEFAULT FALSE,
    is_vpn       BOOLEAN     NOT NULL DEFAULT FALSE,
    country      TEXT,
    raw_data     JSONB       DEFAULT '{}',
    queried_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '1 hour')
);
CREATE INDEX IF NOT EXISTS idx_ti_ip  ON threat_intel_cache (ip_address);
CREATE INDEX IF NOT EXISTS idx_ti_exp ON threat_intel_cache (expires_at);

CREATE TABLE IF NOT EXISTS security_reports (
    id           UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_type  TEXT        NOT NULL DEFAULT 'scheduled',
    period_days  INT         NOT NULL DEFAULT 30,
    score        FLOAT,
    score_trend  TEXT,
    total_events INT         DEFAULT 0,
    json_path    TEXT,
    html_path    TEXT,
    pdf_path     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- RLS
ALTER TABLE security_ai_analysis    ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_blocked_ips    ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_scores         ENABLE ROW LEVEL SECURITY;
ALTER TABLE self_healing_actions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_model_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE threat_intel_cache      ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_reports        ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    DROP POLICY IF EXISTS svc_sec_ai   ON security_ai_analysis;   CREATE POLICY svc_sec_ai   ON security_ai_analysis   FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    DROP POLICY IF EXISTS svc_blocked  ON security_blocked_ips;   CREATE POLICY svc_blocked  ON security_blocked_ips   FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    DROP POLICY IF EXISTS svc_scores   ON security_scores;         CREATE POLICY svc_scores   ON security_scores         FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    DROP POLICY IF EXISTS svc_healing  ON self_healing_actions;    CREATE POLICY svc_healing  ON self_healing_actions    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    DROP POLICY IF EXISTS svc_model    ON security_model_metadata; CREATE POLICY svc_model    ON security_model_metadata FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    DROP POLICY IF EXISTS svc_ti       ON threat_intel_cache;      CREATE POLICY svc_ti       ON threat_intel_cache      FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    DROP POLICY IF EXISTS svc_reports  ON security_reports;        CREATE POLICY svc_reports  ON security_reports        FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
  END IF;
END $$;

DROP POLICY IF EXISTS user_own_sec_ai ON security_ai_analysis;
CREATE POLICY user_own_sec_ai ON security_ai_analysis FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE OR REPLACE FUNCTION auto_unblock_expired_ips() RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN UPDATE security_blocked_ips SET unblocked_at = NOW() WHERE expires_at IS NOT NULL AND expires_at < NOW() AND unblocked_at IS NULL; END;
$$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    PERFORM cron.schedule('unblock-expired-ips', '*/15 * * * *', 'SELECT auto_unblock_expired_ips()');
    PERFORM cron.schedule('prune-security-scores', '0 3 * * *', 'SELECT prune_old_security_scores()');
  END IF;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

COMMIT;
