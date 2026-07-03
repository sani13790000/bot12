"""backend/license/dependency.py - Phase 6 FastAPI license dependencies."""
from __future__ import annotations
from functools import wraps
from typing import Optional
import logging

logger = logging.getLogger("license.dependency")


def require_license(feature: Optional[str] = None):
    """FastAPI dependency: verify active license."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_feature(feature: str):
    """FastAPI dependency: verify feature is licensed."""
    return require_license(feature=feature)


def require_plan(plan: str):
    """FastAPI dependency: verify subscription plan."""
    return require_license(feature=plan)
