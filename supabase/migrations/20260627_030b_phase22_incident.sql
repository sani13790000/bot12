-- Phase 22: Incident Response & Kill-Switch Tables
-- Migration: 20260627_030b_phase22_incident.sql

BEGIN;

-- Kill switch table
CREATE TABLE IF NOT EXISTS kill_switches_v22 (
    ks_id           TEXT        PRIMARY KEY,
    target          TEXT        NOT NULL CHECK (target IN ('bot','device','license','user','tenant','release','global')),
    target_id       TEXT        NOT NULL,
    reason          TEXT        NOT NULL,
    reason_note     TEXT        NOT NULL DEFAULT '',
    severity        TEXT        NOT NULL CHECK (severity IN ('P1','P2','P3','P4')),
    actor_id        TEXT        NOT NULL,
    tenant_id       TEXT        NOT NULL,
    incident_id     TEXT,
    ttl_seconds     REAL,
    activated_at    REAL        NOT NULL,
    reset_at        REAL,
    reset_by        TEXT,
    reset_note      TEXT,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Incident table
CREATE TABLE IF NOT EXISTS incidents_v22 (
    incident_id     TEXT        PRIMARY KEY,
    title           TEXT        NOT NULL,
    severity        TEXT        NOT NULL CHECK (severity IN ('P1','P2','P3','P4')),
    reason          TEXT        NOT NULL,
    tenant_id       TEXT        NOT NULL,
    reporter_id     TEXT        NOT NULL,
    state           TEXT        NOT NULL DEFAULT 'open',
    runbook_id      TEXT,
    tags            TEXT[]      NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    contained_at    TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    closed_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ks22_target         ON kill_switches_v22(target, target_id);
CREATE INDEX IF NOT EXISTS idx_ks22_tenant         ON kill_switches_v22(tenant_id, is_active);
CREATE INDEX IF NOT EXISTS idx_inc22_tenant_state  ON incidents_v22(tenant_id, state);
CREATE INDEX IF NOT EXISTS idx_inc22_severity      ON incidents_v22(severity, created_at DESC);

ALTER TABLE kill_switches_v22 ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents_v22     ENABLE ROW LEVEL SECURITY;

COMMIT;
