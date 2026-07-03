"""backend/api/routes/health.py — Phase I Production Hardening
I-6: health endpoint with CB + DB + MT5 + Kill Switch
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])

_STARTUP_TIME = time.monotonic()


@router.get("/", summary="Health check")
async def health() -> JSONResponse:
    """Health check with all system components."""
    result: Dict[str, Any] = {
        "status": "ok",
        "uptime_seconds": round(time.monotonic() - _STARTUP_TIME, 1),
        "checks": {},
    }

    # Database
    try:
        from backend.database.connection import db
        ping = await asyncio.wait_for(db.ping(), timeout=2.0)
        result["checks"]["database"] = {"status": "ok" if ping else "degraded"}
    except asyncio.TimeoutError:
        result["checks"]["database"] = {"status": "timeout"}
    except Exception as exc:
        result["checks"]["database"] = {"status": "error", "detail": str(exc)[:80]}

    # MT5 Gateway
    try:
        from backend.execution.mt5_connector import mt5_connector
        mt5_ok = await asyncio.wait_for(mt5_connector.health_check(), timeout=3.0)
        result["checks"]["mt5_gateway"] = {
            "status": "ok" if mt5_ok else "degraded",
            "demo_mode": mt5_connector.demo,
        }
    except asyncio.TimeoutError:
        result["checks"]["mt5_gateway"] = {"status": "timeout"}
    except Exception as exc:
        result["checks"]["mt5_gateway"] = {"status": "error", "detail": str(exc)[:80]}

    # Kill Switch
    try:
        from backend.risk.kill_switch import kill_switch
        active = kill_switch.is_active()
        result["checks"]["kill_switch"] = {
            "status": "ACTIVE" if active else "inactive",
            "is_blocking": active,
        }
    except Exception as exc:
        result["checks"]["kill_switch"] = {"status": "unknown", "detail": str(exc)[:80]}

    # Circuit Breakers
    try:
        from backend.circuit_breaker import get_breaker_status
        result["checks"]["circuit_breakers"] = get_breaker_status()
    except Exception:
        result["checks"]["circuit_breakers"] = {"status": "unavailable"}

    # Rate Limiter
    try:
        from backend.middleware.rate_limit import get_rate_limiter
        rl = await get_rate_limiter()
        result["checks"]["rate_limiter"] = {
            "status": "ok",
            "backend": "redis" if getattr(rl, "_redis_client", None) else "in-memory",
        }
    except Exception:
        result["checks"]["rate_limiter"] = {"status": "ok", "backend": "in-memory"}

    # Overall Status
    errors = [
        k for k, v in result["checks"].items()
        if isinstance(v, dict) and v.get("status") in ("error", "timeout")
    ]
    if errors:
        result["status"] = "degraded"
        result["degraded_components"] = errors

    status_code = 200 if result["status"] == "ok" else 503
    return JSONResponse(content=result, status_code=status_code)


@router.get("/live", summary="Liveness probe (Kubernetes)")
async def liveness() -> Dict[str, str]:
    """Kubernetes liveness probe."""
    return {"status": "alive"}


@router.get("/ready", summary="Readiness probe (Kubernetes)")
async def readiness() -> JSONResponse:
    """Kubernetes readiness probe."""
    ready = True
    checks: Dict[str, str] = {}

    try:
        from backend.database.connection import db
        ping = await asyncio.wait_for(db.ping(), timeout=1.0)
        checks["database"] = "ok" if ping else "not_ready"
        if not ping:
            ready = False
    except Exception:
        checks["database"] = "not_ready"
        ready = False

    return JSONResponse(
        content={"ready": ready, "checks": checks},
        status_code=200 if ready else 503,
    )
