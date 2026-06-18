-- ===============================================================================
-- Galaxy Vast AI Trading Platform
-- Migration 003 - Missing Tables
-- Date: 2026-06-18
-- Includes: trade_memory, analytics, self_learning tables
-- ===============================================================================

-- trade_memory table (E3 Fix: persistence bridge)
CREATE TABLE IF NOT EXISTS trade_memory (
    trade_id                    TEXT          PRIMARY KEY,
    signal_id                   TEXT,
    symbol                      VARCHAR(20)   NOT NULL,
    entry_time                  TIMESTAMPTZ,
    exit_time                   TIMESTAMPTZ,
    duration_minutes            FLOAT,
    entry_price                 FLOAT,
    exit_price                  FLOAT,
    stop_loss                   FLOAT,
    take_profit                 FLOAT,
    direction                   VARCHAR(10),
    outcome                     VARCHAR(20),
    pnl_pips                    FLOAT         DEFAULT 0.0,
    pnl_usd                     FLOAT         DEFAULT 0.0,
    realized_rr                 FLOAT         DEFAULT 0.0,
    confidence_score            FLOAT         DEFAULT 0.0,
    session                     VARCHAR(30),
    market_condition            VARCHAR(30),
    smc                         JSONB,
    price_action                JSONB,
    risk                        JSONB,
    confirmation_patterns       JSONB,
    news_active                 BOOLEAN       DEFAULT FALSE,
    previous_consecutive_losses INT          DEFAULT 0,
    notes                       TEXT,
    created_at                  TIMESTAMPTZ   DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_trade_memory_symbol     ON trade_memory (symbol);
CREATE INDEX IF NOT EXISTS idx_trade_memory_outcome    ON trade_memory (outcome);
CREATE INDEX IF NOT EXISTS idx_trade_memory_entry_time ON trade_memory (entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_trade_memory_session    ON trade_memory (session);

-- analytics_trades table
CREATE TABLE IF NOT EXISTS analytics_trades (
    id               BIGSERIAL       PRIMARY KEY,
    ticket           BIGINT          NOT NULL UNIQUE,
    symbol           VARCHAR(20)     NOT NULL,
    direction        VARCHAR(10)     NOT NULL,
    open_time        TIMESTAMPTZ,
    close_time       TIMESTAMPTZ,
    entry_price      FLOAT,
    close_price      FLOAT,
    lot_size         FLOAT           DEFAULT 0.01,
    stop_loss        FLOAT,
    take_profit      FLOAT,
    profit_loss      FLOAT           DEFAULT 0.0,
    pips             FLOAT           DEFAULT 0.0,
    commission       FLOAT           DEFAULT 0.0,
    swap             FLOAT           DEFAULT 0.0,
    net_profit       FLOAT           DEFAULT 0.0,
    risk_reward      FLOAT,
    entry_score      FLOAT,
    decision_score   FLOAT,
    session          VARCHAR(30),
    setup_type       VARCHAR(50),
    status           VARCHAR(20),
    metadata         JSONB,
    created_at       TIMESTAMPTZ     DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_analytics_symbol     ON analytics_trades (symbol);
CREATE INDEX IF NOT EXISTS idx_analytics_close_time ON analytics_trades (close_time DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_status     ON analytics_trades (status);
CREATE INDEX IF NOT EXISTS idx_analytics_session    ON analytics_trades (session);

-- analytics_daily_performance table
CREATE TABLE IF NOT EXISTS analytics_daily_performance (
    id               BIGSERIAL       PRIMARY KEY,
    trade_date       DATE            NOT NULL,
    symbol           VARCHAR(20),
    total_trades     INT             DEFAULT 0,
    winning_trades   INT             DEFAULT 0,
    losing_trades    INT             DEFAULT 0,
    gross_profit     FLOAT           DEFAULT 0.0,
    gross_loss       FLOAT           DEFAULT 0.0,
    net_profit       FLOAT           DEFAULT 0.0,
    win_rate         FLOAT           DEFAULT 0.0,
    profit_factor    FLOAT           DEFAULT 0.0,
    avg_pips         FLOAT           DEFAULT 0.0,
    max_drawdown     FLOAT           DEFAULT 0.0,
    sharpe_ratio     FLOAT           DEFAULT 0.0,
    created_at       TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (trade_date, symbol)
);
CREATE INDEX IF NOT EXISTS idx_daily_perf_date   ON analytics_daily_performance (trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_perf_symbol ON analytics_daily_performance (symbol);

-- analytics_agent_performance table
CREATE TABLE IF NOT EXISTS analytics_agent_performance (
    id               BIGSERIAL       PRIMARY KEY,
    agent_name       VARCHAR(50)     NOT NULL,
    trade_id         TEXT,
    signal_id        TEXT,
    symbol           VARCHAR(20),
    score            FLOAT,
    confidence       FLOAT,
    direction        VARCHAR(10),
    status           VARCHAR(20),
    elapsed_ms       FLOAT,
    was_correct      BOOLEAN,
    recorded_at      TIMESTAMPTZ     DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_perf_name     ON analytics_agent_performance (agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_perf_recorded ON analytics_agent_performance (recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_perf_symbol   ON analytics_agent_performance (symbol);

-- self_learning_trades table
CREATE TABLE IF NOT EXISTS self_learning_trades (
    trade_id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    mt5_ticket             BIGINT        NOT NULL,
    symbol                 VARCHAR(20)   NOT NULL,
    direction              VARCHAR(10),
    open_time              TIMESTAMPTZ,
    close_time             TIMESTAMPTZ,
    entry_price            FLOAT,
    close_price            FLOAT,
    lot_size               FLOAT,
    profit_loss            FLOAT,
    pips                   FLOAT,
    entry_score            FLOAT,
    decision_confidence    FLOAT,
    outcome                VARCHAR(20),
    is_rule_violation      BOOLEAN       DEFAULT FALSE,
    violation_reason       TEXT,
    features               JSONB,
    created_at             TIMESTAMPTZ   DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sl_trades_symbol  ON self_learning_trades (symbol);
CREATE INDEX IF NOT EXISTS idx_sl_trades_outcome ON self_learning_trades (outcome);

-- self_learning_model_registry table
CREATE TABLE IF NOT EXISTS self_learning_model_registry (
    id               BIGSERIAL       PRIMARY KEY,
    model_id         UUID            NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    symbol           VARCHAR(20)     NOT NULL,
    version          TEXT            NOT NULL,
    file_path        TEXT,
    scaler_path      TEXT,
    metadata_path    TEXT,
    train_auc        FLOAT           DEFAULT 0.0,
    val_auc          FLOAT           DEFAULT 0.0,
    test_auc         FLOAT           DEFAULT 0.0,
    accuracy         FLOAT           DEFAULT 0.0,
    f1_score         FLOAT           DEFAULT 0.0,
    train_samples    INT             DEFAULT 0,
    test_samples     INT             DEFAULT 0,
    is_active        BOOLEAN         DEFAULT FALSE,
    is_acceptable    BOOLEAN         DEFAULT FALSE,
    promoted_at      TIMESTAMPTZ,
    rolled_back_at   TIMESTAMPTZ,
    created_at       TIMESTAMPTZ     DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_model_reg_symbol ON self_learning_model_registry (symbol);
CREATE INDEX IF NOT EXISTS idx_model_reg_active ON self_learning_model_registry (is_active);

-- self_learning_retrain_jobs table
CREATE TABLE IF NOT EXISTS self_learning_retrain_jobs (
    job_id           UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol           VARCHAR(20)     NOT NULL,
    status           VARCHAR(30)     NOT NULL,
    reason           TEXT,
    old_model_id     UUID,
    new_model_id     UUID,
    old_auc          FLOAT           DEFAULT 0.0,
    new_auc          FLOAT           DEFAULT 0.0,
    auc_delta        FLOAT           DEFAULT 0.0,
    was_promoted     BOOLEAN         DEFAULT FALSE,
    was_rolled_back  BOOLEAN         DEFAULT FALSE,
    error_message    TEXT,
    training_samples  INT            DEFAULT 0,
    started_at       TIMESTAMPTZ     DEFAULT NOW(),
    completed_at     TIMESTAMPTZ,
    metadata         JSONB
);
CREATE INDEX IF NOT EXISTS idx_retrain_jobs_symbol  ON self_learning_retrain_jobs (symbol);
CREATE INDEX IF NOT EXISTS idx_retrain_jobs_status  ON self_learning_retrain_jobs (status);
CREATE INDEX IF NOT EXISTS idx_retrain_jobs_started ON self_learning_retrain_jobs (started_at DESC);

-- Missing indexes on main tables (H8 Fix)
CREATE INDEX IF NOT EXISTS idx_trades_user_id    ON public.trades (user_id);
CREATE INDEX IF NOT EXISTS idx_signals_user_id   ON public.signals (user_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol     ON public.trades (symbol);
CREATE INDEX IF NOT EXISTS idx_trades_created_at ON public.trades (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_symbol    ON public.signals (symbol);
CREATE INDEX IF NOT EXISTS idx_signals_status    ON public.signals (status);
CREATE INDEX IF NOT EXISTS idx_signals_created   ON public.signals (generated_at DESC);
