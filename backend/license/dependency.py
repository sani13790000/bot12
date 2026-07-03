"""
backend/license/dependency.py
Galaxy Vast AI - FastAPI License Dependencies (Phase 6)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List

from fastapi import Depends, HTTPException, status

logger = logging.getLogger(__name__)


@dataclass
class LicenseCheckResult:
    license_id: str
    tier:       str
    features:   List[str]
    user_id:    str


def _get_engine():
    from backend.license.engine import LicenseEngine
    from backend.core.config import get_settings
    return LicenseEngine(secret_key=get_settings().LICENSE_SECRET_KEY)


def _get_license_id(authorization: str = "") -> str:
    return authorization.replace("Bearer ", "").strip() or "unknown"


def require_license() -> Callable:
    """Verify an active license exists."""
    def _dep(license_id: str = Depends(_get_license_id)) -> LicenseCheckResult:
        engine = _get_engine()
        record = engine._get_license(license_id)
        if record is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid license")
        from backend.license.engine import LicenseStatus
        if record.status != LicenseStatus.ACTIVE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"License {record.status.value}")
        return LicenseCheckResult(license_id=license_id, tier=record.tier.value, features=record.features, user_id=record.user_id)
    return _dep


def require_feature(feature_name: str) -> Callable:
    """Verify license includes a specific feature."""
    def _dep(lic: LicenseCheckResult = Depends(require_license())) -> LicenseCheckResult:
        if feature_name not in lic.features:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Feature not included: {feature_name}")
        return lic
    return _dep


def require_plan(minimum_tier: str) -> Callable:
    """Verify license meets minimum tier."""
    tier_rank = {"FREE": 0, "STARTER": 1, "PRO": 2, "ENTERPRISE": 3}
    req_rank  = tier_rank.get(minimum_tier.upper(), 99)
    def _dep(lic: LicenseCheckResult = Depends(require_license())) -> LicenseCheckResult:
        if tier_rank.get(lic.tier.upper(), -1) < req_rank:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Requires {minimum_tier} or higher")
        return lic
    return _dep
