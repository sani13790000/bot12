from __future__ import annotations
import asyncio, time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional
from fastapi import APIRouter
from ..core.logger import get_logger
from ..core.config_v11 import Settings

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
_settings   = Settings()

async def _check_database(settings: Settings) -> ComponentHealth:
    """Check Supabase DB connectivity."""
    t0 = time.monotonic()
    try:
        from ..database.connection import get_db_client
        db = get_db_client()
        result = db.table("signals").select("id").limit(1).execute()
        latency = time.monotonic() - t0
        return ComponentHealth(
            name="database", status=HealthStatus.HEALTHY, latency=round(latency, 3),
            detail={"rows": len(result.data)}
        )
    except Exception as e:
        return ComponentHealth(
            name="database", status=HealthStatus.UNHEALTHY,
            error=str(e), latency=round(time.monotonic() - t0, 3)
        )

async def _check_mt5(settings: Settings) -> ComponentHealth:
    """Check MT5 gateway connectivity."""
    import httpx
    t0 = time.monotonic()
    try:
        gw_url = getattr(settings, "MT5_GATEWAY_URL", "http://localhost:8080")
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{gw_url}/ping")
            data = r.json()
            latency = time.monotonic() - t0
            return ComponentHealth(
                name="mt5_gateway",
                status=HealthStatus.HEALTHY if data.get("mt5_connected") else HealthStatus.DEGRADED,
                latency=round(latency, 3),
                detail={"mt5_connected": data.get("mt5_connected"), "uptime": data.get("uptime_seconds")}
            )
    except Exception as e:
        return ComponentHealth(
            name="mt5_gateway", status=HealthStatus.UNHEALTHY,
            error=str(e), latency=round(time.monotonic() - t0, 3)
        )

async def _check_kill_switch() -> ComponentHealth:
    """Check Kill Switch state."""
    try:
        from ..risk.kill_switch import KillSwitch
        ks = KillSwitch()
        active = await ks.is_active()
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
        from ..middleware.rate_limit import get_rate_limiter
        rl = await get_rate_limiter()
        mode = getattr(rl, "mode", "unknown")
        return ComponentHealth(
            name="redis",
            status=HealthStatus.HEALTHY if mode == "redis" else HealthStatus.DEGRADED,
            detail={"mode": mode}
        )
    except Exception as e:
        return ComponentHealth(name="redis", status=HealthStatus.UNHEALTHY, error=str(e))

@router.get("/health")
async def health_check():
    """Full health check — all components."""
    t0 = time.monotonic()
    checks: List[ComponentHealth] = await asyncio.gather(
        _check_database(_settings),
        _check_mt5(_settings),
        _check_kill_switch(),
        _check_redis(),
        return_exceptions=False
    )
    overall = (
        HealthStatus.UNHEALTHY if any(c.status == HealthStatus.UNHEALTHY for c in checks)
        else HealthStatus.DEGRADED if any(c.status == HealthStatus.DEGRADED for c in checks)
        else HealthStatus.HEALTHY
    )
    return {
        "status": overall,
        "uptime_seconds": round(time.monotonic() - _start_time),
        "latency_ms": round((time.monotonic() - t0) * 1000, 1),
        "components": [
            {"name": c.name, "status": c.status, "latency_ms": round((c.latency or 0) * 1000, 1),
             "error": c.error, "detail": c.detail}
            for c in checks
        ],
        "environment": getattr(_settings, "APP_ENV", "unknown"),
        "version": getattr(_settings, "APP_VERSION", "unknown"),
    }

@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe — fast, no external calls."""
    return {"status": "ok", "uptime_seconds": round(time.monotonic() - _start_time)}

@router.get("/ready")
async def readiness_check():
    """
    Kubernetes readiness probe.
    O-FIX-2: برمی‌گرداند 503 (نه 500) اگر DB یا MT5 قطع باشد.
    """
    from fastapi import Response
    checks: List[ComponentHealth] = await asyncio.gather(
        _check_database(_settings),
        _check_mt5(_settings),
        return_exceptions=False
    )
    unhealthy = [c for c in checks if c.status == HealthStatus.UNHEALTHY]
    body = {
        "status": "ready" if not unhealthy else "not_ready",
        "checks": [
            {"name": c.name, "status": c.status, "error": c.error}
            for c in checks
        ]
    }
    if unhealthy:
        # O-FIX-2: 503 Service Unavailable (نه 500 Internal Server Error)
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=body)
    return body
