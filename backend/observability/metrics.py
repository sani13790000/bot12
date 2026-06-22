"""Prometheus-compatible metrics registry. Phase L fixes L-15/L-22/L-23/L-24."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class _LabeledMetric:
    def __init__(self) -> None:
        self._values: Dict[str, float] = {}

    def _key(self, **kwargs: str) -> str:
        return str(sorted(kwargs.items()))

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        k = self._key(**labels)
        self._values[k] = self._values.get(k, 0.0) + amount

    def dec(self, amount: float = 1.0, **labels: str) -> None:
        k = self._key(**labels)
        self._values[k] = self._values.get(k, 0.0) - amount

    def set(self, value: float, **labels: str) -> None:
        self._values[self._key(**labels)] = value

    def observe(self, value: float, **labels: str) -> None:
        self.inc(value, **labels)


class _InMemoryLabelProxy:
    def __init__(self, metric: _LabeledMetric, labels: Dict[str, str]) -> None:
        self._metric = metric
        self._labels = labels

    def inc(self, amount: float = 1.0) -> None:
        self._metric.inc(amount, **self._labels)

    def dec(self, amount: float = 1.0) -> None:
        self._metric.dec(amount, **self._labels)

    def set(self, value: float) -> None:
        self._metric.set(value, **self._labels)

    def observe(self, value: float) -> None:
        self._metric.observe(value, **self._labels)


class _InMemoryMetric:
    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description
        self._value: float = 0.0
        self._labeled = _LabeledMetric()

    def inc(self, amount: float = 1.0) -> None:
        self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        self._value -= amount

    def set(self, value: float) -> None:
        self._value = value

    def observe(self, value: float) -> None:
        self.inc(value)

    def labels(self, **kwargs: str) -> _InMemoryLabelProxy:
        return _InMemoryLabelProxy(self._labeled, kwargs)

    @property
    def value(self) -> float:
        return self._value


def _safe_counter(name, desc, labels):
    try:
        from prometheus_client import Counter
        return Counter(name, desc, labels)
    except (ValueError, Exception):
        try:
            from prometheus_client import REGISTRY
            return REGISTRY._names_to_collectors.get(name, _InMemoryMetric(name, desc))
        except Exception:
            return _InMemoryMetric(name, desc)


def _safe_histogram(name, desc, labels, buckets):
    try:
        from prometheus_client import Histogram
        return Histogram(name, desc, labels, buckets=buckets)
    except (ValueError, Exception):
        try:
            from prometheus_client import REGISTRY
            return REGISTRY._names_to_collectors.get(name, _InMemoryMetric(name, desc))
        except Exception:
            return _InMemoryMetric(name, desc)


def _safe_gauge(name, desc, labels=None):
    try:
        from prometheus_client import Gauge
        return Gauge(name, desc, labels or [])
    except (ValueError, Exception):
        return _InMemoryMetric(name, desc)


class MetricsRegistry:
    def __init__(self) -> None:
        self._start_time = time.time()
        self._use_prometheus = False
        self._init_metrics()

    def _init_metrics(self) -> None:
        try:
            import prometheus_client  # noqa
            self._use_prometheus = True
        except ImportError:
            pass
        self.http_requests_total = _safe_counter(
            "gv_http_requests_total", "Total HTTP requests", ["method", "path", "status"])
        self.http_request_duration_seconds = _safe_histogram(
            "gv_http_request_duration_seconds", "HTTP request duration",
            ["method", "path"], (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0))
        self.active_connections = _safe_gauge(
            "gv_active_websocket_connections", "Active WebSocket connections")
        self.trade_executions_total = _safe_counter(
            "gv_trade_executions_total", "Total trade executions", ["symbol", "direction", "status"])
        self.signal_generations_total = _safe_counter(
            "gv_signal_generations_total", "Total signals generated", ["symbol", "direction"])
        self.risk_blocks_total = _safe_counter(
            "gv_risk_blocks_total", "Signals blocked by risk engine", ["reason"])
        self.db_errors_total = _safe_counter(
            "gv_db_errors_total", "Total database errors", ["operation"])

    def prometheus_format(self) -> str:
        """FIX L-15."""
        if self._use_prometheus:
            try:
                from prometheus_client import generate_latest
                return generate_latest().decode("utf-8")
            except Exception as exc:
                logger.warning("prometheus generate_latest failed: %s", exc)
        lines = [
            "# HELP gv_uptime_seconds Uptime in seconds",
            "# TYPE gv_uptime_seconds gauge",
            f"gv_uptime_seconds {time.time() - self._start_time:.1f}",
        ]
        return "\n".join(lines) + "\n"

    def snapshot(self) -> Dict[str, Any]:
        """FIX L-15/L-24."""
        return {
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "prometheus_available": self._use_prometheus,
        }


metrics_registry = MetricsRegistry()
