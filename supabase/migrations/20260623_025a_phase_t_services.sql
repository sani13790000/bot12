-- Migration 025a: Phase T Services (canonical 025)
-- Renamed from 20260623_025_phase_t_services.sql to resolve prefix conflict
-- BUG-J6 FIX: 025 prefix was duplicated — this is now 025a
-- Supabase CLI will execute this BEFORE 025b

-- Create services-related tables
CREATE TABLE IF NOT EXISTS public.service_health (
    id           BIGSERIAL PRIMARY KEY,
    service_name TEXT        NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'unknown',
    last_check   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    details      JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_service_health_name
    ON public.service_health(service_name);
CREATE INDEX IF NOT EXISTS idx_service_health_last_check
    ON public.service_health(last_check DESC);
