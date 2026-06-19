"""
backend/core/security.py
Central security utilities — JWT, password hashing, token validation.
All cryptographic operations live here.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import time
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
    bcrypt__rounds=12,          # OWASP minimum for bcrypt
)


def hash_password(plain: str) -> str:
    """Return bcrypt hash of *plain*."""
    if not plain or len(plain) > 1024:
        raise ValueError("Invalid password length")
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time bcrypt verify — returns False on any error."""
    try:
        return _pwd_ctx.verify(plain, hashed)
    except Exception:          # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
_ALGORITHM = "HS256"
_JTI_PATTERN = re.compile(r"^[0-9a-f]{64}$")  # 32-byte hex


def _secret() -> str:
    s = get_settings().JWT_SECRET_KEY
    if len(s) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be ≥32 chars")
    return s


def create_access_token(
    subject: str,
    extra_claims: Optional[Dict[str, Any]] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    """
    Create a signed JWT access token.

    Security properties:
    - HS256 with secret ≥32 bytes
    - jti = 32-byte random hex (for revocation)
    - iat, exp, sub all set
    - subject is a string (user id), never embedded dict
    """
    settings = get_settings()
    exp_minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
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
        # Only allow safe extra claims — never override reserved ones
        _RESERVED = {"sub", "iat", "exp", "jti", "type"}
        safe = {k: v for k, v in extra_claims.items() if k not in _RESERVED}
        claims.update(safe)

    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM)


def create_refresh_token(subject: str) -> Tuple[str, str]:
    """
    Create a signed JWT refresh token.
    Returns (token, jti) — caller must store jti in DB for revocation.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    jti = secrets.token_hex(32)

    claims = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "jti": jti,
        "type": "refresh",
    }
    token = jwt.encode(claims, _secret(), algorithm=_ALGORITHM)
    return token, jti


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT.
    Raises ValueError with safe message on any failure.
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
        # Log detail internally, return safe message externally
        log.warning("JWT decode failure: %s", type(exc).__name__)
        raise ValueError("Invalid or expired token") from exc

    # Extra validation
    if not _JTI_PATTERN.match(str(payload.get("jti", ""))):
        raise ValueError("Malformed token identifier")

    return payload


def validate_access_token(token: str) -> Dict[str, Any]:
    """Decode and assert token type == 'access'."""
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise ValueError("Not an access token")
    return payload


def validate_refresh_token(token: str) -> Dict[str, Any]:
    """Decode and assert token type == 'refresh'."""
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise ValueError("Not a refresh token")
    return payload


# ---------------------------------------------------------------------------
# HMAC signature for webhook / MQL5 payloads
# ---------------------------------------------------------------------------

def sign_payload(payload: bytes, secret: str) -> str:
    """Return hex HMAC-SHA256 signature."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, secret: str, provided_sig: str) -> bool:
    """Constant-time signature verification."""
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, provided_sig)


# ---------------------------------------------------------------------------
# Secure random helpers
# ---------------------------------------------------------------------------

def generate_secure_token(nbytes: int = 32) -> str:
    """URL-safe random token (for password reset, email verify, etc.)."""
    return secrets.token_urlsafe(nbytes)
