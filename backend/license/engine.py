from __future__ import annotations
import hashlib
import hmac
import secrets
import time
from enum import Enum
from typing import Any, Dict, Optional
from ..core.logger import get_logger

logger = get_logger('license.engine')


class LicenseState(str, Enum):
    PENDING   = 'PENDING'
    ACTIVE    = 'ACTIVE'
    SUSPENDED = 'SUSPENDED'
    EXPIRED   = 'EXPIRED'
    REVOKED   = 'REVOKED'


class SubscriptionTier(str, Enum):
    FREE       = 'FREE'
    BASIC      = 'BASIC'
    PRO        = 'PRO'
    ENTERPRISE = 'ENTERPRISE'


_TIER_DEVICE_LIMITS: Dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE:       1,
    SubscriptionTier.BASIC:      2,
    SubscriptionTier.PRO:        5,
    SubscriptionTier.ENTERPRISE: 20,
}

_NONCE_TTL_S = 300


class LicenseEngine:
    """Core license validation engine with HMAC-SHA256 signing."""

    def __init__(self, secret_key: bytes) -> None:
        self._secret = secret_key
        self._nonces: Dict[str, float] = {}
        self._log = logger

    def hash_key(self, raw_key: str) -> str:
        """P6-FIX-1: HMAC-SHA256 of raw key."""
        return hmac.new(self._secret, raw_key.encode(), hashlib.sha256).hexdigest()

    def verify_key(self, raw_key: str, stored_hash: str) -> bool:
        return hmac.compare_digest(self.hash_key(raw_key), stored_hash)

    def create_heartbeat(self, license_id: str, tier: str) -> Dict[str, Any]:
        """P6-FIX-2: Signed heartbeat response."""
        nonce = secrets.token_hex(16)
        ts = time.time()
        payload = f'{license_id}:{tier}:{nonce}:{ts}'
        sig = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
        return {'license_id': license_id, 'tier': tier, 'nonce': nonce, 'ts': ts, 'sig': sig}

    def verify_heartbeat(self, payload: Dict[str, Any]) -> bool:
        """P6-FIX-3: Validate nonce + signature."""
        nonce = payload.get('nonce', '')
        ts = payload.get('ts', 0.0)
        if nonce in self._nonces:
            return False
        if abs(time.time() - ts) > _NONCE_TTL_S:
            return False
        self._nonces[nonce] = ts
        self._cleanup_nonces()
        lid = payload.get('license_id', '')
        tier = payload.get('tier', '')
        sig = payload.get('sig', '')
        expected = hmac.new(self._secret, f'{lid}:{tier}:{nonce}:{ts}'.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    def check_device_limit(self, tier: SubscriptionTier, current_count: int) -> bool:
        """P6-FIX-5: Fail-closed on unknown tier."""
        limit = _TIER_DEVICE_LIMITS.get(tier)
        if limit is None:
            self._log.warning('Unknown tier %s - failing closed', tier)
            return False
        return current_count < limit

    @staticmethod
    def can_transition(current: LicenseState, target: LicenseState) -> bool:
        """P6-FIX-8: Valid lifecycle transitions."""
        allowed = {
            LicenseState.PENDING:   {LicenseState.ACTIVE, LicenseState.REVOKED},
            LicenseState.ACTIVE:    {LicenseState.SUSPENDED, LicenseState.EXPIRED, LicenseState.REVOKED},
            LicenseState.SUSPENDED: {LicenseState.ACTIVE, LicenseState.REVOKED},
            LicenseState.EXPIRED:   {LicenseState.ACTIVE, LicenseState.REVOKED},
            LicenseState.REVOKED:   set(),
        }
        return target in allowed.get(current, set())

    def _cleanup_nonces(self) -> None:
        now = time.time()
        expired = [n for n, t in self._nonces.items() if now - t > _NONCE_TTL_S]
        for n in expired:
            del self._nonces[n]
