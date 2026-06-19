-- Migration 017 — Phase-4/5/6: Threat Intel + Security Rules + Reporting
BEGIN;

CREATE TABLE IF NOT EXISTS threat_intel_cache (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ip_address    TEXT NOT NULL,
    threat_level  TEXT NOT NULL CHECK (threat_level IN ('clean','low','medium','high','critical')),
    confidence    FLOAT NOT NULL DEFAULT 0.0,
    abuse_score   INT NOT NULL DEFAULT 0,
    is_tor        BOOLEAN DEFAULT FALSE,
    is_vpn        BOOLEAN DEFAULT FALSE,
    is_datacenter BOOLEAN DEFAULT FALSE,
    country_code  TEXT DEFAULT '',
    provider      TEXT NOT NULL DEFAULT 'local',
    raw_data      JSONB DEFAULT '{}',
    expires_at    TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '1 hour'),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_threat_intel_ip ON threat_intel_cache (ip_address);
CREATE INDEX IF NOT EXISTS idx_threat_intel_level ON threat_intel_cache (threat_level);
CREATE INDEX IF NOT EXISTS idx_threat_intel_expires ON threat_intel_cache (expires_at);

CREATE TABLE IF NOT EXISTS security_rule_history (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    changed_by TEXT NOT NULL DEFAULT 'system',
    patch      JSONB NOT NULL,
    full_rules JSONB NOT NULL,
    reason     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rule_history_created ON security_rule_history (created_at DESC);

CREATE TABLE IF NOT EXISTS security_reports (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id    TEXT NOT NULL UNIQUE,
    period_hours INT NOT NULL DEFAULT 24,
    period_start TIMESTAMPTZ NOT NULL,
    period_end   TIMESTAMPTZ NOT NULL,
    score        FLOAT NOT NULL DEFAULT 0.0,
    score_trend  TEXT NOT NULL DEFAULT 'unknown',
    attacks      INT NOT NULL DEFAULT 0,
    blocked_ips  INT NOT NULL DEFAULT 0,
    high_risk    INT NOT NULL DEFAULT 0,
    json_path    TEXT,
    html_path    TEXT,
    pdf_path     TEXT,
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_security_reports_created ON security_reports (created_at DESC);

ALTER TABLE threat_intel_cache ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_full_threat_intel" ON threat_intel_cache;
CREATE POLICY "service_full_threat_intel" ON threat_intel_cache FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE security_rule_history ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_only_rule_history" ON security_rule_history;
CREATE POLICY "service_only_rule_history" ON security_rule_history FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE security_reports ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_only_reports" ON security_reports;
CREATE POLICY "service_only_reports" ON security_reports FOR ALL USING (auth.role() = 'service_role');

COMMIT;
