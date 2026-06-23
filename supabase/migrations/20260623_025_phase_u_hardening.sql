-- Migration 025: Phase U hardening
-- U-11/U-12/U-15: users GDPR columns
-- U-13/U-14: user_settings typed table
-- U-16/U-17: token_revocations JTI blacklist
-- U-9: system_state persistent halt
-- U-1: trade_statistics view with profit_factor

BEGIN;

-- GDPR columns
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_deleted  BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS deleted_at  TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_users_is_deleted ON users(is_deleted) WHERE is_deleted = TRUE;

-- user_settings typed table
CREATE TABLE IF NOT EXISTS user_settings (
    user_id                UUID         PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    language               TEXT         DEFAULT 'en'    CHECK (length(language) <= 10),
    timezone               TEXT         DEFAULT 'UTC'   CHECK (length(timezone) <= 50),
    notifications_enabled  BOOLEAN      NOT NULL DEFAULT TRUE,
    telegram_alerts        BOOLEAN      NOT NULL DEFAULT TRUE,
    email_alerts           BOOLEAN      NOT NULL DEFAULT FALSE,
    default_lot_size       NUMERIC(8,2) DEFAULT 0.01  CHECK (default_lot_size BETWEEN 0.01 AND 100.0),
    default_risk_pct       NUMERIC(5,2) DEFAULT 1.0   CHECK (default_risk_pct BETWEEN 0.1 AND 10.0),
    theme                  TEXT         DEFAULT 'dark' CHECK (theme IN ('light','dark','system')),
    dashboard_layout       TEXT         DEFAULT 'grid' CHECK (length(dashboard_layout) <= 20),
    updated_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS user_settings_owner ON user_settings FOR ALL USING (user_id = auth.uid());

-- JTI revocation
CREATE TABLE IF NOT EXISTS token_revocations (
    jti        TEXT        PRIMARY KEY,
    user_id    UUID        REFERENCES users(id) ON DELETE CASCADE,
    revoked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    reason     TEXT
);
CREATE INDEX IF NOT EXISTS idx_token_revocations_expires ON token_revocations(expires_at);

-- system_state for halt persistence
CREATE TABLE IF NOT EXISTS system_state (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE system_state ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS system_state_service_only ON system_state FOR ALL USING (FALSE);
INSERT INTO system_state (key, value) VALUES ('equity_protection_halt', '{"halted": false}')
ON CONFLICT (key) DO NOTHING;

-- trade_statistics view with profit_factor
CREATE OR REPLACE VIEW trade_statistics AS
SELECT
    user_id,
    COUNT(*)                                                      AS total_trades,
    COUNT(*) FILTER (WHERE pnl_usd > 0)                          AS winning_trades,
    SUM(pnl_usd)                                                  AS total_pnl,
    SUM(pnl_usd) FILTER (WHERE pnl_usd > 0)                      AS gross_profit,
    ABS(SUM(pnl_usd) FILTER (WHERE pnl_usd < 0))                 AS gross_loss,
    CASE
        WHEN ABS(SUM(pnl_usd) FILTER (WHERE pnl_usd < 0)) > 0
        THEN SUM(pnl_usd) FILTER (WHERE pnl_usd > 0)
             / ABS(SUM(pnl_usd) FILTER (WHERE pnl_usd < 0))
        ELSE NULL
    END AS profit_factor,
    ROUND(100.0 * COUNT(*) FILTER (WHERE pnl_usd > 0)::NUMERIC / NULLIF(COUNT(*),0), 2) AS win_rate_pct
FROM trades WHERE status = 'closed' GROUP BY user_id;

-- indexes
CREATE INDEX IF NOT EXISTS idx_trades_user_symbol_status ON trades(user_id, symbol, status);
CREATE INDEX IF NOT EXISTS idx_trades_user_opened_at     ON trades(user_id, opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_signal_id_user     ON trades(signal_id, user_id);

COMMIT;
