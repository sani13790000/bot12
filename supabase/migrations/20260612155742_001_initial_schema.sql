-- =====================================================
-- اسکیمای اولیه اکوسیستم معامله‌گری MT5
-- نسخه: 1.0
-- تاریخ: 2026-06-12
-- =====================================================

-- فعال‌سازی پسوند UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- جدول پروفایل کاربران (در کنار auth.users)
-- =====================================================
CREATE TABLE public.user_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    telegram_id BIGINT UNIQUE,
    telegram_username VARCHAR(255),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(20),
    country VARCHAR(50),
    timezone VARCHAR(50) DEFAULT 'UTC',
    language VARCHAR(10) DEFAULT 'fa',
    avatar_url TEXT,
    role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('user', 'trader', 'admin', 'super_admin')),
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'banned', 'deleted')),
    mt5_account_linked BOOLEAN DEFAULT FALSE,
    mt5_account_number BIGINT,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- جدول تنظیمات کاربر
-- =====================================================
CREATE TABLE public.user_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    
    -- تنظیمات معاملاتی
    default_symbol VARCHAR(20) DEFAULT 'XAUUSD',
    default_lot DECIMAL(10,4) DEFAULT 0.01,
    max_lot DECIMAL(10,4) DEFAULT 1.0,
    risk_per_trade DECIMAL(5,2) DEFAULT 2.0 CHECK (risk_per_trade > 0 AND risk_per_trade <= 10),
    max_daily_trades INTEGER DEFAULT 5,
    max_daily_loss DECIMAL(10,2) DEFAULT 5.0,
    max_drawdown DECIMAL(10,2) DEFAULT 20.0,
    
    -- تنظیمات استاپ و تی‌پی
    default_sl_pips DECIMAL(10,2) DEFAULT 50.0,
    default_tp_pips DECIMAL(10,2) DEFAULT 100.0,
    use_trailing_stop BOOLEAN DEFAULT TRUE,
    trailing_stop_pips DECIMAL(10,2) DEFAULT 30.0,
    
    -- تنظیمات تحلیل
    enabled_timeframes JSONB DEFAULT '["M15", "H1", "H4", "D1"]'::jsonb,
    primary_timeframe VARCHAR(10) DEFAULT 'H1',
    use_multi_timeframe BOOLEAN DEFAULT TRUE,
    min_entry_score DECIMAL(5,2) DEFAULT 65.0,
    
    -- تنظیمات اعلان
    telegram_notifications BOOLEAN DEFAULT TRUE,
    notify_on_entry BOOLEAN DEFAULT TRUE,
    notify_on_exit BOOLEAN DEFAULT TRUE,
    notify_on_sl BOOLEAN DEFAULT TRUE,
    notify_on_tp BOOLEAN DEFAULT TRUE,
    notify_on_session BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id)
);

-- =====================================================
-- جدول لایسنس‌ها
-- =====================================================
CREATE TABLE public.licenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    license_key VARCHAR(64) UNIQUE NOT NULL,
    user_id UUID REFERENCES public.user_profiles(id) ON DELETE SET NULL,
    
    license_type VARCHAR(30) NOT NULL CHECK (license_type IN (
        'trial', 'basic', 'professional', 'enterprise', 'lifetime', 'developer'
    )),
    
    status VARCHAR(20) DEFAULT 'inactive' CHECK (status IN ('inactive', 'active', 'expired', 'revoked', 'suspended')),
    
    activated_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    last_validated_at TIMESTAMPTZ,
    
    max_accounts INTEGER DEFAULT 1,
    max_symbols INTEGER DEFAULT 1,
    max_trades_per_day INTEGER DEFAULT 10,
    
    hardware_id VARCHAR(255),
    mt5_account_binding BIGINT[],
    
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- جدول ویژگی‌های لایسنس
-- =====================================================
CREATE TABLE public.license_features (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    license_id UUID NOT NULL REFERENCES public.licenses(id) ON DELETE CASCADE,
    feature_code VARCHAR(50) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    limit_value INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(license_id, feature_code)
);

-- =====================================================
-- جدول معاملات
-- =====================================================
CREATE TABLE public.trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    signal_id UUID,
    
    mt5_ticket BIGINT UNIQUE,
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('buy', 'sell')),
    trade_type VARCHAR(20) DEFAULT 'market' CHECK (trade_type IN ('market', 'limit', 'stop')),
    
    entry_price DECIMAL(20,8) NOT NULL,
    exit_price DECIMAL(20,8),
    lot_size DECIMAL(10,4) NOT NULL,
    
    stop_loss DECIMAL(20,8),
    take_profit DECIMAL(20,8),
    
    profit_pips DECIMAL(10,2),
    profit_money DECIMAL(12,4),
    
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'open', 'closed', 'cancelled')),
    close_reason VARCHAR(30) CHECK (close_reason IN ('manual', 'sl', 'tp', 'trailing_stop', 'stop_out')),
    
    entry_score DECIMAL(5,2),
    smc_score DECIMAL(5,2),
    price_action_score DECIMAL(5,2),
    total_score DECIMAL(5,2),
    
    analysis_summary JSONB,
    
    opened_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    
    session VARCHAR(20) CHECK (session IN ('sydney', 'tokyo', 'london', 'new_york')),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- جدول سیگنال‌ها
