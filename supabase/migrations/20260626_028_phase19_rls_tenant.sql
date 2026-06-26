-- Phase 19: Multi-Tenant RLS Migration
-- 20260626_028_phase19_rls_tenant.sql
BEGIN;

CREATE OR REPLACE FUNCTION set_app_tenant(p_tenant_id TEXT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
  PERFORM set_config('app.current_tenant_id', p_tenant_id, TRUE);
END;
$$;

CREATE OR REPLACE FUNCTION current_tenant_id()
RETURNS TEXT LANGUAGE sql STABLE AS $$
  SELECT current_setting('app.current_tenant_id', TRUE);
$$;

CREATE OR REPLACE FUNCTION is_app_admin()
RETURNS BOOLEAN LANGUAGE sql STABLE AS $$
  SELECT current_setting('app.current_role', TRUE) IN ('admin', 'super_admin');
$$;

-- licenses
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='licenses'
      AND column_name='tenant_id'
  ) THEN
    ALTER TABLE public.licenses ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_licenses_tenant_id ON public.licenses (tenant_id);
ALTER TABLE public.licenses ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS licenses_tenant_isolation ON public.licenses;
CREATE POLICY licenses_tenant_isolation ON public.licenses
  USING (tenant_id = current_tenant_id() OR is_app_admin() OR current_user = 'service_role')
  WITH CHECK (tenant_id = current_tenant_id() OR is_app_admin() OR current_user = 'service_role');

-- billing_subscriptions
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='billing_subscriptions'
      AND column_name='tenant_id'
  ) THEN
    ALTER TABLE public.billing_subscriptions ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_billing_sub_tenant_id ON public.billing_subscriptions (tenant_id);
ALTER TABLE public.billing_subscriptions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS billing_sub_tenant_isolation ON public.billing_subscriptions;
CREATE POLICY billing_sub_tenant_isolation ON public.billing_subscriptions
  USING (tenant_id = current_tenant_id() OR is_app_admin() OR current_user = 'service_role')
  WITH CHECK (tenant_id = current_tenant_id() OR is_app_admin() OR current_user = 'service_role');

-- billing_invoices
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='billing_invoices'
      AND column_name='tenant_id'
  ) THEN
    ALTER TABLE public.billing_invoices ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_billing_inv_tenant_id ON public.billing_invoices (tenant_id);
ALTER TABLE public.billing_invoices ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS billing_inv_tenant_isolation ON public.billing_invoices;
CREATE POLICY billing_inv_tenant_isolation ON public.billing_invoices
  USING (tenant_id = current_tenant_id() OR is_app_admin() OR current_user = 'service_role')
  WITH CHECK (tenant_id = current_tenant_id() OR is_app_admin() OR current_user = 'service_role');

-- execution_orders
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='execution_orders'
      AND column_name='tenant_id'
  ) THEN
    ALTER TABLE public.execution_orders ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_exec_orders_tenant_id ON public.execution_orders (tenant_id);
ALTER TABLE public.execution_orders ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS exec_orders_tenant_isolation ON public.execution_orders;
CREATE POLICY exec_orders_tenant_isolation ON public.execution_orders
  USING (tenant_id = current_tenant_id() OR is_app_admin() OR current_user = 'service_role')
  WITH CHECK (tenant_id = current_tenant_id() OR is_app_admin() OR current_user = 'service_role');

-- audit_log
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='audit_log') THEN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='audit_log' AND column_name='tenant_id') THEN
      ALTER TABLE public.audit_log ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
    END IF;
    ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
  END IF;
END $$;

DROP POLICY IF EXISTS audit_log_tenant_read ON public.audit_log;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='audit_log') THEN
    EXECUTE $pol$CREATE POLICY audit_log_tenant_read ON public.audit_log FOR SELECT
      USING (tenant_id = current_tenant_id() OR is_app_admin() OR current_user = 'service_role')$pol$;
  END IF;
END $$;

-- refresh_tokens
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='refresh_tokens') THEN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='refresh_tokens' AND column_name='tenant_id') THEN
      ALTER TABLE public.refresh_tokens ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
    END IF;
    ALTER TABLE public.refresh_tokens ENABLE ROW LEVEL SECURITY;
  END IF;
END $$;

DROP POLICY IF EXISTS refresh_tokens_tenant ON public.refresh_tokens;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='refresh_tokens') THEN
    EXECUTE $pol$CREATE POLICY refresh_tokens_tenant ON public.refresh_tokens
      USING (tenant_id = current_tenant_id() OR is_app_admin() OR current_user = 'service_role')
      WITH CHECK (tenant_id = current_tenant_id() OR is_app_admin() OR current_user = 'service_role')$pol$;
  END IF;
END $$;

-- Admin global view
CREATE OR REPLACE VIEW public.vw_admin_all_licenses AS
SELECT l.*, l.tenant_id AS _tenant_label
FROM public.licenses l
WHERE is_app_admin() OR current_user = 'service_role';

COMMENT ON VIEW public.vw_admin_all_licenses IS 'P19-SQL-4: Admin-only cross-tenant license view.';

-- Tenant data summary view
CREATE OR REPLACE VIEW public.vw_my_tenant_data AS
SELECT 'license' AS data_type, id::TEXT AS record_id, user_id::TEXT AS owner_id, tenant_id, created_at
FROM public.licenses WHERE tenant_id = current_tenant_id()
UNION ALL
SELECT 'subscription', id::TEXT, user_id::TEXT, tenant_id, created_at
FROM public.billing_subscriptions WHERE tenant_id = current_tenant_id()
UNION ALL
SELECT 'invoice', id::TEXT, user_id::TEXT, tenant_id, created_at
FROM public.billing_invoices WHERE tenant_id = current_tenant_id();

COMMENT ON VIEW public.vw_my_tenant_data IS 'P19-SQL-8: RLS-filtered tenant data summary.';

-- Self-validation
DO $$
DECLARE missing_fn TEXT;
BEGIN
  SELECT routine_name INTO missing_fn FROM information_schema.routines
  WHERE routine_schema='public' AND routine_name='set_app_tenant';
  IF missing_fn IS NULL THEN
    RAISE EXCEPTION 'P19-VALIDATE: set_app_tenant() missing';
  END IF;
END $$;

COMMIT;
