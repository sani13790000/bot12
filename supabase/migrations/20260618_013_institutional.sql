-- Galaxy Vast — Institutional-grade module tables
-- Run after all previous migrations

-- Institutional trades persistence
CREATE TABLE IF NOT EXISTS institutional_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    source TEXT NOT NULL DEFAULT 'tick_backtest',
    trade_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_time TEXT,
    exit_time TEXT,
    entry_price NUMERIC,
    exit_price NUMERIC,
    stop_loss NUMERIC,
    take_profit NUMERIC,
    lot_size NUMERIC,
    pnl_pips NUMERIC,
    pnl_usd NUMERIC,
    outcome TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_institutional_trades_user ON institutional_trades(user_id);
CREATE INDEX IF NOT EXISTS idx_institutional_trades_symbol ON institutional_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_institutional_trades_created ON institutional_trades(created_at DESC);

-- Institutional backtest results
CREATE TABLE IF NOT EXISTS institutional_backtests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    run_name TEXT NOT NULL,
    config JSONB,
    final_balance NUMERIC,
    total_return_pct NUMERIC,
    total_trades INTEGER,
    metrics JSONB,
    equity_curve JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_institutional_backtests_user ON institutional_backtests(user_id);
CREATE INDEX IF NOT EXISTS idx_institutional_backtests_created ON institutional_backtests(created_at DESC);

-- Market replay sessions
CREATE TABLE IF NOT EXISTS institutional_replay_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    state JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Row Level Security
ALTER TABLE institutional_trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE institutional_backtests ENABLE ROW LEVEL SECURITY;
ALTER TABLE institutional_replay_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS institutional_trades_user_isolation ON institutional_trades
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY IF NOT EXISTS institutional_backtests_user_isolation ON institutional_backtests
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY IF NOT EXISTS institutional_replay_sessions_user_isolation ON institutional_replay_sessions
    FOR ALL USING (auth.uid() = user_id);