-- =====================================================
CREATE TABLE public.signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.user_profiles(id) ON DELETE SET NULL,
    
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    
    signal_type VARCHAR(20) NOT NULL CHECK (signal_type IN ('entry', 'exit', 'close')),
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('buy', 'sell', 'neutral')),
    strength VARCHAR(20) NOT NULL CHECK (strength IN ('weak', 'moderate', 'strong', 'very_strong')),
    
    suggested_entry DECIMAL(20,8),
    suggested_sl DECIMAL(20,8),
    suggested_tp DECIMAL(20,8),
    stop_loss_pips DECIMAL(10,2),
    take_profit_pips DECIMAL(10,2),
    
    total_score DECIMAL(5,2) NOT NULL,
    smc_score DECIMAL(5,2),
    price_action_score DECIMAL(5,2),
    liquidity_score DECIMAL(5,2),
    session_score DECIMAL(5,2),
    
    trigger_reasons JSONB,
    smc_data JSONB,
    price_action_data JSONB,
    
    status VARCHAR(20) DEFAULT 'generated' CHECK (status IN ('generated', 'sent', 'executed', 'expired', 'cancelled')),
    trade_id UUID REFERENCES public.trades(id) ON DELETE SET NULL,
    
    sent_to_telegram BOOLEAN DEFAULT FALSE,
    telegram_message_id BIGINT,
    
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    valid_until TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    
    metadata JSONB DEFAULT '{}'::jsonb
);

-- =====================================================
-- جدول تحلیل SMC
-- =====================================================
CREATE TABLE public.smc_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.user_profiles(id) ON DELETE SET NULL,
    signal_id UUID REFERENCES public.signals(id) ON DELETE SET NULL,
    
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    
    -- ساختار بازار
    trend VARCHAR(20) CHECK (trend IN ('bullish', 'bearish', 'neutral')),
    last_structure_event VARCHAR(20) CHECK (last_structure_event IN ('bos', 'choch', 'mss')),
    structure_direction VARCHAR(10),
    structure_level DECIMAL(20,8),
    
    -- نقدینگی
    liquidity_swept BOOLEAN DEFAULT FALSE,
    sweep_type VARCHAR(20),
    sweep_level DECIMAL(20,8),
    
    -- بلاک‌ها
    active_blocks JSONB DEFAULT '[]'::jsonb,
    
    -- FVG
    active_fvgs JSONB DEFAULT '[]'::jsonb,
    
    -- امتیاز
    total_score DECIMAL(5,2),
    
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- جدول سشن‌های معاملاتی
-- =====================================================
CREATE TABLE public.trading_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_name VARCHAR(30) UNIQUE NOT NULL CHECK (session_name IN ('sydney', 'tokyo', 'london', 'new_york')),
    
    open_time TIME NOT NULL,
    close_time TIME NOT NULL,
    
    killzone_start TIME,
    killzone_end TIME,
    
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 1,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- داده‌های پیش‌فرض سشن‌ها
INSERT INTO public.trading_sessions (session_name, open_time, close_time, killzone_start, killzone_end, priority) VALUES
('sydney', '22:00', '07:00', '22:30', '23:30', 1),
('tokyo', '00:00', '09:00', '00:30', '02:00', 2),
('london', '08:00', '17:00', '08:00', '11:00', 3),
('new_york', '13:00', '22:00', '13:30', '16:00', 4);

-- =====================================================
-- جدول آمار روزانه
-- =====================================================
CREATE TABLE public.daily_statistics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    
    stat_date DATE NOT NULL,
    
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    win_rate DECIMAL(5,2),
    
    gross_profit DECIMAL(12,4) DEFAULT 0,
    gross_loss DECIMAL(12,4) DEFAULT 0,
    net_profit DECIMAL(12,4) DEFAULT 0,
    
    max_drawdown DECIMAL(10,2) DEFAULT 0,
    avg_entry_score DECIMAL(5,2),
    
    signals_generated INTEGER DEFAULT 0,
    signals_executed INTEGER DEFAULT 0,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id, stat_date)
);

-- =====================================================
-- جدود فعالیت‌ها
-- =====================================================
CREATE TABLE public.activity_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.user_profiles(id) ON DELETE SET NULL,
    
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50),
    entity_id UUID,
    
    details JSONB DEFAULT '{}'::jsonb,
    ip_address INET,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- ایندکس‌ها
-- =====================================================
CREATE INDEX idx_user_profiles_telegram_id ON public.user_profiles(telegram_id);
CREATE INDEX idx_user_profiles_user_id ON public.user_profiles(user_id);
CREATE INDEX idx_user_profiles_status ON public.user_profiles(status);

