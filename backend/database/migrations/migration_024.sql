-- ============================================================
-- Migration 024 — Phase S: DB hardening
-- S-6a: ml_models table
-- S-6b: audit_logs composite index
-- S-6c: decisions table
-- S-6d: session_events table
-- S-6e: db_health_log
-- S-6f: walk_forward_results embargo_pct
-- S-6g: signals session_type
-- ============================================================

BEGIN;

-- S-6a: ml_models
CREATE TABLE IF NOT EXISTS ml_models (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol              TEXT        NOT NULL,
    version             TEXT        NOT NULL,
    feature_schema_hash TEXT        NOT NULL,
    train_accuracy      FLOAT,
    test_accuracy       FLOAT,
    auc_score           FLOAT,
    n_features          INT,
    n_train_samples     INT,
    trained_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deployed_at         TIMESTAMPTZ,
    is_active           BOOLEAN     NOT NULL DEFAULT FALSE,
    metadata            JSONB       DEFAULT '{}'::JSONB,
    UNIQUE (symbol, version)
);
CREATE INDEX IF NOT EXISTS idx_ml_models_symbol_active
    ON ml_models (symbol, is_active) WHERE is_active = TRUE;
ALTER TABLE ml_models ENABLE ROW LEVEL SECURITY;
CREATE POLICY ml_models_service_role ON ml_models
    FOR ALL USING (auth.role() = 'service_role');

-- S-6b: audit_logs composite index
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_action
    ON audit_logs (user_id, action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp
    ON audit_logs (timestamp DESC);

-- S-6c: decisions table
CREATE TABLE IF NOT EXISTS decisions (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID        REFERENCES auth.users(id) ON DELETE CASCADE,
    signal_id      UUID,
    symbol         TEXT        NOT NULL,
    direction      TEXT        NOT NULL CHECK (direction IN ('BUY','SELL','NEUTRAL')),
    approved       BOOLEAN     NOT NULL,
    block_reason   TEXT        DEFAULT '',
    risk_pct       FLOAT       DEFAULT 0,
    lot_size       FLOAT       DEFAULT 0,
    vote_result    TEXT        DEFAULT '',
    agents_used    INT         DEFAULT 0,
    processing_ms  INT         DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata       JSONB       DEFAULT '{}'::JSONB
);
CREATE INDEX IF NOT EXISTS idx_decisions_user_created
    ON decisions (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_symbol
    ON decisions (symbol, created_at DESC);
ALTER TABLE decisions ENABLE ROW LEVEL SECURITY;
CREATE POLICY decisions_owner ON decisions
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY decisions_service ON decisions
    FOR ALL USING (auth.role() = 'service_role');

-- S-6d: session_events
CREATE TABLE IF NOT EXISTS session_events (
    id           BIGSERIAL   PRIMARY KEY,
    session_type TEXT        NOT NULL,
    is_tradeable BOOLEAN     NOT NULL,
    utc_hour     INT         NOT NULL,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_session_events_recorded
    ON session_events (recorded_at DESC);

-- S-6e: db_health_log
CREATE TABLE IF NOT EXISTS db_health_log (
    id            BIGSERIAL   PRIMARY KEY,
    probe_ok      BOOLEAN     NOT NULL,
    latency_ms    INT,
    error_message TEXT        DEFAULT '',
    probed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_db_health_probed
    ON db_health_log (probed_at DESC);

-- S-6f: walk_forward_results
ALTER TABLE walk_forward_results
    ADD COLUMN IF NOT EXISTS embargo_pct   FLOAT DEFAULT 0.01,
    ADD COLUMN IF NOT EXISTS n_folds_run   INT   DEFAULT 0,
    ADD COLUMN IF NOT EXISTS n_folds_total INT   DEFAULT 0;

-- S-6g: signals session columns
ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS session_type  TEXT  DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS session_score FLOAT DEFAULT 0.0;
CREATE INDEX IF NOT EXISTS idx_signals_session
    ON signals (session_type, created_at DESC);

COMMIT;
