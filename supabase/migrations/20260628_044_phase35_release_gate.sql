-- Migration 044: Release Gate Check
-- BUG-N3 FIX: was placeholder SELECT 1 — now creates deployment_gates table
BEGIN;

-- deployment_gates: tracks release milestones and go/no-go status
CREATE TABLE IF NOT EXISTS deployment_gates (
    id           UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    gate_name    TEXT        NOT NULL UNIQUE,
    status       TEXT        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','passed','failed','skipped')),
    checked_at   TIMESTAMPTZ,
    details      JSONB       DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_deployment_gates_status ON deployment_gates (status, created_at DESC);

ALTER TABLE deployment_gates ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    DROP POLICY IF EXISTS svc_deployment_gates ON deployment_gates;
    CREATE POLICY svc_deployment_gates ON deployment_gates FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
  END IF;
END $$;

-- Insert canonical gates
INSERT INTO deployment_gates (gate_name, status) VALUES
    ('schema_migrations_complete', 'passed'),
    ('risk_engine_live',           'pending'),
    ('ml_model_trained',           'pending'),
    ('demo_account_validated',     'pending'),
    ('live_deployment_approved',   'pending')
ON CONFLICT (gate_name) DO NOTHING;

-- Helper: check_release_gate
CREATE OR REPLACE FUNCTION check_release_gate(p_gate TEXT)
RETURNS TEXT LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE v_status TEXT;
BEGIN
    SELECT status INTO v_status FROM deployment_gates WHERE gate_name = p_gate;
    RETURN COALESCE(v_status, 'unknown');
END;
$$;

COMMIT;
