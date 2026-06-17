"""
سیستم لایسنس

نویسنده: MT5 Trading Team
"""

from .manager import (
    license_manager,
    LicenseManager,
    LicenseType,
    PermissionLevel,
    Feature,
    LICENSE_FEATURES,
    LICENSE_DURATION
)

__all__ = [
    "license_manager",
    "LicenseManager",
    "LicenseType",
    "PermissionLevel",
    "Feature",
    "LICENSE_FEATURES",
    "LICENSE_DURATION"
]
