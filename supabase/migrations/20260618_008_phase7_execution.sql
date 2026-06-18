-- Phase 7: Execution reliability tables
-- MT5 orders, state transitions, reconciliation logs

-- ============================================================
-- orders table
-- ============================================================
CREATE TABLE IF NOT EXISTS execution_orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id TEXT,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
    requested_volume FLOAT NOT NULL,
    requested_price FLOAT NOT NULL DEFAULT 0,
    stop_loss FLOAT NOT NULL DEFAULT 0,
    take_profit FLOAT NOT NULL DEFAULT 0,
    filled_volume FLOAT NOT NULL DEFAULT 0,
    filled_price FLOAT NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'PENDING',
    mt5_ticket BIGINT,
    mt5_deal BIGINT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    timeout_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_execution_orders_signal ON execution_orders (signal_id);
CREATE INDEX IF NOT EXISTS idx_execution_orders_state ON execution_orders (state);
CREATE INDEX IF NOT EXISTS idx_execution_orders_symbol ON execution_orders (symbol);
CREATE INDEX IF NOT EXISTS idx_execution_orders_mt5_ticket ON execution_orders (mt5_ticket);

-- ============================================================
-- order state transitions audit trail
-- ============================================================
CREATE TABLE IF NOT EXISTS order_transitions (
    id BIGSERIAL PRIMARY KEY,
    order_id UUID REFERENCES execution_orders(order_id) ON DELETE CASCADE,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    reason TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_order_transitions_order ON order_transitions (order_id);
CREATE INDEX IF NOT EXISTS idx_order_transitions_created ON order_transitions (created_at);

-- ============================================================
-- reconciliation log
-- ============================================================
CREATE TABLE IF NOT EXISTS reconciliation_log (
    id BIGSERIAL PRIMARY KEY,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mt5_count INT NOT NULL DEFAULT 0,
    db_count INT NOT NULL DEFAULT 0,
    matched INT NOT NULL DEFAULT 0,
    orphan_in_mt5 JSONB DEFAULT '[]',
    orphan_in_db JSONB DEFAULT '[]',
    has_discrepancy BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_reconciliation_checked ON reconciliation_log (checked_at);

-- ============================================================
-- dead letter queue
-- ============================================================
CREATE TABLE IF NOT EXISTS execution_dead_letter (
    id BIGSERIAL PRIMARY KEY,
    order_id TEXT NOT NULL,
    signal_id TEXT,
    error TEXT NOT NULL,
    retcode INT NOT NULL DEFAULT 0,
    attempts INT NOT NULL DEFAULT 0,
    strategy TEXT NOT NULL DEFAULT 'dead_letter',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dead_letter_created ON execution_dead_letter (created_at);

-- ============================================================
-- Add mt5_ticket to public.trades if missing
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'trades' AND column_name = 'mt5_ticket'
    ) THEN
        ALTER TABLE trades ADD COLUMN mt5_ticket BIGINT;
        CREATE INDEX idx_trades_mt5_ticket ON trades (mt5_ticket);
    END IF;
END $$;
