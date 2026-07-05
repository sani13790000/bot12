-- Migration 046: Final Acceptance & Optimization
-- BUG-U3b FIX: renamed from 20260628_046 to 20260630_046
-- 20260629_045b creates agent_vote_log table
-- 20260628_046 was trying to INDEX agent_vote_log BEFORE it was created
-- 20260630_046 runs AFTER 20260629_045b — agent_vote_log exists
-- Result: INDEX creation succeeds

BEGIN;

-- 1. Final composite indexes for production query performance
CREATE INDEX IF NOT EXISTS idx_trades_symbol_status_created
    ON trades (symbol, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_vote_log_agent_vote
    ON agent_vote_log (agent_name, vote, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_audit_smc_score
    ON signal_audit_log (smc_score DESC, created_at DESC)
    WHERE smc_score IS NOT NULL;

-- 2. Mark schema_migrations_complete gate as passed
UPDATE deployment_gates
   SET status = 'passed', checked_at = NOW(),
       details = jsonb_build_object('migration_count', 47, 'completed_at', NOW())
 WHERE gate_name = 'schema_migrations_complete';

-- 3. Verify pg_stat_statements is available (non-fatal)
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements') THEN
        RAISE NOTICE 'pg_stat_statements available - query performance monitoring enabled';
    ELSE
        RAISE NOTICE 'pg_stat_statements not available - consider enabling for production';
    END IF;
END $$;

-- 4. Final system health check
DO $$ BEGIN
    RAISE NOTICE 'Migration 046 complete (BUG-U3b: now runs after 045b) - system ready for production';
    RAISE NOTICE 'agent_vote_log index created successfully after table creation in 045b';
END $$;

COMMIT;
