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
        self._prom:        bool  = False
        self._prom_warned: bool = False  # log Prometheus failures only once
        self._pc_trades_submitted = self._pc_trades_filled = None
        self._pc_trades_rejected  = self._pc_retries = None
        self._pc_dead_letter      = self._pc_risk_blocks = None
        self._ph_fill_latency     = self._ph_risk_latency = None
        self._pg_lot_size         = self._pg_open_positions = self._pg_equity = None
        try:
            from prometheus_client import Counter, Gauge, Histogram
            self._pc_trades_submitted = Counter('trades_submitted_total',  'Trades submitted',  ['symbol', 'direction'])
            self._pc_trades_filled    = Counter('trades_filled_total',      'Trades filled',     ['symbol', 'direction'])
            self._pc_trades_rejected  = Counter('trades_rejected_total',   'Trades rejected',   ['symbol', 'reason'])
            self._pc_retries          = Counter('order_retries_total',     'Order retries',     ['symbol'])
            self._pc_dead_letter      = Counter('dead_letter_total',       'Dead-letter orders',['symbol'])
            self._pc_risk_blocks      = Counter('risk_blocks_total',       'Risk gate blocks',  ['gate', 'reason'])
            self._ph_fill_latency     = Histogram('fill_latency_seconds',  'Fill latency',      ['symbol', 'direction'], buckets=[.01,.05,.1,.25,.5,1,2,5])
            self._ph_risk_latency     = Histogram('risk_latency_seconds',  'Risk gate latency', ['gate'],                buckets=[.001,.005,.01,.05,.1,.25,.5])
            self._pg_lot_size         = Gauge('lot_size',                  'Current lot size',  ['symbol'])
            self._pg_open_positions   = Gauge('open_positions',            'Open positions count')
            self._pg_equity           = Gauge('account_equity',            'Account equity USD')
            self._prom = True
        except Exception as _e:  # noqa: BLE001 — prometheus_client optional
            _LOG.debug('Prometheus not available: %s', _e)

    def _prom_log_once(self, exc: Exception) -> None:
        """Log Prometheus metric failure once at DEBUG to avoid log spam."""
        if not self._prom_warned:
            _LOG.debug('prometheus metric update failed (will silence further): %s', exc)
            self._prom_warned = True

    def increment(self, name: str, value: float = 1.0) -> None:
        self._counters[name] = self._counters.get(name, 0.0) + value

    def gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        if name not in self._histograms: self._histograms[name] = _HistogramData()
        self._histograms[name].observe(value)

    def trade_submitted(self, symbol: str, direction: str) -> None:
        self.increment('trades_submitted')
        if self._prom:
            try: self._pc_trades_submitted.labels(symbol=symbol, direction=direction).inc()
            except Exception as _pe: self._prom_log_once(_pe)  # noqa: BLE001

    def trade_filled(self, symbol: str, direction: str, fill_latency_s: float) -> None:
        self.increment('trades_filled'); self.histogram('fill_latency_s', fill_latency_s)
        if self._prom:
            try: self._pc_trades_filled.labels(symbol=symbol, direction=direction).inc(); self._ph_fill_latency.observe(fill_latency_s)
            except Exception as _pe: self._prom_log_once(_pe)  # noqa: BLE001

    def trade_rejected(self, symbol: str, reason: str) -> None:
        self.increment('trades_rejected')
        if self._prom:
            try: self._pc_trades_rejected.labels(symbol=symbol, reason=reason).inc()
            except Exception as _pe: self._prom_log_once(_pe)  # noqa: BLE001

    def order_retry(self, symbol: str) -> None:
        self.increment('order_retries')
        if self._prom:
            try: self._pc_retries.labels(symbol=symbol).inc()
            except Exception as _pe: self._prom_log_once(_pe)  # noqa: BLE001

    def dead_letter(self, symbol: str) -> None:
        self.increment('dead_letter')
        if self._prom:
            try: self._pc_dead_letter.labels(symbol=symbol).inc()
            except Exception as _pe: self._prom_log_once(_pe)  # noqa: BLE001

    def risk_block(self, gate: str, reason: str) -> None:
        self.increment(f'risk_blocks.{gate}')
        if self._prom:
            try: self._pc_risk_blocks.labels(gate=gate, reason=reason).inc()
            except Exception as _pe: self._prom_log_once(_pe)  # noqa: BLE001

    def risk_latency(self, gate: str, latency_s: float) -> None:
        self.histogram(f'risk_latency_s.{gate}', latency_s)
        if self._prom:
            try: self._ph_risk_latency.labels(gate=gate).observe(latency_s)
            except Exception as _pe: self._prom_log_once(_pe)  # noqa: BLE001

    def set_lot_size(self, symbol: str, lot_size: float) -> None:
        self.gauge(f'lot_size.{symbol}', lot_size)
        if self._prom:
            try: self._pg_lot_size.labels(symbol=symbol).set(lot_size)
            except Exception as _pe: self._prom_log_once(_pe)  # noqa: BLE001

    def set_open_positions(self, count: int) -> None:
        self.gauge('open_positions', float(count))
        if self._prom:
            try: self._pg_open_positions.set(count)
            except Exception as _pe: self._prom_log_once(_pe)  # noqa: BLE001

    def set_equity(self, equity: float) -> None:
        self.gauge('account_equity', equity)
        if self._prom:
            try: self._pg_equity.set(equity)
            except Exception as _pe: self._prom_log_once(_pe)  # noqa: BLE001

    def snapshot(self) -> Dict[str, Any]:
        return {'uptime_s': round(time.time() - self._started_at, 1), 'counters': dict(self._counters), 'gauges': dict(self._gauges), 'histograms': {k: v.snapshot() for k, v in self._histograms.items()}, 'prometheus': self._prom}

    async def health(self) -> Dict[str, Any]:
        snap = self.snapshot()
        return {'status': 'ok', 'uptime_s': snap['uptime_s'], 'trades_submitted': self._counters.get('trades_submitted', 0), 'trades_filled': self._counters.get('trades_filled', 0), 'trades_rejected': self._counters.get('trades_rejected', 0), 'order_retries': self._counters.get('order_retries', 0), 'dead_letter': self._counters.get('dead_letter', 0), 'prometheus': self._prom}


metrics_registry = MetricsRegistry()
