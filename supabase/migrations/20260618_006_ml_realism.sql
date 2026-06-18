-- Phase 5: ML Realism — walk_forward_folds, drift tracking, model registry columns
-- Run: psql $SUPABASE_DB_URL -f supabase/migrations/20260618_006_ml_realism.sql

BEGIN;

-- 1. Extend self_learning_retrain_jobs with Phase 5 fields
ALTER TABLE self_learning_retrain_jobs
    ADD COLUMN IF NOT EXISTS avg_oos_accuracy   FLOAT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS avg_overfit_ratio  FLOAT DEFAULT 1,
    ADD COLUMN IF NOT EXISTS drift_score        FLOAT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS drift_status       TEXT  DEFAULT 'stable',
    ADD COLUMN IF NOT EXISTS walk_forward_folds JSONB DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS feature_importance JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS model_version      TEXT  DEFAULT '1.0',
    ADD COLUMN IF NOT EXISTS notes              TEXT  DEFAULT '';

-- 2. Extend self_learning_model_registry with OOS + overfit columns
ALTER TABLE self_learning_model_registry
    ADD COLUMN IF NOT EXISTS oos_accuracy    FLOAT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS overfit_ratio   FLOAT DEFAULT 1,
    ADD COLUMN IF NOT EXISTS drift_score     FLOAT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS is_active       BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS file_path       TEXT  DEFAULT '';

-- 3. model_drift_log — tracks every drift event
CREATE TABLE IF NOT EXISTS model_drift_log (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    drift_score     FLOAT NOT NULL,
    drift_status    TEXT NOT NULL,  -- stable / warning / drifted
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retrain_triggered BOOLEAN DEFAULT FALSE,
    notes           TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_drift_log_symbol     ON model_drift_log(symbol);
CREATE INDEX IF NOT EXISTS idx_drift_log_detected   ON model_drift_log(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_drift_log_status     ON model_drift_log(drift_status);

-- 4. walk_forward_results — per-fold OOS results
CREATE TABLE IF NOT EXISTS walk_forward_results (
    id              BIGSERIAL PRIMARY KEY,
    retrain_job_id  BIGINT REFERENCES self_learning_retrain_jobs(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    fold_index      INT NOT NULL,
    train_size      INT NOT NULL,
    test_size       INT NOT NULL,
    train_accuracy  FLOAT NOT NULL,
    test_accuracy   FLOAT NOT NULL,
    train_f1        FLOAT NOT NULL,
    test_f1         FLOAT NOT NULL,
    overfit_ratio   FLOAT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wf_results_symbol  ON walk_forward_results(symbol);
CREATE INDEX IF NOT EXISTS idx_wf_results_version ON walk_forward_results(model_version);

-- 5. feature_importance_log — tracks feature importance per training run
CREATE TABLE IF NOT EXISTS feature_importance_log (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    feature_name    TEXT NOT NULL,
    importance      FLOAT NOT NULL,
    trained_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feat_imp_symbol  ON feature_importance_log(symbol);
CREATE INDEX IF NOT EXISTS idx_feat_imp_version ON feature_importance_log(model_version);

COMMIT;
