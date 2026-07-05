"""
backend/api/routes/health.py — FIXED
Fixes:
  CB-3: db singleton + ping() removed → get_db_client() used correctly
  CB-7: mt5_ok dict evaluated as .get("ok") not bool(dict)
  AI-1: /live endpoint added here (Docker healthcheck target)
  AI-2: KillSwitch.is_active() called as sync (consistent interface)
  CB-1: /live liveness endpoint now present at /api/v1/health/live
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.core.logger import get_logger

logger = get_logger("api.routes.health")
router = APIRouter(tags=["Health"])

_start_time = time.time()


@router.get("", summary="Full health check — all components")
async def health_check() -> JSONResponse:
    """Full health check with all components."""
    t0 = time.monotonic()
    result: Dict[str, Any] = {
        "status": "ok",
        "uptime_seconds": round(time.monotonic() - _start_time),
        "latency_ms": 0.0,
    }
    errors = []

    # --- Database check (CB-3 FIX: use get_db_client, no db.ping()) ---
    try:
        from backend.database.connection import get_db_client
        client = await asyncio.wait_for(get_db_client(), timeout=2.0)
        if client:
            result["database"] = "ok"
        else:
            result["database"] = "degraded"
            errors.append("database")
    except Exception as exc:
        result["database"] = f"error: {str(exc)[:80]}"
        errors.append("database")

    # --- MT5 check (CB-7 FIX: evaluate dict["ok"] not bool(dict)) ---
    try:
        from backend.execution.mt5_connector import mt5_connector
        mt5_result = await asyncio.wait_for(
            mt5_connector.health_check(), timeout=3.0
        )
        # CB-7 FIX: mt5_result is a dict — check .get("ok") explicitly
        mt5_ok = mt5_result.get("ok", False) if isinstance(mt5_result, dict) else bool(mt5_result)
        result["mt5_gateway"] = "ok" if mt5_ok else "degraded"
        result["mt5_mode"] = mt5_result.get("mode", "unknown") if isinstance(mt5_result, dict) else "unknown"
        if not mt5_ok:
            errors.append("mt5_gateway")
    except Exception as exc:
        result["mt5_gateway"] = f"error: {str(exc)[:80]}"
        errors.append("mt5_gateway")

    # --- KillSwitch check (AI-2 FIX: consistent sync is_active()) ---
    try:
        from backend.risk.kill_switch import kill_switch
        # AI-2 FIX: use sync is_active() — single consistent interface
        ks_active = kill_switch.is_active()
        result["kill_switch"] = "ACTIVE" if ks_active else "inactive"
        if ks_active:
            errors.append("kill_switch")
    except Exception as exc:
        result["kill_switch"] = f"error: {str(exc)[:80]}"

    # --- Circuit breaker status ---
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


# CB-1 + AI-1 FIX: /live endpoint so Docker HEALTHCHECK URL works
@router.get("/live", summary="Liveness probe (Kubernetes / Docker)")
async def liveness() -> Dict[str, str]:
    """Kubernetes liveness probe — fast, no external calls."""
    return {"status": "alive", "uptime_seconds": str(round(time.monotonic() - _start_time))}


@router.get("/ready", summary="Readiness probe (Kubernetes)")
async def readiness() -> JSONResponse:
    """Kubernetes readiness probe."""
    ready = True
    checks: Dict[str, str] = {}

    # CB-3 FIX: use get_db_client() not db.ping()
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
