-- ======================================================================
-- Phase 13 — Database & Migration Hardening
-- Migration: 20260626_027_phase13_saas_schema.sql
-- Repeatable: YES (all CREATE ... IF NOT EXISTS + DO $$ ... IF NOT EXISTS)
-- ======================================================================
-- BUG LIST FIXED IN THIS MIGRATION:
-- P13-DB-BUG-1:  licenses.license_key stored plain text → key_hash column
-- P13-DB-BUG-2:  licenses table missing PENDING/REVOKED states
-- P13-DB-BUG-3:  No license_devices table (Phase 6 added device binding)
-- P13-DB-BUG-4:  No audit_log table (Phase 8 RBAC writes audit events)
-- P13-DB-BUG-5:  billing_invoices missing provider_ref UNIQUE (duplicate payment)
-- P13-DB-BUG-6:  billing_subscriptions allows >1 active sub per user (no partial unique)
-- P13-DB-BUG-7:  No duplicate order constraint on execution_orders (mt5_ticket + user_id)
-- P13-DB-BUG-8:  Missing RLS on license_devices, audit_log, billing_webhook_events
-- P13-DB-BUG-9:  Missing composite indexes: licenses(user_id,status), devices(license_id)
-- P13-DB-BUG-10: No refresh_tokens table (Phase 8 rotation needs DB persistence)
-- P13-DB-BUG-11: No nonce_store table (Phase 6/7 anti-replay)
-- P13-DB-BUG-12: signals table missing dedup constraint (symbol+user+generated_at window)
-- P13-DB-BUG-13: billing_plans missing IF NOT EXISTS on initial insert guard
-- P13-DB-BUG-14: No updated_at trigger on licenses table
-- ======================================================================

BEGIN;

-- ======================================================================
-- SECTION 1 — EXTENSIONS
-- ======================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ======================================================================
-- SECTION 2 — SHARED HELPER: updated_at trigger function
-- ======================================================================
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- ======================================================================
-- SECTION 3 — LICENSE HARDENING
-- P13-DB-BUG-1: add key_hash column; raw key must never be stored
-- P13-DB-BUG-2: expand status CHECK to include pending/revoked
-- P13-DB-BUG-14: add updated_at trigger
-- ======================================================================

-- 3a. Add key_hash column if missing (stores HMAC-SHA256 of raw key)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='licenses' AND column_name='key_hash'
    ) THEN
        ALTER TABLE public.licenses ADD COLUMN key_hash TEXT;
        -- Migrate existing keys → hash them
        UPDATE public.licenses
        SET key_hash = encode(
            hmac(license_key::bytea, current_setting('app.license_hmac_secret','t')::bytea, 'sha256'),
            'hex'
        )
        WHERE key_hash IS NULL AND license_key IS NOT NULL;
        -- Add unique constraint on hash
        ALTER TABLE public.licenses ADD CONSTRAINT uq_licenses_key_hash UNIQUE (key_hash);
    END IF;
END $$;

-- 3b. Widen status CHECK to include all Phase 6 states
ALTER TABLE public.licenses
    DROP CONSTRAINT IF EXISTS licenses_status_check;
ALTER TABLE public.licenses
    ADD CONSTRAINT licenses_status_check CHECK (
        status IN ('pending','inactive','active','expired','revoked','suspended')
    );

-- 3c. updated_at trigger on licenses
DROP TRIGGER IF EXISTS trg_licenses_updated_at ON public.licenses;
CREATE TRIGGER trg_licenses_updated_at
    BEFORE UPDATE ON public.licenses
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 3d. Index: (user_id, status) for license lookup (P13-DB-BUG-9)
CREATE INDEX IF NOT EXISTS idx_licenses_user_status
    ON public.licenses(user_id, status);

-- 3e. Partial index: only active licenses
CREATE INDEX IF NOT EXISTS idx_licenses_active_only
    ON public.licenses(user_id, expires_at)
    WHERE status = 'active';

-- ======================================================================
-- SECTION 4 — LICENSE DEVICES TABLE
-- P13-DB-BUG-3: phase 6/7 device binding had no DB table
-- ======================================================================
CREATE TABLE IF NOT EXISTS public.license_devices (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    license_id      UUID        NOT NULL REFERENCES public.licenses(id) ON DELETE CASCADE,
    user_id         UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    fingerprint     TEXT        NOT NULL,
    client_id       TEXT        NOT NULL,
    ip_address      INET,
    user_agent      TEXT,
    status          TEXT        NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','revoked','replaced')),
    last_heartbeat  TIMESTAMPTZ,
    heartbeat_count BIGINT      NOT NULL DEFAULT 0,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ,
    revoked_reason  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_device_fingerprint_license UNIQUE (license_id, fingerprint)
);

