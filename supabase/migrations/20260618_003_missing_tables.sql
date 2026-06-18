-- ============================================================
-- Galaxy Vast AI Trading Platform
-- Migration 003 - Missing Tables Fix
-- ============================================================
-- trade_memory, analytics_trades, analytics_snapshots,
-- analytics_daily, missing indexes on trades+signals
-- ============================================================

CREATE TABLE IF NOT EXISTS public.trade_memory (
    trade_id                    TEXT            PRIMARY KEY,
    signal_id                   TEXT,
    symbol                      VARCHAR(20)     NOT NULL,
    entry_time                  TIMESTAMPTZ,
    exit_time                   TIMESTAMPTZ,
    duration_minutes            NUMERIC(10,2)   DEFAULT 0,
    entry_price                 NUMERIC(18,6)   DEFAULT 0,
    exit_price                  NUMERIC(18,6)   DEFAULT 0,
    stop_loss                   NUMERIC(18,6)   DEFAULT 0,
    take_profit                 NUMERIC(18,6)   DEFAULT 0,
    direction                   VARCHAR(10),
    outcome                     VARCHAR(20),
    pnl_pips                    NUMERIC(10,2)   DEFAULT 0,
    pnl_usd                     NUMERIC(18,4)   DEFAULT 0,
    realized_rr                 NUMERIC(10,4)   DEFAULT 0,
    confidence_score            NUMERIC(5,2)    DEFAULT 0,
    session                     VARCHAR(30),
    market_condition            VARCHAR(50),
    smc                         JSONB           DEFAULT '{}',
    price_action                JSONB           DEFAULT '{}',
    risk                        JSONB           DEFAULT '{}',
    confirmation_patterns       JSONB           DEFAULT '[]',
    news_active                 BOOLEAN         DEFAULT FALSE,
    previous_consecutive_losses INTEGER         DEFAULT 0,
    notes                       TEXT,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trade_memory_symbol
    ON public.trade_memory (symbol);
CREATE INDEX IF NOT EXISTS idx_trade_memory_outcome
    ON public.trade_memory (outcome);
CREATE INDEX IF NOT EXISTS idx_trade_memory_entry_time
    ON public.trade_memory (entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_trade_memory_symbol_outcome
    ON public.trade_memory (symbol, outcome);

CREATE TABLE IF NOT EXISTS public.analytics_trades (
    id               BIGSERIAL       PRIMARY KEY,
    ticket           BIGINT          NOT NULL UNIQUE,
    symbol           VARCHAR(20)     NOT NULL,
    direction        VARCHAR(4)      NOT NULL CHECK (direction IN ('BUY','SELL')),
    status           VARCHAR(10)     NOT NULL DEFAULT 'CLOSED',
    entry_price      NUMERIC(18,6)   NOT NULL,
    exit_price       NUMERIC(18,6)   NOT NULL,
    stop_loss        NUMERIC(18,6)   NOT NULL DEFAULT 0,
    lot_size         NUMERIC(10,4)   NOT NULL DEFAULT 0,
    profit_loss      NUMERIC(18,4)   NOT NULL DEFAULT 0,
    pips             NUMERIC(10,2)   DEFAULT 0,
    risk_amount      NUMERIC(18,4)   DEFAULT 0,
    reward_amount    NUMERIC(18,4)   DEFAULT 0,
    confidence_score NUMERIC(5,2)    DEFAULT 0,
    session          VARCHAR(20)     DEFAULT 'UNKNOWN',
    strategy_tags    JSONB           DEFAULT '[]',
    open_time        TIMESTAMPTZ     NOT NULL,
    close_time       TIMESTAMPTZ     NOT NULL,
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT analytics_trades_close_after_open CHECK (close_time >= open_time)
);

CREATE INDEX IF NOT EXISTS idx_analytics_trades_symbol
    ON public.analytics_trades (symbol);
CREATE INDEX IF NOT EXISTS idx_analytics_trades_close_time
    ON public.analytics_trades (close_time DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_trades_open_time
    ON public.analytics_trades (open_time DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_trades_symbol_close
    ON public.analytics_trades (symbol, close_time DESC);

CREATE TABLE IF NOT EXISTS public.analytics_snapshots (
    id            BIGSERIAL    PRIMARY KEY,
    snapshot_key  VARCHAR(64)  NOT NULL UNIQUE,
    metrics_json  JSONB        NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_key
    ON public.analytics_snapshots (snapshot_key);

CREATE TABLE IF NOT EXISTS public.analytics_daily (
    id              BIGSERIAL    PRIMARY KEY,
    trade_date      DATE         NOT NULL,
    symbol          VARCHAR(20)  NOT NULL DEFAULT 'ALL',
    total_trades    INTEGER      NOT NULL DEFAULT 0,
    winning_trades  INTEGER      NOT NULL DEFAULT 0,
    losing_trades   INTEGER      NOT NULL DEFAULT 0,
    total_pips      NUMERIC(10,2) DEFAULT 0,
    total_profit    NUMERIC(18,4) DEFAULT 0,
    win_rate        NUMERIC(5,2)  DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_analytics_daily_date_symbol UNIQUE (trade_date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_analytics_daily_date
    ON public.analytics_daily (trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_trades_user_id
    ON public.trades (user_id);
CREATE INDEX IF NOT EXISTS idx_trades_user_status
    ON public.trades (user_id, status);
CREATE INDEX IF NOT EXISTS idx_signals_user_id
    ON public.signals (user_id);
CREATE INDEX IF NOT EXISTS idx_signals_user_symbol
    ON public.signals (user_id, symbol);
