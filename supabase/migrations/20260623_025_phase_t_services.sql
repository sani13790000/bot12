-- Migration 025 — Phase T Services
-- Canonical version (was orphaned at repo root as migration_025.sql)
-- Supabase CLI only reads from supabase/migrations/ — root file was ignored

-- Phase T: Trading Services Tables
CREATE TABLE IF NOT EXISTS public.trading_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL', 'NO_TRADE')),
    confidence      NUMERIC(5,2) DEFAULT 0,
    entry_price     NUMERIC(20,8),
    sl_price        NUMERIC(20,8),
    tp_price        NUMERIC(20,8),
    rr_ratio        NUMERIC(6,2),
    vote_result     JSONB,
    risk_result     JSONB,
    executed        BOOLEAN DEFAULT FALSE,
    ticket          BIGINT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trading_signals_symbol
    ON public.trading_signals (symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_trading_signals_executed
    ON public.trading_signals (executed, created_at DESC);

-- Phase T: Service Health Log
CREATE TABLE IF NOT EXISTS public.service_health_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service     TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('ok', 'warn', 'fail')),
    message     TEXT,
    latency_ms  INTEGER,
    checked_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_service_health_log_service
    ON public.service_health_log (service, checked_at DESC);

-- Cleanup note: root-level migration_025.sql is superseded by this file
-- Run: git rm migration_025.sql  (if not already removed)
