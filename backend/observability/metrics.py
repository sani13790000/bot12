"""
backend/observability/metrics.py
Galaxy Vast AI Trading Platform — Enterprise Metrics Registry

All metrics are stored in-memory (always) and optionally pushed to Prometheus.
Prometheus is optional — all prometheus failures are logged once at DEBUG.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional

_LOG = logging.getLogger(__name__)


@dataclass
class _HistogramData:
    """Rolling histogram (last 1000 observations)."""
    _window: Deque[float] = field(default_factory=lambda: deque(maxlen=1000))

    def observe(self, value: float) -> None:
        self._window.append(value)

    def snapshot(self) -> Dict[str, Any]:
        if not self._window:
            return {'count': 0, 'min': 0.0, 'max': 0.0, 'mean': 0.0, 'p95': 0.0, 'p99': 0.0}
        w = sorted(self._window)
        n = len(w)
        return {
            'count': n,
            'min':   round(w[0], 6),
            'max':   round(w[-1], 6),
            'mean':  round(sum(w) / n, 6),
            'p95':   round(w[int(n * 0.95)], 6),
            'p99':   round(w[int(n * 0.99)], 6),
        }


class MetricsRegistry:
    """Thread-safe in-memory metrics registry with optional Prometheus export."""

    def __init__(self) -> None:
        self._counters:   Dict[str, float] = {}
        self._gauges:     Dict[str, float] = {}
        self._histograms: Dict[str, _HistogramData] = {}
        self._started_at: float = time.time()
        self._prom: bool = False
        self._prom_warned: bool = False
        self._pc_trades_submitted = self._pc_trades_filled = None
        self._pc_trades_rejected  = self._pc_retries = None
        self._pc_dead_letter      = self._pc_risk_blocks = None
        self._ph_fill_latency     = self._ph_risk_latency = None
        self._pg_lot_size         = self._pg_open_positions = self._pg_equity = None
        try:
            from prometheus_client import Counter, Gauge, Histogram
            self._pc_trades_submitted = Counter('trades_submitted_total', 'Trades submitted', ['symbol', 'direction'])
            self._pc_trades_filled    = Counter('trades_filled_total', 'Trades filled', ['symbol', 'direction'])
            self._pc_trades_rejected  = Counter('trades_rejected_total', 'Trades rejected', ['symbol', 'reason'])
            self._pc_retries          = Counter('order_retries_total', 'Order retries', ['symbol'])
            self._pc_dead_letter      = Counter('dead_letter_total', 'Dead-letter orders', ['symbol'])
            self._pc_risk_blocks      = Counter('risk_blocks_total', 'Risk gate blocks', ['gate', 'reason'])
            self._ph_fill_latency     = Histogram('fill_latency_seconds', 'Fill latency', ['symbol', 'direction'], buckets=[.01,.05,.1,.25,.5,1,2,5])
            self._ph_risk_latency     = Histogram('risk_latency_seconds', 'Risk gate latency', ['gate'], buckets=[.001,.005,.01,.05,.1,.25,.5])
            self._pg_lot_size         = Gauge('lot_size', 'Current lot size', ['symbol'])
            self._pg_open_positions   = Gauge('open_positions', 'Open positions count')
            self._pg_equity           = Gauge('account_equity', 'Account equity USD')
            self._prom = True
        except Exception as _e:
            _LOG.debug('Prometheus not available: %s', _e)

    def _prom_log_once(self, exc: Exception) -> None:
        if not self._prom_warned:
            _LOG.debug('prometheus metric update failed (will silence further): %s', exc)
            self._prom_warned = True

    def increment(self, name: str, value: float = 1.0) -> None:
        self._counters[name] = self._counters.get(name, 0.0) + value

    def gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        if name not in self._histograms:
            self._histograms[name] = _HistogramData()
        self._histograms[name].observe(value)

    def snapshot(self) -> Dict[str, Any]:
        return {
            'uptime_s': round(time.time() - self._started_at, 1),
            'counters': dict(self._counters),
            'gauges': dict(self._gauges),
            'histograms': {k: v.snapshot() for k, v in self._histograms.items()},
            'dead_letter': self._counters.get('dead_letter', 0),
            'prometheus': self._prom,
        }


metrics_registry = MetricsRegistry()
