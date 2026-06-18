-- Galaxy Vast AI Trading Platform
-- Phase 3: Deduplication Migration
-- Documents canonical sources and removes ambiguity

-- ============================================================
-- CANONICAL TABLE REGISTRY
-- ============================================================
-- These are the ONLY tables that should be used:
--   public.trades           -> canonical trade records
--   public.signals          -> canonical signal records
--   public.trade_memory     -> TradeMemory persistence (added in 004)
--   public.analytics_trades -> Analytics (added in 004)
--   self_learning_*         -> Self-learning (added in 004)

-- ============================================================
-- DUPLICATE ENUM RESOLUTION
-- ============================================================
-- TradeDirection: use backend.core.enums.TradeDirection ONLY
-- MarketSession:  use backend.core.enums.TradingSession ONLY
-- Both are now re-exported from backend.core.unified_types

-- ============================================================
-- ADD MISSING COLUMNS (idempotent)
-- ============================================================
ALTER TABLE IF EXISTS public.trades
    ADD COLUMN IF NOT EXISTS model_version    VARCHAR(50)  DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS vote_result      JSONB        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS agent_scores     JSONB        DEFAULT NULL;

ALTER TABLE IF EXISTS public.signals
    ADD COLUMN IF NOT EXISTS vote_result      JSONB        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS confidence_breakdown JSONB    DEFAULT NULL;

-- ============================================================
-- INDEX FOR MODEL VERSIONING
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_trades_model_version
    ON public.trades (model_version)
    WHERE model_version IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_slmr_symbol_version
    ON self_learning_model_registry (symbol, version);

CREATE INDEX IF NOT EXISTS idx_slmr_is_active
    ON self_learning_model_registry (is_active)
    WHERE is_active = true;
