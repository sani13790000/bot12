"""
Galaxy Vast AI Trading Platform
Analytics DB Schema — PostgreSQL DDL
"""

ANALYTICS_SQL = """
-- ============================================================
-- Galaxy Vast Analytics Schema
-- ============================================================

-- 1. Trade records for analytics calculation
CREATE TABLE IF NOT EXISTS analytics_trades (
    id               BIGSERIAL PRIMARY KEY,
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
    CONSTRAINT analytics_trades_direction_check CHECK (direction IN ('BUY','SELL')),
    CONSTRAINT analytics_trades_close_after_open CHECK (close_time >= open_time)
);

CREATE INDEX IF NOT EXISTS idx_analytics_trades_symbol
    ON analytics_trades (symbol);
CREATE INDEX IF NOT EXISTS idx_analytics_trades_close_time
    ON analytics_trades (close_time DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_trades_open_time
    ON analytics_trades (open_time DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_trades_symbol_close
    ON analytics_trades (symbol, close_time DESC);

-- 2. Cached analytics snapshots (period → metrics JSON)
CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id            BIGSERIAL    PRIMARY KEY,
    snapshot_key  VARCHAR(64)  NOT NULL UNIQUE,
    metrics_json  JSONB        NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_key
    ON analytics_snapshots (snapshot_key);

-- 3. Daily aggregated stats (for fast dashboard queries)
CREATE TABLE IF NOT EXISTS analytics_daily (
    id              BIGSERIAL    PRIMARY KEY,
    trade_date      DATE         NOT NULL,
    symbol          VARCHAR(20)  NOT NULL,
    total_trades    INT          NOT NULL DEFAULT 0,
    winning_trades  INT          NOT NULL DEFAULT 0,
    losing_trades   INT          NOT NULL DEFAULT 0,
    gross_profit    NUMERIC(18,4) NOT NULL DEFAULT 0,
    gross_loss      NUMERIC(18,4) NOT NULL DEFAULT 0,
    net_profit      NUMERIC(18,4) NOT NULL DEFAULT 0,
    max_drawdown    NUMERIC(8,4)  NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (trade_date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_analytics_daily_date_symbol
    ON analytics_daily (trade_date DESC, symbol);

-- 4. Useful views
CREATE OR REPLACE VIEW v_analytics_overview AS
SELECT
    symbol,
    COUNT(*)                                        AS total_trades,
    COUNT(*) FILTER (WHERE profit_loss > 0)         AS wins,
    COUNT(*) FILTER (WHERE profit_loss < 0)         AS losses,
    ROUND(SUM(profit_loss)::NUMERIC, 2)             AS net_profit,
    ROUND(AVG(profit_loss)::NUMERIC, 4)             AS avg_pnl,
    ROUND(
        COUNT(*) FILTER (WHERE profit_loss > 0)::NUMERIC
        / NULLIF(COUNT(*), 0), 4
    )                                               AS win_rate,
    ROUND(AVG(confidence_score)::NUMERIC, 2)        AS avg_confidence,
    MIN(open_time)                                  AS first_trade,
    MAX(close_time)                                 AS last_trade
FROM analytics_trades
WHERE status = 'CLOSED'
GROUP BY symbol
ORDER BY net_profit DESC;


CREATE OR REPLACE VIEW v_analytics_daily_summary AS
SELECT
    DATE(close_time)                               AS trade_date,
    COUNT(*)                                       AS total_trades,
    COUNT(*) FILTER (WHERE profit_loss > 0)        AS wins,
    ROUND(SUM(profit_loss)::NUMERIC, 2)            AS daily_pnl,
    ROUND(
        COUNT(*) FILTER (WHERE profit_loss > 0)::NUMERIC
        / NULLIF(COUNT(*), 0) * 100, 1
    )                                              AS win_rate_pct
FROM analytics_trades
WHERE status = 'CLOSED'
GROUP BY DATE(close_time)
ORDER BY trade_date DESC;
""";

__all__ = ["ANALYTICS_SQL"]
