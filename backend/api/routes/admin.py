"""Admin routes — Phase I: all endpoints fully implemented."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.risk.kill_switch import get_kill_switch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])
Settings = get_settings().__class__


# ── Auth dependency (simple API-key guard) ────────────────────

def _require_admin(x_admin_key: str = "") -> None:
    """Simple admin key check — replace with full JWT in production."""
    settings = get_settings()
    expected = getattr(settings, "ADMIN_API_KEY", None)
    if expected and x_admin_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key")


# ── Models ────────────────────────────────────────────────────

class KillSwitchAction(BaseModel):
    reason: str = "Manual admin action"


class ConfigPatch(BaseModel):
    key: str
    value: Any


# ── Endpoints ─────────────────────────────────────────────────

@router.get("/config")
async def get_config() -> Dict[str, Any]:
    """Return safe (non-secret) config values."""
    settings = get_settings()
    safe_fields = [
        "APP_NAME", "APP_VERSION", "ENVIRONMENT", "DEBUG",
        "MT5_GATEWAY_MODE", "KILL_SWITCH_MAX_DAILY_LOSS_PCT",
        "KILL_SWITCH_MAX_DRAWDOWN_PCT", "KILL_SWITCH_MAX_CONSECUTIVE_LOSSES",
        "MARGIN_GATE_MIN_FREE_MARGIN", "MARGIN_GATE_FAIL_CLOSED_MULTIPLIER",
        "SIGNAL_MIN_CONFIDENCE", "SIGNAL_MIN_RR",
        "RETRAINING_INTERVAL_HOURS", "RETRAINING_MIN_SAMPLES",
        "LOG_LEVEL",
    ]
    return {
        field: getattr(settings, field, None)
        for field in safe_fields
        if hasattr(settings, field)
    }


@router.get("/users")
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """List registered users from database."""
    from backend.database.connection import get_db_client  # lazy
    try:
        db = get_db_client()
        result = (
            db.table("users")
            .select("id, email, created_at, is_active, role")
            .range(offset, offset + limit - 1)
            .execute()
        )
        return {"users": result.data, "count": len(result.data), "offset": offset, "limit": limit}
    except Exception as exc:  # noqa: BLE001
        logger.error("list_users failed: %s", exc)
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.post("/kill")
async def activate_kill_switch(body: KillSwitchAction) -> Dict[str, Any]:
    """Activate kill switch — halts all trading immediately."""
    ks = get_kill_switch()
    await ks.activate(reason=body.reason)
    logger.critical("KILL SWITCH activated via admin API: %s", body.reason)
    return {
        "status": "activated",
        "reason": body.reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/resume")
async def deactivate_kill_switch(body: KillSwitchAction) -> Dict[str, Any]:
    """Deactivate kill switch — resumes trading."""
    ks = get_kill_switch()
    await ks.deactivate(reason=body.reason)
    logger.warning("KILL SWITCH deactivated via admin API: %s", body.reason)
    return {
        "status": "deactivated",
        "reason": body.reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/kill-switch")
async def kill_switch_status() -> Dict[str, Any]:
    """Get kill switch state + statistics."""
    ks = get_kill_switch()
    stats = ks.stats()
    return {
        "active": ks.is_active,
        "stats": stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/logs")
async def get_recent_logs(
    lines: int = Query(100, ge=10, le=1000),
    level: str = Query("INFO", regex="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
) -> Dict[str, Any]:
    """Return recent log lines from Redis ring buffer."""
    from backend.database.redis_client import get_redis  # lazy
    import json
    r = await get_redis()
    if not r:
        return {"logs": [], "note": "Redis unavailable"}
    raw = await r.lrange("app_logs", 0, lines - 1)
    logs = []
    for entry in (raw or []):
        try:
            logs.append(json.loads(entry))
        except Exception:  # noqa: BLE001
            logs.append({"message": entry})
    # Filter by level
    level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    min_level = level_order.get(level, 1)
    filtered = [l for l in logs if level_order.get(l.get("level", "INFO"), 1) >= min_level]
    return {"logs": filtered, "count": len(filtered), "level_filter": level}


@router.get("/metrics/summary")
async def admin_metrics_summary() -> Dict[str, Any]:
    """Admin view of system metrics."""
    from backend.database.redis_client import get_redis  # lazy
    import json
    r = await get_redis()
    cache: Dict[str, Any] = {}
    if r:
        keys = ["metrics:account", "metrics:performance", "metrics:ml_status"]
        for key in keys:
            val = await r.get(key)
            if val:
                try:
                    cache[key] = json.loads(val)
                except Exception:  # noqa: BLE001
                    cache[key] = val
    return {
        "cached_metrics": cache,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
