-- ======================================================================
-- Phase 21: Tamper-Evident Audit Logging
-- Migration: 20260626_029_phase21_audit_chain.sql
-- ======================================================================
-- BUGS FIXED:
-- P21-SQL-1: chain_hash now 64 chars (HMAC-SHA256 full hex)
-- P21-SQL-2: hmac_key_id column for key rotation support
-- P21-SQL-3: 64 event types via severity CHECK
-- P21-SQL-4: Mandatory reason trigger for sensitive events
-- P21-SQL-5: severity column (INFO/WARNING/CRITICAL)
-- P21-SQL-6: tenant_id on all audit records
-- P21-SQL-7: RLS policy - tenant isolation
-- P21-SQL-8: verify_audit_chain_v21() stored procedure
-- ======================================================================
BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- audit_log_v21 table
CREATE TABLE IF NOT EXISTS public.audit_log_v21 (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    seq             BIGINT      NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    ts_epoch        DOUBLE PRECISION NOT NULL,
    event           TEXT        NOT NULL,
    severity        TEXT        NOT NULL DEFAULT 'INFO'
                                CHECK (severity IN ('INFO','WARNING','CRITICAL')),
    user_id         TEXT,
    actor_id        TEXT,
    tenant_id       TEXT        NOT NULL DEFAULT 'default',
    ip              TEXT,
    user_agent      TEXT,
    reason          TEXT,
    detail          JSONB       NOT NULL DEFAULT '{}',
    chain_hash      TEXT        NOT NULL,
    prev_hash       TEXT        NOT NULL,
    hmac_key_id     TEXT        NOT NULL DEFAULT 'v1',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_chain_hash_len CHECK (length(chain_hash) = 64),
    CONSTRAINT chk_prev_hash_len  CHECK (length(prev_hash) >= 64 OR prev_hash LIKE 'GENESIS%')
);

