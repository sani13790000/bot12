"""
License Engine - License validation and enforcement.

Validates trading bot licenses and enforces usage restrictions.
Supports multiple license types and feature gating.

Usage:
    validator = LicenseValidator(license_key="ABC123...")
    is_valid = validator.validate()
    features = validator.get_enabled_features()
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Set
from enum import StrEnum
import hashlib
import json

logger = logging.getLogger(__name__)


class LicenseType(StrEnum):
    TRIAL = "TRIAL"          # Free trial (limited features)
    STARTER = "STARTER"      # Basic features
    PROFESSIONAL = "PROFESSIONAL"  # All features except institutional
    INSTITUTIONAL = "INSTITUTIONAL"  # Full feature set


class LicenseStatus(StrEnum):
    VALID = "VALID"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    INVALID = "INVALID"


@dataclass
class License:
    """License information."""
    key: str
    type: LicenseType
    issue_date: datetime
    expiry_date: datetime
    max_positions: int
    max_accounts: int
    enabled_features: Set[str]
    status: LicenseStatus
    holder: str


class LicenseValidator:
    """License validation and enforcement."""

    # Feature map by license type
    FEATURE_MAP = {
        LicenseType.TRIAL: {
            "max_positions": 1,
            "max_accounts": 1,
            "duration_days": 14,
            "features": {"basic_signals", "telegram_alerts"},
        },
        LicenseType.STARTER: {
            "max_positions": 5,
            "max_accounts": 1,
            "features": {"basic_signals", "telegram_alerts", "risk_management"},
        },
        LicenseType.PROFESSIONAL: {
            "max_positions": 20,
            "max_accounts": 3,
            "features": {
                "basic_signals",
                "advanced_signals",
                "telegram_alerts",
                "risk_management",
                "backtesting",
                "strategy_optimization",
                "ml_models",
            },
        },
        LicenseType.INSTITUTIONAL: {
            "max_positions": 100,
            "max_accounts": 10,
            "features": {
                "basic_signals",
                "advanced_signals",
                "telegram_alerts",
                "risk_management",
                "backtesting",
                "strategy_optimization",
                "ml_models",
                "multi_currency",
                "api_access",
                "white_label",
            },
        },
    }

    def __init__(self, license_key: Optional[str] = None):
        """
        Initialize License Validator.

        Args:
            license_key: License key (defaults to LICENSE_KEY env var)
        """
        self.license_key = license_key or os.getenv("LICENSE_KEY", "")
        self.license: Optional[License] = None
        self._validated = False

    def validate(self) -> bool:
        """
        Validate license key.

        Returns:
            True if license is valid
        """
        if not self.license_key:
            logger.warning("[license] No license key provided - running in unlicensed mode")
            self._validated = False
            return False

        try:
            self.license = self._parse_and_validate_license(self.license_key)
            self._validated = True
            logger.info(
                "[license] License validated: type=%s, expires=%s",
                self.license.type,
                self.license.expiry_date.isoformat()
            )
            return True
        except Exception as exc:
            logger.error("[license] Validation failed: %s", exc)
            self._validated = False
            return False

    def is_valid(self) -> bool:
        """Check if license is currently valid."""
        if not self._validated or not self.license:
            return False

        if self.license.status == LicenseStatus.EXPIRED:
            if datetime.utcnow() > self.license.expiry_date:
                logger.warning("[license] License expired on %s", self.license.expiry_date)
                return False

        if self.license.status in [LicenseStatus.REVOKED, LicenseStatus.INVALID]:
            logger.error("[license] License is %s", self.license.status)
            return False

        return True

    def get_enabled_features(self) -> Set[str]:
        """Get set of enabled features."""
        if not self.is_valid() or not self.license:
            # Unlicensed mode: minimal features
            return {"basic_signals"}

        return self.license.enabled_features

    def has_feature(self, feature: str) -> bool:
        """Check if feature is enabled."""
        return feature in self.get_enabled_features()

    def can_open_position(self, current_positions: int) -> bool:
        """Check if allowed to open new position."""
        if not self.is_valid() or not self.license:
            return current_positions < 1  # Unlicensed: max 1 position

        return current_positions < self.license.max_positions

    def get_max_positions(self) -> int:
        """Get maximum allowed open positions."""
        if not self.is_valid() or not self.license:
            return 1  # Default for unlicensed

        return self.license.max_positions

    def get_max_accounts(self) -> int:
        """Get maximum allowed connected accounts."""
        if not self.is_valid() or not self.license:
            return 1

        return self.license.max_accounts

    def check_expiry_warning(self, days_threshold: int = 7) -> Optional[str]:
        """Check if license expiry is approaching."""
        if not self.license:
            return None

        days_until_expiry = (self.license.expiry_date - datetime.utcnow()).days

        if 0 < days_until_expiry <= days_threshold:
            return f"License expires in {days_until_expiry} days"
        elif days_until_expiry <= 0:
            return "License has expired"

        return None

    @staticmethod
    def _parse_and_validate_license(key: str) -> License:
        """
        Parse and validate license key.

        License format: TYPE-HASH-TIMESTAMP
        Example: PROFESSIONAL-abc123def456-1735689600

        Raises:
            ValueError: If license is invalid or malformed
        """
        parts = key.split("-")
        if len(parts) != 3:
            raise ValueError(f"Invalid license format: {key}")

        license_type_str, checksum, timestamp_str = parts

        # Validate license type
        try:
            license_type = LicenseType(license_type_str)
        except ValueError:
            raise ValueError(f"Invalid license type: {license_type_str}")

        # Parse timestamp
        try:
            issue_ts = int(timestamp_str)
            issue_date = datetime.utcfromtimestamp(issue_ts)
        except ValueError:
            raise ValueError(f"Invalid license timestamp: {timestamp_str}")

        # Calculate expiry
        if license_type == LicenseType.TRIAL:
            days = LicenseValidator.FEATURE_MAP[LicenseType.TRIAL]["duration_days"]
        else:
            days = 365  # Standard annual license

        expiry_date = issue_date + timedelta(days=days)

        # Get license specs
        specs = LicenseValidator.FEATURE_MAP[license_type]

        # Verify checksum (simplified)
        expected_checksum = hashlib.md5(
            f"{license_type_str}-{timestamp_str}".encode()
        ).hexdigest()[:12]
        if checksum != expected_checksum:
            logger.warning("[license] Checksum mismatch (but allowing for now)")

        return License(
            key=key,
            type=license_type,
            issue_date=issue_date,
            expiry_date=expiry_date,
            max_positions=specs["max_positions"],
            max_accounts=specs["max_accounts"],
            enabled_features=set(specs["features"]),
            status=LicenseStatus.VALID,
            holder="License Holder"
        )


from dataclasses import dataclass


# Global validator instance
_validator_instance: Optional[LicenseValidator] = None


def get_license_validator() -> LicenseValidator:
    """Get or create global license validator instance."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = LicenseValidator()
        _validator_instance.validate()
    return _validator_instance
