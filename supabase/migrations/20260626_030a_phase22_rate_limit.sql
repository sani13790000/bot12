-- Phase 22: Rate Limit Audit Table
BEGIN;
CREATE TABLE IF NOT EXISTS rate_limit_bans (
    id          BIGSERIAL PRIMARY KEY,
    ip          TEXT        NOT NULL,
    reason      TEXT        NOT NULL,
    abuse_type  TEXT,
    banned_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    unbanned_at TIMESTAMPTZ,
    tenant_id   TEXT,
    actor_id    TEXT,
    CONSTRAINT rate_limit_bans_ip_check CHECK (length(ip) <= 45)
);
CREATE INDEX IF NOT EXISTS idx_rl_bans_ip        ON rate_limit_bans(ip);
CREATE INDEX IF NOT EXISTS idx_rl_bans_expires   ON rate_limit_bans(expires_at);
CREATE INDEX IF NOT EXISTS idx_rl_bans_abuse     ON rate_limit_bans(abuse_type);
CREATE TABLE IF NOT EXISTS rate_limit_violations (
    id          BIGSERIAL PRIMARY KEY,
    ip          TEXT        NOT NULL,
    endpoint    TEXT        NOT NULL,
    user_id     TEXT,
    tenant_id   TEXT,
    tier        TEXT        NOT NULL DEFAULT 'anonymous',
    violated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retry_after INTEGER     NOT NULL DEFAULT 0,
    reason      TEXT
);
CREATE INDEX IF NOT EXISTS idx_rl_viol_ip     ON rate_limit_violations(ip);
CREATE INDEX IF NOT EXISTS idx_rl_viol_ep     ON rate_limit_violations(endpoint);
CREATE INDEX IF NOT EXISTS idx_rl_viol_at     ON rate_limit_violations(violated_at);
CREATE INDEX IF NOT EXISTS idx_rl_viol_tenant ON rate_limit_violations(tenant_id, violated_at);
CREATE TABLE IF NOT EXISTS rate_limit_abuse (
    id          BIGSERIAL PRIMARY KEY,
    ip          TEXT        NOT NULL,
    abuse_type  TEXT        NOT NULL,
    detail      JSONB       NOT NULL DEFAULT '{}',
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    auto_banned BOOLEAN     NOT NULL DEFAULT FALSE,
    ban_ttl     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_rl_abuse_ip   ON rate_limit_abuse(ip);
CREATE INDEX IF NOT EXISTS idx_rl_abuse_type ON rate_limit_abuse(abuse_type);
CREATE INDEX IF NOT EXISTS idx_rl_abuse_at   ON rate_limit_abuse(detected_at);
ALTER TABLE rate_limit_bans        ENABLE ROW LEVEL SECURITY;
ALTER TABLE rate_limit_violations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE rate_limit_abuse       ENABLE ROW LEVEL SECURITY;
CREATE POLICY rl_bans_admin       ON rate_limit_bans       FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY rl_violations_admin ON rate_limit_violations FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY rl_abuse_admin      ON rate_limit_abuse      FOR ALL USING (auth.role() = 'service_role');
CREATE OR REPLACE FUNCTION cleanup_expired_bans()
RETURNS INTEGER LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE deleted INTEGER;
BEGIN
    DELETE FROM rate_limit_bans WHERE expires_at < NOW() - INTERVAL '30 days';
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$;
CREATE OR REPLACE VIEW vw_active_bans AS
SELECT ip, reason, abuse_type, banned_at, expires_at,
       EXTRACT(EPOCH FROM (expires_at - NOW()))::INTEGER AS expires_in_secs
FROM rate_limit_bans WHERE expires_at > NOW() AND unbanned_at IS NULL;
COMMIT;