CREATE INDEX idx_licenses_license_key ON public.licenses(license_key);
CREATE INDEX idx_licenses_user_id ON public.licenses(user_id);
CREATE INDEX idx_licenses_status ON public.licenses(status);
CREATE INDEX idx_licenses_expires_at ON public.licenses(expires_at);

CREATE INDEX idx_trades_user_id ON public.trades(user_id);
CREATE INDEX idx_trades_symbol ON public.trades(symbol);
CREATE INDEX idx_trades_status ON public.trades(status);
CREATE INDEX idx_trades_opened_at ON public.trades(opened_at);
CREATE INDEX idx_trades_user_status ON public.trades(user_id, status);

CREATE INDEX idx_signals_user_id ON public.signals(user_id);
CREATE INDEX idx_signals_symbol ON public.signals(symbol);
CREATE INDEX idx_signals_status ON public.signals(status);
CREATE INDEX idx_signals_generated_at ON public.signals(generated_at);
CREATE INDEX idx_signals_total_score ON public.signals(total_score DESC);

CREATE INDEX idx_daily_statistics_user_date ON public.daily_statistics(user_id, stat_date);
CREATE INDEX idx_activity_logs_user_id ON public.activity_logs(user_id);
CREATE INDEX idx_activity_logs_created_at ON public.activity_logs(created_at);

-- =====================================================
-- فعال‌سازی RLS
-- =====================================================
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.licenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.license_features ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.smc_analysis ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_statistics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_logs ENABLE ROW LEVEL SECURITY;

-- =====================================================
-- سیاست‌های RLS
-- =====================================================

-- user_profiles
CREATE POLICY "select_own_profile" ON public.user_profiles FOR SELECT
    TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "insert_own_profile" ON public.user_profiles FOR INSERT
    TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "update_own_profile" ON public.user_profiles FOR UPDATE
    TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- user_settings
CREATE POLICY "select_own_settings" ON public.user_settings FOR SELECT
    TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "insert_own_settings" ON public.user_settings FOR INSERT
    TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "update_own_settings" ON public.user_settings FOR UPDATE
    TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- trades
CREATE POLICY "select_own_trades" ON public.trades FOR SELECT
    TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "insert_own_trades" ON public.trades FOR INSERT
    TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "update_own_trades" ON public.trades FOR UPDATE
    TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- signals
CREATE POLICY "select_own_signals" ON public.signals FOR SELECT
    TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "insert_own_signals" ON public.signals FOR INSERT
    TO authenticated WITH CHECK (auth.uid() = user_id OR user_id IS NULL);

-- daily_statistics
CREATE POLICY "select_own_stats" ON public.daily_statistics FOR SELECT
    TO authenticated USING (auth.uid() = user_id);

-- =====================================================
-- تابع به‌روزرسانی updated_at
-- =====================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- تریگرها
CREATE TRIGGER update_user_profiles_updated_at
    BEFORE UPDATE ON public.user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_settings_updated_at
    BEFORE UPDATE ON public.user_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_licenses_updated_at
    BEFORE UPDATE ON public.licenses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_trades_updated_at
    BEFORE UPDATE ON public.trades
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- تابع محاسبه آمار روزانه
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_daily_statistics(
    p_user_id UUID,
    p_date DATE
) RETURNS void AS $$
DECLARE
    v_stats RECORD;
BEGIN
    SELECT
        COUNT(*) as total_trades,
        COUNT(*) FILTER (WHERE profit_money > 0) as winning_trades,
        COUNT(*) FILTER (WHERE profit_money < 0) as losing_trades,
        COALESCE(SUM(profit_money) FILTER (WHERE profit_money > 0), 0) as gross_profit,
        COALESCE(SUM(profit_money) FILTER (WHERE profit_money < 0), 0) as gross_loss,
        COALESCE(SUM(profit_money), 0) as net_profit,
        AVG(entry_score) as avg_entry_score
    INTO v_stats
    FROM public.trades
    WHERE user_id = p_user_id
      AND status = 'closed'
      AND DATE(closed_at) = p_date;

    INSERT INTO public.daily_statistics (
        user_id, stat_date, total_trades, winning_trades, losing_trades,
        gross_profit, gross_loss, net_profit, win_rate, avg_entry_score
    ) VALUES (
        p_user_id, p_date, v_stats.total_trades, v_stats.winning_trades, v_stats.losing_trades,
        v_stats.gross_profit, v_stats.gross_loss, v_stats.net_profit,
        CASE WHEN v_stats.total_trades > 0 
             THEN ROUND((v_stats.winning_trades::DECIMAL / v_stats.total_trades) * 100, 2)
             ELSE 0 END,
        v_stats.avg_entry_score
    )
    ON CONFLICT (user_id, stat_date) DO UPDATE SET
        total_trades = EXCLUDED.total_trades,
        winning_trades = EXCLUDED.winning_trades,
        losing_trades = EXCLUDED.losing_trades,
        gross_profit = EXCLUDED.gross_profit,
        gross_loss = EXCLUDED.gross_loss,
        net_profit = EXCLUDED.net_profit,
        win_rate = EXCLUDED.win_rate,
        avg_entry_score = EXCLUDED.avg_entry_score;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;