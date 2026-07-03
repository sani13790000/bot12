"""License management API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.license.engine import LicenseEngine
from backend.license.dependency import verify_license

router = APIRouter(prefix="/license", tags=["license"])
_engine = LicenseEngine()


class GenerateRequest(BaseModel):
    user_id: str
    plan: str = "pro"
    expires_days: int = 365


@router.post("/generate")
async def generate_license(req: GenerateRequest) -> dict:
    """Generate a new license key."""
    key = _engine.generate(req.user_id, req.plan, req.expires_days)
    return {"key": key, "user": req.user_id, "plan": req.plan}


@router.get("/validate")
async def validate_license(info: dict = Depends(verify_license)) -> dict:
    """Validate and return license details."""
    return info


@router.get("/status")
async def license_status(info: dict = Depends(verify_license)) -> dict:
    """Return current license status."""
    return {"active": True, "plan": info.get("plan"), "expires_at": info.get("expires_at")}
