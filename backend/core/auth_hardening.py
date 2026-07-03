"""
backend/core/auth_hardening.py
Phase S - Auth & Token Hardening

S-9:  hmac.new() correct Python API (hmac.new -> hmac.new with digestmod)
S-10: JTI blocklist purge on every check to prevent unbounded growth
S-11: constant-time comparison via hmac.compare_digest
"""
from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

import jwt

from .config import settings
from .logger import get_logger

logger = get_logger("auth_hardening")

# --------------------------------------------------------------------------- #
# JTI Blocklist
# --------------------------------------------------------------------------- #


class JTIBlocklist:
    """
    In-memory JTI (JWT ID) blocklist with automatic expiry purging.

    S-10: purge() is called on every is_revoked() check so the store
    never grows unbounded even if no external cron runs.
    """

    def __init__(self) -> None:
        self._store: Dict[str, float] = {}   # jti -> expiry unix timestamp

    def revoke(self, jti: str, exp: float) -> None:
        """Add a JTI to the blocklist until its natural expiry."""
        self._store[jti] = exp
        logger.debug("JTI revoked: jti=%s", jti[:8])

    def is_revoked(self, jti: str) -> bool:
        """Return True if jti is currently blocked."""
        self.purge_expired()   # S-10: inline purge
        return jti in self._store

    def purge_expired(self) -> int:
        """Remove all expired JTIs. Returns number purged."""
        now = time.time()
        expired = [jti for jti, exp in self._store.items() if exp < now]
        for jti in expired:
            del self._store[jti]
        return len(expired)


# Module-level singleton
jti_blocklist = JTIBlocklist()


# --------------------------------------------------------------------------- #
# Refresh-token HMAC signing
# --------------------------------------------------------------------------- #


@dataclass
class RefreshToken:
    """Signed refresh token envelope."""
    user_id:  str
    jti:      str = field(default_factory=lambda: str(uuid.uuid4()))
    issued:   float = field(default_factory=time.time)
    expires:  float = 0.0
    sig:      str   = ""

    def __post_init__(self) -> None:
        if self.expires == 0.0:
            self.expires = self.issued + settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires

    @property
    def payload(self) -> str:
        return f"{self.user_id}:{self.jti}:{self.issued:.0f}:{self.expires:.0f}"


class RefreshTokenService:
    """
    Signs and verifies refresh tokens using HMAC-SHA256.

    S-9: uses hmac.new(key, msg, digestmod=hashlib.sha256) — the only
         correct Python API.
    S-11: verification uses hmac.compare_digest for constant-time compare.
    """

    _SECRET: bytes = settings.SECRET_KEY.encode()

    @classmethod
    def sign(cls, token: RefreshToken) -> str:
        """Sign token payload and return hex signature."""
        mac = hmac.new(
            cls._SECRET,
            token.payload.encode(),
            digestmod=hashlib.sha256,
        )
        return mac.hexdigest()

    @classmethod
    def issue(cls, user_id: str) -> RefreshToken:
        """Create, sign, and return a new RefreshToken."""
        token = RefreshToken(user_id=user_id)
        token.sig = cls.sign(token)
        return token

    @classmethod
    def verify(cls, token: RefreshToken) -> bool:
        """
        Verify signature and blocklist in constant time.
        Returns False on any failure.
        """
        if token.is_expired:
            logger.warning("Refresh token expired: jti=%s", token.jti[:8])
            return False
        if jti_blocklist.is_revoked(token.jti):
            logger.warning("Refresh token revoked: jti=%s", token.jti[:8])
            return False
        expected = cls.sign(token)
        return hmac.compare_digest(token.sig, expected)   # S-11

    @classmethod
    def revoke(cls, token: RefreshToken) -> None:
        """Add token's JTI to the blocklist."""
        jti_blocklist.revoke(token.jti, token.expires)


# --------------------------------------------------------------------------- #
# Access-token hardening helpers
# --------------------------------------------------------------------------- #


def decode_access_token(token_str: str) -> dict:
    """
    Decode and validate an access JWT.
    Raises jwt.PyJWTError on any failure.
    """
    payload = jwt.decode(
        token_str,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"require": ["exp", "sub", "jti"]},
    )
    jti = payload.get("jti", "")
    if jti_blocklist.is_revoked(jti):
        raise jwt.InvalidTokenError(f"Token revoked: jti={jti[:8]}")
    return payload


def revoke_access_token(payload: dict) -> None:
    """Blocklist an access token by its JTI."""
    jti = payload.get("jti")
    exp = payload.get("exp", time.time() + 3600)
    if jti:
        jti_blocklist.revoke(jti, float(exp))
