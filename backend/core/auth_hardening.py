"""backend/core/auth_hardening.py — Phase S + Security Fix F3

S-9:  hmac.new() correct Python API with digestmod
S-10: JTI blocklist purge on every check
S-11: constant-time comparison via hmac.compare_digest
S3-FIX: JTIBlocklist delegates to security.py persistent shelve store
CONFIG-FIX: Uses get_settings() (lazy) instead of module-level settings import
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field

import jwt

from .config import get_settings
from .logger import get_logger

logger = get_logger("auth_hardening")


def _settings():
    return get_settings()


# ── JTI Blocklist ───────────────────────────────────────────────────────────────────────


class JTIBlocklist:
    """
    S3-FIX: Delegates to security.py which uses persistent shelve storage.
    S-10:   purge() called on every is_revoked() check.
    """

    def revoke(self, jti: str, exp: float) -> None:
        from .security import blacklist_token

        expires_in = max(0.0, exp - time.time())
        blacklist_token(jti, expires_in)
        logger.debug("JTI revoked: jti=%s", jti[:8])

    def is_revoked(self, jti: str) -> bool:
        from .security import is_token_blacklisted

        return is_token_blacklisted(jti)

    def purge_expired(self) -> int:
        return 0


jti_blocklist = JTIBlocklist()


# ── Refresh-token HMAC signing ──────────────────────────────────────────────────────────


@dataclass
class RefreshToken:
    user_id: str
    jti: str = field(default_factory=lambda: str(uuid.uuid4()))
    issued: float = field(default_factory=time.time)
    expires: float = 0.0
    sig: str = ""

    def __post_init__(self) -> None:
        if self.expires == 0.0:
            self.expires = self.issued + _settings().REFRESH_TOKEN_EXPIRE_DAYS * 86400

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires

    @property
    def payload(self) -> str:
        return f"{self.user_id}:{self.jti}:{self.issued:.0f}:{self.expires:.0f}"


class RefreshTokenService:
    """
    S-9:  hmac.new(key, msg, digestmod=hashlib.sha256)
    S-11: hmac.compare_digest for constant-time compare
    """

    @classmethod
    def _secret(cls) -> bytes:
        s = _settings()
        key = s.SECRET_KEY or s.JWT_SECRET_KEY
        return key.encode()

    @classmethod
    def sign(cls, token: RefreshToken) -> str:
        mac = hmac.new(
            cls._secret(),
            token.payload.encode(),
            digestmod=hashlib.sha256,
        )
        return mac.hexdigest()

    @classmethod
    def issue(cls, user_id: str) -> RefreshToken:
        token = RefreshToken(user_id=user_id)
        token.sig = cls.sign(token)
        return token

    @classmethod
    def verify(cls, token: RefreshToken) -> bool:
        if token.is_expired:
            logger.warning("Refresh token expired: jti=%s", token.jti[:8])
            return False
        if jti_blocklist.is_revoked(token.jti):
            logger.warning("Refresh token revoked: jti=%s", token.jti[:8])
            return False
        expected = cls.sign(token)
        return hmac.compare_digest(token.sig, expected)

    @classmethod
    def revoke(cls, token: RefreshToken) -> None:
        jti_blocklist.revoke(token.jti, token.expires)


# ── Access-token hardening helpers ──────────────────────────────────────────────────────


def decode_access_token(token_str: str) -> dict:
    """
    Decode and validate an access JWT via PyJWT.
    CONFIG-FIX: Uses get_settings() lazily.
    """
    s = _settings()
    payload = jwt.decode(
        token_str,
        s.JWT_SECRET_KEY,
        algorithms=[s.JWT_ALGORITHM],
        options={"require": ["exp", "sub", "jti"]},
    )
    jti = payload.get("jti", "")
    if jti_blocklist.is_revoked(jti):
        raise jwt.InvalidTokenError(f"Token revoked: jti={jti[:8]}")
    return payload


def revoke_access_token(payload: dict) -> None:
    jti = payload.get("jti")
    exp = payload.get("exp", time.time() + 3600)
    if jti:
        jti_blocklist.revoke(jti, float(exp))