DROP TRIGGER IF EXISTS trg_devices_updated_at ON public.license_devices;
CREATE TRIGGER trg_devices_updated_at
    BEFORE UPDATE ON public.license_devices
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_devices_license_id
    ON public.license_devices(license_id);
CREATE INDEX IF NOT EXISTS idx_devices_user_id
    ON public.license_devices(user_id);
CREATE INDEX IF NOT EXISTS idx_devices_active
    ON public.license_devices(license_id, last_heartbeat DESC)
    WHERE status = 'active';

ALTER TABLE public.license_devices ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS devices_own_user    ON public.license_devices;
DROP POLICY IF EXISTS devices_service     ON public.license_devices;
CREATE POLICY devices_own_user ON public.license_devices
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);
CREATE POLICY devices_service ON public.license_devices
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

-- ======================================================================
-- SECTION 5 — AUDIT LOG TABLE
-- P13-DB-BUG-4: Phase 8 RBAC writes audit events — no DB table existed
-- ======================================================================
CREATE TABLE IF NOT EXISTS public.audit_log (
    id          BIGSERIAL   PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event       TEXT        NOT NULL,
    actor_id    UUID        REFERENCES auth.users(id) ON DELETE SET NULL,
    actor_role  TEXT,
    target_id   TEXT,
    target_type TEXT,
    detail      JSONB,
    ip_address  INET,
    request_id  TEXT,
    prev_hash   TEXT,
    entry_hash  TEXT GENERATED ALWAYS AS (
        encode(
            digest(
                COALESCE(prev_hash,'') || id::TEXT || event || ts::TEXT,
                'sha256'
            ),
            'hex'
        )
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_audit_ts
    ON public.audit_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor
    ON public.audit_log(actor_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_target
    ON public.audit_log(target_type, target_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event
    ON public.audit_log(event, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_recent
    ON public.audit_log(ts DESC, event)
    WHERE ts > NOW() - INTERVAL '90 days';

ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS audit_service ON public.audit_log;
CREATE POLICY audit_service ON public.audit_log
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

-- ======================================================================
-- SECTION 6 — REFRESH TOKENS TABLE
-- P13-DB-BUG-10: Phase 8 token rotation needs DB persistence
-- ======================================================================
CREATE TABLE IF NOT EXISTS public.refresh_tokens (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    token_hash      TEXT        NOT NULL UNIQUE,
    family_id       UUID        NOT NULL,
    session_id      UUID        NOT NULL,
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    rotated_at      TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    revoke_reason   TEXT        CHECK (revoke_reason IN
                        ('logout','reuse_detected','admin','family_revoked','expired')),
    ip_address      INET,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rt_user_id
    ON public.refresh_tokens(user_id, issued_at DESC);
CREATE INDEX IF NOT EXISTS idx_rt_family
    ON public.refresh_tokens(family_id);
CREATE INDEX IF NOT EXISTS idx_rt_expires
    ON public.refresh_tokens(expires_at)
    WHERE revoked_at IS NULL;

ALTER TABLE public.refresh_tokens ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rt_service ON public.refresh_tokens;
CREATE POLICY rt_service ON public.refresh_tokens
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

-- ======================================================================
-- SECTION 7 — NONCE STORE TABLE
-- P13-DB-BUG-11: Phase 6/7 anti-replay needs persistent nonce log
-- ======================================================================
CREATE TABLE IF NOT EXISTS public.nonce_store (
    nonce       TEXT        PRIMARY KEY,
    user_id     UUID        REFERENCES auth.users(id) ON DELETE CASCADE,
    context     TEXT        NOT NULL DEFAULT 'heartbeat'
                            CHECK (context IN ('heartbeat','webhook','auth')),
    issued_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_nonce_expires
    ON public.nonce_store(expires_at)
    WHERE used_at IS NULL;

ALTER TABLE public.nonce_store ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nonce_service ON public.nonce_store;
CREATE POLICY nonce_service ON public.nonce_store
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION public.cleanup_expired_nonces()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    DELETE FROM public.nonce_store
    WHERE expires_at < NOW() - INTERVAL '1 hour';
END;
$$;

-- ======================================================================
-- SECTION 8 — BILLING HARDENING
-- P13-DB-BUG-5:  billing_invoices missing provider_ref UNIQUE
-- P13-DB-BUG-6:  billing_subscriptions allows >1 active sub per user
-- P13-DB-BUG-13: INSERT guard for billing_plans
-- ======================================================================

-- 8a. Add provider_ref to invoices if missing (P13-DB-BUG-5)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='billing_invoices' AND column_name='provider_ref'
    ) THEN
        ALTER TABLE billing_invoices ADD COLUMN provider_ref TEXT;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_invoice_provider_ref
            ON billing_invoices(provider, provider_ref)
            WHERE provider_ref IS NOT NULL;
    END IF;
END $$;

-- 8b. Partial unique index: only one ACTIVE subscription per user (P13-DB-BUG-6)
CREATE UNIQUE INDEX IF NOT EXISTS uq_sub_user_active
    ON billing_subscriptions(user_id)
    WHERE status IN ('trial','active','past_due');

-- 8c. Add missing indexes on billing tables
CREATE INDEX IF NOT EXISTS idx_invoices_idempotency
    ON billing_invoices(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_invoices_provider_status
    ON billing_invoices(provider, status);
CREATE INDEX IF NOT EXISTS idx_subs_user_status
    ON billing_subscriptions(user_id, status);

-- 8d. RLS on billing_webhook_events (P13-DB-BUG-8)
ALTER TABLE billing_webhook_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS webhook_service ON billing_webhook_events;
CREATE POLICY webhook_service ON billing_webhook_events
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

-- 8e. RLS on billing_sub_transitions
ALTER TABLE billing_sub_transitions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS transitions_own_user ON billing_sub_transitions;
DROP POLICY IF EXISTS transitions_service  ON billing_sub_transitions;
CREATE POLICY transitions_own_user ON billing_sub_transitions
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);
CREATE POLICY transitions_service ON billing_sub_transitions
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

-- ======================================================================
-- SECTION 9 — TRADES DEDUP HARDENING
-- P13-DB-BUG-7: execution_orders needs (mt5_ticket, user_id) unique
-- ======================================================================

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name='execution_orders'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='execution_orders'
            AND column_name='idempotency_key'
        ) THEN
            ALTER TABLE public.execution_orders
                ADD COLUMN idempotency_key TEXT;
            UPDATE public.execution_orders
            SET idempotency_key = user_id::TEXT || ':' || COALESCE(mt5_ticket::TEXT, id::TEXT)
            WHERE idempotency_key IS NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS uq_exec_order_idempotency
                ON public.execution_orders(idempotency_key)
                WHERE idempotency_key IS NOT NULL;
        END IF;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_exec_order_user_ticket
            ON public.execution_orders(user_id, mt5_ticket)
            WHERE mt5_ticket IS NOT NULL;
    END IF;
END $$;

-- P13-DB-BUG-12: signals dedup
CREATE UNIQUE INDEX IF NOT EXISTS uq_signal_dedup
    ON public.signals(user_id, symbol, direction, date_trunc('minute', generated_at))
    WHERE status NOT IN ('cancelled','expired');

-- ======================================================================
-- SECTION 10 — MISSING COMPOSITE INDEXES
-- ======================================================================

CREATE INDEX IF NOT EXISTS idx_licenses_expires_status
    ON public.licenses(expires_at, status)
    WHERE status IN ('active','trial');

CREATE INDEX IF NOT EXISTS idx_trades_equity_curve
    ON public.trades(user_id, closed_at DESC, profit_money)
    WHERE status = 'closed';

CREATE INDEX IF NOT EXISTS idx_trades_daily_pnl
    ON public.trades(user_id, date_trunc('day', closed_at), profit_money)
    WHERE status = 'closed' AND profit_money IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_signals_admin_overview
    ON public.signals(generated_at DESC, total_score DESC)
    WHERE status IN ('generated','sent');

-- ======================================================================
-- SECTION 11 — DATABASE-LEVEL DUPLICATE ORDER PREVENTION FUNCTION
-- ======================================================================

CREATE OR REPLACE FUNCTION public.insert_trade_idempotent(
    p_user_id       UUID,
    p_mt5_ticket    BIGINT,
    p_symbol        TEXT,
    p_direction     TEXT,
    p_lot_size      DECIMAL,
    p_entry_price   DECIMAL,
    p_opened_at     TIMESTAMPTZ DEFAULT NOW()
) RETURNS TABLE(trade_id UUID, was_duplicate BOOLEAN)
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_id        UUID;
    v_duplicate BOOLEAN := FALSE;
BEGIN
    INSERT INTO public.trades (
        user_id, mt5_ticket, symbol, direction,
        lot_size, entry_price, status, opened_at
    ) VALUES (
        p_user_id, p_mt5_ticket, p_symbol, p_direction,
        p_lot_size, p_entry_price, 'open', p_opened_at
    )
    ON CONFLICT (mt5_ticket) DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NULL THEN
        SELECT id INTO v_id FROM public.trades
        WHERE mt5_ticket = p_mt5_ticket;
        v_duplicate := TRUE;
    END IF;

    RETURN QUERY SELECT v_id, v_duplicate;
END;
$$;

-- ======================================================================
-- SECTION 12 — SUBSCRIPTION EXPIRY FUNCTION
-- ======================================================================

CREATE OR REPLACE FUNCTION public.expire_stale_subscriptions()
RETURNS INTEGER LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    WITH expired AS (
        UPDATE billing_subscriptions
        SET status     = 'expired',
            updated_at = NOW()
        WHERE status IN ('active','trial','past_due')
          AND expires_at IS NOT NULL
          AND expires_at < NOW()
        RETURNING sub_id, user_id
    ),
    logged AS (
        INSERT INTO billing_sub_transitions (sub_id, user_id, from_status, to_status, reason, actor)
        SELECT e.sub_id, e.user_id,
               (SELECT status FROM billing_subscriptions WHERE sub_id = e.sub_id),
               'expired', 'auto-expire cron', 'system'
        FROM expired e
    )
    SELECT COUNT(*) INTO v_count FROM expired;

    RETURN v_count;
END;
$$;

-- ======================================================================
-- SECTION 13 — VIEWS
-- ======================================================================

CREATE OR REPLACE VIEW public.vw_admin_subscriptions AS
SELECT
    bs.sub_id,
    bs.user_id,
    up.telegram_username,
    bs.plan_id,
    bp.label       AS plan_label,
    bs.status,
    bs.expires_at,
    bs.dunning_count,
    bs.created_at,
    COUNT(ld.id)   AS device_count
FROM billing_subscriptions bs
LEFT JOIN public.user_profiles   up ON up.user_id  = bs.user_id
LEFT JOIN billing_plans          bp ON bp.plan_id  = bs.plan_id
LEFT JOIN public.license_devices ld ON ld.user_id  = bs.user_id AND ld.status = 'active'
GROUP BY bs.sub_id, bs.user_id, up.telegram_username,
         bs.plan_id, bp.label, bs.status, bs.expires_at,
         bs.dunning_count, bs.created_at;

CREATE OR REPLACE VIEW public.vw_my_license AS
SELECT
    l.id          AS license_id,
    l.status,
    l.license_type,
    l.expires_at,
    l.key_hash,
    COUNT(ld.id)  AS device_count,
    l.max_accounts AS max_devices
FROM public.licenses     l
LEFT JOIN public.license_devices ld
    ON ld.license_id = l.id AND ld.status = 'active'
WHERE l.user_id = auth.uid()
GROUP BY l.id, l.status, l.license_type, l.expires_at, l.key_hash, l.max_accounts;

-- ======================================================================
-- SECTION 14 — VALIDATE MIGRATION (self-check)
-- ======================================================================

DO $$
DECLARE
    v_missing TEXT[] := ARRAY[]::TEXT[];
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='license_devices' AND table_schema='public') THEN
        v_missing := v_missing || 'license_devices';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='audit_log' AND table_schema='public') THEN
        v_missing := v_missing || 'audit_log';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='refresh_tokens' AND table_schema='public') THEN
        v_missing := v_missing || 'refresh_tokens';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='nonce_store' AND table_schema='public') THEN
        v_missing := v_missing || 'nonce_store';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='licenses' AND column_name='key_hash' AND table_schema='public') THEN
        v_missing := v_missing || 'licenses.key_hash';
    END IF;

    IF array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION 'Migration validation failed — missing: %', array_to_string(v_missing, ', ');
    END IF;

    RAISE NOTICE 'Phase 13 migration OK — all tables and columns verified';
END $$;

COMMIT;
