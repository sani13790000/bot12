"""
backend/observability/metrics.py
Galaxy Vast AI Trading Platform — Enterprise Metrics Registry

All metrics are stored in-memory (always) and optionally pushed to Prometheus.
Prometheus is treated as a best-effort export target.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

LOGGER = logging.getLogger(__name__)


@dataclass
class MetricValue:
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


class MetricsRegistry:
    """In-memory metrics registry with optional Prometheus export."""

    def __init__(self) -> None:
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._events: List[Dict[str, Any]] = []
        self._prom: Optional[Any] = None
        self._start_time = time.time()

    def increment(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        self._counters[key] += value

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        self._gauges[key] = value

    def histogram_observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        self._histograms[key].append(value)

    def event(self, name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self._events.append({
            "name": name,
            "timestamp": time.time(),
            "payload": payload or {},
        })
        if len(self._events) > 10000:
            self._events = self._events[-5000:]

    def _key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def snapshot(self) -> Dict[str, Any]:
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {k: len(v) for k, v in self._histograms.items()},
            "events_count": len(self._events),
            "uptime_s": time.time() - self._start_time,
        }

    def reset(self) -> None:
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._events.clear()
        self._start_time = time.time()


metrics_registry = MetricsRegistry()
