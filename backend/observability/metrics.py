"""
backend/observability/metrics.py
Galaxy Vast AI — Business & Technical Metrics

P13-OBS-1: Prometheus counters/gauges/histograms for SaaS KPIs
P13-OBS-2: Trade execution metrics
P13-OBS-3: System health metrics
P13-OBS-4: Lazy initialisation — no crash if prometheus_client not installed
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import Prometheus; degrade gracefully if not installed
try:
    from prometheus_client import Counter, Gauge, Histogram, Summary
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False
    logger.warning("[Metrics] prometheus_client not installed — metrics disabled")


# --------------------------------------------------------------------------- #
# Metric definitions (lazy: only created if Prometheus is available)
# --------------------------------------------------------------------------- #

if _PROM_AVAILABLE:
    # --- Trades ---
    TRADE_EXECUTED = Counter(
        "galaxy_trades_executed_total",
        "Total trades executed",
        ["symbol", "direction", "strategy"],
    )
    TRADE_PNL = Histogram(
        "galaxy_trade_pnl_usd",
        "Trade P&L in USD",
        ["symbol", "direction"],
        buckets=[-500, -100, -50, -10, 0, 10, 50, 100, 500, 1000],
    )
    TRADE_DURATION = Histogram(
        "galaxy_trade_duration_seconds",
        "Trade open duration in seconds",
        ["symbol"],
        buckets=[60, 300, 900, 3600, 14400, 86400],
    )
    OPEN_POSITIONS = Gauge(
        "galaxy_open_positions",
        "Number of currently open positions",
        ["symbol"],
    )

    # --- Signals ---
    SIGNAL_GENERATED = Counter(
        "galaxy_signals_generated_total",
        "Total trading signals generated",
        ["symbol", "signal_type"],
    )
    SIGNAL_APPROVED = Counter(
        "galaxy_signals_approved_total",
        "Signals approved by voting engine",
        ["symbol"],
    )
    SIGNAL_REJECTED = Counter(
        "galaxy_signals_rejected_total",
        "Signals rejected by voting engine or risk manager",
        ["symbol", "reason"],
    )

    # --- Risk ---
    DAILY_DRAWDOWN = Gauge(
        "galaxy_daily_drawdown_pct",
        "Current daily drawdown percentage",
        ["account"],
    )
    KILL_SWITCH_ACTIVE = Gauge(
        "galaxy_kill_switch_active",
        "1 if kill switch is active, 0 otherwise",
    )

    # --- API ---
    HTTP_REQUEST_DURATION = Histogram(
        "galaxy_http_request_duration_seconds",
        "HTTP request processing time",
        ["method", "endpoint", "status"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    )
    HTTP_REQUESTS_TOTAL = Counter(
        "galaxy_http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )

    # --- System ---
    ACTIVE_USERS = Gauge("galaxy_active_users", "Currently active users")
    LICENSE_VALID = Gauge(
        "galaxy_license_valid",
        "1 if license is valid, 0 otherwise",
        ["user_id"],
    )

else:
    # Dummy objects so callers don't need try/except
    class _Noop:
        def labels(self, **_): return self
        def inc(self, *a, **k): pass
        def dec(self, *a, **k): pass
        def set(self, *a, **k): pass
        def observe(self, *a, **k): pass
        def time(self):          return self
        def __enter__(self):     return self
        def __exit__(self, *a):  pass

    _noop = _Noop()
    TRADE_EXECUTED     = _noop
    TRADE_PNL          = _noop
    TRADE_DURATION     = _noop
    OPEN_POSITIONS     = _noop
    SIGNAL_GENERATED   = _noop
    SIGNAL_APPROVED    = _noop
    SIGNAL_REJECTED    = _noop
    DAILY_DRAWDOWN     = _noop
    KILL_SWITCH_ACTIVE = _noop
    HTTP_REQUEST_DURATION = _noop
    HTTP_REQUESTS_TOTAL   = _noop
    ACTIVE_USERS       = _noop
    LICENSE_VALID      = _noop


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #

def record_trade(
    symbol:    str,
    direction: str,
    strategy:  str,
    pnl_usd:   float,
    duration_s: float,
) -> None:
    """Record a completed trade in all relevant metrics."""
    TRADE_EXECUTED.labels(symbol=symbol, direction=direction, strategy=strategy).inc()
    TRADE_PNL.labels(symbol=symbol, direction=direction).observe(pnl_usd)
    TRADE_DURATION.labels(symbol=symbol).observe(duration_s)


def record_signal(symbol: str, signal_type: str, approved: bool, reason: str = "") -> None:
    """Record a generated signal outcome."""
    SIGNAL_GENERATED.labels(symbol=symbol, signal_type=signal_type).inc()
    if approved:
        SIGNAL_APPROVED.labels(symbol=symbol).inc()
    else:
        SIGNAL_REJECTED.labels(symbol=symbol, reason=reason[:32]).inc()
