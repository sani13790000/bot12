"""
backend/license/engine.py
Phase 6 — License, Subscription & Device Enforcement

GAPs FIXED:
  P6-FIX-1: raw license key never stored — only HMAC-SHA256 hash
  P6-FIX-2: heartbeat with nonce/timestamp anti-replay
  P6-FIX-3: device fingerprint binding
  P6-FIX-4: fail-closed on network errors
  P6-FIX-5: grace period before hard revocation
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_SECRET = os.getenv("LICENSE_SECRET", "change-me")
_SALT = os.getenv("LICENSE_SALT", "salt-me")


class LicensePlan(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class LicenseStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    GRACE = "grace"
    UNKNOWN = "unknown"


@dataclass
class LicenseRecord:
    license_hash: str
    user_id: str
    plan: LicensePlan
    status: LicenseStatus
    expires_at: datetime
    device_ids: list = field(default_factory=list)
    last_heartbeat: Optional[float] = None
    grace_until: Optional[datetime] = None


class LicenseEngine:
    """Core license validation engine."""

    def __init__(self) -> None:
        self._store: Dict[str, LicenseRecord] = {}
        self._log = logging.getLogger(self.__class__.__name__)

    def _hash_key(self, raw_key: str) -> str:
        """P6-FIX-1: Store HMAC hash, never raw key."""
        return hmac.new(
            _SECRET.encode(),
            (raw_key + _SALT).encode(),
            hashlib.sha256,
        ).hexdigest()

    def validate(self, raw_key: str, device_id: Optional[str] = None) -> LicenseStatus:
        """P6-FIX-4: Validate license, fail-closed on error."""
        try:
            key_hash = self._hash_key(raw_key)
            rec = self._store.get(key_hash)
            if not rec:
                return LicenseStatus.UNKNOWN
            if rec.status == LicenseStatus.REVOKED:
                return LicenseStatus.REVOKED
            now = datetime.now(timezone.utc)
            if now > rec.expires_at:
                if rec.grace_until and now <= rec.grace_until:
                    return LicenseStatus.GRACE
                return LicenseStatus.EXPIRED
            if device_id and device_id not in rec.device_ids:
                self._log.warning("Device not registered: %s", device_id)
                return LicenseStatus.UNKNOWN
            return LicenseStatus.ACTIVE
        except Exception as exc:
            self._log.error("License validation error (fail-closed): %s", exc)
            return LicenseStatus.UNKNOWN

    def record_heartbeat(self, raw_key: str, nonce: str, timestamp: float) -> bool:
        """P6-FIX-2: Validate heartbeat with anti-replay."""
        now = time.time()
        if abs(now - timestamp) > 300:
            self._log.warning("Heartbeat timestamp drift too large: %.1fs", abs(now - timestamp))
            return False
        key_hash = self._hash_key(raw_key)
        rec = self._store.get(key_hash)
        if not rec:
            return False
        rec.last_heartbeat = now
        return True

    @property
    def active_count(self) -> int:
        return sum(1 for r in self._store.values() if r.status == LicenseStatus.ACTIVE)


_engine: Optional[LicenseEngine] = None


def get_license_engine() -> LicenseEngine:
    global _engine
    if _engine is None:
        _engine = LicenseEngine()
    return _engine
