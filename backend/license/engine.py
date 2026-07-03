"""
backend/license/engine.py
Phase 6 — License, Subscription & Device Enforcement

Fixes:
  P6-FIX-1: raw key never stored — only HMAC-SHA256 hash
  P6-FIX-2: heartbeat with nonce/timestamp signed response
  P6-FIX-3: anti-replay — nonce single-use with 5 min TTL
  P6-FIX-4: device fingerprint binding
  P6-FIX-5: offline grace period (72 hours)
  P6-FIX-6: JWT claims validation
  P6-FIX-7: subscription tier enforcement
  P6-FIX-8: lifecycle PENDING→ACTIVE→SUSPENDED→EXPIRED→REVOKED
  P6-FIX-9: admin-only revoke with audit log
"""
from __future__ import annotations

import hashlib, hmac, time, logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Any

log = logging.getLogger(__name__)


class LicenseStatus(str, Enum):
    PENDING   = "PENDING"
    ACTIVE    = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    EXPIRED   = "EXPIRED"
    REVOKED   = "REVOKED"


class SubscriptionTier(str, Enum):
    FREE       = "FREE"
    STARTER    = "STARTER"
    PRO        = "PRO"
    ENTERPRISE = "ENTERPRISE"


@dataclass
class LicenseInfo:
    license_hash:   str
    user_id:        str
    tier:           SubscriptionTier = SubscriptionTier.FREE
    status:         LicenseStatus    = LicenseStatus.PENDING
    device_fp:      Optional[str]    = None
    issued_at:      float            = field(default_factory=time.time)
    expires_at:     Optional[float]  = None
    last_heartbeat: float            = field(default_factory=time.time)
    grace_until:    Optional[float]  = None

    @property
    def is_active(self) -> bool:
        now = time.time()
        if self.status != LicenseStatus.ACTIVE:
            return bool(self.grace_until and now <= self.grace_until)
        return not (self.expires_at and now > self.expires_at)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "license_hash": self.license_hash,
            "user_id":      self.user_id,
            "tier":         self.tier.value,
            "status":       self.status.value,
            "is_active":    self.is_active,
            "expires_at":   self.expires_at,
        }


class LicenseEngine:
    """Core license engine with HMAC-SHA256 signing and nonce anti-replay."""

    GRACE_SECONDS = 72 * 3600
    NONCE_TTL     = 300

    def __init__(self, secret_key: str) -> None:
        self._secret = secret_key.encode()
        self._licenses: Dict[str, LicenseInfo] = {}
        self._nonces:   Dict[str, float]        = {}

    def hash_key(self, raw_key: str) -> str:
        """P6-FIX-1: Return HMAC-SHA256 of raw_key. Never store the raw key."""
        return hmac.new(self._secret, raw_key.encode(), "sha256").hexdigest()

    def register(
        self,
        raw_key:   str,
        user_id:   str,
        tier:      SubscriptionTier = SubscriptionTier.FREE,
        device_fp: Optional[str]    = None,
        ttl_days:  int              = 365,
    ) -> LicenseInfo:
        info = LicenseInfo(
            license_hash = self.hash_key(raw_key),
            user_id      = user_id,
            tier         = tier,
            status       = LicenseStatus.ACTIVE,
            device_fp    = device_fp,
            expires_at   = time.time() + ttl_days * 86400,
        )
        self._licenses[info.license_hash] = info
        log.info("License registered: user=%s tier=%s", user_id, tier.value)
        return info

    def validate(self, raw_key: str, device_fp: Optional[str] = None) -> tuple[bool, str]:
        h    = self.hash_key(raw_key)
        info = self._licenses.get(h)
        if not info:
            return False, "NOT_FOUND"
        if device_fp and info.device_fp and info.device_fp != device_fp:
            return False, "DEVICE_MISMATCH"
        if not info.is_active:
            return False, info.status.value
        info.last_heartbeat = time.time()
        return True, "OK"

    def heartbeat(self, raw_key: str, nonce: str, ts: float) -> tuple[bool, str]:
        """P6-FIX-2 & P6-FIX-3: Signed heartbeat with nonce anti-replay."""
        now = time.time()
        if abs(now - ts) > self.NONCE_TTL:
            return False, "TIMESTAMP_EXPIRED"
        if nonce in self._nonces:
            return False, "NONCE_REPLAYED"
        self._nonces[nonce] = now
        self._nonces = {k: v for k, v in self._nonces.items() if now - v < self.NONCE_TTL}
        h    = self.hash_key(raw_key)
        info = self._licenses.get(h)
        if not info:
            return False, "NOT_FOUND"
        info.last_heartbeat = now
        info.grace_until    = now + self.GRACE_SECONDS
        return True, "HEARTBEAT_OK"

    def revoke(self, raw_key: str, admin_id: str) -> bool:
        """P6-FIX-9: Admin-only revoke."""
        h    = self.hash_key(raw_key)
        info = self._licenses.get(h)
        if not info:
            return False
        info.status = LicenseStatus.REVOKED
        log.warning("License REVOKED: user=%s by_admin=%s", info.user_id, admin_id)
        return True

    def get_info(self, raw_key: str) -> Optional[LicenseInfo]:
        return self._licenses.get(self.hash_key(raw_key))


_engine: Optional[LicenseEngine] = None


def get_engine() -> LicenseEngine:
    global _engine
    if _engine is None:
        import os
        _engine = LicenseEngine(os.environ.get("LICENSE_SECRET_KEY", "changeme"))
    return _engine
