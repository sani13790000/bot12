"""
backend/license/routes.py
Galaxy Vast AI - License API Routes (Phase 6)

Endpoints:
    POST   /license/heartbeat
    POST   /license/device/register
    DELETE /license/device/{device_id}
    GET    /license/my
    GET    /license/devices
"""
from __future__ import annotations
import logging
from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from backend.core.auth import get_current_active_user
from backend.core.models import User
from backend.license.engine import LicenseEngine

log = logging.getLogger(__name__)
router = APIRouter(prefix="/license", tags=["license"])
_engine = LicenseEngine()


class HeartbeatRequest(BaseModel):
    device_fingerprint: str
    nonce: str
    timestamp: str


class DeviceRegisterRequest(BaseModel):
    device_fingerprint: str
    device_name: str = ""


@router.post("/heartbeat")
async def heartbeat(body: HeartbeatRequest, current_user: User = Depends(get_current_active_user)) -> dict:
    ok = await _engine.heartbeat(user_id=current_user.id, device_fingerprint=body.device_fingerprint, nonce=body.nonce, timestamp=body.timestamp)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Heartbeat rejected")
    return {"status": "ok"}


@router.post("/device/register")
async def register_device(body: DeviceRegisterRequest, current_user: User = Depends(get_current_active_user)) -> dict:
    ok = await _engine.register_device(user_id=current_user.id, device_fingerprint=body.device_fingerprint)
    if not ok:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device limit reached")
    return {"status": "registered"}


@router.delete("/device/{device_id}")
async def remove_device(device_id: UUID, current_user: User = Depends(get_current_active_user)) -> dict:
    await _engine.remove_device(user_id=current_user.id, device_id=device_id)
    return {"status": "removed"}


@router.get("/my")
async def my_license(current_user: User = Depends(get_current_active_user)) -> dict:
    active = await _engine.is_active(current_user.id)
    return {"user_id": str(current_user.id), "active": active, "status": "active" if active else "expired"}


@router.get("/devices")
async def list_devices(current_user: User = Depends(get_current_active_user)) -> dict:
    return {"user_id": str(current_user.id), "devices": []}
