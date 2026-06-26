-- ======================================================================
-- Phase 10 -- Billing & Subscription Lifecycle
-- Migration: 20260626_026_phase10_billing.sql
-- =======================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS billing_plans (
    plan_id         TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    price_usd       INT  NOT NULL DEFAULT 0,
    price_irr       BIGINT NOT NULL DEFAULT 0,
    duration_days   INT  NOT NULL,
    trial_days      INT  NOT NULL DEFAULT 0,
    device_limit    INT  NOT NULL DEFAULT 1,
    features        TEXT[] NOT NULL DEFAULT '{0}',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO billing_plans VALUES
  ('trial','Trial',0,0,7,7,1,ARRAY['signals_read'],TRUE,NOW(),NOW()),
  ('basic','Basic',1900,7000000,30,0,1,ARRAY['signals_read','signals_write','manual_trade'],TRUE,NOW(),NOW()),
  ('pro','Pro',4900,18000000,90,0,2,ARRAY['signals_read','signals_write','manual_trade','auto_trade','analytics'],TRUE,NOW(),NOW()),
  ('enterprise','Enterprise',14900,55000000,365,0,10,ARRAY['signals_read','signals_write','manual_trade','auto_trade','analytics','api_access','white_label'],TRUE,NOW(),NOW()),
  ('lifetime','Lifetime',49900,180000000,36500,0,5,ARRAY['signals_read','signals_write','manual_trade','auto_trade','analytics','api_access'],TRUE,NOW(),NOW())
ON CONFLICT (plan_id) DO NOTHING;

CREATE TYPE IF NOT EXISTS subscription_status AS ENUM ('trial','active','past_due','suspended','expired','cancelled','revoked');

CREATE TABLE IF NOT EXISTS billing_subscriptions (
    sub_id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    plan_id         TEXT NOT NULL REFERENCES billing_plans(plan_id),
    status          subscription_status NOT NULL DEFAULT 'trial',
    license_key     TEXT,
    expires_at      TIMESTAMPTZ,
    trial_ends_at   TIMESTAMPTZ,
    dunning_count   INT NOT NULL DEFAULT 0,
    cancelled_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id)
);

CREATE TYPE IF NOT EXISTS payment_status AS ENUM ('pending','success','failed','refunded','cancelled');
CREATE TYPE IF NOT EXISTS payment_provider AS ENUM ('stripe','zarinpal','manual','mock');

CREATE TABLE IF NOT EXISTS billing_invoices (
    invoice_id       TEXT PRIMARY KEY DEFAULT 'INV-' || upper(substr(gen_random_uuid()::TEXT,1,10)),
    user_id          UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    plan_id          TEXT NOT NULL REFERENCES billing_plans(plan_id),
    provider         payment_provider NOT NULL,
    provider_ref     TEXT,
    idempotency_key  TEXT NOT NULL,
    amount           BIGINT NOT NULL,
    currency         TEXT NOT NULL DEFAULT 'USD',
    status           payment_status NOT NULL DEFAULT 'pending',
    error            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at          TIMESTAMPTZ,
    UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS billing_webhook_events (
    event_id     TEXT PRIMARY KEY,
    provider     payment_provider NOT NULL,
    event_type   TEXT NOT NULL,
    provider_ref TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    processed_at TIMESTAMPT@ NOT NULL DEFAULT NOW(),
    invoice_id   TEXT REFERENCES billing_invoices(invoice_id)
);

CREATE TABLE IF NOT EXISTS billing_audit_log (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor       TEXT NOT NULL DEFAULT 'system',
    user_id     UUID REFERENCES auth.users(id),
    event       TEXT NOT NULL,
    detail      JSONB,
    ip          TEXT
);

COMMIT;