-- Rollback migration 015
BEGIN;
DROP TABLE IF EXISTS login_attempts CASCADE;
DROP TABLE IF EXISTS refresh_tokens CASCADE;
DROP TABLE IF EXISTS revoked_tokens CASCADE;
DROP FUNCTION IF EXISTS cleanup_expired_revoked_tokens();
DROP FUNCTION IF EXISTS cleanup_expired_refresh_tokens();
COMMIT;
