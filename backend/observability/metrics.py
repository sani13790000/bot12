"""
backend/observability/metrics.py
Galaxy Vast AI Trading Platform — Enterprise Metrics Registry

Phase 9 — Production Observability
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


class MetricsRegistry:
    """Thread-safe metrics registry with Prometheus export."""

    def __init__(self) -> None:
        self._counters:   Dict[str, int]        = defaultdict(int)
        self._gauges:     Dict[str, float]      = defaultdict(float)
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._events:     List[Dict[str, Any]]   = []
        self._start_time: float                  = time.time()
        self._prom: Optional[str]                = None

    def increment(self, name: str, value: int = 1) -> None:
        self._counters[name] += value

    def gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def histogram(self, name: str, value: float) -> None:
        self._histograms[name].append(value)
        if len(self._histograms[name]) > 10000:
            self._histograms[name] = self._histograms[name][-5000:]

    def snapshot(self) -> Dict[str, Any]:
        return {
            "counters":   dict(self._counters),
            "gauges":     dict(self._gauges),
            "histograms": {k: list(v) for k, v in self._histograms.items()},
            "uptime_s":   time.time() - self._start_time,
        }

    def prometheus_text(self) -> str:
        lines = []
        for name, value in self._counters.items():
            safe = name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE {safe} counter")
            lines.append(f"{safe} {value}")
        for name, value in self._gauges.items():
            safe = name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE {safe} gauge")
            lines.append(f"{safe} {value}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._events.clear()
        self._start_time = time.time()

    # SaaS KPI methods
    def license_failure(self, reason: str, **kwargs: Any) -> None:
        self.increment("license_failures_total")
        self.increment(f"license_failures.{reason}")
        event = {"ts": time.time(), "category": "license_failure", "reason": reason, **kwargs}
        self._add_event(event)

    def heartbeat_received(self, device_id: str, **kwargs: Any) -> None:
        self.gauge(f"last_heartbeat.{device_id}", time.time())

    def heartbeat_loss(self, device_id: str, gap_s: float, **kwargs: Any) -> None:
        self.increment("heartbeat_losses_total")
        self.histogram("heartbeat_gap_s", gap_s)
        event = {"ts": time.time(), "category": "heartbeat_loss", "device_id": device_id, "gap_s": gap_s, **kwargs}
        self._add_event(event)

    def kill_switch_activated(self, admin: str, reason: str, **kwargs: Any) -> None:
        self.increment("kill_switch_activations_total")
        self.gauge("kill_switch_active", 1.0)
        event = {"ts": time.time(), "category": "kill_switch", "admin": admin, "reason": reason}
        self._add_event(event)

    def kill_switch_reset(self, admin: str, **kwargs: Any) -> None:
        self.gauge("kill_switch_active", 0.0)

    def is_kill_switch_active(self) -> bool:
        return self._gauges.get("kill_switch_active", 0.0) > 0.5

    def reconciliation_mismatch(self, symbol: str, local: float, remote: float) -> None:
        self.increment("reconciliation_mismatches_total")
        self.increment(f"reconciliation_mismatches.{symbol}")

    def drawdown_alert(self, pct: float, **kwargs: Any) -> None:
        self.increment("drawdown_alerts_total")
        self.gauge("equity_drawdown_pct", pct)

    def admin_snapshot(self) -> Dict[str, Any]:
        snap = self.snapshot()
        return {
            "saas_kpis": {
                "license_failures_total": self._counters.get("license_failures_total", 0),
                "heartbeat_losses_total": self._counters.get("heartbeat_losses_total", 0),
                "kill_switch_active": self._gauges.get("kill_switch_active", 0.0),
                "reconciliation_mismatches_total": self._counters.get("reconciliation_mismatches_total", 0),
                "drawdown_alerts_total": self._counters.get("drawdown_alerts_total", 0),
                "equity_drawdown_pct": self._gauges.get("equity_drawdown_pct", 0.0),
            },
            "recent_events": self._events[-20:],
            **snap,
        }

    def get_events(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        if category:
            return [e for e in self._events if e.get("category") == category]
        return list(self._events)

    def _add_event(self, event: Dict[str, Any]) -> None:
        self._events.append(event)
        if len(self._events) > 5000:
            self._events = self._events[-2500:]


metrics_registry = MetricsRegistry()
