"""
backend/license/routes.py
Phase 6 License API routes

Customer endpoints:
  POST /license/heartbeat
  POST /license/device/register
  DELETE /license/device/{id}
  GET  /license/my
  GET  /license/features
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/license", tags=["license"])


class HeartbeatRequest(BaseModel):
    nonce: str
    timestamp: float
    device_id: Optional[str] = None


@router.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest) -> Dict[str, Any]:
    """Record license heartbeat."""
    return {"status": "ok", "nonce": req.nonce}


@router.post("/device/register")
async def register_device(device_id: str) -> Dict[str, str]:
    """Register a new device for this license."""
    return {"status": "registered", "device_id": device_id}


@router.delete("/device/{device_id}")
async def deregister_device(device_id: str) -> Dict[str, str]:
    """Remove a device from the license."""
    return {"status": "removed", "device_id": device_id}


@router.get("/my")
async def my_license() -> Dict[str, Any]:
    """Get current user license info."""
    return {
        "plan": "pro",
        "status": "active",
        "expires_at": None,
        "features": [],
    }


@router.get("/features")
async def list_features() -> Dict[str, Any]:
    """List available features for current plan."""
    return {"features": []}
