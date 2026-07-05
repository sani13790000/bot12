-- Migration 025a: Phase T - Trading Services Tables
-- Renamed from 20260623_025_phase_t_services.sql to resolve prefix conflict
-- BUG-N2 FIX: 025 prefix was duplicated — this is now 025a (services tables)
-- Supabase CLI executes 025a before 025b (alphabetical order)
BEGIN;

-- 1. signal_audit_log: full audit trail of every signal processed
CREATE TABLE IF NOT EXISTS signal_audit_log (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol          TEXT        NOT NULL,
    direction       TEXT        NOT NULL CHECK (direction IN ('LONG','SHORT','NO_TRADE')),
    entry_price     FLOAT,
    sl_price        FLOAT,
    tp_price        FLOAT,
    rr_ratio        FLOAT,
    confidence      FLOAT       CHECK (confidence BETWEEN 0.0 AND 1.0),
    final_decision  TEXT        NOT NULL DEFAULT 'NO_TRADE',
    vote_summary    JSONB       DEFAULT '{}',
    context_snapshot JSONB      DEFAULT '{}',
    risk_blocked    BOOLEAN     NOT NULL DEFAULT FALSE,
    risk_reason     TEXT,
    executed        BOOLEAN     NOT NULL DEFAULT FALSE,
    mt5_ticket      BIGINT,
    session_name    TEXT,
    smc_bias        TEXT,
    ml_probability  FLOAT,
    pa_trend        TEXT,
    smc_score       FLOAT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_signal_audit_symbol    ON signal_audit_log (symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_audit_direction ON signal_audit_log (direction, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_audit_executed  ON signal_audit_log (executed, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_audit_created   ON signal_audit_log (created_at DESC);

-- 2. agent_vote_log: per-agent vote history for performance tracking
CREATE TABLE IF NOT EXISTS agent_vote_log (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    signal_id   UUID        REFERENCES signal_audit_log(id) ON DELETE CASCADE,
    agent_name  TEXT        NOT NULL,
    vote        TEXT        NOT NULL CHECK (vote IN ('BUY','SELL','NO_TRADE','ABSTAIN')),
    confidence  FLOAT       CHECK (confidence BETWEEN 0.0 AND 1.0),
    weight      FLOAT       NOT NULL DEFAULT 1.0,
    reasoning   TEXT,
    latency_ms  FLOAT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_vote_signal    ON agent_vote_log (signal_id);
CREATE INDEX IF NOT EXISTS idx_agent_vote_agent     ON agent_vote_log (agent_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_vote_created   ON agent_vote_log (created_at DESC);

-- 3. performance_snapshots: periodic system performance KPIs
CREATE TABLE IF NOT EXISTS performance_snapshots (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    period_start    TIMESTAMPTZ NOT NULL,
    period_end      TIMESTAMPTZ NOT NULL,
    total_signals   INT         NOT NULL DEFAULT 0,
    executed_trades INT         NOT NULL DEFAULT 0,
    win_count       INT         NOT NULL DEFAULT 0,
    loss_count      INT         NOT NULL DEFAULT 0,
    win_rate        FLOAT,
    total_pnl       FLOAT,
    max_drawdown    FLOAT,
    sharpe_ratio    FLOAT,
    avg_rr_ratio    FLOAT,
    agent_stats     JSONB       DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_perf_snapshot_period ON performance_snapshots (period_start DESC);

-- 4. RLS
ALTER TABLE signal_audit_log      ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_vote_log        ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_snapshots ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    DROP POLICY IF EXISTS svc_signal_audit ON signal_audit_log;
    CREATE POLICY svc_signal_audit ON signal_audit_log FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    DROP POLICY IF EXISTS svc_agent_vote ON agent_vote_log;
    CREATE POLICY svc_agent_vote ON agent_vote_log FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    DROP POLICY IF EXISTS svc_perf_snapshot ON performance_snapshots;
    CREATE POLICY svc_perf_snapshot ON performance_snapshots FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
  END IF;
END $$;

COMMIT;
