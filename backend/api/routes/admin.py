"""
backend/api/routes/admin.py
P9-FEAT-65: Admin routes - users / licenses / devices / logs / kill-switch
P9-SEC-4: all actions logged in audit_log
P9-SEC-5: no internal stack traces in error responses
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.core.deps_v2 import get_auth_context, AuthContext, require_perm
from backend.core.audit_log import AuditLog, AuditEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

AdminCtx = Depends(require_perm("admin:all"))


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AdminDeviceOut(BaseModel):
    device_id:  str
    user_id:    str
    created_at: str
    active:     bool


# ---------------------------------------------------------------------------
# Device management
# ---------------------------------------------------------------------------

@router.get("/devices", response_model=list[AdminDeviceOut])
async def list_devices(
    user_id: Optional[str] = Query(None),
    ctx: AuthContext         = AdminCtx,
) -> list[AdminDeviceOut]:
    """List all registered devices, optionally filtered by user."""
    from backend.services.license_service import LicenseService
    rows = await LicenseService.list_devices(user_id=user_id)
    return [AdminDeviceOut(**r) for r in rows]


@router.post("/devices/revoke", status_code=204)
async def revoke_device(
    body: dict,
    ctx:  AuthContext = AdminCtx,
) -> None:
    """Revoke a registered device."""
    device_id = str(body.get("device_id", "")).strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id required")
    from backend.services.license_service import LicenseService
    await LicenseService.revoke_device(device_id)
    await AuditLog.log(AuditEvent(
        actor   = ctx.user_id,
        action  = "device.revoke",
        target  = device_id,
        outcome = "success",
    ))
