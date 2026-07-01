"""
backend/observability/metrics.py
Galaxy Vast AI — Metrics Registry (repaired from literal-\\n corruption)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MetricsSnapshot:
    counters: dict[str, float] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)
    histograms: dict[str, list[float]] = field(default_factory=dict)
    uptime_s: float = 0.0


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._events: list[dict[str, Any]] = []
        self._start_time = time.time()
        self._prom: str = ""
        self._kill_switch_active: bool = False

    def _inc(self, name: str, value: float = 1.0) -> None:
        self._counters[name] = self._counters.get(name, 0.0) + value

    def _set_gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def _observe(self, name: str, value: float) -> None:
        self._histograms.setdefault(name, []).append(value)

    def _add_event(self, category: str, **kwargs: Any) -> None:
        evt = {"ts": time.time(), "category": category, **kwargs}
        self._events.append(evt)
        if len(self._events) > 5000:
            self._events = self._events[-5000:]

    def license_failure(self, reason: str, **kwargs: Any) -> None:
        self._inc("license_failures_total")
        self._inc(f"license_failures.{reason}")
        self._add_event("license_failure", reason=reason, **kwargs)

    def heartbeat_received(self, device_id: str) -> None:
        self._set_gauge(f"last_heartbeat.{device_id}", time.time())

    def heartbeat_loss(self, device_id: str, gap_s: float, **kwargs: Any) -> None:
        self._inc("heartbeat_losses_total")
        self._observe("heartbeat_gap_s", gap_s)
        self._add_event("heartbeat_loss", device_id=device_id, gap_s=gap_s, **kwargs)

    def kill_switch_activated(self, by: str, reason: str) -> None:
        self._kill_switch_active = True
        self._inc("kill_switch_activations_total")
        self._set_gauge("kill_switch_active", 1.0)
        self._add_event("kill_switch", by=by, reason=reason)

    def kill_switch_reset(self, by: str) -> None:
        self._kill_switch_active = False
        self._set_gauge("kill_switch_active", 0.0)
        self._add_event("kill_switch_reset", by=by)

    def is_kill_switch_active(self) -> bool:
        return self._kill_switch_active

    def reconciliation_mismatch(self, symbol: str, expected: float, actual: float) -> None:
        self._inc("reconciliation_mismatches_total")
        self._inc(f"reconciliation_mismatches.{symbol}")
        self._add_event("reconciliation_mismatch", symbol=symbol, expected=expected, actual=actual)

    def drawdown_alert(self, pct: float, level: str = "WARNING", **kwargs: Any) -> None:
        self._inc("drawdown_alerts_total")
        self._set_gauge("equity_drawdown_pct", pct)
        self._add_event("drawdown_alert", pct=pct, level=level, **kwargs)

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {k: list(v) for k, v in self._histograms.items()},
            "uptime_s": time.time() - self._start_time,
        }

    def admin_snapshot(self) -> dict[str, Any]:
        snap = self.snapshot()
        snap["saas_kpis"] = {
            "license_failures_total": self._counters.get("license_failures_total", 0),
            "heartbeat_losses_total": self._counters.get("heartbeat_losses_total", 0),
            "kill_switch_active": self._gauges.get("kill_switch_active", 0),
            "reconciliation_mismatches_total": self._counters.get("reconciliation_mismatches_total", 0),
            "drawdown_alerts_total": self._counters.get("drawdown_alerts_total", 0),
            "equity_drawdown_pct": self._gauges.get("equity_drawdown_pct", 0),
        }
        snap["recent_events"] = self._events[-20:]
        return snap

    def get_events(self, category: str | None = None) -> list[dict[str, Any]]:
        if category:
            return [e for e in self._events if e.get("category") == category]
        return list(self._events)

    def reset(self) -> None:
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._events.clear()
        self._kill_switch_active = False
        self._start_time = time.time()

    def prometheus_text(self) -> str:
        lines = []
        for k, v in self._counters.items():
            safe = k.replace(".", "_")
            lines.append(f"# TYPE {safe} counter")
            lines.append(f"{safe} {v}")
        for k, v in self._gauges.items():
            safe = k.replace(".", "_")
            lines.append(f"# TYPE {safe} gauge")
            lines.append(f"{safe} {v}")
        return "\n".join(lines) + "\n"


metrics_registry = MetricsRegistry()

__all__ = ["MetricsRegistry", "MetricsSnapshot", "metrics_registry"]
