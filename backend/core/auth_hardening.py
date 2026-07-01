"""
backend/core/auth_hardening.py
Phase S - Auth & Token Hardening
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

_LOG = logging.getLogger(__name__)


@dataclass
class RevokedToken:
    jti: str
    revoked_at: float = field(default_factory=time.time)
    reason: str = ""


class TokenRevocationList:
    """In-memory token revocation list."""

    def __init__(self, ttl: float = 86400.0) -> None:
        self._store: Dict[str, RevokedToken] = {}
        self._ttl = ttl

    def revoke(self, jti: str, reason: str = "") -> None:
        self._store[jti] = RevokedToken(jti=jti, reason=reason)
        self._purge_expired()

    def is_revoked(self, jti: str) -> bool:
        self._purge_expired()
        return jti in self._store

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._store.items() if now - v.revoked_at > self._ttl]
        for k in expired:
            del self._store[k]


@dataclass
class RefreshToken:
    token: str
    jti: str
    user_id: str
    issued_at: float = field(default_factory=time.time)
    rotated: bool = False


class RefreshTokenStore:
    """Secure refresh token store."""

    def __init__(self) -> None:
        self._tokens: Dict[str, RefreshToken] = {}

    def store(self, token: str, jti: str, user_id: str) -> None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        self._tokens[token_hash] = RefreshToken(token=token_hash, jti=jti, user_id=user_id)

    def validate_and_rotate(self, token: str) -> Optional[RefreshToken]:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        rt = self._tokens.get(token_hash)
        if rt is None or rt.rotated:
            return None
        rt.rotated = True
        return rt

    def revoke(self, jti: str) -> None:
        for rt in list(self._tokens.values()):
            if rt.jti == jti:
                rt.rotated = True


revocation_list = TokenRevocationList()
refresh_token_store = RefreshTokenStore()
