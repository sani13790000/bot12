"""backend/api/health.py - DO-3: production health endpoints"""
from __future__ import annotations
import asyncio
import os
import time
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["health"])
_start_time = time.time()


async def _check_redis() -> Dict[str, Any]:
    try:
        import redis.asyncio as aioredis
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = aioredis.from_url(url, socket_connect_timeout=2)
        t0 = time.monotonic()
        await r.ping()
        lat = round((time.monotonic() - t0) * 1000, 2)
        await r.aclose()
        return {"status": "ok", "latency_ms": lat}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


async def _check_db() -> Dict[str, Any]:
    try:
        from backend.database.connection import get_db_client
        t0 = time.monotonic()
        await get_db_client()
        return {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 2)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness() -> Dict[str, str]:
    """Liveness probe."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness() -> Dict[str, Any]:
    """Readiness probe - checks redis + db."""
    r, d = await asyncio.gather(_check_redis(), _check_db(), return_exceptions=True)
    if isinstance(r, Exception):
        r = {"status": "error", "error": str(r)}
    if isinstance(d, Exception):
        d = {"status": "error", "error": str(d)}
    ok = r.get("status") == "ok" and d.get("status") == "ok"
    payload: Dict[str, Any] = {
        "status": "ready" if ok else "degraded",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "checks": {"redis": r, "database": d},
    }
    if not ok:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=payload)
    return payload


@router.get("/health")
async def health_summary() -> Dict[str, Any]:
    """Health summary endpoint."""
    r, d = await asyncio.gather(_check_redis(), _check_db(), return_exceptions=True)
    if isinstance(r, Exception):
        r = {"status": "error", "error": str(r)}
    if isinstance(d, Exception):
        d = {"status": "error", "error": str(d)}
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "version": os.getenv("APP_VERSION", "unknown"),
        "checks": {"redis": r, "database": d},
    }
