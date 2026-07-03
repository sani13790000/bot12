"""
backend/license/dependency.py
Galaxy Vast AI - FastAPI License Dependencies (Phase 6)

Usage:
    from backend.license.dependency import require_license, require_feature, require_plan
"""
from __future__ import annotations
from typing import Callable
from fastapi import Depends, HTTPException, status
from backend.core.auth import get_current_active_user
from backend.core.models import User
from backend.license.engine import LicenseEngine

_engine = LicenseEngine()


async def require_license(current_user: User = Depends(get_current_active_user)) -> None:
    """Only users with active license can pass."""
    ok = await _engine.is_active(current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="License expired or not found.")


def require_feature(feature: str) -> Callable:
    """Check access to a specific feature."""
    async def _dep(current_user: User = Depends(get_current_active_user)) -> None:
        has_it = await _engine.has_feature(current_user.id, feature)
        if not has_it:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Your plan does not include feature: {feature}")
    return _dep


def require_plan(plan_name: str) -> Callable:
    """Check that user is on at least the specified plan."""
    async def _dep(current_user: User = Depends(get_current_active_user)) -> None:
        meets = await _engine.meets_plan(current_user.id, plan_name)
        if not meets:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"This endpoint requires plan: {plan_name}")
    return _dep
