-- Phase 36: Final Acceptance Extended
-- Migration: 20260629_045b_phase36_final_acceptance.sql

BEGIN;

-- Add review fields to acceptance_runs if not exists
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'acceptance_runs' AND column_name = 'reviewed_by'
    ) THEN
        ALTER TABLE acceptance_runs ADD COLUMN reviewed_by TEXT;
        ALTER TABLE acceptance_runs ADD COLUMN reviewed_at TIMESTAMPTZ;
        ALTER TABLE acceptance_runs ADD COLUMN sign_off_note TEXT;
    END IF;
END $$;

-- Deployment gate check function
CREATE OR REPLACE FUNCTION check_acceptance_gate(
    p_tenant_id TEXT DEFAULT 'system'
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_last_run  acceptance_runs%ROWTYPE;
    v_critical  INTEGER;
BEGIN
    SELECT * INTO v_last_run
    FROM acceptance_runs
    WHERE tenant_id = p_tenant_id AND status = 'passed'
    ORDER BY finished_at DESC LIMIT 1;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'gate', 'BLOCKED',
            'reason', 'No passing acceptance run found'
        );
    END IF;

    SELECT COUNT(*) INTO v_critical
    FROM acceptance_findings
    WHERE run_id = v_last_run.run_id
      AND severity = 'critical'
      AND resolved = FALSE;

    RETURN jsonb_build_object(
        'gate', CASE WHEN v_critical = 0 THEN 'OPEN' ELSE 'BLOCKED' END,
        'last_run_id', v_last_run.run_id,
        'unresolved_critical', v_critical,
        'passed_at', v_last_run.finished_at
    );
END;
$$;

COMMIT;
