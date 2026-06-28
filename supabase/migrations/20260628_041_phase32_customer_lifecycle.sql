-- PHASE 32: Customer Lifecycle Automation
-- Migration 041
-- Tables: customer_lifecycle_events, notification_log, support_tickets,
--         reactivation_offers, dunning_log, lifecycle_audit_log
-- RLS, immutable audit trigger, indexes, views, cleanup

BEGIN;

-- -----------------------------------------------------------------------
-- 1. customer_lifecycle_events
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customer_lifecycle_events (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     TEXT        NOT NULL,
    tenant_id       TEXT        NOT NULL,
    event           TEXT        NOT NULL,
    actor           TEXT        NOT NULL DEFAULT 'system',
    reason          TEXT        NOT NULL DEFAULT '',
    detail          JSONB       NOT NULL DEFAULT '{}',
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE customer_lifecycle_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY lifecycle_events_tenant_isolation
    ON customer_lifecycle_events
    USING (tenant_id = current_setting('app.current_tenant', true));

-- -----------------------------------------------------------------------
-- 2. notification_log
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notification_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     TEXT        NOT NULL,
    tenant_id       TEXT        NOT NULL,
    template        TEXT        NOT NULL,
    channel         TEXT        NOT NULL DEFAULT 'email',
    subject         TEXT        NOT NULL,
    body            TEXT        NOT NULL,
    params          JSONB       NOT NULL DEFAULT '{}',
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE notification_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY notification_log_tenant_isolation
    ON notification_log
    USING (tenant_id = current_setting('app.current_tenant', true));

-- -----------------------------------------------------------------------
-- 3. support_tickets
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS support_tickets (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     TEXT        NOT NULL,
    tenant_id       TEXT        NOT NULL,
    category        TEXT        NOT NULL,
    subject         TEXT        NOT NULL,
    body            TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open','self_served','closed')),
    self_served     BOOLEAN     NOT NULL DEFAULT FALSE,
    resolution      TEXT        NOT NULL DEFAULT '',
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE support_tickets ENABLE ROW LEVEL SECURITY;

CREATE POLICY support_tickets_tenant_isolation
    ON support_tickets
    USING (tenant_id = current_setting('app.current_tenant', true));

-- -----------------------------------------------------------------------
-- 4. reactivation_offers
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reactivation_offers (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     TEXT        NOT NULL,
    tenant_id       TEXT        NOT NULL,
    discount_pct    INTEGER     NOT NULL DEFAULT 20
                                CHECK (discount_pct BETWEEN 0 AND 100),
    valid_until     TIMESTAMPTZ NOT NULL,
    accepted        BOOLEAN,
    responded_at    TIMESTAMPTZ,
    reason          TEXT        NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE reactivation_offers ENABLE ROW LEVEL SECURITY;

CREATE POLICY reactivation_offers_tenant_isolation
    ON reactivation_offers
    USING (tenant_id = current_setting('app.current_tenant', true));

-- -----------------------------------------------------------------------
-- 5. dunning_log
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dunning_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     TEXT        NOT NULL,
    tenant_id       TEXT        NOT NULL,
    event           TEXT        NOT NULL
                                CHECK (event IN (
                                    'payment.failed','payment.recovered',
                                    'dunning.started','dunning.resolved'
                                )),
    attempt         INTEGER     NOT NULL DEFAULT 1,
    plan            TEXT        NOT NULL DEFAULT '',
    actor           TEXT        NOT NULL DEFAULT 'system',
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE dunning_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY dunning_log_tenant_isolation
    ON dunning_log
    USING (tenant_id = current_setting('app.current_tenant', true));

-- -----------------------------------------------------------------------
-- 6. lifecycle_audit_log (IMMUTABLE HMAC chain)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lifecycle_audit_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    seq             BIGSERIAL   NOT NULL,
    entry_id        TEXT        NOT NULL UNIQUE,
    event           TEXT        NOT NULL,
    customer_id     TEXT        NOT NULL,
    tenant_id       TEXT        NOT NULL,
    actor           TEXT        NOT NULL,
    reason          TEXT        NOT NULL DEFAULT '',
    detail          JSONB       NOT NULL DEFAULT '{}',
    chain_hash      CHAR(64)    NOT NULL,
    ts              DOUBLE PRECISION NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE lifecycle_audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY lifecycle_audit_tenant_isolation
    ON lifecycle_audit_log
    USING (tenant_id = current_setting('app.current_tenant', true));

-- Immutable trigger
CREATE OR REPLACE FUNCTION lifecycle_audit_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'lifecycle_audit_log is immutable: UPDATE/DELETE not allowed';
END;
$$;

CREATE TRIGGER lifecycle_audit_log_immutable
    BEFORE UPDATE OR DELETE ON lifecycle_audit_log
    FOR EACH ROW EXECUTE FUNCTION lifecycle_audit_immutable();

-- -----------------------------------------------------------------------
-- Indexes
-- -----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_lifecycle_events_customer
    ON customer_lifecycle_events(customer_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_lifecycle_events_event
    ON customer_lifecycle_events(event, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_log_customer
    ON notification_log(customer_id, tenant_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_log_template
    ON notification_log(template, tenant_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_customer
    ON support_tickets(customer_id, tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_support_tickets_category
    ON support_tickets(category, status);
CREATE INDEX IF NOT EXISTS idx_reactivation_offers_customer
    ON reactivation_offers(customer_id, tenant_id, valid_until);
CREATE INDEX IF NOT EXISTS idx_dunning_log_customer
    ON dunning_log(customer_id, tenant_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_lifecycle_audit_customer
    ON lifecycle_audit_log(customer_id, tenant_id, seq);
CREATE INDEX IF NOT EXISTS idx_lifecycle_audit_event
    ON lifecycle_audit_log(event, ts DESC);

-- -----------------------------------------------------------------------
-- Cleanup function
-- -----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION cleanup_old_lifecycle_events(
    retention_days INTEGER DEFAULT 90
) RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE
    deleted INTEGER;
BEGIN
    DELETE FROM customer_lifecycle_events
    WHERE occurred_at < now() - (retention_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted = ROW_COUNT;
    DELETE FROM notification_log
    WHERE sent_at < now() - (retention_days || ' days')::INTERVAL;
    RETURN deleted;
END;
$$;

-- -----------------------------------------------------------------------
-- Views
-- -----------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_active_customers AS
SELECT
    customer_id,
    tenant_id,
    MAX(occurred_at) AS last_event,
    COUNT(*)         AS event_count
FROM customer_lifecycle_events
GROUP BY customer_id, tenant_id;

CREATE OR REPLACE VIEW vw_support_deflection_rate AS
SELECT
    tenant_id,
    COUNT(*) FILTER (WHERE self_served = TRUE)::FLOAT /
        NULLIF(COUNT(*), 0)                          AS deflection_rate,
    COUNT(*) FILTER (WHERE status = 'open')          AS open_tickets,
    COUNT(*) FILTER (WHERE self_served = TRUE)        AS self_served_count,
    COUNT(*)                                          AS total_tickets
FROM support_tickets
GROUP BY tenant_id;

CREATE OR REPLACE VIEW vw_lifecycle_audit_summary AS
SELECT
    tenant_id,
    event,
    COUNT(*) AS event_count,
    MAX(ts)  AS last_seen
FROM lifecycle_audit_log
GROUP BY tenant_id, event
ORDER BY event_count DESC;

COMMIT;
