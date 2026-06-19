-- Migration 013: Institutional Modules
-- Idempotent: all statements use IF NOT EXISTS
-- Safe to run multiple times without error

BEGIN;

-- Institutional backtests
CREATE TABLE IF NOT EXISTS institutional_backtests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    start_date      TIMESTAMPTZ,
    end_date        TIMESTAMPTZ,
    total_trades    INTEGER DEFAULT 0,
    win_rate        NUMERIC(5,2),
    sharpe_ratio    NUMERIC(8,4),
    sortino_ratio   NUMERIC(8,4),
    calmar_ratio    NUMERIC(8,4),
    max_drawdown    NUMERIC(8,4),
    total_pnl       NUMERIC(12,4),
    parameters      JSONB DEFAULT '{}',
    results         JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inst_backtests_symbol     ON institutional_backtests(symbol);
CREATE INDEX IF NOT EXISTS idx_inst_backtests_created_at ON institutional_backtests(created_at DESC);

-- Institutional trades
CREATE TABLE IF NOT EXISTS institutional_trades (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backtest_id     UUID REFERENCES institutional_backtests(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    direction       TEXT CHECK (direction IN ('long','short')),
    entry_price     NUMERIC(12,5),
    exit_price      NUMERIC(12,5),
    lot_size        NUMERIC(8,4),
    pnl             NUMERIC(12,4),
    duration_bars   INTEGER,
    entry_time      TIMESTAMPTZ,
    exit_time       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inst_trades_backtest_id ON institutional_trades(backtest_id);
CREATE INDEX IF NOT EXISTS idx_inst_trades_symbol      ON institutional_trades(symbol);

-- Monte Carlo results
CREATE TABLE IF NOT EXISTS institutional_monte_carlo (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          TEXT NOT NULL,
    n_simulations   INTEGER NOT NULL,
    initial_balance NUMERIC(12,2),
    final_p10       NUMERIC(12,4),
    final_p50       NUMERIC(12,4),
    final_p90       NUMERIC(12,4),
    ruin_probability NUMERIC(5,4),
    parameters      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inst_mc_symbol     ON institutional_monte_carlo(symbol);
CREATE INDEX IF NOT EXISTS idx_inst_mc_created_at ON institutional_monte_carlo(created_at DESC);

-- Walk-forward results
CREATE TABLE IF NOT EXISTS institutional_wfo_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    n_folds         INTEGER NOT NULL,
    is_sharpe_avg   NUMERIC(8,4),
    oos_sharpe_avg  NUMERIC(8,4),
    robustness_score NUMERIC(5,2),
    fold_results    JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inst_wfo_symbol ON institutional_wfo_results(symbol);

-- Replay sessions
CREATE TABLE IF NOT EXISTS institutional_replay_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    n_candles       INTEGER,
    session_data    JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inst_replay_symbol ON institutional_replay_sessions(symbol);

COMMIT;
