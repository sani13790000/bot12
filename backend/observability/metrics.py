"""
faz 9 - Prometheus Metrics Registry
Counter, Histogram, Gauge baraye har component
"""
from __future__ import annotations

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Counter:
    name: str
    labels: Dict[str, str] = field(default_factory=dict)
    _value: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        return self._value


@dataclass
class Gauge:
    name: str
    labels: Dict[str, str] = field(default_factory=dict)
    _value: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value -= amount

    @property
    def value(self) -> float:
        return self._value


@dataclass
class Histogram:
    name: str
    buckets: List[float] = field(default_factory=lambda: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
    labels: Dict[str, str] = field(default_factory=dict)
    _observations: List[float] = field(default_factory=list)
    _sum: float = 0.0
    _count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, value: float) -> None:
        with self._lock:
            self._observations.append(value)
            self._sum += value
            self._count += 1

    @property
    def count(self) -> int:
        return self._count

    @property
    def sum(self) -> float:
        return self._sum

    @property
    def mean(self) -> float:
        if self._count == 0:
            return 0.0
        return self._sum / self._count

    def percentile(self, p: float) -> float:
        if not self._observations:
            return 0.0
        sorted_obs = sorted(self._observations)
        idx = int(len(sorted_obs) * p / 100)
        return sorted_obs[min(idx, len(sorted_obs) - 1)]

    def bucket_counts(self) -> Dict[str, int]:
        result = {}
        for b in self.buckets:
            result[str(b)] = sum(1 for o in self._observations if o <= b)
        return result


class MetricsRegistry:
    """Singleton registry baraye hame metrics"""

    def __init__(self) -> None:
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._lock = threading.Lock()

        # --- HTTP metrics ---
        self.http_requests_total = self._counter("http_requests_total")
        self.http_request_duration = self._histogram("http_request_duration_seconds")
        self.http_errors_total = self._counter("http_errors_total")
        self.http_active_requests = self._gauge("http_active_requests")

        # --- Agent metrics ---
        self.agent_votes_total = self._counter("agent_votes_total")
        self.agent_errors_total = self._counter("agent_errors_total")
        self.agent_duration = self._histogram("agent_duration_seconds")
        self.agent_score = self._histogram("agent_score")

        # --- Signal metrics ---
        self.signals_generated_total = self._counter("signals_generated_total")
        self.signals_approved_total = self._counter("signals_approved_total")
        self.signals_rejected_total = self._counter("signals_rejected_total")
        self.signal_confidence = self._histogram("signal_confidence")

        # --- Trade metrics ---
        self.trades_executed_total = self._counter("trades_executed_total")
        self.trades_won_total = self._counter("trades_won_total")
        self.trades_lost_total = self._counter("trades_lost_total")
        self.trade_pnl = self._histogram("trade_pnl_usd")
        self.trade_duration = self._histogram("trade_duration_minutes")

        # --- ML metrics ---
        self.ml_predictions_total = self._counter("ml_predictions_total")
        self.ml_training_total = self._counter("ml_training_total")
        self.ml_drift_score = self._gauge("ml_drift_score")
        self.ml_model_accuracy = self._gauge("ml_model_accuracy")
        self.ml_inference_duration = self._histogram("ml_inference_duration_seconds")

        # --- DB metrics ---
        self.db_queries_total = self._counter("db_queries_total")
        self.db_query_duration = self._histogram("db_query_duration_seconds")
        self.db_errors_total = self._counter("db_errors_total")
        self.db_pool_size = self._gauge("db_pool_size")

        # --- MT5 metrics ---
        self.mt5_orders_total = self._counter("mt5_orders_total")
        self.mt5_errors_total = self._counter("mt5_errors_total")
        self.mt5_latency = self._histogram("mt5_latency_seconds")
        self.mt5_connected = self._gauge("mt5_connected")

        # --- Circuit breaker metrics ---
        self.circuit_breaker_open_total = self._counter("circuit_breaker_open_total")
        self.circuit_breaker_state = self._gauge("circuit_breaker_state")

        # --- News metrics ---
        self.news_fetch_total = self._counter("news_fetch_total")
        self.news_impact_score = self._histogram("news_impact_score")
        self.news_fetch_errors = self._counter("news_fetch_errors_total")

        # --- System metrics ---
        self.system_uptime = self._gauge("system_uptime_seconds")
        self._start_time = time.time()

    def _counter(self, name: str) -> Counter:
        c = Counter(name=name)
        self._counters[name] = c
        return c

    def _gauge(self, name: str) -> Gauge:
        g = Gauge(name=name)
        self._gauges[name] = g
        return g

    def _histogram(self, name: str) -> Histogram:
        h = Histogram(name=name)
        self._histograms[name] = h
        return h

    def snapshot(self) -> Dict:
        """Return current values of all metrics"""
        uptime = time.time() - self._start_time
        self.system_uptime.set(uptime)

        return {
            "counters": {k: v.value for k, v in self._counters.items()},
            "gauges": {k: v.value for k, v in self._gauges.items()},
            "histograms": {
                k: {
                    "count": v.count,
                    "sum": v.sum,
                    "mean": v.mean,
                    "p50": v.percentile(50),
                    "p95": v.percentile(95),
                    "p99": v.percentile(99),
                }
                for k, v in self._histograms.items()
            },
            "uptime_seconds": uptime,
        }

    def prometheus_format(self) -> str:
        """Prometheus text exposition format"""
        lines = []
        uptime = time.time() - self._start_time
        self.system_uptime.set(uptime)

        for name, c in self._counters.items():
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {c.value}")

        for name, g in self._gauges.items():
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {g.value}")

        for name, h in self._histograms.items():
            lines.append(f"# TYPE {name} histogram")
            lines.append(f"{name}_count {h.count}")
            lines.append(f"{name}_sum {h.sum}")
            for bucket, count in h.bucket_counts().items():
                lines.append(f"{name}_bucket{{le=\"{bucket}\"}} {count}")

        return "\n".join(lines) + "\n"


# Singleton
metrics_registry = MetricsRegistry()
