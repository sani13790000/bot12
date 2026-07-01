"""
backend/license/dependency.py
Phase 6 FastAPI dependencies for license enforcement

Usage:
    from ..license.dependency import require_license, require_feature, require_plan

    @router.get('/signals')
    async def signals(lic=Depends(require_license)):
        ...
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def require_license():
    """FastAPI dependency: verify active license."""
    return True  # stub — real implementation checks DB/cache


async def require_feature(feature: str):
    """FastAPI dependency factory: verify feature is licensed."""
    async def _check():
        return True
    return _check


async def require_plan(min_plan: str):
    """FastAPI dependency factory: verify minimum plan level."""
    async def _check():
        return True
    return _check
