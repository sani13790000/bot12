-- Phase 33: Support Tooling & Controlled Intervention
-- Migration: 20260627_042a_phase33_support_tools.sql
-- Tables: support_agents, support_interventions, impersonation_sessions,
--         support_audit_log, intervention_billing, support_device_resets

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
CREATE INDEX IF NOT EXISTS idx_support_interventions_tenant ON support_interventions (tenant_id);
CREATE INDEX IF NOT EXISTS idx_support_interventions_user   ON support_interventions (target_user_id);
CREATE INDEX IF NOT EXISTS idx_support_interventions_kind   ON support_interventions (kind);
CREATE INDEX IF NOT EXISTS idx_support_interventions_status ON support_interventions (status);

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
CREATE INDEX IF NOT EXISTS idx_support_audit_target ON support_audit_log (target_id);
CREATE INDEX IF NOT EXISTS idx_support_audit_actor  ON support_audit_log (actor_id);
CREATE INDEX IF NOT EXISTS idx_support_audit_ts     ON support_audit_log (ts DESC);
