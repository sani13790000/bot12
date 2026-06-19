-- Down migration for 013_institutional_modules.sql

BEGIN;

DROP TABLE IF EXISTS public.institutional_monte_carlo CASCADE;
DROP TABLE IF EXISTS public.institutional_trades CASCADE;
DROP TABLE IF EXISTS public.institutional_backtests CASCADE;

COMMIT;
