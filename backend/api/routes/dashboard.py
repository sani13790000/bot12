"""
backend/api/routes/dashboard.py
Galaxy Vast AI Trading Platform
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# BUG-AF1 FIX: removed prefix="/dashboard" -- double prefix was causing /dashboard/dashboard/*
router = APIRouter(tags=["dashboard"])


def _ok(data: Any) -> Dict[str, Any]:
    return {"status": "ok", "data": data}


def _err(msg: str, code: int = 500) -> JSONResponse:
    return JSONResponse({"status": "error", "message": msg}, status_code=code)


@router.get("/summary")
async def get_summary() -> Dict[str, Any]:
    try:
        summary: Dict[str, Any] = {}
        try:
            from backend.execution.mt5_connector import mt5_connector
            account = await mt5_connector.get_account_info()
            summary["account"] = account
        except Exception as exc:
            logger.warning("[dashboard] account unavailable: %s", exc)
            summary["account"] = None
        try:
            from backend.risk.kill_switch import kill_switch
            summary["kill_switch_active"] = kill_switch.is_active()
        except Exception:
            summary["kill_switch_active"] = None
        try:
            from backend.execution.order_state_machine import order_state_machine
            summary["active_positions"] = len(order_state_machine.active_tickets())
            summary["state_stats"] = order_state_machine.stats()
        except Exception:
            summary["active_positions"] = None
        return _ok(summary)
    except Exception as exc:
        logger.exception("[dashboard] /summary error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/positions")
async def get_positions() -> Dict[str, Any]:
    try:
        from backend.execution.mt5_connector import mt5_connector
        positions = await mt5_connector.get_all_positions()
        data = [{"ticket": p.ticket, "symbol": p.symbol, "direction": p.direction, "volume": p.volume, "open_price": p.open_price, "current_price": p.current_price, "profit": p.profit, "sl": p.sl, "tp": p.tp} for p in positions]
        return _ok(data)
    except Exception as exc:
        logger.exception("[dashboard] /positions error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/performance")
async def get_performance(days: int = Query(default=30, ge=1, le=365)) -> Dict[str, Any]:
    try:
        from backend.analytics.analytics_service import analytics_service
        stats = await analytics_service.get_performance_stats(days=days)
        return _ok(stats)
    except Exception as exc:
        logger.exception("[dashboard] /performance error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health")
async def get_health() -> Dict[str, Any]:
    health: Dict[str, Any] = {}
    try:
        from backend.database.client import db_client
        await db_client.ping()
        health["database"] = "healthy"
    except Exception as exc:
        health["database"] = f"unhealthy: {exc}"
    try:
        from backend.execution.mt5_connector import mt5_connector
        health["mt5"] = "connected" if mt5_connector._connected else "disconnected"  # noqa: SLF001
    except Exception:
        health["mt5"] = "unknown"
    return _ok(health)


@router.get("/recent-signals")
async def get_recent_signals(limit: int = Query(default=10, ge=1, le=100)) -> Dict[str, Any]:
    try:
        from backend.database.client import db_client
        rows = await db_client.select("signals", limit=limit, order="created_at.desc")
        return _ok(rows or [])
    except Exception as exc:
        logger.exception("[dashboard] /recent-signals error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
