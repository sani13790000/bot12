-- Phase 33b: Support Tooling Extended
-- Migration: 20260628_042b_phase33_support_tooling.sql

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
CREATE INDEX IF NOT EXISTS idx_impersonation_agent  ON impersonation_sessions (agent_id);
CREATE INDEX IF NOT EXISTS idx_impersonation_target ON impersonation_sessions (target_user_id);
CREATE INDEX IF NOT EXISTS idx_impersonation_status ON impersonation_sessions (status) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS intervention_billing (
    id              BIGSERIAL   PRIMARY KEY,
    intervention_id UUID        NOT NULL REFERENCES support_interventions(intervention_id),
    tenant_id       TEXT        NOT NULL,
    charged_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    amount_cents    INTEGER     NOT NULL DEFAULT 0,
    currency        TEXT        NOT NULL DEFAULT 'USD',
    description     TEXT        NOT NULL DEFAULT ''
);

ALTER TABLE intervention_billing ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_intervention_billing_tenant ON intervention_billing (tenant_id);
