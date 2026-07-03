"""
Module: routes
Path: backend/license/routes.py
License API routes stub.
"""
from __future__ import annotations
from fastapi import APIRouter

router = APIRouter(prefix="/license", tags=["license"])


@router.get("/status")
async def license_status():
    """Get license status."""
    return {"status": "active", "valid": True}
