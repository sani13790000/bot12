"""Admin routes — Phase AD: double prefix fixed + real JWT auth."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.core.deps import get_current_user
from backend.risk.kill_switch import get_kill_switch

logger = logging.getLogger(__name__)
# BUG-AD1 fix: removed prefix="/admin" — main.py provides prefix="/admin"
router = APIRouter(tags=["admin"])


def _require_admin(user=Depends(get_current_user)) -> Any:
    """Real admin auth — requires role admin or superadmin via JWT. BUG-AD2 fix."""
    if not hasattr(user, "role") or user.role not in ("admin", "superadmin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user


class KillSwitchAction(BaseModel):
    reason: str = "Manual admin action"


class ConfigPatch(BaseModel):
    key: str
    value: Any


@router.get("/config")
async def get_config(_user=Depends(_require_admin)) -> Dict[str, Any]:
    """Return safe (non-secret) config values."""
    settings = get_settings()
    safe_fields = [
        "APP_NAME",
        "APP_VERSION",
        "ENVIRONMENT",
        "DEBUG",
        "MT5_GATEWAY_MODE",
        "KILL_SWITCH_MAX_DAILY_LOSS_PCT",
        "KILL_SWITCH_MAX_DRAWDOWN_PCT",
        "KILL_SWITCH_MAX_CONSECUTIVE_LOSSES",
        "MARGIN_GATE_MIN_FREE_MARGIN",
        "MARGIN_GATE_FAIL_CLOSED_MULTIPLIER",
        "SIGNAL_MIN_CONFIDENCE",
        "SIGNAL_MIN_RR",
        "RETRAINING_INTERVAL_HOURS",
        "RETRAINING_MIN_SAMPLES",
        "LOG_LEVEL",
    ]
    return {
        field: getattr(settings, field, None) for field in safe_fields if hasattr(settings, field)
    }


@router.get("/users")
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user=Depends(_require_admin),
) -> Dict[str, Any]:
    """List registered users from database."""
    from backend.database.connection import get_db_client

    try:
        db = get_db_client()
        result = (
            db.table("users")
            .select("id, email, created_at, is_active, role")
            .range(offset, offset + limit - 1)
            .execute()
        )
        return {"users": result.data, "count": len(result.data), "offset": offset, "limit": limit}
    except Exception as exc:
        logger.error("list_users failed: %s", exc)
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.post("/kill")
async def activate_kill_switch(
    body: KillSwitchAction, _user=Depends(_require_admin)
) -> Dict[str, Any]:
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
async def deactivate_kill_switch(
    body: KillSwitchAction, _user=Depends(_require_admin)
) -> Dict[str, Any]:
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
async def kill_switch_status(_user=Depends(_require_admin)) -> Dict[str, Any]:
    """Get kill switch state + statistics."""
    ks = get_kill_switch()
    return {
        "active": ks.is_active,
        "stats": ks.stats(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/logs")
async def get_recent_logs(
    lines: int = Query(100, ge=10, le=1000),
    level: str = Query("INFO", regex="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
    _user=Depends(_require_admin),
) -> Dict[str, Any]:
    """Return recent log lines from Redis ring buffer."""
    import json

    from backend.database.redis_client import get_redis

    r = await get_redis()
    if not r:
        return {"logs": [], "note": "Redis unavailable"}
    raw = await r.lrange("app_logs", 0, lines - 1)
    logs = []
    for entry in raw or []:
        try:
            logs.append(json.loads(entry))
        except Exception:
            logs.append({"message": entry})
    level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    min_level = level_order.get(level, 1)
    filtered = [rec for rec in logs if level_order.get(rec.get("level", "INFO"), 1) >= min_level]
    return {"logs": filtered, "count": len(filtered), "level_filter": level}


@router.get("/metrics/summary")
async def admin_metrics_summary(_user=Depends(_require_admin)) -> Dict[str, Any]:
    """Admin view of system metrics."""
    import json

    from backend.database.redis_client import get_redis

    r = await get_redis()
    cache: Dict[str, Any] = {}
    if r:
        for key in ["metrics:account", "metrics:performance", "metrics:ml_status"]:
            val = await r.get(key)
            if val:
                try:
                    cache[key] = json.loads(val)
                except Exception:
                    cache[key] = val
    return {"cached_metrics": cache, "timestamp": datetime.now(timezone.utc).isoformat()}
