"""Prometheus-compatible metrics registry.

Provides a lightweight metrics_registry that main.py imports.
If prometheus_client is available, uses real Counters/Gauges.
Otherwise falls back to in-memory dicts so the app still starts.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


class _InMemoryMetric:
    """Fallback metric when prometheus_client is not available."""

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description
        self._value: float = 0.0
        self._labels: Dict[str, float] = {}

    def inc(self, amount: float = 1.0) -> None:
        self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        self._value -= amount

    def set(self, value: float) -> None:
        self._value = value

    def labels(self, **kwargs: str) -> "_InMemoryMetric":
        key = str(sorted(kwargs.items()))
        if key not in self._labels:
            self._labels[key] = 0.0
        return self

    @property
    def value(self) -> float:
        return self._value


class MetricsRegistry:
    """Central metrics registry for Galaxy Vast platform."""

    def __init__(self) -> None:
        self._start_time = time.time()
        self._use_prometheus = False
        self._metrics: Dict[str, Any] = {}
        self._init_metrics()

    def _init_metrics(self) -> None:
        try:
            from prometheus_client import Counter, Gauge, Histogram
            self._use_prometheus = True
            self.http_requests_total = Counter(
                "http_requests_total",
                "Total HTTP requests",
                ["method", "path", "status"],
            )
            self.http_request_duration_seconds = Histogram(
                "http_request_duration_seconds",
                "HTTP request duration",
                ["method", "path"],
            )
            self.active_connections = Gauge(
                "active_connections",
                "Active WebSocket connections",
            )
            self.backtest_jobs_total = Counter(
                "backtest_jobs_total",
                "Total backtest jobs submitted",
                ["status"],
            )
            self.signals_generated_total = Counter(
                "signals_generated_total",
                "Total trading signals generated",
                ["symbol", "direction"],
            )
            self.db_query_duration_seconds = Histogram(
                "db_query_duration_seconds",
                "Database query duration",
                ["operation"],
            )
            logger.info("Prometheus metrics registry initialised")
        except ImportError:
            logger.warning(
                "prometheus_client not available — using in-memory metrics fallback"
            )
            self.http_requests_total = _InMemoryMetric(
                "http_requests_total", "Total HTTP requests"
            )
            self.http_request_duration_seconds = _InMemoryMetric(
                "http_request_duration_seconds", "HTTP request duration"
            )
            self.active_connections = _InMemoryMetric(
                "active_connections", "Active connections"
            )
            self.backtest_jobs_total = _InMemoryMetric(
                "backtest_jobs_total", "Backtest jobs"
            )
            self.signals_generated_total = _InMemoryMetric(
                "signals_generated_total", "Signals generated"
            )
            self.db_query_duration_seconds = _InMemoryMetric(
                "db_query_duration_seconds", "DB query duration"
            )

    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    def summary(self) -> Dict[str, Any]:
        return {
            "backend": "prometheus" if self._use_prometheus else "in-memory",
            "uptime_seconds": round(self.uptime_seconds(), 1),
        }


# Module-level singleton
metrics_registry = MetricsRegistry()
