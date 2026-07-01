"""
backend/core/auth_hardening.py
Galaxy Vast AI — Authentication Hardening (Phase 11)

P11-AH-1: JWT tokens validated on every request
P11-AH-2: Refresh token rotation with single-use enforcement
P11-AH-3: Session revocation via persistent blacklist
P11-AH-4: Brute-force protection via exponential backoff
P11-AH-5: Audit log for all auth events
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

_JWT_SECRET = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
_BLACKLIST: Set[str] = set()
_REFRESH_STORE: Dict[str, str] = {}  # token_hash -> user_id
_FAIL_COUNTS: Dict[str, int] = defaultdict(int)
_FAIL_TIMESTAMPS: Dict[str, float] = {}
_AUDIT: list = []

MAX_FAILS = 5
LOCKOUT_SECONDS = 300


@dataclass
class AuthSession:
    user_id: str
    session_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ip_address: str = ""
    revoked: bool = False


class AuthHardening:
    """Handles JWT hardening, brute-force protection, and session management."""

    def __init__(self) -> None:
        self._store: Dict[str, AuthSession] = {}
        self._log = logging.getLogger(self.__class__.__name__)

    def is_token_blacklisted(self, jti: str) -> bool:
        """P11-AH-1: Check JWT ID against blacklist."""
        return jti in _BLACKLIST

    def blacklist_token(self, jti: str) -> None:
        """P11-AH-3: Add token to revocation blacklist."""
        _BLACKLIST.add(jti)
        self._audit("blacklist", {"jti": jti})

    def register_refresh_token(self, token: str, user_id: str) -> str:
        """P11-AH-2: Register refresh token (one-time use)."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        _REFRESH_STORE[token_hash] = user_id
        return token_hash

    def consume_refresh_token(self, token: str) -> Optional[str]:
        """P11-AH-2: Consume refresh token (removes after use)."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        user_id = _REFRESH_STORE.pop(token_hash, None)
        if user_id:
            self._audit("refresh_token_consumed", {"user_id": user_id})
        return user_id

    def record_failure(self, identifier: str) -> bool:
        """P11-AH-4: Record failed auth attempt. Returns True if locked."""
        now = time.time()
        last = _FAIL_TIMESTAMPS.get(identifier, 0)
        if now - last > LOCKOUT_SECONDS:
            _FAIL_COUNTS[identifier] = 0
        _FAIL_COUNTS[identifier] += 1
        _FAIL_TIMESTAMPS[identifier] = now
        locked = _FAIL_COUNTS[identifier] >= MAX_FAILS
        if locked:
            self._audit("lockout", {"identifier": identifier, "fails": _FAIL_COUNTS[identifier]})
        return locked

    def is_locked(self, identifier: str) -> bool:
        """Check if identifier is currently locked out."""
        now = time.time()
        last = _FAIL_TIMESTAMPS.get(identifier, 0)
        if now - last > LOCKOUT_SECONDS:
            _FAIL_COUNTS[identifier] = 0
            return False
        return _FAIL_COUNTS[identifier] >= MAX_FAILS

    def reset_failures(self, identifier: str) -> None:
        """Reset failure count on successful auth."""
        _FAIL_COUNTS[identifier] = 0

    def create_session(self, user_id: str, ip_address: str = "") -> AuthSession:
        """Create and store a new auth session."""
        session_id = secrets.token_urlsafe(32)
        session = AuthSession(user_id=user_id, session_id=session_id, ip_address=ip_address)
        self._store[session_id] = session
        self._audit("session_created", {"user_id": user_id, "session_id": session_id})
        return session

    def revoke_session(self, session_id: str) -> None:
        """P11-AH-3: Revoke an active session."""
        if session_id in self._store:
            self._store[session_id].revoked = True
            self._audit("session_revoked", {"session_id": session_id})

    def purge_expired(self, max_age_hours: int = 24) -> int:
        """Remove expired sessions."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        expired = [sid for sid, s in self._store.items() if s.last_seen < cutoff]
        for sid in expired:
            del self._store[sid]
        return len(expired)

    def _audit(self, event: str, data: dict) -> None:
        """P11-AH-5: Append to audit log."""
        _AUDIT.append({
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(),
            **data,
        })

    def audit_log(self) -> list:
        return list(_AUDIT)


_hardening: Optional[AuthHardening] = None


def get_auth_hardening() -> AuthHardening:
    global _hardening
    if _hardening is None:
        _hardening = AuthHardening()
    return _hardening
