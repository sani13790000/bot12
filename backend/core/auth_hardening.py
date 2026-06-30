"""
backend/core/auth_hardening.py
Phase S - Auth & Token Hardening
S-9:  hmac.new() correct Python 3 API
S-10: TokenRevocationList uses timezone-aware UTC
S-11: Argon2id default parameters tuned
S-12: Brute-force lockout with exponential backoff
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Set

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

LOGGER = logging.getLogger(__name__)

# Argon2id with conservative parameters
_ARGON2_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


class TokenRevocationList:
    """In-memory JWT revocation list with TTL-aware cleanup."""

    def __init__(self) -> None:
        self._store: Dict[str, datetime] = {}

    def revoke(self, jti: str, expires_at: datetime) -> None:
        if expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        self._store[jti] = expires_at
        LOGGER.info("Revoked token jti=%s", jti)

    def is_revoked(self, jti: str) -> bool:
        self.purge_expired()
        return jti in self._store

    def purge_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [jti for jti, exp in self._store.items() if exp <= now]
        for jti in expired:
            del self._store[jti]


class BruteForceProtection:
    """Track failed attempts and enforce exponential backoff."""

    def __init__(self, max_attempts: int = 5, base_delay_seconds: int = 2) -> None:
        self.max_attempts = max_attempts
        self.base_delay = base_delay_seconds
        self._attempts: Dict[str, int] = {}
        self._last_fail: Dict[str, float] = {}

    def record_failure(self, key: str) -> None:
        self._attempts[key] = self._attempts.get(key, 0) + 1
        self._last_fail[key] = time.time()

    def record_success(self, key: str) -> None:
        self._attempts.pop(key, None)
        self._last_fail.pop(key, None)

    def is_locked(self, key: str) -> bool:
        attempts = self._attempts.get(key, 0)
        if attempts < self.max_attempts:
            return False
        last_fail = self._last_fail.get(key, 0)
        delay = self.base_delay ** (attempts - self.max_attempts + 1)
        return time.time() - last_fail < delay

    def remaining_seconds(self, key: str) -> int:
        if not self.is_locked(key):
            return 0
        attempts = self._attempts.get(key, 0)
        delay = self.base_delay ** (attempts - self.max_attempts + 1)
        last_fail = self._last_fail.get(key, 0)
        return max(0, int(delay - (time.time() - last_fail)))


def hash_password(plain: str) -> str:
    return _ARGON2_HASHER.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        _ARGON2_HASHER.verify(hashed, plain)
        return True
    except VerifyMismatchError:
        return False


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def generate_secure_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)
