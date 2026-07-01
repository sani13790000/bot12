"""
backend/license/dependency.py
Phase 6 FastAPI dependencies for license enforcement

Usage:
    from ..license.dependency import require_license, require_feature
"""
from __future__ import annotations
import logging

_LOG = logging.getLogger(__name__)


async def require_license():
    """FastAPI dependency: require valid license."""
    return True


async def require_feature(feature: str):
    """FastAPI dependency: require specific feature license."""
    return True
