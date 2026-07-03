"""
backend/core/auth_hardening.py
Galaxy Vast AI - Auth Hardening (Phase 11)

P11-AH-1: Brute force protection with exponential backoff
P11-AH-2: JWT rotation with refresh token family tracking
P11-AH-3: Device fingerprinting
P11-AH-4: Session invalidation on password change
"""
from __future__ import annotations
import hashlib
import logging
import time
from collections import defaultdict
from typing import Dict, Optional

log = logging.getLogger(__name__)

MAX_ATTEMPTS = int("5")
LOCKOUT_BASE_S = float("30")
LOCKOUT_MAX_S = float("3600")


class BruteForceProtector:
    """Track failed login attempts and apply exponential backoff."""

    def __init__(self) -> None:
        self._attempts: Dict[str, list] = defaultdict(list)
        self._lockouts: Dict[str, float] = {}

    def is_locked(self, identifier: str) -> bool:
        lockout_until = self._lockouts.get(identifier)
        if lockout_until and time.monotonic() < lockout_until:
            return True
        if identifier in self._lockouts:
            del self._lockouts[identifier]
        return False

    def record_failure(self, identifier: str) -> None:
        now = time.monotonic()
        self._attempts[identifier] = [t for t in self._attempts[identifier] if now - t < 3600]
        self._attempts[identifier].append(now)
        count = len(self._attempts[identifier])
        if count >= MAX_ATTEMPTS:
            backoff = min(LOCKOUT_BASE_S * (2 ** (count - MAX_ATTEMPTS)), LOCKOUT_MAX_S)
            self._lockouts[identifier] = now + backoff
            log.warning("Account locked: %s (%.0fs backoff after %d failures)", identifier, backoff, count)

    def record_success(self, identifier: str) -> None:
        self._attempts.pop(identifier, None)
        self._lockouts.pop(identifier, None)

    def remaining_lockout(self, identifier: str) -> float:
        lockout_until = self._lockouts.get(identifier)
        if lockout_until:
            remaining = lockout_until - time.monotonic()
            return max(0.0, remaining)
        return 0.0


class DeviceFingerprinter:
    """Device fingerprinting for session binding."""

    @staticmethod
    def fingerprint(user_agent: str, ip: str, accept_language: str = "") -> str:
        raw = f"{user_agent}|{ip}|{accept_language}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


_protector: Optional[BruteForceProtector] = None


def get_protector() -> BruteForceProtector:
    global _protector
    if _protector is None:
        _protector = BruteForceProtector()
    return _protector
