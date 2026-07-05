-- Migration 025b: Phase U Hardening
-- Renamed from 20260623_025_phase_u_hardening.sql to resolve prefix conflict
-- BUG-J6 FIX: 025 prefix was duplicated — this is now 025b (hardening)
-- Executes AFTER 025a

-- Security hardening additions
ALTER TABLE IF EXISTS public.service_health
    ADD COLUMN IF NOT EXISTS error_count  INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS updated_at   TIMESTAMPTZ DEFAULT NOW();

-- RLS
ALTER TABLE IF EXISTS public.service_health ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS service_health_admin_only
    ON public.service_health
    FOR ALL
    USING (auth.role() = 'service_role');
