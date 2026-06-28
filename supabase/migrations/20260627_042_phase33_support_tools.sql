-- =============================================================================
-- PHASE 33: Support Tooling & Controlled Intervention
-- Migration: 20260627_042_phase33_support_tools.sql
-- Tables: support_agents, support_interventions, impersonation_sessions,
--         support_audit_log, intervention_billing, support_device_resets
-- =============================================================================

CREATE TABLE IF NOT EXISTS support_agents (
    agent_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL,
    role        TEXT        NOT NULL CHECK (role IN (
                    'support.l1','support.l2','support.l3','support.admin'
                )),
    tenant_id   TEXT        NOT NULL DEFAULT 'system',
    active      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE support_agents ENABLE ROW LEVEL SECURITY;
CREATE POLICY support_agents_tenant ON support_agents
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

CREATE INDEX IF NOT EXISTS idx_support_agents_tenant ON support_agents (tenant_id);
CREATE INDEX IF NOT EXISTS idx_support_agents_active ON support_agents (active) WHERE active = TRUE;

CREATE TABLE IF NOT EXISTS support_interventions (
    intervention_id UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kind            TEXT        NOT NULL,
    actor_id        TEXT        NOT NULL,
    actor_role      TEXT        NOT NULL CHECK (actor_role IN (
                        'support.l1','support.l2','support.l3','support.admin'
                    )),
    target_user_id  TEXT        NOT NULL,
    tenant_id       TEXT        NOT NULL,
    reason_note     TEXT        NOT NULL,
    detail          JSONB       NOT NULL DEFAULT '{}',
    status          TEXT        NOT NULL DEFAULT 'executed'
                        CHECK (status IN ('pending','approved','executed','denied','reverted')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_at     TIMESTAMPTZ,
    reverted_at     TIMESTAMPTZ,
    revert_reason   TEXT
);

ALTER TABLE support_interventions ENABLE ROW LEVEL SECURITY;
CREATE POLICY support_interventions_tenant ON support_interventions
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

CREATE INDEX IF NOT EXISTS idx_support_interventions_tenant ON support_interventions (tenant_id);
CREATE INDEX IF NOT EXISTS idx_support_interventions_user ON support_interventions (target_user_id);
CREATE INDEX IF NOT EXISTS idx_support_interventions_kind ON support_interventions (kind);
CREATE INDEX IF NOT EXISTS idx_support_interventions_status ON support_interventions (status);
CREATE INDEX IF NOT EXISTS idx_support_interventions_actor ON support_interventions (actor_id);

CREATE TABLE IF NOT EXISTS impersonation_sessions (
    session_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT        NOT NULL,
    target_user_id  TEXT        NOT NULL,
    tenant_id       TEXT        NOT NULL,
    granted_by      TEXT        NOT NULL,
    reason          TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','ended','revoked','expired')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ttl_seconds     INTEGER     NOT NULL DEFAULT 1800 CHECK (ttl_seconds >= 0),
    ended_at        TIMESTAMPTZ,
    actions_taken   JSONB       NOT NULL DEFAULT '[]'
);

ALTER TABLE impersonation_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY impersonation_sessions_tenant ON impersonation_sessions
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

CREATE INDEX IF NOT EXISTS idx_impersonation_agent ON impersonation_sessions (agent_id);
CREATE INDEX IF NOT EXISTS idx_impersonation_target ON impersonation_sessions (target_user_id);
CREATE INDEX IF NOT EXISTS idx_impersonation_status ON impersonation_sessions (status) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS support_audit_log (
    id          BIGSERIAL   PRIMARY KEY,
    seq         INTEGER     NOT NULL,
    entry_id    UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    kind        TEXT        NOT NULL,
    actor_id    TEXT        NOT NULL,
    target_id   TEXT        NOT NULL,
    tenant_id   TEXT        NOT NULL,
    reason      TEXT        NOT NULL DEFAULT '',
    detail      JSONB       NOT NULL DEFAULT '{}',
    ts          DOUBLE PRECISION NOT NULL,
    chain_hash  CHAR(64)    NOT NULL
);

ALTER TABLE support_audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY support_audit_log_tenant ON support_audit_log
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

CREATE INDEX IF NOT EXISTS idx_support_audit_target ON support_audit_log (target_id);
CREATE INDEX IF NOT EXISTS idx_support_audit_actor  ON support_audit_log (actor_id);
CREATE INDEX IF NOT EXISTS idx_support_audit_kind   ON support_audit_log (kind);
CREATE INDEX IF NOT EXISTS idx_support_audit_ts     ON support_audit_log (ts DESC);

CREATE OR REPLACE FUNCTION support_audit_log_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'support_audit_log is immutable: % denied', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_support_audit_immutable ON support_audit_log;
CREATE TRIGGER trg_support_audit_immutable
    BEFORE UPDATE OR DELETE ON support_audit_log
    FOR EACH ROW EXECUTE FUNCTION support_audit_log_immutable();

CREATE TABLE IF NOT EXISTS intervention_billing (
    billing_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kind            TEXT        NOT NULL CHECK (kind IN ('refund','credit')),
    intervention_id UUID        REFERENCES support_interventions(intervention_id),
    actor_id        TEXT        NOT NULL,
    user_id         TEXT        NOT NULL,
    tenant_id       TEXT        NOT NULL,
    amount_cents    INTEGER     NOT NULL CHECK (amount_cents > 0),
    reason          TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'issued',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE intervention_billing ENABLE ROW LEVEL SECURITY;
CREATE POLICY intervention_billing_tenant ON intervention_billing
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

CREATE INDEX IF NOT EXISTS idx_billing_user   ON intervention_billing (user_id);
CREATE INDEX IF NOT EXISTS idx_billing_tenant ON intervention_billing (tenant_id);
CREATE INDEX IF NOT EXISTS idx_billing_kind   ON intervention_billing (kind);

CREATE TABLE IF NOT EXISTS support_device_resets (
    reset_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id   TEXT        NOT NULL,
    user_id     TEXT        NOT NULL,
    tenant_id   TEXT        NOT NULL,
    actor_id    TEXT        NOT NULL,
    action      TEXT        NOT NULL CHECK (action IN ('reset','revoke','transfer')),
    reason      TEXT        NOT NULL DEFAULT '',
    reset_count INTEGER     NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE support_device_resets ENABLE ROW LEVEL SECURITY;
CREATE POLICY support_device_resets_tenant ON support_device_resets
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

CREATE INDEX IF NOT EXISTS idx_device_resets_device ON support_device_resets (device_id);
CREATE INDEX IF NOT EXISTS idx_device_resets_user   ON support_device_resets (user_id);

CREATE OR REPLACE FUNCTION cleanup_expired_impersonation_sessions()
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE deleted INTEGER;
BEGIN
    UPDATE impersonation_sessions
    SET    status = 'expired'
    WHERE  status = 'active'
    AND    NOW() > (started_at + (ttl_seconds || ' seconds')::interval);
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$;

CREATE OR REPLACE VIEW vw_active_impersonations AS
SELECT s.session_id, s.agent_id, a.name AS agent_name, a.role AS agent_role,
       s.target_user_id, s.tenant_id, s.granted_by, s.started_at,
       (s.started_at + (s.ttl_seconds || ' seconds')::interval) AS expires_at,
       jsonb_array_length(s.actions_taken) AS action_count
FROM impersonation_sessions s
LEFT JOIN support_agents a ON a.agent_id::TEXT = s.agent_id
WHERE s.status = 'active';

CREATE OR REPLACE VIEW vw_support_intervention_summary AS
SELECT tenant_id, kind, status, COUNT(*) AS total, MAX(created_at) AS last_at
FROM support_interventions GROUP BY tenant_id, kind, status;

CREATE OR REPLACE VIEW vw_support_audit_summary AS
SELECT tenant_id, kind, COUNT(*) AS total, MIN(ts) AS first_ts, MAX(ts) AS last_ts
FROM support_audit_log GROUP BY tenant_id, kind;
