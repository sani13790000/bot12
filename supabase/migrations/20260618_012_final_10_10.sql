-- ============================================================
-- Migration 012: Final fixes for 10/10 production readiness
-- ============================================================

-- 1. Ensure all enum types exist (idempotent)
DO $$ BEGIN
    CREATE TYPE IF NOT EXISTS order_state AS ENUM (
        'PENDING', 'SUBMITTED', 'FILLED', 'REJECTED',
        'CANCELLED', 'EXPIRED', 'CLOSING', 'CLOSED'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 2. execution_orders: add missing columns if not present
ALTER TABLE IF EXISTS public.execution_orders
    ADD COLUMN IF NOT EXISTS mt5_ticket    BIGINT,
    ADD COLUMN IF NOT EXISTS mt5_deal      BIGINT,
    ADD COLUMN IF NOT EXISTS filled_price  NUMERIC(20,5),
    ADD COLUMN IF NOT EXISTS filled_volume NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS timeout_at    TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS recovery_strategy TEXT DEFAULT 'none';

-- 3. model_drift_log: ensure table exists
CREATE TABLE IF NOT EXISTS public.model_drift_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_type      TEXT NOT NULL,
    drift_status    TEXT NOT NULL,
    drift_score     NUMERIC(10,6) DEFAULT 0.0,
    ph_statistic    NUMERIC(10,6) DEFAULT 0.0,
    triggered_retrain BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 4. walk_forward_results: ensure table exists
CREATE TABLE IF NOT EXISTS public.walk_forward_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL,
    fold_index      INTEGER NOT NULL,
    train_size      INTEGER NOT NULL,
    test_size       INTEGER NOT NULL,
    train_accuracy  NUMERIC(10,6) DEFAULT 0.0,
    test_accuracy   NUMERIC(10,6) DEFAULT 0.0,
    train_f1        NUMERIC(10,6) DEFAULT 0.0,
    test_f1         NUMERIC(10,6) DEFAULT 0.0,
    overfit_ratio   NUMERIC(10,6) DEFAULT 1.0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 5. feature_importance_log: ensure table exists
CREATE TABLE IF NOT EXISTS public.feature_importance_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version   TEXT NOT NULL,
    feature_name    TEXT NOT NULL,
    importance      NUMERIC(10,6) DEFAULT 0.0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Performance indexes
CREATE INDEX IF NOT EXISTS idx_model_drift_created
    ON public.model_drift_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wf_results_run
    ON public.walk_forward_results (run_id);
CREATE INDEX IF NOT EXISTS idx_feat_importance_version
    ON public.feature_importance_log (model_version, created_at DESC);

-- 7. RLS for new tables
ALTER TABLE public.model_drift_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.walk_forward_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.feature_importance_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "service_role_model_drift"
    ON public.model_drift_log FOR ALL
    TO service_role USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY IF NOT EXISTS "service_role_walk_forward"
    ON public.walk_forward_results FOR ALL
    TO service_role USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY IF NOT EXISTS "service_role_feat_importance"
    ON public.feature_importance_log FOR ALL
    TO service_role USING (TRUE) WITH CHECK (TRUE);

-- Done
SELECT 'Migration 012 complete: 10/10 production readiness' AS status;
