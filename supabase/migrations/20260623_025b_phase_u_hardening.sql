-- Migration 025b: Phase U - Security Hardening Policies
-- Renamed from 20260623_025_phase_u_hardening.sql to resolve prefix conflict
-- BUG-N2 FIX: 025 prefix was duplicated — this is now 025b (hardening)
-- Supabase CLI executes this AFTER 025a (alphabetical order)
BEGIN;

-- 1. Add missing composite indexes for hot query paths
CREATE INDEX IF NOT EXISTS idx_trades_symbol_created
    ON trades (symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_status_created
    ON trades (status, created_at DESC) WHERE status = 'OPEN';
CREATE INDEX IF NOT EXISTS idx_signal_audit_ml_prob
    ON signal_audit_log (ml_probability DESC, created_at DESC)
    WHERE ml_probability IS NOT NULL;

-- 2. Add CHECK constraints to existing tables (idempotent)
DO $$ BEGIN
    BEGIN
        ALTER TABLE trades ADD CONSTRAINT chk_trades_rr_positive
            CHECK (rr_ratio IS NULL OR rr_ratio > 0);
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE trades ADD CONSTRAINT chk_trades_confidence_range
            CHECK (confidence IS NULL OR (confidence BETWEEN 0.0 AND 1.0));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
END $$;

-- 3. Function: get_system_health_summary
CREATE OR REPLACE FUNCTION get_system_health_summary()
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'total_trades_24h',    (SELECT COUNT(*) FROM trades WHERE created_at > NOW() - INTERVAL '24 hours'),
        'open_positions',      (SELECT COUNT(*) FROM trades WHERE status = 'OPEN'),
        'anomalies_24h',       (SELECT COUNT(*) FROM security_ai_analysis WHERE is_anomaly = TRUE AND created_at > NOW() - INTERVAL '24 hours'),
        'blocked_ips_active',  (SELECT COUNT(*) FROM security_blocked_ips WHERE unblocked_at IS NULL),
        'last_signal_at',      (SELECT MAX(created_at) FROM signal_audit_log),
        'generated_at',        NOW()
    ) INTO result;
    RETURN result;
END;
$$;

-- 4. Audit trigger for trades table
CREATE OR REPLACE FUNCTION trades_audit_trigger_fn()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO signal_audit_log (symbol, direction, executed, mt5_ticket, created_at)
        VALUES (NEW.symbol, COALESCE(NEW.direction, 'NO_TRADE'), TRUE, NEW.mt5_ticket, NOW())
        ON CONFLICT DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trades_audit_trigger'
    ) THEN
        CREATE TRIGGER trades_audit_trigger
        AFTER UPDATE ON trades
        FOR EACH ROW EXECUTE FUNCTION trades_audit_trigger_fn();
    END IF;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

COMMIT;
