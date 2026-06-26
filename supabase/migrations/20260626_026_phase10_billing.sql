-- =============================================================
-- PHASE 10 — Billing & Subscription Lifecycle Schema
-- Migration: 20260626_026_phase10_billing.sql
-- =============================================================

-- ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
-- Subscriptions table
-- ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

CREATE TABLE IF NOT EXISTS subscriptions (
    sub_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    plan_id         TEXT NOT NULL CHECK (plan_id IN ('trial', 'basic', 'pro', 'enterprise', 'lifetime')),
    status          TEXT NOT NULL DEFAULT 'trial'
                    CHECK (status IN ('trial', 'active', 'past_due', 'suspended', 'expired', 'cancelled', 'revoked')),
    license_key     TEXT,
    expires_at      TIMESTAMPTZ,
    trial_ends_at   TIMESTAMPTZ,
    cancelled_at    TIMESTAMPTZ,
    dunning_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user
    ON subscriptions(user_id);

CREATE INDEX IF NOT EXISTS idx_subscriptions_status
    ON subscriptions(status);

CREATE INDEX IF NOT EXISTS idx_subscriptions_expiry
    ON subscriptions(expires_at) WHERE status IN ('active', 'trial');


-- ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
-- Invoices table
-- ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    sub_id          UUID REFERENCES subscriptions(sub_id),
    plan_id         TEXT NOT NULL,
    amount          INTEGER NOT NULL CHECK (amount >= 0),
    currency        TEXT NOT NULL DEFAULT 'USD' CHECK (currency IN ('USD', 'EUR', 'IRR', 'IRT')),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'paid', 'failed', 'refunded')),
    provider        TEXT NOT NULL CHECK (provider IN ('stripe', 'zarinpal', 'manual', 'mock')),
    provider_ref    TEXT,
    idempotency_key TEXT UNIQUE,
    paid_at         TIMESTAMPTZ,
    error           TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invoices_user
    ON invoices(user_id);

CREATE INDEX IF NOT EXISTS idx_invoices_provider_ref
    ON invoices(provider_ref) WHERE provider_ref IS NOT NULL;


-- ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
-- Webhook events (audit log)
-- ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

CREATE TABLE IF NOT EXISTS billing_webhook_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id    TEXT UNIQUE NOT NULL,        -- provider event ID (idempotency)
    event_type  TEXT NOT NULL,
    provider    TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}',
    accepted    BOOLEAL� NOT NULL DEFAULT false,
    duplicate   BOOLEAN NOT NULL DEFAULT false,
    error       TEXT,
    invoice_id  UUID REFERENCES invoices(invoice_id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_webhook_event_id
    ON billing_webhook_events(event_id);


-- ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
-- RLS Policies
-- ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices      ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_webhook_events ENABLE ROW LEVEL SECURITY;

-- Customer sees only own subscription
CREATE POLICY subscriptions_user_policy ON subscriptions
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY subscriptions_admin_policy ON subscriptions
    FOR ALL USING (auth.jpt_claim('app_role') IN ('admin', 'super_admin'));

-- Customer sees only own invoices
CREATE POLICY invoices_user_policy ON invoices
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY invoices_admin_policy ON invoices
    FOR ALL USING (auth.jwt_claim('app_role') IN ('admin', 'super_admin'));

-- Webhook events: admin only
CREATE POLICY webhook_admin_policy ON billing_webhook_events
    FOR ALL USING (auth.jwt_claim('app_role') IN ('admin', 'super_admin'));


-- ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
-- Auto updated_at trigger
-- ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

CREATE OR REPLACE FUNCTION update_updated_at()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_credits_updated_at
    BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
