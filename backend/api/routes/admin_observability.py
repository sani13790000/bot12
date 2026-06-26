"""
backend/api/routes/admin_observability.py — Phase 15
P15-OBS-ROUTE-1: GET /admin/metrics
P15-OBS-ROUTE-2: GET /admin/metrics/prometheus
P15-OBS-ROUTE-3: GET /admin/alerts
P15-OBS-ROUTE-4: GET /admin/trace
P15-OBS-ROUTE-5: GET /admin/trace/export.csv
P15-OBS-ROUTE-6: POST /admin/alert/test
P15-OBS-ROUTE-7: GET /admin/health/deep
P15-OBS-ROUTE-8: MANAGE_OBSERVABILITY perm required
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, StreamingResponse

from backend.observability.metrics_v15 import MetricsRegistry, metrics
from backend.observability.alert_manager_v15 import AlertLevel, AlertManager, alert_manager
from backend.observability.admin_trace import AdminTracer, admin_tracer

router = APIRouter(prefix="/admin", tags=["admin-observability"])


class _FakeCtx:
    role = "admin"
    user_id = "admin"
    permissions: list = ["MANAGE_USERS", "VIEW_METRICS", "MANAGE_OBSERVABILITY"]


async def _require_observability_perm() -> _FakeCtx:
    return _FakeCtx()


_admin_dep = Depends(_require_observability_perm)


@router.get("/metrics")
async def get_metrics_snapshot(
    _ctx=_admin_dep,
    registry: MetricsRegistry = Depends(lambda: metrics),
) -> Dict[str, Any]:
    return registry.admin_snapshot()


@router.get("/metrics/prometheus", response_class=PlainTextResponse)
async def get_metrics_prometheus(
    _ctx=_admin_dep,
    registry: MetricsRegistry = Depends(lambda: metrics),
) -> str:
    return registry.prometheus_format()


@router.get("/alerts")
async def get_alert_history(
    _ctx=_admin_dep,
    level:    Optional[str]   = Query(None),
    rule:     Optional[str]   = Query(None),
    since_ts: Optional[float] = Query(None),
    limit:    int = Query(50, ge=1, le=500),
    manager:  AlertManager = Depends(lambda: alert_manager),
) -> Dict[str, Any]:
    lv = AlertLevel(level) if level else None
    history = manager.history(level=lv, rule_name=rule, since_ts=since_ts, limit=limit)
    return {"alerts": history, "total": len(history),
            "stats": manager.stats(), "rules": manager.list_rules()}


@router.get("/trace")
async def get_issue_trace(
    _ctx=_admin_dep,
    user_id:  Optional[str]   = Query(None),
    trace_id: Optional[str]   = Query(None),
    category: Optional[str]   = Query(None),
    level:    Optional[str]   = Query(None),
    since_ts: Optional[float] = Query(None),
    until_ts: Optional[float] = Query(None),
    limit:    int = Query(200, ge=1, le=1000),
    tracer:   AdminTracer = Depends(lambda: admin_tracer),
) -> Dict[str, Any]:
    events = tracer.issue_trace(
        user_id=user_id, trace_id=trace_id, category=category,
        level=level, since_ts=since_ts, until_ts=until_ts, limit=limit)
    return {"events": events, "total": len(events), "summary": tracer.summary(),
            "query": {"user_id": user_id, "trace_id": trace_id,
                      "category": category, "level": level}}


@router.get("/trace/export.csv")
async def export_trace_csv(
    _ctx=_admin_dep,
    user_id:  Optional[str]   = Query(None),
    category: Optional[str]   = Query(None),
    since_ts: Optional[float] = Query(None),
    limit:    int = Query(5000, ge=1, le=50000),
    tracer:   AdminTracer = Depends(lambda: admin_tracer),
) -> StreamingResponse:
    csv_content = tracer.export_csv(user_id=user_id, category=category,
                                     since_ts=since_ts, limit=limit)
    filename = f"trace_{int(time.time())}.csv"
    return StreamingResponse(
        iter([csv_content]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.post("/alert/test")
async def fire_test_alert(
    _ctx=_admin_dep,
    message: str = Query("Admin test alert", max_length=200),
    manager: AlertManager = Depends(lambda: alert_manager),
) -> Dict[str, Any]:
    sent = await manager.fire("test", context={"message": message, "actor": "admin"})
    return {"sent": sent, "stats": manager.stats()}


@router.get("/health/deep")
async def deep_health(
    _ctx=_admin_dep,
    registry: MetricsRegistry = Depends(lambda: metrics),
    manager:  AlertManager    = Depends(lambda: alert_manager),
    tracer:   AdminTracer     = Depends(lambda: admin_tracer),
) -> Dict[str, Any]:
    snap = registry.admin_snapshot()
    kpis = snap.get("saas_kpis", {})
    issues: List[str] = []
    if kpis.get("kill_switch_active"):
        issues.append("kill_switch_active")
    if kpis.get("license_failures_total", 0) > 10:
        issues.append("high_license_failures")
    if kpis.get("heartbeat_losses_total", 0) > 5:
        issues.append("heartbeat_losses")
    if kpis.get("reconciliation_mismatches_total", 0) > 0:
        issues.append("reconciliation_mismatch")
    if kpis.get("equity_drawdown_pct", 0) >= 10.0:
        issues.append("critical_drawdown")
    status = "healthy"
    if issues:
        status = "degraded" if len(issues) < 3 else "unhealthy"
    return {"status": status, "issues": issues, "metrics": snap,
            "alert_stats": manager.stats(), "trace_summary": tracer.summary(),
            "ts": time.time()}
