-- Phase 22: Incident Response & Kill-Switch Tables
-- Migration: 20260627_030_phase22_incident.sql

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

-- Incident timeline (immutable append-only)
CREATE TABLE IF NOT EXISTS incident_timeline_v22 (
    id              BIGSERIAL   PRIMARY KEY,
    incident_id     TEXT        NOT NULL REFERENCES incidents_v22(incident_id),
    ts              REAL        NOT NULL,
    actor_id        TEXT        NOT NULL,
    action          TEXT        NOT NULL,
    detail          JSONB       NOT NULL DEFAULT '{}'
);

-- Prevent UPDATE/DELETE on timeline (append-only)
CREATE OR REPLACE RULE incident_timeline_no_update AS
    ON UPDATE TO incident_timeline_v22 DO INSTEAD NOTHING;
CREATE OR REPLACE RULE incident_timeline_no_delete AS
    ON DELETE TO incident_timeline_v22 DO INSTEAD NOTHING;

-- Alert history
CREATE TABLE IF NOT EXISTS alert_history_v22 (
    id              BIGSERIAL   PRIMARY KEY,
    ts              REAL        NOT NULL,
    message         TEXT        NOT NULL,
    severity        TEXT        NOT NULL,
    channels        JSONB       NOT NULL DEFAULT '{}',
    dedup_key       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ks22_target        ON kill_switches_v22(target, target_id);
CREATE INDEX IF NOT EXISTS idx_ks22_tenant        ON kill_switches_v22(tenant_id, is_active);
CREATE INDEX IF NOT EXISTS idx_ks22_incident      ON kill_switches_v22(incident_id);
CREATE INDEX IF NOT EXISTS idx_inc22_tenant_state ON incidents_v22(tenant_id, state);
CREATE INDEX IF NOT EXISTS idx_inc22_severity     ON incidents_v22(severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_timeline22_inc     ON incident_timeline_v22(incident_id, ts DESC);

-- RLS
ALTER TABLE kill_switches_v22     ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents_v22         ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_timeline_v22 ENABLE ROW LEVEL SECURITY;

CREATE POLICY ks22_tenant_isolation ON kill_switches_v22
    USING (is_app_admin() OR tenant_id = current_tenant_id());
CREATE POLICY inc22_tenant_isolation ON incidents_v22
    USING (is_app_admin() OR tenant_id = current_tenant_id());
CREATE POLICY timeline22_via_incident ON incident_timeline_v22
    USING (is_app_admin() OR EXISTS (
        SELECT 1 FROM incidents_v22 i
        WHERE i.incident_id = incident_timeline_v22.incident_id
          AND (is_app_admin() OR i.tenant_id = current_tenant_id())
    ));

COMMIT;
