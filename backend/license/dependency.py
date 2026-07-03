"""License dependency injection -- FastAPI Depends helper."""
from __future__ import annotations
from fastapi import Depends, HTTPException, Header
from backend.license.engine import LicenseEngine

_engine = LicenseEngine()


async def verify_license(x_license_key: str = Header(...)) -> dict:
    """FastAPI dependency that validates the license key on every request."""
    result = _engine.validate(x_license_key)
    if not result.get("valid"):
        raise HTTPException(status_code=403, detail="Invalid or expired license")
    return result
