"""
backend/core/auth_hardening.py
Phase S - Auth & Token Hardening

S-9:  Constant-time token comparison via hmac.compare_digest
S-10: JWT refresh token rotation
S-11: Account lockout after N failed attempts
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from typing import Optional

logger = logging.getLogger(__name__)

_LOCKOUT_THRESHOLD = 5
_LOCKOUT_DURATION  = 900.0
_failed_attempts: dict[str, list[float]] = {}


def secure_token(nbytes: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(nbytes)


def constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time."""
    return hmac.compare_digest(
        a.encode() if isinstance(a, str) else a,
        b.encode() if isinstance(b, str) else b,
    )


def record_failed_attempt(user_id: str) -> int:
    """Record a failed login attempt. Returns failure count."""
    now = time.time()
    attempts = _failed_attempts.setdefault(user_id, [])
    attempts[:] = [t for t in attempts if now - t < _LOCKOUT_DURATION]
    attempts.append(now)
    logger.warning("Failed login attempt %d for %s", len(attempts), user_id)
    return len(attempts)


def is_locked_out(user_id: str) -> bool:
    """Return True if user is currently locked out."""
    now = time.time()
    recent = [t for t in _failed_attempts.get(user_id, []) if now - t < _LOCKOUT_DURATION]
    return len(recent) >= _LOCKOUT_THRESHOLD


def clear_failed_attempts(user_id: str) -> None:
    _failed_attempts.pop(user_id, None)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class TokenRotation:
    """JWT refresh token rotation manager."""

    def __init__(self) -> None:
        self._used: dict[str, float] = {}

    def issue(self, user_id: str, ttl: float = 86400.0) -> str:
        token = secure_token()
        self._used[hash_token(token)] = time.time() + ttl
        logger.debug("Issued refresh token for %s", user_id)
        return token

    def validate_and_rotate(self, token: str, user_id: str,
                             ttl: float = 86400.0) -> Optional[str]:
        h = hash_token(token)
        expiry = self._used.get(h)
        if expiry is None or time.time() > expiry:
            logger.warning("Invalid/expired refresh token for %s", user_id)
            return None
        del self._used[h]
        return self.issue(user_id, ttl)

    def revoke(self, token: str) -> None:
        self._used.pop(hash_token(token), None)

    def cleanup(self) -> int:
        now = time.time()
        expired = [k for k, v in self._used.items() if v < now]
        for k in expired:
            del self._used[k]
        return len(expired)
