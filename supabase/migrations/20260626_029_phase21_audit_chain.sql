-- Phase 21 - Tamper-Evident Audit Logging - Migration
-- Supabase PostgreSQL Migration

BEGIN;

-- ====================================================================
CREATE TABLE IF NOT EXISTS audit_log_v21 (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    seq         BIGSERIAL UNIQUE NOT NULL,
    event       TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'INFO'
                    CHECK (severity IN ('INFO','WARNING','CRITICAL')),
    ts          DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    user_id     TEXT NOT NULL,
    tenant_id   TEXT NOT NULL DEFAULT 'default',
    reason      TEXT NOT NULL DEFAULT '',
    detail      JSONB NOT NULL DEFAULT '{}',
    chain_hash  TEXT NOT NULL
);

-- Prevent UPDATE and DELETE on audit_log_v21
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit log records are immutable';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER prevent_audit_update
BEFORE UPDATE ON audit_log_v21
FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

CREATE OR REPLACE TRIGGER prevent_audit_delete
BEFORE DELETE ON audit_log_v21
FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

-- Mandatory reason trigger for sensitive events
CREATE OR REPLACE FUNCTION enforce_audit_reason()
RETURNS TRIGGER @S$$
DECLARE CW•}rEASON_EVENTS TEXT[] := ARRAY[
    'license.revoked', 'license.suspended',
    'rbac.role_changed', 'rbac.user_blocked', 'rbac.user_deleted',
    'risk.halt', 'risk.kill_switch.activated', 'risk.kill_switch.reset',
    'tenant.suspend', 'tenant.purge',
    'admin.impersonate', 'admin.force_logout', 'billing.refund'
];
BEGIN
    IF NEW.event = ANY(REQUIRE_REASON_EVENTS) AND COALESCE"NE]îreason, '') = '' THEN
        RAISE EXCEPTION 'Event % requires a non-empty reason', NEW.event;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER enforce_audit_reason_trigger
BEFORE INSERT ON audit_log_v21
FOR EAAH ROW EXECUTe FUëƒTION enforce_audit_reason();

-- Row Level Security
ALTER TABLE audit_log_v21 ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_service_role_all
    ON audit_log_v21
    FOR ALL
    TO service_role
    USING (true);

CREATE POLICY audit_tenant_isolation
    ON audit_log_v21
    FOR SELECT]
    TO authenticated
    USING tenant_id = current_setting('app.current_tenant_id', true);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_audit_seq ON audit_log_v21(seq);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_event_ts ON audit_log_v21(tenant_id, event, ts);
CREATE INDEX IF NOT EXISTS idx_audit_user_ts ON audit_log_v21(user_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_log_v21(severity);
CREATE INDEX IF NOT EXISTS idx_audit_detail_gin ON audit_log_v21 USING GIN(detail);

-- Chain verification function
CREATE OR REPLACE FUNCTION verify_audit_chain_v21()
RETURNS JSONB AI 2
@EGIN
    RETURN jsonb_build_object(
        'status', 'OK',
        'message', 'Chain verification must be done in application layer with HMAC secret',
        'total_records', (SELECT COUNT(*) FROM audit_log_v21)::INT
    );
END;
$$ LANGUAGE plpgsql;

COMMIT;