-- Phase 6: Backtest Validity Tables
-- Walk-Forward results, Monte Carlo runs, Optimization results, Backtest results

-- ============================================================
-- backtest_results: stores full backtest run results
-- ============================================================
CREATE TABLE IF NOT EXISTS backtest_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    start_date      TEXT,
    end_date        TEXT,
    total_trades    INT  DEFAULT 0,
    win_rate        FLOAT DEFAULT 0,
    profit_factor   FLOAT DEFAULT 0,
    sharpe_ratio    FLOAT DEFAULT 0,
    sortino_ratio   FLOAT DEFAULT 0,
    calmar_ratio    FLOAT DEFAULT 0,
    max_drawdown_pct FLOAT DEFAULT 0,
    total_pnl_usd   FLOAT DEFAULT 0,
    final_balance   FLOAT DEFAULT 0,
    total_return_pct FLOAT DEFAULT 0,
    expectancy      FLOAT DEFAULT 0,
    config          JSONB DEFAULT '{}',
    monthly_returns JSONB DEFAULT '{}',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_results_user    ON backtest_results(user_id);
CREATE INDEX IF NOT EXISTS idx_backtest_results_symbol  ON backtest_results(symbol);
CREATE INDEX IF NOT EXISTS idx_backtest_results_created ON backtest_results(created_at DESC);

-- ============================================================
-- walk_forward_windows: one row per IS/OOS window
-- ============================================================
CREATE TABLE IF NOT EXISTS walk_forward_windows (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL,
    user_id         UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    window_id       INT  NOT NULL,
    is_start        TIMESTAMPTZ,
    is_end          TIMESTAMPTZ,
    oos_start       TIMESTAMPTZ,
    oos_end         TIMESTAMPTZ,
    passed          BOOLEAN DEFAULT FALSE,
    fitness_is      FLOAT DEFAULT 0,
    fitness_oos     FLOAT DEFAULT 0,
    efficiency      FLOAT DEFAULT 0,
    best_params     JSONB DEFAULT '{}',
    is_metrics      JSONB DEFAULT '{}',
    oos_metrics     JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wf_windows_run    ON walk_forward_windows(run_id);
CREATE INDEX IF NOT EXISTS idx_wf_windows_user   ON walk_forward_windows(user_id);

-- ============================================================
-- walk_forward_runs: summary per walk-forward analysis run
-- ============================================================
CREATE TABLE IF NOT EXISTS walk_forward_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    symbols             TEXT[],
    total_windows       INT   DEFAULT 0,
    passed_windows      INT   DEFAULT 0,
    pass_rate           FLOAT DEFAULT 0,
    avg_efficiency      FLOAT DEFAULT 0,
    consistency_score   FLOAT DEFAULT 0,
    oos_combined_pnl    FLOAT DEFAULT 0,
    oos_combined_wr     FLOAT DEFAULT 0,
    recommendation      TEXT,
    config              JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wf_runs_user    ON walk_forward_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_wf_runs_created ON walk_forward_runs(created_at DESC);

-- ============================================================
-- monte_carlo_runs: Monte Carlo simulation results
-- ============================================================
CREATE TABLE IF NOT EXISTS monte_carlo_runs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    backtest_result_id      UUID REFERENCES backtest_results(id) ON DELETE SET NULL,
    n_simulations           INT   DEFAULT 1000,
    initial_balance         FLOAT DEFAULT 10000,
    mean_final_balance      FLOAT DEFAULT 0,
    median_final_balance    FLOAT DEFAULT 0,
    std_final_balance       FLOAT DEFAULT 0,
    final_balance_p5        FLOAT DEFAULT 0,
    final_balance_p25       FLOAT DEFAULT 0,
    final_balance_p75       FLOAT DEFAULT 0,
    final_balance_p95       FLOAT DEFAULT 0,
    expected_max_drawdown   FLOAT DEFAULT 0,
    worst_max_drawdown      FLOAT DEFAULT 0,
    kelly_fraction          FLOAT DEFAULT 0,
    optimal_risk_pct        FLOAT DEFAULT 0,
    var_by_level            JSONB DEFAULT '{}',
    cvar_by_level           JSONB DEFAULT '{}',
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mc_runs_user    ON monte_carlo_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_mc_runs_bt      ON monte_carlo_runs(backtest_result_id);

-- ============================================================
-- optimization_results: parameter optimizer runs
-- ============================================================
CREATE TABLE IF NOT EXISTS optimization_results (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    best_params         JSONB DEFAULT '{}',
    best_train_metric   FLOAT DEFAULT 0,
    best_test_metric    FLOAT DEFAULT 0,
    robustness_score    FLOAT DEFAULT 0,
    is_robust           BOOLEAN DEFAULT FALSE,
    overfit_warning     BOOLEAN DEFAULT FALSE,
    total_iterations    INT   DEFAULT 0,
    recommendation      TEXT,
    top_10_iterations   JSONB DEFAULT '[]',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opt_results_user    ON optimization_results(user_id);
CREATE INDEX IF NOT EXISTS idx_opt_results_created ON optimization_results(created_at DESC);
