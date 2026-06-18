-- ============================================================
-- Migration 004: Stabilization — missing tables + indexes
-- Galaxy Vast AI Trading Platform
-- ============================================================

-- ------------------------------------------------------------
-- 1. trade_memory  (TradeMemory.initialize() needs this)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trade_memory (
    trade_id                    TEXT PRIMARY KEY,
    signal_id                   TEXT,
    symbol                      TEXT        NOT NULL DEFAULT 'XAUUSD',
    entry_time                  TIMESTAMPTZ,
    exit_time                   TIMESTAMPTZ,
    duration_minutes            FLOAT,
    entry_price                 FLOAT,
    exit_price                  FLOAT,
    stop_loss                   FLOAT,
    take_profit                 FLOAT,
    direction                   TEXT,
    outcome                     TEXT,
    pnl_pips                    FLOAT,
    pnl_usd                     FLOAT,
    realized_rr                 FLOAT,
    confidence_score            FLOAT,
    session                     TEXT,
    market_condition            TEXT,
    smc                         JSONB       DEFAULT '{}'::JSONB,
    price_action                JSONB       DEFAULT '{}'::JSONB,
    risk                        JSONB       DEFAULT '{}'::JSONB,
    confirmation_patterns       JSONB       DEFAULT '[]'::JSONB,
    news_active                 BOOLEAN     DEFAULT FALSE,
    previous_consecutive_losses INT         DEFAULT 0,
    notes                       TEXT,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trade_memory_symbol    ON trade_memory(symbol);
CREATE INDEX IF NOT EXISTS idx_trade_memory_exit_time ON trade_memory(exit_time DESC);
CREATE INDEX IF NOT EXISTS idx_trade_memory_outcome   ON trade_memory(outcome);
CREATE INDEX IF NOT EXISTS idx_trade_memory_direction ON trade_memory(direction);

-- ------------------------------------------------------------
-- 2. analytics tables (analytics_service.py needs these)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics_trades (
    id              BIGSERIAL   PRIMARY KEY,
    trade_id        TEXT        NOT NULL,
    user_id         UUID,
    symbol          TEXT,
    direction       TEXT,
    outcome         TEXT,
    pnl_usd         FLOAT,
    pnl_pips        FLOAT,
    rr_ratio        FLOAT,
    confidence      FLOAT,
    session         TEXT,
    agents_json     JSONB       DEFAULT '{}'::JSONB,
    entry_time      TIMESTAMPTZ,
    exit_time       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analytics_trades_user   ON analytics_trades(user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_trades_symbol ON analytics_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_analytics_trades_time   ON analytics_trades(exit_time DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_trades_outcome ON analytics_trades(outcome);

CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id              BIGSERIAL   PRIMARY KEY,
    user_id         UUID,
    snapshot_date   DATE        NOT NULL DEFAULT CURRENT_DATE,
    equity          FLOAT,
    balance         FLOAT,
    drawdown_pct    FLOAT,
    win_rate        FLOAT,
    profit_factor   FLOAT,
    total_trades    INT,
    metadata        JSONB       DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_analytics_snapshots_user_date
    ON analytics_snapshots(user_id, snapshot_date);

CREATE TABLE IF NOT EXISTS analytics_daily (
    id              BIGSERIAL   PRIMARY KEY,
    user_id         UUID,
    date            DATE        NOT NULL DEFAULT CURRENT_DATE,
    trades          INT         DEFAULT 0,
    wins            INT         DEFAULT 0,
    losses          INT         DEFAULT 0,
    pnl_usd         FLOAT       DEFAULT 0.0,
    best_trade_usd  FLOAT       DEFAULT 0.0,
    worst_trade_usd FLOAT       DEFAULT 0.0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
);

-- ------------------------------------------------------------
-- 3. self_learning tables (retraining_service.py needs these)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS self_learning_trades (
    id              BIGSERIAL   PRIMARY KEY,
    trade_id        TEXT        NOT NULL,
    user_id         UUID,
    features_json   JSONB       DEFAULT '{}'::JSONB,
    label           INT,  -- 1=WIN 0=LOSS
    model_version   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sl_trades_user    ON self_learning_trades(user_id);
CREATE INDEX IF NOT EXISTS idx_sl_trades_created ON self_learning_trades(created_at DESC);

CREATE TABLE IF NOT EXISTS self_learning_model_registry (
    id              BIGSERIAL   PRIMARY KEY,
    model_name      TEXT        NOT NULL,
    model_version   TEXT        NOT NULL,
    user_id         UUID,
    auc_roc         FLOAT,
    accuracy        FLOAT,
    f1_score        FLOAT,
    n_samples       INT,
    is_active       BOOLEAN     DEFAULT FALSE,
    model_path      TEXT,
    metadata        JSONB       DEFAULT '{}'::JSONB,
    trained_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(model_name, model_version)
);

CREATE INDEX IF NOT EXISTS idx_model_registry_active ON self_learning_model_registry(is_active);
CREATE INDEX IF NOT EXISTS idx_model_registry_name   ON self_learning_model_registry(model_name);

CREATE TABLE IF NOT EXISTS self_learning_retrain_jobs (
    id              BIGSERIAL   PRIMARY KEY,
    job_id          TEXT        NOT NULL UNIQUE DEFAULT gen_random_uuid()::TEXT,
    user_id         UUID,
    status          TEXT        NOT NULL DEFAULT 'PENDING',
    trigger         TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    result_json     JSONB       DEFAULT '{}'::JSONB,
    error_msg       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_retrain_jobs_status ON self_learning_retrain_jobs(status);
CREATE INDEX IF NOT EXISTS idx_retrain_jobs_user   ON self_learning_retrain_jobs(user_id);

-- ------------------------------------------------------------
-- 4. Missing indexes on existing tables
-- ------------------------------------------------------------

-- public.trades
CREATE INDEX IF NOT EXISTS idx_trades_user_id      ON public.trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol       ON public.trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status       ON public.trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_opened_at    ON public.trades(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_closed_at    ON public.trades(closed_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_direction    ON public.trades(direction);

-- public.signals
CREATE INDEX IF NOT EXISTS idx_signals_user_id     ON public.signals(user_id);
CREATE INDEX IF NOT EXISTS idx_signals_symbol      ON public.signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_status      ON public.signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_created_at  ON public.signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_direction   ON public.signals(direction);

-- ------------------------------------------------------------
-- Done
-- ------------------------------------------------------------
SELECT 'migration 004 complete' AS status;
