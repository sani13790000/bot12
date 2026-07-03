"""backend/license/routes.py - Phase 6 License API routes."""
from __future__ import annotations
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger("license.routes")
router = APIRouter(prefix="/license", tags=["license"])


class HeartbeatRequest(BaseModel):
    license_id: str
    nonce: str


class HeartbeatResponse(BaseModel):
    valid: bool
    message: str


class DeviceRegisterRequest(BaseModel):
    license_id: str
    device_id: str


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(req: HeartbeatRequest) -> HeartbeatResponse:
    """License heartbeat endpoint."""
    return HeartbeatResponse(valid=True, message="OK")


@router.post("/device/register")
async def register_device(req: DeviceRegisterRequest) -> dict:
    """Register a device for a license."""
    return {"device_id": req.device_id, "registered": True}


@router.delete("/device/{device_id}")
async def remove_device(device_id: str) -> dict:
    """Remove a registered device."""
    return {"device_id": device_id, "removed": True}
