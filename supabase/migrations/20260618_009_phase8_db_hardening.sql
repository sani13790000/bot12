-- ============================================================
-- Phase 8 — Database Hardening
-- فاز 8: index‌های ترکیبی، بهینه‌سازی query‌ها، RLS hardening
-- ============================================================

-- ============================================================
-- SECTION 1: Composite Indexes (missing from earlier migrations)
-- ============================================================

-- trades: composite index for dashboard queries
CREATE INDEX IF NOT EXISTS idx_trades_user_status_opened
    ON public.trades(user_id, status, opened_at DESC);

-- trades: composite for P&L queries
CREATE INDEX IF NOT EXISTS idx_trades_user_closed_profit
    ON public.trades(user_id, closed_at DESC)
    WHERE status = 'closed';

-- trades: symbol + direction for strategy analysis
CREATE INDEX IF NOT EXISTS idx_trades_symbol_direction
    ON public.trades(symbol, direction, opened_at DESC);

-- signals: composite for active signal lookup
CREATE INDEX IF NOT EXISTS idx_signals_user_status_generated
    ON public.signals(user_id, status, generated_at DESC);

-- signals: score-based filtering
CREATE INDEX IF NOT EXISTS idx_signals_score_status
    ON public.signals(total_score DESC, status)
    WHERE status IN ('generated', 'sent');

-- trade_memory: symbol + direction for ML features
CREATE INDEX IF NOT EXISTS idx_trade_memory_symbol_direction
    ON public.trade_memory(symbol, direction)
    WHERE outcome IS NOT NULL;

-- trade_memory: recent trades per symbol
CREATE INDEX IF NOT EXISTS idx_trade_memory_symbol_exit_time
    ON public.trade_memory(symbol, exit_time DESC);

-- execution_orders: status + created_at for reconciliation
CREATE INDEX IF NOT EXISTS idx_execution_orders_status_created
    ON public.execution_orders(status, created_at DESC);

-- execution_orders: signal_id lookup
CREATE INDEX IF NOT EXISTS idx_execution_orders_signal_id
    ON public.execution_orders(signal_id);

-- ============================================================
-- SECTION 2: Partial Indexes (high-selectivity)
-- ============================================================

-- Only open trades (most queried)
CREATE INDEX IF NOT EXISTS idx_trades_open_only
    ON public.trades(user_id, opened_at DESC)
    WHERE status = 'open';

-- Only active signals
CREATE INDEX IF NOT EXISTS idx_signals_active_only
    ON public.signals(user_id, generated_at DESC)
    WHERE status IN ('generated', 'sent');

-- ============================================================
-- SECTION 3: Slow query view
-- ============================================================

CREATE OR REPLACE VIEW public.vw_recent_signals_summary AS
SELECT
    s.user_id,
    s.symbol,
    s.direction,
    s.total_score,
    s.status,
    s.generated_at,
    t.entry_price,
    t.profit_money,
    t.status AS trade_status
FROM public.signals s
LEFT JOIN public.trades t ON t.signal_id = s.id
WHERE s.generated_at > NOW() - INTERVAL '7 days'
ORDER BY s.generated_at DESC;

CREATE OR REPLACE VIEW public.vw_user_trade_summary AS
SELECT
    user_id,
    COUNT(*) FILTER (WHERE status = 'open') AS open_trades,
    COUNT(*) FILTER (WHERE status = 'closed') AS closed_trades,
    COALESCE(SUM(profit_money) FILTER (WHERE status = 'closed'), 0) AS total_pnl,
    COALESCE(AVG(profit_money) FILTER (WHERE status = 'closed' AND profit_money > 0), 0) AS avg_win,
    COALESCE(AVG(ABS(profit_money)) FILTER (WHERE status = 'closed' AND profit_money < 0), 0) AS avg_loss
FROM public.trades
GROUP BY user_id;

-- ============================================================
-- SECTION 4: RLS hardening
-- ============================================================

-- trade_memory: service role only (no user access)
ALTER TABLE public.trade_memory ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_only_trade_memory" ON public.trade_memory;
CREATE POLICY "service_only_trade_memory" ON public.trade_memory
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- execution_orders: service role only
ALTER TABLE public.execution_orders ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_only_execution_orders" ON public.execution_orders;
CREATE POLICY "service_only_execution_orders" ON public.execution_orders
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- analytics_trades: service role only
ALTER TABLE public.analytics_trades ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_only_analytics_trades" ON public.analytics_trades;
CREATE POLICY "service_only_analytics_trades" ON public.analytics_trades
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ============================================================
-- SECTION 5: Stats function (replaces Python-side calculation)
-- ============================================================

CREATE OR REPLACE FUNCTION public.get_user_trade_stats(
    p_user_id UUID,
    p_days INTEGER DEFAULT 30
) RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'total_trades', COUNT(*),
        'winning_trades', COUNT(*) FILTER (WHERE profit_money > 0),
        'losing_trades', COUNT(*) FILTER (WHERE profit_money < 0),
        'win_rate', CASE WHEN COUNT(*) > 0
            THEN ROUND((COUNT(*) FILTER (WHERE profit_money > 0))::DECIMAL / COUNT(*) * 100, 2)
            ELSE 0 END,
        'total_pnl', COALESCE(SUM(profit_money), 0),
        'avg_win', COALESCE(AVG(profit_money) FILTER (WHERE profit_money > 0), 0),
        'avg_loss', COALESCE(AVG(profit_money) FILTER (WHERE profit_money < 0), 0),
        'profit_factor', CASE
            WHEN COALESCE(SUM(ABS(profit_money)) FILTER (WHERE profit_money < 0), 0) > 0
            THEN ROUND(
                COALESCE(SUM(profit_money) FILTER (WHERE profit_money > 0), 0) /
                COALESCE(SUM(ABS(profit_money)) FILTER (WHERE profit_money < 0), 1), 2
            )
            ELSE 0 END,
        'max_drawdown', 0,
        'period_days', p_days
    ) INTO v_result
    FROM public.trades
    WHERE user_id = p_user_id
      AND status = 'closed'
      AND closed_at > NOW() - (p_days || ' days')::INTERVAL;

    RETURN COALESCE(v_result, '{}'::JSONB);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;

-- ============================================================
-- SECTION 6: VACUUM ANALYZE hints
-- ============================================================
-- Run after migration:
-- VACUUM ANALYZE public.trades;
-- VACUUM ANALYZE public.signals;
-- VACUUM ANALYZE public.trade_memory;
-- VACUUM ANALYZE public.execution_orders;
