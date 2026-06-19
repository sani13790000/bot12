-- Down migration for 014_users_table.sql
-- WARNING: This will DELETE all user data. Use with caution.

BEGIN;

DROP TRIGGER IF EXISTS trg_users_updated_at ON public.users;
DROP FUNCTION IF EXISTS public.set_updated_at();
DROP TABLE IF EXISTS public.refresh_tokens CASCADE;
DROP TABLE IF EXISTS public.users CASCADE;

COMMIT;
