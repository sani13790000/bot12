-- migration_025.sql - Phase T service layer hardening
-- T-22: unique index for signal idempotency
CREATE UNIQUE INDEX IF NOT EXISTS uidx_signals_id_user ON signals (id, user_id);
-- T-26: prevent duplicate trades per signal per user
CREATE UNIQUE INDEX IF NOT EXISTS uidx_trades_signal_user ON trades (signal_id, user_id) WHERE signal_id IS NOT NULL;
-- T-20: active non-expired signals per user
CREATE INDEX IF NOT EXISTS idx_signals_active_user ON signals (user_id, expires_at DESC) WHERE status = 'ACTIVE';
-- T-27: paginated trade history
CREATE INDEX IF NOT EXISTS idx_trades_user_opened ON trades (user_id, opened_at DESC);
-- T-25: open trades only
CREATE INDEX IF NOT EXISTS idx_trades_user_open ON trades (user_id) WHERE status = 'OPEN';
-- T-29: auto-set updated_at
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_trades_updated_at') THEN
    CREATE TRIGGER trg_trades_updated_at BEFORE UPDATE ON trades FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_signals_updated_at') THEN
    CREATE TRIGGER trg_signals_updated_at BEFORE UPDATE ON signals FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
END; $$;
-- T-13: account settings for initial balance
CREATE TABLE IF NOT EXISTS account_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  initial_balance NUMERIC(18,2) NOT NULL DEFAULT 10000.0,
  UNIQUE(user_id)
);
ALTER TABLE IF EXISTS account_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS account_settings_owner ON account_settings FOR ALL USING (user_id = auth.uid());
