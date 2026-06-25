from __future__ import annotations
import logging, math, time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional
logger = logging.getLogger('observability.metrics')

try:
    from prometheus_client import Counter, Gauge, Histogram
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False
    Counter = Gauge = Histogram = None  # type: ignore

@dataclass
class _HistogramData:
    _window: Deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    def observe(self, value: float) -> None: self._window.append(value)
    def snapshot(self) -> Dict[str, float]:
        if not self._window: return {'count': 0, 'sum': 0.0, 'p50': 0.0, 'p95': 0.0, 'p99': 0.0}
        s = sorted(self._window); n = len(s)
        def p(pct: float) -> float: return s[max(0, min(n-1, int(math.ceil(pct/100*n))-1))]
        return {'count': n, 'sum': sum(s), 'p50': p(50), 'p95': p(95), 'p99': p(99), 'min': s[0], 'max': s[-1]}

class MetricsRegistry:
    def __init__(self) -> None:
        self._counters:   Dict[str, float]         = defaultdict(float)
        self._gauges:     Dict[str, float]          = defaultdict(float)
        self._histograms: Dict[str, _HistogramData] = {}
        self._prom: bool  = _PROM_AVAILABLE
        self._started_at: float = time.time()
        if self._prom: self._init_prometheus()
    def _init_prometheus(self) -> None:
        try:
            self._pc_trades_submitted = Counter('trading_trades_submitted_total', 'Trades submitted', ['symbol', 'direction'])
            self._pc_trades_filled    = Counter('trading_trades_filled_total',    'Trades filled',    ['symbol', 'direction'])
            self._pc_trades_rejected  = Counter('trading_trades_rejected_total',  'Trades rejected',  ['symbol', 'reason'])
            self._pc_retries          = Counter('trading_order_retries_total',    'Order retries',    ['symbol'])
            self._pc_dead_letter      = Counter('trading_dead_letter_total',      'Dead letter',      ['symbol'])
            self._pc_risk_blocks      = Counter('trading_risk_blocks_total',      'Risk blocks',      ['gate', 'reason'])
            self._ph_risk_latency     = Histogram('trading_risk_gate_latency_seconds', 'Risk gate latency', ['gate'], buckets=[0.001,0.005,0.01,0.05,0.1,0.5])
            self._ph_fill_latency     = Histogram('trading_fill_latency_seconds', 'Fill latency', buckets=[0.1,0.5,1.0,2.0,5.0,10.0,30.0])
            self._pg_lot_size         = Gauge('trading_last_lot_size', 'Last lot size', ['symbol'])
            self._pg_open_positions   = Gauge('trading_open_positions_total', 'Open positions')
            self._pg_equity           = Gauge('trading_account_equity', 'Account equity')
        except Exception as exc:
            logger.warning('[metrics] Prometheus init failed: %s', exc); self._prom = False
    def increment(self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None) -> None: self._counters[name] += value
    def gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None: self._gauges[name] = value
    def histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        if name not in self._histograms: self._histograms[name] = _HistogramData()
        self._histograms[name].observe(value)
    def trade_submitted(self, symbol: str, direction: str) -> None:
        self.increment('trades_submitted')
        if self._prom:
            try: self._pc_trades_submitted.labels(symbol=symbol, direction=direction).inc()
            except Exception: pass
    def trade_filled(self, symbol: str, direction: str, fill_latency_s: float) -> None:
        self.increment('trades_filled'); self.histogram('fill_latency_s', fill_latency_s)
        if self._prom:
            try: self._pc_trades_filled.labels(symbol=symbol, direction=direction).inc(); self._ph_fill_latency.observe(fill_latency_s)
            except Exception: pass
    def trade_rejected(self, symbol: str, reason: str) -> None:
        self.increment('trades_rejected')
        if self._prom:
            try: self._pc_trades_rejected.labels(symbol=symbol, reason=reason).inc()
            except Exception: pass
    def order_retry(self, symbol: str) -> None:
        self.increment('order_retries')
        if self._prom:
            try: self._pc_retries.labels(symbol=symbol).inc()
            except Exception: pass
    def dead_letter(self, symbol: str) -> None:
        self.increment('dead_letter')
        if self._prom:
            try: self._pc_dead_letter.labels(symbol=symbol).inc()
            except Exception: pass
    def risk_block(self, gate: str, reason: str) -> None:
        self.increment(f'risk_blocks.{gate}')
        if self._prom:
            try: self._pc_risk_blocks.labels(gate=gate, reason=reason).inc()
            except Exception: pass
    def risk_latency(self, gate: str, latency_s: float) -> None:
        self.histogram(f'risk_latency_s.{gate}', latency_s)
        if self._prom:
            try: self._ph_risk_latency.labels(gate=gate).observe(latency_s)
            except Exception: pass
    def set_lot_size(self, symbol: str, lot_size: float) -> None:
        self.gauge(f'lot_size.{symbol}', lot_size)
        if self._prom:
            try: self._pg_lot_size.labels(symbol=symbol).set(lot_size)
            except Exception: pass
    def set_open_positions(self, count: int) -> None:
        self.gauge('open_positions', float(count))
        if self._prom:
            try: self._pg_open_positions.set(count)
            except Exception: pass
    def set_equity(self, equity: float) -> None:
        self.gauge('account_equity', equity)
        if self._prom:
            try: self._pg_equity.set(equity)
            except Exception: pass
    def snapshot(self) -> Dict[str, Any]:
        return {'uptime_s': round(time.time() - self._started_at, 1), 'counters': dict(self._counters), 'gauges': dict(self._gauges), 'histograms': {k: v.snapshot() for k, v in self._histograms.items()}, 'prometheus': self._prom}
    async def health(self) -> Dict[str, Any]:
        snap = self.snapshot()
        return {'status': 'ok', 'uptime_s': snap['uptime_s'], 'trades_submitted': self._counters.get('trades_submitted', 0), 'trades_filled': self._counters.get('trades_filled', 0), 'trades_rejected': self._counters.get('trades_rejected', 0), 'order_retries': self._counters.get('order_retries', 0), 'dead_letter': self._counters.get('dead_letter', 0), 'prometheus': self._prom}

metrics_registry = MetricsRegistry()
