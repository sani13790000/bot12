-- Phase 10: Security hardening migrations
-- Audit log table + RLS enforcement + security functions

-- ============================================================
-- 1. Audit log table
-- ============================================================
CREATE TABLE IF NOT EXISTS public.audit_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    user_id UUID,
    action TEXT NOT NULL,
    resource TEXT,
    resource_id TEXT,
    ip_address INET,
    request_id TEXT,
    status_code INT,
    duration_ms FLOAT,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON public.audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON public.audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON public.audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON public.audit_log(resource, resource_id);

-- ============================================================
-- 2. Security events table (failed logins, blocked requests)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.security_events (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    event_type TEXT NOT NULL, -- sql_injection, xss, path_traversal, brute_force, rate_limit
    severity TEXT NOT NULL DEFAULT 'medium', -- low, medium, high, critical
    ip_address INET,
    user_id UUID,
    path TEXT,
    detail TEXT,
    request_id TEXT,
    blocked BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_security_events_type ON public.security_events(event_type);
CREATE INDEX IF NOT EXISTS idx_security_events_ip ON public.security_events(ip_address);
CREATE INDEX IF NOT EXISTS idx_security_events_created ON public.security_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_severity ON public.security_events(severity);

-- ============================================================
-- 3. User license table
-- ============================================================
CREATE TABLE IF NOT EXISTS public.user_licenses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE,
    tier TEXT NOT NULL DEFAULT 'free', -- free, basic, pro, enterprise
    valid_from TIMESTAMPTZ DEFAULT NOW(),
    valid_until TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_user_licenses_user_id ON public.user_licenses(user_id);
CREATE INDEX IF NOT EXISTS idx_user_licenses_tier ON public.user_licenses(tier);
CREATE INDEX IF NOT EXISTS idx_user_licenses_active ON public.user_licenses(is_active) WHERE is_active = TRUE;

-- ============================================================
-- 4. RLS policies
-- ============================================================
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.security_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_licenses ENABLE ROW LEVEL SECURITY;

-- Audit log: only service role can insert/select
CREATE POLICY IF NOT EXISTS "audit_log_service_only" ON public.audit_log
    USING (auth.role() = 'service_role');

-- Security events: only service role
CREATE POLICY IF NOT EXISTS "security_events_service_only" ON public.security_events
    USING (auth.role() = 'service_role');

-- User licenses: user can read own, service can do all
CREATE POLICY IF NOT EXISTS "user_licenses_read_own" ON public.user_licenses
    FOR SELECT USING (
        auth.uid() = user_id OR auth.role() = 'service_role'
    );

CREATE POLICY IF NOT EXISTS "user_licenses_service_write" ON public.user_licenses
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- 5. Helper function: get user tier
-- ============================================================
CREATE OR REPLACE FUNCTION public.get_user_tier(p_user_id UUID)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_tier TEXT;
BEGIN
    SELECT tier INTO v_tier
    FROM public.user_licenses
    WHERE user_id = p_user_id
      AND is_active = TRUE
      AND (valid_until IS NULL OR valid_until > NOW())
    ORDER BY
        CASE tier
            WHEN 'enterprise' THEN 4
            WHEN 'pro' THEN 3
            WHEN 'basic' THEN 2
            ELSE 1
        END DESC
    LIMIT 1;

    RETURN COALESCE(v_tier, 'free');
END;
$$;

-- ============================================================
-- 6. Default free license for existing users
-- ============================================================
INSERT INTO public.user_licenses (user_id, tier)
SELECT id, 'free'
FROM auth.users
ON CONFLICT (user_id) DO NOTHING;

-- ============================================================
-- 7. Grant permissions
-- ============================================================
GRANT SELECT ON public.user_licenses TO authenticated;
GRANT ALL ON public.audit_log TO service_role;
GRANT ALL ON public.security_events TO service_role;
GRANT ALL ON public.user_licenses TO service_role;
GRANT EXECUTE ON FUNCTION public.get_user_tier TO authenticated, service_role;
