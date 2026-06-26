-- ======================================================================
-- Phase 10 -- Billing & Subscription Lifecycle
-- Migration: 20260626_026_phase10_billing.sql
-- ======================================================================

-- 1. Plans reference table
CREATE TABLE IF NOT EXISTS billing_plans (
    plan_id         TEXT        PRIMARY KEY,
    label           TEXT        NOT NULL,
    price_usd       INTEGER     NOT NULL DEFAULT 0,
    price_irr       BIGINT      NOT NULL DEFAULT 0,
    duration_days   INTEGER     NOT NULL DEFAULT 30,
    features        JSONB       NOT NULL DEFAULT '[]',
    max_devices     INTEGER     NOT NULL DEFAULT 1,
    max_positions   INTEGER     NOT NULL DEFAULT 10,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO billing_plans (plan_id, label, price_usd, price_irr, duration_days, features, max_devices, max_positions)
VALUES
  ('trial',  'Trial',      0,         0,           14,  '["signals_read","signals_write","dashboard"]', 1, 3),
  ('basic',  'Basic',      2900,      4900000,     30,  '["signals_read","signals_write","dashboard","mt5"]', 2, 10),
  ('pro',    'Pro',        7900,      12900000,    30,  '["signals_read","signals_write","dashboard","mt5","ai","analytics"]', 5, 50),
  ('vip',    'VIP',        14900,     24900000,    30,  '["signals_read","signals_write","dashboard","mt5","ai","analytics","institutional"]', 10, 200),
  ('annual', 'Annual Pro', 79900,     129900000,   365, '["signals_read","signals_write","dashboard","mt5","ai","analytics","institutional"]', 10, 500)
ON CONFLICT (plan_id) DO NOTHING;

-- 2. Invoices table
CREATE TABLE IF NOT EXISTS billing_invoices (
    invoice_id      TEXT        PRIMARY KEY,
    user_id         UUID        NOT NULL REFERENCES auth.users(id),
    plan_id         TEXT        NOT NULL REFERENCES billing_plans(plan_id),
    amount          BIGINT      NOT NULL,
    currency        TEXT        NOT NULL DEFAULT 'usd',
    provider        TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'pending',
    checkout_url    TEXT,
    idempotency_key TEXT        UNIQUE NOT NULL,
    raw_data        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at    TIMESTAMPTZ,
    CONSTRAINT chk_invoice_status CHECK (
        status IN ('pending','succeeded','failed','refunded','cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON billing_invoices(user_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status  ON billing_invoices(status);

-- 3. Subscriptions table
CREATE TABLE IF NOT EXISTS billing_subscriptions (
    sub_id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL UNIQUE REFERENCES auth.users(id),
    plan_id         TEXT        NOT NULL REFERENCES billing_plans(plan_id),
    status          TEXT        NOT NULL DEFAULT 'trial',
    license_key     TEXT,
    dunning_count   INTEGER     NOT NULL DEFAULT 0,
    expires_at      TIMESTAMPTZ,
    trial_ends_at   TIMESTAMPTZ,
    cancelled_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_sub_status CHECK (
        status IN ('trial','active','past_due','suspended','expired','cancelled','revoked')
    )
);

CREATE INDEX IF NOT EXISTS idx_subs_status     ON billing_subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subs_expires_at ON billing_subscriptions(expires_at);

-- 4. Subscription transitions (FSM audit trail)
CREATE TABLE IF NOT EXISTS billing_sub_transitions (
    id          BIGSERIAL   PRIMARY KEY,
    sub_id      UUID        NOT NULL REFERENCES billing_subscriptions(sub_id),
    user_id     UUID        NOT NULL,
    from_status TEXT        NOT NULL,
    to_status   TEXT        NOT NULL,
    reason      TEXT,
    actor       TEXT        DEFAULT 'system',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sub_transitions_sub_id ON billing_sub_transitions(sub_id);

-- 5. Webhook events (idempotency log)
CREATE TABLE IF NOT EXISTS billing_webhook_events (
    event_id     TEXT        PRIMARY KEY,
    provider     TEXT        NOT NULL,
    event_type   TEXT        NOT NULL,
    invoice_id   TEXT,
    payload_hash TEXT        NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duplicate    BOOLEAN     NOT NULL DEFAULT FALSE,
    error        TEXT
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_invoice ON billing_webhook_events(invoice_id);

-- 6. FSM trigger: auto-update updated_at
CREATE OR REPLACE FUNCTION billing_sub_update_ts()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_billing_sub_updated_at
    BEFORE UPDATE ON billing_subscriptions
    FOR EACH ROW EXECUTE FUNCTION billing_sub_update_ts();

-- 7. RLS Policies
ALTER TABLE billing_invoices      ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY billing_invoices_own_user ON billing_invoices
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY billing_subscriptions_own_user ON billing_subscriptions
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY billing_invoices_service ON billing_invoices
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY billing_subscriptions_service ON billing_subscriptions
    FOR ALL USING (auth.role() = 'service_role');
