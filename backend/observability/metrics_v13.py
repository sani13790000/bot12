from __future__ import annotations
import logging, threading, time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional
_LOG = logging.getLogger(__name__)

@dataclass
class _HistogramData:
    _window: Deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    _lock: threading.Lock = field(default_factory=threading.Lock)
    def observe(self, value: float) -> None:
        with self._lock: self._window.append(value)
    def snapshot(self) -> Dict[str, Any]:
        with self._lock: w = sorted(self._window)
        if not w: return {'count':0,'min':0.0,'max':0.0,'mean':0.0,'p50':0.0,'p95':0.0,'p99':0.0}
        n = len(w)
        return {'count':n,'min':round(w[0],6),'max':round(w[-1],6),'mean':round(sum(w)/n,6),'p50':round(w[int(n*0.50)],6),'p95':round(w[int(n*0.95)],6),'p99':round(w[max(0,int(n*0.99)-1)],6)}

class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str,float] = {}
        self._gauges: Dict[str,float] = {}
        self._histograms: Dict[str,_HistogramData] = {}
        self._started_at: float = time.time()
        self._prom: bool = False
        self._prom_warned: bool = False
        self._prom_objects: Dict[str,Any] = {}
        self._init_prometheus()
    def _init_prometheus(self) -> None:
        try:
            from prometheus_client import Counter, Gauge, Histogram, REGISTRY
            def _goc(cls, name, desc, labels=None, **kw):
                try: return cls(name, desc, labels or [], **kw)
                except ValueError: return REGISTRY._names_to_collectors.get(name)
            self._prom_objects = {
                'trades_submitted': _goc(Counter,'trades_submitted_total','Trades submitted',['symbol','direction']),
                'trades_filled':    _goc(Counter,'trades_filled_total',   'Trades filled',   ['symbol','direction']),
                'trades_rejected':  _goc(Counter,'trades_rejected_total', 'Trades rejected', ['symbol','reason']),
                'order_retries':    _goc(Counter,'order_retries_total',   'Order retries',   ['symbol']),
                'dead_letter':      _goc(Counter,'dead_letter_total',     'Dead-letter',     ['symbol']),
                'risk_blocks':      _goc(Counter,'risk_blocks_total',     'Risk gate blocks',['gate','reason']),
                'fill_latency':     _goc(Histogram,'fill_latency_seconds','Fill latency',   ['symbol','direction'],buckets=[.01,.05,.1,.25,.5,1,2,5]),
                'risk_latency':     _goc(Histogram,'risk_latency_seconds','Risk latency',   ['gate'],buckets=[.001,.005,.01,.05,.1,.25,.5]),
                'lot_size':         _goc(Gauge,'lot_size',         'Current lot size',['symbol']),
                'open_positions':   _goc(Gauge,'open_positions',   'Open positions count'),
                'account_equity':   _goc(Gauge,'account_equity',   'Account equity USD'),
                'equity_drawdown':  _goc(Gauge,'equity_drawdown_pct','Equity drawdown %'),
            }
            self._prom = True
        except Exception as e: _LOG.debug('Prometheus not available: %s', e)
    def _prom_log_once(self, exc: Exception) -> None:
        if not self._prom_warned: _LOG.debug('prometheus metric failed: %s', exc); self._prom_warned = True
    def increment(self, name: str, value: float = 1.0) -> None:
        with self._lock: self._counters[name] = self._counters.get(name, 0.0) + value
    def gauge(self, name: str, value: float) -> None:
        with self._lock: self._gauges[name] = value
    def histogram(self, name: str, value: float, tags=None) -> None:
        with self._lock:
            if name not in self._histograms: self._histograms[name] = _HistogramData()
            hist = self._histograms[name]
        hist.observe(value)
    def reset(self) -> None:
        with self._lock: self._counters.clear(); self._gauges.clear(); self._histograms.clear(); self._started_at = time.time()
    def trade_submitted(self, symbol: str, direction: str) -> None:
        self.increment('trades_submitted')
        if self._prom:
            try: self._prom_objects['trades_submitted'].labels(symbol=symbol,direction=direction).inc()
            except Exception as e: self._prom_log_once(e)
    def trade_filled(self, symbol: str, direction: str, fill_latency_s: float) -> None:
        self.increment('trades_filled'); self.histogram('fill_latency_s', fill_latency_s)
        if self._prom:
            try: self._prom_objects['trades_filled'].labels(symbol=symbol,direction=direction).inc(); self._prom_objects['fill_latency'].labels(symbol=symbol,direction=direction).observe(fill_latency_s)
            except Exception as e: self._prom_log_once(e)
    def trade_rejected(self, symbol: str, reason: str) -> None:
        self.increment('trades_rejected')
        if self._prom:
            try: self._prom_objects['trades_rejected'].labels(symbol=symbol,reason=reason).inc()
            except Exception as e: self._prom_log_once(e)
    def order_retry(self, symbol: str) -> None:
        self.increment('order_retries')
        if self._prom:
            try: self._prom_objects['order_retries'].labels(symbol=symbol).inc()
            except Exception as e: self._prom_log_once(e)
    def dead_letter(self, symbol: str) -> None:
        self.increment('dead_letter')
        if self._prom:
            try: self._prom_objects['dead_letter'].labels(symbol=symbol).inc()
            except Exception as e: self._prom_log_once(e)
    def risk_block(self, gate: str, reason: str) -> None:
        self.increment(f'risk_blocks.{gate}')
        if self._prom:
            try: self._prom_objects['risk_blocks'].labels(gate=gate,reason=reason).inc()
            except Exception as e: self._prom_log_once(e)
    def risk_latency(self, gate: str, latency_s: float) -> None:
        self.histogram(f'risk_latency_s.{gate}', latency_s)
        if self._prom:
            try: self._prom_objects['risk_latency'].labels(gate=gate).observe(latency_s)
            except Exception as e: self._prom_log_once(e)
    def set_lot_size(self, symbol: str, lot_size: float) -> None:
        self.gauge(f'lot_size.{symbol}', lot_size)
        if self._prom:
            try: self._prom_objects['lot_size'].labels(symbol=symbol).set(lot_size)
            except Exception as e: self._prom_log_once(e)
    def set_open_positions(self, count: int) -> None:
        self.gauge('open_positions', float(count))
        if self._prom:
            try: self._prom_objects['open_positions'].set(count)
            except Exception as e: self._prom_log_once(e)
    def set_equity(self, equity: float) -> None:
        self.gauge('account_equity', equity)
        if self._prom:
            try: self._prom_objects['account_equity'].set(equity)
            except Exception as e: self._prom_log_once(e)
    def set_equity_drawdown(self, drawdown_pct: float) -> None:
        self.gauge('equity_drawdown_pct', drawdown_pct)
        if self._prom:
            try: self._prom_objects['equity_drawdown'].set(drawdown_pct)
            except Exception as e: self._prom_log_once(e)
    def prometheus_format(self) -> str:
        try:
            from prometheus_client import generate_latest
            return generate_latest().decode('utf-8')
        except Exception:
            lines: List[str] = []
            with self._lock:
                for name, value in self._counters.items():
                    safe = name.replace('.','_'); lines.extend([f'# HELP {safe} counter',f'# TYPE {safe} counter',f'{safe} {value}'])
                for name, value in self._gauges.items():
                    safe = name.replace('.','_'); lines.extend([f'# HELP {safe} gauge',f'# TYPE {safe} gauge',f'{safe} {value}'])
            return '\n'.join(lines) + '\n'
    def snapshot(self) -> Dict[str,Any]:
        with self._lock: counters=dict(self._counters); gauges=dict(self._gauges); hists={k:v.snapshot() for k,v in self._histograms.items()}
        return {'uptime_s':round(time.time()-self._started_at,1),'counters':counters,'gauges':gauges,'histograms':hists,'prometheus':self._prom}
    async def health(self) -> Dict[str,Any]:
        snap=self.snapshot()
        return {'status':'ok','uptime_s':snap['uptime_s'],'trades_submitted':self._counters.get('trades_submitted',0),'trades_filled':self._counters.get('trades_filled',0),'trades_rejected':self._counters.get('trades_rejected',0),'order_retries':self._counters.get('order_retries',0),'dead_letter':self._counters.get('dead_letter',0),'prometheus':self._prom}

metrics_registry = MetricsRegistry()
