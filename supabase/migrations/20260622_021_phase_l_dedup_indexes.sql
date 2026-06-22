-- Migration 021: Phase L — Dedup & Missing Indexes
-- L-31: trade_memory schema divergence between 003 and 004
-- L-32: analytics_trades price columns FLOAT -> NUMERIC
-- L-33: missing index on signals.expires_at
-- L-34: missing index on execution_orders.user_id
-- L-35: revoked_tokens no TTL cleanup

BEGIN;

-- L-31: reconcile trade_memory
ALTER TABLE trade_memory
    ADD COLUMN IF NOT EXISTS duration_minutes              FLOAT,
    ADD COLUMN IF NOT EXISTS realized_rr                   FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS confidence_score              FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS market_condition              TEXT,
    ADD COLUMN IF NOT EXISTS smc                           JSONB DEFAULT '{}'::JSONB,
    ADD COLUMN IF NOT EXISTS price_action                  JSONB DEFAULT '{}'::JSONB,
    ADD COLUMN IF NOT EXISTS risk                          JSONB DEFAULT '{}'::JSONB,
    ADD COLUMN IF NOT EXISTS confirmation_patterns         JSONB DEFAULT '[]'::JSONB,
    ADD COLUMN IF NOT EXISTS news_active                   BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS previous_consecutive_losses   INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS notes                         TEXT;

-- L-32: align analytics_trades price columns
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analytics_trades'
          AND column_name = 'entry_price'
          AND data_type = 'double precision'
    ) THEN
        ALTER TABLE analytics_trades
            ALTER COLUMN entry_price  TYPE NUMERIC(18,6) USING entry_price::NUMERIC(18,6),
            ALTER COLUMN exit_price   TYPE NUMERIC(18,6) USING exit_price::NUMERIC(18,6),
            ALTER COLUMN stop_loss    TYPE NUMERIC(18,6) USING stop_loss::NUMERIC(18,6),
            ALTER COLUMN take_profit  TYPE NUMERIC(18,6) USING take_profit::NUMERIC(18,6),
            ALTER COLUMN profit_loss  TYPE NUMERIC(18,4) USING profit_loss::NUMERIC(18,4),
            ALTER COLUMN lot_size     TYPE NUMERIC(10,4) USING lot_size::NUMERIC(10,4);
    END IF;
END $$;

-- L-33: missing index on signals.expires_at
CREATE INDEX IF NOT EXISTS idx_signals_expires_at
    ON public.signals(expires_at)
    WHERE expires_at IS NOT NULL;

-- L-34: missing index on execution_orders.user_id
CREATE INDEX IF NOT EXISTS idx_execution_orders_user_id
    ON public.execution_orders(user_id, created_at DESC);

-- L-35: schedule token cleanup via pg_cron if available
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.schedule(
            'purge-expired-tokens',
            '0 * * * *',
            'SELECT purge_expired_tokens()'
        );
    END IF;
END $$;

-- Additional missing index
CREATE INDEX IF NOT EXISTS idx_trade_memory_created_at
    ON trade_memory(created_at DESC);

COMMIT;
