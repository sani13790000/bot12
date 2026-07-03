"""
Module: dashboard
Path: backend/api/routes/dashboard.py
Note: Original file had unrecoverable syntax errors. Stub generated.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/")
async def get_dashboard():
    """Dashboard overview endpoint."""
    return {"status": "ok", "message": "Dashboard endpoint stub"}
