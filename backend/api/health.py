"""backend/api/health.py — Phase P fix

BUG-P5 FIX: _check_ml_model() added — ML model loaded status exposed in /health
  - If model not loaded: status=DEGRADED, not UNHEALTHY (non-blocking)
  - /ready only checks DB + MT5 (critical path)
  - /health checks all 5 components: DB, MT5, KillSwitch, Redis, MLModel
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from backend.core.logger import get_logger
from backend.core.config import get_settings

logger = get_logger("api.health")
router = APIRouter(tags=["health"])


class HealthStatus(str, Enum):
    HEALTHY   = "healthy"
    DEGRADED  = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    name:    str
    status:  HealthStatus
    latency: Optional[float] = None
    error:   Optional[str]   = None
    detail:  Dict[str, Any]  = field(default_factory=dict)


_start_time = time.time()


async def _check_database() -> ComponentHealth:
    """Check Supabase DB connectivity."""
    t0 = time.monotonic()
    try:
        from backend.database.connection import get_db_client
        client  = await asyncio.wait_for(get_db_client(), timeout=2.0)
        latency = time.monotonic() - t0
        if client:
            return ComponentHealth(
                name="database", status=HealthStatus.HEALTHY,
                latency=round(latency, 3), detail={"client": "ready"}
            )
        return ComponentHealth(
            name="database", status=HealthStatus.DEGRADED,
            latency=round(latency, 3), error="client returned None"
        )
    except Exception as e:
        return ComponentHealth(
            name="database", status=HealthStatus.UNHEALTHY,
            error=str(e), latency=round(time.monotonic() - t0, 3)
        )


async def _check_mt5() -> ComponentHealth:
    """Check MT5 gateway connectivity."""
    t0 = time.monotonic()
    try:
        from backend.execution.mt5_connector import mt5_connector
        result  = await asyncio.wait_for(mt5_connector.health_check(), timeout=5.0)
        latency = time.monotonic() - t0
        ok = result.get("ok", False) if isinstance(result, dict) else bool(result)
        return ComponentHealth(
            name="mt5_gateway",
            status=HealthStatus.HEALTHY if ok else HealthStatus.DEGRADED,
            latency=round(latency, 3),
            detail=result if isinstance(result, dict) else {"ok": ok}
        )
    except Exception as e:
        return ComponentHealth(
            name="mt5_gateway", status=HealthStatus.UNHEALTHY,
            error=str(e), latency=round(time.monotonic() - t0, 3)
        )


async def _check_kill_switch() -> ComponentHealth:
    """Check Kill Switch state."""
    try:
        from backend.risk.kill_switch import kill_switch
        active = kill_switch.is_active()
        return ComponentHealth(
            name="kill_switch",
            status=HealthStatus.DEGRADED if active else HealthStatus.HEALTHY,
            detail={"active": active}
        )
    except Exception as e:
        return ComponentHealth(name="kill_switch", status=HealthStatus.UNHEALTHY, error=str(e))


async def _check_redis() -> ComponentHealth:
    """Check Redis connectivity."""
    try:
        from backend.middleware.rate_limit import get_rate_limiter
        rl   = await get_rate_limiter()
        mode = getattr(rl, "mode", "unknown")
        return ComponentHealth(
            name="redis",
            status=HealthStatus.HEALTHY if mode == "redis" else HealthStatus.DEGRADED,
            detail={"mode": mode}
        )
    except Exception as e:
        return ComponentHealth(name="redis", status=HealthStatus.UNHEALTHY, error=str(e))


async def _check_ml_model() -> ComponentHealth:
    """BUG-P5 FIX: Check ML model loaded status.

    - model loaded + auc > 0.5 → HEALTHY
    - model not loaded yet    → DEGRADED (predictions use fallback, not crash)
    - import error            → DEGRADED (same)
    """
    try:
        from backend.ai_prediction.model_manager import ModelManager
        manager = ModelManager()
        info    = manager.get_model_info()  # returns dict with loaded, auc, path, etc.
        if info and info.get("loaded"):
            auc    = info.get("auc", 0.0)
            status = HealthStatus.HEALTHY if auc >= 0.5 else HealthStatus.DEGRADED
            return ComponentHealth(
                name="ml_model", status=status,
                detail={
                    "loaded":     True,
                    "auc":        round(auc, 4),
                    "model_path": info.get("path", ""),
                    "version":    info.get("version", "unknown"),
                }
            )
        return ComponentHealth(
            name="ml_model", status=HealthStatus.DEGRADED,
            detail={"loaded": False, "note": "model not yet trained — predictions use fallback"}
        )
    except Exception as e:
        return ComponentHealth(
            name="ml_model", status=HealthStatus.DEGRADED,
            error=str(e),
            detail={"loaded": False, "note": "check MODEL_DIR and run initial training"}
        )


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Full health check — all 5 components."""
    t0 = time.monotonic()
    checks: List[ComponentHealth] = await asyncio.gather(
        _check_database(),
        _check_mt5(),
        _check_kill_switch(),
        _check_redis(),
        _check_ml_model(),     # BUG-P5: ML model status added
        return_exceptions=False
    )
    overall = (
        HealthStatus.UNHEALTHY if any(c.status == HealthStatus.UNHEALTHY for c in checks)
        else HealthStatus.DEGRADED if any(c.status == HealthStatus.DEGRADED for c in checks)
        else HealthStatus.HEALTHY
    )
    _settings = get_settings()
    return {
        "status":          overall,
        "uptime_seconds":  round(time.monotonic() - _start_time),
        "latency_ms":      round((time.monotonic() - t0) * 1000, 1),
        "components": [
            {
                "name":       c.name,
                "status":     c.status,
                "latency_ms": round((c.latency or 0) * 1000, 1),
                "error":      c.error,
                "detail":     c.detail,
            }
            for c in checks
        ],
        "environment": _settings.APP_ENV,
        "version":     _settings.APP_VERSION,
    }


@router.get("/live")
async def liveness_check() -> Dict[str, Any]:
    """Kubernetes liveness probe — fast, no external calls."""
    return {"status": "ok", "uptime_seconds": round(time.monotonic() - _start_time)}


@router.get("/ready")
async def readiness_check() -> Any:
    """Kubernetes readiness probe — checks only critical path (DB + MT5)."""
    from fastapi.responses import JSONResponse
    checks: List[ComponentHealth] = await asyncio.gather(
        _check_database(),
        _check_mt5(),
        return_exceptions=False
    )
    unhealthy = [c for c in checks if c.status == HealthStatus.UNHEALTHY]
    body = {
        "status": "ready" if not unhealthy else "not_ready",
        "checks": [{"name": c.name, "status": c.status, "error": c.error} for c in checks]
    }
    if unhealthy:
        return JSONResponse(status_code=503, content=body)
    return body
