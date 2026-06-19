-- Migration 013: Institutional modules tables
-- Run after 012

BEGIN;

-- Institutional backtest results
CREATE TABLE IF NOT EXISTS institutional_backtest_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL DEFAULT 'XAUUSD',
    timeframe TEXT NOT NULL DEFAULT 'M15',
    initial_balance NUMERIC(15,2) NOT NULL,
    final_balance NUMERIC(15,2),
    total_trades INTEGER DEFAULT 0,
    win_rate NUMERIC(6,2) DEFAULT 0,
    profit_factor NUMERIC(8,4) DEFAULT 0,
    sharpe_ratio NUMERIC(8,4) DEFAULT 0,
    sortino_ratio NUMERIC(8,4) DEFAULT 0,
    calmar_ratio NUMERIC(8,4) DEFAULT 0,
    max_drawdown_pct NUMERIC(6,2) DEFAULT 0,
    recovery_factor NUMERIC(8,4) DEFAULT 0,
    total_commission NUMERIC(12,2) DEFAULT 0,
    total_spread_cost NUMERIC(12,2) DEFAULT 0,
    total_slippage_cost NUMERIC(12,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Institutional trades (backtest)
CREATE TABLE IF NOT EXISTS institutional_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backtest_id UUID REFERENCES institutional_backtest_results(id) ON DELETE CASCADE,
    trade_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    open_time NUMERIC(20,3),
    close_time NUMERIC(20,3),
    open_price NUMERIC(15,5),
    close_price NUMERIC(15,5),
    stop_loss NUMERIC(15,5),
    take_profit NUMERIC(15,5),
    lot_size NUMERIC(8,3),
    gross_profit NUMERIC(12,2),
    net_profit NUMERIC(12,2),
    commission NUMERIC(8,2),
    spread_cost NUMERIC(8,2),
    slippage_cost NUMERIC(8,2),
    close_reason TEXT,
    explanation JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Monte Carlo results
CREATE TABLE IF NOT EXISTS institutional_monte_carlo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    n_simulations INTEGER NOT NULL,
    n_trades INTEGER NOT NULL,
    initial_balance NUMERIC(15,2),
    median_final_balance NUMERIC(15,2),
    mean_final_balance NUMERIC(15,2),
    percentile_5 NUMERIC(15,2),
    percentile_25 NUMERIC(15,2),
    percentile_75 NUMERIC(15,2),
    percentile_95 NUMERIC(15,2),
    probability_of_ruin NUMERIC(6,2),
    probability_of_profit NUMERIC(6,2),
    expected_max_drawdown_pct NUMERIC(6,2),
    ruin_threshold NUMERIC(15,2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Walk-Forward results
CREATE TABLE IF NOT EXISTS institutional_wfo_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    n_windows INTEGER NOT NULL,
    optimization_metric TEXT NOT NULL DEFAULT 'sharpe_ratio',
    avg_is_metric NUMERIC(8,4),
    avg_val_metric NUMERIC(8,4),
    avg_oos_metric NUMERIC(8,4),
    avg_robustness_ratio NUMERIC(6,4),
    is_robust BOOLEAN DEFAULT FALSE,
    total_oos_trades INTEGER DEFAULT 0,
    oos_win_rate NUMERIC(6,2),
    oos_profit_factor NUMERIC(8,4),
    best_params JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Market Replay sessions
CREATE TABLE IF NOT EXISTS institutional_replay_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL DEFAULT 'XAUUSD',
    timeframe TEXT NOT NULL DEFAULT 'M15',
    start_timestamp NUMERIC(20,3),
    end_timestamp NUMERIC(20,3),
    total_candles INTEGER DEFAULT 0,
    trades_count INTEGER DEFAULT 0,
    final_equity NUMERIC(15,2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_inst_backtest_symbol ON institutional_backtest_results(symbol);
CREATE INDEX IF NOT EXISTS idx_inst_backtest_created ON institutional_backtest_results(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inst_trades_backtest ON institutional_trades(backtest_id);
CREATE INDEX IF NOT EXISTS idx_inst_trades_symbol ON institutional_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_inst_mc_created ON institutional_monte_carlo(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inst_wfo_created ON institutional_wfo_results(created_at DESC);

-- RLS
ALTER TABLE institutional_backtest_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE institutional_trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE institutional_monte_carlo ENABLE ROW LEVEL SECURITY;
ALTER TABLE institutional_wfo_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE institutional_replay_sessions ENABLE ROW LEVEL SECURITY;

-- Service role full access
CREATE POLICY inst_backtest_service ON institutional_backtest_results
    USING (auth.role() = 'service_role');
CREATE POLICY inst_trades_service ON institutional_trades
    USING (auth.role() = 'service_role');
CREATE POLICY inst_mc_service ON institutional_monte_carlo
    USING (auth.role() = 'service_role');
CREATE POLICY inst_wfo_service ON institutional_wfo_results
    USING (auth.role() = 'service_role');
CREATE POLICY inst_replay_service ON institutional_replay_sessions
    USING (auth.role() = 'service_role');

COMMIT;
