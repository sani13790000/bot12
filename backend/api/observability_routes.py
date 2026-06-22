"""Observability API Routes. Phase L fixes L-13/L-14/L-15/L-16."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from backend.observability.metrics import metrics_registry
from backend.observability.alert_manager import alert_manager
from backend.observability.tracing import tracer
from backend.core.deps import get_current_user

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/metrics", response_class=PlainTextResponse)
async def get_prometheus_metrics(_user=Depends(get_current_user)) -> str:
    """Prometheus text exposition format."""
    return metrics_registry.prometheus_format()


@router.get("/metrics/json")
async def get_metrics_json(_user=Depends(get_current_user)) -> dict:
    return metrics_registry.snapshot()


@router.get("/traces")
async def get_recent_traces(limit: int = 100, _user=Depends(get_current_user)) -> dict:
    return {
        "spans": tracer.get_recent_spans(limit=limit),
        "summary": tracer.summary(),
        "active": tracer.get_active_spans(),
    }


@router.get("/traces/slow")
async def get_slow_traces(threshold_ms: float = 500.0, _user=Depends(get_current_user)) -> dict:
    return {"threshold_ms": threshold_ms, "spans": tracer.get_slow_spans(threshold_ms=threshold_ms)}


@router.get("/alerts")
async def get_alert_history(limit: int = 50, _user=Depends(get_current_user)) -> dict:
    return {"history": alert_manager.get_history(limit=limit), "rules": alert_manager.get_rules()}


@router.post("/alerts/test/{rule_name}")
async def test_alert(rule_name: str, _user=Depends(get_current_user)) -> dict:
    fired = await alert_manager.fire(rule_name, context={"test": True, "manual": "triggered from API"})
    return {"fired": fired, "rule": rule_name}
