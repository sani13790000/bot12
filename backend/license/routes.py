"""
backend/license/routes.py
Galaxy Vast AI - License API Routes (Phase 6)
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger       = logging.getLogger(__name__)
router       = APIRouter(prefix="/license",       tags=["license"])
admin_router = APIRouter(prefix="/admin/license", tags=["license-admin"])


class HeartbeatIn(BaseModel):
    license_id: str
    device_id:  str
    nonce:      str
    timestamp:  float
    signature:  str


class HeartbeatOut(BaseModel):
    ok: bool; status: str; tier: str
    features: List[str]; expires_at: float
    nonce: str; signature: str


class DeviceRegisterIn(BaseModel):
    license_id: str
    device_id:  str


class LicenseCreateIn(BaseModel):
    user_id: str; tier: str
    device_limit: int = 3
    features: List[str] = []
    expires_days: Optional[int] = 365


class LicenseActionIn(BaseModel):
    license_id: str
    reason: str = ""


def _engine():
    from backend.license.engine import LicenseEngine
    from backend.core.config import get_settings
    return LicenseEngine(secret_key=get_settings().LICENSE_SECRET_KEY)


@router.post("/heartbeat", response_model=HeartbeatOut)
async def heartbeat(body: HeartbeatIn) -> HeartbeatOut:
    from backend.license.engine import HeartbeatRequest
    resp = _engine().verify_heartbeat(HeartbeatRequest(
        license_id=body.license_id, device_id=body.device_id,
        nonce=body.nonce, timestamp=body.timestamp, signature=body.signature,
    ))
    return HeartbeatOut(ok=resp.ok, status=resp.status, tier=resp.tier,
        features=resp.features, expires_at=resp.expires_at, nonce=resp.nonce, signature=resp.signature)


@router.post("/device/register", status_code=201)
async def register_device(body: DeviceRegisterIn) -> Dict[str, Any]:
    if not _engine().register_device(body.license_id, body.device_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Device limit reached or license inactive")
    return {"registered": True, "device_id": body.device_id}


@router.get("/my")
async def get_my_license(license_id: str) -> Dict[str, Any]:
    record = _engine()._get_license(license_id)
    if record is None:
        raise HTTPException(404, detail="License not found")
    return {"license_id": record.license_id, "status": record.status.value,
            "tier": record.tier.value, "features": record.features,
            "device_count": record.device_count, "device_limit": record.device_limit,
            "expires_at": record.expires_at}


@router.get("/features")
async def get_features(license_id: str) -> Dict[str, Any]:
    record = _engine()._get_license(license_id)
    if record is None:
        raise HTTPException(404, detail="License not found")
    return {"features": record.features, "tier": record.tier.value}


@admin_router.post("/create", status_code=201)
async def create_license(body: LicenseCreateIn) -> Dict[str, Any]:
    license_id = str(uuid.uuid4())
    raw_key    = str(uuid.uuid4()).replace("-", "")
    expires_at = time.time() + (body.expires_days or 365) * 86400
    logger.info("LICENSE CREATED | id=%s | user=%s | tier=%s", license_id, body.user_id, body.tier)
    return {"license_id": license_id, "raw_key": raw_key, "tier": body.tier, "expires_at": expires_at}


@admin_router.post("/revoke")
async def revoke_license(body: LicenseActionIn) -> Dict[str, Any]:
    if not _engine().revoke_license(body.license_id, admin_id="admin", reason=body.reason):
        raise HTTPException(404, detail="License not found")
    return {"revoked": True, "license_id": body.license_id}
