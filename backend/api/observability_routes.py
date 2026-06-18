"""
faz 9 - Observability API Routes
GET /metrics, /observability/traces, /observability/alerts, /observability/spans
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from backend.observability.metrics import metrics_registry
from backend.observability.alert_manager import alert_manager
from backend.observability.tracing import tracer

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/metrics", response_class=PlainTextResponse)
async def get_prometheus_metrics() -> str:
    """Prometheus text exposition format"""
    return metrics_registry.prometheus_format()


@router.get("/metrics/json")
async def get_metrics_json() -> dict:
    """JSON snapshot of all metrics"""
    return metrics_registry.snapshot()


@router.get("/traces")
async def get_recent_traces(limit: int = 100) -> dict:
    """Recent spans"""
    return {
        "spans": tracer.get_recent_spans(limit=limit),
        "summary": tracer.summary(),
        "active": tracer.get_active_spans(),
    }


@router.get("/traces/slow")
async def get_slow_traces(threshold_ms: float = 500.0) -> dict:
    """Spans slower than threshold"""
    return {
        "threshold_ms": threshold_ms,
        "spans": tracer.get_slow_spans(threshold_ms=threshold_ms),
    }


@router.get("/alerts")
async def get_alert_history(limit: int = 50) -> dict:
    """Alert history"""
    return {
        "history": alert_manager.get_history(limit=limit),
        "rules": alert_manager.get_rules(),
    }


@router.post("/alerts/test/{rule_name}")
async def test_alert(rule_name: str) -> dict:
    """Fire a test alert (baraye debugging)"""
    fired = await alert_manager.fire(
        rule_name,
        context={"test": True, "manual": "triggered from API"},
    )
    return {"fired": fired, "rule": rule_name}
