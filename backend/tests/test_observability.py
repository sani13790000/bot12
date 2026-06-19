"""Tests for observability module."""
from __future__ import annotations

import pytest


def test_metrics_registry_import() -> None:
    """MetricsRegistry should import without error."""
    from backend.observability.metrics import MetricsRegistry, metrics_registry
    assert metrics_registry is not None


def test_metrics_registry_has_counters() -> None:
    from backend.observability.metrics import metrics_registry
    assert hasattr(metrics_registry, "http_requests_total")
    assert hasattr(metrics_registry, "active_connections")
    assert hasattr(metrics_registry, "backtest_jobs_total")


def test_metrics_uptime() -> None:
    from backend.observability.metrics import metrics_registry
    uptime = metrics_registry.uptime_seconds()
    assert uptime >= 0


def test_alert_manager_import() -> None:
    from backend.observability.alert_manager import AlertManager, AlertLevel, alert_manager
    assert alert_manager is not None


@pytest.mark.asyncio
async def test_alert_manager_send() -> None:
    from backend.observability.alert_manager import AlertManager, AlertLevel
    manager = AlertManager()
    await manager.send("test alert", AlertLevel.INFO, {"key": "value"})
    history = manager.get_history()
    assert len(history) == 1
    assert history[0]["message"] == "test alert"


def test_tracing_import() -> None:
    from backend.observability.tracing import new_trace_id, get_trace_id, Timer
    tid = new_trace_id()
    assert get_trace_id() == tid
    assert len(tid) == 36  # UUID format


def test_timer() -> None:
    import time
    from backend.observability.tracing import Timer
    with Timer() as t:
        time.sleep(0.01)
    assert t.elapsed >= 0.005
