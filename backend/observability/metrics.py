"""
backend/observability/metrics.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Prometheus metrics for the Galaxy Vast trading platform.

Metrics exposed
---------------
- trade_executions_total        (counter)   — trades by direction + symbol
- trade_pnl_dollars             (histogram) — P&L distribution per trade
- active_positions              (gauge)     — current open position count
- signal_confidence             (histogram) — model confidence scores
- api_request_duration_seconds  (histogram) — FastAPI latency by route
- kill_switch_activations_total (counter)   — emergency stops
- smc_analysis_duration_seconds (histogram) — SMC engine latency

Usage::

    from backend.observability.metrics import (
        record_trade, record_signal, update_active_positions
    )
    record_trade(symbol="EURUSD", direction="BUY", pnl=42.5)
    record_signal(symbol="EURUSD", confidence=0.82)
    update_active_positions(count=3)

The /metrics endpoint is mounted by the FastAPI app using
``prometheus_fastapi_instrumentator`` or the ``/metrics`` route in
``backend/api/observability_routes.py``.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)


# ── Prometheus registry (graceful degradation if not installed) ──────────── #

try:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

    _REGISTRY = CollectorRegistry(auto_describe=True)

    trade_executions_total = Counter(
        "trade_executions_total",
        "Total number of trade executions",
        ["direction", "symbol", "strategy"],
        registry=_REGISTRY,
    )

    trade_pnl_dollars = Histogram(
        "trade_pnl_dollars",
        "P&L per closed trade in USD",
        ["symbol", "direction"],
        buckets=(-500, -200, -100, -50, -20, 0, 20, 50, 100, 200, 500, 1000),
        registry=_REGISTRY,
    )

    active_positions = Gauge(
        "active_positions",
        "Number of currently open positions",
        registry=_REGISTRY,
    )

    signal_confidence = Histogram(
        "signal_confidence",
        "Model confidence score for generated signals",
        ["symbol", "direction"],
        buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
        registry=_REGISTRY,
    )

    api_request_duration_seconds = Histogram(
        "api_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "endpoint", "status_code"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        registry=_REGISTRY,
    )

    kill_switch_activations_total = Counter(
        "kill_switch_activations_total",
        "Number of times the kill-switch has been activated",
        ["reason"],
        registry=_REGISTRY,
    )

    smc_analysis_duration_seconds = Histogram(
        "smc_analysis_duration_seconds",
        "Time taken to run SMC analysis in seconds",
        ["symbol", "timeframe"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        registry=_REGISTRY,
    )

    _PROMETHEUS_AVAILABLE = True
    logger.debug("[metrics] Prometheus client loaded successfully")

except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.warning(
        "[metrics] prometheus_client not installed — metrics are no-ops. "
        "Install with: pip install prometheus-client"
    )


# ── Public helper functions ────────────────────────────────────────────────── #


def record_trade(
    symbol: str,
    direction: str,
    pnl: float = 0.0,
    strategy: str = "unknown",
) -> None:
    """
    Increment trade counter and record P&L.

    Safe to call even if prometheus_client is not installed.
    """
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        trade_executions_total.labels(
            direction=direction.upper(),
            symbol=symbol.upper(),
            strategy=strategy,
        ).inc()
        trade_pnl_dollars.labels(
            symbol=symbol.upper(),
            direction=direction.upper(),
        ).observe(pnl)
    except Exception as exc:
        logger.debug("[metrics] record_trade error: %s", exc)


def record_signal(symbol: str, direction: str, confidence: float) -> None:
    """Record the confidence score of a generated signal."""
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        signal_confidence.labels(
            symbol=symbol.upper(),
            direction=direction.upper(),
        ).observe(confidence)
    except Exception as exc:
        logger.debug("[metrics] record_signal error: %s", exc)


def update_active_positions(count: int) -> None:
    """Set the active positions gauge to *count*."""
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        active_positions.set(count)
    except Exception as exc:
        logger.debug("[metrics] update_active_positions error: %s", exc)


def record_kill_switch(reason: str = "manual") -> None:
    """Increment the kill-switch activation counter."""
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        kill_switch_activations_total.labels(reason=reason).inc()
    except Exception as exc:
        logger.debug("[metrics] record_kill_switch error: %s", exc)


@contextmanager
def time_smc_analysis(
    symbol: str = "unknown",
    timeframe: str = "unknown",
) -> Generator[None, None, None]:
    """
    Context manager that records how long the SMC analysis took.

    Usage::

        with time_smc_analysis(symbol="EURUSD", timeframe="H1"):
            result = engine.analyse(candles)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        if _PROMETHEUS_AVAILABLE:
            try:
                smc_analysis_duration_seconds.labels(
                    symbol=symbol.upper(),
                    timeframe=timeframe.upper(),
                ).observe(elapsed)
            except Exception as exc:
                logger.debug("[metrics] time_smc_analysis record error: %s", exc)


def get_registry() -> object:
    """
    Return the Prometheus CollectorRegistry.

    Used by the /metrics endpoint to generate the exposition format.
    Returns None if prometheus_client is not available.
    """
    if not _PROMETHEUS_AVAILABLE:
        return None
    return _REGISTRY