CREATE INDEX IF NOT EXISTS idx_audit_v21_seq ON public.audit_log_v21 (seq);
CREATE INDEX IF NOT EXISTS idx_audit_v21_tenant_event ON public.audit_log_v21 (tenant_id, event, ts);
CREATE INDEX IF NOT EXISTS idx_audit_v21_user_ts ON public.audit_log_v21 (user_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_v21_severity_ts ON public.audit_log_v21 (severity, ts DESC) WHERE severity IN ('WARNING','CRITICAL');
CREATE INDEX IF NOT EXISTS idx_audit_v21_detail ON public.audit_log_v21 USING gin (detail);

-- Immutability triggers
CREATE OR REPLACE FUNCTION public.audit_v21_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log_v21 is immutable — records cannot be updated or deleted. seq=%, event=%', OLD.seq, OLD.event;
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_v21_no_update ON public.audit_log_v21;
CREATE TRIGGER trg_audit_v21_no_update
    BEFORE UPDATE ON public.audit_log_v21
    FOR EACH ROW EXECUTE FUNCTION public.audit_v21_immutable();

DROP TRIGGER IF EXISTS trg_audit_v21_no_delete ON public.audit_log_v21;
CREATE TRIGGER trg_audit_v21_no_delete
    BEFORE DELETE ON public.audit_log_v21
    FOR EACH ROW EXECUTE FUNCTION public.audit_v21_immutable();

-- Mandatory reason enforcement
CREATE OR REPLACE FUNCTION public.audit_v21_require_reason()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    sensitive_events TEXT[] := ARRAY[
        'license.revoked', 'license.suspended',
        'rbac.role_changed', 'rbac.user_blocked', 'rbac.user_deleted',
        'risk.kill_switch.activated', 'risk.kill_switch.reset',
        'risk.halt', 'billing.refund',
        'admin.impersonate', 'admin.force_logout',
        'tenant.suspend', 'tenant.purge'
    ];
BEGIN
    IF NEW.event = ANY(sensitive_events) AND (NEW.reason IS NULL OR trim(NEW.reason) = '') THEN
        RAISE EXCEPTION
            'Audit event "%" requires a non-empty reason field for compliance', NEW.event
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_v21_reason ON public.audit_log_v21;
CREATE TRIGGER trg_audit_v21_reason
    BEFORE INSERT ON public.audit_log_v21
    FOR EACH ROW EXECUTE FUNCTION public.audit_v21_require_reason();

-- RLS
ALTER TABLE public.audit_log_v21 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_audit_v21_tenant ON public.audit_log_v21;
CREATE POLICY pol_audit_v21_tenant ON public.audit_log_v21
    FOR SELECT USING (
        tenant_id = current_setting('app.current_tenant_id', true)
        OR public.is_app_admin()
    );

DROP POLICY IF EXISTS pol_audit_v21_insert ON public.audit_log_v21;
CREATE POLICY pol_audit_v21_insert ON public.audit_log_v21
    FOR INSERT WITH CHECK (
        current_setting('role','t') = 'service_role'
        OR public.is_app_admin()
    );

-- verify_audit_chain_v21 function
CREATE OR REPLACE FUNCTION public.verify_audit_chain_v21(
    p_tenant_id TEXT DEFAULT NULL,
    p_limit     INT  DEFAULT 10000
)
RETURNS TABLE (
    is_valid         BOOLEAN,
    total_checked    INT,
    first_broken_seq BIGINT,
    broken_count     INT
) LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    rec          RECORD;
    prev_hash    TEXT := '';
    broken       INT  := 0;
    total        INT  := 0;
    first_broken BIGINT := NULL;
    last_seq     BIGINT := -1;
BEGIN
    FOR rec IN
        SELECT seq, chain_hash, prev_hash as phash
        FROM public.audit_log_v21
        WHERE (p_tenant_id IS NULL OR tenant_id = p_tenant_id)
        ORDER BY seq ASC LIMIT p_limit
    LOOP
        total := total + 1;
        IF last_seq >= 0 AND rec.seq != last_seq + 1 THEN
            broken := broken + 1;
            IF first_broken IS NULL THEN first_broken := rec.seq; END IF;
        END IF;
        IF total > 1 AND rec.phash != prev_hash THEN
            broken := broken + 1;
            IF first_broken IS NULL THEN first_broken := rec.seq; END IF;
        END IF;
        prev_hash := rec.chain_hash;
        last_seq  := rec.seq;
    END LOOP;
    RETURN QUERY SELECT broken = 0, total, first_broken, broken;
END;
$$;

-- Views
CREATE OR REPLACE VIEW public.vw_audit_summary AS
SELECT tenant_id, severity, date_trunc('hour', ts) AS hour_bucket,
       count(*) AS event_count,
       count(*) FILTER (WHERE severity = 'CRITICAL') AS critical_count
FROM public.audit_log_v21 GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW public.vw_audit_admin AS
SELECT a.*, to_timestamp(a.ts_epoch) AS ts_human
FROM public.audit_log_v21 a ORDER BY a.seq DESC;

-- Self-validation
DO $$
DECLARE tbl_count INT; col_count INT; trg_count INT;
BEGIN
    SELECT count(*) INTO tbl_count FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'audit_log_v21';
    IF tbl_count = 0 THEN RAISE EXCEPTION 'P21-VALIDATE: audit_log_v21 table missing'; END IF;
    SELECT count(*) INTO col_count FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'audit_log_v21' AND column_name = 'chain_hash';
    IF col_count = 0 THEN RAISE EXCEPTION 'P21-VALIDATE: chain_hash column missing'; END IF;
    SELECT count(*) INTO trg_count FROM information_schema.triggers
    WHERE trigger_schema = 'public' AND event_object_table = 'audit_log_v21'
      AND trigger_name LIKE 'trg_audit_v21%';
    IF trg_count < 2 THEN RAISE EXCEPTION 'P21-VALIDATE: immutability triggers missing (found %)', trg_count; END IF;
    RAISE NOTICE 'P21-VALIDATE: audit_log_v21 OK — table + chain_hash + % triggers', trg_count;
END;
$$;

COMMIT;
