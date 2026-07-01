"""
backend/observability/metrics.py
Galaxy Vast AI Trading Platform — Enterprise Metrics Registry
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
__all__ = ["MetricsRegistry", "metrics_registry"]


class MetricsRegistry:
    """Thread-safe in-process metrics store."""

    def __init__(self) -> None:
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges:   Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._events:   List[Dict[str, Any]] = []
        self._start_time = time.time()
        self._prom: str = ""

    # ─ counters ────────────────────────────────────────────────────────
    def increment(self, name: str, value: float = 1.0, **labels) -> None:
        key = name + ("."+".".join(f"{k}={v}" for k,v in labels.items()) if labels else "")
        self._counters[key] += value

    # ─ gauges ─────────────────────────────────────────────────────────
    def set_gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    # ─ histograms ───────────────────────────────────────────────────
    def observe(self, name: str, value: float) -> None:
        self._histograms[name].append(value)
        if len(self._histograms[name]) > 10000:
            self._histograms[name] = self._histograms[name][-5000:]

    # ─ SaaS domain metrics ─────────────────────────────────────────
    def license_failure(self, reason: str, **kw) -> None:
        self._counters["license_failures_total"] += 1
        self._counters[f"license_failures.{reason}"] += 1
        self._add_event("license_failure", reason=reason, **kw)

    def heartbeat_received(self, device_id: str) -> None:
        self._gauges[f"last_heartbeat.{device_id}"] = time.time()

    def heartbeat_loss(self, device_id: str, gap_s: float = 0, **kw) -> None:
        self._counters["heartbeat_losses_total"] += 1
        self._histograms["heartbeat_gap_s"].append(gap_s)
        self._add_event("heartbeat_loss", device_id=device_id, gap_s=gap_s, **kw)

    def kill_switch_activated(self, by: str, reason: str = "") -> None:
        self._counters["kill_switch_activations_total"] += 1
        self._gauges["kill_switch_active"] = 1.0
        self._add_event("kill_switch", activated_by=by, reason=reason)

    def kill_switch_reset(self, by: str) -> None:
        self._gauges["kill_switch_active"] = 0.0
        self._add_event("kill_switch_reset", reset_by=by)

    def is_kill_switch_active(self) -> bool:
        return self._gauges.get("kill_switch_active", 0.0) == 1.0

    def reconciliation_mismatch(self, symbol: str, expected: float, actual: float) -> None:
        self._counters["reconciliation_mismatches_total"] += 1
        self._counters[f"reconciliation_mismatches.{symbol}"] += 1
        self._add_event("reconciliation_mismatch", symbol=symbol, expected=expected, actual=actual)

    def drawdown_alert(self, pct: float, level: str = "WARNING", **kw) -> None:
        self._counters["drawdown_alerts_total"] += 1
        self._gauges["equity_drawdown_pct"] = pct
        self._add_event("drawdown_alert", pct=pct, level=level, **kw)

    # ─ snapshots ─────────────────────────────────────────────────────
    def snapshot(self) -> Dict[str, Any]:
        return {
            "counters": dict(self._counters),
            "gauges":   dict(self._gauges),
            "histograms": {k: list(v) for k, v in self._histograms.items()},
            "uptime_s": time.time() - self._start_time,
        }

    def admin_snapshot(self) -> Dict[str, Any]:
        snap = self.snapshot()
        snap["saas_kpis"] = {
            "license_failures_total":          self._counters.get("license_failures_total", 0),
            "heartbeat_losses_total":          self._counters.get("heartbeat_losses_total", 0),
            "kill_switch_active":              self._gauges.get("kill_switch_active", 0),
            "reconciliation_mismatches_total": self._counters.get("reconciliation_mismatches_total", 0),
            "drawdown_alerts_total":           self._counters.get("drawdown_alerts_total", 0),
            "equity_drawdown_pct":             self._gauges.get("equity_drawdown_pct", 0),
        }
        snap["recent_events"] = self._events[-20:]
        return snap

    def get_events(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        if category:
            return [e for e in self._events if e.get("category") == category]
        return list(self._events)

    def prometheus(self) -> str:
        lines = []
        for name, val in self._counters.items():
            safe = name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE {safe} counter")
            lines.append(f"{safe} {val}")
        for name, val in self._gauges.items():
            safe = name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE {safe} gauge")
            lines.append(f"{safe} {val}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._events.clear()

    def _add_event(self, category: str, **kw) -> None:
        import time as _t
        self._events.append({"category": category, "ts": _t.time(), **kw})
        if len(self._events) > 5000:
            self._events = self._events[-5000:]

    # Dead-letter and order-retry counters
    def get_order_stats(self) -> Dict[str, int]:
        return {
            "order_retries": int(self._counters.get("order_retries", 0)),
            "dead_letter":   int(self._counters.get("dead_letter", 0)),
            "prometheus":    len(self._prom),
        }


metrics_registry = MetricsRegistry()
