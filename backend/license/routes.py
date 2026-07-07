"""
Galaxy Vast AI Trading Platform
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
madul: backend/license/routes.py

ä¸­åˆ†åº“:
  REST endpoints Ø¨Ø±Ó¹ mØ¼Ø¯Ø¯ÙšÚ­ Ù„Ø§ÙŠÙ¶*õ¥Ù±s Ù‚Ø§ØªÒ­:
    â€¢ ÑÁØ§Ù„-Ø°Ó¹ Ù„Ø§ÙŠÙ¶*õ¥Ù±s
    â€¢ Ø«Ø¨ Ø¯Ø³ØªØ¯
    â€¢ heartbeat
    â€¢ Ø¨Ø±Ø±Ù· ÙˆØ²Ø¸Ó¹
    â‚‚ Ø·Ú¯Ùˆ Ù„Ø§ÙŠÙ¶*õ¥Ù±s
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.deps_v2 import AuthContext, get_auth_context
from backend.license.engine import LicenseEngine, LicenseStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/license", tags=["license"])
_engine = LicenseEngine()


class ActivateRequest(BaseModel):
    license_key: str = Field(..., min_length=10)
    device_id: str = Field(..., min_length=8)
    device_name: str = Field(..., max_length=64)


class HeartbeatRequest(BaseModel):
    device_id: str = Field(..., min_length=8)
    nonce: str = Field(..., min_length=16)


class LicenseStatusResponse(BaseModel):
    license_id: str
    plan: str
    state: str
    expires_at: str
    devices_active: int
    device_limit: int
    is_valid: bool
    days_remaining: Optional[int]


class ActivateResponse(BaseModel):
    license_id: str
    plan: str
    expires_at: str
    device_id: str
    token: str


@router.post("/activate", response_model=ActivateResponse, status_code=status.HTTP_201_CREATED)
async def activate_license(
    body: ActivateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> ActivateResponse:
    """Ø¡Ø¹Ó½Ø¼`Ù°Ø³Ó¹ Ù„Ø§ÙŠÙ–Ø«Ö•`e 4ßŽ ØªÓŒØ«Ø¨ Ø¯Ø³ØªØ¯."""
    try:
        result = await _engine.activate(
            user_id=ctx.user_id,
            license_key=body.license_key,
            device_id=body.device_id,
            device_name=body.device_name,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    logger.info("license.activated user=%s device=%s", ctx.user_id, body.device_id)
    return ActivateResponse(**result)


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def heartbeat(
    body: HeartbeatRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> None:
    """Ø¥Ù’Ø§Ù„ heartbeat Ø¯ÙˆÙ’Ù….â€"""
    try:
        await _engine.heartbeat(user_id=ctx.user_id, device_id=body.device_id, nonce=body.nonce)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc))


@router.get("/status", response_model=LicenseStatusResponse)
async def get_license_status(
    ctx: AuthContext = Depends(get_auth_context),
) -> LicenseStatusResponse:
    """ÙˆÖÓ¸Ó¹ Ù„Ø§ÙŠÙ–Ø«Ö•e3ØªÙ…Ú­ ÙƒØ§ØªØ¨Ø³."""
    info = await _engine.get_status(user_id=ctx.user_id)
    if info is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ù½Ø§ÙŠÙ–Ø«Ö•`7ØªÙ… YŠÙœ")
    return LicenseStatusResponse(
        license_id=info["license_id"],
        plan=info["plan"],
        state=info["state"],
        expires_at=info["expires_at"],
        devices_active=info["devices_active"],
        device_limit=info["device_limit"],
        is_valid=info["state"] == LicenseStatus.ACTIVE.value,
        days_remaining=info.get("days_remaining"),
    )


@router.post("/revoke-device", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(
    body: dict,
    ctx: AuthContext = Depends(get_auth_context),
) -> None:
    """Ù„Ø³Ú¯Ùˆ ÖªØ«Ø¨ Ø¯Ø³ØªØ¯."""
    device_id = (body.get("device_id") or "").strip()
    if not device_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="device_id Ù„Ø°Þ´« Ø§Ø³t")
    try:
        await _engine.revoke_device(user_id=ctx.user_id, device_id=device_id)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/devices")
async def list_devices(ctx: AuthContext = Depends(get_auth_context)) -> list:
    """Ù½Ø§ÙŠÙ–Ø«Ö•`7 Ø±ØªÙ…."""
    return await _engine.list_devices(user_id=ctx.user_id)
