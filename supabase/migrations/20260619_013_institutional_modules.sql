-- Galaxy Vast AI Trading Platform
-- Migration 013: Institutional Modules Tables
-- Fixed: IF NOT EXISTS on all CREATE TABLE (idempotent)

-- Institutional backtests
CREATE TABLE IF NOT EXISTS institutional_backtests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    total_trades INTEGER DEFAULT 0,
    win_rate DECIMAL(5,2) DEFAULT 0,
    profit_factor DECIMAL(10,4) DEFAULT 0,
    sharpe_ratio DECIMAL(10,4) DEFAULT 0,
    sortino_ratio DECIMAL(10,4) DEFAULT 0,
    calmar_ratio DECIMAL(10,4) DEFAULT 0,
    max_drawdown DECIMAL(5,2) DEFAULT 0,
    total_return DECIMAL(10,4) DEFAULT 0,
    parameters JSONB DEFAULT '{}',
    results JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL
);

-- Institutional trades
CREATE TABLE IF NOT EXISTS institutional_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backtest_id UUID REFERENCES institutional_backtests(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    entry_price DECIMAL(20,8) NOT NULL,
    exit_price DECIMAL(20,8),
    entry_time TIMESTAMPTZ,
    exit_time TIMESTAMPTZ,
    pnl DECIMAL(20,8) DEFAULT 0,
    pnl_pct DECIMAL(10,4) DEFAULT 0,
    lot_size DECIMAL(10,4) DEFAULT 0.01,
    commission DECIMAL(10,4) DEFAULT 0,
    slippage DECIMAL(10,4) DEFAULT 0,
    spread DECIMAL(10,4) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Monte Carlo results
CREATE TABLE IF NOT EXISTS institutional_monte_carlo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20),
    simulations INTEGER DEFAULT 1000,
    probability_of_ruin DECIMAL(5,4) DEFAULT 0,
    expected_return DECIMAL(10,4) DEFAULT 0,
    var_95 DECIMAL(10,4) DEFAULT 0,
    cvar_95 DECIMAL(10,4) DEFAULT 0,
    percentiles JSONB DEFAULT '{}',
    parameters JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Walk-Forward Optimization results
CREATE TABLE IF NOT EXISTS institutional_wfo_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20),
    n_windows INTEGER DEFAULT 0,
    is_sharpe DECIMAL(10,4) DEFAULT 0,
    oos_sharpe DECIMAL(10,4) DEFAULT 0,
    robustness_ratio DECIMAL(10,4) DEFAULT 0,
    windows JSONB DEFAULT '[]',
    parameters JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Replay sessions
CREATE TABLE IF NOT EXISTS institutional_replay_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20),
    timeframe VARCHAR(10),
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    candles_count INTEGER DEFAULT 0,
    trades_count INTEGER DEFAULT 0,
    final_equity DECIMAL(20,8) DEFAULT 0,
    session_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_inst_backtests_symbol ON institutional_backtests(symbol);
CREATE INDEX IF NOT EXISTS idx_inst_backtests_created ON institutional_backtests(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inst_trades_backtest ON institutional_trades(backtest_id);
CREATE INDEX IF NOT EXISTS idx_inst_trades_symbol ON institutional_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_inst_mc_symbol ON institutional_monte_carlo(symbol);
CREATE INDEX IF NOT EXISTS idx_inst_wfo_symbol ON institutional_wfo_results(symbol);

-- RLS
ALTER TABLE institutional_backtests ENABLE ROW LEVEL SECURITY;
ALTER TABLE institutional_trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE institutional_monte_carlo ENABLE ROW LEVEL SECURITY;
ALTER TABLE institutional_wfo_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE institutional_replay_sessions ENABLE ROW LEVEL SECURITY;

-- Policies (service role bypass)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'institutional_backtests'
        AND policyname = 'service_role_all_institutional_backtests'
    ) THEN
        CREATE POLICY service_role_all_institutional_backtests
            ON institutional_backtests FOR ALL
            USING (auth.role() = 'service_role');
    END IF;
END $$;
