-- Phase 33: Support Tools Tables
-- BUG-T3 FIX: Renamed from 20260627_042a to 20260628_042a
-- Ensures execution AFTER 20260628_041_phase32_customer_lifecycle.sql
-- Original content preserved exactly.

-- Support tickets
CREATE TABLE IF NOT EXISTS support_tickets (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id         uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    subject         text NOT NULL,
    body            text NOT NULL,
    status          text NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','in_progress','resolved','closed')),
    priority        text NOT NULL DEFAULT 'normal'
                        CHECK (priority IN ('low','normal','high','urgent')),
    assigned_to     uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    tags            text[] DEFAULT '{}',
    resolved_at     timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_support_tickets_tenant
    ON support_tickets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_status
    ON support_tickets(status);
CREATE INDEX IF NOT EXISTS idx_support_tickets_priority
    ON support_tickets(priority);

-- Support ticket replies
CREATE TABLE IF NOT EXISTS support_ticket_replies (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id   uuid NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
    author_id   uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    body        text NOT NULL,
    is_internal boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_support_replies_ticket
    ON support_ticket_replies(ticket_id);

-- Support knowledge base
CREATE TABLE IF NOT EXISTS support_kb_articles (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid REFERENCES tenants(id) ON DELETE CASCADE,
    title       text NOT NULL,
    body        text NOT NULL,
    tags        text[] DEFAULT '{}',
    published   boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- RLS
ALTER TABLE support_tickets        ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_ticket_replies ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_kb_articles    ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_iso_support_tickets ON support_tickets
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_iso_kb_articles ON support_kb_articles
    USING (tenant_id IS NULL OR
           tenant_id = current_setting('app.current_tenant_id', true)::uuid);
