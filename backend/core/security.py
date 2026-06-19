"""backend/core/security.py — production-hardened v3.

FIX-10 sign_payload(): guard against empty secret (silent HMAC bypass).
FIX-11 hash_password(): enforce 72-byte bcrypt limit.
FIX-2  verify_password(): wrapped in try/except, always returns bool.
FIX-5  decode_access_token alias preserved for backward compatibility.
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

_pwd_ctx = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)

_BCRYPT_MAX_BYTES: int = 72


def hash_password(plain: str) -> str:
    """Return bcrypt hash. FIX-11: enforce 72-byte bcrypt hard limit."""
    if not plain:
        raise ValueError("Password cannot be empty")
    encoded = plain.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Password too long (max {_BCRYPT_MAX_BYTES} bytes when UTF-8 encoded)"
        )
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """FIX-2: always returns bool, never propagates passlib internals."""
    if not plain or not hashed:
        return False
    try:
        return bool(_pwd_ctx.verify(plain, hashed))
    except Exception as exc:
        log.warning("bcrypt verify error: %s", type(exc).__name__)
        return False


_ALGORITHM = "HS256"
_JTI_PATTERN = re.compile(r"^[0-9a-f]{64}$")


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
    s = get_settings()
    exp_minutes = expires_minutes or s.ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    jti = secrets.token_hex(32)
    _RESERVED = {"sub", "iat", "exp", "jti", "type"}
    claims: Dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=exp_minutes),
        "jti": jti,
        "type": "access",
    }
    if extra_claims:
        claims.update({k: v for k, v in extra_claims.items() if k not in _RESERVED})
    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM)


def create_refresh_token(subject: str) -> Tuple[str, str]:
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
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise ValueError("Not an access token")
    return payload


def validate_refresh_token(token: str) -> Dict[str, Any]:
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise ValueError("Not a refresh token")
    return payload


decode_access_token = validate_access_token


def sign_payload(payload: bytes, secret: str) -> str:
    """FIX-10: guard against empty secret."""
    if not secret:
        raise ValueError("HMAC secret must not be empty")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, secret: str, provided_sig: str) -> bool:
    if not secret or not provided_sig:
        return False
    try:
        return hmac.compare_digest(sign_payload(payload, secret), provided_sig)
    except Exception:
        return False


def generate_secure_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)
