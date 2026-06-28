-- Phase 30: Compliance, Legal & User-Facing Disclosures
-- Migration 039
-- Tables: legal_documents, consent_records, retention_policies,
--         refund_requests, cancellation_requests, compliance_audit_log

BEGIN;

-- 1. legal_documents
CREATE TABLE IF NOT EXISTS legal_documents (
    doc_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_type        TEXT NOT NULL,
    version         TEXT NOT NULL,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    content_hash    CHAR(64) NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('draft','active','superseded','archived')),
    effective_date  TIMESTAMPTZ NOT NULL,
    jurisdiction    TEXT NOT NULL DEFAULT 'GLOBAL',
    language        TEXT NOT NULL DEFAULT 'en',
    created_by      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_by   UUID REFERENCES legal_documents(doc_id),
    UNIQUE (doc_type, version, jurisdiction)
);

-- 2. consent_records
CREATE TABLE IF NOT EXISTS consent_records (
    consent_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    tenant_id       UUID NOT NULL,
    doc_id          UUID NOT NULL REFERENCES legal_documents(doc_id),
    doc_type        TEXT NOT NULL,
    doc_version     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'accepted'
                        CHECK (status IN ('pending','accepted','declined','expired','withdrawn')),
    ip_address      INET,
    user_agent      TEXT,
    accepted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ,
    withdrawn_at    TIMESTAMPTZ,
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. retention_policies
CREATE TABLE IF NOT EXISTS retention_policies (
    policy_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    category        TEXT NOT NULL,
    retain_days     INT NOT NULL CHECK (retain_days > 0),
    legal_basis     TEXT NOT NULL,
    jurisdiction    TEXT NOT NULL DEFAULT 'GLOBAL',
    auto_delete     BOOLEAN NOT NULL DEFAULT TRUE,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, category)
);

-- 4. refund_requests
CREATE TABLE IF NOT EXISTS refund_requests (
    request_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    tenant_id       UUID NOT NULL,
    amount_cents    INT NOT NULL CHECK (amount_cents > 0),
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    reason          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','approved','denied')),
    purchase_at     TIMESTAMPTZ NOT NULL,
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ,
    resolved_by     TEXT,
    denial_reason   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. cancellation_requests
CREATE TABLE IF NOT EXISTS cancellation_requests (
    request_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    tenant_id       UUID NOT NULL,
    reason          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','confirmed','cancelled')),
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_at    TIMESTAMPTZ NOT NULL,
    notice_days     INT NOT NULL DEFAULT 30,
    confirmed_at    TIMESTAMPTZ,
    data_deletion   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 6. compliance_audit_log (immutable HMAC chain)
CREATE TABLE IF NOT EXISTS compliance_audit_log (
    entry_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action          TEXT NOT NULL,
    actor           TEXT NOT NULL,
    tenant_id       TEXT NOT NULL DEFAULT 'system',
    detail          JSONB NOT NULL DEFAULT '{}',
    reason          TEXT,
    chain_hash      CHAR(64) NOT NULL,
    seq             BIGINT NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Immutable audit log trigger
CREATE OR REPLACE FUNCTION compliance_audit_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'compliance_audit_log is immutable -- UPDATE not allowed';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'compliance_audit_log is immutable -- DELETE not allowed';
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_compliance_audit_immutable ON compliance_audit_log;
CREATE TRIGGER trg_compliance_audit_immutable
    BEFORE UPDATE OR DELETE ON compliance_audit_log
    FOR EACH ROW EXECUTE FUNCTION compliance_audit_immutable();

-- Indexes
CREATE INDEX IF NOT EXISTS idx_legal_documents_type_status ON legal_documents (doc_type, status);
CREATE INDEX IF NOT EXISTS idx_legal_documents_effective ON legal_documents (effective_date DESC);
CREATE INDEX IF NOT EXISTS idx_consent_records_user_doc ON consent_records (user_id, doc_type, tenant_id);
CREATE INDEX IF NOT EXISTS idx_consent_records_tenant ON consent_records (tenant_id);
CREATE INDEX IF NOT EXISTS idx_refund_requests_user ON refund_requests (user_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_cancellation_requests_user ON cancellation_requests (user_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_compliance_audit_log_action ON compliance_audit_log (action, tenant_id);
CREATE INDEX IF NOT EXISTS idx_compliance_audit_log_seq ON compliance_audit_log (seq);
CREATE INDEX IF NOT EXISTS idx_compliance_audit_log_ts ON compliance_audit_log (ts DESC);

-- RLS
ALTER TABLE legal_documents           ENABLE ROW LEVEL SECURITY;
ALTER TABLE consent_records           ENABLE ROW LEVEL SECURITY;
ALTER TABLE retention_policies        ENABLE ROW LEVEL SECURITY;
ALTER TABLE refund_requests           ENABLE ROW LEVEL SECURITY;
ALTER TABLE cancellation_requests     ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_audit_log      ENABLE ROW LEVEL SECURITY;

-- Cleanup
CREATE OR REPLACE FUNCTION cleanup_expired_consents() RETURNS INT LANGUAGE plpgsql AS $$
DECLARE deleted_count INT;
BEGIN
    WITH deleted AS (
        UPDATE consent_records SET status = 'expired'
        WHERE status = 'accepted' AND expires_at IS NOT NULL AND expires_at < now()
        RETURNING consent_id
    )
    SELECT COUNT(*) INTO deleted_count FROM deleted;
    RETURN deleted_count;
END;
$$;

-- Views
CREATE OR REPLACE VIEW vw_active_legal_documents AS
    SELECT doc_id, doc_type, version, title, content_hash, status, effective_date, jurisdiction, language, created_at
    FROM legal_documents WHERE status = 'active' ORDER BY doc_type, effective_date DESC;

CREATE OR REPLACE VIEW vw_compliance_audit_summary AS
    SELECT action, COUNT(*) AS event_count, MAX(ts) AS last_event_at
    FROM compliance_audit_log GROUP BY action ORDER BY event_count DESC;

CREATE OR REPLACE VIEW vw_pending_consents AS
    SELECT cr.user_id, cr.tenant_id, cr.doc_type, cr.status, cr.accepted_at, cr.expires_at
    FROM consent_records cr WHERE cr.status IN ('pending','accepted') ORDER BY cr.accepted_at DESC;

-- Seed
INSERT INTO retention_policies (tenant_id, category, retain_days, legal_basis, jurisdiction, description) VALUES
    (NULL,'user_pii',730,'GDPR Art.5','EU','PII 2y'),(NULL,'trading_logs',2555,'MiFID II','EU','Logs 7y'),
    (NULL,'audit_logs',2555,'SOC2/ISO27001','GLOBAL','Audit 7y'),(NULL,'financial_records',2555,'Companies Act','UK','Finance 7y'),
    (NULL,'support_tickets',1095,'Operational','GLOBAL','Support 3y'),(NULL,'marketing_consent',1825,'GDPR Art.7','EU','Mktg 5y'),
    (NULL,'backup_data',90,'Operational','GLOBAL','Backup 90d'),(NULL,'session_data',30,'Security','GLOBAL','Session 30d'),
    (NULL,'kyc_documents',1825,'AML Directive','EU','KYC 5y'),(NULL,'payment_records',2555,'PCI-DSS','GLOBAL','Payment 7y')
ON CONFLICT (tenant_id, category) DO NOTHING;

COMMIT;
