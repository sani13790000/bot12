-- ═══════════════════════════════════════════════════════════════════════════
-- Galaxy Vast AI Trading Platform
-- Self-Learning Module — PostgreSQL Schema
-- نسخه: 1.0.0
-- ═══════════════════════════════════════════════════════════════════════════

-- ─── جدول معاملات ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS self_learning_trades (
    trade_id           UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    mt5_ticket         BIGINT        NOT NULL DEFAULT 0,
    symbol             VARCHAR(20)   NOT NULL,
    direction          VARCHAR(4)    NOT NULL CHECK (direction IN ('BUY','SELL')),
    result             VARCHAR(4)    NOT NULL CHECK (result IN ('WIN','LOSS','BE')),
    entry_price        NUMERIC(20,8) NOT NULL,
    exit_price         NUMERIC(20,8) NOT NULL,
    stop_loss          NUMERIC(20,8) NOT NULL DEFAULT 0,
    take_profit        NUMERIC(20,8) NOT NULL DEFAULT 0,
    lot_size           NUMERIC(10,4) NOT NULL,
    profit_loss        NUMERIC(12,4) NOT NULL,
    profit_pips        NUMERIC(10,2) NOT NULL DEFAULT 0,
    risk_reward_actual NUMERIC(8,4)  NOT NULL DEFAULT 0,
    entry_time         TIMESTAMPTZ   NOT NULL,
    exit_time          TIMESTAMPTZ   NOT NULL,
    duration_minutes   INTEGER       NOT NULL DEFAULT 0,
    confidence_score   NUMERIC(5,2)  NOT NULL DEFAULT 0,
    decision_score     NUMERIC(5,2)  NOT NULL DEFAULT 0,
    smc_features       JSONB         NOT NULL DEFAULT '{}',
    market_conditions  JSONB         NOT NULL DEFAULT '{}',
    ml_features        JSONB         NOT NULL DEFAULT '{}',
    model_version      VARCHAR(50)   NOT NULL DEFAULT 'unknown',
    is_rule_violation  BOOLEAN       NOT NULL DEFAULT FALSE,
    violation_reason   TEXT          NOT NULL DEFAULT '',
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_slt_symbol ON self_learning_trades (symbol);
CREATE INDEX IF NOT EXISTS idx_slt_result ON self_learning_trades (result);
CREATE INDEX IF NOT EXISTS idx_slt_entry  ON self_learning_trades (entry_time);
CREATE INDEX IF NOT EXISTS idx_slt_valid  ON self_learning_trades (symbol, is_rule_violation);
CREATE INDEX IF NOT EXISTS idx_slt_symbol_result ON self_learning_trades (symbol, result);

-- ─── جدول registry مدل‌ها ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS self_learning_model_registry (
    record_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id           VARCHAR(100) NOT NULL UNIQUE,
    symbol             VARCHAR(20)  NOT NULL,
    version            VARCHAR(50)  NOT NULL,
    registered_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    train_auc          NUMERIC(6,4) NOT NULL DEFAULT 0,
    val_auc            NUMERIC(6,4) NOT NULL DEFAULT 0,
    test_auc           NUMERIC(6,4) NOT NULL DEFAULT 0,
    cv_auc_mean        NUMERIC(6,4) NOT NULL DEFAULT 0,
    cv_auc_std         NUMERIC(6,4) NOT NULL DEFAULT 0,
    accuracy           NUMERIC(6,4) NOT NULL DEFAULT 0,
    precision_score    NUMERIC(6,4) NOT NULL DEFAULT 0,
    recall_score       NUMERIC(6,4) NOT NULL DEFAULT 0,
    f1_score           NUMERIC(6,4) NOT NULL DEFAULT 0,
    total_samples      INTEGER      NOT NULL DEFAULT 0,
    win_rate           NUMERIC(6,4) NOT NULL DEFAULT 0,
    is_promoted        BOOLEAN      NOT NULL DEFAULT FALSE,
    is_active          BOOLEAN      NOT NULL DEFAULT FALSE,
    model_path         TEXT         NOT NULL DEFAULT '',
    scaler_path        TEXT         NOT NULL DEFAULT '',
    feature_names      JSONB        NOT NULL DEFAULT '[]',
    feature_importance JSONB        NOT NULL DEFAULT '{}',
    metadata           JSONB        NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_slmr_symbol   ON self_learning_model_registry (symbol);
CREATE INDEX IF NOT EXISTS idx_slmr_active   ON self_learning_model_registry (symbol, is_active);
CREATE INDEX IF NOT EXISTS idx_slmr_date     ON self_learning_model_registry (registered_at DESC);

-- ─── جدول چرخه‌های بازآموزی ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS self_learning_retrain_jobs (
    job_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol           VARCHAR(20)  NOT NULL,
    triggered_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at     TIMESTAMPTZ,
    status           VARCHAR(20)  NOT NULL DEFAULT 'IDLE',
    reason           TEXT         NOT NULL DEFAULT '',
    old_model_id     VARCHAR(100) NOT NULL DEFAULT '',
    new_model_id     VARCHAR(100) NOT NULL DEFAULT '',
    old_auc          NUMERIC(6,4) NOT NULL DEFAULT 0,
    new_auc          NUMERIC(6,4) NOT NULL DEFAULT 0,
    auc_delta        NUMERIC(6,4) NOT NULL DEFAULT 0,
    was_promoted     BOOLEAN      NOT NULL DEFAULT FALSE,
    was_rolled_back  BOOLEAN      NOT NULL DEFAULT FALSE,
    error_message    TEXT         NOT NULL DEFAULT '',
    training_samples INTEGER      NOT NULL DEFAULT 0,
    metadata         JSONB        NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_slrj_symbol ON self_learning_retrain_jobs (symbol);
CREATE INDEX IF NOT EXISTS idx_slrj_status ON self_learning_retrain_jobs (status);
CREATE INDEX IF NOT EXISTS idx_slrj_date   ON self_learning_retrain_jobs (triggered_at DESC);

-- ─── View: خلاصه عملکرد هر نماد ───────────────────────────────────────────
CREATE OR REPLACE VIEW v_symbol_performance AS
SELECT
    t.symbol,
    COUNT(*)                                        AS total_trades,
    COUNT(*) FILTER (WHERE t.result = 'WIN')        AS wins,
    COUNT(*) FILTER (WHERE t.result = 'LOSS')       AS losses,
    ROUND(
        COUNT(*) FILTER (WHERE t.result = 'WIN')::numeric
        / NULLIF(COUNT(*), 0), 4
    )                                               AS win_rate,
    ROUND(AVG(t.profit_pips)::numeric, 2)           AS avg_pips,
    ROUND(AVG(t.confidence_score)::numeric, 2)      AS avg_confidence,
    m.test_auc                                      AS active_model_auc,
    m.version                                       AS active_model_version
FROM  self_learning_trades     t
LEFT  JOIN self_learning_model_registry m
      ON m.symbol = t.symbol AND m.is_active = TRUE
WHERE t.is_rule_violation = FALSE
GROUP BY t.symbol, m.test_auc, m.version;
