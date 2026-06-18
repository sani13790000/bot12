-- ============================================================================
-- F3 - Partitioning for high-growth tables: market_data_1m and tick_data
-- ============================================================================

-- market_data_1m: partition by range(timestamp) monthly
CREATE TABLE IF NOT EXISTS public.market_data_1m (
    id              BIGSERIAL,
    symbol          VARCHAR(20)   NOT NULL,
    timeframe       VARCHAR(10)   NOT NULL,
    timestamp       TIMESTAMPTZ   NOT NULL,
    open            NUMERIC(18,8) NOT NULL,
    high            NUMERIC(18,8) NOT NULL,
    low             NUMERIC(18,8) NOT NULL,
    close           NUMERIC(18,8) NOT NULL,
    volume          BIGINT        DEFAULT 0,
    source          VARCHAR(50)   DEFAULT 'mt5',
    created_at      TIMESTAMPTZ   DEFAULT NOW(),
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

CREATE INDEX IF NOT EXISTS idx_market_data_symbol_time
    ON public.market_data_1m (symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_market_data_timeframe
    ON public.market_data_1m (timeframe, timestamp DESC);

-- Create monthly partitions for 6 months ahead
DO $$
DECLARE
    y INT;
    m INT;
    start_date DATE;
    end_date DATE;
    part_name TEXT;
BEGIN
    FOR i IN 0..5 LOOP
        start_date := DATE_TRUNC('month', NOW() + (i || ' months')::INTERVAL)::DATE;
        end_date   := (start_date + INTERVAL '1 month')::DATE;
        y := EXTRACT(YEAR FROM start_date)::INT;
        m := EXTRACT(MONTH FROM start_date)::INT;
        part_name := 'market_data_1m_y' || y || '_m' || LPAD(m::TEXT, 2, '0');
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.market_data_1m FOR VALUES FROM (%L) TO (%L)',
            part_name, start_date, end_date
        );
    END LOOP;
END $$;

-- tick_data: partition by range(timestamp) daily
CREATE TABLE IF NOT EXISTS public.tick_data (
    id              BIGSERIAL,
    symbol          VARCHAR(20)   NOT NULL,
    timestamp       TIMESTAMPTZ   NOT NULL,
    bid             NUMERIC(18,8) NOT NULL,
    ask             NUMERIC(18,8) NOT NULL,
    volume          BIGINT        DEFAULT 0,
    source          VARCHAR(50)   DEFAULT 'mt5',
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

CREATE INDEX IF NOT EXISTS idx_tick_data_symbol_time
    ON public.tick_data (symbol, timestamp DESC);

-- Create daily partitions for 30 days
DO $$
DECLARE
    d DATE;
    part_name TEXT;
BEGIN
    FOR i IN 0..30 LOOP
        d := (NOW() + (i || ' days')::INTERVAL)::DATE;
        part_name := 'tick_data_' || TO_CHAR(d, 'YYYYMMDD');
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.tick_data FOR VALUES FROM (%L) TO (%L)',
            part_name, d, d + INTERVAL '1 day'
        );
    END LOOP;
END $$;

-- Auto-create partition helper
CREATE OR REPLACE FUNCTION public.create_market_data_partition(target_date DATE)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    part_name TEXT;
    y INT := EXTRACT(YEAR FROM target_date)::INT;
    m INT := EXTRACT(MONTH FROM target_date)::INT;
BEGIN
    part_name := 'market_data_1m_y' || y || '_m' || LPAD(m::TEXT, 2, '0');
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.market_data_1m FOR VALUES FROM (%L) TO (%L)',
        part_name,
        DATE_TRUNC('month', target_date),
        DATE_TRUNC('month', target_date) + INTERVAL '1 month'
    );
    RETURN part_name;
END $$;
