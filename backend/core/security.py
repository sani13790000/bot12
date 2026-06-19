"""
backend/core/security.py
Central security utilities — JWT, password hashing, token validation.

Fixes applied:
- Added decode_access_token as alias to maintain backward compatibility
- hmac.new → hmac.new (Python stdlib correct call verified)
- validate_access_token and validate_refresh_token always exported
- JTI pattern enforced on every decode
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.core.config import get_settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
_pwd_ctx = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(plain: str) -> str:
    """Return bcrypt hash of plain text password."""
    if not plain or len(plain) > 1024:
        raise ValueError("Invalid password length")
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time bcrypt verification. Returns False on any error."""
    try:
        return _pwd_ctx.verify(plain, hashed)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
_ALGORITHM = "HS256"
_JTI_PATTERN = re.compile(r"^[0-9a-f]{64}$")  # 32-byte hex = 64 hex chars


def _secret() -> str:
    s = get_settings().JWT_SECRET_KEY
    if len(s) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be >= 32 characters")
    return s


def create_access_token(
    subject: str,
    extra_claims: Optional[Dict[str, Any]] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    """
    Create signed JWT access token.

    Security:
    - HS256 with secret >= 32 bytes
    - jti = secrets.token_hex(32) — 256-bit entropy
    - Reserved claims (sub, iat, exp, jti, type) cannot be overridden by caller
    """
    s = get_settings()
    exp_minutes = expires_minutes or s.ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    jti = secrets.token_hex(32)

    claims: Dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=exp_minutes),
        "jti": jti,
        "type": "access",
    }
    if extra_claims:
        _RESERVED = {"sub", "iat", "exp", "jti", "type"}
        claims.update({k: v for k, v in extra_claims.items() if k not in _RESERVED})

    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM)


def create_refresh_token(subject: str) -> Tuple[str, str]:
    """
    Create signed JWT refresh token.
    Returns (token, jti) — store jti in DB for revocation.
    """
    s = get_settings()
    now = datetime.now(timezone.utc)
    jti = secrets.token_hex(32)
    claims = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(days=s.REFRESH_TOKEN_EXPIRE_DAYS),
        "jti": jti,
        "type": "refresh",
    }
    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM), jti


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate JWT. Raises ValueError with safe message.
    Never leaks cryptographic details to callers.
    """
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "jti", "type"]},
        )
    except JWTError as exc:
        log.warning("JWT decode failure: %s", type(exc).__name__)
        raise ValueError("Invalid or expired token") from exc

    if not _JTI_PATTERN.match(str(payload.get("jti", ""))):
        raise ValueError("Malformed token identifier")

    return payload


def validate_access_token(token: str) -> Dict[str, Any]:
    """Decode and assert type == 'access'."""
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise ValueError("Not an access token")
    return payload


def validate_refresh_token(token: str) -> Dict[str, Any]:
    """Decode and assert type == 'refresh'."""
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise ValueError("Not a refresh token")
    return payload


# Backward-compatibility alias — deps.py and some routes imported this name
decode_access_token = validate_access_token


# ---------------------------------------------------------------------------
# HMAC signature helpers for webhook / MQL5 payloads
# ---------------------------------------------------------------------------
def sign_payload(payload: bytes, secret: str) -> str:
    """Return hex HMAC-SHA256 signature."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, secret: str, provided_sig: str) -> bool:
    """Constant-time signature verification."""
    return hmac.compare_digest(sign_payload(payload, secret), provided_sig)


def generate_secure_token(nbytes: int = 32) -> str:
    """URL-safe random token for password reset, email verify, etc."""
    return secrets.token_urlsafe(nbytes)
