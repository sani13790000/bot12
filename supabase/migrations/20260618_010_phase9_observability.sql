-- faz 9: Observability tables
-- alert_log, span_log, metrics_snapshot

BEGIN;

-- ============================================================
-- Alert log: har alert event
-- ============================================================
CREATE TABLE IF NOT EXISTS public.alert_log (
    id BIGSERIAL PRIMARY KEY,
    rule_name TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO','WARNING','ERROR','CRITICAL')),
    message TEXT NOT NULL,
    context JSONB DEFAULT '{}',
    fired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_alert_log_severity_fired
    ON public.alert_log (severity, fired_at DESC);

CREATE INDEX IF NOT EXISTS idx_alert_log_rule_fired
    ON public.alert_log (rule_name, fired_at DESC);

-- ============================================================
-- Span log: distributed tracing
-- ============================================================
CREATE TABLE IF NOT EXISTS public.span_log (
    id BIGSERIAL PRIMARY KEY,
    trace_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    parent_span_id TEXT,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OK',
    duration_ms FLOAT NOT NULL,
    error TEXT,
    tags JSONB DEFAULT '{}',
    events JSONB DEFAULT '[]',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_span_log_trace_id
    ON public.span_log (trace_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_span_slow
    ON public.span_log (duration_ms DESC)
    WHERE duration_ms > 500;

-- ============================================================
-- Metrics snapshot: hourly metrics
-- ============================================================
CREATE TABLE IF NOT EXISTS public.metrics_snapshot (
    id BIGSERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    counters JSONB NOT NULL DEFAULT '{}',
    gauges JSONB NOT NULL DEFAULT '{}',
    histograms JSONB NOT NULL DEFAULT '{}',
    uptime_seconds FLOAT
);

CREATE INDEX IF NOT EXISTS idx_metrics_snapshot_at
    ON public.metrics_snapshot (snapshot_at DESC);

-- ============================================================
-- Views baraye monitoring dashboard
-- ============================================================
CREATE OR REPLACE VIEW public.vw_recent_alerts AS
SELECT
    rule_name,
    severity,
    message,
    fired_at,
    acknowledged_at IS NOT NULL AS acknowledged
FROM public.alert_log
ORDER BY fired_at DESC
LIMIT 100;

CREATE OR REPLACE VIEW public.vw_slow_spans AS
SELECT
    trace_id,
    name,
    duration_ms,
    status,
    error,
    started_at
FROM public.span_log
WHERE duration_ms > 500
ORDER BY duration_ms DESC
LIMIT 50;

-- ============================================================
-- RLS
-- ============================================================
ALTER TABLE public.alert_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.span_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.metrics_snapshot ENABLE ROW LEVEL SECURITY;

COMMIT;
