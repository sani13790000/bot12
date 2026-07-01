"""
backend/observability/metrics.py
Galaxy Vast AI — Metrics Registry

Provides an in-process metrics registry with:
  - Counters, Gauges, Histograms
  - Prometheus text format export
  - Admin snapshot endpoint
  - SaaS KPI tracking (license failures, heartbeat, kill-switch, etc.)
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MetricsRegistry:
    """Thread-safe in-process metrics store."""

    def __init__(self) -> None:
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._events: Deque[Dict[str, Any]] = deque(maxlen=5000)
        self._start_time = time.time()
        self._kill_switch_active = False
        self._log = logging.getLogger(self.__class__.__name__)

    # ── Counters ──────────────────────────────────────────────────────────────
    def inc(self, name: str, value: int = 1, **labels) -> None:
        key = name + ("|" + ",".join(f"{k}={v}" for k, v in labels.items()) if labels else "")
        self._counters[key] += value

    # ── Gauges ────────────────────────────────────────────────────────────────
    def set_gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    # ── Histograms ────────────────────────────────────────────────────────────
    def observe(self, name: str, value: float) -> None:
        self._histograms[name].append(value)
        if len(self._histograms[name]) > 10_000:
            self._histograms[name] = self._histograms[name][-5_000:]

    # ── SaaS KPIs ─────────────────────────────────────────────────────────────
    def license_failure(self, reason: str, **kwargs) -> None:
        self._counters["license_failures_total"] += 1
        self._counters[f"license_failures.{reason}"] += 1
        self._append_event("license_failure", {"reason": reason, **kwargs})

    def heartbeat_received(self, device_id: str) -> None:
        self._gauges[f"last_heartbeat.{device_id}"] = time.time()

    def heartbeat_loss(self, device_id: str, gap_s: float, **kwargs) -> None:
        self._counters["heartbeat_losses_total"] += 1
        self._histograms.setdefault("heartbeat_gap_s", []).append(gap_s)
        self._append_event("heartbeat_loss", {"device_id": device_id, "gap_s": gap_s, **kwargs})

    def kill_switch_activated(self, admin_id: str, reason: str) -> None:
        self._counters["kill_switch_activations_total"] += 1
        self._gauges["kill_switch_active"] = 1.0
        self._kill_switch_active = True
        self._append_event("kill_switch", {"admin_id": admin_id, "reason": reason})

    def kill_switch_reset(self, admin_id: str) -> None:
        self._gauges["kill_switch_active"] = 0.0
        self._kill_switch_active = False
        self._append_event("kill_switch_reset", {"admin_id": admin_id})

    def is_kill_switch_active(self) -> bool:
        return self._kill_switch_active

    def reconciliation_mismatch(self, symbol: str, expected: float, actual: float) -> None:
        self._counters["reconciliation_mismatches_total"] += 1
        self._counters[f"reconciliation_mismatches.{symbol}"] += 1
        self._append_event("reconciliation_mismatch", {"symbol": symbol, "expected": expected, "actual": actual})

    def drawdown_alert(self, pct: float, level: str = "WARNING", **kwargs) -> None:
        self._counters["drawdown_alerts_total"] += 1
        self._gauges["equity_drawdown_pct"] = pct
        self._append_event("drawdown_alert", {"pct": pct, "level": level, **kwargs})

    def order_retry(self) -> None:
        self._counters["order_retries"] += 1

    def dead_letter(self) -> None:
        self._counters["dead_letter"] += 1

    # ── Snapshots ─────────────────────────────────────────────────────────────
    def snapshot(self) -> Dict[str, Any]:
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {k: list(v) for k, v in self._histograms.items()},
            "uptime_s": time.time() - self._start_time,
        }

    def admin_snapshot(self) -> Dict[str, Any]:
        snap = self.snapshot()
        snap["saas_kpis"] = {
            "license_failures_total": self._counters.get("license_failures_total", 0),
            "heartbeat_losses_total": self._counters.get("heartbeat_losses_total", 0),
            "kill_switch_active": self._gauges.get("kill_switch_active", 0),
            "reconciliation_mismatches_total": self._counters.get("reconciliation_mismatches_total", 0),
            "drawdown_alerts_total": self._counters.get("drawdown_alerts_total", 0),
            "equity_drawdown_pct": self._gauges.get("equity_drawdown_pct", 0),
        }
        snap["recent_events"] = list(self._events)[-20:]
        return snap

    def prometheus_text(self) -> str:
        lines = []
        for name, value in self._counters.items():
            safe = name.replace(".", "_").replace("|", "{").replace(",", ",").replace("=", "=")
            lines.append(f"# TYPE {safe.split('{')[0]} counter")
            lines.append(f"{safe} {value}")
        for name, value in self._gauges.items():
            safe = name.replace(".", "_")
            lines.append(f"# TYPE {safe} gauge")
            lines.append(f"{safe} {value}")
        return "\n".join(lines) + "\n"

    def get_events(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        if category is None:
            return list(self._events)
        return [e for e in self._events if e.get("category") == category]

    def reset(self) -> None:
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._events.clear()
        self._kill_switch_active = False
        self._start_time = time.time()

    def _append_event(self, category: str, data: Dict[str, Any]) -> None:
        import time as t
        self._events.append({"category": category, "ts": t.time(), **data})


metrics_registry = MetricsRegistry()
