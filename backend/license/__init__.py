"""
سیستم لایسنس

نویسنده: MT5 Trading Team
"""

from .manager import (
    LICENSE_DURATION,
    LICENSE_FEATURES,
    Feature,
    LicenseManager,
    LicenseType,
    PermissionLevel,
    license_manager,
)

__all__ = [
    "license_manager",
    "LicenseManager",
    "LicenseType",
    "PermissionLevel",
    "Feature",
    "LICENSE_FEATURES",
    "LICENSE_DURATION",
]
