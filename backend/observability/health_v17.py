"""
PHASE 17 — health_v17.py
Real health-check module: live / ready / aggregate / prometheus_metrics
P17-HEALTH-1: live ≠ ready (Kubernetes probes separated)
P17-HEALTH-2: per-component timeout enforcement
P17-HEALTH-3: degraded→200 / unhealthy→503
P17-HEALTH-4: startup gate (mark_ready)
P17-HEALTH-5: prometheus text exposition
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ComponentHealth:
    name: str
    status: str
    message: str = ""
    latency_ms: float = 0.0


@dataclass
class HealthStatus:
    status: str
    http_status: int
    components: Dict[str, ComponentHealth] = field(default_factory=dict)
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "http_status": self.http_status,
            "components": {k: {"status": v.status, "message": v.message, "latency_ms": round(v.latency_ms, 2)} for k, v in self.components.items()},
            "checked_at": self.checked_at,
        }


class HealthChecker:
    def __init__(self) -> None:
        self._ready = False
        self._lock = threading.Lock()
        self._checks: Dict[str, tuple[Callable, float]] = {}
        self._component_states: Dict[str, ComponentHealth] = {}

    def mark_ready(self) -> None:
        with self._lock:
            self._ready = True

    def register(self, name: str, fn: Callable[[], bool], timeout: float = 5.0) -> None:
        self._checks[name] = (fn, timeout)

    def record_degraded(self, component: str, message: str = "") -> None:
        with self._lock:
            self._component_states[component] = ComponentHealth(name=component, status="degraded", message=message)

    def record_unhealthy(self, component: str, message: str = "") -> None:
        with self._lock:
            self._component_states[component] = ComponentHealth(name=component, status="unhealthy", message=message)

    def record_healthy(self, component: str) -> None:
        with self._lock:
            self._component_states[component] = ComponentHealth(name=component, status="healthy")

    def live(self) -> HealthStatus:
        return HealthStatus(status="healthy", http_status=200)

    def ready(self) -> HealthStatus:
        with self._lock:
            ready = self._ready
        if not ready:
            return HealthStatus(status="not_ready", http_status=503)
        return HealthStatus(status="ready", http_status=200)

    def aggregate(self) -> HealthStatus:
        with self._lock:
            ready = self._ready
            snapshot = dict(self._component_states)
        if not ready:
            return HealthStatus(status="not_ready", http_status=503)
        components: Dict[str, ComponentHealth] = dict(snapshot)
        for name, (fn, timeout) in self._checks.items():
            result_box: List[Optional[bool]] = [None]
            exc_box: List[Optional[Exception]] = [None]
            def _run():
                try:
                    result_box[0] = fn()
                except Exception as e:
                    exc_box[0] = e
            t = threading.Thread(target=_run, daemon=True)
            start = time.monotonic()
            t.start()
            t.join(timeout=timeout)
            elapsed_ms = (time.monotonic() - start) * 1000
            if t.is_alive():
                components[name] = ComponentHealth(name=name, status="unhealthy", message=f"timeout after {timeout}s", latency_ms=elapsed_ms)
            elif exc_box[0]:
                components[name] = ComponentHealth(name=name, status="unhealthy", message=str(exc_box[0]), latency_ms=elapsed_ms)
            elif result_box[0] is False:
                components[name] = ComponentHealth(name=name, status="unhealthy", message="check returned False", latency_ms=elapsed_ms)
            else:
                components[name] = ComponentHealth(name=name, status="healthy", latency_ms=elapsed_ms)
        statuses = {c.status for c in components.values()}
        if "unhealthy" in statuses:
            overall, http_code = "unhealthy", 503
        elif "degraded" in statuses:
            overall, http_code = "degraded", 200
        else:
            overall, http_code = "healthy", 200
        return HealthStatus(status=overall, http_status=http_code, components=components)

    def prometheus_metrics(self) -> str:
        with self._lock:
            ready = self._ready
            snapshot = dict(self._component_states)
        lines = [
            "# HELP health_status Current health status",
            "# TYPE health_status gauge",
            f'health_status{{probe="live"}} 1',
            f'health_status{{probe="ready"}} {1 if ready else 0}',
        ]
        for name, comp in snapshot.items():
            val = {"healthy": 1.0, "degraded": 0.5, "unhealthy": 0.0}.get(comp.status, 0.0)
            lines.append(f'health_status{{component="{name}"}} {val}')
        return "\n".join(lines) + "\n"
