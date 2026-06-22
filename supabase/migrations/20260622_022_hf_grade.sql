-- Migration 022: Hedge-Fund Grade Architecture
-- HF-1: circuit_breaker_events table
-- HF-4: orphan_positions registry
-- HF-5: order_journal table + indexes + RLS

BEGIN;

-- HF-1: Circuit Breaker Events
CREATE TABLE IF NOT EXISTS circuit_breaker_events (
    id           BIGSERIAL   PRIMARY KEY,
    breaker_name TEXT        NOT NULL,
    old_state    TEXT        NOT NULL,
    new_state    TEXT        NOT NULL,
    reason       TEXT,
    failure_count INT        DEFAULT 0,
    window_s     INT         DEFAULT 60,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cbe_name_ts ON circuit_breaker_events(breaker_name, created_at DESC);

-- HF-5: Order Journal
CREATE TABLE IF NOT EXISTS order_journal (
    entry_id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type       TEXT        NOT NULL,
    timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    signal_id        UUID,
    order_id         UUID,
    mt5_ticket       BIGINT,
    user_id          UUID        REFERENCES auth.users(id) ON DELETE SET NULL,
    symbol           TEXT,
    direction        TEXT        CHECK (direction IN ('BUY', 'SELL')),
    lot_size         NUMERIC(10,4),
    price            NUMERIC(18,6),
    stop_loss        NUMERIC(18,6),
    take_profit      NUMERIC(18,6),
    risk_allowed     BOOLEAN,
    risk_reason      TEXT,
    lot_multiplier   NUMERIC(8,4),
    pip_value_used   NUMERIC(10,4),
    fill_price       NUMERIC(18,6),
    fill_volume      NUMERIC(10,4),
    fill_latency_ms  NUMERIC(10,2),
    requested_price  NUMERIC(18,6),
    slippage_pips    NUMERIC(10,4),
    slippage_usd     NUMERIC(14,6),
    close_price      NUMERIC(18,6),
    close_reason     TEXT,
    pnl_usd          NUMERIC(14,4),
    duration_s       NUMERIC(12,2),
    mt5_retcode      INT,
    broker_comment   TEXT,
    breaker_name     TEXT,
    breaker_state    TEXT,
    retry_attempt    SMALLINT,
    max_retries      SMALLINT,
    error_message    TEXT,
    error_type       TEXT,
    metadata         JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_oj_signal_id ON order_journal(signal_id) WHERE signal_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_oj_order_id  ON order_journal(order_id)  WHERE order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_oj_mt5_ticket ON order_journal(mt5_ticket) WHERE mt5_ticket IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_oj_symbol_ts ON order_journal(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_oj_event_ts  ON order_journal(event_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_oj_user_ts   ON order_journal(user_id, timestamp DESC);

ALTER TABLE order_journal ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='order_journal' AND policyname='journal_own') THEN
        CREATE POLICY "journal_own" ON order_journal FOR SELECT USING (user_id = auth.uid());
    END IF;
END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='order_journal' AND policyname='journal_insert') THEN
        CREATE POLICY "journal_insert" ON order_journal FOR INSERT WITH CHECK (true);
    END IF;
END $$;

-- HF-4: Orphan Position Registry
CREATE TABLE IF NOT EXISTS orphan_positions (
    ticket         BIGINT      PRIMARY KEY,
    symbol         TEXT        NOT NULL,
    direction      TEXT        NOT NULL,
    volume         NUMERIC(10,4),
    open_price     NUMERIC(18,6),
    profit         NUMERIC(14,4),
    status         TEXT        NOT NULL DEFAULT 'pending_review'
                               CHECK (status IN ('pending_review','reviewed','manually_closed','ignored')),
    review_note    TEXT,
    discovered_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at      TIMESTAMPTZ
);

-- HF-2: Correlation Snapshots
CREATE TABLE IF NOT EXISTS correlation_snapshots (
    id           BIGSERIAL   PRIMARY KEY,
    symbol_a     TEXT        NOT NULL,
    symbol_b     TEXT        NOT NULL,
    correlation  NUMERIC(8,6) NOT NULL,
    source       TEXT        NOT NULL DEFAULT 'rolling',
    window_bars  INT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_corr_pair_ts ON correlation_snapshots(symbol_a, symbol_b, created_at DESC);

COMMIT;
