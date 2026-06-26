"""
backend/observability/metrics_v15.py — Phase 15
P15-OBS-MET-1: license_failure counter
P15-OBS-MET-2: heartbeat_loss counter + last_heartbeat gauge
P15-OBS-MET-3: kill_switch_activations counter + active gauge
P15-OBS-MET-4: reconciliation_mismatch counter
P15-OBS-MET-5: drawdown_alert counter
P15-OBS-MET-6: thread-safe reset()
P15-OBS-MET-7: prometheus_format() — full text exposition
P15-OBS-MET-8: admin_snapshot() — extended view
"""
from __future__ import annotations
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional


@dataclass
class _HistogramData:
    _window: Deque[float] = field(default_factory=lambda: deque(maxlen=2000))
    _lock: threading.Lock = field(default_factory=threading.Lock)
    def observe(self, value: float) -> None:
        with self._lock:
            self._window.append(value)
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            w = sorted(self._window)
        if not w:
            return {"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
        n = len(w)
        return {
            "count": n, "min": round(w[0], 6), "max": round(w[-1], 6),
            "mean": round(sum(w) / n, 6),
            "p50": round(w[int(n * 0.50)], 6),
            "p95": round(w[int(n * 0.95)], 6),
            "p99": round(w[max(0, int(n * 0.99) - 1)], 6),
        }


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._hists: Dict[str, _HistogramData] = {}
        self._events: List[Dict[str, Any]] = []
        self._started_at = time.time()
        self._prom_available = self._try_init_prometheus()

    def _try_init_prometheus(self) -> bool:
        try:
            import prometheus_client  # noqa: F401
            return True
        except ImportError:
            return False

    def _inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + value

    def _set(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def _obs(self, name: str, value: float) -> None:
        with self._lock:
            if name not in self._hists:
                self._hists[name] = _HistogramData()
        self._hists[name].observe(value)

    def _log_event(self, category: str, detail: Dict[str, Any]) -> None:
        with self._lock:
            self._events.append({"ts": time.time(), "category": category, **detail})
            if len(self._events) > 5000:
                self._events = self._events[-4000:]

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._hists.clear()
            self._events.clear()
            self._started_at = time.time()

    # Trading metrics
    def trade_submitted(self, symbol: str, direction: str) -> None:
        self._inc("trades_submitted"); self._inc(f"trades_submitted.{symbol}")
    def trade_filled(self, symbol: str, direction: str, fill_latency_s: float) -> None:
        self._inc("trades_filled"); self._obs("fill_latency_s", fill_latency_s)
    def trade_rejected(self, symbol: str, reason: str) -> None:
        self._inc("trades_rejected"); self._inc(f"trades_rejected.{reason}")
    def order_retry(self, symbol: str) -> None: self._inc("order_retries")
    def dead_letter(self, symbol: str) -> None: self._inc("dead_letter")
    def risk_block(self, gate: str, reason: str) -> None:
        self._inc(f"risk_blocks.{gate}"); self._inc("risk_blocks_total")
    def risk_latency(self, gate: str, latency_s: float) -> None:
        self._obs(f"risk_latency_s.{gate}", latency_s)
    def set_lot_size(self, symbol: str, lot: float) -> None: self._set(f"lot_size.{symbol}", lot)
    def set_open_positions(self, count: int) -> None: self._set("open_positions", float(count))
    def set_equity(self, equity_usd: float) -> None: self._set("equity_usd", equity_usd)
    def set_equity_drawdown(self, pct: float) -> None: self._set("equity_drawdown_pct", pct)

    # P15-OBS-MET-1: License
    def license_failure(self, reason: str, user_id: Optional[str] = None, device_id: Optional[str] = None) -> None:
        self._inc("license_failures_total"); self._inc(f"license_failures.{reason}")
        self._log_event("license_failure", {"reason": reason, "user_id": user_id, "device_id": device_id})
    def license_validated(self, plan: str) -> None:
        self._inc("license_validations_total"); self._inc(f"license_validations.{plan}")
    def license_expired(self, user_id: Optional[str] = None) -> None:
        self._inc("license_expirations_total"); self._log_event("license_expired", {"user_id": user_id})

    # P15-OBS-MET-2: Heartbeat
    def heartbeat_received(self, device_id: str) -> None:
        self._inc("heartbeat_received_total"); self._set(f"last_heartbeat.{device_id}", time.time())
    def heartbeat_loss(self, device_id: str, gap_s: float = 0.0, user_id: Optional[str] = None,
                      seconds_since_last: Optional[float] = None) -> None:
        if seconds_since_last is not None: gap_s = seconds_since_last
        self._inc("heartbeat_losses_total"); self._obs("heartbeat_gap_s", gap_s)
        self._log_event("heartbeat_loss", {"device_id": device_id, "gap_s": gap_s, "user_id": user_id})
    def get_last_heartbeat(self, device_id: str) -> Optional[float]:
        with self._lock: return self._gauges.get(f"last_heartbeat.{device_id}")

    # P15-OBS-MET-3: Kill switch
    def kill_switch_activated(self, actor: str, reason: str, scope: str = "global") -> None:
        self._inc("kill_switch_activations_total"); self._set("kill_switch_active", 1.0)
        self._log_event("kill_switch_activated", {"actor": actor, "reason": reason, "scope": scope})
    def kill_switch_reset(self, actor: str) -> None:
        self._inc("kill_switch_resets_total"); self._set("kill_switch_active", 0.0)
        self._log_event("kill_switch_reset", {"actor": actor})
    def is_kill_switch_active(self) -> bool:
        with self._lock: return self._gauges.get("kill_switch_active", 0.0) == 1.0

    # P15-OBS-MET-4: Reconciliation
    def reconciliation_started(self) -> None:
        self._inc("reconciliation_runs_total"); self._set("reconciliation_last_run_ts", time.time())
    def reconciliation_mismatch(self, symbol: str, broker_qty: float, local_qty: float) -> None:
        self._inc("reconciliation_mismatches_total"); self._inc(f"reconciliation_mismatches.{symbol}")
        self._log_event("reconciliation_mismatch", {"symbol": symbol, "broker_qty": broker_qty,
                                                     "local_qty": local_qty, "delta": abs(broker_qty - local_qty)})
    def reconciliation_duration(self, duration_s: float) -> None: self._obs("reconciliation_duration_s", duration_s)
    def reconciliation_ok(self, positions_checked: int) -> None:
        self._inc("reconciliation_ok_total")
        self._set("reconciliation_last_ok_ts", time.time())
        self._set("reconciliation_positions_checked", float(positions_checked))

    # P15-OBS-MET-5: Drawdown
    def drawdown_alert(self, pct: float, level: str = "WARNING", equity_usd: Optional[float] = None) -> None:
        self._inc("drawdown_alerts_total"); self._inc(f"drawdown_alerts.{level}")
        self._set("equity_drawdown_pct", pct)
        self._log_event("drawdown_alert", {"pct": pct, "level": level, "equity_usd": equity_usd})

    # P15-OBS-MET-7: Prometheus format
    def prometheus_format(self) -> str:
        lines: List[str] = []
        ts_ms = int(time.time() * 1000)
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            hists = {k: v.snapshot() for k, v in self._hists.items()}
        def _safe(n: str) -> str: return n.replace(".", "_").replace("-", "_")
        for name, value in sorted(counters.items()):
            safe = _safe(name)
            lines += [f"# HELP {safe}_total Counter", f"# TYPE {safe}_total counter", f"{safe}_total {value} {ts_ms}"]
        for name, value in sorted(gauges.items()):
            safe = _safe(name)
            lines += [f"# HELP {safe} Gauge", f"# TYPE {safe} gauge", f"{safe} {value} {ts_ms}"]
        for name, snap in sorted(hists.items()):
            safe = _safe(name)
            lines += [f"# HELP {safe} Histogram", f"# TYPE {safe} histogram",
                      f"{safe}_count {snap['count']} {ts_ms}"]
            for q, qn in [(0.5, "0.5"), (0.95, "0.95"), (0.99, "0.99")]:
                key = f"p{int(q*100)}"
                lines.append(f"{safe}{{quantile=\"{qn}\"}} {snap.get(key,0)} {ts_ms}")
        lines.append("")
        return "\n".join(lines)

    # P15-OBS-MET-8: Admin snapshot
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {"uptime_s": round(time.time() - self._started_at, 1),
                    "counters": dict(self._counters), "gauges": dict(self._gauges),
                    "histograms": {k: v.snapshot() for k, v in self._hists.items()},
                    "prometheus": self._prom_available}

    def admin_snapshot(self) -> Dict[str, Any]:
        snap = self.snapshot()
        c = snap["counters"]; g = snap["gauges"]
        with self._lock: recent_events = list(self._events[-100:])
        return {**snap, "saas_kpis": {
            "license_failures_total": c.get("license_failures_total", 0),
            "heartbeat_losses_total": c.get("heartbeat_losses_total", 0),
            "kill_switch_activations_total": c.get("kill_switch_activations_total", 0),
            "kill_switch_active": g.get("kill_switch_active", 0.0),
            "reconciliation_mismatches_total": c.get("reconciliation_mismatches_total", 0),
            "drawdown_alerts_total": c.get("drawdown_alerts_total", 0),
            "equity_drawdown_pct": g.get("equity_drawdown_pct", 0.0),
            "trades_submitted_total": c.get("trades_submitted", 0),
            "trades_rejected_total": c.get("trades_rejected", 0),
        }, "recent_events": recent_events}

    def get_events(self, category: Optional[str] = None, since_ts: Optional[float] = None,
                   limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock: evs = list(self._events)
        if category: evs = [e for e in evs if e.get("category") == category]
        if since_ts: evs = [e for e in evs if e.get("ts", 0) >= since_ts]
        return evs[-limit:]


metrics = MetricsRegistry()
