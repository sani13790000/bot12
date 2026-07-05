"""
backend/api/routes/health.py
Galaxy Vast AI Trading Platform

FIXES APPLIED:
  BUG-R4-2: kill_switch.is_active() with () -> TypeError
             Fixed: kill_switch.is_active (no parentheses -- it is @property)
  CB-3:     db.ping() -> get_db_client()
  CB-7:     mt5_ok dict -> .get("ok", False)
  AI-1:     /live endpoint for Docker HEALTHCHECK
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.core.logger import get_logger

logger = get_logger("api.routes.health")
router = APIRouter(tags=["Health"])

_start_time = time.time()


@router.get("", summary="Full health check -- all components")
async def health_check() -> JSONResponse:
    t0 = time.monotonic()
    result: Dict[str, Any] = {
        "status": "ok",
        "uptime_seconds": round(time.monotonic() - _start_time),
        "latency_ms": 0.0,
    }
    errors = []

    try:
        from backend.database.connection import get_db_client
        client = await asyncio.wait_for(get_db_client(), timeout=2.0)
        result["database"] = "ok" if client else "degraded"
        if not client:
            errors.append("database")
    except Exception as exc:
        result["database"] = f"error: {str(exc)[:80]}"
        errors.append("database")

    try:
        from backend.execution.mt5_connector import mt5_connector
        mt5_result = await asyncio.wait_for(mt5_connector.health_check(), timeout=3.0)
        mt5_ok = mt5_result.get("ok", False) if isinstance(mt5_result, dict) else bool(mt5_result)
        result["mt5_gateway"] = "ok" if mt5_ok else "degraded"
        result["mt5_mode"] = mt5_result.get("mode", "unknown") if isinstance(mt5_result, dict) else "unknown"
        if not mt5_ok:
            errors.append("mt5_gateway")
    except Exception as exc:
        result["mt5_gateway"] = f"error: {str(exc)[:80]}"
        errors.append("mt5_gateway")

    # BUG-R4-2 FIX: is_active is @property -- NO parentheses
    try:
        from backend.risk.kill_switch import kill_switch
        ks_active = kill_switch.is_active  # was kill_switch.is_active() -> TypeError
        result["kill_switch"] = "ACTIVE" if ks_active else "inactive"
        if ks_active:
            errors.append("kill_switch")
    except Exception as exc:
        result["kill_switch"] = f"error: {str(exc)[:80]}"

    try:
        from backend.database.redis_client import redis_ping
        redis_ok = await asyncio.wait_for(redis_ping(), timeout=1.0)
        result["redis"] = "ok" if redis_ok else "degraded"
        if not redis_ok:
            errors.append("redis")
    except Exception as exc:
        result["redis"] = f"error: {str(exc)[:80]}"
        errors.append("redis")

    try:
        from backend.circuit_breaker import get_breaker_status
        result["circuit_breakers"] = get_breaker_status()
    except Exception:
        result["circuit_breakers"] = "unavailable"

    if errors:
        result["status"] = "degraded"
        result["degraded_components"] = errors

    result["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    status_code = 200 if result["status"] == "ok" else 503
    return JSONResponse(content=result, status_code=status_code)


@router.get("/live", summary="Liveness probe (Docker / Kubernetes)")
async def liveness() -> Dict[str, str]:
    """Fast liveness -- no external calls. Used by Docker HEALTHCHECK."""
    return {
        "status": "alive",
        "uptime_seconds": str(round(time.monotonic() - _start_time)),
    }


@router.get("/ready", summary="Readiness probe (Kubernetes)")
async def readiness() -> JSONResponse:
    ready = True
    checks: Dict[str, str] = {}
    try:
        from backend.database.connection import get_db_client
        client = await asyncio.wait_for(get_db_client(), timeout=1.0)
        checks["database"] = "ok" if client else "not_ready"
        if not client:
            ready = False
    except Exception:
        checks["database"] = "not_ready"
        ready = False
    return JSONResponse(
        content={"ready": ready, "checks": checks},
        status_code=200 if ready else 503,
    )
