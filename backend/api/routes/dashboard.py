"""backend/api/routes/dashboard.py"""
from __future__ import annotations
from fastapi import APIRouter
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/")
async def dashboard_root() -> dict:
    return {"status": "ok", "module": "dashboard"}

@router.get("/summary")
async def dashboard_summary() -> dict:
    return {"summary": {}}

__all__ = ["router"]
